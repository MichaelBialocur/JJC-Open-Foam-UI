# Validation policy and reference provenance

Every physics change must state its comparison source, assumptions, applicable range, observed errors, and what remains unvalidated. Agreement with an analytical solution verifies implementation; comparison with an experiment assesses model adequacy. They are different checks.

## Analytical verification: fully developed laminar pipe

For incompressible Newtonian flow in a straight circular tube:

- `Re = rho U_bulk D / mu`
- Darcy friction factor `f_D = 64/Re`
- `-dp/dx = 32 mu U_bulk / D²`
- `U(r)/U_bulk = 2[1 - (r/R)²]`

Source: [NPTEL, Lecture 26, Hagen–Poiseuille flow](https://archive.nptel.ac.in/content/storage2/courses/112104118/lecture-26/26-3_hag_poiseuille.htm). The implementation derives the dimensional pressure gradient and velocity profile directly, with no fitted coefficient.

The preset uses D=0.01 m, L=1 m, rho=998 kg/m³, mu=0.001002 Pa·s and U chosen for Re=100. A uniform inlet develops into the parabolic profile. Only the downstream developed gradient is compared with the analytical value; the entire pipe pressure loss contains an entrance contribution.

## Experimental comparison: Princeton Superpipe

- [Original numerical dataset, Re 41,727](https://www.princeton.edu/~gasdyn/Superpipe_data/4.1727E%2B04.txt), retrieved 2026-09-29.
- [Dataset description and correction caveats](https://www.princeton.edu/~gasdyn/index.html#superpipe_data).
- Facility/data background: M. V. Zagarola's 1996 Princeton thesis, *Mean Flow Scaling of Turbulent Pipe Flow*.
- Related research: Zagarola & Smits (1998), *Mean-flow scaling of turbulent pipe flow*, JFM 373, 33–79, [DOI 10.1017/S0022112098002419](https://doi.org/10.1017/S0022112098002419).
- Later correction work: McKeon & Smits (2002), [Static pressure correction in high Reynolds number fully developed turbulent pipe flow](https://www.princeton.edu/~gasdyn/Superpipe_data/mckeon%26smits.pdf).

The data file supplies Darcy f=0.021858, U_bulk=5.1320 m/s, friction velocity=0.26825 m/s, rho=1.1620 kg/m³, mu=1.8487e-5 Pa·s, D=0.12936 m and a pressure-gradient magnitude of 2.5855 Pa/m. The preset uses these fluid/flow quantities with a 200D straight inlet development length; its geometry represents the fully developed test section, not the experimental apparatus. Forty-two positive-radius measurements are stored at original precision. Convert the published `u+` to `U/U_bulk` with the published friction and bulk velocities.

**These are uncorrected legacy measurements.** Princeton explicitly says Pitot displacement and other corrections were not applied and identifies later static-pressure work. Do not imply this file contains the corrected 1998/2004 results. Comparisons are exploratory; systematic measurement errors remain. The source does not give a per-point uncertainty for this file. The code uses this limitation in its UI and exported results.

The comparison is enabled only when Re is within 1% of the supplied experiment. It uses dimensionless profiles and Darcy f, allowing dynamically similar constant-property fluid cases, but still requires a smooth, developed, incompressible flow. No turbulent correlation is passed off as measured data. No interpolation to unrelated Reynolds numbers is performed. Profile RMSE is evaluated at experimental radii lying within the CFD sampling interval; there is no extrapolation to the axis or wall. Exported results include the number of comparison points: radial coverage changes with refinement, so the experimental RMSE need not use the same subset on every mesh. Laminar RMSE uses each mesh's cell-centre radii. Use Darcy f for the reported scalar mesh-change metric.

## Qualification and numerical convergence

Before a comparison is qualified, the app requires:

1. A completed mesh check and a finite solution written at the final solver iteration. Iteration limits are multiples of 100 to coincide with saved fields; OpenFOAM also writes on its convergence stop.
2. Convergence: either the OpenFOAM convergence message, or the independent checks below.
3. Inlet/outlet face-flux imbalance below 0.5%.
4. Developed-gradient drift below 2% between the 60–75% and 75–90% axial intervals.
5. Profile drift below 1% of inlet mean velocity between 65% and 80% length.
6. Positive pressure gradient and, for SST, estimated first-wall-cell y+ ≤ 2.
7. A matched reference case.

A relative residual of an identically zero swirl velocity can fluctuate at round-off in wedge cases. When the solver reaches its iteration limit, a separate stationarity check requires **all of the following**: p, Ux, Uy and (when present) k/omega initial residuals below the input tolerance; Uz residual below that tolerance unless the maximum absolute Uz is less than 1e-10 times bulk velocity; and maximum changes between the last two saved fields (at least 10 iterations apart) below the same tolerance for U/U_bulk and p/(rho U_bulk²/2). The raw residuals, swirl magnitude, stopping reason, and field-change metrics remain in JSON. The app does not claim that OpenFOAM reported convergence when it did not.

Project screening targets are 2% for the laminar comparison and 10% for the initial experimental comparison, applied separately to absolute friction-factor error and profile RMSE in percent of bulk velocity. These are engineering screening choices, **not experimental uncertainty bounds**. They must not be represented as a statistical fit, universal solver accuracy, or certification.

## Mesh studies and future work

Coarse/medium/fine are 120×16, 240×32, and 480×64 axial/radial cells, with a single circumferential cell. Laminar spacing is uniform radially; SST's final/first radial-cell-width ratio is 0.02. Report all levels, including poor wall resolution or unconverged cases. A small mesh-to-mesh change does not establish experimental agreement. Angular refinement, domain-length and inlet-turbulence sensitivity remain distinct future checks. Do not calculate a GCI from non-asymptotic data without documenting the method and observed order.

For heated pipes, add analytical energy balance and separate experimental Nusselt/temperature datasets before validation claims. For manifolds/multiport tubes, validate distribution and pressure losses. For imported CAD, retain boundary selection, mesh quality and benchmark provenance. Preserve sources and actual run inputs with every comparison.

OpenFOAM setup follows the [Foundation 14 user guide](https://doc.cfd.direct/openfoam/user-guide-v14/backwardstep) and installed Foundation 14 source dictionaries; `foamRun` loads `incompressibleFluid` with steady-state schemes.
