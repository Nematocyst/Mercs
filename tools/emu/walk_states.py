"""Boot the ROM, tap Start on real screens and log Game_State transitions.

    python3 tools/emu/walk_states.py [mercs.bin] [out_dir]

Saves one screenshot per state, 200 frames after it is entered.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

rom = sys.argv[1] if len(sys.argv) > 1 else 'mercs.bin'
out = sys.argv[2] if len(sys.argv) > 2 else '.'
g = harness.Game(rom)
last, entered, shots, log = None, 0, set(), []
for _ in range(9000):
    st = g.w(0xFFFFFE04 & 0xFFFFFF)                   # Game_State
    if st != last:
        log.append((g.frame, st, g.w(0xFFC5A2))); last, entered = st, g.frame   # Game_NextState
    since = g.frame - entered
    if st not in shots and since == 200:
        g.save_png(os.path.join(out, 'state_%02X.png' % st)); shots.add(st)
    g.step(1, START=st not in (0, 4, 8) and since >= 240 and (since - 240) % 150 < 8)
for f, s, n in log:
    print('frame %5d  Game_State %02X  Game_NextState %02X' % (f, s, n))
