"""Versioned inputs shared by preview, case generation, and validation."""
from math import pi, isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .properties import FLUIDS, MATERIALS, unit_factor


class InletBoundary(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    kind: Literal["velocity", "volumetric_flow", "mass_flow"]
    value: float = Field(gt=0)
    unit: str

    @model_validator(mode="after")
    def compatible_unit(self):
        unit_factor(self.kind, self.unit)
        return self

    def velocity(self, area, density):
        si = self.value * unit_factor(self.kind, self.unit)
        if self.kind == "velocity":
            return si
        denominator = area if self.kind == "volumetric_flow" else density * area
        if denominator <= 0:
            raise ValueError("The pipe area and fluid density must give a positive flow-conversion factor.")
        return si / denominator


class PipeDefinition(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    geometry_type: Literal["pipe"] = "pipe"
    length_mm: float = Field(default=500, gt=0, le=100000)
    inner_diameter_mm: float = Field(default=10, gt=0, le=2000)
    wall_thickness_mm: float = Field(default=2, gt=0, le=500)
    material: Literal["aluminium", "copper"] = "aluminium"
    # Missing mode in a saved v0.3 run must retain its original fluid-only meaning.
    thermal_mode: Literal["fluid_only", "conjugate"] = "fluid_only"
    solid_conductivity_w_m_k: float | None = Field(default=None, gt=0, le=10000)
    solid_density_kg_m3: float | None = Field(default=None, gt=0, le=30000)
    solid_specific_heat_j_kg_k: float | None = Field(default=None, gt=0, le=100000)
    fluid: Literal["custom", "water", "air", "water_eg30", "water_eg50", "water_pg30", "water_pg50"] = "custom"
    inlet: InletBoundary | None = None
    inlet_velocity_m_s: float = Field(default=1, gt=0, le=100)
    inlet_temperature_c: float = Field(default=20, ge=-100, le=500)
    applied_heat_w: float = Field(default=0, ge=0, le=1e7)
    specific_heat_j_kg_k: float = Field(default=4182, gt=0, le=100000)
    thermal_conductivity_w_m_k: float = Field(default=0.6, gt=0, le=10000)
    turbulent_prandtl: float = Field(default=0.85, ge=0.2, le=2)
    thermal_iterations: int = Field(default=200, ge=100, le=2000, multiple_of=50)
    density_kg_m3: float = Field(default=998, gt=0, le=30000)
    dynamic_viscosity_pa_s: float = Field(default=1.002e-3, gt=0, le=100)
    flow_model: Literal["auto", "laminar", "kOmegaSST"] = "auto"
    mesh_level: Literal["coarse", "medium", "fine"] = "medium"
    max_iterations: int = Field(default=2500, ge=100, le=10000, multiple_of=100)
    residual_tolerance: float = Field(default=1e-6, ge=1e-9, le=1e-3)
    turbulence_intensity: float = Field(default=0.05, ge=0.001, le=0.2)
    reference: Literal["auto", "superpipe_41727"] = "auto"

    @model_validator(mode="before")
    @classmethod
    def preset_defaults(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            preset = FLUIDS.get(data.get("fluid"))
            if preset:
                for key, value in preset["values"].items():
                    data.setdefault(key, value)
            # The structured boundary is authoritative; a saved/old cached
            # velocity must never override a mass or volume flow request.
            if data.get("inlet") is not None:
                data.pop("inlet_velocity_m_s", None)
        return data

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

    @property
    def thermal_diffusivity(self):
        return self.thermal_conductivity_w_m_k / (self.density_kg_m3 * self.specific_heat_j_kg_k)

    @property
    def solid_conductivity(self):
        return self.solid_conductivity_w_m_k or MATERIALS[self.material]["values"]["solid_conductivity_w_m_k"]

    @property
    def solid_density(self):
        return self.solid_density_kg_m3 or MATERIALS[self.material]["values"]["solid_density_kg_m3"]

    @property
    def solid_specific_heat(self):
        return self.solid_specific_heat_j_kg_k or MATERIALS[self.material]["values"]["solid_specific_heat_j_kg_k"]

    @property
    def solid_radial_cells(self):
        return {"coarse": 8, "medium": 16, "fine": 32}[self.mesh_level]

    @property
    def prandtl(self):
        return self.nu / self.thermal_diffusivity

    @property
    def ideal_temperature_rise(self):
        mass_flow = self.density_kg_m3 * self.inlet_velocity_m_s * pi * self.diameter_m**2 / 4
        return self.applied_heat_w / (mass_flow * self.specific_heat_j_kg_k)

    def run_errors(self):
        errors = []
        if 2300 <= self.reynolds < 4000:
            errors.append("Re 2300–4000 is transitional. A transition model is not implemented; choose a laminar or fully turbulent operating point.")
        if self.selected_model == "laminar" and self.reynolds >= 2300:
            errors.append("Laminar mode requires Re < 2300.")
        if self.selected_model == "kOmegaSST" and self.reynolds < 4000:
            errors.append("k–ω SST mode requires Re ≥ 4000 in this release.")
        return errors

    @model_validator(mode="after")
    def geometry_limits(self):
        if self.length_mm / self.inner_diameter_mm < 2:
            raise ValueError("Pipe length must be at least two inner diameters.")
        if self.inlet is not None:
            velocity = self.inlet.velocity(pi * self.diameter_m**2 / 4, self.density_kg_m3)
            if not isfinite(velocity) or not 0 < velocity <= 100:
                raise ValueError("The inlet flow must give a mean velocity greater than 0 and no more than 100 m/s; check flow, density and diameter.")
            self.inlet_velocity_m_s = velocity
        return self

    def summary(self):
        return {
            "geometry": {"length_mm": self.length_mm, "inner_diameter_mm": self.inner_diameter_mm,
                         "outer_diameter_mm": self.inner_diameter_mm + 2 * self.wall_thickness_mm,
                         "wall_thickness_mm": self.wall_thickness_mm},
            "material": self.material,
            "fluid": {"id": self.fluid, "label": FLUIDS[self.fluid]["label"] if self.fluid in FLUIDS else "Custom / benchmark properties"},
            "flow": {"velocity_m_s": self.inlet_velocity_m_s,
                     "flow_rate_l_min": pi * self.diameter_m**2 / 4 * self.inlet_velocity_m_s * 60000,
                     "mass_flow_kg_h": pi * self.diameter_m**2 / 4 * self.inlet_velocity_m_s * self.density_kg_m3 * 3600,
                     "inlet": self.inlet.model_dump() if self.inlet else {"kind":"velocity", "value":self.inlet_velocity_m_s, "unit":"m/s"},
                     "reynolds_number": self.reynolds, "model": self.selected_model},
            "thermal": {"inlet_temperature_c": self.inlet_temperature_c,
                        "applied_heat_w": self.applied_heat_w, "enabled": self.applied_heat_w > 0,
                        "prandtl": self.prandtl, "ideal_temperature_rise_k": self.ideal_temperature_rise,
                        "wall_heat_flux_w_m2": self.applied_heat_w / (pi * self.diameter_m * self.length_m),
                        "mode": self.thermal_mode, "solid_conductivity_w_m_k": self.solid_conductivity,
                        "model": "Coupled fluid–solid energy; uniform outer-wall heat input" if self.thermal_mode == "conjugate" else "Passive fluid energy transport; uniform inner-wall heat flux"},
            "mesh": {"axial": self.mesh_shape[0], "radial": self.mesh_shape[1],
                     "solid_radial": self.solid_radial_cells,
                     "cells": self.mesh_shape[0] * (self.mesh_shape[1] + (self.solid_radial_cells if self.applied_heat_w > 0 and self.thermal_mode == "conjugate" else 0)), "type": "5° axisymmetric wedge"},
            "run_errors": self.run_errors(),
            "notes": ["Constant fluid properties are explicit inputs; temperature does not update them automatically.",
                      "Smooth, straight circular pipe; uniform inlet, no-slip wall, zero gauge outlet pressure.",
                      "Conjugate mode solves radial and axial wall conduction with perfect thermal contact and insulated solid ends; power enters the outer surface. Fluid-only mode applies power directly at the inner wall.",
                      "Flow is frozen during heating; buoyancy, radiation, phase change and temperature feedback on flow are not solved."],
        }


PRESETS = {
    "laminar": {"name": "Laminar verification · Re 100", "description": "Hagen–Poiseuille pressure gradient and parabolic velocity. Uniform inlet; compare the developed region.",
                "inputs": PipeDefinition(length_mm=1000, inlet_velocity_m_s=100 * 1.002e-3 / (998 * .01)).model_dump()},
    "superpipe": {"name": "Princeton experiment · Re 41,727", "description": "Air, original Superpipe dataset. Darcy friction factor and normalized velocity profile. 200D development length.",
                  "inputs": PipeDefinition(length_mm=25872, inner_diameter_mm=129.36,
                    inlet_velocity_m_s=5.132, inlet_temperature_c=26.98, density_kg_m3=1.162,
                    dynamic_viscosity_pa_s=1.8487e-5, specific_heat_j_kg_k=1007, thermal_conductivity_w_m_k=.0263,
                    reference="superpipe_41727", max_iterations=4000).model_dump()},
    "heated_laminar": {"name": "Heated pipe · analytical check", "description": "Re 100 water, 10 W into a 100D pipe. Compare Nu with 48/11 and check energy conservation; constant properties, no buoyancy.",
                       "inputs": PipeDefinition(length_mm=1000, inlet_velocity_m_s=100 * 1.002e-3 / (998 * .01), applied_heat_w=10).model_dump()},
    "heated_wall": {"name": "Solid wall · conduction check", "description": "Re 100 water, 10 W at the outer surface of a 2 mm aluminium wall. Coupled fluid/solid temperatures; compare mean wall drop with cylindrical conduction.",
                    "inputs": PipeDefinition(length_mm=1000, inlet_velocity_m_s=100 * 1.002e-3 / (998 * .01), applied_heat_w=10, thermal_mode="conjugate", thermal_iterations=2000).model_dump()},
}
