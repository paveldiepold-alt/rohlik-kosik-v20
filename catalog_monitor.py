"""v20: food-first discovery of all 75 tracked rules via public site search.

Evidence is kept separate from actual price verification and coverage. The
catalogue is not claimed to be complete just because search queries finished.
No login, unofficial API access, captcha bypass or inferred prices.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from catalog_search import (FOOD_CATEGORY_ORDER, balanced_queries, plan_jobs, job_key, scan_plan_signature,
                            scan_single_query)
from monitor import inspect

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'docs' / 'data'
CONFIG = ROOT / 'watchlist.json'
URL_RE = {'Rohlík': re.compile(r'^/\d{5,}(?:-[\w-]+)?/?$', re.I),
          'Košík': re.compile(r'^/p\d+(?:-[\w-]+)?/?$', re.I)}
BASE = {'Rohlík': 'https://www.rohlik.cz/', 'Košík': 'https://www.kosik.cz/'}


def folded(s: object) -> str:
    x = unicodedata.normalize('NFKD', str(s or '')).casefold()
    x = ''.join(c for c in x if not unicodedata.combining(c))
    return re.sub(r'[^\w]+', ' ', x, flags=re.UNICODE).strip()


def has_expression(name: str, expr: str) -> bool:
    """Unicode-aware wildcard stems in watchlist rule terms."""
    pattern = folded(expr).replace(' ', r'\s+')
    if '*' in expr:
        # folded() removes punctuation; compile stem wildcards from pieces instead.
        terms = [re.escape(folded(piece)).replace(r'\ ',r'\s+') for piece in expr.split('*')]
        pat = r'\b' + r'\w*'.join(terms) + r'\w*'
        return bool(re.search(pat, name))
    return bool(re.search(r'(?<!\w)' + re.escape(folded(expr)).replace(r'\ ',r'\s+') + r'(?!\w)', name))



# Fresh produce must be the item sold, never merely an ingredient, flavor,
# fragrance, plant treated by a product or a mention in a baby-food recipe.
_FRESH_REJECT_STEMS = (
    'aktimel','actimel','activia','zaky','kefir','jogurt','tvaroh',
    'smetan','mlec','mlik','puding','dezert','presnidav','vyziv',
    'detsk','kojeneck','kasi','pyre','smoothie','dzem','marmelad',
    'kompot','nektar','dzus','sirup','limonad','napoj','stav',
    'susen','mrazen','lyofiliz','zmrzlin','vafl','oplatk','susenek',
    'cokolad','bonbon','cukrovink','tycink','lizatk','kolac','muffin',
    'peciv','chleb','mous','protein','musli','cereal','vitamin',
    'dopln','tabletk','kapsl','protein', 'sladid', 'neslazen',
    'hnojiv','substrat','postrik','osivo','semeno','sazenic','pestov',
    'houbi','myci','mydl','cistic','cistici','praci','prasek','avivaz',
    'vonn','vuni','vune','osvezov','svick','parfem','aroma',
    'sampon','sprch','gel','krem','balzam','sera','kosmetik',
    'prichut','ochucen','koncentrat','mast','peeling','air wick',
    'krmiv','granul','pamlsk','veterinar','psi','kocici',
    'protlak','kecup','omack','polivk','instant','hotov','konzerv',
    'sterilov','nakladan','zavaren','sekan','loupan','drcen',
    'pecen','grilovan','smaz','vareny','syr','salam','pecivo',
    'snack','chips','nalozen','marinovan','susena',
)
_FRESH_REJECT_PHRASES = (
    's prichuti', 's vuni', 'detska vyziva', 'detske prikrmy',
    'pro rajcata', 'pro papriky', 's boruvkami', 's malinami',
    's bananem', 's banany', 's mrkvi', 's rajcaty', 's okurkami',
    'se zeleninou', 's ovocem', 'obsahuje ovoce',
)
_FRESH_IDENTITIES = {
    'W037': r'\bavokad(?:o|a|u|e|y)?\b',
    'W038': r'\bbanan(?:y|u|a|em)?\b',
    'W039': r'\bboruvk(?:y|a|u|ami|ou)?\b',
    'W040': r'\bmalin(?:y|a|u|ami|ou)?\b',
    'W041': r'\bcitron(?:y|u|em|a)?\b',
    'W042': r'\b(?:hroznov[eay] vino|hrozny|hroznu)\b',
    'W043': r'\bokurk(?:a|y|u|ou|ove|ovy)?\b',
    'W044': r'\brajcat(?:a|o|u|y|um)?\b',
    'W045': r'\b(?:cherry|koktejlova|mini)\s+rajcat(?:a|o|u|y|um)?\b',
    'W046': r'\b(?:mrkev|mrkve|mrkvi|mrkvick\w*|karotk\w*)\b',
    'W047': r'\bpaprik(?:a|y|u|ou|am|ach)?\b',
}

def is_fresh_produce_name(name: str, rule: dict) -> bool:
    n = folded(name)
    if not n or rule.get('id') not in _FRESH_IDENTITIES:
        return False
    if any(re.search(r'(?<!\w)' + re.escape(stem) + r'\w*', n)
           for stem in _FRESH_REJECT_STEMS):
        return False
    if any(phrase in n for phrase in _FRESH_REJECT_PHRASES):
        return False
    # Fruit/vegetable should appear as the product near the start of the title,
    # not in an ingredient listing or a long multiproduct description.
    m = re.search(_FRESH_IDENTITIES[rule['id']], n)
    return bool(m and len(n[:m.start()].split()) <= 4)

def rule_matches(name: str, rule: dict) -> bool:
    """Accept only explicitly specified goods; exclude flavored derivatives."""
    n = folded(name)
    if not n:
        return False
    brands = rule.get('brand_aliases', [])
    if brands and not any(has_expression(n, b) for b in brands):
        return False
    any_terms = rule.get('product_any', [])
    if any_terms and not any(has_expression(n, term) for term in any_terms):
        return False
    if any(has_expression(n, term) for term in rule.get('exclude_any', [])):
        return False
    rid = rule.get('id')
    if rule.get('required_product_state') == 'syrove_cerstve_maso':
        if any(has_expression(n, x) for x in ('uzené', 'vařené', 'pečené', 'grilované', 'sušené', 'konzerva', 'krmivo', 'marinované', 'hotové jídlo')):
            return False
    if rule.get('required_product_state') in ('cerstve_ovoce', 'cerstva_zelenina'):
        if any(has_expression(n, x) for x in ('sušené', 'mražené', 'šťáva', 'sirup', 'ochucený', 'nápoj', 'čaj', 'bonbony', 'chipsy', 'olej')):
            return False
    # Produce name is only a candidate; shop taxonomy is checked after detail fetch.
    if rid in ('W033', 'W034', 'W035', 'W036'):
        # A title alone cannot establish PET unless explicitly marked. Product
        # discovery may include the item, but mark pack confirmation pending.
        if not re.search(r'\b1[\s,.]?5\s*l\b', n) and rid != 'W036':
            return False
        if rid == 'W036':
            if not re.search(r'\b(?:1(?:[\s,.]5)?|2(?:[\s,.]0)?)\s*l\b', n):
                return False
            if any(has_expression(n, x) for x in ('zero','light','bez cukru','diet','vanilla','cherry')):
                return False
    if rid == 'W053':
        return any(has_expression(n,x) for x in ('toaletní papír','toaletní role','papírové ubrousky','ubrousky')) and not any(has_expression(n,x) for x in ('kuchyňské','vlhčené','kapesníky'))
    if rid == 'W050' and has_expression(n,'bez kokosu'):
        return False
    if rid == 'W052':
        return any(has_expression(n,x) for x in ('těstoviny','špagety','penne','fusilli','farfalle','kolínka','rýže','spaghetti','linguine','lasagne','vrtule'))
    if rid == 'W073':
        return all(has_expression(n,x) for x in ('zewa','deluxe','kapesníky','standard')) and not any(has_expression(n,x) for x in ('box','krabice','family'))
    if rid == 'W074':
        return any(has_expression(n,x) for x in ('kuchyňské utěrky','papírové utěrky','kuchyňské role','papírové role')) and not any(has_expression(n,x) for x in ('vlhčené','textilní','hadříky','vlhké'))
    if rid == 'W075':
        return (any(has_expression(n,x) for x in ('kapesníky','kapesniky')) and
                ((any(has_expression(n,x) for x in ('box','krabice','krabička')) and any(has_expression(n,x) for x in ('3vrstvé','3 vrstv')))
                 or (has_expression(n,'zewa deluxe family') and not has_expression(n,'balíčky'))))
    return True


def matching_rules(name: str, rules: list[dict]) -> list[str]:
    return [r['id'] for r in rules if rule_matches(name,r)]


def normal_product_link(store: str, link: str) -> str | None:
    try:
        u = urlparse(link)
        if u.scheme != 'https' or u.hostname not in ('www.rohlik.cz','rohlik.cz','www.kosik.cz','kosik.cz'):
            return None
        if ('rohlik' in u.hostname) != (store == 'Rohlík'):
            return None
        if not URL_RE[store].fullmatch(u.path):
            return None
        return f'https://{u.hostname}{u.path}'.rstrip('/')
    except (TypeError, ValueError):
        return None


def image_url(image: str) -> str | None:
    if not isinstance(image, str):
        return None
    u = urlparse(image)
    if u.scheme != 'https' or not u.hostname or u.username or u.password:
        return None
    # Avoid tracking URLs supplied by unrelated sites; no guessed thumbnails.
    if not any(host in u.hostname.casefold() for host in ('rohlik','kosik','cdn','cloudfront','imgix')):
        return None
    return image[:1100]


def verified_packaging(name: str, ids: list[str]) -> bool | None:
    if not any(x in ids for x in ('W033','W034','W035','W036')):
        return None
    return bool(re.search(r'(?i)\bpet\b|plastov[áé]\s+l[áa]hev', name))


def unique_matches(search_rows: list[dict], store: str, rules: list[dict]) -> list[dict]:
    """Pure filter for offline UAT, never infer price from result card."""
    out={}
    for card in search_rows:
        name=(card.get('name') or '').strip()
        matched=matching_rules(name,rules)
        url=normal_product_link(store,card.get('url',''))
        if not matched or not url:
            continue
        out[url]={'store':store,'name':name,'url':url,'rule_ids':matched,
                  'image_url':image_url(card.get('image_url','')),
                  'package_verified':verified_packaging(name,matched)}
    return list(out.values())


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    tmp.replace(path)


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return default


def progress_overview(jobs: list[dict], done: set[str], query_status: dict) -> dict:
    all_by=Counter(job['shop'] for job in jobs)
    done_by=Counter(j['shop'] for j in jobs if job_key(j) in done)
    return {'total_jobs':len(jobs), 'finished_jobs':len(done),
            'by_store': {k: {'finished':done_by.get(k,0),'planned':v} for k,v in all_by.items()},
            'status_counts':dict(Counter(v.get('status','?') for v in query_status.values()))}


def acceptance(state: dict) -> tuple[bool,str]:
    """Report catalogue success only with real search and >=1 price per shop."""
    statuses=state.get('queries', {})
    found=state.get('discovered_in_cycle', {})
    fresh=state.get('fresh_verified_by_store', {})
    expected=state.get('planned_jobs',len(statuses))
    if len(state.get('completed',statuses)) < expected:
        return False,f'Neúplný průchod: {len(state.get("completed",statuses))}/{expected} vyhledávacích úloh; pokračování ze checkpointu'
    if any(q.get('status') == 'partial_limit' for q in statuses.values()):
        return False,'Některé výsledky vyhledávání byly zkráceny limitem stránek/karet'
    if not any(q.get('status') == 'ok' and q.get('links',0)>0 for q in statuses.values()):
        return False,'Ani jeden dotaz zatím nevrátil produkty z veřejného vyhledávání'
    if any(not found.get(shop) for shop in ('Rohlík','Košík')):
        return False,'Chybí objevené produkty z jednoho obchodu'
    if any(fresh.get(shop,0) <= 0 for shop in ('Rohlík','Košík')):
        return False,'Chybí ověřená cena nalezeného produktu z jednoho obchodu'
    return True,'Vyhledávání a ověřování funguje u obou obchodů; katalog může být částečný'


def main() -> int:
    from playwright.sync_api import sync_playwright
    cfg=load(CONFIG,{})
    rules=cfg.get('watch_rules',[])
    if not rules or len({r['id'] for r in rules}) != len(rules):
        raise ValueError('Chybí sledovací pravidla nebo jsou duplicitní ID')
    search_cfg={'max_cards_per_query':400,'scrolls_per_query':10}
    cfg_search={**cfg,'catalog_search':search_cfg}
    jobs=plan_jobs(cfg_search)
    sig=scan_plan_signature(jobs)
    state=load(DATA/'catalog_progress.json',{})
    if state.get('plan_signature') != sig:
        state={'plan_signature':sig,'completed':[],'queries':{},'discovered_in_cycle':{},'fresh_verified_by_store':{},'cycle':int(state.get('cycle',0))+1}
    state['planned_jobs']=len(jobs)
    done=set(state.get('completed',[]))
    if len(done)>=len(jobs):
        # A new fresh scan starts only after the previous full cycle completed.
        state={'plan_signature':sig,'completed':[],'queries':{},'discovered_in_cycle':{},'fresh_verified_by_store':{},'cycle':state.get('cycle',1)+1}
        done=set()
    state['planned_jobs']=len(jobs)
    current=load(DATA/'catalog_latest.json',{})
    pending=load(DATA/'catalog_taxonomy_review.json',{}).get('items',[])
    # Include quarantined records so each new cycle may recheck their retailer taxonomy.
    all_saved=[*current.get('items',[]), *pending]
    items={x['store']+'|'+x['url']:x for x in all_saved if isinstance(x,dict) and x.get('url') and x.get('store')}
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    started=time.monotonic()
    deadline=started+43*60
    blocked=set()
    processed=0
    detail_checked=0
    search_failures={shop:0 for shop in BASE}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        search_pages={shop:browser.new_page(locale='cs-CZ',timezone_id='Europe/Prague',viewport={'width':1366,'height':900}) for shop in BASE}
        detail_pages={shop:browser.new_page(locale='cs-CZ',timezone_id='Europe/Prague',viewport={'width':1366,'height':900}) for shop in BASE}
        try:
            for job in jobs:
                key=job_key(job)
                if key in done:continue
                if time.monotonic() > deadline:break
                shop=job['shop']
                if shop in blocked:continue
                try:
                    rows,status,note=scan_single_query(search_pages[shop],BASE[shop],job['query'],max_cards=400,scrolls=10)
                except Exception as exc:
                    rows,status,note=[],'error',f'{type(exc).__name__}: {str(exc)[:160]}'
                matches=unique_matches(rows,shop,rules)
                state['queries'][key]={'query':job['query'],'shop':shop,'status':status,'links':len(rows),
                                       'matched':len(matches),'note':note[:320]}
                processed+=1
                print(f'[{len(done)+1}/{len(jobs)}] {shop} {job["query"]}: {status}; cards={len(rows)} matches={len(matches)}', flush=True)
                if status in ('blocked','rate_limited','search_unavailable'):
                    blocked.add(shop)
                    print('SHOP UNAVAILABLE '+shop+': '+note[:300],flush=True)
                elif status in ('search_unconfirmed','error'):
                    search_failures[shop]+=1
                    if search_failures[shop]>=2:
                        blocked.add(shop)
                        print('SHOP SEARCH UNCONFIRMED '+shop+': '+note[:300],flush=True)
                else:
                    search_failures[shop]=0
                if status in ('ok','no_cards','partial_limit'):
                    for product in matches:
                        if time.monotonic() > deadline:break
                        k=shop+'|'+product['url']
                        existing=items.get(k)
                        if existing and existing.get('cycle')==state['cycle']:
                            existing['rule_ids']=sorted(set(existing.get('rule_ids',[])) | set(product['rule_ids']))
                            continue
                        # Verify product-level title and actual price using the successful 10/10 pilot scanner.
                        at=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
                        row=inspect(detail_pages[shop],{'id':product['url'],'store':shop,
                            'label':product['name'],'url':product['url']},at)
                        detail_checked+=1
                        # taxonomy-v21: context from retailer product page, after inspect() has navigated.
                        from store_taxonomy import extract_shop_context
                        if row.get('http_status') == 200 and row.get('status') != 'title_mismatch':
                            shop_context=extract_shop_context(detail_pages[shop])
                        else:
                            shop_context={'store_category_path':[],'category_source':'missing',
                                          'product_description':''}
                        multibuy=[]
                        if shop=='Košík' and row['status']=='ok':
                            try:
                                from monitor import browser_extract
                                detail=browser_extract(detail_pages[shop]).get('detail_text','')
                                for val,qty in re.findall(r'(\d{1,4}[,.]\d{2})\s*Kč\s*od\s*(\d+)\s*ks',detail,flags=re.I):
                                    multibuy.append({'min_qty':int(qty),'price_czk':float(val.replace(',','.'))})
                            except Exception:
                                pass
                        state.setdefault('discovered_in_cycle',{})[shop]=state.get('discovered_in_cycle',{}).get(shop,0)+1
                        if row['status']=='ok':
                            state.setdefault('fresh_verified_by_store',{})[shop]=state.get('fresh_verified_by_store',{}).get(shop,0)+1
                        items[k]={**product, **shop_context, 'taxonomy_checked_at':at, 'cycle':state['cycle'],
                                  'title':row.get('title') or product['name'],
                                  'price_czk':row.get('price_czk'),
                                  'price_status':row['status'],'price_source':row.get('source'),
                                  'checked_at':at,'note':row.get('note',''), 'multibuy':multibuy,
                                  'http_status':row.get('http_status'),
                                  'postcode_verified':False}
                    done.add(key)
                state['completed']=sorted(done)
                if processed % 5 == 0 or time.monotonic() > deadline:
                    snapshot(state,items,jobs,now)
                time.sleep(0.3)
        finally:
            browser.close()
    snapshot(state,items,jobs,now)
    good,reason=acceptance(state)
    print('CATALOGUE RESULT', 'PASS' if good else 'UNVERIFIED',reason)
    print('QUERIES',len(done),'/',len(jobs),'UNIQUE PRODUCTS',len(items),'DETAILS THIS RUN',detail_checked)
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as f:
            f.write(f'## Rohlík × Košík v20: katalogový sběr\n\n')
            f.write(f'**{len(done)}/{len(jobs)} dotazů** v současném cyklu; **{len(items)} různých výrobků**, kontrolovaných detailů v tomto běhu: {detail_checked}.\n\n')
            f.write('| Obchod | Objeveno v cyklu | Ověřené ceny v cyklu |\n|---|---:|---:|\n')
            for shop in BASE:
                f.write(f'| {shop} | {state.get("discovered_in_cycle",{}).get(shop,0)} | {state.get("fresh_verified_by_store",{}).get(shop,0)} |\n')
            f.write(f'\n**Stav:** {"Ověřený dílčí sběr" if good else "Neověřený sběr"} – {reason}. Úplnost katalogu ani ceny pro PSČ 149 00 nelze potvrdit.\n')
    # An incomplete but correctly running scan is distinct from a failed source.
    return 0 if good else 2


def snapshot(state: dict,items: dict,jobs: list[dict],now: str) -> None:
    overview=progress_overview(jobs,set(state.get('completed',[])),state.get('queries',{}))
    all_items=sorted(items.values(),key=lambda x:(x['store'],x['name'].casefold()))
    rules_by_id = {r['id']:r for r in load(CONFIG,{}).get('watch_rules',[])}
    cleaned_items = []
    for row in all_items:
        ids = [rid for rid in row.get('rule_ids', [])
               if rid in rules_by_id and rule_matches(row.get('name',''), rules_by_id[rid])
               and (rules_by_id[rid].get('required_product_state') not in
                    ('cerstve_ovoce','cerstva_zelenina')
                    or not row.get('title')
                    or rule_matches(row['title'], rules_by_id[rid]))]
        if ids:
            row['rule_ids'] = ids
            cleaned_items.append(row)
    all_items = cleaned_items
    # Category MUST come from retailer detail, not the search phrase.
    from store_taxonomy import partition_items
    all_items, needs_review=partition_items(all_items)
    dump(DATA/'catalog_taxonomy_review.json', {
        'schema':'rk-v21-taxonomy-review-1',
        'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'count':len(needs_review), 'items':needs_review})

    verified_current=sum(x.get('price_status')=='ok' and x.get('cycle')==state.get('cycle') for x in all_items)
    latest={'schema':'rk-v20-catalog-1','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),'postcode':'149 00',
            'postcode_verified':False,'complete':False,
            'note':'Výsledky veřejného vyhledávání, nikoli garantovaná úplnost sortimentu. Neověřené položky nejsou slevy.',
            'rules_total':len(load(CONFIG,{}).get('watch_rules',[])),'rules':[{'id':r['id'],'label':r['label'],'category':r['category']} for r in load(CONFIG,{}).get('watch_rules',[])], 'category_order':list(FOOD_CATEGORY_ORDER), 'rules_seen':len(set(id for it in all_items if it.get('cycle')==state.get('cycle') for id in it.get('rule_ids',[]))), 'coverage':overview,'discovered_total':len(all_items),
            'verified_current_cycle':verified_current,'items':all_items}
    dump(DATA/'catalog_latest.json',latest)
    dump(DATA/'catalog_progress.json',state)


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('CATALOGUE FATAL:',type(exc).__name__,str(exc)[:350],file=sys.stderr)
        sys.exit(2)
