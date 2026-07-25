from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "claude-plugin" / "bin" / "agent-supervisor"


def run_supervisor(
    *args: str,
    run_root: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ORCHESTRATOR_AGENT_RUN_ROOT"] = str(run_root)
    return subprocess.run(
        [str(SUPERVISOR), *args],
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def test_supervisor_tracks_real_process_to_completion(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("heartbeat-input\n", encoding="utf-8")
    started = run_supervisor(
        "start",
        "--name",
        "shell-agent",
        "--workdir",
        str(tmp_path),
        "--stdin-file",
        str(prompt),
        "--result-file",
        "result.txt",
        "--max-runtime",
        "5",
        "--",
        "/bin/sh",
        "-c",
        (
            "read value; printf 'started:%s\\n' \"$value\"; "
            "sleep 0.2; printf 'done\\n' > '{run_dir}/result.txt'"
        ),
        run_root=tmp_path / "runs",
    )
    run_dir = json.loads(started.stdout)["run_dir"]
    waited = run_supervisor(
        "wait",
        run_dir,
        "--window",
        "3",
        "--interval",
        "0.05",
        "--report-every",
        "0.05",
        "--idle-limit",
        "2",
        run_root=tmp_path / "runs",
    )

    assert '"state": "completed"' in waited.stdout
    assert "AGENT_RESULT_BEGIN" in waited.stdout
    assert "done" in waited.stdout


def test_supervisor_stops_a_real_silent_process(tmp_path: Path) -> None:
    started = run_supervisor(
        "start",
        "--name",
        "silent-agent",
        "--workdir",
        str(tmp_path),
        "--max-runtime",
        "5",
        "--",
        "/bin/sh",
        "-c",
        "sleep 5",
        run_root=tmp_path / "runs",
    )
    run_dir = json.loads(started.stdout)["run_dir"]
    time.sleep(0.1)
    waited = run_supervisor(
        "wait",
        run_dir,
        "--window",
        "2",
        "--interval",
        "0.05",
        "--report-every",
        "0.05",
        "--idle-limit",
        "0.2",
        run_root=tmp_path / "runs",
    )

    assert '"state": "stale"' in waited.stdout
    assert '"reason": "no-progress"' in waited.stdout


def test_supervisor_treats_real_process_cpu_as_progress(tmp_path: Path) -> None:
    started = run_supervisor(
        "start",
        "--name",
        "busy-agent",
        "--workdir",
        str(tmp_path),
        "--max-runtime",
        "5",
        "--",
        "/bin/sh",
        "-c",
        "while :; do :; done",
        run_root=tmp_path / "runs",
    )
    run_dir = json.loads(started.stdout)["run_dir"]
    waited = run_supervisor(
        "wait",
        run_dir,
        "--window",
        "0.5",
        "--interval",
        "0.1",
        "--report-every",
        "0.1",
        "--idle-limit",
        "0.2",
        run_root=tmp_path / "runs",
    )

    assert '"state": "running"' in waited.stdout
    assert '"wait_window_expired": true' in waited.stdout
    stopped = run_supervisor(
        "stop",
        run_dir,
        run_root=tmp_path / "runs",
    )
    assert '"state": "stopped"' in stopped.stdout
