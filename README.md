# Mercs (Sega Mega Drive, 1991) - disassembly

Reverse engineering of the Mega Drive port of Capcom's *Mercs*, in asm68k syntax.
The ROM itself is not included (see `.gitignore`).

## Rebuilding / regenerating

1. Put your ROM at `mercs.bin` (1,048,576 bytes, sha256 `f56ddf66...ef379`).
2. `pip install capstone` and `apt install binutils-m68k-linux-gnu`.
3. `python3 tools/disasm.py` regenerates `mercs.asm` and checks it rebuilds byte-identical.

`tools/disasm.py` is a recursive-descent disassembler. Every instruction is assembled
on its own with GNU as and compared against the ROM; anything that does not round-trip is
emitted as `dc.w` with the original text in a comment. Extra code entry points and tables can be given in
`tools/hints.json`: `code` (entry addresses), `long_tables` (code pointers), `word_tables`
(code offsets from the table base, as used by `lea tbl(pc,d1.w),a1 / jmp (a1)`) and
`ptr_tables` (pointers to data); each table entry is `["addr", count]`. Code-pointer tables
right after a `bra`/`rts` and ascending data-pointer tables referenced by `lea` are found
automatically; word-offset code tables are hint-only because they look like data tables.

## Names

`tools/names.json` maps hex addresses to symbols (keys starting with `_` are ignored):

* addresses inside the ROM rename the generated label (`loc_`/`sub_`/`dat_`) at that address;
* RAM addresses (`FFxxxx` or `FFFFxxxx`, both forms are the same cell) name a variable. The
  short-absolute form (`(Game_State).w`) uses the name as is, the long form (`.l`) gets an `_L`
  suffix because the encoding differs. Unnamed RAM operands become `ram_XXXX` / `ram_XXXXXX`.

Hardware registers (VDP, Z80, YM2612, I/O ports) are named by the tool. All names are emitted as
`equ` lines at the top of `mercs.asm`, so a name can never change the assembled bytes.

## Emulator tests

`tools/emu/` drives the Genesis Plus GX libretro core headlessly (`pip install stable-retro`;
`stable_retro_shim.py` loads the core through ctypes, so it works on any Python). `harness.py`
offers `Game(rom)` with `step(n, START=True, ...)`, `b/w/l(addr)` RAM reads and `save_png()`.
`walk_states.py` logs the `Game_State` flow and takes a screenshot of each state. Observed so far:

| Game_State | Screen |
|---|---|
| `04` | SEGA logo |
| `08` | transition hub (`Game_NextState` holds the destination) |
| `14` | title (Mercs emblem) |
| `38` | mode select (ARCADE / ORIGINAL / OPTIONS) |
| `28` | intro story text |
| `0C` | gameplay (Mission 1) |
| `18` | attract-mode demo |

## PC trace (`tools/trace/`)

`mdtrace` runs the ROM on the Musashi 68000 core with just enough Mega Drive hardware (VDP status
and registers, Z80 bus handshake, joypads, VBlank interrupt) and logs every executed instruction.
Build and run (Musashi is a separate checkout, not part of this repo):

    git clone --depth 1 https://github.com/kstenerud/musashi ~/musashi
    MUSASHI=~/musashi tools/trace/build.sh && tools/trace/run_all.sh

* `coverage.cov` - 1 bit per ROM byte: an instruction starts here. `tools/disasm.py` loads it
  and uses every executed address as a code entry, and reports any that would fall inside a
  decoded instruction (currently 0 of 15,832).
* `dataread.map` - 1 bit per ROM byte read as data after boot (the boot-time checksum sweep of
  the whole ROM is dropped).
* An autopilot taps Start and mashes buttons; `-types N` snapshots gameplay and forces each of the
  292 object types onto a free slot for N frames. A run that jumps into data (odd PC, `$200`,
  zero word, `ori.b #imm,Dn`) is stopped and the instructions just before it are discarded.

### Finding code the game does not reach

`tools/candidates.py` lists plausible function starts (after an `rts`, >=12 clean instructions, no
junk opcodes, >=2 hardware/RAM/branch refs) in space neither the disassembler nor the trace has
touched. `mdtrace ROM 5000 out 1 -probe cands.txt` then calls each one from a gameplay snapshot
with a return sentinel on the stack and reports `returned` / `running` / `derailed`; only those
that do not derail go into `tools/hints.json` (`code`). The 35 found so far all ran cleanly.

## Data typing

* **Art / ObjData labels** - `tools/classify_data.py` finds the blobs passed (`lea (X).l,An`) to a
  routine just before it is called and records them in `hints.json` (`data_prefix`):
  `Art_XXXXXX` goes to the Huffman-style decompressor `Decompress_ToVDP` / `Decompress_ToRAM`
  (74 blobs), `ObjData_XXXXXX` to the object template / animation loaders (198 blobs).
* **Z80 sound driver** - verified against a Z80 RAM dump: ROM `$FB75A..$FC6AA` goes to Z80 `$0000`,
  `$FC6AA..$FCFA0` to Z80 `$1000` (labels `Z80_Driver`, `Z80_Driver_Data`, `Z80_Driver_End`).
* **Strings** - emitted as `dc.b 'TEXT',0` when they have word structure (space or NUL, enough
  distinct letters, plausible vowels). The assembler check assembles the equivalent bytes and each
  string is also decoded back and compared. The game font is not ASCII: `<` is `.`, `:` is `'`,
  `[` is `!`.
* The `$100..$1FF` header is emitted as typed fields.
