"""Copy the packaged model/mapping JSON into docs/data for the docs site.

The interactive model browser (docs/model.md) fetches these files at runtime,
so MkDocs needs its own copy inside the docs tree. Run after editing any file
in src/imaging_metadata_converter/data:

    python scripts/sync_docs_data.py

Use --check to fail instead of writing, which is what tests/test_docs_data.py
does so a stale copy cannot be committed unnoticed.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'src' / 'imaging_metadata_converter' / 'data'
TARGET = ROOT / 'docs' / 'data'
FILES = ('schema.json', 'schema.extended.json', 'mappings.json')


def rendered(name):
    """The minified text the docs copy of ``name`` should hold."""
    data = json.loads((SOURCE / name).read_text(encoding='utf-8'))
    return json.dumps(data, separators=(',', ':'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='report stale copies without writing')
    args = parser.parse_args(argv)

    TARGET.mkdir(parents=True, exist_ok=True)
    stale = []
    for name in FILES:
        text = rendered(name)
        path = TARGET / name
        if path.exists() and path.read_text(encoding='utf-8') == text:
            continue
        stale.append(name)
        if not args.check:
            path.write_text(text, encoding='utf-8')

    if args.check and stale:
        print('out of date: ' + ', '.join(stale), file=sys.stderr)
        print('run: python scripts/sync_docs_data.py', file=sys.stderr)
        return 1
    if stale and not args.check:
        print('updated: ' + ', '.join(stale))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
