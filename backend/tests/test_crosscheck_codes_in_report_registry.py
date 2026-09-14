"""Contract test — 合并报表 cross-check 用的 BS-*/IS-* 行码存在于 report-config 地址注册表。

Validates: Requirements 19.6

背景（acnr-consumer-wiring task 28.3）：
`audit-platform/frontend/src/views/composables/useReportCrossCheck.ts` 的
`computeCrossCheckResults` 用硬编码报表行码（BS-001 / IS-001 / IS-002 / IS-017 /
IS-018 / IS-019）+ 语义合计名做跨表勾稽取值。本契约测试断言：cross-check 引用的
每个 BS-*/IS-* 行码都存在于 report-config 地址注册表真源（`backend/data/report_config_seed.json`
汇总的全部 report_type × 变体 的 row_code 全集），从而在 CI 阶段捕获"孤儿/拼写错误"
的报表码漂移（Req 19.6）。

策略（无 DB 依赖，纯静态源）：
1. 从 report_config_seed.json 汇总所有 report_type/变体的 row_code → 注册表全集。
2. 用正则从 useReportCrossCheck.ts 抽取 cross-check 实际引用的 BS-\\d+/IS-\\d+ 码 → 使用集。
   （以源码为权威，避免测试与被测代码手抄漂移。）
3. 断言：使用集非空 且 ⊆ 注册表全集；缺失码作为真实漂移报出（不弱化断言）。
"""

import json
import re
from pathlib import Path

import pytest

# ── 路径定位 ──────────────────────────────────────────────────────────────
# test 在 backend/tests/ → parent.parent = backend/
_BACKEND = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND.parent
SEED_PATH = _BACKEND / "data" / "report_config_seed.json"
CROSSCHECK_TS = (
    _REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "views"
    / "composables"
    / "useReportCrossCheck.ts"
)

# cross-check 已知引用的行码（迁移前基线，用作显式回归锚点）。
# 若源码后续新增/改动 BS-*/IS-* 引用，正则抽取集会捕获真实使用，二者取并集校验。
_EXPECTED_CODES = {"BS-001", "IS-001", "IS-002", "IS-017", "IS-018", "IS-019"}

# 报表行码形态：字母域前缀（BS/IS/CF/CE 等）+ '-' + 数字
_ROW_CODE_RE = re.compile(r"\b((?:BS|IS)-\d{1,4})\b")


def _load_report_registry_codes() -> set[str]:
    """汇总 report_config_seed.json 中所有 report_type/变体的 row_code → 注册表全集。"""
    assert SEED_PATH.exists(), f"report_config seed 不存在: {SEED_PATH}"
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data, "report_config_seed.json 应为非空 list"
    codes: set[str] = set()
    for config in data:
        for row in config.get("rows", []):
            rc = row.get("row_code")
            if rc:
                codes.add(rc)
    return codes


def _extract_crosscheck_codes() -> set[str]:
    """从 useReportCrossCheck.ts 正则抽取 cross-check 实际引用的 BS-*/IS-* 行码。"""
    assert CROSSCHECK_TS.exists(), f"cross-check composable 不存在: {CROSSCHECK_TS}"
    src = CROSSCHECK_TS.read_text(encoding="utf-8")
    return set(_ROW_CODE_RE.findall(src))


def test_report_registry_contains_expected_row_codes() -> None:
    """report-config 注册表全集应含 cross-check 已知引用的行码（显式基线锚点）。"""
    registry = _load_report_registry_codes()
    missing = sorted(_EXPECTED_CODES - registry)
    assert not missing, (
        f"cross-check 基线行码在 report-config 注册表中缺失（报表码漂移）: {missing}"
    )


def test_crosscheck_codes_in_report_registry() -> None:
    """契约：useReportCrossCheck.ts 引用的每个 BS-*/IS-* 行码都存在于 report-config 注册表。

    以源码正则抽取为权威使用集，防止 cross-check 与注册表之间的孤儿/拼写漂移。
    """
    used = _extract_crosscheck_codes()
    assert used, (
        "未能从 useReportCrossCheck.ts 抽取到任何 BS-*/IS-* 行码；"
        "cross-check 取值逻辑可能已变更，请更新契约测试。"
    )
    # 源码抽取集应覆盖已知基线（若基线码被移除是有意变更，此断言提示复核）。
    assert _EXPECTED_CODES <= used, (
        f"cross-check 源码不再引用基线行码: {sorted(_EXPECTED_CODES - used)}；"
        "如为有意变更请同步更新 _EXPECTED_CODES。"
    )

    registry = _load_report_registry_codes()
    orphans = sorted(used - registry)
    assert not orphans, (
        f"cross-check 引用的报表行码在 report-config 注册表中不存在"
        f"（孤儿/拼写错误，Req 19.6 漂移）: {orphans}\n"
        f"注册表码样例: {sorted(registry)[:12]} ...（共 {len(registry)} 个）"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
