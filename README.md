# Pipe CFD · v0.7.0

A local React/FastAPI interface to **Foundation OpenFOAM 14**. Import closed CAD bodies or build connected piping, bends, manifolds and multi-port cold plates; select flow and thermal boundaries; mesh and solve full 3D flow with coupled solid conduction. The separate straight-pipe workspace retains its axisymmetric reference benchmarks. All result viewers use actual computed fields.

**New in 0.7.0:** the **CAD import** workspace accepts STEP/STP, IGES/IGS and BREP closed bodies. Identify the fluid and solid volumes, then select inlet/outlet faces, heated faces and convection cooling faces. All 3D viewers now use damped free rotation, pan and zoom; selecting faces preserves the camera and renderer. [CAD import guide](docs/CAD_IMPORT.md) · [CAD benchmark results and remaining errors](docs/CAD_BENCHMARKS.md).

Saved-run deletion, independent desktop panel scrolling and uncapped 3D solver elapsed time/cell count remain available. Larger meshes depend on available RAM, disk space and practical runtime; cancellation, iteration settings and mesh-quality checks remain active. The 3D solver remains an early workflow, not an experimentally validated cold-plate predictor.

## Start on your Windows PC

Stop the existing app with **Ctrl+C**, then open PowerShell and enter Ubuntu:

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

## First builder run

Choose **Geometry builder**, use the cold-plate template, and click **Build geometry**. Select exterior faces and assign heating in watts or convection with a coefficient and ambient temperature. Set fluid, inlet flow and mesh size, then **Mesh & run simulation**. See the [step-by-step builder guide](docs/GEOMETRY_BUILDER.md). The first setup may ask for your Ubuntu password to install Gmsh native libraries.

## First CAD run

Choose **CAD import → Choose CAD file**. STEP is recommended. Export the **fluid cavity as its own closed body**, with separate surrounding metal bodies for heat transfer. Assign body roles, check dimensions, and click **Prepare selected bodies**. Select planar exterior fluid faces for inlet/outlet and exterior solid faces for heating/convection. Set operating conditions and mesh size, then **Mesh & run simulation**. A metal part alone does not define its internal fluid volume. STL/OBJ and native CAD project files are not accepted by this solid-body importer; see the [format and preparation guide](docs/CAD_IMPORT.md).

Left-drag freely rotates the model, middle/right-drag pans, and the wheel or pinch zooms. **Fit / reset view** recentres the geometry. Rotation can pass through either pole and roll; face selection and assignment do not reset the view. WebGL provides the interactive rendering path; the SVG fallback is explicitly labelled as reduced performance.

## Panels and saved runs

On desktop, the controls on the left and the geometry/results on the right have independent vertical scrollbars. The workspace tabs and header stay visible. Hover either panel to scroll it, or focus the panel to scroll with the keyboard. Narrow screens retain the stacked page layout.

Each workspace shows all its saved runs. Use **Delete** on a run card, or tick several cards and choose **Delete selected**. **Select all stopped runs** selects the deletable runs in that workspace only. Confirming deletion permanently removes the selected results, logs, meshes and OpenFOAM case files. Download any wanted exports first. Current inputs, the geometry draft and other runs remain available.

Queued/running jobs cannot be deleted. Select the job, cancel it, and wait for its status to become cancelled. Completed, unconverged, failed, interrupted and cancelled runs can be deleted. Deleting the displayed run clears its results; deleting a mesh-study member also removes that row from the comparison. Deleted runs stay removed after restarting the app.

## First straight-pipe benchmark run

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
- No compressibility, cavitation, roughness, multiphase flow or gravity. Bends and inline manifolds are available in the geometry-builder workspace; closed CAD bodies use the separate CAD import workspace. The wedge and radial grading above apply only to straight-pipe benchmarks. Builder/CAD runs use full 3D tetrahedra without boundary layers. The user must check that constant-property incompressible assumptions fit the selected fluid and conditions.
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
.venv/bin/python scripts/validate_cad.py
```

`validate.py` runs all four presets on all three meshes and saves `validation-output/summary.json` and full cases. Allow tens of minutes for the complete serial study. For a short complete coupled check use `--case heated_wall --meshes coarse`. Validation has its own run directory. Experimental disagreements remain in the report; a solver failure or failed laminar/thermal verification gives a nonzero exit status. To reuse existing converged flow fields for the thermal mesh study, use `scripts/validate_conjugate.py <coarse-case> <medium-case> <fine-case>` (or `validate_thermal.py` for fluid-only heating); provenance and exact inputs are recorded.

`validate_cad.py` generates and imports a STEP fluid/solid pipe, assigns boundaries through the API, and runs three actual OpenFOAM flow/thermal meshes. It saves `validation-output/cad-v070/summary.json` and cases. Its exit code checks execution only; inspect convergence and analytical deviations in the report. See [CAD_BENCHMARKS.md](docs/CAD_BENCHMARKS.md) for fluid-only, reverse-flow and partial-wall checks.

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
| `backend/app/cad_api.py`, `cad_models.py`, `cad_geometry.py` | CAD uploads, explicit body/face roles, units and conformal volume meshing |
| `frontend/src/cadControls.js` | Shared free-orbit navigation, damping and click-versus-drag handling |
| `frontend/src` | Inputs, run monitoring, comparison plots and exports |

The builder and CAD importer share the execution queue and arbitrary-mesh, boundary-face and cell-slice post-processing. The older section-based post-processor remains specific to the straight-pipe benchmark. CAD sources and prepared geometry are cached locally under `runs/`; each submitted CAD run keeps its own source copy and exact assignments.
