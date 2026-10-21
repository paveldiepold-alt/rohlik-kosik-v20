"""Idempotent, fail-closed patch of existing branch price scanner."""
from pathlib import Path
import ast
import sys


def patch(root: Path) -> None:
    monitor=root/'monitor.py'
    visible=root/'visible_price.py'
    m=monitor.read_text(encoding='utf-8')
    v=visible.read_text(encoding='utf-8')
    old="def from_browser_payload(payload: dict, shop: str = \"\") -> tuple[float | None, str | None, str]:\n"
    guard='''    # v22: Košík pack price precedes unit prices in the own H1 price block.\n    if shop == 'Košík':\n        from price_v22 import choose_kosik_pack_price, UNIT_RE\n        pack, pack_source, reason = choose_kosik_pack_price(payload.get('detail_text',''))\n        if pack is not None:\n            return pack, pack_source, reason\n        # If a unit price appears but the pack price is ambiguous, do not\n        # fall back to the old parser, which could publish Kč/dávka as Kč/ks.\n        if UNIT_RE.search(payload.get('detail_text','')):\n            return None, None, reason\n'''
    if "# v22: Košík pack price" not in m:
        if m.count(old)!=1:raise ValueError('Unexpected monitor.py structure; no files modified')
        m=m.replace(old,old+guard,1)
    # Expand unit-price detection everywhere, including visible-price candidates.
    # Existing visible_price parser is retained for non-Košík and legacy tests.
    if 'dávk\\w*' not in v:
        old_unit=r'(?:kg|g|l|ml|ks|m|100\s*g|100\s*ml)'
        new_unit=r'(?:kg|g|l|ml|ks|m|100\s*g|100\s*ml|dávk\w*|pran\w*|porc\w*|použit\w*|rol\w*)'
        if old_unit not in v:raise ValueError('Unexpected visible_price.py unit expression; no files modified')
        v=v.replace(old_unit,new_unit)
    # v22 intentionally reports a more specific price provenance.  The pre-v22
    # unit test asserts the *old* source label while checking the same price.
    # Migrate only that one exact assertion; retain the price and all other
    # tests unchanged. Fail closed if an unexpected test version is found.
    legacy_test = root/'tests'/'test_kosik_routing.py'
    test_text = legacy_test.read_text(encoding='utf-8')
    old_assert = "self.assertEqual(from_browser_payload(payload,'Košík')[:2],(19.9,'kosik-product-text'))"
    new_assert = "self.assertEqual(from_browser_payload(payload,'Košík')[:2],(19.9,'kosik-pack-v22'))"
    if old_assert in test_text:
        test_text = test_text.replace(old_assert,new_assert,1)
    elif new_assert not in test_text:
        raise ValueError('Unknown legacy Košík test assertion; no files modified')
    ast.parse(m,filename='monitor.py')
    ast.parse(v,filename='visible_price.py')
    ast.parse(test_text,filename='tests/test_kosik_routing.py')
    monitor.write_text(m,encoding='utf-8')
    visible.write_text(v,encoding='utf-8')
    legacy_test.write_text(test_text,encoding='utf-8')
    print('OK: v22 price patch installed; repeat-safe')


if __name__=='__main__':
    patch(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd())
