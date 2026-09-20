"""Mirror-based screen-pose calibration.

Why this module exists
----------------------
The error budget for this bench says screen geometry dominates everything else:
a uniform screen-pose offset and the panel's own non-flatness together account
for the great majority of the slope-error variance, while phase noise is a
rounding error beside them.  Eq. (6) of the SMOTS paper needs ``z_d``, the
mirror-to-screen distance, and it needs the screen to actually be where you
think it is.  Guessing those numbers caps your accuracy no matter how good the
phase retrieval gets.

The awkward part is that the camera never sees the screen.  It looks at the
mirrors.  So the screen's pose has to be recovered *through* the reflection,
which is what this module does.

Approach
--------
Structured after the linear-then-nonlinear pattern that mirror-based
deflectometry calibration conventionally uses (cf. Uhlig, *Light Field Imaging
for Deflectometry*, ch. 5).  Written from the geometry rather than transcribed
from that text, so treat the formulation here as this repository's own.

Each observation is a correspondence: a point ``P`` on a mirror of known normal,
the direction ``r`` the camera ray leaves in after reflecting there, and the
screen coordinate ``q = (u, v)`` that the decoded pattern says is being seen.
The screen point must lie somewhere along that reflected ray, which gives

    (I - r r^T) (R q + t - P) = 0                                     (*)

-- two independent constraints per observation on the screen pose ``(R, t)``,
with the unknown ray length eliminated.  Stack enough of them and solve:

1. **Linear.**  ``q`` always has zero third component, so the data constrains
   only the first two columns of ``R``.  Solve the 9 unknowns
   ``[r1, r2, t]`` by least squares, orthonormalise ``[r1 r2]``, and take
   ``r3 = r1 x r2``.
2. **Nonlinear.**  Refine all six pose degrees of freedom by Gauss-Newton on the
   same residual, which removes the bias the orthonormalisation step introduces.

Two things fall out of the linear stage for free, and both are worth more than
the pose itself:

* **The screen pixel pitch is measurable.**  If ``q`` is in millimetres then
  ``|r1|`` and ``|r2|`` must come out at 1.  They do not if the assumed pitch is
  wrong, and the deviation *is* the scale error -- on the number the paper warns
  you to measure under a microscope.
* **Degeneracy is detectable.**  If every reflected ray points the same way, (*)
  says nothing about position along that direction and ``z_d`` is simply not
  observable.  See :func:`ray_conditioning`.

What this needs that plain SMOTS does not
-----------------------------------------
Absolute screen coordinates.  The tilt measurement in :mod:`smots.pipeline`
tracks a *change* against a reference frame and never needs to know which
absolute fringe it is looking at.  Calibration does: ``q`` must be the true
screen coordinate, which means unwrapped absolute phase (a multi-frequency or
coded sequence), not the relative shift.

It also needs the mirror normals, which is circular, because mirror normals are
what SMOTS measures.  Break the loop with the mechanical normals of the manual
reference nodes -- they are set once and do not move -- or with an
autocollimator, then calibrate, then measure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# --------------------------------------------------------------------------
# Plane reflection
# --------------------------------------------------------------------------

def householder(normal: np.ndarray, offset: float) -> np.ndarray:
    """4x4 reflection through the plane ``{x : n.x = offset}``.

    ``normal`` need not be unit; it is normalised here.  The result is an
    involution with determinant -1 on its rotational block: reflecting twice
    returns the identity, and a single reflection flips handedness.
    """
    n = np.asarray(normal, dtype=np.float64).reshape(3)
    norm = np.linalg.norm(n)
    if norm == 0:
        raise ValueError("plane normal must be non-zero")
    n = n / norm
    m = np.eye(4)
    m[:3, :3] = np.eye(3) - 2.0 * np.outer(n, n)
    m[:3, 3] = 2.0 * offset * n
    return m


# --------------------------------------------------------------------------
# Pose
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ScreenPose:
    """Rigid placement of the screen: screen 2-D coordinates -> 3-D, in mm."""

    R: np.ndarray                  # 3x3, columns are the screen's u, v, normal axes
    t: np.ndarray                  # 3, screen origin

    def __post_init__(self) -> None:
        R = np.asarray(self.R, dtype=np.float64).reshape(3, 3)
        t = np.asarray(self.t, dtype=np.float64).reshape(3)
        object.__setattr__(self, "R", R)
        object.__setattr__(self, "t", t)

    @property
    def normal(self) -> np.ndarray:
        """Screen surface normal (its third axis)."""
        return self.R[:, 2]

    def point(self, u, v) -> np.ndarray:
        """3-D position of screen coordinate ``(u, v)`` in mm."""
        u = np.asarray(u, dtype=np.float64)
        v = np.asarray(v, dtype=np.float64)
        return (self.R[:, 0] * u[..., None] + self.R[:, 1] * v[..., None] + self.t)

    def signed_distance(self, p) -> np.ndarray:
        """Signed distance from ``p`` to the screen plane, along the normal."""
        p = np.asarray(p, dtype=np.float64)
        return (p - self.t) @ self.normal

    def as_matrix(self) -> np.ndarray:
        m = np.eye(4)
        m[:3, :3] = self.R
        m[:3, 3] = self.t
        return m

    def __str__(self) -> str:
        n = self.normal
        return (f"ScreenPose(origin=[{self.t[0]:.2f}, {self.t[1]:.2f}, {self.t[2]:.2f}] mm, "
                f"normal=[{n[0]:+.4f}, {n[1]:+.4f}, {n[2]:+.4f}])")


def reflect_pose(pose: ScreenPose, normal: np.ndarray, offset: float) -> ScreenPose:
    """Mirror a pose through a plane.

    The classic mirror-based trick: what the camera sees through a flat mirror is
    a *virtual* screen, and the real screen is that virtual one reflected back
    through the mirror plane.  Reflection is its own inverse, so applying this
    twice with the same plane returns the original pose.

    A reflection flips handedness, so the mirrored basis is left-handed.  The
    third axis is negated to keep the returned frame right-handed, which leaves
    the screen *plane* -- the only thing the geometry depends on -- unchanged.
    """
    H = householder(normal, offset)
    R = H[:3, :3] @ pose.R
    t = H[:3, :3] @ pose.t + H[:3, 3]
    R = R.copy()
    R[:, 2] = np.cross(R[:, 0], R[:, 1])
    return ScreenPose(R=R, t=t)


# --------------------------------------------------------------------------
# Conditioning
# --------------------------------------------------------------------------

def ray_conditioning(directions: np.ndarray) -> float:
    """How well the reflected rays pin down position, in [0, 1].

    Each observation constrains the screen only *across* its ray, never along
    it.  Summing ``I - r r^T`` over the observations accumulates those
    constraints; the smallest eigenvalue of that sum, normalised by the count,
    is how strongly the worst-constrained direction is held.

    Zero means every ray is parallel and the screen can slide freely along them
    -- ``z_d`` is then not observable at all, however much data you take.  That
    is the default state of this bench: a perfectly flat array viewed by a
    distant camera gives parallel rays.  Break it by tilting mirrors (the
    motorised node is ideal, stepping through known positions) or by using a
    camera close enough for perspective to spread the rays.
    """
    d = np.asarray(directions, dtype=np.float64).reshape(-1, 3)
    d = d / np.linalg.norm(d, axis=1, keepdims=True)
    acc = np.zeros((3, 3))
    for r in d:
        acc += np.eye(3) - np.outer(r, r)
    return float(np.linalg.eigvalsh(acc).min() / len(d))


# --------------------------------------------------------------------------
# Estimation
# --------------------------------------------------------------------------

@dataclass
class PoseEstimate:
    """Result of a calibration, with the diagnostics that decide if you trust it."""

    pose: ScreenPose
    rms_mm: float                  # residual distance from screen points to their rays
    pitch_scale: float             # |r1|,|r2| before orthonormalising; 1.0 = pitch correct
    conditioning: float            # ray_conditioning of the input
    n_observations: int
    refined: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def pitch_error_ppm(self) -> float:
        return (self.pitch_scale - 1.0) * 1e6

    def report(self) -> str:
        lines = [str(self.pose),
                 f"  observations   {self.n_observations}"
                 f"{' (Gauss-Newton refined)' if self.refined else ' (linear only)'}",
                 f"  ray residual   {self.rms_mm * 1000:.2f} um RMS",
                 f"  pitch scale    {self.pitch_scale:.6f}  "
                 f"({self.pitch_error_ppm:+.0f} ppm vs the assumed screen pitch)",
                 f"  conditioning   {self.conditioning:.4f}"]
        lines += [f"  WARNING: {w}" for w in self.warnings]
        return "\n".join(lines)


def _orthonormalise(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, float]:
    """Nearest orthonormal pair to two nominally orthonormal columns.

    Returns the 3x3 rotation and the mean length of the inputs, which is the
    scale the data implies and therefore the screen-pitch check.
    """
    scale = 0.5 * (np.linalg.norm(a) + np.linalg.norm(b))
    if scale == 0:
        raise ValueError("degenerate solution: screen axes collapsed to zero length")
    m = np.column_stack([a / scale, b / scale])
    u, _, vt = np.linalg.svd(m, full_matrices=False)
    m = u @ vt                                     # closest orthonormal 3x2
    r3 = np.cross(m[:, 0], m[:, 1])
    return np.column_stack([m[:, 0], m[:, 1], r3]), scale


def _residuals(pose: ScreenPose, P: np.ndarray, r: np.ndarray,
               q: np.ndarray) -> np.ndarray:
    """Component of (screen point - mirror point) perpendicular to each ray."""
    Q = pose.R[:, 0] * q[:, 0:1] + pose.R[:, 1] * q[:, 1:2] + pose.t
    d = Q - P
    along = np.einsum("ij,ij->i", d, r)[:, None] * r
    return (d - along).ravel()


def _rodrigues(w: np.ndarray) -> np.ndarray:
    theta = float(np.linalg.norm(w))
    if theta < 1e-12:
        return np.eye(3)
    k = w / theta
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + np.sin(theta) * K + (1.0 - np.cos(theta)) * (K @ K)


def estimate_screen_pose(mirror_points: np.ndarray, ray_directions: np.ndarray,
                         screen_coords: np.ndarray, refine: bool = True,
                         max_iter: int = 30) -> PoseEstimate:
    """Recover the screen pose from reflected-ray correspondences.

    Parameters
    ----------
    mirror_points
        (N, 3) points on the mirrors where the camera rays land, in mm.
    ray_directions
        (N, 3) directions the rays travel *after* reflecting, toward the screen.
        Normalised internally; they must point at the screen, not away from it.
    screen_coords
        (N, 2) screen coordinates in **millimetres** that the decoded absolute
        pattern says each ray reaches.  Millimetres, not pixels -- convert with
        your assumed pitch, and ``pitch_scale`` in the result will tell you how
        wrong that assumption was.
    """
    P = np.asarray(mirror_points, dtype=np.float64).reshape(-1, 3)
    r = np.asarray(ray_directions, dtype=np.float64).reshape(-1, 3)
    q = np.asarray(screen_coords, dtype=np.float64).reshape(-1, 2)
    if not (len(P) == len(r) == len(q)):
        raise ValueError(f"ragged inputs: {len(P)} points, {len(r)} rays, {len(q)} coords")
    n = len(P)
    if n < 4:
        raise ValueError(f"need at least 4 correspondences to fix 6 pose DOF, got {n}")

    lengths = np.linalg.norm(r, axis=1)
    if np.any(lengths == 0):
        raise ValueError("ray directions contain a zero vector")
    r = r / lengths[:, None]

    warnings: list[str] = []
    cond = ray_conditioning(r)
    if cond < 1e-3:
        warnings.append(
            f"rays are near-parallel (conditioning {cond:.2e}): distance along them is "
            "unobservable, so z_d from this data is meaningless -- tilt mirrors "
            "through known positions to spread the rays")
    elif cond < 0.05:
        warnings.append(
            f"weak ray spread (conditioning {cond:.3f}): z_d is only loosely "
            "constrained; expect the depth to be the least reliable number here")

    # ---- linear stage: least squares on [r1, r2, t] ------------------------
    A = np.zeros((3 * n, 9))
    b = np.zeros(3 * n)
    eye = np.eye(3)
    for i in range(n):
        M = eye - np.outer(r[i], r[i])
        sl = slice(3 * i, 3 * i + 3)
        A[sl, 0:3] = M * q[i, 0]
        A[sl, 3:6] = M * q[i, 1]
        A[sl, 6:9] = M
        b[sl] = M @ P[i]

    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    R, scale = _orthonormalise(sol[0:3], sol[3:6])
    pose = ScreenPose(R=R, t=sol[6:9])

    # ---- nonlinear stage: Gauss-Newton on all six DOF ---------------------
    refined = False
    if refine:
        params = np.zeros(6)                       # [omega (3), delta t (3)]
        R0, t0 = pose.R.copy(), pose.t.copy()

        def build(p: np.ndarray) -> ScreenPose:
            return ScreenPose(R=_rodrigues(p[:3]) @ R0, t=t0 + p[3:])

        cost = float(np.sum(_residuals(pose, P, r, q) ** 2))
        for _ in range(max_iter):
            res = _residuals(build(params), P, r, q)
            J = np.zeros((res.size, 6))
            for k in range(6):
                step = np.zeros(6)
                step[k] = 1e-7
                J[:, k] = (_residuals(build(params + step), P, r, q) - res) / 1e-7
            try:
                delta, *_ = np.linalg.lstsq(J, -res, rcond=None)
            except np.linalg.LinAlgError:                        # pragma: no cover
                break
            trial = params + delta
            new_cost = float(np.sum(_residuals(build(trial), P, r, q) ** 2))
            if not np.isfinite(new_cost) or new_cost > cost:
                break
            params, improvement, cost = trial, cost - new_cost, new_cost
            refined = True
            if improvement < 1e-18:
                break
        pose = build(params)

    res = _residuals(pose, P, r, q).reshape(-1, 3)
    rms = float(np.sqrt(np.mean(np.sum(res ** 2, axis=1))))

    if abs(scale - 1.0) > 0.01:
        warnings.append(
            f"screen axes came out {scale:.4f}x unit length: the assumed screen pixel "
            f"pitch looks wrong by {(scale - 1.0) * 100:+.2f}%, which is a direct scale "
            "error on every angle you report")

    return PoseEstimate(pose=pose, rms_mm=rms, pitch_scale=scale, conditioning=cond,
                        n_observations=n, refined=refined, warnings=warnings)


# --------------------------------------------------------------------------
# What SMOTS actually consumes
# --------------------------------------------------------------------------

def screen_geometry(pose: ScreenPose, array_origin=(0.0, 0.0, 0.0),
                    array_normal=(0.0, 0.0, 1.0)) -> dict:
    """Turn a calibrated pose into the numbers Eq. (6) needs.

    ``z_d`` is the PERPENDICULAR distance from ``array_origin`` to the screen
    plane -- not the distance to the screen's origin, which for a tilted screen
    is a different and larger number.  ``tilt_deg`` is how far the screen is
    from parallel with the array.  Eq. (6) assumes parallel, so a non-zero tilt
    is an error term you are otherwise absorbing silently into every angle.
    """
    o = np.asarray(array_origin, dtype=np.float64).reshape(3)
    a = np.asarray(array_normal, dtype=np.float64).reshape(3)
    a = a / np.linalg.norm(a)
    n = pose.normal / np.linalg.norm(pose.normal)

    z_d = abs(float((pose.t - o) @ n))
    cos_between = abs(float(a @ n))
    tilt = float(np.degrees(np.arccos(np.clip(cos_between, -1.0, 1.0))))
    return {
        "z_d_mm": z_d,
        "tilt_deg": tilt,
        "screen_normal": n,
        "parallel": tilt < 0.5,
        "note": ("screen is effectively parallel to the array"
                 if tilt < 0.5 else
                 f"screen is {tilt:.2f} deg off parallel -- SMOTS Eq. (6) assumes "
                 "parallel, so this bleeds into the reported angles"),
    }


# --------------------------------------------------------------------------
# Synthetic correspondences, for testing and for trying the method out
# --------------------------------------------------------------------------

def synthetic_observations(pose: ScreenPose, mirror_centres: np.ndarray,
                           mirror_normals: np.ndarray, samples: int = 3,
                           half_mm: float = 8.0, view_dir=(0.0, 0.0, -1.0),
                           noise_mm: float = 0.0,
                           rng: np.random.Generator | None = None):
    """Generate correspondences from a known screen pose.

    Rays come in along ``view_dir`` (orthographic), reflect off each mirror, and
    are intersected with the screen plane to give the screen coordinate the
    camera would decode there.

    Returns ``(points, directions, coords)`` ready for
    :func:`estimate_screen_pose`.
    """
    rng = rng or np.random.default_rng(0)
    centres = np.asarray(mirror_centres, dtype=np.float64).reshape(-1, 3)
    normals = np.asarray(mirror_normals, dtype=np.float64).reshape(-1, 3)
    if len(centres) != len(normals):
        raise ValueError("one normal per mirror centre is required")
    u = np.asarray(view_dir, dtype=np.float64).reshape(3)
    u = u / np.linalg.norm(u)

    offsets = np.linspace(-half_mm, half_mm, samples)
    P, D, Q = [], [], []
    for centre, raw_n in zip(centres, normals):
        n = raw_n / np.linalg.norm(raw_n)
        refl = u - 2.0 * np.dot(u, n) * n
        for dx in offsets:
            for dy in offsets:
                p = centre + np.array([dx, dy, 0.0])
                denom = float(refl @ pose.normal)
                if abs(denom) < 1e-9:
                    continue                       # ray runs parallel to the screen
                lam = float((pose.t - p) @ pose.normal) / denom
                if lam <= 0:
                    continue                       # screen is behind the mirror
                hit = p + lam * refl
                rel = hit - pose.t
                q = np.array([rel @ pose.R[:, 0], rel @ pose.R[:, 1]])
                if noise_mm:
                    q = q + rng.normal(0.0, noise_mm, 2)
                P.append(p)
                D.append(refl)
                Q.append(q)
    if not P:
        raise ValueError("no valid rays: check that the screen is in front of the mirrors")
    return np.array(P), np.array(D), np.array(Q)


__all__ = [
    "ScreenPose", "PoseEstimate", "householder", "reflect_pose",
    "ray_conditioning", "estimate_screen_pose", "screen_geometry",
    "synthetic_observations",
]
