import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from catalog_search import plan_jobs, plan_queries, balanced_queries, job_key, scan_plan_signature, scan_single_query
from catalog_monitor import (rule_matches,matching_rules,normal_product_link,
                             unique_matches,acceptance,progress_overview,folded)

CFG=json.loads((ROOT/'watchlist.json').read_text(encoding='utf-8'))
RULES={x['id']:x for x in CFG['watch_rules']}

class CatalogRulesTests(unittest.TestCase):
    def test_every_rule_has_both_stores(self):
        jobs=plan_jobs(CFG)
        covered={rid for job in jobs for rid in job['rule_ids']}
        self.assertEqual(covered,set(RULES))
        self.assertEqual({x['shop'] for x in jobs},{'Rohlík','Košík'})
        self.assertEqual(len(jobs),2*len(plan_queries(CFG)))
        self.assertGreater(len(jobs),140)
    def test_food_before_cleaning(self):
        ordered=balanced_queries(CFG)
        self.assertTrue(any('W001' in x['rule_ids'] for x in ordered[:10]))
        self.assertTrue(any('W061' in x['rule_ids'] for x in ordered[50:]))
    def test_meat_is_not_processed(self):
        self.assertTrue(rule_matches('Kuřecí prsní řízky čerstvé',RULES['W001']))
        self.assertFalse(rule_matches('Kuřecí prsní řízky marinované',RULES['W001']))
        self.assertFalse(rule_matches('Just Meat Kuřecí prsní řízky krmivo pro psa',RULES['W001']))
    def test_fresh_fruit_and_veg(self):
        self.assertTrue(rule_matches('Avokádo volné',RULES['W037']))
        self.assertFalse(rule_matches('Avokádový olej',RULES['W037']))
        self.assertFalse(rule_matches('Ravioli s rajčaty',RULES['W044']))
    def test_brand_typing_and_products(self):
        self.assertTrue(rule_matches('Hellmann\'s Majonéza 625 ml',RULES['W027']))
        self.assertFalse(rule_matches('Hellmann\'s Tatarská omáčka',RULES['W027']))
        self.assertTrue(rule_matches('Opavia Fidorka mléčná s kokosem modrá',RULES['W050']))
        self.assertFalse(rule_matches('Fidorka čokoládová bez kokosu',RULES['W050']))
    def test_paper_separation(self):
        self.assertTrue(rule_matches('Zewa Deluxe Standard kapesníky 3vrstvé 10x10',RULES['W073']))
        self.assertFalse(rule_matches('Zewa Deluxe Family papírové kapesníky 3vrstvé BOX 90 ks',RULES['W073']))
        self.assertTrue(rule_matches('Zewa Deluxe Family kapesníky 3vrstvé',RULES['W075']))
        self.assertTrue(rule_matches('Zewa Wisch Weg kuchyňské utěrky 4 role',RULES['W074']))
        self.assertFalse(rule_matches('Zewa Wisch Weg vlhčené kuchyňské utěrky',RULES['W074']))
        self.assertFalse(rule_matches('Zewa Deluxe Standard kapesníky 3vrstvé',RULES['W053']))
    def test_drinks_sizes_and_variants(self):
        self.assertTrue(rule_matches('Aquila neperlivá 1,5 l PET',RULES['W033']))
        self.assertFalse(rule_matches('Aquila neperlivá 0,5 l PET',RULES['W033']))
        self.assertTrue(rule_matches('Coca-Cola Original 2 l PET',RULES['W036']))
        self.assertFalse(rule_matches('Coca-Cola Zero 2 l PET',RULES['W036']))
        self.assertFalse(rule_matches('Coca-Cola Original 0,5 l PET',RULES['W036']))
    def test_link_safety_and_uniqueness(self):
        cards=[{'name':'Hellmanns Majonéza 625 ml', 'url':'https://www.kosik.cz/p123456-hellmanns-majoneza?ref=abc','image_url':'https://www.kosik.cz/image.jpg'},
               {'name':'Hellmanns Majonéza 625 ml','url':'https://www.kosik.cz/p123456-hellmanns-majoneza?xyz=1'},
               {'name':'Hellmanns Majonéza 625 ml','url':'https://evil.test/p123456-hellmanns-majoneza'},
               {'name':'Hellmanns Majonéza 625 ml','url':'https://www.kosik.cz/?id=p123456'}]
        products=unique_matches(cards,'Košík',list(RULES.values()))
        self.assertEqual(len(products),1)
        self.assertEqual(products[0]['url'],'https://www.kosik.cz/p123456-hellmanns-majoneza')
        self.assertIn('W027',products[0]['rule_ids'])
    def test_pilot_is_not_false_full_catalogue(self):
        self.assertFalse(acceptance({'queries':{},'discovered_in_cycle':{},'fresh_verified_by_store':{}})[0])
        self.assertFalse(acceptance({'queries':{'q':{'status':'ok','links':1}},
            'discovered_in_cycle':{'Rohlík':2,'Košík':2},'fresh_verified_by_store':{'Rohlík':2,'Košík':0}})[0])
        self.assertTrue(acceptance({'planned_jobs':1,'completed':['q'],'queries':{'q':{'status':'ok','links':1}},
            'discovered_in_cycle':{'Rohlík':2,'Košík':2},'fresh_verified_by_store':{'Rohlík':1,'Košík':1}})[0])
        self.assertFalse(acceptance({'planned_jobs':196,'completed':['q'],'queries':{'q':{'status':'ok','links':1}},
            'discovered_in_cycle':{'Rohlík':2,'Košík':2},'fresh_verified_by_store':{'Rohlík':1,'Košík':1}})[0])

if __name__=='__main__':unittest.main()
