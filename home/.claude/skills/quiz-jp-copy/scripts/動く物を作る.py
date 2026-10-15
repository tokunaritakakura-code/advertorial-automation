#!/usr/bin/env python3
r"""参考で動画（GIF に見えるループ）だった場所を、うちの止まった絵から「中身が動く」動画にする（D6）。
止まった絵をゆっくり寄せる mp4（zoompan）は使わない。動きの検査.py が「寄せただけ」で落とす（2026-10-11 漫画の記事で27本中18本落ちた）。

使い方:
  python3 動く物を作る.py <img のフォルダ> <参考の動画のフォルダ> <作業フォルダ> --指示 <動きの指示.json> [--段 広げる,投げる,戻す] [--使う秒 066:1.7]
    img のフォルダ   : 記事の img/。m<番号3桁>.jpg（止まった絵）があり、ここへ m<番号3桁>.mp4 を書く
    参考の動画のフォルダ: 参考の <番号3桁>.mp4（長さを合わせる。参考を落とした時の番号）
    作業フォルダ     : in/（広げた絵）・out/（Kling の出来上がり）・box.json・jobs.json（払った生成の番号の控え）を置く
    動きの指示.json  : {"017": "the man pulls the woman closer, bokeh lights twinkle ...", ...}
                       参考の動画を見て、面ごとに「何がどう動くか」を英語で1〜2文。カメラと文字の決まりは道具が頭に足す
段:
  広げる: 絵を Kling が受ける縦横（9:16・1:1・16:9）に、端をぼかして広げる（box.json に戻す位置）
  投げる: higgsfield の kling3_0_turbo（1080p・5秒・一番安い）に同時6本まで。出来上がりがあれば飛ばす。
          控えに番号がある物は作り直さず待つ所から（落ちて回し直しても2回払わない）
  戻す  : 広げた分を切り、絵と同じ幅にして、参考と同じ長さにする（5秒より長い参考は行って戻る）
既定は3段とも。出来上がりは1本ずつ3コマ見て、途中から物が湧く・字や商品の形が崩れる動画は --使う秒 で崩れる前まで。
湧き方がひどい物は out/<番号>.mp4 と jobs.json のその番号を消し、指示を直して投げ直す。
終わったら python3 ~/Claude\ Code/ec-harness/動きの検査.py <index.html> <参考の動画...> --見比べ 見比べ_動き.jpg が 0 になるのを確かめる。
実写の面（人が商品を使う・話す）は、先に同じ商品を売る店の動画を探す（05 記事を作る.md 手順7）。使える物が無い面だけこの道具で作る。
終了コード: 0 全部できた / 1 できない番号がある（理由を1行ずつ出す） / 2 道具が無い（higgsfield・ffmpeg）
"""
import argparse, json, os, shutil, subprocess, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageFilter

HEAD = ("Static locked-off camera, no zoom, no pan. All text, logos and speech bubbles stay exactly unchanged, sharp and still. "
        "The product keeps exactly the same shape, seams and color as in the image, with no added tags or labels. ")
LOCK = threading.Lock()


def sh(cmd, timeout=900):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        print(f"道具が無い: {cmd[0]}", file=sys.stderr); os._exit(2)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timeout")


def dur(f):
    if not os.path.exists(f): return 0.0
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f], 60)
    try: return float(r.stdout.strip())
    except ValueError: return 0.0


def widen(img, work, nums):
    os.makedirs(f"{work}/in", exist_ok=True)
    bp = f"{work}/box.json"; box = json.load(open(bp)) if os.path.exists(bp) else {}
    for n in nums:
        im = Image.open(f"{img}/m{n}.jpg").convert("RGB"); W, H = im.size; q = H / W
        ar, t = ("9:16", 16 / 9) if q > 1.2 else (("1:1", 1.0) if q > 0.85 else ("16:9", 9 / 16))
        CW, CH = (W, round(W * t)) if q < t else (round(H / t), H)
        bg = im.resize((CW, CH)).filter(ImageFilter.GaussianBlur(40))
        x, y = (CW - W) // 2, (CH - H) // 2
        bg.paste(im, (x, y)); bg.save(f"{work}/in/{n}.png")
        box[n] = {"ar": ar, "box": [x / CW, y / CH, W / CW, H / CH], "w": W, "h": H}
    json.dump(box, open(bp, "w"), indent=1)
    print("広げた", len(nums))


def note(work, n, jid):
    """払った生成の番号を控える（原子的に保存）"""
    with LOCK:
        p = f"{work}/jobs.json"; d = json.load(open(p)) if os.path.exists(p) else {}
        if not isinstance(d, dict): d = {}
        d[n] = jid; tmp = p + ".tmp"; json.dump(d, open(tmp, "w"), indent=1); os.replace(tmp, p)


def one(work, n, ar, prompt):
    out = f"{work}/out/{n}.mp4"
    if dur(out) > 0.5: return n, "skip"
    p = f"{work}/jobs.json"; d = json.load(open(p)) if os.path.exists(p) else {}
    jid = d.get(n) if isinstance(d, dict) else None
    if not jid:
        args = ["higgsfield", "generate", "create", "kling3_0_turbo", "--duration", "5", "--resolution", "1080p",
                "--prompt", HEAD + prompt, "--start-image", f"{work}/in/{n}.png", "--aspect-ratio", ar, "--json"]
        for a in range(5):
            r = sh(args, 300)
            try:
                jid = json.loads(r.stdout)[0]; break
            except Exception:
                if r.returncode == 0:   # 通って払った可能性がある。作り直さずに止める
                    return n, f"create の返事が読めない（払っているかもしれない）: {(r.stdout + r.stderr)[-200:]}"
                print(f"{n}: create 失敗 {a + 1}回目 {r.stderr.strip()[-160:]}", file=sys.stderr)
                time.sleep(15 + a * 15)
        if not jid: return n, "create_failed"
        note(work, n, jid)
    url, last = None, ""
    for a in range(6):
        r = sh(["higgsfield", "generate", "wait", jid, "--json", "--timeout", "10m"], 700)
        last = (r.stdout + r.stderr)[-200:]
        try:
            info = json.loads(r.stdout); st = str(info.get("status", "")).lower(); url = info.get("result_url")
            if url: break
            if "nsfw" in st: return n, "nsfw（指示の言い回しを変えて投げ直す）"
            if st in ("failed", "canceled", "cancelled", "error"): return n, f"生成が {st}"
        except Exception: pass
        time.sleep(20 + a * 20)   # 一時的な失敗・待ちの時間切れは待ち直す（作り終わった物を捨てない）
    if not url: return n, f"出来上がりが取れない（jobs.json に {jid} を控えた。回し直すと待つ所から）: {last}"
    tmp = out + ".tmp.mp4"
    for a in range(3):
        try:
            with urllib.request.urlopen(url, timeout=300) as rs, open(tmp, "wb") as f: shutil.copyfileobj(rs, f)
            if dur(tmp) > 0.5: os.replace(tmp, out); return n, "ok"
        except Exception as e:
            print(f"{n}: 落とせない {e}", file=sys.stderr); time.sleep(5)
    return n, "download_failed"


def throw(work, nums, order):
    os.makedirs(f"{work}/out", exist_ok=True)
    box = json.load(open(f"{work}/box.json"))
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda n: one(work, n, box[n]["ar"], order[n]), nums))
    bad = [x for x in res if x[1] not in ("ok", "skip")]
    print("投げた: ok", sum(x[1] == "ok" for x in res), "/ skip", sum(x[1] == "skip" for x in res), "/ できない", len(bad))
    for n, why in bad: print(f"  × {n}: {why}")
    return not bad


def back(img, ref, work, nums, use=None):
    use = use or {}
    box = json.load(open(f"{work}/box.json")); bad = []
    for n in nums:
        src = f"{work}/out/{n}.mp4"
        if dur(src) <= 0.5: bad.append((n, "出来上がりが無い")); continue
        want = dur(f"{ref}/{n}.mp4")
        if want <= 0: bad.append((n, f"参考の長さが取れない（{ref}/{n}.mp4）")); continue
        b = box[n]; W, H = b["w"], b["h"] - b["h"] % 2
        crop = f"crop=iw*{b['box'][2]:.5f}:ih*{b['box'][3]:.5f}:iw*{b['box'][0]:.5f}:ih*{b['box'][1]:.5f},scale={W}:{H}"
        have = min(dur(src), use.get(n, 99))   # 途中から崩れる動画は、崩れる前の秒までだけ使う
        if want <= have - 0.1:
            vf = f"{crop},trim=0:{want:.2f},setpts=PTS-STARTPTS"
        else:   # 参考の方が長い時は行って戻るをくり返す（ループの切れ目を目立たせない）
            k = int(want // (2 * have)) + 1
            vf = (f"{crop},trim=0:{have:.2f},setpts=PTS-STARTPTS,split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1,"
                  f"loop={k}:{int(2 * have * 30) + 2}:0,trim=0:{want:.2f},setpts=PTS-STARTPTS")
        dst = f"{img}/m{n}.mp4"; tmp = dst + ".tmp.mp4"
        r = sh(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex", vf + ",fps=30,format=yuv420p",
                "-an", "-c:v", "h264_videotoolbox", "-b:v", "1800k", tmp])
        got = dur(tmp)
        if r.returncode or got < want - 0.25:
            bad.append((n, f"書き出せない（{got:.1f}秒 / 参考 {want:.1f}秒）{r.stderr[-160:]}"))
            if os.path.exists(tmp): os.remove(tmp)
            continue
        os.replace(tmp, dst)
    print("戻した", len(nums) - len(bad), "/", len(nums))
    for n, why in bad: print(f"  × {n}: {why}")
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("img"); ap.add_argument("ref"); ap.add_argument("work")
    ap.add_argument("--指示", required=True); ap.add_argument("--段", default="広げる,投げる,戻す")
    ap.add_argument("--使う秒", default="", help="066:1.7 のように、崩れる前の秒まで（行って戻って参考の長さにする）")
    a = ap.parse_args()
    order = {f"{int(k):03d}": v for k, v in json.load(open(a.指示)).items()}   # 記事の側は m017 の3桁で読む
    nums = sorted(order)
    use = {f"{int(k):03d}": float(v) for k, v in (x.split(":") for x in a.使う秒.split(",") if x)}
    steps = a.段.split(","); ok = True
    if "広げる" in steps: widen(a.img, a.work, nums)
    if "投げる" in steps: ok = throw(a.work, nums, order) and ok
    if "戻す" in steps: ok = back(a.img, a.ref, a.work, nums, use) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
