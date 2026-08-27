# figures

Curated PNGs for **tracked** package docs. Demo trees under
`visualisation/output/` are gitignored.

↑ [`docs index`](../README.md) · [`section_geometry`](../../README.md)

## Table of contents

1. [Checked-in assets](#checked-in-assets)
2. [Gallery demo output](#gallery-demo-output)
3. [Regenerate front-door / curated copies](#regenerate-front-door--curated-copies)

---

## Checked-in assets

| Path | Role |
|------|------|
| [`2D-F.png`](2D-F.png) | Package README front-door figure |
| [`structural_systems/`](structural_systems/) | Optional curated copies for tracked docs |

## Gallery demo output

The structural-systems gallery renders from the demo default out-dir (gitignored):

[`../../visualisation/output/structural_family_grids/`](../../visualisation/output/structural_family_grids/)

```bash
python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/structural_family_grids_demo.py
```

Page: [`../structural_systems_gallery.md`](../structural_systems_gallery.md).

## Regenerate front-door / curated copies

To refresh tracked copies under this folder:

```bash
python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/structural_family_grids_demo.py \
  --out-dir blade_structure_utilities/geometry_utilities/section_geometry/docs/figures/structural_systems
```

Front-door `2D-F.png`:

```bash
python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/structural_family_grids_demo.py \
  --keys 2D-F \
  --out-dir blade_structure_utilities/geometry_utilities/section_geometry/docs/figures/structural_systems
# then copy structural_systems/2D-F.png → docs/figures/2D-F.png if needed
```
