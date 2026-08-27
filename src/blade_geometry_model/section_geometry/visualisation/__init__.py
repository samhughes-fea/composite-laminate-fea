"""Matplotlib plot helpers and visualisation demos for section_geometry."""

from .plot import (
    _DEFAULT_COLOR,
    _component_color,
    apply_structural_section_axes,
    draw_section_sdf_panel,
    fit_square_section_axes,
    plot_sdf_field,
    plot_section,
    plot_section_from_mesh,
    plot_section_hybrid,
    plot_section_with_quadtree,
    plot_shell_midline_strip_topology,
    taxonomy_plot_caption,
)

__all__ = [
    "plot_sdf_field",
    "apply_structural_section_axes",
    "fit_square_section_axes",
    "plot_section",
    "plot_section_from_mesh",
    "plot_section_hybrid",
    "plot_section_with_quadtree",
    "plot_shell_midline_strip_topology",
    "draw_section_sdf_panel",
    "taxonomy_plot_caption",
    "_DEFAULT_COLOR",
    "_component_color",
]
