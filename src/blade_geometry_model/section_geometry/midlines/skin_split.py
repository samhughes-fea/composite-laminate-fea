"""Split outer skin midlines into hierarchical suction/pressure × LE/bay/TE arcs."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from blade_structure_utilities.geometry_utilities.section_contract.shell_midline_strip import (
    ShellMidlineStrip,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sections.components.outer_skin import (
    split_closed_ring_ss_ps,
)

from .ring_geometry import (
    merge_sorted_s_values,
    open_polyline_prefix_lengths,
    point_to_open_polyline_nearest,
)

_MERGE_S_TOL_M: float = 1e-4
_CAP_ENDPOINT_ON_WEB_TOL_M: float = 5e-4

_SUCTION = "suction_surface"
_PRESSURE = "pressure_surface"
_LEADING = "leading_edge"
_TRAILING = "trailing_edge"


def _label_key(label: object) -> str:
    return str(getattr(label, "value", label))


def _normalise_side(side: str | None, *, label: str = "", pts: NDArray | None = None) -> str | None:
    if side is not None:
        s = str(side).strip().lower()
        if s in (_SUCTION, "ss", "upper"):
            return _SUCTION
        if s in (_PRESSURE, "ps", "lower"):
            return _PRESSURE
    lab = label.lower()
    if "suction" in lab or lab.endswith("_ss") or ":ss" in lab:
        return _SUCTION
    if "pressure" in lab or lab.endswith("_ps") or ":ps" in lab:
        return _PRESSURE
    if pts is not None and pts.size:
        return _SUCTION if float(np.mean(pts[:, 1])) >= 0.0 else _PRESSURE
    return None


def _open_arc_between(
    pts: NDArray[np.float64],
    prefix: NDArray[np.float64],
    s_lo: float,
    s_hi: float,
) -> NDArray[np.float64]:
    """Extract open polyline samples for ``s_lo <= s <= s_hi`` along ``pts``."""
    if s_hi <= s_lo + 1e-15:
        return np.zeros((0, 2), dtype=float)
    n = int(pts.shape[0])
    out: list[NDArray[np.float64]] = []

    def _at(s: float) -> NDArray[np.float64]:
        if s <= float(prefix[0]) + 1e-15:
            return pts[0].copy()
        if s >= float(prefix[-1]) - 1e-15:
            return pts[-1].copy()
        j = int(np.searchsorted(prefix, s, side="right") - 1)
        j = int(np.clip(j, 0, n - 2))
        seg = float(prefix[j + 1] - prefix[j])
        t = 0.0 if seg < 1e-30 else (s - float(prefix[j])) / seg
        return (1.0 - t) * pts[j] + t * pts[j + 1]

    out.append(_at(s_lo))
    for j in range(1, n - 1):
        sj = float(prefix[j])
        if s_lo + 1e-9 < sj < s_hi - 1e-9:
            out.append(pts[j].copy())
    out.append(_at(s_hi))
    return np.stack(out, axis=0)


def _ensure_ss_ps_skins(
    skins: list[ShellMidlineStrip],
) -> list[ShellMidlineStrip]:
    """Normalise to two open suction/pressure half-rings."""
    if not skins:
        return []
    if len(skins) == 1 and skins[0].closed:
        ring = np.asarray(skins[0].midline_twisted_pitch_axis_blade_frame, dtype=float)
        ss, ps = split_closed_ring_ss_ps(ring)
        t = float(skins[0].thickness_m)
        return [
            ShellMidlineStrip(
                label="skin_suction_surface",
                kind="skin",
                midline_twisted_pitch_axis_blade_frame=ss,
                thickness_m=t,
                closed=False,
                skin_side=_SUCTION,
            ),
            ShellMidlineStrip(
                label="skin_pressure_surface",
                kind="skin",
                midline_twisted_pitch_axis_blade_frame=ps,
                thickness_m=t,
                closed=False,
                skin_side=_PRESSURE,
            ),
        ]
    out: list[ShellMidlineStrip] = []
    for s in skins:
        lab = _label_key(s.label)
        side = _normalise_side(
            s.skin_side,
            label=lab,
            pts=np.asarray(s.midline_twisted_pitch_axis_blade_frame, dtype=float),
        )
        if side is None:
            side = _SUCTION
        long_label = (
            "skin_suction_surface" if side == _SUCTION else "skin_pressure_surface"
        )
        out.append(
            replace(
                s,
                closed=False,
                skin_side=side,
                label=long_label,
            )
        )
    return out


def _classify_side_arcs(
    side: str,
    pts: NDArray[np.float64],
    thickness_m: float,
    split_s: list[float],
    *,
    merge_s_tol_m: float,
) -> list[ShellMidlineStrip]:
    """Split one open half-ring at web-foot arc parameters; name LE/bay/TE."""
    prefix = open_polyline_prefix_lengths(pts)
    L = float(prefix[-1]) if prefix.size else 0.0
    if L < 1e-12 or pts.shape[0] < 2:
        return []

    cuts = merge_sorted_s_values([0.0, L] + list(split_s), merge_s_tol_m)
    cuts = [0.0] + [c for c in cuts if 1e-9 < c < L - 1e-9] + [L]
    cuts = merge_sorted_s_values(cuts, merge_s_tol_m)
    if len(cuts) < 2:
        return []

    segs: list[tuple[float, float, NDArray[np.float64]]] = []
    for i in range(len(cuts) - 1):
        s0, s1 = float(cuts[i]), float(cuts[i + 1])
        arc = _open_arc_between(pts, prefix, s0, s1)
        if arc.shape[0] >= 2:
            segs.append((s0, s1, arc))
    if not segs:
        return []

    root = "skin_suction_surface" if side == _SUCTION else "skin_pressure_surface"
    n = len(segs)
    out: list[ShellMidlineStrip] = []
    bay_i = 0
    for i, (_s0, _s1, arc) in enumerate(segs):
        # Suction is TE→LE (index 0 = TE); pressure is LE→TE (index 0 = LE).
        if n == 1:
            skin_arc, bay_index = _LEADING, None
        elif i == 0:
            skin_arc, bay_index = (
                (_TRAILING, None) if side == _SUCTION else (_LEADING, None)
            )
        elif i == n - 1:
            skin_arc, bay_index = (
                (_LEADING, None) if side == _SUCTION else (_TRAILING, None)
            )
        else:
            skin_arc, bay_index = "bay", bay_i
            bay_i += 1

        if skin_arc == "bay":
            label = f"{root}:bay_{int(bay_index)}"
        else:
            label = f"{root}:{skin_arc}"
        out.append(
            ShellMidlineStrip(
                label=label,
                kind="skin",
                midline_twisted_pitch_axis_blade_frame=arc,
                thickness_m=float(thickness_m),
                closed=False,
                skin_side=side,
                skin_arc=skin_arc,
                bay_index=bay_index,
            )
        )
    return out


def split_skin_at_junctions(
    strips: tuple[ShellMidlineStrip, ...],
    *,
    merge_s_tol_m: float = _MERGE_S_TOL_M,
) -> tuple[ShellMidlineStrip, ...]:
    """Snap web/cap feet and panelise skin into suction/pressure × LE/bay/TE arcs.

    Hierarchical labels: ``skin_{suction|pressure}_surface:{leading_edge|bay_i|trailing_edge}``.
    """
    skin_list = [s for s in strips if s.kind == "skin"]
    if not skin_list:
        return strips

    side_skins = _ensure_ss_ps_skins(skin_list)
    by_side: dict[str, ShellMidlineStrip] = {}
    for s in side_skins:
        side = _normalise_side(s.skin_side, label=_label_key(s.label))
        if side is not None:
            by_side[side] = s
    if _SUCTION not in by_side or _PRESSURE not in by_side:
        others = [s for s in strips if s.kind != "skin"]
        return tuple(side_skins + others)

    out_non_skin: list[ShellMidlineStrip] = []
    web_feet_by_side: dict[str, list[float]] = {_SUCTION: [], _PRESSURE: []}
    web_polys: list[NDArray[np.float64]] = []

    for st in strips:
        if st.kind == "skin":
            continue
        if st.kind == "web":
            arr = np.asarray(st.midline_twisted_pitch_axis_blade_frame, dtype=float).copy()
            if arr.shape[0] < 2:
                out_non_skin.append(st)
                continue
            for row in (0, -1):
                p = arr[row]
                best_side = None
                best_d = 1e300
                best_q: NDArray[np.float64] | None = None
                best_s: float | None = None
                for side, sk in by_side.items():
                    pts = np.asarray(sk.midline_twisted_pitch_axis_blade_frame, dtype=float)
                    d, q = point_to_open_polyline_nearest(p, pts)
                    if d >= best_d:
                        continue
                    pref = open_polyline_prefix_lengths(pts)
                    a = pts[:-1]
                    b = pts[1:]
                    ab = b - a
                    l2 = np.sum(ab * ab, axis=1) + 1e-30
                    t = np.clip(np.sum((q.reshape(1, 2) - a) * ab, axis=1) / l2, 0.0, 1.0)
                    proj = a + t[:, None] * ab
                    j = int(np.argmin(np.sum((q.reshape(1, 2) - proj) ** 2, axis=1)))
                    best_d = float(d)
                    best_side = side
                    best_q = np.asarray(q, dtype=float).reshape(2)
                    best_s = float(pref[j] + float(t[j]) * float(np.linalg.norm(ab[j])))
                if best_side is not None and best_q is not None and best_s is not None:
                    arr[row] = best_q
                    web_feet_by_side[best_side].append(float(best_s))
            out_non_skin.append(
                replace(st, midline_twisted_pitch_axis_blade_frame=arr)
            )
            web_polys.append(arr)
            continue

        if st.kind == "cap":
            arr = np.asarray(st.midline_twisted_pitch_axis_blade_frame, dtype=float).copy()
            if arr.shape[0] < 2:
                out_non_skin.append(st)
                continue
            for row in (0, -1):
                p_end = arr[row]
                on_web = False
                for w in web_polys:
                    d_web, _q = point_to_open_polyline_nearest(p_end, w)
                    if d_web <= _CAP_ENDPOINT_ON_WEB_TOL_M:
                        on_web = True
                        break
                if on_web:
                    continue
                best_q = None
                best_d = 1e300
                for sk in by_side.values():
                    d, q = point_to_open_polyline_nearest(
                        p_end, np.asarray(sk.midline_twisted_pitch_axis_blade_frame)
                    )
                    if d < best_d:
                        best_d, best_q = float(d), q
                if best_q is not None:
                    arr[row] = np.asarray(best_q, dtype=float).reshape(2)
            out_non_skin.append(
                replace(st, midline_twisted_pitch_axis_blade_frame=arr)
            )
            continue

        out_non_skin.append(st)

    new_skins: list[ShellMidlineStrip] = []
    for side in (_SUCTION, _PRESSURE):
        sk = by_side[side]
        pts = np.asarray(sk.midline_twisted_pitch_axis_blade_frame, dtype=float)
        new_skins.extend(
            _classify_side_arcs(
                side,
                pts,
                float(sk.thickness_m),
                web_feet_by_side.get(side, []),
                merge_s_tol_m=merge_s_tol_m,
            )
        )

    if len(new_skins) < 2:
        new_skins = list(by_side.values())

    return tuple(new_skins + out_non_skin)


__all__ = [
    "_MERGE_S_TOL_M",
    "_CAP_ENDPOINT_ON_WEB_TOL_M",
    "split_skin_at_junctions",
]
