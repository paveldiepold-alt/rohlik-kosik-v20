# Monitor slev v27 – UAT6 (21. 10. 2026)

**Pracovní vývojové vydání. NENASAZOVAT do produkce a nenahrávat přes v26.**

## Změna oproti UAT5

1. **Dva nezávislé výsledky**: (a) mapování skutečné kategorie e-shopu, (b) potvrzení nebo vyvrácení konkrétního sledovaného pravidla. Kategorie `Nápoje / vody` nemůže sama potvrdit, že jde o neochucenou/neperlivou/jemně perlivou/kojeneckou variantu.
2. **W033–W035**: obchodem doložená větev `Ochucené` vylučuje shodu se sledovanými neochucenými vodami. Kategorie `Neperlivé` bez důkazu neochucené vody znamená `review`; `Neochucené > Neperlivé` nebo `Neochucené > Jemně perlivé` znamená potvrzený podtyp. Kategorie `Perlivé` bez označení `Jemně` vyvolá nesoulad.
3. **Důsledné upozornění na jiné úzké varianty**: samotný nadřazený regál již neověřuje konkrétní příchuť Jar citron, kokosovou Fidorku, Coca-Colu Original, typ aviváže Lenor/Silan, Vanish odstraňovač skvrn, jednorázová holítka nebo konkrétní balení kapesníků. Podkategorie `Aviváže`, `Prací gely`, `Odstraňovače skvrn` a další užší větve slouží k potvrzení/odmítnutí tam, kde je to opravdu průkazné.
4. **UI nepoužívá zavádějící popisky**: „Shoda se sledovaným pravidlem“ je samostatná od „Společné kategorie“. Neověřené varianty nejsou prezentované jako správné shody jen kvůli nadřazené kategorii.

## Audit známých reálných záznamů

Zdrojový repo: `paveldiepold-alt/rohlik-kosik-v20`, větev `fix/real-product-price-reading-v20`, `docs/data/catalog_latest.json`, blob SHA `eb30728ba2a4155e1e85dc594977168a57039928`.

- Produktů: **1090**; cen: **894**; bez ceny: **196**.
- Cesty kategorie v databázi: **215** záznamů (z nich **214** s více než jedním segmentem); bez cesty **875**. Pořád chybí síťový sběr nepokrytých cest.
- 11 uložených produktů sledovaných pravidly vody W034/W035: 4 mají obchodem doloženou cestu označenou `Ochucené`, a tedy vedou k `mismatch`; 7 nemá potvrzenou podkategorii a zůstává `review`. Žádný z těchto 11 produktů není vyřazen ze zdrojové evidence.
- Z těchto 11 položek mělo 10 uloženou cenu a jedna historickou chybu HTTP. Regresní testy výslovně ověřují zachování 10 cen.
- Košík: 556 produktů / 554 cen. Rohlík: 534 produktů / 340 cen. Mezera cen vzniká hlavně u Rohlíku, což je oddělené od problému kategorií.

## Testy UAT6

- **69/69** offline automatických testů úspěšných.
- Chromium smoke test na syntetické úplné databázi 1090 produktů: **úspěšný**, 11 stran po 100 produktech, desktop + mobil, **0 JavaScript chyb**.
- Regresní vzorek 46 historicky známých cest ze skutečné v26 a samostatný vzorek 11 skutečně pojmenovaných vod. Ostatní testovací položky jsou **syntetické**.
- Testy nejsou důkazem, že se všech 875 neznámých cest podařilo z e-shopů nově získat.

## Bezpečnost a další nutný krok

Součástí balíčku jsou izolovaný dávkový Playwright probe, watchdog pro blokování a workflow pro samostatnou vývojovou větev. Po zjištění HTTP 429 je další kontakt obchodu odložen; nepoužívá obcházení ochrany. Zdrojová v26 se čte, nikdy nepřepisuje.

GitHub integrace v tomto chatu při pokusu o vytvoření vývojové větve vrátila **403**, proto nebylo možné uskutečnit online dávkový běh uvnitř GitHub Actions. Aktuální balíček je **pouze patch** do kopie repo, nikoli samostatná aplikace připravená k nahrání přes produkční větev. Dokončení v27 závisí na izolovaném spouštění dávkového sběru kategorií a kontrolách výstupu na skutečných datech.
