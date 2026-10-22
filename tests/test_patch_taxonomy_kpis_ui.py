import unittest
from patch_taxonomy_kpis_v27 import patch_html

BASE='''<!doctype html><html lang="cs"><head><style>\n.stats{}\n</style>\n</head><body>
<section class="stats" aria-label="Přehled"><div id="nProducts"></div><div id="nPrices"></div></section>
<div class="quick" aria-label="Rychlé zobrazení"></div>
<div id="mobileCards"></div><div id="taxonomyV27Status"></div><select id="categoryStatus"></select>
<select><option value="30">30</option><option value="40">40</option></select>
<script>let db={items:[]};function nf(v){return String(v)};function $(v){return document.getElementById(v)};
async function loadCategoryOverlay(){}
async function load(){await loadCategoryOverlay();rules=new Map([])}
</script></body></html>'''

class PatchTests(unittest.TestCase):
    def test_adds_three_cards(self):
        page=patch_html(BASE)
        for token in ['id="taxKpiMapped"','id="taxKpiVerified"','id="taxKpiUnmapped"','id="taxKpiProgress"']:
            self.assertIn(token,page)
        self.assertIn('renderTaxonomyKpisV27();rules=new Map(',page)
    def test_preserves_existing_features(self):
        page=patch_html(BASE)
        for token in ['id="mobileCards"','id="nProducts"','id="nPrices"','<option value="30">','<option value="40">']:
            self.assertEqual(BASE.count(token),page.count(token))
    def test_idempotent(self):
        once=patch_html(BASE)
        self.assertEqual(patch_html(once),once)
    def test_fail_closed_missing_overlay(self):
        with self.assertRaisesRegex(ValueError,'marker'):
            patch_html(BASE.replace('id="taxonomyV27Status"','id="old"'))
    def test_fail_closed_changed_invocation(self):
        with self.assertRaisesRegex(ValueError,'KPI invocation'):
            patch_html(BASE.replace('await loadCategoryOverlay();rules=new Map(', 'await loadCategoryOverlay();something();rules=new Map('))
    def test_overlay_failure_does_not_claim_zero(self):
        out=patch_html(BASE)
        self.assertIn("$(id).textContent='—'",out)
        self.assertIn('Ověření kategorií není dostupné',out)
    def test_category_metrics_derived_from_live_data(self):
        out=patch_html(BASE)
        for snippet in ['rows.filter(p=>Boolean(p.category_v27.category)).length',
                        "rows.filter(p=>p.category_v27.status==='verified').length",'const missing=rows.length-mapped']:
            self.assertIn(snippet,out)

if __name__=='__main__':unittest.main()
