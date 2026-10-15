#!/usr/bin/env python3
"""勝った広告を広告タイプ別に並べ、まだ借りていない物だけ残して、判断の1枚と参考の箱に書く。

入力は Claude が MCP から取って保存した JSON（このスクリプトは外を叩かない）。
判断（どれを借りるか）は人とClaudeがやる。ここは並べ方・線引き・重複の除外だけを決定的にやる。

使い方:
  python3 erabu.py --自社 jisha.json --hookd hookd.json          # 試し（画面に出すだけ）
  python3 erabu.py --自社 jisha.json --hookd hookd.json --書く   # Vault に書く
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daicho  # noqa: E402

VAULT_KATA = os.path.expanduser("~/Documents/Obsidian Vault/ec/構造/型")
KACHI = os.path.join(VAULT_KATA, "_勝ち一覧.md")
HAKO = os.path.expanduser("~/Documents/Obsidian Vault/ec/構造/毎日の制作/_参考の箱.md")

# 線引き（ここだけ直せば全部変わる。本人 2026-09-22「3以上でも全然高い」）
ROAS線 = 3.0
最低支出 = 20000      # 円。これ未満は学習が足りないので順位に入れない
最低購入 = 10         # 件。獲得単価¥5,000前後だと5件は1日分で、ROASが跳ねているだけになる
上位 = 3              # タイプごとに何本出すか
# AIで作った動画を多めに、VSL着地は少なめに（本人 2026-09-23「AIの割合を高くして」）
タイプ別の上位 = {"H-ai": 12, "H-vsl": 1}   # 2026-09-30 6→12（夜の台本で1晩6本使う）
HOOKD最低点 = 81      # optimized 以上
HOOKD最低秒 = 60      # VSL らしい長さ

# 広告タイプ（機械の見分け。当たらない物は「見て決める」に落ちる）
タイプ表 = [
    # ワンドライは名前に clay が入らない。オリジナル08・W115 は画でクレイと確認（2026-09-28）
    ("V-clay",  "動画・クレイ（粘土）",      "動画", r"clay|cray|粘土|クレイ|オリジナル08|w115"),  # クレイ物語（ワンドライ 2026-10-12 の記事B/D 動画。名前で判定 2026-10-13）
    # メラオの番号だけの広告（3-1 3-5 等）は creative の名前が訴求文になっていて種類が入らない。
    # T09 の分解で「3DCGの体の絵が9割」と実測済みなので、この訴求文を3DCGとして扱う（2026-09-22）
    ("V-anime", "動画・3DCG/アニメ",         "動画", r"アニメ|3dcg|3d|cg|私が神経痛を治した方法|私が足のむくみから解放された方法|w116|w124|スケルトン|zackd"),  # スケルトン＝骸骨の3DCG、ZackDFilms／ZackD POV＝線画アニメ（ワンドライ 2026-10-12 の記事A〜D 動画。名前で判定 2026-10-13）  # W116 は骸骨の犬の3DCG（2026-09-28 画で確認）。W124 は白黒の線画アニメの犬（2026-09-30 画で確認）
    # オリジナル09・W107 は専門家の顔出しが喋る（同じ動画。2026-09-28 画で確認）
    ("V-hito",  "動画・人が喋る",            "動画", r"ugc|対談|heygen|インタビュー|証言|オリジナル09|w107|権威実写"),  # 権威実写＝役だけの1人が顔出しで喋る（ワンドライ 2026-10-12 の記事A/D 動画。名前で判定 2026-10-13）
    # オリジナル11・W109 はAIの実写風素材＋字幕（同じ動画。2026-09-28 画で確認）
    # W119 W120 W121 W125 W126 もAIの実写風の犬と部屋＋赤帯の字幕（2026-09-30 画で確認）
    ("V-vsl",   "動画・VSL（声＋素材）",     "動画", r"vsl|オリジナル11|w109|w119|w120|w121|w125|w126"),
    # W128 はスマホのメモ画面の形（2026-09-30 画で確認）
    ("S-ugc",   "静止画・UGC/手書き",        "静止画", r"ugc|手書き|メモ|手紙|w128"),
    # ワンドライの Static Ads は名前に「比喩」が入らない。06 床スポンジは画で比喩1枚と確認（2026-09-23）
    # W104 スポンジの床・W105 迷路・W106 磁石・0919_b6 砂利道の足裏（2026-09-30 画で確認）
    ("S-hiyu",  "静止画・比喩1枚",           "静止画", r"比喩|スポンジ|磁石|w104|w105|w106|砂利道左右比較"),
    # メラオの静止画の名前の付け方。S1_ S4_ … と T8_ T9_ T10_ の2系統がある（2026-09-22 実測）
    # ワンドライの Static Ads 01〜05 はまとめ買いの商品写真・W127 W129 は文字＋写真（2026-09-30 画で確認）
    # オリジナルVSL06 は獣医師の写真＋赤帯の見出し「しつけは意味ない3つの理由」の1枚（2026-10-12 画で確認。名前は VSL だが SHARE の静止画）
    ("S-static", "静止画・その他",           "静止画", r"(^|\s)[st]\d+_|_static_|static ads|(^|\s)static \d|w127|w129|オリジナルvsl06"),  # ワンドライ旧「static 1〜3｜首こり整体ループ」は商品写真＋本文330字（2026-10-13 本文を読んで確認）
    # JSON に本文を残さないので本文の長さで決まらない。名前で拾う（久美子_ はメラオのネイティブ。2026-09-28 本文4,000字超を確認）
    ("N-native", "ネイティブ広告（長文＋記録風1枚）", "静止画", r"native ads|久美子_|melao_腕_|塩ラップ|主力b mechanism|cr[⑥⑦]"),  # ワンドライ旧 native 1〜3（主力B Mechanism CT矢印・CR⑥・CR⑦）＝耳鳴りの仕組みの長文 500〜900字（2026-10-13 本文を読んで確認）  # 腕_前腕に塩ラップ＝本文4,300字の一人称の記録（2026-10-12 本文を読んで確認）
]


def 読み込む(path):
    """JSON を1本読む。壊れていたら、どのファイルのどこが壊れているかを言って落ちる。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"入力が無い: {path}。Step 1 か Step 2 をやり直す")
    except json.JSONDecodeError as e:
        raise SystemExit(f"入力が壊れている: {path} の {e.lineno}行{e.colno}文字目 ({e.msg})。書き直す")


def 円(v):
    """'¥229,375 JPY' → 229375.0。数でも文字でも受ける。取れなければ None。"""
    if isinstance(v, dict) and "value" in v:   # MCP meta-ads は {"value":"338791","unit":"JPY"} で返す（2026-09-25 実測）
        v = v["value"]
    if v is None or isinstance(v, (list, dict)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.sub(r"[^\d.]", "", str(v))
    return float(m) if m else None


def 数(v):
    """数に直す。配列や辞書（生APIの形）が来たら None を返す ＝ 形が変わった印。"""
    if v in (None, "", "null") or isinstance(v, (list, dict)):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def リンク(ad, アカウント=""):
    """スマホで押したら開くリンクを1本作る。優先順は実測で決めた（2026-09-22 いずれも200）。

    1. 投稿そのもの（`effective_object_story_id` = <ページID>_<投稿ID>）。動画も静止画も開く
    2. 動画だけ: リール（`https://www.facebook.com/reel/<video_id>/`）
    3. どちらも無い時: 広告の管理画面（PCでしか見ない）
    """
    story = str(ad.get("effective_object_story_id") or "")
    if "_" in story:
        ページ, 投稿 = story.split("_", 1)
        return f"https://www.facebook.com/{ページ}/posts/{投稿}"
    vid = str(ad.get("video_id") or "")
    if vid:
        return f"https://www.facebook.com/reel/{vid}/"
    if アカウント:
        return (f"https://adsmanager.facebook.com/adsmanager/manage/ads"
                f"?act={アカウント}&selected_ad_ids={ad.get('id','')}")
    return ""


def 動画か(ad):
    """動画か静止画かを2つの証拠で決める。片方しか無い時はある方を使う。"""
    ot = (ad.get("object_type") or "").upper()
    plays = 数(ad.get("video_play_actions"))
    if ot == "VIDEO" or (plays is not None and plays > 0):
        return "動画"
    if ot in ("SHARE", "PHOTO", "LINK") or plays is None:
        return "静止画"
    return "見て決める"


def タイプ判定(ad):
    媒体 = 動画か(ad)
    名 = f"{ad.get('name','')} {ad.get('creative_name','')}".lower()
    for code, 呼び名, 要る媒体, 正規 in タイプ表:
        if 媒体 == 要る媒体 and re.search(正規, 名):
            return code, 呼び名
    if 媒体 == "静止画" and len(ad.get("body") or "") >= 300:
        return "N-native", "ネイティブ広告（長文＋記録風1枚）"
    if 媒体 == "動画":
        return "V-nazo", "動画・見て決める"
    if 媒体 == "静止画":
        return "S-nazo", "静止画・見て決める"
    return "nazo", "見て決める"


def 入口の検査(出どころ, 広告, 必須):
    """形が変わった入力を「候補なし」と取り違えないための門。

    1本も無い・鍵が空・必須の数が全行 None のどれかなら、その場で落とす。
    """
    if not 広告:
        raise SystemExit(f"{出どころ}: 広告0本。本当に0本なのか取得に失敗したのかを先に切り分ける")
    空鍵 = [a.get("name", "?") for a in 広告 if not str(a.get("id") or "").strip()]
    if 空鍵:
        raise SystemExit(f"{出どころ}: 鍵（id）が空の行が {len(空鍵)}本 ある（{空鍵[:3]}）。"
                         '取り直す時は fields に "id" を入れる')
    for 欄 in 必須:
        # 金額は "¥229,405 JPY" の形で返る。数() では読めないので 円() で見る（2026-09-22）
        読む = 円 if 欄 == "amount_spent" else 数
        if all(読む(a.get(欄)) is None for a in 広告):
            raise SystemExit(f"{出どころ}: {欄} が全行 空か配列。APIの返りの形が変わっている。"
                             "ads_get_field_context で欄の名前を確かめる")


def 自社を並べる(data, 済み):
    出どころ = data.get("出どころ", "自社")
    アカウント = str(data.get("アカウント", ""))
    広告 = data.get("広告", [])
    入口の検査(出どころ, 広告, ["amount_spent", "impressions", "purchase_roas"])
    out = []
    for ad in 広告:
        支出 = 円(ad.get("amount_spent")) or 0.0
        roas = 数(ad.get("purchase_roas")) or 0.0
        購入 = 数(ad.get("omni_purchase")) or 0.0
        imp = 数(ad.get("impressions")) or 0.0
        p25 = 数(ad.get("video_p25_watched_actions"))
        p100 = 数(ad.get("video_p100_watched_actions"))
        code, 呼び名 = タイプ判定(ad)
        鍵 = str(ad["id"]).strip()
        理由 = []
        if 支出 < 最低支出:
            理由.append(f"支出{int(支出):,}円<{最低支出:,}")
        if 購入 < 最低購入:
            理由.append(f"購入{int(購入)}件<{最低購入}")
        if roas < ROAS線:
            理由.append(f"ROAS{roas:.2f}<{ROAS線}")
        out.append({
            "出どころ": 出どころ, "外か": False, "鍵": 鍵,
            "名前": ad.get("name", ""),
            "タイプ": code, "タイプ名": 呼び名,
            "ROAS": round(roas, 2), "支出": int(支出), "購入": int(購入),
            "獲得単価": int(支出 / 購入) if 購入 else None,
            "到達率": round(p25 / imp * 100, 1) if (p25 and imp) else None,
            "残り率": round(p100 / p25 * 100, 1) if (p25 and p100) else None,
            "点": None, "秒": None, "配信日数": None, "台本字数": None,
            "借りた": 鍵 in 済み,
            "落ちた理由": "・".join(理由),
            "参考": リンク(ad, アカウント), "ライブラリ": "",
        })
    return out


def _掘る(ad, *道):
    """`transcript` でも `transcripts.0.content` でも読めるようにする（頼み方のブレを吸う）。"""
    for 鍵 in 道:
        v = ad
        for k in 鍵.split("."):
            if isinstance(v, list):
                v = v[int(k)] if k.isdigit() and len(v) > int(k) else None
            elif isinstance(v, dict):
                v = v.get(k)
            else:
                v = None
            if v is None:
                break
        if v not in (None, "", []):
            return v
    return None


def hookdを並べる(data, 済み):
    広告 = data.get("広告", [])
    入口の検査("gethookd", 広告, ["performance_score", "video_length_seconds"])
    out = []
    for ad in 広告:
        点 = 数(_掘る(ad, "performance_score")) or 0
        秒 = 数(_掘る(ad, "video_length_seconds", "media.0.video_length_seconds")) or 0
        日 = 数(_掘る(ad, "days_active")) or 0
        台本 = str(_掘る(ad, "transcript", "transcripts.0.content") or "")
        落とす動画 = _掘る(ad, "download_url") or ""
        ブランド = _掘る(ad, "brand", "brand.name") or ""
        if isinstance(ブランド, dict):
            ブランド = ブランド.get("name", "")
        鍵 = str(ad["id"]).strip()
        枠 = _掘る(ad, "枠") or "VSL着地"
        理由 = []
        if 点 < HOOKD最低点:
            理由.append(f"点{int(点)}<{HOOKD最低点}")
        if 秒 < HOOKD最低秒:
            理由.append(f"{int(秒)}秒<{HOOKD最低秒}")
        # 台本は分解する時に download_url から whisper で作る（無料）。ここでは求めない
        out.append({
            "出どころ": "gethookd", "外か": True, "鍵": 鍵,
            "名前": f"{ブランド}｜{str(_掘る(ad, 'title') or '')[:24]}",
            "タイプ": "H-ai" if 枠 == "AI" else "H-vsl",
            "タイプ名": ("GetHookd・AIで作った動画" if 枠 == "AI"
                     else f"GetHookd・VSL（{_掘る(ad, 'page_type') or '着地不明'}）"),
            "ROAS": None, "支出": None, "購入": None, "獲得単価": None,
            "到達率": None, "残り率": None,
            "点": int(点), "秒": int(秒), "配信日数": int(日), "台本字数": len(台本),
            "動画": 落とす動画,
            "借りた": 鍵 in 済み,
            "落ちた理由": "・".join(理由),
            # 1本目 = GetHookd の共有ページ（ログイン無しで開くのを2026-09-22に実測）
            "参考": _掘る(ad, "share_url") or "",
            # 2本目 = Meta の広告ライブラリ。共有ページが切れた時の逃げ道
            "ライブラリ": (f"https://www.facebook.com/ads/library/?id={_掘る(ad, 'external_id')}"
                      if _掘る(ad, "external_id") else ""),
        })
    return out


def 候補を選ぶ(rows):
    """タイプごとに、線を越えていて・まだ台帳に無い物の上位N本。

    線を越えた中では、たくさん回っている物ほど型として確か。
    ROAS で並べると ¥23,000・6件の広告が ¥744,000・85件の広告より上に来る（2026-09-22 実測）。
    """
    候補 = []
    for code in sorted({r["タイプ"] for r in rows}):
        中 = [r for r in rows if r["タイプ"] == code and not r["落ちた理由"] and not r["借りた"]]
        中.sort(key=lambda r: (r.get("支出") or 0, r.get("点") or 0, r.get("配信日数") or 0), reverse=True)
        候補 += 中[:タイプ別の上位.get(code, 上位)]
    return 候補


def _欄(v, 形="{}"):
    """測っていない（None）だけを — にする。0 は 0 と出す。"""
    return "—" if v is None else 形.format(v)


def _名(r):
    """広告の名前を押せる形にする。スマホで押すとFBの投稿かGetHookdが開く。

    リンクを名前の中に入れる（URLを名前の後ろに裸で置くと、括弧までリンクに食われる）。
    """
    名 = r["名前"].replace("|", "｜").replace("[", "［").replace("]", "］")
    return f"[{名}]({r['参考']})" if r.get("参考") else 名


# ---------- 参考の箱 ----------

def 箱の範囲(lines):
    """`### 箱` の見出しから次の見出しまで。表の位置を日付の形で探さない。"""
    始め = next((i for i, l in enumerate(lines) if l.strip().startswith("### 箱")), None)
    if 始め is None:
        raise ValueError(f"参考の箱に `### 箱` の見出しが無い: {HAKO}。見出しの形が変わっている")
    終わり = next((i for i in range(始め + 1, len(lines)) if lines[i].startswith("#")), len(lines))
    return 始め, 終わり


def 箱の鍵(lines, 始め, 終わり):
    """箱の「参考」の欄にある6桁以上の数字だけを鍵として拾う（全文の部分一致にしない）。"""
    鍵 = set()
    for l in lines[始め:終わり]:
        if not l.startswith("|"):
            continue
        cells = [c.strip() for c in l.split("|")]
        if len(cells) < 3 or cells[1].startswith("-") or cells[1] == "入れた日":
            continue
        鍵 |= set(re.findall(r"(?<!\d)(\d{6,})(?!\d)", cells[2]))
    return 鍵


def 箱に足す行(候補, 今日):
    """書き込む前に、足す行と入れる場所を先に決める。ここで落ちれば Vault は1文字も変わらない。"""
    if not os.path.exists(HAKO):
        raise FileNotFoundError(f"参考の箱が無い: {HAKO}")
    lines = open(HAKO, encoding="utf-8").read().splitlines()
    始め, 終わり = 箱の範囲(lines)
    既存 = 箱の鍵(lines, 始め, 終わり)
    最後 = None
    for i in range(始め, 終わり):
        if lines[i].startswith("|"):
            最後 = i
    if 最後 is None:
        raise ValueError(f"`### 箱` の下に表が無い: {HAKO}")
    足す = []
    for r in 候補:
        if not r["鍵"] or r["鍵"] in 既存:
            continue
        見出し = (f"広告ID {r['鍵']}（{r['出どころ']}・{r['名前']}）" if not r["外か"]
                  else f"{r['名前']}（gethookd {r['鍵']}）")
        参考 = f"[{見出し.replace('[', '［').replace(']', '］')}]({r['参考']})" if r["参考"] else 見出し
        足す.append(f"| {今日} | {参考} |  |  | 待ち |  |")
    return lines, 最後, 足す


def 箱を書く(lines, 最後, 足す):
    if not 足す:
        return 0
    lines[最後 + 1:最後 + 1] = 足す
    tmp = HAKO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, HAKO)
    return len(足す)


# ---------- 勝ち一覧 ----------

def 一覧を書く(全部, 候補, 期間, 取得):
    L = []
    # 先頭の <!-- 例 --> は check-undug.py の印。`ec/構造/` の下でも「型ではなく実物の一覧」と伝える
    L.append("<!-- 例 -->\n")
    L.append("# 勝ち一覧（借りていない勝ち広告だけ）\n")
    L.append("読む人: 次にどの構造を借りるか決める本人と、台本を書く係。")
    L.append("読む時: 週のはじめ。新しい参考が要る時。")
    L.append("読まなくていい条件: 借りる型がもう決まっている時（`_一覧.md` と `T<番号>/_分解.md` を見る）。\n")
    L.append(f"数字の窓: **{期間}**。取得 {取得}。`/vsl-sagasu` が毎回この1枚を上書きする。\n")
    L.append("## 一行で\n")
    L.append(f"**広告タイプごとに、線を越えていて・まだ台帳に無い物を上位{上位}本まで出す。"
             f"自社の線は ROAS {ROAS線} 以上・支出 {最低支出:,}円 以上・購入 {最低購入} 件以上。"
             f"GetHookd の線は {HOOKD最低点}点以上・{HOOKD最低秒}秒以上・台本あり。**\n")

    内 = [r for r in 候補 if not r["外か"]]
    外 = [r for r in 候補 if r["外か"]]

    L.append("## 次に借りる候補 — 自社（実績あり）\n")
    if 内:
        L.append("| 出どころ | 広告タイプ | 広告 | ROAS | 獲得単価 | 支出 | 購入 | 25%到達率（3秒の代用） | 残り率 | 鍵 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in 内:
            L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | `{}` |".format(
                r["出どころ"], r["タイプ名"], _名(r),
                _欄(r["ROAS"], "{:.2f}"), _欄(r["獲得単価"], "¥{:,}"),
                _欄(r["支出"], "¥{:,}"), _欄(r["購入"], "{}件"),
                _欄(r["到達率"], "{}%"), _欄(r["残り率"], "{}%"), r["鍵"]))
    else:
        L.append("候補なし。線を越えていて台帳に無い自社の広告が1本も無い。")
    L.append("")

    L.append("## 次に借りる候補 — GetHookd（実績は見えない）\n")
    L.append("**出稿額もROASも見えない。点は GetHookd の推定で、うちの ROAS とは別の物差し。**\n")
    if 外:
        L.append("| 広告タイプ | 広告（押すと開く） | 点 | 尺 | 配信日数 | 動画 | 広告ライブラリ | 鍵 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in 外:
            L.append("| {} | {} | {} | {} | {} | {} | {} | `{}` |".format(
                r["タイプ名"], _名(r), _欄(r["点"], "{}点"), _欄(r["秒"], "{}秒"),
                _欄(r["配信日数"], "{}日"),
                ("落とせる" if r.get("動画") else ("台本 " + f'{r["台本字数"]:,}字' if r["台本字数"] else "—")),
                f"[ライブラリ]({r['ライブラリ']})" if r.get("ライブラリ") else "—", r["鍵"]))
    else:
        L.append("候補なし。")
    L.append("")

    見て決める = [r for r in 全部 if r["タイプ"].endswith("nazo")]
    L.append("## 画を見て広告タイプを決める\n")
    if 見て決める:
        L.append("**この表が空になるまで検査は通らない。** 画を開いて決め、"
                 "`erabu.py` の `タイプ表` に見分けの語を1行足してから、もう一度走らせる。\n")
        L.append("| 出どころ | 広告 | 見る所 |")
        L.append("|---|---|---|")
        for r in 見て決める:
            L.append(f"| {r['出どころ']} | {_名(r)} | {r['参考'] or '—'} |")
    else:
        L.append("無し。全部の広告タイプが機械で決まっている。")
    L.append("")

    L.append("## 全部（線に届かなかった物と、もう台帳にある物）\n")
    L.append("| 出どころ | 広告タイプ | 広告 | ROAS／点 | 支出 | 状態 |")
    L.append("|---|---|---|---|---|---|")
    選ばれた = {id(r) for r in 候補}
    for r in sorted(全部, key=lambda r: (r["出どころ"], r["タイプ"], -(r.get("ROAS") or r.get("点") or 0))):
        if r["借りた"]:
            状態 = "台帳にある（借りた／見送った）"
        elif r["落ちた理由"]:
            状態 = r["落ちた理由"]
        elif id(r) in 選ばれた:
            状態 = "候補"
        else:
            状態 = f"線は越えたが同じタイプの{タイプ別の上位.get(r['タイプ'], 上位)}位まで入らなかった"
        L.append("| {} | {} | {} | {} | {} | {} |".format(
            r["出どころ"], r["タイプ名"], _名(r),
            _欄(r["点"], "{}点") if r["外か"] else _欄(r["ROAS"], "{:.2f}"),
            _欄(r["支出"], "¥{:,}"), 状態))
    L.append("")

    L.append("## 測れないもの\n")
    L.append("| 何 | なぜ |")
    L.append("|---|---|")
    L.append("| 3秒再生率 | Meta の広告APIに3秒の欄が無い（2026-09-22 実測）。25%到達率で代用しているので、尺が短い広告ほど甘く出る |")
    L.append("| GetHookd 側の出稿実績 | 出稿額もROASも見えない。点と配信日数が代わり |")
    L.append("| うちのJP広告の映像・台本（GetHookd経由、MCP `gethookd` の `search_ads`） | 索引に入っていない（2026-09-22 実測・0件） |")
    L.append("| ROAS の真偽 | Meta の申告値。Shopify の実売と一致しない |")
    L.append("| 「AIで作ったか」 | GetHookd のタグが動画に付いていない。0/1/3秒の画を見て決める |")
    L.append("")

    os.makedirs(VAULT_KATA, exist_ok=True)
    tmp = KACHI + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    os.replace(tmp, KACHI)
    return KACHI


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--自社", action="append", default=[], help="Meta から取った JSON。複数可")
    p.add_argument("--hookd", default=None, help="GetHookd から取った JSON")
    p.add_argument("--期間", default="Meta last_30d", help="勝ち一覧の見出しに出す数字の窓")
    p.add_argument("--書く", action="store_true", help="Vault に書く（既定は画面に出すだけ）")
    args = p.parse_args()

    if not getattr(args, "自社") and not args.hookd:
        print("入力が1つも無い。--自社 か --hookd を渡す", file=sys.stderr)
        return 2

    済み = daicho.借りた鍵()
    全部 = []
    for path in getattr(args, "自社"):
        全部 += 自社を並べる(読み込む(path), 済み)
    if args.hookd:
        全部 += hookdを並べる(読み込む(args.hookd), 済み)

    候補 = 候補を選ぶ(全部)
    見て決める = [r for r in 全部 if r["タイプ"].endswith("nazo")]
    print(f"読んだ広告 {len(全部)} 本 / 台帳にある {sum(1 for r in 全部 if r['借りた'])} 本 / "
          f"候補 {len(候補)} 本 / 画を見て決める {len(見て決める)} 本")
    for r in 候補:
        print("  {}\t{}\t{}\t{}\t鍵 {}".format(
            r["出どころ"], r["タイプ名"], r["名前"][:28],
            f'{r["点"]}点' if r["外か"] else f'ROAS {r["ROAS"]}', r["鍵"]))
    for r in 見て決める:
        print(f"  画を見て決める: {r['名前']}\t{r['参考']}", file=sys.stderr)

    if not getattr(args, "書く"):
        print("\n（試し。Vault には書いていない。--書く で書く）")
        return 0

    今 = datetime.now()
    # 箱の場所と足す行を先に決める。ここで落ちれば Vault は1文字も変わらない
    lines, 最後, 足す = 箱に足す行(候補, 今.strftime("%Y-%m-%d"))
    path = 一覧を書く(全部, 候補, getattr(args, "期間"), 今.strftime("%Y-%m-%d %H:%M"))
    n = 箱を書く(lines, 最後, 足す)
    print(f"\n書いた: {path}")
    print(f"参考の箱に {n} 行足した: {HAKO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
