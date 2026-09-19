"""test_x3_adapter_host_same_module —— 用例层。

判据（常量 / 登记表 / fixture / 纯函数 / helper）见 `_test_x3_adapter_host_same_module_criteria.py`，
原文件 docstring 也在那里。拆分原因：原单文件 882 行 > pre-commit 800 行门禁。
"""

from __future__ import annotations

import hashlib
import importlib
import re
from pathlib import Path
from typing import Any, Callable

import pytest

from tests.test_ie_route_inventory import classify_route_shapes

from tests._test_x3_adapter_host_same_module_criteria import (  # noqa: F401  fixtures 需在本模块命名空间
    _ADAPTER_SRC,
    _BASE_ADAPTER_REGISTRY_MIN_KEYS,
    _BASE_CATALOG_IE_PREFIXES_MIN,
    _BASE_COARSE_SHAPE_A_PREFIXES,
    _BASE_KEYS_WITHOUT_STRICT_SHAPE_A,
    _BASE_KEYS_WITH_STRICT_SHAPE_A,
    _BASE_PREFIX_TO_MODULE_KEYS,
    _BASE_STRICT_SHAPE_A_PREFIXES,
    _COARSE_ONLY_NON_SHAPE_A,
    _EXPECTED_VIOLATION_HOSTS,
    _FACTORY_CLOSURE_MODULE,
    _KEYS_WITHOUT_STRICT_SHAPE_A,
    _MIN_COMPARED_PAIRS,
    _PRE_X3_BASELINES,
    _SPLIT_BRAIN_BASELINE,
    _THREE_STATE,
    _X3_STRICT_SHAPE_A_PREFIXES,
    _adapter_registry_keys,
    _catalog_ie_prefixes,
    _is_strict_shape_a,
    _md5,
    app_instance,
    identity_violations,
    module_path_violations,
    report,
    resolve_target_module_path,
    split_brain_report,
    strict_shape_a_endpoints,
    strict_shape_a_routes,
)

__all__ = [
    "_ADAPTER_SRC",
    "_BASE_ADAPTER_REGISTRY_MIN_KEYS",
    "_BASE_CATALOG_IE_PREFIXES_MIN",
    "_BASE_COARSE_SHAPE_A_PREFIXES",
    "_BASE_KEYS_WITHOUT_STRICT_SHAPE_A",
    "_BASE_KEYS_WITH_STRICT_SHAPE_A",
    "_BASE_PREFIX_TO_MODULE_KEYS",
    "_BASE_STRICT_SHAPE_A_PREFIXES",
    "_COARSE_ONLY_NON_SHAPE_A",
    "_EXPECTED_VIOLATION_HOSTS",
    "_FACTORY_CLOSURE_MODULE",
    "_KEYS_WITHOUT_STRICT_SHAPE_A",
    "_MIN_COMPARED_PAIRS",
    "_PRE_X3_BASELINES",
    "_SPLIT_BRAIN_BASELINE",
    "_THREE_STATE",
    "_X3_STRICT_SHAPE_A_PREFIXES",
    "_adapter_registry_keys",
    "_catalog_ie_prefixes",
    "_is_strict_shape_a",
    "_md5",
    "app_instance",
    "identity_violations",
    "module_path_violations",
    "report",
    "resolve_target_module_path",
    "split_brain_report",
    "strict_shape_a_endpoints",
    "strict_shape_a_routes",
]


class TestScanSurface:
    def test_prefix_to_module_key_count(self) -> None:
        from app.services.bulk_tab._kfgh_cycle_adapters import _PREFIX_TO_MODULE

        assert len(_PREFIX_TO_MODULE) == _BASE_PREFIX_TO_MODULE_KEYS, (
            f"`_PREFIX_TO_MODULE` 键数变化: {len(_PREFIX_TO_MODULE)} != "
            f"{_BASE_PREFIX_TO_MODULE_KEYS}（design E7）。若确为增删，同步更新基线并在 spec Notes 留痕"
        )

    def test_coarse_shape_a_prefix_count(self, app_instance) -> None:
        """清册粗口径的形态 A 前缀数（任务 1.4 要求 > 50；实测 101，X-3 前 85）。"""
        coarse_a, _ = classify_route_shapes(app_instance)
        assert len(coarse_a) > 50, f"形态 A 扫描面异常小: {len(coarse_a)}"
        assert len(coarse_a) == _BASE_COARSE_SHAPE_A_PREFIXES, (
            f"粗口径形态 A 前缀数变化: {len(coarse_a)} != {_BASE_COARSE_SHAPE_A_PREFIXES}"
        )

    def test_strict_shape_a_prefix_count(self, app_instance) -> None:
        live = strict_shape_a_endpoints(app_instance)
        assert len(live) > 50, f"严格形态 A 扫描面异常小: {len(live)}"
        assert len(live) == _BASE_STRICT_SHAPE_A_PREFIXES, (
            f"严格形态 A 前缀数变化: {len(live)} != {_BASE_STRICT_SHAPE_A_PREFIXES}"
        )

    def test_adapter_registry_nonempty(self) -> None:
        keys = _adapter_registry_keys()
        assert keys, "IE_ADAPTER_REGISTRY 为空 —— 适配器注册未触发，本文件全部判据会空转"
        assert len(keys) >= _BASE_ADAPTER_REGISTRY_MIN_KEYS, (
            f"IE_ADAPTER_REGISTRY 规模下降: {len(keys)} < {_BASE_ADAPTER_REGISTRY_MIN_KEYS}"
        )

    def test_catalog_ie_prefix_surface(self) -> None:
        catalog = _catalog_ie_prefixes()
        assert len(catalog) >= _BASE_CATALOG_IE_PREFIXES_MIN, (
            f"catalog 启用 I/E 的 api_prefix 数下降: {len(catalog)} < "
            f"{_BASE_CATALOG_IE_PREFIXES_MIN}"
        )

    def test_compared_pair_count(self, report) -> None:
        """实判的 (prefix, suffix) 对数必须足量（实测 204 = 68 × 3）。"""
        pairs = sum(len(r["compared_suffixes"]) for r in report.values())
        assert pairs >= _MIN_COMPARED_PAIRS, (
            f"实判对数异常少: {pairs} < {_MIN_COMPARED_PAIRS} —— 判据可能已空转"
        )

    def test_keys_with_strict_shape_a_matches_e7(self, app_instance) -> None:
        """89 键的划分：X-3 后 **84 / 5**（design E7 记的 68 / 21 是 X-3 前）。

        无形态 A 的 5 个键**逐个钉死**而不只钉数量 —— 「换一个键但总数不变」
        （比如 X-3 少接一张、同时别处多接一张）在只钉数量时是静默的。
        """
        from app.services.bulk_tab._kfgh_cycle_adapters import _PREFIX_TO_MODULE

        live = strict_shape_a_endpoints(app_instance)
        full3 = {p for p, v in live.items() if set(v) == set(_THREE_STATE)}
        with_a = set(_PREFIX_TO_MODULE) & full3
        without_a = set(_PREFIX_TO_MODULE) - full3
        assert len(with_a) == _BASE_KEYS_WITH_STRICT_SHAPE_A, (
            f"有形态 A 三态的键数变化: {len(with_a)} != {_BASE_KEYS_WITH_STRICT_SHAPE_A}"
            "（design E7 的 68 是 X-3 前的值）"
        )
        assert len(without_a) == _BASE_KEYS_WITHOUT_STRICT_SHAPE_A, (
            f"无形态 A 三态的键数变化: {len(without_a)} != "
            f"{_BASE_KEYS_WITHOUT_STRICT_SHAPE_A}: {sorted(without_a)}"
        )
        assert without_a == set(_KEYS_WITHOUT_STRICT_SHAPE_A), (
            f"无形态 A 三态的键集变化: 新增 {sorted(without_a - _KEYS_WITHOUT_STRICT_SHAPE_A)}"
            f" / 已获得 {sorted(_KEYS_WITHOUT_STRICT_SHAPE_A - without_a)}"
        )
        # X-3 的 16 个前缀必须全在「有形态 A」那一侧（它们正是本次上调的增量）
        assert _X3_STRICT_SHAPE_A_PREFIXES <= with_a, (
            f"X-3 前缀缺形态 A 三态: {sorted(_X3_STRICT_SHAPE_A_PREFIXES - with_a)}"
        )

    def test_no_shadowed_strict_shape_a_routes(self, app_instance) -> None:
        """同一 (前缀, 后缀) 不得注册两次 —— 否则「用户打到哪个端点」由注册顺序决定。"""
        seen: dict[tuple[str, str], str] = {}
        shadowed: list[str] = []
        for route in app_instance.routes:
            segs = getattr(route, "path", "").strip("/").split("/")
            if not _is_strict_shape_a(segs):
                continue
            key = (segs[-2], segs[-1])
            mod = getattr(getattr(route, "endpoint", None), "__module__", "?")
            if key in seen:
                shadowed.append(f"{key} 先 {seen[key]} 后 {mod}")
            else:
                seen[key] = mod
        assert not shadowed, f"形态 A 路由被重复注册（后者永不可达）: {shadowed}"


# ═══════════════════════════════════════════════════════════════════════════════
# 核心不变量 —— split-brain 违规集
# ═══════════════════════════════════════════════════════════════════════════════


class TestSplitBrainBaseline:
    def test_violation_set_matches_baseline(self, report) -> None:
        """🔴 全量作业面的违规集 == 基线 5（`h7`/`l1`/`l3`/`l4`/`l5`）。"""
        violations = module_path_violations(report)
        added = sorted(violations - _SPLIT_BRAIN_BASELINE)
        fixed = sorted(_SPLIT_BRAIN_BASELINE - violations)
        detail = "\n".join(
            f"  · {p}: 界面宿主 {report[p]['host']} vs bulk 目标 {report[p]['target']} "
            f"→ 实际解析到 {report[p]['adapter']}"
            for p in added
        )
        assert violations == set(_SPLIT_BRAIN_BASELINE), (
            f"split-brain 违规集变化（基线 {len(_SPLIT_BRAIN_BASELINE)}）:\n"
            f"  新增违规: {added}\n{detail}\n"
            f"  已修好  : {fixed}\n"
            "新增违规 = 又有一个前缀的界面与批量跑两套实现，必须修而不是抬基线。\n"
            "下调是好事，但须同步下调 `_SPLIT_BRAIN_BASELINE` 并在 spec Notes 留痕。"
        )

    def test_catalog_prefixes_within_baseline(self, report) -> None:
        """∀catalog `api_prefix`（任务 1.4 的作业面口径）：违规集同样 == 基线 5。

        catalog 侧单独判一遍，因为 bulk 只对 catalog 启用的前缀取数 ——
        catalog 里的 split-brain 才是**已上线**的用户可见风险。
        """
        catalog = _catalog_ie_prefixes()
        assert catalog, "catalog 无任何 I/E 前缀 —— 扫描面异常，本条判据会空转"

        comparable = sorted(p for p in report if p in catalog)
        assert len(comparable) > 30, (
            f"catalog ∩ 形态 A ∩ `_PREFIX_TO_MODULE` 可比前缀异常少: {len(comparable)}"
        )
        violations = {p for p in module_path_violations(report) if p in catalog}
        assert violations == set(_SPLIT_BRAIN_BASELINE), (
            f"catalog 侧 split-brain 违规集变化: 新增 "
            f"{sorted(violations - _SPLIT_BRAIN_BASELINE)} / 已修好 "
            f"{sorted(_SPLIT_BRAIN_BASELINE - violations)}\n"
            f"（涉及 sheet: "
            f"{ {p: catalog.get(p, []) for p in sorted(violations - _SPLIT_BRAIN_BASELINE)} }）"
        )

    def test_violation_hosts_are_pinned_module_paths(self, report) -> None:
        """5 例的宿主模块点路径逐条钉死 —— 按模块路径判，不按导入别名判。

        父 spec 曾因 `router_registry/workpaper.py` 里专属 router 的导入别名恰好叫
        `l1_import_export`（与工厂模块同名）而把 `l1` 误判。这里比的是
        `endpoint.__module__`，别名改名不影响判定。
        """
        for prefix, expected_host in sorted(_EXPECTED_VIOLATION_HOSTS.items()):
            assert prefix in report, f"{prefix} 已无形态 A 端点 —— 结构变化，需显式裁决"
            hosts = report[prefix]["host"]
            assert hosts == [expected_host], (
                f"{prefix} 形态 A 宿主模块变化: {hosts} != ['{expected_host}']"
            )
            assert report[prefix]["adapter"] == [_FACTORY_CLOSURE_MODULE], (
                f"{prefix} 的 adapter 已不再解析到工厂闭包: {report[prefix]['adapter']} "
                "—— 若已改指专属模块则 split-brain 已修好，请下调基线"
            )
            assert expected_host != report[prefix]["target"], (
                f"{prefix} 的宿主模块与 adapter 目标模块已同一 —— 基线应下调"
            )

    def test_identity_criterion_agrees_with_module_criterion(self, report) -> None:
        """判据双跑：端点对象同一性给出的违规集必须与模块路径判据一致。

        两者互为反向自检 —— 模块路径相同但对象不同（同一前缀被两个模块各造一份
        工厂闭包）也是 split-brain，这条会抓住。
        """
        by_module = module_path_violations(report)
        by_identity = identity_violations(report)
        assert by_identity == by_module, (
            f"两判据不一致: 模块路径 {sorted(by_module)} vs 端点对象 {sorted(by_identity)}\n"
            f"  仅对象不同（同模块两份闭包）: {sorted(by_identity - by_module)}\n"
            f"  仅模块不同（对象却同一）  : {sorted(by_module - by_identity)}"
        )
        assert by_identity == set(_SPLIT_BRAIN_BASELINE), (
            f"端点对象判据的违规集 != 基线: {sorted(by_identity)}"
        )

    def test_non_violating_prefixes_share_the_same_endpoint(self, report) -> None:
        """非违规前缀必须**共用同一个端点函数对象** ⇒ 界面与批量跑同一份实现。

        这是本守卫的正向断言：只断言「违规集 == 5」会让「所有前缀都不可比」这种
        退化状态照样通过。
        """
        broken: list[str] = []
        for prefix, r in sorted(report.items()):
            if prefix in _SPLIT_BRAIN_BASELINE:
                continue
            if r["unresolvable"] or r["identity_mismatch"] or r["host"] != r["adapter"]:
                broken.append(f"{prefix}: {r}")
        assert not broken, f"非违规前缀的两侧实现不同源: {broken}"

    def test_every_comparable_prefix_resolves_on_adapter_side(self, report) -> None:
        """adapter 侧三态全解析不到的前缀 = fail-loud（不得静默跳过后当成「不违规」）。"""
        unresolvable = sorted(p for p, r in report.items() if r["unresolvable"])
        assert not unresolvable, (
            f"这些前缀有形态 A 端点，但 bulk adapter 的目标模块解析不出任何三态端点 "
            f"⇒ 批量导出会 RuntimeError / 导入 failed: {unresolvable}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 口径锁死 —— 防「放宽口径 + 抬基线」这种假绿修法
# ═══════════════════════════════════════════════════════════════════════════════


class TestCriterionLock:
    def test_coarse_criterion_would_add_known_non_shape_a_prefixes(
        self, app_instance
    ) -> None:
        """粗口径比严格口径**多**出的违规必须恰好是 `h5` / `n4`（第三形态，非形态 A）。

        钉死这一条是为了：谁把口径放宽到 `segs[-2]`，违规集会变 7，此时正确处置是
        改回严格口径，**不是**把基线抬到 7。
        """
        strict_v = module_path_violations(split_brain_report(app_instance, strict=True))
        coarse_v = module_path_violations(split_brain_report(app_instance, strict=False))
        assert coarse_v - strict_v == set(_COARSE_ONLY_NON_SHAPE_A), (
            f"粗口径多出的违规集变化: {sorted(coarse_v - strict_v)} != "
            f"{sorted(_COARSE_ONLY_NON_SHAPE_A)}"
        )
        assert not strict_v - coarse_v, (
            f"严格口径独有违规: {sorted(strict_v - coarse_v)} —— 粗口径应是严格口径的超集"
        )

    def test_shape_c_prefixes_have_no_wp_id_segment(self, app_instance) -> None:
        """`h5` / `n4` 的三态路径实测是 `/api/{prefix}/{三态}`（无 `{wp_id}` 段）。

        这是「它们不属形态 A」的行为证据，不是靠注释声明。
        """
        for prefix in sorted(_COARSE_ONLY_NON_SHAPE_A):
            paths = [
                p
                for route in app_instance.routes
                if (p := getattr(route, "path", "")).strip("/").split("/")[-1] in _THREE_STATE
                and p.strip("/").split("/")[-2] == prefix
            ]
            assert paths, f"{prefix} 三态端点消失 —— 结构变化，需显式裁决"
            assert all(f"/api/{prefix}/" in p and "workpapers" not in p for p in paths), (
                f"{prefix} 的三态路径已变形（可能已成为真形态 A ⇒ 属真违规，须显式裁决）: {paths}"
            )
        live = strict_shape_a_endpoints(app_instance)
        overlap = sorted(set(_COARSE_ONLY_NON_SHAPE_A) & set(live))
        assert not overlap, f"{overlap} 已获得严格形态 A 端点 ⇒ 应计入违规集并重新裁决基线"

    def test_baseline_rejects_stale_figures(self) -> None:
        """🔴 基线不得被抬到 7（粗口径错值），也不得被清空（清空 = 判据永绿）。"""
        assert len(_SPLIT_BRAIN_BASELINE) == 5, (
            f"基线规模 {len(_SPLIT_BRAIN_BASELINE)}：7 是粗口径错值（含 h5/n4）；"
            "基线只许下调，且下调必须伴随 spec Notes 留痕"
        )
        assert _SPLIT_BRAIN_BASELINE, "基线被清空 ⇒ 判据恒绿"
        assert set(_EXPECTED_VIOLATION_HOSTS) == set(_SPLIT_BRAIN_BASELINE), (
            "`_EXPECTED_VIOLATION_HOSTS` 与基线不同步 ⇒ 有违规前缀的宿主未被钉死"
        )
        assert not (_SPLIT_BRAIN_BASELINE & _COARSE_ONLY_NON_SHAPE_A), (
            "基线混入了粗口径假阳性（h5 / n4）"
        )

    def test_scan_surface_baselines_reject_pre_x3_figures(self) -> None:
        """🔴 四个扫描面基线不得被改回 X-3 前的旧值（85 / 78 / 68 / 21）。

        为什么要单立一条：这四个数被改回旧值时，打红的是
        `TestScanSurface` 里的**扫描面**断言，红的文案长得像「运行期变了」，
        很容易被下一轮读成「app 少注册了 16 个前缀」而去改生产代码。本条把
        「是基线被改回旧值」这件事单独说清楚。
        """
        assert _BASE_COARSE_SHAPE_A_PREFIXES != _PRE_X3_BASELINES["coarse_shape_a"], (
            "粗口径形态 A 基线被改回 X-3 前的 85（实证 101）"
        )
        assert _BASE_STRICT_SHAPE_A_PREFIXES != _PRE_X3_BASELINES["strict_shape_a"], (
            "严格形态 A 基线被改回 X-3 前的 78（实证 94）"
        )
        assert (
            _BASE_KEYS_WITH_STRICT_SHAPE_A
            != _PRE_X3_BASELINES["keys_with_strict_shape_a"]
        ), "有形态 A 三态的键数被改回 X-3 前的 68（实证 84）"
        assert (
            _BASE_KEYS_WITHOUT_STRICT_SHAPE_A
            != _PRE_X3_BASELINES["keys_without_strict_shape_a"]
        ), "无形态 A 三态的键数被改回 X-3 前的 21（实证 5）"
        assert len(_KEYS_WITHOUT_STRICT_SHAPE_A) == _BASE_KEYS_WITHOUT_STRICT_SHAPE_A, (
            "钉死的键集与键数基线不同步"
        )
        assert not (_KEYS_WITHOUT_STRICT_SHAPE_A & _X3_STRICT_SHAPE_A_PREFIXES), (
            "无形态 A 的键集里混进了 X-3 前缀 —— 它们已有形态 A 三态"
        )

    def test_x3_delta_is_internally_consistent(self) -> None:
        """🔴 X-3 增量算术自洽：三项 +16、一项 −16，增量 == `X3_SHEET_SPECS` 的 16。

        让四个新基线不是魔法数：单改任一个，算术就对不上。16 这个数本身也不是
        写死的常量，而是 `_X3_STRICT_SHAPE_A_PREFIXES` 的规模，且该集合与
        `_PREFIX_TO_MODULE` 的键集有交（`test_keys_with_strict_shape_a_matches_e7`
        断言它整体落在「有形态 A」那侧）。
        """
        n = len(_X3_STRICT_SHAPE_A_PREFIXES)
        assert n == 16, f"X-3 前缀集规模变化: {n}"
        assert _BASE_COARSE_SHAPE_A_PREFIXES - _PRE_X3_BASELINES["coarse_shape_a"] == n
        assert _BASE_STRICT_SHAPE_A_PREFIXES - _PRE_X3_BASELINES["strict_shape_a"] == n
        assert (
            _BASE_KEYS_WITH_STRICT_SHAPE_A
            - _PRE_X3_BASELINES["keys_with_strict_shape_a"]
            == n
        )
        assert (
            _PRE_X3_BASELINES["keys_without_strict_shape_a"]
            - _BASE_KEYS_WITHOUT_STRICT_SHAPE_A
            == n
        )
        # 89 键的两侧划分必须仍然对得上总数
        assert (
            _BASE_KEYS_WITH_STRICT_SHAPE_A + _BASE_KEYS_WITHOUT_STRICT_SHAPE_A
            == _BASE_PREFIX_TO_MODULE_KEYS
        ), "84 + 5 != 89 ⇒ 划分与键数基线不自洽"
        # 粗口径与严格口径的差恒为 7 个第三形态前缀（X-3 未改变这个差）
        assert (
            _BASE_COARSE_SHAPE_A_PREFIXES - _BASE_STRICT_SHAPE_A_PREFIXES == 7
        ), "粗/严口径差不再是 7 ⇒ 第三形态前缀集变了，须显式裁决"

    def test_module_path_resolution_rule(self) -> None:
        """`_PREFIX_TO_MODULE` 值 → 模块路径的拼接规则（含 design §C3 的点路径形态）。"""
        from app.services.bulk_tab._kfgh_cycle_adapters import _MODULE_PKG

        assert resolve_target_module_path("_k1_import_export") == (
            _MODULE_PKG + "_k1_import_export"
        )
        assert (
            resolve_target_module_path("app.routers.l2_interest_payable")
            == "app.routers.l2_interest_payable"
        )

    def test_every_target_module_is_importable(self) -> None:
        """89 个目标模块逐个真 import —— 拼接规则写错/模块改名立刻暴露（行为判据）。"""
        from app.services.bulk_tab._kfgh_cycle_adapters import _PREFIX_TO_MODULE

        failures: list[str] = []
        for prefix, value in sorted(_PREFIX_TO_MODULE.items()):
            try:
                importlib.import_module(resolve_target_module_path(value))
            except Exception as exc:  # noqa: BLE001 — 记为失败态，不吞成 warning
                failures.append(f"{prefix} → {resolve_target_module_path(value)}: {exc}")
        assert not failures, "adapter 目标模块无法 import:\n" + "\n".join(failures)


# ═══════════════════════════════════════════════════════════════════════════════
# 反向自检 —— 变异必须打红，且自证还原
# ═══════════════════════════════════════════════════════════════════════════════


class TestReverseSelfCheck:
    """三条命名变异，每条**指名它应当由哪条判据抓住**。

    只断言「变异后套件红了」是不够的：红在别的断言上就是 WRONG-TEST，红在
    「锚点没命中」上就是 ANCHOR-MISS，两者都会被误读成 RED。故每条变异都断言
    具体的检测通道。

    三条变异一律**只在进程内**改（字典值 / 路由对象的 `endpoint` 属性），不落盘；
    每条末尾自证还原：重新读值相等 · 违规集回到基线 · 真源文件 md5 未变。
    """

    def test_mutation_foreign_runtime_host_is_caught_as_module_mismatch(
        self, app_instance
    ) -> None:
        """M1：把某个**当前同源**前缀的运行期端点换成别的模块里的函数。

        期望通道 = 模块路径判据（`module_path_violations`）+ 端点对象判据。
        这条证明「新增违规即红」的主路径真的在工作，而不是靠基线相等蒙对。
        """

        def _foreign_stub() -> None:  # `__module__` = 本测试模块，与任何 router 都不同源
            raise AssertionError("stub 不应被调用")

        routes = strict_shape_a_routes(app_instance)
        victim = "k5"
        key = (victim, "export-data")
        assert key in routes, f"变异锚点未命中: {key}（ANCHOR-MISS，非 RED）"
        assert victim not in _SPLIT_BRAIN_BASELINE, f"{victim} 本就在基线里，换一个变异对象"

        route = routes[key]
        original_endpoint = route.endpoint
        md5_before = _md5(_ADAPTER_SRC)
        try:
            route.endpoint = _foreign_stub
            report = split_brain_report(app_instance)
            assert victim in module_path_violations(report), (
                f"M1 未被模块路径判据抓住 ⇒ 守卫空转（GREEN 态 = 守卫缺陷）；"
                f"实测 host={report[victim]['host']} adapter={report[victim]['adapter']}"
            )
            assert victim in identity_violations(report), "M1 未被端点对象判据抓住"
        finally:
            route.endpoint = original_endpoint

        assert strict_shape_a_routes(app_instance)[key].endpoint is original_endpoint, (
            "M1 未还原：路由 endpoint 仍是 stub"
        )
        self._assert_back_to_baseline(app_instance, md5_before)

    def test_mutation_repointing_to_unrelated_module_is_caught_as_unresolvable(
        self, app_instance
    ) -> None:
        """M2：把 `_PREFIX_TO_MODULE["k1"]` 改指 `_k2_import_export`（不服务 `/k1/*`）。

        期望通道 = `unresolvable`（`test_every_comparable_prefix_resolves_on_adapter_side`），
        **不是**模块路径判据 —— 目标模块解析不出任何 `/k1/{三态}` 端点，bulk 会
        RuntimeError / import failed。把这条错记成「模块路径判据应该红」就是 WRONG-TEST。
        """
        from app.services.bulk_tab._kfgh_cycle_adapters import _PREFIX_TO_MODULE

        victim = "k1"
        assert victim in _PREFIX_TO_MODULE, f"变异锚点未命中: {victim}（ANCHOR-MISS）"
        original = _PREFIX_TO_MODULE[victim]
        md5_before = _md5(_ADAPTER_SRC)
        assert victim not in module_path_violations(split_brain_report(app_instance)), (
            f"{victim} 变异前就已违规，换一个变异对象"
        )

        try:
            _PREFIX_TO_MODULE[victim] = "_k2_import_export"
            report = split_brain_report(app_instance)
            assert report[victim]["unresolvable"], (
                "M2 未被 unresolvable 判据抓住 ⇒ adapter 侧解析失败被静默当成「不违规」"
            )
        finally:
            _PREFIX_TO_MODULE[victim] = original

        from app.services.bulk_tab._kfgh_cycle_adapters import (
            _PREFIX_TO_MODULE as reread,
        )

        assert reread[victim] == original, f"M2 未还原: {reread[victim]}"
        assert f'"{victim}": "{original}"' in _ADAPTER_SRC.read_text(encoding="utf-8"), (
            f"真源文件里 {victim} 的映射行不见了"
        )
        self._assert_back_to_baseline(app_instance, md5_before)

    def test_mutation_pointing_l1_at_its_real_host_drops_the_baseline(
        self, app_instance
    ) -> None:
        """M3：把 `l1` 改指它真实的宿主模块（点路径形态，= design §C3 的目标态）。

        期望通道 = 违规集**下调**（`test_violation_set_matches_baseline` 打红并要求
        同步下调基线）。这条同时证明：①点路径解析规则可用 ②「修好了」也会打红，
        所以基线不可能被悄悄放过。
        """
        from app.services.bulk_tab._kfgh_cycle_adapters import _PREFIX_TO_MODULE

        victim = "l1"
        real_host = _EXPECTED_VIOLATION_HOSTS[victim]
        original = _PREFIX_TO_MODULE[victim]
        md5_before = _md5(_ADAPTER_SRC)
        assert victim in module_path_violations(split_brain_report(app_instance)), (
            f"{victim} 变异前不在违规集里 —— 基线已变，本条变异需重设计（ANCHOR-MISS）"
        )

        try:
            _PREFIX_TO_MODULE[victim] = real_host
            report = split_brain_report(app_instance)
            assert not report[victim]["unresolvable"], (
                f"改指 {real_host} 后 adapter 解析不到 `/l1/*` 端点 —— "
                "点路径解析或专属 router 结构与预期不符"
            )
            assert report[victim]["host"] == report[victim]["adapter"], (
                f"改指真实宿主后两侧仍不同源: {report[victim]}"
            )
            violations = module_path_violations(report)
            assert victim not in violations, f"{victim} 已同源却仍被判违规"
            assert violations != set(_SPLIT_BRAIN_BASELINE), (
                "违规集下调后核心断言未打红 ⇒ 基线不会被要求同步下调（守卫缺陷）"
            )
        finally:
            _PREFIX_TO_MODULE[victim] = original

        from app.services.bulk_tab._kfgh_cycle_adapters import (
            _PREFIX_TO_MODULE as reread,
        )

        assert reread[victim] == original, f"M3 未还原: {reread[victim]}"
        self._assert_back_to_baseline(app_instance, md5_before)

    def test_relaxing_the_shape_criterion_turns_red(self, app_instance) -> None:
        """M4：把形态判据放宽成「只看 `segs[-2]`」⇒ 违规集必须偏离基线。

        期望通道 = 违规集比基线**多** `h5`/`n4` ⇒ 证明严格形态 A 口径有实际约束力。
        """
        relaxed = module_path_violations(split_brain_report(app_instance, strict=False))
        assert relaxed != set(_SPLIT_BRAIN_BASELINE), (
            "放宽口径后违规集与基线相同 ⇒ 严格形态 A 判据没有实际约束力，需复核"
        )
        assert relaxed - set(_SPLIT_BRAIN_BASELINE) == set(_COARSE_ONLY_NON_SHAPE_A), (
            f"放宽口径多出的违规集变化: {sorted(relaxed - set(_SPLIT_BRAIN_BASELINE))}"
        )

    @staticmethod
    def _assert_back_to_baseline(app_instance, md5_before: str) -> None:
        """还原自证：违规集回到基线 + 真源文件 md5 未变（变异绝不落盘）。"""
        assert module_path_violations(split_brain_report(app_instance)) == set(
            _SPLIT_BRAIN_BASELINE
        ), "还原后违规集未回到基线"
        assert _md5(_ADAPTER_SRC) == md5_before, (
            "真源文件 md5 变了 —— 本变异本应只在内存里发生，绝不落盘"
        )

    def test_reverse_self_check_relaxing_the_shape_criterion_turns_red(
        self, app_instance
    ) -> None:
        """把形态判据放宽成「只看 `segs[-2]`」⇒ 违规集必须偏离基线（证明口径在起作用）。"""
        relaxed = module_path_violations(split_brain_report(app_instance, strict=False))
        assert relaxed != set(_SPLIT_BRAIN_BASELINE), (
            "放宽口径后违规集与基线相同 ⇒ 严格形态 A 判据没有实际约束力，需复核"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
