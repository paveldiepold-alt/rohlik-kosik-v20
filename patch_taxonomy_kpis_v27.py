#!/usr/bin/env python3
"""Safely add visible retailer-taxonomy KPIs to the CURRENT published HTML.

Input/output: docs/catalog.html ONLY. Never copies or modifies product catalogue,
price history, taxonomy overlays or any tracked data file.
"""
from __future__ import annotations
import argparse
from pathlib import Path

SENTINEL = 'id="taxonomyKpisV27"'
ANCHORS = {
    'quick': '<div class="quick" aria-label="Rychlé zobrazení">',
    'css': '</style>\n</head>',
    'function': 'async function loadCategoryOverlay(){',
    'loader': 'await loadCategoryOverlay();rules=new Map(',
}

CSS = '''/* v27 UAT13: prominent category progress - visual only, no data mutations. */
.taxonomy-kpis-v27{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 13px}
.taxonomy-kpis-v27 .tax-kpi{border:1px solid #dbe5ef;border-radius:12px;background:#fff;box-shadow:0 2px 11px #1d39550a;padding:13px 17px;min-width:0}
.taxonomy-kpis-v27 .tax-kpi-label{font-size:12px;font-weight:750;color:#50617a}
.taxonomy-kpis-v27 .tax-kpi-number{font-size:26px;font-weight:790;letter-spacing:-.6px;color:#193658;line-height:1.2;margin-top:6px}
.taxonomy-kpis-v27 .tax-kpi-number small{font-size:13px;font-weight:650;color:#587187;letter-spacing:0}
.taxonomy-kpis-v27 .tax-kpi-note{display:block;color:#65788f;font-size:11px;margin-top:4px;line-height:1.4}
.taxonomy-kpis-v27 .tax-kpi-bar{height:6px;border-radius:10px;background:#e6edf4;overflow:hidden;margin-top:10px}
.taxonomy-kpis-v27 .tax-kpi-fill{height:100%;width:0;background:#2a7c95;border-radius:10px;transition:width .25s ease}
.taxonomy-kpis-v27 .tax-kpi-unmapped .tax-kpi-number{color:#925821}
@media(max-width:900px){.taxonomy-kpis-v27{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-bottom:11px}.taxonomy-kpis-v27 .tax-kpi{padding:11px 10px}.taxonomy-kpis-v27 .tax-kpi-number{font-size:22px}.taxonomy-kpis-v27 .tax-kpi:last-child{grid-column:1/-1}}
@media(max-width:370px){.taxonomy-kpis-v27 .tax-kpi-number{font-size:20px}}
'''

HTML = '''<section class="taxonomy-kpis-v27" id="taxonomyKpisV27" aria-label="Pokrok kategorizace podle e-shopů">
 <div class="tax-kpi"><div class="tax-kpi-label">Kategorie přiřazené dle e-shopů</div><div class="tax-kpi-number" id="taxKpiMapped">—</div><span class="tax-kpi-note" id="taxKpiCoverage">Čekám na data kategorií</span><div class="tax-kpi-bar" role="progressbar" id="taxKpiProgress" aria-label="Podíl výrobků s přiřazenou kategorií" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="tax-kpi-fill" id="taxKpiBar"></div></div></div>
 <div class="tax-kpi"><div class="tax-kpi-label">Plně ověřené kategorie</div><div class="tax-kpi-number" id="taxKpiVerified">—</div><span class="tax-kpi-note">Shoda kategorie e-shopu i sledovaného pravidla</span></div>
 <div class="tax-kpi tax-kpi-unmapped"><div class="tax-kpi-label">Bez přiřazené kategorie</div><div class="tax-kpi-number" id="taxKpiUnmapped">—</div><span class="tax-kpi-note" id="taxKpiReview">Výrobky zůstávají v katalogu ke kontrole</span></div>
</section>
'''

JS = '''function renderTaxonomyKpisV27(){
 const fields=['taxKpiMapped','taxKpiVerified','taxKpiUnmapped'];
 const rows=db.items||[];
 // If the separate trusted retailer overlay failed, never show a false zero.
 const ready=rows.length>0 && rows.every(p=>p.category_v27 && typeof p.category_v27==='object');
 const fill=$('taxKpiBar'),bar=$('taxKpiProgress');
 if(!ready){
  for(const id of fields)$(id).textContent='—';
  $('taxKpiCoverage').textContent='Ověření kategorií není dostupné';
  $('taxKpiReview').textContent='Ceny i produkty zůstávají zachované';
  fill.style.width='0%';bar.removeAttribute('aria-valuenow');
  return;
 }
 const mapped=rows.filter(p=>Boolean(p.category_v27.category)).length;
 const verified=rows.filter(p=>p.category_v27.status==='verified').length;
 const missing=rows.length-mapped,review=rows.length-verified;
 const pct=Math.round(mapped*1000/rows.length)/10;
 $('taxKpiMapped').textContent=nf(mapped);
 $('taxKpiVerified').textContent=nf(verified);
 $('taxKpiUnmapped').textContent=nf(missing);
 $('taxKpiCoverage').textContent=pct.toLocaleString('cs-CZ',{maximumFractionDigits:1})+' % z '+nf(rows.length)+' výrobků';
 $('taxKpiReview').textContent=nf(review)+' k ověření včetně neshod; výrobky zůstávají v katalogu';
 fill.style.width=pct+'%';bar.setAttribute('aria-valuenow',String(pct));
}
'''


def replace_once(s: str, before: str, after: str, what: str) -> str:
    count=s.count(before)
    if count!=1:
        raise ValueError(f'{what}: expected exactly one anchor; found {count}')
    return s.replace(before,after,1)


def patch_html(source: str) -> str:
    if SENTINEL in source:
        if source.count(SENTINEL)!=1 or 'function renderTaxonomyKpisV27(){' not in source:
            raise ValueError('Partially patched HTML: refusing to modify')
        return source   # Re-runs are deliberately idempotent.
    expected = ('id="mobileCards"', '<option value="30">', '<option value="40">',
                'id="taxonomyV27Status"', 'id="categoryStatus"', 'id="nProducts"')
    for token in expected:
        if token not in source:
            raise ValueError('Missing supported published-page marker: '+token)
    out=source
    out=replace_once(out,ANCHORS['css'],CSS+ANCHORS['css'],'css')
    out=replace_once(out,ANCHORS['quick'],HTML+ANCHORS['quick'],'KPI container')
    out=replace_once(out,ANCHORS['function'],JS+ANCHORS['function'],'KPI function')
    out=replace_once(out,ANCHORS['loader'],'await loadCategoryOverlay();renderTaxonomyKpisV27();rules=new Map(', 'KPI invocation')
    if not all(marker in out for marker in ('id="mobileCards"','id="nProducts"','id="nPrices"',
                                            '<option value="30">','<option value="40">')):
        raise AssertionError('A pre-existing feature vanished')
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('html',type=Path,help='Existing published docs/catalog.html; modifies this HTML only')
    args=ap.parse_args()
    source=args.html.read_text(encoding='utf-8')
    out=patch_html(source)
    if out!=source:
        args.html.write_text(out,encoding='utf-8')
    print('v27 UAT13 KPI:', 'patched' if out!=source else 'already installed')

if __name__=='__main__':main()
