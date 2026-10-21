Rohlík × Košík v22 – Oprava ceny celého balení
============================================

CO SE OPRAVUJE
- Cena 7,77 Kč/dávka se již nepovažuje za 7,77 Kč za balení.
- Z cenového bloku Košíku se zpracuje například 699 00 + 7,77 Kč/dávka => 699,00 Kč.
- Cena, kterou stránka nepotvrdí, zůstane nezjištěná.
- Všechny původní product URL, kategorie a přiřazení se zachovají.

NASAZENÍ (neposílat ZIP přímo, nejdřív rozbalit):
1. GitHub -> repozitář paveldiepold-alt/rohlik-kosik-v20 -> větev main.
2. Add file -> Upload files. Nahraj do ROOT (hlavního adresáře):
   price_v22.py
   apply_price_patch_v22.py
   recheck_catalog_prices_v22.py
3. Na GitHubu otevři složku tests -> Upload files:
   tests/test_price_v22.py
   tests/test_recheck_v22.py
4. Otevři složku .github/workflows -> Upload files:
   .github/workflows/prices_v22.yml
5. GitHub Actions -> Rohlik Kosik v22 - Oprava cen bez noveho vyhledavani
   -> Run workflow na větvi main.
   Ponech focus=Ariel a max_products=40 pro první kontrolu těchto výrobků.
6. Po běhu zkontroluj počet ověřených cen v logu, diagnostics artifact a katalog.
   Pro celý katalog následně spusť stejné workflow s focus prázdné a vhodnou dávkou.

POZOR
- Žádné 196 plošných vyhledávacích dotazů se nespouští.
- Dřívější chybná cena se uloží do legacy_price_czk, pokud se výrobek kontroluje.
- Není-li stránka dostupná, cena zůstane neověřená; nezaměňovat s nulou.
- Nejde o ověření dostupnosti ani ceny pro konkrétní PSČ 149 00.
- Nasazení do GitHubu musíš provést pod svým přihlášeným účtem; připojení zde nemá write permission.
