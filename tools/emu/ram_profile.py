"""Profile the most used unnamed RAM variables: static use plus runtime behaviour.

    python3 tools/emu/ram_profile.py [rom] [asm] [count] [skip]

Runs the game from boot through the menus into Mission 1 (random input once in gameplay) and
samples every tracked variable each frame.
"""
import collections, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

rom = sys.argv[1] if len(sys.argv) > 1 else 'mercs.bin'
asm = sys.argv[2] if len(sys.argv) > 2 else 'mercs.asm'
count = int(sys.argv[3]) if len(sys.argv) > 3 else 30
skip = int(sys.argv[4]) if len(sys.argv) > 4 else 0

equ = {}
for l in open(asm):
    m = re.match(r'(ram_[0-9A-F]+)\tequ\t\$([0-9A-F]+)', l)
    if m: equ[m.group(1)] = int(m.group(2), 16)
use, imm, ops = collections.Counter(), collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
size = collections.defaultdict(collections.Counter)
for l in open(asm):
    m = re.match(r'\t([a-z]+)(?:\.([bwl]))?\t(.*)', l)
    if not m: continue
    mn, sz, rest = m.groups()
    for nm in re.findall(r'\((ram_[0-9A-F]+)\)\.[wl]', rest):
        if nm not in equ: continue
        use[nm] += 1; ops[nm][mn] += 1
        if sz: size[nm][sz] += 1
        im = re.match(r'#(\$[0-9A-F]+|-?\d+),\(%s\)' % nm, rest)
        if im and mn in ('move', 'ori', 'andi', 'cmpi', 'addi', 'subi'): imm[nm]['%s%s' % ('=' if mn == 'move' else mn + ' ', im.group(1))] += 1
names = [n for n, _ in use.most_common()][skip:skip + count]

g = harness.Game(rom)
stat = {n: dict(v=collections.Counter(), dec=0, inc=0, oth=0, same=0, states=collections.Counter()) for n in names}
prev = {}
random.seed(3); mask = {}
def rd(n):
    sz = size[n].most_common(1)[0][0] if size[n] else 'w'
    a = equ[n]; return (g.b(a) if sz == 'b' else g.w(a) if sz == 'w' else g.l(a)), sz
for fr in range(7000):
    st = g.w(0xFFFE04)
    if st == 0x0C and fr % 10 == 0:
        mask = {k: random.random() < 0.5 for k in ('UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A')}
    start = st != 0x0C and st not in (0, 4, 8) and (fr % 120) < 6
    g.step(1, START=start, **(mask if st == 0x0C else {}))
    for n in names:
        v, sz = rd(n); s = stat[n]; s['v'][v] += 1
        if n in prev:
            d = v - prev[n]
            if d == 0: s['same'] += 1
            else:
                s['states'][st] += 1
                if d == -1: s['dec'] += 1
                elif d == 1: s['inc'] += 1
                else: s['oth'] += 1
        prev[n] = v
print('%-9s %4s %-3s %-22s %-26s %5s %4s %4s %4s  changes in states / common values' % ('var', 'uses', 'sz', 'ops', 'imm written', 'dist', 'dec', 'inc', 'oth'))
for n in names:
    s = stat[n]; tot = s['same'] + s['dec'] + s['inc'] + s['oth'] or 1
    top = lambda c, k: ' '.join('%s×%d' % (x, y) for x, y in c.most_common(k))
    print('%-9s %4d %-3s %-22s %-26s %5d %3d%% %3d%% %3d%%  %s | %s' % (
        n, use[n], (size[n].most_common(1) or [('?',)])[0][0], top(ops[n], 3), top(imm[n], 3), len(s['v']),
        100 * s['dec'] // tot, 100 * s['inc'] // tot, 100 * s['oth'] // tot,
        ','.join('%02X' % k for k, _ in s['states'].most_common(3)), ' '.join('%X×%d' % kv for kv in s['v'].most_common(4))))
