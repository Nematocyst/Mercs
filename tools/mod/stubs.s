| Randomized Mode stubs (GNU as, m68k).  Assembled at 0xFCFA0 into the unused ROM padding.
| PERM[slot] = which merc (0 Rifle,1 Burner,2 Launcher,3 Laser,4 Homing) occupies party slot `slot`.
| Everything the game keys by "who am I" goes through PERM; per-slot state (levels, dead flags) stays by slot.
	.equ PERM,  0xFFFFC3E0
	.equ MARK,  0xFFFFC3E5
	.equ CUR,   0xFFFFC36E
	.equ PLO,   0xFFFFC3C6
	.equ GMODE, 0xFFFFFE44
	.equ RMODE, 0xFFFFC3E8            | word: nonzero = "Original mode, randomized mercs" was chosen in the menu
	.equ MODEFLAGS, 0xFFFFC356
	.equ JOY1P, 0xFFFFC301
	.equ PARTYROW, 0xFFFFC3E6
	.equ PERMREC,  0xFFFFC3F0            | 5 words: stat record address of the merc in each slot
	.equ RNG,   0xFFFFC312
	.equ RANDOM_UPDATE, 0x1ABA6

	.text
	.globl	NewStart, SiteN1, SiteN2, MenuScript, MenuHilite, SiteP, SiteV, SiteW, SiteU1, SiteU2, SiteT1, SiteT2, SiteT5, Phys2_d0, Phys2_d1, Site3, Site6, SetMode, SiteR, SiteS32, SiteB64, SiteQ, SiteX, MsgPtr

| ---- make sure PERM holds a shuffle (Fisher-Yates with the game's RNG); preserves all registers
EnsurePerm:
	cmpi.b	#0xA5,(MARK).w
	beq	3f
	movem.l	%d0-%d3/%a0-%a1,-(%sp)
	lea	(PERM).w,%a0
	moveq	#0,%d0
1:	move.b	%d0,(%a0,%d0.w)
	addq.b	#1,%d0
	cmpi.b	#5,%d0
	bne	1b
	move.w	(0xFFFFC33E).w,%d0        | VBlank_Counter: depends on how long the player sat in the menus
	add.w	(0xC00008).l,%d0          | + VDP HV counter
	add.w	%d0,(RNG).w
	moveq	#7,%d1                    | warm the generator up so nearby seeds diverge
5:	jsr	(RANDOM_UPDATE).l
	dbra	%d1,5b
	moveq	#4,%d1
2:	jsr	(RANDOM_UPDATE).l
	move.w	(RNG).w,%d0
	addq.w	#1,%d1
	mulu.w	%d1,%d0                   | j = (rng * (i+1)) >> 16  -- uses the high bits, which are the good ones
	subq.w	#1,%d1
	swap	%d0
	move.b	(%a0,%d1.w),%d2
	move.b	(%a0,%d0.w),%d3
	move.b	%d3,(%a0,%d1.w)
	move.b	%d2,(%a0,%d0.w)
	subq.w	#1,%d1
	bne	2b
	moveq	#0,%d0                    | the starting merc's weapon (id*4): level start restores it from C65A
	move.b	(PERM).w,%d0
	lsl.w	#2,%d0
	move.w	%d0,(0xFFFFC65A).w
	move.w	%d0,(0xFFFFC352).w
	bset	#7,(0xFFFFC5AF).w         | ask for the weapon art to be (re)loaded
	lea	(PERMREC).w,%a1             | stat records ($C370 + 14*merc) follow the merc, not the slot
	moveq	#4,%d1
6:	moveq	#0,%d0
	move.b	(%a0,%d1.w),%d0
	mulu.w	#14,%d0
	addi.w	#0xC370,%d0
	move.w	%d1,%d2
	add.w	%d2,%d2
	move.w	%d0,(%a1,%d2.w)
	dbra	%d1,6b
	move.b	#0xA5,(MARK).w
	movem.l	(%sp)+,%d0-%d3/%a0-%a1
3:	rts

| ---- Map_dN : dN.w = slot*2  ->  dN.w = merc*2   (identity outside Original mode)
	.macro	MAP r
Map_\r:
	tst.w	(RMODE).w
	beq	9f
	bsr	EnsurePerm
	move.l	%a0,-(%sp)
	lea	(PERM).w,%a0
	lsr.w	#1,%\r
	move.b	(%a0,%\r\().w),%\r
	add.w	%\r,%\r
	movea.l	(%sp)+,%a0
9:	rts
	.endm
	MAP	d0
	MAP	d1
	MAP	d2

| move.w (CUR).w,d0 ; add.w d0,d0
Phys2_d0:
	move.w	(CUR).w,%d0
	bsr	Map_d0
	add.w	%d0,%d0
	rts
Phys2_d1:
	move.w	(CUR).w,%d1
	bsr	Map_d1
	add.w	%d1,%d1
	rts
| move.w (CUR).w,d2 ; lea (0x842E).l,a1
Site3:
	move.w	(CUR).w,%d2
	bsr	Map_d2
	lea	(0x842E).l,%a1
	rts
| move.w (CUR).w,d0 ; lea (0xCA6E).l,a1 ; add.w d0,d0
Site6:
	clr.b	(PARTYROW).w
	move.w	(CUR).w,%d0
	bsr	Map_d0
	add.w	%d0,%d0
	lea	(0xCA6E).l,%a1
	rts
| shop / carrier panels index the same tables by Obj_AnimPtr (= party slot*2)
| move.w $30(a0),d0 ; add.w d0,d0
SiteT2:
	clr.b	(PARTYROW).w
	move.w	0x30(%a0),%d0
	bsr	Map_d0
	add.w	%d0,%d0
	rts
| move.w $30(a0),d1 ; move.w (a1,d1.w),d2
SiteT1:
	clr.b	(PARTYROW).w
	move.w	0x30(%a0),%d1
	bsr	Map_d1
	move.w	(%a1,%d1.w),%d2
	rts
| move.w d1,d2 ; add.w d1,d1 ; move.l (a1,d1.w),(0xE014).w     (d2 keeps the slot for the per-slot record)
SiteT5:
	clr.b	(PARTYROW).w
	move.w	%d1,%d2
	bsr	Map_d1
	add.w	%d1,%d1
	move.l	(%a1,%d1.w),(0xFFFFE014).w
	rts

| ---- tent dialogue tables (dat_00CA82 panels / dat_00CA3E portraits) hard-code the ORIGINAL joiner per tent step.
| Remap: d1 = pointer taken from such a table, a2 = base of the matching 5-entry merc table -> d1 = that merc's
| entry for whoever really occupies the slot.  Entry 0 (Rifle) is the default "no joiner" panel: use the merc under control.
Remap:
	tst.w	(RMODE).w
	beq	9f
	bsr	EnsurePerm
	movem.l	%d0/%d2/%a0,-(%sp)
	movea.l	%a2,%a0
	moveq	#0,%d0
1:	cmp.l	(%a0)+,%d1
	beq	2f
	addq.w	#1,%d0
	cmpi.w	#5,%d0
	bne	1b
	bra	8f
2:	tst.w	%d0
	bne	3f
	move.w	(CUR).w,%d0
	lsr.w	#1,%d0
3:	lea	(PERM).w,%a0
	moveq	#0,%d2
	move.b	(%a0,%d0.w),%d2
	lsl.w	#2,%d2
	move.l	(%a2,%d2.w),%d1
8:	movem.l	(%sp)+,%d0/%d2/%a0
9:	rts
| movea.l (a1,d0.w),a6 ; bra.w sub_00BA7E        (entered with jmp)
SiteU1:
	clr.b	(PARTYROW).w
	movem.l	%d1/%a2,-(%sp)
	move.l	(%a1,%d0.w),%d1
	lea	(0xCA6E).l,%a2
	bsr	Remap
	movea.l	%d1,%a6
	movem.l	(%sp)+,%d1/%a2
	jmp	(0xBA7E).l
| move.l (a1,d0.w),Obj_FramePtr(a0) ; (rts follows in the ROM)        (entered with jmp)
SiteU2:
	movem.l	%d1/%a2,-(%sp)
	move.l	(%a1,%d0.w),%d1
	cmpa.l	#0xCA3E,%a1
	bne	1f
	lea	(0xCA2A).l,%a2
	bsr	Remap
1:	move.l	%d1,0x14(%a0)
	movem.l	(%sp)+,%d1/%a2
	rts

| RemapStrict: like Remap but entry 0 is a real merc, not a default (used where entry k is party slot k)
RemapStrict:
	tst.w	(RMODE).w
	beq	9f
	bsr	EnsurePerm
	movem.l	%d0/%d2/%a0,-(%sp)
	movea.l	%a2,%a0
	moveq	#0,%d0
1:	cmp.l	(%a0)+,%d1
	beq	3f
	addq.w	#1,%d0
	cmpi.w	#5,%d0
	bne	1b
	bra	8f
3:	lea	(PERM).w,%a0
	moveq	#0,%d2
	move.b	(%a0,%d0.w),%d2
	lsl.w	#2,%d2
	move.l	(%a2,%d2.w),%d1
8:	movem.l	(%sp)+,%d0/%d2/%a0
9:	rts
| ObjType_4F party-screen portrait: move.l (a1)+,Obj_FramePtr(a0) ; move.w (a1)+,Obj_X(a0)
SiteP:
	movem.l	%d1/%a2,-(%sp)
	move.l	(%a1)+,%d1
	lea	(0xCA2A).l,%a2
	bsr	RemapStrict
	move.l	%d1,0x14(%a0)
	movem.l	(%sp)+,%d1/%a2
	move.w	(%a1)+,0x04(%a0)
	rts
| the party-screen row loop starts here:  lea (dat_00BE6C).l,a6   -> rows are drawn from one contiguous script
SiteW:
	move.b	#1,(PARTYROW).w
	lea	(0xBE6C).l,%a6
	rts
| sub_00BB56 head (movea.l (a6)+,a1 ; movea.l (a6)+,a2 ; move.w #$C517,d1), entered with jmp, then Text_ToTiles.
| In a party-screen row script the first long this reads (row+4 of each 0x38-byte row) is that row's merc name (it lands in a1): swap in PERM's merc.
SiteV:
	movea.l	(%a6)+,%a1
	movea.l	(%a6)+,%a2
	move.w	#0xC517,%d1
	tst.b	(PARTYROW).w
	beq	9f
	tst.w	(RMODE).w
	beq	9f
	bsr	EnsurePerm
	movem.l	%d0/%d2/%a0,-(%sp)
	move.l	%a6,%d0
	subi.l	#0xBE74,%d0              | offset of the text pointer (first long read here) inside the row chain
	cmpi.l	#0x118,%d0
	bhs	8f
	divu.w	#0x38,%d0
	swap	%d0
	cmpi.w	#4,%d0                   | only the name field, not the "SPEED" label
	bne	8f
	swap	%d0                      | row number = party slot
	lea	(PERM).w,%a0
	moveq	#0,%d2
	move.b	(%a0,%d0.w),%d2
	lsl.w	#2,%d2
	lea	NameTab(%pc),%a0
	movea.l	(%a0,%d2.w),%a1
8:	movem.l	(%sp)+,%d0/%d2/%a0
9:	jmp	(0x87E2).l
NameTab:
	.long	0xBF84,0xBF8A,0xBF92,0xBF9C,0xBFA2


| ---- per-merc stat records ($C370 + 14*merc): PERMREC[slot] replaces the ROM table dat_00BE62 (slot -> record)
SiteR:                                   | replaces "lea (dat_00BE62).l,a1"
	tst.w	(RMODE).w
	beq	1f
	bsr	EnsurePerm
	lea	(PERMREC).w,%a1
	rts
1:	lea	(0xBE62).l,%a1
	rts
SiteS32:                                 | replaces "move.w Words_00C3FA(pc,d0.w),$32(a0)"  (d0 = slot*2)
	move.l	%a1,-(%sp)
	bsr	SiteR
	move.w	(%a1,%d0.w),0x32(%a0)
	movea.l	(%sp)+,%a1
	rts

| ---- party-screen row scripts (dat_00BE6C, 0x38 bytes per slot) hold that slot's ORIGINAL merc's bar maxima and record
| pointers.  RowInfo/RecDelta find the row and the record shift to the merc that really stands in that slot.
RowInfo:                                 | a6 = script pointer -> d0.w = row, or -1 outside the chain
	move.l	%a6,%d0
	subi.l	#0xBE6C,%d0
	bmi	1f
	cmpi.l	#0x118,%d0
	bhs	1f
	divu.w	#0x38,%d0
	andi.l	#0xFFFF,%d0
	rts
1:	moveq	#-1,%d0
	rts
RecDelta:                                | d0 = row -> d0.w = 14*(PERM[row]-row)
	movem.l	%d1/%a0,-(%sp)
	lea	(PERM).w,%a0
	moveq	#0,%d1
	move.b	(%a0,%d0.w),%d1
	sub.w	%d0,%d1
	muls.w	#14,%d1
	move.w	%d1,%d0
	movem.l	(%sp)+,%d1/%a0
	rts
| sub_00BB64 head: movea.l (a6)+,a1 ; movea.w (a6)+,a2 ; move.w (a6)+,d0     (bars: value pointer, maximum)
SiteB64:
	tst.b	(PARTYROW).w
	beq	5f
	tst.w	(RMODE).w
	beq	5f
	bsr	EnsurePerm
	movem.l	%d1-%d2/%a0,-(%sp)
	bsr	RowInfo
	move.w	%d0,%d1                  | d1 = row
	movea.l	(%a6)+,%a1
	movea.w	(%a6)+,%a2
	move.w	(%a6)+,%d2               | maximum written for the slot's original merc
	tst.w	%d1
	bmi	4f
	move.w	%d1,%d0
	bsr	RecDelta                 | d0 = record shift (bytes)
	adda.w	%d0,%a2                  | the right merc's record
	ext.l	%d0
	asl.l	#2,%d0                   | 14*n bytes -> 0x38*n bytes: that merc's own row
	movea.l	%a6,%a0
	subq.l	#2,%a0
	adda.l	%d0,%a0
	move.w	(%a0),%d2                | ... and its maximum
4:	move.w	%d2,%d0
	movem.l	(%sp)+,%d1-%d2/%a0
	jmp	(0xBB6A).l
5:	movea.l	(%a6)+,%a1
	movea.w	(%a6)+,%a2
	move.w	(%a6)+,%d0
	jmp	(0xBB6A).l
| sub_00BB42 tail: movea.w (a6)+,a1 ; movea.l (a6)+,a2 ; jmp (0x8A3C)       (life gauge pointer)
SiteQ:
	tst.b	(PARTYROW).w
	beq	5f
	tst.w	(RMODE).w
	beq	5f
	bsr	EnsurePerm
	movem.l	%d0-%d1/%a0,-(%sp)
	bsr	RowInfo
	move.w	%d0,%d1
	movea.w	(%a6)+,%a1
	movea.l	(%a6)+,%a2
	tst.w	%d1
	bmi	4f
	move.w	%d1,%d0
	bsr	RecDelta
	adda.w	%d0,%a1
4:	movem.l	(%sp)+,%d0-%d1/%a0
	jmp	(0x8A3C).l
5:	movea.w	(%a6)+,%a1
	movea.l	(%a6)+,%a2
	jmp	(0x8A3C).l
| sub_00BAB2 head (two record pointers, a long, a word)                            (entered with jmp, resumes at 0xBABE)
SiteX:
	tst.b	(PARTYROW).w
	beq	5f
	tst.w	(RMODE).w
	beq	5f
	bsr	EnsurePerm
	movem.l	%d2-%d3/%a0,-(%sp)
	bsr	RowInfo
	move.w	%d0,%d2
	moveq	#0,%d3
	tst.w	%d2
	bmi	3f
	move.w	%d2,%d0
	bsr	RecDelta
	move.w	%d0,%d3
3:	movea.w	(%a6)+,%a1
	adda.w	%d3,%a1
	move.w	(%a1),%d0
	movea.w	(%a6)+,%a1
	adda.w	%d3,%a1
	move.w	(%a1),%d1
	movea.l	(%a6)+,%a1
	move.w	(%a6)+,%d4
	movem.l	(%sp)+,%d2-%d3/%a0
	jmp	(0xBABE).l
5:	movea.w	(%a6)+,%a1
	move.w	(%a1),%d0
	movea.w	(%a6)+,%a1
	move.w	(%a1),%d1
	movea.l	(%a6)+,%a1
	move.w	(%a6)+,%d4
	jmp	(0xBABE).l

| ---- mode menu: a fourth line "ORIGINAL RANDOMIZED MERCS" (cursor states 0,2,4,6 = Arcade, Original, Randomized, Options)
MenuScript:                              | text script for sub_0087C6: count-1, tile base (twice), 0, routine, then (text ptr, dest) pairs
	.word	3,0x2517,0
	.long	0x87E2
	.long	0x6646
	.word	0xA418
	.long	0x6654
	.word	0xA518
	.long	MenuText
	.word	0xA618
	.long	0x6662
	.word	0xA718
MenuHilite:                              | for sub_000B54: count-1, then (dest, length-1) per line
	.word	3
	.word	0xA418,12,0xA518,12,0xA618,24,0xA718,6
MenuText:
	.ascii	"ORIGINAL RANDOMIZED MERCS"
	.byte	0
	.align	2
| replaces sub_006536 (menu START handling); entered with jmp from a bsr, so rts returns to the caller
NewStart:
	move.b	(JOY1P).w,%d0
	beq	1f
	andi.b	#0x80,%d0
	beq	9f
	st.b	(0xFFFFC604).w
	move.w	0x28(%a0),%d0            | cursor state
	clr.w	(RMODE).w
	tst.w	%d0
	bne	2f
	bclr	#2,(MODEFLAGS).w         | Arcade
	rts
2:	cmpi.w	#2,%d0
	bne	3f
	bset	#2,(MODEFLAGS).w         | Original
	rts
3:	cmpi.w	#4,%d0
	bne	9f
	bset	#2,(MODEFLAGS).w         | Original, randomized mercs
	move.w	#1,(RMODE).w
9:	rts
1:	addq.l	#4,%sp                   | no button: skip the cursor movement too (as the original does)
	rts
| next game state for the chosen line (replaces the pc-relative word tables Words_0064F0 / Words_0064F6)
SiteN1:
	move.l	%a1,-(%sp)
	lea	NextTab(%pc),%a1
	move.w	(%a1,%d0.w),(0xFFFFC5A2).w
	movea.l	(%sp)+,%a1
	rts
SiteN2:                                  | round-select variant
	move.l	%a1,-(%sp)
	lea	NextTab2(%pc),%a1
	move.w	(%a1,%d0.w),(0xFFFFC5A2).w
	movea.l	(%sp)+,%a1
	rts
NextTab:
	.word	0x28,0x48,0x48,0x1C
NextTab2:
	.word	0x10,0x10,0x10,0x1C

| replaces the tail of the game-mode setter: move.w d0,(GMODE).w ; rts   (entered with jmp)
SetMode:
	move.w	%d0,(GMODE).w
	clr.b	(MARK).w                 | new game choice -> reshuffle on first use
	rts

| replaces "lea (dat_042B5E).l,a1" in the message printer (d0 = 2*message index); d1 is free here
MsgPtr:
	tst.w	(RMODE).w
	beq	8f
	cmpi.w	#0x44,%d0
	blo	8f
	cmpi.w	#0x4A,%d0
	bhi	8f
	bsr	EnsurePerm
	move.w	(PLO).w,%d1
	lsr.w	#1,%d1
	addq.w	#1,%d1                   | slot that is about to join
	cmpi.w	#4,%d1
	bhi	8f
	lea	(PERM).w,%a1
	moveq	#0,%d0
	move.b	(%a1,%d1.w),%d0          | merc id
	beq	7f
	add.w	%d0,%d0
	addi.w	#0x42,%d0                | 0x44 + 2*(merc-1)
	bra	8f
7:	lea	RifleMsg(%pc),%a1        | nobody has a "RIFLE JOINED" line: use our own
	moveq	#0,%d0
	rts
8:	lea	(0x42B5E).l,%a1
	rts
	.align	2
RifleMsg:
	.word	2                        | offset of the string from here
	.byte	0x26                     | newline, as in "&BURNER JOINED YOUR PARTY<"
	.ascii	"RIFLE JOINED YOUR PARTY<"
	.byte	0,0
