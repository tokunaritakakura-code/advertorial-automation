#!/bin/zsh
# GetHookd の勝ちVSLを、MCP もクレジットも使わずに取る
# （本人 2026-09-22「gethookdのmcpは普通に使って欲しくない」）。
# ログイン済みの Dia のタブから Webアプリと同じ内部APIを叩くだけ。画像が返らないのでトークンも食わない。
#
# 使い方: hookd.sh [何本] > /tmp/vsl-sagasu/hookd.json
# 既定10本。1ページ24件までなので、それ以上は hookd.js の page を足す。
#
# **取得を dia do の中で待たない**（2026-09-22 実測）。取得は 8〜15秒かかり、`dia do` の中で await すると
# CDP の評価が時間切れになって undefined が黙って返る。0件と区別が付かないまま朝のGetHookdが2回飛んだ。
# なので「投げる → 待つ → 読む」の3回に割る。
set -u
N="${1:-10}"
HERE="${0:A:h}"
待つ秒=3
待つ回数=40        # 3秒 × 40 = 最大2分。実測は8〜15秒で終わる

TAB=$(dia tabs 2>/dev/null | grep "app.gethookd.ai" | head -1)
if [[ -z "$TAB" ]]; then
  print -u2 'Dia に app.gethookd.ai のタブが無い。本人に開いてもらう（ログインは代行しない）'
  exit 2
fi
# タブが /sign-in に留まっていると fetch が JSON を返さない（2026-09-22 実測。これで朝のGetHookdが飛んだ）。
# 毎回 /explore に入れ直してから取る。クッキーが生きていればそのまま入れる＝ここで自分で直る
NOW=$(dia nav "https://app.gethookd.ai/explore" --tab gethookd 2>&1 | head -1)
if [[ "$NOW" == *"/sign-in"* ]]; then
  print -u2 'GetHookd のログインが本当に切れている。本人がブラウザでログインし直す（代行はしない）'
  exit 4
fi

JS=$(<"$HERE/hookd.js")
JS="${JS//__N__/$N}"

# dia do は結果も所要時間も **標準エラー** に出す（2026-09-22 実測。stdout は空）。
# 最後の行の所要時間だけ落とす
投げた=$(dia do --tab gethookd "$JS" 2>&1 | sed '$d')
if [[ "$投げた" != *"投げた"* ]]; then
  print -u2 "取得を投げられなかった（返り: ${投げた:-空}）。dia doctor と、タブのログインを見る"
  exit 3
fi

# 取れるまで待つ。ページを読み直すと window.__hookd が消えるので、その時は「待ち」のまま時間切れになる
RAW=""
for i in {1..$待つ回数}; do
  sleep $待つ秒
  状態=$(dia do --tab gethookd 'return window.__hookd ? "できた" : (window.__hookdErr ? ("失敗 " + window.__hookdErr) : "待ち");' 2>&1 | sed '$d')
  case "$状態" in
    できた*) RAW=$(dia do --tab gethookd 'return window.__hookd;' 2>&1 | sed '$d'); break ;;
    失敗*)   print -u2 "GetHookd から取れなかった: ${状態#失敗 }（0件なのか失敗なのかを切り分ける）"; exit 5 ;;
  esac
done
if [[ -z "$RAW" ]]; then
  print -u2 "$((待つ秒 * 待つ回数))秒待っても取れなかった。0件と取り違えない。dia doctor と、タブのログインを見る"
  exit 3
fi

print -r -- "$RAW" | python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
except json.JSONDecodeError as e:
    sys.exit(f"dia の返りが JSON ではない（{e}）。hookd.js を dia do に手で通して確かめる")
広告 = d.get("広告") or []
if not 広告:
    sys.exit("GetHookd が0件。条件を緩めるか、タブのログインを確かめる")
print(json.dumps({"出どころ": "gethookd", "全体": d.get("全体"), "広告": 広告},
                 ensure_ascii=False, indent=1))
print(f"GetHookd から {len(広告)} 本（条件に合うのは全体 {d.get("全体")} 件）。クレジットは使っていない",
      file=sys.stderr)
'
