"""Sinusoidal patterns displayed on the screen.

SMOTS does not use temporal phase shifting.  It displays ONE pattern, captures a
reference image, and then compares every later image against that reference.
The tilt comes out of the shift between the two, recovered in the Fourier domain
(see :mod:`smots.analysis`).

Two flavours are provided:

``sinusoid``
    A single carrier per axis.  Simple, highest sensitivity for its period, but
    the recovered shift wraps once it exceeds one period.

``multiplexed``
    Two carriers per axis with co-prime periods.  Section 3.2 of the paper uses
    this to break the 2*pi ambiguity: each carrier wraps at a different shift, so
    the pair agrees only at the true shift, out to their least common multiple.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PatternSpec:
    """Definition of a displayed pattern.

    Periods are in SCREEN PIXELS.  Convert to mm with the screen pitch when you
    need a physical frequency -- :meth:`frequencies_per_mm`.
    """

    periods_px: tuple[float, ...] = (30.0,)
    bias: float = 128.0
    amplitude: float = 100.0
    axes: str = "xy"          # "x", "y" or "xy"
    gamma: float | None = None

    def __post_init__(self) -> None:
        if not self.periods_px:
            raise ValueError("at least one period is required")
        if any(p < 4 for p in self.periods_px):
            raise ValueError("periods below ~4 px cannot render as a sinusoid")
        if self.axes not in ("x", "y", "xy"):
            raise ValueError("axes must be 'x', 'y' or 'xy'")
        lo = self.bias - self.amplitude
        hi = self.bias + self.amplitude
        if lo < 0 or hi > 255:
            raise ValueError(
                f"bias +/- amplitude = {lo:.0f}..{hi:.0f} clips the 0-255 range; "
                "a clipped sinusoid biases the retrieved phase"
            )

    def frequencies_per_mm(self, pitch_mm: float) -> tuple[float, ...]:
        """Carrier spatial frequencies f, in cycles/mm on the screen."""
        return tuple(1.0 / (p * pitch_mm) for p in self.periods_px)

    def periods_mm(self, pitch_mm: float) -> tuple[float, ...]:
        return tuple(p * pitch_mm for p in self.periods_px)


def render(spec: PatternSpec, width: int, height: int,
           phase: float = 0.0) -> np.ndarray:
    """Render ``spec`` to a (height, width) float array in grey levels.

    ``phase`` shifts the pattern in radians of the FIRST carrier, which is only
    used for building test imagery -- the measurement itself never shifts the
    displayed pattern.
    """
    x = np.arange(width, dtype=np.float64)
    y = np.arange(height, dtype=np.float64)

    n_carriers = len(spec.periods_px) * len(spec.axes)
    per_carrier = spec.amplitude / n_carriers

    img = np.full((height, width), spec.bias, dtype=np.float64)
    for period in spec.periods_px:
        if "x" in spec.axes:
            img += per_carrier * np.cos(2 * np.pi * x[None, :] / period + phase)
        if "y" in spec.axes:
            img += per_carrier * np.cos(2 * np.pi * y[:, None] / period + phase)

    if spec.gamma:
        img = 255.0 * np.clip(img / 255.0, 0.0, 1.0) ** (1.0 / spec.gamma)
    return np.clip(img, 0.0, 255.0)


def sample(spec: PatternSpec, xs_px: np.ndarray, ys_px: np.ndarray) -> np.ndarray:
    """Sample the pattern at arbitrary (possibly non-integer) screen pixels.

    Used by the forward model, where a reflected ray lands wherever it lands.
    The pattern is analytic, so this is exact -- no interpolation error.
    """
    n_carriers = len(spec.periods_px) * len(spec.axes)
    per_carrier = spec.amplitude / n_carriers

    out = np.full(np.broadcast(xs_px, ys_px).shape, spec.bias, dtype=np.float64)
    for period in spec.periods_px:
        if "x" in spec.axes:
            out = out + per_carrier * np.cos(2 * np.pi * xs_px / period)
        if "y" in spec.axes:
            out = out + per_carrier * np.cos(2 * np.pi * ys_px / period)

    if spec.gamma:
        out = 255.0 * np.clip(out / 255.0, 0.0, 1.0) ** (1.0 / spec.gamma)
    return np.clip(out, 0.0, 255.0)


def coprime_periods(base_px: float = 30.0, ratio: float = 1.6667) -> tuple[float, float]:
    """A pair of periods for a multiplexed pattern.

    Two competing pressures set ``ratio``:

    * The unambiguous range is the *synthetic period* ``T1 T2 / |T1 - T2|``,
      which grows without bound as the two periods approach each other.  Periods
      sharing small factors are wasted -- (30, 60) wraps together and buys
      nothing over (30,) alone.
    * But the two carriers have to be *separable in the FFT*.  A carrier's bin
      index is ``aperture_mm / period_mm``, so nearly equal periods land in
      nearly the same bin and cannot be told apart at all.

    The default trades some synthetic range for peaks that reliably separate in
    a segment-sized aperture.  Push ``ratio`` toward 1 only if your apertures are
    large enough in periods to keep the peaks apart -- check with
    :func:`smots.analysis.synthetic_period` and ``apertures.sampling_report``.
    """
    return (base_px, round(base_px * ratio, 3))
