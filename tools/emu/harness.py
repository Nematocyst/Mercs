"""Mercs test harness on the genesis_plus_gx libretro core (via the stable_retro shim)."""
import os, sys, zlib, struct
if 'GPGX_CORE' not in os.environ:      # the core ships inside the stable-retro wheel
    import importlib.util
    _spec = importlib.util.find_spec('stable_retro')
    os.environ['GPGX_CORE'] = os.path.join(os.path.dirname(_spec.origin), 'cores', 'genesis_plus_gx_libretro.so')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import stable_retro_shim as sr

BUTTONS = ['B', 'A', 'MODE', 'START', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'C', 'Y', 'X', 'Z']

class Game:
    def __init__(self, rom):
        sr.register('Mercs', rom)
        self.env = sr.make('Mercs'); self.env.reset(); self.frame = 0
    def step(self, n=1, **held):
        a = [1 if held.get(b) else 0 for b in BUTTONS]
        for _ in range(n): self.env.step(a); self.frame += 1
    def b(self, addr):          # byte at physical $FFxxxx
        return int(self.env._ram[(addr & 0xFFFF) ^ 1])
    def w(self, addr):
        return self.b(addr) << 8 | self.b(addr + 1)
    def l(self, addr):
        return self.w(addr) << 16 | self.w(addr + 2)
    def save_png(self, path):
        img = self.env.screen(); h, w, _ = img.shape
        raw = b''.join(b'\0' + img[y].tobytes() for y in range(h))
        def ch(t, d): c = struct.pack('>I', len(d)) + t + d; return c + struct.pack('>I', zlib.crc32(t + d))
        open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                               + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b''))
