#!/usr/bin/env python3
"""Rohlík × Košík: price-sale parser + GitHub Actions v27 repair.

Run inside a CLEAN local clone of paveldiepold-alt/rohlik-kosik-v20.
  python apply_hotfix.py --apply --push
Uses your existing git credentials. No tokens are requested or stored.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

REPO = 'paveldiepold-alt/rohlik-kosik-v20'
PRICE_BRANCH = 'fix/real-product-price-reading-v20'
MAIN_BRANCH = 'main'


def cmd(*args: str, check=True):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError(f"{' '.join(args)} failed:\n{p.stderr}")
    return p.stdout.strip()


def change(path: str, old: str, new: str):
    p = Path(path)
    if not p.is_file():
        raise RuntimeError(f'Missing expected file: {path}; wrong branch?')
    data = p.read_text(encoding='utf-8')
    if new in data:
        print(f'  Already applied: {path}')
        return
    n = data.count(old)
    if n != 1:
        raise RuntimeError(f'Unsafe patch: expected one match in {path}, got {n}: {old[:95]!r}')
    p.write_text(data.replace(old, new, 1), encoding='utf-8')
    print('  Patched:', path)


PROMO = '''def extract_rohlik_discount(current_price: float, candidates: list[dict], detail_text: str = '') -> dict:
    """Only trust a unique visible crossed-out product-pack price.

    No invented promotion from price history, unit prices, quantity discounts,
    structured-data prices or recommendations elsewhere on the page.
    """
    empty = {'original_price_czk': None, 'discount_pct': None,
             'offer_valid_until': None}
    if not isinstance(current_price, (int, float)) or current_price <= 0:
        return empty
    old_prices = set()
    for node in candidates or []:
        if not isinstance(node, dict) or not node.get('detail') or not node.get('old'):
            continue
        if node.get('unit') or node.get('condition'):
            continue
        if float(node.get('distance') if node.get('distance') is not None else 9999) > 450:
            continue
        hint = str(node.get('hint') or '')
        if re.search(r'(?i)unit[-_]?price|price[-_]?per[-_]?unit', hint):
            continue
        amount = parse_display_price(str(node.get('text') or ''))
        if amount is not None:
            old_prices.add(amount)
    if len(old_prices) != 1:
        return empty
    old = old_prices.pop()
    if old <= current_price or old > current_price * 7:
        return empty
    pct = round(100 * (1 - current_price / old), 1)
    if not 1 <= pct <= 85:
        return empty
    explicit = re.search(r'(?<!\\w)[−–-]\\s*(\\d{1,2})\\s*%', str(detail_text or '')[:650])
    if explicit and abs(float(explicit.group(1)) - pct) > 3:
        return empty
    return {'original_price_czk': old, 'discount_pct': pct,
            'offer_valid_until': None}


'''


def patch_prices():
    print('\nPRICE BRANCH')
    change('visible_price.py',
           'def choose_kosik_detail_price(text: str) -> tuple[float | None, str | None, str]:',
           PROMO + 'def choose_kosik_detail_price(text: str) -> tuple[float | None, str | None, str]:')
    change('monitor.py',
           'from visible_price import VISIBLE_PRICE_JS, choose_visible_price, choose_kosik_detail_price',
           'from visible_price import VISIBLE_PRICE_JS, choose_visible_price, choose_kosik_detail_price, extract_rohlik_discount')
    change('monitor.py',
           'def inspect(page, entry: dict, checked_at: str) -> dict:',
           'def inspect(page, entry: dict, checked_at: str, max_price_czk: float = PILOT_MAX_PRICE_CZK) -> dict:')
    change('monitor.py',
           'if not plausible_pilot_price(price):',
           'if not plausible_pilot_price(price, cap=max_price_czk):')
    change('monitor.py',
           "f'{PILOT_MAX_PRICE_CZK:.0f} Kč; nebude použita ani uložena.'",
           "f'{max_price_czk:.0f} Kč; nebude použita ani uložena.'")
    change('monitor.py',
           "data.update(status='ok', price_czk=price, source=source, note=note)\n",
           "offer = extract_rohlik_discount(price, payload.get('visible_prices', []),\n"
           "                                        payload.get('detail_text', '')) if source == 'visible-product-detail' else {}\n"
           "        data.update(status='ok', price_czk=price, source=source, note=note,\n"
           "                    original_price_czk=offer.get('original_price_czk'),\n"
           "                    discount_pct=offer.get('discount_pct'),\n"
           "                    offer_valid_until=offer.get('offer_valid_until'))\n")
    change('maintenance_v26.py',
           "'label':product.get('title') or product.get('name'),'url':product['url']},now)",
           "'label':product.get('title') or product.get('name'),'url':product['url']},now,max_price_czk=5000)")
    change('maintenance_v26.py',
           "'offer':{}}\n    response=page.goto",
           "'offer':{'original_price_czk':report.get('original_price_czk'),\n"
           "                          'discount_pct':report.get('discount_pct'),\n"
           "                          'offer_valid_until':report.get('offer_valid_until')}}\n"
           "    response=page.goto")
    change('maintenance_v26.py',
           "order=['Košík','Košík','Košík','Rohlík']",
           "order=['Košík','Rohlík']")
    change('tests/test_visible_price.py',
           'from visible_price import parse_display_price, choose_visible_price, VISIBLE_PRICE_JS',
           'from visible_price import parse_display_price, choose_visible_price, extract_rohlik_discount, VISIBLE_PRICE_JS')
    change('tests/test_visible_price.py',
           '    def test_quantity_condition_exposed(self):',
           "    def test_rohlik_crossed_price_proves_promotion(self):\n"
           "        old = {**visible('129,90 Kč', 'original-price'), 'old': True}\n"
           "        self.assertEqual(extract_rohlik_discount(74.9, [visible('74,90 Kč'), old])['discount_pct'], 42.3)\n\n"
           "    def test_rohlik_rejects_ambiguous_or_unit_old_prices(self):\n"
           "        old = {**visible('129,90 Kč', 'original-price'), 'old': True}\n"
           "        self.assertIsNone(extract_rohlik_discount(74.9, [old, {**old, 'text': '149,90 Kč'}])['discount_pct'])\n"
           "        self.assertIsNone(extract_rohlik_discount(74.9, [{**old, 'unit': True}])['discount_pct'])\n"
           "        self.assertIsNone(extract_rohlik_discount(74.9, [{**old, 'detail': False}])['discount_pct'])\n"
           "        self.assertIsNone(extract_rohlik_discount(74.9, [old], '-15 %')['discount_pct'])\n\n"
           '    def test_quantity_condition_exposed(self):')
    change('tests/test_maintenance_v26.py',
           '    def test_suppressed_retry_and_other_merchants(self):',
           "    def test_rohlik_offer_metadata_persisted(self):\n"
           "        x=self.row('Rohlík')\n"
           "        y=apply_result(x,status='ok',price=74.9,offer={'original_price_czk':129.9,'discount_pct':42.3},checked_at='2026-10-22T08:00:00+00:00')\n"
           "        self.assertEqual(y['original_price_czk'],129.9)\n"
           "        self.assertEqual(y['discount_pct'],42.3)\n\n"
           '    def test_suppressed_retry_and_other_merchants(self):')
    cmd(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_visible_price.py', '-v')
    cmd(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_maintenance_v26.py', '-v')
    print('  PASS: price parser tests')


PUBLISH = r'''      - name: Publish verified v27 category overlay to public catalogue (no price edits)
        shell: bash
        run: |
          set -euo pipefail
          python - <<'PYOVERLAY'
          import json
          from collections import Counter
          from datetime import datetime, timezone
          from pathlib import Path
          src=json.loads(Path('.v27-run/source.json').read_text(encoding='utf-8'))
          new=json.loads(Path('.v27-run/catalog_v27.json').read_text(encoding='utf-8'))
          ids=lambda rows:[(p['store'],p['url']) for p in rows]
          assert ids(src['items'])==ids(new['items'])
          assert len(new['items'])>=1090
          rows=[]
          for p in new['items']:
            rows.append({k:p.get(k) for k in ('store','url','category_v27','store_category_path','category_source')})
          states=Counter(p['category_v27']['status'] for p in new['items'])
          mapped=sum(p['category_v27'].get('category') is not None for p in new['items'])
          counts=dict(states)
          counts.update(mapped=mapped,unmapped=len(rows)-mapped,
                        mapped_with_rule_review=sum(p['category_v27'].get('category') is not None and p['category_v27']['status']=='review' for p in new['items']))
          overlay={'schema':'rk-v27-retailer-category-overlay-v1',
                   'generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   'source_catalog_generated_at':src['generated_at'],
                   'source_category_run_at':new.get('generated_at'),
                   'total':len(rows),'counts':counts,'items':rows}
          Path('.v27-run/public_overlay.json').write_text(json.dumps(overlay,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
          print('Safe overlay:',len(rows),'mapped:',mapped,'verified:',states['verified'])
          PYOVERLAY
          git fetch --no-tags origin '+refs/heads/fix/real-product-price-reading-v20:refs/remotes/origin/fix/real-product-price-reading-v20'
          git worktree add --detach .v27-public origin/fix/real-product-price-reading-v20
          python - <<'PYVERIFY'
          import json
          from pathlib import Path
          target=Path('.v27-public/docs/data/taxonomy_v27_public.json')
          prior=json.loads(target.read_text(encoding='utf-8'))
          new=json.loads(Path('.v27-run/public_overlay.json').read_text(encoding='utf-8'))
          old_ids=[(x['store'],x['url']) for x in prior['items']]
          new_ids=[(x['store'],x['url']) for x in new['items']]
          assert old_ids==new_ids, 'Product identity mismatch: STOP'
          assert new['counts']['mapped']>=prior['counts']['mapped'], 'Category coverage regression: STOP'
          target.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
          PYVERIFY
          cd .v27-public
          git config user.name 'github-actions[bot]'
          git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
          git add -- docs/data/taxonomy_v27_public.json
          test -z "$(git status --porcelain -- docs/catalog.html docs/data/catalog_latest.json)"
          if ! git diff --cached --quiet; then
            git commit -m 'v27: publish verified merchant taxonomy overlay [skip ci]'
            git push origin 'HEAD:refs/heads/fix/real-product-price-reading-v20'
          fi

'''


def patch_workflows():
    print('\nMAIN BRANCH')
    w='.github/workflows/taxonomy_v27_bootstrap.yml'
    change(w,"default: '60'", "default: '25'")
    change(w,"INPUT_LIMIT: ${{ inputs.limit || '100' }}", "INPUT_LIMIT: ${{ inputs.limit || '25' }}")
    change(w,"timeout-minutes: 45", "timeout-minutes: 25")
    change(w,"      - name: Install browser for a bounded respectful category-only scan\n        shell: bash\n        run: |\n          python -m pip install --disable-pip-version-check playwright==1.56.0\n          python -m playwright install --with-deps chromium",
           "      - name: Install browser for a bounded respectful category-only scan\n        shell: bash\n        timeout-minutes: 6\n        run: |\n          set -euo pipefail\n          python -m pip install --disable-pip-version-check playwright==1.56.0\n          python -m playwright install chromium")
    change(w,"      - name: Explain real progress in Action summary\n",PUBLISH+"      - name: Explain real progress in Action summary\n")
    w='.github/workflows/user_monitor_v26.yml'
    change(w,"on:\n  workflow_dispatch:",
           "on:\n  push:\n    branches: [main]\n    paths:\n      - .github/workflows/user_monitor_v26.yml\n  workflow_dispatch:")
    change(w,"default: '24'", "default: '35'")
    change(w,"- cron: '13 7 * * *'", "- cron: '13 */3 * * *'")
    change(w,"timeout-minutes: 40", "timeout-minutes: 25")
    change(w,"INPUT_LIMIT: ${{ inputs.limit || '24' }}", "INPUT_LIMIT: ${{ inputs.limit || '35' }}")
    change(w,"CHECK_LIMIT: ${{ inputs.limit || '24' }}", "CHECK_LIMIT: ${{ inputs.limit || '35' }}")
    change(w,"      - name: Install price browser\n        shell: bash\n        run: |\n          set -euo pipefail\n          python -m pip install --disable-pip-version-check 'playwright==1.56.0'\n          python -m playwright install --with-deps chromium",
           "      - name: Verify promotion parser offline\n        shell: bash\n        run: |\n          python -m unittest discover -s tests -p 'test_visible_price.py' -v\n          python -m unittest discover -s tests -p 'test_maintenance_v26.py' -v\n\n      - name: Install price browser\n        shell: bash\n        timeout-minutes: 6\n        run: |\n          set -euo pipefail\n          python -m pip install --disable-pip-version-check 'playwright==1.56.0'\n          python -m playwright install chromium")
    print('  PASS: workflow transformations')


def main():
    parser=argparse.ArgumentParser(description='Apply tested Rohlík/Košík hotfix to GitHub clone')
    parser.add_argument('--apply',action='store_true',help='modify both branches')
    parser.add_argument('--push',action='store_true',help='push commits to origin (requires --apply)')
    args=parser.parse_args()
    if not args.apply:
        print('Preview only. Use --apply --push to install and start GitHub Actions.')
        return
    if args.push and not args.apply: parser.error('--push requires --apply')
    if not Path('.git').exists():
        parser.error('Run from root of a clean local Git repository clone')
    origin=cmd('git','remote','get-url','origin')
    if REPO not in origin:
        parser.error(f'Expected origin {REPO}, got {origin}')
    if cmd('git','status','--porcelain'):
        parser.error('Git working tree is not clean; save or commit changes first')
    start=cmd('git','branch','--show-current')
    cmd('git','fetch','origin',MAIN_BRANCH,PRICE_BRANCH)
    try:
        for branch, patch, message, paths in [
            (PRICE_BRANCH,patch_prices,'fix: capture Rohlík promotions safely and test parser',
             ['visible_price.py','monitor.py','maintenance_v26.py','tests/test_visible_price.py','tests/test_maintenance_v26.py']),
            (MAIN_BRANCH,patch_workflows,'fix: unblock v27 categories, publish overlay and refresh prices',
             ['.github/workflows/taxonomy_v27_bootstrap.yml','.github/workflows/user_monitor_v26.yml'])
        ]:
            cmd('git','switch',branch)
            cmd('git','pull','--ff-only','origin',branch)
            patch()
            cmd('git','add','--',*paths)
            if cmd('git','diff','--cached','--name-only'):
                cmd('git','commit','-m',message)
                if args.push:
                    cmd('git','push','origin',branch)
                    print('  PUSHED:',branch)
            else:
                print('  No changes:',branch)
    finally:
        if start and cmd('git','status','--porcelain')=='':
            cmd('git','switch',start)
    print('\nHotfix complete. Github Actions runs start automatically after main workflow push.')


if __name__=='__main__':
    try: main()
    except (RuntimeError, OSError) as e:
        print('STOP:',e,file=sys.stderr)
        sys.exit(1)
