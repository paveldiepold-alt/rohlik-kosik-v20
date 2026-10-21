# Monitor Slev II – v27 UAT7 (21. 10. 2026)

**Stav: bezpečný balíček pro zahájení izolovaného ONLINE ověření kategorií. NENÍ to produkční v27 a žádných 875 kategorií tímto balíčkem ještě nebylo načteno.**

## Co je skutečně provedeno

- Připraven `.github/workflows/taxonomy_v27_bootstrap.yml` pro DEFAULT větev `main`. Oproti UAT6 již **nevyžaduje ruční vytvoření feature větve** před spuštěním. Při prvním push do `main` se spustí automaticky; později jej lze spouštět manuálně v GitHub Actions. Všechny soubory v balíčku mají nové názvy; původní `docs/data/catalog_latest.json` a `docs/catalog.html` se ani ve workflow nepřepisují.
- Workflow vyčte aktuální katalog a příslušné parsovací moduly z `fix/real-product-price-reading-v20` (read-only). Výstup ukládá pouze do `feature/retailer-taxonomy-v27`, která se vytvoří automaticky v GitHub Actions, **pokud GITHUB_TOKEN skutečně smí zapisovat**. Pokud to repo nedovolí, reporty se alespoň uloží jako Action Artifact (workflow může indikovat chybu při push).
- Důležitá oprava: běh načítá parsovací modul `store_taxonomy.py` z čerstvé v26 *před* stejnojmenným souborem na `main` (přes `sys.path` + `runpy`), jinak by se používal starý parser.
- Dávková kontrola nyní **doplňuje nevyužitá místa v dávce** produkty druhého e-shopu, pokud jeden vrátí HTTP 403/429/503 nebo challenge. Otestováno s falešným browserem: dávka 6 → 1 blokování Rohlíku + 5 dalších kontrol Košíku, bez opakování produktu a bez změny zdroje/cen.
- Individuální opakované pokusy mají odstup 24/72/168 hodin. Po blokování platí 24h pauza pro celý obchod. Neobchází se CAPTCHA, autentizace ani omezení přístupu.
- Doplňkový offline průchod `--limit 0` funguje bez Playwrightu a beze změny zdroje; workflow používá pozitivní omezený počet URL.

## Audit neměnného výchozího stavu v26

Repo `paveldiepold-alt/rohlik-kosik-v20`, větev `fix/real-product-price-reading-v20`, Git blob `eb30728ba2a4155e1e85dc594977168a57039928` (znovu ověřen 21. 10. 2026):

- 1 090 výrobků, 894 s uloženou cenou a 196 bez ceny.
- 556 Košík (554 cen); 534 Rohlík (340 cen).
- 215 výrobků má uloženou cestu kategorie, **875 ji nemá**.
- Dvě sledovací pravidla bez výrobků: W008 a W033.

## Testy před předáním

- **73/73 offline automatických testů úspěšných**; včetně kompletního CLI ve dvou procesech, validace nenarušení zdroje, simulace blokování obchodu a doplňování dávky.
- Chromium smoke test **úspěšný**: syntetických 1 090 výrobků, 894 cen, 196 bez ceny, 11 stránek po 100 výrobcích, desktop/mobil, **0 JS errors**.
- YAML `taxonomy_v27_bootstrap.yml` syntakticky načten přes PyYAML; postup vytvoření větve `git worktree` / `git push` lokálně ověřen s testovacím Git repozitářem.
- **Neproběhl skutečný GitHub Actions běh**, protože propojení GitHub konektoru nemá oprávnění vytvořit větev (HTTP 403). Nelze proto slíbit, že GitHub Actions dovolí svůj vlastní push. Online síťový sběr všech 875 kategorií neproběhl.

## Způsob nasazení pouze pro TEST (nikoli produkci)

Na GitHubu rozbalit ZIP a vložit jeho obsah **do kořene větve `main`** přes `Add file → Upload files`. Nepřepisovat původní soubory: `docs/catalog.html`, `docs/data/catalog_latest.json`, stávající cenový monitor ani cenové skripty. Tento balíček přidává pouze nové soubory (výjimkou je případné opakované nahrání stejné v27 verze). GitHub vytvoří nový workflow **Monitor slev v27 - Izolovany sber kategorii** a spustí jej po prvním push. Výsledky jsou v Actions a v oddělené větvi `feature/retailer-taxonomy-v27` (pokud push projde).

**Na publikaci katalogu či nahrazení produkčního dashboardu zatím nesahejte.** Nejprve musíme vyhodnotit počet nově získaných kategorií, případná blokování e-shopů a integritu cen. Po úspěšném prvním online běhu lze opakovat další dávky tlačítkem `Run workflow` (např. limit 60 až 100), pokud to dostupnost e-shopů dovolí.
