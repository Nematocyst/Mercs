"""Boot a (patched) ROM into Original Mission 1 and report the party order / starting merc.
    [DOWNS=n] [DELAY=n] python3 tools/mod/test_start.py patched.bin [extra_wait_frames] [out.png]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'emu'))
import harness
force = None
if '--perm' in sys.argv:
    i = sys.argv.index('--perm'); force = [int(x) for x in sys.argv[i + 1].split(',')]; del sys.argv[i:i + 2]
DELAY = int(os.environ.get("DELAY", 0))
DOWNS = int(os.environ.get("DOWNS", 2))        # menu line: 0 Arcade, 1 Original, 2 Original randomized mercs
rom = sys.argv[1]; wait = int(sys.argv[2]) if len(sys.argv) > 2 else 0
g = harness.Game(rom)
g.step(wait)
e = None
for f in range(9000):
    if force and g.w(0xFFFE44) == 3:
        for i, v in enumerate(force): g.env._ram[(0xC3E0 + i) ^ 1] = v
        g.env._ram[0xC3E5 ^ 1] = 0xA5
    st = g.w(0xFFFE04)
    if st == 0x0C and g.frame > 0: break
    if st == 0x38:
        e = f if e is None else e; k = f - e
        g.step(1, DOWN=any(150 + 20 * i <= k < 154 + 20 * i for i in range(DOWNS)), START=(190 + 20 * (DOWNS - 1) + DELAY <= k < 196 + 20 * (DOWNS - 1) + DELAY)); continue
    g.step(1, START=((f % 100) < 6 and st not in (0, 4, 8)))
g.step(300)
perm = [g.b(0xFFC3E0 + i) for i in range(5)]
print('mode', g.w(0xFFFE44), 'perm', perm, 'mark %02X' % g.b(0xFFC3E5), 'CurrentMerc', g.w(0xFFC36E), 'weapon C352', g.w(0xFFC352))
if len(sys.argv) > 3: g.save_png(sys.argv[3])
if '--fire' in sys.argv:
    g.step(5, B=True, UP=True); g.step(12, B=True)
    print('after fire: C352', g.w(0xFFC352), 'objs B:', [hex(g.w(0xFFED00 + i * 0x60) >> 2) for i in range(25) if g.w(0xFFED00 + i * 0x60)])
    g.save_png(sys.argv[3].replace('.png', '_fire.png'))
