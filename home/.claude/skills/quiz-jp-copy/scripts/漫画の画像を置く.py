#!/usr/bin/env python3
"""作った画像（生成/<番号>.png）を、参考の同じ番号の縦横に切って、記事の img/m<番号>.jpg に置く。
動く番号の mp4 はここでは作らない（止まった絵を寄せた mp4 は D6 で落ちる）。動く物は 動く物を作る.py で作る。

使い方: python3 漫画の画像を置く.py <生成のフォルダ> <縦横.json> <img のフォルダ> [--直す 73:0.26,130:0.26] [--幅 780]
  縦横.json: [[番号, "portrait|square|landscape", 縦÷横], ...]（参考の画像を落とした時に測った値）
  --直す   : 参考が細長い（縦÷横 0.4 未満）番号は、細長い画像の検査で落ちるので縦÷横を上書きする
  作った画像と参考の縦横が 0.06 より違う時は切らない（画像の中の字が切れるため）。幅は既定 780px
"""
import argparse, json, os
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("rows"); ap.add_argument("out")
ap.add_argument("--直す", default=""); ap.add_argument("--幅", type=int, default=780)
a = ap.parse_args()
fix = {int(k): float(v) for k, v in (x.split(":") for x in a.直す.split(",") if x)}
os.makedirs(a.out, exist_ok=True)
done, lost, warn = 0, [], []
rows = json.load(open(a.rows))
for n, _, q in rows:
    src = f"{a.src}/{n:03d}.png"
    if not os.path.exists(src): lost.append(n); continue
    im = Image.open(src).convert("RGB"); W, H = im.size
    if n in fix:
        q = fix[n]
    elif abs(H / W - q) > 0.06:
        warn.append(f"{n}: 参考 {q:.2f} / 作った絵 {H / W:.2f}（作った絵の縦横のまま置いた）"); q = H / W
    if H / W > q: nh = int(W * q); top = (H - nh) // 2; im = im.crop((0, top, W, top + nh))
    else: nw = int(H / q); left = (W - nw) // 2; im = im.crop((left, 0, left + nw, H))
    im = im.resize((a.幅, int(a.幅 * im.height / im.width)), Image.LANCZOS)
    im.save(f"{a.out}/m{n:03d}.jpg", quality=84, optimize=True); done += 1
print(f"置いた {done} / 全体 {len(rows)}")
for w in warn: print("  縦横が違う", w)
if lost:
    print("  作った画像が無い番号:", lost)   # 画像を作る手順5に戻る
    raise SystemExit(1)
