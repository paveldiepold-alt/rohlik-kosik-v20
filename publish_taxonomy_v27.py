#!/usr/bin/env python3
"""Publish retailer-backed category overlay without changing a single public price.

Inputs: current LIVE catalog, v27 compiled staged catalog, current public HTML.
Outputs: tiny category-only JSON, patched HTML, review/verification report.
No network access or GitHub token is needed by this program.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

SCHEMA = 'rk-v27-retailer-category-overlay-v1'
SOURCES = {'jsonld_breadcrumb', 'dom_breadcrumb', 'jsonld_product_category'}
STATES = {'verified', 'review', 'mismatch'}


def key(p):
    return (p.get('store'), p.get('url'))


def load_json(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise ValueError(f'Invalid catalogue: {path}')
    return data


def validate_unique(items, name):
    ids = [key(p) for p in items]
    if len(ids) != len(set(ids)) or any(not k[0] or not k[1] for k in ids):
        raise ValueError(f'Duplicate/missing store-url identity in {name}')
    return ids


def build_overlay(live, compiled, now=None):
    before = live['items']
    results = compiled['items']
    if len(before) < 1090 or len(before) != len(results):
        raise ValueError('Unexpected live/staging product count')
    if validate_unique(before, 'LIVE') != validate_unique(results, 'v27 compiled'):
        raise ValueError('LIVE and staged product order/identity differ; stop instead of losing items')

    counts = Counter()
    products = []
    for product, saved in zip(before, results):
        evidence = saved.get('category_v27')
        if not isinstance(evidence, dict) or evidence.get('status') not in STATES:
            raise ValueError(f'Missing or invalid taxonomy decision: {key(product)}')
        category = evidence.get('category')
        path = saved.get('store_category_path')
        source = saved.get('category_source')
        trusted = (isinstance(path, list) and 2 <= len(path) <= 12
                   and source in SOURCES
                   and all(isinstance(part, str) and 1 <= len(part.strip()) <= 160 for part in path))
        mapped = bool(category)
        if mapped and (not trusted or not isinstance(category, str) or len(category) > 100):
            raise ValueError(f'Mapped category without verified merchant path: {key(product)}')
        if evidence['status'] == 'verified' and not mapped:
            raise ValueError(f'Verified status without category: {key(product)}')
        if evidence.get('display_category') != (category if mapped else 'Ke kontrole'):
            raise ValueError(f'Conflicting displayed category: {key(product)}')

        # Preserve independently meaningful verification and rule mismatch states.
        record = {
            'store': product['store'], 'url': product['url'],
            'category_v27': {
                'category': category if mapped else None,
                'display_category': category if mapped else 'Ke kontrole',
                'status': evidence['status'],
                'evidence_state': evidence.get('evidence_state'),
                'reason': evidence.get('reason') or '',
                'expected_from_rules': evidence.get('expected_from_rules') or [],
            },
            'store_category_path': path if trusted else [],
            'category_source': source if trusted else None,
        }
        products.append(record)
        counts[evidence['status']] += 1
        counts['mapped' if mapped else 'unmapped'] += 1
        if mapped and evidence['status'] != 'verified':
            counts['mapped_with_rule_review'] += 1
    if counts['mapped'] + counts['unmapped'] != len(before):
        raise AssertionError('Invalid category coverage')
    return {
        'schema': SCHEMA,
        'generated_at': (now or datetime.now(timezone.utc)).isoformat(timespec='seconds'),
        'source_catalog_generated_at': live.get('generated_at'),
        'source_category_run_at': compiled.get('v27_probe_control', {}).get('at')
            if isinstance(compiled.get('v27_probe_control'), dict) else None,
        'total': len(products),
        'counts': dict(counts),
        'items': products,
    }


def _replace_once(content, old, new, desc):
    if content.count(old) != 1:
        raise ValueError(f'Unsupported current HTML template ({desc}): {content.count(old)} matches')
    return content.replace(old, new, 1)


def patch_html(source):
    """Small additive patch to the *current live page*, retaining its mobile CSS.

    Fail closed if the published frontend changes its structure; never deploy a
    half-patched page or replace it with an outdated HTML template.
    """
    if 'id="taxonomyV27Status"' in source:
        # Re-running deploy updates only JSON; frontend was already patched.
        for required in ("const categoryV27Label=p=>", 'await loadCategoryOverlay()',
                         "./data/taxonomy_v27_public.json?ts=", 'id="mobileCards"'):
            if required not in source:
                raise ValueError('Partial previous integration detected')
        return source
    if 'id="mobileCards"' not in source:
        raise ValueError('Mobile layout missing; refusing to overwrite live dashboard')

    out = source
    out = _replace_once(out, '<div class="progress" id="progress"></div>',
        '<div class="progress" id="progress"></div>\n'
        ' <div id="taxonomyV27Status" role="status" aria-live="polite" '
        'style="padding:9px 11px;margin:8px 0 11px;background:#f0f5fa;'
        'border:1px solid #d8e4ef;border-radius:8px;font-size:12px;line-height:1.5;'
        'color:#1c4167">Načítám ověřené kategorie obchodů…</div>', 'status block')

    old_cats = 'const cats=p=>[...new Set((p.rule_ids||[]).map(id=>rules.get(id)?.category).filter(Boolean))];'
    new_cats = '''const categoryV27Label=p=>p.category_v27?.display_category||'Ke kontrole';
const categoryV27Badge=p=>{
 const s=p.category_v27?.status;
 return s==='verified'?'✓ Kategorie a pravidlo ověřeny':s==='mismatch'?'⚠ Nesoulad se sledovacím pravidlem':
 (p.category_v27?.category?'◇ Kategorie e-shopu; pravidlo ke kontrole':'◇ Kategorie k ověření');
};
const cats=p=>[categoryV27Label(p)];'''
    out = _replace_once(out, old_cats, new_cats, 'retailer category labels')

    # A separate explicit review filter: a confirmed retailer aisle does not
    # automatically confirm compliance with a specific monitoring rule.
    cat_field = '<div class="field"><label for="category">Kategorie</label><select id="category"><option value="">Všechny kategorie</option></select></div>'
    status_field = ('<div class="field"><label for="categoryStatus">Stav kategorie</label>'
                    '<select id="categoryStatus"><option value="">Všechny stavy</option>'
                    '<option value="verified">Plně ověřené</option>'
                    '<option value="review">Ke kontrole (včetně nesouladu)</option>'
                    '<option value="mismatch">Nesoulad se sledováním</option>'
                    '<option value="unmapped">Bez potvrzené kategorie</option></select></div>')
    out = _replace_once(out, cat_field, cat_field + '\n   ' + status_field, 'review filter UI')
    out = _replace_once(out, "category:$('category').value,brand:",
                        "category:$('category').value,categoryStatus:$('categoryStatus').value,brand:", 'review filter input')
    out = _replace_once(out, 'if(f.category&&!cats(p).includes(f.category))return false;',
        "if(f.category&&!cats(p).includes(f.category))return false;"
        "if(f.categoryStatus==='verified'&&p.category_v27?.status!=='verified')return false;"
        "if(f.categoryStatus==='review'&&p.category_v27?.status==='verified')return false;"
        "if(f.categoryStatus==='mismatch'&&p.category_v27?.status!=='mismatch')return false;"
        "if(f.categoryStatus==='unmapped'&&p.category_v27?.category)return false;", 'review filter predicate')
    events="'shop','category','brand'"
    if out.count(events) != 2:
        raise ValueError('Unsupported current frontend change/listener structure for category status')
    out=out.replace(events, "'shop','category','categoryStatus','brand'")

    # Category dropdown must use the actual retailer-mapped categories in the
    # overlay, not historical query-rule categories.
    start = "const ct=[...new Set((db.rules||[]).map(r=>r.category).filter(Boolean))],ordered=db.category_order||[];"
    out = _replace_once(out, start,
        "const ct=[...new Set((db.items||[]).map(p=>categoryV27Label(p)))],ordered=db.category_order||[];",
        'category dropdown source')

    old_trust = "${shopPath?'✓ Kategorie prodejce':'◇ Kategorie dle pravidla'}"
    out = _replace_once(out, old_trust, '${esc(categoryV27Badge(p))}', 'product badge')
    old_provenance = "'Kategorie podle sledovacího pravidla (e-shop nepotvrzen)'"
    out = _replace_once(out, old_provenance, "'Kategorie prodejce nebyla potvrzena'", 'product provenance')
    old_card_provenance = "'Kategorie dle sledovacího pravidla (neověřeno e-shopem)'"
    out = _replace_once(out, old_card_provenance, "'Kategorie prodejce čeká na ověření'", 'mobile provenance')

    # The record is added only in browser memory. No catalog prices, history,
    # watch rules, or source data are ever written by the integration.
    loader = r'''async function loadCategoryOverlay(){
 const box=$('taxonomyV27Status');
 try{
  const resp=await fetch('./data/taxonomy_v27_public.json?ts='+Date.now(),{cache:'no-store'});
  if(!resp.ok)throw Error('HTTP '+resp.status);
  const data=await resp.json();
  if(data.schema!=='rk-v27-retailer-category-overlay-v1'||data.total!==db.items.length||!Array.isArray(data.items)||data.items.length!==db.items.length)
   throw Error('Počet produktů nesouhlasí');
  const map=new Map(data.items.map(x=>[String(x.store||'')+'|'+String(x.url||''),x]));
  if(map.size!==db.items.length||db.items.some(p=>!map.has(productId(p))))throw Error('Identita produktů nesouhlasí');
  for(const p of db.items){
   const tax=map.get(productId(p));
   p.category_v27=tax.category_v27;
   p.store_category_path=tax.store_category_path||[];
   p.category_source=tax.category_source||null;
  }
  const m=data.counts?.mapped||0,v=data.counts?.verified||0;
  const review=db.items.length-v;
  box.textContent='Kategorie dle e-shopu: '+nf(m)+' / '+nf(db.items.length)+'; plně ověřeno '+nf(v)+
   '; ke kontrole '+nf(review)+'. Neověřené a nesouhlasící položky zůstávají v katalogu.';
 }catch(e){
  for(const p of db.items){delete p.category_v27;}
  box.textContent='Kategorie e-shopů nejsou ověřené ('+e.message+'). Položky jsou ponechány ke kontrole; ceny se zobrazují beze změny.';
 }
}
'''
    marker = 'async function load(){try{'
    out = _replace_once(out, marker, loader + marker, 'overlay async loader')
    marker2 = "rules=new Map((db.rules||[]).map(r=>[r.id,r]));"
    out = _replace_once(out, marker2, "await loadCategoryOverlay();" + marker2, 'overlay load invocation')

    old_stamp = "$('stamp').textContent='Aktualizace: '+new Date(db.generated_at).toLocaleString('cs-CZ');"
    new_stamp = ("$('stamp').textContent='Poslední kontrola cen: '+new Date(db.last_price_monitor_at||db.generated_at).toLocaleString('cs-CZ');"
                 "$('stamp').title='Katalog původně sestaven: '+new Date(db.generated_at).toLocaleString('cs-CZ');")
    out = _replace_once(out, old_stamp, new_stamp, 'freshness label')

    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--live',required=True)
    ap.add_argument('--compiled',required=True)
    ap.add_argument('--html',required=True)
    ap.add_argument('--output-overlay',required=True)
    ap.add_argument('--output-html',required=True)
    ap.add_argument('--report',required=True)
    args=ap.parse_args()
    for path in (args.live,args.compiled,args.html):
        if not Path(path).is_file():raise ValueError(f'Input missing: {path}')
    inputs={Path(p).resolve() for p in (args.live,args.compiled,args.html)}
    outputs={Path(p).resolve() for p in (args.output_overlay,args.output_html,args.report)}
    if len(outputs)!=3 or inputs & outputs:raise ValueError('Outputs must be separate from source inputs')
    live=load_json(args.live); compiled=load_json(args.compiled)
    overlay=build_overlay(live, compiled)
    old_html=Path(args.html).read_text(encoding='utf-8')
    new_html=patch_html(old_html)
    if old_html == new_html and 'id="taxonomyV27Status"' not in new_html:
        raise AssertionError('Frontend integration was not generated')
    report={'schema':'rk-v27-publish-category-preview', 'total':overlay['total'],
            'category_counts':overlay['counts'],
            'live_prices_preserved':True,
            'live_items_preserved':True,
            'live_catalog_written':False,
            'mobile_layout_preserved':'id="mobileCards"' in new_html,
            'price_checked_at':live.get('last_price_monitor_at')}
    for dest,data in ((args.output_overlay,overlay),(args.report,report)):
        dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    h=Path(args.output_html);h.parent.mkdir(parents=True,exist_ok=True)
    h.write_text(new_html,encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
