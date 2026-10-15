#!/usr/bin/env python3
"""SKILL.md を書き換えた時、旧版の固有情報が落ちていないか機械照合する。

目視の「大丈夫そう」を禁止するための道具。
数字つきトークン・コード片・ドメイン・キャメルケース語を旧版から抜き、新版に在るか見る。
"""
import re, sys

if len(sys.argv) != 3:
    sys.exit("usage: check-nolost.py <old> <new>")

old, new = (open(p, encoding='utf-8').read() for p in sys.argv[1:3])
pats = [
    r'\d[\d,\.]*(?:件|字|本|社|秒|回|%|KB|mmHg|人|円)',   # 実測値
    r'`[^`\n]{3,60}`',                                      # コード片・パス・クラス名
    r'[a-zA-Z0-9_\-]+\.(?:co|com|net|jp|org|io|xml|py|md|json|js|sh)',  # ドメイン・ファイル
    r'[A-Za-z_]{4,}[A-Z][A-Za-z_]*',                        # キャメルケース識別子
]
toks = set()
for p in pats:
    toks |= set(re.findall(p, old))
toks = {t for t in toks if len(t) > 2}
missing = sorted(t for t in toks if t not in new)

print(f"旧版の固有トークン: {len(toks)}")
print(f"新版に無いもの: {len(missing)}")
for m in missing:
    print("   欠落?:", m)
sys.exit(1 if missing else 0)
