#!/usr/bin/env python3
"""参考の記事の動く物（GIF に見える動画）と、うちの記事の動画を、上から同じ順で突き合わせる（工程5の手順8）。
2026-10-11 本人「ここは GIF。俺らのは GIF じゃない」。暴露型で、参考の4本（実写＋3D の切り替え・3面の割り）を
止まった絵をゆっくり寄せた mp4 で代えていて、画像の置き方.py は「動画どうし」で一致と出していた。

使い方: python3 動きの検査.py <うちの index.html> <参考の動画ファイルかフォルダ>... [--見比べ <出力.jpg>]
  参考はページの上からの順に並べて渡す（フォルダなら中の mp4/webm/gif/webp を名前順）。うちは index.html の <video>/<img src=.gif> を上から順に取る。
見る物（1本ずつ）:
  寄せただけ: 0.5秒おきのコマを2枚ずつ、特徴点の合わせ（ORB＋相似変換）で比べ、8割以上の組が「1枚の絵の拡大・移動」で説明できたら ×
  カット: ffmpeg の scene 検出（0.3）で数える。参考が2カット以上で、うちが 参考−1 より少なければ ×
  本数: 参考より少なければ ×
--見比べ: 1本ごとに参考とうちのコマを上下に並べた1枚を書く（審査役に渡す。画面の割り・実写か3Dかは審査役が見る）
終了コード: 0 一致 / 1 ずれがある / 2 測れなかった
"""
import os, re, subprocess, sys, tempfile

try:
    import cv2, numpy as np
except ImportError:
    print("測れない: opencv-python が無い（pip install opencv-python）"); sys.exit(2)

EXT = (".mp4", ".webm", ".mov", ".gif", ".webp")


def run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ours_from_html(path):
    html = open(path, encoding="utf-8", errors="ignore").read()
    base = os.path.dirname(os.path.abspath(path))
    out = []
    for m in re.finditer(r"<video\b[^>]*>.*?</video>|<video\b[^>]*/?>|<img\b[^>]*\.gif[^>]*>", html, re.S | re.I):
        tag = m.group(0)
        srcs = re.findall(r"""src=["']([^"']+)["']""", tag)
        srcs = [s for s in srcs if s.lower().split("?")[0].endswith(EXT)]
        if srcs:
            out.append(os.path.join(base, srcs[0]))
    return out


def refs_from_args(args):
    out = []
    for a in args:
        if os.path.isdir(a):
            out += sorted(os.path.join(a, f) for f in os.listdir(a) if f.lower().endswith(EXT))
        else:
            out.append(a)
    return out


def duration(f):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def cuts(f):
    r = run(["ffmpeg", "-hide_banner", "-i", f, "-vf", "select='gt(scene,0.3)',showinfo", "-f", "null", "-"], timeout=300)
    return 1 + len(re.findall(r"pts_time:", r.stderr))


def frames(f, step=0.5, width=480):
    d = tempfile.mkdtemp(prefix="ugoki_")
    run(["ffmpeg", "-v", "error", "-y", "-i", f, "-vf", f"fps={1/step},scale={width}:-2", os.path.join(d, "%04d.png")], timeout=300)
    fs = sorted(os.path.join(d, x) for x in os.listdir(d))
    return [cv2.imread(x, cv2.IMREAD_GRAYSCALE) for x in fs]


def only_zoomed(imgs):
    """コマの組の8割以上が、1枚の絵の拡大・移動（相似変換）で説明できるか（暴露型の 05 は12組中1組だけ外れた）。"""
    orb = cv2.ORB_create(1500)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    pairs = explained = 0
    for a, b in zip(imgs, imgs[1:]):
        if a is None or b is None:
            continue
        if np.abs(a.astype(int) - b.astype(int)).mean() < 1.0:
            continue  # 止まっている組は数えない
        ka, da = orb.detectAndCompute(a, None)
        kb, db = orb.detectAndCompute(b, None)
        pairs += 1
        if da is None or db is None or len(ka) < 30 or len(kb) < 30:
            continue
        ms = bf.match(da, db)
        if len(ms) < 30:
            continue
        pa = np.float32([ka[m.queryIdx].pt for m in ms])
        pb = np.float32([kb[m.trainIdx].pt for m in ms])
        M, inl = cv2.estimateAffinePartial2D(pa, pb, ransacReprojThreshold=2.0)
        if M is None:
            continue
        warped = cv2.warpAffine(a, M, (b.shape[1], b.shape[0]))
        mask = cv2.warpAffine(np.ones_like(a), M, (b.shape[1], b.shape[0])) > 0
        err = np.abs(warped.astype(int) - b.astype(int))[mask].mean() if mask.any() else 255
        if inl.mean() >= 0.8 and err <= 6:
            explained += 1
    return pairs > 0 and explained / pairs >= 0.8


def sheet(ref, ours, out, n=5):
    rows = []
    for f in (ref, ours):
        d = duration(f) or 1
        r = run(["ffmpeg", "-v", "error", "-y", "-i", f, "-vf", f"fps={n}/{d},scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2,tile={n}x1", "-frames:v", "1", out + f".{len(rows)}.jpg"])
        rows.append(out + f".{len(rows)}.jpg")
    run(["ffmpeg", "-v", "error", "-y", "-i", rows[0], "-i", rows[1], "-filter_complex", "vstack=2", out])
    for x in rows:
        if os.path.exists(x):
            os.remove(x)


def main():
    a = sys.argv[1:]
    out_sheet = None
    if "--見比べ" in a:
        i = a.index("--見比べ"); out_sheet = a[i + 1]; del a[i:i + 2]
    if len(a) < 2:
        print(__doc__); sys.exit(2)
    ours = ours_from_html(a[0]) if a[0].endswith(".html") else refs_from_args([a[0]])
    refs = refs_from_args(a[1:])
    missing = [f for f in ours + refs if not os.path.exists(f)]
    if missing:
        print("測れない: 無いファイル", *missing, sep="\n  "); sys.exit(2)
    bad = 0
    print(f"本数: 参考 {len(refs)} / うち {len(ours)}")
    if len(ours) < len(refs):
        print(f"  × うちの動く物が {len(refs) - len(ours)} 本足りない（参考の動く物の場所には動く物を置く）"); bad = 1
    sheets = []
    for k, (r, o) in enumerate(zip(refs, ours), 1):
        rc, oc = cuts(r), cuts(o)
        z = only_zoomed(frames(o))
        rz = only_zoomed(frames(r))
        line = f"{k}. 参考 {os.path.basename(r)} {duration(r):.1f}秒 {rc}カット / うち {os.path.basename(o)} {duration(o):.1f}秒 {oc}カット"
        msgs = []
        if z and not rz:
            msgs.append("止まった絵を寄せた・動かしただけ（参考は中身が動く。実写は実写の素材、3D は AI の動画で作る）")
        if rc >= 2 and oc < rc - 1:
            msgs.append(f"カットが足りない（参考 {rc}・うち {oc}。参考の切り替えの並びを写す）")
        print(("  × " if msgs else "  ○ ") + line + ("\n     " + "\n     ".join(msgs) if msgs else ""))
        bad |= bool(msgs)
        if out_sheet:
            s = re.sub(r"\.jpg$", f"_{k}.jpg", out_sheet)
            sheet(r, o, s); sheets.append(s)
    if sheets:
        print("見比べ（上が参考・下がうち）:", *sheets, sep="\n  ")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
