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
	print substr(FILENAME, 1, length(FILENAME)-length(".calx")), $0
}'
(
	cd &&
	find -H D ?.* dl tp doc -name \*.calx \
		-exec awk -vOFS="$HT" "$calx2tsv" {} + &&
	awk -vOFS="$HT" "$calx2tsv" src/*.calx src/[A-Z_]*/*.calx
) |
sqlite3 -tabs db.sqlite \
	"DELETE FROM file_tag;" \
	".import '| cat -' file_tag" \
	"DELETE FROM impl;" \
	".import impl.tsv impl"
