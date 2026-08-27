"""
sections.multicell
==================
MultiCellSection — generalised N-web blade section with N+1 sandwich-core bays.
"""

from __future__ import annotations

from blade_structure_utilities.geometry_utilities.section_contract.errors import (
    InfeasibleSectionGeometry,
)

from typing import Any

import numpy as np

from blade_structure_utilities.geometry_utilities.section_geometry.sdf.ir import Offset, Rotate, union_expr
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.profiling import timed_stage
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.transforms import rotate_field

from ..layout.thickness_limits import (
    clamp_skin_thickness_m,
    clamp_spar_laminate_thickness_m,
    clamp_web_thickness_m,
)
from ..layout.structural import parse_fixed_cap_anchor, parse_structural_family
from .clips import (
    _parallel_web_half_gt,
    _parallel_web_half_lt,
    _parallel_web_strip_clip,
    airfoil_expr,
    flapwise_web_normal,
    web_station_projection,
)
from .components import LEInsert, OuterSkin, SandwichCore, ShearWeb, TEInsert
from .components.base import expr_callable, twist_component
from .labels import ComponentLabel
from .spar_family import build_spar_caps
from .web_layout import flapwise_web_sframe_inputs, resolve_web_anchors


class MultiCellSection:
    """N-web generalised blade section (N+1 structural bays, N+1 foam cores when enabled)."""

    def __init__(
        self,
        airfoil_sdf,
        web_x_positions,
        web_thickness=0.004,
        web_alignment="chord_normal",
        cap_height=0.012,
        skin_thickness=0.003,
        twist_angle=0.0,
        web_y_coords=None,
        trailing_edge_insert_x_m=None,
        leading_edge_insert_x_m=None,
        le_radius=None,
        core_enabled=True,
        y_search=None,
        structural_family="D",
        fixed_cap_anchor="pitching",
        pitch_fraction_of_chord_from_le=1.0 / 3.0,
        fixed_cap_chord_half_width=None,
        discrete_cap_chord_half_width=None,
        *,
        stage_sink: dict[str, float] | None = None,
    ):
        xs_requested = sorted(float(x) for x in web_x_positions)
        self._structural_family = parse_structural_family(structural_family)
        if len(xs_requested) < 1 and self._structural_family not in ("A", "B"):
            raise ValueError(
                "web_x_positions is empty, which is only supported for "
                f"structural_family 'A' or 'B' (got {self._structural_family!r}). "
                "Family 'C' builds one spar cap per web (nothing to build with zero "
                "webs); family 'D' spans a cap between the outermost webs "
                "(undefined with zero webs)."
            )

        skin_thickness = clamp_skin_thickness_m(skin_thickness)

        self._af = airfoil_sdf
        self._skin_t = float(skin_thickness)
        self._twist = float(twist_angle)
        if self._structural_family in ("B", "C"):
            from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import AirfoilSDF as _AirfoilSDF

            if not isinstance(airfoil_sdf, _AirfoilSDF):
                raise TypeError(
                    "structural_family 'B' or 'C' requires airfoil_sdf to be "
                    "AirfoilSDF (pitching / max-thickness anchors)."
                )

        self._airfoil_expr = airfoil_expr(airfoil_sdf)
        if self._airfoil_expr is None:
            raise ValueError("MultiCellSection requires AirfoilSDF with vertices.")

        self._components: dict[str, Any] = {}

        _chord = float(getattr(airfoil_sdf, "chord", 1.0))
        _f_anchor = (
            parse_fixed_cap_anchor(fixed_cap_anchor)
            if self._structural_family == "B"
            else None
        )
        _pitch_fr = float(pitch_fraction_of_chord_from_le)
        _fhw = (
            float(fixed_cap_chord_half_width)
            if fixed_cap_chord_half_width is not None
            else 0.05 * _chord
        )
        _dhw = (
            float(discrete_cap_chord_half_width)
            if discrete_cap_chord_half_width is not None
            else 0.04 * _chord
        )

        with timed_stage("assemble_skin", stage_sink):
            # SS/PS half-annuli (suction = camber-upper, pressure = camber-lower).
            skin_ss = OuterSkin(
                airfoil_sdf,
                skin_thickness,
                airfoil_expr_node=self._airfoil_expr,
                skin_side="suction_surface",
            )
            skin_ps = OuterSkin(
                airfoil_sdf,
                skin_thickness,
                airfoil_expr_node=self._airfoil_expr,
                skin_side="pressure_surface",
            )
            self._components[ComponentLabel.SKIN_SUCTION_SURFACE] = skin_ss
            self._components[ComponentLabel.SKIN_PRESSURE_SURFACE] = skin_ps
            # Boundary SDFs stay full-annulus (cores/webs/inserts use the cavity).
            skin_outer_sdf = skin_ss.outer_sdf
            skin_inner_sdf = skin_ss.inner_sdf
            self._skin_outer_boundary_expr = Offset(self._airfoil_expr, amount=0.0)
            self._skin_inner_boundary_expr = Offset(self._airfoil_expr, amount=-skin_thickness)
            phi_inner_ref = expr_callable(Offset(self._airfoil_expr, amount=-skin_thickness))

        with timed_stage("assemble_anchors", stage_sink):
            if web_y_coords is None:
                resolved = resolve_web_anchors(
                    airfoil_sdf,
                    skin_thickness,
                    xs_requested,
                    y_search=y_search,
                    phi_inner=phi_inner_ref,
                )
                if xs_requested and not resolved:
                    raise InfeasibleSectionGeometry(
                        "No feasible web anchors: local thickness is smaller than "
                        f"inner-skin offset (skin_thickness={skin_thickness:.6g}) "
                        f"at requested x={xs_requested}."
                    )
                xs = [a[0] for a in resolved]
                anchors = [(a[1], a[2]) for a in resolved]
            else:
                xs = list(xs_requested)
                anchors = [(float(yt), float(yb)) for yt, yb in web_y_coords]
                if len(anchors) != len(xs):
                    raise ValueError(f"web_y_coords must have {len(xs)} entries.")

        N = len(xs)
        if np.isscalar(web_thickness):
            web_thicknesses = [float(web_thickness)] * N
        else:
            web_thicknesses = [float(t) for t in web_thickness]
            if len(web_thicknesses) != len(xs_requested):
                raise ValueError(
                    f"web_thickness must be scalar or length {len(xs_requested)}."
                )
            # If some webs were dropped, keep LE-most thicknesses in order.
            web_thicknesses = web_thicknesses[:N]
        web_thicknesses = [clamp_web_thickness_m(t) for t in web_thicknesses]

        if isinstance(web_alignment, str):
            web_alignments = [web_alignment] * N
        else:
            web_alignments = list(web_alignment)
            if len(web_alignments) != len(xs_requested):
                raise ValueError(
                    f"web_alignment must be scalar or length {len(xs_requested)}."
                )
            web_alignments = web_alignments[:N]

        if np.isscalar(cap_height):
            cap_h_upper = cap_h_lower = float(cap_height)
        else:
            cap_h_upper, cap_h_lower = float(cap_height[0]), float(cap_height[1])
        cap_h_upper = clamp_spar_laminate_thickness_m(cap_h_upper)
        cap_h_lower = clamp_spar_laminate_thickness_m(cap_h_lower)

        with timed_stage("assemble_webs", stage_sink):
            all_flapwise = N > 0 and all(a == "flapwise" for a in web_alignments)
            if all_flapwise:
                _nx, _ny = flapwise_web_normal(float(twist_angle))
                c_station = [
                    web_station_projection(
                        _nx, _ny, xs[i], 0.5 * (anchors[i][0] + anchors[i][1])
                    )
                    for i in range(N)
                ]
            else:
                _nx = _ny = None
                c_station = None

            flapwise_present = any(a == "flapwise" for a in web_alignments)
            needs_b_frame_lookup = flapwise_present and abs(float(twist_angle)) > 1e-10
            phi_inner_b = None
            y_search_b = y_search
            if needs_b_frame_lookup:
                phi_inner_b = rotate_field(phi_inner_ref, float(twist_angle))
                verts = getattr(airfoil_sdf, "vertices", None)
                if verts is not None:
                    arr = np.asarray(verts, dtype=float)
                    cos_t = float(np.cos(float(twist_angle)))
                    sin_t = float(np.sin(float(twist_angle)))
                    y_b_vals = sin_t * arr[:, 0] + cos_t * arr[:, 1]
                    y_search_b = (float(y_b_vals.min()) - 0.1, float(y_b_vals.max()) + 0.1)
                elif y_search_b is None:
                    y_search_b = (-1.5, 1.5)

            web_components = []
            for i, (x, t, align, (y_top, y_bot)) in enumerate(
                zip(xs, web_thicknesses, web_alignments, anchors)
            ):
                if align == "flapwise" and needs_b_frame_lookup:
                    x_top_S, y_top_S, x_bot_S, y_bot_S = flapwise_web_sframe_inputs(
                        x, y_top, y_bot, twist_angle, phi_inner_b, y_search_b
                    )
                else:
                    x_top_S = x
                    x_bot_S = x
                    y_top_S = y_top
                    y_bot_S = y_bot

                web = ShearWeb(
                    airfoil_sdf=airfoil_sdf,
                    skin_thickness=skin_thickness,
                    x_top=x_top_S,
                    y_top=y_top_S,
                    x_bot=x_bot_S,
                    y_bot=y_bot_S,
                    thickness=t,
                    alignment=align,
                    twist_angle=float(twist_angle),
                    airfoil_expr_node=self._airfoil_expr,
                )
                label = f"shear_web_{i}"
                self._components[label] = web
                web_components.append(web)

        sf = self._structural_family
        cap_upper = cap_lower = None
        spar_cap_components_unrotated: dict[str, Any] = {}

        with timed_stage("assemble_caps", stage_sink):
            if sf != "A":
                cap_upper, cap_lower, spar_cap_components_unrotated = build_spar_caps(
                    sf,
                    airfoil_sdf,
                    skin_thickness,
                    xs,
                    anchors,
                    cap_h_upper,
                    cap_h_lower,
                    web_components,
                    airfoil_expr_node=self._airfoil_expr,
                    all_flapwise=all_flapwise,
                    c_station=c_station,
                    nx=_nx,
                    ny=_ny,
                    N=N,
                    f_anchor=_f_anchor,
                    pitch_fr=_pitch_fr,
                    fhw=_fhw,
                    dhw=_dhw,
                    y_search=y_search,
                    phi_inner_ref=phi_inner_ref,
                )
                self._components[ComponentLabel.SPAR_CAP_SUCTION_SURFACE] = cap_upper
                self._components[ComponentLabel.SPAR_CAP_PRESSURE_SURFACE] = cap_lower

        self._spar_cap_components_unrotated = dict(spar_cap_components_unrotated)

        laminates_for_core = (
            list(web_components) if sf == "A" else [cap_upper, cap_lower] + web_components
        )
        laminate_exprs = [c.expr for c in laminates_for_core if c is not None]

        with timed_stage("assemble_cores", stage_sink):
            if core_enabled and N >= 1:
                n_bays = N + 1
                for k in range(n_bays):
                    if all_flapwise and c_station is not None:
                        if k == 0:
                            sclip = _parallel_web_half_lt(_nx, _ny, c_station[0])
                            fw_mode = "half_lt"
                            c_lo, c_hi = float(c_station[0]), None
                        elif k == n_bays - 1:
                            sclip = _parallel_web_half_gt(_nx, _ny, c_station[-1])
                            fw_mode = "half_gt"
                            c_lo, c_hi = float(c_station[-1]), None
                        else:
                            sclip = _parallel_web_strip_clip(
                                _nx, _ny, c_station[k - 1], c_station[k]
                            )
                            fw_mode = "strip"
                            c_lo = float(min(c_station[k - 1], c_station[k]))
                            c_hi = float(max(c_station[k - 1], c_station[k]))
                        core = SandwichCore(
                            airfoil_sdf=airfoil_sdf,
                            skin_thickness=skin_thickness,
                            strip_clip=sclip,
                            airfoil_expr_node=self._airfoil_expr,
                            exclusion_exprs=laminate_exprs,
                            bay_mode="flapwise",
                            flapwise_nx=float(_nx),
                            flapwise_ny=float(_ny),
                            flapwise_c_lo=c_lo,
                            flapwise_c_hi=c_hi,
                            flapwise_clip_mode=fw_mode,
                        )
                    else:
                        if k == 0:
                            x_s, x_e = None, xs[0]
                        elif k == n_bays - 1:
                            x_s, x_e = xs[-1], None
                        else:
                            x_s, x_e = xs[k - 1], xs[k]
                        core = SandwichCore(
                            airfoil_sdf=airfoil_sdf,
                            skin_thickness=skin_thickness,
                            x_start=x_s,
                            x_end=x_e,
                            airfoil_expr_node=self._airfoil_expr,
                            exclusion_exprs=laminate_exprs,
                            bay_mode="chordwise",
                        )
                    self._components[f"sandwich_core_{k}"] = core
            elif core_enabled and N == 0:
                # Zero webs: a single whole-envelope bay (no chordwise/flapwise
                # split point exists), excluding whatever cap regions were built.
                core = SandwichCore(
                    airfoil_sdf=airfoil_sdf,
                    skin_thickness=skin_thickness,
                    x_start=None,
                    x_end=None,
                    airfoil_expr_node=self._airfoil_expr,
                    exclusion_exprs=laminate_exprs,
                    bay_mode="chordwise",
                )
                self._components["sandwich_core_0"] = core

        if trailing_edge_insert_x_m is not None:
            te = TEInsert(
                airfoil_sdf=airfoil_sdf,
                skin_thickness=skin_thickness,
                x_start=float(trailing_edge_insert_x_m),
                airfoil_expr_node=self._airfoil_expr,
            )
            self._components[ComponentLabel.TRAILING_EDGE_INSERT] = te

        if leading_edge_insert_x_m is not None:
            le_x = 0.0
            try:
                le_x = float(airfoil_sdf.leading_edge[0])
            except AttributeError:
                pass
            le = LEInsert(
                airfoil_sdf=airfoil_sdf,
                skin_thickness=skin_thickness,
                x_end=float(leading_edge_insert_x_m),
                le_x=le_x,
                le_y=0.0,
                radius=le_radius,
                airfoil_expr_node=self._airfoil_expr,
            )
            self._components[ComponentLabel.LEADING_EDGE_INSERT] = le

        self._components_unrotated = dict(self._components)
        self._skin_outer_boundary_unrotated_sdf = skin_outer_sdf
        self._skin_inner_boundary_unrotated_sdf = skin_inner_sdf
        if abs(self._twist) > 1e-10:
            skin_outer_sdf = rotate_field(skin_outer_sdf, self._twist)
            skin_inner_sdf = rotate_field(skin_inner_sdf, self._twist)
            twist_expr = Rotate(self._airfoil_expr, angle=self._twist, cx=0.0, cy=0.0)
            self._skin_outer_boundary_expr = Offset(twist_expr, amount=0.0)
            self._skin_inner_boundary_expr = Offset(twist_expr, amount=-skin_thickness)
            self._components = {
                lbl: twist_component(comp, self._twist)
                for lbl, comp in self._components_unrotated.items()
            }
        self._skin_outer_boundary_sdf = skin_outer_sdf
        self._skin_inner_boundary_sdf = skin_inner_sdf
        self._eval_union_expr = union_expr(
            [c.expr for c in self._components.values()]
        )

    def __getitem__(self, label):
        if label not in self._components:
            raise KeyError(f"Unknown component '{label}'. Available: {self.labels}")
        return self._components[label]

    def __iter__(self):
        return iter(self._components)

    def __len__(self):
        return len(self._components)

    @property
    def labels(self):
        return list(self._components.keys())

    @property
    def airfoil(self):
        return self._af

    @property
    def twist_rad(self) -> float:
        """Section twist angle in radians (S → B frame)."""
        return float(self._twist)

    @property
    def underlying_section(self):
        """Concrete section graph host (self for :class:`MultiCellSection`)."""
        return self

    @property
    def components(self) -> dict[str, Any]:
        """Active (possibly twisted) labelled component map."""
        return self._components

    @property
    def components_unrotated(self) -> dict[str, Any]:
        """Public chord-frame skin/web/core map (:class:`SectionMidlineHost`)."""
        return self._components_unrotated

    @property
    def spar_cap_components_unrotated(self) -> dict[str, Any]:
        """Public chord-frame spar-cap map (:class:`SectionMidlineHost`)."""
        return dict(self._spar_cap_components_unrotated)

    @property
    def structural_family(self):
        return self._structural_family

    def eval(self, label, x, y, memo=None):
        return self._components[label](x, y, memo=memo)

    def eval_all(self, x, y):
        memo: dict = {}
        return {label: comp(x, y, memo=memo) for label, comp in self._components.items()}

    def eval_union(self, x, y):
        from blade_structure_utilities.geometry_utilities.section_geometry.sdf.ir import eval_expr_batch

        return eval_expr_batch(self._eval_union_expr, x, y, {})

    @classmethod
    def d_spar(cls, airfoil_sdf, web_x=0.25, **kwargs):
        return cls(airfoil_sdf, web_x_positions=[web_x], **kwargs)

    @classmethod
    def twin_web(cls, airfoil_sdf, x_fore=0.20, x_aft=0.50, **kwargs):
        return cls(airfoil_sdf, web_x_positions=[x_fore, x_aft], **kwargs)

    @classmethod
    def torsion_box(cls, airfoil_sdf, x_fore=0.15, x_mid=0.35, x_aft=0.55, **kwargs):
        return cls(airfoil_sdf, web_x_positions=[x_fore, x_mid, x_aft], **kwargs)

    @property
    def n_webs(self):
        return sum(
            1
            for k in self._components
            if str(getattr(k, "value", k)).startswith(("shear_web_", "web_"))
        )

    @property
    def n_cells(self):
        return self.n_webs + 1

    def __repr__(self):
        return (
            f"MultiCellSection("
            f"structural_family={self._structural_family!r}, "
            f"n_webs={self.n_webs}, "
            f"n_cells={self.n_cells}, "
            f"twist={np.degrees(self._twist):.1f}°, "
            f"components={self.labels})"
        )
