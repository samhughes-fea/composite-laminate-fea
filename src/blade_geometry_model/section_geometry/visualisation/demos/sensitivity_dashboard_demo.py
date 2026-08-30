"""
visualisation/demos/sensitivity_dashboard_demo.py
=====================================
Finite-difference sensitivity dashboard for implicit section geometry.

Writes under ``visualisation/output/sensitivity_dashboard/``:

* ``sensitivity_dashboard.png`` - derivative bars, local sweep responses, and base geometry.
* ``sensitivity_dashboard.json`` - derivatives and sweep data.
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
    SDFGrid,
    build_section_view,
    resolve_system_type,
)
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_backend import (
    quadtree_spec_for_airfoil,
)
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_compute import (
    compute_section_properties,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot import (
    plot_section,
)

_DPI = DEFAULT_DPI


def _totals(props: dict[str, dict[str, float]]) -> dict[str, float]:
    return {
        "area": float(np.nansum([float(v.get("area", np.nan)) for v in props.values()])),
        "Ixx": float(np.nansum([float(v.get("Ixx", np.nan)) for v in props.values()])),
        "Iyy": float(np.nansum([float(v.get("Iyy", np.nan)) for v in props.values()])),
    }


def _evaluate(layout, airfoil, spec, chord_m: float, pars: dict[str, float]) -> dict[str, float]:
    section = build_section_view(
        airfoil,
        layout,
        twist_rad=float(np.deg2rad(pars["twist_deg"])),
        skin_thickness=float(pars["skin_thickness"]),
        spar_cap_thickness=float(pars["spar_cap_thickness"]),
        shear_web_thickness=float(pars["shear_web_thickness"]),
    )
    props, _meta = compute_section_properties(
        section,
        backend="hybrid",
        quadtree_spec=spec,
        chord=float(chord_m),
        twist_rad=float(np.deg2rad(pars["twist_deg"])),
        airfoil_for_spec=airfoil,
    )
    return _totals(props)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key", default="2D-F")
    p.add_argument("--naca", default="2412")
    p.add_argument("--chord", type=float, default=1.0)
    p.add_argument("--twist-deg", type=float, default=15.0)
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args(argv)

    out_dir = args.out_dir or (Path(__file__).resolve().parents[1] / "output" / "sensitivity_dashboard")
    out_dir.mkdir(parents=True, exist_ok=True)

    layout = resolve_system_type(str(args.key))
    airfoil = AirfoilSDF.from_naca(str(args.naca), chord=float(args.chord), n_points=170)
    spec = quadtree_spec_for_airfoil(airfoil, chord=float(args.chord), max_depth=7, max_cells=140000)

    base = {
        "skin_thickness": 0.0035,
        "spar_cap_thickness": 0.0120,
        "shear_web_thickness": 0.0040,
        "twist_deg": float(args.twist_deg),
    }
    deltas = {
        "skin_thickness": 2.5e-4,
        "spar_cap_thickness": 8.0e-4,
        "shear_web_thickness": 3.5e-4,
        "twist_deg": 0.5,
    }

    y0 = _evaluate(layout, airfoil, spec, float(args.chord), base)

    deriv: dict[str, dict[str, float]] = {"area": {}, "Ixx": {}, "Iyy": {}}
    for name, h in deltas.items():
        xp = dict(base)
        xm = dict(base)
        xp[name] = float(xp[name] + h)
        xm[name] = float(xm[name] - h)
        yp = _evaluate(layout, airfoil, spec, float(args.chord), xp)
        ym = _evaluate(layout, airfoil, spec, float(args.chord), xm)
        for out_name in deriv:
            deriv[out_name][name] = float((yp[out_name] - ym[out_name]) / (2.0 * h))

    sweep: dict[str, list[dict[str, float]]] = {}
    for name, h in deltas.items():
        rows: list[dict[str, float]] = []
        for t in [-2.0, -1.0, 0.0, 1.0, 2.0]:
            x = dict(base)
            x[name] = float(x[name] + t * h)
            y = _evaluate(layout, airfoil, spec, float(args.chord), x)
            rows.append({"x": x[name], "area": y["area"], "Ixx": y["Ixx"], "Iyy": y["Iyy"]})
        sweep[name] = rows

    section_base = build_section_view(
        airfoil,
        layout,
        twist_rad=float(np.deg2rad(base["twist_deg"])),
        skin_thickness=base["skin_thickness"],
        spar_cap_thickness=base["spar_cap_thickness"],
        shear_web_thickness=base["shear_web_thickness"],
    )
    airfoil_b = airfoil.rotate(float(np.deg2rad(base["twist_deg"])))
    grid = SDFGrid.from_airfoil(airfoil_b, nx=520, ny=220)

    fig, axs = plt.subplots(2, 2, figsize=(16, 10.5))
    ax0, ax1, ax2, ax3 = axs.ravel()

    names = list(deltas.keys())
    xloc = np.arange(len(names))
    ax0.bar(xloc - 0.25, [deriv["area"][k] for k in names], width=0.25, label="dA/dx")
    ax0.bar(xloc, [deriv["Ixx"][k] for k in names], width=0.25, label="dIxx/dx")
    ax0.bar(xloc + 0.25, [deriv["Iyy"][k] for k in names], width=0.25, label="dIyy/dx")
    ax0.set_xticks(xloc)
    ax0.set_xticklabels(names, rotation=20, ha="right")
    ax0.set_title("Finite-difference sensitivities")
    ax0.grid(True, axis="y", alpha=0.25)
    ax0.legend(loc="best")

    for name in names:
        rows = sweep[name]
        xs = [r["x"] for r in rows]
        ys = [r["area"] for r in rows]
        ax1.plot(xs, ys, marker="o", lw=1.2, label=name)
    ax1.set_title("Local sweep: area response")
    ax1.set_xlabel("parameter value")
    ax1.set_ylabel("area [m²]")
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="best", fontsize=8)

    for name in names:
        rows = sweep[name]
        xs = [r["x"] for r in rows]
        yx = [r["Ixx"] for r in rows]
        yy = [r["Iyy"] for r in rows]
        ax2.plot(xs, yx, marker="o", lw=1.0, alpha=0.9, label=f"{name}: Ixx")
        ax2.plot(xs, yy, marker="s", lw=1.0, alpha=0.9, linestyle="--", label=f"{name}: Iyy")
    ax2.set_title("Local sweep: inertia responses")
    ax2.set_xlabel("parameter value")
    ax2.set_ylabel("inertia [m⁴]")
    ax2.grid(True, alpha=0.25)

    plot_section(
        section_base,
        grid,
        ax=ax3,
        show_airfoil=False,
        show_legend=False,
        auto_limits=True,
        alpha=0.52,
        title=f"Base geometry - {args.key} ({base['twist_deg']:.1f} deg)",
    )

    fig.suptitle("Sensitivity dashboard (implicit CSG section geometry)", fontsize=14)
    fig.tight_layout()
    out_png = out_dir / "sensitivity_dashboard.png"
    save_figure(fig, out_png)
    plt.close(fig)
    print(f"Wrote {out_png}")

    payload = {
        "key": str(args.key),
        "naca": str(args.naca),
        "chord_m": float(args.chord),
        "base": base,
        "base_outputs": y0,
        "deltas": deltas,
        "derivatives": deriv,
        "sweeps": sweep,
        "png": out_png.name,
    }
    out_json = out_dir / "sensitivity_dashboard.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
