"""Retailer-first validation of meat watch rules W001..W005.

No positive classification by keywords. Title/description can only veto a
retailer-confirmed category. Missing retailer taxonomy goes to review.
"""
from __future__ import annotations
import re
import unicodedata

MEAT_RULES = {f'W{x:03d}' for x in range(1, 6)}
TRUSTED = {'jsonld_breadcrumb','dom_breadcrumb','jsonld_product_category','product_category_links'}


def fold(value):
    s = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in s if not unicodedata.combining(c))).split())


def any_part(parts, roots):
    return any(any(part == r or part.startswith(r+' ') or (' '+r+' ') in (' '+part+' ') for r in roots)
               for part in parts)


# Full merchant taxonomy takes precedence over any matching product words.
NON_RAW = (
    'hotova jidla', 'hotovky', 'hotove pokrmy', 'hotova', 'polevky',
    'konzervy', 'konzervovana hotova jidla', 'sterilovane', 'trvanlive',
    'uzeniny', 'sunky', 'salámy', 'saláty', 'sendvice',
    'polotovary', 'hotovky a polotovary', 'obalovane', 'predpripravene',
    'mrazene hotovky', 'zachran me', 'pecene', 'grilovane', 'chlazena hotova jidla',
    'hotova kuchyne', 'lahudky', 'krmiva', 'krmivo', 'psi', 'kocky',
    'chovatelske potreby', 'pro zvirata', 'pro mazlicky', 'restaurace',
)
NON_FOOD = ('drogerie', 'domacnost a zahrada', 'zdravi', 'doplnky stravy', 'kosmetika')
RAW_PARENT = (
    'maso a ryby', 'cerstve maso', 'maso', 'drubezi maso', 'veprove maso',
    'hovezi maso', 'kureci maso', 'kure', 'veprove', 'hovezi',
)
RAW_LEAF = (
    'prsa rizky nudlicky', 'prsa a rizky', 'stehna a ctvrtky',
    'kureci stehna', 'kureci prsa', 'krkovice', 'panenka', 'svickova',
    'hovezi', 'veprove', 'kure', 'drubezi', 'cerstve',
)
# Only negative hints: supplement real retailer paths, never invent a positive category.
NOT_RAW_TITLE = re.compile(r'\b(?:gyros|kentucky|pesto|kurkumov\w*|knedlik\w*|omack\w*|'
                           r'obalovan\w*|grilovan\w*|pecen\w*|'
                           r'konzerv\w*|vlastni stave|uzen\w*|sunk\w*|'
                           r'hotov\w*|varene|smazene|salat|kapsick\w*|'
                           r'pamlsk\w*|krmiv\w*|pro kocky|pro psy|'
                           r'pastet\w*|gulas|ragu)\b')
NOT_RAW_DESCRIPTION = re.compile(r'\b(?:hotove jidlo|hotovy pokrm|tepeln e upravene|'
                                 r'k okamzite konzumaci|staci ohrat|konzervovan\w*|'
                                 r'obalovan\w*|sterilovan\w*)\b'.replace('tepeln e','tepelne'))


def decide(row):
    path = [fold(x) for x in (row.get('store_category_path') or []) if str(x).strip()]
    source = row.get('category_source')
    if not path or source not in TRUSTED:
        return 'review', 'Bez prokazatelne kategorie produktove stranky e-shopu'
    if any_part(path, NON_RAW + NON_FOOD):
        return 'reject', 'Cela kategorie prodejce oznacuje hotovy nebo jiny druh zbozi'
    # A shop's valid fresh-meat branch is required; a generic mention of meat
    # in a description, title or unrelated breadcrumb is insufficient.
    if not any_part(path, RAW_PARENT + RAW_LEAF):
        return 'reject', 'Produkt neni v odpovidajici kategorii syroveho masa'
    # A retailer category with generic "Maso" sometimes includes prepared
    # products. Secondary evidence may only reject or quarantine them.
    name = fold(row.get('title') or row.get('name'))
    desc = fold(row.get('product_description'))
    if NOT_RAW_TITLE.search(name) or NOT_RAW_DESCRIPTION.search(desc):
        return 'review', 'Kategorie je obecna; nazev ci popis naznacuje zpracovany pokrm'
    return 'accept', 'Shoda s kategorii syroveho masa na e-shopu'


def gate_meat_item(item):
    ids=list(item.get('rule_ids') or [])
    targets=[x for x in ids if x in MEAT_RULES]
    if not targets: return dict(item),None
    status, reason=decide(item)
    if status=='accept':
        p=dict(item)
        p['meat_taxonomy_v25']='verified'
        return p,None
    kept=[x for x in ids if x not in MEAT_RULES]
    review=dict(item)
    review['v25_meat_check']={'status':status,'reason':reason,
                              'merchant_path':item.get('store_category_path') or [],
                              'source':item.get('category_source')}
    if not kept:
        review['taxonomy_status']=status
        return None,review
    public=dict(item)
    public['rule_ids']=kept
    public['meat_taxonomy_v25']='partial'
    return public,review
