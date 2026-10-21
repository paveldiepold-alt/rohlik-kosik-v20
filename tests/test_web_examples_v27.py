"""Two manually examined public Košík breadcrumbs, not a complete live crawl."""
import unittest
from catalog_v27 import compile_catalog, merchant_category


class PublicBreadcrumbExamples(unittest.TestCase):
    def test_kosik_meat_breadcrumb_confirms_thigh_rule_only(self):
        path=['Maso a ryby','Drůbeží maso','Kuře','Stehna a čtvrtky']
        item={'store':'Košík',
              'url':'https://www.kosik.cz/p545786-authentic-farmarska-kureci-stehna',
              'name':'Authentic Farmářská kuřecí stehna','rule_ids':['W002'],
              'store_category_path':path,'category_source':'jsonld_breadcrumb',
              'price_status':'ok','price_czk':156.33}
        self.assertEqual(merchant_category(item)[0],'Maso')
        rules=[{'id':'W002','category':'Maso'}]
        view,_,audit=compile_catalog({'items':[item],'rules':rules})
        self.assertEqual(view['items'][0]['category_v27']['rule_checks']['W002']['status'],'verified')
        self.assertEqual(view['items'][0]['price_czk'],156.33)
        self.assertEqual(audit['priced_after'],1)

    def test_kosik_paper_towels_not_just_general_hygiene(self):
        path=['Drogerie a kosmetika','Papírová a vatová hygiena','Kuchyňské utěrky']
        item={'store':'Košík',
              'url':'https://www.kosik.cz/p635600-aro-kuchynske-uterky-2-vrstve-8-roli',
              'name':'ARO Kuchyňské utěrky 2-vrstvé 8 Rolí','rule_ids':['W074'],
              'store_category_path':path,'category_source':'dom_breadcrumb',
              'price_status':'ok','price_czk':114.9,
              'multibuy':[{'min_qty':2,'price_czk':84.9}]}
        view,_,audit=compile_catalog({'items':[item],
            'rules':[{'id':'W074','category':'Papírové utěrky'}]})
        self.assertEqual(view['items'][0]['category_v27']['category'],'Papírové utěrky')
        self.assertEqual(view['items'][0]['category_v27']['status'],'verified')
        self.assertEqual(view['items'][0]['price_czk'],114.9)
        self.assertEqual(view['items'][0]['multibuy'][0]['price_czk'],84.9)
        self.assertEqual(audit['priced_before'],1)

if __name__=='__main__':unittest.main()
