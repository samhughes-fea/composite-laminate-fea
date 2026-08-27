"""SDF field visualisation helpers."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt


def plot_sdf_field(
    phi,
    grid,
    ax=None,
    title="SDF field",
    colorbar=True,
    contour_zero=True,
    cmap="RdBu_r",
    vmax=None,
    *,
    twist_rad: float = 0.0,
    chord_m: float | None = None,
    structural_axes: bool = True,
    airfoil=None,
    sdf_callable=None,
    nx: int | None = None,
    ny: int | None = None,
):
    """Plot a raw SDF field as a filled contour / imshow.

    Parameters
    ----------
    phi : ndarray, shape (ny, nx)
        Precomputed field on ``grid``. Ignored when ``|twist_rad|`` is nonzero
        and ``sdf_callable`` + ``airfoil`` are provided (B-frame resample).
    grid : SDFGrid
    ax : matplotlib Axes or None
    title : str
    colorbar : bool
    contour_zero : bool
        Overlay the zero-level-set as a solid black line.
    cmap : str
    vmax : float or None
        Colour scale symmetric about zero; defaults to max(|phi|).
    twist_rad, chord_m
        NACA→B remap for structural axes (pitch pivot at origin). ``chord_m``
        defaults to the grid x-span when omitted.
    structural_axes : bool
        If True (default), show canonical ``(Y_B, X_B)`` axes.
    airfoil, sdf_callable
        Required together for nonzero twist under ``structural_axes``: sample a
        rectilinear B mesh and evaluate ``sdf_callable(QX, QY)``. Remapping a
        chord-aligned NACA ``phi`` through twist warps the lattice and clips.
    nx, ny
        Optional B-grid resolution (defaults from ``grid.X.shape``).

    Returns
    -------
    fig, ax
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 4))
    else:
        fig = ax.figure

    from .plot_section import (
        apply_structural_section_axes,
        blade_plot_sampling_grid,
        rotated_naca_grid_to_section_plot_axes,
    )

    twist = float(twist_rad)
    phi_plot = np.asarray(phi, dtype=float)

    if structural_axes:
        c = float(chord_m) if chord_m is not None else float(
            np.nanmax(grid.X) - np.nanmin(grid.X)
        )
        if not np.isfinite(c) or c <= 0.0:
            raise ValueError("plot_sdf_field requires a positive chord_m")
        if abs(twist) >= 1e-12:
            if airfoil is None or sdf_callable is None:
                raise ValueError(
                    "plot_sdf_field with nonzero twist and structural_axes "
                    "requires airfoil= and sdf_callable= (B-frame resampling)"
                )
            ny_g, nx_g = int(np.asarray(grid.X).shape[0]), int(np.asarray(grid.X).shape[1])
            X_plot, Y_plot, QX, QY = blade_plot_sampling_grid(
                airfoil,
                twist_rad=twist,
                chord_m=c,
                nx=int(nx) if nx is not None else max(nx_g, 2),
                ny=int(ny) if ny is not None else max(ny_g, 2),
            )
            phi_plot = np.asarray(sdf_callable(QX, QY), dtype=float)
        else:
            X_plot, Y_plot = rotated_naca_grid_to_section_plot_axes(
                grid.X, grid.Y, twist_rad=0.0, chord_m=c
            )
    else:
        X_plot, Y_plot = grid.X, grid.Y

    if vmax is None:
        vmax = float(np.abs(phi_plot).max()) if phi_plot.size else 1.0

    im = ax.pcolormesh(
        X_plot,
        Y_plot,
        phi_plot,
        cmap=cmap,
        vmin=-vmax,
        vmax=vmax,
        shading="auto",
    )
    if colorbar:
        fig.colorbar(im, ax=ax, label="φ (m)")

    if contour_zero:
        ax.contour(X_plot, Y_plot, phi_plot, levels=[0.0], colors="k", linewidths=1.5)

    ax.set_title(title)
    if structural_axes:
        apply_structural_section_axes(ax)
    else:
        ax.set_aspect("equal")
        ax.set_xlabel("x_chord [m]")
        ax.set_ylabel("y_thickness [m]")
    return fig, ax


__all__ = ["plot_sdf_field"]
