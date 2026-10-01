"""Connected parametric assemblies, with explicit exterior-face thermal groups."""
from hashlib import sha256
import json
from math import pi, sin, cos, radians, isfinite
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import PipeDefinition


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, validate_default=True)


class Section(StrictModel):
    shape: Literal['round','rectangle'] = 'round'
    diameter_mm: float = Field(default=10, ge=.2, le=2000)
    width_mm: float = Field(default=30, ge=.2, le=2000)
    height_mm: float = Field(default=6, ge=.2, le=2000)
    wall_mm: float = Field(default=1, ge=.05, le=200)

    @model_validator(mode='after')
    def cavity(self):
        if self.shape == 'rectangle' and min(self.width_mm,self.height_mm) <= 2*self.wall_mm:
            raise ValueError('Rectangular outside dimensions must exceed twice the wall thickness.')
        return self

    def dimensions(self):
        return [self.diameter_mm,self.wall_mm] if self.shape=='round' else [self.width_mm,self.height_mm,self.wall_mm]

    def area_perimeter(self, channels=1, web_mm=0):
        if self.shape=='round':
            return pi*self.diameter_mm**2/4, pi*self.diameter_mm
        w=(self.width_mm-2*self.wall_mm-(channels-1)*web_mm)/channels
        h=self.height_mm-2*self.wall_mm
        return channels*w*h, channels*2*(w+h)


class Part(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9]{0,23}$')
    name: str = Field(default='Part', min_length=1, max_length=60)
    kind: Literal['straight','bend','manifold','multiport'] = 'straight'
    length_mm: float = Field(default=40, ge=.2, le=10000)
    radius_mm: float = Field(default=20, ge=.2, le=5000)
    angle_deg: float = Field(default=90, ge=1, le=270)
    roll_deg: float = Field(default=0, ge=-360, le=360)
    start: Section = Field(default_factory=Section)
    end: Section = Field(default_factory=Section)
    channels: int = Field(default=5, ge=1, le=64)
    web_mm: float = Field(default=1, ge=.05, le=100)

    @model_validator(mode='after')
    def shape_limits(self):
        if self.kind!='manifold' and self.start.shape!=self.end.shape:
            raise ValueError('Use a transition/manifold to change between round and rectangular sections.')
        if self.kind=='multiport':
            if self.start.shape!='rectangle' or self.end.shape!='rectangle':
                raise ValueError('A multi-port tube requires rectangular outside sections.')
            for section in (self.start,self.end):
                if section.width_mm-2*section.wall_mm-(self.channels-1)*self.web_mm <= .1*self.channels:
                    raise ValueError('The channel count and web thickness leave less than 0.1 mm per channel.')
        if self.kind=='bend':
            roll=radians(self.roll_deg)
            largest=max((s.diameter_mm/2+s.wall_mm) if s.shape=='round' else (s.width_mm*abs(cos(roll))+s.height_mm*abs(sin(roll)))/2 for s in (self.start,self.end))
            if self.radius_mm<=largest:
                raise ValueError('Bend centreline radius must exceed the outside half-width of both ends.')
        return self

    def section_flow(self, end=False):
        return (self.end if end else self.start).area_perimeter(self.channels if self.kind=='multiport' else 1,self.web_mm)


class AssemblyGeometry(StrictModel):
    parts: list[Part] = Field(min_length=1, max_length=40)
    origin_mm: tuple[float,float,float] = (0,0,0)
    yaw_deg: float = Field(default=0, ge=-360, le=360)
    pitch_deg: float = Field(default=0, ge=-90, le=90)

    @model_validator(mode='after')
    def connections(self):
        if any(abs(x)>100000 for x in self.origin_mm):
            raise ValueError('Origin coordinates must be within ±100,000 mm.')
        if len({p.id for p in self.parts})!=len(self.parts):
            raise ValueError('Part IDs must be unique.')
        for a,b in zip(self.parts,self.parts[1:]):
            if a.end.shape!=b.start.shape or not np.allclose(a.end.dimensions(),b.start.dimensions(),rtol=0,atol=1e-7):
                raise ValueError(f'{a.name} end and {b.name} start dimensions must match. Add a transition for a change in section.')
        return self

    @property
    def key(self):
        return sha256(('assembly-occ-v1:'+json.dumps(self.model_dump(),sort_keys=True,separators=(',',':'))).encode()).hexdigest()

    def layout(self):
        yaw,pitch=radians(self.yaw_deg),radians(self.pitch_deg)
        p=np.array(self.origin_mm,dtype=float)
        t=np.array([cos(pitch)*cos(yaw),cos(pitch)*sin(yaw),sin(pitch)])
        n=np.array([-sin(yaw),cos(yaw),0.])
        rows=[]
        for part in self.parts:
            start=p.copy(); t0=t.copy(); n0=n.copy(); b=np.cross(t,n)
            if part.kind=='bend':
                roll=radians(part.roll_deg); bend_n=cos(roll)*n+sin(roll)*b
                a=radians(part.angle_deg); axis=np.cross(t,bend_n)
                p=p+part.radius_mm*(sin(a)*t+(1-cos(a))*bend_n)
                n=cos(a)*n+sin(a)*np.cross(axis,n)+(1-cos(a))*np.dot(axis,n)*axis
                t=cos(a)*t+sin(a)*bend_n
                length=part.radius_mm*a
            else:
                p=p+part.length_mm*t; length=part.length_mm
            rows.append({'id':part.id,'name':part.name,'start_mm':start.tolist(),'end_mm':p.tolist(),
                'tangent':t0.tolist(),'normal':n0.tolist(),'bend_normal':bend_n.tolist() if part.kind=='bend' else n0.tolist(),
                'end_tangent':t.tolist(),'end_normal':n.tolist(),'length_mm':length})
        return rows


class ThermalGroup(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9]{0,23}$')
    name: str = Field(default='Thermal boundary',max_length=60)
    kind: Literal['heat','convection']
    faces: list[str] = Field(min_length=1,max_length=2000)
    power_w: float = Field(default=10,ge=0,le=1e7)
    h_w_m2_k: float = Field(default=100,gt=0,le=1e7)
    ambient_c: float = Field(default=20,ge=-100,le=500)


class AssemblyPhysics(PipeDefinition):
    geometry_type: Literal['assembly'] = 'assembly'
    inlet_area_m2: float = Field(gt=0)

    @model_validator(mode='after')
    def geometry_limits(self):
        if self.inlet is not None:
            velocity=self.inlet.velocity(self.inlet_area_m2,self.density_kg_m3)
            if not isfinite(velocity) or not 0<velocity<=100:
                raise ValueError('The inlet flow must give a mean velocity above 0 and at most 100 m/s.')
            self.inlet_velocity_m_s=velocity
        return self


class AssemblyDefinition(StrictModel):
    geometry_type: Literal['assembly'] = 'assembly'
    name: str = Field(default='Cold plate assembly',max_length=80)
    geometry: AssemblyGeometry
    physics: dict = Field(default_factory=lambda:{'fluid':'water','inlet':{'kind':'velocity','value':.05,'unit':'m/s'},'thermal_iterations':2000})
    mesh_size_mm: float = Field(default=2,ge=.05,le=1000)
    boundaries: list[ThermalGroup] = Field(default_factory=list,max_length=200)
    boundary_geometry_key: str | None = None

    @property
    def operating(self):
        area,perimeter=self.geometry.parts[0].section_flow()
        return AssemblyPhysics(**{**self.physics,'geometry_type':'assembly','inlet_area_m2':area*1e-6,
            'inner_diameter_mm':4*area/perimeter,'length_mm':sum(p['length_mm'] for p in self.geometry.layout()),
            'thermal_mode':'conjugate','applied_heat_w':sum(b.power_w for b in self.boundaries if b.kind=='heat')})

    @model_validator(mode='after')
    def boundaries_and_physics(self):
        self.operating  # Validate the physics using the actual inlet area.
        ids=[b.id for b in self.boundaries]
        faces=[f for b in self.boundaries for f in b.faces]
        if len(set(ids))!=len(ids) or len(set(faces))!=len(faces):
            raise ValueError('Each thermal group ID must be unique and a face can belong to only one group.')
        if self.boundaries and self.boundary_geometry_key!=self.geometry.key:
            raise ValueError('Geometry changed: rebuild and reselect the thermal faces before running.')
        return self

    def run_errors(self):
        return self.operating.run_errors()


def builder_presets():
    r=Section().model_dump(); box=Section(shape='rectangle').model_dump()
    def part(id,name,kind,start,end,**kw):
        return Part(id=id,name=name,kind=kind,start=start,end=end,**kw).model_dump()
    return {
        'pipe':{'name':'Straight pipe','geometry':{'parts':[part('pipe1','Pipe','straight',r,r,length_mm=50)]}},
        'elbow':{'name':'Pipe with 90° bend','geometry':{'parts':[
            part('pipe1','Inlet pipe','straight',r,r),part('bend1','90° bend','bend',r,r),part('pipe2','Outlet pipe','straight',r,r)]}},
        'coldplate':{'name':'Pipe → multi-port cold plate → pipe','geometry':{'parts':[
            part('pipe1','Inlet pipe','straight',r,r,length_mm=25),
            part('header1','Inlet manifold','manifold',r,box,length_mm=20),
            part('plate1','Multi-port plate','multiport',box,box,length_mm=50),
            part('header2','Outlet manifold','manifold',box,r,length_mm=20),
            part('pipe2','Outlet pipe','straight',r,r,length_mm=25)]}},
    }
