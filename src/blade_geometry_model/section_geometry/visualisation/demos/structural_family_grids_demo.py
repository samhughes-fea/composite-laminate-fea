"""
visualisation/demos/structural_family_grids_demo.py
=======================================
One PNG per structural system (registry ``SYSTEM_TYPE_KEYS``).

Each figure is a single hybrid constructive fill of that SystemType at a fixed
twist, drawn in a **wide rectangular** frame matching the twin-web /
torsion-box section demos (not a square data window). Skin-only ``0A`` /
``0B`` have no flapwise twin.

Writes under ``visualisation/output/structural_family_grids/``:

* ``{key}.png`` — one file per registry key (e.g. ``2D-F.png``, ``3D-CN.png``)
* ``structural_family_grids.json`` — key inventory + output map

Run from the repository root::

    python blade_structure_utilities/geometry_utilities/section_geometry/visualisation/demos/structural_family_grids_demo.py
    python .../structural_family_grids_demo.py --twist-deg 15 --families A D
    python .../structural_family_grids_demo.py --keys 2D-F 3D-CN
    python .../structural_family_grids_demo.py --wall
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

_EXAMPLES_DIR = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    path = _EXAMPLES_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_ensure_mod = _load_sibling("_ensure_repo_path", "_ensure_repo_path.py")
_ensure_mod.ensure_repo_path()

from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.figure_io import (
    DEFAULT_DPI,
    add_output_and_presentation_args,
    apply_presentation_style,
    demo_output_dir,
    save_figure,
)
_taxonomy = _load_sibling("_taxonomy_cases", "_taxonomy_cases.py")

from blade_structure_utilities.geometry_utilities.section_geometry.api.factory import (
    SYSTEM_TYPE_KEYS,
    build_section_view,
    resolve_system_type,
)
from blade_structure_utilities.geometry_utilities.section_geometry.visualisation.plot import (
    plot_section_hybrid,
)
from blade_structure_utilities.geometry_utilities.section_geometry.sdf.airfoil import AirfoilSDF

_DPI = DEFAULT_DPI
_FAMILIES = ("A", "B", "C", "D")
# Match ``plot_section`` / naca2412 twin-web & torsion-box figure shape.
_FIGSIZE = (12.0, 5.0)


def _keys_by_family() -> dict[str, list[str]]:
    by: dict[str, list[str]] = defaultdict(list)
    for key in SYSTEM_TYPE_KEYS:
        fam = str(resolve_system_type(key).structural_family).upper()
        by[fam].append(key)
    for fam in by:
        by[fam] = sorted(
            by[fam],
            key=lambda k: (
                resolve_system_type(k).n_webs,
                0 if resolve_system_type(k).web_orientation == "chord_normal" else 1,
                k,
            ),
        )
    return dict(by)


def _z_tag(key: str) -> str:
    lay = resolve_system_type(key)
    n = int(lay.n_webs)
    if n == 0:
        return "CN"
    return "CN" if lay.web_orientation == "chord_normal" else "F"


def _png_name(key: str) -> str:
    """Filesystem-safe name for a SystemType key (keys are already safe)."""
    return f"{key}.png"


def _render_system(
    key: str,
    *,
    airfoil: AirfoilSDF,
    twist_deg: float,
    out_dir: Path,
    presentation: bool = False,
) -> dict[str, Any]:
    layout = resolve_system_type(key)
    twist_use = _taxonomy.twist_deg_for_layout(layout, twist_deg=twist_deg)
    twist_rad = float(np.deg2rad(twist_use))
    section = build_section_view(airfoil, layout, twist_angle_rad=twist_rad)
    n_webs = int(layout.n_webs)
    z = _z_tag(key)
    fam = str(layout.structural_family).upper()

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    plot_section_hybrid(
        section,
        residual_mesh=None,
        ax=ax,
        alpha=0.5,
        title=f"{key}\n(n_webs={n_webs}, {z}, twist={twist_use:g}°)",
        show_legend=False,
    )
    # Keep equal scale without expanding to a square data window (twin-web style).
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()

    out_png = out_dir / _png_name(key)
    save_figure(fig, out_png, presentation=presentation)
    plt.close(fig)
    print(f"Wrote {out_png}")
    return {
        "key": key,
        "family": fam,
        "n_webs": n_webs,
        "z": z,
        "n_labels": len(list(section)),
        "twist_deg": float(twist_use),
        "png": out_png.name,
    }



def _compose_contact_sheet(
    systems: list[dict[str, Any]],
    *,
    out_dir: Path,
    presentation: bool = False,
    columns: int = 8,
) -> Path:
    """Tile per-key PNGs into one labelled contact sheet."""
    from PIL import Image, ImageDraw, ImageFont

    if not systems:
        raise SystemExit("No systems to compose into a wall.")

    images: list[tuple[str, Image.Image]] = []
    for row in systems:
        png_path = out_dir / str(row["png"])
        if not png_path.is_file():
            raise SystemExit(f"Missing tile for wall: {png_path}")
        images.append((str(row["key"]), Image.open(png_path).convert("RGB")))

    tile_width, tile_height = images[0][1].size
    label_band = 36
    columns = max(1, int(columns))
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (columns * tile_width, rows * (tile_height + label_band)),
        color=(255, 255, 255),
    )
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()

    for index, (key, image) in enumerate(images):
        row_index = index // columns
        col_index = index % columns
        x0 = col_index * tile_width
        y0 = row_index * (tile_height + label_band)
        sheet.paste(image, (x0, y0))
        draw.rectangle(
            (x0, y0 + tile_height, x0 + tile_width, y0 + tile_height + label_band),
            fill=(245, 247, 250),
        )
        draw.text(
            (x0 + 10, y0 + tile_height + 8),
            key,
            fill=(20, 30, 40),
            font=font,
        )

    out_path = out_dir / "structural_family_wall.png"
    sheet.save(out_path, dpi=(220 if presentation else 200, 220 if presentation else 200))
    print(f"Wrote {out_path}")
    return out_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_output_and_presentation_args(p, default_stem="structural_family_grids")
    p.add_argument("--twist-deg", type=float, default=15.0)
    p.add_argument("--naca", default="2412")
    p.add_argument("--chord", type=float, default=1.0)
    p.add_argument(
        "--families",
        nargs="*",
        default=None,
        help="Subset of A B C D (default: all, unless --keys is set).",
    )
    p.add_argument(
        "--keys",
        nargs="*",
        default=None,
        help="Explicit SystemType keys (overrides --families when set).",
    )
    p.add_argument(
        "--wall",
        action="store_true",
        help="Also compose all rendered keys into structural_family_wall.png.",
    )
    p.add_argument(
        "--wall-columns",
        type=int,
        default=8,
        help="Column count for --wall contact sheet.",
    )
    args = p.parse_args(argv)
    apply_presentation_style(bool(args.presentation))

    out_dir: Path = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    af = AirfoilSDF.from_naca(args.naca, n_points=140, chord=float(args.chord))
    by_fam = _keys_by_family()

    if args.keys:
        keys = [str(k) for k in args.keys]
        unknown = [k for k in keys if k not in SYSTEM_TYPE_KEYS]
        if unknown:
            raise SystemExit(f"Unknown keys {unknown}; have {list(SYSTEM_TYPE_KEYS)}")
    else:
        families = list(args.families) if args.families else list(_FAMILIES)
        keys = []
        for fam in families:
            fam_u = str(fam).upper()
            if fam_u not in by_fam:
                raise SystemExit(f"Unknown family {fam!r}; have {sorted(by_fam)}")
            keys.extend(by_fam[fam_u])

    # Drop stale family-grid composites from older demo versions.
    for stale in out_dir.glob("family_*_grid.png"):
        stale.unlink(missing_ok=True)
        print(f"Removed stale {stale.name}")

    systems: list[dict[str, Any]] = []
    for key in keys:
        systems.append(
            _render_system(
                key,
                airfoil=af,
                twist_deg=float(args.twist_deg),
                out_dir=out_dir,
                presentation=bool(args.presentation),
            )
        )

    by_family_summary: dict[str, list[str]] = defaultdict(list)
    for row in systems:
        by_family_summary[str(row["family"])].append(str(row["key"]))

    payload = {
        "naca": args.naca,
        "chord_m": float(args.chord),
        "twist_deg": float(args.twist_deg),
        "n_systems": len(systems),
        "keys": [row["key"] for row in systems],
        "by_family": {fam: by_family_summary[fam] for fam in sorted(by_family_summary)},
        "systems": systems,
        "notes": (
            "One PNG per SystemType registry key in a wide rectangular frame "
            "(same style as twin_web_section / torsion_box_section). "
            "Taxonomy Y = structural family (A/B/C/D); Z = CN|F. "
            "Skin-only 0A/0B have no flapwise twin."
        ),
    }

    if bool(args.wall):
        wall_path = _compose_contact_sheet(
            systems,
            out_dir=out_dir,
            presentation=bool(args.presentation),
            columns=int(args.wall_columns),
        )
        payload["wall_png"] = wall_path.name
    json_path = out_dir / "structural_family_grids.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {json_path} ({len(systems)} systems)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
