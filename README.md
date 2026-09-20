# Deflectometry Mirror-Array Toolkit

Interactive, browser-based calculators supporting the array sizing and component
selection analysis for a deflectometry (SMOTS / PMD) setup.

Every page is a **single self-contained HTML file** — no build step, no
dependencies, no server. Open it by double-clicking, email it, or serve the
folder with GitHub Pages. All controls update the metrics, sketches and the live
mathematics panel simultaneously.

## Pages

| Page | What it answers |
|---|---|
| [`index.html`](index.html) — **Array Config** | Which mirror layout fits the screen and gives enough fringes? Six governing equations across six candidate layouts, with a ranked comparison table. |
| [`fringes.html`](fringes.html) — **Fringe Generator** | What exactly do I display on the screen? Phase-shifted sinusoid design, 1:1 pixel inspection, full-resolution PNG export and a matching Python snippet. |
| [`piezo.html`](piezo.html) — **Tilt & Actuation** | Can the mounts actually point each mirror? Per-mirror law-of-reflection solution, piezo displacement, angular resolution and range budget. |
| [`budget.html`](budget.html) — **Error Budget** | How accurate will the measurement be? Phase → slope → height propagation with each term integrated by its spatial character. |
| [`simulator.html`](simulator.html) — **SMOTS Simulator** | Does the algorithm actually work? Ray-traces the camera image, runs the full SMOTS retrieval on it live, and compares recovered tilt against commanded tilt. |
| [`smots/`](smots/) — **Python package** | The measurement algorithm for the experimental work: sheared Fourier analysis, per-segment apertures, 2π unwrapping, with a validated forward model and 40 tests. |

## Governing relations

### Array configuration

| Expression | Physical meaning |
|---|---|
| `p = W / Nₓ` | Pixel pitch: screen width ÷ horizontal pixels |
| `P_f = n × p` | Fringe pitch: pixels per fringe × pixel pitch |
| `L = n_cols × a + (n_cols − 1) × g` | Array width: mirrors + gaps |
| `N_f = L / P_f` | Fringes across array — must be ≥ 40, ≥ 60 ideal |
| `θ = 2·arctan(W_s / 2d)` | Screen angular FOV: the array must fit inside |
| `AOV = 2·arctan(sensor / 2f)` | Camera angular FOV: must cover the array at distance d |

### Fringe generation

| Expression | Physical meaning |
|---|---|
| `I_k(x) = A + B·cos(2πx/n − 2πk/N)` | Projected intensity, step *k* of *N* |
| `φ = arctan2( Σ I_k sin(2πk/N), Σ I_k cos(2πk/N) )` | N-step phase retrieval, wrapped to (−π, π] |
| `σ_φ = √(2/N) · σ_I / B` | Phase uncertainty from camera noise |
| `I_out = 255·(I_lin/255)^(1/γ)` | Gamma pre-compensation, so the emitted irradiance is sinusoidal |

### Tilt and actuation

| Expression | Physical meaning |
|---|---|
| `û = (M − C)/‖M − C‖`, `v̂ = (S − M)/‖S − M‖` | Incident and reflected ray directions per mirror |
| `n̂ ∝ v̂ − û` | Law of reflection: the normal bisects the two rays |
| `θ_piezo = θ − θ_base` | The baseplate carries the common fold; the piezos supply the differential |
| `Δ = L·tanθ` | Actuator displacement at lever arm *L* from the pivot |
| `δθ = δΔ / L` | Angular resolution from the actuator step size |

### Error budget

| Expression | Physical meaning |
|---|---|
| `δx_s = σ_φ · P_f / 2π` | Screen-point error from phase noise |
| `δs = δx_s / 2d` | Slope error — a slope change δs deflects the reflected ray by 2δs |
| `δz = δs·√(L·Δx)` | Height from *random* slope error (random walk) |
| `δz = δs·L` | Height from *correlated figure* error (coherent integration) |
| `δz = sag·δd/d` | Height from a *scale* error in the screen distance |

A uniform screen-pose offset produces the same slope error everywhere — that is a
pure tilt, so the reconstruction's piston-and-tilt fit removes it exactly. The
budget page classifies every term this way rather than applying one rule to all of
them.

## The SMOTS algorithm

[`smots/`](smots/) implements the retrieval described in

> H. Choi, I. Trumper, M. Dubin, W. Zhao and D. W. Kim, *"Simultaneous angular
> alignment of segmented mirrors using sinusoidal pattern analysis"*,
> Proc. SPIE **10377**, 103770G (2017).

```bash
cd smots && python demo.py && python -m pytest tests/ -q
```

SMOTS is not phase-shifting deflectometry: one pattern is displayed, one
reference frame is captured, and every later frame is compared against it. The
shift is recovered from the *sheared* pattern in the Fourier domain, per segment,
all segments at once. Because the phase is measured as a fraction of a period —
invariant under magnification — the camera's scale never enters the calculation.

On the synthetic bench the implementation recovers a 150 µrad tilt to **0.63 µrad
RMS** at 2 DN camera noise; the paper reports 0.8 µrad RMS against an
autocollimator. See [`smots/README.md`](smots/README.md) for the three sign
conventions that will silently invert your angles if you get them wrong.

## Notes on the defaults

The fixed hardware values describe the as-built 9-node TR1.5/PH1.5 hybrid from
the 18 Sep 2026 weekly report: 25.4 mm PFSQ10-03-G01 mirrors on Thorlabs KMSR
kinematic mounts, a 344 mm / 3840 px panel (89.6 µm pixel pitch), and the centre
node (M5) motorised with 2× MPIA10 actuators on a KIM101 controller. A KIM101
drives four channels and a tip/tilt node consumes two, so **at most two nodes can
be motorised per controller** — the tilt page enforces that budget.

**Mount- and actuator-specific numbers — lever arm, tilt limit, travel and step
size — are editable inputs, not verified specifications.** Likewise the screen
pixel pitch and the mirror-to-screen distance: both scale every angle the
algorithm reports, and both need measuring rather than assuming. Read the
hardware numbers off the datasheet drawing before committing to a design.

## Authors

Diego Bethancourth — Arizona State University, School of Manufacturing Systems
and Networks. Advisor: Dr. Xiangyu Guo.

System sketch referenced from Huang et al. 2018, Fig. 1 & 3.
