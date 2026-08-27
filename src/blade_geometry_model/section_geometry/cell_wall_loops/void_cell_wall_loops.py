"""
void_cell_wall_loops
====================
Constructive void-cell wall mid-surface loops from skin + web midlines.

Thin orchestrator: geometry helpers, web attach, and loop builders live in
focused modules. ``cell_wall_loops_case_payload`` lives beside the demo and is
re-exported here for compatibility.
"""

from __future__ import annotations

from .void_cell_loop_builders import build_void_cell_wall_loops


def cell_wall_loops_case_payload(*args, **kwargs):
    """Compatibility re-export of the demo payload helper."""
    from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.demos.void_cell_wall_loops_case_payload import (
        cell_wall_loops_case_payload as _impl,
    )

    return _impl(*args, **kwargs)


__all__ = ["build_void_cell_wall_loops", "cell_wall_loops_case_payload"]
