"""Shear web subcomponent."""

from __future__ import annotations

import numpy as np

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

    def midline_polyline(self, n=20):
        n_use = max(2, int(n))
        top = np.array([self.x_top, self.y_top], dtype=float)
        bot = np.array([self.x_bot, self.y_bot], dtype=float)
        return np.linspace(top, bot, n_use)

    def __repr__(self):
        return (
            f"ShearWeb(x=[{self.x_top:.3g},{self.x_bot:.3g}], "
            f"alignment={self.alignment!r}, "
            f"twist={np.degrees(self.twist_angle):.2f}°, "
            f"thickness={self.thickness:.3g})"
        )
