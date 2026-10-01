"""Foundation 14 native fluid/solid energy solve on frozen computed flow.

Conformal mapped walls enforce temperature and heat-flux continuity. The solid
has axial and radial conduction, insulated ends, and prescribed outer power.
"""
import json
from math import cos, sin, pi, radians, log
import re
import shutil

import numpy as np

from .cases import field, header
from .results import read_internal, read_patch

WALL_REFERENCE = {
    "kind": "analytical", "applicable": True,
    "title": "Mean wall temperature drop · cylindrical conduction",
    "url": "https://archive.nptel.ac.in/content/storage2/courses/103103032/module2/lec6/1.html",
    "citation": "NPTEL, Heat Transfer, Module 2, Lecture 6, §2.3.1 (cylindrical conduction).",
    "conditions": "Steady constant-k annulus, no generation, insulated axial ends. Axial averaging reduces the solid conduction equation to the radial cylinder equation.",
    "caveat": "Analytical verification of the mean solid resistance, not experimental validation of conjugate heat transfer. Local inner-wall flux is not uniform: Nu = 48/11 is not a qualified reference for this mode.",
}


def mass_flux(text, density):
    """Convert every scalar FV flux, preserving the original conservative field."""
    text, n = re.subn(r"\[0\s+3\s+-1\s+0\s+0\s+0\s+0\]", "[1 0 -1 0 0 0 0]", text)
    if n != 1:
        raise ValueError("Expected one volumetric-flux dimensions entry.")
    def scale(match):
        return match[1] + "\n" + "\n".join(f"{float(v)*density:.16g}" for v in match[2].split()) + "\n);"
    text = re.sub(r"(nonuniform\s+List<scalar>\s+\d+\s*\()(.*?)\)\s*;", scale, text, flags=re.S)
    return re.sub(r"\buniform\s+([-+0-9.eE]+)\s*;", lambda m: f"uniform {float(m[1])*density:.16g};", text)


def prepare_conjugate(case, spec, flow_iteration):
    thermal = case / "thermal"
    thermal.mkdir()
    def put(path, text):
        dest = thermal / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    shutil.copytree(case / "constant/polyMesh", thermal / "constant/fluid/polyMesh")
    path = thermal / "constant/fluid/polyMesh/boundary"
    boundary, n = re.subn(r"(\bwall\s*\{\s*type\s+)wall;", r"\1mappedWall;\n neighbourRegion solid; neighbourPatch inner;", path.read_text())
    if n != 1:
        raise ValueError("Expected the generated pipe wall patch.")
    path.write_text(boundary)
    flow_time = case / f"{flow_iteration:g}"
    for name in ("U", "phi", "k", "omega", "nut"):
        if (flow_time / name).exists():
            text = (flow_time / name).read_text()
            put("0/fluid/" + name, mass_flux(text, spec.density_kg_m3) if name == "phi" else text)
    tin = spec.inlet_temperature_c + 273.15
    put("0/fluid/p", field("p", "[1 -1 -2 0 0 0 0]", "100000", "type zeroGradient;",
                          "type fixedValue; value uniform 100000;", "type zeroGradient;"))
    put("0/fluid/T", field("T", "[0 0 0 1 0 0 0]", f"{tin:.14g}", f"type fixedValue; value uniform {tin:.14g};",
                          "type zeroGradient;", f"type coupledTemperature; value uniform {tin:.14g};"))
    put("constant/fluid/physicalProperties", header("physicalProperties") + f"""
thermoType {{ type heRhoThermo; mixture pureMixture; transport const; thermo hConst;
             equationOfState rhoConst; specie specie; energy sensibleEnthalpy; }}
mixture {{ specie {{ molWeight 18; }} equationOfState {{ rho {spec.density_kg_m3:.14g}; }}
    thermodynamics {{ Cp {spec.specific_heat_j_kg_k:.14g}; Hf 0; }}
    transport {{ mu {spec.dynamic_viscosity_pa_s:.14g}; Pr {spec.prandtl:.14g}; }} }}
""")
    put("constant/fluid/momentumTransport", (case / "constant/momentumTransport").read_text())
    if spec.selected_model == "kOmegaSST":
        put("constant/fluid/thermophysicalTransport", header("thermophysicalTransport") +
            f"RAS {{ model eddyDiffusivity; Prt {spec.turbulent_prandtl:.14g}; }}\n")
        put("0/fluid/alphat", field("alphat", "[1 -1 -1 0 0 0 0]", "0", "type calculated; value uniform 0;",
                                  "type calculated; value uniform 0;", "type fixedValue; value uniform 0;"))
    # Only k affects this steady solid equation; rho/Cv are representative constants.
    rho, cv = spec.solid_density, spec.solid_specific_heat
    put("constant/solid/physicalProperties", header("physicalProperties") + f"""thermoType constSolidThermo;
rho {{ type uniform; value {rho}; }}
Cv {{ type uniform; value {cv}; }}
kappa {{ type uniform; value {spec.solid_conductivity:.14g}; }}
""")
    a, ri, length = radians(2.5), spec.diameter_m / 2, spec.length_m
    ro = ri + spec.wall_thickness_mm / 1000
    pts = [(x, r*cos(a), sign*r*sin(a)) for sign in (-1, 1) for r in (ri, ro) for x in (0, length)]
    vertices = " ".join("(" + " ".join(f"{v:.14g}" for v in p) + ")" for p in pts)
    put("system/solid/blockMeshDict", header("blockMeshDict") + f"""
vertices ({vertices});
blocks (hex (0 1 3 2 4 5 7 6) ({spec.mesh_shape[0]} {spec.solid_radial_cells} 1) simpleGrading (1 1 1));
edges ();
boundary (
inner {{ type mappedWall; neighbourRegion fluid; neighbourPatch wall; faces ((0 4 5 1)); }}
outer {{ type wall; faces ((2 3 7 6)); }}
inlet {{ type wall; faces ((0 2 6 4)); }}
outlet {{ type wall; faces ((1 5 7 3)); }}
front {{ type wedge; faces ((0 1 3 2)); }}
back {{ type wedge; faces ((4 6 7 5)); }}
); mergePatchPairs ();
""")
    power = spec.applied_heat_w * sin(2*a) / (2*pi)
    put("0/solid/T", header("T", "volScalarField") + f"""
dimensions [0 0 0 1 0 0 0]; internalField uniform {tin:.14g};
boundaryField {{
inner {{ type coupledTemperature; value uniform {tin:.14g}; }}
outer {{ type externalTemperature; Q constant {power:.14g}; value uniform {tin:.14g}; }}
inlet {{ type zeroGradient; }} outlet {{ type zeroGradient; }}
front {{ type wedge; }} back {{ type wedge; }} }}
""")
    put("system/controlDict", header("controlDict") + f"""application foamMultiRun;
regionSolvers {{ fluid fluid; solid solid; }}
startFrom startTime; startTime 0; stopAt endTime; endTime {spec.thermal_iterations};
deltaT 1; writeControl timeStep; writeInterval 50; purgeWrite 2;
writeFormat ascii; writePrecision 12; writeCompression off; runTimeModifiable false;
""")
    put("system/fvSolution", header("fvSolution") + "PIMPLE { nOuterCorrectors 1; nEnergyCorrectors 1; }\n")
    for region in ("fluid", "solid"):
        put(f"system/{region}/fvSchemes", header("fvSchemes") + """ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,h) Gauss upwind; div(phi,K) Gauss upwind; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; } snGradSchemes { default corrected; }
wallDist { method meshWave; }
""")
        solver = "PBiCGStab; preconditioner DILU" if region == "fluid" else "PCG; preconditioner DIC"
        put(f"system/{region}/fvSolution", header("fvSolution") + f"""solvers {{
"(h|hFinal|e|eFinal)" {{ solver {solver}; tolerance 1e-12; relTol 0; }} }}
PIMPLE {{ flow false; models false; thermophysics true; nNonOrthogonalCorrectors 0; }}
""")
    (thermal / "conjugate.foam").touch()
    put("manifest.json", json.dumps({"model": "conjugate-frozen-flow-v1", "inputs": spec.model_dump(),
        "flow_solution_iteration": flow_iteration, "solid_conductivity_w_m_k": spec.solid_conductivity,
        "solid_radial_cells": spec.solid_radial_cells, "wedge_outer_power_w": power,
        "assumptions": ["Frozen computed U, conservative phi and turbulence", "Constant properties; perfect thermal contact",
                        "Radial and axial solid conduction; insulated solid ends; uniform outer heat input",
                        "Native fluid enthalpy equation includes kinetic-energy transport; no buoyancy, radiation or phase change"]}, indent=2))
    return thermal


def solid_metrics(thermal, spec, latest, previous, fluid_wall, fluid_flux, scale):
    """Measure two independent interface fluxes and mean cylindrical resistance."""
    nx = spec.mesh_shape[0]
    centres = read_internal(thermal / "0/solid/C", 3)
    temperature = read_internal(latest / "solid/T", count=len(centres))
    prior = read_internal(previous / "solid/T", count=len(centres))
    xs = np.unique(np.round(centres[:, 0], 11))
    ordered = [ids[np.argsort(centres[ids, 1])] for x in xs for ids in [np.flatnonzero(np.round(centres[:, 0], 11) == x)]]
    if len(xs) != nx or any(len(ids) != spec.solid_radial_cells for ids in ordered):
        raise ValueError("Unexpected solid mesh ordering.")
    inner = read_patch(latest / "solid/T", "inner", nx)
    outer = read_patch(latest / "solid/T", "outer", nx)
    ri, ro = spec.diameter_m / 2, spec.diameter_m / 2 + spec.wall_thickness_mm / 1000
    owners = np.array([ids[0] for ids in ordered])
    solid_flux = spec.solid_conductivity * (temperature[owners] - inner) / (centres[owners, 1] - ri*cos(radians(2.5)))
    full_area = 2*pi*ri*spec.length_m / cos(radians(2.5))
    qfluid, qsolid = float(np.mean(fluid_flux)*full_area), float(np.mean(solid_flux)*full_area)
    expected = spec.applied_heat_w * log(ro/ri) / (2*pi*spec.length_m*spec.solid_conductivity)
    drop = float(np.mean(outer-inner))
    return {
        "conductivity_w_m_k": spec.solid_conductivity, "radial_cells": spec.solid_radial_cells,
        "maximum_temperature_c": float(max(outer.max(), temperature.max(), inner.max())) - 273.15,
        "mean_inner_temperature_c": float(inner.mean()) - 273.15, "mean_outer_temperature_c": float(outer.mean()) - 273.15,
        "mean_wall_drop_k": drop, "analytical_mean_wall_drop_k": expected,
        "resistance_error_percent": (drop/expected-1)*100,
        "interface_fluid_heat_w": qfluid, "interface_solid_heat_w": qsolid,
        "interface_energy_error_percent": abs(qfluid-qsolid)/spec.applied_heat_w*100,
        "interface_local_flux_error_percent": float(np.max(abs(fluid_flux-solid_flux)))*full_area/spec.applied_heat_w*100,
        "interface_temperature_jump_k": float(np.max(abs(fluid_wall-inner))),
        "solid_energy_error_percent": abs(qsolid-spec.applied_heat_w)/spec.applied_heat_w*100,
        "saved_field_change_over_temperature_scale": float(np.max(abs(temperature-prior)))/scale,
    }, outer
