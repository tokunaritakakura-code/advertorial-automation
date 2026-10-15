#!/usr/bin/env python3
"""refs/ の段の表から、変数の木（木.canvas）の骨を作る。

使い方: python3 木を組む.py <型の名前>
  作業場 ~/Claude Code/kata-tsukuru/runs/<型>/refs/*.md の段の表（| 番号 | 段の名前 | 仕事 | 心理 | ビジュアル | コピー |）を読み、
  参考ごとに group（label = ファイル名）を1つ、その中に段ごとのカード（段の名前・仕事・心理）を縦に並べる。
  もう 木.canvas がある時は、手で足したカードを残し、無い参考の group だけ足す。
終了コード: 0=書いた / 1=段の表が読めた参考が0本 / 2=作業場が無い
"""
import json, os, re, sys

RUNS = os.path.expanduser("~/Claude Code/kata-tsukuru/runs")
COL_W, CARD_W, CARD_H, GAP = 420, 380, 150, 20


def rows_of(text):
    out = []
    for l in text.splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|(.*)\|\s*$", l)
        if m:
            cells = [c.strip() for c in m.group(2).split("|")]
            out.append((int(m.group(1)), cells))
    return out


def main(a):
    if not a:
        print(__doc__); return 2
    d = os.path.join(RUNS, a[0])
    rd = os.path.join(d, "refs")
    if not os.path.isdir(rd):
        print(f"作業場が無い: {rd}", file=sys.stderr); return 2
    p = os.path.join(d, "木.canvas")
    canvas = {"nodes": [], "edges": []}
    if os.path.exists(p):
        with open(p) as f:
            canvas = json.load(f)
    have = {n.get("label") for n in canvas["nodes"] if n.get("type") == "group"}
    used = {n.get("id") for n in canvas["nodes"]}
    col = len(have)
    added = 0
    for fn in sorted(f for f in os.listdir(rd) if f.endswith(".md")):
        label = fn[:-3]
        if label in have:
            continue
        with open(os.path.join(rd, fn), encoding="utf-8") as f:
            rows = rows_of(f.read())
        if not rows:
            print(f"段の表が読めない: {fn}", file=sys.stderr); continue
        x = col * COL_W
        gid = f"g{col}"
        h = len(rows) * (CARD_H + GAP) + 60
        canvas["nodes"].append({"id": gid, "type": "group", "label": label, "x": x, "y": 0, "width": CARD_W + 40, "height": h})
        prev = None
        for i, (no, cells) in enumerate(rows):
            name = cells[0] if cells else ""
            job = cells[1] if len(cells) > 1 else ""
            mind = cells[2] if len(cells) > 2 else ""
            vis = cells[3] if len(cells) > 3 else ""
            copy = cells[4] if len(cells) > 4 else ""
            nid = f"{gid}_{no}"
            k = 2
            while nid in used:          # 1本の参考に表が2つ以上あると段の番号がかぶるので、かぶったら -2・-3 を付ける
                nid = f"{gid}_{no}-{k}"; k += 1
            used.add(nid)
            canvas["nodes"].append({"id": nid, "type": "text", "x": x + 20, "y": 40 + i * (CARD_H + GAP),
                                    "width": CARD_W, "height": CARD_H,
                                    "text": f"**{no} {name}**\n仕事: {job}\n心理: {mind}\nビジュアル: {vis}\nコピー: {copy}\n差を0にする事: "})
            if prev:
                canvas["edges"].append({"id": f"e_{prev}_{nid}", "fromNode": prev, "fromSide": "bottom", "toNode": nid, "toSide": "top"})
            prev = nid
        col += 1
        added += 1
    if added == 0 and not have:
        print("段の表が読めた参考が0本", file=sys.stderr); return 1
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(canvas, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    print(f"木.canvas: 参考 {len(have) + added}本（今回足した {added}本）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
