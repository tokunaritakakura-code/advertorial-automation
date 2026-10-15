#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日本語テロップ（白い帯＋黒文字）を、テロップ消し済みの映像に重ねて、ナレーションも乗せる。
使い方: 05_render_telops.py <作業フォルダ> <テロップ.csv(n,ja[,card])> <出力.mp4> [開始秒 終了秒]

v2（2026-09-03）: 位置と時間は whisper の文やなく、元テロップの**1コマ単位の実測**（telop_intervals.json）に合わせる。
 帯の大きさ＝「文字＋余白」と「元テロップの箱＋余白」の大きい方 → 消し跡を帯が必ず覆う（尾を出さん）。
 card=1 の行は大きい字（カード）。
帯の数字はスクショ実測: 白252・角の丸み=帯の高さの10%・文字72px（カード104px）・黒26・余白x48/y30
改行は「／」で意味の塊ごとに手で入れる。"""
import cv2, numpy as np, csv, json, os, sys, subprocess
from PIL import Image, ImageDraw, ImageFont
W_, script, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
t0 = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0; t1 = float(sys.argv[5]) if len(sys.argv) > 5 else 9999
BASE = f"{W_}/clean.mp4"; NARR = f"{W_}/narration.mp3"
FONT = os.environ.get("TELOP_FONT", os.path.expanduser("~/Library/Fonts/Corporate-Logo-Bold-ver3.otf"))
W, H, FPS = 1080, 1920, 30
SIZE, CARD_SIZE, PAD_X, PAD_Y, LINE_GAP, RADIUS = 72, 104, 48, 30, 14, 0.10
COVER_MARGIN = 16          # 元テロップの字の箱の外にこれだけ余分に覆う（1080換算）。消し跡の縁は「消しを丁寧にする」で潰す
BAND, INK = (252, 252, 252), (26, 25, 25); MAXW = W   # 英語が幅広の枚だけ帯も広がる
SX, SY = W/720, H/1280      # 実測の箱（720x1280）→1080x1920
iv = json.load(open(f"{W_}/telop_intervals.json"))
rows = {int(r["n"]): r for r in csv.DictReader(open(script, encoding="utf-8"))}
def make_layer(text, box, card):
    font = ImageFont.truetype(FONT, CARD_SIZE if card else SIZE)
    lines = text.split("／"); tmp = ImageDraw.Draw(Image.new("L", (10, 10))); ws = []; hs = []; bbs = []
    for ln in lines:
        b = tmp.textbbox((0, 0), ln, font=font); bbs.append(b); ws.append(b[2]-b[0]); hs.append(b[3]-b[1])
    tw = max(ws); th = sum(hs) + LINE_GAP*(len(lines)-1)
    # 文字に合わせた帯
    bw = tw + PAD_X*2; bh = th + PAD_Y*2
    ex0, ey0, ex1, ey1 = box["x0"]*SX - COVER_MARGIN, box["y0"]*SY - COVER_MARGIN, box["x1"]*SX + COVER_MARGIN, box["y1"]*SY + COVER_MARGIN
    ex0, ex1 = max(0, ex0), min(W, ex1); ey0, ey1 = max(0, ey0), min(H, ey1)   # 画面の外は覆わんでええ
    ecx, ecy = (ex0+ex1)/2, (ey0+ey1)/2
    # 元テロップの箱も覆う：幅は画面中心基準で左右対称に、高さは箱の中心を基準に
    need_w = 2*max(W/2 - ex0, ex1 - W/2); need_h = ey1 - ey0
    if card: need_w, need_h = 0, 0      # カードは元が右寄せ等で位置が違うので、帯は文字の大きさ（消しが綺麗なこと前提）
    bw = min(MAXW, max(bw, need_w)); bh = max(bh, need_h)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    bx0 = int((W-bw)/2); by0 = int(ecy - bh/2)
    d.rounded_rectangle([bx0, by0, bx0+int(bw), by0+int(bh)], radius=int(bh*RADIUS), fill=BAND+(255,))
    y = by0 + (bh - th)/2
    for ln, w_, h_, b in zip(lines, ws, hs, bbs):
        d.text(((W-w_)/2 - b[0], y - b[1]), ln, font=font, fill=INK+(255,)); y += h_ + LINE_GAP
    return layer, (bx0, by0, bx0+int(bw), by0+int(bh)), (int(ex0), int(ey0), int(ex1), int(ey1))
layers = []
for k, b in enumerate(iv, 1):
    r = rows.get(k)
    if not r or not r["ja"].strip() or b["t1"] < t0 or b["t0"] > t1: continue
    img, band, ebox = make_layer(r["ja"], b, bool(r.get("card", "").strip())); a = np.asarray(img).astype(np.float32)
    layers.append(dict(n=k, f0=b["f0"], f1=b["f1"], t0=b["t0"], t1=b["t1"], rgb=a[:, :, :3][:, :, ::-1], al=a[:, :, 3:4]/255.0, box=band, ebox=ebox))
print(f"テロップ {len(layers)}枚", flush=True)
cap = cv2.VideoCapture(BASE); sfps = cap.get(cv2.CAP_PROP_FPS)
i0 = int(round(t0*sfps)); i1 = min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), int(round(t1*sfps))); cap.set(cv2.CAP_PROP_POS_FRAMES, i0)
tmp = OUT + ".v.mp4"
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                        "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
for i in range(i0, i1):
    ok, f = cap.read()
    if not ok: break
    f = cv2.resize(f, (W, H)).astype(np.float32)
    for L in layers:
        if L["f0"] <= i <= L["f1"]: f = f*(1-L["al"]) + L["rgb"]*L["al"]
    enc.stdin.write(np.clip(f, 0, 255).astype(np.uint8).tobytes())
enc.stdin.close(); enc.wait(); cap.release()
dur = (i1-i0)/sfps
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t0), "-t", str(dur), "-i", NARR, "-i", tmp, "-map", "1:v", "-map", "0:a", "-c:v", "copy", "-c:a", "aac", "-shortest", OUT], check=True)
os.remove(tmp)
json.dump([dict(n=L["n"], f0=L["f0"], f1=L["f1"], t0=L["t0"], t1=L["t1"], box=L["box"], ebox=L["ebox"]) for L in layers], open(OUT+".layers.json", "w"))
# 覆い漏れの検算：元テロップの箱（＋余白）が帯からはみ出とるコマ
leak = sum(1 for L in layers if not (L["box"][0] <= L["ebox"][0] and L["box"][1] <= L["ebox"][1] and L["box"][2] >= L["ebox"][2] and L["box"][3] >= L["ebox"][3]))
print(f"→ {OUT}   帯が元テロップを覆いきれてへん枚数 {leak}（0が合格）")
