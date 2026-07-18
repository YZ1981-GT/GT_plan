# Feature: visibility-isolation-go-live-hardening — Task 4 审计 72 条 native_authz 入口（R3）
"""Task 4 / Requirements 3.1–3.11（组件 H3 NativeAuthzAuditor / C14 CoverageGuard / C8 WpBoundGate）。

证明四层，**分类真实、无假绿、无 silent pass**：

  A. 全量分类（Req 3.1/3.2/3.6/3.7）：Route_Coverage_Ledger 基线 72 条 native_authz 入口每一条被
     判定为 gated（Leak_Risk 已接门）/ justified_allowlist（无 Leak_Risk，附 rationale）；
     原 13 条 leak_risk_deferred 已全部真正接入 Wp_Bound_Gate → leak_risk_deferred=0（无诚实 GAP 残留）。
     计数：gated=19 + justified=52 + leak_risk_deferred=0 + worker(justified)=1 = 72。

  B. Ledger 一致（Req 3.3/3.5/3.9）：committed ledger 中每条 gated 入口 gate=gated + matrix 已登记 +
     test_ids 非空 + classification_reason；每条剩余 native_authz 入口带 audit_classification ∈
     {justified_allowlist, leak_risk_deferred} + audit_reason（+ deferred 带 audit_remediation）+
     audit_reviewer；无 native_authz 入口缺分类（无 silent pass，Req 3.8）。

  C. Route_Drift_Guard 阻断（Req 3.8/3.10）：committed ledger 上 coverage_guard 干净（无
     native_authz_unaudited）；合成一条未分类 native_authz 入口 → 守卫报 native_authz_unaudited
     阻断 CI（drift guard blocks synthetic unclassified）。

  D. 新接门路由真实隔离（Req 3.3/3.4）：**真实 FastAPI 路由 handler + 真实 PostgreSQL**：
     附件族(links/attachment-workpapers/ocr-fields)接 enforce_attachment_wp_visibility 后，
     委派 lead 放行；越权成员(scope_cycles 不含底稿循环)统一 External_Not_Found(404)；跨项目 404；
     未绑定底稿的附件放行(additive passthrough，不越界收紧项目级证据)。

不改父 spec gate 语义；仅审计分类 + 接线附件族 leak_risk + 扩展 coverage_guard。真实 PostgreSQL
（audit_platform），每用例事务隔离回滚。leak_risk_deferred 是诚实待接线 GAP，Task 4 marker 不因此翻绿。
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.security import coverage_guard as cg
from app.security import native_authz_audit as audit
from app.services.wp_visibility.denial import EXTERNAL_NOT_FOUND_DETAIL

from tests.procedure_delegation_visibility._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)


# ===========================================================================
# A. 全量分类（Req 3.1/3.2/3.6/3.7） — 纯数据，无 DB
# ===========================================================================
class TestFullClassification:
    def test_classified_total_is_72_no_unaudited(self):
        """72 条 native_authz 基线全部被分类，无 unaudited 残留（Req 3.1/3.2/3.7）。"""
        report = audit.build_report()
        assert report["classified_total"] == 72, report["classification"]
        assert report["unaudited_http"] == 0
        assert report["baseline_native_authz_total"] == 72

    def test_classification_counts(self):
        """gated=19 + justified=52 + leak_risk_deferred=0 + worker=1 = 72（Req 3.3/3.5）。"""
        c = audit.build_report()["classification"]
        assert c["gated"] == 19
        assert c["justified_allowlist"] == 52
        assert c["leak_risk_deferred"] == 0
        assert c["worker_justified"] == 1
        assert c["gated"] + c["justified_allowlist"] + c["leak_risk_deferred"] + c["worker_justified"] == 72

    def test_flip_condition_met_all_wired(self):
        """13 条 leak_risk 全部真正接门后 leak_risk_deferred==0 → flip 条件满足（Task 4 可翻绿）。"""
        report = audit.build_report()
        assert report["flip_condition_met"] is True
        assert report["classification"]["leak_risk_deferred"] == 0
        assert report["unaudited_http"] == 0

    def test_deferred_table_empty_all_wired(self):
        """LEAK_RISK_DEFERRED 已清空：原 13 条批量导出/下载/导入/同步/搜索全部接入 Wp_Bound_Gate。"""
        assert audit.LEAK_RISK_DEFERRED == {}

    def test_thirteen_previously_deferred_now_gated(self):
        """原 13 条 leak_risk 现全部在 GATED_LEAK_RISK（gated=6 附件族 + 13 批量族 = 19）。"""
        assert len(audit.GATED_LEAK_RISK) == 19
        # 13 条批量/导入/同步/搜索族均带 registered matrix
        newly = {
            ("/api/projects/{project_id}/working-papers/download-pack", "POST"),
            ("/api/projects/{project_id}/workpapers/download-pack", "POST"),
            ("/api/projects/{project_id}/working-papers/batch-export", "POST"),
            ("/api/projects/{project_id}/working-papers/batch-export-async", "POST"),
            ("/api/projects/{project_id}/workpapers/batch-export", "POST"),
            ("/api/projects/{project_id}/workpapers/batch-export-enhanced", "POST"),
            ("/api/projects/{project_id}/workpapers/import-enhanced", "POST"),
            ("/api/projects/{project_id}/workpapers/import/resolve", "POST"),
            ("/api/projects/{project_id}/excel-html/sync-from-onlyoffice/{file_stem}", "POST"),
            ("/api/projects/{project_id}/bulk-tab/export/{task_id}/download", "GET"),
            ("/api/projects/{project_id}/bulk-tab/import/rollback", "POST"),
            ("/api/projects/{project_id}/workpapers/batch-prefill", "POST"),
            ("/api/projects/{project_id}/workpapers/search", "GET"),
        }
        assert newly <= set(audit.GATED_LEAK_RISK)

    def test_justified_entries_carry_rationale_and_reviewer(self):
        """每条 justified_allowlist 附 rationale；分类携 reviewer（Req 3.5/3.11）。"""
        for key, reason in audit.JUSTIFIED_ALLOWLIST.items():
            assert reason and isinstance(reason, str), f"justified missing reason: {key}"
        # classify 返回 reviewer
        for key in list(audit.JUSTIFIED_ALLOWLIST)[:1] + list(audit.GATED_LEAK_RISK)[:1]:
            cls = audit.classify(key[0], key[1])
            assert cls["reviewer"] == audit.REVIEWER

    def test_fail_closed_unlisted_route_is_unaudited(self):
        """未列入任何静态分类表的入口 → unaudited（fail-closed，Req 3.2）。"""
        cls = audit.classify("/api/workpapers/never-registered-synthetic", "GET")
        assert cls["disposition"] == "unaudited"


# ===========================================================================
# B. Ledger 一致（Req 3.3/3.5/3.9） — 读 committed ledger
# ===========================================================================
class TestLedgerConsistency:
    def _ledger(self):
        return audit.load_ledger()

    def test_gated_attachment_entries_finalised(self):
        """6 条附件族 gated 入口：gate=gated + matrix 已登记 + test_ids + reason（Req 3.3/3.9）。"""
        ledger = self._ledger()
        http = {(e["route"], e["method"]): e for e in ledger["entries"] if e.get("kind") == "http"}
        matrix_pairs = cg.matrix_registered_pairs()
        for key in audit.GATED_LEAK_RISK:
            e = http.get(key)
            assert e is not None, f"gated entry missing from ledger: {key}"
            assert e["gate"] == "gated", f"{key} not gated: {e['gate']}"
            pair = cg.parse_matrix_ref(e.get("matrix"))
            assert pair in matrix_pairs, f"{key} matrix not registered: {e.get('matrix')}"
            assert e.get("test_ids"), f"{key} missing test_ids"
            assert audit.AUDIT_TEST in e["test_ids"]
            assert e.get("classification_reason")

    def test_every_native_authz_entry_is_gated_or_allowlisted(self):
        """committed ledger：每条剩余 native_authz 入口带 audit_classification（无 silent pass，Req 3.6/3.8）。"""
        ledger = self._ledger()
        http_native = audit.native_authz_http_entries(ledger)
        assert http_native, "expected remaining native_authz http entries"
        for e in http_native:
            disp = e.get("audit_classification")
            assert disp in ("justified_allowlist", "leak_risk_deferred"), (
                f"native_authz entry without audit classification (silent pass): "
                f"{e['method']} {e['route']} -> {disp}"
            )
            assert e.get("audit_reason"), f"missing audit_reason: {e['route']}"
            assert e.get("audit_reviewer") == audit.REVIEWER
            if disp == "leak_risk_deferred":
                assert e.get("audit_remediation"), f"deferred missing remediation: {e['route']}"
            assert audit.AUDIT_TEST in (e.get("test_ids") or [])

    def test_worker_native_authz_recorded(self):
        """worker native_authz 在 coverage_guard NONHTTP_CLASSIFICATION 有记录（Req 3.6）。"""
        for ep in audit.WORKER_NATIVE_AUTHZ:
            assert ep in cg.NONHTTP_CLASSIFICATION


# ===========================================================================
# C. Route_Drift_Guard 阻断（Req 3.8/3.10）
# ===========================================================================
@pytest.fixture(scope="module")
def _real_app():
    from app.main import app

    return app


class TestDriftGuard:
    def test_committed_ledger_clean_no_unaudited(self, _real_app):
        """committed ledger 上守卫干净：无 native_authz_unaudited（Req 3.8）。"""
        f = cg.check_drift(app=_real_app, ledger=audit.load_ledger())
        assert f.native_authz_unaudited == [], f.native_authz_unaudited
        assert f.is_clean(), f.summary()

    def test_guard_blocks_synthetic_unclassified_native_authz(self):
        """合成一条未分类 native_authz 入口 → 守卫报 native_authz_unaudited 阻断（drift guard blocks synthetic unclassified，Req 3.10）。"""
        from fastapi import FastAPI

        def _native_handler(wp_id):  # 携原生授权 hook（get_current_user 归属）
            from app.deps import get_current_user  # noqa: F401 — 触发 native authz 语义

            return {"wp_id": wp_id}

        app = FastAPI()
        route = "/api/workpapers/{wp_id}/synthetic-unaudited-native"
        app.add_api_route(route, _native_handler, methods=["GET"])
        ledger = {
            "entries": [
                {
                    "kind": "http",
                    "entrypoint": "x:y",
                    "route": route,
                    "method": "GET",
                    "family": "detail",
                    "action": "read",
                    "wp_bound": True,
                    "gate": "native_authz",
                    "matrix": "native_authz",
                    "test_ids": ["x"],
                }
            ],
            "migration_head": "V113",
        }
        f = cg.check_drift(app=app, ledger=ledger)
        assert any("synthetic-unaudited-native" in m for m in f.native_authz_unaudited), (
            "drift guard must block a native_authz route not in any audit table"
        )
        assert not f.is_clean()


# ===========================================================================
# D. 新接门路由真实隔离（Req 3.3/3.4） — 真实 FastAPI handler + 真实 PostgreSQL
# ===========================================================================
class _PgCtx:
    def __init__(self) -> None:
        self.engine = None
        self.conn = None
        self.trans = None
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self.engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
        self.conn = await self.engine.connect()
        self.trans = await self.conn.begin()
        self.session = AsyncSession(bind=self.conn, join_transaction_mode="create_savepoint")
        return self.session

    async def __aexit__(self, *exc) -> None:
        if self.session is not None:
            await self.session.close()
        if self.trans is not None:
            await self.trans.rollback()
        if self.conn is not None:
            await self.conn.close()
        if self.engine is not None:
            await self.engine.dispose()


async def _mk_attachment(s: AsyncSession, project_id):
    from app.models.attachment_models import Attachment

    att = Attachment(
        project_id=project_id,
        file_name=f"e_{uuid.uuid4().hex[:8]}.xlsx",
        file_path=f"/tmp/{uuid.uuid4().hex[:8]}.xlsx",
        file_type="xlsx",
        file_size=1024,
    )
    s.add(att)
    await s.flush()
    return att


async def _link_att_wp(s: AsyncSession, attachment_id, wp_id):
    from app.models.attachment_models import AttachmentWorkingPaper

    link = AttachmentWorkingPaper(
        attachment_id=attachment_id, wp_id=wp_id, association_type="evidence"
    )
    s.add(link)
    await s.flush()
    return link


async def _lead_scenario(s, *, scope="D", cycle="D"):
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (real gate integration)")
@pytest.mark.asyncio
class TestNewlyGatedRouteIsolation:
    async def test_links_allow_for_delegated_lead(self):
        """委派 lead 对绑定底稿可见 → get_attachment_links 放行（Req 3.3/3.4 allow）。"""
        from app.routers.attachment_lineage import get_attachment_links

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, lead, _wi, wp = await _lead_scenario(s)
            att = await _mk_attachment(s, proj.id)
            await _link_att_wp(s, att.id, wp.id)
            res = await get_attachment_links(attachment_id=att.id, db=s, current_user=lead)
            assert res is not None  # 放行（返回关联清单，未抛 404）
        finally:
            await ctx.__aexit__()

    async def test_links_deny_outsider_404_scope_isolation(self):
        """越权成员(scope_cycles 不含底稿循环)→ External_Not_Found(404)（scope 隔离，Req 3.4 deny）。"""
        from app.routers.attachment_lineage import get_attachment_links

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, _wi, wp = await _lead_scenario(s)
            att = await _mk_attachment(s, proj.id)
            await _link_att_wp(s, att.id, wp.id)
            outsider = await mk_user(s)
            await mk_project_user(s, proj.id, outsider.id, scope_cycles="")  # 项目成员但无循环委派
            await s.flush()
            with pytest.raises(HTTPException) as ei:
                await get_attachment_links(attachment_id=att.id, db=s, current_user=outsider)
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        finally:
            await ctx.__aexit__()

    async def test_links_deny_wrong_cycle_scope_404(self):
        """lead 委派循环(F)≠底稿循环(D)→ 404（scope_cycles 上界隔离，Req 3.4）。"""
        from app.routers.attachment_lineage import get_attachment_links

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            # 底稿循环 D，成员 scope 仅 F（不含 D）→ 不可见。
            proj = await mk_project(s)
            user = await mk_user(s)
            wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle="D")
            wp = await mk_working_paper(s, proj.id, wi.id)
            await mk_project_user(s, proj.id, user.id, scope_cycles="F")
            await s.flush()
            att = await _mk_attachment(s, proj.id)
            await _link_att_wp(s, att.id, wp.id)
            with pytest.raises(HTTPException) as ei:
                await get_attachment_links(attachment_id=att.id, db=s, current_user=user)
            assert ei.value.status_code == 404
        finally:
            await ctx.__aexit__()

    async def test_links_cross_project_404(self):
        """跨项目：附件绑定 A 项目底稿，用户仅 B 项目 lead → 404（Req 3.4 cross-project）。"""
        from app.routers.attachment_lineage import get_attachment_links

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj_a, _lead_a, _wi_a, wp_a = await _lead_scenario(s)
            att_a = await _mk_attachment(s, proj_a.id)
            await _link_att_wp(s, att_a.id, wp_a.id)
            # 另一个项目的 lead（对 A 无任何访问）
            _proj_b, lead_b, _wi_b, _wp_b = await _lead_scenario(s)
            with pytest.raises(HTTPException) as ei:
                await get_attachment_links(attachment_id=att_a.id, db=s, current_user=lead_b)
            assert ei.value.status_code == 404
        finally:
            await ctx.__aexit__()

    async def test_unlinked_attachment_passthrough_additive(self):
        """未绑定底稿的附件 → 放行(additive passthrough)，不越界收紧项目级证据（Req 3.4 边界）。"""
        from app.routers.attachment_lineage import get_attachment_links

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, _wi, _wp = await _lead_scenario(s)
            att = await _mk_attachment(s, proj.id)  # 未创建 AttachmentWorkingPaper 关联
            outsider = await mk_user(s)  # 甚至非项目成员
            res = await get_attachment_links(attachment_id=att.id, db=s, current_user=outsider)
            assert res is not None  # passthrough：不因 wp 可见性收紧未绑定底稿的附件
        finally:
            await ctx.__aexit__()

    async def test_attachment_workpapers_deny_outsider_404(self):
        """process_record 附件→底稿清单：越权成员 → 404（Req 3.4 deny）。"""
        from app.routers.process_record import get_attachment_workpapers

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, _wi, wp = await _lead_scenario(s)
            att = await _mk_attachment(s, proj.id)
            await _link_att_wp(s, att.id, wp.id)
            outsider = await mk_user(s)
            await mk_project_user(s, proj.id, outsider.id, scope_cycles="")
            await s.flush()
            with pytest.raises(HTTPException) as ei:
                await get_attachment_workpapers(attachment_id=att.id, db=s, current_user=outsider)
            assert ei.value.status_code == 404
        finally:
            await ctx.__aexit__()

    async def test_ocr_fields_deny_outsider_404_before_service(self):
        """ocr-fields：越权成员在 gate 处即 404（先于 OCR 服务，Req 3.4 deny）。"""
        from app.routers.ocr_fields import extract_ocr_fields

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, _wi, wp = await _lead_scenario(s)
            att = await _mk_attachment(s, proj.id)
            await _link_att_wp(s, att.id, wp.id)
            outsider = await mk_user(s)
            await mk_project_user(s, proj.id, outsider.id, scope_cycles="")
            await s.flush()
            with pytest.raises(HTTPException) as ei:
                await extract_ocr_fields(attachment_id=att.id, db=s, current_user=outsider)
            assert ei.value.status_code == 404
        finally:
            await ctx.__aexit__()


# ===========================================================================
# E. 新接门批量路由真实隔离 + bulk-preflight 原子性（Req 3.3/3.4） —
#    真实 FastAPI handler + 真实 PostgreSQL；每用例事务隔离回滚。
#    覆盖原 13 条 leak_risk 的两类接门语义：
#      · make_bulk_preflight（import/write，原子）：batch_prefill / bulk_import_rollback
#      · make_bulk_visible_filter（export/search 可见集过滤）：search_workpapers
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (real gate integration)")
@pytest.mark.asyncio
class TestNewlyGatedBulkRoutes:
    # ── batch_prefill：make_bulk_preflight（save_parsed_data 写族，原子）──
    async def test_batch_prefill_allows_delegated_lead(self):
        """委派 lead 对底稿可写 → batch_prefill preflight 放行（Req 3.4 allow）。"""
        from app.routers.wp_batch_ops import BatchPrefillRequest, batch_prefill

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, lead, _wi, wp = await _lead_scenario(s)
            res = await batch_prefill(
                project_id=proj.id,
                body=BatchPrefillRequest(wp_ids=[wp.id]),
                db=s,
                current_user=lead,
            )
            assert res.total == 1  # 放行（preflight 通过，无 404）
        finally:
            await ctx.__aexit__()

    async def test_batch_prefill_deny_outsider_404(self):
        """越权成员(scope_cycles 空)→ batch_prefill preflight 于副作用前 404（Req 3.4 deny）。"""
        from app.routers.wp_batch_ops import BatchPrefillRequest, batch_prefill

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, _wi, wp = await _lead_scenario(s)
            outsider = await mk_user(s)
            await mk_project_user(s, proj.id, outsider.id, scope_cycles="")
            await s.flush()
            with pytest.raises(HTTPException) as ei:
                await batch_prefill(
                    project_id=proj.id,
                    body=BatchPrefillRequest(wp_ids=[wp.id]),
                    db=s,
                    current_user=outsider,
                )
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        finally:
            await ctx.__aexit__()

    async def test_batch_prefill_cross_project_404(self):
        """跨项目：底稿属 A 项目，用户仅 B 项目 lead → 404（Req 3.4 cross-project）。"""
        from app.routers.wp_batch_ops import BatchPrefillRequest, batch_prefill

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj_a, _lead_a, _wi_a, wp_a = await _lead_scenario(s)
            _proj_b, lead_b, _wi_b, _wp_b = await _lead_scenario(s)
            with pytest.raises(HTTPException) as ei:
                await batch_prefill(
                    project_id=proj_a.id,
                    body=BatchPrefillRequest(wp_ids=[wp_a.id]),
                    db=s,
                    current_user=lead_b,
                )
            assert ei.value.status_code == 404
        finally:
            await ctx.__aexit__()

    async def test_batch_prefill_atomic_mixed_visible_invisible_404(self):
        """bulk-preflight 原子性：可见+不可见混合 → 整请求 404 于任何预填副作用前（Req 3.4 原子）。"""
        from app.routers.wp_batch_ops import BatchPrefillRequest, batch_prefill

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            # lead 委派循环 D；wp_a 循环 D（可见），wp_b 循环 F（越 scope 上界 → 不可见）。
            proj, lead, _wi_a, wp_a = await _lead_scenario(s, scope="D", cycle="D")
            wi_b = await mk_wp_index(s, proj.id, wp_code="F1-1", audit_cycle="F")
            wp_b = await mk_working_paper(s, proj.id, wi_b.id)
            await s.flush()
            with pytest.raises(HTTPException) as ei:
                await batch_prefill(
                    project_id=proj.id,
                    body=BatchPrefillRequest(wp_ids=[wp_a.id, wp_b.id]),
                    db=s,
                    current_user=lead,
                )
            # 任一不可见 → 整请求 404（preflight 循环于 wp_b 处拒绝，先于任何预填）。
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        finally:
            await ctx.__aexit__()

    # ── bulk_import_rollback：make_bulk_preflight（原子，先于 SnapshotGuard.rollback）──
    async def test_rollback_atomic_denies_before_snapshot_restore(self):
        """回滚原子性：混合可见/不可见 → 404 于 SnapshotGuard.rollback 之前（Req 3.4 原子）。

        断言得到干净的 ExternalNotFound(404)（而非伪造 snapshot_id 还原触发的其它异常）
        即证明 preflight 在任何还原副作用前短路——原子失败。
        """
        from app.routers.wp_bulk_router import RollbackRequest, bulk_import_rollback

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, lead, _wi_a, wp_a = await _lead_scenario(s, scope="D", cycle="D")
            wi_b = await mk_wp_index(s, proj.id, wp_code="F1-1", audit_cycle="F")
            wp_b = await mk_working_paper(s, proj.id, wi_b.id)
            await s.flush()
            body = RollbackRequest(
                import_id="imp-x",
                snapshots=[
                    {"wp_id": str(wp_a.id), "snapshot_id": str(uuid.uuid4())},
                    {"wp_id": str(wp_b.id), "snapshot_id": str(uuid.uuid4())},
                ],
            )
            with pytest.raises(HTTPException) as ei:
                await bulk_import_rollback(
                    project_id=proj.id, body=body, current_user=lead, db=s
                )
            assert ei.value.status_code == 404
            assert ei.value.detail == EXTERNAL_NOT_FOUND_DETAIL
        finally:
            await ctx.__aexit__()

    async def test_rollback_deny_outsider_404(self):
        """越权成员回滚 → preflight 于还原副作用前 404（Req 3.4 deny）。"""
        from app.routers.wp_bulk_router import RollbackRequest, bulk_import_rollback

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, _wi, wp = await _lead_scenario(s)
            outsider = await mk_user(s)
            await mk_project_user(s, proj.id, outsider.id, scope_cycles="")
            await s.flush()
            body = RollbackRequest(
                import_id="imp-y",
                snapshots=[{"wp_id": str(wp.id), "snapshot_id": str(uuid.uuid4())}],
            )
            with pytest.raises(HTTPException) as ei:
                await bulk_import_rollback(
                    project_id=proj.id, body=body, current_user=outsider, db=s
                )
            assert ei.value.status_code == 404
        finally:
            await ctx.__aexit__()

    # ── search_workpapers：make_bulk_visible_filter（可见集过滤，无跨 scope 标题泄露）──
    async def test_search_returns_workpaper_for_delegated_lead(self):
        """委派 lead 搜索命中其可见底稿（Req 3.4 allow）。"""
        from app.routers.wp_search import search_workpapers

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, lead, _wi, _wp = await _lead_scenario(s)  # wp_code D2-1, cycle D
            res = await search_workpapers(
                project_id=proj.id, q="D2-1", scope="content",
                limit=50, db=s, current_user=lead,
            )
            wp_hits = [r for r in res["results"] if r["source"] == "workpaper"]
            assert wp_hits, "委派 lead 应能搜索到其可见底稿"
        finally:
            await ctx.__aexit__()

    async def test_search_filters_invisible_workpaper_titles_for_outsider(self):
        """越权成员搜索：不可见底稿标题/编码被静默过滤（无跨 scope 标题泄露，Req 3.4 deny）。"""
        from app.routers.wp_search import search_workpapers

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, _lead, _wi, _wp = await _lead_scenario(s)  # wp_code D2-1
            outsider = await mk_user(s)
            await mk_project_user(s, proj.id, outsider.id, scope_cycles="")
            await s.flush()
            res = await search_workpapers(
                project_id=proj.id, q="D2-1", scope="content",
                limit=50, db=s, current_user=outsider,
            )
            wp_hits = [r for r in res["results"] if r["source"] == "workpaper"]
            assert wp_hits == [], "不可见底稿标题不得经搜索泄露"
        finally:
            await ctx.__aexit__()

    async def test_search_cross_project_workpaper_not_leaked(self):
        """跨项目：B 项目 lead 搜索 A 项目 → 不返回 A 的底稿标题（Req 3.4 cross-project）。"""
        from app.routers.wp_search import search_workpapers

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj_a, _lead_a, _wi_a, _wp_a = await _lead_scenario(s)  # A 项目 D2-1
            _proj_b, lead_b, _wi_b, _wp_b = await _lead_scenario(s)
            res = await search_workpapers(
                project_id=proj_a.id, q="D2-1", scope="content",
                limit=50, db=s, current_user=lead_b,
            )
            wp_hits = [r for r in res["results"] if r["source"] == "workpaper"]
            assert wp_hits == [], "跨项目底稿标题不得泄露"
        finally:
            await ctx.__aexit__()
