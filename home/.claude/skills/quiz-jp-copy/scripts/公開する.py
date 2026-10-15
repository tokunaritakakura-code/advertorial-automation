#!/usr/bin/env python3
"""通った記事・飛び先を、人の承認なしで Vercel に上げてリンクで見られるようにする（2026-10-10 本人「OKだったら vercel に勝手にあげていい。全自動」）。

使い方: python3 公開する.py <記事のフォルダ> [--名前 <英数字とハイフンの短い名前>] [--店 <店のURL>]
上げる前に、このフォルダの物が通っているかを機械で確かめる（どれか1つでも落ちたら上げない）:
  1 型の検査.py が終了コード0（--店 を付けた時はその値でも見る）
  2 幅の検査.py --押す 3 が終了コード0（アンケートが無いページは --押す を付けずに見る）
  3 最終確認.md があり、理由の無い × の行が0
上げ先: Vercel（ログイン中のアカウント）。プロジェクト名は --名前（無ければフォルダ名から作る）。noindex はページのまま残す。
上げた URL は <フォルダ>/公開URL.txt に書く。Shopify の店には上げない（店は別）。
終了コード: 0=上げた / 1=検査で落ちたので上げていない / 2=道具が無い・上げられなかった
"""
import os, re, subprocess, sys, time

SK = os.path.expanduser("~/.claude/skills")


def run(cmd, cwd=None, timeout=600):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return 124, f"時間切れ: {' '.join(cmd[:3])}"
    except FileNotFoundError as e:
        return 127, f"道具が無い: {e}"


def main(a):
    if not a:
        print(__doc__); return 2
    d = os.path.abspath(os.path.expanduser(a[0]))
    html = os.path.join(d, "index.html")
    if not os.path.exists(html):
        print(f"index.html が無い: {d}", file=sys.stderr); return 2
    name = a[a.index("--名前") + 1] if "--名前" in a else re.sub(r"[^a-z0-9-]+", "-", os.path.basename(d).lower()).strip("-") or f"kiji-{int(time.time())}"
    shop = a[a.index("--店") + 1] if "--店" in a else None

    src = open(html, encoding="utf-8").read()
    # 型の検査はアンケート3〜5問の型の物。問いが6問以上（長い診断）の時は当てない（2026-10-10 7問の診断で落ちて手で上げた）
    nq = len(set(re.findall(r'data-q="(\d+)"', src)))
    checks = [["python3", f"{SK}/quiz-jp-copy/scripts/型の検査.py", html] + (["--店", shop] if shop else [])] if 1 <= nq <= 5 else []
    checks.append(["python3", f"{SK}/kata-tsukuru/scripts/幅の検査.py", html] + (["--押す", str(max(3, nq))] if "data-answer" in src else []))
    for c in checks:
        code, out = run(c)
        if code != 0:
            print(f"上げない: {os.path.basename(c[1])} が終了コード{code}\n" + "\n".join(out.strip().splitlines()[-6:]))
            return 1 if code == 1 else 2
    fin = os.path.join(d, "最終確認.md")
    if not os.path.exists(fin):
        print("上げない: 最終確認.md が無い"); return 1
    bare = [l for l in open(fin, encoding="utf-8") if re.search(r"(^|\|)\s*×\s*(\||$)", l)]
    if bare:
        print(f"上げない: 最終確認.md に理由の無い × が {len(bare)}行（例: {bare[0].strip()[:60]}）"); return 1

    # 上げるのはページと画像だけ。作業用・参考の物・書類は上げない（2026-10-11 作業用 844MB まで上げようとして時間切れ）
    ig = os.path.join(d, ".vercelignore")
    if not os.path.exists(ig):
        with open(ig, "w") as f:
            f.write("作業/\n参考/\n参考の画像/\n参考の動画/\n動く素材/\n実写の素材/\n生成/\n*.bak*\n*.md\n*.py\n*.json\n!vercel.json\n*.mp4\n*.mov\n!img/**/*.mp4\n!申込/**/*.mp4\n")  # ページの動画（img/・申込/）は上げる。素材の動画は上げない（2026-10-11 ここちドライ暴露型で動画が全部404）
    code, out = run(["vercel", "whoami"], timeout=30)
    if code != 0:
        print(f"Vercel にログインしていない: {out.strip()[:120]}", file=sys.stderr); return 2
    code, out = run(["vercel", "link", "--yes", "--project", name], cwd=d, timeout=120)
    if code != 0:
        print(f"Vercel のプロジェクトを作れない: {out.strip()[-200:]}", file=sys.stderr); return 2
    code, out = run(["vercel", "deploy", "--prod", "--yes"], cwd=d, timeout=900)
    urls = re.findall(r"https://[^\s]+\.vercel\.app", out)
    if code != 0 or not urls:
        print(f"上げられなかった（終了コード{code}）: {out.strip()[-300:]}", file=sys.stderr); return 2
    alias = [u for u in urls if name in u]
    url = (alias or urls)[-1]
    with open(os.path.join(d, "公開URL.txt"), "w") as f:
        f.write(f"{url}\n{time.strftime('%Y-%m-%d %H:%M')} 上げた（検査 {len(checks)}本・最終確認 通過）\n")
    print(f"上げた: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
