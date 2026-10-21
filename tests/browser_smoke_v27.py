"""Optional real Chromium smoke test for the v27 catalog UI.

Runs against synthetic offline fixture, NOT a confirmation of live merchant data.
Usage: python tests/browser_smoke_v27.py
"""
from __future__ import annotations
import json
import base64
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from catalog_v27 import compile_catalog
from test_end_to_end_v27 import EndToEndV27


def test():
    catalog=EndToEndV27().make_catalog()
    # Synthetic currently date-valid promotion, compared with undated promotion.
    catalog['items'][0].update(discount_pct=18,original_price_czk=100,price_czk=82,
                               checked_at='2099-10-21T14:00:00Z',offer_valid_until='2099-10-25')
    catalog['items'][1].update(discount_pct=15,original_price_czk=100,price_czk=85,
                               checked_at='2099-10-21T14:00:00Z',offer_valid_until=None)
    new,_,report=compile_catalog(catalog)
    with tempfile.TemporaryDirectory() as folder:
        base=Path(folder)
        (base/'data').mkdir()
        (base/'catalog-v27.html').write_bytes((ROOT/'docs/catalog-v27.html').read_bytes())
        (base/'data/catalog_v27.json').write_text(json.dumps(new,ensure_ascii=False),encoding='utf8')
        payload=base64.b64encode(json.dumps(new,ensure_ascii=False).encode('utf8')).decode('ascii')
        html=(base/'catalog-v27.html').read_text(encoding='utf8')
        mock='<script>window.fetch=async()=>({ok:true,json:async()=>JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(\''+payload+'\'),x=>x.charCodeAt(0))))});</script>'
        html=html.replace('<script>\n\'use strict\';',mock+'<script>\n\'use strict\';')
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--allow-file-access-from-files'])
                page=browser.new_page(viewport={'width':1650,'height':1000},locale='cs-CZ')
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content(html,wait_until='domcontentloaded')
                page.wait_for_function("document.getElementById('nAll').textContent === '1090'")
                assert page.locator('#nPriced').inner_text() == '894'
                assert page.locator('#nMissing').inner_text() == '196'
                assert page.locator('#priceCoverage .shopcover').count()==2
                assert page.locator('#qDeals').inner_text() == '1', 'Undated discount must NOT count as a current sale'
                assert page.locator('#nRules').inner_text() == '6 / 6'
                # Known-category filter must stay distinct from unverified rows.
                # Secondary legacy watch-group filter preserves browsing of
                # unverified items without claiming an authoritative aisle.
                assert page.locator('#rulecat option').count()>1
                page.locator('#rulecat').select_option('Ovoce')
                assert 0<int(page.locator('#shown').inner_text().split(' ')[1])<=1090
                page.locator('#rulecat').select_option('')
                page.locator('#category').select_option('Ke kontrole')
                page.wait_for_timeout(60)
                assert 'Ke kontrole' in page.locator('#shown').inner_text() or int(page.locator('#shown').inner_text().split(' ')[1])>0
                # Basic product search, pagination, two shops, and quick filters.
                page.locator('#category').select_option('')
                page.locator('#shop').select_option('Košík')
                assert int(page.locator('#shown').inner_text().split(' ')[1])>0
                page.locator('#shop').select_option('')
                page.locator('[data-view="missing"]').click()
                assert page.locator('#shown').inner_text().startswith('Zobrazeno 196 ')
                page.locator('[data-view="all"]').click()
                assert page.locator('#rows tr').count()==100
                page.locator('#next').click()
                assert page.locator('#pages').inner_text()=='2 / 11'
                page.locator('#prev').click()
                assert page.locator('#pages').inner_text()=='1 / 11'
                page.locator('#q').fill('SYNTETIC UNVERIFIED 1000')
                assert page.locator('#shown').inner_text().startswith('Zobrazeno 1 ')
                page.locator('#q').fill('')
                page.set_viewport_size({'width':390,'height':844})
                page.wait_for_timeout(50)
                assert page.locator('#cards').is_visible()
                assert page.locator('.mobile-card').count()==100
                assert not errors, 'Browser JS errors: '+repr(errors)
                browser.close()
                print('CHROMIUM OK:',json.dumps({'products':report['products_after'],
                      'prices':report['priced_after'],'missing':report['missing_prices'],
                      'verified_sale_with_date':1,'mobile_cards':100,
                      'pages':11,'js_errors':len(errors)},ensure_ascii=False))
        finally:
            pass

if __name__=='__main__':test()
