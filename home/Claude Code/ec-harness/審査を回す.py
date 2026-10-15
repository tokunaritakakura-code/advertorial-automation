#!/usr/bin/env python3
"""記事を部屋の編集長の審査に出し、判定が出るまで待って、記事のフォルダに 審査_<回>.md を書く（2026-10-15 本人「検査は合格するまで。構造で変えて」）。

使い方: python3 審査を回す.py <記事のフォルダ> <案件ID> [--ブランド リサーチ] [--役 記事ライター] [--待つ分 30]

出す前に道具が自分で確かめる物（通らなければ出さずに終了コード2）:
  - 前の回が FAIL なら、直し_<前の回>.md に「探した語」の行が指摘の件数以上ある（1か所だけ直して別の所と食い違うのを止める）
  - 記事の検査・記事の仕上がり検査・画像の置き方（記事のフォルダの 画像の置き方の引数.txt の引数で）を今の index.html で回して全部0。結果は 検査の結果.md に index.html の指紋つきで書き、審査に一緒に出す
回し方（05 記事を作る の手順9。回数の上限は無い）:
  1. この道具を走らせる。PASS なら終了コード0で終わり
  2. FAIL なら終了コード1。記事のフォルダの 審査_<回>.md を全部直し、直し_<回>.md に1行ずつ書き、検査をやり直して、もう一度 1 へ
  3. 「前の回と同じ所で落ちた」と出た項目は、記事だけでなく原因の手順か道具を直してから 1 へ（同じ落ち方を繰り返さない）
本人に聞くのは、お金のかかる生成・公開・本人にしか決められない事だけ。回数では止めない。

終了コード: 0 PASS（指摘なし）／ 3 PASS だが書き方の指摘あり（審査_<回>.md を直して機械の検査を通す）／ 1 FAIL（審査_<回>.md を書いた）／ 2 出せなかった・判定が待つ分の間に出なかった
"""
import hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request

HOME = os.path.expanduser("~")
部屋 = "http://127.0.0.1:3200"
収束 = os.path.join(HOME, "Claude Code/team-room/data/審査の収束.jsonl")
設定 = os.path.join(HOME, "Claude Code/ec-harness/config/brands.json")
決まり = ("{役} の手順書（Vault ec/構造/ハーネス/役/{役}.md）の関門と、本人の直しの台帳の {役} の節で照らす。"
        "加えて Vault ec/構造/ハーネス/05 記事を作る.md の一回で作る道、ec/構造/型/_買うまでの15の事.md（見終わった人の状態・入れる手段・好奇心の穴をつなぐ）、"
        "ec/決めたこと.md の 2026-10-15 の行。見た目はここちドライの記事の質と比べる。画像は 画像の置き場.md と index.html の画像が1対1か。"
        "【毎回全部を見る（2026-10-15 本人）】2回目以降も前回の指摘だけを見ない。毎回、引き継ぎ/VSL記事リサーチ_資料/記事の最終確認_ひな形.md の全項目と、"
        "編集長の関門 7-1・7-2 を全部の段で上から順に見て、ずれを全部書く。前回○だった所も見直す。名前・数字・場面が記事の中と移植表で食い違っていないかを全文で照らす。"
        "機械の検査は 検査の結果.md（index.html の指紋つき）を読み、指紋が今の index.html と違えば FIX")


def 引数(argv, 名, 既定):
    return argv[argv.index(名) + 1] if 名 in argv else 既定


def 判定たち(案件):
    if not os.path.exists(収束):
        return []
    out = []
    for l in open(収束, encoding="utf-8"):
        if 案件 not in l:
            continue
        d = json.loads(l)
        if d.get("context", {}).get("job_id") == 案件:
            out.append(d)
    return out


def 機械の検査(記事):
    """記事の検査・仕上がり検査・画像の置き方を今の index.html で回し、検査の結果.md に指紋（sha256 の頭12字）つきで書く。全部0なら True"""
    道 = os.path.join(HOME, "Claude Code/ec-harness")
    html = os.path.join(記事, "index.html")
    指紋 = hashlib.sha256(open(html, "rb").read()).hexdigest()[:12]
    移植表 = sorted(f for f in os.listdir(記事) if f.startswith("移植表") and f.endswith(".md"))
    結果 = []
    if not 移植表:
        結果.append(("記事の検査", 2, "移植表*.md が無い"))
    else:
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import 記事の検査; 記事の検査.main(['x', sys.argv[2], sys.argv[3]])",
                            道, os.path.join(記事, 移植表[0]), html], capture_output=True, text=True)
        結果.append(("記事の検査", r.returncode, (r.stdout + r.stderr).strip()))
    r = subprocess.run([sys.executable, os.path.join(道, "記事の仕上がり検査.py"), 記事], capture_output=True, text=True)
    結果.append(("記事の仕上がり検査", r.returncode, (r.stdout + r.stderr).strip()))
    引数の紙 = os.path.join(記事, "画像の置き方の引数.txt")
    if not os.path.exists(引数の紙):
        結果.append(("画像の置き方", 2, "画像の置き方の引数.txt が無い。1行目に参考の URL、2行目から --移植表 <移植表> などの引数を1つずつ書く（うちの記事は index.html を自動で渡す）"))
    else:
        a = [l.strip() for l in open(引数の紙, encoding="utf-8") if l.strip() and not l.startswith("#")]
        r = subprocess.run([sys.executable, os.path.join(道, "画像の置き方.py"), a[0], html] + a[1:], capture_output=True, text=True, cwd=記事, timeout=900)
        結果.append(("画像の置き方", r.returncode, (r.stdout + r.stderr).strip()))
    行 = [f"# 機械の検査の結果（審査を回す.py が書いた。手で直さない）", "",
          "読む人: 編集長と、記事を直す Claude。", "読む時: 審査の前。", "読まなくていい条件: なし。", "",
          f"- index.html の指紋: `{指紋}`（この指紋の index.html で回した結果。index.html を変えたら無効）",
          f"- 回した時刻: {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for 名, 終, 出 in 結果:
        行 += [f"## {名}: 終了コード {終}", "", "```", "\n".join(出.splitlines()[-25:]), "```", ""]
    open(os.path.join(記事, "検査の結果.md"), "w", encoding="utf-8").write("\n".join(行))
    return all(終 == 0 for _, 終, _ in 結果)


def 段たち(文):
    return set(re.findall(r"sec-\d+", 文))


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    記事, 案件 = os.path.abspath(argv[1]), argv[2]
    ブランド, 役 = 引数(argv, "--ブランド", "リサーチ"), 引数(argv, "--役", "記事ライター")
    待つ = int(引数(argv, "--待つ分", "30")) * 60
    if not os.path.exists(os.path.join(記事, "index.html")):
        print("index.html が無い:", 記事); return 2
    前 = 判定たち(案件)
    最後 = max([d["context"].get("revision", 0) for d in 前] + [0])
    回 = 最後 + 1
    # 部屋は、ブランドの置き場（asset_roots/<案件>/r<回>）の中の物しか審査しない
    根 = json.load(open(設定, encoding="utf-8"))["brands"][ブランド]["asset_roots"][0]
    写し = os.path.join(根, 案件, f"r{回}")
    # 直していない記事を出し直さない（2026-10-15 実測: 判定済みの FAIL を返さずに同じ記事を次の回に出し、同じ5件で落ちた）
    前の写し = os.path.join(根, 案件, f"r{最後}", "index.html")
    if 最後 and not os.path.exists(写し) and os.path.exists(前の写し) and \
            hashlib.sha256(open(前の写し, "rb").read()).digest() == hashlib.sha256(open(os.path.join(記事, "index.html"), "rb").read()).digest():
        d = [x for x in 前 if x["context"].get("revision") == 最後][-1]
        if d["収束後"]["decision"] == "PASS":
            print(f"PASS（{最後}回目。直していないので出し直さない）"); return 0
        print(f"{最後}回目の判定が出ていて、記事はまだ直していない。出し直さずに 審査_{最後}.md を書く")
        return 書く(記事, 案件, 最後, 前, d)
    if os.path.exists(写し):
        # 出したまま判定がまだの版は、出し直さずに判定を待つだけにする（二重に出さない）
        print(f"{回}回目はもう出してある。判定を待つ（最大 {待つ // 60} 分）")
        return 待って書く(記事, 案件, 回, 前, 待つ)
    # 出す前の関門1: 前の回の FAIL を全部、同じ事を全体から探して直したか（2026-10-15: 1か所直すと別の所と食い違い、件数が増えた）
    if 最後:
        d = [x for x in 前 if x["context"].get("revision") == 最後][-1]
        if d["収束後"]["decision"] == "FAIL":
            件 = len(d["収束後"].get("reasons", []))
            直し = os.path.join(記事, f"直し_{最後}.md")
            探した = sum(1 for l in open(直し, encoding="utf-8") if "探した語" in l) if os.path.exists(直し) else 0
            if 探した < 件:
                print(f"直し_{最後}.md に「探した語」の行が {探した} 行（{最後}回目の指摘は {件} 件）。指摘1件ごとに、名前・数字・場面の語を "
                      f"`grep -n <語> index.html 移植表*.md 報告.md 画像の置き場.md テスト用に決めた値.md` で全部探してそろえ、"
                      f"「探した語: <語>／見つかった所: <数>／全部そろえた」を書いてから出す"); return 2
    # 出す前の関門2: 機械の検査を、この道具が今の index.html で回し、結果を指紋つきで書く（古い結果を報告に書けないようにする）
    if not 機械の検査(記事):
        print(f"機械の検査が落ちた。審査には出さない。{os.path.join(記事, '検査の結果.md')} を見て直す"); return 2
    subprocess.run(["rsync", "-a", "--exclude", "参考", "--exclude", "作業", 記事 + "/", 写し + "/"], check=True)
    名 = ["index.html", "検査の結果.md"] + sorted(f for f in os.listdir(写し) if f.startswith("移植表") and f.endswith(".md")) + \
        [f for f in ("画像の置き場.md", "報告.md", "最終確認.md", f"直し_{回 - 1}.md") if os.path.exists(os.path.join(写し, f))]
    arts = [{"path": os.path.join(写し, f), "revision": 回, "sha256": hashlib.sha256(open(os.path.join(写し, f), "rb").read()).hexdigest()} for f in 名]
    本文 = {"channel": "funnel", "作り手": 役,
          "text": f"@編集長 部屋の外で作った物の審査 {回}回目（作り手 {役}）（{案件}）" + (f"。前回の FAIL は 直し_{回 - 1}.md で直した" if 回 > 1 else ""),
          "context": {"brand": ブランド, "job_id": 案件, "revision": 回},
          "review": {"artifacts": arts, "rules": 決まり.format(役=役)}}
    try:
        tok = json.load(urllib.request.urlopen(部屋 + "/api/state", timeout=10))["csrf_token"]
        req = urllib.request.Request(部屋 + "/api/post", data=json.dumps(本文, ensure_ascii=False).encode(),
                                     headers={"x-team-token": tok, "content-type": "application/json"})
        r = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        print("部屋に出せなかった（部屋が動いているか http://127.0.0.1:3200 を見る）:", e); return 2
    if not r.get("ok"):
        print("部屋が受け取らなかった:", r); return 2
    print(f"{回}回目を出した。判定を待つ（最大 {待つ // 60} 分）")
    return 待って書く(記事, 案件, 回, 前, 待つ)


def 待って書く(記事, 案件, 回, 前, 待つ):
    t0 = time.time()
    while time.time() - t0 < 待つ:
        今 = [d for d in 判定たち(案件) if d["context"].get("revision") == 回]
        if 今:
            break
        time.sleep(15)
    else:
        print("待つ分の間に判定が出なかった。部屋の画面で編集長が動いているかを見て、もう一度この道具を走らせる"); return 2
    return 書く(記事, 案件, 回, 前, 今[-1])


def 書く(記事, 案件, 回, 前, d):
    決 = d["収束後"]["decision"]; 理由 = d["収束後"].get("reasons", []); ラ = d.get("収束", {}).get("ラベル", [])
    if 決 == "PASS":
        if not 理由:
            print(f"PASS（{回}回目）"); return 0
        # 合格でも書き方の指摘が付いたら、直す物として書いて終了コード3（2026-10-15: 合格の回の書き方の指摘が記事に入らないまま終わった）
        行 = [f"# 編集長の審査 {回}回目（合格）の書き方の指摘（{d['at']}・{案件}）", "", "読む人: この記事を直す Claude。",
              "読む時: 合格の後、書き方の指摘を記事に入れる時。", "読まなくていい条件: なし。", "",
              f"判定: PASS。下の {len(理由)} 件は書き方の指摘。全部直し、直し_{回}.md に「探した語: <語>／見つかった所: <数>／全部そろえた」で書く。再審査には出さない。"
              "直した後は機械の検査だけ回す（`import 審査を回す; 審査を回す.機械の検査(<記事のフォルダ>)` が True）。", ""]
        行 += [f"{i}. {x}" for i, x in enumerate(理由, 1)]
        open(os.path.join(記事, f"審査_{回}.md"), "w", encoding="utf-8").write("\n".join(行) + "\n")
        print(f"PASS（{回}回目）。書き方の指摘 {len(理由)} 件を {os.path.join(記事, f'審査_{回}.md')} に書いた。直して機械の検査を通すまで終わりではない")
        return 3
    前の段 = set()
    for x in 前:
        if x["context"].get("revision") == 回 - 1:
            前の段 = 段たち(" ".join(x["収束後"].get("reasons", [])))
    行 = [f"# 編集長の審査 {回}回目（{d['at']}・{案件}）", "",
          "読む人: この記事を直す Claude。", "読む時: 直す前に全部。", "読まなくていい条件: なし。", "",
          f"判定: FAIL（{len(理由)}件）。全部直して 直し_{回}.md に1行ずつ書き、もう一度 `審査を回す.py` を走らせる（機械の検査はこの道具が回す）。回数の上限は無い。", "",
          "直す時は指摘1件ごとに、名前・数字・場面の語を `grep -n <語> index.html 移植表*.md 報告.md 画像の置き場.md テスト用に決めた値.md` で全部探してそろえる。"
          "直し_<回>.md の各行に「探した語: <語>／見つかった所: <数>／全部そろえた」を入れる。入っていないと道具は次の回を出さない。", ""]
    同じ = 0
    for i, x in enumerate(理由, 1):
        種 = ラ[i - 1]["choice"] if i - 1 < len(ラ) else ""
        重 = 段たち(x) & 前の段
        if 重:
            同じ += 1
        行.append(f"{i}. [{種}]{' [前の回と同じ所で落ちた: ' + '・'.join(sorted(重)) + '。記事だけでなく原因の手順か道具を直す]' if 重 else ''} {x}")
    open(os.path.join(記事, f"審査_{回}.md"), "w", encoding="utf-8").write("\n".join(行) + "\n")
    print(f"FAIL（{回}回目・{len(理由)}件・前の回と同じ所 {同じ}件）。{os.path.join(記事, f'審査_{回}.md')} を直してから、もう一度走らせる")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
