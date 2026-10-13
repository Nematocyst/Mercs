"""Start Original mode at a chosen round using the game's own hidden round select (TCRF: Mercs (Genesis)).
Setting $FFFE58 non-zero before a new game starts routes state $08 -> $10 (the round menu); LEFT/RIGHT change the round,
START starts it.  Usage:  python3 tools/emu/round_select.py rom.bin ROUND out.state [--arcade]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness


def start_round(rom, rnd, arcade=False):
    g = harness.Game(rom); e = None
    for f in range(6000):
        g.env._ram[0xFE58 ^ 1] = 0xFF
        st = g.w(0xFFFE04)
        if st == 0x38:
            e = f if e is None else e; k = f - e
            g.step(1, DOWN=(not arcade and 150 <= k < 154), START=(190 <= k < 196)); continue
        if st == 0x10: break
        g.step(1, START=((f % 100) < 6 and st not in (0, 4, 8)))
    g.step(60)
    for _ in range(rnd - 1):
        g.step(4, RIGHT=True); g.step(20)
    g.step(4, START=True)
    for _ in range(3000):                       # wait for the mission to be playable
        g.step(1)
        if g.w(0xFFFE04) == 0x0C and g.frame > 0: break
    g.step(200)
    return g


if __name__ == '__main__':
    g = start_round(sys.argv[1], int(sys.argv[2]), '--arcade' in sys.argv)
    open(sys.argv[3], 'wb').write(g.env.em.get_state())
    print('round', sys.argv[2], 'stage', g.w(0xFFC328), 'mode', g.w(0xFFFE44), 'state %02X' % g.w(0xFFFE04))
