#!/usr/bin/env python3
"""Run a one-time enhanced price pass on missing prices using v27 safeguards.

This does NOT overwrite any previously verified price; only missing products
are eligible. Product attempts by this new parser have their own 24h cooldown
marker, so a same-day rerun cannot repeatedly hammer retailer pages.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import price_backfill_v27 as base
from maintenance_v26 import hours_since
from price_details_v27b import improved_observation

_COOLDOWN = 24


def pick_new_parser(items, rules, *, limit=80, now=None, cooldown_hours=0):
    """v27b one-off check despite older parser attempts; preserve v27b backoff."""
    now = now or datetime.now(timezone.utc)
    available = [x for x in items if hours_since(x, key='monitor_v27b_last_probe_at', now=now) >= _COOLDOWN]
    return _ORIGINAL_PICK(available, rules, limit=limit, now=now, cooldown_hours=0)


def record_new_parser_attempt(original, observation, *, checked_at):
    result, success = _ORIGINAL_APPLY(original, observation, checked_at=checked_at)
    result['monitor_v27b_last_probe_at'] = checked_at
    return result, success


_ORIGINAL_PICK = base.pick_missing
_ORIGINAL_APPLY = base.apply_observation


def run(args):
    # v27's tested identity gate, rollback behavior, browser setup and source
    # preservation remain in charge. Only the candidate selection and fallback
    # parser are extended.
    # Handle a same-day rerun cleanly, instead of failing or retrying the same URL.
    current = json.loads(Path(args.catalog).read_text(encoding='utf-8'))
    rule_map = {x['id']: x.get('category', '') for x in current.get('rules', [])}
    available = pick_new_parser(current['items'], rule_map, limit=args.limit)
    if not available:
        priced_before = sum(base.priced(x) for x in current['items'])
        report = {
            'schema': 'rk-v27b-cooldown', 'selected': 0, 'attempted': 0,
            'newly_priced': 0, 'priced_before': priced_before,
            'priced_after': priced_before,
            'remaining_missing': len(current['items'])-priced_before,
            'blocked_stores': [], 'statuses': {},
            'note': 'Nothing eligible: checked by this parser in previous 24h or all prices present'
        }
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        return 0
    original_inspect = base.inspect_saved
    base.pick_missing = pick_new_parser
    base.apply_observation = record_new_parser_attempt
    base.inspect_saved = improved_observation
    try:
        status = base.run(args)
    finally:
        base.pick_missing = _ORIGINAL_PICK
        base.apply_observation = _ORIGINAL_APPLY
        base.inspect_saved = original_inspect
    # v27 returns 2 on zero verified results; a diagnostic-only run is normal,
    # but the caller must check report.newly_priced before publishing.
    return 0 if status in (0, 2) else status


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--catalog', default='docs/data/catalog_latest.json')
    p.add_argument('--report', default='docs/data/monitor_v27b_price_report.json')
    p.add_argument('--limit', type=int, default=100)
    p.add_argument('--delay', type=float, default=4.0)
    raise SystemExit(run(p.parse_args()))
