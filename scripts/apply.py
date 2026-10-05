#!/usr/bin/env python3
"""Plan or apply the shelving of a scanned folder.

Plan only (default): apply.py MANIFEST --system loc|dewey [--dest DIR] [--guesses G.json] [-v]
Do it:               add --execute
Undo an in-place run: apply.py --undo FOLDER

No --dest (or --dest equal to the folder): files MOVE inside the folder, and an undo log is kept.
--dest DIR: files are COPIED into DIR. The originals stay untouched.
G.json maps a file path (as in the manifest) to a call number for that system.
"""
import argparse, json, os, re, shutil, sys
from pathlib import Path

LOG = ".library-sorter-undo.json"


def shelf(num, system):
    """Return (folder, number) for a call number, or ("_Unsorted", "")."""
    num = (num or "").strip()
    if system == "loc":
        m = re.match(r"[A-Z]{1,3}", num.upper())
        return (f"{m.group()[0]}/{m.group()}", num) if m else ("_Unsorted", "")
    return (f"{num[0]}00/{num[:2]}0", num) if re.match(r"\d{3}", num) else ("_Unsorted", "")


def safe(s):
    return re.sub(r'[\\/:*?"<>|]', "_", s)


def clean_empty_dirs(root):
    for d, _, _ in os.walk(root, topdown=False):
        if Path(d) != root:
            try:
                os.rmdir(d)
            except OSError:
                pass


def undo(root):
    root = Path(root).resolve()
    for new, old in reversed(json.loads((root / LOG).read_text())):
        Path(old).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(new, old)
    clean_empty_dirs(root)
    (root / LOG).unlink()
    print("Undo done.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", nargs="?")
    ap.add_argument("--system", choices=["loc", "dewey"])
    ap.add_argument("--dest")
    ap.add_argument("--guesses")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--undo")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if a.undo:
        return undo(a.undo)
    if not (a.manifest and a.system):
        ap.error("MANIFEST and --system are required")

    m = json.loads(Path(a.manifest).read_text())
    root = Path(m["root"])
    dest = Path(a.dest).resolve() if a.dest else root
    in_place = dest == root
    guesses = json.loads(Path(a.guesses).read_text()) if a.guesses else {}
    key = "lcc" if a.system == "loc" else "ddc"

    plan, taken, n_guess, n_unsorted = [], set(), 0, 0
    for b in m["books"]:
        num, source = b[key], b["source"]
        if not num and b["path"] in guesses:
            num, source = guesses[b["path"]], "claude-guess"
        folder, num = shelf(num, a.system)
        if not num:  # rerun on a sorted folder: keep a number that already matches the shelf it sits in
            old_folder, old_num = shelf(Path(b["path"]).name.partition(" - ")[0], a.system)
            if old_num and Path(b["path"]).parent.as_posix() == old_folder:
                folder, num = old_folder, old_num
        n_guess += source == "claude-guess" and bool(num)
        n_unsorted += not num
        src = root / b["path"]
        name = src.name if not num or src.name.startswith(num + " - ") else f"{safe(num)} - {src.name}"
        dst = dest / folder / name
        n = 1
        while dst in taken or (dst.exists() and dst != src):
            n += 1
            dst = dest / folder / f"{Path(name).stem} ({n}){src.suffix}"
        taken.add(dst)
        if dst != src:
            plan.append((src, dst))

    for src, dst in plan if a.verbose else plan[:15]:
        print(f"{src.relative_to(root)}  ->  {dst.relative_to(dest)}")
    if not a.verbose and len(plan) > 15:
        print(f"... {len(plan) - 15} more (use -v to list all)")
    print(f"\nSystem: {a.system}. Mode: {'MOVE in place' if in_place else 'COPY to ' + str(dest)}.")
    print(f"Files to place: {len(plan)}. Claude guesses: {n_guess}. Unsorted: {n_unsorted}.")
    if not a.execute:
        return print("Dry run. Nothing changed.")

    done = []
    try:
        for src, dst in plan:
            dst.parent.mkdir(parents=True, exist_ok=True)
            (shutil.move if in_place else shutil.copy2)(src, dst)
            done.append((str(dst), str(src)))
    finally:  # keep the undo log even if a move fails half way
        if in_place:
            log = root / LOG
            old = json.loads(log.read_text()) if log.exists() else []
            log.write_text(json.dumps(old + done))
            clean_empty_dirs(root)
    print(f"Done. {len(done)} files {'moved' if in_place else 'copied'}.")


if __name__ == "__main__":
    sys.exit(main())
