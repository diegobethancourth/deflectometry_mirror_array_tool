"""Synthetic bench: render what the camera would see, from known tilts.

This exists so the algorithm can be tested against ground truth.  You command a
tilt, the model ray-traces the image the camera would record, the pipeline reads
that image back, and the recovered angle is compared against what you commanded.
Without this loop there is no way to tell a working retrieval from a plausible
looking one.

Model and its limits
--------------------
* Mirror array in the plane ``z = 0``, nominal normals along ``+z``.
* Screen plane parallel at ``z = z_d``, showing the pattern.
* **Orthographic camera** looking along ``-z``.  A real camera is perspective,
  but the retrieval works in *fractions of a period*, which is invariant under
  magnification -- so an orthographic model exercises exactly the arithmetic that
  matters and keeps pixel<->mirror mapping exact.  What it does NOT exercise:
  perspective foreshortening across a segment, lens distortion, and defocus.
  Those belong in a Zemax model, as the paper notes they did.
* Flat mirrors, single reflection, no stray light or inter-reflection.

Every ray is traced with the real law of reflection -- ``r = u - 2 (u . n) n`` --
so the 2x angular lever and the off-axis behaviour are genuine, not assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .hardware import Bench
from .patterns import PatternSpec, sample


@dataclass(frozen=True)
class SyntheticFrame:
    """One rendered camera image plus the ground truth that produced it."""

    image: np.ndarray                      # (h, w) grey levels
    tilts_x: dict[str, float]              # node -> tilt that moves the pattern in x (rad)
    tilts_y: dict[str, float]              # node -> tilt that moves the pattern in y (rad)
    bounds: tuple[int, int, int, int]      # (y0, y1, x0, x1) of the array
    px_per_mm: float


def _normal(theta_x: float, theta_y: float) -> np.ndarray:
    """Surface normal for a mirror with tilt components ``theta_x``, ``theta_y``.

    ``theta_x`` rotates the normal toward +x, and so drives the pattern shift
    along the screen's x axis; ``theta_y`` does the same for y.  Naming the tilt
    after the screen axis it moves keeps the whole pipeline in one convention --
    ``theta_x`` in, shift along x out, ``theta_x`` back.
    """
    sx, sy = np.sin(theta_x), np.sin(theta_y)
    n = np.array([sx, sy, np.sqrt(max(0.0, 1.0 - sx ** 2 - sy ** 2))])
    return n / np.linalg.norm(n)


def render_frame(bench: Bench, spec: PatternSpec,
                 tilts_x: dict[str, float] | None = None,
                 tilts_y: dict[str, float] | None = None,
                 px_per_mm: float = 6.0,
                 margin_mm: float = 4.0,
                 noise_dn: float | None = None,
                 rng: np.random.Generator | None = None) -> SyntheticFrame:
    """Ray-trace the camera image for a given set of per-node tilts.

    Tilts are in radians, keyed by node name (``"M5"``).  Missing nodes are flat.
    """
    tilts_x = dict(tilts_x or {})
    tilts_y = dict(tilts_y or {})
    arr, screen = bench.array, bench.screen
    z_d = bench.screen_distance_mm
    rng = rng or np.random.default_rng(0)

    span_x = arr.width_mm + 2 * margin_mm
    span_y = arr.height_mm + 2 * margin_mm
    w = int(round(span_x * px_per_mm))
    h = int(round(span_y * px_per_mm))

    # World coordinates of every camera pixel, origin at the array centre.
    xs = (np.arange(w) + 0.5) / px_per_mm - span_x / 2.0
    ys = span_y / 2.0 - (np.arange(h) + 0.5) / px_per_mm
    X, Y = np.meshgrid(xs, ys)

    img = np.zeros((h, w), dtype=np.float64)      # gaps stay dark
    half = arr.side_mm / 2.0

    for r in range(arr.rows):
        for c in range(arr.cols):
            name = arr.name(r, c)
            cx, cy = arr.centre_mm(r, c)
            on = (np.abs(X - cx) <= half) & (np.abs(Y - cy) <= half)
            if not on.any():
                continue

            n = _normal(tilts_x.get(name, 0.0), tilts_y.get(name, 0.0))
            # Orthographic view direction, camera -> mirror.
            u = np.array([0.0, 0.0, -1.0])
            refl = u - 2.0 * np.dot(u, n) * n           # law of reflection
            if refl[2] <= 1e-9:
                continue                                 # reflected away from the screen

            t = z_d / refl[2]
            sx = X[on] + t * refl[0]
            sy = Y[on] + t * refl[1]

            # Screen millimetres -> screen pixels, origin at the screen centre.
            sx_px = sx / screen.pitch_mm + screen.pixels_x / 2.0
            sy_px = sy / screen.pitch_mm + screen.pixels_y / 2.0
            img[on] = sample(spec, sx_px, sy_px)

    noise = bench.camera.noise_dn if noise_dn is None else noise_dn
    if noise:
        img = img + rng.normal(0.0, noise, img.shape)
    img = np.clip(img, 0.0, 255.0)
    if bench.camera.bits:
        img = np.round(img)

    m = margin_mm * px_per_mm
    bounds = (int(round(m)), int(round(h - m)), int(round(m)), int(round(w - m)))
    return SyntheticFrame(image=img, tilts_x=tilts_x, tilts_y=tilts_y,
                          bounds=bounds, px_per_mm=px_per_mm)


def reference_frame(bench: Bench, spec: PatternSpec, **kw) -> SyntheticFrame:
    """The all-flat reference capture that every measurement is compared against."""
    return render_frame(bench, spec, None, None, **kw)


__all__ = ["SyntheticFrame", "render_frame", "reference_frame"]
