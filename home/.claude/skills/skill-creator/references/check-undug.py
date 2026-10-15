#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""掘り残し検査 — 書いた物の中で「まだ1段割れていない所」を機械で拾う。

対象: .md / .canvas（ノードの text を1行ずつ）/ 日本語でも英語でも見る
拾うのは6種類:
  A 判断語に測り方が無い（良い・適切…。「しっかり」「雰囲気」等の禁止語は数字があっても拾う）
  B 手順の行が動詞だけで道具が無い（確認する・見る…に コマンド/URL/スキル が付いていない）
  C 道具名を「〜で」「〜から」と使っているのに、ファイルのどこにも触り方が無い
  D 数が曖昧（たくさん・ある程度…）
  E 型の文書・正本で3回以上使う言葉が、その文書でも正本でも定義されていない（普通のスキルでは鳴らない）
  F 型の文書（先頭に <!-- 型 -->）に固有名詞（パス・MCP名・スキル名・製品名）が出ている

免除: 行末 <!-- 掘った: 理由 --> （理由4文字以上。理由の無い <!-- 掘った --> は免除しない）
使い方: python3 check-undug.py <file> [...]    exit 1 = 掘り残しあり
        python3 check-undug.py --hook          （PostToolUse Write|Edit。stdin の JSON を読む）
        python3 check-undug.py --recent        （PostToolUse Bash。前回以降に更新された scope 内の .md/.canvas を検査）
        python3 check-undug.py --baseline <files>  （今の件数を記録。以後は「増えた時だけ」exit 2）
  G 母数の無い断定（多い・一番・ほとんど に n が無い）
"""
import re, sys, json, pathlib

HERE = pathlib.Path(__file__).parent
CANON = pathlib.Path.home() / "Documents/Obsidian Vault/ec/構造/_考え方-コンポーネント分解.md"

# ---- 語彙 ----
# 数字があっても許さない語（測れない言葉そのもの）
BANNED_JA = r"(しっかり|ちゃんと|きちんと|適切|十分|なるべく|できるだけ|雰囲気|感覚で|なんとなく|たぶん|おそらく|気合|センス|望ましい|適宜|必要に応じて|うまく|いい感じ|バランス)"
BANNED_EN = r"\b(properly|appropriately|sufficiently|carefully|as needed|as appropriate|if necessary|preferably|roughly|nicely|good enough|well-structured)\b"
# 近くに数字・線があれば許す語
JUDGE_JA = r"(良い|良く|よい|強い|弱い|高い|低い|自然な|高品質|正しく|刺さる|印象)"
CLAIM_JA = r"(多い|少ない|一番|ほとんど|大半|最も)"  # 母数が要る断定
JUDGE_EN = r"\b(good|better|best|strong|weak|many|few|high|low|clear|effective|quality|robust)\b"
VERB_JA = r"(確認する|確認し|見る|調べる|探す|取得する|取る|判断する|チェックする|測る(?!手段)|評価する|検証する)"
VERB_EN = r"\b(check|verify|inspect|review|look at|find|measure|evaluate|validate)\b"
VAGUE_JA = r"(たくさん|いくつか|ある程度|複数の|何本か|何件か|数本|数件|かなり|めっちゃ|色々|いろいろ|など|等を|等の)"
VAGUE_EN = r"\b(several|a few|some of|a lot of|various|etc\.?|and so on)\b"

# 判断語の周り（前後 24 文字）にこれがあれば「測っている」
MEASURE = re.compile(r"(\d+(\.\d+)?\s*(件|本|回|人|秒|分|時間|日|語|字|文字|px|%|％|円|倍|段|枚|行|通り)|\d+\+|\d+(\.\d+)?x\b|>=?\s*\d|<=?\s*\d|\d+\s*(or (fewer|more|less)|以上|以下)|\d+\s*(chars?|characters?|words?|sec(onds?)?|min(utes?)?|days?|items?|results?|px|%)|\d+\s*[-–〜]\s*\d+|[○×]|以上|以下|未満|超え|0/1|はい/いいえ|yes/no)", re.I)
# 道具の印
TOOLED = re.compile(r"(`[^`]+`|https?://\S+|(^|\s)/[a-z][a-z0-9-]{2,}|mcp__\w+|\S+\.(py|sh|mjs|js|md|json)\b|\[\[[^\]]+\]\])")
# 手順の行
STEP = re.compile(r"^\s*(-|\*|\d+\.|\d+\))\s")
# 道具として使っている（値として並べただけの物は拾わない）
TOOL_USE_JA = r"\s*(で|から|を叩|を使|を開|に投げ|経由|で見|で取)"

def load_tools():
    f = HERE / "undug-tools.txt"
    if f.exists():
        return [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return []

def canon_terms():
    """正本の「言葉の定義」表にある語（他の文書ではこれを再定義しなくていい）"""
    if not CANON.exists():
        return set()
    out = set()
    in_tbl = False
    for l in CANON.read_text(encoding="utf-8").splitlines():
        if l.startswith("### 言葉の定義"):
            in_tbl = True; continue
        if in_tbl and l.startswith("### "):
            break
        if in_tbl and l.startswith("|") and l.count("|") >= 3:
            cell = l.split("|")[1].strip()
            if cell and cell not in ("言葉", "---") and not set(cell) <= set("-: "):
                out.add(re.sub(r"（.*?）", "", cell).strip())
    return out

METHOD_TERMS = ["0/1", "部品", "変数", "定義", "実物", "判定", "関門", "掘る", "例", "型", "枠", "差分", "変種", "成功条件", "裁定", "道具",
                "飽和", "領域", "受け手", "区間", "入力項目", "印", "記録", "推測", "仕事", "出どころ", "判別", "判定不能", "落とす", "残す", "貯める", "割る"]

def lines_of(path):
    """(行番号ラベル, 本文) の列。canvas はノードごと"""
    p = pathlib.Path(path)
    if p.suffix == ".canvas":
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
        out = []
        for n in d.get("nodes", []):
            body = (n.get("text") or "") + ("\n" + n["label"] if n.get("label") else "")
            for i, t in enumerate(body.split("\n"), 1):
                out.append((f"node {n.get('id','?')[:6]}:{i}", t))
        for e in d.get("edges", []):
            if e.get("label"):
                out.append((f"edge {e.get('id','?')[:6]}", e["label"]))
        return out
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"読めない: {e}")
    return [(str(i), l) for i, l in enumerate(txt.split("\n"), 1)]

def exempt(line):
    m = re.search(r"<!--\s*掘った\s*[:：]\s*(.{4,}?)\s*-->", line)
    if not m:
        return False
    reason = m.group(1)
    return bool(MEASURE.search(reason) or re.search(r"`[^`]+`|https?://|mcp__|/[a-z][a-z0-9-]{2,}", reason))

def check(path):
    rows = lines_of(path)
    hits = []
    if not rows:
        return hits
    text = "\n".join(t for _, t in rows)
    head = "\n".join(t for _, t in rows[:5])
    is_type_doc = bool(re.search(r"<!--\s*型\s*-->", head)) or ("/ec/構造/" in str(pathlib.Path(path).resolve()) and not re.search(r"<!--\s*例\s*-->", head))
    ja_lines = sum(1 for _, t in rows if re.search(r"[ぁ-んァ-ン一-龥]", t))
    incode = False
    infm = rows and rows[0][1].strip() == "---"
    n_exempt = 0
    plain = []  # (label, core, body, is_heading)
    for i, (lab, ln) in enumerate(rows):
        s = ln.strip()
        if infm:
            if i > 0 and s == "---":
                infm = False
            continue
        if s.startswith("```"):
            incode = not incode; continue
        if incode or not s:
            continue
        # 機械が書いた逐語の表（絵の埋め込み＋「」の1行）は検査しない。言い換えると出どころが変わる
        if "![[" in s and "frames/" in s and "「" in s:
            continue
        if exempt(ln):
            n_exempt += 1
            if n_exempt > 3:
                hits.append((lab, "免除が多すぎる", "掘った", "1ファイル3件まで。4件目からは直す"))
            continue
        # 表の区切り行・ヘッダ行（次の行が |---| の時だけ）
        if set(s) <= set("|-: "):
            continue
        if s.startswith("|") and i + 1 < len(rows) and set(rows[i + 1][1].strip()) <= set("|-: ") and rows[i + 1][1].strip():
            continue
        is_heading = s.startswith("#")
        core = re.sub(r"^\s*(#+|\d+\.|\d+\)|[-*+])\s*", "", s)
        plain.append((lab, core, s, is_heading))

    for lab, core0, body, is_heading in plain:
        core = re.sub(r"`[^`]*`", "`x`", core0)  # コード片の中の語は判断語ではない
        # 「良い」を禁止・引用として書いている行は A を免除
        citing = bool(re.search(r"(禁止|使わない|書かない|やめる|は×|はダメ|で片付けない|ではなく|✗|×|十分条件|必要条件|にしない|としない)", core))
        quoted_phrases = [q for q in re.findall(r"「([^」]*)」", core) if len(q) >= 4]  # 4文字以上の引用は例示。判断語を免除
        # A-1 禁止語（数字があっても拾う）
        cited_words = [q for q in re.findall(r"「([^」]*)」", core) if len(q) <= 6] if body.startswith("|") else []
        for pat in (BANNED_JA, BANNED_EN):
            m = re.search(pat, core, re.I)
            if m and not citing and not any(m.group(0) in q for q in cited_words):
                hits.append((lab, "A 測れない言葉", m.group(0), "何を・いくつ・どう測るかに置き換える")); break
        # A-2 判断語（近くに測り方が無ければ拾う）
        for pat in (JUDGE_JA, JUDGE_EN):
            for m in re.finditer(pat, core, re.I):
                w = m.group(0)
                if re.search(r"(て|で|も|なくて)" + re.escape(w) + r"$", core[max(0, m.start()-3):m.end()]) and w in ("よい", "良い"):
                    continue  # 「〜てよい」は許可の意味
                if citing or any(w in q for q in quoted_phrases) or re.search(re.escape(w) + r"-[a-z]", core, re.I) or re.search(r"[a-z]-" + re.escape(w), core, re.I):
                    continue
                win = core[max(0, m.start()-40): m.end()+40]
                if not MEASURE.search(win):
                    hits.append((lab, "A 判断語に測り方が無い", w, "近くに数字と単位、または○×の線を置く")); break
        # G 母数の無い断定
        mg = re.search(CLAIM_JA, core)
        if mg and not citing and not re.search(r"\d", core) and not any(mg.group(0) in q for q in quoted_phrases):
            hits.append((lab, "G 母数が無い断定", mg.group(0), "n を横に書く（何件中何件か）"))
        # B 手順の行に道具が無い
        if STEP.match(body) and not is_heading and not citing and not re.search(r"(確認し|見|調べ|探さ|取ら|判断し|測ら|評価し|検証し)ない", core):
            for pat in (VERB_JA, VERB_EN):
                m = re.search(pat, core, re.I)
                if m and not TOOLED.search(core):
                    before = core[max(0, m.start()-4):m.start()]
                    if re.search(r"(合意|許可|連絡|近道|責任|距離|バランス|時間)を$", before) or re.search(r"[人者手]が$", before):
                        continue
                    hits.append((lab, "B 動詞だけで道具が無い", m.group(0), "何で確かめるかを1つ名指しする（コマンド / URL / スキル）")); break
        # D 数が曖昧
        for pat in (VAGUE_JA, VAGUE_EN):
            m = re.search(pat, core, re.I)
            if m:
                hits.append((lab, "D 数が曖昧", m.group(0), "数字に置き換える")); break
        # F 型の文書に固有名詞
        if is_type_doc:
            m = re.search(r"(mcp__\w+|(^|\s)/[a-z][a-z0-9-]{2,}|~/\S+|ec/\S+|\.claude/\S+|GetHookd|Meta|Shopify|Clarity|Notion|Palmier|Higgsfield)", core)
            if m:
                hits.append((lab, "F 型の文書に固有名詞", m.group(0).strip(), "例ファイルへ出す。型には『確かめたい事実』だけ残す"))

    # C 道具を使っているのに触り方が無い
    for t in load_tools():
        uses = [c for _, c, _, _ in plain if re.search(re.escape(t) + TOOL_USE_JA, c)]
        if uses and not any(TOOLED.search(c) for c in uses):
            hits.append(("全体", "C 道具の触り方が無い", t, "その道具をどう叩くかを1行足す（コマンド / MCP名 / スキル名）"))

    # E 言葉が定義されていない（型の文書と正本だけ。普通のスキルでは鳴らさない）
    canon = canon_terms()
    is_canon = pathlib.Path(path).resolve() == CANON.resolve() if CANON.exists() else False
    if not (is_canon or is_type_doc):
        return hits, (ja_lines, len(rows))
    cands = set()
    if is_canon:
        cands.update(METHOD_TERMS)
    for m in re.finditer(r"\*\*([^*\n]{2,7})\*\*|「([^」\n]{2,7})」", text):
        w = (m.group(1) or m.group(2)).strip()
        if not re.search(r"[。、？!?]|^\d|^[ぁ-ん]{1,2}$", w):
            cands.add(w)
    headings = {re.sub(r"^#+\s*|（.*?）", "", c).strip() for _, c, b, h in plain if h}
    for w in sorted(cands):
        n = text.count(w)
        if n < 3 or w in headings or any(w in h for h in headings):
            continue
        occ = [c for _, c, _, _ in plain if w in c]
        if occ and all(re.search(r"(禁止|使わない|書かない|✗|×)", c) for c in occ):
            continue
        if not is_canon and w in canon:
            continue
        defined = any((c.startswith("|") and c.count("|") >= 3 and w == re.sub(r"（.*?）", "", c.split("|")[1]).strip())
                      or re.search(re.escape(w) + r"\s*[=＝]", c) or (w + "とは") in c
                      for _, c, _, _ in plain)
        if not defined:
            hits.append(("全体", "E 言葉が定義されていない", w, f"「言葉の定義」の表に1行足す（{n}回使っている）"))
    return hits, (ja_lines, len(rows))

def report(files):
    total = 0
    for f in files:
        p = pathlib.Path(f)
        if not p.exists():
            print(f"{f}: 無い"); continue
        res = check(f)
        if not res:
            print(f"{f}: 対象外（読めない）"); continue
        hits, (ja, n) = res
        tag = "" if ja else "（日本語0行。英語の語彙だけで見た）"
        if not hits:
            print(f"{f}: 掘り残し なし {tag}"); continue
        total += len(hits)
        print(f"{f}: 掘り残し {len(hits)}件 {tag}")
        for lab, kind, word, fix in hits:
            print(f"  {lab:>10}  {kind}  「{word}」 → {fix}")
    return 1 if total else 0

SCOPE_DIRS = ["Documents/Obsidian Vault", "Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault",
              ".claude", "Claude Code", "Desktop", "CLAUDE.md"]
STATE = pathlib.Path.home() / ".claude" / ".undug-state.json"

def in_scope(fp):
    home = pathlib.Path.home()
    try:
        rp = pathlib.Path(fp).resolve()
    except Exception:
        return False
    if rp.suffix not in (".md", ".canvas"):
        return False
    # voc-*.md は客の原文そのもの。書いた文ではないので掘り残しを測らない（2026-10-05）
    if rp.name.startswith("voc-"):
        return False
    parts = set(p.lower() for p in rp.parts)
    # 参考を保存する.py が出す段.md は参考の原文の写し。書いた文ではないので測らない（2026-10-11 型さがしの試験で毎回止まった）
    if rp.name == "段.md" and parts & {"参考", "_さがし"}:
        return False
    # 審査を回す.py が書く 審査_<回>.md は編集長の判定の原文の写し。言い換えると直す中身が変わるので測らない（2026-10-15）
    if re.fullmatch(r"審査_\d+\.md", rp.name) or rp.name == "検査の結果.md":
        return False
    if parts & {"tmp", "scratchpad", "node_modules", ".git", "私的", "_archive", "plugins", "cache", ".trash", ".obsidian", "backups", "_倉庫"}:
        return False
    for d in SCOPE_DIRS:
        if str(rp).startswith(str(home / d)):
            return True
    return False

def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"baseline": {}, "last_recent": 0}

def save_state(st):
    try:
        STATE.write_text(json.dumps(st, ensure_ascii=False))
    except Exception:
        pass

def run_one(fp, st):
    """戻り: (メッセージ行 or None)。ベースライン以下なら黙る、増えたら出す"""
    try:
        res = check(fp)
    except Exception as e:
        return [f"[掘り残し検査] 実行できなかった: {fp}: {e}"]
    if not res:
        return None
    hits, _ = res
    key = str(pathlib.Path(fp).resolve())
    base = st["baseline"].get(key)
    if not hits:
        st["baseline"][key] = 0
        return None
    if base is not None and len(hits) <= base:
        st["baseline"][key] = len(hits)
        return None
    lines = [f"[掘り残し検査] {fp}: {len(hits)}件" + (f"（前回 {base}件から増えた）" if base is not None else "") + "。直してから次へ進む（免除は行末 <!-- 掘った: 数字か`コマンド`入りの理由 -->、1ファイル3件まで）"]
    for lab, kind, word, fix in hits[:12]:
        lines.append(f"  {lab}  {kind} 「{word}」 → {fix}")
    if len(hits) > 12:
        lines.append(f"  …他 {len(hits)-12} 件。python3 {__file__} \"{fp}\" で全部出る")
    st["baseline"][key] = len(hits)
    return lines

def hook_main():
    """PostToolUse(Write|Edit): stdin の JSON から file_path を取り、対象なら検査。掘り残しが増えていれば exit 2"""
    try:
        d = json.load(sys.stdin)
    except Exception:
        return 0
    fp = (d.get("tool_input") or {}).get("file_path") or ""
    if not fp or not in_scope(fp):
        return 0
    st = load_state()
    out = run_one(fp, st)
    save_state(st)
    if out:
        print("\n".join(out), file=sys.stderr); return 2
    return 0

def recent_main():
    """PostToolUse(Bash): 前回の検査以降に更新された scope 内の .md/.canvas を全部検査（Bash 経由の書き込みを拾う）"""
    import os, time
    st = load_state()
    since = st.get("last_recent") or (time.time() - 300)
    st["last_recent"] = time.time()
    home = pathlib.Path.home()
    found = []
    for d in SCOPE_DIRS:
        root = home / d
        if root.is_file():
            if root.stat().st_mtime > since: found.append(str(root))
            continue
        if not root.is_dir():
            continue
        for dp, dns, fns in os.walk(root):
            dns[:] = [x for x in dns if x.lower() not in ("node_modules", ".git", "tmp", "scratchpad", ".obsidian", ".trash", "plugins", "cache")]
            for fn in fns:
                if fn.endswith((".md", ".canvas")):
                    fpath = os.path.join(dp, fn)
                    try:
                        if os.stat(fpath).st_mtime > since and in_scope(fpath):
                            found.append(fpath)
                    except Exception:
                        pass
    msgs = []
    for fp in found[:20]:
        out = run_one(fp, st)
        if out: msgs.extend(out)
    save_state(st)
    if msgs:
        print("\n".join(msgs), file=sys.stderr); return 2
    return 0

def baseline_main(paths):
    """今の件数をベースラインとして記録（既存の負債を認めて、増加だけを止める）"""
    st = load_state()
    n = 0
    for fp in paths:
        try:
            hits, _ = check(fp)
        except Exception:
            continue
        st["baseline"][str(pathlib.Path(fp).resolve())] = len(hits); n += 1
    save_state(st)
    print(f"ベースライン記録: {n}ファイル")
    return 0

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--hook":
        sys.exit(hook_main())
    if len(sys.argv) >= 2 and sys.argv[1] == "--recent":
        sys.exit(recent_main())
    if len(sys.argv) >= 3 and sys.argv[1] == "--baseline":
        sys.exit(baseline_main(sys.argv[2:]))
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    sys.exit(report(sys.argv[1:]))
