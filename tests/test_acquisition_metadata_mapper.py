import json
import os
import re
import shutil
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from imaging_metadata_converter import convert_metadata
from imaging_metadata_converter.AcquisitionMetadataMapper import (
    DEFAULT_COMBINATIONS_FILE, DEFAULT_MAPPINGS_FILE, AcquisitionMetadataMapper, rule_targets, unit_field)
from imaging_metadata_converter.ModelPaths import ModelPaths, _leaf_paths


class AcquisitionMetadataMapperTest(unittest.TestCase):
    """Tests the dict-in/dict-out schema mapping (no file I/O)."""

    @classmethod
    def setUpClass(cls):
        cls.mapper = AcquisitionMetadataMapper()

    def test_value_spelled_otherwise_is_written_in_the_models_spelling(self):
        converted = self.mapper.convert_metadata({'immersion': 'OIL', 'CameraSettingDefinition': {'Immersion': 'Oil'},
                                                  'voxelSize': {'unit': 'micron'}})

        self.assertEqual(converted['Objective'], {'ImmersionType': 'Oil'})
        self.assertEqual(converted['SourceMap']['Objective.ImmersionType'], {'Source': 'immersion', 'SourceValue': 'OIL'})
        # a source already writing the model's spelling is a plain path; one that collides keeps its own
        self.assertEqual(converted['CameraSettingDefinition'], {'Immersion': 'Oil'})
        self.assertEqual(converted['SourceMap']['CameraSettingDefinition.Immersion'], 'CameraSettingDefinition.Immersion')

    def test_leica_settings_reach_the_objective_without_summary_keys(self):
        settings = {'MicroscopeModel': 'MICA', 'Magnification': 10, 'NumericalAperture': 0.32, 'Immersion': 'DRY',
                    'RefractionIndex': 1}

        converted = self.mapper.convert_metadata({'HardwareSetting': {'CameraSettingDefinition': settings}})

        self.assertEqual(converted['Instrument'], {'Model': 'MICA'})
        self.assertEqual(converted['Objective'], {'Magnification': 10, 'LensNA': 0.32, 'ImmersionType': 'Air'})
        self.assertEqual(converted['ImmersionLiquid'], {'RefractiveIndex': 1})
        self.assertNotIn('HardwareSetting', converted)

    def test_leica_sequential_channels_follow_the_sequences_not_the_bands(self):
        def sequence(detector, *lines):
            return {'DetectorList': {'Detector': [{'Channel': 1, 'IsActive': int(detector == 1)},
                                                  {'Channel': 4, 'IsActive': int(detector == 4)}]},
                    'AotfList': {'Aotf': [{'LightSourceType': light_source_type, 'LaserLineSetting': [
                        {'LaserLine': line, 'IntensityDev': intensity} for line, intensity in settings]}
                        for light_source_type, settings in lines]}}
        settings = {
            'ConfocalSettingDefinition': {
                'Spectro': {'MultiBand': [{'Channel': 1, 'DyeName': 'Leica/Cerulean', 'LeftWorld': 460, 'RightWorld': 490},
                                          {'Channel': 4, 'DyeName': 'Leica/ALEXA 488', 'LeftWorld': 500, 'RightWorld': 550}]},
                'LaserArray': {'Laser': [{'LaserName': '405 Diode', 'LightSourceType': 1},
                                         {'LaserName': 'WLL', 'LightSourceType': 4}]}},
            'LDM_Block_Sequential': {'LDM_Block_Sequential_List': {'ConfocalSettingDefinition': [
                sequence(4, (4, [(488, 24.8), (561, 0)])),
                sequence(1, (1, [(405, 3.1)]), (4, [(488, 76.7)]))]}}}

        converted = self.mapper.convert_metadata({'HardwareSetting': settings})

        first, second = converted['Pixels']['Channel']
        self.assertEqual(first['Name'], 'Leica/ALEXA 488')
        self.assertEqual(first['Fluorophore'], {'Name': 'Leica/ALEXA 488', 'ExcitationWavelength': 488,
                                                'ExcitationWavelengthUnit': 'nm'})
        self.assertEqual(first['LightPath'], {'EmissionFilter': ['Filter:0'], 'LightSourceSettings': [{'ID': 'Laser:1'}]})
        # two lines on: no excitation wavelength chosen between them, a setting for each laser
        self.assertEqual(second['Fluorophore'], {'Name': 'Leica/Cerulean'})
        self.assertEqual(second['LightPath']['LightSourceSettings'], [{'ID': 'Laser:0'}, {'ID': 'Laser:1'}])
        self.assertEqual(converted['Filter'][0], {'ID': 'Filter:0', 'Type': 'BandPass', 'TransmittanceRange': {
            'Wavelength': 525, 'FWHMBandwidth': 50, 'WavelengthUnit': 'nm'}})
        self.assertEqual([laser.get('ID') for laser in converted['Laser']], ['Laser:0', 'Laser:1'])
        # the dyes, band limits and single line are held by the channels now; the two lines and intensities stay
        bands = converted['HardwareSetting']['ConfocalSettingDefinition']['Spectro']['MultiBand']
        self.assertEqual(bands, [{'Channel': 1}, {'Channel': 4}])
        sequences = converted['HardwareSetting']['LDM_Block_Sequential']['LDM_Block_Sequential_List'][
            'ConfocalSettingDefinition']
        self.assertEqual(sequences[0]['AotfList']['Aotf'][0]['LaserLineSetting'][0], {'IntensityDev': 24.8})
        self.assertEqual(sequences[1]['AotfList']['Aotf'][1]['LaserLineSetting'][0], {'LaserLine': 488, 'IntensityDev': 76.7})
        self.assertEqual(converted['SourceMap']['Pixels.Channel[0].Name'],
                         ['HardwareSetting.ConfocalSettingDefinition.Spectro.MultiBand[1].DyeName'])

    def test_time_point_range_is_kept_beside_its_count(self):
        timepoints = {'first': 10, 'last': 14, 'type': 'range'}

        converted = self.mapper.convert_metadata({'SpimData': {'SequenceDescription': {'Timepoints': timepoints}}})

        self.assertEqual(converted['Pixels'], {'TimePoints': {'Begin': 10, 'End': 14}, 'SizeT': 5})
        self.assertEqual(converted['SpimData'], {'SequenceDescription': {'Timepoints': {'type': 'range'}}})

    def test_convert_metadata_accepts_in_memory_dict(self):
        sample = {'Make': 'Acme', 'Model': 'Widget-1000'}

        converted = self.mapper.convert_metadata(sample)

        self.assertEqual(converted, {
            'Instrument': {'Manufacturer': 'Acme', 'Model': 'Widget-1000'},
            'SourceMap': {'Instrument.Manufacturer': 'Make', 'Instrument.Model': 'Model'},
        })

    def test_convert_metadata_rejects_non_dict(self):
        with self.assertRaises(TypeError):
            self.mapper.convert_metadata(['not', 'a', 'dict'])

    def test_module_level_convert_metadata_uses_packaged_model(self):
        converted = convert_metadata({'Make': 'Acme'})

        self.assertEqual(converted, {'Instrument': {'Manufacturer': 'Acme'},
                                     'SourceMap': {'Instrument.Manufacturer': 'Make'}})

    def test_aperio_svs_fields_map_to_image_and_instrument(self):
        # OriginalWidth/Height match the description's "28448x21839" header; Left/Top are mm on the slide,
        # the scan area's position, not crop edges
        svs = {'AppMag': 20, 'MPP': 0.4936, 'OriginalWidth': 28448, 'OriginalHeight': 21839,
               'ScanScope ID': 'SS1735', 'ImageID': 18489, 'Left': 29.282969, 'Top': 13.628824}

        converted = self.mapper.convert_metadata(svs)

        self.assertEqual(converted['Pixels'], {'PhysicalSizeX': 0.4936, 'PhysicalSizeY': 0.4936,
                                               'SizeX': 28448, 'SizeY': 21839})
        self.assertEqual(converted['Image'], {'ID': 18489})
        self.assertEqual(converted['Plane'], {'PositionX': 29.282969, 'PositionY': 13.628824,
                                              'PositionXUnit': 'mm', 'PositionYUnit': 'mm'})
        self.assertEqual(converted['Objective'], {'Magnification': 20})
        self.assertEqual(converted['Instrument'], {'ID': 'SS1735'})

    def test_huygens_sampling_sizes_map_to_pixels(self):
        # Checked against DNAcropSmall.ome.json, which carries both this annotation and the image's own OME Pixels
        annotation = {'Geometry': {'SamplingSizes': {'DeltaX': 0.064967, 'DeltaY': 0.064967, 'DeltaZ': 0.2128,
                                                     'DeltaT': 1.0}},
                      'ChannelData': [{'RefrIndexLensMedium': 1.518}]}

        converted = self.mapper.convert_metadata({'Annotation:CustomAttributes:SVI:Image:0': annotation})

        self.assertEqual(converted['Pixels'], {'PhysicalSizeX': 0.064967, 'PhysicalSizeY': 0.064967,
                                               'PhysicalSizeZ': 0.2128, 'TimeIncrement': 1.0})
        self.assertEqual(converted['ImmersionLiquid'], {'RefractiveIndex': 1.518})


class ModelDocumentTest(unittest.TestCase):
    """A source that is a document of the model itself, wrapped in its root (a full OME export)."""

    def test_rules_match_below_the_model_root(self):
        annotation = {'FeatureHistory': {'HuygensVersion': '23.10'}, 'Vendor': {'Setting': 'x'}}
        document = {'OME': {'Creator': 'Huygens', 'StructuredAnnotations': {'XMLAnnotation': {'Value': annotation}},
                            'Image': {'Name': 'cell'}}}

        converted = AcquisitionMetadataMapper().convert_metadata(document)

        # the rule for the annotation applies as if OME were absent; what no rule maps stays under OME
        self.assertEqual(converted['SoftwareModule'], {'Version': '23.10'})
        self.assertEqual(converted['OME']['Creator'], 'Huygens')
        self.assertEqual(converted['SourceMap']['SoftwareModule.Version'],
                         'OME.StructuredAnnotations.XMLAnnotation.Value.FeatureHistory.HuygensVersion')
        self.assertEqual(converted['Image'], {'Name': 'cell'})
        self.assertEqual(converted['OME']['StructuredAnnotations']['XMLAnnotation']['Value']['Vendor'],
                         {'Setting': 'x'})


class HuygensRulesAgreeWithOmeTest(unittest.TestCase):
    """examples/ome-tiff.json is a full OME export holding both the image's own OME values and Huygens' SVI
    annotation of it: what the Huygens rules take from the annotation must be what OME states."""

    ANNOTATION = 'StructuredAnnotations.XMLAnnotation.Value.'
    # the OME field (path in the OME document) each Huygens rule's value also stands in
    OME_COUNTERPARTS = {
        'Geometry.SamplingSizes.DeltaX': 'Image.Pixels.PhysicalSizeX',
        'Geometry.SamplingSizes.DeltaY': 'Image.Pixels.PhysicalSizeY',
        'Geometry.SamplingSizes.DeltaZ': 'Image.Pixels.PhysicalSizeZ',
        'Geometry.SamplingSizes.DeltaT': 'Image.Pixels.TimeIncrement',
        'ChannelData.RefrIndexLensMedium': 'Image.ObjectiveSettings.RefractiveIndex',
    }
    # per channel, and to the nanometre only: Huygens has 424.119995 where OME has 424
    OME_ROUNDED_COUNTERPARTS = {
        'ChannelData.LambdaEx': 'Image.Pixels.Channel.ExcitationWavelength',
        'ChannelData.LambdaEm': 'Image.Pixels.Channel.EmissionWavelength',
    }

    def test_huygens_values_are_the_images_own(self):
        with open(os.path.join(REPO_ROOT, 'examples', 'ome-tiff.json'), encoding='utf-8') as file:
            ome = json.load(file)['OME']
        with open(os.path.join(REPO_ROOT, DEFAULT_MAPPINGS_FILE), encoding='utf-8') as file:
            rules = [rule.removeprefix(self.ANNOTATION) for rule in json.load(file) if rule.startswith(self.ANNOTATION)]
        counterparts = {**self.OME_COUNTERPARTS, **self.OME_ROUNDED_COUNTERPARTS}
        checked = [rule for rule in rules if rule in counterparts]
        self.assertEqual(sorted(checked), sorted(counterparts))
        for rule in checked:
            with self.subTest(rule=rule):
                huygens = _values(ome['StructuredAnnotations']['XMLAnnotation']['Value'], rule.split('.'))
                own = _values(ome, counterparts[rule].split('.'))
                if rule in self.OME_ROUNDED_COUNTERPARTS:
                    self.assertEqual([round(value) for value in huygens], [round(value) for value in own])
                else:
                    self.assertEqual(set(huygens), set(own))


def _values(node, parts):
    """The values at `parts` below `node`, through every item of a list on the way."""
    if isinstance(node, list):
        return [value for item in node for value in _values(item, parts)]
    if not parts:
        return [node]
    return _values(node[parts[0]], parts[1:]) if isinstance(node, dict) and parts[0] in node else []


class RuleTargetsTest(unittest.TestCase):
    """Every rule targets the imaging model: a field, or a group a whole subtree moves into."""

    def test_every_target_is_in_the_model(self):
        tree = ModelPaths().tree()
        paths = set()

        def collect(node, path=''):
            for key, value in node.items():
                current = f'{path}.{key}' if path else key
                paths.add(current)
                if isinstance(value, dict):
                    collect(value, current)

        collect(tree)
        with open(os.path.join(REPO_ROOT, DEFAULT_MAPPINGS_FILE), encoding='utf-8') as file:
            mappings = json.load(file)
        with open(os.path.join(REPO_ROOT, DEFAULT_COMBINATIONS_FILE), encoding='utf-8') as file:
            combinations = json.load(file)
        targets = [target for rule in mappings.values() for target in rule_targets(rule)]
        # a combination turning its parts into their number in place (an Exif rational) targets its own key
        targets += [combination['target'] for combination in combinations
                    if not all(source.startswith(f"{combination['target']}[") for source in combination['sources'])]
        model = ModelPaths()
        # a per-item target (Pixels.Channel[*].Fluorophore...) runs through nested classes the tree lists apart
        # a field of each item a "Target[]" rule collapses (GenericDetector[].Name) is that class's field
        missing = [target for target in targets
                   if '[*]' not in target and target.removesuffix('[]').replace('[].', '.') not in paths]
        missing += [target for target in targets if '[*]' in target and not _nested_path(model, target)]
        self.assertEqual(missing, [])


def _nested_path(model, target):
    """Whether `target` (Class.slot[*].slot...) runs through nested slots of the model to a field."""
    first, *rest = target.replace('[*]', '').split('.')
    current = first if first in model.classes else None
    for position, name in enumerate(rest):
        slot = model.slots(current).get(name) if current else None
        is_last = position == len(rest) - 1
        current = slot.range if slot is not None and not is_last else None
        if slot is None or (not is_last and not (slot.inlined or slot.inlined_as_list)):
            return False
    return current is None and bool(rest)


class LosslessMappingTest(unittest.TestCase):
    """Collisions, empty values and collapsed keys must never drop metadata."""

    def mapper_for(self, mappings, combinations=(), schema=None):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        files = {}
        for name, content in (('schema', schema or {}), ('mappings', mappings), ('combinations', list(combinations))):
            files[name] = os.path.join(directory, f'{name}.json')
            with open(files[name], 'w', encoding='utf-8') as file:
                json.dump(content, file)
        return AcquisitionMetadataMapper(files['schema'], files['mappings'], files['combinations'])

    def test_rule_naming_several_targets_copies_the_value_to_each(self):
        mapper = self.mapper_for({'MPP': ['Pixels.PhysicalSizeX', 'Pixels.PhysicalSizeY']})

        converted = mapper.convert_metadata({'MPP': 0.5})

        self.assertEqual(converted, {'Pixels': {'PhysicalSizeX': 0.5, 'PhysicalSizeY': 0.5},
                                     'SourceMap': {'Pixels.PhysicalSizeX': 'MPP', 'Pixels.PhysicalSizeY': 'MPP'}})

    def test_copy_to_a_further_target_never_overwrites(self):
        mapper = self.mapper_for({'MPP': ['X', 'Y'], 'Height': 'Y'})

        converted = mapper.convert_metadata({'Height': 7, 'MPP': 0.5})

        self.assertEqual(converted, {'Y': 7, 'X': 0.5, 'SourceMap': {'Y': 'Height', 'X': 'MPP'}})

    def test_rule_can_name_one_item_of_a_value_list(self):
        mapper = self.mapper_for({'Spacing[0]': 'Pixels.PhysicalSizeY', 'Spacing[1]': 'Pixels.PhysicalSizeX'})

        converted = mapper.convert_metadata({'Spacing': [0.5, 0.25]})

        self.assertEqual(converted, {'Pixels': {'PhysicalSizeY': 0.5, 'PhysicalSizeX': 0.25},
                                     'SourceMap': {'Pixels.PhysicalSizeY': 'Spacing[0]',
                                                   'Pixels.PhysicalSizeX': 'Spacing[1]'}})

    def test_list_items_without_a_rule_stay_in_the_list(self):
        mapper = self.mapper_for({'Spacing[1]': 'X'})

        converted = mapper.convert_metadata({'Spacing': [1, 2, 3]})

        self.assertEqual(converted, {'X': 2, 'Spacing': [1, 3],
                                     'SourceMap': {'X': 'Spacing[1]', 'Spacing[0]': 'Spacing[0]',
                                                   'Spacing[1]': 'Spacing[2]'}})

    def test_list_item_whose_target_is_taken_stays_in_the_list(self):
        mapper = self.mapper_for({'Height': 'Y', 'Spacing[0]': 'Y'})

        converted = mapper.convert_metadata({'Height': 7, 'Spacing': [1, 2]})

        self.assertEqual(converted, {'Y': 7, 'Spacing': [1, 2],
                                     'SourceMap': {'Y': 'Height', 'Spacing[0]': 'Spacing[0]',
                                                   'Spacing[1]': 'Spacing[1]'}})

    def test_rule_with_a_unit_writes_the_unit_the_source_implies(self):
        mapper = self.mapper_for({'Thickness': {'target': 'Pixels.PhysicalSizeZ', 'unit': 'mm'},
                                  'WD': {'target': 'Beam.WorkingDistance.Value', 'unit': 'mm'}})

        converted = mapper.convert_metadata({'Thickness': 0.625, 'WD': 5})

        self.assertEqual(converted['Pixels'], {'PhysicalSizeZ': 0.625, 'PhysicalSizeZUnit': 'mm'})
        self.assertEqual(converted['Beam'], {'WorkingDistance': {'Value': 5, 'Unit': 'mm'}})
        # the unit is derived from the value it qualifies, as a combination is from its parts
        self.assertEqual(converted['SourceMap']['Pixels.PhysicalSizeZUnit'], ['Thickness'])

    def test_list_item_rule_with_a_unit(self):
        mapper = self.mapper_for({'Spacing[0]': {'target': 'Pixels.PhysicalSizeY', 'unit': 'mm'}})

        converted = mapper.convert_metadata({'Spacing': [0.5, 0.25]})

        self.assertEqual(converted['Pixels'], {'PhysicalSizeY': 0.5, 'PhysicalSizeYUnit': 'mm'})
        self.assertEqual(converted['SourceMap']['Pixels.PhysicalSizeYUnit'], ['Spacing[0]'])

    def test_rule_with_a_unit_for_each_item_of_a_list(self):
        mapper = self.mapper_for({'Lasers.Laser.Wavelength': {'target': 'Laser[*].Wavelength', 'unit': 'nm'}})

        converted = mapper.convert_metadata({'Lasers': {'Laser': [{'Wavelength': 405}, {'Wavelength': 488}]}})

        self.assertEqual(converted['Laser'], [{'Wavelength': 405, 'WavelengthUnit': 'nm'},
                                              {'Wavelength': 488, 'WavelengthUnit': 'nm'}])
        self.assertEqual(converted['SourceMap']['Laser[1].WavelengthUnit'], ['Lasers.Laser[1].Wavelength'])

    def test_implied_unit_qualifies_numbers_only(self):
        mapper = self.mapper_for({'FrameTime': {'target': 'Scan.FrameTime.Value', 'unit': 's'}})

        self.assertEqual(mapper.convert_metadata({'FrameTime': '424.55'})['Scan'],
                         {'FrameTime': {'Value': '424.55', 'Unit': 's'}})
        self.assertEqual(mapper.convert_metadata({'FrameTime': '2min52s'})['Scan'], {'FrameTime': {'Value': '2min52s'}})

    def test_implied_unit_never_overrides_a_stated_one(self):
        mapper = self.mapper_for({'Size': {'target': 'P.SizeX', 'unit': 'mm'}, 'SizeUnit': 'P.SizeXUnit'})

        for source in ({'Size': 3, 'SizeUnit': 'µm'}, {'SizeUnit': 'µm', 'Size': 3}):
            with self.subTest(order=list(source)):
                self.assertEqual(mapper.convert_metadata(source)['P'], {'SizeX': 3, 'SizeXUnit': 'µm'})

    def test_implied_unit_is_left_out_when_the_value_misses_its_target(self):
        mapper = self.mapper_for({'Height': 'Y', 'Size': {'target': 'Y', 'unit': 'mm'}})

        converted = mapper.convert_metadata({'Height': 7, 'Size': 3})

        self.assertEqual(converted, {'Y': 7, 'Size': 3, 'SourceMap': {'Y': 'Height', 'Size': 'Size'}})

    def test_rule_targets_of_a_rule_with_a_unit(self):
        self.assertEqual(rule_targets({'target': 'Pixels.PhysicalSizeZ', 'unit': 'mm'}), ['Pixels.PhysicalSizeZ'])

    def test_packaged_units_go_to_model_unit_fields(self):
        model = ModelPaths()
        model_fields = set(model.aliases()) | {path for name, subtree in model.tree().items()
                                               for path in _leaf_paths(subtree, name)}
        with open(DEFAULT_MAPPINGS_FILE, encoding='utf-8') as file:
            rules = json.load(file)
        for source, rule in rules.items():
            if isinstance(rule, dict):
                with self.subTest(source=source):
                    target = re.sub(r'\[\*?\]', '', rule['target'])
                    self.assertIn(target, model_fields)
                    self.assertIn(unit_field(target), model_fields)

    def test_rule_names_a_field_of_each_collapsed_item(self):
        mapper = self.mapper_for({'Detectors.*': 'GenericDetector[]',
                                  'Detectors.*.DetectorName': 'GenericDetector[].Name',
                                  'Detectors.*.Binning.width': 'GenericDetector[].Binning.X',
                                  'Detectors.*.Binning.height': 'GenericDetector[].Binning.Y'})

        converted = mapper.convert_metadata({'Detectors': {
            'Detector-0': {'DetectorName': 'Ceta', 'Binning': {'width': 1, 'height': 2}, 'Mode': 'x'},
            'Detector-1': {'DetectorName': 'HAADF'}}})

        self.assertEqual(converted['GenericDetector'], [
            {'Name': 'Ceta', 'Binning': {'X': 1, 'Y': 2}, 'Mode': 'x', 'id': 'Detector-0'},
            {'Name': 'HAADF', 'id': 'Detector-1'}])
        self.assertEqual(converted['SourceMap']['GenericDetector[0].Binning.X'], 'Detectors.Detector-0.Binning.width')
        self.assertEqual(converted['SourceMap']['GenericDetector[1].Name'], 'Detectors.Detector-1.DetectorName')
        self.assertNotIn('GenericDetector[0].DetectorName', converted['SourceMap'])

    def test_rule_names_the_label_of_each_collapsed_item(self):
        mapper = self.mapper_for({'detectors.*': 'D[]', 'detectors.*.id': 'D[].Name'})

        converted = mapper.convert_metadata({'detectors': {'QBSD': {'gain': 45}}})

        self.assertEqual(converted['D'], [{'gain': 45, 'Name': 'QBSD'}])
        self.assertEqual(converted['SourceMap']['D[0].Name'], 'detectors.QBSD')

    def test_collapsed_item_field_with_a_unit(self):
        mapper = self.mapper_for({'Detectors.*': 'D[]',
                                  'Detectors.*.ExposureTime': {'target': 'D[].ExposureTime.Value', 'unit': 's'}})

        converted = mapper.convert_metadata({'Detectors': {'A': {'ExposureTime': 0.5}}})

        self.assertEqual(converted['D'], [{'ExposureTime': {'Value': 0.5, 'Unit': 's'}, 'id': 'A'}])
        self.assertEqual(converted['SourceMap']['D[0].ExposureTime.Unit'], ['Detectors.A.ExposureTime'])

    def test_collapsed_item_field_keeps_its_name_where_the_model_name_is_taken(self):
        mapper = self.mapper_for({'Detectors.*': 'D[]', 'Detectors.*.label': 'D[].Name'})

        converted = mapper.convert_metadata({'Detectors': {'A': {'Name': 'kept', 'label': 'other'}}})

        self.assertEqual(converted['D'], [{'Name': 'kept', 'label': 'other', 'id': 'A'}])

    def test_several_targets_for_a_group_are_refused(self):
        mapper = self.mapper_for({'Beam': ['A', 'B']})

        with self.assertRaises(ValueError):
            mapper.convert_metadata({'Beam': {'WD': 1}})

    def test_combination_adds_an_iso_timestamp_in_place_of_its_parts(self):
        mapper = self.mapper_for({}, [{'target': 'Image.AcquisitionDate', 'sources': ['Date', 'Time', 'Time Zone'],
                                       'format': '%m/%d/%y %H:%M:%S GMT%z'}])

        converted = mapper.convert_metadata({'Date': '10/19/15', 'Time': '17:18:12', 'Time Zone': 'GMT-05:00'})

        self.assertEqual(converted['Image'], {'AcquisitionDate': '2015-10-19T17:18:12-05:00'})
        self.assertEqual(converted['SourceMap'], {'Image.AcquisitionDate': ['Date', 'Time', 'Time Zone']})
        self.assertEqual(set(converted), {'Image', 'SourceMap'})

    def test_combination_is_left_out_when_a_part_is_missing_or_does_not_parse(self):
        mapper = self.mapper_for({}, [{'target': 'D', 'sources': ['Date', 'Time'], 'format': '%m/%d/%y %H:%M:%S'}])

        self.assertNotIn('D', mapper.convert_metadata({'Date': '10/19/15'}))
        self.assertNotIn('D', mapper.convert_metadata({'Date': '10/19/15', 'Time': 'noon'}))

    def test_split_combination_takes_one_number_of_a_spaced_value(self):
        source = 'View.size'
        mapper = self.mapper_for({}, [{'target': f'Pixels.Size{axis}', 'sources': [source], 'format': 'split',
                                       'item': index} for index, axis in enumerate('XYZ')]
                                 + [{'target': 'Pixels.PhysicalSizeX', 'sources': ['View.voxel'], 'format': 'split',
                                     'item': 0}])

        converted = mapper.convert_metadata({'View': {'size': '1100 1100 1150', 'voxel': '0.325 0.325 0.325'}})

        self.assertEqual(converted['Pixels'], {'SizeX': 1100, 'SizeY': 1100, 'SizeZ': 1150, 'PhysicalSizeX': 0.325})
        self.assertNotIn('View', converted)
        self.assertEqual(converted['SourceMap']['Pixels.SizeZ'], [source])

    def test_count_combination_gives_the_number_of_a_range(self):
        mapper = self.mapper_for({}, [{'target': 'Pixels.SizeT', 'sources': ['Time.first', 'Time.last'],
                                       'format': 'count'}])

        converted = mapper.convert_metadata({'Time': {'first': 0, 'last': 4}})

        self.assertEqual(converted['Pixels'], {'SizeT': 5})
        self.assertEqual(converted['SourceMap']['Pixels.SizeT'], ['Time.first', 'Time.last'])

    def test_duration_combination_replaces_the_text_its_rule_placed(self):
        mapper = self.mapper_for({'FrameTime': 'Scan.FrameTime.Value'},
                                 [{'target': 'Scan.FrameTime.Value', 'sources': ['FrameTime'], 'format': 'duration'}])

        converted = mapper.convert_metadata({'FrameTime': '2min52s'})

        self.assertEqual(converted['Scan'], {'FrameTime': {'Value': 172, 'Unit': 's'}})
        # the raw text goes, the derived value names it
        self.assertNotIn('FrameTime', converted)
        self.assertNotIn('FrameTime', converted['SourceMap'])
        self.assertEqual(converted['SourceMap']['Scan.FrameTime.Value'], ['FrameTime'])
        self.assertEqual(converted['SourceMap']['Scan.FrameTime.Unit'], ['FrameTime'])

    def test_derived_value_leaves_a_number_its_rule_placed(self):
        mapper = self.mapper_for({'FrameTime': 'Scan.FrameTime.Value'},
                                 [{'target': 'Scan.FrameTime.Value', 'sources': ['FrameTime'], 'format': 'duration'}])

        converted = mapper.convert_metadata({'FrameTime': '424.55'})

        self.assertEqual(converted['Scan'], {'FrameTime': {'Value': '424.55'}})
        self.assertEqual(converted['SourceMap']['Scan.FrameTime.Value'], 'FrameTime')

    def test_quantity_combination_splits_a_number_from_its_unit(self):
        mapper = self.mapper_for({'HFW': 'Scan.FieldOfView.X.Value'},
                                 [{'target': 'Scan.FieldOfView.X.Value', 'sources': ['HFW'], 'format': 'quantity'}])

        converted = mapper.convert_metadata({'HFW': '21.12µm'})

        self.assertEqual(converted['Scan'], {'FieldOfView': {'X': {'Value': 21.12, 'Unit': 'µm'}}})

    def test_product_combination_multiplies_its_parts_and_states_its_unit(self):
        mapper = self.mapper_for({}, [{'target': 'Plane.ExposureTime', 'sources': ['Exposure Time', 'Exposure Scale'],
                                       'format': 'product', 'unit': 's'}])

        converted = mapper.convert_metadata({'Exposure Time': 109, 'Exposure Scale': 1e-06})

        self.assertEqual(converted['Plane']['ExposureTimeUnit'], 's')
        self.assertAlmostEqual(converted['Plane']['ExposureTime'], 1.09e-04)
        self.assertEqual(converted['SourceMap']['Plane.ExposureTimeUnit'], ['Exposure Time', 'Exposure Scale'])
        self.assertNotIn('Plane', mapper.convert_metadata({'Exposure Time': 109, 'Exposure Scale': 'n/a'}))

    def test_ratio_combination_replaces_the_list_the_schema_placed(self):
        mapper = self.mapper_for({}, [{'target': 'Plane.ExposureTime', 'sources': ['ExposureTime[0]', 'ExposureTime[1]'],
                                       'format': 'ratio', 'unit': 's'}])

        converted = mapper.convert_metadata({'ExposureTime': [41, 5000]})

        self.assertEqual(converted, {'Plane': {'ExposureTime': 0.0082, 'ExposureTimeUnit': 's'}, 'SourceMap': {
            'Plane.ExposureTime': ['ExposureTime[0]', 'ExposureTime[1]'],
            'Plane.ExposureTimeUnit': ['ExposureTime[0]', 'ExposureTime[1]']}})

    def test_tuple_converts_as_the_list_json_would_give(self):
        mapper = self.mapper_for({'Spacing[0]': 'Pixels.PhysicalSizeY'},
                                 [{'target': 'Plane.ExposureTime', 'sources': ['ExposureTime[0]', 'ExposureTime[1]'],
                                   'format': 'ratio', 'unit': 's'}])
        metadata = {'ExposureTime': (41, 5000), 'Spacing': (0.5, 0.25), 'Nested': {'Pairs': [(1, 2)]}}

        converted = mapper.convert_metadata(metadata)

        self.assertEqual(converted, mapper.convert_metadata(json.loads(json.dumps(metadata))))
        self.assertEqual(converted['Plane'], {'ExposureTime': 0.0082, 'ExposureTimeUnit': 's'})
        self.assertNotIn('ExposureTime', converted)

    def test_ratio_combination_turns_a_rational_into_its_number_in_place(self):
        mapper = self.mapper_for({}, [{'target': 'FNumber', 'sources': ['FNumber[0]', 'FNumber[1]'],
                                       'format': 'ratio'}])

        converted = mapper.convert_metadata({'FNumber': (28, 10)})

        self.assertEqual(converted, {'FNumber': 2.8, 'SourceMap': {'FNumber': ['FNumber[0]', 'FNumber[1]']}})

    def test_part_stays_where_a_combination_naming_it_writes_nothing(self):
        mapper = self.mapper_for({'Stamp': 'D'}, [{'target': 'E', 'sources': ['Date'], 'format': '%m/%d/%y'},
                                                  {'target': 'D', 'sources': ['Date'], 'format': '%m/%d/%y'}])

        converted = mapper.convert_metadata({'Stamp': 'kept', 'Date': '10/19/15'})

        self.assertEqual(converted['Date'], '10/19/15')
        self.assertEqual(converted['E'], '2015-10-19T00:00:00')

    def test_count_keeps_its_parts(self):
        mapper = self.mapper_for({}, [{'target': 'Pixels.SizeT', 'sources': ['Time.first', 'Time.last'],
                                       'format': 'count'}])

        self.assertEqual(mapper.convert_metadata({'Time': {'first': 3, 'last': 4}})['Time'], {'first': 3, 'last': 4})

    def test_part_a_rule_placed_in_a_model_field_stays(self):
        mapper = self.mapper_for({'Date': 'Image.Date', 'User.*': 'Experimenter'},
                                 [{'target': 'D', 'sources': ['Date'], 'format': '%m/%d/%y'},
                                  {'target': 'E', 'sources': ['User.TimeStamp'], 'format': 'unix'}],
                                 schema={'Image': {'Date': 'string'}, 'Experimenter': {'UserName': 'string'}})

        converted = mapper.convert_metadata({'Date': '10/19/15', 'User': {'TimeStamp': 1683922216, 'Name': 'x'}})

        self.assertEqual(converted['Image'], {'Date': '10/19/15'})
        self.assertEqual(converted['D'], '2015-10-19T00:00:00')
        # a rule moving a part to no model field only renamed it: the derived value holds it
        self.assertEqual(converted['Experimenter'], {'Name': 'x'})

    def test_ratio_combination_is_left_out_without_a_divisor(self):
        mapper = self.mapper_for({}, [{'target': 'R', 'sources': ['Q[0]', 'Q[1]'], 'format': 'ratio'}])

        self.assertNotIn('R', mapper.convert_metadata({'Q': [41, 0]}))
        self.assertNotIn('R', mapper.convert_metadata({'Q': [41]}))

    def test_combination_gives_way_to_the_value_a_rule_placed(self):
        mapper = self.mapper_for({'datetime': 'Image.AcquisitionDate'},
                                 [{'target': 'Image.AcquisitionDate', 'sources': ['DateTimeDigitized'],
                                   'format': '%Y:%m:%d %H:%M:%S'}])

        converted = mapper.convert_metadata({'DateTimeDigitized': '2025:05:28 10:54:29',
                                             'Vendor': {'datetime': '2025-05-28 10:54:00'}})

        self.assertEqual(converted['Image'], {'AcquisitionDate': '2025-05-28 10:54:00'})
        self.assertEqual(converted['DateTimeDigitized'], '2025:05:28 10:54:29')
        self.assertEqual(mapper.convert_metadata({'DateTimeDigitized': '2025:05:28 10:54:29'})['Image'],
                         {'AcquisitionDate': '2025-05-28T10:54:29'})

    def test_duration_and_quantity_are_left_out_without_one(self):
        mapper = self.mapper_for({}, [{'target': 'D', 'sources': ['time'], 'format': 'duration'},
                                      {'target': 'Q', 'sources': ['size'], 'format': 'quantity'}])

        converted = mapper.convert_metadata({'time': 'long', 'size': 'µm'})

        self.assertNotIn('D', converted)
        self.assertNotIn('Q', converted)

    def test_split_combination_is_left_out_without_a_number_there(self):
        mapper = self.mapper_for({}, [{'target': 'N', 'sources': ['size'], 'format': 'split', 'item': 2}])

        self.assertNotIn('N', mapper.convert_metadata({'size': '1100 1100'}))
        self.assertNotIn('N', mapper.convert_metadata({'size': '1100 1100 large'}))

    def test_combination_never_overwrites(self):
        mapper = self.mapper_for({'Stamp': 'D'}, [{'target': 'D', 'sources': ['Date', 'Time'],
                                                   'format': '%m/%d/%y %H:%M:%S'}])

        converted = mapper.convert_metadata({'Stamp': 'kept', 'Date': '10/19/15', 'Time': '17:18:12'})

        self.assertEqual(converted['D'], 'kept')

    def test_colliding_value_falls_back_to_its_source_path(self):
        mapper = self.mapper_for({'a': 'T', 'b': 'T'})

        converted = mapper.convert_metadata({'a': 1, 'b': 2})

        self.assertEqual(converted, {'T': 1, 'b': 2, 'SourceMap': {'T': 'a', 'b': 'b'}})

    def test_value_below_a_scalar_falls_back_to_its_source_path(self):
        mapper = self.mapper_for({'a': 'T', 'b': 'T.X'})

        converted = mapper.convert_metadata({'a': 1, 'b': 2})

        self.assertEqual(converted, {'T': 1, 'b': 2, 'SourceMap': {'T': 'a', 'b': 'b'}})

    def test_refuses_to_overwrite_when_fallback_is_taken_too(self):
        mapper = self.mapper_for({'a': 'b'})

        with self.assertRaises(ValueError):
            mapper.convert_metadata({'a': 1, 'b': 2})

    def test_empty_containers_are_kept(self):
        converted = self.mapper_for({}).convert_metadata({'a': {}, 'b': [], 'c': None})

        self.assertEqual(converted, {'a': {}, 'b': [], 'c': None,
                                     'SourceMap': {'a': 'a', 'b': 'b', 'c': 'c'}})

    def test_numeric_collapsed_key_is_kept(self):
        mapper = self.mapper_for({'Detectors.*': 'D[]'})

        converted = mapper.convert_metadata({'Detectors': {'3': {'gain': 1}}})

        self.assertEqual(converted['D'], [{'gain': 1, 'id': '3'}])
        self.assertEqual(converted['SourceMap']['D[0].id'], 'Detectors.3')

    def test_collapsed_key_is_kept_beside_an_existing_id(self):
        mapper = self.mapper_for({'Detectors.*': 'D[]'})

        converted = mapper.convert_metadata({'Detectors': {'QBSD': {'id': 7, 'ID': 8}}})

        self.assertEqual(converted['D'], [{'id': 7, 'ID': 8, 'SourceKey': 'QBSD'}])

    def test_whole_path_wildcard_key_is_kept(self):
        mapper = self.mapper_for({'Image:*': 'Images[]'})

        converted = mapper.convert_metadata({'Image:0': {'x': 1}})

        self.assertEqual(converted['Images'], [{'x': 1, 'SourceKey': 'Image:0'}])
        self.assertEqual(converted['SourceMap'], {'Images[0].x': 'Image:0.x', 'Images[0].SourceKey': 'Image:0'})

    def test_rule_inside_a_list_item_writes_from_the_root(self):
        mapper = self.mapper_for({'Image:*': 'Images[]', 'Image:*.History.Version': 'Software.Version'})

        converted = mapper.convert_metadata({'Image:0': {'History': {'Version': '1.0', 'Count': 5}}})

        self.assertEqual(converted['Software'], {'Version': '1.0'})
        self.assertEqual(converted['Images'], [{'History': {'Count': 5}, 'SourceKey': 'Image:0'}])
        self.assertEqual(converted['SourceMap']['Software.Version'], 'Image:0.History.Version')

    def test_rule_in_each_list_item_falls_back_into_the_item_on_collision(self):
        mapper = self.mapper_for({'Channels.Refr': 'Medium.RefractiveIndex'})

        converted = mapper.convert_metadata({'Channels': [{'Refr': 1.4}, {'Refr': 1.5}]})

        self.assertEqual(converted['Medium'], {'RefractiveIndex': 1.4})
        self.assertEqual(converted['Channels'], [{}, {'Refr': 1.5}])
        self.assertEqual(converted['SourceMap'], {'Medium.RefractiveIndex': 'Channels[0].Refr',
                                                  'Channels[1].Refr': 'Channels[1].Refr'})

    def test_vendor_wrapper_is_left_out_of_rule_paths_only(self):
        mapper = self.mapper_for({'Make': 'Instrument.Manufacturer'})

        converted = mapper.convert_metadata({'FEI_TITAN': {'Make': 'Acme', 'databarHeight': 0}})

        self.assertEqual(converted, {'Instrument': {'Manufacturer': 'Acme'}, 'FEI_TITAN': {'databarHeight': 0},
                                     'SourceMap': {'Instrument.Manufacturer': 'FEI_TITAN.Make',
                                                   'FEI_TITAN.databarHeight': 'FEI_TITAN.databarHeight'}})

    def test_two_level_vendor_wrapper_is_left_out_of_rule_paths_only(self):
        mapper = self.mapper_for({'Make': 'Instrument.Manufacturer'})

        converted = mapper.convert_metadata({'FEI_TITAN': {'FeiImage': {'Make': 'Acme', 'databarHeight': 0}}})

        self.assertEqual(converted, {'Instrument': {'Manufacturer': 'Acme'},
                                     'FEI_TITAN': {'FeiImage': {'databarHeight': 0}},
                                     'SourceMap': {'Instrument.Manufacturer': 'FEI_TITAN.FeiImage.Make',
                                                   'FEI_TITAN.FeiImage.databarHeight':
                                                       'FEI_TITAN.FeiImage.databarHeight'}})

    def test_wrapper_level_holding_several_keys_ends_the_wrapper(self):
        # below FibicsXML.Fibics the keys are the vendor's own groups; the rules match from there
        mapper = self.mapper_for({'Scan.Focus': 'OME.ElectronBeam.Focus'})

        converted = mapper.convert_metadata({'FibicsXML': {'Fibics': {'Scan': {'Focus': 2.5}, 'version': 1}}})

        self.assertEqual(converted['OME'], {'ElectronBeam': {'Focus': 2.5}})
        self.assertEqual(converted['FibicsXML'], {'Fibics': {'version': 1}})
        self.assertEqual(converted['SourceMap']['OME.ElectronBeam.Focus'], 'FibicsXML.Fibics.Scan.Focus')

    def test_list_item_value_goes_to_its_own_item_with_star_index(self):
        mapper = self.mapper_for({'Data.Lambda': 'Pixels.Channel[*].Fluorophore.ExcitationWavelength'})

        converted = mapper.convert_metadata({'Data': [{'Lambda': 400, 'Other': 1}, {'Lambda': 500}]})

        self.assertEqual(converted['Pixels'], {'Channel': [{'Fluorophore': {'ExcitationWavelength': 400}},
                                                           {'Fluorophore': {'ExcitationWavelength': 500}}]})
        self.assertEqual(converted['SourceMap']['Pixels.Channel[1].Fluorophore.ExcitationWavelength'], 'Data[1].Lambda')
        self.assertEqual(converted['Data'][0], {'Other': 1})

    def test_star_index_target_taken_keeps_the_value_in_its_item(self):
        mapper = self.mapper_for({'Data.Lambda': 'Pixels.Channel[*].Wavelength', 'Own': 'Pixels.Channel[*].Wavelength'})

        converted = mapper.convert_metadata({'Pixels': {'Channel': [{'Wavelength': 424}]},
                                             'Data': [{'Lambda': 424.12}, {'Lambda': 488}]})

        self.assertEqual(converted['Pixels']['Channel'], [{'Wavelength': 424}, {'Wavelength': 488}])
        self.assertEqual(converted['Data'][0], {'Lambda': 424.12})

    def test_unix_timestamp_becomes_an_iso_datetime_and_zero_is_unset(self):
        combinations = [{'target': 'Image.AcquisitionDate', 'sources': ['Acquired.DateTime'], 'format': 'unix'},
                        {'target': 'Image.AcquisitionDate', 'sources': ['Started.DateTime'], 'format': 'unix'}]
        mapper = self.mapper_for({}, combinations)

        converted = mapper.convert_metadata({'Acquired': {'DateTime': '0'}, 'Started': {'DateTime': '1683922216'}})

        # "0" is TALOS's unset time: the second timestamp fills the date and goes, the unset one stays
        self.assertEqual(converted['Image'], {'AcquisitionDate': '2023-05-12T20:10:16+00:00'})
        self.assertEqual(converted['SourceMap']['Image.AcquisitionDate'], ['Started.DateTime'])
        self.assertEqual(converted['Acquired'], {'DateTime': '0'})
        self.assertNotIn('Started', converted)

    def test_wrapped_value_colliding_with_a_top_level_one_is_kept(self):
        mapper = self.mapper_for({'DateTime': 'Image.AcquisitionDate', 'datetime': 'Image.AcquisitionDate'})

        converted = mapper.convert_metadata({'DateTime': '10:54:29', 'OlympusSIS': {'datetime': '10:54:00'}})

        self.assertEqual(converted['Image'], {'AcquisitionDate': '10:54:29'})
        self.assertEqual(converted['OlympusSIS'], {'datetime': '10:54:00'})

    def test_key_named_by_a_rule_is_not_a_wrapper(self):
        mapper = self.mapper_for({'Make': 'Instrument.Manufacturer', 'Tag.Make': 'Other.Make'})

        converted = mapper.convert_metadata({'Tag': {'Make': 'Acme'}})

        self.assertEqual(converted['Other'], {'Make': 'Acme'})

    def test_key_whose_contents_resolve_no_better_is_not_a_wrapper(self):
        mapper = self.mapper_for({'Make': 'Instrument.Manufacturer'})

        converted = mapper.convert_metadata({'Blob': {'odd': 1}})

        self.assertEqual(converted, {'Blob': {'odd': 1}, 'SourceMap': {'Blob.odd': 'Blob.odd'}})

    def test_list_target_taken_by_a_value_falls_back_to_the_source_path(self):
        mapper = self.mapper_for({'Name': 'D', 'Detectors.*': 'D[]'})

        converted = mapper.convert_metadata({'Name': 'x', 'Detectors': {'QBSD': {'gain': 1}}})

        self.assertEqual(converted['D'], 'x')
        self.assertEqual(converted['Detectors'], {'QBSD': {'gain': 1, 'id': 'QBSD'}})
        self.assertEqual(converted['SourceMap']['Detectors.QBSD.gain'], 'Detectors.QBSD.gain')


if __name__ == '__main__':
    unittest.main()
