"""Property 6 —— **登记幂等且差异集最小**（spec `x3-adjustment-entry-import-export` 任务 9.3）。

被测对象：`backend/scripts/fix/fix_x3_adjustment_ie_registration.py`（Catalog_Registrar，禁改）。

## 属性表述（Property 6，两个面）

> **面 1（幂等）**：从「未施加」态起连续跑 **N 次**（N 随机 2~4）`--apply` ⇒ 第 1 次后
> catalog 逐字节**变化**（有待补项时），**第 2 次起**两文件（catalog 副本 + `sources_dir`
> 副本里的 manifest）md5 **逐字节不变**；且第 ≥2 次在「一写就炸」探针（`Path.write_text`
> / `Path.write_bytes` 换成必抛）下**仍能跑完** ⇒ 是**真零字节写入**，不是「又写了一遍
> 同样的内容」。
>
> **面 2（差异集最小）**：∀ 随机「先手工把 16 段里的任意子集 S（|S| = 0~16）预置成
> **已收口**态」⇒ `--apply` 的结构化差异集**恰等于** `16 - S`（不多改一个 `addr_id`、
> 不重写已收口那批），每处被改键恰 `['import_export']`，已启用 I/E 集合**只增不减**。

## 🔴 md5 面单独不够，必须配「一写就炸」探针

登记器的写盘走生成器的**确定性序列化** ⇒ 若幂等早退失效、把同样的内容又写一遍，
**md5 完全不变**，"逐字节不变"这条判据会**判绿**。本文件因此把两条判据并列：md5 面
（内容不变）+ 探针面（**一个字节都没写**）。变异 MUT-A 实测正是这个形态：md5 面 GREEN、
探针面 RED —— 这就是探针不可省的实证。

## 🔴 为什么必须自己造「未施加」态（反空转）

任务 9.1 已施加 —— committed `global_catalog.json` 里 16 段 `import_export` **已在**，
`--check` 现返 **0**。拿仓库当刻状态当输入 ⇒ `plan.pending` 恒为空集、第 1 次 `--apply`
就走幂等早退，「第 2 次起不变」与「差异集最小」双双退化成恒真（空转）。

故本文件**复用**任务 8.3 守卫的 `_catalog_copy_unapplied()`（`tests.test_x3_ie_registrar`）
把副本推回「未施加」态 —— 不抄第二份剥段逻辑；该 helper 自带三条反向自检（16 个 addr_id
必须一条一命中 / 剥完必全无 `import_export` / 实剥段数只许 0 或 16，半施加态当场抛）。
夹具与「真实面零写」autouse fixture 复用任务 9.2 的 `test_x3_registrar_preflight_property`
（`_fresh_case_dir` / `_both_files_md5` / `_assert_copy_is_unapplied` / `unapplied_catalog_seed`），
「一写就炸」探针复用 8.3 的 `_explode_on_write`。

## 正面对照（反空转的另一半）

`|S| = 0` 时第 1 次 `--apply` **必须真写 16 段**（md5 变、差异集恰 16、值逐字段 ==
Key_Ledger 派生值）。没有这条，「差异集恰等于 16 - S」在 S 恒等于全集时也成立，属恒真。

## 真实面零写

复用 9.2 的 autouse fixture：**每条用例前后**复量真实写盘面（committed catalog + 三份真实
manifest + Deviation 侧车正路径）的 md5；属性测试**每条 example 内**再复量一次。所有写盘
（catalog 副本 / manifest 副本 / Deviation 侧车）全落 `tmp_path`。
🔴 刻意**不**写死 committed catalog 的 md5 字面量 —— 9.1 已施加、后续仍可能合法变化，
锁字面量等于把当刻状态当"正确基线"（R8.6 禁止）；这里只比「本次会话内没被改动」。

Requirements: 5.2, 5.3, 5.4, 5.5
**Validates: Requirements 5.4**
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# 🔴 复用任务 8.3 守卫的「未施加态」构造器、目标集与「一写就炸」探针，禁在本文件另造一份。
from tests.test_x3_ie_registrar import (
    _TARGET_ADDR_IDS,
    _TARGET_SHEET_CODES,
    _explode_on_write,
)

# 🔴 复用任务 9.2 的夹具与不变量 helper（含 autouse 的「真实面零写」）。
from tests.test_x3_registrar_preflight_property import (  # noqa: F401 —— fixture 按名注入
    _REG,
    _assert_copy_is_unapplied,
    _both_files_md5,
    _fresh_case_dir,
    _real_face_is_never_written,
    _real_face_md5s,
    real_face_baseline,
    unapplied_catalog_seed,
)

_N_MIN, _N_MAX = 2, 4


def _addr(code: str) -> str:
    """`sheet_code` → `addr_id`（口径与 8.3 的 `_TARGET_ADDR_IDS` 同源，见下方自检）。"""
    return f"{code.split('-')[0]}/{code}"


def test_addr_id_derivation_matches_the_8_3_target_set() -> None:
    """本文件的 `_addr()` 口径必须与 8.3 的目标集逐条一致（否则下游集合断言会错位）。"""
    assert {_addr(c) for c in _TARGET_SHEET_CODES} == set(_TARGET_ADDR_IDS)


# ═══════════════════════════════════════════════════════════════════════════════
# 「预置成已收口」注入器（面 2 的输入）
# ═══════════════════════════════════════════════════════════════════════════════


def _preclose_subset(cat: Path, codes: Sequence[str]) -> set[str]:
    """把 catalog 副本里 `codes` 那批 sheet 的 `import_export` 预置成**已收口**态。

    值必须**逐字段等于** Key_Ledger 派生段 —— 写别的值会被登记器判「已有值且与目标段
    不同 ⇒ 拒绝覆盖」（`test_preclose_with_wrong_value_is_refused` 正向钉住这条），
    那样 `--apply` 会以 2 退出、面 2 的判据形态整体改变。

    写回走生成器自己的 `_deterministic_json` ⇒ 副本仍满足登记器的 round-trip 自检
    （R5.5），不会因为"我自己 `json.dumps` 拼的格式"把 `--apply` 挡在 round-trip 门外。

    返回被预置的 `addr_id` 集合，并做三条**注入有效性自检**（防「注入其实没生效、
    差异集最小恒真」这类假绿）。
    """
    from generate_catalog import _deterministic_json  # noqa: PLC0415

    ledger = _REG._ledger_x3()
    data = json.loads(cat.read_text(encoding="utf-8"))
    by_addr = {str(s.get("addr_id") or ""): s for s in data.get("sheets", [])}

    wanted = {_addr(c): c for c in codes}
    assert len(wanted) == len(list(codes)), f"预置集有重复：{list(codes)}"
    for addr, code in wanted.items():
        sheet = by_addr.get(addr)
        assert sheet is not None, f"副本里没有 {addr} —— catalog 结构变了"
        assert "import_export" not in sheet, (
            f"注入无效：{addr} 本就已有 import_export ⇒ 副本不是「未施加」态"
        )
        assert code in ledger, f"{code} 不在 Key_Ledger ⇒ 无法派生已收口值"
        sheet["import_export"] = dict(ledger[code])

    cat.write_text(_deterministic_json(data), encoding="utf-8")

    # 落盘后复读自检：预置真的进了磁盘，且**只**进了被点名那批
    fresh = json.loads(cat.read_text(encoding="utf-8"))
    applied = {
        str(s.get("addr_id") or "")
        for s in fresh.get("sheets", [])
        if str(s.get("addr_id") or "") in _TARGET_ADDR_IDS and "import_export" in s
    }
    assert applied == set(wanted), (
        f"预置后磁盘上的已收口集 {sorted(applied)} != 期望 {sorted(wanted)}"
    )
    return set(wanted)


def _target_segments(cat: Path) -> dict[str, Any]:
    """磁盘上 16 个目标条目的 `import_export` 现值（缺段用 `None` 表达）。"""
    data = json.loads(cat.read_text(encoding="utf-8"))
    return {
        str(s.get("addr_id") or ""): s.get("import_export")
        for s in data.get("sheets", [])
        if str(s.get("addr_id") or "") in _TARGET_ADDR_IDS
    }


def _assert_segments_are_ledger_derived(cat: Path) -> None:
    """16 段全部在位且逐字段 == Key_Ledger 派生值（R5.3）。"""
    ledger = _REG._ledger_x3()
    segs = _target_segments(cat)
    assert set(segs) == set(_TARGET_ADDR_IDS), f"目标条目缺失：{sorted(segs)}"
    for addr, got in segs.items():
        code = addr.split("/")[1]
        assert got == ledger[code], f"{addr} 的段非 Key_Ledger 派生值：{got!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# 幂等的「真零字节」探测（md5 面 + 探针面并列）
# ═══════════════════════════════════════════════════════════════════════════════


def _apply_under_write_probe(cat: Path, src: Path, dev: Path, *, label: str) -> int:
    """在「一写就炸」探针下跑一次 `--apply`：必须跑完且一次写盘都没触发。

    🔴 这条判据与「md5 不变」**不等价**：登记器写的是确定性序列化结果，重写一遍同样的
    内容 md5 一模一样 ⇒ 只看 md5 会把「每次重写」判绿（变异 MUT-A 实测如此）。
    """
    with pytest.MonkeyPatch.context() as mp:
        hits = _explode_on_write(mp)
        try:
            code = _REG.run("apply", catalog_path=cat, sources_dir=src, deviation_path=dev)
        except AssertionError as exc:  # 探针抛出 ⇒ 非零字节写入
            pytest.fail(f"{label}：--apply 触发了写盘（不是真零字节写入）—— {exc}")
    assert hits == [], f"{label}：幂等分支仍触发写盘 {hits}"
    return code


# ═══════════════════════════════════════════════════════════════════════════════
# Property 6（面 1 + 面 2 同一条属性里串起来）
# ═══════════════════════════════════════════════════════════════════════════════


@st.composite
def _idempotence_cases(draw: st.DrawFn) -> tuple[int, tuple[str, ...]]:
    """随机「连续跑几次 `--apply`」× 「先预置成已收口的子集」。

    子集用「先抽大小、再取随机排列的前 size 个」而不是 `st.lists(..., unique=True)` ——
    后者在 size 接近 16 时会因去重过滤产出大量 invalid example，且几乎抽不到满集。
    """
    n = draw(st.integers(min_value=_N_MIN, max_value=_N_MAX))
    size = draw(st.integers(min_value=0, max_value=len(_TARGET_SHEET_CODES)))
    order = draw(st.permutations(_TARGET_SHEET_CODES))
    return n, tuple(sorted(order[:size]))


#: 实录用：抽样实际覆盖到的 (子集大小, N) 分布（不作断言依赖，避免用例间顺序耦合）。
_OBSERVED_SIZES: Counter[int] = Counter()
_OBSERVED_N: Counter[int] = Counter()


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
    ],
)
@given(case=_idempotence_cases())
def test_property6_registration_is_idempotent_and_diff_is_minimal(
    tmp_path: Path,
    unapplied_catalog_seed: Path,
    real_face_baseline: dict[str, str],
    case: tuple[int, tuple[str, ...]],
) -> None:
    """**Property 6: 登记幂等且差异集最小**

    面 1：第 1 次写、第 2~N 次零字节（md5 面 + 探针面并列）。
    面 2：差异集恰等于「16 - 预置子集」，每处只改 `import_export`，已启用集只增不减。

    **Validates: Requirements 5.4**
    """
    runs, preclosed_codes = case
    _OBSERVED_SIZES[len(preclosed_codes)] += 1
    _OBSERVED_N[runs] += 1

    cat, src, dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    dev.unlink(missing_ok=True)
    _assert_copy_is_unapplied(cat)  # 结构前提：剥段 helper 没失效（否则整条退化为空转）

    preclosed = _preclose_subset(cat, preclosed_codes)
    remaining = set(_TARGET_ADDR_IDS) - preclosed

    before = json.loads(cat.read_text(encoding="utf-8"))
    before_md5 = _both_files_md5(cat, src)
    enabled_before = _REG._enabled_addr_ids(before)
    assert preclosed <= enabled_before, "预置的那批没进已启用集 ⇒ 注入没生效"
    assert enabled_before.isdisjoint(remaining), "未预置的那批却已是启用态 ⇒ 剥段失效"

    # ── 台账侧：already / pending 与预置集**精确对偶**（不是「差不多」）
    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert plan.refusals == [], f"预置态被判结构性拒绝：{plan.refusals}"
    assert plan.blocked == [], f"预置态有 sheet 被 Preflight 挡：{[p.reason for p in plan.blocked]}"
    assert {_addr(c) for c in plan.already} == preclosed, (
        f"plan.already {sorted(_addr(c) for c in plan.already)} != 预置集 {sorted(preclosed)}"
    )
    assert {_addr(t.sheet_code) for t in plan.pending} == remaining, (
        f"plan.pending {sorted(_addr(t.sheet_code) for t in plan.pending)} != 剩余集"
        f" {sorted(remaining)}"
    )
    assert len(plan.targets) == 16, f"作业面 {len(plan.targets)} 张 != 16"

    # ── 第 1 次 --apply
    assert _REG.run("apply", catalog_path=cat, sources_dir=src, deviation_path=dev) == 0
    after = json.loads(cat.read_text(encoding="utf-8"))
    first_md5 = _both_files_md5(cat, src)

    # 面 2①：结构化差异集**恰等于**剩余未收口那批
    diff = _REG._structural_diff(before, after)
    assert set(diff) == remaining, (
        f"差异集 {sorted(diff)} != 剩余未收口集 {sorted(remaining)}"
        f"（预置 {len(preclosed)} 个 ⇒ 期望恰改 {len(remaining)} 个）"
    )
    # 面 2②：每处被改键恰 ['import_export']
    assert all(keys == ["import_export"] for keys in diff.values()), diff
    # 面 2③：已收口那批**逐字段未被重写**
    seg_before = {
        str(s.get("addr_id") or ""): s.get("import_export") for s in before.get("sheets", [])
    }
    seg_after = {
        str(s.get("addr_id") or ""): s.get("import_export") for s in after.get("sheets", [])
    }
    for addr in sorted(preclosed):
        assert seg_after[addr] == seg_before[addr], f"{addr} 已收口却被重写"
    # 面 2④：已启用 I/E 集合只增不减，且新增的恰是剩余集
    enabled_after = _REG._enabled_addr_ids(after)
    assert not (enabled_before - enabled_after), (
        f"{len(enabled_before - enabled_after)} 条已启用 I/E 掉出集合"
        f"（如 {sorted(enabled_before - enabled_after)[:5]}）"
    )
    assert enabled_after - enabled_before == remaining
    _assert_segments_are_ledger_derived(cat)

    # 面 1①：第 1 次的写盘形态（有待补 ⇒ 真写；满预置 ⇒ 第 1 次就零写）
    if remaining:
        assert first_md5[cat.name] != before_md5[cat.name], (
            f"有 {len(remaining)} 张待补，第 1 次 --apply 却一个字节都没写 ⇒ 后续幂等断言空转"
        )
    else:
        assert first_md5 == before_md5, "满预置（S=16）时第 1 次 --apply 就不该写任何字节"
    assert {k: v for k, v in first_md5.items() if k != cat.name} == {
        k: v for k, v in before_md5.items() if k != cat.name
    }, "manifest 副本不该被 --apply 改动"

    # 面 1②：第 2~N 次 —— md5 逐字节不变 **且** 探针下零字节写入
    segs_first = _target_segments(cat)
    for i in range(2, runs + 1):
        assert _apply_under_write_probe(cat, src, dev, label=f"第 {i}/{runs} 次 --apply") == 0
        assert _both_files_md5(cat, src) == first_md5, f"第 {i} 次 --apply 改了两文件（非幂等）"
        assert _target_segments(cat) == segs_first, f"第 {i} 次 --apply 动了 16 段的值"

    assert not dev.exists(), "全 16 张均过 Preflight ⇒ 不该写 Deviation 侧车"
    assert _real_face_md5s() == real_face_baseline, "本 example 写到了真实文件"


# ═══════════════════════════════════════════════════════════════════════════════
# 正面对照（反空转）+ 定点子集实测
# ═══════════════════════════════════════════════════════════════════════════════


def test_positive_control_empty_preset_really_writes_16_segments(
    tmp_path: Path, unapplied_catalog_seed: Path
) -> None:
    """🔴 反空转：**预置子集为空**时第 1 次 `--apply` 必须真写 16 段。

    没有这条，「差异集恰等于 16 - S」在 S 恒为全集（例如注入器把整批都预置了、或剥段
    helper 失效导致 pending 恒空）时也成立 ⇒ 面 2 退化为恒真。
    """
    cat, src, dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    _assert_copy_is_unapplied(cat)

    before = json.loads(cat.read_text(encoding="utf-8"))
    before_md5 = _both_files_md5(cat, src)
    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert plan.already == [], f"零预置却有已收口项：{plan.already}"
    assert len(plan.pending) == 16, f"零预置时 pending {len(plan.pending)} != 16"

    assert _REG.run("apply", catalog_path=cat, sources_dir=src, deviation_path=dev) == 0
    after = json.loads(cat.read_text(encoding="utf-8"))

    assert _both_files_md5(cat, src)[cat.name] != before_md5[cat.name], (
        "零预置时 --apply 一个字节都没写 ⇒ Property 6 的两个面都是空转"
    )
    diff = _REG._structural_diff(before, after)
    assert set(diff) == set(_TARGET_ADDR_IDS), f"差异集 {sorted(diff)}"
    assert all(keys == ["import_export"] for keys in diff.values()), diff
    assert _REG._enabled_addr_ids(after) - _REG._enabled_addr_ids(before) == set(_TARGET_ADDR_IDS)
    _assert_segments_are_ledger_derived(cat)
    assert not dev.exists()


def test_full_preset_makes_the_first_apply_a_true_zero_write(
    tmp_path: Path, unapplied_catalog_seed: Path
) -> None:
    """满预置（S = 16）⇒ **第 1 次** `--apply` 就走幂等早退：探针下跑完、两文件不变。"""
    cat, src, dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    _assert_copy_is_unapplied(cat)
    preclosed = _preclose_subset(cat, _TARGET_SHEET_CODES)
    assert preclosed == set(_TARGET_ADDR_IDS)

    before_md5 = _both_files_md5(cat, src)
    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert len(plan.already) == 16 and plan.pending == []

    assert _apply_under_write_probe(cat, src, dev, label="满预置第 1 次 --apply") == 0
    assert _both_files_md5(cat, src) == before_md5
    assert _REG.run("check", catalog_path=cat, sources_dir=src) == 0, "满预置副本应判已收口"


@pytest.mark.parametrize("size", [1, 8, 15])
def test_fixed_subset_diff_is_exactly_the_remaining(
    tmp_path: Path, unapplied_catalog_seed: Path, size: int
) -> None:
    """定点子集实测（不依赖 hypothesis 抽样命中）：差异集恰 `16 - size` 且只改 `import_export`。"""
    cat, src, dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    _assert_copy_is_unapplied(cat)
    preclosed = _preclose_subset(cat, _TARGET_SHEET_CODES[:size])
    remaining = set(_TARGET_ADDR_IDS) - preclosed

    before = json.loads(cat.read_text(encoding="utf-8"))
    assert _REG.run("apply", catalog_path=cat, sources_dir=src, deviation_path=dev) == 0
    after = json.loads(cat.read_text(encoding="utf-8"))

    diff = _REG._structural_diff(before, after)
    assert set(diff) == remaining, f"size={size}: 差异集 {sorted(diff)} != {sorted(remaining)}"
    assert len(diff) == 16 - size
    assert all(keys == ["import_export"] for keys in diff.values()), diff
    _assert_segments_are_ledger_derived(cat)
    # 二次 apply 真零字节
    md5_after = _both_files_md5(cat, src)
    assert _apply_under_write_probe(cat, src, dev, label=f"size={size} 二次 --apply") == 0
    assert _both_files_md5(cat, src) == md5_after


def test_preclose_injection_is_not_self_fulfilling(
    tmp_path: Path, unapplied_catalog_seed: Path
) -> None:
    """注入器反向自检：预置 1 张 ⇒ 其余 **15 张仍待补**，且那 1 张进 `already` 而非 `pending`。

    钉住「注入其实什么都没改（差异集恒 16）」与「注入把整批都预置了（差异集恒空）」两侧假绿。
    """
    cat, src, _dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    victim = "M4-3"
    preclosed = _preclose_subset(cat, (victim,))
    assert preclosed == {_addr(victim)}

    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert plan.already == [victim], f"预置的那张没进 already：{plan.already}"
    assert len(plan.pending) == 15, f"其余 15 张应仍待补，实得 {len(plan.pending)}"
    assert victim not in {t.sheet_code for t in plan.pending}


def test_preclose_with_wrong_value_is_refused(
    tmp_path: Path, unapplied_catalog_seed: Path
) -> None:
    """预置**错值** ⇒ 登记器拒绝覆盖（exit 2）且零写盘。

    这条既钉住 R5.2「不覆盖已有异值」，也反证 `_preclose_subset` 写的是**真收口值**：
    若它写的值与 Key_Ledger 不等，属性测试里的 `--apply` 会以 2 退出、`already` 也不会
    含它 ⇒ 面 2 的判据形态整体改变而不是静默放过。
    """
    from generate_catalog import _deterministic_json  # noqa: PLC0415

    cat, src, dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    data = json.loads(cat.read_text(encoding="utf-8"))
    for sheet in data.get("sheets", []):
        if str(sheet.get("addr_id") or "") == _addr("M4-3"):
            sheet["import_export"] = {"enabled": True, "api_prefix": "m4-TAMPERED"}
            break
    cat.write_text(_deterministic_json(data), encoding="utf-8")

    before_md5 = _both_files_md5(cat, src)
    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert any("拒绝覆盖" in r for r in plan.refusals), plan.refusals
    assert _REG.run("apply", catalog_path=cat, sources_dir=src, deviation_path=dev) == 2
    assert _both_files_md5(cat, src) == before_md5, "被拒绝的 --apply 仍改了文件"


def test_observed_subset_and_run_count_coverage_is_recorded() -> None:
    """实录用：把属性测试实际抽到的「子集大小 / N」分布打出来（不作强断言）。"""
    print(f"[Property 6] 预置子集大小分布 = {dict(sorted(_OBSERVED_SIZES.items()))}")
    print(f"[Property 6] N（连续 --apply 次数）分布 = {dict(sorted(_OBSERVED_N.items()))}")
    assert set(_OBSERVED_N) <= set(range(_N_MIN, _N_MAX + 1))
