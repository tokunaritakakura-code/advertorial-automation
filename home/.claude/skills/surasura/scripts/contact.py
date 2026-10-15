#!/usr/bin/env python3
"""
contact.py — build labelled contact-sheet montages for av.mjs (task-fleet 映像脚).

ffmpeg's drawtext isn't in every build (no libfreetype), so labelling +
tiling is done here in PIL, which is reliable and gives per-cell timestamp +
caption chips. Reads a JSON spec on stdin, writes montage_NN.jpg files.

stdin JSON:
  { "frames": [ {"path": "...", "t": 12.3, "caption": "..."} , ... ],
    "out_dir": "...", "cols": 5, "rows_per_sheet": 6,
    "cell_w": 480, "caption_chars": 48 }
stdout JSON:
  { "montages": ["/abs/montage_01.jpg", ...], "cells": <int> }
"""
import sys, os, json, math

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

def load_font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def fmt_t(t):
    if t is None:
        return "?"
    t = float(t)
    m, s = int(t // 60), int(t % 60)
    return f"{m}:{s:02d}"

def main():
    spec = json.load(sys.stdin)
    frames = spec["frames"]
    out_dir = spec["out_dir"]
    cols = int(spec.get("cols", 5))
    rows_per_sheet = int(spec.get("rows_per_sheet", 6))
    cell_w = int(spec.get("cell_w", 480))
    cap_chars = int(spec.get("caption_chars", 48))
    pad = 8
    label_h = 26

    os.makedirs(out_dir, exist_ok=True)
    font = load_font(18)
    font_cap = load_font(15)

    # render each frame into a fixed-width cell with a label bar on top
    cells = []
    for i, fr in enumerate(frames):
        try:
            im = Image.open(fr["path"]).convert("RGB")
        except Exception:
            continue
        w, h = im.size
        cell_h = max(1, round(h * cell_w / w))
        im = im.resize((cell_w, cell_h), Image.LANCZOS)
        canvas = Image.new("RGB", (cell_w, cell_h + label_h), (17, 17, 17))
        canvas.paste(im, (0, label_h))
        d = ImageDraw.Draw(canvas)
        idx_t = f"#{i+1}  {fmt_t(fr.get('t'))}"
        d.text((6, 4), idx_t, fill=(255, 255, 255), font=font)
        cap = (fr.get("caption") or "")
        if cap:
            cap = cap[:cap_chars] + ("…" if len(cap) > cap_chars else "")
            # caption chip along the bottom of the image
            tw = d.textlength(cap, font=font_cap)
            d.rectangle([0, cell_h + label_h - 20, min(cell_w, tw + 12), cell_h + label_h],
                        fill=(0, 0, 0))
            d.text((6, cell_h + label_h - 19), cap, fill=(230, 230, 230), font=font_cap)
        cells.append(canvas)

    if not cells:
        print(json.dumps({"montages": [], "cells": 0}))
        return

    # uniform cell height = max, so the grid is aligned
    cell_h = max(c.size[1] for c in cells)
    per_sheet = cols * rows_per_sheet
    montages = []
    n_sheets = math.ceil(len(cells) / per_sheet)
    for s in range(n_sheets):
        chunk = cells[s * per_sheet:(s + 1) * per_sheet]
        rows = math.ceil(len(chunk) / cols)
        sheet_w = cols * cell_w + (cols + 1) * pad
        sheet_h = rows * cell_h + (rows + 1) * pad
        sheet = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))
        for j, c in enumerate(chunk):
            r, col = divmod(j, cols)
            x = pad + col * (cell_w + pad)
            y = pad + r * (cell_h + pad)
            sheet.paste(c, (x, y))
        outp = os.path.join(out_dir, f"montage_{s+1:02d}.jpg")
        sheet.save(outp, "JPEG", quality=85)
        montages.append(outp)

    print(json.dumps({"montages": montages, "cells": len(cells)}))

if __name__ == "__main__":
    main()
