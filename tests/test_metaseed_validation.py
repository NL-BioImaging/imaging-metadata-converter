import glob
import os
import shutil
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_FILE = os.path.join(REPO_ROOT, 'profile', 'imaging.metaseed.yaml')
EXPORT_DIR = os.path.join(REPO_ROOT, 'export')

try:
    from metaseed.specs import loader as metaseed_loader
    from metaseed.validators import validate as metaseed_validate
except ImportError:
    metaseed_loader = None

# the one kind of error the exports are known to have: LiMi's own required fields the sources do not state
REQUIRED_RULE = 'required_fields'


@unittest.skipIf(metaseed_loader is None, 'metaseed is not installed')
class MetaseedValidationTest(unittest.TestCase):
    """Every exported dataset validates with metaseed itself against the generated profile, but for missing
    required fields: no type, format, constraint or unknown-field error."""

    @classmethod
    def setUpClass(cls):
        with open(PROFILE_FILE, encoding='utf-8') as file:
            profile = yaml.safe_load(file)
        cls.name, cls.version = profile['name'], profile['version']
        # metaseed finds profiles in its user data folder, from these variables
        cls.data_dir = tempfile.mkdtemp()
        specs_dir = os.path.join(cls.data_dir, 'metaseed', 'specs', cls.name, cls.version)
        os.makedirs(specs_dir)
        shutil.copy(PROFILE_FILE, os.path.join(specs_dir, 'profile.yaml'))
        cls.saved_environment = {key: os.environ.get(key) for key in ('LOCALAPPDATA', 'XDG_DATA_HOME')}
        os.environ['LOCALAPPDATA'] = cls.data_dir
        os.environ['XDG_DATA_HOME'] = cls.data_dir
        # metaseed makes a new loader, with an empty profile cache, for every nested entity it validates, and
        # re-parses the whole profile each time: one cache for all of them validates in seconds, not hours
        cls.original_init = metaseed_loader.SpecLoader.__init__
        shared_cache = {}

        def shared_init(loader, *args, **kwargs):
            cls.original_init(loader, *args, **kwargs)
            loader._profile_cache = shared_cache

        metaseed_loader.SpecLoader.__init__ = shared_init

    @classmethod
    def tearDownClass(cls):
        metaseed_loader.SpecLoader.__init__ = cls.original_init
        for key, value in cls.saved_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def test_exports_have_no_errors_but_missing_required_fields(self):
        export_files = sorted(glob.glob(os.path.join(EXPORT_DIR, '*.yaml')))
        self.assertTrue(export_files)
        for export_file in export_files:
            with self.subTest(dataset=os.path.basename(export_file)):
                with open(export_file, encoding='utf-8') as file:
                    dataset = yaml.safe_load(file)
                errors = metaseed_validate(dataset, 'OME', self.version, self.name)
                self.assertEqual([f'{error.field}: {error.message} ({error.rule})' for error in errors
                                  if error.rule != REQUIRED_RULE], [])

    def test_profile_declares_its_entities_in_containment_order(self):
        from metaseed.specs.ordering import is_in_containment_order
        from metaseed.specs.schema import ProfileSpec
        with open(PROFILE_FILE, encoding='utf-8') as file:
            self.assertTrue(is_in_containment_order(ProfileSpec.model_validate(yaml.safe_load(file))))

    def test_a_wrong_value_is_reported(self):
        # the check can fail: a value of the wrong type in an otherwise valid export
        with open(os.path.join(EXPORT_DIR, 'Delmic FAST-EM.yaml'), encoding='utf-8') as file:
            dataset = yaml.safe_load(file)
        dataset['Instrument'][0]['Manufacturer'] = 42
        errors = metaseed_validate(dataset, 'OME', self.version, self.name)
        self.assertTrue([error for error in errors if error.rule != REQUIRED_RULE])


if __name__ == '__main__':
    unittest.main()
