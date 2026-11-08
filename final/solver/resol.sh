#!/bin/sh
# resol.sh DATA.pl SOLUTION.csv WORKDIR [extra options for horaris.pl]
#
# Solves DATA.pl with horaris.pl + kissat, allowing as few changes as possible:
# first only the units that MUST change day/hour (bound "min"), then a few more, ... and finally no bound.
# Exit code: 0 SAT (solution written), 20 UNSAT even without a bound, 1 error.
# BOUNDS overrides the sequence, e.g.  BOUNDS="min+10" sh resol.sh ...   or   BOUNDS=300 ...
data=$1; sol=$2; work=$3; shift 3
mkdir -p "$work"
for b in ${BOUNDS:-min min+1 min+2 min+3 min+5 min+10 min+20 min+60}; do
    echo ">> $data: at most '$b' changes of day/hour"
    swipl -g main -t halt horaris.pl -- "$data" "$sol" "$work" "$b" "$@"; r=$?
    [ $r -eq 0 ] && exit 0
    [ $r -eq 20 ] || exit 1
done
echo ">> $data: no bound on changes"
swipl -g main -t halt horaris.pl -- "$data" "$sol" "$work" "$@"; r=$?
[ $r -eq 0 ] && exit 0
if [ $# -gt 0 ]; then
    echo ">> $data: no bound and without '$*'"
    swipl -g main -t halt horaris.pl -- "$data" "$sol" "$work"; exit $?
fi
exit $r
