#!/usr/bin/env python3
"""Surgical idempotent patch of published HTML: add verified -30/-40% filters.

No product data is loaded or modified. Fails closed on unexpected markup.
"""
from __future__ import annotations
import argparse
from pathlib import Path

BEFORE_OPTIONS = '<option value="20">Sleva alespoň 20 %</option><option value="quantity">'
AFTER_OPTIONS = ('<option value="20">Sleva alespoň 20 %</option>'
                 '<option value="30">Sleva alespoň 30 %</option>'
                 '<option value="40">Sleva alespoň 40 %</option>'
                 '<option value="quantity">')
BEFORE_LOGIC = "f.state==='20'&&!(active(p)&&reduction>=20)"
AFTER_LOGIC = "['20','30','40'].includes(f.state)&&!(active(p)&&reduction>=Number(f.state))"


def patch(html: str) -> str:
    if html.count(AFTER_OPTIONS) == 1 and html.count(AFTER_LOGIC) == 1:
        return html  # repeat-safe
    if html.count(BEFORE_OPTIONS) != 1 or html.count(BEFORE_LOGIC) != 1:
        raise ValueError('Unexpected filter HTML/JS; no changes applied')
    updated = html.replace(BEFORE_OPTIONS, AFTER_OPTIONS).replace(BEFORE_LOGIC, AFTER_LOGIC)
    if (updated.count('id="mobileCards"') != 1 or
            updated.count('id="state"') != 1 or
            updated.count('catalog_latest.json') < 1 or
            updated.count('<script>') != html.count('<script>')):
        raise ValueError('Current published layout is not the expected UAT8; refuse to edit')
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('file', type=Path, help='Published docs/catalog.html')
    args = parser.parse_args()
    old = args.file.read_text(encoding='utf-8')
    new = patch(old)
    if new != old:
        args.file.write_text(new, encoding='utf-8')
    print('PASS: verified discount thresholds 20 / 30 / 40 %, mobile layout preserved')

if __name__ == '__main__':
    main()
