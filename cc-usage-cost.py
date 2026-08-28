#!/usr/bin/env python3
"""Price the JSON from cc-usage-tokens.py at Claude API list rates.

Usage: cc-usage-cost.py usage.json [more.json ...]

Rates are $ per million tokens, in this order:
(input, 5 minute cache write, 1 hour cache write, cache read, output).
Copied from https://platform.claude.com/docs/en/about-claude/pricing on 2026-08-28.
"""
import collections
import json
import sys

PRICES = {
    "claude-fable-5":    (10, 12.5, 20, 1.0, 50),
    "claude-opus-5":     (5, 6.25, 10, 0.5, 25),
    "claude-opus-4-8":   (5, 6.25, 10, 0.5, 25),
    "claude-opus-4-7":   (5, 6.25, 10, 0.5, 25),
    "claude-opus-4-6":   (5, 6.25, 10, 0.5, 25),
    "claude-opus-4-5":   (5, 6.25, 10, 0.5, 25),
    "claude-sonnet-5":   (2, 2.5, 4, 0.2, 10),
    "claude-sonnet-4-6": (3, 3.75, 6, 0.3, 15),
    "claude-sonnet-4-5": (3, 3.75, 6, 0.3, 15),
    "claude-haiku-4-5":  (1, 1.25, 2, 0.1, 5),
}


def rate(model):
    # longest prefix wins, so claude-opus-4-8 does not match claude-opus-4
    for k in sorted(PRICES, key=len, reverse=True):
        if model.startswith(k):
            return PRICES[k]
    raise SystemExit(f"no price for model {model}, add it to PRICES")


def split_cost(r):
    """Return (input, cache_write, cache_read, output) dollars for one month+model row."""
    inp, w5, w1, rd, out = rate(r["model"])
    c5, c1 = r["c5m"], r["c1h"]
    if c5 + c1 == 0:
        # older transcripts have no TTL breakdown, assume the cheaper 5 minute write
        c5 = r["cache_creation_input_tokens"]
    return (
        r["input_tokens"] * inp / 1e6,
        (c5 * w5 + c1 * w1) / 1e6,
        r["cache_read_input_tokens"] * rd / 1e6,
        r["output_tokens"] * out / 1e6,
    )


by_host = {}
active_days = {}
by_month = collections.Counter()
by_model = collections.Counter()
tokens = collections.Counter()
share = collections.Counter()
grand = 0
messages = 0

for path in sys.argv[1:]:
    d = json.load(open(path))
    host = d["host"]
    by_host[host] = 0
    active_days[host] = d["active_days"]
    for r in d["by_month_model"]:
        parts = split_cost(r)
        c = sum(parts)
        grand += c
        by_host[host] += c
        by_month[r["month"]] += c
        by_model[r["model"]] += c
        messages += r["messages"]
        for name, v in zip(("input", "cache_write", "cache_read", "output"), parts):
            share[name] += v
        for f in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            tokens[f] += r[f]

print(f"GRAND TOTAL at API list price: ${grand:,.2f}   ({messages:,} assistant messages)")
print("by host:  " + ", ".join(f"{h} ${c:,.2f} ({active_days[h]} active days)" for h, c in by_host.items()))
print("by month: " + ", ".join(f"{m} ${c:,.2f}" for m, c in sorted(by_month.items())))
print("by model: " + ", ".join(f"{m} ${c:,.2f}" for m, c in by_model.most_common()))
print("tokens:   " + ", ".join(f"{k}={v / 1e9:.2f}B" for k, v in tokens.items()))
print("cost split: " + ", ".join(f"{k} ${v:,.0f} ({v / grand * 100:.0f}%)" for k, v in share.items()))
