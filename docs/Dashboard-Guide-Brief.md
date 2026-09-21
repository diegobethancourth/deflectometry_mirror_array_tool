# Deflectometry Mirror-Array Toolkit — Context Brief

**Purpose of this file.** It is a self-contained briefing to paste into a fresh
AI chat so that chat can (a) teach me the dashboard quickly and (b) write a
formal user guide for it. Everything needed is here — no repository access
required.

**Repository:** `diegobethancourth/deflectometry_mirror_array_tool`
**Live site:** `https://diegobethancourth.github.io/deflectometry_mirror_array_tool/`
**Companion:** `docs/Deflectometry-Math-Reference.pdf` — 20 pages, 75 numbered
equations, the full derivations behind everything summarised here.

---

## Instructions for the assistant reading this

You are helping **Diego Bethancourth**, a graduate researcher at Arizona State
University (School of Manufacturing Systems and Networks, SOLAR Lab; advisor
Dr. Xiangyu Guo). He built the dashboard described below with an AI assistant
and now needs to **understand it well enough to operate it and defend it to his
advisor.**

When he asks you for a tutorial or guide:

- **Teach the physics alongside the buttons.** Every control maps to a term in a
  real optical equation. A guide that says "this slider sets the gap" is useless;
  one that says "widening the gap enlarges the array, which raises the fringe
  count but can push the outer mirrors outside the camera's field" is what he
  needs.
- **Lead with the decisions, not the interface.** The dashboard exists to answer
  five questions (§2). Organise any guide around those questions.
- **He is the author of this work and will be examined on it.** Do not
  over-simplify. Use the correct terms — slope error, phase uncertainty,
  conditioning, unambiguous range — and define them once.
- **Flag the traps.** §8 lists failure modes that produce confident wrong
  answers. These matter more than any feature tour.
- Assume he has the pages open in front of him. Concrete "set X to Y, watch Z
  change" exercises work better than prose.

Useful things he might ask you for: a one-page quick-start; a structured
multi-day learning path; a formal user manual with numbered procedures; a
viva-style question bank; a slide outline for a group meeting.

---

## 1. The research in one paragraph

A flat mirror reflects a pattern displayed on a screen into a camera. Tilt the
mirror slightly and the reflected pattern shifts. Measure that shift and you have
measured the tilt. Do it for nine mirrors at once and you can monitor a whole
segmented surface simultaneously. This is **deflectometry**; the specific method
here is **SMOTS** (Simultaneous Multi-segmented mirror Orientation Test System),
from Choi et al., *Proc. SPIE* **10377**, 103770G (2017). Diego's bench is a 3×3
array of 1-inch square mirrors standing in as a surrogate segmented surface, with
the centre mirror motorised so a known tilt can be commanded and then measured.

**Key distinction the guide must make:** SMOTS is *not* classical phase-shifting
deflectometry. It displays **one** pattern that never moves, captures **one**
reference image, and compares every later image against that reference. The tilt
comes from the *difference* between the two images, analysed in the Fourier
domain. That is why it is fast (~15 Hz for seven segments in the original paper)
and why it measures *change* rather than absolute orientation.

## 2. The five questions the dashboard answers

| Page | Question it answers |
|---|---|
| `index.html` — Array Config | Which mirror layout fits the screen and gives enough fringes? |
| `fringes.html` — Fringe Generator | What exactly should be displayed on the screen? |
| `piezo.html` — Tilt & Actuation | Can the mounts physically point each mirror where it needs to go? |
| `budget.html` — Error Budget | How accurate will the measurement actually be? |
| `simulator.html` — SMOTS Simulator | Does the retrieval algorithm work, end to end? |

Every page has the same layout: **controls on the left**, **six metric tiles
across the top**, a **verdict banner** that turns green/amber/red, **two
visualisations**, and a **live Mathematics panel** showing each equation with the
current numbers substituted in. Nothing is hidden in menus; everything updates
instantly.

## 3. The bench being modelled

The as-built assembly, from the 18 Sep 2026 weekly report:

| Item | Value |
|---|---|
| Mirrors | 9 × PFSQ10-03-G01, 25.4 mm square, λ/10 flatness |
| Array | 3×3 with 3 mm gaps → 82.2 × 82.2 mm |
| Mounts | Thorlabs KMSR Ø1″ kinematic |
| Actuation | 2 × MPIA10 piezo inertia actuators on the **centre node (M5) only** |
| Controller | KIM101, **4 channels** |
| Reference nodes | 8 × TR1.5 / PH1.5, height set by hand |
| Screen | 344 mm wide, 3840 px → 89.6 µm pitch |

**Node numbering** runs in reading order, so M1 is top-left and **M5 is the
centre** — matching the mechanical drawings.

**A hard constraint worth teaching early:** a tip/tilt node needs 2 controller
channels, and a KIM101 has 4. So **one controller can drive at most two
motorised mirrors.** The Tilt & Actuation page enforces this.

---

## 4. Page-by-page reference

Control IDs are given in braces `{#id}` in case the guide needs to reference them
precisely. Ranges and defaults below are exact.

### 4.1 Array Config (`index.html`)

Sizes the array against the screen and the camera.

**Controls**

*Array configuration*
- Mirror layout `{#arr}` — 1×4, 1×5, 2×4, **3×3 ★**, 2×5, 3×4
- Mirror gap `{#gap}` — 1–8 mm, default 3
- Screen–mirror distance *d* `{#dist}` — 200–500 mm, default 300
- Pixels per fringe *n* `{#ppf}` — 8–30, default 15

*Camera & lens*
- Sensor format `{#sensor}` — 1/4″ through APS-C, default **1/2″ (8.0 × 6.0 mm)**
- Focal length `{#focal}` — 6–75 mm, default 25

*Fixed parameters* — a read-only panel listing the mirror, screen, mount and
piezo hardware.

**Metric tiles:** Array width · Array height · Fringe pitch · **Fringes N_f** ·
Screen FOV · Camera AOV

**How to read it.** The headline number is **N_f, fringes across the array**.
Target ≥ 60; below about 40 the measurement degrades. It comes from dividing the
array width by the fringe pitch, so a finer fringe (smaller *n*) raises it.

The **Camera AOV** tile turns red when the lens cannot cover the array at that
distance — with the defaults it does, which is a genuine finding, not a bug: a
25 mm lens on a 1/2″ sensor sees only 96 × 72 mm at 300 mm, which is marginal for
an 82 mm array. Shorten the focal length or use a larger sensor.

**Visuals:** *Array Footprint* (top view of the mirror grid) and *PMD Optical
System* (side view showing the probe ray, the reflected ray, the 2α angle and the
screen). The comparison table at the bottom ranks all six layouts at once.

### 4.2 Fringe Generator (`fringes.html`)

Designs the sinusoid to display, and exports it.

**Controls**

*Pattern*
- Orientation `{#orient}` — vertical fringes (phase along x) or horizontal
- Pixels per fringe *n* `{#ppf}` — 4–60, default 15
- Phase steps *N* `{#steps}` — 3, **4 ★**, 5, 8, 12, 16
- Displayed step *k* — clickable dots, one per step

*Intensity*
- Bias *A* `{#bias}` — 60–200 grey levels, default 128
- Modulation *B/A* `{#mod}` — 0.10–1.00, default 0.90
- Pre-compensate display gamma `{#gon}` — checkbox, default **off**; γ slider 1.0–3.0, default 2.2
- Camera noise σ_I `{#noise}` — 0.2–8 DN, default 2.0

*Screen & array*
- Screen resolution `{#res}` — UHD ★ / QHD / FHD / HD
- Screen width *W* `{#sw}` — default 344 mm
- Mirror layout `{#arr}`, mirror gap `{#gap}` — as above

*Export buttons:* **PNG — step k** · **PNG — all N steps** · **Copy Python**

**Metric tiles:** Fringe pitch · Fringes/screen · **Fringes/array** · Phase step ·
**Phase noise σ_φ** · Screen error

**How to read it.** Two things must hold at once. **Sampling:** keep *n* ≥ 8
pixels per fringe, or the panel renders a stepped near-square wave whose harmonics
leak into the retrieved phase. **Coverage:** keep fringes/array ≥ 60. These pull
in opposite directions, and finding the window where both hold is the point of
the page.

Watch for the **clipping** warning: if *A* ± *B* leaves the 0–255 range the
sinusoid is truncated, which *biases* the phase rather than just adding noise.

**Visuals:** *Screen preview* (whole panel), *1:1 pixel crop* (true screen pixels
— this is where undersampling becomes visible), *Intensity profile* (all N steps
plotted over two fringes), and a copyable *Python snippet* that regenerates the
exact pattern with numpy and PIL.

### 4.3 Tilt & Actuation (`piezo.html`)

Solves where each mirror must point and whether the hardware can get it there.

**Controls**

*Array* — layout `{#arr}`, gap `{#gap}`

*Motorised nodes*
- Which mirrors are motorised `{#preset}` — **Centre node only ★**, Four corners, Centre row, All nodes, None
- Actuator `{#act}` — **MPIA10 ★**, PIA13, PIA25, Custom
- Controller `{#chan}` — **KIM101 4 channels ★**, 2 × KIM101 (8), Ignore budget

*Geometry*
- Camera standoff *z* `{#cz}` — 150–1500 mm, default 800
- Camera height offset *y* `{#cy}` — −400 to +400 mm, default +180
- Screen distance *z* `{#sz}` — 150–800 mm, default 400
- Screen height offset *y* `{#sy}` — −500 to +200 mm, default −190

*Mount & actuator*
- Lever arm *L* `{#lev}` — default 19.05 mm
- Mount tilt limit ±θ `{#tlim}` — 1–12°, default 4
- Actuator travel, total `{#trav}` — default 10 mm
- Actuator step size `{#stp}` — default 20 nm
- Baseplate pre-tilted to array mean `{#base}` — checkbox, default **on**

**Metric tiles:** Max piezo tilt · **Motorised (n of N, channels used)** · Max Δ
actuator · Angular resolution · Screen walk per step · Range used

**Interaction:** **click any mirror in the tilt map — or any row in the table — to
toggle it between motorised and manual.**

**The central concept: the baseplate split.** Every mirror needs a large, nearly
identical fold angle to route the camera's line of sight onto the screen, plus a
small differential that varies across the array. The common part is set *once,
mechanically*, by how the baseplate is bolted. Only the differential has to come
from the piezos. With the checkbox on, the page shows ~6.3° of baseplate tilt and
only ~0.03–3° of piezo demand; switch it off and the piezos are charged for the
whole fold, which makes a perfectly feasible design look impossible. **A guide
must explain this or the page will be misread.**

Motorised and manual nodes are checked against *different* limits: a motorised
node is capped by whichever binds first, mount tilt or actuator travel; a manual
node only by the mount's own adjuster range, since nothing is driving it.

**Visuals:** *Required tilt map* (front view, green + P = motorised, dashed grey =
manual, shaded by range utilisation) and *Fold geometry* (side elevation with the
probe and reflected rays for the centre column).

### 4.4 Error Budget (`budget.html`)

Propagates every uncertainty into a slope error, then into a height error.

**Controls**

*Geometry* — layout, gap, screen–mirror distance *d* `{#dist}` (150–800, default
300), camera pixels across the array `{#campx}` (default 2448)

*Phase measurement* — pixels per fringe `{#ppf}`, phase steps `{#steps}`, camera
noise σ_I `{#noise}`, fringe modulation *B* `{#modB}` (20–127 DN, default 115),
frames averaged *M* `{#avg}` (1–32, default 1)

*Calibration*
- Screen lateral calibration δx `{#cal}` — 0–1 mm, default **0.05**
- Screen distance uncertainty δd `{#dd}` — 0–5 mm, default **0.5**
- Screen planarity residual `{#plan}` — 0–0.5 mm, default **0.02**
- Camera registration `{#reg}` — 0–3 px, default 0.3
- Typical surface slope *s* `{#slope}` — 0.1–30 mrad, default 5

*Spec*
- Slope target `{#starget}` — 1–200 µrad RMS, default **50**
- Remove piston & tilt in reconstruction `{#lowo}` — checkbox, default **on**
- Wavelength λ `{#lam}` — default 550 nm

**Metric tiles:** Phase noise σ_φ · Screen point error · **Slope error (RSS)** ·
**Slope margin** · Height error δz · vs λ/10

**The concept that makes this page worth studying: spatial character.** Four
error terms do *not* share one propagation rule.

| Term | Character | Integrates into height as |
|---|---|---|
| Phase noise | **random** — uncorrelated pixel to pixel | δs·√(L·Δx) — averages down |
| Screen pose offset | **tilt-like** — uniform across the aperture | **zero** — it *is* a tilt, removed exactly by the low-order fit |
| Screen planarity | **figure** — correlated across the aperture | δs·L — integrates coherently, ~50× worse |
| Distance error | **scale** — proportional to the true slope | sag·δd/d |

Treating all four the same way is a common and expensive mistake. With the
defaults, **screen planarity dominates at ~93 % of the slope variance** — phase
noise is a rounding error beside it. That is the page's main finding and it drives
where effort should go.

**Also teach:** deflectometry measures *slope* directly; height is integrated and
assumption-dependent. The page treats slope-vs-target as the primary verdict and
height-vs-λ/10 as secondary, because reaching λ/10 in absolute height demands
screen geometry known to a few micrometres.

**Visuals:** *Slope-error contributions* (horizontal bars, share of variance) and
*Propagation chain* (fringe → phase → slope → height, with the multiplier on each
arrow).

### 4.5 SMOTS Simulator (`simulator.html`)

Ray-traces the camera image, then runs the real retrieval on it and compares
recovered tilt against commanded tilt. This is the page that proves the algorithm
works.

**Controls**

*Tilt a node*
- Selected mirror `{#sel}` — M1…M9
- θx `{#tx}` — −600 to +600 µrad, default +150 (shifts fringes in x)
- θy `{#ty}` — −600 to +600 µrad, default 0
- Buttons: **+1 actuator step** · **−1 step** · **Random all** · **Reset**

*Pattern & bench*
- Carrier period `{#per}` — 10–60 screen px, default 30
- Screen distance *z_d* `{#zd}` — 150–900 mm, default 400
- Camera noise σ_I `{#noise}` — 0–8 DN, default 1.0
- Mirror layout `{#arr}` — 1×4, 2×4, **3×3 ★**, 3×4

*View*
- Right panel shows `{#view}` — **Sheared pattern**, Reference frame, Carrier spectrum

**Metric tiles:** Carrier · Screen shift · **Commanded** · **Recovered** ·
**Error** · Unambiguous range

**Interaction:** click a mirror in the camera view, or a table row, to select it.

**The single most instructive thing in the whole toolkit:** set the right panel to
**Sheared pattern** with only M5 tilted. Eight mirrors go uniformly grey — nothing
moved there, so the difference is zero — and only M5 carries fringes. That picture
*is* the method: subtracting the reference leaves only what changed.

**Suggested demonstrations**

1. Default state → commanded 150.0 µrad, recovered ≈ 150.4, error ≈ 0.4 µrad.
2. Set noise to 0 → error drops to ~0.04 µrad. The retrieval is essentially exact; noise is the limit.
3. Press **+1 actuator step** → tilt moves by ~1.05 µrad, and the retrieval still resolves it.
4. Set carrier period to 10 px and *z_d* to 900 mm, then push θx past ~250 µrad → the
   **Error tile reads "wrap"** and the recovered value folds back. This is the 2π
   ambiguity made visible, and it is the reason multiplexed patterns exist.

**Visuals:** *Simulated camera view* (ray-traced, clickable) and one of the three
right-hand views.

---

## 5. Mathematical spine

Full derivations are in `docs/Deflectometry-Math-Reference.pdf`. The minimum to
understand the dashboard:

```
p    = W / Nx                          screen pixel pitch
Pf   = n · p                           fringe pitch on the screen
L    = nc·a + (nc−1)·g                 array width
Nf   = L / Pf                          fringes across the array (target ≥ 60)

S(f) = (e^{iψ} − 1)·F(f)               the sheared pattern, the heart of SMOTS
ψ    = arctan2( Im(S/F), 1 + Re(S/F) ) signed phase from the complex ratio
Δ    = (ψ / 2π) · Pf                   phase fraction → millimetres on the screen
θ    = ½ · arctan(Δ / z_d)             tilt angle — the ½ is the physics

n̂    ∝ v̂ − û                          law of reflection, solved for the normal
Δ    = L · tan θ                       actuator displacement at lever arm L
δθ   = δΔ / L                          angular resolution per actuator step

δs   = δx_s / (2d)                     slope error from a screen-position error
δz   = δs·√(L·Δx)  or  δs·L            height, depending on spatial character
```

**Two facts that explain most of the behaviour:**

1. **The factor of ½ (and its twin, the 2).** Rotating a mirror by θ swings the
   reflected ray by **2θ**. So the observed motion is twice the angle being
   measured — which is why deflectometry is sensitive, and why every
   screen-position error divides by 2*d* to become a slope error.
2. **Phase is measured as a fraction of a period**, and a fraction of a period is
   invariant under magnification. That is why the camera's scale never enters the
   calculation and why the method is robust to an uncalibrated imaging system.

---

## 6. Suggested learning order

**First hour — build intuition.** Open the **Simulator**. Tilt M5 and watch its
fringes move. Switch to the Sheared view and see the other eight go blank. Press
+1 actuator step. Turn noise up and down. You will understand the method before
touching an equation.

**Second — the design chain.** **Array Config** → what fits. **Fringe Generator**
→ what to display. **Tilt & Actuation** → can the hardware point it. Each page's
Mathematics panel shows its equations with live numbers, so read that panel while
moving sliders.

**Third — the hard part.** **Error Budget**. Slower going, but it is where the
real engineering decisions live. Start by moving *screen planarity* and watching
the bar chart, then the others, and see which actually matter.

**Fourth — depth.** The math reference PDF, section by section, alongside the page
that implements each one.

---

## 7. Beyond the dashboard

A Python package `smots/` in the same repository implements the retrieval for the
real experiment (numpy only, 63 tests). Modules: `analysis.py` (sheared Fourier),
`geometry.py` (phase → angle), `apertures.py` (per-segment masks), `pipeline.py`
(two frames in, per-node angles out), `simulate.py` (ray-traced forward model),
`calibration.py` (screen-pose calibration), `hardware.py` (bench configuration).
Run `python demo.py` and `python demo.py calib` for narrated walkthroughs.

Measured on the synthetic bench: a 150 µrad tilt recovered to **0.63 µrad RMS** at
2 DN camera noise. The original paper reports 0.8 µrad RMS against an
autocollimator.

---

## 8. Traps — things that give confident wrong answers

These deserve their own section in any guide.

1. **Three sign conventions.** The published Eq. (2) uses an exponent sign opposite
   to the standard Fourier transform; the published Eq. (6) returns a negative angle
   for a normal rotating toward +x; and camera frames store row 0 at the top, so the
   row index runs *against* world +y. Each one inverts an angle while leaving every
   magnitude, residual and consistency check untouched. **Check them on the bench by
   commanding a known actuator move and confirming the sign.**

2. **A perfectly flat array cannot be calibrated.** If every mirror normal is
   identical, every reflected ray is parallel, and the screen distance *z_d* becomes
   mathematically unobservable — not merely noisy. The counter-intuitive remedy:
   **do not set the eight reference mirrors parallel.** A few degrees of deliberate
   spread is what makes depth measurable at all.

3. **The 2π ambiguity.** A single carrier wraps beyond ±Pf/(4·z_d). Past that the
   answer folds back and looks perfectly plausible. The simulator's "wrap" warning
   demonstrates it.

4. **Unverified inputs.** Five numbers scale the results and are placeholders, not
   datasheet values: screen pixel pitch, mirror-to-screen distance *z_d*, mount
   lever arm, actuator travel, actuator step size. The first two scale **every**
   reported angle. They must be measured.

5. **Don't quote height accuracy as the headline.** Slope is what deflectometry
   measures; height is integrated and assumption-dependent.

---

## 9. Glossary

| Term | Meaning |
|---|---|
| **Deflectometry** | Measuring a specular surface by what it reflects, rather than by touching it |
| **SMOTS** | Simultaneous Multi-segmented mirror Orientation Test System — the method used here |
| **Fringe** | One period of the sinusoidal pattern on the screen |
| **Fringe pitch (Pf)** | Physical period of that pattern, in mm |
| **Phase** | Position within a fringe, in radians; the raw measurement |
| **Sheared pattern** | Measured image minus reference image — what SMOTS analyses |
| **Digital aperture** | A per-mirror mask; how nine segments are solved from one frame |
| **Slope error (δs)** | Angular error of the measured surface normal — the primary figure of merit |
| **Tip/tilt** | The two rotational degrees of freedom of a mirror |
| **Baseplate split** | Separating the common fold angle (mechanical) from the differential (piezo) |
| **Conditioning** | How well the data constrains a quantity; zero means unobservable |
| **Unambiguous range** | How far a tilt can go before the phase wraps and folds back |
| **Common-mode rejection** | Subtracting motion shared by all segments to isolate one mirror's real change |
| **µrad** | Microradian, 10⁻⁶ rad. Tilts here are tens to hundreds of µrad |
| **DN** | Digital number — one grey level of camera output |

---

*Diego Bethancourth · Advisor: Dr. Xiangyu Guo · SOLAR Lab · School of
Manufacturing Systems and Networks · Arizona State University*
