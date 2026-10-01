# Geometry builder · v0.6

Open **Geometry builder** in the workspace tabs. **Straight-pipe benchmark** keeps the existing axisymmetric reference workflow.

![Actual builder CAD view: orange heated faces and cyan convection faces](assembly-preview.png)

## Build a cold plate

1. Start with **Pipe → multi-port cold plate → pipe**, or a straight pipe / elbow template.
2. Select a part in the ordered list. Edit its length, start/end internal diameter and wall thickness. Different start/end dimensions make a taper. Rectangular dimensions are **outside** width and height; the wall is subtracted to obtain the passage.
3. For a bend, set centreline radius, turn angle and bend-plane rotation. Rotation 0° turns toward the local width direction; 90° turns toward local height. Constant-section bends use an exact circular sweep; tapered bends use a loft through sections spaced at most 15° apart. The latter is an approximation, not an exact variable-section torus.
4. Use **Add at outlet** for a straight/tapered tube, bend, transition/manifold or multi-port tube. Adding a multi-port tube after round piping inserts an inlet transition automatically. Add an outlet manifold to return to round piping. A multi-port tube has parallel rectangular channels separated by conducting webs. Edit channel count and web thickness, as well as the start/end outside dimensions and wall thickness.
5. Connected ends share section dimensions. Editing an end updates its neighbour. In **Assembly position & orientation**, set the inlet X/Y/Z position, yaw and pitch. The subsequent endpoints follow the connected lengths and turns; the coordinate table shows their calculated positions after building.
6. Click **Build geometry**. Orbit, zoom, use Along Z / Along X views and inspect **Show fluid passages**. The preview has true proportions and millimetre dimensions. Invalid cavities, disconnected section dimensions, intersecting parts and failed CAD operations produce errors.

One ordered assembly can contain up to 40 parts and each multi-port section up to 64 channels. This is an inline transition/header builder. It does not yet construct arbitrary branched networks, separate inlet/outlet plenums with arbitrary port placement, contact assemblies, or imported CAD.

## Apply heating and cooling

Click exterior faces in the 3D view or check them in **Exterior face list**. Any number of the available exterior faces can be selected. The fluid inlet/outlet and internal fluid–solid interfaces are not selectable exterior thermal faces.

- **Heating · total power:** assign a group and enter watts. The total is distributed over its faces by actual mesh area. For example, 10 W across two equal faces gives 5 W per face. Add separate groups to prescribe different powers on different faces.
- **Convection:** specify `h` in W/(m² K) and ambient temperature in °C. The boundary removes `h (T_surface − T_ambient)` per unit area; a colder surface can receive heat from ambient. This is a prescribed external film coefficient, not a simulated external cooling flow.
- Unassigned exterior faces are insulated. A face belongs to one group. Remove its existing group before reassigning it. Heating and convection cannot occupy the same face in this release.

The entire wall and all channel webs use the selected solid material. Native conjugate heat transfer couples this solid to the flowing fluid with perfect thermal contact. Use the compact fluid/material presets and **Edit** to change properties. They remain constant during the run. Inlet choices retain velocity, actual volumetric flow and mass flow, with their unit selectors. Mass flow uses the chosen density.

Any geometry edit clears existing face assignments and requires rebuilding. Saved designs preserve their geometry-bound face selections; rebuilding verifies the geometry identity. **Save design** / **Load design** exchange this program's parametric JSON, not CAD. The current draft is also saved in this browser. Simulation snapshots are separate from the editable draft; **Load this design** restores a saved run's inputs.

## Mesh, run and inspect

Set the target cell size in mm, then click **Mesh & run simulation**. Gmsh/OpenCASCADE creates a conforming fluid/solid tetrahedral mesh, converted to metres for Foundation OpenFOAM 14. Both regions must pass `checkMesh`. The cap is 600,000 total cells. The preview tessellation is not the volume mesh; narrow features and curvature affect the actual cell count. Repeat a run with a smaller target to assess mesh sensitivity.

Volume/mass inlets enforce the requested flow on the polygonal inlet mesh. Velocity inlets impose the specified mean vector, so their actual flow differs slightly from ideal CAD area × velocity on a coarse curved mesh. The results report both inlet areas and actual face-integrated flow.

The serial queue retains progress, logs, cancellation and saved runs. Flow is solved first. If any thermal group exists, computed flow is frozen while the native fluid/solid modules solve temperature. A convection-only model still runs the thermal solver. Flow and thermal convergence flags remain separate from conservation and reference checks.

The result viewer offers fluid pressure/speed/temperature and solid temperature, surfaces and X/Y/Z slices, orbit/zoom, rounded colour ticks and cell probes. Slices intersect actual finite-volume cells. Surface facets display their adjacent **cell** value; they are not reconstructed surface temperatures. The boundary table separately reports area-averaged surface temperature and independent face powers. Positive table power leaves the solid; heating has negative outgoing power.

Download **Results JSON** or the **OpenFOAM case / ParaView** ZIP. Open `assembly.foam` for hydraulic U/p, and `thermal/conjugate.foam` for the fluid/solid temperatures. Select the latest written time. The thermal subcase holds thermodynamic pressure constant; use the hydraulic case for pressure-drop visualization. ParaView provides additional filters and streamlines.

## Current numerical limits

The builder is an early engineering workflow. Read [the measured 3D benchmark report](ASSEMBLY_BENCHMARKS.md) before relying on its predictions: the finest tested 3D straight-pipe friction factor is still 12.13% above its analytical reference, and the tested cold-plate pressure drop changes by about 4.92% from the medium to fine mesh. Good conservation is not proof of accuracy or mesh independence.

Full 3D turbulence has not been benchmarked in this release; the older axisymmetric experimental comparison does not qualify an arbitrary assembly. Automatic regime selection uses inlet hydraulic diameter and Reynolds number, while local channel/manifold regimes may differ. Tetrahedral meshes currently have no dedicated boundary-layer inflation; assess wall resolution separately for SST.

No buoyancy, compressibility, radiation, phase change, temperature-dependent properties, transient heating, roughness or thermal contact resistance is modeled. There is no claim of experimental cold-plate validation. The reference suite must be expanded using matched geometry, operating conditions and research measurements as the tool develops.

## Setup and repeatable checks

Stop the existing app with Ctrl+C. In PowerShell:

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

Setup installs Gmsh 4.15.2. Its first run may request your **Ubuntu sudo password** to install `libglu1-mesa`, `libxft2` and `libxrender1`. Open http://localhost:5173 and keep the terminal open.

For development checks:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
.venv/bin/python scripts/validate_assembly.py
```

Tests additionally require `pytest` and `httpx`. The validation script requires Foundation OpenFOAM 14 and writes reproducible cases and a summary under ignored `validation-output/assembly`. It runs three pipe meshes, three heated/cooled cold-plate meshes and an elbow flow smoke test. Case summaries preserve unqualified results.
