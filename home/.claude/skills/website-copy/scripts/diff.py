#!/usr/bin/env python3
# diff.py <imgA> <imgB> — 2枚のスクショを500px横帯ごとにピクセル差分（答え合わせ）
# 注意: システムのpythonで実行すること → /usr/bin/python3 scripts/diff.py A.png B.png
#       （HomebrewのPythonはPILが壊れている場合がある）
import sys
from PIL import Image
import numpy as np

a = Image.open(sys.argv[1]).convert('RGB')
b = Image.open(sys.argv[2]).convert('RGB')
if a.size != b.size:
    w = min(a.size[0], b.size[0]); h = min(a.size[1], b.size[1])
    a = a.crop((0, 0, w, h)); b = b.crop((0, 0, w, h))
    print(f'(sizes differ, cropped to {w}x{h})')

na = np.asarray(a, dtype=np.int16); nb = np.asarray(b, dtype=np.int16)
d = np.abs(na - nb).sum(axis=2)   # ピクセルごとのRGB絶対差の和 (0-765)
print(f'TOTAL differing (>30/765): {(d > 30).mean() * 100:.2f}%')
H = a.size[1]
for y in range(0, H, 500):
    p = (d[y:y+500] > 30).mean() * 100
    if p > 1:
        print(f'  {y:6d}-{y+500:6d}  {p:6.2f}%  ' + '#' * int(p // 2))
