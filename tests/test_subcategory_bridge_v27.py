"""UAT14: real trusted Rohlík/Košík category paths, not product title guesses.

Counts reflect 2026-10-22 15:36 UTC path-review snapshot. No retailer requests.
"""
from copy import deepcopy
import unittest
from catalog_v27 import merchant_category, compile_catalog, trusted_path


OBSERVED = [
    (17, 'Sýry / plísňové a zrající', ['Mléčné a chlazené', 'Sýry', 'Plísňové, zrající, pařené a uzené', 'Plísňové a zrající']),
    (9, 'Kosmetika', ['Kosmetika', 'Sprchové gely a mýdla a přísady do koupele', 'Sprchové gely', 'Pánské']),
    (6, 'Sýry / grilovací', ['Mléčné a chlazené', 'Sýry', 'Na gril, fondue a raclette', 'Na gril a pánev']),
    (5, 'Sýry / grilovací', ['Mléčné a\u00a0chlazené', 'Sýry', 'Grilovací sýry, raclette, fondue', 'Grilovací sýry']),
    (3, 'Těstoviny a rýže', ['Speciální výživa', 'Bezlepkové výrobky', 'Pečení a vaření', 'Těstoviny']),
    (2, 'Kosmetika', ['Drogerie a\u00a0kosmetika', 'Sprchové gely, mýdla, pěny', 'Sprchové gely', 'Pánské']),
    (3, 'Sýry / bez laktózy', ['Mléčné a\u00a0chlazené', 'Bez laktózy', 'Sýry']),
    (2, 'Sýry / snacky a dětské', ['Mléčné a chlazené', 'Sýry', 'Sýrové snacky a pro děti']),
    (2, 'Sýry / bez laktózy', ['Speciální výživa', 'Bezlaktózové výrobky', 'Sýry bez laktózy']),
    (1, 'Sladké', ['Trvanlivé', 'Sladké', 'Sladké tyčinky']),
    (1, 'Mléčné / smetany', ['Mléčné a chlazené', 'Smetany, šlehačky a tvarohy', 'Smetany ke šlehání a šlehačky']),
    (1, 'Mléčné / smetany', ['Mléčné a chlazené', 'Smetany, šlehačky a tvarohy', 'Smetany na vaření']),
    (1, 'Sýry / pařené a uzené', ['Mléčné a chlazené', 'Sýry', 'Plísňové, zrající, pařené a uzené', 'Pařené a uzené']),
    (1, 'Rostlinné alternativy / smetany', ['Plant Based', 'Alternativy mléčného a chlazeného', 'Rostlinné smetany, šlehačky a krémy', 'Rostlinné smetany ke šlehání a šlehačky']),
    (1, 'Rostlinné alternativy / smetany', ['Plant Based', 'Alternativy mléčného a chlazeného', 'Rostlinné smetany, šlehačky a krémy', 'Rostlinné smetany na vaření']),
]

# Number of pending products in each intentionally unclassified merchant path:
REVIEW_COUNTS = [2, 1, 1, 1, 2, 2]
REVIEW = [
    ['Maso a ryby', 'Vepřové maso', 'Uzené'],
    ['Maso a ryby', 'Drůbeží maso', 'Kuře', 'Mleté a mělněné kuřecí maso'],
    ['Maso a ryby', 'Maso na grilování', 'Marinované maso'],
    ['Maso a ryby', 'Vepřové', 'Grilování a steaky'],
    ['Ovoce a zelenina', 'Kuchařské boxy, hotové saláty a ready to cook', 'Rychlá příprava a předvařená zelenina'],
    ['Zdraví a životní styl', 'Veggie', 'Sýry, krémy a tuky', 'Krémy'],
]


def item(path, i=0, *, source='jsonld_breadcrumb'):
    return {'store':'Rohlík','url':f'https://www.rohlik.cz/{9999+i}',
            'name': 'Banánová slanina šampon',
            'store_category_path':path,'category_source':source,
            'rule_ids':['W001'], 'price_status':'ok','price_czk':round(39.90+i/100,2),
            'checked_at':'2026-10-22T08:00:00+00:00'}


class MerchantSubcategoryTests(unittest.TestCase):
    def test_observed_groupings_with_real_counts(self):
        self.assertEqual(sum(n for n,*_ in OBSERVED), 55)
        for count,expected,path in OBSERVED:
            with self.subTest(path=path,count=count):
                self.assertTrue(trusted_path(item(path)))
                self.assertEqual(merchant_category(item(path))[0],expected)

    def test_exact_category_bridge_delta_from_review(self):
        # Actual v27 path-review snapshot: 64 trusted paths remain unmapped.
        # Our rule coverage is 55, and 9 stay under review. This is NOT a live
        # scan and does not mean new price data was obtained.
        self.assertEqual(sum(n for n,_,_ in OBSERVED),55)
        self.assertEqual(sum(REVIEW_COUNTS),9)
        self.assertEqual(sum(n for n,_,_ in OBSERVED)+sum(REVIEW_COUNTS),64)

    def test_uncertain_products_not_force_mapped(self):
        for path in REVIEW:
            with self.subTest(path=path):
                self.assertIsNone(merchant_category(item(path))[0])

    def test_never_infer_from_title(self):
        for _,category,path in OBSERVED:
            p=item(path)
            p['name']='Pomerančový WC gel a mleté kuře'
            self.assertEqual(merchant_category(p)[0],category)

    def test_require_trusted_full_path(self):
        for _,cat,path in OBSERVED:
            for src in ('missing','product_category_links','error',None):
                self.assertIsNone(merchant_category(item(path,source=src))[0])
            self.assertIsNone(merchant_category(item(path[:1]))[0])

    def test_avoid_wrong_parent_branches(self):
        bad=[['Ovoce a zelenina','Sprchové gely','Pánské'],
             ['Kosmetika','Ústní hygiena','Grilovací sýry'],
             ['Mléčné a chlazené','Maso','Plísňové a zrající'],
             ['Trvanlivé','Sladké','Maso na grilování'],
             ['Ovoce a zelenina','Maso','Těstoviny'],
             ['Drogerie','Sprchové gely, mýdla, pěny','Ovoce'],
             ['Speciální výživa','Bezlepkové výrobky','Čisticí prostředek','Těstoviny']]
        for path in bad:
            with self.subTest(path=path):
                self.assertIsNone(merchant_category(item(path))[0])

    def test_shower_gel_stays_cosmetics_not_detergent(self):
        for _,expected,path in OBSERVED:
            if expected=='Kosmetika':
                self.assertNotEqual(merchant_category(item(path))[0],'Praní')

    def test_broad_cheese_shelves_not_narrowly_verified(self):
        p=item(OBSERVED[0][2]);p['rule_ids']=['W101']
        c={'items':[p],'rules':[{'id':'W101','category':'Sýry / plísňové'}]}
        result,review,audit=compile_catalog(c)
        self.assertEqual(result['items'][0]['category_v27']['category'],'Sýry / plísňové a zrající')
        self.assertEqual(result['items'][0]['category_v27']['status'],'review')
        self.assertEqual(result['items'][0]['category_v27']['rule_checks']['W101']['status'],'review')
        self.assertEqual(audit['merchant_category_mapped'],1)
        self.assertEqual(review['count'],1)

    def test_full_synthetic_catalog_integrity_1090(self):
        # Synthetic 1090-row catalogue: deliberately no live or confidential prices.
        rows=[]
        for count,category,path in OBSERVED:
            for _ in range(count):
                i=len(rows)
                rows.append(item(path,i))
        for path in REVIEW:
            rows.append(item(path,len(rows)))
        while len(rows)<1090:
            i=len(rows)
            p=item(['Drogerie','Prací prostředky'],i)
            rows.append(p)
        for p in rows[1049:]:
            p.pop('price_czk',None);p['price_status']='price_unverified'
        source={'items':rows,'rules':[{'id':'W001','category':'Kosmetika'}]}
        before=deepcopy(source)
        result,_,audit=compile_catalog(source)
        self.assertEqual(source,before)
        self.assertEqual([p['url'] for p in result['items']],[p['url'] for p in rows])
        self.assertEqual([p.get('price_czk') for p in result['items']],[p.get('price_czk') for p in rows])
        self.assertEqual(audit['priced_before'],1049)
        self.assertEqual(audit['priced_after'],1049)
        self.assertEqual(audit['products_before'],1090)
        self.assertEqual(audit['products_after'],1090)

if __name__=='__main__':unittest.main()
