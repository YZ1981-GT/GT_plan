"""Property 6 —— **核对只读、结论只由生成后目录的现值决定**（spec `x3-adjustment-entry-import-export` 任务 9.3）。

被测对象：`backend/scripts/fix/fix_x3_adjustment_ie_registration.py`（Catalog_Registrar）。

## 改写说明（acnr-foundation-defect-closure T07，design §5.4）

原 Property 6 守的是 `--apply`（就地外科补丁写目录）的「幂等 + 差异集最小」。T07 把目录写入收口到
生成器（`generate_catalog.py --write`，发布门禁通过才写），登记器的目录写入分支已删除，`--check`
改为核对生成后的目录。故本属性改守核对本身：

> ∀ 随机「把 16 段里的任意子集 S（|S| = 0~16）预置成**已收口**态、其余缺段」× 连续跑 N 次（2~4）
> `--check`：①`plan.already` 恰为 S、`plan.pending` 恰为 16 − S（逐个 addr_id 精确对偶）；②退出码
> 恰为「S 是全集 ⇒ 0，否则 2」；③每次都在「一写就炸」探针下跑完（真零字节写入），两文件（catalog 副本
> + `sources_dir` 副本里的 manifest）md5 逐字节不变；④N 次结论相同。

正面对照：|S| = 0 时 pending 恰 16、退出码 2 并点名生成器命令；|S| = 16 时退出码 0。没有这两条，
「pending == 16 − S」在注入器失效（S 恒空或恒满）时也可能成立。

夹具复用任务 8.3 / 9.2 的「未施加态」构造器与「真实面零写」autouse fixture，「一写就炸」探针复用 8.3 的
`_explode_on_write`。

Requirements: 5.2, 5.3, 5.4, 5.5
**Validates: Requirements 5.4**
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Sequence

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.test_x3_ie_registrar import (
    _TARGET_ADDR_IDS,
    _TARGET_SHEET_CODES,
    _explode_on_write,
)
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
    assert {_addr(c) for c in _TARGET_SHEET_CODES} == set(_TARGET_ADDR_IDS)


def _preclose_subset(cat: Path, codes: Sequence[str]) -> set[str]:
    """把 catalog 副本里 `codes` 那批 sheet 的 `import_export` 预置成**已收口**态（值 == Key_Ledger 派生段）。

    落盘后复读自检：预置真的进了磁盘，且只进了被点名那批（防「注入没生效」的假绿）。
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
        assert "import_export" not in sheet, f"注入无效：{addr} 本就已有 import_export"
        sheet["import_export"] = dict(ledger[code])
    cat.write_text(_deterministic_json(data), encoding="utf-8")

    fresh = json.loads(cat.read_text(encoding="utf-8"))
    applied = {
        str(s.get("addr_id") or "")
        for s in fresh.get("sheets", [])
        if str(s.get("addr_id") or "") in _TARGET_ADDR_IDS and "import_export" in s
    }
    assert applied == set(wanted), f"预置后磁盘上的已收口集 {sorted(applied)} != 期望 {sorted(wanted)}"
    return set(wanted)


def _check_under_write_probe(cat: Path, src: Path, *, label: str) -> int:
    """在「一写就炸」探针下跑一次 `--check`：必须跑完且一次写盘都没触发。"""
    with pytest.MonkeyPatch.context() as mp:
        hits = _explode_on_write(mp)
        try:
            code = _REG.run("check", catalog_path=cat, sources_dir=src)
        except AssertionError as exc:
            pytest.fail(f"{label}：--check 触发了写盘 —— {exc}")
    assert hits == [], f"{label}：--check 触发写盘 {hits}"
    return code


@st.composite
def _cases(draw: st.DrawFn) -> tuple[int, tuple[str, ...]]:
    n = draw(st.integers(min_value=_N_MIN, max_value=_N_MAX))
    size = draw(st.integers(min_value=0, max_value=len(_TARGET_SHEET_CODES)))
    order = draw(st.permutations(_TARGET_SHEET_CODES))
    return n, tuple(sorted(order[:size]))


_OBSERVED_SIZES: Counter[int] = Counter()


@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(case=_cases())
def test_property6_check_is_readonly_and_determined_by_catalog(
    tmp_path: Path,
    unapplied_catalog_seed: Path,
    real_face_baseline: dict[str, str],
    case: tuple[int, tuple[str, ...]],
) -> None:
    """**Property 6: 核对只读、结论只由目录现值决定**

    **Validates: Requirements 5.4**
    """
    runs, preclosed_codes = case
    _OBSERVED_SIZES[len(preclosed_codes)] += 1
    cat, src, _dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    _assert_copy_is_unapplied(cat)
    preclosed = _preclose_subset(cat, preclosed_codes)
    remaining = set(_TARGET_ADDR_IDS) - preclosed

    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert plan.refusals == [] and plan.blocked == [], (plan.refusals, [p.reason for p in plan.blocked])
    assert {_addr(c) for c in plan.already} == preclosed
    assert {_addr(t.sheet_code) for t in plan.pending} == remaining
    assert len(plan.targets) == 16

    expected = 0 if not remaining else 2
    before = _both_files_md5(cat, src)
    for i in range(1, runs + 1):
        assert _check_under_write_probe(cat, src, label=f"第 {i}/{runs} 次") == expected
        assert _both_files_md5(cat, src) == before, f"第 {i} 次 --check 改了两文件"
    assert _real_face_md5s() == real_face_baseline, "本 example 写到了真实文件"


def test_positive_control_empty_preset_names_16_missing_segments(
    tmp_path: Path, unapplied_catalog_seed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 反空转：零预置 ⇒ pending 恰 16、退出码 2，输出点名缺段数与生成器命令。"""
    cat, src, _dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    _assert_copy_is_unapplied(cat)
    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert plan.already == [] and len(plan.pending) == 16
    capsys.readouterr()
    assert _check_under_write_probe(cat, src, label="零预置") == 2
    out = capsys.readouterr().out
    assert "目录缺 16 张的 import_export 段" in out, out
    assert "generate_catalog.py --write" in out, out


def test_full_preset_closes(tmp_path: Path, unapplied_catalog_seed: Path) -> None:
    """满预置（S = 16）⇒ 退出码 0，与生成后的 committed 目录同态。"""
    cat, src, _dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    _assert_copy_is_unapplied(cat)
    assert _preclose_subset(cat, _TARGET_SHEET_CODES) == set(_TARGET_ADDR_IDS)
    assert _check_under_write_probe(cat, src, label="满预置") == 0


@pytest.mark.parametrize("size", [1, 8, 15])
def test_fixed_subset_pending_is_exactly_the_remaining(tmp_path: Path, unapplied_catalog_seed: Path, size: int) -> None:
    """定点子集实测（不依赖 hypothesis 抽样命中）：pending 恰为 16 − size，退出码 2。"""
    cat, src, _dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    preclosed = _preclose_subset(cat, _TARGET_SHEET_CODES[:size])
    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert {_addr(t.sheet_code) for t in plan.pending} == set(_TARGET_ADDR_IDS) - preclosed
    assert len(plan.pending) == 16 - size
    assert _check_under_write_probe(cat, src, label=f"size={size}") == 2


def test_preclose_with_wrong_value_is_refused(tmp_path: Path, unapplied_catalog_seed: Path) -> None:
    """目录里是**错值** ⇒ 判结构性拒绝（不认作已收口）、退出码 2 且零写盘。"""
    from generate_catalog import _deterministic_json  # noqa: PLC0415

    cat, src, _dev = _fresh_case_dir(unapplied_catalog_seed, tmp_path)
    data = json.loads(cat.read_text(encoding="utf-8"))
    for sheet in data.get("sheets", []):
        if str(sheet.get("addr_id") or "") == _addr("M4-3"):
            sheet["import_export"] = {"enabled": True, "api_prefix": "m4-TAMPERED"}
            break
    cat.write_text(_deterministic_json(data), encoding="utf-8")
    plan, _data, _raw = _REG.build_plan(catalog_path=cat, sources_dir=src)
    assert any("拒绝覆盖" in r for r in plan.refusals), plan.refusals
    assert "M4-3" not in plan.already
    assert _check_under_write_probe(cat, src, label="错值") == 2


def test_observed_subset_coverage_is_recorded() -> None:
    print(f"[Property 6] 预置子集大小分布 = {dict(sorted(_OBSERVED_SIZES.items()))}")
    assert all(0 <= k <= 16 for k in _OBSERVED_SIZES)
