import os
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from metaseed_generator import DEFAULT_PROFILE_FILE as PROFILE_FILE, MetaseedGenerator
from imaging_metadata_converter.ModelPaths import DEFAULT_MODEL_FILE as MODEL_FILE

# The LiMi XSD references a LightSensor (LightSensorRef) but no element contains one.
UNREACHABLE = {'LightSensor'}


SYNTHETIC_MODEL = """
id: https://example.org/synthetic
name: synthetic
version: 1.2.3
prefixes: {linkml: https://w3id.org/linkml/}
imports: [linkml:types]
default_range: string
types:
  LSID: {typeof: string, pattern: '\\S+:\\S+'}
  LightSourceID: {typeof: LSID}
  UUID: {typeof: uri, pattern: 'urn:uuid:\S+'}
enums:
  Medium: {permissible_values: {Cu: {}, Ar: {}}}
  Role: {permissible_values: {Transmitted: {}, Fluorescence: {}}}
slots:
  ObjectType: {range: string, designates_type: true}
classes:
  Instrument:
    tree_root: true
    attributes:
      ID: {identifier: true, range: LSID}
      UUID: {range: UUID}
      Website: {range: uri}
      LightSource: {range: LightSource, multivalued: true, inlined_as_list: true, required: true}
      Range: {range: WavelengthRange, multivalued: true, inlined_as_list: true}
      Sensor: {range: Sensor, inlined: false}
      Label: {range: Label, inlined: true}
      Shutter: {range: Shutter, multivalued: true, inlined_as_list: true}
      Lamp: {range: Lamp, multivalued: true, inlined_as_list: true}
      Marker: {range: Marker, multivalued: true, inlined_as_list: true}
  Sensor:
    attributes:
      ID: {identifier: true}
  Shutter:
    annotations: {Tier: '2'}
    attributes:
      ID: {identifier: true, required: true, annotations: {Tier: '1'}}
      Speed: {range: float, required: true, annotations: {Tier: '1'}}
  Marker:
    attributes:
      Sensor: {range: Sensor, inlined: false, required: true}
      Name: {required: true, annotations: {Tier: '2'}}
  Lamp:
    annotations: {Tier: '1'}
    attributes:
      ID: {identifier: true, required: true, annotations: {Tier: '1'}}
      Colour: {required: true, annotations: {Tier: '3'}}
      Serial: {required: true}
  Label:
    attributes:
      Text: {range: string}
  LightSource:
    abstract: true
    slots: [ObjectType]
    attributes:
      ID: {identifier: true, range: LightSourceID}
      Power: {range: float, minimum_value: 0}
      PowerUnit: {range: string, ifabsent: string(mW)}
      Role: {range: Role, multivalued: true}
  Laser:
    is_a: LightSource
    attributes:
      Medium: {range: Medium}
      Pump: {range: Laser, inlined: false}
  Filament:
    is_a: LightSource
  WavelengthRange:
    attributes:
      CutIn: {range: float}
  IlluminationWavelengthRange:
    is_a: WavelengthRange
"""


class MetaseedGeneratorTest(unittest.TestCase):
    """The LinkML-to-metaseed rules, on a minimal synthetic model."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            model = os.path.join(folder, 'synthetic.yaml')
            with open(model, 'w', encoding='utf-8') as file:
                file.write(SYNTHETIC_MODEL)
            cls.profile = MetaseedGenerator(model).generate()
        cls.entities = cls.profile['entities']
        cls.fields = {name: {field['name']: field for field in entity['fields']} for name, entity in cls.entities.items()}

    def test_header(self):
        self.assertEqual((self.profile['name'], self.profile['version'], self.profile['root_entity']),
                         ('synthetic', '1.2', 'Instrument'))

    def test_abstract_class_is_one_field_per_subtype(self):
        instrument = self.fields['Instrument']
        self.assertEqual((instrument['Laser']['items'], instrument['Filament']['items']), ('Laser', 'Filament'))
        self.assertNotIn('LightSource', instrument)
        self.assertNotIn('LightSource', self.entities)
        self.assertFalse(instrument['Laser']['required'])

    def test_inherited_slots_written_out(self):
        self.assertEqual(set(self.fields['Laser']), {'ID', 'Power', 'PowerUnit', 'Role', 'Medium', 'Pump'})
        self.assertEqual(set(self.fields['Filament']), {'ID', 'Power', 'PowerUnit', 'Role'})

    def test_concrete_range_is_not_expanded(self):
        self.assertEqual(self.fields['Instrument']['Range']['items'], 'WavelengthRange')
        self.assertNotIn('IlluminationWavelengthRange', self.entities)

    def test_uri_with_a_pattern_is_a_string(self):
        uuid = self.fields['Instrument']['UUID']
        self.assertEqual((uuid['type'], uuid['constraints']), ('string', {'pattern': r'urn:uuid:\S+'}))
        self.assertEqual(self.fields['Instrument']['Website']['type'], 'uri')

    def test_reference_is_an_id_string(self):
        pump = self.fields['Laser']['Pump']
        self.assertEqual((pump['type'], pump['reference']), ('string', 'Laser.ID'))

    def test_constraints_from_types_enums_and_slots(self):
        self.assertEqual(self.fields['Laser']['ID']['constraints'], {'pattern': '\\S+:\\S+'})
        self.assertTrue(self.fields['Laser']['ID']['is_identifier'])
        self.assertEqual(self.fields['Laser']['Medium']['constraints'], {'enum': ['Cu', 'Ar']})
        self.assertEqual(self.fields['Laser']['Power']['constraints'], {'minimum': 0})
        role = self.fields['Laser']['Role']
        self.assertEqual((role['type'], role['items'], role['constraints']),
                         ('list', 'string', {'enum': ['Transmitted', 'Fluorescence']}))
        self.assertEqual(self.fields['Laser']['PowerUnit']['example'], 'mW')
        self.assertNotIn('ObjectType', self.fields['Laser'])


    def test_reference_to_a_class_no_entity_holds_is_a_plain_string(self):
        sensor = self.fields['Instrument']['Sensor']
        self.assertEqual(sensor['type'], 'string')
        self.assertNotIn('reference', sensor)
        self.assertNotIn('Sensor', self.entities)

    def test_identifier_added_where_metaseed_would_take_free_text(self):
        self.assertEqual(list(self.fields['Label']), ['ID', 'Text'])
        self.assertTrue(self.fields['Label']['ID']['is_identifier'])
        self.assertNotIn('ID', self.fields['WavelengthRange'])


    def test_limi_tier_decides_tier_and_required(self):
        # the higher tier of field and class; the XSD's "required" holds only at tier 1
        self.assertEqual((self.fields['Lamp']['ID']['tier'], self.fields['Lamp']['ID']['required']), ('required', True))
        self.assertEqual((self.fields['Lamp']['Colour']['tier'], self.fields['Lamp']['Colour']['required']),
                         ('optional', False))
        self.assertEqual((self.fields['Shutter']['Speed']['tier'], self.fields['Shutter']['Speed']['required']),
                         ('recommended', False))
        # a field without a tier of its own takes its class's
        self.assertEqual((self.fields['Lamp']['Serial']['tier'], self.fields['Lamp']['Serial']['required']),
                         ('required', True))
        self.assertNotIn('tier', self.fields['Label']['Text'])


    def test_identifier_kept_when_a_tier_relaxes_it(self):
        # metaseed keys Marker by its first field that is no reference, Name; the tier makes Name optional, so
        # the generator declares it rather than adding an ID, which would re-key existing datasets
        self.assertEqual([field['name'] for field in self.entities['Marker']['fields']], ['Sensor', 'Name'])
        self.assertTrue(self.fields['Marker']['Name']['is_identifier'])
        self.assertFalse(self.fields['Marker']['Name']['required'])
        self.assertNotIn('is_identifier', self.fields['Marker']['Sensor'])


class GeneratedProfileTest(unittest.TestCase):
    """models/imaging.metaseed.yaml, generated from the master model."""

    @classmethod
    def setUpClass(cls):
        cls.generator = MetaseedGenerator(MODEL_FILE)
        cls.profile = cls.generator.generate()
        cls.entities = cls.profile['entities']

    def test_committed_profile_up_to_date(self):
        with open(PROFILE_FILE, encoding='utf-8') as file:
            committed = yaml.safe_load(file)
        self.assertEqual(committed, self.profile, 'rerun `python scripts/metaseed_generator.py`')

    def test_every_concrete_class_reachable(self):
        concrete = {name for name, cls in self.generator.classes.items() if not cls.abstract and not cls.mixin}
        self.assertEqual(concrete - set(self.entities), UNREACHABLE)


if __name__ == '__main__':
    unittest.main()
