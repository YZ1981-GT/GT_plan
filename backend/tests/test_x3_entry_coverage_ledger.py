"""GS8 —— `wp_bound_entry_coverage.json` 台账新鲜度守卫（X-3 切片）。

Spec: x3-adjustment-entry-import-export · Task 6.2
Requirements: 10.1（Guard_Suite 覆盖）· 10.10（CI 以追加 step 挂载）
Design: §C8 GS8「新增 48 个端点已进 `wp_bound_entry_coverage.json`」/ E15

## 为什么需要本文件（而不是只靠 `coverage_guard` 自己）

`coverage_guard.check_drift()` 的 `missing_in_ledger` 确实能抓「新端点没进台账」，
但它是**全仓单一布尔**：只要仓里任何一条别的 spec 的入口未分类，`is_clean()` 就是
False，于是「X-3 的 48 条在不在台账」这件事被淹没在别人的红里，既看不出、也无法
在不锁死别人基线的前提下断言。本文件把判据收窄到 X-3 切片：

  * 判据一律落在**运行期路由面**与**台账条目**上（不是「源码里有没有某字符串」）；
  * 分类真伪由 `coverage_guard.detect_route_gate` 从**真实代码**派生复核，台账里写着
    `gate="gated"` 不算证据（anti-fake-pass）；
  * 反向自检 `test_reverse_selfcheck_*` 对**全部 48 条逐条**剔除后跑真守卫，
    并要求新增的那条 finding **指名**被剔掉的路由 —— 只判「红了」会把 WRONG-TEST
    误当 RED；
  * 刻意**不断言** `check_drift().is_clean()`：那会把别的 spec 的存量缺口锁进本 spec
    的基线（R8.6「守卫基线只收已确证正确的值」）。改为断言「没有一条 finding 归因到
    X-3 的 48 条」——本 spec 零漂移，别人的红照旧由它们自己的守卫承载。
"""
from __future__ import annotations

import copy

import pytest

from app.routers.wp_render_strategies._x3_adjustment_import_export import (
    X3_SHEET_SPECS,
    _SUFFIX_DATA,
    _SUFFIX_IMPORT,
    _SUFFIX_TEMPLATE,
)
from app.security import coverage_guard as cg

# 形态 A 三态一律 POST（见 `_register_shape_a` 与 `_SHAPE_A_METHOD` 的成块说明）
_METHOD = "POST"
_SUFFIXES = (_SUFFIX_TEMPLATE, _SUFFIX_DATA, _SUFFIX_IMPORT)


def _x3_prefixes() -> list[str]:
    """16 个短前缀，取自清单真源（不硬编码字面量表）。"""
    return sorted({spec.api_prefix for spec in X3_SHEET_SPECS.values()})


def _expected_keys() -> set[tuple[str, str]]:
    """本 spec 应新增的 (route, method) 集合 —— 从清单派生，**不读** `app.routes`。"""
    return {
        (f"/api/workpapers/{{wp_id}}/{p}/{s}", _METHOD)
        for p in _x3_prefixes()
        for s in _SUFFIXES
    }


def _is_x3_shaped(route: str, method: str) -> bool:
    """该 (route, method) 是否长成 X-3 形态 A 三态（用于 stale 方向的比对）。"""
    if method != _METHOD:
        return False
    for p in _x3_prefixes():
        for s in _SUFFIXES:
            if route == f"/api/workpapers/{{wp_id}}/{p}/{s}":
                return True
    return False


def _label(route: str, method: str) -> str:
    """与 `Findings` 里 item 的前缀形态一致：`"<METHOD> <path>"`。"""
    return f"{method} {route}"


def _finding_keys(findings: cg.Findings) -> set[tuple[str, str, str]]:
    """把 Findings 摊平成 (category, item, 归一化 label) —— item 可能带 " (...)" 后缀。"""
    out: set[tuple[str, str, str]] = set()
    for cat in findings.summary():
        for item in getattr(findings, cat):
            out.add((cat, item, item.split(" (")[0]))
    return out


@pytest.fixture(scope="module")
def real_app():
    from app.main import app

    return app


@pytest.fixture(scope="module")
def live(real_app):
    return cg.scan_live_http(real_app)


@pytest.fixture(scope="module")
def ledger():
    return cg.load_ledger()


@pytest.fixture(scope="module")
def ledger_http(ledger):
    return {
        (e.get("route") or "", e.get("method") or ""): e
        for e in ledger.get("entries", [])
        if e.get("kind") == "http"
    }


# ---------------------------------------------------------------------------
# 锚点 —— 作业面规模与真源
# ---------------------------------------------------------------------------
def test_anchor_workscope_is_sixteen_prefixes_times_three_states():
    """48 = 16 短前缀 × 3 态，且前缀与 sheet 一一对应（真源 = `X3_SHEET_SPECS`）。"""
    prefixes = _x3_prefixes()
    assert len(X3_SHEET_SPECS) == 16, sorted(X3_SHEET_SPECS)
    assert len(prefixes) == 16, prefixes
    assert len(_SUFFIXES) == 3 and len(set(_SUFFIXES)) == 3, _SUFFIXES
    keys = _expected_keys()
    assert len(keys) == 48, len(keys)
    # 每个短前缀恰好服务一张 X-3（前缀撞车会让三态端点互相盖掉）
    per_prefix: dict[str, list[str]] = {}
    for code, spec in X3_SHEET_SPECS.items():
        per_prefix.setdefault(spec.api_prefix, []).append(code)
    assert all(len(v) == 1 for v in per_prefix.values()), per_prefix


def test_anchor_x3_shape_predicate_is_neither_vacuous_nor_universal():
    """`_is_x3_shaped` 判据自检：对 48 条恒真、对形近但非作业面的路径恒假。

    没有这条，`test_ledger_x3_slice_is_bidirectionally_equal_to_runtime` 的 stale 方向
    可能因判据恒假而空转（永远比对空集 == 空集）。
    """
    for route, method in _expected_keys():
        assert _is_x3_shaped(route, method), (route, method)
    negatives = [
        ("/api/workpapers/{wp_id}/l2/export-template", "GET"),  # 方法不符
        ("/api/workpapers/{wp_id}/l2/export-templates", _METHOD),  # 后缀形近
        ("/api/workpapers/{wp_id}/j1/export-template", _METHOD),  # 非 X-3 前缀
        ("/api/workpapers/{wp_id}/l2/import-aux-balance", _METHOD),
        ("/api/projects/{project_id}/workpapers/{wp_id}/l2/export-data", _METHOD),
    ]
    for route, method in negatives:
        assert not _is_x3_shaped(route, method), (route, method)


# ---------------------------------------------------------------------------
# 运行期存在（台账收录一条运行期不存在的端点毫无意义）
# ---------------------------------------------------------------------------
def test_all_forty_eight_endpoints_exist_at_runtime(live):
    """∀48：运行期真有该 (route, POST)，且被判为 wp_bound。"""
    missing = sorted(_label(r, m) for r, m in _expected_keys() if (r, m) not in live)
    assert missing == [], f"运行期缺少形态 A 端点: {missing}"
    not_wp_bound = sorted(
        _label(r, m) for r, m in _expected_keys() if not live[(r, m)].wp_bound
    )
    assert not_wp_bound == [], f"应判 wp_bound 却没判到: {not_wp_bound}"


# ---------------------------------------------------------------------------
# 台账收录 —— 双向（缺失 与 幽灵 都要红）
# ---------------------------------------------------------------------------
def test_ledger_records_all_forty_eight_endpoints(ledger_http):
    """48 条逐条在台账里 —— 台账没重生成（或被回退）即红。"""
    missing = sorted(_label(r, m) for r, m in _expected_keys() if (r, m) not in ledger_http)
    assert missing == [], (
        f"台账缺 {len(missing)} 条 X-3 形态 A 端点，需重跑生成器 "
        "`python -c \"from app.security.coverage_guard import write_reconciled_ledger as w; w()\"`: "
        f"{missing}"
    )


def test_ledger_x3_slice_is_bidirectionally_equal_to_runtime(live, ledger_http):
    """台账里长成 X-3 形态的条目集 == 运行期的 48 条（双向）。

    单向（⊇）只抓「漏登记」；反向抓「台账留着一条已经不存在的 X-3 端点」——那会让
    下一轮读台账的人以为某张表还有导入通路。
    """
    ledger_x3 = {k for k in ledger_http if _is_x3_shaped(*k)}
    live_x3 = {k for k in live if _is_x3_shaped(*k)}
    expected = _expected_keys()
    assert live_x3 == expected, {
        "live_only": sorted(_label(*k) for k in live_x3 - expected),
        "expected_only": sorted(_label(*k) for k in expected - live_x3),
    }
    assert ledger_x3 == expected, {
        "ledger_only(stale)": sorted(_label(*k) for k in ledger_x3 - expected),
        "expected_only(missing)": sorted(_label(*k) for k in expected - ledger_x3),
    }


# ---------------------------------------------------------------------------
# 分类真伪 —— 台账写的 gate 必须被真实代码印证（anti-fake-pass）
# ---------------------------------------------------------------------------
def test_each_entry_classification_is_backed_by_real_code(live, ledger_http):
    """∀48：台账 `gate` 非 unmigrated/占位，且**真实代码**确有门控接线。

    左侧（台账声明）与右侧（`detect_route_gate` 从路由对象/AST 派生）互相印证：
    只改台账字符串不改代码 ⇒ 右侧不成立 ⇒ 红；只删门控不改台账 ⇒ 同样红。
    """
    problems: list[str] = []
    for key in sorted(_expected_keys()):
        e = ledger_http.get(key)
        if e is None:
            problems.append(f"{_label(*key)}: 台账无此条目")
            continue
        gate = e.get("gate")
        if gate in (None, "", "unmigrated", "not_applicable"):
            problems.append(f"{_label(*key)}: gate={gate!r} 不是已接入门控的分类")
        if not e.get("wp_bound"):
            problems.append(f"{_label(*key)}: wp_bound 为假")
        if not e.get("test_ids"):
            problems.append(f"{_label(*key)}: test_ids 为空（无稳定测试证据）")
        # 右侧：真实代码派生
        le = live.get(key)
        if le is None or not le.gate_wired:
            problems.append(
                f"{_label(*key)}: 真实代码未检出门控接线 "
                f"(gate_detail={getattr(le, 'gate_detail', 'n/a')!r})"
            )
    assert problems == [], problems


def test_anchor_gate_detector_discriminates_on_the_route_dep_path():
    """非空转自检：`detect_route_gate` 对「同形路径但没挂 gate 依赖」必须返 False。

    本文件对 48 条的右侧判据全部走 **route-level 依赖** 这条通路（形态 A 三态从宿主
    router 继承 `dedicated_wp_gate`），若该探测恒为 True，
    `test_each_entry_classification_is_backed_by_real_code` 的右侧就是空转。
    """
    from fastapi import Depends, FastAPI

    def dedicated_wp_gate() -> None:  # 名字即判据（`ROUTE_DEP_GATE_NAMES`）
        return None

    async def handler(wp_id: str) -> dict:
        return {"wp_id": wp_id}

    app = FastAPI()
    app.add_api_route(
        "/api/workpapers/{wp_id}/probe-gated",
        handler,
        methods=[_METHOD],
        dependencies=[Depends(dedicated_wp_gate)],
    )
    app.add_api_route("/api/workpapers/{wp_id}/probe-bare", handler, methods=[_METHOD])
    by_path = {r.path: r for r in app.routes if getattr(r, "methods", None)}
    assert cg.detect_route_gate(by_path["/api/workpapers/{wp_id}/probe-gated"])[0] is True
    assert cg.detect_route_gate(by_path["/api/workpapers/{wp_id}/probe-bare"])[0] is False


def test_each_entry_matrix_ref_is_registered_in_action_matrix(ledger_http):
    """∀48：`matrix` 能解析成 (entrypoint, action) 且已在 `ActionMatrix` 登记。"""
    registered = cg.matrix_registered_pairs()
    bad: list[str] = []
    for key in sorted(_expected_keys()):
        e = ledger_http.get(key)
        assert e is not None, f"{_label(*key)} 不在台账（前置断言应先红）"
        pair = cg.parse_matrix_ref(e.get("matrix"))
        if pair is None:
            bad.append(f"{_label(*key)}: matrix={e.get('matrix')!r} 解析不出 entrypoint/action")
        elif pair not in registered:
            bad.append(f"{_label(*key)}: matrix={e.get('matrix')!r} 未在 ActionMatrix 登记")
    assert bad == [], bad


# ---------------------------------------------------------------------------
# 「本 spec 零漂移」—— 不锁死别的 spec 的存量红
# ---------------------------------------------------------------------------
def test_no_guard_finding_is_attributable_to_the_x3_workscope(real_app, ledger):
    """`check_drift` 的全部 findings 里，没有一条归因到 X-3 的 48 条。

    刻意不写 `assert f.is_clean()`：本仓当前另有别的 spec 的存量缺口（未接门控的
    wp-bound 端点 / 未审计的 native_authz 入口），把它们锁进本 spec 的基线既不诚实、
    也会在别人修好时反过来打红。
    """
    findings = cg.check_drift(app=real_app, ledger=ledger)
    labels = {_label(r, m) for r, m in _expected_keys()}
    attributable = sorted(
        f"{cat}: {item}" for cat, item, head in _finding_keys(findings) if head in labels
    )
    assert attributable == [], attributable


# ---------------------------------------------------------------------------
# 反向自检 —— 漏掉任一端点必须打红（∀48，四态判读）
# ---------------------------------------------------------------------------
def test_reverse_selfcheck_dropping_any_endpoint_makes_guard_red(real_app, ledger):
    """∀48：从台账剔掉任一条 ⇒ `check_drift` 恰新增 1 条 `missing_in_ledger` 且指名它。

    四态判读（只看「是否变红」会把 WRONG-TEST 误当 RED）：
      RED        = 新增恰 1 条且落在 `missing_in_ledger`、item 恰是被剔那条
      GREEN      = findings 规模未变 ⇒ 守卫缺陷
      WRONG-TEST = 红了但不是那条（或连带多条）⇒ 判据错位
    """
    control = cg.check_drift(app=real_app, ledger=ledger)
    control_keys = _finding_keys(control)
    verdicts: dict[str, list[str]] = {"GREEN": [], "WRONG-TEST": []}
    for key in sorted(_expected_keys()):
        route, method = key
        mutated = copy.deepcopy(ledger)
        before = len(mutated["entries"])
        mutated["entries"] = [
            e
            for e in mutated["entries"]
            if not (
                e.get("kind") == "http"
                and e.get("route") == route
                and e.get("method") == method
            )
        ]
        assert before - len(mutated["entries"]) == 1, (
            f"{_label(*key)}: 期望剔掉恰 1 行，实剔 {before - len(mutated['entries'])} 行"
        )
        f = cg.check_drift(app=real_app, ledger=mutated)
        new = _finding_keys(f) - control_keys
        if f.total() == control.total():
            verdicts["GREEN"].append(_label(*key))
        elif not (
            len(new) == 1
            and next(iter(new))[0] == "missing_in_ledger"
            and next(iter(new))[1] == _label(*key)
        ):
            verdicts["WRONG-TEST"].append(f"{_label(*key)} -> {sorted(new)}")
    assert verdicts["GREEN"] == [], f"守卫缺陷（剔掉端点未打红）: {verdicts['GREEN']}"
    assert verdicts["WRONG-TEST"] == [], f"判据错位: {verdicts['WRONG-TEST']}"


def test_reverse_selfcheck_attribution_helper_is_not_vacuous(real_app, ledger):
    """自检 `test_no_guard_finding_is_attributable_to_the_x3_workscope` 的归因判据非空转。

    剔掉一条 X-3 端点后，同一段归因代码**必须**能把新出现的 finding 归到 X-3 名下。
    否则「零归因」可能只是因为归因判据永远匹配不上。
    """
    victim = (f"/api/workpapers/{{wp_id}}/{_x3_prefixes()[0]}/{_SUFFIX_IMPORT}", _METHOD)
    mutated = copy.deepcopy(ledger)
    mutated["entries"] = [
        e
        for e in mutated["entries"]
        if not (
            e.get("kind") == "http"
            and e.get("route") == victim[0]
            and e.get("method") == victim[1]
        )
    ]
    findings = cg.check_drift(app=real_app, ledger=mutated)
    labels = {_label(r, m) for r, m in _expected_keys()}
    attributable = sorted(
        f"{cat}: {item}" for cat, item, head in _finding_keys(findings) if head in labels
    )
    assert attributable == [f"missing_in_ledger: {_label(*victim)}"], attributable
