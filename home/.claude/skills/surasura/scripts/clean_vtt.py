#!/usr/bin/env python3
"""clean_vtt.py <file.vtt> — collapse a (possibly auto-generated) VTT into
plain text with a [mm:ss] marker roughly every 30 seconds.

Auto-generated YouTube VTTs repeat each line 2-3 times with word-level
timing tags; this dedupes them so Claude reads a clean transcript.
"""
import re
import sys

TAG = re.compile(r"<[^>]+>")
TS_LINE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.\d{3}\s+-->")

def main(path: str) -> None:
    lines_out = []
    last_line = ""
    last_marker = -999.0
    cur_time = 0.0

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            m = TS_LINE.match(line)
            if m:
                h, mnt, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
                cur_time = h * 3600 + mnt * 60 + s
                continue
            if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
                continue
            text = TAG.sub("", line).strip()
            if not text or text == last_line:
                continue
            # auto-subs often re-emit the previous line as a prefix; skip pure repeats
            if last_line and (text in last_line or last_line in text) and abs(len(text) - len(last_line)) < 3:
                continue
            if cur_time - last_marker >= 30:
                lines_out.append(f"\n[{int(cur_time // 60):02d}:{int(cur_time % 60):02d}] ")
                last_marker = cur_time
            lines_out.append(text + " ")
            last_line = text

    sys.stdout.write("".join(lines_out).strip() + "\n")

if __name__ == "__main__":
    main(sys.argv[1])
