"""Regression tests for the executable CLI and safe v26 -> v27 workflow.

Unit-level classification tests cannot detect a broken CLI argument gate. These
checks execute the actual program and assert the v26 input is byte-preserved.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / 'catalog_v27.py'
PROBE_YML = ROOT / '.github/workflows/taxonomy_v27_bootstrap.yml'


class CliAndWorkflow(unittest.TestCase):
    def sample(self):
        return {
            'schema': 'rk-v20-catalog-1',
            'generated_at': '2026-10-21T14:12:55+00:00',
            'catalog_marker': {'must_remain': True},
            'rules': [{'id': 'W037', 'category': 'Ovoce'},
                      {'id': 'W001', 'category': 'Maso'},
                      {'id': 'W033', 'category': 'Nápoje / vody'}],
            'items': [
                {'store': 'Košík', 'url': 'https://www.kosik.cz/p1001-a',
                 'name': 'Avokádo', 'rule_ids': ['W037'],
                 'store_category_path': ['Ovoce a zelenina', 'Ovoce', 'Avokádo'],
                 'category_source': 'jsonld_breadcrumb',
                 'price_status': 'ok', 'price_czk': 41.9, 'checked_at': '2026-10-20',
                 'legacy_price_czk': 53.2, 'discount_pct': 12.5},
                {'store': 'Rohlík', 'url': 'https://www.rohlik.cz/1002-b',
                 'name': 'Kuřecí stehno', 'rule_ids': ['W001'],
                 'price_status': 'http_error', 'price_czk': None, 'http_status': 429},
                {'store': 'Košík', 'url': 'https://www.kosik.cz/p1003-c',
                 'name': 'Ovšem ne ovoce', 'rule_ids': ['W037'],
                 'store_category_path': ['Drogerie a kosmetika', 'Mytí nádobí'],
                 'category_source': 'dom_breadcrumb',
                 'price_status': 'ok', 'price_czk': 129.9, 'checked_at': '2026-10-20'},
            ],
        }

    def test_real_cli_produces_all_four_outputs_and_preserves_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            src = folder/'source.json'
            destinations = [folder/f'v27_{i}.json' for i in range(4)]
            src.write_text(json.dumps(self.sample(), ensure_ascii=False), encoding='utf-8')
            original_bytes = src.read_bytes()
            process = subprocess.run([sys.executable, str(GENERATOR),
                '--input', str(src), '--output', str(destinations[0]),
                '--review', str(destinations[1]), '--audit', str(destinations[2]),
                '--path-review', str(destinations[3])],
                capture_output=True, text=True, cwd=str(folder), timeout=12)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(src.read_bytes(), original_bytes)
            self.assertTrue(all(p.exists() for p in destinations))
            preview = json.loads(destinations[0].read_text(encoding='utf-8'))
            review = json.loads(destinations[1].read_text(encoding='utf-8'))
            audit = json.loads(destinations[2].read_text(encoding='utf-8'))
            self.assertEqual(audit['products_after'], 3)
            self.assertEqual((audit['priced_before'],audit['priced_after']),(2,2))
            self.assertEqual(audit['missing_prices'], 1)
            self.assertEqual(audit['rules_with_products'], 2)
            self.assertEqual(audit['rules_configured'], 3)
            self.assertEqual([x['id'] for x in audit['rules_without_products']], ['W033'])
            self.assertEqual(preview['items'][0]['legacy_price_czk'], 53.2)
            self.assertEqual(preview['items'][2]['price_czk'], 129.9)
            self.assertEqual(preview['items'][2]['category_v27']['status'], 'mismatch')
            self.assertEqual(review['count'], 2)

    def test_cli_rejects_any_output_colliding_with_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/'source.json'
            src.write_text(json.dumps(self.sample()), encoding='utf-8')
            original_bytes = src.read_bytes()
            process = subprocess.run([sys.executable, str(GENERATOR),
                '--input', str(src), '--output', str(src)],
                capture_output=True, text=True, timeout=12)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(src.read_bytes(), original_bytes)

    def test_probe_fetches_current_v26_from_its_own_branch(self):
        yml = PROBE_YML.read_text(encoding='utf-8')
        self.assertIn('refs/heads/fix/real-product-price-reading-v20', yml)
        self.assertIn('git show origin/fix/real-product-price-reading-v20:docs/data/catalog_latest.json', yml)
        self.assertIn('taxonomy_probe_v27.py', yml)
        self.assertIn('assert len(items)>=1090', yml)
        self.assertIn('test -z "$(git status --porcelain -- docs/data/catalog_latest.json docs/catalog.html)"', yml)
        self.assertNotIn('git add docs/data/catalog_latest.json', yml)
        self.assertNotIn('git push origin HEAD:fix/real-product-price-reading-v20', yml)

if __name__ == '__main__':
    unittest.main()
