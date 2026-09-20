"""Bench configuration for the ASU deflectometry mirror array.

Numbers here describe the as-built 9-node TR1.5/PH1.5 hybrid assembly from the
18 Sep 2026 weekly report: a 3x3 array of 1 in square mirrors, the centre node
(M5) motorised with 2x Thorlabs MPIA10 inertia actuators on a KIM101, and the
eight peripheral nodes set by hand.

Anything marked UNVERIFIED is a placeholder to replace with a measured value
before the numbers are used for anything but a sanity check.  In particular the
screen pixel pitch must be measured under a microscope -- the paper calls this
out explicitly, because the tilt scale is directly proportional to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Screen:
    """The display that shows the sinusoidal pattern."""

    width_mm: float = 344.0
    height_mm: float = 193.5
    pixels_x: int = 3840
    pixels_y: int = 2160

    @property
    def pitch_mm(self) -> float:
        """Physical size of one screen pixel, in mm.

        UNVERIFIED: measure this under a microscope.  Eq. (5) of the paper
        converts phase to a physical length using exactly this number, so an
        error here is a direct scale error on every angle you report.
        """
        return self.width_mm / self.pixels_x

    @property
    def pitch_um(self) -> float:
        return self.pitch_mm * 1000.0


@dataclass(frozen=True)
class MirrorArray:
    """Geometry of the segmented surrogate surface."""

    rows: int = 3
    cols: int = 3
    side_mm: float = 25.4          # PFSQ10-03-G01, 1 in square
    gap_mm: float = 3.0

    @property
    def pitch_mm(self) -> float:
        return self.side_mm + self.gap_mm

    @property
    def width_mm(self) -> float:
        return self.cols * self.side_mm + (self.cols - 1) * self.gap_mm

    @property
    def height_mm(self) -> float:
        return self.rows * self.side_mm + (self.rows - 1) * self.gap_mm

    @property
    def count(self) -> int:
        return self.rows * self.cols

    def name(self, row: int, col: int) -> str:
        """Node label in reading order -- the centre of a 3x3 is M5."""
        return f"M{row * self.cols + col + 1}"

    def centre_mm(self, row: int, col: int) -> tuple[float, float]:
        """(x, y) of a node centre, in mm, origin at the array centre.

        Row 0 is the top row, so y decreases as row increases.
        """
        x = (col - (self.cols - 1) / 2.0) * self.pitch_mm
        y = ((self.rows - 1) / 2.0 - row) * self.pitch_mm
        return x, y


@dataclass(frozen=True)
class Actuator:
    """Piezo inertia actuator driving one axis of a motorised node."""

    model: str = "MPIA10"
    travel_mm: float = 10.0        # UNVERIFIED -- read off the datasheet
    step_nm: float = 20.0          # UNVERIFIED -- typical PIA-series step
    lever_arm_mm: float = 19.05    # UNVERIFIED -- KMSR pivot-to-actuator distance

    @property
    def step_rad(self) -> float:
        """Mechanical tilt per actuator step."""
        return (self.step_nm * 1e-6) / self.lever_arm_mm


@dataclass(frozen=True)
class Controller:
    """Piezo controller. A tip/tilt node consumes two channels."""

    model: str = "KIM101"
    channels: int = 4

    @property
    def max_tiptilt_nodes(self) -> int:
        return self.channels // 2


@dataclass(frozen=True)
class Camera:
    pixels_x: int = 2448
    pixels_y: int = 2048
    noise_dn: float = 2.0          # 1-sigma read noise in grey levels
    bits: int = 8


@dataclass(frozen=True)
class Bench:
    """The whole setup: what the algorithm needs to turn phase into angle."""

    screen: Screen = field(default_factory=Screen)
    array: MirrorArray = field(default_factory=MirrorArray)
    actuator: Actuator = field(default_factory=Actuator)
    controller: Controller = field(default_factory=Controller)
    camera: Camera = field(default_factory=Camera)

    #: Mirror-to-screen distance z_d in Eq. (6), in mm.
    #: UNVERIFIED -- measure it; the paper quotes 2020 +/- 5 mm for their bench
    #: and the angle scales as 1/z_d.
    screen_distance_mm: float = 400.0

    #: Nodes carrying actuators, as (row, col). Defaults to the centre node.
    motorised: tuple[tuple[int, int], ...] = ((1, 1),)

    def is_motorised(self, row: int, col: int) -> bool:
        return (row, col) in self.motorised

    def channels_used(self) -> int:
        return 2 * len(self.motorised)

    def channel_budget_ok(self) -> bool:
        return self.channels_used() <= self.controller.channels


DEFAULT_BENCH = Bench()
