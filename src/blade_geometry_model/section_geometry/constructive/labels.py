"""Laminate / core / residual label classification for hybrid properties."""

from __future__ import annotations

from typing import Any, Iterable


def _label_key(label: Any) -> str:
    val = getattr(label, "value", label)
    return str(val)


def _canonical_label_key(label: Any) -> str:
    """Map temporary short prefixes onto long names when reading external maps."""
    key = _label_key(label)
    if key.startswith("web_") and not key.startswith("shear_web_"):
        return "shear_" + key
    if key.startswith("core_") and not key.startswith("sandwich_core_"):
        return "sandwich_" + key
    if key == "core":
        return "sandwich_core"
    if key == "outer_skin_ss" or key.endswith(":ss"):
        return key.replace("outer_skin_ss", "skin_suction_surface").replace(":ss", "")
    if key == "outer_skin_ps" or key.endswith(":ps"):
        return key.replace("outer_skin_ps", "skin_pressure_surface").replace(":ps", "")
    if key.startswith("outer_skin_"):
        # Hierarchical legacy outer_skin:SS:... → leave skin_* form when already long
        return key
    aliases = {
        "le_insert": "leading_edge_insert",
        "te_insert": "trailing_edge_insert",
        "outer_skin_ss": "skin_suction_surface",
        "outer_skin_ps": "skin_pressure_surface",
    }
    return aliases.get(key, key)


def is_core_label(label: Any) -> bool:
    """True for sandwich-core bay labels (constructive polygon path)."""
    key = _canonical_label_key(label)
    return key.startswith("sandwich_core_") or key in {"sandwich_core"}


def is_residual_label(label: Any) -> bool:
    """True for LE/TE inserts (residual φ path). Cores are constructive."""
    key = _canonical_label_key(label)
    return key in {
        "leading_edge_insert",
        "trailing_edge_insert",
    }


def is_skin_label(label: Any) -> bool:
    """True for outer-skin laminate labels (full or suction/pressure)."""
    key = _canonical_label_key(label)
    raw = _label_key(label)
    return (
        key == "outer_skin"
        or raw == "outer_skin"
        or key.startswith("skin_suction_surface")
        or key.startswith("skin_pressure_surface")
        or raw.startswith("outer_skin_")
    )


def is_laminate_label(label: Any) -> bool:
    """True for skin / web / spar-cap laminates (constructive polygon path)."""
    key = _canonical_label_key(label)
    if is_residual_label(key) or is_core_label(key):
        return False
    if is_skin_label(label):
        return True
    if key.startswith("shear_web_"):
        return True
    if key.startswith("spar_cap"):
        return True
    return False


def is_constructive_label(label: Any) -> bool:
    """True for any label integrated via constructive polygons (laminates + cores)."""
    return is_laminate_label(label) or is_core_label(label)


def classify_property_labels(labels: Iterable[Any]) -> tuple[list[str], list[str]]:
    """Split section labels into (constructive_labels, residual_labels).

    ``constructive_labels`` includes laminates and sandwich cores.
    ``residual_labels`` is LE/TE inserts (and any unknown labels).
    """
    constructive: list[str] = []
    residual: list[str] = []
    for raw in labels:
        key = _label_key(raw)
        if is_constructive_label(key):
            constructive.append(key)
        elif is_residual_label(key):
            residual.append(key)
        else:
            residual.append(key)
    return constructive, residual
