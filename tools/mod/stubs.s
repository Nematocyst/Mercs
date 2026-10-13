| Randomized Mode stubs (GNU as, m68k).  Assembled at 0xFFD40 into the unused ROM padding.
| PERM[slot] = which merc (0 Rifle,1 Burner,2 Launcher,3 Laser,4 Homing) occupies party slot `slot`.
| Everything the game keys by "who am I" goes through PERM; per-slot state (levels, dead flags) stays by slot.
	.equ PERM,  0xFFFFC3E0
	.equ MARK,  0xFFFFC3E5
	.equ CUR,   0xFFFFC36E
	.equ PLO,   0xFFFFC3C6
	.equ GMODE, 0xFFFFFE44
	.equ RNG,   0xFFFFC312
	.equ RANDOM_UPDATE, 0x1ABA6

	.text
	.globl	Phys2_d0, Phys2_d1, Site3, Site6, Site7, SetMode, MsgPtr

| ---- make sure PERM holds a shuffle (Fisher-Yates with the game's RNG); preserves all registers
EnsurePerm:
	cmpi.b	#0xA5,(MARK).w
	beq	3f
	movem.l	%d0-%d3/%a0,-(%sp)
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
	move.b	#0xA5,(MARK).w
	movem.l	(%sp)+,%d0-%d3/%a0
3:	rts

| ---- Map_dN : dN.w = slot*2  ->  dN.w = merc*2   (identity outside Original mode)
	.macro	MAP r
Map_\r:
	cmpi.w	#3,(GMODE).w
	bne	9f
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
	move.w	(CUR).w,%d0
	bsr	Map_d0
	add.w	%d0,%d0
	lea	(0xCA6E).l,%a1
	rts
| move.w (CUR).w,d1 ; lea (0xC700).w,a1
Site7:
	move.w	(CUR).w,%d1
	bsr	Map_d1
	lea	(0xFFFFC700).w,%a1
	rts

| replaces the tail of the game-mode setter: move.w d0,(GMODE).w ; rts   (entered with jmp)
SetMode:
	move.w	%d0,(GMODE).w
	clr.b	(MARK).w                 | new game choice -> reshuffle on first use
	rts

| replaces "lea (dat_042B5E).l,a1" in the message printer (d0 = 2*message index); d1 is free here
MsgPtr:
	cmpi.w	#3,(GMODE).w
	bne	8f
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
