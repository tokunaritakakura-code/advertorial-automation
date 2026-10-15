#!/usr/bin/env python3
"""clarity_shot — Clarityの画面を画面外のブラウザで開いてPNGにする。

本人の画面には何も出ない。フォーカスも奪わない。
撮ったPNGをClaudeが読んで判断する。APIでは取れないもの
（録画・ヒートマップ・クリックマップ・エラーの文言）はここでしか見えない。

前提: 専用プロファイルにClarityのログインが1回通っていること。

  python3 clarity_shot.py <view> [--url <ページのURL>] [--days 1|2|3] [--out name.png]

  view:
    dashboard   ダッシュボード全体
    heatmap     ヒートマップ（--url 必須）
    recordings  録画一覧
    errors      JSエラーの内訳
"""
import argparse
import os
import sys
import time
import urllib.parse

PROJECT = os.environ.get("CLARITY_PROJECT", "y6dscmxm7v")
PORT = int(os.environ.get("DIA_AGENT_PORT", "9333"))
BASE = f"https://clarity.microsoft.com/projects/view/{PROJECT}"

VIEWS = {
    "dashboard": "/dashboard",
    "heatmap": "/heatmaps",
    "recordings": "/impressions",
    "errors": "/dashboard",
}


def build_url(view, page_url, days):
    path = VIEWS.get(view)
    if path is None:
        sys.exit(f"error 知らないview: {view}. 使えるのは {', '.join(VIEWS)}")
    q = {"date": f"Last {days} day" + ("s" if days > 1 else "")}
    if page_url:
        q["Url"] = page_url
    return BASE + path + "?" + urllib.parse.urlencode(q)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("view")
    ap.add_argument("--url", default=None, help="絞り込むページのURL")
    ap.add_argument("--days", type=int, default=1, choices=[1, 2, 3])
    ap.add_argument("--out", default=None)
    ap.add_argument("--wait", type=int, default=9, help="描画待ち秒")
    ap.add_argument("--full", action="store_true", help="ページ全体を撮る")
    a = ap.parse_args()

    out = a.out or f"clarity-{a.view}.png"
    out = os.path.abspath(out)
    url = build_url(a.view, a.url, a.days)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        ctx = b.contexts[0]
        pg = ctx.new_page()
        pg.set_viewport_size({"width": 1440, "height": 900})
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        # 固定待ちを避けたいが、Clarityは描画完了の目印を出さない。
        # サインインに落ちていないかだけ先に見て、落ちていれば即終わる。
        time.sleep(3)
        if "signin" in pg.url or "login.microsoftonline" in pg.url:
            print("NOT_LOGGED_IN " + pg.url[:90])
            pg.close()
            b.close()
            sys.exit(4)
        time.sleep(max(0, a.wait - 3))
        pg.screenshot(path=out, full_page=a.full)
        print(f"ok {out} url={pg.url[:100]}")
        pg.close()
        b.close()


if __name__ == "__main__":
    main()
