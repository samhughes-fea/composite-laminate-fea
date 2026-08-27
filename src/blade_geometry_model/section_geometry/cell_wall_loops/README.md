# cell_wall_loops — cell-wall loops

↑ [`section_geometry`](../README.md)

Builds closed wall loops around each inter-web cell from topology-prepared
skin and web centrelines (`CellWallLoop` in
[`section_contract`](../../section_contract/README.md)); spar caps are ignored.
With `n` webs the usual count is `n + 1` (one loop if `n = 0`).

**Naming.** Product gate and result field: `cell_wall_loops`. Implementation
files may still be named `void_cell_*` (historical) — not a second public API.

## Table of contents

1. [Organisation](#organisation)
2. [API](#api)
3. [Usage in the package](#usage-in-the-package)
4. [See also](#see-also)

---

## Organisation

| File | Role |
|------|------|
| `void_cell_wall_loops.py` | `build_void_cell_wall_loops` |
| `void_cell_loop_builders.py` | Loop construction |
| `void_cell_web_attach.py` | Attach webs to the skin ring |
| `void_cell_wall_geom.py` | Arc / geometry helpers |

```mermaid
flowchart LR
  Gate["outputs cell_wall_loops"] --> Build[build_void_cell_wall_loops]
  Build --> Impl["void_cell_* modules"]
  Impl --> DTO[CellWallLoop]
  DTO --> Field[result.cell_wall_loops]
```

## API

| Name | File | Role |
|------|------|------|
| `build_void_cell_wall_loops` | `void_cell_wall_loops.py` | Strips → loops |

Raises `ValueError` if the skin ring is too short.

`CellWallLoop` fields (`id`, `polyline_twisted_pitch_axis_blade_frame`,
`area_m2`, …) are summarised in
[`../README.md` § Results](../README.md#cellwallloop-from-section_contract).

## Usage in the package

Gated by `outputs` including `"cell_wall_loops"`, which implies midline
extraction. Result field is always `cell_wall_loops`. Prefer
topology-prepared strips as input.

## See also

- [`../topology/`](../topology/README.md)
- [`../../section_contract/`](../../section_contract/README.md)
