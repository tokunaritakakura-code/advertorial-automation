#!/usr/bin/env python3
"""digestで当たりを付けた章だけ全文で取り出す。2段目の読み。

使い方:
  slice.py raw/<slug>.txt --ch 3,7,9          章番号で取る（digestのch番号と一致）
  slice.py raw/<slug>.txt --grep "アドバトリアル" --window 400
  slice.py raw/<slug>.txt --ch 3 --max-chars 4000

digest.py と同じ章割りロジックを使うので、ch番号はdigestの表示とずれない。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from digest import load, chapterize  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--ch", help="章番号をカンマ区切りで")
    ap.add_argument("--grep", help="この語の周辺を出す")
    ap.add_argument("--window", type=int, default=300, help="grep時に前後何字")
    ap.add_argument("--chapters", type=int, default=None,
                    help="既定はdigestが使った値を自動で読む。digestが無い時だけ12")
    ap.add_argument("--max-chars", type=int, default=8000)
    a = ap.parse_args()

    if not os.path.exists(a.raw):
        print(f"SLICE_FAILED: 生テキストが無い: {a.raw}", file=sys.stderr)
        sys.exit(2)
    if not a.ch and not a.grep:
        print("SLICE_FAILED: --ch か --grep のどちらかを指定すること", file=sys.stderr)
        sys.exit(2)

    timed, has_ts = load(a.raw)
    if not timed:
        print("SLICE_FAILED: 生テキストが空", file=sys.stderr)
        sys.exit(3)

    # digestが使った章割りを再現する。ここがズレると別の章を読むことになる
    n_chapters = a.chapters
    side = a.raw.replace(".txt", ".digest.json")
    if n_chapters is None:
        if os.path.exists(side):
            try:
                n_chapters = int(json.load(open(side))["chapters_arg"])
            except Exception:
                n_chapters = 12
        else:
            n_chapters = 12
            print("注意: digestのパラメータが見つからないので --chapters 12 で割った。"
                  "digestのch番号とズレている可能性がある", file=sys.stderr)

    parts = []
    if a.ch:
        chs = chapterize(timed, has_ts, n_chapters)
        want = []
        for x in a.ch.split(","):
            x = x.strip()
            if not x.isdigit():
                print(f"SLICE_FAILED: 章番号が数字でない: {x}", file=sys.stderr)
                sys.exit(2)
            want.append(int(x))
        bad = [n for n in want if n < 1 or n > len(chs)]
        if bad:
            print(f"SLICE_FAILED: 章{bad}は無い。この教材の章は1〜{len(chs)}",
                  file=sys.stderr)
            sys.exit(4)
        for n in want:
            t0, sents = chs[n - 1]
            head = f"## ch{n}" + (f" [{t0 // 60:02d}:{t0 % 60:02d}]" if t0 is not None else "")
            parts.append(head + "\n" + " ".join(sents))

    if a.grep:
        full = " ".join(t for _, t in timed)
        low, key = full.lower(), a.grep.lower()
        hits, i = [], 0
        while True:
            j = low.find(key, i)
            if j < 0:
                break
            hits.append(full[max(0, j - a.window): j + a.window])
            i = j + len(key)
            if len(hits) >= 12:
                break
        if not hits:
            print(f"SLICE_EMPTY: 「{a.grep}」はこの教材に出てこない", file=sys.stderr)
            sys.exit(5)
        parts.append(f"## grep: {a.grep}（{len(hits)}箇所）\n" +
                     "\n\n---\n".join(hits))

    body = "\n\n".join(parts)
    if len(body) > a.max_chars:
        body = body[:a.max_chars] + \
            f"\n\n（{a.max_chars}字で切った。章を減らして呼び直すこと）"
    print(body)


if __name__ == "__main__":
    main()
