import unittest
from visible_price import parse_display_price, choose_visible_price, VISIBLE_PRICE_JS
from monitor import from_browser_payload


def visible(text, hint='product-price current', distance=150, **extra):
    return {'text':text, 'hint':hint, 'distance':distance, 'detail':True,
            'old':False, 'unit':False, 'contains_currency':'Kč' in text, **extra}

class VisibleProductPriceTests(unittest.TestCase):
    def test_czech_and_superscript_price(self):
        for v in ('74,90 Kč', '74.90 Kč', '74\n90 Kč','74 90 Kč', '74 90', '74,90'):
            self.assertEqual(parse_display_price(v), 74.9, v)

    def test_reject_unit_price_and_discount(self):
        for v in ('119,84 Kč/l', '4,69 Kč/ks', '-42 %', 'doprava 99 Kč'):
            self.assertIsNone(parse_display_price(v), v)

    def test_current_vs_struck_old_price(self):
        items = [visible('74 90 Kč'), {**visible('129,90 Kč','old-price'), 'old': True}]
        self.assertEqual(choose_visible_price(items)[0], 74.90)

    def test_conflicting_current_prices_not_guessed(self):
        p, src, msg = choose_visible_price([visible('74,90 Kč'), visible('46,90 Kč')])
        self.assertIsNone(p)
        self.assertIn('Více', msg)

    def test_scope_and_confidence(self):
        p,_,_=choose_visible_price([visible('1 999,90 Kč',distance=720), visible('74,90 Kč')])
        self.assertEqual(p,74.9)
        p,_,_=choose_visible_price([{**visible('74,90 Kč'), 'detail':False}])
        self.assertIsNone(p)

    def test_prefers_visible_product_price_to_old_structured(self):
        payload = {'visible_prices':[visible('46,90 Kč')],
                   'jsonld':['{"@type":"Product","offers":{"price":"63.90","priceCurrency":"CZK"}}'],
                   'meta': []}
        self.assertEqual(from_browser_payload(payload)[:2], (46.9, 'visible-product-detail'))

    def test_quantity_condition_exposed(self):
        p, src, note = choose_visible_price([visible('39 90 Kč',condition='Podmínka: od 2 ks')])
        self.assertEqual(p, 39.9)
        self.assertIn('od 2 ks',note)

    def test_structured_fallback_still_supported(self):
        payload = {'visible_prices':[],
                   'jsonld':['{"@type":"Product","offers":{"price":"63.90","priceCurrency":"CZK"}}'],
                   'meta': []}
        self.assertEqual(from_browser_payload(payload)[0],63.9)

    def test_js_is_complete_and_product_scoped(self):
        self.assertIn("document.querySelector('h1')",VISIBLE_PRICE_JS)
        self.assertIn('getBoundingClientRect',VISIBLE_PRICE_JS)
        self.assertIn('return out;',VISIBLE_PRICE_JS)

if __name__=='__main__': unittest.main()


from monitor import plausible_pilot_price, sanitize_history, make_report

class TestPriceRegressions(unittest.TestCase):
    def test_6390_from_tissues_is_not_accepted(self):
        self.assertFalse(plausible_pilot_price(6390))
        self.assertTrue(plausible_pilot_price(63.90))
        self.assertTrue(plausible_pilot_price(169.9))

    def test_suspicious_history_removed_for_pilot_only(self):
        sample = [{'id':'zewa', 'price_czk':6390, 'store':'Rohlík'},
                  {'id':'zewa','price_czk':63.9,'store':'Rohlík'},
                  {'id':'unknown','price_czk':6390,'store':'Rohlík'}]
        clean, removed = sanitize_history(sample, {'zewa'})
        self.assertEqual(removed, 1)
        self.assertEqual([x['price_czk'] for x in clean], [63.9,6390])

    def test_no_discount_from_bad_previous_history(self):
        previous = {'items':[{'id':'zewa', 'status':'ok', 'price_czk':6390}]}
        current = [{'id':'zewa','store':'Rohlík','status':'ok','price_czk':63.9}]
        result = make_report(current,previous,'now')
        self.assertIsNone(result['items'][0]['previous_observed_price_czk'])
        self.assertIsNone(result['items'][0]['drop_since_previous_pct'])

    def test_visible_price_avoids_other_product_and_unit(self):
        rows = [{'text':'63,90 Kč','detail':True,'old':False,'unit':False,'distance':100,'hint':'current price'},
                {'text':'119,84 Kč/l','detail':True,'old':False,'unit':True,'distance':70,'hint':'unit'},
                {'text':'9,90 Kč','detail':False,'old':False,'unit':False,'distance':80,'hint':'price'}]
        price,source,_ = choose_visible_price(rows)
        self.assertEqual(price,63.9)
        self.assertEqual(source,'visible-product-detail')

    def test_unit_prices_still_rejected(self):
        for text in ['99 Kč/kg','12,30 Kč/ks','99 Kč/l']:
            self.assertIsNone(parse_display_price(text))

