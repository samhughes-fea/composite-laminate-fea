"""Geometry helpers for constructive void-cell wall mid-surface loops."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from numpy.typing import NDArray

from blade_structure_utilities.geometry_utilities.section_contract.shell_midline_strip import ShellMidlineStrip

_TOL = 1e-12
_RAY_T_MIN = -1e-9


def shoelace_area(pts: NDArray[np.float64]) -> float:
    x = pts[:, 0]
    y = pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def drop_closing_vertex(pts: NDArray[np.float64], *, tol: float = 1e-12) -> NDArray[np.float64]:
    pts = np.asarray(pts, dtype=float)
    if pts.shape[0] > 2 and np.hypot(*(pts[0] - pts[-1])) < tol:
        return pts[:-1].copy()
    return pts.copy()


_SUCTION = "suction_surface"
_PRESSURE = "pressure_surface"
_LEADING = "leading_edge"
_TRAILING = "trailing_edge"
_BAY = "bay"

_SIDE_ALIASES = {
    "ss": _SUCTION,
    "upper": _SUCTION,
    _SUCTION: _SUCTION,
    "ps": _PRESSURE,
    "lower": _PRESSURE,
    _PRESSURE: _PRESSURE,
}
_ARC_ALIASES = {
    "le": _LEADING,
    _LEADING: _LEADING,
    "te": _TRAILING,
    _TRAILING: _TRAILING,
    "bay": _BAY,
}


def _normalise_skin_side(side: object | None) -> str | None:
    if side is None:
        return None
    key = str(side).strip().lower()
    return _SIDE_ALIASES.get(key)


def _normalise_skin_arc(arc: object | None) -> str | None:
    if arc is None:
        return None
    key = str(arc).strip().lower()
    return _ARC_ALIASES.get(key)


def _skin_ring_order_key(s: ShellMidlineStrip) -> tuple[int, int]:
    """Order hierarchical arcs: suction TE→LE, then pressure LE→TE."""
    side = _normalise_skin_side(s.skin_side)
    arc = _normalise_skin_arc(s.skin_arc)
    bay = int(s.bay_index) if s.bay_index is not None else 0
    side_rank = 0 if side == _SUCTION else 1 if side == _PRESSURE else 2
    if side == _SUCTION:
        # Half-ring runs trailing_edge → bay_i → leading_edge.
        if arc == _TRAILING:
            arc_rank = 0
        elif arc == _BAY:
            arc_rank = 1 + bay
        elif arc == _LEADING:
            arc_rank = 10_000
        else:
            arc_rank = 5_000
    else:
        # Half-ring runs leading_edge → bay_i → trailing_edge.
        if arc == _LEADING:
            arc_rank = 0
        elif arc == _BAY:
            arc_rank = 1 + bay
        elif arc == _TRAILING:
            arc_rank = 10_000
        else:
            arc_rank = 5_000
    return (side_rank, arc_rank)


def _append_oriented(
    poly: NDArray[np.float64],
    nxt: NDArray[np.float64],
    *,
    tol: float,
) -> NDArray[np.float64]:
    end = poly[-1]
    d0 = float(np.hypot(*(nxt[0] - end)))
    d1 = float(np.hypot(*(nxt[-1] - end)))
    if d1 < d0:
        nxt = nxt[::-1].copy()
        d0 = d1
    if d0 > max(tol, 1e-4):
        raise ValueError(f"Could not stitch skin strips into a closed ring (gap={d0:.3e} m)")
    nxt = drop_closing_vertex(nxt, tol=max(tol, 1e-9))
    if np.hypot(*(nxt[0] - poly[-1])) < max(tol, 1e-9):
        return np.vstack([poly, nxt[1:]])
    return np.vstack([poly, nxt])


def stitch_skin_ring(skin_strips: Sequence[ShellMidlineStrip], *, tol: float = 1e-9) -> NDArray[np.float64]:
    """Chain one or more skin strips into a single closed (open-vertex) ring.

    When strips carry hierarchical ``skin_side`` / ``skin_arc`` fields, prefer
    ring order suction (trailing→leading) then pressure (leading→trailing).
    Otherwise fall back to greedy tip chaining (legacy closed ring or
    unlabelled open segments). Short side/arc aliases are normalised at the
    edge of this helper.
    """
    if not skin_strips:
        raise ValueError("Expected at least one skin strip for cell wall loops")
    if len(skin_strips) == 1:
        return drop_closing_vertex(
            np.asarray(
                skin_strips[0].midline_twisted_pitch_axis_blade_frame, dtype=float
            ),
            tol=tol,
        )

    usable = [
        (i, s, np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float))
        for i, s in enumerate(skin_strips)
        if np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float).shape[0]
        >= 2
    ]
    if not usable:
        raise ValueError("Skin strips have no usable polylines")

    sides = [_normalise_skin_side(s.skin_side) for _i, s, _p in usable]
    hierarchical = all(side in (_SUCTION, _PRESSURE) for side in sides)
    if hierarchical and any(_normalise_skin_arc(s.skin_arc) for _i, s, _p in usable):
        ordered = sorted(usable, key=lambda item: _skin_ring_order_key(item[1]))
        try:
            poly = drop_closing_vertex(ordered[0][2].copy(), tol=tol)
            for _i, _s, pts in ordered[1:]:
                poly = _append_oriented(poly, pts.copy(), tol=tol)
            return drop_closing_vertex(poly, tol=max(tol, 1e-6))
        except ValueError:
            pass  # fall through to greedy tip chaining

    remaining = {i: p for i, _s, p in usable}

    def _tip_key(i: int) -> float:
        p = remaining[i]
        return float(max(p[0, 0], p[-1, 0]))

    start_i = max(remaining.keys(), key=_tip_key)
    poly = remaining.pop(start_i).copy()
    poly = drop_closing_vertex(poly, tol=tol)

    while remaining:
        end = poly[-1]
        best_i = None
        best_rev = False
        best_d = 1e300
        for i, p in remaining.items():
            d0 = float(np.hypot(*(p[0] - end)))
            d1 = float(np.hypot(*(p[-1] - end)))
            if d0 < best_d:
                best_d, best_i, best_rev = d0, i, False
            if d1 < best_d:
                best_d, best_i, best_rev = d1, i, True
        if best_i is None or best_d > max(tol, 1e-4):
            raise ValueError(
                f"Could not stitch skin strips into a closed ring (gap={best_d:.3e} m)"
            )
        nxt = remaining.pop(best_i)
        if best_rev:
            nxt = nxt[::-1].copy()
        nxt = drop_closing_vertex(nxt, tol=tol)
        if np.hypot(*(nxt[0] - poly[-1])) < max(tol, 1e-9):
            poly = np.vstack([poly, nxt[1:]])
        else:
            poly = np.vstack([poly, nxt])

    return drop_closing_vertex(poly, tol=max(tol, 1e-6))


def edge_geometry(
    ring: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
    n = int(ring.shape[0])
    el = np.zeros(n, dtype=float)
    for i in range(n):
        j = (i + 1) % n
        el[i] = float(np.hypot(*(ring[j] - ring[i])))
    starts = np.zeros(n, dtype=float)
    for i in range(1, n):
        starts[i] = starts[i - 1] + el[i - 1]
    return starts, el, float(np.sum(el))


def ray_segment_hit(
    origin: NDArray[np.float64],
    direction: NDArray[np.float64],
    a: NDArray[np.float64],
    b: NDArray[np.float64],
) -> tuple[float, float] | None:
    """Return (t, u) for origin + t d = a + u (b-a), else None."""
    d = np.asarray(direction, dtype=float)
    e = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    o = np.asarray(origin, dtype=float)
    # origin + t d = a + u e  →  [d | -e] [t;u] = a - origin
    mat_det = float(d[0] * (-e[1]) - (-e[0]) * d[1])
    if abs(mat_det) < _TOL:
        return None
    rhs = np.asarray(a, dtype=float) - o
    t = (rhs[0] * (-e[1]) - (-e[0]) * rhs[1]) / mat_det
    u = (d[0] * rhs[1] - d[1] * rhs[0]) / mat_det
    if t < _RAY_T_MIN or u < -1e-9 or u > 1.0 + 1e-9:
        return None
    return float(t), float(np.clip(u, 0.0, 1.0))


def first_ray_hit_on_ring(
    origin: NDArray[np.float64],
    direction: NDArray[np.float64],
    ring: NDArray[np.float64],
    edge_starts: NDArray[np.float64],
    edge_lens: NDArray[np.float64],
) -> tuple[NDArray[np.float64], float]:
    dn = float(np.hypot(direction[0], direction[1]))
    if dn < _TOL:
        raise ValueError("Web end tangent is degenerate; cannot extrapolate to skin")
    d = np.asarray(direction, dtype=float) / dn
    o = np.asarray(origin, dtype=float)
    n = int(ring.shape[0])
    best: tuple[float, NDArray[np.float64], float] | None = None
    for i in range(n):
        j = (i + 1) % n
        hit = ray_segment_hit(o, d, ring[i], ring[j])
        if hit is None:
            continue
        t, u = hit
        pt = ring[i] + u * (ring[j] - ring[i])
        s = float(edge_starts[i] + u * edge_lens[i])
        if best is None or t < best[0]:
            best = (t, pt, s)
    if best is None:
        raise ValueError(
            f"Web extrapolation from {o.tolist()} dir {d.tolist()} "
            "does not intersect the skin centreline"
        )
    return best[1], best[2]


def locate_s(
    edge_starts: NDArray[np.float64],
    edge_lens: NDArray[np.float64],
    s: float,
    perimeter: float,
) -> tuple[int, float]:
    """Return (edge_index, u) for arc parameter ``s``."""
    if perimeter <= _TOL:
        return 0, 0.0
    s = float(s) % perimeter
    n = int(edge_starts.shape[0])
    for i in range(n):
        end_s = edge_starts[i] + edge_lens[i]
        if s <= end_s + 1e-14 or i == n - 1:
            u = 0.0 if edge_lens[i] < _TOL else (s - edge_starts[i]) / edge_lens[i]
            return i, float(np.clip(u, 0.0, 1.0))
    return 0, 0.0


def point_at_s(
    ring: NDArray[np.float64],
    edge_starts: NDArray[np.float64],
    edge_lens: NDArray[np.float64],
    s: float,
    perimeter: float,
) -> NDArray[np.float64]:
    i, u = locate_s(edge_starts, edge_lens, s, perimeter)
    j = (i + 1) % int(ring.shape[0])
    return (ring[i] + u * (ring[j] - ring[i])).copy()


def skin_arc(
    ring: NDArray[np.float64],
    edge_starts: NDArray[np.float64],
    edge_lens: NDArray[np.float64],
    perimeter: float,
    s_from: float,
    s_to: float,
    *,
    forward: bool,
) -> NDArray[np.float64]:
    """Walk the skin ring edge-by-edge from ``s_from`` to ``s_to``."""
    if perimeter <= _TOL:
        return np.asarray([ring[0], ring[0]], dtype=float)
    sf = float(s_from) % perimeter
    st = float(s_to) % perimeter
    n = int(ring.shape[0])
    p0 = point_at_s(ring, edge_starts, edge_lens, sf, perimeter)
    p1 = point_at_s(ring, edge_starts, edge_lens, st, perimeter)
    span = ((st - sf) % perimeter) if forward else ((sf - st) % perimeter)
    if span < _TOL:
        return np.asarray([p0, p1], dtype=float)

    pts: list[NDArray[np.float64]] = [p0]
    i0, u0 = locate_s(edge_starts, edge_lens, sf, perimeter)
    i1, u1 = locate_s(edge_starts, edge_lens, st, perimeter)

    if forward:
        # From current point toward end of edge i0, then full edges, then into i1
        if i0 == i1 and ((st - sf) % perimeter) <= edge_lens[i0] + 1e-14 and u1 >= u0 - 1e-14:
            pts.append(p1)
            return np.asarray(pts, dtype=float)
        # Remainder of starting edge
        if u0 < 1.0 - 1e-14:
            pts.append(ring[(i0 + 1) % n].copy())
        i = (i0 + 1) % n
        guard = 0
        while i != i1 and guard < n + 2:
            pts.append(ring[(i + 1) % n].copy())
            i = (i + 1) % n
            guard += 1
        pts.append(p1)
    else:
        # Walk decreasing edge index
        if i0 == i1 and ((sf - st) % perimeter) <= edge_lens[i0] + 1e-14 and u0 >= u1 - 1e-14:
            pts.append(p1)
            return np.asarray(pts, dtype=float)
        if u0 > 1e-14:
            pts.append(ring[i0].copy())
        i = i0
        guard = 0
        while True:
            i = (i - 1) % n
            if i == i1:
                break
            pts.append(ring[i].copy())
            guard += 1
            if guard > n + 2:
                break
        pts.append(p1)

    return np.asarray(pts, dtype=float)


def mean_x(pts: NDArray[np.float64]) -> float:
    if pts.size == 0:
        return 0.0
    return float(np.mean(np.asarray(pts, dtype=float)[:, 0]))


def close_loop(parts: list[NDArray[np.float64]]) -> NDArray[np.float64]:
    chunks: list[NDArray[np.float64]] = []
    for part in parts:
        p = np.asarray(part, dtype=float)
        if p.shape[0] == 0:
            continue
        if not chunks:
            chunks.append(p)
            continue
        if np.hypot(*(p[0] - chunks[-1][-1])) < 1e-9:
            if p.shape[0] > 1:
                chunks.append(p[1:])
        else:
            chunks.append(p)
    poly = np.vstack([c for c in chunks if c.shape[0] > 0])
    if poly.shape[0] < 2:
        raise ValueError("Degenerate cell wall loop")
    if np.hypot(*(poly[0] - poly[-1])) > 1e-9:
        poly = np.vstack([poly, poly[0]])
    return poly


__all__ = [
    "_TOL",
    "_RAY_T_MIN",
    "shoelace_area",
    "drop_closing_vertex",
    "stitch_skin_ring",
    "edge_geometry",
    "ray_segment_hit",
    "first_ray_hit_on_ring",
    "locate_s",
    "point_at_s",
    "skin_arc",
    "mean_x",
    "close_loop",
]
