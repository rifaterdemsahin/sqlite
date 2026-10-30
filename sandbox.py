#!/usr/bin/env python3
"""
SQLite 3.54.1 Interactive Sandbox & Demo Engine
Demonstrates:
1. Embedded in-process library execution (no server, port, password, or network)
2. Single-file persistence & instant file copy cloning
3. ACID transactions & rollback on simulated crash mid-write
4. Real SQL capabilities: Indexes, GROUP BY aggregations, ON CONFLICT upserts
5. Single-writer lock behavior & concurrency patterns
"""

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SANDBOX_DIR = os.environ.get("SANDBOX_DATA_DIR", os.path.join(BASE_DIR, "sandbox_data"))
DB_PATH = os.path.join(SANDBOX_DIR, "ai_workflow_sandbox.db")
BACKUP_PATH = os.path.join(SANDBOX_DIR, "ai_workflow_sandbox_copy.db")
REPORT_JSON_PATH = os.path.join(SANDBOX_DIR, "latest_benchmark.json")


def init_sandbox_db(db_path=DB_PATH, reset=False):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if reset and os.path.exists(db_path):
        os.remove(db_path)
        for suffix in ("-wal", "-shm", "-journal"):
            if os.path.exists(db_path + suffix):
                os.remove(db_path + suffix)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Enable WAL mode for high-concurrency local reads + ACID safety
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA foreign_keys=ON;")

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            run_id TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            model TEXT NOT NULL,
            task_type TEXT NOT NULL,
            tokens_used INTEGER NOT NULL,
            latency_ms REAL NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kv_cache (
            cache_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 1,
            last_accessed TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_agent_runs_task_type ON agent_runs(task_type);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_name ON agent_runs(agent_name);
        """
    )

    # Seed realistic initial rows if empty
    cur.execute("SELECT COUNT(*) AS cnt FROM agent_runs;")
    if cur.fetchone()["cnt"] == 0:
        now = datetime.now(timezone.utc).isoformat()
        seed_runs = [
            ("run-101", "planner-agent", "gemini-2.5-pro", "architecture-synthesis", 4250, 310.4, "SUCCESS", now),
            ("run-102", "retriever-agent", "gemini-2.5-flash", "vector-lookup", 1280, 42.1, "SUCCESS", now),
            ("run-103", "coder-agent", "gemini-2.5-pro", "sql-sandbox-gen", 6890, 512.8, "SUCCESS", now),
            ("run-104", "verifier-agent", "gemini-2.5-flash", "acid-crash-test", 1920, 68.5, "SUCCESS", now),
            ("run-105", "retriever-agent", "gemini-2.5-flash", "vector-lookup", 1540, 39.7, "SUCCESS", now),
            ("run-106", "planner-agent", "gemini-2.5-pro", "architecture-synthesis", 3910, 289.0, "SUCCESS", now),
        ]
        cur.executemany(
            """
            INSERT INTO agent_runs (run_id, agent_name, model, task_type, tokens_used, latency_ms, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            seed_runs,
        )

        seed_cache = [
            ("prompt:system:v1", '{"role":"architect","mode":"embedded_sqlite"}', 14, now),
            ("schema:agent_runs", '{"columns":8,"indexed":true,"wal_enabled":true}', 29, now),
            ("embedding:doc:sqlite_acid", '[0.021, -0.044, 0.198, 0.872]', 7, now),
        ]
        cur.executemany(
            """
            INSERT INTO kv_cache (cache_key, payload, hit_count, last_accessed)
            VALUES (?, ?, ?, ?)
            """,
            seed_cache,
        )
        conn.commit()

    return conn


def run_full_demonstration():
    """Executes every demonstration point from the specification and returns structured telemetry."""
    conn = init_sandbox_db(DB_PATH, reset=False)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    # 1. Runtime & Engine Metadata
    cur.execute("PRAGMA journal_mode;")
    journal_mode = cur.fetchone()[0]
    cur.execute("PRAGMA page_size;")
    page_size = cur.fetchone()[0]
    cur.execute("PRAGMA page_count;")
    page_count = cur.fetchone()[0]

    # 2. ON CONFLICT Upsert demonstration
    t0 = time.perf_counter()
    cur.execute(
        """
        INSERT INTO kv_cache (cache_key, payload, hit_count, last_accessed)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
            hit_count = kv_cache.hit_count + 1,
            last_accessed = excluded.last_accessed
        """,
        ("schema:agent_runs", '{"columns":8,"indexed":true,"wal_enabled":true}', now),
    )
    conn.commit()
    upsert_ms = round((time.perf_counter() - t0) * 1000, 3)

    # 3. Fast Reads with Index & GROUP BY Aggregation
    t1 = time.perf_counter()
    cur.execute(
        """
        SELECT
            agent_name,
            task_type,
            COUNT(*) AS total_runs,
            SUM(tokens_used) AS total_tokens,
            ROUND(AVG(latency_ms), 2) AS avg_latency_ms
        FROM agent_runs
        GROUP BY agent_name, task_type
        ORDER BY total_tokens DESC
        """
    )
    group_by_rows = [dict(r) for r in cur.fetchall()]
    group_by_ms = round((time.perf_counter() - t1) * 1000, 3)

    # Query plan check to prove index usage
    cur.execute("EXPLAIN QUERY PLAN SELECT * FROM agent_runs WHERE agent_name = 'retriever-agent';")
    explain_plan = [dict(r) for r in cur.fetchall()]

    # 4. ACID Crash Simulation (Mid-Write Exception -> Automatic Rollback)
    cur.execute("SELECT COUNT(*) AS cnt FROM agent_runs;")
    before_crash_count = cur.fetchone()["cnt"]
    crash_log = []
    try:
        crash_log.append("BEGIN TRANSACTION")
        cur.execute(
            """
            INSERT INTO agent_runs (run_id, agent_name, model, task_type, tokens_used, latency_ms, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("run-crash-999", "rogue-writer", "gemini-2.5-pro", "partial-write", 99999, 12.3, "IN_FLIGHT", now),
        )
        crash_log.append("INSERT 1 row (run-crash-999) into uncommitted page buffer")
        raise RuntimeError("Simulated power loss / process crash mid-transaction before COMMIT")
    except RuntimeError as exc:
        conn.rollback()
        crash_log.append(f"CAUGHT: {exc} -> AUTOMATIC ROLLBACK EXECUTED")

    cur.execute("SELECT COUNT(*) AS cnt FROM agent_runs;")
    after_crash_count = cur.fetchone()["cnt"]
    cur.execute("PRAGMA integrity_check;")
    integrity_status = cur.fetchone()[0]

    # 5. Ordinary Single-File Copy Demonstration
    conn.execute("PRAGMA wal_checkpoint(FULL);")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    copy_conn = sqlite3.connect(BACKUP_PATH)
    copy_cur = copy_conn.cursor()
    copy_cur.execute("SELECT COUNT(*) FROM agent_runs;")
    copied_rows = copy_cur.fetchone()[0]
    copy_conn.close()

    # 6. Current Tables Snapshot
    cur.execute("SELECT * FROM agent_runs ORDER BY run_id;")
    all_runs = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM kv_cache ORDER BY hit_count DESC;")
    all_cache = [dict(r) for r in cur.fetchall()]

    conn.close()

    db_size_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    copy_size_bytes = os.path.getsize(BACKUP_PATH) if os.path.exists(BACKUP_PATH) else 0

    cli_binary = shutil.which("sqlite3")
    cli_version = None
    if cli_binary:
        try:
            cli_version = subprocess.check_output([cli_binary, "--version"], text=True).strip()
        except Exception:
            cli_version = "installed"

    is_volume_mounted = os.path.abspath(SANDBOX_DIR).startswith("/data")

    report = {
        "timestamp": now,
        "engine": {
            "sqlite_version": sqlite3.sqlite_version,
            "sqlite3_cli_binary": cli_binary or "python-sqlite3-builtin",
            "sqlite3_cli_version": cli_version or sqlite3.sqlite_version,
            "python_module": "sqlite3 (standard library)",
            "server_process": None,
            "port": None,
            "network_socket": None,
            "journal_mode": journal_mode,
            "page_size_bytes": page_size,
            "page_count": page_count,
            "db_file": DB_PATH,
            "db_size_bytes": db_size_bytes,
            "persistent_volume_mounted": is_volume_mounted,
            "storage_directory": os.path.abspath(SANDBOX_DIR),
        },
        "file_copy_proof": {
            "source_file": os.path.relpath(DB_PATH, BASE_DIR),
            "copied_file": os.path.relpath(BACKUP_PATH, BASE_DIR),
            "source_bytes": db_size_bytes,
            "copied_bytes": copy_size_bytes,
            "verified_rows_in_copy": copied_rows,
        },
        "acid_proof": {
            "rows_before_crash": before_crash_count,
            "rows_after_rollback": after_crash_count,
            "integrity_check": integrity_status,
            "transaction_trace": crash_log,
        },
        "performance": {
            "upsert_latency_ms": upsert_ms,
            "group_by_latency_ms": group_by_ms,
            "explain_query_plan": explain_plan,
        },
        "group_by_summary": group_by_rows,
        "agent_runs": all_runs,
        "kv_cache": all_cache,
    }

    with open(REPORT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


def execute_custom_sql(sql_query: str):
    """Executes one or multiple user SQL statements in the sandbox DB safely and returns rows, timing, and state."""
    conn = init_sandbox_db(DB_PATH, reset=False)
    cur = conn.cursor()
    t0 = time.perf_counter()
    try:
        statements = [s.strip() for s in sql_query.split(";") if s.strip()]
        columns = []
        rows = []
        total_changes_before = conn.total_changes
        for stmt in statements:
            cur.execute(stmt)
            if cur.description is not None:
                columns = [col[0] for col in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        conn.commit()
        changes_delta = conn.total_changes - total_changes_before
        if not columns:
            columns = ["status", "affected_rows", "db_file"]
            rows = [{"status": "COMMITTED", "affected_rows": changes_delta, "db_file": DB_PATH}]
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
        conn.close()
        return {
            "ok": True,
            "elapsed_ms": elapsed_ms,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "affected_rows": changes_delta,
        }
    except Exception as exc:
        conn.rollback()
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
        conn.close()
        return {
            "ok": False,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }


class SandboxRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            report = run_full_demonstration()
            self._send_json(report)
            return
        if parsed.path == "/api/reset":
            init_sandbox_db(DB_PATH, reset=True)
            report = run_full_demonstration()
            self._send_json(report)
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            data = {}

        if parsed.path == "/api/query":
            sql = data.get("sql", "").strip()
            if not sql:
                self._send_json({"ok": False, "error": "SQL query cannot be empty."}, status=400)
                return
            result = execute_custom_sql(sql)
            status_report = run_full_demonstration()
            result["snapshot"] = status_report
            self._send_json(result)
            return

        if parsed.path == "/api/simulate-crash":
            report = run_full_demonstration()
            self._send_json({"ok": True, "acid_proof": report["acid_proof"], "snapshot": report})
            return

        if parsed.path == "/api/clone-file":
            report = run_full_demonstration()
            self._send_json({"ok": True, "file_copy_proof": report["file_copy_proof"], "snapshot": report})
            return

        if parsed.path == "/api/sqlite-cli":
            cmd = data.get("cmd", ".tables").strip()
            cli_bin = shutil.which("sqlite3")
            if not cli_bin:
                self._send_json({"ok": False, "error": "sqlite3 CLI binary not found on PATH"}, status=400)
                return
            try:
                out = subprocess.check_output(
                    [cli_bin, "-header", "-column", DB_PATH, cmd],
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=5,
                )
                self._send_json({"ok": True, "command": f"sqlite3 -header -column {DB_PATH} \"{cmd}\"", "output": out})
            except subprocess.CalledProcessError as exc:
                self._send_json({"ok": False, "error": exc.output})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)})
            return

        self._send_json({"ok": False, "error": "Unknown endpoint"}, status=404)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SQLite 3.54.1 Sandbox & Visual Architecture Server")
    parser.add_argument("--host", type=str, default=os.environ.get("HOST", "0.0.0.0"), help="Host interface to bind")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "30085")), help="Port to serve on")
    parser.add_argument("--cli-only", action="store_true", help="Run benchmark and exit without starting HTTP server")
    args = parser.parse_args()

    report = run_full_demonstration()
    print(f"[SQLite Sandbox] Engine initialized: SQLite v{report['engine']['sqlite_version']}")
    print(f"[SQLite Sandbox] Database file: {report['engine']['db_file']} ({report['engine']['db_size_bytes']} bytes)")
    print(f"[SQLite Sandbox] File clone verified: {report['file_copy_proof']['copied_file']} ({report['file_copy_proof']['verified_rows_in_copy']} rows)")
    print(f"[SQLite Sandbox] ACID rollback test: {report['acid_proof']['integrity_check']} (rows before={report['acid_proof']['rows_before_crash']}, after={report['acid_proof']['rows_after_rollback']})")

    if not args.cli_only:
        server = HTTPServer((args.host, args.port), SandboxRequestHandler)
        print(f"[SQLite Sandbox] Serving interactive architecture & live SQLite sandbox on http://{args.host}:{args.port}")
        server.serve_forever()
