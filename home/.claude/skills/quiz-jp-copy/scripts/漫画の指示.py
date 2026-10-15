#!/usr/bin/env python3
"""漫画の記事の画像1枚ごとの指示（MCP chatgpt-image に渡す prompt と添付）を、型の文と記事ごとの表から出す。

使い方: python3 漫画の指示.py <設定.json> <指示表.json> <番号> [--参考 <参考の画像のフォルダ>]
  出力: {"prompt": ..., "refs": [参考の同じ番号の画像, 商品の写真...]} を1行の JSON で
  設定.json（記事ごと。商品の値はここに書く）:
    {"年代": "40〜60代", "人物": "主人公の由美は40代後半の女性（肩までのウェーブの黒茶色の髪）、友人のゆりは…",
     "商品": "ここちドライの吸水ショーツは、添付2の実物と同じ形・色（深めのショーツ、股の内側に黒い吸水部）で描く。",
     "描かない": "香水の瓶やオイルは描かない。",
     "写真": {"商品": "<商品の写真のパス>", "セット": "...", ...}}
  指示表.json（記事ごと。参考の画像1枚に1行）:
    [{"番号": 0, "種類": "m", "文字": "「俺…由美のこともう…」"},
     {"番号": 47, "種類": "m", "文字": "...", "足す": "商品", "添付": ["商品"]},
     {"番号": 51, "種類": "p", "文字": "...", "中身": "白い花を顔の前に持つ40代の日本人女性のイラスト"}]
  種類: m＝漫画のコマ（コマ割り・吹き出し・効果の字を参考どおりに描き直す）／p＝写真や図（構図と字の置き方を写す）
  「足す": "商品"」の行は 設定の商品と描かない を足す。商品が写る行は「添付」に本物の写真（店の front・平置き）を必ず入れ、設定の商品には形の点（帯の形・縫い目・股の作り・色）を1つずつ書く（言葉だけだと帯がまっすぐの別物になる。2026-10-11 審査で2回落ちた）。文字は画像に入れる字だけを一字一句（alt にも同じ文を書く）
"""
import json, os, sys

M = ("添付1の漫画の1枚を描き直してください。同じコマ割り・同じ構図・同じ人物の配置と表情・同じ吹き出しの位置と形・同じ効果音の字の位置と色で、"
     "同じ画風（やわらかい日本の少女漫画風のデジタルイラスト、淡い光、ピンクがかった色）にする。人物は日本人で、{人物}"
     "顔立ちは添付1と少しだけ変える。画像の中の文字は、下の「文字」に書いた物だけを一字一句そのまま、日本語の縦書きで、添付1と同じ吹き出しに入れる。ほかの文字・ロゴ・透かしは入れない。")
P = ("添付1と同じ構図・同じ色づかい・同じ文字の置き方と字の太さ・色で、新しい画像を作ってください。人物が写る時は{年代}の日本人にする。"
     "画像の中の文字は、下の「文字」に書いた物だけを一字一句そのまま入れ、ほかの文字・ロゴ・透かしは入れない。")


def build(cfg, row, ref_dir):
    kind = row.get("種類", "m")
    if kind == "p" and not cfg.get("年代"): raise SystemExit("設定.json に「年代」が無い（写真・図の行で人物の年代に使う）")
    head = M.format(人物=cfg.get("人物", "")) if kind == "m" else P.format(年代=cfg["年代"])
    extra = row.get("中身", "")
    if row.get("足す") == "商品": extra += cfg.get("商品", "") + cfg.get("描かない", "")
    refs = [os.path.join(ref_dir, f"{row['番号']:03d}.png")] + [cfg["写真"][k] for k in row.get("添付", [])]
    txt = row.get("文字", "").strip()
    if not txt or txt.startswith("（文字なし"):
        head = head.replace("画像の中の文字は、下の「文字」に書いた物だけを一字一句そのまま", "画像の中には文字を1字も入れない。吹き出しは参考どおりの形で空ける").split("ほかの文字・ロゴ・透かし")[0] + "ロゴ・透かしも入れない。"
        body = head + extra
    else:
        body = head + extra + "\n文字: " + txt
    lost = [r for r in refs if not os.path.exists(r)]
    if lost: raise SystemExit(f"添付が無い: {lost}")
    return {"prompt": body, "refs": refs}


if __name__ == "__main__":
    if len(sys.argv) < 4: print(__doc__); sys.exit(2)
    cfg = json.load(open(sys.argv[1])); rows = json.load(open(sys.argv[2])); n = int(sys.argv[3])
    ref = sys.argv[sys.argv.index("--参考") + 1] if "--参考" in sys.argv else "参考/画"
    row = next((r for r in rows if r["番号"] == n), None)
    if not row: print(f"番号 {n} が指示表に無い", file=sys.stderr); sys.exit(1)
    print(json.dumps(build(cfg, row, ref), ensure_ascii=False))
