# Development roadmap

## Delivered in v0.2

A straight-pipe flow workflow: typed inputs → axisymmetric mesh → mesh check → steady OpenFOAM solve → field extraction → reference comparison. Run history, cancellation, residuals, CSV/JSON/case export and three-level mesh studies are included.

## Delivered in v0.3

Round plot ticks and explicit zero baselines; interactive 3D pipe geometry; computed field slices, cell probes, temperature/speed/pressure colour maps and VTK export. A one-way fluid energy solve adds uniform inner-wall heating with explicit constant properties. Three laminar thermal meshes were checked against Nu = 48/11 and energy conservation; see the measured thermal benchmark report. The 3D view revolves the axisymmetric solution. Solid conduction followed in v0.4; full 3D flow remains future work.

## Delivered in v0.4

Native coupled fluid/solid temperature solves with radial and axial wall conduction, outer-wall heating, insulated solid ends and perfect thermal contact. Wall material, conductivity and thickness affect the solution. Fluid/solid/combined temperature views, both wall-temperature profiles and solid VTK export are included. Three meshes, material/thickness sensitivity and independent interface/energy checks are recorded in [CONJUGATE_BENCHMARKS.md](CONJUGATE_BENCHMARKS.md).

## Delivered in v0.5

Velocity, volumetric-flow and mass-flow inlet choices with adjacent unit selectors, including L/min, kg/h and actual CFM. Compact fluid and wall-material selectors open separate property editors. Sourced water, air and glycol presets use constant 20 °C properties; aluminium and copper remain editable. Unit-equivalence tests preserve the existing benchmark solver inputs; the additional glycol mass-flow mesh study is documented in [INPUTS_AND_MATERIALS.md](../INPUTS_AND_MATERIALS.md).

## Next: stronger reference evidence and thermal boundary options

First strengthen the flow baseline: the initial turbulent study still changes Darcy f by 3.74% from medium to fine. Extend mesh/angular sensitivity and compare corrected experimental data before claiming mesh independence or general model accuracy.

Add selectable heated surfaces, external convection, contact resistance and temperature-dependent properties where needed. Compare thermal predictions with a traceable heated-pipe experiment, including boundary conditions and measurement uncertainty; current analytical agreement is not experimental validation. Review field visualization while this is developed.

## Geometry builder

Build a connected **pipe → manifold → multiport tube (plate of channels)** model. Represent parts, ports, materials and named boundary regions explicitly. Support channel count/dimensions, branches and junctions, then verify total conservation, pressure loss and flow distribution.

## CAD and complex geometry

Import CAD using a defined STEP/IGES or triangulated-surface pipeline; check units, watertightness and fluid/solid regions. Let the user select/name boundaries, define physical boundary conditions, generate a suitable mesh with boundary layers, inspect quality and run the solver. Full 3D geometry and surface-based post-processing replace the axisymmetric/section-specific assumptions.

## Visualization and model evidence

Evolve visualization with real user cases: slices, vectors, streamlines, pressure/temperature fields, wall heat flux and heat-transfer coefficients. Use actual computed fields. Keep published reference overlays and uncertainty/assumption notes accessible. Extend the reference suite as each model and geometry family is added.

## Architecture constraints

`cases.py` generates geometry independently of the job queue. The case manifest contains versioned inputs and named boundaries. Keep this separation as more geometry generators are introduced. Current flow-property and boundary schemas are deliberately pipe-specific; add versioned geometry/region/BC schemas for the builder rather than forcing CAD into pipe dimensions. Current `results.py` axial-section metrics are not a generic complex-geometry post-processor.
