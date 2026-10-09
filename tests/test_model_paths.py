import os
import tempfile
import unittest

from imaging_metadata_converter.ModelPaths import ModelPaths

SYNTHETIC_MODEL = """
id: https://example.org/synthetic
name: synthetic
prefixes: {linkml: https://w3id.org/linkml/}
imports: [linkml:types]
default_range: string
slots:
  ObjectType: {range: string, designates_type: true}
classes:
  Instrument:
    tree_root: true
    attributes:
      ID: {identifier: true}
      Detector: {range: Detector, multivalued: true, inlined_as_list: true}
      LightPath: {range: LightPath, multivalued: true, inlined_as_list: true}
  Detector:
    abstract: true
    slots: [ObjectType]
    attributes:
      ID: {identifier: true}
  Camera:
    is_a: Detector
  LightPath:
    attributes:
      ID: {identifier: true}
      DetectorSettings: {range: DetectorSettings, multivalued: true, inlined_as_list: true}
  DetectorSettings:
    abstract: true
    slots: [ObjectType]
    attributes:
      ID: {range: Detector, inlined: false}
      Gain: {range: float}
  GenericDetectorSettings:
    is_a: DetectorSettings
  PointDetectorSettings:
    is_a: DetectorSettings
    attributes:
      Voltage: {range: float}
"""


class ModelPathsTest(unittest.TestCase):
    def test_an_abstract_component_slot_names_its_subtypes(self):
        with tempfile.TemporaryDirectory() as folder:
            model_file = os.path.join(folder, 'synthetic.yaml')
            with open(model_file, 'w', encoding='utf-8') as file:
                file.write(SYNTHETIC_MODEL)
            tree = ModelPaths(model_file).tree()

        # settings of an abstract kind are written as their subtype, as the profile has them; a detector, which
        # has an identifier, is a path of its own
        self.assertEqual(tree['LightPath'], {'ID': 'string',
                                             'GenericDetectorSettings': {'ID': 'Detector', 'Gain': 'float'},
                                             'PointDetectorSettings': {'ID': 'Detector', 'Gain': 'float',
                                                                       'Voltage': 'float'}})
        self.assertEqual(tree['Camera'], {'ID': 'string'})


if __name__ == '__main__':
    unittest.main()
