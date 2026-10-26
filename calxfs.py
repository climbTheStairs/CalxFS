#!/bin/env python3
import errno, glob, os, re, sqlite3, stat, sys
import mfusepy as fuse

DIR_MOUNTPOINT = "/mnt/calxfs"
DIR_BASE = os.path.expanduser("~").split("/")
DEFAULT_ATTR = {
    "st_nlink": 1,
    "st_size": 0,
    "st_uid": os.getuid(),
    "st_gid": os.getgid(),
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

def attr_d():
    return DEFAULT_ATTR | {
        "st_mode": stat.S_IFDIR | 0o755,
        "st_nlink": 2,
    }

def attr_l(targ):
    return DEFAULT_ATTR | {
        "st_mode": stat.S_IFLNK | 0o777,
        "st_size": len(targ.encode()),
    }

def path2tags(path_s):
    tags = []
    for t in path_s:
        if t.startswith("#"):
            tags.append(t[1:])
        elif t.startswith("="):
            if not tags:
                raise fuse.FuseOSError(errno.ENOENT)
            tags[-1] += t
    return tags

def esc_regex(s):
    return s.replace("$", r"\$")

def _query_db2(partags, ty="f", tagkey=None):
    partags = [re.compile("," + esc_regex(t) + ",") for t in sorted(partags)]
    if tagkey:
        tagkey = re.compile("," + esc_regex(tagkey) + r"[^,]*,")
    with open("dat/db2.tsv") as f:
        for ln in f:
            f, tags = ln[:-1].split("\t")
            n = 1
            for t in partags:
                tags, n = t.subn("", tags)
                if n == 0:
                    break
            if n == 0 or tagkey and not tagkey.search(tags):
                continue
            if ty == "f":
                yield f
            elif ty == "t":
                tags = tags[1:-1].split(",,")
                for t in tags:
                    yield t

class _F:
    def __init__(self, a):
        self.a = iter(sorted(set(a)))
    def __iter__(self):
        return self
    def __next__(self):
        return (next(self.a),)
    def fetchone(self):
        return next(self, None)

def get_symlink_targs(fname):
    targ = "/".join(DIR_BASE + fname.split(":"))
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
    *partags, tagkey = tags
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
        path_s = path[1:].split("/")
        basename = path_s[-1]
        tags = path2tags(path_s)

        if path == "/":
            return attr_d()

        is_in_virtdir = len(path_s) > 1 and path_s[-2][0] not in "#="
        if is_in_virtdir:
            virtdir_in_tags = get_files_in(tags,
                filt="ft.f = ?",
                args=[path_s[-2].replace(":", "/")]).fetchone()
            if not virtdir_in_tags:
                print(f"ENOENT: virtdir {path_s[-2]=} !in tags {tags}", file=sys.stderr)
                raise fuse.FuseOSError(errno.ENOENT)
            targ = "/".join(DIR_BASE + path_s[-2].split(":")[:-1] + [basename])
            if not os.path.lexists(targ):
                print(f"ENOENT: !E {targ=}", file=sys.stderr)
                raise fuse.FuseOSError(errno.ENOENT)
            return attr_l(targ)

        is_tag_dir = basename[0] in "#="
        if is_tag_dir:
            tag_exists = get_files_in(tags).fetchone() or get_tagvals_in(tags).fetchone()
            if not tag_exists:
                print(f"ENOENT: tags {tags} is empty", file=sys.stderr)
                raise fuse.FuseOSError(errno.ENOENT)
            return attr_d()

        # secret hidden symlink to conveniently edit .calx files
        if basename.endswith(".calx"):
            return attr_l("/".join(DIR_BASE + basename.split(":")))

        file_is_in_tags = get_files_in(tags,
            filt="ft.f = ?",
            args=[basename.replace(":", "/")]).fetchone()
        if not file_is_in_tags:
            print(f"ENOENT: file {basename} !in tags {tags}", file=sys.stderr)
            raise fuse.FuseOSError(errno.ENOENT)

        symlink_targs = get_symlink_targs(basename)
        if len(symlink_targs) > 1:
            return attr_d() # this is a virtdir
        return attr_l(symlink_targs[0])

    def readdir(self, path, _fh):
        path_s = path[1:].split("/")
        basename = path_s[-1]
        tags = path2tags(path_s)

        yield "."
        yield ".."

        is_virtdir = basename and basename[0] not in "#="
        if is_virtdir:
            for f in get_symlink_targs(basename):
                yield f.split("/")[-1]
            return

        for t in proc_tags(
            t[len(tags[-1] + "="):]
            for t, in tags and get_tagvals_in(tags)):
            yield "=" + t
        for t in proc_tags(t for t, in get_tags_in(tags)):
            yield "#" + t
        for f, in get_files_in(tags):
            yield f.replace("/", ":")

    def readlink(self, path):
        path_s = path[1:].split("/")
        basename = path_s[-1]
        is_in_virtdir = len(path_s) > 1 and path_s[-2][0] not in "#="
        if is_in_virtdir:
            return "/".join(DIR_BASE + path_s[-2].split(":")[:-1] + [basename])
        return get_symlink_targs(basename)[0]

if __name__ == "__main__":
    main()

