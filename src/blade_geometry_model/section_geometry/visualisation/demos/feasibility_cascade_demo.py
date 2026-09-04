"""
visualisation/demos/feasibility_cascade_demo.py
===============================================
What the package does when a layout cannot fit: drop → step down → raise.

Sweeps shrinking chord against fixed root-anchored web positions and plots the
resolve ladder for a multi-web catalogue key (default ``5D-F``):

* requested key stays fixed
* surviving web count steps down
* each dropped web is marked with its ``reason``
* the final chord where resolve raises ``InfeasibleSectionGeometry``

Uses ``SectionGeometryRunner(...).resolve().get_layout_resolution()`` — the
cheap path documented in ``docs/guides/feasibility_and_drops.md``.

Writes under ``visualisation/output/feasibility_cascade/``:

* ``feasibility_cascade.png``
* ``feasibility_cascade.json``

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/feasibility_cascade_demo.py --presentation
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

from blade_structure_utilities.geometry_utilities.section_contract import (
    InfeasibleSectionGeometry,
)
from blade_structure_utilities.geometry_utilities.section_geometry import (
    AirfoilSDF,
    SectionGeometryRunner,
    resolve_system_type,
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


def _root_web_positions_m(layout_key: str, root_chord_m: float) -> tuple[float, ...]:
    layout = resolve_system_type(layout_key)
    return tuple(float(frac) * float(root_chord_m) for frac in layout.web_chord_fracs)


def _sweep_cascade(
    *,
    layout_key: str,
    root_chord_m: float,
    chord_values_m: np.ndarray,
    skin_thickness: float,
) -> dict:
    layout = resolve_system_type(layout_key)
    web_x = _root_web_positions_m(layout_key, root_chord_m)
    rows: list[dict] = []
    raise_chord: float | None = None
    raise_message: str | None = None

    for chord in chord_values_m:
        airfoil = AirfoilSDF.from_naca("2412", chord=float(chord), n_points=160)
        runner = SectionGeometryRunner(
            layout=layout,
            airfoil=airfoil,
            skin_thickness=float(skin_thickness),
            spar_cap_thickness=0.0,
            shear_web_thickness=0.004,
            twist_rad=0.0,
            web_x_positions_m=web_x,
            outputs=(),
        )
        try:
            resolution = runner.resolve().get_layout_resolution()
        except InfeasibleSectionGeometry as exc:
            raise_chord = float(chord)
            raise_message = str(exc)
            rows.append(
                {
                    "chord_m": float(chord),
                    "status": "raise",
                    "nominal_key": layout_key,
                    "effective_key": None,
                    "n_webs_surviving": 0,
                    "stepped_down": True,
                    "dropped": [],
                    "message": raise_message,
                }
            )
            break

        dropped = [
            {"x_m": float(item.x_m), "reason": str(item.reason)}
            for item in (resolution.dropped or ())
        ]
        rows.append(
            {
                "chord_m": float(chord),
                "status": "ok",
                "nominal_key": str(resolution.nominal_layout.key),
                "effective_key": str(resolution.layout.key),
                "n_webs_surviving": int(len(resolution.web_x_positions_m)),
                "stepped_down": bool(resolution.stepped_down),
                "dropped": dropped,
                "message": None,
            }
        )

    return {
        "layout_key": layout_key,
        "root_chord_m": float(root_chord_m),
        "web_x_positions_m": list(web_x),
        "skin_thickness_m": float(skin_thickness),
        "raise_chord_m": raise_chord,
        "raise_message": raise_message,
        "rows": rows,
    }


def _plot_cascade(payload: dict, *, presentation: bool) -> plt.Figure:
    rows = payload["rows"]
    chords = np.array([row["chord_m"] for row in rows], dtype=float)
    n_webs = np.array(
        [row["n_webs_surviving"] if row["status"] == "ok" else 0 for row in rows],
        dtype=float,
    )
    fig, axis = plt.subplots(figsize=(12.5, 4.6))
    axis.step(chords, n_webs, where="post", color=NAVY, lw=2.4, label="surviving webs")
    axis.plot(chords, n_webs, "o", color=NAVY, ms=5)

    annotated_chords: set[float] = set()
    for row in rows:
        if row["status"] != "ok":
            continue
        if not row["dropped"]:
            continue
        chord = float(row["chord_m"])
        if chord in annotated_chords:
            continue
        annotated_chords.add(chord)
        reasons = sorted({drop["reason"] for drop in row["dropped"]})
        axis.annotate(
            f"drop: {', '.join(reasons)}\n→ {row['effective_key']}",
            xy=(chord, row["n_webs_surviving"]),
            xytext=(8, 14),
            textcoords="offset points",
            fontsize=8.5,
            color=TEAL,
            arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 0.8},
        )

    raise_chord = payload.get("raise_chord_m")
    if raise_chord is not None:
        axis.axvline(raise_chord, color=RED, ls="--", lw=1.6, label="InfeasibleSectionGeometry")
        axis.scatter([raise_chord], [0.0], s=80, c=RED, zorder=4)
        axis.annotate(
            "raise",
            xy=(raise_chord, 0.0),
            xytext=(10, 20),
            textcoords="offset points",
            color=RED,
            fontsize=11,
            fontweight="bold",
        )

    axis.set_xlabel("local chord [m]", color=INK)
    axis.set_ylabel("surviving web count", color=INK)
    axis.set_title(
        f"Feasibility cascade · {payload['layout_key']} with root-anchored webs "
        f"(root chord {payload['root_chord_m']:.2f} m)",
        color=INK,
    )
    axis.set_ylim(-0.4, max(n_webs.max(), 1.0) + 1.2)
    axis.grid(True, alpha=0.35)
    axis.legend(loc="upper left", frameon=False)
    axis.invert_xaxis()
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_output_and_presentation_args(parser, default_stem="feasibility_cascade")
    parser.add_argument("--layout", default="5D-F")
    parser.add_argument("--root-chord", type=float, default=1.0)
    parser.add_argument("--skin-thickness", type=float, default=0.006)
    parser.add_argument("--chord-min", type=float, default=0.08)
    parser.add_argument("--chord-max", type=float, default=1.0)
    parser.add_argument("--n-chords", type=int, default=28)
    args = parser.parse_args(argv)
    apply_presentation_style(bool(args.presentation))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chord_values = np.linspace(float(args.chord_max), float(args.chord_min), int(args.n_chords))
    payload = _sweep_cascade(
        layout_key=str(args.layout),
        root_chord_m=float(args.root_chord),
        chord_values_m=chord_values,
        skin_thickness=float(args.skin_thickness),
    )
    fig = _plot_cascade(payload, presentation=bool(args.presentation))
    png_path = out_dir / "feasibility_cascade.png"
    save_figure(fig, png_path, presentation=bool(args.presentation))
    plt.close(fig)
    print(f"Wrote {png_path}")

    json_path = out_dir / "feasibility_cascade.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
