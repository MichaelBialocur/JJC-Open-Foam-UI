"""Contracts that can corrupt a native coupled solve, using synthetic fixtures."""
import json
from math import pi, sin, radians

import pytest
from pydantic import ValidationError

from backend.app.cases import generate_pipe
from backend.app.conjugate import mass_flux
from backend.app.models import PipeDefinition, PRESETS
from backend.app.results import read_internal, read_patch, convergence
from backend.app.thermal import prepare_thermal


def test_saved_run_compatibility_and_solid_properties():
    assert PipeDefinition().thermal_mode == 'fluid_only'
    assert PipeDefinition(material='copper').solid_conductivity == 391.1
    assert PipeDefinition(material='copper', solid_conductivity_w_m_k=15).solid_conductivity == 15
    with pytest.raises(ValidationError):
        PipeDefinition(solid_conductivity_w_m_k=0)
    spec=PipeDefinition(**PRESETS['heated_wall']['inputs'])
    assert spec.summary()['mesh']['cells']==240*(32+16)


def test_flux_conversion_keeps_conservative_face_order(tmp_path):
    text='''dimensions [0 3 -1 0 0 0 0];
internalField nonuniform List<scalar> 3 (1 -2 3e-5);
boundaryField { inlet { value nonuniform List<scalar> 2 (-1 -2); }
outlet { value uniform 3; } wall { value uniform 0; } }'''
    p=tmp_path/'phi'; p.write_text(mass_flux(text,998))
    assert '[1 0 -1 0 0 0 0]' in p.read_text()
    assert read_internal(p).tolist()==pytest.approx([998,-1996,.02994])
    assert read_patch(p,'inlet',2).sum()+read_patch(p,'outlet',1).sum()==0
    assert read_patch(p,'wall',3).tolist()==[0,0,0]
    with pytest.raises(ValueError):mass_flux('dimensions [1 0 -1 0 0 0 0];',998)


def test_nested_external_heat_bc_and_prefixed_multi_region_log(tmp_path):
    p=tmp_path/'T'
    p.write_text('boundaryField { outer { Q { type constant; value 0.1; } value nonuniform List<scalar> 2 (300 310); } }')
    assert read_patch(p,'outer',2).tolist()==[300,310]
    c=convergence('      Time = 1000s\nfluid solver: Solving for h, Initial residual = 1e-8\nsolid solver: Solving for e, Initial residual = 2e-8')
    assert c['iteration']==1000 and c['residuals']['h']==1e-8 and c['residuals']['e']==2e-8


def test_outer_power_and_conformal_mapping_contract(tmp_path):
    spec=PipeDefinition(**{**PRESETS['heated_wall']['inputs'],'mesh_level':'coarse','material':'copper'})
    generate_pipe(tmp_path,spec)
    mesh=tmp_path/'constant/polyMesh';mesh.mkdir()
    (mesh/'boundary').write_text('wall { type wall; nFaces 120; startFace 12; }')
    (tmp_path/'2500').mkdir()
    (tmp_path/'2500/phi').write_text('dimensions [0 3 -1 0 0 0 0]; internalField uniform 0;')
    thermal=prepare_thermal(tmp_path,spec,2500)
    manifest=json.loads((thermal/'manifest.json').read_text())
    assert manifest['wedge_outer_power_w']*2*pi/sin(radians(5))==pytest.approx(10)
    assert 'neighbourRegion solid; neighbourPatch inner;' in (thermal/'constant/fluid/polyMesh/boundary').read_text()
    assert 'neighbourRegion fluid; neighbourPatch wall;' in (thermal/'system/solid/blockMeshDict').read_text()
    assert '391.1' in (thermal/'constant/solid/physicalProperties').read_text()
    assert 'flow false;' in (thermal/'system/fluid/fvSolution').read_text()
    assert 'type coupledTemperature' in (thermal/'0/solid/T').read_text()
    assert 'type externalTemperature' in (thermal/'0/solid/T').read_text()
