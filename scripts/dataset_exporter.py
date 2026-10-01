"""Export converted metadata as a metaseed dataset of the imaging profile.

Takes AcquisitionMetadataMapper output (model paths, see ModelPaths, plus
its SourceMap) and builds one OME document for the profile generated from
the model (profile/imaging.metaseed.yaml). A value goes into a typed field
only if it fits, as it is or as the model spells it (a unit alias, a number
written as text); anything else becomes a Property record holding its
source path and JSON-encoded value, so no metadata is lost. Every value
placed in a typed field gets a SourceMapping record on the SourceFile, so its
source key is kept too.
"""

import argparse
import collections
import datetime
import hashlib
import json
import math
import os.path
import re
from pathlib import Path

import yaml

from imaging_metadata_converter.AcquisitionMetadataMapper import SOURCE_MAP_KEY, AcquisitionMetadataMapper, leaf_suffixes
from imaging_metadata_converter.ModelPaths import DEFAULT_MODEL_FILE, ModelPaths
from metaseed_generator import DEFAULT_PROFILE_FILE, ROOT

SOURCE_DIR = ROOT / 'examples'
TARGET_DIR = ROOT / 'export'

# the provenance classes of imaging_provenance.yaml, and the classes holding CustomProperties
ROOT_ENTITY = 'OME'
PROPERTY_ENTITY = 'Property'
SOURCE_FILE_ENTITY = 'SourceFile'
SOURCE_MAPPING_ENTITY = 'SourceMapping'
CUSTOM_PROPERTIES_ANCHORS = ('OME', 'Image', 'Instrument')
PROVENANCE_ENTITIES = (PROPERTY_ENTITY, SOURCE_FILE_ENTITY, SOURCE_MAPPING_ENTITY)


def file_checksum(filename):
    with open(filename, 'rb') as file:
        return hashlib.sha256(file.read()).hexdigest()


class DatasetExporter:
    def __init__(self, profile_filename=DEFAULT_PROFILE_FILE, model_filename=DEFAULT_MODEL_FILE):
        with open(profile_filename, encoding='utf-8') as file:
            profile = yaml.safe_load(file)
        self.entities = {name: {field['name']: field for field in entity['fields']}
                         for name, entity in profile['entities'].items()}
        self.paths = self._shortest_paths()
        # Only a class a model path starts at is placed by its name: a source's "Quantity" subtree is no
        # ElectronBeam.WorkingDistance, although that is where the first Quantity entity sits. An abstract
        # class's name places into its default subtype (a Leica DetectorList.Detector into GenericDetector).
        model = ModelPaths(model_filename)
        self.placeable = {name: name for name in model.tree() if name in self.paths}
        for name, cls in model.classes.items():
            default = model.default_subtype(name) if cls.abstract else None
            if default in self.placeable:
                self.placeable[name] = default
        # the model's spellings of a unit enumeration's values ({"um": "µm", ...}), by the values it allows
        self.aliases = {frozenset(enum.permissible_values): {alias: value for value, spec in
                                                              enum.permissible_values.items() for alias in spec.aliases}
                        for enum in model.view.all_enums().values()
                        if any(spec.aliases for spec in enum.permissible_values.values())}

    def fitting(self, value, field):
        """(True, what `field` stores for `value`) when it fits as is, as a value its unit enumeration spells
        differently ("um" as "µm"), as the number or boolean a source writes as text ("80000" in a float
        field, "true" in a boolean one), or as the text of a number (11506432 in a string field); else
        (False, None). The value's SourceMapping then
        keeps the source's own in SourceValue."""
        if fits(value, field):
            return True, value
        allowed = field.get('constraints', {}).get('enum')
        spelled = self.aliases.get(frozenset(allowed or ()), {}).get(value) if isinstance(value, str) else None
        return next(((True, stored) for stored in (spelled, _as_number(value), _as_boolean(value), _as_text(value))
                     if stored is not None and fits(stored, field)), (False, None))

    def _nested_entity(self, field):
        if field['type'] in ('entity', 'list') and field.get('items') in self.entities:
            return field['items']
        return None

    def _shortest_paths(self):
        """Each reachable entity's first shortest path from the root, as (field, entity, is_list) steps."""
        paths = {ROOT_ENTITY: []}
        queue = collections.deque([ROOT_ENTITY])
        while queue:
            parent = queue.popleft()
            for field in self.entities[parent].values():
                child = self._nested_entity(field)
                if child is not None and child not in paths and child not in PROVENANCE_ENTITIES:
                    paths[child] = paths[parent] + [(field['name'], child, field['type'] == 'list')]
                    queue.append(child)
        return paths

    def export(self, converted, source_name, checksum, file_format=None):
        """Build the OME dataset for one converted source file."""
        export = _Export(self, converted[SOURCE_MAP_KEY])
        image = export.instance_at(self.paths['Image'])
        source_file = {'ID': 'SourceFile:0', 'Name': source_name, 'Checksum': checksum}
        if file_format:
            source_file['Format'] = file_format
        image.node.setdefault('SourceFile', []).append(source_file)
        export.source_file = source_file
        export.walk({key: value for key, value in converted.items() if key != SOURCE_MAP_KEY}, '',
                    export.root)
        if export.mappings:
            source_file['Mapping'] = export.mappings
        return export.root.node


class _Instance:
    def __init__(self, entity, node, path, anchor):
        self.entity = entity
        self.node = node
        self.path = path
        self.anchor = anchor if anchor is not None else self

    def child_path(self, field, index=None):
        path = f'{self.path}.{field}' if self.path else field
        return path if index is None else f'{path}[{index}]'


class _Export:
    def __init__(self, exporter, source_map):
        self.exporter = exporter
        self.source_map = source_map
        self.root = _Instance(ROOT_ENTITY, {'ID': 'OME:0'}, '', None)
        self.mappings = []
        self.property_count = 0
        self.source_file = None

    def child(self, parent, field, entity, is_list, index=0):
        """The `index`-th instance of `entity` in `parent`'s `field`, created if absent."""
        if is_list:
            items = parent.node.setdefault(field, [])
            while len(items) <= index:
                items.append({})
            node, path = items[index], parent.child_path(field, index)
        else:
            node, path = parent.node.setdefault(field, {}), parent.child_path(field)
        return _Instance(entity, node, path, None if entity in CUSTOM_PROPERTIES_ANCHORS else parent.anchor)

    def instance_at(self, steps, index=0):
        instance = self.root
        for position, (field, entity, is_list) in enumerate(steps):
            instance = self.child(instance, field, entity, is_list, index if position == len(steps) - 1 else 0)
        return instance

    def entity_named(self, key):
        return self.exporter.placeable.get(key)

    def walk(self, node, path, anchor_only, instance=None):
        """Place every entry of `node` (at mapper output `path`): in `instance`'s fields, a new entity, or a Property."""
        for key, value in node.items():
            converted_path = f'{path}.{key}' if path else str(key)
            field = self.exporter.entities[instance.entity].get(key) if instance is not None else None
            entity = self.entity_named(key)
            is_record = isinstance(value, dict) and value
            is_record_list = isinstance(value, list) and value and all(isinstance(item, dict) and item for item in value)
            nested = self.exporter._nested_entity(field) if field is not None else None
            if nested is not None and (is_record or (is_record_list and field['type'] == 'list')):
                records = value if is_record_list else [value]
                for index, record in enumerate(records):
                    child = self.child(instance, key, nested, field['type'] == 'list', index)
                    item_path = f'{converted_path}[{index}]' if is_record_list else converted_path
                    self.walk(record, item_path, child.anchor, child)
            elif field is not None and nested is None and key not in instance.node                     and self.exporter.fitting(value, field)[0]:
                stored = self.exporter.fitting(value, field)[1]
                instance.node[key] = stored
                # the type too: 0 == False, but a stored False keeps the source's 0 only in SourceValue
                changed = stored != value or type(stored) is not type(value)
                respelled = self.source_map[converted_path]
                source_value = respelled['SourceValue'] if isinstance(respelled, dict) else value if changed else None
                self.add_mapping(instance.child_path(key), converted_path, source_value)
            elif field is None and entity is not None and (is_record or is_record_list):
                records = value if is_record_list else [value]
                for index, record in enumerate(records):
                    target = self.instance_at(self.exporter.paths[entity], index)
                    item_path = f'{converted_path}[{index}]' if is_record_list else converted_path
                    self.walk(record, item_path, target.anchor, target)
            # a record that fits no field is taken apart like an undeclared one (OME.Operations is declared, as a
            # string, but TALOS holds an object there, whose keys such as "Aperture[C1].Name" no path can re-parse)
            elif (field is None or nested is None) and is_record:
                self.walk(value, converted_path, anchor_only)
            elif (field is None or nested is None) and is_record_list:
                for index, record in enumerate(value):
                    self.walk(record, f'{converted_path}[{index}]', anchor_only)
            else:
                self.add_properties(anchor_only, converted_path, value)

    def add_mapping(self, dataset_path, converted_path, source_value=None):
        mapping = {'ID': f'SourceMapping:{len(self.mappings)}', 'Field': dataset_path}
        mapping.update(_source_fields(self.source_map[converted_path], 'Source'))
        if source_value is not None:
            mapping['SourceValue'] = json.dumps(source_value, ensure_ascii=False)
        self.mappings.append(mapping)

    def add_properties(self, anchor, converted_path, value):
        properties = anchor.node.setdefault('CustomProperties', [])
        for suffix in leaf_suffixes(value):
            leaf_path = f'{converted_path}{suffix}'
            leaf = _value_at(value, suffix)
            record = {'ID': f'Property:{self.property_count}'}
            source = self.source_map[leaf_path]
            record.update(_source_fields(source, 'Name'))
            # a value kept as it is keeps the source's spelling, not the one the mapper gave it for its field
            record['Value'] = json.dumps(source['SourceValue'] if isinstance(source, dict) else leaf, ensure_ascii=False)
            if leaf_path != record['Name']:
                record['SchemaPath'] = leaf_path
            record['Source'] = self.source_file['ID']
            properties.append(record)
            self.property_count += 1


def _source_fields(source, field):
    """The provenance of a value: its source path in `field`, or for a value the mapper combined from
    several source values, those paths joined in `field` and listed in DerivedFrom. A value the mapper respelled
    names its source path in "Source"."""
    if isinstance(source, dict):
        return {field: source['Source']}
    if isinstance(source, list):
        return {field: ' + '.join(source), 'DerivedFrom': list(source)}
    return {field: source}


def _value_at(value, suffix):
    for part in re.findall(r'\.([^.\[]+)|\[(\d+)\]', suffix):
        value = value[part[0]] if part[0] else value[int(part[1])]
    return value


def fits(value, field):
    """Whether `value` can go into `field` as is, so that nothing about it changes."""
    field_type = field['type']
    if field_type == 'list':
        return isinstance(value, list) and all(fits(item, {'type': field.get('items', 'string')}) for item in value)
    constraints = field.get('constraints', {})
    fits_type = {
        'string': isinstance(value, str),
        'uri': isinstance(value, str),
        'date': isinstance(value, str) and _parses(datetime.date.fromisoformat, value),
        'datetime': isinstance(value, str) and _parses(datetime.datetime.fromisoformat, value),
        'integer': isinstance(value, int) and not isinstance(value, bool),
        'float': isinstance(value, (int, float)) and not isinstance(value, bool),
        'boolean': isinstance(value, bool),
    }.get(field_type, False)
    fits_enum = 'enum' not in constraints or (isinstance(value, str) and value in constraints['enum'])
    fits_pattern = ('pattern' not in constraints
                    or (isinstance(value, str) and re.fullmatch(constraints['pattern'], value) is not None))
    return fits_type and fits_enum and fits_pattern


def _as_number(value):
    """The number text `value` writes (TALOS writes every number as a string), else None."""
    if not isinstance(value, str):
        return None
    for parse in (int, float):
        try:
            number = parse(value)
            return number if math.isfinite(number) else None
        except ValueError:
            pass
    return None


def _as_boolean(value):
    """The boolean `value` writes as text ("true", "False", "1", "0") or as an integer flag (Leica's 1 and 0),
    else None."""
    if isinstance(value, int) and not isinstance(value, bool):
        return {1: True, 0: False}.get(value)
    return {'true': True, 'false': False, '1': True, '0': False}.get(value.lower()) if isinstance(value, str) else None


def _as_text(value):
    """The text of a number `value`, else None."""
    return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _parses(parse, text):
    try:
        parse(text)
        return True
    except ValueError:
        return False


def export_file(source_file, output_file, mapper, exporter):
    """Convert one source JSON file and write its dataset to the YAML `output_file`; returns the dataset."""
    with open(source_file, encoding='utf-8') as file:
        converted = mapper.convert_metadata(json.load(file))
    file_format = os.path.splitext(source_file)[1].lstrip('.').lower() or None
    dataset = exporter.export(converted, os.path.basename(source_file), file_checksum(source_file), file_format)
    os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as file:
        yaml.dump(dataset, file, sort_keys=False, allow_unicode=True)
    return dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', default=str(SOURCE_DIR), help='Folder of source metadata files')
    parser.add_argument('--output', default=str(TARGET_DIR), help='Folder to write the datasets to')
    parser.add_argument('--profile', default=DEFAULT_PROFILE_FILE, help='Path to the metaseed profile YAML')
    args = parser.parse_args(argv)

    mapper = AcquisitionMetadataMapper()
    exporter = DatasetExporter(args.profile)
    input_files = sorted(Path(args.input).glob('*.json'))
    if not input_files:
        raise FileNotFoundError(f'No input files found in {args.input}')
    for input_file in input_files:
        output_file = os.path.join(args.output, input_file.stem + '.yaml')
        export_file(str(input_file), output_file, mapper, exporter)
        print(f'Wrote {output_file}')


if __name__ == '__main__':
    main()
