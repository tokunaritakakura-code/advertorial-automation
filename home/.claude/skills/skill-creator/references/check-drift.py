#!/usr/bin/env python3
"""書き換えで「勝手に足したもの」を検出する。check-nolost.py の逆方向。

check-nolost は旧→新の欠落しか見ない。書き換えで一番危ないのは、
**元に無かった規則・数字・パスを発明して、それが正になってしまうこと**なので、
新→旧の増分も必ず見る。

見るのは事実性の高いトークンだけ（実測値・コード片・パス・ドメイン・識別子）。
見出しや接続詞の言い換えはノイズなので拾わない。
"""
import re, sys

PATS = [
    r'\d[\d,\.]*(?:件|字|本|社|秒|回|%|KB|MB|mmHg|人|円|分|時間|px|pt|fps)',
    r'`[^`\n]{3,80}`',
    r'[a-zA-Z0-9_\-]+\.(?:co|com|net|jp|org|io|xml|py|md|json|js|mjs|sh|html|jpg|png)',
    r'[A-Za-z_]{4,}[A-Z][A-Za-z_]*',
    r'20\d\d-\d\d-\d\d',
]
# 書式そのものの語。増えて当然なので除外する
ALLOW = {
    '`gates`', '`reference`', '`procedure`',
    '`references/skill-format.md`', '`check-nolost.py`',
}

def toks(s):
    out = set()
    for p in PATS:
        out |= set(re.findall(p, s))
    return {t for t in out if len(t) > 2} - ALLOW

if len(sys.argv) != 3:
    sys.exit("usage: check-drift.py <old> <new>")
old, new = (open(p, encoding='utf-8').read() for p in sys.argv[1:3])
added = sorted(toks(new) - toks(old))
print(f"新版だけにあるトークン: {len(added)}")
for a in added:
    print("   追加?:", a)
sys.exit(1 if added else 0)
