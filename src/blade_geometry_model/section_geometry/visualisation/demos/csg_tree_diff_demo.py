"""
visualisation/demos/csg_tree_diff_demo.py
=========================================
Diff two design vectors by comparing their CSG expression trees.

Builds two sections (same layout, different thicknesses by default), draws
each region's tree side by side for a chosen label, and colours nodes as
unchanged / changed / added-removed. Reuses layout_tree helpers from
csg_expression_tree_demo.py.

Writes under visualisation/output/csg_tree_diff/:

* csg_tree_diff.png
* csg_tree_diff.json

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/csg_tree_diff_demo.py --presentation
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

_erp = Path(__file__).resolve().parent / "_ensure_repo_path.py"
_spec = importlib.util.spec_from_file_location("_ensure_repo_path", _erp)
_ensure_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_ensure_mod)
_ensure_mod.ensure_repo_path()

_tree = importlib.util.spec_from_file_location(
    "csg_expression_tree_demo",
    Path(__file__).resolve().parent / "csg_expression_tree_demo.py",
)
_tree_mod = importlib.util.module_from_spec(_tree)
assert _tree.loader is not None
_tree.loader.exec_module(_tree_mod)

child_expressions = _tree_mod.child_expressions
collect_unique = _tree_mod.collect_unique
count_nodes = _tree_mod.count_nodes
layout_tree = _tree_mod.layout_tree
node_caption = _tree_mod.node_caption
scalar_parameters = _tree_mod.scalar_parameters

from blade_structure_utilities.geometry_utilities.section_geometry import (
    AirfoilSDF,
    build_section_view,
    resolve_system_type,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.ir import Expr
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.figure_io import (
    add_output_and_presentation_args,
    apply_presentation_style,
    save_figure,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.palette import (
    INK,
    MUTED,
    NAVY,
    RED,
    TEAL,
)

_UNCHANGED = "#6b7280"
_ADDED = TEAL
_REMOVED = NAVY


def _to_key(label) -> str:
    return str(getattr(label, "value", label))


def _expr_signature(node: Expr) -> tuple:
    name = type(node).__name__
    parameters = tuple(sorted(scalar_parameters(node).items()))
    children = tuple(_expr_signature(child) for _, child in child_expressions(node))
    return (name, parameters, children)


def _classify_nodes(left: Expr, right: Expr) -> dict[str, set[Expr]]:
    left_nodes: set[Expr] = set()
    right_nodes: set[Expr] = set()
    collect_unique(left, left_nodes)
    collect_unique(right, right_nodes)
    left_by_sig = {_expr_signature(node): node for node in left_nodes}
    right_by_sig = {_expr_signature(node): node for node in right_nodes}
    shared_sigs = set(left_by_sig) & set(right_by_sig)
    only_left = {left_by_sig[sig] for sig in set(left_by_sig) - shared_sigs}
    only_right = {right_by_sig[sig] for sig in set(right_by_sig) - shared_sigs}
    unchanged = {left_by_sig[sig] for sig in shared_sigs}
    return {
        "unchanged": unchanged,
        "removed": only_left,
        "added": only_right,
    }


def _draw_coloured_tree(axis, root: Expr, colours: dict[Expr, str], title: str) -> None:
    positions, edges = layout_tree(root)
    for parent_id, child_id in edges:
        x0, y0, _, _ = positions[parent_id]
        x1, y1, _, _ = positions[child_id]
        axis.plot([x0, x1], [y0, y1], color=MUTED, lw=0.9, zorder=1)
    for _, (x_position, y_position, node, _) in positions.items():
        colour = colours.get(node, _UNCHANGED)
        caption = node_caption(node).split("\n")[0]
        box = FancyBboxPatch(
            (x_position - 0.38, y_position - 0.16),
            0.76,
            0.32,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            linewidth=1.0,
            edgecolor=INK,
            facecolor=colour,
            alpha=0.85,
            zorder=2,
        )
        axis.add_patch(box)
        axis.text(
            x_position,
            y_position,
            caption,
            ha="center",
            va="center",
            fontsize=6.5,
            color="white",
            zorder=3,
        )
    axis.set_title(title, color=INK, fontsize=11)
    axis.set_axis_off()
    xs = [pos[0] for pos in positions.values()]
    ys = [pos[1] for pos in positions.values()]
    if xs and ys:
        axis.set_xlim(min(xs) - 0.8, max(xs) + 0.8)
        axis.set_ylim(min(ys) - 0.6, max(ys) + 0.6)


def _region_expr(section, label: str) -> Expr:
    label_keys = [_to_key(key) for key in section]
    if label not in label_keys:
        raise SystemExit(f'Label {label!r} not found; have {label_keys}')
    return section[label].expr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_output_and_presentation_args(parser, default_stem="csg_tree_diff")
    parser.add_argument("--layout", default="2D-F")
    parser.add_argument("--label", default="shear_web_0")
    parser.add_argument("--skin-a", type=float, default=0.004)
    parser.add_argument("--skin-b", type=float, default=0.010)
    parser.add_argument("--cap-a", type=float, default=0.012)
    parser.add_argument("--cap-b", type=float, default=0.012)
    parser.add_argument("--web-a", type=float, default=0.005)
    parser.add_argument("--web-b", type=float, default=0.008)
    args = parser.parse_args(argv)
    apply_presentation_style(bool(args.presentation))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    airfoil = AirfoilSDF.from_naca("2412", chord=1.0, n_points=160)
    layout = resolve_system_type(str(args.layout))
    section_a = build_section_view(
        airfoil,
        layout,
        skin_thickness=float(args.skin_a),
        spar_cap_thickness=float(args.cap_a),
        shear_web_thickness=float(args.web_a),
    )
    section_b = build_section_view(
        airfoil,
        layout,
        skin_thickness=float(args.skin_b),
        spar_cap_thickness=float(args.cap_b),
        shear_web_thickness=float(args.web_b),
    )
    left = _region_expr(section_a, str(args.label))
    right = _region_expr(section_b, str(args.label))
    classes = _classify_nodes(left, right)

    left_colours = {node: _UNCHANGED for node in classes["unchanged"]}
    left_colours.update({node: _REMOVED for node in classes["removed"]})
    right_colours = {node: _UNCHANGED for node in classes["unchanged"]}
    right_colours.update({node: _ADDED for node in classes["added"]})

    left_unique: set[Expr] = set()
    right_unique: set[Expr] = set()
    collect_unique(left, left_unique)
    collect_unique(right, right_unique)
    shared_count = len(classes["unchanged"])
    differ_count = len(classes["removed"]) + len(classes["added"])

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    _draw_coloured_tree(
        axes[0],
        left,
        left_colours,
        title=(
            f"A skin={args.skin_a * 1e3:.0f} mm web={args.web_a * 1e3:.0f} mm "
            f"({args.label})"
        ),
    )
    _draw_coloured_tree(
        axes[1],
        right,
        right_colours,
        title=(
            f"B skin={args.skin_b * 1e3:.0f} mm web={args.web_b * 1e3:.0f} mm "
            f"({args.label})"
        ),
    )
    fig.suptitle(
        f"CSG tree diff  A={len(left_unique)}  B={len(right_unique)}  "
        f"shared={shared_count}  differ={differ_count}",
        color=INK,
        fontsize=12,
    )
    fig.text(
        0.5,
        0.02,
        "grey = unchanged signature; navy = only in A; teal = only in B",
        ha="center",
        color=MUTED,
        fontsize=9,
    )
    fig.tight_layout(rect=(0.0, 0.05, 1.0, 0.92))

    png_path = out_dir / "csg_tree_diff.png"
    save_figure(fig, png_path, presentation=bool(args.presentation))
    plt.close(fig)
    print(f"Wrote {png_path}")

    payload = {
        "layout": str(args.layout),
        "label": str(args.label),
        "design_a": {
            "skin_thickness": float(args.skin_a),
            "spar_cap_thickness": float(args.cap_a),
            "shear_web_thickness": float(args.web_a),
            "node_visits": count_nodes(left),
            "unique_nodes": len(left_unique),
        },
        "design_b": {
            "skin_thickness": float(args.skin_b),
            "spar_cap_thickness": float(args.cap_b),
            "shear_web_thickness": float(args.web_b),
            "node_visits": count_nodes(right),
            "unique_nodes": len(right_unique),
        },
        "shared_nodes": shared_count,
        "differing_nodes": differ_count,
        "removed_only_in_a": len(classes["removed"]),
        "added_only_in_b": len(classes["added"]),
    }
    json_path = out_dir / "csg_tree_diff.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
