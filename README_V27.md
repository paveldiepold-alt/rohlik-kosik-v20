# Monitor slev II – v27 UAT7 / online sběr

**Nejde o finální v27. Tento balíček připravuje JEDNORÁZOVÉ bezpečné spuštění online auditu kategorií na GitHubu. Původní v26 zůstává produkční.**

## Jaká je změna proti UAT6?

UAT6 se nedařilo spustit, protože GitHub integrace nedovolila vytvořit vývojovou větev (`403`). UAT7 má nový **bootstrap workflow na `main`**. Po jednorázovém nahrání výhradně nových souborů jej GitHub Actions spustí, načte nejnovější v26 (pouze čtení) a pokusí se samo vytvořit oddělenou větev pro v27 výsledky.

Nově: správné importování aktuálních parserů, automatické využití nevyčerpané dávky druhým obchodem při zablokování prvního, persistentní 24/72/168h backoff a kontrola bezeztrátového převzetí cen.

## Co přesně nahrát

**Až budeš chtít zahájit skutečný test**, rozbal `MonitorSlev_v27_UAT7_2026-10-21.zip` a nahraj *obsah rozbalené složky* do kořene `main` v `https://github.com/paveldiepold-alt/rohlik-kosik-v20` přes **Add file → Upload files**. Nahraješ soubory `catalog_v27.py`, `rule_path_v27.py`, `taxonomy_probe_v27.py`, `tests/test_*v27.py`, `docs/catalog-v27.html` a `.github/workflows/taxonomy_v27_bootstrap.yml` spolu s textovou dokumentací a fixtures.

**Nenahrazovat** `docs/catalog.html`, `docs/index.html`, `docs/data/catalog_latest.json`, `monitor.py`, `watchlist.json` ani žádné stávající workflow v26. V balíčku tyto původní soubory vůbec nejsou.

Po uploadu vyhledej GitHub **Actions → Monitor slev v27 – Izolovany sber kategorii**. První běh spustí push sám. Náhled výsledku najdeš v souhrnu a artefaktu `monitor-slev-v27-taxonomy-uat`, případně na oddělené větvi `feature/retailer-taxonomy-v27`. Tato nová větev není produkční a nebude napojená na veřejný `catalog.html`.

Další ruční dávka: **Run workflow → Branch main → limit 60 nebo 100 → Run workflow**. Jeden běh není důkaz zpracování všech 875 chybějících kategorií. Pokud se objeví `403/429/503`, respektuj uloženou pauzu; nezvyšuj zbytečně frekvenci. Pokud repo zakáže `GITHUB_TOKEN` zápis, výsledný Action Artifact zůstane ke stažení, i když push větve selže.

## Výchozí čísla

- 1 090 produktů, 894 cen, 196 bez ceny; poslední ověřený zdrojový blob `eb30728ba2a4155e1e85dc594977168a57039928`.
- 215 skutečně uložených cest kategorií, **875 zatím chybí**. Chybějící cesty nelze zodpovědně dopočítat z názvů.
- **73/73 offline testů**, Chromium smoke test 1 090 syntetických položek bez JavaScriptových chyb. **Skutečné online ověření všech kategorií stále neproběhlo.**

Podrobnosti: `UAT7_STATUS.md`; historické zjištění UAT6: `UAT6_STATUS.md` a `docs/V27_AUDIT_REAL_V26.md`.
