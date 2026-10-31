"""存量归属行升级工具 ``backend/scripts/fix/republish_report_seed_rows.py``（spec formula-hub-integrity-closure 任务 19；
需求 6.6；ADR-FHIC-23；决策项 X2）。

判据：
1. 目标按行名解析（非 PG）：工具在种子利润表里按需求 6.1 的行名解析出的 8 行目标 = 种子 8 行的 formula（单体两条无公式）。
2. 只读（默认）：列出 8 行旧值 = ``KNOWN_BAD``、目标 = 种子 formula、动作「待升级」；没有写语句、没有加锁语句（含咨询锁）。
3. ``--apply``：8 / 8 = 目标、版本 +1；发布记录按准则各一条（source seed、target global、request_id
   ``seed-upgrade-is-attribution-<准则>``、change_set 旧值 = 已知坏式、新值 = 目标）；``financial_report`` 只变
   ``is_stale``：跟随全局的项目（未删、未归档、准则 = 发布准则）里闭包（变化行 ∪ 经 ROW / SUM_ROW 直接或间接引用它们的行，
   本文件另写）各年度的行 false → true，其余列（金额、计算版本、计算失败原因、生成公式等）与其余行一字不变 ⇒ 没有重算。
4. 第二次 ``--apply``：全部「已是目标」、不发布、0 写语句；行被改回已知坏式后再 ``--apply`` ⇒ 同 request_id 幂等重放、
   0 写语句、不新增发布记录，工具报 ``UpgradeReplayed``（命令行退出码 1）。
5. 旧值既不是已知坏式也不是目标（含已知坏式带末尾空格）⇒ 该行跳过并报告、版本不变，其余照常发布。
6. 行名找不到 / 不唯一 ⇒ 退出码 2、0 写语句、0 加锁。
7. 命令行：参数缺失或非法 ⇒ 退出码 2 + 中文原因（库地址指向不可达端口，连库即退出码 1 —— 对照用例证明 2 在连库之前）；
   快照库只读运行 ⇒ 退出码 0、报告 8 行待升级。

2~6 在 ``pg_tx``（外层事务，结束回滚）里直调工具函数；命令行只读运行不写库，``--apply`` 不在命令行真提交（会改快照库全局定义）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import event, text

from app.services.report_config_service import ReportConfigService
from scripts.fix.republish_report_seed_rows import (
    ACTION_ALREADY,
    ACTION_MISMATCH,
    ACTION_PENDING,
    ATTRIBUTION,
    KNOWN_BAD,
    STANDARDS,
    UpgradeReplayed,
    apply_upgrade,
    dry_run,
    request_id_for,
    resolve_targets,
    run_session,
)
from tests.formula_hub._report_definition_rows import require_snapshot, seed_blocks

BACKEND = Path(__file__).resolve().parents[2]
TOOL_PATH = BACKEND / "scripts" / "fix" / "republish_report_seed_rows.py"
IS = "income_statement"
PURPOSE = "归属行升级工具用例"
_WRITE_SQL = re.compile(r"^\s*(?:INSERT|UPDATE|DELETE|MERGE)\b", re.IGNORECASE)
_LOCK_SQL = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+)?(?:UPDATE|SHARE)\b|pg_advisory", re.IGNORECASE)
ROW_REF = re.compile(r"(?<![A-Za-z0-9_])ROW\([ \t]*'([^']+)'[ \t]*\)")
SUM_ROW_REF = re.compile(r"(?<![A-Za-z0-9_])SUM_ROW\([ \t]*'([^']+)'[ \t]*,[ \t]*'([^']+)'[ \t]*\)")
#: 一定连不上的库（端口 9 无服务）：参数校验若排在连库之后，退出码会是 1 而不是 2
UNREACHABLE_DB = "postgresql+asyncpg://fh_t19:fh_t19@127.0.0.1:9/fh_t19_unreachable"


def _seed_formulas() -> dict[tuple[str, str], str | None]:
    return {(b["applicable_standard"], r["row_code"]): r.get("formula") for b in seed_blocks()
            if b["report_type"] == IS for r in b["rows"] if (b["applicable_standard"], r["row_code"]) in KNOWN_BAD}


# ─── 目标按行名解析（非 PG）──────────────────────────────────────────────────────


def test_targets_resolved_by_name_equal_seed_formulas():
    rows = [(b["applicable_standard"], r["row_code"], r.get("row_name") or "") for b in seed_blocks()
            if b["report_type"] == IS and b["applicable_standard"] in STANDARDS for r in b["rows"]]
    targets = resolve_targets(rows)
    assert {(std, total[0]) for std, totals in ATTRIBUTION.items() for total in totals} == set(KNOWN_BAD)
    assert {key: t.formula for key, t in targets.items()} == _seed_formulas()
    assert sum(t.formula is None for t in targets.values()) == 2, "单体 IS-075 / IS-052 应无公式"


# ─── 命令行参数（非 PG：子进程，库地址不可达）────────────────────────────────────


def _run_cli(*args: str, env: dict[str, str]) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(TOOL_PATH), *args], cwd=BACKEND, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8", **env})
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


@pytest.mark.parametrize(("case", "code", "reason"), [
    ("unknown_option", 2, "无法识别的参数：--bogus"),
    ("missing_value", 2, "参数 --json 缺少取值"),
    ("missing_dir", 2, "参数 --json 的目录不存在"),
    ("json_is_dir", 2, "参数 --json 应为文件路径"),
    ("not_postgresql", 2, "只支持 PostgreSQL：sqlite"),
    ("unreachable_control", 1, "连接数据库失败"),
])
def test_cli_argument_errors_exit_2_before_connecting(tmp_path, case, code, reason):
    args = {"unknown_option": ["--bogus"], "missing_value": ["--apply", "--json"],
            "missing_dir": ["--json", str(tmp_path / "no_such_dir" / "r.json")],
            "json_is_dir": ["--apply", "--json", str(tmp_path)], "not_postgresql": [],
            "unreachable_control": []}[case]
    url = f"sqlite+aiosqlite:///{(tmp_path / 'fh_t19.db').as_posix()}" if case == "not_postgresql" else UNREACHABLE_DB
    got, output = _run_cli(*args, env={"DATABASE_URL": url})
    assert (got, reason in output) == (code, True), output[-2000:]
    if code == 2 and case != "not_postgresql":
        assert "未连接数据库、未做任何修改" in output and "连接数据库失败" not in output, output[-2000:]


# ─── 真 PG（pg_tx 内，结束回滚）──────────────────────────────────────────────────


@contextmanager
def _statements(session) -> Iterator[list[str]]:
    seen: list[str] = []

    def hook(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        seen.append(statement)

    connection = session.bind.sync_connection
    event.listen(connection, "before_cursor_execute", hook)
    try:
        yield seen
    finally:
        event.remove(connection, "before_cursor_execute", hook)


def _writes(statements: list[str]) -> list[str]:
    return [s for s in statements if _WRITE_SQL.match(s)]


def _locks(statements: list[str]) -> list[str]:
    return [s for s in statements if _LOCK_SQL.search(s)]


async def _attr_rows(db) -> dict[tuple[str, str], tuple[str | None, int]]:
    rows = (await db.execute(text(
        "SELECT applicable_standard, row_code, formula, formula_version FROM report_config "
        "WHERE is_deleted = false AND report_type = 'income_statement'"))).all()
    return {(r[0], r[1]): (r[2], r[3]) for r in rows if (r[0], r[1]) in KNOWN_BAD}


async def _set_formula(db, key: tuple[str, str], formula: str | None) -> None:
    await db.execute(text("UPDATE report_config SET formula = :f WHERE is_deleted = false AND report_type = "
                          "'income_statement' AND applicable_standard = :s AND row_code = :c"),
                     {"f": formula, "s": key[0], "c": key[1]})


async def _publishes(db) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT request_id, scope, source, target, status, domain, change_set::text AS change_set FROM formula_publish "
        "WHERE request_id LIKE 'seed-upgrade-is-attribution-%' ORDER BY request_id"))).mappings().all()
    return [{**r, "change_set": json.loads(r["change_set"])} for r in rows]


async def _publish_count(db) -> int:
    return int((await db.execute(text("SELECT count(*) FROM formula_publish"))).scalar_one())


async def _report_rows(db) -> dict[str, dict]:
    rows = (await db.execute(text("SELECT id::text, row_to_json(f)::text FROM financial_report f"))).all()
    return {r[0]: json.loads(r[1]) for r in rows}


def _closure(defs: list[tuple[str, str | None, str | None, str | None]], changed: set[str]) -> set[str]:
    """变化行 ∪ 经 ROW / SUM_ROW（行次区间，字符串比较）直接或间接引用它们的行（本文件独立实现）。"""
    refs = [(code, {ref for t in texts if t for ref in ROW_REF.findall(t)},
             [rng for t in texts if t for rng in SUM_ROW_REF.findall(t)]) for code, *texts in defs]
    closure = set(changed)
    grew = True
    while grew:
        grew = False
        for code, rows, ranges in refs:
            if code not in closure and (rows & closure or any(a <= x <= b for a, b in ranges for x in closure)):
                closure.add(code)
                grew = True
    return closure


async def _expected_stale(db, before: dict[str, dict], changed: dict[str, set[str]]) -> set[str]:
    """跟随全局的项目（未删、未归档、准则 ∈ 发布准则）里闭包行次的报表行中，此前未过期的行 id。"""
    assert (await db.execute(text("SELECT count(*) FROM report_config WHERE applicable_standard LIKE 'project:%'"))
            ).scalar_one() == 0, "前提不成立：有项目层报表定义（预期按全部跟随全局计算）"
    closures = {}
    for std, codes in changed.items():
        defs = (await db.execute(text(
            "SELECT row_code, formula, aje_formula, rje_formula FROM report_config WHERE applicable_standard = :s "
            "AND is_deleted = false"), {"s": std})).all()
        closures[std] = _closure([tuple(d) for d in defs], codes)
    projects = (await db.execute(text(
        "SELECT p.id FROM projects p WHERE p.is_deleted = false AND p.status::text <> 'archived' "
        "AND EXISTS (SELECT 1 FROM financial_report f WHERE f.project_id = p.id)"))).scalars().all()
    standard = {str(pid): await ReportConfigService.resolve_applicable_standard(db, pid) for pid in projects}
    return {rid for rid, row in before.items()
            if standard.get(row["project_id"]) in closures and row["row_code"] in closures[standard[row["project_id"]]]
            and not row["is_deleted"] and not row["is_stale"]}


@pytest.mark.pg_only
async def test_dry_run_lists_eight_pending_rows_and_writes_nothing(pg_tx):
    await require_snapshot(pg_tx, PURPOSE)
    before = await _attr_rows(pg_tx)
    with _statements(pg_tx) as statements:
        report = await dry_run(pg_tx, database="pg_tx")
    assert (_writes(statements), _locks(statements)) == ([], []), statements
    seed = _seed_formulas()
    assert {(r["standard"], r["row_code"]): (r["old"], r["target"], r["action"], r["version"]) for r in report["rows"]} \
        == {key: (KNOWN_BAD[key], seed[key], ACTION_PENDING, 1) for key in KNOWN_BAD}
    assert report["counts"] == {ACTION_PENDING: 8, ACTION_ALREADY: 0, ACTION_MISMATCH: 0}
    assert report["publish_records"] == dict.fromkeys(STANDARDS)
    assert await _attr_rows(pg_tx) == before


@pytest.mark.pg_only
async def test_apply_upgrades_publishes_per_standard_and_only_marks_stale(pg_tx, request):
    await require_snapshot(pg_tx, PURPOSE)
    reports_before = await _report_rows(pg_tx)
    published_before = await _publish_count(pg_tx)
    code, report = await run_session(pg_tx, apply=True, database="pg_tx")
    assert code == 0, report
    seed = _seed_formulas()
    assert await _attr_rows(pg_tx) == {key: (seed[key], 2) for key in KNOWN_BAD}
    records = await _publishes(pg_tx)
    assert await _publish_count(pg_tx) == published_before + 4
    assert [(r["request_id"], r["scope"], r["source"], r["target"], r["status"], r["domain"]) for r in records] == sorted(
        (request_id_for(std), std, "seed", "global", "published", "report") for std in STANDARDS)
    got_changes = {(r["scope"], c["slot_key"]): (c["old"]["formula"], c["new"]["formula"], c["old_version"],
                                                 c["new_version"]) for r in records for c in r["change_set"]}
    assert got_changes == {(std, f"{IS}:{code}"): (KNOWN_BAD[(std, code)], seed[(std, code)], 1, 2)
                           for std, code in KNOWN_BAD}

    expected = await _expected_stale(pg_tx, reports_before, {std: {code for s, code in KNOWN_BAD if s == std}
                                                             for std in STANDARDS})
    after = await _report_rows(pg_tx)
    diff = {rid: {k: (row[k], after[rid][k]) for k in row if row[k] != after[rid][k]} for rid, row in reports_before.items()}
    diff = {rid: d for rid, d in diff.items() if d}
    request.node.user_properties.extend([("stale_marked", str(len(diff))), ("publishes", str(report["publishes"]))])
    assert expected, "预期标过期的报表行为空：用例空转"
    assert set(after) == set(reports_before)
    assert diff == {rid: {"is_stale": (False, True)} for rid in expected}


@pytest.mark.pg_only
async def test_second_apply_changes_nothing_and_same_request_id_replays(pg_tx):
    await require_snapshot(pg_tx, PURPOSE)
    first = await apply_upgrade(pg_tx, database="pg_tx")
    assert first["counts"][ACTION_PENDING] == 8
    published = await _publish_count(pg_tx)
    with _statements(pg_tx) as statements:
        second = await apply_upgrade(pg_tx, database="pg_tx")
    assert (second["counts"], second["publishes"], _writes(statements)) == (
        {ACTION_PENDING: 0, ACTION_ALREADY: 8, ACTION_MISMATCH: 0}, [], [])
    assert await _publish_count(pg_tx) == published

    for key, bad in KNOWN_BAD.items():  # 发布之后被改回已知坏式：同 request_id 只会幂等重放
        await _set_formula(pg_tx, key, bad)
    with _statements(pg_tx) as statements:
        with pytest.raises(UpgradeReplayed, match=re.escape(request_id_for(STANDARDS[0]))):
            await apply_upgrade(pg_tx, database="pg_tx")
    assert _writes(statements) == [], statements
    assert await _publish_count(pg_tx) == published
    assert {key: formula for key, (formula, _v) in (await _attr_rows(pg_tx)).items()} == KNOWN_BAD
    code, report = await run_session(pg_tx, apply=True, database="pg_tx")
    assert (code, report["error"].startswith("UpgradeReplayed")) == (1, True), report


@pytest.mark.pg_only
async def test_mismatched_old_value_is_skipped_and_reported(pg_tx):
    await require_snapshot(pg_tx, PURPOSE)
    third = {("soe_standalone", "IS-074"): "ROW('IS-048')+ROW('IS-053')",
             ("listed_standalone", "IS-051"): KNOWN_BAD[("listed_standalone", "IS-051")] + " "}  # 已知坏式带末尾空格
    for key, formula in third.items():
        await _set_formula(pg_tx, key, formula)
    report = await apply_upgrade(pg_tx, database="pg_tx")
    actions = {(r["standard"], r["row_code"]): r["action"] for r in report["rows"]}
    assert {key: actions[key] for key in third} == dict.fromkeys(third, ACTION_MISMATCH)
    assert {(r["standard"], r["row_code"]): r["old"] for r in report["skipped"]} == third
    assert report["counts"] == {ACTION_PENDING: 6, ACTION_ALREADY: 0, ACTION_MISMATCH: 2}
    seed = _seed_formulas()
    assert await _attr_rows(pg_tx) == {key: (third[key], 1) if key in third else (seed[key], 2) for key in KNOWN_BAD}
    assert {p["standard"]: p["slots"] for p in report["publishes"]} == {
        std: [f"{IS}:{code}" for s, code in KNOWN_BAD if s == std and (s, code) not in third] for std in STANDARDS}


@pytest.mark.pg_only
@pytest.mark.parametrize("case", ["missing", "duplicate"])
async def test_unresolvable_row_names_exit_2_without_writing(pg_tx, case):
    await require_snapshot(pg_tx, PURPOSE)
    if case == "missing":
        std, code, name = "soe_consolidated", "IS-054", "归属于母公司所有者的其他综合收益的税后净额"
        reason = f"{std} 利润表找不到行名「{name}」"
        new_name = name + "（改名）"
    else:
        std, code, name = "soe_standalone", "IS-047", "1.归属于母公司所有者的净利润"
        reason = f"{std} 利润表行名「{name}」不唯一（IS-047、IS-048）"
        new_name = name
    renamed = await pg_tx.execute(text(
        "UPDATE report_config SET row_name = :n WHERE is_deleted = false AND report_type = 'income_statement' "
        "AND applicable_standard = :s AND row_code = :c"), {"n": new_name, "s": std, "c": code})
    assert renamed.rowcount == 1
    with _statements(pg_tx) as statements:
        got, report = await run_session(pg_tx, apply=True, database="pg_tx")
    assert (got, reason in report.get("error", "")) == (2, True), report
    assert (_writes(statements), _locks(statements)) == ([], []), statements


@pytest.mark.pg_only
async def test_cli_dry_run_on_snapshot_lists_eight_rows(pg_tx, tmp_path):
    await require_snapshot(pg_tx, PURPOSE)
    report_path = tmp_path / "dry.json"
    code, output = _run_cli("--json", str(report_path), env={})
    assert code == 0, output[-2000:]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["database"].startswith("fh_snap_") and report["exit_code"] == 0
    assert report["counts"] == {ACTION_PENDING: 8, ACTION_ALREADY: 0, ACTION_MISMATCH: 0}
    assert "模式 只读（只读事务，不写入）" in output
    assert all(f"{std} {code}「" in output for std, code in KNOWN_BAD), output[-3000:]
