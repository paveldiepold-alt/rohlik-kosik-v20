#!/usr/bin/env python3
"""Read-only price diagnosis of selected stored products, never a price updater.

Uses the existing conservative v26 merchant extractor. Treats a seller's 429 as
an instruction to stop contacting that store for the remainder of the run.
Does not use account login, fingerprint spoofing, APIs or captcha circumvention.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.parse import urlparse

SHOPS = ('Rohlík', 'Košík')
GOOD_HOSTS = {
    'Rohlík': {'rohlik.cz', 'www.rohlik.cz'},
    'Košík': {'kosik.cz', 'www.kosik.cz'},
}


def product_key(product: dict) -> tuple[str, str]:
    return str(product.get('store', '')), str(product.get('url', ''))


def eligible(product: dict) -> bool:
    store, url = product_key(product)
    if store not in GOOD_HOSTS or not url.startswith('https://'):
        return False
    u = urlparse(url)
    return (u.scheme == 'https' and u.hostname in GOOD_HOSTS[store]
            and bool(u.path) and not (u.username or u.password))


def priority(product: dict) -> str:
    if product.get('price_status') == 'ok' and isinstance(product.get('price_czk'), (int, float)):
        return 'Rohlík_control' if product['store'] == 'Rohlík' else 'Košík_control'
    if product['store'] == 'Košík':
        return 'Košík_missing'
    if product.get('http_status') == 429:
        return 'Rohlík_http429'
    return 'Rohlík_ambiguous'


def choose_products(items: list[dict], limit: int) -> list[dict]:
    """Controls + representative missing prices from both shops. Deterministic."""
    if not 1 <= limit <= 25:
        raise ValueError('limit must be 1..25')
    queues = {k: [] for k in ('Rohlík_http429', 'Rohlík_ambiguous', 'Košík_missing',
                             'Rohlík_control', 'Košík_control')}
    seen = set()
    for row in items:
        if not eligible(row):
            continue
        key = product_key(row)
        if key in seen:
            continue
        seen.add(key)
        queues[priority(row)].append(row)
    # Cycle favoring diagnosis without starving controls and the other shop.
    # Front-load ambiguity cases so a 429 discovered later does not prevent all
    # analysis of price parsing for that same store.
    order = ['Rohlík_ambiguous', 'Košík_missing', 'Rohlík_http429',
             'Rohlík_control', 'Rohlík_ambiguous', 'Rohlík_http429',
             'Košík_control', 'Rohlík_ambiguous', 'Rohlík_http429',
             'Rohlík_http429', 'Rohlík_ambiguous']
    chosen = []
    while len(chosen) < limit and any(queues.values()):
        added = False
        for bucket in order:
            if queues[bucket] and len(chosen) < limit:
                chosen.append(queues[bucket].pop(0))
                added = True
        if not added:
            break
    return chosen


def categorize(result: dict) -> str:
    if result.get('status') == 'ok' and isinstance(result.get('price_czk'), (float, int)):
        return 'price_read_ok'
    if result.get('http_status') == 429:
        return 'blocked_429'
    if result.get('http_status') in (403, 503):
        return 'shop_unavailable'
    if result.get('status') in ('title_mismatch', 'invalid_url'):
        return result['status']
    if result.get('status') == 'price_unverified':
        return 'ambiguous_or_missing_price'
    return 'technical_or_http_error'


def sanitize_report_row(product: dict, result: dict) -> dict:
    diag = result.get('diagnostics') if isinstance(result.get('diagnostics'), dict) else {}
    return {
        'store': product['store'], 'url': product['url'],
        'name': (product.get('title') or product.get('name') or '')[:150],
        'previous_price_status': product.get('price_status'),
        'previous_price_czk': product.get('price_czk'),
        'previous_http_status': product.get('http_status'),
        'result': categorize(result),
        'new_http_status': result.get('http_status'),
        'new_price_candidate_czk': result.get('price_czk') if categorize(result) == 'price_read_ok' else None,
        'price_source': result.get('source'),
        'note': str(result.get('note') or '')[:300],
        'diagnostics': {key: diag.get(key) for key in
          ('visible_candidates_count', 'visible_candidates_sample',
           'jsonld_blocks_count', 'price_meta_count', 'detail_excerpt') if key in diag},
    }


def report_summary(source: dict, results: list[dict], skipped: list[dict], blocked: set[str], source_hash: str) -> dict:
    items = source['items']
    priced = sum(p.get('price_status') == 'ok' and isinstance(p.get('price_czk'), (float, int)) for p in items)
    counts = Counter(f"{p['store']}|{p['result']}" for p in results)
    return {
        'schema': 'rk-v27-price-diagnostic-only',
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source_generated_at': source.get('generated_at'),
        'source_sha256': source_hash,
        'catalog_products': len(items), 'catalog_priced_before': priced,
        'catalog_missing_before': len(items) - priced,
        'attempted': len(results), 'skipped_due_to_block': len(skipped),
        'blocked_shops': sorted(blocked), 'statuses': dict(counts),
        'candidate_prices_observed_but_not_written': sum(p['result']=='price_read_ok' for p in results),
        'catalog_untouched': True,
        'result_rows': results, 'skipped_rows': skipped,
        'note': 'Candidates are diagnostic only; no price or product data is written to GitHub or the catalogue.',
    }


def run(args) -> int:
    from playwright.sync_api import sync_playwright
    # The repository main branch can carry an older monitor.py. Always load
    # the exact v26 parser fetched into the read-only dependency folder.
    import sys
    deps = Path('.v27-price/deps')
    if not (deps / 'monitor.py').is_file():
        raise RuntimeError('Missing trusted v26 parser dependencies')
    sys.path.insert(0, str(deps.resolve()))
    from monitor import inspect
    source_path = Path(args.input)
    raw = source_path.read_bytes()
    before = sha256(raw).hexdigest()
    source = json.loads(raw)
    if not isinstance(source, dict) or not isinstance(source.get('items'), list):
        raise ValueError('Invalid catalogue')
    targets = choose_products(source['items'], args.limit)
    if not targets: raise ValueError('No valid product URLs')
    results, skipped, blocked = [], [], set()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        contexts = {s: browser.new_context(locale='cs-CZ', timezone_id='Europe/Prague',
                                             viewport={'width':1280,'height':850}) for s in SHOPS}
        pages = {s: contexts[s].new_page() for s in SHOPS}
        try:
            for index, product in enumerate(targets, 1):
                shop = product['store']
                if shop in blocked:
                    skipped.append({'store': shop, 'url': product['url'], 'reason': 'blocked_in_this_run'})
                    continue
                time.sleep(args.delay)
                record = inspect(pages[shop], {
                    'id': product['url'], 'store': shop,
                    'label': product.get('title') or product.get('name') or '',
                    'url': product['url']}, datetime.now(timezone.utc).isoformat(timespec='seconds'))
                entry = sanitize_report_row(product, record)
                results.append(entry)
                if entry['result'] in ('blocked_429', 'shop_unavailable'):
                    blocked.add(shop)
                print(f"[{index}/{len(targets)}] {shop} {entry['result']} "
                      f"old={entry['previous_price_status']} http={entry['new_http_status']}", flush=True)
        finally:
            for ctx in contexts.values(): ctx.close()
            browser.close()
    if sha256(source_path.read_bytes()).hexdigest() != before:
        raise RuntimeError('INPUT MODIFIED - STOP')
    report = report_summary(source, results, skipped, blocked, before)
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print('DIAGNOSTIC:', json.dumps({k: report[k] for k in
          ('attempted','blocked_shops','statuses','candidate_prices_observed_but_not_written')}, ensure_ascii=False))
    return 0  # Diagnostic outcome, including 429, is not a CI software failure.


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Read-only price-probe v27')
    p.add_argument('--input', default='.v27-price/source.json')
    p.add_argument('--report', default='.v27-price/report.json')
    p.add_argument('--limit', type=int, default=12)
    p.add_argument('--delay', type=float, default=4.0)
    args = p.parse_args()
    if not 1 <= args.limit <= 25: p.error('limit must be 1..25')
    if not 4.0 <= args.delay <= 60: p.error('delay must be 4..60 seconds')
    raise SystemExit(run(args))
