"""Shared figure I/O for section_geometry visualisation demos.

All demos should write under ``visualisation/output/<demo_stem>/`` via
:func:`demo_output_dir` and :func:`save_figure`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib as mpl

DEFAULT_DPI = 200
PRESENTATION_DPI = 220

_VISUALISATION_ROOT = Path(__file__).resolve().parent


def demo_output_dir(
    demo_stem: str,
    *,
    repo_visualisation_root: Path | None = None,
) -> Path:
    """Return ``<visualisation>/output/<demo_stem>/`` (created on save, not here)."""
    root = Path(repo_visualisation_root) if repo_visualisation_root is not None else _VISUALISATION_ROOT
    return (root / "output" / str(demo_stem)).resolve()


def apply_presentation_style(presentation: bool) -> None:
    """Bump tick/legend/title fonts when ``presentation`` is true."""
    if not presentation:
        return
    mpl.rcParams.update(
        {
            "font.size": 12,
            "axes.titlesize": 14,
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 10,
            "figure.titlesize": 16,
        }
    )


def save_figure(
    fig: Any,
    path: Path | str,
    *,
    dpi: int | None = None,
    presentation: bool = False,
    **savefig_kwargs: Any,
) -> Path:
    """Save ``fig`` with white face and tight bbox; create parent dirs."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if dpi is None:
        dpi = PRESENTATION_DPI if presentation else DEFAULT_DPI
    kwargs = {
        "dpi": int(dpi),
        "facecolor": "white",
        "bbox_inches": "tight",
    }
    kwargs.update(savefig_kwargs)
    fig.savefig(out, **kwargs)
    return out


def add_output_and_presentation_args(
    parser: argparse.ArgumentParser,
    *,
    default_stem: str,
) -> None:
    """Add ``--out-dir`` and ``--presentation`` with visualisation/output defaults."""
    default_out = demo_output_dir(default_stem)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=default_out,
        help=f"Output directory (default: visualisation/output/{default_stem}/).",
    )
    parser.add_argument(
        "--presentation",
        action="store_true",
        help="Larger fonts and higher DPI for slides/decks.",
    )


def resolve_save_dpi(*, presentation: bool, dpi: int | None = None) -> int:
    """Pick DPI from explicit override, presentation flag, or default."""
    if dpi is not None:
        return int(dpi)
    return PRESENTATION_DPI if presentation else DEFAULT_DPI


__all__ = [
    "DEFAULT_DPI",
    "PRESENTATION_DPI",
    "add_output_and_presentation_args",
    "apply_presentation_style",
    "demo_output_dir",
    "resolve_save_dpi",
    "save_figure",
]
