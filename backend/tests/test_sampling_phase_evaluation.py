"""两阶段合并评价（spec voucher-identity-writeback-and-audit-phase 任务 16，需求 7.5 / 7.6，ADR-VK-10）

- 纯函数 ``combine``：口径 a / b 各一组固定数；口径 b 只用预审样本实际错报合计 E、不碰预审推断错报；可容忍错报
  缺省或为 0 → 不给全年结论；错报上限等于可容忍错报算可以接受。
- ``phase_evaluation``（SQLite 真 ORM 行）：预审缺 E / 预审未评价 / 年审未评价都不给结果并说明原因；只算年审批次
  之前、未撤销、本底稿的预审批次；科目范围不一致注明「仅供参考」；预审手工挂凭注明未计入；预审批次、没有口径的
  年审批次、找不到的批次 → 不适用（applicable=False，界面不显示）。
- ``_normalize_evaluation``：旧载荷输出键不变（逐字节）；E 归一到分；不可解析 / 非有限 / 负数不写；客户端 combined 丢弃。
- 端点：POST /voucher-evaluation 给年审批次写服务端现算的 combined（客户端传的不收）并投影到抽样记录结论；预审批次
  保存 E、不写 combined；预审缺 E 时年审批次不写 combined。``attach_combined``（回填随带评价那条路径）同样写。
  回填端点本身（PG 的 gen_random_uuid 主键）的真实请求在 test_sampling_phase_pg.py。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import WorkpaperExtractionLog
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.workpaper_models import (
    SampledVoucher,
    SamplingRecord,
    WorkingPaper,
    WpIndex,
    WpSourceType,
    WpStatus,
)
from app.routers.voucher_sampling import _normalize_evaluation
from app.services.sampling_phase_evaluation import (
    MISSING_E_MESSAGE,
    attach_combined,
    combine,
    phase_evaluation,
)
from app.services.sampling_registry_service import build_conclusion_supplements

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

D = Decimal
EDITOR = uuid.uuid4()
PROJECT = uuid.uuid4()
WP, WP_OTHER = uuid.uuid4(), uuid.uuid4()
T0 = datetime(2025, 7, 10, 9, 0, 0)


def _iv(p=None, u=None, e=None) -> dict:
    return {"projected": None if p is None else D(p), "upper_limit": None if u is None else D(u),
            "sample_error_total": None if e is None else D(e)}


# ─── combine：两公式各一组固定数 ──────────────────────────────────────────────


class TestCombine:
    FINAL = {"projected": D("1000"), "upper_limit": D("2500"), "tolerable_misstatement": D("5000")}

    def test_mode_a_sums_interim_projected_and_upper(self):
        out = combine("remaining", [_iv(100, 300, 999), _iv(50, 150, 999)], self.FINAL)
        assert (out["interim_component"], out["interim_upper_component"]) == ("150.00", "450.00")
        assert (out["projected"], out["upper_limit"], out["conclusion_code"]) == ("1150.00", "2950.00", "acceptable")
        assert out["interim_batch_count"] == 2 and out["final_projected"] == "1000.00"

    def test_mode_b_uses_actual_error_not_interim_projection(self):
        # 预审推断错报 / 上限故意给大数：口径 b 一旦改成加预审推断，结果与结论都会变
        out = combine("full_minus_interim", [_iv(5000, 9000, 80), _iv(7000, 9000, 20)],
                      {**self.FINAL, "tolerable_misstatement": D("2600")})
        assert (out["interim_component"], out["interim_upper_component"]) == ("100.00", "100.00")
        assert (out["projected"], out["upper_limit"], out["conclusion_code"]) == ("1100.00", "2600.00", "acceptable")
        assert "预审样本实际错报 100.00" in out["conclusion_message"]

    def test_upper_above_tolerable_not_acceptable(self):
        out = combine("full_minus_interim", [_iv(e=80)], {**self.FINAL, "tolerable_misstatement": D("2579.99")})
        assert (out["upper_limit"], out["conclusion_code"]) == ("2580.00", "not_acceptable")
        assert "超过可容忍错报 2579.99 元，不可接受" in out["conclusion_message"]

    @pytest.mark.parametrize("tol", [None, D("0")])
    def test_missing_tolerable_undetermined(self, tol):
        out = combine("remaining", [_iv(1, 2)], {**self.FINAL, "tolerable_misstatement": tol})
        assert out["conclusion_code"] == "undetermined" and "未填可容忍错报" in out["conclusion_message"]


# ─── _normalize_evaluation：E 字段与旧记录逐字节不变 ───────────────────────────

OLD_KEYS = [
    "projected", "known_high_value", "basic_precision", "incremental_allowance", "upper_limit",
    "tolerable_misstatement", "checked_sample_count", "unchecked_sample_count", "deviation_count",
    "conclusion_message", "algo_version", "coverage_threshold", "coverage_threshold_source",
    "unchecked_disposition", "deviation_nature_summary", "stratified_evaluation", "reconcile_override_reason",
    "reconcile_override_by", "reconcile_override_at", "conclusion_code", "conclusion_confirmed",
    "a13_pushed_at", "a13_misstatement_id", "evaluated_at", "evaluated_by",
]


class TestNormalizeSampleErrorTotal:
    def test_old_payload_keys_unchanged(self):
        out = _normalize_evaluation({"projected": "1000", "upper_limit": "2500"}, actor_id=EDITOR)
        assert list(out) == OLD_KEYS

    def test_quantized_to_cent(self):
        assert _normalize_evaluation({"sample_error_total": "80.456"}, actor_id=EDITOR)["sample_error_total"] == "80.46"
        assert _normalize_evaluation({"sample_error_total": 0}, actor_id=EDITOR)["sample_error_total"] == "0.00"

    @pytest.mark.parametrize("bad", ["abc", "NaN", "Infinity", "-0.01", {}, [1]])
    def test_invalid_not_written(self, bad):
        assert "sample_error_total" not in _normalize_evaluation({"sample_error_total": bad}, actor_id=EDITOR)

    def test_client_combined_dropped(self):
        out = _normalize_evaluation({"combined": {"projected": "1.00", "conclusion_message": "伪造"}}, actor_id=EDITOR)
        assert "combined" not in out


def test_supplement_line_only_when_combined_present():
    assert build_conclusion_supplements({}) == []
    assert build_conclusion_supplements({"combined": {"conclusion_message": "全年合并（…）"}}) == ["【全年合并评价】全年合并（…）"]


# ─── 数据库：SQLite 真 ORM 行 ─────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=EDITOR, username="editor", email="editor@test.com", hashed_password="x", role="auditor"))
        session.add(Project(id=PROJECT, name="合并评价测试", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=EDITOR))
        session.add(ProjectUser(project_id=PROJECT, user_id=EDITOR, role="auditor", permission_level="edit",
                                is_deleted=False))
        for wp_id, code in ((WP, "J1-2"), (WP_OTHER, "E1-23")):
            idx = WpIndex(id=uuid.uuid4(), project_id=PROJECT, wp_code=code, wp_name=f"{code} 底稿",
                          status=WpStatus.not_started)
            session.add(idx)
            session.add(WorkingPaper(id=wp_id, project_id=PROJECT, wp_index_id=idx.id, file_path=f"{code}.xlsx",
                                     source_type=WpSourceType.template, file_version=1))
        await session.commit()
        yield session
    await engine.dispose()


def _ev(p, u, *, e=None, tol=None) -> dict:
    ev = {"projected": p, "upper_limit": u, "conclusion_code": "undetermined"}
    if e is not None:
        ev["sample_error_total"] = e
    if tol is not None:
        ev["tolerable_misstatement"] = tol
    return ev


async def _log(db, *, phase, minutes, mode=None, evaluation=None, codes=("2241",), wp=WP, undone=False, record=False):
    crit = {"phase": phase, "filters": {"account_codes": list(codes)}}
    if mode:
        crit["final_population_mode"] = mode
    if evaluation is not None:
        crit["evaluation"] = evaluation
    log = WorkpaperExtractionLog(
        id=uuid.uuid4(), project_id=PROJECT, workpaper_id=wp, user_id=EDITOR, extraction_type="voucher_sampling",
        extraction_criteria=crit, total_matched=100, filled_count=3, fill_mode="append", batch_id=uuid.uuid4(),
        is_undone=undone, status="undone" if undone else "filled",
        created_at=T0.replace(minute=minutes),
    )
    db.add(log)
    if record:
        db.add(SamplingRecord(project_id=PROJECT, working_paper_id=wp, sampling_purpose="测试", population_description="测试",
                              sample_size=3, batch_id=log.batch_id, conclusion="原结论"))
    await db.flush()
    return log


async def _pe(db, **kw):
    return await phase_evaluation(db, project_id=PROJECT, workpaper_id=WP, **kw)


class TestPhaseEvaluation:
    async def test_mode_b_full_flow(self, db):
        await _log(db, phase="preliminary", minutes=1, evaluation=_ev("5000", "9000", e="80"))
        await _log(db, phase="preliminary", minutes=2, evaluation=_ev("7000", "9000", e="20"))
        final = await _log(db, phase="final", minutes=5, mode="full_minus_interim",
                           evaluation=_ev("1000", "2500", tol="5000"))
        out = await _pe(db)
        assert out["available"] and out["applicable"] and out["final_log_id"] == str(final.id)
        c = out["combined"]
        assert (c["projected"], c["upper_limit"], c["conclusion_code"]) == ("1100.00", "2600.00", "acceptable")
        assert c["scope_consistent"] is True and c["notes"] == [] and c["interim_batch_count"] == 2
        assert [i["sample_error_total"] for i in out["interim"]] == ["80.00", "20.00"]
        assert [i["seq"] for i in out["interim"]] == [1, 2]

    async def test_mode_a_full_flow(self, db):
        await _log(db, phase="preliminary", minutes=1, evaluation=_ev("100", "300"))
        await _log(db, phase="preliminary", minutes=2, evaluation=_ev("50", "150"))
        await _log(db, phase="final", minutes=5, mode="remaining", evaluation=_ev("1000", "2500", tol="2900"))
        c = (await _pe(db))["combined"]
        assert (c["projected"], c["upper_limit"], c["conclusion_code"]) == ("1150.00", "2950.00", "not_acceptable")

    async def test_missing_e_refused_not_zero(self, db):
        await _log(db, phase="preliminary", minutes=1, evaluation=_ev("100", "300", e="10"))
        second = await _log(db, phase="preliminary", minutes=2, evaluation=_ev("100", "300"))  # 本功能上线前保存的评价
        await _log(db, phase="final", minutes=5, mode="full_minus_interim", evaluation=_ev("1000", "2500", tol="5000"))
        out = await _pe(db)
        assert out["available"] is False and out["applicable"] is True
        assert out["reason_code"] == "missing_sample_error_total" and MISSING_E_MESSAGE in out["reason"]
        assert out["reason"].startswith("第 2 个") and out["missing_log_id"] == str(second.id)
        assert "combined" not in out

    @pytest.mark.parametrize("mode,need", [("full_minus_interim", "样本实际错报合计"), ("remaining", "推断错报与错报上限")])
    async def test_interim_not_evaluated(self, db, mode, need):
        await _log(db, phase="preliminary", minutes=1)
        await _log(db, phase="final", minutes=5, mode=mode, evaluation=_ev("1000", "2500"))
        out = await _pe(db)
        assert (out["available"], out["reason_code"]) == (False, "interim_not_evaluated") and need in out["reason"]

    async def test_final_not_evaluated(self, db):
        await _log(db, phase="preliminary", minutes=1, evaluation=_ev("1", "2", e="1"))
        await _log(db, phase="final", minutes=5, mode="full_minus_interim")
        out = await _pe(db)
        assert (out["available"], out["applicable"], out["reason_code"]) == (False, True, "final_not_evaluated")

    async def test_only_earlier_live_same_workpaper_interim_batches(self, db):
        await _log(db, phase="preliminary", minutes=1, evaluation=_ev("1", "2", e="80"))
        await _log(db, phase="preliminary", minutes=2, evaluation=_ev("1", "2", e="1000"), undone=True)
        await _log(db, phase="preliminary", minutes=3, evaluation=_ev("1", "2", e="2000"), wp=WP_OTHER)
        await _log(db, phase="final", minutes=5, mode="full_minus_interim", evaluation=_ev("1000", "2500"))
        await _log(db, phase="preliminary", minutes=7, evaluation=_ev("1", "2", e="3000"))  # 年审批次之后抽的
        c = (await _pe(db))["combined"]
        assert (c["interim_component"], c["interim_batch_count"]) == ("80.00", 1)

    async def test_scope_mismatch_and_manual_attach_notes(self, db):
        await _log(db, phase="preliminary", minutes=1, evaluation=_ev("1", "2", e="80"), codes=("2241", "2202"))
        await _log(db, phase="final", minutes=5, mode="full_minus_interim", evaluation=_ev("1000", "2500"))
        db.add(SampledVoucher(project_id=PROJECT, year=2025, voucher_no="0004", working_paper_id=WP, phase="preliminary"))
        db.add(SampledVoucher(project_id=PROJECT, year=2025, voucher_no="0005", working_paper_id=WP, phase="final"))
        await db.flush()
        c = (await _pe(db))["combined"]
        assert c["scope_consistent"] is False
        assert c["notes"] == ["两阶段科目范围不一致，全年合并结果仅供参考",
                              "另有预审手工挂凭 1 张：其核对结果不在抽样评价里，未计入合并"]
        assert c["conclusion_message"].endswith("（两阶段科目范围不一致，全年合并结果仅供参考；另有预审手工挂凭 1 张：其核对结果不在抽样评价里，未计入合并）")

    async def test_not_applicable_cases(self, db):
        assert (await _pe(db))["reason_code"] == "no_final_batch"
        pre = await _log(db, phase="preliminary", minutes=1, evaluation=_ev("1", "2", e="1"))
        no_mode = await _log(db, phase="final", minutes=5, evaluation=_ev("1000", "2500"))
        for kw, code in (({}, "no_final_batch"), ({"log_id": pre.id}, "not_final_batch"),
                         ({"log_id": no_mode.id}, "no_mode"), ({"log_id": uuid.uuid4()}, "batch_not_found")):
            out = await _pe(db, **kw)
            assert (out["available"], out["applicable"], out["reason_code"]) == (False, False, code), kw

    async def test_explicit_final_evaluation_overrides_stored(self, db):
        await _log(db, phase="preliminary", minutes=1, evaluation=_ev("1", "2", e="80"))
        final = await _log(db, phase="final", minutes=5, mode="full_minus_interim", evaluation=_ev("1000", "2500"))
        out = await _pe(db, log_id=final.id, final_evaluation=_ev("10", "20"))
        assert (out["combined"]["projected"], out["combined"]["upper_limit"]) == ("90.00", "100.00")


class TestAttachCombined:
    async def test_final_log_gets_combined_as_new_dict(self, db):
        await _log(db, phase="preliminary", minutes=1, evaluation=_ev("1", "2", e="80"))
        final = await _log(db, phase="final", minutes=5, mode="full_minus_interim", evaluation=_ev("1000", "2500"))
        before = final.extraction_criteria
        await attach_combined(db, project_id=PROJECT, log=final)
        assert final.extraction_criteria is not before  # JSONB 整体赋新 dict 才会被写库
        assert final.extraction_criteria["evaluation"]["combined"]["projected"] == "1080.00"
        assert final.extraction_criteria["filters"] == before["filters"]

    async def test_other_logs_untouched(self, db):
        pre = await _log(db, phase="preliminary", minutes=1, evaluation=_ev("1", "2"))  # 缺 E
        no_eval = await _log(db, phase="final", minutes=5, mode="full_minus_interim")
        refused = await _log(db, phase="final", minutes=6, mode="full_minus_interim", evaluation=_ev("1000", "2500"))
        for log in (pre, no_eval, refused):
            before = log.extraction_criteria
            await attach_combined(db, project_id=PROJECT, log=log)
            assert log.extraction_criteria is before and "combined" not in (before.get("evaluation") or {})


# ─── 端点：POST /voucher-evaluation 与 GET /phase-evaluation ────────────────────


@pytest_asyncio.fixture
async def client(db):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import sampling_phase, voucher_sampling

    class _User:
        id = EDITOR

        class _Role:
            value = "auditor"

        role = _Role()

    async def _db():
        yield db

    async def _user():
        return _User()

    app = FastAPI()
    app.include_router(voucher_sampling.router)
    app.include_router(sampling_phase.router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _save(client, log_id, evaluation):
    resp = await client.post(f"/api/projects/{PROJECT}/sampling/voucher-evaluation",
                             json={"workpaper_id": str(WP), "log_id": str(log_id), "evaluation": evaluation})
    assert resp.status_code == 200, resp.text
    return resp.json()["evaluation"]


async def _stored(db, log_id) -> dict:
    db.expire_all()  # 读库里的值，不读会话里的对象（调用方传 id：expire 之后再读对象属性会触发惰性加载）
    crit = (await db.execute(sa.select(WorkpaperExtractionLog.extraction_criteria).where(
        WorkpaperExtractionLog.id == log_id))).scalar_one()
    return (json.loads(crit) if isinstance(crit, str) else crit)["evaluation"]


def _ids(log) -> tuple[uuid.UUID, uuid.UUID]:
    return log.id, log.batch_id


async def _conclusion(db, batch_id) -> str | None:
    return (await db.execute(sa.select(SamplingRecord.conclusion).where(
        SamplingRecord.batch_id == batch_id))).scalar_one()


class TestEndpoints:
    async def test_interim_saves_e_final_gets_server_combined(self, client, db):
        pre, pre_batch = _ids(await _log(db, phase="preliminary", minutes=1, record=True))
        final, final_batch = _ids(await _log(db, phase="final", minutes=5, mode="full_minus_interim", record=True))
        await db.commit()

        saved = await _save(client, pre, {**_ev("5000", "9000", e="80.456"), "combined": {"projected": "1"}})
        assert saved["sample_error_total"] == "80.46" and "combined" not in saved
        assert "【全年合并评价】" not in (await _conclusion(db, pre_batch) or "")

        bogus = {"projected": "1.00", "upper_limit": "1.00", "conclusion_message": "伪造"}
        saved = await _save(client, final, {**_ev("1000", "2500", tol="5000"), "conclusion_message": "年审结论",
                                            "combined": bogus})
        stored = await _stored(db, final)
        assert stored["combined"] == saved["combined"]
        assert (stored["combined"]["projected"], stored["combined"]["upper_limit"]) == ("1080.46", "2580.46")
        assert stored["combined"]["conclusion_code"] == "acceptable"
        conclusion = await _conclusion(db, final_batch)
        assert conclusion.startswith("年审结论\n【全年合并评价】全年合并（口径 b 全年扣除预审已检样本）：")
        assert "2580.46" in conclusion and "伪造" not in conclusion

        view = (await client.get(f"/api/projects/{PROJECT}/sampling/phase-evaluation",
                                 params={"wp_id": str(WP)})).json()
        assert view["available"] and view["combined"] == stored["combined"]

    async def test_final_without_interim_e_not_written(self, client, db):
        pre, _ = _ids(await _log(db, phase="preliminary", minutes=1, evaluation=_ev("100", "300")))
        final, final_batch = _ids(await _log(db, phase="final", minutes=5, mode="full_minus_interim", record=True))
        await db.commit()
        saved = await _save(client, final, _ev("1000", "2500", tol="5000"))
        assert "combined" not in saved and "combined" not in await _stored(db, final)
        assert "【全年合并评价】" not in (await _conclusion(db, final_batch) or "")
        view = (await client.get(f"/api/projects/{PROJECT}/sampling/phase-evaluation",
                                 params={"wp_id": str(WP), "log_id": str(final)})).json()
        assert (view["available"], view["reason_code"], view["missing_log_id"]) == (
            False, "missing_sample_error_total", str(pre))

    async def test_phase_evaluation_requires_workpaper_in_project(self, client):
        resp = await client.get(f"/api/projects/{uuid.uuid4()}/sampling/phase-evaluation", params={"wp_id": str(WP)})
        assert resp.status_code == 403
