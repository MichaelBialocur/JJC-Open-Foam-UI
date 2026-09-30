# Coupled wall conduction · measured v0.4 results

Measured on 2026-09-30 with Foundation OpenFOAM 14 (`14-7b05503f98a8`), serial execution. Actual computed flow from the earlier laminar benchmark was reused unchanged; native `foamMultiRun` then solved coupled fluid/solid energy. Full inputs, case IDs, convergence checks, deviations and sampled fine-mesh profiles are in [conjugate-benchmarks.json](conjugate-benchmarks.json). No reference temperatures or heat-transfer correlations generated the CFD fields.

## Model and reference

Water: Re=100, D=10 mm, L=1 m, Tin=20 °C, rho=998 kg/m³, mu=0.001002 Pa s, Cp=4182 J/(kg K), k=0.6 W/(m K). A 2 mm aluminium wall has constant k_s=200 W/(m K). Total power **10 W enters the outer solid surface**, uniformly. The solid conducts both axially and radially, its ends are insulated, and the fluid/solid interface has perfect thermal contact. Flow/turbulence and properties remain frozen.

The mean outer-to-inner solid temperature drop is compared with `Q ln(ro/ri)/(2 pi L k_s)` = **0.002677561 K**. Insulated ends make the axial mean obey the radial cylinder equation, even with local axial conduction. The reference and derivation are documented in [VALIDATION.md](VALIDATION.md). This checks the solid resistance and coupling implementation; it is **not experimental validation** of a heated pipe. The previous uniform-inner-flux Nu = 48/11 reference is not a qualification criterion for this conjugate case.

## Three-mesh study

| Mesh | Fluid + solid cells | Thermal iterations | Maximum solid T (°C) | Mean wall drop (K) | Error vs cylindrical resistance |
|---|---:|---:|---:|---:|---:|
| Coarse · 120 × (16 + 8) | 2,880 | 1,000 | 24.172410 | 0.002673682 | −0.14488% |
| Medium · 240 × (32 + 16) | 11,520 | 1,000 | 24.171165 | 0.002672770 | −0.17892% |
| Fine · 480 × (64 + 32) | 46,080 | 2,000 | 24.169420 | 0.002672543 | −0.18743% |

All three completed cases passed residual, saved-field stationarity, mass conservation, whole-system energy and independent fluid/solid interface checks. Whole-system energy errors were below 3 × 10⁻⁹% for this study. Fine-grid integrated interface mismatch was 0.0000503% of input power; the maximum local mismatch was 0.001934% of the mean input flux. Written-field precision affects the gradient comparison across this highly conductive wall, so these small differences are retained, not rounded to zero.

The medium-to-fine maximum solid-temperature change is **0.001745 K**; the mean wall-drop change is **0.00853%**. Outlet mixing temperature on the fine grid is **23.037585 °C**. Wall resistance error does not monotonically approach zero: the planar 5° wedge retains an angular approximation as axial/radial resolution increases. The radial continuum resistance of this planar wedge tends to `cos²(2.5°)` times the cylindrical value, an approximately −0.1903% offset; results are reported against the uncorrected cylinder, not adjusted to hide that difference. Angular refinement is still a separate, unperformed study.

**Recorded failed qualification:** after 1,000 fine-grid iterations, overall energy error was only 0.001109%, but maximum local interface flux mismatch was **2.2951%** and normalized saved solid-temperature change was **2.69 × 10⁻⁵**. That result was correctly marked not converged/not qualified. Continuing the same case to 2,000 iterations passed all gates. Both records are retained in the JSON. The UI and coupled preset now use 2,000 thermal iterations; users still need to inspect convergence for other inputs.

## Material and thickness sensitivity

Same Re=100 water and 10 W input, medium mesh. The two additional cases use 2,000 thermal iterations; the baseline is the converged 1,000-iteration mesh-study case above.

| Wall | Conductivity (W/m K) | Maximum solid T (°C) | Mean wall drop (K) | Resistance error |
|---|---:|---:|---:|---:|
| Aluminium, 2 mm (mesh-study baseline) | 200 | 24.171165 | 0.002672770 | −0.17892% |
| Copper, 2 mm | 391.1 | 24.131043 | 0.001366796 | −0.17891% |
| Aluminium, 4 mm | 200 | 24.121428 | 0.004670273 | −0.15359% |

All checks passed. Increasing conductivity reduces the mean radial wall drop; increasing thickness raises that radial drop. The thicker, conductive wall also spreads heat axially, which reduces the peak wall temperature in this particular insulated-end, fixed-total-power case. A thicker wall does not universally raise or lower peak temperature: boundary conditions and axial spreading matter. The fluid receives almost the same power in all cases; its outlet mixing temperature changes slightly through inlet conductive losses.

## Turbulent path and workflow checks

A separate medium-grid native SST case reused the Princeton flow conditions at Re=41,727, with air Cp=1007 J/(kg K), k=0.0263 W/(m K), Prt=0.85, 100 W outer heating and a 2 mm aluminium wall. Coupled convergence, conservation and solid resistance checks passed. The maximum local interface mismatch was 0.0861%, below the 0.5% project gate; the solid resistance error was −0.19013%. Exact fluid outlet temperature and energy terms are in the JSON. This is a thermal implementation/conservation check, **not** comparison with thermal experimental measurements. Existing turbulent flow grid sensitivity and legacy experimental-data limitations remain unchanged.

A fresh coarse case `d165fb06-203c-4223-957f-2aee2fe9f357` passed the complete generation → fluid mesh/check → flow → solid mesh/check → coupled energy → results workflow. No saved flow was reused for this check. The prior fine fluid-only case was reprocessed without changing its result: Nu=4.381636, within its original analytical screening target.

26 backend tests and 7 frontend tests passed, along with lint and production build. Live API checks covered fluid/solid JSON fields, outer/inner temperature and local heat-flux CSV columns, solid VTK and a ZIP containing the native multi-region case. The compiled React app with the live API passed preset/material selection, SVG orbit/reset, fluid/solid/combined field selection, section slider, solid and fluid probes, round/zero chart ticks and thermal metrics. Full browser/WebGL layout remains unverified because the execution environment blocks browser sandbox startup; the SVG fallback and actual axial colour map were checked.

## Reproduction

For a complete fresh coupled workflow:

```bash
.venv/bin/python scripts/validate.py --case heated_wall --meshes coarse medium fine --output validation-output/conjugate-fresh
```

To reuse converged flow benchmarks without changing their flow solution:

```bash
.venv/bin/python scripts/validate_conjugate.py <coarse-flow-case> <medium-flow-case> <fine-flow-case>
.venv/bin/python scripts/validate_conjugate.py <medium-flow-case> --material copper --output validation-output/copper
.venv/bin/python scripts/validate_conjugate.py <medium-flow-case> --wall-mm 4 --output validation-output/thicker
.venv/bin/python scripts/validate_conjugate.py <medium-superpipe-flow-case> --power 100 --fluid-cp 1007 --fluid-k .0263 --output validation-output/air
```

The reuse script defaults to 2,000 thermal iterations on every grid, records original flow provenance and exact thermal inputs, writes full results and solid VTK, and exits nonzero if the coupled analytical verification is not qualified. Generated cases remain outside Git. In ParaView, open `thermal/conjugate.foam` and select both regions; its iteration values are not physical time.

Current limits: constant properties, frozen flow, axisymmetric geometry, perfect contact, uniform outer heating and insulated solid ends. No thermal experimental uncertainty, contact resistance, external convection/radiation, buoyancy, phase change, transient heating or CAD/multiport geometry has been qualified here.
