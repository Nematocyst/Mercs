#!/usr/bin/env python3
"""List plausible function starts in ROM that neither static analysis nor the trace has reached.

A candidate follows an rts/rte in untouched space, decodes cleanly for >=12 instructions without
junk opcodes and has >=2 hardware/RAM/branch references.   python3 tools/candidates.py > cands.txt
"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disasm

here = os.path.dirname(os.path.abspath(__file__))
r = disasm.Rom(os.path.join(here, '..', 'mercs.bin'))
vec = struct.unpack('>64I', r.d[:256])
h = json.load(open(os.path.join(here, 'hints.json')))
hint = []
for key, kind in (('long_tables', 'l'), ('word_tables', 'w'), ('ptr_tables', 'p')):
    hint += [(int(a, 16), kind, n) for a, n in h.get(key, [])]
cov = open(os.path.join(here, 'trace', 'coverage.cov'), 'rb').read()
dr = open(os.path.join(here, 'trace', 'dataread.map'), 'rb').read()
ex = [a for a in range(0x200, r.size, 2) if cov[a >> 3] >> (a & 7) & 1]
extra = [int(x, 16) for x in h.get('code', [])]
r.discover({v for v in vec[1:] if 0x200 <= v < r.size}, ex + extra, hint)
code = bytearray(r.size)
for a, i in r.code.items():
    code[a:a + i.n] = b'\1' * i.n
touched = lambda i: code[i] or (dr[i >> 3] >> (i & 7) & 1)
i = 0x200
while True:
    i = r.d.find(b'\x4e\x75', i)
    if i < 0:
        break
    a = i + 2
    if i % 2 == 0 and a < r.size - 8 and not touched(a) and not touched(a + 8) and r.plausible(a, limit=64):
        n, x, ref, junk = 0, a, 0, 0
        while n < 64:
            ins = r.decode(x)
            if not ins:
                break
            junk += r.is_junk(ins)
            ref += sum(1 for p in ins.parts if isinstance(p, tuple) and
                       (p[0] == 'br' or p[0] == 'abs' and p[1] >= 0xA00000))
            n += 1; x += ins.n
            if ins.mnem.split('.')[0] in disasm.ENDS:
                break
        if n >= 12 and not junk and ref >= 2:
            print('%X' % a)
    i += 2
