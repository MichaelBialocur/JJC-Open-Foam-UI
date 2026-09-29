# Development roadmap

## Delivered in v0.2

A straight-pipe flow workflow: typed inputs → axisymmetric mesh → mesh check → steady OpenFOAM solve → field extraction → reference comparison. Run history, cancellation, residuals, CSV/JSON/case export and three-level mesh studies are included. The thermal UI metadata is preserved, with nonzero heat rejected until an energy model exists.

## Next: heat transfer in the pipe

Add coupled fluid/solid regions, conduction through aluminium/copper walls, explicit heated surface selection, coolant heating and energy conservation. Validate temperature and Nusselt-number outputs against appropriate research data and analytical limiting cases. Review field visualization while this is developed.

## Geometry builder

Build a connected **pipe → manifold → multiport tube (plate of channels)** model. Represent parts, ports, materials and named boundary regions explicitly. Support channel count/dimensions, branches and junctions, then verify total conservation, pressure loss and flow distribution.

## CAD and complex geometry

Import CAD using a defined STEP/IGES or triangulated-surface pipeline; check units, watertightness and fluid/solid regions. Let the user select/name boundaries, define physical boundary conditions, generate a suitable mesh with boundary layers, inspect quality and run the solver. Full 3D geometry and surface-based post-processing replace the axisymmetric/section-specific assumptions.

## Visualization and model evidence

Evolve visualization with real user cases: slices, vectors, streamlines, pressure/temperature fields, wall heat flux and heat-transfer coefficients. Use actual computed fields. Keep published reference overlays and uncertainty/assumption notes accessible. Extend the reference suite as each model and geometry family is added.

## Architecture constraints

`cases.py` generates geometry independently of the job queue. The case manifest contains versioned inputs and named boundaries. Keep this separation as more geometry generators are introduced. Current flow-property and boundary schemas are deliberately pipe-specific; add versioned geometry/region/BC schemas for the builder rather than forcing CAD into pipe dimensions. Current `results.py` axial-section metrics are not a generic complex-geometry post-processor.
