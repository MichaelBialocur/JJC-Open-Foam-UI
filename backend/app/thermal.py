"""Constant-property thermal solves on the computed, frozen flow field.

OpenFOAM solves div(phi,T) - laplacian(alpha_eff,T) = 0. This module
generates and measures the fluid-only case. Conjugate mode delegates generation
to native fluid/solid modules. Neither model obtains temperatures from a correlation.
"""
import json
from math import cos, pi, radians, sin
from pathlib import Path
import shutil

import numpy as np

from .cases import field, header
from .results import convergence, read_internal, read_patch
from .conjugate import prepare_conjugate, solid_metrics, WALL_REFERENCE

THERMAL_REFERENCE = {
    "kind": "analytical",
    "title": "Fully developed laminar pipe · uniform wall heat flux",
    "url": "https://archive.nptel.ac.in/content/storage2/courses/103105052/AdvHeatMass_L_29.pdf",
    "citation": "S. Chakraborty, NPTEL / IIT Kharagpur, Advanced Heat and Mass Transfer, Lecture 29, pp. 5–7.",
    "nusselt": 48 / 11,
    "conditions": "Smooth circular pipe; fully developed laminar velocity and temperature profiles; constant properties; negligible axial diffusion and viscous heating.",
    "caveat": "Analytical verification, not experimental validation. Turbulent heat transfer has no experimental qualification in this release.",
}


def prepare_thermal(case: Path, spec, flow_iteration):
    if spec.thermal_mode == "conjugate":
        return prepare_conjugate(case, spec, flow_iteration)
    thermal = case / "thermal"
    thermal.mkdir()
    shutil.copytree(case / "constant", thermal / "constant")
    (thermal / "0").mkdir()
    (thermal / "system").mkdir()
    flow_time = case / f"{flow_iteration:g}"
    for name in ("U", "p", "phi", "k", "omega", "nut"):
        if (flow_time / name).exists():
            shutil.copy2(flow_time / name, thermal / "0" / name)
    # Match the total power to the same full-pipe scaling used for face fluxes.
    # A planar 5-degree wedge's wall area differs from its ideal circular sector.
    wall_flux = spec.applied_heat_w / (pi * spec.diameter_m * spec.length_m) * cos(radians(2.5))
    tin = spec.inlet_temperature_c + 273.15
    (thermal / "0/T").write_text(field("T", "[0 0 0 1 0 0 0]", f"{tin:.14g}",
        f"type fixedValue; value uniform {tin:.14g};", "type zeroGradient;",
        f"type fixedGradient; gradient uniform {wall_flux / spec.thermal_conductivity_w_m_k:.14g}; value uniform {tin:.14g};"))
    diffusion = (f"diffusivity constant; D {spec.thermal_diffusivity:.14g};" if spec.selected_model == "laminar" else
                 f"diffusivity viscosity; alphal {1 / spec.prandtl:.14g}; alphat {1 / spec.turbulent_prandtl:.14g};")
    (thermal / "system/controlDict").write_text(header("controlDict") + f"""
application foamRun;
solver functions;
subSolver incompressibleFluid;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {spec.thermal_iterations};
deltaT 1;
writeControl timeStep;
writeInterval 50;
purgeWrite 2;
writeFormat ascii;
writePrecision 12;
writeCompression off;
runTimeModifiable false;
functions
{{
    fluidTemperature
    {{
        type scalarTransport;
        libs ("libsolverFunctionObjects.so");
        field T;
        {diffusion}
        executeControl timeStep;
        executeInterval 1;
        writeControl writeTime;
    }}
}}
""")
    (thermal / "system/fvSchemes").write_text((case / "system/fvSchemes").read_text().replace(
        "default none;", "default none;\n    div(phi,T) Gauss upwind;"))
    (thermal / "system/fvSolution").write_text(header("fvSolution") + """
solvers
{
    T { solver PBiCGStab; preconditioner DILU; tolerance 1e-11; relTol 0; }
}
SIMPLE { nNonOrthogonalCorrectors 0; }
""")
    (thermal / "thermal.foam").touch()
    (thermal / "manifest.json").write_text(json.dumps({"model": "passive-fluid-energy-v1", "inputs": spec.model_dump(),
        "flow_solution_iteration": flow_iteration, "wall_flux_on_planar_wedge_w_m2": wall_flux,
        "wedge_to_full_pipe_scale": 2 * pi / sin(radians(5)),
        "assumptions": ["Frozen computed velocity, flux and eddy viscosity", "Constant fluid properties",
                        "Uniform inner-wall heat input", "No solid, buoyancy, radiation, phase change or viscous dissipation"]}, indent=2))
    return thermal


def analyse_thermal(case, spec, flow_result):
    thermal = case / "thermal"
    coupled = spec.thermal_mode == "conjugate"
    region_path = "fluid/T" if coupled else "T"
    frozen = thermal / "0/fluid" if coupled else thermal / "0"
    times = sorted((p for p in thermal.iterdir() if p.is_dir() and p.name.isdigit() and int(p.name) > 0), key=lambda p: int(p.name))
    if len(times) < 2:
        raise ValueError("Thermal solver must write at least two states for the stationarity check.")
    latest = times[-1]
    centres = read_internal(case / "0/C", 3)
    n = len(centres)
    volumes = read_internal(case / "0/Vc", count=n)
    temperature = read_internal(latest / region_path, count=n)
    velocity = read_internal(frozen / "U", 3, n)
    nx, nr = spec.mesh_shape
    xs = np.unique(np.round(centres[:, 0], 11))
    sections = [np.flatnonzero(np.round(centres[:, 0], 11) == x) for x in xs]
    ordered = [ids[np.argsort(centres[ids, 1])] for ids in sections]
    if len(xs) != nx or any(len(ids) != nr for ids in ordered):
        raise ValueError("Thermal postprocessor expects the generated structured pipe mesh.")
    weights = [volumes[ids] * velocity[ids, 0] for ids in ordered]
    if any(np.any(w <= 0) for w in weights):
        raise ValueError("Reverse axial flow is unsupported by this pipe thermal comparison.")
    bulk = np.array([np.average(temperature[ids], weights=w) for ids, w in zip(ordered, weights)])
    # Foundation writes these BCs without values: evaluate their exact discrete
    # rules, fixedGradient = Towner + gradient/deltaCoeffs; zeroGradient = Towner.
    outer = np.array([ids[-1] for ids in ordered])
    wall_distance = spec.diameter_m / 2 * cos(radians(2.5)) - centres[outer, 1]
    wall_gradient = spec.applied_heat_w / (pi * spec.diameter_m * spec.length_m) * cos(radians(2.5)) / spec.thermal_conductivity_w_m_k
    wall = temperature[outer] + wall_gradient * wall_distance
    if coupled:
        wall = read_patch(latest / "fluid/T", "wall", nx)
    fluid_flux = spec.thermal_conductivity_w_m_k * (wall - temperature[outer]) / wall_distance
    outlet = temperature[ordered[-1]]
    # The original flow phi is volumetric; the native fluid module uses rho*phi.
    flow_path = case / f"{flow_result['solution_iteration']:g}"
    phi_out = read_patch(flow_path / "phi", "outlet", nr)
    phi_in = read_patch(flow_path / "phi", "inlet", nr)
    if np.any(phi_out <= 0) or np.any(phi_in >= 0):
        raise ValueError("Reverse boundary flux is unsupported by the thermal balance.")
    tin = spec.inlet_temperature_c + 273.15
    tout = float(np.average(outlet, weights=phi_out))
    full_scale = 2 * pi / sin(radians(5))
    rho_cp = spec.density_kg_m3 * spec.specific_heat_j_kg_k
    advected = float(np.sum(phi_out * (outlet - tin))) * rho_cp * full_scale
    dx = spec.length_m / nx
    inlet_areas = volumes[ordered[0]] / dx
    diffusivity = np.full(nr, spec.thermal_diffusivity)
    if spec.selected_model == "kOmegaSST":
        diffusivity += read_patch(frozen / "nut", "inlet", nr) / spec.turbulent_prandtl
    # Orthogonal inlet: fixed Tin, adjacent centre dx/2 inside. Positive means
    # diffusion carries heat out through the inlet. Outlet gradient is zero.
    inlet_conduction = float(np.sum(diffusivity * rho_cp * inlet_areas * (temperature[ordered[0]] - tin) / (dx / 2))) * full_scale
    kinetic = 0.0
    if coupled:
        kinetic = float(np.sum(phi_out * np.sum(velocity[ordered[-1]]**2, axis=1)/2) +
                        np.sum(phi_in) * spec.inlet_velocity_m_s**2/2) * spec.density_kg_m3 * full_scale
    energy_error = abs(advected + inlet_conduction + kinetic - spec.applied_heat_w) / spec.applied_heat_w * 100
    qnominal = spec.applied_heat_w / (pi * spec.diameter_m * spec.length_m)
    delta = wall - bulk
    if np.any(temperature <= 0):
        raise ValueError("Non-positive absolute temperature.")
    # Use the computed local interface flux in conjugate mode, circular-area
    # normalized with the same wedge correction as the global power balance.
    flux = fluid_flux / cos(radians(2.5)) if coupled else np.full(nx, qnominal)
    nus = np.divide(flux * spec.diameter_m, spec.thermal_conductivity_w_m_k * delta,
                    out=np.full(nx, np.nan), where=np.abs(delta) > 1e-12)
    region = (xs >= .65 * spec.length_m) & (xs <= .85 * spec.length_m)
    nu = float(np.mean(nus[region])) if np.all(np.isfinite(nus[region])) else None
    early = float(np.mean(nus[(xs >= .60 * spec.length_m) & (xs <= .75 * spec.length_m)]))
    late = float(np.mean(nus[(xs >= .75 * spec.length_m) & (xs <= .9 * spec.length_m)]))
    drift = abs(early - late) / abs(nu) * 100 if nu and np.isfinite(early+late) else None
    conv = convergence((case / "log.thermal").read_text(errors="replace"))
    scale = max(spec.ideal_temperature_rise, float(np.max(delta)), 1e-6)
    change = float(np.max(abs(temperature - read_internal(times[-2] / region_path, count=n)))) / scale
    solid = None
    if coupled:
        solid, outer_temperature = solid_metrics(thermal, spec, latest, times[-2], wall, fluid_flux, scale)
        change = max(change, solid["saved_field_change_over_temperature_scale"])
    residual_keys = ("h", "e") if coupled else ("T",)
    converged = (int(latest.name) == conv["iteration"] and
                 all(conv["residuals"].get(key, 1) < spec.residual_tolerance for key in residual_keys) and change < spec.residual_tolerance)
    if coupled:
        converged = converged and energy_error < .5 and solid["solid_energy_error_percent"] < .5 and solid["interface_local_flux_error_percent"] < .5
    conv.update(converged=converged, saved_field_change_over_temperature_scale=change,
                compared_iterations=[int(p.name) for p in times[-2:]], temperature_scale_k=scale)
    applicable = spec.selected_model == "laminar" and not coupled
    checks = {
        "flow_converged": flow_result["convergence"]["converged"],
        "temperature_converged": converged,
        "mass_balance_below_0_5_percent": flow_result["mass_balance_error_percent"] < .5,
        "energy_balance_below_0_5_percent": energy_error < .5,
        "inlet_conduction_below_1_percent_input": abs(inlet_conduction) / spec.applied_heat_w < .01,
        "developed_velocity_profile": flow_result["profile_drift_percent"] < 1 and flow_result["gradient_drift_percent"] < 2,
        "nusselt_drift_below_2_percent": drift is not None and drift < 2,
        "thermal_entrance_length_satisfied": .65 * spec.length_m / spec.diameter_m > .05 * spec.reynolds * spec.prandtl,
        "laminar_reference_applicable": applicable,
    }
    error = (nu / THERMAL_REFERENCE["nusselt"] - 1) * 100 if applicable and nu is not None else None
    status = "not_qualified"
    if all(checks.values()) and error is not None:
        status = "within_project_target" if abs(error) <= 2 else "outside_project_target"
    if coupled:
        checks = {key: checks[key] for key in ("flow_converged", "temperature_converged", "mass_balance_below_0_5_percent", "energy_balance_below_0_5_percent")}
        checks.update(solid_energy_balance_below_0_5_percent=solid["solid_energy_error_percent"] < .5,
                      local_interface_flux_mismatch_below_0_5_percent=solid["interface_local_flux_error_percent"] < .5,
                      interface_temperature_continuity=solid["interface_temperature_jump_k"] / scale < spec.residual_tolerance)
        status = "not_qualified" if not all(checks.values()) else ("within_project_target" if abs(solid["resistance_error_percent"]) <= 2 else "outside_project_target")
    result = {
        "source": "OpenFOAM scalarTransport on computed frozen flow", "solution_iteration": int(latest.name),
        "mode": spec.thermal_mode,
        "inlet_temperature_c": spec.inlet_temperature_c, "outlet_bulk_temperature_c": tout - 273.15,
        "maximum_fluid_temperature_c": float(max(temperature.max(), wall.max())) - 273.15,
        "applied_heat_w": spec.applied_heat_w, "advected_heat_w": advected,
        "inlet_conduction_loss_w": inlet_conduction, "energy_balance_error_percent": energy_error,
        "net_kinetic_energy_transport_w": kinetic,
        "ideal_adiabatic_temperature_rise_k": spec.ideal_temperature_rise,
        "wall_heat_flux_w_m2": qnominal, "prandtl": spec.prandtl,
        "heat_input_boundary": "solid outer wall" if coupled else "fluid inner wall",
        "developed_nusselt": nu, "nusselt_drift_percent": drift, "convergence": conv,
        "profile": [{"x_m": float(x), "bulk_temperature_c": float(b - 273.15),
                     "wall_temperature_c": float(w - 273.15), "nusselt": float(v) if np.isfinite(v) else None} for x, b, w, v in zip(xs, bulk, wall, nus)],
        "validation": {"status": status, "checks": checks,
                       "reference": WALL_REFERENCE if coupled else {**THERMAL_REFERENCE, "applicable": applicable},
                       "nusselt_error_percent": error, "project_target_percent": 2},
        "limitations": "One-way, constant-property fluid heating. Wall material/thickness do not affect this solve. No solid conduction, buoyancy, radiation or phase change. Turbulent Prandtl closure is unvalidated against thermal experiments.",
    }
    if coupled:
        result.update(source="OpenFOAM foamMultiRun · native fluid/solid energy on frozen computed flow", solid=solid,
                      outer_wall_heat_flux_w_m2=spec.applied_heat_w/(pi*(spec.diameter_m+2*spec.wall_thickness_mm/1000)*spec.length_m),
                      limitations="Steady radial and axial wall conduction with perfect contact, insulated solid ends and uniform outer heating. Constant properties and frozen flow; no buoyancy, radiation or phase change. Turbulent thermal closure is not experimentally validated.")
        result["validation"]["wall_resistance_error_percent"] = solid["resistance_error_percent"]
        for row, outer_t, q in zip(result["profile"], outer_temperature, flux):
            row.update(outer_wall_temperature_c=float(outer_t-273.15), inner_wall_heat_flux_w_m2=float(q))
    return result
