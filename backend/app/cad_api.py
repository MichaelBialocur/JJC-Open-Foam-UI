"""Local CAD upload and domain/face assignment. No caller-supplied file paths."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from .assembly_api import PROJECT, builder_health, mesher_health, preview_lock
from .cad_models import CadGeometry, CadDefinition, CadMetrics

router = APIRouter(prefix='/api/cad')
FORMATS = {'.step': '.step', '.stp': '.step', '.iges': '.iges', '.igs': '.iges', '.brep': '.brep'}


def source_file(root, source_id):
    if not re.fullmatch(r'[a-f0-9]{64}', source_id):
        raise HTTPException(422, 'Invalid CAD source ID.')
    folder = root/'_cad_sources'/source_id
    try:
        metadata = json.loads((folder/'source.json').read_text())
        suffix = metadata['suffix']
        if suffix not in FORMATS.values():
            raise ValueError('Invalid source format')
        path = folder/('source'+suffix)
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError()
        return path, metadata
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(404, 'CAD source is unavailable. Upload the original CAD file again.') from exc


def generate(source, folder, geometry=None):
    folder.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, '-m', 'backend.app.cad_geometry', str(source), str(folder)]
    if geometry:
        (folder/'input.json').write_text(geometry.model_dump_json())
        args += ['--spec', str(folder/'input.json')]
    with (folder/'build.log').open('w') as log:
        try:
            result = subprocess.run(args, cwd=PROJECT, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(422, 'CAD preview exceeded 180 seconds. Simplify tiny features or split the model before importing.') from exc
    if result.returncode:
        with (folder/'build.log').open('rb') as log:
            log.seek(max(0, (folder/'build.log').stat().st_size-3000))
            lines = log.read().decode(errors='replace').strip().splitlines()
        raise HTTPException(422, 'CAD import failed: '+(lines[-1] if lines else 'See the build log.'))
    return json.loads((folder/'geometry.json').read_text())


def ready_mesher():
    status = mesher_health()
    if not status['available']:
        raise HTTPException(503, status['error'])


@router.post('/sources', status_code=201)
async def upload(request: Request, filename: str = Query(min_length=1, max_length=240)):
    ready_mesher()
    name = filename.replace('\\', '/').split('/')[-1]
    suffix = FORMATS.get(Path(name).suffix.lower())
    if suffix is None:
        raise HTTPException(415, 'Choose STEP (.step/.stp), IGES (.iges/.igs), or BREP (.brep). Export native CAD parts to STEP; STL/OBJ are not solid CAD bodies.')
    root = request.app.state.jobs.root/'_cad_sources'
    root.mkdir(exist_ok=True)
    # Stream to disk, never buffer an entire CAD upload in API memory.
    limit = int(os.environ.get('PIPE_CFD_CAD_UPLOAD_BYTES', 256*1024*1024))
    digest, size = sha256(), 0
    with tempfile.TemporaryDirectory(prefix='upload-', dir=root) as temporary:
        path = Path(temporary)/('source'+suffix)
        with path.open('wb') as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f'CAD upload exceeds the configured {limit//(1024*1024)} MiB file limit.')
                digest.update(chunk); output.write(chunk)
        if size == 0:
            raise HTTPException(422, 'The CAD file is empty.')
        source_id = digest.hexdigest()
        destination = root/source_id
        def finish():
            with preview_lock:
                if not (destination/'source.json').exists():
                    generate(path, Path(temporary))
                    metadata = {'source_id': source_id, 'filename': name, 'suffix': suffix, 'bytes': size}
                    (Path(temporary)/'source.json').write_text(json.dumps(metadata))
                    if destination.exists():
                        raise HTTPException(409, 'An incomplete CAD import exists. Try another file or remove its incomplete import directory.')
                    shutil.copytree(temporary, destination)
                return {**json.loads((destination/'source.json').read_text()), 'preview': json.loads((destination/'geometry.json').read_text())}
        return await run_in_threadpool(finish)


@router.get('/sources/{source_id}')
def source_info(source_id: str, request: Request):
    path, metadata = source_file(request.app.state.jobs.root, source_id)
    return {**metadata, 'preview': json.loads((path.parent/'geometry.json').read_text())}


@router.get('/sources/{source_id}/file')
def download_source(source_id: str, request: Request):
    path, metadata = source_file(request.app.state.jobs.root, source_id)
    return FileResponse(path, filename=metadata['filename'], media_type='application/octet-stream')


@router.post('/preview')
def preview(geometry: CadGeometry, request: Request):
    ready_mesher()
    source, _ = source_file(request.app.state.jobs.root, geometry.source_id)
    folder = request.app.state.jobs.root/'_geometry'/geometry.key
    with preview_lock:
        if not (folder/'geometry.json').exists():
            return generate(source, folder, geometry)
        return json.loads((folder/'geometry.json').read_text())


def resolve(spec, root):
    source_file(root, spec.geometry.source_id)
    folder = root/'_geometry'/spec.geometry.key
    if not (folder/'geometry.json').exists():
        raise HTTPException(422, 'Prepare the CAD bodies before assigning faces and running.')
    data = json.loads((folder/'geometry.json').read_text())
    faces = {f['id']: f for f in data['faces']}
    if not spec.inlet_faces or not spec.outlet_faces:
        raise HTTPException(422, 'Select at least one fluid inlet face and one fluid outlet face.')
    for name, selection in [('inlet', spec.inlet_faces), ('outlet', spec.outlet_faces)]:
        if any(f not in faces or not faces[f]['port_selectable'] or not faces[f]['planar'] for f in selection):
            raise HTTPException(422, f'Every {name} must be a planar exterior face of the fluid volume, not a solid face or internal interface.')
    thermal = [f for b in spec.boundaries for f in b.faces]
    if any(f not in faces or not faces[f]['thermal_selectable'] for f in thermal):
        raise HTTPException(422, 'Heating and cooling can only be assigned to exterior solid faces. Include the surrounding solid bodies for thermal simulation.')
    area = sum(faces[f]['area_mm2'] for f in spec.inlet_faces)
    curves = {}
    for f in spec.inlet_faces:
        for key, length in faces[f]['curves_mm'].items():
            count, _ = curves.get(key, (0, length)); curves[key] = (count+1, length)
    perimeter = sum(length for count, length in curves.values() if count == 1)
    if perimeter <= 0:
        raise HTTPException(422, 'The selected inlet has no valid perimeter.')
    direction = -sum((np.array(faces[f]['outward_normal'])*faces[f]['area_mm2'] for f in spec.inlet_faces), np.zeros(3))
    if np.linalg.norm(direction) < area*1e-8:
        direction = -np.array(faces[spec.inlet_faces[0]]['outward_normal'])
    direction /= np.linalg.norm(direction)
    bounds = np.array(data['bounds_mm'])
    # Always overwrite caller-provided metrics: flow conversion uses actual CAD.
    spec.metrics = CadMetrics(inlet_area_m2=area*1e-6, hydraulic_diameter_mm=4*area/perimeter,
        length_mm=float(np.linalg.norm(bounds[1]-bounds[0])), inlet_direction=tuple(direction))
    try:
        spec.operating
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return spec


@router.post('/operating')
def operating(spec: CadDefinition, request: Request):
    spec = resolve(spec, request.app.state.jobs.root)
    p = spec.operating; q = p.inlet_velocity_m_s*p.inlet_area_m2
    return {'physics': p.model_dump(), 'metrics': spec.metrics.model_dump(), 'flow': {
        'velocity_m_s': p.inlet_velocity_m_s, 'flow_rate_l_min': q*60000,
        'mass_flow_kg_h': q*p.density_kg_m3*3600, 'reynolds_number': p.reynolds, 'model': p.selected_model},
        'run_errors': spec.run_errors()}


@router.get('/jobs')
def jobs(request: Request):
    return [j for j in request.app.state.jobs.recent() if j['inputs'].get('geometry_type') == 'cad']


@router.post('/jobs', status_code=202)
def submit(spec: CadDefinition, request: Request):
    spec = resolve(spec, request.app.state.jobs.root)
    if spec.run_errors():
        raise HTTPException(422, ' '.join(spec.run_errors()))
    for status in builder_health().values():
        if not status['available']:
            raise HTTPException(503, status['error'])
    spec.physics = spec.operating.model_dump()
    try:
        return request.app.state.jobs.submit(spec)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
