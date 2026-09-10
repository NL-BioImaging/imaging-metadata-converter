"""Convert every example source metadata file in examples/."""

import json
import os
import unittest

from imaging_metadata_converter import AcquisitionMetadataMapper

EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'examples')


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


if __name__ == '__main__':
    unittest.main()
