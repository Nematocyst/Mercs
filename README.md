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

Object handlers are labelled `ObjType_xx` after their type number (the index in `ObjectTypeTable`; a word
`Obj_Type` of `$04` is type 1). Only `ObjType_01_Player` has a verified role so far.

### Object type catalog

`tools/emu/spawn_types.py` restores a Mission 1 snapshot for each object type, places that type on a free
`Objects_A` slot next to the player, runs 45 frames and compares the frame with a run without it.
`tools/emu/objtypes.tsv` lists, per handler, the changed pixels and bounding box: 101 of the 274 handlers
draw something on their own; the rest are children, spawners, triggers or effects that need a parent.
Size classes: type `01` (player) and `44` reload the whole screen; `1B`, `A0`, `C3`, `D5`, `AB`, `F7` change
6,000-10,000 pixels (large objects); most others are 16x16 sprites. Contact sheets are not committed (they are
game art); rerun the script to regenerate them. Named so far: see below.

`tools/emu/watch_spawns.py` plays Mission 1 with an autopilot and records every type the *game* spawns
(`tools/emu/spawns_mission1.tsv`: first frame, array, position, count) with a screen crop at spawn time, which
identifies types far better than spawning them by hand. Named from it: `ObjType_03_PlayerShot` (261 spawns just
above the player), `ObjType_80_Explosion`, `ObjType_8F_Shadow`, `ObjType_82/83/8E_EnemySoldier`, plus
`ObjType_01_Player` and `ObjType_05_Crate`. Types `85`/`F5` (a rifleman pair), `08`, `12` and `4B..4E` (a scenery
group that appears together) were seen but not named.

### Starting any mission (`boot_state.py`)

`python3 tools/emu/boot_state.py mercs.bin out.bin 24 K` boots into the next-mission state with the stage
index preset (`Stage_Index` = `ram_C328` = mission number minus 1 in Arcade; state `$24` adds 1, so `K = N-2`
starts Mission N). The trampoline lives in unused ROM padding at `$FFF00`. Running `watch_spawns.py` on missions
2-7 (`tools/emu/spawns_missions2_7.tsv`; Mission 8 does not exist) added: `ObjType_32/33/34/35/B4_BossPlane`
(Mission 7 only, one giant aircraft), `ObjType_8A_EnemyTroop` (originally read as a tank; corrected, see names.json), `ObjType_97_Explosion` and `ObjType_9C/A0/A3/A6_EnemySoldier`.

### Full Arcade playthrough of the object spawns

`watch_spawns.py ... god` holds `Player_Invuln_Timer` high, so each mission plays to its end (about 13,000-19,000
frames). Over Missions 1-7 the game spawns only **74 distinct object types** of the 274 handlers
(`tools/emu/spawns_arcade_all.tsv`, with missions and counts); a second full pass found just 9 new ones, so the
list has saturated. The other ~200 handlers are not created in Arcade play: probably children made inside
handlers of those types, Original-mode content or unused. New names from this pass: `ObjType_26/38_EnterDoor`
(building entrances with an ENTER sign, Mission 5), `ObjType_98_BigTank` (Mission 6), `ObjType_A4/A5_EnemySoldier`.

### Sound interface (68k -> Z80)

`PlaySound` (`$A068`, d0 = id) is the only way the game talks to the sound driver. It takes the Z80 bus, and for ids with
bit 7 set (written as negative bytes, e.g. `moveq #-$63,d0`) stores the id in the first free slot of a 3-byte queue in Z80
RAM at `$1C0A..$1C0C` (it is dropped if all three are taken); ids with bit 7 clear jump to `$CA`, which is never used.
`Sound_StopAll` (`$A0A2`) writes d0 to `$1C10`; the Z80 main loop silences everything and clears the queue when that
byte is nonzero. On the Z80 side (`z80/driver.asm`) `Queue_Scan` runs every loop: each queue entry is looked up in a
priority table (pointer in `Priority_Table_Ptr`, `$1C02`) and moved to `Cmd_Current` (`$1C09`) when its priority is >= the
priority of the sound already playing (`Cmd_Priority`, `$1C18`). `Cmd_Dispatch` then splits the id space:

| id | handler | what |
|---|---|---|
| `$81..$B0` | `Cmd_Music_81` | music tracks (the game uses `$81 $89 $8A $8B $8C $8D $8F $91 $9B $9C $9D $9E $9F $A0 $A1`) |
| `$B1..$D3` | `Cmd_Sfx_B1` | sound effects (most used: `$B4` 19 call sites, `$BC` 17, `$BD` 15, `$B2` 12) |
| `$D4..$DF` | `Cmd_Sfx_D4` | extra effects on the second channel set (`$D1..$D3`, `$DD..$DF` are used) |
| `$E0..$F8` | table `tbl_04CB` | commands such as `$E0` (stop; 7 call sites: title, intro, options, demo, ending) |

The ids were collected from every `moveq/move.b #id,d0 ; jsr PlaySound` pair in the ROM; the sound test (`SoundTest_BGM`
`$C667`, `SoundTest_SE` `$C669`) plays them from the options screen.

### Original mode

`watch_spawns.py ... god original` chooses ORIGINAL MODE in the menu and keeps playing across screens
(`tools/emu/spawns_original_mission1.tsv`). Original Mission 1 spawns the same types as Arcade Mission 1 plus
`5D` (an invisible trigger on the beach) and `5F` (`ObjType_5F_EnemyGrenadier`). Its levels do not simply scroll upward,
so the random autopilot stalls; the `explore` driver below solves that.

### Explorer driver (`watch_spawns.py ... god original explore`)

Every 90 frames it probes nine directions from a saved state and keeps the one reaching the rarest position; it also
holds fire (B) and pulses grenades (C, which break fences and are needed for the Mission 1 boss), and after about
3,600 frames without upward progress runs `gap_sweep()`: run to the end of the wall, then walk back in short hops
trying UP until a gap (fence / sandbag line) lets the camera advance. With that it finishes Original Mission 1
(boss included), enters Mission 2, passes the tank fight and the first tent, and surveys 31 object types in Mission 1.
Handy environment options: `LOAD_STATE` (start from a savestate), `SAVE_STATE` (write one at the end), `SNAP_EVERY=n`
(screenshots) and `RAM_RANGE=from,to,step` (RAM dumps + screenshots for diffing around events).

### Hidden round select (`tools/emu/round_select.py`)

Setting `$FFFE58` non-zero before a new game starts makes state `$08` go to state `$10` (a "ROUND n" menu) instead of
the mission (the original trick: hold Down+Left+A+B+C on pad 2 at the Sega logo; see TCRF "Mercs (Genesis)").
LEFT/RIGHT change the round, START starts it. In Original mode round 1-7 are internal stages 7-13.
`round_select.py rom.bin ROUND out.state` saves a savestate at the start of any round.

### Original mode party and tents

Original mode plays a party of five mercs in a fixed order (Rifle, Burner, Launcher, Laser, Homing); tents (blinking
ENTER sign) shops hand out the next one. Findings: `Current_Merc` (`$C36E`, word = 2 x party slot) is written only by the
party screen (`sub_00BC28`) and level start; `Party_Last_Offset` (`$C3C6`) = 2 x (party size - 1); `Merc_Flags`
(`$C3B8`..) are *dead* flags per slot; `Merc_Medals` (`$C350`, BCD, copied into per-slot records at
`$C370 + 14*slot`); weapon id `$C352` (= merc x 4) drives the fire jump table at `loc_00DEA2`. The party screen and
shop panels are drawn from per-merc tables (`dat_00CA6E`, `CA2A`, `CCFA`, `CD0E`, `CD22`, `CD36`, `842E`,
`ColorList_00BFB0`) and from a contiguous five-row script at `dat_00BE6C` (0x38 bytes per slot, name pointer at +4).

### Randomized Mode (`tools/mod/`)

A separate patch (the disassembly and ROM stay untouched) that adds a menu line, ORIGINAL RANDOMIZED MERCS, which plays
Original mode with the party order shuffled each new game: random starting merc and random join order at the tents. See `tools/mod/README.md`; `tools/mod/check.py` is its
regression check and `tools/mod/mercs_randomized.ips` the prebuilt patch.

### More object types named (Original Mission 1 survey)

`ObjType_8B_EnemyShot` (hitbox + `Collision_HitPlayer`, no AI), `ObjType_B0_BossSetup`, `ObjType_B1_HarrierBody` (the
Harrier's movement/attack AI), `ObjType_B2_HarrierPodMount`, `ObjType_B3_HarrierGunPod` (spawns the shots),
`ObjType_B4_BossHealthBar` (renamed from `BossPlane`: it draws the five boxes from the boss HP), `ObjType_11_ScrollTrigger`,
`ObjType_8C/F5_Decoration`, `ObjType_FE_GrenadeThrow` and `ObjType_FF_EnemyGrenade`. Confidence per name is in
`tools/names.json`.

### Remaining untyped data

About 340 KB of the ROM is still emitted as raw `dc.b` blocks under `dat_` labels (the rest is code, typed art/maps/object data,
palettes and text). The largest: `$EFFF4` (57 KB, `$FF`-filled records), `$D1418` (40 KB), `$48B70` (37 KB, frame lists with
long pointers), `$70002` (28 KB), `$5A32C` (22 KB, high entropy: probably compressed), `$34D14` (14 KB), `$45A1C` (12 KB,
frame table), `$CF50E` (8 KB), `$DB534` (7 KB, pointer list). Their structure needs a reader per format. A scanner for
unreferenced runs of long pointers was tried and dropped: it matched word-pair data such as `08FFD8` and would have
produced misleading `dc.l` lists. Tables confirmed by hand while building the mod are typed instead: the merc portrait,
panel, bar and tent-step tables (`Merc_*`, `TentStep_*`), `Merc_RecordAddrs`, `Words_MercMaxLife` and
`Words_MessageOffsets`.
