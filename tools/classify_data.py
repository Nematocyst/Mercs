#!/usr/bin/env python3
"""Type ROM data by what consumes it and record the result in tools/hints.json ("data_prefix").

A data blob is whatever a routine receives through lea (X).l,An just before it is called.
Consumers and their meaning are listed in CONSUMERS (found by reading the routines):

  Art      sub_00A218 / sub_00A22A   Huffman-style decompressor, to VDP / to a RAM buffer
  ObjData  sub_01ADB0 / 01ADF6 / 01AF0E / 01AF1A   object template and animation-script loaders
  Map      sub_00A11A / 00A150   tilemap rectangle writer: a1 = (d1+1)*(d2+1) words
  Words/Longs  tables read with move.w / move.l table(pc,dN)
  Pal / ColorList   runs of Genesis colour words (0BGR, every nibble even), found by scanning;
           ColorList = interleaved (CRAM offset, colour) pairs

Typed entries are written to hints.json "data_typed": [prefix, size, addr, length].

    python3 tools/classify_data.py        (rewrites the data_prefix entry of hints.json)
"""
import collections, json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disasm

CONSUMERS = {'Art': (0xA218, 0xA22A), 'ObjData': (0x1ADB0, 0x1ADF6, 0x1AF0E, 0x1AF1A), 'Map': (0xA11A, 0xA150),
             'Rle': (0x8524, 0x855A), 'Desc': (0x8C10, 0x8C5C, 0x8CC0)}   # Decompress_RLE/RLE2 inputs; descriptor lists for the sub_008C10 family

here = os.path.dirname(os.path.abspath(__file__))
r = disasm.Rom(os.path.join(here, '..', 'mercs.bin'))
vec = struct.unpack('>64I', r.d[:256])
hp = os.path.join(here, 'hints.json')
h = json.load(open(hp))
hint = []
for key, kind in (('long_tables', 'l'), ('word_tables', 'w'), ('ptr_tables', 'p')):
    hint += [(int(a, 16), kind, n) for a, n in h.get(key, [])]
cov = open(os.path.join(here, 'trace', 'coverage.cov'), 'rb').read()
ex = [a for a in range(0x200, r.size, 2) if cov[a >> 3] >> (a & 7) & 1]
r.discover({v for v in vec[1:] if 0x200 <= v < r.size}, ex + [int(x, 16) for x in h.get('code', [])], hint)

order = sorted(r.code)
pos = {a: i for i, a in enumerate(order)}
which = {a: p for p, rs in CONSUMERS.items() for a in rs}
found = collections.defaultdict(set)
for a in order:
    ins = r.code[a]
    if ins.mnem.split('.')[0] not in ('jsr', 'bsr', 'bra', 'jmp'):
        continue
    tg = [p[1] for p in ins.parts if isinstance(p, tuple) and p[0] in ('abs', 'br', 'pc')]
    if not tg or tg[0] not in which:
        continue
    k = pos[a]
    for j in range(k - 1, max(k - 9, -1), -1):          # straight-line instructions before the call
        pa, pi = order[j], r.code[order[j]]
        if pa + pi.n != order[j + 1]:
            break
        if pi.mnem == 'lea':
            ps = [p for p in pi.parts if isinstance(p, tuple)]
            if ps and ps[0][0] in ('abs', 'pc') and ps[0][1] < r.size and ps[0][1] not in r.code:
                found[which[tg[0]]].add(ps[0][1])
typed = []
for prefix in ('Map',):
    for a in sorted(found[prefix] - found['Art']):
        typed.append([prefix, 'w', '%X' % a, 0])
# tables read with an indexed pc-relative load: the access size is the element size
tab = {}
for a, ins in r.code.items():
    base, _, sz = ins.mnem.partition('.')
    if base in ('move', 'add', 'sub', 'cmp') and sz in ('w', 'l') and r.indexed_pc(ins):
        for p_ in ins.parts:
            if isinstance(p_, tuple) and p_[0] == 'pc' and p_[1] < r.size and p_[1] not in r.code:
                tab.setdefault(p_[1], sz)
for a, sz in sorted(tab.items()):
    if a % 2 == 0 and not any(a == int(t[2], 16) for t in typed):
        typed.append(['Words' if sz == 'w' else 'Longs', sz, '%X' % a, 0])
# colour words: 0BGR with bits 15-12 and the low bit of every nibble clear
code_bytes = bytearray(r.size)
for a, i in r.code.items():
    code_bytes[a:a + i.n] = b'\1' * i.n
isc = lambda w: (w & 0xF111) == 0
a = 0x200
while a < r.size - 16:
    run = 0
    while a + 2 * run + 1 < r.size and not code_bytes[a + 2 * run] and isc(r.d[a + 2 * run] << 8 | r.d[a + 2 * run + 1]):
        run += 1
    ws = [r.d[a + 2 * k] << 8 | r.d[a + 2 * k + 1] for k in range(run)]
    nz = [w for w in ws if w]
    nib = {(w >> sh) & 15 for w in nz for sh in (0, 4, 8)} - {0}
    if run >= 8 and len(set(nz)) >= 8 and len(nib) >= 4 and len(nz) >= run // 2:
        frac = sum(1 for w in nz if w >= 0x100) / len(nz)      # real colours have a blue/green part
        kind = 'Pal' if frac >= 0.6 else 'ColorList' if frac >= 0.3 else None   # lists of (CRAM offset, colour)
        if kind:
            typed.append([kind, 'w', '%X' % a, 2 * run])
        a += 2 * run
    else:
        a += 2
manual = h.get('data_typed_manual', [])                  # hand-confirmed entries survive a re-run
typed += [m for m in manual if not any(m[2] == t[2] for t in typed)]
h['data_typed'] = typed
print('typed:', {k: sum(1 for t in typed if t[0] == k) for k in ('Map', 'Words', 'Longs', 'Pal', 'ColorList')})
out = {}
for prefix in CONSUMERS:                                  # Art wins when a blob is used both ways
    out[prefix] = sorted('%X' % a for a in found[prefix] - (found['Art'] if prefix != 'Art' else set()))
    out[prefix] = sorted(set(out[prefix]) | {x for x in h.get('data_prefix_manual', {}).get(prefix, [])})   # hand-confirmed blobs (the lea is too far from the call)
h['data_prefix'] = out
json.dump(h, open(hp, 'w'), indent=2)
print({k: len(v) for k, v in out.items()})
