#!/bin/bash
set -euo pipefail

LOG="$HOME/ai-comms/pm_packet_quality.jsonl"
OUT="$HOME/obsidian-vault/projects/pm-quality-weekly.md"
NOW=$(date '+%Y-%m-%d %H:%M %Z')

python3 - <<'PY'
import json, os, time, statistics
from collections import Counter, defaultdict

log = os.path.expanduser('~/ai-comms/pm_packet_quality.jsonl')
out = os.path.expanduser('~/obsidian-vault/projects/pm-quality-weekly.md')
now = time.time()
week_ago = now - 7*24*3600

rows=[]
if os.path.exists(log):
    with open(log,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                r=json.loads(line)
            except Exception:
                continue
            if r.get('ts',0) >= week_ago:
                rows.append(r)

scores=[r.get('score',0) for r in rows]
by_kind=defaultdict(list)
by_assignee=defaultdict(list)
for r in rows:
    by_kind[r.get('kind','unknown')].append(r.get('score',0))
    by_assignee[r.get('assignee','unknown')].append(r.get('score',0))

low = sorted(rows, key=lambda x: x.get('score',0))[:10]

def avg(xs):
    return round(sum(xs)/len(xs),1) if xs else 0.0

def pct(cond):
    if not rows: return 0.0
    return round(100.0*sum(1 for r in rows if cond(r))/len(rows),1)

lines=[]
lines.append('# PM Packet Quality Weekly Report')
lines.append('')
lines.append(f'- generated: {time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(now))}')
lines.append('- window: last 7 days')
lines.append('')
lines.append('## Summary')
lines.append(f'- samples: {len(rows)}')
lines.append(f'- avg score: {avg(scores)} / 100')
lines.append(f'- p50: {round(statistics.median(scores),1) if scores else 0.0}')
lines.append(f'- high quality (>=85): {pct(lambda r: r.get("score",0) >= 85)}%')
lines.append(f'- low quality (<70): {pct(lambda r: r.get("score",0) < 70)}%')
lines.append('')

lines.append('## By kind')
if by_kind:
    for k,v in sorted(by_kind.items()):
        lines.append(f'- {k}: {avg(v)} ({len(v)} samples)')
else:
    lines.append('- no data')
lines.append('')

lines.append('## By assignee')
if by_assignee:
    for k,v in sorted(by_assignee.items()):
        lines.append(f'- {k}: {avg(v)} ({len(v)} samples)')
else:
    lines.append('- no data')
lines.append('')

lines.append('## Lowest 10 packets (action needed)')
if low:
    for r in low:
        lines.append(f"- score {r.get('score',0)} | {r.get('kind','?')} | {r.get('title','(no title)')}")
else:
    lines.append('- no data')

os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out,'w',encoding='utf-8') as f:
    f.write('\n'.join(lines)+'\n')
print(f'updated: {out}')
PY
