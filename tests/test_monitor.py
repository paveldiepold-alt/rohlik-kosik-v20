import json
import unittest
from monitor import as_money, choose_price, valid_title, extract_jsonld_prices, from_browser_payload, make_report


class MonitorTests(unittest.TestCase):
    def test_money(self):
        self.assertEqual(as_money('74,90'), 74.9)
        self.assertIsNone(as_money('od 74,90 Kč'))
        self.assertIsNone(as_money('-10 %'))

    def test_structured_product_only(self):
        raw = json.dumps({'@graph': [{'@type': 'WebPage', 'offers': {'price': '999'}},
                                     {'@type': 'Product', 'offers': {'price': '74.90', 'priceCurrency': 'CZK'}}]})
        self.assertEqual(choose_price(extract_jsonld_prices(raw))[0], 74.9)

    def test_conflicting_prices_not_guessed(self):
        cands = [{'source': 'product-jsonld', 'price': '25', 'currency': 'CZK'},
                 {'source': 'product-meta', 'price': '50', 'currency': 'CZK'}]
        self.assertIsNone(choose_price(cands)[0])

    def test_foreign_currency_rejected(self):
        self.assertIsNone(choose_price([{'source': 'product-jsonld', 'price': '20', 'currency': 'EUR'}])[0])

    def test_product_title_guard(self):
        entry = {'label': 'Zewa Deluxe Standard kapesníky', 'brand': 'Zewa'}
        self.assertTrue(valid_title('Zewa Deluxe Standard 10x10 ks', entry))
        self.assertFalse(valid_title('Přihlášení ke Košíku', entry))

    def test_empty_or_unknown_report(self):
        row = {'id': 'x', 'store': 'Košík', 'price_czk': None, 'status': 'price_unverified'}
        rep = make_report([row], {}, '2026-10-19T08:00:00Z')
        self.assertEqual(rep['verified_price_count'], 0)
        self.assertEqual(rep['status'], 'partial_or_unverified')

    def test_real_price_drop_only(self):
        row = {'id': 'x', 'store': 'Rohlík', 'price_czk': 80.0, 'status': 'ok'}
        old = {'items': [{'id': 'x', 'price_czk': 100.0, 'status': 'ok'}]}
        rep = make_report([row], old, '2026-10-19T08:00:00Z')
        self.assertEqual(rep['items'][0]['drop_since_previous_pct'], 20.0)
        self.assertEqual(rep['verified_price_count'], 1)

    def test_no_drop_when_unverified(self):
        row = {'id': 'x', 'store': 'Rohlík', 'price_czk': None, 'status': 'price_unverified'}
        old = {'items': [{'id': 'x', 'price_czk': 100.0, 'status': 'ok'}]}
        self.assertIsNone(make_report([row], old, 'now')['items'][0]['drop_since_previous_pct'])

    def test_nested_graph(self):
        data = {'@graph': [{'@type': 'Product', 'offers': [{'price': 120, 'priceCurrency': 'CZK'}]}]}
        self.assertEqual(from_browser_payload({'jsonld': [json.dumps(data)], 'meta': []})[0], 120.0)


if __name__ == '__main__':
    unittest.main()
