#!/usr/bin/env python3
"""閉本テスト。playbook が外部保管物として機能しているかを測る。

根拠: Dunlosky et al. 2013 が10手法を格付けし、練習テストを最高有用度、
要約を最低有用度に置いた。Roediger & Karpicke 2006 はテスト自体が記憶を強くすると示し、
Karpicke & Blunt 2011 は概念マップ作りよりテストが勝つと示した。
だからこの脳は「まとめて終わり」にせず、必ずここを通す。

やり方は2段。
  1) selftest.py questions <source.md>
     → source の主張から問いだけを出す。答えは出さない
     → **playbook だけを見て**答えを書く（sourceを開かない。ここが閉本の意味）
  2) 書いた答えをファイルに保存して
     selftest.py answers <source.md> --recall <答えを書いたファイル>
     → 文字3-gramの重なりで機械採点する。自己申告を信用しない
     → 一致しなかった主張が playbook の穴

  selftest.py coverage <source.md> <playbook.md>
     → 機械的な網羅チェック。source の主張のうち playbook が引いていないものを出す
"""
import argparse
import os
import re
import sys


def read(p):
    if not os.path.exists(p):
        print(f"SELFTEST_FAILED: ファイルが無い: {p}", file=sys.stderr)
        sys.exit(2)
    return open(p, encoding="utf-8", errors="replace").read()


def parse_claims(body):
    """source の主張ブロックを取る。

    形式:
      c01
      - 何を言っているか: ...
      - なぜそうなるのか: ...
      - どこまで効くか: ...
      - これが正しいなら: ...
      - 逐語: ...
    """
    sec = re.search(r"##\s*主張(.*?)(\n##\s|\Z)", body, re.S)
    if not sec:
        return {}
    text = sec.group(1)
    claims = {}
    cur = None
    for line in text.split("\n"):
        m = re.match(r"^\s*(c\d+)\s*$", line)
        if m:
            cur = m.group(1)
            claims[cur] = {}
            continue
        m = re.match(r"^\s*[-*]\s*([^:：]+)[:：]\s*(.+)$", line)
        if m and cur:
            claims[cur][m.group(1).strip()] = m.group(2).strip()
    return claims


def cmd_questions(a):
    body = read(a.source)
    claims = parse_claims(body)
    if not claims:
        print("SELFTEST_FAILED: 主張が読めない。sourceの書式を確認すること"
              "（c01 の行 + 「- 何を言っているか: 」形式）", file=sys.stderr)
        sys.exit(3)
    topic = (re.search(r"^title:\s*(.+)$", body, re.M) or
             re.search(r"^#\s*(.+)$", body, re.M))
    q = re.search(r"##\s*この教材が答えている問い\s*\n+(.+)", body)
    print(f"# 閉本テスト: {topic.group(1) if topic else os.path.basename(a.source)}")
    if q:
        print(f"\n問い: {q.group(1).strip()}")
    print(f"\n**ここから先、source は開かない。playbook だけを見て答える。**\n")
    # 主張の中身は1文字も出さない。出すと自由再生のテストにならない
    print(f"この教材からは主張が **{len(claims)}件** 取れている。")
    print("playbook だけを見て、この教材から来ている指示を**全部書き出せ**。")
    print("番号順である必要はない。思い出せた分だけ書いて、そこで止める。\n")
    print("書いた答えをファイルに保存してから答え合わせ:")
    print(f'  python3 {os.path.basename(__file__)} answers "{a.source}" --recall <答えのファイル>')
    print("（機械が突き合わせる。自己申告にしない）")


def ngrams(s, n=3):
    s = re.sub(r"[\s、。,.「」（）()【】・:：]", "", s)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def score_recall(recall_text, claim_text):
    """書いた答えと主張の重なりを機械で測る。自己申告を信用しないための採点。
    文字3-gramの再現率（主張側のn-gramのうち、答えに含まれる割合）。"""
    c = ngrams(claim_text)
    if not c:
        return 0.0
    return len(c & ngrams(recall_text)) / len(c)


def cmd_answers(a):
    claims = parse_claims(read(a.source))

    if a.recall:
        # 自分で書いた答えのファイルと突き合わせる（本来こちらを使う）
        recall = read(a.recall)
        if len(recall.strip()) < 30:
            print("SELFTEST_FAILED: 答えのファイルが空に近い。"
                  "playbookを見て書いた答えを渡すこと", file=sys.stderr)
            sys.exit(4)
        ok, scores = set(), {}
        for cid, c in claims.items():
            s = score_recall(recall, c.get("何を言っているか", ""))
            scores[cid] = s
            if s >= a.threshold:
                ok.add(cid)
        print(f"# 答え合わせ（機械採点 / しきい値 {a.threshold}）\n")
        print("**この採点は字面の重なりしか見ていない。**"
              "同じ意味を別の言葉で書いた答えは低く出る。\n"
              "しきい値未満は『不正解』ではなく『**要確認**』として扱うこと。\n")
        for cid in claims:
            print(f"- {cid}: 一致 {scores[cid]:.0%} "
                  f"{'○' if cid in ok else '要確認'}")
        print()

        # 要確認の主張について、playbook の中で一番近い行を出す。
        # 「言い換えて入っている」のか「本当に落ちている」のかを、目で1秒で分けるため
        if a.playbook:
            # 折り返した行を1つの塊に戻してから比べる。
            # 物理行で比べると、2行に跨いだルールが見つからない（2026-08-15 実測）
            raw_pb = read(a.playbook)
            pb_lines = []
            for block in re.split(r"\n\s*\n|\n(?=[-*\d#])", raw_pb):
                b = " ".join(x.strip() for x in block.split("\n")).strip()
                if len(b) > 12 and not b.startswith("|"):
                    pb_lines.append(b)
            print("## 要確認の主張と、playbook で一番近い行\n")
            for cid in claims:
                if cid in ok:
                    continue
                claim = claims[cid].get("何を言っているか", "")
                best, bs = "", 0.0
                for l in pb_lines:
                    s = score_recall(l, claim)
                    if s > bs:
                        best, bs = l, s
                print(f"- {cid} 「{claim[:50]}」")
                print(f"  playbookで最も近い行（{bs:.0%}）: {best[:90] or '（無し）'}")
            print()
    else:
        print("注意: --recall を使っていない。自己申告は答えを見た後でも○にできるので、"
              "テストとして弱い。書いた答えをファイルに保存して --recall で渡すこと\n",
              file=sys.stderr)
        ok = {x.strip() for x in (a.answered or "").split(",") if x.strip()}

    miss = [c for c in claims if c not in ok]
    print("# 内容\n")
    for cid, c in claims.items():
        mark = "一致" if cid in ok else "**要確認**"
        print(f"## {cid} {mark}")
        print(f"- 何を言っているか: {c.get('何を言っているか', '(欠)')}")
        print(f"- なぜそうなるのか: {c.get('なぜそうなるのか', '(欠)')}")
        print()
    if miss:
        print(f"## 要確認: {', '.join(miss)}")
        print("この主張は、書いた答えと字面が合わなかった。**2つに切り分けること。**")
        print("  1) playbookに別の言葉で入っている → そのまま進んでよい")
        print("  2) playbookから落ちている → 足すか、sourceの「採らなかった主張」に移す")
        sys.exit(3)
    print("## 全主張が、書いた答えと一致した")


def cmd_coverage(a):
    src = read(a.source)
    pb = read(a.playbook)
    claims = parse_claims(src)
    if not claims:
        print("SELFTEST_FAILED: 主張が読めない。sourceの書式を確認すること", file=sys.stderr)
        sys.exit(3)
    slug = (re.search(r"^slug:\s*(.+)$", src, re.M) or [None, ""])
    slug = slug.group(1).strip() if hasattr(slug, "group") else \
        os.path.basename(a.source)[:-3]
    cited = set(re.findall(rf"{re.escape(slug)}#(c\d+)", pb))  # 表の中は括弧なしで書かれる
    dropped = set(re.findall(r"^\s*[-*]\s*(c\d+)",
                             (re.search(r"##\s*採らなかった主張(.*?)(\n##\s|\Z)", src, re.S)
                              or type("x", (), {"group": lambda *_: ""})).group(1), re.M))
    missing = [c for c in claims if c not in cited and c not in dropped]
    print(f"主張 {len(claims)}件 / playbookが引いている {len(cited)}件 / "
          f"意図的に捨てた {len(dropped)}件 / 宙に浮いている {len(missing)}件")
    if missing:
        for c in missing:
            print(f"- {c}: {claims[c].get('何を言っているか', '(欠)')[:70]}")
        print("\nこの主張は playbook にも「採らなかった主張」にも無い。"
              "どちらかに入れること（黙って落とさない）")
        sys.exit(3)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("questions"); q.add_argument("source"); q.set_defaults(fn=cmd_questions)
    an = sub.add_parser("answers"); an.add_argument("source")
    an.add_argument("--recall", help="playbookだけを見て書いた答えのファイル（推奨）")
    an.add_argument("--playbook", help="要確認の主張について、playbook側の近い行を出す")
    an.add_argument("--threshold", type=float, default=0.35,
                    help="一致とみなす下限（既定0.35）")
    an.add_argument("--answered", default="", help="自己申告。--recall が使えない時だけ")
    an.set_defaults(fn=cmd_answers)
    cv = sub.add_parser("coverage"); cv.add_argument("source"); cv.add_argument("playbook")
    cv.set_defaults(fn=cmd_coverage)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
