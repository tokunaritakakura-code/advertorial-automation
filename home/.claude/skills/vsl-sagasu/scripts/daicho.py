#!/usr/bin/env python3
"""借りた元の台帳（_借りた元.tsv）を読む・足す・過去分を埋める。

台帳が「もう借りた物を消す」の土台。型の一覧(_一覧.md)は型しか持っていないので、
広告IDで引ける台帳をここに持つ。

使い方:
  python3 daicho.py 埋める            # _一覧.md から過去分を台帳に写す（既にある行は触らない）
  python3 daicho.py 見る              # 台帳を出す
  python3 daicho.py 足す --鍵 <鍵> --出どころ <melao|wandry|gethookd> --型 T10 --呼び名 <名前>
"""
import argparse
import csv
import os
import re
import sys
from datetime import date

VAULT = os.path.expanduser("~/Documents/Obsidian Vault/ec/構造/型")
DAICHO = os.path.join(VAULT, "_借りた元.tsv")
ICHIRAN = os.path.join(VAULT, "_一覧.md")
COLS = ["鍵", "出どころ", "型", "呼び名", "軸", "借りた日", "備考"]
軸の種類 = ("構造", "フォーマット", "フック", "見送り")
# 何を借りたか。構造が同じでも画とフックは別に借りられる。見送り＝見て却下した物（候補に出し続けない）


def 読む():
    """台帳を読む。無ければ空のリスト。壊れていれば例外で落とす（黙って0件にしない）。"""
    if not os.path.exists(DAICHO):
        return []
    with open(DAICHO, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    for r in rows:
        if "鍵" not in r or not r["鍵"]:
            raise ValueError(f"台帳の行に鍵が無い: {r}。{DAICHO} を直す")
        r.setdefault("軸", "")
        if not r["軸"]:
            r["軸"] = "構造"      # 欄が無い古い行は構造を借りた物として扱う
    return rows


def 借りた鍵(軸=None):
    """候補から消す鍵の集合。軸を指定すればその軸だけ。

    軸を問わず1度でも台帳に載った広告は候補に出さない（見送りも含む）。
    同じ広告を別の軸でもう1度借りるのは、その分解を書く時に人が決める。
    """
    鍵 = {r["鍵"].strip() for r in 読む() if 軸 is None or r["軸"] == 軸}
    return 鍵 | 書類に出てくる鍵() if 軸 is None else 鍵


def 書類に出てくる鍵():
    """台帳に入れ忘れても、もう台本に使った広告は候補に出さない。
    ec/<商品>/05 VSL/ の書類に書いてある Meta の広告ID（120…の18桁）と GetHookd の share/ad/<id> を拾う
    （2026-09-30 メラオ「3-1」が 9/24 に T09 の書類で使われていたのに台帳に無く、夜の台本で T15 として二度借りた）。
    """
    import glob
    鍵 = set()
    for p in glob.glob(os.path.expanduser("~/Documents/Obsidian Vault/ec/*/05 VSL/**/*.md"), recursive=True):
        try: t = open(p, encoding="utf-8").read()
        except OSError: continue
        鍵 |= set(re.findall(r"(?<!\d)(120\d{15})(?!\d)", t))
        鍵 |= set(re.findall(r"gethookd\.ai/share/ad/(\d+)", t))
    return 鍵


def 書く(rows):
    os.makedirs(VAULT, exist_ok=True)
    tmp = DAICHO + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, DAICHO)  # 原子的に置き換える（途中で落ちても台帳が壊れない）


def 足す(鍵, 出どころ, 型, 呼び名, 軸="構造", 備考=""):
    if 軸 not in 軸の種類:
        raise ValueError(f"軸は {軸の種類} のどれか: {軸}")
    rows = 読む()
    # 同じ広告でも軸が違えば別の行。同じ (鍵, 軸) だけを弾く
    if any(r["鍵"].strip() == str(鍵).strip() and r["軸"] == 軸 for r in rows):
        return False
    rows.append({
        "鍵": str(鍵).strip(), "出どころ": 出どころ, "型": 型, "呼び名": 呼び名, "軸": 軸,
        "借りた日": date.today().isoformat(), "備考": 備考,
    })
    書く(rows)
    return True


def 分解から広告ID(型):
    """T<番号>/_分解.md の「元の広告」から広告IDを拾う。一覧にIDが無い型を救う。"""
    if not os.path.isdir(VAULT_KATA_DIR := VAULT):
        return None
    for name in os.listdir(VAULT_KATA_DIR):
        if not name.startswith(型 + " "):
            continue
        path = os.path.join(VAULT_KATA_DIR, name, "_分解.md")
        if not os.path.exists(path):
            continue
        m = re.search(r"広告ID\s*(\d{10,})", open(path, encoding="utf-8").read())
        if m:
            return m.group(1)
    return None


def 埋める():
    """_一覧.md の型の表と、各型の _分解.md から過去分を写す。

    鍵は広告ID優先（分解の中にある事が多い）。無い型だけ「型 呼び名」を鍵にする。
    後からIDが見つかった型は、鍵を差し替える（同じ型で2行にしない）。
    """
    if not os.path.exists(ICHIRAN):
        print(f"型の一覧が無い: {ICHIRAN}", file=sys.stderr)
        return 1
    with open(ICHIRAN, encoding="utf-8") as f:
        text = f.read()
    足した = 差し替えた = 当たり = 0
    for line in text.splitlines():
        m = re.match(r"^\|\s*([TA]\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|", line)
        if not m:
            continue
        型, 呼び名, 元 = m.group(1), m.group(2), m.group(3)
        id_m = re.search(r"(\d{10,})", 元)
        広告ID = id_m.group(1) if id_m else 分解から広告ID(型)
        鍵 = 広告ID or f"{型} {呼び名}"
        出どころ = "melao" if "メラオ" in 元 + 呼び名 else "手で書いた型"
        備考 = re.sub(r"[|\[\]\\]", "", 元)[:60]
        当たり += 1
        rows = 読む()
        # 差し替えるのは「構造の軸で、鍵がまだ文字（広告IDが無かった）」の行だけ。
        # 全行を対象にすると、同じ型のフォーマット行の広告IDまで上書きして鍵が重複する
        古い = [r for r in rows
                if r["型"] == 型 and r["軸"] == "構造" and not r["鍵"].strip().isdigit()]
        if 広告ID and 古い:
            for r in 古い:
                r["鍵"] = 鍵
                r["備考"] = 備考
            書く(rows)
            差し替えた += 1
            continue
        if 足す(鍵, 出どころ, 型, 呼び名, 備考=備考):
            足した += 1
    if 当たり == 0:  # 表の形が変わった時に「0行足した」で静かに通さない
        print(f"型の表から1行も読めなかった: {ICHIRAN}。表の列の形が変わっている", file=sys.stderr)
        return 1
    print(f"型の表から {当たり} 行読んだ / 台帳に {足した} 行足した / "
          f"{差し替えた} 行の鍵を広告IDに差し替えた → {DAICHO}")
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("埋める")
    sub.add_parser("見る")
    a = sub.add_parser("足す")
    a.add_argument("--鍵", required=True)
    a.add_argument("--出どころ", required=True)
    a.add_argument("--型", required=True)
    a.add_argument("--呼び名", required=True)
    a.add_argument("--軸", default="構造", choices=list(軸の種類))
    a.add_argument("--備考", default="")
    args = p.parse_args()

    if args.cmd == "埋める":
        return 埋める()
    if args.cmd == "見る":
        rows = 読む()
        print("\t".join(COLS))
        for r in rows:
            print("\t".join(r.get(c, "") for c in COLS))
        print(f"-- {len(rows)} 行", file=sys.stderr)
        return 0
    if args.cmd == "足す":
        ok = 足す(getattr(args, "鍵"), getattr(args, "出どころ"), getattr(args, "型"),
                 getattr(args, "呼び名"), getattr(args, "軸"), getattr(args, "備考"))
        print("足した" if ok else "もう台帳にある")
        return 0


if __name__ == "__main__":
    sys.exit(main())
