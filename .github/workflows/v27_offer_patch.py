#!/usr/bin/env python3
"""Safe, additive v27 offer UI patch. Does not touch catalog data.

Runs on GitHub Actions checkout of the published branch. Fails closed when the
current dashboard template no longer has the expected anchors.
"""
import argparse
from collections import Counter
import json
from pathlib import Path


def change_once(src: str, needle: str, value: str) -> str:
    count = src.count(needle)
    if count != 1:
        raise RuntimeError(f"Template conflict: expected exactly one match, found {count}: {needle[:100]}")
    return src.replace(needle, value, 1)


def patch_html(html: str) -> str:
    if 'id="qMulti"' in html:
        # Idempotence for retries; ensure all expected parts were previously added.
        for part in ('data-quick="multi"', 'const savedMulti=', 'id="offersV27Status"',
                     "view==='multi'", "$('qMulti').textContent"):
            if part not in html:
                raise RuntimeError(f"Partial v27 offer patch: {part} missing")
        return html
    html = change_once(html,
        '<button type="button" data-quick="deals" class="quick-active">🔥 Ověřené akce <span id="qDeals">—</span></button>',
        '<button type="button" data-quick="deals" class="quick-active">🔥 Ověřené akce <span id="qDeals">—</span></button>\n'
        '  <button type="button" data-quick="multi" title="Dříve zjištěné množstevní nabídky. Aktuální platnost nemusí být potvrzena.">🛒 Množstevní (uložené) <span id="qMulti">—</span></button>')
    html = change_once(html,
        '<span class="quicknote">Oblíbené se ukládají jen v tomto prohlížeči. Nabídky mohou být starší; zkontroluj datum ceny.</span>',
        '<span class="quicknote">Oblíbené se ukládají jen v tomto prohlížeči. Nabídky mohou být starší; zkontroluj datum ceny.</span>\n'
        '  <span id="offersV27Status" class="quicknote" role="status" aria-live="polite">Načítám podmíněné nabídky…</span>')
    html = change_once(html,
        'const actualDrop=p=>freshPrice(p)',
        'const savedMulti=p=>isPrice(p)&&Array.isArray(p.multibuy)&&p.multibuy.some(x=>Number(x.min_qty)>=2&&'
        'typeof x.price_czk===\'number\'&&Number.isFinite(x.price_czk)&&x.price_czk>0&&x.price_czk<p.price_czk);\n'
        'const multiUnconfirmed=p=>!freshPrice(p)||(String(p.last_monitor_attempt_at||\'\')>String(p.checked_at||\'\')'
        '&&p.monitor_v26_status!==\'ok\');\n'
        'const actualDrop=p=>freshPrice(p)')
    html = change_once(html,
        "if(view==='deals'&&!datedPromo(p))return false;if(view==='favs'",
        "if(view==='deals'&&!datedPromo(p))return false;if(view==='multi'&&!savedMulti(p))return false;if(view==='favs'")
    html = change_once(html,
        "view==='deals'?'Doložené aktuální akce':view==='favs'",
        "view==='deals'?'Doložené aktuální akce':view==='multi'?'Uložené množstevní nabídky – platnost je nutno ověřit':view==='favs'")
    html = change_once(html,
        'result.push(`od ${Number(x.min_qty)} ks za ${money(x.price_czk)}`)',
        'result.push(`od ${Number(x.min_qty)} ks za ${money(x.price_czk)}`+'
        '(multiUnconfirmed(p)?\' (poslední kontrola nepotvrdila)\':\'\'))')
    html = change_once(html,
        "$('qDeals').textContent=nf(db.items.filter(datedPromo).length);$('qDrops')",
        "$('qDeals').textContent=nf(db.items.filter(datedPromo).length);$('qMulti').textContent=nf(db.items.filter(savedMulti).length);$('qDrops')")
    html = change_once(html,
        "$('qFavs').textContent=favs.size;document.getElementById('monitorStamp')",
        "$('qFavs').textContent=favs.size;"+
        "{const regular=db.items.filter(datedPromo).length, conditional=db.items.filter(savedMulti);"+
        "const unconfirmed=conditional.filter(multiUnconfirmed).length;"+
        "const onlyMulti=conditional.filter(p=>!datedPromo(p)).length;"+
        "$('offersV27Status').textContent='Akce: '+nf(regular)+' běžných slev + '+nf(onlyMulti)+' dalších množstevních nabídek'+"+
        "' (z nich '+nf(unconfirmed)+' bez aktuálního potvrzení). Celkem potenciálně '+nf(regular+onlyMulti)+"+
        "'; neznamená to stejně tolik platných dnešních slev.';}"+
        "document.getElementById('monitorStamp')")
    for part in ('id="mobileCards"', 'id="categoryStatus"', 'id="taxKpiVerified"',
                 'await loadCategoryOverlay()', 'const datedPromo=p=>'):
        if part not in html:
            raise RuntimeError(f'Dashboard feature missing after patch: {part}')
    return html


def analyze(prices, taxonomy):
    items = prices['items']
    overlay = taxonomy['items']
    if len(items) < 1090 or len(overlay) != len(items):
        raise RuntimeError('Number of products changed')
    idfun = lambda p: (p['store'], p['url'])
    keys = [idfun(p) for p in items]
    if len(keys) != len(set(keys)) or set(keys) != set(map(idfun, overlay)):
        raise RuntimeError('Product identities differ or duplicate')
    category_counts = Counter(x['category_v27']['status'] for x in overlay)
    mapped = sum(bool(x['category_v27'].get('category')) for x in overlay)
    if sum(category_counts.values()) != len(items):
        raise RuntimeError('Category status totals differ')
    rule_review = [p for p in overlay if p['category_v27']['status'] == 'review' and p['category_v27'].get('category')]
    mapping = {idfun(x): x for x in items}
    rule_lookup = {p['id']: p.get('label', p.get('category', '')) for p in prices.get('rules', [])}
    rule_counts = Counter()
    category_rule_counts = Counter()
    examples = []
    for item in rule_review:
        p = mapping[idfun(item)]
        category_rule_counts[item['category_v27']['category']] += 1
        for rid in (p.get('rule_ids') or []): rule_counts[rid] += 1
        if len(examples) < 50:
            examples.append({'store': p['store'], 'name': p.get('name'), 'url': p['url'],
                             'merchant_path': item.get('store_category_path', []),
                             'rule_ids': p.get('rule_ids', []), 'review_reason': item['category_v27'].get('reason')})
    valid_price = lambda p: p.get('price_status') == 'ok' and type(p.get('price_czk')) in (int, float) and p['price_czk'] > 0
    normal = lambda p: valid_price(p) and type(p.get('discount_pct')) in (float, int) and p['discount_pct'] > 0 and type(p.get('original_price_czk')) in (float, int) and p['original_price_czk'] > p['price_czk']
    multi = lambda p: valid_price(p) and isinstance(p.get('multibuy'), list) and any(type(m.get('price_czk')) in (float, int) and m['price_czk'] > 0 and m['price_czk'] < p['price_czk'] and type(m.get('min_qty')) in (float, int) and m['min_qty'] >= 2 for m in p['multibuy'] if isinstance(m, dict))
    specials = [p for p in items if multi(p)]
    regular = [p for p in items if normal(p)]
    conditional_no_discount = [p for p in specials if not normal(p)]
    stale_conditional = [p for p in specials if p.get('monitor_v26_status') != 'ok' and str(p.get('last_monitor_attempt_at', '')) > str(p.get('checked_at', ''))]
    return {'products':len(items), 'priced':sum(map(valid_price, items)),
            'normal_discount_evidence': len(regular),
            'stored_quantity_offers': len(specials),
            'quantity_not_in_normal': len(conditional_no_discount),
            'quantity_newer_check_unconfirmed': len(stale_conditional),
            'potential_combined_distinct': len(regular)+len(conditional_no_discount),
            'caution':'Stored quantity promotions with subsequent price_unverified must NOT be presented as currently verified',
            'category':{'mapped':mapped, 'fully_verified':category_counts['verified'],
                        'rule_review_with_mapped_category':len(rule_review),
                        'mismatch':category_counts['mismatch'],
                        'unmapped':len(items)-mapped},
            'rule_review_by_category':category_rule_counts.most_common(),
            'rule_review_by_rule':[{'id':rid, 'label':rule_lookup.get(rid), 'count':cnt} for rid,cnt in rule_counts.most_common()],
            'rule_review_examples':examples}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog', required=True)
    parser.add_argument('--taxonomy', required=True)
    parser.add_argument('--html', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--only-report', action='store_true')
    opt=parser.parse_args()
    before=Path(opt.html).read_bytes()
    prices=json.loads(Path(opt.catalog).read_text('utf8'))
    taxonomy=json.loads(Path(opt.taxonomy).read_text('utf8'))
    report=analyze(prices,taxonomy)
    dest=Path(opt.report)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    if not opt.only_report:
        new=patch_html(before.decode('utf8'))
        Path(opt.html).write_text(new,encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rule_review_by_category','rule_review_by_rule','rule_review_examples')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
