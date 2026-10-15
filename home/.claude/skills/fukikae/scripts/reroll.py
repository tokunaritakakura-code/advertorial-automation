#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ブロックを「枠に収まる」かつ「誤読が無い」まで振り直す。
🔴 長さだけで採ったらアカン（発音が転けた回を採ってまう。2026-09-04実測）。
使い方: reroll.py <作業フォルダ> <no,no,...> [--tries 5]
"""
import csv,subprocess,sys,os,shutil,argparse,re
os.makedirs(sys.argv[1]+"/hear",exist_ok=True) if len(sys.argv)>1 else None
NG = ["サンマリオン","サンマル用","サンバリオン","サンミャル","変形","みゃくわ","ミヤクア","ミヤクワ","ニャクワ","ミャクア","脈","メコ","シール","ジェンゾー","掛け底","ニャクワ","にゃくわ","ニャクア―","ワクワ","わくわ","枠輪","枠が","ワークワ","ワック・ワ","湧くわ","バナ","もまった","しずいれ","高評","交渉","死女","多効"]
def dur(p): return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p],capture_output=True,text=True).stdout)
def hear(W,n):
    w=f"{W}/hear/r{n}.wav"
    subprocess.run(["ffmpeg","-v","error","-y","-i",f"{W}/seg/{int(n):02d}.mp3","-ar","16000","-ac","1",w],check=True)
    subprocess.run(["whisper-cli","-m",os.path.expanduser("~/.cache/whisper/ggml-large-v3-turbo.bin"),
                    "-f",w,"-l","ja","-otxt","-of",f"{W}/hear/r{n}"],capture_output=True)
    return open(f"{W}/hear/r{n}.txt",encoding="utf-8").read().replace("\n","")
a=argparse.ArgumentParser(); a.add_argument("work"); a.add_argument("nos"); a.add_argument("--tries",type=int,default=5)
o=a.parse_args(); W=o.work
rows=list(csv.DictReader(open(W+"/script.csv",encoding="utf-8")))
lim={}
for i,r in enumerate(rows):
    s,e=float(r["start"]),float(r["end"])
    nxt=float(rows[i+1]["start"]) if i+1<len(rows) else e+0.25
    lim[r["no"]]=min(e,nxt-0.25)-s
for n in o.nos.split(","):
    ok=None; best=None
    for k in range(o.tries):
        r=subprocess.run(["python3",os.path.expanduser("~/bin/eltts.py"),W,W+"/script.csv","--only",n,"--stability","0.5","--take",str(k+1)],capture_output=True,text=True)
        if r.returncode: sys.exit("eltts.py が落ちた: "+r.stderr[-300:])
        p=f"{W}/seg/{int(n):02d}.mp3"; d=dur(p); txt=hear(W,n)
        bad=[g for g in NG if g in txt]
        mark = "🔴誤読:"+"・".join(bad) if bad else ("✅" if d<=lim[n] else "…長い")
        print(f"  文{n} 試行{k+1}: {d:.2f}秒/{lim[n]:.2f}秒 {mark}")
        if not bad and (best is None or d<best[0]):
            best=(d,f"{W}/seg/{int(n):02d}_b.mp3"); shutil.copy(p,best[1])
        if not bad and d<=lim[n]: ok=True; break
    if best: shutil.move(best[1],f"{W}/seg/{int(n):02d}.mp3")
    print(f"文{n} → 採用 {best[0]:.2f}秒 {'✅' if ok else '⚠️確認要'}" if best else f"文{n} 🔴 全部誤読")
