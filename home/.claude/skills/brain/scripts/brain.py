#!/usr/bin/env python3
"""広告脳（Vault内の知識置き場）の骨組みを作る・台帳を書く・整合を検査する。

Claudeが読む量を増やさないために、検査はコードでやる。

  brain.py init                       フォルダと _map.md / _log.md を作る
  brain.py log --slug S --claims N [--status 取り込み済み|保留|却下]
  brain.py check                      未統合・出典切れ・地図落ちを洗い出す
  brain.py stats                      未初期化なら終了コード4
"""
import argparse
import json
import os
import re
import sys
import time

BRAIN = os.environ.get("ADS_BRAIN") or os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/"
    "Obsidian Vault/ec/wiki/ads-brain")

STATUSES = ["取り込み済み", "保留", "却下"]

MAP_HEADER = """# 広告脳 地図

**制作の入力になるのは playbooks/ だけ。** sources/ は読まない（証拠の保管庫）。

読み方は2段。
1. この地図で、今から作るものに要る playbook を選ぶ
2. その playbook だけ読む。足りなければ playbook の出典から source を1本だけ開く

| playbook | いつ読む | 確度 | 更新 |
|---|---|---|---|
<!-- BRAIN:MAP -->

## 取り込み待ち
<!-- BRAIN:PENDING -->
"""

LOG_HEADER = """# 取り込み台帳

同じ教材を二度取り込まないためのリスト。`/study` が追記する。

状態の意味
- **取り込み済み** … source を書いた。playbook への統合が済んでいなければ check が拾う
- **保留** … 既存の知識と食い違っていて、まだ裁定していない。playbook には入れない
- **却下** … 使わないと決めた。check は無視する

| 日付 | slug | 種別 | 主張数 | 状態 | 出所 |
|---|---|---|---|---|---|
"""


def paths():
    return {
        "root": BRAIN,
        "playbooks": os.path.join(BRAIN, "playbooks"),
        "sources": os.path.join(BRAIN, "sources"),
        "raw": os.path.join(BRAIN, "raw"),
        "map": os.path.join(BRAIN, "_map.md"),
        "log": os.path.join(BRAIN, "_log.md"),
        "conflicts": os.path.join(BRAIN, "_conflicts.md"),
    }


def read(path):
    return open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else ""


def initialized():
    p = paths()
    return os.path.isdir(p["playbooks"]) and os.path.isdir(p["sources"]) \
        and os.path.exists(p["map"]) and os.path.exists(p["log"])


def cmd_init(_):
    p = paths()
    for k in ("playbooks", "sources", "raw"):
        os.makedirs(p[k], exist_ok=True)
    if not os.path.exists(p["map"]):
        open(p["map"], "w", encoding="utf-8").write(MAP_HEADER)
    if not os.path.exists(p["log"]):
        open(p["log"], "w", encoding="utf-8").write(LOG_HEADER)
    if not os.path.exists(p["conflicts"]):
        open(p["conflicts"], "w", encoding="utf-8").write(
            "# 教材どうしが食い違った所\n\n"
            "同じ論点で違うことを言っている教材を並べて、どっちを採るか決めた記録。\n"
            "裁定していない論点は playbook に入れない（台帳では 保留 にする）。\n\n"
            "| 論点 | A（出典） | B（出典） | 採用 | 理由 | 日付 |\n"
            "|---|---|---|---|---|---|\n")
    open(os.path.join(p["raw"], "README.md"), "w", encoding="utf-8").write(
        "文字起こしの保管庫。Claudeは読まない。slice.py と grep だけが触る。\n")
    print(json.dumps({"brain": BRAIN, "created": True}, ensure_ascii=False))


def front(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    d = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def claim_ids(source_body):
    """source の「主張」節に実在する claim ID を集める。
    旧形式（c01. 本文）と新形式（c01 の行の下に箇条書き）の両方を読む。"""
    sec = re.search(r"##\s*主張(?:リスト)?(.*?)(\n##\s|\Z)", source_body, re.S)
    text = sec.group(1) if sec else source_body
    return set(re.findall(r"^\s*(c\d+)(?:[.\s]|$)", text, re.M))


def claim_fields(source_body):
    """主張ごとに、必須欄が埋まっているかを見る。
    根拠: Chi et al. 1989（自己説明）と Woloshyn et al. 1990（精緻化質問）から
    「なぜそうなるのか」を必須にしている。空欄で通すと効果が消える。"""
    sec = re.search(r"##\s*主張(?:リスト)?(.*?)(\n##\s|\Z)", source_body, re.S)
    if not sec:
        return {}
    out, cur = {}, None
    for line in sec.group(1).split("\n"):
        m = re.match(r"^\s*(c\d+)\s*$", line)
        if m:
            cur = m.group(1)
            out[cur] = set()
            continue
        m = re.match(r"^\s*[-*]\s*([^:：]+)[:：]\s*(\S.*)$", line)
        if m and cur:
            out[cur].add(m.group(1).strip())
    return out


def log_rows():
    """台帳を行として読む。slug -> status"""
    rows = {}
    for line in read(paths()["log"]).split("\n"):
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 7 and cells[2] and cells[2] not in ("slug", "---"):
            rows[cells[2]] = cells[5]
    return rows


def cmd_log(a):
    if not initialized():
        cmd_init(a)
    p = paths()
    if a.status not in STATUSES:
        print(f"LOG_FAILED: 状態は {STATUSES} のどれかにすること", file=sys.stderr)
        sys.exit(2)

    # source が実体として成立しているか確認してから台帳に載せる。
    # 載せてしまうと次回は重複判定で弾かれ、取りこぼしに気づけなくなる
    if a.status == "取り込み済み":
        sp = os.path.join(p["sources"], a.slug + ".md")
        if not os.path.exists(sp):
            print(f"LOG_FAILED: sources/{a.slug}.md が無い。"
                  "source を書いてから台帳に載せること", file=sys.stderr)
            sys.exit(3)
        body = read(sp)
        f = front(body)
        if f.get("slug") != a.slug:
            print(f"LOG_FAILED: sources/{a.slug}.md の frontmatter の slug が "
                  f"'{f.get('slug')}' でファイル名と合っていない", file=sys.stderr)
            sys.exit(4)
        ids = claim_ids(body)
        if not ids:
            print(f"LOG_FAILED: sources/{a.slug}.md に主張リスト（c01. 形式）が無い",
                  file=sys.stderr)
            sys.exit(5)
        if a.claims and str(a.claims) != str(len(ids)):
            print(f"LOG_FAILED: --claims {a.claims} だが、ファイルにある主張は "
                  f"{len(ids)}個（{sorted(ids)[:3]}...）。数を合わせること", file=sys.stderr)
            sys.exit(6)
        a.claims = len(ids)

    if a.slug in log_rows():
        print(json.dumps({"status": "DUPLICATE", "slug": a.slug,
                          "note": "この教材は取り込み済み。状態を変えるなら台帳の行を直すこと"},
                         ensure_ascii=False))
        sys.exit(1)

    open(p["log"], "a", encoding="utf-8").write(
        f"| {time.strftime('%Y-%m-%d')} | {a.slug} | {a.kind} | {a.claims} | "
        f"{a.status} | {a.source[:80]} |\n")
    print(json.dumps({"status": "LOGGED", "slug": a.slug, "claims": a.claims,
                      "state": a.status}, ensure_ascii=False))


def map_entries(map_body):
    """地図の表から playbook 名を取る。単なる部分一致にしない。"""
    names = set()
    for line in map_body.split("\n"):
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 5 and cells[1] and cells[1] not in ("playbook", "---"):
            names.add(re.sub(r"^\[\[|\]\]$", "", cells[1]).strip())
    return names


def cmd_check(_):
    p = paths()
    if not initialized():
        print("CHECK_FAILED: 広告脳がまだ無い。先に brain.py init", file=sys.stderr)
        sys.exit(2)

    pbs, srcs = {}, {}
    for f in sorted(os.listdir(p["playbooks"])):
        if f.endswith(".md"):
            pbs[f[:-3]] = read(os.path.join(p["playbooks"], f))
    for f in sorted(os.listdir(p["sources"])):
        if f.endswith(".md"):
            srcs[f[:-3]] = read(os.path.join(p["sources"], f))

    mapped = map_entries(read(p["map"]))
    status = log_rows()
    issues = []

    # どの playbook が、どの source を引いているか（frontmatter と出典の両方から）
    cited = {}
    # 日本語の本文は全角括弧で書かれる。半角だけ見ていると検査が素通りする
    # （2026-08-14 のE2Eで発覚）
    cite = re.compile(r"[(（|\s]([\w\-.一-鿿ぁ-ヿ]+)#(c\d+)")
    for name, body in pbs.items():
        f = front(body)
        listed = re.findall(r"[\w\-一-鿿ぁ-ヿ.]+",
                            f.get("sources", "").strip("[]"))
        for sid in listed:
            cited.setdefault(sid, set())
        for sid, cid in cite.findall(body):
            cited.setdefault(sid, set()).add(cid)
            if sid not in srcs:
                issues.append({"type": "出典切れ", "target": f"playbooks/{name}.md",
                               "detail": sid,
                               "fix": "その教材が sources/ に無い。IDの綴りか取り込み漏れ"})
            elif cid not in claim_ids(srcs[sid]):
                issues.append({"type": "主張ID違い", "target": f"playbooks/{name}.md",
                               "detail": f"{sid}#{cid}",
                               "fix": "その番号の主張が source に無い。番号を直す"})

    # 1. 地図に載っていない playbook（Claudeが見つけられない＝存在しないのと同じ）
    for name in pbs:
        if name not in mapped:
            issues.append({"type": "地図落ち", "target": f"playbooks/{name}.md",
                           "fix": "_map.md の表に1行足す"})

    # 2. 地図にあるのに実体が無い playbook
    for name in mapped:
        if name not in pbs:
            issues.append({"type": "地図の幽霊", "target": f"_map.md の {name}",
                           "fix": "playbookが無い。行を消すか、playbookを作る"})

    # 3. 未統合（保留・却下は終端状態なので対象外）
    for name in srcs:
        st = status.get(name, "取り込み済み")
        if st in ("保留", "却下"):
            continue
        if name not in cited:
            issues.append({"type": "未統合", "target": f"sources/{name}.md",
                           "fix": "/brain で playbook に反映するか、"
                                  "裁定できないなら台帳の状態を 保留 にする"})

    # 4. 台帳に無い source（どこから来たか分からない知識）
    for name in srcs:
        if name not in status:
            issues.append({"type": "台帳落ち", "target": f"sources/{name}.md",
                           "fix": "brain.py log で台帳に載せる"})

    # 5. 確度が書かれていない playbook
    for name, body in pbs.items():
        f = front(body)
        if f.get("confidence") not in ("実証あり", "教材のみ", "未検証"):
            issues.append({"type": "確度なし", "target": f"playbooks/{name}.md",
                           "fix": "frontmatterに confidence: 実証あり|教材のみ|未検証"})

    # 5b. 転移に要る欄が無い playbook
    # 根拠: Gick & Holyoak 1983（共通の型が無いと転移しない）、
    #       Catrambone 1998（サブゴール見出し）、Renkl et al. 1998（お手本）
    for name, body in pbs.items():
        if not re.search(r"^##\s*共通の型", body, re.M):
            issues.append({"type": "型なし", "target": f"playbooks/{name}.md",
                           "fix": "「## 共通の型」を書く。これが無いと別の商品に使えない"
                                  "（Gick & Holyoak 1983）"})
        if not re.search(r"^###\s*サブゴール", body, re.M):
            issues.append({"type": "サブゴールなし", "target": f"playbooks/{name}.md",
                           "fix": "手順を「### サブゴールN: 〜」で束ねる（Catrambone 1998）"})
        if not re.search(r"^##\s*お手本", body, re.M):
            issues.append({"type": "お手本なし", "target": f"playbooks/{name}.md",
                           "fix": "「## お手本」に現物を1つ。無いなら『まだ無い』と書く"
                                  "（Renkl et al. 1998）"})
        if not re.search(r"^##\s*根拠と確度", body, re.M):
            issues.append({"type": "根拠表なし", "target": f"playbooks/{name}.md",
                           "fix": "「## 根拠と確度」の表を書く。ルールごとに 仮説/定説/実証 を出す"})
        else:
            # 出典1本のルールを「定説」にしていないか。
            # 表の走査は「根拠と確度」の節に限る（他の4列の表を誤検知しないため）
            sec = re.search(r"##\s*根拠と確度(.*?)(\n##\s|\Z)", body, re.S)
            table = sec.group(1) if sec else ""
            if re.search(r"手順\s*\d", table):
                issues.append({
                    "type": "手順番号への参照", "target": f"playbooks/{name}.md",
                    "fix": "根拠と確度の表で「手順N」と番号で指さない。手順を1つ挿入すると"
                           "全部ズレるのに、検査では気づけない。ルール名で指すこと"})
            for row in re.findall(r"^\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|\s*$", table, re.M):
                cites, backing, state = row[1], row[2].strip(), row[3].strip()
                n = len(re.findall(r"#c\d+", cites))
                if state in ("定説", "実証") and n < 2:
                    issues.append({
                        "type": "裏付け不足", "target": f"playbooks/{name}.md",
                        "detail": f"{cites.strip()[:40]} を {state} にしている",
                        "fix": "独立した出典2本以上でないと定説にしない"
                               "（1例では型ができない: Gick & Holyoak 1983）"})

    # 5c. source の必須欄が空
    for name, body in srcs.items():
        fields = claim_fields(body)
        ids = claim_ids(body)
        if ids and not fields:
            # 旧書式（c01. 本文）は欄の検査が素通りしてしまう。素通りさせない
            issues.append({"type": "旧書式のsource", "target": f"sources/{name}.md",
                           "fix": "主張を新書式に直す（c01 の行の下に "
                                  "「- 何を言っているか:」「- なぜそうなるのか:」"
                                  "「- どこまで効くか:」）。旧書式だと欄の検査が効かない"})
            continue
        if not re.search(r"^##\s*この教材が答えている問い", body, re.M):
            issues.append({"type": "問いなし", "target": f"sources/{name}.md",
                           "fix": "「## この教材が答えている問い」を書く"})
        for cid, got in fields.items():
            need = {"何を言っているか", "なぜそうなるのか", "どこまで効くか"}
            missing = need - got
            if missing:
                issues.append({"type": "主張の欄が欠けている",
                               "target": f"sources/{name}.md",
                               "detail": f"{cid}: {'/'.join(sorted(missing))}",
                               "fix": "書いていないなら『理由の記載なし』『境界の記載なし』"
                                      "と明示する。空欄で通さない（Chi et al. 1989）"})

    # 6. 太りすぎ playbook（読む量が増えると使われなくなる）
    for name, body in pbs.items():
        if len(body) > 8000:
            issues.append({"type": "太りすぎ", "target": f"playbooks/{name}.md",
                           "detail": f"{len(body):,}字",
                           "fix": "8000字を超えたら分割する。長いplaybookは制作で読まれない"})

    print(json.dumps({
        "brain": BRAIN, "playbooks": len(pbs), "sources": len(srcs),
        "保留": sum(1 for v in status.values() if v == "保留"),
        "却下": sum(1 for v in status.values() if v == "却下"),
        "issues": issues, "issue_count": len(issues),
    }, ensure_ascii=False, indent=1))
    sys.exit(3 if issues else 0)


def cmd_stats(_):
    if not initialized():
        print("STATS_FAILED: 広告脳が未初期化。brain.py init を実行すること", file=sys.stderr)
        sys.exit(4)
    p = paths()
    raw = sum(os.path.getsize(os.path.join(p["raw"], f))
              for f in os.listdir(p["raw"]) if f.endswith(".txt")) \
        if os.path.isdir(p["raw"]) else 0
    print(json.dumps({
        "playbooks": len([f for f in os.listdir(p["playbooks"]) if f.endswith(".md")]),
        "sources": len([f for f in os.listdir(p["sources"]) if f.endswith(".md")]),
        "raw_bytes": raw, "brain": BRAIN}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    lg = sub.add_parser("log")
    lg.add_argument("--slug", required=True)
    lg.add_argument("--title", default="")
    lg.add_argument("--kind", default="")
    lg.add_argument("--source", default="")
    lg.add_argument("--claims", default="")
    lg.add_argument("--status", default="取り込み済み")
    lg.set_defaults(fn=cmd_log)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
