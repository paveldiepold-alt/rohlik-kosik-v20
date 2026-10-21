#!/usr/bin/env python3
"""Safe, bounded replay of existing retailer URLs: NO product search.

Leaves catalogue taxonomy untouched. Stores old observations in explicit
legacy fields; only new verified whole-package prices are published as OK.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import time
from urllib.parse import urlparse


def read(path,default):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:return default


def write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    tmp.replace(path)


def score(row):
    if row.get('store')!='Košík':return -1
    # UAT first: unit-value artefacts; then genuinely missing prices; then
    # past prices from the older generic Košík text parser. No brand rules.
    if (row.get('price_status')=='ok' and row.get('price_source')=='kosik-product-text'
        and isinstance(row.get('price_czk'),(int,float)) and row['price_czk']<20):return 300
    if row.get('price_status')!='ok':return 200
    if row.get('price_source')=='kosik-product-text':return 100
    return 0


def candidates(data,focus='',limit=50):
    q=focus.casefold().strip()
    options=[]
    for row in data.get('items',[]):
        if row.get('store')!='Košík' or not row.get('url'):continue
        if q and q not in (row.get('name') or row.get('title') or '').casefold():continue
        # Successful checks are final for this correction cycle. Temporary
        # failures may be retried once, but are not hammered indefinitely.
        if row.get('price_v22_result')=='ok':continue
        if int(row.get('price_v22_attempts',0))>=2:continue
        if score(row)<0:continue
        options.append(row)
    return sorted(options,key=lambda x:(-score(x),str(x.get('name',''))))[:limit]


def apply_observation(row,result,checked):
    """Pure transformation: never silently accept a stale or per-unit price."""
    updated=dict(row)
    if 'legacy_price_czk' not in updated:
        updated['legacy_price_czk']=row.get('price_czk')
        updated['legacy_price_status']=row.get('price_status')
        updated['legacy_price_source']=row.get('price_source')
    updated['price_v22_checked_at']=checked
    updated['price_v22_attempts']=int(row.get('price_v22_attempts',0))+1
    updated['price_v22_result']=result.get('status')
    updated['price_v22_note']=result.get('note','')
    if result.get('status')=='ok' and result.get('price_czk') is not None:
        updated['price_czk']=result['price_czk']
        updated['price_status']='ok'
        updated['price_source']=result.get('source')
        updated['checked_at']=checked
        updated['note']=result.get('note','')
    else:
        # An earlier faulty value cannot remain verified after a failed replay.
        updated['price_czk']=None
        updated['price_status']='price_unverified'
        updated['price_source']=None
        updated['note']='v22: znovu neověřeno – '+str(result.get('note') or result.get('status') or '')[:220]
    return updated


def run(args):
    from playwright.sync_api import sync_playwright
    from monitor import inspect
    catalog=read(args.catalog,{})
    if not isinstance(catalog.get('items'),list):raise ValueError('No saved catalogue items')
    targets=candidates(catalog,args.focus,min(args.max_products,70))
    print(f'v22 PRICE RECHECK: {len(targets)} URLs, filter={args.focus or "all"}, no catalogue search',flush=True)
    by_key={r['store']+'|'+r['url']:r for r in catalog['items']}
    counts=Counter();sample=[];blocked=False
    deadline=time.monotonic()+args.budget_seconds
    if targets:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            ctx=browser.new_context(locale='cs-CZ',timezone_id='Europe/Prague',viewport={'width':1366,'height':900})
            page=ctx.new_page()
            try:
                for row in targets:
                    if blocked or time.monotonic()>deadline:break
                    time.sleep(args.delay_seconds)
                    at=datetime.now(timezone.utc).isoformat(timespec='seconds')
                    entry={'id':row['url'],'store':row['store'],
                           'label':row.get('title') or row['name'],'url':row['url']}
                    result=inspect(page,entry,at)
                    if result.get('http_status') in (403,429,503):
                        blocked=True
                        print('STORE THROTTLED – stop; no requests to bypass source limits',flush=True)
                    key=row['store']+'|'+row['url']
                    by_key[key]=apply_observation(row,result,at)
                    counts[result.get('status','?')]+=1
                    if len(sample)<30:
                        sample.append({'name':row.get('name'),'url':row['url'],
                                       'before':row.get('price_czk'),'after':by_key[key].get('price_czk'),
                                       'status':result.get('status'), 'reason':result.get('note','')[:160]})
                    print(f'[{sum(counts.values())}/{len(targets)}] {row.get("name")[:65]}:'
                          f' {row.get("price_czk")} -> {by_key[key].get("price_czk")}; {result.get("status")}',flush=True)
            finally:
                ctx.close();browser.close()
    cat=dict(catalog)
    cat['items']=[by_key[r['store']+'|'+r['url']] for r in catalog['items']]
    cat['generated_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    current_cycle=max((r.get('cycle',1) for r in cat['items']),default=1)
    cat['verified_current_cycle']=sum(r.get('price_status')=='ok' and r.get('cycle',1)==current_cycle for r in cat['items'])
    cat['price_v22']={'last_check':cat['generated_at'],'processed':sum(counts.values()),'statuses':dict(counts),'blocked':blocked}
    # Only write report and changed catalog; no taxonomy review files edited.
    report={'schema':'rk-v22-price-review-1','run_at':cat['generated_at'],
            'processed':sum(counts.values()),'requested':len(targets),'statuses':dict(counts),
            'blocked':blocked,'sample':sample,
            'note':'Price values are whole packs only when validated; no inferred price or location availability.'}
    write(args.catalog,cat);write(args.report,report)
    print('v22 DONE:',json.dumps({'count':len(cat['items']),'prices_ok':cat['verified_current_cycle'],
                                  'batch':report['processed'],'statuses':report['statuses'],'blocked':blocked}),flush=True)
    # A blocked run should not be labelled as complete; report remains persisted.
    return 2 if blocked else 0

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--catalog',default='docs/data/catalog_latest.json')
    p.add_argument('--report',default='docs/data/catalog_price_review_v22.json')
    p.add_argument('--max-products',type=int,default=40)
    p.add_argument('--budget-seconds',type=int,default=1200)
    p.add_argument('--delay-seconds',type=float,default=3)
    p.add_argument('--focus',default='')
    raise SystemExit(run(p.parse_args()))
