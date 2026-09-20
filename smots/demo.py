#!/usr/bin/env python3
"""End-to-end SMOTS demonstration on the synthetic bench.

Run it with ``python demo.py``.  Nothing here touches hardware -- it commands a
set of tilts, renders the frames the camera would record, and runs the full
retrieval, so you can see the whole chain work before any of it meets a mirror.
"""

from __future__ import annotations

import numpy as np

from smots import (Bench, PatternSpec, analysis, coprime_periods, geometry,
                   grid_apertures, measure, reference_frame, render_frame,
                   sampling_report, synthetic_period)

URAD = 1e-6


def banner(text: str) -> None:
    print(f"\n{text}\n{'=' * len(text)}")


def main() -> None:
    bench = Bench()
    arr, screen = bench.array, bench.screen

    banner("Bench")
    print(f"  array            {arr.rows}x{arr.cols}, {arr.side_mm} mm mirrors, "
          f"{arr.gap_mm} mm gap  ->  {arr.width_mm:.1f} x {arr.height_mm:.1f} mm")
    print(f"  screen           {screen.width_mm} mm / {screen.pixels_x} px  "
          f"->  pitch {screen.pitch_um:.1f} um   [MEASURE THIS]")
    print(f"  screen distance  {bench.screen_distance_mm:.0f} mm            [MEASURE THIS]")
    print(f"  motorised        {[arr.name(r, c) for r, c in bench.motorised]}"
          f"  ({bench.channels_used()} of {bench.controller.channels} "
          f"{bench.controller.model} channels)")

    # ---------------------------------------------------------------- single
    banner("1. Single carrier -- resolution and range")
    spec = PatternSpec(periods_px=(30.0,), axes="xy", bias=128.0, amplitude=100.0)
    period_mm = spec.periods_mm(screen.pitch_mm)[0]
    rng = geometry.unambiguous_range(period_mm, bench.screen_distance_mm)
    print(f"  carrier          {spec.periods_px[0]:.0f} px = {period_mm:.3f} mm on screen")
    print(f"  unambiguous      +/- {rng * 1e6:.0f} urad before it wraps")

    ref = reference_frame(bench, spec, noise_dn=0.0)
    aps = grid_apertures(ref.image.shape, bench.array, bounds=ref.bounds)
    rep = sampling_report(aps, carrier_period_px=period_mm * ref.px_per_mm)
    print(f"  sampling         {rep['worst']:.1f} periods in the smallest aperture "
          f"-- {'ok' if rep['ok'] else 'TOO FEW'}")

    applied = {"M5": 150 * URAD}
    mea = render_frame(bench, spec, tilts_x=applied, noise_dn=0.0)
    res = measure(bench, spec, ref.image, mea.image, aps)
    print(f"\n  commanded M5 theta_x = {applied['M5'] * 1e6:+.1f} urad")
    print(f"  recovered  M5 theta_x = {res.by_name('M5').theta_x_urad:+.1f} urad")

    # ------------------------------------------------------------ all at once
    banner("2. All nine segments from one pair of frames")
    applied = {"M1": 60 * URAD, "M3": -80 * URAD, "M5": 140 * URAD, "M9": 100 * URAD}
    mea = render_frame(bench, spec, tilts_x=applied, noise_dn=bench.camera.noise_dn)
    ref_n = reference_frame(bench, spec, noise_dn=bench.camera.noise_dn,
                            rng=np.random.default_rng(1))
    res = measure(bench, spec, ref_n.image, mea.image, aps)
    print(res.table())
    print("\n  commanded:", {k: f"{v * 1e6:+.0f}" for k, v in applied.items()}, "urad in x")

    # --------------------------------------------------------- common mode
    banner("3. Common-mode rejection")
    drift, real = 90 * URAD, 130 * URAD
    tilts = {arr.name(r, c): drift for r in range(arr.rows) for c in range(arr.cols)}
    tilts["M5"] = drift + real
    mea = render_frame(bench, spec, tilts_x=tilts, noise_dn=0.0)
    res = measure(bench, spec, ref.image, mea.image, aps)
    dx, _ = res.differential("M5")
    print(f"  whole array drifts {drift * 1e6:+.0f} urad, M5 additionally {real * 1e6:+.0f}")
    print(f"  M5 raw          {res.by_name('M5').theta_x_urad:+.1f} urad")
    print(f"  M5 differential {dx * 1e6:+.1f} urad  <- the real motion, drift removed")

    # ---------------------------------------------------------- multiplexed
    banner("4. Multiplexed carriers break the 2*pi ambiguity")
    periods = coprime_periods(24.0)
    multi = PatternSpec(periods_px=periods, axes="xy", bias=128.0, amplitude=90.0)
    pmm = multi.periods_mm(screen.pitch_mm)
    single = geometry.unambiguous_range(pmm[0], bench.screen_distance_mm)
    beat = geometry.unambiguous_range(synthetic_period(*pmm), bench.screen_distance_mm)
    print(f"  periods          {periods[0]:.0f} and {periods[1]:.0f} px")
    print(f"  single carrier   +/- {single * 1e6:.0f} urad")
    print(f"  multiplexed      +/- {beat * 1e6:.0f} urad (conservative; real repeat is a "
          f"multiple of this)")

    over = 1.4 * single
    ref_m = reference_frame(bench, multi, px_per_mm=9.0, noise_dn=0.0)
    mea_m = render_frame(bench, multi, tilts_x={"M5": over}, px_per_mm=9.0, noise_dn=0.0)
    aps_m = grid_apertures(ref_m.image.shape, bench.array, bounds=ref_m.bounds)
    res_m = measure(bench, multi, ref_m.image, mea_m.image, aps_m)
    print(f"\n  commanded {over * 1e6:+.0f} urad -- past the single-carrier wrap")
    print(f"  recovered {res_m.by_name('M5').theta_x_urad:+.0f} urad")

    # ------------------------------------------------------------- accuracy
    banner("5. Accuracy vs camera noise (50 trials, M5 at 150 urad)")
    truth = 150 * URAD
    print("   sigma_I (DN)     bias (urad)     RMS error (urad)")
    for noise in (0.5, 1.0, 2.0, 4.0):
        errs = []
        for seed in range(50):
            g = np.random.default_rng(seed)
            r0 = reference_frame(bench, spec, noise_dn=noise, rng=g)
            m0 = render_frame(bench, spec, tilts_x={"M5": truth}, noise_dn=noise, rng=g)
            out = measure(bench, spec, r0.image, m0.image, aps)
            errs.append(out.by_name("M5").theta_x - truth)
        e = np.asarray(errs) * 1e6
        print(f"   {noise:>6.1f}        {e.mean():+10.3f}      {np.sqrt((e ** 2).mean()):12.3f}")
    print("\n  For reference the paper reports 0.8 urad RMS against an autocollimator.")

    banner("Before this touches hardware")
    for line in (
        "measure the screen pixel pitch under a microscope -- it scales every angle",
        "measure the mirror-to-screen distance z_d -- angle goes as 1/z_d",
        "replace grid_apertures bounds with the real array location in your frames",
        "confirm the tilt signs against a known actuator move before trusting them",
        "cross-check absolute angle against an autocollimator; SMOTS measures change",
    ):
        print(f"  - {line}")


if __name__ == "__main__":
    main()
