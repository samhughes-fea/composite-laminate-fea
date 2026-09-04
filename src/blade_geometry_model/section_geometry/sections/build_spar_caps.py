"""Build spar-cap wall recipes and SDF projections from CapPlacementRule.

Assemble authors frozen :class:`CapWall` recipes (G-RECIPE SoT), then projects
to SDF IR. Web-subtract remains an SDF-only post-step and is not encoded on
the recipe parameters.
"""

from __future__ import annotations

from typing import Any

from blade_structure_utilities.geometry_utilities.section_geometry.recipes.walls import (
    CapWall,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.ir import (
    Expr,
    Subtract,
    union_expr,
)

from ..layout.cap_placement import CapPlacementRule
from ..layout.section_axes import max_thickness_chord_x, pitch_axis_x_from_le
from .cap_feasibility import cap_feasibility_clamp
from .clip_algebra import _parallel_web_strip_clip, web_station_projection
from blade_structure_utilities.geometry_utilities.section_geometry.recipes.sdf_ir.spar_cap import (
    SparCap,
)
from .labels import ComponentLabel
from .web_layout import inner_y_at_x, inner_y_at_xs


def _label_str(label: Any) -> str:
    return str(getattr(label, "value", label))


def _flapwise_strip_params(nx, ny, c_lo, c_hi) -> dict[str, Any]:
    """Kwargs mirroring a ``_parallel_web_strip_clip`` for the Shapely emitter."""
    return {
        "flapwise_nx": float(nx),
        "flapwise_ny": float(ny),
        "flapwise_c_lo": float(min(c_lo, c_hi)),
        "flapwise_c_hi": float(max(c_lo, c_hi)),
        "flapwise_clip_mode": "strip",
    }


def _wrap_expr_cap(base_cap: SparCap, expr: Expr) -> SparCap:
    out = SparCap.__new__(SparCap)
    out.surface = base_cap.surface
    out.x_start = base_cap.x_start
    out.x_end = base_cap.x_end
    out.cap_height = base_cap.cap_height
    out.skin_thickness = base_cap.skin_thickness
    out.twist_angle = base_cap.twist_angle
    out._af = base_cap._af
    out._strip_clip = base_cap._strip_clip
    out._camber_xy = getattr(base_cap, "_camber_xy", None)
    for _fw in (
        "flapwise_nx",
        "flapwise_ny",
        "flapwise_c_lo",
        "flapwise_c_hi",
        "flapwise_clip_mode",
    ):
        setattr(out, _fw, getattr(base_cap, _fw, None))
    out.expr = expr
    out._expr = expr
    return out


def _cap_wall(
    *,
    skin_thickness: float,
    x_start: float,
    x_end: float,
    cap_height: float,
    surface: str,
    twist_angle: float = 0.0,
    fw: dict[str, Any] | None = None,
) -> CapWall:
    fw = fw or {}
    return CapWall(
        skin_thickness=float(skin_thickness),
        x_start=float(x_start),
        x_end=float(x_end),
        cap_height=float(cap_height),
        surface=str(surface),
        twist_angle=float(twist_angle),
        flapwise_nx=fw.get("flapwise_nx"),
        flapwise_ny=fw.get("flapwise_ny"),
        flapwise_c_lo=fw.get("flapwise_c_lo"),
        flapwise_c_hi=fw.get("flapwise_c_hi"),
        flapwise_clip_mode=fw.get("flapwise_clip_mode"),
    )


def _project_cap(
    wall: CapWall,
    airfoil_sdf,
    *,
    airfoil_expr_node,
    camber_xy=None,
    strip_clip=None,
) -> SparCap:
    cap = wall.to_sdf_component(
        airfoil_sdf, camber_xy=camber_xy, airfoil_expr_node=airfoil_expr_node
    )
    if strip_clip is not None:
        cap._strip_clip = strip_clip
    return cap


def build_spar_caps(
    airfoil_sdf,
    skin_thickness,
    xs,
    anchors,
    cap_h_upper,
    cap_h_lower,
    web_components,
    *,
    cap_placement: CapPlacementRule,
    airfoil_expr_node,
    all_flapwise: bool,
    c_station,
    nx,
    ny,
    N: int,
    pitch_fr: float,
    fhw: float,
    dhw: float,
    y_search,
    phi_inner_ref,
) -> tuple[Any | None, Any | None, dict[str, Any], dict[str, CapWall]]:
    """Return (cap_upper, cap_lower, unrotated_SparCap, CapWall recipes).

    CapWall recipes are authored first from :class:`CapPlacementRule`; SDF
    components are projections. Family letters are not accepted here.
    """
    rule = cap_placement

    if rule.kind == "none":
        return None, None, {}, {}

    web_exprs = [w.expr for w in web_components]
    web_union = union_expr(web_exprs) if web_exprs else None
    unrotated: dict[str, Any] = {}
    recipes: dict[str, CapWall] = {}
    cap_upper = cap_lower = None

    if rule.kind == "continuous_box":
        if N < 1:
            raise ValueError(
                "continuous_box cap placement requires at least one web "
                f"(got N={N})."
            )
        x_cap_start = xs[0]
        x_cap_end = xs[-1]
        x_cap_start, x_cap_end, cap_h_upper, cap_h_lower, _clamp_info = (
            cap_feasibility_clamp(
                airfoil_sdf,
                skin_thickness,
                x_cap_start,
                x_cap_end,
                cap_h_upper,
                cap_h_lower,
                y_search=y_search,
                phi_inner_ref=phi_inner_ref,
                aft_half_depth_rule=True,
            )
        )
        cap_strip = None
        cap_fw: dict[str, Any] = {}
        if all_flapwise and c_station is not None:
            probes = inner_y_at_xs(
                airfoil_sdf,
                skin_thickness,
                [float(x_cap_start), float(x_cap_end)],
                y_search=y_search,
                phi_inner=phi_inner_ref,
                raise_on_miss=False,
            )
            cys = []
            for xq, pair in zip((x_cap_start, x_cap_end), probes):
                if pair is None:
                    cys.append(0.0)
                else:
                    cys.append(0.5 * (float(pair[0]) + float(pair[1])))
            c_lo_cap = web_station_projection(nx, ny, float(x_cap_start), cys[0])
            c_hi_cap = web_station_projection(nx, ny, float(x_cap_end), cys[1])
            d_stat = abs(c_lo_cap - c_hi_cap)
            chord_scale = float(getattr(airfoil_sdf, "chord", 1.0))
            if d_stat > 1e-9 * max(chord_scale, 1e-9):
                cap_strip = _parallel_web_strip_clip(nx, ny, c_lo_cap, c_hi_cap)
                cap_fw = _flapwise_strip_params(nx, ny, c_lo_cap, c_hi_cap)
        _camber = _clamp_info.get("camber_xy")
        wall_u = _cap_wall(
            skin_thickness=skin_thickness,
            x_start=x_cap_start,
            x_end=x_cap_end,
            cap_height=cap_h_upper,
            surface="suction_surface",
            fw=cap_fw,
        )
        wall_l = _cap_wall(
            skin_thickness=skin_thickness,
            x_start=x_cap_start,
            x_end=x_cap_end,
            cap_height=cap_h_lower,
            surface="pressure_surface",
            fw=cap_fw,
        )
        recipes[_label_str(ComponentLabel.SPAR_CAP_SUCTION_SURFACE)] = wall_u
        recipes[_label_str(ComponentLabel.SPAR_CAP_PRESSURE_SURFACE)] = wall_l
        cap_upper = _project_cap(
            wall_u,
            airfoil_sdf,
            airfoil_expr_node=airfoil_expr_node,
            camber_xy=_camber,
            strip_clip=cap_strip,
        )
        cap_lower = _project_cap(
            wall_l,
            airfoil_sdf,
            airfoil_expr_node=airfoil_expr_node,
            camber_xy=_camber,
            strip_clip=cap_strip,
        )
        unrotated[ComponentLabel.SPAR_CAP_SUCTION_SURFACE] = cap_upper
        unrotated[ComponentLabel.SPAR_CAP_PRESSURE_SURFACE] = cap_lower
        if web_union is not None:
            cap_upper = _wrap_expr_cap(cap_upper, Subtract(cap_upper.expr, web_union))
            cap_lower = _wrap_expr_cap(cap_lower, Subtract(cap_lower.expr, web_union))
    elif rule.kind == "fixed_band":
        anchor = rule.anchor or "max_thickness"
        half = float(rule.half_width) if rule.half_width is not None else float(fhw)
        if anchor == "pitching":
            x_c = pitch_axis_x_from_le(airfoil_sdf, pitch_fr)
        else:
            x_c = max_thickness_chord_x(airfoil_sdf)
        x_lo = x_c - half
        x_hi = x_c + half
        x_lo, x_hi, cap_h_upper, cap_h_lower, _clamp_b = cap_feasibility_clamp(
            airfoil_sdf,
            skin_thickness,
            x_lo,
            x_hi,
            cap_h_upper,
            cap_h_lower,
            y_search=y_search,
            phi_inner_ref=phi_inner_ref,
            aft_half_depth_rule=False,
        )
        _camber_b = _clamp_b.get("camber_xy")
        strip_b = None
        strip_b_fw: dict[str, Any] = {}
        if all_flapwise and c_station is not None:
            y_tc, y_bc = inner_y_at_x(
                airfoil_sdf,
                skin_thickness,
                x_c,
                y_search=y_search,
                phi_inner=phi_inner_ref,
            )
            cy_c = 0.5 * (y_tc + y_bc)
            c_lo = web_station_projection(nx, ny, x_lo, cy_c)
            c_hi = web_station_projection(nx, ny, x_hi, cy_c)
            strip_b = _parallel_web_strip_clip(nx, ny, c_lo, c_hi)
            strip_b_fw = _flapwise_strip_params(nx, ny, c_lo, c_hi)
        wall_u = _cap_wall(
            skin_thickness=skin_thickness,
            x_start=x_lo,
            x_end=x_hi,
            cap_height=cap_h_upper,
            surface="suction_surface",
            fw=strip_b_fw,
        )
        wall_l = _cap_wall(
            skin_thickness=skin_thickness,
            x_start=x_lo,
            x_end=x_hi,
            cap_height=cap_h_lower,
            surface="pressure_surface",
            fw=strip_b_fw,
        )
        recipes[_label_str(ComponentLabel.SPAR_CAP_SUCTION_SURFACE)] = wall_u
        recipes[_label_str(ComponentLabel.SPAR_CAP_PRESSURE_SURFACE)] = wall_l
        cap_upper = _project_cap(
            wall_u,
            airfoil_sdf,
            airfoil_expr_node=airfoil_expr_node,
            camber_xy=_camber_b,
            strip_clip=strip_b,
        )
        cap_lower = _project_cap(
            wall_l,
            airfoil_sdf,
            airfoil_expr_node=airfoil_expr_node,
            camber_xy=_camber_b,
            strip_clip=strip_b,
        )
        unrotated[ComponentLabel.SPAR_CAP_SUCTION_SURFACE] = cap_upper
        unrotated[ComponentLabel.SPAR_CAP_PRESSURE_SURFACE] = cap_lower
        if web_union is not None:
            cap_upper = _wrap_expr_cap(cap_upper, Subtract(cap_upper.expr, web_union))
            cap_lower = _wrap_expr_cap(cap_lower, Subtract(cap_lower.expr, web_union))
    elif rule.kind == "per_web_pads":
        if N < 1:
            raise ValueError(
                "per_web_pads cap placement requires at least one web "
                f"(got N={N})."
            )
        _clamped_c = [
            cap_feasibility_clamp(
                airfoil_sdf,
                skin_thickness,
                xs[i] - dhw,
                xs[i] + dhw,
                cap_h_upper,
                cap_h_lower,
                y_search=y_search,
                phi_inner_ref=phi_inner_ref,
                aft_half_depth_rule=False,
            )
            for i in range(N)
        ]
        if _clamped_c:
            cap_h_upper = min(float(c[2]) for c in _clamped_c)
            cap_h_lower = min(float(c[3]) for c in _clamped_c)

        caps_u = []
        caps_l = []
        for i in range(N):
            x_lo, x_hi = float(_clamped_c[i][0]), float(_clamped_c[i][1])
            _camber_c = _clamped_c[i][4].get("camber_xy")
            strip_c = None
            strip_c_fw: dict[str, Any] = {}
            if all_flapwise and c_station is not None:
                cy_i = 0.5 * (anchors[i][0] + anchors[i][1])
                c_lo = web_station_projection(nx, ny, x_lo, cy_i)
                c_hi = web_station_projection(nx, ny, x_hi, cy_i)
                strip_c = _parallel_web_strip_clip(nx, ny, c_lo, c_hi)
                strip_c_fw = _flapwise_strip_params(nx, ny, c_lo, c_hi)
            wall_u = _cap_wall(
                skin_thickness=skin_thickness,
                x_start=x_lo,
                x_end=x_hi,
                cap_height=cap_h_upper,
                surface="suction_surface",
                fw=strip_c_fw,
            )
            wall_l = _cap_wall(
                skin_thickness=skin_thickness,
                x_start=x_lo,
                x_end=x_hi,
                cap_height=cap_h_lower,
                surface="pressure_surface",
                fw=strip_c_fw,
            )
            recipes[f"spar_cap_suction_surface_{i}"] = wall_u
            recipes[f"spar_cap_pressure_surface_{i}"] = wall_l
            cu = _project_cap(
                wall_u,
                airfoil_sdf,
                airfoil_expr_node=airfoil_expr_node,
                camber_xy=_camber_c,
                strip_clip=strip_c,
            )
            cl = _project_cap(
                wall_l,
                airfoil_sdf,
                airfoil_expr_node=airfoil_expr_node,
                camber_xy=_camber_c,
                strip_clip=strip_c,
            )
            caps_u.append(cu)
            caps_l.append(cl)
            unrotated[f"spar_cap_suction_surface_{i}"] = cu
            unrotated[f"spar_cap_pressure_surface_{i}"] = cl
        # Continuous labels point at the first pad's recipe for midline emit;
        # discrete labels remain in recipes for constructive unions.
        recipes[_label_str(ComponentLabel.SPAR_CAP_SUCTION_SURFACE)] = recipes[
            "spar_cap_suction_surface_0"
        ]
        recipes[_label_str(ComponentLabel.SPAR_CAP_PRESSURE_SURFACE)] = recipes[
            "spar_cap_pressure_surface_0"
        ]
        cap_upper_expr = union_expr([c.expr for c in caps_u])
        cap_lower_expr = union_expr([c.expr for c in caps_l])
        if web_union is not None:
            cap_upper_expr = Subtract(cap_upper_expr, web_union)
            cap_lower_expr = Subtract(cap_lower_expr, web_union)
        cap_upper = _wrap_expr_cap(caps_u[0], cap_upper_expr)
        cap_lower = _wrap_expr_cap(caps_l[0], cap_lower_expr)

    return cap_upper, cap_lower, unrotated, recipes


__all__ = ["build_spar_caps"]
