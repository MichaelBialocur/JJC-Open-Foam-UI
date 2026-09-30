# Pipe CFD · v0.3

A local React/FastAPI interface to **Foundation OpenFOAM 14**. Generate a straight circular pipe, inspect its 3D geometry, mesh it, and solve steady flow and optional fluid heating. Inspect actual pressure, speed and temperature fields, and compare results with traceable analytical or experimental references.

## Start on your Windows PC

Open PowerShell and enter Ubuntu:

```powershell
wsl -d Ubuntu-24.04
```

In Ubuntu:

```bash
cd ~/projects/pipe-cfd
git pull --ff-only
bash scripts/setup.sh
bash scripts/start.sh
```

Open **http://localhost:5173** in your Windows browser. Keep the terminal open; **Ctrl+C** stops the frontend, backend, and running solver. Setup preserves your project and installs dependencies into `.venv` and `frontend/node_modules`. These generated directories are ignored by Git.

Requirements: Ubuntu/WSL2, Python 3.12, Node 22.12+ (your Node 24 is suitable), and [Foundation OpenFOAM 14](https://openfoam.org/download/14-ubuntu/). The default environment file is `/opt/openfoam14/etc/bashrc`. For a different installation path set `OPENFOAM_BASHRC` before starting. This release checks for version 14; the OpenCFD v24xx/v25xx distribution uses different configuration conventions and is not supported.

The server binds to localhost. It is a local engineering tool, not an authenticated public simulation service. Run one backend worker; a lock prevents two processes owning the same run directory. Do not use Uvicorn reload while jobs are running.

## First run

1. Click **Heated pipe · analytical check**, choose **Coarse**, then **Run simulation**. The preset adds 10 W through the inner wall to water entering at 20 °C, Re 100.
2. Follow meshing, flow and temperature stages. Inspect the heat balance, outlet temperature and Nusselt comparison.
3. In **Computed field viewer**, choose speed, pressure or temperature. Orbit, zoom, select a cutaway/axial/cross-section view, move the section slider and click a cell to probe its values. **End view** looks down the pipe; **Reset view** restores the initial camera.
4. The axial colour map also supports probing. The optional section plot follows the slider. Colours are computed cell values without smoothing; a single global colour scale applies along the whole pipe.
5. **Enlarge diameter for viewing** makes slender pipes legible and states the scale factor. Uncheck it for true proportions. The wall geometry includes thickness; it has no computed solid-temperature field.
6. Click **Run three-mesh study** to compare flow and thermal metrics. Use **Laminar verification · Re 100** for flow only or **Princeton experiment · Re 41,727** for the existing turbulent flow experiment.

An unavailable OpenFOAM installation produces an explicit error. The software never returns analytical or reference curves as CFD output. Runs and results persist under `runs/`; startup marks unfinished runs as interrupted. Cancelled/failed runs keep their logs and cases. Existing v0.2 flow runs can be viewed directly; run a new heated case to get temperatures.

Exports include results JSON, velocity CSV, thermal-profile CSV, the computed meridional section as a ParaView-readable `.vtk` structured grid, and the full OpenFOAM case ZIP. Extract the ZIP and open `pipe.foam` at the latest flow iteration to see U, p and the final T together. The `thermal/thermal.foam` subcase retains the temperature solve and its separate iteration history. Both histories are steady-solver iterations, **not physical time**.

The 3D display revolves an axisymmetric solution; it does not add a circumferential flow calculation. WebGL is used when available. Without WebGL, the interactive SVG geometry/cross-section and 2D axial map remain available. Linear charts use decimal 1/2/5 tick steps; pressure and speed include a clearly marked zero while retaining any actual negative data. Temperature charts can use a focused range, and residuals use integer powers of ten.

## Physics and numerical scope

- Straight, smooth, circular pipe, a **5° axisymmetric wedge** with one circumferential cell.
- Uniform velocity inlet, no-slip wall, zero gauge pressure at the outlet.
- Constant density, dynamic viscosity, heat capacity and fluid conductivity entered by the user. Properties are **not** automatically temperature-dependent.
- Laminar below Re 2300; k–ω SST RANS from Re 4000. The transition interval is rejected explicitly. Regime cutoffs are application policy, not a universal prediction of transition.
- SST uses radial grading, near-zero wall k (1e-12 m²/s²), `omegaWallFunction`, and `nutLowReWallFunction`. The UI estimates y+ from the developed pressure gradient and first wall-cell position; it is a screening estimate, not an exported turbulence-model y+ field.
- Positive heat input enables a second OpenFOAM **fluid energy transport** solve on the computed frozen velocity/flux field. Uniform power enters through the inner wall; inlet temperature is fixed and the outlet has zero temperature gradient. The heat capacity, conductivity and turbulent Prandtl number are explicit inputs. 0 W runs flow only.
- Wall thickness and material are geometry metadata. **Solid conduction, temperature feedback on flow, buoyancy, radiation, viscous heating and phase change are not solved.** This is a constant-property forced-convection model, not conjugate heat transfer.
- No compressibility, cavitation, roughness, multiphase flow, gravity, bends, manifolds, or CAD meshing yet. The user must check that constant-property incompressible assumptions fit the selected fluid and conditions.
- Preview values use analytical geometry relations. Simulation results come from the written OpenFOAM fields.

## How results are computed

OpenFOAM's kinematic pressure is multiplied by density to obtain Pa. Pressure is averaged over each axial cell layer using cell-volume weights (equivalent to area weights because axial cell length is uniform). The displayed pressure drop spans the first and last **cell-centre stations**, whose coordinates are displayed; it is not silently treated as an exact inlet-to-outlet measurement.

The developed pressure gradient is fitted over 65–85% of the pipe length. The Darcy friction factor is `f = (-dp/dx) D / (rho U_bulk²/2)`. Drift between downstream fitting intervals and velocity profiles flags insufficient development. The velocity profile is sampled near 80% length. Boundary **face fluxes** from `phi` determine inlet/outlet mass conservation; interpolated cell-centre velocity is not used as a conservation measure.

The wedge approximates a cylinder with planar circumferential faces. Axial/radial refinement alone does not remove its small fixed angular approximation; use an angular-refinement study before claiming sub-percent geometric accuracy.

Thermal results use OpenFOAM's `scalarTransport` through the `functions` solver module with `incompressibleFluid` supplying the frozen fields. Diffusivity is `k/(rho Cp) + nut/Prt` (the turbulent term is omitted for laminar flow). The conservative first-order upwind temperature discretization is independent of the unchanged flow discretization. Outlet mixing temperature uses boundary face fluxes. The reported heat balance includes heat diffusing out of the fixed-temperature inlet. The Nusselt number uses the computed inner-wall and mixing temperatures; it is never used to generate those temperatures.

See [validation methods and sources](docs/VALIDATION.md), [flow benchmarks](docs/BENCHMARKS.md), [thermal benchmarks](docs/THERMAL_BENCHMARKS.md), and the [roadmap](docs/ROADMAP.md).

## Tests and reproducible CFD benchmarks

```bash
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend test
.venv/bin/python scripts/validate.py --case all
```

The final command runs all three presets on all three meshes and saves `validation-output/summary.json` and full cases. Allow tens of minutes for the complete serial study. For a short complete heating check use `--case heated_laminar --meshes coarse`. Validation has its own run directory. Experimental disagreements remain in the report; a solver failure or failed laminar/thermal verification gives a nonzero exit status. To repeat only the new energy solve on existing matching laminar benchmark fields, use `scripts/validate_thermal.py <coarse-case> <medium-case> <fine-case>`; it records the reused flow provenance.

## Source layout

| Component | Responsibility |
|---|---|
| `backend/app/models.py` | Validated inputs, regimes, benchmark presets |
| `backend/app/cases.py` | Pipe geometry and OpenFOAM case generation |
| `backend/app/runner.py` | Job queue, processes, cancellation and saved run records |
| `backend/app/results.py` | Field parsing, pressure/flow metrics and validation gates |
| `backend/app/thermal.py` | OpenFOAM fluid-energy subcase, heat balance and thermal verification |
| `backend/app/fields.py` | Actual mesh/cell data for the viewer and VTK export |
| `backend/app/references.py` | Reference data and provenance |
| `frontend/src` | Inputs, run monitoring, comparison plots and exports |

Future geometry generators can use the execution queue. The current section-based post-processor is pipe-specific; CAD and branching geometries will need boundary/surface-based result extraction.
