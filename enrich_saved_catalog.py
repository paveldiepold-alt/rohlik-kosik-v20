#!/usr/bin/env python3
"""One-time retailer taxonomy enrichment of already discovered product URLs.

Do not run a new catalogue search. Preserve all observations in either public
catalog or review data; do not claim missing taxonomy is a valid category.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlparse
from store_taxonomy import FRESH_IDS, CONTEXT_JS, parse_context, partition_items


def load(path, fallback):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError: return fallback


def save(path, data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)


def make_public(catalog, rows, catalog_path, review_path):
    visible,review=partition_items(list(rows.values()))
    cat=dict(catalog)
    cat['items']=sorted(visible,key=lambda a:(a.get('store',''),a.get('name','').casefold()))
    cat['discovered_total']=len(visible)
    cat['verified_current_cycle']=sum(p.get('price_status')=='ok' and
                        p.get('cycle')==cat.get('cycle',1) for p in visible)
    cat['rules_seen']=len({rid for item in visible for rid in item.get('rule_ids',[])})
    cat['taxonomy_v21']={'total_known':len(rows),'visible':len(visible),
                        'review_or_rejected':len(review),'category_verified':sum(
                         bool(p.get('store_category_path')) for p in rows.values())}
    cat['note']=str(cat.get('note') or '').split(' | Kategorie prodejce')[0] + \
       f' | Kategorie prodejce: {len(visible)} veřejných produktů; {len(review)} záznamů k prověření.'
    cat['generated_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    save(catalog_path,cat)
    save(review_path,{'schema':'rk-v21-taxonomy-review-1',
                       'generated_at':cat['generated_at'],
                       'count':len(review),'items':review})
    return cat['taxonomy_v21']


# Conservative incremental retry policy: do not re-fetch confirmed category pages,
# and do not hammer retailer pages after rate limiting.
MAX_RETRY_PER_RUN = 100
MAX_NON_RATE_RETRIES = 2


def should_retry_product(item: dict, *, only_produce: bool = True) -> bool:
    if only_produce and not any(r in FRESH_IDS for r in item.get('rule_ids', [])):
        return False
    if item.get('store_category_path'):
        return False  # Already verified using retailer metadata.
    if not item.get('taxonomy_checked_at'):
        return True  # Previously discovered, never checked.
    if item.get('category_source') not in ('error', 'missing'):
        return False
    reason = str(item.get('taxonomy_error') or '')
    if '429' in reason or '403' in reason or '503' in reason:
        return int(item.get('taxonomy_attempts', 0)) < 6
    # Old v21 error records had one attempted request, before this counter existed.
    return int(item.get('taxonomy_attempts', 1)) < MAX_NON_RATE_RETRIES


def product_identity_matches(original: str, payload: dict) -> bool:
    """Confirm identity via visible heading or Product JSON-LD, not URL keyword."""
    import re
    import unicodedata
    def tokens(s):
        z = unicodedata.normalize('NFKD', str(s or '')).casefold()
        z = ''.join(c for c in z if not unicodedata.combining(c))
        return re.findall(r'[a-z0-9]+', z)
    base = tokens(original)
    if not base: return False
    candidates = [payload.get('title','')]
    for raw in payload.get('jsonld', []):
        try: obj=json.loads(raw)
        except (ValueError,TypeError): continue
        def walk(node):
            if isinstance(node,list):
                for x in node: yield from walk(x)
            elif isinstance(node,dict):
                yield node
                if '@graph' in node: yield from walk(node['@graph'])
        for obj2 in walk(obj):
            types=obj2.get('@type',[])
            if 'Product' in (types if isinstance(types,list) else [types]):
                candidates.append(obj2.get('name',''))
    from collections import Counter
    a=Counter(base)
    for candidate in candidates:
        b=Counter(tokens(candidate))
        if not b: continue
        shared=sum((a & b).values())
        # A swapped word order or accent change is fine. A different product or
        # redirected shop homepage must not be treated as a verified product.
        if shared / sum(a.values()) >= 0.90 and shared / sum(b.values()) >= 0.75:
            return True
    return False



async def run(args):
    catalog_path=Path(args.catalog)
    catalog=load(catalog_path, None)
    if not catalog or not isinstance(catalog.get('items'),list):
        raise ValueError('Missing valid initial catalog')
    old_review=load(args.review,{}).get('items',[])
    by_key={}
    for product in [*old_review,*catalog['items']]:
        if product.get('url') and product.get('store'):
            key=product['store']+'|'+product['url']
            if key in by_key:
                # One URL can have more than one rule; preserve all associations.
                old=by_key[key]
                by_key[key]={**old,**product,
                    'rule_ids':sorted(set(old.get('rule_ids',[])) | set(product.get('rule_ids',[])))}
            else:

