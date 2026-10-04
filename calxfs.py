#!/bin/env python3
import sqlite3, stat, sys
import mfusepy

# TODO: don't forget to conn.commit() af write

MY_ID = 1000
DIR_MOUNTPOINT = "/home/stairs/calxfs"
DIR_BASE = "/home/stairs/dl"

def main():
    global conn
    conn = sqlite3.connect("db.sqlite")
    mfusepy.FUSE(CalxFS(), DIR_MOUNTPOINT, foreground=True, nothreads=True)
    conn.close()

class CalxFS(mfusepy.Operations):
    def __init__(self):
        self.use_ns = True # make warning go away

    def getattr(self, path, fh=None):
        path_s = path[1:].split("/")
        basename = path_s[-1]
        attr = {
            "st_nlink": 1,
            "st_size": 0,
            "st_uid": MY_ID,
            "st_gid": MY_ID,
        }
        if basename == "" or basename[0] in ".#":
            attr["st_mode"] = stat.S_IFDIR | 0o755
            attr["st_nlink"] = 2
        else:
            attr["st_mode"] = stat.S_IFLNK | 0o777
            attr["st_size"] = len(DIR_BASE + "/" + basename)
        return attr

    def readdir(self, path, _fh):
        #print("[DEBUG] readdir", path, file=sys.stderr)
        cursor = conn.cursor()
        yield "."
        yield ".."
        path_s = path[1:].split("/")
        partags = [t[1:] for t in path_s if t and t[0] in ".#"]

        q = "SELECT DISTINCT ft.t AS chitag FROM file_tag ft\n"
        for i in range(len(partags)):
            q += f"JOIN file_tag ft{i} ON ft.f = ft{i}.f AND ft{i}.t = ? AND chitag != ft{i}.t\n"
        #q += "WHERE chitag NOT LIKE '.%'\n"
        #print("[DEBUG] readdir", path, q, partags, file=sys.stderr)
        for e, in cursor.execute(q, partags):
            if e.startswith("."):
                continue #yield e.replace("/", ":")
            yield "#" + e

        q = "SELECT DISTINCT ft.f FROM file_tag ft\n"
        for i in range(len(partags) - 1):
            q += f"JOIN file_tag ft{i} ON ft.f = ft{i}.f AND ft{i}.t = ?\n"
        if len(partags):
            q += "WHERE ft.t = ?\n"
        #print("[DEBUG] readdir", path, q, partags, file=sys.stderr)
        for e, in cursor.execute(q, partags):
            yield e.replace("/", ":")

    def readlink(self, path):
        fname = path.split("/")[-1]
        return DIR_BASE + "/" + fname.replace(":", "/")

if __name__ == "__main__":
    main()

