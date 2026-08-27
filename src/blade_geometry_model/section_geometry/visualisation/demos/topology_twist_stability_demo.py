"""
examples/topology_twist_stability_demo.py
=========================================
Computational-geometry demo: shell topology stability under twist.

``build_shell_strip_topology`` snaps web feet onto skin and inserts cap–web
T-junction vertices. This demo sweeps section twist and shows that junction
gaps stay near geometry tolerance — topology ops are stable under rigid motion
of the IR section.

Writes:

* ``gap_vs_twist.png`` — max web–skin gap (raw vs topology) vs twist
* ``junction_zoom_worst_twist.png`` — junction zooms at the worst twist
* ``topology_twist_stability.json`` — per-twist metrics

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/topology_twist_stability_demo.py
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

from blade_structure_utilities.geometry_utilities.section_geometry import (
    AirfoilSDF,
    MultiCellSection,
)
from blade_structure_utilities.geometry_utilities.section_geometry.midlines.ring_geometry import (
    point_to_open_polyline_nearest,
)
from blade_structure_utilities.geometry_utilities.section_geometry.midlines.shell_midline_export import (
    build_shell_midline_strips,
)
from blade_structure_utilities.geometry_utilities.section_geometry.topology.shell_strip_topology import (
    build_shell_strip_topology,
)
from blade_structure_utilities.geometry_utilities.coordinate_frames import (
    section_plot_axes,
)

_DPI = 220
_TWIST_DEG = (0.0, 5.0, 10.0, 15.0, 30.0)


def _build_section(af: AirfoilSDF, *, twist_rad: float) -> MultiCellSection:
    return MultiCellSection.torsion_box(
        af,
        x_fore=0.15,
        x_mid=0.35,
        x_aft=0.55,
        skin_thickness=0.005,
        web_thickness=0.006,
        cap_height=(0.014, 0.012),
        web_alignment="chord_normal",
        twist_angle=float(twist_rad),
        structural_family="D",
        core_enabled=False,
    )


def _nearest_point_distance(pt: np.ndarray, poly: np.ndarray) -> float:
    return float(np.min(np.linalg.norm(poly - pt.reshape(1, 2), axis=1)))


def _web_skin_gaps(strips) -> list[dict]:
    skins = [np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float) for s in strips if s.kind == "skin"]
    if not skins:
        return []
    skin = np.vstack(skins)
    gaps: list[dict] = []
    for s in strips:
        if s.kind != "web":
            continue
        pts = np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float)
        if pts.shape[0] < 2:
            continue
        for end_name, row in (("top", 0), ("bot", -1)):
            pt = pts[row]
            gaps.append(
                {
                    "web_label": str(s.label),
                    "end": end_name,
                    "gap_to_skin_vertex_m": _nearest_point_distance(pt, skin),
                }
            )
    return gaps


def _cap_web_shared_count(strips, *, tol_m: float = 2.5e-3) -> int:
    webs = [
        (s.label, np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float))
        for s in strips
        if s.kind == "web" and np.asarray(s.midline_twisted_pitch_axis_blade_frame).shape[0] >= 2
    ]
    n = 0
    for s in strips:
        if s.kind != "cap":
            continue
        pts = np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float)
        for pt in pts:
            best = 1e300
            for _wlab, wpts in webs:
                gap, _q = point_to_open_polyline_nearest(pt, wpts)
                best = min(best, float(gap))
            if best <= tol_m:
                n += 1
    return n


def _overlay_strips(ax, strips, *, lw: float = 1.8) -> None:
    kind_colour = {"skin": "#2196F3", "web": "#4CAF50", "cap": "#F44336"}
    for strip in strips:
        pts = np.asarray(strip.midline_twisted_pitch_axis_blade_frame, dtype=float)
        if pts.shape[0] < 2:
            continue
        h, v = section_plot_axes(pts)
        ax.plot(
            h,
            v,
            color=kind_colour.get(str(strip.kind), "#607D8B"),
            lw=lw,
            alpha=0.95,
        )


def _save_fig(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {path}")


def main(argv: list[str] | None = None) -> Path:
    default_out = Path(__file__).resolve().parents[1] / "output" / "topology_twist_stability"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=default_out)
    args = parser.parse_args(argv)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    af = AirfoilSDF.from_naca("2412", chord=1.0)
    rows: list[dict] = []
    topo_by_twist: dict[float, object] = {}

    for deg in _TWIST_DEG:
        twist = float(np.deg2rad(deg))
        section = _build_section(af, twist_rad=twist)
        raw = build_shell_midline_strips(section, twist_rad=twist)
        topo = build_shell_strip_topology(raw)
        topo_by_twist[deg] = topo
        gaps_raw = _web_skin_gaps(raw)
        gaps_topo = _web_skin_gaps(topo)
        row = {
            "twist_deg": float(deg),
            "twist_rad": twist,
            "max_web_skin_gap_raw_m": max(
                (g["gap_to_skin_vertex_m"] for g in gaps_raw), default=float("nan")
            ),
            "max_web_skin_gap_topology_m": max(
                (g["gap_to_skin_vertex_m"] for g in gaps_topo), default=float("nan")
            ),
            "mean_web_skin_gap_topology_m": float(
                np.mean([g["gap_to_skin_vertex_m"] for g in gaps_topo])
            )
            if gaps_topo
            else float("nan"),
            "n_cap_web_shared_vertices": _cap_web_shared_count(topo),
            "n_skin_strips": sum(1 for s in topo if s.kind == "skin"),
            "n_web_strips": sum(1 for s in topo if s.kind == "web"),
        }
        rows.append(row)

    # Gap vs twist
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    degs = [r["twist_deg"] for r in rows]
    raw_g = [max(r["max_web_skin_gap_raw_m"], 1e-16) for r in rows]
    topo_g = [max(r["max_web_skin_gap_topology_m"], 1e-16) for r in rows]
    ax.semilogy(degs, raw_g, "o--", color="#EF6C00", lw=1.8, label="max gap raw")
    ax.semilogy(
        degs, topo_g, "s-", color="#2E7D32", lw=2.0, label="max gap after topology"
    )
    ax.set_xlabel("section twist [deg]")
    ax.set_ylabel("max web–skin foot gap [m]")
    ax.set_title("Topology snap stability under twist (NACA 2412 3-web box)")
    ax.grid(True, which="both", alpha=0.35)
    ax.legend(fontsize=9)
    _save_fig(fig, out_dir / "gap_vs_twist.png")

    # Worst topology gap (should still be tiny); zoom that case.
    worst = max(rows, key=lambda r: r["max_web_skin_gap_topology_m"])
    topo = topo_by_twist[worst["twist_deg"]]
    gaps_topo = _web_skin_gaps(topo)
    # Pick a few feet for zoom panels.
    centres = []
    for g in gaps_topo:
        # Reconstruct point from strips for zoom centre.
        pass
    # Use web endpoints from topo strips.
    for s in topo:
        if s.kind != "web":
            continue
        pts = np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float)
        if pts.shape[0] < 2:
            continue
        centres.append((f"{s.label} top @ {worst['twist_deg']:g}°", pts[0].copy()))
        centres.append((f"{s.label} bot @ {worst['twist_deg']:g}°", pts[-1].copy()))
    centres = centres[:6]

    n = len(centres)
    ncols = 3 if n > 3 else max(n, 1)
    nrows = int(np.ceil(n / ncols)) if n else 1
    fig2, axes2 = plt.subplots(nrows, ncols, figsize=(13.0, 3.8 * nrows))
    axes_flat = np.atleast_1d(axes2).ravel()
    half = 0.035
    for ax, (title, centre) in zip(axes_flat, centres):
        _overlay_strips(ax, topo, lw=2.0)
        # centre is canonical B (X_B, Y_B); plot horizontal = Y_B.
        h_c, v_c = section_plot_axes(np.asarray(centre, dtype=float).reshape(1, 2))
        ax.scatter(
            [float(h_c[0])],
            [float(v_c[0])],
            s=40,
            c="#FFC107",
            edgecolors="k",
            linewidths=0.4,
            zorder=10,
        )
        ax.set_xlim(float(h_c[0]) - half, float(h_c[0]) + half)
        ax.set_ylim(float(v_c[0]) - half, float(v_c[0]) + half)
        ax.grid(True, alpha=0.3)
        ax.set_title(title, fontsize=9)
        from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot_section import (
            apply_structural_section_axes,
        )

        apply_structural_section_axes(ax)
    for ax in axes_flat[n:]:
        ax.axis("off")
    fig2.suptitle(
        f"Junction zooms at worst twist "
        f"(topo max gap={worst['max_web_skin_gap_topology_m']:.3e} m)",
        fontsize=11,
    )
    _save_fig(fig2, out_dir / "junction_zoom_worst_twist.png")

    payload = {
        "airfoil": "NACA 2412",
        "layout": "torsion_box family D (x=0.15/0.35/0.55)",
        "twist_deg_sweep": list(_TWIST_DEG),
        "rows": rows,
        "worst_twist_deg": float(worst["twist_deg"]),
        "max_topology_gap_over_sweep_m": max(
            r["max_web_skin_gap_topology_m"] for r in rows
        ),
        "notes": (
            "Web–skin snap gaps after topology remain near machine/geometry "
            "tolerance across the twist sweep."
        ),
    }
    json_path = out_dir / "topology_twist_stability.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {json_path}")
    for r in rows:
        print(
            f"  twist={r['twist_deg']:5.1f}°  raw={r['max_web_skin_gap_raw_m']:.3e}  "
            f"topo={r['max_web_skin_gap_topology_m']:.3e}  "
            f"cap-web nodes={r['n_cap_web_shared_vertices']}"
        )
    return out_dir


if __name__ == "__main__":
    main()
