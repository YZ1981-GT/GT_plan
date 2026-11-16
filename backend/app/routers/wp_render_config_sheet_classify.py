"""render-config 逐 sheet 路由判定的纯函数（spec platform-global-display-settings-closure 6A / design §18 H1①）。

从 `wp_render_config._get_render_config_impl` 里把「`_real_sheets` 计算 + 逐 sheet
componentType 派生」抽成**同步纯函数**，目的有三：

1. **可被离线工具复用**：`scripts/analyze/render_schema_measure_audit.py` 要在不连库、
   不启动应用的前提下算出每个 render schema 的 `reached_by`（哪些 wp_code/sheet 会
   真的走到它）。不抽出来就只能靠 `git grep` 猜，判据会随实现漂移。
2. **可表驱动测试**：`tests/test_render_sheet_classify.py` 直接给输入断言输出，
   不需要构造 AsyncSession / 项目数据。
3. **`wp_render_config.py` 瘦身**：该文件在行数门白名单上（基线 1135，+5% 上限约 1191），
   白名单注释写明的拆分方向就是本模块。

🔴 判定口径与 router 内**逐字一致**（不是重新设计）：`_real_sheets` 的四条过滤、
`_is_multi_sheet` 的阈值、`_sheet_ovr` 的三级回退、`pkg_sheets and ovr` 分支里
`B-` 前缀保留 `b-index`、`G-` class_code 强制 OnlyOffice 的例外条件。
改动这里等于改生产行为，必须同步改 router 与表驱动用例。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

#: sheet 名尾部编码（与 `wp_render_config._SHEET_CODE_RE` 同一条正则）。
SHEET_CODE_RE = re.compile(r"([A-Z]\d+(?:-\d+)*[A-Z]?)(?:-新增)?\s*$")

#: 开头的裸编码（用于「编码在开头」的补充匹配，如 `C1-4-4企业层面…`）。
LEADING_CODE_RE = re.compile(r"([A-Z]\d+(?:-\d+)*)")

#: 强制 OnlyOffice 的 class_code 前缀。
ONLYOFFICE_CLASS_PREFIX = "G-"

#: 合成底稿目录的 class_code 前缀（保留原生 b-index 渲染）。
INDEX_CLASS_PREFIX = "B-"


@dataclass(frozen=True)
class SheetRoute:
    """一个 sheet 的路由判定结果（纯数据，不含 renderer / html_data）。"""

    sheet_name: str
    component_type: str
    #: 判定依据，便于表驱动用例与离线审计解释来源
    reason: Literal[
        "sheet_override",
        "whole_wp_dedicated",
        "package_sheets",
        "package_sheets_b_index",
        "derived",
        "single_sheet_override",
        "derived_single",
        "g_prefix_onlyoffice",
        "classification_missing",
    ]
    #: 命中的 sheet 级 override（None 表示未命中）
    sheet_override: str | None = None


def is_multi_sheet(real_sheets: list[Any]) -> bool:
    """`_real_sheets` 多于一个即多 sheet（与 router 内 `len(...) > 1` 逐字一致）。"""
    return len(real_sheets) > 1


def compute_real_sheets(
    classifications: list[Any],
    *,
    wp_code_override: dict[str, Any],
) -> list[Any]:
    """算出 `_real_sheets`：与 router 内四条过滤逐字一致。

    过滤项（按 router 顺序）：
    1. sheet 名含 `GT_Custom`；
    2. `class_code` 以 `I-` 开头；
    3. `_WP_CODE_OVERRIDE[sheet_name] == "skip"`；
    4. sheet 名以 `-原版` / `-原` 结尾。
    """
    result = []
    for c in classifications:
        sheet_name = getattr(c, "sheet_name", None)
        class_code = getattr(c, "class_code", "") or ""
        if sheet_name and "GT_Custom" in sheet_name:
            continue
        if class_code.startswith("I-"):
            continue
        if sheet_name and wp_code_override.get(sheet_name) == "skip":
            continue
        if sheet_name and (sheet_name.endswith("-原版") or sheet_name.endswith("-原")):
            continue
        result.append(c)
    return result


def resolve_sheet_override(
    sheet_name: str | None,
    *,
    is_multi: bool,
    wp_code: str | None,
    wp_code_override: dict[str, Any],
) -> str | None:
    """`_sheet_ovr` 的三级回退（与 router 逐字一致）。

    1. sheet 名尾部编码（`SHEET_CODE_RE`）；
    2. 完整 sheet 名（如「函证差异检查表（示例）」无尾部编码）；
    3. `{wp_code}-{sheet_name}`（G/F 等循环附注页，如 `G1-附注披露信息（上市公司）`）。

    非多 sheet 时恒返回 None（router 里 `_sheet_ovr` 只在 `_is_multi_sheet` 分支计算）。
    """
    if not is_multi or not sheet_name:
        return None
    m = SHEET_CODE_RE.search(sheet_name)
    if m:
        found = wp_code_override.get(m.group(1))
        if found:
            return found
    found = wp_code_override.get(sheet_name)
    if found:
        return found
    if wp_code:
        found = wp_code_override.get(f"{wp_code}-{sheet_name}")
        if found:
            return found
    return None


def classify_sheet(
    *,
    sheet_name: str | None,
    class_code: str,
    is_multi: bool,
    wp_code_override_value: str | None,
    sheet_override: str | None,
    whole_wp_dedicated: frozenset[str] | set[str],
    has_package_sheets: bool,
    derive_component_type: Any,
    ignore_wp_code_override_deriver: Any,
) -> SheetRoute:
    """单 sheet 的 componentType 判定（与 router 内嵌套 try/if 链逐字一致）。

    两个 `deriver` 是**函数**（不是结果），因为 router 的派生在异常时要退回
    `ovr` / `"skip"`，需要现场调用。

    `derive_component_type(cls)` 与 `derive_component_type(cls, ignore_wp_code_override=True)`
    是两个不同调用口径，所以分开传入，避免在这里猜。
    """
    name = sheet_name or ""
    ovr = wp_code_override_value

    if is_multi:
        if sheet_override:
            return SheetRoute(name, sheet_override, "sheet_override", sheet_override)
        if ovr and ovr in whole_wp_dedicated:
            return SheetRoute(name, ovr, "whole_wp_dedicated", sheet_override)
        if has_package_sheets and ovr:
            # pkg_sheets 模式：合成底稿目录（`B-` 前缀）保留原生 b-index
            if class_code[:2] == INDEX_CLASS_PREFIX:
                try:
                    component = ignore_wp_code_override_deriver()
                except Exception:  # noqa: BLE001 — 与 router 的 ClassificationNotFoundError 同效
                    component = "b-index"
                return SheetRoute(name, component, "package_sheets_b_index", sheet_override)
            return SheetRoute(name, ovr, "package_sheets", sheet_override)
        try:
            component = ignore_wp_code_override_deriver()
            return SheetRoute(name, component, "derived", sheet_override)
        except Exception:  # noqa: BLE001
            return SheetRoute(
                name, ovr or "skip", "classification_missing", sheet_override,
            )

    # 单 sheet：wp_code override 优先
    if ovr:
        return SheetRoute(name, ovr, "single_sheet_override", sheet_override)
    try:
        component = derive_component_type()
        return SheetRoute(name, component, "derived_single", sheet_override)
    except Exception:  # noqa: BLE001
        return SheetRoute(name, "skip", "classification_missing", sheet_override)


def apply_g_prefix_onlyoffice(
    route: SheetRoute,
    *,
    class_code: str,
    is_multi: bool,
    wp_code_override_value: str | None,
) -> SheetRoute:
    """`G-` 前缀 class_code 强制 OnlyOffice（与 router 的例外条件逐字一致）。

    例外（保持原 componentType）：sheet 级 override 已命中；或整册 wp_code
    override 已路由到专属 HTML 组件（`component_type == ovr`）。
    """
    if (
        is_multi
        and class_code.startswith(ONLYOFFICE_CLASS_PREFIX)
        and not route.sheet_override
        and not (wp_code_override_value and route.component_type == wp_code_override_value)
    ):
        return SheetRoute(
            route.sheet_name, "onlyoffice-sheet", "g_prefix_onlyoffice", route.sheet_override,
        )
    return route
