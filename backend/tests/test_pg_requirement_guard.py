"""测试盲区收口（spec procedure-chain-hardening-and-java-contracts R20）。

1. PG 判定认 ``postgres://``（原先只认含 ``postgresql`` 的地址：别的写法下 pg_only 用例整批静默跳过）；
2. ``GT_REQUIRE_PG=1`` 而地址不是 PG、又收集到了 pg_only 用例 ⇒ 整次运行以 UsageError 失败（不再显示 skipped、退出码 0）；
3. 本 spec 涉及外键的 SQLite 用例开外键检查（SQLite 默认不查：R3 模板复制先插子表的错在 SQLite 上测不出）。

子进程只做 ``--collect-only``，并指向临时空库（不连真库、不跑任何用例）。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests._pg_url import is_pg_url, pg_requirement_error

BACKEND = Path(__file__).resolve().parents[1]
PG_ONLY_TARGET = "tests/test_workpaper_lifecycle_events_pg.py"


@pytest.mark.parametrize(("url", "expected"), [
    ("postgresql+asyncpg://u:p@h:5432/db", True),
    ("postgresql://u@h/db", True),
    ("postgres://u@h/db", True),
    ("POSTGRES+psycopg://u@h/db", True),
    ("sqlite+aiosqlite:///:memory:", False),
    ("sqlite", False),
    ("", False),
    (None, False),
    ("mysql://u@h/db", False),
])
def test_is_pg_url(url, expected):
    assert is_pg_url(url) is expected


def test_pg_requirement_error_only_when_required_and_not_pg_and_pg_tests_collected():
    ids = ["tests/a_pg.py::t1"]
    assert pg_requirement_error("sqlite", None, ids) is None, "没设 GT_REQUIRE_PG：照旧跳过"
    assert pg_requirement_error("sqlite", "0", ids) is None
    assert pg_requirement_error("postgres://u@h/db", "1", ids) is None, "postgres:// 是 PG"
    assert pg_requirement_error("sqlite", "1", []) is None, "没有 pg_only 用例：不拦"
    msg = pg_requirement_error("sqlite+aiosqlite:///x.db", "1", ids)
    assert msg and "GT_REQUIRE_PG=1" in msg and "tests/a_pg.py::t1" in msg and "sqlite+aiosqlite" in msg
    many = pg_requirement_error("sqlite", "true", [f"t{i}" for i in range(8)])
    assert many and "等 8 个" in many


def _collect(tmp_path: Path, **env_over: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    env.pop("FORCE_COLOR", None)
    env.pop("GT_REQUIRE_PG", None)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{(tmp_path / 'nothing.db').as_posix()}"
    env.update(env_over)
    return subprocess.run(
        [sys.executable, "-m", "pytest", PG_ONLY_TARGET, "--collect-only", "-q",
         "-p", "no:playwright", "-p", "no:cacheprovider"],
        cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )


def test_require_pg_fails_the_run_instead_of_skipping(tmp_path):
    proc = _collect(tmp_path, GT_REQUIRE_PG="1")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 4, out[-2000:]  # pytest.UsageError
    assert "GT_REQUIRE_PG=1" in out and "test_workpaper_lifecycle_events_pg.py" in out


def test_without_require_pg_collection_still_succeeds(tmp_path):
    proc = _collect(tmp_path)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]
    assert re.search(r"\d+ tests? collected", proc.stdout), proc.stdout[-1000:]


# postgres:// 端到端不做子进程用例：应用自己的 create_async_engine 不认这个写法（导入 app.core.database 即报错，
# 同样不会静默跳过）；判定本身由上面 is_pg_url / pg_requirement_error 覆盖。


#: 本 spec 新建 / 改过的、会插带外键关系行的 SQLite 用例
SPEC_SQLITE_FK_TESTS = (
    "tests/test_template_copy_integrity.py",
    "tests/test_staff_removal_and_delegate_account.py",
    "tests/test_generation_receipt.py",
    "tests/test_generation_entries_retention.py",
    "tests/test_workpaper_file_backlog.py",
    "tests/test_workpaper_lifecycle_events.py",
)


@pytest.mark.parametrize("rel", SPEC_SQLITE_FK_TESTS)
def test_spec_sqlite_tests_enable_foreign_keys(rel):
    src = (BACKEND / rel).read_text(encoding="utf-8")
    assert "sqlite+aiosqlite" in src, f"{rel} 不再是 SQLite 用例，清单该更新"
    assert "enable_sqlite_foreign_keys(engine)" in src or "PRAGMA foreign_keys=ON" in src, (
        f"{rel} 没开 SQLite 外键检查（SQLite 默认不查外键，插入顺序 / 悬空引用在 PG 才 500）")
