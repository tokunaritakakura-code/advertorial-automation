#!/usr/bin/env python3
"""記事のページ（index.html）だけを見て、本人に出す前に機械で落とす（2026-10-09 本人「構造的に直して」）。

使い方: python3 記事の仕上がり検査.py <記事のフォルダか index.html>
終了コード: 0 全部通った / 1 落ちた所がある（行ごとに出す） / 2 読めなかった

見る物（最終確認の表のうち、機械で決められる物だけ。目で見る物は表に残す）:
  1. 「未定」の字が画面に出ていない（HTML のコメントは数えない）
  2. 細長い画像が無い（縦÷横 が 0.4 未満か 2.5 より大きい。80px 未満の飾りと svg は数えない）
  3. 同じ物を指す数字がページの中で食い違っていない（声・評価の数・使っている人の数・保証の日数）
  4. 文の書き方がここちドライの記事の幅に入っている（1文の平均 18〜30字・数字の無い60字超えの文が3本以下・強調は 100〜260字に1回）
     基準の元: 針マット/ここちドライの手本/共通点.md（平均22〜27字・約165字に1回）
  5. テスト用の印がある（noindex と「テスト用の値」のコメント）。公開前に本物の値へ替えるため
  6. 最悪の結末の箱（data-tasu="1"）が読み手への警告の言い方になっていない（「こうなります」「放っておくと」「放置すると」「読まずに」「⚠」が0）。
  7. まとめ買いを並べる所（記事か申込のページ）で、いちばん高いセットに「一番人気」が付いている（2026-10-11 本人「15枚・いちばん高い値段を一番人気に」）
     「最後まで読」がページに1回だけある
  8. 商品の写真（img に data-shohin の印）で、白い背景の商品が画像の端で切れていない（2026-10-11 ranking-static の審査で×）（2026-10-11 本人「押しつけにせず、書き手が寄り添う。最後まで読んでほしいは自然に1回」。正本は Vault ec/構造/型/_必ず入れる物.md の「1 の言い方」）
  9. 値段の段（data-tasu="2"）が ここちドライの値段の段の部品を全部持つ: ① 本文に「1日あたり」か「1日○円」 ② 比べる物（今の対策の値段。「比べ」「より安」と、円の値が3つ以上）
     ③ 価格の箱（打ち消し線の通常の値段 → 今の値段・送料無料） ④ 縦長の値段画像（幅÷高さ 0.67〜0.75。img の width/height か画像ファイルの実寸。手本は 800×1200）。
     「期間限定」「ご案内」を含む段（section か data-dan の枠）があれば、その中にも ③④ と 値段の段を組む.py の出力（data-nedan="ここちドライ型"）があるか。申込のページには当てない
     あわせて、ボタン（class に btn・cta・atc・button か data-cta を持つ a と、button）の文が動作の語（試す・見る・手に入れる・確かめる・購入手続き・申し込む）で終わる物が0か。
     ボタンの文は読み手の望む結果にする（手本 ここちドライ「もう、干す時に隠さない毎日へ ›」）。記事と申込のページの両方に当てる。閉じる・断るボタン（×・いいえ）は見ない（2026-10-11 本人）
     （2026-10-11 本人「期間限定のご案内と値段の見せ方は、ここちドライの値段の段を手本にデザインまで合わせる」。正本は Vault ec/構造/型/_必ず入れる物.md の 2）
  10. 値段の段（data-tasu="2"）が ここちドライ型の部品で組まれている: 同じ外枠に data-nedan="ここちドライ型"、中に価格の箱（nd-box）と最初から選ばれたセット（nd-set is-sel）。
     組むのは ~/.claude/skills/kata-tsukuru/scripts/値段の段を組む.py。漫画（data-format="漫画"）にも当てる（漫画は段16が必ず入れる物2の HTML の値段の段で、絵で語るのは物語の段だけ。型_物語の記事.md の日本版の枝）。申込のページには当てない
     （2026-10-11 本人「値段のデザインをここちドライに寄せる。色ではなく見せ方とエフェクト」）
  11. 値段の比べは毎回いちばん高いセットで出す: 本文の「1日あたり約N円」が値段の段の1日あたりと同じ・いちばん高いセット以外の値段が値段の段の外に0。
     値段の段が古い形（硬貨の絵が本物でない頃の物）なら組み直すように出す。申込のページには当てない（2026-10-12 本人）
  12. 仕掛けの棚の値段の部品（A1 3年で並べる・A5 最後の一押し）が値段の段にある。正本 Vault ec/構造/型/_仕掛けの棚.md（2026-10-12 本人）
  13. 記事の一番下のコメント欄（値段の段を組む.py --出す コメント欄 の data-koe）がある: 声のカードが2つ以上で全部に潰す反論（data-hanron）があり重ならない・
     よくある質問が3つ以上・最後の一押し（nd-push）とボタンがコメント欄の一番下・コメント欄の後に記事の段が無い・押せないボタンが無い。
     値段の段（ここちドライ型）がある記事に当てる。申込のページには当てない。正本 Vault ec/構造/型/_仕掛けの棚.md の E（2026-10-12 本人）
  14. 「店を見ると／店のページを見ると／店で見た事／店の表示」の言い方は、値段の段（data-nedan を含む段）・コメント欄（data-koe）・最後の箱の中だけ。
     記事の頭の帯や本文には無い（帯は参考の文をそのまま移す。決めたこと 2026-10-12 本人。申込のページには当てない）
  15. 買うまでの15の事が揃っている（正本 Vault ec/構造/型/_買うまでの15の事.md。2026-10-12 本人）: 段（section か data-dan の枠）に data-koto="<事の名前>" が付き、
     body の data-motteiru="<段階で持っている事の名前をカンマ区切り>" を除いた15の事が全部どこかの段にある。名前は下の 十五の事 の通り。申込のページには当てない。data-koto が1つも無い記事（2026-10-12 より前の作り）は見ない
"""
import html, os, re, sys

def 読む(p):
    f = os.path.join(p, "index.html") if os.path.isdir(p) else p
    return f, open(f, encoding="utf-8", errors="ignore").read()

def 画面の字(s):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|h[1-6]|li|div|blockquote)>", "\n", s, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", s))

def 画像の縦横(f, s):
    bad = []
    try:
        from PIL import Image
    except ImportError:
        return ["Pillow が無いので画像を測れない（pip install pillow）"]
    base = os.path.dirname(f)
    srcs = set(re.findall(r'<img[^>]+src="([^"]+)"', s)) | set(re.findall(r'srcSet="([^" ,]+)', s))
    for src in sorted(srcs):
        if src.startswith(("http", "data:", "//")) or src.lower().endswith(".svg"):
            continue
        p = os.path.join(base, src.split("?")[0])
        if not os.path.exists(p):
            bad.append(f"画像が無い: {src}"); continue
        w, h = Image.open(p).size
        if min(w, h) < 80:
            continue
        r = h / w
        if r < 0.4 or r > 2.5:
            bad.append(f"細長い画像: {src}（{w}×{h}・縦÷横 {r:.2f}）")
    return bad

def 数字の食い違い(t):
    """同じ物を指す数字だけを比べる（医者の人数と客の人数のような別の数は比べない）"""
    bad = []
    n = r"(\d{1,3}(?:,\d{3})+|\d{3,})"
    声 = set(re.findall(n + r"\s*(?:件|人)(?:以上)?(?:の|が|を)?\s*(?:声|レビュー|評価|口コミ)", t))
    声 |= set(re.findall(r"(?:声|レビュー|評価|口コミ)[^。\n]{0,8}?" + n + r"\s*(?:件|人)", t))
    使う人 = set(re.findall(n + r"\s*人(?:以上)?(?:が|の方が)(?:使|愛用|選|購入|試)", t))
    保証 = set(re.findall(r"(\d+)\s*日間?(?:の)?(?:返金|全額返金|お試し|保証)", t))
    for 名, v in (("声・評価の数", 声), ("使っている人の数", 使う人), ("保証の日数", 保証)):
        if len(v) > 1:
            bad.append(f"{名}が食い違う: {'・'.join(sorted(v))}（同じ物を指すなら1つにそろえる）")
    return bad

def 文の書き方(s, t):
    bad = []
    文 = [x.strip() for x in re.split(r"(?<=[。！？])|\n", t) if len(x.strip()) >= 6]
    if not 文:
        return ["本文の文が取れない"]
    平均 = sum(len(x) for x in 文) / len(文)
    if not 18 <= 平均 <= 30:
        bad.append(f"1文の平均が {平均:.1f}字（手本は22〜27字。18〜30字に入れる）")
    長い = [x for x in 文 if len(x) > 60 and not re.search(r"\d", x)]
    if len(長い) > 3:
        bad.append(f"数字の無い60字超えの文が {len(長い)}本（3本以下）: 「{長い[0][:30]}…」")
    強調 = len(re.findall(r"<(strong|b|mark)\b", s, flags=re.I))
    字数 = len(re.sub(r"\s", "", t))
    if 強調 == 0:
        bad.append("強調（太字・色）が0回")
    else:
        間 = 字数 / 強調
        if not 100 <= 間 <= 260:
            bad.append(f"強調が {間:.0f}字に1回（手本は約165字に1回。100〜260字に入れる）")
    return bad

def テストの印(s):
    bad = []
    if not re.search(r'name="robots"\s+content="noindex"', s):
        bad.append('noindex が無い（<meta name="robots" content="noindex">）')
    if "テスト用の値" not in s:
        bad.append("「テスト用の値」のコメントが無い（決めた値の一覧の場所を書く）")
    return bad

def 寄り添い(s, t, 申込=False):
    bad = []
    m = re.search(r'data-tasu="1"', s)
    if m:
        seg = s[m.start():m.start() + 2500]
        nxt = re.search(r'data-tasu="[02-9]', seg)
        box = 画面の字(seg[:nxt.start()] if nxt else seg)
        hit = [w for w in ("こうなります", "放っておくと", "放置すると", "読まずに", "⚠") if w in box]
        if hit:
            bad.append(f"最悪の結末の箱が読み手への警告の言い方: {'・'.join(hit)}（書き手の立場で、知っている理由と気持ちで言う。_必ず入れる物.md の「1 の言い方」）")
    n = len(re.findall(r"最後まで読", t))
    漫画 = re.search(r'data-format="漫画"|class="[^"]*manga', s)  # 漫画は物語で読ませるので入れない（2026-10-11 本人）
    # 申込のページ（記事のフォルダの 申込/）は書き手のいない商品の申込なので、最悪の結末の箱も「最後まで読んでほしい」も置かない（2026-10-11 睡眠イヤホン: ここちドライ・アルコットの暴露型の申込/ も同じ所で落ちていた）
    if n != 1 and not (漫画 and n == 0) and not (申込 and n == 0):
        bad.append(f"「最後まで読んでほしい」がページに {n}回（書き手の気持ちとして自然に1回）")
    return bad

def 一番人気(f):
    bad = []
    d = os.path.dirname(os.path.abspath(f))
    for g in (f, os.path.join(d, "申込", "index.html")):
        if not os.path.exists(g):
            continue
        h = open(g, encoding="utf-8", errors="ignore").read()
        h = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h, flags=re.S | re.I)
        h = re.sub(r"<(ul|div)\b[^>]*data-kuraberu[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)  # 比べる物（今の対策の値段）はセットの値段でないので数えない
        h = re.sub(r"<(ul|div|table|section)\b[^>]*data-sannen[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)  # 仕掛けの棚 A1「3年で並べる」の今の対策の積み上がり（¥180,000 など）はセットの値段でないので数えない（2026-10-12 static）
        # 打ち消し線の通常価格は数えない（<s>・<del>・line-through・compare/was/old/regular の名前の付いた物）
        h = re.sub(r"<(s|del|strike)\b[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
        h = re.sub(r'<(\w+)\b[^>]*(?:line-through|class="[^"]*(?:compare|was|old|regular|strike|normal|teika)[^"]*")[^>]*>[^<]*</\1>', " ", h, flags=re.S | re.I)
        h = re.sub(r"(通常価格|通常|定価|参考価格)\s*[:：]?\s*(?:<[^>]+>\s*)*[¥￥]?\s*\d{1,3}(?:,\d{3})+\s*円?", " ", h)
        t = re.sub(r"<[^>]+>", " ", h)
        値 = [int(x.replace(",", "")) for x in re.findall(r"[¥￥]\s*(\d{1,3}(?:,\d{3})+)|(?<![\d,])(\d{1,3}(?:,\d{3})+)\s*円", t) for x in x if x]
        セット = re.search(r"\d+\s*(枚|ペア|個|本|箱)\s*(セット|組)", t)
        if len(set(値)) < 3 or not セット:
            continue
        top = f"{max(値):,}"
        m = re.search(r'data-ookii="(\d+)"', h)  # 値段の段を組む.py が書く「いちばん高いセット」の値。あれば本文の ¥ の最大（3年の積み上がり等）より優先（2026-10-12 static）
        if m:
            top = f"{int(m.group(1)):,}"
        i = t.find("一番人気")
        if i < 0:
            bad.append(f"{os.path.relpath(g, d)}: まとめ買いを並べているのに「一番人気」が無い（いちばん高いセット ¥{top} に付ける）")
        elif top not in t[max(0, i - 400):i + 600]:
            bad.append(f"{os.path.relpath(g, d)}: 「一番人気」の近くに、いちばん高いセットの値段 ¥{top} が無い")
    return bad

def 商品の切れ(f, s):
    """白い背景の商品写真で、商品が画像の端で切れていないか（2026-10-11 ranking-static: 0.457 に合わせて切った中敷きのつま先とかかとが消え、審査で×）。
    白い背景の写真＝ふちの画素の35%以上が白（切れた写真はふちに物がかかって白が減るので低めに置く）。その写真で、白でない所の外枠が上下左右の端から2%以内に触れたら「切れ」。人の写真（ふちが白くない）は見ない"""
    bad = []
    try:
        from PIL import Image
    except ImportError:
        return []
    base = os.path.dirname(f)
    # 商品の写真の印 data-shohin が付いた img だけ見る（人の写真・寄った写真・見出しの帯は、端に触れるのが正しいので見ない）
    for src in sorted(set(re.findall(r'<img(?=[^>]*data-shohin)[^>]+src="([^"]+)"', s) + re.findall(r'<img[^>]+src="([^"]+)"(?=[^>]*data-shohin)', s))):
        if src.startswith(("http", "data:", "//")) or src.lower().endswith(".svg"):
            continue
        p = os.path.join(base, src.split("?")[0])
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("L"); w, h = im.size
        if w < 120 or h < 120:
            continue
        sm = im.resize((max(1, w // 4), max(1, h // 4))); W, H = sm.size; px = sm.load()
        ふち = [px[x, 0] for x in range(W)] + [px[x, H - 1] for x in range(W)] + [px[0, y] for y in range(H)] + [px[W - 1, y] for y in range(H)]
        if sum(1 for v in ふち if v >= 235) < 0.35 * len(ふち):
            continue
        box = sm.point(lambda v: 255 if v < 235 else 0).getbbox()
        if not box:
            continue
        m = 0.02
        if box[0] <= W * m or box[1] <= H * m or box[2] >= W * (1 - m) or box[3] >= H * (1 - m):
            bad.append(f"商品が画像の端で切れている: {src}（白い背景の写真で、物が端から2%以内に触れている。切らずに白い余白で全体を入れる）")
    return bad

def 枠の終わり(s, i):
    """s[i] から始まる開きタグの要素が閉じる位置（同じタグ名の入れ子を数える）。閉じが無ければ文の終わり"""
    m = re.match(r"<(\w+)", s[i:])
    if not m:
        return len(s)
    tag = m.group(1).lower(); d = 0
    for t in re.finditer(r"<(/?)" + tag + r"\b[^>]*>", s[i:], flags=re.I):
        d += -1 if t.group(1) else 1
        if d == 0:
            return i + t.end()
    return len(s)

def 枠(s, attr_pos):
    """属性の位置から、その属性を持つ開きタグの始まりと要素の終わりを返す"""
    st = s.rfind("<", 0, attr_pos)
    return st, 枠の終わり(s, st)

def 縦長の値段画像(f, seg):
    base = os.path.dirname(f)
    for tag in re.findall(r"<img\b[^>]*>", seg, flags=re.I):
        w = re.search(r'\bwidth="?(\d+)', tag); h = re.search(r'\bheight="?(\d+)', tag)
        if w and h and int(h.group(1)):
            q = int(w.group(1)) / int(h.group(1))
        else:
            src = re.search(r'\bsrc="([^"]+)"', tag)
            if not src or src.group(1).startswith(("http", "data:", "//")):
                continue
            p = os.path.join(base, src.group(1).split("?")[0])
            try:
                from PIL import Image
                iw, ih = Image.open(p).size; q = iw / ih
            except Exception:
                continue
        if 0.67 <= q <= 0.75:
            return True
    return False

def 価格の箱(seg):
    t = 画面の字(seg)
    打ち消し = re.search(r"<(s|del|strike)\b|line-through|class=\"[^\"]*\b(was|old|regular|teika|compare)\b", seg, flags=re.I)
    値 = set(re.findall(r"[¥￥]\s*\d{1,3}(?:,\d{3})+|\d{1,3}(?:,\d{3})+\s*円", t))
    return bool(打ち消し) and len(値) >= 2 and "送料無料" in t

def 値段の段(f, s):
    """9. 値段の段（data-tasu=2）と「期間限定」「ご案内」の段が、ここちドライの値段の段の部品を持つか"""
    bad = []
    s = re.sub(r"<!--.*?-->", lambda m: " " * len(m.group(0)), s, flags=re.S)
    m = re.search(r'data-tasu="2"', s)
    if not m:
        return ['値段の段（data-tasu="2"）が無い（前振りで1日あたり → 比べる物 → 価格の箱 → 縦長の値段画像。_必ず入れる物.md の 2）']
    a, b = 枠(s, m.start()); seg = s[a:b]; t = 画面の字(seg)
    無い = []
    if not re.search(r"1日あたり|1日\s*(?:約|およそ)?\s*[\d,]+\s*円", t):
        無い.append("①本文の1日あたりの値段")
    if not (re.search(r"比べ|より安|より高", t) and len(set(re.findall(r"[\d,]+\s*円", t))) >= 3):
        無い.append("②比べる物（今の対策の値段）")
    if not 価格の箱(seg):
        無い.append("③価格の箱（打ち消し線の通常の値段 → 今の値段・送料無料）")
    # アンケート型・漫画は値段が「問いの前の札」（部品の --出す 札だけ）と「答えた後の段」に分かれるので、④はどれかの data-tasu=2 の段にあればよい（2026-10-11）
    他の段 = [s[x:y] for x, y in (枠(s, o.start()) for o in re.finditer(r'data-tasu="2"', s)) if x != a]
    if not 縦長の値段画像(f, seg) and not any(縦長の値段画像(f, g) for g in 他の段):
        無い.append("④縦長の値段画像（幅÷高さ 0.67〜0.75）")
    if 無い:
        bad.append(f"値段の段（data-tasu=2）に無い: {'・'.join(無い)}（ここちドライの値段の段に合わせる。手本 共通点.md 5-2・欄のCSS.html。data-tasu=2 は前振りから値段画像までを囲む枠に付ける）")
    # 「期間限定」「ご案内」の段: その字を含むいちばん内側の section か data-dan の枠
    見た = set()
    for w in re.finditer(r"期間限定|ご案内", s):
        if re.search(r"<(script|style)[^>]*>[^<]*$", s[:w.start()][-3000:], flags=re.I):
            continue
        # 見出し（h1〜h6）か、札・帯のような短い字（40字以下の span・div など）の時だけ段の名前と見る。
        # 本文の段落（p・li）の中の「特別なご案内があります」は前振りなので見ない（2026-10-11 ここちドライ暴露型の段15）
        短い = False
        for o in reversed(list(re.finditer(r"<(p|h[1-6]|span|div|li|a|label|figcaption)\b[^>]*>", s[max(0, w.start() - 4000):w.start()], flags=re.I))):
            st = max(0, w.start() - 4000) + o.start(); e = 枠の終わり(s, st)
            if e > w.end():
                tg = o.group(1).lower()
                短い = tg.startswith("h") or (tg not in ("p", "li") and len(re.sub(r"\s", "", 画面の字(s[st:e]))) <= 40); break
        if not 短い:
            continue
        cand = []
        for o in re.finditer(r'<(section)\b[^>]*>|<\w+\b[^>]*\bdata-dan="[^"]*"[^>]*>', s[:w.start()], flags=re.I):
            e = 枠の終わり(s, o.start())
            if e > w.end():
                cand.append((o.start(), e))
        if not cand:
            continue
        a2, b2 = max(cand)  # いちばん内側
        if (a2, b2) in 見た or (a2 <= a and b <= b2):
            見た.add((a2, b2)); continue  # 値段の段を中に持つ段は上で見た
        見た.add((a2, b2))
        seg2 = s[a2:b2]; 無い2 = []
        if not 価格の箱(seg2):
            無い2.append("③価格の箱")
        if not 縦長の値段画像(f, seg2):
            無い2.append("④縦長の値段画像")
        if 'data-nedan="ここちドライ型"' not in seg2:
            無い2.append("値段の段を組む.py の出力（data-nedan）")
        if 無い2:
            名 = re.search(r'data-dan="([^"]*)"', s[a2:a2 + 300])
            bad.append(f"「{w.group(0)}」の段{'（data-dan=' + 名.group(1) + '）' if 名 else ''}に無い: {'・'.join(無い2)}（値段の段と同じ部品で作る）")
    return bad

def ボタンの文(s):
    """9 の続き: ボタンの文が動作の語で終わっていないか（記事と申込の両方）"""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", s, flags=re.S | re.I)
    bad = []
    for m in re.finditer(r'<(a|button)\b([^>]*)>(.*?)</\1>', s, flags=re.S | re.I):
        if m.group(1).lower() == "a" and not re.search(r'class="[^"]*\b(btn|cta|nd-cta|atc|button)\b|\bdata-cta\b', m.group(2)):
            continue
        t = re.sub(r"\s|[›→>▶＞]", "", html.unescape(re.sub(r"<[^>]+>", "", m.group(3))))
        if not t or t in ("×",) or t.startswith("いいえ"):
            continue
        核 = re.split(r"[｜|]", t)[0]
        if re.search(r"(試す|試してみる|見る|見てみる|手に入れる|確かめる|申し込む|申込む)$", 核) or re.search(r"購入手続き|申し込", 核):
            bad.append(f"ボタンの文が動作の語: 「{t}」（読み手の望む結果にする。手本「もう、干す時に隠さない毎日へ ›」）")
    return bad

def ここちドライ型(s):
    """10. 値段の段（data-tasu=2 の段は全部）が ここちドライ型の部品（値段の段を組む.py の出力）か"""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    bad = []
    for m in re.finditer(r'<\w+\b[^>]*data-tasu="2"[^>]*>', s):
        tag = m.group(0)
        if 'data-nedan="ここちドライ型"' not in tag:
            bad.append('値段の段（data-tasu="2"）が ここちドライ型の部品で組まれていない（同じ外枠に data-nedan="ここちドライ型" が無い）。'
                       '`python3 ~/.claude/skills/kata-tsukuru/scripts/値段の段を組む.py <入力.json>` で組み、data-tasu="2" の段と差し替える')
            continue
        seg = s[m.start():枠の終わり(s, m.start())]
        無い = []
        if 'class="nd-box"' not in seg:
            無い.append("価格の箱 nd-box")
        cards = re.findall(r'<a class="nd-set( is-sel)?"[^>]*>(.*?)</a>', seg, flags=re.S)
        値 = lambda c: int((re.search(r'class="nd-y">[¥￥]([\d,]+)', c) or re.search(r"()0", "0")).group(1).replace(",", "") or 0)
        sel = [c for f, c in cards if f]
        if len(sel) != 1:
            無い.append("最初から選ばれたセット nd-set is-sel が1つ")
        else:
            if 'class="nd-badge">一番人気' not in sel[0]:
                無い.append("選ばれたセットの「一番人気」の札")
            if 値(sel[0]) < max(値(c) for f, c in cards):
                無い.append("選ばれたセットがいちばん高い値段")
        if 無い:
            bad.append(f"ここちドライ型の値段の段に無い: {'・'.join(無い)}（手で写さず 値段の段を組む.py の出力をそのまま貼る）")
    return bad

def いちばん高いセット(s, t):
    """11. 値段の比べは毎回いちばん高いセットで出す（2026-10-12 本人）。値段の段の外枠の data-ichinichi・data-ookii と、セットのカード（nd-set）の値段から、
    ページの字の「1日あたり約N円」が N と違う物・いちばん高いセット以外のセットの値段（¥N・N円）が値段の段の外に出ている物を落とす。
    値段の段が古い（data-ichinichi が無い）時は、値段の段を組む.py で組み直すように出す"""
    m = re.search(r'data-nedan="ここちドライ型"[^>]*', s) or re.search(r'<[^>]*data-nedan="ここちドライ型"[^>]*>', s)
    if not m:
        return []
    tag = s[s.rfind("<", 0, m.start()):s.find(">", m.start()) + 1]
    a = re.search(r'data-ichinichi="(\d+)"', tag); o = re.search(r'data-ookii="(\d+)"', tag)
    if not (a and o):
        return ['値段の段が古い形（data-ichinichi・data-ookii が無い）。値段の段を組む.py で組み直す（硬貨の絵と、いちばん高いセットで比べる決まりが入る）']
    日, 大 = int(a.group(1)), int(o.group(1))
    bad = []
    for x in re.finditer(r"1日あたり\s*(?:約|およそ)?\s*([\d,]+)\s*円", t):
        if int(x.group(1).replace(",", "")) != 日:
            bad.append(f"「{x.group(0)}」がいちばん高いセットの1日あたり約{日}円と違う（値段の比べは毎回いちばん高いセットで出す）")
    cards = re.findall(r'<a class="nd-set(?: is-sel)?"[^>]*>.*?<div class="nd-y">[¥￥]([\d,]+)</div>', s, flags=re.S)
    ほか = {int(c.replace(",", "")) for c in cards} - {大}
    # セットのカードの「1つあたり」も見る。いちばん高いセット（選ばれたカード is-sel）の1つあたりは本文に出てよい
    for card in re.finditer(r'<a class="nd-set( is-sel)?"[^>]*>(.*?)</a>', s, flags=re.S):
        u = re.search(r"あたり\s*[¥￥]([\d,]+)", card.group(2))
        if u and not card.group(1):
            ほか.add(int(u.group(1).replace(",", "")))
    for card in re.finditer(r'<a class="nd-set is-sel"[^>]*>(.*?)</a>', s, flags=re.S):
        u = re.search(r"あたり\s*[¥￥]([\d,]+)", card.group(1))
        if u:
            ほか.discard(int(u.group(1).replace(",", "")))
    外 = re.sub(r'<div class="nd-sets".*?</div>\s*</div>|<a class="nd-set.*?</a>', " ", s, flags=re.S)
    外字 = 画面の字(外)
    for v in sorted(ほか):
        hit = re.search(r"(?:¥|￥)\s*" + f"{v:,}".replace(",", ",?") + r"(?!\d)|(?<![\d,])" + f"{v:,}".replace(",", ",?") + r"\s*円", 外字)
        if hit:
            bad.append(f"いちばん高いセット以外の値段「{hit.group(0)}」が本文に出ている（値段の比べは毎回いちばん高いセット ¥{大:,} で出す。並べるのはセットのカードだけ）")
    return list(dict.fromkeys(bad))

def 仕掛けの棚(s):
    """12. 仕掛けの棚の値段の部品（Vault ec/構造/型/_仕掛けの棚.md の A1 3年で並べる・A5 最後の一押し）が値段の段にある（2026-10-12 本人「全部の広告のフォーマットで」）"""
    if 'data-nedan="ここちドライ型"' not in s:
        return []
    無い = [n for k, n in (('data-sannen', 'A1 3年で並べる（入力の「3年」）'), ('class="nd-push"', 'A5 最後の一押し（入力の「一押し」）')) if k not in s]
    return [f"仕掛けの棚の部品が値段の段に無い: {'・'.join(無い)}（値段の段を組む.py の入力に足して組み直す。正本 Vault ec/構造/型/_仕掛けの棚.md）"] if 無い else []

def コメント欄(s):
    """13. 記事の一番下のコメント欄が、アングルの人の反論を潰す声と質問で、最後の一押しとボタンがその一番下にある（2026-10-12 本人）"""
    if 'data-nedan="ここちドライ型"' not in s:
        return []
    m = re.search(r'<section class="nd nd-koe" data-koe[^>]*>(.*?)</section>', s, flags=re.S)
    if not m:
        return ["記事の一番下のコメント欄が無い（値段の段を組む.py の入力に「コメント欄」を足し、--出す コメント欄 で組んで記事の一番下に貼る。正本 Vault ec/構造/型/_仕掛けの棚.md の E）"]
    k, bad = m.group(1), []
    反論 = re.findall(r'class="nd-vcard" data-hanron="([^"]+)"', k)
    if len(反論) < 2 or len(re.findall(r'class="nd-vcard"', k)) != len(反論):
        bad.append(f"コメント欄の声が2つ未満か、潰す反論（data-hanron）の無いカードがある（{len(反論)}つ）")
    if len(set(反論)) < len(反論):
        bad.append("コメント欄の声の反論が重なっている（1枚に1つ、違う反論）")
    faq = re.search(r'class="nd-faq">(.*?)</div>', k, flags=re.S)
    if not faq or len(re.findall(r"<h3", faq.group(1))) < 3:
        bad.append("コメント欄のよくある質問が3つ未満")
    i_push, i_cta = k.rfind('class="nd-push"'), k.rfind('class="nd-cta"')
    if i_push < 0 or i_cta < i_push or (faq and i_push < k.find('class="nd-faq"')):
        bad.append("最後の一押しとボタンがコメント欄の一番下に無い（声 → 質問 → 一押し → ボタン の順）")
    if 'class="nd-push"' in s[:m.start()]:
        bad.append("最後の一押しがコメント欄の外（値段の段）にも残っている（値段の段を組み直す）")
    if re.search(r"<button[^>]*disabled|<textarea[^>]*disabled", k):
        bad.append("コメント欄に押せないボタン・書けない入力欄がある（中身の無い部品は足さない。決めたこと 2026-10-12）")
    後 = s[m.end():]
    if re.search(r"<section\b|data-dan=|data-tasu=", 後.split('class="foot"')[0]):
        bad.append("コメント欄の後に記事の段がある（コメント欄は記事の一番下。後ろは出典と記事の下の欄だけ）")
    return bad

def 店で見た事の置き場(s):
    """14. 「店を見ると」の言い方が、値段の段・コメント欄・最後の箱の外（頭の帯・本文）に無い（決めたこと 2026-10-12 本人）"""
    if 'data-nedan="ここちドライ型"' not in s:
        return []
    # 値段の段・最後の箱を含む data-dan の段（data-nedan を含む段。段は順に並ぶので次の段の頭まで）と、コメント欄を外す
    r = "".join(p for p in re.split(r'(?=<section data-dan="\d+")', s) if 'data-nedan=' not in p)
    r = re.sub(r'<section class="nd nd-koe" data-koe[^>]*>.*?</section>', '', r, flags=re.S)
    r = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', r, flags=re.S)
    t = html.unescape(re.sub(r'<[^>]+>', '', r.replace('<wbr>', '')))
    hits = re.findall(r'(?:公式の)?店(?:のページ)?を見(?:る|た)と|店で見た事|店の表示', t)
    if hits:
        return [f"「店を見ると」の言い方が値段の段・コメント欄・最後の箱の外に {len(hits)}か所（{hits[0]}）。頭の帯・本文には当てない。帯は参考の文をそのまま移す（決めたこと 2026-10-12）"]
    return []

十五の事 = ["試した物は効かない", "本当の原因", "怖い先", "信じられる人", "その人の物語", "なぜ今まで無かったか", "仕組み", "効いた人",
          "作るのが難しかった", "商品", "値段", "損はしない", "無くなる", "決めなくていい", "最後の疑問", "動かない代償"]

def 十五の事の揃い(s):
    """15. 買うまでの15の事（Vault ec/構造/型/_買うまでの15の事.md）が、段の data-koto で全部ある（2026-10-12 本人）"""
    ある = set()
    for v in re.findall(r'data-koto="([^"]*)"', s):
        for x in re.split(r"[,、・]", v):
            x = x.strip()
            if x: ある.add(x)
    m = re.search(r'<body[^>]*data-motteiru="([^"]*)"', s)
    持っている = {x.strip() for x in re.split(r"[,、・]", m.group(1)) if x.strip()} if m else set()
    if not ある:
        # data-koto が1つも無い記事は、2026-10-12 より前の作り（15の事を塗る前）。ここでは落とさず、新しい作りは最終確認 A5・B5 と 05 の手順の関門で止める
        print("（15の事: data-koto が無いので見ていない。新しく作る記事は段ごとに data-koto を付ける。正本 Vault ec/構造/型/_買うまでの15の事.md）", file=sys.stderr)
        return []
    知らない = sorted(x for x in ある | 持っている if x not in 十五の事 and x != "この痛みは私の事")
    無い = [x for x in 十五の事 if x not in ある and x not in 持っている]
    bad = []
    if 知らない:
        bad.append(f"data-koto / data-motteiru に正本に無い名前: {'・'.join(知らない)}（使える名前: {'・'.join(十五の事)}・この痛みは私の事）")
    if 無い:
        bad.append(f"15の事が段に無い: {'・'.join(無い)}（段階で持っている物なら body に data-motteiru で書く。正本 Vault ec/構造/型/_買うまでの15の事.md）")
    return bad

def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    try:
        f, s = 読む(argv[1])
    except Exception as e:
        print(f"読めなかった: {e}"); return 2
    t = 画面の字(s)
    bad = []
    n = t.count("未定")
    if n:
        bad.append(f"画面に「未定」が {n}か所")
    申込 = os.path.basename(os.path.dirname(os.path.abspath(f))) == "申込"
    bad += 画像の縦横(f, s) + 数字の食い違い(t) + 文の書き方(s, t) + テストの印(s) + 寄り添い(s, t, 申込) + 一番人気(f) + 商品の切れ(f, s) + ([] if 申込 else 値段の段(f, s) + ここちドライ型(s) + いちばん高いセット(s, t) + 仕掛けの棚(s) + コメント欄(s) + 店で見た事の置き場(s) + 十五の事の揃い(s)) + ボタンの文(s)
    if bad:
        print("\n".join("- " + x for x in bad)); return 1
    print("通った"); return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
