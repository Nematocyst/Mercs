#!/usr/bin/env python3
"""Randomized Mode patch for Mercs (Mega Drive).  The original ROM is only ever read.

    python3 tools/mod/randomizer.py mercs.bin mercs_randomized.bin [--ips out.ips]

In Original mode (Game_Mode == 3) the party order is shuffled each new game: you start as a random one of
Rifle/Burner/Launcher/Laser/Homing and the tents hand out the rest in a random order.  Arcade mode is untouched.
The new code lives in the unused ROM padding at $FCFA0 (stubs.s); the game is hooked at the sites below.
"""
import os, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_ADDR = 0xFCFA0          # 4192 bytes of $FF padding after the Z80 driver (never read: dataread.map)
AS = 'm68k-linux-gnu-as'; LD = 'm68k-linux-gnu-ld'; NM = 'm68k-linux-gnu-nm'; OC = 'm68k-linux-gnu-objcopy'


def assemble():
    t = tempfile.mkdtemp()
    run = lambda *a: subprocess.run(a, check=True, capture_output=True, text=True).stdout
    run(AS, '-m68000', '--register-prefix-optional', '-o', t + '/s.o', HERE + '/stubs.s')
    run(LD, '-Ttext=0x%X' % CODE_ADDR, '-o', t + '/s.elf', t + '/s.o')
    run(OC, '-O', 'binary', t + '/s.elf', t + '/s.bin')
    syms = {}
    for line in run(NM, t + '/s.elf').splitlines():
        f = line.split()
        if len(f) == 3: syms[f[2]] = int(f[0], 16)
    return open(t + '/s.bin', 'rb').read(), syms


def jsr(a): return bytes.fromhex('4eb9') + struct.pack('>I', a)
def jmp(a): return bytes.fromhex('4ef9') + struct.pack('>I', a)
NOP = bytes.fromhex('4e71')

# (address, expected original bytes, replacement builder)
SITES = [
    (0x7E86, '3038c36ed040', lambda s: jsr(s['Phys2_d0'])),                       # level cap table CD36[merc]
    (0x8074, '3238c36ed241', lambda s: jsr(s['Phys2_d1'])),                       # table CD0E[merc]
    (0x80DE, '3438c36e43f90000842e', lambda s: jsr(s['Site3']) + NOP * 2),        # word table 842E[merc]
    (0xB65A, '3038c36ee348', lambda s: jsr(s['Phys2_d0'])),                       # weapon id -> C352
    (0xB730, '3038c36ed040', lambda s: jsr(s['Phys2_d0'])),                       # sprite colours ColorList[merc]
    (0xB86E, '3038c36e43f90000ca6ed040', lambda s: jsr(s['Site6']) + NOP * 3),    # panel layout CA6E[merc]
    (0xCA18, '60000006', lambda s: bytes.fromhex('d0406006')),                    # bra loc_00CA20 -> add.w d0,d0 ; bra.b +6
    (0xCA1C, '3038c36ed040', lambda s: jsr(s['Phys2_d0'])),                       # portrait frame CA2A[merc]
    (0xC4D6, '3228003034311000', lambda s: jsr(s['SiteT1']) + NOP),                # shop: stat cap word table
    (0xC544, '30280030d040', lambda s: jsr(s['SiteT2'])),                         # shop: CD0E
    (0xC578, '30280030d040', lambda s: jsr(s['SiteT2'])),                         # shop: CD22
    (0xC5A4, '30280030d040', lambda s: jsr(s['SiteT2'])),                         # shop: CD36
    (0xC658, '3401d24121f11000e014', lambda s: jsr(s['SiteT5']) + NOP),           # carrier panel portrait + layout
    (0xB93A, '2c7100006000013e', lambda s: jmp(s['SiteU1']) + NOP),                # join dialogue: header panel
    (0xCA22, '217100000014', lambda s: jmp(s['SiteU2'])),                         # join dialogue: portrait
    (0xBCD6, '215900143159' + '0004', lambda s: jsr(s['SiteP']) + NOP),             # party screen portraits
    (0xBA1C, '4df90000be6c', lambda s: jsr(s['SiteW'])),                          # party screen rows start
    (0xBB56, '225e245e323cc517', lambda s: jmp(s['SiteV']) + NOP),               # party screen names
    (0xB6EE, '43f90000be62', lambda s: jsr(s['SiteR'])),                          # stat records follow the merc (5 lookups)
    (0xBA56, '43f90000be62', lambda s: jsr(s['SiteR'])),
    (0xBD56, '43f90000be62', lambda s: jsr(s['SiteR'])),
    (0xC662, '43f90000be62', lambda s: jsr(s['SiteR'])),
    (0xC980, '43f90000be62', lambda s: jsr(s['SiteR'])),
    (0xC3EC, '317b000c0032', lambda s: jsr(s['SiteS32'])),                        # shop: record of the carrier
    (0xBB64, '225e345e301e', lambda s: jmp(s['SiteB64'])),                        # party screen bars: record + maximum
    (0xBB4C, '325e245e4ef900008a3c', lambda s: jmp(s['SiteQ']) + NOP * 2),       # party screen life gauge
    (0xBAB2, '325e3011325e3211225e381e', lambda s: jmp(s['SiteX']) + NOP * 3),    # party screen record pointers
    (0x6536, '10 38 c3 01 67 54'.replace(' ', ''), lambda s: jmp(s['NewStart'])),     # menu START handling (Randomized entry)
    (0x657A, '0004', lambda s: bytes.fromhex('0006')),                            # cursor wrap: last state 4 -> 6
    (0x6584, '0006', lambda s: bytes.fromhex('0008')),                            # cursor wrap: states < 8
    (0x659E, '43f9000065a8', lambda s: bytes.fromhex('43f9') + struct.pack('>I', s['MenuHilite'])),   # highlight table
    (0x65C6, '4df90000662a', lambda s: bytes.fromhex('4df9') + struct.pack('>I', s['MenuScript'])),   # menu text script
    (0x64D6, '31fb0018c5a2', lambda s: jsr(s['SiteN1'])),                         # next state per menu line
    (0x64E2, '31fb0012c5a2', lambda s: jsr(s['SiteN2'])),
    (0x6512, '31c0fe444e75', lambda s: jmp(s['SetMode'])),                        # mode chosen -> reshuffle
    (0x8954, '43f900042b5e', lambda s: jsr(s['MsgPtr'])),                         # "X JOINED YOUR PARTY" text
]


def build(rom):
    code, syms = assemble()
    d = bytearray(rom)
    assert len(code) <= 4192, 'code does not fit the padding'
    assert len(set(d[CODE_ADDR:CODE_ADDR + len(code)])) == 1 and d[CODE_ADDR] == 0xFF, 'ROM padding at $%X is not free' % CODE_ADDR
    d[CODE_ADDR:CODE_ADDR + len(code)] = code
    hunks = [(CODE_ADDR, code)]
    for addr, old, rep in SITES:
        old = bytes.fromhex(old); new = rep(syms)
        assert bytes(d[addr:addr + len(old)]) == old, 'unexpected bytes at $%X: %s' % (addr, d[addr:addr + len(old)].hex())
        new += NOP * ((len(old) - len(new)) // 2)
        assert len(new) == len(old), 'size mismatch at $%X' % addr
        d[addr:addr + len(old)] = new; hunks.append((addr, new))
    ck = sum(struct.unpack('>%dH' % ((len(d) - 0x200) // 2), bytes(d[0x200:]))) & 0xFFFF
    d[0x18E:0x190] = struct.pack('>H', ck); hunks.append((0x18E, struct.pack('>H', ck)))
    return bytes(d), hunks, len(code)


def ips(hunks):
    out = b'PATCH'
    for a, b in sorted(hunks):
        out += struct.pack('>I', a)[1:] + struct.pack('>H', len(b)) + b
    return out + b'EOF'


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    rom = open(args[0], 'rb').read()
    out, hunks, n = build(rom)
    open(args[1], 'wb').write(out)
    if '--ips' in sys.argv:
        open(sys.argv[sys.argv.index('--ips') + 1], 'wb').write(ips(hunks))
    print('wrote %s: %d bytes of new code at $%X, %d hooks' % (args[1], n, CODE_ADDR, len(SITES)))
