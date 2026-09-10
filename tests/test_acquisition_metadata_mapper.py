import unittest

from imaging_metadata_converter import (
    AcquisitionMetadataMapper,
    convert_metadata,
)


class AcquisitionMetadataMapperTest(unittest.TestCase):
    """Tests the dict-in/dict-out schema mapping (no file I/O)."""

    @classmethod
    def setUpClass(cls):
        cls.mapper = AcquisitionMetadataMapper()

    def test_convert_metadata_accepts_in_memory_dict(self):
        sample = {'Make': 'Acme', 'Model': 'Widget-1000'}

        converted = self.mapper.convert_metadata(sample)

        self.assertEqual(converted, {
            'Instrument': {'Manufacturer': 'Acme', 'Model': 'Widget-1000'},
        })

    def test_convert_metadata_rejects_non_dict(self):
        with self.assertRaises(TypeError):
            self.mapper.convert_metadata(['not', 'a', 'dict'])

    def test_module_level_convert_metadata_uses_packaged_schema(self):
        converted = convert_metadata({'Make': 'Acme'})

        self.assertEqual(converted, {'Instrument': {'Manufacturer': 'Acme'}})


if __name__ == '__main__':
    unittest.main()
