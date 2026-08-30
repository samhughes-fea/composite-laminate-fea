"""Shear web subcomponent."""

from __future__ import annotations

import numpy as np

from blade_structure_utilities.geometry_utilities.section_geometry.sdf.csg import offset
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.ir import Capsule, Intersect, Offset

from ..clips import airfoil_expr
from ..labels import ComponentLabel
from .base import SectionComponent


class ShearWeb(SectionComponent):
    """Constant-thickness shear web as a shell around a capsule axis."""

    label = ComponentLabel.SHEAR_WEB

    def __init__(
        self,
        airfoil_sdf,
        skin_thickness,
        x_top,
        y_top,
        x_bot,
        y_bot,
        thickness,
        alignment="chord_normal",
        twist_angle=0.0,
        *,
        airfoil_expr_node=None,
    ):
        if alignment not in ("chord_normal", "flapwise"):
            raise ValueError("alignment must be 'chord_normal' or 'flapwise'.")

        self.x_top = float(x_top)
        self.y_top = float(y_top)
        self.x_bot = float(x_bot)
        self.y_bot = float(y_bot)
        self.thickness = float(thickness)
        self.alignment = alignment
        self.twist_angle = float(twist_angle)
        self.skin_thickness = float(skin_thickness)
        self._af = airfoil_sdf

        poly = airfoil_expr_node if airfoil_expr_node is not None else airfoil_expr(airfoil_sdf)
        if poly is None:
            raise ValueError("ShearWeb requires an AirfoilSDF with vertices for IR evaluation.")

        r = thickness / 2.0
        # Extend the capsule axis beyond the inner-skin anchors so the round
        # end-caps land outside the cavity. The intersection with the cavity
        # then yields a clean constant-width strip flush against the skin;
        # otherwise the disk ends bite asymmetrically into slanted skins and
        # the web body appears tilted (runtime-confirmed on twisted sections).
        dx = float(x_top) - float(x_bot)
        dy = float(y_top) - float(y_bot)
        seg_len = float(np.hypot(dx, dy))
        ext = 2.0 * float(thickness) + float(skin_thickness)
        if seg_len > 1e-12:
            ux, uy = dx / seg_len, dy / seg_len
        else:
            ux, uy = 0.0, 1.0
        self.x_top_ext = float(x_top) + ux * ext
        self.y_top_ext = float(y_top) + uy * ext
        self.x_bot_ext = float(x_bot) - ux * ext
        self.y_bot_ext = float(y_bot) - uy * ext
        expr = Intersect(
            Capsule(
                ax=self.x_top_ext,
                ay=self.y_top_ext,
                bx=self.x_bot_ext,
                by=self.y_bot_ext,
                r=float(r),
            ),
            Offset(poly, amount=-skin_thickness),
        )
        super().__init__(expr)

    def _extend_to_skin_mid_surface(self, anchor, direction):
        """Walk ``anchor`` outward along ``direction`` onto the skin mid-surface.

        The anchors are inner-mould-line intercepts — the right locus for
        building the *solid*, but half a skin gauge short of where the web's
        **mid-surface** actually ends. A web mid-surface runs mid-surface to
        mid-surface; emitting it to the IML leaves it short at both ends and
        forces the topology pass to relocate the foot, which is what put a kink
        in it (see ``docs/bug_log.md``).

        The step is ``skin_thickness / 2`` divided by the cosine between the web
        axis and the local skin normal, so it is solved rather than assumed.
        """
        half_gauge = 0.5 * float(self.skin_thickness)
        if half_gauge <= 0.0:
            return np.asarray(anchor, dtype=float)

        phi_mid = offset(self._af, -half_gauge)
        step = np.asarray(direction, dtype=float)
        norm = float(np.linalg.norm(step))
        if norm <= 1e-15:
            return np.asarray(anchor, dtype=float)
        step = step / norm
        origin = np.asarray(anchor, dtype=float)

        def phi_at(t):
            p = origin + float(t) * step
            return float(phi_mid(np.array([p[0]]), np.array([p[1]]))[0])

        # phi < 0 at the anchor (inside the mid-surface) and must cross zero
        # within a couple of gauges even for a steeply raked web.
        lo, hi = 0.0, 4.0 * half_gauge
        phi_lo, phi_hi = phi_at(lo), phi_at(hi)
        if not (phi_lo <= 0.0 <= phi_hi):
            # Degenerate local geometry: fall back to the normal-distance step
            # rather than emitting something wilder than the anchor itself.
            return origin + half_gauge * step
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if phi_at(mid) <= 0.0:
                lo = mid
            else:
                hi = mid
        return origin + 0.5 * (lo + hi) * step

    def midline_polyline(self, n=20):
        n_use = max(2, int(n))
        top = np.array([self.x_top, self.y_top], dtype=float)
        bot = np.array([self.x_bot, self.y_bot], dtype=float)
        axis = top - bot
        return np.linspace(
            self._extend_to_skin_mid_surface(top, axis),
            self._extend_to_skin_mid_surface(bot, -axis),
            n_use,
        )

    def __repr__(self):
        return (
            f"ShearWeb(x=[{self.x_top:.3g},{self.x_bot:.3g}], "
            f"alignment={self.alignment!r}, "
            f"twist={np.degrees(self.twist_angle):.2f}°, "
            f"thickness={self.thickness:.3g})"
        )
