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
#:
#: 🔴 加进这里的条件（2026-11-16 现读 M1 模板「明细表M1-2」A~U 21 列后定）：
#:    该键在**权威模板里没有对应列**，是前端为业务流程（宣告/支付/核对）做的展示或计算。
#:    进这里的每一项都要在 `_M1_UI_ONLY_CLAIM` 之外单独可伪证：模板列数固定 21，
#:    键不在那 21 列里。M1 专属的 14 个键另见 `_M1_UI_ONLY_CLAIM`（可伪证断言在那组）。

#: 跨表通用的行身份 / 组件状态键 —— 任何循环的任何明细表都可能有，不需逐表声明。
_GENERIC_UI_ONLY_KEYS = frozenset(
    {"key", "seq", "rowId", "selected", "expanded", "id"}
)

_UI_ONLY_KEYS = {
    *_GENERIC_UI_ONLY_KEYS,

    # ── M1 应付股利：模板 21 列（A~U）里没有的 14 个前端派生键 ──────────────
    # 股东信息区
    "shareholdingRatio",   # 「持股比例(%)」—— 模板无此列，纯展示
    "currency",            # 「币种」—— 模板无此列
    # 宣告区（模板只有 E「本期增加」一列，没有宣告流程的细分）
    "declaredDate",        # 「宣告日期」—— 模板无此列
    "resolutionRef",       # 「决议文号」—— 模板无；T 列是「相关文件索引号」refIndex，不是同一个
    "distributionRatio",   # 「分配比例(%)」—— 模板无
    "distributionBase",    # 「分配基数(可供分配利润)」—— 模板无
    "expectedDeclared",    # 「应宣告=基数×比例」—— 模板无（纯前端计算）
    "declareDiff",         # 「宣告差异=实际宣告-应宣告」—— 模板无（纯前端计算）
    # 支付区（模板只有 F「本期减少」一列，没有支付流程的细分）
    "paidDate",            # 「支付日期」—— 模板无
    "paymentMethod",       # 「支付方式」—— 模板无
    "withholdingTax",      # 「代扣代缴税金」—— 模板无
    "netPaidAmount",       # 「实际支付净额=支付-代扣」—— 模板无（纯前端计算）
    # 交叉核对 / 公式派生
    "crossRefDiff",        # 「与M1-1交叉验证差额」—— 模板无（纯前端计算）
    "periodChange",        # 「本期变动=宣告-支付」—— 模板无（纯前端计算）
}

#: 🔴 棘轮基线：`(label, interface) -> {provider 有但前端没有的键}`。
#: **只许减小**。任一条目对齐后必须从对应集合里删掉；集合空了就删整个键。
#: 下面这些是 2026-11-15 现算值（`probe` 见 spec 9.2），不是手写猜测。
_BASELINE_PROVIDER_ONLY: dict[tuple[str, str], set[str]] = {
    # M1：2026-11-16 按模板「明细表M1-2」A~U 21 列补齐 11 个字段后，从 18 条降到 7 条
    # （删：aging / companyCode / currentAjeDecrease / currentAjeIncrease / currentRjeDecrease /
    #   currentRjeIncrease / overdueReason / priorAdjAje / priorAdjRje / priorOpening / refIndex）
    # 余 7 条全是 D~G / N~Q 的 R2 结构差异（模板「期初数/本期增加/本期减少/期末数」vs
    # 前端 beginBalance/declaredAmount/paidAmount/endBalance/endAudited 的另一套语义），
    # 需业务裁决，不能靠键名对齐解决。
    ("M1", "M1DetailRow"): {
        "auditedClosing", "auditedDecrease", "auditedIncrease",
        "auditedOpening", "closingBalance", "decreaseAmount", "increaseAmount",
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
    # M1：2026-11-16 把 14 个「模板无此列」的纯 UI 派生键登记进 `_UI_ONLY_KEYS` 后，
    # 从 19 条降到 5 条 —— 余下这 5 条全是 R2 结构差异（模板 D~G / N~Q 那一套
    # 「期初+增−减=期末」与前端「宣告/支付」流程的语义映射），需业务裁决。
    ("M1", "M1DetailRow"): {
        "beginBalance", "declaredAmount", "endAudited", "endBalance", "paidAmount",
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


# ═══════════════════════════════════════════════════════════════════════════
# `_UI_ONLY_KEYS` 的可伪证断言（spec m-cycle-key-naming-unification 任务 5）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么需要这组用例：`_UI_ONLY_KEYS` 是「不算差异」的白名单，而白名单天然是
#    **可以夹带私货的地方** —— 把没接的字段塞进去，棘轮就假性变短了。
#    所以每条豁免必须有**可被实际情况推翻的判据**，不是只有一句理由文本。
#
# 判据（M1 这批）：该键在权威模板「明细表M1-2」的 A~U 21 列里**没有对应列**。
# 现算口径 = provider `DETAIL_SHEET.fields`（21 条）的 json_key 集合；
# 若某个被豁免的键出现在 provider 声明里，说明它其实有模板列 ⇒ 豁免是错的。

#: M1 模板（明细表M1-2）声明为「模板无对应列」的纯 UI 派生键。
_M1_UI_ONLY_CLAIM = {
    "shareholdingRatio", "currency", "declaredDate", "resolutionRef",
    "distributionRatio", "distributionBase", "expectedDeclared", "declareDiff",
    "paidDate", "paymentMethod", "withholdingTax", "netPaidAmount",
    "crossRefDiff", "periodChange",
}


def test_m1_ui_only_claims_have_no_provider_column() -> None:
    """M1 那 14 个豁免键必须**真的不在** provider 声明里（模板无对应列）。

    反向：provider 若新增了同名字段（等于模板补了列），这条会红 ⇒ 逼着把该键
    从 `_UI_ONLY_KEYS` 挪回正常对账（也就是它必须进前端受管面）。
    """
    provider = _provider_keys("phase5_m1_dividends_payable")
    overlap = sorted(_M1_UI_ONLY_CLAIM & provider)
    assert not overlap, (
        f"这些键被登记为「模板无对应列」但 provider 其实声明了: {overlap}。\n"
        "说明模板确实有这一列 ⇒ 豁免是错的，必须把它们从 `_UI_ONLY_KEYS` 删掉、"
        "按正常键名对账处理。"
    )


def test_m1_ui_only_claim_matches_registered_ui_only_both_ways() -> None:
    """豁免声明与 `_UI_ONLY_KEYS` 必须**双向**一致（防两边各写一份后漂移）。

    🔴 单向检查会漏：只查 `CLAIM - _UI_ONLY_KEYS`（声明少了）能红，但
    `_UI_ONLY_KEYS` 里多出来的 M1 键**没人管** —— 那正好是「夹带私货」的落点。
    第一版只写单向，变异「从 CLAIM 删一个键」存活；补成双向后 RED。
    """
    # 方向 1：声明里的键必须都真的在 _UI_ONLY_KEYS
    missing = sorted(_M1_UI_ONLY_CLAIM - _UI_ONLY_KEYS)
    assert not missing, (
        f"这些键在 _M1_UI_ONLY_CLAIM 里但没进 _UI_ONLY_KEYS: {missing}"
        " —— 两处必须同改，否则判据会对实际豁免视而不见"
    )
    # 方向 2：_UI_ONLY_KEYS 里属于 M1 的键必须都在声明里（否则豁免无判据支撑）
    m1_fe = _interface_keys(_FE / "useM1Detail.ts", "M1DetailRow")
    provider = _provider_keys("phase5_m1_dividends_payable")
    # 「M1 专属的 UI 豁免」= 前端有、provider 没有、在 _UI_ONLY_KEYS 里、
    # **且不属于跨表通用的行身份/UI 键**（那些不需要 M1 专属声明）
    m1_ui_exempt = (m1_fe - provider) & _UI_ONLY_KEYS - _GENERIC_UI_ONLY_KEYS
    unclaimed = sorted(m1_ui_exempt - _M1_UI_ONLY_CLAIM)
    assert not unclaimed, (
        f"这些键被 _UI_ONLY_KEYS 豁免但不在 _M1_UI_ONLY_CLAIM 声明里: {unclaimed}。\n"
        "豁免必须有可伪证判据（该键不在模板 A~U 21 列里）——"
        "没进声明的豁免就是「夹带私货」，会让棘轮假性变短。"
    )


def test_m1_ui_only_claim_covers_every_frontend_only_key() -> None:
    """M1 的 frontend-only 基线 + UI 豁免，必须覆盖前端**全部**非 provider 键。

    防的是「新增一个既不进基线也不进豁免的键」—— 那种键会被 `_UI_ONLY_KEYS`
    静默扣掉，两侧都看不见它（假绿）。
    """
    from pathlib import Path as _P

    fe = _interface_keys(_FE / "useM1Detail.ts", "M1DetailRow")
    provider = _provider_keys("phase5_m1_dividends_payable")
    # 既不在 provider、也不在 UI 豁免、也不在基线的键 = 无人管
    unaccounted = sorted(
        fe - provider - _UI_ONLY_KEYS - _BASELINE_FRONTEND_ONLY[("M1", "M1DetailRow")]
    )
    assert not unaccounted, (
        f"M1 有 {len(unaccounted)} 个前端键既不在 provider 声明、也不在 UI 豁免、"
        f"也不在棘轮基线里: {unaccounted}。\n"
        "每个键必须有明确归属：接 provider 真名 / 登记为模板无列的 UI 派生 / 进基线等裁决。"
    )
