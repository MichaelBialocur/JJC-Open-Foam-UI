"""Numerical/data-contract checks; synthetic fields below are test fixtures only."""
import json
from math import pi, sin, radians
from pathlib import Path
import threading
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.models import PipeDefinition, PRESETS
from backend.app.cases import generate_pipe
from backend.app.references import reference_for, SUPERPIPE
from backend.app.results import read_internal, convergence, analyse
from backend.app.runner import JobManager, Cancelled
from backend.app.main import app


def test_regimes_and_thermal_scope():
    assert PipeDefinition().selected_model == 'kOmegaSST'
    p = PipeDefinition(**PRESETS['laminar']['inputs'])
    assert p.reynolds == pytest.approx(100)
    assert p.selected_model == 'laminar'
    assert p.model_copy(update={'applied_heat_w':500}).run_errors()
    assert PipeDefinition(inlet_velocity_m_s=3000*p.nu/p.diameter_m).run_errors()
    assert PipeDefinition(flow_model='laminar').run_errors()


@pytest.mark.parametrize('changes', [{'length_mm':-1}, {'inner_diameter_mm':float('nan')},
    {'density_kg_m3':0}, {'dynamic_viscosity_pa_s':float('inf')}, {'geometry_type':'$(touch hacked)'}, {'max_iterations':1000000}, {'max_iterations':251}])
def test_invalid_inputs(changes):
    with pytest.raises(ValidationError):
        PipeDefinition(**changes)


def test_experimental_reference_does_not_extrapolate():
    assert not reference_for(PipeDefinition())['applicable']
    ref = reference_for(PipeDefinition(**PRESETS['superpipe']['inputs']))
    assert ref['applicable'] and ref['kind'] == 'experiment'
    assert len(ref['profile']) == 42
    assert ref['darcy_friction_factor'] == .021858
    assert ref['profile'][0]['u_over_bulk'] == pytest.approx(23.654 * .26825 / 5.132)
    assert 'NOT' in SUPERPIPE['caveat']


def test_generated_case_uses_correct_model_and_scope(tmp_path):
    spec = PipeDefinition()
    generate_pipe(tmp_path, spec)
    assert 'kOmegaSST' in (tmp_path/'constant/momentumTransport').read_text()
    assert (tmp_path/'0/omega').exists()
    assert 'noSlip' in (tmp_path/'0/U').read_text()
    assert not (tmp_path/'0/T').exists()
    with pytest.raises(ValueError):
        generate_pipe(tmp_path/'invalid', spec.model_copy(update={'applied_heat_w':1}))


def write_field(path, values):
    values = np.asarray(values)
    kind = 'vector' if values.ndim == 2 else 'scalar'
    rows = ['('+' '.join(map(str,row))+')' if kind=='vector' else str(row) for row in values]
    path.write_text(f'internalField nonuniform List<{kind}>\n{len(values)}\n(\n'+'\n'.join(rows)+'\n);\n')


def test_ascii_reader_and_residuals(tmp_path):
    p=tmp_path/'p'
    p.write_text('internalField uniform 2;')
    assert read_internal(p,count=3).tolist() == [2,2,2]
    p.write_text('internalField nonuniform List<scalar> 3 (1 2);')
    with pytest.raises(ValueError): read_internal(p)
    p.write_text('internalField uniform nan;')
    with pytest.raises(ValueError): read_internal(p,count=3)
    log='Time = 20s\nGAMG: Solving for p, Initial residual = 0.1, Final residual = 1e-8\nGAMG: Solving for p, Initial residual = 1e-9, Final residual = 1e-10\n'
    r=convergence(log)
    assert r['residuals']['p']==.1
    assert not r['solver_converged']


def test_pressure_units_face_mass_balance_and_validation_gates(tmp_path):
    spec=PipeDefinition(**{**PRESETS['laminar']['inputs'],'mesh_level':'coarse'})
    nx,nr=spec.mesh_shape
    radius=spec.diameter_m/2
    x=(np.arange(nx)+.5)*spec.length_m/nx
    r=(np.arange(nr)+.5)*radius/nr
    centres=np.array([[a,b,0] for b in r for a in x])
    volumes=np.array([b for b in r for _ in x])
    gradient=32*spec.dynamic_viscosity_pa_s*spec.inlet_velocity_m_s/spec.diameter_m**2
    p=gradient*(spec.length_m-centres[:,0])/spec.density_kg_m3
    u=np.zeros_like(centres);u[:,0]=2*spec.inlet_velocity_m_s*(1-(centres[:,1]/radius)**2)
    for folder in ['0','100','200']:(tmp_path/folder).mkdir()
    write_field(tmp_path/'0/C',centres);write_field(tmp_path/'0/Vc',volumes)
    for folder in ['100','200']:
        write_field(tmp_path/folder/'U',u);write_field(tmp_path/folder/'p',p)
    q=.5*radius**2*sin(radians(5))*spec.inlet_velocity_m_s
    flux=f'boundaryField {{ inlet {{ value uniform {-q/nr}; }} outlet {{ value uniform {q/nr}; }} }}'
    (tmp_path/'200/phi').write_text(flux)
    log='Time = 200s\n'+'\n'.join(f'Solving for {v}, Initial residual = 1e-10, Final residual = 1e-12' for v in ['p','Ux','Uy','Uz'])
    (tmp_path/'log.foamRun').write_text(log)
    result=analyse(tmp_path,spec)
    assert result['darcy_friction_factor']==pytest.approx(.64)
    assert result['developed_pressure_gradient_pa_m']==pytest.approx(gradient)
    assert result['mass_flow_kg_s']==pytest.approx(spec.density_kg_m3*pi*radius**2*spec.inlet_velocity_m_s)
    assert result['validation']['status']=='within_project_target'
    assert result['convergence']['saved_field_stationarity_passed']
    # Low residuals alone cannot qualify a solution whose saved fields still change.
    write_field(tmp_path/'100/U',u*.99)
    assert not analyse(tmp_path,spec)['convergence']['converged']
    write_field(tmp_path/'100/U',u)
    (tmp_path/'log.foamRun').write_text(log.replace('Time = 200s','Time = 250s'))
    assert not analyse(tmp_path,spec)['convergence']['final_field_written']
    (tmp_path/'log.foamRun').write_text(log)
    # A large unconverged pressure residual must not be rescued by stationary fields.
    (tmp_path/'log.foamRun').write_text(log.replace('for p, Initial residual = 1e-10','for p, Initial residual = 0.1'))
    assert analyse(tmp_path,spec)['validation']['status']=='not_qualified'
    (tmp_path/'200/phi').write_text(flux.replace(f'outlet {{ value uniform {q/nr};', f'outlet {{ value uniform {1.1*q/nr};'))
    assert not analyse(tmp_path,spec)['validation']['checks']['mass_balance_below_0_5_percent']


def test_restart_and_cancellation(tmp_path):
    jid=str(uuid4());p=tmp_path/jid;p.mkdir()
    (p/'job.json').write_text(json.dumps({'id':jid,'status':'solving','created_at':0}))
    manager=JobManager(tmp_path)
    with pytest.raises(RuntimeError, match='already owns'):
        JobManager(tmp_path)
    assert manager.snapshot(jid)['status']=='interrupted'
    event=threading.Event();event.set();manager.cancel_events[jid]=event
    with pytest.raises(Cancelled):manager._command(jid,'unused',['false'],{})
    manager.close()


def test_api_errors_and_persistence(tmp_path,monkeypatch):
    monkeypatch.setenv('PIPE_CFD_RUNS',str(tmp_path))
    monkeypatch.setattr('backend.app.main.foam_health',lambda:{'available':False,'error':'Test: OpenFOAM absent'})
    with TestClient(app) as client:
        assert client.get('/api/health').json()['openfoam']['available'] is False
        preview=client.post('/api/pipe/preview',json={}).json()
        assert preview['flow']['reynolds_number']==pytest.approx(9960.0798403)
        assert client.post('/api/jobs',json={}).status_code==503
        assert client.post('/api/jobs',json={'length_mm':-1}).status_code==422
        assert client.get('/api/jobs/not-a-uuid').status_code==422
        assert client.get('/api/jobs/'+str(uuid4())).status_code==404
        assert client.get('/api/jobs').json()==[]
