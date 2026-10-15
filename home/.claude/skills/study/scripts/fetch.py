#!/usr/bin/env python3
"""教材を1本、生テキストに落とす。Claudeはこの出力を読まない。

出力:
  <out>/<slug>.txt       [mm:ss] 付きの本文（文書系はタイムスタンプ無し）
  <out>/<slug>.meta.json 種別・出所・長さ・取得方法・失敗理由

使い方:
  fetch.py <入力> --out DIR [--slug NAME] [--lang ja|en|auto] [--model PATH]

入力は以下のどれか:
  YouTubeのURL / 通常のWebページURL / ローカルの動画・音声 / PDF / txt・md
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

WHISPER_MODEL_DEFAULT = os.path.expanduser("~/.cache/whisper/ggml-large-v3-turbo.bin")
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
DOC_EXT = {".txt", ".md", ".markdown", ".vtt", ".srt"}


def die(msg, code=2):
    print(f"FETCH_FAILED: {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd, timeout=None, check=True):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} exited {p.returncode}: {p.stderr[-800:]}")
    return p


def slugify(s):
    s = re.sub(r"https?://", "", s)
    s = re.sub(r"[^\w぀-ヿ一-鿿-]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-").lower()[:60] or "material"


# ---------- 字幕・文字起こしを [mm:ss] 行に正規化 ----------

def ts(sec):
    sec = int(sec)
    return f"[{sec // 60:02d}:{sec % 60:02d}]"


def parse_vtt(path):
    """VTTを (秒, テキスト) に。YouTubeの自動字幕にある重複行とインライン
    タイムタグを落とす。落とさないと同じ文が3回入って倍のトークンを食う。"""
    out, last = [], None
    cur_t = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        m = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)\s+-->", line)
        if m:
            h, mi, s, _ = m.groups()
            cur_t = int(h) * 3600 + int(mi) * 60 + int(s)
            continue
        if not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        txt = re.sub(r"<[^>]+>", "", line)
        txt = re.sub(r"\s+", " ", txt).strip()
        if not txt or txt == last:
            continue
        # 自動字幕は前行の末尾を次行の先頭で繰り返す
        if last and txt.startswith(last):
            txt = txt[len(last):].strip()
            if not txt:
                continue
        out.append((cur_t if cur_t is not None else 0, txt))
        last = re.sub(r"<[^>]+>", "", line).strip()
    return out


def parse_srt(path):
    out = []
    cur_t = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        m = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)\s+-->", line)
        if m:
            h, mi, s, _ = m.groups()
            cur_t = int(h) * 3600 + int(mi) * 60 + int(s)
            continue
        if not line or line.isdigit():
            continue
        out.append((cur_t or 0, line))
    return out


def write_timed(pairs, out_txt):
    lines, last_t = [], -999
    buf = []
    for t, txt in pairs:
        if t - last_t >= 15 and buf:
            lines.append(f"{ts(last_t)} " + " ".join(buf))
            buf = []
        if not buf:
            last_t = t
        buf.append(txt)
    if buf:
        lines.append(f"{ts(last_t)} " + " ".join(buf))
    open(out_txt, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return len(lines)


# ---------- 取得経路 ----------

CLIENTS = ["", "tv", "web_safari", "ios"]


def _yt_extra(client):
    return ["--extractor-args", f"youtube:player_client={client}"] if client else []


def yt_subs(url, workdir, lang):
    """YouTubeの字幕を無料で取る。手動字幕を優先し、無ければ自動字幕。

    YouTubeは 429(Too Many Requests) と 403 を返してくる。どちらも「字幕が無い」
    ではないので、待ってから別のクライアントで取り直す。ここを区別しないと
    「字幕なし」と誤判定して、要らないwhisperを1時間回すことになる。
    """
    langs = {"ja": "ja.*,ja", "en": "en.*,en"}.get(lang, "ja.*,en.*,ja,en")
    base = os.path.join(workdir, "sub")
    blocked = False
    saw_no_subs = False   # yt-dlpが明示的に「字幕が無い」と言った時だけ立てる
    other_error = None
    for attempt, client in enumerate(CLIENTS):
        for args, how in ((["--write-sub"], "手動字幕"), (["--write-auto-sub"], "自動字幕")):
            try:
                p = run(["yt-dlp", "--skip-download", *args, "--sub-lang", langs,
                         "--sub-format", "vtt", "--retries", "5", "--socket-timeout", "30",
                         "--sleep-requests", "1", *_yt_extra(client),
                         "-o", base + ".%(ext)s", url], timeout=300, check=False)
            except subprocess.TimeoutExpired:
                other_error = "yt-dlpがタイムアウト"
                continue
            err = (p.stderr or "") + (p.stdout or "")
            if re.search(r"HTTP Error (429|403)|Sign in to confirm|bot", err, re.I):
                blocked = True
            elif re.search(r"(no subtitles|There are no subtitles|"
                           r"no automatic captions|has no subtitles)", err, re.I):
                saw_no_subs = True
            elif p.returncode != 0:
                other_error = err.strip().splitlines()[-1][:200] if err.strip() else \
                    f"yt-dlp exit {p.returncode}"
            vtts = [f for f in os.listdir(workdir)
                    if f.startswith("sub") and f.endswith(".vtt")
                    and os.path.getsize(os.path.join(workdir, f)) > 300]
            if vtts:
                vtts.sort(key=lambda f: (0 if "orig" in f else 1, len(f)))
                return os.path.join(workdir, vtts[0]), how
        if blocked and attempt < len(CLIENTS) - 1:
            time.sleep(20 * (attempt + 1))
    if blocked:
        return None, "BLOCKED"
    if other_error:
        return None, "UNKNOWN_ERROR"
    if saw_no_subs:
        return None, "NO_SUBS"
    return None, "UNKNOWN_ERROR"   # 何も分からない時に「字幕なし」と断定しない


def yt_meta(url):
    try:
        p = run(["yt-dlp", "--skip-download", "--print",
                 "%(title)s\t%(duration)s\t%(uploader)s\t%(upload_date)s", url],
                timeout=90, check=False)
        parts = (p.stdout.strip().split("\n")[-1]).split("\t")
        if len(parts) >= 4:
            return {"title": parts[0], "duration_sec": parts[1],
                    "uploader": parts[2], "upload_date": parts[3]}
    except Exception:
        pass
    return {}


def yt_audio(url, workdir):
    out = os.path.join(workdir, "a.%(ext)s")
    last = ""
    for i, client in enumerate(CLIENTS):
        p = run(["yt-dlp", "-f", "bestaudio/best", "-x", "--audio-format", "mp3",
                 "--retries", "5", "--sleep-requests", "1", *_yt_extra(client),
                 "-o", out, url], timeout=1800, check=False)
        for f in os.listdir(workdir):
            if f.startswith("a.") and not f.endswith(".part") \
                    and os.path.getsize(os.path.join(workdir, f)) > 10000:
                return os.path.join(workdir, f)
        last = (p.stderr or "")[-300:]
        if re.search(r"HTTP Error (429|403)", last):
            time.sleep(20 * (i + 1))
    raise RuntimeError(
        f"YouTubeが音声を返さない（字幕もブロックされている）。"
        f"時間を置くか、動画を手元にダウンロードしてローカルファイルとして渡すこと。詳細: {last}")


def yt_video(url, workdir):
    """画面を見るための動画本体。解像度は落とす（読むのは文字とレイアウトなので480pで足りる）。
    失敗しても教材の取り込み自体は止めない（呼び出し側で握りつぶす）。"""
    out = os.path.join(workdir, "v.%(ext)s")
    last = ""
    for i, client in enumerate(CLIENTS):
        p = run(["yt-dlp", "-f", "bv*[height<=480]+ba/b[height<=480]/b",
                 "--merge-output-format", "mp4", "--retries", "5",
                 "--sleep-requests", "1", *_yt_extra(client),
                 "-o", out, url], timeout=3600, check=False)
        for f in os.listdir(workdir):
            if f.startswith("v.") and not f.endswith(".part") \
                    and os.path.getsize(os.path.join(workdir, f)) > 100000:
                return os.path.join(workdir, f)
        last = (p.stderr or "")[-300:]
        if re.search(r"HTTP Error (429|403)", last):
            time.sleep(20 * (i + 1))
    raise RuntimeError(f"動画本体を落とせなかった: {last}")


def to_wav16(src, workdir):
    wav = os.path.join(workdir, "audio16.wav")
    run(["ffmpeg", "-y", "-i", src, "-vn", "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", wav, "-loglevel", "error"], timeout=3600)
    if not os.path.exists(wav) or os.path.getsize(wav) < 1000:
        raise RuntimeError("音声トラックが空。動画に音が入っていない可能性")
    return wav


def whisper(wav, workdir, lang, model):
    if not os.path.exists(model):
        die(f"whisperのモデルが無い: {model}\n"
            f"  mkdir -p ~/.cache/whisper && curl -L -o {model} "
            f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin")
    outbase = os.path.join(workdir, "w")
    cmd = ["whisper-cli", "-m", model, "-f", wav, "-osrt", "-of", outbase, "-pp"]
    if lang in ("ja", "en"):
        cmd += ["-l", lang]
    else:
        cmd += ["-l", "auto"]
    run(cmd, timeout=14400)
    srt = outbase + ".srt"
    if not os.path.exists(srt):
        raise RuntimeError("whisperがSRTを出さなかった")
    return srt


BLOCK_MARKS = re.compile(
    r"(enable javascript|are you a robot|verify you are human|access denied|"
    r"403 forbidden|404 not found|cloudflare|captcha|sign in to continue|"
    r"log in to continue|subscribe to (read|continue)|paywall|"
    r"ログインしてください|アクセスできません|お探しのページ)", re.I)


def fetch_html(url, workdir):
    """r.jina.ai 経由でMarkdown化。ブラウザUAは403になるので素のUAで投げる。

    ブロックページ・ログイン要求・404は「短い本文」として普通に返ってくる。
    それを教材として学習させないため、中身を見て弾く。
    """
    req = urllib.request.Request("https://r.jina.ai/" + url,
                                 headers={"User-Agent": "curl/8"})
    last = None
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status = r.status
                body = r.read().decode("utf-8", "replace")
        except Exception as e:
            last = str(e)
            time.sleep(3 * (i + 1))
            continue
        if status != 200:
            last = f"HTTP {status}"
            time.sleep(3 * (i + 1))
            continue
        if len(body) < 800:
            last = f"本文が短すぎる({len(body)}字)。ブロックか空ページの可能性"
            time.sleep(3 * (i + 1))
            continue
        head = body[:1500]
        m = BLOCK_MARKS.search(head)
        if m and len(body) < 4000:
            last = f"ブロック/ログイン画面を掴んでいる（目印: {m.group(0)}）"
            time.sleep(3 * (i + 1))
            continue
        # リンクばかりで地の文が無いページ（一覧ページ）は教材にならない
        links = body.count("](http")
        prose = len(re.sub(r"\[[^\]]*\]\([^)]*\)", "", body))
        if links > 40 and prose < len(body) * 0.4:
            raise RuntimeError(
                f"リンク一覧ページを掴んでいる（リンク{links}本、地の文{prose}字）。"
                "記事本文のURLを直接渡すこと")
        return body, status
    raise RuntimeError(f"Web取得に3回失敗: {last}")


def read_pdf(path):
    """ページ単位の失敗を数える。1ページでも取れれば成功、にしない。
    部分取得を成功として通すと、抜けた章が「教材に書いていない」として学習される。"""
    import pypdf
    rd = pypdf.PdfReader(path)
    pages, failed, empty = [], [], []
    for i, pg in enumerate(rd.pages, 1):
        try:
            t = (pg.extract_text() or "").strip()
        except Exception as e:
            failed.append(i)
            t = f"[このページの抽出に失敗: {e}]"
        else:
            if len(t) < 20:
                empty.append(i)
        pages.append(f"\n## p.{i}\n{t}")
    body = "\n".join(pages)
    n = len(rd.pages)
    bad = len(failed) + len(empty)
    if bad / max(1, n) > 0.2:
        raise RuntimeError(
            f"PDF {n}ページ中 {bad}ページが取れない"
            f"（例外 {len(failed)}ページ / 空 {len(empty)}ページ）。"
            f"画像PDFかレイアウトが特殊。OCRが要る（このスキルは未対応）。"
            f"取れなかったページ: {(failed + empty)[:20]}")
    return body, {"pages": n, "failed_pages": failed, "empty_pages": empty}


# ---------- 本体 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--slug")
    ap.add_argument("--lang", default="auto", choices=["auto", "ja", "en"])
    ap.add_argument("--model", default=WHISPER_MODEL_DEFAULT)
    ap.add_argument("--force-whisper", action="store_true")
    ap.add_argument("--keep-video", action="store_true",
                    help="YouTubeの動画本体も480pで残す（frames.py で画面を見るため）")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    src = a.source
    slug = a.slug or slugify(os.path.splitext(os.path.basename(src))[0] if not src.startswith("http") else src)
    final_txt = os.path.join(a.out, slug + ".txt")
    meta = {"slug": slug, "source": src, "fetched_at": time.strftime("%Y-%m-%d %H:%M"),
            "kind": None, "method": None, "status": "OK"}

    vid_tmp = None
    work = tempfile.mkdtemp(prefix="study-")
    # 途中で失敗しても前回の .txt を残さない。残すと「今回の教材」として
    # 古い内容がdigestに流れる（Codex指摘・2026-08-14）
    out_txt = os.path.join(work, "out.txt")
    try:
        is_url = src.startswith("http")
        ext = os.path.splitext(src)[1].lower()

        if is_url and re.search(r"(youtube\.com|youtu\.be)", src):
            meta["kind"] = "youtube"
            meta.update(yt_meta(src))
            sub, how = (None, "SKIPPED") if a.force_whisper else yt_subs(src, work, a.lang)
            meta["subtitle_result"] = how
            if sub:
                n = write_timed(parse_vtt(sub), out_txt)
                meta["method"] = f"yt-dlp {how}"
            elif how in ("BLOCKED", "UNKNOWN_ERROR") and not a.force_whisper:
                meta["blocked"] = True
                raise RuntimeError(
                    "YouTubeから字幕を取れなかったが、"
                    f"『字幕が無い』とは確認できていない（{how}）。"
                    "20分ほど置いて再実行するか、内容を確認した上で "
                    "--force-whisper で音声から起こすこと。"
                    "ここで自動的にwhisperに進むと、由来が誤って記録される")
            else:
                aud = yt_audio(src, work)
                srt = whisper(to_wav16(aud, work), work, a.lang, a.model)
                n = write_timed(parse_srt(srt), out_txt)
                meta["method"] = ("whisper(字幕なしを確認済み)" if how == "NO_SUBS"
                                  else "whisper(--force-whisper指定)")
            meta["blocks"] = n
            if a.keep_video:
                try:
                    vid_tmp = yt_video(src, work)
                except Exception as e:
                    meta["video_error"] = str(e)[:300]
                    print(f"注意: 画面用の動画は落とせなかった（文字起こしは取れている）: "
                          f"{str(e)[:200]}", file=sys.stderr)

        elif is_url:
            meta["kind"] = "web"
            body, http_status = fetch_html(src, work)
            open(out_txt, "w", encoding="utf-8").write(body)
            meta["method"] = "r.jina.ai"
            meta["http_status"] = http_status
            meta["chars"] = len(body)

        elif ext in VIDEO_EXT or ext in AUDIO_EXT:
            if not os.path.exists(src):
                die(f"ファイルが無い: {src}")
            meta["kind"] = "video" if ext in VIDEO_EXT else "audio"
            try:
                d = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=nw=1:nk=1", src], timeout=120).stdout.strip()
                meta["duration_sec"] = d
            except Exception:
                pass
            srt = whisper(to_wav16(src, work), work, a.lang, a.model)
            n = write_timed(parse_srt(srt), out_txt)
            meta["method"] = "whisper(ローカル)"
            meta["blocks"] = n

        elif ext == ".pdf":
            if not os.path.exists(src):
                die(f"ファイルが無い: {src}")
            meta["kind"] = "pdf"
            body, pdfinfo = read_pdf(src)
            open(out_txt, "w", encoding="utf-8").write(body)
            meta["method"] = "pypdf"
            meta.update(pdfinfo)
            meta["chars"] = len(body)

        elif ext in DOC_EXT:
            if not os.path.exists(src):
                die(f"ファイルが無い: {src}")
            meta["kind"] = "doc"
            if ext == ".vtt":
                write_timed(parse_vtt(src), out_txt)
            elif ext == ".srt":
                write_timed(parse_srt(src), out_txt)
            else:
                shutil.copyfile(src, out_txt)
            meta["method"] = "そのまま"
            meta["chars"] = os.path.getsize(out_txt)

        else:
            die(f"対応していない入力: {src}")

        if not os.path.exists(out_txt) or os.path.getsize(out_txt) < 200:
            meta["status"] = "EMPTY"
            die(f"取れた本文が短すぎる({os.path.getsize(out_txt) if os.path.exists(out_txt) else 0}"
                "バイト)。0件ではなく取得失敗として扱うこと")

        os.replace(out_txt, final_txt)   # 成功した時だけ置き換える
        meta["txt"] = final_txt

        if vid_tmp:
            viddir = os.path.join(a.out, "video")
            os.makedirs(viddir, exist_ok=True)
            final_vid = os.path.join(viddir, slug + os.path.splitext(vid_tmp)[1])
            shutil.move(vid_tmp, final_vid)
            meta["video"] = final_vid

    except Exception as e:
        meta["status"] = "ERROR"
        meta["error"] = str(e)[:500]
        # 前回の成功データが残っていると次のdigestがそれを読む。名前を変えて無効化する
        if os.path.exists(final_txt):
            stale = final_txt.replace(".txt", f".stale-{time.strftime('%H%M%S')}.txt")
            os.replace(final_txt, stale)
            meta["stale_moved_to"] = stale
            print(f"注意: 前回の {os.path.basename(final_txt)} は "
                  f"{os.path.basename(stale)} に退避した（今回の取得は失敗）", file=sys.stderr)
        json.dump(meta, open(os.path.join(a.out, slug + ".meta.json"), "w"),
                  ensure_ascii=False, indent=1)
        die(str(e))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    json.dump(meta, open(os.path.join(a.out, slug + ".meta.json"), "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"txt": final_txt, "meta": meta}, ensure_ascii=False))


if __name__ == "__main__":
    main()
