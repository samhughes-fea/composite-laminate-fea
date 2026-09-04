"""
visualisation/demos/dual_rep_consistency_demo.py
=====================================
Computational-geometry demo: constructive vs residual-φ consistency.

Hybrid properties use constructive wall-solid polygons for skin/web/cap and
residual φ (adaptive quadtree) for LE/TE inserts. This demo overlays both
boundaries and reports measurable gap / area metrics.

Writes:

* ``dual_rep_boundary_overlay.png`` — constructive exterior vs φ=0 for wall solids
* ``dual_rep_residual_inserts.png`` — insert φ heatmaps + constructive skin
* ``dual_rep_consistency.json`` — max/mean gaps and area deltas

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/dual_rep_consistency_demo.py
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

from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.figure_io import (
    DEFAULT_DPI,
    demo_output_dir,
    save_figure,
)

from blade_structure_utilities.geometry_utilities.section_geometry import (
    AirfoilSDF,
    MultiCellSection,
    SDFGrid,
)
from blade_structure_utilities.geometry_utilities.section_geometry.constructive import (
    emit_wall_solid_polygons,
    is_residual_label,
)
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_backend import (
    quadtree_spec_for_airfoil,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot import (
    plot_section_hybrid,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot_sdf import (
    plot_sdf_field,
)
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_compute import (
    compute_section_properties,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf import offset

_DPI = DEFAULT_DPI
_SKIN_T = 0.003
_COMPARE_LABELS = ("skin_suction_surface", "skin_pressure_surface", "shear_web_0", "spar_cap_suction_surface")


def _build_section(af: AirfoilSDF) -> MultiCellSection:
    return MultiCellSection.twin_web(
        af,
        x_fore=0.20,
        x_aft=0.50,
        skin_thickness=_SKIN_T,
        web_thickness=0.004,
        cap_height=(0.014, 0.012),
        web_alignment="chord_normal",
        twist_angle=0.0,
        trailing_edge_insert_x_m=0.75,
        leading_edge_insert_x_m=0.10,
        core_enabled=True,
    )


def _ring_from_geom(geom) -> np.ndarray:
    g = geom
    if hasattr(g, "geoms"):
        g = max(g.geoms, key=lambda x: x.area)
    ring = np.asarray(g.exterior.coords, dtype=float)
    if ring.shape[0] > 1 and np.hypot(*(ring[0] - ring[-1])) < 1e-15:
        ring = ring[:-1]
    return ring


def _point_to_segments_gap(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Exact point-to-polyline segment distances for a modest point set."""
    if pts.shape[0] == 0 or poly.shape[0] < 2:
        return np.zeros(0, dtype=float)
    a = poly[:-1]
    b = poly[1:]
    ab = b - a
    l2 = np.sum(ab * ab, axis=1) + 1e-30
    out = np.empty(pts.shape[0], dtype=float)
    for i, p in enumerate(pts):
        t = np.clip(np.sum((p - a) * ab, axis=1) / l2, 0.0, 1.0)
        proj = a + t[:, None] * ab
        out[i] = float(np.min(np.linalg.norm(p - proj, axis=1)))
    return out


def _per_point_gap(constructive_ring: np.ndarray, zero_contours: list[np.ndarray]):
    """Gap at each sampled ring point, against normalised arc length round the ring.

    Overlaying the two boundaries shows only that they coincide. Walking the gap
    round the ring shows *where* they part company and by how much.
    """
    ring = np.asarray(constructive_ring, dtype=float)
    step = max(1, ring.shape[0] // 120)
    samples = ring[::step]
    gaps = [
        _point_to_segments_gap(samples, cont)
        for cont in zero_contours
        if cont.shape[0] >= 2
    ]
    if samples.shape[0] == 0 or not gaps:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=float), samples

    per_point = np.min(np.stack(gaps, axis=0), axis=0)
    step_lengths = np.linalg.norm(np.diff(samples, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(step_lengths)])
    total = float(arc[-1]) if arc[-1] > 0.0 else 1.0
    return arc / total, per_point, samples


def _gap_metrics(constructive_ring: np.ndarray, zero_contours: list[np.ndarray]) -> dict:
    _, per_point, samples = _per_point_gap(constructive_ring, zero_contours)
    if per_point.size == 0:
        return {
            "max_gap_m": float("nan"),
            "mean_gap_m": float("nan"),
            "n_sample": int(samples.shape[0]) if samples.size else 0,
            "n_zero_polylines": len(zero_contours),
        }
    return {
        "max_gap_m": float(np.max(per_point)),
        "mean_gap_m": float(np.mean(per_point)),
        "n_sample": int(samples.shape[0]),
        "n_zero_polylines": len(zero_contours),
    }


def _save_fig(fig, path: Path) -> None:
    fig.tight_layout()
    save_figure(fig, path)
    plt.close(fig)
    print(f"Wrote {path}")


def main(argv: list[str] | None = None) -> Path:
    default_out = Path(__file__).resolve().parents[1] / "output" / "dual_rep_consistency"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=default_out)
    args = parser.parse_args(argv)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    af = AirfoilSDF.from_naca("2412", chord=1.0, n_points=140)
    section = _build_section(af)
    grid = SDFGrid.from_airfoil(af, padding=0.06, nx=480, ny=220)
    polys = emit_wall_solid_polygons(section)

    fig, axes = plt.subplots(2, 2, figsize=(12.0, 8.0))
    metrics: dict[str, dict] = {}
    residual_tracks: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ax, label in zip(axes.ravel(), _COMPARE_LABELS):
        geom = polys[label]
        ring = _ring_from_geom(geom)
        phi = grid.eval(section[label])
        zero = grid.zero_contour(phi)
        arc, per_point, _ = _per_point_gap(ring, zero)
        residual_tracks[label] = (arc, per_point)
        ax.plot(ring[:, 0], ring[:, 1], color="#1565C0", lw=1.8, label="constructive")
        for i, cont in enumerate(zero):
            ax.plot(
                cont[:, 0],
                cont[:, 1],
                color="#E53935",
                lw=1.1,
                ls="--",
                label="φ=0 contour" if i == 0 else None,
            )
        g = _gap_metrics(ring, zero)
        a_c = float(geom.area)
        a_g = float(grid.area(phi))
        metrics[label] = {
            **g,
            "area_constructive_m2": a_c,
            "area_grid_phi_m2": a_g,
            "area_delta_m2": a_g - a_c,
            "area_rel_err": abs(a_g - a_c) / max(a_c, 1e-30),
        }
        ax.set_title(
            f"{label}\nmax gap={g['max_gap_m']:.2e} m  "
            f"ΔA/A={metrics[label]['area_rel_err']:.2e}",
            fontsize=9,
        )
        ax.legend(fontsize=7, loc="best")
        ax.grid(True, alpha=0.3)
        from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot_section import (
            apply_structural_section_axes,
        )

        apply_structural_section_axes(ax)
    fig.suptitle(
        "Dual-rep consistency — constructive exterior vs dense-grid φ=0",
        fontsize=12,
    )
    _save_fig(fig, out_dir / "dual_rep_boundary_overlay.png")

    # --- Where the two representations actually part company ---
    # The overlay above is deliberately dull: the curves sit on top of each other.
    # Walk the gap round each ring instead, and the sampling cell explains it.
    half_cell = 0.5 * float(max(grid.dx, grid.dy))
    fig_r, (ax_track, ax_area) = plt.subplots(1, 2, figsize=(13.0, 4.8))
    track_colours = {
        "skin_suction_surface": "#1565C0",
        "skin_pressure_surface": "#42A5F5",
        "shear_web_0": "#2E7D32",
        "spar_cap_suction_surface": "#E53935",
    }
    for label in _COMPARE_LABELS:
        arc, per_point = residual_tracks.get(label, (np.zeros(0), np.zeros(0)))
        if per_point.size == 0:
            continue
        ax_track.semilogy(
            arc,
            np.maximum(per_point, 1e-9) * 1e3,
            lw=1.6,
            color=track_colours.get(label, "#607D8B"),
            label=label,
        )
    ax_track.axhline(
        half_cell * 1e3,
        color="0.35",
        ls="--",
        lw=1.6,
        label=f"half a grid cell ({half_cell * 1e3:.2f} mm)",
    )
    ax_track.set_xlabel("normalised arc length round the region boundary")
    ax_track.set_ylabel("gap: constructive to φ=0  [mm]")
    ax_track.set_title("The disagreement is bounded by the sampling cell")
    ax_track.grid(True, which="both", alpha=0.3)
    ax_track.legend(fontsize=7, loc="lower right")

    # Relative area error against how thin the region is. The web is the outlier
    # not because the field is wrong but because the feature is 4 mm across.
    widths_mm, rel_errs, names = [], [], []
    for label in _COMPARE_LABELS:
        m = metrics.get(label)
        if not m or not np.isfinite(m["area_rel_err"]):
            continue
        ring = _ring_from_geom(polys[label])
        extent = ring.max(axis=0) - ring.min(axis=0)
        widths_mm.append(float(np.min(extent)) * 1e3)
        rel_errs.append(float(m["area_rel_err"]))
        names.append(label)
    if widths_mm:
        ax_area.loglog(widths_mm, rel_errs, "o", ms=10, color="#6A1B9A")
        for w, e, n in zip(widths_mm, rel_errs, names):
            ax_area.annotate(
                n.replace("_surface", "").replace("_", " "),
                xy=(w, e),
                xytext=(6, 4),
                textcoords="offset points",
                fontsize=8,
            )
        ax_area.set_xlabel("narrowest extent of the region [mm]")
        ax_area.set_ylabel("relative area error  ΔA / A")
        ax_area.set_title("Thin features are where a sampled area stops being usable")
        ax_area.grid(True, which="both", alpha=0.3)

    fig_r.suptitle(
        "Two representations: where they agree, and exactly where they do not",
        fontsize=12,
    )
    _save_fig(fig_r, out_dir / "dual_rep_residual_track.png")

    # Residual inserts on hybrid mesh.
    spec = quadtree_spec_for_airfoil(af, chord=1.0, max_depth=7, max_cells=120000)
    props, meta, mesh = compute_section_properties(
        section,
        backend="hybrid",
        quadtree_spec=spec,
        airfoil_for_spec=af,
        with_mesh=True,
    )
    assert mesh is not None

    fig2, axes2 = plt.subplots(1, 3, figsize=(14.0, 4.5))
    plot_section_hybrid(
        section,
        residual_mesh=mesh,
        ax=axes2[0],
        title="Hybrid: constructive wall solids + residual inserts",
        show_legend=True,
    )
    # Inner-skin reference (insert flush interface).
    phi_inner = grid.eval(offset(af, -_SKIN_T))
    axes2[0].contour(
        grid.X,
        grid.Y,
        phi_inner,
        levels=[0.0],
        colors=["#111111"],
        linewidths=1.0,
        linestyles=["--"],
        zorder=20,
    )

    residual_areas: dict[str, float] = {}
    for ax, lab in zip(axes2[1:], ("leading_edge_insert", "trailing_edge_insert")):
        if lab not in section:
            ax.set_title(f"{lab} missing")
            ax.axis("off")
            continue
        phi = grid.eval(section[lab])
        plot_sdf_field(phi, grid, ax=ax, title=f"{lab} residual φ", vmax=0.03)
        residual_areas[lab] = float(props.get(lab, {}).get("area", float("nan")))
        # Zoom
        inside = phi < 0
        if np.any(inside):
            xs = grid.X[inside]
            ys = grid.Y[inside]
            pad = 0.03
            ax.set_xlim(float(xs.min()) - pad, float(xs.max()) + pad)
            ax.set_ylim(float(ys.min()) - pad, float(ys.max()) + pad)
    fig2.suptitle("Residual-φ consumers (LE/TE inserts) on hybrid path", fontsize=11)
    _save_fig(fig2, out_dir / "dual_rep_residual_inserts.png")

    max_gap = max(
        (m["max_gap_m"] for m in metrics.values() if np.isfinite(m["max_gap_m"])),
        default=float("nan"),
    )
    payload = {
        "airfoil": "NACA 2412",
        "chord_m": 1.0,
        "skin_thickness_m": _SKIN_T,
        "wall_solid_boundary_metrics": metrics,
        "max_boundary_gap_m": max_gap,
        "residual_areas_hybrid_m2": residual_areas,
        "hybrid_meta_keys": sorted(meta.keys()),
        "residual_labels_in_mesh": [
            str(k)
            for k in getattr(mesh, "phi_by_label", {})
            if is_residual_label(str(getattr(k, "value", k)))
        ],
        "notes": (
            "Constructive wall-solid boundaries and dense-grid φ=0 agree to a "
            "measurable gap; inserts are residual-φ only on the hybrid mesh."
        ),
    }
    json_path = out_dir / "dual_rep_consistency.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"  max boundary gap = {max_gap:.3e} m")
    for lab, m in metrics.items():
        print(
            f"  {lab}: max_gap={m['max_gap_m']:.3e} mean={m['mean_gap_m']:.3e} "
            f"dA/A={m['area_rel_err']:.3e}"
        )
    return out_dir


if __name__ == "__main__":
    main()
