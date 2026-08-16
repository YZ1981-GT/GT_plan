"""调整分录导入导出 —— 后端契约守卫（对 adjustment_ie_contract.json）。

spec: adjustment-import-export-contract / Task 4.1 + Task 4.3

守卫内容：
  * Property 9  遍历**全部循环** `_X_SPECS` 中的调整 sheet（不硬编码逐条清单），
                逐条对照 `backend/data/adjustment_ie_contract.json`：
                `item_id` / **有效** `storage_field` / `field_keys` 必须一致；
                不一致时失败信息指名具体 sheet + 维度。
  * Property 11 注册完整性：后端发现的每张调整 sheet 必须出现在清单 `sheets` 或 `exempt` 中；
                遗漏即失败（前端侧同款守卫在 vitest：`adjustmentIeContract.spec.ts`）。
  * Property 6  中央通道三者列集合互相兼容：中央导入必填列 ⊆ 富模板列集合，
                且 ⊆ 汇总导出列集合（经别名规范化后）→ 导出产物可被导入接受。

判定「调整 sheet」的口径（避免硬编码清单）：spec 的 `title` 含「调整分录」，
或 `item_id` 命中 `adj` / `adjustment` / `-aje-` 等调整语义片段。

**后端 specs 发现口径 = 口径① 或 口径② 二者之一**（详见下方 `X3_SHEET_SPECS` 段的成块注释）：
  * 口径① 数据驱动工厂模块 `*_import_export.py` 里的 `_X_SPECS`（实测 37 张）
  * 口径② X-3 共享实现模块 `_x3_adjustment_import_export.py` 里的 `X3_SHEET_SPECS`
"""
from __future__ import annotations

import enum
import importlib
import inspect
import json
import re
import types
import warnings
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, NamedTuple

import pytest

_IE_DIR = Path(__file__).resolve().parents[1] / "app" / "routers" / "wp_render_strategies"
_CONTRACT_PATH = Path(__file__).resolve().parents[1] / "data" / "adjustment_ie_contract.json"
_FACTORY_DEFAULT_STORAGE_FIELD = "conclusion"

# 调整分录 sheet 的 item_id 语义片段。
# ⚠️ 刻意**不含**裸 `-adj-`：审定表（X-1）的 AJE/RJE 列数据键形如 `F4-1-adj-aging-rows`、
#    `G10-adj-rows`、`I1-adj-rows`，属审定表而非调整分录汇总表，不在本 spec 契约范围内。
_ADJ_ITEM_ID_HINTS = ("adjustment", "adj-entries", "-aje-rows")

#: 发现口径②的宿主：16 张 X-3 的共享实现模块（spec `x3-adjustment-entry-import-export`
#: design §C1；由该 spec **Wave 2 任务 4.1** 交付，在那之前磁盘上不存在）
_X3_SHARED_MODULE = "app.routers.wp_render_strategies._x3_adjustment_import_export"
_X3_SHARED_PATH = _IE_DIR / (_X3_SHARED_MODULE.rsplit(".", 1)[-1] + ".py")
#: 该模块的 specs 出口属性名（口径②的唯一查询点）
_X3_SPECS_ATTR = "X3_SHEET_SPECS"
#: X-3 作业面规模（16 张：L2-3 · L6-3 · M1-3~M10-3 · N1-3 · N2-3 · N3-3 · N5-3）。
#: 仅用于两处：态②「真取出 16 个 sheet 键」的下界、态①「暂缓集」的上界；不写任何 sheet 码字面量。
_X3_EXPECTED_SHEETS = 16
#: X-3 sheet 码形状（cycle = 字母 + 0~2 位数字，后缀恒 `-3`）。给态①的暂缓集封形状，
#: 使 `K1-4` 这类工厂 sheet 永远不可能借道暂缓（design §Data Models：sheet_code = `{CYCLE}-3`）。
_X3_SHEET_CODE_RE = re.compile(r"[A-Z]\d{0,2}-3")


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _router_default_storage_field(mod) -> str:
    """截取 `create_cycle_import_export_router(...)` 实参里的 storage_field（未传则工厂默认）。"""
    try:
        src = inspect.getsource(mod)
    except OSError:  # pragma: no cover
        return _FACTORY_DEFAULT_STORAGE_FIELD
    marker = "create_cycle_import_export_router("
    if marker not in src:
        return _FACTORY_DEFAULT_STORAGE_FIELD
    idx = src.index(marker)
    i = idx + len(marker)
    depth = 1
    while i < len(src) and depth:
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
        i += 1
    args = src[idx + len(marker):i - 1]
    m = re.search(r'storage_field\s*=\s*"([^"]*)"', args)
    return m.group(1) if m else _FACTORY_DEFAULT_STORAGE_FIELD


def _is_adjustment_spec(sheet: str, spec: dict) -> bool:
    title = str(spec.get("title") or "")
    item_id = str(spec.get("item_id") or f"{sheet}-rows")
    if "调整分录" in title:
        return True
    low = item_id.lower()
    return any(h in low for h in _ADJ_ITEM_ID_HINTS)


def _discover_factory_adjustment_sheets() -> dict[str, dict[str, Any]]:
    """遍历全部 `*_import_export.py` 的工厂式 `_X_SPECS`，返回调整 sheet 的实测三重键。"""
    found: dict[str, dict[str, Any]] = {}
    for f in sorted(_IE_DIR.glob("*_import_export.py")):
        if f.name == _X3_SHARED_PATH.name:
            # X-3 共享实现不是数据驱动工厂模块，其 specs 走口径②（`X3_SHEET_SPECS`）。
            # 它的文件名恰好也以 `_import_export.py` 结尾会被本 glob 捞到，故显式排除
            # ⇒ 两条口径按模块互斥，union 里不会出现同一张 sheet 的两个来源。
            continue
        mod_name = "app.routers.wp_render_strategies." + f.stem
        mod = importlib.import_module(mod_name)
        specs = None
        for attr in dir(mod):
            if re.fullmatch(r"_[A-Z0-9]+_SPECS", attr) and isinstance(getattr(mod, attr), dict):
                specs = getattr(mod, attr)
                break
        if not specs:
            continue
        router_default = _router_default_storage_field(mod)
        for sheet, spec in specs.items():
            if not isinstance(spec, dict) or "item_id" not in spec:
                continue
            if not _is_adjustment_spec(sheet, spec):
                continue
            found[sheet] = {
                "module": mod_name,
                "item_id": spec["item_id"],
                "storage_field_effective": spec.get("storage_field") or router_default,
                "field_keys": list(spec["field_keys"]),
                "headers": list(spec["headers"]),
            }
    return found


_DISCOVERED = _discover_factory_adjustment_sheets()


# ═══════════════════════════════════════════════════════════════════════════
# 发现口径② —— X-3 共享实现模块的 `X3_SHEET_SPECS`
#
# 【为什么这 16 张不走工厂 `_X_SPECS`】
#   16 张 X-3 调整分录汇总表（`L2-3` `L6-3` `M1-3`~`M10-3` `N1-3` `N2-3` `N3-3` `N5-3`）
#   的底稿实现在 16 个**专属 router**（`l2_interest_payable` / `m4_capital_reserve` / …）里，
#   不经 `create_cycle_import_export_router` 数据驱动工厂 ⇒ 它们没有 `_X_SPECS`。
#   其导入导出侧改为共用一份共享实现 `_x3_adjustment_import_export.py`，
#   Sheet_Spec 的唯一出口是 `X3_SHEET_SPECS`（spec `x3-adjustment-entry-import-export`
#   design §C1；`X3_SHEET_SPECS` 本身在模块导入时从本清单装载，两侧双向锁死）。
#   ⇒ 口径①的 `_[A-Z0-9]+_SPECS` 正则对这 16 张命中 0/16（实测：口径① 37 张，X-3 0 张），
#     故清单 `sheets` 迁入这 16 条的当刻，
#     `test_p9_contract_sheets_all_exist_in_backend` 会在**迁入正确**的情况下打红。
#     本口径就是为消掉那个假红而存在的（见该 spec tasks.md 任务 1.1 末尾的前置发现）。
#
# 【本口径的两态语义 —— 两条必须同时成立】
#   态① MODULE_ABSENT（今天）：共享实现模块尚未交付（**由该 spec Wave 2 任务 4.1 交付**）。
#        ⇒ 不因缺模块而报错：清单 `sheets` 里「形如 X-3 且已登记 `key_family`」的条目
#          按 `pending_shared_impl` 暂缓放行（并 warning 报数，绿但不静默）。
#   态② OK（任务 4.1 之后）：模块已交付 ⇒ **真 import 它、真读 `X3_SHEET_SPECS`、真取键**。
#        此时暂缓通道整体关闭（`_contract_sheets_not_backed` 只在态①才计算暂缓集），
#        16 张里缺任何一张都由 `test_p9_contract_sheets_all_exist_in_backend` 打红。
#
#   没有第三种「静默通过」：模块存在却缺 / 空 / 非映射 `X3_SHEET_SPECS`，
#   一律落 `SPECS_*` 状态并由 `test_x3_shared_specs_discovery_is_two_state` 打红 ——
#   否则「模块建了但 specs 没接上」会伪装成「尚未实现」= fail-open（本仓库最贵的一类假绿）。
#   同理：模块文件在磁盘上存在却 import 不到（内部 import 写错）也只落 SPECS_*/原样抛，
#   不会被吞成 MODULE_ABSENT。
# ═══════════════════════════════════════════════════════════════════════════


class _X3Status(enum.Enum):
    """口径②的实测状态。只有前两个是允许态，其余三个一律打红。"""

    MODULE_ABSENT = "module_absent"  # 态①：模块尚未交付（Wave 2 任务 4.1）
    OK = "ok"  # 态②：真取到非空 X3_SHEET_SPECS
    SPECS_MISSING = "specs_missing"  # 模块在、属性缺 ⇒ 接线错误，禁止当「尚未实现」
    SPECS_NOT_MAPPING = "specs_not_mapping"  # 模块在、属性类型错
    SPECS_EMPTY = "specs_empty"  # 模块在、specs 为空 ⇒ 装载失败被吞


class _X3Discovery(NamedTuple):
    status: _X3Status
    sheets: dict[str, Any]  # sheet 码 → spec 对象（口径②的发现结果）
    detail: str  # 人读诊断，进断言消息


def _import_x3_shared_module() -> types.ModuleType | None:
    """import 共享实现模块；**只有**「就是这个模块不存在」才返回 None。

    模块存在但其内部 import 写错时原样抛出 —— 吞掉会把接线错误伪装成「尚未实现」。
    """
    try:
        return importlib.import_module(_X3_SHARED_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == _X3_SHARED_MODULE:
            return None
        raise


def _extract_x3_specs(mod: types.ModuleType) -> _X3Discovery:
    """从（已 import 的）共享实现模块真取 `X3_SHEET_SPECS`。纯函数，便于替身自检。"""
    specs = getattr(mod, _X3_SPECS_ATTR, None)
    where = f"{getattr(mod, '__name__', mod)}.{_X3_SPECS_ATTR}"
    if specs is None:
        return _X3Discovery(_X3Status.SPECS_MISSING, {}, f"{where} 不存在")
    if not isinstance(specs, Mapping):
        return _X3Discovery(
            _X3Status.SPECS_NOT_MAPPING, {}, f"{where} 类型是 {type(specs).__name__}，应为 Mapping"
        )
    if not specs:
        return _X3Discovery(_X3Status.SPECS_EMPTY, {}, f"{where} 为空映射")
    return _X3Discovery(_X3Status.OK, dict(specs), f"{where} 取到 {len(specs)} 张: {sorted(specs)}")


def _discover_x3_shared_adjustment_sheets() -> _X3Discovery:
    mod = _import_x3_shared_module()
    if mod is None:
        return _X3Discovery(
            _X3Status.MODULE_ABSENT,
            {},
            f"{_X3_SHARED_MODULE} 尚未交付（Wave 2 任务 4.1）",
        )
    return _extract_x3_specs(mod)


_X3 = _discover_x3_shared_adjustment_sheets()


def _is_pending_x3_shared(sheet: str, entry: Any) -> bool:
    """该清单条目是否属「后端 spec 落在尚未交付的 X-3 共享实现里」⇒ 态①可暂缓。

    判据全部取自清单自身（单一真源，不在本文件写 sheet 码字面量）：
      * sheet 码形如 `{CYCLE}-3`；
      * 条目登记了 `key_family` —— 这是 X-3 条目独有的写入键族声明（任务 2.1 逐条写入），
        14 张既有工厂条目都没有它 ⇒ 暂缓通道不会漏放行普通工厂 sheet。
    """
    return (
        _X3_SHEET_CODE_RE.fullmatch(sheet) is not None
        and isinstance(entry, Mapping)
        and bool(entry.get("key_family"))
    )


def _contract_sheets_not_backed(
    contract_sheets: Mapping[str, Any],
    factory_sheets: Iterable[str],
    x3: _X3Discovery,
) -> tuple[list[str], list[str]]:
    """清单 `sheets` 里后端查不到的条目，拆成 (硬缺失, 态①暂缓)。

    发现面 = 口径① ∪ 口径②。暂缓集**只在态①计算**：共享实现一交付，
    暂缓通道即整体关闭，16 张缺一张就落进硬缺失。
    """
    backed = set(factory_sheets) | set(x3.sheets)
    missing = [s for s in contract_sheets if s not in backed]
    if x3.status is not _X3Status.MODULE_ABSENT:
        return missing, []
    pending = [s for s in missing if _is_pending_x3_shared(s, contract_sheets[s])]
    pending_set = set(pending)
    return [s for s in missing if s not in pending_set], pending


def test_guard_discovers_adjustment_sheets():
    """守卫自身有效性：必须真的发现到调整 sheet（否则遍历口径失效 → 守卫变空转）。"""
    assert len(_DISCOVERED) >= 14, f"仅发现 {len(_DISCOVERED)} 张调整 sheet，遍历口径疑似失效：{sorted(_DISCOVERED)}"


@pytest.mark.parametrize("sheet", sorted(_DISCOVERED))
def test_p11_every_backend_adjustment_sheet_is_registered(sheet, contract):
    """Property 11：后端调整 sheet 必须登记在清单 sheets 或 exempt。"""
    in_sheets = sheet in contract["sheets"]
    in_exempt = sheet in contract["exempt"] and not sheet.startswith("_")
    assert in_sheets or in_exempt, (
        f"后端调整 sheet {sheet}（{_DISCOVERED[sheet]['module']}）未登记到契约清单；"
        "请补 sheets 条目（纳入对齐）或 exempt 条目（写明豁免原因）"
    )


@pytest.mark.parametrize("sheet", sorted(_DISCOVERED))
def test_p9_backend_triple_matches_contract(sheet, contract):
    """Property 9：清单内 aligned 的 sheet，后端三重键逐字一致。"""
    if sheet not in contract["sheets"]:
        pytest.skip(f"{sheet} 属 exempt（{contract['exempt'][sheet]['kind']}）")
    entry = contract["sheets"][sheet]
    if entry["status"] != "aligned":
        pytest.skip(f"{sheet} 仍待对齐（status={entry['status']}）")
    actual = _DISCOVERED[sheet]
    mismatches = []
    if actual["item_id"] != entry["item_id"]:
        mismatches.append(f"item_id: 后端 {actual['item_id']!r} != 清单 {entry['item_id']!r}")
    if actual["storage_field_effective"] != entry["storage_field"]:
        mismatches.append(
            f"storage_field(有效): 后端 {actual['storage_field_effective']!r} != 清单 {entry['storage_field']!r}"
        )
    if actual["field_keys"] != entry["field_keys"]:
        mismatches.append(
            f"field_keys:\n    后端 {actual['field_keys']}\n    清单 {entry['field_keys']}"
        )
    assert not mismatches, f"{sheet} 契约漂移（{actual['module']}）:\n  " + "\n  ".join(mismatches)


def test_p9_contract_sheets_all_exist_in_backend(contract):
    """反向：清单 sheets 里的每张必须真的在后端注册（防清单登记了不存在的 sheet）。

    发现口径 = 工厂 `_X_SPECS`（口径①）**或** X-3 共享实现的 `X3_SHEET_SPECS`（口径②）。
    口径②的两态语义见上方成块注释：态①暂缓 X-3 条目、态②必须真取到键。
    """
    hard_missing, pending = _contract_sheets_not_backed(contract["sheets"], _DISCOVERED, _X3)

    # 暂缓集封顶：只可能是那 16 张 X-3。超出即说明暂缓通道被滥用（或清单被写脏），必须打红
    assert len(pending) <= _X3_EXPECTED_SHEETS, (
        f"态①暂缓集 {len(pending)} 条 > X-3 作业面 {_X3_EXPECTED_SHEETS} 张：{pending}；"
        f"暂缓通道只为 16 张 X-3 而开（{_X3.detail}）"
    )
    if pending:
        # 绿但不静默：让「16 条已迁入清单、后端共享实现还没交付」这个中间态在测试输出里可见，
        # 免得下一轮把「全绿」误读成「这 16 张的后端 spec 已核验过」
        warnings.warn(
            f"清单 sheets 有 {len(pending)} 条 X-3 暂缓待 {_X3_SHARED_MODULE} 交付"
            f"（Wave 2 任务 4.1）: {pending}",
            UserWarning,
            stacklevel=2,
        )

    assert not hard_missing, (
        f"清单 sheets 登记了后端未注册/未被识别为调整 sheet 的条目: {hard_missing}"
        f"（发现面：工厂 _X_SPECS {len(_DISCOVERED)} 张 + 口径② {len(_X3.sheets)} 张；{_X3.detail}）"
    )


def test_x3_shared_specs_discovery_is_two_state():
    """口径②只许两态，且两态都被真断言（态①不报错 / 态②不放过）。

    这条是口径② 的反空转锚点：`test_p9_contract_sheets_all_exist_in_backend` 在态①
    会因暂缓而变宽，若没有本条钉住「态②必须真取到 16 张」，缺模块就成了永久免检。
    """
    assert _X3.status in (_X3Status.MODULE_ABSENT, _X3Status.OK), (
        f"口径②落在非法态 {_X3.status.value}：{_X3.detail}。"
        f"模块已存在却取不到可用的 {_X3_SPECS_ATTR} ⇒ 这是接线错误，"
        f"不得被当成「尚未实现（Wave 2 任务 4.1）」放过"
    )

    if _X3.status is _X3Status.MODULE_ABSENT:
        assert not _X3_SHARED_PATH.exists(), (
            f"{_X3_SHARED_PATH} 在磁盘上存在，却 import 不到 {_X3_SHARED_MODULE} ⇒ "
            f"不是「尚未实现」而是模块自身 import/语法错误，禁止吞成缺失态"
        )
        assert not _X3.sheets, f"态①不应发现任何 sheet，实测 {sorted(_X3.sheets)}"
        return

    assert len(_X3.sheets) >= _X3_EXPECTED_SHEETS, (
        f"{_X3_SHARED_MODULE} 已交付，但 {_X3_SPECS_ATTR} 只有 {len(_X3.sheets)} 张 "
        f"（< 作业面 {_X3_EXPECTED_SHEETS}）: {sorted(_X3.sheets)}"
    )
    bad_shape = [s for s in _X3.sheets if _X3_SHEET_CODE_RE.fullmatch(s) is None]
    assert not bad_shape, f"{_X3_SPECS_ATTR} 出现非 X-3 形状的键: {bad_shape}"


@pytest.mark.parametrize(
    ("specs", "set_attr", "expected"),
    [
        (None, False, _X3Status.SPECS_MISSING),
        (None, True, _X3Status.SPECS_MISSING),
        ({}, True, _X3Status.SPECS_EMPTY),
        (["M4-3"], True, _X3Status.SPECS_NOT_MAPPING),
    ],
)
def test_x3_extraction_rejects_degenerate_specs(specs, set_attr, expected):
    """口径②反向自检：模块在但 specs 退化 ⇒ 必须落 SPECS_* 而不是「尚未实现」。"""
    mod = types.ModuleType("_x3_stand_in")
    if set_attr:
        setattr(mod, _X3_SPECS_ATTR, specs)
    assert _extract_x3_specs(mod).status is expected


def test_x3_extraction_really_reads_keys_from_module():
    """口径②反向自检：替身模块导出 `X3_SHEET_SPECS` ⇒ 必须真取到那些键（非恒返空集）。"""
    stand_in = types.ModuleType("_x3_stand_in")
    setattr(stand_in, _X3_SPECS_ATTR, {"M4-3": object(), "N5-3": object()})
    got = _extract_x3_specs(stand_in)
    assert got.status is _X3Status.OK
    assert set(got.sheets) == {"M4-3", "N5-3"}


def test_p9_criterion_catches_missing_key_once_shared_module_exists():
    """口径②反向自检：态②下 specs 少一张 ⇒ 该张必落硬缺失（不再走暂缓）。"""
    contract_sheets = {"M4-3": {"key_family": "per_field_plus_data"}, "N5-3": {"key_family": "single_json"}}

    full = _X3Discovery(_X3Status.OK, {"M4-3": object(), "N5-3": object()}, "stand-in")
    assert _contract_sheets_not_backed(contract_sheets, (), full) == ([], [])

    short = _X3Discovery(_X3Status.OK, {"M4-3": object()}, "stand-in")
    assert _contract_sheets_not_backed(contract_sheets, (), short) == (["N5-3"], [])


def test_p9_criterion_tolerates_only_pending_x3_entries_while_module_absent():
    """口径②反向自检：态①的暂缓只放行「形如 X-3 且登记 key_family」的条目，其余照旧打红。"""
    absent = _X3Discovery(_X3Status.MODULE_ABSENT, {}, "stand-in")
    contract_sheets = {
        "M4-3": {"key_family": "per_field_plus_data"},  # X-3 且有键族 ⇒ 暂缓
        "N5-3": {"item_id": "N5-3-entries"},  # 未登记 key_family ⇒ 不暂缓
        "K1-4": {"key_family": "per_field"},  # 非 X-3 形状 ⇒ 不暂缓
    }
    hard, pending = _contract_sheets_not_backed(contract_sheets, (), absent)
    assert pending == ["M4-3"]
    assert hard == ["N5-3", "K1-4"]

    # 口径①命中的条目不进任何一边（发现面是 union）
    assert _contract_sheets_not_backed(contract_sheets, contract_sheets, absent) == ([], [])


def test_exempt_entries_have_kind_and_reason(contract):
    """豁免必须可区分：每条 exempt 有已登记的 kind + 非空 reason。"""
    kinds = set(contract["exempt"]["_exempt_kinds"])
    bad = []
    for sheet, e in contract["exempt"].items():
        if sheet.startswith("_"):
            continue
        if not isinstance(e, dict) or e.get("kind") not in kinds or not e.get("reason"):
            bad.append(sheet)
    assert not bad, f"exempt 条目缺 kind/reason 或 kind 未登记: {bad}"


def test_no_sheet_both_registered_and_exempt(contract):
    dup = sorted(set(contract["sheets"]) & {k for k in contract["exempt"] if not k.startswith("_")})
    assert not dup, f"同一 sheet 既在 sheets 又在 exempt: {dup}"


# ═══════════════════════════════════════════════════════════════════════════
# Property 6 —— 中央通道三者列集合互相兼容
# ═══════════════════════════════════════════════════════════════════════════


def _summary_export_headers() -> list[str]:
    """从 `_write_adj_sheet` 源码提取汇总导出列头（唯一真源，避免复制常量）。"""
    from app.routers import adjustments as adj_router

    src = inspect.getsource(adj_router._write_adj_sheet)
    m = re.search(r"headers\s*=\s*\[(.*?)\]", src, re.S)
    assert m, "未能从 _write_adj_sheet 提取 headers"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_p6_central_required_columns_compatible_with_both_templates():
    """中央导入必填列 ⊆ 富模板列，且（经别名规范化后）⊆ 汇总导出列。"""
    from app.services.import_template_service import (
        TEMPLATE_COLUMNS,
        ImportType,
        normalize_adjustment_header,
    )

    cols = TEMPLATE_COLUMNS[ImportType.adjustments]
    required = [c[0] for c in cols if c[1]]
    rich = [c[0] for c in cols]
    assert required, "调整分录模板必填列不应为空"
    assert set(required) <= set(rich)

    summary_norm = {normalize_adjustment_header(h) for h in _summary_export_headers()}
    missing = [h for h in required if h not in summary_norm]
    assert not missing, (
        f"汇总导出列（规范化后 {sorted(summary_norm)}）缺中央导入必填列 {missing} → "
        "导出的汇总无法直接导回（Property 6）"
    )
