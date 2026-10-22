#!/usr/bin/env python3
"""Strict Rohlík product-header fallback when normal parser says unverified.

The prior certified parser runs first; this function never overrides an existing
verified price. Read ONLY the current product's own text between H1 and the cart
button; refuse ambiguous prices, unit prices and multibuy conditions. Never
infer a pack price by multiplying a per-kg price by approximate weight.
"""
from __future__ import annotations
import re
from typing import Any

# Whole amount, decimal amount, or visually split crowns + superscript haléře.
_SPLIT = re.compile(r'(?<![\d])(?P<korun>\d{1,5})[ \t\r\n\u00a0\u202f]+(?P<haleru>\d{2})[ \t\r\n\u00a0\u202f]*(?:Kč|CZK)\b', re.I)
_DEC = re.compile(r'(?<![\d])(?P<korun>\d{1,5})[.,](?P<haleru>\d{2})\s*(?:Kč|CZK)\b', re.I)
_WHOLE = re.compile(r'(?<![\d])(?P<korun>\d{1,5})\s*(?:Kč|CZK)\b', re.I)
_UNIT_PRICE = re.compile(r'(?iu)\b\d{1,6}(?:[.,]\d{1,2})?\s*(?:Kč|CZK)\s*/\s*(?:\d+\s*)?(?:kg|g|l|ml|ks|m|100\s*g|100\s*ml|pran\w*|dávk\w*|porc\w*|rol\w*|použit\w*)\b')
_CUTOFF = re.compile(r'(?im)^\s*(?:Do košíku|Souhrn produktu|Více informací o produktu|Podobné produkty|Další varianty)\s*$')
_CONDITIONAL = re.compile(r'(?iu)\b(?:od\s+\d+\s*ks|při\s+nákupu|s\s+klubovou\s+cenou)\b')
_OLD_LINE = re.compile(r'(?iu)\b(?:původní\s+cena|p\u016fvodn\u011b|dříve\s+za|ušetříte|běžná\s+cena)\b')

# The first add-to-cart boundary guarantees recommendation cards are not read.
OWN_HEADER_JS = r"""() => {
  const h = document.querySelector('h1');
  if (!h) return {title:'',text:'',bounded:false};
  const title=(h.innerText||h.textContent||'').trim();
  const main=h.closest('main')||document.querySelector('main')||document.body;
  const all=main.innerText||'';
  const start=all.indexOf(title);
  if (start<0) return {title,text:'',bounded:false};
  const tail=all.slice(start+title.length,start+title.length+1100);
  const match=/(?:^|\n)\s*Do košíku\s*(?=\n|$)/i.exec(tail);
  if (!match || match.index>650) return {title,text:'',bounded:false};
  return {title,text:tail.slice(0,match.index),bounded:true};
}"""


def detail_price(text: str) -> tuple[float | None, str]:
    """Return unique unambiguous H1-header CZK item price, or reject.

    Intended for a rendered product page. Not a general text/document scraper.
    """
    if not isinstance(text, str) or not text.strip():
        return None, 'missing-product-header-text'
    text = text.replace('\u00a0', ' ').replace('\u202f', ' ')
    cutoff = _CUTOFF.search(text)
    if cutoff:
        text = text[:cutoff.start()]
    # Source extractor anchors just after H1; cap length to avoid recommendations.
    text = text[:650]
    if _CONDITIONAL.search(text):
        return None, 'conditional-multibuy-without-unique-single-price'
    # Reject old-price labels; never promote a former price to the current price.
    text = '\n'.join(line for line in text.splitlines() if not _OLD_LINE.search(line))
    # Strip any unit-price amount (e.g. 259,90 Kč/kg); NEVER treat it as pack price.
    cleaned = _UNIT_PRICE.sub(' ', text)
    candidates = []
    occupied = []
    # Prioritize decimal/split forms before whole amounts and avoid overlap.
    for pattern in (_SPLIT, _DEC, _WHOLE):
        for match in pattern.finditer(cleaned):
            if any(match.start() < hi and match.end() > lo for lo, hi in occupied):
                continue
            crowns = int(match.group('korun'))
            cents = match.groupdict().get('haleru')
            amount = round(crowns + (int(cents) / 100 if cents is not None else 0), 2)
            if 0.5 <= amount <= 1000:
                candidates.append(amount)
            occupied.append(match.span())
    unique = set(candidates)
    if len(unique) == 1:
        amount = unique.pop()
        return amount, ('rohlik-own-H1-visible-price-estimated' if re.search(r'(?iu)\bcca\b', cleaned)
                        else 'rohlik-own-H1-visible-price')
    if not unique:
        return None, 'no-unique-product-pack-price'
    return None, 'conflicting-product-price-candidates'


def improved_observation(page: Any, row: dict) -> dict:
    """Use the certified reader first; fallback only after safe identity match."""
    from maintenance_v26 import inspect_saved
    observation = inspect_saved(page, row)
    if (row.get('store') != 'Rohlík' or observation.get('status') != 'price_unverified'
            or observation.get('blocked')):
        return observation
    from monitor import valid_title
    try:
        payload = page.evaluate(OWN_HEADER_JS)  # same visited page; no extra request
        if not isinstance(payload, dict) or not payload.get('bounded'):
            return observation
        title = payload.get('title') or ''
        if not valid_title(title, {'label': row.get('title') or row.get('name') or ''}):
            return observation
        value, reason = detail_price(payload.get('text', ''))
        if value is not None:
            return {'status': 'ok', 'price': value, 'source': 'v27b:'+reason,
                    'note': 'Výslovná cena v detailu výrobku; dostupnost/lokalita nepotvrzena',
                    'blocked': False, 'offer': {}}
        observation = dict(observation)
        observation['note'] = 'v27b: '+reason+'; '+str(observation.get('note',''))[:130]
    except Exception as exc:
        observation = dict(observation)
        observation['note'] = 'v27b diagnostic: '+type(exc).__name__+'; '+str(observation.get('note',''))[:130]
    return observation
