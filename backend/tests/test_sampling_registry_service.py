"""抽样登记服务守卫（sampling-compliance-closure Wave 2 Task 16）

背景：`sampling_records` 0 行 / `sampled_vouchers` 1 行（唯一写入点是穿透页手工标记），
而这两张表的字段正是 CAS 1314 要求的记录项。本轮把它们接成 canonical 留痕的
**可查询侧投影**（权威仍是 `workpaper_extraction_log.extraction_criteria`）。

Validates: Requirements 5.1, 5.2, 5.4, 5.5, 5.6, 5.8
Properties: Property 11, Property 12, Property 14
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa

from app.services import sampling_registry_service as reg

_BACKEND = Path(__file__).resolve().parent.parent
_APP = _BACKEND / "app"
_MIGRATION = _BACKEND / "migrations" / "V139__sampling_registry_batch_binding.sql"


def _strip_comments(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return re.sub(r"(?m)#.*$", "", src)


def _func_body(src: str, name: str) -> str:
    """截取顶层函数体：从 `[async ]def name(` 到下一个顶层 `def`/`class`。

    禁用「固定字符窗口」截取（平台踩过：窗口溢出到下一个函数导致假绿/假红）。
    """
    m = re.search(rf"(?m)^(?:async\s+)?def\s+{re.escape(name)}\s*\(", src)
    if not m:
        return ""
    rest = src[m.end() :]
    nxt = re.search(r"(?m)^(?:async\s+)?def\s|^class\s", rest)
    return rest[: nxt.start()] if nxt else rest


def _criteria(**over) -> dict:
    base = {
        "sampling_method": "mus",
        "phase": "final",
        "random_seed": 424242,
        "dataset_id": "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49",
        "sampling_interval": "50000.00",
        "algo_version": "cas1314-poisson-v1",
        "filled_voucher_nos": ["V-001", "V-002"],
        "filters": {
            "account_codes": ["1122"],
            "period_range": [1, 12],
            "amount_min": 1000,
            "direction_filter": "debit",
            "summary_keyword": "退货",
        },
        "coverage_stats": {"population_amount": "1000000.00"},
        "evaluation": {
            "deviation_count": 3,
            "projected": "1234.56",
            "upper_limit": "2334.56",
            "known_high_value": "200.00",
            "conclusion_message": "总体可接受",
        },
    }
    base.update(over)
    return base


# ─── 纯函数：留痕 → 记录表字段映射 ────────────────────────────────────────────


class TestFieldMapping:
    def test_population_description_renders_all_conditions(self):
        text = reg.build_population_description(_criteria())
        for token in ("序时账", "1122", "金额 ≥ 1000", "仅借方", "退货"):
            assert token in text

    def test_population_description_never_empty(self):
        """无过滤条件时返回明确文字而非空串 —— 空串在归档核对时无法与"渲染失败"区分。"""
        text = reg.build_population_description({})
        assert text
        assert "未记录" in text

    def test_full_year_vs_partial_periods(self):
        full = reg.build_population_description(
            {"filters": {"period_range": list(range(1, 13))}}
        )
        assert "全年度" in full
        partial = reg.build_population_description({"filters": {"period_range": [1, 12]}})
        assert "1、12" in partial and "全年度" not in partial

    def test_amount_range_three_forms(self):
        f = lambda **kw: reg.build_population_description({"filters": kw})  # noqa: E731
        assert "金额 1000~5000" in f(amount_min=1000, amount_max=5000)
        assert "金额 ≥ 1000" in f(amount_min=1000)
        assert "金额 ≤ 5000" in f(amount_max=5000)

    def test_sampling_purpose_includes_method_phase_and_resample_reason(self):
        text = reg.build_sampling_purpose(_criteria(resample_reason="样本代表性不足"))
        assert "货币单元抽样" in text
        assert "年审" in text
        assert "样本代表性不足" in text

    def test_method_description_records_sample_size_basis(self):
        """CAS 1314 要求记录样本量确定依据 → 置信度/可容忍错报/间隔/种子/算法版本齐备。"""
        text = reg.build_method_description(
            _criteria(confidence_level=0.95, tolerable_misstatement="500000",
                      suggested_sample_size=27)
        )
        for token in ("置信度=0.95", "可容忍错报=500000", "系统建议样本量=27",
                      "抽样间隔=50000.00", "随机种子=424242", "算法版本="):
            assert token in text

    def test_record_fields_projection(self):
        f = reg.build_record_fields(criteria=_criteria(), total_matched=500, filled_count=25)
        assert f["sample_size"] == 25
        assert f["population_total_count"] == 500
        assert f["population_total_amount"] == Decimal("1000000.00")
        assert f["sampling_method"] == "mus"
        assert f["random_seed"] == 424242
        assert isinstance(f["dataset_id"], UUID)
        assert f["deviations_found"] == 3
        assert f["projected_misstatement"] == Decimal("1234.56")
        assert f["upper_misstatement_limit"] == Decimal("2334.56")
        assert f["misstatements_found"] == Decimal("200.00")
        assert f["conclusion"] == "总体可接受"

    def test_missing_evaluation_yields_none_not_zero(self):
        """未评价的批次：错报字段必须是 None 而非 0 —— 「没评价」与「评价为 0」不同。"""
        f = reg.build_record_fields(
            criteria=_criteria(evaluation=None), total_matched=10, filled_count=5
        )
        assert f["projected_misstatement"] is None
        assert f["upper_misstatement_limit"] is None
        assert f["deviations_found"] is None

    def test_unparseable_amounts_yield_none(self):
        f = reg.build_record_fields(
            criteria=_criteria(evaluation={"projected": "abc", "upper_limit": ""}),
            total_matched=1, filled_count=1,
        )
        assert f["projected_misstatement"] is None
        assert f["upper_misstatement_limit"] is None

    def test_invalid_dataset_id_yields_none(self):
        f = reg.build_record_fields(
            criteria=_criteria(dataset_id="not-a-uuid"), total_matched=1, filled_count=1
        )
        assert f["dataset_id"] is None


# ─── Property 12：fail-open 必留 WARNING ─────────────────────────────────────


class _BoomDB:
    """任何 execute/flush 都抛异常的替身，用于验证 fail-open 行为。"""

    async def execute(self, *a, **k):
        raise RuntimeError("boom")

    async def flush(self):
        raise RuntimeError("boom")

    def add(self, *a, **k):
        raise RuntimeError("boom")


class TestFailOpenLeavesWarning:
    def _log(self):
        return SimpleNamespace(
            project_id=uuid4(),
            workpaper_id=uuid4(),
            batch_id=uuid4(),
            user_id=uuid4(),
            extraction_criteria=_criteria(),
            total_matched=100,
            filled_count=2,
        )

    def test_register_batch_fail_open_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            got = asyncio.run(
                reg.register_sampling_batch(_BoomDB(), log=self._log(), created_by=uuid4())
            )
        assert got is None
        assert any(r.levelno >= logging.WARNING for r in caplog.records), (
            "fail-open 必须留 WARNING，否则投影失败变成静默黑洞"
        )

    def test_register_vouchers_fail_open_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            got = asyncio.run(
                reg.register_sampled_vouchers(_BoomDB(), log=self._log(), year=2025)
            )
        assert got == 0
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_update_evaluation_fail_open_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            got = asyncio.run(
                reg.update_sampling_record_evaluation(
                    _BoomDB(), batch_id=uuid4(), evaluation={"projected": "1.00"}
                )
            )
        assert got is False
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_no_voucher_nos_is_noop_without_warning(self, caplog):
        """本批次没有回填凭证号 → 直接返回 0，不算异常、不留 WARNING。"""
        log = self._log()
        log.extraction_criteria = _criteria(filled_voucher_nos=[])
        with caplog.at_level(logging.WARNING):
            got = asyncio.run(reg.register_sampled_vouchers(_BoomDB(), log=log, year=2025))
        assert got == 0
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_project_level_exclusion_fail_open_with_warning(self, caplog):
        """R5.5 的排除来源同样 fail-open —— 它读的是投影表且 `batch_id` 是 V139 新列，
        未应用迁移的环境下若不 fail-open 会把整个 `/voucher-extract` 打成 500，
        审计师一选「全项目排除」就完全无法抽样。降级为「不排除」不掩盖重复抽凭：
        `cross_workpaper_duplicate_vouchers` 是独立检测，仍会在预览前弹窗。
        """
        with caplog.at_level(logging.WARNING):
            got = asyncio.run(
                reg.project_level_extracted_voucher_nos(_BoomDB(), uuid4(), 2025)
            )
        assert got == []
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_all_task13_entrypoints_are_fail_open(self):
        """源码级：Task 13 声明的四个入口函数体内必须同时有 except 与 logger.warning。

        行为级 caplog 断言只能证明「异常时留了 WARNING」，本条防的是另一种退化 ——
        有人把 try 收窄到只包一句、或把 warning 降成 debug/静默 pass。
        """
        src = _strip_comments(
            (_APP / "services" / "sampling_registry_service.py").read_text(encoding="utf-8")
        )
        for name in (
            "register_sampling_batch",
            "register_sampled_vouchers",
            "update_sampling_record_evaluation",
            "project_level_extracted_voucher_nos",
        ):
            body = _func_body(src, name)
            assert body, f"抽不到 {name} 函数体 → 断言会空转"
            assert "except Exception" in body, f"{name} 未 fail-open"
            assert "logger.warning" in body, f"{name} fail-open 未留 WARNING（静默黑洞）"

    def test_reverse_selfcheck_fail_open_detector(self):
        """反向自检：静默吞异常的替身函数必须被上一条判据判红。"""
        stub = (
            "async def register_sampling_batch(db, *, log):\n"
            "    try:\n"
            "        return await db.flush()\n"
            "    except Exception:\n"
            "        return None\n"
            "\n"
            "async def register_sampled_vouchers(db):\n"
            "    return 0\n"
        )
        body = _func_body(stub, "register_sampling_batch")
        assert body and "except Exception" in body
        assert "logger.warning" not in body, "反向自检失效：替身竟含 warning"


# ─── Property 14：接入点确实存在（防"建了表没人写"再退化为孤儿） ─────────────


class TestFieldMappingIsLiveInProduction:
    """🔴 fixture 与真实载荷分叉 = 假绿（2026-08-04 实测抓出）。

    `build_record_fields` 从 `coverage_stats.population_amount` 投影
    `sampling_records.population_total_amount`（CAS 1314 的「总体金额」记录项），
    而写入侧 `useVoucherSampling.confirmFill` 改造前只发 `count_rate` / `amount_rate`
    → 该列在生产里恒为 NULL，本文件的 `_criteria()` 自带该 key 故一路全绿。
    这一组把「后端读的 key」与「前端写的 key」绑死。
    """

    _COMPOSABLE = (
        _BACKEND.parent
        / "audit-platform"
        / "frontend"
        / "src"
        / "components"
        / "workpaper"
        / "composables"
        / "useVoucherSampling.ts"
    )

    @staticmethod
    def _coverage_stats_literal(src: str) -> str:
        """截取 confirmFill 里 `coverage_stats:` 三元表达式的对象字面量（括号配对）。"""
        i = src.find("coverage_stats:")
        if i < 0:
            return ""
        j = src.find("{", i)
        if j < 0:
            return ""
        depth = 0
        for k in range(j, len(src)):
            if src[k] == "{":
                depth += 1
            elif src[k] == "}":
                depth -= 1
                if depth == 0:
                    return src[j : k + 1]
        return ""

    def test_frontend_composable_found(self):
        """哨兵：路径解析失败会让下面两条断言空转。"""
        assert self._COMPOSABLE.exists(), f"取不到前端 composable: {self._COMPOSABLE}"

    def test_frontend_persists_population_amount(self):
        literal = self._coverage_stats_literal(
            self._COMPOSABLE.read_text(encoding="utf-8")
        )
        assert literal, "未定位到 coverage_stats 对象字面量 → 断言会空转"
        assert "population_amount" in literal, (
            "写入侧未发 population_amount → sampling_records.population_total_amount 恒 NULL"
        )

    def test_reverse_selfcheck_rates_only_payload_is_detected(self):
        """反向自检 A：只发两个 rate 的旧形态必须被上一条判据判红。"""
        stub = "coverage_stats: cs ? { count_rate: a, amount_rate: b } : null,"
        assert "population_amount" not in self._coverage_stats_literal(stub)

    def test_reverse_selfcheck_projection_is_none_for_legacy_payload(self):
        """反向自检 B：旧形态载荷（无 population_amount）投影出 None，
        证明该列此前确实取不到值（而不是"本来就有默认值"）。"""
        legacy = _criteria(coverage_stats={"count_rate": "2.00", "amount_rate": "0.20"})
        f = reg.build_record_fields(criteria=legacy, total_matched=100, filled_count=2)
        assert f["population_total_amount"] is None
        # 但 count 走 total_matched，不受影响
        assert f["population_total_count"] == 100


class TestRegistryWiring:
    def test_service_constructs_both_models(self):
        src = _strip_comments(
            (_APP / "services" / "sampling_registry_service.py").read_text(encoding="utf-8")
        )
        assert "SamplingRecord(" in src, "登记服务须真的构造 SamplingRecord"
        assert "SampledVoucher.__table__" in src or "SampledVoucher(" in src

    def test_cutoff_fill_calls_registry_for_voucher_sampling_only(self):
        src = _strip_comments(
            (_APP / "routers" / "cutoff_sampling.py").read_text(encoding="utf-8")
        )
        assert "register_sampling_batch" in src
        assert "register_sampled_vouchers" in src
        # 必须按 extraction_type 门控：截止测试的回填不应写抽样登记表
        assert 'extraction_type == "voucher_sampling"' in src

    def test_evaluation_endpoint_projects_to_record(self):
        src = _strip_comments(
            (_APP / "routers" / "voucher_sampling.py").read_text(encoding="utf-8")
        )
        assert "update_sampling_record_evaluation" in src

    def test_project_scope_exclusion_wired(self):
        src = _strip_comments(
            (_APP / "routers" / "voucher_sampling.py").read_text(encoding="utf-8")
        )
        assert "project_level_extracted_voucher_nos" in src
        assert 'exclude_scope' in src
        # 缺省必须是 workpaper（零回归）
        assert 'filters.get("exclude_scope", "workpaper")' in src

    def test_coverage_endpoint_exists(self):
        src = _strip_comments(
            (_APP / "routers" / "voucher_sampling.py").read_text(encoding="utf-8")
        )
        assert "voucher-coverage" in src
        assert "project_sampling_coverage" in src

    def test_reverse_selfcheck_wiring_detector(self):
        """反向自检：删掉构造调用的替身源码必须被判为"未接入"。"""
        stub = "async def register_sampling_batch(db, *, log):\n    return None\n"
        assert "SamplingRecord(" not in _strip_comments(stub)

    def test_cross_workpaper_detection_wired_into_extract(self):
        """R8.1：extract 必须返回 cross_workpaper_duplicates。"""
        src = _strip_comments(
            (_APP / "routers" / "voucher_sampling.py").read_text(encoding="utf-8")
        )
        assert "cross_workpaper_duplicate_vouchers" in src
        assert '"cross_workpaper_duplicates"' in src
        # 必须排除当前底稿自身（R8.2）
        assert "exclude_workpaper_id=req.workpaper_id" in src

    def test_cross_workpaper_detection_scope(self):
        """R8.2/8.3：排除当前底稿 + 只算引擎登记行（穿透页手工标记不算已抽凭）。"""
        src = _strip_comments(
            (_APP / "services" / "sampling_registry_service.py").read_text(encoding="utf-8")
        )
        body = src[src.index("async def cross_workpaper_duplicate_vouchers") :]
        body = body[: body.index("async def project_sampling_coverage")]
        assert "batch_id.isnot(None)" in body, "须只统计抽凭引擎登记行"
        assert "working_paper_id != exclude_workpaper_id" in body, "须排除当前底稿"
        # wp_code 在 wp_index，须 JOIN（working_paper 表无该列）
        assert "WpIndex" in body

    def test_cross_workpaper_detection_fail_open(self, caplog):
        """R8.9：检测失败降级为空清单 + WARNING，绝不阻断抽样。"""
        with caplog.at_level(logging.WARNING):
            got = asyncio.run(
                reg.cross_workpaper_duplicate_vouchers(
                    _BoomDB(),
                    project_id=uuid4(),
                    year=2025,
                    voucher_nos=["V-1"],
                    exclude_workpaper_id=uuid4(),
                )
            )
        assert got == []
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_cross_workpaper_empty_input_is_noop(self):
        """空样本 → 直接返回空，不查库（不产生无意义查询）。"""
        got = asyncio.run(
            reg.cross_workpaper_duplicate_vouchers(
                _BoomDB(),
                project_id=uuid4(),
                year=2025,
                voucher_nos=[],
                exclude_workpaper_id=None,
            )
        )
        assert got == []

    def test_project_exclusion_only_counts_engine_rows(self):
        """项目级排除只取 batch_id 非空的登记行 —— 穿透页手工标记不是"已执行抽凭程序"。"""
        src = _strip_comments(
            (_APP / "services" / "sampling_registry_service.py").read_text(encoding="utf-8")
        )
        body = src[src.index("async def project_level_extracted_voucher_nos") :]
        body = body[: body.index("async def project_sampling_coverage")]
        assert "batch_id.isnot(None)" in body


# ─── Property 11（写入侧）：ON CONFLICT 目标必须与 V139 唯一索引逐列一致 ──────


_ON_CONFLICT_COLS = ("project_id", "year", "voucher_no", "working_paper_id", "batch_id")


def _declared_conflict_target(src: str) -> tuple[list[str], str]:
    """从 `register_sampled_vouchers` 源码里抽 `index_elements` 列表与 `index_where` 文本。"""
    body = _func_body(src, "register_sampled_vouchers")
    assert body, "抽不到 register_sampled_vouchers 函数体 → 断言会空转"
    m = re.search(r"index_elements\s*=\s*\[([^\]]*)\]", body)
    cols = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    w = re.search(r'index_where\s*=\s*sa\.text\(\s*"([^"]*)"', body)
    return cols, (w.group(1) if w else "")


class TestSampledVoucherConflictTarget:
    """DB 侧索引存在 ≠ 写入侧声明对得上。

    `on_conflict_do_nothing(index_elements=...)` 若与实际唯一索引不一致，PG 抛
    `no unique or exclusion constraint matching the ON CONFLICT specification`
    → 被 `register_sampled_vouchers` 的 fail-open 吞成 WARNING → 登记**每次都静默失败**。
    V139→V140 返工正是这一形态（声明五列索引却撞上另一个全局唯一索引），故本组把
    「服务源码声明」与「V139 迁移文本」交叉锁死，改一侧另一侧必红。
    """

    def _src(self) -> str:
        return _strip_comments(
            (_APP / "services" / "sampling_registry_service.py").read_text(encoding="utf-8")
        )

    def test_uses_on_conflict_do_nothing(self):
        assert "on_conflict_do_nothing" in _func_body(self._src(), "register_sampled_vouchers")

    def test_conflict_target_columns_match_migration_index(self):
        cols, _ = _declared_conflict_target(self._src())
        assert cols, "未声明 index_elements → ON CONFLICT 目标不确定"
        sql = _MIGRATION.read_text(encoding="utf-8")
        idx = sql[sql.index("uq_sampled_vouchers_batch") : sql.index("WHERE is_deleted = false")]
        assert set(cols) == set(_ON_CONFLICT_COLS), f"声明列集与预期不符: {cols}"
        for col in cols:
            assert col in idx, f"声明的 {col} 不在 V139 唯一索引里 → ON CONFLICT 必报错"

    def test_conflict_predicate_matches_partial_index(self):
        """部分唯一索引必须配同谓词的 `index_where`，否则 PG 匹配不到该索引。"""
        _, where = _declared_conflict_target(self._src())
        assert "is_deleted" in where and "false" in where, f"index_where 缺失或不匹配: {where!r}"

    def test_reverse_selfcheck_missing_batch_id_is_detected(self):
        """反向自检：漏掉 batch_id（回到 V139 前的全局唯一语义）必须被判红。"""
        stub = (
            "async def register_sampled_vouchers(db):\n"
            "    stmt = stmt.on_conflict_do_nothing(\n"
            '        index_elements=["project_id", "year", "voucher_no"],\n'
            "    )\n"
        )
        cols, where = _declared_conflict_target(stub)
        assert set(cols) != set(_ON_CONFLICT_COLS)
        assert where == ""


# ─── 迁移 V139 ───────────────────────────────────────────────────────────────


class TestMigrationV139:
    def test_file_exists(self):
        assert _MIGRATION.exists()

    def test_all_statements_idempotent(self):
        sql = _MIGRATION.read_text(encoding="utf-8")
        for stmt in ("ADD COLUMN", "CREATE INDEX", "CREATE UNIQUE INDEX"):
            for m in re.finditer(stmt, sql):
                tail = sql[m.start() : m.start() + 120]
                assert "IF NOT EXISTS" in tail, f"非幂等语句: {tail[:80]}"

    def test_unique_index_is_partial_on_not_deleted(self):
        """部分索引排除软删除行，否则删除后无法重新登记同一凭证。"""
        sql = _MIGRATION.read_text(encoding="utf-8")
        assert "uq_sampled_vouchers_batch" in sql
        idx = sql[sql.index("uq_sampled_vouchers_batch") :]
        assert "WHERE is_deleted = false" in idx

    def test_unique_index_includes_batch_id(self):
        """batch_id 必须在唯一键里 —— 不同批次的同一凭证要能共存
        （那正是「该凭证被抽过两次」这一需要被发现的事实）。"""
        sql = _MIGRATION.read_text(encoding="utf-8")
        idx = sql[sql.index("uq_sampled_vouchers_batch") : sql.index("WHERE is_deleted = false")]
        for col in ("project_id", "year", "voucher_no", "working_paper_id", "batch_id"):
            assert col in idx


# ─── 连库：ORM 新列与 DB 实际列一致 ─────────────────────────────────────────


@dataclass
class _Snapshot:
    record_cols: set[str] = field(default_factory=set)
    voucher_cols: set[str] = field(default_factory=set)
    indexes: set[str] = field(default_factory=set)
    manual_index_def: str = ""
    batch_index_def: str = ""
    available: bool = False
    reason: str = ""


def _load_snapshot() -> _Snapshot:
    snap = _Snapshot()

    async def _all() -> None:
        from app.core.database import async_session

        async with async_session() as db:
            for table, sink in (
                ("sampling_records", snap.record_cols),
                ("sampled_vouchers", snap.voucher_cols),
            ):
                rows = (
                    await db.execute(
                        sa.text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema='public' AND table_name=:t"
                        ),
                        {"t": table},
                    )
                ).fetchall()
                sink.update(r[0] for r in rows)
            idx = (
                await db.execute(
                    sa.text(
                        "SELECT indexname, indexdef FROM pg_indexes "
                        "WHERE schemaname='public' "
                        "AND tablename IN ('sampling_records','sampled_vouchers')"
                    )
                )
            ).fetchall()
            for name, definition in idx:
                snap.indexes.add(name)
                if name == "uq_sampled_voucher_manual_project_year_no":
                    snap.manual_index_def = definition
                elif name == "uq_sampled_vouchers_batch":
                    snap.batch_index_def = definition
            snap.available = True

    try:
        asyncio.run(_all())
    except Exception as exc:  # noqa: BLE001
        snap.available = False
        snap.reason = f"{type(exc).__name__}: {exc}"
    return snap


_SNAP = _load_snapshot()
_live = pytest.mark.skipif(not _SNAP.available, reason=f"数据库不可用（{_SNAP.reason}）")


@_live
class TestMigrationApplied:
    """V139 是否已应用。**MigrationRunner 只在后端启动时跑** → 未重启后端时本组会红，
    这是有意的信号（提示需重启），不是判据错误。"""

    def test_snapshot_non_empty(self):
        assert _SNAP.record_cols, "扫不到 sampling_records 列 → 断言会空转"

    def test_sampling_records_new_columns(self):
        missing = {"batch_id", "sampling_method", "random_seed", "dataset_id"} - _SNAP.record_cols
        assert not missing, f"V139 未应用（缺列 {missing}）→ 需重启后端让 MigrationRunner 执行"

    def test_sampled_vouchers_batch_id(self):
        assert "batch_id" in _SNAP.voucher_cols, "V139 未应用（sampled_vouchers 缺 batch_id）"

    def test_indexes_created(self):
        expected = {
            "ix_sampling_records_batch",
            "ix_sampling_records_project_wp",
            "uq_sampled_vouchers_batch",
            "ix_sampled_vouchers_project_voucher",
        }
        missing = expected - _SNAP.indexes
        assert not missing, f"V139 索引缺失 {missing}"

    def test_legacy_global_unique_index_narrowed_to_manual_scope(self):
        """🔴 Property 11 的前提：旧全局唯一索引必须已收窄到手工标记范围（V140）。

        `uq_sampled_voucher_project_year_no` 原为
        `UNIQUE (project_id, year, voucher_no) WHERE NOT is_deleted`
        —— 它让「同一凭证被多个底稿抽取」在数据层不可表达，且会让抽凭登记撞它抛
        UniqueViolation（on_conflict 只声明了五列索引）被 fail-open 吞成 WARNING。
        V140 把它收窄为仅约束 `batch_id IS NULL` 的手工标记。
        """
        assert "uq_sampled_voucher_project_year_no" not in _SNAP.indexes, (
            "旧全局唯一索引仍在 → 抽凭登记会撞它，重复抽凭检测永远为空"
        )
        assert "uq_sampled_voucher_manual_project_year_no" in _SNAP.indexes, (
            "V140 未应用：手工标记去重索引缺失"
        )

    def test_manual_index_predicate_scopes_to_null_batch(self):
        assert _SNAP.manual_index_def, "取不到手工索引定义 → 断言空转"
        assert "batch_id IS NULL" in _SNAP.manual_index_def

    def test_batch_index_not_scoped_to_null_batch(self):
        """批次索引不得也带 batch_id IS NULL —— 否则抽凭登记侧完全无唯一约束。"""
        assert _SNAP.batch_index_def, "取不到批次索引定义 → 断言空转"
        assert "batch_id IS NULL" not in _SNAP.batch_index_def
        assert "batch_id" in _SNAP.batch_index_def
