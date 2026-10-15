"""夜の台本づくり: ワンドライの自社広告と GetHookd の AI の勝ち広告から参考を選び、商品ごとに VSL 台本を本数ぶん Obsidian に書いて、朝に Telegram で1通送る。
決まりの正本: ~/.claude/skills/vsl-sagasu/SKILL.md の Step 7
使い方: python3 daihon.py [--商品 アルコット,ここちドライ] [--本数 3（1商品あたり）] [--今すぐ] [--試し]

launchd から 15分おきに呼ばれる。03:00 を過ぎていて今日の分が終わっていなければ続きから走る。
段ごとに作業場へファイルを残すので、落ちても同じコマンドで続きから戻れる（1日3回まで試す）。
Vault と Desktop には claude の中からだけ触る（launchd の python は ~/Documents を読めない）。
"""
import os, sys, json, time, shlex, argparse, datetime, subprocess

ここ = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser("~/.local/bin/claude")
始める時刻 = "0300"
試す回数 = 3
段の分 = {"探す": 50, "書く": 60}
sys.path.insert(0, os.path.expanduser("~/Claude Code/毎日の制作"))


def 作業場(日): return os.path.join(ここ, "state", "台本", 日)


def 読む(p):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return None


def 書く(p, d):
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def claude(指示書, ば, 分, ログ, 試し):
    本文 = open(os.path.join(ここ, "daihon", 指示書), encoding="utf-8").read().format(**ば)
    if 試し:
        print(f"（試し）{指示書} {本文[:80]}…"); return 0
    cmd = f"/usr/bin/caffeinate -s -i {shlex.quote(CLAUDE)} -p {shlex.quote(本文)} --permission-mode bypassPermissions < /dev/null"   # 走っている間は Mac を寝かせない（電源の設定はスリープ1分）
    with open(ログ, "a", encoding="utf-8") as f:
        f.write(f"\n=== {datetime.datetime.now():%H:%M} {指示書} ===\n"); f.flush()
        try:
            return subprocess.run(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT, timeout=分 * 60).returncode
        except subprocess.TimeoutExpired:
            f.write(f"{分}分を超えたので打ち切った\n"); return 124


def 知らせる(日, 選, 結果):
    import html, telegram
    e = html.escape
    行 = [f"<b>VSL台本 {日}</b>（{sum(r.get('状態') == '済' for r in 結果)}/{len(選.get('参考', []))}本）"]
    if 選.get("注記"): 行.append(f"※ {e(選['注記'])}")
    前の商品 = None
    for 参 in 選.get("参考", []):
        if not any(x.get("番号") == 参["番号"] for x in 結果): continue   # 使わなかった予備は出さない
        if 参.get("商品") != 前の商品:
            前の商品 = 参.get("商品"); 行 += ["", f"<b>■ {e(前の商品 or '')}</b>"]
        r = next((x for x in 結果 if x.get("番号") == 参["番号"]), {})
        名 = f"<a href=\"{e(参.get('リンク', ''))}\">{e(参.get('名前', ''))}</a>"
        if r.get("状態") == "同じ骨組み":
            行 += ["", f"{参['番号']}. 見送り（もう使った構造）: {e(r.get('理由', ''))}（参考 {名}）"]
        elif r.get("状態") == "済":
            書類 = r.get("書類", "").split("Obsidian Vault/")[-1]
            元 = {"wandry": "ワンドライの自社広告", "melao": "メラオの自社広告", "gethookd": "GetHookd・AI"}.get(参.get("出どころ"), 参.get("出どころ", ""))
            行 += ["", f"{参['番号']}. {e(r.get('型', ''))}｜{e(r.get('入口', ''))}",
                   f"参考の動画: {名}（{元}・{e(参.get('数字', ''))}）",
                   f"フック: {e(r.get('フック', ''))}", f"書類: {e(書類)}"]
            if r.get("本人に聞くこと"): 行.append(f"聞くこと: {e(r['本人に聞くこと'])}")
        else:
            行 += ["", f"{参['番号']}. 止まった: {e(r.get('理由', '結果が無い'))}（参考 {名}）"]
    行 += ["", "朝は「今日の3本やって」で本人チェック1から始める。"]
    telegram.送る("\n".join(行))


def main(商品の並び, 本数, 今すぐ, 試し):
    日 = datetime.date.today().isoformat()
    場 = 作業場(日); os.makedirs(場, exist_ok=True)
    印, 回数ファイル, 鍵 = os.path.join(場, "済"), os.path.join(場, "回数"), os.path.join(場, "走っている")
    if os.path.exists(印): return 0
    if not 今すぐ and datetime.datetime.now().strftime("%H%M") < 始める時刻: return 0
    回 = int(open(回数ファイル).read() or 0) if os.path.exists(回数ファイル) else 0
    if 回 >= 試す回数 and not 今すぐ: return 0
    try: os.mkdir(鍵)                        # 15分おきの呼び出しと重ならない
    except FileExistsError:
        if time.time() - os.path.getmtime(鍵) < 4 * 3600: return 0
    try:
        if not 試し: open(回数ファイル, "w").write(str(回 + 1))
        ば = {"商品の並び": "・".join(商品の並び), "本数": 本数, "日": 日, "作業場": 場}
        ログ = os.path.join(場, "log.txt")
        選p = os.path.join(場, "選んだ.json")
        if not 読む(選p):
            claude("探す.md", ば, 段の分["探す"], ログ, 試し)
        選 = 読む(選p)
        if not 選 or not 選.get("参考"):
            if 試し: return 0
            if 回 + 1 >= 試す回数:
                import telegram; telegram.送る(f"VSL台本 {日}: 参考を選べずに止まった。{ログ}")
                open(印, "w").write("止まった")
            return 1
        結果, 済の数 = [], {}
        for 参 in 選["参考"]:                 # 予備は、その商品が本数に届いていない時だけ使う
            品 = 参.get("商品", "")
            if 参.get("予備") and 済の数.get(品, 0) >= 本数: continue
            rp = os.path.join(場, f"結果-{参['番号']}.json")
            r = 読む(rp)
            if not r or r.get("状態") not in ("済", "同じ骨組み"):
                claude("書く.md", {**ば, "番号": 参["番号"]}, 段の分["書く"], ログ, 試し)
                r = 読む(rp) or {"番号": 参["番号"], "状態": "止まった", "理由": "結果を書かずに終わった"}
            結果.append(r)
            if r.get("状態") == "済": 済の数[品] = 済の数.get(品, 0) + 1
        # 「同じ骨組み」で見送った物は失敗ではない。商品ごとに本数ぶん済か、予備まで使い切ったら終わり
        全部 = all(r.get("状態") in ("済", "同じ骨組み") for r in 結果)
        if 試し: print(json.dumps(結果, ensure_ascii=False)); return 0
        if 全部 or 回 + 1 >= 試す回数:           # 残りは次の15分で続きから。3回目で出来た分だけ送る
            知らせる(日, 選, 結果)
            open(印, "w").write("済" if 全部 else "一部")
        return 0 if 全部 else 1
    finally:
        try: os.rmdir(鍵)
        except OSError: pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--商品", default="アルコット,ここちドライ", help="カンマ区切り。本人 2026-09-30「毎回アルコットとここちドライ」")
    ap.add_argument("--本数", type=int, default=3, help="1商品あたり")
    ap.add_argument("--今すぐ", action="store_true", help="03:00 を待たず・回数の上限を無視して走る")
    ap.add_argument("--試し", action="store_true", help="claude を呼ばずに流れだけ見る")
    a = ap.parse_args()
    raise SystemExit(main([x.strip() for x in a.商品.split(",") if x.strip()], a.本数, a.今すぐ, a.試し))
