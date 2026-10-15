#!/usr/bin/env python3
"""動画から「見て意味がある画面」だけを抜く。

字幕だけだと、広告のレイアウト・LPの見た目・画面共有の中身が丸ごと落ちる。
かといって全フレームを見るのは論外（1本で数万枚）。だから3段で絞る。

  1. ffmpeg の場面変化検出で候補を出す（喋りの切れ目ではなく、画面が変わった所）
  2. 知覚ハッシュで重複を落とす（同じスライドが何度も出るのを1枚にする）
  3. 文字らしさ（エッジの多さ）で並べ替え、上位N枚だけ残す
     → スライドや画面共有が優先され、話者の顔だけの絵は後回しになる

使い方:
  frames.py <動画> --out DIR [--max 16] [--scene 0.30] [--every 0]

出力: DIR/f<通し番号>_<秒数>.jpg と frames.json（各フレームの秒数と採用理由）
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


def die(msg, code=2):
    print(f"FRAMES_FAILED: {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd, timeout=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def dhash(path, size=8):
    """知覚ハッシュ。同じスライドを2枚持たないために使う。"""
    from PIL import Image
    img = Image.open(path).convert("L").resize((size + 1, size))
    px = list(img.getdata())
    bits = 0
    for r in range(size):
        for c in range(size):
            left = px[r * (size + 1) + c]
            right = px[r * (size + 1) + c + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a, b):
    return bin(a ^ b).count("1")


def textiness(path):
    """文字の多さの代理指標。隣り合う画素の差が大きいほど、文字や図が多い。
    顔のアップより、スライドや画面共有を上に持ってくるために使う。"""
    from PIL import Image, ImageFilter
    img = Image.open(path).convert("L").resize((320, 180))
    edges = img.filter(ImageFilter.FIND_EDGES)
    data = list(edges.getdata())
    strong = sum(1 for v in data if v > 40)
    return strong / len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max", type=int, default=16, help="残す枚数")
    ap.add_argument("--scene", type=float, default=0.30, help="場面変化のしきい値")
    ap.add_argument("--every", type=float, default=0,
                    help="秒数を指定すると、場面変化ではなく等間隔で取る")
    ap.add_argument("--min-hamming", type=int, default=6,
                    help="これ未満の差は同じ画面とみなす")
    a = ap.parse_args()

    if not os.path.exists(a.video):
        die(f"動画が無い: {a.video}")
    if not shutil.which("ffmpeg"):
        die("ffmpeg が無い")
    os.makedirs(a.out, exist_ok=True)

    work = tempfile.mkdtemp(prefix="frames-")
    try:
        vf = (f"fps=1/{a.every}" if a.every > 0
              else f"select='gt(scene,{a.scene})'")
        cmd = ["ffmpeg", "-y", "-i", a.video, "-vf", vf, "-vsync", "vfr",
               "-frame_pts", "1", "-q:v", "4",
               os.path.join(work, "c%05d.jpg"), "-loglevel", "error"]
        p = run(cmd, timeout=7200)
        cands = sorted(f for f in os.listdir(work) if f.endswith(".jpg"))

        if not cands and a.every == 0:
            # 場面変化が拾えない動画（ずっと同じ画面）は等間隔に切り替える
            print("場面変化が0件。等間隔（30秒）に切り替える", file=sys.stderr)
            run(["ffmpeg", "-y", "-i", a.video, "-vf", "fps=1/30", "-q:v", "4",
                 os.path.join(work, "c%05d.jpg"), "-loglevel", "error"], timeout=7200)
            cands = sorted(f for f in os.listdir(work) if f.endswith(".jpg"))

        if not cands:
            die(f"1枚も取れなかった。動画が壊れている可能性。ffmpeg: {p.stderr[-300:]}")

        # 動画の長さを取って、候補の位置を秒に直す
        dur = 0.0
        try:
            dur = float(run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of", "default=nw=1:nk=1",
                             a.video], timeout=120).stdout.strip())
        except Exception:
            pass

        scored = []
        for i, f in enumerate(cands):
            fp = os.path.join(work, f)
            try:
                scored.append({"file": fp, "hash": dhash(fp),
                               "text": textiness(fp),
                               "sec": (dur * i / max(1, len(cands) - 1)) if dur else 0})
            except Exception as e:
                print(f"読めない画像を飛ばす {f}: {e}", file=sys.stderr)

        if not scored:
            die("画像を1枚も読めなかった（Pillowの問題）")

        # 重複を落とす（時系列順に見て、直前までと似ていたら捨てる）
        kept = []
        for s in scored:
            if all(hamming(s["hash"], k["hash"]) >= a.min_hamming for k in kept):
                kept.append(s)

        # 文字の多い順に上位だけ残し、最後に時系列に戻す
        kept.sort(key=lambda s: -s["text"])
        kept = kept[:a.max]
        kept.sort(key=lambda s: s["sec"])

        out = []
        for i, s in enumerate(kept, 1):
            name = f"f{i:02d}_{int(s['sec']):04d}s.jpg"
            shutil.copyfile(s["file"], os.path.join(a.out, name))
            out.append({"file": name, "sec": round(s["sec"], 1),
                        "文字らしさ": round(s["text"], 3)})

        json.dump({"video": a.video, "候補": len(cands), "重複除去後": len(scored),
                   "採用": len(out), "frames": out},
                  open(os.path.join(a.out, "frames.json"), "w"),
                  ensure_ascii=False, indent=1)
        print(json.dumps({"out": a.out, "候補": len(cands), "採用": len(out)},
                         ensure_ascii=False))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
