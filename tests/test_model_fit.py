import json
import sys
import unittest
from pathlib import Path

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
                    mapping('Image[0].ScanSettings.LineIntegrationCount', 'integrations'),
                ]}],
                'CustomProperties': [
                    prop('Vendor.Other'),
                    prop('Channel[0].Wavelength', 'Pixels.PhysicalSizeY'),
                    prop('Channel[1].Wavelength'),
                    prop('Scan.scanHW', 'Image.ScanSettings.scanHW'),
                ],
            }],
        }
        fit = model_fit.ExampleFit('synthetic', dataset, self.context)
        self.assertEqual(fit.value_categories, {
            'VENDOR.Image.pixelWidth.value': 'rule',
            'Pixels.SizeX': 'automatic',
            'Date': 'rule',
            'Time': 'rule',
            'integrations': 'rule',
            'Vendor.Other': 'no_location',
            'Channel[0].Wavelength': 'no_fit',
            'Channel[1].Wavelength': 'no_location',
            'Scan.scanHW': 'no_field',
        })
        # a key counts in the best category of its values
        self.assertEqual(fit.key_categories['Channel[].Wavelength'], 'no_fit')
        self.assertEqual(sum(fit.keys.values()), 8)
        self.assertEqual(fit.automatic, {'Pixels.SizeX': 'Image.Pixels.SizeX'})
        self.assertEqual(fit.missing_fields, {'Image.ScanSettings': 1})
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
        for fit in model_fit.fits(self.context):
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

    def test_page_fills_in(self):
        page = (ROOT / 'docs' / 'model-fit.md').read_text(encoding='utf-8')
        self.assertIn('{{ model.fit }}', page)
        filled = docs_data.fill(page, {'fit': model_fit.render(self.context.data)})
        self.assertNotIn('{{', filled)
        for fit in model_fit.fits(self.context):
            self.assertIn(f'| {fit.name} |', filled)


if __name__ == '__main__':
    unittest.main()
