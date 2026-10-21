"""Tests for persistent merchant backoff and lossless production-price updates."""
import unittest
from datetime import datetime, timedelta, timezone
from taxonomy_probe_v27 import active_shop_blocks, eligible, pick, sync_new_prices

UTC = timezone.utc


def product(store='Košík', n=1234):
    url=(f'https://www.kosik.cz/p{n}-brand' if store=='Košík'
         else f'https://www.rohlik.cz/{n}99-brand')
    return {'store':store, 'url':url,'name':'Brand sample',
            'price_status':'ok','price_czk':49.5,'checked_at':'2026-10-21T09:00:00+00:00',
            'price_history_previous_czk':59.5,'rule_ids':['W001']}


class BackoffTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,21,19,0,tzinfo=UTC)

    def test_active_shop_backoff_blocks_only_that_merchant(self):
        control={'shop_backoff_until':{'Košík':(self.now+timedelta(hours=21)).isoformat(),
                                      'Rohlík':(self.now-timedelta(minutes=1)).isoformat(),
                                      'forged.invalid':'2099-01-01T00:00:00+00:00'}}
        blocked=active_shop_blocks(control,self.now)
        self.assertEqual(list(blocked),['Košík'])
        items=[product('Košík'),product('Rohlík')]
        self.assertEqual([p['store'] for p in pick(items,10,now=self.now,blocked_stores=blocked)],['Rohlík'])

    def test_repeated_missing_path_backoff_increases_without_deleting(self):
        p=product()
        for attempts,hours,expect in [(1,25,True),(2,30,False),(2,73,True),
                                      (4,160,False),(4,169,True)]:
            p['v27_category_probe_attempts']=attempts
            p['v27_category_checked_at']=(self.now-timedelta(hours=hours)).isoformat()
            self.assertEqual(eligible(p,self.now),expect)

    def test_merchant_backoff_survives_newer_source_prices(self):
        current=product();current['price_czk']=62.9
        previous=product();previous.update(price_czk=35.5,
                store_category_path=[],v27_category_probe_attempts=2,
                v27_category_probe_status='category_missing')
        control={'shop_backoff_until':{'Košík':(self.now+timedelta(hours=2)).isoformat()}}
        result=sync_new_prices({'items':[current]},
                {'items':[previous],'v27_probe_control':control})
        self.assertEqual(result['items'][0]['price_czk'],62.9)
        self.assertEqual(result['items'][0]['v27_category_probe_attempts'],2)
        self.assertEqual(result['v27_probe_control'],control)
        self.assertNotIn('v27_probe_control',current)

    def test_untrusted_malformed_backoff_is_ignored(self):
        self.assertEqual(active_shop_blocks({'shop_backoff_until':{'Košík':'not-a-date'}},self.now),{})
        self.assertEqual(active_shop_blocks({'shop_backoff_until':[]},self.now),{})

if __name__=='__main__':unittest.main()
