import unittest

from imaging_metadata_converter import AcquisitionMetadataMapper


class VendorWrapperTest(unittest.TestCase):
    """Tests that a per-tag vendor wrapper does not hide the fields below it."""

    @classmethod
    def setUpClass(cls):
        cls.mapper = AcquisitionMetadataMapper()

    def test_an_unknown_wrapper_key_is_dropped(self):
        # a reader keying each vendor blob by the TIFF tag it came from
        # produces this shape; no rule names "FEI_TITAN"
        wrapped = {'FEI_TITAN': {'Make': 'Acme', 'Model': 'Widget-1000'}}

        converted = self.mapper.convert_metadata(wrapped)

        self.assertEqual(converted, {
            'Instrument': {'Manufacturer': 'Acme', 'Model': 'Widget-1000'},
        })

    def test_wrapped_and_unwrapped_metadata_convert_alike(self):
        unwrapped = {'Make': 'Acme', 'Scan': {'ResolutionX': 1024}}

        self.assertEqual(
            self.mapper.convert_metadata({'FEI_HELIOS': unwrapped}),
            self.mapper.convert_metadata(unwrapped))

    def test_several_vendor_tags_are_all_unwrapped(self):
        wrapped = {
            'ExifTag': {'Make': 'Acme'},
            'OlympusSIS': {'cameraname': 'Xarosa'},
        }

        converted = self.mapper.convert_metadata(wrapped)

        self.assertEqual(converted['Instrument']['Manufacturer'], 'Acme')
        self.assertEqual(converted['Detector']['Name'], 'Xarosa')

    def test_plain_tag_values_beside_a_wrapper_are_kept(self):
        wrapped = {'Make': 'Acme', 'FibicsXML': {'Model': 'Widget-1000'}}

        converted = self.mapper.convert_metadata(wrapped)

        self.assertEqual(converted, {
            'Instrument': {'Manufacturer': 'Acme', 'Model': 'Widget-1000'},
        })

    def test_a_namespace_the_rules_name_is_never_stripped(self):
        # "Beam" is part of the mapped paths ("Beam.WD"), so it stays,
        # unlike an unrecognised wrapper
        converted = self.mapper.convert_metadata({'Beam': {'WD': 0.004}})

        self.assertEqual(
            converted['ElectronBeam']['WorkingDistance']['Value'], 0.004)

    def test_a_vendor_namespace_in_the_rules_survives_its_fields_resolving(self):
        # TALOS "CustomProperties" holds fields whose bare names do resolve
        # against the model, but a rule names the namespace, so the fields
        # must stay below it rather than being promoted
        metadata = {'CustomProperties': {'Detectors': {'Name': 'BM-Ceta'}}}

        converted = self.mapper.convert_metadata(metadata)

        self.assertNotIn('Detector', converted)

    def test_an_unknown_key_whose_fields_gain_nothing_is_kept(self):
        # nothing below it resolves either way, so there is no reason to
        # believe the key is a wrapper - keep the data where it was
        metadata = {'PrivateBlob': {'unmappable': 1}}

        converted = self.mapper.convert_metadata(metadata)

        self.assertEqual(converted, {'PrivateBlob': {'unmappable': 1}})


if __name__ == '__main__':
    unittest.main()
