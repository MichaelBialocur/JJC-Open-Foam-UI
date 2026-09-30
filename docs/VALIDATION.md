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

For heated pipes, the analytical energy/Nusselt checks below are implemented; separate experimental Nusselt/temperature datasets are still needed for experimental validation claims. For manifolds/multiport tubes, validate distribution and pressure losses. For imported CAD, retain boundary selection, mesh quality and benchmark provenance.

OpenFOAM setup follows the [Foundation 14 user guide](https://doc.cfd.direct/openfoam/user-guide-v14/backwardstep) and installed Foundation 14 source dictionaries; `foamRun` loads `incompressibleFluid` with steady-state schemes.

## Fluid heating: analytical verification added in v0.3

Reference: S. Chakraborty, NPTEL / IIT Kharagpur, [Advanced Heat and Mass Transfer, Lecture 29](https://archive.nptel.ac.in/content/storage2/courses/103105052/AdvHeatMass_L_29.pdf), pp. 5–7, accessed 2026-09-30. For fully developed laminar flow and uniform wall heat flux, `Nu = h D/k = 48/11`. The assumptions include constant properties, negligible axial diffusion and viscous heating. Its entrance-length estimate is `Lth/D ≈ 0.05 Re Pr`. This is an analytical limiting case, not an experimental dataset.

The heated preset adds Q=10 W, Tin=20 °C, Cp=4182 J/(kg K) and k=0.6 W/(m K) to the Re=100, L/D=100 flow case. `Pr = mu Cp/k = 6.98394`. The energy solve uses actual frozen U, phi and, for SST, nut fields. No reference temperature profile is substituted into the solver. OpenFOAM 14 source and `pitzDailyScalarTransport` tutorial define the `functions`/`scalarTransport` configuration; no custom solver compilation is required.

For the planar 5° wedge, full-cylinder flow scales by `2 pi/sin(5°)`. The applied wedge wall flux is `Q cos(2.5°)/(pi D L)` so the same scaling yields exactly Q. The wedge's fixed angular geometry error remains. OpenFOAM omits values for `fixedGradient`/`zeroGradient` T boundaries; postprocessing evaluates those exact discrete boundary rules from their owner cells. Wall T is `Towner + gradient * normal_distance`; outlet T equals its owner-cell T. The structured generator's radial ordering is retained for boundary flux integration.

Report `Qadv = rho Cp Σ phi_out (Tout − Tin)`, scaled to a complete pipe, plus the conductive loss through the fixed-temperature inlet. The inlet diffusion uses the boundary effective diffusivity and its orthogonal centre-to-face distance. The outlet has zero conductive flux. The conservation error is `|Qadv + Qcond,in − Q|/Q`; the ideal adiabatic rise `Q/(mass_flow Cp)` is labelled as a preview estimate only. Section bulk T uses Ux-area weighting; outlet T uses the actual boundary phi weighting.

Local Nu uses the computed wall-to-bulk temperature difference and nominal circular wall flux. The comparison averages Nu over 65–85% of length and reports its change between 60–75% and 75–90%. Qualification requires converged flow and T, mass and energy errors below 0.5%, inlet conduction below 1% of heat input, developed velocity, Nu drift below 2%, sufficient estimated thermal entrance length and laminar reference applicability. T convergence requires a final written state, initial T residual below the input tolerance, and stationarity of the last two saved fields normalized by the larger of ideal bulk rise and computed wall-to-bulk difference. These are project screening gates. The Nu screening target is 2%; it does not replace a mesh study or measurement uncertainty.

The [three-mesh fluid-only results](THERMAL_BENCHMARKS.md) retain actual deviations and remaining fixed wedge/development/discretization limitations. A turbulent heating smoke test checks implementation and conservation only: `Prt=0.85` is an explicit closure assumption and there is no thermal experimental qualification. Solid conduction was added separately in v0.4, below; buoyancy, phase change and temperature-dependent properties remain outside the model.

## Coupled wall conduction: analytical verification added in v0.4

The [NPTEL cylinder conduction reference](https://archive.nptel.ac.in/content/storage2/courses/103103032/module2/lec6/1.html) gives the logarithmic resistance of a steady constant-k annulus. For this model, integrate the solid conduction equation over the length. Insulated end conditions eliminate the axial derivative's boundary terms; consequently the **axial mean** temperature solves the radial equation, even when the local temperature varies axially. The predicted mean outer-to-inner drop is `Q ln(ro/ri)/(2 pi L k_s)`. This derivation is the application's extension of the reference's 1D result. It does not imply that the local inner flux is uniform. No analytical temperature is supplied to the CFD solver.

Native Foundation 14 `foamMultiRun` loads `fluid` and `solid`. `flow false; models false; thermophysics true;` keeps the computed flow/turbulence frozen. Fluid thermo uses `heRhoThermo`, `rhoConst`, `hConst`, constant transport and sensible enthalpy. Conservative volumetric phi is multiplied by density for the native mass flux. The prescribed outer `externalTemperature` power is `Q sin(5°)/(2 pi)` for the planar wedge. The interfaces use matching `mappedWall` patches and `coupledTemperature`. The annulus has the fluid axial cell count and 8/16/32 uniform radial cells. Each solid mesh must pass `checkMesh`.

The energy balance includes fluid enthalpy gain, inlet conduction and the native equation's net boundary kinetic-energy transport, `rho [Σout(phi |U|²/2) + Σin(phi |U|²/2)]`. Flow pressure remains the independent incompressible result. No buoyancy, viscous dissipation, radiation, external heat loss or property feedback is introduced.

Convergence requires both fluid h and solid e initial residuals below the input tolerance and changes in **both** saved temperature fields below that tolerance after normalization by the temperature-rise scale. Independently, global energy error, solid energy error and maximum local interface flux mismatch must each be below 0.5% of input power (local mismatch is normalized by the mean input flux). Interface temperature mismatch must be below the temperature-rise scale times the tolerance. The resistance comparison is qualified only after convergence and mass/energy/interface checks pass; its screening target is 2%. This is implementation verification, not a thermal experiment or a guaranteed uncertainty bound.

The wall-flux postprocessor uses two independent one-sided conductive gradients from actual written fluid/solid temperatures. At a resolved no-slip SST wall, nut/alphat are zero; inlet diffusion includes `nut/Prt`. Native pressure is held constant in the thermal subcase. No corrections are applied to force agreement with the cylindrical reference. The remaining 5° wedge angular error is retained; axial/radial refinement cannot remove it.

Material presets: aluminium EN AW-6060 uses **200 W/(m K)**, the lower end of [thyssenkrupp's 200–220 W/(m K) room-temperature guidance](https://www.thyssenkrupp-materials.co.uk/aluminium-6060.html); copper C11000 uses **391.1 W/(m K) at 20 °C**, from [Aviva Metals' material data](https://www.avivametals.com/collections/copper-alloys/beryllium-copper/c11000-cda-110-cu-etp-electrolytic-tough-pitch-etp-copper). These are explicit constant-property presets, not universal values for all grades or temperatures. Users can override conductivity. Solid density/heat capacity are representative constants required by the native thermo model; they do not affect this steady equation. Transient storage is not implemented.

Measured results, the initially unconverged fine mesh, and remaining limitations are retained in [CONJUGATE_BENCHMARKS.md](CONJUGATE_BENCHMARKS.md).
