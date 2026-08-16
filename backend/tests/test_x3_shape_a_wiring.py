"""GS3b —— 形态 A 接线守卫（X-3 短前缀三态端点 + `IE_SHEETS` 唯一真源）。

spec: `x3-adjustment-entry-import-export` · Wave 3 任务 5.1
_Requirements: 4.1, 4.4, 1.6, 9.6, 11.5_

## 为什么任务 5.1 必须**新增**这一条守卫（变异检验实测出的守卫缺口）

任务 5.1 的施加物是「14 个宿主模块各挂 3 条形态 A 端点 + 各声明 `IE_SHEETS`」。
按 R10.2 逐条做变异时实测到两个 **GREEN（守卫缺陷）**：

1. **把某模块的 `attach_shape_a_routes(...)` 调用删掉** —— 全库无一条判据打红。
   路由计数类判据（`test_ie_route_inventory` 的三态端点分布 / 分组数 / 形态 A 前缀数）
   在任务 6.3 上调基线**之前**本来就是红的，红→红分辨不出少了一条端点；而
   `test_ie_prefix_reachability` 只查形态 B 与白名单内容，不查形态 A 是否真注册。
   ⇒ 少挂一个前缀的三态端点会**静默通过**，表现成「那张表的导入导出入口点了没反应」。

2. **把 `_X3_CODES` 的清单反查改成写死字面量**（如 `frozenset({"M4-3"})`）—— 同样无一条
   判据打红。它的运行期取值与反查结果**完全相同**，故任何值判据都抓不到；只有结构判据
   （剥注释后代码行内是否出现 X-3 字面量）能抓。既有的字面量扫描器只扫共享实现
   `_x3_adjustment_import_export.py` 一个文件，不扫这 16 个宿主模块。
   ⇒ 前端改键 / 清单改码时，写死的那一份不会打红 = 平台最贵的那类假绿（后端第二真源）。

两条都按 R10.4 处置：**补守卫**，不是改变异。

## 判据一律落在运行期结构或源码结构上，不查「源码里有没有某个字符串」

- 宿主模块**不写第二份映射表**：从运行期 `app.routes` 的形态 B 端点反查
  `endpoint.__module__` 得到（与任务 1.5 同一手法），长前缀清单直接 import 任务 1.5 的
  `_X3_DEDICATED_LONG_PREFIXES`。
- X-3 码两路派生**互为对照**：①清单 `X3_SHEET_SPECS` 按 `api_prefix` 反查（= 生产代码
  用的那条路）②长前缀派生 `{SHORT.upper()}-3`。两路必须一致 —— 只用①的话，清单被改坏时
  生产与守卫会一起错、判据静默失效。
- `sheet` 是否必填取 FastAPI 已解析的 `dependant.query_params[].field_info.is_required()`。
  🔴 **不得**写 `getattr(field, "required", False)`：该属性在 `fastapi._compat.v2.ModelField`
  上**不存在**，带默认值的 `getattr` 会 fail-open 把 42 个必填参数全判成「非必填」
  （本任务施工期真踩过，首版探针据此误报 42 条失败）。判据不可用时本文件一律**失败**，
  不返回「看起来没问题」。

## 反空转锚点

`test_scan_surface_hosts_resolved` 先把作业面钉住：16 个长前缀必须各解析到宿主模块、
各有 3 条形态 B 端点。少一条即本文件其余结论都是「没查到」而不是「查过了没问题」。

## 施加状态（本文件会自己报出来，不靠注释口头约定）

- 任务 5.1 作业面 = 14 个（`l6` `m2`~`m10` `n1` `n2` `n3` `n5`）：已接线。
- 任务 5.2 作业面 = `l2` / `m1`（`_TASK_52_HOSTS`）：**已接线**（2026-08-14）。
  `_PENDING_TASK_52` 随之改为**空集**，`test_wired_hosts_*` 两条的期望数由 14/42 变 16/48，
  原「现状登记」那条反转为 `test_task_52_hosts_are_wired`。
- 这两个前缀还额外给六个既有形态 B handler 追加了 `sheet: str | None = Query(None)`
  （additive，`None` ⇒ 既有行为逐字不变），其可达性判据在
  `tests/test_ie_prefix_reachability.py`（同一批反转）。
"""

from __future__ import annotations

import importlib
import io
import re
import tokenize
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.routers.wp_render_strategies._x3_adjustment_import_export import X3_SHEET_SPECS
from tests.test_ie_prefix_reachability import _X3_DEDICATED_LONG_PREFIXES

#: 三态后缀（与 design §C1 / 前端共享 composable 同一组字面量）
_ACTIONS: tuple[str, ...] = ("export-template", "export-data", "import-data")

#: 形态 A 三态的唯一合法宿主实现（R1.5：现存两套已够，不造第三套）
_SHARED_IMPL = "app.routers.wp_render_strategies._x3_adjustment_import_export"

#: 形态 A 三态一律 POST（前端共享 composable `useWorkpaperImportExport` 唯一支持的形态）
_SHAPE_A_METHOD = "POST"

#: 任务 5.2 的作业面（`l2` / `m1` 两个长前缀，另需给六个既有 handler 追加 `sheet` 参数）。
_TASK_52_HOSTS: frozenset[str] = frozenset(
    {"l2-interest-payable", "m1-dividends-payable"}
)

#: 「尚未接线」的待办集 —— **任务 5.2 已施加完毕，故为空集**（2026-08-14）。
#:
#: 🔴 只许缩小、不许再填回去：下面 `test_wired_hosts_*` 两条的期望数按
#: `16 - len(_PENDING_TASK_52)` 派生 ⇒ 往这里塞前缀就是把它从实判里摘出去。
_PENDING_TASK_52: frozenset[str] = frozenset()

#: 既有形态 B 三态的 HTTP 方法 —— 16 个长前缀逐个运行期实测（2026-08-13）。
#:
#: 🔴 这里同时是对 design §逐张两列实测值表的**更正**：那张表 13 行的方法列一律写成
#: `POST` × 3，与运行期实测不符。实测分两组：
#:   · **15 / 16 = GET / GET / POST**（含本任务的 14 个与 `l2-interest-payable`）
#:   · **1 / 16 = POST / POST / POST** —— 仅 `m1-dividends-payable`
#: 任务 5.2 要给这两个前缀的六个既有 handler 追加 `sheet`，若按「三态全 POST」或
#: 「导出全 GET」任一种套公式，都会有一侧对不上。
_LEGACY_SHAPE_B_METHOD_DEFAULT: dict[str, str] = {
    "export-template": "GET",
    "export-data": "GET",
    "import-data": "POST",
}

#: 逐前缀例外（只此一个；空 dict 会让上面的默认表被当成 16/16 通用，属把实测抹平）
_LEGACY_SHAPE_B_METHOD_OVERRIDE: dict[str, dict[str, str]] = {
    "m1-dividends-payable": {
        "export-template": "POST",
        "export-data": "POST",
        "import-data": "POST",
    },
}


def _legacy_methods(long_prefix: str) -> dict[str, str]:
    return _LEGACY_SHAPE_B_METHOD_OVERRIDE.get(long_prefix, _LEGACY_SHAPE_B_METHOD_DEFAULT)

#: 既有 sheet 白名单的宿主模块级载体（前 5 条 = 任务 5.1 施加前就有；后 2 条 = 任务 5.2
#: 为 `l2` / `m1` **派生**出来的，取值分别来自既有 `_SHEET_NAME` 与 service 的 `EXPORT_SHEETS`）。
#:
#: 载体名与形态逐个不同，故此处逐个登记而不套公式：
#:   `_SUPPORTED_SHEETS`（set，n1/n3/n5）· `SUPPORTED_SHEETS`（set，**无下划线前缀**，n2）
#:   · `_SHEET_CONFIGS`（**dict**，键 = sheet 码、值 = 列头/字段配置，l6）
#:   · `_LEGACY_SHEETS`（frozenset，l2 —— 由 `_SHEET_NAME = "L2-2 明细表"` 取首段派生；
#:     该模块的既有载体是 sheet **标题**而非码，直接登记标题无法与 X-3 码比对）
#:   · `EXPORT_SHEETS`（list，m1 —— 真源在 `m1_dividends_payable_service`，router 只 import）
#:
#: 值本身是「已确证正确」的既有生产取值（R8.6），故可入基线：本 spec 的义务是让它们
#: **逐字不变**，任何变动都意味着改到了既有形态 B 的可服务面。
#: 🔴 `l2` / `m1` 这两条尤其要盯：前端 `useL2ImportExport` / `useM1ImportExport` 一直在传
#: 这些码（4 个组件 12 处调用），任务 5.2 之后它们会被 `sheet ∉ IE_SHEETS ⇒ 400` 那条分支
#: 判定 —— 白名单少一张即线上该页导入导出全废。
_LEGACY_WHITELIST: dict[str, tuple[str, frozenset[str]]] = {
    "l2-interest-payable": ("_LEGACY_SHEETS", frozenset({"L2-2"})),
    "l6-special-payables": ("_SHEET_CONFIGS", frozenset({"L6-2"})),
    "m1-dividends-payable": ("EXPORT_SHEETS", frozenset({"M1-2", "M1-4", "M1-5"})),
    "n1-deferred-tax-assets": ("_SUPPORTED_SHEETS", frozenset({"N1-2", "N1-4", "N1-5"})),
    "n2-taxes-payable": (
        "SUPPORTED_SHEETS",
        frozenset({"N2-2", "N2-6", "N2-8", "N2-9", "N2-10"}),
    ),
    "n3-deferred-tax-liabilities": ("_SUPPORTED_SHEETS", frozenset({"N3-2"})),
    "n5-income-tax-expense": ("_SUPPORTED_SHEETS", frozenset({"N5-2", "N5-5"})),
}

#: 剥注释后用于扫 X-3 字面量的正则（作业面 16 个码由清单给出，不写死）
_X3_LITERAL_RE = re.compile("|".join(re.escape(c) for c in sorted(X3_SHEET_SPECS)))


def _short(long_prefix: str) -> str:
    """`m10-other-equity-instruments` → `m10`。"""
    return long_prefix.split("-", 1)[0]


def _x3_from_ledger(short: str) -> str | None:
    """清单按 `api_prefix` 反查 X-3 码 —— 生产代码用的就是这条路。"""
    hits = sorted(c for c, s in X3_SHEET_SPECS.items() if s.api_prefix == short)
    return hits[0] if len(hits) == 1 else None


def _x3_from_pattern(short: str) -> str:
    """长前缀派生 —— 与清单反查互为对照，防「两侧一起错」。"""
    return f"{short.upper()}-3"


def _methods(route: Any) -> frozenset[str]:
    return frozenset(
        str(m).upper()
        for m in (getattr(route, "methods", None) or ())
        if str(m).upper() not in {"HEAD", "OPTIONS"}
    )


def _code_only(path: Path) -> str:
    """剥掉 `#` 注释与独立成句的字符串（docstring），保留代码行。

    保留代码行内的字符串字面量 —— 「写死一份 X-3 码」正是以代码行内字面量的形态出现。
    """
    src = path.read_text(encoding="utf-8")
    out: list[str] = []
    prev_end = (1, 0)
    prev_type = tokenize.INDENT
    for tok_type, text, start, end, _ in tokenize.generate_tokens(io.StringIO(src).readline):
        if start[0] > prev_end[0]:
            out.append("\n" * (start[0] - prev_end[0]))
            prev_end = (start[0], 0)
        if start[1] > prev_end[1]:
            out.append(" " * (start[1] - prev_end[1]))
        if tok_type == tokenize.COMMENT:
            pass
        elif tok_type == tokenize.STRING and prev_type in (
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.NEWLINE,
            tokenize.NL,
        ):
            pass
        else:
            out.append(text)
        if tok_type not in (tokenize.NL, tokenize.COMMENT):
            prev_type = tok_type
        prev_end = end
    return "".join(out)


@pytest.fixture(scope="module")
def x3_hosts() -> dict[str, ModuleType]:
    """长前缀 → 宿主模块对象，从运行期形态 B 端点的 `__module__` 反查得到。

    刻意不写第二份「前缀 → 模块名」映射表：抄一份就有第二个真源，改一处漏一处
    （父 spec 已因导入别名同名把 `l1` 误判过一次）。
    """
    from app.main import app

    pattern = re.compile(r"^/api/([\w-]+)/\{wp_id\}/(" + "|".join(_ACTIONS) + r")$")
    found: dict[str, set[str]] = {}
    for route in app.routes:
        m = pattern.match(getattr(route, "path", "") or "")
        if not m or m.group(1) not in _X3_DEDICATED_LONG_PREFIXES:
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        found.setdefault(m.group(1), set()).add(getattr(endpoint, "__module__", "?"))

    hosts: dict[str, ModuleType] = {}
    for long_prefix, modules in found.items():
        assert len(modules) == 1, (
            f"{long_prefix} 的三条形态 B 端点分散在多个模块 {sorted(modules)} —— "
            "宿主判定不可信，本文件其余结论一律不成立"
        )
        hosts[long_prefix] = importlib.import_module(next(iter(modules)))
    return hosts


def test_scan_surface_hosts_resolved(x3_hosts: dict[str, ModuleType]) -> None:
    """反空转锚点：16 个长前缀各解析到唯一宿主模块（否则下面的绿都是空转）。"""
    assert len(_X3_DEDICATED_LONG_PREFIXES) == 16, (
        f"作业面清单规模变了：{len(_X3_DEDICATED_LONG_PREFIXES)} != 16 —— "
        "长前缀表来自任务 1.5，改它须同步改 spec 作业面声明"
    )
    missing = sorted(set(_X3_DEDICATED_LONG_PREFIXES) - set(x3_hosts))
    assert not missing, (
        f"以下长前缀在运行期解析不到宿主模块：{missing}\n"
        "→ app 未装配好或形态 B 路径改版；此时「形态 A 已挂载」「白名单含 X-3」都会恒真变绿"
    )


def test_ledger_and_pattern_derived_x3_codes_agree() -> None:
    """X-3 码两路派生必须一致（清单反查 ↔ 长前缀派生），16/16。"""
    problems: list[str] = []
    for long_prefix in _X3_DEDICATED_LONG_PREFIXES:
        short = _short(long_prefix)
        ledger, pattern = _x3_from_ledger(short), _x3_from_pattern(short)
        if ledger != pattern:
            problems.append(f"{short}: 清单反查 {ledger!r} != 长前缀派生 {pattern!r}")
    assert not problems, (
        "X-3 码两路派生分叉：\n"
        + "\n".join(f"  · {p}" for p in problems)
        + "\n→ 生产代码走的是清单反查这一路；两路不一致时本文件的比对基准本身不可信"
    )


def test_wired_hosts_declare_ie_sheets_with_x3(x3_hosts: dict[str, ModuleType]) -> None:
    """已接线宿主（5.1 的 14 个 + 5.2 的 2 个 = 16）：`IE_SHEETS` 存在、是 frozenset、含各自 X-3（R4.4）。"""
    problems: list[str] = []
    checked: list[str] = []
    for long_prefix in _X3_DEDICATED_LONG_PREFIXES:
        if long_prefix in _PENDING_TASK_52:
            continue
        module = x3_hosts.get(long_prefix)
        if module is None:
            continue  # test_scan_surface_hosts_resolved 已负责报
        checked.append(long_prefix)
        ie_sheets = getattr(module, "IE_SHEETS", None)
        code = _x3_from_ledger(_short(long_prefix))
        if ie_sheets is None:
            problems.append(f"{long_prefix}: 未声明 IE_SHEETS")
        elif not isinstance(ie_sheets, frozenset):
            problems.append(
                f"{long_prefix}: IE_SHEETS 类型 {type(ie_sheets).__name__}，"
                "期望 frozenset（白名单要能做集合运算且不可变）"
            )
        elif code not in ie_sheets:
            problems.append(f"{long_prefix}: IE_SHEETS 缺 {code}，现值 {sorted(ie_sheets)}")
    expected = len(_X3_DEDICATED_LONG_PREFIXES) - len(_PENDING_TASK_52)
    assert len(checked) == expected == 16, (
        f"只检查到 {len(checked)} 个已接线前缀（期望 {expected}）—— 作业面被静默缩小"
    )
    assert not problems, (
        "以下宿主模块的 `IE_SHEETS` 不合格（任务 5.1 / 5.2）：\n"
        + "\n".join(f"  · {p}" for p in problems)
        + "\n→ `IE_SHEETS` 是该前缀 sheet 白名单的唯一真源（R4.4），"
        "形态 A 端点收到 sheet=X-3 时靠它放行"
    )


def test_wired_hosts_register_shape_a_three_state(x3_hosts: dict[str, ModuleType]) -> None:
    """已接线宿主（16 个）：各 3 条形态 A 路由，路径逐字、方法 POST、`sheet` 必填。

    🔴 这条就是「删掉 `attach_shape_a_routes(...)` 调用」那个变异的检测通道
    （施加前实测：全库无一条判据能抓到它 = GREEN 守卫缺陷，故本条为新增）。
    """
    problems: list[str] = []
    seen = 0
    for long_prefix in _X3_DEDICATED_LONG_PREFIXES:
        if long_prefix in _PENDING_TASK_52:
            continue
        module = x3_hosts.get(long_prefix)
        if module is None:
            continue
        short = _short(long_prefix)
        routes = list(getattr(getattr(module, "router", None), "routes", []))
        for action in _ACTIONS:
            want = f"/api/workpapers/{{wp_id}}/{short}/{action}"
            hit = [r for r in routes if getattr(r, "path", "") == want]
            if len(hit) != 1:
                problems.append(
                    f"{short}/{action}: `{want}` 命中 {len(hit)} 条（期望 1）"
                    + ("（挂载调用缺失或路径漂移）" if not hit else "（重复注册，first-wins 静默失效）")
                )
                continue
            route = hit[0]
            seen += 1
            methods = sorted(_methods(route))
            if methods != [_SHAPE_A_METHOD]:
                problems.append(f"{short}/{action}: 方法 {methods} != ['{_SHAPE_A_METHOD}']")
            host_impl = getattr(getattr(route, "endpoint", None), "__module__", "?")
            if host_impl != _SHARED_IMPL:
                problems.append(
                    f"{short}/{action}: 端点宿主 {host_impl} != 共享实现 {_SHARED_IMPL}"
                    "（R1.5：不许再抄一套三态实现）"
                )
            # `sheet` 必填 —— 判据不可用时失败，不返回「看起来没问题」
            required: dict[str, bool] = {}
            for field in getattr(getattr(route, "dependant", None), "query_params", []) or []:
                info = getattr(field, "field_info", None)
                if info is None or not hasattr(info, "is_required"):
                    problems.append(
                        f"{short}/{action}: 无法判定 query 参数 {getattr(field, 'name', '?')!r} "
                        f"是否必填（field_info={type(info).__name__}）—— 判据失效"
                    )
                    continue
                required[field.name] = bool(info.is_required())
            if not required.get("sheet", False):
                problems.append(
                    f"{short}/{action}: `sheet` 非必填（query_params={required}）—— "
                    "FastAPI 对未声明/可选的 sheet 会静默丢弃或落默认值，导出到别张表"
                )
    assert seen == 48, (
        f"只枚举到 {seen} 条形态 A 路由（期望 48 = 16 前缀 × 3 态）—— "
        "扫描面缩小时下面的「没有问题」是空转出来的"
    )
    assert not problems, (
        "形态 A 三态接线不合格（任务 5.1 / 5.2）：\n" + "\n".join(f"  · {p}" for p in problems)
    )


def test_legacy_shape_b_methods_and_paths_unchanged(x3_hosts: dict[str, ModuleType]) -> None:
    """既有形态 B 三态的路径与 HTTP 方法逐字不变（R1.6）。

    方法基线 = 逐前缀运行期实测：15 个 GET/GET/POST + `m1` 一个 POST×3
    （design 表的 POST×3 通用写法有误，见 `_LEGACY_SHAPE_B_METHOD_DEFAULT` 的说明）。
    """
    problems: list[str] = []
    seen = 0
    for long_prefix in _X3_DEDICATED_LONG_PREFIXES:
        module = x3_hosts.get(long_prefix)
        if module is None:
            continue
        routes = list(getattr(getattr(module, "router", None), "routes", []))
        for action, expected in _legacy_methods(long_prefix).items():
            want = f"/api/{long_prefix}/{{wp_id}}/{action}"
            hit = [r for r in routes if getattr(r, "path", "") == want]
            if len(hit) != 1:
                problems.append(f"{long_prefix}/{action}: `{want}` 命中 {len(hit)} 条（期望 1）")
                continue
            seen += 1
            methods = sorted(_methods(hit[0]))
            if methods != [expected]:
                problems.append(f"{long_prefix}/{action}: 方法 {methods} != ['{expected}']")
    assert seen == 48, (
        f"只枚举到 {seen} 条形态 B 路由（期望 48 = 16 前缀 × 3 态）—— 扫描面缩小"
    )
    # 例外表非空自检：写成空 dict 会把「15 + 1」的实测抹平成 16/16 通用
    assert _LEGACY_SHAPE_B_METHOD_OVERRIDE, (
        "方法例外表被清空 —— 实测有 1 个前缀（m1）是 POST×3，抹平后该前缀的方法漂移抓不到"
    )
    assert not problems, (
        "既有形态 B 端点的路径/方法被改动（违反 R1.6「既有端点逐字不动」）：\n"
        + "\n".join(f"  · {p}" for p in problems)
    )


def test_legacy_whitelist_is_single_sourced_from_ie_sheets(
    x3_hosts: dict[str, ModuleType],
) -> None:
    """7 个有既有白名单载体的宿主：`IE_SHEETS - {X-3}` == 既有白名单，且取值逐字不变。

    这条抓的是「影子白名单」——`IE_SHEETS` 与既有白名单各写一份字面量、两边独立漂移。
    等式成立 ⇔ 两者中只有一份是声明、另一份由它派生（哪个方向都行）。
    """
    problems: list[str] = []
    for long_prefix, (name, baseline) in _LEGACY_WHITELIST.items():
        module = x3_hosts.get(long_prefix)
        if module is None:
            problems.append(f"{long_prefix}: 宿主模块未解析到")
            continue
        raw = getattr(module, name, None)
        if raw is None:
            problems.append(f"{long_prefix}: 既有白名单载体 {name} 不存在（改名/删除？）")
            continue
        actual = frozenset(raw)  # dict 取键集、set/frozenset 原样
        if actual != baseline:
            problems.append(
                f"{long_prefix}.{name} 取值变了：{sorted(actual)} != 基线 {sorted(baseline)}"
                " —— 既有形态 B 的可服务面被改动（R1.6）"
            )
        ie_sheets = getattr(module, "IE_SHEETS", None)
        code = _x3_from_ledger(_short(long_prefix))
        if isinstance(ie_sheets, frozenset):
            derived = ie_sheets - {code}
            if derived != actual:
                problems.append(
                    f"{long_prefix}: IE_SHEETS - {{{code}}} = {sorted(derived)} != "
                    f"{name} = {sorted(actual)} ⇒ 两份白名单已分叉（影子真源）"
                )
    assert len(_LEGACY_WHITELIST) == 7, "既有白名单登记数变了，须同步核对实测"
    assert not problems, (
        "既有 sheet 白名单与 `IE_SHEETS` 不同源或取值变动：\n"
        + "\n".join(f"  · {p}" for p in problems)
        + "\n→ R4.4 要求白名单有唯一真源；两份各写字面量时改一处漏一处不会打红"
    )


def test_host_modules_have_no_x3_literal(x3_hosts: dict[str, ModuleType]) -> None:
    """剥注释/docstring 后，宿主模块**代码行内**不得出现任何 X-3 字面量。

    🔴 这条是「把 `_X3_CODES` 的清单反查改成写死字面量」那个变异的唯一检测通道：
    写死后运行期取值与反查结果完全相同 ⇒ 一切值判据都抓不到，只有结构判据能抓。
    """
    problems: list[str] = []
    scanned = 0
    for long_prefix in _X3_DEDICATED_LONG_PREFIXES:
        module = x3_hosts.get(long_prefix)
        if module is None:
            continue
        source = getattr(module, "__file__", None)
        if not source:
            problems.append(f"{long_prefix}: 取不到模块源文件路径")
            continue
        scanned += 1
        found = sorted(set(_X3_LITERAL_RE.findall(_code_only(Path(source)))))
        if found:
            problems.append(
                f"{long_prefix}（{Path(source).name}）: 代码行内出现 X-3 字面量 {found}"
            )
    assert scanned == 16, f"只扫了 {scanned} 个宿主模块（期望 16）—— 扫描面缩小，零命中不可信"
    assert len(_X3_LITERAL_RE.pattern) > 40, (
        "X-3 字面量正则疑似空转（模式过短）—— 清单作业面为空时会把「零命中」判成通过"
    )
    assert not problems, (
        "宿主模块内出现 X-3 字面量（禁硬编码，design §C2）：\n"
        + "\n".join(f"  · {p}" for p in problems)
        + "\n→ X-3 码一律从 `X3_SHEET_SPECS` 按短前缀反查；写死一份就是后端第二真源，"
        "前端改键或清单改码时不会打红"
    )


def test_task_52_hosts_are_wired(x3_hosts: dict[str, ModuleType]) -> None:
    """任务 5.2 已接线：`l2` / `m1` 各有 `IE_SHEETS` 与 3 条形态 A 路由，待办集为空。

    施加前本条是【现状登记】（`test_pending_task_52_hosts_not_yet_wired`，断言这两个前缀
    **未**接线）；5.2 施加后按其断言消息的指引反转成本形态 —— 反转而非删除，
    否则「`_PENDING_TASK_52` 被人重新填上以换取上面两条变绿」就没人盯了。
    """
    assert _TASK_52_HOSTS <= set(_X3_DEDICATED_LONG_PREFIXES), (
        f"_TASK_52_HOSTS 有不在专属前缀清单里的项："
        f"{sorted(_TASK_52_HOSTS - set(_X3_DEDICATED_LONG_PREFIXES))}"
    )
    assert not _PENDING_TASK_52, (
        f"_PENDING_TASK_52 非空：{sorted(_PENDING_TASK_52)}\n"
        "→ 任务 5.2 已收口，该集合应保持空集；往里塞前缀会让上面两条的期望数"
        "（16 - len(_PENDING_TASK_52)）自动减小 = 把该前缀从实判里摘出去"
    )
    problems: list[str] = []
    for long_prefix in sorted(_TASK_52_HOSTS):
        module = x3_hosts.get(long_prefix)
        if module is None:
            problems.append(f"{long_prefix}: 宿主模块未解析到")
            continue
        short = _short(long_prefix)
        routes = list(getattr(getattr(module, "router", None), "routes", []))
        shape_a = sorted(
            getattr(r, "path", "")
            for r in routes
            if getattr(r, "path", "").startswith(f"/api/workpapers/{{wp_id}}/{short}/")
        )
        ie_sheets = getattr(module, "IE_SHEETS", None)
        if ie_sheets is None:
            problems.append(f"{long_prefix}: 未声明 IE_SHEETS")
        if len(shape_a) != len(_ACTIONS):
            problems.append(
                f"{long_prefix}: 形态 A 路由 {len(shape_a)} 条（期望 {len(_ACTIONS)}）：{shape_a}"
            )
    assert not problems, (
        "任务 5.2 的两个宿主接线不完整：\n"
        + "\n".join(f"  · {p}" for p in problems)
        + "\n→ 5.2 的施加物 = `IE_SHEETS` + `attach_shape_a_routes`，两者缺一即该前缀的"
        "单份 UI 通路不可达（bulk 侧 `_endpoint_for` 也解析不到形态 A）"
    )
