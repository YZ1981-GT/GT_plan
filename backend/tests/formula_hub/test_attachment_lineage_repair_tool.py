"""修复工具 ``backend/scripts/fix/attachment_lineage_orphans.py``（spec formula-hub-integrity-closure 任务 3；需求 7.1；ADR-FHIC-13）。

判据：
1. 只读（默认）：逐行列出孤儿（附件不存在，含已回填过 project_id 的）与未回填（附件存在、project_id 为空），
   正常行不列；没有写语句、没有加锁语句、不写备份，行原样。
2. ``--apply``：先把待处理行原文写入备份文件（每条写语句执行时备份文件都已落盘），再回填可归属的行、删孤儿；
   正常行不动；第二次待处理 0 行、不再写备份。
3. 备份写不出去 ⇒ 抛错，没有任何写语句，行原样。
4. 列未就绪（R227 删列后）⇒ 只读与 ``--apply`` 都拒绝（``ColumnNotReady``），不写备份。
5. 命令行端到端（快照库真提交，``committed_project``）：只读输出恰为本用例的两行 → ``--apply`` 提交后备份 2 行、
   未回填行已回填、孤儿已删 → 再跑只读 0 行。

1~4 在 ``pg_tx``（外层事务，结束回滚）里直调工具的函数；前提：快照库 ``attachment_lineage`` 没有待处理行
（与共享库同为 0 行），因此列出的每一行都是本用例写入的。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import event, text

from app.models.attachment_models import Attachment
from app.services.attachment_lineage_schema import clear_lineage_schema_cache
from tests.formula_hub._lineage_fixtures import R227, insert_lineage, lineage_state, make_attachment, make_project, replay
from tests.formula_hub._pg_harness import database_name, database_url

pytestmark = pytest.mark.pg_only

BACKEND = Path(__file__).resolve().parents[2]
TOOL_PATH = BACKEND / "scripts" / "fix" / "attachment_lineage_orphans.py"
REF = "FH-T3-FIX!B5"
_WRITE_SQL = re.compile(r"^\s*(?:INSERT|UPDATE|DELETE|MERGE)\b", re.IGNORECASE)
_LOCK_SQL = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+)?(?:UPDATE|SHARE)\b", re.IGNORECASE)


def _load_tool():
    spec = importlib.util.spec_from_file_location("attachment_lineage_orphans", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


@pytest.fixture(autouse=True)
def _fresh_schema_cache():
    clear_lineage_schema_cache()
    yield
    clear_lineage_schema_cache()


async def _seed(session) -> dict[str, uuid.UUID]:
    assert await tool.scan(session) == [], "前提不成立：快照库 attachment_lineage 已有待处理行"
    project_id = await make_project(session, "lineage_fix")
    attachment_id = await make_attachment(session, project_id)
    rows = {
        "project": project_id,
        "normal": await insert_lineage(session, attachment_id=attachment_id, target_ref=REF, project_id=project_id),
        "unfilled": await insert_lineage(session, attachment_id=attachment_id, target_ref=REF),
        "orphan_null": await insert_lineage(session, attachment_id=uuid.uuid4(), target_ref=REF),
        "orphan_filled": await insert_lineage(session, attachment_id=uuid.uuid4(), target_ref=REF,
                                              project_id=project_id),
    }
    return rows


def _lineage_ids(rows: dict[str, uuid.UUID]) -> list[uuid.UUID]:
    return [value for key, value in rows.items() if key != "project"]


@contextmanager
def _statements(session, on_statement=None) -> Iterator[list[str]]:
    seen: list[str] = []

    def hook(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        seen.append(statement)
        if on_statement is not None:
            on_statement(statement)

    connection = session.bind.sync_connection
    event.listen(connection, "before_cursor_execute", hook)
    try:
        yield seen
    finally:
        event.remove(connection, "before_cursor_execute", hook)


def _writes(statements: list[str]) -> list[str]:
    return [s for s in statements if _WRITE_SQL.match(s)]


def _backups(directory: Path) -> list[Path]:
    return sorted(directory.glob("attachment_lineage_orphans_*.json")) if directory.is_dir() else []


async def test_dry_run_lists_orphans_and_unfilled_and_writes_nothing(pg_tx, tmp_path):
    rows = await _seed(pg_tx)
    before = await lineage_state(pg_tx, _lineage_ids(rows))
    with _statements(pg_tx) as statements:
        report = await tool.dry_run(pg_tx, database="pg_tx")
    listed = {(row["lineage_id"], row["reason"]) for row in report["rows"]}
    assert listed == {(str(rows["unfilled"]), "未回填"), (str(rows["orphan_null"]), "孤儿"),
                      (str(rows["orphan_filled"]), "孤儿")}
    assert (report["pending"], report["orphans"], report["unfilled"]) == (3, 2, 1)
    assert _writes(statements) == [] and not [s for s in statements if _LOCK_SQL.search(s)], statements
    assert await lineage_state(pg_tx, _lineage_ids(rows)) == before
    assert _backups(tmp_path) == []


async def test_apply_backs_up_first_then_backfills_and_deletes_orphans(pg_tx, tmp_path):
    rows = await _seed(pg_tx)
    before = await lineage_state(pg_tx, _lineage_ids(rows))
    backup_dir = tmp_path / "backups"
    backup_seen_at_write: list[bool] = []

    def on_statement(statement: str) -> None:
        if _WRITE_SQL.match(statement):
            backup_seen_at_write.append(bool(_backups(backup_dir)))

    with _statements(pg_tx, on_statement) as statements:
        report = await tool.apply_repairs(pg_tx, backup_dir=backup_dir, database="pg_tx",
                                          now=datetime(2026, 10, 27, 1, 2, 3))
    assert [s for s in statements if _LOCK_SQL.search(s)], "待处理行没有加锁"
    assert backup_seen_at_write == [True, True], (backup_seen_at_write, statements)  # 回填、删孤儿各一条
    (backup,) = _backups(backup_dir)
    assert backup.name == "attachment_lineage_orphans_20261027_010203.json"
    assert report["backup"] == str(backup)
    saved = json.loads(backup.read_text(encoding="utf-8"))
    originals = {uuid.UUID(row["lineage_id"]): (row["reason"], row["original"]) for row in saved["rows"]}
    assert originals == {
        rows["unfilled"]: ("未回填", before[rows["unfilled"]]),
        rows["orphan_null"]: ("孤儿", before[rows["orphan_null"]]),
        rows["orphan_filled"]: ("孤儿", before[rows["orphan_filled"]]),
    }
    after = await lineage_state(pg_tx, _lineage_ids(rows))
    assert set(after) == {rows["normal"], rows["unfilled"]}
    assert after[rows["normal"]] == before[rows["normal"]]
    assert after[rows["unfilled"]]["project_id"] == str(rows["project"])
    assert (report["backfilled"], report["deleted"]) == (1, 2)

    # 可重复执行：第二次 0 行、不再写备份
    again = await tool.apply_repairs(pg_tx, backup_dir=backup_dir, database="pg_tx")
    assert (again["pending"], again["backup"], again["backfilled"], again["deleted"]) == (0, None, 0, 0)
    assert _backups(backup_dir) == [backup]


async def test_apply_writes_nothing_when_backup_fails(pg_tx, tmp_path):
    rows = await _seed(pg_tx)
    before = await lineage_state(pg_tx, _lineage_ids(rows))
    not_a_directory = tmp_path / "occupied"
    not_a_directory.write_text("x", encoding="utf-8")
    with _statements(pg_tx) as statements:
        with pytest.raises(OSError):
            await tool.apply_repairs(pg_tx, backup_dir=not_a_directory, database="pg_tx")
    assert _writes(statements) == [], statements
    assert await lineage_state(pg_tx, _lineage_ids(rows)) == before


async def test_refuses_when_column_missing(pg_tx, tmp_path):
    await replay(pg_tx, R227)
    clear_lineage_schema_cache()
    with pytest.raises(tool.ColumnNotReady, match="V227"):
        await tool.dry_run(pg_tx, database="pg_tx")
    with _statements(pg_tx) as statements:
        with pytest.raises(tool.ColumnNotReady, match="V227"):
            await tool.apply_repairs(pg_tx, backup_dir=tmp_path, database="pg_tx")
    assert _writes(statements) == [] and _backups(tmp_path) == []


def _run_cli(tmp_path: Path, name: str, *args: str) -> tuple[int, dict, str]:
    report_path = tmp_path / f"{name}.json"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, str(TOOL_PATH), *args, "--json", str(report_path)],
                          cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    assert report_path.exists(), (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])
    return proc.returncode, json.loads(report_path.read_text(encoding="utf-8")), proc.stdout


async def test_cli_dry_run_then_apply_commits_against_snapshot(committed_project, tmp_path):
    handle = committed_project
    attachment = Attachment(project_id=handle.project_id, file_name="fh_cli.pdf", file_path="/tmp/fh_cli.pdf",
                            file_type="pdf", file_size=1024)
    await handle.add(attachment)
    async with handle.session() as session:
        unfilled = await insert_lineage(session, attachment_id=attachment.id, target_ref=REF)
        orphan = await insert_lineage(session, attachment_id=uuid.uuid4(), target_ref=REF)
        await session.commit()
    handle.track("attachment_lineage", id=unfilled)
    handle.track("attachment_lineage", id=orphan)

    code, report, stdout = _run_cli(tmp_path, "dry")
    assert code == 0, stdout
    assert {(row["lineage_id"], row["reason"]) for row in report["rows"]} == {
        (str(unfilled), "未回填"), (str(orphan), "孤儿")}, "列出的行不只本用例写入的两行：不执行 --apply"
    # 命令行连的就是夹具真提交的那个库（快照库或 CI 点名的一次性库；committed_project 已拒绝共享库）
    # 报告里的库名形如「<库名>（<主机>:<端口>）」
    assert report["database"].split("（", 1)[0] == database_name(database_url()) and "模式 只读" in stdout
    assert f"lineage_id={orphan} attachment_id=" in stdout and "原因=孤儿" in stdout and "原因=未回填" in stdout

    code, report, stdout = _run_cli(tmp_path, "apply", "--apply", "--backup-dir", str(tmp_path / "backups"))
    assert code == 0, stdout
    backup = Path(report["backup"])
    assert backup.parent == tmp_path / "backups"
    assert {row["lineage_id"] for row in json.loads(backup.read_text(encoding="utf-8"))["rows"]} == {
        str(unfilled), str(orphan)}
    async with handle.session() as session:
        state = await lineage_state(session, [unfilled, orphan])
    assert set(state) == {unfilled} and state[unfilled]["project_id"] == str(handle.project_id)

    code, report, _stdout = _run_cli(tmp_path, "dry_again")
    assert (code, report["pending"]) == (0, 0)
