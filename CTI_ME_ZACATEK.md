# Monitor slev – společný balíček UAT8 (design) + UAT9 (ceny)

Toto je sloučený balíček dvou samostatných změn. Nenahrazuje kompletní v27 ani produktový katalog.

## Obsah
- `apply_v26_mobile_layout.py` – patch aktuálního veřejného HTML: mobilní karty a oprava posunutého sloupce (v26)
- `.github/workflows/mobile_design_v26.yml` – ruční test nebo výslovně povolené nasazení změny HTML
- `docs/catalog-v27.html` – samostatný náhled designu v27, který ke správné funkci vyžaduje dosud nezveřejněný soubor `docs/data/catalog_v27.json`; nenahrazuje webovou v26
- `price_probe_v27.py` – diagnostika chybějících cen, bez uložení nových cen
- `.github/workflows/price_probe_v27_readonly.yml` – ruční cenová diagnostika
- `tests/test_price_probe_v27.py` – testy cenové diagnostiky

## Postup
1. Obsah ZIPu rozbal a nahraj do větve `main` se zachováním uvedených cest. Nenahrávej ZIP jako jediný soubor.
2. **Design**: v Actions otevři `Monitor slev - mobilni design v26 (manual)`, spusť z `main` s `deploy=false`. Z artefaktu zkontroluj HTML. Teprve po kontrole lze zvolit `deploy=true`, který mění **jen** `docs/catalog.html` ve veřejné větvi `fix/real-product-price-reading-v20`.
3. **Ceny**: v Actions otevři `Monitor slev v27 - Cenova diagnostika (bez zapisu)`, spusť z `main` s limit=12 a delay=4. Sběr nic nepřepisuje; uloží JSON report.

Nikdy nepřepisuj ručně soubory pod `docs/data/`. Zelená cenová diagnostika neznamená, že chybějící ceny byly doplněny.

Existující `.github/workflows/taxonomy_v27_bootstrap.yml` z UAT7 v tomto ZIPu záměrně není, protože už je na GitHubu – nech jej beze změny.
