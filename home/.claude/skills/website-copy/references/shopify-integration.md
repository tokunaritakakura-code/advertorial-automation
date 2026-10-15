# Shopify連携（アップロード・公開）

Shopify MCP（claude.ai Shopify）を使う。**接続確認**は `get-shop-info`。別ストアなら `switch-shop`→再認証。

## テーマ戦略（既存デザインを壊さない）

- 完コピは**非公開テーマ**に入れる。ライブテーマ（MAIN）には絶対に直接書かない。
- MCPの制約（安全仕様・回避不可）:
  - **ライブ(MAIN)テーマへのファイル書き込みはブロック**される
  - **テーマの公開もブロック**される
- テーマ一覧: `graphql_query { themes(first:20){ nodes{ id name role } } }`
- 素URLで完コピを出したい時は「ライブをブラウザで複製 → 複製に注入 → 複製を公開」。複製と公開はブラウザ操作（task-fleet）でユーザーのクリックを挟む。**プレビュー確認だけなら公開不要**。

## アップロード手順（3ステップ・実証済み）

テーマファイルの内容をコンテキストに通さずに上げる。`body type: URL` を使うのがポイント。

1. **staged upload枠を作る**（MCP `graphql_mutation`）。theme/内の全ファイル名を渡す:
   ```graphql
   mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
     stagedUploadsCreate(input: $input) {
       stagedTargets { url resourceUrl parameters { name value } }
       userErrors { field message }
     } }
   ```
   variables: 各ファイルを `{resource:"FILE", filename:"<name>", mimeType:"text/plain", httpMethod:"POST"}`
2. **GCSへPOST**（スクリプト）: 返ってきた stagedTargets を JSON ファイルに保存し、
   `node scripts/upload-gcs.mjs <targets.json> <outdir>/theme` を実行。全ファイルが `201` を返せばOK。
3. **テーマに取り込む**（MCP `graphql_mutation`）。resourceUrl を body type URL で:
   ```graphql
   mutation themeFilesUpsert($themeId: ID!, $files: [OnlineStoreThemeFilesUpsertFileInput!]!) {
     themeFilesUpsert(themeId:$themeId, files:$files) { job{ id done } userErrors{ field message } } }
   ```
   files: `{filename:"snippets/<name>.liquid", body:{type:"URL", value:"<resourceUrl>"}}`。
   テンプレートは `templates/product.<suffix>.liquid` として同様に。

## 商品の作成とテンプレート割り当て

1. `create-product`（status:DRAFT）で商品を作る（価格は元ページのAOVでよい）。
2. テンプレート割り当て（MCP `graphql_mutation`）:
   ```graphql
   mutation productUpdate($product: ProductUpdateInput!) {
     productUpdate(product:$product){ product{ id handle onlineStorePreviewUrl } userErrors{ field message } } }
   ```
   variables: `{product:{id:"gid://...Product/ID", templateSuffix:"<suffix>"}}`
3. **プレビュー表示の注意**: API作成商品は販売チャネル未公開がデフォルト。素のストアフロントで見るには
   status を ACTIVE にし、オンラインストアচ販売チャネルへ `publishablePublish` する（プレビューだけなら onlineStorePreviewUrl を使う）。
   - オンラインストアの publicationId は `graphql_query { publications(first:10){ nodes{ id name } } }` で取得。
   - `?preview_theme_id=<非公開テーマの数値ID>` を付ければ、そのテーマでのレンダリングを確認できる。

## 検証（答え合わせループ）

```
bash scripts/screenshot.sh "<元URL>"                 out/orig.png
bash scripts/screenshot.sh "<プレビューURL>"          out/clone.png
/usr/bin/python3 scripts/diff.py out/orig.png out/clone.png
```
差分が大きい帯を特定 → 原因（多くはJS動的要素の焼き込み漏れ）を直して bake→chunk→再アップロード。
残差は動画の再生フレーム・カウントダウン秒など**構造的に一致不能なランタイム要素**（無視してよい）。
