#!/usr/bin/env python3
"""残す .md が読める形になっているかを機械で判定する。
文章の規則は破れるので、機械で判定できる分だけコードにしてある。

使い方:
  python3 check-md-format.py <file.md> [--skill]
    --skill … スキル/T09 メラオ型資料として並び順(関門→参考→手順)まで見る

落ちたら直す。通っても「中身が正しい」保証ではない(形だけ見ている)。
"""
import re, sys, pathlib

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    skill = '--skill' in sys.argv
    if not args:
        print(__doc__); return 2
    p = pathlib.Path(args[0])
    t = p.read_text(encoding='utf-8')
    lines = t.split('\n')
    n = len(lines)
    ng, warn = [], []

    # 1. 先頭で読者と読まなくていい条件を言っているか
    head = '\n'.join(lines[:12])
    if not re.search(r'読む|読まなく|使うだけ|向け|だけでいい|飛ばして', head):
        ng.append('先頭12行に「誰が・いつ読む物か・読まなくていい条件」が無い')

    # 6. 長さ
    if n > 500:
        ng.append(f'{n}行。500行を超えたら割る(読者が2種類混ざっていないか見る)')
    elif n > 400:
        warn.append(f'{n}行。400行を超えた。割る準備をする')

    # 3. 長い物には索引が要る
    h2 = [l for l in lines if l.startswith('## ')]
    if n > 150 and len(h2) >= 6:
        if not re.search(r'\|.*(症状|やりたいこと|出ている|探す|引く|見る|読むところ|どこを).*\|', t):
            ng.append(f'見出し{len(h2)}個 / {n}行あるのに索引表が無い。「症状 → どこを読む」を頭に置く')

    # 4. 表を使っているか(条件と対処が並ぶ長さなら)
    if n > 120 and t.count('\n|') < 6:
        warn.append('表がほとんど無い。条件と対処の対応は表にする')

    # 7. 見出しの否定形
    neg = [l for l in lines if re.match(r'^#{1,3} ', l) and re.search(r'(しない|使わない|やらない|禁止)\s*$', l)]
    if neg:
        warn.append('否定形の見出し: ' + ' / '.join(x.strip('# ')[:34] for x in neg[:3]))

    # 2. 強い位置。最後の見出しの中身が薄いと末尾を捨てている
    if h2:
        last = t.rindex(h2[-1])
        if len(t[last:].split('\n')) < 5:
            warn.append('末尾の節が4行未満。末尾は強い位置なので、置くなら中身を入れる')

    # 5. 同じ規則の重複(同一の文が2回以上)
    body = [l.strip() for l in lines if len(l.strip()) > 40 and not l.strip().startswith('|')]
    dup = {x for x in body if body.count(x) > 1}
    if dup:
        ng.append('同じ文が2箇所にある(1箇所に書いて他はそこを指す): ' + list(dup)[0][:50])

    # スキル/T09 メラオ型資料は並び順まで固定
    if skill:
        order = [t.find('<gates>'), t.find('<reference>'), t.find('<procedure>')]
        名 = ['<gates>(関門)', '<reference>(参考)', '<procedure>(手順)']
        for i, x in enumerate(order):
            if x < 0: ng.append(f'{名[i]} が無い')
        got = [x for x in order if x >= 0]
        if len(got) == 3 and got != sorted(got):
            ng.append('並び順が 関門 → 参考 → 手順 になっていない')

    for w in warn: print('  △ ' + w)
    for x in ng:   print('  ✗ ' + x)
    if ng:
        print(f'\n{p.name}: 落ちた {len(ng)}件。直してから使う')
        return 1
    print(f'\n{p.name}: 通った ({n}行' + (f' / △{len(warn)}件' if warn else '') + ')')
    return 0

sys.exit(main())
