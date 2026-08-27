"""
ShellMidlineStrip
=================
FE-agnostic DTO carrying one subcomponent's mid-surface locus and thickness
for handoff from ``section_geometry`` to a shell mesh builder.

**Boundary contract:**

* This record is a *geometric locus*, not an SDF evaluation cache.  The
  ``midline_twisted_pitch_axis_blade_frame`` array is the materialised polyline
  of the subcomponent's mid-surface in
  ``twisted_pitch_axis_blade_frame`` (**B**) — storage ``(X_B, Y_B)`` with
  ``+Y_B`` toward the TE and the pitch axis at the origin (see
  ``geometry_utilities.coordinate_frames``). Producers map NACA / S authoring
  arrays through
  :func:`~blade_structure_utilities.geometry_utilities.coordinate_frames.naca_to_twisted_pitch_axis_blade_frame`
  (alias ``chord_to_blade``).

* It carries no MITC4-, ``Panel``-, laminate-, or ``n_elements``-level
  information; those details are added downstream in ``section_shell_fea``.

* Consumers (e.g. ``shell_mesh_inputs_from_strips``) must not call any SDF
  evaluation (``section[label](x, y)``) after this record exists — the polyline
  is the sole geometry source beyond this point.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class ShellMidlineStrip:
    """Mid-surface strip for one SDF subcomponent; FE-kernel-agnostic.

    Parameters
    ----------
    label
        Component key from ``SectionMidlineHost.components_unrotated`` or
        ``spar_cap_components_unrotated``, or a hierarchical skin panel label
        (e.g. ``"skin_suction_surface:bay_0"``, ``"shear_web_0"``,
        ``"spar_cap_suction_surface"``).
    kind
        Shell role: ``"skin"``, ``"web"``, or ``"cap"``.
    midline_twisted_pitch_axis_blade_frame
        ``(N, 2)`` polyline in ``twisted_pitch_axis_blade_frame`` (**B**).
    thickness_m
        Full laminate through-thickness in metres.
    closed
        ``True`` only for a legacy full outer-skin loop; hierarchical skin
        arcs are open (``False``).
    surface
        For caps only: ``"suction_surface"`` or ``"pressure_surface"``
        (legacy ``"upper"`` / ``"lower"`` still accepted at emit).  ``None``
        otherwise.
    alignment
        For webs only: ``"chord_normal"`` or ``"flapwise"``.  ``None``
        otherwise.
    skin_side
        For skin only: ``"suction_surface"`` or ``"pressure_surface"``.
        ``None`` for web/cap.
    skin_arc
        For skin only after topology: ``"leading_edge"``, ``"bay"``, or
        ``"trailing_edge"``.  ``None`` before hierarchical split / for web/cap.
    bay_index
        For skin only when ``skin_arc == "bay"``: zero-based bay index between
        consecutive webs (``0`` … ``n_webs-2``).  ``None`` otherwise.
    """

    label: str
    kind: str
    midline_twisted_pitch_axis_blade_frame: NDArray[np.float64]
    thickness_m: float
    closed: bool = False
    surface: str | None = None
    alignment: str | None = None
    skin_side: str | None = None
    skin_arc: str | None = None
    bay_index: int | None = None

    def arc_length_m(self) -> float:
        """Total polyline arc length in metres (twisted pitch-axis blade frame)."""
        pts = self.midline_twisted_pitch_axis_blade_frame
        if pts.shape[0] < 2:
            return 0.0
        d = np.diff(pts, axis=0)
        return float(np.sum(np.hypot(d[:, 0], d[:, 1])))


__all__ = ["ShellMidlineStrip"]
