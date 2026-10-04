"""任务 2.5：附注公式端点 section 2 综合真实测试 —— 真 ORM / 真 SQLite + 真 FastAPI 请求。

spec: consol-node-key-isolation-and-shared-context（需求 1.5、2.1~2.5；设计 §四、P2~P5）。

本任务是对 section 2（任务 2.1~2.4）尚未被充分覆盖的**综合场景**补齐，刻意不重复既有测试：
  - fill_rows 纯函数 / 单节点 P10 手工格、公式 CRUD 鉴权、consol lock 423  → test_consol_note_formulas.py
  - 非法 node_key 400、legacy 兼容、request_ctx 复用                       → test_consol_note_shared_context.py
  - 真实 TB 列取数、TB 失败 500（refresh/apply/audit-all/audit）           → test_consol_note_real_tb_columns.py
  - loader 级节点隔离 / 根回退                                             → test_consol_note_node_isolation.py
  - scope 解析、body/query 优先级单测                                      → test_consol_note_scope.py

本文件新增覆盖（任务 2.5 清单，均经真 FastAPI 请求或真 ORM 复读）：
  1. 不同节点公式结果互不串用：fill-by-formula / breakdown 对 G:consol 与 A:consol 产出不同合并数，
     各写各节点专属行，独立复读互不覆盖（P2、需求 2.4）。
  2. 手工格保护跨节点隔离：两节点各自手工格互不影响（需求 2.4）。
  3. 失败响应：非合并项目 404、非法 node_key 400、空字符串 400（需求 2.3、设计 §四「明确 HTTP 错误」）。
  4. 旧路由节点语义：body node_key 与 query node_key 优先级（端到端经端点）；无 node_key 走 legacy（需求 1.5）。
  5. 事务回滚：apply-formulas 中途 TB 失败 ⇒ 500 且 ORM 复读无部分写入（需求 2.3、设计 §四「事务回滚」）。
  6. 权限依赖真发请求：refresh/apply-formulas（edit）、aggregate（readonly）的 readonly/edit/outsider 行为。

证据纪律：故障注入放在被测端点的**下一层**（patch 生产函数 ``_load_tb_account_map`` / ``_save_note_record``），
不替换被测端点本身；断言写的是设计要求的正确行为，不写恒绿断言。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.base import PermissionLevel, UserRole
from app.models.consol_note_data_models import ConsolNoteData

from tests.test_consol_push import (  # noqa: F401  复用真集团与端点夹具
    Y,
    _persist,
    _User,
    client_for,
    db,
    factory,
    group,
)
from tests.test_consol_note_formulas import note_client  # noqa: F401

D = Decimal
_NS = "/api/consol-note-sections"
SID = "五-1-1"  # 货币资金章：种子 (4,1)=REPORT('BS-002')（合计=货币资金）

# 五-1-1 (4,1)=REPORT('BS-002')（货币资金合计）的各节点真实合并数。
# 数值来源：``group`` 夹具已种 G_s 1001=1000、A_s 1001=400（见 test_consol_push._tb），
# 多级合并 ⇒ G:consol=1400、A:consol=400、B 无货币资金=0。本文件不另种 1001（会撞 TB 唯一键）。
G_TOTAL = D("1400.00")
A_TOTAL = D("400.00")
B_TOTAL = D("0.00")


async def _generate_reports(db, project):
    """生成合并报表（breakdown / fill 的 REPORT() 取数依赖报表配置与已生成报表）。"""
    from app.services.consol_report_service import generate_consol_reports_sync

    await generate_consol_reports_sync(db, project.id, Y)
    await db.commit()


async def _node_rows(db, project_id, section_id=SID):
    """独立复读：返回 {node_key: ConsolNoteData} —— 验证节点行物理隔离。"""
    rows = (await db.execute(sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == project_id,
        ConsolNoteData.year == Y,
        ConsolNoteData.section_id == section_id,
    ))).scalars().all()
    return {r.node_key: r for r in rows}


# ─────────────────── 1. 不同节点公式结果互不串用（P2、需求 2.4） ───────────────────


class TestPerNodeFormulaResultsIsolated:
    @pytest.mark.asyncio
    async def test_breakdown_differs_per_node(self, db, group, note_client):
        """breakdown：同 project/year/section 下不同 node_key 的合并数互不相同（真树按节点取数）。

        五-1-1 (4,1)=REPORT('BS-002')（货币资金合计）：G_s=1000 + A_s=400 ⇒ G:consol=1400、A:consol=400、
        B 无货币资金=0。三节点结果不同即证明按节点计算、无串用。TB 数据来自 ``group`` 夹具，不另种。
        """
        await _generate_reports(db, group["G"])
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)

        async def _cell41(resp):
            assert resp.status_code == 200, resp.text
            cells = {(x["row_index"], x["col_index"]): x for x in resp.json()["cells"]}
            return cells[(4, 1)]["consolidated"]

        async with note_client(admin) as c:
            g_val = await _cell41(await c.get(f"{_NS}/breakdown/{gid}/{Y}/{SID}", params={"node_key": "G:consol"}))
            a_val = await _cell41(await c.get(f"{_NS}/breakdown/{gid}/{Y}/{SID}", params={"node_key": "A:consol"}))
            b_val = await _cell41(await c.get(f"{_NS}/breakdown/{gid}/{Y}/{SID}", params={"node_key": "B:subsidiary"}))
        assert D(g_val) == G_TOTAL, f"根节点合并货币资金=1400，实得 {g_val}"
        assert D(a_val) == A_TOTAL, f"A:consol 子合并只含 A_s=400，实得 {a_val}"
        assert D(b_val) == B_TOTAL, f"B 无货币资金=0，实得 {b_val}"
        assert len({g_val, a_val, b_val}) == 3, "三节点结果必须互不相同（无串用）"

    @pytest.mark.asyncio
    async def test_fill_by_formula_writes_isolated_node_rows(self, db, group, note_client):
        """fill-by-formula：对 G:consol 与 A:consol 分别填入，各写各节点专属行，独立复读互不覆盖（P2）。"""
        await _generate_reports(db, group["G"])
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)

        async with note_client(admin) as c:
            rg = await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/{SID}", params={"node_key": "G:consol"})
            ra = await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/{SID}", params={"node_key": "A:consol"})
        assert rg.status_code == 200 and ra.status_code == 200, (rg.text, ra.text)
        assert rg.json()["node_key"] == "G:consol" and ra.json()["node_key"] == "A:consol"

        # 独立复读：两节点各一行，物理独立，合计值各自不同
        await db.rollback()  # 内存 SQLite StaticPool 共用连接：回滚后看到的即已提交数据
        rows = await _node_rows(db, group["G"].id)
        assert set(rows) == {"G:consol", "A:consol"}, f"应各建一节点专属行，实得 {set(rows)}"
        assert rows["G:consol"].id != rows["A:consol"].id, "两节点行物理独立"
        g_total = rows["G:consol"].data["rows"][4][1]
        a_total = rows["A:consol"].data["rows"][4][1]
        assert D(g_total) == G_TOTAL and D(a_total) == A_TOTAL, (g_total, a_total)
        assert g_total != a_total, "不同节点合计写入值不得串用"

    @pytest.mark.asyncio
    async def test_fill_one_node_does_not_touch_other_node_row(self, db, group, note_client):
        """只对 A:consol 填入，不得创建或修改 G:consol 行（精确节点写入）。"""
        await _generate_reports(db, group["G"])
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/{SID}", params={"node_key": "A:consol"})
        assert resp.status_code == 200, resp.text
        await db.rollback()
        rows = await _node_rows(db, group["G"].id)
        assert set(rows) == {"A:consol"}, f"只应有 A:consol 行，不得凭空产生 G:consol 行：{set(rows)}"


# ─────────────────── 2. 手工格保护跨节点隔离（需求 2.4） ───────────────────


class TestManualCellCrossNodeIsolation:
    @pytest.mark.asyncio
    async def test_manual_cell_of_one_node_not_affected_by_other(self, db, group, note_client):
        """两节点各自预置带手工格的已保存行；对各节点填入后，每节点手工格保各自原值、互不影响。"""
        headers = ["项  目", "期末余额", "期初余额"]
        base_rows = [["库存现金", "", ""], ["银行存款", "", ""], ["其他货币资金", "", ""],
                     ["数字货币", "", ""], ["合  计", "", ""], ["其中：存放在境外的款项总额", "", ""]]

        def _mk(manual_val):
            rows = [list(r) for r in base_rows]
            rows[0][1] = manual_val  # 库存现金 期末 = 手工值
            return {"headers": headers, "rows": rows, "manual_cells": [{"row": 0, "col": 1}]}

        db.add(ConsolNoteData(project_id=group["G"].id, year=Y, section_id=SID, node_key="G:consol",
                              is_stale=True, data=_mk("G手填888")))
        db.add(ConsolNoteData(project_id=group["G"].id, year=Y, section_id=SID, node_key="A:consol",
                              is_stale=True, data=_mk("A手填111")))
        await db.commit()
        await _generate_reports(db, group["G"])
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)

        async with note_client(admin) as c:
            rg = await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/{SID}", params={"node_key": "G:consol"})
            ra = await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/{SID}", params={"node_key": "A:consol"})
        assert rg.status_code == 200 and ra.status_code == 200, (rg.text, ra.text)
        # 两次填入各自保留 1 个手工格
        assert [k["row_index"] for k in rg.json()["kept_manual"]] == [0]
        assert [k["row_index"] for k in ra.json()["kept_manual"]] == [0]

        await db.rollback()
        rows = await _node_rows(db, group["G"].id)
        assert rows["G:consol"].data["rows"][0][1] == "G手填888", "G 节点手工格保原值，不被 A 填入影响"
        assert rows["A:consol"].data["rows"][0][1] == "A手填111", "A 节点手工格保原值，不被 G 填入影响"
        # 合计行（非手工）按各节点合并数填入，互不相同
        assert D(rows["G:consol"].data["rows"][4][1]) == G_TOTAL
        assert D(rows["A:consol"].data["rows"][4][1]) == A_TOTAL


# ─────────────────── 3. 失败响应：非合并项目 404 / 非法 node 400 / 空串 400 ───────────────────


class TestFailureResponses:
    @pytest.mark.asyncio
    async def test_non_consol_project_returns_404(self, db, group, note_client):
        """对单户项目（非合并）发节点级公式端点 ⇒ 404（设计 §四「请求级上下文失败用明确 HTTP 错误」）。

        传 node_key 触发共享上下文装载；单户项目建树为非合并 ⇒ NoteScopeError(status=404)。
        """
        bid = str(group["B"].id)  # B 是单户项目
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            cases = [
                c.get(f"{_NS}/breakdown/{bid}/{Y}/{SID}", params={"node_key": "B:subsidiary"}),
                c.post(f"{_NS}/fill-by-formula/{bid}/{Y}/{SID}", params={"node_key": "B:subsidiary"}),
                c.post(f"{_NS}/refresh/{bid}/{Y}/{SID}", params={"node_key": "B:subsidiary"}, json={"standard": "soe"}),
                c.post(f"{_NS}/apply-formulas/{bid}/{Y}", params={"node_key": "B:subsidiary"}, json={"standard": "soe"}),
            ]
            for coro in cases:
                resp = await coro
                assert resp.status_code == 404, f"非合并项目应 404：{resp.request.url} -> {resp.status_code} {resp.text}"

    @pytest.mark.asyncio
    async def test_empty_string_node_key_rejected_400(self, db, group, note_client):
        """空字符串 node_key 是显式无效输入 ⇒ 400（不降级成省略；设计 §三.1）。"""
        await _generate_reports(db, group["G"])
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            # query 为空串经 FastAPI 传入；refresh 走 body 优先级链，这里显式用 query
            resp = await c.get(f"{_NS}/breakdown/{gid}/{Y}/{SID}", params={"node_key": ""})
        assert resp.status_code == 400, f"空字符串 node_key 应 400：{resp.text}"


# ─────────────────── 4. 旧路由节点语义：body vs query 优先级（端到端） ───────────────────


class TestLegacyRouteNodeSemantics:
    @pytest.mark.asyncio
    async def test_query_node_key_takes_priority_over_body(self, db, group, note_client):
        """refresh：query node_key 与 body node_key 同时给出时，query 优先（§三.1、需求 1.5）。

        body 给非法键、query 给合法键 ⇒ 不应报错（证明用的是 query）；反之 body 合法、query 非法 ⇒ 400。
        """
        await _generate_reports(db, group["G"])
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            # query 合法 + body 非法 ⇒ 用 query（合法）⇒ 200
            ok = await c.post(f"{_NS}/refresh/{gid}/{Y}/{SID}", params={"node_key": "G:consol"},
                              json={"standard": "soe", "node_key": "ZZ:illegal"})
            assert ok.status_code == 200, f"query 合法应优先、放行：{ok.text}"
            # query 非法 + body 合法 ⇒ 用 query（非法）⇒ 400
            bad = await c.post(f"{_NS}/refresh/{gid}/{Y}/{SID}", params={"node_key": "ZZ:illegal"},
                               json={"standard": "soe", "node_key": "G:consol"})
            assert bad.status_code == 400, f"query 非法应优先、拒绝：{bad.text}"

    @pytest.mark.asyncio
    async def test_body_node_key_used_when_query_absent(self, db, group, note_client):
        """refresh：未传 query node_key 时读取 body node_key（兼容旧调用；§三.1）。

        body 给非法键、不传 query ⇒ 用 body（非法）⇒ 400（证明 body 被采纳）。
        """
        await _generate_reports(db, group["G"])
        gid = str(group["G"].id)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(f"{_NS}/refresh/{gid}/{Y}/{SID}", json={"standard": "soe", "node_key": "ZZ:illegal"})
        assert resp.status_code == 400, f"query 缺省应采纳 body node_key（非法）⇒ 400：{resp.text}"

    @pytest.mark.asyncio
    async def test_no_node_key_runs_legacy_null_path(self, db, group, factory, note_client):
        """旧调用（无 node_key）走 legacy NULL 兼容；带 node_key 写节点专属行 —— 端到端经 PUT /data 验证（§三.5）。

        PUT /data 的 legacy / 节点写入是确定性的（不依赖 TB 匹配），是「无键走 NULL」最直接的端到端证据。
        同时验证 refresh / apply-formulas 无键调用不报错、也不升级成节点请求。
        """
        await _generate_reports(db, group["G"])
        gid_uuid = group["G"].id
        gid = str(gid_uuid)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            # 无 node_key ⇒ 写 legacy NULL 行
            put_legacy = await c.put(f"{_NS}/data/{gid}/{Y}/{SID}", json={"data": {"v": "legacy-put"}})
            assert put_legacy.status_code == 200 and put_legacy.json()["ok"] is True, put_legacy.text
            assert put_legacy.json()["node_key"] is None
            # 带 node_key ⇒ 写节点专属行
            put_node = await c.put(f"{_NS}/data/{gid}/{Y}/{SID}", params={"node_key": "A:consol"},
                                   json={"data": {"v": "node-put"}})
            assert put_node.status_code == 200 and put_node.json()["ok"] is True, put_node.text
            # refresh / apply-formulas 无键调用放行，不升级为节点请求
            r1 = await c.post(f"{_NS}/refresh/{gid}/{Y}/{SID}", json={"standard": "soe"})
            r2 = await c.post(f"{_NS}/apply-formulas/{gid}/{Y}", json={"standard": "soe"})
            assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)

        # 独立会话复读已提交数据（避免复用端点会话的连接状态）。
        async with factory() as verify:
            rows = {r.node_key: r.data for r in (await verify.execute(sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == gid_uuid, ConsolNoteData.year == Y,
                ConsolNoteData.section_id == SID,
            ))).scalars().all()}
        assert rows[None] == {"v": "legacy-put"}, "无 node_key 的 PUT 必须写 legacy NULL 行"
        assert rows["A:consol"] == {"v": "node-put"}, "带 node_key 的 PUT 必须写节点专属行"
        assert set(rows) == {None, "A:consol"}, "legacy 行与节点行物理独立，无键调用不升级为节点请求"


# ─────────────────── 5. 事务回滚：失败不留部分写入 ───────────────────


class TestTransactionRollback:
    @pytest.mark.asyncio
    async def test_apply_formulas_tb_failure_leaves_no_partial_write(self, db, group, factory, note_client, monkeypatch):
        """apply-formulas 中途 TB 取数失败 ⇒ 500，且**独立会话**复读确认 consol_note_data 无部分写入（事务回滚）。

        故障注在被测端点下一层（patch 生产函数 ``_load_tb_account_map``），不替换端点本身。
        失败请求的会话已 rollback 且连接状态不宜复用 ⇒ 用 ``factory`` 另开一个会话做独立事务复读（内存
        SQLite StaticPool 共用底层连接，另开会话看得到已提交数据）。
        """
        import app.routers.consol_note_sections as mod

        # 预置一行无关章节的 legacy 数据作对照（失败不得改动已有数据，也不得新增）
        db.add(ConsolNoteData(project_id=group["G"].id, year=Y, section_id="已存在章节", node_key=None,
                              data={"v": "pre"}))
        await db.commit()
        gid_uuid = group["G"].id

        async def _boom(*a, **k):
            raise RuntimeError("列 closing_balance 不存在")

        monkeypatch.setattr(mod, "_load_tb_account_map", _boom)
        gid = str(gid_uuid)
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            resp = await c.post(f"{_NS}/apply-formulas/{gid}/{Y}", json={"standard": "soe"})
        assert resp.status_code == 500 and "试算表取数失败" in resp.text, resp.text

        # 独立会话复读：失败后无任何 五-1-1 行被写入，且对照章节原样（事务回滚无部分写入）。
        async with factory() as verify:
            all_rows = (await verify.execute(sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == gid_uuid, ConsolNoteData.year == Y,
            ))).scalars().all()
        by_sid = {(r.section_id, r.node_key): r.data for r in all_rows}
        assert (SID, None) not in by_sid and (SID, "G:consol") not in by_sid, \
            f"TB 失败后不得留下 {SID} 的部分写入：{set(by_sid)}"
        assert by_sid[("已存在章节", None)] == {"v": "pre"}, "对照章节数据不得被失败请求改动"


# ─────────────────── 6. 权限依赖真发请求（refresh/apply-formulas=edit, aggregate=readonly） ───────────────────


class TestEndpointAuthorization:
    @pytest.mark.asyncio
    async def test_edit_endpoints_require_edit_permission(self, db, group, note_client):
        """refresh / apply-formulas 需 edit 权限：outsider 403、readonly 403、manager（edit）200。"""
        outsider = await _persist(db, _User(UserRole.auditor))
        reader = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.readonly)])
        # edit 权限经**项目成员资格**授予（require_project_access 只对 admin 角色跳过成员检查）。
        editor = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.edit)])
        await _generate_reports(db, group["G"])
        gid = str(group["G"].id)

        async with note_client(outsider) as c:
            assert (await c.post(f"{_NS}/refresh/{gid}/{Y}/{SID}", json={"standard": "soe"})).status_code == 403
            assert (await c.post(f"{_NS}/apply-formulas/{gid}/{Y}", json={"standard": "soe"})).status_code == 403
        async with note_client(reader) as c:
            assert (await c.post(f"{_NS}/refresh/{gid}/{Y}/{SID}", json={"standard": "soe"})).status_code == 403, \
                "只读成员不能执行 refresh（edit）"
            assert (await c.post(f"{_NS}/apply-formulas/{gid}/{Y}", json={"standard": "soe"})).status_code == 403, \
                "只读成员不能执行 apply-formulas（edit）"
        async with note_client(editor) as c:
            assert (await c.post(f"{_NS}/refresh/{gid}/{Y}/{SID}", json={"standard": "soe"})).status_code == 200
            assert (await c.post(f"{_NS}/apply-formulas/{gid}/{Y}", json={"standard": "soe"})).status_code == 200

    @pytest.mark.asyncio
    async def test_readonly_endpoints_allow_readonly_reject_outsider(self, db, group, note_client):
        """aggregate / audit / audit-all 为 readonly：成员（含只读）可访问、非成员 403。"""
        outsider = await _persist(db, _User(UserRole.auditor))
        reader = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.readonly)])
        await _generate_reports(db, group["G"])
        gid = str(group["G"].id)

        async with note_client(outsider) as c:
            assert (await c.post(f"{_NS}/aggregate/{gid}/{Y}",
                                 json={"section_id": SID, "mode": "direct"})).status_code == 403
            assert (await c.post(f"{_NS}/audit-all/{gid}/{Y}", json={"standard": "soe"})).status_code == 403
            assert (await c.post(f"{_NS}/audit/{gid}/{Y}/{SID}", json={"standard": "soe"})).status_code == 403
        async with note_client(reader) as c:
            assert (await c.post(f"{_NS}/aggregate/{gid}/{Y}",
                                 json={"section_id": SID, "mode": "direct"})).status_code == 200, "只读成员可汇总"
            assert (await c.post(f"{_NS}/audit-all/{gid}/{Y}", json={"standard": "soe"})).status_code == 200
            assert (await c.post(f"{_NS}/audit/{gid}/{Y}/{SID}", json={"standard": "soe"})).status_code == 200
