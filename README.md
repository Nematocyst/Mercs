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
