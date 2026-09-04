"""Build LE / bay / TE void-cell wall loops from skin + web midlines."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from numpy.typing import NDArray

from blade_structure_utilities.geometry_utilities.section_contract.cell_wall_loop import CellWallLoop
from blade_structure_utilities.geometry_utilities.section_contract.shell_midline_strip import ShellMidlineStrip

from .cell_wall_geom import (
    close_loop,
    drop_closing_vertex,
    edge_geometry,
    mean_x,
    shoelace_area,
    skin_arc,
    stitch_skin_ring,
)
from .cell_wall_web_attach import make_attach


def loop_dto(
    cell_id: int,
    poly: NDArray[np.float64],
    *,
    web_labels: tuple[str, ...],
    piece_labels: tuple[str, ...],
) -> CellWallLoop:
    open_poly = drop_closing_vertex(poly)
    area = abs(shoelace_area(open_poly))
    if np.hypot(*(poly[0] - poly[-1])) > 1e-12:
        poly = np.vstack([poly, poly[0]])
    return CellWallLoop(
        id=int(cell_id),
        polyline_twisted_pitch_axis_blade_frame=np.asarray(poly, dtype=float),
        area_m2=float(area),
        web_labels=web_labels,
        piece_labels=piece_labels,
    )


def build_cell_wall_loops(
    strips: Sequence[ShellMidlineStrip],
) -> tuple[CellWallLoop, ...]:
    """Build constructive cell-wall loops from midline strips.

    Parameters
    ----------
    strips
        Skin / web / cap midlines (caps ignored). Prefer topology-prepared
        strips from ``build_shell_strip_topology``.

    Returns
    -------
    tuple[CellWallLoop, ...]
        LE → TE ordered cell wall loops. Length is ``1`` when there are no
        webs, else ``n_webs + 1``.
    """
    skins = [s for s in strips if s.kind == "skin"]
    webs = [s for s in strips if s.kind == "web"]
    ring = stitch_skin_ring(skins)
    if ring.shape[0] < 3:
        raise ValueError("Skin centreline too short for a cell wall loop")

    if not webs:
        poly = np.vstack([ring, ring[0]])
        return (loop_dto(0, poly, web_labels=(), piece_labels=("skin",)),)

    edge_starts, edge_lens, perimeter = edge_geometry(ring)
    attachments = [make_attach(w, ring, edge_starts, edge_lens) for w in webs]
    attachments.sort(key=lambda a: a.x_key)
    n_web = len(attachments)

    def skin_le_or_te(s_a: float, s_b: float, *, le: bool) -> NDArray[np.float64]:
        fw = skin_arc(ring, edge_starts, edge_lens, perimeter, s_a, s_b, forward=True)
        bw = skin_arc(ring, edge_starts, edge_lens, perimeter, s_a, s_b, forward=False)
        if le:
            return fw if mean_x(fw) <= mean_x(bw) else bw
        return fw if mean_x(fw) >= mean_x(bw) else bw

    def prefer_between(s_a: float, s_b: float, x_lo: float, x_hi: float) -> NDArray[np.float64]:
        """Shorter skin arc between attachments (bay upper/lower)."""
        _ = x_lo, x_hi
        fw = skin_arc(ring, edge_starts, edge_lens, perimeter, s_a, s_b, forward=True)
        bw = skin_arc(ring, edge_starts, edge_lens, perimeter, s_a, s_b, forward=False)

        def _alen(pts: NDArray[np.float64]) -> float:
            if pts.shape[0] < 2:
                return 0.0
            d = np.diff(pts, axis=0)
            return float(np.sum(np.hypot(d[:, 0], d[:, 1])))

        return fw if _alen(fw) <= _alen(bw) else bw

    loops: list[CellWallLoop] = []

    a0 = attachments[0]
    le_skin = skin_le_or_te(a0.s_top, a0.s_bot, le=True)
    te_skin_single = skin_le_or_te(a0.s_top, a0.s_bot, le=False)
    le_poly = close_loop([le_skin, a0.path_top_to_bot[::-1]])
    loops.append(
        loop_dto(
            0,
            le_poly,
            web_labels=(a0.label,),
            piece_labels=("skin", a0.label),
        )
    )

    for k in range(n_web - 1):
        a = attachments[k]
        b = attachments[k + 1]
        upper = prefer_between(a.s_top, b.s_top, a.x_key, b.x_key)
        lower = prefer_between(b.s_bot, a.s_bot, a.x_key, b.x_key)
        bay = close_loop(
            [
                upper,
                b.path_top_to_bot,
                lower,
                a.path_top_to_bot[::-1],
            ]
        )
        loops.append(
            loop_dto(
                len(loops),
                bay,
                web_labels=(a.label, b.label),
                piece_labels=("skin", b.label, "skin", a.label),
            )
        )

    an = attachments[-1]
    te_skin = te_skin_single if n_web == 1 else skin_le_or_te(an.s_top, an.s_bot, le=False)
    te_poly = close_loop([te_skin, an.path_top_to_bot[::-1]])
    loops.append(
        loop_dto(
            len(loops),
            te_poly,
            web_labels=(an.label,),
            piece_labels=("skin", an.label),
        )
    )

    return tuple(loops)


# Historical alias — prefer :func:`build_cell_wall_loops`.
build_void_cell_wall_loops = build_cell_wall_loops


__all__ = ["loop_dto", "build_cell_wall_loops"]
