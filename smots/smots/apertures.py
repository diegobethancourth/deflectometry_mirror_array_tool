"""Binary digital apertures -- one per mirror segment.

The paper applies "a binary digital mask ... on each mirror segment during the
image processing such that only the pattern in each masked area was used to
calculate the corresponding mirror orientation change".  That is what makes the
measurement simultaneous: every segment is an independent little interferogram
inside one camera frame, and they are all solved from the same pair of images.

Apertures here are axis-aligned boxes, which is exact for a square array.  Inset
them away from the mirror edge: the bevel, the mount and the gap all contribute
signal that belongs to no segment and only adds spectral junk.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .hardware import MirrorArray


@dataclass(frozen=True)
class Aperture:
    """One segment's region of interest in the camera image."""

    name: str
    row: int
    col: int
    y0: int
    y1: int
    x0: int
    x1: int

    @property
    def shape(self) -> tuple[int, int]:
        return (self.y1 - self.y0, self.x1 - self.x0)

    @property
    def area(self) -> int:
        h, w = self.shape
        return h * w

    def extract(self, image: np.ndarray) -> np.ndarray:
        """The sub-image this aperture selects."""
        return np.asarray(image)[self.y0:self.y1, self.x0:self.x1]

    def mask(self, shape: tuple[int, int]) -> np.ndarray:
        """Boolean mask of this aperture over a full frame of ``shape``."""
        m = np.zeros(shape, dtype=bool)
        m[self.y0:self.y1, self.x0:self.x1] = True
        return m


def grid_apertures(image_shape: tuple[int, int], array: MirrorArray,
                   inset_frac: float = 0.18,
                   bounds: tuple[int, int, int, int] | None = None) -> list[Aperture]:
    """Lay one aperture over each segment of a regular array.

    ``bounds`` is ``(y0, y1, x0, x1)`` of the region the array occupies in the
    image; it defaults to the whole frame.  ``inset_frac`` shrinks each aperture
    toward its centre by that fraction of a cell, keeping mirror edges out.

    For real camera frames, locate the array first (corner detection, a fiducial,
    or a one-off manual click) and pass the result as ``bounds`` -- a misplaced
    aperture quietly mixes two segments' signals.
    """
    h, w = image_shape
    y0b, y1b, x0b, x1b = bounds if bounds is not None else (0, h, 0, w)
    if not (0 <= y0b < y1b <= h and 0 <= x0b < x1b <= w):
        raise ValueError(f"bounds {bounds} fall outside a {image_shape} image")
    if not 0.0 <= inset_frac < 0.5:
        raise ValueError("inset_frac must be in [0, 0.5)")

    cell_h = (y1b - y0b) / array.rows
    cell_w = (x1b - x0b) / array.cols
    pad_y = cell_h * inset_frac
    pad_x = cell_w * inset_frac

    out: list[Aperture] = []
    for r in range(array.rows):
        for c in range(array.cols):
            y0 = int(round(y0b + r * cell_h + pad_y))
            y1 = int(round(y0b + (r + 1) * cell_h - pad_y))
            x0 = int(round(x0b + c * cell_w + pad_x))
            x1 = int(round(x1b - (array.cols - c - 1) * cell_w - pad_x)) \
                if c == array.cols - 1 else int(round(x0b + (c + 1) * cell_w - pad_x))
            if y1 - y0 < 8 or x1 - x0 < 8:
                raise ValueError(
                    f"aperture {array.name(r, c)} is only {y1-y0}x{x1-x0} px; "
                    "too small to hold a usable carrier -- use a bigger frame "
                    "or a smaller inset"
                )
            out.append(Aperture(array.name(r, c), r, c, y0, y1, x0, x1))
    return out


def sampling_report(apertures: list[Aperture], carrier_period_px: float) -> dict:
    """How many carrier periods each aperture contains.

    The paper's condition for a valid segment is that "each digital aperture has
    a sufficient sampling of the sinusoidal pattern".  Fewer than ~3 periods
    across an aperture and the Fourier peak is too broad to locate reliably.
    """
    if carrier_period_px <= 0:
        raise ValueError("carrier period must be positive")
    per = {a.name: min(a.shape) / carrier_period_px for a in apertures}
    worst = min(per.values()) if per else 0.0
    return {
        "periods_per_aperture": per,
        "worst": worst,
        "ok": worst >= 3.0,
        "advice": ("fine" if worst >= 3.0 else
                   "increase the carrier frequency, enlarge the apertures, or "
                   "move the camera closer -- under ~3 periods the FFT peak is "
                   "too broad to locate"),
    }


__all__ = ["Aperture", "grid_apertures", "sampling_report"]
