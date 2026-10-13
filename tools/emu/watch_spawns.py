"""Play Mission 1 and record every object type the game itself spawns, with a crop of the screen
around it a few frames after it appears.

    python3 tools/emu/watch_spawns.py [mercs.bin] [out_dir] [frames]

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
os.makedirs(out, exist_ok=True)
g = harness.Game(rom)
for f in range(9000):
    st = g.w(0xFFFE04)
    if st == 0x0C and g.frame > 0:
        break
    g.step(1, START=((f % 100) < 6 and st not in (0, 4, 8)))
g.step(200)
ARR = [('A', 0xE000, 0x40, 52), ('B', 0xED00, 0x60, 25), ('C', 0xF660, 0x40, 22)]
prev = {}; first = {}; count = collections.Counter(); pending = []
random.seed(5); pad = {}
for fr in range(frames):
    if fr % 15 == 0:
        pad = {'UP': random.random() < 0.8, 'LEFT': random.random() < 0.3, 'RIGHT': random.random() < 0.3,
               'DOWN': random.random() < 0.1, 'B': random.random() < 0.7, 'C': random.random() < 0.4, 'A': random.random() < 0.2}
    g.step(1, **pad)
    if g.w(0xFFFE04) != 0x0C:
        break
    for nm, base, stride, n in ARR:
        for i in range(n):
            a = 0xFF0000 + base + i * stride
            t = g.w(a) >> 2
            if t and prev.get(a) != t:
                count[t] += 1
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
print('frames played %d, types seen %d (%s)' % (fr, len(first), ' '.join('%02X' % t for t in sorted(first))))
