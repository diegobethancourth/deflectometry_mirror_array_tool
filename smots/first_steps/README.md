# First steps — working up to SMOTS

Scripts written while reading Choi et al., *Proc. SPIE* **10377**, 103770G (2017),
in the order the understanding actually has to be built. Each one is standalone,
needs only numpy, and answers one question before the next is attempted.

| Script | Question it answers |
|---|---|
| `01_shear_theorem.py` | Does subtracting two shifted sinusoids really encode the shift? |

```bash
python 01_shear_theorem.py
```

---

## Talking points for the advisor meeting

### The one idea to get across

> *"The paper rests on a single non-obvious claim: if you subtract two copies of
> the same sinusoid offset by Δ, the amplitude of what's left tells you Δ.
> Before writing anything else, I wanted to check that claim in one dimension,
> with a shift I already knew the answer to."*

That is the whole pitch. Everything else in SMOTS — nine mirrors, digital
apertures, tilt angles — is bookkeeping on top of it.

### What to show, in order

**1. The claim, on paper (2 minutes).** Write Eq. (1)–(3) out:

```
FT[ f(x)           ] = F(f)
FT[ f(x + Δ)       ] = e^{iψ} F(f)          ψ = 2πfΔ
FT[ f(x + Δ) − f(x)] = (e^{iψ} − 1) F(f)
```

A shift is a phase ramp in the Fourier domain. So the *difference* of the two
frames has the same frequency as the original, with an amplitude set entirely by
the shift. Divide one transform by the other at the carrier and what is left is
`e^{iψ} − 1`, which is just ψ.

**2. Run the script (2 minutes).** It recovers known shifts to machine
precision, then keeps pushing until it breaks.

**3. The two things the script surfaced.** These matter more than the fact that
it works:

- **Eq. (4) throws away the direction.** The paper takes the magnitude of the
  ratio, `|S/F|² = 2 − 2cos ψ`, and inverts it with an arccos — which is always
  positive. It cannot tell a mirror tilted left from one tilted right, so the
  paper recovers the sign separately from the imaginary part. Keeping the
  complex ratio gives the sign for free: `ψ = atan2(Im, 1+Re)`.
- **It fails beyond half a period.** At a 30 px fringe the recovery is exact up
  to ±15 px and then folds back: a commanded +16 px reads as −14. That is the 2π
  ambiguity, and it is why Sec. 3.2 introduces a second frequency.

**4. What it means for our bench.** With a 30 px fringe at *z*<sub>d</sub> = 400 mm,
the useful range is about **±1680 µrad**, and 0.1 px of shift is **11 µrad** of
mirror tilt. Those numbers come straight out of θ = Δ/(2·*z*<sub>d</sub>) — the
factor of 2 being the physics, since a mirror tilted by θ swings the reflected
ray by 2θ.

### Questions to bring

1. **Sign convention.** Eq. (2) is printed as `e^{−i2πfΔ}`, but the standard
   forward transform gives `e^{+i2πfΔ}` for that shift. Magnitudes are
   unaffected — so every numerical check still passes — but the sign of the
   recovered angle flips. Which convention do we adopt, and how do we verify it
   on the bench rather than on paper?
2. **Fringe period.** Finer fringes measure smaller angles but wrap sooner.
   What angular range does the experiment actually need? That choice sets
   everything downstream.
3. **Multiplexing.** Worth implementing the two-frequency pattern now, or only
   once we know the real range?
4. **What limits us.** Both *z*<sub>d</sub> and the screen pixel pitch scale the
   answer linearly. How accurately can we measure them, and does that — rather
   than camera noise — set our accuracy floor?

### On the rest of the repository

There is a fuller implementation in `smots/` — the nine-segment retrieval,
apertures, the 2π unwrap, screen-pose calibration, a ray-traced forward model
and a test suite. It was scaffolded quickly with AI assistance, and it is
validated against synthetic data only; it has never seen a real camera frame.

Say so plainly. The useful framing is: *"the scaffolding is further along than
my understanding, so I'm working backwards through it — here is the piece I can
derive from scratch, and here is what I want to check next."* An advisor cares
whether you can defend the method, not how fast the file count grew.

### What comes next

`02` should be the two-dimensional version — the same recovery on an image
rather than a line, with a mask around one mirror, since that is the step where
digital apertures and spectral leakage start to matter.
