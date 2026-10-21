import unittest
from price_v22 import choose_kosik_pack_price,UNIT_RE

class PackPriceTests(unittest.TestCase):
    def check(self,block,expected):
        self.assertEqual(choose_kosik_pack_price(block)[0],expected,block)
    def test_ariel_splits(self):
        self.check('90 dávek\n699\n00\n7,77 Kč/dávka\nDo košíku\n0 ks\n0,00 Kč',699.0)
        self.check('100 dávek\n699 00\n6,99 Kč/dávka\nDo košíku',699.0)
        self.check('40 dávek\n199 90\n5,00 Kč/dávka\nDo košíku',199.9)
    def test_unit_only_never_equals_total(self):
        self.check('90 dávek\n7,77 Kč/dávka\nDo košíku\n0 ks\n0,00 Kč',None)
        self.check('90 dávek\n699 Kč/dávka',None)
    def test_standard_weight_prices(self):
        self.check('125 g\n49 90\n399,20 Kč/kg\nDo košíku',49.9)
        self.check('250 ml\n39\n90\n159,60 Kč/l',39.9)
    def test_multibuy_single_price_explicit(self):
        self.check('15,90 Kč od 4 ks\n17,90 Kč od 2 ks\n19,90 Kč za 1 ks\nDo košíku',19.9)
    def test_no_old_price_inference(self):
        self.check('100 dávek\n469 00\n699,00 Kč\n-32 %',469.0)
    def test_no_cart_or_recommendations(self):
        self.check('Vyprodáno\nDo košíku\n0 ks\n0,00 Kč',None)
    def test_unit_label_detection(self):
        self.assertTrue(UNIT_RE.search('7,77 Kč/dávka'))
        self.assertTrue(UNIT_RE.search('3,99 Kč/praní'))
        self.assertTrue(UNIT_RE.search('5,99 Kč/ks'))
        self.assertFalse(UNIT_RE.search('699,00 Kč'))

if __name__=='__main__':unittest.main()
