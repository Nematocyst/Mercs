#!/usr/bin/env python3
"""Regression check for the Randomized Mode patch (needs mercs.bin, the emulator shim and the m68k binutils).

    python3 tools/mod/check.py mercs.bin

1. the patch builds and the prebuilt IPS reproduces it byte for byte;
2. Original mode: over several menu timings PERM is always a permutation, the weapon id matches PERM[0] and the
   starting merc varies;
3. Arcade mode: PERM is never generated and the mission starts normally.
"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'emu'))
import randomizer, harness

rom = open(sys.argv[1], 'rb').read()
patched, hunks, n = randomizer.build(rom)
ips = open(HERE + '/mercs_randomized.ips', 'rb').read()
assert ips == randomizer.ips(hunks), 'mercs_randomized.ips is stale: rerun randomizer.py --ips'
print('patch ok: %d bytes of code, %d hooks, IPS up to date' % (n, len(randomizer.SITES)))
path = '/tmp/_mr_check.bin'; open(path, 'wb').write(patched)


def boot(arcade, delay):
    """one emulator per process (two Game objects share the core), so run the boot in a subprocess"""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import harness\n"
        "g = harness.Game(%r); e = None\n"
        "for f in range(9000):\n"
        "    st = g.w(0xFFFE04)\n"
        "    if st == 0x0C and g.frame > 0: break\n"
        "    if st == 0x38:\n"
        "        e = f if e is None else e; k = f - e\n"
        "        g.step(1, DOWN=(not %r and 150 <= k < 154), START=(190 + %d <= k < 196 + %d)); continue\n"
        "    g.step(1, START=((f %% 100) < 6 and st not in (0, 4, 8)))\n"
        "g.step(300)\n"
        "print(g.w(0xFFFE44), g.w(0xFFFE04), g.w(0xFFC352), g.b(0xFFC3E5), *[g.b(0xFFC3E0 + i) for i in range(5)])\n"
    ) % (os.path.join(HERE, '..', 'emu'), path, arcade, delay, delay)
    out = subprocess.run([sys.executable, '-I', '-c', code], check=True, capture_output=True, text=True).stdout.split()
    return [int(x) for x in out]


starts = set()
for d in (0, 3, 7, 12, 25, 41, 77):
    mode, state, weapon, mark, *perm = boot(False, d)
    assert mode == 3 and sorted(perm) == [0, 1, 2, 3, 4], (d, mode, perm)
    assert weapon == perm[0] * 4, (d, perm, weapon)
    starts.add(perm[0])
assert len(starts) >= 3, 'starting merc barely varies: %s' % starts
print('original mode ok: starting mercs seen', sorted(starts))
mode, state, weapon, mark, *perm = boot(True, 0)
assert mode != 3 and mark == 0 and state == 0x0C
print('arcade mode ok: no shuffle, mission running (Game_Mode %d)' % mode)
