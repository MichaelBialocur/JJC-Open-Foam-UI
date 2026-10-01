"""Geometry contracts and native CAD topology; CFD benchmarks are in scripts/validate_assembly.py."""
import json
from math import pi
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from backend.app.assembly_models import AssemblyGeometry, AssemblyDefinition, Part, Section, builder_presets
from backend.app.assembly_solver import flow_dictionaries
from backend.app.main import app


def geometry(name='coldplate'):
    return AssemblyGeometry(**builder_presets()[name]['geometry'])


@pytest.mark.parametrize('name',['pipe','elbow','coldplate'])
def test_saved_geometry_roundtrip_keeps_face_identity(name):
    g=geometry(name)
    assert g.key==AssemblyGeometry.model_validate_json(g.model_dump_json()).key
    body={'geometry':g,'boundaries':[dict(id='heat',kind='heat',faces=['f_pipe1_1'])],'boundary_geometry_key':g.key}
    assert AssemblyDefinition.model_validate_json(AssemblyDefinition(**body).model_dump_json()).geometry.key==g.key


def test_boundaries_cannot_overlap_or_survive_geometry_change():
    g=geometry();body=dict(geometry=g,boundary_geometry_key=g.key,boundaries=[dict(id='heat',kind='heat',faces=['face'])])
    body['boundaries'].append(dict(id='cool',kind='convection',faces=['face']))
    with pytest.raises(ValidationError,match='one group'):AssemblyDefinition(**body)
    body['boundaries'].pop();body['geometry']=g.model_copy(update={'yaw_deg':10})
    with pytest.raises(ValidationError,match='Geometry changed'):AssemblyDefinition(**body)


def test_dimensions_channel_area_and_flow_units():
    g=geometry();p=g.parts[2]
    assert p.section_flow()==pytest.approx((96,88))  # 5 × 4.8 × 4 mm; 5 × 2 × (4.8+4)
    plate=AssemblyGeometry(parts=[p]);spec=AssemblyDefinition(geometry=plate,physics={'inlet':{'kind':'volumetric_flow','value':.576,'unit':'L/min'}})
    assert spec.operating.inlet_velocity_m_s==pytest.approx(.1)
    mass=AssemblyDefinition(geometry=plate,physics={'inlet':{'kind':'mass_flow','value':6,'unit':'kg/h'}})
    assert mass.operating.inlet_velocity_m_s*mass.operating.inlet_area_m2*mass.operating.density_kg_m3==pytest.approx(6/3600)


@pytest.mark.parametrize('changes',[{'kind':'bend','radius_mm':5},{'kind':'multiport'},{'kind':'straight','end':{'shape':'rectangle'}}])
def test_impossible_parts_rejected(changes):
    with pytest.raises(ValidationError):Part(id='p',**changes)


def test_shared_ends_and_thin_channels_rejected():
    parts=geometry('pipe').parts;parts.append(Part(id='p2',start=Section(diameter_mm=9)))
    with pytest.raises(ValidationError,match='must match'):AssemblyGeometry(parts=parts)
    with pytest.raises(ValidationError,match='0.1 mm'):Part(id='p',kind='multiport',start=Section(shape='rectangle'),end=Section(shape='rectangle'),channels=30,web_mm=1)


def test_bend_endpoints_and_transport_of_rectangular_frame():
    rows=geometry('elbow').layout()
    assert rows[1]['end_mm']==pytest.approx([60,20,0])
    assert rows[-1]['end_mm']==pytest.approx([60,60,0])
    box=Section(shape='rectangle')
    g=AssemblyGeometry(parts=[Part(id='b',kind='bend',start=box,end=box,roll_deg=90),Part(id='p',start=box,end=box)])
    a,b=g.layout();assert a['end_mm']==pytest.approx([20,0,20]);assert a['end_normal']==pytest.approx([0,1,0]);assert b['normal']==pytest.approx(a['end_normal'])
    assert np.dot(a['end_tangent'],a['end_normal'])==pytest.approx(0,abs=1e-12)


def test_flow_rate_bc_uses_requested_volume_not_cad_polygon_area(tmp_path):
    spec=AssemblyDefinition(geometry=geometry('pipe'),physics={'inlet':{'kind':'volumetric_flow','value':.6,'unit':'L/min'}})
    flow_dictionaries(tmp_path,spec,{'patches':{'inlet':{},'outlet':{},'fluid_to_solid':{}}})
    field=(tmp_path/'0/U').read_text()
    assert 'flowRateInletVelocity' in field and 'volumetricFlowRate constant 1e-05;' in field
    assert 'noSlip' in field


def test_api_resolves_rectangular_inlet_and_separates_histories(tmp_path,monkeypatch):
    monkeypatch.setenv('PIPE_CFD_RUNS',str(tmp_path/'runs'))
    with TestClient(app) as client:
        r=client.post('/api/assembly/operating',json=AssemblyDefinition(geometry=geometry()).model_dump())
        assert r.status_code==200 and r.json()['flow']['flow_rate_l_min']>0
        assert client.get('/api/jobs').json()==[] and client.get('/api/assembly/jobs').json()==[]
        bad=geometry().model_dump();bad['parts'][0]['end']['diameter_mm']=3
        assert client.post('/api/assembly/preview',json=bad).status_code==422


@pytest.fixture(scope='module')
def native_cad(tmp_path_factory):
    status=subprocess.run([sys.executable,'-c','import gmsh'],capture_output=True)
    if status.returncode:pytest.skip('Gmsh native libraries unavailable; run scripts/setup.sh')
    root=tmp_path_factory.mktemp('cad')
    def build(g,size=2,mesh=False):
        folder=root/str(len(list(root.iterdir())));folder.mkdir();source=folder/'input.json';source.write_text(g.model_dump_json())
        command=[sys.executable,'-m','backend.app.assembly_geometry',str(source),str(folder),'--size',str(size)]+(['--mesh'] if mesh else [])
        p=subprocess.run(command,capture_output=True,text=True,timeout=90)
        assert p.returncode==0,p.stdout[-1500:]+p.stderr
        return json.loads((folder/'geometry.json').read_text()),folder
    return build


def test_native_coldplate_preserves_faces_between_mesh_sizes(native_cad):
    g=geometry();a,_=native_cad(g,2);b,_=native_cad(g,1.4)
    assert {f['id'] for f in a['faces']}=={f['id'] for f in b['faces']}
    external={f['id']:f for f in a['faces'] if f['selectable']}
    assert external['f_plate1_1']['area_mm2']==pytest.approx(1500)
    assert external['f_plate1_2']['area_mm2']==pytest.approx(1500)
    assert external['f_plate1_0']['area_mm2']==pytest.approx(300)
    assert a['geometry_key']==g.key
    assert a['inlet_area_m2']==pytest.approx(pi*.005**2)


def test_native_mesh_is_metres_and_fluid_volume_is_correct(native_cad):
    a,folder=native_cad(geometry('pipe'),2,True)
    text=(folder/'assembly.msh').read_text().split('$Nodes\n')[1].split('$EndNodes')[0].splitlines()
    xyz=np.array([[float(x) for x in line.split()[1:]] for line in text[1:] if line.strip()])
    assert np.ptp(xyz[:,0])==pytest.approx(.05,abs=1e-9)
    assert a['fluid_volume_mm3']==pytest.approx(pi*25*50,rel=1e-6)
    assert a['cells']>100


def test_native_rolled_tapered_bend_builds(native_cad):
    r=Section();end=Section(diameter_mm=8,wall_mm=.8)
    g=AssemblyGeometry(parts=[Part(id='bend',kind='bend',start=r,end=end,angle_deg=60,roll_deg=45)])
    a,_=native_cad(g)
    assert a['fluid_volume_mm3']>0 and sum(f['selectable'] for f in a['faces'])>=1
