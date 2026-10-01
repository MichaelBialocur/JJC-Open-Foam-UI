from contextlib import asynccontextmanager
import csv
import io
import json
import platform
from uuid import UUID, uuid4
import zipfile

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from .models import PipeDefinition, PRESETS
from .references import reference_for
from .runner import ACTIVE, JobManager, health as foam_health
from .fields import fields_json, meridional_vtk
from .properties import CATALOG
from .assembly_api import router as assembly_router


@asynccontextmanager
async def lifespan(app):
    app.state.jobs = JobManager()
    yield
    app.state.jobs.close()


app = FastAPI(title="Pipe CFD", version="0.6.1", lifespan=lifespan)
app.include_router(assembly_router)


@app.get("/")
def root():
    return {"application": "Pipe CFD", "version": app.version, "status": "running"}


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version, "python": platform.python_version(), "openfoam": foam_health()}


@app.get("/api/presets")
def presets():
    return PRESETS


@app.get("/api/materials")
def materials():
    return CATALOG


@app.post("/api/pipe/preview")
def preview(pipe: PipeDefinition):
    return {**pipe.summary(), "openfoam": foam_health(), "reference": reference_for(pipe)}


def validate_run(pipe):
    if pipe.run_errors():
        raise HTTPException(422, " ".join(pipe.run_errors()))
    status = foam_health()
    if not status["available"]:
        raise HTTPException(503, status["error"])


@app.post("/api/jobs", status_code=202)
def run(pipe: PipeDefinition):
    validate_run(pipe)
    try:
        return app.state.jobs.submit(pipe)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/mesh-studies", status_code=202)
def mesh_study(pipe: PipeDefinition):
    validate_run(pipe)
    manager = app.state.jobs
    with manager.lock:
        if sum(j["status"] in ACTIVE for j in manager.jobs.values()) > 6:
            raise HTTPException(409, "The queue needs space for three refinement runs.")
        study_id = str(uuid4())
        jobs = [manager.submit(pipe.model_copy(update={"mesh_level": level}), study_id) for level in ("coarse", "medium", "fine")]
    return {"id": study_id, "jobs": jobs}


@app.get("/api/jobs")
def jobs():
    return [j for j in app.state.jobs.recent() if j['inputs'].get('geometry_type')!='assembly']


def get_job(job_id):
    try:
        return app.state.jobs.snapshot(str(job_id))
    except KeyError as exc:
        raise HTTPException(404, "Run not found") from exc


@app.get("/api/jobs/{job_id}")
def job(job_id: UUID):
    return get_job(job_id)


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: UUID):
    try:
        app.state.jobs.delete(str(job_id))
    except KeyError as exc:
        raise HTTPException(404, "Run not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, "Could not remove all run files. Check file permissions and try again.") from exc
    fields_json.cache_clear()
    return Response(status_code=204)


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: UUID):
    try:
        return app.state.jobs.cancel(str(job_id))
    except KeyError as exc:
        raise HTTPException(404, "Run not found") from exc


@app.get("/api/jobs/{job_id}/results.json")
def results_json(job_id: UUID):
    data = get_job(job_id)
    if not data.get("results"):
        raise HTTPException(409, "No computed results available")
    payload = {"inputs": data["inputs"], "results": data["results"], "run_id": str(job_id)}
    return Response(json.dumps(payload, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="pipe-{job_id}.json"'})


@app.get("/api/jobs/{job_id}/profile.csv")
def profile_csv(job_id: UUID):
    data = get_job(job_id)
    if not data.get("results"):
        raise HTTPException(409, "No computed results available")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["r_over_R", "velocity_m_s", "u_over_bulk"])
    writer.writeheader()
    writer.writerows(data["results"]["velocity_profile"])
    return Response(output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="profile-{job_id}.csv"'})


@app.get("/api/jobs/{job_id}/case.zip")
def case_zip(job_id: UUID):
    with app.state.jobs.lock:
        data = get_job(job_id)
        if data["status"] in ACTIVE:
            raise HTTPException(409, "Wait for the run to stop before exporting its case")
        case = app.state.jobs.root / str(job_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in case.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    archive.write(path, str(job_id) + "/" + str(path.relative_to(case)))
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="case-{job_id}.zip"'})


def get_fields(job_id):
    with app.state.jobs.lock:
        data = get_job(job_id)
        if not data.get("results"):
            raise HTTPException(409, "No computed fields available until the run finishes")
        case = app.state.jobs.root / str(job_id)
        try:
            return fields_json(str(case), (case / "results.json").stat().st_mtime_ns)
        except (OSError, ValueError) as exc:
            raise HTTPException(409, f"Cannot load the saved mesh/fields: {exc}") from exc


@app.get("/api/jobs/{job_id}/fields.json")
def field_data(job_id: UUID):
    return Response(get_fields(job_id), media_type="application/json")


@app.get("/api/jobs/{job_id}/section.vtk")
def field_vtk(job_id: UUID):
    return Response(meridional_vtk(json.loads(get_fields(job_id))), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="section-{job_id}.vtk"'})


@app.get("/api/jobs/{job_id}/thermal.csv")
def thermal_csv(job_id: UUID):
    data = get_job(job_id)
    thermal = data.get("results", {}).get("thermal")
    if not thermal:
        raise HTTPException(409, "This run has no computed temperature field")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(thermal["profile"][0]))
    writer.writeheader()
    writer.writerows(thermal["profile"])
    return Response(output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="thermal-{job_id}.csv"'})


@app.get("/api/jobs/{job_id}/solid-section.vtk")
def solid_vtk(job_id: UUID):
    data = json.loads(get_fields(job_id))
    if 'solid' not in data:
        raise HTTPException(409, "This run has no computed solid temperature field")
    return Response(meridional_vtk(data['solid']), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="solid-section-{job_id}.vtk"'})
