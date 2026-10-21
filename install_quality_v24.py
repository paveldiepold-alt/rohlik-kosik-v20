"""Attach catalog-wide safety gate to the existing vendor-category classifier.
Idempotent, fail-closed, no modifications if the anchor is missing.
"""
from pathlib import Path
import ast

def patch(path: Path):
    s=path.read_text(encoding='utf-8')
    marker='def partition_items(items: list[dict]) -> tuple[list[dict],list[dict]]:'
    original='''def partition_items(items: list[dict]) -> tuple[list[dict],list[dict]]:
    visible,review=[],[]
    for row in items:
        included, excluded=gate_item(row)
        if included:visible.append(included)
        if excluded:review.append(excluded)
    return visible,review
'''
    upgraded='''def partition_items(items: list[dict]) -> tuple[list[dict],list[dict]]:
    # v24: apply retailer taxonomy and item-type guard across all categories.
    from catalog_quality_v24 import gate_catalog_item
    visible,review=[],[]
    for row in items:
        included, excluded=gate_item(row)  # existing fresh produce verification
        if excluded:review.append(excluded)
        if included:
            verified, flagged = gate_catalog_item(included)
            if verified:visible.append(verified)
            if flagged:review.append(flagged)
    return visible,review
'''
    if upgraded in s:return False
    if s.count(original)!=1 or s.count(marker)!=1:
        raise RuntimeError('Unexpected store_taxonomy.py format; no files modified')
    future=s.replace(original,upgraded)
    ast.parse(future,filename=str(path))
    path.write_text(future,encoding='utf-8')
    return True

if __name__=='__main__':
    changed=patch(Path('store_taxonomy.py'))
    print('v24 taxonomy classifier upgraded' if changed else 'v24 taxonomy already installed')
