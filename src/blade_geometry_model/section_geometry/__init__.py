"""Section geometry **worker** — use-case-agnostic implicit section kernel.

Owns the nested CSG toolbox (:mod:`.sdf`). Emits props / midlines into
:mod:`blade_structure_utilities.geometry_utilities.section_contract` DTOs.
Sizing and fatigue orchestration call this package; they do not own it.

Entrypoints (prefer the first): ``SectionGeometryRunner`` →
``build_section_geometry`` → ``build_section_with_thicknesses`` (assemble only)
→ ``build_section_view`` (demos / properties).
"""

from .api import (
    SectionGeometryResult,
    SectionGeometryRunner,
    StationLayoutResolution,
    build_section_geometry,
    build_section_view,
    build_section_with_thicknesses,
    resolve_system_type,
    section_geometry_prep_key,
)
from .layout.types import SDFCallable
from .layout.section_axes import max_thickness_chord_x, pitch_axis_x_from_le
from .layout.structural import (
    FixedCapAnchor,
    StructuralFamily,
    parse_fixed_cap_anchor,
    parse_structural_family,
)
from .layout.system_layout import SYSTEM_TYPE_KEYS, SystemLayoutSpec
from .sections import MultiCellSection, multicell_from_layout
from .sdf.airfoil import AirfoilSDF
from .sdf.grid import SDFGrid
from .props_emit.export import SectionPropertiesReport, export_section_json
from .props_emit.props_handoff import (
    fiber_extents_from_airfoil,
    fiber_extents_from_outline,
    outer_polygon_from_airfoil,
    topology_for_section_properties,
)
from .visualisation import plot_sdf_field, plot_section

__version__ = "0.2.0"
__author__ = "Sam Hughes"

__all__ = [
    "SectionGeometryResult",
    "SectionGeometryRunner",
    "StationLayoutResolution",
    "build_section_geometry",
    "build_section_with_thicknesses",
    "multicell_from_layout",
    "section_geometry_prep_key",
    "SDFCallable",
    "AirfoilSDF",
    "SDFGrid",
    "MultiCellSection",
    "SectionPropertiesReport",
    "export_section_json",
    "fiber_extents_from_outline",
    "fiber_extents_from_airfoil",
    "outer_polygon_from_airfoil",
    "topology_for_section_properties",
    "plot_section",
    "plot_sdf_field",
    "StructuralFamily",
    "FixedCapAnchor",
    "parse_structural_family",
    "parse_fixed_cap_anchor",
    "pitch_axis_x_from_le",
    "max_thickness_chord_x",
    "build_section_view",
    "resolve_system_type",
    "SYSTEM_TYPE_KEYS",
    "SystemLayoutSpec",
]
