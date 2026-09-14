"""H 类 `tb_values` 键契约守卫 —— 后端产出键 ⊇ 前端消费键。

**为什么需要这条守卫（2026-08-03 复盘引入）**

本 spec 重写 9 个 render 的取数函数时把键名统一成 `{prefix}_unadjusted_opening`，
而 `GtH8RightOfUseAssets.vue` 读的是旧键 `tv.rou_asset_closing ?? 0` ——
后果是 H8 审定表的 TB 核对种子**静默恒为 0**（`?? 0` 吞掉 `undefined`，
不报错、不崩溃、`get_diagnostics` 零诊断、55 个既有守卫全绿）。
复盘时顺带查出**三组改造前就存在的同类 dead read**（见 `_KNOWN_DEAD_READS`）。

这类缺陷四层验证（Volar / vitest / Vite transform / 后端单测）全部查不出，
因为后端与前端各自都"自洽"，只有**跨侧交叉比对**能拦。

**实现取向：真跑纯函数收键，不解析 f-string 源码。**
后端键是 `out[f"{prefix}_unadjusted_opening"]` 形态，`prefix` 来自
`H{N}_SLOT_KEY_PREFIX`。静态解析 f-string 既脆弱又会漏（例如漏掉条件分支里的别名），
故直接构造「全部槽都命中」的 `SemanticAccountResult` 调用真实纯函数，
收集实际输出的 dict 键 —— 这样守卫随实现自动演进，不会因改写法而失效。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/ 复盘建议 1
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.four_table.semantic_account_resolver import (
    RESOLVED_FROM_CLIENT_CHART,
    ResolvedSlot,
    SemanticAccountResult,
)

_FRONTEND = (
    Path(__file__).resolve().parent.parent.parent
    / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
)


# ──────────────────────────────────────────────────────────────────────────────
# 已知的既有 dead read（改造前就存在，非本 spec 引入）
#
# 每条必须写明「前端读什么 / 后端实际产什么 / 归属」，禁止无理由挂白名单。
# 修好后必须从此表移出，否则 `test_known_dead_reads_still_dead` 会打红
# （反向自检：白名单里的项若已修好，说明白名单过时）。
# ──────────────────────────────────────────────────────────────────────────────
_KNOWN_DEAD_READS: dict[str, str] = {
    # ✅ 已修（2026-08-03）：`rou_1901_*` / `rou_acc_dep_*` 四个键原属 useH8FormData.ts，
    # 已改为读后端真实产出的 `rou_asset_unadjusted|_audited` / `rou_dep_unadjusted|_audited`
    # → 从本白名单移出（`test_known_dead_reads_still_dead` 会拦回归）。
    # useH6FormData.ts；H6 render 旧版与新版都产 unadjusted_amount / audited_amount
    "disposal_1606_unadjusted": "useH6FormData.ts；render 实产 unadjusted_amount；改造前即断",
    "disposal_1606_audited": "useH6FormData.ts；render 实产 audited_amount；改造前即断",
    # useH3FormData.ts；H3 render 由并发 spec 改为 ip_* / dep_* 前缀，前端未同步
    "inv_prop_1503_unadjusted": "useH3FormData.ts；并发 spec 改 render 为 ip_* 前缀，前端未同步",
    "inv_prop_1503_audited": "useH3FormData.ts；同上",
    "dep_1504_unadjusted": "useH3FormData.ts；并发 spec 改 render 为 dep_* 但语义槽不同；待核",
    "dep_1504_audited": "useH3FormData.ts；同上",
}


def _slot(key: str, code: str) -> ResolvedSlot:
    """构造一个「已命中」的槽（`found` 由 codes 非空派生）。"""
    return ResolvedSlot(
        key=key,
        label=key,
        codes=[code],
        standard_codes=[code],
        matched=[(code, f"科目{code}")],
        resolved_from=RESOLVED_FROM_CLIENT_CHART,
        exact=True,
    )


def _all_found_result(slot_keys: list[str]) -> SemanticAccountResult:
    """构造「全部槽都命中」的定位结果（用于收集最大键集）。"""
    return SemanticAccountResult(
        slots={k: _slot(k, f"9{i:03d}") for i, k in enumerate(slot_keys)},
        row_code="TEST-000",
        chart_available=True,
    )


class _TbRow:
    """`tb_balance` 行替身（叶子聚合需要的字段）。"""

    def __init__(self, code: str):
        self.account_code = code
        self.account_name = f"科目{code}"
        self.opening_balance = 100.0
        self.closing_balance = 200.0
        self.debit_amount = 50.0
        self.credit_amount = 30.0
        self.closing_direction = "debit"
        self.dataset_id = None


class _TrialRow:
    """`trial_balance` 行替身。"""

    def __init__(self, code: str):
        self.standard_account_code = code
        self.unadjusted_amount = 111.0
        self.audited_amount = 222.0


def _collect_backend_keys(build_fn, slot_prefix_map: dict[str, str]) -> set[str]:
    """真跑纯函数，收集它实际产出的键集。"""
    slot_keys = list(slot_prefix_map.keys())
    accounts = _all_found_result(slot_keys)
    codes = [c for s in accounts.slots.values() for c in s.codes]
    tb_rows = [_TbRow(c) for c in codes]
    trial_rows = [_TrialRow(c) for c in codes]
    out = build_fn(accounts, tb_rows, trial_rows)
    return set(out.keys())


# ── 各循环：(纯函数, SLOT_KEY_PREFIX) ─────────────────────────────────────────

def _cycle_build_fns() -> dict[str, tuple]:
    from app.routers.wp_render_strategies._h8_right_of_use_assets import (
        build_h8_tb_values,
    )
    from app.routers.wp_render_strategies._h9_lease_liabilities import (
        build_h9_tb_values,
    )
    from app.services.four_table.h8_account_scope import H8_SLOT_KEY_PREFIX
    from app.services.four_table.h9_account_scope import H9_SLOT_KEY_PREFIX

    return {
        "H8": (build_h8_tb_values, H8_SLOT_KEY_PREFIX),
        "H9": (build_h9_tb_values, H9_SLOT_KEY_PREFIX),
    }


@pytest.fixture(scope="module")
def backend_keys_by_cycle() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for cycle, (fn, prefixes) in _cycle_build_fns().items():
        out[cycle] = _collect_backend_keys(fn, prefixes)
    return out


# ── 前端：扫 tb_values?.KEY / tb_values.KEY ───────────────────────────────────

_FE_KEY_RE = re.compile(r"tb_values\s*\??\s*\.\s*([A-Za-z_][A-Za-z_0-9]*)")


def _frontend_keys_for(patterns: list[str]) -> dict[str, set[str]]:
    """扫描匹配文件名的前端源码，返回 {文件名: 键集}。"""
    out: dict[str, set[str]] = {}
    if not _FRONTEND.is_dir():
        return out
    for path in _FRONTEND.rglob("*"):
        if path.suffix not in (".ts", ".vue"):
            continue
        if not any(p in path.name for p in patterns):
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except Exception:
            continue
        keys = set(_FE_KEY_RE.findall(src))
        if keys:
            out[path.name] = keys
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 反向自检：守卫本身没失效
# ──────────────────────────────────────────────────────────────────────────────

def test_backend_key_collection_not_empty(backend_keys_by_cycle: dict[str, set[str]]):
    """真跑纯函数确实收到了键（空集意味着守卫空转）。"""
    for cycle, keys in backend_keys_by_cycle.items():
        assert keys, f"{cycle}: 未收集到任何后端产出键，守卫失效"
        assert len(keys) >= 4, f"{cycle}: 只收到 {len(keys)} 个键，疑似构造失败"


def test_frontend_regex_finds_keys():
    """前端正则确实能命中（正则失效时此条打红）。"""
    hits = _frontend_keys_for(["useH8FormData", "useH9FormData"])
    assert hits, "前端未扫到任何 tb_values 读取，正则或路径失效"


def test_known_dead_reads_table_not_empty():
    """白名单非空（空表意味着 `test_frontend_keys_subset_of_backend` 的豁免逻辑空转）。"""
    assert _KNOWN_DEAD_READS


# ──────────────────────────────────────────────────────────────────────────────
# 主断言：前端消费键 ⊆ 后端产出键 ∪ 已知白名单
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cycle,file_patterns", [
    ("H8", ["useH8FormData", "GtH8RightOfUseAssets", "H8Tab"]),
    ("H9", ["useH9FormData", "GtH9LeaseLiabilities", "H9Tab"]),
])
def test_frontend_keys_subset_of_backend(
    cycle: str,
    file_patterns: list[str],
    backend_keys_by_cycle: dict[str, set[str]],
):
    """前端读的每个 `tb_values` 键，后端必须产出（或在白名单里写明原因）。"""
    backend = backend_keys_by_cycle[cycle]
    fe = _frontend_keys_for(file_patterns)
    if not fe:
        pytest.skip(f"{cycle}: 未扫到前端消费点")

    violations: list[str] = []
    for fname, keys in sorted(fe.items()):
        for k in sorted(keys):
            if k in backend or k in _KNOWN_DEAD_READS:
                continue
            violations.append(f"{fname} 读 tb_values.{k}，但 {cycle} render 不产出该键")

    assert not violations, (
        f"{cycle}: 发现 {len(violations)} 处 dead read（前端读、后端不产 → "
        f"`?? 0` 会静默兜成 0，四层验证查不出）：\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_known_dead_reads_still_dead(backend_keys_by_cycle: dict[str, set[str]]):
    """白名单反向自检：已登记的 dead read 若已被修好，必须从白名单移出。

    否则白名单会掩盖新引入的同名缺陷。
    """
    all_backend: set[str] = set()
    for keys in backend_keys_by_cycle.values():
        all_backend |= keys

    stale = sorted(k for k in _KNOWN_DEAD_READS if k in all_backend)
    assert not stale, (
        "以下键已被后端产出，但仍留在 `_KNOWN_DEAD_READS` 白名单里 → 请移出：\n"
        + "\n".join(f"  {k}（登记原因：{_KNOWN_DEAD_READS[k]}）" for k in stale)
    )


# ──────────────────────────────────────────────────────────────────────────────
# 回归钉死：本 spec 修掉的那处（H8 opening/closing 别名）不得再消失
# ──────────────────────────────────────────────────────────────────────────────

_H8_HOST_REQUIRED = [
    "rou_asset_opening", "rou_asset_closing",
    "rou_dep_opening", "rou_dep_closing",
]


def test_h8_host_consumed_aliases_present(backend_keys_by_cycle: dict[str, set[str]]):
    """`GtH8RightOfUseAssets.vue` 的 TB 核对种子依赖这四个别名键。

    2026-08-03 实测：缺这些键会让 `H8-adj-tb-amount-ending` / `-opening`
    静默恒为 0（宿主写的是 `tv.rou_asset_closing ?? 0`）。
    """
    backend = backend_keys_by_cycle["H8"]
    missing = [k for k in _H8_HOST_REQUIRED if k not in backend]
    assert not missing, (
        f"H8 render 缺少宿主依赖的别名键 {missing} → TB 核对行会静默恒为 0"
    )


def test_h8_host_actually_reads_those_aliases():
    """反向自检：宿主确实在读这四个键（否则上一条断言在保护不存在的需求）。"""
    host = _FRONTEND / "GtH8RightOfUseAssets.vue"
    if not host.is_file():
        pytest.skip("H8 宿主文件不存在")
    src = host.read_text(encoding="utf-8")
    not_read = [k for k in _H8_HOST_REQUIRED if k not in src]
    assert not not_read, (
        f"反向自检失败：宿主未读 {not_read}，`_H8_HOST_REQUIRED` 已过时"
    )


# ──────────────────────────────────────────────────────────────────────────────
# payload dict 重复键守卫（2026-08-03 浏览器实测抓到）
#
# H1 的 payload 曾同时写 `"tb_source_codes": accounts.as_dict()` 与
# `"tb_source_codes": h1_source_codes`（旧路径码列表）—— Python **静默取最后一个**，
# 于是溯源面板拿到数组、`hasSemanticAccountSource()` 恒 false、**面板永不渲染**。
#
# `get_diagnostics` / vitest / 55 个后端守卫 / Vite transform 全部查不出；
# 只有浏览器打开 + 拉 render-config 看 `Object.keys(tb_source_codes)` = `["0","1"]`
# 才暴露。故用 AST 把这条钉死。
# ──────────────────────────────────────────────────────────────────────────────

import ast as _ast

_H_RENDER_FILES = [
    "_h1_fixed_assets.py", "_h2_construction_in_progress.py", "_h4_engineering_materials.py",
    "_h5_oil_gas_assets.py", "_h6_asset_disposal_clearing.py", "_h7_biological_assets.py",
    "_h8_right_of_use_assets.py", "_h9_lease_liabilities.py", "_h10_asset_disposal_income.py",
]

_RENDER_DIR = (
    Path(__file__).resolve().parent.parent / "app" / "routers" / "wp_render_strategies"
)


def _duplicate_dict_keys(src: str) -> list[tuple[int, list[str]]]:
    """返回 ``[(行号, [重复键])]``。"""
    out: list[tuple[int, list[str]]] = []
    for node in _ast.walk(_ast.parse(src)):
        if not isinstance(node, _ast.Dict):
            continue
        keys = [
            k.value for k in node.keys
            if isinstance(k, _ast.Constant) and isinstance(k.value, str)
        ]
        dups = sorted({k for k in keys if keys.count(k) > 1})
        if dups:
            out.append((node.lineno, dups))
    return out


@pytest.mark.parametrize("fname", _H_RENDER_FILES)
def test_no_duplicate_dict_keys_in_render(fname: str):
    """render 策略里任何字面量 dict 都不得有重复键。"""
    path = _RENDER_DIR / fname
    if not path.is_file():
        pytest.skip(f"{fname} 不存在")
    dups = _duplicate_dict_keys(path.read_text(encoding="utf-8"))
    assert not dups, (
        f"{fname} 存在重复 dict 键（Python 静默取最后一个 → 前面的赋值被丢弃）：\n"
        + "\n".join(f"  line {ln}: {ks}" for ln, ks in dups)
    )


def test_duplicate_key_detector_works():
    """反向自检：检测器对已知重复键样本必须报出。"""
    sample = 'x = {\n  "a": 1,\n  "b": 2,\n  "a": 3,\n}\n'
    dups = _duplicate_dict_keys(sample)
    assert dups and dups[0][1] == ["a"], "重复键检测器失效"


def test_h_render_tb_source_codes_is_semantic_dict():
    """`tb_source_codes` 必须赋语义 dict（`as_dict()`），不得直接赋码列表。

    反向锁死 H1 那次事故：赋列表会让前端 `hasSemanticAccountSource` 恒 false。
    """
    violations: list[str] = []
    pat = re.compile(r'"tb_source_codes"\s*:\s*([A-Za-z_][\w\.]*)')
    for fname in _H_RENDER_FILES:
        path = _RENDER_DIR / fname
        if not path.is_file():
            continue
        for m in pat.finditer(path.read_text(encoding="utf-8")):
            expr = m.group(1)
            # 允许：accounts.as_dict() 的结果变量、或直接 accounts.as_dict
            if expr.endswith("as_dict") or expr in ("source_codes", "accounts"):
                continue
            violations.append(f"{fname}: tb_source_codes 赋给了 `{expr}`（疑似码列表）")
    assert not violations, "\n".join(violations)
