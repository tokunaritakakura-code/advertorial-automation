#!/bin/bash
# chrome.sh — 統一プロファイルのChromeをCDP付きで起動する（surasuraの足回り）
#
# 鉄則:
#   - ブラウザは1つ: このプロファイル($HOME/.claude/task-fleet/chrome-profile)が
#     全スキル共通の「唯一のブラウザ」。別プロファイルの新設は禁止（2026-08-15 Seiyo指示）
#   - Seiyoの普段のChromeプロファイルは絶対に使わない（Cookie・ウィンドウ完全分離）
#   - open -g でフォーカスを奪わない（Seiyoの作業を止めない）
#   - ログインセッションはこのプロファイルに永続保存（ログインは1回だけ）
#   - ヘッドレスは使わない（bot検知で落とされる。headedでもフォーカスは奪わないので実害なし）
#
# usage:
#   bash chrome.sh [url …]   # CDP(port 9222)付きで起動。既に起動済みならタブとして開く
PROFILE="$HOME/.claude/task-fleet/chrome-profile"
mkdir -p "$PROFILE"

exec open -g -na "Google Chrome" --args \
  --user-data-dir="$PROFILE" \
  --no-first-run --no-default-browser-check \
  --remote-debugging-port=9222 \
  --new-window "${@:-about:blank}"
