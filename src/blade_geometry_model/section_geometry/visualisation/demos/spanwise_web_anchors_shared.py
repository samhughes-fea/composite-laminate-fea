"""Shared spanwise station loader for section-geometry demos."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np

from blade_structure_precompute.examples._shared import load_blade_structure_inputs
from blade_structure_precompute.module.feasibility import Feasibility
from blade_structure_precompute.module.internal_force import InternalForce
from blade_structure_precompute.examples._shared.scaled_geometry import analysis_geometry_from_blade

DEFAULT_ROTOR = "new_3.2m_rotor"
DEFAULT_MATERIALS = {"skin": 2, "spar": 2, "web": 2}


def build_stations(
    *,
    repo_root: Path,
    rotor: str = DEFAULT_ROTOR,
    materials: Mapping[str, int] | None = None,
    structural_system_key: str = "5D-F",
    flap_tip_disp_ratio: float = 0.1,
    apply_benchmark_64_station_grid: bool = True,
) -> list[dict[str, Any]]:
    """Run the precompute scale pipeline and return per-station section data."""
    base = Path(repo_root)
    cot = base / "cotide_data_interfaces"
    repo_root_for_loader = base
    if not cot.is_dir():
        cot = base.parent / "cotide_data_interfaces"
        repo_root_for_loader = base.parent
    use_materials = dict(materials or DEFAULT_MATERIALS)
    inputs = load_blade_structure_inputs(
        rotor_dir=cot / rotor,
        naca_file=cot / "NACA_63-415.dat",
        repo_root=repo_root_for_loader,
        structural_system_key=str(structural_system_key),
        component_materials=use_materials,
        flap_tip_disp_ratio=float(flap_tip_disp_ratio),
        apply_benchmark_64_station_grid=bool(apply_benchmark_64_station_grid),
    )

    scale = analysis_geometry_from_blade(inputs.blade_geometry, inputs.sampling_distribution_parameters)
    try:
        ifm = InternalForce(scaling=scale, loading=inputs.loading)
        ifm.execute()
        Feasibility(
            internal_force=ifm,
            scaling=scale,
            structural_system_parameters=inputs.structural_system_parameters,
            apply_thickening=True,
            tc_iteration_mode="thicken_only",
            fos=2.5,
            root_blend_mode="off",
            smooth_section_depth=False,
        ).execute()
    except Exception as exc:
        print(f"[spanwise-loader] feasibility pass skipped: {type(exc).__name__}: {exc}")

    scale_set = scale.get_scale_set()
    geom = scale_set.get_outer_loop_geometry_S_for_analysis()
    counts = scale_set.outer_loop_point_counts
    rows = scale_set.primary_bin.rows

    stations: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        n = int(counts[i])
        stations.append(
            {
                "idx": int(row.station_index),
                "zL": float(row.zL),
                "chord": float(row.chord),
                "coords": np.asarray(geom[i, :n, :], dtype=float),
                "metadata": {
                    "chord": float(row.chord),
                    "twist_deg": float(row.twist),
                },
            }
        )
    return stations


__all__ = ["DEFAULT_MATERIALS", "DEFAULT_ROTOR", "build_stations"]
