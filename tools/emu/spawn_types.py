"""Spawn every object type next to the player and make labelled contact sheets of what appears.

    python3 tools/emu/spawn_types.py [mercs.bin] [out_dir]

A gameplay snapshot is restored for each type; one free slot of Objects_A gets the type word and a
position near the player, 45 frames run, and the frame is compared with a run without the spawn.
Only pixels that changed are kept bright, so even small sprites stand out.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import harness
from PIL import Image, ImageDraw

rom = sys.argv[1] if len(sys.argv) > 1 else 'mercs.bin'
out = sys.argv[2] if len(sys.argv) > 2 else '.'
os.makedirs(out, exist_ok=True)
g = harness.Game(rom)
for f in range(9000):
    st = g.w(0xFFFE04)
    if st == 0x0C and g.frame > 0:
        break
    g.step(1, START=((f % 100) < 6 and st not in (0, 4, 8)))
g.step(350)
S = g.env.em.get_state()
SLOT = 0xE000 + 0x40 * 45


def setb(addr, v): g.env._ram[(addr & 0xFFFF) ^ 1] = v & 0xFF
def setw(addr, v): setb(addr, v >> 8); setb(addr + 1, v)


def run(t):
    g.env.em.set_state(S)
    if t is not None:
        px, py = g.w(0xFFE004), g.w(0xFFE008)
        for k in range(0x40): setb(SLOT + k, 0)
        setw(SLOT, t * 4); setw(SLOT + 4, px + 48); setw(SLOT + 8, py - 70)
    g.step(45)
    return g.env.screen()[:, :240].astype(int)


base = run(None)
tbl = [struct.unpack('>I', open(rom, 'rb').read()[0x1435A + 4 * j:0x1435E + 4 * j])[0] for j in range(292)]
seen, order = {}, []
for t in range(1, 292):
    if tbl[t] in seen or t == 73:            # shared handlers and the data slot
        continue
    seen[tbl[t]] = t; order.append(t)
cells, catalog = [], []
for t in order:
    img = run(t)
    diff = (np.abs(img - base).sum(axis=2) > 30)
    cell = (base * 0.25).astype(np.uint8)
    cell[diff] = img[diff].astype(np.uint8)
    im = Image.fromarray(cell).resize((120, 112), Image.NEAREST)
    ImageDraw.Draw(im).rectangle((0, 0, 30, 10), fill=(0, 0, 0))
    ImageDraw.Draw(im).text((2, 0), '%02X' % t, fill=(255, 255, 0))
    ys, xs = np.nonzero(diff)
    bbox = (int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)) if len(xs) else (0, 0)
    cells.append((t, im, int(diff.sum())))
    catalog.append((t, tbl[t], int(diff.sum()), bbox))
per = 40
for s in range(0, len(cells), per):
    sheet = Image.new('RGB', (120 * 8, 112 * 5))
    for i, (t, im, n) in enumerate(cells[s:s + per]):
        sheet.paste(im, ((i % 8) * 120, (i // 8) * 112))
    sheet.save(os.path.join(out, 'sheet_%d.png' % (s // per)))
with open(os.path.join(out, 'objtypes.tsv'), 'w') as f:
    f.write('type\thandler\tchanged_px\tbbox_w\tbbox_h\n')
    for t, h, n, (w, hh) in catalog:
        f.write('%02X\t%06X\t%d\t%d\t%d\n' % (t, h, n, w, hh))
print('types shown:', len(cells), 'sheets:', (len(cells) + per - 1) // per)
print('no visible change:', ' '.join('%02X' % t for t, _, n in cells if n == 0))
