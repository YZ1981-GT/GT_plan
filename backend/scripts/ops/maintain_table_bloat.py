#!/usr/bin/env python
"""Safely compact ``checklist_responses``; dry-run unless explicitly confirmed.

The apply path creates a custom-format, table-scoped pg_dump first, records a
logical digest and catalog manifest, rejects long/prepared transactions, then
runs ``VACUUM (FULL, ANALYZE)`` with bounded lock/statement timeouts.  It never
kills sessions or drops indexes.  Production should normally use pg_repack.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TARGET = "checklist_responses"
QUALIFIED_TARGET = f"public.{TARGET}"
CONFIRMATION = "VACUUM_FULL_CHECKLIST_RESPONSES"
DEFAULT_BACKUP_ROOT = BACKEND_ROOT / "backups"
LEDGER_TABLES = ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")


async def _snapshot(conn: AsyncConnection) -> dict[str, Any]:
    logical = (await conn.execute(sa.text("""
        SELECT count(*)::bigint AS exact_rows,
               md5(COALESCE(string_agg(md5(to_jsonb(t)::text), '' ORDER BY t.id), '')) AS row_digest,
               COALESCE(sum(pg_column_size(t)), 0)::bigint AS logical_bytes
          FROM public.checklist_responses AS t
    """))).mappings().one()
    sizes = (await conn.execute(sa.text("""
        SELECT pg_relation_size(c.oid)::bigint AS heap_bytes,
               pg_indexes_size(c.oid)::bigint AS index_bytes,
               pg_total_relation_size(c.oid)::bigint AS total_bytes,
               CASE WHEN c.reltoastrelid=0 THEN 0
                    ELSE pg_total_relation_size(c.reltoastrelid) END::bigint AS toast_bytes,
               c.reltuples::bigint AS estimated_rows,
               s.n_live_tup::bigint, s.n_dead_tup::bigint,
               s.last_vacuum, s.last_autovacuum, s.last_analyze, s.last_autoanalyze
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
         WHERE n.nspname='public' AND c.relname='checklist_responses'
    """))).mappings().one()
    columns = (await conn.execute(sa.text("""
        SELECT ordinal_position, column_name, data_type, udt_schema, udt_name,
               is_nullable, column_default
          FROM information_schema.columns
         WHERE table_schema='public' AND table_name='checklist_responses'
         ORDER BY ordinal_position
    """))).mappings().all()
    constraints = (await conn.execute(sa.text("""
        SELECT conname, contype::text AS contype, convalidated, pg_get_constraintdef(oid, true) AS definition
          FROM pg_constraint WHERE conrelid='public.checklist_responses'::regclass
         ORDER BY conname
    """))).mappings().all()
    indexes = (await conn.execute(sa.text("""
        SELECT c.relname AS name, i.indisvalid, i.indisready, i.indisunique,
               pg_relation_size(c.oid)::bigint AS size_bytes, pg_get_indexdef(c.oid) AS definition
          FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
         WHERE i.indrelid='public.checklist_responses'::regclass ORDER BY c.relname
    """))).mappings().all()
    return {"captured_at": _utc_now(), "logical": dict(logical), "sizes": dict(sizes),
            "columns": [dict(r) for r in columns], "constraints": [dict(r) for r in constraints],
            "indexes": [dict(r) for r in indexes]}


async def _safety(conn: AsyncConnection, max_age_seconds: int) -> dict[str, Any]:
    long_transactions = (await conn.execute(sa.text("""
        SELECT pid, usename, application_name, state, wait_event_type, wait_event,
               round(extract(epoch FROM (clock_timestamp()-xact_start))::numeric, 1) AS age_seconds
          FROM pg_stat_activity
         WHERE datname=current_database() AND pid<>pg_backend_pid() AND xact_start IS NOT NULL
           AND clock_timestamp()-xact_start > make_interval(secs => :age)
         ORDER BY xact_start
    """), {"age": max_age_seconds})).mappings().all()
    target_locks = (await conn.execute(sa.text("""
        SELECT l.pid, a.usename, a.application_name, a.state, l.mode, l.granted,
               a.wait_event_type, a.wait_event
          FROM pg_locks l LEFT JOIN pg_stat_activity a ON a.pid=l.pid
         WHERE l.relation='public.checklist_responses'::regclass AND l.pid<>pg_backend_pid()
         ORDER BY l.granted, l.pid, l.mode
    """))).mappings().all()
    prepared = (await conn.execute(sa.text("""
        SELECT gid, owner, database, prepared FROM pg_prepared_xacts
         WHERE database=current_database() ORDER BY prepared
    """))).mappings().all()
    return {"captured_at": _utc_now(), "max_transaction_age_seconds": max_age_seconds,
            "long_transactions": [dict(r) for r in long_transactions],
            "target_locks": [dict(r) for r in target_locks],
            "prepared_transactions": [dict(r) for r in prepared],
            "safe": not long_transactions and not prepared}


async def _database_identity(conn: AsyncConnection) -> dict[str, str]:
    row = (await conn.execute(sa.text("""
        SELECT system_identifier::text, current_database()::text AS database_name,
               current_user::text AS database_user
          FROM pg_control_system()
    """))).mappings().one()
    return dict(row)


def _public_connection(url: URL) -> dict[str, Any]:
    return {"host": url.host or "localhost", "port": url.port or 5432,
            "user": url.username or "postgres", "database": (url.database or "audit_platform").lstrip("/"),
            "password": url.password or ""}


def _recovery_guidance(url: URL, dump_path: Path, docker_container: str) -> dict[str, Any]:
    """Return credential-free restore commands; restoration is intentionally never automatic."""
    info = _public_connection(url)
    return {
        "warning": "仅在逐值核对确认需要恢复后执行；先停止 checklist_responses 写入并另备当前状态。",
        "local": (f'pg_restore -h {info["host"]} -p {info["port"]} -U {info["user"]} '
                  f'-d {info["database"]} --clean --if-exists --single-transaction "{dump_path}"'),
        "docker": [
            f'docker cp "{dump_path}" {docker_container}:/tmp/checklist_responses.dump',
            (f'docker exec {docker_container} pg_restore -U {info["user"]} -d {info["database"]} '
             "--clean --if-exists --single-transaction /tmp/checklist_responses.dump"),
            f"docker exec {docker_container} rm /tmp/checklist_responses.dump",
        ],
    }


def _local_dump_command(url: URL) -> tuple[list[str], dict[str, str]]:
    info = _public_connection(url)
    command = ["pg_dump", "-h", info["host"], "-p", str(info["port"]), "-U", info["user"],
               "-d", info["database"], "-Fc", "-t", QUALIFIED_TARGET]
    env = dict(os.environ)
    if info["password"]:
        env["PGPASSWORD"] = info["password"]
    return command, env


def _docker_identity(container: str, info: dict[str, Any]) -> dict[str, str]:
    command = ["docker", "exec", container, "psql", "-X", "-A", "-t", "-U", info["user"],
               "-d", info["database"], "-c",
               "SELECT system_identifier::text||'|'||current_database()::text FROM pg_control_system()"]
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"无法验证 Docker PostgreSQL 身份：{proc.stderr.strip()[:300]}")
    parts = proc.stdout.strip().split("|")
    if len(parts) != 2:
        raise RuntimeError("Docker PostgreSQL 身份响应格式异常")
    return {"system_identifier": parts[0], "database_name": parts[1]}


def _dump_table(url: URL, output: Path, database_identity: dict[str, str], docker_container: str) -> dict[str, Any]:
    info = _public_connection(url)
    local = shutil.which("pg_dump")
    if local:
        command, env = _local_dump_command(url)
        command[0] = local
        mode = "local"
    else:
        if not shutil.which("docker"):
            raise RuntimeError("找不到 pg_dump，也找不到 Docker 兜底")
        docker_identity = _docker_identity(docker_container, info)
        if docker_identity["system_identifier"] != database_identity["system_identifier"] or \
                docker_identity["database_name"] != database_identity["database_name"]:
            raise RuntimeError("Docker 容器并非当前连接的 PostgreSQL，拒绝备份错误数据库")
        command = ["docker", "exec", docker_container, "pg_dump", "-U", info["user"], "-d", info["database"],
                   "-Fc", "-t", QUALIFIED_TARGET]
        env, mode = dict(os.environ), f"docker:{docker_container}"
    with output.open("wb") as stream:
        proc = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE, env=env, timeout=600)
    if proc.returncode != 0:
        output.unlink(missing_ok=True)
        err = proc.stderr.decode("utf-8", "replace") if isinstance(proc.stderr, bytes) else str(proc.stderr)
        raise RuntimeError(f"pg_dump 失败：{err.strip()[:500]}")
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("pg_dump 返回成功但备份文件为空")
    return {"mode": mode, "path": str(output), "size_bytes": output.stat().st_size,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "command": "pg_dump -Fc -t public.checklist_responses（凭据未记录）"}


def _verify_dump(path: Path, docker_container: str) -> dict[str, Any]:
    local = shutil.which("pg_restore")
    if local:
        command, stdin = [local, "--list", str(path)], None
    else:
        command, stdin = ["docker", "exec", "-i", docker_container, "pg_restore", "--list"], path.open("rb")
    try:
        proc = subprocess.run(command, stdin=stdin, capture_output=True, timeout=120)
    finally:
        if stdin is not None:
            stdin.close()
    output = proc.stdout.decode("utf-8", "replace")
    error = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise RuntimeError(f"pg_restore --list 无法读取备份：{error.strip()[:500]}")
    has_table = " TABLE public checklist_responses " in f" {output} "
    has_data = " TABLE DATA public checklist_responses " in f" {output} "
    if not has_table or not has_data:
        raise RuntimeError("备份目录缺 checklist_responses 的 TABLE 或 TABLE DATA")
    return {"pg_restore_list_ok": True, "has_table": has_table, "has_table_data": has_data,
            "catalog_lines": len(output.splitlines())}


def _structure(snapshot: dict[str, Any]) -> dict[str, Any]:
    indexes = [{k: row[k] for k in ("name", "indisvalid", "indisready", "indisunique", "definition")}
               for row in snapshot["indexes"]]
    return {"columns": snapshot["columns"], "constraints": snapshot["constraints"], "indexes": indexes}


def _same_logical(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for key in ("exact_rows", "row_digest", "logical_bytes"):
        if before["logical"][key] != after["logical"][key]:
            failures.append(f"logical.{key} changed")
    if _structure(before) != _structure(after):
        failures.append("schema/index/constraint contract changed")
    return not failures, failures


async def _vacuum(url: str, lock_timeout_ms: int, statement_timeout_seconds: int,
                  analyze_ledgers: bool) -> list[str]:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    analyzed: list[str] = []
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql(f"SET lock_timeout = '{lock_timeout_ms}ms'")
            await conn.exec_driver_sql(f"SET statement_timeout = '{statement_timeout_seconds}s'")
            await conn.exec_driver_sql(f"VACUUM (FULL, ANALYZE) {QUALIFIED_TARGET}")
            if analyze_ledgers:
                for table in LEDGER_TABLES:
                    await conn.exec_driver_sql(f"ANALYZE public.{table}")
                    analyzed.append(table)
    finally:
        await engine.dispose()
    return analyzed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", choices=[TARGET], default=TARGET)
    parser.add_argument("--apply", action="store_true", help="backup then execute VACUUM FULL; default dry-run")
    parser.add_argument("--confirm", default="", help=f"required with --apply: {CONFIRMATION}")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--docker-container", default=os.getenv("GT_POSTGRES_CONTAINER", "audit-postgres"),
                        help="pg_dump fallback when host client is unavailable")
    parser.add_argument("--max-transaction-age", type=int, default=60)
    parser.add_argument("--lock-timeout-ms", type=int, default=5000)
    parser.add_argument("--statement-timeout-seconds", type=int, default=1800)
    parser.add_argument("--analyze-ledgers", action="store_true")
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if args.apply and args.confirm != CONFIRMATION:
        raise SystemExit(f"--apply requires --confirm {CONFIRMATION}")
    for name in ("max_transaction_age", "lock_timeout_ms", "statement_timeout_seconds"):
        if getattr(args, name) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")


async def _read_state(url: str, max_age: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return await _snapshot(conn), await _safety(conn, max_age), await _database_identity(conn)
    finally:
        await engine.dispose()


def _print_summary(label: str, snapshot: dict[str, Any], safety: dict[str, Any] | None = None) -> None:
    logical, sizes = snapshot["logical"], snapshot["sizes"]
    print(f"[{label}] rows={logical['exact_rows']} digest={logical['row_digest']} "
          f"heap={sizes['heap_bytes']} indexes={sizes['index_bytes']} total={sizes['total_bytes']} bytes")
    if safety is not None:
        print(f"[safety] safe={safety['safe']} long={len(safety['long_transactions'])} "
              f"prepared={len(safety['prepared_transactions'])} target_locks={len(safety['target_locks'])}")


async def run(args: argparse.Namespace) -> int:
    from app.core.config import settings

    url_text = settings.DATABASE_URL
    before, safety, identity = await _read_state(url_text, args.max_transaction_age)
    _print_summary("before", before, safety)
    if not args.apply:
        print({"dry_run": True, "would_backup": QUALIFIED_TARGET, "would_vacuum_full": QUALIFIED_TARGET,
               "analyze_ledgers": bool(args.analyze_ledgers)})
        return 0
    if not safety["safe"]:
        print("拒绝执行：存在长事务或 prepared transaction；不会强杀会话，也尚未执行 VACUUM FULL。", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = args.backup_root.resolve() / f"checklist_responses_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    dump_path, manifest_path = backup_dir / "checklist_responses.dump", backup_dir / "manifest.json"
    parsed_url = make_url(url_text)
    manifest: dict[str, Any] = {"version": 1, "target": QUALIFIED_TARGET, "started_at": _utc_now(),
                                "database": identity,
                                "recovery": _recovery_guidance(parsed_url, dump_path, args.docker_container),
                                "before": before, "preflight": safety,
                                "status": "backing_up"}
    _write_manifest(manifest_path, manifest)
    try:
        dump = _dump_table(parsed_url, dump_path, identity, args.docker_container)
        dump["verification"] = _verify_dump(dump_path, args.docker_container)
        manifest.update({"backup": dump, "status": "backup_verified"})
        _write_manifest(manifest_path, manifest)

        pre_vacuum, final_safety, final_identity = await _read_state(url_text, args.max_transaction_age)
        stable, drift = _same_logical(before, pre_vacuum)
        if final_identity != identity or not stable or not final_safety["safe"]:
            manifest.update({"status": "aborted_before_vacuum", "pre_vacuum": pre_vacuum,
                             "final_preflight": final_safety,
                             "failures": (["database identity changed"] if final_identity != identity else []) + drift})
            _write_manifest(manifest_path, manifest)
            print("备份后状态发生变化或出现长事务，拒绝执行 VACUUM FULL；备份已保留。", file=sys.stderr)
            return 3

        analyzed = await _vacuum(url_text, args.lock_timeout_ms, args.statement_timeout_seconds,
                                 args.analyze_ledgers)
        after, after_safety, after_identity = await _read_state(url_text, args.max_transaction_age)
        valid, failures = _same_logical(before, after)
        if after_identity != identity:
            failures.append("database identity changed")
            valid = False
        manifest.update({"status": "verified" if valid else "verification_failed", "finished_at": _utc_now(),
                         "pre_vacuum": pre_vacuum, "final_preflight": final_safety, "after": after,
                         "after_safety": after_safety, "analyzed_ledgers": analyzed,
                         "verification": {"ok": valid, "failures": failures}})
        _write_manifest(manifest_path, manifest)
        _print_summary("after", after, after_safety)
        print(f"backup={dump_path}\nmanifest={manifest_path}\nverification={valid}")
        return 0 if valid else 4
    except Exception as exc:
        manifest.update({"status": "failed", "finished_at": _utc_now(),
                         "error": f"{type(exc).__name__}: {exc}"})
        _write_manifest(manifest_path, manifest)
        print(f"维护失败，备份目录与清单已保留：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 5


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _validate_args(args)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
