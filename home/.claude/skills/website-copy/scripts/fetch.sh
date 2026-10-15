#!/bin/bash
# fetch.sh <url> <outdir> — 完成した公開ページの「生HTML」を1枚まるごと取る
# ブラウザ描画ではなくサーバーが返す素のHTMLを取る（見た目を作る構造とスタイル参照が全部乗っている）
set -e
URL="$1"; OUT="${2:-.}"
[ -z "$URL" ] && { echo "usage: fetch.sh <url> <outdir>"; exit 1; }
mkdir -p "$OUT"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
curl -sL -A "$UA" "$URL" -o "$OUT/original.html"
echo "saved $OUT/original.html ($(wc -c < "$OUT/original.html") bytes)"
