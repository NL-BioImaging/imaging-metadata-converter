"""Convert every example source metadata file in examples/."""

import json
import os
import sys
import unittest

from imaging_metadata_converter import AcquisitionMetadataMapper


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES_DIR = os.path.join(REPO_ROOT, 'examples')
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import convert_examples


def example_files():
    return sorted(
        os.path.join(EXAMPLES_DIR, name)
        for name in os.listdir(EXAMPLES_DIR)
        if name.endswith('.json')
    )


class ExampleConversionTest(unittest.TestCase):
    """Each example is real vendor metadata, so this doubles as a smoke test."""

    @classmethod
    def setUpClass(cls):
        cls.mapper = AcquisitionMetadataMapper()

    def test_examples_present(self):
        self.assertTrue(example_files())

    def test_every_example_converts_to_a_non_empty_dict(self):
        for file_path in example_files():
            with self.subTest(example=os.path.basename(file_path)):
                with open(file_path, 'r', encoding='utf-8') as file:
                    metadata = json.load(file)

                converted = self.mapper.convert_metadata(metadata)

                self.assertIsInstance(converted, dict)
                self.assertTrue(converted)

    def test_output_is_up_to_date(self):
        self.assertEqual(convert_examples.main(['--check']), 0, 'rerun: python scripts/convert_examples.py')


if __name__ == '__main__':
    unittest.main()
