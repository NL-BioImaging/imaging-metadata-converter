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

`python scripts/model_fit.py` prints the tables; the MkDocs hook
scripts/docs_data.py puts render() on docs/model-fit.md, so they are never
stored and cannot go stale.
"""

import json
import re
import sys
from collections import Counter
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

    def mechanism(self, source):
        """How the mapper placed the value at `source`: 'rule', 'automatic', or None if it resolves neither way.

        The mapper strips vendor wrapper levels ("FEI_TITAN.FeiImage") before it resolves a path, and rules see
        list items unindexed, so the path is tried as rules see it, from each of its levels down.
        """
        parts = unindexed(source).split('.')
        for start in range(len(parts)):
            path = '.'.join(parts[start:])
            if self.mapper._resolve_rule_path(path) is not None:
                return 'rule'
            if self.mapper._resolve_schema_path(path) is not None:
                return 'automatic'
        return None

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

    def __init__(self, name, dataset, context):
        self.name = name
        value_categories = {}
        schema_paths = {}
        self.fields = {}
        self.automatic = {}
        self.missing_fields = Counter()
        self.unlocated = Counter()
        for field, record in records(dataset):
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
    def extension_fields(self):
        return sum(1 for is_extension in self.fields.values() if is_extension)

    @property
    def limi_fields(self):
        return len(self.fields) - self.extension_fields


def source_values(example_file):
    """Every leaf path of an example, as the dataset's source paths spell them."""
    metadata = json.loads(Path(example_file).read_text(encoding='utf-8'))
    return {suffix[1:] if suffix.startswith('.') else suffix for suffix in leaf_suffixes(metadata)}


def fits(context=None, export_dir=EXPORT_DIR):
    """The ExampleFit of every dataset in `export_dir`, in name order."""
    context = context or FitContext()
    return [ExampleFit(path.stem, yaml.safe_load(path.read_text(encoding='utf-8')), context)
            for path in sorted(Path(export_dir).glob('*.yaml'), key=lambda path: path.stem.lower())]


def _percent(share):
    return f'{100 * share:.0f}%'


def summary_table(example_fits):
    lines = ['| Example | Covered, keys | Covered, values | Keys | '
             + ' | '.join(LABELS[category].capitalize() for category in CATEGORIES) + ' |',
             '| --- | ---: | ---: | ---: | ' + ' | '.join('---:' for _ in CATEGORIES) + ' |']
    for fit in example_fits:
        cells = [str(fit.keys[category]) for category in CATEGORIES]
        covered_values = sum(fit.values[category] for category in COVERED)
        lines.append(f'| {fit.name} | **{_percent(fit.key_coverage)}** '
                     f'| {_percent(fit.value_coverage)} ({covered_values} of {sum(fit.values.values())}) '
                     f'| {sum(fit.keys.values())} | ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def fields_table(example_fits):
    lines = ['| Example | Fields filled | LiMi | Extension |', '| --- | ---: | ---: | ---: |']
    for fit in example_fits:
        lines.append(f'| {fit.name} | {len(fit.fields)} | {fit.limi_fields} | {fit.extension_fields} |')
    return '\n'.join(lines)


def _counted(counter):
    return '\n'.join(f'- `{name}`: {count}' for name, count in counter.most_common(TOP)) \
        + (f'\n- and {len(counter) - TOP} more' if len(counter) > TOP else '')


def details(fit):
    """What explains one example's fit: its automatic matches, and where the keys not covered are."""
    parts = []
    if fit.automatic:
        parts.append('Placed automatically, without a rule (worth checking that each means what the field does):\n\n'
                     + '\n'.join(f'- `{key}` → `{field}`' for key, field in sorted(fit.automatic.items())))
    if fit.missing_fields:
        parts.append('No such field, by the model path the keys were headed for (a group without their field, or a plain field given a record):\n\n' + _counted(fit.missing_fields))
    if fit.unlocated:
        parts.append('No location, by source group:\n\n' + _counted(fit.unlocated))
    return '\n\n'.join(parts) or 'Every key is covered.'


def render(data=None, export_dir=EXPORT_DIR):
    """The model fit page's tables, as Markdown."""
    example_fits = fits(FitContext(data), export_dir)
    sections = [summary_table(example_fits), '## Fields filled', fields_table(example_fits), '## Per example']
    for fit in example_fits:
        sections.append(f'<details markdown>\n<summary>{fit.name}: {_percent(fit.key_coverage)} of '
                        f'{sum(fit.keys.values())} keys covered</summary>\n\n{details(fit)}\n\n</details>')
    return '\n\n'.join(sections)


def main():
    print(render())


if __name__ == '__main__':
    main()
