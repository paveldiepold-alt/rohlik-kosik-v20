"""UAT6: Merchant leaf taxonomy never turns the wrong narrow variant into a match.

Examples include genuine breadcrumb vocabulary observed on Košík. Names do
not provide positive evidence for classification; the stored watchlist matcher
remains a separate, explicitly less reliable signal.
"""
import unittest
from catalog_v27 import compile_catalog

GROUPS = {
    'W033': 'Nápoje / vody', 'W034': 'Nápoje / vody', 'W035': 'Nápoje / vody',
    'W036':'Nápoje / limonády', 'W050':'Sladké', 'W060':'Holení',
    'W063':'Praní','W064':'Praní','W065':'Praní','W072':'Úklid',
    'W054':'Papír a hygiena', 'W075':'Kapesníky / krabice',
}

def classify(rule,path,title='Zcela nesouvisející název'):
    p={'store':'Košík','url':'https://www.kosik.cz/p820466-ukazka',
       'name':title,'rule_ids':[rule], 'store_category_path':path,
       'category_source':'jsonld_breadcrumb','price_status':'ok',
       'price_czk':119.9,'checked_at':'2026-10-20T14:00:00+00:00'}
    src={'items':[p],'rules':[{'id':rule,'category':GROUPS[rule]}]}
    view,review,meta=compile_catalog(src)
    return view['items'][0],meta,review

class MerchantVariantTests(unittest.TestCase):
    def test_flavored_dobra_voda_is_not_matching_plain_water(self):
        path=['Nápoje','Vody','Minerální','Ochucené','Neperlivé']
        for rid in ('W033','W034','W035'):
            with self.subTest(rule=rid):
                row,meta,rev=classify(rid,path,title='Dobrá voda Neperlivá Mandarinka 6 x 1,5l')
                self.assertEqual(row['category_v27']['category'],'Nápoje / vody')
                self.assertEqual(row['category_v27']['status'],'mismatch')
                self.assertEqual(row['price_czk'],119.9)
                self.assertEqual(rev['count'],1)
                self.assertEqual(row['rule_ids'],[rid])

    def test_plain_water_needs_positive_variant_proof(self):
        examples=[
          (['Nápoje','Vody','Neperlivé'],'review'),
          (['Nápoje','Vody','Neochucené','Neperlivé'],'verified'),
          (['Nápoje','Vody','Neochucené','Jemně perlivé'],'verified'),
          (['Nápoje','Vody','Kojenecké vody'],'verified'),
          (['Nápoje','Vody','Neochucené','Perlivé'],'mismatch'),
          (['Nápoje','Vody','Ochucené neperlivé minerální vody'],'mismatch'),
        ]
        for path,state in examples:
            with self.subTest(path=path):
                row,*_=classify('W035',path)
                self.assertEqual(row['category_v27']['status'],state)

    def test_general_shelves_never_prove_flavor_or_package(self):
        samples=[
          ('W036',['Nápoje','Limonády']),
          ('W050',['Trvanlivé potraviny','Sladkosti']),
          ('W072',['Drogerie a kosmetika','Mytí nádobí','Ruční mytí']),
          ('W060',['Drogerie a kosmetika','Holení']),
          ('W063',['Drogerie a kosmetika','Praní']),
          ('W064',['Drogerie a kosmetika','Praní']),
          ('W065',['Drogerie a kosmetika','Praní']),
        ]
        for rid,path in samples:
            with self.subTest(rule=rid):
                row,*_=classify(rid,path)
                self.assertEqual(row['category_v27']['category'],GROUPS[rid])
                self.assertEqual(row['category_v27']['status'],'review')

    def test_specific_laundry_branches(self):
        examples=[
            ('W063',['Drogerie a kosmetika','Praní','Aviváže'],'verified'),
            ('W063',['Drogerie a kosmetika','Praní','Prací gely'],'mismatch'),
            ('W065',['Drogerie a kosmetika','Praní','Odstraňovače skvrn'],'verified'),
            ('W065',['Drogerie a kosmetika','Praní','Aviváže'],'mismatch'),
        ]
        for rid,path,expected in examples:
            with self.subTest(rule=rid,path=path):
                row,*_=classify(rid,path)
                self.assertEqual(row['category_v27']['status'],expected)

    def test_positive_title_never_fixes_wrong_merchant_path(self):
        path=['Nápoje','Vody','Minerální','Ochucené','Neperlivé']
        first,*_=classify('W035',path,title='Neperlivá voda, zaručeně čistá')
        second,*_=classify('W035',path,title='S vůní mandarinky')
        self.assertEqual(first['category_v27']['status'],second['category_v27']['status'])
        self.assertEqual(first['category_v27']['status'],'mismatch')

if __name__=='__main__': unittest.main()
