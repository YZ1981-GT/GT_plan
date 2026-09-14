"""GS-P —— `check_ie_catalog_sync` 「部分登记循环」模式守卫

spec: `x3-adjustment-entry-import-export` · Wave 5 任务 8.2
_Requirements: 5.2, 8.6, 11.3_

## 判据为什么不能落在「源码里有 `_PARTIAL_CYCLES` 这个名字」

任务 8.2 的交付物是一个**行为差异**：同一种输入形态（catalog 有已启用 I/E 而
manifest 未登记该 sheet），在全量登记循环里判 error（Step 4），在部分登记循环里
只计数、不判 error（跳过 Step 4）。「常量名存在」「字符串出现」这类判据命中
memory 记的假绿第②类 —— 把 `continue` 改成 `pass`、把跳过条件反过来、把
`_COMPARE_FIELDS` 删掉几项，全都照绿。

⇒ 本文件全部判据落**可观察输出 / 退出码 / 真实被比对的字段集**：

- `test_step4_fires_for_full_cycle_and_is_skipped_for_partial_cycle`
  —— **同形输入 + 两组循环**的差分：full 组 exit=1 且报「未登记」；partial 组
  exit=0 且**一条 error 都没有**。差分本身就是「Step 4 被跳过」的证据，与常量
  叫什么名字无关。
- `test_partial_cycle_still_compares_every_field_in_step3`
  —— 参数化跑遍**从模块现读的** `_COMPARE_FIELDS`（不内联字段名），逐个在
  catalog 侧扰动一格，每一格都必须被判红。字段集被削弱 ⇒ 对应参数变绿 ⇒ 红。
- `test_partial_uncovered_count_*` 三条
  —— 未覆盖条目数落在 **stdout 的可读行**上（`未被 manifest 覆盖 N 条（基线 M）`），
  且 N > M 判红、N < M 要求把基线同步下调。
- `test_cycle_in_both_groups_is_config_contradiction`
  —— 「把 L/M/N 误加进 `_SUPPORTED_CYCLES`」这条变异的接住点：两组重叠时脚本
  必须立刻打红（否则重叠时哪一支胜出都会让另一支判据静默失效）。
- `test_real_*` 四条 —— 在**真实 catalog / manifest** 上复算，钉住三件事：
  ①L/M/N 在 error 里**零条目**（Step 4 真的没跑）②未覆盖条目数 = 测试独立复算
  值 = 脚本自报值 = 脚本基线（三向一致，防「基线被上调放水」）③红的规模不变大
  且成分仍只有 D/G/H（裁决 2：本任务不修绿，只保证不变大）。

## 未覆盖启用条目数的口径（可复算）

    catalog.sheets 中 cycle == C 且 import_export.enabled 为真的 sheet_code 集合
      减去
    C 的 manifest entries 的 sheet_code 集合
      取势

实测（2026-08-15，committed catalog）：L 8 · M 0 · N 2，合计 **10**
（`L1-2 L1-3 L3-2 L3-3 L4-2 L4-3 L5-2 L5-3` + `N4-2 N4-3`）。

**为什么只许下调**：这个数字是别的 spec 半径内的**待消化存量欠账**，不是目标值。
变大 = 又有人往 catalog 塞未登记的启用条目（回归）；变小 = 欠账被消化，必须把
脚本里的基线同步下调，否则守卫会拿一个过时的宽松上限继续放行（基线自我失效）。
把这 10 条抄进 manifest 才是真正被禁的动作 —— 那等于把未经核验的值写进真源
（R8.6「基线断言只收录已确证正确的值」）。

## 本文件不负责修绿（裁决 2）

`acnr-ie-catalog-sync` 当前 exit=1 / 19 条不一致（D 1 · G 14 · H 4），radius 在
d/g manifest 与 H 循环，属别的 active spec。本文件只钉「红的规模不变大、成分不
变脏」，用 `<=` 而不是 `==` —— 别的 spec 把 d/g 修绿时不许在这里假红。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

# ─── 路径与被测模块 ───────────────────────────────────────────────────────────

_TESTS_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TESTS_DIR.parent
_SCRIPT_PATH = _BACKEND_ROOT / "scripts" / "acnr" / "check_ie_catalog_sync.py"
_REAL_CATALOG = _BACKEND_ROOT / "data" / "acnr" / "global_catalog.json"
_REAL_SOURCES = _BACKEND_ROOT / "data" / "acnr" / "sources"


def _load_script() -> Any:
    """把 CI 脚本作为模块载入（脚本无 package，只能按路径载）。"""
    assert _SCRIPT_PATH.exists(), f"被测脚本不存在：{_SCRIPT_PATH}"
    spec = importlib.util.spec_from_file_location(
        "_x3_check_ie_catalog_sync_under_test", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MOD = _load_script()

#: 本 spec 作业面所在的三个部分登记循环
_X3_CYCLES: tuple[str, ...] = ("L", "M", "N")

#: 存量孤儿锚点 —— 只用于「不许新增」的子集判定，不作为「正确值」断言（R8.6）。
#: 这 10 条是实测的欠账清单（属别的 spec 半径），只许缩小。
_KNOWN_ORPHANS: frozenset[str] = frozenset({
    "L1-2", "L1-3", "L3-2", "L3-3", "L4-2", "L4-3", "L5-2", "L5-3",
    "N4-2", "N4-3",
})

#: 裁决 2 的红规模基线（D 1 · G 14 · H 4）—— 只许下调，成分只许是 D/G/H
_RED_SCALE_BASELINE = 19
_RED_SCALE_CYCLES: frozenset[str] = frozenset({"D", "G", "H"})

#: Step 3 必须逐字段比对的字段集 —— **由本文件持有**，不是从脚本现读。
#: 从脚本现读会让「删掉一个字段」这条变异变成参数少一个 ⇒ 静默变绿（GREEN）。
#: 与脚本侧 `_COMPARE_FIELDS` 由 `test_step3_compared_field_set_is_locked_both_ways`
#: 双向锁死：脚本删字段 ⇒ 对应参数的扰动不再被判红；脚本加字段 ⇒ 锚点条打红，
#: 迫使本文件同步补扰动值（新字段不会静默逃出行为判据）。
_MUST_COMPARE: tuple[str, ...] = (
    "api_prefix",
    "item_id",
    "storage_field",
    "import_order",
    "depends_on_sheets",
)

#: 每字段扰动用的异型值（类型与原字段一致，避免 normalize 把差异吃掉）
_PERTURBED: dict[str, Any] = {
    "api_prefix": "zz-perturbed",
    "item_id": "ZZ-9-perturbed",
    "storage_field": "perturbed_field",
    "import_order": 999,
    "depends_on_sheets": ["ZZ-9"],
}


# ─── 夹具构造 ─────────────────────────────────────────────────────────────────


def _ie(code: str, **over: Any) -> dict[str, Any]:
    """一条启用的 import_export 段（manifest 与 catalog 共用同一形状）。"""
    seg = {
        "enabled": True,
        "api_prefix": code.split("-")[0].lower(),
        "item_id": f"{code}-entries",
        "storage_field": "remark",
        "import_order": 20,
        "depends_on_sheets": [],
    }
    seg.update(over)
    return seg


def _manifest_entry(code: str, **over: Any) -> dict[str, Any]:
    entry = {k: v for k, v in _ie(code).items() if k != "enabled"}
    entry["sheet_code"] = code
    entry.update(over)
    return entry


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    *,
    full_cycles: list[str],
    partial_cycles: list[str],
    baseline: dict[str, int],
    catalog: list[tuple[str, str, dict[str, Any] | None]],
    manifests: dict[str, list[dict[str, Any]]],
) -> tuple[int, str, str]:
    """在受控夹具上真跑 `main()`，返回 (exit_code, stdout, stderr)。"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    cat_path = tmp_path / "global_catalog.json"
    cat_path.write_text(
        json.dumps(
            {
                "sheets": [
                    {"cycle": cyc, "sheet_code": code, "import_export": ie}
                    for cyc, code, ie in catalog
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    src_dir = tmp_path / "sources"
    src_dir.mkdir(exist_ok=True)
    for cyc in [*full_cycles, *partial_cycles]:
        (src_dir / f"{cyc.lower()}_cycle_ie_manifest.yaml").write_text(
            yaml.safe_dump(
                {"entries": manifests.get(cyc, [])}, allow_unicode=True, sort_keys=False
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(_MOD, "_CATALOG_PATH", cat_path)
    monkeypatch.setattr(_MOD, "_MANIFEST_DIR", src_dir)
    monkeypatch.setattr(_MOD, "_SUPPORTED_CYCLES", list(full_cycles))
    monkeypatch.setattr(_MOD, "_PARTIAL_CYCLES", list(partial_cycles))
    monkeypatch.setattr(_MOD, "_PARTIAL_UNCOVERED_BASELINE", dict(baseline))

    capsys.readouterr()  # 清掉此前的捕获
    code = _MOD.main()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _marker_lines(stderr: str) -> list[str]:
    """脚本判定出的不一致条目 —— 与下游同口径（以 ✗ 起头的行）。"""
    return [ln.strip() for ln in stderr.splitlines() if ln.strip().startswith("✗")]


def _declared_count(stderr: str) -> int | None:
    hit = re.search(r"发现\s*(\d+)\s*处不一致", stderr)
    return int(hit.group(1)) if hit else None


def _reported_uncovered(stdout: str) -> dict[str, tuple[int, int]]:
    """从 stdout 解析每个部分登记循环自报的 (未覆盖数, 基线)。"""
    out: dict[str, tuple[int, int]] = {}
    pattern = re.compile(
        r"\[([A-Z][A-Z0-9]*)\].*?未被 manifest 覆盖\s*(\d+)\s*条（基线\s*(\d+)）"
    )
    for line in stdout.splitlines():
        hit = pattern.search(line)
        if hit:
            out[hit.group(1)] = (int(hit.group(2)), int(hit.group(3)))
    return out


# ─── 真实数据侧的独立复算（不读脚本的任何常量）─────────────────────────────────


def _measure_real_uncovered() -> dict[str, dict[str, Any]]:
    """按口径从真实 catalog + manifest 复算未覆盖启用条目。"""
    catalog = json.loads(_REAL_CATALOG.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for cyc in _X3_CYCLES:
        enabled = {
            sheet.get("sheet_code", "")
            for sheet in catalog.get("sheets", [])
            if sheet.get("cycle") == cyc
            and (sheet.get("import_export") or {}).get("enabled")
        }
        manifest = yaml.safe_load(
            (_REAL_SOURCES / f"{cyc.lower()}_cycle_ie_manifest.yaml").read_text(
                encoding="utf-8"
            )
        )
        registered = {
            entry.get("sheet_code") for entry in (manifest.get("entries") or [])
        }
        out[cyc] = {
            "enabled": sorted(enabled),
            "registered": sorted(registered),
            "uncovered": sorted(enabled - registered),
        }
    return out


def _run_real(capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    capsys.readouterr()
    code = _MOD.main()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ─── 1. 机制差分：Step 4 只对全量登记循环生效 ─────────────────────────────────


def test_step4_fires_for_full_cycle_and_is_skipped_for_partial_cycle(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """同形输入（catalog 启用、manifest 未登记）在两组循环里的判定必须相反。

    这是「部分登记模式真的跳过了 Step 4」的核心判据 —— 输入形态逐字段相同，
    唯一差别是该循环落在哪一组，故差分只能由 Step 4 的跑/不跑造成。
    """
    shape: list[tuple[str, str, dict[str, Any] | None]] = [
        ("D", "D9-9", _ie("D9-9")),  # 全量登记循环里的同形孤儿
        ("L", "L9-9", _ie("L9-9")),  # 部分登记循环里的同形孤儿
    ]

    # --- full 组：Step 4 判 error ---
    code_full, _, err_full = _run(
        monkeypatch,
        capsys,
        tmp_path / "full",
        full_cycles=["D"],
        partial_cycles=[],
        baseline={},
        catalog=[shape[0]],
        manifests={"D": []},
    )
    assert code_full == 1, "全量登记循环的未登记孤儿必须判红（Step 4 应当跑）"
    assert any("D9-9" in m and "未登记" in m for m in _marker_lines(err_full)), (
        f"Step 4 未报出 D9-9：{_marker_lines(err_full)}"
    )

    # --- partial 组：同形输入零 error ---
    code_partial, out_partial, err_partial = _run(
        monkeypatch,
        capsys,
        tmp_path / "partial",
        full_cycles=[],
        partial_cycles=["L"],
        baseline={"L": 1},
        catalog=[shape[1]],
        manifests={"L": []},
    )
    assert _marker_lines(err_partial) == [], (
        f"部分登记循环不该产生任何不一致条目，实得：{_marker_lines(err_partial)}"
    )
    assert code_partial == 0, f"部分登记循环应当放行，stderr={err_partial!r}"
    assert _reported_uncovered(out_partial) == {"L": (1, 1)}, (
        f"未覆盖条目数没有被计数汇报：{out_partial!r}"
    )


# ─── 2. Step 3 仍逐字段跑（字段集不许被削弱）───────────────────────────────────


def test_step3_compared_field_set_is_locked_both_ways() -> None:
    """脚本的比对字段集必须与本文件的必比集**逐项相等**（双向锁死）。

    只有这条加上下面的参数化行为条，才能同时接住两类削弱：
    删字段 ⇒ 行为条对应参数不再判红；加字段 ⇒ 本条打红要求补扰动值。
    """
    assert tuple(_MOD._COMPARE_FIELDS) == _MUST_COMPARE, (
        f"脚本比对字段集变了：{list(_MOD._COMPARE_FIELDS)} != {list(_MUST_COMPARE)}"
    )
    assert set(_PERTURBED) == set(_MUST_COMPARE), "扰动值与必比集脱节"


@pytest.mark.parametrize("field", _MUST_COMPARE)
def test_partial_cycle_still_compares_every_field_in_step3(
    field: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """部分登记循环里，必比集的每一格都必须真被比对（逐格真扰动 + 真跑）。"""
    code, _, err = _run(
        monkeypatch,
        capsys,
        tmp_path,
        full_cycles=[],
        partial_cycles=["L"],
        baseline={"L": 0},
        catalog=[("L", "L2-3", _ie("L2-3", **{field: _PERTURBED[field]}))],
        manifests={"L": [_manifest_entry("L2-3")]},
    )
    markers = _marker_lines(err)
    assert code == 1, f"{field} 被扰动却放行了 —— Step 3 在部分登记循环里没跑"
    assert any(f"'L2-3'.{field}" in m for m in markers), (
        f"{field} 的不一致没有被报出：{markers}"
    )


def test_partial_cycle_passes_when_step3_fields_all_match(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """对照组：字段全一致时必须绿（否则上一条的红说明不了任何事）。"""
    code, _, err = _run(
        monkeypatch,
        capsys,
        tmp_path,
        full_cycles=[],
        partial_cycles=["L"],
        baseline={"L": 0},
        catalog=[("L", "L2-3", _ie("L2-3"))],
        manifests={"L": [_manifest_entry("L2-3")]},
    )
    assert (code, _marker_lines(err)) == (0, []), f"对照组不该红：{err!r}"


# ─── 3. 未覆盖条目数的基线比对（只许下调）─────────────────────────────────────


def test_partial_uncovered_count_above_baseline_is_red(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """未覆盖条目变多 = 回归，必须打红并指名多出来的条目。"""
    code, out, err = _run(
        monkeypatch,
        capsys,
        tmp_path,
        full_cycles=[],
        partial_cycles=["L"],
        baseline={"L": 1},
        catalog=[("L", "L8-8", _ie("L8-8")), ("L", "L9-9", _ie("L9-9"))],
        manifests={"L": []},
    )
    markers = _marker_lines(err)
    assert code == 1, "未覆盖条目 2 > 基线 1 却放行了"
    assert any("> 基线" in m and "L9-9" in m for m in markers), markers
    assert _reported_uncovered(out) == {"L": (2, 1)}, out


def test_partial_uncovered_count_below_baseline_demands_lowering(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """未覆盖条目变少 = 基线过期，必须要求同步下调（否则守卫自我失效）。"""
    code, out, err = _run(
        monkeypatch,
        capsys,
        tmp_path,
        full_cycles=[],
        partial_cycles=["L"],
        baseline={"L": 2},
        catalog=[("L", "L9-9", _ie("L9-9"))],
        manifests={"L": []},
    )
    markers = _marker_lines(err)
    assert code == 1, "基线过期（实测 1 < 基线 2）却放行了"
    assert any("NEEDS_BASELINE_LOWERING" in m and "1" in m for m in markers), markers
    assert _reported_uncovered(out) == {"L": (1, 2)}, out


def test_partial_uncovered_count_ignores_disabled_and_other_cycles(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """口径核验：只数「本循环 + enabled 为真」的条目。

    `enabled=false` / `import_export=null` / 别的循环的条目都不许进这个数 ——
    否则「只许下调」会被无关改动推高成假红。
    """
    code, out, err = _run(
        monkeypatch,
        capsys,
        tmp_path,
        full_cycles=[],
        partial_cycles=["L"],
        baseline={"L": 1},
        catalog=[
            ("L", "L9-9", _ie("L9-9")),
            ("L", "L9-8", _ie("L9-8", enabled=False)),
            ("L", "L9-7", None),
            ("Z", "Z9-9", _ie("Z9-9")),
        ],
        manifests={"L": []},
    )
    assert (code, _marker_lines(err)) == (0, []), err
    assert _reported_uncovered(out) == {"L": (1, 1)}, out


# ─── 4. 两组配置不自洽必须打红（「误加进 _SUPPORTED_CYCLES」的接住点）─────────


def test_cycle_in_both_groups_is_config_contradiction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """同一循环既全量又部分登记 = 配置矛盾，必须立刻红。

    这条是「把 L/M/N 误加进 `_SUPPORTED_CYCLES`」那条变异的接住点：两组重叠时
    无论哪一支胜出，另一支的判据都会静默失效，故不许静默通过。
    """
    code, _, err = _run(
        monkeypatch,
        capsys,
        tmp_path,
        full_cycles=["L"],
        partial_cycles=["L"],
        baseline={"L": 0},
        catalog=[("L", "L2-3", _ie("L2-3"))],
        manifests={"L": [_manifest_entry("L2-3")]},
    )
    assert code == 1, "两组重叠却放行了"
    assert any("自相矛盾" in m and "L" in m for m in _marker_lines(err)), err


def test_partial_cycle_without_baseline_is_red(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """部分登记循环缺基线 = Step 4 跳过后没人接住，必须红。"""
    code, _, err = _run(
        monkeypatch,
        capsys,
        tmp_path,
        full_cycles=[],
        partial_cycles=["L"],
        baseline={},
        catalog=[("L", "L9-9", _ie("L9-9"))],
        manifests={"L": []},
    )
    assert code == 1, "缺基线却放行了"
    assert any("缺" in m and "_PARTIAL_UNCOVERED_BASELINE" in m for m in _marker_lines(err)), err


def test_config_contradiction_report_keeps_marker_count_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """配置矛盾这条早退路径也要守住「表头自报数 == ✗ 行数」。

    下游 `snapshot_x3_baseline._count_ie_sync_drift` 以这两者交叉核对条目数，
    任一侧漏写都会让它判「解析口径已漂」。
    """
    _, _, err = _run(
        monkeypatch,
        capsys,
        tmp_path,
        full_cycles=["L", "M"],
        partial_cycles=["L", "M"],
        baseline={},
        catalog=[],
        manifests={"L": [], "M": []},
    )
    # 两条：①两组重叠 ②两个部分登记循环都缺基线（各自一条汇总行）
    assert _declared_count(err) == len(_marker_lines(err)) == 2, err


# ─── 5. 真实数据：L/M/N 零 error、三向一致、红不变大 ──────────────────────────


def test_real_run_reports_lmn_without_producing_any_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """真实 catalog 上：L/M/N 有计数汇报、但一条 error 都不产生。

    「一条 error 都没有」正是 Step 4 在真实数据上被跳过的实证 —— 真实 catalog
    里 L/N 确有 10 条未登记的启用条目，Step 4 若跑必然报出来。
    """
    code, out, err = _run_real(capsys)
    reported = _reported_uncovered(out)
    assert set(reported) == set(_X3_CYCLES), f"L/M/N 未被汇报：{out!r}"
    tagged = [m for m in _marker_lines(err) if re.match(r"✗\s*\[[LMN]\]", m)]
    assert tagged == [], f"部分登记循环产生了 error（Step 4 疑似在跑）：{tagged}"
    assert code == 1, "裁决 2：该脚本当前应仍是红（本任务不负责修绿）"


def test_real_uncovered_count_agrees_three_ways(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """独立复算值 == 脚本自报值 == 脚本基线，三向一致。

    - 与「独立复算」一致 ⇒ 脚本报的不是拍出来的数；
    - 与「基线」一致 ⇒ 基线没有被上调放水（上调后脚本自己会判
      NEEDS_BASELINE_LOWERING，这里也会红，两条独立路径）。
    """
    measured = _measure_real_uncovered()
    _, out, _ = _run_real(capsys)
    reported = _reported_uncovered(out)
    baseline = _MOD._PARTIAL_UNCOVERED_BASELINE

    for cyc in _X3_CYCLES:
        n = len(measured[cyc]["uncovered"])
        assert reported[cyc][0] == n, (
            f"[{cyc}] 脚本自报 {reported[cyc][0]} 条，独立复算 {n} 条"
        )
        assert reported[cyc][1] == baseline[cyc] == n, (
            f"[{cyc}] 基线 {baseline.get(cyc)} 与实测 {n} 不一致 —— "
            f"上调基线属放水，下调后须同步改基线"
        )


def test_real_uncovered_entries_never_grow_beyond_known_orphans() -> None:
    """存量孤儿只许缩小：实测集必须是已知欠账清单的子集。

    这一条不断言「这 10 条是正确的」（它们恰恰是别的 spec 要修的欠账，R8.6 不许
    把错值当正确基线），只断言「不许新增」—— 数量不变而成分被换掉也会红。
    """
    measured = _measure_real_uncovered()
    actual = {code for cyc in _X3_CYCLES for code in measured[cyc]["uncovered"]}
    assert actual <= _KNOWN_ORPHANS, (
        f"出现了新的未登记启用条目：{sorted(actual - _KNOWN_ORPHANS)}"
    )
    assert actual, "实测孤儿集为空 —— 口径或夹具失效（应为 10 条存量欠账）"


def test_real_red_scale_does_not_grow_and_stays_dgh(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """裁决 2：红的规模只许下调，成分只许是 D/G/H。

    用 `<=` 不用 `==`：别的 spec 把 d/g manifest 修绿时不许在这里假红。
    """
    _, _, err = _run_real(capsys)
    markers = _marker_lines(err)
    declared = _declared_count(err)
    assert declared == len(markers), (
        f"表头自报 {declared} 与 ✗ 行数 {len(markers)} 不一致 —— 下游解析口径会漂"
    )
    assert len(markers) <= _RED_SCALE_BASELINE, (
        f"红的规模从 {_RED_SCALE_BASELINE} 涨到 {len(markers)}：{markers}"
    )
    tags = {m.split("]")[0].split("[")[-1] for m in markers}
    assert tags <= _RED_SCALE_CYCLES, f"红里出现了新的循环：{sorted(tags)}"
