"""QC 规则门控三态 — 守卫

spec: sampling-evaluation-and-governance-closure
Validates: Requirements 7.1, 7.2, 7.3, 11.2, 11.3
Properties: Property 18

## 背景（2026-08-05 实证 F15，平台级 P0）

`qc_rule_definitions` 表存在但真实库 **0 行**。改造前 `_get_enabled_rule_codes` 把返回值
当「启用白名单」，空表走的是「查询成功 + rows 为空」这条路（**不进 except**，故连 WARNING
都没有）→ `enabled_codes = set()` → `active_rules = []` ⇒ **全部 20 条内置 QC 规则静默不
执行**，底稿质量自检长期整体空转。

这也是「修好 QC-12 判据也不会生效」的原因，故本 spec 必须先修它。
"""

from __future__ import annotations

import inspect
import logging

import pytest

from app.services.qc_engine import QCEngine, SamplingCompletenessRule


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """按 rows 返回 qc_rule_definitions 查询结果；rows=None 表示查询抛异常。"""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):  # noqa: ANN001
        if self._rows is None:
            raise RuntimeError("模拟 qc_rule_definitions 查询失败（表不存在）")
        return _FakeResult(self._rows)


def _all_rule_ids() -> set[str]:
    return {r.rule_id for r in QCEngine().rules}


# ─── Property 18：三态 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_table_runs_all_rules_with_warning(caplog):
    """空表 = 尚未配置，不是「全部禁用」→ 全部执行 + WARNING。

    这是改造前的 P0：空表时返回空集导致 20 条规则全不执行且无任何日志。
    """
    engine = QCEngine()
    with caplog.at_level(logging.WARNING, logger="app.services.qc_engine"):
        codes = await engine._get_enabled_rule_codes(_FakeSession([]))

    assert codes == _all_rule_ids(), "空表时必须执行全部内置规则"
    assert any("qc_rule_definitions" in r.getMessage() for r in caplog.records), (
        "空表降级必须留 WARNING，否则「全部规则没跑」无从发现"
    )


@pytest.mark.asyncio
async def test_query_failure_runs_all_rules(caplog):
    """查询失败（表不存在等）→ 全部执行 + WARNING（既有行为，保留）。"""
    engine = QCEngine()
    with caplog.at_level(logging.WARNING, logger="app.services.qc_engine"):
        codes = await engine._get_enabled_rule_codes(_FakeSession(None))
    assert codes == _all_rule_ids()
    assert any("Failed to load" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_explicitly_disabled_rule_is_excluded():
    """显式 enabled=false → 该规则不执行（保留原有关闭能力）。"""
    engine = QCEngine()
    codes = await engine._get_enabled_rule_codes(
        _FakeSession([("QC-12", "python", False)])
    )
    assert "QC-12" not in codes
    assert codes == _all_rule_ids() - {"QC-12"}


@pytest.mark.asyncio
async def test_unregistered_rule_is_enabled(caplog):
    """未登记的内置规则视为启用（登记表是禁用清单，不是准入白名单）。"""
    engine = QCEngine()
    with caplog.at_level(logging.INFO, logger="app.services.qc_engine"):
        codes = await engine._get_enabled_rule_codes(
            _FakeSession([("QC-12", "python", True)])
        )
    assert codes == _all_rule_ids(), "只登记一条且启用时，其余规则也应执行"
    assert any("未在 qc_rule_definitions 登记" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_explicitly_enabled_rule_runs():
    """显式 enabled=true → 执行。"""
    engine = QCEngine()
    codes = await engine._get_enabled_rule_codes(
        _FakeSession([("QC-12", "python", True), ("QC-13", "python", True)])
    )
    assert {"QC-12", "QC-13"} <= codes


@pytest.mark.asyncio
async def test_non_python_rule_does_not_disable_python_rule(caplog):
    """非 python 类型规则不参与 python 规则启停（由别的执行器处理）。"""
    engine = QCEngine()
    with caplog.at_level(logging.WARNING, logger="app.services.qc_engine"):
        codes = await engine._get_enabled_rule_codes(
            _FakeSession([("QC-12", "sql", False)])
        )
    assert "QC-12" in codes, "非 python 登记不应关掉同名 python 内置规则"
    assert any("non-python rule ignored" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_multiple_disabled_rules_all_excluded():
    engine = QCEngine()
    codes = await engine._get_enabled_rule_codes(
        _FakeSession([
            ("QC-12", "python", False),
            ("QC-13", "python", False),
            ("QC-01", "python", True),
        ])
    )
    assert not ({"QC-12", "QC-13"} & codes)


# ─── 反向自检：复现旧行为必打红 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reverse_selfcheck_legacy_whitelist_semantics_would_be_empty():
    """复现旧语义（只收 enabled=true 的 rule_code 作白名单）在空表下产出空集。

    没有这条，上面的空表断言可能因取源方式变化而变成空转 —— 它证明「空表 → 空集」
    确实是一种可能的实现结果，从而证明我们的断言有区分力。
    """
    rows: list[tuple[str, str, bool]] = []
    legacy_codes = {code for code, etype, enabled in rows if etype == "python" and enabled}
    assert legacy_codes == set(), "反向自检自身失效"
    assert legacy_codes != _all_rule_ids(), "旧语义与新语义在空表下必须不同"


def test_gating_query_does_not_filter_enabled_in_sql():
    """SQL 不得再带 `WHERE enabled = true`。

    带上之后「显式 disabled」与「未登记」在结果里不可区分（两者都不出现在 rows 里），
    三态语义就退化成两态，未登记的规则会被误当禁用。
    """
    src = inspect.getsource(QCEngine._get_enabled_rule_codes)
    assert "QcRuleDefinition.enabled == sa.true()" not in src, (
        "查询仍在 SQL 层过滤 enabled → 无法区分「显式禁用」与「未登记」"
    )
    assert "QcRuleDefinition.enabled" in src, "必须把 enabled 取出来在 Python 侧判定"


# ─── Property 19：QC-12 判据不依赖 SamplingConfig ────────────────────────────


def _strip_docstring_and_comments(src: str) -> str:
    """剥掉 docstring 与行注释 —— 说明文字里会如实提到 SamplingConfig（讲为什么不用它）。"""
    out = src
    for quote in ('"""', "'''"):
        parts = out.split(quote)
        # 偶数下标是代码，奇数下标是 docstring 内容
        out = "".join(p for i, p in enumerate(parts) if i % 2 == 0)
    lines = []
    for line in out.splitlines():
        idx = line.find("#")
        lines.append(line if idx < 0 else line[:idx])
    return "\n".join(lines)


def test_qc12_does_not_reference_sampling_config():
    """QC-12 的**可执行代码**不得引用 SamplingConfig（真实库 0 行且已软弃用）。"""
    code = _strip_docstring_and_comments(inspect.getsource(SamplingCompletenessRule))
    assert "SamplingConfig" not in code, (
        "QC-12 仍依赖 SamplingConfig —— 该表 0 行且 SamplingRecord.sampling_config_id 恒 NULL，"
        "判据双重失效"
    )


def test_qc12_reads_extraction_log_and_delegates_to_pure_function():
    code = _strip_docstring_and_comments(inspect.getsource(SamplingCompletenessRule))
    assert "WorkpaperExtractionLog" in code, "应基于抽凭批次留痕判定"
    assert "is_undone" in code, "必须排除已撤销批次"
    assert 'extraction_type == "voucher_sampling"' in code
    assert "evaluate_sampling_completeness" in code, (
        "判据必须委托纯函数（与归档完整性检查共用同一判据，避免结论打架）"
    )


def test_strip_docstring_selfcheck():
    """自检：剥离函数确实剥掉了 docstring 与注释里的 SamplingConfig。"""
    fake = '''def f():
    """这里提到 SamplingConfig 只是说明。"""
    # 注释里也提到 SamplingConfig
    return 1
'''
    cleaned = _strip_docstring_and_comments(fake)
    assert "SamplingConfig" not in cleaned
    assert "return 1" in cleaned


def test_qc12_severity_is_warning_not_blocking():
    """抽样记录补齐是审计判断，不应阻断（与 memory 记的『不假绿』一致：报出但不硬卡）。"""
    assert SamplingCompletenessRule.severity == "warning"
    assert SamplingCompletenessRule.rule_id == "QC-12"
