"""An interior cap-web T-junction must put a node on **both** strips.

Where a web crosses a cap's middle rather than its end, the cap used to get a
node and the web did not: measured gaps up to **4.54 mm** across layouts, twists
and chords. The junction held together only because ``section_mesh`` clusters
endpoints within ``ENDPOINT_TOL_FRAC`` — 6 mm on a 1 m chord — a tolerance that
scales with *chord* rather than with mesh density, so refining the web or
shrinking the chord erodes it silently with no error raised.

**Why this test does not use ``intersect_open_polylines_2d``.** That is the
detector the fix itself uses, and once both strips carry the shared node the two
polylines *touch* rather than cross, so a strict-interior intersection finds
nothing at all. A test built on it would pass vacuously on a correct fix and
also on a fix that deleted every junction. Crossings are therefore located
independently here, from the web's own axis against the cap polyline.

That trap is not hypothetical: an earlier attempt inserted the web node at emit,
which made the polylines tangent and stopped the cap side being found —
``4D-F`` swapped from web 1570 um / cap 0 um to web 0 um / cap 1056 um. Hence
the second test, which pins the cap side against exactly that regression.

See ``docs/bug_log.md`` SG-005.
"""

from __future__ import annotations

import numpy as np
import pytest

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

# Layouts where a web crosses a cap interior: family D with 3+ webs, and family C.
LAYOUTS = ["3D-F", "4D-F", "5D-CN", "2C-F", "5C-CN"]
TWIST_DEG = [0.0, 15.0]
# The tip chord is the aggravating case: caps are short, so any absolute
# tolerance in the junction path has the least headroom there.
CHORD_M = [1.0, 0.241]

#: The web node is placed at the solved crossing itself, so nothing but
#: floating-point should separate them.
_MAX_WEB_GAP_M = 1e-9
#: The cap side is allowed the de-dup window of ``_CAP_WEB_JUNCTION_MERGE_ARC_M``
#: (1 um absolute), which can collapse two crossings that are genuinely distinct
#: on a short cap. Worst measured 0.89 um on ``5C-CN`` at the tip chord. This is
#: a pre-existing residual tracked as SG-007 — not licence for the cap side to
#: drift, which is why the bound is 1 um and not "small".
_MAX_CAP_GAP_M = 1e-6


def _prepared(layout_key: str, twist_deg: float, chord_m: float):
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


def _by_kind(strips, kind):
    return [
        np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float)
        for s in strips
        if str(s.kind) == kind
    ]


def _axis_crossings(web: np.ndarray, cap: np.ndarray) -> list[np.ndarray]:
    """Points where the web's own axis meets the cap polyline, interior only.

    Independent of the production detector on purpose — see the module
    docstring. Endpoints of the cap are excluded: those are cap-*end* junctions,
    which ``shell_midline_export`` already closes at emit (SG-004).
    """
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
    out = []
    for i in np.flatnonzero(on_both):
        point = seg_start[i] + u[i] * seg[i]
        at_cap_end = min(
            float(np.linalg.norm(point - cap[0])),
            float(np.linalg.norm(point - cap[-1])),
        )
        if at_cap_end < 1e-9:
            continue
        out.append(point)
    return out


def _interior_junctions(strips):
    webs = _by_kind(strips, "web")
    caps = _by_kind(strips, "cap")
    for web in webs:
        for cap in caps:
            for point in _axis_crossings(web, cap):
                yield web, cap, point


@pytest.mark.parametrize("chord_m", CHORD_M)
@pytest.mark.parametrize("twist_deg", TWIST_DEG)
@pytest.mark.parametrize("layout_key", LAYOUTS)
def test_web_carries_a_node_at_every_interior_cap_crossing(layout_key, twist_deg, chord_m):
    strips = _prepared(layout_key, twist_deg, chord_m)
    found = 0
    for web, _cap, point in _interior_junctions(strips):
        found += 1
        gap = float(np.linalg.norm(web - point, axis=1).min())
        assert gap <= _MAX_WEB_GAP_M, (
            f"{layout_key} @ {twist_deg} deg, chord {chord_m} m: a web crosses a cap "
            f"interior but its nearest node is {gap * 1e6:.1f} um from the crossing. "
            "The junction is conforming only through the mesher's chord-scaled "
            "ENDPOINT_TOL_FRAC. insert_cap_web_interior_junctions should insert the "
            "solved crossing into the web as well as the cap."
        )
    assert found > 0, (
        f"{layout_key} @ {twist_deg} deg, chord {chord_m} m produced no interior "
        "cap-web crossings, so this case pins nothing. Either the layout changed or "
        "the crossing detector is broken — check before relaxing this."
    )


@pytest.mark.parametrize("chord_m", CHORD_M)
@pytest.mark.parametrize("twist_deg", TWIST_DEG)
@pytest.mark.parametrize("layout_key", LAYOUTS)
def test_cap_still_carries_its_node_at_every_interior_crossing(layout_key, twist_deg, chord_m):
    """Guards the swap: fixing the web side must not lose the cap side."""
    strips = _prepared(layout_key, twist_deg, chord_m)
    for _web, cap, point in _interior_junctions(strips):
        gap = float(np.linalg.norm(cap - point, axis=1).min())
        assert gap <= _MAX_CAP_GAP_M, (
            f"{layout_key} @ {twist_deg} deg, chord {chord_m} m: the cap's nearest node "
            f"is {gap * 1e6:.1f} um from an interior web crossing. Placing a web vertex "
            "exactly on the cap turns the crossing into a tangency, and "
            "intersect_open_polylines_2d then stops finding it — which moves the defect "
            "from the web to the cap instead of fixing it."
        )
