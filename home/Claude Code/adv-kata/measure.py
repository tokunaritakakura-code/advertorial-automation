#!/usr/bin/env python3
"""参考アドバトリアルのURLを1本渡すと、型の「左の列」を機械で書き出す。

使い方:
    python3 measure.py <URL> [出力先.md]

出す物（全部この1枚に入る）:
  1. 数値トークン（幅・本文・見出し・蛍光・CTA・引用の色と大きさ）
  2. 節の一覧（h2ごとに 段落数・引用数・画像・リスト・CTAの有無）
  3. 蛍光を引いてある文（全部そのまま）
  4. 太字の全件（種類を数える材料）
  5. CTAの位置（何節目か）と、浮遊ボタンの起動条件（JSから読む）
  6. 画像の位置（見出しの直後か、章の途中か）
どれも実測。推測は1行も書かない。
"""
import re, sys, json, html, urllib.request
from collections import OrderedDict

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "ignore")


def txt(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h))).strip()


def tokens(css):
    want = OrderedDict([
        ("記事列の最大幅", r"max-width:\s*(\d+px)"),
        ("本文の大きさ", r"p\{[^}]*font-size:\s*(\d+px)"),
        ("本文の行間", r"p\{[^}]*line-height:\s*([\d.]+)"),
        ("本文の色", r"p\{[^}]*color:\s*(#[0-9A-Fa-f]{3,8})"),
        ("h1", r"h1[^{]*\{[^}]*font-size:\s*(\d+px)"),
        ("h2", r"h2[^{]*\{[^}]*font-size:\s*(\d+px)"),
        ("蛍光の色", r"\.highlight[^{]*\{[^}]*background[^:]*:\s*([^;!}]+)"),
        ("CTAの色", r"\.ctabut[^{]*\{[^}]*background[^:]*:\s*([^;!}]+)"),
        ("引用の左罫", r"blockquote[^{]*\{[^}]*border-left:\s*([^;!}]+)"),
        ("フォント", r"font-family:\s*([^;!}]+)"),
    ])
    out = []
    for k, pat in want.items():
        m = re.search(pat, css, re.S)
        out.append((k, m.group(1).strip() if m else "（取れず）"))
    return out


def main():
    url = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else "_分解-自動.md"
    raw = fetch(url)
    css = "\n".join(re.findall(r"(?is)<style[^>]*>(.*?)</style>", raw))
    js = "\n".join(re.findall(r"(?is)<script[^>]*>(.*?)</script>", raw))
    body = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", "", raw)

    # 節に割る（h2 が節の区切り）
    parts = re.split(r"(?i)(<h2[^>]*>.*?</h2>)", body)
    secs = []
    if parts:
        secs.append(("（導入）", parts[0]))
    for i in range(1, len(parts), 2):
        secs.append((txt(parts[i]), parts[i + 1] if i + 1 < len(parts) else ""))

    hl = [txt(m) for m in re.findall(r'(?is)<span class="[^"]*highlight[^"]*">(.*?)</span>', body)]
    bolds = [txt(m) for m in re.findall(r"(?is)<(?:strong|b)>(.*?)</(?:strong|b)>", body)]

    trig = re.search(r"indexOf\(['\"](.+?)['\"]\)", js)
    pct = re.search(r"innerHeight\s*\*\s*([\d.]+)", js)

    L = []
    A = L.append
    A(f"# 自動実測｜{url}\n")
    A("**この1枚は機械が数えた物。判断は書いていない。**\n")
    A("## 1. 数値トークン\n")
    A("| 部品 | 実測値 |\n|---|---|")
    for k, v in tokens(css):
        A(f"| {k} | `{v}` |")
    A("")
    A(f"## 2. 節（h2 は {len(secs)-1} 本・本文 {len(re.sub(chr(92)+'s','',txt(body)))} 和文字）\n")
    A("| # | 見出し | 段落 | 引用 | 画像 | リスト | CTA |\n|---|---|---|---|---|---|---|")
    for i, (h, b) in enumerate(secs):
        A("| {} | {} | {} | {} | {} | {} | {} |".format(
            i, h[:44],
            len(re.findall(r"(?i)<p[ >]", b)),
            len(re.findall(r"(?i)blockquote", b)) // 2,
            len(re.findall(r"(?i)<(img|video)[ >]", b)),
            len(re.findall(r"(?i)<(ul|ol)[ >]", b)),
            "●" if "ctabox" in b or "ctabut" in b else ""))
    A("")
    A(f"## 3. 蛍光（{len(hl)}本。1節に1本までか確認する）\n")
    for i, t in enumerate(hl, 1):
        A(f"{i}. {t}")
    A("")
    A(f"## 4. 太字（{len(bolds)}件。数字／客の逐語／章の結論／成分ラベル／否定リストの5種に分ける）\n")
    for t in bolds:
        A(f"- {t}")
    A("")
    A("## 5. 浮遊ボタン\n")
    A(f"- 起動する見出しに含まれる語：**{trig.group(1) if trig else '（JSに無い）'}**")
    A(f"- 画面のどこまで来たら出るか：**{pct.group(1) if pct else '（取れず）'}**（1.0＝画面の下端）")
    A("- 本文中のCTAが画面に入っている間は消えるか：" + ("はい" if "bottom>0" in js else "（取れず）"))
    A("")
    A("## 6. 画像の置き方\n")
    for i, (h, b) in enumerate(secs):
        for m in re.finditer(r"(?is)<(img|video)[^>]*(?:src|poster)=\"([^\"]+)\"[^>]*>", b):
            head = b[:m.start()]
            pos = "見出しの直後" if len(txt(head)) < 30 else "章の途中"
            A(f"- 節{i}「{h[:24]}」：{pos} — `{m.group(2)}`")
    open(dst, "w").write("\n".join(L))
    print(f"書いた: {dst}（節 {len(secs)-1}・蛍光 {len(hl)}・太字 {len(bolds)}）")


if __name__ == "__main__":
    main()
