#!/bin/sh
readonly HT=$(printf \\t)
readonly calx2tsv='function esc_sh(s) {
	gsub("'\''", "'\'\\\\\'\''", s) # have fun parsing this
	return "'\''" s "'\''"
}
function get_exts(f, exts,   nfiles, cmd, ext) {
	split("", exts)
	f=esc_sh(f); f=f ".* " f
	cmd="find -H -- 2> /dev/null " f " \\! -name \\*.calx -prune \\( " \
		"-type d -exec echo _d \\; -o " \
		"-type f -name \\*.\\* -print -o " \
		"-type f -exec echo _n \\; -o " \
		"-type l -exec echo _l \\; -o " \
		"-exec echo _s \\; \\) | " \
		"sed \"s,.*/,,; s,.*[.],,\""
	while ((cmd | getline ext) > 0)
		exts[ext]=nfiles++
	close(cmd)
	cmd="find -- 2> /dev/null " f " -prune -type l"
	if ((cmd | getline ext) > 0)
		exts["_l"]=1
	close(cmd)
	return nfiles+0
}
index(FILENAME, ":") {
	print "fname " FILENAME " contains illegal char '\':\''" | "cat >&2"
	exit 1
}
index(FILENAME, "\n") {
	print "fname " FILENAME " contains illegal char '\'\\\\n\''" | "cat >&2"
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
	find -H -- [!#=] [!#=].* dl tp doc -type f -name \*.calx \
		-exec awk -vOFS="$HT" -- "$calx2tsv" {} + &&
	awk -vOFS="$HT" -- "$calx2tsv" src/*.calx src/[A-Z_]*/*.calx
) | sqlite3 -tabs db.sqlite \
	"BEGIN;" \
	"DELETE FROM file_tag;" \
	".import '| cat -' file_tag" \
	"DELETE FROM impl;" \
	".import impl.tsv impl" \
	"COMMIT;"

