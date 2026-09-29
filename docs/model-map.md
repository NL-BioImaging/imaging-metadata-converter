# Model map

One picture of what the converter actually produces: every field a mapping
rule targets, shown under the groups that hold it, with each top-level section
as its own block. <span class="map-key">Orange</span> marks a path LiMi does
not have — one the imaging model adds in `imaging_extension.yaml` or
`imaging_provenance.yaml` — so the map also shows how much of the converter's
output comes from those extensions, mostly electron microscopy, rather than
from LiMi. LiMi's own paths stay a quiet grey.

<div class="map-legend" markdown>
<span><i class="gext"></i> extension group</span>
<span><i class="fext"></i> extension field</span>
<span><i class="gbase"></i> LiMi group</span>
<span><i class="fbase"></i> LiMi field</span>
</div>

A path counts as an extension as soon as it runs through an added class or
slot, so every field under `Image.ElectronBeamSettings` is orange, and so is
`Instrument.Manufacturer`, which LiMi's `Instrument` does not have.

{{ model.map }}

## Keeping this page in sync

The map is drawn when the site is built, by the MkDocs hook
`scripts/docs_data.py` (with `scripts/model_map.py`), from the packaged
mappings and model files. It is never stored, so it cannot disagree with
them: an edited `mappings.json` or a new model shows up on the next build.
