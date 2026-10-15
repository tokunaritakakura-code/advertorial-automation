#!/bin/bash
# UserPromptSubmit フック: EC の仕事っぽい発話を検知したら、本人の決めたこと（1枚）をその会話の最初に1回だけ全文入れる。
# 2026-10-08 本人「決めたことを1枚 → 毎回最初に読ませる」（記事 @polydao の CONSTRAINTS.md）。前の版は役と124マスの図に従えと入れていた（.bak-1008）。
# 何もブロックしない。
set -uo pipefail
payload=$(cat 2>/dev/null || true)
prompt=$(printf '%s' "$payload" | jq -r '.prompt // empty' 2>/dev/null || true)
sid=$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null || true)
[ -z "$prompt" ] && exit 0
printf '%s' "$prompt" | grep -qE 'ハーネス|harness|工程|商品(を|の)?(決め|選|リサーチ)|プロダクトリサーチ|客を知る|ペルソナ|アングル|割り付け|VSL|台本|広告(を|作|の制作)|記事(を|作)|LP|PDP|商品ページ|店を|配信|入稿|測る|学ぶ|リップ|吹き替え|アルコット|ここちドライ|ワンドライ' || exit 0
F="$HOME/Documents/Obsidian Vault/ec/決めたこと.md"
mark="$HOME/.claude/hooks/.決めたこと_読んだ/${sid:-none}"
if [ -f "$F" ] && [ ! -f "$mark" ]; then
  mkdir -p "$(dirname "$mark")"; touch "$mark"
  python3 - "$F" <<'PY'
import json, sys
p = sys.argv[1]; body = open(p, encoding="utf-8").read()
msg = (f"[本人の決めたこと] EC の仕事。手を動かす前にこれを全部守る（正本 {p}）。段の中は役で渡し合わず1つのAIが通す。"
       "合格の線を先に決め、合格するまで回す（回数では止めない。同じ所で2回続けて落ちたら手順か道具を直して続ける）。本人に聞くのはお金のかかる生成・公開・本人にしか決められない事だけ。本人から新しい決めをもらったら、その場でこの1枚に日付つきで1行足す。\n\n" + body)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}}, ensure_ascii=False))
PY
else
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"[本人の決めたこと] EC の仕事。~/Documents/Obsidian Vault/ec/決めたこと.md を守る（この会話では読み込み済み）。新しい決めは、その場でそこに1行足す。"}}'
fi
exit 0
