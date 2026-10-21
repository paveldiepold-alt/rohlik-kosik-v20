#!/usr/bin/env python3
"""Safe bounded merchant breadcrumb enrichment for v27 (manual only).

Requires Playwright and files from the existing repository (store_taxonomy,
price_v23). No price scraping or manipulation; original v26 remains untouched.
The staging file is synchronized with NEWEST v26 source prices on every run.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import json
import re
from pathlib import Path
import time
from urllib.parse import urlparse
from catalog_v27 import TRUSTED_SOURCES, identity, price_snapshot, write_json, merchant_category, norm, trusted_path

SHOPS = {'Košík': 'kosik.cz', 'Rohlík': 'rohlik.cz'}
ENRICH_FIELDS = ('store_category_path', 'category_source', 'product_description',
                 'taxonomy_checked_at', 'v27_category_probe_status',
                 'v27_category_probe_note', 'v27_category_checked_at',
                 'v27_category_probe_attempts')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def safe_url(row):
    shop, url = row.get('store'), row.get('url')
    if shop not in SHOPS or not isinstance(url, str): return False
    parts = urlparse(url)
    host = (parts.hostname or '').removeprefix('www.')
    try:
        secure_port = parts.port in (None, 443)
    except ValueError:
        return False
    product_path = (re.fullmatch(r'/p\d+(?:-[\w-]+)?/?', parts.path, re.I)
                    if shop == 'Košík' else
                    re.fullmatch(r'/\d{5,}(?:-[\w-]+)?/?', parts.path, re.I))
    return (parts.scheme == 'https' and host == SHOPS[shop] and bool(product_path) and
            parts.username is None and parts.password is None and secure_port and
            not parts.query and not parts.fragment)


def sync_new_prices(source, staging):
    """Keep fresh price records from v26, transplant ONLY saved category evidence."""
    if not isinstance(source, dict) or not isinstance(source.get('items'), list):
        raise ValueError('Invalid v26 source')
    old_rows = (staging or {}).get('items', [])
    old = {identity(p): p for p in old_rows}
    source_keys = [identity(p) for p in source['items']]
    if len(old) != len(old_rows) or len(set(source_keys)) != len(source_keys):
        raise ValueError('Duplicate product identities in staging or current v26 source')
    # Never silently drop products already staged in v27 if the original
    # source changes; require an explicit review instead of data loss.
    missing = set(old) - set(source_keys)
    if missing:
        raise ValueError(f'Current v26 is missing {len(missing)} previously staged products. Stop before publishing.')
    merged = json.loads(json.dumps(source, ensure_ascii=False))
    # Control data belongs solely to the v27 staging snapshot; never to v26.
    if staging and isinstance(staging.get('v27_probe_control'), dict):
        merged['v27_probe_control'] = json.loads(json.dumps(staging['v27_probe_control']))
    for row in merged['items']:
        backup = old.get(identity(row))
        if not backup: continue
        if not trusted_path(row) and trusted_path(backup):
            for k in ENRICH_FIELDS:
                if k in backup: row[k] = backup[k]
        else:
            for k in ('v27_category_probe_status', 'v27_category_probe_note', 'v27_category_checked_at',
                 'v27_category_probe_attempts'):
                if k in backup: row[k] = backup[k]
    for a,b in zip(source['items'],merged['items']):
        if price_snapshot(a) != price_snapshot(b): raise AssertionError('Price fields changed during staging sync')
    return merged


def eligible(row, now, retry_hours=24):
    # A trusted but not-yet-mapped breadcrumb needs taxonomy review, NOT another
    # HTTP request to the merchant. Keep unknown categories as review entries.
    if trusted_path(row): return False
    at = row.get('v27_category_checked_at')
    if at:
        try:
            when = datetime.fromisoformat(at.replace('Z','+00:00'))
            # Repeated failed attempts are not useful every day. Back off to
            # 3 days, then a week, without inventing an unavailable product.
            attempts = max(0, int(row.get('v27_category_probe_attempts', 0)))
            hours = retry_hours if attempts <= 1 else 72 if attempts == 2 else 168
            if (now - when).total_seconds() < hours*3600: return False
        except (ValueError, TypeError, OverflowError): pass
    return safe_url(row)


def active_shop_blocks(control, now=None):
    """Return only ongoing merchant backoffs; expired entries are ignored."""
    now = now or datetime.now(timezone.utc)
    until = control.get('shop_backoff_until', {}) if isinstance(control, dict) else {}
    active = {}
    if isinstance(until, dict):
        for shop, stamp in until.items():
            if shop not in SHOPS or not isinstance(stamp, str): continue
            try:
                parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                if parsed.tzinfo and parsed > now: active[shop] = parsed.isoformat()
            except ValueError: pass
    return active


def pick(items, limit, now=None, blocked_stores=(), excluded_keys=()):
    now = now or datetime.now(timezone.utc)
    blocked_stores = set(blocked_stores)
    excluded_keys = set(excluded_keys)
    queues = {store: [] for store in SHOPS if store not in blocked_stores}
    for row in items:
        if row.get('store') in queues and identity(row) not in excluded_keys and eligible(row, now):
            queues[row['store']].append(row)
    for q in queues.values():
        q.sort(key=lambda x: (x.get('v27_category_checked_at', ''), x.get('url', '')))
    selected = []
    while len(selected) < limit and any(queues.values()):
        for shop in SHOPS:
            if queues.get(shop): selected.append(queues[shop].pop(0))
            if len(selected) >= limit: break
    return selected


def probe_one(page, item):
    from store_taxonomy import extract_shop_context
    from price_v23 import product_identity
    try:
        response = page.goto(item['url'], wait_until='domcontentloaded', timeout=25000)
        code = response.status if response else 0
        if code in (403, 429, 503):
            return {'status':'blocked', 'note':f'HTTP {code}', 'blocked':True}
        if code != 200:
            return {'status':'http_error', 'note':f'HTTP {code}', 'blocked':False}
        # Product redirects must remain on the same intended merchant.
        if not safe_url({'store': item['store'], 'url': page.url}):
            return {'status':'redirect_outside_shop', 'note':'Přesměrování mimo e-shop; kategorii nelze potvrdit', 'blocked':False}
        page.wait_for_timeout(650)
        # An anti-bot page returning 200 is not a product page. Do not retry
        # aggressively or mistake its heading for a product identity issue.
        challenge = page.locator('iframe[src*=recaptcha], iframe[src*=hcaptcha], #challenge-running, #cf-challenge-running, [data-sitekey]').count()
        if challenge:
            return {'status':'blocked','note':'Access challenge visible in product page', 'blocked':True}
        context = extract_shop_context(page)
        # The product heading is required. Do not attribute another item's breadcrumb.
        found_title = str(page.locator('h1').first.text_content(timeout=4000) or '').strip()
        expected = item.get('title') or item.get('name') or ''
        # Exact one-word names may be valid even though the legacy identity
        # matcher requires two shared tokens. Do NOT allow substring matches.
        if not (product_identity(expected, found_title) or (norm(expected) and norm(expected) == norm(found_title))):
            return {'status':'identity_mismatch','note':'Neshoda titulku; nelze důvěřovat kategorii', 'blocked':False}
        path = context.get('store_category_path')
        if isinstance(path, list) and len(path) >= 2 and context.get('category_source') in TRUSTED_SOURCES:
            return {'status':'category_found', 'note':context.get('category_source'),
                    'context':context, 'blocked':False}
        return {'status':'category_missing', 'note':context.get('taxonomy_error') or 'Chybí důvěryhodný breadcrumb',
                'blocked':False}
    except Exception as exc:
        return {'status':'error', 'note':f'{type(exc).__name__}: {str(exc)[:160]}', 'blocked':False}


def run(args):
    # Fail immediately, before any network request, if a proposed output could
    # overwrite the authoritative source or the other result file.
    guard = [Path(x).resolve() for x in (args.input, args.staging, args.report)]
    if len(set(guard)) != 3:
        raise ValueError('All input/output paths must differ, preserving v26 source')
    source = load(args.input)
    stage_path = Path(args.staging)
    stage = load(stage_path) if stage_path.exists() else None
    merged = sync_new_prices(source, stage)
    before = {identity(p): price_snapshot(p) for p in merged['items']}
    now = datetime.now(timezone.utc)
    control = merged.setdefault('v27_probe_control', {})
    backoff = active_shop_blocks(control, now)
    initial_backoff = dict(backoff)
    targets = pick(merged['items'], max(0, min(args.limit, 120)), now=now,
                   blocked_stores=backoff)
    by_id = {identity(p): p for p in merged['items']}
    blocked, statuses = set(), Counter()
    attempted = set()
    requested_limit = max(0, min(args.limit, 120))
    if targets:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as play:
            browser = play.chromium.launch(headless=True, args=['--no-sandbox'])
            pages = {s: browser.new_page(locale='cs-CZ',timezone_id='Europe/Prague') for s in SHOPS}
            try:
                # A merchant may block on its first attempt. Backfill the
                # remaining bounded slots from the still reachable merchant
                # instead of wasting half of the batch on skipped requests.
                queue = list(targets)
                selected_keys = {identity(p) for p in queue}
                while queue and len(attempted) < requested_limit:
                    item = queue.pop(0)
                    shop = item['store']
                    if shop in blocked: continue
                    attempted.add(identity(item))
                    time.sleep(max(2.5, args.delay))
                    result = probe_one(pages[shop], item)
                    current = by_id[identity(item)]
                    current['v27_category_checked_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
                    current['v27_category_probe_status'] = result['status']
                    current['v27_category_probe_note'] = result['note'][:240]
                    current['v27_category_probe_attempts'] = int(current.get('v27_category_probe_attempts', 0)) + 1
                    if result.get('context'):
                        for k in ('store_category_path','category_source','product_description'):
                            current[k] = result['context'].get(k)
                        current['taxonomy_checked_at'] = current['v27_category_checked_at']
                    statuses[f'{shop}|{result["status"]}'] += 1
                    if result.get('blocked'):
                        blocked.add(shop)
                        backoff[shop] = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec='seconds')
                    print(f'{len(attempted)}/{requested_limit} {shop}: {result["status"]}',flush=True)
                    if result.get('blocked') and len(attempted) < requested_limit:
                        excluded = selected_keys | attempted
                        spare = pick(merged['items'], requested_limit - len(attempted),
                                     now=datetime.now(timezone.utc),
                                     blocked_stores=set(blocked) | set(initial_backoff),
                                     excluded_keys=excluded)
                        queue.extend(spare)
                        selected_keys.update(identity(p) for p in spare)
            finally:
                for page in pages.values(): page.close()
                browser.close()
    after = {identity(p): price_snapshot(p) for p in merged['items']}
    if before != after:raise AssertionError('A price changed during taxonomy collection')
    control['shop_backoff_until'] = backoff
    control['last_batch_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    # Staging updates are atomic; original v26 source is never written.
    write_json(stage_path, merged)
    report = {'schema':'rk-v27-category-probe','at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'total':len(merged['items']),'source_generated_at':source.get('generated_at'),
              'selected_initial':len(targets),'attempted':sum(statuses.values()),
              'blocked_stores':sorted(blocked),'preexisting_shop_backoffs':sorted(initial_backoff),
              'shop_backoff_until':backoff,'statuses':dict(statuses),
              'still_without_category':sum(merchant_category(p)[0] is None for p in merged['items']),
              'still_needing_probe':sum(not trusted_path(p) for p in merged['items']),
              'trusted_but_unmapped':sum(trusted_path(p) and merchant_category(p)[0] is None for p in merged['items']),
              'prices_unchanged':True,'source_file_untouched':True}
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='docs/data/catalog_latest.json')
    parser.add_argument('--staging', default='docs/data/catalog_v27_staging.json')
    parser.add_argument('--report', default='docs/data/catalog_v27_probe.json')
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--delay', type=float, default=3.1)
    raise SystemExit(run(parser.parse_args()))
