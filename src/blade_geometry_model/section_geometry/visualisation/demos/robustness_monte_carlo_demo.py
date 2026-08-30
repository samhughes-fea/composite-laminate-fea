"""
examples/robustness_monte_carlo_demo.py
=======================================
Randomized robustness sweep for implicit section geometry.

Writes under ``visualisation/output/robustness_monte_carlo/``:

* ``robustness_monte_carlo.png`` - parameter sweep success map and response spread.
* ``robustness_monte_carlo.json`` - per-sample metadata and aggregate statistics.
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
    build_section_view,
    resolve_system_type,
)
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_backend import (
    quadtree_spec_for_airfoil,
)
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_compute import (
    compute_section_properties,
)

_DPI = 190


def _safe_float(v: float) -> float | None:
    return float(v) if np.isfinite(v) else None


def _totals(props: dict[str, dict[str, float]]) -> dict[str, float]:
    area = float(np.nansum([float(row.get("area", np.nan)) for row in props.values()]))
    ixx = float(np.nansum([float(row.get("Ixx", np.nan)) for row in props.values()]))
    iyy = float(np.nansum([float(row.get("Iyy", np.nan)) for row in props.values()]))
    return {"area": area, "Ixx": ixx, "Iyy": iyy}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key", default="2D-F")
    p.add_argument("--naca", default="2412")
    p.add_argument("--chord", type=float, default=1.0)
    p.add_argument("--twist-deg", type=float, default=15.0)
    p.add_argument("--n-samples", type=int, default=120)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args(argv)

    out_dir = args.out_dir or (Path(__file__).resolve().parents[1] / "output" / "robustness_monte_carlo")
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(int(args.seed))
    twist_nom_deg = float(args.twist_deg)
    layout = resolve_system_type(str(args.key))
    airfoil = AirfoilSDF.from_naca(str(args.naca), chord=float(args.chord), n_points=170)
    spec = quadtree_spec_for_airfoil(airfoil, chord=float(args.chord), max_depth=7, max_cells=140000)

    samples: list[dict[str, object]] = []
    ok_area: list[float] = []
    ok_ixx: list[float] = []
    ok_iyy: list[float] = []

    for i in range(int(args.n_samples)):
        skin = float(np.clip(rng.normal(0.0035, 0.0008), 0.0015, 0.0065))
        cap = float(np.clip(rng.normal(0.0120, 0.0025), 0.0060, 0.0200))
        web = float(np.clip(rng.normal(0.0040, 0.0010), 0.0015, 0.0080))
        twist_deg = float(np.clip(rng.normal(float(args.twist_deg), 4.0), -2.0, 30.0))
        twist_rad = float(np.deg2rad(twist_deg))

        row: dict[str, object] = {
            "i": i,
            "skin_thickness_m": skin,
            "spar_cap_thickness_m": cap,
            "shear_web_thickness_m": web,
            "twist_deg": twist_deg,
            "twist_dev_deg": twist_deg - twist_nom_deg,
            "ok": False,
            "error": None,
            "area": None,
            "Ixx": None,
            "Iyy": None,
        }
        try:
            section = build_section_view(
                airfoil,
                layout,
                twist_rad=twist_rad,
                skin_thickness=skin,
                spar_cap_thickness=cap,
                shear_web_thickness=web,
            )
            props, _meta = compute_section_properties(
                section,
                backend="hybrid",
                quadtree_spec=spec,
                chord=float(args.chord),
                twist_rad=twist_rad,
                airfoil_for_spec=airfoil,
            )
            t = _totals(props)
            good = all(np.isfinite([t["area"], t["Ixx"], t["Iyy"]])) and t["area"] > 0.0
            row["ok"] = bool(good)
            row["area"] = _safe_float(t["area"])
            row["Ixx"] = _safe_float(t["Ixx"])
            row["Iyy"] = _safe_float(t["Iyy"])
            if good:
                ok_area.append(float(t["area"]))
                ok_ixx.append(float(t["Ixx"]))
                ok_iyy.append(float(t["Iyy"]))
        except Exception as exc:
            row["error"] = str(exc)

        samples.append(row)

    ok_mask = np.array([bool(r["ok"]) for r in samples], dtype=bool)
    skin_vals = np.array([float(r["skin_thickness_m"]) for r in samples], dtype=float)
    web_vals = np.array([float(r["shear_web_thickness_m"]) for r in samples], dtype=float)
    area_vals = np.array([np.nan if r["area"] is None else float(r["area"]) for r in samples], dtype=float)
    twdev_vals = np.array([float(r["twist_dev_deg"]) for r in samples], dtype=float)

    fig, axs = plt.subplots(2, 2, figsize=(15.5, 10.5))
    ax0, ax1, ax2, ax3 = axs.ravel()

    ax0.scatter(skin_vals[~ok_mask], web_vals[~ok_mask], s=36, c="#d32f2f", alpha=0.65, label="failed")
    ax0.scatter(skin_vals[ok_mask], web_vals[ok_mask], s=30, c="#2e7d32", alpha=0.65, label="ok")
    ax0.set_title("Monte Carlo feasibility map")
    ax0.set_xlabel("skin thickness [m]")
    ax0.set_ylabel("web thickness [m]")
    ax0.grid(True, alpha=0.25)
    ax0.legend(loc="best")

    ax1.hist(area_vals[np.isfinite(area_vals)], bins=28, color="#1976d2", alpha=0.8)
    ax1.set_title("Total area distribution")
    ax1.set_xlabel("area [m²]")
    ax1.set_ylabel("count")
    ax1.grid(True, alpha=0.25)

    metrics = [np.array(ok_area, dtype=float), np.array(ok_ixx, dtype=float), np.array(ok_iyy, dtype=float)]
    ax2.boxplot(metrics, tick_labels=["area", "Ixx", "Iyy"], showfliers=False)
    ax2.set_title("Valid-sample response spread")
    ax2.grid(True, axis="y", alpha=0.25)

    sc = ax3.scatter(twdev_vals, area_vals, c=np.where(ok_mask, 1.0, 0.0), cmap="coolwarm", alpha=0.7, s=28)
    _ = sc
    ax3.set_title("Area vs twist perturbation")
    ax3.set_xlabel("twist deviation from nominal [deg]")
    ax3.set_ylabel("area [m²]")
    ax3.grid(True, alpha=0.25)

    fail_count = int(np.sum(~ok_mask))
    ok_count = int(np.sum(ok_mask))
    success_rate = float(ok_count / max(len(samples), 1))
    fig.suptitle(
        f"Robustness Monte Carlo - key={args.key}, n={len(samples)}, success={success_rate:.1%}",
        fontsize=14,
    )

    out_png = out_dir / "robustness_monte_carlo.png"
    fig.tight_layout()
    fig.savefig(out_png, dpi=_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {out_png}")

    payload = {
        "key": str(args.key),
        "naca": str(args.naca),
        "chord_m": float(args.chord),
        "seed": int(args.seed),
        "n_samples": int(args.n_samples),
        "ok_count": ok_count,
        "fail_count": fail_count,
        "success_rate": success_rate,
        "area_mean": _safe_float(float(np.nanmean(area_vals)) if np.any(np.isfinite(area_vals)) else np.nan),
        "area_std": _safe_float(float(np.nanstd(area_vals)) if np.any(np.isfinite(area_vals)) else np.nan),
        "samples": samples,
        "png": out_png.name,
    }
    out_json = out_dir / "robustness_monte_carlo.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

