"""Versioned inputs shared by preview, case generation, and validation."""
from math import pi
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PipeDefinition(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    geometry_type: Literal["pipe"] = "pipe"
    length_mm: float = Field(default=500, gt=0, le=100000)
    inner_diameter_mm: float = Field(default=10, gt=0, le=2000)
    wall_thickness_mm: float = Field(default=2, gt=0, le=500)
    material: Literal["aluminium", "copper"] = "aluminium"
    inlet_velocity_m_s: float = Field(default=1, gt=0, le=100)
    inlet_temperature_c: float = Field(default=20, ge=-100, le=500)
    applied_heat_w: float = Field(default=0, ge=0, le=1e7)
    density_kg_m3: float = Field(default=998, gt=0, le=30000)
    dynamic_viscosity_pa_s: float = Field(default=1.002e-3, gt=0, le=100)
    flow_model: Literal["auto", "laminar", "kOmegaSST"] = "auto"
    mesh_level: Literal["coarse", "medium", "fine"] = "medium"
    max_iterations: int = Field(default=2500, ge=100, le=10000, multiple_of=100)
    residual_tolerance: float = Field(default=1e-6, ge=1e-9, le=1e-3)
    turbulence_intensity: float = Field(default=0.05, ge=0.001, le=0.2)
    reference: Literal["auto", "superpipe_41727"] = "auto"

    @property
    def diameter_m(self):
        return self.inner_diameter_mm / 1000

    @property
    def length_m(self):
        return self.length_mm / 1000

    @property
    def nu(self):
        return self.dynamic_viscosity_pa_s / self.density_kg_m3

    @property
    def reynolds(self):
        return self.inlet_velocity_m_s * self.diameter_m / self.nu

    @property
    def selected_model(self):
        if self.flow_model != "auto":
            return self.flow_model
        return "laminar" if self.reynolds < 2300 else "kOmegaSST"

    @property
    def mesh_shape(self):
        return {"coarse": (120, 16), "medium": (240, 32), "fine": (480, 64)}[self.mesh_level]

    def run_errors(self):
        errors = []
        if 2300 <= self.reynolds < 4000:
            errors.append("Re 2300–4000 is transitional. A transition model is not implemented; choose a laminar or fully turbulent operating point.")
        if self.selected_model == "laminar" and self.reynolds >= 2300:
            errors.append("Laminar mode requires Re < 2300.")
        if self.selected_model == "kOmegaSST" and self.reynolds < 4000:
            errors.append("k–ω SST mode requires Re ≥ 4000 in this release.")
        if self.applied_heat_w != 0:
            errors.append("This release solves isothermal flow. Set applied heat to 0 W; conjugate heat transfer is a later milestone.")
        return errors

    @model_validator(mode="after")
    def geometry_limits(self):
        if self.length_mm / self.inner_diameter_mm < 2:
            raise ValueError("Pipe length must be at least two inner diameters.")
        return self

    def summary(self):
        return {
            "geometry": {"length_mm": self.length_mm, "inner_diameter_mm": self.inner_diameter_mm,
                         "outer_diameter_mm": self.inner_diameter_mm + 2 * self.wall_thickness_mm,
                         "wall_thickness_mm": self.wall_thickness_mm},
            "material": self.material,
            "flow": {"velocity_m_s": self.inlet_velocity_m_s,
                     "flow_rate_l_min": pi * self.diameter_m**2 / 4 * self.inlet_velocity_m_s * 60000,
                     "reynolds_number": self.reynolds, "model": self.selected_model},
            "thermal": {"inlet_temperature_c": self.inlet_temperature_c,
                        "applied_heat_w": self.applied_heat_w, "solved": False},
            "mesh": {"axial": self.mesh_shape[0], "radial": self.mesh_shape[1],
                     "cells": self.mesh_shape[0] * self.mesh_shape[1], "type": "5° axisymmetric wedge"},
            "run_errors": self.run_errors(),
            "notes": ["Constant fluid properties are explicit inputs; temperature does not update them automatically.",
                      "Smooth, straight circular pipe; uniform inlet, no-slip wall, zero gauge outlet pressure.",
                      "Wall material and thickness are stored geometry metadata; solid conduction is not solved."],
        }


PRESETS = {
    "laminar": {"name": "Laminar verification · Re 100", "description": "Hagen–Poiseuille pressure gradient and parabolic velocity. Uniform inlet; compare the developed region.",
                "inputs": PipeDefinition(length_mm=1000, inlet_velocity_m_s=100 * 1.002e-3 / (998 * .01)).model_dump()},
    "superpipe": {"name": "Princeton experiment · Re 41,727", "description": "Air, original Superpipe dataset. Darcy friction factor and normalized velocity profile. 200D development length.",
                  "inputs": PipeDefinition(length_mm=25872, inner_diameter_mm=129.36,
                    inlet_velocity_m_s=5.132, inlet_temperature_c=26.98, density_kg_m3=1.162,
                    dynamic_viscosity_pa_s=1.8487e-5, reference="superpipe_41727", max_iterations=4000).model_dump()},
}
