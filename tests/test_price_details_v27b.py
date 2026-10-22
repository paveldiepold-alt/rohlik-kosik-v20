"""UAT10 regression tests for verified discount UI and price-block fallback."""
from __future__ import annotations
import unittest
from unittest.mock import patch
import types
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import patch_sale_filters_v27 as filters
from price_details_v27b import detail_price, improved_observation


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.html = '<select id="state">'+filters.BEFORE_OPTIONS+'</select><div id="mobileCards"></div>' \
                    + '<script>if('+filters.BEFORE_LOGIC+'){};fetch("./data/catalog_latest.json?ts=")</script>'

    def test_30_and_40_values_present(self):
        result=filters.patch(self.html)
        self.assertIn('<option value="30">Sleva alespoň 30 %</option>',result)
        self.assertIn('<option value="40">Sleva alespoň 40 %</option>',result)
        self.assertIn('active(p)&&reduction>=Number(f.state)',result)

    def test_idempotent(self):
        once=filters.patch(self.html)
        self.assertEqual(once,filters.patch(once))

    def test_no_nonexistent_anchor(self):
        with self.assertRaises(ValueError): filters.patch('<html><script>x</script></html>')

    def test_mobile_and_catalog_read_still_present(self):
        result=filters.patch(self.html)
        self.assertEqual(result.count('id="mobileCards"'),1)
        self.assertIn('catalog_latest.json',result)


class RohlíkHeaderPriceTests(unittest.TestCase):
    def test_citron_approximate_split_with_perkg(self):
        self.assertEqual(detail_price('cca 210 g 79,90 Kč/kg\ncca 17\n12 Kč\nDo košíku')[0],17.12)

    def test_chicken_approximate_split_and_shelf_life(self):
        self.assertEqual(detail_price('cca 270 g 259,90 Kč/kg\nBĚŽNĚ ČERSTVÉ 4 DNY\ncca 70\n17 Kč\nDo košíku')[0],70.17)

    def test_persil_unit_per_wash_and_price(self):
        self.assertEqual(detail_price('22 praní 4,54 Kč/praní\n99\n90 Kč\nNabídka do 31. 8.\nDo košíku')[0],99.90)

    def test_decimal_price(self):
        self.assertEqual(detail_price('500 g\n69,90 Kč\nDo košíku')[0],69.90)

    def test_whole_price(self):
        self.assertEqual(detail_price('Sýr\n30 Kč\nDo košíku')[0],30.0)

    def test_only_unit_price_rejected(self):
        self.assertIsNone(detail_price('cca 250 g 199,90 Kč/kg\nDo košíku')[0])

    def test_multiple_competing_prices_rejected(self):
        self.assertIsNone(detail_price('cca 17 12 Kč\n19,90 Kč\nDo košíku')[0])

    def test_explicitly_old_price_is_not_current(self):
        self.assertEqual(detail_price('cca 17 12 Kč\nPůvodní cena 19,90 Kč\nDo košíku')[0],17.12)
        self.assertIsNone(detail_price('Původní cena 19,90 Kč\nDo košíku')[0])

    def test_product_recommendation_price_excluded(self):
        self.assertEqual(detail_price('99 90 Kč\nDo košíku\nOblíbené 49,90 Kč')[0],99.90)

    def test_multibuy_rejected(self):
        self.assertIsNone(detail_price('99 90 Kč od 2 ks\nDo košíku')[0])

    def test_missing_amount_rejected(self):
        self.assertIsNone(detail_price('Skladem 5 ks\nDo košíku')[0])

    def test_price_above_pilot_cap_rejected(self):
        self.assertIsNone(detail_price('1999 90 Kč\nDo košíku')[0])

    def test_no_guesses_from_weights(self):
        self.assertIsNone(detail_price('cca 540 g\n159,90 Kč/kg')[0])

    def test_invalid_input(self):
        self.assertIsNone(detail_price(None)[0])



class FallbackSafetyTests(unittest.TestCase):
    def _run(self, shop, original_status, payload):
        original={'status':original_status,'price':None,'blocked':False,'note':'old reader'}
        maintenance=types.ModuleType('maintenance_v26')
        maintenance.inspect_saved=lambda page, row: original
        monitor=types.ModuleType('monitor')
        monitor.valid_title=lambda title,entry: title == 'Citron 1 ks' and entry.get('label') == 'Citron 1 ks'
        class Page:
            def evaluate(self, expression):return payload
        with patch.dict(sys.modules,{'maintenance_v26':maintenance,'monitor':monitor}):
            return improved_observation(Page(),{'store':shop,'name':'Citron 1 ks'})

    def test_fallback_when_previous_price_ambiguous_and_own_block_verified(self):
        output=self._run('Rohlík','price_unverified',
           {'bounded':True,'title':'Citron 1 ks','text':'cca 210 g 79,90 Kč/kg\ncca 17 12 Kč'})
        self.assertEqual(output['status'],'ok')
        self.assertEqual(output['price'],17.12)

    def test_identity_mismatch_prevents_publication(self):
        output=self._run('Rohlík','price_unverified',
           {'bounded':True,'title':'Jiný výrobek','text':'99 90 Kč'})
        self.assertEqual(output['status'],'price_unverified')

    def test_without_cart_boundary_not_accepted(self):
        output=self._run('Rohlík','price_unverified',
           {'bounded':False,'title':'Citron 1 ks','text':'99 90 Kč'})
        self.assertEqual(output['status'],'price_unverified')

    def test_preserves_already_verified_and_other_shop(self):
        output=self._run('Rohlík','ok',{'bounded':True,'title':'Citron 1 ks','text':'99 90 Kč'})
        self.assertEqual(output['status'],'ok')
        output=self._run('Košík','price_unverified',{'bounded':True,'title':'Citron 1 ks','text':'99 90 Kč'})
        self.assertEqual(output['status'],'price_unverified')

if __name__ == '__main__':
    unittest.main()
