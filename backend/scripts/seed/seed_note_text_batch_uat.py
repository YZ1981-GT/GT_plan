"""附注正文批量写入 / 集团内容模板的真实写入验收用测试集团（Task 54 / 55，幂等）。

造数据内容（项目名都带「【测试】」前缀，不碰任何真实项目）：
- 1 个合并母项目 + 2 个子项目（同一集团根 ⇒ 子项目保存的集团内容模板，兄弟项目可见）；
- 国企模板、单体 / 合并口径按项目，审计年度默认 2025；
- 两个子项目用平台「生成附注」同一引擎生成附注初稿（母项目不生成：集团模板在兄弟之间引用，母项目无附注不影响可见性）。

做法与平台一致，不手写派生值：
- 建项走 ``project_wizard_service.create_project``（向导同一校验链：企业代码 USCC、唯一性、集团三码规范化），
  建项后按三码重算本年度派生链接 ``parent_project_id``；
- 附注走 ``DisclosureEngine.generate_notes``。不走 ``/generate`` 端点的「须先有报表」前置条件：
  测试项目没有试算表 / 报表数据，生成的是模板正文初稿，正好用来做正文批量写入；
  初稿不调大模型（只用模板默认文字），测试数据可复现、几秒生成完。

幂等：按「企业代码 + 审计年度 + 口径」找已有项目，有则复用；已有附注的项目不重复生成。

用法::

    python backend/scripts/seed/seed_note_text_batch_uat.py            # 写库
    python backend/scripts/seed/seed_note_text_batch_uat.py --dry-run  # 只打印计划，不连库
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from unittest import mock
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sqlalchemy as sa  # noqa: E402

from app.services.uscc_validator import USCC_CHARSET  # noqa: E402

DEFAULT_YEAR = 2025


def uscc(base17: str) -> str:
    """补第 18 位校验码（与 ``uscc_validator`` 同算法：Wi = 3^(i-1) mod 31，余数 31 记 0）。"""
    total = sum(USCC_CHARSET.index(ch) * pow(3, i, 31) for i, ch in enumerate(base17))
    return base17 + USCC_CHARSET[(31 - total % 31) % 31]


@dataclass(frozen=True)
class ProjectSpec:
    key: str
    client_name: str
    short_name: str
    company_code: str
    report_scope: str
    parent_key: str | None = None
    generate_notes: bool = False


#: 稳定业务键（幂等去重锚点）——切勿改码，否则重复运行会造出第二套集团
SPECS: tuple[ProjectSpec, ...] = (
    ProjectSpec("root", "【测试】附注批量集团有限公司", "附注批量集团", uscc("9150000NTBUAT000P"), "consolidated"),
    ProjectSpec("a", "【测试】附注批量甲有限公司", "附注批量甲", uscc("9150000NTBUAT000A"), "standalone",
                parent_key="root", generate_notes=True),
    ProjectSpec("b", "【测试】附注批量乙有限公司", "附注批量乙", uscc("9150000NTBUAT000B"), "standalone",
                parent_key="root", generate_notes=True),
)


async def _no_llm_text(*_args: Any, **_kwargs: Any) -> None:
    """替代 ``DisclosureEngine._generate_text_with_llm``：返回 None ⇒ 引擎回落到模板默认文字。"""
    return None


async def _find(db, spec: ProjectSpec, year: int):
    from app.models.core import Project

    return (await db.execute(sa.select(Project).where(
        Project.company_code == spec.company_code, Project.audit_year == year,
        Project.report_scope == spec.report_scope, Project.is_deleted == sa.false(),
    ))).scalar_one_or_none()


async def seed(db, *, year: int = DEFAULT_YEAR) -> dict[str, Any]:
    """建（或复用）三个测试项目并给子项目生成附注；每个项目、每次生成各自提交。"""
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.models.report_models import DisclosureNote
    from app.services.disclosure_engine import DisclosureEngine
    from app.services.note_content_template_service import resolve_canonical_group_root
    from app.services.project_wizard_service import create_project

    by_key = {s.key: s for s in SPECS}
    stats: dict[str, Any] = {"created": [], "reused": [], "notes": {}, "ids": {}}
    for spec in SPECS:
        project = await _find(db, spec, year)
        if project is None:
            parent = by_key[spec.parent_key] if spec.parent_key else None
            project = await create_project(BasicInfoSchema(
                client_name=spec.client_name, short_name=spec.short_name, audit_year=year,
                project_type="annual", accounting_standard="enterprise", company_code=spec.company_code,
                template_type="soe", report_scope=spec.report_scope,
                parent_company_name=parent.client_name if parent else None,
                parent_company_code=parent.company_code if parent else None,
                relation_to_parent="subsidiary" if parent else None,
                ultimate_company_name=parent.client_name if parent else None,
                ultimate_company_code=parent.company_code if parent else None,
            ), db)
            stats["created"].append(spec.client_name)
        else:
            stats["reused"].append(spec.client_name)
        stats["ids"][spec.key] = project.id

    for spec in SPECS:
        if not spec.generate_notes:
            continue
        pid: UUID = stats["ids"][spec.key]
        existing = await db.scalar(sa.select(sa.func.count()).select_from(DisclosureNote).where(
            DisclosureNote.project_id == pid, DisclosureNote.year == year, DisclosureNote.is_deleted == sa.false()))
        if existing:
            stats["notes"][spec.key] = f"已有 {existing} 章，跳过"
            continue
        # 测试数据要可复现、几秒生成完：初稿只用模板默认文字，不逐章调大模型（真机首跑实测约 10~20 秒一章、
        # 两个项目 300 多章要近一小时；平台「生成附注」本身照常调用，这里只替换本脚本内的这一步）
        with mock.patch.object(DisclosureEngine, "_generate_text_with_llm", _no_llm_text):
            generated = await DisclosureEngine(db).generate_notes(pid, year, "soe")
        await db.commit()
        stats["notes"][spec.key] = f"生成 {len(generated)} 章"

    stats["group_roots"] = {key: await resolve_canonical_group_root(db, pid) for key, pid in stats["ids"].items()}
    await db.rollback()
    return stats


def print_plan(year: int) -> None:
    print(f"年度 {year}（国企模板）")
    for s in SPECS:
        parent = f"，上级 {s.parent_key}" if s.parent_key else ""
        notes = "，生成附注" if s.generate_notes else ""
        print(f"  [{s.key}] {s.client_name}  企业代码 {s.company_code}  {s.report_scope}{parent}{notes}")


def _register_models() -> None:
    """独立运行须先注册全部 ORM 模型（与 schema_drift_detector 同法）：建项 flush 要解析 projects 的外键表
    （如 accounting_standards），只导入用到的几个模型会 NoReferencedTableError。"""
    import importlib
    import pkgutil

    import app.models as models_pkg

    for info in pkgutil.walk_packages(models_pkg.__path__, prefix="app.models."):
        importlib.import_module(info.name)


async def _run(year: int) -> int:
    from app.core.database import async_session

    _register_models()
    async with async_session() as db:
        stats = await seed(db, year=year)
    ids = stats["ids"]
    print("新建:", stats["created"] or "无", "| 复用:", stats["reused"] or "无")
    print("附注:", stats["notes"])
    for key, pid in ids.items():
        root = stats["group_roots"][key]
        print(f"  {key} = {pid}  集团根 = {root}{'（同一集团）' if root == ids['root'] else ''}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="附注正文批量写入真实验收用测试集团（幂等）")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不连库")
    args = parser.parse_args(argv)
    print_plan(args.year)
    if args.dry_run:
        print("[DRY RUN] 未连库、未写入。")
        return 0
    return asyncio.run(_run(args.year))


if __name__ == "__main__":
    raise SystemExit(main())
