"""Profile object fields: static writes/compares from mercs.asm plus runtime behaviour.

    python3 tools/emu/field_profile.py [mercs.bin] [mercs.asm] [offsets...]

Runtime: plays Mission 1 with random input, samples every active object every 3 frames and
records, per field, distinct values and how often it goes down by 1 (timer), up by 1 (counter),
changes by other amounts or stays put.
"""
import collections, os, re, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

rom = sys.argv[1] if len(sys.argv) > 1 else 'mercs.bin'
asm = sys.argv[2] if len(sys.argv) > 2 else 'mercs.asm'
offs = [int(x, 16) for x in sys.argv[3:]] or [0x10, 0x0C, 0x16, 0x18, 0x19, 0x1A, 0x20, 0x22, 0x24, 0x29, 0x2A, 0x2E, 0x2F, 0x35, 0x36, 0x38, 0x3E, 0x44]

# static: immediates written and compared
wr, cmp_, ops = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
for l in open(asm):
    m = re.match(r'\t([a-z]+)(?:\.([bwl]))?\t(.*)', l)
    if not m:
        continue
    mn, sz, rest = m.groups()
    for mm in re.finditer(r'(?<![\w$-])\$([0-9A-F]+)\(a0\)', rest):
        o = int(mm.group(1), 16)
        ops[o]['%s.%s' % (mn, sz or '')] += 1
        im = re.match(r'#(\$[0-9A-F]+|-?\d+),', rest)
        if im and rest.endswith('(a0)'):
            (wr if mn in ('move', 'ori', 'andi', 'eori') else cmp_)[o][im.group(1)] += 1

# runtime
g = harness.Game(rom)
for f in range(9000):
    st = g.w(0xFFFE04)
    if st == 0x0C and g.frame > 0:
        break
    g.step(1, START=((f % 100) < 6 and st not in (0, 4, 8)))
g.step(300)
ARR = [(0xE000, 0x40, 52), (0xED00, 0x60, 25), (0xF660, 0x40, 22)]
prev = {}
stat = {o: dict(vals=collections.Counter(), dec1=0, inc1=0, other=0, same=0) for o in offs}
random.seed(1)
mask = 0
for fr in range(3000):
    if fr % 10 == 0:
        mask = {k: random.random() < 0.5 for k in ('UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A')}
    g.step(3, **mask)
    for base, stride, n in ARR:
        for i in range(n):
            a = 0xFF0000 + base + i * stride
            if g.w(a) == 0:
                prev.pop(a, None)
                continue
            cur = bytes(g.b(a + k) for k in range(stride))
            if a in prev:
                for o in offs:
                    if o >= len(cur):
                        continue                  # field only exists in the larger objects
                    s = stat[o]
                    v1, v0 = cur[o], prev[a][o]
                    s['vals'][v1] += 1
                    if v1 == v0: s['same'] += 1
                    elif (v1 - v0) & 255 == 255: s['dec1'] += 1
                    elif (v1 - v0) & 255 == 1: s['inc1'] += 1
                    else: s['other'] += 1
            prev[a] = cur
print('off  static ops                       written imms                      runtime: distinct  same%  -1%  +1%  other%   common values')
for o in offs:
    s = stat[o]; tot = s['same'] + s['dec1'] + s['inc1'] + s['other'] or 1
    top = lambda c, k=5: ' '.join('%s×%d' % (x, n) for x, n in c.most_common(k))
    print('+%02X  %-30s %-34s %5d  %3d%% %3d%% %3d%% %3d%%   %s' % (
        o, top(ops[o], 3), top(wr[o], 4), len(s['vals']), 100 * s['same'] // tot, 100 * s['dec1'] // tot,
        100 * s['inc1'] // tot, 100 * s['other'] // tot, ' '.join('%02X×%d' % kv for kv in s['vals'].most_common(5))))
