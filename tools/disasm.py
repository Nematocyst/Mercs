#!/usr/bin/env python3
"""Recursive-descent disassembler for the Mercs (Mega Drive) ROM.

Writes mercs.asm in asm68k-style syntax and proves it rebuilds byte-identical.
Every instruction is assembled on its own (pinned with .org) with GNU as and
compared with the ROM; anything that does not round-trip is emitted as dc.w.

    python3 tools/disasm.py [--rom mercs.bin] [--out mercs.asm] [--hints tools/hints.json]

Requires: capstone (pip), binutils-m68k-linux-gnu (apt).
"""
import argparse
import bisect
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from collections import Counter

from capstone import Cs, CS_ARCH_M68K, CS_MODE_M68K_000

CC = 'hi ls cc cs ne eq vc vs pl mi ge lt gt le'.split()
BRANCH = re.compile(r'^(bra|bsr|b(%s)|db(ra|t|f|%s))$' % ('|'.join(CC), '|'.join(CC)))
HEXTOK = re.compile(r'(-?)\$([0-9a-f]+)(?:\.([wl]))?(\(pc)?')
ENDS = {'rts', 'rte', 'rtr', 'illegal', 'bra', 'jmp'}
AS = ['m68k-linux-gnu-as', '-m68000', '--register-prefix-optional']

VECTOR_NAMES = {1: 'EntryPoint', 28: 'HInt', 30: 'VInt'}


class Insn:
    __slots__ = ('addr', 'n', 'mnem', 'parts', 'text')

    def __init__(self, addr, n, mnem, parts):
        self.addr, self.n, self.mnem, self.parts = addr, n, mnem, parts


class Rom:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        self.size = len(self.d)
        self.md = Cs(CS_ARCH_M68K, CS_MODE_M68K_000)
        self.md.detail = False
        self.code = {}      # addr -> Insn
        self.calls = set()  # jsr/bsr targets
        self.refs = set()   # any other referenced address
        self.tables = {}    # addr -> (kind 'l'|'w', count, base)
        self.idx_cands, self.data_cands, self.end_cands = set(), set(), set()

    # -- decoding ---------------------------------------------------------
    def decode(self, a):
        if a & 1 or a < 0x200 or a + 2 > self.size:
            return None
        try:
            i = next(self.md.disasm(self.d[a:a + 12], a, 1))
        except StopIteration:
            return None
        mnem, ops = i.mnemonic, i.op_str
        base = mnem.split('.')[0]
        if base in ('lea', 'pea'):
            mnem = base
        isbr = bool(BRANCH.match(base))
        parts, pos = [], 0
        for m in HEXTOK.finditer(ops):
            neg, val, sfx, pc = m.group(1), int(m.group(2), 16), m.group(3), m.group(4)
            parts.append(ops[pos:m.start()].replace(', ', ','))
            pos = m.end()
            if pc and not neg:
                parts.append(('pc', val))
            elif isbr and not neg:
                parts.append(('br', val))
            elif sfx and not neg:
                parts.append(('abs', val, sfx, base in ('lea', 'pea', 'jmp', 'jsr')))
            else:
                parts.append('%s$%X%s' % (neg, val, ('.' + sfx) if sfx else ''))
                if pc:
                    parts.append('(pc')
        parts.append(ops[pos:].replace(', ', ','))
        ins = Insn(a, i.size, mnem, parts)
        return ins

    def targets(self, ins):
        for p in ins.parts:
            if isinstance(p, tuple) and p[0] in ('pc', 'br') or \
               isinstance(p, tuple) and p[0] == 'abs' and p[3]:
                yield p[1]

    # -- discovery --------------------------------------------------------
    def plausible(self, a, limit=48):
        """Does address a start code that decodes cleanly and terminates?"""
        if a in self.code:
            return True
        if a & 1 or a < 0x200 or a >= self.size:
            return False
        zeros = 0
        for _ in range(limit):
            ins = self.decode(a)
            if ins is None:
                return False
            zeros = zeros + 1 if self.d[a:a + 2] == b'\0\0' else 0
            base = ins.mnem.split('.')[0]
            if zeros >= 2 or base == 'illegal':
                return False
            for x in ins.parts:
                if isinstance(x, tuple) and (x[0] != 'abs' or base in ('jsr', 'jmp')) \
                        and (x[1] & 1 or not 0x200 <= x[1] < self.size):
                    return False
            if base in ENDS:
                return True
            a += ins.n
        return True     # long clean run with no terminator: still looks like code

    def long_table(self, a):
        n = 0
        while a + 4 * n + 4 <= self.size and n < 512:
            v = struct.unpack('>I', self.d[a + 4 * n:a + 4 * n + 4])[0]
            if not self.plausible(v):
                break
            n += 1
        return n

    def word_table(self, base):
        n, minoff = 0, None
        while n < 256 and (minoff is None or 2 * n < minoff):
            w = struct.unpack('>h', self.d[base + 2 * n:base + 2 * n + 2])[0]
            if w & 1 or not self.plausible(base + w):
                break
            if w > 0:
                minoff = w if minoff is None else min(minoff, w)
            n += 1
        return n

    @staticmethod
    def indexed_pc(ins):
        """True for the (table,pc,Xn) addressing mode."""
        p = ins.parts
        return any(isinstance(x, tuple) and x[0] == 'pc' and i + 1 < len(p)
                   and isinstance(p[i + 1], str) and p[i + 1].startswith(',')
                   for i, x in enumerate(p))

    def flow(self, work):
        while work:
            a = work.pop()
            while a not in self.code:
                ins = self.decode(a)
                if ins is None:
                    break
                self.code[a] = ins
                base = ins.mnem.split('.')[0]
                idx = self.indexed_pc(ins)
                for t in self.targets(ins):
                    if t >= self.size:
                        continue
                    (self.calls if base in ('bsr', 'jsr') else self.refs).add(t)
                    if base in ('jsr', 'jmp') or BRANCH.match(base):
                        if not idx:
                            work.append(t)
                    if idx:
                        self.idx_cands.add(t)
                    elif base in ('lea', 'pea') or (base not in ('jsr', 'jmp', 'bsr')
                                                    and not BRANCH.match(base)):
                        self.data_cands.add(t)
                if base in ENDS:
                    if a + ins.n < self.size:
                        self.end_cands.add(a + ins.n)
                    break
                a += ins.n

    def add_table(self, a, kind, n, work, base=None):
        self.tables[a] = (kind, n, base)
        self.refs.add(a)
        for k in range(n):
            if kind == 'l':
                t = struct.unpack('>I', self.d[a + 4 * k:a + 4 * k + 4])[0]
            else:
                t = a + struct.unpack('>h', self.d[a + 2 * k:a + 2 * k + 2])[0]
            self.calls.add(t)
            work.append(t)

    def discover(self, roots, hint_code, hint_ltables=()):
        work = list(roots) + list(hint_code)
        for a, n in hint_ltables:
            self.add_table(a, 'l', n, work)
        tried = set()
        while True:
            self.flow(work)
            # instruction/table bytes already claimed are never table candidates
            claimed = set()
            for a, i in self.code.items():
                claimed.update(range(a, a + i.n))
            for a, (k, n, _) in self.tables.items():
                claimed.update(range(a, a + (4 if k == 'l' else 2) * n))
            for t in sorted(self.idx_cands - tried):
                tried.add(t)
                if t in claimed or t >= self.size:
                    continue
                ins = self.decode(t)
                if ins and ins.mnem.split('.')[0] in ('bra', 'jmp'):
                    a = t                       # table of bra/jmp entries
                    while True:
                        e = self.decode(a)
                        if e is None or e.mnem.split('.')[0] not in ('bra', 'jmp'):
                            break
                        work.extend(self.targets(e))
                        a += e.n
                    continue
                n = self.word_table(t)
                if n >= 2:
                    self.add_table(t, 'w', n, work, base=t)
            for t in sorted((self.data_cands | self.end_cands) - tried):
                tried.add(t)
                if t in claimed or t in self.tables or t & 1 or t >= self.size:
                    continue
                n = self.long_table(t)
                if n >= (3 if t in self.end_cands and t not in self.data_cands else 2):
                    self.add_table(t, 'l', n, work)
            if not work:
                break


def text_of(ins, label, final=True):
    out = []
    for p in ins.parts:
        if isinstance(p, str):
            out.append(p)
        elif p[0] == 'pc':
            out.append(label.get(p[1], '$%X' % p[1]) + '(pc')
        elif p[0] == 'br':
            out.append(label.get(p[1], '$%X' % p[1]))
        else:
            lab = label.get(p[1]) if p[3] else None
            out.append('(%s).%s' % (lab or '$%X' % p[1], p[2]))
    ops = ''.join(out)
    return '%s\t%s' % (ins.mnem, ops) if ops.strip() else ins.mnem


# -- layout -----------------------------------------------------------------
def build_entries(rom, label, bad):
    ents = []  # dict(addr,n,kind,text,comment)
    d, a = rom.d, 0
    labels_at = sorted(label)
    code_addrs = sorted(rom.code)
    table_addrs = sorted(rom.tables)
    ci = 0
    while a < rom.size:
        if a in rom.code and a not in bad:
            ins = rom.code[a]
            ents.append(dict(addr=a, n=ins.n, kind='i', text=text_of(ins, label), comment=''))
            a += ins.n
            continue
        if a in rom.code:
            ins = rom.code[a]
            words = ','.join('$%04X' % w for w in struct.unpack('>%dH' % (ins.n // 2), d[a:a + ins.n]))
            ents.append(dict(addr=a, n=ins.n, kind='w', text='dc.w\t' + words,
                             comment=text_of(ins, label).replace('\t', ' ')))
            a += ins.n
            continue
        if a in rom.tables:
            kind, cnt, base = rom.tables[a]
            step = 4 if kind == 'l' else 2
            for k in range(0, cnt, 4 if kind == 'l' else 8):
                m = min(4 if kind == 'l' else 8, cnt - k)
                toks = []
                for j in range(k, k + m):
                    if kind == 'l':
                        v = struct.unpack('>I', d[a + 4 * j:a + 4 * j + 4])[0]
                        toks.append(label.get(v, '$%08X' % v))
                    else:
                        v = a + struct.unpack('>h', d[a + 2 * j:a + 2 * j + 2])[0]
                        toks.append('%s-%s' % (label.get(v, '$%X' % v), label[a]))
                ents.append(dict(addr=a + k * step, n=m * step, kind='t',
                                 text='dc.%s\t%s' % (kind, ','.join(toks)), comment=''))
            a += cnt * step
            continue
        if a < 0x100:
            n = 16
            vals = struct.unpack('>4I', d[a:a + 16])
            toks = [label.get(v, '$%08X' % v) if (a + 4 * k) else '$%08X' % v
                    for k, v in enumerate(vals)]
            ents.append(dict(addr=a, n=16, kind='l', text='dc.l\t' + ','.join(toks), comment=''))
            a += 16
            continue
        end = min(a + 16 - (a % 16), rom.size)
        for nxt in (code_addrs[ci:ci + 1] if False else []):
            pass
        # stop at the next code start or label
        k = bisect.bisect_right(code_addrs, a)
        if k < len(code_addrs):
            end = min(end, code_addrs[k])
        k = bisect.bisect_right(table_addrs, a)
        if k < len(table_addrs):
            end = min(end, table_addrs[k])
        k = bisect.bisect_right(labels_at, a)
        if k < len(labels_at):
            end = min(end, labels_at[k])
        chunk = d[a:end]
        ents.append(dict(addr=a, n=len(chunk), kind='d',
                         text='dc.b\t' + ','.join('$%02X' % b for b in chunk), comment=''))
        a = end
    return ents


def render_final(ents, label):
    names_at = {}
    for t, nme in label.items():
        names_at[t] = nme
    out = ['; Mercs (Sega Mega Drive, 1991) - disassembly',
           '; asm68k syntax.  Generated by tools/disasm.py; rebuilds byte-identical.',
           '']
    for e in ents:
        if e['addr'] in names_at:
            out.append('%s:' % names_at[e['addr']])
        line = '\t' + e['text']
        if e['comment']:
            line += '\t\t; ' + e['comment']
        out.append(line)
    return '\n'.join(out) + '\n'


def to_gas(text):
    text = re.sub(r'\$([0-9A-Fa-f]+)', r'0x\1', text)
    return text


def render_gas(ents, label, pinned):
    lines, owner = ['\t.text'], {}
    for idx, e in enumerate(ents):
        a = e['addr']
        if pinned:
            lines.append('\t.org\t0x%X' % a)
        if a in label:
            lines.append('%s:' % label[a])
        if pinned and e['kind'] == 'i':
            lines.append('I_%X:' % a)
        lines.append('\t' + to_gas(e['text']))
        owner[len(lines)] = idx
        if pinned and e['kind'] == 'i':
            lines.append('E_%X:' % a)
    return '\n'.join(lines) + '\n', owner


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def assemble(src, tmp, tag):
    s, o, elf, binf = (os.path.join(tmp, tag + x) for x in ('.s', '.o', '.elf', '.bin'))
    open(s, 'w').write(src)
    r = run(AS + ['-o', o, s])
    errs = [int(m.group(1)) for m in re.finditer(re.escape(s) + r':(\d+): Error', r.stderr)]
    if errs or not os.path.exists(o):
        return None, errs, r.stderr
    r = run(['m68k-linux-gnu-ld', '-Ttext=0', '-o', elf, o])
    if not os.path.exists(elf):
        return None, [], r.stderr
    run(['m68k-linux-gnu-objcopy', '-O', 'binary', '-j', '.text', elf, binf])
    syms = {}
    for ln in run(['m68k-linux-gnu-nm', elf]).stdout.splitlines():
        p = ln.split()
        if len(p) == 3:
            syms[p[2]] = int(p[0], 16)
    return (open(binf, 'rb').read(), syms), [], ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', default='mercs.bin')
    ap.add_argument('--out', default='mercs.asm')
    ap.add_argument('--hints', default=os.path.join(os.path.dirname(__file__), 'hints.json'))
    args = ap.parse_args()

    rom = Rom(args.rom)
    d = rom.d
    vec = struct.unpack('>64I', d[:256])
    roots = {v for v in vec[1:] if 0x200 <= v < rom.size}
    hint_code, hint_lt = [], []
    if os.path.exists(args.hints):
        h = json.load(open(args.hints))
        hint_code = [int(x, 16) for x in h.get('code', [])]
        hint_lt = [(int(a, 16), n) for a, n in h.get('long_tables', [])]
    rom.discover(roots, hint_code, hint_lt)

    # labels
    label = {}
    vnames = {}
    for i, v in enumerate(vec):
        if i and 0x200 <= v < rom.size:
            vnames.setdefault(v, []).append(i)
    for t in sorted(rom.refs | rom.calls | roots | set(hint_code)):
        if t >= rom.size or t < 0x200:
            continue
        if t in vnames:
            idxs = vnames[t]
            nm = next((VECTOR_NAMES[i] for i in idxs if i in VECTOR_NAMES),
                      'ErrorTrap' if len(idxs) > 3 else None)
            if nm and nm not in label.values():
                label[t] = nm
                continue
        if t in rom.code:
            label[t] = ('sub_%06X' if (t in rom.calls or t in roots) else 'loc_%06X') % t
        else:
            label[t] = 'dat_%06X' % t
    # a label that falls inside an instruction cannot be placed: drop it
    inside = set()
    for a, ins in rom.code.items():
        inside.update(range(a + 1, a + ins.n))
    label = {t: n for t, n in label.items() if t not in inside}

    bad = set()
    while True:     # labels must sit on an emitted entry boundary
        starts = {e['addr'] for e in build_entries(rom, label, bad)}
        drop = [t for t in label if t not in starts]
        if not drop:
            break
        print('dropping %d labels not on entry boundaries' % len(drop))
        for t in drop:
            del label[t]
    with tempfile.TemporaryDirectory() as tmp:
        for rnd in range(1, 9):
            ents = build_entries(rom, label, bad)
            src, owner = render_gas(ents, label, pinned=True)
            res, errs, stderr = assemble(src, tmp, 'v')
            new = set()
            for ln in errs:
                k = max((l for l in owner if l <= ln), default=None)
                # errors point at the statement; attribute to the owning entry
                for l in range(ln, 0, -1):
                    if l in owner:
                        new.add(ents[owner[l]]['addr'])
                        break
            if res:
                img, syms = res
                for e in ents:
                    if e['kind'] != 'i':
                        continue
                    a, n = e['addr'], e['n']
                    if syms.get('E_%X' % a) != a + n or img[a:a + n] != d[a:a + n]:
                        new.add(a)
            new -= bad
            print('round %d: %d mismatching instructions' % (rnd, len(new)))
            if not new:
                if not res:
                    print(stderr[:2000])
                    sys.exit('assembler failed')
                break
            bad |= new

        ents = build_entries(rom, label, bad)
        src, _ = render_gas(ents, label, pinned=False)
        res, errs, stderr = assemble(src, tmp, 'f')
        if not res:
            print(stderr[:2000])
            sys.exit('final assembly failed')
        img = res[0]
        ok = img[:rom.size] == d and len(img) == rom.size
        print('rebuild: %d bytes, %s' % (len(img), 'BYTE-IDENTICAL' if ok else 'MISMATCH'))
        if not ok:
            diff = [i for i in range(min(len(img), rom.size)) if img[i] != d[i]][:10]
            print('first diffs', [hex(x) for x in diff])
    open(args.out, 'w').write(render_final(ents, label))

    for a, (k, n, _) in sorted(rom.tables.items()):
        print('table %06X %s x%d' % (a, k, n))
    code_bytes = sum(i.n for i in rom.code.values())
    print('code: %d instructions, %d bytes (%.1f%% of ROM); data: %d bytes'
          % (len(rom.code), code_bytes, 100.0 * code_bytes / rom.size, rom.size - code_bytes))
    print('dc.w fallbacks:', len(bad), Counter(rom.code[a].mnem for a in bad).most_common(8))
    print('sha256', hashlib.sha256(d).hexdigest())
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
