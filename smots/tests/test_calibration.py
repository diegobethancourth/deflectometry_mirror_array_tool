"""Tests for mirror-based screen-pose calibration.

The load-bearing tests are the closed-loop ones: place a screen at a known pose,
generate the correspondences that geometry implies, recover the pose, and check
it comes back.  The rest guard the two things this method gets wrong quietly --
a degenerate ray bundle, and a wrong screen pitch.
"""

from __future__ import annotations

import numpy as np
import pytest

from smots import Bench
from smots.calibration import (PoseEstimate, ScreenPose, estimate_screen_pose,
                               householder, ray_conditioning, reflect_pose,
                               screen_geometry, synthetic_observations)


@pytest.fixture
def centres():
    arr = Bench().array
    return np.array([[*arr.centre_mm(r, c), 0.0]
                     for r in range(arr.rows) for c in range(arr.cols)])


def normals(spread_deg: float, n: int, seed: int = 5) -> np.ndarray:
    """Mirror normals scattered by a given RMS tilt, as a hand-set array is."""
    rng = np.random.default_rng(seed)
    s = np.radians(spread_deg)
    out = []
    for _ in range(n):
        tx, ty = (rng.normal(0.0, s, 2) if s > 0 else (0.0, 0.0))
        out.append([np.sin(tx), np.sin(ty),
                    np.sqrt(max(0.0, 1 - np.sin(tx) ** 2 - np.sin(ty) ** 2))])
    return np.array(out)


def tilted_pose(deg: float = 2.5, t=(3.0, -12.0, 400.0)) -> ScreenPose:
    a = np.radians(deg)
    R = np.array([[1.0, 0.0, 0.0],
                  [0.0, np.cos(a), -np.sin(a)],
                  [0.0, np.sin(a), np.cos(a)]])
    return ScreenPose(R=R, t=np.array(t))


# --------------------------------------------------------------------------
# Plane reflection
# --------------------------------------------------------------------------

def test_householder_is_an_involution():
    H = householder([0.0, 0.3, 1.0], 12.5)
    assert np.allclose(H @ H, np.eye(4))


def test_householder_flips_handedness():
    H = householder([0.0, 0.0, 1.0], 5.0)
    assert np.linalg.det(H[:3, :3]) == pytest.approx(-1.0)


def test_householder_fixes_points_on_the_plane():
    n, d = np.array([0.0, 0.0, 1.0]), 7.0
    H = householder(n, d)
    on_plane = np.array([4.0, -2.0, 7.0, 1.0])
    assert np.allclose((H @ on_plane)[:3], on_plane[:3])


def test_zero_normal_rejected():
    with pytest.raises(ValueError):
        householder([0.0, 0.0, 0.0], 1.0)


def test_reflecting_a_pose_twice_returns_it():
    """The mirror trick: real -> virtual -> real."""
    pose = tilted_pose()
    n, d = [0.1, 0.0, 1.0], 50.0
    back = reflect_pose(reflect_pose(pose, n, d), n, d)
    assert np.allclose(back.t, pose.t, atol=1e-9)
    assert np.allclose(np.abs(back.R), np.abs(pose.R), atol=1e-9)


def test_reflected_pose_stays_right_handed():
    out = reflect_pose(tilted_pose(), [0.0, 0.0, 1.0], 200.0)
    assert np.linalg.det(out.R) == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------
# Conditioning -- the failure mode that returns a confident wrong answer
# --------------------------------------------------------------------------

def test_parallel_rays_are_exactly_degenerate():
    parallel = np.tile([0.0, 0.0, 1.0], (20, 1))
    assert ray_conditioning(parallel) == pytest.approx(0.0, abs=1e-12)


def test_spread_rays_are_conditioned():
    rng = np.random.default_rng(0)
    spread = rng.normal(0.0, 0.3, (40, 3)) + np.array([0.0, 0.0, 1.0])
    assert ray_conditioning(spread) > 0.01


def test_flat_array_cannot_see_depth_and_says_so(centres):
    """A perfectly flat array is the degenerate case, not merely a hard one.

    Every reflected ray is parallel, so the screen slides freely along them and
    z_d is unobservable no matter how much data is collected.  The estimator
    must flag this rather than return a plausible number.
    """
    truth = ScreenPose(R=np.eye(3), t=np.array([0.0, 0.0, 400.0]))
    flat = np.tile([0.0, 0.0, 1.0], (len(centres), 1))
    P, D, Q = synthetic_observations(truth, centres, flat, samples=3)
    est = estimate_screen_pose(P, D, Q)

    assert est.conditioning == pytest.approx(0.0, abs=1e-9)
    assert any("unobservable" in w for w in est.warnings)
    # and the depth it reports is indeed meaningless
    assert abs(screen_geometry(est.pose)["z_d_mm"] - 400.0) > 100.0


# --------------------------------------------------------------------------
# Closed loop
# --------------------------------------------------------------------------

def test_pose_recovered_exactly_from_clean_data(centres):
    truth = tilted_pose()
    P, D, Q = synthetic_observations(truth, centres, normals(4.0, len(centres)),
                                     samples=3)
    est = estimate_screen_pose(P, D, Q)

    assert est.rms_mm < 1e-6
    assert np.allclose(est.pose.t, truth.t, atol=1e-4)
    assert np.allclose(est.pose.normal, truth.normal, atol=1e-6)
    assert est.pitch_scale == pytest.approx(1.0, abs=1e-6)
    assert est.refined


def test_screen_geometry_extracts_what_eq6_needs(centres):
    """z_d is the PERPENDICULAR distance to the screen plane.

    With the screen origin 400 mm out but the plane tilted 2.5 deg, that
    perpendicular distance is 400*cos(2.5 deg), not 400 -- the foot of the
    perpendicular is not the screen origin.  Perpendicular distance is the right
    quantity for Eq. (6), and the reported tilt is what tells you the equation's
    parallel-screen assumption is being stretched.
    """
    truth = tilted_pose(deg=2.5, t=(0.0, 0.0, 400.0))
    P, D, Q = synthetic_observations(truth, centres, normals(4.0, len(centres)),
                                     samples=3)
    geom = screen_geometry(estimate_screen_pose(P, D, Q).pose)

    assert geom["z_d_mm"] == pytest.approx(400.0 * np.cos(np.radians(2.5)), abs=0.01)
    assert geom["tilt_deg"] == pytest.approx(2.5, abs=0.01)
    assert not geom["parallel"]
    assert "off parallel" in geom["note"]


def test_parallel_screen_reported_as_parallel(centres):
    truth = ScreenPose(R=np.eye(3), t=np.array([0.0, 0.0, 380.0]))
    P, D, Q = synthetic_observations(truth, centres, normals(4.0, len(centres)),
                                     samples=3)
    geom = screen_geometry(estimate_screen_pose(P, D, Q).pose)
    assert geom["parallel"]
    assert geom["z_d_mm"] == pytest.approx(380.0, abs=0.01)


def test_noise_degrades_gracefully(centres):
    truth = tilted_pose(t=(0.0, 0.0, 400.0))
    P, D, Q = synthetic_observations(truth, centres, normals(4.0, len(centres)),
                                     samples=3, noise_mm=0.05,
                                     rng=np.random.default_rng(1))
    est = estimate_screen_pose(P, D, Q)
    assert abs(screen_geometry(est.pose)["z_d_mm"] - 400.0) < 1.0
    assert est.rms_mm < 0.5


def test_more_tilt_spread_gives_better_depth(centres):
    """Conditioning is the lever: deliberately scattering the reference mirrors
    buys depth accuracy, which is why a 'perfectly aligned' array calibrates worst.
    """
    truth = ScreenPose(R=np.eye(3), t=np.array([0.0, 0.0, 400.0]))

    def z_error(spread_deg, seed):
        P, D, Q = synthetic_observations(
            truth, centres, normals(spread_deg, len(centres), seed=seed),
            samples=3, noise_mm=0.05, rng=np.random.default_rng(seed))
        return abs(screen_geometry(estimate_screen_pose(P, D, Q).pose)["z_d_mm"] - 400.0)

    tight = np.mean([z_error(0.5, s) for s in range(8)])
    wide = np.mean([z_error(6.0, s) for s in range(8)])
    assert wide < tight / 3.0


# --------------------------------------------------------------------------
# The free diagnostic: a wrong screen pitch shows up as a scale error
# --------------------------------------------------------------------------

@pytest.mark.parametrize("assumed_too_big", [1.02, 0.97])
def test_wrong_screen_pitch_shows_up_as_scale(centres, assumed_too_big):
    """Screen axes must come out unit length. They do not if the pitch is wrong.

    This matters because the screen pixel pitch is the one number the paper
    insists you measure under a microscope -- it scales every reported angle.
    """
    truth = tilted_pose(t=(0.0, 0.0, 400.0))
    P, D, Q = synthetic_observations(truth, centres, normals(4.0, len(centres)),
                                     samples=3)
    est = estimate_screen_pose(P, D, Q * assumed_too_big)

    assert est.pitch_scale == pytest.approx(1.0 / assumed_too_big, rel=1e-3)
    assert any("pitch" in w for w in est.warnings)


def test_correct_pitch_raises_no_scale_warning(centres):
    truth = tilted_pose(t=(0.0, 0.0, 400.0))
    P, D, Q = synthetic_observations(truth, centres, normals(4.0, len(centres)),
                                     samples=3)
    est = estimate_screen_pose(P, D, Q)
    assert not any("pitch" in w for w in est.warnings)


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------

def test_ragged_inputs_rejected():
    with pytest.raises(ValueError, match="ragged"):
        estimate_screen_pose(np.zeros((5, 3)), np.zeros((4, 3)), np.zeros((5, 2)))


def test_too_few_correspondences_rejected():
    with pytest.raises(ValueError, match="at least 4"):
        estimate_screen_pose(np.zeros((3, 3)), np.ones((3, 3)), np.zeros((3, 2)))


def test_zero_ray_direction_rejected():
    P = np.zeros((5, 3))
    D = np.tile([0.0, 0.0, 1.0], (5, 1)); D[2] = 0.0
    with pytest.raises(ValueError, match="zero vector"):
        estimate_screen_pose(P, D, np.zeros((5, 2)))


def test_screen_behind_the_mirrors_is_caught(centres):
    behind = ScreenPose(R=np.eye(3), t=np.array([0.0, 0.0, -400.0]))
    with pytest.raises(ValueError, match="in front"):
        synthetic_observations(behind, centres,
                               np.tile([0.0, 0.0, 1.0], (len(centres), 1)))


def test_mismatched_normals_rejected(centres):
    with pytest.raises(ValueError, match="one normal per"):
        synthetic_observations(tilted_pose(), centres, np.zeros((2, 3)))


def test_report_is_human_readable(centres):
    truth = tilted_pose()
    P, D, Q = synthetic_observations(truth, centres, normals(4.0, len(centres)),
                                     samples=3)
    text = estimate_screen_pose(P, D, Q).report()
    for expected in ("ScreenPose", "observations", "ray residual", "pitch scale"):
        assert expected in text
