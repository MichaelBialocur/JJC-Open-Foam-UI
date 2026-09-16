from math import pi
import platform
import subprocess
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(
    title="Pipe CFD",
    version="0.1.0",
)


class PipeDefinition(BaseModel):
    length_mm: float = Field(gt=0)
    inner_diameter_mm: float = Field(gt=0)
    wall_thickness_mm: float = Field(gt=0)

    material: Literal["aluminium", "copper"]

    inlet_velocity_m_s: float = Field(gt=0)
    inlet_temperature_c: float

    applied_heat_w: float = Field(ge=0)


def get_openfoam_version():
    try:
        result = subprocess.run(
            [
                "bash",
                "-lc",
                "source /opt/openfoam14/etc/bashrc && foamVersion",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            return result.stdout.strip()

        return "OpenFOAM version check failed"

    except Exception as exc:
        return f"OpenFOAM unavailable: {exc}"


@app.get("/")
def root():
    return {
        "application": "Pipe CFD",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "python": platform.python_version(),
        "openfoam": get_openfoam_version(),
    }


@app.post("/api/pipe/preview")
def preview_pipe(pipe: PipeDefinition):

    diameter_m = pipe.inner_diameter_mm / 1000.0
    length_m = pipe.length_mm / 1000.0

    area_m2 = pi * diameter_m**2 / 4.0

    volumetric_flow_m3_s = (
        area_m2 * pipe.inlet_velocity_m_s
    )

    volumetric_flow_l_min = (
        volumetric_flow_m3_s * 60_000.0
    )

    # Approximate water properties for initial development.
    density = 998.0
    dynamic_viscosity = 1.002e-3

    reynolds_number = (
        density
        * pipe.inlet_velocity_m_s
        * diameter_m
        / dynamic_viscosity
    )

    outer_diameter_mm = (
        pipe.inner_diameter_mm
        + 2 * pipe.wall_thickness_mm
    )

    return {
        "geometry": {
            "length_mm": pipe.length_mm,
            "inner_diameter_mm": pipe.inner_diameter_mm,
            "outer_diameter_mm": outer_diameter_mm,
            "wall_thickness_mm": pipe.wall_thickness_mm,
        },
        "material": pipe.material,
        "flow": {
            "velocity_m_s": pipe.inlet_velocity_m_s,
            "flow_rate_l_min": volumetric_flow_l_min,
            "reynolds_number": reynolds_number,
        },
        "thermal": {
            "inlet_temperature_c": pipe.inlet_temperature_c,
            "applied_heat_w": pipe.applied_heat_w,
        },
        "openfoam": get_openfoam_version(),
    }