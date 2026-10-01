"""Builder routes share the existing serialized solver queue and saved runs."""
from functools import lru_cache
import json
from pathlib import Path
import subprocess
import sys
import threading
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from .assembly_models import AssemblyGeometry, AssemblyDefinition, builder_presets
from .assembly_results import field_surface
from .runner import health

router=APIRouter(prefix='/api/assembly')
preview_lock=threading.Lock()
PROJECT=Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def mesher_health():
    try:
        check=subprocess.run([sys.executable,'-c','import gmsh; print(gmsh.__version__)'],capture_output=True,text=True,timeout=15)
        if check.returncode: raise RuntimeError(check.stderr.strip().splitlines()[-1])
        return {'available':True,'version':check.stdout.strip()}
    except (OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
        return {'available':False,'error':f'Geometry engine unavailable: {exc}. Run bash scripts/setup.sh.'}


@router.get('/presets')
def presets():
    return builder_presets()


@router.get('/health')
def builder_health():
    return {'mesher':mesher_health(),'openfoam':health()}


@router.post('/preview')
def preview(geometry: AssemblyGeometry,request: Request):
    status=mesher_health()
    if not status['available']: raise HTTPException(503,status['error'])
    folder=request.app.state.jobs.root/'_geometry'/geometry.key
    with preview_lock:
        if not (folder/'geometry.json').exists():
            folder.mkdir(parents=True,exist_ok=True)
            (folder/'input.json').write_text(geometry.model_dump_json())
            # Coarse surface tessellation is a preview, not a volume mesh.
            try:
                result=subprocess.run([sys.executable,'-m','backend.app.assembly_geometry',str(folder/'input.json'),str(folder)],cwd=PROJECT,capture_output=True,text=True,timeout=90)
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(422,'Geometry construction exceeded 90 seconds. Simplify the assembly.') from exc
            (folder/'build.log').write_text(result.stdout+'\n'+result.stderr)
            if result.returncode:
                message=(result.stderr or result.stdout).strip().splitlines()[-1]
                raise HTTPException(422,f'Geometry could not be built: {message}')
    return json.loads((folder/'geometry.json').read_text())


@router.post('/operating')
def operating(spec: AssemblyDefinition):
    p=spec.operating;q=p.inlet_velocity_m_s*p.inlet_area_m2
    return {'physics':p.model_dump(),'flow':{'velocity_m_s':p.inlet_velocity_m_s,'flow_rate_l_min':q*60000,
        'mass_flow_kg_h':q*p.density_kg_m3*3600,'reynolds_number':p.reynolds,'model':p.selected_model},'run_errors':spec.run_errors()}


@router.get('/jobs')
def jobs(request: Request):
    return [j for j in request.app.state.jobs.recent() if j['inputs'].get('geometry_type')=='assembly']


@router.post('/jobs',status_code=202)
def submit(spec: AssemblyDefinition,request: Request):
    errors=spec.run_errors()
    if errors: raise HTTPException(422,' '.join(errors))
    status=builder_health()
    for tool in status.values():
        if not tool['available']: raise HTTPException(503,tool['error'])
    folder=request.app.state.jobs.root/'_geometry'/spec.geometry.key
    if not (folder/'geometry.json').exists(): raise HTTPException(422,'Build and inspect the geometry before running.')
    built=json.loads((folder/'geometry.json').read_text());valid={f['id'] for f in built['faces'] if f['selectable']}
    if any(f not in valid for b in spec.boundaries for f in b.faces): raise HTTPException(422,'A thermal selection contains an invalid exterior face.')
    # Save resolved properties as well as the original inlet quantity/units.
    spec.physics=spec.operating.model_dump()
    try: return request.app.state.jobs.submit(spec)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc


def saved(request,job_id):
    try: job=request.app.state.jobs.snapshot(str(job_id))
    except KeyError as exc: raise HTTPException(404,'Run not found') from exc
    if job['inputs'].get('geometry_type')!='assembly': raise HTTPException(422,'This is a straight-pipe benchmark run, not a builder run.')
    return job,request.app.state.jobs.root/str(job_id)


@router.get('/jobs/{job_id}/geometry')
def saved_geometry(job_id: UUID,request: Request):
    with request.app.state.jobs.lock:
        _,folder=saved(request,job_id)
        path=folder/'geometry.json'
        if not path.exists(): raise HTTPException(409,'The run has not finished generating its geometry.')
        return json.loads(path.read_text())


@router.get('/jobs/{job_id}/fields')
def fields(job_id: UUID,request: Request,region: Literal['fluid','solid']='fluid',
           field: Literal['pressure','speed','temperature']='speed',axis: Literal['x','y','z']|None=None,
           fraction: float=Query(default=.5,ge=.001,le=.999)):
    with request.app.state.jobs.lock:
        job,folder=saved(request,job_id)
        if not job.get('results'): raise HTTPException(409,'Computed fields are available after the run finishes.')
        try: return field_surface(folder,region,field,axis,fraction)
        except (OSError,ValueError) as exc: raise HTTPException(422,str(exc)) from exc
