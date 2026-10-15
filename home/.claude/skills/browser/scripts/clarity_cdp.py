#!/usr/bin/env python3
"""clarity_cdp — Clarityの画面と録画を、画像ではなく中身で取る。

なぜ画像で読まないか:
  Clarityの録画は動画ではなく、DOMの変化とイベントの記録。プレーヤーが裏でJSONを取って
  ブラウザ上で再現している。その通信を横取りすれば「何秒に何%スクロールした」「何秒に
  どの要素を押した」が文字で取れる。スクショから読むより速く、要素のセレクタまで正確。

  絵が要るのは、重なり具合や動きそのものを見る時だけ。そこだけコマ撮りする。

前提:
  CDPが開いているブラウザに、Clarityのログイン済みセッションがあること。
  ポートは --port（既定 9222）。

  probe   指定URLを開いて、飛んだ通信を全部ファイルに落とす（形を知るための工程）
  shots   指定URLを開いて、一定間隔でコマ撮りする
  ls      落とした通信を大きい順に並べて、どれが本体かを見る

例:
  python3 clarity_cdp.py probe --url "https://clarity.microsoft.com/projects/view/<id>/impressions" --out ~/clarity/rec
  python3 clarity_cdp.py ls --out ~/clarity/rec
  python3 clarity_cdp.py shots --url "<プレーヤーのURL>" --out ~/clarity/play --shots 12 --every 2
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse

DEFAULT_PORT = int(os.environ.get("CLARITY_CDP_PORT", "9222"))
SKIP_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com", "browser.events.data.microsoft.com")
SKIP_TYPES = ("image/", "font/", "text/css", "video/", "audio/")


def safe_name(url, i):
    p = urllib.parse.urlparse(url)
    tail = (p.path or "/").strip("/").replace("/", "_") or "root"
    tail = re.sub(r"[^A-Za-z0-9._-]", "-", tail)[:70]
    return f"{i:04d}_{tail}.json"


def connect(port):
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=60000)
    except Exception as e:
        pw.stop()
        sys.exit(f"error CDPに繋がらない port={port}: {str(e)[:160]}")
    if not b.contexts:
        pw.stop()
        sys.exit("error ブラウザにコンテキストが無い")
    return pw, b


def guard_login(pg):
    u = pg.url or ""
    if "signin" in u or "login.microsoftonline" in u or "login.live.com" in u:
        print("NOT_LOGGED_IN " + u[:110])
        return False
    return True


def cmd_probe(a):
    out = os.path.abspath(a.out)
    bodies = os.path.join(out, "bodies")
    os.makedirs(bodies, exist_ok=True)
    manifest = []
    seen = {"n": 0}

    pw, b = connect(a.port)
    ctx = b.contexts[0]
    pg = ctx.new_page()
    pg.set_viewport_size({"width": a.width, "height": a.height})

    def on_response(resp):
        try:
            url = resp.url
            if any(h in url for h in SKIP_HOSTS):
                return
            ct = (resp.headers or {}).get("content-type", "")
            if any(ct.startswith(t) for t in SKIP_TYPES):
                return
            seen["n"] += 1
            i = seen["n"]
            row = {"i": i, "url": url, "status": resp.status, "type": ct, "bytes": None, "file": None}
            try:
                body = resp.body()
            except Exception:
                manifest.append(row)
                return
            row["bytes"] = len(body)
            # JSONらしいものだけ本体を保存する。HTMLとJSは形を知る役に立たない。
            looks_json = "json" in ct or body[:1] in (b"{", b"[")
            if looks_json and len(body) > 0:
                fn = safe_name(url, i)
                tmp = os.path.join(bodies, fn + ".part")
                with open(tmp, "wb") as f:
                    f.write(body)
                os.replace(tmp, os.path.join(bodies, fn))
                row["file"] = fn
            manifest.append(row)
        except Exception:
            pass

    pg.on("response", on_response)

    try:
        pg.goto(a.url, wait_until="domcontentloaded", timeout=90000)
    except Exception as e:
        print("goto失敗:", str(e)[:150])
    time.sleep(3)
    if not guard_login(pg):
        _finish(out, manifest, pg, b, pw)
        sys.exit(4)

    # 画面が描き終わる目印をClarityは出さないので、指定秒だけ通信を拾い続ける。
    t0 = time.time()
    while time.time() - t0 < a.seconds:
        time.sleep(0.5)

    if a.shot:
        try:
            pg.screenshot(path=os.path.join(out, "screen.png"))
        except Exception as e:
            print("スクショ失敗:", str(e)[:120])

    _finish(out, manifest, pg, b, pw)
    kept = [m for m in manifest if m.get("file")]
    print(f"ok 通信{len(manifest)}件 / JSON保存{len(kept)}件 -> {out}")
    print(f"   次: python3 {os.path.basename(__file__)} ls --out {out}")


def _finish(out, manifest, pg, b, pw):
    tmp = os.path.join(out, "manifest.json.part")
    with open(tmp, "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(out, "manifest.json"))
    try:
        pg.close()
    except Exception:
        pass
    try:
        b.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass


def cmd_ls(a):
    out = os.path.abspath(a.out)
    p = os.path.join(out, "manifest.json")
    if not os.path.exists(p):
        sys.exit(f"error manifestが無い: {p}")
    rows = json.load(open(p))
    rows = [r for r in rows if r.get("bytes")]
    rows.sort(key=lambda r: -(r.get("bytes") or 0))
    print(f"{'bytes':>10}  {'status':>6}  file / url")
    for r in rows[: a.top]:
        u = r["url"]
        u = u if len(u) <= 96 else u[:93] + "..."
        print(f"{r['bytes']:>10}  {r['status']:>6}  {r.get('file') or '-'}\n{'':>20}{u}")


def cmd_shots(a):
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    pw, b = connect(a.port)
    ctx = b.contexts[0]
    pg = ctx.new_page()
    pg.set_viewport_size({"width": a.width, "height": a.height})
    try:
        pg.goto(a.url, wait_until="domcontentloaded", timeout=90000)
    except Exception as e:
        print("goto失敗:", str(e)[:150])
    time.sleep(4)
    if not guard_login(pg):
        _finish(out, [], pg, b, pw)
        sys.exit(4)
    for i in range(a.shots):
        path = os.path.join(out, f"f{i:03d}.png")
        try:
            pg.screenshot(path=path)
        except Exception as e:
            print(f"f{i:03d} 失敗:", str(e)[:100])
        time.sleep(a.every)
    _finish(out, [], pg, b, pw)
    print(f"ok コマ撮り{a.shots}枚 -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe", "ls", "shots"])
    ap.add_argument("--url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--seconds", type=int, default=25, help="probe: 通信を拾い続ける秒数")
    ap.add_argument("--shots", type=int, default=10)
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--shot", action="store_true", help="probe: 最後に1枚撮る")
    a = ap.parse_args()
    if a.cmd in ("probe", "shots") and not a.url:
        sys.exit("error --url が要る")
    {"probe": cmd_probe, "ls": cmd_ls, "shots": cmd_shots}[a.cmd](a)


if __name__ == "__main__":
    main()
