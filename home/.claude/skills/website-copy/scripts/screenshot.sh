#!/bin/bash
# screenshot.sh <url> <outfile> [width=1440] [height=14000]
# ヘッドレスChromeでフルページのスクショを撮る（検証の答え合わせ用）
URL="$1"; OUT="$2"; W="${3:-1440}"; H="${4:-14000}"
[ -z "$URL" ] && { echo "usage: screenshot.sh <url> <outfile> [w] [h]"; exit 1; }
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars \
  --window-size="$W,$H" --virtual-time-budget=30000 \
  --screenshot="$OUT" "$URL" 2>/dev/null
echo "shot -> $OUT"
