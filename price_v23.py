"""Retailer product-detail prices and promotion metadata (never per-unit as pack).

Pure functions are independent of brand or product category. Ambiguous prices
stay unknown. Read only the product's own header, not recommended products.
"""
from __future__ import annotations
from datetime import datetime, timezone
import re

UNIT = re.compile(r'(?iu)(?:kč|czk)\s*/\s*(?:\d+\s*)?(?:kg|g|l|ml|ks|m|dávk\w*|pran\w*|porc\w*|použit\w*|myt\w*|rol\w*|metr\w*)\b')
SPLIT = re.compile(r'^(\d{1,5})\s+(\d{2})(?:\s*(?:kč|czk))?$',re.I)
DEC = re.compile(r'^(\d{1,5})[.,](\d{2})(?:\s*(?:kč|czk))?$',re.I)
WHOLE = re.compile(r'^(\d{1,5})\s*(?:kč|czk)$',re.I)
PERCENT = re.compile(r'(?i)[−-]\s*(\d{1,2})\s*%')
DATE = re.compile(r'(?i)\bdo\s+(\d{1,2})\.\s*(\d{1,2})\.(?:\s*(\d{4}))?')
QUANTITY = re.compile(r'(?i)\bod\s*(\d+)\s*ks\b')
STOP = re.compile(r'(?i)^(?:do košíku|popis produktu|složení|další varianty|podobné produkty|produkty značky|zákonný název|značka\s*:|země původu\s*:)')

# Run inside retailer page after successful top-level navigation.
PRODUCT_HEADER_JS = r'''() => {
  const h=document.querySelector('h1');
  if (!h) return {title:'',text:''};
  const title=(h.innerText||h.textContent||'').trim();
  const main=h.closest('main') || document.querySelector('main') || document.body;
  const raw=main.innerText || '';
  const start=raw.indexOf(title);
  if (start < 0) return {title,text:''};
  const text=raw.slice(start+title.length,start+title.length+1750);
  return {title,text};
}'''


def _money(text:str)->float|None:
    s=' '.join(str(text or '').replace('\u00a0',' ').replace('\u202f',' ').split())
    match=SPLIT.fullmatch(s) or DEC.fullmatch(s)
    if match:
        amount=int(match[1])+int(match[2])/100
        return round(amount,2) if .5<=amount<=50000 else None
    match=WHOLE.fullmatch(s)
    if match:
        amount=int(match[1]);return float(amount) if 1<=amount<=50000 else None
    return None


def _expiry(text: str, checked_at: str) -> str|None:
    match=DATE.search(text)
    if not match:return None
    try:
        stamp=datetime.fromisoformat(checked_at.replace('Z','+00:00'))
        year=int(match[3]) if match[3] else stamp.year
        date=datetime(year,int(match[2]),int(match[1]),tzinfo=timezone.utc)
        # If the observation occurs in December and the promo is explicitly
        # listed for January, it most probably refers to the following year.
        if not match[3] and stamp.month>=11 and date.month<=2:
            date=date.replace(year=year+1)
        return date.date().isoformat()
    except (ValueError,TypeError):return None


def parse_product_offer(text: str, checked_at: str) -> dict:
    """Return price of *one entire package* and observed promotion fields.

    An old crossed-out price needs independent evidence (percentage/date).
    A standalone per-dose/per-kilo price is never the package price.
    """
    empty={'price_czk':None,'original_price_czk':None,'discount_pct':None,
           'offer_valid_until':None,'min_qty':None,'multibuy_price_czk':None,
           'source':'none','reason':'Cenový blok není jednoznačný'}
    if not isinstance(text,str) or not text.strip():return empty
    lines=[]
    for raw in text.replace('\u00a0',' ').replace('\u202f',' ').splitlines():
        line=' '.join(raw.split())
        if STOP.match(line):break
        if line:lines.append(line)
        if len(lines)>=55:break
    if not lines:return empty
    pct=None;until=None;qty=None;special=None
    for i,line in enumerate(lines):
        mm=PERCENT.search(line)
        if mm and pct is None:pct=int(mm[1])
        if until is None and mm:until=_expiry(line,checked_at)
        if qty is None:
            q=QUANTITY.search(line)
            if q:qty=int(q[1])
    # The explicit single-item price has highest authority for multibuy rows.
    one=None
    for line in lines:
        m=re.search(r'(?iu)(\d{1,5})[,.](\d{2})\s*(?:Kč|CZK)\s+za\s+1\s*ks',line)
        if m:one=_money(m[1]+' '+m[2]);break
    if qty:
        for line in lines:
            m=re.search(r'(?iu)(\d{1,5})[,.](\d{2})(?:\s*(?:Kč|CZK))?\s+od\s*\d+\s*ks',line)
            if m:special=_money(m[1]+' '+m[2]);break
    # Distinguish price lines from dose / per-unit labels and quantity offers.
    found=[]
    for i,line in enumerate(lines):
        if UNIT.search(line) or re.search(r'(?i)%|od\s*\d+\s*ks|za\s*1\s*ks|doprava|sleva',line):continue
        val=_money(line);consumed=1
        if val is None and i+1<len(lines) and re.fullmatch(r'\d{1,5}',line) and re.fullmatch(r'\d{2}',lines[i+1]):
            val=_money(line+' '+lines[i+1]);consumed=2
        if val is None:continue
        nearby=lines[i+consumed:i+consumed+6]
        evidence=any(UNIT.search(x) for x in nearby)
        found.append((i,val,evidence,consumed))
    result=dict(empty)
    result.update(offer_valid_until=until,min_qty=qty,multibuy_price_czk=special)
    if one is not None:
        result.update(price_czk=one,source='single-pack-explicit',reason='Výslovná cena za 1 ks');return result
    if not found:
        result['reason']='Cena za celé balení nebyla nalezena';return result
    # For discounted products, price text commonly follows: current, former, -N%.
    if pct is not None and len(found)>=2:
        first,second=found[0],found[1]
        if first[1]<second[1] and first[0]<second[0] and abs(100*(1-first[1]/second[1])-pct)<=2.5:
            result.update(price_czk=first[1],original_price_czk=second[1],
                          discount_pct=round(100*(1-first[1]/second[1]),1),
                          source='discounted-pack',reason='Cena balení, původní cena a sleva souhlasí')
            return result
    supported=[x for x in found if x[2]]
    if len({x[1] for x in supported})==1 and supported:
        result.update(price_czk=supported[0][1],source='pack-plus-unit',reason='Cena balení ověřená jednotkovou cenou')
        return result
    # One price and no unit label: accept only when displayed with currency.
    if len(found)==1 and not any(UNIT.search(x) for x in lines):
        i,val,_,_=found[0]
        if re.search(r'(?i)kč|czk',lines[i]):
            result.update(price_czk=val,source='single-product-amount',reason='Jednoznačná cena produktu')
            return result
    result['reason']='Různé kandidátní ceny; cena celého balení nepotvrzena'
    return result


def product_identity(expected: str, actual: str) -> bool:
    def norm(s):
        import unicodedata
        s=''.join(c for c in unicodedata.normalize('NFKD',str(s or '').casefold()) if not unicodedata.combining(c))
        return re.findall(r'[a-z0-9]+',s)
    x=norm(expected);y=norm(actual)
    if not x or not y:return False
    from collections import Counter
    a=Counter(x);b=Counter(y);shared=sum((a&b).values())
    return shared>=2 and shared/len(x)>=0.75 and shared/len(y)>=0.65
