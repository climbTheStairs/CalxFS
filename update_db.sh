#!/bin/sh
readonly HT=$(printf \\t)
readonly calx2tsv='FILENAME ~ /:/ {
	print "fname " FILENAME " contains illegal char \":\"" | "cat >&2"
	exit 1
}
/^=/ {
	print "file " FILENAME " contains illegal tag starting with \"=\"" | "cat >&2"
	exit 1
}
{
	print substr(FILENAME, 3, length(FILENAME)-7), $0
	# s[3:-7] == s[len("./")+1:len("./" ".calx")]
}'
(cd ~/dl && find -L ./ -name \*.calx \
	-exec awk -vOFS="$HT" "$calx2tsv" {} +) |
sqlite3 -tabs db.sqlite \
	"DELETE FROM file_tag;" \
	".import '| cat -' file_tag"
