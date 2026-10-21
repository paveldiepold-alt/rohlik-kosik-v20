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
                by_key[key]=product
    all_count=len(by_key)
    targets=[(k,item) for k,item in by_key.items()
             if should_retry_product(item, only_produce=args.only_produce)]
    requested=len(targets)
    # Alternate retailers so neither can starve the other in a limited batch.
    by_store={name:[entry for entry in targets if entry[1].get('store')==name]
              for name in ('Košík','Rohlík')}
    others=[entry for entry in targets if entry[1].get('store') not in by_store]
    alternating=[]
    for idx in range(max((len(v) for v in by_store.values()), default=0)):
        for name in ('Košík','Rohlík'):
            if idx<len(by_store[name]): alternating.append(by_store[name][idx])
    targets=(alternating+others)[:min(args.max_products, MAX_RETRY_PER_RUN)]
    print(f'Taxonomy retry: {requested} pending, {len(targets)} selected '
          f'(safety limit {MAX_RETRY_PER_RUN} per run).',flush=True)
    if not targets:
        print('No new taxonomy checks needed; existing records preserved')
        print(make_public(catalog,by_key,catalog_path,args.review))
        return
    deadline=time.monotonic()+args.budget_seconds
    queue=asyncio.Queue()
    for obj in targets:queue.put_nowait(obj)
    results=Counter()
    completed=0
    blocked_stores=set()
    store_locks={s:asyncio.Lock() for s in ('Rohlík','Košík')}
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,args=['--no-sandbox'])
        async def worker(idx):
            nonlocal completed
            ctx=await browser.new_context(locale='cs-CZ',timezone_id='Europe/Prague',viewport={'width':1260,'height':800})
            page=await ctx.new_page()
            try:
                while time.monotonic()<deadline:
                    try:key,item=queue.get_nowait()
                    except asyncio.QueueEmpty:break
                    rec=dict(item)
                    url=rec['url']
                    host=urlparse(url).hostname
                    store=rec['store']
                    if store in blocked_stores:
                        results['skipped_rate_limit']+=1
                        queue.task_done()
                        continue
                    # Serialize per retailer and slow requests so 429 does not
                    # cascade into hundreds of false failures in a few seconds.
                    async with store_locks.setdefault(store,asyncio.Lock()):
                        if store in blocked_stores:
                            results['skipped_rate_limit']+=1
                            queue.task_done()
                            continue
                        await asyncio.sleep(args.delay_seconds)
                        if host not in ('www.rohlik.cz','rohlik.cz','www.kosik.cz','kosik.cz') or \
                           (store=='Rohlík') != ('rohlik.cz' in host):
                            context={'store_category_path':[],'category_source':'error',
                                     'taxonomy_error':'Invalid source URL','product_description':''}
                        else:
                            try:
                                response=await page.goto(url,wait_until='domcontentloaded',timeout=22000)
                                code=response.status if response else 0
                                if code in (403,429,503):
                                    blocked_stores.add(store)
                                    raise RuntimeError(f'HTTP {code}: shop checks paused for this run')
                                if not response or code>=400:
                                    raise RuntimeError(f'HTTP {code or "none"}')
                                await page.wait_for_timeout(650)
                                payload=await page.evaluate(CONTEXT_JS)
                                context=parse_context(payload)
                                original=rec.get('title') or rec.get('name') or ''
                                if not product_identity_matches(original,payload):
                                    context={'store_category_path':[],'category_source':'error',
                                             'taxonomy_error':'Product title changed / mismatch',
                                             'product_description':''}
                            except Exception as e:
                                context={'store_category_path':[],'category_source':'error',
                                         'taxonomy_error':f'{type(e).__name__}: {str(e)[:150]}',
                                         'product_description':''}
                        rec.update(context)
                        rec['taxonomy_checked_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
                        rec['taxonomy_attempts']=int(rec.get('taxonomy_attempts',1 if item.get('taxonomy_checked_at') else 0))+1
                        by_key[key]=rec
                        results[rec.get('category_source','missing')]+=1
                        completed+=1
                        if completed%20==0:
                            outcome=make_public(catalog,by_key,catalog_path,args.review)
                            print(f'Checked {completed}/{len(targets)}, {dict(results)}, '
                                  f'blocked={sorted(blocked_stores)}, {outcome}',flush=True)
                    queue.task_done()
                    await asyncio.sleep(0.2)
            finally:
                await ctx.close()
        await asyncio.gather(*(worker(i) for i in range(min(args.workers,2))))
        await browser.close()
    outcome=make_public(catalog,by_key,catalog_path,args.review)
    print(f'DONE: initial={all_count}, checked={completed}/{len(targets)}, blocked_shops={sorted(blocked_stores)}, '
          f'sources={dict(results)}, public/review={outcome}',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--catalog',default='docs/data/catalog_latest.json')
    p.add_argument('--review',default='docs/data/catalog_taxonomy_review.json')
    p.add_argument('--max-products',type=int,default=650)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--budget-seconds',type=int,default=1800)
    p.add_argument('--only-produce',action='store_true',default=True)
    p.add_argument('--all',dest='only_produce',action='store_false')
    p.add_argument('--retry-missing',action='store_true',default=False)
    p.add_argument('--delay-seconds',type=float,default=2.5)
    asyncio.run(run(p.parse_args()))
