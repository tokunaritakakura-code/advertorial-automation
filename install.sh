#!/bin/bash
# advertorial-automation を、この Mac の $HOME の同じ場所へ写す。
# 既に同じ名前のファイルがあって中身が違う時は、<名前>.bak-<日時> に避けてから写す。
# 使い方: ./install.sh            … 写す
#         ./install.sh --見るだけ  … 何をどこへ写すかを出すだけ（何も変えない）
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
DRY=0; [ "${1:-}" = "--見るだけ" ] && DRY=1
N_NEW=0; N_REP=0; N_SAME=0

put() { # put <元のファイル> <写す先>
  local src="$1" dst="$2"
  if [ -e "$dst" ]; then
    if cmp -s "$src" "$dst"; then N_SAME=$((N_SAME+1)); return; fi
    [ $DRY = 1 ] && { echo "替える: $dst（今の物は .bak-$TS へ）"; N_REP=$((N_REP+1)); return; }
    mv "$dst" "$dst.bak-$TS"; N_REP=$((N_REP+1))
  else
    [ $DRY = 1 ] && { echo "新しく: $dst"; N_NEW=$((N_NEW+1)); return; }
    N_NEW=$((N_NEW+1))
  fi
  mkdir -p "$(dirname "$dst")"
  cp -p "$src" "$dst"
}

# 1. home/ の中を $HOME の同じ並びへ
while IFS= read -r -d '' f; do
  rel="${f#"$HERE/home/"}"
  put "$f" "$HOME/$rel"
done < <(find "$HERE/home" -type f ! -name '.DS_Store' -print0)

# 2. 試しの結果（草むしり椅子）を、手順書が指している場所へ（記事1は「普通」の形の固定の参考）
EX_DST="$HOME/Claude Code/team-room/引き継ぎ/VSL記事リサーチ_資料/草むしり椅子"
while IFS= read -r -d '' f; do
  rel="${f#"$HERE/example/草むしり椅子/"}"
  put "$f" "$EX_DST/$rel"
done < <(find "$HERE/example/草むしり椅子" -type f ! -name '.DS_Store' -print0)

if [ $DRY = 1 ]; then
  echo "見るだけ: 新しく $N_NEW ／ 替える $N_REP ／ 同じなので飛ばす $N_SAME"; exit 0
fi

# 3. brands.json の "~/" を、この Mac の $HOME に直す（道具は ~ を広げずに読むため）
B="$HOME/Claude Code/ec-harness/config/brands.json"
python3 - "$B" <<'PY'
import os, sys
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
open(p, "w", encoding="utf-8").write(s.replace('"~/', '"' + os.path.expanduser("~") + '/'))
PY

# 4. 実行できる印
chmod +x "$HOME/.local/bin/dia" "$HOME/.local/bin/dia-agent" "$HOME/Claude Code/adv-kata/新規.sh" 2>/dev/null || true
find "$HOME/.claude/skills" "$HOME/.claude/hooks" -name '*.sh' -exec chmod +x {} + 2>/dev/null || true

# 5. 空の置き場（審査を回す.py が写しを置く所）
mkdir -p "$HOME/Claude Code/ec-harness/data/brands/リサーチ/assets" "$HOME/Claude Code/team-room/data" "$HOME/Documents/Obsidian Vault/ec/_リサーチ済み"

# 6. Node の部品（部屋と dia）
if command -v npm >/dev/null 2>&1; then
  (cd "$HOME/Claude Code/team-room" && npm install --no-audit --no-fund)
  (cd "$HOME/.claude/skills/surasura/scripts" && npm install --no-audit --no-fund)
else
  echo "npm が無い。Node.js を入れてから、team-room と ~/.claude/skills/surasura/scripts で npm install を回す"
fi

echo "写した: 新しく $N_NEW ／ 替えた $N_REP（前の物は *.bak-$TS）／ 同じなので飛ばした $N_SAME"
echo "次: README の「4. 入れ方」の 2 から（鍵を置く・フックと MCP を足す・部屋を立てる）"
