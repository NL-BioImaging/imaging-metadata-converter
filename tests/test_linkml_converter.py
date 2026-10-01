import json
import os
import sys
import tempfile
import unittest

import yaml
from linkml_runtime.utils.schemaview import SchemaView

try:
    from linkml.linter.linter import Linter
    from linkml.validator import validate
except ImportError:
    Linter = None

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from linkml_converter import (DEFAULT_LINKML_FILE as MODEL_FILE, DEFAULT_OME_XSD_FILE as OME_XSD_FILE,
                              DEFAULT_XSD_FILE as XSD_FILE, OME_SOURCE, SCHEMA_NAME, UNITS_SCHEMA_NAME,
                              LinkmlConverter, write_schema)


JSON_SCHEMA_FILE = os.path.join(REPO_ROOT, 'reference', 'fullSchema.json')

# fullSchema.json content the model holds differently, not as a slot of the same name
JSON_ONLY = {
    ('Image', 'InstrumentName'): 'readonly display of the referenced Instrument',
    ('Image', 'InstrumentID'): 'readonly; the Image.Instrument reference holds the ID',
    ('Pump', None): 'the XSD Pump element is a LaserRef: the Laser.Pump reference',
}

SYNTHETIC_XSD = """<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" version="1.0">
  <xs:element name="OME">
    <xs:complexType><xs:sequence>
      <xs:element ref="Instrument" maxOccurs="unbounded"/>
    </xs:sequence></xs:complexType>
  </xs:element>
  <xs:element name="Instrument">
    <xs:complexType>
      <xs:sequence>
        <xs:element ref="LightSourceGroup" maxOccurs="unbounded"/>
        <xs:element ref="LightSourceSettings" minOccurs="0"/>
        <xs:element ref="Description" minOccurs="0"/>
      </xs:sequence>
      <xs:attribute name="ID" type="InstrumentID" use="required"/>
    </xs:complexType>
  </xs:element>
  <xs:element name="LightSourceGroup" abstract="true" type="LightSource"/>
  <xs:complexType name="LightSource">
    <xs:sequence><xs:element ref="WavelengthRange" minOccurs="0" maxOccurs="unbounded"/></xs:sequence>
    <xs:attribute name="ID" type="LightSourceID" use="required"/>
    <xs:attribute name="Power" type="xs:float"/>
    <xs:attribute name="PowerUnit" type="UnitsPower" default="mW"/>
  </xs:complexType>
  <xs:element name="Laser" substitutionGroup="LightSourceGroup">
    <xs:annotation>
      <xs:documentation>Description=A laser.</xs:documentation>
      <xs:documentation>Tier=1</xs:documentation>
      <xs:documentation>Split=[Fluorescence_LightSource]</xs:documentation>
    </xs:annotation>
    <xs:complexType><xs:complexContent><xs:extension base="LightSource">
      <xs:sequence><xs:element ref="Pump" minOccurs="0"/></xs:sequence>
      <xs:attribute name="Medium" type="LaserMedium"/>
    </xs:extension></xs:complexContent></xs:complexType>
  </xs:element>
  <xs:element name="Filament" substitutionGroup="LightSourceGroup">
    <xs:annotation><xs:documentation>Split=[Transmitted_LightSource; Fluorescence_LightSource]</xs:documentation>
    </xs:annotation>
    <xs:complexType><xs:complexContent><xs:extension base="LightSource">
      <xs:sequence><xs:element ref="ProfileFile" minOccurs="0"/></xs:sequence>
      <xs:attribute name="ProfileFile" type="xs:anyURI"/>
    </xs:extension></xs:complexContent></xs:complexType>
  </xs:element>
  <xs:element name="Pump" type="LaserRef"/>
  <xs:element name="ProfileFile" type="FileType"/>
  <xs:complexType name="FileType"><xs:attribute name="Location" type="xs:anyURI"/></xs:complexType>
  <xs:element name="WavelengthRange" type="WavelengthRangeType"/>
  <xs:complexType name="WavelengthRangeType">
    <xs:attribute name="CutIn" type="xs:float"/>
    <xs:attribute name="CutInUnit" type="UnitsLength"/>
  </xs:complexType>
  <xs:complexType name="Reference"/>
  <xs:complexType name="LaserRef">
    <xs:complexContent><xs:extension base="Reference">
      <xs:attribute name="ID" type="LaserID"/>
    </xs:extension></xs:complexContent>
  </xs:complexType>
  <xs:complexType name="Settings">
    <xs:complexContent><xs:extension base="Reference">
      <xs:attribute name="Note" type="xs:string"/>
    </xs:extension></xs:complexContent>
  </xs:complexType>
  <xs:element name="LightSourceSettings">
    <xs:complexType><xs:complexContent><xs:extension base="Settings">
      <xs:attribute name="ID" type="LightSourceID" use="required"/>
      <xs:attribute name="Attenuation" type="xs:float"/>
    </xs:extension></xs:complexContent></xs:complexType>
  </xs:element>
  <xs:element name="Description"><xs:simpleType><xs:restriction base="xs:string"/></xs:simpleType></xs:element>
  <xs:simpleType name="LSID"><xs:restriction base="xs:string"><xs:pattern value="\\S+:\\S+"/></xs:restriction>
  </xs:simpleType>
  <xs:simpleType name="InstrumentID"><xs:restriction base="LSID"/></xs:simpleType>
  <xs:simpleType name="LightSourceID"><xs:restriction base="LSID"/></xs:simpleType>
  <xs:simpleType name="LaserID"><xs:restriction base="LSID"/></xs:simpleType>
  <xs:simpleType name="LaserMedium"><xs:restriction base="xs:string">
    <xs:enumeration value="Cu"/><xs:enumeration value="Ar"/>
  </xs:restriction></xs:simpleType>
  <xs:simpleType name="UnitsPower"><xs:restriction base="xs:string">
    <xs:enumeration value="mW"/>
  </xs:restriction></xs:simpleType>
  <xs:simpleType name="UnitsLength"><xs:restriction base="xs:string">
    <xs:enumeration value="nm"/>
  </xs:restriction></xs:simpleType>
</xs:schema>
"""

SYNTHETIC_OME_XSD = """<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Laser">
    <xs:complexType>
      <xs:attribute name="Medium">
        <xs:annotation><xs:documentation>The lasing medium.</xs:documentation></xs:annotation>
      </xs:attribute>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


@unittest.skipIf(Linter is None, 'linkml is not installed')
class LinkmlConverterTest(unittest.TestCase):
    """The XSD-to-LinkML rules, each on a minimal synthetic XSD."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            xsd = os.path.join(folder, 'synthetic.xsd')
            ome_xsd = os.path.join(folder, 'ome.xsd')
            with open(xsd, 'w', encoding='utf-8') as file:
                file.write(SYNTHETIC_XSD)
            with open(ome_xsd, 'w', encoding='utf-8') as file:
                file.write(SYNTHETIC_OME_XSD)
            cls.schema, cls.units = LinkmlConverter(xsd, ome_xsd).convert()
        cls.classes = cls.schema['classes']

    def test_substitution_member_inherits_the_group_type(self):
        self.assertEqual(self.classes['Laser']['is_a'], 'LightSource')
        self.assertEqual(self.classes['Filament']['is_a'], 'LightSource')
        self.assertTrue(self.classes['LightSource']['abstract'])
        self.assertNotIn('Power', self.classes['Laser'].get('attributes', {}))

    def test_abstract_group_is_one_polymorphic_slot(self):
        slot = self.classes['Instrument']['attributes']['LightSource']
        self.assertEqual(slot['range'], 'LightSource')
        self.assertTrue(slot['multivalued'] and slot['inlined_as_list'] and slot['required'])
        self.assertNotIn('LightSourceGroup', self.classes)
        self.assertEqual(self.classes['LightSource']['slots'], ['ObjectType'])

    def test_reference_is_a_slot_to_the_target_id(self):
        pump = self.classes['Laser']['attributes']['Pump']
        self.assertEqual((pump['range'], pump['inlined']), ('Laser', False))
        self.assertNotIn('LaserRef', self.classes)
        self.assertNotIn('Pump', self.classes)

    def test_settings_id_refers_to_the_component(self):
        settings_id = self.classes['LightSourceSettings']['attributes']['ID']
        self.assertEqual((settings_id['range'], settings_id['inlined']), ('LightSource', False))
        self.assertNotIn('identifier', settings_id)
        self.assertTrue(self.classes['LightSource']['attributes']['ID']['identifier'])

    def test_type_used_by_one_element_is_one_class(self):
        self.assertIn('CutIn', self.classes['WavelengthRange']['attributes'])
        self.assertNotIn('WavelengthRangeType', self.classes)
        self.assertEqual(self.classes['LightSource']['attributes']['WavelengthRange']['range'], 'WavelengthRange')

    def test_attribute_and_element_of_one_name_both_kept(self):
        attributes = self.classes['Filament']['attributes']
        self.assertEqual(attributes['ProfileFile']['range'], 'uri')
        self.assertEqual(attributes['ProfileFileElement']['range'], 'ProfileFile')
        self.assertEqual(attributes['ProfileFileElement']['annotations']['xsd_element'], 'ProfileFile')

    def test_role_from_split_annotation(self):
        role = self.classes['LightSource']['attributes']['Role']
        self.assertEqual(role['range'], 'LightSourceRole')
        self.assertEqual(list(self.schema['enums']['LightSourceRole']['permissible_values']),
                         ['Fluorescence', 'Transmitted'])
        laser_role = self.classes['Laser']['slot_usage']['Role']['range']
        self.assertEqual(list(self.schema['enums'][laser_role]['permissible_values']), ['Fluorescence'])
        self.assertNotIn('slot_usage', self.classes['Filament'])

    def test_documentation_and_defaults(self):
        self.assertEqual(self.classes['Laser']['description'], 'A laser.')
        self.assertEqual(self.classes['Laser']['annotations']['Tier'], '1')
        self.assertEqual(self.classes['LightSource']['attributes']['PowerUnit']['ifabsent'], 'string(mW)')
        self.assertEqual(self.classes['Instrument']['attributes']['Description']['range'], 'string')

    def test_units_in_their_own_schema(self):
        self.assertEqual(set(self.units['enums']), {'UnitsPower', 'UnitsLength'})
        self.assertEqual(set(self.schema['enums']), {'LaserMedium', 'LightSourceRole', 'FluorescenceLightSourceRole'})

    def test_missing_descriptions_filled_with_their_source(self):
        medium = self.classes['Laser']['attributes']['Medium']
        self.assertEqual(medium['description'], 'The lasing medium.')
        self.assertEqual(medium['annotations']['description_source'], OME_SOURCE)
        unit = self.classes['LightSource']['attributes']['PowerUnit']
        self.assertEqual(unit['description'], 'The unit of Power.')
        self.assertEqual(unit['annotations']['description_source'], 'derived from LightSource.Power')
        self.assertEqual(self.schema['enums']['LaserMedium']['annotations']['description_source'], OME_SOURCE)

    def test_output_is_valid_linkml(self):
        with tempfile.TemporaryDirectory() as folder:
            write_schema(self.schema, os.path.join(folder, f'{SCHEMA_NAME}.yaml'))
            write_schema(self.units, os.path.join(folder, f'{UNITS_SCHEMA_NAME}.yaml'))
            self.assertEqual([problem.message for problem in
                              Linter.validate_schema(os.path.join(folder, f'{SCHEMA_NAME}.yaml'))], [])


@unittest.skipIf(Linter is None, 'linkml is not installed')
class MasterModelTest(unittest.TestCase):
    """models/imaging.yaml, the master model: valid, and still holding everything of the XSD and the JSON."""

    @classmethod
    def setUpClass(cls):
        cls.view = SchemaView(MODEL_FILE)
        cls.view.merge_imports()
        with open(MODEL_FILE, encoding='utf-8') as file:
            cls.model = yaml.safe_load(file)

    def test_valid_against_the_linkml_metamodel(self):
        self.assertEqual([problem.message for problem in Linter.validate_schema(MODEL_FILE)], [])

    def test_keeps_everything_converted_from_the_xsd(self):
        # The model is edited by hand; an edit may add to it but must not lose what the XSD defines.
        schema, units = LinkmlConverter(XSD_FILE, OME_XSD_FILE).convert()
        missing = []
        for class_name, cls in schema['classes'].items():
            kept = self.model['classes'].get(class_name)
            if kept is None:
                missing.append(class_name)
            for slot_name, slot in cls.get('attributes', {}).items():
                kept_slot = (kept or {}).get('attributes', {}).get(slot_name)
                # a range changed by hand keeps the XSD's as xsd_range (Image.AcquisitionDate: date -> datetime)
                kept_range = kept_slot and kept_slot.get('annotations', {}).get('xsd_range', kept_slot.get('range'))
                if kept_slot is None or kept_range != slot.get('range'):
                    missing.append(f'{class_name}.{slot_name}')
        for enum_name, enum in {**schema['enums'], **units['enums']}.items():
            kept = self.view.get_enum(enum_name)
            missing += [f'{enum_name}.{value}' for value in enum['permissible_values']
                        if kept is None or value not in kept.permissible_values]
        missing += [type_name for type_name in schema['types'] if type_name not in self.model['types']]
        self.assertEqual(missing, [])

    def test_holds_every_json_property(self):
        with open(JSON_SCHEMA_FILE, encoding='utf-8') as file:
            schemas = json.load(file)
        missing = []
        for schema in schemas:
            title = schema['title']
            if title not in self.view.all_classes():
                missing += [] if (title, None) in JSON_ONLY else [title]
            else:
                missing += self._missing_properties(title, schema['properties'])
        self.assertEqual(missing, [])

    def _missing_properties(self, class_name, properties):
        slots = {slot.name: slot for slot in self.view.class_induced_slots(class_name)}
        missing = []
        for prop, spec in properties.items():
            # the JSON drops the Ref of *Ref elements and calls AnnotationRef Description; Tier is an annotation
            slot = slots.get(prop) or slots.get(f'{prop}Ref') or (slots.get('Annotation') if prop == 'Description'
                                                                    else None)
            has_tier = prop == 'Tier' and 'Tier' in (self.view.get_class(class_name).annotations or {})
            if slot is None and not has_tier and (class_name, prop) not in JSON_ONLY:
                missing.append(f'{class_name}.{prop}')
            elif slot is not None and spec.get('type') == 'array' and 'properties' in spec.get('items', {}):
                missing += self._missing_properties(slot.range, spec['items']['properties'])
        return missing

    def _problems(self, instance, target_class):
        return [result.message for result in validate(instance, self.view.schema, target_class).results]

    def test_light_sources_of_several_types_in_one_list(self):
        laser = {'ObjectType': 'Laser', 'ID': 'LightSource:1', 'Manufacturer': 'Acme', 'Model': 'L1',
                 'CatalogNumber': 'C1', 'Tuneable': False, 'ModulationMechanism': 'Other', 'Pulse': False,
                 'IsPumped': True, 'IsPump': False, 'Pump': 'LightSource:2', 'Role': ['Fluorescence'],
                 'IlluminationWavelengthRange': [{'IlluminationPower': 20, 'PeakWavelength': 488}]}
        filament = {'ObjectType': 'Filament', 'ID': 'LightSource:3', 'Manufacturer': 'Acme', 'Model': 'F1',
                    'CatalogNumber': 'C3', 'Type': 'Halogen', 'Role': ['Transmitted', 'Fluorescence']}
        problems = self._problems({'ID': 'Instrument:1', 'Name': 'Test', 'LightSource': [laser, filament]},
                                  'Instrument')
        self.assertEqual([problem for problem in problems if 'is a required property' not in problem], [])
        self.assertEqual(self._problems({**laser, 'Role': ['Transmitted']}, 'Laser'),
                         ["'Transmitted' is not one of ['Fluorescence', 'Microdissection'] in /Role/0"])
        self.assertEqual(self._problems({**filament, 'LaserMedium': 'Cu'}, 'Filament'),
                         ["Additional properties are not allowed ('LaserMedium' was unexpected) in /"])

    def test_mappings_use_declared_prefixes(self):
        # exact_mappings/close_mappings to the OME LinkML schema (ome:)
        prefixes = set(self.view.schema.prefixes)
        undeclared = []
        for class_name, cls in self.view.all_classes().items():
            elements = [(class_name, cls)] + [(f'{class_name}.{name}', slot) for name, slot in (cls.attributes or {}).items()]
            for where, element in elements:
                for curie in list(element.exact_mappings) + list(element.close_mappings):
                    if curie.split(':')[0] not in prefixes:
                        undeclared.append(f'{where}: {curie}')
        self.assertEqual(undeclared, [])
        self.assertEqual(self.view.get_class('Laser').exact_mappings, ['ome:LaserLightSource'])

    def test_no_copies_of_shared_submodels(self):
        # fullSchema.json made a copy per parent (Arc_IlluminationWavelengthRange, StandardDichroic_Transmittance...)
        self.assertEqual({self.view.induced_slot('IlluminationWavelengthRange', name).range
                          for name in ('Arc', 'Laser', 'Filament', 'GenericExcitationSource')},
                         {'IlluminationWavelengthRange'})
        self.assertEqual(self.view.induced_slot('LEDModule', 'LightEmittingDiode').range, 'LEDModule')
        self.assertEqual({self.view.induced_slot('TransmittanceRange', name).range
                          for name in ('ExcitationFilter', 'EmissionFilter', 'StandardDichroic', 'NeutralDensityFilter')},
                         {'TransmittanceRange'})
        self.assertFalse([name for name in self.view.all_classes() if '_' in name])


if __name__ == '__main__':
    unittest.main()
