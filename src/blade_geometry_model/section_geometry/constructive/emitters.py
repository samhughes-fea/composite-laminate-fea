"""Recipe-faithful constructive polygons for laminate subcomponents."""

from __future__ import annotations

from typing import Any

import numpy as np
from shapely.geometry import MultiPolygon, Polygon

from .helpers import (
    airfoil_polygon,
    chordwise_bay_clip,
    chordwise_box,
    ensure_polygon,
    flapwise_bay_clip,
    half_plane_clip,
    rotate_geom,
    stadium_polygon,
)


def _af_from_component(comp: Any):
    af = getattr(comp, "_af", None)
    if af is not None:
        return af
    raise ValueError(f"{type(comp).__name__} lacks airfoil reference (_af).")


def emit_outer_skin_polygon(
    comp: Any,
    *,
    airfoil_poly: Polygon | MultiPolygon | None = None,
    inner_cavity: Polygon | MultiPolygon | None = None,
) -> Polygon | MultiPolygon:
    """Skin annulus grown inward: airfoil polygon minus inner(−t) offset.

    When ``comp.skin_side`` is ``SS``/``PS``, the annulus is clipped to the
    suction (camber-upper) or pressure (camber-lower) half.
    """
    af = _af_from_component(comp)
    t = float(getattr(comp, "thickness"))
    if t <= 0:
        raise ValueError("OuterSkin thickness must be positive.")
    poly = airfoil_poly if airfoil_poly is not None else airfoil_polygon(af)
    inner = (
        inner_cavity
        if inner_cavity is not None
        else poly.buffer(-t, quad_segs=16, join_style=2, mitre_limit=5.0)
    )
    if inner.is_empty:
        annulus = ensure_polygon(poly)
    else:
        annulus = ensure_polygon(poly.difference(inner))

    side = getattr(comp, "skin_side", None)
    if side is None:
        return annulus
    s = str(side).strip().lower()
    if s in ("ss", "suction_surface", "upper"):
        surface = "upper"
    elif s in ("ps", "pressure_surface", "lower"):
        surface = "lower"
    else:
        return annulus
    camber_xy = getattr(comp, "_camber_xy", None)
    if camber_xy is not None and np.asarray(camber_xy).shape[0] >= 2:
        return ensure_polygon(
            _camber_clip(annulus, camber_xy, surface=surface), allow_empty=True
        )
    return half_plane_clip(annulus, surface=surface)


def emit_shear_web_polygon(
    comp: Any,
    *,
    resolution: int = 16,
    cavity: Polygon | MultiPolygon | None = None,
) -> Polygon | MultiPolygon:
    """Stadium capsule clipped to the interior of the inner skin."""
    # Prefer the extended capsule axis (round ends land outside the cavity so
    # the clipped web is a clean constant-width strip flush against the skin).
    x_top = float(getattr(comp, "x_top_ext", comp.x_top))
    y_top = float(getattr(comp, "y_top_ext", comp.y_top))
    x_bot = float(getattr(comp, "x_bot_ext", comp.x_bot))
    y_bot = float(getattr(comp, "y_bot_ext", comp.y_bot))
    r = 0.5 * float(comp.thickness)
    stadium = stadium_polygon(x_top, y_top, x_bot, y_bot, r, resolution=resolution)

    # Inner-skin clip: Offset(airfoil, -skin).
    if cavity is not None:
        if not cavity.is_empty:
            stadium = stadium.intersection(cavity)
    else:
        af = getattr(comp, "_af", None)
        skin_thickness = getattr(comp, "skin_thickness", None)
        if af is not None and skin_thickness is not None:
            poly = airfoil_polygon(af)
            cav = poly.buffer(
                -float(skin_thickness),
                quad_segs=16,
                join_style=2,
                mitre_limit=5.0,
            )
            if not cav.is_empty:
                stadium = stadium.intersection(cav)
    # Thick skin / shallow sections can empty the cavity ∩ stadium Boolean.
    return ensure_polygon(stadium, allow_empty=True)


def _camber_clip(geom, camber_xy, *, surface: str):
    """Clip to the cap's own side of the sampled cavity midline polyline."""
    cam = np.asarray(camber_xy, dtype=float)
    minx, miny, maxx, maxy = geom.bounds
    pad = max(maxx - minx, maxy - miny, 1.0) + 1.0
    xs = np.concatenate(([minx - pad], cam[:, 0], [maxx + pad]))
    ys = np.concatenate(([cam[0, 1]], cam[:, 1], [cam[-1, 1]]))
    y_far = (maxy + pad) if surface == "upper" else (miny - pad)
    ring = [(x, y) for x, y in zip(xs, ys)] + [(xs[-1], y_far), (xs[0], y_far)]
    return geom.intersection(Polygon(ring))


def emit_spar_cap_polygon(
    comp: Any,
    *,
    airfoil_poly: Polygon | MultiPolygon | None = None,
    inner_cavity: Polygon | MultiPolygon | None = None,
    deeper_cavity: Polygon | MultiPolygon | None = None,
) -> Polygon | MultiPolygon:
    """Slab against inner skin, camber/half-plane + chord/strip clipped, local twist applied."""
    af = _af_from_component(comp)
    skin_t = float(comp.skin_thickness)
    cap_h = float(comp.cap_height)
    surface_raw = str(comp.surface)
    s = surface_raw.strip().lower()
    if s in ("ss", "suction_surface", "upper"):
        surface = "upper"
    elif s in ("ps", "pressure_surface", "lower"):
        surface = "lower"
    else:
        surface = surface_raw
    poly = airfoil_poly if airfoil_poly is not None else airfoil_polygon(af)
    inner = (
        inner_cavity
        if inner_cavity is not None
        else poly.buffer(-skin_t, quad_segs=16, join_style=2, mitre_limit=5.0)
    )
    deeper = (
        deeper_cavity
        if deeper_cavity is not None
        else poly.buffer(
            -(skin_t + cap_h), quad_segs=16, join_style=2, mitre_limit=5.0
        )
    )
    if inner.is_empty:
        raise ValueError("SparCap: inner-skin offset is empty.")
    slab = inner if deeper.is_empty else inner.difference(deeper)
    camber_xy = getattr(comp, "_camber_xy", None)
    if camber_xy is not None and np.asarray(camber_xy).shape[0] >= 2:
        slab = _camber_clip(slab, camber_xy, surface=surface)
    else:
        slab = half_plane_clip(slab, surface=surface)
    if slab.is_empty:
        # The side clip consumed the whole band: this cap has no material on
        # this surface. Both clip branches below build their clip region from
        # ``slab.bounds``, and Shapely raises an opaque LinearRing error on the
        # empty bounds rather than returning an empty geometry.
        return Polygon()
    strip_clip = getattr(comp, "_strip_clip", None)
    if strip_clip is not None:
        # Clip the solid directly with the same parallel-line strip the IR path
        # uses (``_parallel_web_strip_clip``). Previously this approximated the
        # clip by the chordwise extent of the *midline*, which coupled the
        # geometry-property path to the midline construction; the parameters are
        # now carried on the component, so the two are independent.
        if getattr(comp, "flapwise_nx", None) is None:
            raise ValueError(
                "SparCap has a strip_clip but no flapwise_nx/ny/c_lo/c_hi/clip_mode; "
                "the polygon path needs the clip parameters to clip the solid. "
                "Construct it via spar_family (which supplies them) or pass them "
                "explicitly."
            )
        bay = flapwise_bay_clip(
            slab,
            nx=float(comp.flapwise_nx),
            ny=float(comp.flapwise_ny),
            clip_mode=str(comp.flapwise_clip_mode),
            c_lo=comp.flapwise_c_lo,
            c_hi=comp.flapwise_c_hi,
        )
        slab = slab.intersection(bay)
        if slab.is_empty:
            return Polygon()
    else:
        box = chordwise_box(slab, float(comp.x_start), float(comp.x_end))
        slab = slab.intersection(box)

    twist = float(getattr(comp, "twist_angle", 0.0) or 0.0)
    if abs(twist) > 1e-10:
        cx = 0.5 * (float(comp.x_start) + float(comp.x_end))
        slab = rotate_geom(slab, twist, cx=cx, cy=0.0)
    # Cap/cavity clips can collapse on heavily thickened tip stations.
    return ensure_polygon(slab, allow_empty=True)


def emit_inner_cavity_polygon(
    airfoil_sdf,
    skin_thickness: float,
    *,
    airfoil_poly: Polygon | MultiPolygon | None = None,
) -> Polygon | MultiPolygon:
    """Interior of the inner skin: Offset(airfoil, -skin)."""
    poly = airfoil_poly if airfoil_poly is not None else airfoil_polygon(airfoil_sdf)
    cavity = poly.buffer(-float(skin_thickness), quad_segs=16, join_style=2, mitre_limit=5.0)
    # Fully closed sections (skin ≥ local thickness) yield an empty cavity.
    return ensure_polygon(cavity, allow_empty=True)


def emit_sandwich_core_polygon(
    comp: Any,
    laminate_exclusion_union: Polygon | MultiPolygon | None,
    *,
    cavity: Polygon | MultiPolygon | None = None,
) -> Polygon | MultiPolygon:
    """Core bay: (inner cavity − laminates) ∩ bay clip.

    Matches SDF ``SandwichCore``: Offset(airfoil,-skin/2) minus laminate
    exclusions, then chordwise or flapwise bay clip.
    """
    af = _af_from_component(comp)
    skin_t = float(comp.skin_thickness)
    if cavity is None:
        cavity = emit_inner_cavity_polygon(af, skin_t)

    region = cavity
    if laminate_exclusion_union is not None and not laminate_exclusion_union.is_empty:
        region = region.difference(laminate_exclusion_union)

    bay_mode = getattr(comp, "bay_mode", "chordwise")
    if bay_mode == "flapwise":
        clip = flapwise_bay_clip(
            region if not region.is_empty else cavity,
            nx=float(comp.flapwise_nx),
            ny=float(comp.flapwise_ny),
            clip_mode=str(comp.flapwise_clip_mode),
            c_lo=comp.flapwise_c_lo,
            c_hi=comp.flapwise_c_hi,
        )
    else:
        clip = chordwise_bay_clip(
            region if not region.is_empty else cavity,
            x_start=comp.x_start,
            x_end=comp.x_end,
        )
        # Optional y half-planes if present
        if getattr(comp, "y_min", None) is not None or getattr(comp, "y_max", None) is not None:
            minx, miny, maxx, maxy = clip.bounds
            pad = max(maxx - minx, maxy - miny, 1.0) + 1.0
            y0 = float(comp.y_min) if comp.y_min is not None else miny - pad
            y1 = float(comp.y_max) if comp.y_max is not None else maxy + pad
            ybox = Polygon(
                [(minx - pad, y0), (maxx + pad, y0), (maxx + pad, y1), (minx - pad, y1)]
            )
            clip = clip.intersection(ybox)

    if region.is_empty:
        return Polygon()
    clipped = region.intersection(clip)
    if clipped.is_empty or float(getattr(clipped, "area", 0.0) or 0.0) <= 0.0:
        return Polygon()
    return ensure_polygon(clipped, allow_empty=True)


def emit_component_polygon(comp: Any) -> Polygon | MultiPolygon:
    """Dispatch constructive polygon emission by component type / attributes."""
    name = type(comp).__name__
    if name == "OuterSkin" or (
        hasattr(comp, "thickness") and hasattr(comp, "midline_polyline") and hasattr(comp, "_af")
        and not hasattr(comp, "x_top") and not hasattr(comp, "cap_height")
    ):
        if hasattr(comp, "cap_height"):
            return emit_spar_cap_polygon(comp)
        if hasattr(comp, "x_top"):
            return emit_shear_web_polygon(comp)
        return emit_outer_skin_polygon(comp)
    if name == "ShearWeb" or hasattr(comp, "x_top"):
        return emit_shear_web_polygon(comp)
    if name == "SparCap" or hasattr(comp, "cap_height"):
        return emit_spar_cap_polygon(comp)
    if name == "SandwichCore" or hasattr(comp, "bay_mode"):
        raise TypeError(
            "SandwichCore requires emit_sandwich_core_polygon with laminate exclusions."
        )
    raise TypeError(f"No constructive polygon emitter for {name}.")
