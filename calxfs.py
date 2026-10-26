#!/bin/env python3
import errno, glob, os, re, sqlite3, stat, sys
import mfusepy as fuse

DIR_MOUNTPOINT = "/mnt/calxfs"
DIR_BASE = os.path.expanduser("~")
ATTR_DEFAULT = {
    "st_nlink": 1,
    "st_size": 0,
    "st_uid": os.getuid(),
    "st_gid": os.getgid(),
}
ATTR_D = ATTR_DEFAULT | {
    "st_mode": stat.S_IFDIR | 0o755,
    "st_nlink": 2,
}

def main():
    """
    global conn
    conn = sqlite3.connect("dat/db.sqlite")
    conn.execute("PRAGMA case_sensitive_like=ON")
    """
    fg = (sys.argv[1] != "bg") if len(sys.argv) > 1 else True
    fuse.FUSE(CalxFS(), DIR_MOUNTPOINT, foreground=fg, nothreads=True)
    """
    conn.close()
    """

PAT_WILDCARDS = re.compile(r"([%_\\])")
def esc_sql_like(s):
    return PAT_WILDCARDS.sub(r"\\\1", s)

def attr_l(targ):
    return ATTR_DEFAULT | {
        "st_mode": stat.S_IFLNK | 0o777,
        "st_size": len(targ.encode()),
    }

def path2tags(path_s):
    pos, neg = [], []
    for t in path_s:
        if t.startswith("#"):
            pos.append(t[1:])
        elif t.startswith("!"):
            neg.append(t[1:])
        elif t.startswith("="):
            if not pos:
                raise fuse.FuseOSError(errno.ENOENT)
            pos[-1] += t
    return pos, neg

def esc_regex(s):
    return s.replace("$", r"\$")

def _query_db2(partags, ty="f", tagkey=None):
    pos, neg = partags
    pos = [re.compile("," + esc_regex(t) + ",") for t in sorted(pos)]
    neg = re.compile("|".join("," + esc_regex(t) + "," for t in sorted(neg)))
    if tagkey:
        tagkey = re.compile("," + esc_regex(tagkey) + r"[^,]*,")
    with open("dat/db2.tsv") as f:
        for ln in f:
            f, tt = ln[:-1].split("\t")
            n = 1
            for t in pos:
                tt, n = t.subn("", tt)
                if n == 0:
                    break
            if n == 0 or tagkey and not tagkey.search(tt):
                continue
            if neg.pattern and neg.search(tt):
                continue
            if ty == "f":
                yield f
            elif ty == "t":
                yield from tt[1:-1].split(",,")

class _F:
    def __init__(self, a):
        self.a = iter(sorted(set(a)))
    def __iter__(self):
        return self
    def __next__(self):
        return (next(self.a),)
    def fetchone(self):
        return next(self, None)

def real_path(fname, virtdir=None):
    fname = fname.split(":")
    if virtdir:
        fname = virtdir.split(":")[:-1] + fname
    return DIR_BASE + "/" + "/".join(fname)

def get_symlink_targs(fname):
    targ = real_path(fname)
    paths = glob.glob(glob.escape(targ)) + glob.glob(glob.escape(targ) + ".*")
    return [
        p for p in paths if not p.endswith(".calx")
    ] or [targ] # broken symlink or *.calx

def get_files_in(partags, filt="1", args=[]):
    filt = filt == "ft.f = ?"
    return _F(f for f in _query_db2(partags) if not filt or f == args[0])
"""
    q = "SELECT DISTINCT ft.f FROM file_tag_w_impl ft\n"
    for i in range(len(partags)):
        q += f"JOIN file_tag_w_impl ft{i} ON ft.f = ft{i}.f AND ft{i}.t = ?\n"
    q += f"WHERE {filt}\n"
    q += "ORDER BY ft.f\n"
    return conn.cursor().execute(q, partags + args)
"""

def get_tags_in(partags, filt="1", args=[]):
    return _F(_query_db2(partags, "t"))
"""
    q = "SELECT DISTINCT ft.t FROM file_tag_w_impl ft\n"
    for i in range(len(partags)):
        q += f"JOIN file_tag_w_impl ft{i} ON ft.f = ft{i}.f AND ft{i}.t = ? AND ft.t != ft{i}.t\n"
    q += f"WHERE ft.t NOT LIKE '.%' AND {filt}\n"
    q += "ORDER BY ft.t || '<'\n" # appending '<' sorts "a" imm before "a="
    return conn.cursor().execute(q, partags + args)
"""

def get_tagvals_in(tags):
    (*pos, tagkey), neg = tags
    partags = (pos, neg)
    tagkey += "="
    return _F(t for t in _query_db2(partags, "t", tagkey) if t.startswith(tagkey))
"""
    return get_tags_in(partags,
        filt="ft.t LIKE ? ESCAPE '\\'",
        args=[esc_sql_like(tagkey) + "=%"])
"""

def same_prefix_len(a, b):
    return ([x == y for x, y in zip(a, b)] + [False]).index(False)

def proc_tags(tags):
    try:
        prev = next(tags).split("=")
    except StopIteration:
        return
    for t in tags:
        t = t.split("=")
        i = same_prefix_len(prev, t)
        if i:
            prev = t[:i]
            continue
        yield "=".join(prev)
        prev = t
    yield "=".join(prev)

class CalxFS(fuse.Operations):
    def __init__(self):
        self.use_ns = True # make warning go away

    def getattr(self, path, fh=None):
        dname = path[1:].split("/")
        tags = path2tags(dname)
        bname = dname.pop()

        if path == "/":
            return ATTR_D

        is_in_virtdir = dname and dname[-1][0] not in "#!="
        if is_in_virtdir:
            virtdir_in_tags = get_files_in(tags,
                filt="ft.f = ?",
                args=[dname[-1].replace(":", "/")]).fetchone()
            if not virtdir_in_tags:
                print(f"ENOENT: virtdir {dname[-1]} !in tags {tags}", file=sys.stderr)
                raise fuse.FuseOSError(errno.ENOENT)
            targ = real_path(bname, dname[-1])
            if not os.path.lexists(targ):
                print(f"ENOENT: !E {targ=}", file=sys.stderr)
                raise fuse.FuseOSError(errno.ENOENT)
            return attr_l(targ)

        if bname[0] in "#!=":
            return ATTR_D

        # secret hidden symlink to conveniently edit .calx files
        if bname.endswith(".calx"):
            return attr_l(real_path(bname))

        file_is_in_tags = get_files_in(tags,
            filt="ft.f = ?",
            args=[bname.replace(":", "/")]).fetchone()
        if not file_is_in_tags:
            print(f"ENOENT: file {bname} !in tags {tags}", file=sys.stderr)
            raise fuse.FuseOSError(errno.ENOENT)

        symlink_targs = get_symlink_targs(bname)
        if len(symlink_targs) > 1:
            return ATTR_D # this is a virtdir
        return attr_l(symlink_targs[0])

    def readdir(self, path, _fh):
        dname = path[1:].split("/")
        tags = path2tags(dname)
        bname = dname.pop()

        yield "."
        yield ".."

        is_virtdir = bname and bname[0] not in "#!="
        if is_virtdir:
            for f in get_symlink_targs(bname):
                yield f.split("/")[-1]
            return

        for t in proc_tags(
            t[len(tags[0][-1] + "="):]
            for t, in tags[0] and get_tagvals_in(tags)):
            yield "=" + t
        for t in proc_tags(t for t, in get_tags_in(tags)):
            yield "#" + t
        for f, in get_files_in(tags):
            yield f.replace("/", ":")

    def readlink(self, path):
        dname = path[1:].split("/")
        bname = dname.pop()
        is_in_virtdir = dname and dname[-1][0] not in "#!="
        if is_in_virtdir:
            return real_path(bname, dname[-1])
        return get_symlink_targs(bname)[0]

if __name__ == "__main__":
    main()

