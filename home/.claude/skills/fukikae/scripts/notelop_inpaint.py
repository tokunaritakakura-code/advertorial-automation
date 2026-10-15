#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本家の広告からテロップを1コマずつ見つけて塗り直す（研究用）。

見つけ方＝「真っ白な字」＋「そのすぐ外に黒いフチがある」の2条件。
イラストの白い毛や白い壁はフチが無いので引っかからん。
白い字やない物（壁の看板・半透明の大カード・Trustpilot）は手で箱を置く。
"""
import cv2, numpy as np

W, H = 720, 1280
BAND = (150, 950)          # テロップが出る帯（この外は見に行かん）

# 白い字やない物＝手で置く箱 (t0, t1, x0, y0, x1, y1, 名前)
MANUAL = [
    ( 9.83, 13.13,   0,  78, 356, 538, "壁の看板"),
    (96.20,100.60, 243, 143, 719, 357, "大カード 600,000+"),
    (98.20,100.60, 455,1035, 719,1275, "Trustpilot"),
    (156.00,157.76,233, 118, 719, 358, "大カード Get Yours Today!"),
    # #1 #2 #3 の番号カード＝字が短すぎて自動では拾えん
    (74.05, 75.30, 272, 250, 432, 328, "#1"),
    (80.30, 81.45, 300, 250, 420, 328, "#2"),
    (87.60, 88.70, 300, 250, 420, 328, "#3"),
]

def telop_mask(bgr):
    """真っ白＋黒フチ の所だけ True を返す"""
    b, g, r = bgr[:, :, 0].astype(np.int16), bgr[:, :, 1].astype(np.int16), bgr[:, :, 2].astype(np.int16)
    mx = np.maximum(np.maximum(b, g), r); mn = np.minimum(np.minimum(b, g), r)
    white = (mx > 246) & ((mx - mn) < 12)   # 本物の白だけ。猫のクリーム色の口元は外れる
    dark  = (mx < 115)
    band = np.zeros((H, W), bool); band[BAND[0]:BAND[1]] = True
    white &= band

    m = (white.astype(np.uint8)) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    # 黒フチが周りにある塊だけ残す
    darku = (dark.astype(np.uint8)) * 255
    dark_near = cv2.dilate(darku, np.ones((17, 17), np.uint8)) > 0
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros((H, W), np.uint8)
    cand = []
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if a < 40 or a > 60000:
            continue
        # 字の形やない物を落とす：細長すぎ／薄すぎ（シンクの縁・水の光など）
        if bh < 8 or bh > 95 or bw > 480:
            continue
        if bw > 8 * bh or bh > 8 * bw:
            continue
        if a < 0.16 * bw * bh:
            continue
        comp = lab == i
        if dark_near[comp].mean() > 0.55:      # 塊の大半が黒フチに囲まれとる
            cand.append((i, stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP], bw, bh))

    # 🔑 字は「横一列に並ぶ」。ポツンと1個だけの白い塊（毛・光）は字やない
    rows = []
    for c in sorted(cand, key=lambda z: z[2] + z[4] / 2):
        cy = c[2] + c[4] / 2
        for r in rows:
            ry0 = min(x[2] for x in r); ry1 = max(x[2] + x[4] for x in r)
            if ry0 - 6 <= cy <= ry1 + 6:
                r.append(c); break
        else:
            rows.append([c])

    def span_of(r):
        return max(x[1] + x[3] for x in r) - min(x[1] for x in r)

    ok = []
    for r in rows:
        inkw = sum(x[3] for x in r)
        ok.append(span_of(r) >= 130 and (len(r) >= 4 or inkw >= 120))

    # 🔑 2行目・3行目は短いことがある。合格した行のすぐ上下にある行は道連れで残す
    for _ in range(4):
        for i, r in enumerate(rows):
            if ok[i] or span_of(r) < 60:
                continue
            cy = sum(x[2] + x[4] / 2 for x in r) / len(r)
            for j, r2 in enumerate(rows):
                if not ok[j]:
                    continue
                cy2 = sum(x[2] + x[4] / 2 for x in r2) / len(r2)
                if abs(cy - cy2) < 110:
                    ok[i] = True; break

    for i, r in enumerate(rows):
        if not ok[i]:
            continue
        for c in r:
            keep[lab == c[0]] = 255
    return keep

def full_mask(bgr, t):
    m = telop_mask(bgr)
    m = cv2.dilate(m, np.ones((21, 21), np.uint8))     # 黒いフチごと覆う
    for t0, t1, x0, y0, x1, y1, _ in MANUAL:
        if t0 <= t <= t1:
            m[y0:y1, x0:x1] = 255
    return m

def clean(bgr, t):
    m = full_mask(bgr, t)
    if m.max() == 0:
        return bgr
    out = cv2.inpaint(bgr, m, 9, cv2.INPAINT_TELEA)
    # 塗った跡の構造を消す：マスクの内側だけ軽くぼかして戻す
    soft = cv2.GaussianBlur(out, (0, 0), 3.0)
    inner = cv2.erode(m, np.ones((5, 5), np.uint8))
    a = (cv2.GaussianBlur(inner, (0, 0), 3.0).astype(np.float32) / 255.0)[:, :, None]
    return (out * (1 - a) + soft * a).astype(np.uint8)
