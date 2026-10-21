from pathlib import Path
import unittest
class SiteTests(unittest.TestCase):
    def test_user_modes_and_date_price_guards(self):
        s=(Path(__file__).resolve().parents[1]/'docs/catalog.html').read_text(encoding='utf8')
        for phrase in ('data-quick="deals"','data-quick="favs"','data-quick="drops"',
             "ageHours(p)<=72",'offer_valid_until>=today()',"original_price_czk>p.price_czk",
             'localStorage.setItem','Kategorie dle pravidla','data-quick="missing"'):
            self.assertIn(phrase,s)
    def test_full_current_catalog_without_embedded_data(self):
        s=(Path(__file__).resolve().parents[1]/'docs/catalog.html').read_text(encoding='utf8')
        self.assertIn('catalog_latest.json',s)
        self.assertIn('const section=list.slice((page-1)*per,page*per)',s)
        self.assertNotIn('nový projekt',s)
if __name__=='__main__':unittest.main()
