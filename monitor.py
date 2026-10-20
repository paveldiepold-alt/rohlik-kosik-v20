"""Rohlík × Košík v20: conservative observations for explicitly linked products.

No price is invented. A successful HTTP response does not imply a valid price.
Runs without login, and cannot verify local availability/prices for PSČ 149 00.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from visible_price import VISIBLE_PRICE_JS, choose_visible_price

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "docs" / "data"
WATCHLIST = ROOT / "watchlist.json"
PRICE_META = {'product:price:amount', 'og:price:amount'}


def fold(value: object) -> str:
    s = unicodedata.normalize('NFKD', str(value or ''))
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def as_money(v: object) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        raw = str(v).strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
        if not re.fullmatch(r'\d{1,6}(?:\.\d{1,2})?', raw):
            return None
        n = float(raw)
    return round(n, 2) if 0 < n < 100_000 else None


def choose_price(candidates: list[dict]) -> tuple[float | None, str | None, str]:
    """Accept exactly one unique CZK price from product-scoped structured data."""
    good: list[tuple[float, str]] = []
    for cand in candidates:
        curr = str(cand.get('currency') or 'CZK').upper().strip()
        if curr not in ('CZK', 'KČ', 'KC'):
            continue
        n = as_money(cand.get('price'))
        if n is not None and cand.get('source') in ('product-jsonld', 'product-meta'):
            good.append((n, cand['source']))
    values = sorted({v for v, _ in good})
    if not values:
        return None, None, 'Stránka neposkytla jednoznačnou cenu produktu'
    if len(values) != 1:
        return None, None, 'Konfliktní produktové ceny ve strukturovaných datech'
    return values[0], good[0][1], 'Veřejná strukturovaná cena; PSČ nepotvrzeno'


def valid_title(title: str | None, entry: dict) -> bool:
    """Require product title, not a redirected home page or challenge screen."""
    t = fold(title)
    if len(t) < 5 or any(x in t for x in ('captcha', 'access denied', 'prihlaseni', 'overeni ze nejste robot')):
        return False
    brand = entry.get('brand')
    if brand:
        return fold(brand) in t
    tokens = [x for x in re.findall(r'[a-z0-9]{4,}', fold(entry['label'])) if x not in {'original', 'mlecna', 'kapsle'}]
    return bool(tokens) and sum(x in t for x in tokens[:4]) >= min(2, len(tokens))


def extract_jsonld_prices(raw: str) -> list[dict]:
    """Pure parser for unit tests. Ignores offers unrelated to a Product node."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    output: list[dict] = []

    def visit(node: object, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(node, list):
            for item in node:
                visit(item, depth + 1)
            return
        if not isinstance(node, dict):
            return
        types = node.get('@type') or []
        types = types if isinstance(types, list) else [types]
        if 'Product' in types:
            offers = node.get('offers') or []
            offers = offers if isinstance(offers, list) else [offers]
            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                raw_price = offer.get('price') or offer.get('lowPrice')
                if raw_price is not None:
                    output.append({'price': raw_price, 'currency': offer.get('priceCurrency', 'CZK'), 'source': 'product-jsonld'})
        for key in ('@graph', 'mainEntity', 'itemListElement'):
            if key in node:
                visit(node[key], depth + 1)
    visit(data)
    return output


def from_browser_payload(payload: dict) -> tuple[float | None, str | None, str]:
    visible_price, visible_source, visible_note = choose_visible_price(payload.get('visible_prices', []))
    if visible_price is not None:
        return visible_price, visible_source, visible_note
    candidates = []
    for raw in payload.get('jsonld', []):
        candidates.extend(extract_jsonld_prices(raw))
    for m in payload.get('meta', []):
        if m.get('itemprop') == 'price' or m.get('property') in PRICE_META:
            candidates.append({'price': m.get('content'), 'currency': m.get('currency', 'CZK'), 'source': 'product-meta'})
    structured_price, structured_source, structured_note = choose_price(candidates)
    if structured_price is not None:
        return structured_price, structured_source, structured_note
    return None, None, f'{visible_note}; {structured_note}'


def browser_extract(page) -> dict:
    payload = page.evaluate("""() => ({
       title: (document.querySelector('h1')?.textContent || '').trim(),
       jsonld: [...document.querySelectorAll('script[type="application/ld+json"]')].map(e => e.textContent),
       meta: [...document.querySelectorAll('meta[itemprop="price"],meta[property="product:price:amount"],meta[property="og:price:amount"]')]
         .map(m => ({itemprop:m.getAttribute('itemprop'),property:m.getAttribute('property'),content:m.getAttribute('content'),currency:m.getAttribute('data-currency')||'CZK'})),
    })""")
    payload["visible_prices"] = page.evaluate(VISIBLE_PRICE_JS)
    return payload


def inspect(page, entry: dict, checked_at: str) -> dict:
    data = {'id': entry['id'], 'store': entry['store'], 'label': entry['label'], 'url': entry['url'],
            'checked_at': checked_at, 'status': 'unknown', 'price_czk': None, 'title': None,
            'source': None, 'note': '', 'http_status': None, 'postcode_verified': False}
    hostname = urlparse(entry['url']).hostname or ''
    host_ok = hostname in ('www.rohlik.cz', 'rohlik.cz', 'www.kosik.cz', 'kosik.cz')
    if not host_ok:
        data['status'] = 'invalid_url'
        data['note'] = 'URL není z povoleného obchodu'
        return data
    try:
        response = page.goto(entry['url'], wait_until='domcontentloaded', timeout=35000)
        status = response.status if response else None
        data['http_status'] = status
        if not status or status >= 400:
            data['status'] = 'http_error'
            data['note'] = 'HTTP ' + str(status) if status else 'Bez odpovědi HTTP'
            return data
        page.wait_for_timeout(1200)
        payload = browser_extract(page)
        title = payload.get('title') or ''
        data['title'] = title or None
        if not valid_title(title, entry):
            data['status'] = 'title_mismatch'
            data['note'] = 'Produktový nadpis neodpovídá požadovanému výrobku'
            return data
        price, source, note = from_browser_payload(payload)
        if price is None:
            data['status'] = 'price_unverified'
            data['note'] = note
            return data
        data.update(status='ok', price_czk=price, source=source, note=note)
    except Exception as exc:
        data['status'] = 'error'
        data['note'] = f'{type(exc).__name__}: {str(exc)[:160]}'
    return data


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def make_report(results: list[dict], previous: dict, now: str) -> dict:
    previous_by_id = {e['id']: e for e in previous.get('items', []) if e.get('status') == 'ok' and as_money(e.get('price_czk'))}
    enriched = []
    for row in results:
        v = dict(row)
        old = previous_by_id.get(v['id'])
        prev = old.get('price_czk') if old else None
        v['previous_observed_price_czk'] = prev
        v['drop_since_previous_pct'] = None
        if v['status'] == 'ok' and prev and prev > v['price_czk']:
            v['drop_since_previous_pct'] = round(100 * (prev - v['price_czk']) / prev, 1)
        enriched.append(v)
    return {'schema': 'rk-v20-observations-1', 'checked_at': now, 'postcode': '149 00',
            'postcode_verified': False, 'plan_count': len(results),
            'verified_price_count': sum(x['status'] == 'ok' for x in enriched),
            'status': 'partial_or_unverified' if any(x['status'] != 'ok' for x in enriched) else 'all_listed_products_observed',
            'scope': 'Pouze konkrétní odkazy (nikoli celý katalog 75 pravidel)', 'items': enriched}


def save_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def run() -> int:
    source = json.loads(WATCHLIST.read_text(encoding='utf-8'))
    products = source['specific_products']
    if not products or len({p['id'] for p in products}) != len(products):
        raise RuntimeError('Neplatné nebo duplicitní product ID')
    prior = load_json(DATA / 'latest.json', {})
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    results = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale='cs-CZ', timezone_id='Europe/Prague', viewport={'width': 1366, 'height': 900})
            for index, entry in enumerate(products, start=1):
                row = inspect(page, entry, now)
                results.append(row)
                print(f"[{index}/{len(products)}] {entry['store']} {entry['id']}: {row['status']} {row.get('price_czk')}", flush=True)
        finally:
            browser.close()
    report = make_report(results, prior, now)
    save_json(DATA / 'latest.json', report)
    history = load_json(DATA / 'history.json', [])
    if not isinstance(history, list):
        history = []
    history.extend({'id': row['id'], 'store': row['store'], 'checked_at': now, 'price_czk': row['price_czk']}
                   for row in results if row['status'] == 'ok')
    save_json(DATA / 'history.json', history[-10000:])
    print('VERIFIED PRICES:', report['verified_price_count'], '/', report['plan_count'], flush=True)
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        rows = ['## Rohlík × Košík v20: výsledek sběru', '',
                f'**Ověřené ceny: {report["verified_price_count"]}/{report["plan_count"]}**',
                'Ceny pro PSČ 149 00 nebyly ověřené.', '',
                '| Obchod | Výrobek | HTTP | Stav | Cena |', '|---|---|---|---|---|']
        for row in results:
            label = row['label'].replace('|', '/')
            price = f'{row["price_czk"]:.2f} Kč' if row['price_czk'] is not None else 'nezjištěna'
            rows.append(f'| {row["store"]} | {label} | {row["http_status"] or "–"} | {row["status"]} | {price} |')
        rows += ['', 'Při nezjištěné ceně otevři diagnostický artefakt `rk-v20-results` a zkontroluj pole `note`.', '']
        with open(summary, 'a', encoding='utf-8') as f:
            f.write('\n'.join(rows))
    # Real unknowns must not be disguised as a successful price scan.
    return 0 if report['verified_price_count'] else 2


if __name__ == '__main__':
    try:
        sys.exit(run())
    except Exception as exc:
        print('FATAL:', repr(exc), file=sys.stderr)
        sys.exit(2)
