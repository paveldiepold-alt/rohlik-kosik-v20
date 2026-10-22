"""Cautious, product-detail-scoped price extraction for Czech grocery pages.

A price is accepted only when it is linked to the product detail, visibly
rendered, not crossed out and not a unit price. We never use prices from
recommendation cards. No postcode/availability claims are made.
"""
from __future__ import annotations

import re
from typing import Any

_UNIT = re.compile(r'(?i)\b(?:kč|czk)\s*/\s*(?:kg|g|l|ml|ks|m|100\s*g|100\s*ml|dávk\w*|pran\w*|porc\w*|použit\w*|rol\w*)\b')
_PRICE = re.compile(r'(?i)(?<!\d)(\d{1,4})[,.](\d{2})(?:\s*(?:kč|czk))?(?!\d)')
_SPLIT = re.compile(r'(?i)^(\d{1,4})[\s\u00a0\n]+(\d{2})(?:\s*(?:kč|czk))?$')
_WHOLE = re.compile(r'(?i)(?<!\d)(\d{1,4})\s*(?:kč|czk)(?!\w)')
_HINT_EXCLUDE = re.compile(r'(?i)(?:unit|per-unit|unitprice|regular|original|previous|strike|old[-_]?price|crossed|reference|price-per)')
_HINT_GOOD = re.compile(r'(?i)(?:actual|current|final|sale|discounted|product-price|product-detail-price-section-price|price--now|price-current)')


def parse_display_price(text: str) -> float | None:
    """Parse a single displayed CZK price; avoid percentages, packs and unit prices."""
    if not isinstance(text, str):
        return None
    s = text.replace('\u202f', ' ').replace('\xa0', ' ').strip()
    if not s or len(s) > 75 or _UNIT.search(s):
        return None
    # Do not accept a shipping threshold or packaging condition as a product price.
    if re.search(r'(?i)(?:doprava|za dopravu|nad \d+\s*kč)', s):
        return None
    # Price wrappers can concatenate children: '14990 Kč 169,90 Kč'.
    # Accept only a single amount, not one numeric match within a bigger string.
    if len(re.findall(r'(?i)\b\d{2,5}\s*(?:Kč|CZK)\b', s)) > 1:
        return None
    for pattern in (_PRICE, _SPLIT, _WHOLE):
        matches = list(pattern.finditer(s))
        if len(matches) != 1:
            continue
        match = matches[0]
        if match.re is _WHOLE:
            number = float(match.group(1))
        else:
            number = float(match.group(1)) + int(match.group(2)) / 100
        if 0.5 <= number <= 50000:
            return round(number, 2)
    return None


def choose_visible_price(nodes: list[dict[str, Any]]) -> tuple[float | None, str | None, str]:
    """Choose only a uniquely supported current price from the product header.

    `nodes` are filtered in the browser by proximity to the product H1,
    excluding unrelated links and recommendations. Conflicts remain unverified.
    """
    possible: list[tuple[int, float, str]] = []
    for node in nodes or []:
        if not isinstance(node, dict) or node.get('old') or node.get('unit') or not node.get('detail', False):
            continue
        hint = str(node.get('hint') or '')
        if _HINT_EXCLUDE.search(hint):
            continue
        price = parse_display_price(str(node.get('text') or ''))
        if price is None:
            continue
        distance = float(node.get('distance') or 0)
        if distance > 560:
            continue
        score = 3 if _HINT_GOOD.search(hint) else 1
        if distance <= 240:
            score += 2
        if node.get('contains_currency'):
            score += 1
        condition = str(node.get('condition') or '')
        possible.append((score, price, condition))
    if not possible:
        return None, None, 'Na detailu produktu nebyla jednoznačná běžná/akční cena'
    highest = max(score for score, _, _ in possible)
    winning_prices = {price for score, price, _ in possible if score == highest}
    if len(winning_prices) != 1:
        return None, None, 'Více různých možných aktuálních cen v detailu produktu'
    selected = winning_prices.pop()
    # If a different current-looking price is nearly as strong, do not guess.
    if any(price != selected and score >= highest - 1 for score, price, _ in possible):
        return None, None, 'Rozpor mezi aktuálními cenovými údaji produktu'
    conditions = {cond for score, price, cond in possible if price == selected and score == highest and cond}
    note = 'Zobrazená cena na detailu výrobku; lokalita nebyla ověřena'
    if len(conditions) == 1:
        note = conditions.pop() + '; ' + note
    return selected, 'visible-product-detail', note


def extract_rohlik_discount(current_price: float, candidates: list[dict], detail_text: str = '') -> dict:
    """Only trust a unique visible crossed-out product-pack price.

    No invented promotion from price history, unit prices, quantity discounts,
    structured-data prices or recommendations elsewhere on the page.
    """
    empty = {'original_price_czk': None, 'discount_pct': None,
             'offer_valid_until': None}
    if not isinstance(current_price, (int, float)) or current_price <= 0:
        return empty
    old_prices = set()
    for node in candidates or []:
        if not isinstance(node, dict) or not node.get('detail') or not node.get('old'):
            continue
        if node.get('unit') or node.get('condition'):
            continue
        if float(node.get('distance') if node.get('distance') is not None else 9999) > 450:
            continue
        hint = str(node.get('hint') or '')
        if re.search(r'(?i)unit[-_]?price|price[-_]?per[-_]?unit', hint):
            continue
        amount = parse_display_price(str(node.get('text') or ''))
        if amount is not None:
            old_prices.add(amount)
    if len(old_prices) != 1:
        return empty
    old = old_prices.pop()
    if old <= current_price or old > current_price * 7:
        return empty
    pct = round(100 * (1 - current_price / old), 1)
    if not 1 <= pct <= 85:
        return empty
    explicit = re.search(r'(?<!\w)[−–-]\s*(\d{1,2})\s*%', str(detail_text or '')[:650])
    if explicit and abs(float(explicit.group(1)) - pct) > 3:
        return empty
    return {'original_price_czk': old, 'discount_pct': pct,
            'offer_valid_until': None}


def choose_kosik_detail_price(text: str) -> tuple[float | None, str | None, str]:
    """Read Košík product's *own* price block, never search/recommendations.

    Input is text immediately after the product H1, cut at the cart/brand
    boundary by the browser. This deliberately prefers a non-conditional price
    over multibuy discounts. Unclear cases are left unverified.
    """
    if not isinstance(text, str) or not text.strip():
        return None, None, 'Košík: cenový blok produktu nebyl vykreslen'
    text = text.replace('\u00a0', ' ').replace('\u202f', ' ')
    text = re.split(r'(?im)^\s*(?:Značka\s*:|Země původu\s*:|Popis produktu\s*$|Další varianty\s*$|Do košíku\s*$)', text, maxsplit=1)[0]
    lines = [x.strip() for x in text.splitlines() if x.strip()][:28]
    # Decimal fractions in a separate superscript usually appear as '19 90'.
    # On Košík this denotes ordinary price unless specifically marked 'od N ks'.
    split_candidates: list[float] = []
    for i, line in enumerate(lines):
        if re.fullmatch(r'\d{1,4}', line) and i+1 < len(lines) and re.fullmatch(r'\d{2}', lines[i+1]):
            # Split DOM spans (crowns then superscript cents on the next line).
            # Accept only when a unit-price label corroborates the pair nearby.
            if any(_UNIT.search(other) for other in lines[i+2:i+5]):
                amount = parse_display_price(line + ' ' + lines[i+1])
                if amount is not None:
                    split_candidates.append(amount)
            continue
        if _UNIT.search(line) or re.search(r'(?i)\bod\s*\d+\s*ks\b|\bza\s*1\s*ks\b', line):
            continue
        if re.search(r'(?i)doprav|registr|přihl', line):
            continue
        if not re.fullmatch(r'\d{1,4}\s+\d{2}(?:\s*(?:Kč|CZK))?', line, re.I):
            continue
        # Validate that the price is on the product's price line, not a pack size.
        if i + 1 < len(lines) and re.search(r'(?i)\b(?:ks|g|kg|ml|l)\b', lines[i+1]) and not _UNIT.search(lines[i+1]):
            continue
        val = parse_display_price(line)
        if val is not None:
            split_candidates.append(val)
    if len(set(split_candidates)) == 1:
        return split_candidates[0], 'kosik-product-text', 'Běžná cena 1 ks z produktového detailu; místní dostupnost neověřena'
    if len(set(split_candidates)) > 1:
        return None, None, 'Košík: více různých nekondicionálních cen v detailu'
    # If the page prints 19,90 Kč rather than 19 90, accept only one price
    # once quantity discounts, old prices and unit prices are excluded.
    if re.search(r'(?i)multikup|množstevní sleva|\bod\s*\d+\s*ks', text):
        return None, None, 'Košík: množstevní nabídka bez jednoznačné ceny jednoho kusu'
    ordinary = []
    for line in lines:
        if _UNIT.search(line) or '%' in line or re.search(r'(?i)\bod\s*\d+\s*ks\b', line):
            continue
        amount = parse_display_price(line)
        if amount is not None:
            ordinary.append(amount)
    if len(set(ordinary)) == 1:
        return ordinary[0], 'kosik-product-text', 'Cena z produktového detailu; místní dostupnost neověřena'
    return None, None, 'Košík: cena není v detailu dostatečně jednoznačná'


# Executed in the browser only. Visible DOM geometry anchors candidates to
# the target product heading, avoiding other product cards and page-wide prices.
VISIBLE_PRICE_JS = r"""() => {
  const title = document.querySelector('h1');
  if (!title) return [];
  const h = title.getBoundingClientRect();
  if (!h.width || !h.height) return [];
  const tags = '[data-testid*="price" i], [data-test*="price" i], [class*="price" i], [itemprop="price"]';
  const all = [...document.querySelectorAll(tags)];
  const out = [];
  const seen = new Set();
  for (const el of all) {
    if (el.closest('header,nav,footer,aside,[role="dialog"], [role="listbox"]')) continue;
    if (el.closest('a[href*="/p"], a[href*="/product"]')) continue;
    const r = el.getBoundingClientRect();
    const dist = Math.abs(r.top-h.top);
    if (!r.width || !r.height || dist > 560 || Math.abs(r.left-h.left) > 530) continue;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
    let txt = (el.innerText || el.textContent || '').replace(/\s+/g,' ').trim();
    // A Czech price may render crowns and cents in separate inline nodes.
    // Some DOM layouts concatenate `63` + `90` into misleading `6390`.
    const centsEl = el.querySelector('sup');
    if (centsEl) {
      const cents = (centsEl.textContent || '').trim();
      const withoutCents = (el.textContent || '').replace(centsEl.textContent || '', '').trim();
      const crowns = withoutCents.match(/^\s*(\d{1,3})\s*(?:Kč|CZK)?\s*$/i);
      if (/^\d{2}$/.test(cents) && crowns) txt = crowns[1] + ',' + cents + ' Kč';
    }
    if (!txt || txt.length > 75) continue;
    const cls = typeof el.className === 'string' ? el.className : '';
    const hint = [cls, el.getAttribute('data-testid'), el.getAttribute('data-test')].filter(Boolean).join(' ');
    const parents = [el, el.parentElement, el.parentElement?.parentElement].filter(Boolean);
    const old = parents.some(p => {
      const cl = typeof p.className === 'string' ? p.className : '';
      const dec = getComputedStyle(p).textDecorationLine;
      return p.matches('s,del,strike') || /line-through/.test(dec) || /(?:old[-_]?price|previous-price|original-price|strikethrough)/i.test(cl);
    });
    const unit = /\b(?:Kč|CZK)\s*\/\s*(?:kg|g|l|ml|ks|m|100\s*g|100\s*ml|dávk\w*|pran\w*|porc\w*|použit\w*|rol\w*)\b/i.test(txt)
        || /unit[-_]?price|price[-_]?per[-_]?unit/i.test(hint);
    const key = [txt,hint,Math.round(r.top),Math.round(r.left)].join('|');
    if (seen.has(key)) continue;
    seen.add(key);
    const parentText = (el.parentElement?.innerText || '').replace(/\s+/g, ' ').slice(0,100);
    const qty = parentText.match(/\bod\s+(\d+)\s*ks\b/i);
    out.push({text: txt, hint, distance: Math.round(dist), old, unit,
      condition: qty ? ('Podmínka: od ' + qty[1] + ' ks') : '',
      contains_currency: /(?:Kč|CZK)/i.test(txt), detail: true});
    if (out.length >= 75) break;
  }
  return out;
}"""
