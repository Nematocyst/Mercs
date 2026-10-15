# Mercs (Sega Mega Drive, 1991) - Disassembly Guide

A reverse-engineering report on the Mega Drive port of Capcom's *Mercs*: what the ROM contains, how the disassembly
was built and verified, how the game works, and what is still unknown. The companion files are `mercs.asm` (the
disassembly), `z80/driver.asm` (the sound driver) and `tools/` (everything that produced them).

> The ROM is a commercial binary and is not part of the repository. Put your own copy at `mercs.bin`
> (1,048,576 bytes, SHA-256 `f56ddf669afe63920bff1df792773ef4b3c4440b3f1655b1a012f17bb2eef379`).

## Contents

1. [Summary](#1-summary)
2. [The ROM at a glance](#2-the-rom-at-a-glance)
3. [Rebuilding and verifying](#3-rebuilding-and-verifying)
4. [Toolchain reference](#4-toolchain-reference)
5. [Boot, main loop and the state machine](#5-boot-main-loop-and-the-state-machine)
6. [Game modes, missions and the hidden round select](#6-game-modes-missions-and-the-hidden-round-select)
7. [Objects](#7-objects)
8. [Original mode: mercs, party and tents](#8-original-mode-mercs-party-and-tents)
9. [Video and data formats](#9-video-and-data-formats)
10. [Sound](#10-sound)
11. [RAM map](#11-ram-map)
12. [Routine catalog](#12-routine-catalog)
13. [Randomized Mode patch](#13-randomized-mode-patch)
14. [Naming conventions and confidence](#14-naming-conventions-and-confidence)
15. [Open items](#15-open-items)

---

## 1. Summary

| | |
|---|---|
| Output | `mercs.asm`: about 104,000 lines, 18,400 labels, asm68k syntax; the generated file assembles back to the **byte-identical** 1 MB ROM |
| Sound driver | `z80/driver.asm`: 1,709 Z80 instructions (pasmo syntax), also byte-identical |
| Verified code | About 95 KB of 68000 code (roughly 9% of the ROM); the rest is graphics, maps, tables and sound data |
| Ground truth | 15,832 instruction addresses actually executed on a 68000 emulator (0 of them fall inside a decoded instruction) |
| Round-trip | Every instruction is assembled alone with GNU `as` and compared against the ROM; 28 instructions that GNU `as` cannot encode identically are kept as `dc.w` |
| Names | 124 ROM labels and 52 RAM variables with a confidence note each (`tools/names.json`) |
| Game coverage | All 19 game states identified; 274 object handlers catalogued; the whole Arcade game and the Original mode up to Mission 2 played in an emulator |
| Extras | A Z80 driver disassembly, an emulator harness, a trace tool, and a separate **Randomized Mode** patch |

What the work is *not*: a complete, fully commented source. Names are evidence-based labels, not the original
programmers' names, and about 250 KB of data is still raw `dc.b` (section 15).

## 2. The ROM at a glance

### 2.1 Header and vectors

The vector table at `$000000` starts with the initial stack pointer `$FFFE00` and entry point `$000208`; every other
exception vector points at `$000200`. The header at `$100..$1FF` is emitted as typed fields:

```
SEGA MEGA DRIVE   (C)SEGA 1991.AUG
MERCS    (title fields)    serial "mk 00001119-00AJ"    regions J U E
```

The header checksum word at `$18E` is verified by the game at boot, so any patched ROM needs it recomputed
(the sum of all words from `$200` to the end).

### 2.2 Memory map

| Range | Contents |
|---|---|
| `$000000..$0001FF` | vectors and header |
| `$000200..` | code: boot, main loop at `$3EE`, game-state table at `$400`, state handlers, engine routines |
| about `$00C000..$02A000` | object handlers and their helpers (`ObjectUpdate` at `$142AE`, `ObjectTypeTable` at `$1435A`) |
| `$02D000` | `Hitbox_Table` (4,096 bytes) |
| `$030000..$0FB000` | graphics (Huffman-style compressed `Art_*`), tilemaps, palettes, object/animation data, level data, text |
| `$0FB75A..$0FCFA0` | Z80 sound driver (copied to Z80 RAM at boot): code at Z80 `$0000`, music data at `$1000` |
| `$0FCFA0..$0FDFFF` | `$FF` padding (4,192 bytes); the Randomized Mode patch uses it |
| `$0FFD30..$0FFFFF` | `$FF` padding (720 bytes) |

### 2.3 What the bytes are

Sizes measured from label to label (rough, because some data labels run into the next block):

| Class | About |
|---|---|
| `Art_*` blobs (compressed graphics, 74 consumers) | 540 KB |
| 68000 code (`loc_`/`sub_`/`ObjType_*`) | 107 KB |
| raw data still under `dat_` labels | 250 KB |
| palettes (`Pal_`, `ColorList_`) | 33 KB |
| object templates and animation scripts (`ObjData_`, 198 blobs) | 28 KB |
| RLE blobs (`Rle_`, 11) and descriptor lists (`Desc_`, 9) | 75 KB |
| tilemaps (`Map_`) | 3 KB |

## 3. Rebuilding and verifying

```
pip install capstone
apt install binutils-m68k-linux-gnu          # GNU as / ld for the m68000 target
python3 tools/disasm.py                      # regenerates mercs.asm and prints "BYTE-IDENTICAL"
```

How a disassembly that cannot be checked against the original assembler (asm68k) is still trusted:

1. **Recursive descent** from the vectors, the game-state table, jump tables and executed addresses, decoded with
   Capstone and corrected for its known mis-sizing (`sbcd`, `moveq` above `$7F`, `exg`/`abcd` suffixes).
2. **Per-instruction round-trip.** Each instruction is rendered as asm68k-style text, assembled alone with
   `m68k-linux-gnu-as -m68000 --register-prefix-optional`, and the bytes compared. Anything that does not match is emitted as
   `dc.w` with the intended text in a comment. Pinned `.org` blocks make the whole file reassemble at the exact addresses.
3. **Executed-code ground truth.** `tools/trace/mdtrace` runs the ROM on the Musashi 68000 core and logs every executed
   instruction; the disassembler uses all of them as entry points and reports any that land inside another instruction
   (currently none).
4. **Data typing** is checked too: strings are decoded back and compared, tables are only typed when every entry resolves.
5. **asm68k itself is not available here**, so the claim is "byte-identical when assembled with GNU `as` from the same text".
   Names are `equ` constants (the generator never changes a byte by renaming), and short-absolute `$FFFFxxxx` versus
   long `$FFxxxx` forms of the same RAM cell are kept distinct (the long form gets an `_L` suffix) because they encode differently.

## 4. Toolchain reference

| Tool | Purpose |
|---|---|
| `tools/disasm.py` | the disassembler / generator / verifier. Inputs: `mercs.bin`, `tools/hints.json`, `tools/names.json`, `tools/trace/coverage.cov` |
| `tools/hints.json` | extra entry points (`code`), tables (`long_tables`, `word_tables`, `ptr_tables`), typed data (`data_typed`, `data_typed_manual`), blob prefixes (`data_prefix`, `data_prefix_manual`), object field names and routines |
| `tools/names.json` | ROM label and RAM variable names plus a `_notes` entry with the evidence and confidence for each |
| `tools/classify_data.py` | labels blobs by consumer (`Art_`, `ObjData_`, `Map_`, `Rle_`, `Desc_`), finds typed tables and palettes |
| `tools/candidates.py` | finds plausible unreached functions; `mdtrace -probe` calls each one from a gameplay snapshot |
| `tools/trace/` | `mdtrace` (Musashi 68000 + minimal Mega Drive hardware): coverage and data-read bitmaps, `-watch` for RAM writes, `-types` to force each object type |
| `tools/z80/disasm.py` | Z80 driver disassembler; reassembles with `pasmo` and compares |
| `tools/emu/` | headless Genesis Plus GX harness (`harness.py`), plus the exploration scripts below |
| `tools/mod/` | the Randomized Mode patch builder and tests |

Emulator scripts (`tools/emu/`): `walk_states.py` (log and screenshot the `Game_State` flow), `boot_state.py` (patched ROM that boots
into any state/stage), `round_select.py` (start any round through the game's hidden menu), `watch_spawns.py` (autopilot that records
every object type the game spawns, with the `explore` driver, `gap_sweep()`, savestates, snapshots, RAM dumps and state logging),
`spawn_types.py` and `objtypes.tsv` (force each type on screen), `field_profile.py` and `ram_profile.py` (what a field or variable
does at runtime), `ending_run.py` (play the last Arcade round to the ending).

## 5. Boot, main loop and the state machine

After the hardware setup (Z80 reset and driver upload, VDP and I/O port init, RAM clear, the ROM checksum sweep) the code
sets `Game_State` (`$FFFE04`) and falls into the main loop at `$3EE`, which dispatches through `GameStateTable` at `$400`:
19 longs, `Game_State = 4 x (index + 1)`.

State `08` is a **hub**: handlers finish by storing a destination in `Game_NextState` (`$FFC5A2`) and setting `Game_State` to
`08`, which fades and then jumps to the destination. Forcing `Game_State` from outside does not work (handlers loop on their own
setup), which is why `boot_state.py` patches the first `move.w #4,($FE04).w` at `$3E8` into a jump to a trampoline in padding.

| State | Handler | Screen (verified in the emulator unless noted) |
|---|---|---|
| `04` | `GameState_SegaLogo` `$0468` | SEGA logo |
| `08` | `GameState_Transition` `$35C2` | hub: fade, then go to `Game_NextState` |
| `0C` | `GameState_Gameplay` `$1394` | gameplay |
| `10` | `GameState_RoundStart` `$0650` | "ROUND n" card (and the hidden round menu) |
| `14` | `GameState_Title` `$0E46` | title (Mercs emblem) |
| `18` | `GameState_Demo` `$2C8C` | attract-mode demo |
| `1C` | `GameState_Options` `$085A` | options (level, controls, rapid fire, sound test) |
| `20` | `GameState_MissionComplete` `$2D80` | "MISSION ACCOMPLISHED / BONUS POINT n PTS" |
| `24` | `GameState_NextMission` `$440E` | adds 1 to the stage and starts it |
| `28` | `GameState_Intro` `$494E` | Arcade story text |
| `2C` | `GameState_Ending_Plane` `$50FC` | Arcade ending 1: cargo plane on the tarmac |
| `30` | `GameState_Ending_Sunset` `$578C` | Arcade ending 2: jeep and motorbike at sunset (about 8,400 frames) |
| `34` | `GameState_MissionMap` `$5D48` | island map, Original mode only |
| `38` | `GameState_ModeSelect` `$6448` | ARCADE / ORIGINAL / OPTIONS menu |
| `3C` | `GameState_HighScores` `$666A` | "BEST FIGHTERS" |
| `40` | `GameState_Credits_Intro` `$6BD2` | Original ending: fade into the staff roll (observed by booting into the state) |
| `44` | `GameState_Credits_Page` `$6FDE` | one credits page; the game repeats `44 -> 08 -> 44` per page |
| `48` | `GameState_OriginalIntro` `$798C` | Original mode intro |
| `4C` | `GameState_GameOver` `$6AAE` | "TRY", then back to the logo |

Flow (the edges are the values each handler writes to `Game_NextState`):

```
04 SegaLogo -> 14 Title -> 18 Demo -> 04            14 Title -> 38 ModeSelect
38 ModeSelect -> 28 Intro (Arcade) | 48 OriginalIntro -> 34 MissionMap (Original) | 1C Options -> 38
10 RoundStart -> 0C Gameplay        0C Gameplay -> 20 MissionComplete | 4C GameOver
20 MissionComplete -> 24 NextMission -> 0C Gameplay
20 MissionComplete -> 2C Ending_Plane -> 30 Ending_Sunset -> 3C HighScores -> 04      (Arcade, played through)
40 Credits_Intro -> 44 Credits_Page -> 3C HighScores                                 (Original)
4C GameOver -> 04
```

Every hop goes through hub state `08`. The Arcade ending was played through (round 7, final boss's HP shrunk so the 200 s timer
does not expire); the Original ending was observed only by booting into state `40`.

## 6. Game modes, missions and the hidden round select

* **Modes.** `Game_Mode` (`$FFFE44`): Arcade = 1, Original = 3 (difficulty variants add to it). `Mode_Flags` (`$FFC356`) bit 2 means
  Original. The mode menu draws three lines from a text script at `$662A`.
* **Stages.** `Stage_Index` (`$FFC328`): Arcade stages 0-6 (Missions 1-7), Original stages 7-13. State `24` adds 1;
  `boot_state.py ... 24 K` with `K = N - 2` starts Mission N. Arcade has a 200-second timer that restarts the mission when it expires.
* **Hidden round select** (documented on TCRF as "hold Down+Left+A+B+C on pad 2 at the Sega logo"): setting `$FFFE58` non-zero before a
  new game makes state `08` go to state `10` (a "ROUND n" menu); LEFT/RIGHT change the round, START starts it.
  `tools/emu/round_select.py` automates it. Arcade rounds 1-7 are stages 0-6; Original rounds 1-7 are stages 7-13.
* **Object spawns.** Over the seven Arcade missions the game creates only **74 distinct object types** (a second full pass found 9 new
  ones, so the list has saturated); the other ~200 handlers are children, Original-mode content or unused.

## 7. Objects

Three arrays, run each frame by `ObjectUpdate` (`$142AE`) through `ObjectTypeTable` (`$1435A`, 292 entries; `Obj_Type` word / 4 = index):

| Array | Address | Slots |
|---|---|---|
| `Objects_A` | `$FFE000` | 52 x `$40` (the player is slot 0, type 1) |
| `Objects_B` | `$FFED00` | 25 x `$60` |
| `Objects_C` | `$FFF660` | 22 x `$40` |

Field layout (evidence: the arrays diffed after identical runs with and without input, plus the code that writes each field):

| Offset | Name | Meaning |
|---|---|---|
| `$00` w | `Obj_Type` | index x 4 into the type table; 0 = empty slot |
| `$02` b | `Obj_Flags` | handlers start `bset.b #0,2(a0) ; bne` as a first-run guard; bits steer the sprite builder |
| `$03` b | `Obj_Flags2` | mostly tested with `btst` |
| `$04` l | `Obj_X` | 16.16 fixed point |
| `$08` l | `Obj_Y` | 16.16 fixed point |
| `$0C` l / `$10` l | `Obj_VelX` / `Obj_VelY` | 16.16; applied each frame |
| `$14` l | `Obj_FramePtr` | frame definition (sprite size at `+2`) |
| `$22` b | `Obj_TileAttr` | VDP palette and priority bits |
| `$24` w | `Obj_SpriteSize` | VDP sprite-size nibble |
| `$26` w | `Obj_SortKey` | sprite list ordering |
| `$28` w | `Obj_State` | per-object state, stepped through jump tables |
| `$2C` w | `Obj_Timer` | `subq.w #1,$2C(a0)` countdowns |
| `$30` l | `Obj_AnimPtr` | animation script (`Object_LoadTemplate`, `Object_RunAnimScript`) |
| `$34` b | `Obj_AnimTimer` | set by the animation script |
| `$35` b / `$3B` b | `Obj_Direction` / `Obj_SpeedClass` | direction and speed class |

The generator rewrites `$NN(a0)` to these names only where `a0` is provably the object (the 274 handlers, `object_routines` and their
callees, 15,410 instructions), so unrelated uses of `a0` keep their numeric form.

### 7.1 Named object types

Handlers are labelled `ObjType_xx` after their type number. Roles confirmed by behaviour (confidence per name in `tools/names.json`):

| Type | Name | Role |
|---|---|---|
| `01` | `ObjType_01_Player` | the player |
| `03` | `ObjType_03_PlayerShot` | player bullet |
| `05` | `ObjType_05_Crate` | crate |
| `80`, `97` | `ObjType_80_Explosion`, `97_Explosion` | explosions |
| `8F` | `ObjType_8F_Shadow` | ground shadow |
| `82`, `83`, `8E`, `9C`, `A0`, `A3`, `A6`, `A4`, `A5` | `..._EnemySoldier` | soldiers |
| `8A` | `ObjType_8A_EnemyTroop` | troop (first read as a tank, corrected) |
| `5F` | `ObjType_5F_EnemyGrenadier` | grenadier (Original mode) |
| `26`, `38` | `..._EnterDoor` | building entrance with a blinking ENTER sign |
| `98` | `ObjType_98_BigTank` | Mission 6 tank |
| `32`, `33`, `34`, `35` | `..._BossPlane` | Mission 7 boss plane and its parts |
| `8B` | `ObjType_8B_EnemyShot` | enemy bullet (hitbox + damage, no AI) |
| `B0`..`B4` | `BossSetup`, `HarrierBody`, `HarrierPodMount`, `HarrierGunPod`, `BossHealthBar` | the Mission 1 Harrier fight |
| `11` | `ObjType_11_ScrollTrigger` | stage trigger zone |
| `FE`, `FF` | `GrenadeThrow`, `EnemyGrenade` | thrown grenade |

## 8. Original mode: mercs, party and tents

Original mode plays a party of five mercs in a fixed order: **Rifle, Burner, Launcher, Laser, Homing**. New mercs join at tents
(buildings with a blinking ENTER sign); the first tent is in Mission 2 right after the tank fight and hands out Burner.

| Merc | Max life-ups | Max power | Max speed |
|---|---|---|---|
| Rifle | 4 | 10 | 5 |
| Burner | 2 | 10 | 3 |
| Launcher | 5 | 10 | 2 |
| Laser | 4 | 4 | 4 |
| Homing | 2 | 3 | 3 |

(Life maxima are `Words_MercMaxLife` at `$842E` = 2 x life-ups; the bar maxima are the words at `+6` of the bar lists `Merc_PowerBarLists`
and `Merc_SpeedBarLists`.)

Key variables:

| Variable | Meaning |
|---|---|
| `Current_Merc` `$C36E` | word = 2 x the party slot of the controlled merc; written by the party screen (`sub_00BC28`) and at level start |
| `Party_Last_Offset` `$C3C6` | 2 x (party size - 1); joining adds 2 |
| `Merc_Flags` `$C3B8..` | one *dead* flag per slot; the party cursor skips flagged slots; the tent revive item clears them |
| `Merc_Medals` `$C350` | BCD medal count, copied into the per-slot stat records at `$C370 + 14 x slot` (power, speed, life level, medals, ...) |
| weapon id `$C352` | merc x 4; the fire routine jumps through a 5-entry table at `loc_00DEA2`; restored from `$C65A` at level start |

The party screen and tent panels are drawn from per-merc tables: `Merc_PortraitFrames` `$CA2A`, `Merc_PanelLayouts` `$CA6E`,
`Merc_LifeGaugeLists` `$CCFA`, `Merc_PowerBarLists` `$CD0E`, `Merc_LifeBarLists` `$CD22`, `Merc_SpeedBarLists` `$CD36`,
`ColorList_00BFB0` (sprite colours), the tent-step tables `TentStep_PortraitFrames` `$CA3E` and `TentStep_PanelLayouts` `$CA82`
(indexed by the tent script step), the message offset table `Words_MessageOffsets` `$42B5E`, and a contiguous five-row script
`PartyScreen_RowScripts` at `$BE6C` (`0x38` bytes per slot, hard-coding each slot's original merc: name pointer, bar maxima, record pointers).

## 9. Video and data formats

| Format | Consumer | Notes |
|---|---|---|
| Compressed graphics `Art_` | `Decompress_ToVDP` / `Decompress_ToRAM` | Huffman-style decoder using `Huffman_Table` `$FFCE00`; 74 blobs |
| RLE blobs `Rle_` | `Decompress_RLE` `$8524`, `Decompress_RLE2` `$855A` | 11 blobs (tilemaps and graphics) |
| Tilemaps `Map_` | `Write_TileMap` (`sub_00A11A/A150`) | `(d1+1) x (d2+1)` tile words to the VRAM address in `d0` |
| Palettes `Pal_` / `ColorList_` | `LoadPalette`, `LoadColorList`, `PaletteFade_Step` | `0BGR` words; copied to `Palette_Buffer` `$C700`, faded toward `Palette_Target` `$C780`, then DMAed |
| Object templates `ObjData_` | `Object_LoadTemplate`, `Object_RunAnimScript` | 198 blobs: template fields plus animation scripts |
| Descriptor lists `Desc_` | `sub_008C10/8C5C/8CC0` | multi-plane sprite / tilemap composites (9 blobs) |
| Hitboxes | `Object_GetHitbox*`, collision code | `Hitbox_Table` `$2D000`: 512 records of x1, x2, y1, y2 offsets |
| Text | `Text_ToTiles` | strings are `dc.b 'TEXT',0`; the font is not ASCII: `<` is `.`, `:` is `'`, `[` is `!`, `&` (`$26`) is a line break |

Scrolling: `Update_Scroll` writes `VScroll_A/B` (`$C522/$C568`) and `HScroll_A/B` (`$C510/$C556`) to VSRAM and the VRAM scroll table at
`$D000`; the camera is `Camera_Y` `$C516` with fraction `$C514` and velocity `$C51A`, bounded by `Camera_SetBounds`.

## 10. Sound

The 68000 uploads `z80/driver.asm` to Z80 RAM at boot. The driver is the common "coordination flag" design: music and effects are
sequences of commands in `$1000..$18F5`, a 35-entry pointer table selects them, and flag commands (`$E0` and up inside a sequence) go through
`CoordFlag_Table` (41 handlers). YM2612 access is through `YM_A0/D0/A1/D1` (`$4000..$4003`), the PSG at `$7F11`, the ROM bank register at `$6000`.

### 10.1 The 68k to Z80 interface

`PlaySound` (`$A068`, d0 = id) is the only way the game talks to the driver. It takes the Z80 bus; for ids with bit 7 set (written as
negative bytes such as `moveq #-$63,d0`) it stores the id in the first free slot of a **3-byte queue at Z80 `$1C0A..$1C0C`** and drops
it if all three are taken. `Sound_StopAll` (`$A0A2`) writes `$1C10`, which makes the Z80 silence everything and clear the queue.

On the Z80 side `Queue_Scan` runs every loop: each queued id is looked up in a priority table (pointer at `$1C02`) and moved to
`Cmd_Current` (`$1C09`) if its priority is >= the priority of what is playing (`Cmd_Priority`, `$1C18`). `Cmd_Dispatch` splits the id space:

| Id | Handler | What |
|---|---|---|
| `$81..$B0` | `Cmd_Music_81` | music tracks (used: `$81 $89 $8A $8B $8C $8D $8F $91 $9B $9C $9D $9E $9F $A0 $A1`) |
| `$B1..$D3` | `Cmd_Sfx_B1` | sound effects (most used: `$B4` 19 call sites, `$BC` 17, `$BD` 15, `$B2` 12) |
| `$D4..$DF` | `Cmd_Sfx_D4` | extra effects |
| `$E0..$F8` | `tbl_04CB` | control commands (`$E0` = stop; 7 call sites) |

The id list was collected from every `moveq/move.b #id,d0 ; jsr PlaySound` pair; the options-screen sound test (`SoundTest_BGM`
`$C667`, `SoundTest_SE` `$C669`) plays them.

## 11. RAM map

| Address | Name | Notes |
|---|---|---|
| `$FFE000` / `$FFED00` / `$FFF660` | `Objects_A/B/C` | object arrays |
| `$FFFE04` | `Game_State` | current state (index x 4 + 4) |
| `$FFC5A2` | `Game_NextState` | destination read by hub state `08` |
| `$FFFE44` | `Game_Mode` | 1 Arcade, 3 Original |
| `$FFFE82` | `Difficulty` | |
| `$FFFE42` / `$FFFE81` | `Control_Config` / `Rapid_Fire` | options |
| `$FFFE58` | (round select flag) | non-zero routes new games to the round menu |
| `$FFC300..$FFC303` | `Joy1_Held/Pressed`, `Joy2_*` | bits B `$10`, C `$20`, Right `$08`, Start `$80` |
| `$FFC312` | `RNG_Seed` | updated by `Random_Update` |
| `$FFC318` | `DMA_Trigger_Word` | the final DMA command word is written from RAM |
| `$FFC328` | `Stage_Index` | stage number (0-6 Arcade, 7-13 Original) |
| `$FFC33E` | `VBlank_Counter` | |
| `$FFC356` | `Mode_Flags` | bit 2 = Original |
| `$FFC516/514/51A` | `Camera_Y`, `_Frac`, `_VelY` | |
| `$FFC700` / `$FFC780` | `Palette_Buffer` / `Palette_Target` | |
| `$FFC5C2` | `Player_Invuln_Timer` | non-zero blocks damage; counts down each frame |
| `$FFC350..$FFC3C6` | `Merc_*`, `Current_Merc`, `Party_Last_Offset` | section 8 |
| `$FFA000` | `Decomp_Buffer` | |
| `$FFFDC0..$FFFDFF` | (the 68000 stack) | not variables |

The full list with evidence per name is in `tools/names.json` (`_notes`); `tools/emu/ram_profile.py` ranks still-unnamed variables by how they behave.

## 12. Routine catalog

| Area | Routines |
|---|---|
| Sound | `PlaySound`, `Sound_StopAll` |
| Video | `WaitVBlank`, `Update_Scroll`, `Write_TileMap`, `LoadPalette`, `LoadColorList`, `PaletteFade_Step`, `Decompress_ToVDP`, `Decompress_ToRAM`, `Decompress_RLE/RLE2`, `DMA_ToVRAM`, `Text_ToTiles`, `BuildSpriteList`, `Frame_Update` |
| Objects | `ObjectUpdate`, `Object_Alloc*`, `Object_Free`, `Object_LoadTemplate/A2`, `Object_RunAnimScript`, `Object_AnimTick`, `Anim_Set/Step/Restart`, `Object_ToScreen`, `Object_DirectionTo` |
| Collision | `Object_GetHitbox*`, `Collision_BoxTest`, `Collision_FindHit_E1C0`, `Collision_HitPlayer` |
| Camera | `Camera_Reset`, `Camera_SetBounds`, `Camera_Follow` |
| Misc | `Random_Update`, `ReadJoypads`, `InitVDP`, `InitIOPorts`, `Clear_GameVars` |

## 13. Randomized Mode patch

A separate patch (`tools/mod/`) that leaves the disassembly and the original ROM untouched. It adds a fourth line to the mode menu,
**ORIGINAL RANDOMIZED MERCS**; choosing it plays Original mode with the party order shuffled each new game: a random starting merc and
a random join order at the tents. Plain Original mode and Arcade behave exactly as before.

* **How it works.** A 5-byte permutation `PERM` (RAM `$FFC3E0`) maps party slot to merc; a flag word `RMODE` (`$FFC3E8`), set only by the new
  menu line, gates it. The shuffle is a Fisher-Yates over the game's RNG, seeded from how long the player sat in the menus plus the VDP
  HV counter. Per-slot state (dead flags, cursor) stays by slot; everything keyed by who the merc is (weapon id, sprite colours, stat caps,
  panel layouts, portraits, names, the tent dialogue, the "X JOINED YOUR PARTY" line) goes through `PERM`, and the stat records follow the merc
  (`PERMREC`, `$FFC3F0`) so each merc keeps their own upgrades and maxima.
* **Size and placement.** About 1.4 KB of new 68000 code in the `$FF` padding at `$FCFA0`, with 36 hook sites; each hook asserts the original bytes,
  so the patch only applies to the right ROM. It also fixes the header checksum.
* **Files.** `randomizer.py` (builder, `--ips`, `--invulnerable`), `stubs.s` (the new code), `check.py` (regression test), `test_start.py`,
  `mercs_randomized.ips`, and `mercs_randomized_invulnerable.ips` (a test build that holds `Player_Invuln_Timer` at `$7FFF`).
* **Verified** in the emulator and in a human playthrough: the shuffle, menu, tents (Mission 2 and rounds 4 and 6), joins, party screen, stat
  caps, deaths and the join message. Not observed: the revive item actually reviving, rounds 3/5/7 tents, real hardware.

## 14. Naming conventions and confidence

* `loc_XXXXXX` / `sub_XXXXXX` / `dat_XXXXXX`: unnamed code, routine or data at that address. Typed data uses `Art_`, `ObjData_`, `Map_`, `Rle_`, `Desc_`,
  `Pal_`, `ColorList_`, `Words_`, `Longs_` prefixes. `ObjType_xx` is the handler for object type `xx`.
* RAM: `ram_XXXX` for unnamed cells; named cells appear as `Name` (short-absolute form) and `Name_L` (long form).
* Every name in `tools/names.json` has a `_notes` entry beginning with a confidence word (`high`, `medium`, `medium-low`, `low`) and the evidence.
  Roles inferred from a screenshot alone are at most medium; a name stays `low` when it rests on a single observation.
* Corrections are part of the record: `ObjType_8A` was first read as a tank and is a troop; `GameState_Title` at `$0E46` was first the SEGA logo;
  `$FDC0..` is the stack, not sound requests, and `Game_SubState` was really `Game_NextState`.

## 15. Open items

* **About 250 KB of raw data** remains under `dat_` labels. The largest pieces: the script-like records after `$EFFF4` (up to the Z80 driver),
  `$70002` (28 KB of raw 4bpp tile data), `$5A32C` (22 KB, probably compressed; both loaded by a screen load script at `$D38`), the frame data after
  `Player_FramePtrs` (`$34F5A`, 13 KB) and `$44174` (3.8 KB). Each needs its own format reader. An automatic scanner for pointer runs was tried and
  dropped because it matched word-pair data.
* **Original ending.** States `40`/`44` were observed by booting into them, not reached by completing Original mode.
* **Object types.** About 200 of the 274 handlers are never spawned by the Arcade game; their roles are unknown or inferred.
* **Revive.** The tent's revive item deducts medals and sets up a carrier, but the revive itself was not observed.
* **asm68k.** Byte-identity is established with GNU `as`; building with asm68k itself has not been tried.
* **Harrier report.** A playtest report of the Mission 1 Harrier not attacking when the player hides in a corner was not reproduced.

---

*Sources of evidence used throughout: emulator screenshots and RAM diffs (Genesis Plus GX), the Musashi-based PC trace, GNU `as` round-trips,
`pasmo` for the Z80 driver, and a human playthrough of the Randomized Mode patch. Repository: `nematocyst/mercs`.*
