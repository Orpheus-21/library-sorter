#!/usr/bin/env python3
"""Scan a folder of books, read metadata, look up call numbers, write a manifest.

Usage: scan.py FOLDER -o MANIFEST.json [--offline]
This script only reads. It never changes the books.
"""
import argparse, collections, difflib, json, re, shutil, struct, subprocess, sys, time
import urllib.parse, urllib.request, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

UA = {"User-Agent": "library-sorter/1.0 (personal book sorting)"}


def clean_isbn(s):
    d = re.sub(r"[\s-]", "", s or "")
    d = re.sub(r"^(urn:)?isbn:?", "", d, flags=re.I)
    return d if re.fullmatch(r"(97[89]\d{10}|\d{9}[\dXx])", d) else ""


def isbn_in(text):
    m = re.search(r"ISBN[^0-9]{0,12}([\d\- ]{10,17}[\dXx]?)", text or "", re.I)
    return clean_isbn(m.group(1)) if m else ""


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=30).stdout
    except Exception:
        return ""


def meta_epub(p):
    with zipfile.ZipFile(p) as z:
        root = ET.fromstring(z.read("META-INF/container.xml"))
        pkg = ET.fromstring(z.read(root.find(".//{*}rootfile").get("full-path")))
    g = lambda t: [e.text.strip() for e in pkg.iterfind(f".//{{*}}{t}") if e.text]
    return {"title": (g("title") or [""])[0], "author": ", ".join(g("creator")),
            "isbn": next((i for i in map(clean_isbn, g("identifier")) if i), "")}


def meta_docx(p):
    with zipfile.ZipFile(p) as z:
        r = ET.fromstring(z.read("docProps/core.xml"))
    g = lambda t: (r.findtext(f"{{*}}{t}") or "").strip()
    return {"title": g("title"), "author": g("creator")}


def meta_pdf(p):
    out = {}
    if shutil.which("pdfinfo"):
        info = run(["pdfinfo", str(p)])
        for key, field in (("Title", "title"), ("Author", "author")):
            m = re.search(rf"^{key}:\s*(.+)$", info, re.M)
            if m:
                out[field] = m.group(1).strip()
    if shutil.which("pdftotext"):
        out["isbn"] = isbn_in(run(["pdftotext", "-l", "10", str(p), "-"]))
    return out


def meta_txt(p):
    return {"isbn": isbn_in(p.read_bytes()[:20000].decode("utf-8", "replace"))}


def meta_mobi(p):
    # PalmDB header -> record 0 -> MOBI header -> EXTH block (types 100 author, 104 isbn, 503 title)
    d = p.read_bytes()
    start = struct.unpack(">I", d[78:82])[0]
    rec = d[start:]
    if rec[16:20] != b"MOBI":
        return {}
    hlen = struct.unpack(">I", rec[20:24])[0]
    off, ln = struct.unpack(">II", rec[84:92])
    out = {"title": rec[off:off + ln].decode("utf-8", "replace").strip()}
    if struct.unpack(">I", rec[128:132])[0] & 0x40:
        pos = 16 + hlen
        if rec[pos:pos + 4] == b"EXTH":
            count = struct.unpack(">I", rec[pos + 8:pos + 12])[0]
            pos += 12
            for _ in range(count):
                t, n = struct.unpack(">II", rec[pos:pos + 8])
                val = rec[pos + 8:pos + n].decode("utf-8", "replace").strip()
                if t == 100: out["author"] = val
                elif t == 503: out["title"] = val
                elif t == 104: out["isbn"] = clean_isbn(val)
                pos += n
    return out


READERS = {".epub": meta_epub, ".docx": meta_docx, ".pdf": meta_pdf, ".txt": meta_txt,
           ".mobi": meta_mobi, ".azw": meta_mobi, ".azw3": meta_mobi}


def denormalize_lcc(s):
    """Open Library stores LCC in sort form (QA-0076.73000000.C15). Turn it back into QA76.73.C15."""
    m = re.match(r"([A-Z]{1,3})-(\d+)(?:\.(\d+))?(.*)", s.strip())
    if not m:
        return s.strip()
    letters, whole, frac, rest = m.groups()
    rest = rest.strip()
    frac = (frac or "").rstrip("0")
    return letters + (whole.lstrip("0") or "0") + ("." + frac if frac else "") + \
        ("" if not rest else rest if rest.startswith(".") else " " + rest)


def commonest(values, cls):
    """Open Library lists values from every edition, unsorted. Take the first value of the commonest class."""
    values = [v for v in values if cls(v)]
    top = collections.Counter(map(cls, values)).most_common(1)
    return next((v for v in values if cls(v) == top[0][0]), "") if top else ""


def openlibrary(params):
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(
        {**params, "fields": "title,author_name,lcc,ddc", "limit": 5})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            return json.load(r)["docs"]
    except Exception:
        return []


def lookup(b):
    docs = openlibrary({"isbn": b["isbn"]}) if b["isbn"] else []
    if not any(d.get("lcc") or d.get("ddc") for d in docs) and b["title"]:
        q = {"title": b["title"], **({"author": b["author"].split(",")[0]} if b["author"] else {})}
        sim = lambda x, y: difflib.SequenceMatcher(None, x.lower(), y.lower()).ratio()
        first = b["author"].split(",")[0]
        docs = [d for d in openlibrary(q) if sim(d.get("title", ""), b["title"]) >= 0.8
                and (not first or any(sim(n, first) >= 0.6 for n in d.get("author_name", [])))]
    for d in docs:
        if d.get("lcc") or d.get("ddc"):
            b["lcc"] = denormalize_lcc(commonest(d.get("lcc") or [], lambda v: v.split("-")[0] if "-" in v else ""))
            b["ddc"] = commonest([v.split("/")[0].strip() for v in d.get("ddc") or []],
                                 lambda v: v[:3] if re.match(r"\d{3}", v) else "")
            b["source"] = "openlibrary"
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--offline", action="store_true", help="skip the online lookup")
    a = ap.parse_args()
    root = Path(a.folder).resolve()
    books = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_symlink() or not p.is_file() or any(part.startswith(".") for part in rel.parts):
            continue
        try:
            meta = READERS.get(p.suffix.lower(), lambda _: {})(p)
        except Exception as e:
            print(f"metadata error in {rel}: {e}", file=sys.stderr)
            meta = {}
        b = {"path": str(rel), "title": meta.get("title") or re.sub(r"[_\-.]+", " ", p.stem).strip(),
             "author": meta.get("author", ""), "isbn": meta.get("isbn", ""),
             "meta_found": bool(meta.get("title")), "lcc": "", "ddc": "", "source": ""}
        if not a.offline:
            lookup(b)
            time.sleep(0.3)  # ponytail: fixed delay, add backoff if Open Library rate-limits
        books.append(b)
        print(f"[{len(books)}] {rel} -> lcc={b['lcc'] or '-'} ddc={b['ddc'] or '-'}", file=sys.stderr)
    Path(a.out).write_text(json.dumps({"root": str(root), "books": books}, indent=1, ensure_ascii=False))
    print(f"{len(books)} files. Manifest: {a.out}")


if __name__ == "__main__":
    main()
