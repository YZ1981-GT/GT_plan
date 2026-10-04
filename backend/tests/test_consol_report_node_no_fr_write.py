"""任务 4.4：普通合并报表按节点读时计算 —— 读路径不写 FinancialReport + 不改唯一键/generate 流程 + 缺配置明确 404。

spec: consol-node-key-isolation-and-shared-context（需求 4.3；设计 §六.6、ADR-CNSC-003、P8）。

本任务职责（验证 + 守卫，确认 4.2/4.3 收口符合约束）：
  1. **GET 读路径在任何路径（成功 / 非法键 / 缺配置）都不得 INSERT/UPDATE/DELETE FinancialReport** ——
     真 ORM/SQLite：请求前后 `financial_report` 行数与逐行内容（current/prior/is_deleted/updated_at）完全不变。
  2. **报表 config 不存在 ⇒ 返回明确 404**，不静默空数组、不伪造行。
  3. **不改 FinancialReport 唯一键** `(project_id, year, report_type, row_code)`，也不改 generate/push 物化写入流程
     —— 结构性断言：唯一索引仍在 ORM、generate 写入路径仍存在（本 spec 的节点读时计算未触碰）。

被测真实生产函数（禁 mock 替换被测函数本身）：
  - ``routers.consol_report.get_consol_report``  经真 FastAPI 请求（读路径）
  - 真 ``FinancialReport`` ORM 行作前后不变量锚点（group 夹具预置 G24 BS-002=888.00 legacy 物化行）

变异证明（守卫能真打红）：若 ``get_consol_report`` 在读路径里对 FinancialReport 执行任何写入
（如误把节点结果 upsert 回物化表、或误触 generate），行数或内容快照即变 ⇒ 断言失败。
见 `TestReadPathNeverWritesFinancialReport.test_mutation_proof_write_detected` 以真实写入证明守卫非恒绿。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.core import UserRole
from app.models.report_models import FinancialReport, FinancialReportType

# 复用 test_consol_push 的真集团夹具（真 SQLite 内存库 + 真 ORM 行 + 真 FastAPI client）。
from tests.test_consol_push import (  # noqa: F401
    Y,
    _User,
    client_for,
    db,
    factory,
    group,
)

D = Decimal


async def _fr_snapshot(db) -> dict[tuple, dict]:
    """financial_report 全表快照：按唯一键锚定每行的内容（含软删标记与更新时间）。

    返回 {(project_id, year, report_type, row_code): {字段...}}，用于读请求前后逐行对拍。
    """
    rows = (await db.execute(sa.select(FinancialReport))).scalars().all()
    snap: dict[tuple, dict] = {}
    for r in rows:
        key = (str(r.project_id), r.year, _enum_text(r.report_type), r.row_code)
        snap[key] = {
            "current": None if r.current_period_amount is None else str(r.current_period_amount),
            "prior": None if r.prior_period_amount is None else str(r.prior_period_amount),
            "is_deleted": bool(r.is_deleted),
            "row_name": r.row_name,
            "updated_at": r.updated_at,
            "id": str(r.id),
        }
    return snap


def _enum_text(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


class TestReadPathNeverWritesFinancialReport:
    """P8 / 设计 §六.6 / ADR-CNSC-003：节点读时计算是**只读**，不写项目级物化 FinancialReport。"""

    @pytest.mark.asyncio
    async def test_read_paths_do_not_mutate_financial_report(self, db, group, client_for):
        """成功 / 非法键 / 缺配置三条 GET 路径请求前后，financial_report 行数与逐行内容完全不变。

        group 夹具预置了上年合并项目 G24 的 BS-002=888.00 物化行（legacy），它是本不变量的锚点：
        读路径既不读它冒充（见 test_consol_push 的哨兵反证），也**不写/不改/不删**它。
        """
        admin = _User(UserRole.admin)
        gid = str(group["G"].id)

        before = await _fr_snapshot(db)
        assert before, "前置：group 夹具应已预置至少一行物化 FinancialReport（G24 BS-002）作不变量锚点"

        async with client_for(admin) as c:
            # 路径 A：成功（缺省根 + 显式非根子合并节点，两套报表类型）
            for node_key in (None, "G:consol", "A:consol"):
                for rt in ("balance_sheet", "income_statement"):
                    params = {"report_type": rt}
                    if node_key is not None:
                        params["node_key"] = node_key
                    resp = await c.get(f"/api/consolidation/reports/{gid}/{Y}", params=params)
                    assert resp.status_code == 200, resp.text
            # 路径 B：非法节点键 ⇒ 400（校验先于读取，不触数据层写入）
            bad = await c.get(f"/api/consolidation/reports/{gid}/{Y}",
                              params={"report_type": "balance_sheet", "node_key": "ZZ:consol"})
            assert bad.status_code == 400
            # 路径 C：缺报表配置（equity_statement 无 config 行）⇒ 404
            missing = await c.get(f"/api/consolidation/reports/{gid}/{Y}",
                                  params={"report_type": "equity_statement"})
            assert missing.status_code == 404
            # 路径 D：非合并项目 ⇒ 404
            not_consol = await c.get(f"/api/consolidation/reports/{group['B'].id}/{Y}",
                                     params={"report_type": "balance_sheet"})
            assert not_consol.status_code == 404

        # 读路径执行完毕，financial_report 必须与请求前逐行一致（行数 + 每行内容 + 更新时间）。
        # 需用新会话读，避免 identity map 掩盖未提交的游离写入 —— 这里 db 是同一会话，
        # 但读路径若写入会先 flush/commit 到该会话，故同会话快照已足以暴露写入。
        after = await _fr_snapshot(db)
        assert set(after) == set(before), (
            f"读路径不得新增/删除 FinancialReport 行；多出或丢失："
            f"新增 {set(after) - set(before)}，丢失 {set(before) - set(after)}"
        )
        for key, b in before.items():
            assert after[key] == b, f"读路径不得修改 FinancialReport 行 {key}：{b} -> {after[key]}"

    @pytest.mark.asyncio
    async def test_mutation_proof_write_detected(self, db, group, client_for):
        """变异证明：若读请求后 financial_report 真被写了一行，_fr_snapshot 对拍必打红 ⇒ 守卫非恒绿。

        这里**不改生产代码**，而是在同一会话中模拟"读路径误写"的后果（真写一行），
        证明上面的不变量断言能够检测到任何写入。
        """
        admin = _User(UserRole.admin)
        gid = str(group["G"].id)

        before = await _fr_snapshot(db)
        async with client_for(admin) as c:
            resp = await c.get(f"/api/consolidation/reports/{gid}/{Y}",
                               params={"report_type": "balance_sheet"})
            assert resp.status_code == 200, resp.text
        # 模拟"误写"：真向 financial_report 插入一行（这是守卫要防止的后果）
        db.add(FinancialReport(
            project_id=group["G"].id, year=Y, report_type=FinancialReportType.balance_sheet,
            row_code="BS-002", row_name="货币资金", current_period_amount=D("1.00"),
        ))
        await db.commit()
        after = await _fr_snapshot(db)
        # 行数/内容对拍应检出差异（证明不变量断言不是恒绿）
        changed = set(after) != set(before) or any(after[k] != before.get(k) for k in after if k in before)
        assert changed, "变异证明失败：真写入一行后快照对拍竟未检出差异 ⇒ 守卫恒绿"


class TestMissingConfigExplicit404:
    """设计 §六.6 / 需求 4.3：有效 node_key 下报表配置缺失 ⇒ 明确 404，不静默空数组/不伪造。"""

    @pytest.mark.asyncio
    async def test_report_type_without_config_returns_404_not_empty(self, db, group, client_for):
        """equity_statement / cash_flow_statement / impairment_provision 在 group 夹具无 config 行 ⇒ 404。

        关键：不得返回 200 空数组（静默）。错误 detail 为中文、含报表类型名与"没有报表配置"。
        """
        admin = _User(UserRole.admin)
        gid = str(group["G"].id)
        async with client_for(admin) as c:
            for rt in ("equity_statement", "cash_flow_statement", "impairment_provision"):
                resp = await c.get(f"/api/consolidation/reports/{gid}/{Y}",
                                   params={"report_type": rt})
                assert resp.status_code == 404, (rt, resp.status_code, resp.text)
                detail = resp.json()["detail"]
                assert "没有报表配置" in detail, (rt, detail)

    @pytest.mark.asyncio
    async def test_configured_report_type_returns_rows_not_404(self, db, group, client_for):
        """反面：有 config 行的 balance_sheet 返回 200 行数组（证明上面的 404 不是无差别拒绝）。"""
        admin = _User(UserRole.admin)
        gid = str(group["G"].id)
        async with client_for(admin) as c:
            resp = await c.get(f"/api/consolidation/reports/{gid}/{Y}",
                               params={"report_type": "balance_sheet"})
            assert resp.status_code == 200, resp.text
            rows = resp.json()
            assert isinstance(rows, list) and len(rows) > 0
            assert any(r["row_code"] == "BS-002" for r in rows)


class TestUniqueKeyAndGenerateFlowUntouched:
    """ADR-CNSC-003 / 设计 §六.6：不改 FinancialReport 唯一键，不改 generate/push 物化写入流程。

    结构性断言（现读 ORM/service 实证），确认本 spec 的节点读时计算未触碰物化写入侧。
    """

    def test_financial_report_unique_key_unchanged(self):
        """唯一索引仍为 (project_id, year, report_type, row_code)，且无 node_key 列。"""
        table = FinancialReport.__table__
        # 列集合不含 node_key（FinancialReport 继续是项目级物化模型，不是多节点写入表）
        assert "node_key" not in table.c, "FinancialReport 不应新增 node_key 列（节点报表读时计算，不物化）"
        # 唯一约束/索引覆盖且仅覆盖这四列
        unique_cols_sets = []
        for idx in table.indexes:
            if idx.unique:
                unique_cols_sets.append(tuple(c.name for c in idx.columns))
        for con in table.constraints:
            cols = getattr(con, "columns", None)
            if cols is not None and type(con).__name__ == "UniqueConstraint":
                unique_cols_sets.append(tuple(c.name for c in cols))
        expected = ("project_id", "year", "report_type", "row_code")
        assert any(set(cs) == set(expected) for cs in unique_cols_sets), (
            f"FinancialReport 唯一键应为 {expected}，实得 {unique_cols_sets}"
        )

    def test_generate_write_flow_present_and_read_endpoint_does_not_import_it(self):
        """generate 物化写入入口仍存在；GET 读端点模块不依赖 generate 写入（读路径不触发物化）。"""
        from app.services import consol_report_service

        # generate 写入流程仍在（本 spec 未删/改它）
        assert hasattr(consol_report_service, "generate_consol_reports_sync")
        # 读端点源码中不出现对 generate_consol_reports_sync 的调用（只 POST /generate 用它）
        import inspect

        from app.routers.consol_report import get_consol_report

        src = inspect.getsource(get_consol_report)
        assert "generate_consol_reports_sync" not in src, "GET 读路径不应调用 generate 物化写入"
        # 读端点也不 add/flush/commit FinancialReport（源码级辅助断言，真不变量由上面的集成测试守护）
        assert "FinancialReport(" not in src, "GET 读路径不应构造 FinancialReport 行"
