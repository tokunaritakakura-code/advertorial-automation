#!/bin/bash
# yt-ingest.sh <url> [outdir] — YouTube 1本を「音声×映像」両チャンネルで完全取得する。
#
# パイプライン(レシピの正は references/recipes/youtube.md):
#   0. キャッシュ確認(動画IDごと)。manifest.mdが既にあれば即返す(再取得ゼロ)
#   1. メタデータ + 手動字幕のみ取得(自動字幕は精度が悪いので最初から使わない)
#   2. 手動字幕なし → 音声だけDL(映像なしで速い) → ローカルWhisper(large-v3-turbo)
#      タイトル/章題を --prompt に入れて固有名詞のASR誤りを減らす
#      動画尻を超えるWhisper幻覚はduration超の行を捨てて対策
#   3. 映像をDL → frames.py で場面転換+間隔フロアのキーフレーム抽出(768px, 並列, 画の重複はdHashで破棄)
#      **降ってきた映像が720p未満なら**その場で frames.py --times-only に時刻だけ選ばせ、
#      yt-grab.mjs(ブラウザのプレイヤーから直接スクショ, 実測1920x1080)で撮り直す
#      (2026-08-27実測: yt-dlpはdefault/android/mweb/ios/tv/cookies全経路で360pしか降ってこない。
#       DLは「成功」するので、放っておくと黙って360pのコマで学習してしまう)
#   4. merge.py で時刻同期の統合manifest.mdを生成 ← 学習素材はこれ。字幕単体で学習しない
#
# env: FRAMES_MAX(既定150) / NO_VIDEO=1(フレーム省略) / SURASURA_WHISPER_MODEL(モデルパス)
#      SURASURA_CACHE(既定 ~/.claude/skills/surasura/.cache) / NO_CACHE=1 / MIN_HEIGHT(既定720)
#      NO_HIRES=1(低解像度でも撮り直さない) / KEEP_VIDEO=1
set -euo pipefail

URL="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMES_MAX="${FRAMES_MAX:-150}"
MIN_HEIGHT="${MIN_HEIGHT:-720}"
CACHE_ROOT="${SURASURA_CACHE:-$HOME/.claude/skills/surasura/.cache}"

# --- 0. キャッシュ: 同じ動画を2度取らない ---
VID="$(printf '%s' "$URL" | sed -E 's#.*[?&]v=([A-Za-z0-9_-]{11}).*#\1#; s#.*youtu\.be/([A-Za-z0-9_-]{11}).*#\1#; s#.*/shorts/([A-Za-z0-9_-]{11}).*#\1#')"
if [ "${#VID}" != 11 ]; then VID="$(printf '%s' "$URL" | shasum | cut -c1-11)"; fi
OUTDIR="${2:-$CACHE_ROOT/$VID}"
if [ "${NO_CACHE:-0}" != "1" ] && [ -s "$OUTDIR/manifest.md" ]; then
  echo "CACHED: 取得済みを再利用 (再取得したい時は NO_CACHE=1)"
  echo "OUTDIR: $OUTDIR"
  echo "SOURCE: $(cat "$OUTDIR/.source" 2>/dev/null || echo unknown)"
  echo "SEGMENTS: $(wc -l < "$OUTDIR/segments.tsv" 2>/dev/null | tr -d ' ')"
  echo "FRAMES: $(wc -l < "$OUTDIR/frames.tsv" 2>/dev/null | tr -d ' ')"
  echo "MANIFEST: $OUTDIR/manifest.md  BEATS: $OUTDIR/beats.json"
  exit 0
fi
mkdir -p "$OUTDIR/frames"

# --- 1. メタデータ + 手動字幕のみ(--write-auto-subs は使わない) ---
yt-dlp --skip-download --no-simulate --no-warnings \
  --print "id: %(id)s" \
  --print "title: %(title)s" \
  --print "channel: %(channel)s" \
  --print "duration: %(duration_string)s" \
  --print "duration_sec: %(duration)s" \
  --print "uploaded: %(upload_date)s" \
  --print "views: %(view_count)s" \
  --print "chapters: %(chapters)j" \
  --print "description: %(description)j" \
  --write-subs --sub-langs "ja,ja-orig,en,en-orig" --sub-format vtt \
  -o "$OUTDIR/sub" "$URL" > "$OUTDIR/meta.txt" || true
grep -E "^(id|title|channel|duration|uploaded|views):" "$OUTDIR/meta.txt" || true
DUR="$(grep -E '^duration_sec:' "$OUTDIR/meta.txt" | awk '{print $2}' | cut -d. -f1)"
DUR="${DUR:-99999}"

# --- 2. 文字起こし: 手動字幕(ja-orig>ja>en-orig>en) or Whisper ---
SOURCE="none"
for lang in ja-orig ja en-orig en; do
  if [ -e "$OUTDIR/sub.$lang.vtt" ]; then
    python3 "$SCRIPT_DIR/to_segments.py" "$OUTDIR/sub.$lang.vtt" > "$OUTDIR/segments.tsv"
    SOURCE="manual-sub($lang)"
    break
  fi
done

if [ "$SOURCE" = "none" ]; then
  echo "手動字幕なし → Whisperで文字起こし" >&2
  # 音声DLも403が出る(2026-08-15実測) → 映像と同じくandroidクライアントにフォールバック
  yt-dlp --no-warnings -f bestaudio -x --audio-format wav \
    --postprocessor-args "ffmpeg:-ar 16000 -ac 1" \
    -o "$OUTDIR/audio.%(ext)s" "$URL" >&2 \
  || yt-dlp --no-warnings --rm-cache-dir --extractor-args "youtube:player_client=android" \
    -f "bestaudio/b" -x --audio-format wav \
    --postprocessor-args "ffmpeg:-ar 16000 -ac 1" \
    -o "$OUTDIR/audio.%(ext)s" "$URL" >&2
  # モデルは2箇所を見る(2026-08-27: 実体は ~/.cache/whisper にあるのにこのスクリプトは
  # ~/Library/Caches/whisper-cpp だけを見ていて、手動字幕の無い動画は全部 exit 3 で死んでいた)
  MODEL="${SURASURA_WHISPER_MODEL:-}"
  if [ -z "$MODEL" ]; then
    for m in "$HOME/.cache/whisper/ggml-large-v3-turbo.bin" \
             "$HOME/Library/Caches/whisper-cpp/ggml-large-v3-turbo.bin"; do
      [ -e "$m" ] && MODEL="$m" && break
    done
  fi
  if [ ! -e "${MODEL:-/nonexistent}" ]; then
    echo "ERROR: Whisperモデルが無い: ${MODEL:-未検出} (references/recipes/youtube.md のセットアップ参照)" >&2
    exit 3
  fi
  # 固有名詞のASR誤りを減らす: タイトル+章題を初期プロンプトに与える(速度は変わらない)
  PROMPT="$(python3 - "$OUTDIR/meta.txt" <<'PY'
import json, re, sys
title = chapters = ""
for line in open(sys.argv[1], encoding="utf-8", errors="ignore"):
    if line.startswith("title: "): title = line[7:].strip()
    if line.startswith("chapters: "):
        try:
            ch = json.loads(line[10:].strip())
            if isinstance(ch, list):
                chapters = " ".join(str(c.get("title", "")) for c in ch[:30])
        except Exception: pass
print(re.sub(r"\s+", " ", f"{title} {chapters}").strip()[:800])
PY
)"
  whisper-cli -m "$MODEL" -f "$OUTDIR/audio.wav" -l auto \
    ${PROMPT:+--prompt "$PROMPT"} -osrt -of "$OUTDIR/whisper" >&2
  # 幻覚対策: 動画のdurationを超えた行は捨てる
  python3 "$SCRIPT_DIR/to_segments.py" "$OUTDIR/whisper.srt" \
    | awk -F'\t' -v d="$DUR" '$1 <= d+2' > "$OUTDIR/segments.tsv"
  SOURCE="whisper"
fi

# --- 3. キーフレーム(映像チャンネル。NO_VIDEO=1で省略) ---
# フォールバック3段: 既定クライアント → androidクライアント(403対策, 2026-08-15実測)
#                  → ブラウザseekスクショ yt-grab.mjs(DL自体を回避)
: > "$OUTDIR/frames.tsv"
FRAME_SRC="none"
if [ "${NO_VIDEO:-0}" != "1" ]; then
  if yt-dlp --no-warnings -f "bv*[height<=720]/b[height<=720]/b" \
       -o "$OUTDIR/video.%(ext)s" "$URL" >&2 \
     || yt-dlp --no-warnings --extractor-args "youtube:player_client=android" \
       -f "bv*[height<=720][ext=mp4]/b[height<=720]/bv*[height<=720]" \
       -o "$OUTDIR/video.%(ext)s" "$URL" >&2; then
    VIDEO="$(ls "$OUTDIR"/video.* | head -1)"
    HEIGHT="$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$VIDEO" | head -1)"
    HEIGHT="${HEIGHT:-0}"
    if [ "${NO_HIRES:-0}" != "1" ] && [ "$HEIGHT" -lt "$MIN_HEIGHT" ]; then
      # 降ってきたのが低解像度 → 時刻だけこの映像から選び、実物はプレイヤーから撮り直す
      echo "映像が ${HEIGHT}p (< ${MIN_HEIGHT}p) → 場面転換の時刻だけ使って yt-grab で撮り直す" >&2
      python3 "$SCRIPT_DIR/frames.py" "$VIDEO" - --max "$FRAMES_MAX" --times-only \
        > "$OUTDIR/times.txt" || true
      if node "$SCRIPT_DIR/yt-grab.mjs" "$URL" --times-file "$OUTDIR/times.txt" \
           --out "$OUTDIR/frames" > "$OUTDIR/frames.tsv"; then
        FRAME_SRC="yt-grab(プレイヤー実解像度・時刻は場面転換)"
      else
        echo "yt-grabも失敗 → ${HEIGHT}pの映像からフレームを取る(解像度は低いまま)" >&2
        python3 "$SCRIPT_DIR/frames.py" "$VIDEO" "$OUTDIR/frames" --max "$FRAMES_MAX" > "$OUTDIR/frames.tsv"
        FRAME_SRC="yt-dlp(${HEIGHT}p)"
      fi
    else
      python3 "$SCRIPT_DIR/frames.py" "$VIDEO" "$OUTDIR/frames" --max "$FRAMES_MAX" > "$OUTDIR/frames.tsv"
      FRAME_SRC="yt-dlp(${HEIGHT}p)"
    fi
  else
    echo "yt-dlp全滅 → ブラウザseekスクショにフォールバック(yt-grab.mjs)" >&2
    node "$SCRIPT_DIR/yt-grab.mjs" "$URL" --points "${GRAB_POINTS:-40}" \
      --out "$OUTDIR/frames" > "$OUTDIR/frames.tsv" || true
    FRAME_SRC="yt-grab(等間隔)"
  fi
fi

# --- 4. 統合manifest + ビート構造 + モンタージュ(全景の一次読み) ---
python3 "$SCRIPT_DIR/merge.py" "$OUTDIR/segments.tsv" "$OUTDIR/frames.tsv" > "$OUTDIR/manifest.md"
python3 "$SCRIPT_DIR/beats.py" "$OUTDIR/segments.tsv" "$OUTDIR/frames.tsv" "$OUTDIR" >&2 || true
printf '%s' "$SOURCE" > "$OUTDIR/.source"

# --- 5. 後始末: 学習素材(manifest/segments/frames/montage/beats)以外の重い中間物を消す ---
# 動画・音声はフレーム抽出/文字起こしが済めば用済み。残したい時だけ KEEP_VIDEO=1
if [ "${KEEP_VIDEO:-0}" != "1" ]; then
  rm -f "$OUTDIR"/video.* "$OUTDIR"/audio.wav
  echo "CLEANED: video/audio deleted (KEEP_VIDEO=1で保持可)"
fi

echo "OUTDIR: $OUTDIR"
echo "SOURCE: $SOURCE"
echo "FRAME_SRC: $FRAME_SRC"
echo "SEGMENTS: $(wc -l < "$OUTDIR/segments.tsv" | tr -d ' ')"
echo "FRAMES: $(wc -l < "$OUTDIR/frames.tsv" | tr -d ' ')"
echo "MONTAGES: $(ls "$OUTDIR/montage" 2>/dev/null | wc -l | tr -d ' ')"
echo "MANIFEST: $OUTDIR/manifest.md  BEATS: $OUTDIR/beats.json"
