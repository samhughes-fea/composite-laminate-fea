"""Closed-ring and open-polyline geometry helpers for shell strip topology."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

_MIN_SEGMENT_LENGTH_M: float = 1e-12


def closed_ring_edge_data(
    verts: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
    """Per-edge length, arc offset at each vertex start, and perimeter ``L``."""
    v = np.asarray(verts, dtype=float)
    nxt = np.roll(v, -1, axis=0)
    edge_len = np.linalg.norm(nxt - v, axis=1)
    L = float(np.sum(edge_len))
    edge_start = np.zeros(int(v.shape[0]), dtype=float)
    if v.shape[0] > 1:
        edge_start[1:] = np.cumsum(edge_len[:-1])
    return edge_len, edge_start, L


def merge_sorted_s_values(values: list[float], tol_m: float) -> list[float]:
    if not values:
        return []
    vals = sorted(float(v) for v in values)
    out = [vals[0]]
    for v in vals[1:]:
        if abs(v - out[-1]) > tol_m:
            out.append(v)
    return out


def nearest_on_closed_polyline(
    pt: NDArray[np.float64],
    verts: NDArray[np.float64],
    edge_len: NDArray[np.float64],
    edge_start: NDArray[np.float64],
    L: float,
) -> tuple[float, NDArray[np.float64]]:
    """Closest point on a closed polygonal ring; returns ``(s, yz)`` with ``s`` in ``[0, L)``."""
    s_arr, yz_arr = nearest_on_closed_polyline_many(
        np.asarray(pt, dtype=float).reshape(1, 2),
        verts,
        edge_len,
        edge_start,
        L,
    )
    return float(s_arr[0]), yz_arr[0].astype(float).copy()


def nearest_on_closed_polyline_many(
    pts: NDArray[np.float64],
    verts: NDArray[np.float64],
    edge_len: NDArray[np.float64],
    edge_start: NDArray[np.float64],
    L: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Batch closest points on a closed ring; returns ``(s[M], yz[M,2])``."""
    p = np.asarray(pts, dtype=float).reshape(-1, 2)
    v = np.asarray(verts, dtype=float)
    if p.shape[0] == 0:
        return np.zeros(0, dtype=float), np.zeros((0, 2), dtype=float)
    if v.shape[0] < 1:
        raise ValueError("closed polyline requires at least one vertex")
    a = v[None, :, :]
    b = np.roll(v, -1, axis=0)[None, :, :]
    e = b - a
    elen2 = np.sum(e * e, axis=2) + 1e-30
    t = np.clip(np.sum((p[:, None, :] - a) * e, axis=2) / elen2, 0.0, 1.0)
    q = a + t[:, :, None] * e
    d2 = np.sum((p[:, None, :] - q) ** 2, axis=2)
    i_best = np.argmin(d2, axis=1)
    m = np.arange(p.shape[0])
    yz = q[m, i_best]
    s = np.asarray(edge_start, dtype=float)[i_best] + t[m, i_best] * np.asarray(
        edge_len, dtype=float
    )[i_best]
    if L > 1e-15:
        s = np.mod(s, L)
    return s.astype(float), yz.astype(float)


def yz_at_s_on_closed_ring(
    s: float,
    verts: NDArray[np.float64],
    edge_len: NDArray[np.float64],
    edge_start: NDArray[np.float64],
    L: float,
) -> NDArray[np.float64]:
    if L <= 1e-15:
        return verts[0].astype(float).copy()
    s_mod = float(s % L)
    n = int(verts.shape[0])
    for i in range(n):
        lo = float(edge_start[i])
        hi = lo + float(edge_len[i])
        if lo <= s_mod <= hi + 1e-12 or (i == n - 1 and s_mod >= lo - 1e-12):
            el = float(edge_len[i])
            t = 0.0 if el < 1e-30 else float(np.clip((s_mod - lo) / el, 0.0, 1.0))
            j = (i + 1) % n
            return verts[i] + t * (verts[j] - verts[i])
    return verts[0].astype(float).copy()


def arc_polyline_no_wrap(
    s_lo: float,
    s_hi: float,
    verts: NDArray[np.float64],
    edge_len: NDArray[np.float64],
    edge_start: NDArray[np.float64],
    L: float,
) -> NDArray[np.float64]:
    """Polyline samples from ``s_lo`` to ``s_hi`` along the ring (``s_lo < s_hi``)."""
    n = int(verts.shape[0])
    out_pts: list[NDArray[np.float64]] = []
    out_pts.append(yz_at_s_on_closed_ring(s_lo, verts, edge_len, edge_start, L))
    for j in range(1, n):
        sj = float(edge_start[j])
        if s_lo + 1e-9 < sj < s_hi - 1e-9:
            out_pts.append(np.asarray(verts[j], dtype=float).copy())
    out_pts.append(yz_at_s_on_closed_ring(s_hi, verts, edge_len, edge_start, L))
    return np.stack(out_pts, axis=0)


def arc_polyline_wrap(
    s_lo: float,
    s_hi: float,
    verts: NDArray[np.float64],
    edge_len: NDArray[np.float64],
    edge_start: NDArray[np.float64],
    L: float,
) -> NDArray[np.float64]:
    """Arc from ``s_lo`` forward through ``L`` and ``0`` to ``s_hi`` (``s_lo > s_hi`` on the circle)."""
    a = arc_polyline_no_wrap(s_lo, L, verts, edge_len, edge_start, L)
    b = arc_polyline_no_wrap(0.0, s_hi, verts, edge_len, edge_start, L)
    if len(a) and len(b) and np.allclose(a[-1], b[0], atol=1e-9, rtol=0.0):
        return np.vstack([a[:-1], b])
    return np.vstack([a, b])


def open_polyline_prefix_lengths(pts: NDArray[np.float64]) -> NDArray[np.float64]:
    """Cumulative distance along open polyline ``pts``; ``prefix[i]`` = arc to vertex ``i``."""
    n = int(pts.shape[0])
    if n < 2:
        return np.zeros(max(n, 0), dtype=float)
    ds = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    prefix = np.zeros(n, dtype=float)
    prefix[1:] = np.cumsum(ds)
    return prefix


def intersect_open_segments_2d(
    a0: NDArray[np.float64],
    a1: NDArray[np.float64],
    b0: NDArray[np.float64],
    b1: NDArray[np.float64],
    *,
    eps: float = 1e-9,
) -> tuple[float, float, NDArray[np.float64]] | None:
    """Strict-interior intersection of segment ``a0a1`` with ``b0b1``; ``ta,tb`` in ``(0,1)``."""
    r = (a1.astype(float) - a0).reshape(2)
    svec = (b1.astype(float) - b0).reshape(2)
    rxs = float(r[0] * svec[1] - r[1] * svec[0])
    denom_tol = 1e-15 * max(
        1.0,
        float(np.linalg.norm(r)) * float(np.linalg.norm(svec)),
    )
    if abs(rxs) < denom_tol:
        return None
    qp = (b0.astype(float) - a0.astype(float)).reshape(2)
    ta = float((qp[0] * svec[1] - qp[1] * svec[0]) / rxs)
    tb = float((qp[0] * r[1] - qp[1] * r[0]) / rxs)
    if ta <= eps or ta >= 1.0 - eps or tb <= eps or tb >= 1.0 - eps:
        return None
    pt = (a0.astype(float) + ta * r).astype(float)
    return ta, tb, pt


def intersect_open_polylines_2d(
    a_pts: NDArray[np.float64],
    b_pts: NDArray[np.float64],
    *,
    eps: float = 1e-9,
) -> list[tuple[int, float, float, NDArray[np.float64]]]:
    """All strict-interior edge×edge intersections of two open polylines.

    Returns ``(i_edge_a, ta, tb, point)`` with ``ta,tb`` in ``(eps, 1-eps)``,
    matching :func:`intersect_open_segments_2d` semantics.
    """
    a = np.asarray(a_pts, dtype=float)
    b = np.asarray(b_pts, dtype=float)
    if a.ndim != 2 or a.shape[0] < 2 or b.ndim != 2 or b.shape[0] < 2:
        return []
    a0 = a[:-1]
    a1 = a[1:]
    b0 = b[:-1]
    b1 = b[1:]
    r = a1 - a0  # (Na, 2)
    svec = b1 - b0  # (Nb, 2)
    r_norm = np.linalg.norm(r, axis=1)
    s_norm = np.linalg.norm(svec, axis=1)
    rxs = r[:, None, 0] * svec[None, :, 1] - r[:, None, 1] * svec[None, :, 0]
    denom_tol = 1e-15 * np.maximum(1.0, r_norm[:, None] * s_norm[None, :])
    parallel = np.abs(rxs) < denom_tol
    qp = b0[None, :, :] - a0[:, None, :]
    # Avoid divide-by-zero; parallel rows are discarded below.
    rxs_safe = np.where(parallel, 1.0, rxs)
    ta = (qp[..., 0] * svec[None, :, 1] - qp[..., 1] * svec[None, :, 0]) / rxs_safe
    tb = (qp[..., 0] * r[:, None, 1] - qp[..., 1] * r[:, None, 0]) / rxs_safe
    ok = (
        (~parallel)
        & (ta > eps)
        & (ta < 1.0 - eps)
        & (tb > eps)
        & (tb < 1.0 - eps)
    )
    ii, jj = np.nonzero(ok)
    out: list[tuple[int, float, float, NDArray[np.float64]]] = []
    for i, j in zip(ii.tolist(), jj.tolist()):
        ta_i = float(ta[i, j])
        tb_j = float(tb[i, j])
        pt = (a0[i] + ta_i * r[i]).astype(float)
        out.append((int(i), ta_i, tb_j, pt.reshape(2)))
    return out


def open_polyline_min_segment_length(pts: NDArray[np.float64]) -> float:
    if pts.shape[0] < 2:
        return float("inf")
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).min())


def point_to_open_polyline_nearest(
    p: NDArray[np.float64], w: NDArray[np.float64]
) -> tuple[float, NDArray[np.float64]]:
    """Nearest distance and point from 2-D point ``p`` to open polyline ``w``."""
    q = np.asarray(p, dtype=float).reshape(2)
    pts = np.asarray(w, dtype=float)
    if pts.shape[0] < 2:
        return float("inf"), q.copy()
    a = pts[:-1]
    b = pts[1:]
    ab = b - a
    l2 = np.sum(ab * ab, axis=1) + 1e-30
    t = np.clip(np.sum((q - a) * ab, axis=1) / l2, 0.0, 1.0)
    c = a + t[:, None] * ab
    d = np.linalg.norm(q - c, axis=1)
    j = int(np.argmin(d))
    return float(d[j]), np.asarray(c[j], dtype=float).reshape(2)


def normal_2d_ccw(t: NDArray[np.float64]) -> NDArray[np.float64]:
    """Unit normal: 90° CCW rotation of a 2-D tangent (same convention as MITC4 assembly)."""
    tx, ty = float(t[0]), float(t[1])
    n = np.array([-ty, tx], dtype=float)
    ln = float(np.linalg.norm(n))
    if ln < 1e-30:
        return np.array([0.0, 1.0], dtype=float)
    return n / ln


__all__ = [
    "_MIN_SEGMENT_LENGTH_M",
    "closed_ring_edge_data",
    "merge_sorted_s_values",
    "nearest_on_closed_polyline",
    "nearest_on_closed_polyline_many",
    "yz_at_s_on_closed_ring",
    "arc_polyline_no_wrap",
    "arc_polyline_wrap",
    "open_polyline_prefix_lengths",
    "intersect_open_segments_2d",
    "intersect_open_polylines_2d",
    "open_polyline_min_segment_length",
    "point_to_open_polyline_nearest",
    "normal_2d_ccw",
]
