#!/bin/sh
# Regenerates tools/trace/coverage.cov (executed instruction addresses) and dataread.map
# (ROM bytes read as data after boot) from 12 random-play runs and 8 object-type runs.
#   tools/trace/build.sh && tools/trace/run_all.sh [mercs.bin]
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROM=${1:-$HERE/../../mercs.bin}
T=$HERE/build/mdtrace
W=$(mktemp -d)
seq 1 12  | xargs -P 6 -I{} sh -c "$T '$ROM' 150000 $W/n{} {} > /dev/null"
seq 21 28 | xargs -P 8 -I{} sh -c "$T '$ROM' 5000 $W/t{} {} -types 400 > /dev/null"
python3 - "$W" "$HERE" <<'PY'
import glob, sys
w, here = sys.argv[1:3]
for ext, out in (('cov', 'coverage.cov'), ('dread', 'dataread.map')):
    acc = None
    for f in sorted(glob.glob('%s/*.%s' % (w, ext))):
        d = open(f, 'rb').read()
        acc = bytearray(d) if acc is None else bytearray(a | b for a, b in zip(acc, d))
    open('%s/%s' % (here, out), 'wb').write(acc)
    print(out, sum(bin(x).count('1') for x in acc))
PY
rm -rf "$W"
