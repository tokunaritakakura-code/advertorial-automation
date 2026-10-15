# レシピ: Instagram

## 最速経路(ZeroGuri Trackerで実証済みの機械経路)
- プロフィール+直近投稿(~24件, 未認証可): `https://www.instagram.com/api/v1/users/web_profile_info/?username=<name>`
  (ヘッダ `x-ig-app-id: 936619743392459` が必要)
- 投稿詳細のJSON: `https://i.instagram.com/api/v1/...` 系フィードエンドポイント
- embed scraping は死んでいる(2026時点)

## ブラウザ経路(上のAPIで足りない時)
統一プロファイルでログインし、Xと同様に `/graphql/query` 応答を横取り。
リール・ストーリーズはログイン必須。

## 落とし穴
- IGはIPブロックが強め(ZeroGuriで障害実績あり)。連打しない・失敗時は間隔を空ける
- 画像が本体のプラットフォームなので、学習用途では投稿画像もDLしてキャプションと組で読む(二重符号化)
