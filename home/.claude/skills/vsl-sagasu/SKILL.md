---
name: vsl-sagasu
description: 勝っている広告を本人に聞かずに自分で見つけてきて、広告タイプ別に並べ、まだ構造を借りていない物だけを次の参考として出すスキル。自社のMeta広告（MELAO・ワンドライ）の実績と、GetHookdの勝ちVSLの両方から拾い、フックを0/1/3秒まで割った分解にして型の棚に入れる。発動:「勝ってる広告探して」「winning VSL見つけて」「今週の参考出して」「/vsl-sagasu」「まだ借りてない勝ち広告ある？」「AI広告の勝ち型取ってきて」「次に何をリップする？」。参考を渡されてから台本を書くのは /vsl-tsukuru、構造を割るだけなら /vsl。
---

# vsl-sagasu — 次に借りる構造を、自分で見つけてくる

読む人: 次の参考を探す Claude と本人。
読む時: 週のはじめ。参考が切れた時。`/vsl-sagasu` と言われた時。
読まなくていい条件: 参考がもう決まっている時（`/vsl-tsukuru` に直行する）。

やることは1つ。**勝っている広告を広告タイプ別に並べ、まだ借りていない物だけ残して、次の参考にする。**
台本は書かない（`/vsl-tsukuru`）。動画も作らない（`ec/構造/編集OS/_設計.md`）。

出口は4つ。`_勝ち一覧.md`（判断の1枚）・`_借りた元.tsv`（重複を消す台帳）・
`_参考の箱.md` に「待ち」の行・借りると決めた物だけ `T<番号>/_分解.md`。

**このファイルの並び順は意図的。** 冒頭＝関門、中盤＝参考、末尾＝手順。

---

<gates>

# 1. 関門 — ここを通らないものは成果物にしない

## 着手ゲート

| 条件 | 無い時 |
|---|---|
| MCP `meta-ads` がつながっている | 自社の段を飛ばし、GetHookd の段だけ回す。飛ばした事を報告に書く |
| Dia に `app.gethookd.ai` のログイン済みタブがある（`dia tabs`） | 自社の段だけ回す。飛ばした事を報告に書く。ログインは代行しない |
| `_借りた元.tsv` に行がある | `python3 scripts/daicho.py 埋める` を先に走らせる。台帳が空だと全部が「まだ借りていない」に見える |
| `~/Documents/Obsidian Vault/ec/構造/毎日の制作/_参考の箱.md` がある | 書き込み先が無い。パスを本人に確認する |

## 契約

- **広告は読むだけ。停止・予算・リンク・素材は1つも触らない**（本人 2026-09-19。提案だけする）
- **GetHookd は MCP を使わず、ログイン済みタブから内部APIで取る**（`scripts/hookd.sh`）。
  クレジットを使わない。MCP の `search_ads` は1行につき静止画が最大4枚返り、20行で8万トークン飛ぶ
- **順位・線引き・重複の除外は `scripts/erabu.py` が決める。** 会話の中で数えない
- **画を見て決めるのは Claude の仕事。** 名前から広告タイプが決まらない物は `erabu.py` が
  標準エラーに出すので、その `参考` の画像を開いて決め、名前ではなく画で判定する
- **構造・フォーマット・フックは別の軸。** 候補の creative の名前に、もう借りた型の元の広告の名前が
  入っていたら（`melao_clay_3-5_紙一枚フック` の `3-5` は T09）、新しいのは画とフックだけ。分解では
  段の表を書き直さず「構造は T<番号> と同じ」と1行書き、フックの節と作り方だけ埋める。台帳へは
  `--軸 フォーマット`（または `--軸 フック`）で入れる。既定の `--軸 構造` は新しい段の並びを借りた時だけ
- 落ちたら同じコマンドで続きから。`erabu.py` は `--書く` を付けるまで Vault に触らない

## 合格の定義

```bash
python3 ~/.claude/skills/vsl-sagasu/scripts/check.py            # exit 3 なら報告しない
python3 ~/.claude/skills/vsl-sagasu/scripts/check.py --分解 "<T<番号>/_分解.md>"
```

| # | 検査 | 落ちる条件 |
|---|---|---|
| 1 | 台帳が読めて (鍵,軸) が重複していない | 台帳が空・同じ広告IDが同じ軸で2行 |
| 2 | 勝ち一覧が今日の日付・数字の窓と取得時刻つき | 前回の物が残っている |
| 3 | 候補の表が読める | 見出しの形が変わった（0本と取り違えない） |
| 4 | 画を見て決める広告が0本 | 名前から広告タイプが決まらない物を放置した |
| 5 | 候補に台帳の物が混ざっていない | 台帳と照合できていない |
| 6 | 候補が全部 参考の箱に入っている（鍵の完全一致） | 21:30の発注に乗らない |
| 7 | 分解のフックの節が10項目とも埋まっている | 見出しだけ写して中身が空・`<秒>` のまま |

## 成果物に出してよいもの

| 出す | 出さない |
|---|---|
| 広告タイプ・ROAS・獲得単価・25%到達率・残り率・鍵 | 広告の停止や予算の提案（別の会話でやる） |
| 広告の名前を押せる形にしたリンク（`[名前](URL)`。Telegramは `<a href>`） | URLを名前の後ろに裸で置く形（括弧までリンクに食われて404を開かせる） |
| 「まだ借りていない」候補 | もう `_借りた元.tsv` にある物 |
| 実測できた数字 | 推定した出稿額・推定したROAS |
| 薬機法・景表法に触れない書き方 | 法の指摘そのもの（本人が聞いた時だけ） |

</gates>

---

<reference>

# 2. 参考（引く。通読しない）

## 実測済みの事実（2026-09-22）

| 分かった事 | 効き方 |
|---|---|
| MELAO は自社のアカウント `REPLACE_ME`、ワンドライは `REPLACE_ME` | 競合ではない。実績（ROAS・獲得単価）が全部取れる |
| ad の `creative_id` は取れる。`creative` は取れない | 広告タイプは creative を1回引いてから決める |
| creative の名前に種類が入っている（`melao_clay_3-5_紙一枚フック` `melao_static_01_砂利道`） | 広告の名前（`3-5` `clay-2 紙一枚`）より creative の名前の方が正確 |
| `video_play_actions` が null の広告は静止画 | 動画か静止画かの機械の見分けがこれ |
| Meta に3秒再生の欄が無い（`video_3_sec_watched_actions` は存在しない） | フック率は `video_p25_watched_actions ÷ impressions` で代用する |
| `is_ai_generated` は **MCP では動画と掛けると0件だが、内部API では効く**（勝ち・動画・60秒以上で126本／1社1本で17社）。`page_type` と同時に付けると0件 | AIの動画はこれで引く。着地の条件とは**別々に**取る |
| `video_format=vsl` はほぼ空（勝ち・動画と掛けて24件） | 使わない |
| うちのJP広告は GetHookd に入っていない（`REPLACE_ME.myshopify.com` も日本語クエリも0件） | 自社の画と台本は Meta と Vault から取る |
| GetHookd の MCP は1行 0.01クレジット。残り 287 | **使わない。** 内部APIなら0クレジット |
| 内部APIの行に台本は無い。`download_url` から mp4 が落ちる | 台本は借りる1本だけ `whisper-cli` で起こす |
| `download_url` の mp4 を `ffmpeg` で 0/1/3秒に切れる | フックの分解の絵はここから |
| 手元の道具: `yt-dlp` `ffmpeg` `whisper-cli`（`~/.cache/whisper/ggml-large-v3-turbo.bin`）あり。python の `whisper` は無い | 文字起こしは `whisper-cli` |
| 自社の動画は `permalink_url`（`/reel/<video_id>/`）から `yt-dlp --cookies-from-browser chrome` で落ちる。素の `yt-dlp` は落ちない | 0/1/3秒の画はここから切る |
| `clay-2 紙一枚`（¥229,375・ROAS 3.83）は T09 の台本をクレイで撮り直し、フックだけ新しい物だった | 「まだ借りていない」＝構造が新しい、とは限らない。軸で分ける |
| `effective_object_story_id` は `<ページID>_<投稿ID>`。`https://www.facebook.com/<ページID>/posts/<投稿ID>` が動画も静止画も200で開く（2026-09-22 実測） | **広告IDを出す時は必ずこのリンクにする。** スマホで押すとFBアプリで実物が開く |
| GetHookd の `share_url` はログイン無しで開く（2026-09-22 実測・200、題と社名が出る） | GetHookd 側のリンクはこれを1本目にする。2本目は `external_id` の広告ライブラリ |
| この Mac は `wakepoweron at 4:58AM every day` が既に入っている（`pmset -g sched` で確認） | 電源に繋がっていれば、蓋を閉じていても朝の2本は走る |
| routine（クラウド実行）が使えるのは claude.ai のコネクタだけ。`meta-ads` と `gethookd` は Claude Code 側のMCPなので routine から呼べない（2026-09-22 確認） | 見張りはこの Mac で走らせる。クラウドに移すなら先に claude.ai/customize/connectors で両方つなぐ |

## GetHookd の内部API（2026-09-22 実測。MCPは使わない）

| 何 | 値 |
|---|---|
| 探す | `POST /api/get-ads`（本文はJSON・値は**配列**）。1ページ24件 |
| 1本の中身 | `GET /api/get-ad/<id>` → `media[0].video_length` と `download_url` |
| スワイプ欄 | `GET /api/get-user-ads` |
| 効く条件の名前 | `performance_scores` `ad_format` `page_type` `video_lengths` `ads_per_brand_limit` `is_ai_generated`（full/partial）`language` |
| **効かない名前（黙って無視される）** | `page_types` `ad_formats` `landing_page_types` `ai_generated` `cls_is_ai_generated`。件数が動かないので気づけない |
| 取る枠は2つ（`hookd.js`） | **AI**＝`is_ai_generated`（126本・17社）／**VSL着地**＝`page_type`（558件）。同時に付けると0件になるので分けて取り、それぞれ上位3本を出す。AIだけに絞らない（本人 2026-09-23「AIだけじゃなくても全然いい」） |
| 言語 | 絞らない。`language:["en"]` にすると17社→6社に落ちる。構造を借りるので言語は問わない |
| 認証 | タブのセッション。`XSRF-TOKEN` のクッキーを `X-XSRF-TOKEN` に入れる |
| `dia do` の出口 | **結果も所要時間も標準エラーに出る。** stdout は空（`2>&1` で拾う） |

実測: AI枠17社・VSL着地枠558件。6本ずつ取って 64〜263秒・81〜100点。`/api/v1/explore`（MCPが叩く方）は
タブのセッションでは 401 なので使わない。

## 広告タイプ（`erabu.py` の `タイプ表` が正本）

| コード | 呼び名 | 機械の見分け |
|---|---|---|
| V-clay | 動画・クレイ（粘土） | 動画 かつ 名前に clay / cray / 粘土 |
| V-anime | 動画・3DCG/アニメ | 動画 かつ 名前に アニメ / 3d / cg / メラオの訴求文（`私が神経痛を治した方法` 等。T09の分解で3DCGと実測済み） |
| V-hito | 動画・人が喋る | 動画 かつ 名前に UGC / 対談 / heygen / インタビュー / 証言 |
| V-vsl | 動画・VSL（声＋素材） | 動画 かつ 上に当たらない |
| S-ugc | 静止画・UGC/手書き | 静止画 かつ 名前に UGC / 手書き / メモ / 手紙 |
| S-hiyu | 静止画・比喩1枚 | 静止画 かつ 名前に 比喩 |
| S-static | 静止画・その他 | 静止画 かつ 名前が `S<数字>_` `T<数字>_` `_static_`（メラオの付け方は2系統） |
| N-native | ネイティブ広告（長文＋記録風1枚） | 静止画 かつ 本文300字以上 |
| H-ai | GetHookd・AIで作った動画 | `hookd.js` の AI 枠から来た行（`is_ai_generated`） |
| H-vsl | GetHookd・VSL | `hookd.js` の VSL着地 枠から来た行（`page_type`） |
| V-nazo / S-nazo | 見て決める | 上のどれにも当たらない。画を開いて Claude が決める |

## 線引き（`erabu.py` の頭で1行ずつ直せる）

| 何 | 値 | なぜ |
|---|---|---|
| ROAS | 3.0 以上 | 本人 2026-09-22「3以上でも全然高いから、それを基準にしつつ」 |
| 支出 | ¥20,000 以上 | これ未満は学習が足りず、ROASが跳ねているだけ |
| 購入 | 10件以上 | 獲得単価¥5,000前後だと5件は1日分。ROASが跳ねているだけの物が上に来る |
| タイプごとの本数 | 上位3本 | 本人 2026-09-22「上位3位とかでまだコピーしてないの」 |
| 並べ方 | 線を越えた中で**支出の多い順** | ROAS順だと ¥23,000・6件が ¥744,000・85件より上に来る（2026-09-22 実測） |
| GetHookd | 81点以上・60秒以上。AI枠は上位6本、VSL着地枠は上位1本（`erabu.py` の `タイプ別の上位`。本人 2026-09-23「AIの割合を高く」） | optimized 以上。60秒未満はVSLの構造を持たない。台本は借りる時に起こす |

## 測れないもの

| 何 | なぜ |
|---|---|
| 3秒再生率 | Meta の広告APIに欄が無い。25%到達で代用しているので、短い動画ほど甘く出る |
| GetHookd 側の出稿実績 | 出稿額もROASも見えない。点と配信日数が代わり |
| うちのJP広告の映像・台本（GetHookd の `POST /api/get-ads` で探しても出ない） | 索引に入っていない |
| ROAS の真偽 | Meta の申告値。Shopify の実売と一致しない |
| 「AIで作ったか」の自動判定 | GetHookd のタグが動画に付いていない。画を見て決めるしかない |

## 前後の工程

| 前 | ここ | 後 |
|---|---|---|
| なし（週の頭に自分から動く） | `/vsl-sagasu` 勝ちを見つけて型にする | `/vsl-tsukuru` 台本を書く → `ec/構造/編集OS/_設計.md` 動画を作る |

</reference>

---

<procedure>

# 3. 実行手順

## Step 0: 台帳を用意する（初回だけ）

```bash
python3 ~/.claude/skills/vsl-sagasu/scripts/daicho.py 埋める
python3 ~/.claude/skills/vsl-sagasu/scripts/daicho.py 見る
```

`_一覧.md` の T01〜T09・A01 が台帳に入る。広告IDがある物はID、無い物は「型 呼び名」が鍵になる。

## Step 1: 自社の広告を取る（MELAO・ワンドライ）

MCP `meta-ads` を2回。`date_preset="last_30d"`、`level="ad"`、`sort="amount_spent_descending"`、`limit=30`。

```
fields = ["id","name","creative_id","amount_spent","purchase_roas","omni_purchase","impressions",
          "video_play_actions","video_p25_watched_actions","video_p100_watched_actions",
          "video_avg_time_watched_actions"]
ad_account_id = "REPLACE_ME"   # MELAO
ad_account_id = "REPLACE_ME"   # ワンドライ
```

返ってきた `creative_id` を集めて `ads_get_creatives` を1回ずつ。

```
fields = ["id","name","object_type","video_id","effective_object_story_id","title","body"]
# body は静止画の creative だけ取り、JSON には長さだけ残す（ネイティブ広告の本文は4,000字を超える）
```

広告と creative を突き合わせ、creative の `name` を `creative_name` に、`object_type` `body`
`video_id` `effective_object_story_id` をそのまま足して、作業場に保存する。
`アカウント` にアカウントIDを入れる（スマホで開くリンクを作るのに使う）。

```bash
W=/tmp/vsl-sagasu && mkdir -p $W     # 中身は Write ツールで直接書く（手で写し直さない）
# $W/melao.json   {"出どころ":"melao",  "アカウント":"REPLACE_ME", "広告":[ ... ]}
# $W/wandry.json  {"出どころ":"wandry", "アカウント":"REPLACE_ME", "広告":[ ... ]}
```

## Step 2: GetHookd の勝ちVSLを取る（MCPは使わない）

**GetHookd の MCP は使わない**（本人 2026-09-22「gethookdのmcpは普通に使って欲しくない」）。
ログイン済みの Dia のタブから、Webアプリと同じ内部APIを叩く。クレジット0・画像0枚・独立エージェント不要。

```bash
~/.claude/skills/vsl-sagasu/scripts/hookd.sh 10 > /tmp/vsl-sagasu/hookd.json
```

Dia に `app.gethookd.ai` のログイン済みタブが要る。無ければ本人に開いてもらう（ログインは代行しない）。
条件と欄の名前は `scripts/hookd.js` が正本。**名前を間違えた条件は黙って無視されて件数が減らない**ので、
直す時は必ず `filtered_ads_count` が動くかを見てから入れる。

台本はここでは取らない。借りると決めた1本だけ、Step 4 で `download_url` から落として
`whisper-cli` で起こす（これも無料）。

## Step 3: 並べて、まだ借りていない物だけ残す

```bash
S=~/.claude/skills/vsl-sagasu/scripts
python3 $S/erabu.py --自社 /tmp/vsl-sagasu/melao.json --自社 /tmp/vsl-sagasu/wandry.json \
                    --hookd /tmp/vsl-sagasu/hookd.json
```

試しで画面に出る。標準エラーに「見て決める」が出たら、その `参考` のURL（creative の
`thumbnail_url` か GetHookd の `share_url`）を開いて画を見て、広告タイプを決める。
決まったら `erabu.py` の `タイプ表` に見分けの語を1行足す（次から機械で決まる）。

そのうえで書く。**上と同じコマンドに `--書く` を足すだけ。**

```bash
python3 $S/check.py    # erabu.py に --書く を足して走らせた後に
```

`_勝ち一覧.md` が書かれ、候補が `_参考の箱.md` に「待ち」で入る。

## Step 4: 借りる1本を型にする

候補から1本選ぶ（本人が選ぶ。選ばれなければ ROAS か点の1位）。
`references/分解の型.md` を写して `ec/構造/型/T<番号> <呼び名>/_分解.md` を作る。
番号は `_一覧.md` の最大＋1。呼び名は**中を開かなくても分かる名前**にする。

フックの節の埋め方（0/1/3秒の絵・原文・実測の取り方）は `references/分解の型.md` の末尾の表。

できたら台帳と一覧に足す。

```bash
python3 $S/daicho.py 足す --鍵 <広告ID> --出どころ <melao|wandry|gethookd> \
                          --型 T<番号> --呼び名 "<呼び名>"
python3 $S/check.py --分解 "$HOME/Documents/Obsidian Vault/ec/構造/型/T<番号> <呼び名>/_分解.md"
```

`_一覧.md` の動画の型の表にも1行足す（番号・呼び名・元の広告・分解・使っているブランド）。
画とフックだけ借りた時は `↳ T<番号>` の行にする（新しい番号を取らない）。

**見て却下した候補も台帳に入れる。** 入れないと毎週同じ物が候補に出続ける。

```bash
python3 $S/daicho.py 足す --鍵 <広告ID> --出どころ <出どころ> --型 なし --呼び名 "<なぜ却下したか>" --軸 見送り
```

## Step 5: 見張りの日（`/vsl-sagasu 見張り` で呼ばれた時）

**自社と GetHookd の両方を回す。** GetHookd は `scripts/hookd.sh` から叩けば無料なので毎日でいい
（本人 2026-09-22「GetHookd からもしてきてっていうプロンプトをさしてたのに全然してない」。`scripts/hookd.sh` で叩く）。

```bash
S=~/.claude/skills/vsl-sagasu/scripts
# Step 1 と同じやり方で自社2アカウントを取って melao.json / wandry.json に保存してから
$S/hookd.sh 10 > /tmp/vsl-sagasu/hookd.json          # 落ちたら理由を控えて次へ進む
python3 $S/mihari.py --自社 /tmp/vsl-sagasu/melao.json --自社 /tmp/vsl-sagasu/wandry.json \
                     --hookd /tmp/vsl-sagasu/hookd.json
python3 $S/check.py --知らせる     # 最後に必ず。落ちたら Telegram に1行行く
```

**検査は必ずこの会話の中で走らせる。** launchd から直に `python3` を叩くと
`~/Documents`（Obsidian）が読めない（macOS の許可。2026-09-22 実測 `Operation not permitted`）。

`hookd.sh` が落ちた時（Dia のタブが無い等）は、**自社だけで止めずに `--注記` を付けて回す。**
黙って自社だけ送ると「今日は GetHookd に何も無かった」と区別が付かない。

```bash
python3 $S/mihari.py --自社 … --注記 "GetHookd は取れなかった（Dia に app.gethookd.ai のタブが無い）"
```

前回から新しく線を越えた広告がある日だけ Telegram に1行行く。無ければ何も送らない
（ただし `--注記` がある日は、新しい物が無くてもその1行だけ送る）。
Vault には書かない（書くのは本走だけ）。覚えている鍵は `scripts/state/前回の候補.json`。
今回読まなかった出どころの記憶は消えないので、同じ物を二度知らせない。

## Step 6: 自分から走る仕掛け（入れてある）

| いつ | 何を | plist |
|---|---|---|
| 月曜 6:30 | 本走（Step 1〜4） | `~/Library/LaunchAgents/com.zerogrid.vsl-sagasu.plist` |
| 毎朝 6:50 | 見張り（Step 5・自社とGetHookdの両方） | `~/Library/LaunchAgents/com.zerogrid.vsl-sagasu-mihari.plist` |

**plist には PATH を書く。** launchd は `.zshrc` を読まないので `~/.local/bin` が入らず、
`claude` も `dia` も見つからずに落ちる（2026-09-22 これで朝が1回飛んだ）。
`claude` は絶対パス `~/.local/bin/claude` で呼ぶ。
届かない朝は `/tmp/vsl-sagasu/mihari.err` を見る（`command not found` ならここ）。

どちらも `launchctl load` 済み。止める時は `launchctl unload <plist>`。

Mac が寝ていると走らないので、電源に繋いだまま蓋を閉じて寝る日は次を1回打つ。

```bash
pmset -g sched          # `wakepoweron at 4:58AM every day` が出ていれば何もしなくていい
```

**バッテリーだけで蓋を閉じている時は走らない。** ただし取りこぼさない。見張りは
`scripts/state/前回の候補.json` と比べるので、次に起きた朝の1通に、寝ていた日の分もまとめて出る
（前に見た日から2日以上空いていたら、その事も1通目に書く）。

## Step 7: 夜に台本まで作る（アルコットとここちドライ・毎晩 3:00〜）

朝の3本のために、夜のうちに **探す→選ぶ→台本を書く→Obsidian に入れる** までを通す。本人には聞かない。

| 何 | 中身 |
|---|---|
| 走らせる物 | `python3 ~/.claude/skills/vsl-sagasu/scripts/daihon.py --商品 アルコット,ここちドライ --本数 3`（1商品3本。手で今すぐ回す時は `--今すぐ`） |
| 参考を取る所 | **ワンドライの自社広告と、GetHookd の AIで作った勝ち広告だけ。メラオからは取らない**（本人 2026-09-30）。1商品につきワンドライは最大1本 |
| いつ | `com.zerogrid.vsl-daihon.plist`。3:00 以降、15分おきに「今日の分が終わっていなければ続きから」。1日3回まで試す |
| 探す係 | `scripts/daihon/探す.md`。ワンドライと GetHookd を取り、商品ごとに動画3本と入口を選ぶ（商品をまたいで同じ参考を使わない） |
| 台本係 | `scripts/daihon/書く.md`。1本ずつ `/vsl-tsukuru` の流れ1〜8（分解→書類→フック5案→`入れる.py` 0件）。声・素材・有料の生成には進まない |
| 置き場 | 書類は Vault `ec/<商品>/05 VSL/02 構造で作る/T<番号> <呼び名>/<入口>.md`。見出しのすぐ下に `> **参考の動画**:` の2行（リンク・出どころ・数字・手元の動画）。作業場は `scripts/state/台本/<日>/`（選んだ.json・結果-N.json・log.txt） |
| 知らせ | 終わったら Telegram に1通（型・入口・参考のリンク・フック・書類）。朝は `/asa-3bon` の工程7（本人チェック1）から |
| 止まった時 | `scripts/state/台本/<日>/log.txt`。やり直しは同じコマンドに `--今すぐ` |

## 使った構造の記録（骨組み）

型の番号（T）より1段上の「話の進め方」を骨組みと呼ぶ。番号が違っても骨組みが同じなら、もう使った構造（2026-09-30 本人「使った構造・フレームワークを記載できる仕組み」。T11・T16・T18・T19 が全部「日を追って変わる」だった）。

| 物 | 中身 |
|---|---|
| 正本（手で足す） | Vault `ec/構造/型/_骨組み.tsv`（骨組み・見分け・型・元の広告の鍵・決めた日） |
| 見る1枚（機械が書く） | Vault `ec/構造/型/_使った構造.md`（骨組みごとの型と、商品ごとの台本の本数・台本の一覧） |
| 道具 | `python3 ~/.claude/skills/vsl-sagasu/scripts/kouzou.py 全部`（同期＝書類に出てくる広告IDを台帳に足す → 書く → 検査） |
| 自動で走る所 | `台本/入れる.py` が違反0件の後に毎回呼ぶ。骨組みの無い型があると `入れる.py` が止まる |
| 夜の台本係 | 参考の進め方を `_使った構造.md` と比べ、同じなら書かずに「同じ骨組み」で見送り、予備の参考に回す（`scripts/daihon/書く.md` 手順3） |

## 保存先

| 物 | 置き場 |
|---|---|
| 判断の1枚 | `ec/構造/型/_勝ち一覧.md`（毎回上書き） |
| 借りた台帳 | `ec/構造/型/_借りた元.tsv`（足すだけ） |
| 次の参考 | `ec/構造/毎日の制作/_参考の箱.md` に「待ち」で1行 |
| 借りた型 | `ec/構造/型/T<番号> <呼び名>/_分解.md` と `_一覧.md` の1行 |
| 作業場 | `/tmp/vsl-sagasu/`（生JSON。Vaultに入れない） |

</procedure>
