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
    targets=[(k,item) for k,item in by_key.items() if
        (not args.only_produce or any(r in FRESH_IDS for r in item.get('rule_ids',[])))
        and (args.retry_missing or not item.get('store_category_path'))
        and (args.retry_missing or not item.get('taxonomy_checked_at'))]
    targets=targets[:args.max_products]
    if not targets:
        print('No new taxonomy checks needed; existing records preserved')
        print(make_public(catalog,by_key,catalog_path,args.review))
        return
    deadline=time.monotonic()+args.budget_seconds
    queue=asyncio.Queue()
    for obj in targets:queue.put_nowait(obj)
    results=Counter()
    completed=0
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
                    if host not in ('www.rohlik.cz','rohlik.cz','www.kosik.cz','kosik.cz') or \
                       (store=='Rohlík') != ('rohlik.cz' in host):
                        context={'store_category_path':[],'category_source':'error',
                                 'taxonomy_error':'Invalid source URL','product_description':''}
                    else:
                        try:
                            response=await page.goto(url,wait_until='domcontentloaded',timeout=22000)
                            if not response or response.status>=400:
                                raise RuntimeError(f'HTTP {response.status if response else "none"}')
                            await page.wait_for_timeout(650)
                            payload=await page.evaluate(CONTEXT_JS)
                            context=parse_context(payload)
                            # Avoid a stale page or redirection to a different product.
                            title=payload.get('title','')
                            original=rec.get('title') or rec.get('name') or ''
                            if not title or (len(original)>10 and original.casefold() not in title.casefold()
                                and title.casefold() not in original.casefold()):
                                context={'store_category_path':[],'category_source':'error',
                                         'taxonomy_error':'Product title changed / mismatch',
                                         'product_description':''}
                        except Exception as e:
                            context={'store_category_path':[],'category_source':'error',
                                     'taxonomy_error':f'{type(e).__name__}: {str(e)[:150]}',
                                     'product_description':''}
                    rec.update(context)
                    rec['taxonomy_checked_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
                    by_key[key]=rec
                    results[rec.get('category_source','missing')]+=1
                    completed+=1
                    if completed%20==0:
                        outcome=make_public(catalog,by_key,catalog_path,args.review)
                        print(f'Checked {completed}/{len(targets)}, {dict(results)}, {outcome}',flush=True)
                    queue.task_done()
                    await asyncio.sleep(0.2)
            finally:
                await ctx.close()
        await asyncio.gather(*(worker(i) for i in range(args.workers)))
        await browser.close()
    outcome=make_public(catalog,by_key,catalog_path,args.review)
    print(f'DONE: initial={all_count}, checked={completed}/{len(targets)}, '
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
    asyncio.run(run(p.parse_args()))
