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
| `10` | round-start card ("ROUND 1") |
| `20` | mission-complete bonus screen |
| `3C` | high scores ("BEST FIGHTERS") |
| `4C` | game over ("TRY"), then back to the SEGA logo (medium confidence) |
| `1C`, `48`, `34` | options, Original-mode intro, mission map |

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
* `-watch FFC328[-FFC32B]` (up to 8) logs every write to a RAM range with the writing instruction, value and
  Game_State, which shows who owns a variable (it showed that `$FDC0..` is the stack).
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

## Object fields

Objects live in three arrays (`Objects_A` `$E000` 52 x `$40`, `Objects_B` `$ED00` 25 x `$60`,
`Objects_C` `$F660` 22 x `$40`) and are run by `ObjectUpdate` through `ObjectTypeTable`.
`hints.json` (`object_fields`) names the offsets; `tools/disasm.py` rewrites `$NN(a0)` only where
`a0` is provably the object: the 292 handlers, `object_routines` and their callees, up to any
instruction that loads `a0` with something else (15,410 instructions). Evidence (the player is
`Objects_A[0]`, type `$04`; found by diffing the arrays after identical runs with and without input):

| Offset | Name | Evidence |
|---|---|---|
| `$00` w | `Obj_Type` | index x4 into `ObjectTypeTable`, 0 = empty |
| `$02` b | `Obj_Flags` | handlers start `bset.b #0,2(a0) ; bne` (first-run guard); bits 2/3 steer the sprite builder |
| `$03` b | `Obj_Flags2` | mostly `btst` |
| `$04` l | `Obj_X` | 16.16 fixed point; RIGHT/LEFT move it, fraction at `+$06` |
| `$08` l | `Obj_Y` | 16.16 fixed point; DOWN moves it, fraction at `+$0A` |
| `$0C` l | `Obj_VelX` | 16.16; RIGHT sets `$00013333`, LEFT `$FFFECCCD`, cleared on release; `Obj_X` changes by it each frame |
| `$10` l | `Obj_VelY` | same, DOWN sets `$00013333` |
| `$14` l | `Obj_FramePtr` | `movea.l $14(a0),a1 ; move.w 2(a1),$24(a0)` |
| `$22` b | `Obj_TileAttr` | only `$20/$40/$60/$C0`: the VDP tile-attribute bits for palette and priority; loaded from tables |
| `$24` w | `Obj_SpriteSize` | `move.w 2(a1),$24(a0)` from the frame definition; runtime values `1..7` are the VDP sprite-size nibble |
| `$26` w | `Obj_SortKey` | pushed with the object address into the sprite list |
| `$28` w | `Obj_State` | per-object state set to constants and stepped |
| `$2C` w | `Obj_Timer` | `subq.w #1,$2C(a0)` countdowns |
| `$30` l | `Obj_AnimPtr` | set by `Object_LoadTemplate`, read by `Object_RunAnimScript` |
| `$34` b | `Obj_AnimTimer` | set by the animation script |

`tools/emu/field_profile.py` prints, per field, the immediates the code writes and how the field behaves
across all active objects at runtime (distinct values, counts down/up by 1, stays put).

## RAM names (evidence)

Verified in the emulator or by decoding VDP commands (see `_notes` in `tools/names.json` for every name):

| Variable | Evidence |
|---|---|
| `Game_State` `$FE04`, `Game_NextState` `$C5A2` | state flow logged with screenshots; state `08` is a hub |
| `Joy1_Held/Pressed` `$C300/1`, `Joy2_*` `$C302/3` | `ReadJoypads`; bits B `$10`, C `$20`, Right `$08`, Start `$80` |
| `RNG_Seed` `$C312` | seeded with `$2A6D365A`; changes every gameplay frame |
| `DMA_Trigger_Word` `$C318` | final DMA command word is written from RAM |
| `VScroll_A/B` `$C522/$C568`, `HScroll_A/B` `$C510/$C556` | written by `Update_Scroll` to VSRAM (`$40000010`) and the VRAM scroll table `$D000` (`$50000003`) |
| `Game_Mode` `$FE44` | menu choice: ARCADE sets 1, ORIGINAL sets 3 |
| `Difficulty` `$FE82` | `$FE83` 2 -> 4 when LEVEL changes; boot value 2 |
| `Control_Config` `$FE42`, `Rapid_Fire` `$FE81`, `Mode_Flags` `$C356` (bit 2 = Original) | each changes when its Options row changes |
| `SoundTest_BGM/SE` `$C667/$C669` | follow the numbers on the Options screen |
| `Player1_X/Y` `$E004/$E008` | `Objects_A[0]` follows pad 1 |

`tools/emu/ram_profile.py` ranks unnamed variables and shows how each one behaves while the game runs.

## Z80 sound driver (`z80/driver.asm`)

`python3 tools/z80/disasm.py` (needs `pip install z80dis`, `apt install pasmo`) disassembles the two
segments the 68k uploads to the Z80 and checks that `pasmo` reassembles them byte-identical:

* `$0000..$0F4F` is code (1,709 instructions, about 3.4 KB): reset at `$00`, interrupt `ret` at `$38`,
  main loop at `$39`, `rst $08` waits for the YM2612, `rst $28/$30` index and load a word table.
  The command interpreter subtracts `$E0` and jumps through `CoordFlag_Table` (41 handlers): the
  usual "coordination flag" scheme of Sega sound drivers.
* `$1000..$18F5` is music data: a 35-entry pointer table to the sequences.
* Hardware: `YM_A0/D0/A1/D1` `$4000-$4003`, `Bank_Reg` `$6000`, `PSG_Port` `$7F11`; driver
  variables are `var_XXXX` equates (`$1BF0..`).
* YM2612 F-number tables (`val_0872`, `val_08FC`) are recognised as constants, not code pointers.

### Typed data (tilemaps, tables, palettes)

`tools/classify_data.py` also writes `data_typed` entries to `hints.json`; `tools/disasm.py` labels them
and emits `dc.w` / `dc.l`:

* `Map_XXXXXX` - blobs passed in `a1` to `sub_00A11A` / `sub_00A150`, the tilemap rectangle writer
  ((d1+1) x (d2+1) tile words to the VRAM address in `d0`).
* `Words_` / `Longs_` - tables read with `move.w` / `move.l table(pc,dN)`; the access size is the
  element size (extent: up to the next label).
* `Pal_` - runs of colour words found by scanning for the Genesis `0BGR` pattern (every nibble even,
  top nibble 0), at least 8 distinct words and 60% with a blue/green part. `ColorList_` is the
  same pattern with 30-60%: interleaved (CRAM offset, colour) pairs. The code copies palettes into a RAM
  buffer and DMAs them, so they are not found by CRAM commands.

`tools/emu/boot_state.py` writes a scratch ROM (checksum fixed) that boots straight into any `Game_State`,
which is how the screens of states that need long play to reach were captured.

### Game state graph

Edges are the immediates each handler writes to `Game_NextState` (gameplay, mode select and the hub
decide dynamically, so they show no edges here):

    04 SegaLogo -> 14 Title -> 18 Demo -> 04            14 Title -> 38 ModeSelect
    10 RoundStart -> 0C Gameplay | 28 Intro (Arcade) | 34 MissionMap (Original)
    48 OrigIntro -> 34 MissionMap -> 0C Gameplay
    20 MissionComplete -> 24 NextMission -> 0C Gameplay
    20 MissionComplete -> 2C Ending_A -> 30 Ending_B -> 3C HighScores -> 04
    40 Ending2_A -> 44 Ending2_B -> 3C HighScores
    4C GameOver -> 04          1C Options -> 38 ModeSelect

The `Ending*` names are medium-low confidence: they rest on the graph, not on a verified screen.

## Main routines (named from behaviour; confidence per name in `tools/names.json`)

| Area | Routines |
|---|---|
| Sound | `PlaySound` (queues d0 in the Z80 mailbox at `$1C0A`, 148 calls) |
| Video | `WaitVBlank`, `Update_Scroll`, `Write_TileMap`, `LoadPalette`, `LoadColorList`, `PaletteFade_Step`, `Decompress_ToVDP/ToRAM` (Huffman), `Decompress_RLE`, `BuildSpriteList`, `Frame_Update` |
| Objects | `ObjectUpdate`, `Object_AllocC*/AllocA*`, `Object_Free`, `Object_LoadTemplate/A2`, `Object_RunAnimScript`, `Object_AnimTick`, `Anim_Set/Step/Restart`, `Object_ToScreen`, `Object_DirectionTo` |
| Collision | `Object_GetHitbox*`, `Collision_BoxTest`, `Collision_FindHit_E1C0`, `Collision_HitPlayer` |
| Misc | `Random_Update`, `ReadJoypads`, `InitVDP`, `InitIOPorts`, `Camera_Reset`, `Clear_GameVars` |
