"""v20 catalogue search helpers for Rohlík and Košík.

Finds products via the PUBLIC site search box across categories, irrespective
of whether the product is on sale. No private APIs, authentication, captcha
bypass, or claim that a retailer's entire catalogue was enumerated.

The planned queries cover every configured shopping rule at both stores. The scan attempts the entire dynamic plan on each run when allowed by
source availability and time budget; an incomplete run resumes from its
first unfinished query for each shop. Last observed prices are timestamped. A query returning zero rows is not a proof of absence.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

QUERY_BY_RULE = {
    'W001': ['kuřecí prsní řízky', 'kuřecí prsa'],
    'W002': ['kuřecí stehna', 'kuřecí paličky'],
    'W003': ['vepřová krkovice'],
    'W004': ['vepřová panenka'],
    'W005': ['hovězí svíčková'],
    'W037': ['avokádo'], 'W038': ['banány'],
    'W039': ['borůvky'], 'W040': ['maliny'],
    'W041': ['citrony'], 'W042': ['hroznové víno', 'hrozny'],
    'W043': ['okurky'], 'W044': ['rajčata'],
    'W045': ['cherry rajčata'], 'W046': ['mrkev'],
    'W047': ['papriky'], 'W051': ['ORION KOKO kokosová tyčinka'],
    'W053': ['Zewa toaletní papír', 'Zewa ubrousky'],
    'W074': ['kuchyňské papírové utěrky', 'papírové utěrky'],
    'W075': ['kapesníky box 3vrstvé', 'kapesníky v krabici'],
}
# Supplemental searches limit the risk of a brand-only query being truncated
# before the relevant type (e.g. other cosmetics from AXE / another Zewa line).
EXTRA_BRAND_TERMS = {
    'W006': ['LE CO šunka'], 'W027': ['Hellmann majonéza'],
    'W019': ['President plátkový sýr'],
    'W020': ['Smetanito'], 'W022': ['Lipno tavený sýr'],
    'W023': ['Král sýrů hermelín'],
    'W026': ['Galbani mozzarella'],
    'W028': ['Madeta máslo'],
    'W033': ['Aquila 1,5 l'], 'W034': ['Rajec 1,5 l'],
    'W035': ['Dobrá voda 1,5 l'],
    'W036': ['Coca-Cola Original 1,5 l', 'Coca-Cola Original 2 l'],
    'W052': ['Panzani těstoviny', 'Panzani rýže'],
    'W055': ['Axe deodorant', 'Axe sprchový gel'],
    'W056': ['Syoss Men Intense Power'],
    'W060': ['Wilkinson jednorázová holítka'],
    'W072': ['Jar citron'], 'W073': ['Zewa Deluxe Standard kapesníky'],
    'W074': ['Zewa papírové utěrky'],
    'W075': ['Zewa kapesníky box', 'papírové kapesníky box'],
}


def plan_queries(config: dict) -> list[dict]:
    """One search term may cover multiple rules; EVERY rule is represented."""
    dedup: dict[str, dict] = {}
    for rule in config.get('watch_rules', []):
        if rule.get('enabled') is False:
            continue
        rid = rule['id']
        queries = config.get('catalog_search',{}).get('queries_by_rule',{}).get(rid,QUERY_BY_RULE.get(rid))
        if queries is None:
            aliases = rule.get('brand_aliases', [])
            queries = [aliases[0]] if aliases else [rule['label']]
        queries = [*queries, *EXTRA_BRAND_TERMS.get(rid, [])]
        for term in queries:
            term = re.sub(r'\s+', ' ', term).strip()
            if not term:
                continue
            key = term.casefold()
            entry = dedup.setdefault(key, {'query': term, 'rule_ids': []})
            if rid not in entry['rule_ids']:
                entry['rule_ids'].append(rid)
    return list(dedup.values())


# Sort by ACTUAL shopping category, not by the user's historical insertion order.
# The user wants all selected foods first, then drinks, then non-food goods.
# Query terms shared between rules inherit the highest-ranking linked category.
SCAN_PLAN_VERSION = 'food-first-resume-partial-19.4'
FOOD_CATEGORY_ORDER = (
    'Maso',
    'Uzeniny / šunky', 'Uzeniny / salámy', 'Uzeniny / párky a klobásy',
    'Sýry / plátkové', 'Sýry / tavené', 'Sýry / plísňové',
    'Sýry / mozzarella a salátové',
    'Majonézy', 'Másla a tuky',
    'Ovoce', 'Zelenina', 'Sladké', 'Těstoviny a rýže',
    'Nápoje / vody', 'Nápoje / limonády',
    'Kapesníky / balíčky', 'Kapesníky / krabice',
    'Papírové utěrky', 'Papír a hygiena',
    'Kosmetika', 'Dentální hygiena', 'Holení',
    'Praní', 'Úklid',
)
RANK_BY_CATEGORY = {name: index for index, name in enumerate(FOOD_CATEGORY_ORDER)}


def balanced_queries(config: dict) -> list[dict]:
    """All distinct terms; complete FOOD -> DRINKS -> HYGIENE -> CLEANING order.

    Legacy function name retained for compatibility with existing imports/tests.
    A single term shared across several rules keeps all rule IDs and is sorted
    by its most important category. No terms are dropped or repeated.
    """
    queries = plan_queries(config)
    by_id = {rule['id']: rule for rule in config.get('watch_rules', [])}

    def rank(query: dict) -> int:
        ranks = [RANK_BY_CATEGORY.get(by_id.get(rid, {}).get('category'), 999)
                 for rid in query['rule_ids']]
        return min(ranks, default=999)

    # Python stable sort keeps the natural rule/query order within each category.
    return sorted(queries, key=rank)


def plan_jobs(config: dict) -> list[dict]:
    """Search every term in both shops, pairing stores within each batch."""
    stores = tuple(config.get('shops', ['Rohlík', 'Košík']))
    return [{'shop': shop, **plan} for plan in balanced_queries(config) for shop in stores]


def job_key(job: dict) -> str:
    return f"{job['shop']}::{job['query'].casefold()}"


def choose_batch(jobs: list[dict], cursor: int, limit: int) -> tuple[list[dict], int]:
    if not jobs:
        return [], 0
    n = len(jobs)
    count = min(max(1, limit), n)
    chosen = [jobs[(cursor + i) % n] for i in range(count)]
    return chosen, (cursor + count) % n


# Checkpoints are per shop so one retailer rate-limiting access does not
# prevent the other retailer from progressing through the watch list.
# A new rule or a changed scan order invalidates the old checkpoint.
def scan_plan_signature(jobs: list[dict]) -> str:
    import hashlib
    return hashlib.sha256('\n'.join(job_key(j) for j in jobs).encode('utf-8')).hexdigest()[:20]


def resume_plan(jobs: list[dict], state: dict) -> tuple[list[dict], dict]:
    """Return uncompleted jobs while retaining food-first order where possible."""
    sig=scan_plan_signature(jobs)
    progress=state.get('scan_progress', {}) if state.get('scan_plan_signature')==sig else {}
    shops=list(dict.fromkeys(j['shop'] for j in jobs))
    counts={shop:sum(j['shop']==shop for j in jobs) for shop in shops}
    offsets={shop:min(max(0,int(progress.get(shop,0))),counts[shop]) for shop in shops}
    # A shop reaching the end of its cycle begins again on the next run,
    # even if the other shop was unavailable.
    offsets={shop:(0 if offsets[shop]>=counts[shop] else offsets[shop]) for shop in shops}
    idx={shop:0 for shop in shops}
    selected=[]
    for j in jobs:
        shop=j['shop']; pos=idx[shop];idx[shop]+=1
        if pos>=offsets[shop]: selected.append(j)
    return selected, offsets


def advance_scan_progress(jobs: list[dict], batch: list[dict], results: dict,
                          starting: dict) -> dict:
    """Advance through contiguous completed queries; retry blocked/timeouts."""
    completed={'ok','no_cards','partial_limit'}
    progress=dict(starting)
    shops=list(dict.fromkeys(j['shop'] for j in jobs))
    per_shop={shop:[j for j in jobs if j['shop']==shop] for shop in shops}
    submitted={job_key(j) for j in batch}
    for shop, ordered in per_shop.items():
        pos=progress.get(shop,0)
        while pos<len(ordered):
            k=job_key(ordered[pos])
            if k not in submitted or results.get(k,{}).get('status') not in completed:
                break
            pos+=1
        progress[shop]=pos
    return progress


# Executed against product cards in the *search results* — not the promotions
# page. A nearest-price-card check prevents grabbing neighbouring products.
SEARCH_EXTRACT_JS = r"""() => {
 const shop=location.hostname.includes('rohlik')?'Rohlík':'Košík';
 const pattern=shop==='Rohlík'?/^\/\d{5,}(?:-[\w-]+)?\/?$/i:/^\/p\d+(?:-[\w-]+)?\/?$/i;
 const nodes=[...document.querySelectorAll('a[href]')];
 const output=new Map();
 for(const a of nodes){
   let u;try{u=new URL(a.href)}catch(_){continue}
   if(u.hostname!==location.hostname||!pattern.test(u.pathname))continue;
   let card=null;
   for(let e=a,level=0;e&&level<7;e=e.parentElement,level++){
     const t=(e.innerText||'').trim();
     const links=[...e.querySelectorAll('a[href]')].filter(x=>{
       try{return pattern.test(new URL(x.href).pathname)}catch(_){return false}
     });
     const different=new Set(links.map(x=>new URL(x.href).pathname));
     if(different.size>1)continue;
     if(t.length>=6&&t.length<1100&&(/\d+[,. ]\d{2}\s*(?:Kč|CZK)/i.test(t)||/[-−]\s*\d{1,2}\s*%/.test(t))){card=e;break;}
   }
   if(!card)continue;
   const img=a.querySelector('img')||(card.querySelectorAll('a[href]').length<=2?card.querySelector('img'):null);
   const titleCandidates=[img?.alt,a.getAttribute('title'),a.getAttribute('aria-label'),a.innerText];
   let name=(titleCandidates.find(x=>x&&x.trim().length>=4&&x.trim().length<=185&&!/Kč|kusů v košíku|[-−]\s*\d{1,2}\s*%/i.test(x))||'').trim();
   name=name.replace(/^(?:zobrazit|otevřít)\s+detail\s+produktu\s*/i,'').trim();
   if(!name)continue;
   const price=card.querySelector('[data-testid*="price"], [class*="currentPrice"], [class*="salePrice"], [class*="Price_current"]');
   const old=card.querySelector('del, s, [class*="oldPrice"], [class*="originalPrice"]');
   const photo=img?.currentSrc||img?.getAttribute('data-src')||img?.getAttribute('src')||'';
   const item={url:u.href,name,card:(card.innerText||'').trim().slice(0,950),
       current_price:(price?.innerText||'').trim().slice(0,100),
       old_price:(old?.innerText||'').trim().slice(0,100),image_url:photo};
   const prev=output.get(u.pathname);
   if(!prev||(!prev.current_price&&item.current_price))output.set(u.pathname,item);
 }
 return [...output.values()];
}"""


def _get_search_field(page):
    """Wait for site JS to render the *visible* public search input."""
    import time
    selectors = (
        'input[type="search"]', 'input[role="searchbox"]',
        'input[placeholder*="hledat" i]', 'input[placeholder*="hledejte" i]',
        'input[aria-label*="hledat" i]', 'input[aria-label*="hledejte" i]',
        'input[name*="search" i]', 'input[id*="search" i]',
    )
    for pass_no in range(5):
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if loc.count() and loc.is_visible(): return loc
            except Exception:pass
        # Some storefronts mount the search input only when the search icon is opened.
        if pass_no == 1:
            for sel in ('button[aria-label*="hledat" i]', '[role="button"][aria-label*="hledat" i]'):
                try:
                    loc=page.locator(sel).first
                    if loc.count() and loc.is_visible():loc.click(timeout=1200);break
                except Exception:pass
        if pass_no < 4: page.wait_for_timeout(1200)
    return None


def public_search_diagnostic(page) -> str:
    """Only non-sensitive DOM metadata (no input values, cookies, browser storage)."""
    try:
        record=page.evaluate('''() => ({title:document.title.slice(0,70),
          inputs:[...document.querySelectorAll('input')].slice(0,9).map(e=>({
           type:e.type, placeholder:(e.getAttribute('placeholder')||'').slice(0,80),
           aria:(e.getAttribute('aria-label')||'').slice(0,80), visible:!!e.getClientRects().length})),
          buttons:[...document.querySelectorAll('button')].slice(0,12).map(e=>({
            aria:(e.getAttribute('aria-label')||'').slice(0,40),
            text:(e.innerText||'').trim().slice(0,32)}))})''')
        return json.dumps(record,ensure_ascii=False)[:1000]
    except Exception as e:
        return f'DOM diagnostic unavailable: {type(e).__name__}'


def scan_single_query(page, base_url: str, query: str, *, max_cards: int = 300,
                      scrolls: int = 8) -> tuple[list[dict], str, str]:
    """Run visible store search; don't invent a URL or silently accept homepage cards."""
    try:
        landing=page.goto(base_url, wait_until='domcontentloaded', timeout=16000)
        if landing and landing.status in (403, 429):
            return [], 'rate_limited' if landing.status==429 else 'blocked', f'HTTP {landing.status}'
        if landing and landing.status >= 400:
            return [], 'error', f'Úvodní stránka HTTP {landing.status}'
        field = _get_search_field(page)
        if field is None:
            return [], 'search_unavailable', 'Nenalezeno veřejné vyhledávací pole; ' + public_search_diagnostic(page)
        field.fill(query, timeout=4000)
        field.press('Enter', timeout=4000)
        page.wait_for_timeout(950)
        now_url = page.url
        # Search on some sites stays in the same route with an inline result pane;
        # do not assume those are actual search results without clear evidence.
        if now_url.rstrip('/') == base_url.rstrip('/'):
            value = (field.input_value() or '').strip()
            if value.casefold() != query.casefold():
                return [], 'search_unconfirmed', 'Vyhledávání nepotvrdilo zadaný dotaz'
            # Inline search results need a dedicated semantic results container.
            if not page.locator('[role="listbox"], [data-testid*="search-result"], [class*="search-result"]').count():
                return [], 'search_unconfirmed', 'Enter nepřešel na výsledky; nelze použít domácí nabídku'
        found = {}
        stagnant=0
        last_count=-1
        for _ in range(max(1,scrolls)):
            for row in page.evaluate(SEARCH_EXTRACT_JS):
                found[row['url']]=row
            if len(found)>=max_cards:
                return list(found.values())[:max_cards], 'partial_limit', f'Dosažen limit {max_cards} produktů'
            stagnant = (stagnant+1) if len(found)==last_count else 0
            last_count=len(found)
            if stagnant>=3:break
            clicked=False
            for selector in ('button:has-text("Načíst další")', 'button:has-text("Zobrazit další")'):
                try:
                    btn=page.locator(selector).first
                    if btn.count() and btn.is_visible():
                        btn.click(timeout=1300);clicked=True;break
                except Exception:
                    pass
            if not clicked:page.evaluate('window.scrollBy(0, Math.max(1000, innerHeight * 1.5))')
            page.wait_for_timeout(330)
        # Empty result is distinguishable from errors but NOT proof a product doesn't exist.
        return list(found.values()), 'ok' if found else 'no_cards', 'Veřejné výsledky vyhledávání; úplnost neověřena'
    except Exception as exc:
        msg=f'{type(exc).__name__}: {str(exc)[:160]}'
        if '429' in msg:return [], 'rate_limited', msg
        return [], 'error', msg


def playwright_search_batch(batch: list[dict], cfg: dict) -> dict[str, dict]:
    """One reusable browser; no logins, captcha circumvention or internal API."""
    from playwright.sync_api import sync_playwright
    results={}
    search_cfg=cfg.get('catalog_search', {})
    # Per-run time budget prevents abrupt GitHub job timeout and allows
    # publishing partial coverage with an honest status, never false zero sales.
    deadline=time.monotonic()+60*float(search_cfg.get('max_scan_minutes',42))
    pause_seconds=max(0,float(search_cfg.get('pause_between_queries_seconds',0.4)))
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        pages={}
        blocked={}  # obchod -> přesný důvod blokace (rate_limited / blocked / search_unavailable)
        unavailable_count={}
        try:
            for job in batch:
                key=job_key(job);shop=job['shop']
                if time.monotonic() >= deadline:
                    results[key]={'status':'skipped_time_budget','items':[],
                                  'detail':'Vyhledávání zastaveno kvůli časovému limitu jednoho běhu'}
                    continue
                if shop in blocked:
                    reason=blocked[shop]
                    status='skipped_rate_limit' if reason=='rate_limited' else 'skipped_search_unavailable'
                    results[key]={'status':status,'items':[],
                                  'detail':'Další dotazy daného obchodu pozastaveny: '+reason}
                    continue
                if shop not in pages:
                    pages[shop]=browser.new_page(locale='cs-CZ',timezone_id='Europe/Prague',
                                                 viewport={'width':1366,'height':950})
                url='https://www.rohlik.cz/' if shop=='Rohlík' else 'https://www.kosik.cz/'
                rows,status,desc=scan_single_query(pages[shop],url,job['query'],
                    max_cards=int(search_cfg.get('max_cards_per_query',400)),
                    scrolls=int(search_cfg.get('scrolls_per_query',12)))
                results[key]={'status':status,'items':rows,'detail':desc}
                if pause_seconds: time.sleep(pause_seconds)
                if status in ('rate_limited','blocked'):
                    blocked[shop]=status
                elif status=='search_unavailable':
                    unavailable_count[shop]=unavailable_count.get(shop,0)+1
                    if unavailable_count[shop]>=2:blocked[shop]=status
                else:unavailable_count[shop]=0
        finally:
            browser.close()
    return results


