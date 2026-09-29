"""MkDocs hook: the model data the docs read, built from the packaged model.

The interactive model browser (docs/model.md) fetches three JSON files at
runtime. They are not kept in the repository: this hook writes them into
the site as it is built, straight from the packaged model and mappings, so
the browser always shows the model the package ships.

- data/model.json - the imaging model's paths as one nested tree, every leaf
  "FieldName": "range", as the mapper sees them (ModelPaths.tree)
- data/added.json - the paths the imaging model adds to LiMi: its extension
  (mostly electron microscopy) and provenance classes and slots
- data/mappings.json - the packaged mapping rules

It also fills in the model's counts on model.md, written there as
{{ model.<name> }}, so no number on that page is typed by hand.

mkdocs.yml loads it under `hooks:`; gen_model_map.py uses its path helpers.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

from imaging_metadata_converter import DEFAULT_MAPPINGS_FILE, ModelPaths  # noqa: E402

# the one schema of models/ that is LiMi itself; its imports hold what the model adds
LIMI_SCHEMA_SUFFIX = '/models/imaging'
PLACEHOLDER = re.compile(r'\{\{\s*model\.(\w+)\s*\}\}')


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


def leaf_paths(tree, path=''):
    """The paths of `tree` that are fields rather than groups."""
    for key, value in tree.items():
        current = f'{path}.{key}' if path else key
        if isinstance(value, dict):
            yield from leaf_paths(value, current)
        else:
            yield current


def _schema(element):
    """The model file an element is declared in: imaging, extension, provenance or units."""
    return element.from_schema.rsplit('/', 1)[-1]


class ModelData:
    """The packaged model, and everything the docs derive from it."""

    def __init__(self):
        self.model = ModelPaths()
        self.tree = self.model.tree()
        self.added = added_paths(self.model, self.tree)
        self.mappings = json.loads(Path(DEFAULT_MAPPINGS_FILE).read_text(encoding='utf-8'))

    def files(self):
        """{file name: the minified text the site serves under data/}."""
        return {name: json.dumps(data, separators=(',', ':')) for name, data in (
            ('model.json', self.tree),
            ('added.json', self.added),
            ('mappings.json', self.mappings),
        )}

    def counts(self):
        """The numbers model.md quotes, by placeholder name."""
        view = self.model.view
        classes = Counter(_schema(cls) for cls in self.model.classes.values())
        abstract = sum(1 for cls in self.model.classes.values()
                       if cls.abstract and _schema(cls) == 'imaging')
        enums = Counter(_schema(enum) for enum in view.all_enums().values())
        added = set(self.added)
        fields = list(leaf_paths(self.tree))
        return {
            'version': view.schema.version,
            'classes': classes['imaging'],
            'abstract_classes': abstract,
            'enums': enums['imaging'],
            'types': len(view.all_types(imports=False)),
            'extension_classes': classes['extension'],
            'provenance_classes': classes['provenance'],
            'unit_enums': enums['units'],
            'paths': len(list(all_paths(self.tree))),
            'fields': len(fields),
            'added_fields': sum(1 for path in fields if path in added),
            'rules': len(self.mappings),
        }


_data = None


def _model_data():
    global _data
    if _data is None:
        _data = ModelData()
    return _data


def fill(markdown, counts):
    """Replace each {{ model.<name> }} with its count; an unknown name is an error."""
    def replace(match):
        name = match.group(1)
        if name not in counts:
            raise KeyError(f'model.md names an unknown model count: {name}')
        return str(counts[name])
    return PLACEHOLDER.sub(replace, markdown)


# MkDocs hooks ------------------------------------------------------------

def on_startup(command, dirty):
    # `mkdocs serve` rebuilds on every change; read the model afresh each time
    global _data
    _data = None


def on_pre_build(config):
    global _data
    _data = None


def on_files(files, config):
    from mkdocs.structure.files import File
    for name, text in _model_data().files().items():
        files.append(File.generated(config, f'data/{name}', content=text))
    return files


def on_page_markdown(markdown, page, config, files):
    if page.file.src_uri == 'model.md':
        return fill(markdown, _model_data().counts())
    return markdown
