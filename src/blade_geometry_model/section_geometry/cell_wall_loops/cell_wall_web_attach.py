"""Web-to-skin attachment for void-cell wall loop construction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from blade_structure_utilities.geometry_utilities.section_contract.shell_midline_strip import ShellMidlineStrip

from .cell_wall_geom import drop_closing_vertex, first_ray_hit_on_ring


@dataclass(frozen=True)
class WebAttach:
    x_key: float
    label: str
    wpts: NDArray[np.float64]
    p_top: NDArray[np.float64]
    s_top: float
    p_bot: NDArray[np.float64]
    s_bot: float
    # Extended web polyline oriented top → bot (hits as endpoints)
    path_top_to_bot: NDArray[np.float64]


def make_attach(
    web: ShellMidlineStrip,
    ring: NDArray[np.float64],
    edge_starts: NDArray[np.float64],
    edge_lens: NDArray[np.float64],
) -> WebAttach:
    w = drop_closing_vertex(
        np.asarray(web.midline_twisted_pitch_axis_blade_frame, dtype=float)
    )
    if w.shape[0] < 2:
        raise ValueError(f"Web {web.label!r} midline must have at least two points")
    d0 = w[0] - w[1]
    d1 = w[-1] - w[-2]
    p0, s0 = first_ray_hit_on_ring(w[0], d0, ring, edge_starts, edge_lens)
    p1, s1 = first_ray_hit_on_ring(w[-1], d1, ring, edge_starts, edge_lens)
    # Interior samples between ends
    interior = w[1:-1] if w.shape[0] > 2 else np.zeros((0, 2), dtype=float)
    path_start_to_end = (
        np.vstack([p0.reshape(1, 2), interior, p1.reshape(1, 2)])
        if interior.size
        else np.vstack([p0, p1])
    )
    if p0[1] >= p1[1]:
        p_top, s_top, p_bot, s_bot = p0, s0, p1, s1
        path_top_to_bot = path_start_to_end
    else:
        p_top, s_top, p_bot, s_bot = p1, s1, p0, s0
        path_top_to_bot = path_start_to_end[::-1].copy()
    x_key = float(0.5 * (p_top[0] + p_bot[0]))
    return WebAttach(
        x_key=x_key,
        label=str(web.label),
        wpts=w,
        p_top=p_top,
        s_top=float(s_top),
        p_bot=p_bot,
        s_bot=float(s_bot),
        path_top_to_bot=path_top_to_bot,
    )


__all__ = ["WebAttach", "make_attach"]
