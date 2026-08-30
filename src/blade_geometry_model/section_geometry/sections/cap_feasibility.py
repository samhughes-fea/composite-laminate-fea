"""Clamp spar-cap heights / chordwise extent so upper and lower caps never meet."""

from __future__ import annotations

import math

import numpy as np

from .web_layout import inner_y_at_xs

# Minimum void kept between upper and lower spar caps so the shear core
# (ellipse void) is never consumed: absolute floor and fraction of local depth.
MIN_CAP_VOID_ABS_M = 0.001
MIN_CAP_VOID_FRAC = 0.15

# Solids camber-clip resolution (SG-010). Chord-approx error of the cavity
# midline scales ~ band / n² for similar sections. Budget is well below the
# airfoil-polygon LE floor (~62 µm at n_points=200 / 1 m chord, SG-008), so
# solid areas inherit the polygon contract rather than this knob.
CAMBER_CLIP_DEV_BUDGET_M = 1e-6  # 1 µm
_CAMBER_CLIP_N_MIN = 33
# Fitted to measured 18.56 µm deviation at n=33 on a 0.50 m band (x/c 0.15–0.65
# at 1 m chord, NACA 2412, 6 mm skin): err ≈ C * band / n².
_CAMBER_CLIP_C = 18.56e-6 * (33**2) / 0.50


def default_camber_clip_n_samples(x_lo: float, x_hi: float) -> int:
    """Sample count so cavity-midline chord error stays within the solid-clip budget."""
    band = max(abs(float(x_hi) - float(x_lo)), 1e-12)
    n = int(math.ceil(math.sqrt(_CAMBER_CLIP_C * band / CAMBER_CLIP_DEV_BUDGET_M)))
    return max(_CAMBER_CLIP_N_MIN, n)


def cap_feasibility_clamp(
    airfoil_sdf,
    skin_thickness,
    x_lo: float,
    x_hi: float,
    cap_h_upper: float,
    cap_h_lower: float,
    *,
    y_search,
    phi_inner_ref,
    n_samples: int | None = None,
    aft_half_depth_rule: bool = False,
) -> tuple[float, float, float, float, dict]:
    """Clamp cap heights / chordwise extent so the caps never meet.

    Samples the inner-cavity depth over ``[x_lo, x_hi]`` and:
    1. restricts the cap band to the contiguous interval (around the deepest
       point) where ``cap_h_upper + cap_h_lower + void_min(x) <= depth(x)``;
    2. if no such interval exists, scales both cap heights proportionally so
       the caps fit over the central half of the band.

    With ``aft_half_depth_rule=True`` (continuous-spar families), the extent
    is never trimmed: each cap height is instead clamped to half the cavity
    depth at the aft end of the band (the aft web), so the caps span the full
    web-to-web band and at most butt at the cavity midline at the aft web.

    Returns ``(x_lo_eff, x_hi_eff, cap_h_upper_eff, cap_h_lower_eff, info)``.
    ``info["camber_xy"]`` holds sampled cavity-midline points for the cap split
    (solids / properties only — not shell midlines; see bug_log SG-010).

    Default ``n_samples`` is derived from band width so the clip polyline's
    chord-approximation stays within :data:`CAMBER_CLIP_DEV_BUDGET_M`.
    """
    caps_sum = float(cap_h_upper) + float(cap_h_lower)
    info: dict = {
        "clamped_extent": False,
        "scaled_heights": False,
        "scale": 1.0,
        "camber_xy": None,
    }
    if caps_sum <= 0.0 or x_hi <= x_lo:
        return float(x_lo), float(x_hi), float(cap_h_upper), float(cap_h_lower), info

    n = (
        int(n_samples)
        if n_samples is not None
        else default_camber_clip_n_samples(x_lo, x_hi)
    )
    xs_q = np.linspace(float(x_lo), float(x_hi), n)
    depth = np.full(xs_q.shape, -np.inf)
    y_mid = np.full(xs_q.shape, np.nan)
    # One shared φ grid eval for all sample stations. Feasibility only needs
    # depth / camber to clamp accuracy; skip per-crossing bisection refine.
    probes = inner_y_at_xs(
        airfoil_sdf,
        skin_thickness,
        xs_q,
        y_search=y_search,
        phi_inner=phi_inner_ref,
        bisection_iters=0,
        raise_on_miss=False,
    )
    for i, pair in enumerate(probes):
        if pair is None:
            continue
        yt, yb = pair
        depth[i] = float(yt) - float(yb)
        y_mid[i] = 0.5 * (float(yt) + float(yb))
    if not np.any(np.isfinite(depth)):
        return float(x_lo), float(x_hi), float(cap_h_upper), float(cap_h_lower), info
    ok = np.isfinite(y_mid)
    if np.any(ok):
        info["camber_xy"] = np.column_stack([xs_q[ok], y_mid[ok]])

    if aft_half_depth_rule:
        # Continuous spar: cap height limited to half the cavity depth at the
        # aft web (the shallowest end of the band), full extent preserved.
        i_fin = np.where(np.isfinite(depth))[0]
        h_allow = 0.5 * float(depth[i_fin[-1]])
        if h_allow > 0.0:
            h_u = min(float(cap_h_upper), h_allow)
            h_l = min(float(cap_h_lower), h_allow)
            if h_u < float(cap_h_upper) or h_l < float(cap_h_lower):
                info["scaled_heights"] = True
                info["scale"] = (h_u + h_l) / caps_sum
            return float(x_lo), float(x_hi), h_u, h_l, info
        return float(x_lo), float(x_hi), float(cap_h_upper), float(cap_h_lower), info

    allowed = depth - np.maximum(MIN_CAP_VOID_ABS_M, MIN_CAP_VOID_FRAC * depth)
    if caps_sum > float(np.max(allowed)):
        # Caps do not fit anywhere at sized thickness: scale to fit the
        # central half of the band (falls back to the deepest point).
        i0, i1 = len(xs_q) // 4, (3 * len(xs_q)) // 4 + 1
        a_central = float(np.min(allowed[i0:i1]))
        target = max(a_central, 0.5 * float(np.max(allowed)))
        if target <= 0.0:
            target = float(np.max(allowed))
        if target <= 0.0:
            return float(x_lo), float(x_hi), float(cap_h_upper), float(cap_h_lower), info
        scale = target / caps_sum
        cap_h_upper = float(cap_h_upper) * scale
        cap_h_lower = float(cap_h_lower) * scale
        caps_sum = cap_h_upper + cap_h_lower
        info["scaled_heights"] = True
        info["scale"] = scale

    def _contiguous_extent(caps_sum_q: float) -> tuple[float, float]:
        feasible = caps_sum_q <= allowed + 1e-12
        if not np.any(feasible):
            return float(x_lo), float(x_hi)
        i_deep = int(np.nanargmax(np.where(np.isfinite(depth), depth, -np.inf)))
        if not feasible[i_deep]:
            i_deep = int(np.where(feasible)[0][0])
        lo_i = i_deep
        while lo_i > 0 and feasible[lo_i - 1]:
            lo_i -= 1
        hi_i = i_deep
        while hi_i < len(xs_q) - 1 and feasible[hi_i + 1]:
            hi_i += 1
        return float(xs_q[lo_i]), float(xs_q[hi_i])

    x_lo_eff, x_hi_eff = _contiguous_extent(caps_sum)
    if (
        not info["scaled_heights"]
        and (x_hi_eff - x_lo_eff) < 0.5 * (float(x_hi) - float(x_lo))
    ):
        # Barely-feasible dead zone: the caps fit only in a sliver around the
        # deepest point, so clamping the extent would collapse the cap (and
        # make stiffness *decrease* with growing cap height). Scale the
        # heights with the same central-half rule as the infeasible branch
        # instead, keeping the extent continuous with neighbouring sizings.
        i0, i1 = len(xs_q) // 4, (3 * len(xs_q)) // 4 + 1
        a_central = float(np.min(allowed[i0:i1]))
        target = max(a_central, 0.5 * float(np.max(allowed)))
        if target > 0.0:
            scale = min(1.0, target / caps_sum)
            cap_h_upper = float(cap_h_upper) * scale
            cap_h_lower = float(cap_h_lower) * scale
            caps_sum = cap_h_upper + cap_h_lower
            info["scaled_heights"] = True
            info["scale"] = scale
            x_lo_eff, x_hi_eff = _contiguous_extent(caps_sum)
    if x_lo_eff > float(x_lo) + 1e-12 or x_hi_eff < float(x_hi) - 1e-12:
        info["clamped_extent"] = True
    return x_lo_eff, x_hi_eff, float(cap_h_upper), float(cap_h_lower), info


# Historic private alias used by factory / tests / examples.
_cap_feasibility_clamp = cap_feasibility_clamp

__all__ = [
    "MIN_CAP_VOID_ABS_M",
    "MIN_CAP_VOID_FRAC",
    "CAMBER_CLIP_DEV_BUDGET_M",
    "default_camber_clip_n_samples",
    "cap_feasibility_clamp",
    "_cap_feasibility_clamp",
]
