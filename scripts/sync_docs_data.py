"""Write the model and mapping JSON the docs site reads into docs/data.

The interactive model browser (docs/model.md) fetches these files at runtime,
so MkDocs needs its own copy inside the docs tree:

- model.json - the imaging model's paths as one nested tree, every leaf
  "FieldName": "range", as the mapper sees them (ModelPaths.tree)
- added.json - the paths the imaging model adds to LiMi: its extension
  (mostly electron microscopy) and provenance classes and slots
- mappings.json - the packaged mapping rules

Run after editing the model or the mappings:

    python scripts/sync_docs_data.py

Use --check to fail instead of writing, which is what tests/test_docs_data.py
does so a stale copy cannot be committed unnoticed.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / 'docs' / 'data'
sys.path.insert(0, str(ROOT / 'src'))

from imaging_metadata_converter import DEFAULT_MAPPINGS_FILE, ModelPaths  # noqa: E402

# the one schema of models/ that is LiMi itself; its imports hold what the model adds
LIMI_SCHEMA_SUFFIX = '/models/imaging'


def all_paths(tree, path=''):
    """Every path in `tree`, groups as well as leaves, in model order."""
    for key, value in tree.items():
        current = f'{path}.{key}' if path else key
        yield current
        if isinstance(value, dict):
            yield from all_paths(value, current)


def added_paths(model, tree):
    """The paths of `tree` that run through a class or slot LiMi does not have."""
    added_classes = {name for name, cls in model.classes.items()
                     if not cls.from_schema.endswith(LIMI_SCHEMA_SUFFIX)}

    def declared_only_by_added(class_name, slot_name):
        # a slot name is declared by many classes, so ask the ones this class inherits it from
        declarers = [ancestor for ancestor in model.view.class_ancestors(class_name, mixins=True)
                     if slot_name in (model.view.get_class(ancestor).attributes or {})
                     or slot_name in (model.view.get_class(ancestor).slots or [])]
        return bool(declarers) and all(declarer in added_classes for declarer in declarers)

    def is_added(path):
        first, *rest = path.split('.')
        current = first
        added = first in added_classes
        for name in rest:
            added = added or declared_only_by_added(current, name)
            slot = model.slots(current)[name]
            current = slot.range if slot.range in model.classes else None
        return added

    return [path for path in all_paths(tree) if is_added(path)]


def rendered():
    """{file name: the minified text its docs copy should hold}."""
    model = ModelPaths()
    tree = model.tree()
    mappings = json.loads(Path(DEFAULT_MAPPINGS_FILE).read_text(encoding='utf-8'))
    return {name: json.dumps(data, separators=(',', ':')) for name, data in (
        ('model.json', tree),
        ('added.json', added_paths(model, tree)),
        ('mappings.json', mappings),
    )}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='report stale copies without writing')
    args = parser.parse_args(argv)

    TARGET.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, text in rendered().items():
        path = TARGET / name
        is_current = path.exists() and path.read_text(encoding='utf-8') == text
        if not is_current:
            stale.append(name)
        if not is_current and not args.check:
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
