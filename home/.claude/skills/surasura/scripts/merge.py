#!/usr/bin/env python3
"""merge.py <segments.tsv> <frames.tsv> — 文字起こしとキーフレームを時刻で貼り合わせ、
「その瞬間、こう話しながらこの画面を見せていた」統合manifest(Markdown)をstdoutに出す。
学習素材はこのmanifestであって字幕単体ではない(surasuraの鉄則)。"""
import sys


def mmss(sec: float) -> str:
    return f"{int(sec // 60):02d}:{int(sec % 60):02d}"


def load(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            continue
        t, v = line.split("\t", 1)
        rows.append((float(t), v))
    return rows


def main() -> None:
    segs = [(t, "T", v) for t, v in load(sys.argv[1])]
    frames = [(t, "F", v) for t, v in load(sys.argv[2])]
    print("# 統合記録（文字起こし × キーフレーム, 時刻同期）\n")
    buf = []
    last_marker = -999.0
    for t, kind, v in sorted(segs + frames, key=lambda x: (x[0], x[1] == "T")):
        if kind == "F":
            if buf:
                print(" ".join(buf) + "\n")
                buf = []
            print(f"**[{mmss(t)}] 画面**: {v}\n")
            last_marker = t
        else:
            if t - last_marker >= 30:
                if buf:
                    print(" ".join(buf) + "\n")
                    buf = []
                buf.append(f"[{mmss(t)}]")
                last_marker = t
            buf.append(v)
    if buf:
        print(" ".join(buf))


if __name__ == "__main__":
    main()
