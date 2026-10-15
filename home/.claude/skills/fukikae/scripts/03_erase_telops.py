#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元動画から焼き込みテロップを消す（カットごと・ボカさずに埋める）→ work/clean.mp4
使い方: 03_erase_telops.py <作業フォルダ> [カット割り.csv]
  カット割りCSV（No,開始秒,終了秒）が無ければ、場面転換を自動検出して使う。
  文字やない箱（看板・大カード等）は work/manual_boxes.json に [[t0,t1,x0,y0,x1,y1,名前],...] で置く（720x1280基準）。
実測で決めた値: 覆う範囲29px／穴のまわりの合致6.0／塊の75%未満は借りた画素を捨てる／NS+内側だけ軽くぼかす"""
import cv2, numpy as np, subprocess, sys, os, csv, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notelop_inpaint as N, notelop_v2 as V
W = sys.argv[1]; SRC = f"{W}/src.mp4"; OUT = f"{W}/clean.mp4"; TMP = f"{W}/.clean_tmp.mp4"
DIL = 29
mb = f"{W}/manual_boxes.json"
N.MANUAL = [tuple(x) for x in json.load(open(mb))] if os.path.exists(mb) else []
def full_mask(bgr, t):
    m = cv2.dilate(N.telop_mask(bgr), np.ones((DIL, DIL), np.uint8))
    for t0, t1, x0, y0, x1, y1, _ in N.MANUAL:
        if t0 <= t <= t1: m[y0:y1, x0:x1] = 255
    return m
N.full_mask = full_mask

cap = cv2.VideoCapture(SRC); fps = cap.get(cv2.CAP_PROP_FPS); total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
# カット割り
if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
    bounds = [0] + [int(round(float(r["終了秒"])*fps)) for r in csv.DictReader(open(sys.argv[2], encoding="utf-8-sig"))]
else:
    prev = None; d = []
    while True:
        ok, f = cap.read()
        if not ok: break
        g = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (90, 160)).astype(np.float32)
        d.append(float(np.abs(g-prev).mean()) if prev is not None else 0.0); prev = g
    d = np.array(d); cuts = [i for i, x in enumerate(d) if x > 25 and x > 2.5*np.median([d[j] for j in range(max(0, i-3), min(len(d), i+4)) if j != i] or [1])]
    bounds = [0] + cuts + [total]
    print(f"場面転換を自動検出: {len(cuts)}か所")
bounds[-1] = total
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{N.W}x{N.H}", "-r", str(fps), "-i", "-",
                        "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", TMP], stdin=subprocess.PIPE)
done = 0
for si in range(len(bounds)-1):
    i0, i1 = bounds[si], bounds[si+1]
    if i1 <= i0: continue
    cap.set(cv2.CAP_PROP_POS_FRAMES, i0); fr = []
    for _ in range(i1-i0):
        ok, f = cap.read()
        if not ok: break
        fr.append(cv2.resize(f, (N.W, N.H)))
    if not fr: continue
    out, ratio = V.clean_shot(fr, [(i0+k)/fps for k in range(len(fr))])
    for f in out: enc.stdin.write(f.tobytes())
    done += len(out); print(f"  カット{si+1}/{len(bounds)-1}  {done}/{total}コマ  本物の画素{ratio*100:.0f}%", flush=True)
enc.stdin.close(); enc.wait(); cap.release()
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", TMP, "-i", SRC, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart", OUT], check=True)
os.remove(TMP)
# 消し残しの検算
c = cv2.VideoCapture(OUT); i = 0; hits = 0
while True:
    ok, f = c.read()
    if not ok: break
    if i % 15 == 0 and N.telop_mask(f).max() > 0: hits += 1
    i += 1
print(f"✅ {OUT}  {i}コマ  消し残しの疑い {hits}点（0が合格）")
