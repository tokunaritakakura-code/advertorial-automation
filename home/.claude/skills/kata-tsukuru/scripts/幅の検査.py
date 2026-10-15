#!/usr/bin/env python3
"""出来た飛び先を、パソコン（1280）とスマホ（390）の幅で開き、崩れを数える。

使い方: python3 幅の検査.py <index.html のパスか URL> [--押す <回数>]
  --押す N: アンケートの答えのボタン（[data-answer]）を N 回押し、押すたびに次の問いが出るか、
            最後に「ご回答」の画面が出るかを確かめる（既定 0）
見る物: 文の最後の行に1〜2文字だけ落ちた所（句読点は数えない）・横のはみ出し（ページ幅より広い）・画像の抜け（読めなかった img。小さな画像も数える）・
        細長い画像（幅40pxより大きい物で、縦÷横 0.4未満・2.5超）・押した後の画面の進み・
        最初の画面の最初の写真（本文の最初の画像か動画（幅80px以上）の上端が 画面の高さ−100px より上。1280×800 と 390×844。
        申込のページ（パスに /申込/）には当てない。2026-10-11 本人「最初の写真が入るぐらいに」。正本は Vault ec/構造/型/_必ず入れる物.md の 1）
終了コード: 0=全部0 / 1=どれかが1以上 / 2=道具が動かない・開けない（ページの見た目のせいではない）
本人のブラウザ（Dia）には繋がない。手元の Playwright の Chromium を裏で立てる。
"""
import os, sys

JS = r"""async () => {
  // 遅れて読む画像も読ませるため、一番下まで送ってから戻す
  for (let y = 0; y < document.body.scrollHeight; y += 700) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); }
  window.scrollTo(0, 0);
  // 隠した箱の中の遅れて読む画像は読み込まれず decode が返らない。1枚3秒で待つのをやめる（2026-10-12 申込のページで止まった）
  await Promise.all([...document.images].map(i => i.decode ? Promise.race([i.decode().catch(() => {}), new Promise(r => setTimeout(r, 3000))]) : null));
  const W = document.documentElement.clientWidth;
  const over = [...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.right > W + 1 && s.position !== 'fixed' && !e.closest('[data-marquee],.marquee');
  }).slice(0, 5).map(e => e.tagName + '.' + (e.className || '').toString().slice(0, 30));
  const imgs = [...document.images];
  const broken = imgs.filter(i => i.naturalWidth === 0 && getComputedStyle(i).display !== 'none').map(i => (i.currentSrc || i.src).slice(-60));
  const thin = imgs.filter(i => i.naturalWidth > 0 && i.getBoundingClientRect().width > 40)
                   .filter(i => { const q = i.naturalHeight / i.naturalWidth; return q < 0.4 || q > 2.5; })
                   .map(i => i.src.slice(-60));
  // 文の最後の行に1〜2文字だけ落ちた所（句読点と括弧は数えない）。行は「次の字が左に戻った所」で分ける
  await document.fonts.ready;
  const P = /[、。？！「」『』（）()・…\s!?]/;
  const orphans = [];
  for (const el of document.querySelectorAll('p,h1,h2,h3,h4,li,td,dd,span,div,strong,b,a,button')) {  // a・button はボタンの「›」だけが落ちるのを拾う（2026-10-11 睡眠イヤホン）
    if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    const r0 = el.getBoundingClientRect(); if (!r0.width || getComputedStyle(el).display === 'none') continue;
    const chars = [];
    const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n; while ((n = walk.nextNode())) {
      for (let i = 0; i < n.textContent.length; i++) {
        const rg = document.createRange(); rg.setStart(n, i); rg.setEnd(n, i + 1);
        const b = rg.getClientRects()[0]; if (b && b.width) chars.push([n.textContent[i], b.left]);
      }
    }
    if (chars.length < 6) continue;
    let lines = [[]];
    for (let i = 0; i < chars.length; i++) {
      if (i && chars[i][1] < chars[i - 1][1] - 2) lines.push([]);
      lines[lines.length - 1].push(chars[i][0]);
    }
    if (lines.length < 2) continue;
    const last = lines[lines.length - 1].filter(c => !P.test(c));
    if (last.length > 0 && last.length <= 2) orphans.push(lines.slice(-2).map(l => l.join('')).join('｜').slice(-30));
  }
  // 文がはみ出して切れている要素（中身の幅が枠の幅より4px以上広い・画面の右端より外に字がある）。2026-10-10 nowrap の枠で「ます。」が切れたのを拾えなかった
  const clipped = [...document.querySelectorAll('p,h1,h2,h3,h4,li,div,span,b,strong')].filter(e => {
    if (![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return false;
    const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (e.closest('[data-marquee],.marquee')) return false;  // 流れる帯は横に長いのが正しい（はみ出しの判定と同じ除外。2026-10-11 ranking-static の申込の帯）
    const r = e.getBoundingClientRect(); if (!r.width) return false;
    // 横に送る箱（overflow-x が auto か scroll。客の声の横送りなど）の中で画面の右へ出ている物は、送れば見えるので切れではない（2026-10-12 arukoto-listicle の声の横送り）
    let 送る箱 = false; for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') { 送る箱 = true; break; } }
    return e.scrollWidth > e.clientWidth + 4 && s.overflowX !== 'auto' && s.overflowX !== 'scroll' || (!送る箱 && r.right > W + 2);
  }).slice(0, 5).map(e => e.textContent.trim().slice(0, 24));
  // 必ず入れる物2: 値段の段（data-tasu=2）の中の縦長の画像は 幅÷高さ 0.67〜0.75
  const price = [...document.querySelectorAll('[data-tasu="2"] img')].filter(i => i.naturalWidth && i.naturalHeight > i.naturalWidth)
    .map(i => i.naturalWidth / i.naturalHeight).filter(q => q < 0.67 || q > 0.75).map(q => q.toFixed(3));
  // 最初の画面に最初の写真（2026-10-11 本人）: 本文の最初の画像か動画（幅80px以上・浮く帯や隠れた窓の中は数えない）の上端（ページの頭から）
  const media = [...document.querySelectorAll('img,video')].find(e => {
    const r = e.getBoundingClientRect(); if (r.width < 80 || r.height < 10) return false;
    for (let p = e; p && p !== document.body; p = p.parentElement) {
      const ps = getComputedStyle(p);
      if (ps.position === 'fixed' || ps.display === 'none' || ps.visibility === 'hidden' || ps.opacity === '0') return false;
    }
    return true;
  });
  const first = media ? {top: Math.round(media.getBoundingClientRect().top + window.scrollY), src: (media.currentSrc || media.src || media.poster || '').split('/').pop().slice(0, 40)} : null;
  // 最悪の結末の箱（data-tasu="1"）の下端（仕掛けの棚 B5: 最初の画面に全部入れる。2026-10-12 本人）
  const t1 = [...document.querySelectorAll('[data-tasu="1"]')].find(e => e.getBoundingClientRect().height > 0);  // 幅で出し分ける2つの箱のうち見えている方
  const box1 = t1 ? Math.round(t1.getBoundingClientRect().bottom + window.scrollY) : null;
  return {scrollW: document.documentElement.scrollWidth, W, over, broken, thin, orphans: [...new Set(orphans)], price, clipped, first, box1};
}"""

STATE = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const ans = [...document.querySelectorAll('[data-answer]')].filter(vis);
  const qs = new Set(ans.map(a => (a.closest('[data-q],[data-dan]') || a.parentElement).getAttribute('data-q') || (a.closest('[data-dan]') || {}).dataset?.dan || ''));
  return {answers: ans.length, groups: [...qs].join(','), thanks: [...document.querySelectorAll('body *')].some(e => vis(e) && e.children.length === 0 && /ご回答/.test(e.textContent + (e.alt || '')))};
}"""


def main(a):
    if not a:
        print(__doc__); return 2
    target = a[0]
    try:
        presses = int(a[a.index("--押す") + 1]) if "--押す" in a else 0
    except (IndexError, ValueError):
        print("使い方: --押す の後に回数（数字）", file=sys.stderr); return 2
    url = target if target.startswith("http") else "file://" + os.path.abspath(os.path.expanduser(target))
    from urllib.parse import unquote
    申込 = "/申込/" in unquote(url) or unquote(url).rstrip("/").endswith("/申込")  # 申込のページ（商品の申込）は最初の写真の検査を当てない
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("道具が無い: pip install playwright", file=sys.stderr); return 2
    bad = 0
    try:
        with sync_playwright() as pw:
            try:
                b = pw.chromium.launch(headless=True)
            except Exception as e:
                print(f"Chromium が立たない: {e}\n→ `python3 -m playwright install chromium`", file=sys.stderr); return 2
            try:
                for w, h in ((1280, 800), (390, 844)):
                    pg = b.new_page(viewport={"width": w, "height": h})
                    try:
                        pg.goto(url, wait_until="load", timeout=30000)
                    except Exception as e:
                        print(f"開けない（{w}）: {e}", file=sys.stderr); return 2
                    r = pg.evaluate(JS)
                    wide = r["scrollW"] > r["W"] + 1
                    cnt = int(wide) + len(r["broken"]) + len(r["thin"]) + len(r["orphans"]) + len(r["price"]) + len(r["clipped"])
                    # 最初の画面に最初の写真: 上端が 画面の高さ−100px より上（申込のページには当てない）
                    first_txt = "申込のページなので見ない"
                    if not 申込:
                        lim = h - 100
                        if not r["first"]:
                            cnt += 1; first_txt = "×（本文に幅80px以上の画像・動画が無い）"
                        elif r["first"]["top"] >= lim:
                            cnt += 1; first_txt = f"×（上端 {r['first']['top']}px・画面の中に入る線は {lim}px より上。頭の文を縮める: {r['first']['src']}）"
                        else:
                            first_txt = f"○（上端 {r['first']['top']}px < {lim}px）"
                    if not 申込 and r.get("box1") is not None:
                        if r["box1"] > h:
                            cnt += 1; first_txt += f"・最悪の結末の箱×（下端 {r['box1']}px が最初の画面 {h}px の外。箱を短くするか上に寄せる。仕掛けの棚 B5）"
                        else:
                            first_txt += f"・最悪の結末の箱○（下端 {r['box1']}px）"
                    bad += cnt
                    print(f"幅{w}: はみ出し{'あり ' + str(r['over']) if wide else '0'}・画像の抜け{len(r['broken'])}・細長い画像{len(r['thin'])}・行末の1〜2文字落ち{len(r['orphans'])}・値段の縦長画像の比の外れ{len(r['price'])}・はみ出して切れた文{len(r['clipped'])}・最初の画面の最初の写真{first_txt}")
                    for k in ("broken", "thin", "orphans", "price", "clipped"):
                        for s in r[k]:
                            print(f"   {k}: {s}")
                    if presses:
                        before = pg.evaluate(STATE)
                        for n in range(presses):
                            btn = pg.query_selector("[data-answer]:visible")
                            if not btn:
                                print(f"幅{w} {n + 1}回目: 押せる答えのボタン（[data-answer]）が無い → ×"); bad += 1; break
                            try:
                                btn.click(timeout=5000)
                            except Exception as e:
                                print(f"幅{w} {n + 1}回目: 押せない（上に別の物が乗っている等）: {str(e).splitlines()[0]} → ×"); bad += 1; break
                            pg.wait_for_timeout(1500)   # ページの中で画面が切り替わる作りは load を待っても戻るので、少し待つ
                            after = pg.evaluate(STATE)
                            last = n == presses - 1
                            if not last and after["groups"] == before["groups"] and after["answers"] == before["answers"]:
                                print(f"幅{w} {n + 1}回目: 押しても次の問いに進まない → ×"); bad += 1; break
                            before = after
                        else:
                            if not pg.evaluate(STATE)["thanks"]:
                                print(f"幅{w}: {presses}回押した後に「ご回答」の画面が見えない → ×"); bad += 1
                            else:
                                print(f"幅{w}: {presses}回押して「ご回答」の画面まで出た")
                    pg.close()
            finally:
                b.close()
    except Exception as e:
        print(f"道具が途中で止まった: {type(e).__name__}: {e}", file=sys.stderr); return 2
    print("通った" if bad == 0 else f"落ちた: {bad}件")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
