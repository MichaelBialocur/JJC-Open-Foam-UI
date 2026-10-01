# Development roadmap

## Delivered in v0.2

A straight-pipe flow workflow: typed inputs → axisymmetric mesh → mesh check → steady OpenFOAM solve → field extraction → reference comparison. Run history, cancellation, residuals, CSV/JSON/case export and three-level mesh studies are included.

## Delivered in v0.3

Round plot ticks and explicit zero baselines; interactive 3D pipe geometry; computed field slices, cell probes, temperature/speed/pressure colour maps and VTK export. A one-way fluid energy solve adds uniform inner-wall heating with explicit constant properties. Three laminar thermal meshes were checked against Nu = 48/11 and energy conservation; see the measured thermal benchmark report. The 3D view revolves the axisymmetric solution. Solid conduction followed in v0.4; full 3D flow followed in v0.6.

## Delivered in v0.4

Native coupled fluid/solid temperature solves with radial and axial wall conduction, outer-wall heating, insulated solid ends and perfect thermal contact. Wall material, conductivity and thickness affect the solution. Fluid/solid/combined temperature views, both wall-temperature profiles and solid VTK export are included. Three meshes, material/thickness sensitivity and independent interface/energy checks are recorded in [CONJUGATE_BENCHMARKS.md](CONJUGATE_BENCHMARKS.md).

## Delivered in v0.5

Velocity, volumetric-flow and mass-flow inlet choices with adjacent unit selectors, including L/min, kg/h and actual CFM. Compact fluid and wall-material selectors open separate property editors. Sourced water, air and glycol presets use constant 20 °C properties; aluminium and copper remain editable. Unit-equivalence tests preserve the existing benchmark solver inputs; the additional glycol mass-flow mesh study is documented in [INPUTS_AND_MATERIALS.md](../INPUTS_AND_MATERIALS.md).

## Delivered in v0.6

A connected pipe/bend/taper/manifold/multi-port builder, start/end sections, wall/web thickness, native CAD face selection, multiple heating and convection groups, conforming 3D fluid/solid tetrahedral meshes, steady OpenFOAM flow and coupled conduction, actual cell slices/probes, design persistence and case export. See [GEOMETRY_BUILDER.md](GEOMETRY_BUILDER.md) and [ASSEMBLY_BENCHMARKS.md](ASSEMBLY_BENCHMARKS.md).

## Next: improve 3D accuracy and add matched research data

First strengthen the flow baseline: the initial turbulent study still changes Darcy f by 3.74% from medium to fine. Extend mesh/angular sensitivity and compare corrected experimental data before claiming mesh independence or general model accuracy.

Selectable heated surfaces and external convection shipped in v0.6. Improve tetrahedral pressure-gradient accuracy and wall-layer resolution next, then add contact resistance and temperature-dependent properties where needed. Compare thermal predictions with a traceable heated-pipe experiment, including boundary conditions and measurement uncertainty; current analytical agreement is not experimental validation. Review field visualization while this is developed.

## Delivered in v0.7

Local STEP/STP, IGES/IGS and BREP import of closed bodies; explicit fluid/solid/ignore roles; declared unit conversion and checked scaling; selectable planar fluid inlet/outlet faces and exterior solid heating/convection groups; conformal tetrahedral meshing, fluid-only flow or coupled conduction, source/setup persistence, and separate deletable CAD run history. All 3D viewers use damped free rotation with pan/zoom and stable camera state during face selection. See [CAD_IMPORT.md](CAD_IMPORT.md) and [CAD_BENCHMARKS.md](CAD_BENCHMARKS.md). Native CAD solves and conservation pass, but pressure-gradient accuracy is still unqualified.

## Extend the geometry builder

The inline pipe → manifold → multi-port tube → manifold → pipe workflow is available. Next extend to general branch junctions and arbitrary header-port placement, add channel-resolved flow-distribution reporting and boundary-layer meshing, and validate pressure/temperature against matched cold-plate measurements.

## CAD and complex geometry

Closed-body CAD import shipped in v0.7. Extend it with automatic fluid-cavity extraction, a defined STL/OBJ surface-repair/volume pipeline, boundary layers, per-body solid materials, nonplanar ports and broader real engineering geometry qualification. The current importer requires an explicit connected fluid volume and rejects ambiguous open or overlapping bodies. Native feature-tree editing remains outside the solver UI.

## Visualization and model evidence

Evolve visualization with real user cases: slices, vectors, streamlines, pressure/temperature fields, wall heat flux and heat-transfer coefficients. Use actual computed fields. Keep published reference overlays and uncertainty/assumption notes accessible. Extend the reference suite as each model and geometry family is added.

## Architecture constraints

`cases.py` generates geometry independently of the job queue. The case manifest contains versioned inputs and named boundaries. Keep this separation as more geometry generators are introduced. Current flow-property and boundary schemas are deliberately pipe-specific; add versioned geometry/region/BC schemas for the builder rather than forcing CAD into pipe dimensions. Current `results.py` axial-section metrics are not a generic complex-geometry post-processor.
