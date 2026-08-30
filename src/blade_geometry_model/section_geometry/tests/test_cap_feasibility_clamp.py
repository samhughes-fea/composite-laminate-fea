"""Cap heights are clamped to what the local cavity can hold, in every family.

``_cap_feasibility_clamp`` was wired only to family D (continuous spar, via the
aft-web half-depth rule). Families B and C passed sized cap heights straight
through, so a cap deeper than the local cavity produced either an empty midline
or no offset locus at all — 49 of 261 catalogue combinations at absolute
thicknesses. The sizing-level bound (``_max_spar_from_cavity``) does not cover
this: it uses the section-wide flapwise extent of the *outer* contour, which says
nothing about the inner cavity at an aft discrete cap.

The extent/scale branch these tests exercise (``aft_half_depth_rule=False``) had
no callers and no coverage before this.
"""

from __future__ import annotations

import numpy as np
import pytest

from blade_structure_utilities.geometry_utilities.section_geometry.sections.spar_family import (
    _cap_feasibility_clamp,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sections.web_layout import (
    inner_y_at_x,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import AirfoilSDF


def _af(chord: float = 1.0):
    return AirfoilSDF.from_naca("0012", n_points=200, chord=chord)


def _clamp(af, skin_thickness, h_u, h_l, x_lo=0.30, x_hi=0.50, **kw):
    return _cap_feasibility_clamp(
        af, skin_thickness, x_lo, x_hi, h_u, h_l,
        y_search=None, phi_inner_ref=None, **kw,
    )


def test_feasible_caps_pass_through_untouched() -> None:
    """A cap that comfortably fits must not be clamped or rescaled."""
    af = _af()
    x_lo, x_hi, h_u, h_l, info = _clamp(af, 0.003, 0.004, 0.004)

    assert (h_u, h_l) == pytest.approx((0.004, 0.004))
    assert (x_lo, x_hi) == pytest.approx((0.30, 0.50))
    assert info["scaled_heights"] is False
    assert info["clamped_extent"] is False
    assert info["scale"] == pytest.approx(1.0)


def test_caps_too_deep_are_scaled_to_fit_the_cavity() -> None:
    """Caps that cannot fit must shrink, and must leave a void between them."""
    af = _af()
    skin_thickness = 0.003
    # The band allows a caps_sum of ~0.085-0.097 m; ask for 0.120 m.
    _lo, _hi, h_u, h_l, info = _clamp(af, skin_thickness, 0.060, 0.060)

    assert info["scaled_heights"] is True
    assert 0.0 < h_u < 0.060 and 0.0 < h_l < 0.060
    assert info["scale"] < 1.0

    # The clamped pair must still leave a residual cavity everywhere in the band.
    for xq in np.linspace(0.30, 0.50, 9):
        yt, yb = inner_y_at_x(af, skin_thickness, float(xq))
        assert h_u + h_l < (yt - yb), f"caps meet at x={xq:.3f}"


def test_clamp_is_monotone_in_requested_height() -> None:
    """Asking for more cap must never yield less cap.

    The scale branch divides by the requested sum, so a non-monotone result here
    would make the sizing loop's growth phase chase its own tail.
    """
    af = _af()
    heights = [_clamp(af, 0.003, h, h)[2] for h in (0.004, 0.016, 0.040, 0.060, 0.090)]
    assert heights == sorted(heights), heights


def test_camber_midline_is_returned_for_the_cap_split() -> None:
    """B and C previously split upper/lower on a flat half-plane."""
    af = _af()
    _lo, _hi, _hu, _hl, info = _clamp(af, 0.003, 0.004, 0.004)
    camber = info["camber_xy"]
    assert camber is not None and camber.shape[1] == 2 and camber.shape[0] >= 2
    assert np.all(np.isfinite(camber))


def test_default_camber_clip_n_samples_meets_budget() -> None:
    """SG-010: default density tracks band width for the 1 µm solid-clip budget."""
    from blade_structure_utilities.geometry_utilities.section_geometry.sections.cap_feasibility import (
        default_camber_clip_n_samples,
    )

    # Reference band x/c 0.15–0.65 at 1 m chord → ~142 samples (≥ 33 floor).
    n_1m = default_camber_clip_n_samples(0.15, 0.65)
    assert n_1m >= 140
    # Narrower tip-scale band needs fewer absolute samples but still ≥ floor.
    n_tip = default_camber_clip_n_samples(0.15 * 0.241, 0.65 * 0.241)
    assert n_tip >= 33
    assert n_tip < n_1m

    af = _af()
    _lo, _hi, _hu, _hl, info = _clamp(af, 0.003, 0.004, 0.004, x_lo=0.15, x_hi=0.65)
    assert info["camber_xy"].shape[0] == n_1m


@pytest.mark.parametrize("layout_key", ["0B", "1B-CN", "2C-CN", "5C-F", "3C-F"])
def test_short_chord_thick_cap_builds_for_families_b_and_c(layout_key: str) -> None:
    """The 49-case class: absolute thicknesses on a tip-scale chord.

    Before clamping was wired to B/C these raised — either no offset locus at
    all, or an empty cap strip rejected by the mesh worker.
    """
    from blade_structure_utilities.geometry_utilities.section_geometry.api.factory import (
        build_section_view,
        resolve_system_type,
    )
    from blade_structure_utilities.mesh_utilities.section_mesh.handoff._section_to_shell_inputs import (
        shell_mesh_inputs_from_section,
    )
    from blade_structure_utilities.mesh_utilities.section_mesh import (
        build_section_strip_mesh,
    )

    chord, twist = 0.112, float(np.deg2rad(1.5))
    af = AirfoilSDF.from_naca_series(
        6, 63.0, 4.0, 15.0, n_points=200, chord=chord, closed_te=True
    )
    section = build_section_view(
        af,
        resolve_system_type(layout_key),
        twist_angle_rad=twist,
        skin_thickness=0.003,
        web_thickness=0.003,
        cap_height=0.012,  # deeper than the ~7.8 mm inscribed depth if unclamped
    )
    shell = shell_mesh_inputs_from_section(
        section, twist_rad=twist, layout_key=layout_key,
        n_web_samples=20, n_cap_samples=80,
    )
    mesh = build_section_strip_mesh(
        shell, target_element_length_frac=0.012, endpoint_tol=1e-6
    )
    caps = [pm for pm in mesh.panel_meshes if pm.kind == "cap" and pm.yz_nodes.size]
    assert caps, f"{layout_key} produced no usable cap strips"
    for pm in caps:
        assert pm.thickness_m > 0.0
        assert pm.thickness_m <= 0.012 + 1e-12, "clamp must not grow the cap"


def test_family_d_still_uses_the_aft_web_half_depth_rule() -> None:
    """D keeps full extent and clamps height; it must not switch branches."""
    af = _af()
    # Aft-end (x=0.50) cavity depth is ~0.0997 m, so the rule allows ~0.0499 m.
    x_lo, x_hi, h_u, h_l, info = _clamp(
        af, 0.003, 0.060, 0.060, aft_half_depth_rule=True
    )
    assert (x_lo, x_hi) == pytest.approx((0.30, 0.50)), "extent must be preserved"
    assert info["clamped_extent"] is False
    assert h_u == h_l and h_u < 0.060
    assert h_u == pytest.approx(0.5 * 0.09971, rel=1e-3), "not the aft half-depth"
