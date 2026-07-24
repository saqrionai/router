from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from orchestrator.domain import AgentResult, Artifact, BoardMessage, CheckResult, Scope


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    workflow TEXT NOT NULL,
                    task TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    tracking_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    current_round INTEGER NOT NULL DEFAULT 0,
                    decision TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    actor TEXT,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_outputs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    round_number INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    model TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    status TEXT NOT NULL,
                    raw TEXT NOT NULL,
                    parsed_json TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    round_number INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    thread TEXT NOT NULL,
                    author TEXT NOT NULL,
                    recipients_json TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    body TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    parent_id INTEGER REFERENCES messages(id),
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    round_number INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    thread TEXT NOT NULL,
                    author TEXT NOT NULL,
                    local_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_message_ids_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, round_number, stage, author, local_id)
                );

                CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    round_number INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    argv_json TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exit_code INTEGER,
                    stdout TEXT NOT NULL,
                    stderr TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS native_route_observations (
                    workflow_run_id TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    bead_id TEXT,
                    task TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    persona TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reward REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (workflow_run_id, unit_id)
                );

                CREATE INDEX IF NOT EXISTS idx_outputs_run_round
                    ON agent_outputs(run_id, round_number, stage);
                CREATE INDEX IF NOT EXISTS idx_events_run
                    ON events(run_id, id);
                CREATE INDEX IF NOT EXISTS idx_messages_run_thread
                    ON messages(run_id, thread, id);
                CREATE INDEX IF NOT EXISTS idx_artifacts_run_thread
                    ON artifacts(run_id, thread, id);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "tracking_json" not in columns:
                connection.execute(
                    "ALTER TABLE runs ADD COLUMN tracking_json TEXT NOT NULL DEFAULT '{}'"
                )

    def create_run(
        self,
        *,
        workflow: str,
        task: str,
        workspace: Path,
        scope: Scope,
        tracking: dict[str, Any] | None = None,
    ) -> str:
        run_id = uuid.uuid4().hex[:12]
        timestamp = _now()
        scope_json = json.dumps(
            {
                "authorization": scope.authorization,
                "targets": list(scope.targets),
                "allowed_actions": list(scope.allowed_actions),
                "execution": scope.execution,
            },
            sort_keys=True,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, workflow, task, workspace, scope_json, tracking_json, status,
                    current_round, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'created', 0, ?, ?)
                """,
                (
                    run_id,
                    workflow,
                    task,
                    str(workspace.resolve()),
                    scope_json,
                    json.dumps(tracking or {}, sort_keys=True),
                    timestamp,
                    timestamp,
                ),
            )
        self.event(run_id, "run.created", None, {"workflow": workflow})
        return run_id

    def run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown run: {run_id}")
        result = dict(row)
        result["scope"] = json.loads(result.pop("scope_json"))
        result["tracking"] = json.loads(result.pop("tracking_json"))
        return result

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        current_round: int | None = None,
        decision: str | None = None,
    ) -> None:
        fields = ["updated_at = ?"]
        values: list[Any] = [_now()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if current_round is not None:
            fields.append("current_round = ?")
            values.append(current_round)
        if decision is not None:
            fields.append("decision = ?")
            values.append(decision)
        values.append(run_id)
        with self.connect() as connection:
            cursor = connection.execute(
                f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", values
            )
            if cursor.rowcount == 0:
                raise ValueError(f"unknown run: {run_id}")

    def event(
        self,
        run_id: str,
        kind: str,
        actor: str | None,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO events (run_id, created_at, kind, actor, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, _now(), kind, actor, json.dumps(payload, sort_keys=True)),
            )

    def save_agent_result(
        self,
        run_id: str,
        round_number: int,
        stage: str,
        result: AgentResult,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_outputs (
                    run_id, round_number, stage, persona, model, backend,
                    status, raw, parsed_json, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, estimated_cost_usd,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    round_number,
                    stage,
                    result.persona,
                    result.model,
                    result.backend,
                    result.status,
                    result.raw,
                    json.dumps(result.parsed, sort_keys=True)
                    if result.parsed is not None
                    else None,
                    result.usage.input_tokens,
                    result.usage.output_tokens,
                    result.usage.cache_read_tokens,
                    result.usage.cache_write_tokens,
                    result.usage.estimated_cost_usd,
                    _now(),
                ),
            )

    def publish(
        self,
        run_id: str,
        round_number: int,
        stage: str,
        message: BoardMessage,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO messages (
                    run_id, round_number, stage, thread, author,
                    recipients_json, kind, body, metadata_json, parent_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    round_number,
                    stage,
                    message.thread,
                    message.author,
                    json.dumps(message.recipients),
                    message.kind,
                    message.body,
                    json.dumps(message.metadata, sort_keys=True),
                    message.parent_id,
                    _now(),
                ),
            )
            return int(cursor.lastrowid)

    def messages(
        self,
        run_id: str,
        *,
        threads: tuple[str, ...] | None = None,
        round_number: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["run_id = ?"]
        values: list[Any] = [run_id]
        if round_number is not None:
            clauses.append("round_number = ?")
            values.append(round_number)
        if threads:
            placeholders = ",".join("?" for _ in threads)
            clauses.append(f"thread IN ({placeholders})")
            values.extend(threads)
        query = "SELECT * FROM messages WHERE " + " AND ".join(clauses) + " ORDER BY id"
        with self.connect() as connection:
            rows = connection.execute(query, values).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["recipients"] = json.loads(item.pop("recipients_json"))
            item["metadata"] = json.loads(item.pop("metadata_json"))
            results.append(item)
        return results

    def save_artifact(
        self,
        run_id: str,
        round_number: int,
        stage: str,
        message_id: int,
        artifact: Artifact,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO artifacts (
                    run_id, round_number, stage, message_id, thread, author,
                    local_id, title, kind, media_type, content,
                    source_message_ids_json, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    round_number,
                    stage,
                    message_id,
                    artifact.thread,
                    artifact.author,
                    artifact.local_id,
                    artifact.title,
                    artifact.kind,
                    artifact.media_type,
                    artifact.content,
                    json.dumps(artifact.source_message_ids),
                    json.dumps(artifact.metadata, sort_keys=True),
                    _now(),
                ),
            )
            return int(cursor.lastrowid)

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["source_message_ids"] = json.loads(
                item.pop("source_message_ids_json")
            )
            item["metadata"] = json.loads(item.pop("metadata_json"))
            results.append(item)
        return results

    def usage_summary(self, run_id: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE run_id = ?" if run_id else ""
        values: tuple[Any, ...] = (run_id,) if run_id else ()
        query = f"""
            SELECT model, backend, persona,
                   COUNT(*) AS calls,
                   SUM(input_tokens) AS input_tokens,
                   SUM(output_tokens) AS output_tokens,
                   SUM(cache_read_tokens) AS cache_read_tokens,
                   SUM(cache_write_tokens) AS cache_write_tokens,
                   SUM(COALESCE(estimated_cost_usd, 0)) AS estimated_cost_usd
            FROM agent_outputs
            {where}
            GROUP BY model, backend, persona
            ORDER BY calls DESC, model, persona
        """
        with self.connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [dict(row) for row in rows]

    def routing_outcomes(self) -> list[dict[str, Any]]:
        """Return round-attributed rewards for locally observed live routes."""
        with self.connect() as connection:
            legacy_rows = connection.execute(
                """
                SELECT outputs.persona,
                       outputs.model,
                       COUNT(*) AS calls,
                       SUM(CASE WHEN outputs.status = 'completed' THEN 1 ELSE 0 END)
                           AS format_successes,
                       SUM(
                           CASE
                               WHEN json_extract(outcomes.payload_json, '$.decision')
                                    IN ('accept', 'revise', 'reject')
                               THEN 1
                               ELSE 0
                           END
                       )
                           AS terminal_calls,
                       SUM(
                           CASE
                               WHEN json_extract(outcomes.payload_json, '$.decision')
                                    = 'accept'
                               THEN 1
                               ELSE 0
                           END
                       )
                           AS accepted_calls
                FROM agent_outputs AS outputs
                JOIN runs ON runs.id = outputs.run_id
                LEFT JOIN events AS outcomes
                  ON outcomes.id = (
                      SELECT MAX(candidate.id)
                      FROM events AS candidate
                      WHERE candidate.run_id = outputs.run_id
                        AND candidate.kind = 'round.completed'
                        AND json_extract(candidate.payload_json, '$.round')
                            = outputs.round_number
                  )
                WHERE outputs.persona != 'conductor'
                  AND EXISTS (
                      SELECT 1
                      FROM events
                      WHERE events.run_id = runs.id
                        AND events.kind = 'round.started'
                        AND json_extract(events.payload_json, '$.mode') = 'live'
                  )
                GROUP BY outputs.persona, outputs.model
                ORDER BY outputs.persona, outputs.model
                """
            ).fetchall()
            native_rows = connection.execute(
                """
                SELECT persona,
                       model,
                       COUNT(*) AS calls,
                       SUM(CASE WHEN status != 'blocked' THEN 1 ELSE 0 END)
                           AS format_successes,
                       COUNT(*) AS terminal_calls,
                       SUM(
                           CASE
                               WHEN decision = 'accept' AND status = 'accepted'
                               THEN 1
                               ELSE 0
                           END
                       ) AS accepted_calls
                FROM native_route_observations
                GROUP BY persona, model
                ORDER BY persona, model
                """
            ).fetchall()
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for row in (*legacy_rows, *native_rows):
            item = dict(row)
            key = (str(item["persona"]), str(item["model"]))
            aggregate = merged.setdefault(
                key,
                {
                    "persona": key[0],
                    "model": key[1],
                    "calls": 0,
                    "format_successes": 0,
                    "terminal_calls": 0,
                    "accepted_calls": 0,
                },
            )
            for field in (
                "calls",
                "format_successes",
                "terminal_calls",
                "accepted_calls",
            ):
                aggregate[field] += int(item[field] or 0)
        return [merged[key] for key in sorted(merged)]

    def routing_observations(self) -> list[dict[str, Any]]:
        """Return task-level live outcomes used by the contextual routing head."""
        with self.connect() as connection:
            legacy_rows = connection.execute(
                """
                SELECT outputs.run_id,
                       outputs.round_number AS round,
                       runs.task,
                       outputs.persona,
                       outputs.model,
                       outputs.status,
                       json_extract(outcomes.payload_json, '$.decision') AS decision,
                       CASE
                           WHEN outputs.status != 'completed' THEN 0.0
                           WHEN json_extract(outcomes.payload_json, '$.decision')
                                = 'accept' THEN 1.0
                           WHEN json_extract(outcomes.payload_json, '$.decision')
                                = 'revise' THEN 0.5
                           WHEN json_extract(outcomes.payload_json, '$.decision')
                                = 'reject' THEN 0.0
                           ELSE NULL
                       END AS reward
                FROM agent_outputs AS outputs
                JOIN runs ON runs.id = outputs.run_id
                JOIN events AS outcomes
                  ON outcomes.id = (
                      SELECT MAX(candidate.id)
                      FROM events AS candidate
                      WHERE candidate.run_id = outputs.run_id
                        AND candidate.kind = 'round.completed'
                        AND json_extract(candidate.payload_json, '$.round')
                            = outputs.round_number
                  )
                WHERE outputs.persona != 'conductor'
                  AND json_extract(outcomes.payload_json, '$.decision')
                      IN ('accept', 'revise', 'reject')
                  AND EXISTS (
                      SELECT 1
                      FROM events
                      WHERE events.run_id = runs.id
                        AND events.kind = 'round.started'
                        AND json_extract(events.payload_json, '$.mode') = 'live'
                  )
                ORDER BY outputs.run_id, outputs.round_number, outputs.id
                """
            ).fetchall()
            native_rows = connection.execute(
                """
                SELECT workflow_run_id AS run_id,
                       round_number AS round,
                       task,
                       persona,
                       model,
                       status,
                       decision,
                       reward
                FROM native_route_observations
                ORDER BY workflow_run_id, round_number, unit_id
                """
            ).fetchall()
        return [dict(row) for row in (*legacy_rows, *native_rows)]

    def record_native_outcome(
        self,
        *,
        workflow_run_id: str,
        bead_id: str | None,
        task: str,
        decision: str,
        queue: list[dict[str, Any]],
    ) -> int:
        """Persist idempotent per-unit outcomes from one native workflow."""
        if not workflow_run_id.strip():
            raise ValueError("workflow_run_id must be non-empty")
        if not task.strip():
            raise ValueError("native outcome task must be non-empty")
        if decision not in {"accept", "revise", "reject", "inconclusive"}:
            raise ValueError(f"invalid native outcome decision: {decision}")
        rows: list[tuple[Any, ...]] = []
        for item in queue:
            unit_id = str(item.get("id") or "").strip()
            persona = str(item.get("persona") or "").strip()
            model = str(item.get("model") or "").strip()
            status = str(item.get("status") or "").strip()
            if not unit_id or not persona or not model:
                continue
            if status not in {"accepted", "verified", "returned", "blocked"}:
                continue
            reward = {
                "accepted": 1.0,
                "verified": 0.5,
                "returned": 0.5,
                "blocked": 0.0,
            }[status]
            rows.append(
                (
                    workflow_run_id,
                    unit_id,
                    bead_id,
                    task,
                    int(item.get("round") or 1),
                    persona,
                    model,
                    status,
                    decision,
                    reward,
                    _now(),
                )
            )
        with self.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO native_route_observations (
                    workflow_run_id, unit_id, bead_id, task, round_number,
                    persona, model, status, decision, reward, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return connection.total_changes - before

    def save_check_result(
        self,
        run_id: str,
        round_number: int,
        result: CheckResult,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO checks (
                    run_id, round_number, name, argv_json, cwd, status,
                    exit_code, stdout, stderr, duration_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    round_number,
                    result.name,
                    json.dumps(result.argv),
                    str(result.cwd),
                    result.status,
                    result.exit_code,
                    result.stdout,
                    result.stderr,
                    result.duration_seconds,
                    _now(),
                ),
            )

    def outputs(
        self,
        run_id: str,
        *,
        round_number: int | None = None,
        stages: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["run_id = ?"]
        values: list[Any] = [run_id]
        if round_number is not None:
            clauses.append("round_number = ?")
            values.append(round_number)
        if stages:
            placeholders = ",".join("?" for _ in stages)
            clauses.append(f"stage IN ({placeholders})")
            values.extend(stages)
        query = (
            "SELECT * FROM agent_outputs WHERE "
            + " AND ".join(clauses)
            + " ORDER BY id"
        )
        with self.connect() as connection:
            rows = connection.execute(query, values).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            parsed_json = item.pop("parsed_json")
            item["parsed"] = json.loads(parsed_json) if parsed_json else None
            results.append(item)
        return results

    def checks(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM checks WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["argv"] = json.loads(item.pop("argv_json"))
            results.append(item)
        return results

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            results.append(item)
        return results

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, workflow, task, workspace, status, current_round,
                       decision, created_at, updated_at,
                       COALESCE(
                           (
                               SELECT json_extract(events.payload_json, '$.mode')
                               FROM events
                               WHERE events.run_id = runs.id
                                 AND events.kind = 'round.started'
                               ORDER BY events.id
                               LIMIT 1
                           ),
                           'unknown'
                       ) AS mode
                FROM runs ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
