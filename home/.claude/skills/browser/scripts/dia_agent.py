#!/usr/bin/env python3
"""dia_agent — 本人のDiaを一切触らずに、同じDiaの実体を別プロファイルで裏に立てる。

なぜ別インスタンスか（2026-08-22）:
  従来は本人のDiaを --remote-debugging-port 付きで起動し直していた。
  タブが一瞬消えるので本人に断る必要があり、タブも1枚しか使えず、本人の作業と競合する。
  Diaは中身がChromium（ArcCore/Blink、標準の --user-data-dir）なので、
  **同じ実体を別プロファイルでもう1つ起動できる**。本人の画面には出ない。

なぜPlaywright同梱のChromiumを使わないか:
  PlaywrightのChromiumはTLSフィンガープリント(JA3)が実在するどのChromeとも一致せず、
  JavaScriptが動く前に落とされる。Diaの実体なら本物のChromeとして通る。

なぜ headless を使わないか:
  headless は UA に "HeadlessChrome" が出るうえ検出対象。
  画面外の座標に普通のウィンドウを置く方が、本人の目に入らず、かつ検出されにくい。

  start   立てる（既に動いていれば再利用）
  stop    落とす ← 作業が終わったら必ず呼ぶ
  status  状態
  login   画面に出して人がログインする（1回だけ）
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

DIA = "/Applications/Dia.app/Contents/MacOS/Dia"
PROFILE = os.path.expanduser("~/.claude/browser-profiles/dia-agent")
PORT = int(os.environ.get("DIA_AGENT_PORT", "9333"))
PIDFILE = os.path.join(PROFILE, ".agent.pid")
OFFSCREEN = ["--window-position=-32000,-32000", "--window-size=1440,900"]

COMMON = [
    "--no-first-run", "--no-default-browser-check", "--disable-sync",
    "--disable-features=Translate,MediaRouter",
    "--disable-background-networking",
    # 画面外の窓でもページを「見えている」扱いにする（隠れていると描かないサイトがある。2026-09-27 Brandsearch）
    "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    "--mute-audio",   # 裏の窓から音を出さない（2026-09-27 本人）
]


def cdp(path="/json/version", timeout=2):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def alive():
    return cdp() is not None


def _launch(visible):
    os.makedirs(PROFILE, exist_ok=True)
    args = [DIA, f"--user-data-dir={PROFILE}", f"--remote-debugging-port={PORT}"] + COMMON
    # 工程1の月間訪問数は Similarweb 拡張で測る決まり。本人の Chrome から写した拡張を読み込む（2026-10-05。ストアは Dia に入れられない）
    ext = os.path.expanduser("~/.claude/browser-profiles/extensions/similarweb")
    if os.path.isfile(os.path.join(ext, "manifest.json")):
        args += [f"--load-extension={ext}", f"--disable-extensions-except={ext}"]
    args += [] if visible else OFFSCREEN
    log = open(os.path.join(PROFILE, "launch.log"), "ab")
    p = subprocess.Popen(args, stdout=log, stderr=log, start_new_session=True)
    with open(PIDFILE, "w") as f:
        f.write(str(p.pid))
    return p.pid


USER_PORT = 9222
PROXY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cdp_proxy.py")


def user_dia_pids():
    """本人の Dia（裏用プロファイルではない Dia）の pid。"""
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    pids = []
    for ln in out.splitlines():
        pid, _, cmd = ln.strip().partition(" ")
        if cmd.startswith(DIA) and "--type=" not in cmd and f"user-data-dir={PROFILE}" not in cmd:
            pids.append(int(pid))
    return pids


def user_cdp():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{USER_PORT}/json/version", timeout=2) as r:
            return json.load(r)
    except Exception:
        return None


def start(visible=False):
    # 本人の Dia が開いている間は、2つ目の Dia を絶対に立てない（本人 2026-10-07「dia 使ってたら消える」）。
    # 同じアプリを2つ動かすと、立てた・止めた拍子に本人の Dia が落ちていた（09:05・09:14 の2回とも裏用の起動と同じ時刻）。
    # 代わりに、本人の Dia の 9222 を 9333 に中継して、裏のタブだけで作業する。
    if not visible and user_dia_pids():
        if alive():
            print(f"ok reuse port={PORT} (本人の Dia に中継中)")
            return 0
        if not user_cdp():
            print("error 本人の Dia が開いているがデバッグポート 9222 が無い。本人の Dia は閉じない。"
                  "本人に `open -a Dia --args --remote-debugging-port=9222` で開き直してもらう", file=sys.stderr)
            return 3
        log = open(os.path.join(PROFILE, "launch.log"), "ab")
        p = subprocess.Popen([sys.executable, PROXY, str(PORT), str(USER_PORT)], stdout=log, stderr=log, start_new_session=True)
        with open(PIDFILE, "w") as f:
            f.write(f"proxy:{p.pid}")
        for _ in range(20):
            if alive():
                print(f"ok proxied port={PORT} -> 本人の Dia {USER_PORT}（2つ目の Dia は立てていない。Similarweb 拡張は使えない）")
                return 0
            time.sleep(0.25)
        print("error 中継が立たなかった", file=sys.stderr)
        return 3
    if alive():
        v = cdp()
        print(f"ok reuse port={PORT} browser={v.get('Browser')}")
        return 0
    if not os.path.exists(DIA):
        print("error Dia が見つからない: " + DIA, file=sys.stderr)
        return 3
    pid = _launch(visible)
    for _ in range(40):
        if alive():
            v = cdp()
            print(f"ok started pid={pid} port={PORT} browser={v.get('Browser')} "
                  f"visible={visible} profile={PROFILE}")
            return 0
        time.sleep(0.5)
    print(f"error CDPが20秒で応答しなかった。{PROFILE}/launch.log を見る", file=sys.stderr)
    return 3


def stop():
    killed = []
    try:
        with open(PIDFILE) as f:
            raw = f.read().strip()
        if raw.startswith("proxy:"):  # 中継だけ止める。本人の Dia には触らない
            try:
                os.kill(int(raw[6:]), signal.SIGTERM)
            except ProcessLookupError:
                pass
            os.remove(PIDFILE)
            print("ok stopped (中継だけ。本人の Dia はそのまま)")
            return 0
        killed.append(int(raw))
    except Exception:
        pass
    killed = [k for k in killed if k not in user_dia_pids()]  # 念のため本人の Dia は殺さない
    out = subprocess.run(["pgrep", "-f", f"user-data-dir={PROFILE}"],
                         capture_output=True, text=True).stdout.split()
    killed += [int(x) for x in out]
    for pid in sorted(set(killed)):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(20):
        if not alive() and not subprocess.run(
                ["pgrep", "-f", f"user-data-dir={PROFILE}"],
                capture_output=True, text=True).stdout.strip():
            print("ok stopped")
            try:
                os.remove(PIDFILE)
            except OSError:
                pass
            return 0
        time.sleep(0.3)
    for pid in sorted(set(killed)):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    print("ok stopped (SIGKILL)")
    return 0


def status():
    v = cdp()
    if not v:
        print(f"stopped port={PORT} profile={PROFILE}")
        return 1
    tabs = cdp("/json/list") or []
    print(f"running port={PORT} browser={v.get('Browser')} tabs={len(tabs)}")
    for t in tabs[:10]:
        if t.get("type") == "page":
            print(f"   - {t.get('url','')[:90]}")
    return 0


def login(url):
    """画面に出して人がログインする。1回通せば以後は裏で使える。"""
    if alive():
        stop()
        time.sleep(1)
    rc = start(visible=True)
    if rc:
        return rc
    print(f"\n画面にDiaが出ています。{url} でログインしてください。")
    print("終わったら Enter を押す。→ 落として裏用に立て直します。")
    try:
        input()
    except EOFError:
        pass
    stop()
    time.sleep(1)
    return start(visible=False)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        sys.exit(start())
    if cmd == "stop":
        sys.exit(stop())
    if cmd == "status":
        sys.exit(status())
    if cmd == "login":
        sys.exit(login(sys.argv[2] if len(sys.argv) > 2 else "https://example.com"))
    if cmd == "reset":
        stop(); shutil.rmtree(PROFILE, ignore_errors=True); print("ok profile removed"); sys.exit(0)
    print(__doc__); sys.exit(2)
