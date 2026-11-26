"""Write the model index (models/model_index.json): what the mapper uses of the LinkML model, as plain JSON, so
mapping metadata needs no LinkML. Run after every change to the model; a test checks the index is current.

    python scripts/model_index.py
"""

import argparse
import json

from imaging_metadata_converter.model_files import DEFAULT_MODEL_FILE, DEFAULT_MODEL_INDEX_FILE
from imaging_metadata_converter.ModelPaths import ModelPaths


def model_index(model_filename=DEFAULT_MODEL_FILE):
    return ModelPaths(model_filename).index()


def write_model_index(model_filename=DEFAULT_MODEL_FILE, index_filename=DEFAULT_MODEL_INDEX_FILE):
    with open(index_filename, 'w', encoding='utf-8', newline='\n') as file:
        json.dump(model_index(model_filename), file, ensure_ascii=False, separators=(',', ':'))
        file.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--model', default=DEFAULT_MODEL_FILE, help='Path to the LinkML model')
    parser.add_argument('--output', default=DEFAULT_MODEL_INDEX_FILE, help='Path of the index to write')
    args = parser.parse_args()
    write_model_index(args.model, args.output)
