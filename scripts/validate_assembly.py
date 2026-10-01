"""Reproduce the full 3D pipe reference and cold-plate mesh-sensitivity cases."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.assembly_models import AssemblyDefinition, AssemblyGeometry, builder_presets
from backend.app.runner import JobManager, ACTIVE


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('validation-output/assembly'))
    parser.add_argument('--case',choices=['all','pipe','coldplate','elbow'],default='all')
    args=parser.parse_args();manager=JobManager(args.output.resolve());rows=[]
    try:
        names=['pipe','coldplate','elbow'] if args.case=='all' else [args.case]
        for name in names:
            geometry=AssemblyGeometry(**builder_presets()[name]['geometry'])
            for size in ([2,1,.65] if name=='pipe' else [2,1.4,1] if name=='coldplate' else [2]):
                boundaries=[]
                if name=='coldplate':
                    boundaries=[dict(id='heat1',name='Top and bottom, 10 W total',kind='heat',faces=['f_plate1_1','f_plate1_2'],power_w=10),
                        dict(id='cool1',name='Side convection',kind='convection',faces=['f_plate1_0','f_plate1_3'],h_w_m2_k=500,ambient_c=20)]
                physics={'fluid':'water','inlet':{'kind':'velocity','value':.001,'unit':'m/s'} if name=='pipe' else {'kind':'volumetric_flow','value':.1,'unit':'L/min'},'max_iterations':2500,'thermal_iterations':500}
                spec=AssemblyDefinition(name=f'{name} {size} mm',geometry=geometry,physics=physics,mesh_size_mm=size,boundaries=boundaries,boundary_geometry_key=geometry.key)
                job=manager.submit(spec);print(name,size,job['id'],flush=True)
                while manager.snapshot(job['id'],False)['status'] in ACTIVE: time.sleep(.5)
                job=manager.snapshot(job['id']);result=job.get('results',{})
                for key in ['convergence']:
                    if key in result: result[key].pop('history',None)
                if 'thermal' in result: result['thermal']['convergence'].pop('history',None)
                row={'case':name,'mesh_size_mm':size,'job_id':job['id'],'status':job['status'],'error':job.get('error'),'inputs':spec.model_dump(),'results':result}
                rows.append(row);(args.output/'summary.json').write_text(json.dumps(rows,indent=2,allow_nan=False))
                print(json.dumps({'case':name,'size':size,'status':job['status'],'error':job.get('error'),'checks':result.get('checks'),'pressure_pa':result.get('pressure_drop_pa'),'reference':result.get('reference')}),flush=True)
    finally: manager.close()

if __name__=='__main__': main()
