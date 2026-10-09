"""One place per meaning, in the model and in the rules that map onto it.

MechanicalStage.Position.Rot once repeated MechanicalStage.Rotation (a class shared by Position and RawPosition
carried fields only one of them needed), and the EM vendors' StagePosX went to the stage hardware while Leica's
went to Plane.PositionX. These tests look for both kinds of repetition.
"""

import json
import os
import re
import tempfile
import unittest
from collections import defaultdict

from imaging_metadata_converter.AcquisitionMetadataMapper import DEFAULT_MAPPINGS_FILE, rule_targets
from imaging_metadata_converter.ModelPaths import ModelPaths

EXTENSION_SCHEMA = 'imaging_extension'

# components whose fields repeat their owner's by design: the stage's raw readout of the Plane's axes
MIRRORS = {'Plane.RawStage'}

# names every kind of record has, which mean something different in each
STRUCTURAL_NAMES = {'ID', 'Name', 'Type', 'Value', 'Unit', 'Begin', 'End', 'X', 'Y', 'Annotation'}

# source names too generic to mean the same wherever a source writes them
GENERIC_SOURCE_NAMES = {'id', 'name', 'type', 'width', 'height', 'left', 'top'}

# source names that do go to different fields, each reviewed (2026-10-09) and left for a decision of its own
KNOWN_DIFFERING_SOURCE_NAMES = {
    # Leica's CameraName is a camera model ("DFC4400-GI_..."), EMSIS's cameraname the camera's name
    'cameraname',
}


def same_name(name, other):
    """Whether two field names name the same thing: equal, or one the other cut short within a word (Rot,
    Rotation), not a compound of it (Begin, BeginEnergy)."""
    short, long = sorted((name, other), key=len)
    return name == other or (len(short) >= 3 and long.startswith(short) and long[len(short)].islower())


def defining_schema(paths, class_name, slot_name):
    for ancestor in paths.view.class_ancestors(class_name, mixins=True):
        if slot_name in (paths.view.get_class(ancestor).attributes or {}):
            return paths.view.in_schema(ancestor)
    return paths.view.in_schema(class_name)


def repeated_fields(paths, extension_schema=EXTENSION_SCHEMA, mirrors=frozenset()):
    """(field path, the field above it that it repeats) for each field of a component named as a field of a
    class above it, where the extension has a part in at least one of the two; LiMi's own names are not
    ours to change."""
    found = []

    def walk(class_name, path, ancestors):
        for slot_name, slot in paths.slots(class_name).items():
            child_path = f'{path}.{slot_name}'
            seen = [owner for owner, _, _ in ancestors] + [class_name]
            is_component = slot.range in paths.classes and bool(slot.inlined or slot.inlined_as_list) \
                and paths.is_component(slot.range) and slot.range not in seen
            if is_component and child_path not in mirrors:
                walk(slot.range, child_path, ancestors + [(class_name, path, slot_name)])
            for owner, owner_path, held_by in ancestors:
                for other in paths.slots(owner):
                    if other != held_by and slot_name not in STRUCTURAL_NAMES and same_name(slot_name, other) \
                            and extension_schema in (defining_schema(paths, class_name, slot_name),
                                                     defining_schema(paths, owner, other)):
                        found.append((child_path, f'{owner_path}.{other}'))

    for start in paths.tree():
        walk(start, start, [])
    return found


def target_field(target, mirrors=frozenset()):
    """The field a rule's target is a part of: Plane.PositionXUnit and Plane.PositionX are one field, a
    Quantity's Value and Unit one, a list item's field the list's, and a mirror's field its owner's."""
    field = re.sub(r'\[\*?\]', '', target)
    for mirror in mirrors:
        field = field.replace(f'{mirror}.', f'{mirror.rsplit(".", 1)[0]}.')
    return re.sub(r'\.(Value|Unit|Begin|End)$|Unit$', '', field)


def differing_targets(rules, mirrors=frozenset()):
    """{source name: {(field, source key), ...}} for each name that sources of different rules write, but the
    rules send to different fields: the same value in two places, or a rule to correct."""
    fields_by_name = defaultdict(set)
    for source, rule in rules.items():
        names = [name for name in source.split('.') if name.lower() not in ('value', 'unit', 'units', 'variant')]
        name = names[-1].lower() if names else ''
        if not source.endswith('*') and len(name) > 2 and name not in GENERIC_SOURCE_NAMES:
            fields_by_name[name].update((target_field(target, mirrors), source) for target in rule_targets(rule))
    return {name: entries for name, entries in fields_by_name.items()
            if len({field for field, _ in entries}) > 1 and len({source for _, source in entries}) > 1}


SYNTHETIC_MODEL = """
id: https://example.org/synthetic
name: synthetic
prefixes: {linkml: https://w3id.org/linkml/}
imports: [linkml:types, synthetic_extension]
default_range: string
classes:
  Instrument:
    tree_root: true
    attributes:
      ID: {identifier: true}
      Stage: {range: Stage, inlined: true}
  Stage:
    mixins: [StageExtension]
    attributes:
      ID: {identifier: true}
      RotationAngle: {range: float}
"""

SYNTHETIC_EXTENSION = """
id: https://example.org/synthetic/extension
name: synthetic_extension
prefixes: {linkml: https://w3id.org/linkml/}
imports: [linkml:types]
default_range: string
classes:
  Quantity:
    attributes:
      Value: {range: float}
      Unit: {}
  StageExtension:
    mixin: true
    attributes:
      Position: {range: StagePosition, inlined: true}
      RawPosition: {range: StagePosition, inlined: true}
      Rotation: {range: Quantity, inlined: true}
      Tilt: {range: Quantity, inlined: true}
  StagePosition:
    attributes:
      X: {range: Quantity, inlined: true}
      Tilt: {range: Quantity, inlined: true}
      Rot: {range: Quantity, inlined: true}
      BeginEnergy: {range: Quantity, inlined: true}
"""


class RepeatedFieldTest(unittest.TestCase):
    def test_a_shared_class_repeating_its_owner_is_found(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, text in (('synthetic', SYNTHETIC_MODEL), ('synthetic_extension', SYNTHETIC_EXTENSION)):
                with open(os.path.join(folder, f'{name}.yaml'), 'w', encoding='utf-8') as file:
                    file.write(text)
            paths = ModelPaths(os.path.join(folder, 'synthetic.yaml'))
            found = set(repeated_fields(paths, extension_schema='synthetic_extension'))
        self.assertEqual(found, {(f'Stage.{position}.{name}', f'Stage.{other}')
                                 for position in ('Position', 'RawPosition')
                                 for name, other in (('Rot', 'Rotation'), ('Rot', 'RotationAngle'),
                                                     ('Tilt', 'Tilt'))})

    def test_names_cut_short_within_a_word_are_the_same(self):
        self.assertTrue(same_name('Rot', 'Rotation'))
        self.assertTrue(same_name('Tilt', 'Tilt'))
        self.assertFalse(same_name('Begin', 'BeginEnergy'))
        self.assertFalse(same_name('Tilt', 'TiltBeta'))

    def test_no_field_of_the_model_repeats_one_above_it(self):
        self.assertEqual(repeated_fields(ModelPaths(), mirrors=MIRRORS), [])


class DifferingTargetTest(unittest.TestCase):
    def test_a_source_name_sent_to_two_fields_is_found(self):
        rules = {
            'Stage.StagePosX': {'target': 'MechanicalStage.Position.X.Value', 'unit': 'mm'},
            'CameraSettingDefinition.StagePosX': {'target': 'Plane.PositionX', 'unit': 'm'},
            'Stage.X.value': 'Plane.PositionX',
            'Stage.X.units': 'Plane.PositionXUnit',
            'RawStage.Rot.value': 'Plane.RawStage.Rotation',
            'Stage.Rot.value': 'Plane.Rotation',
            'MPP': ['Pixels.PhysicalSizeX', 'Pixels.PhysicalSizeY'],
            'Stage.*': 'MechanicalStage',
            'Beam.*': 'Image.ElectronBeamSettings',
        }
        self.assertEqual(set(differing_targets(rules, mirrors=MIRRORS)), {'stageposx'})

    def test_the_rules_send_each_source_name_to_one_field(self):
        with open(DEFAULT_MAPPINGS_FILE, encoding='utf-8') as file:
            rules = json.load(file)
        differing = differing_targets(rules, mirrors=MIRRORS)
        self.assertEqual({name: sorted(entries) for name, entries in differing.items()
                          if name not in KNOWN_DIFFERING_SOURCE_NAMES}, {})
        self.assertEqual(KNOWN_DIFFERING_SOURCE_NAMES - set(differing), set(),
                         'a known difference is resolved: take it off the list')


if __name__ == '__main__':
    unittest.main()
