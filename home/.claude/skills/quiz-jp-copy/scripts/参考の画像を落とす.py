#!/usr/bin/env python3
"""参考の HTML から、画像と動画を出てくる順に落とし、画像の添付に使える png / jpg にそろえる。

使い方: python3 参考の画像を落とす.py <参考の HTML のパスか URL> <出力フォルダ>
  出力: <出力フォルダ>/<3桁の順番>.<png|jpg>（mp4・webm は ffmpeg で1コマ目、webp・avif・gif は png にする）と 一覧.tsv（順番・元の URL・段の見当に使う前後の文）
終了コード: 0=1枚以上落とせた / 1=画像が0枚（HTML に img が無い）/ 2=開けない・道具が無い
取れなかった画像は 一覧.tsv に「取れなかった: <理由>」と書く（0枚と取れなかったを分ける）。
"""
import html, os, re, shutil, subprocess, sys, time, urllib.parse, urllib.request

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


def get(url, tries=3):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:      # 落ちたら少し待って取り直す
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


def main(a):
    if len(a) < 2:
        print(__doc__); return 2
    src, out = a[0], os.path.expanduser(a[1])
    if not shutil.which("ffmpeg"):
        print("道具が無い: ffmpeg（brew install ffmpeg）", file=sys.stderr); return 2
    try:
        if src.startswith("http"):
            page, base = get(src).decode("utf-8", "ignore"), src
        else:
            page, base = open(os.path.expanduser(src), encoding="utf-8", errors="ignore").read(), None
    except Exception as e:
        print(f"開けない: {e}", file=sys.stderr); return 2
    os.makedirs(out, exist_ok=True)
    # img の src / data-src / srcset の1つ目、video / source の src を、HTML に出てくる順に
    pat = re.compile(r'(?is)<(img|source|video)\b[^>]*?\b(?:data-src|src|srcset)="([^"]+)"')
    urls = []
    for m in pat.finditer(page):
        u = html.unescape(m.group(2).split(",")[0].split(" ")[0])
        if u.startswith("data:") or not u:
            continue
        if base:
            u = urllib.parse.urljoin(base, u)
        elif not u.startswith("http"):
            u = os.path.join(os.path.dirname(os.path.abspath(os.path.expanduser(src))), u)
        ctx = re.sub(r"(?s)<[^>]+>", " ", page[max(0, m.start() - 300):m.start()])
        urls.append((u, re.sub(r"\s+", " ", html.unescape(ctx)).strip()[-60:]))
    if not urls:
        print("画像が0枚（HTML に img・video が無い）"); return 1
    rows, ok = [], 0
    for i, (u, ctx) in enumerate(urls, 1):
        name = f"{i:03d}"
        ext = os.path.splitext(urllib.parse.urlparse(u).path)[1].lower()
        try:
            raw = get(u) if u.startswith("http") else open(u, "rb").read()
            tmp = os.path.join(out, f"{name}.src{ext or '.bin'}")
            with open(tmp, "wb") as f:
                f.write(raw)
            if ext in (".jpg", ".jpeg", ".png"):
                final = os.path.join(out, name + (".png" if ext == ".png" else ".jpg"))
                os.replace(tmp, final)
            else:
                final = os.path.join(out, name + ".png")
                args = ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp]
                if ext in (".mp4", ".webm", ".mov", ".gif"):
                    args += ["-frames:v", "1"]
                r = subprocess.run(args + [final], capture_output=True, text=True, timeout=60)
                os.remove(tmp)
                if r.returncode != 0:
                    raise RuntimeError(f"変換できない（{ext}）: {r.stderr.strip()[:80]}")
            rows.append(f"{name}\t{u}\t{ctx}")
            ok += 1
        except Exception as e:
            rows.append(f"{name}\t{u}\t取れなかった: {type(e).__name__}: {str(e)[:80]}")
    with open(os.path.join(out, "一覧.tsv"), "w") as f:
        f.write("順番\t元のURL\t前の文（段の見当）\n" + "\n".join(rows) + "\n")
    print(f"{len(urls)}個のうち {ok}枚を落とした → {out}（取れなかった {len(urls) - ok}個は 一覧.tsv）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
