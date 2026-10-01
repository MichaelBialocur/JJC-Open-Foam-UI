"""Boundary/material contracts: physical units, persistence and solver inputs."""
import json
from math import pi
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.cases import generate_pipe
from backend.app.main import app
from backend.app.models import PipeDefinition, PRESETS
from backend.app.properties import CATALOG
from backend.app.thermal import prepare_thermal


# Independent, dimensional examples (not generated from the application's factors).
@pytest.mark.parametrize('kind,value,unit,expected', [
    ('velocity', 100, 'cm/s', 1), ('velocity', 1000, 'mm/s', 1),
    ('velocity', 3.6, 'km/h', 1), ('velocity', 1, 'ft/s', .3048),
    ('volumetric_flow', 60, 'L/min', .001), ('volumetric_flow', 3600, 'L/h', .001),
    ('volumetric_flow', 1, 'L/s', .001), ('volumetric_flow', 60000, 'mL/min', .001),
    ('volumetric_flow', 3.6, 'm3/h', .001), ('volumetric_flow', .001, 'm3/s', .001),
    ('volumetric_flow', 1, 'CFM', .0004719474432),
    ('volumetric_flow', 1, 'US_gpm', .0000630901964),
    ('mass_flow', 3600, 'kg/h', 1), ('mass_flow', 60, 'kg/min', 1),
    ('mass_flow', 1, 'kg/s', 1), ('mass_flow', 1000, 'g/s', 1),
])
def test_units_and_reloading(kind, value, unit, expected):
    # Diameter chosen for a 0.01 m² area, density 1000 kg/m³.
    spec = PipeDefinition(inner_diameter_mm=1000*(.04/pi)**.5, density_kg_m3=1000,
        inlet={'kind':kind, 'value':value, 'unit':unit})
    velocity = expected if kind == 'velocity' else expected/.01 if kind == 'volumetric_flow' else expected/10
    assert spec.inlet_velocity_m_s == pytest.approx(velocity)
    restored = PipeDefinition.model_validate_json(spec.model_dump_json())
    assert restored.inlet == spec.inlet
    assert restored.inlet_velocity_m_s == spec.inlet_velocity_m_s


@pytest.mark.parametrize('inlet', [
    {'kind':'mass_flow','value':1,'unit':'L/min'},
    {'kind':'volumetric_flow','value':1,'unit':'SCFM'},
    {'kind':'velocity','value':0,'unit':'m/s'},
    {'kind':'velocity','value':-1,'unit':'m/s'},
    {'kind':'velocity','value':float('nan'),'unit':'m/s'},
    {'kind':'velocity','value':float('inf'),'unit':'m/s'},
    {'kind':'velocity','value':101,'unit':'m/s'},
    {'kind':'volumetric_flow','value':1e300,'unit':'L/min'},
])
def test_invalid_boundaries(inlet):
    with pytest.raises(ValidationError):
        PipeDefinition(inlet=inlet)


def test_inlet_recomputes_after_density_or_diameter_edits():
    data = {'inlet':{'kind':'mass_flow','value':360,'unit':'kg/h'}, 'density_kg_m3':1000}
    first = PipeDefinition(**data)
    saved = first.model_dump()
    saved['inlet_velocity_m_s'] = 99  # A stale cached value must not win.
    saved['density_kg_m3'] = 500
    assert PipeDefinition(**saved).inlet_velocity_m_s == 2*first.inlet_velocity_m_s
    saved['inner_diameter_mm'] *= 2
    assert PipeDefinition(**saved).inlet_velocity_m_s == first.inlet_velocity_m_s/2
    saved['inlet'] = {'kind':'volumetric_flow','value':6,'unit':'L/min'}
    a = PipeDefinition(**saved)
    saved['density_kg_m3'] = 1000
    assert PipeDefinition(**saved).inlet_velocity_m_s == a.inlet_velocity_m_s
    with pytest.raises(ValidationError):
        PipeDefinition(inner_diameter_mm=1e-200, inlet=data['inlet'])


def test_presets_do_not_overwrite_explicit_or_legacy_values():
    assert PipeDefinition().density_kg_m3 == 998
    assert PipeDefinition().specific_heat_j_kg_k == 4182
    assert PipeDefinition().inlet is None
    water = PipeDefinition(fluid='water')
    assert water.density_kg_m3 == pytest.approx(998.2071505)
    assert PipeDefinition(fluid='water', density_kg_m3=990).density_kg_m3 == 990
    air = PipeDefinition(fluid='air')
    assert air.density_kg_m3 == pytest.approx(1.204575182)
    assert air.prandtl == pytest.approx(.707, rel=.01)
    for key in ('water_eg30','water_eg50','water_pg30','water_pg50'):
        assert CATALOG['fluids'][key]['glycol_mass_fraction'] in (.3,.5)
        assert PipeDefinition(fluid=key).dynamic_viscosity_pa_s > water.dynamic_viscosity_pa_s
    assert PipeDefinition(**PRESETS['laminar']['inputs']).reynolds == pytest.approx(100)


@pytest.mark.parametrize('mesh', ['coarse','medium','fine'])
@pytest.mark.parametrize('preset', ['laminar','superpipe'])
def test_same_operating_point_writes_same_openfoam_case(tmp_path, mesh, preset):
    velocity = PipeDefinition(**{**PRESETS[preset]['inputs'], 'mesh_level':mesh})
    q = velocity.inlet_velocity_m_s*pi*velocity.diameter_m**2/4
    generate_pipe(tmp_path/'velocity', velocity)
    baseline = {p.relative_to(tmp_path/'velocity'):p.read_text() for p in (tmp_path/'velocity').rglob('*')
                if p.is_file() and p.name != 'manifest.json'}
    for kind, value, unit in [('volumetric_flow',q*60000,'L/min'),
                             ('mass_flow',q*velocity.density_kg_m3*3600,'kg/h')]:
        spec = PipeDefinition(**{**velocity.model_dump(), 'inlet':{'kind':kind,'value':value,'unit':unit}})
        folder = tmp_path/kind
        generate_pipe(folder, spec)
        assert {p.relative_to(folder):p.read_text() for p in folder.rglob('*')
                if p.is_file() and p.name != 'manifest.json'} == baseline
        assert json.loads((folder/'manifest.json').read_text())['inputs']['inlet']['unit'] == unit


def test_edited_solid_properties_reach_native_solver(tmp_path):
    spec = PipeDefinition(**{**PRESETS['heated_wall']['inputs'], 'mesh_level':'coarse',
        'solid_conductivity_w_m_k':150, 'solid_density_kg_m3':2800, 'solid_specific_heat_j_kg_k':900})
    generate_pipe(tmp_path,spec)
    mesh=tmp_path/'constant/polyMesh'; mesh.mkdir()
    (mesh/'boundary').write_text('wall { type wall; nFaces 120; startFace 12; }')
    (tmp_path/'2500').mkdir()
    (tmp_path/'2500/phi').write_text('dimensions [0 3 -1 0 0 0 0]; internalField uniform 0;')
    thermal=prepare_thermal(tmp_path,spec,2500)
    physical=(thermal/'constant/solid/physicalProperties').read_text()
    for name, expected in [('kappa',150),('rho',2800),('Cv',900)]:
        match = re.search(rf'{name}\s*\{{\s*type uniform;\s*value ([0-9.]+);', physical)
        assert match and float(match.group(1)) == expected


def test_preview_and_submission_share_normalized_input(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_CFD_RUNS',str(tmp_path))
    monkeypatch.setattr('backend.app.main.foam_health',lambda:{'available':True})
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.jobs, 'submit', lambda spec: {'inputs':spec.model_dump()})
        assert client.get('/api/materials').json() == CATALOG
        data={'fluid':'water_eg30','inlet':{'kind':'mass_flow','value':6,'unit':'kg/h'}}
        preview=client.post('/api/pipe/preview',json=data)
        submitted=client.post('/api/jobs',json=data)
        assert preview.status_code == 200 and submitted.status_code == 202
        assert preview.json()['flow']['mass_flow_kg_h'] == pytest.approx(6)
        assert submitted.json()['inputs']['inlet_velocity_m_s'] == preview.json()['flow']['velocity_m_s']
        data['inlet']['unit']='CFM'
        assert client.post('/api/pipe/preview',json=data).status_code == 422
        assert client.post('/api/jobs',json=data).status_code == 422
