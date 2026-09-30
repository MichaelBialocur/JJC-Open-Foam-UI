"""Viewer data from actual mesh points and cell fields, including old saved runs."""
from functools import lru_cache
import json
from pathlib import Path
import re

import numpy as np

from .models import PipeDefinition
from .results import read_internal


def mesh_points(path):
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", path.read_text(), flags=re.S)
    match = re.search(r"\}\s*(\d+)\s*\((.*)\)\s*$", text, re.S)
    if not match:
        raise ValueError("Viewer requires an ASCII OpenFOAM points file.")
    data = np.fromstring(match[2].replace("(", " ").replace(")", " "), sep=" ")
    if data.size != int(match[1]) * 3 or not np.all(np.isfinite(data)):
        raise ValueError("Invalid mesh points.")
    return data.reshape((-1, 3))


def build_fields(case, spec, result):
    centres = read_internal(case / "0/C", 3)
    vertices = mesh_points(case / "constant/polyMesh/points")
    nx, nr = spec.mesh_shape
    xs = np.unique(np.round(centres[:, 0], 11))
    x_edges = np.unique(np.round(vertices[:, 0], 12))
    r_edges = np.unique(np.round(np.linalg.norm(vertices[:, 1:], axis=1), 12))
    if len(xs) != nx or len(x_edges) != nx + 1 or len(r_edges) != nr + 1 or len(centres) != nx * nr:
        raise ValueError("This viewer supports the generated axisymmetric pipe mesh only.")
    order = np.concatenate([ids[np.argsort(centres[ids, 1])] for x in xs
        for ids in [np.flatnonzero(np.round(centres[:, 0], 11) == x)]])
    if len(set(order.tolist())) != nx * nr:
        raise ValueError("Non-unique cell ordering.")
    latest = case / f"{result['solution_iteration']:g}"
    velocity = read_internal(latest / "U", 3, nx * nr)[order]
    p = read_internal(latest / "p", count=nx * nr)[order] * spec.density_kg_m3
    scalar_fields = {
        "speed": {"label": "Speed", "unit": "m/s", "values": np.linalg.norm(velocity, axis=1).tolist()},
        "pressure": {"label": "Gauge pressure", "unit": "Pa", "values": p.tolist()},
    }
    if result.get("thermal_solved"):
        time = result['thermal']['solution_iteration']
        t = read_internal(case / 'thermal' / str(time) / 'T', count=nx * nr)[order] - 273.15
        scalar_fields["temperature"] = {"label": "Fluid temperature", "unit": "°C", "values": t.tolist()}
    for field in scalar_fields.values():
        field.update(min=min(field["values"]), max=max(field["values"]))
    return {
        "schema_version": 1, "source": "Computed OpenFOAM cell fields; no reference profiles used",
        "representation": "Axisymmetric wedge revolved for display; not a full 3D flow solution",
        "ordering": "axial-major, radial-minor", "nx": nx, "nr": nr,
        "x_edges_m": x_edges.tolist(), "r_edges_m": r_edges.tolist(),
        "cell_x_m": centres[order, 0].tolist(),
        "cell_r_m": np.linalg.norm(centres[order, 1:], axis=1).tolist(),
        "axial_velocity_m_s": velocity[:, 0].tolist(), "radial_velocity_m_s": velocity[:, 1].tolist(),
        "fields": scalar_fields,
        "flow_converged": result["convergence"]["converged"],
        "thermal_converged": result.get("thermal", {}).get("convergence", {}).get("converged"),
    }


@lru_cache(maxsize=8)
def fields_json(case_path: str, result_mtime_ns: int):
    # Terminal run data are immutable. mtime invalidates the cache if results
    # are explicitly reprocessed; large grids are never included in job polling.
    case = Path(case_path)
    spec = PipeDefinition(**json.loads((case / "job.json").read_text())["inputs"])
    result = json.loads((case / "results.json").read_text())
    return json.dumps(build_fields(case, spec, result), separators=(",", ":"), allow_nan=False)


def meridional_vtk(data):
    """Exact cell data on the x–r plane; readable by ParaView, no interpolation."""
    nx, nr = data["nx"], data["nr"]
    points = [f"{x:.12g} {r:.12g} 0" for r in data["r_edges_m"] for x in data["x_edges_m"]]
    lines = ['# vtk DataFile Version 3.0', 'Pipe CFD computed meridional cell fields (x,r,0), SI units',
             'ASCII', 'DATASET STRUCTURED_GRID', f'DIMENSIONS {nx+1} {nr+1} 1',
             f'POINTS {len(points)} double', *points, f'CELL_DATA {nx*nr}']
    for name, item in data["fields"].items():
        label = {'speed':'speed_m_s', 'pressure':'gauge_pressure_Pa', 'temperature':'temperature_C'}[name]
        lines += [f'SCALARS {label} double 1', 'LOOKUP_TABLE default']
        lines += [f'{item["values"][i*nr+j]:.12g}' for j in range(nr) for i in range(nx)]
    return '\n'.join(lines) + '\n'
