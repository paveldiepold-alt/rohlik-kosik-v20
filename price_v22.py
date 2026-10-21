"""Košík: strict product-pack price parsing from the own H1-adjacent price block.

No category/brand-specific prices; never substitute a unit or quantity offer for
one item. Returns (amount, extraction_source, explanation), or unverified.
"""
from __future__ import annotations
import re

UNIT_RE = re.compile(
    r'(?i)(?:kč|czk)\s*/\s*(?:1\s*)?(?:kg|g|l|ml|ks|m|100\s*g|100\s*ml|'
    r'dávk\w*|pran\w*|porc\w*|použit\w*|rol\w*|metr\w*|myt\w*|tab\w*)\b'
)
AMOUNT_SPLIT = re.compile(r'^([1-9]\d{0,4})\s+([0-9]{2})(?:\s*(?:Kč|CZK))?$', re.I)
AMOUNT_DECIMAL = re.compile(r'^([1-9]\d{0,4})[.,]([0-9]{2})\s*(?:Kč|CZK)?$', re.I)
CONDITIONAL = re.compile(r'(?i)(?:\bod\s*\d+\s*ks\b|\bza\s*(?!1\s*ks)\d+\s*ks\b)')
STOP = re.compile(r'(?i)^(?:do košíku|značka\s*:|země původu\s*:|popis produktu|podobné produkty|další varianty)')


def _val(s: str) -> float | None:
    s = s.replace('\u00a0',' ').replace('\u202f',' ').strip()
    m = AMOUNT_SPLIT.fullmatch(s) or AMOUNT_DECIMAL.fullmatch(s)
    return (round(int(m.group(1))+int(m.group(2))/100,2) if m else None)


def choose_kosik_pack_price(detail_text: str) -> tuple[float | None, str | None, str]:
    """Parse only the product's own compact price area, not page-wide cards.

    Strong positive evidence is a pair 'crowns cents' followed by a unit-price
    label. A product-specific display with a single price line can also work.
    Ambiguous prices, old prices without clear distinction and only unit-prices
    remain unverified.
    """
    if not isinstance(detail_text,str) or not detail_text.strip():
        return None, None, 'v22: produktový cenový blok není dostupný'
    lines=[]
    for x in detail_text.replace('\u00a0',' ').replace('\u202f',' ').splitlines():
        x=' '.join(x.split())
        if STOP.match(x):break
        if x:lines.append(x)
        if len(lines)>=30:break
    if not lines:return None,None,'v22: prázdný cenový blok'

    # Labelled price of ONE whole item wins over a price conditional on 2+ items.
    for line in lines:
        m=re.search(r'(?i)([1-9]\d{0,4})[,.]([0-9]{2})\s*(?:Kč|CZK)\s+za\s+1\s+ks\b',line)
        if m:
            return round(int(m.group(1))+int(m.group(2))/100,2),'kosik-pack-v22', 'Ceníková cena 1 ks (výslovná)'

    # Find H1-adjacent price, whose printed currency-unit is usually the next
    # line: '699 00 / 7,77 Kč/dávka'. Skip promo/old-price segments.
    found=[]
    for i,line in enumerate(lines):
        if any(z in line.lower() for z in ('doprava','registrace','přihlášení')):continue
        if UNIT_RE.search(line) or '%' in line or CONDITIONAL.search(line):continue
        if '~~' in line or 'původní' in line.lower() or 'běžná cena' in line.lower():continue
        amount=_val(line)
        consume=1
        if amount is None and i+1<len(lines) and re.fullmatch(r'[1-9]\d{0,4}',line) and re.fullmatch(r'\d{2}',lines[i+1]):
            amount=_val(line+' '+lines[i+1]); consume=2
        if amount is None:continue
        # Price in product header is followed by a labelled unit-price in many
        # Košík layouts. This proves the split numbers are a PACK price.
        neighbor=lines[i+consume:i+consume+4]
        evidence=any(UNIT_RE.search(x) for x in neighbor)
        # Avoid accepting sale/old-price pair when no corroboration exists.
        found.append((i,amount,bool(evidence),consume))

    # Price reduced from a struck-through old value: header text often reads
    # '469 00 / 699,00 Kč / -32 % / unit price'. Both figures can precede
    # unit pricing; the first is current only when the following line clearly
    # carries a discount percentage.
    if len(found) >= 2:
        first, second = found[0], found[1]
        after_old=lines[second[0]+second[3]:second[0]+second[3]+2]
        if (first[0] < second[0] and first[1] < second[1]
            and any(re.search(r'-\s*\d{1,2}\s*%', z) for z in after_old)):
            return first[1],'kosik-pack-v22','Aktuální cena se slevovým procentem u původní ceny'

    supported=[(i,n) for i,n,e,_ in found if e]
    if supported:
        # Usually one such price; two corroborated and different => ambiguity.
        prices={n for _,n in supported}
        if len(prices)==1:
            return prices.pop(),'kosik-pack-v22','Celé balení: cena navázaná na jednotkovou cenu'
        return None,None,'v22: více konfliktujících cen celého balení'
    # A single standalone decimal price without any other candidate is safe,
    # but NEVER equate a dose price with a whole-pack price.
    if len(found)==1 and not any(UNIT_RE.search(x) for x in lines):
        i,n,e,c=found[0]
        if AMOUNT_DECIMAL.fullmatch(lines[i]):
            return n,'kosik-pack-v22','Jednoznačná cena v produktovém detailu'
    if any(UNIT_RE.search(x) for x in lines):
        return None,None,'v22: nalezena pouze jednotková nebo nejednoznačná cena; celá cena není potvrzena'
    return None,None,'v22: cena balení není jednoznačně identifikovaná'
