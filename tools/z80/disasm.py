#!/usr/bin/env python3
"""Disassemble the Mercs Z80 sound driver (uploaded by the 68k at boot) to z80/driver.asm.

ROM $FB75A..$FC6AA is copied to Z80 $0000 (code), $FC6AA..$FCFA0 to Z80 $1000 (music data);
see Z80_Driver* in mercs.asm. The source is verified by assembling with pasmo and comparing.

    python3 tools/z80/disasm.py [mercs.bin] [z80/driver.asm]      needs: pip z80dis, apt pasmo
"""
import os, re, subprocess, sys, tempfile
from z80dis import z80

SEGS = [(0x0000, 0xFB75A, 0xF50, 'code'), (0x1000, 0xFC6AA, 0x8F6, 'data')]   # z80 addr, rom addr, size
HW = {0x4000: 'YM_A0', 0x4001: 'YM_D0', 0x4002: 'YM_A1', 0x4003: 'YM_D1', 0x6000: 'Bank_Reg', 0x7F11: 'PSG_Port'}
FLOW_END = {'RET', 'RETI', 'RETN', 'HALT_NEVER'}

rom = open(sys.argv[1] if len(sys.argv) > 1 else 'mercs.bin', 'rb').read()
out_path = sys.argv[2] if len(sys.argv) > 2 else 'z80/driver.asm'
mem = bytearray(0x10000)
inseg = bytearray(0x10000)
for za, ra, n, _ in SEGS:
    mem[za:za + n] = rom[ra:ra + n]
    inseg[za:za + n] = b'\1' * n
CODE_END = SEGS[0][0] + SEGS[0][2]


def decode(a):
    if not inseg[a] or a >= CODE_END:
        return None
    i = z80.decode(bytes(mem[a:a + 4]), a)
    if i is None or i.status.name != 'OK' or a + i.len > CODE_END:
        return None
    # DD/FD/ED-prefixed no-ops cannot be written by an assembler; keep them as data
    if i.op.name == 'NOP' and i.len > 1:
        return None
    return i


def targets(i):
    """(flow-through?, [branch targets], [call targets])"""
    op = i.op.name
    addr = next((o[1] for o in i.operands if o[0].name == 'ADDR'), None)
    cond = any(o[0].name == 'COND' for o in i.operands)
    if op in ('RET', 'RETI', 'RETN'):
        return cond, [], []
    if op == 'JP':
        if any(o[0].name == 'REG_DEREF' for o in i.operands):
            return False, [], []
        return cond, [addr], []
    if op in ('JR', 'DJNZ'):
        return cond or op == 'DJNZ', [addr], []
    if op == 'CALL':
        return True, [], [addr]
    if op == 'RST':
        return True, [], [i.operands[0][1]]
    return True, [], []


def plausible(a, limit=48):
    for k in range(limit):
        i = decode(a)
        if i is None:
            return False
        if i.op.name == 'NOP' and mem[a:a + 4] == b'\0\0\0\0':
            return False
        flow, br, calls = targets(i)
        for t in br + calls:
            if t is None or t >= CODE_END:
                return False
        if not flow:
            return True
        a += i.len
    return True


code, calls, branches, dataref, memref = {}, set(), set(), set(), set()
wtables = {}     # addr -> number of 16-bit data constants


def dispatched(d):
    """Is the table at d loaded with ld rr,d and used by a jp (hl)/(ix) within a few instructions?"""
    order = sorted(code)
    pos = {a: i for i, a in enumerate(order)}
    for a, i in code.items():
        if i.op.name == 'LD' and any(o[0].name == 'IMM' and o[1] == d for o in i.operands):
            k = pos[a]
            for j in range(k + 1, min(k + 24, len(order))):
                x = code[order[j]]
                if x.op.name == 'JP' and any(o[0].name == 'REG_DEREF' for o in x.operands):
                    return True
                if x.op.name in ('RET', 'RETI', 'RETN'):
                    break
    return False
tables = {}      # addr -> number of 16-bit code pointers


def flow(work):
    while work:
        a = work.pop()
        while a not in code:
            i = decode(a)
            if i is None:
                break
            code[a] = i
            f, br, cl = targets(i)
            for t in br:
                branches.add(t); work.append(t)
            for t in cl:
                calls.add(t); work.append(t)
            if i.op.name == 'LD':
                for o in i.operands:
                    if o[0].name == 'IMM' and o[1] >= 0x100 and any(p[0].name == 'REG' and p[1].name in ('HL', 'DE', 'BC', 'IX', 'IY') for p in i.operands):
                        dataref.add(o[1])
            for o in i.operands:
                if o[0].name == 'ADDR_DEREF':
                    memref.add(o[1])
            if not f:
                break
            a += i.len


work = [0x0000, 0x0038, 0x0066]
flow(work)
tried = set()
while True:                          # pointer tables of routines: data refs whose words all look like code
    new = False
    for d in sorted(dataref - tried):
        tried.add(d)
        if d >= CODE_END or d in code:
            continue
        # 16-bit constants first: a monotonic run (e.g. YM2612 F-numbers) is data, whatever it points at
        words, k = [], 0
        while d + 2 * k + 1 < CODE_END:
            w = mem[d + 2 * k] | mem[d + 2 * k + 1] << 8
            if not 0x80 <= w < 0x800 or (words and abs(w - words[-1]) > 0x80):
                break
            words.append(w); k += 1
        inc = all(x <= y for x, y in zip(words, words[1:])); dec = all(x >= y for x, y in zip(words, words[1:]))
        disp = dispatched(d)
        if len(words) >= 6 and (inc or dec) and not disp:
            wtables[d] = len(words)
            continue
        n = 0
        while d + 2 * n + 1 < CODE_END:
            w = mem[d + 2 * n] | mem[d + 2 * n + 1] << 8
            if w >= CODE_END or w in (0,) or not plausible(w):
                break
            n += 1
        if n >= 3:
            targets_ = [mem[d + 2 * k] | mem[d + 2 * k + 1] << 8 for k in range(n)]
            solid = sum(1 for t in targets_ if t in calls or t in branches)   # called/jumped to elsewhere
            if solid >= max(2, n // 2) or disp:
                tables[d] = n
                for t in targets_:
                    calls.add(t); work.append(t)
                new = True
    flow(work)
    if not new:
        break

# second segment: pointer table at the start (little-endian words into the segment)
S2 = 0x1000
seg2_ptrs = []
a = S2
while a < S2 + 0x8F6:
    w = mem[a] | mem[a + 1] << 8
    if not (S2 <= w < S2 + 0x8F6) or (seg2_ptrs and w < seg2_ptrs[-1]) or a >= (seg2_ptrs[0] if seg2_ptrs else 0xFFFF):
        break
    seg2_ptrs.append(w); a += 2
seg2_table_end = a

labels = {}
for t in sorted(calls | branches | set(tables)):
    if t in code:
        labels[t] = ('sub_%04X' if t in calls or t in (0, 0x38, 0x66) else 'loc_%04X') % t
for d in sorted(dataref):
    if d < CODE_END and d not in labels:
        labels[d] = 'dat_%04X' % d
for t in tables:
    labels[t] = 'tbl_%04X' % t
for t in wtables:
    labels[t] = 'val_%04X' % t
labels.update({0x0000: 'Reset', 0x0038: 'IRQ', 0x0066: 'NMI'})
# hand-chosen names (evidence in the code): rst $08 polls the YM2612 busy flag, rst $28/$30 index and
# load a word table, $39 sets the stack and runs the main loop, $0AF8 does sub $E0 ; table ; jp (hl)
for a, nm in {0x0008: 'WaitYM', 0x0028: 'WordTableIndex', 0x0030: 'LoadWord', 0x0039: 'Main',
              0x0AF8: 'CoordFlag_Dispatch', 0x0B0F: 'CoordFlag_Table'}.items():
    if a in labels:
        labels[a] = nm
# the 68k->Z80 sound mailbox (see PlaySound in mercs.asm): sound ids with bit 7 set go into a 3-byte queue at $1C0A..$1C0C
for a, nm in {0x0825: 'Queue_Scan', 0x082E: 'Queue_Slot', 0x04A4: 'Cmd_Dispatch', 0x04A7: 'Cmd_DispatchA',
              0x04F4: 'Cmd_Music_81', 0x05A2: 'Cmd_Sfx_B1', 0x0595: 'Cmd_Sfx_D4'}.items():
    if a in labels:
        labels[a] = nm
for w in seg2_ptrs:
    labels.setdefault(w, 'seq_%04X' % w)
inside = set()
for a, i in code.items():
    inside.update(range(a + 1, a + i.len))
overlaps = sorted(t for t in labels if t in inside)
for t in overlaps:                      # a label inside an instruction cannot be placed
    del labels[t]
SYM = dict(HW)
VARNAMES = {0x1C02: 'Priority_Table_Ptr', 0x1C09: 'Cmd_Current', 0x1C0A: 'Cmd_Queue0', 0x1C0B: 'Cmd_Queue1', 0x1C0C: 'Cmd_Queue2',
            0x1C10: 'Cmd_StopAll', 0x1C18: 'Cmd_Priority'}
for m in sorted(memref):
    if m not in SYM and m >= 0x1000:
        SYM[m] = VARNAMES.get(m, 'var_%04X' % m)


def render(i):
    t = z80.disasm(i)
    op = i.op.name
    m = re.match(r'(\w+)\s*(.*)', t)
    mn, ops = m.group(1).lower(), m.group(2).lower()
    tg = [o[1] for o in i.operands if o[0].name == 'ADDR']
    if tg and op in ('JP', 'JR', 'CALL', 'DJNZ'):
        ops = re.sub(r'0x[0-9a-fA-F]+$', labels.get(tg[0], '$%04X' % tg[0]), ops)
    elif op == 'RST':
        ops = ops.replace('0x', '$')
    else:
        def mem_sub(mm):
            v = int(mm.group(1), 16)
            return '(%s)' % SYM.get(v, '$%04X' % v)
        ops = re.sub(r'\(0x([0-9a-fA-F]{3,4})\)', mem_sub, ops)
        if op == 'LD' and re.match(r'(hl|de|bc|ix|iy|sp),0x', ops, re.I):
            reg, val = ops.split(',', 1)
            v = int(val, 16)
            if v in labels:
                ops = '%s,%s' % (reg, labels[v])
    ops = re.sub(r'0x([0-9a-fA-F]+)', lambda mm: '$' + mm.group(1).upper(), ops)
    return mn + (' ' + ops if ops else '')


def build(bad):
    lines = ['; Mercs - Z80 sound driver (pasmo syntax). Generated by tools/z80/disasm.py.',
             '; Segment 1 is copied from ROM $FB75A to Z80 $0000 (code), segment 2 from $FC6AA to Z80 $1000 (sequences).', '']
    for a, n in sorted(SYM.items()):
        lines.append('%s\tequ\t$%04X' % (n, a))
    lines.append('')
    owner = {}
    for za, ra, n, kind in SEGS:
        lines.append('\torg\t$%04X' % za)
        a, end = za, za + n
        while a < end:
            if a in labels:
                lines.append('%s:' % labels[a])
            if a in code and a not in bad:
                owner[len(lines) + 1] = a
                lines.append('\t' + render(code[a])); a += code[a].len
                continue
            if a in code:                                   # fallback: raw bytes of one instruction
                k = code[a].len
                lines.append('\tdefb\t' + ','.join('$%02X' % b for b in mem[a:a + k]) + '\t; ' + render(code[a]))
                owner[len(lines)] = a; a += k; continue
            if a in wtables:
                k = wtables[a]
                lines.append('\tdefw\t' + ','.join('$%04X' % (mem[a + 2 * j] | mem[a + 2 * j + 1] << 8) for j in range(k)))
                a += 2 * k; continue
            if a in tables:
                k = tables[a]
                lines.append('\tdefw\t' + ','.join(labels.get(mem[a + 2 * j] | mem[a + 2 * j + 1] << 8, '$%04X' % (mem[a + 2 * j] | mem[a + 2 * j + 1] << 8)) for j in range(k)))
                a += 2 * k; continue
            if kind == 'data' and a < seg2_table_end:
                k = min(8, (seg2_table_end - a) // 2)
                lines.append('\tdefw\t' + ','.join(labels.get(mem[a + 2 * j] | mem[a + 2 * j + 1] << 8, '$%04X' % (mem[a + 2 * j] | mem[a + 2 * j + 1] << 8)) for j in range(k)))
                a += 2 * k; continue
            stop = min([x for x in list(code) + list(labels) + list(tables) if x > a] + [end, a + 16 - (a % 16) if a % 16 else a + 16])
            if kind == 'data' and a >= seg2_table_end:
                nxt = [x for x in labels if x > a]
                stop = min(nxt + [end, a + 16 - (a % 16) if a % 16 else a + 16])
            stop = min(stop, end)
            lines.append('\tdefb\t' + ','.join('$%02X' % b for b in mem[a:stop])); a = stop
    return '\n'.join(lines) + '\n'


def assemble(src):
    with tempfile.TemporaryDirectory() as t:
        s, b = os.path.join(t, 'd.z80'), os.path.join(t, 'd.bin')
        open(s, 'w').write(src)
        r = subprocess.run(['pasmo', '--bin', s, b], capture_output=True, text=True)
        errs = [int(x) for x in re.findall(r'line (\d+)', r.stdout + r.stderr)]
        return (open(b, 'rb').read() if os.path.exists(b) else None), errs, r.stdout + r.stderr


bad = set()
for rnd in range(400):
    src = build(bad)
    img, errs, msg = assemble(src)
    new = set()
    lines = src.split('\n')
    for ln in errs:
        for k in range(ln, 0, -1):                          # map an assembler error line to its instruction
            if k in (0,): break
            txt = lines[k - 1].strip()
            m = None
            for a, i in code.items():
                pass
            break
    if img is None:
        und = re.findall(r"Symbol '(\w+)' is undefined", msg)
        gone = [t for t, n in labels.items() if n in und]
        if not gone:
            print('assembler error:', msg[:300]); sys.exit(1)
        for t in gone:                   # label never reached an instruction boundary: keep it numeric
            del labels[t]
        continue
    for za, ra, n, _ in SEGS:
        if img[za:za + n] != mem[za:za + n]:
            for a in range(za, za + n):
                if img[a] != mem[a]:
                    cand = max((x for x in code if x <= a), default=None)
                    if cand is not None and cand + code[cand].len > a:
                        new.add(cand)
                    else:
                        print('mismatch in data at %04X' % a); sys.exit(1)
                    break
    new -= bad
    if not new:
        break
    bad |= new
else:
    sys.exit('did not converge')

ok = all(img[za:za + n] == mem[za:za + n] for za, _, n, _ in SEGS)
os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
open(out_path, 'w').write(src)
codebytes = sum(i.len for a, i in code.items())
print('word tables:', ' '.join('%04X(x%d)' % (a, n) for a, n in sorted(wtables.items())), '| code tables:', ' '.join('%04X(x%d)' % (a, n) for a, n in sorted(tables.items())))
print('z80: %d instructions, %d code bytes of %d; %d tables; %d labels; fallbacks %d; reassembly %s' % (
    len(code), codebytes, SEGS[0][2], len(tables), len(labels), len(bad), 'BYTE-IDENTICAL' if ok else 'MISMATCH'))
print('labels dropped (inside instructions): %s' % ' '.join('%04X' % t for t in overlaps))
print('seg2 pointer table: %d entries; hardware/variable symbols: %d' % (len(seg2_ptrs), len(SYM)))
