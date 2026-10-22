#!/usr/bin/env python3
"""v27: retailer-path-first common taxonomy + independent price diagnostics.

No product is deleted, no price is changed, and no category is inferred from a
product name or watchlist query. Output is separate from the v26 source JSON.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import unicodedata
from rule_path_v27 import verify_specific_rule

TRUSTED_SOURCES = frozenset({
    'jsonld_breadcrumb', 'dom_breadcrumb', 'jsonld_product_category',
})
PRICE_FIELDS = (
    'price_czk', 'price_status', 'price_source', 'checked_at', 'multibuy',
    'original_price_czk', 'discount_pct', 'offer_valid_until',
    'price_history_previous_czk', 'price_history_previous_at',
    'legacy_price_czk', 'legacy_price_status', 'legacy_price_source',
    'pre_v23_price_czk', 'pre_v23_price_status',
)


def norm(text):
    s = unicodedata.normalize('NFKD', str(text or '')).casefold()
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', s))


def match(value, *phrases):
    """Compare whole category segments, not product titles or substring hits."""
    n = norm(value)
    return any(n == norm(p) for p in phrases)


def has_seg(segments, *phrases):
    return any(match(s, *phrases) for s in segments)


def segment_starts(segments, *prefixes):
    return any(norm(s).startswith(norm(prefix) + ' ') or match(s, prefix)
               for s in segments for prefix in prefixes)


def trusted_path(item):
    """A usable retailer path, independent of whether v27 knows its mapping."""
    path = item.get('store_category_path')
    return (isinstance(path, list) and len(path) >= 2
            and item.get('category_source') in TRUSTED_SOURCES
            and all(isinstance(x, str) and norm(x) for x in path))


def mapped_known_merchant_path(parts):
    """Conservative extension from *merchant breadcrumbs* only (never product title).

    Every rule checks the parent aisle together with a specific child/leaf.
    Generic cheese/marinated-meat paths stay under human review rather than
    being forcibly assigned to a rule-specific subcategory.
    """
    root, branch = parts[:2]
    tail = parts[1:]
    # Baby wipes and sanitary paper are a shared hygiene shelf in the dashboard.
    if root == 'deti' and branch == 'vlhcene ubrousky':
        return 'Papír a hygiena', 'Dětské vlhčené ubrousky podle cesty e-shopu'
    if root == 'dite' and branch == 'pleny a ubrousky' and has_seg(tail, 'vlhčené ubrousky'):
        return 'Papír a hygiena', 'Vlhčené ubrousky pro děti podle cesty e-shopu'
    if root == 'dite' and branch == 'detska kosmetika' and has_seg(tail, 'zubní hygiena'):
        return 'Dentální hygiena', 'Dětská dentální hygiena podle cesty e-shopu'

    if root in {'drogerie', 'drogerie a kosmetika'}:
        if branch == 'papirova a vatova hygiena' and has_seg(tail, 'toaletní papíry', 'vlhčené ubrousky'):
            return 'Papír a hygiena', 'Papírová a vlhčená hygiena podle cesty e-shopu'
        if branch == 'damska hygiena' and has_seg(tail, 'intimní hygiena'):
            return 'Papír a hygiena', 'Intimní hygiena podle cesty e-shopu'
        if branch == 'deodoranty a antiperspiranty' or branch == 'pece o vlasy':
            return 'Kosmetika', 'Kosmetický sortiment podle cesty e-shopu'
        if branch == 'papirova a vatova hygiena' and has_seg(tail, 'ubrousky a utěrky', 'vlhčené ubrousky na úklid'):
            # Cleaning wipes are not automatically paper tissues.
            if has_seg(tail, 'vlhčené ubrousky na úklid'):
                return 'Úklid', 'Čisticí ubrousky podle cesty e-shopu'

    if root == 'kosmetika':
        if branch == 'ustni hygiena' and has_seg(tail, 'zubní pasty'):
            return 'Dentální hygiena', 'Zubní pasty podle cesty e-shopu'
        if branch in {'deodoranty a parfemy', 'vlasova pece'}:
            return 'Kosmetika', 'Kosmetický sortiment podle cesty e-shopu'
        if branch == 'pletova pece a dekorativni kosmetika' and has_seg(tail, 'odličovací tampony a vata'):
            return 'Papír a hygiena', 'Vatové tampony podle cesty e-shopu'

    if root == 'mlecne a chlazene':
        if has_seg(tail, 'majonézy a dresingy', 'majonézy, tatarské omáčky a dresingy') and has_seg(tail, 'majonézy'):
            return 'Majonézy', 'Majonézy podle konkrétní cesty e-shopu'
        if branch == 'syry' and has_seg(tail, 'mozzarella a salátové', 'mozzarella a burrata',
                                        'mozzarella, ricotta a salátové sýry', 'mozzarella, burrata a ricotta'):
            return 'Sýry / mozzarella a salátové', 'Mozzarella/salátové sýry podle cesty e-shopu'

    if root == 'trvanlive' and branch == 'sladke' and has_seg(tail, 'oplatky a sušenky', 'oplatky'):
        return 'Sladké', 'Oplatky a sušenky podle cesty e-shopu'
    if root == 'plant based' and branch == 'alternativy mlecneho a chlazeneho' and has_seg(tail, 'rostlinné tuky a margaríny'):
        return 'Másla a tuky', 'Rostlinné tuky a margaríny podle cesty e-shopu'
    return None


def merchant_category(item):
    """Return category + reason based only on merchant breadcrumb path.

    Conservative: unknown branches and broad ambiguous leaves must be reviewed.
    Read *parent and child* together, never a matching word from another aisle.
    """
    path = item.get('store_category_path')
    src = item.get('category_source')
    if not isinstance(path, list) or len(path) < 2:
        return None, 'Chybí dostatečná cesta kategorie prodejce (min. 2 úrovně)'
    if src not in TRUSTED_SOURCES:
        return None, 'Neověřený zdroj kategorie prodejce'
    if not trusted_path(item):
        return None, 'Neplatný segment cesty kategorie'
    parts = [norm(p) for p in path]
    root, branch = parts[0], parts[1]
    tail = parts[1:]
    extra = mapped_known_merchant_path(parts)
    if extra is not None:
        return extra


    # Fresh produce: the actual food aisle must be established by ancestry.
    if root in {'ovoce a zelenina', 'bio ovoce a zelenina'}:
        if branch == 'bio ovoce a zelenina':
            if len(parts) >= 3 and parts[2] in {'bio ovoce', 'ovoce'}:
                return 'Ovoce', 'BIO ovoce podle vnořené cesty prodejce'
            if len(parts) >= 3 and parts[2] in {'bio zelenina', 'zelenina'}:
                return 'Zelenina', 'BIO zelenina podle vnořené cesty prodejce'
            return None, 'Nejednoznačné BIO ovoce a zelenina'
        if branch in {'ovoce', 'bio ovoce', 'cerstve ovoce'}:
            return 'Ovoce', 'Ovoce podle cesty prodejce'
        if branch in {'zelenina', 'bio zelenina', 'cerstva zelenina'}:
            return 'Zelenina', 'Zelenina podle cesty prodejce'
        return None, 'Jiná nebo nejednoznačná podkategorie ovoce a zeleniny'

    if root == 'maso a ryby':
        if segment_starts(tail, 'uzeniny', 'uzené', 'marinované', 'grilované',
                          'hotová jídla', 'maso na grilování', 'mražené',
                          'hotovky', 'krmiva', 'konzervy', 'hotové pokrmy',
                          'grilování', 'mleté', 'mleté a mělněné'):
            return None, 'Maso ve zpracované či nejednoznačné kategorii'
        if segment_starts([branch], 'drůbež', 'drůbeží maso', 'vepřové',
                          'vepřové maso', 'hovězí', 'hovězí maso',
                          'hovězí a telecí', 'telecí maso', 'čerstvé maso'):
            return 'Maso', 'Syrové maso podle cesty prodejce; typ upřesňují pravidla'
        return None, 'Neprokázaná podkategorie syrového masa'

    if root in {'uzeniny a lahudky', 'uzeniny', 'lahudky a uzeniny'}:
        if segment_starts(tail, 'šunky', 'šunka'):
            return 'Uzeniny / šunky', 'Šunky podle cesty prodejce'
        if segment_starts(tail, 'salámy', 'salám'):
            return 'Uzeniny / salámy', 'Salámy podle cesty prodejce'
        if segment_starts(tail, 'párky', 'klobásy', 'párky a klobásy'):
            return 'Uzeniny / párky a klobásy', 'Párky/klobásy podle cesty prodejce'
        return None, 'Podkategorie uzenin neodpovídá některé sledované skupině'

    if segment_starts([root], 'mléčné výrobky', 'mléčné', 'mléko vejce a máslo',
                      'mléčné výrobky a vejce', 'sýry a mléčné výrobky'):
        # Košík (public breadcrumb, 2026-10-21):
        # "Mléčné a chlazené > Máslo, margaríny, tuky > Rostlinné tuky a margaríny".
        # This is merchant ancestry, NOT a Flora/Omega brand-name guess.
        if has_seg(tail, 'másla', 'máslo', 'margaríny', 'tuky', 'másla a margaríny',
                   'máslo, margaríny, tuky', 'rostlinné tuky',
                   'rostlinné tuky a margaríny'):
            return 'Másla a tuky', 'Jedlé máslo/tuky podle cesty prodejce'
        # Short merchant leaves such as "Tavené" are valid only under the
        # established "Sýry" parent; an isolated "Tavené" is not evidence.
        cheese_branch = has_seg(tail, 'sýry', 'sýry a sýrové výrobky', 'sýry a sýrové speciality')
        if has_seg(tail, 'tavené sýry', 'sýry tavené') or (cheese_branch and has_seg(tail, 'tavené')):
            return 'Sýry / tavené', 'Tavené sýry podle cesty prodejce'
        if has_seg(tail, 'plísňové sýry', 'sýry s plísní', 'sýry plísňové') or (cheese_branch and has_seg(tail, 'plísňové')):
            return 'Sýry / plísňové', 'Plísňové sýry podle cesty prodejce'
        if has_seg(tail, 'plátkové sýry', 'sýry plátkové', 'plátky') or (cheese_branch and has_seg(tail, 'plátkové')):
            return 'Sýry / plátkové', 'Plátkové sýry podle cesty prodejce'
        if has_seg(tail, 'mozzarella', 'mozzarelly', 'salátové sýry',
                   'mozzarella a salátové sýry') or (cheese_branch and has_seg(tail, 'salátové')):
            return 'Sýry / mozzarella a salátové', 'Mozzarella/salátové sýry podle cesty prodejce'
        return None, 'Mléčná kategorie bez jednoznačného sledovaného typu'

    if root in {'napoje', 'vody a napoje'}:
        if segment_starts([branch], 'vody', 'vody a minerálky', 'minerální vody'):
            return 'Nápoje / vody', 'Vody podle cesty prodejce'
        if segment_starts([branch], 'limonády', 'sycené nápoje', 'colové nápoje'):
            return 'Nápoje / limonády', 'Limonády podle cesty prodejce'
        return None, 'Nesledovaná podkategorie nápojů'

    if root in {'drogerie a kosmetika', 'drogerie', 'domacnost a drogerie'}:
        if segment_starts(tail, 'praní', 'prací prostředky', 'aviváže', 'prací gely',
                          'prací prášky', 'kapsle na praní'):
            return 'Praní', 'Praní podle cesty prodejce'
        if segment_starts(tail, 'mytí nádobí', 'úklid', 'čisticí prostředky',
                          'čištění domácnosti', 'prostředky na úklid',
                          'čistící přípravky', 'čisticí přípravky',
                          'čisticí prostředky na toaletu'):
            return 'Úklid', 'Úklid podle cesty prodejce'
        if segment_starts(tail, 'zubní hygiena', 'ústní hygiena', 'péče o zuby',
                          'dentální hygiena'):
            return 'Dentální hygiena', 'Dentální hygiena podle cesty prodejce'
        if segment_starts(tail, 'holení', 'holicí potřeby'):
            return 'Holení', 'Holení podle cesty prodejce'
        if segment_starts(tail, 'kosmetika', 'péče o tělo', 'péče o pleť'):
            return 'Kosmetika', 'Kosmetika podle cesty prodejce'
        if segment_starts(tail, 'papírové utěrky', 'kuchyňské utěrky'):
            return 'Papírové utěrky', 'Papírové utěrky podle cesty prodejce'
        if segment_starts(tail, 'papírové kapesníky', 'kapesníky', 'hygienické potřeby',
                          'toaletní papír', 'papírová hygiena'):
            return 'Papír a hygiena', 'Papírová hygiena podle cesty prodejce; typ je neověřený'
        return None, 'Nesledovaná podkategorie drogerie'

    if root in {'trvanlive potraviny', 'trvanlive', 'potraviny a pochutiny'}:
        if segment_starts(tail, 'těstoviny', 'rýže', 'těstoviny a rýže'):
            return 'Těstoviny a rýže', 'Těstoviny/rýže podle cesty prodejce'
        if segment_starts(tail, 'majonézy', 'majonézy a tatarky', 'tatarské omáčky'):
            return 'Majonézy', 'Majonézy/tatarky podle cesty prodejce'
        if segment_starts(tail, 'sladkosti', 'cukrovinky', 'čokolády'):
            return 'Sladké', 'Sladkosti podle cesty prodejce'
        return None, 'Nesledovaná podkategorie trvanlivých potravin'

    if root in {'sladkosti', 'cukrovinky a sladkosti', 'cukrovinky'}:
        return 'Sladké', 'Sladkosti podle cesty prodejce'
    return None, 'Cesta prodejce nemá schválené mapování'


def broader_merchant_category(merchant, target):
    """Is a retailer's broad shelf consistent but inconclusive for a narrow rule?

    Do not mark paper handkerchiefs as a wrong category merely because a
    merchant uses one shared 'Papír a hygiena' breadcrumb for all paper types.
    """
    compatible = {
        'Papír a hygiena': {'Kapesníky / balíčky', 'Kapesníky / krabice', 'Papírové utěrky'},
        'Kosmetika': {'Holení', 'Dentální hygiena'},
    }
    return target in compatible.get(merchant, set())


def diagnose_price(item):
    """Observations, NOT definitive explanations of website availability."""
    value, status = item.get('price_czk'), item.get('price_status')
    if status == 'ok' and type(value) in (float, int) and 0 < value < 50000:
        return 'ok', 'Dříve zaznamenaná cena; aktuálnost podle checked_at'
    code = item.get('http_status')
    recent = item.get('monitor_v26_status')
    if recent in {'blocked', 'throttled', 'rate_limited'}:
        return 'blocked_http', 'Poslední v26 kontrola byla omezená zdrojem'
    # A v26 attempt is NEWER than historical http_status/price_status.
    # E.g. old HTTP 429 followed by a reachable page with unreadable price.
    if recent in {'price_unverified', 'parse_error'}:
        return 'price_read_unverified', 'Poslední v26 pokus: cena nebyla spolehlivě vyčtena'
    if recent == 'title_mismatch':
        return 'identity_mismatch', 'Poslední v26 pokus: neshoda identity detailu'
    if code in (403, 429, 503):
        return 'blocked_http', f'Uložený HTTP stav {code}; omezení požadavků při posledním známém HTTP pokusu'
    if code in (404, 410):
        return 'product_unavailable_unconfirmed', f'HTTP {code}; dostupnost produktu vyžaduje kontrolu'
    if status == 'title_mismatch':
        return 'identity_mismatch', 'Původní neshoda identity při ověřování detailu produktu'
    if status == 'price_unverified':
        return 'price_read_unverified', 'Cena z detailu není spolehlivě vyčtena (neověřeno)'
    if status == 'ok':
        return 'invalid_price_evidence', 'Stav ok, ale chybí platná kladná číselná cena'
    return 'unknown', f'Nedostatek údajů k určení příčiny ({status or "bez stavu"})'


def identity(item):
    return (item.get('store'), item.get('url'))


def price_snapshot(item):
    return {k: deepcopy(item[k]) for k in PRICE_FIELDS if k in item}


def compile_catalog(source):
    if not isinstance(source, dict) or not isinstance(source.get('items'), list):
        raise ValueError('Neplatná data katalogu')
    rows = source['items']
    keys = [identity(p) for p in rows]
    if any(not x[0] or not x[1] for x in keys) or len(set(keys)) != len(keys):
        raise ValueError('Duplicitní nebo neplatný klíč obchod+URL')
    categories = {r['id']: r['category'] for r in source.get('rules', [])}
    result = deepcopy(source)
    statuses, reasons, price_reasons, shops, rule_decisions = Counter(), Counter(), Counter(), Counter(), Counter()
    review = []
    shop_price = {}
    for old, row in zip(rows, result['items']):
        merchant, detail = merchant_category(row)
        rid_list = list(row.get('rule_ids', []))
        expected = sorted({categories[r] for r in rid_list if r in categories})
        checks = {}
        for rid in rid_list:
            target = categories.get(rid)
            decision = ('review' if merchant is None or target is None or broader_merchant_category(merchant, target)
                        else ('verified' if merchant == target else 'mismatch'))
            note = ('Kategorie neověřena u prodejce' if merchant is None else
                    'Širší kategorie prodejce nezaručuje konkrétní typ' if broader_merchant_category(merchant, target)
                    else 'Srovnání se společnou kategorií')
            if decision == 'verified':
                specific_status, specific_reason = verify_specific_rule(rid, row, merchant)
                if specific_status is not None:
                    decision, note = specific_status, specific_reason
            checks[rid] = {'expected': target, 'status': decision, 'reason': note}
            rule_decisions[decision] += 1
        if merchant is None or not rid_list:
            state = 'review'
        elif any(x['status'] != 'verified' for x in checks.values()):
            state = 'mismatch' if any(x['status'] == 'mismatch' for x in checks.values()) else 'review'
            if state == 'mismatch':
                detail = f'{detail}; nesoulad s pravidly: {", ".join(expected) or "žádná"}'
            else:
                detail = f'{detail}; konkrétní typ dle pravidel zatím nelze potvrdit: {", ".join(expected) or "žádná"}'
        else:
            state = 'verified'
        price_code, price_note = diagnose_price(row)
        shop = row.get('store', '?')
        if shop not in shop_price:
            shop_price[shop] = {'total': 0, 'priced': 0, 'missing': 0, 'diagnostics': Counter()}
        shop_price[shop]['total'] += 1
        shop_price[shop]['priced' if price_code == 'ok' else 'missing'] += 1
        shop_price[shop]['diagnostics'][price_code] += 1
        row['category_v27'] = {
            'status': state,
            'evidence_state': ('mapped' if merchant is not None else ('unmapped_merchant_path' if trusted_path(row) else 'merchant_path_missing')),
            'probe_status': row.get('v27_category_probe_status'), 'category': merchant, 'display_category': merchant if merchant else 'Ke kontrole',
            'source': row.get('category_source') if merchant else None,
            'expected_from_rules': expected, 'rule_checks': checks, 'reason': detail,
        }
        row['price_diagnostic_v27'] = {'status': price_code, 'reason': price_note}
        if state != 'verified':
            review.append({'store': row.get('store'), 'url': row.get('url'),
                           'name': row.get('name'), 'rule_ids': row.get('rule_ids', []),
                           'status': state, 'merchant_category': merchant,
                           'merchant_path': row.get('store_category_path') or [],
                           'expected_categories': expected, 'rule_checks': checks, 'reason': detail})
        statuses[state] += 1
        reasons[detail] += 1
        price_reasons[price_code] += 1
        shops[row.get('store', '?')] += 1
        if price_snapshot(old) != price_snapshot(row):
            raise AssertionError('Nepovolená změna historie ceny')
        if {k: v for k, v in row.items() if k not in ('category_v27', 'price_diagnostic_v27')} != old:
            raise AssertionError('Nepovolená změna existujících dat produktu')
    if len(result['items']) != len(rows) or [identity(r) for r in result['items']] != keys:
        raise AssertionError('Ztracený nebo přeuspořádaný produkt')
    priced_before = sum(diagnose_price(p)[0] == 'ok' for p in rows)
    priced_after = price_reasons['ok']
    if priced_before != priced_after:
        raise AssertionError('Ztráta cen mezi vstupem a výstupem')
    # Search coverage must be reported independently of taxonomy success.
    configured = {r['id']: r for r in source.get('rules', [])}
    observed = Counter(rid for product in rows for rid in product.get('rule_ids', []))
    missing_rules = [
        {'id': rid, 'label': rule.get('label') or rule.get('name') or '',
         'category': rule.get('category') or ''}
        for rid, rule in configured.items() if rid not in observed
    ]
    metadata = {
        'rules_configured': len(configured),
        'rules_with_products': sum(1 for rid in configured if rid in observed),
        'rules_without_products': missing_rules,
        'unknown_rule_ids': sorted(set(observed) - set(configured)),
        'schema': 'rk-v27-taxonomy-audit',
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source_generated_at': source.get('generated_at'),
        'products_before': len(rows), 'products_after': len(result['items']),
        'priced_before': priced_before, 'priced_after': priced_after,
        'missing_prices': len(rows)-priced_after,
        'category_statuses': dict(statuses), 'rule_match_statuses': dict(rule_decisions),
        'merchant_category_mapped': sum(merchant_category(p)[0] is not None for p in rows),
        'merchant_category_unmapped': sum(merchant_category(p)[0] is None for p in rows),
        'products_with_merchant_category_but_rule_review': sum(
            p.get('category_v27', {}).get('category') is not None and
            p.get('category_v27', {}).get('status') == 'review' for p in result['items']),
        'products_with_merchant_category_but_rule_mismatch': sum(
            p.get('category_v27', {}).get('category') is not None and
            p.get('category_v27', {}).get('status') == 'mismatch' for p in result['items']),
        'price_diagnostics': dict(price_reasons),
        'price_by_shop': {shop: {**data, 'diagnostics': dict(data['diagnostics'])}
                          for shop, data in shop_price.items()},
        'shops': dict(shops), 'review_count': len(review),
        'retailer_path_present': sum(bool(p.get('store_category_path')) for p in rows),
        'retailer_path_missing': sum(not p.get('store_category_path') for p in rows),
        'trusted_retailer_path': sum(trusted_path(p) for p in rows),
        'trusted_but_unmapped': sum(trusted_path(p) and merchant_category(p)[0] is None for p in rows),
        'untrusted_or_missing_path': sum(not trusted_path(p) for p in rows),
        'source_price_evidence_unchanged': True,
        'source_items_unchanged': True,
        'category_mapping_method': 'trusted merchant path only; specific rule checks for meat and produce; no titles',
    }
    result['schema'] = 'rk-v27-catalogue-preview-1'
    result['v27_audit'] = metadata
    return result, {'schema': 'rk-v27-category-review', 'count': len(review), 'items': review}, metadata


def summarize_merchant_paths(source):
    """Collapse individual category reviews into actual merchant paths.

    This is evidence clustering, NOT automatic approval of a search-rule label.
    Group by store+full category path, never by product titles or fuzzy words.
    """
    rules = {r['id']: r['category'] for r in source.get('rules', [])}
    grouped = {}
    unresolved = Counter()
    for product in source.get('items', []):
        store = product.get('store', '?')
        raw_path = product.get('store_category_path') or []
        if not trusted_path(product):
            unresolved[store] += 1
            continue
        key = (store, tuple(norm(x) for x in raw_path))
        if key not in grouped:
            category, reason = merchant_category(product)
            grouped[key] = {
                'shop': store, 'merchant_path': list(raw_path),
                'mapped_category': category, 'mapping_reason': reason,
                'product_count': 0, 'old_rule_categories': Counter(),
                'sample_product_urls': [], 'needs_review': category is None,
            }
        rec = grouped[key]
        rec['product_count'] += 1
        for rid in product.get('rule_ids', []):
            old_category = rules.get(rid, 'NEZNÁMÉ PRAVIDLO')
            rec['old_rule_categories'][old_category] += 1
            if old_category != rec['mapped_category']:
                rec['needs_review'] = True
        if len(rec['sample_product_urls']) < 3:
            rec['sample_product_urls'].append(product.get('url'))
    paths = sorted(grouped.values(), key=lambda x: (-x['product_count'], x['shop'], x['merchant_path']))
    for rec in paths:
        rec['old_rule_categories'] = dict(rec['old_rule_categories'])
    return {
        'schema': 'rk-v27-merchant-path-review',
        'number_of_distinct_trusted_paths': len(paths),
        'mapped_product_total': sum(x['product_count'] for x in paths if x['mapped_category']),
        'unmapped_or_mismatched_path_count': sum(x['needs_review'] for x in paths),
        'without_trusted_path_by_shop': dict(unresolved),
        'note': 'Old rule categories are references for audit only; never proof of merchant classification.',
        'paths': paths,
    }


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def main():
    p = argparse.ArgumentParser(description='Bezpečná příprava katalogu v27 z existujících produktů')
    p.add_argument('--input', default='docs/data/catalog_latest.json')
    p.add_argument('--output', default='docs/data/catalog_v27.json')
    p.add_argument('--review', default='docs/data/catalog_v27_review.json')
    p.add_argument('--audit', default='docs/data/catalog_v27_audit.json')
    p.add_argument('--path-review', default='docs/data/catalog_v27_path_review.json')
    args = p.parse_args()
    names = {str(Path(x).resolve()) for x in (args.input, args.output, args.review, args.audit, args.path_review)}
    if len(names) != 5:
        p.error('Vstup a všechny výstupy musejí mít různé cesty (v26 se nesmí přepsat)')
    data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    result, review, audit = compile_catalog(data)
    path_review = summarize_merchant_paths(data)
    # Generate everything in memory before writing: no partial classifications.
    write_json(args.output, result)
    write_json(args.review, review)
    write_json(args.audit, audit)
    write_json(args.path_review, path_review)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
