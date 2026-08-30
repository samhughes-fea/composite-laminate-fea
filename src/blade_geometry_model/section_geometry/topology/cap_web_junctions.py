"""Insert cap midline vertices at web T-junctions."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from blade_structure_utilities.geometry_utilities.section_contract.shell_midline_strip import ShellMidlineStrip

from ..midlines.ring_geometry import (
    _MIN_SEGMENT_LENGTH_M,
    intersect_open_polylines_2d,
    open_polyline_min_segment_length,
    open_polyline_prefix_lengths,
)

_CAP_WEB_JUNCTION_MERGE_ARC_M: float = 1e-6


def insert_cap_web_interior_junctions(
    strips: tuple[ShellMidlineStrip, ...],
    *,
    vertex_coincide_tol_m: float = 1e-6,
    merge_arc_m: float | None = None,
    min_seg_m: float | None = None,
    foot_proximity_tol_m: float = 0.0,
) -> tuple[ShellMidlineStrip, ...]:
    """Insert cap midline vertices for web-related T-junctions.

    (1) Strict interior **segment intersections** of the cap with each web polyline.
    (2) Optional **proximity** to each shear-web **foot** (endpoint on skin): when
    enabled (``foot_proximity_tol_m > 0``) and the foot is within tolerance of the
    cap polyline, insert the foot ``yz`` as a new vertex.

    Layout-wise, **Y = C** systems hit every web this way by construction; **Y = B**
    systems often need it only once **X** is large enough that the cap band
    crosses webs between bay ends.

    Intended after :func:`split_skin_at_junctions` and (when enabled) after
    :func:`resample_cap_interiors_from_skin_rays`, so cap endpoints are final.
    """
    web_pts: list[NDArray[np.float64]] = []
    web_feet: list[NDArray[np.float64]] = []
    for st in strips:
        if st.kind != "web":
            continue
        w = np.asarray(st.midline_twisted_pitch_axis_blade_frame, dtype=float)
        if w.shape[0] >= 2:
            web_pts.append(w)
            web_feet.append(np.asarray(w[0], dtype=float).reshape(2))
            web_feet.append(np.asarray(w[-1], dtype=float).reshape(2))

    if not web_pts:
        return strips

    min_seg = float(min_seg_m) if min_seg_m is not None else max(_MIN_SEGMENT_LENGTH_M * 100.0, 1e-9)
    foot_tol = float(foot_proximity_tol_m)
    use_foot_proximity = foot_tol > 0.0

    out: list[ShellMidlineStrip] = []
    for st in strips:
        if st.kind != "cap":
            out.append(st)
            continue
        pts = np.asarray(st.midline_twisted_pitch_axis_blade_frame, dtype=float)
        if pts.shape[0] < 2:
            out.append(st)
            continue
        prefix = open_polyline_prefix_lengths(pts)
        arc_total = float(prefix[-1])
        if arc_total < min_seg * 3.0:
            out.append(st)
            continue
        merge_arc = (
            float(merge_arc_m)
            if merge_arc_m is not None
            else max(1e-7 * arc_total, _CAP_WEB_JUNCTION_MERGE_ARC_M)
        )
        eps_s = max(1e-12 * arc_total, 1e-15)

        hits: list[tuple[float, NDArray[np.float64]]] = []
        n = int(pts.shape[0])
        seg_lens = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        for w in web_pts:
            for i, ta, _tb, p_hit in intersect_open_polylines_2d(pts, w):
                seg_len = float(seg_lens[i])
                if seg_len < min_seg:
                    continue
                s_hit = float(prefix[i] + ta * seg_len)
                if s_hit <= merge_arc or s_hit >= arc_total - merge_arc:
                    continue
                hits.append((s_hit, np.asarray(p_hit, dtype=float).reshape(2)))

        if use_foot_proximity and web_feet:
            a0 = pts[:-1]
            a1 = pts[1:]
            ab = a1 - a0
            l2 = np.sum(ab * ab, axis=1) + 1e-30
            feet = np.asarray(web_feet, dtype=float).reshape(-1, 2)
            for q in feet:
                t_raw = np.sum((q[None, :] - a0) * ab, axis=1) / l2
                for i in range(n - 1):
                    seg_len = float(seg_lens[i])
                    if seg_len < min_seg:
                        continue
                    eps_line = max(1e-12, min(1e-7, 1e-6 * seg_len / max(seg_len, 1e-15)))
                    ti = float(t_raw[i])
                    if ti <= 0.0:
                        if float(np.linalg.norm(q - a0[i])) > foot_tol:
                            continue
                        t_ins = eps_line
                    elif ti >= 1.0:
                        if float(np.linalg.norm(q - a1[i])) > foot_tol:
                            continue
                        t_ins = 1.0 - eps_line
                    else:
                        c = a0[i] + ab[i] * ti
                        if float(np.linalg.norm(q - c)) > foot_tol:
                            continue
                        t_ins = ti
                    s_hit = float(prefix[i] + t_ins * seg_len)
                    if s_hit <= merge_arc or s_hit >= arc_total - merge_arc:
                        continue
                    if float(np.linalg.norm(pts - q, axis=1).min()) <= vertex_coincide_tol_m:
                        continue
                    hits.append((s_hit, q.copy()))

        # A cap-endpoint-on-web branch used to live here, inserting the nearest
        # web-midline point for any cap end within ``_CAP_ENDPOINT_ON_WEB_TOL_M``
        # of a web. It became unreachable once ``shell_midline_export`` started
        # emitting the web vertex at each cap-end junction: a family-D cap end is
        # then already coincident with a web node, so the ``vertex_coincide_tol_m``
        # guard skipped it, and a family-B/C free end is 38.6-148.6 mm from the
        # nearest web, so the tolerance guard skipped it. Removed after
        # confirming byte-identical output across 108 layout x twist x chord
        # configurations with the branch disabled. See ``docs/bug_log.md`` SG-004.

        if not hits:
            out.append(st)
            continue

        hits.sort(key=lambda h: h[0])
        merged: list[tuple[float, NDArray[np.float64]]] = []
        for s_h, p_h in hits:
            if merged and abs(s_h - merged[-1][0]) <= merge_arc:
                continue
            if float(np.linalg.norm(pts - p_h, axis=1).min()) <= vertex_coincide_tol_m:
                continue
            merged.append((s_h, p_h))

        if not merged:
            out.append(st)
            continue

        new_rows: list[NDArray[np.float64]] = []
        mi = 0
        for i in range(n - 1):
            new_rows.append(pts[i].copy())
            s_lo = float(prefix[i])
            s_hi = float(prefix[i + 1])
            while mi < len(merged) and merged[mi][0] < s_hi - eps_s:
                s_h, p_h = merged[mi]
                if s_h > s_lo + eps_s and float(np.linalg.norm(p_h - new_rows[-1])) >= min_seg:
                    new_rows.append(p_h.copy())
                mi += 1
        new_rows.append(pts[-1].copy())

        slim: list[NDArray[np.float64]] = [new_rows[0]]
        for r in new_rows[1:]:
            if float(np.linalg.norm(r - slim[-1])) < min_seg:
                slim[-1] = r.copy()
            else:
                slim.append(r.copy())

        new_pts = np.stack(slim, axis=0)
        if new_pts.shape[0] < 2 or open_polyline_min_segment_length(new_pts) < _MIN_SEGMENT_LENGTH_M:
            out.append(st)
            continue
        out.append(replace(st, midline_twisted_pitch_axis_blade_frame=new_pts))

    return tuple(out)


__all__ = [
    "_CAP_WEB_JUNCTION_MERGE_ARC_M",
    "insert_cap_web_interior_junctions",
]
