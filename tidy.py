#!/usr/bin/env python3
"""Finder Tidy: sort a messy Mac folder into colorful, icon'd category folders.

Safe by default: it only PREVIEWS. Nothing moves until you add --apply.
Nothing is ever deleted. Every run is logged so --undo can put it all back.

  python3 tidy.py                     # preview what would happen to ~/Downloads
  python3 tidy.py --apply             # do it
  python3 tidy.py ~/Desktop --apply   # any folder works
  python3 tidy.py --undo              # reverse the last run
  python3 tidy.py --style-only        # just (re)apply folder icons and color tags

Standard library only. Python 3.8+.
"""
import argparse, ctypes, ctypes.util, datetime as dt, hashlib, json, os, plistlib, re, shutil
import struct, sys, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = ".tidy"
TAG_CODES = {"Gray": 1, "Green": 2, "Purple": 3, "Blue": 4, "Yellow": 5, "Red": 6, "Orange": 7}
PARTIAL_EXT = {"crdownload", "download", "part", "partial", "opdownload"}
PROJECT_MARKERS = {".git", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
                   "go.mod", "pom.xml", "Gemfile", "Makefile", "CMakeLists.txt", ".xcodeproj"}
KEEP_FOREVER = {"Career", "Personal", "Taxes", "Health", "Home", "Car", "Money"}
TEXT_PEEK_EXT = {"docx", "txt", "md", "rtf", "csv", "html"}
REVIEW = "Review to Delete"


# ---------------------------------------------------------------- categories
def load_categories(path=None):
    path = path or os.path.join(HERE, "categories.json")
    with open(path, encoding="utf-8") as f:
        cats = json.load(f)["categories"]
    return {c["name"]: c for c in cats}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def folder_name(cat, emoji=True):
    return f"{cat['emoji']} {cat['name']}" if emoji else cat["name"]


def bare(name):
    """'📚 School' -> 'school' so we can match folders with or without emoji."""
    return re.sub(r"^[\W_]+", "", name).strip().lower()


# ---------------------------------------------------------------- helpers
def norm_words(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def ext_of(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""


def peek_text(path, limit=4000):
    """Cheap content peek for a few text-ish formats (no third party libraries)."""
    e = ext_of(path)
    try:
        if e == "docx":
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf8", "ignore")
            return re.sub(r"<[^>]+>", " ", xml)[:limit]
        if e in TEXT_PEEK_EXT and os.path.getsize(path) < 5_000_000:
            with open(path, encoding="utf8", errors="ignore") as f:
                return f.read(limit)
    except Exception:
        pass
    return ""


def sha256(path, cap=1 << 30):
    if os.path.getsize(path) > cap:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def installed_apps():
    names = set()
    for d in ("/Applications", os.path.expanduser("~/Applications")):
        if os.path.isdir(d):
            names |= {re.sub(r"[^a-z0-9]", "", n.lower().replace(".app", "")) for n in os.listdir(d)}
    return names


# ---------------------------------------------------------------- classify
class Classifier:
    def __init__(self, cats):
        self.cats = cats
        self.by_ext = {}
        for c in cats.values():
            for e in c["extensions"]:
                self.by_ext.setdefault(e, c["name"])
        self.kw = []
        for c in cats.values():
            for k in c["keywords"]:
                self.kw.append((re.compile(r"\s" + re.escape(norm_words(k).strip()) + r"\s"), c["name"]))
        self.apps = installed_apps()

    def keyword_category(self, text):
        hits = {}
        for rx, name in self.kw:
            if rx.search(text):
                hits[name] = hits.get(name, 0) + 1
        if not hits:
            return None
        order = list(self.cats)
        return max(hits, key=lambda n: (hits[n], -order.index(n)))

    def classify(self, path, now):
        """Return (category, reason, review_subfolder_or_None)."""
        name = os.path.basename(path)
        e = ext_of(name)
        age_days = (now - os.path.getmtime(path)) / 86400

        if os.path.isdir(path):
            if e == "app":
                return "Software", "app bundle", None
            if any(os.path.exists(os.path.join(path, m)) for m in PROJECT_MARKERS) or \
               any(x.endswith(".xcodeproj") for x in os.listdir(path)):
                return "Projects", "code project folder", None
            return None, "folder left as is", None

        size = os.path.getsize(path)
        if name.startswith("~$"):
            return REVIEW, "Office lock file", "Office Temp Files"
        if e in PARTIAL_EXT:
            if age_days > 1:
                return REVIEW, "unfinished download", "Partial Downloads"
            return None, "still downloading", None
        if size == 0:
            return REVIEW, "empty file", "Empty Files"

        words = norm_words(os.path.splitext(name)[0])
        ext_cat = self.by_ext.get(e)

        if ext_cat == "Software":
            base = re.sub(r"[^a-z0-9]", "", re.split(r"[\s_\-.]\d", name.lower())[0])
            if age_days > 14 and base and any(a.startswith(base[:6]) for a in self.apps if len(base) >= 3):
                return REVIEW, "installer for an app you already have", "Used Installers"
            return "Software", "installer", None

        kw_cat = self.keyword_category(words)
        if not kw_cat and e in TEXT_PEEK_EXT | {"docx"}:
            kw_cat = self.keyword_category(norm_words(peek_text(path)))
            if kw_cat:
                return kw_cat, "content mentions " + kw_cat.lower(), None

        media_like = ext_cat in ("Photos", "Videos")
        if kw_cat in ("Screenshots", "Wallpapers") and not media_like:
            kw_cat = None
        if kw_cat and (not media_like or kw_cat in ("Screenshots", "Wallpapers")):
            return kw_cat, "name looks like " + kw_cat.lower(), None
        if ext_cat:
            return ext_cat, "." + e + " file", None
        return "Sort Later", "unknown type", None


# ---------------------------------------------------------------- plan
def existing_category_folders(target, cats):
    found = {}
    for n in os.listdir(target):
        p = os.path.join(target, n)
        if os.path.isdir(p):
            b = bare(n)
            for c in cats.values():
                if b == c["name"].lower():
                    found[c["name"]] = n
    return found


def unique_dest(dst, taken):
    base, ext = os.path.splitext(dst)
    cand, i = dst, 2
    while os.path.exists(cand) or cand in taken:
        cand = f"{base} {i}{ext}"
        i += 1
    taken.add(cand)
    return cand


def build_plan(target, cats, args):
    clf = Classifier(cats)
    now = time.time()
    existing = existing_category_folders(target, cats)
    skip_names = set(existing.values()) | {STATE_DIR, ".DS_Store", ".localized", "Icon\r"}

    items = []
    for n in sorted(os.listdir(target)):
        if n in skip_names or n.startswith("."):
            continue
        p = os.path.join(target, n)
        if now - os.path.getmtime(p) < 600:
            continue  # touched in the last 10 minutes, may still be in use
        cat, reason, sub = clf.classify(p, now)
        if cat:
            items.append({"src": n, "cat": cat, "reason": reason, "sub": sub, "mtime": os.path.getmtime(p)})

    # duplicates (identical bytes): keep the oldest copy
    groups = {}
    for it in items:
        p = os.path.join(target, it["src"])
        if os.path.isfile(p) and it["cat"] != REVIEW:
            h = sha256(p)
            if h:
                groups.setdefault(h, []).append(it)
    for g in groups.values():
        if len(g) > 1:
            g.sort(key=lambda x: (x["mtime"], len(x["src"])))
            for dup in g[1:]:
                dup.update(cat=REVIEW, sub="Duplicates", reason="exact copy of " + g[0]["src"])

    # auto detect: fold small categories into their parent so you only get folders you need
    while True:
        counts = {}
        for it in items:
            counts[it["cat"]] = counts.get(it["cat"], 0) + 1
        changed = False
        for it in items:
            c = cats.get(it["cat"])
            if not c or not c.get("parent") or it["cat"] in existing:
                continue
            if counts[it["cat"]] < args.min_files:
                it.setdefault("orig", it["cat"])
                it["cat"] = c["parent"]
                it["reason"] = it["reason"].split(" (")[0] + f" ({it['orig']}, too few for its own folder)"
                changed = True
        if not changed:
            break

    # archive anything old (except things you should keep handy)
    if args.archive_days:
        cutoff = now - args.archive_days * 86400
        for it in items:
            if it["mtime"] < cutoff and it["cat"] not in KEEP_FOREVER | {REVIEW, "Software"}:
                year = dt.datetime.fromtimestamp(it["mtime"]).year
                it["reason"] = f"untouched since {year}, was {it['cat']}"
                it["sub"] = os.path.join(str(year), it["cat"])
                it["cat"] = "Archive"

    taken, moves = set(), []
    for it in items:
        folder = existing.get(it["cat"]) or folder_name(cats[it["cat"]], not args.no_emoji)
        rel = os.path.join(folder, it["sub"]) if it["sub"] else folder
        dst = unique_dest(os.path.join(target, rel, it["src"]), taken)
        moves.append({"src": it["src"], "dst": os.path.relpath(dst, target),
                      "category": it["cat"], "reason": it["reason"]})
    return moves


def print_plan(moves):
    if not moves:
        print("Nothing to tidy. Your folder is already clean.")
        return
    groups = {}
    for m in moves:
        groups.setdefault(m["dst"].split(os.sep)[0], []).append(m)
    print(f"\nPlan: {len(moves)} items\n")
    for folder in sorted(groups, key=lambda f: (bare(f) == REVIEW.lower(), f)):
        ms = groups[folder]
        print(f"{folder}  ({len(ms)})")
        for m in ms[:12]:
            print(f"   {m['src']}   [{m['reason']}]")
        if len(ms) > 12:
            print(f"   ...and {len(ms) - 12} more")
    print("\nNothing has moved yet. Run again with --apply to do it.")


# ---------------------------------------------------------------- apply / undo
def apply_plan(target, moves):
    os.makedirs(os.path.join(target, STATE_DIR, "logs"), exist_ok=True)
    log_path = os.path.join(target, STATE_DIR, "logs", dt.datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".json")
    done = []
    for m in moves:
        src, dst = os.path.join(target, m["src"]), os.path.join(target, m["dst"])
        if not os.path.abspath(dst).startswith(os.path.abspath(target) + os.sep):
            print("skipped (outside folder):", m["dst"])
            continue
        if not os.path.exists(src) or os.path.exists(dst):
            print("skipped:", m["src"])
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        done.append(m)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(done, f, ensure_ascii=False, indent=1)
    print(f"Moved {len(done)} of {len(moves)} items. Undo any time with: python3 tidy.py --undo")
    return done


def undo_last(target):
    logs = sorted(os.listdir(os.path.join(target, STATE_DIR, "logs"))) if \
        os.path.isdir(os.path.join(target, STATE_DIR, "logs")) else []
    logs = [l for l in logs if l.endswith(".json")]
    if not logs:
        print("No runs to undo.")
        return
    path = os.path.join(target, STATE_DIR, "logs", logs[-1])
    with open(path, encoding="utf-8") as f:
        moves = json.load(f)
    back = 0
    for m in reversed(moves):
        src, dst = os.path.join(target, m["dst"]), os.path.join(target, m["src"])
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            back += 1
    os.rename(path, path + ".undone")
    print(f"Put back {back} of {len(moves)} items.")


# ---------------------------------------------------------------- Finder styling
_libc = None


def _lib():
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        sig = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
        _libc.setxattr.argtypes = sig
        _libc.getxattr.argtypes = sig
        _libc.getxattr.restype = ctypes.c_ssize_t
    return _libc


def set_xattr(path, name, value):
    if hasattr(os, "setxattr"):  # Linux
        os.setxattr(path, name, value)
        return
    buf = ctypes.create_string_buffer(value, len(value))  # macOS
    if _lib().setxattr(os.fsencode(path), name.encode(), buf, len(value), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "setxattr failed: " + path)


def get_xattr(path, name):
    if hasattr(os, "getxattr"):
        try:
            return os.getxattr(path, name)
        except OSError:
            return None
    lib = _lib()
    n = lib.getxattr(os.fsencode(path), name.encode(), None, 0, 0, 0)
    if n <= 0:
        return None
    buf = ctypes.create_string_buffer(n)
    lib.getxattr(os.fsencode(path), name.encode(), buf, n, 0, 0)
    return buf.raw


def resource_fork(icns_bytes):
    body = struct.pack(">I", len(icns_bytes)) + icns_bytes
    rmap = (b"\0" * 24 + struct.pack(">HH", 28, 50) + struct.pack(">H", 0) + b"icns" +
            struct.pack(">HH", 0, 10) + struct.pack(">hHB", -16455, 0xFFFF, 0) + b"\0\0\0" + b"\0" * 4)
    return struct.pack(">IIII", 256, 256 + len(body), len(body), len(rmap)) + b"\0" * 240 + body + rmap


def set_color_tag(folder, color):
    data = plistlib.dumps([f"{color}\n{TAG_CODES[color]}"], fmt=plistlib.FMT_BINARY)
    set_xattr(folder, "com.apple.metadata:_kMDItemUserTags", data)


def _set_custom_icon_flag(folder, on):
    info = bytearray(get_xattr(folder, "com.apple.FinderInfo") or b"\0" * 32)
    flags = struct.unpack_from(">H", info, 8)[0]
    flags = flags | 0x0400 if on else flags & ~0x0400
    struct.pack_into(">H", info, 8, flags)
    set_xattr(folder, "com.apple.FinderInfo", bytes(info))


def set_folder_icon(folder, icns_path):
    icon_file = os.path.join(folder, "Icon\r")
    had_icon = os.path.exists(icon_file)
    if not had_icon:
        open(icon_file, "wb").close()
    with open(icns_path, "rb") as f:
        set_xattr(icon_file, "com.apple.ResourceFork", resource_fork(f.read()))
    hidden = bytearray(32)
    hidden[0:8] = b"iconMACS"
    struct.pack_into(">H", hidden, 8, 0x4000)  # invisible
    set_xattr(icon_file, "com.apple.FinderInfo", bytes(hidden))
    if had_icon:  # nudge Finder to drop its cached icon
        _set_custom_icon_flag(folder, False)
        os.utime(folder, None)
        time.sleep(1)
    _set_custom_icon_flag(folder, True)
    os.utime(folder, None)


def style_folders(target, cats, icons=True, tags=True):
    styled = 0
    for name, folder in existing_category_folders(target, cats).items():
        c = cats[name]
        path = os.path.join(target, folder)
        try:
            if tags:
                set_color_tag(path, c["finder_tag"])
            icns = os.path.join(HERE, "icons", "icns", slug(name) + ".icns")
            if icons and os.path.exists(icns):
                set_folder_icon(path, icns)
            styled += 1
        except OSError as e:
            print(f"Could not style {folder}: {e}")
    print(f"Styled {styled} folders with icons and color tags.")


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Sort a messy folder into colorful category folders.")
    ap.add_argument("target", nargs="?", default="~/Downloads", help="folder to tidy (default ~/Downloads)")
    ap.add_argument("--apply", action="store_true", help="actually move files (default is preview only)")
    ap.add_argument("--undo", action="store_true", help="reverse the last run")
    ap.add_argument("--style-only", action="store_true", help="only apply icons and color tags")
    ap.add_argument("--min-files", type=int, default=3, help="smallest group that gets its own folder (default 3)")
    ap.add_argument("--archive-days", type=int, default=180, help="archive files untouched this long, 0 = never")
    ap.add_argument("--no-emoji", action="store_true", help="plain folder names without emoji")
    ap.add_argument("--no-icons", action="store_true", help="skip custom folder icons")
    ap.add_argument("--no-tags", action="store_true", help="skip Finder color tags")
    ap.add_argument("--categories", help="use your own categories.json")
    ap.add_argument("--plan-out", help="save the plan as JSON instead of printing it")
    ap.add_argument("--plan-in", help="run a plan JSON (for example one written by the Claude skill)")
    args = ap.parse_args(argv)

    target = os.path.abspath(os.path.expanduser(args.target))
    if not os.path.isdir(target):
        sys.exit(f"Not a folder: {target}")
    cats = load_categories(args.categories)
    do_style = not (args.no_icons and args.no_tags)

    if args.undo:
        return undo_last(target)
    if args.style_only:
        return style_folders(target, cats, not args.no_icons, not args.no_tags)

    if args.plan_in:
        with open(args.plan_in, encoding="utf-8") as f:
            moves = json.load(f)
    else:
        moves = build_plan(target, cats, args)

    if args.plan_out:
        with open(args.plan_out, "w", encoding="utf-8") as f:
            json.dump(moves, f, ensure_ascii=False, indent=1)
        print(f"Saved plan with {len(moves)} moves to {args.plan_out}")
        return
    if not args.apply:
        return print_plan(moves)
    apply_plan(target, moves)
    if do_style:
        style_folders(target, cats, not args.no_icons, not args.no_tags)


if __name__ == "__main__":
    main()
