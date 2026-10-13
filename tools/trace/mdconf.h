/* Musashi configuration for mdtrace: instruction hook, separate data/code reads, int-ack handler. */
#include "m68kconf.h"

int  md_int_ack(int level);
void md_instr_hook(unsigned int pc);

#undef M68K_SEPARATE_READS
#define M68K_SEPARATE_READS M68K_OPT_ON
#undef M68K_EMULATE_INT_ACK
#define M68K_EMULATE_INT_ACK M68K_OPT_SPECIFY_HANDLER
#undef M68K_INT_ACK_CALLBACK
#define M68K_INT_ACK_CALLBACK(A) md_int_ack(A)
#undef M68K_INSTRUCTION_HOOK
#define M68K_INSTRUCTION_HOOK M68K_OPT_SPECIFY_HANDLER
#undef M68K_INSTRUCTION_CALLBACK
#define M68K_INSTRUCTION_CALLBACK(pc) md_instr_hook(pc)

/* the Mega Drive CPU is a plain 68000 */
#undef M68K_EMULATE_010
#define M68K_EMULATE_010 M68K_OPT_OFF
#undef M68K_EMULATE_EC020
#define M68K_EMULATE_EC020 M68K_OPT_OFF
#undef M68K_EMULATE_020
#define M68K_EMULATE_020 M68K_OPT_OFF
#undef M68K_EMULATE_030
#define M68K_EMULATE_030 M68K_OPT_OFF
#undef M68K_EMULATE_040
#define M68K_EMULATE_040 M68K_OPT_OFF
#undef M68K_EMULATE_PMMU
#define M68K_EMULATE_PMMU M68K_OPT_OFF
