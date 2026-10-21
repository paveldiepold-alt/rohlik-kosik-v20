# Monitor slev v27 – výchozí audit skutečné v26

**Datum přístupu:** 21. 10. 2026. **Zdroj:** GitHub `paveldiepold-alt/rohlik-kosik-v20`, větev `fix/real-product-price-reading-v20`, soubor `docs/data/catalog_latest.json`, blob SHA `eb30728ba2a4155e1e85dc594977168a57039928`.

Tento dokument zaznamenává stav existujícího vstupu. **Nejde o výsledek dokončené klasifikace v27** a přiložený patch zatím nebyl nasazen na GitHub ani na Pages.

## Skutečný stav katalogu při auditu

| Metrika | Zjištěno |
|---|---:|
| Produktů | **1 090** |
| Jedinečných dvojic obchod + URL | **1 090** |
| Košík / Rohlík | 556 / 534 |
| Pozorování s `price_status=ok` a číselnou cenou | **894** |
| Bez doložené ceny | **196 (18,0 %)** |
| Produktů s uloženou cestou kategorie e-shopu | **215** |
| Bez uložené cesty kategorie e-shopu | **875 (80,3 %)** |
| Celkové vyhledávací úlohy | 196 / 196 |

Údaj z dřívějšího zadání 882 cen / 208 bez ceny odpovídal staršímu stavu. Aktuální data už mají **894/196**. Cena je historické pozorování; neznamená platnost dnes ani dodání do zvoleného PSČ.

## Diagnostika 196 cen bez potvrzení: původní uložené stavy

| Pozorovaný stav v datech | Rohlík | Košík | Celkem |
|---|---:|---:|---:|
| Uložený `http_status=429` / omezení přístupu | **171** | 0 | **171** |
| Cena nebyla spolehlivě přečtena (`price_unverified`, HTTP 200) | **23** | **1** | **24** |
| Neshoda identity produktu (`title_mismatch`, HTTP 200) | 0 | **1** | **1** |
| Součet | **194** | **2** | **196** |

**Výklad:** 171 historicky uložených záznamů HTTP 429 ukazuje na omezení Rohlíku, ale **u 2 těchto položek** proběhla později kontrola v26 se stavem `price_unverified`. Také u jediné historické neshody titulku na Košíku přišla novější kontrola `price_unverified`. Diagnostika v27 upřednostňuje poslední zaznamenaný pokus: **169 bez novějšího vysvětlení než blokování a 27 s posledním pokusem bez spolehlivě přečtené ceny**. Neshoda titulku zůstává v historii. V této várce nebyla potvrzena žádná trvalá nedostupnost konkrétního produktu. `price_unverified` může znamenat změnu struktury ceny, více kandidátů nebo jinou nejednoznačnost – ne automaticky „chybějící výrobek“.

## Riziko kategorií

Existující dashboard v26 odvozuje viditelnou kategorii především z `rule_ids` a přiřazených kategorií sledovaných pravidel. Toto není důkaz, že produkt takto kategorizuje samotný obchod. Pouze **215/1090** položek má dosud uloženou cestu prodejce; ostatní produkty musí v27 zůstat ve stavu **Ke kontrole**, dokud nebude získána a ověřena skutečná kategorie.

Příklady složek, které **nesmějí** automaticky splynout: `Ovoce a zelenina > Zelenina` versus `Ovoce a zelenina > Kuchařské boxy, hotové saláty a ready to cook`; `Maso a ryby > Drůbež` versus `Maso a ryby > Maso na grilování > Marinované maso`. Jméno výrobku ani klíčová slova „ovoce“, „kuřecí“, „máslo“ se nepoužívají pro pozitivní přiřazení do společné kategorie.

## Co v27 patch skutečně řeší

1. Přidává konzervativní společnou taxonomii podle cesty u prodejce, s oddělenými stavy **Potvrzeno / Ke kontrole / Nesoulad**. Pro celý katalog, nikoli pouze pro maso/ovoce.
2. Zachovává všechna původní pole všech výrobků, včetně cen, historie a původních pravidel; generuje **oddělený** soubor katalogu v27, nikoli náhradu v26.
3. Rozlišuje diagnostiku cen nezávisle na správnosti kategorie.
4. Obsahuje ručně spustitelný bezpečný dávkový sběr chybějících kategorií. Sběr neobchází captcha ani blokace a při chybě zachovává data.
5. Obsahuje náhled uživatelského dashboardu v27 a offline UAT testy. Nasazení zůstává podmíněné skutečným ověřením produktů na e-shopech.

## Blokující fakta před produkčním nasazením

* U **875 výrobků** nyní chybí skutečný breadcrumb obchodníka; jejich správnou kategorii nelze spolehlivě získat pouhým přepisem názvů nebo pravidel.
* GitHub konektor při pokusu založit oddělenou vývojovou větev vrátil **HTTP 403 / Resource not accessible by integration**. Stávající repozitář nebyl změněn; patch je předán jako ZIP.
* Offline testy neprokazují, že weby poskytují všechny kategorie online. Produkční spuštění v27 až po dokončeném sběru a úspěšném UAT na skutečném souboru.

## Kontrola všech 46 skutečně uložených cest kategorií

Regresní fixture `tests/fixtures/merchant_paths_v26_20261021.json` shrnuje **všech 46 unikátních cest kategorií, které v26 obsahovala**, včetně jejich četností: **215 produktů**. Tyto konkrétní cesty byly zhodnoceny pro mapování do společných kategorií bez použití názvu výrobku. Po doplnění výjimek pro mleté/grilované maso a BIO ovoce lze ze známých cest **208 produktů předběžně mapovat**, zatímco **7 zůstává ke kontrole** (marinované/uzené/mleté maso, grilovací větev, samotná nadřazená kategorie maso a předvařená zelenina). Zbylých **875 produktů** bez důvěryhodného breadcrumbu zůstává ke kontrole. **208 není nový živý sběr** a neříká, že všechna mapování byla potvrzena ručně na aktuální stránce; je to kontrola uložených dat v26 proti konzervativním cestám.

Pracovní náhled tak při tomto zmrazeném vstupu odpovídá očekávání **208 s mapovanou kategorií / 882 ke kontrole**. Závěrečná produkční validace musí pracovat s právě aktuálním katalogem po dávkovém ověření obou obchodů.

## Provedené kontroly pracovního patchu

- 43 offline testů včetně syntetického 1 090řádkového konzervačního testu se stavem 894 cen / 196 bez ceny.
- Regresní kontrola skutečných 46 cest, reprezentujících 215 uložených záznamů.
- Testovací webový dashboard ověřen v headless Chromium se syntetickými daty; fungovaly počty, filtrování, oblíbené, řazení a rychlé přepínače, bez JavaScriptových chyb.
- **Není hotov reálný online sběr těch 875 zbývajících kategorií**, proto pracovní v27 zatím není produkční verze.

## Aktualizace UAT3 – ochrana aktualizací a diagnostika pravidel

Doplněno 21. 10. 2026:

- Při spuštění dávkového ověření se původní katalog nejdřív načte z **aktuální** větve `fix/real-product-price-reading-v20`; vývojová větev tak nepřekryje aktuálnější ceny zastaralým snapshotem.
- Při rozdílu v identitách produktů ze stagingu a nového zdroje se dávka **zastaví** místo tichého odstranění položek.
- CLI generátoru mělo chybnou kontrolu počtu cest (5 argumentů / test vyžadoval 4), což by zabránilo reálnému vytvoření náhledu; chyba byla odstraněna a otestována přes subprocess.
- Všech **75** konfigurovaných pravidel je auditováno, v katalogu mají výsledky **73**. Bez nalezených produktů: **W008 (Šunky – Wein)** a **W033 (Aquila – neperlivá/jemně perlivá/kojenecká)**. To není automaticky chyba klasifikace ani důkaz nedostupnosti u obchodů.
- Prošlo **43 automatizovaných offline testů**. Dashboard se syntetickými 1 090 záznamy byl ověřen v Chromium (KPI, kategorie, 196 chybějících cen, filtry, oblíbené; bez chyby JavaScriptu). V prohlížeči nebylo provedeno živé ověření prodejců.

**Přetrvávající blokery:** 875 chybějících úplných cest kategorií; bez funkčního zápisu na GitHub (HTTP 403 u konektoru) nelze spouštět připravené dávky v oddělené větvi. Testy na syntetické kopii nevydávat za výsledky živého sběru 1 090 výrobků.

## Dodatek v27 UAT4 – kontrola jednotlivých druhů sledovaného výrobku

Výstup **208 ze 215 produktů se známou cestou** označuje pouze možné společné zařazení podle celé cesty e-shopu. Není to počet produktů s plně potvrzeným konkrétním vyhledávacím pravidlem. Další vrstva nyní validuje zvlášť 16 úzkých pravidel masa a čerstvého ovoce/zeleniny (W001–W005, W037–W047). Jestliže je dostupná jen širší podkategorie například `Banány a exotické ovoce`, zůstává konkrétní banán/avokádo **ke kontrole**, přestože společná kategorie `Ovoce` je správná.

Při testech byly též odděleny široké kategorie papírového zboží od konkrétních typů kapesníků a utěrek. Vývojový dashboard nezobrazuje nedatované slevy jako aktuálně platné akce. V lokálním Chromium prošlo UI ověřením 1 090 syntetických výrobků, 11 stran, filtrů, mobilních karet i časově doložené akce; bez chyb JavaScriptu.

**54 offline testů úspěšných.** Nejde o náhradu skutečného online sběru kategorií 875 produktů ani o potvrzení aktuálních cen v e-shopech.
