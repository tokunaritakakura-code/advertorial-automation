#!/bin/bash
# 元動画の音声を文字起こしする（言語は自動判定）→ work/whisper.srt
# 使い方: 01_transcribe.sh <元動画.mp4> <作業フォルダ>
set -e
SRC="$1"; W="$2"; mkdir -p "$W"
MODEL="${WHISPER_MODEL:-$HOME/.cache/whisper/ggml-large-v3-turbo.bin}"
cp "$SRC" "$W/src.mp4"
ffmpeg -v error -y -i "$W/src.mp4" -vn -ac 1 -ar 16000 "$W/src.wav"
whisper-cli -m "$MODEL" -f "$W/src.wav" -l auto -osrt -of "$W/whisper" >/dev/null 2>&1
ffprobe -v error -show_entries format=duration -of csv=p=0 "$W/src.mp4" > "$W/duration.txt"
echo "✅ $(grep -c '^[0-9]*$' "$W/whisper.srt")文  尺 $(cat "$W/duration.txt")秒  → $W/whisper.srt"
