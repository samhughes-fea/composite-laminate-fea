"""Realistic lower bounds (m) on explicit SDF wall-solid thickness.

These floors are applied when building :class:`MultiCellSection` and when mapping
optimisation design variables to section strips, so unphysically thin inputs are
not silently used. They are geometric manufacturing minima, not ply / laminate
schedules (those belong to section_bind / section_layup / section_schedule).
"""

from __future__ import annotations

# Conservative wall-solid floors: shell, shear web, and spar-cap thickness
# are kept at or above typical GFRP/CFRP manufacturing minimums for structural walls.
MIN_REALISTIC_SKIN_WALL_THICKNESS_M = 0.0025
MIN_REALISTIC_WEB_WALL_THICKNESS_M = 0.0040
MIN_REALISTIC_SPAR_WALL_THICKNESS_M = 0.0050

# One-release private aliases (not re-exported on the package barrel __all__).
MIN_REALISTIC_SKIN_LAMINATE_THICKNESS_M = MIN_REALISTIC_SKIN_WALL_THICKNESS_M
MIN_REALISTIC_WEB_LAMINATE_THICKNESS_M = MIN_REALISTIC_WEB_WALL_THICKNESS_M
MIN_REALISTIC_SPAR_LAMINATE_THICKNESS_M = MIN_REALISTIC_SPAR_WALL_THICKNESS_M


def clamp_skin_thickness_m(t: float) -> float:
    return max(float(t), MIN_REALISTIC_SKIN_WALL_THICKNESS_M)


def clamp_web_thickness_m(t: float) -> float:
    return max(float(t), MIN_REALISTIC_WEB_WALL_THICKNESS_M)


def clamp_spar_thickness_m(t: float) -> float:
    return max(float(t), MIN_REALISTIC_SPAR_WALL_THICKNESS_M)


# One-release private alias.
clamp_spar_laminate_thickness_m = clamp_spar_thickness_m
