"""Resample cap interiors via inward rays from the skin master ring."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from blade_structure_utilities.geometry_utilities.section_contract.shell_midline_strip import ShellMidlineStrip

from .ring_geometry import (
    _MIN_SEGMENT_LENGTH_M,
    normal_2d_ccw,
    open_polyline_prefix_lengths,
)

_SKIN_RAY_CAP_BBOX_MARGIN_M: float = 5e-3
_SKIN_RAY_T_MIN_M: float = 1e-9


def concat_skin_ring_vertices(strips: tuple[ShellMidlineStrip, ...]) -> NDArray[np.float64]:
    """Concatenate all skin ``midline_twisted_pitch_axis_blade_frame`` strips
    in list order; dedupe shared joints."""
    chunks: list[NDArray[np.float64]] = []
    for st in strips:
        if st.kind != "skin":
            continue
        arr = np.asarray(st.midline_twisted_pitch_axis_blade_frame, dtype=float)
        if arr.shape[0] < 2:
            continue
        if chunks and np.allclose(chunks[-1][-1], arr[0], atol=1e-9, rtol=0.0):
            arr = arr[1:]
        if arr.shape[0] == 0:
            continue
        chunks.append(arr)
    if not chunks:
        return np.empty((0, 2), dtype=float)
    return np.vstack(chunks)


def skin_ring_vertex_tangents(ring: NDArray[np.float64]) -> NDArray[np.float64]:
    """Unit tangent at each ring vertex; ring treated closed (last → first edge)."""
    r = np.asarray(ring, dtype=float)
    m = int(r.shape[0])
    if m < 2:
        return np.zeros((0, 2), dtype=float)
    prev_v = np.roll(r, 1, axis=0)
    next_v = np.roll(r, -1, axis=0)
    d = next_v - prev_v
    ln = np.linalg.norm(d, axis=1)
    out = np.zeros((m, 2), dtype=float)
    ok = ln >= 1e-30
    out[ok] = d[ok] / ln[ok, None]
    out[~ok] = np.array([1.0, 0.0], dtype=float)
    return out


def _ray_segment_hit_first(
    p: NDArray[np.float64],
    v: NDArray[np.float64],
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    *,
    t_min: float = _SKIN_RAY_T_MIN_M,
) -> tuple[float, NDArray[np.float64]] | None:
    """First hit of ray ``p + t v`` (``t >= t_min``) on segment ``ab``; ``v`` unit."""
    w = b - a
    mat = np.column_stack([v, -w])
    det = float(np.linalg.det(mat))
    if abs(det) < 1e-18:
        return None
    rhs = a - p
    tu = np.linalg.solve(mat, rhs)
    t = float(tu[0])
    u = float(tu[1])
    if t < t_min or u < -1e-10 or u > 1.0 + 1e-10:
        return None
    uu = float(np.clip(u, 0.0, 1.0))
    hit = a + uu * w
    return t, hit


def _ray_hits_open_polyline(
    p: NDArray[np.float64],
    v: NDArray[np.float64],
    cap_pts: NDArray[np.float64],
) -> list[tuple[float, float, NDArray[np.float64]]]:
    """All ray hits on open ``cap_pts``; each entry ``(t_ray, s_cap, hit)`` with smallest ``t`` first."""
    pts = np.asarray(cap_pts, dtype=float)
    n = int(pts.shape[0])
    if n < 2:
        return []
    p2 = np.asarray(p, dtype=float).reshape(2)
    v2 = np.asarray(v, dtype=float).reshape(2)
    a = pts[:-1]
    b = pts[1:]
    w = b - a
    vx, vy = float(v2[0]), float(v2[1])
    # det([[vx,-wx],[vy,-wy]]) = -vx*wy + wx*vy
    det = -vx * w[:, 1] + w[:, 0] * vy
    rhs = a - p2
    # Avoid divide-by-zero; mark parallel edges invalid.
    ok_det = np.abs(det) >= 1e-18
    det_safe = np.where(ok_det, det, 1.0)
    t = (-rhs[:, 0] * w[:, 1] + w[:, 0] * rhs[:, 1]) / det_safe
    u = (vx * rhs[:, 1] - vy * rhs[:, 0]) / det_safe
    t_min = _SKIN_RAY_T_MIN_M
    ok = ok_det & (t >= t_min) & (u >= -1e-10) & (u <= 1.0 + 1e-10)
    if not np.any(ok):
        return []
    uu = np.clip(u[ok], 0.0, 1.0)
    hit = a[ok] + uu[:, None] * w[ok]
    prefix = open_polyline_prefix_lengths(pts)
    u_len = np.linalg.norm(w[ok], axis=1)
    s_cap = prefix[:-1][ok] + np.where(
        u_len < 1e-30, 0.0, uu * u_len
    )
    order = np.argsort(t[ok])
    hits: list[tuple[float, float, NDArray[np.float64]]] = []
    t_ok = t[ok]
    for idx in order:
        hits.append(
            (float(t_ok[idx]), float(s_cap[idx]), hit[idx].astype(float).copy())
        )
    return hits


def pick_inward_ray_direction(
    p_skin: NDArray[np.float64],
    n_ccw: NDArray[np.float64],
    cap_centroid: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Choose ``+/- n_ccw`` so the ray points generally toward the cap interior."""
    n1 = np.asarray(n_ccw, dtype=float)
    n2 = -n1
    if float(np.dot(n1, cap_centroid - p_skin)) >= float(np.dot(n2, cap_centroid - p_skin)):
        return n1
    return n2


def _resample_one_cap_interior_from_skin_rays(
    cap_strip: ShellMidlineStrip,
    skin_ring: NDArray[np.float64],
    skin_tangents: NDArray[np.float64],
    *,
    bbox_margin_m: float = _SKIN_RAY_CAP_BBOX_MARGIN_M,
) -> ShellMidlineStrip | None:
    """Return replaced cap strip, or ``None`` to keep original."""
    pts = np.asarray(cap_strip.midline_twisted_pitch_axis_blade_frame, dtype=float)
    if pts.shape[0] < 3:
        return None

    p0 = pts[0].copy()
    p1 = pts[-1].copy()
    c_mid = np.asarray(np.mean(pts, axis=0), dtype=float).reshape(2)

    xmin, xmax = float(pts[:, 0].min()), float(pts[:, 0].max())
    ymin, ymax = float(pts[:, 1].min()), float(pts[:, 1].max())
    mrg = float(bbox_margin_m)

    prefix_full = open_polyline_prefix_lengths(pts)
    arc_total = float(prefix_full[-1])
    if arc_total < 1e-9:
        return None
    s_eps = max(1e-6 * arc_total, 1e-7)
    # Target interior spacing follows the incoming cap polyline resolution so
    # skin-ray hits do not over-cluster and create pathological short segments.
    target_step = arc_total / max(float(pts.shape[0] - 1), 1.0)

    collected: list[tuple[float, NDArray[np.float64]]] = []

    m = int(skin_ring.shape[0])
    for i in range(m):
        q = skin_ring[i]
        if (
            q[0] < xmin - mrg
            or q[0] > xmax + mrg
            or q[1] < ymin - mrg
            or q[1] > ymax + mrg
        ):
            continue
        ti = skin_tangents[i]
        n_ccw = normal_2d_ccw(ti)
        v = pick_inward_ray_direction(q, n_ccw, c_mid)
        hits = _ray_hits_open_polyline(q, v, pts)
        for t_ray, s_cap, hit in hits:
            if s_cap <= s_eps or s_cap >= arc_total - s_eps:
                continue
            collected.append((s_cap, hit))
            break

    if len(collected) < 1:
        return None

    collected.sort(key=lambda x: x[0])
    merged: list[tuple[float, NDArray[np.float64]]] = []
    merge_tol = max(0.35 * target_step, 1e-7)
    for s_cap, hit in collected:
        if merged and abs(s_cap - merged[-1][0]) <= merge_tol:
            continue
        merged.append((s_cap, hit))

    seq: list[NDArray[np.float64]] = [p0.copy()]
    min_keep = max(0.5 * target_step, _MIN_SEGMENT_LENGTH_M)
    for _s_cap, hit in merged:
        if float(np.linalg.norm(hit - seq[-1])) >= min_keep:
            seq.append(hit.copy())
    if float(np.linalg.norm(p1 - seq[-1])) >= min_keep:
        seq.append(p1.copy())
    else:
        seq[-1] = p1.copy()

    new_pts = np.stack(seq, axis=0)
    if new_pts.shape[0] < 2:
        return None
    if not np.allclose(new_pts[0], p0, atol=1e-12, rtol=0.0) or not np.allclose(
        new_pts[-1], p1, atol=1e-12, rtol=0.0
    ):
        return None
    return replace(cap_strip, midline_twisted_pitch_axis_blade_frame=new_pts)


def resample_cap_interiors_from_skin_rays(
    strips: tuple[ShellMidlineStrip, ...],
    *,
    bbox_margin_m: float = _SKIN_RAY_CAP_BBOX_MARGIN_M,
) -> tuple[ShellMidlineStrip, ...]:
    """Replace interior vertices of each cap using inward rays from skin master ring.

    Cap **endpoints** are left unchanged (skin–web junction snap is applied earlier
    in :func:`split_skin_at_junctions`). If resampling yields too few hits for a
    cap, that strip is left unchanged.
    """
    skin_ring = concat_skin_ring_vertices(strips)
    if skin_ring.shape[0] < 3:
        return strips

    skin_tangents = skin_ring_vertex_tangents(skin_ring)
    if skin_tangents.shape[0] != skin_ring.shape[0]:
        return strips

    out: list[ShellMidlineStrip] = []
    for st in strips:
        if st.kind != "cap":
            out.append(st)
            continue
        new_st = _resample_one_cap_interior_from_skin_rays(
            st,
            skin_ring,
            skin_tangents,
            bbox_margin_m=bbox_margin_m,
        )
        out.append(new_st if new_st is not None else st)
    return tuple(out)


__all__ = [
    "_SKIN_RAY_CAP_BBOX_MARGIN_M",
    "concat_skin_ring_vertices",
    "skin_ring_vertex_tangents",
    "pick_inward_ray_direction",
    "resample_cap_interiors_from_skin_rays",
]
