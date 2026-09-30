"""Boundary conservation and field indexing checks; all numeric fixtures are synthetic."""
import json
from math import cos, pi, radians, sin

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.cases import generate_pipe
from backend.app.fields import meridional_vtk, mesh_points
from backend.app.models import PipeDefinition, PRESETS
from backend.app.results import read_patch
from backend.app.thermal import prepare_thermal, THERMAL_REFERENCE


@pytest.mark.parametrize('change', [{'specific_heat_j_kg_k':0}, {'thermal_conductivity_w_m_k':-1},
                                  {'turbulent_prandtl':0}, {'thermal_iterations':151}])
def test_thermal_input_limits(change):
    with pytest.raises(ValidationError):
        PipeDefinition(**change)


def test_energy_input_boundary_and_solver_are_dimensionally_consistent(tmp_path):
    spec = PipeDefinition(**PRESETS['heated_laminar']['inputs'])
    generate_pipe(tmp_path, spec)
    (tmp_path/'100').mkdir()
    (tmp_path/'100/U').write_text('test placeholder')
    thermal = prepare_thermal(tmp_path,spec,100)
    manifest = json.loads((thermal/'manifest.json').read_text())
    area = spec.diameter_m * sin(radians(2.5)) * spec.length_m
    assert manifest['wall_flux_on_planar_wedge_w_m2'] * area * manifest['wedge_to_full_pipe_scale'] == pytest.approx(10)
    q = 10 / (pi * spec.diameter_m * spec.length_m) * cos(radians(2.5))
    content = (thermal/'0/T').read_text()
    assert f'gradient uniform {q/spec.thermal_conductivity_w_m_k:.14g}' in content
    assert '293.15' in content and '[0 0 0 1 0 0 0]' in content
    assert 'solver functions;' in (thermal/'system/controlDict').read_text()
    assert 'diffusivity constant' in (thermal/'system/controlDict').read_text()
    assert (thermal/'0/U').read_text()=='test placeholder'
    assert THERMAL_REFERENCE['nusselt']==pytest.approx(48/11)


def test_turbulent_transport_uses_viscosity_and_prandtl_closure(tmp_path):
    spec=PipeDefinition(applied_heat_w=100)
    generate_pipe(tmp_path,spec);(tmp_path/'100').mkdir()
    thermal=prepare_thermal(tmp_path,spec,100)
    control=(thermal/'system/controlDict').read_text()
    assert 'diffusivity viscosity' in control
    assert f'alphal {1/spec.prandtl:.14g}' in control
    assert f'alphat {1/spec.turbulent_prandtl:.14g}' in control


def test_scalar_patch_order_is_preserved(tmp_path):
    p=tmp_path/'phi'
    p.write_text('boundaryField { outlet { value nonuniform List<scalar> 3 (2 4 8); } }')
    assert read_patch(p,'outlet',3).tolist()==[2,4,8]
    with pytest.raises(ValueError):read_patch(p,'outlet',2)


def test_ascii_mesh_and_vtk_cell_order(tmp_path):
    p=tmp_path/'points'
    p.write_text('FoamFile {format ascii; class vectorField; object points;}\n3\n((0 0 0) (1 0 0) (1 2 0))\n// end')
    assert np.array_equal(mesh_points(p),[[0,0,0],[1,0,0],[1,2,0]])
    data={'nx':2,'nr':3,'x_edges_m':[0,1,2],'r_edges_m':[0,1,2,3],
          'fields':{'pressure':{'values':[10,11,12,20,21,22]}}}
    vtk=meridional_vtk(data)
    assert 'DIMENSIONS 3 4 1' in vtk and 'CELL_DATA 6' in vtk
    # VTK's x index varies fastest; our API's radial index varies fastest.
    assert vtk.split('LOOKUP_TABLE default\n')[1].splitlines()==['10','20','11','21','12','22']
