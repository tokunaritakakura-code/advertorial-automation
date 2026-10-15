#!/usr/bin/env python3
"""機械の検査。exit 0 で合格、exit 3 で不合格（不合格のうちは本人に報告しない）。

文章の規則は破れるが、コードの規則は破れない。ここを通った物だけ成果物にする。

使い方:
  python3 check.py                 # 勝ち一覧・台帳・参考の箱の整合
  python3 check.py --分解 "<path>" # その分解のフックの節が埋まっているか
"""
import argparse
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daicho  # noqa: E402
import erabu  # noqa: E402

落ちた = []
見張り = False  # --知らせる（朝の見張り）の時だけ True
雛形 = re.compile(r"^[<＜].*[>＞]$")   # `<秒>` のようにテンプレのまま残っているセル


def 見る(条件, 名前, 詳しく=""):
    if 条件:
        print(f"  OK   {名前}")
    else:
        print(f"  NG   {名前}  {詳しく}")
        落ちた.append(名前)


def 候補の鍵(text):
    """2つの「次に借りる候補」の表から鍵（バッククォートの中）を拾う。"""
    始め = text.find("## 次に借りる候補")
    終わり = text.find("## 画を見て")
    if 始め < 0 or 終わり < 0:
        return None      # 表の形が変わった。0本と取り違えない
    return re.findall(r"`([0-9A-Za-z_-]{6,})`\s*\|", text[始め:終わり])


def 埋まっているか(text, 見出し):
    """その行の見出しより右のセルに中身があるか。見出しのセル自体は数えない。"""
    for l in text.splitlines():
        if 見出し not in l or not l.startswith("|"):
            continue
        cells = [c.strip() for c in l.split("|")]
        # cells[0] は空、cells[1] は番号、cells[2] が見出し。中身は cells[3:]
        中身 = [c for c in cells[3:-1] if c and not 雛形.match(c)]
        if 中身:
            return True
    return False


def 分解の検査(path):
    見る(os.path.exists(path), "分解の1枚がある", path)
    if not os.path.exists(path):
        return
    t = open(path, encoding="utf-8").read()
    見る("## フックの分解" in t, "フックの節がある")
    for 見出し in ["映っている物", "動き", "画面の文字", "音",
                 "誰を名指したか", "何を外したか", "開けた隙間",
                 "商品が出る秒", "実測", "真似する時に外せない物"]:
        見る(埋まっているか(t, 見出し), f"フックの節「{見出し}」が埋まっている")
    見る(re.search(r"広告ID\s*\S+", t) is not None, "元の広告に広告IDがある")
    見る("| フォーマット |" in t, "作り方（次の工程へ渡す）がある")


def 通しの検査():
    try:
        rows = daicho.読む()
    except Exception as e:  # 壊れた台帳を「0件」と読み違えない
        print(f"  NG   台帳が読めない: {e}")
        落ちた.append("台帳が読めない")
        return
    鍵軸 = [(r["鍵"].strip(), r["軸"]) for r in rows]
    見る(len(鍵軸) > 0, "台帳に行がある",
       f"{daicho.DAICHO} が空。`daicho.py 埋める` を先に走らせる")
    見る(len(鍵軸) == len(set(鍵軸)), "台帳の (鍵,軸) が重複していない",
       f"重複: {[x for x in set(鍵軸) if 鍵軸.count(x) > 1]}")

    見る(os.path.exists(erabu.KACHI), "勝ち一覧がある", erabu.KACHI)
    if not os.path.exists(erabu.KACHI):
        return
    text = open(erabu.KACHI, encoding="utf-8").read()
    if 見張り:
        # 勝ち一覧を書くのは月曜の本走だけ。見張りの朝に「今日の日付」を求めると毎朝誤報になる（2026-09-23）
        直近 = [(date.today() - timedelta(days=i)).isoformat() for i in range(8)]
        見る(any(d in text for d in 直近), "勝ち一覧が直近の本走（8日以内）で更新されている")
    else:
        見る(date.today().isoformat() in text, "勝ち一覧が今日の日付で更新されている")
    見る("## 測れないもの" in text, "測れないものの節がある")
    見る("数字の窓:" in text, "数字の窓と取得の時刻が書いてある")

    候補 = 候補の鍵(text)
    見る(候補 is not None, "候補の表が読める", "見出しの形が変わっている")
    if 候補 is None:
        return

    見る("無し。全部の広告タイプが機械で決まっている。" in text,
       "画を見て決める広告が残っていない", "その表の広告を見て `タイプ表` に語を足す")

    台帳の鍵 = {k for k, _ in 鍵軸}
    かぶり = [k for k in 候補 if k in 台帳の鍵]
    見る(not かぶり, "候補に台帳の物が混ざっていない", f"かぶり: {かぶり}")

    見る(os.path.exists(erabu.HAKO), "参考の箱がある", erabu.HAKO)
    if os.path.exists(erabu.HAKO):
        lines = open(erabu.HAKO, encoding="utf-8").read().splitlines()
        try:
            始め, 終わり = erabu.箱の範囲(lines)
        except ValueError as e:
            見る(False, "参考の箱の表が読める", str(e))
            return
        箱 = erabu.箱の鍵(lines, 始め, 終わり)   # 完全一致の鍵だけ。全文の部分一致にしない
        漏れ = [k for k in 候補 if k not in 箱]
        見る(not 漏れ, "候補が全部 参考の箱に入っている", f"漏れ: {漏れ}")

    print(f"\n候補 {len(候補)} 本 / 台帳 {len(鍵軸)} 行 / 落ちた検査 {len(落ちた)} 件")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--分解", default=None)
    p.add_argument("--知らせる", action="store_true",
                   help="落ちた時に Telegram に1行送る（誰も画面を見ていない自動実行用）")
    args = p.parse_args()
    global 見張り
    見張り = getattr(args, "知らせる")
    if getattr(args, "分解"):
        分解の検査(getattr(args, "分解"))
    else:
        通しの検査()
    if not 落ちた:
        return 0
    if getattr(args, "知らせる"):
        sys.path.insert(0, os.path.expanduser("~/Claude Code/毎日の制作"))
        import telegram  # noqa: E402  ここで落ちたら黙らせない
        telegram.送る("vsl-sagasu の検査が落ちた: " + "／".join(落ちた) +
                     "\n直す所 → ec/構造/型/_勝ち一覧.md")
    return 3


if __name__ == "__main__":
    sys.exit(main())
