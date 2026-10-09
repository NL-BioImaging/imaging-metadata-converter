import json
import sys
import unittest
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import docs_data
import model_fit


def mapping(field, source, derived_from=None):
    record = {'ID': 'SourceMapping:0', 'Field': field, 'Source': source}
    if derived_from:
        record['Source'] = ' + '.join(derived_from)
        record['DerivedFrom'] = derived_from
    return record


def prop(name, schema_path=None):
    record = {'ID': 'Property:0', 'Name': name, 'Value': '1'}
    if schema_path:
        record['SchemaPath'] = schema_path
    return record


class ModelFitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = model_fit.FitContext()

    def test_each_value_is_placed_in_its_category(self):
        dataset = {
            'Image': [{
                'SourceFile': [{'Mapping': [
                    mapping('Image[0].Pixels.PhysicalSizeX', 'VENDOR.Image.pixelWidth.value'),
                    mapping('Image[0].Pixels.SizeX', 'Pixels.SizeX'),
                    mapping('Image[0].AcquisitionDate', None, ['Date', 'Time']),
                    mapping('Image[0].BeamScanSettings.LineInterlacing', 'Scan.Interlaced'),
                ]}],
                'CustomProperties': [
                    prop('Vendor.Other'),
                    prop('Channel[0].Wavelength', 'Pixels.PhysicalSizeY'),
                    prop('Channel[1].Wavelength'),
                    prop('Scan.scanHW', 'Image.BeamScanSettings.scanHW'),
                ],
            }],
        }
        fit = model_fit.ExampleFit('synthetic', dataset, self.context)
        self.assertEqual(fit.value_categories, {
            'VENDOR.Image.pixelWidth.value': 'rule',
            'Pixels.SizeX': 'automatic',
            'Date': 'rule',
            'Time': 'rule',
            'Scan.Interlaced': 'rule',
            'Vendor.Other': 'no_location',
            'Channel[0].Wavelength': 'no_fit',
            'Channel[1].Wavelength': 'no_location',
            'Scan.scanHW': 'no_field',
        })
        # a key counts in the best category of its values
        self.assertEqual(fit.key_categories['Channel[].Wavelength'], 'no_fit')
        self.assertEqual(sum(fit.keys.values()), 8)
        self.assertEqual(fit.automatic, {'Pixels.SizeX': 'Image.Pixels.SizeX'})
        self.assertEqual(fit.missing_fields, {'Image.BeamScanSettings': 1})
        self.assertEqual(fit.unlocated, {'Vendor.Other': 1})
        self.assertEqual((fit.limi_fields, fit.extension_fields), (3, 1))
        self.assertEqual(fit.key_coverage, 5 / 8)

    def test_a_value_both_placed_and_kept_counts_as_placed(self):
        dataset = {'Image': [{
            'SourceFile': [{'Mapping': [mapping('Image[0].AcquisitionDate', None, ['Date', 'Time'])]}],
            'CustomProperties': [prop('Date')],
        }]}
        fit = model_fit.ExampleFit('synthetic', dataset, self.context)
        self.assertEqual(fit.value_categories['Date'], 'rule')

    def test_every_source_value_of_every_example_is_counted_once(self):
        for export in sorted(model_fit.EXPORT_DIR.glob('*.yaml')):
            fit = model_fit.ExampleFit(export.stem, yaml.safe_load(export.read_text(encoding='utf-8')), self.context)
            with self.subTest(example=fit.name):
                example = model_fit.EXAMPLES_DIR / f'{fit.name}.json'
                leaves = model_fit.source_values(example)
                counted = set(fit.value_categories)
                self.assertEqual(leaves - counted, set())
                # beyond the leaves, only the labels of records keyed by them, which the mapper keeps as data
                metadata = json.loads(example.read_text(encoding='utf-8'))
                for extra in counted - leaves:
                    parent, label = extra.rsplit('.', 1)
                    node = metadata
                    for part in parent.split('.'):
                        node = node[part]
                    self.assertIsInstance(node[label], dict, extra)

    def test_kept_and_traced_fall_short_when_output_and_input_differ(self):
        metadata = {'Image': {'pixelWidth': {'value': 1, 'unit': 'um'}}, 'Vendor': {'Other': 2}}
        dataset = {'Image': [{
            'SourceFile': [{'Mapping': [mapping('Image[0].Pixels.PhysicalSizeX', 'Image.pixelWidth.value')]}],
            'CustomProperties': [prop('Image.pixelWidth.unit'), prop('Nowhere.Else')],
        }]}
        stats = model_fit.analyse(dataset, metadata, self.context)
        # Vendor.Other is lost, and Nowhere.Else names no input value
        self.assertEqual((stats['kept'], stats['traced']), (2 / 3, 2 / 3))
        self.assertEqual(stats['values']['input'], 3)
        self.assertEqual(stats['records'], {'total': 3, 'traced': 2})

    def test_every_example_is_kept_and_traced_in_full(self):
        for stats in model_fit.analyse_examples(self.context):
            with self.subTest(example=stats['name']):
                self.assertEqual((stats['kept'], stats['traced']), (1.0, 1.0))
                self.assertEqual(stats['values']['kept'], stats['values']['input'])

    def test_a_source_dict_is_analysed_as_its_export_is(self):
        name = 'EMSIS Xarosa'
        metadata = json.loads((model_fit.EXAMPLES_DIR / f'{name}.json').read_text(encoding='utf-8'))
        exported = next(stats for stats in model_fit.analyse_examples(self.context) if stats['name'] == name)

        self.assertEqual(model_fit.analyse_metadata(metadata, name, self.context), exported)

    def test_every_out_of_scope_pattern_names_a_key_of_some_example(self):
        keys = set()
        for export in model_fit.EXPORT_DIR.glob('*.yaml'):
            fit = model_fit.ExampleFit(export.stem, yaml.safe_load(export.read_text(encoding='utf-8')), self.context)
            keys |= set(fit.key_categories)
        for kind, patterns in self.context.out_of_scope.items():
            for pattern in patterns:
                with self.subTest(kind=kind, pattern=pattern):
                    self.assertTrue(any(fnmatchcase(key, pattern) for key in keys))

    def test_in_scope_coverage_leaves_out_only_what_is_not_covered(self):
        dataset = {'Image': [{
            'SourceFile': [{'Mapping': [mapping('Image[0].Pixels.SizeX', 'Pixels.SizeX')]}],
            'CustomProperties': [prop('Operations.DisplayLevelsOperation.Level'), prop('Vendor.Other')],
        }]}
        stats = model_fit.analyse(dataset, context=self.context)
        # a Velox operation is processing history: out of scope, so one of the two in-scope keys is covered
        self.assertEqual(stats['in_scope']['out_of_scope'], {'processing': 1})
        self.assertEqual((stats['in_scope']['keys'], stats['in_scope']['coverage']['keys']), (2, 0.5))
        self.assertEqual(stats['coverage']['keys'], 1 / 3)

    def test_page_fills_in(self):
        page = (ROOT / 'docs' / 'model-fit.md').read_text(encoding='utf-8')
        self.assertIn('{{ model.fit }}', page)
        filled = docs_data.fill(page, {'fit': model_fit.render(self.context.data)})
        self.assertNotIn('{{', filled)
        for stats in model_fit.analyse_examples(self.context):
            self.assertIn(f"| {stats['name']} |", filled)


if __name__ == '__main__':
    unittest.main()
