"""`DisplayPreferencesPatch` 不得在生成 OpenAPI 时抛 PydanticJsonSchemaWarning。

## 缺陷

`schema/display_preferences.py` 里 9 个业务字段用 `= _UNSET`（一个裸 `object()` 实例）
做默认值。Pydantic v2 在生成 JSON Schema 时要序列化默认值，`object()` 不可序列化
⇒ 每次 `app.openapi()` 打 9 条 `PydanticJsonSchemaWarning`。

影响是**噪声而非功能**（启动日志里 9 条重复告警，训练所有人忽略告警），
但它是「门禁/告警失效」这一类问题的典型前兆 —— 本仓已有多次「红成常态 = 没人看」
的历史（memory：永红门禁等于没有门禁）。

## 修法

用 `Field(default_factory=_unset)` 代替直接赋值：pydantic 不再把对象当默认值做
JSON Schema 序列化，而 `default_factory` 返回的**仍是同一个** `_UNSET`
⇒ `is` 判据与校验行为完全不变（「字段未出现在请求里」的语义原样保留）。

## 本守卫的三条

1. **生成 OpenAPI 时 0 条** PydanticJsonSchemaWarning（正向）。
2. **语义未变**：未传字段 → 值 `is _UNSET`；显式传 `None` → 值为 `None`
   （「跟随项目」语义）（`default_factory` 改造最危险的回归点）。
3. **反向**：不得再用「直接赋值裸对象」的写法（防止有人改回去）。
"""

from __future__ import annotations

import warnings

import pytest


def test_openapi_generation_emits_no_pydantic_json_schema_warning() -> None:
    """生成 OpenAPI schema 时不得有 PydanticJsonSchemaWarning。

    🔴 必须调到 `app.openapi()` —— 只在 `import app.main` 时收警告会是 0 条，
    让判据假绿（本轮实测：HEAD 版 import 时 0 条，生成 schema 时才 9 条）。
    """
    from app.main import app

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app.openapi()

    offenders = [
        w for w in caught
        if "PydanticJsonSchemaWarning" in type(w.message).__name__
    ]
    assert offenders == [], (
        f"生成 OpenAPI 时出现 {len(offenders)} 条 PydanticJsonSchemaWarning；"
        f"首条：{offenders[0].message if offenders else ''}"
    )


def test_unset_semantics_preserved() -> None:
    """`default_factory` 改造后，「显式 null / 显式值」两条语义必须与改造前一致。

    🔴 「全字段未传」不能构造合法实例（validator 要求至少一个业务字段），
    而 `model_construct` 又**不执行 default_factory**（字段直接缺失，本轮实测踩到）。
    所以「未传 = _UNSET」这条由 `test_default_factory_returns_same_unset_object`
    从 default_factory 本身验证；本用例只管另外两条可合法构造的语义。
    """
    from app.schemas.display_preferences import DisplayPreferencesPatch, _UNSET

    # ① 显式 null → None（「跟随项目」语义），只对 amount_unit_override 合法
    p2 = DisplayPreferencesPatch(base_revision=1, amount_unit_override=None)
    assert p2.amount_unit_override is None
    # 同实例上其它字段仍是 _UNSET（未被"顺手"填上默认值）
    assert p2.font_size is _UNSET
    assert p2.fixed_columns is _UNSET

    # ② 显式值 → 保留；未传的邻居保持 _UNSET
    #    🔴 FontSize 的字面量是 xs/sm/md/lg（不是 large）—— 本轮实测被 literal_error 打红
    p3 = DisplayPreferencesPatch(base_revision=1, font_size="lg")
    assert p3.font_size == "lg"
    assert p3.amount_unit_override is _UNSET


def test_default_factory_returns_same_unset_object() -> None:
    """`default_factory=_unset` 返回的必须**是同一个** `_UNSET` 对象。

    这是改造的正确性前提：`is` 判定（`val is not _UNSET`）全靠对象同一性。
    若 default_factory 每次返回新对象，validator 会把「未传」误判成「传了」，
    于是「至少一个业务字段」恒真 —— 就是 memory 里记的「恒绿判据」形态。
    """
    import inspect

    from app.schemas.display_preferences import DisplayPreferencesPatch, _UNSET

    field = DisplayPreferencesPatch.model_fields["font_size"]
    factory = field.default_factory
    assert factory is not None, "font_size 必须用 default_factory"
    produced = factory()
    assert produced is _UNSET, "default_factory 必须返回同一个 _UNSET 对象（is 判定依赖它）"

    # 两次调用也要同一对象（不是每次新建）
    assert factory() is factory()
    # 与模块常量同一
    src = inspect.getsource(DisplayPreferencesPatch)
    assert "_unset" in src


def test_no_bare_object_default_assignment() -> None:
    """反向：不得再出现「直接赋值 `= _UNSET`」的写法。

    直接赋值会让 pydantic 把 object() 当默认值做 JSON Schema 序列化，
    正是那 9 条警告的成因。
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "schemas" / "display_preferences.py"
    ).read_text(encoding="utf-8")

    # 只查「字段行」：以标识符开头、含 `: <类型> = _UNSET`
    offenders = [
        line.strip()
        for line in src.replace("\r\n", "\n").split("\n")
        if "= _UNSET" in line and "default_factory" not in line and "return _UNSET" not in line
        and not line.strip().startswith("#")
        and "_UNSET = " not in line
    ]
    assert offenders == [], (
        "以下字段仍用裸对象默认值（会在生成 OpenAPI 时打警告），"
        f"应改为 Field(default_factory=_unset)：{offenders}"
    )


def test_all_nine_fields_updated_together() -> None:
    """9 个业务字段必须**全部**用 default_factory —— 漏一个就还有警告。

    数字 9 来自 HEAD 实测（`app.openapi()` 9 条警告逐字段对应）；
    这里按「字段清单」断言而非只数与警告数，避免有人删掉一个字段
    让测试碰巧变绿。
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "schemas" / "display_preferences.py"
    ).read_text(encoding="utf-8").replace("\r\n", "\n")

    # 🔴 只查 `DisplayPreferencesPatch` 类体内 —— 同文件还有
    #    `DisplayPreferencesResponse` 也定义 `amount_unit_override: AmountUnitOverride = None`
    #    （那里默认 None 是对的，不该被本判据命中；本轮实测踩到）。
    body = src.split("class DisplayPreferencesPatch(", 1)[1]
    body = body.split("\n    @model_validator", 1)[0]

    expected = [
        "amount_unit_override", "font_size", "show_zero", "decimals",
        "negative_red", "highlight_threshold", "density", "grid_edit_mode",
        "fixed_columns",
    ]
    for name in expected:
        line = next(
            (l for l in body.split("\n") if l.strip().startswith(f"{name}:")),
            None,
        )
        assert line is not None, f"DisplayPreferencesPatch 缺少字段 {name}"
        assert "default_factory=_unset" in line, (
            f"字段 {name} 未使用 default_factory（会在 OpenAPI 生成时打警告）：{line.strip()}"
        )