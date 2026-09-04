"""
visualisation/demos/bug_log_sg009_demo.py
========================================
SG-009 schematic: making a junction exact destroys the evidence used to find it.

Three panels:

1. Two open polylines cross (strict-interior detector finds the hit).
2. A shared node is inserted at the crossing — the polylines now only *touch*.
3. The same detector returns nothing (tangency is not an interior crossing).

Writes under ``visualisation/output/bug_log_sg009/``:

* ``bug_log_sg009_schematic.png``
* ``bug_log_sg009.json``

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/bug_log_sg009_demo.py --presentation
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

_erp = Path(__file__).resolve().parent / "_ensure_repo_path.py"
_spec = importlib.util.spec_from_file_location("_ensure_repo_path", _erp)
_ensure_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_ensure_mod)
_ensure_mod.ensure_repo_path()

from blade_structure_utilities.geometry_utilities.section_geometry.midlines.ring_geometry import (
    intersect_open_polylines_2d,
)
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


def _crossing_polylines() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Two open polylines that cross at the origin, plus the shared point."""
    horizontal = np.array([[-1.0, 0.0], [1.0, 0.0]], dtype=float)
    diagonal = np.array([[-0.8, -0.8], [0.8, 0.8]], dtype=float)
    shared = np.array([0.0, 0.0], dtype=float)
    return horizontal, diagonal, shared


def _insert_shared_node(poly: np.ndarray, shared: np.ndarray) -> np.ndarray:
    """Insert ``shared`` between the two endpoints (open two-segment polyline)."""
    return np.vstack([poly[0], shared, poly[-1]])


def _draw_panel(
    axis,
    poly_a: np.ndarray,
    poly_b: np.ndarray,
    *,
    title: str,
    hits: list,
    highlight: np.ndarray | None = None,
) -> None:
    axis.plot(poly_a[:, 0], poly_a[:, 1], color=NAVY, lw=2.4, solid_capstyle="round")
    axis.plot(poly_b[:, 0], poly_b[:, 1], color=TEAL, lw=2.4, solid_capstyle="round")
    axis.scatter(poly_a[:, 0], poly_a[:, 1], s=28, c=NAVY, zorder=3)
    axis.scatter(poly_b[:, 0], poly_b[:, 1], s=28, c=TEAL, zorder=3)
    if highlight is not None:
        axis.scatter(
            [highlight[0]],
            [highlight[1]],
            s=90,
            c=RED,
            zorder=4,
            edgecolors=INK,
            linewidths=0.8,
            label="shared node",
        )
    for hit in hits:
        point = np.asarray(hit[4], dtype=float)
        axis.scatter([point[0]], [point[1]], s=70, c=RED, zorder=4, marker="x", linewidths=2.0)
    axis.set_title(title, color=INK, fontsize=12)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlim(-1.25, 1.25)
    axis.set_ylim(-1.05, 1.05)
    axis.tick_params(colors=MUTED)
    for spine in axis.spines.values():
        spine.set_color(MUTED)
    n_hits = len(hits)
    axis.text(
        0.02,
        0.04,
        f"detector hits: {n_hits}",
        transform=axis.transAxes,
        color=RED if n_hits == 0 else NAVY,
        fontsize=11,
        fontweight="bold",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_output_and_presentation_args(parser, default_stem="bug_log_sg009")
    args = parser.parse_args(argv)
    apply_presentation_style(bool(args.presentation))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    horizontal, diagonal, shared = _crossing_polylines()
    hits_before = intersect_open_polylines_2d(horizontal, diagonal)
    touching_a = _insert_shared_node(horizontal, shared)
    touching_b = _insert_shared_node(diagonal, shared)
    hits_after = intersect_open_polylines_2d(touching_a, touching_b)

    # Presentation aspect ~2.5:1 for a full-width slide panel.
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.2))
    _draw_panel(
        axes[0],
        horizontal,
        diagonal,
        title="1 · Crossing polylines",
        hits=hits_before,
    )
    _draw_panel(
        axes[1],
        touching_a,
        touching_b,
        title="2 · Shared node inserted",
        hits=[],
        highlight=shared,
    )
    _draw_panel(
        axes[2],
        touching_a,
        touching_b,
        title="3 · Detector sees nothing",
        hits=hits_after,
        highlight=shared,
    )
    fig.suptitle(
        "SG-009 · Making a junction exact destroys the evidence used to find it",
        color=INK,
        fontsize=13,
        y=0.98,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.92))

    png_path = out_dir / "bug_log_sg009_schematic.png"
    save_figure(fig, png_path, presentation=bool(args.presentation))
    plt.close(fig)
    print(f"Wrote {png_path}")

    payload = {
        "hits_before": len(hits_before),
        "hits_after_shared_node": len(hits_after),
        "oracle": "intersect_web_axis_open_polyline_2d (post-resample)",
        "detector": "intersect_open_polylines_2d (strict interior; tools only)",
        "invariant": (
            "A component must emit its mid-surface at its true extent, "
            "so junctions coincide by construction."
        ),
    }
    json_path = out_dir / "bug_log_sg009.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
