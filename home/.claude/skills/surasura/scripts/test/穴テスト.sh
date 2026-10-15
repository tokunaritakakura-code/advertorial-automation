#!/bin/bash
# dia の10個の穴を実際に踏んで、塞がっているか確かめる。
# 使い方: bash ~/.claude/skills/surasura/scripts/test/穴テスト.sh
cd "$(dirname "$0")/.." || exit 1
P="file://$(cd "$(dirname "$0")" && pwd)/穴テスト.html"
D="node dia.mjs"
ok=0; ng=0
判定() { # 判定 <題> <期待する文字> <実際の出力>
  if echo "$3" | grep -q "$2"; then echo "  通った  $1"; ok=$((ok+1));
  else echo "  落ちた  $1"; echo "        期待:$2"; echo "        実際:$(echo "$3"|head -2|tr '\n' ' ')"; ng=$((ng+1)); fi
}
$D daemon stop >/dev/null 2>&1; sleep 1
$D close --tab 穴テスト >/dev/null 2>&1

echo "── 重なり(オーバーレイ有り) ──"
$D open "$P#overlay" >/dev/null 2>&1; sleep 1
判定 "1 オーバーレイの下は押せないと返す" "押せない" "$($D click "A 普通のボタン" --tab 穴テスト 2>&1)"

echo "── 通常(オーバーレイ無し) ──"
$D nav "$P" --tab 穴テスト >/dev/null 2>&1; sleep 1
L=$($D look --tab 穴テスト --max 60 2>&1)
判定 "2 disabled に印が付く"            "B disabled.*✗disabled"  "$L"
判定 "4 addEventListenerのdivが出る"     "D divにaddEventListener" "$L"
判定 "5 role=switch が出る"              "E role=switch"           "$L"
判定 "6 closed shadow の中が出る"        "J closed shadow内"       "$L"
判定 "3 pointerdownだけの要素が反応する" "変化"                    "$($D click "G pointerdownしか見ない" --tab 穴テスト 2>&1)"
判定 "7 confirm を掴んで知らせる"        "confirm"                 "$($D click "F confirmが出る" --tab 穴テスト 2>&1)"
$D dialog dismiss --tab 穴テスト >/dev/null 2>&1
判定 "7b ダイアログの後に次が通る"       "A 普通のボタン"          "$($D look --tab 穴テスト --max 3 2>&1)"
判定 "8 新しいタブが開いたと返す"        "新しいタブが開いた"      "$($D click "H 新しいタブを開く" --tab 穴テスト 2>&1)"
判定 "10 曖昧なラベルは押さない"         "決まらない"              "$($D click "公開" --tab 穴テスト --force 2>&1)"
判定 "10b 完全一致が1つなら押す"        "OK click"                "$($D click "保存" --tab 穴テスト 2>&1)"
判定 "11 戻せない操作を止める"           "止めた"                  "$($D click "保存して公開" --tab 穴テスト --force 2>&1; $D click "保存して公開" --tab 穴テスト 2>&1)"

A=$($D look --tab 穴テスト --max 60 2>&1 | grep "A 普通のボタン")
$D look --tab 穴テスト >/dev/null 2>&1
B=$($D look --tab 穴テスト --max 60 2>&1 | grep "A 普通のボタン")
N=$(echo "$A"|sed "s/^\[//;s/\].*//")
M=$(echo "$B"|sed "s/^\[//;s/\].*//")
判定 "9 番号が3回のlookで変わらない" "^$N\$" "$M"

$D close --tab about:blank >/dev/null 2>&1
echo; echo "通った $ok / 落ちた $ng"
[ "$ng" -eq 0 ]
