import copy
import unittest
from price_probe_v27 import choose_products, categorize, sanitize_report_row, report_summary
from pathlib import Path


def prod(store, status, http=None, id=1, price=None):
    host = 'www.rohlik.cz' if store == 'Rohlík' else 'www.kosik.cz'
    return {'store': store, 'url': f'https://{host}/{123456+id}' if store == 'Rohlík' else f'https://{host}/p{123456+id}',
            'name': 'Test', 'price_status': status, 'price_czk': price, 'http_status': http}

class PriceProbeTests(unittest.TestCase):
    def test_chooses_both_shops_and_categories_of_price_failure(self):
        source = [prod('Rohlík','http_error',429,id=i) for i in range(8)] + [
          prod('Rohlík','price_unverified',200,id=i+20) for i in range(4)] + [
          prod('Košík','price_unverified',200,id=40),
          prod('Rohlík','ok',200,id=50,price=19.9),
          prod('Košík','ok',200,id=60,price=29.9)]
        snapshot = copy.deepcopy(source)
        chosen = choose_products(source, 11)
        self.assertEqual(len(chosen),11)
        self.assertEqual(len({(x['store'],x['url']) for x in chosen}),11)
        self.assertIn(('Košík','price_unverified'),[(x['store'],x['price_status']) for x in chosen])
        self.assertIn(('Rohlík','ok'),[(x['store'],x['price_status']) for x in chosen])
        self.assertEqual(source,snapshot)

    def test_deploy_uses_verified_v26_parser_and_read_only_permissions(self):
        root=Path(__file__).resolve().parents[1]
        code=(root/'price_probe_v27.py').read_text(encoding='utf8')
        workflow=(root/'.github/workflows/price_probe_v27_readonly.yml').read_text(encoding='utf8')
        self.assertIn("sys.path.insert(0, str(deps.resolve()))",code)
        self.assertIn('persist-credentials: false',workflow)
        self.assertIn('contents: read',workflow)
        self.assertIn('workflow_dispatch:',workflow)
        self.assertNotIn('git push',workflow)
        self.assertIn('git show origin/fix/real-product-price-reading-v20:docs/data/catalog_latest.json',workflow)

    def test_bounded_target_count(self):
        with self.assertRaises(ValueError): choose_products([], 26)
        with self.assertRaises(ValueError): choose_products([], 0)

    def test_price_candidate_only_if_verified(self):
        row=prod('Rohlík','http_error',429)
        bad=sanitize_report_row(row, {'status':'http_error','http_status':429,'price_czk':None})
        self.assertEqual(bad['result'],'blocked_429')
        self.assertIsNone(bad['new_price_candidate_czk'])
        good=sanitize_report_row(row, {'status':'ok','http_status':200,'price_czk':99.8,'source':'visible'})
        self.assertEqual(good['new_price_candidate_czk'],99.8)
        self.assertEqual(row['price_status'],'http_error')

    def test_ambiguous_never_guessed(self):
        self.assertEqual(categorize({'status':'price_unverified','http_status':200}), 'ambiguous_or_missing_price')
        self.assertEqual(categorize({'status':'title_mismatch','http_status':200}), 'title_mismatch')
        self.assertEqual(categorize({'status':'http_error','http_status':403}), 'shop_unavailable')

    def test_report_never_rewrites_price_evidence(self):
        old={'generated_at':'2026-10-21','items':[prod('Rohlík','http_error',429),prod('Košík','ok',200,2,49.9)]}
        original=copy.deepcopy(old)
        obs=[sanitize_report_row(old['items'][0], {'status':'ok','price_czk':30.0,'http_status':200})]
        report=report_summary(old,obs,[],set(),'abc')
        self.assertEqual((report['catalog_products'],report['catalog_priced_before'],report['catalog_missing_before']),(2,1,1))
        self.assertEqual(report['candidate_prices_observed_but_not_written'],1)
        self.assertEqual(old,original)

if __name__ == '__main__': unittest.main()
