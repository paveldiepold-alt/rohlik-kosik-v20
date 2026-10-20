"""One-time safe fix for fresh-produce rules and previously saved catalogue data."""
from __future__ import annotations
import ast
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
SRC = ROOT / 'catalog_monitor.py'
WATCH = ROOT / 'watchlist.json'
CATALOG = ROOT / 'docs/data/catalog_latest.json'
REJECTED = ROOT / 'docs/data/catalog_quality_excluded.json'

HELPER = r'''
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
'''

# Prevent repeated execution from duplicating code.
source = SRC.read_text(encoding='utf-8')
if 'def is_fresh_produce_name(' not in source:
    anchor = '\ndef rule_matches(name: str, rule: dict) -> bool:'
    assert source.count(anchor) == 1, 'Unexpected catalog_monitor.py structure (helper insertion)'
    source = source.replace(anchor, '\n' + HELPER + anchor, 1)
    target = "    if rid in ('W033', 'W034', 'W035', 'W036'):"
    guard = """    # Do not treat a product mentioning fruit/vegetables as fresh produce.
    if rule.get('required_product_state') in ('cerstve_ovoce', 'cerstva_zelenina'):
        if not is_fresh_produce_name(name, rule):
            return False
"""
    assert source.count(target) == 1, 'Unexpected catalog_monitor.py structure (guard insertion)'
    source = source.replace(target, guard + target, 1)
    # Revalidate every future snapshot, so stale entries cannot reappear.
    old = "    all_items=sorted(items.values(),key=lambda x:(x['store'],x['name'].casefold()))"
    replacement = old + """
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
"""
    assert source.count(old) == 1, 'Unexpected catalog_monitor.py structure (snapshot insertion)'
    source = source.replace(old, replacement, 1)
    ast.parse(source,filename=str(SRC))
    SRC.write_text(source,encoding='utf-8')

# Re-evaluate previously collected data *without any internet access or rescan*.
import importlib
import sys

sys.path.insert(0, str(ROOT.resolve()))
sys.modules.pop('catalog_monitor', None)
importlib.invalidate_caches()

from catalog_monitor import rule_matches

cfg = json.loads(WATCH.read_text(encoding='utf-8'))
by_id = {r['id']:r for r in cfg.get('watch_rules', [])}
data = json.loads(CATALOG.read_text(encoding='utf-8'))
original = data.get('items', [])
clean, excluded = [], []
changed_rules = 0
for orig in original:
    product = dict(orig)
    ids = list(product.get('rule_ids', []))
    kept = [rid for rid in ids
            if rid in by_id and rule_matches(product.get('name', ''), by_id[rid])
            and (by_id[rid].get('required_product_state') not in ('cerstve_ovoce','cerstva_zelenina')
                 or not product.get('title')
                 or rule_matches(product['title'],by_id[rid]))]
    if kept != ids:
        changed_rules += 1
    if kept:
        product['rule_ids'] = kept
        clean.append(product)
    else:
        product['quality_rejection_reason'] = 'Nevyhovuje pravidlům pro čerstvé ovoce/zeleninu nebo ostatním sledovacím pravidlům'
        excluded.append(product)

# Verified counts and rule coverage must reflect the corrected visible data.
data['items'] = clean
data['discovered_total'] = len(clean)
data['raw_discovered_total'] = len(original)
data['quality_excluded_total'] = len(excluded)
data['quality_changed_rule_matches'] = changed_rules
data['verified_current_cycle'] = sum(
    p.get('price_status') == 'ok' and p.get('cycle') == data.get('cycle',1)
    for p in clean
)
data['rules_seen'] = len({rid for p in clean for rid in p.get('rule_ids',[])})
# The progress checkpoint remains unchanged; 196/196 still represents completed searches.
data['note'] = (str(data.get('note','')).split(' | Korekce kategorií:')[0]
                + f' | Korekce kategorií: vyřazeno {len(excluded)} nesouvisejících výrobků;'
                + ' údaje z veřejného vyhledávání, nikoli garantované úplnosti sortimentu.')

now = datetime.now(timezone.utc).isoformat(timespec='seconds')
REJECTED.parent.mkdir(parents=True,exist_ok=True)
REJECTED.write_text(json.dumps({'generated_at':now,'count':len(excluded),'items':excluded},
                               ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
CATALOG.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Regression test fixtures mirroring the user-reported screenshot.
scenarios = [
    ('Aktimel Kids Banana split 8x100g','W038',False),
    ('Actimel Triple Action Borůvka - Ostružina','W039',False),
    ('Activia Kefír Borůvka','W039',False),
    ('AGIVA 2v1 Mycí houbička s mýdlem s vůní manga, kiwi a avokáda','W037',False),
    ('Agro Přírodní hnojivo pro rajčata a papriky 1,5 kg','W044',False),
    ('Agrola Zákys Borůvka','W039',False),
    ('Air Wick Vonné tyčinky - Růžový šek a maliny','W040',False),
    ('ALNATURA BIO Dětská výživa Hovězí, mrkev, brambory a brokolice','W046',False),
    ('ALNATURA BIO Rajčata sekaná','W044',False),
    ('ALNATURA BIO Borůvky neslazené','W039',False),
    ('Banány volné 1 kg','W038',True),
    ('BIO Borůvky čerstvé 125 g','W039',True),
    ('Rajčata cherry 250 g','W044',True),
    ('Čerstvá mrkev s natí svazek','W046',True),
    ('Paprika červená 1 ks','W047',True),
    ('Avokádo Hass kus','W037',True),
    ('Okurka hadovka 1 kus','W043',True),
    ('Maliny čerstvé 125g','W040',True),
    ('Citrony volné 500g','W041',True),
    ('Hroznové víno bílé 500g','W042',True),
]
for name,rid,expected in scenarios:
    actual=rule_matches(name,by_id[rid])
    assert actual==expected, f'{name}: expected {expected}, got {actual}'
assert len(clean)+len(excluded)==len(original)
assert all(p.get('rule_ids') for p in clean)
print(f'OK: {len(scenarios)} regresních testů, původně {len(original)} produktů, '
      f'v katalogu {len(clean)}, vyřazeno {len(excluded)}, změněna pravidla u {changed_rules}; '
      f'bez nového sběru',flush=True)
