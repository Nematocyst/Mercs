"""Play the last Arcade round to the ending: start from a round-select state of round 7, keep the player alive, shrink the
final boss's HP ($38 of the ObjType_32 controller) so a few hits finish it, then tap START on every non-gameplay screen
and log every Game_State change with screenshots.   python3 tools/emu/ending_run.py rom.bin round7.state outdir [frames]"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
rom, state, out = sys.argv[1:4]; frames = int(sys.argv[4]) if len(sys.argv) > 4 else 60000
os.makedirs(out, exist_ok=True)
g = harness.Game(rom); g.step(3)
g.env.em.set_state(open(state, 'rb').read()); g.step(2)
random.seed(1); pad = {}; last = None; shots = []; hist = []
for fr in range(frames):
    st = g.w(0xFFFE04)
    if st != last:
        hist.append((fr, st)); print('frame %d: state %02X (stage %d, mode %d)' % (fr, st, g.w(0xFFC328), g.w(0xFFFE44)), flush=True)
        shots += [(fr + 30, st), (fr + 200, st)]; last = st
    for q in [q for q in shots if q[0] == fr]:
        g.save_png(os.path.join(out, 'state_%02X_f%d.png' % (q[1], fr)))
    g.env._ram[0xC5C2 ^ 1] = 0x40; g.env._ram[0xC5C3 ^ 1] = 0
    if st == 0x0C:
        for j in range(52):                                      # the boss controller: shrink its HP
            a = 0xE000 + j * 0x40
            if g.w(a) >> 2 == 0x32 and g.w(a + 0x38) > 2: g.env._ram[(a + 0x38) ^ 1] = 0; g.env._ram[(a + 0x39) ^ 1] = 2
        if fr % 20 == 0:
            pad = {'UP': random.random() < .5, 'LEFT': random.random() < .4, 'RIGHT': random.random() < .4, 'B': True, 'C': random.random() < .5}
        g.step(1, **pad)
    else:
        g.step(1, START=((fr % 90) < 6))
    if st in (0x04,) and len(hist) > 6: break
g.save_png(os.path.join(out, 'final.png'))
print('done: %d frames, last state %02X' % (fr, g.w(0xFFFE04)))
