#!/usr/bin/env python3
"""見張り。前回から新しく線を越えた広告がある日だけ、Telegram に1行送る。

何も変わっていない日は何も送らない（変化があった時だけ起こす）。
Vault には書かない。書くのは週1の本走（erabu.py --書く）だけ。

使い方:
  python3 mihari.py --自社 melao.json --自社 wandry.json            # 送る
  python3 mihari.py --自社 melao.json --自社 wandry.json --試し     # 画面に出すだけ
"""
import argparse
import html
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import daicho  # noqa: E402
import erabu  # noqa: E402

STATE = os.path.join(HERE, "state", "前回の候補.json")
TELEGRAM_DIR = os.path.expanduser("~/Claude Code/毎日の制作")  # telegram.送る がある所


def 前回():
    """前に見張った時の鍵と、その日。無ければ (None, None)。

    None と「0本」を取り違えないために、初回は空集合ではなく None を返す。
    """
    if not os.path.exists(STATE):
        return None, None
    with open(STATE, encoding="utf-8") as f:
        d = json.load(f)
    return set(d.get("鍵", [])), d.get("日")


def 残す(鍵):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"日": date.today().isoformat(), "鍵": sorted(鍵)}, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def 送る(文):
    sys.path.insert(0, TELEGRAM_DIR)
    import telegram  # noqa: E402  ここで落ちたら黙らず例外にする
    telegram.送る(文)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--自社", action="append", default=[], required=True)
    p.add_argument("--hookd", default=None)
    p.add_argument("--注記", default="", help="GetHookd が取れなかった等、本人に伝える1行")
    p.add_argument("--試し", action="store_true")
    args = p.parse_args()

    済み = daicho.借りた鍵()
    全部 = []
    for path in getattr(args, "自社"):
        全部 += erabu.自社を並べる(erabu.読み込む(path), 済み)
    if args.hookd:
        全部 += erabu.hookdを並べる(erabu.読み込む(args.hookd), 済み)
    if not 全部:
        print("取得0件。広告が0本なのか取得に失敗したのかを切り分ける", file=sys.stderr)
        return 3

    今 = {r["鍵"] for r in erabu.候補を選ぶ(全部)}
    昨, 前の日 = 前回()
    if 昨 is None:
        残す(今)
        print(f"初回。{len(今)}本を覚えた。今日は送らない")
        return 0

    新しい = [r for r in erabu.候補を選ぶ(全部) if r["鍵"] not in 昨]
    # 今回読まなかった出どころ（自社だけ回した日の gethookd 等）の記憶は消さない。
    # 消すと次に読んだ時に全部「新しい」になって、同じ物を二度知らせてしまう
    読んだ鍵 = {r["鍵"] for r in 全部}
    # --試し では覚えない。覚えると次の本番が「変わりなし」になって1通も出ない（2026-09-22）
    注記 = getattr(args, "注記", "")
    if not 新しい:
        if 注記:   # 出どころ が落ちた日は黙らない。黙ると「今日は何も無かった」と区別が付かない
            文 = f"新しい勝ち広告は無し。ただし {注記}"
            if not getattr(args, "試し"):
                送る(文); 残す(今 | (昨 - 読んだ鍵))
                print(f"Telegram に送った（新しい物0本・注記だけ）: {文}")  # 黙ると送れたか分からず二度走らせる（2026-10-09）
            else:
                print(文)
            return 0
        print(f"変わりなし（候補 {len(今)}本）。送らない")
        if not getattr(args, "試し"):
            残す(今 | (昨 - 読んだ鍵))
        return 0

    空き = ""
    if 前の日:
        日数 = (date.today() - date.fromisoformat(前の日)).days
        # Macが寝ていた日は見張りが飛ぶ。飛んでも取りこぼさず、次に起きた朝にまとめて出る
        if 日数 > 1:
            空き = f"（前に見たのは {日数}日前・{前の日}。その間の分もまとめて出している）"
    行 = [f"まだ借りていない勝ち広告が {len(新しい)}本 増えた{空き}"]
    for r in 新しい:
        金 = f"ROAS {r['ROAS']}・獲得単価 ¥{r['獲得単価']:,}" if r["ROAS"] else f"{r.get('点')}点"
        # Telegram は HTML で送るので、名前の < & " を必ず逃がす（1文字で全文が崩れる）
        名前 = html.escape(r["名前"])
        名 = f'<a href="{html.escape(r["参考"], quote=True)}">{名前}</a>' if r.get("参考") else 名前
        行.append(f"・{r['タイプ名']}｜{名}（{金}）")   # HTMLのリンク。スマホで押すと開く
    if 注記:
        行.append(注記)
    行.append("週1の本走で型にする → ec/構造/型/_勝ち一覧.md")
    文 = "\n".join(行)

    if getattr(args, "試し"):
        print(文)
        return 0
    送る(文)
    # 送れてから覚える。先に覚えると、送信が落ちた日の分が二度と届かない（2026-09-23）
    残す(今 | (昨 - 読んだ鍵))
    print(f"Telegram に送った（{len(新しい)}本）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
