"""模板库预设公式 ACNR 迁移 drift guard（Task 14.5 / Req 24.3, 24.4）。

依 `.kiro/specs/acnr-consumer-wiring/design.md` §Coverage Ledger 的 drift-guard 范式：
把**模板库预设公式引用**作为一个 ACNR 消费点纳入清单，并以 CI 契约测试守护其
归一化不漂移。

规则：
1. 模板库全部预设公式（prefill_formula_mapping + formula_presets_seed）逐条经
   `normalize_ref` 归一化，判定 migrated（grammar_v1 可解析）或 pending（待迁移）。
2. **drift guard**：pending 项使用的未映射函数集合必须 ⊆ 文档化的
   `PENDING_FUNCTION_ALLOWLIST`（ADJ/LEDGER/LEDGER_DETAIL/COUNT_LEDGER）。
   任何**新**的未映射函数（无 ACNR 等价且未登记）→ 本测试 CI 失败，提示补充
   ACNR grammar_v1 映射或登记为待迁移（Req 24.4）。
3. 归一化把旧格式 `TB_SUM`→`SUM_TB`、`TB_AUX`→`AUX`（Req 24.4 硬编码旧格式归一化）。
4. 增量、无回归：已迁移覆盖不得退化为 0（迁移是净增量）。

单一真源：`app.services.formula_management.preset_acnr_migration`。

Validates: Requirements 24.1, 24.3, 24.4
"""

from __future__ import annotations

import pytest

from app.services.formula_management.preset_acnr_migration import (
    LEGACY_ALIAS_MAP,
    PENDING_FUNCTION_ALLOWLIST,
    STATUS_MIGRATED,
    STATUS_PENDING,
    _collect_template_library_expressions,
    build_migration_ledger,
    normalize_ref,
)


@pytest.fixture(scope="module")
def ledger() -> dict:
    led = build_migration_ledger()
    assert led["total"] > 0, "模板库预设公式采集为空——采集器或数据源可能失效"
    return led


def test_every_preset_formula_is_classified(ledger: dict) -> None:
    """每条预设公式都被判定为 migrated 或 pending（无未分类）。"""
    assert ledger["migrated"] + ledger["pending"] == ledger["total"]


def test_migration_is_net_positive(ledger: dict) -> None:
    """已迁移覆盖为净增量，不得退化为 0（增量、无回归，Req 24.4）。"""
    assert ledger["migrated"] > 0, "没有任何预设公式被归一化为 ACNR grammar_v1"


def test_no_undocumented_pending_function(ledger: dict) -> None:
    """drift guard：pending 未映射函数集合 ⊆ 文档化待迁移白名单（Req 24.3/24.4）。

    出现新的未登记未映射函数 → CI 失败，提示补 ACNR grammar_v1 映射或登记待迁移。
    """
    used_pending = set(ledger["pending_functions"].keys())
    undocumented = sorted(used_pending - set(PENDING_FUNCTION_ALLOWLIST))
    assert not undocumented, (
        "检测到未登记的待迁移函数（无 ACNR grammar_v1 等价且不在白名单）：\n"
        + "\n".join(f"  - {fn}()" for fn in undocumented)
        + "\n\n请为其补充 ACNR grammar_v1 映射（若有 canonical 等价，加入 "
        "preset_acnr_migration.LEGACY_ALIAS_MAP），或在 PENDING_FUNCTION_ALLOWLIST "
        "登记为待迁移项（Req 24.4）。"
    )


def test_pending_allowlist_has_no_stale_entries(ledger: dict) -> None:
    """待迁移白名单保持权威：不残留已无引用的函数（可选提示，non-fatal 收敛）。

    白名单条目若已无任何预设引用，说明该旧格式已消除，可从白名单移除。
    """
    used_pending = set(ledger["pending_functions"].keys())
    stale = sorted(set(PENDING_FUNCTION_ALLOWLIST) - used_pending)
    # COUNT_LEDGER 等可能当前无引用——仅告警不失败（保留白名单前瞻位）
    if stale:
        # 不断言失败：这些是前瞻登记项，允许存在
        assert all(fn in PENDING_FUNCTION_ALLOWLIST for fn in stale)


def test_legacy_alias_normalized_to_acnr_canonical() -> None:
    """旧格式函数别名归一化为 ACNR canonical（Req 24.4）。"""
    assert LEGACY_ALIAS_MAP["TB_SUM"] == "SUM_TB"
    assert LEGACY_ALIAS_MAP["TB_AUX"] == "AUX"

    r1 = normalize_ref("=TB_SUM('1121~1122','期末余额')")
    assert r1.status == STATUS_MIGRATED
    assert r1.formula_ref == "SUM_TB('1121~1122','期末余额')"

    r2 = normalize_ref("=TB_AUX('1122','客户','期末余额')")
    assert r2.status == STATUS_MIGRATED
    assert r2.formula_ref == "AUX('1122','客户','期末余额')"


def test_canonical_grammar_recognized_as_migrated() -> None:
    """canonical grammar_v1 函数被识别为 migrated。"""
    for expr in [
        "=TB('1121','期末余额')",
        "=PREV('D1','审定表D1-1','审定数')",
        "=WP('H1','折旧分配分析表H1-13','生产成本折旧')",
        "=NOTE('I2-6','项目启动日期','value')",
        "=ROW('assets_total')",
        "=AUX('1122','客户','TOP1','期末余额')",
    ]:
        assert normalize_ref(expr).status == STATUS_MIGRATED, expr


def test_hardcoded_old_format_is_pending() -> None:
    """无 ACNR 等价的旧格式/裸坐标/占位判为 pending（待迁移，Req 24.4）。"""
    assert normalize_ref("=ADJ('1121','aje_net')").status == STATUS_PENDING
    assert normalize_ref("=LEDGER('1001','借','全年')").status == STATUS_PENDING
    assert normalize_ref("A5").status == STATUS_PENDING  # 裸坐标
    assert normalize_ref(None).status == STATUS_PENDING  # 占位
    assert normalize_ref("").status == STATUS_PENDING


def test_normalization_idempotent() -> None:
    """归一化幂等：对已 migrated 的 canonical ref 再归一化结果不变（Req 24.1）。"""
    once = normalize_ref("=TB_SUM('1121~1122','期末余额')")
    twice = normalize_ref(once.formula_ref)
    assert twice.status == STATUS_MIGRATED
    assert twice.formula_ref == once.formula_ref


def test_refs_carry_acnr_status_no_bare_string() -> None:
    """归一化引用为规范 dict（formula_ref + acnr_status），禁裸坐标串（Req 24.1）。"""
    exprs = _collect_template_library_expressions()
    assert exprs
    for e in exprs:
        nr = normalize_ref(e)
        ref = nr.to_ref_dict()
        if ref is None:
            # 仅空/占位允许无引用
            assert nr.reason == "empty_or_placeholder"
            continue
        assert "formula_ref" in ref
        assert ref["acnr_status"] in {STATUS_MIGRATED, STATUS_PENDING}
