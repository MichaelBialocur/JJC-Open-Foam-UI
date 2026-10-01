"""CAD inputs. Geometric metrics are resolved from the server's imported model."""
from hashlib import sha256
import json
from typing import Literal

from pydantic import Field, model_validator

from .assembly_models import StrictModel, ThermalGroup, AssemblyPhysics


class CadGeometry(StrictModel):
    source_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    scale: float = Field(default=1, gt=0, le=1e6)
    fluid_bodies: list[str] = Field(min_length=1, max_length=1000)
    solid_bodies: list[str] = Field(default_factory=list, max_length=1000)

    @model_validator(mode='after')
    def roles(self):
        bodies = self.fluid_bodies + self.solid_bodies
        if len(set(bodies)) != len(bodies):
            raise ValueError('A body must have exactly one role: fluid, solid, or ignored.')
        return self

    @property
    def key(self):
        data = {**self.model_dump(), 'fluid_bodies': sorted(self.fluid_bodies), 'solid_bodies': sorted(self.solid_bodies)}
        return sha256(('cad-occ-v1:' + json.dumps(data, sort_keys=True)).encode()).hexdigest()


class CadMetrics(StrictModel):
    inlet_area_m2: float = Field(gt=0)
    hydraulic_diameter_mm: float = Field(gt=0)
    length_mm: float = Field(gt=0)
    inlet_direction: tuple[float, float, float]


class CadDefinition(StrictModel):
    geometry_type: Literal['cad'] = 'cad'
    name: str = Field(default='Imported CAD', max_length=80)
    geometry: CadGeometry
    inlet_faces: list[str] = Field(default_factory=list, max_length=2000)
    outlet_faces: list[str] = Field(default_factory=list, max_length=2000)
    boundaries: list[ThermalGroup] = Field(default_factory=list, max_length=200)
    boundary_geometry_key: str | None = None
    physics: dict = Field(default_factory=lambda: {'fluid': 'water', 'inlet': {'kind': 'velocity', 'value': .05, 'unit': 'm/s'}, 'thermal_iterations': 2000})
    mesh_size_mm: float = Field(default=2, ge=.05, le=1000)
    metrics: CadMetrics | None = None

    @model_validator(mode='after')
    def assignments(self):
        faces = self.inlet_faces + self.outlet_faces + [f for b in self.boundaries for f in b.faces]
        if len(faces) != len(set(faces)):
            raise ValueError('A face can have only one inlet, outlet, heating, or cooling assignment.')
        if len({b.id for b in self.boundaries}) != len(self.boundaries):
            raise ValueError('Thermal group IDs must be unique.')
        if faces and self.boundary_geometry_key != self.geometry.key:
            raise ValueError('CAD bodies or scale changed. Prepare the geometry and reselect its faces.')
        return self

    @property
    def operating(self):
        if self.metrics is None:
            raise ValueError('Select inlet and outlet faces to calculate operating conditions.')
        m = self.metrics
        return AssemblyPhysics(**{**self.physics, 'geometry_type': 'assembly',
            'inlet_area_m2': m.inlet_area_m2, 'inner_diameter_mm': m.hydraulic_diameter_mm,
            'length_mm': m.length_mm, 'thermal_mode': 'conjugate',
            'applied_heat_w': sum(b.power_w for b in self.boundaries if b.kind == 'heat')})

    def run_errors(self):
        return self.operating.run_errors()
