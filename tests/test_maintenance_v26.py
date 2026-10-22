import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from maintenance_v26 import apply_result,pick_items
from datetime import datetime,timezone,timedelta
class MaintenanceTests(unittest.TestCase):
    def row(self,store='Košík',name='Ariel'):
        host='kosik.cz/p123-ariel' if store=='Košík' else 'rohlik.cz/12345-ariel'
        return {'store':store,'url':'https://www.'+host,'name':name,'price_czk':100.,'price_status':'ok','checked_at':'2026-10-20T10:00:00+00:00'}
    def test_price_failure_preserves_previous_and_time(self):
        x=self.row();y=apply_result(x,status='http_error',checked_at='2026-10-21T08:00:00+00:00')
        self.assertEqual(y['price_czk'],100)
        self.assertEqual(y['checked_at'],x['checked_at']);self.assertEqual(y['monitor_v26_status'],'http_error')
    def test_verified_drop_same_identity(self):
        x=self.row();y=apply_result(x,status='ok',price=80,offer={'discount_pct':20,'original_price_czk':100,'offer_valid_until':'2026-10-27'},checked_at='2026-10-21T08:00:00+00:00')
        self.assertEqual(y['drop_since_previous_pct'],20.0)
        self.assertEqual(y['offer_valid_until'],'2026-10-27')
    def test_non_sale_clears_outdated_merchant_discount(self):
        x=self.row();x.update(discount_pct=30,offer_valid_until='2026-10-20')
        y=apply_result(x,status='ok',price=110,offer={},checked_at='2026-10-21T08:00:00+00:00')
        self.assertIsNone(y['discount_pct']);self.assertIsNone(y['offer_valid_until'])
    def test_rohlik_offer_metadata_persisted(self):
        x=self.row('Rohlík')
        y=apply_result(x,status='ok',price=74.9,offer={'original_price_czk':129.9,'discount_pct':42.3},checked_at='2026-10-22T08:00:00+00:00')
        self.assertEqual(y['original_price_czk'],129.9)
        self.assertEqual(y['discount_pct'],42.3)

    def test_suppressed_retry_and_other_merchants(self):
        now=datetime(2026,10,21,8,tzinfo=timezone.utc)
        a=self.row();a['last_monitor_attempt_at']=(now-timedelta(hours=2)).isoformat()
        b=self.row('Rohlík','Ariel 2');b['price_status']='unknown'
        self.assertEqual(pick_items([a,b],limit=2,now=now),[b])
    def test_limit_and_no_invalid_url(self):
        a=self.row();b=self.row('Rohlík');b['url']='https://example.org/other'
        self.assertEqual(pick_items([a,b],limit=1),[a])
if __name__=='__main__':unittest.main()
