#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元テロップを ProPainter（動画AIの穴埋め・VMake相当の公開コード）で消す。Replicate の GPU で回す。
使い方: 08_propainter.py <作業フォルダ> [カット割り.csv] [--dry] [--only 3,7]
要る物: <作業フォルダ>/src.mp4・mask.mp4（白＝消す・同じコマ数）、キーチェーン `replicate-api`
やること:
 1. カット単位に分ける（カット跨ぎで流れの推定が壊れるのを防ぐ）。消す字が無いカットは投げん
 2. 1カットずつ Replicate に投げて、返ってきた映像は**マスクの中だけ**元映像に貼り戻す（外は元の画質のまま）
 3. → clean_pp.mp4（全編・元と同じコマ数）。途中で落ちても pp/ に残った分から再開できる
費用の目安: L40S $0.000975/秒。1カット数十秒〜数分。"""
import cv2, numpy as np, csv, json, os, sys, subprocess, time, requests
W_ = sys.argv[1]; CUTS = next((a for a in sys.argv[2:] if a.endswith(".csv")), None)
DRY = "--dry" in sys.argv; ONLY = None
if "--only" in sys.argv: ONLY = {int(x) for x in sys.argv[sys.argv.index("--only")+1].split(",")}
SRC, MSK = f"{W_}/src.mp4", f"{W_}/mask.mp4"; PP = f"{W_}/pp"; os.makedirs(PP, exist_ok=True)
MODEL = "jd7h/propainter"; API = "https://api.replicate.com/v1"
DIL = 6            # 貼り戻す範囲＝マスク＋この幅（ProPainter側の mask_dilation と同じくらい）
PAD = 8            # カットの前後にこれだけ余分に渡す（端のコマの参照用）。貼り戻しは本体のコマだけ

def key():
    return subprocess.run(["security", "find-generic-password", "-s", "replicate-api", "-w"], capture_output=True, text=True, check=True).stdout.strip()
def hdr(): return {"Authorization": f"Bearer {key()}", "Content-Type": "application/json"}

cap = cv2.VideoCapture(SRC); N = int(cap.get(7)); FPS = cap.get(5); W = int(cap.get(3)); H = int(cap.get(4)); cap.release()
# カット境界（コマ番号）
if CUTS:
    rows = list(csv.reader(open(CUTS, encoding="utf-8-sig")))[1:]
    bounds = sorted({int(round(float(r[1])*FPS)) for r in rows} | {0, N})
else:
    bounds = [0, N]
cuts = [(bounds[i], bounds[i+1]) for i in range(len(bounds)-1) if bounds[i+1] > bounds[i]]
merged = []                                    # 10コマ未満の切れ端は次のカットにくっつける（境界の取り違え対策）
for a, b in cuts:
    if merged and merged[-1][1]-merged[-1][0] < 10: merged[-1] = (merged[-1][0], b)
    else: merged.append((a, b))
cuts = merged

# 各カットにマスクがあるか（白の画素数）
mc = cv2.VideoCapture(MSK); has = np.zeros(N, np.int64)
for i in range(N):
    ok, m = mc.read()
    if not ok: break
    has[i] = int((m[:, :, 0] > 127).sum())
mc.release()
jobs = [(k+1, a, b) for k, (a, b) in enumerate(cuts) if has[a:b].sum() > 0]
print(f"カット {len(cuts)}本 / 消す字があるのは {len(jobs)}本 / コマ {sum(b-a for _, a, b in jobs)}")
if DRY:
    for k, a, b in jobs: print(f"  カット{k:>2} コマ{a}-{b} ({(b-a)/FPS:.1f}s) 白{has[a:b].max()}px")
    sys.exit()

def write_chunk(src, a, b, path):
    c = cv2.VideoCapture(src); c.set(cv2.CAP_PROP_POS_FRAMES, a)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
    for i in range(a, b):
        ok, f = c.read()
        if not ok: break
        enc.stdin.write(f.tobytes())
    enc.stdin.close(); enc.wait(); c.release()

def upload(path):
    with open(path, "rb") as f:
        r = requests.post(f"{API}/files", headers={"Authorization": f"Bearer {key()}"}, files={"content": (os.path.basename(path), f, "video/mp4")})
    r.raise_for_status(); return r.json()["urls"]["get"]

def run_one(k, a, b):
    out = f"{PP}/cut{k:02d}.mp4"
    if os.path.exists(out): return out
    a2, b2 = max(0, a-PAD), min(N, b+PAD)
    vin, min_ = f"{PP}/in{k:02d}.mp4", f"{PP}/mask{k:02d}.mp4"
    write_chunk(SRC, a2, b2, vin); write_chunk(MSK, a2, b2, min_)
    vurl, murl = upload(vin), upload(min_)
    body = {"input": dict(video=vurl, mask=murl, mode="video_inpainting", fp16=True, mask_dilation=4, ref_stride=10, neighbor_length=10, subvideo_length=80, raft_iter=20)}
    r = requests.post(f"{API}/models/{MODEL}/predictions", headers=hdr(), json=body); r.raise_for_status(); p = r.json()
    t0 = time.time()
    while p["status"] not in ("succeeded", "failed", "canceled"):
        time.sleep(5); p = requests.get(p["urls"]["get"], headers=hdr()).json()
    if p["status"] != "succeeded":
        print(f"  🔴 カット{k} 失敗: {str(p.get('error'))[:300]}"); return None
    url = p["output"] if isinstance(p["output"], str) else p["output"][0]
    raw = f"{PP}/raw{k:02d}.mp4"
    open(raw, "wb").write(requests.get(url).content)
    # マスクの中だけ貼り戻す（コマ数・大きさを元に合わせる）
    cs, cm, cr = cv2.VideoCapture(SRC), cv2.VideoCapture(MSK), cv2.VideoCapture(raw)
    cs.set(cv2.CAP_PROP_POS_FRAMES, a2); cm.set(cv2.CAP_PROP_POS_FRAMES, a2)
    nr = int(cr.get(7)); print(f"  返ってきたコマ {nr} / 渡した {b2-a2}", end="")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    K = np.ones((2*DIL+1, 2*DIL+1), np.uint8)
    for i in range(a2, b2):
        ok1, fs = cs.read(); ok2, fm = cm.read(); ok3, fr = cr.read()
        if not ok3: fr = fs
        if fr.shape[:2] != (H, W): fr = cv2.resize(fr, (W, H))
        if a <= i < b:
            m = cv2.dilate((fm[:, :, 0] > 127).astype(np.uint8)*255, K)
            m = cv2.GaussianBlur(m, (7, 7), 0).astype(np.float32)[:, :, None]/255.0
            f = fs.astype(np.float32)*(1-m) + fr.astype(np.float32)*m
            enc.stdin.write(np.clip(f, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close(); enc.wait(); [c.release() for c in (cs, cm, cr)]
    print(f"  ✅ {time.time()-t0:.0f}秒  金額目安 ${p.get('metrics', {}).get('predict_time', 0)*0.000975:.3f}")
    return out

done = {}
for k, a, b in jobs:
    if ONLY and k not in ONLY: continue
    print(f"カット{k:>2} コマ{a}-{b} ({(b-a)/FPS:.1f}s)", flush=True)
    r = run_one(k, a, b)
    if r: done[k] = (a, b, r)
json.dump({k: v[:2] for k, v in done.items()}, open(f"{PP}/done.json", "w"))

# 全編に組む：処理したカットは pp/cutNN.mp4、それ以外は元のまま
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
