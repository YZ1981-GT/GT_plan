"""公式 E2E CI 种子 — formula-e2e-ci-gate ADR-FEC-02。

职责：在一次性库上确定性创建五个账号（角色都是 admin）、两个【E2E】项目（国企单体 + 国企合并），
每个项目两份底稿（D2-1、A1，各配一个只有一页的最小工作簿）。

不建试算表 / 余额表、报表配置、附注、附件：用例按「没有四表数据」写判据（一键刷新被前置校验挡下、
门禁记「未执行」），需要附件的用例显式跳过并写明原因（spec formula-management-repair-closure R7）。

幂等：第二次运行 0 变更、清单字节相同。

安全：拒绝连接库名为 audit_platform 的共享库（除非 ``--allow-shared``）。

用法::

    python backend/scripts/e2e/seed_formula_e2e.py
    python backend/scripts/e2e/seed_formula_e2e.py --allow-shared   # CI 不传此参数

清单写入 ``backend/data/e2e_formula_manifest.json``（无时间戳）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]  # backend/
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 强制 UTF-8 输出
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import sqlalchemy as sa
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.base import UserRole
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.extension_models import AccountingStandard  # noqa: F401 — 注册 FK metadata
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus

# ─── 常量 ────────────────────────────────────────────────────────────────────

MANIFEST_PATH = ROOT / "data" / "e2e_formula_manifest.json"
STORAGE_ROOT = ROOT / "storage" / "e2e" / "formula-hub"

ROLES_SPEC: list[dict] = [
    {"username": "fhe2e_partner", "password": "partner123", "role": UserRole.admin, "email": "fhe2e_partner@gt.com"},
    {"username": "fhe2e_manager", "password": "manager123", "role": UserRole.admin, "email": "fhe2e_manager@gt.com"},
    {"username": "fhe2e_auditor", "password": "auditor123", "role": UserRole.admin, "email": "fhe2e_auditor@gt.com"},
    {"username": "fhe2e_qc", "password": "qc123", "role": UserRole.admin, "email": "fhe2e_qc@gt.com"},
    {"username": "fhe2e_eqcr", "password": "eqcr123", "role": UserRole.admin, "email": "fhe2e_eqcr@gt.com"},
]

STANDALONE_NAME = "【E2E】公式链路单体_2025"
CONSOL_NAME = "【E2E】公式链路合并_2025"
YEAR = 2025

WP_CODES = {
    "D2-1": "应收账款审定表",
    "A1": "财务报表审计总览",
}


# ─── 工具 ────────────────────────────────────────────────────────────────────

def _database_url() -> str:
    url = str(settings.DATABASE_URL)
    return url.replace("postgresql://", "postgresql+asyncpg://", 1) if url.startswith("postgresql://") else url


def _check_shared_db(allow: bool) -> None:
    """拒绝连接共享库 audit_platform（ADR-FEC-02）。"""
    url = _database_url()
    if "audit_platform" in url and not allow:
        print("❌ 拒绝连接共享库 audit_platform。使用 --allow-shared 解除限制。", file=sys.stderr)
        sys.exit(2)


def _ensure_workbook(path: Path, code: str) -> None:
    if path.is_file() and path.stat().st_size > 0:
        try:
            book = load_workbook(path, read_only=True, data_only=False)
            book.close()
            return
        except Exception:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = code
    sheet["A1"] = f"E2E formula hub — {code}"
    sheet["A2"] = code
    book.save(path)
    book.close()


# ─── 种子逻辑 ────────────────────────────────────────────────────────────────

async def _ensure_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    role: UserRole,
    email: str,
    stats: dict[str, list[str]],
) -> User:
    user = (await db.execute(sa.select(User).where(User.username == username))).scalars().first()
    if user is None:
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role=role,
            is_active=True,
            is_deleted=False,
        )
        db.add(user)
        await db.flush()
        stats["created"].append(f"user:{username}")
    else:
        changed: list[str] = []
        if not verify_password(password, user.hashed_password):
            user.hashed_password = hash_password(password)
            changed.append("password")
        if user.role != role:
            user.role = role
            changed.append("role")
        if not user.is_active or user.is_deleted:
            user.is_active = True
            user.is_deleted = False
            changed.append("active")
        target = stats["updated"] if changed else stats["skipped"]
        suffix = f"({','.join(changed)})" if changed else ""
        target.append(f"user:{username}{suffix}")
    return user


async def _ensure_project(
    db: AsyncSession,
    *,
    name: str,
    scope: str,
    admin: User,
    stats: dict[str, list[str]],
) -> Project:
    rows = list((await db.execute(sa.select(Project).where(
        Project.client_name == name,
        Project.audit_year == YEAR,
        Project.is_deleted == sa.false(),
    ))).scalars().all())
    if len(rows) > 1:
        raise RuntimeError(f"E2E 项目重复：{name} 共 {len(rows)} 条")
    if rows:
        project = rows[0]
        stats["skipped"].append(f"project:{name}")
    else:
        project = Project(
            name=name,
            client_name=name,
            audit_period_start=date(YEAR, 1, 1),
            audit_period_end=date(YEAR, 12, 31),
            audit_year=YEAR,
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
            manager_id=admin.id,
            partner_id=admin.id,
            business_category="A1",
            scenario="normal",
            template_type="soe",
            report_scope=scope,
            applicable_standard_v2={"entity_type": "soe", "scope": scope, "stage": "normal"},
            is_deleted=False,
        )
        db.add(project)
        await db.flush()
        stats["created"].append(f"project:{name}")
    # 确保关键字段正确
    project.manager_id = admin.id
    project.partner_id = admin.id
    project.report_scope = scope
    project.template_type = "soe"
    project.is_deleted = False
    return project


async def _ensure_papers(
    db: AsyncSession,
    *,
    project: Project,
    admin: User,
    stats: dict[str, list[str]],
) -> dict[str, str]:
    ids: dict[str, str] = {}
    storage = STORAGE_ROOT / str(project.id)

    for code, label in WP_CODES.items():
        index = (await db.execute(sa.select(WpIndex).where(
            WpIndex.project_id == project.id,
            WpIndex.wp_code == code,
        ))).scalars().first()
        if index is None:
            index = WpIndex(
                project_id=project.id,
                wp_code=code,
                wp_name=label,
                audit_cycle=code[0],
                assigned_to=admin.id,
                reviewer=admin.id,
                status=WpStatus.not_started,
                is_deleted=False,
            )
            db.add(index)
            await db.flush()
            stats["created"].append(f"wp_index:{code}@{project.client_name}")
        else:
            index.is_deleted = False
            stats["skipped"].append(f"wp_index:{code}@{project.client_name}")

        path = storage / f"{code}.xlsx"
        _ensure_workbook(path, code)

        paper = (await db.execute(sa.select(WorkingPaper).where(
            WorkingPaper.project_id == project.id,
            WorkingPaper.wp_index_id == index.id,
        ))).scalars().first()
        if paper is None:
            paper = WorkingPaper(
                project_id=project.id,
                wp_index_id=index.id,
                file_path=str(path),
                source_type=WpSourceType.template,
                file_version=1,
                assigned_to=admin.id,
                reviewer=admin.id,
                created_by=admin.id,
                updated_by=admin.id,
                parsed_data={"html_data": {code: {"cells": {}}}},
                is_deleted=False,
            )
            db.add(paper)
            await db.flush()
            stats["created"].append(f"working_paper:{code}@{project.client_name}")
        else:
            paper.file_path = str(path)
            paper.is_deleted = False
            stats["skipped"].append(f"working_paper:{code}@{project.client_name}")
        ids[code] = str(paper.id)

    await db.flush()
    return ids


async def seed(*, allow_shared: bool = False) -> dict:
    _check_shared_db(allow_shared)
    engine = create_async_engine(_database_url())
    Session = async_sessionmaker(engine, expire_on_commit=False)
    stats: dict[str, list[str]] = {"created": [], "updated": [], "skipped": []}
    try:
        async with Session() as db:
            # 五个角色账号
            users: dict[str, User] = {}
            for spec in ROLES_SPEC:
                u = await _ensure_user(db, stats=stats, **spec)
                users[spec["username"]] = u
            admin = users["fhe2e_partner"]

            # 两个项目
            standalone = await _ensure_project(db, name=STANDALONE_NAME, scope="standalone", admin=admin, stats=stats)
            consol = await _ensure_project(db, name=CONSOL_NAME, scope="consolidated", admin=admin, stats=stats)

            # 底稿（两个项目各建一套）
            standalone_wp = await _ensure_papers(db, project=standalone, admin=admin, stats=stats)
            consol_wp = await _ensure_papers(db, project=consol, admin=admin, stats=stats)

            await db.commit()

        # ── 构建清单（无时间戳） ──
        manifest = {
            "accounts": {s["username"]: s["password"] for s in ROLES_SPEC},
            "standalone": {
                "project_id": str(standalone.id),
                "project_name": STANDALONE_NAME,
                "wp_ids": standalone_wp,
            },
            "consolidated": {
                "project_id": str(consol.id),
                "project_name": CONSOL_NAME,
                "wp_ids": consol_wp,
            },
            "year": YEAR,
            "stats": stats,
        }
        return manifest
    finally:
        await engine.dispose()


def _write_manifest(manifest: dict) -> None:
    # stats 不进持久清单（每次运行不同），单独剥出
    persistent = {k: v for k, v in manifest.items() if k != "stats"}
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(persistent, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="公式 E2E CI 种子（formula-e2e-ci-gate）")
    parser.add_argument("--allow-shared", action="store_true", help="允许连接共享库 audit_platform")
    args = parser.parse_args()

    result = asyncio.run(seed(allow_shared=args.allow_shared))

    _write_manifest(result)
    stats = result.get("stats", {})
    print(f"✅ seed 完成: created={len(stats.get('created', []))}, "
          f"updated={len(stats.get('updated', []))}, "
          f"skipped={len(stats.get('skipped', []))}")
    print(f"   清单写入 {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
