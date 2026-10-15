#!/bin/bash
# 型を1本コピーして、新しいアドバトリアルの作業場を作る。
# 使い方: ./新規.sh <型の番号> <商品> <角度の短い名前>
#   例:   ./新規.sh A01 アルコット 夕方
set -e
KATA="$1"; SHOHIN="$2"; KAKUDO="$3"
[ -z "$KAKUDO" ] && { echo "使い方: ./新規.sh <型の番号> <商品> <角度>"; exit 1; }

VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/ec"
[ -d "$VAULT" ] || VAULT="$HOME/Documents/Obsidian Vault/ec"
SRC="$HOME/Claude Code/arukoto-store/adv/index.bak-preoffer-2026-09-06.html"   # 型のCSSの元
OUT="$HOME/Desktop/ec/$SHOHIN/08 記事/02 HTML/${SHOHIN}記事_${KATA}_${KAKUDO}_v1"
MD="$VAULT/$SHOHIN/08 記事/09 $KATA-$KAKUDO"

mkdir -p "$OUT/img" "$OUT/vid" "$MD"
# CSSだけ取り出して、空の記事の殻を置く
sed -n '1,136p' "$SRC" > "$OUT/_殻.html"
echo "</head><body><div class=\"mlnroot\"><div class=\"mlnwrap\"><div class=\"mlnadv\">" >> "$OUT/_殻.html"
echo "<!-- ここに本文 -->" >> "$OUT/_殻.html"
echo "</div></div></div></body></html>" >> "$OUT/_殻.html"

KATA_DIR=$(ls -d "$VAULT/構造/型/$KATA"* 2>/dev/null | head -1)
cat > "$MD/01 移植表.md" <<EOF
# $SHOHIN｜$KATA × $KAKUDO（v1・$(date +%Y-%m-%d)）

読む人: この記事を直す人。
読む時: 本文を直す前。
読まなくていい条件: 別の角度の記事をさわる回。

型の正本: \`${KATA_DIR#$VAULT/}/_分解.md\`。実物: \`$OUT/index.html\`。

## 10個の問い（埋まるまで書き始めない）

| # | 問い | 答え |
|---|---|---|
| 1 | 痛みと、強くなる時刻 | |
| 2 | 試した物と金額 | |
| 3 | 専門家の終わらせ方 | |
| 4 | **全部に共通する1つ** | |
| 5 | 詰まっている入り口 | |
| 6 | 別の入り口と名前 | |
| 7 | 通れる物の条件 | |
| 8 | 客が自分で確かめる物差し | |
| 9 | 恐怖の核 | |
| 10 | 買うのが本人でない場合 | |

## 塗り（広告を15の事で塗る。◎言い切った／○名前だけ／△匂わせ／×言っていない。正本 構造/型/_買うまでの15の事.md）

| 事 | 印 | 根拠（秒） |
|---|---|---|
$(for k in ① ② ③ ④a ④b ⑤ ⑥ ⑦ ⑧ ⑨ ⑩ ⑪ ⑫ ⑬ ⑭ ⑮; do echo "| $k | | |"; done)

## 見終わった人の状態（根拠に広告の秒。段階と今の気持ち以外）

| 状態の欄 | 中身 | 根拠（秒） |
|---|---|---|
| 段階 | | |
| 信じた事 | | |
| 残った疑い | | |
| 今の気持ち | | |
| 広告の構造 | | |
| 開けた穴 | | |

## 型の候補（2〜3個を比べてから選ぶ。正本 構造/型/_VSLから型を選ぶ.md の決め方3）

| 候補 | 題 | 入りの1行 | 受ける疑い |
|---|---|---|---|

選んだ:

## 穴のつなぎ（受けた穴は閉じず、段の終わりで次の穴を開ける。# 1 から最後の1つ前まで）

| 段 | 受ける穴 | 開ける次の穴 |
|---|---|---|

## 受け渡し（広告が渡した問いを、どの段が受けるか。1つは # 0 か 1 で受ける）

| 渡した問い | 受ける段 |
|---|---|

## 移植表（ボタンの位置は右の列に「CTA①」と丸数字で書く）

| # | 段 | 参考 | $SHOHIN |
|---|---|---|---|
EOF
echo "作業場を作った:"
echo "  文字  $MD/01 移植表.md"
echo "  実物  $OUT/（_殻.html にCSSだけ入っている）"
echo "  型    ${KATA_DIR:-（見つからず）}/_分解.md を左の列にする"
