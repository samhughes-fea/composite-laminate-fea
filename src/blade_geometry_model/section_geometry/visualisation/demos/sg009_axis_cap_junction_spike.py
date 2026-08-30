"""SG-009 offline spike: compare production shared nodes to axis x cap oracle.

Non-production. Does not change build_shell_strip_topology.

For layouts 4D-F (tangency stress) and 5C-CN (short-cap / SG-007 stress):

1. Run production emit + topology.
2. Re-solve interior crossings via web axis x final cap polyline.
3. Report max gap from each oracle hit to the nearest production web/cap vertex.

Expect ~0 nm after SG-005 / SG-007. See docs/reports/SG009_JUNCTION_PRIMITIVES_SPIKE.md.

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/sg009_axis_cap_junction_spike.py
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

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
from blade_structure_utilities.geometry_utilities.section_geometry.midlines.shell_midline_export import (
    build_shell_midline_strips,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import AirfoilSDF
from blade_structure_utilities.geometry_utilities.section_geometry.topology.shell_strip_topology import (
    build_shell_strip_topology,
)

LAYOUTS = ("4D-F", "5C-CN")
CHORD_M = 1.0
TWIST_DEG = 0.0


def _axis_crossings(web: np.ndarray, cap: np.ndarray) -> list[np.ndarray]:
    """Interior hits of the web axis against the cap polyline (SG-009 oracle)."""
    origin = web[0]
    direction = web[-1] - web[0]
    length = float(np.linalg.norm(direction))
    if length < 1e-12:
        return []
    direction = direction / length

    seg_start = cap[:-1]
    seg = cap[1:] - seg_start
    denominator = seg[:, 0] * direction[1] - seg[:, 1] * direction[0]
    usable = np.abs(denominator) > 1e-14
    safe = np.where(usable, denominator, 1.0)
    rel = origin - seg_start
    u = np.where(usable, (rel[:, 0] * direction[1] - rel[:, 1] * direction[0]) / safe, -9.0)
    t = np.where(usable, (rel[:, 0] * seg[:, 1] - rel[:, 1] * seg[:, 0]) / safe, -9.0)
    on_both = usable & (u >= -1e-9) & (u <= 1.0 + 1e-9) & (t >= -1e-9) & (t <= length + 1e-9)

    out: list[np.ndarray] = []
    for i in np.flatnonzero(on_both):
        point = seg_start[i] + u[i] * seg[i]
        at_cap_end = min(
            float(np.linalg.norm(point - cap[0])),
            float(np.linalg.norm(point - cap[-1])),
        )
        if at_cap_end < 1e-9:
            continue
        out.append(np.asarray(point, dtype=float).reshape(2))
    return out


def _prepared(layout_key: str, *, chord_m: float, twist_deg: float):
    twist_rad = float(np.deg2rad(twist_deg))
    section = build_section_view(
        AirfoilSDF.from_naca("2412", n_points=200, chord=chord_m),
        resolve_system_type(layout_key),
        twist_rad=twist_rad,
        skin_thickness=0.006 * chord_m,
        spar_cap_thickness=0.014 * chord_m,
        shear_web_thickness=0.008 * chord_m,
    )
    raw = build_shell_midline_strips(section, twist_rad=twist_rad, chord_m=chord_m)
    return build_shell_strip_topology(raw)


def _report(layout_key: str, *, chord_m: float, twist_deg: float) -> dict:
    strips = _prepared(layout_key, chord_m=chord_m, twist_deg=twist_deg)
    webs = [
        np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float)
        for s in strips
        if str(s.kind) == "web"
    ]
    caps = [
        np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float)
        for s in strips
        if str(s.kind) == "cap"
    ]
    n_hits = 0
    max_web_gap = 0.0
    max_cap_gap = 0.0
    for web in webs:
        for cap in caps:
            for point in _axis_crossings(web, cap):
                n_hits += 1
                web_gap = float(np.linalg.norm(web - point, axis=1).min())
                cap_gap = float(np.linalg.norm(cap - point, axis=1).min())
                max_web_gap = max(max_web_gap, web_gap)
                max_cap_gap = max(max_cap_gap, cap_gap)
    return {
        "layout": layout_key,
        "chord_m": chord_m,
        "twist_deg": twist_deg,
        "n_oracle_hits": n_hits,
        "max_web_gap_nm": max_web_gap * 1e9,
        "max_cap_gap_nm": max_cap_gap * 1e9,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chord-m", type=float, default=CHORD_M)
    parser.add_argument("--twist-deg", type=float, default=TWIST_DEG)
    args = parser.parse_args()

    print("SG-009 offline spike — production nodes vs axis x cap oracle")
    print(f"chord={args.chord_m} m  twist={args.twist_deg} deg")
    print(f"{'layout':8s}  {'hits':>5s}  {'max_web_nm':>12s}  {'max_cap_nm':>12s}")
    for layout in LAYOUTS:
        row = _report(layout, chord_m=float(args.chord_m), twist_deg=float(args.twist_deg))
        print(
            f"{row['layout']:8s}  {row['n_oracle_hits']:5d}  "
            f"{row['max_web_gap_nm']:12.3f}  {row['max_cap_gap_nm']:12.3f}"
        )
    print("Expect max_*_nm ~ 0 after SG-005 / SG-007. Not wired into production.")


if __name__ == "__main__":
    main()
