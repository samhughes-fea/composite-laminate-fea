"""
visualisation/demos/brep_vs_implicit_offset_demo.py
===================================================
Why the representation was changed: what an inward offset costs each way.

Wall thickness is the design variable the sizing loop actually turns, and
applying it means offsetting the mould line inward. This demo runs that one
operation two ways on the same aerofoil:

* **Curve offset** (the boundary-representation move) - displace every vertex
  along its mitred normal. Cheap, exact where the boundary is locally convex,
  and *self-intersecting* wherever the offset distance exceeds the local radius
  of curvature. On an aerofoil that happens first at the trailing-edge wedge,
  where the two surfaces run toward each other: past a few millimetres the two
  offset surfaces cross and the curve folds into a swallowtail loop. The
  enclosed area computed from that curve is then wrong - the shoelace integral
  counts the folded lobe with the opposite sign.

* **Level-set offset** (what the package does) - evaluate ``phi = -t``. The
  boundary that comes back is the set of points at distance ``t``, which cannot
  self-intersect: where the wedge closes, the region simply stops existing.
  There is no fold to detect and nothing to trim.

**On fairness.** A production B-rep kernel does not ship the naive curve: it
detects these loops and trims them, and for an aerofoil at modest offsets it
will get the right answer. The claim here is narrower and is the one the talk
makes - the *repair step exists at all*, it is the part that gets hard as
sections get thinner and topologies change, and the implicit path never runs
it. The mitre is capped at the usual limit of 4, exactly as a real
implementation would, so the failure shown is folding and not a spike artifact.

Writes under ``visualisation/output/brep_vs_implicit_offset/``:

* ``brep_vs_implicit_offset.png`` - the four-panel comparison.
* ``brep_vs_implicit_offset.json`` - self-intersection counts and area error.

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/brep_vs_implicit_offset_demo.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

_erp = Path(__file__).resolve().parent / "_ensure_repo_path.py"
_spec = importlib.util.spec_from_file_location("_ensure_repo_path", _erp)
_ensure_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_ensure_mod)
_ensure_mod.ensure_repo_path()

from blade_structure_utilities.geometry_utilities.section_geometry import (
    AirfoilSDF,
    SDFGrid,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.figure_io import (
    add_output_and_presentation_args,
    apply_presentation_style,
    save_figure,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.palette import (
    INK,
    MUTED,
    NAVY,
    RED,
    TEAL,
)

#: The standard mitre limit used by stroke/offset implementations. Without it a
#: near-cusp vertex throws its offset point to infinity, which would make this
#: comparison a strawman about spikes rather than about folding.
_MITRE_LIMIT = 4.0


def _signed_area(polygon: np.ndarray) -> float:
    """Shoelace area. Negative for a clockwise loop, and *cancelling* over a fold."""
    x = polygon[:, 0]
    y = polygon[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _inward_mitre_offset(polygon: np.ndarray, distance: float) -> np.ndarray:
    """Displace every vertex along its mitred inward normal by ``distance``.

    This is the naive curve offset: a local operation with no global awareness,
    which is precisely why it folds where the offset outruns the curvature.
    """
    points = np.asarray(polygon, dtype=float)
    # Orient counter-clockwise so "left of travel" is reliably inward.
    if _signed_area(points) < 0.0:
        points = points[::-1]

    following = np.roll(points, -1, axis=0)
    preceding = np.roll(points, 1, axis=0)

    def _left_normals(starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
        edges = ends - starts
        lengths = np.linalg.norm(edges, axis=1, keepdims=True)
        lengths[lengths == 0.0] = 1.0
        edges = edges / lengths
        return np.column_stack((-edges[:, 1], edges[:, 0]))

    incoming_normal = _left_normals(preceding, points)
    outgoing_normal = _left_normals(points, following)

    # Mitre vector: bisector scaled so the offset edges still meet at a point.
    bisector = incoming_normal + outgoing_normal
    scale = 1.0 + np.sum(incoming_normal * outgoing_normal, axis=1)
    scale[np.abs(scale) < 1e-12] = 1e-12
    mitre = bisector / scale[:, None]

    lengths = np.linalg.norm(mitre, axis=1)
    over_limit = lengths > _MITRE_LIMIT
    if np.any(over_limit):
        mitre[over_limit] *= (_MITRE_LIMIT / lengths[over_limit])[:, None]

    return points + float(distance) * mitre


def _count_self_intersections(polygon: np.ndarray) -> int:
    """Proper crossings between non-adjacent segments of a closed polyline.

    O(N^2) and deliberately simple: at a couple of hundred vertices it costs
    nothing, and a sweep line would only obscure what is being counted.
    """
    starts = np.asarray(polygon, dtype=float)
    ends = np.roll(starts, -1, axis=0)
    count = int(starts.shape[0])

    def _orientation(a, b, c):
        return np.sign(
            (b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1])
            - (b[..., 1] - a[..., 1]) * (c[..., 0] - a[..., 0])
        )

    crossings = 0
    for i in range(count):
        # Skip the two neighbours (they share an endpoint) and, for segment 0,
        # the closing segment as well.
        j_lo = i + 2
        j_hi = count - 1 if i == 0 else count
        if j_lo >= j_hi:
            continue
        p1 = starts[i]
        p2 = ends[i]
        q1 = starts[j_lo:j_hi]
        q2 = ends[j_lo:j_hi]
        d1 = _orientation(q1, q2, p1)
        d2 = _orientation(q1, q2, p2)
        d3 = _orientation(p1, p2, q1)
        d4 = _orientation(p1, p2, q2)
        crossings += int(np.sum((d1 * d2 < 0) & (d3 * d4 < 0)))
    return crossings


def _self_intersection_points(polygon: np.ndarray) -> np.ndarray:
    """Where the offset curve crosses itself, for marking on a figure.

    Same predicate as :func:`_count_self_intersections`; kept separate so the
    counting sweep stays allocation-free.
    """
    starts = np.asarray(polygon, dtype=float)
    ends = np.roll(starts, -1, axis=0)
    count = int(starts.shape[0])
    found: list[tuple[float, float]] = []

    def _cross(a, b):
        return a[0] * b[1] - a[1] * b[0]

    for i in range(count):
        j_lo = i + 2
        j_hi = count - 1 if i == 0 else count
        for j in range(j_lo, j_hi):
            p, r = starts[i], ends[i] - starts[i]
            q, s = starts[j], ends[j] - starts[j]
            denominator = _cross(r, s)
            if abs(denominator) < 1e-15:
                continue
            t_param = _cross(q - p, s) / denominator
            u_param = _cross(q - p, r) / denominator
            if 0.0 < t_param < 1.0 and 0.0 < u_param < 1.0:
                found.append(tuple(p + t_param * r))
    return np.asarray(found, dtype=float).reshape(-1, 2)


def _level_set_area(grid: SDFGrid, phi: np.ndarray, distance: float) -> float:
    """Area enclosed by ``phi = -distance``, by direct measure on the grid."""
    return float(grid.area(phi + float(distance)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--naca", default="2412")
    parser.add_argument("--chord", type=float, default=1.0)
    parser.add_argument("--n-points", type=int, default=220)
    parser.add_argument("--nx", type=int, default=1100)
    parser.add_argument("--ny", type=int, default=480)
    parser.add_argument(
        "--max-offset",
        type=float,
        default=0.030,
        help="Largest inward offset to sweep [m].",
    )
    parser.add_argument("--samples", type=int, default=40)
    add_output_and_presentation_args(parser, default_stem="brep_vs_implicit_offset")
    args = parser.parse_args(argv)
    presentation = bool(args.presentation)
    apply_presentation_style(presentation)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    airfoil = AirfoilSDF.from_naca(
        str(args.naca), n_points=int(args.n_points), chord=float(args.chord)
    )
    polygon = np.asarray(airfoil.vertices, dtype=float)
    grid = SDFGrid.from_airfoil(airfoil, nx=int(args.nx), ny=int(args.ny))
    phi = np.asarray(airfoil(grid.X, grid.Y), dtype=float)

    distances = np.linspace(
        float(args.max_offset) / int(args.samples), float(args.max_offset), int(args.samples)
    )
    # A handful of gauges to draw, spanning "fine" to "the wedge has closed".
    drawn = [0.004, 0.010, 0.020, 0.030]

    records = []
    for distance in distances:
        offset_polygon = _inward_mitre_offset(polygon, distance)
        crossings = _count_self_intersections(offset_polygon)
        curve_area = abs(_signed_area(offset_polygon))
        true_area = _level_set_area(grid, phi, distance)
        records.append(
            {
                "offset_m": float(distance),
                "curve_self_intersections": int(crossings),
                "curve_area_m2": float(curve_area),
                "level_set_area_m2": float(true_area),
                "area_rel_error": float(
                    abs(curve_area - true_area) / true_area if true_area > 0 else np.nan
                ),
            }
        )

    # Wide: this lands in a full-width slide panel of roughly 2.6:1, and a
    # squarer figure would be letterboxed down to two thirds of the width.
    figure = plt.figure(figsize=(17.0, 6.6))
    outer = figure.add_gridspec(2, 2, height_ratios=[1.0, 1.08], hspace=0.28, wspace=0.14)
    axis_curve = figure.add_subplot(outer[0, 0])
    axis_level = figure.add_subplot(outer[0, 1])
    axis_zoom = figure.add_subplot(outer[1, 0])
    axis_metric = figure.add_subplot(outer[1, 1])

    shades = plt.cm.viridis(np.linspace(0.15, 0.85, len(drawn)))

    # --- top left: the curve offset, folding ---------------------------------
    axis_curve.plot(
        polygon[:, 0], polygon[:, 1], color=INK, linewidth=1.8, zorder=5, label="mould line"
    )
    for colour, distance in zip(shades, drawn):
        offset_polygon = _inward_mitre_offset(polygon, distance)
        closed = np.vstack([offset_polygon, offset_polygon[:1]])
        crossings = _count_self_intersections(offset_polygon)
        axis_curve.plot(
            closed[:, 0],
            closed[:, 1],
            color=colour,
            linewidth=1.4,
            label=f"t = {distance * 1e3:.0f} mm  ({crossings} crossings)",
        )
    axis_curve.set_title("Curve offset: displace each vertex along its normal", fontsize=12)
    # Below the axes: equal aspect letterboxes this panel, so any in-axes legend
    # lands on top of the aerofoil.
    axis_curve.legend(
        fontsize=8.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.01),
        ncol=3,
        frameon=False,
    )

    # --- top right: the level set, clean --------------------------------------
    axis_level.plot(polygon[:, 0], polygon[:, 1], color=INK, linewidth=1.8, zorder=5)
    for colour, distance in zip(shades, drawn):
        # linestyles must be forced: matplotlib dashes negative contour levels by
        # default, which would make the two panels look different for a reason
        # that has nothing to do with the comparison.
        axis_level.contour(
            grid.X,
            grid.Y,
            phi,
            levels=[-float(distance)],
            colors=[colour],
            linewidths=1.4,
            linestyles="solid",
        )
    axis_level.set_title(r"Level-set offset: evaluate $\varphi = -t$", fontsize=12)
    axis_level.text(
        0.98,
        0.08,
        "0 crossings, every gauge — by construction",
        transform=axis_level.transAxes,
        ha="right",
        fontsize=10,
        style="italic",
        color=TEAL,
    )

    vertical_pad = 0.035 * float(args.chord)
    for axis in (axis_curve, axis_level):
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlim(polygon[:, 0].min() - 0.02, polygon[:, 0].max() + 0.02)
        axis.set_ylim(
            float(polygon[:, 1].min()) - vertical_pad,
            float(polygon[:, 1].max()) + vertical_pad,
        )
        axis.set_xticks([])
        axis.set_yticks([])

    # --- bottom left: the trailing edge, where it happens first ---------------
    trailing_x = float(polygon[:, 0].max())
    worst = drawn[-1]
    folded = _inward_mitre_offset(polygon, worst)
    closed = np.vstack([folded, folded[:1]])

    axis_zoom.plot(polygon[:, 0], polygon[:, 1], color=INK, linewidth=2.2, label="mould line")
    axis_zoom.plot(
        closed[:, 0],
        closed[:, 1],
        color=RED,
        linewidth=2.0,
        label=f"curve offset, t = {worst * 1e3:.0f} mm",
    )
    axis_zoom.contour(
        grid.X,
        grid.Y,
        phi,
        levels=[-worst],
        colors=[TEAL],
        linewidths=2.4,
        linestyles="solid",
    )
    axis_zoom.plot([], [], color=TEAL, linewidth=2.4, label="level set, same t")

    crossing_points = _self_intersection_points(folded)
    if crossing_points.size:
        axis_zoom.scatter(
            crossing_points[:, 0],
            crossing_points[:, 1],
            s=150,
            facecolor="none",
            edgecolor=RED,
            linewidths=2.4,
            zorder=8,
            label="self-intersection",
        )

    # Window sized to the panel's own aspect and wide enough that the aerofoil
    # still reads as an aerofoil: zoomed harder, the mould line degenerates into
    # two straight lines and the reader loses where they are.
    zoom_half_width = 0.26 * float(args.chord)
    zoom_aspect = 1.75
    zoom_center = (trailing_x - 0.62 * zoom_half_width, 0.0)
    axis_zoom.set_aspect("equal", adjustable="box")
    axis_zoom.set_xlim(
        zoom_center[0] - zoom_half_width, zoom_center[0] + zoom_half_width
    )
    axis_zoom.set_ylim(
        zoom_center[1] - zoom_half_width / zoom_aspect,
        zoom_center[1] + zoom_half_width / zoom_aspect,
    )
    axis_zoom.set_xticks([])
    axis_zoom.set_yticks([])
    axis_zoom.set_title(
        "Trailing edge: the offset outruns the curvature and folds", fontsize=12
    )
    axis_zoom.legend(fontsize=9.5, loc="lower left")
    # The teal curve stopping short is the result, not a truncation: past this
    # station the wedge is thinner than 2t, so there is no material left and the
    # level set has nothing to trace. The curve offset has no such notion and
    # keeps going, which is exactly why it folds.
    axis_zoom.annotate(
        "the level set simply ends —\nthe wedge is thinner than 2t here",
        xy=(zoom_center[0] + 0.02 * zoom_half_width, 0.0),
        xytext=(0.52, 0.80),
        textcoords="axes fraction",
        fontsize=9.5,
        color=TEAL,
        arrowprops={"arrowstyle": "->", "color": TEAL, "linewidth": 1.2},
    )

    # --- bottom right: what it costs -----------------------------------------
    offsets_mm = [r["offset_m"] * 1e3 for r in records]
    crossings = [r["curve_self_intersections"] for r in records]
    area_error = [100.0 * r["area_rel_error"] for r in records]

    # Area error leads: it is the smooth, large signal and it is the one that
    # reaches the sizing loop. The crossing count is a step function between one
    # and two and says far less on its own.
    axis_metric.plot(
        offsets_mm,
        area_error,
        color=NAVY,
        linewidth=2.4,
        label="curve offset: enclosed-area error",
    )
    axis_metric.axhline(
        0.0, color=TEAL, linewidth=2.4, label="level set: exact by measure"
    )
    axis_metric.set_xlabel("inward offset t [mm]")
    axis_metric.set_ylabel("enclosed-area error vs level set [%]", color=NAVY)
    axis_metric.tick_params(axis="y", labelcolor=NAVY)
    axis_metric.grid(True, alpha=0.25)

    axis_crossings = axis_metric.twinx()
    axis_crossings.step(
        offsets_mm,
        crossings,
        where="post",
        color=RED,
        linewidth=1.8,
        linestyle="--",
        label="curve offset: self-intersections",
    )
    axis_crossings.set_ylabel("self-intersections", color=RED)
    axis_crossings.tick_params(axis="y", labelcolor=RED)
    axis_crossings.set_ylim(-0.15, max(crossings) + 0.85)

    first_fold = next((r for r in records if r["curve_self_intersections"] > 0), None)
    if first_fold is not None:
        axis_metric.axvline(
            first_fold["offset_m"] * 1e3, color=MUTED, linewidth=1.0, linestyle=":"
        )
        axis_metric.annotate(
            f"folds from t = {first_fold['offset_m'] * 1e3:.1f} mm\n"
            "— the sharp TE is a cusp",
            xy=(first_fold["offset_m"] * 1e3, max(area_error) * 0.56),
            xytext=(14, 0),
            textcoords="offset points",
            fontsize=9.5,
            color=INK,
        )

    handles, labels = axis_metric.get_legend_handles_labels()
    extra_handles, extra_labels = axis_crossings.get_legend_handles_labels()
    axis_metric.legend(
        handles + extra_handles, labels + extra_labels, fontsize=8.5, loc="upper left"
    )
    axis_metric.set_title("What the repair step is for", fontsize=12)

    figure.suptitle(
        "One inward offset, two representations — the fold is the work the implicit path never does",
        fontsize=13.5,
    )
    figure.tight_layout()
    out_png = out_dir / "brep_vs_implicit_offset.png"
    save_figure(figure, out_png, presentation=presentation)
    plt.close(figure)
    print(f"Wrote {out_png}")

    out_json = out_dir / "brep_vs_implicit_offset.json"
    out_json.write_text(
        json.dumps(
            {
                "naca": str(args.naca),
                "chord_m": float(args.chord),
                "n_points": int(args.n_points),
                "mitre_limit": _MITRE_LIMIT,
                "first_fold_offset_m": (
                    first_fold["offset_m"] if first_fold is not None else None
                ),
                "sweep": records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {out_json}")

    if first_fold is not None:
        print(
            f"  curve offset first self-intersects at t = {first_fold['offset_m'] * 1e3:.1f} mm"
        )
    print(f"  worst area error over the sweep: {max(area_error):.1f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
