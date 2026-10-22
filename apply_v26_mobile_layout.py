#!/usr/bin/env python3
"""Apply safe mobile-only presentation update to v26 docs/catalog.html.

This DOES NOT update the catalogue data, workflows, or production branch.
Usage: python apply_v26_mobile_layout.py INPUT_HTML OUTPUT_HTML
Both paths may be the same after taking a backup.
"""
from pathlib import Path
import sys

CSS = r'''
/* Mobile catalogue cards + accessibility; legacy desktop filters still work. */
.v26-mobile,.v26-mobile-tools{display:none}
.v26-card{padding:13px;border:1px solid #e4eaf1;border-radius:12px;background:white;margin:0 0 9px}
.v26-card-head,.v26-card-product,.v26-card-foot{display:flex;align-items:center;gap:10px}
.v26-card-head{justify-content:space-between;margin-bottom:10px}
.v26-card-store{border-radius:999px;background:#eef3f9;color:#294966;font-weight:750;font-size:11px;padding:6px 10px}
.v26-card-product{align-items:flex-start}
.v26-card-product .photo{width:72px;height:72px;border-radius:9px;flex-shrink:0;object-fit:contain}
.v26-card-text{min-width:0;flex:1}
.v26-card-name{font-size:14px;font-weight:780;line-height:1.4;color:#172c49;overflow-wrap:anywhere}
.v26-card-category{font-size:11px;color:#506d86;margin-top:5px}
.v26-card-foot{justify-content:space-between;margin-top:12px;border-top:1px solid #e9edf2;padding-top:11px}
.v26-card-price{font-size:21px;font-weight:800;color:#087953;white-space:nowrap}
.v26-card-price.missing{font-size:14px;color:#966b27}
.v26-card-price-note{font-size:10px;color:#8492a3;margin-top:4px}
.v26-card-link{font-size:12px;background:#173f66;color:white!important;border-radius:8px;padding:12px 13px;white-space:nowrap;text-decoration:none;min-height:42px;text-align:center}
.v26-card-more{border-top:1px dashed #e6ebf2;margin-top:11px;padding-top:9px;font-size:11px;color:#5e758e}
.v26-card-more summary{font-size:12px;cursor:pointer;color:#22547e;font-weight:750;min-height:27px}
.v26-card-details{padding-top:6px;line-height:1.65;overflow-wrap:anywhere}
.v26-card .fav{min-height:44px;min-width:44px;font-size:25px}
@media(max-width:900px){
 html,body{max-width:100%;overflow-x:clip}
 header{padding:17px 14px}header h1{font-size:20px}header p{font-size:11px}
 main{padding:12px 11px 22px}.notice{padding:11px 12px;font-size:11px;line-height:1.5}
 .stats{grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
 .stat{padding:11px 9px;min-width:0}.stat strong{font-size:21px}.stat span{font-size:10px;line-height:1.3}
 .quick{flex-wrap:nowrap;overflow-x:auto;scroll-snap-type:x proximity;scrollbar-width:none;-webkit-overflow-scrolling:touch;gap:7px;padding-bottom:9px}
 .quick::-webkit-scrollbar{display:none}.quick button{flex:0 0 auto;white-space:nowrap;scroll-snap-align:start;padding:11px 12px;min-height:43px;font-size:12px}
 .panel{padding:12px}.top h2{font-size:16px}.progress{gap:7px}
 .filters{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
 .field.wide{grid-column:1/-1;grid-row:1}
 .filters .field :is(input,select){height:44px;font-size:16px}
 .filters.v26-filter-collapsed .field:not(.wide){display:none}
 .v26-mobile-tools{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:12px}
 .v26-mobile-tools button{min-height:44px;padding:10px 13px;border:1px solid #d0dbe7;border-radius:9px;background:#eff4f9;color:#234768;font-weight:750;font-size:12px}
 .v26-mobile-tools span{font-size:11px;color:#71839a}
 .actions{gap:8px;align-items:flex-start}.actions .count{line-height:1.55;font-size:11px}
 .actions #clear{white-space:nowrap;min-height:41px}
 .tablewrap{display:none}.v26-mobile{display:block}
 .pagination{justify-content:space-between}.pagination button{min-height:44px;font-size:12px;padding:10px 12px}
 footer{font-size:10px;line-height:1.55}
}
@media(max-width:370px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.v26-card-product .photo{width:64px;height:64px}.v26-card-price{font-size:18px}}
'''
CARDS = r'''
 $('mobileCards').innerHTML=section.length?section.map(p=>{
 const good=isPrice(p),id=productId(p),saved=favs.has(id),shopPath=(p.store_category_path||[]).join(' → ');
 const url=/^https:\/\/(www\.)?(rohlik|kosik)\.cz\//.test(p.url||'')?p.url:'';
 return `<article class="v26-card"><div class="v26-card-head"><span class="v26-card-store">${esc(p.store)}</span><button type="button" class="fav ${saved?'on':''}" data-id="${esc(id)}" aria-label="Oblíbené">${saved?'★':'☆'}</button></div>
 <div class="v26-card-product">${photo(p)}<div class="v26-card-text"><div class="v26-card-name">${esc(p.title||p.name||'—')}</div><div class="v26-card-category">${esc(cats(p).join(', ')||'Kategorie k prověření')}</div></div></div>
 <div class="v26-card-foot"><div><div class="v26-card-price ${good?'':'missing'}">${good?money(p.price_czk):'Cena nezjištěna'}</div><div class="v26-card-price-note">${freshPrice(p)?'Cena ≤ 72 h':good?'Starší cenové pozorování':'Bez potvrzené ceny'}</div>${datedPromo(p)?`<span class="discount">Sleva −${disc(p)} %</span>`:''}</div>${url?`<a class="v26-card-link" target="_blank" rel="noopener noreferrer" href="${esc(url)}">Otevřít v e-shopu ↗</a>`:''}</div>
 <details class="v26-card-more"><summary>Podrobnosti výrobku a kategorie</summary><div class="v26-card-details"><div>${esc(shopPath?'Kategorie e-shopu: '+shopPath:'Kategorie dle sledovacího pravidla (neověřeno e-shopem)')}</div><div>${esc((p.checked_at||'Bez data').replace('T',' ').slice(0,19))}</div><div>Podmínky: ${conditions(p)}</div></div></details></article>`;
 }).join(''):'<div class="empty">Žádné výrobky pro zvolené filtry.</div>';
'''

def patch(src: str) -> str:
    def single(old,new):
        nonlocal src
        if src.count(old)!=1:
            raise RuntimeError(f'Expected exactly one HTML anchor, got {src.count(old)}: {old[:95]!r}')
        src=src.replace(old,new,1)
    if 'id="mobileCards"' in src:
        raise RuntimeError('Mobile patch already applied; refusing a second application')
    single('th:nth-child(3){width:31%}', 'th:nth-child(4){width:31%}')
    single('</style>',CSS+'</style>')
    single('<div class="filters">','<div class="v26-mobile-tools"><button type="button" id="mobileFilters" aria-controls="filtersV26" aria-expanded="false">☷ Další filtry a řazení</button><span>20 výrobků na mobilní stránku</span></div><div class="filters v26-filter-collapsed" id="filtersV26">')
    single(' </div>\n  <div class="actions">',' </div>\n  <div class="actions">') if False else None
    single('<div class="pagination">','<div class="v26-mobile" id="mobileCards"></div>\n  <div class="pagination">')
    single("const list=chosen(),per=Number($('pagesize').value);","const list=chosen(),per=window.matchMedia('(max-width:900px)').matches?20:Number($('pagesize').value);")
    single("$('pageInfo').textContent=`${page} / ${pages}`;", CARDS+" $('pageInfo').textContent=`${page} / ${pages}`;")
    single("document.getElementById('rows').addEventListener('click',e=>{", "$('mobileFilters').addEventListener('click',()=>{const f=$('filtersV26'),b=$('mobileFilters');const expanded=!f.classList.toggle('v26-filter-collapsed');b.setAttribute('aria-expanded',String(expanded));b.textContent=expanded?'☷ Skrýt další filtry':'☷ Další filtry a řazení'});\nwindow.matchMedia('(max-width:900px)').addEventListener('change',()=>{page=1;render()});\n$('mobileCards').addEventListener('click',e=>{const b=e.target.closest('button.fav');if(!b)return;const id=b.dataset.id;if(favs.has(id))favs.delete(id);else favs.add(id);storeFavs();render()});\ndocument.getElementById('rows').addEventListener('click',e=>{")
    return src

if __name__=='__main__':
    if len(sys.argv)!=3:
        raise SystemExit('Usage: python apply_v26_mobile_layout.py INPUT_HTML OUTPUT_HTML')
    source,out=Path(sys.argv[1]),Path(sys.argv[2]); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(patch(source.read_text(encoding='utf8')),encoding='utf8')
    print('Mobile presentation generated:',out)
