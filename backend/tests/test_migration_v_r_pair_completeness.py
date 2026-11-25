"""全仓 V/R 迁移配对守卫。

MigrationRunner 只有在 rollback_to 时才暴露缺失 R 文件；正常启动不会阻止 V 应用。
因此缺配对会长期沉淀，直到需要跨版本回滚才爆炸。这个守卫要求：
- 每个 ``V<number>__*.sql`` 都有同号 ``R<number>__*.sql``；
- 没有孤儿 R；
- 每个 R 至少有可执行 SQL，显式 no-op 必须写 ``SELECT 1``。
"""
from __future__ import annotations

import re
from pathlib import Path


MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_VERSION = re.compile(r"^([VR])(\d+)__.+\.sql$", re.IGNORECASE)


def _versions(prefix: str) -> dict[str, Path]:
    return {
        match.group(2): path
        for path in MIGRATIONS.glob(f"{prefix}*.sql")
        if (match := _VERSION.match(path.name)) and match.group(1).upper() == prefix
    }


def test_every_versioned_migration_has_a_rollback_pair() -> None:
    versions = _versions("V")
    rollbacks = _versions("R")
    assert set(versions) == set(rollbacks), {
        "missing_rollback": sorted(set(versions) - set(rollbacks)),
        "orphan_rollback": sorted(set(rollbacks) - set(versions)),
    }


def test_every_rollback_has_sql_or_explicit_noop_marker() -> None:
    empty: list[str] = []
    for path in _versions("R").values():
        text = path.read_text(encoding="utf-8-sig")
        executable = [line.strip() for line in text.splitlines()
                      if line.strip() and not line.strip().startswith("--")]
        if not executable or not any(
            token in text.upper() for token in (
                "SELECT 1", "DROP ", "ALTER ", "DELETE ", "UPDATE ",
                "INSERT ", "CREATE ", "DO $$", "BEGIN",
            )
        ):
            empty.append(path.name)
    assert empty == [], f"回滚文件没有可执行 SQL 或显式 no-op：{empty}"
