"""Every source metadata value and key must survive conversion.

The converted output carries a SourceMap of {output path: source path} for
every leaf. The check is exact: each source leaf must sit, with the same
value and type (so 1, 1.0, True and "1" stay distinct), at the output path
the SourceMap records for it, so both the value and its original key path
are recoverable from the output alone, or a value derived from it names it
(combinations.json: a date from its date and time parts holds them, so they
go). Nulls and empty dicts and lists count as leaves. The same holds for the metaseed dataset scripts/dataset_exporter.py
makes of the output.
"""

import glob
import json
import os
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from dataset_exporter import DatasetExporter, export_file
from imaging_metadata_converter import SOURCE_MAP_KEY, AcquisitionMetadataMapper


EXAMPLES_DIR = os.path.join(REPO_ROOT, 'examples')


def read_json(filename):
    with open(filename, encoding='utf-8') as file:
        return json.load(file)


def nodes(node, path=''):
    """Yield (path, key, value) for every dict entry and list item below `node`."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f'{path}.{key}' if path else str(key)
            yield child, key, value
            yield from nodes(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child = f'{path}[{index}]'
            yield child, index, value
            yield from nodes(value, child)


def is_leaf(value):
    return not isinstance(value, (dict, list)) or not value


def typed(value):
    return type(value).__name__, repr(value)


def missing_metadata(source, converted):
    """Describe every way `converted` fails to preserve `source`; empty when nothing is lost."""
    source_map = converted.get(SOURCE_MAP_KEY, {})
    output = {path: value for path, _, value in nodes(converted)
              if not path.startswith(SOURCE_MAP_KEY) and is_leaf(value)}
    source_nodes = {path: (key, value) for path, key, value in nodes(source)}
    problems = []

    # a value combined from parts (combinations.json) holds them, in place of the parts themselves
    derived = {output_path: parts for output_path, parts in source_map.items() if isinstance(parts, list)}
    derived_parts = {part for parts in derived.values() for part in parts}
    for output_path, parts in derived.items():
        if output_path not in output:
            problems.append(f'SourceMap names {output_path}, which holds no value')
        problems += [f'{output_path} is derived from {part}, which does not exist'
                     for part in parts if part not in source_nodes]

    placed = {}
    for output_path, origin in (entry for entry in source_map.items() if entry[0] not in derived):
        # a value in the model's spelling ("OIL" as Oil) records the source's beside its path
        source_path = origin['Source'] if isinstance(origin, dict) else origin
        held = {output_path: origin['SourceValue']} if isinstance(origin, dict) else output
        placed.setdefault(source_path, []).append(output_path)
        if output_path not in output:
            problems.append(f'SourceMap names {output_path}, which holds no value')
        elif source_path not in source_nodes:
            problems.append(f'SourceMap names source {source_path}, which does not exist')
        elif not is_leaf(source_nodes[source_path][1]):
            if output[output_path] != source_nodes[source_path][0]:
                problems.append(f'{output_path} should hold the key of {source_path}')
        elif typed(held[output_path]) != typed(source_nodes[source_path][1]):
            problems.append(f'{output_path} holds {typed(held[output_path])}, '
                            f'but its source {source_path} holds {typed(source_nodes[source_path][1])}')

    for source_path, (_, value) in source_nodes.items():
        if is_leaf(value) and source_path not in placed and source_path not in derived_parts:
            problems.append(f'{source_path} = {typed(value)} is missing from the output')
    for output_path in output:
        if output_path not in source_map:
            problems.append(f'{output_path} has no SourceMap entry')
    return problems


class MissingMetadataTest(unittest.TestCase):
    """The check itself must catch each way metadata can go missing."""

    def test_derived_value_keeps_only_the_parts_it_names(self):
        source = {'Date': '10/19/15', 'Time': '17:18:12', 'Zone': 'GMT'}
        converted = {'D': '2015-10-19T17:18:12', SOURCE_MAP_KEY: {'D': ['Date', 'Time']}}
        self.assertEqual(missing_metadata(source, converted), ["Zone = ('str', \"'GMT'\") is missing from the output"])

    def test_derived_value_from_an_unknown_part_is_caught(self):
        converted = {'A': 1, 'D': 'x', SOURCE_MAP_KEY: {'A': 'A', 'D': ['A', 'Nope']}}
        self.assertEqual(missing_metadata({'A': 1}, converted), ['D is derived from Nope, which does not exist'])

    def test_value_copied_to_several_targets_is_complete(self):
        converted = {'X': 0.5, 'Y': 0.5, SOURCE_MAP_KEY: {'X': 'MPP', 'Y': 'MPP'}}
        self.assertEqual(missing_metadata({'MPP': 0.5}, converted), [])

    def test_renamed_values_with_source_map_are_complete(self):
        converted = {'X': {'Y': 'x'}, 'Z': 1, SOURCE_MAP_KEY: {'X.Y': 'c', 'Z': 'a.b'}}
        self.assertEqual(missing_metadata({'a': {'b': 1}, 'c': 'x'}, converted), [])

    def test_value_without_source_map_entry_is_missing(self):
        problems = missing_metadata({'a': 1}, {'t': 1, SOURCE_MAP_KEY: {}})
        self.assertIn("a = ('int', '1') is missing from the output", problems)
        self.assertIn('t has no SourceMap entry', problems)

    def test_overwritten_value_is_missing(self):
        problems = missing_metadata({'a': 1, 'b': 2}, {'t': 2, SOURCE_MAP_KEY: {'t': 'b'}})
        self.assertEqual(problems, ["a = ('int', '1') is missing from the output"])

    def test_changed_type_is_caught(self):
        problems = missing_metadata({'a': True}, {'t': 1, SOURCE_MAP_KEY: {'t': 'a'}})
        self.assertEqual(problems, ["t holds ('int', '1'), but its source a holds ('bool', 'True')"])

    def test_null_and_empty_containers_count(self):
        problems = missing_metadata({'a': None, 'b': {}, 'c': []}, {SOURCE_MAP_KEY: {}})
        self.assertEqual(len(problems), 3)

    def test_list_items_are_checked_by_index(self):
        converted = {'t': [2, 1], SOURCE_MAP_KEY: {'t[0]': 'a[0]', 't[1]': 'a[1]'}}
        self.assertEqual(len(missing_metadata({'a': [1, 2]}, converted)), 2)

    def test_key_label_must_match_its_key(self):
        source = {'Detectors': {'QBSD': {'gain': 1}}}
        converted = {'D': [{'gain': 1, 'id': 'QBSD'}],
                     SOURCE_MAP_KEY: {'D[0].gain': 'Detectors.QBSD.gain', 'D[0].id': 'Detectors.QBSD'}}
        self.assertEqual(missing_metadata(source, converted), [])
        converted['D'][0]['id'] = 'SED'
        self.assertEqual(missing_metadata(source, converted), ['D[0].id should hold the key of Detectors.QBSD'])


class NoDataLossTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapper = AcquisitionMetadataMapper()
        cls.source_files = sorted(glob.glob(os.path.join(EXAMPLES_DIR, '*.json')))

    def test_sources_exist(self):
        self.assertTrue(self.source_files, 'expected at least one examples/*.json file')

    def test_conversion_keeps_every_value_and_key(self):
        for source_file in self.source_files:
            with self.subTest(source=os.path.basename(source_file)):
                source = read_json(source_file)
                problems = missing_metadata(source, self.mapper.convert_metadata(source))
                self.assertEqual(problems, [], '\n'.join(problems))



def recovered_from_dataset(dataset):
    """({source path: [values]}, [derived-from part lists]) as the dataset records them, from its
    SourceMappings and Properties; a combined value is derived from the parts it names."""
    values = {path: value for path, _, value in nodes(dataset)}
    recovered = {}
    derived = []
    for path, _, value in nodes(dataset):
        records = value if (path.endswith('.Mapping') or path.endswith('.CustomProperties')
                            or path == 'CustomProperties') and isinstance(value, list) else []
        for record in records:
            if 'DerivedFrom' in record:
                derived.append(record['DerivedFrom'])
            elif 'SourceValue' in record:
                # the field holds the model's spelling (a unit "µm"); the record keeps the source's ("um")
                recovered.setdefault(record['Source'], []).append(json.loads(record['SourceValue']))
            elif 'Field' in record:
                recovered.setdefault(record['Source'], []).append(values[record['Field']])
            else:
                recovered.setdefault(record['Name'], []).append(json.loads(record['Value']))
    return recovered, derived


def missing_from_dataset(source, dataset):
    """Describe every source value or key the dataset fails to keep; empty when nothing is lost."""
    recovered, derived = recovered_from_dataset(dataset)
    source_nodes = {path: (key, value) for path, key, value in nodes(source)}
    # one value may fill several fields (a rule naming several targets), but every copy must agree
    problems = [f'{path} is recorded with different values' for path, values in recovered.items()
                if len({typed(value) for value in values}) > 1]
    problems += [f'a derived value names part {part}, which does not exist'
                 for parts in derived for part in parts if part not in source_nodes]
    for path, (key, value) in source_nodes.items():
        expected = value if is_leaf(value) else key
        if path in recovered and typed(recovered[path][0]) != typed(expected):
            problems.append(f'{path} holds {typed(recovered[path][0])}, but the source holds {typed(expected)}')
        elif path not in recovered and is_leaf(value) and not any(path in parts for parts in derived):
            problems.append(f'{path} = {typed(value)} is missing from the dataset')
    problems += [f'dataset records unknown source path {path}' for path in recovered if path not in source_nodes]
    return problems


class DatasetNoDataLossTest(unittest.TestCase):
    """Every source value and key must be recoverable from the exported metaseed dataset alone."""

    @classmethod
    def setUpClass(cls):
        cls.mapper = AcquisitionMetadataMapper()
        cls.exporter = DatasetExporter()
        cls.source_files = sorted(glob.glob(os.path.join(EXAMPLES_DIR, '*.json')))

    def test_missing_from_dataset_accepts_equal_copies_only(self):
        mappings = [{'Field': 'X', 'Source': 'MPP'}, {'Field': 'Y', 'Source': 'MPP'}]
        self.assertEqual(missing_from_dataset({'MPP': 0.5}, {'X': 0.5, 'Y': 0.5, 'S': {'Mapping': mappings}}), [])
        self.assertEqual(missing_from_dataset({'MPP': 0.5}, {'X': 0.5, 'Y': 0.6, 'S': {'Mapping': mappings}}),
                         ['MPP is recorded with different values'])

    def test_missing_from_dataset_takes_a_derived_value_for_the_parts_it_names(self):
        mapping = {'Field': 'D', 'Source': 'Date + Time', 'DerivedFrom': ['Date', 'Time']}
        problems = missing_from_dataset({'Date': 'd', 'Time': 't', 'Zone': 'z'}, {'D': 'x', 'S': {'Mapping': [mapping]}})
        self.assertEqual(problems, ["Zone = ('str', \"'z'\") is missing from the dataset"])

    def test_missing_from_dataset_recovers_a_respelled_value_from_its_source_value(self):
        mapping = {'Field': 'U', 'Source': 'unit', 'SourceValue': '"um"'}
        self.assertEqual(missing_from_dataset({'unit': 'um'}, {'U': 'µm', 'S': {'Mapping': [mapping]}}), [])
        wrong = {**mapping, 'SourceValue': '"nm"'}
        self.assertEqual(len(missing_from_dataset({'unit': 'um'}, {'U': 'µm', 'S': {'Mapping': [wrong]}})), 1)

    def test_missing_from_dataset_catches_a_lost_value(self):
        dataset = {'CustomProperties': [{'Name': 'a', 'Value': '1'}]}
        self.assertEqual(missing_from_dataset({'a': 1, 'b': 2}, dataset), ["b = ('int', '2') is missing from the dataset"])
        self.assertEqual(missing_from_dataset({'a': '1'}, dataset), ["a holds ('int', '1'), but the source holds ('str', \"'1'\")"])

    def test_export_keeps_every_value_and_key(self):
        for source_file in self.source_files:
            with self.subTest(source=os.path.basename(source_file)):
                source = read_json(source_file)
                dataset = self.exporter.export(self.mapper.convert_metadata(source), 'source.json', '0' * 64)
                problems = missing_from_dataset(source, dataset)
                self.assertEqual(problems, [], '\n'.join(problems))

    def test_written_dataset_keeps_every_value_and_key(self):
        with tempfile.TemporaryDirectory() as directory:
            for source_file in self.source_files:
                with self.subTest(source=os.path.basename(source_file)):
                    source = read_json(source_file)
                    output_file = os.path.join(directory, os.path.basename(source_file) + '.yaml')
                    export_file(source_file, output_file, self.mapper, self.exporter)
                    with open(output_file, encoding='utf-8') as file:
                        problems = missing_from_dataset(source, yaml.safe_load(file))
                    self.assertEqual(problems, [], '\n'.join(problems))


if __name__ == '__main__':
    unittest.main()
