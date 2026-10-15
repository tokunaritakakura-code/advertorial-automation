#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「尾」を全コマで数える（合格＝不良コマ ≤ 0.09%）。v2：正解のある物差しで測る。
使い方: 07_residue.py <作業フォルダ> <出力.mp4> [しきい値=10]
 A 覆い漏れ：元テロップの**字の箱**（+4px）が帯からはみ出とるコマ
 B 白い字の残り：帯の外に「白字＋黒フチ」が残っとるコマ
 C にじみ：字の周り（字と黒フチを除いた、消した範囲の残り）で、**元動画と消し済みの差**が大きいコマ
   ここは元動画に本物の背景が写っとる場所なので、消したあとも同じ画素になるのが正解。差＝消し跡。
→ work/residue.json ／ 悪い順12コマ work/residue_worst.png"""
import cv2, numpy as np, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notelop_inpaint as N
W_, OUT = sys.argv[1], sys.argv[2]; TH = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
layers = {L["n"]: L for L in json.load(open(OUT + ".layers.json"))}
iv = json.load(open(f"{W_}/telop_intervals.json")); SX, SY = 1080/720, 1920/1280
src = cv2.VideoCapture(f"{W_}/src.mp4"); cln = cv2.VideoCapture(f"{W_}/clean.mp4"); out = cv2.VideoCapture(OUT); prev_s = None
n = int(out.get(cv2.CAP_PROP_FRAME_COUNT)); fps = out.get(cv2.CAP_PROP_FPS)
frame_iv = {}
for k, b in enumerate(iv, 1):
    for f in range(b["f0"], b["f1"] + 1): frame_iv[f] = k
bad = []; i = 0; cvals = []
K6 = np.ones((7, 7), np.uint8); K29 = np.ones((29, 29), np.uint8)
while True:
    ok1, fs = src.read(); ok2, fc = cln.read(); ok3, fo = out.read()
    if not (ok1 and ok2 and ok3): break
    reasons = []; k = frame_iv.get(i); L = layers.get(k) if k else None
    fs = cv2.resize(fs, (N.W, N.H)); fc = cv2.resize(fc, (N.W, N.H))
    band = np.zeros((N.H, N.W), np.uint8)
    if L:
        x0, y0, x1, y1 = [int(v) for v in L["box"]]; band[int(y0/SY):int(y1/SY), int(x0/SX):int(x1/SX)] = 255
        b = iv[k-1]
        if not (x0 <= max(0, b["x0"]*SX-4) and y0 <= max(0, b["y0"]*SY-4) and x1 >= min(1080, b["x1"]*SX+4) and y1 >= min(1920, b["y1"]*SY+4)): reasons.append("A覆い漏れ")
    # B：出力の帯の外に白字
    mo = N.telop_mask(cv2.resize(fo, (N.W, N.H))); mo[band > 0] = 0
    if (mo > 0).sum() > 40: reasons.append("B白字")
    # C：元の字の周りで、元動画と消し済みの差
    ms = N.telop_mask(fs)
    if ms.max():
        strokes = cv2.dilate(ms, K6); ring = cv2.dilate(ms, K29); ring[strokes > 0] = 0; ring[band > 0] = 0
        if (ring > 0).sum() > 300:
            d = np.abs(fs.astype(np.float32) - fc.astype(np.float32)).mean(2)
            v = float(d[ring > 0].mean()); cvals.append(v)
            # 元動画そのものがその場所で動いとる量（前のコマとの差）。それより十分大きい差だけ「消し跡」
            mv = float(np.abs(fs.astype(np.float32) - prev_s.astype(np.float32)).mean(2)[ring > 0].mean()) if prev_s is not None else 0.0
            if v > TH and v > 1.5*mv + 4: reasons.append(f"Cにじみ{v:.1f}")
    if reasons: bad.append(dict(f=i, t=round(i/fps, 2), n=k, why=reasons))
    prev_s = fs; i += 1
for c in (src, cln, out): c.release()
json.dump(bad, open(f"{W_}/residue.json", "w"), ensure_ascii=False)
pct = len(bad)/n*100
print(f"不良コマ {len(bad)}/{n} = {pct:.3f}%   合格ライン0.09%（{int(n*0.0009)}コマ）  {'✅' if pct <= 0.09 else '🔴'}")
from collections import Counter
print("  内訳:", dict(Counter(w[0] for b_ in bad for w in b_["why"])))
if cvals: print(f"  にじみの値（字の周りの元との差）: 中央値{np.median(cvals):.1f} / 90%点{np.percentile(cvals,90):.1f} / 最大{max(cvals):.1f}  しきい値{TH}")
seen = set(); pick = []
for b_ in sorted(bad, key=lambda b_: -max([float(w[4:]) for w in b_["why"] if w.startswith("C")] or [0])):
    if b_["n"] in seen: continue
    seen.add(b_["n"]); pick.append(b_)
    if len(pick) >= 12: break
if pick:
    cap = cv2.VideoCapture(OUT); cells = []
    for b_ in pick:
        cap.set(cv2.CAP_PROP_POS_FRAMES, b_["f"]); ok, f = cap.read(); L = layers.get(b_["n"])
        if L: x0, y0, x1, y1 = L["box"]; cy = (y0+y1)//2; crop = f[max(0, cy-260):cy+260, :]
        else: crop = f[300:820, :]
        crop = cv2.resize(crop, (360, int(crop.shape[0]*360/1080)))
        cv2.putText(crop, f"#{b_['n']} {b_['t']}s {' '.join(b_['why'])}", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2); cells.append(crop)
    h = max(c_.shape[0] for c_ in cells); cells = [np.vstack([c_, np.zeros((h-c_.shape[0], 360, 3), np.uint8)]) for c_ in cells]
    rows = [np.hstack(cells[j:j+4]) for j in range(0, len(cells), 4)]; w = max(r.shape[1] for r in rows)
    rows = [np.hstack([r, np.zeros((r.shape[0], w-r.shape[1], 3), np.uint8)]) for r in rows]
    cv2.imwrite(f"{W_}/residue_worst.png", np.vstack(rows)); print(f"→ {W_}/residue_worst.png")
