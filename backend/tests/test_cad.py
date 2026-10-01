"""Native import/topology, face assignments, units and saved source provenance."""
import json
from math import pi
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.cad_geometry import build
from backend.app.cad_models import CadDefinition, CadGeometry
from backend.app.cad_api import resolve
from backend.app.assembly_solver import flow_dictionaries
from backend.app.assembly_mesh import cad_wall_patches
from backend.app.main import app


@pytest.fixture(scope='module')
def cad_files(tmp_path_factory):
    if subprocess.run([sys.executable, '-c', 'import gmsh'], capture_output=True).returncode:
        pytest.skip('Gmsh native libraries unavailable')
    import gmsh
    folder = tmp_path_factory.mktemp('cad-import-files')
    gmsh.initialize(); gmsh.option.setNumber('General.Terminal', 0)
    try:
        occ = gmsh.model.occ
        fluid = occ.addCylinder(0, 0, 0, 50, 0, 0, 5)
        outer = occ.addCylinder(0, 0, 0, 50, 0, 0, 6)
        occ.cut([(3, outer)], [(3, fluid)], removeTool=False); occ.synchronize()
        for ext in ('step', 'brep', 'iges'):
            gmsh.write(str(folder/('pipe.'+ext)))
        gmsh.clear(); occ.addBox(0, 0, 0, 10, 10, 10); occ.synchronize()
        gmsh.write(str(folder/'box.iges'))
        gmsh.clear(); occ.addBox(0, 0, 0, 10, 10, 10); occ.addBox(5, 0, 0, 10, 10, 10); occ.synchronize()
        gmsh.write(str(folder/'overlap.step'))
        gmsh.clear(); occ.addRectangle(0, 0, 0, 10, 10); occ.synchronize()
        gmsh.write(str(folder/'sheet.step'))
        gmsh.clear(); occ.addBox(0, 0, 0, 10, 5, 5); occ.addBox(10, 0, 0, 10, 5, 5)
        occ.addBox(0, 0, 5, 10, 5, 2); occ.addBox(10, 0, 5, 10, 5, 2); occ.synchronize()
        gmsh.write(str(folder/'joined.step'))
    finally:
        gmsh.finalize()
    return folder


def geometry(scale=1):
    return CadGeometry(source_id='a'*64, scale=scale, fluid_bodies=['v_1'], solid_bodies=['v_2'])


def ports(data):
    candidates = sorted((f for f in data['faces'] if f['port_selectable'] and f['planar']), key=lambda f: f['center_mm'][0])
    return [candidates[0]['id']], [candidates[-1]['id']]


@pytest.mark.parametrize('extension', ['step', 'brep'])
def test_native_formats_read_closed_bodies(cad_files, tmp_path, extension):
    data = build(cad_files/('pipe.'+extension), tmp_path)
    assert len(data['bodies']) == 2
    volumes = sorted(b['volume_mm3'] for b in data['bodies'])
    assert volumes == pytest.approx(sorted([pi*25*50, pi*(36-25)*50]), rel=1e-7)
    assert all(f['triangles'] for f in data['faces'])


def test_iges_closed_shell_is_sewn_but_ambiguous_touching_shells_rejected(cad_files, tmp_path):
    data = build(cad_files/'box.iges', tmp_path/'closed')
    assert len(data['bodies']) == 1
    assert data['bodies'][0]['volume_mm3'] == pytest.approx(1000)
    # This IGES export loses body topology at the touching cylinder surfaces.
    # Refuse to invent regions; STEP retains their separate solid definitions.
    with pytest.raises(ValueError, match='No closed volume'):
        build(cad_files/'pipe.iges', tmp_path/'ambiguous')


def test_step_declared_metres_are_converted_to_mm(cad_files, tmp_path):
    text = (cad_files/'pipe.step').read_text()
    assert 'SI_UNIT(.MILLI.,.METRE.)' in text
    source = tmp_path/'metres.step'
    source.write_text(text.replace('SI_UNIT(.MILLI.,.METRE.)', 'SI_UNIT($,.METRE.)'))
    data = build(source, tmp_path/'preview')
    assert data['bounds_mm'][1][0]-data['bounds_mm'][0][0] == pytest.approx(50000)
    assert sorted(b['volume_mm3'] for b in data['bodies']) == pytest.approx(sorted([pi*25*50*1e9, pi*11*50*1e9]))


def test_preview_and_volume_mesh_keep_faces_scale_and_normals(cad_files, tmp_path):
    source = cad_files/'pipe.step'
    a = build(source, tmp_path/'preview', geometry())
    inlet, outlet = ports(a)
    b = build(source, tmp_path/'mesh', geometry(), 2, inlet, outlet)
    assert {f['id'] for f in a['faces']} == {f['id'] for f in b['faces']}
    face = {f['id']: f for f in a['faces']}
    assert face[inlet[0]]['outward_normal'] == pytest.approx([-1, 0, 0])
    assert face[outlet[0]]['outward_normal'] == pytest.approx([1, 0, 0])
    text = (tmp_path/'mesh/assembly.msh').read_text()
    nodes = text.split('$Nodes\n')[1].split('$EndNodes')[0].splitlines()[1:]
    xyz = np.array([[float(v) for v in line.split()[1:]] for line in nodes if line.strip()])
    assert np.ptp(xyz[:, 0]) == pytest.approx(.05)
    assert '"inlet"' in text and '"outlet"' in text and '"solid"' in text and b['cells'] > 100
    scaled = build(source, tmp_path/'scaled', geometry(2))
    assert scaled['fluid_volume_mm3'] == pytest.approx(8*a['fluid_volume_mm3'])
    assert scaled['geometry_key'] != a['geometry_key']
    assert sum(f['area_mm2'] for f in scaled['faces']) == pytest.approx(4*sum(f['area_mm2'] for f in a['faces']))


def test_fluid_only_mesh_is_supported(cad_files, tmp_path):
    g = geometry().model_copy(update={'solid_bodies': []})
    data = build(cad_files/'pipe.step', tmp_path/'preview', g)
    inlet, outlet = ports(data)
    meshed = build(cad_files/'pipe.step', tmp_path/'mesh', g, 2, inlet, outlet)
    assert meshed['solid_volume_mm3'] == 0 and meshed['cells'] > 0
    assert all(not f['thermal_selectable'] for f in data['faces'])


def test_body_selection_order_keeps_cached_and_replayed_face_identity(cad_files, tmp_path):
    a = CadGeometry(source_id='b'*64, fluid_bodies=['v_1', 'v_2'], solid_bodies=['v_3', 'v_4'])
    b = a.model_copy(update={'fluid_bodies': ['v_2', 'v_1'], 'solid_bodies': ['v_4', 'v_3']})
    assert a.key == b.key
    first = build(cad_files/'joined.step', tmp_path/'first', a)
    replay = build(cad_files/'joined.step', tmp_path/'replay', b)
    assert first['faces'] == replay['faces']
    assert first['fluid_volume_mm3'] == pytest.approx(500)
    assert first['solid_volume_mm3'] == pytest.approx(200)


def test_invalid_domains_are_rejected(cad_files, tmp_path):
    with pytest.raises(ValueError, match='overlap'):
        build(cad_files/'overlap.step', tmp_path/'overlap', geometry())
    with pytest.raises(ValueError, match='No closed volume'):
        build(cad_files/'sheet.step', tmp_path/'sheet')
    with pytest.raises(ValidationError, match='one role'):
        CadGeometry(source_id='a'*64, fluid_bodies=['v_1'], solid_bodies=['v_1'])


@pytest.fixture
def imported(cad_files, tmp_path, monkeypatch):
    root = tmp_path/'runs'; monkeypatch.setenv('PIPE_CFD_RUNS', str(root))
    with TestClient(app) as client:
        response = client.post('/api/cad/sources?filename=pipe.STP', content=(cad_files/'pipe.step').read_bytes())
        assert response.status_code == 201, response.text
        source = response.json()
        g = geometry().model_copy(update={'source_id': source['source_id']})
        response = client.post('/api/cad/preview', json=g.model_dump())
        assert response.status_code == 200, response.text
        built = response.json(); inlet, outlet = ports(built)
        spec = CadDefinition(geometry=g, inlet_faces=inlet, outlet_faces=outlet, boundary_geometry_key=g.key,
            physics={'fluid': 'water', 'inlet': {'kind': 'volumetric_flow', 'value': .6, 'unit': 'L/min'}})
        yield client, spec, built, root


def test_upload_roundtrip_and_authoritative_inlet_metrics(imported, cad_files, tmp_path):
    client, spec, data, root = imported
    response = client.get(f'/api/cad/sources/{spec.geometry.source_id}/file')
    assert response.content == (cad_files/'pipe.step').read_bytes()
    assert client.get(f'/api/cad/sources/{spec.geometry.source_id}').status_code == 200
    body = spec.model_dump()
    body['metrics'] = {'inlet_area_m2': 999, 'hydraulic_diameter_mm': 99, 'length_mm': 99, 'inlet_direction': [0, 1, 0]}
    result = client.post('/api/cad/operating', json=body)
    assert result.status_code == 200, result.text
    assert result.json()['metrics']['inlet_area_m2'] == pytest.approx(pi*25*1e-6)
    assert result.json()['metrics']['hydraulic_diameter_mm'] == pytest.approx(10)
    assert result.json()['flow']['flow_rate_l_min'] == pytest.approx(.6)
    resolved = resolve(spec, root)
    flow_dictionaries(tmp_path/'case', resolved, {'patches': {'inlet': {}, 'outlet': {}, 'wall': {}}})
    text = (tmp_path/'case/0/U').read_text()
    assert 'flowRateInletVelocity' in text and 'volumetricFlowRate constant 1e-05;' in text


def test_wrong_faces_conflicts_and_stale_geometry_rejected(imported):
    client, spec, data, _ = imported
    solid = next(f['id'] for f in data['faces'] if f['thermal_selectable'])
    interface = next(f['id'] for f in data['faces'] if f['region'] == 'interface')
    for bad in (solid, interface, 'missing'):
        body = spec.model_dump(); body['inlet_faces'] = [bad]
        assert client.post('/api/cad/operating', json=body).status_code == 422
    body = spec.model_dump(); body['outlet_faces'] = body['inlet_faces']
    assert client.post('/api/cad/operating', json=body).status_code == 422
    body = spec.model_dump(); body['geometry']['scale'] = 2
    assert client.post('/api/cad/operating', json=body).status_code == 422
    body = spec.model_dump(); body['boundaries'] = [{'id':'heat', 'kind':'heat', 'faces':[interface]}]
    assert client.post('/api/cad/operating', json=body).status_code == 422
    body['boundaries'][0]['faces'] = [solid]
    assert client.post('/api/cad/operating', json=body).status_code == 200


def test_invalid_uploads_and_source_ids(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_CFD_RUNS', str(tmp_path/'runs'))
    # These checks happen before invoking the CAD interpreter.
    monkeypatch.setattr('backend.app.cad_api.ready_mesher', lambda: None)
    with TestClient(app) as client:
        assert client.post('/api/cad/sources?filename=script.geo', content=b'x').status_code == 415
        assert client.post('/api/cad/sources?filename=empty.step', content=b'').status_code == 422
        monkeypatch.setenv('PIPE_CFD_CAD_UPLOAD_BYTES', '4')
        assert client.post('/api/cad/sources?filename=large.step', content=b'12345').status_code == 413
        assert client.get('/api/cad/sources/not-a-source').status_code == 422
        assert client.get('/api/cad/sources/'+'a'*64).status_code == 404


def test_cad_fluid_walls_keep_coupling_and_support_wall_functions(tmp_path):
    path = tmp_path/'boundary'
    path.write_text('inlet { type patch; }\noutlet { type patch; }\nf_cad_12 { type patch; nFaces 12; }\nfluid_to_solid { type mappedWall; neighbourRegion solid; }\n')
    cad_wall_patches(path)
    text = path.read_text()
    assert 'inlet { type patch;' in text and 'outlet { type patch;' in text
    assert 'f_cad_12 { type wall;' in text
    assert 'fluid_to_solid { type mappedWall; neighbourRegion solid;' in text


def test_cad_jobs_are_separate_and_snapshot_resolved_inputs(imported, monkeypatch):
    client, spec, _, root = imported
    monkeypatch.setattr('backend.app.cad_api.builder_health', lambda: {'mesher': {'available': True}, 'openfoam': {'available': True}})
    # This checks submission/persistence only, not a simulated CFD result.
    monkeypatch.setattr('backend.app.runner.JobManager._run', lambda *args: None)
    response = client.post('/api/cad/jobs', json=spec.model_dump())
    assert response.status_code == 202, response.text
    job = response.json()
    assert job['inputs']['metrics']['inlet_area_m2'] == pytest.approx(pi*25*1e-6)
    assert len(client.get('/api/cad/jobs').json()) == 1
    assert client.get('/api/assembly/jobs').json() == [] and client.get('/api/jobs').json() == []
    assert (root/job['id']/'job.json').exists()
