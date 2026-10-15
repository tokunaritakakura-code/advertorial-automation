#!/usr/bin/env python3
"""to_segments.py <file.vtt|file.srt> — 字幕/Whisper出力を「秒\tテキスト」のTSVに正規化する。
自動字幕VTTの行重複(進行表示)もここでdedupeする。merge.pyとtranscriptの共通入力。"""
import re
import sys

TAG = re.compile(r"<[^>]+>")
VTT_TS = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.\d{3}\s+-->")
SRT_TS = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),\d{3}\s+-->")


def main(path: str) -> None:
    last_line = ""
    cur = 0.0
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.strip()
        m = VTT_TS.match(line) or SRT_TS.match(line)
        if m:
            h, mnt, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            cur = h * 3600 + mnt * 60 + s
            continue
        if not line or line.isdigit() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        text = TAG.sub("", line).strip()
        if not text or text == last_line:
            continue
        if last_line and (text in last_line or last_line in text) and abs(len(text) - len(last_line)) < 3:
            continue
        print(f"{cur:.1f}\t{text}")
        last_line = text


if __name__ == "__main__":
    main(sys.argv[1])
