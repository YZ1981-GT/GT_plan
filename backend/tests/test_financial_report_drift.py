"""财务报表 xlsx 差异告警守卫 — deliverable-lineage-wiring-and-writeback-closure Task 21/22

**Validates: Requirements 10.1~10.8, 12.6**

Property 20：xlsx 无回写通道（全仓不存在 xlsx→trial_balance/report_config/AuditReport 的写入路径）
Property 21：差异告警阻断确认（三态判定）
Property 26：迁移幂等且三层一致（DDL + ORM + service）

反向自检：
- 把「解析失败」也按 fail-open 放行（旧口径）时守卫必须打红 ——
  否则弄坏一个映射文件即可绕过需求 10.4 的阻断
- `if drift_report:` 式判定必须打红 —— `{"diffs": []}` 非空但表示已比对且一致
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.phase13_models import WordExportTaskVersion
from app.services.financial_report_drift_service import (
    AMOUNT_TOLERANCE,
    PERIODS,
    DriftUnavailable,
    compare_cells,
    should_block_confirm,
)

BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS = BACKEND / "migrations"
V143 = MIGRATIONS / "V143__deliverable_version_drift_report.sql"
R143 = MIGRATIONS / "R143__deliverable_version_drift_report.sql"


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(
        ln for ln in sql.splitlines() if not ln.lstrip().startswith("--")
    )


def _strip_py_comments(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return re.sub(r"#[^\n]*", "", src)


# ─── Property 21：三态判定 ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("payload", "blocked"),
    [
        (None, False),  # 未检测 / 未配映射 → 放行
        ({}, False),  # 空结果视为未检测
        ({"diffs": []}, False),  # 已比对且一致 → **必须放行**
        ({"diffs": [], "checked": 120}, False),
        ({"unavailable": "映射解析失败"}, True),  # 配置损坏 → fail-closed
        ({"unavailable": ""}, True),  # 原因缺失也要阻断
        (
            {
                "diffs": [
                    {
                        "row_name": "货币资金",
                        "sheet": "balance_sheet",
                        "coord": "C6",
                        "file_value": "100.00",
                        "expected_value": "90.00",
                        "diff": "10.00",
                    }
                ]
            },
            True,
        ),
        ("not-a-dict", True),  # 结构异常 → fail-closed
        (123, True),
    ],
)
def test_property_21_three_state_block_decision(payload, blocked):
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 21
    got, reason = should_block_confirm(payload)
    assert got is blocked, f"{payload!r} 判定错误"
    if blocked:
        assert reason and len(reason) > 10, "阻断必须给出可读中文原因"


_ONE_DIFF = {
    "diffs": [
        {
            "row_name": "应收账款",
            "sheet": "balance_sheet",
            "coord": "C12",
            "file_value": "500",
            "expected_value": "400",
            "diff": "100",
        }
    ]
}


def test_block_reason_points_to_adjustment_entries():
    """差异态的拒绝文案必须指向调整分录（需求 10.3），并给出具体行/格/两侧数值。"""
    _, reason = should_block_confirm(_ONE_DIFF)
    assert "调整分录" in reason
    assert "应收账款" in reason and "C12" in reason, "必须指出具体报表行与单元格"
    assert "500" in reason and "400" in reason, "必须给出文件值与重算值"


def test_block_reason_is_neutral_not_an_accusation():
    """🔴 文案必须**中性归因**，不得直接断言「有人手工改了数字」。

    真实库实测（项目 0ec33ac9 报表 v8，**非 stale**）报出 22 处差异，逐个看是
    **系统性错位**（`应付票据 C9` 取到应收票据的余额）—— 属「Cell_Mapping 坐标与
    该模板变体实际布局不一致」的配置问题，不是手工改动。在审计平台里把这种情况
    说成「有人改了报表数字」是**误指控**，比不告警更坏。

    故文案只陈述「与重算值不一致」这一事实，并列出三种可能原因供审计师判断。
    """
    _, reason = should_block_confirm(_ONE_DIFF)
    assert "手工改动共" not in reason, "不得直接断言手工改动"
    assert "不一致" in reason
    # 三种可能原因都要列出
    assert "上游数据已变更" in reason
    assert "手工改动" in reason  # 作为「可能原因之一」出现是允许的
    assert "映射" in reason


def test_stale_hint_only_when_stale():
    """`stale` 标记只影响**归因提示**，不改变阻断结论。"""
    _, plain = should_block_confirm(_ONE_DIFF)
    _, stale = should_block_confirm({**_ONE_DIFF, "stale": True})
    assert "快照已过期" not in plain
    assert "快照已过期" in stale
    assert should_block_confirm({**_ONE_DIFF, "stale": True})[0] is True
    # stale 但无差异 ⇒ 仍放行（stale 由既有 stale 机制提示，不在此重复阻断）
    assert should_block_confirm({"diffs": [], "stale": True})[0] is False


def test_unavailable_reason_points_to_mapping_config():
    _, reason = should_block_confirm({"unavailable": "Cell_Mapping 解析失败: xxx"})
    assert "映射" in reason and "重新生成" in reason


def test_reverse_selfcheck_naive_truthiness_would_block_clean_reports():
    """反向自检：用 `if drift_report:` 这种朴素判据会把「已比对且一致」误判成有差异。

    `{"diffs": []}` 是**非空 dict** ⇒ 朴素判据为真 ⇒ 每个配了映射的报表永远确认不了。
    这正是需求 10.8 要求三态的原因。
    """
    clean = {"diffs": [], "checked": 120}
    assert bool(clean) is True, "前提：该结构在朴素判据下为真"
    assert should_block_confirm(clean)[0] is False, "正确判据必须放行"


def test_reverse_selfcheck_failopen_on_parse_error_would_be_a_backdoor():
    """反向自检：解析失败若按 fail-open 放行，弄坏一个配置文件即可绕过阻断。"""
    assert should_block_confirm({"unavailable": "坏了"})[0] is True


# ─── 比对纯函数 ────────────────────────────────────────────────────────────


_VARIANT = {
    "rows": {
        "BS-002": {
            "row_code": "BS-002",
            "sheet": "balance_sheet",
            "row_name": "货币资金",
            "current": "C6",
            "prior": "D6",
        },
        "BS-008": {
            "row_code": "BS-008",
            "sheet": "balance_sheet",
            "row_name": "应收账款",
            "current": "C12",
        },
    }
}


def test_compare_detects_manual_edit():
    sheet_values = {"balance_sheet": {"C6": 1000.0, "D6": 900.0, "C12": 555.0}}
    expected = {
        "BS-002": {"current_period_amount": Decimal("1000.00"), "prior_period_amount": Decimal("900.00")},
        "BS-008": {"current_period_amount": Decimal("500.00")},
    }
    diffs = compare_cells(_VARIANT, sheet_values, expected)
    assert [d["row_code"] for d in diffs] == ["BS-008"]
    assert diffs[0]["coord"] == "C12"
    assert diffs[0]["diff"] == "55.00"


def test_compare_skips_formula_and_text_cells():
    """需求 10.7：公式格 / 文字格不参与数字比对。"""
    sheet_values = {"balance_sheet": {"C6": "=SUM(C7:C20)", "D6": "见附注五、1", "C12": None}}
    expected = {
        "BS-002": {"current_period_amount": 1, "prior_period_amount": 2},
        "BS-008": {"current_period_amount": 3},
    }
    assert compare_cells(_VARIANT, sheet_values, expected) == []


def test_compare_skips_when_expected_missing():
    """重算值缺失（该行未参与报表）≠ 手工改动 ⇒ 跳过而非报差异。"""
    sheet_values = {"balance_sheet": {"C6": 123.0}}
    assert compare_cells(_VARIANT, sheet_values, {}) == []


def test_compare_respects_tolerance():
    """浮点噪声（< 半分）不算手工改动；≥ 半分才算。"""
    sheet_values = {"balance_sheet": {"C6": 100.000000001}}
    expected = {"BS-002": {"current_period_amount": Decimal("100.00")}}
    assert compare_cells(_VARIANT, sheet_values, expected) == []

    sheet_values = {"balance_sheet": {"C6": 100.01}}
    diffs = compare_cells(_VARIANT, sheet_values, expected)
    assert len(diffs) == 1
    assert AMOUNT_TOLERANCE == Decimal("0.005")


def test_compare_handles_thousand_separator_strings():
    """文件里若是带千分符的字符串仍要能比（人工改动常留字符串）。"""
    sheet_values = {"balance_sheet": {"C6": "1,234.56"}}
    expected = {"BS-002": {"current_period_amount": Decimal("1000.00")}}
    diffs = compare_cells(_VARIANT, sheet_values, expected)
    assert len(diffs) == 1
    assert diffs[0]["file_value"] == "1234.56"


def test_periods_covers_only_current_and_prior():
    assert PERIODS == ("current", "prior")


# ─── Property 20：xlsx 无回写通道 ───────────────────────────────────────────


def test_property_20_no_xlsx_writeback_channel():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 20
    """财务报表不得出现「xlsx → 上游」的写入通道（需求 10.1）。

    判据：差异服务只读不写 —— 全文不得出现对 trial_balance / report_config /
    AuditReport / DisclosureNote 的 UPDATE/INSERT。
    """
    src = _strip_py_comments(
        (
            BACKEND / "app" / "services" / "financial_report_drift_service.py"
        ).read_text(encoding="utf-8")
    )
    for forbidden in (
        "sa.update(TrialBalance",
        "sa.insert(TrialBalance",
        "sa.update(AuditReport",
        "sa.update(DisclosureNote",
        "report_body_json =",
        "audited_amount =",
    ):
        assert forbidden not in src, f"差异服务出现写入通道: {forbidden}"


def test_capability_matrix_forbids_financial_report_writeback():
    """能力矩阵必须把 financial_report* 永久列为禁止回填（需求 10.1）。"""
    from app.services.deliverable_capabilities import (
        WRITEBACK_FORBIDDEN_DOC_TYPES,
        WRITEBACK_SUPPORTED_DOC_TYPES,
        supports_writeback,
    )

    assert "financial_report" in WRITEBACK_FORBIDDEN_DOC_TYPES
    assert not supports_writeback("financial_report")
    assert not supports_writeback("financial_report_unadjusted")
    assert not (WRITEBACK_FORBIDDEN_DOC_TYPES & WRITEBACK_SUPPORTED_DOC_TYPES)


# ─── Task 22 接线：confirm 前置校验 ─────────────────────────────────────────


def test_confirm_deliverable_calls_drift_gate():
    src = _strip_py_comments(
        (BACKEND / "app" / "services" / "deliverable_service.py").read_text(
            encoding="utf-8"
        )
    )
    assert "_assert_no_report_drift(" in src, "confirm_deliverable 未接差异阻断闸"
    assert "should_block_confirm(" in src, "未走三态判定唯一入口"


def test_confirm_gate_does_not_use_naive_truthiness():
    """反向自检：闸门内不得写 `if latest.drift_report:` 之类朴素判据。"""
    src = (BACKEND / "app" / "services" / "deliverable_service.py").read_text(
        encoding="utf-8"
    )
    i = src.index("async def _assert_no_report_drift")
    nxt = re.search(r"\n    (?:async )?def ", src[i:])
    fn = _strip_py_comments(src[i : i + nxt.start()] if nxt else src[i:])
    assert "if latest.drift_report" not in fn
    assert "if version.drift_report" not in fn
    assert "should_block_confirm(" in fn


# ─── Property 26：迁移三层一致 ─────────────────────────────────────────────


def test_v143_migration_idempotent_with_rollback():
    assert V143.exists() and R143.exists()
    ddl = _strip_sql_comments(V143.read_text(encoding="utf-8"))
    assert ddl.count("ADD COLUMN IF NOT EXISTS") == 1, "迁移必须幂等"
    assert "drift_report JSONB" in ddl
    rb = _strip_sql_comments(R143.read_text(encoding="utf-8"))
    assert "DROP COLUMN IF EXISTS drift_report" in rb


def test_v143_number_not_reused():
    """迁移版本号永不复用：V143 只能有一个文件。"""
    hits = sorted(p.name for p in MIGRATIONS.glob("V143__*.sql"))
    assert hits == ["V143__deliverable_version_drift_report.sql"], hits


def test_orm_has_drift_report_column():
    col = WordExportTaskVersion.__table__.columns.get("drift_report")
    assert col is not None, "ORM 缺 drift_report ⇒ 迁移跑了也写不进去"
    assert col.nullable is True


def test_migration_comment_avoids_text_bind_pitfall():
    """迁移里的 `COMMENT ... IS '...:xxx'` 只能由 exec_driver_sql 执行。

    🔴 实测坑：SQLAlchemy `text()` 会把字符串字面量里的 `:标识符` 当 bind parameter
    （本迁移的 `"unavailable":原因` 直接报
    `A value is required for bind parameter '原因'`）。
    MigrationRunner 生产路径已用 `exec_driver_sql`（其源码注释写着这条坑），
    本断言钉住该前提 —— 若有人把它改回 `text()`，本迁移会在启动时炸。
    """
    runner = _strip_py_comments(
        (BACKEND / "app" / "core" / "migration_runner.py").read_text(encoding="utf-8")
    )
    assert "exec_driver_sql(stmt)" in runner, (
        "MigrationRunner 未用 exec_driver_sql 执行用户 SQL ⇒ 含 ':标识符' 的迁移会炸"
    )
    # 本迁移确实含该模式（否则上面的断言是空转）
    assert '"unavailable":' in V143.read_text(encoding="utf-8")


def test_drift_unavailable_is_an_exception():
    assert issubclass(DriftUnavailable, Exception)
