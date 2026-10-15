#!/usr/bin/env python3
"""参考の記事とうちの記事の画像を、置き場所と大きさまで突き合わせる（工程5・6の出口）。
2026-10-06 本人「イメージが置かれてる場所を完全にコピーする。そうすれば大きさがおかしいことに気づける」。

使い方: python3 画像の置き方.py <参考のURL> <うちの記事（index.html のパスかURL）> [--移植表 <01 移植表.md>] [--測った <参考.json> <うち.json>] [--見た目は日本風]
  --見た目は日本風: 字の大きさ・太さ・色・後ろの箱・寄せを参考と比べない（日本風・ここちドライに寄せる記事。2026-10-12）。章・段の数・画像は比べる
  --幅 <px>: Dia でなく Playwright の Chromium（headless）で、参考とうちを同じ幅（例 390）で測る。スマホの幅では参考も1列になり、
            ここちドライの1列の記事と同じ物差しで横幅を比べられる（2026-10-15 草むしり椅子: 1280では参考が2列・うちが1列で横幅が比べられなかった）
  --書き出す <フォルダ>: 測った JSON（測った_参考.json・測った_うち.json）を書き出す（ずれを1枚ずつ確かめるため）
  参考の測りは、うちの記事のフォルダの 参考の測り_<幅>.json に1回だけ取って固定し、次からはそれと比べる（2026-10-15）
  --測り直す: 参考そのものを替えた時だけ付ける。固定した参考の測りを取り直す
  --測った: 裏用 Dia が立てられない時、内蔵ブラウザで LOAD_ALL と JS を同じ幅で当てた結果（JSON）を渡して判定だけする
裏用 Dia（9333）の同じ窓で両方を開き（同じ幅になる）、本文の画像（幅80px以上）を上から順に測る。裏用が立たない時は dia-agent（9223）に切り替える。
参考は本番の URL を渡す（保存した 焼き込み.html は Next.js 等の JS が file:// で失敗して本文が空になり、参考0枚と出る。2026-10-11）。
見る物: 枚数 / 何番目の章（h2）にあるか / 本文の中の位置（前にある段の割合） / 本文幅に対する横幅 / 縦横比。
段の並び（2026-10-07 本人「記事も同じことを」）: 章の数 / 章ごとの段・箇条・引用・小見出し・ボタンの数 / 型ごとの字の大きさ・太さ・色・後ろの箱・寄せ。言葉の中身は見ない。
ビジュアルの種類（2026-10-07 本人「ほとんどの場合は GIF」）: 1枚ずつ 動く（GIF・動くWebP）／止まり／動画 が参考と同じか。
訳（--移植表 を渡した時）: 参考の小さな言葉（actually・definitely など）を含む文が全部「## 訳の対照表」にあり、心理の効果・言葉ごとの運び方（「actually → …」）・うちの日本語が埋まっているか。参考の絵1枚ずつに「## 絵の対照表」の行（起こす感情・絵の調子・うちの絵）があるか。「## 変数の木」で参考を小さな変数まで割り、変数ごとに「→ やる事」があるか。参考が日本語なら、参考の段ごとに訳の対照表の行があるか。
終了コード: 0 一致 / 1 ずれがある（行ごとに直す所を出す） / 2 測れなかった。開いたタブは毎回閉じる。
"""
import json, os, subprocess, sys, time

ENV = {**os.environ, "DIA_CDP_PORT": "9333", "DIA_SOCK": "/tmp/dia-cdp-9333.sock"}
JS = r"""
const root = document.querySelector('article, main, .article, #content') || document.body;
const cw = root.getBoundingClientRect().width || innerWidth;
const fixedUp = e => { for (let x = e; x && x !== document.body; x = x.parentElement) { const p = getComputedStyle(x).position; if (p === 'fixed' || getComputedStyle(x).display === 'none') return true; } return false; };
// 背景に置いた写真（題の後ろの冒頭写真など）も絵として数える。見えている所の 200×150 以上だけ・固定の箱（カートの引き出し）は外す（2026-10-15 草むしり椅子: 参考の冒頭写真が背景で、数えていなかった）
const isBg = e => { if (/IMG|VIDEO|IFRAME/.test(e.tagName)) return false; const s = getComputedStyle(e); if (!/url\(/.test(s.backgroundImage) || /data:image\/svg/.test(s.backgroundImage)) return false; const r = e.getBoundingClientRect(); if (r.width >= innerWidth * 0.95 && r.height / r.width > 1.5) return false;  /* 画面の幅いっぱいで縦に長い背景は段の後ろの模様。写真ではない */ return r.width >= 200 && r.height >= 150 && r.right > 0 && r.left < innerWidth && !fixedUp(e); };
const all = [...root.querySelectorAll('h1,h2,h3,p,li,blockquote,img,video,iframe,div,section,header,a,span')].filter(e => /^(H1|H2|H3|P|LI|BLOCKQUOTE|IMG|VIDEO|IFRAME)$/.test(e.tagName) || isBg(e));
const blocks = all.filter(e => /^(H1|H2|H3|P|LI|BLOCKQUOTE)$/.test(e.tagName) && !e.closest('[data-tasu]') && e.innerText && e.innerText.trim().length > 1).filter((e, i, a) => a.findIndex(x => x.innerText.trim() === e.innerText.trim()) === i);  // 足す段の中の文は位置の割合にも数えない。同じ文の写し（流れる帯・横送りの2周目）は1回だけ数える（2026-10-15 草むしり椅子）
const out = [];
let h2 = 0, seen = 0;
for (const e of all) {
  if (e.tagName === 'H2' && !e.closest('[data-tasu]')) h2++;
  if (blocks.includes(e)) { seen++; continue; }
  if (!/IMG|VIDEO|IFRAME/.test(e.tagName) && !isBg(e)) continue;  // 背景の写真（isBg）は絵として残す  // 文の無い p・h2 などの入れ物は画像に数えない（2026-10-15 草むしり椅子。参考 Roosty's の空の p が1枚と数えられていた）
  if (e.closest('[data-tasu]')) continue;  // 参考に無くても足す物（_必ず入れる物.md の値段の画像など）は数えない（2026-10-11 睡眠イヤホン）
  const r = e.getBoundingClientRect();
  if (r.width < 80 || r.height < 40) continue;
  if (/^(IMG|VIDEO|IFRAME)$/.test(e.tagName) && fixedUp(e)) continue;
  out.push({ 型: /^(IMG|VIDEO|IFRAME)$/.test(e.tagName) ? e.tagName : 'BG', src: e.currentSrc || e.src || e.querySelector?.("source")?.src || (getComputedStyle(e).backgroundImage.match(/url\(["']?([^"')]+)/) || [])[1] || "", 章: h2, 位置: +(seen / Math.max(blocks.length, 1)).toFixed(3), 幅: +(r.width / cw).toFixed(3), 縦横: +(r.height / r.width).toFixed(3), px: [Math.round(r.width), Math.round(r.height)] });
}
// 段の並びと見た目（2026-10-07 本人「記事も同じことをしたい」＝参考との差を0に）。言葉の中身は見ない
const css = e => getComputedStyle(e);
const bg = e => { for (let x = e; x && x !== root.parentElement; x = x.parentElement) { const c = css(x).backgroundColor; if (c && !/rgba\(0, 0, 0, 0\)|transparent/.test(c)) return x === root || x === document.body ? null : c; } return null; };
const isBtn = e => e.tagName === 'BUTTON' || (e.tagName === 'A' && (/btn|button|cta/i.test(e.className) || (bg(e) && css(e).display !== 'inline')));
const seq = []; let 章 = 0;
for (const e of root.querySelectorAll('h1,h2,h3,p,li,blockquote,a,button')) {
  const r = e.getBoundingClientRect(); if (r.width < 20 || r.height < 8) continue;
  if (e.closest('[data-tasu]')) continue;  // 足す段（値段の段など）の中の文・ボタンも段の並びに数えない（画像と同じ。2026-10-11 睡眠イヤホン）
  if (e.tagName === 'H2') 章++;
  const t = e.tagName === 'A' || e.tagName === 'BUTTON' ? (isBtn(e) ? 'ボタン' : null) : e.tagName.toLowerCase();
  if (!t || (t !== 'ボタン' && !(e.innerText || '').trim())) continue;
  if (t === 'p' && e.closest('li,blockquote')) continue;
  const s = css(e);
  seq.push({ 型: t, 章, 文: (e.innerText || '').trim().slice(0, 60), 字: +parseFloat(s.fontSize).toFixed(1), 太: +s.fontWeight >= 600, 色: s.color, 箱: bg(e), 寄せ: s.textAlign });
}
const 文 = []; { let k = 0; for (const e of root.querySelectorAll('h1,h2,h3,p,li,blockquote')) { if (e.closest('[data-tasu]')) continue; if (e.tagName === 'H2') k++; if (e.tagName === 'P' && e.closest('li,blockquote')) continue; const t = (e.innerText || '').trim(); if (t) 文.push({ 章: k, 型: e.tagName.toLowerCase(), 文: t }); } }
// 日本語は \uXXXX にし、ページに置いて 30,000字ずつ取る（dia の出力は約65,000字で切れ、長い記事で JSON が壊れて KeyError「章」・Expecting delimiter になった。2026-10-11 睡眠イヤホン）
window.__m = JSON.stringify({ 画像: out, 段: seq, 文 }).replace(/[\u0080-\uffff]/g, c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
return "LEN:" + window.__m.length;
"""

LOAD_ALL = r"""
document.querySelectorAll('img').forEach(i => { i.loading = 'eager'; for (const k of ['data-src','data-lazy-src','data-original']) { const v = i.getAttribute(k); if (v && !i.getAttribute('src')?.startsWith('http')) i.src = v; } const ss = i.getAttribute('data-srcset'); if (ss) i.srcset = ss; });
for (let y = 0; y < document.body.scrollHeight; y += Math.max(innerHeight / 2, 300)) { scrollTo(0, y); await new Promise(r => setTimeout(r, 250)); }
scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 1500));
await Promise.all([...document.images].filter(i => !i.complete).map(i => new Promise(r => { i.onload = i.onerror = r; setTimeout(r, 8000); })));
scrollTo(0, 0); return 1;
"""

BIN = ["dia"]   # 裏用 Dia（9333）。立たない時は measure() が Claude 用の dia-agent（9223）に切り替える

def dia(*args, timeout=90):
    r = subprocess.run([*BIN, *args], env=ENV if BIN == ["dia"] else os.environ, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()

def measure(target):
    global BIN
    url = target if target.startswith("http") or target.startswith("file:") else "file://" + os.path.abspath(target)
    out = dia("open", url)
    if not out.strip():
        # 裏用 Dia は本人の Dia がポート無しで開いていると立たない（2026-10-11 ranking-static で list index out of range）。dia-agent は別に立つ
        BIN = ["dia-agent"]
        out = dia("open", url)
    if not out.strip():
        raise RuntimeError("ブラウザが開けない（裏用 Dia 9333 も dia-agent 9223 も返事が無い）")
    tab = out.splitlines()[0].strip()
    try:
        time.sleep(6)
        # 遅延読み込みの画像を出す。一番下へ飛ぶだけだと途中の絵が読み込まれない（2026-10-07 Everdries の理由5・6の絵が数えられず終了コード1）
        dia("do", LOAD_ALL, "--tab", tab, timeout=120)
        time.sleep(3)
        raw = dia("do", JS, "--tab", tab)
        import re as _re
        n = int(_re.search(r"LEN:(\d+)", raw).group(1))
        buf = ""
        for i in range(0, n, 30000):
            part = dia("do", f"return 'B<' + window.__m.slice({i}, {i + 30000}) + '>B'", "--tab", tab)
            buf += part[part.index("B<") + 2: part.rindex(">B")]
        return json.loads(buf)
    finally:
        dia("close", "--tab", tab)

def measure_pw(target, w):
    """Playwright の Chromium で幅 w にして LOAD_ALL と JS を当てる（Dia と同じ JS・同じ JSON）"""
    from playwright.sync_api import sync_playwright
    url = target if target.startswith(("http", "file:")) else "file://" + os.path.abspath(target)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        try:
            pg = b.new_page(viewport={"width": w, "height": 844 if w < 700 else 800})
            pg.goto(url, wait_until="load", timeout=60000)
            pg.wait_for_timeout(3000)
            pg.evaluate("async () => {" + LOAD_ALL + "}")
            pg.wait_for_timeout(1500)
            pg.evaluate("() => {" + JS + "}")
            return json.loads(pg.evaluate("() => window.__m"))
        finally:
            b.close()

def 色(c):
    import re
    v = [int(x) for x in re.findall(r"\d+", c or "")[:3]]
    return v if len(v) == 3 else None

def 段の突き合わせ(R, O, 日本風=False):
    """章ごとの段の数と、型ごとの見た目（字の大きさ・太さ・色・後ろの箱・寄せ）を比べる。
    日本風=True の時は見た目を比べない（2026-10-12 本人「文字とデザインは全部日本風・ここちドライに寄せる。英語の参考の見た目は写さない」。数と画像の置き方は比べる）"""
    bad = []
    # 同じ章の同じ文は1回だけ数える。流れる帯の写し・横送りの2周目は同じ段落の写しで、段の数ではない（2026-10-15 草むしり椅子）
    def 一回(xs):
        seen, out = set(), []
        for x in xs:
            k = (x["章"], x["型"], x.get("文"))
            if x.get("文") and k in seen: continue
            seen.add(k); out.append(x)
        return out
    R, O = 一回(R), 一回(O)
    rn, on = max([x["章"] for x in R] + [0]), max([x["章"] for x in O] + [0])
    if rn != on: bad.append(f"章（h2）の数: 参考 {rn} / うち {on}")
    for k in range(min(rn, on) + 1):
        for t in ("p", "li", "blockquote", "h3", "ボタン"):
            a = sum(1 for x in R if x["章"] == k and x["型"] == t); b = sum(1 for x in O if x["章"] == k and x["型"] == t)
            if abs(a - b) > (max(1, round(a * 0.25)) if t == "p" else 0): bad.append(f"{k}番目の章: {t} の数 参考 {a} / うち {b}")
    for t in (() if 日本風 else ("h1", "h2", "h3", "p", "li", "blockquote", "ボタン")):
        a = [x for x in R if x["型"] == t]; b = [x for x in O if x["型"] == t]
        if not a or not b: continue
        ma, mb = sorted(x["字"] for x in a)[len(a) // 2], sorted(x["字"] for x in b)[len(b) // 2]
        if abs(ma - mb) > 0.15 * ma: bad.append(f"{t}: 字の大きさ 参考 {ma}px / うち {mb}px")
        if (sum(x["太"] for x in a) * 2 > len(a)) != (sum(x["太"] for x in b) * 2 > len(b)): bad.append(f"{t}: 太字 参考 {'太い' if sum(x['太'] for x in a) * 2 > len(a) else '細い'} / うち {'太い' if sum(x['太'] for x in b) * 2 > len(b) else '細い'}")
        多 = lambda xs, k: max(set(x[k] for x in xs), key=[x[k] for x in xs].count)  # 1つ目ではなく一番多い見た目で比べる（飾りの1個に引きずられない）
        ca, cb = 色(多(a, "色")), 色(多(b, "色"))
        if ca and cb and sum((x - y) ** 2 for x, y in zip(ca, cb)) ** 0.5 > 90: bad.append(f"{t}: 字の色 参考 {多(a, '色')} / うち {多(b, '色')}")
        if (sum(1 for x in a if x["箱"]) * 2 > len(a)) != (sum(1 for x in b if x["箱"]) * 2 > len(b)): bad.append(f"{t}: 後ろの箱 参考 {'あり' if sum(1 for x in a if x['箱']) * 2 > len(a) else 'なし'} / うち {'あり' if sum(1 for x in b if x['箱']) * 2 > len(b) else 'なし'}")
        if 多(a, "寄せ") != 多(b, "寄せ") and t in ("h1", "h2", "ボタン"): bad.append(f"{t}: 寄せ 参考 {多(a, '寄せ')} / うち {多(b, '寄せ')}")
    return bad


小さな言葉 = ["actually", "definitely", "just", "even", "only", "still", "really", "finally", "simply", "exactly", "quietly", "secretly", "literally", "already", "never", "ever", "almost", "truly", "honestly", "instantly", "suddenly", "completely", "totally", "absolutely", "seriously", "surprisingly", "basically", "practically", "barely", "hardly", "right now", "today", "anymore", "at last", "no longer", "in fact", "of course", "here's", "here is", "why", "what", "imagine", "but"]

def 動きの種類(img):
    """動く（GIF・動くWebP）／止まり／動画 を見分ける"""
    if img.get("型") in ("VIDEO", "IFRAME"): return "動画"
    src = img.get("src") or ""
    try:
        import io, urllib.request
        from PIL import Image
        if src.startswith("file://"):
            import urllib.parse; data = open(urllib.parse.unquote(src[7:]), "rb").read()
        elif src.startswith("data:"):
            import base64; data = base64.b64decode(src.split(",", 1)[1])
        else:
            data = urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
        im = Image.open(io.BytesIO(data))
        return "動く" if getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1 else "止まり"
    except Exception:
        return "測れない"

def 訳の照らし(参考の文, 移植表):
    """参考の小さな言葉を含む文が、移植表の「訳の対照表」に全部あり、その言葉の運び方が書いてあるか（2026-10-07 本人「小さい英語を訳すところが弱い」）"""
    import re
    md = open(移植表, encoding="utf-8").read()
    m = re.search(r"\n## 訳の対照表[^\n]*\n(.*?)(?=\n## |\Z)", md, re.S)
    if not m: return ["移植表に「## 訳の対照表」が無い（| # | 参考の英語 | 心理の効果 | 小さな言葉 → 日本語での運び方 | うちの日本語 |）"]
    行 = [[c.strip() for c in l.strip().strip("|").split("|")] for l in m.group(1).splitlines() if l.strip().startswith("|") and not re.match(r"^\|\s*-", l.strip())][1:]
    norm = lambda t: re.sub(r"\s+", " ", t.lower()).strip()
    bad = []
    全文 = "".join(x["文"] for x in 参考の文)
    if 全文 and sum(1 for c in 全文 if "\u3040" <= c <= "\u9fff") / len(全文) > 0.3:
        # 参考が日本語（たいていは違う商品）: 段ごとに、同じ心理の効果を起こす行が要る（2026-10-07 本人）
        for x in 参考の文:
            if x["型"] not in ("p", "li", "blockquote", "h1", "h2") or len(x["文"]) < 8: continue
            hit = next((r for r in 行 if len(r) >= 5 and norm(x["文"])[:20] in norm(r[1])), None)
            if not hit: bad.append(f"訳の対照表に無い段（日本語の参考）: 「{x['文'][:40]}」")
            elif not hit[2] or not hit[4]: bad.append(f"心理の効果かうちの文が空: 「{x['文'][:30]}」")
        return bad
    for x in 参考の文:
        for s_ in re.split(r"(?<=[.!?])\s+", x["文"]):
            ns = norm(s_)
            if len(ns) < 8: continue
            words = [w for w in 小さな言葉 if re.search(r"(?<![a-z'])" + re.escape(w) + r"(?![a-z])", ns)]
            if not words: continue
            hit = next((r for r in 行 if len(r) >= 5 and (ns[:40] in norm(r[1]) or norm(r[1])[:40] in ns)), None)
            if not hit: bad.append(f"訳の対照表に無い文（小さな言葉 {', '.join(words)}）: 「{s_[:60]}」"); continue
            if not hit[2]: bad.append(f"心理の効果が空: 「{s_[:40]}」")
            for w in words:
                if not re.search(re.escape(w) + r"[^|]*→", hit[3].lower()): bad.append(f"小さな言葉「{w}」の運び方が無い（「{w} → …」と書く）: 「{s_[:40]}」")
            if not hit[4]: bad.append(f"うちの日本語が空: 「{s_[:40]}」")
    return bad

def 木の照らし(移植表):
    """参考を小さな変数の木に割ってから作っているか（2026-10-07 本人「どの小さな variable で集まってるかを tree diagram で考える」）"""
    import re
    md = open(移植表, encoding="utf-8").read()
    m = re.search(r"\n## 変数の木[^\n]*\n(.*?)(?=\n## |\Z)", md, re.S)
    if not m: return ["移植表に「## 変数の木」が無い（参考を 構造（シンプルさ・コピー）とビジュアル から小さな変数まで割り、変数ごとに差を0にするやる事を書く）"]
    枝 = [l for l in m.group(1).splitlines() if re.match(r"^\s*[-*]\s+\S", l)]
    深い = [l for l in 枝 if len(l) - len(l.lstrip()) >= 4]
    bad = []
    if len(枝) < 6 or not 深い: bad.append(f"変数の木が浅い（枝 {len(枝)} 本・2段目より下 {len(深い)} 本）。構造とビジュアルの下に、差を測れる小さな変数まで割る")
    if 枝 and not any("→" in l for l in 枝): bad.append("変数の木に「→ 差を0にするやる事」が無い")
    return bad

def 絵の照らし(参考の画像, 移植表, 狭い=False):
    """参考の絵1枚ずつに、読み手に起こす感情と絵の調子を読み取ってから、うちの絵を作っているか（2026-10-07 本人「その画像がどんな心理的な感情を与えてるのかを読み取って、同じ感情を与える画像を作る」）"""
    import re
    md = open(移植表, encoding="utf-8").read()
    m = re.search(r"\n## 絵の対照表[^\n]*\n(.*?)(?=\n## |\Z)", md, re.S)
    if not m: return ["移植表に「## 絵の対照表」が無い（| 枚 | 参考の絵が起こす感情 | 絵の調子（例: 日本風の優しい感じ） | うちの絵（ファイルとプロンプト） |）"]
    行 = [[c.strip() for c in l.strip().strip("|").split("|")] for l in m.group(1).splitlines() if l.strip().startswith("|") and not re.match(r"^\|\s*-", l.strip())][1:]
    # 幅で出る絵が違う参考（スマホだけの写真・パソコンだけの部品）は、枚の欄に「390幅だけ」「既定の幅だけ」と書いた行を、その幅で測った時だけ数える（2026-10-15 草むしり椅子: 既定の幅20枚・390幅17枚で1つの表が両方に合わなかった）
    行 = [r for r in 行 if not (r and (("390幅だけ" in r[0] and not 狭い) or ("既定の幅だけ" in r[0] and 狭い)))]
    bad = []
    if len(行) != len(参考の画像): bad.append(f"絵の対照表の行 {len(行)} / 参考の絵 {len(参考の画像)} 枚。1枚1行にする")
    for i, r in enumerate(行, 1):
        if len(r) < 4 or not all(r[:4]): bad.append(f"絵の対照表の{i}行目: 空の欄がある（感情・調子・うちの絵を全部書く）")
    return bad

def main(argv):
    if len(argv) < 3:
        print(__doc__); return 2
    # 参考の測りは記事ごとに1回だけ取って固定する（2026-10-15 本人「構造から変えて」。参考の本番ページが途中で19枚→20枚・20枚→41枚に変わり、
    # 毎回測り直すたびに比べる元が動いて審査の件数が増えた）。うちの記事のフォルダに 参考の測り_<幅>.json を置き、次からはそれと比べる。
    # 参考を測り直すのは、参考そのものを替えた時だけ（--測り直す）
    幅 = argv[argv.index("--幅") + 1] if "--幅" in argv else "既定"
    固定 = None if argv[2].startswith("http") else os.path.join(os.path.dirname(os.path.abspath(argv[2])), f"参考の測り_{幅}.json")
    try:
        if "--測った" in argv:
            # 裏用 Dia が立てられない時（本人の Dia が 9222 無しで開いている時）は、内蔵ブラウザで同じ JS（下の JS_FOR_EXPORT）を当てた結果を渡す（2026-10-09）
            k = argv.index("--測った")
            ref, ours = json.load(open(argv[k + 1], encoding="utf-8")), json.load(open(argv[k + 2], encoding="utf-8"))
        else:
            測る = (lambda t: measure_pw(t, int(幅))) if 幅 != "既定" else measure
            if 固定 and os.path.exists(固定) and "--測り直す" not in argv:
                f = json.load(open(固定, encoding="utf-8"))
                if f.get("参考") != argv[1]:
                    print(f"固定した参考の測りは別の参考の物: {f.get('参考')}。参考を替えたなら --測り直す を付ける"); return 2
                ref = f["測り"]
                print(f"参考は固定した測り（{f.get('測った日')}・{os.path.basename(固定)}）と比べる")
            else:
                ref = 測る(argv[1])
                if 固定:
                    json.dump({"参考": argv[1], "幅": 幅, "測った日": time.strftime("%Y-%m-%d %H:%M"), "測り": ref},
                              open(固定, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                    print(f"参考を測って固定した: {固定}")
            ours = 測る(argv[2])
        if "--書き出す" in argv:
            d = argv[argv.index("--書き出す") + 1]; os.makedirs(d, exist_ok=True)
            for n, v in (("測った_参考.json", ref), ("測った_うち.json", ours)):
                json.dump(v, open(os.path.join(d, n), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"測れなかった: {e}"); return 2
    移植表 = argv[argv.index("--移植表") + 1] if "--移植表" in argv else None
    bad = 段の突き合わせ(ref["段"], ours["段"], 日本風="--見た目は日本風" in argv)  # 分かりやすさは字数・漢字では測れない（2026-10-07 本人）。編集長が客の目で読んで決める
    参考の文 = ref["文"]
    def 絵だけ(xs):
        # 横送りの2周目（同じ src）と、縦に長いレビューの部品の iframe（縦÷横 2.5 超。動画ではない）は絵の枚数に入れない（2026-10-15 草むしり椅子）
        seen, out = set(), []
        for x in xs:
            if x["型"] == "IFRAME" and x["縦横"] > 2.5: continue
            if x["src"] and x["src"] in seen: continue
            seen.add(x["src"]); out.append(x)
        return out
    ref, ours = 絵だけ(ref["画像"]), 絵だけ(ours["画像"])
    日本風 = "--見た目は日本風" in argv
    if 移植表: bad += 木の照らし(移植表) + 訳の照らし(参考の文, 移植表) + 絵の照らし(ref, 移植表, "--幅" in argv and int(argv[argv.index("--幅") + 1]) < 700)  # 絵の対照表は2周目・部品の iframe を除いた絵の枚数で数える（2026-10-15）
    for i, (a, b) in enumerate(zip(ref, ours), 1):
        ka, kb = 動きの種類(a), 動きの種類(b)
        if "測れない" not in (ka, kb) and ka != kb: bad.append(f"{i}枚目: 参考は「{ka}」/ うちは「{kb}」（GIF・動画は同じ種類で作る）")
    if len(ref) != len(ours):
        bad.append(f"画像の枚数: 参考 {len(ref)} 枚 / うち {len(ours)} 枚。参考と同じ枚数にする")
    for i, (a, b) in enumerate(zip(ref, ours), 1):
        if a["章"] != b["章"]: bad.append(f"{i}枚目: 参考は {a['章']} 番目の章 / うちは {b['章']} 番目の章")
        if abs(a["位置"] - b["位置"]) > 0.08: bad.append(f"{i}枚目: 本文の中の位置 参考 {a['位置']:.0%} / うち {b['位置']:.0%}")
        if abs(a["幅"] - b["幅"]) > 0.10: bad.append(f"{i}枚目: 横幅（本文幅に対して）参考 {a['幅']:.0%} / うち {b['幅']:.0%}（{a['px']} / {b['px']}px）")
        # 日本風の記事は、本文の写真を横長（縦÷横 0.56〜0.75）で作る決め（05 記事を作る 手順7・ここちドライの手本）。参考が横長より縦に高い写真（0.56以上）の所は、うちが決めの範囲なら合っている（2026-10-15 草むしり椅子）
        横長の決め = 日本風 and a["縦横"] >= 0.56 and 0.56 <= b["縦横"] <= 0.75 and b["幅"] >= 0.5
        if not 横長の決め and abs(a["縦横"] - b["縦横"]) > 0.10 * max(a["縦横"], 0.1): bad.append(f"{i}枚目: 縦横比 参考 {a['縦横']} / うち {b['縦横']}（{a['px']} / {b['px']}px）")
    bad = list(dict.fromkeys(bad))  # 同じ文が入れ子の段で2回数えられても1回だけ出す
    print(f"参考 {len(ref)} 枚・うち {len(ours)} 枚を突き合わせた")
    if bad:
        print("\n".join("- " + x for x in bad)); return 1
    print("通った"); return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
