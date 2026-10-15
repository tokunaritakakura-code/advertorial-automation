#!/usr/bin/env python3
"""生テキストを「Claudeが読む用の小さい地図」に潰す。

考え方: 教材の全文をClaudeに読ませない。
  1. チャプターに割る
  2. 各チャプターから「指示・数字・禁止・条件」だけを機械的に抜く
  3. Claudeはこのdigestだけ読み、深掘りしたいチャプターを slice.py で取りに行く

出力は digest.md（既定で 6000 字上限 = 目安 3〜4kトークン）。

使い方:
  digest.py raw/<slug>.txt [--chapters 12] [--per-chapter 6] [--max-chars 6000]
"""
import argparse
import json
import os
import re
import sys

# 「使える情報」を含む文の目印。日本語と英語の両方。
SIGNALS = [
    # 命令・手順
    (r"(必ず|絶対に|するな|しない(で|こと)|してはいけない|やめ(ろ|て)|避け(る|て))", 3.0),
    (r"(まず|次に|最後に|ステップ|手順|やり方|方法は)", 2.0),
    (r"\b(never|always|must|don'?t|avoid|make sure|you need to|you have to|the key is|the trick)\b", 3.0),
    (r"\b(first|second|third|next|finally|step \d|here'?s how|the way to)\b", 2.0),
    # 判断基準・数字
    (r"\d+\s*(%|％|円|ドル|\$|倍|本|個|日|週間|ヶ月|秒|分)", 2.5),
    (r"[\$￥]\s?\d", 2.5),
    (r"\b\d+(\.\d+)?\s*(percent|x|k|m)\b", 2.0),
    (r"(以上|以下|未満|超え(る|た)|上限|下限|基準|しきい値)", 2.0),
    # 因果・理由（型として使える所）
    (r"(なぜなら|理由は|だから|そのため|つまり|要は|ポイントは|コツは)", 2.0),
    (r"\b(because|the reason|that'?s why|which means|in other words)\b", 1.8),
    # 条件分岐
    (r"(もし|場合は|とき(は|に)|なら(ば)?)", 1.2),
    (r"\b(if you|when you|unless)\b", 1.2),
    # 失敗談・逆張り（教材の一番おいしい所）
    (r"(失敗|間違(い|え)|勘違い|落とし穴|よくある|多くの人|みんな)", 2.5),
    (r"\b(mistake|wrong|myth|most people|everyone thinks|counterintuitive)\b", 2.5),
    # 名前つきの型
    (r"(フレームワーク|テンプレート|型|フォーミュラ|公式|構成|チェックリスト)", 2.2),
    (r"\b(framework|formula|template|structure|checklist|blueprint)\b", 2.2),
]
NOISE = re.compile(
    r"^(\[音楽\]|\[music\]|\[applause\]|\[laughter\]|♪|うん|えー|あの|so |okay|alright|yeah)",
    re.I)
TS = re.compile(r"^\[(\d+):(\d+)\]\s*")


FILLER = re.compile(r"\b(um+|uh+|erm|you know|i mean|kind of|sort of)\b[,]?\s*", re.I)
# 話し言葉の切れ目。字幕には句読点が無いのでここで割らないと1章＝1文になる。
MARK_EN = re.compile(
    r"^(so|and|but|then|now|okay|alright|also|plus|first|second|third|next|finally|"
    r"because|if|when|what|here|the)$", re.I)
# 日本語の字幕には句読点が無い。文末は「です・ます」で終わるのでそこで割る。
# ここに です/ます が無いと80字で機械的に切れて、途中で切れた断片が並ぶ（2026-08-14実測）
MARK_JA = re.compile(
    r"(です|ます|ました|ません|でした|ですね|ますね|だった|になる|になります|"
    r"ので|から|けど|けれど|ですが|ますが|したら|なら|ため|とか|でも)$")


def clean(s):
    return re.sub(r"\s{2,}", " ", FILLER.sub("", s)).strip(" ,")


def _chunk_spaced(text, min_w=12, max_w=40):
    words, out, cur = text.split(), [], []
    for w in words:
        if len(cur) >= min_w and MARK_EN.match(w.strip(",.")):
            out.append(" ".join(cur))
            cur = []
        cur.append(w)
        if len(cur) >= max_w:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def _chunk_ja(text, min_c=28, max_c=80):
    out, cur = [], ""
    for ch in text:
        cur += ch
        if ch in "、,":
            if len(cur) >= min_c:
                out.append(cur)
                cur = ""
        elif len(cur) >= min_c and MARK_JA.search(cur):
            out.append(cur)
            cur = ""
        elif len(cur) >= max_c:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def split_sentences(text):
    """句読点があれば文で割る。字幕のように句読点が無ければ話し言葉の切れ目で割る。
    ここを間違えると1章が1文になり、digestが圧縮にならない（2026-08-14に実測）。"""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    n_punct = len(re.findall(r"[。！？!?]|\.\s", text))
    if n_punct >= max(2, len(text) // 250):
        parts = re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+(?=[A-Z])", text)
    else:
        spaced = text.count(" ") > len(text) / 12
        parts = _chunk_spaced(text) if spaced else _chunk_ja(text)
    return [clean(p) for p in parts if p and len(clean(p)) > 12]


def score(sent):
    s = 0.0
    for pat, w in SIGNALS:
        if re.search(pat, sent, re.I):
            s += w
    n = len(sent)
    if n < 20:
        s -= 1.5
    if n > 400:
        s -= 1.0
    if NOISE.match(sent):
        s -= 2.0
    return s


def load(path):
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    timed = []
    has_ts = False
    for ln in lines:
        m = TS.match(ln)
        if m:
            has_ts = True
            timed.append((int(m.group(1)) * 60 + int(m.group(2)), TS.sub("", ln)))
        elif ln.strip():
            timed.append((None, ln))
    return timed, has_ts


def chapterize(timed, has_ts, n_ch):
    """時間があれば等間隔、無ければ見出し優先、それも無ければ文字数で割る。"""
    if has_ts:
        times = [t for t, _ in timed if t is not None]
        if times:
            span = max(times) - min(times)
            if span > 0:
                step = max(60, span // max(1, n_ch))
                chs, cur, start = [], [], min(times)
                for t, txt in timed:
                    tt = t if t is not None else start
                    if tt - start >= step and cur:
                        chs.append((start, cur))
                        cur, start = [], tt
                    cur.append(txt)
                if cur:
                    chs.append((start, cur))
                return chs
    heads = [i for i, (_, t) in enumerate(timed) if re.match(r"^#{1,3} |^##? p\.\d+", t)]
    if len(heads) >= 3:
        chs, bounds = [], heads + [len(timed)]
        for i in range(len(heads)):
            seg = timed[bounds[i]:bounds[i + 1]]
            chs.append((None, [t for _, t in seg]))
        return chs
    total = sum(len(t) for _, t in timed)
    per = max(500, total // max(1, n_ch))
    chs, cur, cnt = [], [], 0
    for _, t in timed:
        cur.append(t)
        cnt += len(t)
        if cnt >= per:
            chs.append((None, cur))
            cur, cnt = [], 0
    if cur:
        chs.append((None, cur))
    return chs


def label(sents, clauses):
    """章の見出し。見出し行があればそれ、無ければ一番スコアの高い一節を短く。
    字幕の冒頭は「yeah so um」で始まるので、先頭をそのまま使わない。"""
    for s in sents[:3]:
        if re.match(r"^#{1,3} ", s):
            return re.sub(r"^#+\s*", "", s)[:60]
    if clauses:
        best = max(clauses, key=score)
        return clean(best)[:70]
    return clean(" ".join(sents))[:70]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--chapters", type=int, default=12)
    ap.add_argument("--per-chapter", type=int, default=6)
    ap.add_argument("--max-chars", type=int, default=6000)
    ap.add_argument("--out")
    a = ap.parse_args()

    if not os.path.exists(a.raw):
        print(f"DIGEST_FAILED: 生テキストが無い: {a.raw}", file=sys.stderr)
        sys.exit(2)
    timed, has_ts = load(a.raw)
    if not timed:
        print("DIGEST_FAILED: 生テキストが空。取得失敗を0件と混同しないこと", file=sys.stderr)
        sys.exit(3)

    chs = chapterize(timed, has_ts, a.chapters)
    total_chars = sum(len(t) for _, t in timed)

    out = [f"# digest: {os.path.basename(a.raw)}",
           f"元の量 {total_chars:,}字 / 章 {len(chs)}個 / "
           f"全文をそのまま読むと約 {total_chars // 2:,} トークン",
           "",
           "この digest だけで判断する。足りない章だけ slice.py で取りに行くこと。",
           ""]

    # 章ごとにブロックを作ってから予算配分する。
    # 単純に末尾を切ると、後半の章が「情報が無い章」に見える（Codex指摘・2026-08-14）
    blocks, picked_counts = [], []
    seen = set()  # 教材は同じ言い回しを何度も繰り返す。同じ主張を2回載せない
    for i, (t0, sents_raw) in enumerate(chs, 1):
        text = " ".join(sents_raw)
        sents = split_sentences(text)
        scored = sorted(((score(s), s) for s in sents), key=lambda x: -x[0])
        picked = []
        for sc, s in scored:
            if len(picked) >= a.per_chapter:
                break
            if sc <= 1.0:
                break
            key = re.sub(r"[\s、。,.]", "", s)[:40]
            if key in seen:
                continue
            seen.add(key)
            picked.append(s)
        head = f"## ch{i}" + (f" [{t0 // 60:02d}:{t0 % 60:02d}]" if t0 is not None else "")
        lines = [f"{head} {label(sents_raw, sents)}", f"({len(text):,}字)"]
        if picked:
            lines += [f"- {s[:200]}" for s in picked]
        else:
            # 「情報が無い」と断定しない。機械抽出に引っかからなかっただけの章もある
            lines.append("- （機械抽出に引っかからなかった章。"
                         "見出しで判断できなければ slice.py で中を見ること）")
            if sents:
                lines.append(f"- 章の書き出し: {sents[0][:120]}")
        lines.append("")
        blocks.append("\n".join(lines))
        picked_counts.append(len(picked))

    header = "\n".join(out)
    budget = a.max_chars - len(header) - 200
    kept, omitted, used = [], [], 0
    for i, b in enumerate(blocks, 1):
        if used + len(b) <= budget:
            kept.append(b)
            used += len(b)
        else:
            omitted.append(i)
    body = header + "\n".join(kept)
    if omitted:
        body += (f"\n（上限{a.max_chars}字のため、章 "
                 f"{','.join(map(str, omitted))} は載せていない。**中身が無いのではない。**"
                 f" slice.py --ch {omitted[0]} で直接見るか、--per-chapter を下げて取り直す）\n")

    picked_total = sum(picked_counts[:len(kept)])
    dest = a.out or a.raw.replace(".txt", ".digest.md")
    open(dest, "w", encoding="utf-8").write(body)

    # slice が同じ章割りを再現できるように、使ったパラメータを残す
    json.dump({"raw": os.path.abspath(a.raw), "chapters_arg": a.chapters,
               "chapters_made": len(chs), "per_chapter": a.per_chapter,
               "raw_chars": total_chars, "omitted_chapters": omitted},
              open(dest.replace(".md", ".json"), "w"), ensure_ascii=False, indent=1)

    # 短い教材はdigestを挟む方が損。素直に生を読ませる。
    if total_chars < 8000:
        rec = "生を直接読め（8000字未満。digestを挟む意味が無い）"
    elif len(body) / total_chars > 0.20:
        rec = "圧縮が甘い。--per-chapter を下げて取り直す"
    else:
        rec = "このdigestだけ読む"

    print(json.dumps({
        "digest": dest, "chapters": len(chs), "chapters_shown": len(kept),
        "omitted_chapters": omitted,
        "picked": picked_total, "picked_all": sum(picked_counts),
        "raw_chars": total_chars, "digest_chars": len(body),
        "圧縮率": f"{len(body) / max(1, total_chars):.1%}",
        "slice_args": f"--chapters {a.chapters}",
        "推奨": rec,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
