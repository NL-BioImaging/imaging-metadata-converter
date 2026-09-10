import unittest

from imaging_metadata_converter import flatten_dict


class FlattenDictTest(unittest.TestCase):
    """Tests flattening a nested metadata dict to one entry per leaf."""

    def test_nested_dicts_are_joined_with_dots(self):
        flattened = flatten_dict({'Scan': {'Resolution': {'X': 1024}}})

        self.assertEqual(flattened, {'Scan.Resolution.X': 1024})

    def test_top_level_leaves_keep_their_own_key(self):
        flattened = flatten_dict({'Make': 'Acme', 'Model': 'Widget-1000'})

        self.assertEqual(flattened, {'Make': 'Acme', 'Model': 'Widget-1000'})

    def test_list_items_are_keyed_by_index(self):
        flattened = flatten_dict({'Detectors': [{'Name': 'QBSD'}, {'Name': 'SED'}]})

        self.assertEqual(flattened, {
            'Detectors.0.Name': 'QBSD',
            'Detectors.1.Name': 'SED',
        })

    def test_tuples_are_flattened_like_lists(self):
        flattened = flatten_dict({'Size': (16, 32)})

        self.assertEqual(flattened, {'Size.0': 16, 'Size.1': 32})

    def test_a_key_containing_colons_stays_one_segment(self):
        # some sources hold a key of literally this shape, so the colons
        # are part of the name and must not be treated as separators
        flattened = flatten_dict({
            'Annotation:CustomAttributes:SVI:Image:0': {'RefrIndexMedium': 1.515},
        })

        self.assertEqual(flattened, {
            'Annotation:CustomAttributes:SVI:Image:0.RefrIndexMedium': 1.515,
        })

    def test_prefix_is_prepended_when_given(self):
        flattened = flatten_dict({'WD': 0.004}, 'Beam')

        self.assertEqual(flattened, {'Beam.WD': 0.004})

    def test_non_string_keys_are_usable_as_path_segments(self):
        flattened = flatten_dict({0: {'Name': 'first'}})

        self.assertEqual(flattened, {'0.Name': 'first'})


if __name__ == '__main__':
    unittest.main()
