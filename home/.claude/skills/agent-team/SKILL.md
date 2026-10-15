---
name: agent-team
description: AIエージェント・係・社員（employee）を作る時は毎回これを通す型。1体に仕事1つ・ルール・終わりの形を持たせ、上に振り分け役を置き、引き継ぎ・共有の資料・状態・審査（PASS/FIX/HUMAN）・承認ゲート・変化があった時だけ起こす見張りまで決める。原文（0xMorlex「How to Turn Grok Into a Team of AI Agents」）を毎回全文読む。発動:「エージェント作って」「エージェント組んで」「係を作って」「社員を雇う」「employee」「サブエージェント作って」「自動で〇〇してくれる仕組み」「毎朝〇〇して報告」「AIに〇〇を任せたい」。スキル単体を作る時は skill-creator、エージェントに仕事を1回投げるだけの時は prompt-quality.md。
---

# agent-team — エージェントを作る時の型

読む人: AIエージェント・係・社員を作る、または直す Claude。
読む時: エージェントを1体でも作る前。定義ファイル・スキル・定時実行・振り分け役のどれを書く前でも。
読まなくていい条件: 既にあるエージェントに仕事を1回投げるだけの時（それは `~/.claude/skills/skill-creator/references/prompt-quality.md`）。

<gates>
## 関門（通らなければ作り始めない）

1. **原文を全文読む。** `references/原文-0xMorlex-2026-08-31.txt`（573行）を毎回、頭から最後まで読む。要約・記憶で済ませない（本人の指示 2026-09-15「一言一句覚えてないと意味ない」）
2. **1体ごとに3つが書けている。** 仕事（1つ）・ルール・終わりの形。どれか1つでも書けないなら、その1体は作らない（原文 §2「An agent needs a job, not a personality」）
3. **振り分け役は自分で作業しない。** 振り分け役の仕事は「誰が持つか決める・引き継ぎを作る・審査を通してから返す」の3つだけ（原文 §3 の router prompt）
4. **戻せない行動に承認ゲートがある。** 送信・公開・支払い・本番反映・削除は、係が準備までで止まり、本人の承認で動く。仕組みで止める（許可設定・送らない作り）。係への「しないで」のお願いでは止めない（原文 §7）
5. **出力は判断に圧縮されている。** 入力が37件なら37件の要約を返さない。本人に届くのは「本人が決める物」だけ（原文 §4「compress the inbox into decisions」）
6. **最初の1体は、毎日くり返す退屈な仕事にする。** 見栄えのするデモから作らない（原文 §4）
7. **効果は実際の1回の実行ログで数える。** 「10倍」と言わず、実行ログに「入った件数・本人に届いた件数・本人が書き直した件数」の3つを書き出す（原文 §9）
</gates>

<reference>
## 参考（引く。通読しない。原文は関門1で全文読んである前提）

### 決める物の一覧（エージェント1組につき、全部埋める）

| # | 決める物 | 原文 | 書く場所（Claude Code） |
|---|---|---|---|
| 1 | 係ごとの 仕事・ルール・終わりの形 | §2 | `~/.claude/agents/<名>.md` か、スキルの手順 |
| 2 | 振り分け役（誰が持つか・引き継ぎ・審査の後に返す） | §3 | 本体の会話で使うスキル（例 `<領域>-tencho`） |
| 3 | 引き継ぎ（相手に渡すのは答えてほしい問いだけ。相手は持ち主の仕事をしない） | §5 | 係の終わりの形に `HANDOFF:` の1行 |
| 4 | 共有の資料（係ごとに要る物だけ読ませる。全員に全部渡さない） | §6 context on demand | Vault の入口と、係ごとの「読む物」の表 |
| 5 | 状態（何が済んだか・何を待っているか・何を決めたか） | §6 の `/state` | `followups.json` `tasks.json` `decisions.json` の形 |
| 6 | 審査（PASS / FIX / HUMAN） | §7 Review Agent | 審査役の定義。FIX は持ち主に戻す |
| 7 | 承認ゲート（戻せない行動の一覧と止め方） | §7 | `settings.json` の許可設定、送らない作り |
| 8 | 見張り（変化があった時だけ起こす） | §10 Monitoring | launchd / `/schedule` と通知先（本人は Telegram） |
| 9 | 測り方（1回の実行で何件入り、何件届き、何件直したか） | §9 | 実行ログに数を残す |

### 原文のプロンプトの型（そのまま使う）

**係の定義**（原文 §2）
```
You own my inbox.

For every new email:
classify it,
identify whether I need to act,
prepare a reply when needed,
track anything waiting for a response.

Never send without my approval.
```

**振り分け役**（原文 §3）
```
Read the request and decide which agent owns it.

Delegate specialist work instead of doing it yourself.

If one agent needs information from another,
create a handoff.

Return the final result only after review.
```

**調べ係**（原文 §2）
```
You own research.

Find primary sources first.
Remove duplicated information.
Verify important claims.
Return only what changes the decision.

Always include the sources.
```

**引き継ぎを受ける調べ係**（原文 §5）
```
Research this for another agent.

Return:
3 important findings,
primary sources,
anything uncertain,
one recommendation.

Do not write the email.
```

**審査役**（原文 §7）
```
Review this action.

Check:
facts,
missing context,
recipient,
tone,
permissions.

Return PASS, FIX, or HUMAN.
```

### Claude Code で置く時の決まり

| 原文の物 | Claude Code | 注意 |
|---|---|---|
| Grok（振り分け役） | 本体の会話か `claude -p` | 係は別の係を直接呼べない。引き継ぎは必ず振り分け役を通す |
| 係 | サブエージェント（`~/.claude/agents/`）かスキル | `tools` で持ち物を絞る |
| 定時の見張り | launchd の `claude -p` | 標準入力を閉じる（`< /dev/null`）。閉じないと止まる（2026-09-15 実測、12分CPU0）。打ち切り時間も付ける |
| 本人への通知 | Telegram（`~/.telegram-arukoto.json` の形） | HTML で太字・表。区切り線で割る |
| 共有の資料 | Vault の `_入口.md` | 係に Vault を探させない。パスで渡す（`~/Documents/Obsidian Vault/_Vault設計.md`） |
| 係への指示文の書き方 | `~/.claude/skills/skill-creator/references/prompt-quality.md` | 役割固定・結論を1行目・禁止・検証手段・反証を3つ |

### 実例（この型で作った物）

| 物 | 場所 |
|---|---|
| アルコットの朝の判断（見張り＋審査の型） | スキル `asa-handan`、`~/Claude Code/arukoto-track/朝判断` |
| EC の係の分業（振り分け役＋係9人） | `~/Documents/Obsidian Vault/ec/wiki/_エージェント構成.md` |
</reference>

<procedure>
## 手順

1. 原文 `references/原文-0xMorlex-2026-08-31.txt` を全文読む
2. 本人の頼みを「毎日くり返す仕事」まで割り、最初の1体を決める（関門6）
3. 「決める物の一覧」の9行を全部埋める。埋まらない行は本人に聞く前に、`~/Documents/Obsidian Vault/ec/_入口.md` と `ls ~/.claude/skills` で既にある物を当たる
4. 係の定義を「原文のプロンプトの型」の形で書く（仕事・ルール・終わりの形・しない事）
5. 承認ゲートを仕組みで入れる（許可設定か、送らない作り）
6. 実際の入力で1回回し、「入った件数 → 本人に届いた件数 → 直した件数」を数える（関門7）
7. 文脈を持たない別のエージェントに、関門1〜7と一覧9行で監査させる
8. 本人に報告する時は、届く物の見本1つと、本人がやる事だけを書く
</procedure>
