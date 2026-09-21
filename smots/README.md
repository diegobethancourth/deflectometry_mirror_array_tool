# SMOTS — reference implementation

Sheared-Fourier tilt retrieval for a segmented mirror array, implementing

> H. Choi, I. Trumper, M. Dubin, W. Zhao and D. W. Kim,
> *"Simultaneous angular alignment of segmented mirrors using sinusoidal pattern
> analysis"*, Proc. SPIE **10377**, 103770G (2017).

Built for the ASU bench: a 3×3 array of 1″ square mirrors with the centre node
(M5) motorised by 2× MPIA10 inertia actuators on a KIM101 controller.

## For a reviewer

Nothing here needs hardware. From a fresh clone:

```bash
pip install -r requirements.txt

pytest                  # 63 tests, ~2 s
python demo.py          # narrated walkthrough of the retrieval
python demo.py calib    # screen-pose calibration through the mirrors
```

`pytest` works from the repository root or from this directory. To use the
package from elsewhere, `pip install -e .` first.

**Where to look, in order.** `analysis.py` is the core — Eqs. (1)–(4) of the
paper, plus the phase estimator this implementation prefers and why.
`geometry.py` turns phase into an angle. `pipeline.py` is the whole chain in one
function, and is the shortest way to see how the pieces connect. `simulate.py`
is the ray-traced forward model that makes the tests meaningful: it renders the
image the camera *would* record from a commanded tilt, so the retrieval can be
checked against ground truth rather than against itself.

**What is and is not established.** The algorithm is validated end to end against
that synthetic model, including simultaneous multi-segment retrieval,
common-mode rejection and the 2π unwrap. It has **not** been run against real
camera frames — that waits on the bench. Five hardware values are marked
`UNVERIFIED` in `hardware.py`; two of them, the screen pixel pitch and the
mirror-to-screen distance, scale every angle the code reports and must be
measured before any number here means anything. The three sign conventions
below are the most likely source of a silently wrong result.


## How the measurement works

SMOTS is **not** phase-shifting deflectometry. Nothing on the screen moves
during a measurement. One sinusoidal pattern is displayed, one reference image
is captured, and every later image is compared against that reference:

| Step | Where |
|---|---|
| Subtract the reference → *sheared pattern* | `analysis.shear_ratio` |
| FFT both, take the ratio at the carrier bin | `analysis.shear_ratio` |
| Ratio → signed phase | `analysis.phase_complex` |
| Phase → shift on the screen, Eq. (5) | `analysis.shift_mm` |
| Two carriers → break the 2π ambiguity | `analysis.unwrap_two_carrier` |
| Shift → tilt angle, Eq. (6) | `geometry.tilt_from_shift` |
| One aperture per segment, all at once | `apertures.grid_apertures` |

Because the phase is recovered as a *fraction of a period*, and a fraction of a
period is invariant under magnification, **the camera magnification never enters
the calculation.** The carrier is located in the camera's own spectrum; only the
physical period on the screen is needed to convert to millimetres.

```python
from smots import Bench, PatternSpec, reference_frame, render_frame
from smots import grid_apertures, measure

bench = Bench()
spec  = PatternSpec(periods_px=(30.0,), axes="xy")

ref = reference_frame(bench, spec)                        # flat, all nodes
mea = render_frame(bench, spec, tilts_x={"M5": 150e-6})    # M5 tilted 150 µrad
aps = grid_apertures(ref.image.shape, bench.array, bounds=ref.bounds)

result = measure(bench, spec, ref.image, mea.image, aps)
print(result.table())
print(result.differential("M5"))     # common array drift removed
```

## Measured performance on the synthetic bench

M5 commanded to 150 µrad, 50 trials per row, 30 px carrier at *z*<sub>d</sub> = 400 mm:

| Camera noise σ_I | Bias | RMS error |
|---|---|---|
| 0.5 DN | −0.03 µrad | **0.18 µrad** |
| 1.0 DN | +0.02 µrad | **0.34 µrad** |
| 2.0 DN | +0.06 µrad | **0.63 µrad** |
| 4.0 DN | +0.15 µrad | **1.30 µrad** |

The paper reports 0.8 µrad RMS against an autocollimator. These are synthetic
numbers from an idealised forward model — they show the *arithmetic* is sound,
not that your bench will hit them.

## Three sign conventions that will bite you

Each of these was found by a test failing against the ray-traced forward model,
not by reading the paper. Each inverts an angle silently.

1. **Eq. (2)'s exponent.** Written `exp(-i2πfΔ)`, but the standard forward
   transform (and `numpy.fft`) gives `exp(+i2πfΔ)` for that shift. Eq. (4) is
   immune — it only uses the magnitude — but the *sign* of every recovered shift
   flips. This module fixes the readable convention: positive phase ⇒ pattern
   displaced toward +x.
2. **Eq. (6)'s term order.** As printed it returns a *negative* angle for a
   mirror whose normal rotates toward +x. `tilt_from_shift` uses the readable
   sign; `tilt_from_shift_paper` reproduces the paper verbatim. They differ only
   in sign, and a test pins that down.
3. **Image row direction.** Camera frames store row 0 at the top, so the row
   index runs *against* world +y. Without the flip, x reads perfectly and y comes
   back inverted — which looks like a wiring fault, not a software one. See
   `measure(..., y_axis_down=True)`.

## Two limits worth knowing

**Eq. (4) throws away half the information.** It uses only the magnitude ratio,
so it returns an unsigned angle in [0, π] and needs a separate sign step. The
complex ratio carries both: `ψ = atan2(Im(S/F), 1 + Re(S/F))` is signed, spans
(−π, π], and stays well-conditioned at ψ → 0 and ψ → π, exactly where arccos has
infinite derivative. Both are implemented; `phase_complex` is the one to run.

**The unambiguous range is the LCM, not the beat period.** Two carriers agree at
solutions spaced by the least common multiple of their periods. Writing
`Pb/Pa = p/q` in lowest terms, that repeat is `(p−q) ×` the beat period, so a 4:3
pair repeats exactly at the beat while a 5:3 pair repeats at twice it.
`synthetic_period` returns the beat — deliberately conservative. Choosing periods
is a real trade: closer periods lengthen the range, but a carrier's FFT bin index
is `aperture_mm / period_mm`, so nearly equal periods land in nearly the same bin
and cannot be separated at all.

## Modules

| Module | Contents |
|---|---|
| `hardware.py` | Bench geometry and the as-built BOM values |
| `patterns.py` | Pattern generation, single and multiplexed |
| `analysis.py` | Eqs. (1)–(4), carrier location, phase, 2π unwrap |
| `geometry.py` | Eqs. (5)–(6), resolution and range helpers |
| `apertures.py` | Per-segment binary digital masks |
| `simulate.py` | Ray-traced forward model, for ground truth |
| `pipeline.py` | `measure()` — two frames in, per-node angles out |
| `calibration.py` | Mirror-based screen-pose calibration — where `z_d` should come from |

## Calibrating the screen pose through the mirrors

The error budget says screen geometry dominates everything else, and Eq. (6)
needs `z_d`. But the camera never sees the screen — only its reflection. So
`calibration.py` recovers the screen pose *through* the mirrors.

Each observation is a correspondence: a point **P** on a mirror of known normal,
the direction **r** the ray leaves in after reflecting, and the screen coordinate
**q** the decoded pattern says is seen there. The screen point lies on that ray,
which gives two constraints per observation with the ray length eliminated:

```
(I − r rᵀ)(R q + t − P) = 0
```

Solved linearly for `[r₁, r₂, t]` (the data never constrains `R`'s third column,
since `q` is planar), orthonormalised, then refined by Gauss-Newton on all six
pose degrees of freedom. Structured after the conventional linear-then-nonlinear
pattern — cf. Uhlig, *Light Field Imaging for Deflectometry*, ch. 5 — but written
from the geometry, not transcribed from it.

### A flat array cannot be calibrated at all

This is the finding worth carrying to the bench. If every mirror normal is
identical, every reflected ray is **parallel**, and (I − r rᵀ) says nothing about
position *along* those rays. `z_d` is not poorly determined — it is not
determined. No quantity of data fixes it.

Measured on the synthetic bench with 50 µm absolute decode noise, 20 trials:

| Mirror tilt spread | Conditioning | `z_d` error |
|---|---|---|
| 0° (perfectly flat) | 0.0000 | **unobservable** |
| 0.5° | 0.0004 | 0.345 mm |
| 1.0° | 0.0018 | 0.144 mm |
| 2.0° | 0.0070 | 0.078 mm |
| 4.0° | 0.0279 | 0.038 mm |
| 8.0° | 0.1064 | 0.018 mm |

So **do not try to set the nine mirrors parallel.** A few degrees of deliberate
spread across the eight reference nodes buys more calibration accuracy than any
amount of extra data at zero spread. Stepping only the motorised node helps far
less — it is one node in nine. `ray_conditioning()` reports where you are, and
the estimator refuses to be quiet when the bundle is degenerate.

### The screen pitch measures itself

If `q` is in millimetres, the recovered screen axes must come out unit length.
They do not if the assumed pixel pitch is wrong, and the deviation *is* the scale
error — on the one number the paper insists you measure under a microscope.
`PoseEstimate.pitch_scale` reports it, and a 2% error raises a warning.

### Two prerequisites

- **Absolute screen coordinates**, so unwrapped phase — a multi-frequency or
  coded sequence. The relative SMOTS tilt measurement never needs to know which
  fringe it is on; calibration does.
- **Mirror normals from somewhere else first.** This is circular, since normals
  are what SMOTS measures. Break it with the mechanical normals of the reference
  nodes (set once, stable) or an autocollimator, then calibrate, then measure.

## Before this touches hardware

Values in `hardware.py` marked **UNVERIFIED** are placeholders:

- **Measure the screen pixel pitch under a microscope.** Eq. (5) multiplies by it
  directly, so an error here is a pure scale error on every angle you report. The
  paper calls this out explicitly.
- **Measure *z*<sub>d</sub>, the mirror-to-screen distance.** Angle goes as 1/*z*<sub>d</sub>.
  The paper quotes 2020 ± 5 mm for their bench.
- **Locate the array in real frames.** `grid_apertures` assumes the array fills
  `bounds`; a misplaced aperture silently mixes two segments' signals.
- **Confirm the tilt signs** against a known actuator move before trusting them.
- **Cross-check absolute angle against an autocollimator.** SMOTS measures
  *change* from a reference; absolute numbers need absolute calibration.

The lever arm, travel and step size in `Actuator` are plausible placeholders, not
datasheet values — read the real ones off the Thorlabs drawing.
