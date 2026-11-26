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

# mapping in a Python without LinkML: importing linkml_runtime fails there
WITHOUT_LINKML = """
import sys
sys.modules['linkml_runtime'] = None
from imaging_metadata_converter import convert_metadata
print(convert_metadata({'Make': 'Acme', 'Pixels': {'PhysicalSizeX': 0.5}})['Pixels']['PhysicalSizeX'])
try:
    from imaging_metadata_converter import ModelPaths
except ImportError as error:
    print(error)
"""


class ModelIndexTest(unittest.TestCase):
    def test_index_is_current(self):
        """The packaged index is what scripts/model_index.py makes of the model now."""
        with open(DEFAULT_MODEL_INDEX_FILE, encoding='utf-8') as file:
            packaged = json.load(file)
        self.assertEqual(packaged, model_index(), 'the model changed: run python scripts/model_index.py')

    def test_mapping_needs_no_linkml(self):
        source = os.path.join(REPO_ROOT, 'src')
        environment = dict(os.environ, PYTHONPATH=source + os.pathsep + os.environ.get('PYTHONPATH', ''))
        result = subprocess.run([sys.executable, '-c', WITHOUT_LINKML], capture_output=True, text=True,
                                env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        mapped, model_paths_error = result.stdout.strip().splitlines()
        self.assertEqual(mapped, '0.5')
        self.assertIn('imaging-metadata-converter[model]', model_paths_error)


if __name__ == '__main__':
    unittest.main()
