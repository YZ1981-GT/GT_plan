"""M 循环明细行前端键与 provider 声明的差异**棘轮**（只许减小）。

spec: `oo-writeback-template-parity-closure` 任务 9.2。

## 现算事实（2026-11-15，不是推测）

M1 / M2 的明细行前端键与 provider 声明**两套并存**：
- provider 声明（契约 `sheets[].tables[].fields[].column_key` / `json_key`）：`aging`、
  `refIndex`、`priorAdjAje`、`currentAjeIncrease`、`verified`、`verificationRef` …
- 前端 `useM{n}Detail.ts` 行接口实际用：`beginBalance`、`endBalance`、`declaredAmount`、
  `paidAmount`、`resolutionRef`、`subtotal`、`beginAje`、`ajeIncrease` …

两侧交集很小。**这不是「少接了字段」可以顺手补上的问题**：前端明细表用整表 JSON
（`M1-M1-2-full-data` 等），契约声明 `flat_key_value`；统一任一侧都要改 canonical
digest（已发布 representation 脱钩、须重发布）或动 10 个宿主的读写语义，且必须真实
OnlyOffice 往返验证。处置见 spec 9.2 的裁决方向 ①/②。

## 本守卫的作用：把差异冻结成棘轮

- **禁增**：前端与 provider 的不一致集合不得比基线更大（新增臆造键立刻打红）。
- **允许减小**：任何一侧对齐后，把对应条目从基线删掉即可（棘轮只许变短）。
- **基线自证**：基线里每个条目必须**现在真的仍然不一致**——已对齐却没删条目会打红
  （防止棘轮虚高隐藏真实进展）。
- **反向**：provider 键若已在前端出现，说明该键接通了，必须从基线删除。

🔴 本守卫**不**接受「把 provider 换个名字让它匹配前端」——那会把缺陷正当化
（spec 9.2 记录的真实反例：曾按中文表头反推 `endAging` / `beginAje` / `isVerified`
等六个键，与 provider 真名全不一致）。字段名的唯一权威是 provider 声明。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
_FE = _ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"

#: 行身份 / 纯 UI 派生键：本来就不该出现在 provider 里，不算差异。
_UI_ONLY_KEYS = {
    "key", "seq", "rowId", "selected", "expanded", "id",
}

#: 🔴 棘轮基线：`(label, interface) -> {provider 有但前端没有的键}`。
#: **只许减小**。任一条目对齐后必须从对应集合里删掉；集合空了就删整个键。
#: 下面这些是 2026-11-15 现算值（`probe` 见 spec 9.2），不是手写猜测。
_BASELINE_PROVIDER_ONLY: dict[tuple[str, str], set[str]] = {
    ("M1", "M1DetailRow"): {
        "aging", "auditedClosing", "auditedDecrease", "auditedIncrease",
        "auditedOpening", "closingBalance", "companyCode", "currentAjeDecrease",
        "currentAjeIncrease", "currentRjeDecrease", "currentRjeIncrease",
        "decreaseAmount", "increaseAmount", "overdueReason", "priorAdjAje",
        "priorAdjRje", "priorOpening", "refIndex",
    },
    ("M2", "M2DetailUnlistedRow"): {
        "auditedClosing", "auditedClosingRatio", "auditedDecrease",
        "auditedIncrease", "auditedOpening", "auditedOpeningRatio",
        "closingAmount", "closingRatio", "currentAjeDecrease",
        "currentAjeIncrease", "currentRjeDecrease", "currentRjeIncrease",
        "increaseMethod", "investAmount", "investMethod", "priorAdjAje",
        "priorAdjRje", "verificationRef", "verified",
    },
}

#: 前端有但 provider 未声明的键（同为棘轮，只许减小）。
_BASELINE_FRONTEND_ONLY: dict[tuple[str, str], set[str]] = {
    ("M1", "M1DetailRow"): {
        "beginBalance", "crossRefDiff", "currency", "declareDiff", "declaredAmount",
        "declaredDate", "distributionBase", "distributionRatio", "endAudited",
        "endBalance", "expectedDeclared", "netPaidAmount", "paidAmount", "paidDate",
        "paymentMethod", "periodChange", "resolutionRef", "shareholdingRatio",
        "withholdingTax",
    },
    ("M2", "M2DetailUnlistedRow"): {
        "beginAmount", "decreaseReason", "endAmount", "idNumber", "idType",
        "increaseReason", "investDate", "investType", "subscribedAmount",
    },
}

CASES = [
    ("M1", "phase5_m1_dividends_payable", "useM1Detail.ts", "M1DetailRow"),
    ("M2", "phase5_m2_paid_in_capital", "useM2Detail.ts", "M2DetailUnlistedRow"),
]


def _provider_keys(module_name: str) -> set[str]:
    import importlib
    import sys

    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
    keys: set[str] = set()
    for sheet in mod.CONFIG.sheets:
        for f in sheet.fields:
            keys.add(f.json_key)
    return keys


def _interface_keys(path: Path, interface: str) -> set[str]:
    src = path.read_text(encoding="utf-8")
    m = re.search(rf"export interface {interface}\b[^{{]*{{(.*?)\n}}", src, re.S)
    if not m:
        pytest.fail(f"{path.name} 找不到 interface {interface}（改名后必须同步本守卫）")
    keys: set[str] = set()
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith(("//", "/*", "*")):
            continue
        hit = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\??\s*:", line)
        if hit:
            keys.add(hit.group(1))
    return keys


def _diff(module_name: str, fe_file: str, interface: str) -> tuple[set[str], set[str]]:
    provider = _provider_keys(module_name)
    assert provider, f"{module_name} provider 没有声明任何字段"
    fe = _interface_keys(_FE / fe_file, interface) - _UI_ONLY_KEYS
    return provider - fe, fe - provider


@pytest.mark.parametrize("label,module_name,fe_file,interface", CASES)
def test_provider_only_keys_do_not_grow(
    label: str, module_name: str, fe_file: str, interface: str
) -> None:
    """禁增：provider 有、前端没有的键不得比基线多。"""
    only_provider, _ = _diff(module_name, fe_file, interface)
    baseline = _BASELINE_PROVIDER_ONLY[(label, interface)]
    added = sorted(only_provider - baseline)
    assert not added, (
        f"{label} 新增「provider 声明但前端没有」的键: {added}。"
        f"要么接通它们（用 provider 的真名），要么显式扩大基线并写明裁决。"
    )


@pytest.mark.parametrize("label,module_name,fe_file,interface", CASES)
def test_frontend_only_keys_do_not_grow(
    label: str, module_name: str, fe_file: str, interface: str
) -> None:
    """禁增：前端有、provider 未声明的键不得比基线多（抓臆造键）。"""
    _, only_fe = _diff(module_name, fe_file, interface)
    baseline = _BASELINE_FRONTEND_ONLY[(label, interface)]
    added = sorted(only_fe - baseline)
    assert not added, (
        f"{label} 新增 provider 未声明的前端键: {added}。"
        f"若是按表头反推的英文键，必须改成 provider 真名；"
        f"若确属 UI 派生，加入 _UI_ONLY_KEYS 并写明理由。"
    )


@pytest.mark.parametrize("label,module_name,fe_file,interface", CASES)
def test_baseline_entries_are_still_real(
    label: str, module_name: str, fe_file: str, interface: str
) -> None:
    """基线自证：已对齐却没删的条目会打红（防棘轮虚高藏进展）。"""
    only_provider, only_fe = _diff(module_name, fe_file, interface)
    stale_provider = sorted(_BASELINE_PROVIDER_ONLY[(label, interface)] - only_provider)
    stale_fe = sorted(_BASELINE_FRONTEND_ONLY[(label, interface)] - only_fe)
    assert not stale_provider and not stale_fe, (
        f"{label} 基线里这些条目已经不一致消失了，必须从基线删除（只许变短）："
        f" provider_only={stale_provider} frontend_only={stale_fe}"
    )


@pytest.mark.parametrize("label,module_name,fe_file,interface", CASES)
def test_side_mismatch_counts_decrease_monotonically(
    label: str, module_name: str, fe_file: str, interface: str
) -> None:
    """总量棘轮：单向不一致总数不得超过基线总量（只许变小）。"""
    only_provider, only_fe = _diff(module_name, fe_file, interface)
    baseline_total = len(_BASELINE_PROVIDER_ONLY[(label, interface)]) + len(
        _BASELINE_FRONTEND_ONLY[(label, interface)]
    )
    assert len(only_provider) + len(only_fe) <= baseline_total, (
        f"{label} 不一致总数 {len(only_provider) + len(only_fe)} > 基线 {baseline_total}"
    )