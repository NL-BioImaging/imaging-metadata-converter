"""Every source metadata value and key must survive conversion.

The converted output carries a SourceMap of {output path: source path} for
every leaf. The check is exact: each source leaf must sit, with the same
value and type (so 1, 1.0, True and "1" stay distinct), at the output path
the SourceMap records for it, so both the value and its original key path
are recoverable from the output alone. Nulls and empty dicts and lists count
as leaves.
"""

import glob
import json
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from imaging_metadata_converter import SOURCE_MAP_KEY, AcquisitionMetadataMapper


EXAMPLES_DIR = os.path.join(REPO_ROOT, 'examples')


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

    # a value combined from several parts (combinations.json) is extra: it recovers none of its parts
    derived = {output_path: parts for output_path, parts in source_map.items() if isinstance(parts, list)}
    for output_path, parts in derived.items():
        if output_path not in output:
            problems.append(f'SourceMap names {output_path}, which holds no value')
        problems += [f'{output_path} is derived from {part}, which does not exist'
                     for part in parts if part not in source_nodes]

    placed = {}
    for output_path, source_path in (entry for entry in source_map.items() if entry[0] not in derived):
        placed.setdefault(source_path, []).append(output_path)
        if output_path not in output:
            problems.append(f'SourceMap names {output_path}, which holds no value')
        elif source_path not in source_nodes:
            problems.append(f'SourceMap names source {source_path}, which does not exist')
        elif not is_leaf(source_nodes[source_path][1]):
            if output[output_path] != source_nodes[source_path][0]:
                problems.append(f'{output_path} should hold the key of {source_path}')
        elif typed(output[output_path]) != typed(source_nodes[source_path][1]):
            problems.append(f'{output_path} holds {typed(output[output_path])}, '
                            f'but its source {source_path} holds {typed(source_nodes[source_path][1])}')

    for source_path, (_, value) in source_nodes.items():
        if is_leaf(value) and source_path not in placed:
            problems.append(f'{source_path} = {typed(value)} is missing from the output')
    for output_path in output:
        if output_path not in source_map:
            problems.append(f'{output_path} has no SourceMap entry')
    return problems


class MissingMetadataTest(unittest.TestCase):
    """The check itself must catch each way metadata can go missing."""

    def test_derived_value_does_not_count_as_keeping_its_parts(self):
        source = {'Date': '10/19/15', 'Time': '17:18:12'}
        converted = {'Date': '10/19/15', 'D': '2015-10-19T17:18:12',
                     SOURCE_MAP_KEY: {'Date': 'Date', 'D': ['Date', 'Time']}}
        self.assertEqual(missing_metadata(source, converted), ["Time = ('str', \"'17:18:12'\") is missing from the output"])

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
                with open(source_file, encoding='utf-8') as file:
                    source = json.load(file)
                problems = missing_metadata(source, self.mapper.convert_metadata(source))
                self.assertEqual(problems, [], '\n'.join(problems))


if __name__ == '__main__':
    unittest.main()
