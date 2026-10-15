#!/bin/zsh
# 朝の見張り／週1の本走を「走るべき時が過ぎていて、まだ走っていなければ走る」形で回す。
#
# launchd の時刻ぴったりの起動に加えて、15分おきにもこれが呼ばれる。
# 寝ていて 6:50 を逃した日は、Mac が起きた最初の15分以内にここが気づいて走らせる
# （本人 2026-09-22「パソコンが動いた瞬間に動かしてすぐ送って欲しい」）。
# 走る条件を満たしていない時は、何もせず 0 で戻る（1日に何回呼ばれても1回しか走らない）。
#
# 使い方: asa.sh 見張り   （毎日 6:50 以降・1日1回）
#         asa.sh 本走     （月曜 6:30 以降・1週に1回）
set -u
種類="${1:?見張り か 本走}"
HERE="${0:A:h}"
印="$HERE/state/最後に走った-$種類.txt"
PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH

case "$種類" in
  見張り) 刻=0650; 期="$(date +%Y-%m-%d)" ;;                 # 1日1回
  本走)   刻=0630; 期="$(date -v-mon +%Y-%m-%d)" ;;          # その週の月曜の日付＝1週1回
  *) print -u2 "種類は 見張り か 本走"; exit 2 ;;
esac

今=$(date +%H%M)
[[ "$今" < "$刻" ]] && exit 0                                 # まだその時刻になっていない
[[ -f "$印" && "$(cat "$印")" == "$期" ]] && exit 0            # もう走った

# claude が無い環境（PATHが壊れた・入れ替え中）で空振りしない
if ! command -v claude >/dev/null; then
  print -u2 "claude が見つからない（PATH=$PATH）。走らせずに終わる"
  exit 3
fi

mkdir -p "$HERE/state"
print -r -- "$(date '+%Y-%m-%d %H:%M') $種類 を走らせる（印=$期）" >&2
if [[ "$種類" == "見張り" ]]; then
  claude -p "/vsl-sagasu 見張り" --permission-mode bypassPermissions
else
  claude -p "/vsl-sagasu" --permission-mode bypassPermissions
fi
結果=$?
# 走り切った時だけ印を付ける。落ちた時は付けないので、15分後にもう一度試す
[[ $結果 -eq 0 ]] && print -r -- "$期" > "$印"
exit $結果
