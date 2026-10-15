#!/usr/bin/env python3
"""beats.py <segments.tsv> <frames.tsv> <outdir> [--cols 5] [--cell-w 480]
文字起こしとキーフレームを {t, frame, caption} のビート構造に束ね、
- <outdir>/beats.json … 機械可読(大規模モードで下流エージェントに配る用)
- <outdir>/montage/montage_NN.jpg … 時刻+字幕チップ付きcontact sheet(全景の一次読み用)
を生成する。詳細読みは個別768pxフレーム(2段読み)。contact.pyを内部で呼ぶ。"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_tsv(path):
    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            continue
        t, v = line.split("\t", 1)
        rows.append((float(t), v))
    return rows


def main() -> None:
    segs = load_tsv(sys.argv[1])
    frames = load_tsv(sys.argv[2])
    outdir = sys.argv[3]
    cols = int(sys.argv[sys.argv.index("--cols") + 1]) if "--cols" in sys.argv else 5
    cell_w = int(sys.argv[sys.argv.index("--cell-w") + 1]) if "--cell-w" in sys.argv else 480
    os.makedirs(outdir, exist_ok=True)

    # 各フレームに [そのフレーム時刻, 次フレーム時刻) の文字起こしを紐付け
    beats = []
    for i, (t, path) in enumerate(frames):
        t_next = frames[i + 1][0] if i + 1 < len(frames) else float("inf")
        caption = " ".join(txt for st, txt in segs if t <= st < t_next)
        if not caption:  # 区間が無音ならフレーム時刻に最も近いセグメントを借りる
            near = min(segs, key=lambda s: abs(s[0] - t), default=None)
            caption = near[1] if near and abs(near[0] - t) <= 15 else ""
        beats.append({"t": t, "frame": path, "caption": caption})

    with open(os.path.join(outdir, "beats.json"), "w", encoding="utf-8") as fh:
        json.dump(beats, fh, ensure_ascii=False, indent=1)

    montages = []
    if beats:
        spec = json.dumps({
            "frames": [{"path": b["frame"], "t": b["t"], "caption": b["caption"]} for b in beats],
            "out_dir": os.path.join(outdir, "montage"),
            "cols": cols, "rows_per_sheet": 6, "cell_w": cell_w, "caption_chars": 48,
        })
        r = subprocess.run([sys.executable, os.path.join(HERE, "contact.py")],
                           input=spec, capture_output=True, text=True)
        try:
            montages = json.loads(r.stdout.strip().splitlines()[-1]).get("montages", [])
        except Exception:
            print(f"contact.py failed: {r.stderr[-200:]}", file=sys.stderr)

    print(json.dumps({"beats": len(beats), "montages": montages}, ensure_ascii=False))


if __name__ == "__main__":
    main()
