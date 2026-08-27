"""Resolve preferred long thickness / twist kwargs (optional secondary aliases)."""

from __future__ import annotations

from collections.abc import Sequence


def _pick_exclusive(
    preferred: float | None,
    aliases: Sequence[float | None],
    *,
    names: str,
    default: float | None = None,
    required: bool = False,
) -> float:
    """Return the single provided value among preferred + aliases.

    Conflict (two unequal non-None values) → ``ValueError``.
    """
    present: list[float] = []
    if preferred is not None:
        present.append(float(preferred))
    for a in aliases:
        if a is not None:
            present.append(float(a))
    if not present:
        if required:
            raise TypeError(f"Missing required thickness kwargs ({names})")
        if default is None:
            raise TypeError(f"Missing thickness kwargs ({names})")
        return float(default)
    first = present[0]
    for v in present[1:]:
        if v != first:
            raise ValueError(f"Conflicting thickness kwargs for {names}")
    return first


def resolve_skin_thickness(
    *,
    skin_thickness: float | None = None,
    default: float | None = None,
    required: bool = False,
) -> float:
    return _pick_exclusive(
        skin_thickness,
        (),
        names="skin_thickness",
        default=default,
        required=required,
    )


def resolve_spar_cap_thickness(
    *,
    spar_cap_thickness: float | None = None,
    cap_height: float | None = None,
    default: float | None = None,
    required: bool = False,
) -> float:
    return _pick_exclusive(
        spar_cap_thickness,
        (cap_height,),
        names="spar_cap_thickness / cap_height",
        default=default,
        required=required,
    )


def resolve_shear_web_thickness(
    *,
    shear_web_thickness: float | None = None,
    web_thickness: float | None = None,
    default: float | None = None,
    required: bool = False,
) -> float:
    return _pick_exclusive(
        shear_web_thickness,
        (web_thickness,),
        names="shear_web_thickness / web_thickness",
        default=default,
        required=required,
    )


def resolve_twist_rad(
    *,
    twist_rad: float | None = None,
    twist_angle_rad: float | None = None,
    twist_angle: float | None = None,
    default: float = 0.0,
) -> float:
    """Canonical twist [rad]. Aliases are also radians (not degrees)."""
    return _pick_exclusive(
        twist_rad,
        (twist_angle_rad, twist_angle),
        names="twist_rad / twist_angle_rad / twist_angle",
        default=default,
    )


def resolve_geometry_mode(token: str | None) -> str:
    """Map legacy ``airfoil_sdf_only`` → ``zero_web_catalogue``."""
    if token is None:
        return "multicell"
    t = str(token)
    if t == "airfoil_sdf_only":
        return "zero_web_catalogue"
    return t


__all__ = [
    "resolve_skin_thickness",
    "resolve_spar_cap_thickness",
    "resolve_shear_web_thickness",
    "resolve_twist_rad",
    "resolve_geometry_mode",
]
