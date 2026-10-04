"""任务 2.3：附注公式端点只读真实 TB 列、不吞异常 —— 真 ORM / 真 SQLite + 真 FastAPI 请求。

spec: consol-node-key-isolation-and-shared-context（需求 2.2、2.3；设计 §四）。

背景（修复前的真实缺陷）：``/refresh``、``/audit``、``/audit-all``、``/apply-formulas``、``/aggregate``
内直接 SQL 查询 ``trial_balance`` 中**不存在的列** ``account_code`` / ``closing_balance`` /
``debit_amount`` / ``credit_amount``，且 ``except Exception`` 把 SQL 错误吞掉后回传模板值 / 伪造 0 /
报告成功。真实 ``trial_balance`` 列见 ``app.models.audit_platform_models.TrialBalance``：
``standard_account_code / account_name / unadjusted_amount / audited_amount / opening_balance / ...``。

本测试：
  A. 用真实列（``audited_amount`` / ``opening_balance``）种子化 TB，验证端点取数正确流经真实列
     （期末→审定数、期初→期初余额），而非回退模板默认值 —— 证明假列已删且 SQL 实际跑通。
  B. 注入 DB 层取数失败，验证端点返回明确 HTTP 错误，而不是吞异常回传模板 / 伪造 0 / 报告成功。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.audit_platform_models import AccountCategory, TrialBalance

from app.models.base import UserRole
from tests.test_consol_push import (  # noqa: F401  复用真集团与端点夹具
    Y,
    _User,
    client_for,
    db,
    factory,
    group,
)
from tests.test_consol_note_formulas import note_client  # noqa: F401

D = Decimal
_NS = "/api/consol-note-sections"


def _tb_row(project_id, code, name, *, audited, opening, company_code="001"):
    """真实 TB 行：带 audited_amount（审定数）与 opening_balance（期初余额）。"""
    return TrialBalance(
        id=uuid.uuid4(), project_id=project_id, year=Y, company_code=company_code,
        standard_account_code=code, account_name=name,
        account_category=AccountCategory.asset,
        audited_amount=D(str(audited)), opening_balance=D(str(opening)),
    )


async def _seed_tb(db, project):
    """为 五-1-1（货币资金：库存现金 / 银行存款）种子真实 TB 行。"""
    db.add(_tb_row(project.id, "1001", "库存现金", audited="100.00", opening="40.00"))
    db.add(_tb_row(project.id, "1002", "银行存款", audited="800.00", opening="500.00"))
    await db.commit()


# ─────────────────── A. 真实列取数（证明假列已删、SQL 真跑通） ───────────────────


class TestRealColumnReads:
    @pytest.mark.asyncio
    async def test_refresh_fills_from_audited_and_opening(self, db, group, note_client):
        """``/refresh``：期末余额列=审定数(audited_amount)、期初余额列=opening_balance。

        修复前查 ``closing_balance`` 列不存在 ⇒ SQL 抛错 ⇒ 吞异常回传模板空值。
        现在应真实命中并填入 100 / 40（库存现金）与 800 / 500（银行存款）。
        """
        await _seed_tb(db, group["G"])
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(f"{_NS}/refresh/{gid}/{Y}/五-1-1", json={"standard": "soe"})
        assert resp.status_code == 200, resp.text
        rows = resp.json()["rows"]
        by_name = {r[0]: r for r in rows if r and r[0]}
        # 期末余额(col1)=审定数, 期初余额(col2)=opening_balance
        assert by_name["库存现金"][1] == "100.0"
        assert by_name["库存现金"][2] == "40.0"
        assert by_name["银行存款"][1] == "800.0"
        assert by_name["银行存款"][2] == "500.0"

    @pytest.mark.asyncio
    async def test_apply_formulas_updates_from_real_columns(self, db, group, note_client):
        """``/apply-formulas``：按真实列填充并保存；返回更新的章节数 > 0（修复前恒 0 / 吞异常）。"""
        await _seed_tb(db, group["G"])
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(f"{_NS}/apply-formulas/{gid}/{Y}", json={"standard": "soe"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["updated_sections"] > 0, "真实列命中应更新至少一个章节"

    @pytest.mark.asyncio
    async def test_apply_formulas_empty_tb_reports_no_fabrication(self, db, group, note_client):
        """无 TB 数据：如实返回 0 更新与「试算表无数据」，不伪造成功。"""
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(f"{_NS}/apply-formulas/{gid}/{Y}", json={"standard": "soe"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["updated_sections"] == 0
        assert "无数据" in body["message"]


# ─────────────────── B. 取数失败不被吞（明确 HTTP 错误） ───────────────────


class TestFailuresNotSwallowed:
    """注入 TB 取数失败，验证端点明确报错而非回传模板 / 伪造 0 / 报成功。

    故障注在被测端点的下一层：patch 生产函数 ``_load_tb_account_map`` 使其抛错；
    不替换被测端点本身。``/aggregate`` 走独立 per-company 查询，单独 patch ``db.execute``。
    """

    @pytest.mark.asyncio
    async def test_refresh_tb_failure_returns_error(self, db, group, note_client, monkeypatch):
        import app.routers.consol_note_sections as mod

        async def _boom(*a, **k):
            raise RuntimeError("列 closing_balance 不存在")

        monkeypatch.setattr(mod, "_load_tb_account_map", _boom)
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(f"{_NS}/refresh/{gid}/{Y}/五-1-1", json={"standard": "soe"})
        assert resp.status_code == 500, f"取数失败必须明确报错，不得回传模板：{resp.text}"
        assert "试算表取数失败" in resp.text

    @pytest.mark.asyncio
    async def test_apply_formulas_tb_failure_returns_error(self, db, group, note_client, monkeypatch):
        import app.routers.consol_note_sections as mod

        async def _boom(*a, **k):
            raise RuntimeError("列 debit_amount 不存在")

        monkeypatch.setattr(mod, "_load_tb_account_map", _boom)
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(f"{_NS}/apply-formulas/{gid}/{Y}", json={"standard": "soe"})
        assert resp.status_code == 500, f"取数失败必须明确报错，不得伪造 0：{resp.text}"
        assert "试算表取数失败" in resp.text

    @pytest.mark.asyncio
    async def test_audit_all_tb_failure_returns_error(self, db, group, note_client, monkeypatch):
        import app.routers.consol_note_sections as mod

        async def _boom(*a, **k):
            raise RuntimeError("列 credit_amount 不存在")

        monkeypatch.setattr(mod, "_load_tb_account_map", _boom)
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(f"{_NS}/audit-all/{gid}/{Y}", json={"standard": "soe"})
        assert resp.status_code == 500, f"交叉校验取数失败必须明确报错，不得吞成「全部通过」：{resp.text}"
        assert "试算表取数失败" in resp.text

    @pytest.mark.asyncio
    async def test_audit_single_tb_failure_returns_error(self, db, group, note_client, monkeypatch):
        import app.routers.consol_note_sections as mod

        async def _boom(*a, **k):
            raise RuntimeError("列 account_code 不存在")

        monkeypatch.setattr(mod, "_load_tb_account_map", _boom)
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(
                f"{_NS}/audit/{gid}/{Y}/五-1-1",
                json={"standard": "soe", "headers": ["项  目", "期末余额"], "rows": [["库存现金", "1"]]},
            )
        assert resp.status_code == 500, f"交叉校验取数失败必须明确报错：{resp.text}"
        assert "试算表取数失败" in resp.text


# ─────────────────── C. 真实列映射单元测试（_load_tb_account_map） ───────────────────


class TestLoadTbAccountMap:
    @pytest.mark.asyncio
    async def test_period_is_audited_minus_opening(self, db, group):
        """``period`` = 审定数 - 期初余额（本期发生额口径，与 amount_resolver 一致）。"""
        from app.routers.consol_note_sections import _load_tb_account_map

        await _seed_tb(db, group["G"])
        tb_map = await _load_tb_account_map(db, group["G"].id, Y, "001")
        assert tb_map["库存现金"]["closing"] == 100.0
        assert tb_map["库存现金"]["opening"] == 40.0
        assert tb_map["库存现金"]["period"] == 60.0  # 100 - 40

    @pytest.mark.asyncio
    async def test_soft_deleted_rows_excluded(self, db, group):
        """软删行不计入（is_deleted=True）。"""
        from app.routers.consol_note_sections import _load_tb_account_map

        row = _tb_row(group["G"].id, "1001", "库存现金", audited="100.00", opening="40.00")
        row.is_deleted = True
        db.add(row)
        await db.commit()
        tb_map = await _load_tb_account_map(db, group["G"].id, Y, "001")
        assert "库存现金" not in tb_map
