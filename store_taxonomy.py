"""Retailer-category-first classification for the existing Rohlík/Košík v20 scan.

No guessing from a search term. If authoritative breadcrumbs are missing, put fresh
produce candidates into review instead of silently calling them fresh.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import re
import unicodedata

FRESH_IDS = {f'W{x:03d}' for x in range(37, 48)}
FRUIT_IDS = {f'W{x:03d}' for x in range(37, 43)}

# Extract ONLY scoped structured breadcrumbs / category navigation; never use
# all navigation links on the page (mega-menu and recommendations pollute data).
CONTEXT_JS = r'''() => {
 const clean = s => (s || '').replace(/\s+/g,' ').trim();
 const h = document.querySelector('h1');
 const title = clean(h && h.textContent);
 const ld = [...document.querySelectorAll('script[type="application/ld+json"]')]
      .map(s => (s.textContent||'').slice(0,60000));
 const metaDescription = clean(document.querySelector('meta[name="description"]')?.content || '');
 let crumbs = [];
 const blocks = [...document.querySelectorAll('[aria-label*="breadcrumb" i], [class*="breadcrumb" i], [data-testid*="breadcrumb" i], nav[itemtype*="BreadcrumbList"], ol[itemtype*="BreadcrumbList"]')];
 for (const block of blocks) {
   const list = [...block.querySelectorAll('li')].map(n=>clean(n.textContent)).filter(Boolean);
   const links = [...block.querySelectorAll('a,[itemprop="name"]')]
     .map(n => clean(n.textContent)).filter(Boolean);
   const trail = list.length>=2 ? list : links;
   if (trail.length >= 2 && trail.length <= 9 && trail.join('|').length < 420) {
     crumbs = trail; break;
   }
 }
 // On some retailer detail pages the breadcrumb widget is not labelled.
 // Category hyperlinks in the product's MAIN content remain useful but only
 // if there are few enough to plausibly represent a taxonomy trail.
 let categoryLinks = [];
 const main = h?.closest('main') || document.querySelector('main');
 if (main) {
   const shop = location.hostname;
   categoryLinks = [...main.querySelectorAll('a[href]')].filter(a => {
     try { const u = new URL(a.href, location.href);
       return u.hostname.replace(/^www\./,'') === shop.replace(/^www\./,'') && /^\\/c\\d{2,}(?:[-/]|$)/.test(u.pathname);
     } catch(_) { return false; }
   }).map(a => ({name:clean(a.textContent),url:a.href}))
     .filter(a => a.name && a.name.length < 65);
   categoryLinks = categoryLinks.filter((a,i) => categoryLinks.findIndex(b => b.url === a.url)===i);
   if (categoryLinks.length > 10) categoryLinks = [];
 }
 return {title, jsonld:ld, dom_breadcrumbs:crumbs,
         scoped_category_links:categoryLinks, meta_description:metaDescription};
}'''
# Fix escaped delimiter to plain JS regex literal, serialized as raw string.
CONTEXT_JS = CONTEXT_JS.replace('\\\\/c\\\\d', '\\/c\\d')


def fold(value: object) -> str:
    raw = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return ' '.join(''.join(ch for ch in raw if not unicodedata.combining(ch)).split())


def _clean_path(path: list[str], title: str = '') -> list[str]:
    out = []
    for part in path:
        p = str(part or '').strip()
        if not p or fold(p) in {'kosik.cz','kosik', 'rohlik.cz','rohlik','domu','homepage','uvod', 'produkty'}:
            continue
        if title and fold(p) == fold(title):
            continue
        if not out or fold(out[-1]) != fold(p):
            out.append(p[:110])
    return out[:9]


def _jsonld_walk(node):
    if isinstance(node,list):
        for x in node: yield from _jsonld_walk(x)
    if isinstance(node,dict):
        yield node
        if '@graph' in node: yield from _jsonld_walk(node['@graph'])


def parse_context(payload: dict) -> dict:
    """Parse normalized taxonomy from a Playwright extraction payload (offline-testable)."""
    title = str(payload.get('title') or '')[:200]
    description = str(payload.get('meta_description') or '')[:750]
    data = []
    for raw in payload.get('jsonld',[]):
        try: data.extend(_jsonld_walk(json.loads(raw)))
        except (ValueError, TypeError): continue
    for obj in data:
        typ = obj.get('@type', [])
        types = typ if isinstance(typ,list) else [typ]
        if 'BreadcrumbList' in types:
            steps = sorted((a for a in obj.get('itemListElement',[]) if isinstance(a,dict)),
                           key=lambda a: int(a.get('position') or 0))
            path = []
            for step in steps:
                item = step.get('item')
                name = step.get('name') or (item.get('name') if isinstance(item,dict) else None)
                if name: path.append(str(name))
            result = _clean_path(path, title)
            if result:
                return {'store_category_path':result,'category_source':'jsonld_breadcrumb',
                        'product_description':description}
    path = _clean_path(payload.get('dom_breadcrumbs') or [],title)
    if path:
        return {'store_category_path':path,'category_source':'dom_breadcrumb',
                'product_description':description}
    links = payload.get('scoped_category_links') or []
    if 1 <= len(links) <= 8:
        path = _clean_path([x.get('name','') for x in links if isinstance(x,dict)],title)
        if path:
            return {'store_category_path':path,'category_source':'product_category_links',
                    'product_description':description}
    for obj in data:
        typ = obj.get('@type', [])
        types = typ if isinstance(typ,list) else [typ]
        if 'Product' in types:
            description = str(obj.get('description') or description)[:750]
            cat = obj.get('category')
            if isinstance(cat,dict): cat = cat.get('name')
            if isinstance(cat,str) and len(cat)<200:
                path = _clean_path(re.split(r'\s*[>/|]\s*',cat),title)
                if path: return {'store_category_path':path,'category_source':'jsonld_product_category',
                                 'product_description':description}
    return {'store_category_path':[],'category_source':'missing',
            'product_description':description}


def extract_shop_context(page) -> dict:
    """Use an already-loaded retailer product page; no second navigation."""
    try: return parse_context(page.evaluate(CONTEXT_JS))
    except Exception as exc:
        return {'store_category_path':[],'category_source':'error',
                'product_description':'', 'taxonomy_error':f'{type(exc).__name__}: {str(exc)[:140]}'}


def decide_fresh_rule(rule_id: str, context: dict) -> tuple[str,str]:
    """accept / reject / review; only retailer taxonomy may prove freshness."""
    if rule_id not in FRESH_IDS: return 'accept','Non-produce rule; original matcher applies'
    path = context.get('store_category_path') or []
    source = context.get('category_source')
    if not path or source in ('missing','error',None):
        return 'review','Prodejce neposkytl spolehlivou kategorii'
    folded = [fold(p) for p in path]
    joined = ' | '.join(folded)
    # A processed/frozen food can mention fruit/vegetables in a subcategory.
    processed = ('mrazene','zmrzlin','sorbet','susene','konzerv','nakladan','zpracovan',
                 'detska vyziva','prikrm','napoj','limonad','stav','dzus','pecivo','cokolad',
                 'cukrovink','drogerie','koreni','kosmetika','jogur','mlecne','maso','pamlsk')
    if any(token in joined for token in processed):
        return 'reject','Kategorie obchodu označuje jiný/zpracovaný výrobek'
    # Retailers expose either the broad parent "Ovoce" or a clearly named leaf.
    fruit = ('ovoce', 'banany a exoticke', 'citrusy', 'jablka a hrusky',
             'hrozny a melouny', 'jahody a lesni plody', 'peckoviny a bobuloviny',
             'bobuloviny', 'cerstve ovoce', 'banany', 'hrozny')
    veg = ('zelenina','rajcata a papriky','okurky a cukety', 'korenova zelenina',
           'cerstva zelenina','papriky','rajcata','okurky','mrkev')
    def is_match(tokens):
        return any((val == t or val.startswith(t+' ') or val.endswith(' '+t))
                   for val in folded if val != 'ovoce a zelenina' for t in tokens)
    # Combined parent "Ovoce a zelenina" alone is ambiguous.
    if len(folded)==1 and folded[0]=='ovoce a zelenina':
        return 'review','Pouze společná kategorie Ovoce a zelenina'
    if rule_id in FRUIT_IDS:
        if is_match(fruit): return 'accept','Čerstvé ovoce dle kategorie obchodu'
        return 'reject','Produkt není v kategorii čerstvého ovoce'
    if is_match(veg): return 'accept','Čerstvá zelenina dle kategorie obchodu'
    return 'reject','Produkt není v kategorii čerstvé zeleniny'


def gate_item(item: dict, *, strict_missing: bool = True) -> tuple[dict|None,dict|None]:
    """Returns (public item or None, review record or None), never deletes originals."""
    row = dict(item)
    ids = list(row.get('rule_ids',[]))
    produce_ids = [rid for rid in ids if rid in FRESH_IDS]
    if not produce_ids: return row, None
    valid = [rid for rid in ids if rid not in FRESH_IDS]
    decisions = []
    for rid in produce_ids:
        status, reason = decide_fresh_rule(rid, row)
        decisions.append({'rule_id':rid,'decision':status,'reason':reason})
        if status == 'accept':valid.append(rid)
    row['rule_ids'] = sorted(set(valid))
    if valid:
        row['taxonomy_status'] = 'verified' if all(x['decision']=='accept' for x in decisions) else 'partial'
        return row, ({**dict(item),'taxonomy_decisions':decisions} if any(d['decision']!='accept' for d in decisions) else None)
    if not strict_missing and all(d['decision']=='review' for d in decisions):
        row['taxonomy_status']='review'
        return row, {**dict(item),'taxonomy_decisions':decisions}
    return None,{**dict(item),'taxonomy_decisions':decisions,
                 'taxonomy_status':'review' if any(d['decision']=='review' for d in decisions) else 'rejected'}


def partition_items(items: list[dict]) -> tuple[list[dict],list[dict]]:
    # v24: apply retailer taxonomy and item-type guard across all categories.
    from catalog_quality_v24 import gate_catalog_item
    visible,review=[],[]
    for row in items:
        included, excluded=gate_item(row)  # existing fresh produce verification
        if excluded:review.append(excluded)
        if included:
            verified, flagged = gate_catalog_item(included)
            if verified:visible.append(verified)
            if flagged:review.append(flagged)
    return visible,review
