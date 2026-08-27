"""Build upper/lower spar caps for structural families A/B/C/D."""

from __future__ import annotations

from typing import Any

from blade_structure_utilities.geometry_utilities.section_geometry.sdf.ir import Expr, Subtract, union_expr

from .cap_feasibility import cap_feasibility_clamp
from .clips import _parallel_web_strip_clip, web_station_projection
from .components.spar_cap import SparCap
from ..layout.section_axes import max_thickness_chord_x, pitch_axis_x_from_le
from .labels import ComponentLabel
from .web_layout import inner_y_at_x, inner_y_at_xs


def _flapwise_strip_params(nx, ny, c_lo, c_hi) -> dict[str, Any]:
    """Kwargs mirroring a ``_parallel_web_strip_clip`` for the Shapely emitter.

    The IR path consumes the callable; the polygon path needs the parameters so
    it can clip the cap solid with :func:`flapwise_bay_clip` rather than infer
    the clip from the midline's chordwise extent.
    """
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


def build_spar_caps(
    sf: str,
    airfoil_sdf,
    skin_thickness,
    xs,
    anchors,
    cap_h_upper,
    cap_h_lower,
    web_components,
    *,
    airfoil_expr_node,
    all_flapwise: bool,
    c_station,
    nx,
    ny,
    N: int,
    f_anchor,
    pitch_fr: float,
    fhw: float,
    dhw: float,
    y_search,
    phi_inner_ref,
) -> tuple[Any | None, Any | None, dict[str, Any]]:
    """Return (cap_upper, cap_lower, unrotated_spar_cap_components)."""
    web_exprs = [w.expr for w in web_components]
    web_union = union_expr(web_exprs) if web_exprs else None
    unrotated: dict[str, Any] = {}
    cap_upper = cap_lower = None

    if sf == "D":
        x_cap_start = xs[0]
        x_cap_end = xs[-1]
        x_cap_start, x_cap_end, cap_h_upper, cap_h_lower, _clamp_info = cap_feasibility_clamp(
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
        cap_upper = SparCap(
            airfoil_sdf,
            skin_thickness,
            x_cap_start,
            x_cap_end,
            cap_h_upper,
            "suction_surface",
            strip_clip=cap_strip,
            airfoil_expr_node=airfoil_expr_node,
            camber_xy=_camber,
            **cap_fw,
        )
        cap_lower = SparCap(
            airfoil_sdf,
            skin_thickness,
            x_cap_start,
            x_cap_end,
            cap_h_lower,
            "pressure_surface",
            strip_clip=cap_strip,
            airfoil_expr_node=airfoil_expr_node,
            camber_xy=_camber,
            **cap_fw,
        )
        unrotated[ComponentLabel.SPAR_CAP_SUCTION_SURFACE] = cap_upper
        unrotated[ComponentLabel.SPAR_CAP_PRESSURE_SURFACE] = cap_lower
        if web_union is not None:
            cap_upper = _wrap_expr_cap(cap_upper, Subtract(cap_upper.expr, web_union))
            cap_lower = _wrap_expr_cap(cap_lower, Subtract(cap_lower.expr, web_union))
    elif sf == "B":
        if f_anchor == "pitching":
            x_c = pitch_axis_x_from_le(airfoil_sdf, pitch_fr)
        else:
            x_c = max_thickness_chord_x(airfoil_sdf)
        x_lo = x_c - fhw
        x_hi = x_c + fhw
        # Family B is a single continuous band, but unlike D it has no aft web
        # to key a half-depth rule on, so it uses the extent/scale path.
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
        cap_upper = SparCap(
            airfoil_sdf,
            skin_thickness,
            x_lo,
            x_hi,
            cap_h_upper,
            "suction_surface",
            strip_clip=strip_b,
            airfoil_expr_node=airfoil_expr_node,
            camber_xy=_camber_b,
            **strip_b_fw,
        )
        cap_lower = SparCap(
            airfoil_sdf,
            skin_thickness,
            x_lo,
            x_hi,
            cap_h_lower,
            "pressure_surface",
            strip_clip=strip_b,
            airfoil_expr_node=airfoil_expr_node,
            camber_xy=_camber_b,
            **strip_b_fw,
        )
        unrotated[ComponentLabel.SPAR_CAP_SUCTION_SURFACE] = cap_upper
        unrotated[ComponentLabel.SPAR_CAP_PRESSURE_SURFACE] = cap_lower
        if web_union is not None:
            cap_upper = _wrap_expr_cap(cap_upper, Subtract(cap_upper.expr, web_union))
            cap_lower = _wrap_expr_cap(cap_lower, Subtract(cap_lower.expr, web_union))
    elif sf == "C":
        # Discrete caps, one per web. Clamp each band against its own local
        # cavity depth, then take the common minimum: aft caps sit where the
        # section is shallowest, and letting each shrink independently would
        # make a nominally uniform discrete spar vary along the chord.
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
            caps_u.append(
                SparCap(
                    airfoil_sdf,
                    skin_thickness,
                    x_lo,
                    x_hi,
                    cap_h_upper,
                    "suction_surface",
                    strip_clip=strip_c,
                    airfoil_expr_node=airfoil_expr_node,
                    camber_xy=_camber_c,
                    **strip_c_fw,
                )
            )
            caps_l.append(
                SparCap(
                    airfoil_sdf,
                    skin_thickness,
                    x_lo,
                    x_hi,
                    cap_h_lower,
                    "pressure_surface",
                    strip_clip=strip_c,
                    airfoil_expr_node=airfoil_expr_node,
                    camber_xy=_camber_c,
                    **strip_c_fw,
                )
            )
        for i, (cu, cl) in enumerate(zip(caps_u, caps_l)):
            unrotated[f"spar_cap_suction_surface_{i}"] = cu
            unrotated[f"spar_cap_pressure_surface_{i}"] = cl
        cap_upper_expr = union_expr([c.expr for c in caps_u])
        cap_lower_expr = union_expr([c.expr for c in caps_l])
        if web_union is not None:
            cap_upper_expr = Subtract(cap_upper_expr, web_union)
            cap_lower_expr = Subtract(cap_lower_expr, web_union)
        cap_upper = _wrap_expr_cap(caps_u[0], cap_upper_expr)
        cap_lower = _wrap_expr_cap(caps_l[0], cap_lower_expr)

    return cap_upper, cap_lower, unrotated


__all__ = ["build_spar_caps"]
