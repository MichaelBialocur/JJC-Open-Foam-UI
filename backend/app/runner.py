"""One local solver at a time, with persistent manifests, logs, and cancellation."""
import json
import fcntl
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from uuid import uuid4, UUID

from .cases import generate_pipe
from .results import analyse, convergence

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = {"queued", "generating", "meshing", "checking", "solving", "processing"}


@lru_cache(maxsize=1)
def foam_environment():
    bashrc = Path(os.environ.get("OPENFOAM_BASHRC", "/opt/openfoam14/etc/bashrc")).expanduser()
    if not bashrc.is_file():
        raise RuntimeError(f"OpenFOAM 14 environment not found at {bashrc}. Set OPENFOAM_BASHRC or install Foundation OpenFOAM 14.")
    proc = subprocess.run(["bash", "-c", 'source "$1" >/dev/null && env -0', "pipe-cfd", str(bashrc)],
                          capture_output=True, timeout=20)
    if proc.returncode:
        raise RuntimeError("Could not load OpenFOAM: " + proc.stderr.decode(errors="replace")[-1500:])
    env = dict(item.decode().split("=", 1) for item in proc.stdout.split(b"\0") if b"=" in item)
    if env.get("WM_PROJECT_VERSION") != "14":
        raise RuntimeError("Foundation OpenFOAM 14 is required. Detected: " + env.get("WM_PROJECT_VERSION", "unknown"))
    for exe in ("blockMesh", "checkMesh", "foamRun", "foamPostProcess"):
        if not shutil.which(exe, path=env.get("PATH")):
            raise RuntimeError(f"OpenFOAM executable is missing: {exe}")
    env["LC_ALL"] = "C"
    return env


def health():
    try:
        env = foam_environment()
        return {"available": True, "version": env["WM_PROJECT_VERSION"], "solver": "incompressibleFluid"}
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "version": None, "error": str(exc)}


class Cancelled(Exception):
    pass


class JobManager:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("PIPE_CFD_RUNS", ROOT / "runs"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._root_lock = (self.root / ".runner.lock").open("a")
        try:
            fcntl.flock(self._root_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._root_lock.close()
            raise RuntimeError("Another backend or validation process already owns this runs directory. Use one backend worker.") from exc
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="openfoam")
        self.cancel_events = {}
        self.jobs = {}
        for file in self.root.glob("*/job.json"):
            try:
                job = json.loads(file.read_text())
                UUID(job["id"])
                if job["status"] in ACTIVE:
                    job.update(status="interrupted", error="Backend restarted before this job completed.")
                    self._save(job)
                self.jobs[job["id"]] = job
            except (ValueError, KeyError, OSError):
                continue

    def _save(self, job):
        path = self.root / job["id"] / "job.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(job, indent=2, allow_nan=False))
        temp.replace(path)

    def update(self, job_id, **changes):
        with self.lock:
            self.jobs[job_id].update(changes, updated_at=time.time())
            self._save(self.jobs[job_id])

    def submit(self, spec, study_id=None):
        with self.lock:
            if sum(j["status"] in ACTIVE for j in self.jobs.values()) >= 9:
                raise ValueError("The queue is full. Wait for a run to finish or cancel one.")
            job_id = str(uuid4())
            job = {"id": job_id, "status": "queued", "created_at": time.time(), "updated_at": time.time(),
                   "inputs": spec.model_dump(), "study_id": study_id, "error": None}
            self.jobs[job_id] = job
            self.cancel_events[job_id] = threading.Event()
            self._save(job)
            self.executor.submit(self._run, job_id, spec)
            return dict(job)

    def _command(self, job_id, name, args, env, timeout=3600):
        case = self.root / job_id
        event = self.cancel_events[job_id]
        if event.is_set():
            raise Cancelled()
        started = time.monotonic()
        with (case / f"log.{name}").open("w") as log:
            proc = subprocess.Popen(args, cwd=case, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                while proc.poll() is None:
                    if event.is_set():
                        raise Cancelled()
                    if time.monotonic() - started > timeout:
                        raise RuntimeError(f"{name} exceeded the {timeout}s time limit.")
                    event.wait(.2)
                if proc.returncode:
                    raise RuntimeError(f"{name} failed (exit {proc.returncode}). See the run log.")
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
        if event.is_set():
            raise Cancelled()

    def _run(self, job_id, spec):
        case = self.root / job_id
        try:
            if self.cancel_events[job_id].is_set():
                raise Cancelled()
            env = foam_environment()
            self.update(job_id, status="generating", openfoam_version=env["WM_PROJECT_VERSION"])
            generate_pipe(case, spec)
            self.update(job_id, status="meshing")
            self._command(job_id, "blockMesh", ["blockMesh"], env, 180)
            self.update(job_id, status="checking")
            self._command(job_id, "checkMesh", ["checkMesh"], env, 180)
            check_log = (case / "log.checkMesh").read_text(errors="replace")
            if "Mesh OK." not in check_log or re.search(r"Failed \d+ mesh checks", check_log):
                raise RuntimeError("Mesh quality checks did not pass. See log.checkMesh.")
            self._command(job_id, "centres", ["foamPostProcess", "-func", "writeCellCentres", "-time", "0"], env, 120)
            self._command(job_id, "volumes", ["foamPostProcess", "-func", "writeCellVolumes", "-time", "0"], env, 120)
            self.update(job_id, status="solving")
            self._command(job_id, "foamRun", ["foamRun"], env)
            self.update(job_id, status="processing")
            result = analyse(case, spec)
            if self.cancel_events[job_id].is_set():
                raise Cancelled()
            self.update(job_id, status="completed" if result["convergence"]["converged"] else "not_converged")
        except Cancelled:
            self.update(job_id, status="cancelled")
        except Exception as exc:
            self.update(job_id, status="failed", error=str(exc))

    def snapshot(self, job_id, details=True):
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = dict(self.jobs[job_id])
        if details:
            case = self.root / job_id
            logs = []
            for name in ("blockMesh", "checkMesh", "centres", "volumes", "foamRun"):
                file = case / f"log.{name}"
                if file.exists():
                    with file.open("rb") as stream:
                        stream.seek(max(0, file.stat().st_size - 12000))
                        tail = stream.read().decode(errors="replace")
                    logs.append(f"--- {name} ---\n{tail}")
            job["log"] = "\n".join(logs)[-24000:]
            if (case / "log.foamRun").exists():
                job["progress"] = convergence((case / "log.foamRun").read_text(errors="replace"))
            results = case / "results.json"
            if results.exists() and job["status"] in ("completed", "not_converged"):
                job["results"] = json.loads(results.read_text())
        return job

    def recent(self):
        with self.lock:
            return [dict(j) for j in sorted(self.jobs.values(), key=lambda j: j["created_at"], reverse=True)[:50]]

    def cancel(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            if self.jobs[job_id]["status"] in ACTIVE:
                self.cancel_events[job_id].set()
        return self.snapshot(job_id)

    def close(self):
        for event in self.cancel_events.values():
            event.set()
        self.executor.shutdown(wait=True)
        fcntl.flock(self._root_lock, fcntl.LOCK_UN)
        self._root_lock.close()
