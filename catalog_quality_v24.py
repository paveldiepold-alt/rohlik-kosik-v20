"""Cross-category retailer-taxonomy sanity gate for Rohlík/Košík.

Use the retailer's complete breadcrumb path when available. A section name at
its end does not override incompatible ancestors (e.g. seeds -> Zelenina).
If retailer taxonomy is absent, quarantine only high-confidence wrong types;
do not claim a retailer-verified classification. Never alter price evidence.
"""
from __future__ import annotations
import json, re, unicodedata
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parent
FOOD = {'Maso','Ovoce','Zelenina','Másla a tuky','Majonézy','Sladké','Těstoviny a rýže'}

def norm(v):
    s=unicodedata.normalize('NFKD',str(v or '')).casefold()
    return ' '.join(re.sub(r'[^a-z0-9]+',' ', ''.join(c for c in s if not unicodedata.combining(c))).split())

CATEGORY_BY_ID = {x['id']:x['category'] for x in json.loads((ROOT/'watchlist.json').read_text(encoding='utf-8')).get('watch_rules',[])} if (ROOT/'watchlist.json').exists() else {}

# These are product TYPE checks, not product-brand blacklists.
PET = re.compile(r'\b(?:cat|kitten|dog|puppy|koc(?:ka|ky|ky|ku|ek|ici|iciho)|kocky|psi|psy|psu|pamlsk\w*|krmiv\w*|granul\w*|steliv\w*|konzervy pro psy)\b')
PROCESSED_MEAT = re.compile(r'\b(?:pecen\w*|grilovan\w*|smazen\w*|uzen\w*|gyros|nugget\w*|hotov\w*|pokr\w*|sendvic\w*|salat\w*|marinovan\w*|susen\w*|snack\w*|kapsick\w*|miska)\b')
NOT_EDIBLE_FAT = re.compile(r'\b(?:vaginaln\w*|cipk\w*|pletov\w*|telov\w*|opalovan\w*|pena|sprej|sampon|serum|kapky|ocni|vitamin\w*|dopln\w*|tobol\w*|cps|chews|zele|kolagen\w*|toaletn\w*|papi\w*|ubrousk\w*|vonav\w*)\b')
NON_FOOD_PATH = re.compile(r'\b(?:osiva|osivo|semena|seminka|travni smesi|zahrada|zahradn\w*|balkon|pestovan\w*|sazenice|rostliny)\b')
PET_PATH = re.compile(r'\b(?:chovatel\w*|zvirat\w*|mazlic\w*|krmiv\w*|koc\w*|psu|psy)\b')
CARE_PATH = re.compile(r'\b(?:zdravi|lekarn\w*|dopl\w* stravy|kosmetika|pece o telo|pece o pokozku|hygiena|toaletni papir|domacnost|drogerie)\b')
PROCESSED_PATH = re.compile(r'\b(?:hotova jidla|sterilovan\w*|mrazene|polevk\w*|konzerv\w*|uzenin\w*|pecen\w*)\b')

def gate_catalog_item(item:dict, category_by_id:dict|None=None):
    """Return (retained item or None, review item or None) with per-rule decisions.
    Does not require every retailer to expose taxonomy, and does not invent it.
    """
    mapping=category_by_id if category_by_id is not None else CATEGORY_BY_ID
    raw_ids=list(item.get('rule_ids') or [])
    if not raw_ids:return dict(item),None
    path=item.get('store_category_path') or []
    full=norm(' > '.join(path)); title=norm(item.get('title') or item.get('name'))
    kept=[];removed=[]
    for rid in raw_ids:
        category=mapping.get(rid,'')
        reason=None
        if path:
            is_food=category in FOOD or category.startswith(('Sýry','Uzeniny','Nápoje'))
            if is_food and PET_PATH.search(full): reason='Prodejce: krmivo/chovatelske zbozi neni potravina'
            elif category in {'Zelenina','Ovoce'} and NON_FOOD_PATH.search(full):reason='Prodejce: pestovani a osiva nejsou cerstva zelenina/ovoce'
            elif category=='Maso' and PROCESSED_PATH.search(full):reason='Prodejce: zpracovany vyrobek neni syrove maso'
            elif category=='Másla a tuky' and CARE_PATH.search(full):reason='Prodejce: drogerie/zdravi neni jedly tuk'
        # Safety net for entries already gathered before retailer categories
        # were recorded. Keep positive matches; quarantine clear mismatches.
        if not reason and category=='Maso':
            if PET.search(title):reason='Nazev oznacuje potravu pro zvirata'
            elif PROCESSED_MEAT.search(title):reason='Zpracovany nebo hotovy pokrm, nikoli syrove maso'
        if not reason and category=='Másla a tuky':
            if NOT_EDIBLE_FAT.search(title):reason='Kosmetika, zdravotnicky nebo papirovy vyrobek neni jedly tuk'
            # Non-edible products mentioning Omega/Flora do not become food by brand.
            elif ('omega' in title.split() or 'flora' in title.split()) and not re.search(r'\b(?:tuk|maslo|margarin|rostlinny|gold|light|original|classic)\b',title):
                reason='Jen znacka/nazev bez potvrzeni, ze jde o jedly tuk'
        if reason:removed.append({'rule_id':rid,'category':category,'reason':reason})
        else:kept.append(rid)
    if not removed:return dict(item),None
    source=dict(item)
    source['rule_ids']=raw_ids
    source['v24_review']={'decisions':removed,'category_path':path}
    source['taxonomy_status']='review' if not kept else 'partial'
    if not kept:return None,source
    retained=dict(item)
    retained['rule_ids']=sorted(set(kept))
    retained['taxonomy_status']='partial'
    return retained,source


def apply_catalog(catalog:dict,review:dict):
    out=[];new_review=[];category_counts=Counter();reason_counts=Counter()
    for product in catalog['items']:
        kept,flagged=gate_catalog_item(product)
        if kept:out.append(kept)
        if flagged:
            new_review.append(flagged)
            for issue in flagged['v24_review']['decisions']:
                category_counts[issue['category']]+=1
                reason_counts[issue['reason']]+=1
    already=list(review.get('items') or [])
    unique={ (p.get('store'),p.get('url')):p for p in [*already,*new_review] if p.get('url') }
    newcat=dict(catalog)
    newcat['items']=out
    newcat['discovered_total']=len(out)
    newcat['rules_seen']=len({r for p in out for r in p.get('rule_ids',[])})
    newcat['verified_current_cycle']=sum(p.get('price_status')=='ok' for p in out)
    newcat['quality_v24']={'removed_from_public':len(catalog['items'])-len(out),
                          'review_records_added':len(new_review),'removed_rules_by_category':dict(category_counts),
                          'price_status_not_modified':True}
    newcat['note']=(newcat.get('note') or '')+' | Kontrola kategorii v24: '+str(len(catalog['items'])-len(out))+' vyrazenych zobrazeni; puvodni pozorovani zachovana.'
    flagged_this_run=list(new_review)
    new_review={'schema':'rk-v24-taxonomy-review','count':len(unique),'items':list(unique.values())}
    audit={'schema':'rk-v24-audit','before':len(catalog['items']),'after':len(out),
           'quarantined':len(catalog['items'])-len(out),'flagged':len(new_review['items']),
           'removed_rules_by_category':dict(category_counts),'reasons':dict(reason_counts),
           'samples':[{'name':p.get('name'),'category':p['v24_review']['decisions'][0]['category'],
                       'reason':p['v24_review']['decisions'][0]['reason']} for p in flagged_this_run[:45]],
           'price_gaps':{}}
    byrule={x['id']:x['category'] for x in newcat.get('rules',[])}
    for p in out:
        if 'Praní' in [byrule.get(x) for x in p.get('rule_ids',[])]:
            k=p.get('store','?')+'|'+p.get('price_status','?')
            audit['price_gaps'][k]=audit['price_gaps'].get(k,0)+1
    return newcat,new_review,audit
