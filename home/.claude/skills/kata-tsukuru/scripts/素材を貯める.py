#!/usr/bin/env python3
"""記事の素材庫（動く素材・写真）に、取った物を入れる・探す・使った記事を書く（2026-10-11 本人「誰のパソコンでも同じ形で溜まるように」）。

素材庫の場所: --根 <フォルダ> か、環境変数 KIJI_SOZAI。どちらも無ければ ~/Desktop/ec/共通/記事の素材庫（~/Desktop/ec が無いパソコンでは ~/記事の素材庫）。無ければ作る。
中の形（README.md にも書く）:
  <悩み>/01 商品が写る/<商品の種類>/0001_<中身>.mp4 ＋ 同じ名前の .json（札）
  <悩み>/02 人の反応/ ・ 03 体の中/ ・ 04 写真/ は商品の種類で分けない（同じ悩みなら別の商品でも使える）

使い方:
  入れる <ファイル> --悩み 尿もれ --種類 商品が写る|人の反応|体の中|写真 --中身 "はいて帯を伸ばす手元"
         [--商品の種類 吸水ショーツ（商品が写る時は必須）] [--同じ商品 ここちドライ] [--出どころ <URL>] [--店 <名前>]
         [--秒 3.0-6.5（その区間だけ切って入れる）] [--印 "右下にロゴ・切り取り済み"] [--使った記事 <記事のフォルダ名>]
  探す [語...] [--悩み 尿もれ] [--種類 体の中] [--商品の種類 吸水ショーツ] [--同じ商品 ここちドライ]   語は札の中身・ファイル名に全部含まれる物
  使った <番号> --悩み 尿もれ --記事 <記事のフォルダ名>
終了コード: 0 できた・見つかった / 1 見つからない / 2 入力の誤り・ファイルが無い
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
from datetime import date

種類 = {"商品が写る": "01 商品が写る", "人の反応": "02 人の反応", "体の中": "03 体の中", "写真": "04 写真"}
README = """# 記事の素材庫

読む人: 記事を作る人と Claude。読む時: 記事の動く素材・写真を探す時と、取った物を入れる時。
読まなくていい条件: 道具 `素材を貯める.py` で入れる・探すだけの時（この形は道具が守る）。

- いちばん上は悩み（商品名にしない）。人の反応・体の中は、同じ悩みなら別の商品でも使えるので商品で分けない
- `01 商品が写る/` だけ、その下を商品の種類（ブランド名にしない）で分ける。形が本物と同じ物しか使えないため
- ファイル名は `4桁の番号_中身を短く`。番号は悩みのフォルダの中で通し。店・ブランド・日付・出どころは名前に入れず札に書く
- 1つの素材に札（同じ名前の .json）を1枚。一覧のファイルは作らない（書き込みがぶつからないように）
- 置くのは使う所だけ切った物。元の URL と秒は札に書く（取り直す時は札から戻る）
- 入れる・探す: `python3 <kata-tsukuru>/scripts/素材を貯める.py 入れる|探す|使った ...`
"""


def 根(a):
    r = a or os.environ.get("KIJI_SOZAI")
    if not r:
        ec = os.path.expanduser("~/Desktop/ec")
        r = os.path.join(ec, "共通", "記事の素材庫") if os.path.isdir(ec) else os.path.expanduser("~/記事の素材庫")
    os.makedirs(r, exist_ok=True)
    rd = os.path.join(r, "README.md")
    if not os.path.exists(rd):
        open(rd, "w", encoding="utf-8").write(README)
    return r


def 安全(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "", s).strip("_")[:40]


def 札を全部(r, 悩み=None):
    for d, _, fs in os.walk(os.path.join(r, 悩み) if 悩み else r):
        for f in fs:
            if f.endswith(".json"):
                p = os.path.join(d, f)
                try:
                    yield p, json.load(open(p, encoding="utf-8"))
                except Exception:
                    continue


def 次の番号(r, 悩み):
    n = 0
    for p, _ in 札を全部(r, 悩み):
        m = re.match(r"(\d{4})_", os.path.basename(p))
        if m:
            n = max(n, int(m.group(1)))
    return n + 1


def 測る(f):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "json", f],
                             capture_output=True, text=True, timeout=60).stdout
        j = json.loads(out or "{}")
        st = (j.get("streams") or [{}])[0]
        return {"秒": round(float(j.get("format", {}).get("duration", 0) or 0), 2), "幅": st.get("width"), "高さ": st.get("height")}
    except Exception:
        return {}


def 入れる(a):
    if not os.path.exists(a.ファイル):
        print(f"無い: {a.ファイル}"); return 2
    if a.種類 == "商品が写る" and not a.商品の種類:
        print("商品が写る物は --商品の種類 が要る（例: 吸水ショーツ）"); return 2
    r = 根(a.根)
    d = os.path.join(r, 安全(a.悩み), 種類[a.種類])
    if a.種類 == "商品が写る":
        d = os.path.join(d, 安全(a.商品の種類))
    os.makedirs(d, exist_ok=True)
    n = 次の番号(r, 安全(a.悩み))
    ext = os.path.splitext(a.ファイル)[1].lower() or ".mp4"
    名 = f"{n:04d}_{安全(a.中身)}"
    dst = os.path.join(d, 名 + ext)
    区間 = None
    if a.秒:
        m = re.match(r"^\s*([\d.]+)\s*-\s*([\d.]+)\s*$", a.秒)
        if not m:
            print("--秒 は 3.0-6.5 の形"); return 2
        区間 = (float(m.group(1)), float(m.group(2)))
    tmp = dst + ".part"
    if 区間 and ext in (".mp4", ".mov", ".webm", ".gif"):
        outext = ".mp4"
        dst = os.path.join(d, 名 + outext); tmp = dst + ".part"
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(区間[0]), "-to", str(区間[1]), "-i", a.ファイル, "-an",
               "-c:v", "h264_videotoolbox", "-b:v", "6M", "-f", "mp4", tmp]
        r1 = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r1.returncode != 0:  # 専用チップが無いパソコン
            cmd[cmd.index("h264_videotoolbox")] = "libx264"
            r1 = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r1.returncode != 0:
            print("切れなかった:", r1.stderr[-300:]); return 2
    else:
        shutil.copyfile(a.ファイル, tmp)
    os.replace(tmp, dst)
    札 = {"番号": n, "ファイル": os.path.basename(dst), "種類": a.種類, "悩み": a.悩み, "商品の種類": a.商品の種類 or "",
          "同じ商品": a.同じ商品 or "", "中身": a.中身, "出どころ": a.出どころ or "", "店": a.店 or "",
          "元の秒": a.秒 or "", "他社の印": a.印 or "", "使った記事": [a.使った記事] if a.使った記事 else [],
          "入れた日": date.today().isoformat(), **測る(dst)}
    p = os.path.join(d, os.path.splitext(os.path.basename(dst))[0] + ".json")
    with open(p + ".part", "w", encoding="utf-8") as f:
        json.dump(札, f, ensure_ascii=False, indent=1)
    os.replace(p + ".part", p)
    print(f"入れた: {os.path.relpath(dst, r)}（番号 {n}）")
    return 0


def 探す(a):
    r = 根(a.根)
    hit = []
    for p, j in 札を全部(r, 安全(a.悩み) if a.悩み else None):
        if a.種類 and j.get("種類") != a.種類: continue
        if a.商品の種類 and j.get("商品の種類") != a.商品の種類: continue
        if a.同じ商品 and j.get("同じ商品") != a.同じ商品: continue
        text = " ".join(str(v) for v in j.values()) + " " + os.path.basename(p)
        if all(w in text for w in a.語):
            hit.append((p, j))
    for p, j in sorted(hit, key=lambda x: x[0]):
        使 = "・".join(j.get("使った記事") or []) or "まだ"
        print(f"{j.get('悩み')}/{j.get('種類')} {j.get('番号'):04d} {j.get('中身')}  {j.get('秒','')}秒 {j.get('幅','')}×{j.get('高さ','')}  同じ商品:{j.get('同じ商品') or '-'}  使った:{使}\n   {os.path.join(os.path.dirname(p), j.get('ファイル',''))}")
    print(f"{len(hit)}件（{r}）")
    return 0 if hit else 1


def 使った(a):
    r = 根(a.根)
    for p, j in 札を全部(r, 安全(a.悩み)):
        if j.get("番号") == a.番号:
            j.setdefault("使った記事", [])
            if a.記事 not in j["使った記事"]:
                j["使った記事"].append(a.記事)
            with open(p + ".part", "w", encoding="utf-8") as f:
                json.dump(j, f, ensure_ascii=False, indent=1)
            os.replace(p + ".part", p)
            print(f"書いた: {j['番号']:04d} {j['中身']} ← {a.記事}"); return 0
    print("その番号が無い"); return 1


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("命令", choices=["入れる", "探す", "使った"])
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--根"); ap.add_argument("--悩み"); ap.add_argument("--種類", choices=list(種類))
    ap.add_argument("--中身"); ap.add_argument("--商品の種類"); ap.add_argument("--同じ商品"); ap.add_argument("--出どころ")
    ap.add_argument("--店"); ap.add_argument("--秒"); ap.add_argument("--印"); ap.add_argument("--使った記事"); ap.add_argument("--記事")
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); return 2
    a = ap.parse_args()
    if a.命令 == "入れる":
        if len(a.rest) != 1 or not (a.悩み and a.種類 and a.中身):
            print("入れる <ファイル> --悩み --種類 --中身 が要る"); return 2
        a.ファイル = a.rest[0]; return 入れる(a)
    if a.命令 == "探す":
        a.語 = a.rest; return 探す(a)
    if not (a.rest and a.悩み and a.記事):
        print("使った <番号> --悩み --記事 が要る"); return 2
    a.番号 = int(a.rest[0]); return 使った(a)


if __name__ == "__main__":
    sys.exit(main())
