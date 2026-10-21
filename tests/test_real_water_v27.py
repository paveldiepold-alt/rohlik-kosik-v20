"""Known v26 snapshot of 11 water products (not a live catalogue pull).

Only four records carry actual stored merchant breadcrumb paths. We must not
pretend the seven unproven items have verified variant taxonomy.
"""
import json
from pathlib import Path
import unittest
from catalog_v27 import compile_catalog

FILE=Path(__file__).parent/'fixtures'/'water_known_v26_20261021.json'

class StoredWaterPaths(unittest.TestCase):
    def test_no_flavored_water_is_accepted_as_plain_water(self):
        saved=json.loads(FILE.read_text(encoding='utf-8'))
        self.assertEqual(len(saved),11)
        items=[]
        for i,row in enumerate(saved):
            r=dict(row);r['url']=f'https://www.kosik.cz/p{999900+i}' if r['store']=='Košík' else f'https://www.rohlik.cz/{999900+i}'
            r['rule_ids']=[r.pop('rule_id')]
            r['price_czk']=119.9 if r['price_status']=='ok' else None
            items.append(r)
        raw={'items':items,'rules':[{'id':'W034','category':'Nápoje / vody'},
                                    {'id':'W035','category':'Nápoje / vody'}]}
        compiled,review,audit=compile_catalog(raw)
        statuses=[p['category_v27']['status'] for p in compiled['items']]
        self.assertEqual(statuses.count('mismatch'),4)
        self.assertEqual(statuses.count('review'),7)
        self.assertEqual(statuses.count('verified'),0)
        self.assertEqual(audit['priced_before'],10)
        self.assertEqual(audit['priced_after'],10)
        self.assertEqual(audit['products_after'],11)
        self.assertEqual(review['count'],11)
        self.assertEqual([x['name'] for x in items],[x['name'] for x in compiled['items']])

if __name__=='__main__':unittest.main()
