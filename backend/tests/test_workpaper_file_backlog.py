"""存量底稿文件梳理（spec procedure-chain-hardening-and-java-contracts R14）。

SQLite 真 ORM，工作目录与底稿存储都在临时目录：分类（自己的文件 / 无路径 / 旧占位 / 指向模板 / 文件缺失 / 越界）、
按项目与内嵌子底稿计数；处理只动可处理的三类（已有懒加载文件只回写路径，否则落文件），条件更新期间被改过的不覆盖
并删掉刚落的文件；默认不写（脚本 --apply 须带 --confirm）。
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType  # noqa: E402
from app.services import wp_template_init_service  # noqa: E402
from app.services import workpaper_file_backlog as backlog  # noqa: E402
from app.services.workpaper_sync.canonical_paths import TEMPLATE_ROOT  # noqa: E402
from tests._sqlite_fk import enable_sqlite_foreign_keys, with_fk_parents  # noqa: E402

pytestmark = pytest.mark.asyncio

_TABLES = with_fk_parents([User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__])
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fix" / "report_workpaper_file_backlog.py"


def _a_template() -> Path:
    return next(p for p in sorted((TEMPLATE_ROOT / "E").glob("*.xlsx")))


@pytest.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage = tmp_path / "wp_storage"
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", storage)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    enable_sqlite_foreign_keys(engine)  # 与 PG 一样检查外键（R20）
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        pid = uuid.uuid4()
        db.add(Project(id=pid, name="【测试】存量文件", client_name="【测试】存量文件", status=ProjectStatus.execution))
        await db.flush()
        papers: dict[str, WorkingPaper] = {}

        async def _paper(code: str, file_path: str) -> WorkingPaper:
            idx = WpIndex(project_id=pid, wp_code=code, wp_name=f"底稿{code}", audit_cycle=code[0])
            db.add(idx)
            await db.flush()
            wp = WorkingPaper(project_id=pid, wp_index_id=idx.id, file_path=file_path,
                              source_type=WpSourceType.template, file_version=1)
            db.add(wp)
            await db.flush()
            papers[code] = wp
            return wp

        own = await _paper("E1", "")
        own_file = storage / str(pid) / f"{own.id}.xlsx"
        own_file.parent.mkdir(parents=True, exist_ok=True)
        own_file.write_bytes(b"PK-own")
        own.file_path = str(own_file)
        await _paper("E2", "")
        await _paper("A1-11", f"storage/projects/{pid}/workpapers/A1-11.xlsx")
        await _paper("H1", str(_a_template()))
        await _paper("G1", str(tmp_path / "lost" / "G1.xlsx"))
        lazy = await _paper("D2", "")  # 打开时懒加载落过文件、file_path 没回写
        (storage / str(pid) / f"{lazy.id}.xlsx").write_bytes(b"PK-lazy")
        await db.commit()
        yield {"db": db, "pid": pid, "papers": papers, "storage": storage}
    await engine.dispose()


async def test_scan_classifies_every_shape_and_counts_by_project(world):
    rows = await backlog.scan_backlog(world["db"], world["pid"])
    got = {r.wp_code: r.category for r in rows}
    assert got == {"E1": "own_file", "E2": "empty", "A1-11": "placeholder", "H1": "template", "G1": "missing",
                   "D2": "empty"}
    report = backlog.summarize(rows, skip_codes=frozenset({"A1-11"}))
    assert report["totals"] == {"own_file": 1, "empty": 2, "placeholder": 1, "template": 1, "missing": 1, "rejected": 0}
    assert report["fixable"] == 4 and report["fixable_rebind_only"] == 1, "D2 已有懒加载落的文件：只回写路径"
    assert report["skip_sub_workpapers"] == {"placeholder": 1}
    assert report["by_project"][str(world["pid"])]["empty"] == 2
    assert all(len(v) <= 5 for v in report["samples"].values()) and "own_file" not in report["samples"]


async def test_classify_rejects_paths_outside_allowed_roots(world):
    import shutil
    import tempfile

    outside_dir = Path(tempfile.mkdtemp(prefix="ptgd_backlog_"))  # 不在工作目录 / 后端 / 仓库根之内
    try:
        outside = outside_dir / "x.xlsx"
        outside.write_bytes(b"PK")
        assert backlog.classify(str(outside))[0] == "rejected"
    finally:
        shutil.rmtree(outside_dir, ignore_errors=True)
    assert backlog.classify("   ")[0] == "empty"
    assert backlog.classify(f"storage\\projects\\{uuid.uuid4()}\\workpapers\\D\\D2-2.xlsx")[0] == "placeholder"
    assert backlog.classify(f"storage/projects/{uuid.uuid4().hex}/workpapers/D2.xlsx")[0] == "placeholder"


async def test_apply_fixes_only_fixable_rows_and_never_overwrites_concurrent_changes(world, monkeypatch):
    db, pid, papers = world["db"], world["pid"], world["papers"]
    monkeypatch.setattr(wp_template_init_service, "init_workpaper_from_template", lambda **kw: None)
    rows = await backlog.scan_backlog(db, pid)
    # 扫描之后、处理之前 E2 被别处写了路径：不得覆盖
    await db.execute(sa.update(WorkingPaper).where(WorkingPaper.id == papers["E2"].id).values(file_path="别处写的"))

    async def _scenario(_pid):
        return "normal", False

    done = await backlog.apply_backlog(db, rows, scenario_of=_scenario)
    assert done == {"rebound": 1, "blank": 1, "materialized": 1, "changed_meanwhile": 1}
    paths = dict((await db.execute(sa.select(WpIndex.wp_code, WorkingPaper.file_path)
                                   .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id))).all())
    storage = world["storage"] / str(pid)
    assert paths["D2"] == str(storage / f"{papers['D2'].id}.xlsx"), "已有懒加载文件 ⇒ 只回写路径"
    assert paths["H1"] == str(storage / f"{papers['H1'].id}.xlsx") and Path(paths["H1"]).read_bytes() == \
        _a_template().read_bytes(), "指向模板 ⇒ 复制所指模板到本底稿存储"
    assert Path(paths["A1-11"]).is_file(), "旧占位 ⇒ 落文件（找不到模板建空白册）"
    assert paths["E2"] == "别处写的" and not any(storage.glob(f"{papers['E2'].id}.*")), "期间被改：不覆盖、删掉刚落的文件"
    assert paths["G1"].endswith("G1.xlsx") and paths["E1"].endswith(f"{papers['E1'].id}.xlsx"), "缺失 / 自有文件不动"


async def test_script_refuses_apply_without_confirm_or_project(tmp_path):
    import os

    # 🔴 子进程一律指向临时的空库：变异掉参数校验时脚本会真的去扫库、写库（2026-10-26 真库事故：
    #    变异 D6 让本用例的子进程按默认配置连上真库跑了一遍 --apply，改了 3364 份底稿的 file_path，已按备份恢复）
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",  # 子进程管道默认 gbk，中文报错按 utf-8 读会乱码
           "DATABASE_URL": f"sqlite+aiosqlite:///{(tmp_path / 'nothing.db').as_posix()}"}
    for argv, message in ((["--apply"], "--apply 须同时带 --confirm"),
                          (["--apply", "--confirm"], "--apply 须指定 --project-id")):
        proc = subprocess.run([sys.executable, str(_SCRIPT), *argv], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env, timeout=120)
        assert proc.returncode == 2 and message in proc.stderr, proc.stderr
