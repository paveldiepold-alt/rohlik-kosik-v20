"""Regression sample of all 46 distinct stored merchant paths in the real v26.

Expected review cases are deliberately conservative. This is not proof of
merchant availability or full 1090-product online category verification.
"""
import json
import unittest
from pathlib import Path
from catalog_v27 import merchant_category

FIXTURE = Path(__file__).parent / 'fixtures' / 'merchant_paths_v26_20261021.json'

class RealMerchantPaths(unittest.TestCase):
    def test_all_46_distinct_observed_paths_and_215_products(self):
        records = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.assertEqual(len(records), 46)
        self.assertEqual(sum(count for _,_,_,count in records),215)
        weighted = {'mapped':0, 'needs_review':0}
        for store, raw, expected, count in records:
            # There are NBSPs in the live Košík paths; normalization must match.
            item = {'store':store,'store_category_path':raw.split(' > '),
                    'category_source':'jsonld_breadcrumb'}
            actual, _ = merchant_category(item)
            with self.subTest(store=store,path=raw):
                self.assertEqual(actual, expected)
            weighted['mapped' if actual else 'needs_review'] += count
        self.assertEqual(weighted, {'mapped':208, 'needs_review':7})

if __name__ == '__main__': unittest.main()
