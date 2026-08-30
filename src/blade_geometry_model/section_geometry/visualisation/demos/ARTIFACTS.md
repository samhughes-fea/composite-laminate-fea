# Visualisation artefacts (regen index)

Figures under [`../output/`](../output/) are **gitignored**. Regenerate locally
before previewing docs that embed them.

? [`demos README`](README.md) ? [`section_geometry`](../../README.md)

## Regen gallery + anatomy

From the repository root:

```bash
python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/structural_family_grids_demo.py
python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/anatomy_2d_f_demo.py
```

- Gallery tiles (legend-less): `../output/structural_family_grids/{key}.png`
- Labelled anatomy: `../output/anatomy_2d_f/2D-F_labelled.png`

Shared save helpers: [`../figure_io.py`](../figure_io.py) (`save_figure`,
`demo_output_dir`, `--presentation`).

## Artefact map

| Output path (under `visualisation/output/`) | Demo | Purpose |
|---|---|---|
| `structural_family_grids/` | `structural_family_grids_demo.py` | All 40 layout keys (gallery) |
| `anatomy_2d_f/` | `anatomy_2d_f_demo.py` | Labelled `2D-F` teaching figure |
| `naca2412_section/` | `naca2412_section.py` | Twin-web + torsion-box intro |
| `shell_junction_topology/` | `shell_junction_topology_demo.py` | Raw vs prepared midlines |
| `void_cell_wall_loops/` | `void_cell_wall_loops_demo.py` | Closed cell-wall loops |
| `geometry_to_mesh/` | `geometry_to_mesh_flythrough.py` | Solids ? midlines ? mesh stages |
| `dual_rep_consistency/` | `dual_rep_consistency_demo.py` | Polygon vs SDF boundary |
| `le_te_exactness/` | `le_te_exactness_demo.py` | Skin midline vs aerofoil tip |
| `le_trailing_edge_insert_residual/` | `le_te_insert_residual_demo.py` | LE/TE inserts on SDF path |
| `topology_twist_stability/` | `topology_twist_stability_demo.py` | Junction gaps vs twist |
| `thin_feature_robustness/` | `thin_feature_robustness_demo.py` | Thin webs under twist |
| `csg_expression_tree/` | `csg_expression_tree_demo.py` | Expr tree / shared nodes |
| `sdf_operator_algebra/` | `sdf_operator_algebra_demo.py` | IR operator gallery |
| `thickness_as_field_offset/` | `thickness_as_field_offset_demo.py` | Offset / Eikonal residual |
| `evaluation_cost_pruning/` | `evaluation_cost_pruning_demo.py` | Memoisation / bbox cull |
| `quadtree_union/` | `quadtree_union_mesh.py` | Union quadtree meshes |
| `quadtree_convergence/` | `quadtree_convergence_study.py` | Depth vs dense grid |
| `props_cost/` | `props_cost_demo.py` | Hybrid vs quadtree cost |
| `section_properties_dashboard/` | `section_properties_dashboard.py` | Area / inertia panels |
| `flythroughs/` / `gifs/` | `feature_flythroughs.py` | Scenario GIFs |

Stdout-only (no figures): `constructive_vs_quadtree_spike.py`,
`sg009_axis_cap_junction_spike.py` (numeric oracle report).
