#!/bin/sh
# Builds tools/trace/build/mdtrace against a Musashi checkout.
#   git clone --depth 1 https://github.com/kstenerud/musashi ~/musashi
#   MUSASHI=~/musashi tools/trace/build.sh
set -e
MUSASHI=${MUSASHI:-$HOME/musashi}
HERE=$(cd "$(dirname "$0")" && pwd)
B=$HERE/build
mkdir -p "$B"
gcc -O2 -o "$B/m68kmake" "$MUSASHI/m68kmake.c"
(cd "$B" && ./m68kmake "$B" "$MUSASHI/m68k_in.c" >/dev/null)
gcc -O2 -w -I"$MUSASHI" -I"$B" -I"$HERE" -DMUSASHI_CNF='"mdconf.h"' \
    -o "$B/mdtrace" "$HERE/mdtrace.c" "$MUSASHI/m68kcpu.c" "$B/m68kops.c" \
    "$MUSASHI/m68kdasm.c" "$MUSASHI/softfloat/softfloat.c" -lm
echo "built $B/mdtrace"
