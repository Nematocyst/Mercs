"""Write a scratch copy of the ROM that boots straight into a given Game_State.

    python3 tools/emu/boot_state.py mercs.bin out.bin 3C

The game sets its first state with `move.w #$4,($FE04).w` at $3E8 just before the main loop; the
copy patches that immediate and fixes the header checksum (the boot code verifies the ROM).
Use the copy only in the emulator/trace harness; it is never written into the repo.
"""
import struct, sys

rom, out, state = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
d = bytearray(open(rom, 'rb').read())
assert d[0x3E8:0x3EE] == bytes.fromhex('31fc0004fe04'), 'unexpected ROM'
d[0x3EA:0x3EC] = struct.pack('>H', state)
ck = sum(struct.unpack('>%dH' % ((len(d) - 0x200) // 2), bytes(d[0x200:]))) & 0xFFFF
d[0x18E:0x190] = struct.pack('>H', ck)
open(out, 'wb').write(d)
print('wrote %s: boots into Game_State %02X, checksum %04X' % (out, state, ck))
