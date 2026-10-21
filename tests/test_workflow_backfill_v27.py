"""End-to-end offline simulation of a blocked retailer and alternate-shop backfill."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from taxonomy_probe_v27 import run, pick, identity


class FakeBrowser:
    def new_page(self, **kwargs):
        return SimpleNamespace(close=lambda: None)
    def close(self):
        pass


class FakeRunner:
    chromium = SimpleNamespace(launch=lambda **kwargs: FakeBrowser())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class BackfillTests(unittest.TestCase):
    def sample(self):
        items = []
        for store in ('Košík', 'Rohlík'):
            for n in range(5):
                url=(f'https://www.kosik.cz/p{700000+n}-t' if store=='Košík'
                     else f'https://www.rohlik.cz/{700000+n}-t')
                items.append({'store':store,'url':url,'name':f'Sample {n}',
                              'rule_ids':['W061'], 'price_status':'ok',
                              'price_czk':round(20+n+0.3,2),'price_source':'v26',
                              'checked_at':'2026-10-21T16:00:00+00:00'})
        return {'items':items, 'rules':[{'id':'W061','category':'Praní'}]}

    def test_pick_can_exclude_already_queued_items(self):
        catalog=self.sample()['items']
        excluded={identity(p) for p in catalog[:3]}
        result=pick(catalog,10,excluded_keys=excluded)
        self.assertEqual(len(result),7)
        self.assertFalse(any(identity(p) in excluded for p in result))

    def test_blocked_shop_refills_batch_without_rewriting_source(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            inp=p/'source.json'; stage=p/'stage.json'; report=p/'report.json'
            inp.write_text(json.dumps(self.sample(),ensure_ascii=False),encoding='utf8')
            before=inp.read_bytes()
            seen=[]
            def synthetic_probe(page, product):
                seen.append(identity(product))
                if product['store']=='Rohlík':
                    return {'status':'blocked', 'note':'HTTP 429', 'blocked':True}
                return {'status':'category_missing','note':'No verified path','blocked':False}
            # The mocked browser never accesses the network.
            fake=types.ModuleType('playwright.sync_api')
            fake.sync_playwright=lambda: FakeRunner()
            pkg=types.ModuleType('playwright')
            pkg.sync_api=fake
            with patch.dict(sys.modules,{'playwright':pkg,'playwright.sync_api':fake}), \
                 patch('taxonomy_probe_v27.probe_one',side_effect=synthetic_probe), \
                 patch('taxonomy_probe_v27.time.sleep',return_value=None):
                code=run(SimpleNamespace(input=str(inp),staging=str(stage),report=str(report),limit=6,delay=2.5))
            self.assertEqual(code,0)
            self.assertEqual(inp.read_bytes(),before)
            self.assertEqual(len(seen),len(set(seen)))
            self.assertEqual(len(seen),6)
            self.assertEqual(sum(shop=='Rohlík' for shop,_ in seen),1)
            self.assertEqual(sum(shop=='Košík' for shop,_ in seen),5)
            result=json.loads(report.read_text(encoding='utf8'))
            self.assertEqual(result['attempted'],6)
            self.assertIn('Rohlík',result['blocked_stores'])
            self.assertEqual(result['statuses']['Rohlík|blocked'],1)
            saved=json.loads(stage.read_text(encoding='utf8'))
            self.assertEqual(len(saved['items']),10)
            for orig,new in zip(self.sample()['items'],saved['items']):
                self.assertEqual(orig['price_czk'],new['price_czk'])
                self.assertEqual(orig['checked_at'],new['checked_at'])

if __name__=='__main__':unittest.main()
