"""Offline regression tests for missing-only v27 backfill.

On GitHub these import the real v26 maintenance module. In the downloadable
isolated test bundle a compatibility stub is used only if v26 isn't present.
"""
import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

try:
    import maintenance_v26
except ImportError:
    maintenance_v26 = types.ModuleType('maintenance_v26')
    def hours_since(row, key='last_monitor_attempt_at', now=None):
        try:
            return ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(row[key])).total_seconds()/3600
        except (ValueError, KeyError, TypeError):
            return float('inf')
    def apply_result(original, *, price=None, source=None, offer=None, status='unknown', checked_at=None, note=''):
        out=dict(original)
        out.update(last_monitor_attempt_at=checked_at,monitor_v26_attempts=original.get('monitor_v26_attempts',0)+1,monitor_v26_status=status,monitor_v26_note=note)
        if status=='ok' and type(price) in (int,float) and .5<=price<=50000:
            out.update(price_status='ok',price_czk=price,price_source=source,checked_at=checked_at)
        return out
    maintenance_v26.hours_since = hours_since
    maintenance_v26.apply_result = apply_result
    maintenance_v26.inspect_saved = lambda page, row: {'status':'price_unverified'}
    sys.modules['maintenance_v26']=maintenance_v26

try:
    import price_backfill_v27 as module
except ImportError:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import price_backfill_v27 as module

NOW = datetime(2026,10,22,8,0,tzinfo=timezone.utc)


def row(shop='Rohlík', n=1, category='W061', status='http_error', value=None):
    host='rohlik.cz' if shop=='Rohlík' else 'kosik.cz'
    url=f'https://www.{host}/p{n:07d}-sample'
    return {'store':shop,'url':url,'name':f'Produkt {n}', 'rule_ids':[category],
            'price_status':status,'price_czk':value,'http_status':429 if status=='http_error' else 200}


class PriceBackfillTests(unittest.TestCase):
    def setUp(self):
        self.rules={'W061':'Praní','W037':'Ovoce','W074':'Papírové utěrky'}

    def test_all_valid_prices_are_excluded(self):
        products=[row(n=i,status='ok',value=120.9) for i in range(1,13)]
        self.assertEqual(module.pick_missing(products,self.rules,limit=10,now=NOW),[])

    def test_prioritises_missing_rohlik_not_priced_kosik(self):
        missing=[row(n=i) for i in range(1,120)]
        priced=[row(shop='Košík',n=i,status='ok',value=45.2) for i in range(1,70)]
        got=module.pick_missing(priced+missing,self.rules,limit=100,now=NOW)
        self.assertEqual(len(got),100)
        self.assertEqual({p['store'] for p in got},{'Rohlík'})
        self.assertTrue(all(p['price_status']!='ok' for p in got))

    def test_small_kosik_backlog_does_not_starve_rohlik(self):
        missing=[row(n=i) for i in range(1,130)]
        missing += [row(shop='Košík',n=1000+i,status='price_unverified') for i in range(2)]
        got=module.pick_missing(missing,self.rules,limit=100,now=NOW)
        counts={s:sum(x['store']==s for x in got) for s in ('Rohlík','Košík')}
        self.assertEqual(counts,{'Rohlík':98,'Košík':2})

    def test_rotates_categories(self):
        missing=[row(n=i) for i in range(1,11)]
        missing += [row(n=100+i,category='W037') for i in range(5)]
        missing += [row(n=200+i,category='W074') for i in range(5)]
        got=module.pick_missing(missing,self.rules,limit=9,now=NOW)
        self.assertEqual(len({self.rules[p['rule_ids'][0]] for p in got[:3]}),3)

    def test_recent_failures_cool_down(self):
        p=row();p['last_monitor_attempt_at']=(NOW-timedelta(hours=1)).isoformat()
        eligible=row(n=2)
        self.assertEqual(module.pick_missing([p,eligible],self.rules,limit=10,now=NOW),[eligible])

    def test_url_whitelist(self):
        invalid=[row(n=1), row(n=2), row(n=3)]
        invalid[0]['url']='http://www.rohlik.cz/id'
        invalid[1]['url']='https://www.rohlik.cz.evil.com/id'
        invalid[2]['store']='Košík'
        self.assertEqual(module.pick_missing(invalid,self.rules,limit=9,now=NOW),[])

    def test_invalid_limit(self):
        for n in (0,101):
            with self.assertRaises(ValueError):module.pick_missing([],self.rules,limit=n,now=NOW)

    def test_verified_product_never_changed_even_when_offered_new_price(self):
        original=row(n=1,status='ok',value=45.9)
        new,added=module.apply_observation(original,{'status':'ok','price':18.1,'source':'x'},checked_at=NOW.isoformat())
        self.assertFalse(added)
        self.assertEqual(new,original)

    def test_unambiguous_price_adds_missing(self):
        original=row(n=1)
        new,added=module.apply_observation(original,{'status':'ok','price':39.9,'source':'merchant-detail'},checked_at=NOW.isoformat())
        self.assertTrue(added)
        self.assertEqual(new['price_status'],'ok')
        self.assertEqual(new['price_czk'],39.9)
        self.assertEqual(original['price_status'],'http_error')

    def test_ambiguous_price_never_invented(self):
        original=row(n=1)
        new,added=module.apply_observation(original,{'status':'price_unverified','price':None,'note':'ambiguous'},checked_at=NOW.isoformat())
        self.assertFalse(added)
        self.assertEqual(new['price_status'],'http_error')
        self.assertIsNone(new['price_czk'])

    def test_report_guards_against_loss_of_verified_price(self):
        a={'items':[row(n=1,status='ok',value=19.9),row(n=2)]}
        b=copy.deepcopy(a)
        b['items'][0]['price_czk']=22.5
        with self.assertRaisesRegex(ValueError,'Previously priced'):
            module.build_report(a,b,attempted=2,statuses={},blocked=set(),requested=10,candidates=2,first_errors=[],started_at=NOW.isoformat())

    def test_report_counts_only_new_prices_not_refreshes(self):
        old={'items':[row(n=1,status='ok',value=19.9),row(n=2)]}
        new=copy.deepcopy(old);new['items'][1]['price_czk']=48.5;new['items'][1]['price_status']='ok'
        rep=module.build_report(old,new,attempted=1,statuses={'Rohlík|ok':1},blocked=set(),requested=10,candidates=1,first_errors=[],started_at=NOW.isoformat())
        self.assertEqual(rep['newly_priced'],1)
        self.assertEqual(rep['remaining_missing'],0)

    def test_historical_http_429_is_not_permanent_block(self):
        got=module.pick_missing([row(n=1)],self.rules,limit=1,now=NOW)
        self.assertEqual(len(got),1)

    def test_no_price_guess_from_true_boolean(self):
        o=row(n=1)
        new, added = module.apply_observation(o, {'status':'ok','price':True,'source':'x'},checked_at=NOW.isoformat())
        self.assertFalse(added)

    @staticmethod
    def _mock_browser():
        class FakeContext:
            def new_page(self): return object()
            def close(self): pass
        class FakeBrowser:
            def new_context(self, **kwargs): return FakeContext()
            def close(self): pass
        class FakeChromium:
            def launch(self, **kwargs): return FakeBrowser()
        class FakePlaywright:
            chromium=FakeChromium()
            def __enter__(self): return self
            def __exit__(self,*args): return None
        api=types.ModuleType('playwright.sync_api')
        api.sync_playwright=lambda:FakePlaywright()
        p=types.ModuleType('playwright')
        p.sync_api=api
        return {'playwright':p,'playwright.sync_api':api}

    def test_end_to_end_bulk_80_missing_prices_without_changing_existing_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/'catalog.json'; report=Path(tmp)/'report.json'
            items=[row(n=i,status='ok',value=10+i) for i in range(1,901)]
            items += [row(n=i,status='http_error') for i in range(901,1091)]
            source={'generated_at':'2026-10-21T14:12:55+00:00',
                    'rules':[{'id':'W061','category':'Praní'}], 'items':items}
            dst.write_text(json.dumps(source,ensure_ascii=False),encoding='utf-8')
            args=types.SimpleNamespace(catalog=str(dst),report=str(report),limit=80,delay=4.0)
            with patch.dict(sys.modules,self._mock_browser()), \
                 patch.object(module,'inspect_saved',return_value={'status':'ok','price':49.90,'source':'merchant-detail'}), \
                 patch.object(module.time,'sleep',return_value=None):
                rc=module.run(args)
            after=json.loads(dst.read_text(encoding='utf-8'))
            d=json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(rc,0)
            self.assertEqual(d['newly_priced'],80)
            self.assertEqual(d['remaining_missing'],110)
            self.assertEqual(after['items'][:900],source['items'][:900])
            self.assertEqual(after['generated_at'],source['generated_at'])
            self.assertEqual([x['price_czk'] for x in after['items'][900:980]],[49.9]*80)

    def test_http_429_stops_same_shop_without_touching_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/'catalog.json'; report=Path(tmp)/'report.json'
            items=[row(n=i,status='ok',value=10+i) for i in range(1,1089)]
            items += [row(n=1089),row(n=1090)]
            source={'generated_at':'2026-10-21T14:12:55+00:00',
                    'rules':[{'id':'W061','category':'Praní'}], 'items':items}
            dst.write_text(json.dumps(source,ensure_ascii=False),encoding='utf-8')
            previous=dst.read_bytes()
            args=types.SimpleNamespace(catalog=str(dst),report=str(report),limit=80,delay=4.0)
            tracker=[]
            def blocked(page,item):
                tracker.append(item['url'])
                return {'status':'http_error','blocked':True,'note':'HTTP 429'}
            with patch.dict(sys.modules,self._mock_browser()), \
                 patch.object(module,'inspect_saved',side_effect=blocked), \
                 patch.object(module.time,'sleep',return_value=None):
                rc=module.run(args)
            d=json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(rc,2)
            self.assertEqual(len(tracker),1)
            self.assertEqual(d['blocked_stores'],['Rohlík'])
            self.assertEqual(d['newly_priced'],0)
            self.assertEqual(dst.read_bytes(),previous)

    def test_eligible_products_selected_from_1090_sample_without_duplication(self):
        ps=[row(n=i,status='ok',value=150.0) for i in range(1,900)]
        ps += [row(n=i,status='http_error') for i in range(900,1091)]
        self.assertEqual(len(ps),1090)
        chosen=module.pick_missing(ps,self.rules,limit=80,now=NOW)
        self.assertEqual(len(chosen),80)
        self.assertEqual(len({p['url'] for p in chosen}),80)
        self.assertTrue(all(not module.priced(p) for p in chosen))


if __name__=='__main__':unittest.main()
