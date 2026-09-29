# Pipe CFD · v0.2

A local React/FastAPI interface to **Foundation OpenFOAM 14**. This release generates and checks a straight circular pipe mesh, runs steady incompressible flow, and compares computed results with an analytical solution or a traceable experiment.

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

1. Click **Laminar verification · Re 100**, then **Run simulation**.
2. Follow mesh generation, mesh checks, solving, and post-processing in the run panel.
3. Inspect pressure, the velocity profile, residual history, and the validation checks.
4. Click **Run three-mesh study** to queue coarse, medium, and fine cases.
5. Use **Princeton experiment · Re 41,727** for the first turbulent experimental comparison.

An unavailable OpenFOAM installation produces an explicit error. The software never returns analytical or reference curves as though they were CFD output. Runs and results persist under `runs/`; startup marks previously unfinished runs as interrupted. A cancelled or failed run keeps its logs and case for diagnosis. Download JSON, velocity CSV, or the complete OpenFOAM case ZIP. Extract the ZIP and open `pipe.foam` in ParaView for full field inspection.

## Physics and numerical scope

- Straight, smooth, circular pipe, a **5° axisymmetric wedge** with one circumferential cell.
- Uniform velocity inlet, no-slip wall, zero gauge pressure at the outlet.
- Constant density and dynamic viscosity entered by the user. Temperature is recorded; properties are **not** automatically temperature-dependent.
- Laminar below Re 2300; k–ω SST RANS from Re 4000. The transition interval is rejected explicitly. Regime cutoffs are application policy, not a universal prediction of transition.
- SST uses radial grading, near-zero wall k (1e-12 m²/s²), `omegaWallFunction`, and `nutLowReWallFunction`. The UI estimates y+ from the developed pressure gradient and first wall-cell position; it is a screening estimate, not an exported turbulence-model y+ field.
- Material and wall thickness are stored for the thermal stage. **Solid conduction and heat transfer are not solved. Nonzero heat input is rejected.**
- No compressibility, cavitation, roughness, multiphase flow, gravity, bends, manifolds, or CAD meshing yet. The user must check that constant-property incompressible assumptions fit the selected fluid and conditions.
- Preview values use analytical geometry relations. Simulation results come from the written OpenFOAM fields.

## How results are computed

OpenFOAM's kinematic pressure is multiplied by density to obtain Pa. Pressure is averaged over each axial cell layer using cell-volume weights (equivalent to area weights because axial cell length is uniform). The displayed pressure drop spans the first and last **cell-centre stations**, whose coordinates are displayed; it is not silently treated as an exact inlet-to-outlet measurement.

The developed pressure gradient is fitted over 65–85% of the pipe length. The Darcy friction factor is `f = (-dp/dx) D / (rho U_bulk²/2)`. Drift between downstream fitting intervals and velocity profiles flags insufficient development. The velocity profile is sampled near 80% length. Boundary **face fluxes** from `phi` determine inlet/outlet mass conservation; interpolated cell-centre velocity is not used as a conservation measure.

The wedge approximates a cylinder with planar circumferential faces. Axial/radial refinement alone does not remove its small fixed angular approximation; use an angular-refinement study before claiming sub-percent geometric accuracy.

See [validation methods and sources](docs/VALIDATION.md), [measured benchmark results](docs/BENCHMARKS.md), and the [development roadmap](docs/ROADMAP.md).

## Tests and reproducible CFD benchmarks

```bash
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
npm --prefix frontend run lint
.venv/bin/python scripts/validate.py --case all
```

The final command runs real OpenFOAM on all three meshes and saves `validation-output/summary.json` and full cases. Allow tens of minutes for the complete serial study; duration depends on your computer. For a short integration check use `--case laminar --meshes coarse`. Validation has its own run directory so it can coexist with the app. Experimental disagreements are reported, not tuned away or hidden; a solver failure or failed laminar verification gives a nonzero exit status.

## Source layout

| Component | Responsibility |
|---|---|
| `backend/app/models.py` | Validated inputs, regimes, benchmark presets |
| `backend/app/cases.py` | Pipe geometry and OpenFOAM case generation |
| `backend/app/runner.py` | Job queue, processes, cancellation and saved run records |
| `backend/app/results.py` | Field parsing, pressure/flow metrics and validation gates |
| `backend/app/references.py` | Reference data and provenance |
| `frontend/src` | Inputs, run monitoring, comparison plots and exports |

Future geometry generators can use the execution queue. The current section-based post-processor is pipe-specific; CAD and branching geometries will need boundary/surface-based result extraction.
