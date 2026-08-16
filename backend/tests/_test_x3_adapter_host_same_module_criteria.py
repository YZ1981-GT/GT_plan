"""test_x3_adapter_host_same_module —— 判据层（常量 / 登记表 / fixture / 纯函数 / 取证 helper）。

从 `backend/tests/test_x3_adapter_host_same_module.py` 拆出：原文件 882 行 > pre-commit 的 800 行门禁。
**不加 file_size_whitelist** —— 白名单表头写明「仅历史大文件」，新增文件
套用属滥用。

刻意与用例文件**同目录**：判据里的 `Path(__file__).parents[N]` 路径推算
移到子目录会整体错一层（实测过，会变成 fixture setup 全 ERROR）。

用例层的 import 清单由拆分脚本按其**实际引用**算出，不手写 —— 漏一个名字
就是 collection error，会让整份守卫的断言零执行而表面上「没有失败」。

原文件 docstring 原样保留在下方。
"""

from __future__ import annotations

"""GS6 同源宿主守卫 —— Wave 0 任务 1.4（spec: `x3-adjustment-entry-import-export`）

## 不变量

∀ 一个短前缀 `p`：**运行期形态 A 端点的宿主模块** 必须与 **`_PREFIX_TO_MODULE[p]`
（bulk adapter 的目标模块）实际解析出的端点所在模块** 同一。

不同 ⇒ **split-brain**：同一个 `api_prefix` 下，界面（单份 UI 通路）跑专属 router
模块的实现，批量（bulk 通路）跑工厂模块的实现 ⇒ 改一处忘一处，且两侧列面/键面
不一致时用户看到的是「单份导出对、批量导出错」这类只在 ZIP 里暴露的静默偏差。

**违规集基线 = 5**（`h7` / `l1` / `l3` / `l4` / `l5`，design E8）。基线**只许下调**：
新增违规立刻打红；下调是好事，但必须同步下调本文件基线并在 spec Notes 留痕。

本守卫**只读事实**，预期全绿；本 spec 施加改动（design §C3 把 16 个短前缀改指专属
模块）后仍须保持 5（tasks.md 任务 6.1 的验收条件之一）。

## 🔴 口径一：形态 A 必须按「严格形态」判，不能沿用清册的粗口径

`test_ie_route_inventory.classify_route_shapes` 的粗口径是「`segs[-2]` 不是路径参数
段」⇒ 得 85 个前缀。但 design 说的形态 A 是**具体一种 URL**：

    形态 A  /api/workpapers/{wp_id}/{prefix}/{三态}     ← 本守卫作业面（94 个前缀）
    形态 B  /api/{prefix}/{wp_id}/{三态}                ← 不判（前端共享 composable 不支持）

粗口径比严格口径多出 7 个前缀，它们是**第三种形态**，逐个实测：

| 前缀 | 实际路径 | 为什么不是形态 A |
|---|---|---|
| `h5` / `n4` | `/api/h5/export-data` | 路径里**根本没有 `{wp_id}` 段**（wp_id 走请求体） |
| `disclosure` | `/api/workpapers/{wp_id}/d1/disclosure/export-data` | 前缀占两段，`segs[-3]` 是 `d1` 不是参数 |
| `adjustments` / `bulk-tab` | `/api/projects/{project_id}/…` | 挂在项目下，非底稿下 |
| `import-export` / `staff` | `/api/formula-management/import-export/…` 等 | 与底稿三态族无关 |

**这 7 个里 `h5` 与 `n4` 会污染判据**：它们的 `/api/{prefix}/{三态}` 端点由专属
router（`h5_oil_gas_assets` / `n4_taxes_and_surcharges`）提供，而 adapter 目标是
工厂模块 ⇒ 粗口径下违规集会变成 **7** 而不是 5。若有人为了「让守卫通过」把口径放宽
到粗口径，再把基线从 5 抬到 7，就是把一个**口径错误**锁成基线（memory 假绿三源之三）。
`test_coarse_criterion_would_add_known_non_shape_a_prefixes` 钉死这两个前缀属
「粗口径假阳性」，`test_baseline_rejects_stale_figures` 钉死基线不得被抬到 7。

严格口径同时与 design E7 的划分自洽：`_PREFIX_TO_MODULE` 的 89 键里
**68 键**有形态 A 三态、**21 键**没有（`h5`/`h9`/`l2`/`l6`/`l7`/`l8`/`m1`~`m10`/
`n1`/`n2`/`n3`/`n4`/`n5`）—— 实测与 E7 逐字相符。粗口径会算成 70/19。

🔴 **2026-08-14（任务 6.3）上调**：X-3 施加后 16 个短前缀（`l2`/`l6`/`m1`~`m10`/
`n1`/`n2`/`n3`/`n5`）获得严格形态 A 三态，划分变成 **84 / 5**，剩下的 5 个是
`h5`/`h9`/`l7`/`l8`/`n4`（`_KEYS_WITHOUT_STRICT_SHAPE_A` 逐个钉死）。四个基线
（粗口径 85→101 · 严格 78→94 · 有形态 A 68→84 · 无形态 A 21→5）增量同为 16，
算术自洽由 `test_x3_delta_is_internally_consistent` 钉住；`h5`/`n4` 仍是粗口径
假阳性（第三形态），故 `_COARSE_ONLY_NON_SHAPE_A` 与违规集基线 5 均**不变**。

## 🔴 口径二：比的是「adapter 实际解析到的端点所在模块」，不是目标模块路径字符串

工厂族（`create_cycle_import_export_router` 生成）的端点是闭包，其
`endpoint.__module__` 恒为 `…wp_render_strategies._cycle_import_export_common`
（闭包的定义处），**不是** `_k1_import_export`。所以「运行期 host `__module__`
== `_PREFIX_TO_MODULE` 的目标模块路径」这种字面比法会把 42 个正常的工厂族前缀
全部误判成违规。

正确判据 = 两侧走**同一条解析路径**：

- 运行期侧：`app.routes` 里该前缀形态 A 路由的 `endpoint.__module__`
- adapter 侧：`_endpoint_for(目标模块, prefix, suffix)`（bulk 真正用的那个函数）
  返回端点的 `endpoint.__module__`

两侧都是「谁定义了这个函数」，可比。工厂族两侧同为 `_cycle_import_export_common`
且**是同一个函数对象** ⇒ 不违规；`l1` 这类运行期侧是 `app.routers.l1_short_term_loans`
（专属 router 手写函数）、adapter 侧是工厂闭包 ⇒ 违规。

判据双跑（模块路径 / 端点对象同一性）并断言两者给出同一个违规集 —— 互为反向自检：
模块路径相同但对象不同（两个工厂模块给同一前缀各造一份闭包）也要被抓住。

## 🔴 口径三：按模块路径判，不按导入别名判

父 spec 曾把 `l1` 误判为「唯一真缺口」：`router_registry/workpaper.py` 里专属
router 的**导入别名**恰好叫 `l1_import_export`，与工厂模块 `_l1_import_export`
同名 ⇒ 按变量名匹配把两者混为一体。本守卫一律取 `endpoint.__module__`（真实模块
点路径），`_EXPECTED_VIOLATION_HOSTS` 把 5 例的宿主模块**逐条钉死**，别名改名不影响
判定。

## 反向自检（四条命名变异，每条指名检测通道）

| 变异 | 内容 | 期望通道 |
|---|---|---|
| M1 | 把 `k5` 的运行期端点换成别模块里的函数 | 模块路径判据 + 端点对象判据（新增违规） |
| M2 | `_PREFIX_TO_MODULE["k1"]` → `_k2_import_export`（不服务 `/k1/*`） | `unresolvable`（**不是**模块路径判据） |
| M3 | `_PREFIX_TO_MODULE["l1"]` → `app.routers.l1_short_term_loans` | 违规集下调 ⇒ 核心断言要求同步下调基线 |
| M4 | 形态判据放宽成只看 `segs[-2]` | 违规集比基线多 `h5`/`n4` |

只断言「变异后套件红了」不够：红在别的断言上是 WRONG-TEST、红在锚点没命中上是
ANCHOR-MISS，两者都会被误读成 RED，所以每条变异都断言具体通道。四条变异一律
**只在进程内**改（字典值 / 路由对象的 `endpoint` 属性），末尾自证还原：重新读值
相等 · 违规集回到基线 · 真源文件 md5 未变（证明从未落盘）。

任务 1.4 另做过一次**真实落盘变异**（改 `_PREFIX_TO_MODULE["k1"]` 的映射行 → 跑本
文件确认 RED → 还原 → md5 与 `git status` 双证），结果记在 spec tasks.md 实录里。
"""

import hashlib
import importlib
import re
from pathlib import Path
from typing import Any, Callable

import pytest

from tests.test_ie_route_inventory import classify_route_shapes

_BACKEND = Path(__file__).resolve().parents[1]
_ADAPTER_SRC = _BACKEND / "app" / "services" / "bulk_tab" / "_kfgh_cycle_adapters.py"

_THREE_STATE = ("export-template", "export-data", "import-data")
_PARAM_SEG = re.compile(r"^\{.*\}$")

# ─── 基线（2026-08-11 运行期实测；只许按注释里的方向调整）──────────────────────
# 🔴 2026-08-14 上调一次（任务 6.3）：X-3 的 16 个短前缀（`l2`/`l6`/`m1`~`m10`/
#    `n1`/`n2`/`n3`/`n5`）获得严格形态 A 三态端点，端点函数定义在
#    `_x3_adjustment_import_export.py`。四个数各 +16 / −16，增量同源同量，
#    由 `test_x3_delta_is_internally_consistent` 钉住算术自洽。
#: `_PREFIX_TO_MODULE` 键数（design E7）—— X-3 不新增键（16 个前缀原本就在）
_BASE_PREFIX_TO_MODULE_KEYS = 89
#: 清册粗口径的形态 A 前缀数（`test_ie_route_inventory` 基线，任务 1.4 扫描面自检要求 > 50）
_BASE_COARSE_SHAPE_A_PREFIXES = 101  # X-3 前: 85（+16）
#: 严格形态 A（`/api/workpapers/{wp_id}/{prefix}/{三态}`）前缀数
_BASE_STRICT_SHAPE_A_PREFIXES = 94  # X-3 前: 78（+16）
#: 89 键里有/无严格形态 A 三态的划分 —— design E7 记 68 / 21，X-3 后为 84 / 5
_BASE_KEYS_WITH_STRICT_SHAPE_A = 84  # X-3 前: 68（+16）
_BASE_KEYS_WITHOUT_STRICT_SHAPE_A = 5  # X-3 前: 21（−16）
#: 无严格形态 A 三态的 5 个键**逐个钉死**（比只钉数量强：换人不换数也要打红）。
#: `h5`/`n4` 走 `/api/{prefix}/{三态}` 第三形态；`h9`/`l7`/`l8` 只有形态 B 专属 router。
_KEYS_WITHOUT_STRICT_SHAPE_A = frozenset({"h5", "h9", "l7", "l8", "n4"})
#: X-3 施加带来的增量（= `X3_SHEET_SPECS` 的 16 张 sheet 各一个前缀）
_X3_STRICT_SHAPE_A_PREFIXES = frozenset({
    "l2", "l6",
    "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10",
    "n1", "n2", "n3", "n5",
})
_PRE_X3_BASELINES = {
    "coarse_shape_a": 85,
    "strict_shape_a": 78,
    "keys_with_strict_shape_a": 68,
    "keys_without_strict_shape_a": 21,
}
#: `IE_ADAPTER_REGISTRY` 规模下界（实测 97；只许上调）
_BASE_ADAPTER_REGISTRY_MIN_KEYS = 90
#: catalog 启用 I/E 的 `api_prefix` 数下界（实测 72；只许上调）
_BASE_CATALOG_IE_PREFIXES_MIN = 60
#: 实判的 (prefix, suffix) 对数下界（实测 204 = 68 × 3）—— 防「一个都没扫到」
_MIN_COMPARED_PAIRS = 150

#: 🔴 split-brain 违规集基线（design E8，5 例存量）。**只许下调**。
_SPLIT_BRAIN_BASELINE = frozenset({"h7", "l1", "l3", "l4", "l5"})

#: 5 例的宿主模块**点路径**逐条钉死（按模块路径判，不按导入别名判）
_EXPECTED_VIOLATION_HOSTS: dict[str, str] = {
    "h7": "app.routers.h7_biological_assets",
    "l1": "app.routers.l1_short_term_loans",
    "l3": "app.routers.l3_long_term_loans",
    "l4": "app.routers.l4_bonds_payable",
    "l5": "app.routers.l5_long_term_payables",
}

#: 工厂闭包的定义处 —— adapter 侧解析到工厂族端点时 `__module__` 恒为此
_FACTORY_CLOSURE_MODULE = "app.routers.wp_render_strategies._cycle_import_export_common"

#: 粗口径会多算进来、但**不是**形态 A 的前缀（`/api/{prefix}/{三态}`，无 `{wp_id}` 段）
_COARSE_ONLY_NON_SHAPE_A = frozenset({"h5", "n4"})


# ═══════════════════════════════════════════════════════════════════════════════
# 判据本体（fixture 与验收脚本共用；不得在别处再写一份）
# ═══════════════════════════════════════════════════════════════════════════════


def strict_shape_a_routes(app) -> dict[tuple[str, str], Any]:
    """严格形态 A 路由对象：`/api/workpapers/{wp_id}/{prefix}/{三态}` ⇒ {(前缀, 后缀): route}。

    · **first-wins**：Starlette 按注册顺序匹配，先注册的那条才是用户真正打到的端点，
      故重复路径以第一条为准（实测重复 0 条，见 `test_no_shadowed_strict_shape_a_routes`）。
    · 前缀必须落在**倒数第二段**且倒数第三段是 `{wp_id}` 参数段、倒数第四段是
      `workpapers` —— 这三条一起把形态 B 与 `/api/{prefix}/{三态}` 第三形态排除干净。
    """
    out: dict[tuple[str, str], Any] = {}
    for route in app.routes:
        segs = getattr(route, "path", "").strip("/").split("/")
        if not _is_strict_shape_a(segs):
            continue
        out.setdefault((segs[-2], segs[-1]), route)
    return out


def strict_shape_a_endpoints(app) -> dict[str, dict[str, Callable[..., Any]]]:
    """同上，但归约为 {前缀: {后缀: endpoint}}（判据比对用）。"""
    out: dict[str, dict[str, Callable[..., Any]]] = {}
    for (prefix, suffix), route in strict_shape_a_routes(app).items():
        out.setdefault(prefix, {})[suffix] = getattr(route, "endpoint", None)
    return out


def _is_strict_shape_a(segs: list[str]) -> bool:
    return (
        len(segs) >= 4
        and segs[0] == "api"
        and segs[-1] in _THREE_STATE
        and segs[-4] == "workpapers"
        and bool(_PARAM_SEG.match(segs[-3]))
        and not _PARAM_SEG.match(segs[-2])
    )


def resolve_target_module_path(value: str) -> str:
    """`_PREFIX_TO_MODULE` 的值 → 模块点路径。**委派生产实现**，不另写一份规则。

    🔴 2026-08-14 任务 6.3 收口的承重缺口（任务 6.1 双证查出）：本函数原先**自带
    一份点路径规则的镜像**（只从生产 import `_MODULE_PKG`，`value if "." in value
    else _MODULE_PKG + value` 是抄的）。后果是生产 `_resolve_module_path` 的行为漂移
    **全仓不可见** —— 6.1 实测把生产规则取反后 89 个目标模块**全部 unimportable**，
    而 GS6 24 条 + witness 50 条 + 零回归 305 条**无一新红**（MUT-3 只坏 16 个点路径值
    也同样 GREEN）。X-3 施加后有 16 个键依赖点路径分支 ⇒ 缺口是承重的。

    修法：**唯一规则源 = 生产 `_resolve_module_path`**，本函数只转发。再加一道
    双向锁死：拿镜像值与生产值比对，不等即 fail-loud —— 这样「生产改了规则」和
    「生产被改坏」两种情形都由本函数当场暴露，而不是被守卫自己的副本盖住。
    """
    from app.services.bulk_tab._kfgh_cycle_adapters import (
        _MODULE_PKG,
        _resolve_module_path,
    )

    resolved = _resolve_module_path(value)
    mirror = value if "." in value else _MODULE_PKG + value
    assert resolved == mirror, (
        f"生产 `_resolve_module_path` 的拼接规则已漂移: {value!r} → 生产 {resolved!r} "
        f"vs 守卫镜像 {mirror!r}。两侧只许同时改：先确认生产改动是有意的，再同步本镜像。"
    )
    return resolved


def adapter_resolved_endpoints(prefix: str, value: str) -> dict[str, Callable[..., Any] | None]:
    """bulk adapter 对该前缀实际解析到的三态端点（走生产同一个 `_endpoint_for`）。"""
    from app.services.bulk_tab._kfgh_cycle_adapters import _endpoint_for

    module = importlib.import_module(resolve_target_module_path(value))
    return {suffix: _endpoint_for(module, prefix, suffix) for suffix in _THREE_STATE}


def split_brain_report(app, *, strict: bool = True) -> dict[str, dict[str, Any]]:
    """逐前缀比对「运行期宿主模块」与「adapter 解析到的端点所在模块」。

    Returns:
        {prefix: {host, adapter, target, unresolvable, identity_mismatch}}，
        仅收录**可比**的前缀（既有形态 A 端点、又在 `_PREFIX_TO_MODULE` 里）。
        `strict=False` 时改用清册粗口径 —— 只给
        `test_coarse_criterion_would_add_known_non_shape_a_prefixes` 用来证明口径差异。
    """
    from app.services.bulk_tab._kfgh_cycle_adapters import _PREFIX_TO_MODULE

    live = strict_shape_a_endpoints(app) if strict else _coarse_shape_a_endpoints(app)
    report: dict[str, dict[str, Any]] = {}
    for prefix, value in _PREFIX_TO_MODULE.items():
        endpoints = live.get(prefix)
        if not endpoints:
            continue
        adapter_side = adapter_resolved_endpoints(prefix, value)
        host_modules = sorted({getattr(ep, "__module__", "?") for ep in endpoints.values()})
        adapter_modules = sorted(
            {getattr(ep, "__module__", "?") for ep in adapter_side.values() if ep is not None}
        )
        identity_mismatch = sorted(
            suffix
            for suffix, ep in endpoints.items()
            if adapter_side.get(suffix) is not None and adapter_side[suffix] is not ep
        )
        report[prefix] = {
            "host": host_modules,
            "adapter": adapter_modules,
            "target": resolve_target_module_path(value),
            "unresolvable": not adapter_modules,
            "identity_mismatch": identity_mismatch,
            "compared_suffixes": sorted(endpoints),
        }
    return report


def _coarse_shape_a_endpoints(app) -> dict[str, dict[str, Callable[..., Any]]]:
    """清册粗口径（`segs[-2]` 非参数段）—— 仅供口径对照，不作判据。"""
    out: dict[str, dict[str, Callable[..., Any]]] = {}
    for route in app.routes:
        segs = getattr(route, "path", "").strip("/").split("/")
        if len(segs) < 2 or segs[-1] not in _THREE_STATE or _PARAM_SEG.match(segs[-2]):
            continue
        out.setdefault(segs[-2], {}).setdefault(segs[-1], getattr(route, "endpoint", None))
    return out


def module_path_violations(report: dict[str, dict[str, Any]]) -> set[str]:
    """判据一：宿主模块集 != adapter 解析到的模块集。"""
    return {
        p
        for p, r in report.items()
        if not r["unresolvable"] and r["host"] != r["adapter"]
    }


def identity_violations(report: dict[str, dict[str, Any]]) -> set[str]:
    """判据二：同一 (prefix, suffix) 上运行期端点与 adapter 端点不是同一个函数对象。"""
    return {p for p, r in report.items() if r["identity_mismatch"]}


def _adapter_registry_keys() -> set[str]:
    """触发 `register_*_adapters()` 后取 `IE_ADAPTER_REGISTRY` 键集。

    口径与 `test_ie_route_inventory._adapter_registry_keys` 一致（import 模块不会
    自动注册，必须显式调）。
    """
    from app.services.bulk_tab import _d_cycle_adapters, _kfgh_cycle_adapters
    from app.services.bulk_tab.single_tab_adapter import IE_ADAPTER_REGISTRY

    for mod in (_d_cycle_adapters, _kfgh_cycle_adapters):
        for fn_name in dir(mod):
            if fn_name.startswith("register_") and fn_name.endswith("_adapters"):
                try:
                    getattr(mod, fn_name)()
                except Exception:  # noqa: BLE001 — 重复注册无害，缺失由断言暴露
                    pass
    return set(IE_ADAPTER_REGISTRY)


def _catalog_ie_prefixes() -> dict[str, list[str]]:
    """catalog 启用 I/E 的 `api_prefix` → sheet_code 列表。"""
    from app.services.acnr.catalog import list_sheets

    out: dict[str, list[str]] = {}
    for sheet in list_sheets(import_export_only=True):
        seg = (sheet.get("import_export") or {}).get("api_prefix")
        if seg:
            out.setdefault(seg, []).append(sheet.get("sheet_code", "?"))
    return out


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures（module 级共用一个 app 实例：导入期开销大且重复导入会重复注册路由）
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def app_instance():
    from app.main import app

    return app


@pytest.fixture(scope="module")
def report(app_instance) -> dict[str, dict[str, Any]]:
    _adapter_registry_keys()  # 与 bulk 运行态一致：先触发注册
    return split_brain_report(app_instance)


# ═══════════════════════════════════════════════════════════════════════════════
# 类 A —— 扫描面自检（应全绿；防「一个都没扫到 ⇒ 违规集恒空 ⇒ 恒绿」）
# ═══════════════════════════════════════════════════════════════════════════════


