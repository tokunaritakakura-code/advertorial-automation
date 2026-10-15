#!/usr/bin/env python3
"""PostToolUse(Write|Edit): 残す .md を書いた直後に check-md-format.py をかける。
落ちたら exit 2 で書いた本人(Claude)に返し、その場で直させる（2026-10-15 本人「md の書き方を毎回実行されるように」）。
対象外: 一時置き場・記憶・CLAUDE.md・機械が作る .mdview。"""
import json, subprocess, sys, pathlib
CHECK = pathlib.Path.home() / '.claude/skills/skill-creator/references/check-md-format.py'
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
fp = (d.get('tool_input') or {}).get('file_path') or ''
p = pathlib.Path(fp)
if p.suffix != '.md' or not p.exists():
    sys.exit(0)
s = str(p)
skip = ('/tmp/', '/private/tmp/', '/private/var/', '/memory/', '/.mdview/', '/node_modules/')
if any(k in s for k in skip) or p.name in ('CLAUDE.md', 'MEMORY.md', 'README.md'):
    sys.exit(0)
args = ['python3', str(CHECK), s]
if '/.claude/skills/' in s and p.name == 'SKILL.md':
    args.append('--skill')
# 決めたこと.md: 2026-10-15 以降の本人の決めは、正本の場所か「まだ」「記録だけ」を行に持つ（正本に入れ忘れて食い違うのを止める。2026-10-15）
if p.name == '決めたこと.md':
    import re
    抜け = [l[:60] for l in p.read_text(encoding='utf-8').split('\n')
            if (m := re.search(r'2026-(\d\d)-(\d\d)[^）]*本人', l)) and (int(m.group(1)), int(m.group(2))) >= (10, 15)
            and not any(k in l for k in ('正本', 'まだ', '記録だけ'))]
    if 抜け:
        sys.stderr.write('[md書式検査] 決めたこと.md の新しい決めに、正本の場所が無い。正本（手順書・型の表）に入れて「正本は `<パス>`」と書くか、入れていなければ「まだ手順書に入っていない」と書く\n  ' + '\n  '.join(抜け) + '\n')
        sys.exit(2)
r = subprocess.run(args, capture_output=True, text=True, timeout=10)
if r.returncode == 1:
    sys.stderr.write('[md書式検査] ~/.claude/手順/md書式.md の形に落ちた。直してから次へ進む\n' + r.stdout)
    sys.exit(2)
sys.exit(0)
