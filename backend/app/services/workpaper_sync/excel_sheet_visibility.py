"""受管 xlsx 的 sheet 可见性 —— **zip 级外科手术**，只改 `xl/workbook.xml`。

## 为什么必须是 zip 级（2026-09-03 实测，K11 模板）

原实现 `wp_onlyoffice_router._hide_non_target_sheets` 用 openpyxl
`load_workbook()` + `wb.save()` 全量重写。openpyxl 只理解它自己建模的那部分
OOXML，其余一律丢弃或重排。K11（`审定表K11-1` 等 7 张 sheet）实测 before→after：

| 项 | before | after | 后果 |
|---|---|---|---|
| zip 部件数 | 37 | **19** | 丢 20 个（见下） |
| 缓存值 `<v>` | 716 | **478** | 且余下的变成空标签 `<v></v>` |
| 共享公式主格 | 12 | **0** | 整组被展开成独立公式 |
| `calcChain.xml` | 有 | **无** | 计算链丢失 |
| 文件大小 | 58,013 | 38,116 | 缩 34% |

丢失的 20 个部件按类别：

* `xl/printerSettings/printerSettings1..7.bin`（**7 个**）
  —— 审计底稿要按原样打印归档，纸型/缩放/页边距全丢。
* `xl/worksheets/_rels/sheet{1,3,4,5,6,7}.xml.rels`（**6 个**）
  —— sheet 级关系表，超链接 / 打印设置 / 批注的关联全断。
* `xl/sharedStrings.xml` —— 被改写成 inline 字符串。
* `xl/comments1.xml` + `xl/drawings/vmlDrawing1.vml` —— 批注被换成另一种形态。
* `customXml/item1.xml` + 两个伴生件 —— 自定义 XML 数据。
* `xl/calcChain.xml` —— 可再生，是唯一无害的一项。

单元格级毁坏样本（`审定表K11-1`）::

    before  <c r="B26" s="94"><f t="shared" ref="B26:G26" si="3">SUM(B7:B25)</f><v>0</v></c>
    after   <c r="B26" s="218"><f>SUM(B7:B25)</f><v></v></c>
                        ↑样式索引全表重排        ↑共享组展开   ↑空缓存值

    before  <c r="H9" s="95"><f t="shared" si="1"/><v>0</v></c>
    after   <c r="H9" s="219"><f>G9-D9</f><v></v></c>

`<v></v>` 空缓存值比"丢失"更糟：Excel 读到空值直接显示 0，而不是触发重算。
样式索引 94→218 是因为 openpyxl 重建了整张 `styles.xml`。

而 `excel_materialize.select_write_strategy` 早已判定「生产上没有一个模板能
通过 openpyxl 这道门」（351 个模板 182 个含 drawing）—— 隐藏 sheet 这条路径
**绕过了那道门**，且每次切换 sheet 都跑一次。

## 隐藏本身无害，实现方式才有害

Excel / OnlyOffice 里**隐藏的 sheet 照样参与计算**，跨 sheet 引用
（`'明细表K11-2'!F29`，实测 351 个模板里 188 份有、共 81,955 处）指向隐藏
sheet 完全正常。所以本模块保留「只显示目标 tab」的既有行为，只把实现换成
「除 `xl/workbook.xml` 外一个字节都不动」。

## 自检是结构性的，不是靠人记得

:func:`_assert_only_workbook_part_changed` 在每次产出新字节后逐部件比对：
部件集合必须逐位相等、除 `xl/workbook.xml` 外每个部件的字节必须逐字相等。
任何人日后把实现换回 openpyxl（或引入别的全量重写）都会当场抛错，而不是
静默少 20 个部件 —— 这是让该类缺陷无法再无声复发的唯一办法。
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Sequence
from xml.sax.saxutils import unescape as xml_unescape

from app.services.workpaper_sync.models import SyncDomainError

__all__ = [
    "SheetVisibilityError",
    "SheetVisibilityPartSetChangedError",
    "SheetVisibilityPartMutatedError",
    "SheetVisibilityWorkbookPartMissingError",
    "SheetVisibilityNoVisibleSheetError",
    "SheetEntry",
    "VisibilityOutcome",
    "WORKBOOK_PART",
    "read_sheet_entries",
    "read_workbook_part",
    "resolve_target_sheet",
    "plan_single_sheet_visibility",
    "plan_all_sheets_visible",
    "plan_restore_workbook_part",
    "apply_single_sheet_visibility",
    "restore_all_sheets_visible",
    "restore_workbook_part_from_source",
    "assert_only_workbook_part_changed",
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常 —— 一条禁令一个类型一个 error_code
# ═══════════════════════════════════════════════════════════════════════════


class SheetVisibilityError(SyncDomainError):
    """sheet 可见性改写的基类。"""

    error_code = "excel_sheet_visibility_error"


class SheetVisibilityWorkbookPartMissingError(SheetVisibilityError):
    """zip 里没有 `xl/workbook.xml` —— 不是一个 OOXML workbook。"""

    error_code = "excel_sheet_visibility_workbook_part_missing"


class SheetVisibilityPartSetChangedError(SheetVisibilityError):
    """产出的 zip 部件集合与输入不同 —— 有部件被丢弃或新增。"""

    error_code = "excel_sheet_visibility_part_set_changed"


class SheetVisibilityPartMutatedError(SheetVisibilityError):
    """`xl/workbook.xml` 之外的某个部件字节被改动。"""

    error_code = "excel_sheet_visibility_part_mutated"


class SheetVisibilityNoVisibleSheetError(SheetVisibilityError):
    """改写后没有任何可见 sheet —— 这样的 xlsx 打不开。"""

    error_code = "excel_sheet_visibility_no_visible_sheet"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 常量与低层解析
# ═══════════════════════════════════════════════════════════════════════════

WORKBOOK_PART: Final[str] = "xl/workbook.xml"

#: `<sheets>` 容器（`<sheet>` 只能出现在它里面，避免误伤 `<definedNames>` 等）。
_SHEETS_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"(?P<open><sheets\b[^>]*>)(?P<body>.*?)(?P<close></sheets>)", re.S
)

#: 单个 `<sheet>` 元素（自闭合或成对，两种形态都合法）。
_SHEET_EL_RE: Final[re.Pattern[str]] = re.compile(
    r"<sheet\b(?P<attrs>[^>]*?)(?:/>|>\s*</sheet>)"
)

#: `<workbookView>`，`activeTab` / `firstSheet` 在这里。
_WORKBOOK_VIEW_RE: Final[re.Pattern[str]] = re.compile(
    r"<workbookView\b(?P<attrs>[^>]*?)/>"
)

#: OOXML 的 sheet 可见性取值。`visible` 是默认值，通常整个属性被省略。
_STATE_VISIBLE: Final[str] = "visible"
_STATE_HIDDEN: Final[str] = "hidden"


def _get_attr(attrs: str, name: str) -> str | None:
    found = re.search(rf'\b{re.escape(name)}="([^"]*)"', attrs)
    return found.group(1) if found else None


def _set_attr(attrs: str, name: str, value: str) -> str:
    pattern = re.compile(rf'(\b{re.escape(name)}=")[^"]*(")')
    if pattern.search(attrs):
        return pattern.sub(lambda m: f"{m.group(1)}{value}{m.group(2)}", attrs, count=1)
    # 追加到末尾，保持原有属性顺序不动（顺序变化虽语义等价，但会让 diff 失真）
    return f"{attrs.rstrip()} {name}=\"{value}\""


def _del_attr(attrs: str, name: str) -> str:
    return re.sub(rf'\s*\b{re.escape(name)}="[^"]*"', "", attrs, count=1)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 只读观测
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SheetEntry:
    """`xl/workbook.xml` 的 `<sheets>` 里的一条，按文档顺序。"""

    index: int
    name: str
    state: str
    sheet_id: str = ""

    @property
    def is_visible(self) -> bool:
        return self.state == _STATE_VISIBLE


@dataclass(frozen=True)
class VisibilityOutcome:
    """一次可见性改写的结果。`changed=False` 时**磁盘未被触碰**。"""

    changed: bool
    target_sheet: str | None
    visible: tuple[str, ...]
    hidden: tuple[str, ...]
    active_tab: int | None
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "changed": self.changed,
            "target_sheet": self.target_sheet,
            "visible": list(self.visible),
            "hidden": list(self.hidden),
            "active_tab": self.active_tab,
            "reason": self.reason,
        }


def _parse_sheet_entries(workbook_xml: str) -> tuple[SheetEntry, ...]:
    block = _SHEETS_BLOCK_RE.search(workbook_xml)
    if block is None:
        return ()
    entries: list[SheetEntry] = []
    for index, element in enumerate(_SHEET_EL_RE.finditer(block.group("body"))):
        attrs = element.group("attrs") or ""
        raw_name = _get_attr(attrs, "name") or ""
        entries.append(
            SheetEntry(
                index=index,
                name=xml_unescape(raw_name, {"&quot;": '"', "&apos;": "'"}),
                state=(_get_attr(attrs, "state") or _STATE_VISIBLE),
                sheet_id=_get_attr(attrs, "sheetId") or "",
            )
        )
    return tuple(entries)


def read_sheet_entries(path: Path | str) -> tuple[SheetEntry, ...]:
    """只读地列出 sheet 名与可见性（按文档顺序）。不改磁盘。"""
    with zipfile.ZipFile(str(path)) as zf:
        if WORKBOOK_PART not in zf.namelist():
            raise SheetVisibilityWorkbookPartMissingError(
                f"{path} 里没有 {WORKBOOK_PART} —— 不是一个 OOXML workbook"
            )
        return _parse_sheet_entries(zf.read(WORKBOOK_PART).decode("utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# 4. 目标 sheet 解析 —— 规则与原 router 实现逐条一致
# ═══════════════════════════════════════════════════════════════════════════


def resolve_target_sheet(names: Sequence[str], target: str) -> str | None:
    """按「精确 → 包含 / 后缀」解析目标 sheet 名；解析不到返回 None。

    🔴 规则**刻意与原 `_hide_non_target_sheets` 逐条一致**（精确匹配优先，
    否则 `target in title or title.endswith(target)`，取第一个命中）。
    `backend/tests/workpaper_sync/test_task54_l_cycle_migration.py` 的
    `_router_matches` 复刻了这套规则并现读源码交叉锁死；本次只换实现不动语义，
    所以匹配规则一个字也不能改 —— 否则 L 循环的 sheet 落位判据会整片失真。
    """
    if not target:
        return None
    for name in names:
        if name == target:
            return name
    for name in names:
        if target in name or name.endswith(target):
            return name
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 5. 纯函数：算出新的 workbook.xml
# ═══════════════════════════════════════════════════════════════════════════


def _render_sheets(
    workbook_xml: str, *, desired: Mapping[int, str], active_tab: int | None
) -> str:
    """按 `desired`（索引 -> state）重写 `<sheets>`，并可选设置 `activeTab`。"""
    block = _SHEETS_BLOCK_RE.search(workbook_xml)
    if block is None:
        return workbook_xml

    body = block.group("body")
    out: list[str] = []
    cursor = 0
    for index, element in enumerate(_SHEET_EL_RE.finditer(body)):
        out.append(body[cursor : element.start()])
        cursor = element.end()
        attrs = element.group("attrs") or ""
        state = desired.get(index)
        if state == _STATE_VISIBLE:
            # 默认值 ⇒ 省略属性，回到 Excel 自己的写法
            attrs = _del_attr(attrs, "state")
        elif state is not None:
            attrs = _set_attr(attrs, "state", state)
        out.append(f"<sheet{attrs}/>")
    out.append(body[cursor:])

    new_body = "".join(out)
    rebuilt = (
        workbook_xml[: block.start()]
        + block.group("open")
        + new_body
        + block.group("close")
        + workbook_xml[block.end() :]
    )

    if active_tab is None:
        return rebuilt

    def _view(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        attrs = _set_attr(attrs, "activeTab", str(active_tab))
        # `firstSheet` 是 tab 栏最左侧的 sheet。它大于 activeTab 时某些阅读器
        # 会显示一条空 tab 栏，故向下夹紧；小于时不动（最小改动）。
        first = _get_attr(attrs, "firstSheet")
        if first is not None and first.isdigit() and int(first) > active_tab:
            attrs = _set_attr(attrs, "firstSheet", str(active_tab))
        return f"<workbookView{attrs}/>"

    return _WORKBOOK_VIEW_RE.sub(_view, rebuilt, count=1)


def plan_single_sheet_visibility(
    workbook_xml: str, target: str
) -> tuple[str, VisibilityOutcome]:
    """只让 `target` 可见、其余隐藏，并把它设为活动 sheet。**纯函数**。

    Returns:
        `(新 workbook.xml, outcome)`。`outcome.changed=False` 表示已是期望状态，
        调用方**不得**落盘（写盘会无谓轮转 mtime）。
    """
    entries = _parse_sheet_entries(workbook_xml)
    if len(entries) <= 1:
        return workbook_xml, VisibilityOutcome(
            changed=False,
            target_sheet=entries[0].name if entries else None,
            visible=tuple(e.name for e in entries if e.is_visible),
            hidden=tuple(e.name for e in entries if not e.is_visible),
            active_tab=None,
            reason="single_sheet_workbook",
        )

    resolved = resolve_target_sheet([e.name for e in entries], target)
    if resolved is None:
        # 安全降级：匹配不到就一个字节都不动（与原实现一致）
        return workbook_xml, VisibilityOutcome(
            changed=False,
            target_sheet=None,
            visible=tuple(e.name for e in entries if e.is_visible),
            hidden=tuple(e.name for e in entries if not e.is_visible),
            active_tab=None,
            reason="target_not_matched",
        )

    target_entry = next(e for e in entries if e.name == resolved)
    desired = {
        e.index: (_STATE_VISIBLE if e.index == target_entry.index else _STATE_HIDDEN)
        for e in entries
    }
    if not any(state == _STATE_VISIBLE for state in desired.values()):
        raise SheetVisibilityNoVisibleSheetError(
            "改写后没有任何可见 sheet —— 这样的 xlsx 打不开"
        )

    current_view = _WORKBOOK_VIEW_RE.search(workbook_xml)
    current_active = (
        _get_attr(current_view.group("attrs") or "", "activeTab")
        if current_view
        else None
    )
    already = all(
        entry.state == desired[entry.index] for entry in entries
    ) and (current_active or "0") == str(target_entry.index)

    outcome_visible = (resolved,)
    outcome_hidden = tuple(e.name for e in entries if e.index != target_entry.index)

    if already:
        return workbook_xml, VisibilityOutcome(
            changed=False,
            target_sheet=resolved,
            visible=outcome_visible,
            hidden=outcome_hidden,
            active_tab=target_entry.index,
            reason="already_in_desired_state",
        )

    rebuilt = _render_sheets(
        workbook_xml, desired=desired, active_tab=target_entry.index
    )
    return rebuilt, VisibilityOutcome(
        changed=True,
        target_sheet=resolved,
        visible=outcome_visible,
        hidden=outcome_hidden,
        active_tab=target_entry.index,
        reason="visibility_rewritten",
    )


def plan_restore_workbook_part(
    workbook_xml: str, source_workbook_xml: str
) -> tuple[str, VisibilityOutcome]:
    """把 `xl/workbook.xml` 的**可见性与视图状态**还原成源模板的样子。**纯函数**。

    ## 为什么需要它（spec excel-template-override-layer Task 16）

    模板编辑会话为了让审计师看到全部 sheet，会先把工作副本改成「全部可见」。若保存时
    照原样落盘，覆盖版本的 sheet 可见性就跟权威模板**不一样**了 —— 权威模板刻意隐藏的
    sheet 会在覆盖版本里变可见。那是内容之外的语义漂移，用户没要求过。

    ## 两条分支

    * **sheet 名序列完全相同**（用户没增删 sheet）⇒ 直接把整个 `workbook.xml` 换回源版本。
      这样可见性、`activeTab`、`firstSheet`、`definedNames` 等一切非内容状态都精确还原，
      比逐属性还原更可靠。
    * **序列不同**（用户增删了 sheet）⇒ 不能整体换回（会丢掉新 sheet 的 `<sheet>` 条目与
      `r:id` 引用）。此时按 sheet **名字**匹配还原可见性；源里没有的新 sheet 保持现状。
      按名字而不是索引 —— 增删 sheet 会让索引全部错位。
    """
    current = _parse_sheet_entries(workbook_xml)
    source = _parse_sheet_entries(source_workbook_xml)

    current_names = tuple(e.name for e in current)
    source_names = tuple(e.name for e in source)

    if current_names == source_names:
        changed = workbook_xml != source_workbook_xml
        return source_workbook_xml, VisibilityOutcome(
            changed=changed,
            target_sheet=None,
            visible=tuple(e.name for e in source if e.is_visible),
            hidden=tuple(e.name for e in source if not e.is_visible),
            active_tab=None,
            reason="restored_from_source" if changed else "already_identical",
        )

    source_state = {e.name: e.state for e in source}
    desired: dict[int, str] = {}
    for entry in current:
        want = source_state.get(entry.name)
        if want is not None and want != entry.state:
            desired[entry.index] = want

    if not desired:
        return workbook_xml, VisibilityOutcome(
            changed=False,
            target_sheet=None,
            visible=tuple(e.name for e in current if e.is_visible),
            hidden=tuple(e.name for e in current if not e.is_visible),
            active_tab=None,
            reason="sheet_set_changed_no_visibility_diff",
        )

    rendered = _render_sheets(workbook_xml, desired=desired, active_tab=None)
    after = _parse_sheet_entries(rendered)
    if not any(e.is_visible for e in after):
        raise SheetVisibilityNoVisibleSheetError(
            "还原源可见性后没有任何可见 sheet —— 这样的 xlsx 打不开"
        )
    return rendered, VisibilityOutcome(
        changed=True,
        target_sheet=None,
        visible=tuple(e.name for e in after if e.is_visible),
        hidden=tuple(e.name for e in after if not e.is_visible),
        active_tab=None,
        reason="sheet_set_changed_visibility_restored_by_name",
    )


def restore_workbook_part_from_source(
    path: Path | str, source_workbook_xml: str
) -> VisibilityOutcome:
    """:func:`plan_restore_workbook_part` 的落盘版（幂等，无变化不落盘）。"""

    def _planner(workbook_xml: str) -> tuple[str, VisibilityOutcome]:
        return plan_restore_workbook_part(workbook_xml, source_workbook_xml)

    return _apply(Path(path), _planner)


def read_workbook_part(path: Path | str) -> str:
    """只读地取出 `xl/workbook.xml` 全文（供会话开始时记录源状态）。"""
    with zipfile.ZipFile(str(path)) as zf:
        if WORKBOOK_PART not in zf.namelist():
            raise SheetVisibilityWorkbookPartMissingError(
                f"{path} 里没有 {WORKBOOK_PART} —— 不是一个 OOXML workbook"
            )
        return zf.read(WORKBOOK_PART).decode("utf-8")


def plan_all_sheets_visible(workbook_xml: str) -> tuple[str, VisibilityOutcome]:
    """把全部 sheet 恢复可见（「完整 Excel」页签用）。**纯函数**。

    🔴 只碰**本模块自己隐藏过的那类** sheet 是做不到的（`workbook.xml` 里没有
    "谁隐藏了它"的记录），所以这里与原 `_ensure_all_sheets_visible` 一样把全部
    sheet 置为可见。源模板里本来就 hidden 的 sheet（如 `GT_Custom`、
    `_GT_SYNC`）因此也会露出来 —— 这是原有行为，本次不改语义。
    """
    entries = _parse_sheet_entries(workbook_xml)
    if not entries or all(e.is_visible for e in entries):
        return workbook_xml, VisibilityOutcome(
            changed=False,
            target_sheet=None,
            visible=tuple(e.name for e in entries),
            hidden=(),
            active_tab=None,
            reason="already_all_visible",
        )
    desired = {e.index: _STATE_VISIBLE for e in entries}
    rebuilt = _render_sheets(workbook_xml, desired=desired, active_tab=None)
    return rebuilt, VisibilityOutcome(
        changed=True,
        target_sheet=None,
        visible=tuple(e.name for e in entries),
        hidden=(),
        active_tab=None,
        reason="all_sheets_restored",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. zip 重写 + 结构性自检
# ═══════════════════════════════════════════════════════════════════════════


def _replace_workbook_part(data: bytes, new_workbook_xml: bytes) -> bytes:
    """只替换 `xl/workbook.xml`，其余部件连 `ZipInfo` 一起原样搬过去。

    保留每个部件的 `date_time` / `compress_type` / 属性位，让"除 workbook.xml
    外一个字节都没动"这句话在 zip 元数据层面也成立。
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        infos = src.infolist()
        with zipfile.ZipFile(buf, "w") as out:
            for info in infos:
                payload = src.read(info.filename)
                if info.filename == WORKBOOK_PART:
                    payload = new_workbook_xml
                clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                clone.compress_type = info.compress_type
                clone.external_attr = info.external_attr
                clone.internal_attr = info.internal_attr
                clone.create_system = info.create_system
                clone.flag_bits = info.flag_bits & ~0x08  # 不用 data descriptor
                out.writestr(clone, payload)
    return buf.getvalue()


def _assert_only_workbook_part_changed(before: bytes, after: bytes) -> None:
    """结构性自检：部件集合逐位相等 + 除 workbook.xml 外每个部件字节逐字相等。

    🔴 这道自检是本模块存在的**主要理由**。openpyxl 那版之所以能长期在生产路径上
    丢 20 个部件、把 12 个共享公式组展平、把缓存值写成 `<v></v>`，就是因为没有
    任何判据在看"除了我要改的那一处，别的动了没有"。日后谁把实现换回全量重写，
    这里会当场抛错。
    """
    with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(
        io.BytesIO(after)
    ) as b:
        names_before, names_after = a.namelist(), b.namelist()
        if names_before != names_after:
            lost = [n for n in names_before if n not in set(names_after)]
            gained = [n for n in names_after if n not in set(names_before)]
            raise SheetVisibilityPartSetChangedError(
                f"zip 部件集合变了：丢 {len(lost)} 个 {lost[:8]}、"
                f"多 {len(gained)} 个 {gained[:8]} —— sheet 可见性改写只许改 "
                f"{WORKBOOK_PART}"
            )
        for name in names_before:
            if name == WORKBOOK_PART:
                continue
            if a.read(name) != b.read(name):
                raise SheetVisibilityPartMutatedError(
                    f"部件 {name} 的字节被改动 —— sheet 可见性改写只许改 "
                    f"{WORKBOOK_PART}"
                )


#: 公开别名 —— 供别的模块复用这条结构性自检，而不是各写一份逐部件比对。
#:
#: spec excel-template-override-layer 的 Property 11（会话建立前后仅 workbook.xml 变）
#: 直接用它；design.md 明写「复用已交付的 `_assert_only_workbook_part_changed`」。
assert_only_workbook_part_changed = _assert_only_workbook_part_changed


def _apply(path: Path, planner) -> VisibilityOutcome:
    """读 → 规划 → （必要时）原子落盘 + 自检 的共同骨架。"""
    data = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if WORKBOOK_PART not in zf.namelist():
            raise SheetVisibilityWorkbookPartMissingError(
                f"{path.name} 里没有 {WORKBOOK_PART} —— 不是一个 OOXML workbook"
            )
        workbook_xml = zf.read(WORKBOOK_PART).decode("utf-8")

    rebuilt, outcome = planner(workbook_xml)
    if not outcome.changed:
        return outcome

    new_data = _replace_workbook_part(data, rebuilt.encode("utf-8"))
    _assert_only_workbook_part_changed(data, new_data)

    # 原子替换：新字节先落临时文件，成功才顶替。任何一步抛错，原文件完好无损。
    tmp = path.with_name(f"{path.name}.visibility.tmp")
    tmp.write_bytes(new_data)
    os.replace(tmp, path)
    return outcome


def apply_single_sheet_visibility(path: Path | str, target: str) -> VisibilityOutcome:
    """只让 `target` 可见、其余隐藏并置为活动 sheet。

    幂等：已是期望状态时**不落盘**（避免无谓轮转 mtime）。
    目标 sheet 匹配不到 / 单 sheet workbook 时同样不落盘（安全降级）。
    """
    return _apply(
        Path(path), lambda xml: plan_single_sheet_visibility(xml, target)
    )


def restore_all_sheets_visible(path: Path | str) -> VisibilityOutcome:
    """把全部 sheet 恢复可见（幂等，无变化不落盘）。"""
    return _apply(Path(path), plan_all_sheets_visible)
