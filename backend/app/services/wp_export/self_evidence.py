"""底稿导出产物自证 — 单一真源（workpaper-import-export-lifecycle-closure Task 4）

## 为什么需要这个模块

用户反馈「导出的很多模板都是空的」。实证后确认这是**两个独立缺陷叠加**，而本模块
是止损层：让空产物**自证**，而不是伪装成「这份底稿内容本来就空」。

改造前用户拿到一份空白 xlsx 时，无从判断到底是：

- 底稿文件压根不存在（回退了模板库）
- 文件在、但结构化录入没写进 xlsx
- 这份底稿确实还没人填

三种情形的处置动作完全不同，而产物里一个字都没说。

## 四档语义（`SelfEvidenceKind` + `None`）

| kind                | 触发条件                                                          | 用户该做什么             |
|---------------------|-------------------------------------------------------------------|--------------------------|
| `verdict`           | `resolve_wp_file` 返回 `verdict != 'file'`                        | 看 `VERDICT_LABELS` 原因 |
| `html_data_absent`  | `verdict == 'file'` 但 `html_data` 空 / 缺该 sheet 键             | 打开底稿保存一次         |
| `entry_not_in_xlsx` | `verdict == 'file'` + `html_data` 空 + `checklist_responses` 有行 | 录入在库里但没落 xlsx    |
| `None`              | `verdict == 'file'` + `html_data` 非空                            | 正常导出，**零噪声**     |

### 为什么 `entry_not_in_xlsx` 必须独立成档

真实库实测（2026-08-10，2802 份未软删底稿）：

- 有 `checklist_responses` 行的底稿 **131 份**
- `parsed_data.html_data` 非空的底稿 **73 份**
- **两集合交集仅 5 份**

也就是说，绝大多数「有录入」的底稿走的正是这一档 —— 文件在、`verdict='file'`、
但 `_sync_export_workpaper_xlsx` 只读 `html_data`，那 131 份里 126 份的 `html_data`
键根本不存在 ⇒ 模板被原样另存 ⇒ 用户看到空模板。

把它和 `html_data_absent` 合并会给出**错误的处置建议**：后者提示「打开底稿保存
一次」是有效的（保存会写 `html_data`），前者的数据其实已经在库里了，提示应指向
「导出未包含结构化录入」这条真实原因。

## 🔴 R1.6：正常导出零噪声

`needs_self_evidence` 在正常态**必须**返 `None`，调用方据此完全跳过自证。给正常
导出加 banner 会污染每一份产物，且让「自证」这件事失去信噪比。

判据抽成纯函数正是为了让守卫能直测这一点，不必造 workbook。

## 设计约束

- **纯同步、无 DB、无 ORM 依赖** —— 与 `wp_file_resolver` 同款，便于异步下载路径
  与同步 render 路径共用，也便于守卫直接单测。
- **文案只有两个真源**：`VERDICT_LABELS`（verdict 档）+ 本模块 `_KIND_LABELS`
  （其余两档）。调用方一律不得硬写中文（R1.3，守卫扫源码钉死）。
- **落盘范式复用** `export_engine._build_failure_fallback_workbook`：
  第 1 行 banner（加粗标红）/ 第 2 行留空 / 第 3 行起数据。行号由
  `SELF_EVIDENCE_DATA_START_ROW` 单一常量提供，禁调用方各写一份（R1.7）。
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from openpyxl.styles import Font

from app.services.wp_export.wp_file_resolver import VERDICT_LABELS

logger = logging.getLogger(__name__)

# ─── 自证档位 ────────────────────────────────────────────────────────────────

SelfEvidenceKind = Literal[
    "verdict",
    "html_data_absent",
    "entry_not_in_xlsx",
]

#: 档位取值域（守卫按它断言，禁止在调用方硬写字面量）
SELF_EVIDENCE_KINDS: tuple[SelfEvidenceKind, ...] = (
    "verdict",
    "html_data_absent",
    "entry_not_in_xlsx",
)

#: 🔴 非 verdict 档的中文文案 —— 唯一真源（verdict 档取 `VERDICT_LABELS`）。
#:
#: 两档文案必须**逐字不同**：它们对应的用户动作不同，合并会给出错误建议。
#: 守卫 `test_entry_not_in_xlsx_and_html_absent_labels_differ` 钉死这一点。
_KIND_LABELS: dict[str, str] = {
    "html_data_absent": (
        "录入内容未包含：本份底稿的结构化录入尚未写入 xlsx，"
        "请打开该底稿并保存一次后重新导出"
    ),
    "entry_not_in_xlsx": (
        "录入内容未包含：本份底稿已有录入记录存于系统内，但未随 xlsx 导出，"
        "请在底稿界面查看，或使用「导出数据」获取含录入内容的版本"
    ),
}

#: 自证 banner 固定占第 1 行、第 2 行留空 ⇒ 数据从第 3 行起。
#:
#: 🔴 这是**共享常量**而非各调用方自写的魔数：`_build_failure_fallback_workbook`
#: 已用同一范式（第 1 行原因 / 第 2 行空 / 第 3 行起数据），两处必须同源，
#: 否则将来有人改了一处，产物的数据区首行语义就会错位。
SELF_EVIDENCE_DATA_START_ROW = 3

#: banner 视觉标记（与 `_build_failure_fallback_workbook` 逐字同色）
_BANNER_COLOR = "C00000"

#: 空白模板的统一前缀短语（R1.1 判据：产物内必须含此字样）
_BLANK_TEMPLATE_PHRASE = "本份为空白模板"


# ─── 判定（纯函数，供守卫直测）──────────────────────────────────────────────


def needs_self_evidence(
    *,
    verdict: str,
    html_data: dict[str, Any] | None,
    has_entry_rows: bool,
    sheet_name: str | None = None,
) -> SelfEvidenceKind | None:
    """判定是否需要自证、以及属哪一档。

    这是本模块的**判据本体**。抽成纯函数（无 DB / 无 workbook）是为了让守卫
    能直接测四态，而不必造一整个导出流程 —— memory 铁律：判据要能被单测覆盖，
    否则只能靠「跑一遍看产物」，变异检验无从下手。

    Args:
        verdict: `resolve_wp_file` 的判定档位，取值 ⊆ `WP_FILE_VERDICTS`。
        html_data: `working_paper.parsed_data['html_data']`（可为 None）。
        has_entry_rows: 该底稿在 `checklist_responses` 是否有**非空**行。
            注意是「非空」——真实库 103.37 万行里仅 695 行非空，按「有行」判
            会让几乎所有底稿都落进 `entry_not_in_xlsx` 档。
        sheet_name: 若给定，则按「该 sheet 键是否存在且非空」判 `html_data`；
            不给则按「整个 `html_data` 是否非空」判。

    Returns:
        档位字符串，或 `None` 表示**正常导出、不加任何自证**（R1.6）。

    Examples:
        >>> needs_self_evidence(verdict="template_fallback", html_data={}, has_entry_rows=False)
        'verdict'
        >>> needs_self_evidence(verdict="file", html_data={"S": {"rows": [1]}}, has_entry_rows=True) is None
        True
    """
    # ─── 档 1：文件层面就不 OK（回退模板 / 无路径 / 文件丢失）───────────
    if verdict != "file":
        return "verdict"

    # ─── 判断 html_data 是否「有该 sheet 的内容」──────────────────────
    if sheet_name is not None:
        sheet_payload = (html_data or {}).get(sheet_name)
        html_ok = bool(sheet_payload)
    else:
        html_ok = bool(html_data)

    if html_ok:
        # 🔴 R1.6：正常导出零噪声。这条 return 是「不给正常产物加噪声」的唯一出口。
        return None

    # ─── 档 3 vs 档 2：库里有录入 ⇒ 语义是「未写进 xlsx」而非「没填过」──
    if has_entry_rows:
        return "entry_not_in_xlsx"
    return "html_data_absent"


# ─── 文案构造 ────────────────────────────────────────────────────────────────


def build_self_evidence_banner(
    *,
    kind: SelfEvidenceKind,
    verdict: str | None = None,
    detail: str = "",
) -> str:
    """产出自证首行文案。

    🔴 文案只取两个真源：`VERDICT_LABELS`（verdict 档）与 `_KIND_LABELS`（其余）。
    调用方一律不得硬写中文（R1.3，守卫扫调用方源码钉死）。

    Args:
        kind: 档位，取值 ⊆ `SELF_EVIDENCE_KINDS`。
        verdict: `kind == 'verdict'` 时必须给出，用于取 `VERDICT_LABELS` 原因。
        detail: 可选补充（如 file_path / sheet 名），拼在末尾括号内便于排查。

    Returns:
        单行中文文案。

    Raises:
        ValueError: kind 不在取值域内，或 verdict 档缺 verdict 实参。
            **有意 fail-fast**：文案缺失比抛异常更难排查（产物看着正常、
            实则少了自证），故这里不做静默降级。
    """
    if kind not in SELF_EVIDENCE_KINDS:
        raise ValueError(f"未知自证档位: {kind!r}，取值域={SELF_EVIDENCE_KINDS}")

    if kind == "verdict":
        if not verdict:
            raise ValueError("kind='verdict' 时必须提供 verdict 实参")
        reason = VERDICT_LABELS.get(verdict)
        if reason is None:
            raise ValueError(
                f"verdict={verdict!r} 不在 VERDICT_LABELS 内 —— "
                "新增 verdict 档需同步补文案真源"
            )
        banner = f"{_BLANK_TEMPLATE_PHRASE}：{reason}"
    else:
        banner = _KIND_LABELS[kind]

    if detail:
        banner = f"{banner}（{detail}）"
    return banner


# ─── 落盘 ────────────────────────────────────────────────────────────────────


def stamp_self_evidence(ws: Any, banner: str) -> None:
    """把 banner 写进 worksheet 第 1 行并加粗标红；第 2 行留空。

    复用 `export_engine._build_failure_fallback_workbook` 的既定范式
    （第 1 行原因 / 第 2 行留空 / 第 3 行起数据），使自证行**不占数据区首行
    语义**（R1.7）。调用方写数据时应从 `SELF_EVIDENCE_DATA_START_ROW` 起。

    Args:
        ws: openpyxl worksheet（用 `Any` 避免为类型注解引入重依赖）。
        banner: `build_self_evidence_banner` 的产出。

    Note:
        本函数**不**移动既有内容。对「模板另存」场景，调用方需自行决定是
        插入行还是另建 sheet —— 直接覆写模板第 1 行会吃掉模板表头。
        Task 5 的接线按「另建自证 sheet」处理带内容的模板。
    """
    cell = ws.cell(row=1, column=1, value=banner)
    cell.font = Font(bold=True, color=_BANNER_COLOR)
    # 第 2 行显式留空（模板可能原本有内容 ⇒ 必须主动清）
    ws.cell(row=2, column=1, value=None)


__all__ = [
    "SELF_EVIDENCE_DATA_START_ROW",
    "SELF_EVIDENCE_KINDS",
    "SelfEvidenceKind",
    "build_self_evidence_banner",
    "needs_self_evidence",
    "stamp_self_evidence",
]
