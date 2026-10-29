#!/bin/env python3
import errno, glob, os, re, sqlite3, stat, sys
from typing import Any, Self
from collections.abc import Iterable, Iterator
import mfusepy as fuse # type: ignore[import-untyped]

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

def main() -> None:
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
def esc_sql_like(s: str) -> str:
    return PAT_WILDCARDS.sub(r"\\\1", s)

def attr_l(targ: str) -> dict[str, Any]:
    return ATTR_DEFAULT | {
        "st_mode": stat.S_IFLNK | 0o777,
        "st_size": len(targ.encode()),
    }

def path2tags(path_s: list[str]) -> tuple[list[str], list[str]]:
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

def esc_regex(s: str) -> str:
    # TODO
    return s.replace("$", r"\$")

def _query_db2(
    pos: list[str],
    neg: list[str],
    ty: str = "f",
    tagkey: str = "",
) -> Iterator[str]:
    pos_r = [re.compile("," + esc_regex(t) + ",") for t in sorted(pos)]
    neg_r = re.compile("|".join("," + esc_regex(t) + "," for t in sorted(neg)))
    tagkey_r = re.compile("," + esc_regex(tagkey) + r"[^,]*,")
    with open("dat/db2.tsv") as _f:
        for ln in _f:
            f, tt = ln[:-1].split("\t")
            n = 1
            for t in pos_r:
                tt, n = t.subn("", tt)
                if n == 0:
                    break
            if n == 0 or (tagkey and not tagkey_r.search(tt)):
                continue
            if neg and neg_r.search(tt):
                continue
            if ty == "f":
                yield f
            elif ty == "t":
                yield from tt[1:-1].split(",,")

class _F:
    def __init__(self, a: Iterable[str]) -> None:
        self.a = iter(sorted(set(a)))
    def __iter__(self) -> Self:
        return self
    def __next__(self) -> tuple[str]:
        return (next(self.a),)

def real_path(fname: str, virtdir: str = "") -> str:
    fname_s = fname.split(":")
    if virtdir:
        fname_s = virtdir.split(":")[:-1] + fname_s
    return DIR_BASE + "/" + "/".join(fname_s)

def get_symlink_targs(fname: str) -> list[str]:
    targ = real_path(fname)
    paths = glob.glob(glob.escape(targ)) + glob.glob(glob.escape(targ) + ".*")
    return [
        p for p in paths if not p.endswith(".calx")
    ] or [targ] # broken symlink or *.calx

def get_files_in(
    pos: list[str],
    neg: list[str],
    filt: str = "1",
    args: list[str] = [],
) -> Iterator[tuple[str]]:
    def file_is(f: str) -> bool: return filt != "ft.f = ?" or f == args[0]
    return _F(f for f in _query_db2(pos, neg) if file_is(f))
"""
    q = "SELECT DISTINCT ft.f FROM file_tag_w_impl ft\n"
    for i in range(len(partags)):
        q += f"JOIN file_tag_w_impl ft{i} ON ft.f = ft{i}.f AND ft{i}.t = ?\n"
    q += f"WHERE {filt}\n"
    q += "ORDER BY ft.f\n"
    return conn.cursor().execute(q, partags + args)
"""

def get_tags_in(
    pos: list[str],
    neg: list[str],
    filt: str = "1",
    args: list[str] = [],
) -> Iterator[tuple[str]]:
    return _F(_query_db2(pos, neg, "t"))
"""
    q = "SELECT DISTINCT ft.t FROM file_tag_w_impl ft\n"
    for i in range(len(partags)):
        q += f"JOIN file_tag_w_impl ft{i} ON ft.f = ft{i}.f AND ft{i}.t = ? AND ft.t != ft{i}.t\n"
    q += f"WHERE ft.t NOT LIKE '.%' AND {filt}\n"
    q += "ORDER BY ft.t || '<'\n" # appending '<' sorts "a" imm before "a="
    return conn.cursor().execute(q, partags + args)
"""

def get_tagvals_in(pos: list[str], neg: list[str]) -> Iterator[tuple[str]]:
    (*pos, tagkey) = pos
    tagkey += "="
    return _F(t for t in _query_db2(pos, neg, "t", tagkey) if t.startswith(tagkey))
"""
    return get_tags_in(partags,
        filt="ft.t LIKE ? ESCAPE '\\'",
        args=[esc_sql_like(tagkey) + "=%"])
"""

def len_shared_prefix(a: Iterable[Any], b: Iterable[Any]) -> int:
    return ([x == y for x, y in zip(a, b)] + [False]).index(False)

def proc_tags(tags: Iterator[str]) -> Iterator[str]:
    try:
        prev = next(tags).split("=")
    except StopIteration:
        return
    for _t in tags:
        t = _t.split("=")
        if i := len_shared_prefix(prev, t):
            prev = t[:i]
            continue
        yield "=".join(prev)
        prev = t
    yield "=".join(prev)

class CalxFS(fuse.Operations): # type: ignore[misc]
    def __init__(self) -> None:
        self.use_ns = True # make warning go away

    def getattr(self, path: str, fh: int | Any = None) -> dict[str, Any]:
        dname = path[1:].split("/")
        tags = path2tags(dname)
        bname = dname.pop()

        if path == "/":
            return ATTR_D

        is_in_virtdir = dname and dname[-1][0] not in "#!="
        if is_in_virtdir:
            virtdir_in_tags = next(get_files_in(*tags,
                filt="ft.f = ?",
                args=[dname[-1].replace(":", "/")]), None)
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

        file_is_in_tags = next(get_files_in(*tags,
            filt="ft.f = ?",
            args=[bname.replace(":", "/")]), None)
        if not file_is_in_tags:
            print(f"ENOENT: file {bname} !in tags {tags}", file=sys.stderr)
            raise fuse.FuseOSError(errno.ENOENT)

        if len(symlink_targs := get_symlink_targs(bname)) > 1:
            return ATTR_D # this is a virtdir
        return attr_l(symlink_targs[0])

    def readdir(self, path: str, _fh: int) -> fuse.ReadDirResult:
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

        if tags[0]:
            for t in proc_tags(
                t[len(tags[0][-1] + "="):]
                for t, in get_tagvals_in(*tags)):
                yield "=" + t
        for t in proc_tags(t for t, in get_tags_in(*tags)):
            yield "#" + t
        for f, in get_files_in(*tags):
            yield f.replace("/", ":")

    def readlink(self, path: str) -> str:
        dname = path[1:].split("/")
        bname = dname.pop()
        is_in_virtdir = dname and dname[-1][0] not in "#!="
        if is_in_virtdir:
            return real_path(bname, dname[-1])
        return get_symlink_targs(bname)[0]

if __name__ == "__main__":
    main()

