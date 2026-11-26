import unittest

from imaging_metadata_converter.spatial import spatial_metadata


class SpatialMetadataTest(unittest.TestCase):
    def test_pixel_size_in_micrometres(self):
        mapped = {'Pixels': {'PhysicalSizeX': 10, 'PhysicalSizeXUnit': 'nm', 'PhysicalSizeY': 10,
                             'PhysicalSizeYUnit': 'nm'}}
        self.assertEqual(spatial_metadata(mapped)['pixel_size'], {'x': 0.01, 'y': 0.01})

    def test_value_without_unit_in_micrometres(self):
        self.assertEqual(spatial_metadata({'Pixels': {'PhysicalSizeX': 0.5}})['pixel_size'], {'x': 0.5})

    def test_position_of_the_plane(self):
        mapped = {'Plane': {'PositionX': 1.5, 'PositionXUnit': 'mm', 'PositionY': -2, 'PositionYUnit': 'mm'}}
        self.assertEqual(spatial_metadata(mapped)['position'], {'x': 1500.0, 'y': -2000.0})

    def test_position_of_the_first_plane(self):
        mapped = {'Plane': [{'PositionX': 1}, {'PositionX': 2}]}
        self.assertEqual(spatial_metadata(mapped)['position'], {'x': 1.0})

    def test_position_from_stage_label(self):
        mapped = {'Image': {'StageLabel': {'X': 3, 'XUnit': 'µm'}}}
        self.assertEqual(spatial_metadata(mapped)['position'], {'x': 3.0})

    def test_plane_position_before_stage_label(self):
        mapped = {'Plane': {'PositionX': 1}, 'Image': {'StageLabel': {'X': 3}}}
        self.assertEqual(spatial_metadata(mapped)['position'], {'x': 1.0})

    def test_scan_rotation_in_degrees(self):
        mapped = {'Image': {'BeamScanSettings': {'Rotation': 0.5, 'RotationUnit': 'rad'}}}
        self.assertEqual(spatial_metadata(mapped)['rotation'], 28.64788975654116)

    def test_rotation_without_unit_in_degrees(self):
        self.assertEqual(spatial_metadata({'Image': {'BeamScanSettings': {'Rotation': 90}}})['rotation'], 90.0)

    def test_slide_scan_rotation(self):
        self.assertEqual(spatial_metadata({'Image': {'SlideScanSettings': {'Rotation': 90}}})['rotation'], 90.0)

    def test_stage_rotation_apart_from_image_rotation(self):
        spatial = spatial_metadata({'Plane': {'Rotation': 30}})
        self.assertEqual((spatial['rotation'], spatial['stage_rotation']), (None, 30.0))

    def test_raw_stage_rotation(self):
        mapped = {'Plane': {'RawStage': {'Rotation': 1, 'RotationUnit': 'rad'}}}
        self.assertEqual(spatial_metadata(mapped)['stage_rotation'], 57.29577951308232)

    def test_no_rotation_is_not_negative_zero(self):
        mapped = {'Image': {'BeamScanSettings': {'Rotation': -0.0}}}
        self.assertEqual(str(spatial_metadata(mapped)['rotation']), '0.0')

    def test_nothing_known(self):
        self.assertEqual(spatial_metadata({'Make': 'Acme'}),
                         {'pixel_size': {}, 'position': {}, 'rotation': None, 'stage_rotation': None})

    def test_unit_without_size_is_left_out(self):
        self.assertEqual(spatial_metadata({'Plane': {'PositionX': 4, 'PositionXUnit': 'reference frame'}})
                         ['position'], {})


def scanned(field_of_view, **pixels):
    return {'Image': {'BeamScanSettings': {'FieldOfView': field_of_view}}, 'Pixels': pixels}


class FieldOfViewPixelSizeTest(unittest.TestCase):
    def test_field_of_view_over_pixels(self):
        mapped = scanned({'X': {'Value': 100, 'Unit': 'µm'}, 'Y': {'Value': 50, 'Unit': 'µm'}}, SizeX=1000, SizeY=250)
        self.assertEqual(spatial_metadata(mapped)['pixel_size'], {'x': 0.1, 'y': 0.2})

    def test_one_axis_means_square_pixels(self):
        mapped = scanned({'X': {'Value': 0.1, 'Unit': 'mm'}}, SizeX=1000)
        self.assertEqual(spatial_metadata(mapped)['pixel_size'], {'x': 0.1, 'y': 0.1})

    def test_shape_given_by_the_reader(self):
        mapped = scanned({'X': {'Value': 100}}, SizeX=1000)
        self.assertEqual(spatial_metadata(mapped, shape={'x': 500})['pixel_size'], {'x': 0.2, 'y': 0.2})

    def test_stated_pixel_size_first(self):
        mapped = scanned({'X': {'Value': 100}}, SizeX=1000, PhysicalSizeX=0.5)
        self.assertEqual(spatial_metadata(mapped)['pixel_size'], {'x': 0.5})

    def test_no_pixel_count(self):
        self.assertEqual(spatial_metadata(scanned({'X': {'Value': 100}}))['pixel_size'], {})


if __name__ == '__main__':
    unittest.main()
