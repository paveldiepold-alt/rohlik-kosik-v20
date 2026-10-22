#!/usr/bin/env python3
"""Missing-price-only Rohlík/Košík backlog processor.

Only follows stored product URLs. Reuses tested v26 identity/pack-price parser.
Does not guess a price or change a previously verified observation.
Honors HTTP 429/403/503 and a per-product retry cooldown.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from urllib.parse import urlparse

from maintenance_v26 import apply_result, inspect_saved, hours_since

ALLOWED_HOSTS = {'Rohlík': {'rohlik.cz', 'www.rohlik.cz'},
                 'Košík': {'kosik.cz', 'www.kosik.cz'}}
MAX_BATCH = 100
MIN_DELAY = 3.3
COOLDOWN_HOURS = 24


def priced(row):
    v = row.get('price_czk')
    return row.get('price_status') == 'ok' and type(v) in (int, float) and math.isfinite(v) and v > 0


def identity(row):
    return (row.get('store'), row.get('url'))


def permitted_url(row):
    shop = row.get('store')
    url = row.get('url')
    if shop not in ALLOWED_HOSTS or not isinstance(url, str):
        return False
    try:
        u = urlparse(url)
        return u.scheme == 'https' and u.hostname in ALLOWED_HOSTS[shop] and not u.username and not u.password
    except (TypeError, ValueError):
        return False


def _buckets(rows, rules, now):
    """Round-robin category buckets rather than 100 consecutive Ariel URLs."""
    by_cat = defaultdict(list)
    for row in rows:
        ids = row.get('rule_ids') or []
        categories = [rules.get(r, 'Nezařazeno') for r in ids]
        cat = categories[0] if categories else 'Nezařazeno'
        by_cat[cat].append(row)
    for group in by_cat.values():
        group.sort(key=lambda r: (int(r.get('monitor_v26_attempts') or 0),
                                  r.get('last_monitor_attempt_at') or '',
                                  r.get('url') or ''))
    q = deque((k, deque(v)) for k, v in sorted(by_cat.items()))
    result = []
    while q:
        k, group = q.popleft()
        result.append(group.popleft())
        if group:
            q.append((k, group))
    return result


def pick_missing(items, rules, *, limit=80, now=None, cooldown_hours=COOLDOWN_HOURS):
    """Missing prices first; no refresh of existing prices while gaps remain.

    Reserve at most two places for Košík's outstanding gaps; the remainder
    targets Rohlík. Do not retry any URL inside the configured cooldown.
    """
    if not isinstance(limit, int) or not 1 <= limit <= MAX_BATCH:
        raise ValueError('limit must be 1..100')
    now = now or datetime.now(timezone.utc)
    eligible = {'Rohlík': [], 'Košík': []}
    for row in items:
        if priced(row) or not permitted_url(row):
            continue
        if hours_since(row, now=now) < cooldown_hours:
            continue
        eligible[row['store']].append(row)

    by_store = {store: _buckets(rows, rules, now) for store, rows in eligible.items()}
    # Prioritize the 192 missing Rohlík prices. Reserve up to two Košík
    # missing entries, but never waste a slot if they are on cooldown.
    kosik_count = min(len(by_store['Košík']), 2, max(0, limit - 1)) if by_store['Rohlík'] else min(len(by_store['Košík']), limit)
    selected = by_store['Rohlík'][:limit - kosik_count] + by_store['Košík'][:kosik_count]
    if len(selected) < limit:
        extra = by_store['Košík'][kosik_count:] + by_store['Rohlík'][limit - kosik_count:]
        selected.extend(extra[:limit - len(selected)])
    return selected


def _read_json(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict) or not isinstance(value.get('items'), list):
        raise ValueError('Invalid product catalogue')
    return value


def _save_json(path, value):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(dest)


def apply_observation(original, observation, *, checked_at):
    """Unchanged verified rows; evidence required for a new price."""
    if priced(original):
        return dict(original), False
    result = apply_result(original, price=observation.get('price'),
                          source=observation.get('source'), offer=observation.get('offer'),
                          status=observation.get('status', 'unknown'),
                          checked_at=checked_at, note=observation.get('note', ''))
    return result, priced(result)


def build_report(before, after, *, attempted, statuses, blocked, requested, candidates, first_errors, started_at):
    a = before['items']; b = after['items']
    if [identity(p) for p in a] != [identity(p) for p in b]:
        raise ValueError('Product identities or order changed')
    if any(priced(x) and x != y for x, y in zip(a, b)):
        raise ValueError('Previously priced product changed')
    old_ok = sum(priced(p) for p in a)
    new_ok = sum(priced(p) for p in b)
    if new_ok < old_ok:
        raise ValueError('Price coverage decreased')
    return {
        'schema': 'rk-v27-missing-price-backfill',
        'started_at': started_at,
        'finished_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'requested': requested,
        'selected': candidates,
        'attempted': attempted,
        'newly_priced': new_ok - old_ok,
        'priced_before': old_ok,
        'priced_after': new_ok,
        'missing_before': len(a) - old_ok,
        'remaining_missing': len(b) - new_ok,
        'blocked_stores': sorted(blocked),
        'statuses': dict(statuses),
        'failure_examples': first_errors[:20],
        'existing_verified_prices_untouched': True,
        'catalogue_products_unchanged': True,
    }


def run(args):
    from playwright.sync_api import sync_playwright
    now = datetime.now(timezone.utc)
    before = _read_json(args.catalog)
    all_rows = before['items']
    keys = [identity(row) for row in all_rows]
    if len(all_rows) < 1090 or len(keys) != len(set(keys)):
        raise ValueError('STOP: the source catalogue shrank or has duplicate identities')
    if not 1 <= args.limit <= MAX_BATCH or not MIN_DELAY <= args.delay <= 60:
        raise ValueError('Out-of-range limit or delay')
    rules = {x['id']: x.get('category', '') for x in before.get('rules', [])}
    targets = pick_missing(all_rows, rules, limit=args.limit, now=now)
    if not targets:
        raise RuntimeError('No currently eligible missing-price products (cooldown or complete)')

    out = json.loads(json.dumps(before, ensure_ascii=False))
    indexes = {identity(p): i for i, p in enumerate(out['items'])}
    statuses = Counter()
    blocked = set()
    failure_examples = []
    attempted = 0
    new_prices = 0
    last_attempt = {'Rohlík': 0.0, 'Košík': 0.0}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        contexts = {store: browser.new_context(locale='cs-CZ', timezone_id='Europe/Prague',
                    viewport={'width': 1366, 'height': 900}) for store in ALLOWED_HOSTS}
        pages = {shop: ctx.new_page() for shop, ctx in contexts.items()}
        try:
            for i, original in enumerate(targets, start=1):
                shop = original['store']
                if shop in blocked:
                    continue
                remaining = args.delay - (time.monotonic() - last_attempt[shop])
                if last_attempt[shop] and remaining > 0:
                    time.sleep(remaining)
                last_attempt[shop] = time.monotonic()
                try:
                    observation = inspect_saved(pages[shop], original)
                except Exception as exc:
                    observation = {'status': 'error', 'note': f'{type(exc).__name__}: {exc}'[:180], 'blocked': False}
                at = datetime.now(timezone.utc).isoformat(timespec='seconds')
                updated, success = apply_observation(original, observation, checked_at=at)
                out['items'][indexes[identity(original)]] = updated
                attempted += 1
                status = observation.get('status') or 'unknown'
                statuses[f'{shop}|{status}'] += 1
                if success:
                    new_prices += 1
                else:
                    if len(failure_examples) < 20:
                        failure_examples.append({'store': shop, 'url': original['url'],
                            'status': status, 'reason': str(observation.get('note') or '')[:160]})
                if observation.get('blocked'):
                    blocked.add(shop)
                print(f'[{i}/{len(targets)}] {shop}: {status}, new prices={new_prices}'
                      + (' – STOP shop: throttled' if shop in blocked else ''), flush=True)
        finally:
            for ctx in contexts.values():
                ctx.close()
            browser.close()

    report = build_report(before, out, attempted=attempted, statuses=statuses,
                          blocked=blocked, requested=args.limit, candidates=len(targets),
                          first_errors=failure_examples, started_at=now.isoformat(timespec='seconds'))
    # Preserve metadata from original crawler; mark last price check separately.
    out['last_price_monitor_at'] = report['finished_at']
    out['verified_current_cycle'] = report['priced_after']
    out['price_backfill_v27'] = {key: report[key] for key in
        ('finished_at', 'attempted', 'newly_priced', 'remaining_missing', 'blocked_stores', 'statuses')}
    # Always preserve a diagnostic artifact, even when no prices were obtained.
    _save_json(args.report, report)
    # Publishing is gated by the calling workflow; a zero-result run is not an update.
    if new_prices:
        _save_json(args.catalog, out)
    else:
        print('NO NEW PRICES: source catalogue untouched', flush=True)
    print('BACKFILL v27', json.dumps({k: report[k] for k in
          ('attempted', 'newly_priced', 'remaining_missing', 'blocked_stores')}, ensure_ascii=False), flush=True)
    return 0 if new_prices else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog', default='docs/data/catalog_latest.json')
    parser.add_argument('--report', default='docs/data/monitor_v27_backfill_report.json')
    parser.add_argument('--limit', type=int, default=80)
    parser.add_argument('--delay', type=float, default=4.0)
    raise SystemExit(run(parser.parse_args()))
