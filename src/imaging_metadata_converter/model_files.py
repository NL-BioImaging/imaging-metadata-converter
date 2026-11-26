"""Where the packaged model and its index are, importable without LinkML."""

import os.path

DEFAULT_MODEL_FILE = os.path.join(os.path.dirname(__file__), 'models', 'imaging.yaml')
# what the mapper uses of the model, generated from it by scripts/model_index.py, so mapping needs no LinkML
DEFAULT_MODEL_INDEX_FILE = os.path.join(os.path.dirname(__file__), 'models', 'model_index.json')
