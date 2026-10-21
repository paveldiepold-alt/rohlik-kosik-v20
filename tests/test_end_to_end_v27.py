"""End-to-end 1090-row offline conservation test.

The 215 known merchant-category paths are represented by a frequency fixture
captured from the v26 repository on 2026-10-21. The remaining 875 rows are
synthetic unknown-path placeholders: they are NOT newly verified retailer data.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from catalog_v27 import compile_catalog, write_json, diagnose_price
from taxonomy_probe_v27 import sync_new_prices

FIXTURE=Path(__file__).parent/'fixtures'/'merchant_paths_v26_20261021.json'

class EndToEndV27(unittest.TestCase):
    def make_catalog(self):
        known=json.loads(FIXTURE.read_text(encoding='utf8'))
        rows=[]
        for store,path,expected,count in known:
            for _ in range(count):
                j=len(rows)
                rows.append({'store':store,'url':('https://www.kosik.cz/p'+str(900000+j)
                                                      if store=='Košík' else 'https://www.rohlik.cz/'+str(900000+j)),
                             'name': 'TEST REAL-PATH-FIXTURE '+str(j),
                             'title': 'TEST REAL-PATH-FIXTURE '+str(j),
                             'rule_ids':['W001' if (expected=='Maso' or path.startswith('Maso a ryby'))
                                         else 'W037' if (expected=='Ovoce' or ('Ovoce' in path and 'Zelenina' not in path))
                                         else 'W043' if (expected=='Zelenina' or 'zelenina' in path.lower())
                                         else 'W074' if expected=='Úklid' else 'W030' if expected=='Uzeniny / šunky' else 'W034'],
                             'store_category_path':path.split(' > '),'category_source':'jsonld_breadcrumb'})
        for j in range(len(rows),1090):
            shop='Košík' if j%2 else 'Rohlík'
            rows.append({'store':shop,'url':('https://www.kosik.cz/p'+str(900000+j)
                                         if shop=='Košík' else 'https://www.rohlik.cz/'+str(900000+j)),
                         'name':'SYNTETIC UNVERIFIED '+str(j),'rule_ids':['W037']})
        assert len(rows)==1090
        for i,r in enumerate(rows):
            # Deliberate price and error distributions; these records are synthetic.
            r.update(price_czk=round(40+i/10,2) if i<894 else None,
                     price_status='ok' if i<894 else ('http_error' if i<1063 else 'price_unverified'),
                     price_source='v26_unchanged' if i<894 else None,
                     checked_at='2026-10-21T14:00:00Z',
                     multibuy=[{'min_qty':2,'price_czk':24.5}] if i%7==0 else [],
                     price_history_previous_czk=99 if i%9==0 else None,
                     original_price_czk=60 if i%13==0 else None)
            if 894<=i<1063:r['http_status']=429
            elif i>=1063:r['http_status']=200
        rules=[{'id':'W001','category':'Maso'},{'id':'W037','category':'Ovoce'},
               {'id':'W043','category':'Zelenina'},{'id':'W074','category':'Úklid'},
               {'id':'W030','category':'Uzeniny / šunky'},{'id':'W034','category':'Nápoje / vody'}]
        return {'schema':'rk-v26', 'items':rows,'rules':rules,'generated_at':'2026-10-21T14:12:55+00:00',
                'extra_nested':{'keep':'unchanged'}}

    def test_1090_rows_894_prices_full_integrity_and_evidence(self):
        old=self.make_catalog();old_copy=deepcopy(old)
        stage=sync_new_prices(old,{'items':[]})
        new,review,audit=compile_catalog(stage)
        self.assertEqual(old,old_copy)
        self.assertEqual(len(new['items']),1090)
        self.assertEqual(audit['priced_before'],894)
        self.assertEqual(audit['priced_after'],894)
        self.assertEqual(audit['missing_prices'],196)
        self.assertEqual(sum(v['total'] for v in audit['price_by_shop'].values()),1090)
        self.assertEqual(sum(v['priced'] for v in audit['price_by_shop'].values()),894)
        self.assertEqual(sum(v['missing'] for v in audit['price_by_shop'].values()),196)
        self.assertEqual(audit['retailer_path_present'],215)
        self.assertEqual(audit['retailer_path_missing'],875)
        # Exactly 208 of 215 known-path records have a shared merchant
        # category. A broad supermarket aisle does NOT verify whether the
        # product really is the specific variant requested by the rule.
        self.assertEqual(sum(bool(p['category_v27']['category']) for p in new['items']),208)
        self.assertEqual(sum(not p['category_v27']['category'] for p in new['items']),882)
        self.assertLess(audit['category_statuses'].get('verified',0),208)
        self.assertEqual(sum(audit['category_statuses'].values()),1090)
        self.assertEqual(review['count'],1090-audit['category_statuses'].get('verified',0))
        self.assertEqual(audit['price_diagnostics'],{'ok':894,'blocked_http':169,'price_read_unverified':27})
        for before,after in zip(old['items'],new['items']):
            for k,v in before.items():self.assertEqual(after[k],v)
        self.assertEqual(new['extra_nested'],old['extra_nested'])

    def test_write_separate_untouched_inputs(self):
        original=self.make_catalog()
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'v26.json'; dst=Path(d)/'v27.json'
            write_json(src,original)
            input_bytes=src.read_bytes()
            view,_,_=compile_catalog(json.loads(src.read_text(encoding='utf8')))
            write_json(dst,view)
            self.assertEqual(src.read_bytes(),input_bytes)
            self.assertEqual(len(json.loads(dst.read_text(encoding='utf8'))['items']),1090)

if __name__=='__main__':unittest.main()
