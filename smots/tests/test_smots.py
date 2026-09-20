"""Test suite for the SMOTS reference implementation.

The tests that matter are the closed-loop ones: command a tilt, render the frame
the camera would see, run the full retrieval, and check the number that comes
back is the number that went in.  Everything else is a guard on a convention or
an edge case that would otherwise fail silently.
"""

from __future__ import annotations

import numpy as np
import pytest

from smots import (Bench, MirrorArray, PatternSpec, coprime_periods,
                   find_carriers, geometry, grid_apertures, measure,
                   phase_complex, phase_paper_eq4, reference_frame,
                   render_frame, sampling_report, shear_ratio, shift_mm,
                   synthetic_period, unwrap_two_carrier)

URAD = 1e-6


# --------------------------------------------------------------------------
# Phase estimators
# --------------------------------------------------------------------------

@pytest.mark.parametrize("psi", [0.05, 0.4, 1.2, 2.0, 2.9, -0.4, -1.7, -2.9])
def test_both_estimators_recover_the_phase(psi):
    """Eq. (4) and the complex form agree, and both invert the shear exactly."""
    ratio = np.exp(1j * psi) - 1.0
    assert float(phase_complex(ratio)) == pytest.approx(psi, abs=1e-12)
    assert float(phase_paper_eq4(ratio)) == pytest.approx(psi, abs=1e-6)


def test_eq4_without_sign_recovery_is_unsigned():
    """Eq. (4) alone cannot tell +psi from -psi -- hence the paper's sign step."""
    up = phase_paper_eq4(np.exp(1j * 0.7) - 1.0, use_sign=False)
    dn = phase_paper_eq4(np.exp(-1j * 0.7) - 1.0, use_sign=False)
    assert float(up) == pytest.approx(float(dn), abs=1e-12)
    assert float(up) > 0


def test_complex_form_is_better_conditioned_near_wrap():
    """arccos loses precision where its derivative blows up; atan2 does not."""
    psi = np.pi - 1e-4
    ratio = np.exp(1j * psi) - 1.0
    err_complex = abs(float(phase_complex(ratio)) - psi)
    err_eq4 = abs(float(phase_paper_eq4(ratio)) - psi)
    assert err_complex <= err_eq4


def test_shift_recovered_from_synthetic_fringes():
    """A known sub-pixel displacement comes back out of the sheared analysis."""
    period, h, w = 30.0, 64, 240
    x = np.arange(w)
    for delta in (0.25, -3.5, 11.0, -14.0):
        ref = (128 + 80 * np.cos(2 * np.pi * x / period))[None, :].repeat(h, 0)
        mea = (128 + 80 * np.cos(2 * np.pi * (x + delta) / period))[None, :].repeat(h, 0)
        carrier = find_carriers(ref, "x", 1)[0]
        got = shift_mm(float(phase_complex(shear_ratio(ref, mea, carrier))),
                       carrier.period_px)
        assert got == pytest.approx(delta, abs=1e-3)


# --------------------------------------------------------------------------
# Geometry conventions
# --------------------------------------------------------------------------

def test_paper_eq6_is_our_convention_negated():
    a = geometry.tilt_from_shift(0.0, 0.5, 0.0, 400.0)
    b = geometry.tilt_from_shift_paper(0.0, 0.5, 0.0, 400.0)
    assert float(a) == pytest.approx(-float(b), rel=1e-12)


def test_small_angle_matches_full_arctan_on_axis():
    z_d, delta = 400.0, 0.4
    full = float(geometry.tilt_from_shift(0.0, delta, 0.0, z_d))
    para = float(geometry.small_angle_tilt(delta, z_d))
    assert full == pytest.approx(para, rel=2e-6)


def test_tilt_and_shift_are_inverses():
    z_d, x0 = 400.0, 41.2
    for theta in (10 * URAD, -250 * URAD, 1e-3):
        xf = float(geometry.shift_from_tilt(theta, x0, z_d))
        back = float(geometry.tilt_from_shift(x0, xf, x0, z_d))
        assert back == pytest.approx(theta, rel=1e-9)


def test_zero_distance_rejected():
    with pytest.raises(ValueError):
        geometry.tilt_from_shift(0.0, 1.0, 0.0, 0.0)


# --------------------------------------------------------------------------
# Closed loop through the full pipeline
# --------------------------------------------------------------------------

@pytest.fixture
def bench():
    return Bench()


@pytest.fixture
def spec():
    return PatternSpec(periods_px=(30.0,), axes="xy", bias=128.0, amplitude=100.0)


def _loop(bench, spec, tilts_x=None, tilts_y=None, noise=0.0, px_per_mm=6.0, seed=0):
    rng = np.random.default_rng(seed)
    ref = reference_frame(bench, spec, px_per_mm=px_per_mm, noise_dn=noise, rng=rng)
    mea = render_frame(bench, spec, tilts_x=tilts_x, tilts_y=tilts_y,
                       px_per_mm=px_per_mm, noise_dn=noise, rng=rng)
    aps = grid_apertures(ref.image.shape, bench.array, bounds=ref.bounds)
    return measure(bench, spec, ref.image, mea.image, aps)


@pytest.mark.parametrize("applied", [20 * URAD, 75 * URAD, -120 * URAD, 200 * URAD])
def test_centre_node_tilt_recovered(bench, spec, applied):
    """The headline capability: command M5, read M5 back."""
    res = _loop(bench, spec, tilts_x={"M5": applied})
    assert res.by_name("M5").theta_x == pytest.approx(applied, rel=0.02, abs=1.0 * URAD)


def test_untilted_nodes_read_near_zero(bench, spec):
    res = _loop(bench, spec, tilts_x={"M5": 150 * URAD})
    for node in res.nodes:
        if node.name == "M5":
            continue
        assert abs(node.theta_x) < 2 * URAD
        assert abs(node.theta_y) < 2 * URAD


def test_both_axes_are_independent(bench, spec):
    """A tilt in x must not leak into the y channel."""
    res = _loop(bench, spec, tilts_x={"M5": 180 * URAD}, tilts_y={"M5": -90 * URAD})
    node = res.by_name("M5")
    assert node.theta_x == pytest.approx(180 * URAD, rel=0.03)
    assert node.theta_y == pytest.approx(-90 * URAD, rel=0.03)


def test_all_segments_measured_simultaneously(bench, spec):
    """Every segment is solved from the same pair of frames."""
    applied = {"M1": 60 * URAD, "M3": -80 * URAD, "M5": 140 * URAD, "M9": 100 * URAD}
    res = _loop(bench, spec, tilts_x=applied)
    assert len(res.nodes) == bench.array.count
    for name, value in applied.items():
        assert res.by_name(name).theta_x == pytest.approx(value, rel=0.03, abs=1.0 * URAD)


def test_common_mode_is_rejected(bench, spec):
    """A global disturbance is recognised as common motion and subtracted.

    Section 3.1: the whole point of watching every segment at once.
    """
    drift = 90 * URAD
    real = 130 * URAD
    tilts = {bench.array.name(r, c): drift
             for r in range(bench.array.rows) for c in range(bench.array.cols)}
    tilts["M5"] = drift + real
    res = _loop(bench, spec, tilts_x=tilts)

    assert res.by_name("M5").theta_x == pytest.approx(drift + real, rel=0.03)
    diff_x, _ = res.differential("M5")
    assert diff_x == pytest.approx(real, rel=0.05, abs=2 * URAD)
    for name in ("M1", "M9"):
        dx, _ = res.differential(name)
        assert abs(dx) < 3 * URAD


def test_noise_degrades_gracefully(bench, spec):
    """With realistic camera noise the answer stays usable, not perfect."""
    applied = 150 * URAD
    res = _loop(bench, spec, tilts_x={"M5": applied}, noise=2.0, seed=7)
    assert res.by_name("M5").theta_x == pytest.approx(applied, rel=0.10, abs=5 * URAD)


# --------------------------------------------------------------------------
# 2*pi ambiguity and multiplexing
# --------------------------------------------------------------------------

def test_single_carrier_wraps_beyond_its_range(bench, spec):
    """Past half a period the single-carrier answer folds back -- as expected."""
    wrap = geometry.unambiguous_range(spec.periods_mm(bench.screen.pitch_mm)[0],
                                      bench.screen_distance_mm)
    res = _loop(bench, spec, tilts_x={"M5": 1.6 * wrap})
    assert abs(res.by_name("M5").theta_x) < wrap          # folded back inside
    assert res.by_name("M5").theta_x != pytest.approx(1.6 * wrap, rel=0.1)


def test_multiplexed_pattern_extends_the_range(bench):
    """Two carriers recover a tilt that wraps either one alone."""
    periods = coprime_periods(24.0)                 # (24, 40) px
    multi = PatternSpec(periods_px=periods, axes="xy", bias=128.0, amplitude=90.0)
    pitch = bench.screen.pitch_mm
    single = geometry.unambiguous_range(multi.periods_mm(pitch)[0],
                                        bench.screen_distance_mm)
    synth = geometry.unambiguous_range(
        synthetic_period(*multi.periods_mm(pitch)), bench.screen_distance_mm)
    assert synth > 1.9 * single, "the pair must actually extend the range"

    applied = 1.4 * single                          # wraps carrier 1, inside synth
    res = _loop(bench, multi, tilts_x={"M5": applied}, px_per_mm=9.0)
    assert res.by_name("M5").theta_x == pytest.approx(applied, rel=0.10)


def test_synthetic_period_beats_either_carrier():
    assert synthetic_period(24.0, 40.0) == pytest.approx(60.0)
    with pytest.raises(ValueError):
        synthetic_period(30.0, 30.0)


def test_unwrap_agrees_with_itself_inside_one_period():
    value, residual = unwrap_two_carrier(0.4, 3.0, 0.4, 3.7)
    assert value == pytest.approx(0.4, abs=1e-9)
    assert residual == pytest.approx(0.0, abs=1e-9)


def test_unwrap_reports_a_residual_when_carriers_disagree():
    _, residual = unwrap_two_carrier(0.4, 3.0, 1.9, 3.7)
    assert residual > 0.05


# --------------------------------------------------------------------------
# Apertures and hardware guards
# --------------------------------------------------------------------------

def test_aperture_grid_covers_every_node():
    arr = MirrorArray()
    aps = grid_apertures((600, 600), arr)
    assert [a.name for a in aps] == [f"M{i}" for i in range(1, 10)]
    assert all(a.area > 0 for a in aps)


def test_apertures_do_not_overlap():
    aps = grid_apertures((600, 600), MirrorArray())
    for i, a in enumerate(aps):
        for b in aps[i + 1:]:
            disjoint = (a.x1 <= b.x0 or b.x1 <= a.x0
                        or a.y1 <= b.y0 or b.y1 <= a.y0)
            assert disjoint, f"{a.name} overlaps {b.name}"


def test_tiny_apertures_are_rejected():
    with pytest.raises(ValueError, match="too small"):
        grid_apertures((30, 30), MirrorArray())


def test_sampling_report_flags_an_undersampled_aperture():
    aps = grid_apertures((600, 600), MirrorArray())
    assert sampling_report(aps, 30.0)["ok"]
    assert not sampling_report(aps, 200.0)["ok"]


def test_channel_budget_matches_the_kim101():
    assert Bench().channel_budget_ok()
    assert Bench().controller.max_tiptilt_nodes == 2
    crowded = Bench(motorised=((0, 0), (1, 1), (2, 2)))
    assert not crowded.channel_budget_ok()
    assert crowded.channels_used() == 6


def test_clipped_pattern_is_rejected():
    with pytest.raises(ValueError, match="clips"):
        PatternSpec(bias=200.0, amplitude=100.0)


def test_mismatched_frames_are_rejected(bench, spec):
    ref = reference_frame(bench, spec, noise_dn=0)
    aps = grid_apertures(ref.image.shape, bench.array, bounds=ref.bounds)
    with pytest.raises(ValueError, match="shapes differ"):
        measure(bench, spec, ref.image, ref.image[:-5, :-5], aps)


def _wrap(value, period):
    return (value + period / 2) % period - period / 2


def test_unwrap_picks_the_branch_nearest_the_prior():
    """Consistent solutions repeat; the prior chooses which one is reported.

    A 4:3 period pair repeats exactly at the beat period, so the arithmetic here
    is unambiguous to state.
    """
    pa = 2.15
    pb = pa * 4.0 / 3.0
    beat = synthetic_period(pa, pb)
    assert beat == pytest.approx(4 * pa)          # 4:3 -> repeat == beat

    true = 1.5035
    wa, wb = _wrap(true, pa), _wrap(true, pb)

    near, res = unwrap_two_carrier(wa, pa, wb, pb)
    assert near == pytest.approx(true, abs=0.02)
    assert res < 0.05

    far, _ = unwrap_two_carrier(wa, pa, wb, pb, prior=true + beat)
    assert far == pytest.approx(true + beat, abs=0.05)


def test_unwrap_aliases_beyond_the_unambiguous_range():
    """Documented limit: shifts one repeat apart are indistinguishable."""
    pa = 2.15
    pb = pa * 4.0 / 3.0
    beat = synthetic_period(pa, pb)
    true = 1.5035 + beat
    got, _ = unwrap_two_carrier(_wrap(true, pa), pa, _wrap(true, pb), pb)
    assert got == pytest.approx(true - beat, abs=0.05)   # folded to the near branch


def test_beat_period_is_a_conservative_range():
    """The real repeat is the LCM, which can exceed the beat period.

    Guards the claim in ``synthetic_period``'s docstring: for a 5:3 pair the
    solutions repeat at twice the beat, so quoting the beat under-claims.
    """
    pa = 2.15
    pb = pa * 5.0 / 3.0
    beat = synthetic_period(pa, pb)
    true = 1.5035
    wa, wb = _wrap(true, pa), _wrap(true, pb)

    tol = 0.25 * min(pa, pb)
    branches = []
    for na in range(-8, 9):
        ca = wa + na * pa
        cb = wb + round((ca - wb) / pb) * pb
        if abs(ca - cb) <= tol:
            branches.append(0.5 * (ca + cb))
    branches.sort()
    spacing = np.diff(branches)
    assert np.allclose(spacing, spacing[0], rtol=1e-3)
    assert spacing[0] == pytest.approx(2 * beat, rel=1e-3)


def test_unwrap_flags_carriers_that_never_agree():
    _, residual = unwrap_two_carrier(0.0, 2.0, 1.0, 2.0)   # same period, offset
    assert residual > 0.4
