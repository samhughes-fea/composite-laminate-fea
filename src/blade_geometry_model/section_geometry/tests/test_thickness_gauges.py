"""Independent SS/PS skin gauges and per-web thicknesses."""

from __future__ import annotations

from blade_structure_utilities.geometry_utilities.section_geometry.api.kwarg_aliases import (
    resolve_shear_web_thickness,
    resolve_skin_gauges,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import (
    AirfoilSDF,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sections.multicell import (
    MultiCellSection,
)

def test_resolve_skin_gauges_scalar_broadcasts():
    assert resolve_skin_gauges(skin_thickness=0.005) == (0.005, 0.005)

def test_resolve_skin_gauges_pair():
    assert resolve_skin_gauges(skin_thickness=(0.004, 0.006)) == (0.004, 0.006)

def test_resolve_shear_web_thickness_list():
    assert resolve_shear_web_thickness(shear_web_thickness=[0.005, 0.007]) == [
        0.005,
        0.007,
    ]

def test_multicell_asymmetric_skin_recipes():
    af = AirfoilSDF.from_naca("2412", n_points=80, chord=1.0)
    mcs = MultiCellSection(
        af,
        web_x_positions=[0.25, 0.5],
        skin_thickness=(0.004, 0.008),
        web_thickness=[0.005, 0.007],
        cap_height=0.01,
        structural_family="D",
        core_enabled=False,
    )
    ss = mcs.wall_recipes["skin_suction_surface"]
    ps = mcs.wall_recipes["skin_pressure_surface"]
    assert float(ss.thickness) == 0.004
    assert float(ps.thickness) == 0.008
    w0 = mcs.wall_recipes["shear_web_0"]
    w1 = mcs.wall_recipes["shear_web_1"]
    assert float(w0.thickness) == 0.005
    assert float(w1.thickness) == 0.007
