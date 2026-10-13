/* mdtrace - headless Mega Drive CPU harness for Mercs.
 *
 * Runs the ROM on the Musashi 68000 core with just enough hardware (VDP status/registers,
 * Z80 bus handshake, joypads, VBlank interrupt) to run the game logic, and records
 *   <prefix>.cov    1 bit per ROM byte: an instruction starts here
 *   <prefix>.dread  1 bit per ROM byte: read as data
 *   <prefix>.ram    work RAM at the end of the run
 *
 *   mdtrace rom.bin frames out_prefix [seed] [-v]
 *
 * An autopilot taps Start on menus and mashes random buttons so that more code runs.
 * Game_State is the word at $FFFE04 and Game_NextState the word at $FFC5A2.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "m68k.h"

#define ROMSZ 0x100000
static uint8_t rom[ROMSZ], ram[0x10000], zram[0x10000];
static uint8_t cov[ROMSZ / 8], dread[ROMSZ / 8];
static int vblank, vint_pending, busreq, vdp_reg1, cmd_pending;
static uint8_t io_data[3] = {0x7F, 0x7F, 0x7F}, io_ctrl[3];
static unsigned buttons[2];                         /* UP=1 DOWN=2 LEFT=4 RIGHT=8 B=10 C=20 A=40 START=80 */
static unsigned long frame_instr, total_instr;

/* Derailment: the game jumped into data. Detected by an odd PC, execution outside ROM, the error
 * trap at $200, a zero opcode word, or "ori.b #imm,Dn" (pointer tables like 0003xxxx decode as
 * these) - except the genuine "ori.b #$40,d0" display-enable idiom. The instructions recorded just
 * before the detection are forgotten, as they may already have been garbage. */
#define RING 32
static uint8_t runcov[ROMSZ / 8];
static uint8_t *curcov = cov;                      /* where the hook records: cov, or runcov in the type pass */
static unsigned ring[RING]; static int ring_n, derail, sentinel_hit; static unsigned derail_pc;
#define SENTINEL 0x0FFFFEu

static int bad_pc(unsigned pc) {
    if ((pc & 1) || pc >= ROMSZ || pc == 0x200) return 1;
    if (!rom[pc] && !rom[pc + 1] && !rom[pc + 2] && !rom[pc + 3]) return 1;
    unsigned w = rom[pc] << 8 | rom[pc + 1];
    return (w & 0xFFF8) == 0 && !(w == 0 && rom[pc + 2] == 0x00 && rom[pc + 3] == 0x40);
}
static void forget_tail(uint8_t *map) {
    int n = ring_n < RING ? ring_n : RING;
    for (int i = 1; i <= n; i++) { unsigned a = ring[(ring_n - i) % RING]; map[a >> 3] &= ~(1 << (a & 7)); }
    ring_n = 0;
}

void md_instr_hook(unsigned pc) {
    pc &= 0xFFFFFF;
    frame_instr++; total_instr++;
    if (derail) return;
    if (pc == SENTINEL) { sentinel_hit = 1; m68k_end_timeslice(); return; }
    if (bad_pc(pc)) { derail = 1; derail_pc = pc; m68k_end_timeslice(); return; }
    if (!(curcov[pc >> 3] >> (pc & 7) & 1)) { curcov[pc >> 3] |= 1 << (pc & 7); ring[ring_n++ % RING] = pc; }
}
int md_int_ack(int level) { (void)level; m68k_set_irq(0); return M68K_INT_ACK_AUTOVECTOR; }

static unsigned pad_read(int p) {
    unsigned b = buttons[p], th = (io_ctrl[p] & 0x40) ? (io_data[p] >> 6) & 1 : 1, v;
    if (th) v = 0x40 | (~(((b >> 5) & 1) << 5 | ((b >> 4) & 1) << 4 | ((b >> 3) & 1) << 3 |
                          ((b >> 2) & 1) << 2 | ((b >> 1) & 1) << 1 | (b & 1))) & 0x3F;
    else    v = 0x00 | (~(((b >> 7) & 1) << 5 | ((b >> 6) & 1) << 4 |
                          ((b >> 1) & 1) << 1 | (b & 1))) & 0x33;
    return v;
}

static unsigned rd8(unsigned a, int data) {
    a &= 0xFFFFFF;
    if (a < 0x400000) {
        if (a >= ROMSZ) return 0;
        if (data) dread[a >> 3] |= 1 << (a & 7);
        return rom[a];
    }
    if (a >= 0xA00000 && a < 0xA10000) {
        if (a >= 0xA04000 && a < 0xA04004) return 0;           /* YM2612 status */
        return zram[a & 0xFFFF];
    }
    if (a >= 0xA10000 && a < 0xA10020) {
        switch ((a & 0x1F) >> 1) {
            case 0: return 0xA0;                                /* overseas, NTSC */
            case 1: return pad_read(0); case 2: return pad_read(1); case 3: return 0x7F;
            case 4: return io_ctrl[0]; case 5: return io_ctrl[1]; case 6: return io_ctrl[2];
        }
        return 0;
    }
    if (a == 0xA11100) return !busreq;                          /* bit 0 = 0 once the bus is granted */
    if (a >= 0xC00000 && a < 0xC00020) {
        unsigned off = a & 0x1F;
        if (off == 4 || off == 5) { unsigned s = 0x3600 | (vblank ? 8 : 0) | (vint_pending ? 0x80 : 0);
                                    vint_pending = 0; cmd_pending = 0; return off == 4 ? s >> 8 : s & 0xFF; }
        if (off == 8 || off == 9) { unsigned v = (frame_instr / 115) & 0xFF; return off == 8 ? v : (frame_instr & 0xFF); }
        return 0;
    }
    if (a >= 0xE00000) return ram[a & 0xFFFF];
    return 0;
}

static void wr8(unsigned a, unsigned v) {
    a &= 0xFFFFFF; v &= 0xFF;
    if (a >= 0xE00000) { ram[a & 0xFFFF] = v; return; }
    if (a >= 0xA00000 && a < 0xA10000) { zram[a & 0xFFFF] = v; return; }
    if (a >= 0xA10000 && a < 0xA10020) {
        int r = (a & 0x1F) >> 1;
        if (r >= 1 && r <= 3) io_data[r - 1] = v; else if (r >= 4 && r <= 6) io_ctrl[r - 4] = v;
        return;
    }
    if (a == 0xA11100) busreq = v & 1;
}

static void vdp_ctrl_word(unsigned w) {
    if (cmd_pending) { cmd_pending = 0; return; }
    if ((w & 0xC000) == 0x8000) { if (((w >> 8) & 0x1F) == 1) vdp_reg1 = w & 0xFF; return; }
    cmd_pending = 1;
}

unsigned m68k_read_memory_8(unsigned a)  { return rd8(a, 1); }
unsigned m68k_read_memory_16(unsigned a) {
    if ((a & 0xFFFFFF) == 0xA11100) return busreq ? 0 : 0x100;
    return rd8(a, 1) << 8 | rd8(a + 1, 1);
}
unsigned m68k_read_memory_32(unsigned a) { return m68k_read_memory_16(a) << 16 | m68k_read_memory_16(a + 2); }
unsigned m68k_read_immediate_16(unsigned a) { return rd8(a, 0) << 8 | rd8(a + 1, 0); }
unsigned m68k_read_immediate_32(unsigned a) { return m68k_read_immediate_16(a) << 16 | m68k_read_immediate_16(a + 2); }
unsigned m68k_read_pcrelative_8(unsigned a)  { return rd8(a, 1); }
unsigned m68k_read_pcrelative_16(unsigned a) { return rd8(a, 1) << 8 | rd8(a + 1, 1); }
unsigned m68k_read_pcrelative_32(unsigned a) { return m68k_read_pcrelative_16(a) << 16 | m68k_read_pcrelative_16(a + 2); }
unsigned m68k_read_disassembler_8(unsigned a)  { return rd8(a, 0); }
unsigned m68k_read_disassembler_16(unsigned a) { return m68k_read_immediate_16(a); }
unsigned m68k_read_disassembler_32(unsigned a) { return m68k_read_immediate_32(a); }

void m68k_write_memory_8(unsigned a, unsigned v) { wr8(a, v); }
void m68k_write_memory_16(unsigned a, unsigned v) {
    unsigned x = a & 0xFFFFFF;
    if (x == 0xA11100) { busreq = (v >> 8) & 1; return; }
    if (x >= 0xC00000 && x < 0xC00020 && ((x & 0x1F) == 4 || (x & 0x1F) == 6)) { vdp_ctrl_word(v & 0xFFFF); return; }
    wr8(a, v >> 8); wr8(a + 1, v);
}
void m68k_write_memory_32(unsigned a, unsigned v) {
    unsigned x = a & 0xFFFFFF;
    if (x >= 0xC00000 && x < 0xC00020 && (x & 0x1F) == 4) { vdp_ctrl_word(v >> 16); vdp_ctrl_word(v & 0xFFFF); return; }
    m68k_write_memory_16(a, v >> 16); m68k_write_memory_16(a + 2, v & 0xFFFF);
}

static unsigned rng_state = 1; static int derailed_types, dread_reset;
static unsigned rnd(void) { rng_state = rng_state * 1664525u + 1013904223u; return rng_state >> 8; }
static unsigned ramw(unsigned a) { return ram[(a ^ 1) & 0xFFFF] | 0, ram[a & 0xFFFF] << 8 | ram[(a + 1) & 0xFFFF]; }

int main(int argc, char **argv) {
    if (argc < 4) { fprintf(stderr, "usage: %s rom frames out_prefix [seed] [-v]\n", argv[0]); return 2; }
    FILE *f = fopen(argv[1], "rb"); if (!f || fread(rom, 1, ROMSZ, f) != ROMSZ) { fprintf(stderr, "bad rom\n"); return 2; } fclose(f);
    long frames = atol(argv[2]); const char *pfx = argv[3];
    rng_state = argc > 4 ? (unsigned)atol(argv[4]) | 1 : 1;
    int verbose = 0, type_frames = 0, type_max = 291; const char *probe_file = NULL;
    for (int i = 5; i < argc; i++) {
        if (!strcmp(argv[i], "-v")) verbose = 1;
        else if (!strcmp(argv[i], "-types") && i + 1 < argc) type_frames = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-maxtype") && i + 1 < argc) type_max = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-probe") && i + 1 < argc) { probe_file = argv[++i]; type_frames = 1; }
    }
    m68k_init(); m68k_set_cpu_type(M68K_CPU_TYPE_68000); m68k_pulse_reset();
    unsigned last_state = 0xFFFF, entered = 0, mask = 0;
    static unsigned char ctx[65536], ctx0[65536];           /* CPU context for the type pass */
    static uint8_t ram0[0x10000], zram0[0x10000];
    int have_snap = 0, snap_busreq = 0, snap_reg1 = 0;
    unsigned snap_rng = 0;
    for (long fr = 0; fr < frames; fr++) {
        unsigned st = ramw(0xFE04);
        if (st != last_state) { if (verbose) { long nd = 0; for (unsigned i = 0; i < sizeof dread; i++) for (int b = 0; b < 8; b++) nd += (dread[i] >> b) & 1;
                                    printf("frame %6ld  Game_State %02X  Game_NextState %02X  rom bytes read as data so far %ld\n", fr, st, ramw(0xC5A2), nd); }
                                last_state = st; entered = fr; }
        if (st == 0x04 && !dread_reset) { memset(dread, 0, sizeof dread); dread_reset = 1; }   /* drop the boot-time ROM checksum sweep */
        unsigned since = fr - entered, period = st == 0x0C ? 900 : 150;
        if (type_frames && !have_snap && st == 0x0C && since >= 400) {      /* snapshot inside gameplay */
            m68k_get_context(ctx0); memcpy(ram0, ram, sizeof ram); memcpy(zram0, zram, sizeof zram);
            snap_busreq = busreq; snap_reg1 = vdp_reg1; snap_rng = rng_state; have_snap = 1;
            if (verbose) printf("snapshot at frame %ld\n", fr);
            break;
        }
        if (fr % 12 == 0) mask = (rnd() & 0xFF) & ~0x80u;                 /* random pad, no Start */
        buttons[0] = mask | ((st > 8 && !(type_frames && st == 0x0C) && since >= 60 && (since - 60) % period < 8) ? 0x80 : 0);
        buttons[1] = 0;
        frame_instr = 0; vblank = 0;
        m68k_execute(100000);
        if (!derail) { vblank = 1; vint_pending = 1;
            if (vdp_reg1 & 0x20) m68k_set_irq(6);
            m68k_execute(27841); }
        if (derail) {
            forget_tail(cov);
            printf("derailed at frame %ld (Game_State %02X) pc=%06X\n", fr, ramw(0xFE04), derail_pc);
            break;
        }
    }
    if (probe_file && have_snap) {
        /* call each address as a subroutine with a return sentinel; report how it behaves */
        FILE *pf = fopen(probe_file, "r"); unsigned addr;
        while (pf && fscanf(pf, "%x", &addr) == 1) {
            m68k_set_context(ctx0); memcpy(ram, ram0, sizeof ram); memcpy(zram, zram0, sizeof zram);
            busreq = snap_busreq; vdp_reg1 = snap_reg1; derail = 0; sentinel_hit = 0; ring_n = 0;
            memset(runcov, 0, sizeof runcov); curcov = runcov;
            unsigned sp = m68k_get_reg(NULL, M68K_REG_SP) - 4;
            m68k_set_reg(M68K_REG_SP, sp); m68k_write_memory_32(sp, SENTINEL);
            m68k_set_reg(M68K_REG_PC, addr);
            frame_instr = 0; unsigned long i0 = total_instr;
            m68k_execute(200000);
            long nd = 0; for (unsigned i = 0; i < sizeof runcov; i++) for (int b = 0; b < 8; b++) nd += (runcov[i] >> b) & 1;
            printf("%06X %s instructions=%lu distinct=%ld\n", addr,
                   sentinel_hit ? "returned" : derail ? "derailed" : "running", total_instr - i0, nd);
            curcov = cov;
        }
        have_snap = 0;                       /* skip the type pass */
    }
    if (type_frames && have_snap) {
        /* force every object type onto a free slot of the first object array, run it, restore */
        for (int t = 1; t <= type_max; t++) {
            m68k_set_context(ctx0); memcpy(ram, ram0, sizeof ram); memcpy(zram, zram0, sizeof zram);
            busreq = snap_busreq; vdp_reg1 = snap_reg1; rng_state = snap_rng ^ (unsigned)t * 2654435761u;
            unsigned slot = 0xE000 + 0x40 * 45;
            memset(&ram[slot], 0, 0x40);
            ram[(slot + 0) & 0xFFFF] = (t * 4) >> 8; ram[(slot + 1) & 0xFFFF] = (t * 4) & 0xFF;
            memset(runcov, 0, sizeof runcov); ring_n = 0; derail = 0; curcov = runcov;
            for (int k = 0; k < type_frames && !derail; k++) {
                if (k % 12 == 0) mask = (rnd() & 0xFF) & ~0x80u;
                buttons[0] = mask; buttons[1] = 0;
                frame_instr = 0; vblank = 0; m68k_execute(100000);
                if (derail) break;
                vblank = 1; vint_pending = 1; if (vdp_reg1 & 0x20) m68k_set_irq(6); m68k_execute(27841);
            }
            curcov = cov;
            if (derail) {                         /* forget what ran just before the jump into data */
                forget_tail(runcov);
                derailed_types++;
                if (verbose) printf("type %d derailed\n", t);
            }
            for (unsigned i = 0; i < sizeof cov; i++) cov[i] |= runcov[i];
        }
    }
    char name[512];
    snprintf(name, sizeof name, "%s.cov", pfx);   f = fopen(name, "wb"); fwrite(cov, 1, sizeof cov, f);     fclose(f);
    snprintf(name, sizeof name, "%s.dread", pfx); f = fopen(name, "wb"); fwrite(dread, 1, sizeof dread, f); fclose(f);
    snprintf(name, sizeof name, "%s.zram", pfx);  f = fopen(name, "wb"); fwrite(zram, 1, sizeof zram, f);   fclose(f);
    snprintf(name, sizeof name, "%s.ram", pfx);   f = fopen(name, "wb"); fwrite(ram, 1, sizeof ram, f);     fclose(f);
    long n = 0; for (unsigned i = 0; i < sizeof cov; i++) for (int b = 0; b < 8; b++) n += (cov[i] >> b) & 1;
    if (type_frames) printf("types derailed: %d of %d\n", derailed_types, type_max);
    printf("frames %ld  instructions %lu  distinct instruction addresses %ld  final Game_State %02X\n",
           frames, total_instr, n, ramw(0xFE04));
    return 0;
}
