import unittest
from datetime import datetime, timezone, timedelta
from maintenance_v26 import pick_items

class FastRefreshTests(unittest.TestCase):
    def row(self, store, n, age=100):
        host='kosik.cz' if store=='Košík' else 'rohlik.cz'
        t=datetime(2026,10,22,18,tzinfo=timezone.utc)-timedelta(hours=age)
        return {'store':store,'url':f'https://www.{host}/p{n}',
                'name':f'Item {n}','price_status':'ok',
                'last_monitor_attempt_at':t.isoformat()}
    def test_all_1090_and_two_stores(self):
        now=datetime(2026,10,22,18,tzinfo=timezone.utc)
        items=[self.row('Košík',i) for i in range(550)] + [self.row('Rohlík',i) for i in range(540)]
        selected=pick_items(items,1200,now)
        self.assertEqual(len(selected),1090)
        self.assertEqual({x['store'] for x in selected},{'Košík','Rohlík'})
        self.assertEqual(len({(x['store'],x['url']) for x in selected}),1090)
    def test_recent_products_not_rechecked_immediately(self):
        now=datetime(2026,10,22,18,tzinfo=timezone.utc)
        selected=pick_items([self.row('Košík',1,age=1),self.row('Rohlík',2,age=6)],1200,now)
        self.assertEqual([x['name'] for x in selected],['Item 2'])
    def test_oldest_attempt_first(self):
        now=datetime(2026,10,22,18,tzinfo=timezone.utc)
        rows=[self.row('Košík',1,age=5),self.row('Košík',2,age=20)]
        self.assertEqual(pick_items(rows,1,now)[0]['name'],'Item 2')

if __name__=='__main__':unittest.main()
