#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元テロップを ProPainter（動画AIの穴埋め・VMake相当の公開コード）で消す。**このMac（Apple GPU=MPS）で回す。鍵も外部も要らん。**
使い方: 08_propainter_local.py <作業フォルダ> [カット割り.csv] [--dry] [--only 1,3] [--sub 40]
要る物: <作業フォルダ>/src.mp4・mask.mp4（白＝消す・同じコマ数）、~/tools/ProPainter（.venv と weights/ 入り）
やること:
 1. カット単位に分ける（カット跨ぎで流れの推定が壊れる）。消す字が無いカットは飛ばす
 2. 🔑 メモリ対策：画面全体やなく、**字の周りの横帯だけ切り出して**AIに渡す（元の解像度のまま・処理量1/3）
 3. 返ってきたコマは**マスク＋6pxの中だけ**元に貼り戻す（外は元画質のまま）→ pp/cutNN.mp4
 4. 全編に組む → clean_pp.mp4。途中で落ちても pp/cutNN.mp4 から再開"""
import cv2, numpy as np, csv, json, os, sys, subprocess, time, shutil, glob
W_ = os.path.abspath(sys.argv[1]); CUTS = next((a for a in sys.argv[2:] if a.endswith(".csv")), None)
DRY = "--dry" in sys.argv; ONLY = None
if "--only" in sys.argv: ONLY = {int(x) for x in sys.argv[sys.argv.index("--only")+1].split(",")}
SUB = int(sys.argv[sys.argv.index("--sub")+1]) if "--sub" in sys.argv else 30
SCALE = 0.5        # 🔴 16GBのMacの実測：元の大きさ＝メモリ溢れ／半分＝30コマ36秒・0.4GB・見た目は4分の3と差なし
SRC, MSK = f"{W_}/src.mp4", f"{W_}/mask.mp4"; PP = f"{W_}/pp"; os.makedirs(PP, exist_ok=True)
PPD = os.path.expanduser("~/tools/ProPainter"); PY = f"{PPD}/.venv/bin/python"
DIL = 6; PAD = 8; MARGIN = 110      # 貼り戻し幅／カット前後の余分コマ／字の上下に足す文脈（px・720幅基準）

cap = cv2.VideoCapture(SRC); N = int(cap.get(7)); FPS = cap.get(5); W = int(cap.get(3)); H = int(cap.get(4)); cap.release()
if CUTS:
    rows = list(csv.reader(open(CUTS, encoding="utf-8-sig")))[1:]
    bounds = sorted({int(round(float(r[1])*FPS)) for r in rows} | {0, N})
else: bounds = [0, N]
cuts = [(bounds[i], bounds[i+1]) for i in range(len(bounds)-1) if bounds[i+1] > bounds[i]]
merged = []
for a, b in cuts:
    if merged and merged[-1][1]-merged[-1][0] < 10: merged[-1] = (merged[-1][0], b)
    else: merged.append((a, b))
cuts = merged
# 各コマのマスク：白の画素数と上下端
mc = cv2.VideoCapture(MSK); has = np.zeros(N, np.int64); ymin = np.full(N, H); ymax = np.zeros(N)
for i in range(N):
    ok, m = mc.read()
    if not ok: break
    mm = m[:, :, 0] > 127; has[i] = int(mm.sum())
    if has[i]: ys = np.where(mm.any(1))[0]; ymin[i] = ys[0]; ymax[i] = ys[-1]
mc.release()
jobs = []
for k, (a, b) in enumerate(cuts, 1):
    if has[a:b].sum() == 0: continue
    y0 = max(0, int(ymin[a:b].min()) - MARGIN); y1 = min(H, int(ymax[a:b].max()) + MARGIN)
    y0 -= y0 % 8; y1 += (8 - y1 % 8) % 8; y1 = min(H, y1)            # 8の倍数に
    jobs.append((k, a, b, y0, y1))
print(f"カット {len(cuts)}本 / 消す字があるのは {len(jobs)}本 / コマ {sum(b-a for _, a, b, *_ in jobs)}")
if DRY:
    for k, a, b, y0, y1 in jobs: print(f"  カット{k:>2} コマ{a}-{b} ({(b-a)/FPS:.1f}s) 切り出し y{y0}-{y1} (高さ{y1-y0})")
    sys.exit()

def run_one(k, a, b, y0, y1):
    out = f"{PP}/cut{k:02d}.mp4"
    if os.path.exists(out): return out
    a2, b2 = max(0, a-PAD), min(N, b+PAD); d = f"{PP}/cut{k:02d}"; fd, md = f"{d}/frames", f"{d}/masks"
    shutil.rmtree(d, ignore_errors=True); os.makedirs(fd); os.makedirs(md)
    cs, cm = cv2.VideoCapture(SRC), cv2.VideoCapture(MSK); cs.set(1, a2); cm.set(1, a2)
    for i in range(a2, b2):
        _, fs = cs.read(); _, fm = cm.read()
        cv2.imwrite(f"{fd}/{i-a2:05d}.png", fs[y0:y1]); cv2.imwrite(f"{md}/{i-a2:05d}.png", (fm[y0:y1, :, 0] > 127).astype(np.uint8)*255)
    cs.release(); cm.release()
    t0 = time.time()
    env = dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK="1")
    pw, ph = int(W*SCALE)//8*8, int((y1-y0)*SCALE)//8*8
    r = subprocess.run(["nice", "-n", "19", PY, "inference_propainter.py", "--video", fd, "--mask", md, "--output", d, "--fp16", "--subvideo_length", str(SUB),
                        "--width", str(pw), "--height", str(ph),
                        "--neighbor_length", "10", "--ref_stride", "10", "--mask_dilation", "4", "--save_frames", "--save_fps", "30"],
                       cwd=PPD, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  🔴 失敗:\n{r.stderr[-1500:]}"); return None
    outs = sorted(glob.glob(f"{d}/frames/frames/*.png")) or sorted(glob.glob(f"{d}/*/frames/*.png"))
    if len(outs) != b2-a2: print(f"  🔴 返ってきたコマ {len(outs)} ≠ {b2-a2}"); return None
    # マスクの中だけ貼り戻す
    cs, cm = cv2.VideoCapture(SRC), cv2.VideoCapture(MSK); cs.set(1, a2); cm.set(1, a2)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    K = np.ones((2*DIL+1, 2*DIL+1), np.uint8)
    for i in range(a2, b2):
        _, fs = cs.read(); _, fm = cm.read()
        if a <= i < b:
            fr = cv2.imread(outs[i-a2]); full = fs.copy()
            if fr.shape[:2] != (y1-y0, W): fr = cv2.resize(fr, (W, y1-y0), interpolation=cv2.INTER_CUBIC)
            full[y0:y1] = fr
            m = cv2.dilate((fm[:, :, 0] > 127).astype(np.uint8)*255, K)
            m = cv2.GaussianBlur(m, (7, 7), 0).astype(np.float32)[:, :, None]/255.0
            f = fs.astype(np.float32)*(1-m) + full.astype(np.float32)*m
            enc.stdin.write(np.clip(f, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close(); enc.wait(); cs.release(); cm.release()
    shutil.rmtree(d, ignore_errors=True)
    print(f"  ✅ {time.time()-t0:.0f}秒（{(time.time()-t0)/(b2-a2):.2f}秒/コマ）", flush=True)
    return out

done = {}
for k, a, b, y0, y1 in jobs:
    if ONLY and k not in ONLY: continue
    print(f"カット{k:>2} コマ{a}-{b} ({(b-a)/FPS:.1f}s) 高さ{y1-y0}", flush=True)
    r = run_one(k, a, b, y0, y1)
    if r: done[k] = (a, b, r)
if not ONLY:
    outp = f"{W_}/clean_pp.mp4"; cs = cv2.VideoCapture(SRC)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p", outp], stdin=subprocess.PIPE)
    seg = {a: (b, r) for a, b, r in done.values()}; i = 0; cr = None; cb = -1
    while True:
        ok, f = cs.read()
        if not ok: break
        if i in seg: cb, r = seg[i]; cr = cv2.VideoCapture(r)
        if cr is not None and i < cb:
            ok2, g = cr.read()
            if ok2: f = g
        else: cr = None
        enc.stdin.write(f.tobytes()); i += 1
    enc.stdin.close(); enc.wait()
    print(f"→ {outp}  コマ {i}/{N}  消したカット {len(done)}/{len(jobs)}")
