"""
examples/manystation_bench.py
=============================
Many-station throughput benchmark for the section_geometry property backend.

Times the per-station hot path (section build + property integration,
and optionally plot + JSON export) across ``--stations`` stations.

Run from the repository root:
    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/manystation_bench.py --stations 25
    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/manystation_bench.py --stations 10 --backend hybrid
    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/manystation_bench.py --stations 10 --compare
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import tempfile
import time
from pathlib import Path

# Enable phi-eval profiling before engine imports.
os.environ.setdefault("SECTION_GEOMETRY_PROFILE", "1")

_erp = Path(__file__).resolve().parent / "_ensure_repo_path.py"
if _erp.exists():
    _spec = importlib.util.spec_from_file_location("_ensure_repo_path", _erp)
    _mod = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_mod)
    _mod.ensure_repo_path()

import numpy as np

from blade_structure_utilities.geometry_utilities.section_geometry.api.factory import (
    build_section_view,
    resolve_system_type,
)
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_backend import (
    quadtree_spec_for_airfoil,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import AirfoilSDF
from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.props_compute import (
    compute_section_properties,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.cache import SectionEvalCache
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.profiling import get_stats, reset_stats


def _station_params(n: int):
    """Spread stations over a few NACA codes and twist angles."""
    codes = ["2412", "2410", "4412", "0012"]
    for i in range(n):
        code = codes[i % len(codes)]
        twist = np.deg2rad(15.0 * (i / max(1, n - 1)))  # 0 .. 15 deg
        yield code, float(twist)


def _run_bench(args, backend: str) -> dict:
    sys_type = resolve_system_type(args.system)
    tmp = Path(tempfile.mkdtemp(prefix=f"manystation_bench_{backend}_"))
    stage_s = {"build": 0.0, "properties": 0.0, "plot": 0.0, "export": 0.0}

    reset_stats()
    t0 = time.perf_counter()
    last_meta = {}
    for i, (code, twist) in enumerate(_station_params(args.stations)):
        t = time.perf_counter()
        airfoil = AirfoilSDF.from_naca(code, n_points=args.n_points, chord=1.0)
        section = build_section_view(airfoil, sys_type, twist_angle_rad=twist)
        stage_s["build"] += time.perf_counter() - t

        spec = quadtree_spec_for_airfoil(
            airfoil, chord=1.0, max_depth=args.depth, max_cells=150000
        )
        eval_cache = SectionEvalCache()

        t = time.perf_counter()
        _props, _meta, mesh = compute_section_properties(
            section,
            backend=backend,
            quadtree_spec=spec,
            airfoil_for_spec=airfoil,
            with_mesh=True,
        )
        stage_s["properties"] += time.perf_counter() - t
        last_meta = _meta

        if args.plot and mesh is not None:
            from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot import (
                plot_section_from_mesh,
                plot_section_hybrid,
            )
            import matplotlib

            matplotlib.use("Agg", force=False)
            import matplotlib.pyplot as plt

            t = time.perf_counter()
            if backend == "hybrid":
                fig, _ = plot_section_hybrid(section, mesh)
            else:
                fig, _ = plot_section_from_mesh(mesh)
            fig.savefig(tmp / f"station_{i:03d}.png", dpi=170)
            plt.close(fig)
            stage_s["plot"] += time.perf_counter() - t

        if args.export:
            from blade_structure_utilities.geometry_utilities.section_geometry.props_emit.export import (
                SectionPropertiesReport,
                export_section_json,
            )
            from blade_structure_utilities.geometry_utilities.section_geometry.sdf.grid import SDFGrid

            grid = SDFGrid.from_bbox(spec.x_min, spec.x_max, spec.y_min, spec.y_max, 384, 180)
            report = SectionPropertiesReport.from_precomputed(
                section, _props, _meta, mesh
            )
            t = time.perf_counter()
            export_section_json(
                section,
                grid,
                {},
                str(tmp / f"station_{i:03d}.json"),
                include_component_zero_contours=True,
                include_geometry_detail=True,
                eval_cache=eval_cache,
                properties_report=report,
            )
            stage_s["export"] += time.perf_counter() - t

    wall = time.perf_counter() - t0
    n = args.stations
    stats = get_stats()
    return {
        "backend": backend,
        "wall": wall,
        "n": n,
        "stage_s": stage_s,
        "stats": stats.to_dict() if stats is not None else {},
        "meta": last_meta,
        "tmp": tmp,
        "ms_per_station": wall / n * 1000,
        "properties_ms": stage_s["properties"] / n * 1000,
    }


def _print_result(r: dict) -> None:
    n = r["n"]
    print(f"\nMany-station bench: {n} stations, backend={r['backend']}")
    print(f"  total wall        : {r['wall']:8.3f} s   ({r['ms_per_station']:7.1f} ms/station)")
    for stage, v in r["stage_s"].items():
        if v:
            print(f"  {stage + '_s':<18}: {v:8.3f} s   ({v / n * 1000:7.1f} ms/station)")
    d = r["stats"]
    if d:
        print(f"  phi_eval_count    : {d.get('phi_eval_count', 0):>12,}")
        print(f"  sdf_polygon_count : {d.get('sdf_polygon_count', 0):>12,}")
    meta = r["meta"]
    if meta.get("constructive_s") is not None:
        print(f"  constructive_s    : {meta['constructive_s']:.4f} (last station)")
        print(f"  residual_quadtree_s: {meta.get('residual_quadtree_s', 0):.4f} (last station)")
        print(f"  residual_labels   : {meta.get('residual_labels')}")
    print(f"  artifacts in      : {r['tmp']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stations", type=int, default=20)
    ap.add_argument("--depth", type=int, default=7)
    ap.add_argument("--system", default="2D-CN")
    ap.add_argument("--n-points", type=int, default=120)
    ap.add_argument("--backend", default="hybrid", choices=("hybrid", "quadtree", "grid"))
    ap.add_argument(
        "--compare",
        action="store_true",
        help="run both hybrid and quadtree and print speedup",
    )
    ap.add_argument("--plot", action="store_true", help="also render a PNG per station")
    ap.add_argument("--export", action="store_true", help="also write a section JSON per station")
    args = ap.parse_args()

    if args.compare:
        r_qt = _run_bench(args, "quadtree")
        _print_result(r_qt)
        r_hy = _run_bench(args, "hybrid")
        _print_result(r_hy)
        speedup = r_qt["properties_ms"] / max(r_hy["properties_ms"], 1e-9)
        print(f"\n  properties speedup (quadtree/hybrid): {speedup:.2f}x")
        print(f"  hybrid properties_ms/station: {r_hy['properties_ms']:.1f}")
        return

    r = _run_bench(args, args.backend)
    _print_result(r)


if __name__ == "__main__":
    main()
