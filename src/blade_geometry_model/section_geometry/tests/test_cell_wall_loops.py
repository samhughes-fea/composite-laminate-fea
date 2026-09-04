"""Unit tests for constructive void-cell wall loops."""

from __future__ import annotations

import numpy as np
import pytest

from blade_structure_utilities.geometry_utilities.section_geometry.cell_wall_loops.cell_wall_loops import (
    build_cell_wall_loops,
    cell_wall_loops_case_payload,
)
from blade_structure_utilities.geometry_utilities.section_contract import CellWallLoop, ShellMidlineStrip


def _rect_skin(*, width: float = 2.0, height: float = 1.0, t: float = 0.01) -> ShellMidlineStrip:
    w, h = 0.5 * width, 0.5 * height
    skin = np.array(
        [
            [w, 0.0],
            [w, h],
            [0.0, h],
            [-w, h],
            [-w, 0.0],
            [-w, -h],
            [0.0, -h],
            [w, -h],
            [w, 0.0],
        ],
        dtype=float,
    )
    return ShellMidlineStrip(
        label="outer_skin",
        kind="skin",
        midline_twisted_pitch_axis_blade_frame=skin,
        thickness_m=t,
        closed=True,
        surface=None,
        alignment=None,
    )


def _web(x: float, *, y0: float = 0.35, y1: float = -0.35, label: str = "shear_web_0") -> ShellMidlineStrip:
    """Open web that does **not** reach the skin (y=Â±0.5) â€” must be extrapolated."""
    return ShellMidlineStrip(
        label=label,
        kind="web",
        midline_twisted_pitch_axis_blade_frame=np.array([[x, y0], [x, y1]], dtype=float),
        thickness_m=0.008,
        closed=False,
        surface=None,
        alignment="chord_normal",
    )


def _point_on_skin(pt: np.ndarray, skin: np.ndarray, *, tol: float = 1e-8) -> bool:
    ring = skin[:-1] if np.hypot(*(skin[0] - skin[-1])) < 1e-12 else skin
    n = ring.shape[0]
    for i in range(n):
        a = ring[i]
        b = ring[(i + 1) % n]
        e = b - a
        L2 = float(np.dot(e, e))
        if L2 < 1e-30:
            continue
        u = float(np.dot(pt - a, e) / L2)
        if u < -1e-9 or u > 1.0 + 1e-9:
            continue
        proj = a + u * e
        if float(np.hypot(*(pt - proj))) <= tol:
            return True
    return False


def test_hierarchical_skin_arcs_use_ordered_ring_path():
    """Long skin_side/skin_arc tokens stitch via the hierarchical ring order."""
    from blade_structure_utilities.geometry_utilities.section_geometry.cell_wall_loops.cell_wall_geom import (
        stitch_skin_ring,
    )

    # Deliberately shuffled list order; hierarchical key must still TEâ†’LE then LEâ†’TE.
    skins = [
        ShellMidlineStrip(
            label="skin_pressure_surface:bay_0",
            kind="skin",
            midline_twisted_pitch_axis_blade_frame=np.array(
                [[0.0, -0.5], [0.5, -0.5]], dtype=float
            ),
            thickness_m=0.01,
            closed=False,
            skin_side="pressure_surface",
            skin_arc="bay",
            bay_index=0,
        ),
        ShellMidlineStrip(
            label="skin_suction_surface:trailing_edge",
            kind="skin",
            midline_twisted_pitch_axis_blade_frame=np.array(
                [[1.0, 0.5], [0.5, 0.5]], dtype=float
            ),
            thickness_m=0.01,
            closed=False,
            skin_side="suction_surface",
            skin_arc="trailing_edge",
        ),
        ShellMidlineStrip(
            label="skin_suction_surface:bay_0",
            kind="skin",
            midline_twisted_pitch_axis_blade_frame=np.array(
                [[0.5, 0.5], [0.0, 0.5]], dtype=float
            ),
            thickness_m=0.01,
            closed=False,
            skin_side="suction_surface",
            skin_arc="bay",
            bay_index=0,
        ),
        ShellMidlineStrip(
            label="skin_suction_surface:leading_edge",
            kind="skin",
            midline_twisted_pitch_axis_blade_frame=np.array(
                [[0.0, 0.5], [-0.5, 0.5], [-0.5, -0.5]], dtype=float
            ),
            thickness_m=0.01,
            closed=False,
            skin_side="suction_surface",
            skin_arc="leading_edge",
        ),
        ShellMidlineStrip(
            label="skin_pressure_surface:leading_edge",
            kind="skin",
            midline_twisted_pitch_axis_blade_frame=np.array(
                [[-0.5, -0.5], [0.0, -0.5]], dtype=float
            ),
            thickness_m=0.01,
            closed=False,
            skin_side="pressure_surface",
            skin_arc="leading_edge",
        ),
        ShellMidlineStrip(
            label="skin_pressure_surface:trailing_edge",
            kind="skin",
            midline_twisted_pitch_axis_blade_frame=np.array(
                [[0.5, -0.5], [1.0, -0.5], [1.0, 0.5]], dtype=float
            ),
            thickness_m=0.01,
            closed=False,
            skin_side="pressure_surface",
            skin_arc="trailing_edge",
        ),
    ]
    ring = stitch_skin_ring(skins)
    assert ring.shape[0] >= 8
    # Hierarchical order starts at suction trailing_edge tip (xâ‰ˆ1, yâ‰ˆ0.5).
    assert ring[0, 0] == pytest.approx(1.0, abs=1e-9)
    assert ring[0, 1] == pytest.approx(0.5, abs=1e-9)

    web = _web(0.0, y0=0.4, y1=-0.4)
    loops = build_cell_wall_loops([*skins, web])
    assert len(loops) == 2
    assert all(lp.is_closed() for lp in loops)


def test_no_web_copies_skin_ring():
    skin = _rect_skin()
    loops = build_cell_wall_loops([skin])
    assert len(loops) == 1
    loop = loops[0]
    assert isinstance(loop, CellWallLoop)
    assert loop.is_closed()
    assert loop.web_labels == ()
    assert loop.area_m2 == pytest.approx(2.0 * 1.0, rel=1e-9)
    # Closed polyline matches skin ring (up to starting vertex)
    assert loop.polyline_twisted_pitch_axis_blade_frame.shape[0] >= 4


def test_one_web_two_cells_extrapolate_to_skin():
    skin = _rect_skin()
    strips = [skin, _web(0.0)]
    loops = build_cell_wall_loops(strips)
    assert len(loops) == 2
    assert all(lp.is_closed() for lp in loops)
    assert sum(lp.area_m2 for lp in loops) == pytest.approx(2.0, rel=1e-6)
    # Each loop should contain points on the skin at y=Â±0.5 (extrapolated hits)
    for lp in loops:
        ys = lp.polyline_twisted_pitch_axis_blade_frame[:, 1]
        assert np.min(np.abs(ys - 0.5)) < 1e-8 or np.min(np.abs(ys + 0.5)) < 1e-8
        # Web label present
        assert "shear_web_0" in lp.web_labels
        # Intersection points lie on skin
        for pt in lp.polyline_twisted_pitch_axis_blade_frame:
            if abs(abs(pt[1]) - 0.5) < 1e-8 and abs(pt[0]) < 1e-8:
                assert _point_on_skin(pt, skin.midline_twisted_pitch_axis_blade_frame)


def test_two_webs_three_cells():
    skin = _rect_skin()
    strips = [skin, _web(-0.4, label="shear_web_0"), _web(0.4, label="shear_web_1")]
    loops = build_cell_wall_loops(strips)
    assert len(loops) == 3
    assert all(lp.is_closed() for lp in loops)
    assert sum(lp.area_m2 for lp in loops) == pytest.approx(2.0, rel=1e-5)
    assert loops[0].id == 0
    assert loops[-1].id == 2


def test_caps_ignored():
    skin = _rect_skin()
    cap = ShellMidlineStrip(
        label="cap_upper",
        kind="cap",
        midline_twisted_pitch_axis_blade_frame=np.array([[-0.3, 0.5], [0.3, 0.5]], dtype=float),
        thickness_m=0.02,
        closed=False,
        surface="upper",
        alignment=None,
    )
    loops = build_cell_wall_loops([skin, _web(0.0), cap])
    assert len(loops) == 2
    for lp in loops:
        assert "cap_upper" not in lp.web_labels
        assert "cap" not in lp.piece_labels


def test_short_web_hits_lie_on_skin_polyline():
    skin = _rect_skin()
    loops = build_cell_wall_loops([skin, _web(0.2, y0=0.2, y1=-0.2)])
    skin_pts = skin.midline_twisted_pitch_axis_blade_frame
    for lp in loops:
        # Corners of the web after extrapolation should be on top/bottom flanges
        tops = [pt for pt in lp.polyline_twisted_pitch_axis_blade_frame if abs(pt[1] - 0.5) < 1e-8]
        bots = [pt for pt in lp.polyline_twisted_pitch_axis_blade_frame if abs(pt[1] + 0.5) < 1e-8]
        assert tops and bots
        for pt in tops + bots:
            assert _point_on_skin(np.asarray(pt), skin_pts)


@pytest.mark.parametrize(
    "strips,expected_loops",
    [
        ([_rect_skin()], 1),
        ([_rect_skin(), _web(0.0)], 2),
        ([_rect_skin(), _web(-0.4, label="shear_web_0"), _web(0.4, label="shear_web_1")], 3),
    ],
)
def test_cell_wall_loops_case_payload_shape(strips, expected_loops):
    payload = cell_wall_loops_case_payload(strips, name=f"n_webs_{expected_loops - 1}")
    assert payload["name"] == f"n_webs_{expected_loops - 1}"
    assert payload["n_webs"] == expected_loops - 1
    assert payload["n_loops"] == expected_loops
    assert len(payload["loops"]) == expected_loops
    assert all(s["kind"] in ("skin", "web") for s in payload["strips"])
    for loop in payload["loops"]:
        assert isinstance(loop["id"], int)
        assert isinstance(loop["area_m2"], float)
        assert isinstance(loop["web_labels"], list)
        assert isinstance(loop["piece_labels"], list)
        assert isinstance(loop["polyline_twisted_pitch_axis_blade_frame"], list)
        assert len(loop["polyline_twisted_pitch_axis_blade_frame"]) >= 3
        assert all(len(pt) == 2 for pt in loop["polyline_twisted_pitch_axis_blade_frame"])
        assert all(isinstance(v, float) for pt in loop["polyline_twisted_pitch_axis_blade_frame"] for v in pt)
    for strip in payload["strips"]:
        assert isinstance(strip["midline_twisted_pitch_axis_blade_frame"], list)
        assert all(isinstance(v, float) for pt in strip["midline_twisted_pitch_axis_blade_frame"] for v in pt)

