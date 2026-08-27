"""Constructive laminate/core polygons and hybrid property helpers."""

from .export import emit_constructive_polygons, emit_core_polygons, emit_laminate_polygons
from .labels import (
    classify_property_labels,
    is_constructive_label,
    is_core_label,
    is_laminate_label,
    is_residual_label,
    is_skin_label,
)
from .properties import section_properties_from_polygons

__all__ = [
    "classify_property_labels",
    "emit_constructive_polygons",
    "emit_core_polygons",
    "emit_laminate_polygons",
    "is_constructive_label",
    "is_core_label",
    "is_laminate_label",
    "is_residual_label",
    "is_skin_label",
    "section_properties_from_polygons",
]
