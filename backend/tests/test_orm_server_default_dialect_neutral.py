"""ORM server_default 不得含 PG 专有的 `::` 类型转换。

背景：`'[]'::jsonb` 这类写法会被 SQLAlchemy 原样写进 CREATE TABLE，SQLite 解析到 `:`
报 `unrecognized token: ":"`，于是全平台任何用 `Base.metadata.create_all(sqlite)` 的测试
在 setup 阶段报错。该写法已三次进入模型（workpaper_sync_models 两次、consolidation_models
一次，2026-10-27 那次让 117 例同时报错）。真实表由迁移 SQL 创建，PG 对 jsonb 列的
`DEFAULT '[]'` 会隐式转型，去掉 `::jsonb` 无行为变化。
"""

from __future__ import annotations

import importlib
import pkgutil

import sqlalchemy as sa

import app.models as models_pkg
from app.models.base import Base


def _load_all_models() -> None:
    for mod in pkgutil.walk_packages(models_pkg.__path__, models_pkg.__name__ + "."):
        importlib.import_module(mod.name)


def _server_default_text(col: sa.Column) -> str | None:
    sd = col.server_default
    if sd is None:
        return None
    arg = getattr(sd, "arg", None)
    if arg is None:
        return None
    return str(getattr(arg, "text", arg))


def _violations() -> list[str]:
    _load_all_models()
    found: list[str] = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            text_default = _server_default_text(col)
            if text_default and "::" in text_default:
                found.append(f"{table.name}.{col.name}: {text_default}")
    return sorted(found)


def test_no_pg_cast_in_server_default():
    bad = _violations()
    assert not bad, "ORM server_default 含 PG 专有 `::` 转换（SQLite 建表会失败）：\n  " + "\n  ".join(bad)


def test_scanner_sees_models():
    """防空转：扫描器必须看到足够多的表，且能读到 server_default 文本。"""
    _load_all_models()
    tables = Base.metadata.tables
    assert len(tables) > 100
    col = tables["consol_note_template_push_log"].columns["failures"]
    assert _server_default_text(col) == "'[]'"
