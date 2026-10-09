"""Dotted paths into the LinkML master model, as the mapper and its rules use them.

A path starts at a class with an identifier (OME, Image, Laser, ...), which
the exporter can place on its own, and continues through the slots of
components without one: OME.ElectronBeam.WorkingDistance.Value,
Image.ObjectiveSettings.Medium. Every value in the model has one such path,
so the mapper's name matching never sees the same field twice.
"""

import os.path

from linkml_runtime.utils.schemaview import SchemaView

DEFAULT_MODEL_FILE = os.path.join(os.path.dirname(__file__), 'models', 'imaging.yaml')


class ModelPaths:
    def __init__(self, model_filename=DEFAULT_MODEL_FILE):
        # an absolute path, so the model's imports resolve next to it
        self.view = SchemaView(os.path.abspath(model_filename))
        self.classes = self.view.all_classes()
        self._slots = {}
        self.root = next(name for name, cls in self.classes.items() if cls.tree_root)

    def slots(self, class_name):
        if class_name not in self._slots:
            self._slots[class_name] = {slot.name: slot for slot in self.view.class_induced_slots(class_name)}
        return self._slots[class_name]

    def has_identifier(self, class_name):
        return any(slot.identifier for slot in self.slots(class_name).values())

    def default_subtype(self, class_name):
        """The concrete class values for an abstract one go into (GenericDetector for Detector), or None."""
        annotation = (self.classes[class_name].annotations or {}).get('default_subtype')
        return annotation.value if annotation is not None else None

    def is_component(self, class_name):
        cls = self.classes[class_name]
        return not self.has_identifier(class_name) and not cls.abstract and not cls.mixin and class_name != self.root

    def _is_nested(self, slot):
        return slot.range in self.classes and bool(slot.inlined or slot.inlined_as_list)

    def tree(self):
        """{class: {slot: range or subtree}} for every class a path starts at; components are subtrees."""
        starts = [name for name, cls in self.classes.items()
                  if not cls.abstract and not cls.mixin and (name == self.root or self.has_identifier(name))]
        return {name: self._subtree(name, (name,)) for name in starts}

    def _subtree(self, class_name, seen):
        subtree = {}
        for name, slot in self.slots(class_name).items():
            subtypes = self._component_subtypes(slot, seen)
            if subtypes:
                subtree.update({subtype: self._subtree(subtype, seen + (subtype,)) for subtype in subtypes})
            elif not slot.designates_type:
                is_component = self._is_nested(slot) and self.is_component(slot.range) and slot.range not in seen
                subtree[name] = self._subtree(slot.range, seen + (slot.range,)) if is_component \
                    else slot.range or 'string'
        return subtree

    def detector_settings(self):
        """{detector class: the class of its settings for an image}, as LiMi's Model_Settings pairs them
        (PhotoMultiplierTube: PointDetectorSettings)."""
        if 'Detector' not in self.classes:
            return {}
        return {name: self.classes[name].annotations['Model_Settings'].value
                for name in self.view.class_descendants('Detector') if not self.classes[name].abstract}

    def settings_path(self, path):
        """The model path of a detector's settings a rule writes with the detector until the mapper knows
        whether it made the image (GenericDetector.GenericDetectorSettings.LiveTime.Value:
        LightPath.GenericDetectorSettings.LiveTime.Value); any other path as it is."""
        detector, _, rest = path.partition('.')
        settings = self.detector_settings().get(detector)
        return f'LightPath.{rest}' if settings is not None and rest.startswith(f'{settings}.') else path

    def slot_at(self, class_name, name):
        """(slot, class it leads to) for the path segment `name` of `class_name`: the slot of that name, or, for a
        concrete subtype named for itself (LightPath.GenericDetectorSettings), the slot over its abstract class."""
        slots = self.slots(class_name)
        if name in slots:
            slot = slots[name]
            return slot, slot.range if slot.range in self.classes else None
        holding = next((slot for slot in slots.values() if name in self._component_subtypes(slot, ())), None)
        return holding, name if holding is not None else None

    def _component_subtypes(self, slot, seen):
        """The concrete components a nested slot over an abstract class holds (LightPath.DetectorSettings:
        GenericDetectorSettings, PointDetectorSettings, ...), each written under its own name, as in the
        profile."""
        cls = self.classes.get(slot.range)
        if cls is None or not cls.abstract or not self._is_nested(slot):
            return []
        return [name for name in self.view.class_descendants(slot.range, reflexive=False)
                if self.is_component(name) and name not in seen]

    def aliases(self):
        """{Detector.Name: GenericDetector.Name, ...}: an abstract class's paths, for its default subtype."""
        tree = self.tree()
        aliases = {}
        for name, cls in self.classes.items():
            default = self.default_subtype(name) if cls.abstract else None
            if default in tree:
                aliases.update({f'{name}{path[len(default):]}': path for path in _leaf_paths(tree[default], default)})
        return aliases

    def spellings(self):
        """{enumeration: {alias: value}} for each enumeration whose values have other spellings ("um" for "µm",
        Leica's "OIL" for Oil)."""
        return {name: {alias: value for value, spec in enum.permissible_values.items() for alias in spec.aliases}
                for name, enum in self.view.all_enums().items()
                if any(spec.aliases for spec in enum.permissible_values.values())}

    def parents(self, class_name):
        """(class, slot) pairs nesting `class_name` directly."""
        return [(owner, name) for owner, cls in self.classes.items() if not cls.mixin and not cls.abstract
                for name, slot in self.slots(owner).items() if slot.range == class_name and self._is_nested(slot)]

    def canonical(self, class_path):
        """The path of `Class.slot...`: an abstract class replaced by its default subtype, and a component
        prefixed with the path of the class nesting it. None where that is not unique."""
        parts = class_path.split('.')
        first = parts[0]
        if first in self.classes and self.classes[first].abstract:
            first = self.default_subtype(first)
        if first is None or first not in self.classes:
            return None
        if not self.is_component(first):
            return self._from_last_start([first] + parts[1:])
        parents = self.parents(first)
        if len(parents) != 1:
            return None
        owner, slot_name = parents[0]
        return self.canonical('.'.join([owner, slot_name] + parts[1:]))

    def _from_last_start(self, parts):
        """Image.Pixels.SizeX -> Pixels.SizeX: a path restarts at every class with an identifier it passes."""
        start, current = 0, parts[0]
        for index, name in enumerate(parts[1:], start=1):
            slot = self.slots(current).get(name) if current else None
            current = slot.range if slot is not None and slot.range in self.classes else None
            if current is not None and self._is_nested(slot) and not self.is_component(current) \
                    and index < len(parts) - 1:
                start = index
        path = parts[start:]
        if start:
            path[0] = self.slots(self._class_at(parts[:start]))[parts[start]].range
        return '.'.join(path)

    def _class_at(self, parts):
        current = parts[0]
        for name in parts[1:]:
            current = self.slots(current)[name].range
        return current


def _leaf_paths(tree, path):
    for key, value in tree.items():
        current = f'{path}.{key}'
        if isinstance(value, dict) and value:
            yield from _leaf_paths(value, current)
        else:
            yield current
