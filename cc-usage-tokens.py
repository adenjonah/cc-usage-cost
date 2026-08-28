#!/usr/bin/env python3
"""Add up Claude Code token usage from the transcripts in ~/.claude/projects.

Usage: cc-usage-tokens.py [SINCE] > usage.json      (SINCE defaults to 2026-05-01)

Claude Code writes several partial usage records per response while it streams,
so records are deduped by message id and the largest value per field is kept.
"""
import collections
import datetime
import glob
import json
import os
import sys

since = sys.argv[1] if len(sys.argv) > 1 else "2026-05-01"
root = os.path.expanduser("~/.claude/projects")
FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens",
          "cache_read_input_tokens", "c5m", "c1h")

msgs = {}
files = 0
lines = 0
bad = 0

for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
    files += 1
    try:
        fh = open(path, "r", errors="replace")
    except OSError:
        continue
    with fh:
        for line in fh:
            if '"usage"' not in line:
                continue
            lines += 1
            try:
                d = json.loads(line)
            except Exception:
                bad += 1
                continue
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            u = m.get("usage") if isinstance(m, dict) else None
            if not u:
                continue
            ts = d.get("timestamp") or ""
            if ts[:10] < since:
                continue
            model = m.get("model") or "unknown"
            if model.startswith("<"):
                continue
            mid = m.get("id") or d.get("uuid")
            cc = u.get("cache_creation") or {}
            vals = [
                u.get("input_tokens", 0) or 0,
                u.get("output_tokens", 0) or 0,
                u.get("cache_creation_input_tokens", 0) or 0,
                u.get("cache_read_input_tokens", 0) or 0,
                cc.get("ephemeral_5m_input_tokens", 0) or 0,
                cc.get("ephemeral_1h_input_tokens", 0) or 0,
            ]
            rec = msgs.get(mid)
            if rec is None:
                msgs[mid] = [model, ts[:7], ts[:10]] + vals
            else:
                for i, v in enumerate(vals):
                    if v > rec[3 + i]:
                        rec[3 + i] = v

# roll up by (month, model)
agg = collections.defaultdict(lambda: [0] * 6 + [0])
days = set()
months_days = collections.defaultdict(set)
for rec in msgs.values():
    model, month, day = rec[0], rec[1], rec[2]
    a = agg[(month, model)]
    for i in range(6):
        a[i] += rec[3 + i]
    a[6] += 1
    days.add(day)
    months_days[month].add(day)

# Claude Code deletes transcripts older than cleanupPeriodDays (30 by default), but the
# prompt log in history.jsonl is never cleaned up. Any day with prompts and no transcript
# data is a window that already got deleted.
hist = collections.Counter()
transcript_days = {r[2] for r in msgs.values()}
hp = os.path.expanduser("~/.claude/history.jsonl")
if os.path.exists(hp):
    for line in open(hp, errors="replace"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        ts = d.get("timestamp")
        if not ts:
            continue
        secs = ts / 1000 if ts > 1e12 else ts
        day = datetime.datetime.utcfromtimestamp(secs).strftime("%Y-%m-%d")
        if day >= since:
            hist[day] += 1
missing = {k: v for k, v in sorted(hist.items()) if k not in transcript_days}

out = {
    "host": os.uname().nodename,
    "since": since,
    "files": files,
    "usage_lines": lines,
    "bad_lines": bad,
    "messages": len(msgs),
    "active_days": len(days),
    "active_days_by_month": {k: len(v) for k, v in sorted(months_days.items())},
    "prompts_since": sum(hist.values()),
    "prompts_on_days_without_transcripts": sum(missing.values()),
    "days_with_prompts_but_no_transcripts": missing,
    "by_month_model": [
        {"month": k[0], "model": k[1], **dict(zip(FIELDS, v[:6])), "messages": v[6]}
        for k, v in sorted(agg.items())
    ],
}
json.dump(out, sys.stdout, indent=1)
