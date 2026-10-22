"""UAT12: category extension is rooted in genuine merchant breadcrumb ancestry.
These examples are from v27 path-review evidence, not product-name guesses.
"""
import unittest
from copy import deepcopy
from catalog_v27 import merchant_category, compile_catalog

SRC='jsonld_breadcrumb'

class ObservedPathTests(unittest.TestCase):
    CASES = [
        ('Papír a hygiena', ['Děti', 'Vlhčené ubrousky']),
        ('Papír a hygiena', ['Dítě','Pleny a ubrousky','Vlhčené ubrousky']),
        ('Dentální hygiena', ['Dítě','Dětská kosmetika','Zubní hygiena','Věk 6 a více let']),
        ('Dentální hygiena', ['Kosmetika','Ústní hygiena','Zubní pasty','Bělící']),
        ('Dentální hygiena', ['Kosmetika','Ústní hygiena','Zubní pasty','Běžné']),
        ('Papír a hygiena', ['Drogerie a kosmetika','Papírová a vatová hygiena','Toaletní papíry','Vlhčené']),
        ('Papír a hygiena', ['Drogerie a kosmetika','Papírová a vatová hygiena','Vlhčené ubrousky']),
        ('Papír a hygiena', ['Drogerie a kosmetika','Dámská hygiena','Intimní hygiena']),
        ('Kosmetika', ['Drogerie a kosmetika','Deodoranty a antiperspiranty','Pánské','Spreje']),
        ('Kosmetika', ['Drogerie a kosmetika','Péče o vlasy','Šampony','Pánské']),
        ('Kosmetika', ['Kosmetika','Vlasová péče','Šampony','Pro muže']),
        ('Kosmetika', ['Kosmetika','Deodoranty a parfémy','Pánské','Ve spreji']),
        ('Papír a hygiena', ['Kosmetika','Pleťová péče a dekorativní kosmetika','Čištění a odlíčení pleti','Odličovací tampony a vata']),
        ('Úklid', ['Drogerie','Papírová a vatová hygiena','Ubrousky a utěrky','Vlhčené ubrousky na úklid']),
        ('Majonézy', ['Mléčné a chlazené','Majonézy a dresingy','Majonézy']),
        ('Majonézy', ['Mléčné a chlazené','Majonézy, tatarské omáčky a dresingy','Majonézy']),
        ('Sýry / mozzarella a salátové', ['Mléčné a chlazené','Sýry','Mozzarella a salátové','Mozzarella a burrata']),
        ('Sýry / mozzarella a salátové', ['Mléčné a chlazené','Sýry','Mozzarella, ricotta a salátové sýry','Mozzarella, burrata a ricotta']),
        ('Sladké', ['Trvanlivé','Sladké','Oplatky a sušenky','Oplatky']),
        ('Másla a tuky', ['Plant Based','Alternativy mléčného a chlazeného','Rostlinné tuky a margaríny']),
    ]
    UNCERTAIN = [
        ['Mléčné a chlazené','Sýry','Plísňové, zrající, pařené a uzené','Plísňové a zrající'],
        ['Mléčné a chlazené','Sýry','Grilovací sýry, raclette, fondue','Grilovací sýry'],
        ['Maso a ryby','Vepřové maso','Uzené'],
        ['Zdraví a životní styl','Veggie','Sýry, krémy a tuky','Krémy'],
        ['Speciální výživa','Bezlaktózové výrobky','Sýry bez laktózy'],
    ]
    def item(self,path,source=SRC):
        return {'store_category_path':path,'category_source':source,'title':'IGNORE-PRODUCT-TITLE',
                'name':'IGNORE-PRODUCT-NAME','store':'Rohlík','url':'https://www.rohlik.cz/example', 'rule_ids':['W001']}
    def test_observed_clear_paths(self):
        for expected,path in self.CASES:
            with self.subTest(path=path):
                self.assertEqual(merchant_category(self.item(path))[0],expected)
    def test_uncertain_stays_review(self):
        for path in self.UNCERTAIN:
            with self.subTest(path=path):
                self.assertIsNone(merchant_category(self.item(path))[0])
    def test_never_guess_untrusted_or_incomplete(self):
        for expected,path in self.CASES:
            for src in ['missing','error','product_category_links',None]:
                self.assertIsNone(merchant_category(self.item(path,src))[0])
            self.assertIsNone(merchant_category(self.item(path[:1]))[0])
    def test_title_does_not_change_category(self):
        for expected,path in self.CASES:
            i=self.item(path)
            i['title']='BANÁNY MÁSL0 ŠUNKA'
            self.assertEqual(merchant_category(i)[0],expected)
            i['title']='WC ČISTIČ A PRACÍ PRÁŠEK'
            self.assertEqual(merchant_category(i)[0],expected)
    def test_compilation_preserves_price_and_identity(self):
        rows=[]
        for idx,(cat,path) in enumerate(self.CASES):
            row=self.item(path)
            row['url']=f'https://www.rohlik.cz/{idx+10000}-sample'
            row['price_status']='ok';row['price_czk']=19.9+idx
            row['checked_at']='2026-10-22T10:00:00+00:00'
            rows.append(row)
        source={'items':rows,'rules':[{'id':'W001','category':'Sladké'}]}
        before=deepcopy(source)
        result,review,audit=compile_catalog(source)
        self.assertEqual(source,before)
        self.assertEqual(len(result['items']),len(rows))
        self.assertEqual([p['price_czk'] for p in result['items']],[p['price_czk'] for p in rows])
        self.assertEqual(audit['priced_before'],audit['priced_after'])
        self.assertTrue(all(x['category_v27']['category'] for x in result['items']))

if __name__=='__main__':unittest.main()
