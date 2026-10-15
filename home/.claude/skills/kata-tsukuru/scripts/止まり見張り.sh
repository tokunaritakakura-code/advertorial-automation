#!/bin/bash
# 裏の AI の作業場を見て、30分以上どのファイルも更新されていない所を出す（2026-10-10 ハリネルが知らせなしに2時間止まっていた）。
# 使い方: bash 止まり見張り.sh <作業場のフォルダ>...   終了コード: 0=全部動いている / 1=止まっている所がある
now=$(date +%s); bad=0
for d in "$@"; do
  [ -d "$d" ] || { echo "無い: $d"; continue; }
  last=$(find "$d" -type f -not -name '.DS_Store' -print0 2>/dev/null | xargs -0 stat -f %m 2>/dev/null | sort -n | tail -1)
  [ -z "$last" ] && { echo "空: $d"; continue; }
  m=$(( (now - last) / 60 ))
  if [ "$m" -ge 30 ]; then echo "止まっているかも（${m}分更新なし）: $d"; bad=1; else echo "動いている（${m}分前に更新）: $(basename "$d")"; fi
done
exit $bad
