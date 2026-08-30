"""
visualisation/demos/props_cost_demo.py
===========================
Section-property backends: wall time vs accuracy (Pareto).

For a canonical 2D-CN NACA 2412 section (0° and 15° twist), times:

* hybrid (constructive laminates + residual QT)
* full-label quadtree at depths 5..8
* dense uniform grid (reference accuracy / cost ceiling)

Writes:

* ``props_cost_pareto.png`` — relative area error vs wall time
* ``props_cost_table.png`` — summary table figure
* ``props_cost.json`` — raw timings and errors

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/props_cost_demo.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

os.environ.setdefault("SECTION_GEOMETRY_PROFILE", "1")

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
    emit_constructive_polygons,
    section_properties_from_polygons,
)
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_backend import (
    quadtree_spec_for_airfoil,
)
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_compute import (
    compute_section_properties,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.profiling import (
    get_stats,
    reset_stats,
)

_DPI = DEFAULT_DPI
_DEPTHS = (5, 6, 7, 8)
_TRACK = (
    "skin_suction_surface",
    "skin_pressure_surface",
    "shear_web_0",
    "shear_web_1",
    "spar_cap_suction_surface",
    "spar_cap_pressure_surface",
)


def _build(af: AirfoilSDF, *, twist_rad: float) -> MultiCellSection:
    return MultiCellSection.twin_web(
        af,
        x_fore=0.20,
        x_aft=0.50,
        skin_thickness=0.004,
        web_thickness=0.004,
        cap_height=(0.014, 0.012),
        web_alignment="chord_normal",
        twist_angle=float(twist_rad),
        structural_family="D",
        core_enabled=True,
    )


def _mean_rel_area_err(
    props: dict[str, dict[str, float]],
    ref: dict[str, dict[str, float]],
    labels: tuple[str, ...] = _TRACK,
) -> float:
    errs = []
    for lab in labels:
        if lab not in props or lab not in ref:
            continue
        a = float(props[lab]["area"])
        ar = float(ref[lab]["area"])
        if not np.isfinite(a) or not np.isfinite(ar) or ar <= 0.0:
            continue
        errs.append(abs(a - ar) / ar)
    return float(np.mean(errs)) if errs else float("nan")


def _run_case(
    section: MultiCellSection,
    af: AirfoilSDF,
    *,
    twist_rad: float,
    tag: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # Constructive-only reference for laminate labels (hybrid without residual cost).
    t0 = time.perf_counter()
    polys = emit_constructive_polygons(section)
    constr = section_properties_from_polygons(polys)
    constr_s = time.perf_counter() - t0
    rows.append(
        {
            "tag": tag,
            "backend": "constructive",
            "max_depth": None,
            "wall_time_s": constr_s,
            "phi_eval_count": 0,
            "leaf_count": 0,
            "mean_rel_area_err_vs_constructive": 0.0,
            "n_labels": len(constr),
        }
    )

    # Hybrid at depth 7 (production default class).
    spec7 = quadtree_spec_for_airfoil(af, chord=1.0, max_depth=7, max_cells=150000)
    reset_stats()
    t0 = time.perf_counter()
    hy, hy_meta = compute_section_properties(
        section,
        backend="hybrid",
        quadtree_spec=spec7,
        airfoil_for_spec=af,
        twist_rad=float(twist_rad),
    )
    hy_s = time.perf_counter() - t0
    st = get_stats()
    rows.append(
        {
            "tag": tag,
            "backend": "hybrid",
            "max_depth": 7,
            "wall_time_s": hy_s,
            "phi_eval_count": int(st.phi_eval_count) if st else 0,
            "leaf_count": int(
                (hy_meta.get("quadtree_stats") or {}).get("leaf_count", 0)
            ),
            "mean_rel_area_err_vs_constructive": _mean_rel_area_err(hy, constr),
            "constructive_s": hy_meta.get("constructive_s"),
            "residual_quadtree_s": hy_meta.get("residual_quadtree_s"),
            "n_labels": len(hy),
        }
    )

    for depth in _DEPTHS:
        spec = quadtree_spec_for_airfoil(
            af, chord=1.0, max_depth=int(depth), max_cells=200000
        )
        reset_stats()
        t0 = time.perf_counter()
        qt, qt_meta = compute_section_properties(
            section,
            backend="quadtree",
            quadtree_spec=spec,
            airfoil_for_spec=af,
            twist_rad=float(twist_rad),
        )
        qt_s = time.perf_counter() - t0
        st = get_stats()
        qt_stats = qt_meta.get("quadtree_stats") or {}
        rows.append(
            {
                "tag": tag,
                "backend": "quadtree",
                "max_depth": int(depth),
                "wall_time_s": qt_s,
                "phi_eval_count": int(st.phi_eval_count) if st else 0,
                "leaf_count": int(qt_stats.get("leaf_count", 0)),
                "mean_rel_area_err_vs_constructive": _mean_rel_area_err(qt, constr),
                "n_labels": len(qt),
            }
        )

    # Dense grid — accuracy/cost ceiling (same labels as constructive).
    grid = SDFGrid.from_airfoil(af, padding=0.06, nx=600, ny=240)
    reset_stats()
    t0 = time.perf_counter()
    grid_props, grid_meta = compute_section_properties(
        section,
        backend="grid",
        grid=grid,
        airfoil_for_spec=af,
        twist_rad=float(twist_rad),
    )
    grid_s = time.perf_counter() - t0
    st = get_stats()
    rows.append(
        {
            "tag": tag,
            "backend": "grid",
            "max_depth": None,
            "wall_time_s": grid_s,
            "phi_eval_count": int(st.phi_eval_count) if st else int(grid.X.size),
            "leaf_count": 0,
            "mean_rel_area_err_vs_constructive": _mean_rel_area_err(grid_props, constr),
            "grid_nx": grid.nx,
            "grid_ny": grid.ny,
            "n_labels": len(grid_props),
            "meta_backend": grid_meta.get("backend"),
        }
    )
    return rows


def _save_fig(fig, path: Path) -> None:
    fig.tight_layout()
    save_figure(fig, path)
    plt.close(fig)
    print(f"Wrote {path}")


def main(argv: list[str] | None = None) -> Path:
    default_out = Path(__file__).resolve().parents[1] / "output" / "props_cost"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=default_out)
    args = parser.parse_args(argv)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    af = AirfoilSDF.from_naca("2412", n_points=120, chord=1.0)
    all_rows: list[dict[str, Any]] = []
    for tag, twist in (("twist_0deg", 0.0), ("twist_15deg", float(np.deg2rad(15.0)))):
        section = _build(af, twist_rad=twist)
        all_rows.extend(_run_case(section, af, twist_rad=twist, tag=tag))

    # Pareto: one panel per twist tag
    tags = sorted({r["tag"] for r in all_rows})
    fig, axes = plt.subplots(1, len(tags), figsize=(6.0 * len(tags), 4.8), squeeze=False)
    colours = {
        "constructive": "#1565C0",
        "hybrid": "#2E7D32",
        "quadtree": "#EF6C00",
        "grid": "#6A1B9A",
    }
    for ax, tag in zip(axes[0], tags):
        subset = [r for r in all_rows if r["tag"] == tag]
        for r in subset:
            x = max(float(r["wall_time_s"]), 1e-6)
            y = max(float(r["mean_rel_area_err_vs_constructive"]), 1e-12)
            be = str(r["backend"])
            lab = be
            if be == "quadtree":
                lab = f"QT d={r['max_depth']}"
            ax.scatter(
                x,
                y,
                s=90,
                c=colours.get(be, "k"),
                edgecolors="k",
                linewidths=0.4,
                zorder=3,
                label=lab,
            )
            ax.annotate(
                lab,
                (x, y),
                textcoords="offset points",
                xytext=(6, 4),
                fontsize=7,
            )
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("wall time [s]")
        ax.set_ylabel("mean rel. area err vs constructive")
        ax.set_title(f"Accuracy–cost Pareto — {tag.replace('_', ' ')}")
        ax.grid(True, which="both", alpha=0.35)
        ax.legend(fontsize=7, loc="best")
    fig.suptitle(
        "Section property backends (2D-CN NACA 2412) — lower-left is better",
        fontsize=12,
    )
    _save_fig(fig, out_dir / "props_cost_pareto.png")

    # Table figure
    fig2, ax2 = plt.subplots(figsize=(11.5, 0.45 * len(all_rows) + 1.8))
    ax2.axis("off")
    col_labels = [
        "case",
        "backend",
        "depth",
        "t [s]",
        "φ-evals",
        "leaves",
        "mean |ΔA|/A",
    ]
    cell = []
    for r in all_rows:
        cell.append(
            [
                r["tag"],
                r["backend"],
                "-" if r["max_depth"] is None else str(r["max_depth"]),
                f"{r['wall_time_s']:.3f}",
                f"{r['phi_eval_count']:,}",
                f"{r['leaf_count']:,}",
                f"{r['mean_rel_area_err_vs_constructive']:.2e}",
            ]
        )
    table = ax2.table(
        cellText=cell,
        colLabels=col_labels,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.0, 1.25)
    ax2.set_title("Property backend cost / accuracy summary", fontsize=12, pad=12)
    _save_fig(fig2, out_dir / "props_cost_table.png")

    payload = {
        "airfoil": "NACA 2412",
        "layout": "twin_web family D (2D-CN class)",
        "track_labels": list(_TRACK),
        "reference": "constructive laminate polygons (shoelace)",
        "rows": all_rows,
        "notes": (
            "Hybrid = constructive laminates + residual QT for inserts/cores path. "
            "Area error is mean relative |dA|/A over track labels vs constructive. "
            "At non-zero twist, full-label QT can under-resolve vs constructive "
            "(supports/refinement); hybrid remains the production path."
        ),
    }
    json_path = out_dir / "props_cost.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {json_path}")
    for r in all_rows:
        print(
            f"  {r['tag']:<12} {r['backend']:<12} d={str(r['max_depth']):<4} "
            f"t={r['wall_time_s']:.3f}s  err={r['mean_rel_area_err_vs_constructive']:.2e}"
        )
    return out_dir


if __name__ == "__main__":
    main()
