import unittest
from recheck_catalog_prices_v22 import candidates,apply_observation
class RecheckTests(unittest.TestCase):
    def test_old_unit_suspect_first_and_filter(self):
        data={'items':[
          {'name':'Ariel example','store':'Košík','url':'https://www.kosik.cz/p1', 'price_czk':7.77,'price_status':'ok','price_source':'kosik-product-text'},
          {'name':'Ariel example','store':'Rohlík','url':'https://www.rohlik.cz/12345','price_czk':None,'price_status':'price_unverified'},
          {'name':'Another brand','store':'Košík','url':'https://www.kosik.cz/p2','price_czk':None,'price_status':'price_unverified'}]}
        results=candidates(data,'Ariel',20)
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]['price_czk'],7.77)
    def test_preserve_metadata_and_legacy(self):
        row={'name':'Ariel','rule_ids':['W061'],'store_category_path':['Praní'],'price_czk':7.77,'price_status':'ok','price_source':'kosik-product-text'}
        after=apply_observation(row,{'status':'ok','price_czk':699.,'source':'kosik-pack-v22','note':'valid'},'today')
        self.assertEqual(after['price_czk'],699.)
        self.assertEqual(after['legacy_price_czk'],7.77)
        self.assertEqual(after['rule_ids'],['W061'])
        self.assertEqual(after['store_category_path'],['Praní'])
    def test_uncertain_cannot_publish_stale_price(self):
        row={'price_czk':7.77,'price_status':'ok','price_source':'kosik-product-text'}
        after=apply_observation(row,{'status':'price_unverified','note':'missing'},'today')
        self.assertIsNone(after['price_czk'])
        self.assertEqual(after['price_status'],'price_unverified')
        self.assertEqual(after['legacy_price_czk'],7.77)
    def test_transient_failure_can_retry_once(self):
        row={'store':'Košík','name':'x','url':'https://www.kosik.cz/p5',
             'price_czk':None,'price_status':'price_unverified'}
        a=apply_observation(row,{'status':'http_error','note':'HTTP 429'},'today')
        self.assertEqual(len(candidates({'items':[a]})),1)
        b=apply_observation(a,{'status':'http_error','note':'HTTP 429'},'tomorrow')
        self.assertEqual(len(candidates({'items':[b]})),0)
if __name__=='__main__': unittest.main()
