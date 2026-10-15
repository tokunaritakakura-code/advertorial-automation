#!/usr/bin/env python3
"""現行入口: 既存の位置引数に --context <job.json> --config <brands.json> を必ず付ける。
結果はJSON。status=executableは検査材料の準備完了で、配信・公開の承認ではない。
旧資料のURLは実行前にブランド配下の版付きローカルartifactへ保存する。

旧入力形式の説明（上記の契約が優先）:
記事の移植表と index.html を機械で落とす。2026-10-02 版。

使い方: python3 記事の検査.py <01 移植表.md> [<index.html>] [--古い作り]
  --古い作り: 2026-10-15 より前に作った記事。3〜6 を見ない（新しく作る記事には付けない）
  index.html を渡さない時は 1 だけ見る（組む前に回せる）。

移植表に要る表は2つ（`adv-kata/新規.sh` が空の表を置く）:
  「受け渡し」表  | 渡した問い | 受ける段 |       受ける段は移植表の # の番号
  「移植表」      | # | 段 | 参考 | うち |      右の列に「CTA①」のように丸数字でボタンの位置を書く

落とす物（1つでもあれば終了コード1）:
  1. 受け渡し
     a. 受け渡し表が無い・行が0
     b. 受ける段が空、または移植表に無い番号
     c. 頭（# 0 か 1）で受けている問いが1つも無い（広告が渡した問いは記事の頭で受ける）
  2. 計測の印（index.html を渡した時だけ）
     a. 移植表の節（# 1 以上）の数と、index.html の id="sec-N" の数が違う
     b. sec-N の番号が 1..N で抜け・重複がある
     c. 移植表のボタン（丸数字の数）と、data-cta の数（"浮遊" を除く）が違う
     d. data-cta の名前が重複している
     e. 商品ページ・カートへのリンクで data-cta が無い物がある
  3. 塗り（| 事 | 印 | 根拠（秒） |。正本 Vault ec/構造/型/_買うまでの15の事.md。2026-10-15 本人）
     a. 表が無い、または ①〜⑮ のどれかの行が無い
     b. 印が ◎○△× 以外
     c. ◎○△ の行の根拠に秒（1:25 の形）が無い
  4. 見終わった人の状態（| 状態の欄 | 中身 | 根拠（秒） |）
     a. 表が無い、または 段階・信じた事・残った疑い・今の気持ち・広告の構造・開けた穴 のどれかが無い
     b. 中身が空
     c. 段階・今の気持ち 以外の欄の根拠に秒が無い（秒が付かない行は推測で書いている）
  5. 型の候補（| 候補 | 題 | 入りの1行 | 受ける疑い |。正本 _VSLから型を選ぶ.md の決め方3）
     a. 候補が2行未満、または題・入りの1行が空
     b. 「選んだ: 」の行が無い
  6. 穴のつなぎ（| 段 | 受ける穴 | 開ける次の穴 |。正本 _買うまでの15の事.md の「好奇心の穴をつなぐ」）
     a. 表が無い
     b. 移植表の # 1 から最後の1つ前までの段で、行が無い・開ける次の穴が空
     c. # 1 の受ける穴が空（広告の穴を頭で受ける）
"""
import re, sys

丸 = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


def 表たち(文):
    """見出し行の1列目で表を分けて返す: {1列目: [行の列のリスト]}"""
    out, 今 = {}, None
    for 行 in 文.split("\n"):
        if not 行.lstrip().startswith("|"):
            今 = None
            continue
        列 = [s.strip() for s in 行.split("|")[1:-1]]
        if 列 and 列[0] and set(列[0]) <= set("-: "):
            continue
        if 今 is None:
            今 = 列[0]
            # 1列目が「#」でも2列目が「段」でない表（画像の置き方.py の訳の対照表 | # | 参考の英語 | …）は移植表と混ぜない（2026-10-15 草むしり椅子）
            if 今 == "#" and len(列) > 1 and 列[1] != "段":
                今 = "#" + 列[1]
            out.setdefault(今, [])
            continue
        out[今].append(列)
    return out


def 移植表の行(表):
    行たち = 表.get("#", [])
    return [r for r in 行たち if len(r) >= 4 and re.fullmatch(r"\d+", r[0])]


def 受け渡しを見る(表, 番号たち, 落):
    行たち = 表.get("渡した問い")
    if not 行たち:
        落.append("1a 受け渡し表（| 渡した問い | 受ける段 |）が無いか、行が0")
        return
    頭で受けた = False
    for r in 行たち:
        問い = r[0] if r else ""
        受け = r[1] if len(r) > 1 else ""
        if not 問い.strip(): 落.append("1b 渡した問いが空")
        if not 受け:
            落.append(f"1b 受ける段が空: {問い}")
            continue
        段 = re.findall(r"\d+", 受け)
        if not 段 or any(s not in 番号たち for s in 段):
            落.append(f"1b 受ける段が移植表に無い: {問い} → {受け}")
        if any(s in ("0", "1") for s in 段):
            頭で受けた = True
    if not 頭で受けた:
        落.append("1c 頭（# 0 か 1）で受けている問いが1つも無い")


def 印を見る(行たち, html, 落):
    節 = sorted({int(r[0]) for r in 行たち if int(r[0]) >= 1})
    secs = [int(x) for x in re.findall(r'id="sec-(\d+)"', html)]
    if len(節) != len(secs):
        落.append(f"2a 節の数が違う: 移植表 {len(節)} ／ index.html の sec-N {len(secs)}")
    if sorted(secs) != 節: 落.append(f"2b 予定節IDと実物が違う: {節} / {sorted(secs)}")
    if sorted(secs) != list(range(1, len(secs) + 1)):
        落.append(f"2b sec-N の番号に抜けか重複: {sorted(secs)}")
    ボタン = set()
    for r in 行たち:
        ボタン |= {c for c in r[-1] if c in 丸}
    ctas = re.findall(r'data-cta="([^"]*)"', html)
    番号つき = [c for c in ctas if c != "浮遊"]
    if len(ボタン) != len(番号つき):
        落.append(f"2c ボタンの数が違う: 移植表 {len(ボタン)}（{''.join(sorted(ボタン))}）／ data-cta {len(番号つき)}")
    重複 = sorted({c for c in ctas if ctas.count(c) > 1})
    if 重複:
        落.append(f"2d data-cta の名前が重複: {重複}")
    for a in re.findall(r"<a\b[^>]*>", html):
        href = re.search(r'href="([^"]*)"', a)
        if href and re.search(r"/products/|/cart", href.group(1)) and "data-cta=" not in a:
            落.append(f"2e 商品ページへのリンクに data-cta が無い: {href.group(1)[:80]}")


秒 = re.compile(r"\d{1,2}:\d{2}")
十五 = ["①", "②", "③", "④a", "④b", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫", "⑬", "⑭", "⑮"]
状態の欄 = ["段階", "信じた事", "残った疑い", "今の気持ち", "広告の構造", "開けた穴"]


def 新しい表を見る(表, 文, 番号たち, 落):
    塗り = 表.get("事")
    if not 塗り:
        落.append("3a 塗りの表（| 事 | 印 | 根拠（秒） |）が無い")
    else:
        ある = {r[0].split()[0] if r and r[0] else "" for r in 塗り}
        無い = [k for k in 十五 if k not in ある]
        if 無い: 落.append(f"3a 塗りに無い事: {'・'.join(無い)}")
        for r in 塗り:
            印 = r[1].strip() if len(r) > 1 else ""
            if 印 not in ("◎", "○", "△", "×"): 落.append(f"3b 印が ◎○△× でない: {r[0]} → {印 or '空'}")
            elif 印 != "×" and not 秒.search(r[2] if len(r) > 2 else ""): 落.append(f"3c 根拠に秒が無い: {r[0]}")
    状態 = 表.get("状態の欄")
    if not 状態:
        落.append("4a 見終わった人の状態の表（| 状態の欄 | 中身 | 根拠（秒） |）が無い")
    else:
        行 = {r[0]: r for r in 状態 if r}
        for k in 状態の欄:
            if k not in 行: 落.append(f"4a 状態の欄が無い: {k}"); continue
            r = 行[k]
            if len(r) < 2 or not r[1].strip(): 落.append(f"4b 中身が空: {k}")
            if k not in ("段階", "今の気持ち") and not 秒.search(r[2] if len(r) > 2 else ""): 落.append(f"4c 根拠に秒が無い: {k}")
    候補 = 表.get("候補")
    if not 候補 or len(候補) < 2:
        落.append("5a 型の候補（| 候補 | 題 | 入りの1行 | 受ける疑い |）が2行未満")
    else:
        for r in 候補:
            if len(r) < 3 or not r[1].strip() or not r[2].strip(): 落.append(f"5a 題か入りの1行が空: {r[0] if r else ''}")
    if not re.search(r"^選んだ[:：]\s*\S", 文, flags=re.M): 落.append("5b 「選んだ: <候補>（理由1行）」の行が無い")
    穴 = 表.get("段")
    if not 穴:
        落.append("6a 穴のつなぎの表（| 段 | 受ける穴 | 開ける次の穴 |）が無い"); return
    行 = {re.sub(r"\D", "", r[0]): r for r in 穴 if r}
    節 = sorted(int(x) for x in 番号たち if int(x) >= 1)
    for n in 節[:-1]:
        r = 行.get(str(n))
        if not r: 落.append(f"6b 穴のつなぎに段 {n} の行が無い"); continue
        if len(r) < 3 or not r[2].strip(): 落.append(f"6b 段 {n} の開ける次の穴が空")
    r1 = 行.get("1")
    if r1 is not None and (len(r1) < 2 or not r1[1].strip()): 落.append("6c 段 1 の受ける穴が空（広告の穴を頭で受ける）")


def main(argv):
    古い = "--古い作り" in argv
    argv = [a for a in argv if a != "--古い作り"]
    if len(argv) < 2:
        sys.exit(__doc__)
    文 = open(argv[1], encoding="utf-8").read()
    表 = 表たち(文)
    行たち = 移植表の行(表)
    if not 行たち:
        sys.exit("移植表（| # | 段 | 参考 | うち |）の行が見つからない")
    番号たち = {r[0] for r in 行たち}
    落 = []
    if len(行たち) != len(表.get("#", [])): 落.append("移植表に解析不能の行")
    if len(番号たち) != len(行たち): 落.append("移植表の節番号が重複")
    if len(argv) <= 2: 落.append("index.htmlが無い（構造確認のみ）")
    受け渡しを見る(表, 番号たち, 落)
    if not 古い:
        新しい表を見る(表, 文, 番号たち, 落)
    if len(argv) > 2:
        印を見る(行たち, open(argv[2], encoding="utf-8").read(), 落)
    if 落:
        print(f"落ちた {len(落)}件")
        for x in 落:
            print("  " + x)
        sys.exit(1)
    print("通った（受け渡し" + ("" if 古い else "・塗り・状態・型の候補・穴のつなぎ") + ("・計測の印" if len(argv) > 2 else "") + "）")


if __name__ == "__main__":
    from 検査契約 import cli
    sys.exit(cli("記事", lambda args,job,cfg: main(args), sys.argv))
