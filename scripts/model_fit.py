"""How well each example can be expressed in the imaging model, from its dataset in export/.

Every source value of an example ends up in the exported dataset either in a
model field, with a SourceMapping naming its source path, or in a Property
record. That places each value in one of five categories, best first:

- rule: placed by a rule of mappings.json or combinations.json
- automatic: placed without a rule, the mapper matching its source path to a
  model path as it is (a source that uses the model's own names needs no rule)
- no_fit: kept as a Property although the mapper found its model field: the
  value's type, format or enumeration does not fit the field, or it is taken
- no_field: kept as a Property, the mapper having found a model path whose
  group the model has, but no field of that name (Image.ScanSettings.scanHW)
- no_location: kept as a Property, no rule and no model path taking it

The first two are covered. A value the dataset holds twice (a combined date
that is also kept whole) counts in the better of its categories, and so does a
source key, a source path with its list indices removed, whose values differ
(one channel's value fits, another's does not). Keys are the headline, so a
long list of repeated records does not swamp the count; values are given too.
The values are the source's leaves, and the labels the mapper keeps as data:
a record keyed by its label (Detectors.QBSD) becomes a list item that holds
the label, so no key name is lost either.

Whether a placed value came from a rule is asked of the mapper itself, with
the rule and model-path resolution it converts with, so the split is the one
the conversion made. The fields filled are counted as LiMi's or the
extension's, a path counting as extension as soon as it runs through a class
or slot LiMi does not have, as on the model browser.

analyse() returns these stats for one conversion, analyse_metadata() for a
source dict not exported yet, and analyse_examples() for every example;
`python scripts/model_fit.py` prints the tables they give, and the MkDocs hook
scripts/docs_data.py puts render() on docs/model-fit.md, so they are never
stored and cannot go stale.
"""

import json
import re
import sys
from collections import Counter
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from imaging_metadata_converter import AcquisitionMetadataMapper  # noqa: E402
from imaging_metadata_converter.AcquisitionMetadataMapper import leaf_suffixes  # noqa: E402
from docs_data import ModelData, added_classes, all_paths, declared_only_by_added, leaf_paths  # noqa: E402

EXAMPLES_DIR = ROOT / 'examples'
EXPORT_DIR = ROOT / 'export'
# the reviewed source groups that are not acquisition metadata (processing, file, display, ...), by kind
OUT_OF_SCOPE_FILE = ROOT / 'scripts' / 'out_of_scope.json'

CATEGORIES = ('rule', 'automatic', 'no_fit', 'no_field', 'no_location')
COVERED = ('rule', 'automatic')
LABELS = {
    'rule': 'by rule',
    'automatic': 'automatic',
    'no_fit': 'does not fit',
    'no_field': 'no such field',
    'no_location': 'no location',
}
TOP = 10
# the keys the mapper keeps a collapsed record's label under
LABEL_KEYS = ('id', 'ID', 'SourceKey')


def records(node, field=None):
    """(field name, record) for every record in the dataset `node`, the field holding it included."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from records(value, key)
        yield field, node
    elif isinstance(node, list):
        for item in node:
            yield from records(item, field)


def source_key(path):
    return re.sub(r'\[\d+\]', '[]', path)


def unindexed(path):
    return re.sub(r'\[\d+\]', '', path)


def better(first, second):
    return first if first is not None and (second is None or CATEGORIES.index(first) <= CATEGORIES.index(second)) \
        else second


class FitContext:
    """What classifying needs of the model and the mapper, built once for every example."""

    def __init__(self, data=None):
        self.data = data or ModelData()
        self.model = self.data.model
        self.mapper = AcquisitionMetadataMapper()
        self.added = added_classes(self.model)
        self.model_paths = set(all_paths(self.data.tree))
        self.fields = set(leaf_paths(self.data.tree)) | set(self.model.aliases())
        self.out_of_scope = {kind: entry['patterns']
                             for kind, entry in json.loads(OUT_OF_SCOPE_FILE.read_text(encoding='utf-8')).items()}

    def scope_of(self, key):
        """The kind of source key `key` if it is out of scope, not acquisition metadata, else None."""
        return next((kind for kind, patterns in self.out_of_scope.items()
                     if any(fnmatchcase(key, pattern) for pattern in patterns)), None)

    def mechanism(self, source):
        """How the mapper placed the value at `source`: 'rule', 'automatic', or None if it resolves neither way.

        The mapper strips vendor wrapper levels ("FEI_TITAN.FeiImage") before it resolves a path, and rules see
        list items unindexed but for a rule naming one item of a value list ("PixelSpacing[0]"), so the path is
        tried as rules see it, from each of its levels down.
        """
        for path in (re.sub(r'\[\d+\](?!$)', '', source), unindexed(source)):
            parts = path.split('.')
            for start in range(len(parts)):
                level = '.'.join(parts[start:])
                if self.mapper._resolve_rule_path(level) is not None or self._names_an_item_field(level):
                    return 'rule'
                if self.mapper._resolve_schema_path(level) is not None:
                    return 'automatic'
        return None

    def _names_an_item_field(self, level):
        """Whether the value at `level` is in a record a "Prefix.*": "Target[]" rule collapses into an item, as
        is or named by a rule for its field ("Detectors.*.DetectorName"), or is such a record's label, which the
        item records at the record's own path."""
        segments = level.split('.')
        collapsed = any(self.mapper._resolve_whole_segment_wildcard_path('.'.join(segments[:end]))[1]
                        for end in range(1, len(segments) + 1))
        return collapsed or any(
            (len(parts) == len(segments) and fnmatchcase(level, pattern))
            or (parts[-1] in LABEL_KEYS and len(parts) == len(segments) + 1
                and fnmatchcase(level, '.'.join(parts[:-1])))
            for pattern, parts in ((pattern, pattern.split('.')) for pattern in self.mapper.item_fields))

    def is_extension(self, field_path):
        """Whether the dataset field `field_path` (Image[0].ScanSettings.Rotation.Value) runs through a class or
        slot LiMi does not have."""
        current, result = self.model.root, False
        for name in unindexed(field_path).split('.'):
            slots = self.model.slots(current) if current in self.model.classes else {}
            if name in slots:
                result = result or declared_only_by_added(self.model, self.added, current, name)
                current = slots[name].range
            elif name in self.model.classes:
                # the profile has a field per concrete subtype of an abstract slot's range (Instrument.GenericDetector)
                result = result or name in self.added
                current = name
            else:
                raise ValueError(f'{field_path}: {name} is no field of {current}')
        return result

    def model_location(self, schema_path):
        """The longest start of `schema_path` the model has: the group a value without a field was headed for."""
        parts = unindexed(schema_path).split('.')
        return next(('.'.join(parts[:end]) for end in range(len(parts), 0, -1)
                     if '.'.join(parts[:end]) in self.model_paths), parts[0])


class ExampleFit:
    """The fit of one example: its values and keys by category, and what explains the ones not covered."""

    def __init__(self, name, dataset, context, metadata=None):
        self.name = name
        value_categories = {}
        self.output_records = 0
        self.traced_records = 0
        source_nodes = set(all_source_paths(metadata)) if metadata is not None else None
        schema_paths = {}
        self.fields = {}
        self.automatic = {}
        self.missing_fields = Counter()
        self.unlocated = Counter()
        for field, record in records(dataset):
            if field in ('Mapping', 'CustomProperties'):
                named = record.get('DerivedFrom') or [record['Source' if field == 'Mapping' else 'Name']]
                self.output_records += 1
                self.traced_records += source_nodes is None or all(path in source_nodes for path in named)
            if field == 'Mapping':
                sources = record.get('DerivedFrom') or [record['Source']]
                category = 'rule' if record.get('DerivedFrom') else context.mechanism(record['Source'])
                if category is None:
                    raise ValueError(f'{name}: {record["Source"]} is placed, but resolves by no rule or model path')
                for source in sources:
                    value_categories[source] = better(category, value_categories.get(source))
                self.fields[unindexed(record['Field'])] = context.is_extension(record['Field'])
                if category == 'automatic':
                    self.automatic[source_key(record['Source'])] = unindexed(record['Field'])
            if field == 'CustomProperties':
                schema_path = record.get('SchemaPath')
                if schema_path is None:
                    category = 'no_location'
                elif unindexed(schema_path) in context.fields:
                    category = 'no_fit'
                else:
                    category = 'no_field'
                for source in record.get('DerivedFrom') or [record['Name']]:
                    value_categories[source] = better(category, value_categories.get(source))
                    if category == 'no_field':
                        schema_paths.setdefault(source_key(source), schema_path)
        self.value_categories = value_categories
        self.key_categories = {}
        for source, category in value_categories.items():
            key = source_key(source)
            self.key_categories[key] = better(category, self.key_categories.get(key))
        # what explains the keys not covered: the model group lacking their field, the source part with no rule
        for key, category in self.key_categories.items():
            if category == 'no_field':
                self.missing_fields[context.model_location(schema_paths[key])] += 1
            if category == 'no_location':
                self.unlocated['.'.join(key.split('.')[:2])] += 1
        self.values = Counter(value_categories.values())
        self.keys = Counter(self.key_categories.values())
        # a covered key counts as in scope whatever its group: only what the model does not hold can be out of it
        self.out_of_scope_keys = {key: context.scope_of(key) for key, category in self.key_categories.items()
                                  if category not in COVERED and context.scope_of(key)}
        self.out_of_scope_values = sum(1 for source, category in value_categories.items()
                                       if category not in COVERED and source_key(source) in self.out_of_scope_keys)
        self.input_values = source_values_of(metadata) if metadata is not None else set(value_categories)
        self.kept_values = len(self.input_values & set(value_categories))

    @property
    def kept(self):
        """The share of the input's values the output holds, in a field or a Property: always 1, or data is lost."""
        return self.kept_values / len(self.input_values) if self.input_values else 1.0

    @property
    def traced(self):
        """The share of the output's fields and Properties that name the input's values they hold or derive from."""
        return self.traced_records / self.output_records if self.output_records else 1.0

    @staticmethod
    def _share(counts):
        total = sum(counts.values())
        return sum(counts[category] for category in COVERED) / total if total else 0.0

    @property
    def key_coverage(self):
        return self._share(self.keys)

    @property
    def value_coverage(self):
        return self._share(self.values)

    @property
    def in_scope_key_coverage(self):
        in_scope = sum(self.keys.values()) - len(self.out_of_scope_keys)
        return sum(self.keys[category] for category in COVERED) / in_scope if in_scope else 1.0

    @property
    def in_scope_value_coverage(self):
        in_scope = sum(self.values.values()) - self.out_of_scope_values
        return sum(self.values[category] for category in COVERED) / in_scope if in_scope else 1.0

    @property
    def extension_fields(self):
        return sum(1 for is_extension in self.fields.values() if is_extension)

    @property
    def limi_fields(self):
        return len(self.fields) - self.extension_fields

    def stats(self):
        """The fit as plain data, what analyse() returns."""
        return {
            'name': self.name,
            'kept': self.kept,
            'traced': self.traced,
            'coverage': {'keys': self.key_coverage, 'values': self.value_coverage},
            'keys': {'total': sum(self.keys.values()), **{category: self.keys[category] for category in CATEGORIES}},
            'values': {'total': sum(self.values.values()), 'input': len(self.input_values), 'kept': self.kept_values,
                       **{category: self.values[category] for category in CATEGORIES}},
            'records': {'total': self.output_records, 'traced': self.traced_records},
            'fields': {'total': len(self.fields), 'limi': self.limi_fields, 'extension': self.extension_fields},
            'automatic': dict(sorted(self.automatic.items())),
            'missing_fields': dict(self.missing_fields.most_common()),
            'unlocated': dict(self.unlocated.most_common()),
            'in_scope': {
                'keys': sum(self.keys.values()) - len(self.out_of_scope_keys),
                'values': sum(self.values.values()) - self.out_of_scope_values,
                'coverage': {'keys': self.in_scope_key_coverage, 'values': self.in_scope_value_coverage},
                'out_of_scope': dict(Counter(self.out_of_scope_keys.values()).most_common()),
            },
        }


def source_values(example_file):
    """Every leaf path of an example, as the dataset's source paths spell them."""
    return source_values_of(json.loads(Path(example_file).read_text(encoding='utf-8')))


def source_values_of(metadata):
    return {suffix[1:] if suffix.startswith('.') else suffix for suffix in leaf_suffixes(metadata)}


def all_source_paths(node, path=''):
    """Every path of `node`, its records as well as its values: a record's label is kept at the record's path."""
    items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
    for key, value in items:
        current = f'{path}[{key}]' if isinstance(node, list) else (f'{path}.{key}' if path else str(key))
        yield current
        yield from all_source_paths(value, current)


def analyse(dataset, metadata=None, context=None, name=''):
    """The stats of one conversion, as a dict: how much of the source `metadata` its exported `dataset`

    - keeps, in a model field or a Property ("kept"; 1.0, or data is lost),
    - traces back to it, each field and Property naming the values it holds or derives from ("traced"; 1.0, or
      something is made up),
    - places in model fields ("coverage", by keys and by values),

    with the counts behind them by category ("keys", "values"), the fields filled by LiMi and extension
    ("fields"), and what explains the rest: the automatic matches, the model paths lacking a field and the
    source groups with no location. Without `metadata` the dataset is taken as complete."""
    return ExampleFit(name, dataset, context or FitContext(), metadata).stats()


def analyse_metadata(metadata, name='', context=None):
    """analyse() of a source `metadata` dict, converted and exported in memory as dataset_exporter.py would."""
    from dataset_exporter import DatasetExporter
    context = context or FitContext()
    dataset = DatasetExporter().export(context.mapper.convert_metadata(metadata), name or 'source', '0' * 64)
    return analyse(dataset, metadata, context, name)


def analyse_examples(context=None, export_dir=EXPORT_DIR):
    """analyse() of every dataset in `export_dir` against its example, in name order."""
    context = context or FitContext()
    return [analyse(yaml.safe_load(path.read_text(encoding='utf-8')), _example(path.stem), context, path.stem)
            for path in sorted(Path(export_dir).glob('*.yaml'), key=lambda path: path.stem.lower())]


def _example(name):
    example = EXAMPLES_DIR / f'{name}.json'
    return json.loads(example.read_text(encoding='utf-8')) if example.exists() else None


def _percent(share):
    return f'{100 * share:.0f}%'


def summary_table(results):
    lines = ['| Example | Kept | Traced | Covered, keys | Covered, in scope | Covered, values | Keys | '
             + ' | '.join(LABELS[category].capitalize() for category in CATEGORIES) + ' | Out of scope |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ' + ' | '.join('---:' for _ in CATEGORIES)
             + ' | ---: |']
    for result in results:
        values = result['values']
        covered_values = sum(values[category] for category in COVERED)
        lines.append(f"| {result['name']} | {_percent(result['kept'])} | {_percent(result['traced'])} "
                     f"| **{_percent(result['coverage']['keys'])}** "
                     f"| **{_percent(result['in_scope']['coverage']['keys'])}** "
                     f"| {_percent(result['coverage']['values'])} ({covered_values} of {values['total']}) "
                     f"| {result['keys']['total']} | "
                     + ' | '.join(str(result['keys'][category]) for category in CATEGORIES)
                     + f" | {result['keys']['total'] - result['in_scope']['keys']} |")
    return '\n'.join(lines)


def fields_table(results):
    lines = ['| Example | Fields filled | LiMi | Extension |', '| --- | ---: | ---: | ---: |']
    for result in results:
        fields = result['fields']
        lines.append(f"| {result['name']} | {fields['total']} | {fields['limi']} | {fields['extension']} |")
    return '\n'.join(lines)


def _counted(counts):
    ranked = list(counts.items())
    return '\n'.join(f'- `{name}`: {count}' for name, count in ranked[:TOP]) \
        + (f'\n- and {len(ranked) - TOP} more' if len(ranked) > TOP else '')


def details(result):
    """What explains one example's fit: its automatic matches, and where the keys not covered are."""
    parts = []
    if result['automatic']:
        parts.append('Placed automatically, without a rule (worth checking that each means what the field does):\n\n'
                     + '\n'.join(f'- `{key}` → `{field}`' for key, field in result['automatic'].items()))
    if result['missing_fields']:
        parts.append('No such field, by the model path the keys were headed for (a group without their field, '
                     'or a plain field given a record):\n\n' + _counted(result['missing_fields']))
    if result['unlocated']:
        parts.append('No location, by source group:\n\n' + _counted(result['unlocated']))
    if result['in_scope']['out_of_scope']:
        parts.append('Out of scope, not acquisition metadata (scripts/out_of_scope.json):\n\n'
                     + _counted(result['in_scope']['out_of_scope']))
    return '\n\n'.join(parts) or 'Every key is covered.'


def render(data=None, export_dir=EXPORT_DIR):
    """The model fit page's tables, as Markdown."""
    results = analyse_examples(FitContext(data), export_dir)
    sections = [summary_table(results), '## Fields filled', fields_table(results), '## Per example']
    for result in results:
        sections.append(f"<details markdown>\n<summary>{result['name']}: {_percent(result['coverage']['keys'])} of "
                        f"{result['keys']['total']} keys covered</summary>\n\n{details(result)}\n\n</details>")
    return '\n\n'.join(sections)


def main():
    print(render())


if __name__ == '__main__':
    main()
