"""Saved-run removal must preserve live solvers, other runs and restart history."""
import json
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.runner import ACTIVE, DELETABLE, JobManager


def saved_run(root, status="completed", geometry_type="pipe", created_at=0):
    job_id = str(uuid4())
    job = {"id": job_id, "status": status, "created_at": created_at,
           "inputs": {"geometry_type": geometry_type}, "study_id": "shared-study"}
    folder = root / job_id
    (folder / "constant" / "polyMesh").mkdir(parents=True)
    (folder / "job.json").write_text(json.dumps(job))
    (folder / "results.json").write_text('{"computed": true}')
    (folder / "log.foamRun").write_text("")
    (folder / "constant" / "polyMesh" / "points").write_text("mesh fixture")
    return job_id


@pytest.mark.parametrize("status", sorted(DELETABLE))
@pytest.mark.parametrize("geometry_type", ["pipe", "assembly"])
def test_delete_removes_case_and_history_across_restart(tmp_path, status, geometry_type):
    target = saved_run(tmp_path, status, geometry_type)
    other = saved_run(tmp_path, "completed", geometry_type)
    (tmp_path / "_geometry" / "shared-preview").mkdir(parents=True)
    manager = JobManager(tmp_path)
    try:
        manager.cancel_events[target] = threading.Event()
        manager.delete(target)
        assert not (tmp_path / target).exists()
        assert target not in manager.cancel_events
        assert [j["id"] for j in manager.recent()] == [other]
        assert manager.snapshot(other)["results"] == {"computed": True}
        assert (tmp_path / "_geometry" / "shared-preview").exists()
        with pytest.raises(KeyError):
            manager.snapshot(target)
    finally:
        manager.close()
    restarted = JobManager(tmp_path)
    try:
        assert [j["id"] for j in restarted.recent()] == [other]
    finally:
        restarted.close()


@pytest.mark.parametrize("status", sorted(ACTIVE))
def test_delete_rejects_every_active_stage(tmp_path, status):
    target = saved_run(tmp_path)
    manager = JobManager(tmp_path)
    try:
        manager.update(target, status=status)
        with pytest.raises(ValueError, match="wait for it to stop"):
            manager.delete(target)
        assert manager.snapshot(target)["status"] == status
        assert (tmp_path / target / "constant" / "polyMesh" / "points").exists()
    finally:
        manager.close()


def test_delete_does_not_follow_symlinks(tmp_path):
    root = tmp_path / "runs"
    target = saved_run(root)
    outside = tmp_path / "other-data"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep me")
    (root / target / "linked-data").symlink_to(outside, target_is_directory=True)
    manager = JobManager(root)
    try:
        manager.delete(target)
        assert (outside / "keep.txt").read_text() == "keep me"
        # A symlink replacing the whole case is rejected as well.
        (root / target).symlink_to(outside, target_is_directory=True)
        manager.jobs[target] = {"id": target, "status": "completed", "created_at": 0}
        with pytest.raises(ValueError, match="symbolic link"):
            manager.delete(target)
        with pytest.raises(ValueError):
            manager.delete("../other-data")
    finally:
        manager.close()


def test_api_delete_and_entire_workspace_histories(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPE_CFD_RUNS", str(tmp_path))
    oldest = saved_run(tmp_path, created_at=0)
    for i in range(55):
        saved_run(tmp_path, geometry_type="assembly", created_at=i + 1)
    with TestClient(app) as client:
        # Newer builder jobs must not hide old pipe jobs behind a global cap.
        assert [j["id"] for j in client.get("/api/jobs").json()] == [oldest]
        builder_jobs = client.get("/api/assembly/jobs").json()
        assert len(builder_jobs) == 55
        target = builder_jobs[0]["id"]
        app.state.jobs.update(oldest, status="queued")
        assert client.delete(f"/api/jobs/{oldest}").status_code == 409
        app.state.jobs.update(oldest, status="cancelled")
        assert client.delete(f"/api/jobs/{oldest}").status_code == 204
        assert client.delete(f"/api/jobs/{target}").status_code == 204
        assert client.get("/api/jobs").json() == []
        assert len(client.get("/api/assembly/jobs").json()) == 54
        for suffix in ("", "/results.json", "/case.zip", "/fields.json"):
            assert client.get(f"/api/jobs/{oldest}{suffix}").status_code == 404
        assert client.get(f"/api/assembly/jobs/{target}/geometry").status_code == 404
        assert client.delete(f"/api/jobs/{oldest}").status_code == 404
        assert client.delete("/api/jobs/not-a-uuid").status_code == 422


def test_failed_file_removal_keeps_history(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPE_CFD_RUNS", str(tmp_path))
    target = saved_run(tmp_path)
    def denied(_):
        raise PermissionError("read-only fixture")
    with TestClient(app) as client:
        monkeypatch.setattr("backend.app.runner.shutil.rmtree", denied)
        response = client.delete(f"/api/jobs/{target}")
        assert response.status_code == 500
        assert "permissions" in response.json()["detail"]
        assert client.get(f"/api/jobs/{target}").status_code == 200
        assert (tmp_path / target / "job.json").exists()
