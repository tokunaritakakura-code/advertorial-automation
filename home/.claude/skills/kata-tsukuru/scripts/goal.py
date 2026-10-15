#!/usr/bin/env python3
"""飛び先の型を作るループの「ゴール」と「チェックボックス」を機械で判定する。

使い方:
  python3 goal.py init  <型の名前> [--子 <子スキル名>]   作業場と GOAL.md を作る
  python3 goal.py check <型の名前>                       全部の箱を判定。全部○で終了コード0
  python3 goal.py fail  <型の名前> <箱の番号> "<理由1行>"  ×を記録。同じ箱2回目で「やり方を変える」を出す
  python3 goal.py show  <型の名前>                       今の周回と×の履歴
  python3 goal.py reset <型の名前>                       周回を0に戻す（本人が続けてよいと言った時だけ）

作業場: ~/Claude Code/kata-tsukuru/runs/<型の名前>/
終了コード: 0=全部○ / 1=×あり / 2=使い方・作業場が無い / 3=周回の上限（本人に1行）
"""
import json, os, re, subprocess, sys, time

HOME = os.path.expanduser("~")
RUNS = os.path.join(HOME, "Claude Code", "kata-tsukuru", "runs")
SKILLS = os.path.join(HOME, ".claude", "skills")
CREATOR = os.path.join(SKILLS, "skill-creator", "references")
MAX_ROUNDS = 8          # 周回の上限。超えたら本人に1行
MIN_REFS = 3            # 割る参考の最低本数（2026-10-11 本人「同じ構造の記事が3本以上あればいい」）
MIN_SHARE = 3           # 「固定」と呼ぶには何本の参考に出ているか
MIN_VARS = 3            # 参考1本あたり、自分で足す変数のカードの最低枚数

BOXES = [
    ("G1", "同じ認知の段階・同じ構造の参考を3本以上集めて段に割った（refs/*.md に URL と、段ごとにビジュアルとコピーを分けた表）"),
    ("G2", "参考ごとの段を小さな変数の木に割った（木.canvas に参考ごとのまとまり）"),
    ("G3", "共通項を出した（型.md に 固定・分岐・誤差 の3節、固定の行は3本以上の参考を名指し）"),
    ("G4", "子スキルを書いた（SKILL.md 500行以内・掘り残し0・書式0・最終確認の箱あり）"),
    ("G5", "子スキルを本物の入力で、別の参考か別の商品で2本、端まで通し、2本とも子の最終確認が全部○（e2e/結果_1.json・結果_2.json）"),
    ("G6", "別の AI の審査が2本とも PASS（審査は基準ごとに理由→○×・受け取った物の一覧つき）と、参考を見せない読み手の目が2本とも PASS"),
    ("G8", "飛び先へ飛ばしている広告を割り、「この広告の組み立て → この型」の線を出した（広告と型のつながり.md に3本以上の広告と、その組み立て・飛び先・認知の段階）"),
    ("G7", "直しは手順の中に入れ、止める検査か見本を名指しした（直しの記録.md の各行に『手順N』と『止める検査:』・しない一覧の節が無い）"),
]


def run_dir(name):
    return os.path.join(RUNS, name)


def load_state(d):
    p = os.path.join(d, "state.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def save_state(d, st):
    p = os.path.join(d, "state.json")
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)   # 途中で落ちても壊れた state を残さない


def read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def sh(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"時間切れ（{timeout}秒）: {' '.join(cmd)}"
    except FileNotFoundError as e:
        return 127, f"道具が無い: {e}"


# ---- 箱ごとの判定。戻り値 (ok, 理由) ----

def g1(d, st):
    rd = os.path.join(d, "refs")
    if not os.path.isdir(rd):
        return False, "refs/ が無い"
    files = sorted(f for f in os.listdir(rd) if f.endswith(".md"))
    good, bad = [], []
    for f in files:
        t = read(os.path.join(rd, f)) or ""
        has_url = re.search(r"https?://", t) is not None
        rows = len(re.findall(r"^\|\s*\d+\s*\|", t, re.M))   # 段の表の行（| 1 | ... |）
        vc = "ビジュアル" in t and "コピー" in t                   # 段ごとに画像と文を分けたか（2026-10-10 本人）
        (good if has_url and rows >= 3 and vc else bad).append(f"{f}(段{rows}{'' if has_url else '・URL無し'}{'' if vc else '・ビジュアル/コピーの列無し'})")
    if len(good) < MIN_REFS:
        return False, f"段に割れた参考 {len(good)}本（{MIN_REFS}本要る）。足りない: {', '.join(bad) or 'なし'}"
    return True, f"{len(good)}本"


def g2(d, st):
    p = os.path.join(d, "木.canvas")
    t = read(p)
    if t is None:
        return False, "木.canvas が無い"
    try:
        c = json.loads(t)
    except json.JSONDecodeError as e:
        return False, f"木.canvas が JSON として読めない: {e}"
    allids = [n.get("id") for n in c.get("nodes", [])]
    if len(allids) != len(set(allids)):
        return False, f"カードの id のかぶりが {len(allids) - len(set(allids))}件（Obsidian でカードが重なって消える）"
    groups = [n for n in c.get("nodes", []) if n.get("type") == "group"]
    leaves = [n for n in c.get("nodes", []) if n.get("type") == "text"]
    # 木を組む.py が作る段のカード（id g<n>_<段>）は骨。自分で足した変数のカード（id g<n>_v<n>）だけを変数と数える
    added = [n for n in leaves if re.match(r"^g\d+_v\d+$", n.get("id", ""))]
    empty = [n["id"] for n in leaves if re.search(r"差を0にする事:\s*$", n.get("text", ""))]
    refs = [f[:-3] for f in os.listdir(os.path.join(d, "refs")) if f.endswith(".md")] if os.path.isdir(os.path.join(d, "refs")) else []
    labels = " ".join(g.get("label", "") for g in groups)
    missing = [r for r in refs if r.split(" ")[0] not in labels]
    if missing:
        return False, f"木に参考のまとまりが無い: {', '.join(missing)}"
    per = {}
    for n in added:
        per[n["id"].split("_")[0]] = per.get(n["id"].split("_")[0], 0) + 1
    thin = [g["label"] for g in groups if per.get(g["id"], 0) < MIN_VARS]
    if thin:
        return False, f"自分で足した変数のカード（id g<n>_v<n>）が{MIN_VARS}枚未満の参考: {', '.join(thin)}"
    if empty:
        return False, f"「差を0にする事」が空のカード {len(empty)}枚（例: {empty[0]}）"
    return True, f"まとまり{len(groups)}・段{len(leaves) - len(added)}・足した変数{len(added)}"


def g3(d, st):
    t = read(os.path.join(d, "型.md"))
    if t is None:
        return False, "型.md が無い"
    need = ["## 固定", "## 分岐", "## 誤差"]
    lack = [h for h in need if h not in t]
    if lack:
        return False, f"型.md に節が無い: {', '.join(lack)}"
    fixed = t.split("## 固定", 1)[1].split("\n## ", 1)[0]
    ls = fixed.splitlines()
    # 表の見出し行（すぐ下が |---| の行）と区切り行は数えない
    rows = [l for i, l in enumerate(ls) if l.startswith("|") and not re.match(r"^\|\s*:?-", l)
            and not (i + 1 < len(ls) and re.match(r"^\|\s*:?-", ls[i + 1]))]
    weak = []
    for l in rows:
        m = re.search(r"(\d+)\s*/\s*(\d+)", l)
        if not m or int(m.group(1)) < MIN_SHARE:
            weak.append(l[:40])
    if not rows:
        return False, "固定の節に表の行が無い"
    if weak:
        return False, f"固定の行で参考が{MIN_SHARE}本未満か『n/N』が無い: {len(weak)}行（例: {weak[0]}）"
    return True, f"固定{len(rows)}行"


def g4(d, st):
    child = st.get("child")
    p = os.path.join(SKILLS, child, "SKILL.md") if child else None
    t = read(p) if p else None
    if t is None:
        return False, f"子スキル {child} の SKILL.md が無い"
    n = t.count("\n") + 1
    if n > 500:
        return False, f"SKILL.md が {n}行（500行まで）"
    if not re.search(r"^- \[[ x]\]", t, re.M):
        return False, "最終確認のチェックボックス（- [ ]）が無い"
    errs = []
    for tool, extra in (("check-undug.py", []), ("check-md-format.py", ["--skill"])):
        code, out = sh(["python3", os.path.join(CREATOR, tool), p, *extra])
        if code != 0:
            errs.append(f"{tool} 終了コード{code}: {out.splitlines()[0] if out else ''}")
    if errs:
        return False, " / ".join(errs)
    return True, f"{n}行"


def g5(d, st):
    msgs, outs = [], []
    for k in (1, 2):
        ok, why, out = g5_one(d, st, f"結果_{k}.json")
        if not ok:
            return False, f"結果_{k}: {why}"
        msgs.append(f"{k}本目 {why}"); outs.append(out)
    if os.path.realpath(outs[0]) == os.path.realpath(outs[1]):
        return False, "結果_1 と結果_2 の出力が同じ物（別の参考か別の商品で2本要る）"
    return True, " / ".join(msgs)


def g5_one(d, st, name):
    t = read(os.path.join(d, "e2e", name))
    if t is None:
        return False, f"e2e/{name} が無い（子スキルを本物の入力で通していない）", None
    try:
        r = json.loads(t)
    except json.JSONDecodeError as e:
        return False, f"e2e/{name} が読めない: {e}", None
    boxes = r.get("最終確認", {})
    if not boxes:
        return False, f"{name} に『最終確認』の欄が無い", None
    child = read(os.path.join(SKILLS, st.get("child") or "", "SKILL.md")) or ""
    want = set(re.findall(r"^- \[[ x]\] ([A-Z]\d+)", child, re.M))
    if not want:
        return False, "子スキルの最終確認の箱の番号（- [ ] A1 …）が読めない", None
    lack = sorted(want - set(boxes))
    if lack:
        return False, f"{name} に無い箱: {', '.join(lack)}", None
    good = [k for k in want if boxes[k] in ("○", True)]
    why_x = [k for k in want if isinstance(boxes[k], str) and re.match(r"^×\s*\S{3,}", boxes[k])]
    ng = sorted(want - set(good) - set(why_x))
    if ng:
        return False, f"○でも理由つき×でもない箱: {', '.join(ng)}（×は「× <理由>」で書く）", None
    out = r.get("出力")
    if not out or not os.path.exists(os.path.expanduser(out)):
        return False, f"出力が無い: {out}", None
    return True, f"箱{len(want)}個: ○{len(good)}・理由つき×{len(why_x)}", os.path.expanduser(out)


REVIEW_KEYS = ["前の回の直し", "段ごとの効果", "質", "分かりやすさ"]   # 2026-10-10 18:20 審査の頼み方で「型の固定」を「質」に替えた（型は機械の検査が見る）
REVIEW_GOT = ["参考の段の表", "参考の画面", "出来た物の画面", "移植表", "最終確認"]


def newest(d, pat):
    fs = [f for f in os.listdir(d) if re.match(pat, f)]
    return sorted(fs, key=lambda f: [int(x) for x in re.findall(r"\d+", f)])[-1] if fs else None


def g6(d, st):
    """結果_<k>.json ごとに、審査_<k>_<回>.md と 読み手の目_<k>_<回>.md の一番新しい物を見る。
    審査: 1行目 PASS・「## 受け取った物」に決めた5つ・基準ごとの行に ○ か ×。読み手の目: 1行目 PASS（足した段に強・中が無い）。
    どちらも出来た物より新しい事。"""
    said = []
    for k in (1, 2):
        try:
            out = json.loads(read(os.path.join(d, "e2e", f"結果_{k}.json")) or "{}").get("出力")
        except json.JSONDecodeError:
            out = None
        out = os.path.expanduser(out) if out else None
        for kind, pat in (("審査", rf"審査_{k}_\d+\.md$"), ("読み手の目", rf"読み手の目_{k}_\d+\.md$")):
            f = newest(d, pat)
            if not f:
                return False, f"{k}本目の {kind}_{k}_<回>.md が無い"
            body = read(os.path.join(d, f)) or ""
            first = body.strip().splitlines()[:1]
            if not first or not first[0].strip().upper().startswith("PASS"):
                return False, f"{f} の1行目が PASS でない: {first[0][:60] if first else '空'}"
            if out and os.path.exists(out) and os.path.getmtime(out) > os.path.getmtime(os.path.join(d, f)) + 60:
                return False, f"{f} は出来た物より古い（直した後に通し直していない）"
            if kind == "審査":
                got = body.split("## 受け取った物", 1)[1].split("\n## ", 1)[0] if "## 受け取った物" in body else ""
                lack = [g for g in REVIEW_GOT if g not in got]
                if lack:
                    return False, f"{f} の「## 受け取った物」に無い: {', '.join(lack)}（入力が欠けても審査役は PASS を出すので）"
                miss = [c for c in REVIEW_KEYS if not re.search(rf"^.*{c}.*[○×]", body, re.M)]
                if miss:
                    return False, f"{f} に基準ごとの理由→○×が無い: {', '.join(miss)}"
            said.append(f)
    return True, "・".join(said)


def g7(d, st):
    child = st.get("child")
    t = read(os.path.join(SKILLS, child, "SKILL.md")) if child else ""
    if t and re.search(r"^#+\s*(しないこと|禁止|やらないこと|NG ?リスト|しない一覧)", t, re.M):
        return False, "子スキルに『しない一覧』の節がある。手順の中のその作業の位置に入れ直す"
    log = read(os.path.join(d, "直しの記録.md")) or ""
    rows = [l for l in log.splitlines() if l.startswith("- ")]
    need = len(st.get("fails", []))
    if len(rows) < need:
        return False, f"fail で記録した×が{need}件、直しの記録が{len(rows)}行（×ごとに、手順のどこに入れたかを1行）"
    if not rows:
        return True, "直し無し（fail の記録も0件）"
    bad = [l[:40] for l in rows if not re.search(r"手順\s*\d+", l)]
    if bad:
        return False, f"手順の番号を指していない直し {len(bad)}行（例: {bad[0]}）"
    nostop = [l[:40] for l in rows if not re.search(r"止める検査:\s*\S+", l)]
    if nostop:
        return False, f"『止める検査: <検査の項目名 か 見本の番号>』が無い直し {len(nostop)}行（例: {nostop[0]}）。文だけの直しは破れるので、落ちた物を必ず落とす検査か見本に結ぶ"
    return True, f"直し{len(rows)}行すべて手順に入れた"


def g8(d, st):
    t = read(os.path.join(d, "広告と型のつながり.md"))
    if t is None:
        return False, "広告と型のつながり.md が無い（飛び先へ飛ばしている広告を割っていない）"
    rows = [l for l in t.splitlines() if re.match(r"^\|\s*\d+\s*\|", l)]
    with_ad = [l for l in rows if re.search(r"ads/library/\?id=\d+|広告ライブラリ|https?://", l)]
    if len(with_ad) < 3:
        return False, f"広告の行が{len(with_ad)}本（出どころの URL つきで3本以上要る）"
    for need in ("組み立て", "飛び先"):
        if need not in t:
            return False, f"「{need}」の列が無い"
    return True, f"広告{len(with_ad)}本"


CHECKS = dict(G1=g1, G2=g2, G3=g3, G4=g4, G5=g5, G6=g6, G7=g7, G8=g8)


def write_goal(d, name, child):
    lines = [f"# GOAL: {name} の飛び先を、本人なしで写して作れる子スキル `{child}` を作る", "",
             "読む人: kata-tsukuru を回す Claude。", "読む時: 周回の頭に毎回。",
             "読まなくていい条件: なし。", "",
             "全部の箱が○になるまで回す。箱の判定は `python3 ~/.claude/skills/kata-tsukuru/scripts/goal.py check " + name + "` がする（手で○を付けない）。", ""]
    lines += [f"- [ ] {k} {v}" for k, v in BOXES]
    with open(os.path.join(d, "GOAL.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main(a):
    if len(a) < 2 or a[0] not in ("init", "check", "fail", "show", "reset"):
        print(__doc__); return 2
    cmd, name = a[0], a[1]
    d = run_dir(name)
    if cmd == "init":
        child = a[a.index("--子") + 1] if "--子" in a else f"{name}-copy"
        for sub in ("refs", "e2e"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        st = load_state(d) or {"name": name, "child": child, "round": 0, "fails": [], "started": time.strftime("%Y-%m-%d %H:%M")}
        st["child"] = child
        save_state(d, st)
        if not os.path.exists(os.path.join(d, "GOAL.md")):
            write_goal(d, name, child)
        print(f"作業場: {d}\n子スキル: {child}"); return 0
    st = load_state(d)
    if st is None:
        print(f"作業場が無い: {d}。先に init", file=sys.stderr); return 2
    if cmd == "reset":
        st["round"] = 0; st["streak"] = {}
        save_state(d, st); print("周回を0に戻した（×の記録は残す）"); return 0
    if cmd == "show":
        print(json.dumps(st, ensure_ascii=False, indent=1)); return 0
    if cmd == "fail":
        if len(a) < 4:
            print("使い方: goal.py fail <型> <箱> \"<理由>\"", file=sys.stderr); return 2
        box, why = a[2], a[3]
        st["round"] += 1
        st["fails"].append({"round": st["round"], "box": box, "why": why, "at": time.strftime("%H:%M")})
        save_state(d, st)
        same = [f for f in st["fails"] if f["box"] == box]
        same_why = [f for f in same if f["why"] == why]
        if len(same_why) >= 3:
            print(f"{box} が同じ理由で{len(same_why)}回×。8周を待たずに止める。本人に1行: 何の箱が何の理由で何回×で、何を試したか")
            return 3
        if len(same) >= 2:
            print(f"{box} が{len(same)}回目の×。同じやり方をもう一度回さない。新しい文脈の Opus のサブエージェントに、{box} の×の理由{len(same)}回分・出来た物・その箱を作る手順を渡し、「試みに共通する前提を1つ」「手順の問題か・道具が測れていないか・参考が足りないか」「直し方1案」を5行で返させてから直す（作った本人には自分の前提が見えない）")
        else:
            print(f"{box} の×を記録。理由を付けてその箱を作る手順に戻る")
        return 1
    # check
    if st["round"] >= MAX_ROUNDS:
        print(f"周回が上限（{MAX_ROUNDS}）。本人に1行: 何の箱が何回×で、何を試したか（`goal.py show {name}`）。本人が続けてよいと言ったら `goal.py reset {name}`"); return 3
    allok = True
    res = []
    for k, label in BOXES:
        try:
            ok, why = CHECKS[k](d, st)
        except Exception as e:      # 判定の道具が壊れた時は×として理由を出す（○にしない）
            ok, why = False, f"判定で例外: {type(e).__name__}: {e}"
        allok &= ok
        res.append((k, label, ok, why))
    # 周回は check では進めない。やり直しを決めて理由を記録した時（fail）だけ1周と数える
    # （2026-10-10 2回目: 作業の途中で何度も check を走らせ、そのたびに数えて上限8に当たった）
    # 同じ箱が、作った物があるのに続けて×（「無い」以外の理由）なら数える
    streak = st.setdefault("streak", {})
    for k, _, ok, why in res:
        streak[k] = 0 if ok or "無い" in why else streak.get(k, 0) + 1
    save_state(d, st)
    print(f"周回 {st['round']}")
    for k, label, ok, why in res:
        print(f"- [{'x' if ok else ' '}] {k} {label}  → {'○' if ok else '×'} {why}")
        if streak.get(k, 0) >= 2:
            print(f"   ⚠ {k} は{streak[k]}回続けて×。同じやり方をもう一度回さない: 原因を割り、その箱を作る手順か道具を直し、`goal.py fail {name} {k} \"<理由>\"` と直しの記録に1行足してから戻る")
    # GOAL.md の箱も同じ判定で塗り直す（手で付けた○は残さない）
    g = read(os.path.join(d, "GOAL.md")) or ""
    for k, label, ok, why in res:
        g = re.sub(rf"^- \[[ x]\] {k} .*$", f"- [{'x' if ok else ' '}] {k} {label}", g, flags=re.M)
    with open(os.path.join(d, "GOAL.md"), "w") as f:
        f.write(g)
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
