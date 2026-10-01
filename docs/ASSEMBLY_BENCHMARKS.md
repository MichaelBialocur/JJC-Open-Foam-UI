# Full 3D assembly benchmarks · v0.6

Measured with Foundation OpenFOAM 14 and Gmsh 4.15.2 on 2026-10-01. Complete inputs, run IDs, convergence, face powers and references are in [assembly-benchmarks.json](assembly-benchmarks.json). Reproduce with `scripts/validate_assembly.py`.

## Straight-pipe analytical verification

D = 10 mm, L = 50 mm, wall = 1 mm, constant water properties, uniform inlet U = 0.001 m/s (Re ≈ 10). The actual polygonal inlet area changes with refinement. Compare the volume-weighted downstream pressure-gradient fit over 60–85% of length with Hagen–Poiseuille, `f_D = 64/Re`, using face-integrated flow and nominal CAD area. Velocity RMSE compares actual cell-centre velocities with the parabolic analytical profile.

Reference: [NPTEL Lecture 26](https://archive.nptel.ac.in/content/storage2/courses/112104118/lecture-26/26-3_hag_poiseuille.htm). This is an analytical solution, not research measurements. The new 3D discretization must earn its own qualification; the prior axisymmetric benchmark does not transfer automatically.

| Target mm | Fluid cells | Computed Darcy f | Reference f | f error % | Profile RMSE % of bulk | Gradient drift % |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 4,971 | 7.577149 | 6.528591 | +16.061 | 3.378 | 3.192 |
| 1 | 17,627 | 7.467162 | 6.463178 | +15.534 | 2.078 | 1.009 |
| 0.65 | 59,532 | 7.220472 | 6.439361 | +12.130 | 1.524 | 1.668 |

All three flow runs converge and conserve mass. **None meets the 5% friction-factor screening target.** The finest error is +12.13%; the profile RMSE is 1.52%. Pressure-gradient accuracy remains a development priority. Do not equate conservation or a converged residual with accuracy.

The applicability screen requires <5% gradient drift and a downstream fitting region beyond `max(1, 0.05 Re) D`. That entrance-length estimate is a project screening heuristic; it is not proof of fully developed flow. The full-reference error remains visible even if a comparison is unqualified.

## Heated and externally cooled cold plate

Preset: 25 mm inlet pipe → 20 mm round-to-rectangular manifold → 50 mm multi-port plate → 20 mm outlet manifold → 25 mm outlet pipe. Pipe ID 10 mm; plate outside section 30 × 6 mm, outer wall 1 mm, five channels, 1 mm webs (each channel 4.8 × 4 mm). Water enters at 20 °C and 0.1 L/min; aluminium conductivity 200 W/(m K).

The **total 10 W** is split across the equal plate top and bottom faces, 5 W each. Both side faces have h = 500 W/(m² K), ambient 20 °C. Other exterior faces are insulated. All meshes use the same CAD face IDs and physical boundary values.

| Target mm | Fluid / solid cells | Δp Pa | Outlet °C | Max solid cell °C | Fluid heat gain W | Energy error % |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 18,955 / 21,918 | 2.569548 | 21.355119 | 22.243366 | 9.432872 | 1.56e-07 |
| 1.4 | 32,179 / 36,575 | 2.687050 | 21.358095 | 22.189620 | 9.453585 | 2.89e-07 |
| 1 | 67,895 / 63,525 | 2.826021 | 21.360438 | 22.151491 | 9.469893 | 3.5e-08 |

All three runs pass flow/thermal convergence, mass and energy conservation, boundary-power agreement, and interface temperature/flux checks. Medium→fine pressure drop changes by **4.92%**, and maximum solid temperature by **0.0381 K**. These meshes do not establish pressure-loss independence or an error bound. No Richardson extrapolation is claimed for this nonuniform tetrahedral sequence.

The energy check independently sums fluid enthalpy gain, inlet conductive loss, net kinetic-energy transport and heat leaving each exterior solid face. Each imposed power/convection flux is compared against a one-sided gradient from the written solid temperatures. Fluid/solid interface gradients are reconstructed separately and matched by conformal face centroids. This verifies conservative coupling and boundary implementation, **not experimental thermal accuracy**.

## Elbow smoke test

The 40 mm pipe → 90° bend with 20 mm centreline radius → 40 mm pipe preset completes a real 3D flow solve at 0.1 L/min on the 2 mm target mesh (11,032 fluid cells). Pressure drop is 1.509580 Pa and mass imbalance 1.87e-08%. This is a geometry/solver integration check; no experimental bend-loss qualification is claimed.

## Initial failures and corrective work

The first `cellLimited Gauss linear 1` gradient scheme gave pipe friction errors of +37.51%, +40.74% and +49.15% under refinement and a small two-iteration residual cycle in the cold plate. Tightening linear-solver tolerance did not cure the cycle. Those attempts are retained in the JSON report. The final solver uses **least-squares gradient reconstruction** for the unstructured tetrahedral mesh; physical viscosity, density and other material coefficients were unchanged. The replacement converges in the tested cold plate and gives decreasing pipe error, but the remaining +12.13% is explicitly unqualified.

An earlier short-pipe Re ≈ 98 comparison was +70.14% and overlapped inlet development. It is also retained as unqualified. Initial CAD development exposed a round-to-rectangle wire-edge mismatch and topology changes caused by CAD scaling. Four-arc transition wires and scaling at mesh export fixed these defects. Native tests now check SI mesh dimensions, fluid volume, rolled/tapered bends, exterior areas and persistent face IDs across mesh sizes. Serialization defects discovered after the first coupled solve were fixed and the original fields reprocessed, without changing CFD values.

## Scope and sources

- [Gmsh 4.15.2 manual](https://gmsh.info/doc/texinfo/gmsh.html): OpenCASCADE lofts, revolutions, booleans, conformal fragments, mesh sizing and output scaling. Gmsh authors: Christophe Geuzaine and Jean-François Remacle.
- Foundation OpenFOAM 14 installed source: `flowRateInletVelocity`, `externalTemperature`, `coupledTemperature`, `splitMeshRegions` and `surfaceInterpolation`. Exact distribution syntax is used.
- Existing [conjugate benchmarks](CONJUGATE_BENCHMARKS.md) and [experimental pipe provenance](VALIDATION.md) remain available, but they do not qualify this new arbitrary-geometry solver.

The builder uses linear tetrahedra without wall-layer inflation and first-order upwind thermal convection. No full-3D SST reference study or matched cold-plate research experiment has yet been added. Next validation work should improve near-wall/pressure-gradient discretization and compare channel flow distribution, pressure loss and temperatures against a reproducible, geometry-matched cold-plate dataset with uncertainty. Do not substitute a mismatched research curve for this evidence.

Automated verification: 75 backend tests (including native CAD), 16 frontend tests, ESLint and production build, plus the real compiled React bundle against a live API for geometry building, face assignments, flow units, 3D orbit, run/cancel, native solid-temperature slicing, stale-face invalidation and draft persistence. A full browser screenshot run was unavailable in this environment; SVG rendering and actual DOM behavior were exercised.
