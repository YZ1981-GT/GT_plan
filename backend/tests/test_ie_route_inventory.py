"""导入导出端点清册守卫 —— Wave 1 Task 2（spec: workpaper-import-export-lifecycle-closure）

## 为什么必须从运行期 `app.routes` 取

`backend/app/routers/wp_render_strategies/` 下 **99 个** `*_import_export.py` 里
**63 个零 `@router.` 装饰器** —— 它们的端点由
`_cycle_import_export_common.create_cycle_import_export_router(tag=, api_prefix=, specs=)`
在**导入期**生成。所以：

- 数源码里的 `@router.get/post` ⇒ 只能看到 36 个模块的端点，**漏掉 2/3**
- 想从源码「数出」工厂模块的 sheet 键 ⇒ 必须解析散落在各模块顶部的
  `_Kx_x_HEADERS` / `_Kx_x_KEYS` 字典字面量 = memory 明令禁止的 grep 式守卫

唯一可靠判据是**启动 app 后枚举 `app.routes`**。

## 🔴 URL 有两种形态，前缀段位不同（本轮最贵的一处口径修正）

| 形态 | 样例 | 前缀段位 | 组数 |
|---|---|---|---|
| A | `/api/workpapers/{wp_id}/k5/export-data` | `segs[-2]` | 101 |
| B | `/api/h9-lease-liabilities/{wp_id}/export-data` | `segs[-3]` | 22 |

只处理形态 A 会把形态 B 的前缀全部误判成 `{wp_id}` 这一个「前缀」。

**修正历程（三轮，全部留痕以防重犯）**：

1. 初稿只取 `segs[-2]` ⇒ 得 87 组 / 三态齐全 81 组
2. 发现 `{wp_id}` 在分组键里 ⇒ 加「剔除路径参数段」⇒ 得 85 组 / 齐全 **80** 组，
   并误以为 `{wp_id}` 是「误计」应当丢弃
3. 展开 `{wp_id}` 组的实际路径 ⇒ 它藏着 **20 个真实前缀**
   （`h9-lease-liabilities` / `l2-interest-payable` / `m1`~`m10` / `n1`~`n3` / `n5` /
   `s-estimate` 等），**不是误计而是另一种 URL 形态** ⇒ 改为「参数段时回退取
   `segs[-3]`」⇒ 得 **107 组 / 三态齐全 100 组**（2026-08-10 的基线）
4. 2026-08-14（spec `x3-adjustment-entry-import-export` 任务 6.3）：X-3 调整分录
   导入导出新增 **16 个形态 A 前缀 × 3 态 = 48 条**端点（`l2` / `l6` / `m1`~`m10` /
   `n1` / `n2` / `n3` / `n5`，端点函数定义在
   `wp_render_strategies/_x3_adjustment_import_export.py`，挂载在各自的专属 router
   上）⇒ 基线上调为 **123 组 / 三态齐全 116 组 / 形态 A 101 / 形态 B 22（不变）/
   三态端点 356 条**。这一轮是**纯增量**：形态 B、零装饰器模块数、工厂 `api_prefix`
   数三项逐字未变，故 16 与 48 都能由「新基线 − 旧基线」复算出来

立项需求文档写的「各 36 组 / 合计 314 个」与前两轮我自己的 81、80 **都是错的**。
反向自检 `test_shape_b_prefixes_are_not_dropped` 钉死形态 B 不得再被丢弃。

## 🔴 工厂声明的 api_prefix ≠ 真实 URL 前缀

`_h9_import_export.py` 声明 `api_prefix='h9'`，但运行期真实前缀是
`h9-lease-liabilities` —— 因为那 3 个端点根本**不是这个工厂 router 造的**，
而是 `backend/app/routers/h9_lease_liabilities.py`（自带
`prefix="/api/h9-lease-liabilities"`）造的，且**只有后者被 include_router**。

⇒ 2026-08-10 实测 **19 个工厂模块是死代码**（见 `_PRE_X3_DEAD_FACTORY_PREFIXES`）。
⇒ registry 绝不能抄工厂声明的 `api_prefix`（会得到 404 的前缀）。

🔴 **2026-08-14 判据命中面收缩（X-3 任务 6.3，必读）**：X-3 为 16 个前缀
（`l2` / `l6` / `m1`~`m10` / `n1` / `n2` / `n3` / `n5`）新增了形态 A 端点，于是
「声明的 `api_prefix` 在运行期零三态端点」这条判据**不再命中它们**，死集由 19 收缩
到 **3**（`h9` / `l7` / `l8`）。但那 16 个**工厂模块本身仍是死代码** —— 它们的
`router` 依旧从未被 `include_router`，新端点由
`_x3_adjustment_import_export.py` 提供。⇒ 判它们死活**不能再靠本条判据**，须换成
「该模块的 `router` 是否被 `include_router`」；删除仍属父 spec Task 25 的作业面
（目标基线登记在 `_TASK25_PENDING_BASELINES`）。`test_dead_set_records_the_x3_revival`
把这 16 个「非真复活」逐条钉死，防下一轮据「死集只剩 3」误判「16 个模块已经在用」。

## 本文件同时固化 design §核心事实修正 的台账

反向自检 `test_baseline_numbers_reject_stale_figures` 断言「把任一数字改回
立项旧数或我前两轮的错数必须打红」—— 防下一轮有人凭旧数重新发起改动。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_STRATEGIES = _BACKEND / "app" / "routers" / "wp_render_strategies"

_THREE_STATE = ("export-template", "export-data", "import-data")
_PARAM_SEG = re.compile(r"^\{.*\}$")

# ─── 台账基线（2026-08-10 三轮实证；旧错数写在注释里，禁止改回）────────────────
# 🔴 2026-08-14 上调一次（spec `x3-adjustment-entry-import-export` 任务 6.3）。
#    唯一增量 = X-3 的 `_x3_adjustment_import_export.py`：**1 个模块 / 16 个形态 A
#    前缀 / 48 条端点（16 × 3）**，其余口径一字未改 ⇒ 每个新值都能由
#    「X-3 前的值 + 增量」复算，增量本身由 `X3_SHEET_SPECS` 的 16 张 sheet 派生。
#    反向自检见 `TestBaselineRejectsStaleFigures`（改回任一旧值必打红）。
_BASE_IE_MODULES = 100           # X-3 前: 99（+1 个 X-3 模块）/ 立项: 102
_BASE_NO_DECORATOR_MODULES = 63  # X-3 不变（X-3 模块自带 `@router.`）/ 立项: 未记
_BASE_FACTORY_PREFIXES = 62      # X-3 不变（X-3 不走 create_cycle_import_export_router）
_BASE_THREE_STATE_ROUTES = 356   # X-3 前: 308（+48）/ 立项: 314
_BASE_GROUPS = 123               # X-3 前: 107（+16）/ 我的第 1 轮: 87 / 第 2 轮: 85
_BASE_FULL3_PREFIXES = 116       # X-3 前: 100（+16）/ 立项: 36 / 第 1 轮: 81 / 第 2 轮: 80
_BASE_SHAPE_A = 101              # X-3 前: 85（+16，X-3 全走形态 A）
_BASE_SHAPE_B = 22               # X-3 不变（X-3 无形态 B 端点）
_BASE_ROUTE_KINDS = {            # X-3 前: 106 / 102 / 100（三态各 +16）
    "export-template": 122,
    "export-data": 118,
    "import-data": 116,
}
#: X-3 增量的可复算分解（供反向自检与 spec 实录交叉核对；不是独立事实源）
_X3_SHAPE_A_PREFIXES = frozenset({
    "l2", "l6",
    "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10",
    "n1", "n2", "n3", "n5",
})
#: X-3 的 48 条端点函数的定义处（`endpoint.__module__`）
_X3_HOST_MODULE = "app.routers.wp_render_strategies._x3_adjustment_import_export"
_PRE_X3_BASELINES = {
    "ie_modules": 99,
    "three_state_routes": 308,
    "groups": 107,
    "full3_prefixes": 100,
    "shape_a": 85,
    "route_kinds": {"export-template": 106, "export-data": 102, "import-data": 100},
}

#: 2026-08-10 实测：19 个工厂模块的 router 从未被 include_router，且其 api_prefix
#: 在运行期零端点。X-3 施加后其中 16 个前缀有了形态 A 端点（宿主是 X-3 模块，
#: **不是**这些工厂模块），故本判据的命中面收缩到 3 —— 详见文件头「判据命中面收缩」。
_PRE_X3_DEAD_FACTORY_PREFIXES = frozenset({
    "h9", "l2", "l6", "l7", "l8",
    "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10",
    "n1", "n2", "n3", "n5",
})

#: 🔴 判据「声明的 `api_prefix` 在运行期三态端点里零命中」当前命中的 3 个前缀。
#: 它们的能力由 `backend/app/routers/{name}.py` 专属 router 提供（形态 B / 第三形态）。
#: **只许下调**：新增必须查清是不是又有工厂模块被 include_router 漏了。
_TRULY_DEAD_FACTORY_PREFIXES = frozenset({"h9", "l7", "l8"})

# ═══════════════════════════════════════════════════════════════════════════════
# 🔴 父 spec `workpaper-import-export-lifecycle-closure` **Task 25 施加后**的目标基线
#    —— **待 Task 25 执行时启用**。现在不是生效基线，禁止提前套用。
#
# Task 25 = 删除 19 个死代码工厂模块（`_PRE_X3_DEAD_FACTORY_PREFIXES` 各对应 1 个
# `_{prefix}_import_export.py`；2026-08-14 AST 实测：19 前缀 ↔ 19 模块一一对应，
# 每个模块恰好 1 次 `create_cycle_import_export_router`，且不声明任何别的前缀）。
#
# ⚠️ 其中两项与父 spec 自己记的数字不同，成因是**父 spec 的数字算在 X-3 之前**：
#   · `_BASE_IE_MODULES`：父 spec 记 99 → 80；X-3 加了 1 个不在删除清单里的模块，
#     故实际是 100 → **81**。
#   · `IE_ADAPTER_REGISTRY`：父 spec 记 97 → 78（= 97 − 19）；X-3 已把那 16 个键
#     改指专属 router 点路径（`app.routers.l2_interest_payable` 等），只剩
#     `h9`/`l7`/`l8` 三个键的目标模块在删除清单内，故实际是 97 → **94**。
#     （2026-08-14 实测：`registry_keys_pointing_at_dead_modules == ['h9','l7','l8']`）
# ═══════════════════════════════════════════════════════════════════════════════
_TASK25_PENDING_BASELINES: dict[str, object] = {
    # 常量名 → Task 25 施加后应下调到的值
    "_BASE_IE_MODULES": 81,               # 100 − 19（父 spec 口径 99 → 80）
    "_BASE_FACTORY_PREFIXES": 43,         # 62 − 19（与父 spec 一致）
    "IE_ADAPTER_REGISTRY": 94,            # 97 − 3（父 spec 口径 97 → 78，已被 X-3 改变）
    "_TRULY_DEAD_FACTORY_PREFIXES": frozenset(),  # 19 个模块删完 ⇒ 声明面清空
}

#: 形态 B 的真实前缀样本（守卫钉死它们不得被当成 `{wp_id}` 丢弃）
_SHAPE_B_SAMPLES = (
    "h9-lease-liabilities",
    "l2-interest-payable",
    "m10-other-equity-instruments",
    "n1-deferred-tax-assets",
    "s-estimate",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 分组口径 —— design §Data Models 的 group_ie_routes，守卫与验收脚本共用
# ═══════════════════════════════════════════════════════════════════════════════


def group_ie_routes(app) -> dict[str, set[str]]:
    """按真实前缀分组三态端点，兼容两种 URL 形态。

    · 形态 A `/api/workpapers/{wp_id}/k5/export-data` ⇒ 前缀 = `segs[-2]`
    · 形态 B `/api/h9-lease-liabilities/{wp_id}/export-data` ⇒ 前缀 = `segs[-3]`

    🔴 这个函数是**判据本体**，验收脚本必须 import 它而不是各写一份，
    否则两处数字对不上时无法判断谁错。
    """
    out: dict[str, set[str]] = {}
    for r in app.routes:
        path = getattr(r, "path", "")
        segs = path.strip("/").split("/")
        if len(segs) < 2 or segs[-1] not in _THREE_STATE:
            continue
        prefix = segs[-2]
        if _PARAM_SEG.match(prefix):
            # 形态 B：倒数第二段是 {wp_id} ⇒ 真实前缀在倒数第三段
            if len(segs) < 3:
                continue
            prefix = segs[-3]
            if _PARAM_SEG.match(prefix):
                continue  # 连续两段参数 ⇒ 无可用前缀
        out.setdefault(prefix, set()).add(segs[-1])
    return out


def classify_route_shapes(app) -> tuple[set[str], set[str]]:
    """返回 (形态 A 前缀集, 形态 B 前缀集)。用于证明两种形态都被覆盖。"""
    shape_a: set[str] = set()
    shape_b: set[str] = set()
    for r in app.routes:
        segs = getattr(r, "path", "").strip("/").split("/")
        if len(segs) < 2 or segs[-1] not in _THREE_STATE:
            continue
        if _PARAM_SEG.match(segs[-2]):
            if len(segs) >= 3 and not _PARAM_SEG.match(segs[-3]):
                shape_b.add(segs[-3])
        else:
            shape_a.add(segs[-2])
    return shape_a, shape_b


def _adapter_registry_keys() -> set[str]:
    """取 `IE_ADAPTER_REGISTRY` 的键集 —— **bulk 批量导入导出的真实可达面**。

    🔴 为什么判「catalog 前缀有效」必须用这个而不是 URL 前缀相似度：

    `bulk_export_service` / `bulk_import_service` 对未注册的 `api_prefix` 走
    `except KeyError` → 标 `skip_reason=no_adapter` **静默跳过该 sheet**。
    所以一个前缀即便在运行期有 HTTP 端点，只要没进 `IE_ADAPTER_REGISTRY`，
    批量四场景里它就是不可达的（`d1-ecl` 正是此例：端点在、适配器无）。

    2026-08-10 教训：初版判据写 `not any(live.startswith(f"{p}-"))`，
    结果 `g4`/`g6`/`g7`/`g7-method` 被 `g4-main`/`g6-main`/`g7-main` 冒充放过，
    `d1-ecl` 更是三条判据全部放过 —— 变异检验 RED 0/3 才暴露出来。

    注册表由 `register_*_adapters()` 填充，import 模块不会自动触发，必须显式调。
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


def _count_ie_routes(app) -> dict[str, int]:
    counts = {k: 0 for k in _THREE_STATE}
    for r in app.routes:
        last = getattr(r, "path", "").rstrip("/").rsplit("/", 1)[-1]
        if last in counts:
            counts[last] += 1
    return counts


def _factory_api_prefixes(ie_modules: list[Path]) -> list[str]:
    """AST 取 `create_cycle_import_export_router(api_prefix=...)` 的实参。

    用 AST 不用正则 —— 正则会被字符串里的同名字段骗到。
    """
    prefixes: list[str] = []
    for p in ie_modules:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name != "create_cycle_import_export_router":
                continue
            for kw in node.keywords:
                if kw.arg == "api_prefix" and isinstance(kw.value, ast.Constant):
                    prefixes.append(str(kw.value.value))
    return prefixes


@pytest.fixture(scope="module")
def app_instance():
    """整个模块共用一个 app 实例（导入期开销大，且重复导入会重复注册路由）。"""
    from app.main import app

    return app


@pytest.fixture(scope="module")
def ie_modules() -> list[Path]:
    return sorted(_STRATEGIES.glob("*_import_export.py"))


# ═══════════════════════════════════════════════════════════════════════════════
# 类 A —— 扫描面自检（应全绿；防「没命中导致全部断言空转」）
# ═══════════════════════════════════════════════════════════════════════════════


class TestScanSurfaceNonEmpty:
    def test_strategies_dir_exists(self) -> None:
        assert _STRATEGIES.is_dir(), f"目录不存在: {_STRATEGIES}"

    def test_ie_modules_nonempty(self, ie_modules: list[Path]) -> None:
        assert len(ie_modules) > 50, f"扫描面异常小: {len(ie_modules)}"

    def test_app_has_routes(self, app_instance) -> None:
        assert len(app_instance.routes) > 1000, (
            f"app.routes 异常少: {len(app_instance.routes)} —— 疑似部分 router 未注册"
        )

    def test_grouping_surface_nonempty(self, app_instance) -> None:
        groups = group_ie_routes(app_instance)
        assert len(groups) > 50, f"分组结果异常少: {len(groups)}"


# ═══════════════════════════════════════════════════════════════════════════════
# 类 A —— 台账固化（只读事实，应全绿）
# ═══════════════════════════════════════════════════════════════════════════════


class TestBaselineNumbers:
    def test_ie_module_count(self, ie_modules: list[Path]) -> None:
        """台账 #3：100 个模块（X-3 前 99 / 立项写 102）。"""
        assert len(ie_modules) == _BASE_IE_MODULES, (
            f"`*_import_export.py` 模块数变化: {len(ie_modules)} != "
            f"{_BASE_IE_MODULES}。若确为新增/删除，同步更新基线并在 spec Notes 留痕"
        )

    def test_modules_without_router_decorator(self, ie_modules: list[Path]) -> None:
        """台账 #3：63 个模块零 `@router.` 装饰器 —— 「源码扫描漏 2/3」的量化证据。"""
        no_dec = [
            p.name
            for p in ie_modules
            if not re.search(
                r"@router\.(get|post|put|delete)", p.read_text(encoding="utf-8")
            )
        ]
        assert len(no_dec) == _BASE_NO_DECORATOR_MODULES, (
            f"零装饰器模块数变化: {len(no_dec)} != {_BASE_NO_DECORATOR_MODULES}"
        )

    def test_factory_api_prefixes_unique(self, ie_modules: list[Path]) -> None:
        """台账 #3：62 个工厂 `api_prefix`，且全唯一。"""
        prefixes = _factory_api_prefixes(ie_modules)
        assert len(prefixes) == _BASE_FACTORY_PREFIXES, (
            f"工厂调用数变化: {len(prefixes)} != {_BASE_FACTORY_PREFIXES}"
        )
        dupes = {p for p in prefixes if prefixes.count(p) > 1}
        assert not dupes, f"api_prefix 撞车（会让后注册的覆盖前者）: {sorted(dupes)}"

    def test_three_state_route_counts(self, app_instance) -> None:
        """台账 #4：356 条 = 122 + 118 + 116（X-3 前 308 = 106 + 102 + 100）。"""
        counts = _count_ie_routes(app_instance)
        assert counts == _BASE_ROUTE_KINDS, (
            f"三态端点分布变化: {counts} != {_BASE_ROUTE_KINDS}"
        )
        assert sum(counts.values()) == _BASE_THREE_STATE_ROUTES

    def test_group_and_full3_counts(self, app_instance) -> None:
        """台账 #4：123 组 / 三态齐全 116 组（X-3 前 107 / 100，X-3 各 +16）。

        立项写 36 组；我的第 1 轮算 81、第 2 轮算 80 —— 都因漏了形态 B。
        """
        groups = group_ie_routes(app_instance)
        assert len(groups) == _BASE_GROUPS, (
            f"分组数变化: {len(groups)} != {_BASE_GROUPS}"
        )
        full3 = {k for k, v in groups.items() if len(v) == 3}
        assert len(full3) == _BASE_FULL3_PREFIXES, (
            f"三态齐全前缀数变化: {len(full3)} != {_BASE_FULL3_PREFIXES}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 类 A —— 两种 URL 形态（本轮口径修正的核心判据）
# ═══════════════════════════════════════════════════════════════════════════════


class TestTwoUrlShapes:
    def test_both_shapes_present(self, app_instance) -> None:
        """两种形态都存在且组数符合实证（101 / 22；X-3 前 85 / 22）。"""
        shape_a, shape_b = classify_route_shapes(app_instance)
        assert len(shape_a) == _BASE_SHAPE_A, (
            f"形态 A 前缀数变化: {len(shape_a)} != {_BASE_SHAPE_A}"
        )
        assert len(shape_b) == _BASE_SHAPE_B, (
            f"形态 B 前缀数变化: {len(shape_b)} != {_BASE_SHAPE_B}"
        )

    def test_shapes_do_not_overlap(self, app_instance) -> None:
        """同一前缀不应同时用两种形态（否则前端无法确定该拼哪种 URL）。"""
        shape_a, shape_b = classify_route_shapes(app_instance)
        both = shape_a & shape_b
        assert not both, f"同一前缀混用两种 URL 形态: {sorted(both)}"

    def test_shape_b_prefixes_are_not_dropped(self, app_instance) -> None:
        """🔴 反向自检：形态 B 的真实前缀必须出现在分组结果里。

        这条钉死「把 `{wp_id}` 当误计丢弃」这个错法不得重演 ——
        那样会连带丢掉 20 个真实前缀。
        """
        groups = group_ie_routes(app_instance)
        missing = [p for p in _SHAPE_B_SAMPLES if p not in groups]
        assert not missing, (
            f"形态 B 前缀被丢弃（口径退回到只取 segs[-2]）: {missing}"
        )

    def test_no_param_segment_in_group_keys(self, app_instance) -> None:
        """分组键不得含 `{...}` —— 参数段必须已被回退逻辑消化。"""
        groups = group_ie_routes(app_instance)
        param_keys = [k for k in groups if _PARAM_SEG.match(k)]
        assert not param_keys, f"分组键含路径参数（回退逻辑失效）: {param_keys}"

    def test_naive_grouping_loses_prefixes(self, app_instance) -> None:
        """反向自检：只取 `segs[-2]` 的朴素口径**必须**丢掉形态 B 前缀。

        若这条断言失败，说明形态 B 已不存在，两形态兼容逻辑可以简化 ——
        属于需要显式裁决的结构变化，不该静默通过。
        """
        naive: set[str] = set()
        for r in app_instance.routes:
            segs = getattr(r, "path", "").strip("/").split("/")
            if len(segs) >= 2 and segs[-1] in _THREE_STATE:
                naive.add(segs[-2])
        lost = [p for p in _SHAPE_B_SAMPLES if p not in naive]
        assert lost, (
            "朴素口径未丢失任何形态 B 前缀 —— 与实证不符，请复核 URL 形态是否已变"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 类 A —— 死代码工厂模块（决定 registry 真源选型 + Task 14/16 作业面）
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeadFactoryModules:
    def test_dead_prefixes_have_zero_runtime_endpoints(
        self, app_instance, ie_modules: list[Path]
    ) -> None:
        """🔴 3 个工厂 `api_prefix` 在运行期零三态端点（X-3 前 19 个）。

        判据是「运行期该 prefix 有没有端点」，不是「源码里有没有这个模块」。
        ⚠️ 判据只证明「prefix 有端点」，**不证明**端点由这个工厂模块提供 ——
        X-3 的 16 个前缀正是「prefix 活了但工厂模块仍死」，见
        `test_dead_set_records_the_x3_revival`。
        """
        groups = group_ie_routes(app_instance)
        declared = set(_factory_api_prefixes(ie_modules))

        actually_dead = {p for p in declared if p not in groups}
        assert actually_dead == set(_TRULY_DEAD_FACTORY_PREFIXES), (
            f"死代码 prefix 集合变化:\n"
            f"  新增死亡: {sorted(actually_dead - _TRULY_DEAD_FACTORY_PREFIXES)}\n"
            f"  已复活  : {sorted(_TRULY_DEAD_FACTORY_PREFIXES - actually_dead)}\n"
            f"复活是好事，但须同步下调基线并在 spec Notes 留痕"
        )

    def test_dead_prefix_capability_covered_by_dedicated_router(
        self, app_instance
    ) -> None:
        """死代码的能力必须仍被专属 router 覆盖（否则是真功能缺口）。

        判据：死 prefix 的字母数字前段（如 `h9`）应能匹配到某个运行期前缀
        （如 `h9-lease-liabilities`）。
        """
        groups = group_ie_routes(app_instance)
        full3 = {k for k, v in groups.items() if len(v) == 3}

        uncovered: list[str] = []
        for dead in sorted(_TRULY_DEAD_FACTORY_PREFIXES):
            if any(live == dead or live.startswith(f"{dead}-") for live in full3):
                continue
            uncovered.append(dead)

        assert not uncovered, (
            f"死代码 prefix 的能力无任何专属 router 覆盖 = 真功能缺口: {uncovered}"
        )

    def test_dead_set_records_the_x3_revival(
        self, app_instance, ie_modules: list[Path]
    ) -> None:
        """🔴 死集由 19 收缩到 3，收缩量必须**恰好**是 X-3 的 16 个前缀。

        这条把「命中面收缩」钉成结构事实，作用有两层：

        1. 防「死集只剩 3」被下一轮读成「另外 16 个工厂模块已经在用，不能删」——
           它们只是 prefix 被 X-3 点亮，模块本身仍未被 `include_router`。
        2. 若哪天真有工厂模块被接上，收缩量就会 != X-3 的 16 个 ⇒ 本条打红，
           要求显式裁决，而不是静默并入死集变化里。
        """
        groups = group_ie_routes(app_instance)
        declared = set(_factory_api_prefixes(ie_modules))
        actually_dead = {p for p in declared if p not in groups}

        revived = _PRE_X3_DEAD_FACTORY_PREFIXES - actually_dead
        assert revived == set(_X3_SHAPE_A_PREFIXES), (
            f"死集收缩量 != X-3 的 16 个前缀:\n"
            f"  多复活: {sorted(revived - _X3_SHAPE_A_PREFIXES)}（须查是否有工厂 router 被接上）\n"
            f"  未复活: {sorted(_X3_SHAPE_A_PREFIXES - revived)}（X-3 端点缺失）"
        )
        assert _TRULY_DEAD_FACTORY_PREFIXES == _PRE_X3_DEAD_FACTORY_PREFIXES - revived, (
            "`_TRULY_DEAD_FACTORY_PREFIXES` 与「X-3 前死集 − 复活集」不自洽"
        )
        # 复活的 16 个前缀，其端点宿主必须是 X-3 模块而**不是**同名工厂模块
        hosts: dict[str, set[str]] = {}
        for r in app_instance.routes:
            segs = getattr(r, "path", "").strip("/").split("/")
            if len(segs) >= 2 and segs[-1] in _THREE_STATE and segs[-2] in revived:
                hosts.setdefault(segs[-2], set()).add(
                    getattr(getattr(r, "endpoint", None), "__module__", "?")
                )
        wrong = {
            p: sorted(mods)
            for p, mods in hosts.items()
            if mods != {_X3_HOST_MODULE}
        }
        assert set(hosts) == set(revived) and not wrong, (
            f"复活前缀的端点宿主不是 X-3 模块: {wrong}；缺前缀: "
            f"{sorted(set(revived) - set(hosts))}"
        )

    def test_l1_short_term_loans_has_live_endpoints(self, app_instance) -> None:
        """L1 短期借款三态端点必须存在（用户明确要求 L1 要有导入导出）。

        🔴 留痕：本 spec 中途曾误判「l1 是唯一真缺口」，成因是
        `router_registry/workpaper.py` 里专属 router 的导入别名恰好叫
        `l1_import_export`，与工厂模块同名 ⇒ 按变量名匹配把两者搞混。
        实证：`/api/workpapers/{wp_id}/l1/*` 三态齐全，由
        `backend/app/routers/l1_short_term_loans.py` 提供且已注册。
        """
        groups = group_ie_routes(app_instance)
        assert "l1" in groups, "L1 短期借款前缀在运行期不存在"
        assert groups["l1"] == set(_THREE_STATE), (
            f"L1 三态不齐: {sorted(groups['l1'])}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 类 A —— 反向自检（防基线被改回旧错数）
# ═══════════════════════════════════════════════════════════════════════════════


class TestBaselineRejectsStaleFigures:
    def test_baseline_numbers_reject_stale_figures(self) -> None:
        """🔴 把台账改回立项旧数、我前两轮的错数、或 X-3 前的旧数必须打红。"""
        stale = {
            "ie_modules": (102, _PRE_X3_BASELINES["ie_modules"]),
            "three_state_routes": (314, _PRE_X3_BASELINES["three_state_routes"]),
            "full3_prefixes": (36, 81, 80, _PRE_X3_BASELINES["full3_prefixes"]),
            "groups": (87, 85, _PRE_X3_BASELINES["groups"]),
            "shape_a": (_PRE_X3_BASELINES["shape_a"],),
        }
        assert _BASE_IE_MODULES not in stale["ie_modules"], (
            "基线被改回旧数（立项 102 / X-3 前 99，实证 100）"
        )
        assert _BASE_THREE_STATE_ROUTES not in stale["three_state_routes"], (
            "基线被改回旧数（立项 314 / X-3 前 308，实证 356）"
        )
        assert _BASE_FULL3_PREFIXES not in stale["full3_prefixes"], (
            "基线被改回旧错数（立项 36 / 第 1 轮 81 / 第 2 轮 80 / X-3 前 100，实证 116）"
        )
        assert _BASE_GROUPS not in stale["groups"], (
            "分组数基线被改回旧错数（第 1 轮 87 / 第 2 轮 85 / X-3 前 107，实证 123）"
        )
        assert _BASE_SHAPE_A not in stale["shape_a"], (
            "形态 A 基线被改回 X-3 前的 85（实证 101）"
        )
        assert _BASE_ROUTE_KINDS != _PRE_X3_BASELINES["route_kinds"], (
            "三态分布基线被改回 X-3 前的 106/102/100（实证 122/118/116）"
        )
        assert _TRULY_DEAD_FACTORY_PREFIXES != _PRE_X3_DEAD_FACTORY_PREFIXES, (
            "死集被改回 X-3 前的 19 个（实证 3 个：h9/l7/l8）"
        )
        assert not (_TRULY_DEAD_FACTORY_PREFIXES & _X3_SHAPE_A_PREFIXES), (
            "死集混入了已被 X-3 点亮的前缀 —— 它们在运行期有形态 A 端点，判据不会命中"
        )

    def test_x3_delta_is_internally_consistent(self) -> None:
        """🔴 X-3 增量的算术自洽：4 个上调值 − X-3 前的值 == 16 / 16 / 16 / 48。

        这条让 4 个新基线**不是魔法数**：只要有人单改其中一个，算术就对不上。
        16 = `len(_X3_SHAPE_A_PREFIXES)`（= `X3_SHEET_SPECS` 的 16 张 sheet），
        48 = 16 × 3（三态）。三态分布逐项也必须各 +16。
        """
        n = len(_X3_SHAPE_A_PREFIXES)
        assert n == 16, f"X-3 前缀集规模变化: {n}"
        assert _BASE_GROUPS - _PRE_X3_BASELINES["groups"] == n
        assert _BASE_FULL3_PREFIXES - _PRE_X3_BASELINES["full3_prefixes"] == n
        assert _BASE_SHAPE_A - _PRE_X3_BASELINES["shape_a"] == n
        assert _BASE_THREE_STATE_ROUTES - _PRE_X3_BASELINES["three_state_routes"] == n * 3
        for kind, before in _PRE_X3_BASELINES["route_kinds"].items():
            assert _BASE_ROUTE_KINDS[kind] - before == n, (
                f"{kind} 增量 != {n}: {_BASE_ROUTE_KINDS[kind]} - {before}"
            )
        assert sum(_BASE_ROUTE_KINDS.values()) == _BASE_THREE_STATE_ROUTES

    def test_task25_targets_are_registered_but_not_yet_applied(self) -> None:
        """🔴 Task 25 的目标值只登记、**不生效**；谁提前套用就打红。

        为什么要有这条：目标值写在同一个文件里，最省事的误用是「先把基线改成目标
        值让守卫看起来前瞻」—— 那会在 19 个模块还在仓里时把守卫锁成红/假绿。
        本条同时钉死目标值与当前值的**差额**，防目标值被随手改成别的数。
        """
        assert set(_TASK25_PENDING_BASELINES) == {
            "_BASE_IE_MODULES",
            "_BASE_FACTORY_PREFIXES",
            "IE_ADAPTER_REGISTRY",
            "_TRULY_DEAD_FACTORY_PREFIXES",
        }, "Task 25 目标值清单被改动 —— 须与父 spec Task 25 的作业面同步裁决"

        # 尚未施加：当前基线必须仍是「删除前」的值
        assert _BASE_IE_MODULES != _TASK25_PENDING_BASELINES["_BASE_IE_MODULES"], (
            "`_BASE_IE_MODULES` 已被改成 Task 25 的目标值，但 19 个工厂模块还在仓里"
        )
        assert (
            _BASE_FACTORY_PREFIXES != _TASK25_PENDING_BASELINES["_BASE_FACTORY_PREFIXES"]
        ), "`_BASE_FACTORY_PREFIXES` 已被提前下调"
        assert _TRULY_DEAD_FACTORY_PREFIXES, (
            "死集被清空 —— 那是 Task 25 的目标态，现在清空 = 判据恒绿"
        )

        # 差额锁死（19 个待删模块，各贡献 1 模块 + 1 工厂 api_prefix）
        n_dead_modules = len(_PRE_X3_DEAD_FACTORY_PREFIXES)
        assert n_dead_modules == 19, f"待删模块数变化: {n_dead_modules}"
        assert (
            _BASE_IE_MODULES - _TASK25_PENDING_BASELINES["_BASE_IE_MODULES"]
            == n_dead_modules
        )
        assert (
            _BASE_FACTORY_PREFIXES
            - _TASK25_PENDING_BASELINES["_BASE_FACTORY_PREFIXES"]
            == n_dead_modules
        )
        # registry 只降 3：另外 16 个键已被 X-3 改指专属 router，不随删除消失
        assert _TASK25_PENDING_BASELINES["IE_ADAPTER_REGISTRY"] == 97 - len(
            _TRULY_DEAD_FACTORY_PREFIXES
        ), "registry 目标值与「当前 97 − 仍指向待删模块的 3 个键」不自洽"

    def test_shape_ab_sum_consistent(self, app_instance) -> None:
        """形态 A + 形态 B 应等于总组数（无第三种形态被静默丢弃）。"""
        shape_a, shape_b = classify_route_shapes(app_instance)
        groups = group_ie_routes(app_instance)
        assert len(shape_a) + len(shape_b) == len(groups), (
            f"形态拆分与总组数不符: A={len(shape_a)} B={len(shape_b)} "
            f"总={len(groups)} ⇒ 存在未被两形态覆盖的路由"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 类 A —— catalog 与运行期路由的缺口（决定 registry 真源选型）
# ═══════════════════════════════════════════════════════════════════════════════


class TestCatalogVsRuntimeGaps:
    def test_catalog_is_subset_of_live_routes(self, app_instance) -> None:
        """catalog 声明的前缀必须**全部**落在运行期三态齐全前缀里（单向包含）。

        🔴 这条判据的方向在 2026-08-10 被修正过一次，记录教训：

        初版写的是 `assert catalog_only`（断言「catalog 独有前缀非空」），
        理由是当时实测 catalog 确有 5 个前缀（`d1-ecl`/`g4`/`g6`/`g7`/`g7-method`）
        落不到运行期端点上。但那 5 个**正是本 spec 要修的缺陷**，把它当成
        「两侧都不是全集」的证据 = 把错值锁成基线（memory 假绿三源之三）：
        修好之后守卫反而打红，且红的方向会诱导下一轮把修复回退掉。

        正确的不变量是**单向**的：
          · catalog ⊆ 运行期活前缀   ← 本条（catalog 声明了就必须能落地）
          · 运行期 ⊋ catalog         ← 下一条（差集 = catalog 缺口 = 待补作业面）
        """
        from app.services.acnr.catalog import list_sheets

        catalog_prefixes: set[str] = set()
        for s in list_sheets(import_export_only=True):
            seg = (s.get("import_export") or {}).get("api_prefix")
            if seg:
                catalog_prefixes.add(seg)

        assert catalog_prefixes, "catalog 无任何 I/E 前缀 —— 扫描面异常"

        route_full3 = {
            k for k, v in group_ie_routes(app_instance).items() if len(v) == 3
        }
        assert route_full3, "运行期无三态齐全前缀 —— 扫描面异常"

        dangling = sorted(catalog_prefixes - route_full3)
        assert not dangling, (
            f"catalog 声明的前缀在运行期无三态端点: {dangling}\n"
            "→ 跑 `python backend/scripts/fix/fix_acnr_dangling_api_prefix.py --check`"
        )

    def test_runtime_has_prefixes_catalog_lacks(self, app_instance) -> None:
        """运行期活前缀**严格多于** catalog ⇒ 差集就是 catalog 缺口。

        这个差集是 Task 14 的作业面，也是「registry 不能只抄 catalog 一侧」的判据。
        非空断言同时防「有人把 catalog 与路由做成双向等价后删掉 Task 14」。
        """
        from app.services.acnr.catalog import list_sheets

        catalog_prefixes = {
            seg
            for s in list_sheets(import_export_only=True)
            if (seg := (s.get("import_export") or {}).get("api_prefix"))
        }
        route_full3 = {
            k for k, v in group_ie_routes(app_instance).items() if len(v) == 3
        }

        gap = route_full3 - catalog_prefixes
        assert gap, (
            "运行期前缀未超出 catalog —— 与实证不符（实测 41 个缺口）；"
            "若确已全部补齐，同步删除 Task 14 并更新本断言"
        )

    def test_catalog_prefixes_have_bulk_adapters(self, app_instance) -> None:
        """🔴 catalog 的每个 `api_prefix` 必须在 `IE_ADAPTER_REGISTRY` 有适配器。

        这是本组**唯一可靠**的判据，理由（2026-08-10 变异检验实证）：

        初版判据写的是「前缀能落到活路由上」，且带一个
        `startswith(f"{p}-")` 的宽容分支 —— 它让 `g4` 被 `g4-main` 冒充、
        `g7-method` 被 `g7-main` 冒充，四个死前缀全部逃逸。
        更糟的是 `d1-ecl`：它在运行期**确实有** `/api/workpapers/{wp_id}/d1-ecl/*`
        三个端点，所以任何「按路由存在性」的判据都放过它，
        而它没有 bulk 适配器 ⇒ 批量导出照样静默跳过。

        变异检验结论：M1（`D1-15` 改回 `d1-ecl`）在旧判据下 **GREEN**，
        M2/M3 只红在无关断言上（WRONG-TEST）。改用适配器判据后三条全 RED。

        真实后果链（为什么必须 fail-loud）：
          `bulk_export_service` → `export_tab(api_prefix=...)`
          → `IE_ADAPTER_REGISTRY.get(prefix)` 返 None → 抛 KeyError
          → 上层 `except KeyError` → `skip_reason=no_adapter`
        全程只有一条 debug 日志，用户拿到的 ZIP 静默少了这些 sheet。
        """
        from app.services.acnr.catalog import list_sheets

        adapters = _adapter_registry_keys()
        assert adapters, "IE_ADAPTER_REGISTRY 为空 —— 适配器注册未触发，判据会空转"

        missing: dict[str, list[str]] = {}
        for s in list_sheets(import_export_only=True):
            seg = (s.get("import_export") or {}).get("api_prefix")
            if not seg or seg in adapters:
                continue
            missing.setdefault(seg, []).append(s.get("sheet_code", "?"))

        assert not missing, (
            "catalog 声明的 api_prefix 无 bulk 适配器 ⇒ 批量导出/回传会以 "
            f"skip_reason=no_adapter 静默跳过，共 {sum(len(v) for v in missing.values())} 个 sheet：\n"
            + "\n".join(f"  · {k} → {', '.join(sorted(v))}" for k, v in sorted(missing.items()))
            + "\n→ 跑 `python backend/scripts/fix/fix_acnr_dangling_api_prefix.py --check`"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
