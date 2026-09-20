"""Screen shift -> mirror tilt angle. Eqs. (5) and (6) of the paper.

    Eq. (5)  x_f = x_i + (pixel pitch) * (pixels per period) * (shifted phase)
    Eq. (6)  theta = 1/2 * ( atan((x_i - x_0)/z_d) - atan((x_f - x_0)/z_d) )

where ``x_0`` is the mirror's own position along the axis, ``z_d`` the
mirror-to-screen distance, ``x_i`` the screen point the camera saw through that
mirror in the reference image and ``x_f`` the point it sees now.

The factor of 1/2 is the whole physics: rotating a mirror by ``theta`` swings the
reflected ray by ``2 theta``.

**Sign convention -- the second trap in this pipeline.**
Eq. (6) as printed subtracts the final term from the initial one, which returns a
NEGATIVE angle for a mirror whose normal rotates toward +x (verified against the
ray-traced forward model in :mod:`smots.simulate`).  That is self-consistent
inside the paper but inverts the sign of every angle relative to the intuitive
reading.  :func:`tilt_from_shift` uses the readable convention -- positive tilt
means the surface normal rotates toward +x -- and :func:`tilt_from_shift_paper`
reproduces Eq. (6) verbatim.  They differ only in sign; the test suite pins that
down so it cannot drift.
"""

from __future__ import annotations

import numpy as np


def tilt_from_shift(x_i: float | np.ndarray, x_f: float | np.ndarray,
                    x_0: float | np.ndarray, z_d: float) -> np.ndarray:
    """Mirror tilt in radians, positive when the normal rotates toward +x.

    All lengths in the same units (mm).  This is Eq. (6) with the two arctan
    terms in the order that yields the readable sign.
    """
    if z_d <= 0:
        raise ValueError("mirror-to-screen distance must be positive")
    x_i = np.asarray(x_i, dtype=np.float64)
    x_f = np.asarray(x_f, dtype=np.float64)
    x_0 = np.asarray(x_0, dtype=np.float64)
    return 0.5 * (np.arctan2(x_f - x_0, z_d) - np.arctan2(x_i - x_0, z_d))


def tilt_from_shift_paper(x_i, x_f, x_0, z_d):
    """Eq. (6) exactly as printed. Equals ``-tilt_from_shift(...)``."""
    return -tilt_from_shift(x_i, x_f, x_0, z_d)


def shift_from_tilt(theta: float | np.ndarray, x_0: float | np.ndarray,
                    z_d: float, x_i: float | np.ndarray | None = None) -> np.ndarray:
    """Forward model: screen point a mirror at ``x_0`` sends to the camera.

    Inverse of :func:`tilt_from_shift`.  Used to predict a shift from a commanded
    tilt, and by the tests to close the loop.
    """
    theta = np.asarray(theta, dtype=np.float64)
    x_0 = np.asarray(x_0, dtype=np.float64)
    x_i = np.asarray(x_0 if x_i is None else x_i, dtype=np.float64)
    a_i = np.arctan2(x_i - x_0, z_d)
    return x_0 + z_d * np.tan(a_i + 2.0 * theta)


def small_angle_tilt(delta_mm: float | np.ndarray, z_d: float) -> np.ndarray:
    """Paraxial shortcut: ``theta = delta / (2 z_d)``.

    Valid while the mirror sits near the optical axis and the tilt is small.
    Useful as an independent check on the full arctan form -- they agree to
    better than 0.1% for a mirror within ~5% of z_d off axis.
    """
    return np.asarray(delta_mm, dtype=np.float64) / (2.0 * z_d)


def angle_resolution(period_mm: float, z_d: float, phase_noise_rad: float) -> float:
    """Angular uncertainty (rad) implied by a given phase uncertainty.

    A phase error becomes a screen-position error ``period * phi / 2pi``, and the
    1/(2 z_d) lever turns that into an angle.  Shorter periods and longer
    standoffs both buy resolution -- at the cost of dynamic range, which is the
    trade the multiplexed pattern exists to dodge.
    """
    return (phase_noise_rad / (2.0 * np.pi)) * period_mm / (2.0 * z_d)


def unambiguous_range(period_mm: float, z_d: float) -> float:
    """Half-range of tilt a single carrier can report before it wraps (rad).

    The shift wraps at +/- period/2, so the tilt wraps at +/- period/(4 z_d).
    """
    return period_mm / (4.0 * z_d)


__all__ = [
    "tilt_from_shift", "tilt_from_shift_paper", "shift_from_tilt",
    "small_angle_tilt", "angle_resolution", "unambiguous_range",
]
