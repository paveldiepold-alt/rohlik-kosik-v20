import unittest
from copy import deepcopy
from catalog_v27 import merchant_category, diagnose_price, compile_catalog, norm


class RetailerTaxonomyV27(unittest.TestCase):
    def product(self, path, *, ids=None, name='Ověřený výrobek', status='ok', price=34.9,
                source='jsonld_breadcrumb', store='Košík'):
        return {'store': store, 'url': 'https://www.kosik.cz/p123456-zbozi' if store=='Košík' else 'https://www.rohlik.cz/123456-zbozi',
                'name': name, 'rule_ids': ids or ['W037'], 'store_category_path': path,
                'category_source': source, 'price_czk': price, 'price_status': status,
                'price_source': 'original', 'checked_at': '2026-10-20T10:00:00Z',
                'multibuy': [{'min_qty': 2, 'price_czk': 30}],
                'legacy_price_czk': 99.0, 'original_price_czk': 42.0}

    def test_diacritics(self):
        self.assertEqual(norm('Ovoce a\u00a0zelenina'), 'ovoce a zelenina')

    def test_fresh_fruit_from_merchant_not_title(self):
        p = self.product(['Ovoce a\u00a0zelenina', 'Ovoce', 'Exotické', 'Avokádo'], name='Avokádo s nápisem čistící')
        self.assertEqual(merchant_category(p)[0], 'Ovoce')

    def test_peach_cleaning_spray_never_fruit(self):
        p = self.product(['Drogerie a kosmetika', 'Mytí nádobí', 'Ruční mytí'], name='Ovocný čistící prostředek')
        self.assertEqual(merchant_category(p)[0], 'Úklid')

    def test_baby_food_never_fruit(self):
        p = self.product(['Dětská výživa', 'Ovocné přesnídávky'], name='Banánové pyré')
        self.assertIsNone(merchant_category(p)[0])

    def test_ready_to_cook_never_fresh_vegetable(self):
        p = self.product(['Ovoce a zelenina', 'Kuchařské boxy, hotové saláty a ready to cook', 'Předvařená zelenina'])
        self.assertIsNone(merchant_category(p)[0])

    def test_real_vegetable(self):
        p = self.product(['Ovoce a zelenina', 'Zelenina', 'Rajčata', 'Cherry červená'])
        self.assertEqual(merchant_category(p)[0], 'Zelenina')

    def test_real_meat(self):
        p = self.product(['Maso a ryby', 'Drůbeží maso', 'Kuře', 'Prsa'])
        self.assertEqual(merchant_category(p)[0], 'Maso')

    def test_marinated_meat_quarantined(self):
        p = self.product(['Maso a ryby', 'Maso na grilování', 'Marinované maso'])
        self.assertIsNone(merchant_category(p)[0])

    def test_smoked_meat_quarantined(self):
        p = self.product(['Maso a ryby', 'Vepřové maso', 'Uzené'])
        self.assertIsNone(merchant_category(p)[0])

    def test_meat_root_alone_not_enough(self):
        self.assertIsNone(merchant_category(self.product(['Maso a ryby']))[0])

    def test_grilling_and_steaks_branch_never_confirms_raw_meat(self):
        p=self.product(['Maso a ryby','Vepřové','Grilování a steaky'],ids=['W003'])
        self.assertIsNone(merchant_category(p)[0])

    def test_ground_meat_branch_never_confirms_raw_chicken_cuts(self):
        p=self.product(['Maso a ryby','Drůbeží maso','Kuře','Mleté a mělněné kuřecí maso'],ids=['W001'])
        self.assertIsNone(merchant_category(p)[0])

    def test_known_rohlik_bio_fruit_path(self):
        p=self.product(['Ovoce a zelenina','BIO ovoce a zelenina','BIO Ovoce'],ids=['W037'])
        self.assertEqual(merchant_category(p)[0],'Ovoce')

    def test_unknown_category_no_title_guess(self):
        self.assertIsNone(merchant_category(self.product([], name='Kuřecí maso 1 kg'))[0])

    def test_untrusted_source(self):
        self.assertIsNone(merchant_category(self.product(['Ovoce a zelenina','Ovoce'],source='name_prediction'))[0])

    def test_category_links_without_ordered_breadcrumb_are_not_proof(self):
        p=self.product(['Ovoce a zelenina','Ovoce'],source='product_category_links')
        self.assertIsNone(merchant_category(p)[0])

    def test_uzeniny(self):
        self.assertEqual(merchant_category(self.product(['Uzeniny a lahůdky', 'Šunky', 'Drůbeží']))[0], 'Uzeniny / šunky')

    def test_water(self):
        self.assertEqual(merchant_category(self.product(['Nápoje', 'Vody', 'Ochucené']))[0], 'Nápoje / vody')

    def test_broad_paper_shelf_not_false_mismatch_for_handkerchief_box(self):
        p = self.product(['Drogerie a kosmetika','Papírová hygiena','Papírové kapesníky'], ids=['W075'])
        out,review,_ = compile_catalog({'items':[p], 'rules':[{'id':'W075','category':'Kapesníky / krabice'}]})
        self.assertEqual(out['items'][0]['category_v27']['category'],'Papír a hygiena')
        self.assertEqual(out['items'][0]['category_v27']['rule_checks']['W075']['status'],'review')
        self.assertEqual(review['count'],1)

    def test_broad_paper_shelf_not_false_mismatch_for_towels(self):
        p = self.product(['Drogerie a kosmetika','Papírová hygiena','Papírové kapesníky'], ids=['W074'])
        out,review,_ = compile_catalog({'items':[p], 'rules':[{'id':'W074','category':'Papírové utěrky'}]})
        self.assertEqual(out['items'][0]['category_v27']['rule_checks']['W074']['status'],'review')
        self.assertEqual(out['items'][0]['price_czk'],34.9)

    def test_price_http_429_blocked(self):
        p = self.product([],status='http_error',price=None);p['http_status']=429
        self.assertEqual(diagnose_price(p)[0], 'blocked_http')

    def test_price_200_read_unverified(self):
        p = self.product([],status='price_unverified',price=None);p['http_status']=200
        self.assertEqual(diagnose_price(p)[0], 'price_read_unverified')

    def test_recent_v26_result_beats_stale_429(self):
        p = self.product([], status='http_error', price=None)
        p.update(http_status=429, monitor_v26_status='price_unverified')
        self.assertEqual(diagnose_price(p)[0], 'price_read_unverified')

    def test_historical_identity_mismatch_superseded_by_recent_parse_attempt(self):
        p = self.product([], status='title_mismatch', price=None)
        p.update(http_status=200, monitor_v26_status='price_unverified')
        self.assertEqual(diagnose_price(p)[0], 'price_read_unverified')

    def test_price_title_mismatch(self):
        p = self.product([],status='title_mismatch',price=None);p['http_status']=200
        self.assertEqual(diagnose_price(p)[0], 'identity_mismatch')

    def test_price_404_suspected_not_confirmed(self):
        p = self.product([],status='http_error',price=None);p['http_status']=404
        self.assertEqual(diagnose_price(p)[0], 'product_unavailable_unconfirmed')

    def test_roundtrip_preserves_every_original_field(self):
        p = self.product(['Ovoce a zelenina','Ovoce','Avokádo'], name='Produkty',ids=['W037'])
        raw = {'items': [p], 'rules': [{'id':'W037','category':'Ovoce'}],
               'schema':'legacy','generated_at':'2026-10-21T14:12:55+00:00', 'unknown_field': {'nested': [123]}}
        copy = deepcopy(raw)
        new, review, audit = compile_catalog(raw)
        self.assertEqual(raw, copy)
        self.assertEqual(audit['priced_before'], 1)
        self.assertEqual(audit['priced_after'], 1)
        self.assertEqual(audit['category_statuses']['verified'], 1)
        self.assertEqual(review['count'], 0)
        self.assertEqual(new['items'][0]['price_czk'],p['price_czk'])
        self.assertEqual(new['items'][0]['multibuy'],p['multibuy'])
        self.assertEqual(new['items'][0]['legacy_price_czk'],p['legacy_price_czk'])
        self.assertEqual(new['unknown_field'], raw['unknown_field'])
        for k in p: self.assertEqual(p[k], new['items'][0][k])

    def test_mismatch_is_not_deleted_and_keeps_price(self):
        p = self.product(['Drogerie a kosmetika','Mytí nádobí'], name='Ovocný detergent', ids=['W037'])
        new, review, audit = compile_catalog({'items':[p], 'rules':[{'id':'W037','category':'Ovoce'}]})
        self.assertEqual(new['items'][0]['category_v27']['status'],'mismatch')
        self.assertEqual(new['items'][0]['category_v27']['category'],'Úklid')
        self.assertEqual(new['items'][0]['price_czk'], 34.9)
        self.assertEqual(review['count'], 1)
        self.assertEqual(audit['products_before'],audit['products_after'])

    def test_each_search_rule_is_verified_independently(self):
        p = self.product(['Ovoce a zelenina','Ovoce','Avokádo'],ids=['W037','W061'])
        rules = [{'id':'W037','category':'Ovoce'},{'id':'W061','category':'Praní'}]
        out, review, report = compile_catalog({'items':[p], 'rules':rules})
        c = out['items'][0]['category_v27']
        self.assertEqual(c['rule_checks']['W037']['status'],'verified')
        self.assertEqual(c['rule_checks']['W061']['status'],'mismatch')
        self.assertEqual(c['status'], 'mismatch')
        self.assertEqual(out['items'][0]['rule_ids'], ['W037','W061'])
        self.assertEqual(report['rule_match_statuses'], {'verified':1, 'mismatch':1})
        self.assertEqual(review['count'],1)

    def test_no_path_keeps_item_review_and_price(self):
        p = self.product([], name='Banánový příkrm', ids=['W037'])
        new, review, audit = compile_catalog({'items':[p], 'rules':[{'id':'W037','category':'Ovoce'}]})
        self.assertEqual(new['items'][0]['category_v27']['display_category'], 'Ke kontrole')
        self.assertEqual(review['count'], 1)
        self.assertEqual(audit['priced_after'],1)

    def test_duplicate_key_rejected(self):
        p = self.product(['Ovoce a zelenina', 'Ovoce'])
        with self.assertRaises(ValueError):
            compile_catalog({'items':[p, deepcopy(p)]})


if __name__ == '__main__': unittest.main()
