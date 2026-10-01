"""An uncapped assembly command must stay cancellable; finite cutoffs still work."""
import os
import subprocess
import sys
import threading
from uuid import uuid4

import pytest

from backend.app.runner import Cancelled, JobManager


@pytest.fixture
def command_run(tmp_path):
    manager = JobManager(tmp_path)
    job_id = str(uuid4())
    folder = tmp_path / job_id
    folder.mkdir()
    event = threading.Event()
    manager.cancel_events[job_id] = event
    try:
        yield manager, job_id, folder, event
    finally:
        manager.close()


@pytest.mark.parametrize("timeout", [None, 3600])
def test_optional_elapsed_time_limit(command_run, monkeypatch, timeout):
    manager, job_id, folder, _ = command_run
    clock = iter([0, 7200])
    monkeypatch.setattr("backend.app.runner.time.monotonic", lambda: next(clock, 7200))
    args = [sys.executable, "-c", "import time; time.sleep(.1); print('finished')"]
    if timeout is None:
        manager._command(job_id, "runtime", args, os.environ.copy(), timeout=None)
        assert "finished" in (folder / "log.runtime").read_text()
    else:
        with pytest.raises(RuntimeError, match="3600s time limit"):
            manager._command(job_id, "runtime", args, os.environ.copy(), timeout=timeout)


def test_running_command_without_deadline_can_be_cancelled(command_run, monkeypatch):
    manager, job_id, _, event = command_run
    popen = subprocess.Popen
    processes = []

    def start_then_cancel(*args, **kwargs):
        child = popen(*args, **kwargs)
        processes.append(child)
        event.set()
        return child

    monkeypatch.setattr("backend.app.runner.subprocess.Popen", start_then_cancel)
    with pytest.raises(Cancelled):
        manager._command(job_id, "cancel", [sys.executable, "-c", "import time; time.sleep(30)"],
                         os.environ.copy(), timeout=None)
    assert len(processes) == 1
    assert processes[0].poll() is not None
