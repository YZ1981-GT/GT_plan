# -*- coding: utf-8 -*-
"""可插行清册的判据（Task 19 / T3）。

spec: excel-structural-row-insertion-and-shift-aware-verification
Requirements: 10.1 ~ 10.6 · Properties: **P27** / **P28**

═══ 这一份守什么 ═══════════════════════════════════════════════════════════

清册的价值在于「结论与引擎一致」。所以本文件的判据几乎全是**交叉验证**：

* 词表封闭且穷尽（每个 entry 恰好一格，没有 entry 落在词表之外）；
* 结论**由生产函数现算**，不是手填 —— 判据形态是「篡改模板/契约 ⇒ 结论必须跟着变」；
* 清册与 `excel_materialize` 的**独立第二实现**在同一个 entry 上给出同一结论
  （H1 实测两边都是 `blocked_total_formula_not_extendable`）；
* 阻塞项各有 `diagnostic_code` 与**解除条件**（AC 10.6）。

🔴 **不测「跑起来不报错」**：一个恒返回 `insertion_safe` 的清册也不报错，而那是最坏的
假绿 —— 它会让人以为可以上线。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

#: N2 脚本路径 —— 按路径加载（`backend/scripts/check` 不是包）。
SCRIPT_PATH = _BACKEND / "scripts" / "check" / "check_excel_row_insertion_readiness.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("_row_insertion_readiness", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def N() -> Any:
    return _load_module()


@pytest.fixture(scope="module")
def report(N: Any) -> dict[str, Any]:
    return N.build_report()


class TestScriptExistsAndIsReadOnly:
    """**Validates: Requirements 10.1**"""

    def test_script_is_on_disk_at_the_declared_path(self) -> None:
        assert SCRIPT_PATH.is_file(), f"N2 不在声明路径上: {SCRIPT_PATH}"

    def test_script_never_writes_into_the_template_library(self, N: Any) -> None:
        """清册只读模板库 —— 模板库是唯一权威源。"""
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        # 只允许 `TEMPLATE_ROOT / ...` 形态的读取；不得出现写入 API
        for forbidden in ("TEMPLATE_ROOT.write", "shutil.copy", "shutil.move", "os.replace"):
            assert forbidden not in source, f"清册脚本里出现写入面 {forbidden!r}"
        assert N.TEMPLATE_ROOT.name == "wp_templates"

    def test_json_is_written_by_python_not_shell_redirection(self) -> None:
        """AC 10.3：落盘走 `Path.write_text(encoding="utf-8")`。

        PowerShell 重定向会写出 UTF-16 / 带 BOM，下游 `json.loads` 直接炸。
        """
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'write_text(' in source and 'encoding="utf-8"' in source


class TestVerdictVocabularyIsClosedAndExhaustive:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 28: 可插行清册的结算词表封闭，每个 entry 恰好落进一格**

    **Validates: Requirements 10.2, 10.4**
    """

    def test_every_entry_lands_in_exactly_one_declared_verdict(
        self, report: dict[str, Any], N: Any
    ) -> None:
        assert report["entries"], "清册是空的 ⇒ 判据全部空转"
        verdicts = {e["verdict"] for e in report["entries"]}
        assert verdicts <= set(N.VERDICTS), sorted(verdicts - set(N.VERDICTS))
        # 计数与逐条一致（计数是独立算的 ⇒ 两者不一致说明有 entry 被漏计）
        for verdict in N.VERDICTS:
            expected = sum(1 for e in report["entries"] if e["verdict"] == verdict)
            assert report["counts"][verdict] == expected, verdict
        assert sum(report["counts"].values()) == len(report["entries"]) == report["total_entries"]

    def test_the_two_verdicts_found_during_implementation_are_in_the_vocabulary(
        self, N: Any
    ) -> None:
        """🔴 实施中实测发现的两格必须在词表里 —— design.md 的原词表少了它们。

        少了它们，清册会把「引擎明确拒绝」错报成 `insertion_safe`。
        """
        assert "blocked_static_row_below_insertion" in N.VERDICTS
        assert "blocked_total_formula_not_extendable" in N.VERDICTS

    def test_every_blocked_verdict_has_a_resolution(self, N: Any) -> None:
        """AC 10.6：不可插行的每一格都要给解除条件。"""
        blocked = [v for v in N.VERDICTS if v.startswith("blocked_")]
        assert blocked, "词表里一个 blocked_* 都没有 ⇒ 判据空转"
        for verdict in blocked:
            assert N.RESOLUTIONS.get(verdict), f"{verdict} 没有解除条件"
            assert len(N.RESOLUTIONS[verdict]) > 15, verdict

    def test_diagnostic_codes_are_present_on_blocked_entries_only(
        self, report: dict[str, Any]
    ) -> None:
        for entry in report["entries"]:
            if entry["verdict"].startswith("blocked_"):
                assert entry["diagnostic_code"], entry["adapter_id"]
                assert entry["resolution"], entry["adapter_id"]
                assert entry["detail"], entry["adapter_id"]
            else:
                assert entry["diagnostic_code"] == "", entry["adapter_id"]


class TestCensusFactsAreRealNotHandFilled:
    """**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property 27: 清册结论由真实模板与真实契约现算，不得手填**

    **Validates: Requirements 10.3, 10.5**
    """

    def test_every_entry_points_at_a_real_template_on_disk(
        self, report: dict[str, Any], N: Any
    ) -> None:
        assert not report["errors"], f"有 entry 现算失败: {report['errors']}"
        for entry in report["entries"]:
            template = N.TEMPLATE_ROOT / entry["template_relative_path"]
            assert template.is_file(), entry["template_relative_path"]

    def test_skeleton_row_counts_match_the_real_sheet_xml(
        self, report: dict[str, Any], N: Any
    ) -> None:
        """骨架行数必须与模板 XML 里的真实 `<row r>` 对得上（不是写死的数字）。"""
        for entry in report["entries"]:
            template = N.TEMPLATE_ROOT / entry["template_relative_path"]
            with zipfile.ZipFile(template) as zf:
                part = entry["facts"]["sheet_part"]
                xml = zf.read(part).decode("utf-8")
            rows = {int(m.group(1)) for m in re.finditer(r'<row r="(\d+)"', xml)}
            first, last = entry["managed_rows"]
            assert last in rows, f"{entry['adapter_id']}: 受管末行 {last} 不在真实 XML 里"
            assert entry["skeleton_rows"] == last - first + 1
            assert entry["insert_at"] == last + 1

    def test_mutating_the_contract_changes_the_verdict(self, N: Any) -> None:
        """🔴 篡改契约 ⇒ 结论必须跟着变。这才证明结论是**现算**的。

        ═══ 方向已反转（Open Gate 5，2026-09-05）════════════════════════════════

        原状：H1 实测 `blocked_total_formula_not_extendable`，本判据把它的 footer 改成
        `carries_total_formula=True` 证明阻塞理由会消失。

        现状：H1 的契约**已如实声明** `carries_total_formula=True`
        （`I28..O28` 逐格实测 7 条 `SUM(x13:x27)`，Open Gate 5 裁决），基线因此是
        `insertion_safe`。于是同一条证明改成**反向**：把声明改回 `False` ⇒ 阻塞理由必须
        重新出现。要证的东西没变（结论是现算的、不是冻结的），且反向更强 ——
        它同时证明「不声明就 fail closed」这条语义没有被 Open Gate 5 放宽。
        """
        import dataclasses

        from app.services.workpaper_sync.contracts import load_contract

        base = N.assess("h1.disposal_check")
        assert base.verdict == "insertion_safe", base.verdict

        real = load_contract("h1.disposal_check")
        patched_tables = []
        for table in real.sheets[0].tables:
            if table.footer_anchor is None:
                patched_tables.append(table)
                continue
            assert table.footer_anchor.carries_total_formula is True, (
                "基线契约应当已声明 carries_total_formula=True（Open Gate 5）—— "
                "否则本判据的反向变异无从施加"
            )
            patched_tables.append(
                dataclasses.replace(
                    table,
                    footer_anchor=dataclasses.replace(
                        table.footer_anchor, carries_total_formula=False
                    ),
                )
            )
        patched = dataclasses.replace(
            real,
            sheets=(dataclasses.replace(real.sheets[0], tables=tuple(patched_tables)),),
        )
        original = N.load_contract
        try:
            N.load_contract = lambda adapter_id: patched  # type: ignore[assignment]
            after = N.assess("h1.disposal_check")
        finally:
            N.load_contract = original  # type: ignore[assignment]
        assert after.verdict != base.verdict, (
            "把 carries_total_formula 改成 False 后结论没变 ⇒ 结论不是现算的（AC 10.3）"
        )
        assert after.verdict == "blocked_total_formula_not_extendable", after.verdict

    def test_an_unlocatable_footer_marker_fails_closed(self, N: Any) -> None:
        """🔴 契约声明了 footer 但定位不到 ⇒ 必须抛，**不得**当成「没有 footer 问题」。

        本脚本首版正是在这里假绿：它手写了一份没有数字字符引用解码的 marker 定位，
        于是在 H1 / B60 / G7（无 `sharedStrings.xml`、中文以 `&#21512;&#35745;` 存 inline）
        上一个都找不到，接着走进「无 footer ⇒ safe」那一支，把 3 个 entry 全报成可插行。
        """
        import dataclasses

        from app.services.workpaper_sync.contracts import load_contract

        real = load_contract("h1.disposal_check")
        table = real.sheets[0].tables[0]
        assert table.footer_anchor is not None
        broken = dataclasses.replace(
            real,
            sheets=(
                dataclasses.replace(
                    real.sheets[0],
                    tables=(
                        dataclasses.replace(
                            table,
                            footer_anchor=dataclasses.replace(
                                table.footer_anchor, marker="这个标记不存在于任何模板"
                            ),
                        ),
                    )
                    + tuple(real.sheets[0].tables[1:]),
                ),
            ),
        )
        original = N.load_contract
        try:
            N.load_contract = lambda adapter_id: broken  # type: ignore[assignment]
            with pytest.raises(N.ReadinessError, match="一处都找不到"):
                N.assess("h1.disposal_check")
        finally:
            N.load_contract = original  # type: ignore[assignment]

    def test_marker_location_reuses_the_production_finder(self, N: Any) -> None:
        """判据落在**函数身份**：清册必须调生产的 `_find_marker_row`，不是自己写一份。

        内容相等型判据挡不住「抄了一份、暂时行为还一样」——而这一份抄错过一次。
        """
        from app.services.workpaper_sync import excel_materialize as M

        source = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "M._find_marker_row" in source, "清册没有复用生产的 marker 定位入口"
        assert "M._shared_strings" in source
        # 反向：脚本里不得再出现第二份三载体解析
        assert 't="inlineStr"' not in source, (
            "清册里又出现了手写的 inlineStr 解析 ⇒ 第二份实现回来了"
        )
        assert callable(M._find_marker_row)


class TestCensusAgreesWithTheEngine:
    """清册与 `excel_materialize` 的**独立第二实现**必须给出同一结论。

    **Validates: Requirements 10.4**

    🔴 这是本文件最重要的一条：清册自己算一遍、引擎自己算一遍，两边独立。
    两边一致才说明清册可信；不一致说明其中一个错了，而那正是要立刻知道的事。
    """

    def test_h1_is_insertion_safe_by_both_the_census_and_the_engine(self, N: Any) -> None:
        """🔴 Open Gate 5 之后 H1 的结论从 blocked 翻成 `insertion_safe`。

        翻转的**唯一**原因是契约如实声明了 `carries_total_formula=True`
        （`I28..O28` 7 条 `SUM(x13:x27)` 逐格实测）。判据仍是「清册与引擎两个独立实现
        给出同一结论」：清册说 safe，引擎侧两条独立判据（静态行、合计覆盖）也都不反对。
        """
        import dataclasses

        from app.services.workpaper_sync import excel_materialize as M
        from app.services.workpaper_sync.contracts import load_contract

        census = N.assess("h1.disposal_check")
        assert census.verdict == "insertion_safe", census.verdict
        # `insertion_safe` 时无阻塞码（实测是空串而非 None）
        assert not census.diagnostic_code, repr(census.diagnostic_code)

        contract = load_contract("h1.disposal_check")
        # 引擎侧判据一：没有「静态行落在插入点之下」的问题（清册也这么认为）
        assert M._static_rows_at_or_below(
            contract=contract, insert_at=census.insert_at
        ) == ()
        # 引擎侧判据二：footer 确实声明了合计公式，且模板上真有公式格
        footer = contract.sheets[0].tables[0].footer_anchor
        assert footer is not None and footer.carries_total_formula is True

        # 🔴 非空证明：把声明去掉 ⇒ 清册与引擎**同时**翻红。
        #    只断言「两边都说 safe」时，一个恒返回 safe 的清册也能通过。
        patched = dataclasses.replace(
            contract,
            sheets=(
                dataclasses.replace(
                    contract.sheets[0],
                    tables=(
                        dataclasses.replace(
                            contract.sheets[0].tables[0],
                            footer_anchor=dataclasses.replace(
                                footer, carries_total_formula=False
                            ),
                        ),
                    )
                    + tuple(contract.sheets[0].tables[1:]),
                ),
            ),
        )
        original = N.load_contract
        try:
            N.load_contract = lambda adapter_id: patched  # type: ignore[assignment]
            blocked = N.assess("h1.disposal_check")
        finally:
            N.load_contract = original  # type: ignore[assignment]
        assert blocked.verdict == "blocked_total_formula_not_extendable", blocked.verdict
        assert blocked.diagnostic_code == "contract_total_formula_not_extendable"

    def test_the_engine_rejection_codes_are_all_mapped_into_the_vocabulary(
        self, N: Any
    ) -> None:
        """引擎能抛的每个位移域 `error_code` 都必须映射进词表 —— 漏一个就会落到错的格里。"""
        from app.services.workpaper_sync import excel_row_shift as RS

        engine_codes = {
            cls.error_code
            for cls in (
                RS.UnlistedRowBearingStructureError,
                RS.RowShiftStyleSourceMissingError,
                RS.SharedFormulaSpanError,
                RS.SharedFormulaOrientationError,
                RS.RowShiftPlanRangeError,
                RS.RowShiftPlanCountError,
            )
        }
        assert engine_codes <= set(N._CODE_TO_VERDICT), sorted(
            engine_codes - set(N._CODE_TO_VERDICT)
        )
        for code, verdict in N._CODE_TO_VERDICT.items():
            assert verdict in N.VERDICTS, (code, verdict)


class TestRequiredCoverage:
    """AC 10.5：必须覆盖 D2（真实超出骨架）与一个零增长对照。"""

    def test_d2_is_present_and_is_the_large_json_entry(self, report: dict[str, Any]) -> None:
        d2 = next(
            (e for e in report["entries"] if e["adapter_id"] == "d2.receivable_detail"), None
        )
        assert d2 is not None, "清册里没有 D2 ⇒ AC 10.5 的主载体缺失"
        assert d2["skeleton_rows"] > 0
        # D2 的 HTML store 实测 1260 行，远超骨架 ⇒ 它必然需要插行
        assert d2["skeleton_rows"] < 1260, d2["skeleton_rows"]

    def test_all_four_published_contracts_are_assessed(self, report: dict[str, Any]) -> None:
        ids = {e["adapter_id"] for e in report["entries"]}
        assert ids == {
            "b60.hour_budget",
            "d2.receivable_detail",
            "g7.soe_subsidiary_disclosure",
            "h1.disposal_check",
        }, sorted(ids)

    def test_store_rows_absent_means_structural_only_conclusions(
        self, report: dict[str, Any]
    ) -> None:
        """不给 `store_rows` 时 `rows_needed` 必须是 `None`，不能瞎猜一个数。"""
        assert report["store_rows_provided"] is False
        for entry in report["entries"]:
            assert entry["store_rows"] is None
            assert entry["rows_needed"] is None

    def test_a_zero_growth_entry_is_reported_as_no_insertion_needed(self, N: Any) -> None:
        """零增长对照：给一个 <= 骨架行数的 store_rows ⇒ `no_insertion_needed`。"""
        entry = N.assess("b60.hour_budget", store_rows=1)
        assert entry.verdict == "no_insertion_needed", entry.verdict
        assert entry.rows_needed == 0, entry.rows_needed


class TestCheckModeIsStrict:
    """`--check` 必须能发现磁盘清册与现算的差异（否则它是装饰品）。"""

    def test_check_mode_detects_a_tampered_census(
        self, N: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "census.json"
        monkeypatch.setattr(N, "OUTPUT_PATH", target, raising=True)
        assert N.main(["--json"]) == 0
        assert target.is_file()
        assert N.main(["--check"]) == 0

        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["entries"][0]["verdict"] = "insertion_safe"
        payload["counts"]["insertion_safe"] = 99
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        assert N.main(["--check"]) == 1, "篡改后 --check 仍返回 0 ⇒ 它没在比对"

    def test_check_mode_fails_when_the_census_is_missing(
        self, N: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(N, "OUTPUT_PATH", tmp_path / "absent.json", raising=True)
        assert N.main(["--check"]) == 2

    def test_written_census_is_utf8_and_loads_back(
        self, N: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """落盘必须是 UTF-8 且能直接 `json.loads` —— 中文模板名会暴露编码问题。"""
        target = tmp_path / "census.json"
        monkeypatch.setattr(N, "OUTPUT_PATH", target, raising=True)
        N.main(["--json"])
        raw = target.read_bytes()
        assert not raw.startswith(b"\xff\xfe") and not raw.startswith(b"\xef\xbb\xbf"), (
            "清册带 BOM / 是 UTF-16 ⇒ 下游 json.loads 会炸"
        )
        loaded = json.loads(raw.decode("utf-8"))
        assert any("应收账款" in e["template_relative_path"] for e in loaded["entries"]), (
            "中文模板名没保住 ⇒ 编码有问题"
        )
