"""Write a scratch copy of the ROM that boots straight into a given Game_State (and stage).

    python3 tools/emu/boot_state.py mercs.bin out.bin 24 [STAGE]

The game sets its first state with `move.w #$4,($FE04).w` at $3E8 just before the main loop. That
6-byte instruction is replaced by a jump to a trampoline in the unused ROM padding at $FFF00, which sets
Game_State, optionally the stage index (ram_C328) and jumps back to the main loop at $3EE. The header
checksum is fixed (the boot code verifies the ROM). Use the copy only in the emulator/trace harness;
it is never written into the repo.
"""
import struct, sys

rom, out, state = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
stage = int(sys.argv[4]) if len(sys.argv) > 4 else None
d = bytearray(open(rom, 'rb').read())
assert d[0x3E8:0x3EE] == bytes.fromhex('31fc0004fe04'), 'unexpected ROM'
TRAMP = 0xFFF00
assert len(set(d[TRAMP:TRAMP + 32])) == 1, 'padding at $FFF00 is not unused'
code = b''
if stage is not None:
    code += bytes.fromhex('31fc') + struct.pack('>H', stage) + bytes.fromhex('c328')      # move.w #stage,($C328).w
code += bytes.fromhex('31fc') + struct.pack('>H', state) + bytes.fromhex('fe04')           # move.w #state,($FE04).w
code += bytes.fromhex('4ef9') + struct.pack('>I', 0x3EE)                                   # jmp $3EE
d[TRAMP:TRAMP + len(code)] = code
d[0x3E8:0x3EE] = bytes.fromhex('4ef9') + struct.pack('>I', TRAMP)                          # jmp trampoline
ck = sum(struct.unpack('>%dH' % ((len(d) - 0x200) // 2), bytes(d[0x200:]))) & 0xFFFF
d[0x18E:0x190] = struct.pack('>H', ck)
open(out, 'wb').write(d)
print('wrote %s: boots into Game_State %02X%s, checksum %04X' % (out, state, '' if stage is None else ' stage %d' % stage, ck))
