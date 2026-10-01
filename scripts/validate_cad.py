#!/usr/bin/env python3
"""Real STEP import -> mesh -> OpenFOAM flow/CHT study; no synthetic fields."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.results import read_internal  # noqa: E402
from backend.app.assembly_mesh import read_mesh  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT/'validation-output/cad-v070'))
    parser.add_argument('--sizes', nargs='+', type=float, default=[2, 1.4, 1])
    parser.add_argument('--flow-only', action='store_true')
    parser.add_argument('--reverse', action='store_true')
    parser.add_argument('--partial-wall', action='store_true')
    parser.add_argument('--velocity', type=float, default=.01, help='Mean inlet speed in m/s')
    args = parser.parse_args()
    folder = Path(args.output).resolve(); folder.mkdir(parents=True, exist_ok=True)
    source = folder/'pipe.step'
    script = """import gmsh,sys
gmsh.initialize();o=gmsh.model.occ
f=o.addCylinder(0,0,0,100,0,0,5)
s=o.addCylinder(25 if sys.argv[2]=='partial' else 0,0,0,50 if sys.argv[2]=='partial' else 100,0,0,6)
o.cut([(3,s)],[(3,f)],removeTool=False);o.synchronize();gmsh.write(sys.argv[1]);gmsh.finalize()
"""
    subprocess.run([sys.executable, '-c', script, str(source), 'partial' if args.partial_wall else 'full'], check=True, stdout=subprocess.DEVNULL)
    os.environ['PIPE_CFD_RUNS'] = str(folder/'runs')
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.cad_models import CadDefinition
    rows = []
    with TestClient(app) as client:
        def post(url, **kwargs):
            response = client.post(url, **kwargs)
            if response.status_code >= 300:
                raise RuntimeError(response.text)
            return response.json()
        uploaded = post('/api/cad/sources?filename=pipe.step', content=source.read_bytes())
        geometry = {'source_id': uploaded['source_id'], 'scale': 1, 'fluid_bodies': ['v_1'], 'solid_bodies': [] if args.flow_only else ['v_2']}
        built = post('/api/cad/preview', json=geometry)
        ports = sorted((f for f in built['faces'] if f['port_selectable'] and f['planar']), key=lambda f:f['center_mm'][0])
        if args.reverse:
            ports.reverse()
        solid = [f for f in built['faces'] if f['thermal_selectable']]
        heating = [f['id'] for f in solid if not f['planar']]
        cooling = [f['id'] for f in solid if f['planar']]
        for size in args.sizes:
            spec = {'geometry_type': 'cad', 'name': f'STEP pipe {"flow" if args.flow_only else "CHT"} {size} mm', 'geometry': geometry,
                'boundary_geometry_key': built['geometry_key'], 'inlet_faces': [ports[0]['id']], 'outlet_faces': [ports[-1]['id']],
                'mesh_size_mm': size, 'boundaries': [
                    {'id':'heater','kind':'heat','faces':heating,'power_w':10},
                    {'id':'cooler','kind':'convection','faces':cooling,'h_w_m2_k':1000,'ambient_c':15}],
                'physics': {'fluid':'water','inlet':{'kind':'velocity','value':args.velocity,'unit':'m/s'},
                            'max_iterations':3000,'thermal_iterations':2000,'residual_tolerance':1e-6}}
            if args.flow_only:
                spec['boundaries'] = []
            started = time.monotonic(); job = post('/api/cad/jobs', json=spec)
            print(f"Running STEP import and {'flow' if args.flow_only else 'coupled heat transfer'}: {size} mm, {job['id']}", flush=True)
            while job['status'] in ('queued','generating','meshing','checking','solving','heating','processing'):
                time.sleep(.5)
                job = client.get('/api/jobs/'+job['id']).json()
            row = {'mesh_size_mm':size,'run_id':job['id'],'status':job['status'],'error':job.get('error'),
                   'runtime_seconds':round(time.monotonic()-started,2),'inputs':job['inputs'],'results':job.get('results')}
            if job.get('results') and CadDefinition(**job['inputs']).operating.selected_model == 'laminar':
                case = folder/'runs'/job['id']; mesh = read_mesh(case/'constant/polyMesh'); n = mesh['cell_count']
                centres = read_internal(case/'0/C',3,n); volumes = read_internal(case/'0/Vc',count=n)
                p = job['inputs']['physics']; latest = case/str(job['results']['solution_iteration'])
                pressure = read_internal(latest/'p',count=n)*p['density_kg_m3']; x = .1-centres[:,0] if args.reverse else centres[:,0]
                mask = (x>.06)&(x<.085)
                slope = np.polyfit(x[mask],pressure[mask],1,w=np.sqrt(volumes[mask]))[0]
                q = job['results']['volumetric_flow_l_min']/60000; u = q/(np.pi*.005**2)
                expected = 32*p['dynamic_viscosity_pa_s']*u/.01**2
                row['analytical_screen'] = {'kind':'analytical, not experimental','reference':'Hagen–Poiseuille developed gradient, 32 mu U / D²',
                    'fit_interval_m':[.06,.085],'computed_gradient_pa_m':float(-slope),'reference_gradient_pa_m':float(expected),
                    'gradient_error_percent':float(100*(-slope/expected-1)),
                    'note':'Entrance length and mesh dependence must be assessed; no automatic CAD accuracy qualification.'}
            rows.append(row)
            case_description = '100 mm pipe, 10 mm bore; STEP imported as fluid'
            if not args.flow_only:
                case_description += (' + aluminium sleeve from x=25 to 75 mm' if args.partial_wall else ' + full-length aluminium wall')
                case_description += ', 1 mm thickness; 10 W outer heating, solid-end convection h=1000 W/m²K to 15 °C'
            (folder/'summary.json').write_text(json.dumps({'schema':1,'case':case_description,
                'flow_only':args.flow_only,'reverse_flow':args.reverse,'partial_wall':args.partial_wall,
                'openfoam':'Foundation 14','source_sha256':uploaded['source_id'],'runs':rows},indent=2))
            print(json.dumps({k:row[k] for k in ['mesh_size_mm','status','error','runtime_seconds']}),flush=True)
    return int(any(r['status'] not in ('completed','not_converged') for r in rows))


if __name__ == '__main__':
    raise SystemExit(main())
