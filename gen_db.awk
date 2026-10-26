#!/bin/awk -f
BEGIN {FS="\t"}
index($2, ".") == 1 {next}
$1 != prev && NR != 1 {print ""}
$1 != prev {printf "%s\t", prev=$1}
{printf ",%s,", $2}
END {print ""}
