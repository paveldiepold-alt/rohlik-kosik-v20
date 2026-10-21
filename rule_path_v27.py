"""Check narrow product-type rules against merchant breadcrumbs, never titles.

v27 taxonomy has two separate questions: is this in the correct shared aisle,
and does the retailer's category path independently substantiate the specific
search rule (e.g. chicken breasts versus thighs, or bananas versus avocado)?
A broad aisle is NOT evidence for the specific product type.
"""
from __future__ import annotations

import re
import unicodedata


def norm(v):
    s=unicodedata.normalize('NFKD',str(v or '')).casefold()
    return ' '.join(re.findall(r'[a-z0-9]+',''.join(c for c in s if not unicodedata.combining(c))))


def is_one(value, *terms):
    return norm(value) in {norm(x) for x in terms}


def starts(value, *terms):
    v=norm(value)
    return any(v == norm(x) or v.startswith(norm(x)+' ') for x in terms)


# Specific types that retailer navigation can actually distinguish.
# For ambiguous grouped subcategories the decision remains "review".
MEAT_TARGETS = {'W001':'chicken_breast', 'W002':'chicken_thigh',
                'W003':'pork_neck', 'W004':'pork_tenderloin',
                'W005':'beef_tenderloin'}
PRODUCE_TARGETS = {'W037':'avocado', 'W038':'banana', 'W039':'blueberry',
                   'W040':'raspberry', 'W041':'lemon', 'W042':'grapes',
                   'W043':'cucumber', 'W044':'tomato', 'W045':'cherry_tomato',
                   'W046':'carrot', 'W047':'pepper'}

# Leaf category recognizers do not read the product name. More ambiguous
# supermarket categories (e.g. "Citrusy") are deliberately absent.

def specific_type(path, category):
    """Return specific type from a conclusive merchant subcategory, else None.

    The *last* product-type breadcrumb takes precedence over broader ancestors:
    e.g. "Prsa a stehenní řízky > Prsa" is breasts, whereas the parent alone
    cannot establish that distinction.
    """
    if not isinstance(path, list) or len(path) < 3:
        return None
    nodes=[norm(x) for x in path[2:]]
    if category == 'Maso':
        # Verify the source animal from the second segment before checking the cut.
        branch=norm(path[1]);
        if starts(branch, 'drubez', 'drubezi maso'):
            for n in reversed(nodes):
                if starts(n, 'prsa a stehenni rizky'):
                    return None
                if starts(n, 'stehna', 'stehna a ctvrtky', 'stehenni rizky', 'spodni stehna', 'horni stehna', 'palicky'):
                    return 'chicken_thigh'
                if starts(n, 'prsa', 'prsa a rizky', 'prsni rizky', 'prsni platky'):
                    return 'chicken_breast'
            return None
        if starts(branch, 'veprove', 'veprove maso'):
            for n in reversed(nodes):
                if starts(n, 'krkovice a plec'): return None
                if starts(n,'krkovice'):return 'pork_neck'
                if starts(n,'panenka', 'veprova panenka'):return 'pork_tenderloin'
            return None
        if starts(branch, 'hovezi', 'hovezi maso', 'hovezi a teleci'):
            for n in reversed(nodes):
                if starts(n,'svickova a rostenec', 'rostena a svickova'): return None
                if starts(n,'svickova'):return 'beef_tenderloin'
            return None
        return None
    if category in {'Ovoce','Zelenina'}:
        for n in reversed(nodes):
            # Broad mixed categories must not prove a narrow variant.
            if is_one(n,'banany a exoticke', 'banany a exoticke ovoce',
                      'jahody a lesni plody','jahody a bobuloviny',
                      'citrusy','hrozny a melouny','okurky a cukety',
                      'okurky cukety a lilky','mrkev a korenova zelenina',
                      'korenova zelenina', 'papriky a chilli',
                      'papriky a chilli papricky', 'rajcata a papriky',
                      'salatova rajcata', 'zelenina','ovoce'):
                continue
            if starts(n, 'cherry rajcata', 'koktejlova cherry rajcata',
                      'cherry cervena','cherry barevna a mix', 'koktejlova rajcata', 'mini rajcata'):
                return 'cherry_tomato'
            if starts(n, 'rajcata','salatova rajcata'):
                return 'tomato'
            if starts(n, 'avokado'):return 'avocado'
            if starts(n, 'banany'):return 'banana'
            if starts(n, 'boruvky'):return 'blueberry'
            if starts(n, 'maliny'):return 'raspberry'
            if starts(n, 'citrony','citrony a limetky'):return 'lemon' if is_one(n,'citrony') else None
            if starts(n, 'hrozny', 'hroznove vino'):return 'grapes'
            if starts(n, 'okurky'):return 'cucumber'
            if starts(n, 'mrkev'):return 'carrot'
            if starts(n, 'papriky'):return 'pepper'
            # A leaf like "Salátová rajčata volná" clearly means tomatoes, not cherry.
        return None
    return None


# The rule itself may be narrower than a perfectly valid merchant aisle.
# Merchant breadcrumbs prove product TYPE, not the brand, package size or
# specific flavor. Names stay out of positive classification entirely.
WATER_RULES = frozenset({'W033', 'W034', 'W035'})
NEEDS_NARROW_EVIDENCE = frozenset({
    'W036',  # Coca-Cola Original, not Cola Zero/Light
    'W048', 'W049', 'W050', 'W051',  # specific sweets/flavors
    'W053', 'W054', 'W056',  # specific paper/wipes, shampoo variant
    'W060',  # disposable razors, not every shaving product
    'W063', 'W064', 'W065',  # conditioners vs washing agents, stain remover
    'W072', 'W073', 'W075',  # Jar lemon / particular handkerchief packs
})


def _path_nodes(item):
    path=item.get('store_category_path') or []
    return [norm(part) for part in path] if isinstance(path,list) else []


def _any_category(nodes,*terms):
    return any(starts(node,*terms) for node in nodes)


def _check_water_variant(nodes):
    # "Neperlivá mandarinka" is still flavored! Category ancestors outrank
    # carbonation words. Never turn flavor into acceptable plain water.
    if _any_category(nodes,'ochucene','ochucene vody','ochucene mineralni vody',
                     'ochucene neperlive','s prichuti','prichutove vody'):
        return 'mismatch','Prodejce výslovně řadí výrobek mezi ochucené vody'
    if _any_category(nodes,'silne perlive','stredne perlive','perlive','perlive vody') and not _any_category(nodes,'jemne perlive'):
        return 'mismatch','Kategorie prodejce označuje perlivou, nikoli sledovanou jemně perlivou/neperlivou vodu'
    if _any_category(nodes,'kojenecke vody','kojenecka voda','voda pro kojence'):
        return 'verified','Prodejce potvrzuje kojeneckou vodu; značku a balení stále kontroluje původní pravidlo'
    if _any_category(nodes,'neochucene','neochucene vody','neochucene mineralni vody') and _any_category(nodes,'neperlive','jemne perlive'):
        return 'verified','Prodejce potvrzuje neochucenou vodu odpovídající požadované variantě'
    return 'review','Prodejce potvrzuje kategorii vody, ale neprokazuje neochucenou povolenou variantu'


def _check_variant(rid,nodes):
    if rid in WATER_RULES:
        return _check_water_variant(nodes)
    if rid in ('W063','W064'):
        if _any_category(nodes,'avivaze','avivazni pripravky','vonne perlicky do pradla'):
            return 'verified','Podkategorie e-shopu odpovídá aviváži / pracím perličkám'
        if _any_category(nodes,'praci gely','praci prasky','kapsle na prani', 'praci tablety'):
            return 'mismatch','E-shop řadí produkt mezi prací prostředky, nikoli aviváže'
    if rid == 'W065':
        if _any_category(nodes,'odstranovace skvrn'):
            return 'verified','E-shop potvrzuje kategorii odstraňovačů skvrn'
        if _any_category(nodes,'avivaze'):
            return 'mismatch','E-shop řadí produkt mezi aviváže, nikoli odstraňovače skvrn'
    if rid == 'W054':
        if _any_category(nodes,'vlhcene ubrousky','vlhcene kapesniky'):
            return 'verified','Podkategorie e-shopu potvrzuje vlhčené ubrousky'
        if _any_category(nodes,'toaletni papir','papirove uterky','kuchynske uterky'):
            return 'mismatch','Podkategorie e-shopu je papír, nikoli vlhčené ubrousky'
    if rid == 'W060':
        if _any_category(nodes,'jednorazove holitka','jednorazove zilety','jednorazova holitka'):
            return 'verified','E-shop potvrzuje jednorázové holítko'
        if _any_category(nodes,'nahradni hlavice','elektricke strojky'):
            return 'mismatch','E-shop uvádí jiný typ holicího produktu'
    # For a narrow brand-specific variant a generic aisle cannot prove the
    # exact flavor, format or package. Do NOT infer it from a product title.
    return 'review','Kategorie prodejce potvrzuje sortiment, ale ne konkrétní variantu sledovaného pravidla'


def verify_specific_rule(rule_id, item, merchant):
    """Check the subtype proven independently by the *merchant's path*.

    Non-specialized rules return (None,None): their aisle mapping is already
    evaluated by catalog_v27. A rule-specific review is not a product deletion.
    """
    if rule_id in MEAT_TARGETS or rule_id in PRODUCE_TARGETS:
        targets = MEAT_TARGETS if rule_id in MEAT_TARGETS else PRODUCE_TARGETS
        expected = targets[rule_id]
        actual = specific_type(item.get('store_category_path'), merchant)
        if actual is None:
            return 'review','Cesta prodejce potvrzuje širší kategorii, nikoli konkrétní typ sledovaného pravidla'
        if actual == expected or (expected == 'tomato' and actual == 'cherry_tomato'):
            return 'verified',f'Konkrétní typ potvrzený podkategorií prodejce ({actual})'
        return 'mismatch',f'Konkrétní podkategorie prodejce ({actual}) je jiný druh než sledované pravidlo ({expected})'
    if rule_id in WATER_RULES or rule_id in NEEDS_NARROW_EVIDENCE:
        return _check_variant(rule_id, _path_nodes(item))
    return None, None
