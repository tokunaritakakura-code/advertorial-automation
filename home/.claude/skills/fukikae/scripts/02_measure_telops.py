#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元動画の「焼き込みテロップ」の位置を、文（whisperの区切り）ごとに全コマで測って中央値を取る。
→ work/english_boxes.json  （n, t0, t1, en, cy=中心yの比率, lines, found）
使い方: 02_measure_telops.py <作業フォルダ>
※ テロップ検出は「真っ白い字＋黒フチ」の条件（notelop_inpaint.telop_mask）。別の見た目なら telop_mask を差し替える"""
import cv2, numpy as np, re, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notelop_inpaint as N
W = sys.argv[1]
segs = []
for blk in open(f"{W}/whisper.srt", encoding="utf-8").read().strip().split("\n\n"):
    ls = blk.split("\n"); m = re.match(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", ls[1])
    t0 = int(m[1])*3600+int(m[2])*60+int(m[3])+int(m[4])/1000; t1 = int(m[5])*3600+int(m[6])*60+int(m[7])+int(m[8])/1000
    segs.append((int(ls[0]), t0, t1, " ".join(ls[2:]).strip()))
cap = cv2.VideoCapture(f"{W}/src.mp4"); out = []
for n, t0, t1, en in segs:
    boxes = []
    for t in np.arange(t0+0.15, t1-0.1, 0.2):
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000); ok, f = cap.read()
        if not ok: continue
        f = cv2.resize(f, (N.W, N.H)); m = N.telop_mask(f)
        if m.max() == 0: continue
        ys, xs = np.nonzero(m); boxes.append((xs.min(), ys.min(), xs.max(), ys.max()))
    if boxes:
        b = np.median(np.array(boxes), 0).astype(int)
        out.append(dict(n=n, t0=t0, t1=t1, en=en, x0=int(b[0]), y0=int(b[1]), x1=int(b[2]), y1=int(b[3]),
                        cy=round((b[1]+b[3])/2/N.H, 3), lines=1 if (b[3]-b[1]) < 60 else 2, found=len(boxes)))
    else:
        out.append(dict(n=n, t0=t0, t1=t1, en=en, found=0))
cap.release()
json.dump(out, open(f"{W}/english_boxes.json", "w"), ensure_ascii=False, indent=0)
print(f"{'#':>2}{'秒':>13}{'検出':>5}{'中心y':>7}  元の文")
for o in out:
    print(f"{o['n']:>2}{o['t0']:>6.1f}-{o['t1']:<6.1f}{o['found']:>5}{(o.get('cy') or 0):>7.3f}  {o['en'][:48]}")
print(f"\n→ {W}/english_boxes.json   テロップが無い文＝{sum(1 for o in out if not o['found'])}本（そこは日本語も出さん）")
