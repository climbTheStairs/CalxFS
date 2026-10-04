#!/bin/sh
readonly HT=$(printf \\t)
readonly calx2tsv='{
	print substr(FILENAME, 3, length(FILENAME)-7), $0
}' # s[3:-7] == [len("./")+1:len("./" ".calx")]
(cd ~/dl; find -L ./ -name \*.calx \
	-exec awk -vOFS="$HT" "$calx2tsv" {} +) |
sqlite3 -tabs db.sqlite \
	"DELETE FROM file_tag;" \
	".import '| cat -' file_tag"
