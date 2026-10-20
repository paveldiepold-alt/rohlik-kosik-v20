"""Cautious, product-detail-scoped price extraction for Czech grocery pages.

A price is accepted only when it is linked to the product detail, visibly
rendered, not crossed out and not a unit price. We never use prices from
recommendation cards. No postcode/availability claims are made.
"""
from __future__ import annotations

import re
from typing import Any

_UNIT = re.compile(r'(?i)\b(?:kč|czk)\s*/\s*(?:kg|g|l|ml|ks|m|100\s*g|100\s*ml)\b')
_PRICE = re.compile(r'(?i)(?<!\d)(\d{1,4})[,.](\d{2})(?:\s*(?:kč|czk))?(?!\d)')
_SPLIT = re.compile(r'(?i)^(\d{1,4})[\s\u00a0\n]+(\d{2})(?:\s*(?:kč|czk))?$')
_WHOLE = re.compile(r'(?i)(?<!\d)(\d{1,4})\s*(?:kč|czk)(?!\w)')
_HINT_EXCLUDE = re.compile(r'(?i)(?:unit|per-unit|unitprice|regular|original|previous|strike|old[-_]?price|crossed|reference|price-per)')
_HINT_GOOD = re.compile(r'(?i)(?:actual|current|final|sale|discounted|product-price|price--now|price-current)')


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
    const unit = /\b(?:Kč|CZK)\s*\/\s*(?:kg|g|l|ml|ks|m|100\s*g|100\s*ml)\b/i.test(txt)
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
