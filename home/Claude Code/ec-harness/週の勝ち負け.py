#!/usr/bin/env python3
"""現行入口: 既存の位置引数に --context <job.json> --config <brands.json> を必ず付ける。
結果はJSON。status=executableは検査材料の準備完了で、配信・公開の承認ではない。
旧資料のURLは実行前にブランド配下の版付きローカルartifactへ保存する。
書くは --output <brand workspace/job_id/rrevision/proposal.md> に提案だけを生成し、入力台帳は上書きしない。
ブランド別閾値はconfig.thresholds.retreat_roas/rollout_roasが必須。

旧入力形式の説明（上記の契約が優先）:
週の A・H ごとの勝ち負けを、アングル台帳の「週の勝ち負け」表に戻す道具と、その検査（工程9 学ぶ）。

使い方:
  python3 週の勝ち負け.py 表   <ブランド> <判断の材料.json> [--撤退 1.45 --ロールアウト 1.89]   # 出すだけ
  python3 週の勝ち負け.py 書く <ブランド> <判断の材料.json> [同上]                             # 台帳に書く（同じ週の行は置き換え）
  python3 週の勝ち負け.py 検査 <ブランド> <判断の材料.json> [同上]                             # 終了コード1で落ちる

材料: 朝の判断の材料 `~/Claude Code/arukoto-track/data/判断/<日>.json` の `アングル.直近7日`（A別・H別・未割り当て）と `期間7日`。
運用線: アルコットは `arukoto-track/lib/判断の材料.mjs` の `運用線` を読む。他のブランドは --撤退 と --ロールアウト を必ず渡す。

判定（暫定。線は実測で引き直す）:
  量が足りる = 注文 10件以上 か、費用が 目安CPA の3倍以上（目安CPA = 週の平均注文額 ÷ 撤退ROAS）
  勝ち = 量が足りる かつ ROAS ≥ ロールアウト／負け = 量が足りる かつ ROAS < 撤退
  線の間 = 量が足りる かつ その間／足りない = 量が足りない
次の手（戦略担当が書く。判定ごとに選べる物が決まっている）:
  勝ち → 伸ばす提案・続ける／線の間 → 続ける・H を変える・量を足す／負け → 止める提案・H を変える／足りない → 量を足す・続ける

検査が落とす物:
  1. 漏れ: その週に費用が付いた A・H に行が無い
  2. 作り話: 台帳の数字（費用・注文・ROAS）が材料と違う／材料に無い番号の行がある
  3. 判定違い: 判定が上の決まりと違う
  4. 次の手の空き・選べない次の手
  5. 未割り当て: 番号を引けない広告が1本以上ある（数字が A・H に戻らないので学べない）
  6. 台帳に無い番号
出す物（落とさない）: 実証の候補（2週以上「勝ち」の番号。brain の playbook の行に（実証: …）を付ける材料）
"""
import json, os, re, sys, tempfile, hashlib
from datetime import date
from pathlib import Path
import math

VAULT = os.environ.get("EC_VAULT") or os.path.expanduser("~/Documents/Obsidian Vault")  # 試す時だけ写しを指す
材料の運用線 = os.path.expanduser("~/Claude Code/arukoto-track/lib/判断の材料.mjs")
見出し = "## 週の勝ち負け"
表の頭 = "| 週 | 番号 | 費用 | 注文 | ROAS | 判定 | 次の手 |\n|---|---|---|---|---|---|---|"
空き = "（書く）"
選べる = {"勝ち": ["伸ばす提案", "続ける"], "線の間": ["続ける", "H を変える", "量を足す"],
          "負け": ["止める提案", "H を変える"], "足りない": ["量を足す", "続ける"]}


def 台帳の場所(ブランド):
    return f"{VAULT}/ec/{ブランド}/04 設計/06 アングル台帳.md"


def 運用線(ブランド, 撤退, ロール):
    if type(撤退) not in (int,float) or type(ロール) not in (int,float) or not 0<撤退<ロール:
        raise ValueError("ブランド別の撤退・ロールアウト線が未設定")
    return 撤退,ロール


def 材料を読む(p):
    d = json.load(open(p, encoding="utf-8"))
    a = (d.get("アングル") or {}).get("直近7日")
    if not a: sys.exit(f"材料に アングル.直近7日 が無い: {p}")
    始, 終 = d["期間7日"]
    週 = f"{始}〜{終}"
    return 週, a


def 判定(r, 撤退, ロール, 目安CPA):
    足りる = r["注文"] >= 10 or (目安CPA and r["費用"] >= 3 * 目安CPA)
    if not 足りる or r["ROAS"] is None: return "足りない"
    if r["ROAS"] >= ロール: return "勝ち"
    if r["ROAS"] < 撤退: return "負け"
    return "線の間"


def 行を作る(週, a, 撤退, ロール):
    全 = a["A別"]
    if not 全 or not a.get("H別"): raise ValueError("週のA/H対象が0件")
    if any(r.get("注文") is None or r.get("売上") is None for r in 全 + a["H別"]):
        # 注文が取れなかった週（材料で null）は 0 件と見なして負けにしない（2026-10-02 工程8の穴①）
        raise SystemExit("注文が取れなかった週なので判定しない。材料の 警告 を見て、取り直してから回す")
    for side in ("A別","H別"):
        seen=set()
        for row in a[side]:
            number=row.get("番号")
            if not isinstance(number,str) or not re.fullmatch(("A" if side=="A別" else "H")+r"\d{2}",number) or number in seen:raise ValueError("invalid/duplicate weekly target")
            seen.add(number)
            if any(type(row.get(k)) not in (int,float) or not math.isfinite(row[k]) or row[k]<0 for k in ("費用","注文","売上")):raise ValueError("invalid weekly metrics")
            if row["費用"]>0 and (type(row.get("ROAS")) not in (int,float) or not math.isfinite(row["ROAS"]) or abs(row["ROAS"]-row["売上"]/row["費用"])>.011):raise ValueError("weekly ROAS disagrees with metrics")
    費 = sum(r["費用"] for r in 全); 注 = sum(r["注文"] for r in 全); 売 = sum(r["売上"] for r in 全)
    目安CPA = (売 / 注) / 撤退 if 注 else None
    out = []
    for 段 in ("A別", "H別"):
        for r in a[段]:
            if not r["費用"]: continue
            out.append({"週": 週, "番号": r["番号"], "費用": r["費用"], "注文": r["注文"],
                        "ROAS": r["ROAS"], "判定": 判定(r, 撤退, ロール, 目安CPA)})
    if not out:raise ValueError("週の消化対象が0件。学習判断はしない")
    return out, 目安CPA


def 文にする(r, 次=空き):
    roas = "" if r["ROAS"] is None else f'{r["ROAS"]:.2f}'
    return f'| {r["週"]} | {r["番号"]} | {r["費用"]} | {r["注文"]} | {roas} | {r["判定"]} | {次} |'


def 台帳の行(文):
    """週の勝ち負けの表の行と、A・H の番号の一覧を返す"""
    行たち, A, H, 中 = [], set(), set(), False
    for 行 in 文.split("\n"):
        if 行.startswith("## "): 中 = (行.strip() == 見出し); continue
        if not 行.lstrip().startswith("|"): continue
        列 = [s.strip() for s in 行.split("|")[1:-1]]
        if not 中:
            if 列 and re.fullmatch(r"A\d{2}", 列[0]): A.add(列[0])
            if 列 and re.fullmatch(r"H\d{2}", 列[0]): H.add(列[0])
            continue
        if len(列) < 7 or 列[0] == "週" or set(列[0]) <= set("-: "): continue
        行たち.append(dict(zip(["週", "番号", "費用", "注文", "ROAS", "判定", "次の手"], 列)))
    return 行たち, A, H


def 書く(場所, 週, 新):
    文 = open(場所, encoding="utf-8").read()
    if 見出し not in 文:
        説明 = ("\n" + 見出し + "\n\n毎週、戦略担当が `python3 ~/Claude\\ Code/ec-harness/週の勝ち負け.py 書く` で足し、"
              "「次の手」を書いてから `検査` を通す。判定の決まりは道具の頭（工程9 [[09 学ぶ]]）。\n\n" + 表の頭 + "\n")
        i = 文.find("\n## 読む機械")
        文 = 文 + 説明 if i < 0 else 文[:i] + "\n" + 説明 + 文[i:]
    前, 後 = 文.split(見出し, 1)
    j = 後.find("\n## ")
    節, 残り = (後, "") if j < 0 else (後[:j], 後[j:])
    残す = {}
    for 行 in 節.split("\n"):
        列 = [s.strip() for s in 行.split("|")[1:-1]] if 行.lstrip().startswith("|") else []
        if len(列) >= 7 and 列[0] == 週: 残す[列[1]] = 列[6]   # 書いてある次の手は消さない
    節の行 = [行 for 行 in 節.split("\n") if not (行.lstrip().startswith(f"| {週} |"))]
    while 節の行 and 節の行[-1] == "": 節の行.pop()
    節の行 += [文にする(r, 残す.get(r["番号"], 空き)) for r in 新]
    新しい文 = 前 + 見出し + "\n".join(節の行) + "\n" + 残り
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(場所), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f: f.write(新しい文)
    os.replace(tmp, 場所)


def 検査(場所, 週, 新, 未割り当て):
    行たち, A, H = 台帳の行(Path(場所).read_text(encoding="utf-8"))
    駄目 = []
    今週 = {r["番号"]: r for r in 行たち if r["週"] == 週}
    材料 = {r["番号"]: r for r in 新}
    for 番, r in 材料.items():
        if 番 not in 今週: 駄目.append(f"漏れ: {週} の {番} に行が無い"); continue
        t = 今週[番]
        if str(r["費用"]) != t["費用"] or str(r["注文"]) != t["注文"] or ("" if r["ROAS"] is None else f'{r["ROAS"]:.2f}') != t["ROAS"]:
            駄目.append(f"作り話: {番} の数字が材料と違う（台帳 {t['費用']}/{t['注文']}/{t['ROAS']}・材料 {r['費用']}/{r['注文']}/{r['ROAS']}）")
        if t["判定"] != r["判定"]: 駄目.append(f"判定違い: {番} は {r['判定']}（台帳は {t['判定']}）")
        次 = t["次の手"]
        if not 次 or 次 == 空き: 駄目.append(f"次の手の空き: {番}")
        elif not any(次.startswith(x) for x in 選べる[r["判定"]]):
            駄目.append(f"選べない次の手: {番} は {r['判定']} なので {'・'.join(選べる[r['判定']])} から（台帳は「{次}」）")
    for 番 in 今週:
        if 番 not in 材料: 駄目.append(f"作り話: {番} は材料のこの週に費用が無い")
    for 番 in list(今週) + list(材料):
        if (番.startswith("A") and 番 not in A) or (番.startswith("H") and 番 not in H):
            駄目.append(f"台帳に無い番号: {番}")
    if 未割り当て: 駄目.append(f"未割り当て: {len(未割り当て)}本（{' / '.join(未割り当て[:5])}）。台帳の対応表か名前の番号を直す")
    勝ち = {}
    for r in 行たち:
        if r["判定"] == "勝ち": 勝ち.setdefault(r["番号"], set()).add(r["週"])
    独立勝ち = {}
    for 番, periods in 勝ち.items():
        parsed=[]
        for period in periods:
            try:
                start,end=period.split("〜")
                if len(end)==5:end=start[:5]+end
                parsed.append((date.fromisoformat(start),date.fromisoformat(end),period))
            except ValueError:駄目.append("期間を解析できない: "+period)
        keep=[]
        for start,end,label in sorted(parsed,key=lambda p:p[1]):
            if start>end:駄目.append("逆転した期間: "+label)
            elif not keep or start>keep[-1][1]:keep.append((start,end,label))
        if len(keep)>=2:独立勝ち[番]=[p[2] for p in keep]
    return sorted(set(駄目)), 独立勝ち


def main():
    a = sys.argv[1:]
    def 取る(名):
        if 名 in a:
            i = a.index(名); v = float(a[i + 1]); del a[i:i + 2]; return v
        return None
    撤退, ロール = 取る("--撤退"), 取る("--ロールアウト")
    if len(a) != 3 or a[0] not in ("表", "書く", "検査"): print(__doc__); return 2
    動き, ブランド, 材料p = a
    場所 = 台帳の場所(ブランド)
    if not os.path.exists(場所): sys.exit(f"アングル台帳が無い: {場所}")
    撤退, ロール = 運用線(ブランド, 撤退, ロール)
    週, ang = 材料を読む(材料p)
    新, 目安 = 行を作る(週, ang, 撤退, ロール)
    print(f"{ブランド} {週}  運用線 撤退{撤退}・ロールアウト{ロール}  目安CPA {round(目安) if 目安 else '-'}円  行 {len(新)}")
    if 動き == "表":
        for r in 新: print(文にする(r))
        return 0
    if 動き == "書く":
        書く(場所, 週, 新)
        print(f"書いた: {場所}（次の手 {空き} を埋めてから 検査）")
        return 0
    駄目, 実証 = 検査(場所, 週, 新, ang.get("未割り当て") or [])
    for k, v in 実証.items(): print(f"実証の候補: {k}（勝ち {len(v)}週: {', '.join(v)}）")
    if 駄目:
        print("落ちた:"); [print("  " + x) for x in 駄目]; return 1
    print("通った"); return 0


def scoped_main(args,job,cfg):
    from 検査契約 import bound, identity
    d=json.load(open(args[3],encoding="utf-8")); errors=identity(d,job)
    if d.get("metrics_source")!=cfg.get("metrics_source"):errors.append("metric source mismatch")
    if d.get("thresholds")!=cfg.get("thresholds"):errors.append("threshold mismatch")
    period=d.get("期間7日")
    if not isinstance(period,list) or len(period)!=2:errors.append("explicit 7-day period required")
    else:
        start,end=map(date.fromisoformat,period)
        if (end-start).days!=6:errors.append("period must be seven inclusive days")
    lineage=d.get("lineage")
    if not isinstance(lineage,list) or not lineage:errors.append("experiment lineage required")
    artifacts={a["id"]:a for a in job["artifacts"]}
    for row in lineage or []:
        artifact=artifacts.get(row.get("artifact_id"))
        if not artifact or artifact["sha256"]!=row.get("artifact_sha256") or not row.get("ad_id") or not row.get("approval_ref"):errors.append("incomplete artifact/approval/ad lineage")
    if errors:raise ValueError("; ".join(errors))
    thresholds=cfg.get("thresholds") or {}
    retreat,roll=運用線(job["brand"],thresholds.get("retreat_roas"),thresholds.get("rollout_roas"))
    week,angles=材料を読む(args[3]);rows,cpa=行を作る(week,angles,retreat,roll)
    if args[1]=="表":
        for row in rows:print(文にする(row))
        return 0
    path=(job.get("evidence") or {}).get("ledger_path")
    if not path:raise ValueError("explicit brand ledger_path required")
    bound(path,job)
    if args[1]=="書く":
        if len(args)!=6:
            print("提案の --output が無い。入力台帳は更新しない");return 2
        output=Path(args[5]).resolve()
        workspace=Path(cfg.get("workspace_root") or cfg["asset_roots"][0]).resolve()
        proposal_root=workspace/job["job_id"]/f"r{job['revision']}"
        if not output.is_relative_to(proposal_root):raise ValueError("output must be inside brand/job/revision proposal workspace")
        if any(output==Path(a["path"]).resolve() for a in job["artifacts"]):raise ValueError("output cannot overwrite input artifact")
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open("x",encoding="utf-8") as f:f.write(Path(path).read_text(encoding="utf-8"))
        書く(str(output),week,rows)
        with output.open("a",encoding="utf-8") as f:
            f.write("\n<!-- experiment_lineage: "+json.dumps({"brand":job["brand"],"job_id":job["job_id"],"revision":job["revision"],"period":period,"source_material_sha256":hashlib.sha256(Path(args[3]).read_bytes()).hexdigest(),"lineage":lineage},ensure_ascii=False)+" -->\n")
        print("提案を生成: "+str(output)+"。次の手・新artifact版・独立レビューが必要。入力台帳は変更していない")
        return 3
    if args[1]!="検査":raise ValueError("unknown weekly operation")
    errors,proof=検査(path,week,rows,angles.get("未割り当て") or [])
    for e in errors:print(e)
    print("独立した勝ち期間:",json.dumps(proof,ensure_ascii=False))
    return 2 if errors else 0

if __name__ == "__main__":
    from 検査契約 import cli
    sys.exit(cli("週",scoped_main,sys.argv))
