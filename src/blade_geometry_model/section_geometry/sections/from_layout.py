"""Build :class:`MultiCellSection` from a :class:`SystemLayoutSpec`.

Single production host path for every registered layout key (including
``0A`` / ``0B``). Cap-family and orientation come from the layout; thickness
and twist are free DVs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from blade_structure_utilities.geometry_utilities.section_geometry.api.kwarg_aliases import (
    resolve_shear_web_thickness,
    resolve_skin_thickness,
    resolve_spar_cap_thickness,
    resolve_twist_rad,
)
from blade_structure_utilities.geometry_utilities.section_geometry.layout.system_layout import (
    SystemLayoutSpec,
)
from blade_structure_utilities.geometry_utilities.section_geometry.midlines.section_midline_host import (
    SectionMidlineHost,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import (
    AirfoilSDF,
)

# Matches the former OuterSkinOnlySection band half-width for zero-web family B.
_ZERO_WEB_CAP_HALF_BAND_FRAC = 0.10


def fixed_cap_anchor_from_layout(layout: SystemLayoutSpec) -> str:
    """Map layout spar-cap positioning onto MultiCell ``fixed_cap_anchor`` (family B)."""
    if str(layout.structural_family).upper() != "B":
        return "pitching"
    pos = str(layout.spar_cap_positioning or "").lower()
    if pos == "max_thickness":
        return "max_thickness"
    return "pitching"


def multicell_from_layout(
    airfoil: AirfoilSDF,
    layout: SystemLayoutSpec,
    *,
    twist_rad: float | None = None,
    twist_angle_rad: float | None = None,
    twist_angle: float | None = None,
    skin_thickness: float | None = None,
    spar_cap_thickness: float | None = None,
    shear_web_thickness: float | None = None,
    web_thickness: float | None = None,
    cap_height: float | None = None,
    web_x_positions_m: Sequence[float] | None = None,
    web_y_coords: Sequence[tuple[float, float]] | None = None,
    stage_sink: dict[str, float] | None = None,
) -> SectionMidlineHost:
    """Assemble a sized :class:`MultiCellSection` for any catalogue layout key."""
    from blade_structure_utilities.geometry_utilities.section_geometry.sections.multicell import (
        MultiCellSection,
    )

    skin = resolve_skin_thickness(
        skin_thickness=skin_thickness, required=True
    )
    spar = resolve_spar_cap_thickness(
        spar_cap_thickness=spar_cap_thickness,
        cap_height=cap_height,
        required=True,
    )
    web = resolve_shear_web_thickness(
        shear_web_thickness=shear_web_thickness,
        web_thickness=web_thickness,
        required=True,
    )
    twist = resolve_twist_rad(
        twist_rad=twist_rad,
        twist_angle_rad=twist_angle_rad,
        twist_angle=twist_angle,
    )

    xs: list[float]
    if web_x_positions_m is not None:
        xs = [float(x) for x in web_x_positions_m]
    else:
        xs = [float(f) * float(airfoil.chord) for f in layout.web_chord_fracs]
    if web_x_positions_m is None and len(xs) != int(layout.n_webs):
        raise ValueError(
            f"web_chord_fracs length ({len(layout.web_chord_fracs)}) must "
            f"equal n_webs ({layout.n_webs}) for key {layout.key!r}."
        )

    align = "flapwise" if layout.web_orientation == "flapwise" else "chord_normal"
    y_coords = None
    if web_y_coords is not None:
        y_coords = [(float(yt), float(yb)) for yt, yb in web_y_coords]
        if len(y_coords) != len(xs):
            raise ValueError(
                f"web_y_coords length ({len(y_coords)}) must match "
                f"web_x_positions length ({len(xs)})."
            )

    fhw: float | None = None
    if int(layout.n_webs) == 0 and str(layout.structural_family).upper() == "B":
        fhw = _ZERO_WEB_CAP_HALF_BAND_FRAC * float(airfoil.chord)

    return MultiCellSection(
        airfoil,
        web_x_positions=list(xs),
        web_thickness=float(web),
        web_alignment=align,
        cap_height=float(spar),
        skin_thickness=float(skin),
        twist_angle=float(twist),
        core_enabled=True,
        structural_family=layout.structural_family,
        fixed_cap_anchor=fixed_cap_anchor_from_layout(layout),
        fixed_cap_chord_half_width=fhw,
        web_y_coords=y_coords,
        stage_sink=stage_sink,
    )


__all__ = [
    "fixed_cap_anchor_from_layout",
    "multicell_from_layout",
]
