"""MkDocs hook: the model data the docs read, built from the packaged model.

The interactive model browser (docs/model.md) fetches four JSON files at
runtime. They are not kept in the repository: this hook writes them into
the site as it is built, straight from the packaged model and mappings, so
the browser always shows the model the package ships.

- data/model.json - the imaging model's paths as one nested tree, every leaf
  "FieldName": "range", as the mapper sees them (ModelPaths.tree)
- data/added.json - the paths the imaging model adds to LiMi: its extension
  (mostly electron microscopy) and provenance classes and slots
- data/mappings.json - the packaged mapping rules
- data/details.json - what the model says of each path beyond its range:
  description, LiMi tier, required, multivalued, identifier, reference,
  the class declaring it, Category and Domain, and mappings to OME;
  descriptions are listed once, in "texts", and named by index; and the
  model's root class and each abstract class's concrete subclasses, which
  the browser follows to nest every class under the root; and the
  permissible values of every enumeration a field ranges over, each with
  its description and aliases

It also fills in the pages' {{ model.<name> }} placeholders: the model's
counts on model.md, so no number there is typed by hand, and the examples'
fit (scripts/model_fit.py) on model-fit.md.

mkdocs.yml loads it under `hooks:`.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

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


def declarers(model, class_name, slot_name):
    """The classes `class_name` has `slot_name` from, itself first: a slot name is declared by many classes."""
    return [ancestor for ancestor in model.view.class_ancestors(class_name, mixins=True)
            if slot_name in (model.view.get_class(ancestor).attributes or {})
            or slot_name in (model.view.get_class(ancestor).slots or [])]


def added_classes(model):
    """The classes LiMi does not have: those of the extension and provenance schemas."""
    return {name for name, cls in model.classes.items() if not cls.from_schema.endswith(LIMI_SCHEMA_SUFFIX)}


def declared_only_by_added(model, added, class_name, slot_name):
    """Whether `class_name` has `slot_name` only from classes in `added`."""
    declared = declarers(model, class_name, slot_name)
    return bool(declared) and all(declarer in added for declarer in declared)


def added_paths(model, tree):
    """The paths of `tree` that run through a class or slot LiMi does not have."""
    added = added_classes(model)

    def is_added(path):
        first, *rest = path.split('.')
        current = first
        result = first in added
        for name in rest:
            slot, next_class = model.slot_at(current, name)
            result = result or declared_only_by_added(model, added, current, slot.name) \
                or (name != slot.name and name in added)
            current = next_class
        return result

    return [path for path in all_paths(tree) if is_added(path)]


def leaf_paths(tree, path=''):
    """The paths of `tree` that are fields rather than groups."""
    for key, value in tree.items():
        current = f'{path}.{key}' if path else key
        if isinstance(value, dict):
            yield from leaf_paths(value, current)
        else:
            yield current


def leaf_ranges(tree):
    """The range of every field of `tree`."""
    for value in tree.values():
        if isinstance(value, dict):
            yield from leaf_ranges(value)
        else:
            yield value


def _annotation(element, name):
    annotations = element.annotations
    return str(annotations[name].value) if annotations is not None and name in annotations else None


def _tier(*elements):
    """The higher LiMi tier of `elements`, as the metaseed profile gives a field that of its class too."""
    tiers = [int(tier) for tier in (_annotation(element, 'Tier') for element in elements)
             if tier in ('1', '2', '3', '4')]
    return max(tiers) if tiers else None


def path_details(model, tree):
    """{path: its details} for every path of `tree`, and the descriptions they name by index."""
    texts = {}
    details = {}

    def text(value):
        return texts.setdefault(value, len(texts))

    def describe(element, entry):
        if element.description:
            entry['description'] = text(element.description)
        source = _annotation(element, 'description_source')
        if source:
            entry['description_source'] = text(source)
        # LiMi's XSD spells Domain "Domanin" on two classes
        for key, value in (('category', _annotation(element, 'Category')),
                           ('domain', _annotation(element, 'Domain') or _annotation(element, 'Domanin')),
                           ('exact_mappings', list(element.exact_mappings or [])),
                           ('close_mappings', list(element.close_mappings or []))):
            if value:
                entry[key] = value
        return entry

    def visit(class_name, node, path):
        for name, value in node.items():
            slot, next_class = model.slot_at(class_name, name)
            current = f'{path}.{name}'
            entry = describe(slot, {})
            tier = _tier(slot, model.classes[class_name])
            declared = declarers(model, class_name, slot.name)
            flags = (('tier', tier),
                     ('required', bool(slot.required)),
                     ('multivalued', bool(slot.multivalued)),
                     ('identifier', bool(slot.identifier)),
                     ('reference', slot.range in model.classes and not (slot.inlined or slot.inlined_as_list)),
                     ('declared_by', declared[-1] if declared and declared[-1] != class_name else None))
            entry.update({key: flag for key, flag in flags if flag})
            if isinstance(value, dict):
                entry['class'] = next_class
                visit(next_class, value, current)
            details[current] = entry

    for class_name, node in tree.items():
        cls = model.classes[class_name]
        entry = describe(cls, {'class': class_name})
        entry.update({key: value for key, value in (('tier', _tier(cls)), ('is_a', cls.is_a)) if value})
        details[class_name] = entry
        visit(class_name, node, class_name)
    # an abstract range has no place in the tree, so the browser opens it as the classes that can stand for it
    subclasses = {name: [descendant for descendant in model.view.class_descendants(name, reflexive=False)
                         if descendant in tree]
                  for name, cls in model.classes.items() if cls.abstract}
    all_enums = model.view.all_enums()
    ranges = {value_range for value_range in leaf_ranges(tree) if value_range in all_enums}
    enums = {}
    for name in sorted(ranges):
        enum = all_enums[name]
        values = []
        for value_name, value in (enum.permissible_values or {}).items():
            entry = {'value': value_name}
            if value.description:
                entry['description'] = text(value.description)
            if value.aliases:
                entry['aliases'] = list(value.aliases)
            values.append(entry)
        enums[name] = {'values': values}
        if enum.description:
            enums[name]['description'] = text(enum.description)
    return {'texts': list(texts), 'paths': details, 'root': model.root,
            'subclasses': {name: concrete for name, concrete in subclasses.items() if concrete},
            'enums': enums}


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
            ('details.json', path_details(self.model, self.tree)),
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


def _load_script(name):
    # MkDocs loads this hook by file path, and its plugins may reset
    # sys.path, so load the sibling module by its path too
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    if page.file.src_uri == 'model-fit.md':
        model_fit = _load_script('model_fit')
        return fill(markdown, {'fit': model_fit.render(_model_data())})
    return markdown
