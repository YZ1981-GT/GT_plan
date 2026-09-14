"""Property 5 —— **适配器未就绪则拒绝登记**（spec `x3-adjustment-entry-import-export` 任务 9.2）。

被测对象：`backend/scripts/fix/fix_x3_adjustment_ie_registration.py`（Catalog_Registrar，禁改）。
其 Preflight 四门顺序 = `adapter_registered` → `module_resolved` → `three_state_endpoints`
→ `sheet_in_ie_sheets`；任一门不过的 sheet **不进 `plan.pending`**（拒绝，不是警告），
且只要有任何一张被挡，`--apply` **整体不执行**（R5.1 是任务 9.1 的前置门控）。

## 属性表述（Property 5）

> 对**任意**非空的「(目标 sheet, 不就绪形态) 组合」，在一个**未施加**的 catalog 副本上跑
> `--apply`：①每个被注入的 sheet 都出现在 `plan.blocked` 且**不在** `plan.pending`；
> ②退出码为 2；③**两文件**（catalog 副本 + `sources_dir` 副本里的三份 manifest）**逐字节不变**
> （md5 比对）；④未被注入的 sheet 不受连带影响（作业面仍 16 张、被挡集恰等于注入集）。

## 🔴 为什么必须自己造「未施加」态（反空转）

任务 9.1 已施加 —— committed `global_catalog.json` 里 16 段 `import_export` **已在**，
`--check` 现返 **0**。此时拿仓库当刻状态当输入，`plan.pending` 恒为空集，"两文件不变"
会因为**根本没有待写内容**而恒真（空转），四门是否真挡下无从体现。

故本文件**复用**任务 8.3 守卫的 `_catalog_copy_unapplied()`（`tests.test_x3_ie_registrar`）
在 `tmp_path` 副本上剥掉那 16 段，把副本推回「未施加」态 —— 不抄第二份剥段逻辑，该 helper
自带三条反向自检（16 个 addr_id 必须一条一命中 / 剥完必全无 `import_export` / 实剥段数只许
0 或 16，半施加态当场抛）。本文件另在**每条用例内**复核一次结构前提（16 条目标全部无
`import_export`），使「helper 剥段失效」这类退化在属性测试内部即打红，而不是留到断言恒真。

## 正面对照（反空转的另一半）

`test_positive_control_no_injection_really_writes_16_segments`：**同一夹具、不注入任何
不就绪形态** ⇒ `--apply` 必须真的写入 16 段（退出码 0、catalog 副本 md5 变化、差异集恰
16 个 `addr_id`、值逐字段 == Key_Ledger 派生值）。没有这条，"不变"只能证明通路没接通。

## 真实面零写

autouse fixture 在**每条用例前后**复量真实写盘面（committed catalog + 三份真实 manifest
+ Deviation 侧车正路径）的 md5，任一变动当场判红；属性测试每条 example 内部再复量一次。
所有写盘（catalog 副本 / manifest 副本 / Deviation 侧车）全落 `tmp_path`。
🔴 刻意**不**写死 committed catalog 的 md5 字面量 —— 9.1 已施加、后续仍可能合法变化，
锁字面量等于把当刻状态当"正确基线"（R8.6 禁止）；这里只比「本次会话内没被改动」。

Requirements: 5.1, 5.7, 5.8
**Validates: Requirements 5.1**
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# 🔴 复用任务 8.3 守卫的「未施加态」构造器与目标集，禁止在本文件再造一份剥段逻辑。
from tests.test_x3_ie_registrar import (
    _TARGET_ADDR_IDS,
    _TARGET_SHEET_CODES,
    _catalog_copy_unapplied,
    _load_registrar,
    _md5,
)

_REG = _load_registrar()

#: 三态端点后缀（真源 = 登记器常量，不在本文件另抄一份）。
_THREE_STATE: tuple[str, ...] = tuple(_REG.THREE_STATE)

#: sheet_code → api_prefix（真源 = Key_Ledger 派生段，不做字符串手术）。
_PREFIX_BY_CODE: dict[str, str] = {
    code: str(seg["api_prefix"])
    for code, seg in _REG._ledger_x3().items()
    if code in set(_TARGET_SHEET_CODES)
}

#: 四种不就绪形态 → 期望挡下它的那道门。
#:
#: 任务正文点名的三类为「未注册前缀 / 端点解析失败 / sheet 不在白名单」；「前缀未注册」
#: 在实现上有两处物理落点（`IE_ADAPTER_REGISTRY` 缺键 / `_PREFIX_TO_MODULE` 指向不存在的
#: 模块），二者分属不同门、拒绝路径不同，故分开注入并各自钉门名。
_FORM_TO_GATE: dict[str, str] = {
    "unregistered_prefix": "adapter_registered",
    "unresolvable_module": "module_resolved",
    "endpoint_missing": "three_state_endpoints",
    "sheet_not_whitelisted": "sheet_in_ie_sheets",
}
_UNREADY_FORMS: tuple[str, ...] = tuple(_FORM_TO_GATE)

#: 三类形态归并（用于实录/统计口径与任务正文对齐）。
_FORM_CATEGORY: dict[str, str] = {
    "unregistered_prefix": "未注册前缀",
    "unresolvable_module": "未注册前缀",
    "endpoint_missing": "端点解析失败",
    "sheet_not_whitelisted": "sheet 不在白名单",
}

_MISSING_MODULE = "app.routers.does_not_exist_x3_t92_preflight_probe"


# ═══════════════════════════════════════════════════════════════════════════════
# 真实面零写（autouse）
# ═══════════════════════════════════════════════════════════════════════════════


def _real_face_md5s() -> dict[str, str]:
    """真实（非副本）写盘面快照：committed catalog + 三份 manifest + Deviation 侧车正路径。

    侧车文件当前不存在 —— 用 `<absent>` 表达"不存在"也是一种状态，被创建即判红。
    """
    files = [
        _REG.CATALOG,
        *sorted(_REG.SOURCES.glob("*_cycle_ie_manifest.yaml")),
        _REG.DEVIATION_SIDECAR,
    ]
    return {p.name: (_md5(p) if p.exists() else "<absent>") for p in files}


@pytest.fixture(scope="module")
def real_face_baseline() -> dict[str, str]:
    return _real_face_md5s()


@pytest.fixture(autouse=True)
def _real_face_is_never_written(real_face_baseline: dict[str, str]):
    """每条用例前后复量真实写盘面 —— 任何一条用例写到真实文件即当场判红。"""
    assert _real_face_md5s() == real_face_baseline, (
        "用例开始前真实写盘面就已与基线不同 —— 上一条用例写到了真实文件"
    )
    yield
    assert _real_face_md5s() == real_face_baseline, (
        "本用例改到了真实文件（catalog / manifest / Deviation 侧车正路径）——"
        " 任务 9.2 的所有写盘都必须落在 tmp_path"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 夹具：未施加态 catalog 字节 + manifest 副本
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def unapplied_catalog_seed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """「9.1 未施加」态 catalog 的**种子文件** —— 由 8.3 的 `_catalog_copy_unapplied()` 造一次。

    每条 example 都把它 `copyfile` 进本例的副本路径，从而每次输入都是干净的未施加态。
    🔴 刻意返回 Path 而非 bytes：hypothesis 会 repr 每个测试参数，1.4 MB 的 bytes 会触发
    `Generating overly large repr` 并显著拖慢每条 example。"""
    seed_dir = tmp_path_factory.mktemp("x3_t92_unapplied_seed")
    return _catalog_copy_unapplied(seed_dir)


@pytest.fixture(scope="module")
def adapter_registry_snapshot() -> dict[str, Any]:
    """真实注册完成后的 `IE_ADAPTER_REGISTRY` 快照（D 循环需显式注册，故走登记器入口）。"""
    return dict(_REG._adapter_registry())


def _fresh_case_dir(seed: Path, tmp_path: Path) -> tuple[Path, Path, Path]:
    """在 `tmp_path` 里布出「未施加 catalog 副本 + sources 副本 + Deviation 侧车路径」。

    sources 副本收全部 8 份 `*_cycle_ie_manifest.yaml`（与生产读取面同形），其中
    `partial: true` 的恰 3 份（l/m/n）—— 那 3 份才是登记器的作业面真源，故这里把
    「恰 3 份 partial」当结构前提断言；md5 不变量则覆盖全部副本（比只看 3 份更严）。
    """
    src = tmp_path / "sources"
    src.mkdir(exist_ok=True)
    manifests = sorted(_REG.SOURCES.glob("*_cycle_ie_manifest.yaml"))
    for p in manifests:
        shutil.copy2(p, src / p.name)
    partial = sorted(_REG._partial_manifests(src))
    assert len(partial) == 3, f"partial manifest 实读 {partial} != 3 份 —— 路径或作业面变了"
    cat = tmp_path / "global_catalog.json"
    shutil.copyfile(seed, cat)  # 每条 example 都回到干净的「未施加」态
    return cat, src, tmp_path / "registrar_preflight_deviations.json"


def _both_files_md5(cat: Path, src: Path) -> dict[str, str]:
    """「两文件」的 md5：catalog 副本 + `sources_dir` 副本里的 manifest（含 3 份 partial）。"""
    return {cat.name: _md5(cat), **{p.name: _md5(p) for p in sorted(src.glob("*.yaml"))}}


def _assert_copy_is_unapplied(cat: Path) -> None:
    """结构前提：副本里 16 个目标条目**全部**不含 `import_export`。

    这条把「8.3 的剥段 helper 失效（剥 0 段）」直接变成本文件内部的红 —— 否则
    `plan.pending` 恒为空集，后面"两文件不变"会退化成恒真。
    """
    data = json.loads(cat.read_text(encoding="utf-8"))
    hits = [s for s in data.get("sheets", []) if str(s.get("addr_id") or "") in _TARGET_ADDR_IDS]
    assert len(hits) == len(_TARGET_ADDR_IDS), (
        f"副本里只定位到 {len(hits)} / {len(_TARGET_ADDR_IDS)} 个目标 addr_id"
    )
    still_applied = sorted(s["addr_id"] for s in hits if "import_export" in s)
    assert not still_applied, (
        f"副本未处于「未施加」态，{len(still_applied)} 个目标仍带 import_export（如"
        f" {still_applied[:3]}）⇒ 剥段 helper 失效，本属性测试会退化为空转"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 不就绪形态注入器（四门各一处物理落点，其余逐字不变）
# ═══════════════════════════════════════════════════════════════════════════════


def _inject_unready(
    mp: pytest.MonkeyPatch,
    registry_snapshot: dict[str, Any],
    cases: tuple[tuple[str, str, str], ...],
) -> None:
    """按 `(sheet_code, form, suffix)` 注入不就绪形态。只动被点名的那一处。"""
    from app.services.bulk_tab import _kfgh_cycle_adapters as kfgh

    drop_prefixes = {
        _PREFIX_BY_CODE[c] for c, f, _s in cases if f == "unregistered_prefix"
    }
    unresolvable = {
        _PREFIX_BY_CODE[c] for c, f, _s in cases if f == "unresolvable_module"
    }
    endpoint_holes = {
        (_PREFIX_BY_CODE[c], s) for c, f, s in cases if f == "endpoint_missing"
    }
    whitelist_removals: dict[str, set[str]] = {}
    for code, form, _s in cases:
        if form != "sheet_not_whitelisted":
            continue
        whitelist_removals.setdefault(_PREFIX_BY_CODE[code], set()).add(code)

    if drop_prefixes:
        patched = {k: v for k, v in registry_snapshot.items() if k not in drop_prefixes}
        assert len(patched) == len(registry_snapshot) - len(drop_prefixes), (
            f"注入无效：{sorted(drop_prefixes)} 本就不在 IE_ADAPTER_REGISTRY"
        )
        mp.setattr(_REG, "_adapter_registry", lambda: patched)

    if unresolvable:
        mapping = dict(kfgh._PREFIX_TO_MODULE)
        for prefix in unresolvable:
            assert prefix in mapping, f"注入无效：_PREFIX_TO_MODULE 本就无 '{prefix}'"
            mapping[prefix] = _MISSING_MODULE
        mp.setattr(kfgh, "_PREFIX_TO_MODULE", mapping)

    if endpoint_holes:
        real_endpoint_for = kfgh._endpoint_for

        def _holed(module: Any, api_prefix: str, suffix: str) -> Any:
            if (api_prefix, suffix) in endpoint_holes:
                return None
            return real_endpoint_for(module, api_prefix, suffix)

        mp.setattr(kfgh, "_endpoint_for", _holed)

    for prefix, removed in whitelist_removals.items():
        host = importlib.import_module(kfgh._resolve_module_path(kfgh._PREFIX_TO_MODULE[prefix]))
        declared = getattr(host, "IE_SHEETS", None)
        assert isinstance(declared, (set, frozenset)), (
            f"注入无效：{host.__name__}.IE_SHEETS 类型 {type(declared).__name__}"
        )
        assert removed <= set(declared), (
            f"注入无效：{sorted(removed)} 本就不在 {host.__name__}.IE_SHEETS"
        )
        mp.setattr(host, "IE_SHEETS", frozenset(set(declared) - removed), raising=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5
# ═══════════════════════════════════════════════════════════════════════════════


@st.composite
def _unready_cases(draw: st.DrawFn) -> tuple[tuple[str, str, str], ...]:
    """随机「哪些 sheet / 哪一门 / 组合几处」不就绪（1~4 处，sheet 不重复）。"""
    codes = draw(
        st.lists(st.sampled_from(_TARGET_SHEET_CODES), min_size=1, max_size=4, unique=True)
    )
    forms = draw(
        st.lists(st.sampled_from(_UNREADY_FORMS), min_size=len(codes), max_size=len(codes))
    )
    suffixes = draw(
        st.lists(st.sampled_from(_THREE_STATE), min_size=len(codes), max_size=len(codes))
    )
    return tuple(zip(codes, forms, suffixes))


#: 属性测试实际覆盖到的形态（用于实录；不作断言依赖，避免用例间顺序耦合）。
_OBSERVED_FORMS: dict[str, int] = {form: 0 for form in _UNREADY_FORMS}


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
    ],
)
@given(cases=_unready_cases())
def test_property5_unready_adapter_refuses_registration(
    tmp_path: Path,
    unapplied_catalog_seed: Path,
    adapter_registry_snapshot: dict[str, Any],
    real_face_baseline: dict[str, str],
    cases: tuple[tuple[str, str, str], ...],
) -> None:
    """**Property 5: 适配器未就绪则拒绝登记**

    随机不就绪组合下：被挡 sheet 不进 `pending`、`--apply` 整体不执行、两文件逐字节不变。

    **Validates: Requirements 5.1**
    """
    cat, src, dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    dev.unlink(missing_ok=True)
    _assert_copy_is_unapplied(cat)

    before = _both_files_md5(cat, src)
    victims = {code for code, _f, _s in cases}

    with pytest.MonkeyPatch.context() as mp:
        _inject_unready(mp, adapter_registry_snapshot, cases)
        exit_code = _REG.run("apply", catalog_path=cat, sources_dir=src, deviation_path=dev)
        plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)

    # ① 拒绝而非警告：被挡 sheet 不进 plan.pending
    blocked = {p.sheet_code for p in plan.blocked}
    assert blocked == victims, (
        f"被挡集 {sorted(blocked)} != 注入集 {sorted(victims)}"
        " —— 要么注入没生效（空转），要么连带挡下了别的 sheet"
    )
    pending = {t.sheet_code for t in plan.pending}
    assert not (victims & pending), (
        f"被挡 sheet {sorted(victims & pending)} 仍进了 plan.pending ⇒ 会被写入 catalog"
        "（这正是禁止的「警告而非拒绝」）"
    )
    # 门与理由不许错位：注入哪一门，就必须是那一门（或其前置）报出不过
    for code, form, _s in cases:
        p = next(x for x in plan.blocked if x.sheet_code == code)
        failed = {g.name for g in p.failures}
        assert _FORM_TO_GATE[form] in failed, (
            f"{code}/{form}: 期望门 {_FORM_TO_GATE[form]} 报不过，实际不过的门 {sorted(failed)}"
        )
        _OBSERVED_FORMS[form] += 1

    # 作业面未被打断（不许一处不就绪就整批哑掉）
    assert len(plan.targets) == 16, f"作业面 {len(plan.targets)} 张 != 16"

    # ② --apply 整体不执行：退出码 2 + 两文件逐字节不变
    assert exit_code == 2, f"有 {len(victims)} 张被挡时 --apply 退出码 {exit_code} != 2"
    after = _both_files_md5(cat, src)
    assert after == before, (
        "两文件（catalog 副本 / 三份 manifest 副本）被改动了 —— "
        f"变动项 {[k for k in before if before[k] != after[k]]}"
    )
    _assert_copy_is_unapplied(cat)  # 结构面再确认：一段都没被补上

    # R5.8：拒绝记录落到注入的侧车路径（不是 evidence/ 正路径）
    assert dev.exists(), "有被挡 sheet 时 --apply 未写 Deviation 侧车（R5.8）"
    doc = json.loads(dev.read_text(encoding="utf-8"))
    assert {r["sheet_code"] for r in doc["records"]} == victims
    assert all(r["evidence"]["refused_write"] is True for r in doc["records"])

    # 真实面零写（每条 example 内部再复量一次）
    assert _real_face_md5s() == real_face_baseline, "本 example 写到了真实文件"


# ═══════════════════════════════════════════════════════════════════════════════
# 正面对照（反空转）+ 逐形态实测
# ═══════════════════════════════════════════════════════════════════════════════


def test_positive_control_no_injection_really_writes_16_segments(
    tmp_path: Path, unapplied_catalog_seed: Path
) -> None:
    """🔴 反空转：**同一夹具、不注入任何不就绪形态** ⇒ `--apply` 必须真写入 16 段。

    没有这条，Property 5 的"两文件不变"可能只是通路没接通（例如副本路径没被登记器接受、
    或作业面被算成 0 张）而恒真。
    """
    cat, src, dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    _assert_copy_is_unapplied(cat)

    before_md5 = _both_files_md5(cat, src)
    before = json.loads(cat.read_text(encoding="utf-8"))
    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert plan.blocked == [], f"未注入却有被挡：{[p.reason for p in plan.blocked]}"
    assert len(plan.pending) == 16, f"未施加副本上 pending {len(plan.pending)} != 16"

    assert _REG.run("apply", catalog_path=cat, sources_dir=src, deviation_path=dev) == 0
    after = json.loads(cat.read_text(encoding="utf-8"))
    after_md5 = _both_files_md5(cat, src)

    assert after_md5[cat.name] != before_md5[cat.name], (
        "不注入时 --apply 一个字节都没写 ⇒ Property 5 的「不变」是空转"
    )
    assert {k: v for k, v in after_md5.items() if k != cat.name} == {
        k: v for k, v in before_md5.items() if k != cat.name
    }, "三份 manifest 副本不该被 --apply 改动"
    assert not dev.exists(), "无被挡 sheet 时不该写 Deviation 侧车"

    diff = _REG._structural_diff(before, after)
    assert set(diff) == set(_TARGET_ADDR_IDS), f"差异集 {sorted(diff)}"
    assert all(keys == ["import_export"] for keys in diff.values()), diff
    ledger = _REG._ledger_x3()
    by_addr = {s["addr_id"]: s for s in after["sheets"]}
    for addr in _TARGET_ADDR_IDS:
        code = addr.split("/")[1]
        assert by_addr[addr]["import_export"] == ledger[code], f"{addr} 的段非 Key_Ledger 派生值"


@pytest.mark.parametrize("form", _UNREADY_FORMS)
def test_each_unready_form_leaves_both_files_byte_identical(
    tmp_path: Path,
    unapplied_catalog_seed: Path,
    adapter_registry_snapshot: dict[str, Any],
    form: str,
) -> None:
    """逐形态定点实测（不依赖 hypothesis 抽样命中）：每一种不就绪都必须拒绝且零写盘。

    与 8.3 守卫的逐门用例分工不同：那边判「被挡 sheet 不进 pending」（真实 catalog、
    不涉写盘），这边判「`--apply` 整体不执行 + 两文件逐字节不变」（未施加副本上真跑 apply）。
    注入手法复用同一个 `_inject_unready`，不抄第二份。
    """
    cat, src, dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    _assert_copy_is_unapplied(cat)
    before = _both_files_md5(cat, src)

    victim = "M4-3"
    cases = ((victim, form, "import-data"),)
    with pytest.MonkeyPatch.context() as mp:
        _inject_unready(mp, adapter_registry_snapshot, cases)
        exit_code = _REG.run("apply", catalog_path=cat, sources_dir=src, deviation_path=dev)
        plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)

    assert [p.sheet_code for p in plan.blocked] == [victim]
    assert _FORM_TO_GATE[form] in {g.name for g in plan.blocked[0].failures}
    assert victim not in {t.sheet_code for t in plan.pending}
    assert exit_code == 2
    assert _both_files_md5(cat, src) == before, f"{form}: 两文件被改动"
    _assert_copy_is_unapplied(cat)


def test_unready_injection_is_not_self_fulfilling(
    tmp_path: Path, unapplied_catalog_seed: Path, adapter_registry_snapshot: dict[str, Any]
) -> None:
    """注入器本身的反向自检：注入 `M4-3` 后，**同前缀族的其余 15 张仍必须全过四门**。

    钉住「一处不就绪 ⇒ 整批哑掉」这类假红，也钉住「注入器其实什么都没改、靠别的原因
    恰好全被挡」这类假绿。
    """
    cat, src, dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)

    with pytest.MonkeyPatch.context() as mp:
        _inject_unready(mp, adapter_registry_snapshot, (("M4-3", "unregistered_prefix", "import-data"),))
        plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)

    assert [p.sheet_code for p in plan.blocked] == ["M4-3"]
    assert len(plan.pending) == 15, f"其余 15 张应仍待补，实得 {len(plan.pending)}"
    # 退出 patch 上下文后必须自愈（monkeypatch 复原有效）
    plan2, _d2, _r2 = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert plan2.blocked == [], "monkeypatch 未复原 ⇒ 后续用例会被污染"
    assert len(plan2.pending) == 16
    assert not dev.exists()


def test_observed_form_coverage_is_recorded() -> None:
    """实录用：把属性测试实际命中的形态分布打出来（不作强断言，避免用例顺序耦合）。"""
    print(f"[Property 5] 形态命中分布 = {_OBSERVED_FORMS}")
    print(f"[Property 5] 三类归并 = {_FORM_CATEGORY}")
    assert set(_OBSERVED_FORMS) == set(_UNREADY_FORMS)
