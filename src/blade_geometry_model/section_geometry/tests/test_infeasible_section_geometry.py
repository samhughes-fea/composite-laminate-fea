"""Infeasible sections raise a type the sizing loop can catch.

A thickness search will inevitably propose sections that cannot be built — a cap
deeper than the local cavity, a skin that closes the section, a web with no
inner-skin intercept. Those must be *scored* as failed trials so the search backs
off, not raised through the station worker.

This used to be decided by substring-matching the exception message in
``optimize.py``, which meant any newly-worded or newly-added infeasibility became
a crash. These tests pin the type instead.
"""

from __future__ import annotations

import numpy as np
import pytest

from blade_structure_utilities.geometry_utilities.section_contract import (
    InfeasibleSectionGeometry,
)


def test_is_a_valueerror_subclass() -> None:
    """Pre-existing ``except ValueError`` handlers must keep working."""
    assert issubclass(InfeasibleSectionGeometry, ValueError)


def test_offset_ring_deeper_than_the_section_is_infeasible() -> None:
    """The direct oracle: no locus exists at a depth past the inscribed limit."""
    from blade_structure_utilities.geometry_utilities.section_geometry.constructive.helpers import (
        airfoil_offset_ring,
    )
    from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import (
        AirfoilSDF,
    )

    # chord 0.112 m has max inscribed depth ~7.84 mm.
    af = AirfoilSDF.from_naca_series(
        6, 63.0, 4.0, 15.0, n_points=200, chord=0.112, closed_te=True
    )
    airfoil_offset_ring(af, 0.003)  # feasible, must not raise

    with pytest.raises(InfeasibleSectionGeometry):
        airfoil_offset_ring(af, 0.009)


def test_bad_depth_argument_is_not_infeasibility() -> None:
    """A malformed request is a caller bug, not an unbuildable section.

    Keeping these distinct is the point: the sizing loop must not swallow real
    programming errors as failed trials.
    """
    from blade_structure_utilities.geometry_utilities.section_geometry.constructive.helpers import (
        airfoil_offset_ring,
    )
    from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import (
        AirfoilSDF,
    )

    af = AirfoilSDF.from_naca("0012", n_points=100, chord=1.0)
    with pytest.raises(ValueError) as exc:
        airfoil_offset_ring(af, -0.001)
    assert not isinstance(exc.value, InfeasibleSectionGeometry)


def test_web_anchors_and_skin_intercepts_are_infeasibility() -> None:
    """The two cases the old message allowlist covered, now matched by type."""
    from blade_structure_utilities.geometry_utilities.section_geometry.sections.web_layout import (
        inner_y_at_x,
    )
    from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import (
        AirfoilSDF,
    )

    af = AirfoilSDF.from_naca("0012", n_points=100, chord=1.0)
    # A skin thicker than the local half-thickness leaves no inner cavity.
    with pytest.raises(InfeasibleSectionGeometry):
        inner_y_at_x(af, 0.4, 0.95)


def test_sizing_loop_catches_infeasibility_by_type() -> None:
    """``optimize.py`` must no longer decide this by reading the message."""
    import inspect

    from blade_structure_precompute.module.section_selection.processing.shell_station import (
        optimize,
    )

    src = inspect.getsource(optimize)
    assert "except InfeasibleSectionGeometry" in src
    for stale in ("inner skin intercept", "no feasible web anchor"):
        assert stale not in src, (
            f"optimize.py still string-matches {stale!r}; the type check was "
            "meant to replace it"
        )


def _sizing_call(exc: Exception):
    """Drive ``size_station_against_ei`` with a geometry that always raises."""
    from unittest.mock import MagicMock, patch

    from blade_structure_precompute.module.section_selection.processing.shell_station.optimize import (
        size_station_against_ei,
    )

    t = np.linspace(0.0, 2.0 * np.pi, 60, endpoint=False)
    coords = np.column_stack([0.03 * np.sin(t), 0.5 + 0.5 * np.cos(t)])
    system = MagicMock()
    system.STRUCTURAL_SYSTEM_KEY = "SystemType2D-CN"
    system.n_cells = 3
    system.structural_family = "D"
    system.web_orientation = "chord_normal"

    def _always_raises(**_kwargs):
        raise exc

    with patch(
        "blade_structure_precompute.module.section_selection.processing"
        ".shell_station.optimize.evaluate_station",
        side_effect=_always_raises,
    ):
        return size_station_against_ei(
            system=system,
            station_idx=0,
            zL=0.5,
            coords=coords,
            metadata={"chord": 1.0, "twist_deg": 0.0},
            EI_req=1.0e9,
        )


def test_infeasible_geometry_is_a_failed_trial_not_a_crash() -> None:
    """Sizing must absorb infeasibility so the search can back off."""
    bin_obj, _ = _sizing_call(
        InfeasibleSectionGeometry("cap deeper than the local cavity")
    )
    assert bin_obj is not None


def test_a_real_bug_still_propagates() -> None:
    """The discrimination is the point: a plain ValueError must not be swallowed.

    Without this, the handler would quietly turn genuine defects into
    "this station is just infeasible" and the search would wander.
    """
    with pytest.raises(ValueError) as exc:
        _sizing_call(ValueError("some genuine defect"))
    assert not isinstance(exc.value, InfeasibleSectionGeometry)
