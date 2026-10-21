"""v27 strict per-rule type validation against retailer paths, not titles."""
import unittest
from catalog_v27 import compile_catalog
from rule_path_v27 import specific_type


def testitem(path, rid, store='Košík', name='Název nesmí klasifikovat'):
    return {'store':store, 'url':'https://www.kosik.cz/p7777-x' if store=='Košík' else 'https://www.rohlik.cz/777777-x',
            'name':name, 'rule_ids':[rid], 'store_category_path':path,
            'category_source':'jsonld_breadcrumb', 'price_status':'ok', 'price_czk':120.5}

RULE_GROUP={**{k:'Maso' for k in ('W001','W002','W003','W004','W005')},
            **{k:'Ovoce' for k in ('W037','W038','W039','W040','W041','W042')},
            **{k:'Zelenina' for k in ('W043','W044','W045','W046','W047')}}


def classify(path,rid,store='Košík',name='Název nesmí klasifikovat'):
    product=testitem(path,rid,store,name)
    out,rev,audit=compile_catalog({'items':[product], 'rules':[{'id':rid,'category':RULE_GROUP[rid]}]})
    p=out['items'][0]
    return (p['category_v27']['status'],p['category_v27']['category'],p['category_v27']['rule_checks'][rid]['status'],
            p['price_czk'],rev['count'])


class RetailerSpecificRuleTests(unittest.TestCase):
    def test_merchant_paths_correctly_disambiguate_specific_tracked_types(self):
        samples=[
            ('W001',['Maso a ryby','Drůbež','Prsa a stehenní řízky','Prsa'],'Rohlík'),
            ('W002',['Maso a ryby','Drůbež','Stehna a čtvrtky','Stehna'],'Rohlík'),
            ('W002',['Maso a ryby','Drůbeží maso','Kuře','Stehna a čtvrtky'],'Košík'),
            ('W003',['Maso a ryby','Vepřové maso','Krkovice'],'Košík'),
            ('W004',['Maso a ryby','Vepřové','Panenka'],'Rohlík'),
            ('W005',['Maso a ryby','Hovězí a telecí','Roštěná a svíčková','Svíčková'],'Rohlík'),
            ('W037',['Ovoce a zelenina','Ovoce','Banány a exotické','Avokádo'],'Košík'),
            ('W038',['Ovoce a zelenina','Ovoce','Banány a exotické','Banány'],'Košík'),
            ('W041',['Ovoce a zelenina','Ovoce','Citrusy','Citróny'],'Košík'),
            ('W042',['Ovoce a zelenina','Ovoce','Hrozny'],'Košík'),
            ('W043',['Ovoce a zelenina','Zelenina','Okurky, cukety a lilky','Okurky'],'Košík'),
            ('W044',['Ovoce a zelenina','Zelenina','Rajčata'],'Rohlík'),
            ('W044',['Ovoce a zelenina','Zelenina','Rajčata','Cherry rajčata'],'Košík'),
            ('W045',['Ovoce a zelenina','Zelenina','Rajčata','Cherry rajčata'],'Košík'),
            ('W046',['Ovoce a zelenina','Zelenina','Kořenová zelenina','Mrkev'],'Košík'),
            ('W047',['Ovoce a zelenina','Zelenina','Papriky a chilli papričky','Papriky'],'Košík')]
        for rid,path,shop in samples:
            with self.subTest(id=rid, shop=shop,path=path):
                status,cat,rule,price,rev=classify(path,rid,shop)
                self.assertEqual((status,rule,price,rev),('verified','verified',120.5,0))

    def test_rule_type_mismatch_is_not_accepted_by_common_parent(self):
        samples=[
          ('W001',['Maso a ryby','Drůbež','Stehna a čtvrtky','Stehna'],'Rohlík'),
          ('W002',['Maso a ryby','Drůbež','Prsa a stehenní řízky','Prsa'],'Rohlík'),
          ('W037',['Ovoce a zelenina','Ovoce','Banány a exotické','Banány'],'Košík'),
          ('W038',['Ovoce a zelenina','Ovoce','Banány a exotické','Avokádo'],'Košík'),
          ('W045',['Ovoce a zelenina','Zelenina','Rajčata','Salátová rajčata','Salátová rajčata na stonku'],'Košík'),
          ('W047',['Ovoce a zelenina','Zelenina','Rajčata','Cherry rajčata'],'Košík'),
        ]
        for rid,path,shop in samples:
            with self.subTest(id=rid,path=path):
                state,cat,status,price,rev=classify(path,rid,shop)
                self.assertEqual((state,status,price,rev),('mismatch','mismatch',120.5,1))
                self.assertEqual(cat,RULE_GROUP[rid])

    def test_unresolved_broad_branch_never_makes_positive_type_claim(self):
        samples=[
           ('W038',['Ovoce a zelenina','Ovoce','Banány a exotické ovoce']),
           ('W039',['Ovoce a zelenina','Ovoce','Jahody a lesní plody']),
           ('W040',['Ovoce a zelenina','Ovoce','Jahody a bobuloviny']),
           ('W041',['Ovoce a zelenina','Ovoce','Citrusy']),
           ('W042',['Ovoce a zelenina','Ovoce','Hrozny a melouny']),
           ('W043',['Ovoce a zelenina','Zelenina','Okurky, cukety a lilky']),
           ('W046',['Ovoce a zelenina','Zelenina','Mrkev a kořenová zelenina']),
           ('W047',['Ovoce a zelenina','Zelenina','Papriky a chilli']),
           ('W005',['Maso a ryby','Hovězí maso','Svíčková a roštěnec']),
           ('W001',['Maso a ryby','Drůbež','Prsa a stehenní řízky']),
        ]
        for rid,path in samples:
            with self.subTest(id=rid,path=path):
                state,cat,status,price,rev=classify(path,rid)
                self.assertEqual((state,status,price,rev),('review','review',120.5,1))
                self.assertEqual(cat,RULE_GROUP[rid])

    def test_product_title_cannot_turn_unverified_path_into_verified(self):
        path=['Ovoce a zelenina','Ovoce','Banány a exotické ovoce']
        a=classify(path,'W038',name='Banány žluté 1kg')
        b=classify(path,'W038',name='Rohlík čisticí prostředek s vůní banánu')
        self.assertEqual(a,b)
        self.assertEqual(a[0],'review')

    def test_known_cherry_type_must_override_parent_rajcata(self):
        p=['Ovoce a zelenina','Zelenina','Rajčata','Cherry rajčata','Cherry červená']
        self.assertEqual(specific_type(p,'Zelenina'),'cherry_tomato')
        self.assertEqual(classify(p,'W045')[0],'verified')
        self.assertEqual(classify(p,'W044')[0],'verified')

if __name__=='__main__':unittest.main()
