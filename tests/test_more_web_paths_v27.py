"""Public Košík breadcrumbs reviewed independently: category-path-only checks."""
import unittest
from catalog_v27 import merchant_category,compile_catalog


class MoreVerifiedWebPaths(unittest.TestCase):
    def case(self, path, expected, rule_id, rule_category):
        item={'store':'Košík','url':'https://www.kosik.cz/p12345-test',
              'name':'Název neobsahuje žádný typ produktu',
              'store_category_path':path,'category_source':'dom_breadcrumb',
              'rule_ids':[rule_id],'price_czk':37.8,'price_status':'ok'}
        self.assertEqual(merchant_category(item)[0],expected)
        view,review,audit=compile_catalog({'items':[item],
                       'rules':[{'id':rule_id,'category':rule_category}]})
        self.assertEqual(view['items'][0]['category_v27']['status'],'verified')
        self.assertEqual(view['items'][0]['price_czk'],37.8)
        self.assertEqual(audit['priced_after'],1)
        self.assertEqual(review['count'],0)

    def test_kosik_processed_cheese_lipno(self):
        self.case(['Mléčné a chlazené','Sýry','Tavené'],
                   'Sýry / tavené','W022','Sýry / tavené')

    def test_kosik_flora_margarine_not_cosmetic(self):
        self.case(['Mléčné a chlazené','Máslo, margaríny, tuky',
                   'Rostlinné tuky a margaríny'],
                   'Másla a tuky','W032','Másla a tuky')

    def test_kosik_bref_toilet_cleaning(self):
        self.case(['Drogerie a kosmetika','Čistící přípravky','Toaleta','WC bloky a gely'],
                   'Úklid','W066','Úklid')

    def test_short_leaf_tavene_without_cheese_parent_is_not_enough(self):
        row={'store_category_path':['Mléčné a chlazené','Tavené'],
             'category_source':'jsonld_breadcrumb'}
        self.assertIsNone(merchant_category(row)[0])

    def test_cosmetic_product_with_margarine_word_cannot_map_as_edible_fat(self):
        row={'store_category_path':['Drogerie a kosmetika','Pleťové krémy',
                                    'Máslo, margaríny, tuky'],
             'category_source':'dom_breadcrumb'}
        self.assertIsNone(merchant_category(row)[0])

if __name__=='__main__':unittest.main()
