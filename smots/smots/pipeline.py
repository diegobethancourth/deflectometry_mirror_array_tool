"""End-to-end SMOTS measurement: two images in, per-segment tilt angles out.

    reference frame + measured frame
      -> per-segment digital aperture          (apertures.py)
      -> carrier located in the camera spectrum (analysis.find_carriers)
      -> sheared Fourier ratio S/F              (analysis.shear_ratio)
      -> signed phase                           (analysis.phase_complex)
      -> screen shift in mm, Eq. (5)            (analysis.shift_mm)
      -> 2*pi unwrap if multiplexed             (analysis.unwrap_two_carrier)
      -> tilt angle, Eq. (6)                    (geometry.tilt_from_shift)

Every angle is RELATIVE to the reference capture, which is the whole design of
SMOTS: it measures a *change* in orientation, and an absolute number needs a
separate absolute-reference calibration (an autocollimator, as the paper used).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import analysis, geometry
from .apertures import Aperture
from .hardware import Bench
from .patterns import PatternSpec


@dataclass
class NodeResult:
    """One segment's measured orientation change."""

    name: str
    row: int
    col: int
    theta_x: float                  # rad, normal rotates toward +x
    theta_y: float
    shift_x_mm: float
    shift_y_mm: float
    period_x_px: float = 0.0        # apparent carrier period in the camera
    period_y_px: float = 0.0
    residual_x_mm: float | None = None   # two-carrier disagreement, if multiplexed
    residual_y_mm: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def theta_x_urad(self) -> float:
        return self.theta_x * 1e6

    @property
    def theta_y_urad(self) -> float:
        return self.theta_y * 1e6

    @property
    def magnitude_urad(self) -> float:
        return float(np.hypot(self.theta_x, self.theta_y) * 1e6)


@dataclass
class Measurement:
    """All segments from one pair of frames."""

    nodes: list[NodeResult]
    common_x: float = 0.0           # rad, median tilt across all segments
    common_y: float = 0.0

    def by_name(self, name: str) -> NodeResult:
        for n in self.nodes:
            if n.name == name:
                return n
        raise KeyError(f"no node {name!r}; have {[n.name for n in self.nodes]}")

    def differential(self, name: str) -> tuple[float, float]:
        """This node's tilt with the array-wide common motion removed.

        Section 3.1 of the paper: watching every segment at once lets a global
        disturbance -- someone leaning on the table, the whole breadboard
        drifting -- be recognised as common motion and subtracted, leaving the
        real relative change on the node you actually moved.
        """
        n = self.by_name(name)
        return n.theta_x - self.common_x, n.theta_y - self.common_y

    def table(self) -> str:
        w = max((len(n.name) for n in self.nodes), default=4)
        lines = [f"{'node'.ljust(w)}   theta_x     theta_y      |theta|",
                 f"{'':-<{w}}   --------    --------    --------"]
        for n in self.nodes:
            lines.append(f"{n.name.ljust(w)}  {n.theta_x_urad:+8.2f}    "
                         f"{n.theta_y_urad:+8.2f}    {n.magnitude_urad:8.2f}   urad")
        return "\n".join(lines)


def _axis_shift(ref: np.ndarray, meas: np.ndarray, axis: str,
                periods_mm: tuple[float, ...],
                window: bool) -> tuple[float, float, float | None, list[str]]:
    """Recover the screen shift along one axis for a single aperture."""
    notes: list[str] = []
    n_carriers = len(periods_mm)
    carriers = analysis.find_carriers(ref, axis, n_carriers=n_carriers, window=window)
    if not carriers:
        return float("nan"), 0.0, None, [f"no {axis} carrier found"]
    if len(carriers) < n_carriers:
        notes.append(f"expected {n_carriers} {axis} carriers, found {len(carriers)}")

    # Carriers come back sorted by ascending frequency; the longest screen period
    # is the lowest frequency, so pair them off in that order.
    screen_periods = sorted(periods_mm, reverse=True)

    shifts, periods = [], []
    for carrier, period_mm in zip(carriers, screen_periods):
        ratio = analysis.shear_ratio(ref, meas, carrier, window=window)
        phase = float(analysis.phase_complex(ratio))
        shifts.append(analysis.shift_mm(phase, period_mm))
        periods.append(period_mm)

    if len(shifts) >= 2:
        value, residual = analysis.unwrap_two_carrier(
            shifts[0], periods[0], shifts[1], periods[1])
        if residual > 0.25 * min(periods):
            notes.append(f"{axis}: carriers disagree by {residual:.3f} mm "
                         "-- unwrap unreliable, treat this node as suspect")
        return value, carriers[0].period_px, residual, notes

    return shifts[0], carriers[0].period_px, None, notes


def measure(bench: Bench, spec: PatternSpec, reference: np.ndarray,
            measured: np.ndarray, apertures: list[Aperture],
            window: bool = True, y_axis_down: bool = True) -> Measurement:
    """Measure every segment's orientation change between two frames.

    ``y_axis_down`` says the image is stored with row 0 at the TOP, so the row
    index increases as world y decreases -- the usual convention for camera
    frames and for every image library.  The retrieval works in array indices,
    so without this flip the y tilt comes back with the wrong sign while x is
    perfectly correct, which is a failure mode that looks like a wiring error
    rather than a software one.  Set it False only if your frames are already
    stored bottom-up.
    """
    reference = np.asarray(reference, dtype=np.float64)
    measured = np.asarray(measured, dtype=np.float64)
    if reference.shape != measured.shape:
        raise ValueError(f"frame shapes differ: {reference.shape} vs {measured.shape}")
    if not apertures:
        raise ValueError("no apertures supplied")

    periods_mm = spec.periods_mm(bench.screen.pitch_mm)
    z_d = bench.screen_distance_mm

    nodes: list[NodeResult] = []
    for ap in apertures:
        r = ap.extract(reference)
        m = ap.extract(measured)
        cx, cy = bench.array.centre_mm(ap.row, ap.col)

        dx, px, rx, nx = _axis_shift(r, m, "x", periods_mm, window)
        dy, py, ry, ny = _axis_shift(r, m, "y", periods_mm, window)
        if y_axis_down:
            dy = -dy                    # image rows run against world +y

        # The reference intercept for a flat mirror is the mirror's own position,
        # so x_i = x_0 and the first arctan term vanishes.  Passing both keeps the
        # off-axis arctan intact rather than assuming the paraxial shortcut.
        theta_x = float(geometry.tilt_from_shift(cx, cx + dx, cx, z_d)) if np.isfinite(dx) else float("nan")
        theta_y = float(geometry.tilt_from_shift(cy, cy + dy, cy, z_d)) if np.isfinite(dy) else float("nan")

        nodes.append(NodeResult(
            name=ap.name, row=ap.row, col=ap.col,
            theta_x=theta_x, theta_y=theta_y,
            shift_x_mm=dx, shift_y_mm=dy,
            period_x_px=px, period_y_px=py,
            residual_x_mm=rx, residual_y_mm=ry,
            notes=nx + ny))

    good_x = [n.theta_x for n in nodes if np.isfinite(n.theta_x)]
    good_y = [n.theta_y for n in nodes if np.isfinite(n.theta_y)]
    return Measurement(nodes=nodes,
                       common_x=float(np.median(good_x)) if good_x else 0.0,
                       common_y=float(np.median(good_y)) if good_y else 0.0)


__all__ = ["NodeResult", "Measurement", "measure"]
