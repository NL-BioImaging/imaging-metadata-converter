import unittest

from imaging_metadata_converter import AcquisitionMetadataMapper
from imaging_metadata_converter.spatial import spatial_metadata


class SpatialVendorTest(unittest.TestCase):
    """How each vendor writes where its image is, mapped by the rules: each case a few fields of its header."""

    @classmethod
    def setUpClass(cls):
        cls.mapper = AcquisitionMetadataMapper()

    def spatial(self, metadata):
        return spatial_metadata(self.mapper.convert_metadata(metadata))

    def test_ciqtek_scan_rotation_in_degrees(self):
        self.assertEqual(self.spatial({'FEI_HELIOS': {'Beam': {'ElectricRotate': -135.0}}})['rotation'], -135.0)

    def test_ciqtek_stage_in_millimetres(self):
        spatial = self.spatial({'FEI_HELIOS': {'Stage': {'StagePosX': 12.5, 'StagePosR': 11.7}}})
        self.assertEqual((spatial['position'], spatial['stage_rotation']), ({'x': 12500.0}, 11.7))

    def test_ciqtek_pixel_size_from_field_width(self):
        metadata = {'FEI_HELIOS': {'Beam': {'HFW': '71.68µm'}, 'Scan': {'ResolutionX': 1024, 'ResolutionY': 768}}}
        self.assertEqual(self.spatial(metadata)['pixel_size'], {'x': 0.07, 'y': 0.07})

    def test_fei_scan_rotation_in_radians(self):
        self.assertEqual(self.spatial({'FEI_HELIOS': {'Beam': {'ScanRotation': 0.5}}})['rotation'],
                         28.64788975654116)

    def test_fei_stage_in_metres_and_radians(self):
        spatial = self.spatial({'FEI_HELIOS': {'Stage': {'StageX': 0.001, 'StageR': 1.0}}})
        self.assertEqual((spatial['position'], spatial['stage_rotation']), ({'x': 1000.0}, 57.29577951308232))

    def test_fei_pixel_size_in_metres(self):
        metadata = {'FEI_HELIOS': {'Scan': {'PixelWidth': 1e-08, 'PixelHeight': 1e-08}}}
        self.assertEqual(self.spatial(metadata)['pixel_size'], {'x': 0.01, 'y': 0.01})

    def test_fei_titan_pixel_size_in_metres(self):
        metadata = {'Metadata': {'BinaryResult': {'PixelSize': {'X': 1.6528e-9, 'Y': 1.6528e-9}}}}
        self.assertEqual(self.spatial(metadata)['pixel_size'], {'x': 0.0016528, 'y': 0.0016528})

    def test_fei_titan_stage_position_in_metres(self):
        """In metres, its y pointing up (inverted), as Fibics'."""
        metadata = {'FEI_TITAN': {'Metadata': {'StageSettings': {'StagePosition': {
            'X': -0.000285, 'Y': -4.7e-05, 'Tilt': {'Alpha': 3.4e-05}}}}}}
        self.assertEqual(self.spatial(metadata)['position'], {'x': -285.0, 'y': 47.0})

    def test_fei_titan_tiles_turned_90_degrees(self):
        """Its tiles are turned 90 degrees against the stage, which the header does not state."""
        metadata = {'FEI_TITAN': {'Metadata': {'StageSettings': {'StagePosition': {'X': 0.0, 'Y': 0.0}}}}}
        self.assertEqual(self.spatial(metadata)['rotation'], 90.0)

    def test_stated_rotation_before_implied_one(self):
        metadata = {'FEI_TITAN': {'Metadata': {'StageSettings': {'StagePosition': {'X': 0.0}}}},
                    'acquisition': {'scan': {'rotation': 30}}}
        self.assertEqual(self.spatial(metadata)['rotation'], 30.0)

    def test_fei_stage_section_over_beam_copy(self):
        metadata = {'FEI_HELIOS': {'IRBeam': {'StageX': -0.00126661}, 'Stage': {'StageX': 0.0699197}}}
        self.assertEqual(self.spatial(metadata)['position'], {'x': 69919.7})

    def test_phenom_sample_position_in_metres(self):
        self.assertEqual(self.spatial({'samplePosition': {'x': 0.002, 'y': -0.001}})['position'],
                         {'x': 2000.0, 'y': -1000.0})

    def test_stage_rotation_with_units(self):
        self.assertEqual(self.spatial({'Stage': {'R': {'value': 0.5, 'units': 'rad'}}})['stage_rotation'],
                         28.64788975654116)

    def test_phenom_scan_rotation(self):
        self.assertEqual(self.spatial({'acquisition': {'scan': {'rotation': 90}}})['rotation'], 90.0)

    def test_fibics_scan_rotation(self):
        metadata = {'FibicsXML': {'Fibics': {'Scan': {'ScanRot': {'units': 'deg', 'value': 12.0}}}}}
        self.assertEqual(self.spatial(metadata)['rotation'], 12.0)

    def test_fibics_stage_y_points_up(self):
        """Fibics' stage y axis points against the image's, so its y position is inverted."""
        metadata = {'FibicsXML': {'Fibics': {'Stage': {'X': {'units': 'um', 'value': 5},
                                                       'Y': {'units': 'um', 'value': 10}}}}}
        self.assertEqual(self.spatial(metadata)['position'], {'x': 5.0, 'y': -10.0})

    def test_inverted_number_written_as_text(self):
        metadata = {'FibicsXML': {'Fibics': {'Stage': {'Y': {'units': 'um', 'value': '10'}}}}}
        self.assertEqual(self.spatial(metadata)['position'], {'y': -10.0})

    def test_fibics_pixel_size_from_field_of_view(self):
        metadata = {'FibicsXML': {'Fibics': {'Image': {'Width': 1000, 'Height': 500},
                                             'Scan': {'FOV_X': {'units': 'um', 'value': 100},
                                                      'FOV_Y': {'units': 'um', 'value': 50}}}}}
        self.assertEqual(self.spatial(metadata)['pixel_size'], {'x': 0.1, 'y': 0.1})


if __name__ == '__main__':
    unittest.main()
