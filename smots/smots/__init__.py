"""SMOTS -- Simultaneous Multi-segmented mirror Orientation Test System.

A reference implementation of the sheared-Fourier tilt retrieval described in

    H. Choi, I. Trumper, M. Dubin, W. Zhao and D. W. Kim,
    "Simultaneous angular alignment of segmented mirrors using sinusoidal
    pattern analysis", Proc. SPIE 10377, 103770G (2017).

Built for the ASU deflectometry mirror-array bench: a 3x3 array of 1 in square
mirrors with the centre node (M5) motorised by 2x MPIA10 inertia actuators.

Quick start
-----------
>>> from smots import Bench, PatternSpec, reference_frame, render_frame
>>> from smots import grid_apertures, measure
>>> bench = Bench()
>>> spec = PatternSpec(periods_px=(30.0,), axes="xy")
>>> ref = reference_frame(bench, spec, noise_dn=0)
>>> mea = render_frame(bench, spec, tilts_x={"M5": 150e-6}, noise_dn=0)
>>> aps = grid_apertures(ref.image.shape, bench.array, bounds=ref.bounds)
>>> result = measure(bench, spec, ref.image, mea.image, aps)
>>> round(result.by_name("M5").theta_x_urad)
150
"""

from .analysis import (Carrier, find_carriers, phase_complex, phase_paper_eq4,
                       shear_ratio, shift_mm, synthetic_period,
                       unwrap_two_carrier)
from .apertures import Aperture, grid_apertures, sampling_report
from .geometry import (angle_resolution, shift_from_tilt, small_angle_tilt,
                       tilt_from_shift, tilt_from_shift_paper, unambiguous_range)
from .hardware import (Actuator, Bench, Camera, Controller, MirrorArray, Screen,
                       DEFAULT_BENCH)
from .patterns import PatternSpec, coprime_periods, render, sample
from .pipeline import Measurement, NodeResult, measure
from .simulate import SyntheticFrame, reference_frame, render_frame

__version__ = "0.1.0"

__all__ = [
    "Bench", "Screen", "MirrorArray", "Actuator", "Controller", "Camera",
    "DEFAULT_BENCH", "PatternSpec", "render", "sample", "coprime_periods",
    "synthetic_period",
    "Carrier", "find_carriers", "shear_ratio", "phase_complex",
    "phase_paper_eq4", "shift_mm", "unwrap_two_carrier",
    "Aperture", "grid_apertures", "sampling_report",
    "tilt_from_shift", "tilt_from_shift_paper", "shift_from_tilt",
    "small_angle_tilt", "angle_resolution", "unambiguous_range",
    "SyntheticFrame", "render_frame", "reference_frame",
    "measure", "Measurement", "NodeResult", "__version__",
]
