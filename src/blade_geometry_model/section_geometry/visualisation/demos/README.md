# visualisation demos — run list

Demo scripts for `section_geometry` products. Outputs:
[`../output/`](../output/) (gitignored). Run from the repository root.

Teaching scripts (print-first, few flags):
[`../../examples/`](../../examples/README.md).

↑ [`section_geometry`](../../README.md) ·
[`../README.md`](../README.md)

```bash
python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/<script>.py
```

## Table of contents

1. [Newcomer path](#newcomer-path)
2. [Scripts](#scripts)
3. [Helpers (not demos)](#helpers-not-demos)

---

## Newcomer path

Run these first (from the repository root):

1. [`naca2412_section.py`](naca2412_section.py) — one twin-web station
2. [`structural_family_grids_demo.py`](structural_family_grids_demo.py) — all 40 layout keys
3. [`shell_junction_topology_demo.py`](shell_junction_topology_demo.py) — junction snap
4. [`void_cell_wall_loops_demo.py`](void_cell_wall_loops_demo.py) — cell-wall loops

Checked-in gallery:
[`../../docs/reference/structural_systems_gallery.md`](../../docs/reference/structural_systems_gallery.md).

## Scripts

| Script | What it draws |
|--------|----------------|
| [`naca2412_section.py`](naca2412_section.py) | Twin-web section and twisted box examples |
| [`geometry_from_design_vector.py`](geometry_from_design_vector.py) | Build/plot from thicknesses + layout (families A–D) |
| [`structural_family_grids_demo.py`](structural_family_grids_demo.py) | One PNG per layout id → `../output/structural_family_grids/`; gallery: [`../../docs/reference/structural_systems_gallery.md`](../../docs/reference/structural_systems_gallery.md) |
| [`section_centerline_geometry_taxonomy.py`](section_centerline_geometry_taxonomy.py) | Per-label SDF panels for layout keys |
| [`system_types_twist_grid.py`](system_types_twist_grid.py) | Layout grids at fixed twist |
| [`spanwise_web_anchors.py`](spanwise_web_anchors.py) | Root-anchored vs per-station web positions |
| [`feature_flythroughs.py`](feature_flythroughs.py) | Reusable GIF fly-through pipeline (6 engineering scenarios) |
| [`skin_ss_ps_taxonomy_demo.py`](skin_ss_ps_taxonomy_demo.py) | Upper/lower skin solids and midline arcs |
| [`shell_junction_topology_demo.py`](shell_junction_topology_demo.py) | Junction snap before/after |
| [`sg009_axis_cap_junction_spike.py`](sg009_axis_cap_junction_spike.py) | SG-009 offline: axis x cap oracle vs production shared nodes |
| [`void_cell_wall_loops_demo.py`](void_cell_wall_loops_demo.py) | Closed cell loops for 0–5 webs |
| [`topology_twist_stability_demo.py`](topology_twist_stability_demo.py) | Junction gaps vs twist |
| [`dual_rep_consistency_demo.py`](dual_rep_consistency_demo.py) | Polygon boundary vs SDF contour |
| [`le_te_exactness_demo.py`](le_te_exactness_demo.py) | Skin midline vs aerofoil tip |
| [`le_te_insert_residual_demo.py`](le_te_insert_residual_demo.py) | LE/TE inserts on the SDF path |
| [`sdf_metric_quality_demo.py`](sdf_metric_quality_demo.py) | SDF gradient quality fields |
| [`thin_feature_robustness_demo.py`](thin_feature_robustness_demo.py) | Thin webs under twist |
| [`section_properties_dashboard.py`](section_properties_dashboard.py) | Per-label area / inertia dashboard |
| [`props_cost_demo.py`](props_cost_demo.py) | Hybrid vs quadtree vs grid cost |
| [`quadtree_union_mesh.py`](quadtree_union_mesh.py) | Shared union quadtree meshes |
| [`quadtree_convergence_study.py`](quadtree_convergence_study.py) | Quadtree depth vs dense-grid reference |
| [`quadtree_vs_shoelace_convergence_study.py`](quadtree_vs_shoelace_convergence_study.py) | Polygon vs quadtree accuracy–cost |
| [`constructive_vs_quadtree_spike.py`](constructive_vs_quadtree_spike.py) | Console comparison (stdout) |
| [`manystation_bench.py`](manystation_bench.py) | Throughput across many stations |
| [`csg_provenance_demo.py`](csg_provenance_demo.py) | Winner-label / nearest-interface / ambiguity maps |
| [`robustness_monte_carlo_demo.py`](robustness_monte_carlo_demo.py) | Randomized thickness+twist robustness sweep |
| [`sensitivity_dashboard_demo.py`](sensitivity_dashboard_demo.py) | Finite-difference sensitivities and local sweeps |

## Implicit-geometry capability set

Written for presenting the package: these four cover the implicit machinery
itself rather than the blade product built on top of it.

| Script | What it draws |
|--------|----------------|
| [`csg_expression_tree_demo.py`](csg_expression_tree_demo.py) | The `Expr` tree behind one region, the field emerging operator by operator, and the shared-node census |
| [`sdf_operator_algebra_demo.py`](sdf_operator_algebra_demo.py) | Every IR operator as one line of numpy; plus a clearly-labelled panel of kernel-only smooth/blend operators no blade recipe uses |
| [`thickness_as_field_offset_demo.py`](thickness_as_field_offset_demo.py) | Gauge sweep through one unchanged tree, and where `Offset` stops being a true offset (Eikonal residual) |
| [`evaluation_cost_pruning_demo.py`](evaluation_cost_pruning_demo.py) | Shared-subtree memoisation, `expr_bbox` support culling, and cost scaling |
| [`geometry_to_mesh_flythrough.py`](geometry_to_mesh_flythrough.py) | **Animated**: solids → raw midlines → junction-prepared strips → Q4 shell mesh, diving into a web–skin junction. Also writes a static four-stage strip. |

Suggested order when presenting: expression tree → operator algebra →
thickness-as-offset → evaluation cost → geometry-to-mesh fly-through
(the fly-through is the natural closer: it is what the representation is *for*).

The fly-through needs ImageMagick (`magick`) on PATH; pass `--no-gif` to render
frames and the static strip only. `--max-frames N` gives a fast preview.

### Pipeline stages, and the one that is easy to get wrong

Stages 2 and 3 are both "midlines" and are commonly conflated. The distinction
that matters:

| | Produced by | Endpoints |
|---|---|---|
| **Raw** | `midlines.build_shell_midline_strips` | free — a web foot lands part-way along a skin segment, with no node there to share |
| **Prepared** | `topology.build_shell_strip_topology` | split and merged — the skin arc is cut at the foot, so the web endpoint coincides exactly with a skin node |

Meshing consumes the **prepared** form only, and
`SectionGeometryResult.midline_strips` is already prepared — the raw form has to
be rebuilt from the section host to show the difference.

## Helpers (not demos)

- [`_ensure_repo_path.py`](_ensure_repo_path.py) — put repo root on `sys.path`
- [`_taxonomy_cases.py`](_taxonomy_cases.py) — shared twist/aerofoil helpers
- [`void_cell_wall_loops_case_payload.py`](void_cell_wall_loops_case_payload.py) — JSON payload helper

Mesh strip demos live under
[`section_mesh/visualisation/demos/`](../../../../mesh_utilities/section_mesh/visualisation/demos/).

Dual-rep acceptance narrative:
[`../../docs/reports/DUAL_REP_ACCEPTANCE.md`](../../docs/reports/DUAL_REP_ACCEPTANCE.md).

### Plot debug tracing

Set `SECTION_GEOMETRY_PLOT_DEBUG=1` to capture structured summaries of data passed
to Matplotlib calls (`plot`, `contourf`, `pcolormesh`, `scatter`, etc.) for any
demo script.

- Default log dir: `../output/_plot_debug/`
- One JSONL per run (includes plot-call payload summaries and `savefig` metadata)
- Optional overrides:
  - `SECTION_GEOMETRY_PLOT_DEBUG_DIR`
  - `SECTION_GEOMETRY_PLOT_DEBUG_TAG`

