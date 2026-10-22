"""Offline integration/regression tests for safe v27 category publishing."""
import copy
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('publish_taxonomy_v27',SRC/'publish_taxonomy_v27.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

HTML='''<!doctype html><html><body>
<div class="progress" id="progress"></div><div id="mobileCards"></div><span id="stamp"></span>
<div class="field"><label for="category">Kategorie</label><select id="category"><option value="">Všechny kategorie</option></select></div>
<script>
'use strict';
let db={items:[],rules:[]};let rules=new Map();
const $=id=>({textContent:'',title:''});
for(const id of ['shop','category','brand','state','minPrice','maxPrice','validity','sort','search','until','pagesize'])id.length;
for(const id of ['shop','category','brand','state','minPrice','maxPrice','validity','search','until'])id.length;
const productId=p=>p.store+'|'+p.url;
const nf=n=>String(n);
const cats=p=>[...new Set((p.rule_ids||[]).map(id=>rules.get(id)?.category).filter(Boolean))];
const today=()=>'';
function render(){
 const p={};const shopPath='';
 const f={category:$('category').value,brand:''};
 if(f.category&&!cats(p).includes(f.category))return false;
 const provenance=shopPath?'Kategorie e-shopu: '+shopPath:'Kategorie podle sledovacího pravidla (e-shop nepotvrzen)';
 const badge=`${shopPath?'✓ Kategorie prodejce':'◇ Kategorie dle pravidla'}`;
 const cardPath='Kategorie dle sledovacího pravidla (neověřeno e-shopem)';
}
async function load(){try{
 const rsp=await fetch('./data/catalog_latest.json?ts='+Date.now(),{cache:'no-store'});
 if(!rsp.ok)throw Error('HTTP '+rsp.status);
 db=await rsp.json();if(!Array.isArray(db.items))throw Error('Neplatný katalog');rules=new Map((db.rules||[]).map(r=>[r.id,r]));
 const ct=[...new Set((db.rules||[]).map(r=>r.category).filter(Boolean))],ordered=db.category_order||[];ct.sort((a,b)=>(ordered.indexOf(a)<0?999:ordered.indexOf(a))-(ordered.indexOf(b)<0?999:ordered.indexOf(b))||a.localeCompare(b,'cs'));
 $('category').innerHTML='<option value="">Všechny kategorie</option>'+ct.map(x=>`<option value="${x}">${x}</option>`).join('');
 $('stamp').textContent='Aktualizace: '+new Date(db.generated_at).toLocaleString('cs-CZ');
}catch(e){}}
</script>
</body></html>'''


def items():
    live=[];compiled=[]
    for i in range(1090):
        shop='Košík' if i<556 else 'Rohlík'
        url=f'https://www.kosik.cz/p{i}-test' if shop=='Košík' else f'https://www.rohlik.cz/{i}-test'
        x={'store':shop,'url':url,'name':f'Product {i}', 'price_status':'ok' if i<1049 else 'price_unverified',
           'price_czk':float(i+1) if i<1049 else None,'discount_pct':12.5 if i%10==0 else None,
           'checked_at':'2026-10-22T08:00:00+00:00','price_history_previous_czk':None,'rule_ids':['W001']}
        live.append(x)
        new=copy.deepcopy(x)
        # Simulate stale v27 staged prices to prove they never leak to public.
        new['price_czk']=4.50
        new['price_status']='ok'
        if i<457:
            cat='Ovoce' if i%2 else 'Zelenina'
            new.update(store_category_path=['Ovoce a zelenina','Ovoce' if i%2 else 'Zelenina'],category_source='dom_breadcrumb')
            status='verified' if i<352 else ('mismatch' if i<375 else 'review')
        else:
            cat=None
            status='review'
        new['category_v27']={'category':cat,'display_category':cat or 'Ke kontrole', 'status':status,
                             'expected_from_rules':['Ovoce'],'reason':'From merchant path','evidence_state':'mapped' if cat else 'merchant_path_missing'}
        compiled.append(new)
    return {'generated_at':'2026-10-21T14:12:55+00:00','last_price_monitor_at':'2026-10-22T08:20:05+00:00','items':live}, {'items':compiled}


class PublishTests(unittest.TestCase):
    def test_realistic_1090_overlay_1049_prices_unchanged(self):
        live,compiled=items();old=json.dumps(live,ensure_ascii=False)
        x=mod.build_overlay(live,compiled,now=datetime(2026,10,22,tzinfo=timezone.utc))
        self.assertEqual(x['total'],1090)
        self.assertEqual(x['counts']['mapped'],457)
        self.assertEqual(x['counts']['unmapped'],633)
        self.assertEqual(x['counts']['verified'],352)
        self.assertEqual(x['counts']['mismatch'],23)
        self.assertEqual(sum(p['price_status']=='ok' for p in live['items']),1049)
        self.assertEqual(json.dumps(live,ensure_ascii=False),old)
        self.assertEqual(set(x['items'][0]),{'store','url','category_v27','store_category_path','category_source'})
        self.assertTrue(all('price_czk' not in p and 'checked_at' not in p for p in x['items']))

    def test_live_identity_mismatch_fails_closed(self):
        live,compiled=items();compiled['items'][14]['url']='https://evil.example/product'
        with self.assertRaisesRegex(ValueError,'identity'):
            mod.build_overlay(live,compiled)

    def test_product_count_loss_fails_closed(self):
        live,compiled=items();compiled['items'].pop()
        with self.assertRaisesRegex(ValueError,'count'):
            mod.build_overlay(live,compiled)

    def test_duplicate_product_fails_closed(self):
        live,compiled=items();live['items'][1]=copy.deepcopy(live['items'][0])
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            mod.build_overlay(live,compiled)

    def test_category_without_trusted_path_fails_closed(self):
        live,compiled=items();compiled['items'][0]['category_source']='name_heuristic'
        with self.assertRaisesRegex(ValueError,'verified merchant path'):
            mod.build_overlay(live,compiled)

    def test_broad_category_held_for_review_is_not_claimed_verified(self):
        live,compiled=items();overlay=mod.build_overlay(live,compiled)
        self.assertEqual(overlay['items'][360]['category_v27']['status'],'mismatch')
        self.assertEqual(overlay['items'][360]['category_v27']['category'],'Zelenina')
        self.assertEqual(overlay['items'][700]['category_v27']['display_category'],'Ke kontrole')

    def test_patch_requires_existing_mobile_layout(self):
        with self.assertRaisesRegex(ValueError,'Mobile layout'):
            mod.patch_html(HTML.replace('<div id="mobileCards"></div>',''))

    def test_patch_keeps_existing_sale_30_40_and_is_idempotent(self):
        once=mod.patch_html(HTML)
        twice=mod.patch_html(once)
        self.assertEqual(once,twice)
        self.assertIn('id="mobileCards"',once)
        self.assertIn('categoryV27Badge',once)
        self.assertIn('id="categoryStatus"',once)
        self.assertIn("f.categoryStatus==='mismatch'",once)
        self.assertIn('await loadCategoryOverlay()',once)
        self.assertIn('Kategorie e-shopu',once)
        self.assertIn('Poslední kontrola cen',once)
        self.assertNotIn('Kategorie podle sledovacího pravidla (e-shop nepotvrzen)',once)
        self.assertNotIn('let db={items:[],rules:[]};let rules=new Map();\nconst categoryV27Label=p',once)  # original placement retained

    def test_patch_script_syntax_valid_node(self):
        patched=mod.patch_html(HTML)
        js=patched.split('<script>',1)[1].split('</script>',1)[0]
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'page.js';p.write_text(js,encoding='utf8')
            res=subprocess.run(['node','--check',str(p)],text=True,capture_output=True)
            self.assertEqual(res.returncode,0,res.stderr)

    def test_cli_outputs_and_never_writes_source_prices(self):
        live,compiled=items()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            a=root/'live.json';b=root/'compiled.json';c=root/'live.html'
            x=root/'tax.json';y=root/'patched.html';z=root/'report.json'
            a.write_text(json.dumps(live,ensure_ascii=False),encoding='utf8')
            b.write_text(json.dumps(compiled,ensure_ascii=False),encoding='utf8')
            c.write_text(HTML,encoding='utf8')
            before=a.read_bytes()
            result=subprocess.run([sys.executable,str(SRC/'publish_taxonomy_v27.py'),
                '--live',str(a),'--compiled',str(b),'--html',str(c),
                '--output-overlay',str(x),'--output-html',str(y),'--report',str(z)],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(a.read_bytes(),before)
            self.assertEqual(c.read_text(encoding='utf8'),HTML)
            self.assertEqual(json.loads(x.read_text(encoding='utf8'))['total'],1090)
            self.assertTrue(json.loads(z.read_text(encoding='utf8'))['live_prices_preserved'])

    def test_if_overlay_is_missing_page_labels_as_review(self):
        patch=mod.patch_html(HTML)
        self.assertIn("'Ke kontrole'",patch)
        self.assertIn('Kategorie e-shopů nejsou ověřené',patch)

    def test_no_old_query_category_source_in_filter(self):
        patch=mod.patch_html(HTML)
        self.assertIn('map(p=>categoryV27Label(p))',patch)
        self.assertNotIn('map(r=>r.category).filter(Boolean)',patch)

if __name__=='__main__':unittest.main()
