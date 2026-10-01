# CAD import · v0.7.0

This workspace runs locally on the same Ubuntu/WSL2 installation as the builder. Gmsh/OpenCASCADE reads the CAD, generates a conformal volume mesh and writes Gmsh `.msh`; Foundation OpenFOAM 14 converts that mesh and solves the flow and optional solid/fluid heat transfer. The browser provides model preparation, navigation and results.

## Accepted files

| Format | This importer | Preparation |
|---|---|---|
| STEP `.step`, `.stp` | Recommended | Export closed solid bodies, including a separate fluid cavity. Preserves body topology better than surface-only exports. |
| IGES `.iges`, `.igs` | Accepted conditionally | Must contain closed volumes or shells that can be sewn into unambiguous closed volumes. Touching surface exports can lose body topology; export STEP if this happens. |
| OpenCASCADE BREP `.brep` | Accepted | Closed bodies; coordinates interpreted in mm. Apply an explicit scale if the exporter used another unit. |
| STL, OBJ | Not accepted here | OpenFOAM's `snappyHexMesh` has surface-mesh workflows for these, but this importer requires solid CAD topology. A separate surface-to-volume workflow is future work. |
| Native SolidWorks, Inventor, CATIA, Creo, Fusion projects; DWG/DXF | Not accepted directly | Export a 3D STEP model with the required bodies. A drawing or feature tree is not a CFD volume. |

OpenFOAM solves on a volume mesh. It does not directly simulate a STEP file or automatically identify its fluid regions. The [Gmsh API manual](https://gmsh.info/doc/texinfo/#Namespace-gmsh_002fmodel_002focc) documents BREP/STEP/IGES import; the [OpenFOAM 14 utilities guide](https://doc.cfd.direct/openfoam/user-guide-v14/standard-utilities) documents `gmshToFoam`; the [snappyHexMesh guide](https://doc.cfd.direct/openfoam/user-guide-v14/snappyhexmesh) describes triangulated-surface meshing.

## Prepare the CAD model

1. Create the volume occupied by the fluid as an actual **closed solid body** in your CAD software. Cap the flow openings with planar faces. This body represents fluid, not metal. The app does not extract cavities from a metal-only part.
2. Keep surrounding metal as separate, non-overlapping solid bodies if heating or cooling is needed. The fluid must touch the metal with coincident surfaces. All selected solid bodies must connect to the fluid, directly or through other selected solids.
3. Export these bodies together, preferably as STEP. Suppress irrelevant hardware and tiny details in CAD if they make meshing impractical. The importer does not invent missing faces, fill arbitrary holes or remove engineering features.
4. One connected fluid circuit is supported per run. Multiple fluid bodies may be selected if their union is connected. Separate sealed circuits need separate runs.

## Import and assign boundaries

1. Open **CAD import → Choose CAD file**. Use **Highlight** or click a visible body to identify it. Assign each body **Fluid volume**, **Solid material**, or **Ignore**. All bodies initially default to Ignore.
2. Check the bounding dimensions and volume in mm/mm³. STEP and IGES declared units are converted to mm automatically. BREP has no declared unit; for a BREP drawn in metres use scale **1000**. Scale **1** is normally correct for STEP.
3. Click **Prepare selected bodies**. The importer joins the fluid volumes and imprints touching fluid/solid surfaces to make a conformal mesh. Overlaps, disconnected selected solids and invalid volumes produce explicit errors.
4. Choose **Visible bodies → Fluid passages**. Select a planar exterior fluid face, choose **Inlet**, and click **Assign selected**. Repeat for **Outlet**. Multiple faces may belong to each port group. Their actual CAD inlet area and perimeter determine flow conversion and hydraulic diameter. Outlet pressure is 0 Pa gauge.
5. Choose **Solid bodies**. Select exterior faces and assign **Heating · total power** or **Cooling · convection to ambient**. Each heating group specifies total watts distributed by face area. Each convection group specifies `h` in W/m²K and ambient °C. Convection cools a hotter wall and warms a colder wall.
6. Set fluid, inlet value/units, temperature, solid material and mesh size. All selected solids share one material and perfect thermal contact. Click **Mesh & run simulation**.

Selection is purple; inlet blue, outlet green, heating orange and convection cyan. A face can have only one assignment. Remove its previous assignment before changing roles. Fluid–solid interfaces couple automatically and cannot be assigned external conditions. Unassigned fluid faces are no-slip adiabatic walls; unassigned exterior solid faces are insulated. A fluid-only model can run flow, but heating/convection currently requires solid bodies.

The inlet is a total volumetric-flow condition derived from the chosen velocity, volume-flow or mass-flow input and actual selected CAD area. It follows the local inward normal, including reversed or differently oriented ports. All inlet faces share one flow condition and temperature; all outlets share one pressure. The combined inlet hydraulic diameter provides a regime-screening estimate, not a local prediction for every branch.

Changing body roles or scale clears face assignments. Prepare and assign again. Exported face IDs remain stable when the same source and body/scale settings are replayed for volume meshing; re-exported CAD may have different topology and must be reassigned.

## Navigate the model

- **Left-drag:** free trackball rotation, including through both poles and roll.
- **Middle/right-drag:** pan.
- **Wheel/pinch:** zoom.
- **Click:** select a face or probe a computed cell. Drags, right-clicks and multi-touch gestures do not select faces.
- **Fit / reset view**, **Isometric**, **Along Z**, **Along X:** recover a useful view.

Face selection, boundary assignment, visible-body changes and triangle-wire toggles update existing meshes without recreating the renderer or resetting the camera. Damping updates on animation frames; idle views do not redraw continuously. Controls refresh their viewport position after scrolling either independent panel. GPU/WebGL rendering is preferred. If WebGL is unavailable, the app clearly labels the reduced-performance SVG fallback. Browser/GPU frame rate on Michael's PC has not yet been measured.

## Save, reopen and export

The editable CAD setup is saved in the browser and restored on returning to the tab. **Save setup** downloads its JSON; **Original CAD** downloads the unchanged uploaded file. To transfer a setup to a different installation, upload the same original CAD file first, then **Load saved setup**. The source hash must match. Saved CAD runs retain the source, resolved inputs, selected face IDs, mesh, logs and fields; the case ZIP includes the original CAD and manifest.

**Load this CAD setup** copies a saved run's inputs into the editor. Editing does not alter its saved results. CAD history supports the same cancellation and stopped-run deletion as the other workspaces. Deleting a run removes its case and results but retains the shared CAD source and editable setup.

## Local operation and limits

Stop the app with Ctrl+C. In PowerShell:

```powershell
wsl -d Ubuntu-24.04
```

Then in Ubuntu:

```bash
cd ~/projects/pipe-cfd
git pull --ff-only
bash scripts/setup.sh
bash scripts/start.sh
```

Open http://localhost:5173 and keep the terminal open. Setup installs the pinned Gmsh 4.15.2 Python package and required native libraries. Use Foundation OpenFOAM 14 and one backend worker; this release remains a localhost application.

Uploads default to 256 MiB per source file and stream to disk. For a larger file, set `PIPE_CFD_CAD_UPLOAD_BYTES` to the desired byte limit before starting, for example `export PIPE_CFD_CAD_UPLOAD_BYTES=536870912` for 512 MiB. Raw import/preparation previews have a 180-second timeout to release an unresponsive CAD request; simplify or split models that exceed it. Submitted 3D meshing/solver jobs have no application cell-count or elapsed-time cap, remain cancellable and retain finite iteration settings and mesh-quality gates. Practical capacity depends on memory, disk and the CAD's smallest features.

The current mesh is first-order tetrahedral without wall layers. The solver uses constant properties and steady incompressible flow, followed by frozen-flow coupled heat transfer. No buoyancy, radiation, contact resistance, phase change, moving geometry or temperature feedback on flow is included. Native execution and conservation have been tested, but the imported-pipe pressure-gradient comparison remains unqualified. Read [CAD_BENCHMARKS.md](CAD_BENCHMARKS.md) before relying on predictions.
