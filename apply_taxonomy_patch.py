#!/usr/bin/env python3
"""Idempotent, structural patch for the existing v20 catalog_monitor.py.

Applies context capture at the already-loaded detail and authoritative taxonomy
validation at publication. Does not modify search, price extraction or watchlist.
"""
from __future__ import annotations
import ast
import sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv)>1 else 'catalog_monitor.py')
text = src.read_text(encoding='utf-8')
if '# taxonomy-v21: context from retailer product page' in text:
    print('Taxonomy v21 patch already installed')
    raise SystemExit(0)

patches = [
(
"""    current=load(DATA/'catalog_latest.json',{})
    items={x['store']+'|'+x['url']:x for x in current.get('items',[]) if isinstance(x,dict) and x.get('url') and x.get('store')}
""",
"""    current=load(DATA/'catalog_latest.json',{})
    pending=load(DATA/'catalog_taxonomy_review.json',{}).get('items',[])
    # Include quarantined records so each new cycle may recheck their retailer taxonomy.
    all_saved=[*current.get('items',[]), *pending]
    items={x['store']+'|'+x['url']:x for x in all_saved if isinstance(x,dict) and x.get('url') and x.get('store')}
"""
),
(
"""                        detail_checked+=1
                        multibuy=[]
""",
"""                        detail_checked+=1
                        # taxonomy-v21: context from retailer product page, after inspect() has navigated.
                        from store_taxonomy import extract_shop_context
                        if row.get('http_status') == 200 and row.get('status') != 'title_mismatch':
                            shop_context=extract_shop_context(detail_pages[shop])
                        else:
                            shop_context={'store_category_path':[],'category_source':'missing',
                                          'product_description':''}
                        multibuy=[]
"""
),
(
"""                        items[k]={**product, 'cycle':state['cycle'],
""",
"""                        items[k]={**product, **shop_context, 'taxonomy_checked_at':at, 'cycle':state['cycle'],
"""
),
(
"""    all_items = cleaned_items

    verified_current=sum(""",
"""    all_items = cleaned_items
    # Category MUST come from retailer detail, not the search phrase.
    from store_taxonomy import partition_items
    all_items, needs_review=partition_items(all_items)
    dump(DATA/'catalog_taxonomy_review.json', {
        'schema':'rk-v21-taxonomy-review-1',
        'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'count':len(needs_review), 'items':needs_review})

    verified_current=sum("""
)
]
for old,new in patches:
    n=text.count(old)
    if n!=1:
        raise SystemExit(f'STOP: Expected one matching location, got {n}: {old[:70]!r}')
    text=text.replace(old,new,1)

# Old name-only produce filters are unsuitable as authoritative classification.
# Keep candidate matching against watchlist product names, but require retailer
# category to qualify it for the visible catalogue.
old="""    # Do not treat a product mentioning fruit/vegetables as fresh produce.
    if rule.get('required_product_state') in ('cerstve_ovoce', 'cerstva_zelenina'):
        if not is_fresh_produce_name(name, rule):
            return False
"""
if old in text:
    text=text.replace(old,"""    # Produce name is only a candidate; shop taxonomy is checked after detail fetch.
""",1)

# Save a valid working Python file and retain fallback if validation fails.
ast.parse(text,filename=str(src))
src.write_text(text,encoding='utf-8')
print('OK: v20 collector now captures shop categories; publishing gate is category-first')
