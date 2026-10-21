"""Deployability checks for the single safe workflow on the GitHub default branch."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
YML=ROOT/'.github/workflows/taxonomy_v27_bootstrap.yml'


class BootstrapUat(unittest.TestCase):
    def test_default_branch_dispatch_reads_latest_v26_and_does_not_push_production(self):
        y=YML.read_text(encoding='utf8')
        self.assertIn('workflow_dispatch:',y)
        self.assertIn('branches: [main]',y)
        self.assertIn('permissions:\n  contents: write',y)
        self.assertIn('git show origin/fix/real-product-price-reading-v20:docs/data/catalog_latest.json',y)
        self.assertIn('git show origin/fix/real-product-price-reading-v20:store_taxonomy.py',y)
        self.assertIn("sys.path.insert(0,'.v27-run/deps')",y)
        self.assertIn('refs/heads/${BRANCH}',y)
        self.assertIn('cp .v27-run/staging.json .v27-out/v27-results/catalog_v27_staging.json',y)
        self.assertIn('test -z "$(git status --porcelain -- docs/data/catalog_latest.json docs/catalog.html)"',y)
        self.assertNotIn('git push origin HEAD:fix/real-product-price-reading-v20',y)
        self.assertNotIn('git add docs/data/catalog_latest.json',y)
        self.assertNotIn('git add docs/catalog.html',y)

    def test_no_network_zero_limit_full_probe_and_compile(self):
        sample={'schema':'v26','rules':[{'id':'W037','category':'Ovoce'}],
                'items':[{'store':'Košík','url':'https://www.kosik.cz/p123456-avokado',
                          'name':'Avokádo','rule_ids':['W037'],'price_status':'ok',
                          'price_czk':42.9,'checked_at':'2026-10-21T18:00:00+00:00'}]}
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); source=d/'source.json'
            source.write_text(json.dumps(sample,ensure_ascii=False),encoding='utf8')
            original=source.read_bytes()
            stage=d/'stage.json';report=d/'probe.json';view=d/'view.json'
            review=d/'review.json';audit=d/'audit.json';path_review=d/'paths.json'
            commands=[
                [sys.executable,str(ROOT/'taxonomy_probe_v27.py'),'--input',str(source),
                 '--staging',str(stage),'--report',str(report),'--limit','0'],
                [sys.executable,str(ROOT/'catalog_v27.py'),'--input',str(stage),
                 '--output',str(view),'--review',str(review),'--audit',str(audit),
                 '--path-review',str(path_review)]
            ]
            for cmd in commands:
                result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(json.loads(stage.read_text())['items'][0]['price_czk'],42.9)
            self.assertEqual(json.loads(view.read_text())['items'][0]['price_czk'],42.9)
            self.assertEqual(json.loads(audit.read_text())['products_after'],1)
            self.assertEqual(json.loads(report.read_text())['attempted'],0)

if __name__=='__main__':unittest.main()
