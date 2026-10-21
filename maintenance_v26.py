#!/usr/bin/env python3
"""Bounded price monitoring of existing Rohlík/Košík URLs. NO discovery.
Preserves previously observed values on source failure, marks their age clearly.
Updates only after a product-identical, full-pack price is observed.
"""
from __future__ import annotations
import argparse
import collections
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlparse

DATE_FORMAT='%Y-%m-%dT%H:%M:%S+00:00'

def read(path, default):
    try: return json.loads(Path(path).read_text(encoding='utf8'))
    except FileNotFoundError:return default

def save(path,data):
    dst=Path(path); dst.parent.mkdir(parents=True,exist_ok=True)
    tmp=dst.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp.replace(dst)

def hours_since(row, key='last_monitor_attempt_at', now=None):
    try:
        current=now or datetime.now(timezone.utc)
        return (current-datetime.fromisoformat(row[key].replace('Z','+00:00'))).total_seconds()/3600
    except (KeyError,ValueError,TypeError):return float('inf')

def pick_items(items, limit=30, now=None):
    """Fair rotating queue; one merchant may not starve the other.
    Repeat errors no faster than every 24 h; prefer unverified but don't hammer.
    """
    now=now or datetime.now(timezone.utc)
    queues={'Košík':[],'Rohlík':[]}
    for row in items:
        shop=row.get('store'); url=row.get('url','')
        if shop not in queues or not isinstance(url,str):continue
        host=urlparse(url).hostname
        if host not in ('kosik.cz','www.kosik.cz','rohlik.cz','www.rohlik.cz'):continue
        if (shop=='Košík')!=('kosik.cz' in host):continue
        if hours_since(row,now=now)<24:continue
        # Products without a price are checked first; all others rotate by last attempt.
        missing=row.get('price_status')!='ok'
        # Recently failing sources still remain eligible but do not overtake never-attempted URLs.
        attempts=int(row.get('monitor_v26_attempts',0))
        rank=(0 if missing else 1,0 if attempts==0 else 1,
              row.get('last_monitor_attempt_at',''),row.get('name',''))
        queues[shop].append((rank,row))
    for shop in queues:queues[shop].sort(key=lambda x:x[0])
    result=[]
    # Košík has supplied full-pack prices more reliably. Still probe Rohlík cautiously.
    order=['Košík','Košík','Košík','Rohlík']
    for i in range(max(limit*2,3)):
        shop=order[i%len(order)]
        if not queues[shop]:shop='Rohlík' if shop=='Košík' else 'Košík'
        if not queues[shop]:break
        result.append(queues[shop].pop(0)[1])
        if len(result)>=limit:break
    return result

def apply_result(original, *, price=None, source=None, offer=None, status='unknown', checked_at=None, note=''):
    row=dict(original)
    checked_at=checked_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    row['last_monitor_attempt_at']=checked_at
    row['monitor_v26_attempts']=int(original.get('monitor_v26_attempts',0))+1
    row['monitor_v26_status']=status
    row['monitor_v26_note']=str(note)[:240]
    if status=='ok' and isinstance(price,(int,float)) and not isinstance(price,bool) and 0.5<=price<=50000:
        old=original.get('price_czk') if original.get('price_status')=='ok' else None
        old_time=original.get('checked_at')
        row['price_czk']=round(price,2)
        row['price_status']='ok'
        row['price_source']='monitor-v26:'+str(source or 'merchant-detail')
        row['checked_at']=checked_at
        offer=offer or {}
        row['original_price_czk']=offer.get('original_price_czk')
        row['discount_pct']=offer.get('discount_pct')
        row['offer_valid_until']=offer.get('offer_valid_until')
        row['multibuy']=([{'min_qty':offer['min_qty'],'price_czk':offer['multibuy_price_czk']}]
                         if offer.get('min_qty') and offer.get('multibuy_price_czk') is not None else [])
        row['price_history_previous_czk']=old
        row['price_history_previous_at']=old_time
        row['drop_since_previous_pct']=round(100*(old-price)/old,1) if old and price<old else None
    # FAILURE: Do not overwrite a good earlier observation; age/health UI reveals its staleness.
    return row

def inspect_saved(page,product):
    from monitor import inspect
    from price_v23 import PRODUCT_HEADER_JS,parse_product_offer,product_identity
    store=product['store'];now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    if store=='Rohlík':
        report=inspect(page,{'id':product['url'],'store':store,
                'label':product.get('title') or product.get('name'),'url':product['url']},now)
        status=report.get('status')
        return {'status':status,'price':report.get('price_czk'),
                'source':report.get('source'),'note':report.get('note',''),
                'blocked':report.get('http_status') in (403,429,503),
                'offer':{}}
    response=page.goto(product['url'],wait_until='domcontentloaded',timeout=25000)
    code=response.status if response else None
    if code in (403,429,503):return {'status':'throttled','price':None,'blocked':True,'note':'HTTP '+str(code)}
    if code!=200:return {'status':'http_error','price':None,'blocked':False,'note':'HTTP '+str(code)}
    page.wait_for_timeout(1000)
    details=page.evaluate(PRODUCT_HEADER_JS)
    if not product_identity(product.get('title') or product.get('name'),details.get('title')):
        return {'status':'title_mismatch','price':None,'blocked':False,'note':'Product identity differs'}
    offer=parse_product_offer(details.get('text',''),now)
    price=offer.get('price_czk')
    if price is None:return {'status':'price_unverified','price':None,'blocked':False,'note':offer.get('reason','Price unverified')}
    return {'status':'ok','price':price,'source':offer.get('source'),
            'offer':offer,'blocked':False,'note':offer.get('reason','Merchant price')}

def run(args):
    from playwright.sync_api import sync_playwright
    cat=read(args.catalog,None)
    if not isinstance(cat,dict) or not isinstance(cat.get('items'),list):raise RuntimeError('Invalid catalogue')
    allrows=cat['items']; now=datetime.now(timezone.utc)
    targets=pick_items(allrows,min(max(int(args.limit),1),35),now)
    found=set();stats=collections.Counter();price_updates=0;new_drops=[]
    positions={(p['store'],p['url']):i for i,p in enumerate(allrows)}
    # All changes kept in memory. Never publish partial failure as fresh catalogue.
    if not targets:raise RuntimeError('No product is eligible for safe daily verification')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        context={s:browser.new_context(locale='cs-CZ',timezone_id='Europe/Prague',viewport={'width':1366,'height':900}) for s in ('Košík','Rohlík')}
        pages={s:c.new_page() for s,c in context.items()}
        try:
            for i,row in enumerate(targets,1):
                shop=row['store']
                if shop in found:continue
                time.sleep(max(float(args.delay),2.5))
                try:result=inspect_saved(pages[shop],row)
                except Exception as e:result={'status':'error','price':None,'blocked':False,'note':type(e).__name__+': '+str(e)[:120]}
                if result.get('blocked'):found.add(shop)
                at=datetime.now(timezone.utc).isoformat(timespec='seconds')
                revised=apply_result(row,price=result.get('price'),source=result.get('source'),
                      offer=result.get('offer'),status=result['status'],checked_at=at,note=result.get('note',''))
                allrows[positions[(shop,row['url'])]]=revised
                stats[shop+'|'+result['status']]+=1
                if result['status']=='ok':
                    price_updates+=1
                    if revised.get('drop_since_previous_pct') and revised['drop_since_previous_pct']>=5:
                        new_drops.append({'store':shop,'url':row['url'],'name':row.get('name'),
                          'previous':revised['price_history_previous_czk'],'now':revised['price_czk'],
                          'drop_pct':revised['drop_since_previous_pct'],'checked_at':at})
                print(f'[{i}/{len(targets)}] {shop}: {row.get("name", "")[:44]} – {result["status"]}',flush=True)
        finally:
            for c in context.values():c.close()
            browser.close()
    cat['last_price_monitor_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    cat['verified_current_cycle']=sum(p.get('price_status')=='ok' for p in allrows)
    cat['monitor_v26']={'processed':sum(stats.values()),'updated_prices':price_updates,
                        'blocked_stores':sorted(found),'statuses':dict(stats),'last_price_monitor_at':cat['last_price_monitor_at']}
    # Keep source crawl date generated_at unchanged: a price check is not a new full catalogue scan.
    report={'schema':'rk-user-monitor-v26','at':cat['last_price_monitor_at'],**cat['monitor_v26'],
            'new_drops':new_drops,'remaining_missing':sum(p.get('price_status')!='ok' for p in allrows)}
    save(args.catalog,cat);save(args.report,report)
    summary={'scanned':sum(stats.values()),'updated':price_updates,'remaining':report['remaining_missing'], 'new_drops':len(new_drops),'blocked':sorted(found)}
    print('MONITOR v26',json.dumps(summary,ensure_ascii=False),flush=True)
    return 0 if price_updates>=1 else 2

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--catalog',default='docs/data/catalog_latest.json')
    p.add_argument('--report',default='docs/data/monitor_v26_report.json')
    p.add_argument('--limit',type=int,default=24)
    p.add_argument('--delay',type=float,default=3.3)
    raise SystemExit(run(p.parse_args()))
