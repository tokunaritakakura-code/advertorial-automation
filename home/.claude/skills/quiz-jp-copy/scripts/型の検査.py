#!/usr/bin/env python3
"""日本の「記事＋アンケート3問」型の出来た物（index.html）を、型.md の固定の並びで数える。

使い方: python3 型の検査.py <index.html> [--店 <店のURL（例 https://kokochidry.shop）>]
見る物（型.md の固定の段の番号）:
  段1  広告の表示（「PR」「広告を含みます」）がページに無い（2026-10-12 本人「全部のフォーマットで止めて」。前は頭の2,000字に PR を求めていた）
  段9  値段の札（割引の「OFF」か「%」）が Q1 より前
  段11 アンケートの入口（「問」「アンケート」）が Q1 より前
  段12〜14 問いが3〜5問（data-q の枠の「Q1.」〜）。各問いの枠に data-answer のボタンが2つ以上
  位置 Q1 が本文の 50% より後ろ（型.md の誤差: 参考は後ろ3分の1）
  段15 最後の問いの後に「ご回答」とボタン
  段10 不安つぶし（解約・返金保証・後払い のどれか）
  段16 本文の最後の 20% に「検索しても」か「追記」
  注記 「※」が5か所以上
  A2 型の固定16段（data-dan="1"〜"16"）が全部ある。段8（完売）は型.md の誤差なので無くてよい
  A4 割引率（○%OFF）と保証の日数（○日間）が、ページの中でそれぞれ1種類だけ
  B4 --店 を付けた時: 店の今の値段が1つ以上載っている・1万円以上の値段で店に無い物は、年・か月・比べる・代 の言葉のそばだけ
  計算 「1日あたり約N円」がページの値段÷日数（365・180・90・60・30）に±15%で合う
  T1 T2 必ず入れる物の印 data-tasu="1"（本文の12%まで）・"2"
  その他 noindex あり・他社の計測タグ（gtag fbq klaviyo tiktok clarity）0
画像の中の文字は alt の文で数える（参考の実物は alt が空なので、段15・16 は参考では×になる。これは測定の限界）
終了コード: 0=全部通った / 1=落ちた / 2=開けない
"""
import re
import html, re, sys

TRACK = re.compile(r"gtag\(|fbq\(|googletagmanager|gtm\.js|ytag\(|_lt\(|line-scdn|criteo|connect\.facebook|analytics\.tiktok|klaviyo|clarity\.ms", re.I)


def text_of(src):
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", src)
    # 文字が入った画像は alt に同じ文を書く決まり（子スキルの手順4）。alt も本文として数える
    body = re.sub(r'(?is)<img[^>]*\balt="([^"]*)"[^>]*>', lambda m: "\n" + m.group(1) + "\n", body)
    body = re.sub(r"(?s)<[^>]+>", "\n", body)
    return re.sub(r"\n\s*\n+", "\n", html.unescape(body))


def main(a):
    if not a:
        print(__doc__); return 2
    try:
        src = open(a[0], encoding="utf-8").read()
    except OSError as e:
        print(f"開けない: {e}", file=sys.stderr); return 2
    t = text_of(src)
    n = len(t)
    res = []

    def ok(name, cond, why=""):
        res.append((name, bool(cond), why))

    ok("段1 広告の表示が無い", not re.search(r"(?<![A-Za-z])PR(?![A-Za-z])|広告を含み", t), "「PR」か「広告を含みます」がある（決めたこと 2026-10-12 で全部やめた）")
    # 問いは、答えのボタン（data-answer）を持つ枠の Q だけを数える（よくある質問の Q1. を数えない）
    qblocks = re.findall(r"(?is)<[^>]+data-q=\"(\d+)\"", src)
    qs = [m.start() for m in re.finditer(r"Q\s*[1-5]\s*[.．]", t)]
    if qblocks:
        qs = qs[:len(set(qblocks))]
    ok("段12〜14 問いが3〜5問", 3 <= len(qs) <= 5, f"問いが{len(qs)}問")
    if qs:
        q1, ql = qs[0], qs[-1]
        yen = re.findall(r"\d[\d,]{2,}\s*円", t[:q1])
        ok("段9 値段の札（通常と今の2つ以上の円）が Q1 より前", len(set(yen)) >= 2, f"Q1 より前の値段が{len(set(yen))}種類")
        ok("段11 アンケートの入口が Q1 より前", re.search(r"タップ|[3３三]問|アンケート", t[:q1]) is not None, "Q1 より前に「タップ・3問・アンケート」が無い")
        ok("位置 Q1 が本文の後ろ半分", q1 / max(n, 1) >= 0.5, f"Q1 が本文の {q1 / max(n, 1):.0%} の位置")
        tail = t[ql:]
        m_ans = re.search(r"ご回答(ありがとう|いただ)", tail)
        ok("段15 最後の問いの後に「ご回答ありがとう」", m_ans is not None, "最後の問いの後に「ご回答ありがとう／いただいた」が無い")
        # 問いごとのボタン: HTML の側で Q の見出しから次の Q までの button / [data-answer] を数える
        if qblocks:
            per = {}
            for m in re.finditer(r"(?is)<[^>]+data-q=\"(\d+)\"(.*?)(?=<[^>]+data-q=\"\d+\"|data-dan=\"15\"|$)", src):
                per[m.group(1)] = len(re.findall(r"data-answer", m.group(2)))
            few = [k for k, v in per.items() if v < 2]
            ok("段12〜14 各問いにボタン2つ以上", not few, f"ボタンが2つ未満の問い: {few}")
        blocks = [] if qblocks else re.split(r"(?=Q\s*[1-5]\s*[.．])", re.sub(r"(?s)<[^>]+>", lambda m: m.group(0) if re.match(r"<(button|a|div|label)[^>]*(data-answer|class=\"[^\"]*(ans|choice|btn)[^\"]*\")", m.group(0)) else "", src))
        if not qblocks:
            ok("段12〜14 問いの枠に data-q がある", False, "問いの枠に data-q=\"1\"〜 が無い（手順3）")
    ok("段10 不安つぶし", re.search(r"解約|返金保証|後払い", t) is not None, "解約・返金保証・後払いのどれも無い")
    ok("段16 最後に急ぎ", re.search(r"検索しても|追記", t[int(n * 0.8):]) is not None, "最後の20%に「検索しても」「追記」が無い")
    ok("注記 ※が5か所以上", t.count("※") >= 5, f"※が{t.count('※')}か所")
    # 必ず入れる物（_必ず入れる物.md）: data-tasu の印と、1 が本文の頭にあるか
    tasu = re.findall(r'data-tasu="(\d+)"', src)
    ok("T1 最悪の結末の印 data-tasu=1", "1" in tasu, "data-tasu=\"1\" が無い（手順3）")
    ok("T2 値段の見せ方の印 data-tasu=2", "2" in tasu, "data-tasu=\"2\" が無い（手順3）")
    m1 = re.search(r'(?is)data-tasu="1"', src)
    if m1:
        pos = len(text_of(src[:m1.start()])) / max(n, 1)
        ok("T1 最悪の結末が本文の頭（12%まで）", pos <= 0.12, f"本文の {pos:.0%} の位置")
    # A2 型の固定の段
    dans = set(re.findall(r'data-dan="(\d+)"', src))
    lack = [str(i) for i in range(1, 17) if str(i) not in dans and i != 8]
    ok("A2 型の固定16段が全部ある（data-dan）", not lack, f"無い段: {', '.join(lack)}")
    # A4 数字の食い違い
    offs = set(re.findall(r"(\d{2})\s*[%％]\s*OFF", t, re.I))
    days = set(re.findall(r"(\d{2,3})\s*日間", t))
    ok("A4 割引率が1種類", len(offs) <= 1, f"割引率が{len(offs)}種類: {sorted(offs)}")
    ok("A4 保証の日数が1種類", len(days) <= 1, f"日数が{len(days)}種類: {sorted(days)}")
    sales = sorted({m.group(0) for m in re.finditer(r"[一-龥ぁ-んァ-ヶー]{1,6}セール", t)})
    ok("A4 割引の理由（○○セール）が1種類まで", len(sales) <= 1, f"セールの名前が{len(sales)}種類: {sales}（オファーの表の理由1つにそろえる）")
    # B4 店の値段
    if "--店" in a:
        shop = a[a.index("--店") + 1].rstrip("/")
        try:
            import json, urllib.request
            req = urllib.request.Request(shop + "/products.json?limit=50", headers={"User-Agent": "Mozilla/5.0"})
            prods = json.load(urllib.request.urlopen(req, timeout=20))["products"]
            store = set()
            for pr in prods:
                for v in pr["variants"]:
                    for k in ("price", "compare_at_price"):
                        if v.get(k):
                            store.add(int(float(v[k])))
            yen = [(int(m.group(1).replace(",", "")), m.start()) for m in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d{4,})\s*円", t)]
            ok("B4 店の今の値段が載っている", any(y in store for y, _ in yen), f"店の値段（{sorted(store)[:6]}…）がページに無い")
            mult = lambda y: any(s and y % s == 0 and y // s <= 30 for s in store)   # 店の値段の何枚分か（1枚ずつ15枚買うと 等）
            odd = [y for y, pos in yen if y >= 10000 and y not in store and not mult(y) and not re.search(r"年|か月|ヶ月|比べ|代|お得|差", t[max(0, pos - 25):pos + 25])]
            ok("B4 店に無い1万円以上の値段が無い", not odd, f"店に無い値段: {sorted(set(odd))}")
        except Exception as e:     # 店が取れない時は×にして理由を出す（○にしない）
            ok("B4 店の値段を取れた", False, f"取れなかった: {type(e).__name__}: {e}")
    # D5 申込ボタンの先: data-cta の行き先が手元のページで、そのページがある（2026-10-10 本人「その後のファネルがコピーできてない」）
    import os
    base = os.path.dirname(os.path.abspath(a[0]))
    hrefs = re.findall(r'(?is)<a[^>]*data-cta[^>]*href="([^"]*)"|<a[^>]*href="([^"]*)"[^>]*data-cta', src)
    hrefs = [x or y for x, y in hrefs]
    bad = [h for h in hrefs if not h or h.startswith("#") or (not h.startswith("http") and not os.path.exists(os.path.join(base, h.split("#")[0].split("?")[0] or "index.html")))]
    ok("D5 申込ボタンの行き先が手元の申込のページ", hrefs and not bad, f"ボタン{len(hrefs)}個のうち行き先が無い・#: {len(bad)}個（例: {bad[0] if bad else 'ボタンが無い'}）")
    # 1日あたりの値段の計算: 「1日あたり約N円」の N が、ページの値段÷日数（365・90・60・30）か÷枚数のどれかに±15%で合うか（2026-10-10 本番の advertorial-05 で 1枚あたりの額を1日あたりと書いていた）
    perday = [int(m.group(1).replace(",", "")) for m in re.finditer(r"1日(?:あたり|当たり)\s*(?:約|たった|わずか)?\s*(\d[\d,]*)\s*円", t)]
    if perday:
        prices = {int(m.group(1).replace(",", "")) for m in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d{4,})\s*円", t)}
        def fits(v):
            for p_ in prices:
                for d in (365, 180, 90, 60, 30):
                    if abs(p_ / d - v) <= max(1, v * 0.15):
                        return True
            return False
        wrong = sorted({v for v in perday if not fits(v)})
        ok("1日あたりの値段の計算", not wrong, f"ページのどの値段を日数で割っても合わない: {wrong}円（1枚あたりの額と取り違えていないか）")
    ok("noindex あり", re.search(r"noindex", src, re.I) is not None, "noindex が無い")
    scripts = " ".join(re.findall(r"(?is)<script[^>]*>.*?</script>", src))
    hit = TRACK.search(scripts)
    ok("他社の計測タグ 0", hit is None, f"計測タグが残っている: {hit.group(0) if hit else ''}")

    bad = [r for r in res if not r[1]]
    for name, good, why in res:
        print(f"{'○' if good else '×'} {name}{'' if good else '  → ' + why}")
    print("通った" if not bad else f"落ちた: {len(bad)}件")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
