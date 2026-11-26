import json
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from model_index import model_index
from imaging_metadata_converter.model_files import DEFAULT_MODEL_INDEX_FILE

# run in a Python without LinkML: importing linkml_runtime fails there
WITHOUT_LINKML = """
import sys
sys.modules['linkml_runtime'] = None
"""
MAPPING = """
from imaging_metadata_converter import convert_metadata
print(convert_metadata({'Pixels': {'PhysicalSizeX': 0.5}})['Pixels']['PhysicalSizeX'])
"""
MODEL_PATHS = """
try:
    from imaging_metadata_converter import ModelPaths
except ImportError as error:
    print(error)
"""


def run_without_linkml(code):
    source = os.path.join(REPO_ROOT, 'src')
    environment = dict(os.environ, PYTHONPATH=source + os.pathsep + os.environ.get('PYTHONPATH', ''))
    return subprocess.run([sys.executable, '-c', WITHOUT_LINKML + code], capture_output=True, text=True,
                          env=environment)


class ModelIndexTest(unittest.TestCase):
    def test_index_is_current(self):
        """The packaged index is what scripts/model_index.py makes of the model now."""
        with open(DEFAULT_MODEL_INDEX_FILE, encoding='utf-8') as file:
            packaged = json.load(file)
        self.assertEqual(packaged, model_index(), 'the model changed: run python scripts/model_index.py')

    def test_mapping_needs_no_linkml(self):
        result = run_without_linkml(MAPPING)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '0.5')

    def test_star_import_without_linkml(self):
        result = run_without_linkml('from imaging_metadata_converter import *')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_model_paths_names_the_extra_without_linkml(self):
        result = run_without_linkml(MODEL_PATHS)
        self.assertIn('imaging-metadata-converter[model]', result.stdout)


if __name__ == '__main__':
    unittest.main()
