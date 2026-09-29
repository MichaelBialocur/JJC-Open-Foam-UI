"""Read real solver output and qualify comparisons; never substitute reference data."""
import json
from math import cos, radians, sin, pi
import re
from pathlib import Path

import numpy as np

from .references import reference_for

NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"


def read_internal(path: Path, components=1, count=None):
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", path.read_text(), flags=re.S)
    match = re.search(r"internalField\s+nonuniform\s+List<(?:scalar|vector)>\s+(\d+)\s*\((.*?)\)\s*;", text, re.S)
    if match:
        n = int(match[1])
        values = np.fromstring(match[2].replace("(", " ").replace(")", " "), sep=" ")
        if values.size != n * components or (count is not None and n != count):
            raise ValueError(f"Wrong number of values in {path.name}")
        values = values.reshape((n, components)) if components > 1 else values
    else:
        match = re.search(r"internalField\s+uniform\s+(.*?);", text, re.S)
        if not match or count is None:
            raise ValueError(f"Cannot read an ASCII internal field from {path}")
        row = np.fromstring(match[1].replace("(", " ").replace(")", " "), sep=" ")
        if row.size != components:
            raise ValueError(f"Invalid uniform field in {path}")
        values = np.tile(row, (count, 1)) if components > 1 else np.full(count, row[0])
    if not np.all(np.isfinite(values)):
        raise ValueError(f"Non-finite solver values in {path}")
    return values


def convergence(log: str):
    iteration = 0
    rows = {}
    for line in log.splitlines():
        match = re.match(r"Time = (\d+(?:\.\d+)?)", line)
        if match:
            iteration = int(float(match[1]))
        match = re.search(rf"Solving for (\w+), Initial residual = ({NUMBER})", line)
        if match:
            values = rows.setdefault(iteration, {"iteration": iteration})
            # First pressure solve of each outer iteration, not its corrected residual.
            values.setdefault(match[1], float(match[2]))
    history = list(rows.values())
    stride = max(1, len(history) // 250)
    sampled = history[::stride]
    if history and (not sampled or sampled[-1] != history[-1]):
        sampled.append(history[-1])
    return {"iteration": iteration, "solver_converged": bool(re.search(r"(?:SIMPLE|PIMPLE) solution converged", log)),
            "residuals": history[-1] if history else {}, "history": sampled}


def patch_flux(path: Path, name, count):
    """Sum finite-volume face fluxes, not interpolated cell-centre velocities."""
    text = path.read_text()
    match = re.search(r"\b" + re.escape(name) + r"\s*\{([^{}]*)\}", text, re.S)
    if not match:
        raise ValueError(f"Missing {name} flux patch")
    block = match[1]
    values = re.search(r"value\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;", block, re.S)
    if values:
        data = np.fromstring(values[2], sep=" ")
        if int(values[1]) != count or data.size != count:
            raise ValueError(f"Unexpected {name} flux size")
        total = float(data.sum())
    else:
        value = re.search(rf"value\s+uniform\s+({NUMBER})\s*;", block)
        if not value:
            raise ValueError(f"No flux values on {name}")
        total = float(value[1]) * count
    if not np.isfinite(total):
        raise ValueError("Non-finite boundary flux")
    return total


def analyse(case: Path, spec):
    times = sorted((p for p in case.iterdir() if p.is_dir() and re.fullmatch(NUMBER, p.name) and float(p.name) > 0), key=lambda p: float(p.name))
    if not times:
        raise ValueError("Solver did not write a solution time directory.")
    latest = times[-1]
    centres = read_internal(case / "0/C", 3)
    n = len(centres)
    volumes = read_internal(case / "0/Vc", count=n)
    if np.any(volumes <= 0):
        raise ValueError("Non-positive cell volume.")
    pressure = read_internal(latest / "p", count=n) * spec.density_kg_m3
    velocity = read_internal(latest / "U", 3, n)
    x = np.round(centres[:, 0], 11)
    xs = np.unique(x)
    if len(xs) < 10:
        raise ValueError("Insufficient axial sampling stations.")
    sections = [np.flatnonzero(x == station) for station in xs]
    ps = np.array([np.average(pressure[ids], weights=volumes[ids]) for ids in sections])
    us = np.array([np.average(velocity[ids, 0], weights=volumes[ids]) for ids in sections])
    bulk = spec.inlet_velocity_m_s

    def gradient(a, b):
        selected = (xs >= a * spec.length_m) & (xs <= b * spec.length_m)
        slope, intercept = np.polyfit(xs[selected], ps[selected], 1)
        return -float(slope), selected, intercept

    grad, region, intercept = gradient(.65, .85)
    g1, _, _ = gradient(.60, .75)
    g2, _, _ = gradient(.75, .90)
    drift = abs(g1 - g2) / max(abs(grad), 1e-30) * 100
    qin = -patch_flux(latest / "phi", "inlet", spec.mesh_shape[1])
    qout = patch_flux(latest / "phi", "outlet", spec.mesh_shape[1])
    if qin <= 0 or qout <= 0:
        raise ValueError("Inlet or outlet net flux is reversed or zero.")
    mass_error = abs(qout / qin - 1) * 100
    profile_index = int(np.argmin(abs(xs / spec.length_m - .8)))
    ids = sections[profile_index]
    radius = np.linalg.norm(centres[ids, 1:], axis=1)
    order = np.argsort(radius)
    rs = radius[order] / (spec.diameter_m / 2)
    speeds = velocity[ids[order], 0]
    # Radial coordinates are identical at every axial station in this mesh.
    early = sections[int(np.argmin(abs(xs / spec.length_m - .65)))]
    early = early[np.argsort(np.linalg.norm(centres[early, 1:], axis=1))]
    profile_drift = float(np.sqrt(np.mean(((velocity[early, 0] - speeds) / bulk)**2)) * 100)
    darcy = grad * spec.diameter_m / (.5 * spec.density_kg_m3 * bulk**2)
    yplus = float(np.sqrt(max(grad, 0) * spec.diameter_m / (4 * spec.density_kg_m3)) *
                  (spec.diameter_m / 2 * cos(radians(2.5)) - max(radius)) / spec.nu)
    conv = convergence((case / "log.foamRun").read_text(errors="replace"))
    final_field_written = float(latest.name) == conv["iteration"]
    # Relative residuals of a round-off-level swirl velocity can be noisy.
    # An iteration-limit exit is never labelled "solver converged". Instead,
    # independently check physical residuals AND changes over saved states.
    last = conv["residuals"]
    swirl_ratio = float(np.max(np.abs(velocity[:, 2])) / bulk)
    small_swirl = swirl_ratio < 1e-10
    required = ["p", "Ux", "Uy"] + ([] if small_swirl else ["Uz"])
    if spec.selected_model == "kOmegaSST":
        required += ["k", "omega"]
    residuals_ok = all(last.get(key, float("inf")) < spec.residual_tolerance for key in required)
    du = dp = None
    stationary = False
    if len(times) >= 2 and float(times[-1].name) - float(times[-2].name) >= 10:
        previous = times[-2]
        du = float(np.max(np.abs(velocity - read_internal(previous / "U", 3, n))) / bulk)
        dp = float(np.max(np.abs(pressure - read_internal(previous / "p", count=n) * spec.density_kg_m3)) /
                   (.5 * spec.density_kg_m3 * bulk**2))
        stationary = du < spec.residual_tolerance and dp < spec.residual_tolerance
    conv.update(converged=final_field_written and (conv["solver_converged"] or (residuals_ok and stationary)),
                final_field_written=final_field_written,
                physical_residuals_passed=residuals_ok, saved_field_stationarity_passed=stationary,
                compared_solution_iterations=[float(t.name) for t in times[-2:]],
                field_change_U_over_bulk=du, field_change_p_over_dynamic_pressure=dp,
                maximum_swirl_over_bulk=swirl_ratio,
                negligible_swirl_residual_excluded=small_swirl,
                convergence_basis="Final solver iteration was not written; comparison is unqualified" if not final_field_written else
                    "OpenFOAM stop criterion" if conv["solver_converged"] else
                    ("Independent residual and saved-field stationarity checks passed; solver reached iteration limit"
                     if residuals_ok and stationary else
                     "Convergence checks did not pass; solver reached iteration limit"))
    ref = reference_for(spec)
    f_error = ((darcy / ref["darcy_friction_factor"] - 1) * 100) if ref["applicable"] else None
    ref_values = None
    profile_points = 0
    if spec.selected_model == "laminar":
        ref_values = 2 * (1 - rs**2)
        profile_error = float(np.sqrt(np.mean((speeds / bulk - ref_values)**2)) * 100)
        profile_points = len(rs)
    elif ref["applicable"]:
        points = ref["profile"]
        rx = np.array([p["r_over_R"] for p in points])
        ry = np.array([p["u_over_bulk"] for p in points])
        common = (rx >= min(rs)) & (rx <= max(rs))
        profile_points = int(common.sum())
        profile_error = float(np.sqrt(np.mean((np.interp(rx[common], rs, speeds / bulk) - ry[common])**2)) * 100)
    else:
        profile_error = None
    ref_profile = ([{"r_over_R": float(r), "u_over_bulk": float(u)} for r, u in zip(rs, ref_values)]
                   if ref_values is not None else ref.get("profile", []))
    checks = {
        "solution_converged": conv["converged"],
        "mass_balance_below_0_5_percent": mass_error < .5,
        "gradient_drift_below_2_percent": drift < 2,
        "profile_drift_below_1_percent": profile_drift < 1,
        "positive_pressure_gradient": grad > 0,
        "near_wall_resolution": spec.selected_model == "laminar" or 0 < yplus <= 2,
        "reference_conditions_matched": ref["applicable"],
    }
    qualified = all(checks.values())
    target = 2 if ref["kind"] == "analytical" else 10
    status = "comparison_ready" if qualified else "not_qualified"
    if qualified:
        status = "within_project_target" if abs(f_error) <= target and profile_error <= target else "outside_project_target"
    result = {
        "source": "OpenFOAM computed fields", "solution_iteration": float(latest.name),
        "pressure_drop_pa": float(ps[0] - ps[-1]),
        "pressure_drop_stations_m": [float(xs[0]), float(xs[-1])],
        "developed_pressure_gradient_pa_m": grad,
        "fit_stations_m": [float(xs[region][0]), float(xs[region][-1])],
        "darcy_friction_factor": darcy,
        "mass_flow_kg_s": (qin + qout) / 2 * (2 * pi / sin(radians(5))) * spec.density_kg_m3,
        "mass_balance_error_percent": mass_error, "gradient_drift_percent": drift,
        "profile_drift_percent": profile_drift, "estimated_y_plus": yplus,
        "profile_station_m": float(xs[profile_index]), "convergence": conv,
        "pressure_profile": [{"x_m": float(a), "pressure_pa": float(b), "bulk_velocity_m_s": float(c)} for a, b, c in zip(xs, ps, us)],
        "velocity_profile": [{"r_over_R": float(r), "velocity_m_s": float(u), "u_over_bulk": float(u / bulk)} for r, u in zip(rs, speeds)],
        "reference_profile": ref_profile,
        "validation": {"status": status, "checks": checks, "reference": ref,
            "friction_error_percent": f_error, "profile_rmse_percent_of_bulk": profile_error,
            "profile_comparison_points": profile_points,
            "project_target_percent": target,
            "note": "Targets are project screening criteria, not published experimental uncertainty. Mesh refinement is required before an accuracy claim."},
        "thermal_solved": False,
    }
    # Do not emit NaN/Infinity as JSON or label divergence a successful simulation.
    (case / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    return result
