"""Labelled anatomy figure for layout 2D-F (teaching companion to the gallery).

Writes visualisation/output/anatomy_2d_f/2D-F_labelled.png with the standard
component legend so docs can name suction/pressure skin, webs, and spar caps.

Gallery tiles from structural_family_grids_demo.py stay legend-less.

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/anatomy_2d_f_demo.py
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

_erp = Path(__file__).resolve().parent / "_ensure_repo_path.py"
_spec = importlib.util.spec_from_file_location("_ensure_repo_path", _erp)
_ensure_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_ensure_mod)
_ensure_mod.ensure_repo_path()

from blade_structure_utilities.geometry_utilities.section_geometry.api.factory import (
    build_section_view,
    resolve_system_type,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import AirfoilSDF
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.figure_io import (
    add_output_and_presentation_args,
    apply_presentation_style,
    save_figure,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot import (
    plot_section_hybrid,
)

_FIGSIZE = (12.0, 5.0)
_LAYOUT_KEY = "2D-F"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_output_and_presentation_args(parser, default_stem="anatomy_2d_f")
    parser.add_argument("--twist-deg", type=float, default=0.0)
    parser.add_argument("--naca", default="2412")
    parser.add_argument("--chord", type=float, default=1.0)
    args = parser.parse_args(argv)

    apply_presentation_style(bool(args.presentation))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    airfoil = AirfoilSDF.from_naca(args.naca, n_points=140, chord=float(args.chord))
    layout = resolve_system_type(_LAYOUT_KEY)
    twist_rad = float(np.deg2rad(float(args.twist_deg)))
    section = build_section_view(airfoil, layout, twist_angle_rad=twist_rad)

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    plot_section_hybrid(
        section,
        residual_mesh=None,
        ax=ax,
        alpha=0.5,
        title=(
            f"{_LAYOUT_KEY} anatomy - suction/pressure skin, spar caps, shear webs\n"
            f"(NACA {args.naca}, chord={args.chord:g} m, twist={args.twist_deg:g} deg)"
        ),
        show_legend=True,
    )
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()

    out_png = out_dir / "2D-F_labelled.png"
    save_figure(fig, out_png, presentation=bool(args.presentation))
    plt.close(fig)
    print(f"Wrote {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
