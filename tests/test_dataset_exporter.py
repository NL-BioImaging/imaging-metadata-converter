import glob
import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import yaml

from dataset_exporter import (PROVENANCE_ENTITIES, SOURCE_DIR as SOURCES_DIR, TARGET_DIR as EXPORT_DIR,
                              DatasetExporter, export_file, fits)
from imaging_metadata_converter import AcquisitionMetadataMapper
from metaseed_generator import DEFAULT_PROFILE_FILE as PROFILE_FILE


def read_json(filename):
    with open(filename, encoding='utf-8') as file:
        return json.load(file)


def read_yaml(filename):
    with open(filename, encoding='utf-8') as file:
        return yaml.safe_load(file)
CHECKSUM = '0' * 64


def unknown_keys(exporter, node, entity, path=''):
    """Paths of keys in `node` that `entity` does not declare, recursing into nested entities."""
    fields = exporter.entities[entity]
    unknown = []
    for key, value in node.items():
        key_path = f'{path}.{key}' if path else key
        field = fields.get(key)
        child = exporter._nested_entity(field) if field is not None else None
        if field is None:
            unknown.append(key_path)
        elif child is not None:
            records = value if isinstance(value, list) else [value]
            for index, record in enumerate(records):
                record_path = f'{key_path}[{index}]' if isinstance(value, list) else key_path
                unknown += unknown_keys(exporter, record, child, record_path)
    return unknown


class FitsTest(unittest.TestCase):
    def test_types_must_match_exactly(self):
        self.assertTrue(fits('a', {'type': 'string'}))
        self.assertFalse(fits(1, {'type': 'string'}))
        self.assertTrue(fits(1, {'type': 'integer'}))
        self.assertFalse(fits(True, {'type': 'integer'}))
        self.assertFalse(fits(1.5, {'type': 'integer'}))
        self.assertTrue(fits(1, {'type': 'float'}))
        self.assertFalse(fits(None, {'type': 'string'}))
        self.assertTrue(fits(['a', 'b'], {'type': 'list', 'items': 'string'}))
        self.assertFalse(fits(['a', 1], {'type': 'list', 'items': 'string'}))

    def test_constraints_must_hold(self):
        self.assertTrue(fits('µm', {'type': 'string', 'constraints': {'enum': ['µm']}}))
        self.assertFalse(fits('um', {'type': 'string', 'constraints': {'enum': ['µm']}}))
        self.assertFalse(fits('ABC', {'type': 'string', 'constraints': {'pattern': '^[a-z]+$'}}))

    def test_dates_and_uris_must_parse(self):
        self.assertTrue(fits('2015-10-19', {'type': 'date'}))
        self.assertFalse(fits('19/10/2015', {'type': 'date'}))
        self.assertTrue(fits('2015-10-19T17:18:12-05:00', {'type': 'datetime'}))
        # ISO 8601 variations are taken as they come, without converting them
        self.assertTrue(fits('2025-05-28 10:54:00', {'type': 'datetime'}))
        self.assertTrue(fits('2024-02-06T13:21:05Z', {'type': 'datetime'}))
        self.assertFalse(fits('yesterday', {'type': 'datetime'}))
        self.assertFalse(fits('0', {'type': 'datetime'}))
        self.assertTrue(fits('https://example.org/spec.pdf', {'type': 'uri'}))
        self.assertFalse(fits(3, {'type': 'uri'}))


class DatasetExporterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exporter = DatasetExporter(PROFILE_FILE)

    def export(self, converted):
        return self.exporter.export(converted, 'source.json', CHECKSUM)

    def test_fitting_value_goes_into_its_field_with_a_mapping(self):
        dataset = self.export({'Image': {'Name': 'x'}, 'SourceMap': {'Image.Name': 'title'}})

        image = dataset['Image'][0]
        self.assertEqual(image['Name'], 'x')
        self.assertEqual(image['SourceFile'][0]['Mapping'],
                         [{'ID': 'SourceMapping:0', 'Field': 'Image[0].Name', 'Source': 'title'}])
        self.assertNotIn('CustomProperties', image)

    def test_unit_spelled_otherwise_is_stored_as_the_models_unit(self):
        dataset = self.export({'Pixels': {'PhysicalSizeXUnit': 'um', 'PhysicalSizeYUnit': 'micrometre'},
                               'SourceMap': {'Pixels.PhysicalSizeXUnit': 'pixelWidth.unit',
                                             'Pixels.PhysicalSizeYUnit': 'pixelHeight.unit'}})

        image = dataset['Image'][0]
        self.assertEqual(image['Pixels'], {'PhysicalSizeXUnit': 'µm', 'PhysicalSizeYUnit': 'µm'})
        self.assertEqual([(mapping['Source'], mapping['SourceValue']) for mapping in image['SourceFile'][0]['Mapping']],
                         [('pixelWidth.unit', '"um"'), ('pixelHeight.unit', '"micrometre"')])

    def test_number_written_as_text_is_stored_as_a_number(self):
        dataset = self.export({'Pixels': {'SizeX': '2048', 'PhysicalSizeX': ' 4.0000000000000011e-09'},
                               'SourceMap': {'Pixels.SizeX': 'Scan.ScanSize.width',
                                             'Pixels.PhysicalSizeX': 'BinaryResult.PixelSize.width'}})

        image = dataset['Image'][0]
        self.assertEqual(image['Pixels'], {'SizeX': 2048, 'PhysicalSizeX': 4.0000000000000011e-09})
        self.assertEqual([mapping['SourceValue'] for mapping in image['SourceFile'][0]['Mapping']],
                         ['"2048"', '" 4.0000000000000011e-09"'])

    def test_number_is_stored_as_text_in_a_text_field(self):
        dataset = self.export({'Objective': {'CatalogNumber': 11506432},
                               'SourceMap': {'Objective.CatalogNumber': 'ObjectiveNumber'}})

        mapping = dataset['Image'][0]['SourceFile'][0]['Mapping'][0]
        self.assertEqual(dataset['Instrument'][0]['Objective'][0]['CatalogNumber'], '11506432')
        self.assertEqual(mapping['SourceValue'], '11506432')

    def test_true_or_false_written_as_text_is_stored_as_a_boolean(self):
        dataset = self.export({'Laser': {'Tuneable': 'true', 'IsPumped': 'False'},
                               'SourceMap': {'Laser.Tuneable': 'tuneable', 'Laser.IsPumped': 'pumped'}})

        laser = dataset['Instrument'][0]['Laser'][0]
        self.assertEqual((laser['Tuneable'], laser['IsPumped']), (True, False))
        self.assertEqual([mapping['SourceValue'] for mapping in dataset['Image'][0]['SourceFile'][0]['Mapping']],
                         ['"true"', '"False"'])

    def test_one_or_zero_written_as_text_is_stored_as_a_boolean(self):
        dataset = self.export({'Laser': {'Tuneable': '1', 'IsPumped': '0', 'Pulse': '2'},
                               'SourceMap': {'Laser.Tuneable': 'a', 'Laser.IsPumped': 'b', 'Laser.Pulse': 'c'}})

        laser = dataset['Instrument'][0]['Laser'][0]
        self.assertEqual((laser['Tuneable'], laser['IsPumped']), (True, False))
        self.assertNotIn('Pulse', laser)

    def test_integer_flag_is_stored_as_a_boolean(self):
        dataset = self.export({'Laser': {'Tuneable': 1, 'IsPumped': 0, 'Pulse': 2},
                               'SourceMap': {'Laser.Tuneable': 'a', 'Laser.IsPumped': 'b', 'Laser.Pulse': 'c'}})

        laser = dataset['Instrument'][0]['Laser'][0]
        self.assertEqual((laser['Tuneable'], laser['IsPumped']), (True, False))
        self.assertNotIn('Pulse', laser)
        # 1 == True, so the source's integers are kept by type, not by value
        self.assertEqual([mapping['SourceValue'] for mapping in dataset['Image'][0]['SourceFile'][0]['Mapping']],
                         ['1', '0'])

    def test_text_that_is_no_fitting_number_stays_a_property(self):
        for text in ('1.5', 'wide', 'nan', 'inf', ''):
            with self.subTest(text=text):
                dataset = self.export({'Pixels': {'SizeX': text}, 'SourceMap': {'Pixels.SizeX': 'width'}})
                self.assertEqual(dataset['Image'][0]['Pixels'], {})
        dataset = self.export({'Objective': {'CatalogNumber': True}, 'SourceMap': {'Objective.CatalogNumber': 'n'}})
        instrument = dataset['Instrument'][0]
        self.assertEqual(instrument['Objective'], [{}])
        self.assertEqual(instrument['CustomProperties'][0]['Value'], 'true')

    def test_value_that_does_not_fit_becomes_a_property(self):
        dataset = self.export({'Pixels': {'PhysicalSizeXUnit': 'micro', 'SizeX': 1.5},
                               'SourceMap': {'Pixels.PhysicalSizeXUnit': 'unit', 'Pixels.SizeX': 'Pixels.SizeX'}})

        image = dataset['Image'][0]
        self.assertEqual(image['Pixels'], {})
        self.assertEqual(image['CustomProperties'], [
            {'ID': 'Property:0', 'Name': 'unit', 'Value': '"micro"', 'SchemaPath': 'Pixels.PhysicalSizeXUnit',
             'Source': 'SourceFile:0'},
            {'ID': 'Property:1', 'Name': 'Pixels.SizeX', 'Value': '1.5', 'Source': 'SourceFile:0'},
        ])

    def test_entity_is_placed_along_the_profile_tree(self):
        dataset = self.export({'Plane': {'TheZ': 3}, 'Objective': {'LensNA': 1.4}, 'Filament': {'Name': 'lamp'},
                               'SourceMap': {'Plane.TheZ': 'z', 'Objective.LensNA': 'na', 'Filament.Name': 'lamp'}})

        self.assertEqual(dataset['Image'][0]['Pixels']['Plane'], [{'TheZ': 3}])
        self.assertEqual(dataset['Instrument'][0]['Objective'], [{'LensNA': 1.4}])
        self.assertEqual(dataset['Instrument'][0]['Filament'], [{'Name': 'lamp'}])

    def test_components_nest_in_the_class_their_path_starts_at(self):
        dataset = self.export({'Image': {'ElectronBeamSettings': {'WorkingDistance': {'Value': 0.005, 'Unit': 'm'}}},
                               'SourceMap': {'Image.ElectronBeamSettings.WorkingDistance.Value': 'Beam.WD',
                                             'Image.ElectronBeamSettings.WorkingDistance.Unit': 'Beam.WDUnit'}})

        image = dataset['Image'][0]
        self.assertEqual(image['ElectronBeamSettings'], {'WorkingDistance': {'Value': 0.005, 'Unit': 'm'}})
        self.assertEqual([mapping['Field'] for mapping in image['SourceFile'][0]['Mapping']],
                         ['Image[0].ElectronBeamSettings.WorkingDistance.Value',
                          'Image[0].ElectronBeamSettings.WorkingDistance.Unit'])

    def test_unmodelled_values_go_to_the_nearest_anchor(self):
        dataset = self.export({'Instrument': {'Colour': 'grey'}, 'Scanner': {'Speed': 2},
                               'SourceMap': {'Instrument.Colour': 'Colour', 'Scanner.Speed': 'Scanner.Speed'}})

        self.assertEqual([record['Name'] for record in dataset['Instrument'][0]['CustomProperties']], ['Colour'])
        self.assertEqual([record['Name'] for record in dataset['CustomProperties']], ['Scanner.Speed'])

    def test_taken_field_keeps_the_second_value_as_a_property(self):
        dataset = self.export({'Image': {'Name': 'a'}, 'Other': {'Image': {'Name': 'b'}},
                               'SourceMap': {'Image.Name': 'n1', 'Other.Image.Name': 'n2'}})

        image = dataset['Image'][0]
        self.assertEqual(image['Name'], 'a')
        self.assertEqual([(record['Name'], record['Value']) for record in image['CustomProperties']], [('n2', '"b"')])

    def test_null_and_empty_values_become_properties(self):
        dataset = self.export({'a': None, 'b': {}, 'SourceMap': {'a': 'a', 'b': 'b'}})

        self.assertEqual([record['Value'] for record in dataset['CustomProperties']], ['null', '{}'])

    def test_sources_export_only_declared_fields(self):
        mapper = AcquisitionMetadataMapper()
        for source_file in sorted(glob.glob(os.path.join(SOURCES_DIR, '*.json'))):
            with self.subTest(source=os.path.basename(source_file)):
                dataset = self.export(mapper.convert_metadata(read_json(source_file)))
                self.assertEqual(unknown_keys(self.exporter, dataset, 'OME'), [])

    def test_provenance_entities_are_not_placement_targets(self):
        for entity in PROVENANCE_ENTITIES:
            self.assertNotIn(entity, self.exporter.paths)


class ExportFolderTest(unittest.TestCase):
    """export/ must hold what exporting examples/ against the generated profile gives today."""

    REGENERATE = 'rerun: python scripts/dataset_exporter.py'

    def test_export_holds_one_dataset_per_source(self):
        sources = {os.path.splitext(os.path.basename(path))[0] for path in glob.glob(os.path.join(SOURCES_DIR, '*.json'))}
        exported = {os.path.splitext(os.path.basename(path))[0] for path in glob.glob(os.path.join(EXPORT_DIR, '*.yaml'))}
        self.assertEqual(exported, sources, self.REGENERATE)

    def test_export_is_up_to_date(self):
        mapper = AcquisitionMetadataMapper()
        exporter = DatasetExporter(PROFILE_FILE)
        with tempfile.TemporaryDirectory() as directory:
            for source_file in sorted(glob.glob(os.path.join(SOURCES_DIR, '*.json'))):
                name = os.path.splitext(os.path.basename(source_file))[0] + '.yaml'
                with self.subTest(source=name):
                    fresh = os.path.join(directory, name)
                    export_file(source_file, fresh, mapper, exporter)
                    self.assertEqual(read_yaml(os.path.join(EXPORT_DIR, name)), read_yaml(fresh),
                                     self.REGENERATE)

    def test_every_derived_value_fits_its_field(self):
        """A value the mapper derives is written for a model field, so it must fit it: one kept as a Property
        instead was written in the wrong form (a laser's Role as text, where the field is a list)."""
        def derived_properties(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    records = value if key == 'CustomProperties' else []
                    yield from (record.get('SchemaPath') for record in records if 'DerivedFrom' in record)
                    yield from derived_properties(value) if key != 'CustomProperties' else ()
            elif isinstance(node, list):
                for item in node:
                    yield from derived_properties(item)

        for export in sorted(glob.glob(os.path.join(EXPORT_DIR, '*.yaml'))):
            with self.subTest(export=os.path.basename(export)):
                self.assertEqual(list(derived_properties(read_yaml(export))), [])


if __name__ == '__main__':
    unittest.main()
