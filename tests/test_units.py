import unittest

from imaging_metadata_converter.units import normalise


class NormaliseTest(unittest.TestCase):
    def test_lengths_to_micrometres(self):
        for value, unit, micrometres in ((1.5, 'mm', 1500.0), (532, 'nm', 0.532), (0.1, 'mm', 100.0),
                                         (2.5, 'Å', 0.00025), (300, 'pm', 0.0003), (1, 'in', 25400.0),
                                         (3, 'µm', 3.0), (2, 'm', 2000000.0)):
            with self.subTest(unit=unit):
                self.assertEqual(normalise(value, unit, 'µm'), micrometres)

    def test_angles_to_degrees(self):
        for value, unit, degrees in ((90, 'deg', 90.0), (0.5, 'rad', 28.64788975654116), (100, 'gon', 90.0),
                                     (1000, 'mrad', 57.29577951308232), (-135.0, 'degree', -135.0)):
            with self.subTest(unit=unit):
                self.assertEqual(normalise(value, unit, 'deg'), degrees)

    def test_aliases(self):
        for spelling in ('um', 'micron', 'micrometre'):
            with self.subTest(spelling=spelling):
                self.assertEqual(normalise(1, spelling, 'nm'), 1000.0)

    def test_micro_sign_and_greek_mu(self):
        self.assertEqual(normalise(1, 'μm', 'nm'), normalise(1, 'µm', 'nm'))

    def test_angstrom_sign(self):
        self.assertEqual(normalise(1, 'Å', 'nm'), 0.1)

    def test_case_tells_units_apart(self):
        self.assertEqual(normalise(1, 'pm', 'm'), 1e-12)
        self.assertEqual(normalise(1, 'Pm', 'm'), 1e15)

    def test_text_values(self):
        self.assertEqual(normalise('1.5', 'mm', 'µm'), 1500.0)

    def test_other_kind(self):
        self.assertIsNone(normalise(1, 'deg', 'µm'))

    def test_unknown_unit(self):
        self.assertIsNone(normalise(1, 'furlong', 'µm'))

    def test_length_unit_without_size(self):
        self.assertIsNone(normalise(1, 'Pixel', 'µm'))

    def test_not_a_number(self):
        self.assertIsNone(normalise('wide', 'mm', 'µm'))

    def test_no_negative_zero(self):
        """No rotation is 0, not a turn of -0.0."""
        self.assertEqual(str(normalise(-0.0, 'rad', 'deg')), '0.0')


if __name__ == '__main__':
    unittest.main()
