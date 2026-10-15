"""漫画の記事（物語の記事の日本版）を組む部品。記事ごとの 組む.py から読み込んで使う（商品の値はここに書かない）。

使い方（記事の 組む.py の頭）:
    import importlib.util, os
    p = os.path.expanduser("~/.claude/skills/quiz-jp-copy/scripts/漫画の部品.py")
    s = importlib.util.spec_from_file_location("k", p); K = importlib.util.module_from_spec(s); s.loader.exec_module(K)
    K.setup(動く={17, 36, ...}, 細い帯={73, 130}, 画像の文=lambda n: "<その画像の中の字>")
    B = [K.sec(1, 1, [K.img(0), K.t("まさか40代半ばで…"), ...]), ...]
    open("index.html", "w").write(K.page("<題>", B, 申込="申込/index.html", 札の画像="img/m900.jpg", 札の文="..."))

部品（見た目は 漫画の部品/記事.css、動きは 記事.js。YURiiRO 漫画の記事 2026-10-10 から写した）:
    img(n)        画像1枚。動く番号は <video> と止まった絵（alt つき）。細い帯は <video> だけ（細長い画像にしない）
    t(s)          地の文1行（中央寄せ）。続けて並ぶ行は sec() が1段落にまとめる（文の途中で段落を切らない）
    fuki(s)       主人公の心の声: 顔アイコン（img/m901.jpg）＋水色の吹き出し
    pfuki(s)      ピンクの吹き出し（左下に丸2つ）。友人や大事な一言
    dots() typing() bars() arrows() chev()  間をつなぐ動く印（…・入力中・棒・下向きの矢印3つ・山形）
    hbox(s)       見出しの帯（緊急追記など）
    q(no, 題, 画像の番号, 答え)  アンケート1問（丸番号・灰色の丸ボタン・押すとピンクで次の問いへ送る）
    sec(型の段, 参考の段, 中身, extra)  <section data-dan data-kdan>。必ず入れる物は extra=' data-tasu="1"'
    page(題, 段の一覧, ...)  1枚の index.html（noindex・右下の札・CSS と JS を中に入れる・<body data-format="漫画">。記事の仕上がり検査.py はこの印で漫画と見分ける）
"""
import html, os, re

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "漫画の部品")
動く, 細い帯 = set(), set()
_alt = lambda n: ""


def setup(動く=(), 細い帯=(), 画像の文=None):
    global _alt
    globals()["動く"] = set(動く); globals()["細い帯"] = set(細い帯)
    if 画像の文: _alt = 画像の文


def img(n, cls="full"):
    a = html.escape(_alt(n), quote=True)
    if n in 細い帯:
        return f'<video class="{cls}" src="img/m{n:03d}.mp4" poster="img/m{n:03d}.jpg" autoplay muted loop playsinline aria-label="{a}"></video><span class="sr">{a}</span>'
    if n in 動く:
        return (f'<div class="vid {cls}"><video class="full" src="img/m{n:03d}.mp4" poster="img/m{n:03d}.jpg" autoplay muted loop playsinline></video>'
                f'<img class="vpost" src="img/m{n:03d}.jpg" alt="{a}"></div>')
    return f'<img class="{cls}" src="img/m{n:03d}.jpg" alt="{a}">'


def t(s): return f'<p class="l">{s}</p>'
def gap(): return '<div class="sp"></div>'
def fuki(s): return f'<div class="fk"><img class="ic" src="img/m901.jpg" alt=""><div class="fb">{s}</div></div>'
def pfuki(s): return f'<div class="pf"><div class="pb">{s}</div><i></i><i></i></div>'
def dots(): return '<div class="dots"><i></i><i></i><i></i></div>'
def typing(): return '<div class="typ"><span class="d1"></span><span class="d2"></span><span class="d3"></span></div>'
def bars(): return '<div class="bars"><i></i><i></i><i></i></div>'
def arrows(): return '<div class="arr3"><i class="mv"></i><i class="mv"></i><i class="mv"></i></div>'
def chev(): return '<div class="chev"><i class="c1"></i><i class="c2"></i></div>'
def hbox(s): return f'<div class="hbox">{s}</div>'


PL = re.compile(r'^<p class="l([^"]*)">(.*)</p>$', re.S)


def merge(body):
    out, grp = [], []
    def flush():
        if not grp: return
        if len(grp) == 1: out.append(f'<p class="l{grp[0][0]}">{grp[0][1]}</p>')
        else: out.append('<p class="l">' + "".join(f'<span class="seg{c}">{x}</span>' for c, x in grp) + '</p>')
        grp.clear()
    for b in body:
        m = PL.match(b)
        if m and "<p" not in m.group(2): grp.append((m.group(1), m.group(2)))
        else: flush(); out.append(b)
    flush()
    return out


def sec(dan, k, body, extra=""):
    return f'<section data-dan="{dan}" data-kdan="{k}"{extra}>\n' + "\n".join(merge(body)) + "\n</section>"


def q(no, title, pic, opts, total=3):
    nums = "".join(f'<span class="{"cur" if i == no else ("done" if i < no else "")}">0{i}</span>' for i in range(1, total + 1))
    btns = "".join(f'<button type="button" class="ans" data-answer="{i + 1}">{o}</button>' for i, o in enumerate(opts))
    return (f'<div class="qa" data-q="{no}" id="q{no}"><div class="navi">{nums}</div><h3 class="qt"><span class="sr">Q{no}.</span>{title}</h3>'
            f'{img(pic, "qimg")}<p class="note r">※画像はイメージです</p><div class="opts">{btns}</div></div>')


def send_button(label="回答を完了する"):
    """最後の問いの下に置く。押すと id="reveal" の値段の画像が出る"""
    return f'<div class="send" id="sendwrap"><button type="button" id="send">{label}</button></div>'


def page(title, B, 申込="申込/index.html", 札の画像="img/m900.jpg", 札の文="", css_extra=""):
    body = "\n".join(B)
    if 'id="send"' in body and 'id="reveal"' not in body:
        raise ValueError("「回答を完了する」があるのに、出す値段の画像（id=\"reveal\"）が無い")
    css = open(os.path.join(HERE, "記事.css"), encoding="utf-8").read() + css_extra
    js = open(os.path.join(HERE, "記事.js"), encoding="utf-8").read()
    p = f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{html.escape(title)}</title>
<style>{css}</style></head><body data-format="漫画">
<!-- テスト用の値: テスト用に決めた値.md と 予測した事.md に一覧 -->
<main class="wrap">
{chr(10).join(B)}
</main>
<div class="fixpop" id="fixpop"><button type="button" class="x" id="fixx" aria-label="閉じる">×</button><a data-cta="popup" href="{申込}"><img src="{札の画像}" alt="{html.escape(札の文, quote=True)}"></a></div>
<script>{js}</script></body></html>'''
    return p.replace("<br>", '<span class="brk"></span>')
