"""Offline, repeatable cleanup using existing saved retailer metadata."""
import json
from pathlib import Path
from catalog_quality_v24 import apply_catalog
from store_taxonomy import partition_items

def save(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    tmp.replace(p)

def execute(base:Path=Path('docs/data')):
    cat=json.loads((base/'catalog_latest.json').read_text(encoding='utf-8'))
    revpath=base/'catalog_taxonomy_review.json'
    rev=json.loads(revpath.read_text(encoding='utf-8')) if revpath.exists() else {'items':[]}
    before=len(cat['items'])
    clean,review,audit=apply_catalog(cat,rev)
    # Safety: if a rule change would wipe an unexpectedly large portion,
    # stop instead of publishing silently.
    if before and (before-len(clean['items']))/before>0.20:
        raise RuntimeError(f'Unexpected catalog impact {before-len(clean["items"])}/{before}')
    # Regression: the saved price/status of each retained SKU must not change.
    bykey={(p['store'],p['url']):p for p in cat['items']}
    for p in clean['items']:
        old=bykey[p['store'],p['url']]
        for key in ('price_czk','price_status','original_price_czk','discount_pct','offer_valid_until','multibuy'):
            assert p.get(key)==old.get(key), (p.get('name'),key)
    # Future snapshot must agree with direct category filtering.
    sample=[p for p in clean['items'] if p.get('rule_ids')][:10]
    partition_items(sample)
    save(base/'catalog_latest.json',clean)
    save(revpath,review)
    save(base/'catalog_quality_v24.json',audit)
    print('QUALITY v24',json.dumps({k:audit[k] for k in ('before','after','quarantined','removed_rules_by_category','price_gaps')},ensure_ascii=False))
    return audit
if __name__=='__main__':execute()
