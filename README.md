# Pipe CFD · v0.5

A local React/FastAPI interface to **Foundation OpenFOAM 14**. Generate a straight circular pipe, inspect its 3D geometry, mesh it, and solve steady flow and optional coupled fluid–solid heating. Inspect actual pressure, speed, fluid temperature and solid temperature fields, and compare results with traceable analytical or experimental references.

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

1. Click **Solid wall · conduction check**, choose **Coarse**, then **Run simulation**. The preset adds 10 W at the outside of a 2 mm aluminium wall around water entering at 20 °C, Re 100.
2. Follow meshing, flow and temperature stages. Inspect heat balance, outlet temperature, maximum solid temperature, interface continuity and the cylindrical wall-conduction comparison.
3. In **Computed field viewer**, choose speed, pressure or temperature. Orbit, zoom, select a cutaway/axial/cross-section view, move the section slider and click a cell to probe its values. **End view** looks down the pipe; **Reset view** restores the initial camera.
4. The axial colour map also supports probing. The optional section plot follows the slider. Colours are computed cell values without smoothing; a single global colour scale applies along the whole pipe.
5. Select **Region → Fluid + solid** for both computed temperature fields on one colour scale, or **Solid wall** to inspect only the annulus. White lines in the axial map mark the interface. **Enlarge diameter for viewing** states its scale factor; uncheck for true proportions.
6. Change wall thickness/material under **Wall geometry**. Choose aluminium or copper, then **Edit** to customize conductivity, density or heat capacity. The temperature plot shows inner and outer walls; a separate wall-drop plot resolves their small difference.
7. Click **Run three-mesh study** to compare flow and thermal metrics. **Heated pipe · analytical check** retains the fluid-only uniform inner-flux Nu benchmark. Use **Laminar verification · Re 100** for flow only or **Princeton experiment · Re 41,727** for the existing turbulent flow experiment.

An unavailable OpenFOAM installation produces an explicit error. The software never returns analytical or reference curves as CFD output. Runs and results persist under `runs/`; startup marks unfinished runs as interrupted. Cancelled/failed runs keep their logs and cases. Existing v0.2 flow runs can be viewed directly; run a new heated case to get temperatures.

Exports include results JSON, velocity CSV, thermal-profile CSV, separate fluid and solid meridional `.vtk` sections, and the full OpenFOAM case ZIP. For coupled heating, open **`thermal/conjugate.foam`** in ParaView and select the fluid and solid regions at the latest iteration. Original hydraulic pressure/velocity are in `pipe.foam`; the thermal subcase uses a constant thermodynamic pressure and frozen flow. For fluid-only heating, `pipe.foam` contains U, p and final T together, while `thermal/thermal.foam` retains the temperature history. These are steady-solver iterations, **not physical time**. Old saved runs retain their original thermal mode; they are not retroactively assigned solid temperatures.

The 3D display revolves an axisymmetric solution; it does not add a circumferential flow calculation. WebGL is used when available. Without WebGL, the interactive SVG geometry/cross-section and 2D axial map remain available. Linear charts use decimal 1/2/5 tick steps; pressure and speed include a clearly marked zero while retaining any actual negative data. Temperature charts can use a focused range, and residuals use integer powers of ten.

## Fluid, inlet units and material presets

Under **Fluid & flow**, choose water, dry air, or water with 30%/50% ethylene or propylene glycol **by mass**. Presets use CoolProp 7.2.0 at **20 °C and 1 atm**. Select **Edit** to inspect or change density, dynamic viscosity, heat capacity and thermal conductivity. **Apply properties** saves the edits; **Cancel** discards them and **Reset to preset** restores the source values. Property inputs stay hidden until the editor is opened. Wall materials use the same workflow under **Wall geometry**.

Choose an **Inlet boundary**, enter a value, and select its adjacent unit:

| Boundary | Available units |
|---|---|
| Velocity | m/s, cm/s, mm/s, km/h, ft/s |
| Volumetric flow | L/min, L/h, L/s, mL/min, m³/h, m³/s, CFM, US gal/min |
| Mass flow | kg/h, kg/min, kg/s, g/s |

Changing the boundary type or unit preserves the current physical flow. Editing the value changes the operating point. A fixed volumetric flow gives `U = Q/A`; a fixed mass flow gives `U = mass_flow/(rho A)`. Changing diameter or fluid density therefore updates the derived velocity as appropriate. The solver still applies a uniform mean-velocity inlet. Original input type, value and unit are retained with the run and its JSON export.

**CFM means actual cubic feet per minute**, using the international foot. It does not mean SCFM or another standard-condition gas volume. Properties remain constant during the simulation; changing inlet temperature does not update the property values. Glycol presets represent generic solutions, without inhibitor/additive effects. The editor shows each preset's source and assumptions. Benchmark buttons retain their original exact properties under **Custom / benchmark properties**, rather than replacing them with the new catalog.

See [property provenance, conversion checks and the glycol mesh study](INPUTS_AND_MATERIALS.md).

## Physics and numerical scope

- Straight, smooth, circular pipe, a **5° axisymmetric wedge** with one circumferential cell.
- Uniform velocity inlet, no-slip wall, zero gauge pressure at the outlet.
- Constant density, dynamic viscosity, heat capacity and fluid conductivity from an editable preset or explicit user values. Properties are **not** automatically temperature-dependent.
- Laminar below Re 2300; k–ω SST RANS from Re 4000. The transition interval is rejected explicitly. Regime cutoffs are application policy, not a universal prediction of transition.
- SST uses radial grading, near-zero wall k (1e-12 m²/s²), `omegaWallFunction`, and `nutLowReWallFunction`. The UI estimates y+ from the developed pressure gradient and first wall-cell position; it is a screening estimate, not an exported turbulence-model y+ field.
- Positive heat input enables a thermal solve on computed frozen velocity/flux/turbulence fields. In **Coupled fluid + solid wall** mode, native `foamMultiRun` fluid/solid modules solve radial and axial wall conduction with perfect thermal contact. Uniform power enters the **outer** wall; solid ends are insulated. Inlet fluid temperature is fixed and the outlet has zero temperature gradient. Wall thickness and conductivity affect the computed temperatures.
- **Fluid only** mode retains the prescribed inner-wall flux and `scalarTransport` benchmark. The heat capacity, fluid conductivity and turbulent Prandtl number are explicit inputs in both modes. 0 W runs flow only. The UI defaults to coupled mode; legacy API inputs with no mode retain fluid-only behavior.
- **Temperature feedback on flow, buoyancy, radiation, temperature-dependent properties and phase change are not solved.** Coupled mode includes the native fluid equation's kinetic-energy transport in its energy balance; it does not provide a viscous-heating model or a compressible flow calculation.
- No compressibility, cavitation, roughness, multiphase flow, gravity, bends, manifolds, or CAD meshing yet. The user must check that constant-property incompressible assumptions fit the selected fluid and conditions.
- Preview values use analytical geometry relations. Simulation results come from the written OpenFOAM fields.

## How results are computed

OpenFOAM's kinematic pressure is multiplied by density to obtain Pa. Pressure is averaged over each axial cell layer using cell-volume weights (equivalent to area weights because axial cell length is uniform). The displayed pressure drop spans the first and last **cell-centre stations**, whose coordinates are displayed; it is not silently treated as an exact inlet-to-outlet measurement.

The developed pressure gradient is fitted over 65–85% of the pipe length. The Darcy friction factor is `f = (-dp/dx) D / (rho U_bulk²/2)`. Drift between downstream fitting intervals and velocity profiles flags insufficient development. The velocity profile is sampled near 80% length. Boundary **face fluxes** from `phi` determine inlet/outlet mass conservation; interpolated cell-centre velocity is not used as a conservation measure.

The wedge approximates a cylinder with planar circumferential faces. Axial/radial refinement alone does not remove its small fixed angular approximation; use an angular-refinement study before claiming sub-percent geometric accuracy.

Fluid-only thermal results use OpenFOAM's `scalarTransport` through `functions` with `incompressibleFluid` supplying frozen fields. Coupled heating uses constant-density `fluid` and `solid` modules with conformal `mappedWall` / `coupledTemperature` interfaces, and disables flow/model updates. A separate 8/16/32-layer solid annulus shares the fluid mesh's axial stations. The fluid equation uses conservative upwind advection and `k/(rho Cp) + nut/Prt` diffusion (no turbulent term in laminar flow). Outlet mixing temperature uses boundary face fluxes. Heat balance includes inlet conduction and, in native coupled mode, net kinetic-energy transport.

Local Nu uses computed interface heat flux and wall/mixing temperatures. **Nu = 48/11 is not used to qualify coupled cases**, because solid axial conduction redistributes the inner-wall flux. Instead, compare the mean solid temperature drop with `Q ln(ro/ri)/(2 pi L k_s)`; insulated ends make this axial-mean relation valid even with axial conduction. Both interface fluxes, interface temperature continuity, whole-system energy balance and saved-field stationarity are checked. Fine coupled meshes use 2,000 thermal iterations by default; unconverged results remain flagged.

See [validation methods and sources](docs/VALIDATION.md), [flow benchmarks](docs/BENCHMARKS.md), [fluid-only thermal benchmarks](docs/THERMAL_BENCHMARKS.md), [coupled wall benchmarks](docs/CONJUGATE_BENCHMARKS.md), and the [roadmap](docs/ROADMAP.md).

## Tests and reproducible CFD benchmarks

```bash
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend test
.venv/bin/python scripts/validate.py --case all
```

The final command runs all four presets on all three meshes and saves `validation-output/summary.json` and full cases. Allow tens of minutes for the complete serial study. For a short complete coupled check use `--case heated_wall --meshes coarse`. Validation has its own run directory. Experimental disagreements remain in the report; a solver failure or failed laminar/thermal verification gives a nonzero exit status. To reuse existing converged flow fields for the thermal mesh study, use `scripts/validate_conjugate.py <coarse-case> <medium-case> <fine-case>` (or `validate_thermal.py` for fluid-only heating); provenance and exact inputs are recorded.

## Source layout

| Component | Responsibility |
|---|---|
| `backend/app/models.py` | Validated inputs, regimes, benchmark presets |
| `backend/app/material-catalog.json` | Shared unit factors and sourced fluid/wall presets |
| `backend/app/cases.py` | Pipe geometry and OpenFOAM case generation |
| `backend/app/runner.py` | Job queue, processes, cancellation and saved run records |
| `backend/app/results.py` | Field parsing, pressure/flow metrics and validation gates |
| `backend/app/thermal.py` | OpenFOAM fluid-energy subcase, heat balance and thermal verification |
| `backend/app/conjugate.py` | Native fluid/solid coupling, solid mesh, interface conservation and wall resistance |
| `backend/app/fields.py` | Actual mesh/cell data for the viewer and VTK export |
| `backend/app/references.py` | Reference data and provenance |
| `frontend/src` | Inputs, run monitoring, comparison plots and exports |

Future geometry generators can use the execution queue. The current section-based post-processor is pipe-specific; CAD and branching geometries will need boundary/surface-based result extraction.
