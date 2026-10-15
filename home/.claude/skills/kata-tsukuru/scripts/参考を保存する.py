#!/usr/bin/env python3
"""新しい参考（記事のリンク1本）を、誰の手元でも同じ形で保存する。

使い方: python3 参考を保存する.py <記事のURL> <出力フォルダ> [--vsl <mp4かURL>] [--辿る <広告.jsonのあるフォルダ>] [--やり直す]
  1 生.html        … サーバーが返す素のHTML（website-copy の fetch.sh と同じ UA）
  2 画面_390.png / 画面_1280.png … Playwright の Chromium（headless）で下まで送ってから撮った全体の画面
  3 焼き込み.html   … JS で出来た後のページ。website-copy の transform.mjs → bake.mjs（CAPTURED=1）で焼き込む
  4 段.md / 段.json … 390幅の見た目で見出しごとに段に割り、段ごとに「画像（ファイル名と大きさ）」と「文（切らずに全部）」
     画像/          … 段の画像そのもの（段03_02.jpg ＝ 3段目の2枚目）
  5 文字起こし.txt  … VSL があれば（--vsl か --辿る）。fukikae の 01_transcribe.sh（whisper-cli + large-v3-turbo）で時刻つき
  記録.json        … 何をどこから取ったか・段の数・画像の数・文字起こしの秒数
本人の Dia は使わない。出来ている物は飛ばす（途中で落ちたら同じコマンドでもう一度。--やり直す で全部取り直し）。
--辿る は リンクから辿る.py の出力フォルダ。記事と同じ飛び先（道まで同じ）の動画を先に、その中で配信日数の長い順に1本選ぶ。
要る物: python3 の playwright（`pip install playwright && playwright install chromium`）・node・ffmpeg・whisper-cli とモデル・yt-dlp（VSL が URL の時）
終了コード: 0=全部出来た / 1=記事は出来たが VSL の文字起こしが出来なかった / 2=記事が取れなかった・道具が無い
"""
import json, os, re, shutil, subprocess, sys, time, urllib.parse, urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
UA_SP = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
SKILLS = HERE.parent.parent   # ~/.claude/skills（GitHub では claude-skills/）


def find(env, *rel):
    """部品の置き場: 環境変数 → 同じ skills の並び → ~/.claude/skills"""
    if os.environ.get(env):
        return Path(os.environ[env])
    for base in (SKILLS, Path.home() / ".claude/skills"):
        p = base.joinpath(*rel)
        if p.exists():
            return p
    return None


def retry(fn, what, tries=3, wait=3):
    last = None
    for k in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            print(f"  {what} 失敗 {k + 1}/{tries}: {str(e)[:120]}", file=sys.stderr)
            time.sleep(wait * (k + 1))
    raise RuntimeError(f"{what}: {last}")


def save_atomic(path, data):
    tmp = Path(str(path) + ".tmp")
    if isinstance(data, str):
        tmp.write_text(data, encoding="utf-8")
    else:
        tmp.write_bytes(data)
    os.replace(tmp, path)


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "")


def download(url, path, timeout=600):
    """大きい物は少しずつ書いて、最後に名前を変える"""
    def go():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        tmp = Path(str(path) + ".part")
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            t0 = time.time()
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                if time.time() - t0 > timeout:
                    raise TimeoutError("ダウンロードが長すぎる")
            ctype = r.headers.get("Content-Type", "")
        if tmp.stat().st_size < 10000:
            raise RuntimeError(f"小さすぎる（{tmp.stat().st_size}バイト・{ctype}）")
        os.replace(tmp, path)
    retry(go, "動画のダウンロード")


# ---- ページの中で段の材料を集める（文の塊と画像を、ページの上から順に） ----
COLLECT = r"""() => {
 const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','SVG','TEMPLATE','IFRAME','HEAD']);
 const disp = new Map();
 const cs = el => { let s = disp.get(el); if (!s) { s = getComputedStyle(el); disp.set(el, s); } return s; };
 const shown = el => { for (let e = el; e && e !== document.body; e = e.parentElement) { const s = cs(e); if (s.display === 'none' || s.visibility === 'hidden') return false; } return true; };
 const blockOf = n => { let e = n.nodeType === 1 ? n : n.parentElement; while (e && e !== document.body) { const d = cs(e).display; if (d !== 'inline' && d !== 'contents') return e; e = e.parentElement; } return document.body; };
 const items = []; const blocks = new Map();
 const add = (b) => { let it = blocks.get(b); if (!it) { const s = cs(b), r = b.getBoundingClientRect();
   let tag = b.tagName; const h = b.closest('h1,h2,h3,h4'); if (h) tag = h.tagName;
   it = {kind: 'text', tag, raw: '', size: parseFloat(s.fontSize) || 0, weight: parseInt(s.fontWeight) || 400, y: Math.round(r.top + scrollY), color: s.color};
   blocks.set(b, it); items.push(it); } return it; };
 const pushImg = (src, el, r, extra) => { if (!src) return; items.push(Object.assign({kind: 'img', src, w: Math.round(r.width), h: Math.round(r.height), y: Math.round(r.top + scrollY), alt: (el.getAttribute('alt') || '').trim()}, extra || {})); };
 const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {acceptNode: n => {
   if (n.nodeType === 1 && SKIP.has(n.tagName.toUpperCase())) return NodeFilter.FILTER_REJECT; return NodeFilter.FILTER_ACCEPT; }});
 let n;
 while ((n = walk.nextNode())) {
  if (n.nodeType === 3) { if (!n.data.trim()) continue; const b = blockOf(n); if (!shown(b)) continue; add(b).raw += n.data; continue; }
  const el = n, t = el.tagName;
  if (t === 'BR') { const b = blockOf(el); if (blocks.has(b)) blocks.get(b).raw += '\n'; continue; }
  if (t === 'IMG' || t === 'VIDEO') { if (!shown(el)) continue; const r = el.getBoundingClientRect(); if (r.width < 40 || r.height < 40) continue;
    if (t === 'IMG') pushImg(el.currentSrc || el.src || el.dataset.src || el.dataset.lazySrc, el, r, {nw: el.naturalWidth, nh: el.naturalHeight});
    else pushImg(el.currentSrc || el.src || (el.querySelector('source') || {}).src || el.poster || '', el, r, {video: true, poster: el.poster || '', nw: el.videoWidth, nh: el.videoHeight});
    continue; }
  const bg = cs(el).backgroundImage;
  if (bg && bg.startsWith('url(') && shown(el)) { const r = el.getBoundingClientRect(); if (r.width >= 150 && r.height >= 100) { const m = bg.match(/url\(["']?([^"')]+)/); if (m) pushImg(m[1], el, r, {bg: true}); } }
 }
 for (const it of items) if (it.kind === 'text') { it.text = it.raw.replace(/[ \t\r\f\v\u00a0]+/g, ' ').replace(/ *\n */g, '\n').replace(/\n{2,}/g, '\n').trim(); delete it.raw; }
 return {title: document.title, url: location.href, height: document.documentElement.scrollHeight, items: items.filter(x => x.kind === 'img' || x.text)};
}"""

SCROLL = r"""async () => { let last = -1, same = 0;
 for (let i = 0; i < 400; i++) { window.scrollBy(0, Math.round(innerHeight * 0.8)); await new Promise(r => setTimeout(r, 200));
   const y = scrollY + innerHeight, h = document.documentElement.scrollHeight;
   if (y >= h - 2) { if (h === last && ++same >= 3) break; last = h; } }
 window.scrollTo(0, 0); await new Promise(r => setTimeout(r, 800)); }"""


def open_page(ctx, url):
    pg = ctx.new_page()
    def go():
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    retry(go, f"ページを開く {url}")
    try:
        pg.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    pg.evaluate(SCROLL)
    try:
        pg.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    return pg


def shot(pg, path):
    try:
        pg.screenshot(path=str(path), full_page=True, timeout=120000)
        return [path.name]
    except Exception as e:   # 長すぎて1枚で撮れない時は 8000px ずつ
        print(f"  1枚で撮れない（{str(e)[:80]}）。分けて撮る", file=sys.stderr)
        h = pg.evaluate("document.documentElement.scrollHeight")
        w = pg.viewport_size["width"]
        names = []
        for i, top in enumerate(range(0, h, 8000), 1):
            p = path.with_name(f"{path.stem}_{i}.png")
            pg.screenshot(path=str(p), full_page=True, clip={"x": 0, "y": top, "width": w, "height": min(8000, h - top)}, timeout=120000)
            names.append(p.name)
        return names


def is_heading(it, base):
    t = it["text"]
    if it["tag"] in ("H1", "H2", "H3", "H4") and len(t) <= 220:
        return True
    return len(t) <= 140 and it["size"] >= max(18, base * 1.3)


def split_sections(items):
    sizes = sorted(x["size"] for x in items if x["kind"] == "text" and len(x["text"]) >= 80)
    base = sizes[len(sizes) // 2] if sizes else 16
    secs = [{"見出し": "（最初の見出しの前）", "文": [], "画像": []}]
    for it in items:
        if it["kind"] == "text" and is_heading(it, base):
            secs.append({"見出し": it["text"], "文": [], "画像": []})
        elif it["kind"] == "text":
            secs[-1]["文"].append(it["text"])
        else:
            secs[-1]["画像"].append(it)
    if not secs[0]["文"] and not secs[0]["画像"]:
        secs.pop(0)
    return secs, base


def ext_of(ctype, src):
    for k, v in (("png", ".png"), ("webp", ".webp"), ("gif", ".gif"), ("svg", ".svg"), ("avif", ".avif"), ("jpeg", ".jpg"), ("jpg", ".jpg")):
        if k in (ctype or ""):
            return v
    m = re.search(r"\.(png|jpe?g|webp|gif|svg|avif)(?:\?|$)", src.lower())
    return "." + m.group(1).replace("jpeg", "jpg") if m else ".jpg"


def norm(t):
    return re.sub(r"\W+", "", t.lower())


# ---- 動く物（動画・GIF・動く WebP）: 元の形のまま保存し、カットの切れ目・コマの一覧・画面の割りを出す ----
def is_moving(path):
    b = path.read_bytes()[:4 << 20]
    if path.suffix in (".mp4", ".webm", ".mov", ".m4v"):
        return True
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return b.count(b"\x21\xf9\x04") > 1     # コマの区切りが2つ以上
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return b"ANIM" in b[:64]
    return False


def as_video(path, work):
    """ffmpeg が読めない動く WebP は Pillow でコマに開いて mp4 にする"""
    if path.suffix != ".webp":
        return path
    mp4 = work / (path.stem + "_写し.mp4")
    if mp4.exists():
        return mp4
    from PIL import Image, ImageSequence
    im = Image.open(path)
    fr = work / (path.stem + "_コマ")
    fr.mkdir(exist_ok=True)
    durs = []
    for i, f in enumerate(ImageSequence.Iterator(im)):
        f.convert("RGB").save(fr / f"{i:05d}.png"); durs.append(f.info.get("duration", 100) or 100)
    fps = max(1, round(1000 / (sum(durs) / len(durs))))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(fr / "%05d.png"), "-pix_fmt", "yuv420p",
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", str(mp4)], check=True, timeout=300)
    shutil.rmtree(fr, ignore_errors=True)
    return mp4


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
    j = json.loads(r.stdout or "{}")
    st = next((x for x in j.get("streams", []) if x.get("width")), {})
    try:
        d = float(j.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        d = None
    return d, st.get("width"), st.get("height")


def gray(path, t, w=160, h=90):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True, timeout=60)
    return r.stdout if len(r.stdout) == w * h else None


def seams(px, w=160, h=90):
    """画面の中の仕切り（縦・横にまっすぐ通る明るさの段差）を探す"""
    v, hz = [], []
    for x in range(int(w * .15), int(w * .85)):
        n = sum(1 for y in range(h) if abs(px[y * w + x] - px[y * w + x - 1]) > 18)
        if n > h * .7:
            v.append(x)
    for y in range(int(h * .1), int(h * .92)):
        n = sum(1 for x in range(w) if abs(px[y * w + x] - px[(y - 1) * w + x]) > 18)
        if n > w * .55:
            hz.append(y)
    group = lambda xs: [g[len(g) // 2] for g in _runs(xs)]
    return group(v), group(hz)


def _runs(xs):
    out = []
    for x in xs:
        if out and x - out[-1][-1] <= 3:
            out[-1].append(x)
        else:
            out.append([x])
    return out


def layout(path, t0, t1, w=160, h=90):
    """カットの中の3コマで仕切りを見て、2コマ以上に出た物だけ数える"""
    vs, hs, k = [], [], 0
    for t in (t0 + (t1 - t0) * f for f in (.25, .5, .75)):
        px = gray(path, t, w, h)
        if not px:
            continue
        k += 1
        a, b = seams(px, w, h); vs += a; hs += b
    keep = lambda xs: [g[0] for g in _runs(sorted(xs)) if len(g) >= 2]
    v, hz = keep(vs), keep(hs)
    # 広告の画面の割りはほぼ等分。仕切りが 1/3・2/3 にあれば3面、真ん中の3割（35〜65%）にあれば左右2面（中の物のまっすぐな線と分けるため）
    near = lambda f, d: any(abs(x / w - f) < d for x in v)
    name = "3面" if near(1 / 3, .07) and near(2 / 3, .07) else "左右2面" if near(.5, .15) else "1面"
    bands = []
    for y in hz:
        bands.append("上に帯" if y < h * .35 else "下に帯" if y > h * .65 else "上下2面")
    return name + ("・" + "・".join(dict.fromkeys(bands)) if bands else "")


def analyze_moving(path, work, label):
    """(1) カットの切れ目の表 (2) カットごとのコマの一覧画像 (3) 画面の割り"""
    src = as_video(path, work)
    d, vw, vh = duration(src)
    if not d:   # GIF は format に長さが無い事がある
        r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames,r_frame_rate", "-of", "csv=p=0", str(src)], capture_output=True, text=True, timeout=120)
        try:
            rate, n = r.stdout.strip().split(",")[:2]; a_, b_ = rate.split("/"); d = int(n) / (int(a_) / int(b_))
        except Exception:
            d = 0
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(src), "-vf", "select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=600)
    cuts = [0.0] + [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr) if 0.2 < float(m) < (d or 1e9) - 0.2]
    pts = []
    for t in cuts:
        if not pts or t - pts[-1] >= 0.4:
            pts.append(t)
    spans = list(zip(pts, pts[1:] + [d or pts[-1] + 1]))
    rows, sheet_parts = [], []
    for k, (t0, t1) in enumerate(spans, 1):
        rows.append({"カット": k, "始め": round(t0, 2), "終わり": round(t1, 2), "画面の割り": layout(src, t0, t1)})
        part = work / f"{label}_カット{k:02d}.jpg"
        dur = max(t1 - t0, 0.1)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.2f}", "-t", f"{dur:.2f}", "-i", str(src),
                        "-vf", f"fps={4 / dur:.4f},scale=240:-2,tile=4x1:padding=4:color=white", "-frames:v", "1", str(part)], check=True, timeout=120)
        sheet_parts.append(part)
    sheet = work.parent / "画像" / f"{label}_コマ.jpg"
    if len(sheet_parts) == 1:
        shutil.copy(sheet_parts[0], sheet)
    else:
        ins = sum((["-i", str(x)] for x in sheet_parts), [])
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", f"vstack=inputs={len(sheet_parts)}", str(sheet)], check=True, timeout=120)
    for x in sheet_parts:
        x.unlink(missing_ok=True)
    return {"秒": round(d or 0, 2), "元の大きさ": f"{vw}×{vh}" if vw else "", "カット": rows, "コマの一覧": sheet.name}


def cell(s):
    return s.replace("|", "\\|").replace("\n", "<br>")


def save_page(url, out, redo):
    from playwright.sync_api import sync_playwright
    raw = out / "生.html"
    if redo or not raw.exists():
        data, _ = retry(lambda: http_get(url), "生HTMLを取る")
        save_atomic(raw, data)
        print(f"生.html {len(data)}バイト")
    need = redo or not (out / "段.json").exists() or not list(out.glob("画面_390*.png")) or not list(out.glob("画面_1280*.png"))
    if not need:
        return json.loads((out / "段.json").read_text())
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            ctx = b.new_context(user_agent=UA_SP, viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True, locale="en-US")
            pg = open_page(ctx, url)
            data = pg.evaluate(COLLECT)
            seen_text = pg.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
            wall = r"captcha|are you a robot|access denied|attention required|verify you are human|verification|unusual traffic"
            # 題か、本文がほぼ無いページの文に壁の言葉がある時だけ（ふつうのページの中のスクリプトの語では止めない）
            if re.search(wall, data["title"], re.I) or (len(seen_text) < 1500 and re.search(wall, seen_text, re.I)) or "<punish-component" in pg.content():
                raise RuntimeError(f"ボット除けで止まった（題「{data['title']}」）。headless では取れない。ログイン済みのブラウザで開いて動画の URL を --vsl に渡すか、売り手に元の動画をもらう")
            shots390 = shot(pg, out / "画面_390.png")
            dom_dir = out / "焼き込み_作業"
            dom_dir.mkdir(exist_ok=True)
            save_atomic(dom_dir / "original-dom.html", pg.content())
            # 画像そのもの
            secs, base = split_sections(data["items"])
            (out / "画像").mkdir(exist_ok=True)
            got = {}
            for si, s in enumerate(secs, 1):
                for ii, im in enumerate(s["画像"], 1):
                    src = urllib.parse.urljoin(data["url"], im["src"])
                    name = f"段{si:02d}_{ii:02d}"
                    if src in got:
                        im["file"] = got[src]; continue
                    try:
                        if src.startswith("data:"):
                            continue
                        r = retry(lambda: ctx.request.get(src, timeout=120000 if im.get("video") else 30000, headers={"Referer": data["url"]}), f"画像 {name}", tries=2, wait=2)
                        if not r.ok:
                            im["file"] = f"（取れない HTTP {r.status}）"; continue
                        fn = name + (ext_of(r.headers.get("content-type", ""), src) if not im.get("video") else
                                     (re.search(r"\.(mp4|webm|mov|m4v)(?:\?|$)", src.lower()) and "." + re.search(r"\.(mp4|webm|mov|m4v)(?:\?|$)", src.lower()).group(1) or ".mp4"))
                        save_atomic(out / "画像" / fn, r.body())
                        im["file"] = got[src] = fn
                    except Exception as e:
                        im["file"] = f"（取れない {str(e)[:40]}）"
                    im["src"] = src
            moving = {}
            (out / "動く物_作業").mkdir(exist_ok=True)
            for s_ in secs:
                for im in s_["画像"]:
                    f = out / "画像" / im.get("file", "?")
                    if not f.is_file() or not is_moving(f):
                        continue
                    if f.name not in moving:
                        try:
                            moving[f.name] = analyze_moving(f, out / "動く物_作業", f.stem)
                        except Exception as e:
                            moving[f.name] = {"失敗": str(e)[:120]}
                    im["動く"] = moving[f.name]
            shutil.rmtree(out / "動く物_作業", ignore_errors=True)
            ctx.close()
            ctx2 = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}, device_scale_factor=1, locale="en-US")
            pg2 = open_page(ctx2, url)
            shots1280 = shot(pg2, out / "画面_1280.png")
            # 1280 の幅でだけ出る文（スマホでは隠している段）も落とさない
            seen = {norm(t) for x in data["items"] if x["kind"] == "text" for t in [x["text"]]}
            wide = [x["text"] for x in pg2.evaluate(COLLECT)["items"] if x["kind"] == "text" and norm(x["text"]) not in seen]
            wide = list(dict.fromkeys(t for t in wide if len(norm(t)) >= 3))
            ctx2.close()
        finally:
            b.close()
    res = {"url": url, "最後のURL": data["url"], "題": data["title"], "高さ_390": data["height"], "本文の字の大きさ": base,
           "画面": shots390 + shots1280, "段": secs, "1280だけの文": wide}
    save_atomic(out / "段.json", json.dumps(res, ensure_ascii=False, indent=1))
    write_md(res, out)
    return res


def write_md(res, out):
    secs = res["段"]
    nimg = sum(len(s["画像"]) for s in secs)
    nchr = sum(len(t) for s in secs for t in s["文"]) + sum(len(s["見出し"]) for s in secs)
    L = [f"# 段: {res['題']}", "",
         f"- URL: {res['url']}" + (f"（着いた先 {res['最後のURL']}）" if res["最後のURL"] != res["url"] else ""),
         f"- 取った日: {date.today().isoformat()}・幅390で割った・段 {len(secs)}・画像 {nimg}枚・文 {nchr}字",
         f"- 割り方: h1〜h4 と、本文（{res['本文の字の大きさ']:.0f}px）の1.3倍以上の大きさの短い行を見出しとして段を切る。画像は幅390で表示された大きさ（元の大きさ）",
         f"- 画面: {'・'.join(res['画面'])}",
         "- 動く物（動画・GIF・動く WebP）は元の形のまま保存。カットの切れ目は ffmpeg の scene 検出（0.3）、画面の割りはカットの中の3コマに縦・横にまっすぐ通る仕切りが2コマ以上に出た物", "",
         "| 段 | 画像 | 文 |", "|---|---|---|"]
    for i, s in enumerate(secs, 1):
        imgs = []
        for im in s["画像"]:
            sz = f"表示 {im['w']}×{im['h']}" + (f"・元 {im['nw']}×{im['nh']}" if im.get("nw") else "")
            kind = "動画 " if im.get("video") else ("背景 " if im.get("bg") else "")
            mv = im.get("動く")
            if mv and not mv.get("失敗"):
                kind = kind or "動く画像 "
                sz += f"・{mv['秒']}秒" + (f"・元 {mv['元の大きさ']}" if mv.get("元の大きさ") and "元" not in sz else "") + f"・カット{len(mv['カット'])}"
            imgs.append(f"{kind}{im.get('file', '（未保存）')}（{sz}）" + (f" alt「{im['alt']}」" if im.get("alt") else ""))
            if mv and mv.get("失敗"):
                imgs.append(f"　動きを割れなかった: {mv['失敗']}")
            elif mv:
                for c in mv["カット"]:
                    imgs.append(f"　カット{c['カット']} {c['始め']:.1f}〜{c['終わり']:.1f}秒 {c['画面の割り']}")
                imgs.append(f"　コマの一覧: {mv['コマの一覧']}（1行＝1カット・左から4コマ）")
        body = [f"**{s['見出し']}**"] + s["文"]
        L.append(f"| {i} | {cell(chr(10).join(imgs)) or '（なし）'} | {cell(chr(10).join(body))} |")
    wide = res.get("1280だけの文") or []
    L += ["", f"## 1280の幅でだけ出る文（{len(wide)}個。スマホでは隠している）", ""] + [f"- {t}".replace("\n", " / ") for t in wide]
    save_atomic(out / "段.md", "\n".join(L) + "\n")


def bake(url, out, redo):
    if not redo and (out / "焼き込み.html").exists():
        return "済"
    work = out / "焼き込み_作業"
    shutil.copy(out / "生.html", work / "original.html")
    scripts = find("WEBSITE_COPY_SCRIPTS", "website-copy", "scripts")
    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(url))
    note = ""
    try:
        if not scripts or not shutil.which("node"):
            raise RuntimeError("website-copy の scripts か node が無い")
        subprocess.run(["node", str(scripts / "transform.mjs"), str(work), origin], check=True, capture_output=True, timeout=120)
        subprocess.run(["node", str(scripts / "bake.mjs"), str(work), url], check=True, capture_output=True, timeout=180, env={**os.environ, "CAPTURED": "1"})
        shutil.copy(work / "clone-baked.html", out / "焼き込み.html")
        note = "website-copy で焼き込み"
    except Exception as e:   # 焼き込めない時は JS 実行後の DOM をそのまま残す（文と画像の抜き出しはこれと同じ物から取っている）
        shutil.copy(work / "original-dom.html", out / "焼き込み.html")
        note = f"焼き込めず JS 実行後の DOM をそのまま（{str(e)[:80]}）"
    print(f"焼き込み.html: {note}")
    return note


def pick_vsl(tadoru, url):
    j = json.loads((Path(tadoru) / "広告.json").read_text())
    want = urllib.parse.urlparse(url)
    def same_path(l):
        u = urllib.parse.urlparse(l or "")
        return u.netloc.lower().removeprefix("www.") == want.netloc.lower().removeprefix("www.") and u.path.rstrip("/") == want.path.rstrip("/")
    vids = [a for a in j.get("広告", []) if a.get("動画")]
    if not vids:
        return None, None
    vids.sort(key=lambda a: (not same_path(a.get("飛び先")), not a.get("同じドメイン"), -(a.get("日数") or 0)))
    a = vids[0]
    return a["動画"][0], f"広告 {a['id']}（{a.get('日数')}日・{'同じ飛び先' if same_path(a.get('飛び先')) else '飛び先 ' + str(a.get('飛び先'))}）{a.get('広告ライブラリ', '')}"


def transcribe(vsl, src_note, out, redo):
    txt = out / "文字起こし.txt"
    if not redo and txt.exists():
        m = re.search(r"尺 ([\d.]+)秒", txt.read_text().splitlines()[0])
        return float(m.group(1)) if m else None
    w = out / "vsl"
    w.mkdir(exist_ok=True)
    mp4 = w / "動画.mp4"
    if os.path.exists(os.path.expanduser(vsl)):
        mp4 = Path(os.path.expanduser(vsl))
    elif redo or not mp4.exists():
        if re.search(r"\.(mp4|mov|m4v|webm)(\?|$)", vsl.lower()) or "fbcdn" in vsl or "/download" in vsl:
            download(vsl, mp4)
        else:
            if not shutil.which("yt-dlp"):
                raise RuntimeError("yt-dlp が無い")
            retry(lambda: subprocess.run(["yt-dlp", "-q", "-f", "mp4/best", "-o", str(mp4), vsl], check=True, timeout=900), "yt-dlp")
    sh = find("TRANSCRIBE_SH", "fukikae", "scripts", "01_transcribe.sh")
    if not sh:
        raise RuntimeError("fukikae の 01_transcribe.sh が無い")
    for tool in ("ffmpeg", "whisper-cli"):
        if not shutil.which(tool):
            raise RuntimeError(f"{tool} が無い")
    subprocess.run(["bash", str(sh), str(mp4), str(w / "作業")], check=True, timeout=3600, capture_output=True)
    srt = (w / "作業" / "whisper.srt").read_text(encoding="utf-8", errors="ignore")
    dur = float((w / "作業" / "duration.txt").read_text().strip())
    lines = []
    for blk in re.split(r"\n\s*\n", srt.strip()):
        p = blk.strip().splitlines()
        if len(p) >= 3 and "-->" in p[1]:
            a, b = [x.strip().replace(",", ".")[:11] for x in p[1].split("-->")]
            lines.append(f"[{a} → {b}] {' '.join(p[2:]).strip()}")
    head = f"# 文字起こし 尺 {dur:.1f}秒・{len(lines)}行・whisper large-v3-turbo・出どころ {src_note}"
    save_atomic(txt, head + "\n" + "\n".join(lines) + "\n")
    for f in ("src.mp4", "src.wav"):   # 大きい写しは消す（元の動画は vsl/動画.mp4）
        (w / "作業" / f).unlink(missing_ok=True)
    print(f"文字起こし.txt {len(lines)}行・{dur:.0f}秒")
    return dur


def main(a):
    if len(a) < 2 or a[0].startswith("-"):
        print(__doc__); return 2
    url, out = a[0], Path(os.path.expanduser(a[1]))
    opt = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
    vsl, tadoru, redo = opt("--vsl"), opt("--辿る"), "--やり直す" in a
    out.mkdir(parents=True, exist_ok=True)
    try:
        import playwright  # noqa
    except ImportError:
        print("道具が無い: pip install playwright && playwright install chromium", file=sys.stderr); return 2
    try:
        res = save_page(url, out, redo)
        note = bake(url, out, redo)
    except Exception as e:
        print(f"記事が取れなかった: {e}", file=sys.stderr); return 2
    rec = {"url": url, "取った日": date.today().isoformat(), "段の数": len(res["段"]),
           "画像の数": sum(len(s["画像"]) for s in res["段"]), "焼き込み": note}
    code = 0
    src_note = vsl
    if not vsl and tadoru:
        try:
            vsl, src_note = pick_vsl(tadoru, url)
        except Exception as e:
            print(f"広告.json が読めない: {e}", file=sys.stderr)
        if not vsl:
            rec["VSL"] = "辿った広告に動画が無い"; code = 1
    if vsl:
        try:
            rec["文字起こしの秒数"] = transcribe(vsl, src_note, out, redo)
            rec["VSL"] = src_note
        except Exception as e:
            rec["VSL"] = f"文字起こしが出来なかった: {str(e)[:200]}"; code = 1
            print(rec["VSL"], file=sys.stderr)
    save_atomic(out / "記録.json", json.dumps(rec, ensure_ascii=False, indent=1))
    print(f"段 {rec['段の数']}・画像 {rec['画像の数']}枚" + (f"・文字起こし {rec['文字起こしの秒数']:.0f}秒" if rec.get("文字起こしの秒数") else "") + f" → {out}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
