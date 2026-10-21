"""Bounded price validation for existing Košík laundry items only.
No store search, no fabricated prices, no Rohlík 429 retries.
"""
from __future__ import annotations
import argparse,json,time,math
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from price_v23 import PRODUCT_HEADER_JS,parse_product_offer,product_identity

def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)

def select(items,rules,limit=24):
    cats={r['id']:r['category'] for r in rules}
    candidates=[p for p in items if p.get('store')=='Košík'
         and p.get('price_status')!='ok'
         and p.get('price_v24_attempts',0)<1
         and any(cats.get(rid)=='Praní' for rid in p.get('rule_ids',[]))
         and urlparse(p.get('url','')).hostname in ('kosik.cz','www.kosik.cz')]
    return sorted(candidates,key=lambda p:p.get('name',''))[:max(0,min(limit,30))]

def main(args):
    from playwright.sync_api import sync_playwright
    p=Path(args.catalog);d=json.loads(p.read_text(encoding='utf-8'))
    chosen=select(d['items'],d['rules'],args.limit)
    observations={};counts=Counter();blocked=False
    if chosen:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
            ctx=browser.new_context(locale='cs-CZ',timezone_id='Europe/Prague',viewport={'width':1366,'height':900})
            page=ctx.new_page()
            try:
                for item in chosen:
                    time.sleep(max(2.5,args.delay))
                    ts=datetime.now(timezone.utc).isoformat(timespec='seconds')
                    status='price_unverified';why='No verified whole-pack price';offer={};code=None
                    try:
                        rsp=page.goto(item['url'],wait_until='domcontentloaded',timeout=25000)
                        code=rsp.status if rsp else 0
                        if code in (403,429,503):
                            blocked=True;status='throttled';why=f'HTTP {code}; stop checking retailer'
                        elif code!=200:status='http_error';why=f'HTTP {code}'
                        else:
                            page.wait_for_timeout(1200)
                            payload=page.evaluate(PRODUCT_HEADER_JS)
                            if not product_identity(item.get('title') or item.get('name',''),payload.get('title','')):
                                status='title_mismatch';why='Retailer product identity not confirmed'
                            else:
                                offer=parse_product_offer(payload.get('text',''),ts)
                                if offer.get('price_czk') is not None:
                                    status='ok';why=offer.get('reason','Whole-pack price')
                                else:why=offer.get('reason','Price not unambiguous')
                    except Exception as e:status='error';why=f'{type(e).__name__}: {str(e)[:120]}'
                    key=(item['store'],item['url'])
                    observations[key]={'status':status,'why':why,'offer':offer,'checked_at':ts,'http_status':code}
                    counts[status]+=1
                    print(item['name'][:60],status,offer.get('price_czk'),flush=True)
                    if blocked:break
            finally:ctx.close();browser.close()
    for item in d['items']:
        val=observations.get((item['store'],item['url']))
        if not val:continue
        item['price_v24_attempts']=int(item.get('price_v24_attempts',0))+1
        item['price_v24_status']=val['status']
        item['price_v24_checked_at']=val['checked_at']
        item['price_v24_note']=val['why']
        if val['status']=='ok':
            price=val['offer']['price_czk']
            item['price_czk']=price;item['price_status']='ok'
            item['price_source']='product-detail-v23:'+val['offer'].get('source','pack')
            item['checked_at']=val['checked_at']
            for key in ('original_price_czk','discount_pct','offer_valid_until'):
                item[key]=val['offer'].get(key)
            item['note']=val['why']
    checked=sum(counts.values());ok=counts['ok'];required=math.ceil(len(chosen)*0.70)
    report={'schema':'rk-v24-laundry-prices','requested':len(chosen),'checked':checked,
           'verified':ok,'required_verified':required,'status_counts':dict(counts),'blocked':blocked,
           'sample':[{'name':r.get('name'),'status':observations.get((r['store'],r['url']),{}).get('status'),
                      'price':r.get('price_czk')} for r in chosen]}
    d['verified_current_cycle']=sum(x.get('price_status')=='ok' for x in d['items'])
    save(p,d);save(args.report,report)
    print('LAUNDRY PRICE PILOT',json.dumps(report,ensure_ascii=False)[:1800],flush=True)
    return 0 if len(chosen)>0 and ok>=required and not blocked else 2
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--catalog',default='docs/data/catalog_latest.json');ap.add_argument('--report',default='docs/data/catalog_laundry_v24.json');ap.add_argument('--limit',type=int,default=24);ap.add_argument('--delay',type=float,default=3)
    raise SystemExit(main(ap.parse_args()))
