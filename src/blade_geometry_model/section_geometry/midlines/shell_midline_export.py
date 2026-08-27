"""
shell_midline_export
====================
Export ``section_geometry`` subcomponent midlines as FE-agnostic
:class:`ShellMidlineStrip` records in the blade (B) frame.

**Dependency rule:** this module may import from ``blade_structure_utilities.geometry_utilities.section_contract``
and from ``blade_structure_utilities.geometry_utilities.section_geometry``, but must **never** import from
``blade_structure_utilities.fem_utilities.section_shell_model``.

**Strip order:** ``build_shell_midline_strips`` yields skins and webs in
``components_unrotated`` dict-insertion order, then spar caps in
``spar_cap_components_unrotated`` dict-insertion order.  Any consumer that
cares about a canonical ordering (e.g. ``skin → caps → webs`` as required by
``bind_shell_material_zones``) must sort or reorder independently.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from blade_structure_utilities.geometry_utilities.section_contract.shell_midline_strip import ShellMidlineStrip
from blade_structure_utilities.geometry_utilities.section_geometry.midlines.section_midline_host import (
    CapShellComponentLike,
    SectionMidlineHost,
    ShellComponentLike,
    SkinShellComponentLike,
    WebShellComponentLike,
)


def rotate_chord_to_blade(
    points_S: NDArray[np.float64], twist_rad: float
) -> NDArray[np.float64]:
    """Rotate ``(N, 2)`` chord-frame points by ``+twist_rad`` into the B-frame.

    Mirrors the rotation that :class:`MultiCellSection` applies to every
    component's SDF when ``twist_angle != 0``: ``x' = R(twist) @ x`` about
    the origin (``cx=0``, ``cy=0``).

    Parameters
    ----------
    points_S
        ``(N, 2)`` array of points in the chord (S) frame.
    twist_rad
        Section twist angle in radians.

    Returns
    -------
    NDArray[np.float64]
        ``(N, 2)`` array of points rotated into the blade (B) frame.
    """
    if abs(twist_rad) < 1e-15:
        return np.asarray(points_S, dtype=float).copy()
    c = float(np.cos(twist_rad))
    s = float(np.sin(twist_rad))
    p = np.asarray(points_S, dtype=float)
    return np.column_stack([c * p[:, 0] - s * p[:, 1], s * p[:, 0] + c * p[:, 1]])


def _skin_side_from_label(label: object) -> str | None:
    """``suction_surface`` / ``pressure_surface`` from a skin label, or ``None``.

    Accepts long labels and legacy ``SS`` / ``PS`` / ``outer_skin_*`` tails.
    """
    key = str(getattr(label, "value", label)).lower()
    if "suction" in key or key.endswith("_ss") or key == "ss":
        return "suction_surface"
    if "pressure" in key or key.endswith("_ps") or key == "ps":
        return "pressure_surface"
    return None


def build_shell_midline_strips(
    section: SectionMidlineHost,
    *,
    twist_rad: float,
    n_web_samples: int = 20,
    n_cap_samples: int = 80,
    chord_m: float | None = None,
    pivot_fraction: float | None = None,
) -> tuple[ShellMidlineStrip, ...]:
    """Extract per-subcomponent midline strips from a :class:`SectionMidlineHost`.

    Iterates ``components_unrotated`` (skin + webs) then
    ``spar_cap_components_unrotated`` (caps), calls ``midline_polyline()``
    on each subcomponent in its chord frame, and maps each polyline into the
    canonical **B frame** via
    :func:`coordinate_frames.naca_to_twisted_pitch_axis_blade_frame`
    (short alias ``chord_to_blade``).

    The map is a component **swap** plus a **pivot shift** plus the twist
    rotation, and all three matter. The SDF interior stays in the raw-NACA
    chord frame by design (``AirfoilSDF`` is built on
    ``(x_chord, y_thickness)`` with the LE at ``x = 0``); this function is the
    authoring→handoff boundary. Output arrays are ``(X_B, Y_B)`` with
    ``Y_LE < 0 < Y_TE`` and the pivot at the origin.

    A bare rotation (:func:`rotate_chord_to_blade`) is **not** sufficient — it
    leaves the array chordwise-first with its origin at the LE, which is the
    rotated-NACA adapter frame, not B. Everything downstream (``+x3``
    orientation, the flap/edge load-channel map, the section plot contract)
    reads canonical B.

    Parameters
    ----------
    section
        Section implementing :class:`SectionMidlineHost`.
    twist_rad
        Section twist in radians applied to every chord-frame midline.
    n_web_samples, n_cap_samples
        Number of sample points for web / cap polylines.  Skin midline
        resolution is set by the underlying airfoil tessellation.
    chord_m
        Section chord [m] for the pivot shift. Defaults to
        ``section.airfoil.chord``.
    pivot_fraction
        Pitch-axis chordline as a fraction of chord from the LE. Defaults to
        ``coordinate_frames.PIVOT_FRACTION_DEFAULT``.

    Returns
    -------
    tuple[ShellMidlineStrip, ...]
        Strips in dict-insertion order: skins + webs first, then caps.
    """
    from blade_structure_utilities.geometry_utilities.coordinate_frames import (
        PIVOT_FRACTION_DEFAULT,
        naca_to_twisted_pitch_axis_blade_frame,
    )

    try:
        components_S = section.components_unrotated
    except AttributeError as exc:
        raise ValueError(
            "section must expose public 'components_unrotated' "
            "(SectionMidlineHost). Expected MultiCellSection."
        ) from exc

    if chord_m is None:
        airfoil = getattr(section, "airfoil", None)
        chord_m = float(getattr(airfoil, "chord", 0.0) or 0.0)
    chord_m = float(chord_m)
    if chord_m <= 0.0:
        raise ValueError(
            "chord_m is required for the chord→B pivot shift and could not be read "
            "from section.airfoil.chord; pass chord_m explicitly."
        )
    f_pivot = (
        PIVOT_FRACTION_DEFAULT if pivot_fraction is None else float(pivot_fraction)
    )

    def _to_twisted_pitch_axis_blade_frame(mid_zero_twist_pitch_axis_station_frame):
        return naca_to_twisted_pitch_axis_blade_frame(
            mid_zero_twist_pitch_axis_station_frame, twist_rad, chord_m, f_pivot
        )

    def _label_key(label: object) -> str:
        """Stable string id; prefer Enum.value over ``ComponentLabel.NAME`` repr."""
        value = getattr(label, "value", None)
        if isinstance(value, str) and value:
            return value
        return str(label)

    strips: list[ShellMidlineStrip] = []

    # Web before skin: webs also satisfy SkinShellComponentLike (thickness + midline).
    for label, comp in components_S.items():
        if isinstance(comp, WebShellComponentLike):
            mid_S = comp.midline_polyline(n=n_web_samples)
            strips.append(
                ShellMidlineStrip(
                    label=_label_key(label),
                    kind="web",
                    midline_twisted_pitch_axis_blade_frame=_to_twisted_pitch_axis_blade_frame(mid_S),
                    thickness_m=float(comp.thickness),
                    closed=False,
                    alignment=str(comp.alignment),
                )
            )
        elif isinstance(comp, SkinShellComponentLike):
            mid_S = comp.midline_polyline()
            # The label already says which side this is (skin_suction_surface /
            # skin_pressure_surface), so tag it here rather than leaving
            # `_ensure_ss_ps_skins` to infer it a stage later. Its inference
            # falls back to a mean-y heuristic when the label yields nothing,
            # and that heuristic is what would misclassify a strongly cambered
            # or twisted section; setting the side at source means the emit
            # path never reaches it.
            side = _skin_side_from_label(label)
            strips.append(
                ShellMidlineStrip(
                    label=_label_key(label),
                    kind="skin",
                    midline_twisted_pitch_axis_blade_frame=_to_twisted_pitch_axis_blade_frame(mid_S),
                    thickness_m=float(comp.thickness),
                    # A suction/pressure-surface half-ring is an open arc; only an
                    # undivided skin is a closed ring. This was previously `True`
                    # for both, which `_ensure_ss_ps_skins` corrected downstream.
                    closed=side is None,
                    skin_side=side,
                )
            )

    try:
        cap_components = section.spar_cap_components_unrotated
    except AttributeError:
        cap_components = {}
    for label, comp in (cap_components or {}).items():
        if not isinstance(comp, CapShellComponentLike):
            continue
        mid_S = comp.midline_polyline(n=n_cap_samples)
        strips.append(
            ShellMidlineStrip(
                label=_label_key(label),
                kind="cap",
                midline_twisted_pitch_axis_blade_frame=_to_twisted_pitch_axis_blade_frame(mid_S),
                thickness_m=float(comp.cap_height),
                closed=False,
                surface=str(comp.surface),
            )
        )


    return tuple(strips)


__all__ = [
    "build_shell_midline_strips",
    "rotate_chord_to_blade",
    "SectionMidlineHost",
    "ShellComponentLike",
    "SkinShellComponentLike",
    "WebShellComponentLike",
    "CapShellComponentLike",
]
