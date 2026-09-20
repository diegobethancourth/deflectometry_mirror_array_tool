"""Sheared Fourier analysis -- Eqs. (1)-(4) of Choi et al., SPIE 10377, 103770G.

The measurement in one sentence: subtract the reference image from the measured
image, and the amplitude of what is left tells you how far the pattern moved.

    Eq. (1)  FT[f(x)]                = F(f)
    Eq. (2)  FT[f(x + D)]            = exp(-i 2 pi f D) F(f)
    Eq. (3)  FT[f(x + D) - f(x)]     = (exp(-i 2 pi f D) - 1) F(f)
    Eq. (4)  D = 1/(2 pi f) * arccos( 1 - 1/2 * |S(f)|^2 / |F(f)|^2 )

Two things are worth knowing before using this module.

**The phase is measured in camera pixels but converted with screen units.**
What the camera sees is the pattern at some unknown magnification.  A *fraction
of a period* is invariant under that magnification, so we find the carrier in
the camera's own spectrum, recover the phase as a fraction of a period, and only
then multiply by the physical period on the screen (Eq. (5)).  Nothing in the
chain needs the magnification, which is why the method is robust.

**Eq. (4) throws away half the information, and we do not have to.**
It uses only the magnitude ratio, so it returns an unsigned angle in [0, pi];
the paper then recovers the sign separately from the imaginary part.  But the
complex ratio S/F already contains both:

    S/F = exp(i psi) - 1  =>  Re(S/F) = cos(psi) - 1,  Im(S/F) = sin(psi)
    =>  psi = atan2( Im(S/F), 1 + Re(S/F) )

**Sign convention -- read this before comparing against the paper.**
Eq. (2) is written ``FT[f(x + D)] = exp(-i 2 pi f D) F(f)``, but the standard
forward transform (and ``numpy.fft``) gives ``exp(+i 2 pi f D) F(f)`` for that
same shift.  The paper's exponent sign therefore corresponds to the opposite
shift direction.  Eq. (4) is unaffected -- it only uses the magnitude, and
|exp(+i psi) - 1| = |exp(-i psi) - 1| -- but the *sign* of the recovered shift
flips, which silently inverts every tilt angle you report.

This module fixes the convention to the physically readable one: a POSITIVE
returned phase means the pattern appears displaced toward +x (or +y), so that
``D = psi / (2 pi) * period`` is a displacement in +x and drops straight into
Eq. (5) as ``x_f = x_i + D``.

which is signed, spans the full (-pi, pi], and stays conditioned where Eq. (4)
does not -- arccos has infinite derivative at phi = 0 and phi = pi, exactly where
small shifts and near-wrap shifts live.  Both are implemented;
:func:`phase_paper_eq4` reproduces the paper, :func:`phase_complex` is what you
should actually run.  The test suite checks they agree away from those corners.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TWO_PI = 2.0 * np.pi


# --------------------------------------------------------------------------
# Phase from the complex ratio
# --------------------------------------------------------------------------

def phase_complex(ratio: complex | np.ndarray) -> np.ndarray:
    """Signed phase shift in radians, from the complex ratio S(f)/F(f).

    Returns a value in (-pi, pi].  This is the recommended estimator.
    """
    ratio = np.asarray(ratio, dtype=np.complex128)
    return np.arctan2(ratio.imag, 1.0 + ratio.real)


def phase_paper_eq4(ratio: complex | np.ndarray,
                    use_sign: bool = True) -> np.ndarray:
    """Phase shift via the paper's Eq. (4): arccos of the magnitude ratio.

    ``use_sign`` applies the paper's sign recovery -- the sign of the imaginary
    part of the ratio, per Section 2.1 -- in this module's sign convention (see
    the module docstring).  With ``use_sign=False`` you get the raw unsigned
    [0, pi] result, which is what Eq. (4) alone gives you.
    """
    ratio = np.asarray(ratio, dtype=np.complex128)
    mag_sq = np.abs(ratio) ** 2
    cos_phi = np.clip(1.0 - 0.5 * mag_sq, -1.0, 1.0)
    phi = np.arccos(cos_phi)
    if use_sign:
        # Im(S/F) = sin(psi), so the imaginary part carries the sign directly.
        phi = np.where(ratio.imag < 0, -phi, phi)
    return phi


# --------------------------------------------------------------------------
# Finding the carrier in the camera's own spectrum
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Carrier:
    """One carrier located in a camera-frame spectrum."""

    axis: str                  # "x" or "y"
    bin_index: int             # FFT bin along that axis
    cycles_per_px: float       # apparent frequency in the camera image
    period_px: float           # apparent period in camera pixels
    power: float               # |F| at that bin, for ranking / diagnostics


def _hann2d(shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    wy = np.hanning(h + 2)[1:-1] if h > 2 else np.ones(h)
    wx = np.hanning(w + 2)[1:-1] if w > 2 else np.ones(w)
    return np.outer(wy, wx)


def find_carriers(ref: np.ndarray, axis: str, n_carriers: int = 1,
                  window: bool = True, min_bin: int = 2,
                  suppress_bins: int = 1) -> list[Carrier]:
    """Locate the strongest ``n_carriers`` along ``axis`` in a reference image.

    The carrier is found from the data, not assumed, so the unknown camera
    magnification never enters the calculation.

    ``min_bin`` skips the DC neighbourhood, where the aperture's own envelope
    puts a large peak that is not a carrier.  ``suppress_bins`` is how much of
    each found peak's skirt is blanked before hunting the next one -- keep it
    small, or a second carrier only a couple of bins away gets erased along with
    the first.  The bin index of a carrier is just ``aperture_mm / period_mm``,
    so two carriers separate in the spectrum only when the aperture holds
    appreciably different numbers of their periods.
    """
    if axis not in ("x", "y"):
        raise ValueError("axis must be 'x' or 'y'")
    img = np.asarray(ref, dtype=np.float64)
    img = img - img.mean()
    if window:
        img = img * _hann2d(img.shape)

    spec = np.fft.fft2(img)
    h, w = img.shape

    # A carrier that varies along x has no y-dependence, so its energy sits on
    # the ky = 0 row of the 2-D spectrum (and vice versa).
    if axis == "x":
        line = np.abs(spec[0, : w // 2])
        n = w
    else:
        line = np.abs(spec[: h // 2, 0])
        n = h

    if line.size <= min_bin:
        return []
    searchable = line.copy()
    searchable[:min_bin] = 0.0

    out: list[Carrier] = []
    for _ in range(n_carriers):
        k = int(np.argmax(searchable))
        if searchable[k] <= 0:
            break
        out.append(Carrier(axis=axis, bin_index=k, cycles_per_px=k / n,
                           period_px=(n / k) if k else np.inf,
                           power=float(line[k])))
        # suppress this peak's immediate skirt before hunting the next one
        lo = max(0, k - suppress_bins)
        hi = min(searchable.size, k + suppress_bins + 1)
        searchable[lo:hi] = 0.0

    return sorted(out, key=lambda c: c.cycles_per_px)


def shear_ratio(ref: np.ndarray, meas: np.ndarray, carrier: Carrier,
                window: bool = True) -> complex:
    """The complex ratio S(f)/F(f) at ``carrier``.

    ``S`` is the transform of the sheared pattern (measured minus reference) and
    ``F`` the transform of the reference -- Eqs. (1) and (3).
    """
    ref = np.asarray(ref, dtype=np.float64)
    meas = np.asarray(meas, dtype=np.float64)
    if ref.shape != meas.shape:
        raise ValueError(f"shape mismatch: ref {ref.shape} vs meas {meas.shape}")

    r = ref - ref.mean()
    d = (meas - meas.mean()) - r          # the sheared pattern
    if window:
        win = _hann2d(r.shape)
        r = r * win
        d = d * win

    F = np.fft.fft2(r)
    S = np.fft.fft2(d)
    idx = (0, carrier.bin_index) if carrier.axis == "x" else (carrier.bin_index, 0)

    f = F[idx]
    if f == 0 or not np.isfinite(f):
        raise ValueError("reference has no energy at the carrier bin")
    return complex(S[idx] / f)


# --------------------------------------------------------------------------
# Phase -> physical shift on the screen (Eq. 5)
# --------------------------------------------------------------------------

def shift_mm(phase: float, period_mm: float) -> float:
    """Convert a phase shift to a length on the SCREEN, via Eq. (5).

    ``phase`` is in radians of the carrier; ``period_mm`` is that carrier's
    physical period on the screen (pixels-per-period x measured pixel pitch).
    The camera magnification cancels because a phase fraction is invariant.
    """
    return (phase / TWO_PI) * period_mm


def synthetic_period(period_a: float, period_b: float) -> float:
    """Beat period of two carriers: a CONSERVATIVE unambiguous range.

    Consistent solutions actually repeat at the least common multiple of the two
    periods, which is an integer multiple of this beat period.  Writing
    ``Pb/Pa = p/q`` in lowest terms, the true repeat is ``p * Pa = (p - q) * beat``
    -- so a 4:3 pair repeats exactly at the beat period, while the 5:3 pair from
    :func:`~smots.patterns.coprime_periods` repeats at twice it.

    This returns the beat period because under-claiming the range is the safe
    direction: quote it, and the measurement is unambiguous for certain.
    """
    if period_a == period_b:
        raise ValueError("two identical periods carry no extra information")
    return abs(period_a * period_b / (period_a - period_b))


def unwrap_two_carrier(shift_a: float, period_a: float,
                       shift_b: float, period_b: float,
                       max_orders: int = 12, prior: float = 0.0,
                       tol: float | None = None) -> tuple[float, float]:
    """Resolve the 2*pi ambiguity from two carriers -- Section 3.2 of the paper.

    Each carrier reports its shift only modulo its own period.  The true shift is
    one both agree on -- but "both agree" does not pick out a single answer.  The
    pair realigns every *synthetic period* ``Pa Pb / |Pa - Pb|``, so consistent
    solutions repeat forever at that spacing.  Taking the globally best-agreeing
    candidate therefore returns an arbitrary alias; this function instead keeps
    every candidate that agrees within ``tol`` and returns the one nearest
    ``prior`` (zero by default, i.e. the smallest plausible motion).

    Pass ``prior`` when you are tracking -- the previous measurement extends the
    usable range indefinitely, because you only need to resolve the change since
    the last frame rather than the total.

    Returns ``(shift, residual)``.  The residual is how far the two carriers
    still disagree; a residual approaching a period means they never really
    agreed and the result should not be trusted.
    """
    if period_a <= 0 or period_b <= 0:
        raise ValueError("periods must be positive")
    if tol is None:
        tol = 0.25 * min(period_a, period_b)

    candidates: list[tuple[float, float]] = []
    for na in range(-max_orders, max_orders + 1):
        cand_a = shift_a + na * period_a
        nb = round((cand_a - shift_b) / period_b)      # nearest order of carrier b
        cand_b = shift_b + nb * period_b
        candidates.append((0.5 * (cand_a + cand_b), abs(cand_a - cand_b)))

    agreeing = [c for c in candidates if c[1] <= tol]
    if not agreeing:
        # Nothing lined up: hand back the closest call together with its residual
        # so the caller can see it failed rather than silently trusting it.
        return min(candidates, key=lambda c: c[1])
    return min(agreeing, key=lambda c: abs(c[0] - prior))


__all__ = [
    "Carrier", "phase_complex", "phase_paper_eq4", "find_carriers",
    "shear_ratio", "shift_mm", "unwrap_two_carrier", "synthetic_period",
    "TWO_PI",
]
