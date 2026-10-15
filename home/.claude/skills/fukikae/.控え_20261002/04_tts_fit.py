#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日本語台本（no,start,end,ja）を1文ずつ Fish Audio で読ませ、枠に収め、1本の音声にする。
→ work/seg*.mp3, work/narration.mp3, work/plan.json
使い方: 04_tts_fit.py <作業フォルダ> <台本.csv> [--breath 0.2] [--maxspeed 1.0]
鉄則: 速くして収めん（既定 maxspeed=1.0）。はみ出す文は台本の言い回しを締めて出し直す。
      前の文が終わってから次を始める「流し置き」で、余裕のある文が吸収する。"""
import csv, subprocess, os, json, sys, argparse
ap = argparse.ArgumentParser(); ap.add_argument("work"); ap.add_argument("script")
ap.add_argument("--breath", type=float, default=0.2); ap.add_argument("--maxspeed", type=float, default=1.0)
ap.add_argument("--only", default="")   # 例 "3,7,12" その文だけ作り直す
a = ap.parse_args(); W = a.work
F = os.path.expanduser("~/bin/fishtts.py")
def dur(p): return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout)
total = float(open(f"{W}/duration.txt").read())
rows = list(csv.DictReader(open(a.script, encoding="utf-8")))
only = {int(x) for x in a.only.split(",") if x}
old = {p["n"]: p for p in json.load(open(f"{W}/plan.json"))} if os.path.exists(f"{W}/plan.json") else {}
plan = []
for r in rows:
    n = int(r["no"]); st, en = float(r["start"]), float(r["end"]); slot = en-st; out = f"{W}/seg{n:02d}.mp3"
    if only and n not in only and n in old and os.path.exists(out):
        plan.append(old[n]); continue
    best = None
    for sp in ([1.0] if a.maxspeed <= 1.0 else [1.0, min(a.maxspeed, 1.1), a.maxspeed]):
        subprocess.run([F, r["ja"], f"{W}/tmp.mp3", "--speed", str(sp)], check=True, capture_output=True); d = dur(f"{W}/tmp.mp3")
        if best is None or d < best[0]: best = (d, sp); os.replace(f"{W}/tmp.mp3", out)
        if d <= slot: break
    plan.append(dict(n=n, start=st, slot=slot, dur=best[0], speed=best[1], ja=r["ja"]))
    print(f"  {n:>2}  枠{slot:>5.2f}s  音声{best[0]:>5.2f}s  {'✅' if best[0] <= slot+0.2 else f'🔴 {best[0]-slot:+.2f}s（言い回しを締める）'}")
# 流し置き
t_prev = 0.0; places = []; mx = 0
for p in plan:
    stt = max(p["start"], t_prev + a.breath); mx = max(mx, stt-p["start"]); p["placed"] = round(stt, 3); places.append((p["n"], stt)); t_prev = stt + p["dur"]
json.dump(plan, open(f"{W}/plan.json", "w"), ensure_ascii=False, indent=0)
print(f"\n最後の文が終わる {t_prev:.1f}s / 動画 {total:.1f}s  {'✅' if t_prev <= total else '🔴 終盤の文を締める'}   元の秒からのズレ最大 {mx:+.2f}s")
inputs = ["-f", "lavfi", "-t", str(total), "-i", "anullsrc=r=44100:cl=mono"]; fc = []
for i, (n, stt) in enumerate(places, 1):
    inputs += ["-i", f"{W}/seg{n:02d}.mp3"]; fc.append(f"[{i}:a]adelay={int(stt*1000)}|{int(stt*1000)}[s{i}]")
mix = "[0:a]" + "".join(f"[s{i}]" for i in range(1, len(places)+1)) + f"amix=inputs={len(places)+1}:normalize=0[out]"
subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", ";".join(fc)+";"+mix, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", f"{W}/narration.mp3"], check=True)
print(f"→ {W}/narration.mp3")
