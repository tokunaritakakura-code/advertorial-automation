# チームの部屋

読む人: この部屋を直す・役を足す Claude。
読む時: 画面・会話の流れ・承認カードを直す前。
読まなくていい条件: 役の仕事の中身を直す時（それは Vault `ec/構造/ハーネス/00 組織図.md` と `役/<名前>.md`）。

| 何 | どこ・どうする |
|---|---|
| 画面 | http://localhost:3200 （Mac の起動時に `com.zerogrid.team-room` が立ち上げる） |
| 止める・入れ直す | `launchctl kickstart -k gui/$(id -u)/com.zerogrid.team-room` |
| 役とチャンネル | `roles.json`（名前・部・色・チャンネルのリーダーとメンバー） |
| 役の指示 | 組織図の行＋`役/<名前>.md` を毎回読んで渡す（`server.mjs` の `指示`） |
| 承認カードの対象 | `server.mjs` の `危ない道具`・`危ないコマンド`。全部の道具の手前の PreToolUse で止める |
| 戻しから学ぶ | 編集長が FAIL にした理由を、作った役（編集長の前に頼まれた役）ごとに Opus が一般化して `data/戻しの決まり.json` に溜める。その役が動くたびに多い順25行を指示に付け、出す前に照らさせる。本人の決まりに反する物（薬機法・景表法の指摘、店の声を疑う指摘）は外す（`data/戻しの決まり_外した.json`） |
| 記録 | `data/room.db`（会話）・`data/server.log` |
| 頭脳 | Claude Agent SDK。Claude Code のログイン（Max）のまま。APIキーは使わない |

確かめた事（2026-10-01）: リーダー → コピーライター → 編集長の差し戻し → 直し → 通す → まとめ、が会話だけで回る／`rm -rf` で承認カードが出て、却下すると実行せずに止まる／裏で動く状態から Claude につながる。

## 部屋の外で作った物を審査に出す（2026-10-07 本人）

Claude Code の会話で直接作った・直した EC の成果物は、本人に出す前にこの形で編集長に出す。`作り手` に、本来その仕事を持つ役の名前を入れる（戻された理由はその役の決まりに溜まる）。部屋で走っている仕事は止めない（同時に動くのは4人まで。空くまで待つだけ）。

```bash
F=<成果物の絶対パス>; ROLE=<作り手の役>; CH=<その役のチャンネル creative|funnel|research|growth|hq>
python3 - "$F" "$ROLE" "$CH" > /tmp/review.json <<'PY'
import json,sys,hashlib
f,role,ch=sys.argv[1:4]
print(json.dumps({"channel":ch,"作り手":role,"text":f"@編集長 部屋の外で作った物の審査（作り手 {role}）","context":{"brand":"<ブランド>","job_id":"<案件>","revision":1},
 "review":{"artifacts":[{"path":f,"revision":1,"sha256":hashlib.sha256(open(f,'rb').read()).hexdigest()}],"rules":f"{role} の手順書（Vault ec/構造/ハーネス/役/{role}.md）の関門と、本人の直しの台帳の {role} の節で照らす。参考がある物は差の検査も"}},ensure_ascii=False))
PY
T=$(curl -s http://127.0.0.1:3200/api/state | python3 -c "import json,sys;print(json.load(sys.stdin)['csrf_token'])")
curl -s -X POST -H "x-team-token: $T" -H 'content-type: application/json' --data-binary @/tmp/review.json http://127.0.0.1:3200/api/post
```
