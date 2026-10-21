import copy,unittest
import catalog_quality_v24 as q

MAP={'W001':'Maso','W028':'Másla a tuky','W030':'Másla a tuky','W032':'Másla a tuky','W047':'Zelenina','W043':'Zelenina','W061':'Praní'}

class CategoryAudit(unittest.TestCase):
    def check(self,name,category,path=None):
        rid=next(k for k,v in MAP.items() if v==category)
        return q.gate_catalog_item({'name':name,'title':name,'store':'Košík','url':'https://www.kosik.cz/p11111','rule_ids':[rid],
                                    'store_category_path':path or [],'price_czk':84.9,'price_status':'ok'},MAP)
    def test_seeds_last_breadcrumb_says_zelenina_but_is_garden(self):
        ok,review=self.check('Semo Paprika NAGA MORICHA','Zelenina',['Domácnost a zahrada','Osiva a travní směsi','Zelenina'])
        self.assertIsNone(ok);self.assertIn('osiva',review['v24_review']['decisions'][0]['reason'])
    def test_fresh_vegetables_not_removed(self):
        ok,review=self.check('Rajčata oválná vanička','Zelenina',['Ovoce a zelenina','Zelenina','Rajčata'])
        self.assertIsNotNone(ok);self.assertIsNone(review)
    def test_pet_food_not_raw_meat(self):
        ok,review=self.check('Applaws Cat kapsička kuřecí prsa s lososem','Maso')
        self.assertIsNone(ok);self.assertIsNotNone(review)
    def test_cooked_meat_not_raw_meat(self):
        ok,_=self.check('Apetisimo Kuřecí prsa krájená pečená','Maso');self.assertIsNone(ok)
    def test_real_chicken_kept(self):
        ok,review=self.check('Amadori BIO Kuřecí prso','Maso')
        self.assertIsNotNone(ok);self.assertIsNone(review)
    def test_medical_and_cosmetic_not_edible_fat(self):
        for name in ['GYNELLA Flora 10 vaginálních čípků','EvoTears Omega oční kapky',
                     'Panthenol Omega tělové mléko','Harmony Soft Flora toaletní papír',
                     'Dr.Max Omega Smart Chews želé']:
            ok,_=self.check(name,'Másla a tuky');self.assertIsNone(ok,name)
    def test_edible_fat_kept(self):
        for name in ['Omega 100% rostlinný tuk','Flora Gold','Madeta Jihočeské máslo 82 %']:
            ok,_=self.check(name,'Másla a tuky');self.assertIsNotNone(ok,name)
    def test_persist_no_price_mutation(self):
        q.CATEGORY_BY_ID.update(MAP)
        p={'name':'Semo Okurka setá hadovka','store':'Košík','url':'https://www.kosik.cz/p1',
           'rule_ids':['W043'],'store_category_path':['Domácnost a zahrada','Osiva','Zelenina'],
           'price_czk':84.9,'price_status':'ok','multibuy':[{'min_qty':2,'price_czk':80}]}
        orig=copy.deepcopy(p)
        c={'items':[p],'rules':[{'id':'W043','category':'Zelenina'}]}
        nc,r,a=q.apply_catalog(c,{'items':[]})
        self.assertEqual(len(nc['items']),0)
        self.assertEqual(r['items'][0]['price_czk'],84.9)
        self.assertEqual(orig,p)
    def test_multirule_item_keeps_valid_rule_and_audits_invalid(self):
        ok,review=q.gate_catalog_item({'name':'Applaws Cat kuřecí prsa','rule_ids':['W001','W061']},MAP)
        self.assertEqual(ok['rule_ids'],['W061']);self.assertIsNotNone(review)
    def test_dont_flag_washing_powder(self):
        ok,review=q.gate_catalog_item({'name':'Ariel Color prací prášek','rule_ids':['W061']},MAP)
        self.assertIsNotNone(ok);self.assertIsNone(review)

if __name__=='__main__':unittest.main()
