#!/usr/bin/env python3
"""現行入口: 既存の位置引数に --context <job.json> --config <brands.json> を必ず付ける。
結果はJSON。status=executableは検査材料の準備完了で、配信・公開の承認ではない。
旧資料のURLは実行前にブランド配下の版付きローカルartifactへ保存する。

旧入力形式の説明（上記の契約が優先）:
割り付けの1枚（アングル1本 × 着地1本）を機械で落とす。2026-10-01 版（深さと参考の数で見る）。

使い方: python3 割り付け検査.py <割り付け.md>
1枚の頭に `反論台帳: <パス>` を書く。表は2つ（型は Vault `ec/構造/ハーネス/型/割り付け.md`）:
  「参考の扱い」表   | 面 | 参考の位置 | 参考が扱った反論 | 深さ | うちの番号 |
  「割り付け」表     | 番号 | 広告 | 記事 | 店 | 起きる瞬間 | 理由 |
深さ: 0 触れない / 1 一言 / 2 理由をつけて解く / 3 証拠まで出して潰す

落とす物（1つでもあれば終了コード1）:
  1. 漏れ: 反論台帳の番号に割り付けの行が無い
  2. 作り話: 反論台帳に無い番号が割り付けにある
  3. 深い説明の重複: 1つの反論で深さ2以上の面が2つ以上ある（深さ1は何回出てもいい）
  4. 浅いまま: どの面も深さ1以下なのに理由が空
  5. 容量: 面ごとの「深さ2以上の数」「深さ3の数」が、参考の扱い表の同じ面の数と違う（参考と同じ数にする）
  6. 遅すぎる: 深く解く面が、その反論が起きる瞬間より後ろにある（広告→記事→店の順）
"""
import os, re, sys

VAULT = os.path.expanduser("~/Documents/Obsidian Vault")
面たち = ["広告", "記事", "店"]
瞬間の面 = {"広告を見た時": 0, "記事の途中": 1, "商品ページ": 2, "値段を見た時": 2, "カート・レジ": 2, "届いた後": 2}


def 表たち(文):
    """見出し行で表を分けて返す: {見出しの1列目: [行の列のリスト]}"""
    out, 今 = {}, None
    for 行 in 文.split("\n"):
        if not 行.lstrip().startswith("|"): 今 = None; continue
        列 = [s.strip() for s in 行.split("|")[1:-1]]
        if 列 and set(列[0]) <= set("-: ") and 列[0]: continue
        if 今 is None: 今 = 列[0]; out.setdefault(今, []); continue
        out[今].append(列)
    return out


def main(p):
    文 = open(p, encoding="utf-8").read()
    m = re.search(r"^反論台帳:\s*(.+)$", 文, re.M)
    if not m: sys.exit("1枚の頭に `反論台帳: <パス>` が無い")
    台帳 = m.group(1).strip().strip("`")
    if not os.path.isabs(台帳): 台帳 = os.path.join(VAULT, 台帳)
    if not os.path.exists(台帳): sys.exit(f"反論台帳が無い: {台帳}")
    台帳の番号 = set()
    for 行たち in 表たち(open(台帳, encoding="utf-8").read()).values():
        for 列 in 行たち:
            if re.fullmatch(r"\d+|[A-Z]", 列[0]): 台帳の番号.add(列[0])
    if not 台帳の番号: sys.exit("反論台帳に有効な番号が0件")
    表 = 表たち(文)
    参考 = 表.get("面", []); 割 = 表.get("番号", [])
    if not 割: sys.exit("「割り付け」表（1列目の見出しが 番号）が無い")
    駄目 = []
    深い数 = {f: 0 for f in 面たち}; 三の数 = {f: 0 for f in 面たち}
    見た = set()
    for 列 in 割:
        if not 列 or not re.fullmatch(r"\d+|[A-Z]", 列[0]):
            駄目.append("割り付けに解析できない番号の行"); continue
        番 = 列[0]
        if 番 in 見た: 駄目.append(f"#{番}: 番号が重複")
        見た.add(番)
        try: 深さ = [int(列[i]) for i in (1, 2, 3)]
        except (ValueError, IndexError): 駄目.append(f"#{番}: 広告・記事・店の深さは 0〜3 の数字"); continue
        if any(d not in (0, 1, 2, 3) for d in 深さ): 駄目.append(f"#{番}: 深さは 0〜3"); continue
        瞬間 = 列[4] if len(列) > 4 else ""; 理由 = 列[5] if len(列) > 5 else ""
        if 番 not in 台帳の番号: 駄目.append(f"#{番}: 反論台帳に無い番号（作り話）")
        深い = [i for i, d in enumerate(深さ) if d >= 2]
        if len(深い) > 1: 駄目.append(f"#{番}: {'・'.join(面たち[i] for i in 深い)} の{len(深い)}か所で深く説明している。深く解く面は1つ、ほかは深さ1まで")
        if not 深い and not 理由: 駄目.append(f"#{番}: どの面も深さ1以下。浅くていい理由を書く")
        if 瞬間 not in 瞬間の面: 駄目.append(f"#{番}: 起きる瞬間は {'/'.join(瞬間の面)} のどれか（今: {瞬間 or '空'}）")
        elif 深い and 深い[0] > 瞬間の面[瞬間]: 駄目.append(f"#{番}: 「{瞬間}」に起きる反論を、その後ろの{面たち[深い[0]]}で深く解いている（遅すぎる）")
        for i, d in enumerate(深さ):
            if d >= 2: 深い数[面たち[i]] += 1
            if d == 3: 三の数[面たち[i]] += 1
    for 番 in sorted(台帳の番号 - 見た, key=lambda x: (len(x), x)): 駄目.append(f"#{番}: 割り付けの行が無い（漏れ）")
    if not 見た: 駄目.append("割り付け対象が0件")
    if not 参考: 駄目.append("参考の扱い表が無いか行が0")
    参深 = {f: 0 for f in 面たち}; 参三 = {f: 0 for f in 面たち}
    for 列 in 参考:
        if len(列) < 4 or 列[0] not in 面たち:
            駄目.append("参考の扱いに解析できない行"); continue
        try: d = int(列[3])
        except ValueError: 駄目.append(f"参考の扱い表の深さが数字でない: {列}"); continue
        if d not in (0, 1, 2, 3): 駄目.append("参考の深さは0〜3"); continue
        if not 列[1] or not 列[2]: 駄目.append("参考の位置・反論が空")
        if d >= 2: 参深[列[0]] += 1
        if d == 3: 参三[列[0]] += 1
    for f in 面たち:
        if (深い数[f], 三の数[f]) != (参深[f], 参三[f]):
            駄目.append(f"{f}: 深く解く反論 {深い数[f]}個（うち深さ3が{三の数[f]}個）。参考は {参深[f]}個（うち{参三[f]}個）。参考と同じ数にする")
    print(f"反論 {len(台帳の番号)}件 / 割り付け {len(見た)}件 / 落ちた {len(駄目)}件")
    if 駄目: print("\n".join("  " + x for x in 駄目)); sys.exit(1)
    print("通った")


if __name__ == "__main__":
    from 検査契約 import cli
    sys.exit(cli("割", lambda args,job,cfg: main(args[1]), sys.argv))
