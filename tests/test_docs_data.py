import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import docs_data


def test_model_page_counts_are_all_known():
    data = docs_data.ModelData()
    page = (ROOT / 'docs' / 'model.md').read_text(encoding='utf-8')
    filled = docs_data.fill(page, data.counts())
    assert '{{' not in filled


def test_site_data_is_the_packaged_model():
    data = docs_data.ModelData()
    files = data.files()
    assert set(files) == {'model.json', 'added.json', 'mappings.json', 'details.json'}
    assert json.loads(files['model.json']) == data.model.tree()
    assert set(json.loads(files['added.json'])) <= set(docs_data.all_paths(data.tree))


def test_details_cover_every_path_and_name_known_texts():
    data = docs_data.ModelData()
    details = json.loads(data.files()['details.json'])
    assert set(details['paths']) == set(docs_data.all_paths(data.tree))
    for entry in details['paths'].values():
        for key in ('description', 'description_source'):
            assert 0 <= entry.get(key, 0) < len(details['texts'])


def test_details_state_what_the_model_says():
    data = docs_data.ModelData()
    details = json.loads(data.files()['details.json'])
    paths = details['paths']
    manufacturer = paths['Laser.Manufacturer']
    assert details['texts'][manufacturer['description']] == data.model.slots('Laser')['Manufacturer'].description
    assert manufacturer['declared_by'] == 'ManufacturerSpec'
    assert manufacturer['exact_mappings'] == ['ome:manufacturer']
    assert paths['Laser.ID']['identifier'] and paths['Laser.ID']['required']
    assert paths['Laser.Pump']['reference']
    assert 'reference' not in paths['Image.Pixels']
    assert paths['Image.StageLabel']['multivalued'] and paths['Image.StageLabel']['class'] == 'StageLabel'
    assert paths['Laser']['is_a'] == 'LightSource'
    assert paths['Laser']['domain'] == 'MicroscopeHardwareSpecifications'


def test_a_field_takes_the_larger_tier_of_its_own_and_its_class():
    def tiered(tier):
        return SimpleNamespace(annotations={'Tier': SimpleNamespace(value=tier)} if tier else None)

    assert docs_data._tier(tiered('1'), tiered('2')) == 2
    assert docs_data._tier(tiered('3'), tiered('1')) == 3
    assert docs_data._tier(tiered(None), tiered('2')) == 2
    assert docs_data._tier(tiered(None), tiered(None)) is None


def test_details_name_the_root_and_what_an_abstract_class_stands_for():
    data = docs_data.ModelData()
    details = json.loads(data.files()['details.json'])
    assert details['root'] == 'OME'
    assert 'Laser' in details['subclasses']['LightSource']
    assert 'CCD' in details['subclasses']['Detector']
    for concrete in details['subclasses'].values():
        assert set(concrete) <= set(data.tree)


def test_details_list_the_values_of_every_enumeration_a_field_ranges_over():
    data = docs_data.ModelData()
    details = json.loads(data.files()['details.json'])
    enums = details['enums']
    ranges = set(docs_data.leaf_ranges(data.tree))
    assert set(enums) == ranges & set(data.model.view.all_enums())
    for name, enumeration in enums.items():
        permissible = data.model.view.get_enum(name).permissible_values
        assert [value['value'] for value in enumeration['values']] == list(permissible)
    micrometre = next(value for value in enums['UnitsLength']['values'] if value['value'] == 'µm')
    assert 'um' in micrometre['aliases']
    assert details['texts'][enums['UnitsAngle']['description']] == data.model.view.get_enum('UnitsAngle').description
