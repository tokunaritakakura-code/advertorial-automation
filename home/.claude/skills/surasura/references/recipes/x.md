# レシピ: X (x.com)

## 最速経路
`node scripts/x-collect.mjs --handle <name> --count 60` — GraphQL横取りが本命。
ページがスクロール時に受信する `/graphql/*/UserTweets` 系のJSONを `page.on('response')` で捕獲。
全文(長文ポストは `note_tweet` 側)・正確なISO日時・エンゲージ数値まで取れる。DOMはフォールバック。

## 差分収集(2026-08-27導入)
`--out` のJSONが既にあれば読み込んでマージし、**新規だけ**を target 件まで取る。
既知IDばかりが `--stop-on-known`(既定3)回続いたら打ち切る。DL済みメディアは再DLしない。
全部取り直すなら `--no-merge`。実測: naval 23件既存 → 2回目 8.0s で新規24件を足して47件。

## 3媒体100%(鉄則5)
- 文字: 本文+引用RTの中身(`tweetText`の2個目以降)+外部リンクカード(`[data-testid="card.wrapper"]`)
- 画像: `pbs.twimg.com/media` のsrcを `name=orig` に書き換えて原寸DL(未認証で取れる)
- 動画: GraphQL側なら `extended_entities.media[].video_info.variants` の最高bitrate mp4を直DL。
  DOM側は動画URLが取れないので `yt-dlp <ポストURL>` でDL(公開ポスト)
- タブ: 既存のx.comタブを `getOrCreateTab` で再利用し、終了後も標準タブとして残す(2026-08-15 Seiyo指示)

## ログイン
- 統一プロファイルでSeiyoが1回ログイン(未ログインなら x-collect が exit 2 でログインタブを残す)
- ログイン判定セレクタ: `[data-testid="SideNav_AccountSwitcher_Button"]` / `[data-testid="AppTabBar_Home_Link"]`
- 未ログインでもプロフィール冒頭数件は見えるが、スクロールでログイン壁が出て止まる

## セレクタ(DOMフォールバック用)
- 投稿: `article[data-testid="tweet"]`、本文: `[data-testid="tweetText"]`、日時: `time[datetime]`
- リポスト表示: `[data-testid="socialContext"]`

## 落とし穴(実測)
- **GraphQL横取りの落とし穴2つ(2026-08-15解決済み)**:
  (1) タイムラインのクエリ名はXがよくリネームする。`UserTweets`は現在**`UserOriginalsTimeline`**。
  フィルタは `/Timeline|UserTweets|UserMedia|TweetDetail/` と広めに書く。0件になったらまず
  CDP `Network.enable` で全 `/graphql/` のクエリ名を列挙して現物を確認する
  (2) XのAPI呼び出しは**XHRのみ(fetchは0)**で、Playwrightの `page.on('response')` はsw.jsの影響か
  一切発火しない。効くのは「`addInitScript`でXHRをフックして応答テキストを`window.__gq`に積む」方式と
  「`context.newCDPSession(page)` + `Network.enable`」の2つ(両方実測済み)。x-collect.mjsは前者
- GraphQL横取りは引用RT先のツイートも個別エントリとして回収できる(85件中25件が引用先だった実測)。
  DOM併用時は `quoted`/`cardLink`/DL済み`media.file` をマージで温存する
- **ヘッドレスはNG**(2026-08-15実測): `--headless=new` だとログイン扱いから外れ、SSR軽量版(直近7件・ページ送りなし)に落とされた。syndication API(埋め込み用)も実質死んでいる。headed+実プロファイルのみ通る
- 自動化フラグ隠し(playwright起動引数)では回避できなかった
- DOMの `full_text` は途中で切れる。全文はGraphQLの `note_tweet.note_tweet_results.result.text`。
  横取りが0件の間、長文ポスト(「さらに表示」付き)はDOM経由だと途中までしか取れていない可能性がある
  → 長文と分かったポストは個別に `TweetDetail` を開いて取るか、GraphQL横取りを直すのが残タスク
- ユーザー名のスキーマは2系統併存: `core.user_results.result.core.screen_name`(新) / `...result.legacy.screen_name`(旧)。両対応で読む
- x.comのタブを残したままにするとCPUを食い続けることがある → 自分のタブは必ず閉じる
