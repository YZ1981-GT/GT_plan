"""真 PG 测试基座自检（spec formula-hub-integrity-closure 任务 1，需求 17.4，ADR-FHIC-25 第 3 点）。

判据：
1. ``pg_tx`` 内的写入（含会话 commit）在用例结束回滚后，另开连接查不到；
2. ``committed_project`` 真提交的项目与登记行，夹具结束后按主键再查为 0 行；
3. 子进程把库名换成 ``audit_platform`` 时 ``committed_project`` 在建项目之前失败（守卫文案、函数体未执行）；
4. ``GT_REQUIRE_PG=1`` + SQLite URL 的子进程以 UsageError 退出（退出码非 0、没有 skip）。

夹具「结束后」的状态只能在夹具外观测：1~3 以子进程按 node id 运行 ``_harness_inner.py`` 的内层用例，
外层在子进程结束后另开连接查库。子进程环境 = pytest 启动时的环境（``tests.conftest.ENVIRON_AT_START``）+ 覆盖项。
判据 3 的子进程 URL 把端口也换成不可达的 1：守卫失效时夹具会以连接错误失败（文案不同 ⇒ 本条红），
且绝不会真连到共享库。
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from tests.formula_hub._pg_harness import (
    DISPOSABLE_DB_ENV,
    REQUIRE_PG_USAGE_TEXT,
    SNAPSHOT_GUARD_TEXT,
    TEST_PROJECT_PREFIX,
    database_url,
    make_engine,
)

pytestmark = pytest.mark.pg_only

BACKEND = Path(__file__).resolve().parents[2]
INNER = "tests/formula_hub/_harness_inner.py"
_COUNT_KEYS = ("tests", "failures", "errors", "skipped")


@dataclass
class InnerRun:
    returncode: int
    output: str
    out_file: Path
    totals: dict[str, int] | None  # junit 汇总；None = 没生成 junit

    def outcome(self) -> tuple:
        return (self.returncode, *((self.totals or {}).get(k) for k in _COUNT_KEYS))


def _junit_totals(path: Path) -> dict[str, int] | None:
    if not path.exists():
        return None
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return {key: sum(int(suite.get(key, 0)) for suite in suites) for key in _COUNT_KEYS}


def _run_inner(target: str, tmp_path: Path, **env_overrides: str) -> InnerRun:
    from tests.conftest import ENVIRON_AT_START

    junit = tmp_path / f"inner_{uuid.uuid4().hex[:8]}.xml"
    out_file = tmp_path / f"inner_{uuid.uuid4().hex[:8]}.json"
    env = dict(ENVIRON_AT_START)
    env.pop("PYTEST_ADDOPTS", None)
    env.update({"PYTHONIOENCODING": "utf-8", "FH_HARNESS_OUT": str(out_file), **env_overrides})
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "-p", "no:playwright", "-p", "no:cacheprovider",
         f"--junitxml={junit}"],
        cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
    )
    # 捕获输出解码失败时 run() 照样返回、只把 stdout 置 None —— 只看退出码会假绿
    assert proc.stdout is not None and proc.stderr is not None
    return InnerRun(proc.returncode, proc.stdout + proc.stderr, out_file, _junit_totals(junit))


async def _count(sql: str, **params) -> int:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql), params)).scalar_one()
    finally:
        await engine.dispose()


async def test_pg_tx_writes_are_rolled_back_and_invisible(tmp_path):
    name = f"{TEST_PROJECT_PREFIX}fh_harness_tx_{uuid.uuid4().hex[:10]}"
    run = _run_inner(f"{INNER}::test_inner_pg_tx_write", tmp_path, FH_HARNESS_MARKER=name)
    assert run.outcome() == (0, 1, 0, 0, 0), run.output[-4000:]
    observed = json.loads(run.out_file.read_text(encoding="utf-8"))
    # 用例期间：本会话 commit 后可见、另一连接不可见（外层事务未提交）
    assert observed == {"in_tx": 1, "other_connection_during_tx": 0}
    # 用例结束回滚后：另开连接仍查不到
    assert await _count("SELECT count(*) FROM projects WHERE name = :name", name=name) == 0


async def test_committed_project_rows_are_gone_after_fixture(tmp_path):
    run = _run_inner(f"{INNER}::test_inner_committed_project", tmp_path)
    assert run.outcome() == (0, 1, 0, 0, 0), run.output[-4000:]
    observed = json.loads(run.out_file.read_text(encoding="utf-8"))
    # 夹具期间真提交：另一连接看得到项目与登记行
    assert observed["visible_from_other_connection"] == {"projects": 1, "formula_sync_item": 1}
    assert observed["tracked_tables"] == ["formula_sync_item"]
    assert observed["project_name"].startswith(TEST_PROJECT_PREFIX)
    project_id, item_id = uuid.UUID(observed["project_id"]), uuid.UUID(observed["sync_item_id"])
    # 夹具结束后：按主键再查为 0 行
    assert await _count("SELECT count(*) FROM projects WHERE id = :pid", pid=project_id) == 0
    assert await _count("SELECT count(*) FROM formula_sync_item WHERE id = :iid", iid=item_id) == 0
    assert await _count("SELECT count(*) FROM formula_sync_item WHERE project_id = :pid", pid=project_id) == 0


@pytest.mark.parametrize("declared", ["", "audit_platform"], ids=["undeclared", "shared_declared"])
def test_committed_project_refuses_shared_database(tmp_path, declared):
    """共享库即使被 ``GT_PG_DISPOSABLE_DB`` 点名（CI 的一次性库声明）也在建项目之前失败。"""
    shared = make_url(database_url()).set(database="audit_platform", port=1)
    run = _run_inner(
        f"{INNER}::test_inner_committed_guard", tmp_path,
        DATABASE_URL=shared.render_as_string(hide_password=False), **{DISPOSABLE_DB_ENV: declared},
    )
    assert run.outcome() == (1, 1, 0, 1, 0), run.output[-4000:]  # 夹具建立阶段报错，非跳过
    assert SNAPSHOT_GUARD_TEXT in run.output and "当前库名 audit_platform" in run.output, run.output[-4000:]
    assert not run.out_file.exists(), "守卫失效：内层用例函数体执行了"


def test_require_pg_with_sqlite_url_is_usage_error(tmp_path):
    sqlite_url = f"sqlite+aiosqlite:///{(tmp_path / 'harness.db').as_posix()}"
    run = _run_inner(INNER, tmp_path, DATABASE_URL=sqlite_url, GT_REQUIRE_PG="1")
    assert run.returncode == int(pytest.ExitCode.USAGE_ERROR), run.output[-4000:]
    # 确认退出码来自「GT_REQUIRE_PG 但地址不是 PG」这一判定，而不是 conftest 导入失败之类的其他用法错误。
    #
    # 🔴 2026-10-29 整合：本 spec 合入分支后，`tests/conftest.py` 已有同义的根级守卫
    # （spec procedure-chain-hardening-and-java-contracts R20，`tests/_pg_url.pg_requirement_error`，
    # 还会点名被跳过的 pg_only 用例），它不是 trylast ⇒ **先于**本基座的钩子抛出，文案也不同。
    # 两个守卫同一语义（需求 17.4：整轮 UsageError、不出现 skip），所以这里断言**行为与语义**，
    # 不绑定其中某一个实现的文案；只要文案两要素齐全，就排除了「别的用法错误」。
    assert "GT_REQUIRE_PG" in run.output, run.output[-4000:]
    assert "不是 PostgreSQL" in run.output, run.output[-4000:]
    fired = "本 spec 基座钩子" if REQUIRE_PG_USAGE_TEXT in run.output else "根 conftest 守卫（R20）"
    assert fired in {"本 spec 基座钩子", "根 conftest 守卫（R20）"}
    assert run.totals is None or (run.totals["tests"], run.totals["skipped"]) == (0, 0), run.totals
    assert "skipped" not in run.output.lower(), run.output[-4000:]
    assert not run.out_file.exists()
