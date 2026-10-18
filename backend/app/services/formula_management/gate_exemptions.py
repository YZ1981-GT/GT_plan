"""公式管理全量门禁的分母豁免登记——读取 + 可伪证校验。

Task 2.2 / spec `formula-manager-closure`（design ADR-FMC-03、§5 步骤 2、§7.3）。

**为什么不是只存理由文本**（memory 铁律㉗⑤）：
    只存一行 reason 的豁免 = 加一行就变绿的后门。本模块要求每条豁免附带
    ``verify_against``（可被运行时事实验证的字段），门禁读取时逐条调
    :func:`validate_exemption` 比对**活数据**（这里是 ``wp_code_overrides.json``
    的运行时映射 + render-config 对 B15 的 redirect 口径）。任一字段抽不到值
    或与事实不符 → 豁免**失效**（``valid=False``），该项须重新计入门禁分母并
    触发相应断言红。

**防空转断言**（memory 铁律㉗⑤「判据抽不到值」）：
    :func:`validate_exemption` 在 ``verify_against`` 为空、或声明的 wp_code 在
    运行时 override 表里根本抽不到值时，一律判 ``valid=False`` 且归因
    ``probe_empty``——绝不因为「抽不到就跳过」而静默放行（静默放行正是空转后门）。

门禁（``formula-manager-all-accessible-pages.spec.ts`` / 其 Python 子进程）
复用本模块：调 :func:`load_exemptions` 读登记、对每条调 :func:`validate_exemption`，
只有 ``valid=True`` 的 key 才从非 redirect 分母剔除。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.services.wp_code_override_loader import load_wp_code_overrides

__all__ = [
    "GateExemption",
    "ExemptionValidation",
    "load_exemptions",
    "validate_exemption",
    "exempted_keys",
    "classify_404_wp_code",
    "KIND_CLASSIFICATION_404_OUT_OF_SCOPE",
    "EXEMPTIONS_PATH",
]

EXEMPTIONS_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "formula_manager_gate_exemptions.json"
)

#: redirect 类豁免的 ``verify_against`` 必填键（防空转：缺任一即 probe_empty）。
_REQUIRED_VERIFY_KEYS = (
    "wp_code",
    "override_component_type",
    "delegated_module",
    "target_path",
)

#: classification-404 口径外豁免的 ``verify_against`` 必填键。
#: 「口径外」的可验证事实 = 该 wp_code 在运行时 wp_code_overrides 表里**本就没有映射**
#: （未建模底稿）。``classification_status`` 固定声明 ``out_of_scope``，供门禁/审计读取意图。
_REQUIRED_404_VERIFY_KEYS = (
    "wp_code",
    "classification_status",
)

#: classification-404 口径外豁免的 kind 常量。
KIND_CLASSIFICATION_404_OUT_OF_SCOPE = "classification-404-out-of-scope"

#: 口径外豁免 ``classification_status`` 必须是这个字面值（意图声明）。
_OUT_OF_SCOPE_STATUS = "out_of_scope"

#: B15 redirect 的运行时口径真源（与 wp_render_config.py 的 redirect-materiality 分支逐字一致）。
_REDIRECT_MATERIALITY_MODULE = "materiality"
_REDIRECT_MATERIALITY_TARGET = "/materiality"


@dataclass(slots=True)
class GateExemption:
    """一条门禁分母豁免登记。"""

    key: str
    kind: str
    owner: str
    reason: str
    expires_at: str | None
    verify_against: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, today: date | None = None) -> bool:
        """expires_at 为未来日期（含今天）才未过期；缺失 / 不可解析 → 视为过期（fail-closed）。"""
        if not self.expires_at:
            return True
        try:
            return (today or date.today()) > date.fromisoformat(self.expires_at)
        except (ValueError, TypeError):
            return True


@dataclass(slots=True)
class ExemptionValidation:
    """单条豁免的校验结论。"""

    key: str
    valid: bool
    #: 失效归因：ok / fields_missing / expired / probe_empty / fact_mismatch
    reason_code: str
    detail: str = ""


def load_exemptions(path: Path | None = None) -> list[GateExemption]:
    """读登记文件为 :class:`GateExemption` 列表。

    文件缺失 / 解析失败 / 结构非法均抛异常（门禁不吞——坏登记必须炸出来，
    否则等于悄悄放行所有分母项）。
    """
    p = path or EXEMPTIONS_PATH
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"豁免登记根元素必须是 object，实际 {type(data).__name__}")
    raw_list = data.get("exemptions")
    if not isinstance(raw_list, list):
        raise ValueError("豁免登记缺少 list 字段 `exemptions`")
    out: list[GateExemption] = []
    for i, raw in enumerate(raw_list):
        if not isinstance(raw, dict):
            raise ValueError(f"exemptions[{i}] 必须是 object")
        out.append(
            GateExemption(
                key=str(raw.get("key", "")),
                kind=str(raw.get("kind", "")),
                owner=str(raw.get("owner", "")),
                reason=str(raw.get("reason", "")),
                expires_at=raw.get("expires_at"),
                verify_against=dict(raw.get("verify_against") or {}),
            )
        )
    return out


def validate_exemption(
    ex: GateExemption,
    *,
    overrides: dict[str, str] | None = None,
    today: date | None = None,
) -> ExemptionValidation:
    """对一条豁免做**可伪证**校验。

    ``overrides`` 为运行时 wp_code→componentType 映射；不传则现读
    ``wp_code_overrides.json``（活数据）。这是豁免可伪证的关键：若 B15 的
    override 不再是 ``redirect-materiality``，或 redirect 口径变了，则豁免失效。

    返回 ``valid=False`` 的归因（reason_code）:
      * ``fields_missing`` —— owner/reason/expires_at/verify_against 三字段不齐。
      * ``probe_empty`` —— verify_against 缺必填键，或声明 wp_code 在运行时
        override 表抽不到值（防空转断言）。
      * ``expired`` —— expires_at 已过期（或缺失 / 不可解析）。
      * ``fact_mismatch`` —— verify_against 与运行时事实不符。
    """
    # ① 三字段齐全（owner / reason / expires_at 非空）+ verify_against 存在
    if not ex.owner.strip() or not ex.reason.strip() or not ex.expires_at or not ex.verify_against:
        return ExemptionValidation(
            ex.key, False, "fields_missing",
            "owner/reason/expires_at/verify_against 必须齐全且非空",
        )

    # classification-404 口径外豁免走独立校验路径（可验证事实 = wp_code 本就不在 override 表）。
    if ex.kind == KIND_CLASSIFICATION_404_OUT_OF_SCOPE:
        return _validate_classification_404(ex, overrides=overrides, today=today)

    # ② 防空转：verify_against 必填键齐全
    missing = [k for k in _REQUIRED_VERIFY_KEYS if not str(ex.verify_against.get(k, "")).strip()]
    if missing:
        return ExemptionValidation(
            ex.key, False, "probe_empty",
            f"verify_against 缺必填键 {missing}（判据抽不到值，拒绝空转放行）",
        )

    # ③ expires_at 必须是未来日期（含今天）
    if ex.is_expired(today):
        return ExemptionValidation(
            ex.key, False, "expired",
            f"expires_at={ex.expires_at!r} 已过期或不可解析",
        )

    # ④ 对活数据逐值比对（可伪证核心）
    ov = overrides if overrides is not None else load_wp_code_overrides()
    wp_code = str(ex.verify_against["wp_code"])
    declared_ct = str(ex.verify_against["override_component_type"])

    # 防空转：声明的 wp_code 在运行时 override 表里抽不到值
    live_ct = ov.get(wp_code)
    if live_ct is None:
        return ExemptionValidation(
            ex.key, False, "probe_empty",
            f"wp_code={wp_code!r} 在运行时 wp_code_overrides 表抽不到值（判据空转）",
        )

    if live_ct != declared_ct:
        return ExemptionValidation(
            ex.key, False, "fact_mismatch",
            f"wp_code={wp_code!r} 运行时 override={live_ct!r} ≠ 登记 {declared_ct!r}",
        )

    # redirect-materiality 专项：redirect 目标仍须是 materiality 模块
    if declared_ct == "redirect-materiality":
        dm = str(ex.verify_against["delegated_module"])
        tp = str(ex.verify_against["target_path"])
        if dm != _REDIRECT_MATERIALITY_MODULE or tp != _REDIRECT_MATERIALITY_TARGET:
            return ExemptionValidation(
                ex.key, False, "fact_mismatch",
                f"redirect 目标登记为 module={dm!r}/target={tp!r}，"
                f"与运行时口径 {_REDIRECT_MATERIALITY_MODULE!r}/{_REDIRECT_MATERIALITY_TARGET!r} 不符",
            )

    return ExemptionValidation(ex.key, True, "ok", "")


def _validate_classification_404(
    ex: GateExemption,
    *,
    overrides: dict[str, str] | None = None,
    today: date | None = None,
) -> ExemptionValidation:
    """校验一条 classification-404「口径外」豁免（可伪证）。

    可验证事实（Task 2.3，design §5 步骤 2 404 归类）:
      「口径外」= 该 404 wp_code 在运行时 ``wp_code_overrides.json`` 表里**没有映射**
      （本就无建模的未知底稿）。这正是它从门禁按钮分母剔除的唯一正当理由。

    可伪证点（这不是加一行就绿的后门）:
      * ``fields_missing`` —— verify_against 缺（含 ``classification_status`` 非 ``out_of_scope``）。
      * ``probe_empty`` —— verify_against 缺必填键。
      * ``expired`` —— expires_at 过期 / 缺失 / 不可解析（fail-closed）。
      * ``fact_mismatch`` —— **wp_code 竟然在运行时 override 表里有映射** → 它其实是
        「数据漂移」（应补 classification / 仍计入分母），不该被当口径外剔除 → 豁免失效，
        该 404 重新计入分母、门禁要求重新归类。
    """
    # 防空转：必填键齐全 + classification_status 固定字面值
    missing = [k for k in _REQUIRED_404_VERIFY_KEYS if not str(ex.verify_against.get(k, "")).strip()]
    if missing:
        return ExemptionValidation(
            ex.key, False, "probe_empty",
            f"verify_against 缺必填键 {missing}（判据抽不到值，拒绝空转放行）",
        )
    if str(ex.verify_against.get("classification_status")) != _OUT_OF_SCOPE_STATUS:
        return ExemptionValidation(
            ex.key, False, "fields_missing",
            f"classification_status 必须是 {_OUT_OF_SCOPE_STATUS!r}（口径外意图声明）",
        )

    # expires_at 必须未过期
    if ex.is_expired(today):
        return ExemptionValidation(
            ex.key, False, "expired",
            f"expires_at={ex.expires_at!r} 已过期或不可解析",
        )

    # 可伪证核心：对活数据比对——口径外的 wp_code 必须在 override 表里**抽不到映射**。
    ov = overrides if overrides is not None else load_wp_code_overrides()
    wp_code = str(ex.verify_against["wp_code"])
    live_ct = ov.get(wp_code)
    if live_ct is not None:
        return ExemptionValidation(
            ex.key, False, "fact_mismatch",
            f"wp_code={wp_code!r} 在运行时 override 表有映射={live_ct!r} → 实为『数据漂移』"
            f"（应补 classification、仍计入分母），不得当口径外剔除",
        )

    return ExemptionValidation(ex.key, True, "ok", "")


def classify_404_wp_code(
    wp_code: str,
    *,
    overrides: dict[str, str] | None = None,
) -> str:
    """对一个 classification 404 的 wp_code 做一次 ``wp_code_overrides.json`` 查表归类。

    这是 design §5 步骤 2「逐个查 wp_code_overrides.json」的单点实现，供探针 / 门禁 / 测试复用。

    Returns:
      * ``"data_drift"`` —— 命中 override 映射（应补 classification / 补 override 行，**仍计入**
        门禁按钮分母）。
      * ``"out_of_scope"`` —— 未命中映射（本就无建模的未知底稿，从门禁分母**显式剔除** +
        登记带可验证理由字段的豁免）。
    """
    ov = overrides if overrides is not None else load_wp_code_overrides()
    return "data_drift" if ov.get(wp_code) is not None else "out_of_scope"


def exempted_keys(
    path: Path | None = None,
    *,
    overrides: dict[str, str] | None = None,
    today: date | None = None,
) -> set[str]:
    """门禁便捷入口：返回**当前有效**（校验通过）的豁免 key 集合。

    只有这些 key 才允许从非 redirect 分母剔除；校验失败的 key 不进该集合，
    从而重新计入分母 → 门禁相应断言红。
    """
    valid: set[str] = set()
    for ex in load_exemptions(path):
        res = validate_exemption(ex, overrides=overrides, today=today)
        if res.valid:
            valid.add(ex.key)
    return valid
