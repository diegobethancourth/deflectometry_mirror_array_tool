"""
Step 1 -- Does the shear trick in the SMOTS paper actually work?

Choi et al. (SPIE 10377, 103770G) make one claim that the whole method rests on,
and it is not obvious:

    If you subtract two copies of the same sinusoid that are offset by a small
    amount, the AMPLITUDE of what is left tells you how big that offset was.

Everything else in the paper -- the digital apertures, the nine mirrors, the
tilt angles -- is bookkeeping on top of that one idea. So before writing any of
it, the first thing to check is whether that claim is true, in one dimension,
with numbers I choose and an answer I already know.

That is all this script does. No mirrors, no camera, no images. One sinusoid,
shifted by a known amount, recovered.

Run:  python 01_shear_theorem.py        (needs only numpy)
"""

import numpy as np

# ----------------------------------------------------------------------------
# Bench numbers, so this connects to the real setup rather than being abstract
# ----------------------------------------------------------------------------
SCREEN_WIDTH_MM = 344.0     # the Upperizon panel
SCREEN_PIXELS = 3840
PIXEL_PITCH_MM = SCREEN_WIDTH_MM / SCREEN_PIXELS      # 89.6 um
PERIOD_PX = 30.0                                       # pixels per fringe
PERIOD_MM = PERIOD_PX * PIXEL_PITCH_MM                 # 2.688 mm
Z_D_MM = 400.0                                         # mirror to screen

# Samples in our 1-D "camera line". Deliberately a whole number of fringe
# periods: an FFT assumes the signal repeats, so a partial period at the end
# looks like a discontinuity and smears the carrier across neighbouring bins
# ("spectral leakage"). With 512 samples the recovery is still good to ~1e-3 px,
# but with a whole number of periods it is exact -- and seeing that difference is
# worth the one-line change. Real camera frames never land on a whole period,
# which is why the full implementation applies a window function.
PERIODS_IN_WINDOW = 17
N = int(PERIODS_IN_WINDOW * PERIOD_PX)   # 510


def displayed_pattern(x, shift_px=0.0):
    """The sinusoid on the screen, sampled along a line, optionally shifted.

    A mirror tilt makes the reflected pattern appear shifted. So 'the camera
    saw the pattern move by shift_px' and 'the mirror tilted' are the same
    statement -- which is the whole trick.
    """
    return 128.0 + 100.0 * np.cos(2 * np.pi * (x + shift_px) / PERIOD_PX)


def recover_shift_px(reference, measured):
    """Recover the shift, following Eqs. (1)-(4) of the paper.

    Eq. (1)  FT[f(x)]              = F(f)
    Eq. (3)  FT[f(x+D) - f(x)]     = (e^{i.psi} - 1) . F(f)

    So dividing the transform of the DIFFERENCE by the transform of the
    REFERENCE, at the carrier frequency, leaves exactly (e^{i.psi} - 1), and
    psi is what we want.
    """
    ref = reference - reference.mean()
    sheared = (measured - measured.mean()) - ref      # <- "the sheared pattern"

    F = np.fft.fft(ref)
    S = np.fft.fft(sheared)

    # Which FFT bin is the carrier? Find it in the data rather than assuming.
    k = np.argmax(np.abs(F[1:N // 2])) + 1

    ratio = S[k] / F[k]                                # = e^{i.psi} - 1

    # The paper (Eq. 4) takes the magnitude:  |ratio|^2 = 2 - 2.cos(psi)
    #   -> psi = arccos(1 - |ratio|^2 / 2),  which has NO SIGN.
    psi_paper = np.arccos(np.clip(1 - abs(ratio) ** 2 / 2, -1, 1))

    # But the complex ratio carries the sign already:
    #   Re = cos(psi) - 1,  Im = sin(psi)
    psi_signed = np.arctan2(ratio.imag, 1 + ratio.real)

    # phase -> length: psi/2pi is a fraction of one period
    return (psi_signed / (2 * np.pi)) * PERIOD_PX, psi_paper, k


def main():
    x = np.arange(N, dtype=float)
    reference = displayed_pattern(x)        # the "before" frame

    print(__doc__.split("Run:")[0].strip())
    print("\n" + "=" * 68)
    print("SETUP")
    print("=" * 68)
    print(f"  screen pixel pitch   {PIXEL_PITCH_MM * 1000:.1f} um")
    print(f"  fringe period        {PERIOD_PX:.0f} px  =  {PERIOD_MM:.3f} mm")
    print(f"  mirror-screen z_d    {Z_D_MM:.0f} mm")

    # ------------------------------------------------------------------
    # Test 1: does it recover a shift I already know?
    # ------------------------------------------------------------------
    print("\n" + "=" * 68)
    print("TEST 1 -- recover a known shift")
    print("=" * 68)
    print("   true (px)   recovered (px)    error (px)   unsigned (paper Eq. 4)")
    for true_px in (0.5, 2.0, -3.5, 7.0, -11.0):
        measured = displayed_pattern(x, shift_px=true_px)
        got, psi_unsigned, _ = recover_shift_px(reference, measured)
        unsigned_px = psi_unsigned / (2 * np.pi) * PERIOD_PX
        print(f"   {true_px:+8.2f}      {got:+9.4f}      {got - true_px:+8.2e}"
              f"        {unsigned_px:+7.2f}")

    print("\n  It works, to machine precision.")
    print("  Note the last column: Eq. (4) gets the SIZE right but is always")
    print("  positive -- it cannot tell which way the mirror tilted. The paper")
    print("  recovers the direction separately from the imaginary part. Using")
    print("  the complex ratio directly gives the sign for free.")

    # ------------------------------------------------------------------
    # Test 2: where does it stop working?
    # ------------------------------------------------------------------
    print("\n" + "=" * 68)
    print("TEST 2 -- push it until it breaks")
    print("=" * 68)
    print("   true (px)   recovered (px)   comment")
    for true_px in (10.0, 14.0, 15.0, 16.0, 20.0, 31.0):
        measured = displayed_pattern(x, shift_px=true_px)
        got, _, _ = recover_shift_px(reference, measured)
        note = "ok" if abs(got - true_px) < 0.05 else "WRAPPED -> folded back"
        print(f"   {true_px:+8.2f}      {got:+9.3f}      {note}")

    print(f"\n  The method fails beyond half a period ({PERIOD_PX / 2:.0f} px).")
    print("  Past that, a shift is indistinguishable from itself minus one whole")
    print("  period. This is the 2*pi ambiguity the paper discusses, and it is")
    print("  the reason for the multiplexed two-frequency pattern in Sec. 3.2.")

    # ------------------------------------------------------------------
    # What this means in angle, on our bench
    # ------------------------------------------------------------------
    print("\n" + "=" * 68)
    print("WHAT THIS MEANS FOR OUR MIRRORS")
    print("=" * 68)
    print("  A mirror tilted by theta swings the reflected ray by 2.theta")
    print("  (angle of incidence = angle of reflection), so a shift D on the")
    print("  screen at distance z_d corresponds to")
    print("\n      theta  =  D / (2 . z_d)\n")

    for shift_px in (0.1, 1.0, 15.0):
        shift_mm = shift_px * PIXEL_PITCH_MM
        theta_urad = shift_mm / (2 * Z_D_MM) * 1e6
        print(f"   {shift_px:6.2f} px  =  {shift_mm:7.4f} mm  ->  "
              f"{theta_urad:8.2f} urad of mirror tilt")

    max_urad = (PERIOD_PX / 2 * PIXEL_PITCH_MM) / (2 * Z_D_MM) * 1e6
    print(f"\n  So with a {PERIOD_PX:.0f} px fringe at z_d = {Z_D_MM:.0f} mm we can measure")
    print(f"  tilts up to about +/- {max_urad:.0f} urad before the phase wraps.")

    # ------------------------------------------------------------------
    print("\n" + "=" * 68)
    print("WHAT I STILL NEED TO SETTLE")
    print("=" * 68)
    for q in (
        "Sign convention. Eq. (2) in the paper is written exp(-i.2.pi.f.D), but\n"
        "     numpy's forward transform gives exp(+i...) for that same shift. The\n"
        "     magnitude is unaffected, so every check still passes -- but the sign\n"
        "     of the angle flips. Which convention do we adopt, and how do we\n"
        "     verify it on the bench?",
        "Fringe period. Finer fringes measure smaller angles but wrap sooner.\n"
        "     30 px gives +/- 1680 urad here. Is that the range we need?",
        "Two frequencies. Sec. 3.2 uses a second period to break the wrap. Worth\n"
        "     implementing now, or only once we see the real range we need?",
        "z_d and the pixel pitch both scale the answer linearly. How accurately\n"
        "     can we measure them, and does that set our accuracy floor?",
    ):
        print(f"\n  *  {q}")
    print()


if __name__ == "__main__":
    main()
