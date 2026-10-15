#!/usr/bin/env python3
"""frames.py <video> <outdir> [--max 150] [--interval 45] [--jobs 8] [--dedupe 4] [--times-only]
場面転換(ffmpeg scene score)+一定間隔サンプリングでキーフレームを抽出する。
- 適応的: scene閾値は0.22から始め、多すぎたらスコア上位を残す
- 間隔フロア: 話が静かでも --interval 秒ごとに1枚は取る(スライド長映し対策)
- 最小ギャップ2秒でdedupe、--max枚に収める、768px幅に縮小
- 抽出は --jobs 並列(2026-08-27実測: 60枚 1.71s → 0.46s)
- 画の重複は dHash で落とす(2026-08-27実測: 固定15秒刻みで33%が直前とほぼ同一。
  読ませる画像が減る = トークンと注意の節約。--dedupe 0 で無効)
出力: <outdir>/f_<秒6桁>.jpg を書き、stdoutに「秒\tパス」のTSVを出す。
--times-only: 抽出せず選んだ秒だけを1行1件でstdoutに出す(yt-grabに高解像度で撮らせる時に使う)。"""
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

SHOWINFO = re.compile(r"pts_time:(\d+\.?\d*)")
SCENE = re.compile(r"lavfi\.scene_score=(\d+\.?\d*)")


def opt(name, default, cast=int):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def duration_of(video: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def scene_times(video: str, thresh: float = 0.22):
    """(秒, sceneスコア) のリスト。ffmpegはデコードのみで速い。
    (縮小してからscene判定する案は2026-08-27に実測して却下: 360pでは scale の方が高くつく)"""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", video,
         "-vf", f"select='gt(scene,{thresh})',metadata=print",
         "-f", "null", "-"],
        capture_output=True, text=True)
    times = []
    cur_t = None
    for line in proc.stderr.splitlines() + proc.stdout.splitlines():
        mt = SHOWINFO.search(line)
        if mt:
            cur_t = float(mt.group(1))
        ms = SCENE.search(line)
        if ms and cur_t is not None:
            times.append((cur_t, float(ms.group(1))))
            cur_t = None
    return times


def dhash(path: str) -> int:
    """9x8グレースケールに潰して隣接ピクセルの大小で64bit。ffmpegだけで計算できる。"""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf", "scale=9:8,format=gray",
         "-f", "rawvideo", "-"], capture_output=True).stdout
    if len(raw) < 72:
        return -1
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if raw[row * 9 + col] < raw[row * 9 + col + 1] else 0)
    return bits


def main() -> None:
    video, outdir = sys.argv[1], sys.argv[2]
    max_frames = opt("--max", 150)
    interval = opt("--interval", 45)
    jobs = opt("--jobs", 8)
    dedupe = opt("--dedupe", 4)  # ハミング距離。0で無効
    times_only = "--times-only" in sys.argv
    if not times_only:
        os.makedirs(outdir, exist_ok=True)

    dur = duration_of(video)
    scenes = scene_times(video)

    # 候補 = 冒頭 + 場面転換 + 間隔フロア
    cand = {0.5: 1.0}
    for t, score in scenes:
        cand[t] = max(cand.get(t, 0), score)
    t = float(interval)
    while t < dur:
        cand.setdefault(t, 0.05)  # 間隔フロアは低スコア扱い(間引き時に先に消える)
        t += interval

    # 最小ギャップ2秒: 時刻順に走査し、近接は高スコア側を残す
    picked = []
    for t in sorted(cand):
        if picked and t - picked[-1][0] < 2.0:
            if cand[t] > picked[-1][1]:
                picked[-1] = (t, cand[t])
        else:
            picked.append((t, cand[t]))

    # 上限: スコア上位max枚を残して時刻順に戻す
    if len(picked) > max_frames:
        picked = sorted(sorted(picked, key=lambda x: -x[1])[:max_frames])

    if times_only:
        for t, _ in picked:
            print(f"{t:.1f}")
        return

    def grab(t):
        path = os.path.join(outdir, f"f_{int(t):06d}.jpg")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(t),
             "-i", video, "-frames:v", "1", "-vf", "scale=768:-2", "-q:v", "4",
             "-y", path], check=True)
        return (t, path)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        rows = sorted(ex.map(grab, [t for t, _ in picked]))

    # 画が動いていないコマを捨てる(直前の採用コマとの距離で判定)
    kept, dropped, prev = [], 0, None
    for t, path in rows:
        if dedupe > 0:
            h = dhash(path)
            if prev is not None and h >= 0 and bin(h ^ prev).count("1") <= dedupe:
                os.remove(path)
                dropped += 1
                continue
            if h >= 0:
                prev = h
        kept.append((t, path))

    for t, path in kept:
        print(f"{t:.1f}\t{path}")
    if dropped:
        print(f"dedupe: {dropped}枚を重複として破棄 (残り{len(kept)}枚)", file=sys.stderr)


if __name__ == "__main__":
    main()
