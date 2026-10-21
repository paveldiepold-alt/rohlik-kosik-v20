import unittest
from types import SimpleNamespace
from pathlib import Path
import tempfile
from datetime import datetime, timezone
from taxonomy_probe_v27 import eligible, safe_url, sync_new_prices, pick, run


def item(shop='Košík', url='https://www.kosik.cz/p11111-x'):
    return {'store':shop, 'url':url, 'name':'Pomazánka',
            'price_czk':99.0, 'price_status':'ok','price_source':'v26',
            'checked_at':'2026-10-21', 'rule_ids':['W001']}

class ProbeTests(unittest.TestCase):
    def test_refuses_same_input_output_before_any_network_or_read(self):
        with tempfile.TemporaryDirectory() as folder:
            f=str(Path(folder)/'missing.json')
            args=SimpleNamespace(input=f, staging=f, report=str(Path(folder)/'report.json'),limit=10,delay=3.2)
            with self.assertRaisesRegex(ValueError,'preserving v26'):
                run(args)

    def test_url_must_be_actual_product_not_a_generic_merchant_page(self):
        self.assertFalse(safe_url(item(url='https://www.kosik.cz/admin')))
        self.assertFalse(safe_url(item(url='https://www.kosik.cz/c301-napoje')))
        self.assertFalse(safe_url(item(url='https://www.kosik.cz/p11111-x?offer=bad')))
        self.assertTrue(safe_url(item(url='https://www.kosik.cz/p11111-x')))

    def test_host_validation(self):
        self.assertTrue(safe_url(item()))
        self.assertFalse(safe_url(item(url='https://evil.example/p11111-x')))
        self.assertFalse(safe_url(item(url='https://www.rohlik.cz/11111-x')))
        self.assertFalse(safe_url(item(url='http://www.kosik.cz/p11111-x')))
        self.assertFalse(safe_url(item(url='https://www.kosik.cz:1234/p11111-x')))

    def test_later_v26_price_wins_over_old_stage(self):
        current=item(); current['price_czk']=144.5;current['checked_at']='2026-10-22'
        stage=item(); stage.update(store_category_path=['Maso a ryby','Drůbež','Prsa'],
                                  category_source='jsonld_breadcrumb',v27_category_probe_status='category_found')
        combined=sync_new_prices({'items':[current],'v26':'new'},{'items':[stage]})
        actual=combined['items'][0]
        self.assertEqual(actual['price_czk'],144.5)
        self.assertEqual(actual['checked_at'],'2026-10-22')
        self.assertEqual(actual['store_category_path'],['Maso a ryby','Drůbež','Prsa'])
        self.assertEqual(actual['v27_category_probe_status'],'category_found')

    def test_missing_category_queue(self):
        a=item();b=item(shop='Rohlík',url='https://www.rohlik.cz/123456-y')
        selected=pick([a,b],2)
        self.assertEqual(len(selected),2)

    def test_trusted_but_unmapped_path_is_not_requeried(self):
        p=item(); p.update(store_category_path=['Neznámé potraviny','Nesměrované výrobky'],
                           category_source='jsonld_breadcrumb')
        self.assertFalse(eligible(p,datetime.now(timezone.utc)))

    def test_new_source_breadcrumb_takes_precedence_over_staging(self):
        current=item(); current.update(store_category_path=['Drogerie a kosmetika','Mytí nádobí'],
                                      category_source='jsonld_breadcrumb',price_czk=199)
        previous=item(); previous.update(store_category_path=['Maso a ryby','Drůbež','Prsa'],
                                        category_source='jsonld_breadcrumb',price_czk=99)
        result=sync_new_prices({'items':[current]},{'items':[previous]})
        self.assertEqual(result['items'][0]['store_category_path'],current['store_category_path'])
        self.assertEqual(result['items'][0]['price_czk'],199)

    def test_source_dropping_previous_v27_product_is_rejected(self):
        kept=item(); removed=item(shop='Rohlík',url='https://www.rohlik.cz/123450-c')
        with self.assertRaisesRegex(ValueError, 'previously staged products'):
            sync_new_prices({'items':[kept]},{'items':[kept, removed]})

    def test_staging_duplicate_products_are_rejected(self):
        kept=item()
        with self.assertRaisesRegex(ValueError, 'Duplicate product identities'):
            sync_new_prices({'items':[kept]},{'items':[kept, kept]})

    def test_verified_path_not_requeried(self):
        p=item();p.update(store_category_path=['Ovoce a zelenina','Ovoce'],category_source='dom_breadcrumb')
        self.assertFalse(eligible(p,datetime.now(timezone.utc)))

if __name__=='__main__':unittest.main()
