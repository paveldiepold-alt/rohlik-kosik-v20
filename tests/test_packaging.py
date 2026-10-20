import json
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

class PackageTests(unittest.TestCase):
    def test_required_files(self):
        for path in ('watchlist.json','monitor.py','docs/index.html','.github/workflows/monitor.yml'):
            self.assertTrue((ROOT/path).is_file(), path)

    def test_watchlist_product_urls(self):
        w = json.loads((ROOT/'watchlist.json').read_text(encoding='utf-8'))
        products = w['specific_products']
        self.assertGreaterEqual(len(w['watch_rules']), 70)
        self.assertEqual(len(products), 10)
        self.assertEqual(len(products), len({p['id'] for p in products}))
        for entry in products:
            self.assertIn(urlparse(entry['url']).hostname, ('www.rohlik.cz','www.kosik.cz'))
            self.assertEqual(urlparse(entry['url']).scheme, 'https')

    def test_no_embedded_fake_results(self):
        self.assertFalse((ROOT/'docs/data/latest.json').exists())
        self.assertFalse((ROOT/'docs/data/history.json').exists())

    def test_workflow_no_pages_dependency(self):
        yml = (ROOT/'.github/workflows/monitor.yml').read_text(encoding='utf-8')
        self.assertNotIn('environment:', yml)
        self.assertNotIn('deploy-pages', yml)
        self.assertIn('python monitor.py', yml)
        self.assertIn('upload-artifact@v4', yml)
        self.assertIn('workflow_dispatch:', yml)
        self.assertNotIn('  schedule:', yml)

if __name__ == '__main__':
    unittest.main()
