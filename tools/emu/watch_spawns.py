"""Play Mission 1 and record every object type the game itself spawns, with a crop of the screen
around it a few frames after it appears.

    python3 tools/emu/watch_spawns.py [mercs.bin] [out_dir] [frames] [god] [original] [explore]

`original` chooses ORIGINAL MODE in the menu and keeps playing across missions (mission map, mission complete...) until
the game returns to the logo or title; otherwise the run stops when the first mission ends.
`explore` replaces the random pad with a driver that, every 90 frames, tries nine directions from a saved state and
chooses the one reaching the least-visited camera position (for levels that are not a plain upward scroll).
`god` keeps Player_Invuln_Timer ($C5C2) high every frame, so the player is never hit and whole missions can be played.

Writes spawns.tsv (type, first frame, array, X, Y, count) and spawn_sheet_N.png contact sheets.
Objects live in VDP sprite coordinates, so the screen position is about (X-$80, Y-$80).
"""
import collections, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import harness
from PIL import Image, ImageDraw

rom = sys.argv[1] if len(sys.argv) > 1 else 'mercs.bin'
out = sys.argv[2] if len(sys.argv) > 2 else '.'
frames = int(sys.argv[3]) if len(sys.argv) > 3 else 6000
god = 'god' in sys.argv[4:]
original = 'original' in sys.argv[4:]
explore = 'explore' in sys.argv[4:]
os.makedirs(out, exist_ok=True)
g = harness.Game(rom)
entered38 = None
for f in range(9000):
    st = g.w(0xFFFE04)
    if st == 0x0C and g.frame > 0:
        break
    if original and st == 0x38:
        entered38 = f if entered38 is None else entered38
        k = f - entered38
        g.step(1, DOWN=(150 <= k < 154), START=(190 <= k < 196))     # cursor to ORIGINAL MODE, then Start
        continue
    g.step(1, START=((f % 100) < 6 and st not in (0, 4, 8)))
g.step(200)
if os.environ.get('LOAD_STATE'): g.env.em.set_state(open(os.environ['LOAD_STATE'], 'rb').read())
ARR = [('A', 0xE000, 0x40, 52), ('B', 0xED00, 0x60, 25), ('C', 0xF660, 0x40, 22)]
prev = {}; first = {}; count = collections.Counter(); pending = []
random.seed(5); pad = {}; had_play = False
visited = collections.Counter()
DIRS = [(), ('UP',), ('DOWN',), ('LEFT',), ('RIGHT',), ('UP', 'LEFT'), ('UP', 'RIGHT'), ('DOWN', 'LEFT'), ('DOWN', 'RIGHT')]


def poke_god():
    g.env._ram[0xC5C2 ^ 1] = 0x40; g.env._ram[0xC5C3 ^ 1] = 0


def pos_cell():
    sg = lambda v: v - 0x10000 if v >= 0x8000 else v
    return ((g.w(0xFFC516) >> 5), (sg(g.w(0xFFC510)) >> 5), (g.w(0xFFE004) >> 6), (g.w(0xFFE008) >> 6))


def choose():
    """Probe each direction for 40 frames from the current state and keep the one reaching the rarest position."""
    S0 = g.env.em.get_state(); best, best_score = None, -1e9
    for d in DIRS:
        g.env.em.set_state(S0)
        c0 = pos_cell(); p0 = (g.w(0xFFE004), g.w(0xFFE008), g.w(0xFFC516))
        for _ in range(40):
            poke_god(); g.step(1, B=True, **{k: True for k in d})
        c1 = pos_cell(); p1 = (g.w(0xFFE004), g.w(0xFFE008), g.w(0xFFC516))
        moved = abs(p1[0] - p0[0]) + abs(p1[1] - p0[1]) + 2 * abs(p1[2] - p0[2])
        score = -3.0 * visited[c1] + moved / 20.0 + random.random() * 0.5
        if score > best_score: best, best_score = d, score
    g.env.em.set_state(S0)
    return best
def gap_sweep():
    """Stuck against a wall: run to its left end, then walk right in short hops, trying UP after each hop (and a
    mirrored sweep), keeping the first hop where Y or the camera advances (a gap in a fence / sandbag line)."""
    for first, second in (('LEFT', 'RIGHT'), ('RIGHT', 'LEFT')):
        for _ in range(300):
            poke_god(); g.step(1, B=True, **{first: True})
        for _ in range(40):
            S0 = g.env.em.get_state(); y0 = (g.w(0xFFC516), g.w(0xFFE008))
            for _ in range(25):
                poke_god(); g.step(1, B=True, UP=True)
            if (g.w(0xFFC516), g.w(0xFFE008)) < y0:
                for _ in range(60):
                    poke_god(); g.step(1, B=True, UP=True)
                return True
            g.env.em.set_state(S0)
            for _ in range(10):
                poke_god(); g.step(1, B=True, **{second: True})
    return False


best_cam = 0xFFFF; best_at = 0; last_stt = None; shot_at = []
for fr in range(frames):
    if explore and fr % 90 == 0 and g.w(0xFFFE04) == 0x0C:
        if g.w(0xFFC516) < best_cam: best_cam, best_at = g.w(0xFFC516), fr
        elif fr - best_at > 3600:                 # no upward progress for 40 decisions
            gap_sweep(); best_at = fr
        visited[pos_cell()] += 1
        pad = {k: True for k in choose()}; pad['B'] = True
    elif explore:
        pad['C'] = (fr % 20) < 10            # grenades break fences / crates that bullets cannot
    elif fr % 15 == 0:
        pad = {'UP': random.random() < 0.8, 'LEFT': random.random() < 0.3, 'RIGHT': random.random() < 0.3,
               'DOWN': random.random() < 0.1, 'B': random.random() < 0.7, 'C': random.random() < 0.4, 'A': random.random() < 0.2}
    if god:                                   # never hit: a nonzero Player_Invuln_Timer suppresses Collision_HitPlayer
        g.env._ram[0xC5C2 ^ 1] = 0x40; g.env._ram[0xC5C3 ^ 1] = 0
    stt = g.w(0xFFFE04)
    if os.environ.get('LOG_STATES'):                  # STATE_LOG: print every Game_State change, screenshot 90 frames after it
        if stt != last_stt:
            print('frame %d: state %02X -> %02X (stage %d)' % (fr, last_stt if last_stt is not None else 0xFF, stt, g.w(0xFFC328)), flush=True)
            last_stt = stt; shot_at.append((fr + 90, stt))
        for q in [q for q in shot_at if q[0] == fr]:
            g.save_png(os.path.join(out, 'state_%02X_f%d.png' % (q[1], fr)))
    if os.environ.get('RAM_RANGE'):               # RAM_RANGE=from,to,step: dump RAM + screenshot (for diffing around events)
        lo, hi, stp = map(int, os.environ['RAM_RANGE'].split(','))
        if lo <= fr < hi and fr % stp == 0:
            open(os.path.join(out, 'ram_%05d.bin' % fr), 'wb').write(bytes(g.env._ram)); g.save_png(os.path.join(out, 'rs_%05d.png' % fr))
    if original and stt != 0x0C:                  # between missions: tap Start on every screen
        if stt in (0x04, 0x14) and had_play:
            break
        g.step(1, START=((fr % 90) < 6 and stt not in (0, 4, 8)))
        continue
    had_play = True
    g.step(1, **pad)
    if os.environ.get('SNAP_EVERY') and fr % int(os.environ['SNAP_EVERY']) == 0:
        g.save_png(os.path.join(out, 'snap_%05d.png' % fr))
    if g.w(0xFFFE04) != 0x0C and not original:
        break
    for nm, base, stride, n in ARR:
        for i in range(n):
            a = 0xFF0000 + base + i * stride
            t = g.w(a) >> 2
            if t and prev.get(a) != t:
                count[t] += 1
                if os.environ.get('SAVE_ON_TYPE') and t == int(os.environ['SAVE_ON_TYPE'], 16) and not os.path.exists(os.environ['SAVE_STATE']):
                    open(os.environ['SAVE_STATE'], 'wb').write(g.env.em.get_state())
                if t not in first:
                    first[t] = (fr, nm, g.w(a + 4), g.w(a + 8)); pending.append((fr + 3, t, g.w(a + 4), g.w(a + 8)))
            prev[a] = t
    for p in [p for p in pending if p[0] <= fr]:
        pending.remove(p)
        _, t, x, y = p
        sx, sy = x - 0x80 + 8, y - 0x80 + 8
        img = Image.fromarray(g.env.screen()[:, :240]).convert('RGB')
        box = (max(0, min(240 - 96, sx - 48)), max(0, min(224 - 96, sy - 48)))
        cell = img.crop((box[0], box[1], box[0] + 96, box[1] + 96))
        d = ImageDraw.Draw(cell); d.rectangle((0, 0, 40, 10), fill=(0, 0, 0)); d.text((2, 0), '%02X' % t, fill=(255, 255, 0))
        first[t] = first[t] + (cell,)
        cell.save(os.path.join(out, 'crop_%02X.png' % t))
g.save_png(os.path.join(out, 'final.png'))
if os.environ.get('SAVE_STATE'): open(os.environ['SAVE_STATE'], 'wb').write(g.env.em.get_state())
if explore:
    print('explorer: %d distinct positions, final camera Y=%04X HScroll=%04X, player (%04X,%04X)' % (
        len(visited), g.w(0xFFC516), g.w(0xFFC510), g.w(0xFFE004), g.w(0xFFE008)))
with open(os.path.join(out, 'spawns.tsv'), 'w') as f:
    f.write('type\tfirst_frame\tarray\tX\tY\tspawned\n')
    for t, v in sorted(first.items()):
        f.write('%02X\t%d\t%s\t%04X\t%04X\t%d\n' % (t, v[0], v[1], v[2], v[3], count[t]))
cells = [v[4] for t, v in sorted(first.items()) if len(v) > 4]
per = 60
for s in range(0, len(cells), per):
    sheet = Image.new('RGB', (96 * 10, 96 * 6))
    for i, c in enumerate(cells[s:s + per]): sheet.paste(c, ((i % 10) * 96, (i // 10) * 96))
    sheet.save(os.path.join(out, 'spawn_sheet_%d.png' % (s // per)))
print('end state %02X, mission index %d, ' % (g.w(0xFFFE04), g.w(0xFFC328)) + 'frames played %d, types seen %d (%s)' % (fr, len(first), ' '.join('%02X' % t for t in sorted(first))))
