"""T型账户跨项目隔离守卫

🔴 缘起（第四轮复盘）：上一轮给 `list_t_accounts` 补了 `get_current_user` 就算"修完"，
理由是"对齐同文件另 7 个端点"。**那是错的** —— 那 7 个端点本身只有 `get_current_user`
（仅身份认证、不含项目维度），且 service 层 5 个方法**全不按 project_id 过滤**，
router 也不把路径上的 `project_id` 传下去 ⇒ `project_id` 纯属装饰。

后果：任何登录用户传任意 `t_account_id` 可读他人项目的 T 型账户，
`add_entry` 更可**往他人项目写分录**（篡改审计数据）。

本表不在 RLS 覆盖范围（`V005__enable_rls.sql` 只保护 4 张表；真实 PG 现查
217 张带 project_id 的表里仅 3 张受保护）⇒ 无 DB 层兜底。

**教训**：把"对齐既有基准"当正确性依据 = 把缺陷正当化。基准本身要先验证。

本文件锁死 service 层的归属过滤（真 ORM 两项目互访），端点层门禁由
`test_project_endpoint_authorization_baseline.py` 覆盖。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.t_account_models import TAccount, TAccountEntry
from app.services.t_account_service import TAccountService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _mk_project(db: AsyncSession, name: str) -> uuid.UUID:
    p = Project(
        id=uuid.uuid4(), name=name, client_name=name,
        project_type=ProjectType.annual, status=ProjectStatus.planning,
    )
    db.add(p)
    await db.flush()
    return p.id


@pytest_asyncio.fixture
async def two_projects(db: AsyncSession):
    """项目 A（含 1 个 T 型账户）与项目 B（空）。"""
    pid_a = await _mk_project(db, "项目A_2025")
    pid_b = await _mk_project(db, "项目B_2025")
    svc = TAccountService()
    acc = await svc.create_t_account(db, pid_a, {
        "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        "opening_balance": 1000,
    })
    await db.flush()
    return pid_a, pid_b, uuid.UUID(acc["id"])


class TestReadIsolation:
    @pytest.mark.asyncio
    async def test_owner_project_can_read(self, db: AsyncSession, two_projects):
        """正向：归属项目能读到（否则下面的断言是空转）。"""
        pid_a, _, aid = two_projects
        svc = TAccountService()
        got = await svc.get_t_account(db, aid, project_id=pid_a)
        assert got is not None
        assert got["account_code"] == "1601"

    @pytest.mark.asyncio
    async def test_other_project_cannot_read(self, db: AsyncSession, two_projects):
        """🔴 反向：拿项目 B 的 id 去读项目 A 的账户 → None（不是数据）。"""
        _, pid_b, aid = two_projects
        svc = TAccountService()
        got = await svc.get_t_account(db, aid, project_id=pid_b)
        assert got is None, "跨项目读到了他人 T 型账户（IDOR）"

    @pytest.mark.asyncio
    async def test_no_project_id_still_reads_legacy_behavior(
        self, db: AsyncSession, two_projects
    ):
        """不传 project_id 保持旧行为（内部调用过渡），但 router 禁止这么用。"""
        _, _, aid = two_projects
        svc = TAccountService()
        assert await svc.get_t_account(db, aid) is not None


class TestWriteIsolation:
    @pytest.mark.asyncio
    async def test_owner_project_can_add_entry(self, db: AsyncSession, two_projects):
        """正向：归属项目可写分录。"""
        pid_a, _, aid = two_projects
        svc = TAccountService()
        r = await svc.add_entry(
            db, aid, {"entry_type": "debit", "amount": 500}, project_id=pid_a
        )
        assert r["amount"] == 500

    @pytest.mark.asyncio
    async def test_other_project_cannot_add_entry(self, db: AsyncSession, two_projects):
        """🔴 反向：拿项目 B 的 id 往项目 A 的账户写分录 → 拒绝且**零写入**。"""
        pid_a, pid_b, aid = two_projects
        svc = TAccountService()
        before = await db.scalar(
            sa.select(sa.func.count()).select_from(TAccountEntry)
            .where(TAccountEntry.t_account_id == aid)
        )
        with pytest.raises(ValueError, match="不存在"):
            await svc.add_entry(
                db, aid, {"entry_type": "debit", "amount": 999}, project_id=pid_b
            )
        after = await db.scalar(
            sa.select(sa.func.count()).select_from(TAccountEntry)
            .where(TAccountEntry.t_account_id == aid)
        )
        assert after == before, "跨项目写入被拒后仍落了分录（必须零写入）"


class TestDerivedMethodsIsolation:
    """三个派生方法都走 get_t_account，须一并隔离。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["calculate_net_change", "integrate_to_cfs"])
    async def test_derived_cross_project_rejected(
        self, db: AsyncSession, two_projects, method: str
    ):
        _, pid_b, aid = two_projects
        svc = TAccountService()
        with pytest.raises(ValueError, match="不存在"):
            await getattr(svc, method)(db, aid, project_id=pid_b)

    @pytest.mark.asyncio
    async def test_reconcile_cross_project_rejected(self, db: AsyncSession, two_projects):
        from decimal import Decimal

        _, pid_b, aid = two_projects
        svc = TAccountService()
        with pytest.raises(ValueError, match="不存在"):
            await svc.reconcile_with_balance_sheet(
                db, aid, Decimal("0"), Decimal("1000"), project_id=pid_b
            )

    @pytest.mark.asyncio
    async def test_derived_owner_project_works(self, db: AsyncSession, two_projects):
        """正向对照：归属项目下三个派生方法都正常（防上面三条空转）。"""
        from decimal import Decimal

        pid_a, _, aid = two_projects
        svc = TAccountService()
        assert (await svc.calculate_net_change(db, aid, project_id=pid_a))["account_code"] == "1601"
        assert (await svc.integrate_to_cfs(db, aid, project_id=pid_a))["account_code"] == "1601"
        r = await svc.reconcile_with_balance_sheet(
            db, aid, Decimal("0"), Decimal("0"), project_id=pid_a
        )
        assert "is_reconciled" in r


class TestListIsolation:
    @pytest.mark.asyncio
    async def test_list_only_returns_own_project(self, db: AsyncSession, two_projects):
        """list 本就按 project_id 过滤 —— 正反两侧都断言，防回退。"""
        pid_a, pid_b, _ = two_projects
        svc = TAccountService()
        assert len(await svc.list_t_accounts(db, pid_a)) == 1
        assert len(await svc.list_t_accounts(db, pid_b)) == 0


class TestRouterPassesProjectId:
    """🔴 router 必须把 project_id 传给 service，否则 service 的过滤是死代码。"""

    @staticmethod
    def _router_src() -> str:
        import pathlib

        p = (
            pathlib.Path(__file__).resolve().parents[1]
            / "app" / "routers" / "t_accounts.py"
        )
        return p.read_text(encoding="utf-8")

    @pytest.mark.parametrize("call", [
        "svc.get_t_account(db, t_account_id, project_id=project_id)",
        "svc.add_entry(\n            db, t_account_id, body.model_dump(), project_id=project_id\n        )",
        "svc.calculate_net_change(db, t_account_id, project_id=project_id)",
        "svc.integrate_to_cfs(db, t_account_id, project_id=project_id)",
    ])
    def test_service_called_with_project_id(self, call: str):
        assert call in self._router_src(), (
            f"router 未把 project_id 传给 service：{call!r} 缺失 ⇒ 归属过滤是死代码"
        )

    def test_reconcile_passes_project_id(self):
        """reconcile 调用跨多行且内含 `Decimal(str(...))` 嵌套括号。

        🔴 首版用 `split(")", 1)` 取参数块 —— 被内层 `Decimal(str(body.bs_opening))`
        的 `)` 提前截断，断言必假红。必须**括号配平**取整个调用。
        """
        src = self._router_src()
        anchor = "reconcile_with_balance_sheet("
        i = src.index(anchor) + len(anchor)
        depth = 1
        while depth > 0:
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
            i += 1
        seg = src[src.index(anchor):i]
        assert "project_id=project_id" in seg, (
            f"reconcile 未传 project_id ⇒ 归属过滤是死代码。调用段：{seg}"
        )

    def test_no_endpoint_uses_identity_only_auth(self):
        """本文件端点不得回退到仅 `get_current_user`（不含项目维度）。"""
        src = self._router_src()
        # 剔 docstring 与注释后再判（否则说明文字会骗过断言）
        import re

        code = re.sub(r'"""[\s\S]*?"""', "", src)
        code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
        assert "Depends(get_current_user)" not in code, (
            "又回退到仅登录鉴权 —— T 型账户端点需 require_project_access"
        )
        assert code.count("require_project_access") >= 7, (
            f"项目级门禁数不足（现 {code.count('require_project_access')}，应 ≥7）"
        )
