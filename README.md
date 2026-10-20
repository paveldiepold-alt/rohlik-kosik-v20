# Rohlík × Košík v20 – sjednocený pilot

Toto je **jediný kompletní ověřovací balíček** pro repozitář `rohlik-kosik-v20`. Obsahuje 75 katalogových pravidel, ale zatím čte jen 10 konkrétních produktových URL. **Není to hotový hlídač veškerých akcí.**

## Jednorázová instalace

1. Rozbal tento ZIP na počítači. Archiv obsahuje přímo soubory `monitor.py`, `watchlist.json`, `README.md` a složky `.github`, `tests`, `docs` – **žádný vnořený adresář projektu**.
2. Otevři `https://github.com/paveldiepold-alt/rohlik-kosik-v20` → **Add file → Upload files**.
3. Přetáhni **obsah rozbalené složky**, ne ZIP a ne samotnou nadřazenou složku. Ponech složky `.github/workflows`, `tests` a `docs` ve správných cestách. Pokud se GitHub zeptá na přepsání `watchlist.json` nebo `README.md`, nahraď je tímto balíčkem. Potvrď **Commit changes** do `main`.
4. Zkontroluj, že v repozitáři jsou `monitor.py` a `.github/workflows/monitor.yml`.
5. Otevři `https://github.com/paveldiepold-alt/rohlik-kosik-v20/actions/workflows/monitor.yml` → **Run workflow → main → Run workflow**. Tento test může skončit červeně, pokud weby neposkytnou ověřitelné ceny, ale nesmí selhat na syntaxi či chybějícím souboru.
6. V běhu otevři **Summary**: tabulka ukáže 10 kontrolovaných produktů a stav každého; v artefaktu `rk-v20-results` jsou i diagnostické důvody. Pošli tento výsledek do chatu. **Nemaž původní projekt v19**, dokud nové ceny nefungují.

Automatické denní spouštění je pro první ověřovací běh **vypnuto**. GitHub Pages v této fázi nenastavuj. Staré `test.yml`/`probe.yml` můžeš zatím ponechat, ale používej jen nové workflow `Kontrola cen`.

## Ověřený obsah

- `monitor.py` – skutečný kód pro otevření 10 veřejných produktových stránek Playwrightem, nikoli kopie HTML.
- `watchlist.json` – 75 pravidel + 10 konkrétních URL, nadále rozšiřitelných.
- `tests/` – statické testy formátu, cen, shody názvu a struktury.
- `docs/index.html` – mobilní/desktopový dashboard bez vymyšlených cen.
- `.github/workflows/monitor.yml` – ruční kontrola, uložení diagnostiky i při neúspěchu.

### Omezení

Bez přihlášení a nastavení dopravy není potvrzena cena ani dostupnost pro PSČ 149 00. Získání strukturovaných produktových cen z obou obchodů není provozně ověřené; zelená kontrola syntaxe tuto nejistotu neřeší. Kompletní katalog 75 pravidel, oficiální akční sleva, její konec, množstevní podmínky, fotografie, porovnání shodných balení a upozornění do druhého účtu ChatGPT **nejsou v tomto pilotu aktivní**. Rozšíření závisí na funkčním a ověřeném sběru cen.
