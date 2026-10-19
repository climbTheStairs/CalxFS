#!/bin/env python3
import glob, sqlite3, stat, sys
import mfusepy

# TODO: don't forget to conn.commit() af write

MY_ID = 1000
DIR_MOUNTPOINT = "/home/stairs/calxfs/"
DIR_BASE = "/home/stairs/dl/"
DEFAULT_ATTR = {
    "st_nlink": 1,
    "st_size": 0,
    "st_uid": MY_ID,
    "st_gid": MY_ID,
}

def main():
    global conn
    conn = sqlite3.connect("db.sqlite")
    fg = (sys.argv[1] != "bg") if len(sys.argv) > 1 else True
    mfusepy.FUSE(CalxFS(), DIR_MOUNTPOINT, foreground=fg, nothreads=True)
    conn.close()

def attr_d():
    a = DEFAULT_ATTR.copy()
    a["st_mode"] = stat.S_IFDIR | 0o755
    a["st_nlink"] = 2
    return a

def attr_l(sz):
    a = DEFAULT_ATTR.copy()
    a["st_mode"] = stat.S_IFLNK | 0o777
    a["st_size"] = sz
    return a

def get_files(fname):
    globstr = glob.escape(DIR_BASE + fname.replace(":", "/")) + "*"
    return [
        path[len(DIR_BASE):].replace("/", ":")
        for path in glob.glob(globstr)
        if not path.endswith(".calx") or fname.endswith(".calx")
    ]

class CalxFS(mfusepy.Operations):
    def __init__(self):
        self.use_ns = True # make warning go away

    def getattr(self, path, fh=None):
        path_s = path[1:].split("/")
        basename = path_s[-1]
        if basename == "" or basename[0] in "#=":
            return attr_d()
        files = get_files(basename)
        if len(files) == 1:
            return attr_l(len((DIR_BASE + files[0]).encode()))
        return attr_d()

    def readdir(self, path, _fh):
        #print("[DEBUG] readdir", path, file=sys.stderr)
        path_s = path[1:].split("/")
        basename = path_s[-1]
        yield "."
        yield ".."

        # non-tag dir; for when ${f%.calx}* yields mult
        if basename and basename[0] not in "#=":
            for f in get_files(basename):
                yield f
            return

        cursor = conn.cursor()
        partags = []
        for t in path_s:
            if t.startswith("#"):
                partags.append(t[1:])
            elif t.startswith("="):
                partags[-1] += t

        # TODO: DRY
        if partags:
            q = "SELECT DISTINCT ft.t AS chitag FROM file_tag ft\n"
            for i in range(len(partags[:-1])):
                q += f"JOIN file_tag ft{i} ON ft.f = ft{i}.f AND ft{i}.t = ? AND chitag != ft{i}.t\n"
            q += "WHERE chitag LIKE ?\n"
            q += "ORDER BY chitag\n"
            s = partags[-1].replace("'", "''") + "=%"
            for e, in cursor.execute(q, partags[:-1] + [s]):
                yield e[e.index("="):]

        q = "SELECT DISTINCT ft.t AS chitag FROM file_tag ft\n"
        for i in range(len(partags)):
            q += f"JOIN file_tag ft{i} ON ft.f = ft{i}.f AND ft{i}.t = ? AND chitag != ft{i}.t\n"
        q += "WHERE chitag NOT LIKE '.%'\n"
        q += "ORDER BY chitag || '<'\n" # append '<' to sort "a" imm before "a="
        #print("[DEBUG] readdir", path, q, partags, file=sys.stderr)
        prev = ""
        for e, in cursor.execute(q, partags):
            if "=" in e:
                e = e[:e.index("=")]
            if e == prev:
                continue
            yield "#" + e
            prev = e

        q = "SELECT DISTINCT ft.f FROM file_tag ft\n"
        for i in range(len(partags) - 1):
            q += f"JOIN file_tag ft{i} ON ft.f = ft{i}.f AND ft{i}.t = ?\n"
        if len(partags):
            q += "WHERE ft.t = ?\n"
        #print("[DEBUG] readdir", path, q, partags, file=sys.stderr)
        for e, in cursor.execute(q, partags):
            yield e.replace("/", ":")

    def readlink(self, path):
        path_s = path[1:].split("/")
        basename = path_s[-1]
        return DIR_BASE + get_files(basename)[0].replace(":", "/")

if __name__ == "__main__":
    main()

