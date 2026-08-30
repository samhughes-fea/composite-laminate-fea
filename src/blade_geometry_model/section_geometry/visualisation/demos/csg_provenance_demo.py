"""
examples/csg_provenance_demo.py
===============================
Demonstrate implicit-CSG component interactions via distance-field diagnostics.

Writes under ``visualisation/output/csg_provenance/``:

* ``csg_provenance_map.png`` - geometry, winner-label map, nearest-interface map,
  and ambiguity margin.
* ``csg_provenance_map.json`` - run metadata and winner-pixel counts.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

_erp = Path(__file__).resolve().parent / "_ensure_repo_path.py"
_spec = importlib.util.spec_from_file_location("_ensure_repo_path", _erp)
_ensure_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_ensure_mod)
_ensure_mod.ensure_repo_path()

from blade_structure_utilities.geometry_utilities.section_geometry import (
    AirfoilSDF,
    SDFGrid,
    build_section_view,
    resolve_system_type,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot import (
    _component_color,
    plot_section,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot_section import (
    apply_structural_section_axes,
    rotated_naca_grid_to_section_plot_axes,
)

_DPI = 190


def _to_key(label) -> str:
    return str(getattr(label, "value", label))


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {path}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key", default="2D-F")
    p.add_argument("--naca", default="2412")
    p.add_argument("--chord", type=float, default=1.0)
    p.add_argument("--twist-deg", type=float, default=15.0)
    p.add_argument("--nx", type=int, default=640)
    p.add_argument("--ny", type=int, default=280)
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args(argv)

    out_dir = args.out_dir or (Path(__file__).resolve().parents[1] / "output" / "csg_provenance")
    out_dir.mkdir(parents=True, exist_ok=True)

    layout = resolve_system_type(str(args.key))
    twist_rad = float(np.deg2rad(float(args.twist_deg)))
    airfoil = AirfoilSDF.from_naca(str(args.naca), chord=float(args.chord), n_points=180)
    section = build_section_view(
        airfoil,
        layout,
        twist_rad=twist_rad,
        skin_thickness=0.0035,
        spar_cap_thickness=0.012,
        shear_web_thickness=0.004,
    )

    airfoil_for_grid = airfoil.rotate(twist_rad) if abs(twist_rad) > 1e-12 else airfoil
    grid = SDFGrid.from_airfoil(airfoil_for_grid, nx=int(args.nx), ny=int(args.ny), padding=0.08)

    labels = list(section)
    phi_stack: list[np.ndarray] = []
    label_keys: list[str] = []
    for label in labels:
        key = _to_key(label)
        try:
            phi_i = np.asarray(grid.eval(section[label]), dtype=float)
        except Exception:
            continue
        if phi_i.shape == grid.X.shape:
            phi_stack.append(phi_i)
            label_keys.append(key)
    if not phi_stack:
        raise RuntimeError("No evaluable label SDFs found for provenance map")

    phi = np.stack(phi_stack, axis=0)
    n_labels = int(phi.shape[0])
    inside = phi < 0.0
    any_inside = np.any(inside, axis=0)
    winner_inside = np.argmin(phi, axis=0)
    nearest = np.argmin(np.abs(phi), axis=0)
    winner = np.where(any_inside, winner_inside, nearest)

    abs_phi = np.abs(phi)
    if n_labels > 1:
        part = np.partition(abs_phi, kth=1, axis=0)
        ambiguity = np.maximum(part[1] - part[0], 0.0)
    else:
        ambiguity = np.zeros_like(abs_phi[0])

    x_plot, y_plot = rotated_naca_grid_to_section_plot_axes(
        grid.X, grid.Y, twist_rad=twist_rad, chord_m=float(args.chord)
    )

    fig, axs = plt.subplots(2, 2, figsize=(16, 11))
    ax_geom, ax_winner, ax_nearest, ax_margin = axs.ravel()

    plot_section(section, grid, ax=ax_geom, alpha=0.52, show_airfoil=False, show_legend=True, auto_limits=True,
                 title=f"Hybrid section plot - {args.key} ({args.twist_deg:g} deg)")

    colors = [_component_color(k) for k in label_keys]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(np.arange(-0.5, n_labels + 0.5, 1.0), cmap.N)

    ax_winner.pcolormesh(x_plot, y_plot, winner, cmap=cmap, norm=norm, shading="auto")
    apply_structural_section_axes(ax_winner)
    ax_winner.set_title("Winner label map (inside: most negative phi)")

    ax_nearest.pcolormesh(x_plot, y_plot, nearest, cmap=cmap, norm=norm, shading="auto")
    apply_structural_section_axes(ax_nearest)
    ax_nearest.set_title("Nearest label map (global nearest interface)")

    margin_map = ax_margin.pcolormesh(x_plot, y_plot, ambiguity, shading="auto", cmap="magma")
    plt.colorbar(margin_map, ax=ax_margin, label="second|phi| - min|phi| [m]")
    apply_structural_section_axes(ax_margin)
    ax_margin.set_title("Interface ambiguity margin")

    legend_handles = [Patch(facecolor=colors[i], edgecolor="none", label=label_keys[i]) for i in range(n_labels)]
    ax_winner.legend(handles=legend_handles, title="Labels", loc="lower right", fontsize=8, title_fontsize=9)

    out_png = out_dir / "csg_provenance_map.png"
    _save(fig, out_png)

    payload = {
        "key": str(args.key),
        "naca": str(args.naca),
        "chord_m": float(args.chord),
        "twist_deg": float(args.twist_deg),
        "grid": {"nx": int(args.nx), "ny": int(args.ny)},
        "labels": label_keys,
        "winner_pixel_counts": {k: int(np.sum(winner == i)) for i, k in enumerate(label_keys)},
        "nearest_pixel_counts": {k: int(np.sum(nearest == i)) for i, k in enumerate(label_keys)},
        "inside_fraction": float(np.mean(any_inside)),
        "ambiguity_margin_mean_m": float(np.mean(ambiguity)),
        "ambiguity_margin_p95_m": float(np.quantile(ambiguity, 0.95)),
        "png": out_png.name,
    }
    out_json = out_dir / "csg_provenance_map.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

