"""Offline regression tests; no retailer requests, no tokens/credentials."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store_taxonomy import decide_fresh_rule, parse_context, gate_item, partition_items

FRUIT={'category_source':'jsonld_breadcrumb','store_category_path':['Ovoce a zelenina','Ovoce','Banány a exotické ovoce']}
VEG={'category_source':'dom_breadcrumb','store_category_path':['Ovoce a zelenina','Zelenina','Rajčata a papriky']}
FROZEN={'category_source':'dom_breadcrumb','store_category_path':['Mražené','Zmrzliny','Kelímky','Sorbety a dřeně']}
BABY={'category_source':'dom_breadcrumb','store_category_path':['Děti','Dětská výživa','Ovocné příkrmy']}
DRINK={'category_source':'dom_breadcrumb','store_category_path':['Nápoje','Pivo a nealko','Ochucené pivo']}
SPICE={'category_source':'dom_breadcrumb','store_category_path':['Trvanlivé','Koření','Mletá paprika']}
REVIEW={'category_source':'missing','store_category_path':[]}

class RetailerTaxonomyTests(unittest.TestCase):
 def test_sorbet_looks_like_citron_but_category_frozen(self):
  self.assertEqual(decide_fresh_rule('W041',FROZEN)[0],'reject')
 def test_baby_food_not_banana(self):
  self.assertEqual(decide_fresh_rule('W038',BABY)[0],'reject')
 def test_drink_not_maliny(self):
  self.assertEqual(decide_fresh_rule('W040',DRINK)[0],'reject')
 def test_spice_not_paprika(self):
  self.assertEqual(decide_fresh_rule('W047',SPICE)[0],'reject')
 def test_fresh_banana(self):
  self.assertEqual(decide_fresh_rule('W038',FRUIT)[0],'accept')
 def test_fresh_avocado(self):
  self.assertEqual(decide_fresh_rule('W037',FRUIT)[0],'accept')
 def test_fresh_tomato(self):
  self.assertEqual(decide_fresh_rule('W044',VEG)[0],'accept')
 def test_cross_category_fruit_and_veg(self):
  self.assertEqual(decide_fresh_rule('W037',VEG)[0],'reject')
  self.assertEqual(decide_fresh_rule('W047',FRUIT)[0],'reject')
 def test_combined_parent_never_proves_fruit_or_veg(self):
  c={'category_source':'dom_breadcrumb','store_category_path':['Ovoce a zelenina']}
  self.assertEqual(decide_fresh_rule('W037',c)[0],'review')
  self.assertEqual(decide_fresh_rule('W046',c)[0],'review')
 def test_missing_metadata_does_not_accept(self):
  self.assertEqual(decide_fresh_rule('W038',REVIEW)[0],'review')
 def test_jsonld_breadcrumb(self):
  ld={'@context':'https://schema.org','@type':'BreadcrumbList','itemListElement':[
   {'@type':'ListItem','position':1,'name':'Košík.cz'},
   {'@type':'ListItem','position':2,'name':'Mražené'},
   {'@type':'ListItem','position':3,'name':'Zmrzliny'},
   {'@type':'ListItem','position':4,'name':'Sorbety a dřeně'}]}
  data=parse_context({'title':'ALNATURA BIO Sorbet citron s bergamotem',
                      'jsonld':[json.dumps(ld)],'dom_breadcrumbs':['Ovoce']})
  self.assertEqual(data['store_category_path'],['Mražené','Zmrzliny','Sorbety a dřeně'])
  self.assertEqual(decide_fresh_rule('W041',data)[0],'reject')
 def test_dom_breadcrumb_fallback(self):
  data=parse_context({'title':'BIO Banány 500g','jsonld':[],
            'dom_breadcrumbs':['Košík.cz','Ovoce a zelenina','Ovoce','Banány a exotické']})
  self.assertEqual(decide_fresh_rule('W038',data)[0],'accept')
 def test_scoped_links_fallback(self):
  data=parse_context({'title':'Banány 1ks', 'jsonld':[],
        'scoped_category_links':[{'name':'Ovoce','url':'https://rohlik.cz/c123-ovoce'}]})
  self.assertEqual(decide_fresh_rule('W038',data)[0],'accept')
 def test_not_from_description_alone(self):
  data=parse_context({'title':'ALNATURA Sorbet citron','jsonld':[],
           'meta_description':'Z čerstvých citronů a ovoce'})
  self.assertEqual(decide_fresh_rule('W041',data)[0],'review')
 def test_category_removal_preserves_price_and_link(self):
  item={'name':'ALNATURA BIO Sorbet citron s bergamotem','store':'Košík',
        'url':'https://www.kosik.cz/p610029-foo','price_czk':149.9,
        'rule_ids':['W041'],**FROZEN}
  accepted,rejected=gate_item(item)
  self.assertIsNone(accepted)
  self.assertEqual(rejected['price_czk'],149.9)
  self.assertEqual(rejected['url'],item['url'])
 def test_no_mutation_of_original(self):
  item={'name':'BIO Banány','rule_ids':['W038'],**FRUIT}
  original=dict(item)
  good,bad=gate_item(item)
  self.assertIsNone(bad)
  self.assertEqual(good['rule_ids'],['W038'])
  self.assertEqual(item,original)
 def test_unknown_goes_to_review_and_not_disappear(self):
  a={'name':'Banán bez taxonomie','rule_ids':['W038'],**REVIEW}
  b={'name':'BIO Banány','rule_ids':['W038'],**FRUIT}
  kept,review=partition_items([a,b])
  self.assertEqual(len(kept)+len(review),2)
  self.assertEqual(len(review),1)
 def test_other_categories_stay_untouched(self):
  product={'name':'Ariel Prací gel','rule_ids':['W061']}
  good,bad=gate_item(product)
  self.assertIsNone(bad)
  self.assertEqual(good,product)

if __name__=='__main__':unittest.main()
