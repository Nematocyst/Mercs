#!/usr/bin/env python3
"""Type ROM data by what consumes it and record the result in tools/hints.json ("data_prefix").

A data blob is whatever a routine receives through lea (X).l,An just before it is called.
Consumers and their meaning are listed in CONSUMERS (found by reading the routines):

  Art      sub_00A218 / sub_00A22A   Huffman-style decompressor, to VDP / to a RAM buffer
  ObjData  sub_01ADB0 / 01ADF6 / 01AF0E / 01AF1A   object template and animation-script loaders

    python3 tools/classify_data.py        (rewrites the data_prefix entry of hints.json)
"""
import collections, json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disasm

CONSUMERS = {'Art': (0xA218, 0xA22A), 'ObjData': (0x1ADB0, 0x1ADF6, 0x1AF0E, 0x1AF1A)}

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
out = {}
for prefix in CONSUMERS:                                  # Art wins when a blob is used both ways
    out[prefix] = sorted('%X' % a for a in found[prefix] - (found['Art'] if prefix != 'Art' else set()))
h['data_prefix'] = out
json.dump(h, open(hp, 'w'), indent=2)
print({k: len(v) for k, v in out.items()})
