# Monitor slev v27 – publikace ověřených kategorií

Balíček připraven 22. 10. 2026. **Žádný produkt, cena, historie cen ani sleva se tímto balíčkem nepřepisuje.** Cílem je ukázat ve veřejném dashboardu skutečné kategorie e-shopů z již existujícího izolovaného sběru v27.

## 1. Co nahrát na GitHub

Repozitář: `paveldiepold-alt/rohlik-kosik-v20`, větev **main**. Rozbal ZIP a nahraj **pouze jednotlivé soubory do příslušných existujících složek**:

- Kořen repozitáře: `publish_taxonomy_v27.py`
- Složka `tests`: `test_publish_taxonomy_v27.py`
- Složka `.github/workflows`: `publish_taxonomy_v27.yml`

U každé skupiny potvrď **Commit changes**. Nikam nekopíruj JSON katalogu ani starý HTML dashboard.

## 2. Spuštění a bezpečné nasazení

V GitHub **Actions** otevři **Monitor slev v27 – Zveřejnění ověřených kategorií**.

1. Spusť `Run workflow` s větví **main** a `deploy = false` (pouze test a vytvoření náhledu). Ověř zelený stav a artefakt `rk-v27-kategorie-nahled`.
2. Potom spusť `Run workflow` znovu s větví **main** a `deploy = true` (skutečné publikování).
3. Po zeleném nasazení otevři https://paveldiepold-alt.github.io/rohlik-kosik-v20/catalog.html a obnov stránku `Ctrl+F5`.

**Pozor:** Dokud krok 2 neskončí úspěšně, veřejný web se nezmění. Pouze zelené testy ještě neznamenají nasazení.

## 3. Co bude nového na webu

- Kategorie se berou z e-shopem doložené cesty, nikoli z názvu výrobku nebo starého sledovacího pravidla.
- Pole **Kategorie** zobrazuje společné ověřené kategorie a **Ke kontrole**, pokud e-shop kategorii nepotvrdil.
- Přibude filtr **Stav kategorie**: `Plně ověřené`, `Ke kontrole (včetně nesouladu)`, `Nesoulad se sledováním`, `Bez potvrzené kategorie`.
- Každý produkt uvádí, zda se shoduje i s konkrétním pravidlem sledování. Prokázaná kategorie e-shopu neznamená automaticky správnou shodu s pravidlem.
- Pod průběhem vyhledávacích úloh přibude ukazatel počtu mapovaných, plně ověřených a kontrolovaných výrobků.
- Horní datum přejde na **Poslední kontrola cen**; staré datum sestavení katalogu zůstane dostupné po najetí myší.
- Mobilní produktové karty, oblíbené a filtry slev 20/30/40 % zůstávají.

## 4. Co se technicky mění

Publikující workflow načte:
- aktuální **živý** `docs/data/catalog_latest.json` a `docs/catalog.html` z větve `fix/real-product-price-reading-v20`,
- již zkompilované kategorie `v27-results/catalog_v27.json` z větve `feature/retailer-taxonomy-v27`.

Porovná všech 1 090 kombinací obchod+URL a sestaví **pouze** nový soubor `docs/data/taxonomy_v27_public.json`. V žádném kroku nepublikuje starý katalog v27 ani jeho cenové údaje. Ke zveřejnění se smí změnit jen:

- `docs/catalog.html` (malá úprava JS a filtrů v aktuální mobilní verzi)
- `docs/data/taxonomy_v27_public.json` (samostatná evidence kategorií)

Publikační brána odmítá jakoukoli změnu `docs/data/catalog_latest.json` a jiných cest. V případě konfliktu nebo chybějícího pole se nic nezveřejní.

## 5. Jak bude fungovat další sběr kategorií

Až později spustíš stávající `Monitor slev v27 – Izolovaný sběr kategorií`, uloží výsledek do vývojové větve, nikoli na veřejný web. Potom stačí opět spustit **Zveřejnění ověřených kategorií** s `deploy = true`. Nemusíš opět nahrávat kód.

Poslední ověřená čísla před instalací: 1 090 výrobků, 1 049 cen, 41 bez ceny, 457 přiřazených kategorií podle cesty e-shopu, 352 plně ověřených vůči sledovanému pravidlu. Tyto hodnoty nejsou garancí pozdějšího stavu; workflow vždy přepočítá aktuální data.

## 6. Omezení

Balíček **ještě nedoplňuje zbývající chybějící kategorie**: pouze bezpečně zpřístupňuje už ověřené výsledky a umožní je filtrovat. Nové mapování 68 známých, ale nezařazených cest vyžaduje samostatné rozšíření pravidel a opakovaný audit, nikoli automatické domýšlení podle názvu.

Kontrola při tvorbě balíčku: 12/12 regresních testů na syntetických datech, validní JavaScript testovacího HTML, kontrola všech potřebných HTML kotev na aktuální živé stránce GitHubu. Skutečné zveřejnění musí provést GitHub workflow v tvém repozitáři.
