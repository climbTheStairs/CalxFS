#!/bin/sh
readonly HT=$(printf \\t)
readonly calx2tsv='function esc_sh(s) {
	gsub("'\''", "'\'\\\\\'\''", s) # have fun parsing this
	return "'\''" s "'\''"
}
function get_exts(fname_root, exts,   nfiles, cmd, f) {
	split("", exts)
	cmd="ls -dp -- 2> /dev/null " \
		esc_sh(fname_root) ".* " \
		esc_sh(fname_root)
	while ((cmd | getline f) > 0)
		if (f !~ /[.]calx$/)
			exts[get_ext(f)]=nfiles++
	close(cmd)
	return nfiles+0
}
function get_ext(fname,   a) {
	sub("/$",		"._d",		fname)
	sub(".*/",		"",			fname)
	sub("^[^.]*$",	"_none",	fname)
	return a[split(fname, a, ".")]
}
index(FILENAME, "#") == 1 {
	print "fname " FILENAME " illegal, cannot start with char '\'#\''" | "cat >&2"
	exit 1
}
index(FILENAME, ":") {
	print "fname " FILENAME " contains illegal char '\':\''" | "cat >&2"
	exit 1
}
index(FILENAME, "\n") {
	print "fname " FILENAME " contains illegal char '\'\\n\''" | "cat >&2"
	exit 1
}
FNR == 1 {
	fname_root=substr(FILENAME, 1, length(FILENAME)-length(".calx"))
	print fname_root, "$nfiles=" get_exts(fname_root, exts)
	for (ext in exts)
		print fname_root, "$ext=" ext
}
{
	print fname_root, $0
}'
(
	cd &&
	find -H -- ? ?.* dl tp doc -name \*.calx \
		-exec awk -vOFS="$HT" -- "$calx2tsv" {} + &&
	awk -vOFS="$HT" -- "$calx2tsv" src/*.calx src/[A-Z_]*/*.calx
) | sqlite3 -tabs db.sqlite \
	"DELETE FROM file_tag;" \
	".import '| cat -' file_tag" \
	"DELETE FROM impl;" \
	".import impl.tsv impl"

