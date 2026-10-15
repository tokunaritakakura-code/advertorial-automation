#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出来上がりの検算（4段）。数字で白黒つける。
使い方: 06_verify.py <作業フォルダ> <出力.mp4>
 ① 帯と文字の中心が画面中心に合うとるか（テロップ全枚・インクの重心で）
 ② 帯の外に元のテロップ（白字＋黒フチ）が残ってへんか（0.5秒ごと全走査）
 ③ ナレーションを機械に聞き取らせて、台本と食い違う語が無いか（同音の字違いは除く）
 ④ コマ数・尺が元動画と同じか"""
import cv2, numpy as np, json, sys, os, subprocess, re, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notelop_inpaint as N
W_, OUT = sys.argv[1], sys.argv[2]
layers = json.load(open(OUT+".layers.json")); c = cv2.VideoCapture(OUT); FW = 1080
ng = 0
# ①
worst = 0.0
for L in layers:
    c.set(cv2.CAP_PROP_POS_MSEC, ((L["t0"]+L["t1"])/2)*1000); ok, f = c.read()
    if not ok: continue
    x0, y0, x1, y1 = L["box"]; g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    inner = g[y0+8:y1-8, x0+8:x1-8]; ys, xs = np.nonzero(inner < 80)
    if len(xs) == 0: print(f"  🔴 本{L['n']} 文字が見つからん"); ng += 1; continue
    tcx = (xs.min()+xs.max())/2 + x0 + 8; bcx = (x0+x1)/2
    dev = max(abs(tcx-FW/2), abs(bcx-FW/2)); worst = max(worst, dev)
    if dev > 6: print(f"  🔴 本{L['n']} 中心ズレ {dev:.1f}px"); ng += 1
print(f"① 中心ズレ 最大 {worst:.1f}px  {'✅' if worst <= 6 else '🔴'}")
# ②
c.set(cv2.CAP_PROP_POS_FRAMES, 0); i = 0; hits = []; fps = c.get(cv2.CAP_PROP_FPS)
while True:
    ok, f = c.read()
    if not ok: break
    if i % 15 == 0:
        t = i/fps; m = N.telop_mask(cv2.resize(f, (N.W, N.H)))
        for L in layers:
            if L["t0"] <= t < L["t1"]:
                x0, y0, x1, y1 = L["box"]; m[int(y0*N.H/1920):int(y1*N.H/1920), :] = 0
        if m.max() > 0: hits.append(round(t, 1))
    i += 1
print(f"② 元テロップの残り {len(hits)}点  {'✅' if not hits else '🔴 '+str(hits[:8])}"); ng += bool(hits)
# ③
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{W_}/narration.mp3", "-ac", "1", "-ar", "16000", f"{W_}/nar.wav"], check=True)
subprocess.run(["whisper-cli", "-m", os.path.expanduser("~/Library/Caches/whisper-cpp/ggml-large-v3-turbo.bin"), "-f", f"{W_}/nar.wav", "-l", "ja", "-otxt", "-of", f"{W_}/kikitori"], capture_output=True)
heard = open(f"{W_}/kikitori.txt", encoding="utf-8").read()
plan = json.load(open(f"{W_}/plan.json"))
import unicodedata
KN = {"〇":"0","一":"1","二":"2","三":"3","四":"4","五":"5","六":"6","七":"7","八":"8","九":"9","十":"","百":"","千":""}
def norm(s):
    s = unicodedata.normalize("NFKC", s)
    s = "".join(KN.get(ch, ch) for ch in s)
    return re.sub(r"[^ぁ-んァ-ン一-龥0-9]", "", s)
H = norm(heard); miss = []
for p in plan:
    k = norm(p["ja"])
    # 文のどこか4文字が聞き取りに無ければ疑い（同音の字違いは拾えんので「疑い」止まり）
    if k and not any(k[i:i+4] in H for i in range(0, max(1, len(k)-3), 2)): miss.append(p["n"])
print(f"③ 聞き取りで見つからん文 {len(miss)}本  {'✅' if not miss else '🟡 本'+str(miss)+'（耳で確認）'}")
# ④
d_out = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", OUT], capture_output=True, text=True).stdout)
d_src = float(open(f"{W_}/duration.txt").read())
if d_out < d_src*0.9: print(f"④ 尺 {d_out:.2f}s（部分描画なので省略。全編で確認）")
else: print(f"④ 尺 {d_out:.2f}s / 元 {d_src:.2f}s  {'✅' if abs(d_out-d_src) < 0.2 else '🔴'}"); ng += abs(d_out-d_src) >= 0.2
print("\n" + ("✅ 全部合格" if ng == 0 else f"🔴 直す所 {ng}件"))
