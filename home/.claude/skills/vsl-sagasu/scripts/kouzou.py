"""使った構造（骨組み）の記録係。台本を Obsidian に入れるたびに `台本/入れる.py` から呼ばれる。
決まりの正本: ~/.claude/skills/vsl-sagasu/SKILL.md の「使った構造の記録」

使い方:
  python3 kouzou.py 同期   書類に出てくる広告IDのうち台帳に無い物を `_借りた元.tsv` に足す
  python3 kouzou.py 書く   `_使った構造.md`（骨組みごとの型・台本・元の広告の1枚）を書き直す
  python3 kouzou.py 検査   骨組みの無い型・台帳に無い広告IDがあれば exit 1
  python3 kouzou.py 全部   同期→書く→検査（入れる.py はこれを呼ぶ）

骨組み＝話の進め方（日を追う・段階で悪化・並べて落とす…）。型の番号（T）より1段上で、
番号が違っても骨組みが同じなら「もう使った構造」。正本は `ec/構造/型/_骨組み.tsv`（手で足す）。
"""
import os, re, csv, sys, glob, datetime

ここ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ここ)
import daicho  # noqa: E402

EC = os.path.expanduser("~/Documents/Obsidian Vault/ec")
型 = os.path.join(EC, "構造", "型")
骨組みTSV = os.path.join(型, "_骨組み.tsv")
出す = os.path.join(型, "_使った構造.md")
商品 = ["アルコット", "ここちドライ", "ワンドライ"]


def 骨組みを読む():
    with open(骨組みTSV, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def 型の番号(txt):
    """「T09（三段階）」「T11,T16」から T番号の並び"""
    return re.findall(r"T\d{2}", txt or "")


def 書類を集める():
    """[(商品, 種類, T番号 or '', 書類の相対パス, 広告IDの集合)]"""
    出 = []
    for 品 in 商品:
        for p in glob.glob(os.path.join(EC, 品, "05 VSL", "0[12] *", "**", "*.md"), recursive=True):
            rel = os.path.relpath(p, EC)
            m = re.search(r"/(T\d{2}) [^/]+/", rel)
            try: t = open(p, encoding="utf-8").read()
            except OSError: continue
            鍵 = set(re.findall(r"(?<!\d)(120\d{15})(?!\d)", t)) | set(re.findall(r"gethookd\.ai/share/ad/(\d+)", t))
            出.append((品, rel.split("/")[2], m.group(1) if m else "", rel, 鍵))
    return 出


def 一覧の型():
    t = open(os.path.join(型, "_一覧.md"), encoding="utf-8").read()
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^\|\s*(T\d{2})\s*\|\s*([^|]+)\|", t, flags=re.M)}


def 同期():
    台帳 = daicho.読む()
    ある = {r["鍵"].strip() for r in 台帳}
    足した = []
    今日 = datetime.date.today().isoformat()
    for 品, _, t番号, rel, 鍵 in 書類を集める():
        for k in sorted(鍵 - ある):
            出どころ = "gethookd" if not k.startswith("120") else "自社"
            台帳.append({"鍵": k, "出どころ": 出どころ, "型": t番号 or "なし", "呼び名": os.path.basename(rel)[:-3],
                        "軸": "構造", "借りた日": 今日, "備考": f"書類から自動（{rel}）"})
            ある.add(k); 足した.append(k)
    if 足した: daicho.書く(台帳)
    print(f"台帳に足した {len(足した)} 本")
    return 足した


def 書く():
    骨 = 骨組みを読む()
    書類 = 書類を集める()
    名 = 一覧の型()
    L = ["# 使った構造（骨組み）", "",
         "読む人: 次の参考を選ぶ係・台本を書く係・本人。",
         "読む時: 新しい参考で台本を書く前（その参考の話の進め方が、下のどれかと同じならもう使った構造）。",
         "読まなくていい条件: 既にある型で台本を1本足すだけの時。", "",
         f"**`kouzou.py 書く` が毎回上書きする（{datetime.datetime.now():%Y-%m-%d %H:%M}）。手で直すのは `_骨組み.tsv` だけ。**", "",
         "骨組み＝話の進め方。型の番号（T）が違っても骨組みが同じなら同じ構造。", ""]
    L += ["| 骨組み | 見分け（話の進め方） | 型 | アルコット | ここちドライ | ワンドライ |", "|---|---|---|---|---|---|"]
    # 「T09（三段階）」のように括弧が付いた行は、同じ型のフォルダの中で書類の名前にその語がある物だけ数える
    絞り = {t: re.findall(r"（(.+?)）", r["型"]) for r in 骨 for t in 型の番号(r["型"]) if "（" in r["型"]}
    def 当たる(r, b):
        ts = 型の番号(r["型"])
        if b[2] not in ts or not b[1].startswith("02"): return False
        語 = re.findall(r"（(.+?)）", r["型"])
        if 語: return any(w in os.path.basename(b[3]) for w in 語)
        return not any(w in os.path.basename(b[3]) for w in 絞り.get(b[2], []))
    for r in 骨:
        ts = 型の番号(r["型"])
        数 = {品: sum(1 for b in 書類 if b[0] == 品 and 当たる(r, b)) for 品 in 商品}
        型欄 = "・".join(f"{t} {名.get(t, '')}".strip() for t in ts) + "".join(f"（{w}）" for w in re.findall(r"（(.+?)）", r["型"]))
        L.append(f"| **{r['骨組み']}** | {r['見分け（話の進め方）']} | {型欄} | " + " | ".join(f"{数[品]}本" if 数[品] else "—" for 品 in 商品) + " |")
    L += ["", "## 台本ごと", "", "| 商品 | 型 | 台本 |", "|---|---|---|"]
    for 品, 種類, t番号, rel, _ in sorted(書類, key=lambda b: (b[0], b[2], b[3])):
        if 種類.startswith("02"):
            L.append(f"| {品} | {t番号 or '—'} | [[{rel[:-3]}\\|{os.path.basename(rel)[:-3]}]] |")
    tmp = 出す + ".tmp"
    open(tmp, "w", encoding="utf-8").write("\n".join(L) + "\n"); os.replace(tmp, 出す)
    print(f"書いた: {os.path.relpath(出す, os.path.dirname(EC))}")


def 検査():
    骨の型 = {t for r in 骨組みを読む() for t in 型の番号(r["型"])}
    落ち = [f"骨組みの無い型: {t} {n}（`_骨組み.tsv` のどれかの行に足すか、新しい骨組みの行を足す）"
            for t, n in 一覧の型().items() if t not in 骨の型]
    ある = {r["鍵"].strip() for r in daicho.読む()}
    for 品, _, _, rel, 鍵 in 書類を集める():
        for k in 鍵 - ある: 落ち.append(f"台帳に無い広告ID: {k}（{rel}）→ `kouzou.py 同期`")
    for x in 落ち: print("  ×", x)
    print(f"使った構造の検査: 落ちた {len(落ち)} 件")
    return 0 if not 落ち else 1


if __name__ == "__main__":
    何 = sys.argv[1] if len(sys.argv) > 1 else "全部"
    if 何 == "同期": 同期()
    elif 何 == "書く": 書く()
    elif 何 == "検査": raise SystemExit(検査())
    elif 何 == "全部": 同期(); 書く(); raise SystemExit(検査())
    else: print(__doc__); raise SystemExit(2)
