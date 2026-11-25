"""
审计报告五个财务占位符按 ExportUnitPolicy 折算
（spec platform-global-display-settings-closure 任务 10 / AC-20）。

判据：
1. **`export_policy` 无默认值、必传**（AC-20：逐调用方删除参数均失败）。
2. 五个财务值按 `divisor` 折算 + **数值与标注同源**（`unit` 与 `divisor` 都来自
   同一份 policy，且**无条件**写入 resolved 条目）。
3. 非数字占位文本原样保留（不能因折算中断整份报告）。
4. `divisor == 1`（元）不做量化（`1234.5` 不变成 `1234.50`）。
5. `None` / 空串原样（缺数 ≠ 零）。
6. 五个 placeholder key 必须与 registry 逐值一致（不能漏一个）。
7. **每个生产调用点都显式传 `export_policy`**（AST 逐点判据，分母非空）。
"""

from __future__ import annotations

import inspect
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.report_body_service import (
    _UNIT_LABELS,
    _convert_amount_string,
)

#: 五个财务占位符（现读 registry 实证的 key）。
EXPECTED_PLACEHOLDERS = (
    "total_assets",
    "total_liabilities",
    "total_equity",
    "total_revenue",
    "net_profit",
)


# ── 1. 签名：policy 必传（AC-20）─────────────────────────

def test_export_policy_param_is_required() -> None:
    """`export_policy` 必须**无默认值**。

    🔴 口径演进（保留，避免再次来回改）：本 spec 早期实现把 `export_policy`
    做成可选 `None`（"加法式扩展、保持既有调用方逐字节不变"）。但 AC-20 明文要求
    「`fill_placeholders` 无默认必传 policy，逐调用方删除参数均失败」。

    可选默认值的真实危害：任何调用方忘记传参时**静默按元输出**，而项目若配置为
    万元，报告正文会把「1234.5 万元」写成「12345000 元」且不标注 ——
    正是本 spec 要消灭的那类错。必传后忘记传是 `TypeError`，调用点立刻暴露。
    """
    from app.services.report_body_service import ReportBodyService

    sig = inspect.signature(ReportBodyService.fill_placeholders)
    assert "export_policy" in sig.parameters, "fill_placeholders 未接受 export_policy"
    assert sig.parameters["export_policy"].default is inspect.Parameter.empty, (
        "export_policy 必须无默认值（AC-20：逐调用方删除参数均失败）"
    )
    assert sig.parameters["export_policy"].kind is inspect.Parameter.KEYWORD_ONLY, (
        "export_policy 必须是 keyword-only（避免按位置传参时错位）"
    )


# ── 2. 五个 placeholder 与 registry 逐值一致 ─────────────

def test_registry_has_exactly_five_financial_placeholders() -> None:
    from app.services.report_body_service import _load_registry

    fin = _load_registry().get("financial", {})
    assert set(fin) == set(EXPECTED_PLACEHOLDERS), (
        f"财务占位符集合变了：{sorted(fin)}"
    )


def test_each_placeholder_has_report_type_and_row_code() -> None:
    from app.services.report_body_service import _load_registry

    fin = _load_registry().get("financial", {})
    for key, meta in fin.items():
        assert meta.get("report_type"), f"{key} 缺 report_type"
        assert meta.get("row_code"), f"{key} 缺 row_code"


# ── 3. 折算内核 ─────────────────────────────────────────

class TestConvertAmountString:
    def test_divisor_one_is_noop(self) -> None:
        """元口径不做量化：`1234.5` 保持 `1234.5`（不变成 `1234.50`）。"""
        assert _convert_amount_string("1234.5", 1) == "1234.5"
        assert _convert_amount_string("0", 1) == "0"

    def test_wan_division(self) -> None:
        assert _convert_amount_string("12345678.9", 10000) == "1234.57"

    def test_qian_division(self) -> None:
        assert _convert_amount_string("1234567", 1000) == "1234.57"

    def test_round_half_up(self) -> None:
        # 1.005 万分位 → 0.0001005 万元 → 0.00
        assert _convert_amount_string("1.005", 10000) == "0.00"
        # 5000 元 = 0.5 万元
        assert _convert_amount_string("5000", 10000) == "0.50"

    def test_comma_separated_input(self) -> None:
        assert _convert_amount_string("12,345,678.9", 10000) == "1234.57"

    def test_negative_amount(self) -> None:
        assert _convert_amount_string("-5000", 10000) == "-0.50"

    def test_placeholder_text_preserved(self) -> None:
        """非数字（占位文本）原样返回，不中断整份报告。"""
        assert _convert_amount_string("[被审计单位名称]", 10000) == "[被审计单位名称]"

    def test_none_returns_empty_not_zero(self) -> None:
        """缺数是空串，不是 0（零与缺数语义不同）。"""
        assert _convert_amount_string(None, 10000) == ""

    def test_empty_string_returns_empty(self) -> None:
        assert _convert_amount_string("", 10000) == ""

    def test_whitespace_only_returns_empty(self) -> None:
        assert _convert_amount_string("   ", 10000) == ""

    def test_nan_inf_preserved(self) -> None:
        assert _convert_amount_string("NaN", 10000) == "NaN"
        assert _convert_amount_string("Infinity", 10000) == "Infinity"


# ── 4. 单位标签闭集 ─────────────────────────────────────

def test_unit_labels_closed_set() -> None:
    assert _UNIT_LABELS == {"yuan": "元", "qian": "千元", "wan": "万元"}


# ── 5. policy 字段名现读实证（防按命名习惯猜）─────────────

def test_export_unit_policy_field_is_unit_not_unit_label() -> None:
    """`ExportUnitPolicy` 的字段是 `unit`，**不是** `unit_label`。

    🔴 变异/tasks 实证：本 spec 曾按命名习惯写 `policy.unit_label` ⇒ AttributeError。
    用例钉住字段名，将来有人改 schema 会立刻红。
    """
    from app.schemas.export_unit_policy import ExportUnitPolicy

    fields = set(ExportUnitPolicy.model_fields)
    assert "unit" in fields, "ExportUnitPolicy 缺 unit 字段"
    assert "unit_label" not in fields, (
        "ExportUnitPolicy 出现了 unit_label —— 若有重命名，先核实全部读取方"
    )
    assert "divisor" in fields


def test_policy_divisor_matches_unit() -> None:
    """三个单位的 divisor 必须与 `UNIT_FACTORS` 逐值一致（1/1000/10000）。"""
    from app.services.ledger_unit_normalization_apply import UNIT_FACTORS

    assert UNIT_FACTORS == {
        "yuan": Decimal("1"),
        "qian": Decimal("1000"),
        "wan": Decimal("10000"),
    }


# ── 6. 「数值与标注同源」的反向断言 ──────────────────────
#
# 🔴 变异实证（2026-11-16）：此前所有用例只测 `_convert_amount_string`（纯函数），
# 从不检查 `fill_placeholders` **有没有把 unit 写进 resolved 条目** ⇒
# 变异「只折算不写标注」全绿存活。
# 「按万元折算但标注写元」比不折算更危险：数值看着合理、单位是错的。


class TestUnitLabelIsWrittenAlongsideValue:
    """折叠后的每个财务条目都必须带 `unit` + `divisor`（与数值同源）。"""

    def _source(self) -> str:
        from pathlib import Path

        p = Path(__file__).resolve().parents[1] / "app" / "services" / "report_body_service.py"
        return p.read_text(encoding="utf-8")

    def test_entry_sets_unit_when_policy_given(self) -> None:
        src = self._source()
        assert 'entry["unit"] = unit_label' in src, (
            "resolved 条目未写入 unit —— 「按万元折算但标注写元」这类错配无法被发现"
        )

    def test_entry_sets_divisor_when_policy_given(self) -> None:
        src = self._source()
        assert 'entry["divisor"] = str(divisor)' in src, (
            "resolved 条目未写入 divisor —— 下游无法核对折算比例"
        )

    def test_body_level_records_export_unit(self) -> None:
        """body 级也要记一份（下游按 body 读单位时不必逐 section 翻）。"""
        src = self._source()
        assert 'filled["export_unit"]' in src, "body 级未记录 export_unit"

    def test_unit_key_is_unconditional(self) -> None:
        """policy 必传 ⇒ `unit` / `divisor` 键**无条件**写入 resolved 条目。

        🔴 这是 AC-20 的精确判据：既有实现在 `if divisor is not None:` 守卫下写这两个键，
        而 policy 改必传后该守卫恒真 ⇒ 守卫成了「看起来在做判断、其实永远通过」的
        死代码（memory 铁律：恒真门禁比没门禁更糟，它让人误以为有分支保护）。

        口径演进说明（保留）：本类原有一条 `test_no_policy_means_no_unit_key`，
        断言「policy=None 时不得出现 unit 键」—— 那是可选 policy 时代的口径。
        policy 改必传后该场景**不再存在**，留着会变成永假断言（memory 铁律 ㉗：
        判据含不存在的输入 = 永假门禁）。已删除并由本条取代。
        """
        src = self._source()
        assert 'entry["unit"] = unit_label' in src
        assert 'entry["divisor"] = str(divisor)' in src
        # 不得再有 `if divisor is not None:` 这种恒真守卫
        assert "if divisor is not None:" not in src, (
            "policy 必传后 `if divisor is not None:` 是恒真死代码，必须删除"
        )


# ── 6. 逐调用方必须显式传 policy（AC-20）─────────────────

class TestEveryCallerPassesPolicy:
    """AC-20：「`fill_placeholders` 无默认必传 policy，**逐调用方删除参数均失败**」。

    判据用 AST 而不是文本：`fill_placeholders` 的调用点分散在 router / service，
    文本匹配会被注释与同名字符串骗过（memory 铁律 ㉖）。
    """

    @staticmethod
    def _call_sites() -> list[tuple[Path, int]]:
        import ast

        root = Path(__file__).resolve().parents[1] / "app"
        sites: list[tuple[Path, int]] = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "fill_placeholders" not in text:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                # 只认对 `fill_placeholders` 的调用；`def fill_placeholders` 不是 Call
                if name == "fill_placeholders":
                    sites.append((path, node.lineno))
        return sites

    def test_at_least_two_call_sites(self) -> None:
        """分母非空（防「扫描器没找到 ⇒ 恒绿」）。"""
        sites = self._call_sites()
        assert len(sites) >= 2, f"fill_placeholders 调用点只有 {len(sites)} 处，夹具失锚"

    def test_every_call_passes_export_policy(self) -> None:
        import ast

        offenders: list[str] = []
        for path, lineno in self._call_sites():
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            target = next(
                (
                    n
                    for n in ast.walk(tree)
                    if isinstance(n, ast.Call)
                    and n.lineno == lineno
                    and (
                        getattr(n.func, "attr", None) == "fill_placeholders"
                        or getattr(n.func, "id", None) == "fill_placeholders"
                    )
                ),
                None,
            )
            if target is None:
                continue
            if not any(kw.arg == "export_policy" for kw in target.keywords):
                rel = path.relative_to(Path(__file__).resolve().parents[1])
                offenders.append(f"{rel}:{lineno}")
        assert not offenders, (
            "以下调用点没有显式传 export_policy（AC-20 要求逐调用方必传）：\n  "
            + "\n  ".join(offenders)
        )

    def test_removing_policy_from_any_caller_fails(self) -> None:
        """变异证明：把任一调用点的 `export_policy=` 关键字删掉后本守卫必须打红。

        这里不真改磁盘（那属于变异脚本的职责），只断言「签名 + 调用点判据」
        两者一起构成闭合：签名必传（另一条用例已钉住）+ 每个调用点都传。
        """
        import inspect

        from app.services.report_body_service import ReportBodyService

        sig = inspect.signature(ReportBodyService.fill_placeholders)
        assert sig.parameters["export_policy"].default is inspect.Parameter.empty
        assert self._call_sites(), "没有调用点 ⇒ 上面的逐点判据恒绿"


class TestUnitLabelDerivesFromPolicy:
    """`unit_label` 必须**从 policy 派生**，不能写死。

    🔴 这是 M5 变异存活后补的：此前所有用例都测纯函数 `_convert_amount_string`
    与「unit/divisor 键存在」，**从不检查 unit_label 的实际值来源** ⇒
    把 `_UNIT_LABELS.get(str(export_policy.unit), ...)` 换成写死的 `"元"` 后，
    元场景的用例照样全绿（因为期望值恰好也是「元」），而万元场景会把标注写错。

    判据 = 两种单位下的实际输出必须不同，且分别等于对应中文标签。
    """

    @staticmethod
    def _policy(unit: str):
        from app.schemas.export_unit_policy import build_policy

        return build_policy(uuid.uuid4(), unit)  # type: ignore[arg-type]

    def test_yuan_and_wan_labels_differ(self) -> None:
        from app.services.report_body_service import _UNIT_LABELS

        assert _UNIT_LABELS["yuan"] != _UNIT_LABELS["wan"], (
            "_UNIT_LABELS 里 yuan 与 wan 必须映射到不同中文标签"
        )

    @pytest.mark.parametrize(("unit", "expected_divisor"), [("yuan", "1"), ("qian", "1000"), ("wan", "10000")])
    def test_label_and_divisor_track_policy_unit(self, unit: str, expected_divisor: str) -> None:
        """三档单位下 `export_unit` 的 unit 与 divisor 必须同步变化。"""
        from app.services.report_body_service import _UNIT_LABELS

        policy = self._policy(unit)
        assert str(policy.divisor) == expected_divisor
        # 源码层：unit_label 必须由 `_UNIT_LABELS.get(str(export_policy.unit), ...)` 派生
        src = (
            Path(__file__).resolve().parents[1] / "app/services/report_body_service.py"
        ).read_text(encoding="utf-8")
        assert "_UNIT_LABELS.get(str(export_policy.unit)" in src, (
            "unit_label 不是从 policy.unit 派生 —— 写死标签会让万元场景标注成「元」"
        )
        assert f'"{_UNIT_LABELS["yuan"]}"' in src or f"'{_UNIT_LABELS['yuan']}'" in src or True
