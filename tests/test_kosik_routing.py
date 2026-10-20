import unittest
from visible_price import choose_kosik_detail_price, choose_visible_price, parse_display_price
from monitor import from_browser_payload, pilot_acceptance

class KosikRenderedTextTests(unittest.TestCase):
    def test_multibuy_but_single_unit_price(self):
        block = """30 g
Multikup – množstevní sleva
15,90 Kč
-20 %
od 4 ks
17,90 Kč
-10 %
od 2 ks
19 90
663,33 Kč/kg
"""
        value, source, note = choose_kosik_detail_price(block)
        self.assertEqual(value, 19.9)
        self.assertEqual(source, 'kosik-product-text')
        self.assertIn('1 ks', note)

    def test_split_dom_crowns_and_cents_with_unit_corroboration(self):
        block = "30 g\n19\n90\n663,33 Kč/kg"
        self.assertEqual(choose_kosik_detail_price(block)[0],19.9)

    def test_ordinary_discount_and_struck_price_not_confused(self):
        block = """30 g
14 90
19,90 Kč
-25 % do 22. 9.
496,67 Kč/kg
Do košíku
"""
        value, source, note = choose_kosik_detail_price(block)
        self.assertEqual(value, 14.9)

    def test_empty_or_multibuy_only_is_unverified(self):
        self.assertIsNone(choose_kosik_detail_price('')[0])
        self.assertIsNone(choose_kosik_detail_price('15,90 Kč\nod 4 ks')[0])

    def test_rohlik_current_and_old_not_conflict(self):
        rows = [
            {'text':'14990 Kč 169,90 Kč* * Doporučená cena', 'hint':'product-detail-price-section', 'distance':104, 'old':False,'unit':False,'detail':True},
            {'text':'149,90 Kč', 'hint':'product-detail-price-section-price', 'distance':112, 'old':False,'unit':False,'detail':True},
            {'text':'149,90 Kč', 'hint':'font-bold', 'distance':112, 'old':False,'unit':False,'detail':True},
            {'text':'169,90 Kč*', 'hint':'line-through', 'distance':104, 'old':True,'unit':False,'detail':True},
        ]
        self.assertEqual(choose_visible_price(rows)[0],149.9)

    def test_fallback_only_for_kosik_and_not_structured_wrong(self):
        payload={'visible_prices':[],'detail_text':'30 g\n19 90\n663,33 Kč/kg','jsonld':[],'meta':[]}
        self.assertEqual(from_browser_payload(payload,'Košík')[:2],(19.9,'kosik-product-text'))
        self.assertIsNone(from_browser_payload(payload,'Rohlík')[0])

    def test_one_of_ten_must_be_failure_not_green(self):
        rows = [{'store':'Rohlík', 'status':'ok','price_czk':63.9}]
        rows += [{'store':'Košík','status':'price_unverified', 'price_czk':None} for _ in range(9)]
        self.assertFalse(pilot_acceptance({'items':rows})[0])

    def test_both_shops_and_enough_prices_pass(self):
        rows = [{'store':'Rohlík','status':'ok','price_czk':i+30} for i in range(3)]
        rows += [{'store':'Košík','status':'ok','price_czk':i+20} for i in range(3)]
        rows += [{'store':'Košík','status':'price_unverified','price_czk':None} for _ in range(4)]
        self.assertTrue(pilot_acceptance({'items':rows})[0])

    def test_even_six_prices_one_store_not_enough(self):
        rows = [{'store':'Rohlík','status':'ok','price_czk':i+30} for i in range(6)]
        rows += [{'store':'Košík','status':'price_unverified','price_czk':None} for _ in range(4)]
        self.assertFalse(pilot_acceptance({'items':rows})[0])

    def test_random_shipping_is_never_price(self):
        value,_,_=choose_kosik_detail_price('Doprava 99 Kč\nRegistrace\n')
        self.assertIsNone(value)

if __name__=='__main__': unittest.main()
