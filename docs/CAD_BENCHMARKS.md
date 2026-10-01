# CAD import verification · v0.7.0

Measured on 2026-10-01 with Gmsh 4.15.2 and native Foundation OpenFOAM 14, build `14-7b05503f98a8`. Inputs, source hashes, run IDs, numerical checks, face powers and failed attempts are retained in [cad-benchmarks.json](cad-benchmarks.json). These are actual imported CAD meshes and solver fields. No reference values or fabricated results were substituted.

The release verifies the import/assignment/meshing/solver workflow. **It does not qualify general CAD prediction accuracy.** The imported pipe still has substantial pressure-gradient error, and the turbulent smoke test does not converge. The existing axisymmetric pipe results do not establish accuracy for these tetrahedral meshes.

## Three-mesh imported STEP study

The reproducible script constructs and exports a 100 mm pipe as two STEP bodies: a 10 mm diameter fluid cylinder and a 1 mm aluminium annulus. It imports the file through the real API, explicitly assigns body roles and inlet/outlet faces, and applies 10 W to the outer cylindrical solid face. Both solid annular end faces have convection `h = 1000 W/(m² K)` to 15 °C. Water enters at 20 °C and 0.01 m/s (Re ≈ 99.7). The exact resolved water/solid properties are in the JSON report.

The importer's flow-rate boundary preserves the CAD-derived inlet volume flow even when the triangulated inlet area differs slightly. Solid/fluid meshes are conformal. Heating is distributed by mesh face area; the fluid and solid use perfect thermal contact. Flow is steady and frozen for the subsequent native coupled temperature solve.

| Target mm | Fluid / solid cells | Pressure drop Pa | Outlet °C | Max solid cell °C | Energy error % |
|---:|---:|---:|---:|---:|---:|
| 2 | 15,985 / 12,307 | 0.477744 | 22.868946 | 25.271275 | 7.86e-08 |
| 1.4 | 16,046 / 13,829 | 0.478370 | 22.867634 | 25.257743 | 8.43e-08 |
| 1 | 34,528 / 24,920 | 0.469419 | 22.865890 | 25.419796 | 2.85e-07 |

All three runs pass the existing flow and thermal convergence, mass and energy balance, boundary-power agreement, and fluid/solid interface checks. The largest mass imbalance is 1.63e-08%, largest interface temperature jump 0 K, and largest interface-flux mismatch 6.70e-05%. The temperature solves run 2,000 iterations; flow converges at 168, 178 and 237 iterations respectively.

Curvature and thin-wall sizing constrain the coarse meshes, so 2 mm and 1.4 mm produce almost the same fluid cell count. The 1 mm target produces a meaningful increase in fluid/solid resolution. Medium-to-fine pressure drop changes by 1.87% relative to the medium result; maximum solid cell temperature changes by 0.162 K. This nonuniform tetrahedral sequence does not establish mesh independence or justify Richardson extrapolation.

### Analytical pressure-gradient comparison

Fit the computed pressure over x = 60–85 mm, weighted by cell volume, and compare with the fully developed laminar relation `32 μ U / D²`, using actual face-integrated flow and nominal CAD area. The reference is the [NPTEL Hagen–Poiseuille teaching derivation](https://archive.nptel.ac.in/content/storage2/courses/112104118/lecture-26/26-3_hag_poiseuille.htm). It is an analytical reference, not an experiment or measured research dataset.

| Target mm | Computed gradient Pa/m | Analytical Pa/m | Deviation % |
|---:|---:|---:|---:|
| 2 | 4.034842 | 3.205108 | +25.888 |
| 1.4 | 4.192589 | 3.205108 | +30.810 |
| 1 | 3.968180 | 3.205108 | +23.808 |

All exceed the project's 5% pipe screening target. The fit begins downstream of the approximate `0.05 Re D` entrance-length estimate, but the imported-case script does not establish developed-flow independence through profile and interval-drift checks. The comparisons remain unqualified. Further near-wall resolution, scheme/mesh sensitivity and inlet-development checks are required. No physical coefficients were adjusted to conceal these errors.

## Additional native integration cases

| Case | Result | Evidence and limitation |
|---|---|---|
| Fluid-only pipe, flow reversed from x=100 to 0 mm | Completed | 15,963 fluid cells, pressure drop 0.480372 Pa, mass error 1.75e-08%. Correct inward port direction, total-flow boundary and single-region path. Analytical gradient deviation +27.964%, unqualified. |
| Aluminium sleeve over x=25–75 mm only | Completed | 15,976 fluid / 6,464 solid cells. Exposed fluid wall sections are no-slip and adiabatic. Outlet 22.812815 °C, max solid 27.582073 °C; energy error 1.84e-07%. All implemented coupling/convergence checks pass; gradient deviation +33.574%, unqualified. |
| Fluid-only k–ω SST at 1 m/s, 2 mm mesh | **Not converged** | Native solve reaches 3,000 iterations without a wall-patch/configuration fatal error. Mass imbalance 3.33e-06%; k/omega and flow residuals exceed 1e-6. Saved results retain `not_converged`. This tests wall-function patch compatibility, not turbulence accuracy. |

The partial sleeve has the same 10 W total outer heating and end convection as the full sleeve. No experimental thermal comparison is claimed. The SST mesh has no wall layers and is unsuitable as evidence of a resolved turbulent boundary layer.

## Failures found and fixed

- Applying a general OpenCASCADE dilation changed analytic surface types and failed exact volume-scaling checks. Scaling at import with `Geometry.OCCScaling` preserves analytic planar ports and passes area/volume scaling tests. Native tests also verify STEP declarations in metres are converted to mm and the exported mesh coordinates are in SI metres.
- The touching-cylinder IGES fixture lost separate closed-body topology and could not be sewn into an unambiguous model. It remains explicitly rejected. The same fluid/solid geometry imports through STEP/BREP; a closed-box IGES shell sews successfully. Unsupported surface geometry is not silently converted to invented CFD regions.
- The first fluid-only run failed during mesh checking: Foundation 14 `splitMeshRegions` emits no separate directory when only one region exists. That failed run (`8e0a2863-36d6-4e88-b8b6-566100fd1ff6`) remains in the report. The corrected path copies the single mesh into the expected fluid region, skips splitting, and completes the reverse-flow rerun.
- Gmsh external CAD surface groups initially have generic patch types. They are converted to OpenFOAM wall patches for no-slip/SST wall functions while preserving inlet/outlet and mapped interfaces. The subsequent SST smoke solve executes but remains unconverged as reported above.
- The SVG fallback initially produced out-of-range lit colour channels because Three's SVG renderer ignores ambient-light intensity. Scaling its ambient colour fixes the fallback without changing WebGL lighting. No solver values or boundary assignments changed.

## UI and automated verification

111 backend tests pass, including native Gmsh import, declared units, explicit scaling, topology, selection-order-independent face identity, fluid-only meshing, invalid body/face rejection, authoritative inlet area, upload checks and separated job history. All 19 frontend tests, ESLint and the production build pass. Shared-control tests cover pointer direction, free rotation through both poles, damping, pure roll, narrow/wide camera fitting, gesture-versus-click distinction and disposal.

The compiled production React bundle is exercised with JSDOM, the actual Three SVG renderer and a live native API: CAD upload, roles, preparation, all four boundary assignments, persistent renderer/camera, actual projected orbit motion, right-click protection, saved setup, actual saved CFD/thermal fields, submit/cancel/delete, retained CAD source, scale invalidation and independent-panel overflow styles. A test initially clicked a disabled Delete button before the cancelled run's card refreshed; waiting for the button to become enabled fixes that test timing assumption.

A rendered SVG projection was visually inspected. A native Chrome run could not start because the execution environment rejects the browser's socket creation. Consequently **browser/GPU frame rate, native pointer feel and full page layout were not measured**. Those should be checked on the target Windows browser; the SVG integration check does not establish WebGL performance.

## Reproduce locally

Install the app and developer test dependencies, then use Foundation OpenFOAM 14:

```bash
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python scripts/validate_cad.py
.venv/bin/python scripts/validate_cad.py --flow-only --reverse --sizes 2 --output validation-output/cad-flow-only
.venv/bin/python scripts/validate_cad.py --partial-wall --sizes 2 --output validation-output/cad-partial-wall
.venv/bin/python scripts/validate_cad.py --flow-only --velocity 1 --sizes 2 --output validation-output/cad-sst-smoke
```

Each folder receives the STEP file, source hash, full inputs, saved cases and a summary. The script's exit status checks whether execution completed or produced explicit unconverged results; it is **not** an accuracy/convergence acceptance gate. Inspect `status`, `checks` and `analytical_screen`. The laminar reference is omitted for turbulent cases. Generated meshes, fields and dependencies are excluded from Git.

The validation environment used native serial OpenFOAM with its dummy Pstream library because an MPI runtime was unavailable. This was an environment-only setting; the application's normal OpenFOAM environment and one-worker queue remain unchanged.
