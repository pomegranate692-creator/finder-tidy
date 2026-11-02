#!/usr/bin/env python3
"""Rebuild the folder icon pack from categories.json.

Each icon = a macOS style folder in the category color + a Lucide glyph (ISC license).
Needs: rsvg-convert (librsvg) and Pillow. Outputs icons/svg, icons/png (1024), icons/icns.
Run from the repo root:  python3 scripts/build_icons.py [path/to/lucide/icons]
"""
import io, json, os, re, struct, subprocess, sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLYPHS = os.path.join(ROOT, "icons", "glyphs")

def shade(hexc, f):
    r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    t = [c + (255 - c) * f if f > 0 else c * (1 + f) for c in (r, g, b)]
    return "#%02X%02X%02X" % tuple(int(x) for x in t)

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def glyph_body(svg_text):
    return "".join(re.findall(r"<(?:path|rect|circle|line|polyline|polygon|ellipse)[^>]*/>", svg_text, re.S))

def folder_svg(color, glyph, i):
    b1, b2, f1 = shade(color, -0.12), shade(color, -0.24), shade(color, 0.2)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
<defs><linearGradient id="b{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{b1}"/><stop offset="1" stop-color="{b2}"/></linearGradient>
<linearGradient id="f{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{f1}"/><stop offset="1" stop-color="{color}"/></linearGradient></defs>
<path d="M168 196h214c22 0 36 8 50 24l30 34c12 14 24 20 44 20h338c38 0 56 18 56 56v460c0 38-18 56-56 56H168c-38 0-56-18-56-56V252c0-38 18-56 56-56z" fill="url(#b{i})"/>
<rect x="146" y="262" width="732" height="220" rx="18" fill="#FFFFFF" opacity="0.92"/>
<rect x="112" y="330" width="800" height="530" rx="54" fill="url(#f{i})"/>
<path d="M166 332h692c30 0 52 22 54 50" stroke="#FFFFFF" stroke-opacity="0.45" stroke-width="4" fill="none"/>
<svg x="362" y="446" width="300" height="300" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">{glyph}</svg>
</svg>'''

def icns(png_path):
    im = Image.open(png_path).convert("RGBA")
    ents = b""
    for typ, size in [(b"icp4", 16), (b"icp5", 32), (b"ic11", 32), (b"ic12", 64), (b"ic07", 128),
                      (b"ic13", 256), (b"ic08", 256), (b"ic14", 512), (b"ic09", 512)]:
        buf = io.BytesIO()
        im.resize((size, size), Image.LANCZOS).save(buf, "PNG", optimize=True)
        d = buf.getvalue()
        ents += typ + struct.pack(">I", len(d) + 8) + d
    return b"icns" + struct.pack(">I", len(ents) + 8) + ents

def main():
    lucide = sys.argv[1] if len(sys.argv) > 1 else None
    cats = json.load(open(os.path.join(ROOT, "categories.json"), encoding="utf-8"))["categories"]
    os.makedirs(GLYPHS, exist_ok=True)
    for sub in ("svg", "png", "icns"):
        os.makedirs(os.path.join(ROOT, "icons", sub), exist_ok=True)
    for i, c in enumerate(cats):
        gpath = os.path.join(GLYPHS, c["glyph"] + ".svg")
        if lucide and not os.path.exists(gpath):
            with open(os.path.join(lucide, c["glyph"] + ".svg")) as src, open(gpath, "w") as dst:
                dst.write(src.read())
        body = glyph_body(open(gpath).read())
        s = slug(c["name"])
        svg = os.path.join(ROOT, "icons", "svg", s + ".svg")
        png = os.path.join(ROOT, "icons", "png", s + ".png")
        open(svg, "w").write(folder_svg(c["color"], body, i))
        subprocess.run(["rsvg-convert", "-w", "1024", "-h", "1024", "-o", png, svg], check=True)
        open(os.path.join(ROOT, "icons", "icns", s + ".icns"), "wb").write(icns(png))
        print("built", s)

if __name__ == "__main__":
    main()
