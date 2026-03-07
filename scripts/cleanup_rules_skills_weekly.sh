#!/bin/bash
set -euo pipefail

OUT="$HOME/obsidian-vault/projects/rolemesh-rules-skills-weekly.md"
NOW=$(date '+%Y-%m-%d %H:%M %Z')

python3 - <<'PY'
from pathlib import Path
import re, time

root = Path('/Users/rocky/rolemesh')
docs = root / 'docs'
files = sorted([p for p in docs.glob('*.md') if p.is_file()])

rule_like=[]
skill_like=[]
for p in files:
    t = p.read_text(encoding='utf-8', errors='ignore')
    for line in t.splitlines():
        s=line.strip()
        if not s.startswith('- '):
            continue
        low=s.lower()
        if any(k in low for k in ['must', 'should', '금지', '필수', '차단', 'rule']):
            rule_like.append((p.name, s))
        if any(k in low for k in ['workflow', 'guide', '절차', 'skill', 'how to']):
            skill_like.append((p.name, s))

# naive duplicates by normalized bullet text
from collections import Counter
norm=lambda x: re.sub(r'\s+',' ',x.lower())
rule_cnt=Counter(norm(x[1]) for x in rule_like)
skill_cnt=Counter(norm(x[1]) for x in skill_like)

rule_dups=[k for k,v in rule_cnt.items() if v>=2]
skill_dups=[k for k,v in skill_cnt.items() if v>=2]

lines=[]
lines.append('# RoleMesh Rules/Skills Weekly Cleanup Report')
lines.append('')
lines.append(f'- generated: {time.strftime("%Y-%m-%d %H:%M %Z")})')
lines.append(f'- scanned files: {len(files)}')
lines.append(f'- rule-like bullets: {len(rule_like)}')
lines.append(f'- skill-like bullets: {len(skill_like)}')
lines.append('')
lines.append('## Potential Duplicates (Rules)')
if rule_dups:
    for d in rule_dups[:20]:
        lines.append(f'- {d}')
else:
    lines.append('- none')
lines.append('')
lines.append('## Potential Duplicates (Skills/Procedures)')
if skill_dups:
    for d in skill_dups[:20]:
        lines.append(f'- {d}')
else:
    lines.append('- none')
lines.append('')
lines.append('## Action')
lines.append('- Merge duplicate bullets and keep one canonical source doc per topic.')
lines.append('- Remove stale bullets not referenced by PRD/Test-Plan/Architecture.')

out=Path('~/obsidian-vault/projects/rolemesh-rules-skills-weekly.md').expanduser()
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text('\n'.join(lines)+'\n', encoding='utf-8')
print(f'updated: {out}')
PY
