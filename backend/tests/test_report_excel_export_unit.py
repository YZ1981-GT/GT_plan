"""
单张报表 Excel 正式导出必须消费 ExportUnitPolicy（AC-20 / AC-22）。

🔴 本守卫来自一次**浏览器实测抓到的真实缺陷**（2026-11-16）：

`GET /api/reports/{project_id}/{year}/{report_type}/export-excel` 已在
`EXPORT_SURFACE_REGISTRY` 登记为 `formal`，但实现**直接写 `current_period_amount`
原值、无单位标注、不读 policy**。实测证据：把【测试】项目的 `amount_unit`
从 `yuan` 改成 `wan` 后，两次导出的 xlsx **sha256 完全相同** ——
用户按万元看数、拿到的却是元值，文件里也不写口径。

修复后实测：yuan 档 `金额单位：元` + `350`；wan 档 `金额单位：万元` + `0.04`，
数值与标注同源、按同一 divisor 改变。

本文件只做**纯函数与接线判据**（不需要真库）。端到端 Excel 内容比对由
浏览器实测承担（见 spec tasks A-V/C-V 证据）。
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_SERVICE = _BACKEND / "app/services/report_excel_export.py"
_ROUTER = _BACKEND / "app/routers/reports.py"
_REGISTRY = _BACKEND / "app/services/export_surface_registry.py"


class TestConvertAmountForExport:
    """折算内核的四条纪律（与 trial_balance_export / report_body_service 同一套）。"""

    def _convert(self, value, divisor):
        from app.services.report_excel_export import convert_amount_for_export

        return convert_amount_for_export(value, divisor)

    @pytest.mark.parametrize("value", [None, ""])
    def test_missing_value_stays_none(self, value) -> None:
        """缺数 ≠ 零：`None` / 空串必须返回 `None`，不能写 0 冒充有数据。"""
        assert self._convert(value, 1) is None
        assert self._convert(value, 10000) is None

    def test_divisor_one_does_not_quantize(self) -> None:
        """元档不做量化（`1234.5` 不变成 `1234.50`）。

        🔴 M4 变异存活暴露的判据弱点：`convert_amount_for_export` 返回 **float**，
        而 `float(Decimal("1234.5").quantize(Decimal("0.01")))` 与
        `float(Decimal("1234.5"))` **完全相同**（尾随零在 float 里不可表示）
        ⇒ 只比返回值的用例对「元档是否量化」是**等价变异**，永远测不出来。

        正解 = 判**代码路径**：`divisor == 1` 分支必须提前 return，
        不得走到 `.quantize(...)`（用 AST 判 `return` 在 quantize 之前）。
        """
        assert self._convert("1234.5", 1) == 1234.5
        assert self._convert(Decimal("1234.5"), 1) == 1234.5

        # 代码路径判据（对 float 不可见的那一半）
        import ast

        tree = ast.parse((_BACKEND / "app/services/report_excel_export.py").read_text(encoding="utf-8"))
        func = next(
            (
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "convert_amount_for_export"
            ),
            None,
        )
        assert func is not None, "找不到 convert_amount_for_export"
        # 找出 `if divisor == 1:` 的位置与其 body 里是否有 return
        guard_line = None
        early_return_line = None
        quantize_line = None
        for node in ast.walk(func):
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "divisor"
                and any(isinstance(op, ast.Eq) for op in node.test.ops)
            ):
                if any(isinstance(stmt, ast.Return) for stmt in node.body):
                    guard_line = node.lineno
                    early_return_line = node.body[0].lineno
            if isinstance(node, ast.Attribute) and node.attr == "quantize":
                quantize_line = node.lineno
        assert guard_line is not None, (
            "`divisor == 1` 分支里没有提前 return —— 元档会走 quantize"
        )
        assert quantize_line is not None, "找不到 quantize 调用（夹具失锚）"
        assert early_return_line < quantize_line, (
            f"`divisor == 1` 的 return（行 {early_return_line}）必须在 quantize"
            f"（行 {quantize_line}）之前"
        )

    @pytest.mark.parametrize(
        ("value", "divisor", "expected"),
        [
            ("350", 10000, 0.04),          # 0.035 → ROUND_HALF_UP → 0.04
            ("-350", 10000, -0.04),        # 负对称
            ("9182572.99", 10000, 918.26), # 918.257299 → 918.26
            ("9182572.99", 1000, 9182.57), # 9182.57299 → 9182.57
            ("0", 10000, 0.0),
        ],
    )
    def test_divisor_conversion_uses_half_up(self, value, divisor, expected) -> None:
        assert self._convert(value, divisor) == pytest.approx(expected, abs=0.0001)

    def test_half_up_not_half_even(self) -> None:
        """必须是 ROUND_HALF_UP（0.035 → 0.04），不是银行家舍入（0.035 → 0.03）。"""
        from app.services import report_excel_export as mod

        src = mod.__file__
        text = Path(src).read_text(encoding="utf-8")
        assert "ROUND_HALF_UP" in text, "折算内核必须显式使用 ROUND_HALF_UP"

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), "-inf"])
    def test_non_finite_raises(self, value) -> None:
        """NaN / ±Infinity 必须抛（不能静默写 0）。"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._convert(str(value), 10000)
        assert exc.value.status_code == 500

    def test_garbage_raises(self) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            self._convert("not-a-number", 1)


class TestUnitLabelsAreSingleSource:
    def test_labels_cover_all_policy_units(self) -> None:
        """三档单位都必须有中文标签（新增单位时这条会打红提醒同步）。"""
        from app.schemas.export_unit_policy import UNIT_DIVISORS
        from app.services.report_excel_export import EXPORT_UNIT_LABELS

        assert set(EXPORT_UNIT_LABELS) == set(UNIT_DIVISORS), (
            f"标签集合与 UNIT_DIVISORS 不一致：{sorted(EXPORT_UNIT_LABELS)} vs {sorted(UNIT_DIVISORS)}"
        )
        for unit, label in EXPORT_UNIT_LABELS.items():
            assert label, f"{unit} 的标签为空"
            assert label != unit, f"{unit} 的标签回退成了英文键名"

    def test_labels_are_chinese(self) -> None:
        from app.services.report_excel_export import EXPORT_UNIT_LABELS

        assert EXPORT_UNIT_LABELS == {"yuan": "元", "qian": "千元", "wan": "万元"}


class TestRouterIsThinShellAndRegistered:
    def test_router_delegates_to_service(self) -> None:
        """路由必须是薄壳：只调 service，不自己拼 xlsx（撤回这条等于撤回修复）。"""
        tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
        calls: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "export_report_excel":
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    calls.append(
                        getattr(inner.func, "attr", None) or getattr(inner.func, "id", None) or ""
                    )
        assert "build_report_excel_response" in calls, (
            "路由没有调用 build_report_excel_response"
        )
        # 不得在路由里直接构造 openpyxl 工作簿（那是修复前的形态）
        assert "Workbook" not in calls, "路由仍在自行构造 openpyxl Workbook"

    @staticmethod
    def _code_only(rel: str) -> str:
        """剥离注释与 docstring，只留可执行代码。

        🔴 这两条判据首轮都**被自己的注释骗过**（memory 铁律 ㉖）：
        service 的模块 docstring 里写了「不读 displayPrefs」「不写 `_GT_EXPORT_META`」
        作为纪律说明，而判据是 `"displayPrefs" not in text` ⇒ 说明文字自己把判据打红了。
        反过来，若有人真写了读取代码、只是把注释删掉，纯文本判据也会漏。
        正解 = 去掉注释与字符串常量后判。
        """
        import ast

        tree = ast.parse((_BACKEND / rel).read_text(encoding="utf-8"))
        # 去掉所有 docstring（Expr(Constant(str))）
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    node.body = body[1:] or [ast.Pass()]
        return ast.unparse(tree)

    def test_service_reads_policy_via_single_entry(self) -> None:
        """policy 必须经唯一入口 `resolve_export_policy` 取，不读 displayPrefs。"""
        code = self._code_only("app/services/report_excel_export.py")
        assert "resolve_export_policy" in code
        # formal 出口不得读个人显示偏好（判**代码**，不是注释）
        for forbidden in ("displayPrefs", "display_prefs", "user_display_preferences"):
            assert forbidden not in code, f"service 的可执行代码里出现了 {forbidden}"

    def test_service_writes_unit_label(self) -> None:
        """必须写「金额单位：X」标注（数值与标注同源，用户才能核对口径）。"""
        code = self._code_only("app/services/report_excel_export.py")
        assert "金额单位" in code, "可执行代码里没有「金额单位」标注（写在注释里不算）"

    def test_service_does_not_write_data_exchange_marker(self) -> None:
        """formal 出口不得出现 `_GT_EXPORT_META`（那是 data_exchange 的标记）。"""
        code = self._code_only("app/services/report_excel_export.py")
        assert "_GT_EXPORT_META" not in code, (
            "formal 出口的可执行代码里出现了 data_exchange 的 marker"
        )

    def test_endpoint_is_registered_as_formal(self) -> None:
        """注册表必须把本端点登记为 formal（否则「已收口」与注册表自相矛盾）。"""
        text = _REGISTRY.read_text(encoding="utf-8")
        assert "/api/reports/{project_id}/{year}/{report_type}/export-excel" in text
        # 该条目附近必须是 formal
        idx = text.find("/api/reports/{project_id}/{year}/{report_type}/export-excel")
        window = text[idx : idx + 400]
        assert 'classification="formal"' in window
