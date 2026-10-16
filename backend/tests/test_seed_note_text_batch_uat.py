"""测试集团 seed（Task 54 / 55 真实写入验收用）的契约测试。

- 企业代码都是合法 USCC、互不相同；项目名都带「【测试】」前缀（不会和真实项目混淆）；
- 建项走向导同一服务：两个子项目按三码派生到母项目 ⇒ 集团根相同（集团内容模板兄弟可见的前提）；
- 只给子项目生成附注；重复运行不重复建项目、不重复生成附注。

附注生成引擎本身另有测试；这里替换成最小替身，只验 seed 的编排（调用对象 / 次数 / 幂等）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型
from app.models.base import Base
from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine
from app.services.uscc_validator import validate_uscc

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

_SEED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed" / "seed_note_text_batch_uat.py"
_SPEC = importlib.util.spec_from_file_location("test_seed_note_text_batch_uat_script", _SEED_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_seed = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _seed
_SPEC.loader.exec_module(_seed)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


def test_codes_are_valid_uscc_and_names_marked_as_test() -> None:
    codes = [s.company_code for s in _seed.SPECS]
    assert [validate_uscc(c) for c in codes] == [(True, None)] * 3
    assert len(set(codes)) == 3
    assert all(s.client_name.startswith("【测试】") for s in _seed.SPECS)
    assert {s.key: (s.parent_key, s.report_scope, s.generate_notes) for s in _seed.SPECS} == {
        "root": (None, "consolidated", False),
        "a": ("root", "standalone", True),
        "b": ("root", "standalone", True),
    }


@pytest.mark.asyncio
async def test_children_share_group_root_and_rerun_is_idempotent(db, monkeypatch) -> None:
    calls: list[tuple] = []

    async def fake_generate(self, project_id, year, template_type="soe"):
        # 生成链本身已不调大模型（2026-10-16），脚本不再打桩：引擎上不存在大模型那一级
        assert not hasattr(DisclosureEngine, "_generate_text_with_llm")
        calls.append((project_id, year, template_type))
        self.db.add(DisclosureNote(project_id=project_id, year=year, note_section="一、1", section_title="公司基本情况"))
        await self.db.flush()
        return [{"note_section": "一、1"}]

    monkeypatch.setattr(DisclosureEngine, "generate_notes", fake_generate)
    first = await _seed.seed(db, year=2025)
    ids = first["ids"]
    assert len(first["created"]) == 3 and first["reused"] == []
    assert first["group_roots"] == {"root": ids["root"], "a": ids["root"], "b": ids["root"]}
    assert sorted(calls) == sorted([(ids["a"], 2025, "soe"), (ids["b"], 2025, "soe")])  # 母项目不生成
    for key in ("a", "b"):
        project = await db.get(Project, ids[key])
        assert (project.parent_project_id, project.template_type, project.audit_year) == (ids["root"], "soe", 2025)

    second = await _seed.seed(db, year=2025)
    assert second["ids"] == ids and second["created"] == [] and len(second["reused"]) == 3
    assert len(calls) == 2, "已有附注的项目不得重复生成"
    assert set(second["notes"].values()) == {"已有 1 章，跳过"}
    assert await db.scalar(select(func.count()).select_from(Project)) == 3


def test_dry_run_does_not_touch_database(monkeypatch, capsys) -> None:
    def boom(*_a, **_k):
        raise AssertionError("dry-run 不得连库")

    monkeypatch.setattr(_seed, "_run", boom)
    assert _seed.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "[DRY RUN]" in out and all(s.company_code in out for s in _seed.SPECS)


def test_standalone_run_registers_every_model_first() -> None:
    """独立运行（不经 conftest）只导入用到的几个模型时，建项 flush 解析不了 projects 的外键表
    （真库首跑实测 NoReferencedTableError: accounting_standards）。在全新解释器里验证注册后外键可解析。"""
    import subprocess

    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('seed', r'{_SEED_PATH}')\n"
        "mod = importlib.util.module_from_spec(spec); sys.modules['seed'] = mod; spec.loader.exec_module(mod)\n"
        "from app.models.core import Project\n"
        "mod._register_models()\n"
        "print([fk.column.table.name for c in Project.__table__.c for fk in c.foreign_keys])\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "accounting_standards" in proc.stdout
