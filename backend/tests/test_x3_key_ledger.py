"""X-3 键三重对齐（GS1）+ 机制↔列推导（GS9 后端侧）守卫

spec: `x3-adjustment-entry-import-export` / **Wave 0 任务 1.1（判据先行）**

## 这个文件在守什么

16 张 X-3 调整分录汇总表（`L2-3` `L6-3` `M1-3`~`M10-3` `N1-3` `N2-3` `N3-3` `N5-3`）
接入三态导入导出时，最贵的一类假绿是「后端把键写死一份、清单写另一份，两边各自
自洽、守卫全绿、用户导入后界面读不到」。故本文件把两条不变量钉死：

| 守卫 | 不变量 | 判据形态 |
|---|---|---|
| **GS1** | `X3_SHEET_SPECS` 的 `item_id` / `storage_field` / `field_keys` == `adjustment_ie_contract.json` 登记值，且 `X3_SHEET_SPECS` 是**真的从清单装载**的 | 结构 + **真实装载行为** |
| **GS9 后端侧** | `storage_field == {formdata_setfield: conclusion, adjustment_savebatch: remark}[mechanism]`，逐张断言 | 清单内双向推导 |

## 🔴 类 A / 类 B 分离（Wave 0「先打红」设计，沿用父 spec `workpaper-import-export-lifecycle-closure` Wave 1 范式）

- **类 A**（`TestLedgerTruthSourceSelfCheck`）：独立口径自检，**当前应全绿**。
  它验的是判据基础设施本身没写错（清单可解析 / 三条铁律在位 / 豁免种类表非空 /
  扫描面 16 张非空 / 剥注释确实生效 / 字面量扫描器不会被 docstring 骗 /
  替身清单重定向确实生效）。**类 A 红 = 守卫自身有缺陷**，不是被测实现的问题。
- **类 B**（其余 class）：被测实现，**当前应全红**：
  - `_x3_adjustment_import_export.py` 尚不存在 ⇒ 红消息带「尚未实现（Wave 2 任务 4.1）」
  - 16 条尚未从 `exempt` 迁入 `sheets`（15 条 `kind=no_backend_spec`、`L6-3` 完全未登记）
    ⇒ 红消息带「尚未实现（Wave 1 任务 2.1）」

## 🔴 GS9 后端侧的判据边界（不许当成「机制已被证实」）

本文件的 `mechanism` **取清单登记值**，因此它只能抓出「清单内机制与列自相矛盾」
（例：登记 `adjustment_savebatch` 却写 `conclusion`）。它抓不出「清单把 N1-3 登记成
`adjustment_savebatch` + `remark`」这种**两处一起错**的情形 —— 那要靠**前端源码实测**
的机制探针，由任务 1.9（`x3KeyProbe.ts` + `adjustmentIeContract.spec.ts`）承担。
两侧合起来才是 design §GS9 的完整判据；单看本文件会高估覆盖面。

## 🔴 为什么「从清单装载」不能只 grep 源码有没有 `json.load`

`json.load` 存在 ≠ 装载结果被采用（同一模块里再写一份硬编码 dict 覆盖它，grep 照样绿）。
本文件的判据是**行为**：把清单内容重定向成替身（`storage_field` 与 `mechanism` 成对翻到
另一个合法取值），重新 exec 一份模块副本，`X3_SHEET_SPECS` 必须跟着变。跟着变 ⇒ 真装载；
不变 ⇒ 值另有出处（硬编码）。同时保留结构判据（剥注释后模块源码不得出现 X-3 键字面量），
两条一起才既抓「硬编码」也抓「装载了但不采用」。

## 🔴 剥注释必须配自检

`_x3_adjustment_import_export.py` 的 docstring 里几乎必然出现示例键（正是它要产出的东西），
不剥注释会让 docstring **冒充**硬编码而假红；剥过头（把普通字符串一起剥掉）又会漏检真
硬编码。故 `_strip_py_comments` 只剥 `#` 行注释与 docstring，并配
`test_strip_comments_actually_works` / `test_literal_scanner_ignores_docstring_examples`
两条反向自检（memory 铁律：没打红的守卫 = 守卫有缺陷）。
"""

from __future__ import annotations

import ast
import builtins
import importlib
import importlib.util
import io
import json
import re
import sys
import types
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

_BACKEND = Path(__file__).resolve().parents[1]

#: Key_Ledger 单一真源（design §C6）。绝对路径派生 ⇒ pytest 从仓库根跑也找得到
_LEDGER_PATH = _BACKEND / "data" / "adjustment_ie_contract.json"

#: Wave 2 任务 4.1 的交付物（共享实现，`X3_SHEET_SPECS` 的唯一出口）
_MODULE_NAME = "app.routers.wp_render_strategies._x3_adjustment_import_export"
_MODULE_PATH = (
    _BACKEND / "app" / "routers" / "wp_render_strategies" / "_x3_adjustment_import_export.py"
)

#: 统一的「尚未实现」文案前缀（便于变异检验按名归因，禁用 skip —— skip 在 CI 里是绿的）
_NOT_YET_LEDGER = "尚未实现（Wave 1 任务 2.1）"
_NOT_YET_MODULE = "尚未实现（Wave 2 任务 4.1）"

#: 本 spec 作业面 = 16 张（design 用户裁决 1：`N5-3` 纳入，零 pending_manual）
_X3_SHEETS: tuple[str, ...] = (
    "L2-3",
    "L6-3",
    "M1-3",
    "M2-3",
    "M3-3",
    "M4-3",
    "M5-3",
    "M6-3",
    "M7-3",
    "M8-3",
    "M9-3",
    "M10-3",
    "N1-3",
    "N2-3",
    "N3-3",
    "N5-3",
)

#: 机制 ⇒ 写入列（design E18 / §storage_field 机制归类，16/16 无例外）
#: ① `use{X}FormData.setField` → `saveField(itemId, { conclusion })` 恒 conclusion
#: ② `use{X}Adjustment` 的 `saveBatch` / `debouncedSave({ remark })` 恒 remark
_MECHANISM_TO_COLUMN: dict[str, str] = {
    "formdata_setfield": "conclusion",
    "adjustment_savebatch": "remark",
}

#: 机制分布（design §Data Models「16 张的键族与机制分布」登记值）
_MECHANISM_DISTRIBUTION: dict[str, int] = {
    "adjustment_savebatch": 12,  # L2-3 · L6-3 · M1-3 ~ M10-3
    "formdata_setfield": 4,  # N1-3 · N2-3 · N3-3 · N5-3
}

#: 写入键族（design §Data Models `KeyFamily`）；`none` 只作 read_family 取值
_WRITE_KEY_FAMILIES = frozenset({"single_json", "per_field", "per_field_plus_data"})

#: 源模板第 5 行列数（design §C1 `COLUMN_ORDER`）。`field_keys` 与之同序、10 项。
#: 🔴 design §D2 原写「`……`（F 列）在 16 张全部为占位……登记在 `column_map[5].gap`」，
#: 隐含前提「每张**恰 1 个**占位」。该前提已被任务 2.1 批次 1 实测推翻 ⇒ 本文件不再数
#: 占位个数，改判「**≥1 个占位，且每个占位位在同索引的 `column_map` 上都带非空 `gap`
#: 说明**」。推翻依据与新判据语义见下方「占位列（gap）判据」注释块。
#: 列面本体由任务 1.2（GS2）对 openpyxl 实读比对，本文件只用列数。
_COLUMN_COUNT = 10

#: 清单三条铁律（design §C6「三条铁律不动」/ R7.6）——(名称, 判据锚点)
_IRON_RULES: tuple[tuple[str, str], ...] = (
    ("对齐方向：后端 Sheet_Spec 向前端对齐", "向前端对齐"),
    ("不启用 dual_write（双写会形成第二真源）", "不启用 dual_write"),
    ("field_keys 是对齐完成后的期望值", "对齐完成后的期望值"),
)


# ═══════════════════════════════════════════════════════════════════════════
# 纯函数 helper（都配了类 A 反向自检；改这里必须同步看那些自检还红不红）
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=1)
def _ledger() -> dict[str, Any]:
    """读 Key_Ledger。进程级缓存 —— 物理变异清单后需新起 pytest 进程才生效。"""
    return json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))


def _ledger_sheets() -> dict[str, Any]:
    sheets = _ledger().get("sheets")
    return sheets if isinstance(sheets, dict) else {}


def _entry_or_fail(sheet: str) -> dict[str, Any]:
    """取某张 X-3 的清单条目；未迁入时 `fail` 并说清它现在在哪（不 skip）。"""
    entry = _ledger_sheets().get(sheet)
    if isinstance(entry, dict):
        return entry
    exempt = _ledger().get("exempt", {})
    cur = exempt.get(sheet)
    where = (
        f"当前在 exempt 段（kind={cur.get('kind')!r}）"
        if isinstance(cur, dict)
        else "当前在清单中完全无登记"
    )
    pytest.fail(
        f"{_NOT_YET_LEDGER}：{sheet} 尚未迁入 `sheets` 段 —— {where}。"
        f"任务 2.1 须把 16 条从 exempt 迁入 sheets（`L6-3` 为新登记），"
        f"并逐条写入 mechanism / key_family / key_families / column_map / provenance。"
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _derive_storage_field(mechanism: Any) -> str | None:
    """由持久化机制推导应有写入列（design E18）。未知机制返回 None。"""
    if not isinstance(mechanism, str):
        return None
    return _MECHANISM_TO_COLUMN.get(mechanism)


def _missing_iron_rules(doc: dict[str, Any]) -> list[str]:
    """返回清单中缺失的铁律名（判据锚点在 `_source` + `_iron_rules` 的合并文本里找）。"""
    blob_parts: list[str] = []
    src = doc.get("_source")
    if isinstance(src, str):
        blob_parts.append(src)
    rules = doc.get("_iron_rules")
    if isinstance(rules, list):
        blob_parts.extend(r for r in rules if isinstance(r, str))
    blob = "\n".join(blob_parts)
    return [name for name, anchor in _IRON_RULES if anchor not in blob]


def _strip_py_comments(source: str) -> str:
    """剥 `#` 行注释与 docstring，**保留**其余字符串字面量。

    只剥 docstring 是有意的：普通字符串字面量里可能是真的硬编码（正是要抓的），
    也可能是 `sa.text(\"\"\"SELECT ...\"\"\")` 这类 SQL（memory 已记「剥过头吃掉 SQL」的坑）。
    """
    lines = source.splitlines(keepends=True)
    try:
        tree: ast.AST | None = ast.parse(source)
    except SyntaxError:
        tree = None

    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
                and first.lineno is not None
                and first.end_lineno is not None
            ):
                for idx in range(first.lineno - 1, min(first.end_lineno, len(lines))):
                    lines[idx] = "\n"
        source = "".join(lines)

    out: list[str] = []
    for line in source.splitlines(keepends=True):
        in_s: str | None = None
        cut: int | None = None
        i = 0
        while i < len(line):
            ch = line[i]
            if in_s is None:
                if ch in ("'", '"'):
                    in_s = ch
                elif ch == "#":
                    cut = i
                    break
            else:
                if ch == "\\":
                    i += 2
                    continue
                if ch == in_s:
                    in_s = None
            i += 1
        out.append(line if cut is None else line[:cut].rstrip() + "\n")
    return "".join(out)


def _forbidden_x3_literals() -> tuple[str, ...]:
    """X-3 键字面量禁写清单：16 个 sheet 码 + 清单已登记的 item_id / 逐字段族前缀。

    不收 `per_field.suffixes`（`type` / `desc` / `ref` 等是通用英文词，收进来会误红）；
    也不收列标签（那是任务 1.2 / GS2 的作业面）。
    """
    out: set[str] = set(_X3_SHEETS)
    for sheet in _X3_SHEETS:
        entry = _ledger_sheets().get(sheet)
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("item_id")
        if isinstance(item_id, str) and item_id:
            out.add(item_id)
        families = entry.get("key_families")
        if isinstance(families, dict):
            for fam in families.values():
                if isinstance(fam, dict):
                    prefix = fam.get("prefix")
                    if isinstance(prefix, str) and len(prefix) >= 4:
                        out.add(prefix)
    return tuple(sorted(out))


def _literals_present_in_code(source: str, forbidden: tuple[str, ...]) -> list[str]:
    """剥注释后仍出现的禁写字面量（= 真硬编码）。"""
    code = _strip_py_comments(source)
    return [lit for lit in forbidden if lit in code]


def _spec_field(spec: Any, name: str) -> Any:
    """兼容 dataclass / 普通对象 / dict 三种 spec 载体取字段。"""
    if isinstance(spec, dict):
        return spec.get(name)
    return getattr(spec, name, None)


def _as_key_tuple(value: Any) -> tuple[Any, ...] | None:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 占位列（gap）判据 —— 🔴 design §D2「F 列唯一占位」前提已被实测推翻
# ═══════════════════════════════════════════════════════════════════════════
#
# design §D2 / R3.4 原文：「`……`（F 列）在 16 张全部为占位。……登记在 `column_map[5].gap`」
# ⇒ 隐含前提「每张恰 1 个占位」。任务 2.1 **批次 1 交付时实测推翻**：
#
#   · `L2-3` 实测 **2 个占位（F + J）**：J 列「备注」在 `useL2Adjustment.AdjustmentEntry`
#     里**无对应字段**、`normalizeEntry` 不接受该键、L2-3 界面表格亦无「备注」列（三重证据）。
#     ⇒ 旧断言对 L2-3 打红，是**判据前提错**，不是清单落错值。
#   · `N5-3` 行模型更精简，实测 B/C/E/I/J 五列均无对应字段 ⇒ 连同 F 列共 **6 个占位**
#     （批次 3 迁入时旧断言必然再红一次）。
#
# 🔴 已明确**不接受**的消红方式：给 J 列凭空登记 `remark`。那会新造前端键，且导入的备注
# 会在 `normalizeEntry` 处被静默丢弃 ⇒ 往返丢数据（违反「不新造前端键」与「禁止把错值锁
# 成基线」两条铁律）。
#
# 改判后的语义（**比旧判据更强**，不是放水 —— 旧判据只数个数，抓不到「不写 gap 理由就把
# 列留空」这种偷懒）：
#   ① 占位数 **≥ 1**：0 个 ⇒ 10 列全有前端字段，与源模板确实存在 `……` 列的事实矛盾，仍红；
#   ② `field_keys` 的空位集合与 `column_map[].field` 的空位集合**按同索引逐一相等** ——
#      这条挡住「`field_keys` 第 9 位空、`column_map` 第 5 位写 gap」的蒙混；
#   ③ 每个占位位的 `column_map[i].gap` 必须**非空且有实质内容**（判据见 `_gap_defect`）；
#   ④ `gap` 不许出现在**非**占位位（gap 是「此列为何无字段」的理由，写在有字段的列上属
#      登记错位，同样是双真源隐患）。
#
# 保留不动：`field_keys` 恰 `_COLUMN_COUNT` 项那条（列数与源模板第 5 行同势，无问题）。

#: `gap` 说明的实质性阈值。取值依据 = **实测两侧留足量级差**，故不会退化成空转：
#: · 已登记的 6 条真 gap 文本（L2-3 F/J · L6-3 F · M1-3 F · M2-3 F · M3-3 F）strip 后
#:   最短 **75** 字符、实义字符最少 **41** 种；
#: · 而 `""` / `"   "` / `-` / `—` / `?` / `.` / `N/A` / `TODO` / `TBD` / `xxx` / `无` /
#:   `待补` / `占位` / `（占位）`，以及它们的**重复填充**（`"待补"*6`、`"-"*20`、
#:   `"TODO TODO TODO TODO"`）与**纯数字填充**（`"1234567890123456"`），实义字符
#:   **最多 3 种**（重复填充能把长度撑过线，但撑不出种数）。
#: ⇒ 8 这条线离真值下界（41）与占位符上界（3）各有 5 倍量级余量：既不会对真说明误红，
#:   也不给任何占位符/填充文案放行。长度线 16 只作粗筛（真值 75 / 占位符裸值 ≤ 5）。
_GAP_MIN_LEN = 16
_GAP_MIN_DISTINCT = 8

#: 比对占位符黑名单前先剥掉的空白与标点（含全角）——`N/A` / `（占位）` / `todo!` 因此同样命中
_GAP_PUNCT = frozenset(" \t\r\n-—_.。、,，:：;；?？!！/\\|*+~`'\"()（）[]【】<>《》…·")

#: 明确不接受的占位符文案（比对时已小写化 + 剥标点空白）
_GAP_PLACEHOLDERS = frozenset(
    {
        "",
        "na",
        "nil",
        "none",
        "null",
        "todo",
        "tbd",
        "tba",
        "fixme",
        "xxx",
        "pending",
        "无",
        "略",
        "占位",
        "待补",
        "待补充",
        "同上",
        "见上",
        "暂无",
        "不适用",
    }
)


def _is_blank_key(value: Any) -> bool:
    """「无对应前端字段」判定：None / 空串 / 纯空白（`field_keys` 与 `column_map[].field` 同口径）。"""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _gap_text_norm(text: str) -> str:
    """小写化并剥空白/标点，使 `N/A`、`（占位）`、`todo!` 与黑名单可比。"""
    return "".join(ch for ch in text.lower() if ch not in _GAP_PUNCT)


def _gap_substantive_chars(text: str) -> set[str]:
    """实义字符集 = 字母与汉字（`str.isalnum()` 对汉字为 True），**排除数字与标点**。

    用「去重后的种数」而不是长度，是因为种数对**重复填充免疫**：`"待补"*6` 长 12、
    `"-"*20` 长 20、`"TODO TODO TODO TODO"` 长 19，长度都能过线，但种数只有 2 / 0 / 3。
    排除数字则挡住 `"1234567890123456"` 这类纯数字凑长度。
    """
    return {ch for ch in text if ch.isalnum() and not ch.isdigit()}


def _gap_defect(text: Any) -> str | None:
    """返回 `gap` 说明的缺陷描述；合格返回 None（阈值依据见 `_GAP_MIN_DISTINCT` 注释）。"""
    if not isinstance(text, str):
        return f"缺 gap 键或不是字符串（实测 {type(text).__name__}: {text!r}）"
    body = text.strip()
    if not body:
        return "gap 是空串 / 纯空白"
    if _gap_text_norm(body) in _GAP_PLACEHOLDERS:
        return f"gap 是占位符文案: {body!r}"
    if len(body) < _GAP_MIN_LEN:
        return f"gap 过短（{len(body)} < {_GAP_MIN_LEN} 字符）: {body!r}"
    kinds = _gap_substantive_chars(body)
    if len(kinds) < _GAP_MIN_DISTINCT:
        return (
            f"gap 实义字符仅 {len(kinds)} 种（< {_GAP_MIN_DISTINCT}）——"
            f"符号 / 数字 / 复读填充凑不出说明: {body!r}"
        )
    return None


def _column_map_cells(entry: dict[str, Any]) -> list[Any] | None:
    """取 `column_map` 数组（非数组返回 None）。同索引核对占位位置的前提。"""
    cmap = entry.get("column_map")
    return list(cmap) if isinstance(cmap, list) else None


def _cell_field(cell: Any) -> Any:
    """取 `column_map[i].field`；非对象条目按「值本身」处理（便于报出畸形登记）。"""
    return cell.get("field") if isinstance(cell, dict) else cell


def _cell_gap(cell: Any) -> Any:
    return cell.get("gap") if isinstance(cell, dict) else None


# ═══════════════════════════════════════════════════════════════════════════
# 替身清单重定向（真实装载行为判据的基础设施；类 A 有自检）
# ═══════════════════════════════════════════════════════════════════════════


class _LedgerRedirect:
    """把「读 `_LEDGER_PATH`」重定向到内存中的替身内容。

    覆盖四个读取入口（不同实现可能走任一个）：`builtins.open` / `io.open` /
    `Path.read_text` / `Path.open`。**只拦读、不拦写**，真实清单文件逐字节不动。
    """

    def __init__(self, content: str) -> None:
        self.content = content
        self.hits = 0
        self._target = _LEDGER_PATH.resolve()
        self._real_open = builtins.open
        self._real_read_text = Path.read_text
        self._real_path_open = Path.open
        self._patches: list[Any] = []

    def _is_target(self, file: Any) -> bool:
        try:
            return Path(file).resolve() == self._target
        except (TypeError, ValueError, OSError):
            return False

    def _fake_open(self, file: Any, *args: Any, **kwargs: Any) -> Any:
        mode = kwargs.get("mode", args[0] if args else "r")
        if self._is_target(file) and isinstance(mode, str) and "r" in mode and "b" not in mode:
            self.hits += 1
            return io.StringIO(self.content)
        return self._real_open(file, *args, **kwargs)

    def __enter__(self) -> "_LedgerRedirect":
        # 🔴 `Path` 上的两个补丁必须是**普通函数**（描述符），不能用 bound method ——
        # 把 bound method 赋成类属性后，`p.read_text()` 不会再把 `p` 作为第一个实参传进来，
        # 表现为 `missing 1 required positional argument: 'this'`（本轮已实测踩到）。
        redirect = self

        def fake_read_text(this: Any, *args: Any, **kwargs: Any) -> str:
            if redirect._is_target(this):
                redirect.hits += 1
                return redirect.content
            return redirect._real_read_text(this, *args, **kwargs)

        def fake_path_open(this: Any, *args: Any, **kwargs: Any) -> Any:
            mode = kwargs.get("mode", args[0] if args else "r")
            if (
                redirect._is_target(this)
                and isinstance(mode, str)
                and "r" in mode
                and "b" not in mode
            ):
                redirect.hits += 1
                return io.StringIO(redirect.content)
            return redirect._real_path_open(this, *args, **kwargs)

        self._patches = [
            mock.patch.object(builtins, "open", self._fake_open),
            mock.patch.object(io, "open", self._fake_open),
            mock.patch.object(Path, "read_text", fake_read_text),
            mock.patch.object(Path, "open", fake_path_open),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        for p in reversed(self._patches):
            p.stop()
        self._patches = []


def _exec_module_with_ledger(content: str) -> tuple[types.ModuleType, int]:
    """用替身清单内容重新 exec 一份模块副本，返回 (模块, 清单被读次数)。

    用真实包名下的**另一个叶子名**载入 ⇒ 相对 import 可解析，且不污染 `sys.modules`
    里的正式模块。

    🔴 **`exec_module` 前必须先把克隆名注册进 `sys.modules`**（任务 4.1 后半 GD-3）：
    CPython 3.12 的 `dataclasses._process_class` 对**字符串形态**的字段注解
    （= 被测模块写了 `from __future__ import annotations` 时的效果）会走
    `_is_type(...)` → `sys.modules.get(cls.__module__).__dict__`，克隆名查不到就是
    `None.__dict__` ⇒ `AttributeError: 'NoneType' object has no attribute '__dict__'`。
    那个报错与被测逻辑毫无关系，却会表现成「装载探针失败」，把本文件所有行为判据
    连带打成红/ERROR（曾迫使被测模块刻意不写该 future import）。`finally` 删键，
    保证异常路径（GD-2 的畸形清单用例**期望**抛异常）也不残留。
    """
    clone_name = f"{_MODULE_NAME.rsplit('.', 1)[0]}._x3_ledger_probe_clone"
    spec = importlib.util.spec_from_file_location(clone_name, _MODULE_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - 路径存在时不会走到
        pytest.fail(f"{_NOT_YET_MODULE}：无法为 {_MODULE_PATH} 构造 import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[clone_name] = module
    try:
        with _LedgerRedirect(content) as redirect:
            spec.loader.exec_module(module)
            return module, redirect.hits
    finally:
        sys.modules.pop(clone_name, None)


def _require_module() -> types.ModuleType:
    try:
        return importlib.import_module(_MODULE_NAME)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"{_NOT_YET_MODULE}：缺 {_MODULE_NAME}（{exc}）。"
            f"该模块是 16 张 X-3 的共享实现与 `X3_SHEET_SPECS` 唯一出口（design §C1）。"
        )
    raise AssertionError("unreachable")  # pragma: no cover


def _require_specs() -> dict[str, Any]:
    module = _require_module()
    specs = getattr(module, "X3_SHEET_SPECS", None)
    if not isinstance(specs, dict) or not specs:
        pytest.fail(
            f"{_NOT_YET_MODULE}：{_MODULE_NAME}.X3_SHEET_SPECS 缺失或为空 "
            f"（实测 {type(specs).__name__}）。design §C1 要求它在模块导入时从 "
            f"adjustment_ie_contract.json 装载并做结构校验。"
        )
    return specs


# ═══════════════════════════════════════════════════════════════════════════
# 类 A —— 独立口径自检（**当前应全绿**；红 = 守卫自身缺陷）
# ═══════════════════════════════════════════════════════════════════════════


class TestLedgerTruthSourceSelfCheck:
    """Key_Ledger 与判据基础设施的自检 —— 不依赖任务 2.1 / 4.1 的交付物。"""

    def test_ledger_file_parses_and_sheets_section_is_mapping(self):
        """清单可解析、`sheets` 段是非空映射且每条是对象（扫描面非空自检）。"""
        assert _LEDGER_PATH.is_file(), f"Key_Ledger 缺失: {_LEDGER_PATH}"
        doc = _ledger()
        sheets = doc.get("sheets")
        assert isinstance(sheets, dict) and sheets, "`sheets` 段必须是非空对象"
        bad = [k for k, v in sheets.items() if not isinstance(v, dict)]
        assert not bad, f"`sheets` 下存在非对象条目: {bad}"

    def test_three_iron_rules_are_in_place(self):
        """三条铁律在位（design §C6 / R7.6：任务 2.1 迁入时不得动它们）。"""
        missing = _missing_iron_rules(_ledger())
        assert not missing, (
            f"清单缺三条铁律中的: {missing}。"
            f"它们是 X-3 迁入后仍须成立的前提（对齐方向 / dual_write 停用 / field_keys 为期望值）"
        )

    def test_iron_rule_probe_rejects_doctored_ledger(self):
        """反向自检：铁律探针不是空转 —— 抽掉任一条铁律必须被检出。"""
        doc = json.loads(json.dumps(_ledger(), ensure_ascii=False))
        assert not _missing_iron_rules(doc), "基线复制体应无缺失"
        doc["_source"] = "（替身：抹掉对齐方向表述）"
        doc["_iron_rules"] = ["三重键必须同时对齐：item_id + storage_field + field_keys。"]
        missing = _missing_iron_rules(doc)
        assert len(missing) == len(_IRON_RULES), (
            f"探针漏检：抹掉三条铁律后只检出 {missing}（应检出全部 {len(_IRON_RULES)} 条）"
        )

    def test_exempt_kinds_registry_is_non_empty(self):
        """`exempt._exempt_kinds` 键集非空，且含 `no_backend_spec`（16 条现居该 kind）。"""
        kinds = _ledger().get("exempt", {}).get("_exempt_kinds")
        assert isinstance(kinds, dict) and kinds, "`exempt._exempt_kinds` 必须是非空对象"
        assert "no_backend_spec" in kinds, (
            f"缺 kind=no_backend_spec —— 16 张 X-3 目前正靠它豁免，"
            f"任务 2.1 的迁移单调性以它为准。实测 kinds={sorted(kinds)}"
        )

    def test_work_surface_is_sixteen_and_derivations_roundtrip(self):
        """作业面 16 张、无重复，且 sheet 码 → cycle → 短前缀 的派生可往返。

        派生规则（design 逐张两列实测表）：`M4-3` → cycle `M4` → 短前缀 `m4`。
        16 张全部按该规则派生 ⇒ 后续任务无需再写一份 per-sheet 映射表。
        """
        assert len(_X3_SHEETS) == 16, f"作业面应为 16 张，实测 {len(_X3_SHEETS)}"
        assert len(set(_X3_SHEETS)) == 16, "作业面有重复项"
        prefixes: set[str] = set()
        for sheet in _X3_SHEETS:
            cycle, _, tail = sheet.partition("-")
            assert tail == "3", f"{sheet} 不是 X-3 形态（尾段应为 3）"
            assert cycle[0] in "LMN" and cycle[1:].isdigit(), f"{sheet} 的 cycle 段异常: {cycle}"
            assert f"{cycle}-{tail}" == sheet, f"{sheet} 的派生不可往返"
            prefixes.add(cycle.lower())
        assert len(prefixes) == 16, f"短前缀应 16 个互不相同，实测 {sorted(prefixes)}"

    def test_mechanism_column_table_discriminates(self):
        """机制→列表必须能区分（两个机制映射到两个不同列），否则 GS9 恒真。"""
        assert len(_MECHANISM_TO_COLUMN) == 2, f"机制取值域应为 2: {_MECHANISM_TO_COLUMN}"
        assert set(_MECHANISM_TO_COLUMN.values()) == {"conclusion", "remark"}
        assert len(set(_MECHANISM_TO_COLUMN.values())) == 2, (
            "两个机制映射到同一列 ⇒ GS9 变成恒真断言（假绿）"
        )
        assert _derive_storage_field("adjustment_savebatch") != _derive_storage_field(
            "formdata_setfield"
        )
        assert _derive_storage_field("no_such_mechanism") is None, "未知机制必须判 None 而不是兜底"
        assert sum(_MECHANISM_DISTRIBUTION.values()) == len(_X3_SHEETS), (
            f"机制分布合计应等于作业面 16: {_MECHANISM_DISTRIBUTION}"
        )

    def test_strip_comments_actually_works(self):
        """反向自检：剥注释确实生效，且**不**误剥普通字符串字面量。"""
        src = (
            '"""docstring 里的示例键 M4-3-entry-1-desc 应被剥掉。"""\n'
            'SQL = """SELECT 1 FROM checklist_responses"""\n'
            "X = 1  # 行注释里的 N1-3-entries 应被剥掉\n"
            'HARD = "M4-3-entry-1-desc"\n'
        )
        out = _strip_py_comments(src)
        assert "docstring 里的示例键" not in out, "docstring 未被剥掉"
        assert "行注释里的" not in out, "# 行注释未被剥掉"
        assert "SELECT 1 FROM checklist_responses" in out, "普通字符串被误剥（SQL 会被吃掉）"
        assert out.count("M4-3-entry-1-desc") == 1, (
            f"剥后应只剩字面量里的那一处，实测 {out.count('M4-3-entry-1-desc')} 处"
        )

    def test_literal_scanner_ignores_docstring_examples(self):
        """反向自检：字面量扫描器只报真硬编码，docstring 里的示例键不得冒充。"""
        forbidden = ("M4-3", "N1-3-entries")
        doc_only = '"""说明：本模块处理 M4-3 与 N1-3-entries。"""\nSPECS = load()\n'
        assert _literals_present_in_code(doc_only, forbidden) == [], (
            "docstring 里的示例键被当成硬编码（会让守卫对正确实现假红）"
        )
        hard_coded = '"""说明。"""\nSPECS = {"M4-3": 1}\n'
        assert _literals_present_in_code(hard_coded, forbidden) == ["M4-3"], (
            "真硬编码未被检出（扫描器空转）"
        )

    def test_forbidden_literal_set_is_non_empty(self):
        """禁写清单非空（否则「模块不含 X-3 键字面量」是空转断言）。"""
        forbidden = _forbidden_x3_literals()
        assert len(forbidden) >= len(_X3_SHEETS), (
            f"禁写清单过小（{len(forbidden)}）—— 至少应含 16 个 sheet 码"
        )
        assert set(_X3_SHEETS) <= set(forbidden)

    def test_ledger_redirect_really_redirects_reads(self):
        """反向自检：替身清单重定向确实生效（四个读取入口都被拦住）。

        这是「真实装载行为」判据的基础设施；它若空转，类 B 的装载检验就变成
        「无论实现怎么写都通过」。
        """
        sentinel = json.dumps({"sheets": {"__probe__": {"item_id": "probe"}}}, ensure_ascii=False)
        with _LedgerRedirect(sentinel) as redirect:
            via_read_text = _LEDGER_PATH.read_text(encoding="utf-8")
            with open(_LEDGER_PATH, encoding="utf-8") as fh:
                via_open = fh.read()
            with _LEDGER_PATH.open(encoding="utf-8") as fh:
                via_path_open = fh.read()
        assert via_read_text == sentinel, "Path.read_text 未被重定向"
        assert via_open == sentinel, "builtins.open 未被重定向"
        assert via_path_open == sentinel, "Path.open 未被重定向"
        assert redirect.hits >= 3, f"重定向命中次数异常: {redirect.hits}"
        # 退出上下文后必须复原，且真实文件逐字节未变
        restored = json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
        assert "sheets" in restored and "__probe__" not in restored["sheets"], (
            "重定向未复原 —— 真实清单读取被污染"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-1 —— 16 条迁入 `sheets`（当前应全红：尚未实现（Wave 1 任务 2.1））
# ═══════════════════════════════════════════════════════════════════════════


class TestLedgerRegistersSixteenX3:
    """16 张 X-3 必须在 Key_Ledger 的 `sheets` 段有记录（R2.1）。"""

    @pytest.mark.parametrize("sheet", _X3_SHEETS)
    def test_sheet_is_registered_in_sheets_section(self, sheet: str):
        entry = _entry_or_fail(sheet)
        assert isinstance(entry, dict) and entry, f"{sheet} 的清单条目为空"

    def test_no_x3_left_in_exempt_section(self):
        """迁移的另一半：迁入 `sheets` 后不得同时留在 `exempt`（否则两处双真源）。"""
        exempt = _ledger().get("exempt", {})
        left = [s for s in _X3_SHEETS if isinstance(exempt.get(s), dict)]
        assert not left, (
            f"{_NOT_YET_LEDGER}：以下 X-3 仍留在 exempt 段: {left}。"
            f"任务 2.1 须迁出（`exempt.no_backend_spec` 条目数只许下调、"
            f"`sheets` 条目数只许上调）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-2 —— 三重键 + 机制字段完备（当前应全红）
# ═══════════════════════════════════════════════════════════════════════════


class TestLedgerEntryDeclaresTripleAndMechanism:
    """每条 X-3 必须给全 `item_id` / `storage_field` / `field_keys` + `mechanism`（R2.1 / R2.2）。"""

    @pytest.mark.parametrize("sheet", _X3_SHEETS)
    def test_entry_declares_triple_and_mechanism(self, sheet: str):
        entry = _entry_or_fail(sheet)

        key_family = entry.get("key_family")
        assert key_family in _WRITE_KEY_FAMILIES, (
            f"{sheet} 的 key_family 非法: {key_family!r}（应属 {sorted(_WRITE_KEY_FAMILIES)}）"
        )

        # `item_id` 只有单键 JSON 族才是单键；逐字段族的身份是族前缀（design §Data Models）
        if key_family == "single_json":
            item_id = entry.get("item_id")
            assert isinstance(item_id, str) and item_id, (
                f"{sheet} 是 single_json 族但缺 item_id: {item_id!r}"
            )
        else:
            families = entry.get("key_families")
            assert isinstance(families, dict) and families, (
                f"{sheet} 是 {key_family} 族但缺 key_families 段（族前缀与后缀表无处承载）"
            )
            per_field = families.get("per_field")
            assert isinstance(per_field, dict), f"{sheet} 的 key_families 缺 per_field 段"
            prefix = per_field.get("prefix")
            assert isinstance(prefix, str) and prefix, (
                f"{sheet} 的 per_field.prefix 缺失（双前缀逐 sheet 不同，禁写全局常量）"
            )
            suffixes = per_field.get("suffixes")
            assert isinstance(suffixes, list) and suffixes, (
                f"{sheet} 的 per_field.suffixes 缺失 —— 后缀表必须逐 sheet 承载"
                f"（design E20：M9-3 有第 11 个后缀 ociBlock）"
            )

        mechanism = entry.get("mechanism")
        assert mechanism in _MECHANISM_TO_COLUMN, (
            f"{sheet} 的 mechanism 非法: {mechanism!r}（应属 {sorted(_MECHANISM_TO_COLUMN)}）。"
            f"provenance 记机制而非只记观察列，是 R2.7 / R2.8 双向锁死的前提"
        )

        storage_field = entry.get("storage_field")
        assert storage_field in set(_MECHANISM_TO_COLUMN.values()), (
            f"{sheet} 的 storage_field 非法: {storage_field!r}"
        )

        field_keys = _as_key_tuple(entry.get("field_keys"))
        assert field_keys is not None, f"{sheet} 的 field_keys 不是数组: {entry.get('field_keys')!r}"
        assert len(field_keys) == _COLUMN_COUNT, (
            f"{sheet} 的 field_keys 应与 COLUMN_ORDER 同序、共 {_COLUMN_COUNT} 项，"
            f"实测 {len(field_keys)} 项（列面本体由任务 1.2 / GS2 对源模板实读比对）"
        )
        # ── 占位列判据 ────────────────────────────────────────────────────
        # 🔴 旧判据是「恰 1 个 None 占位」，沿用 design §D2「`……`（F 列）唯一占位」前提；
        # 该前提已被任务 2.1 批次 1 实测推翻（`L2-3` = F+J 两个占位；`N5-3` 预计 6 个），
        # 故改判为「≥1 个占位 + 每个占位位在**同索引**的 column_map 上带非空实质 gap 说明」。
        # 详细推翻依据与四条子判据见文件上方「占位列（gap）判据」注释块。
        cells = _column_map_cells(entry)
        assert cells is not None and len(cells) == _COLUMN_COUNT, (
            f"{sheet} 的 column_map 应是与 COLUMN_ORDER 同序、共 {_COLUMN_COUNT} 项的数组，"
            f"实测 {type(entry.get('column_map')).__name__} / "
            f"{len(cells) if cells is not None else '不可数'} 项。"
            f"占位判据改判后要按**同索引**核对 field_keys 与 column_map（design §D2 的"
            f"「F 列唯一占位」前提已被 L2-3 实测推翻），缺了它无从核对"
        )
        key_gaps = {i for i, k in enumerate(field_keys) if _is_blank_key(k)}
        map_gaps = {i for i, cell in enumerate(cells) if _is_blank_key(_cell_field(cell))}
        assert key_gaps == map_gaps, (
            f"{sheet} 的占位位置未一一对应：field_keys 空位 {sorted(key_gaps)} vs "
            f"column_map 空 field 位 {sorted(map_gaps)}（只在一侧出现的: "
            f"{sorted(key_gaps ^ map_gaps)}）。两侧必须是**同一批索引** —— 否则"
            f"「field_keys 第 9 位空、column_map 第 5 位写 gap」也能蒙过占位判据"
        )
        assert key_gaps, (
            f"{sheet} 未登记任何占位列（field_keys 10 项全有前端字段）。"
            f"源模板第 5 行确实存在无对应前端字段的列（至少 F 列 `……`）⇒ 占位数必 ≥1；"
            f"0 个占位意味着「为凑齐 10 列而给无字段列硬塞前端键」，那会新造前端键并让"
            f"导入值在 normalizeEntry 处被静默丢弃（往返丢数据）"
        )
        gap_defects = {i: _gap_defect(_cell_gap(cells[i])) for i in sorted(key_gaps)}
        gap_defects = {i: d for i, d in gap_defects.items() if d}
        assert not gap_defects, (
            f"{sheet} 的占位列缺实质 `gap` 说明: "
            + "；".join(
                f"index {i}（列 "
                f"{cells[i].get('letter') if isinstance(cells[i], dict) else '?'}）{d}"
                for i, d in gap_defects.items()
            )
            + f"。改判后的语义：占位数不再限定为 1（design §D2「F 列唯一占位」前提已被 "
            f"`L2-3`（F+J 两个占位）与 `N5-3`（预计 6 个）实测推翻），但**每个占位都必须"
            f"写明为何无对应前端字段** —— 这比旧的「恰 1 个」更强：旧判据只数个数，抓不到"
            f"「不写 gap 理由就把列留空」；阈值 = strip 后 ≥{_GAP_MIN_LEN} 字符且实义字符 "
            f"≥{_GAP_MIN_DISTINCT} 种（实测真 gap 最短 75 字符 / 41 种，占位符与复读填充 "
            f"≤3 种，两侧各留 5 倍余量）"
        )
        stray_gaps = sorted(
            i
            for i, cell in enumerate(cells)
            if i not in key_gaps and not _is_blank_key(_cell_gap(cell))
        )
        assert not stray_gaps, (
            f"{sheet} 在**非占位**列上写了 gap 说明: index {stray_gaps}"
            f"（这些列的 field 非空）。gap 的语义是「此列为何无对应前端字段」，"
            f"写在有字段的列上属登记错位，也会让「gap 位 ↔ 占位位」的对应关系失真"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-3 —— GS9 后端侧：storage_field 由机制推导（当前应全红）
# ═══════════════════════════════════════════════════════════════════════════


class TestStorageFieldDerivedFromMechanism:
    """`storage_field == derive(mechanism)`，逐张断言（GS9 后端侧 / R2.7 / R2.8）。

    判据边界见模块 docstring：`mechanism` 取清单登记值 ⇒ 只抓「清单内自相矛盾」；
    「机制本身是否与前端源码一致」由任务 1.9 的前端探针承担。
    """

    @pytest.mark.parametrize("sheet", _X3_SHEETS)
    def test_storage_field_matches_mechanism(self, sheet: str):
        entry = _entry_or_fail(sheet)
        mechanism = entry.get("mechanism")
        expected = _derive_storage_field(mechanism)
        assert expected is not None, (
            f"{sheet} 的 mechanism 未登记或非法: {mechanism!r} ⇒ 无法推导写入列"
        )
        actual = entry.get("storage_field")
        assert actual == expected, (
            f"{sheet} 机制↔列不一致：mechanism={mechanism!r} 应写 {expected!r}，"
            f"清单登记 storage_field={actual!r}。"
            f"（① use{{X}}FormData.setField → saveField(itemId, {{conclusion}}) 恒 conclusion；"
            f"② use{{X}}Adjustment 的 saveBatch/debouncedSave 恒 remark）"
        )

    def test_mechanism_distribution_matches_design(self):
        """机制分布须等于 design §Data Models 登记值（12 savebatch / 4 setfield）。

        这条抓的是「整批登记成同一机制」这类批量错；逐张的机制正确性靠任务 1.9。
        """
        missing = [s for s in _X3_SHEETS if s not in _ledger_sheets()]
        assert not missing, f"{_NOT_YET_LEDGER}：{len(missing)} 张尚未迁入 sheets: {missing}"
        counts: dict[str, int] = {k: 0 for k in _MECHANISM_TO_COLUMN}
        unknown: dict[str, Any] = {}
        for sheet in _X3_SHEETS:
            mech = _ledger_sheets()[sheet].get("mechanism")
            if mech in counts:
                counts[mech] += 1
            else:
                unknown[sheet] = mech
        assert not unknown, f"以下 sheet 的 mechanism 非法: {unknown}"
        assert counts == _MECHANISM_DISTRIBUTION, (
            f"机制分布与 design 登记值不符：实测 {counts}，应为 {_MECHANISM_DISTRIBUTION}"
            f"（formdata_setfield 的 4 张 = N1-3 / N2-3 / N3-3 / N5-3）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-4 —— GS1：X3_SHEET_SPECS 与清单三重对齐 + 真从清单装载（当前应全红）
# ═══════════════════════════════════════════════════════════════════════════


class TestX3SheetSpecsAlignedWithLedger:
    """`X3_SHEET_SPECS` ↔ Key_Ledger 双向锁死（GS1 / design §Data Models「唯一真源关系」）。"""

    def test_module_exists_and_exposes_specs(self):
        specs = _require_specs()
        assert isinstance(specs, dict) and specs

    def test_specs_cover_exactly_the_sixteen_sheets(self):
        specs = _require_specs()
        missing = [s for s in _X3_SHEETS if s not in specs]
        extra = sorted(set(specs) - set(_X3_SHEETS))
        assert not missing, f"X3_SHEET_SPECS 缺 {len(missing)} 张: {missing}"
        assert not extra, f"X3_SHEET_SPECS 多出非作业面条目: {extra}"

    @pytest.mark.parametrize("sheet", _X3_SHEETS)
    def test_triple_alignment_with_ledger(self, sheet: str):
        """三重键逐字对齐：item_id / storage_field / field_keys。"""
        specs = _require_specs()
        entry = _entry_or_fail(sheet)
        spec = specs.get(sheet)
        assert spec is not None, f"X3_SHEET_SPECS 缺 {sheet}"

        assert _spec_field(spec, "item_id") == entry.get("item_id"), (
            f"{sheet} item_id 不一致：specs={_spec_field(spec, 'item_id')!r} "
            f"vs 清单={entry.get('item_id')!r}"
        )
        assert _spec_field(spec, "storage_field") == entry.get("storage_field"), (
            f"{sheet} storage_field 不一致：specs={_spec_field(spec, 'storage_field')!r} "
            f"vs 清单={entry.get('storage_field')!r}（写错列 = 界面读不到，最隐蔽的 Orphan_Key）"
        )
        spec_keys = _as_key_tuple(_spec_field(spec, "field_keys"))
        ledger_keys = _as_key_tuple(entry.get("field_keys"))
        assert spec_keys == ledger_keys, (
            f"{sheet} field_keys 不一致：specs={spec_keys!r} vs 清单={ledger_keys!r}"
        )

    def test_module_source_has_no_x3_key_literals(self):
        """剥注释后模块源码不得出现 X-3 键字面量（禁硬编码，design §C1）。"""
        if not _MODULE_PATH.is_file():
            pytest.fail(f"{_NOT_YET_MODULE}：缺 {_MODULE_PATH}")
        forbidden = _forbidden_x3_literals()
        hits = _literals_present_in_code(
            _MODULE_PATH.read_text(encoding="utf-8"), forbidden
        )
        assert not hits, (
            f"{_MODULE_PATH.name} 剥注释后仍含 X-3 键字面量（硬编码）: {hits}。"
            f"design §C1：Python 侧不写任何键字面量，`X3_SHEET_SPECS` 一律从 "
            f"adjustment_ie_contract.json 装载"
        )

    def test_specs_really_loaded_from_ledger(self):
        """真实装载行为判据：替身清单改一处，`X3_SHEET_SPECS` 必须跟着变。

        变异内容 = 把某张的 `mechanism` 与 `storage_field` **成对**翻到另一个合法取值
        （成对翻 ⇒ 替身清单自身仍自洽，不会被实现的结构校验拒收）。

        - 跟着变 ⇒ 值真来自清单
        - 不变 ⇒ 值另有出处（硬编码 / 装载了但不采用），本条判红
        """
        if not _MODULE_PATH.is_file():
            pytest.fail(f"{_NOT_YET_MODULE}：缺 {_MODULE_PATH}")

        doc = json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
        registered = [s for s in _X3_SHEETS if isinstance(doc.get("sheets", {}).get(s), dict)]
        if not registered:
            pytest.fail(
                f"{_NOT_YET_LEDGER}：清单 sheets 段无任何 X-3 条目 ⇒ 无法做装载行为检验"
            )
        probe_sheet = registered[0]
        entry = doc["sheets"][probe_sheet]
        old_mech = entry.get("mechanism")
        assert old_mech in _MECHANISM_TO_COLUMN, (
            f"{probe_sheet} 的 mechanism 非法: {old_mech!r}（先修类 B-2 再看本条）"
        )
        new_mech = next(m for m in _MECHANISM_TO_COLUMN if m != old_mech)
        entry["mechanism"] = new_mech
        entry["storage_field"] = _MECHANISM_TO_COLUMN[new_mech]

        module, hits = _exec_module_with_ledger(json.dumps(doc, ensure_ascii=False))
        assert hits >= 1, (
            "模块 import 期间一次都没读 adjustment_ie_contract.json ⇒ "
            "`X3_SHEET_SPECS` 不是从清单装载的（design §C1 禁硬编码）"
        )
        specs = getattr(module, "X3_SHEET_SPECS", None)
        assert isinstance(specs, dict) and probe_sheet in specs, (
            f"替身清单下 X3_SHEET_SPECS 缺 {probe_sheet}"
        )
        assert _spec_field(specs[probe_sheet], "storage_field") == _MECHANISM_TO_COLUMN[new_mech], (
            f"替身清单把 {probe_sheet} 的 storage_field 改成 "
            f"{_MECHANISM_TO_COLUMN[new_mech]!r}，但 X3_SHEET_SPECS 仍是 "
            f"{_spec_field(specs[probe_sheet], 'storage_field')!r} ⇒ 该值不来自清单"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-5 —— 任务 4.1 后半补的三条守卫缺陷（GD-1 / GD-2 + entryType 大小写行为）
#
# 三条都由任务 4.1 前半的变异检验暴露：前半只交付了数据层，两条变异（把
# `COLUMN_ORDER` 改成写死字面量 / 把结构校验改成静默兜空）**判据面 101 passed 全绿**
# ⇒ 判 GREEN = 守卫缺陷。成因不是「没人写判据」，而是两侧各让了一步：
#   * GS1（本文件）的字面量禁写清单 docstring 明写「不收列标签」（那是 GS2 的作业面）；
#   * GS2（`test_x3_column_alignment`）做的是三向**值**比对 —— 把正确值原地写死，
#     三向照样逐字相等 ⇒ 「派生关系」断了也全绿。
# 故 GD-1 的判据只能落在**替身清单驱动**上（改清单 ⇒ 常量必须跟着变），这只有本文件
# 的 `_exec_module_with_ledger` 有载具。
# ═══════════════════════════════════════════════════════════════════════════


def _ledger_doc_copy() -> dict[str, Any]:
    """磁盘清单的可改副本（内存改，绝不写盘）。"""
    return json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))


def _registered_x3(doc: dict[str, Any]) -> list[str]:
    sheets = doc.get("sheets") or {}
    return [s for s in _X3_SHEETS if isinstance(sheets.get(s), dict)]


def _contract_error(module: types.ModuleType) -> type[BaseException]:
    exc = getattr(module, "X3ContractError", None)
    if not (isinstance(exc, type) and issubclass(exc, BaseException)):
        pytest.fail(
            f"{_NOT_YET_MODULE}：{_MODULE_NAME}.X3ContractError 缺失或不是异常类"
            f"（实测 {exc!r}）。结构校验的唯一失败出口必须是具名异常 —— "
            f"否则畸形清单只能靠「抛了任何异常」蒙对（`AttributeError` / `StopIteration` / "
            f"`IndexError` 都会让判据假通过）"
        )
    return exc  # type: ignore[return-value]


def _assert_is_contract_error(raised: BaseException, reference: type[BaseException], case: str) -> None:
    """断言 `raised` 的**类型**就是被测模块的 `X3ContractError`。

    🔴 不能直接 `pytest.raises(reference)`：`_exec_module_with_ledger` 会重新 exec 一份
    模块副本 ⇒ 副本里的 `X3ContractError` 是**另一个类对象**，`isinstance` 必不成立。
    本轮首版就是这么写的，11/11 全红而实现其实抛得好好的 —— 属 harness 缺陷（四态里的
    ANCHOR-MISS 一类），若不查清会误判成「实现没抛」并去改实现。

    判据强度与 `isinstance` 等价：类名 + MRO 尾部 + 出处包路径三者全等。
    `AttributeError` / `StopIteration` / `IndexError`（= 结构校验被改成静默兜空后
    残留的偶发异常）三者的名字与 MRO 都不同 ⇒ 蒙不过去。
    """
    actual = type(raised)
    assert actual.__name__ == reference.__name__, (
        f"「{case}」抛的是 {actual.__module__}.{actual.__name__}: {raised!r}，"
        f"不是 {reference.__name__} ⇒ 结构校验没拦住这类畸形，异常是后续代码"
        f"「静默兜空之后」偶然撞出来的（这正是本判据要排除的假通过形态）"
    )
    assert actual.__mro__[1:] == reference.__mro__[1:], (
        f"「{case}」抛的 {actual.__name__} 基类链 {actual.__mro__[1:]} 与被测模块的 "
        f"{reference.__mro__[1:]} 不同 ⇒ 同名不同源"
    )
    assert actual.__module__.rsplit(".", 1)[0] == reference.__module__.rsplit(".", 1)[0], (
        f"「{case}」抛的异常出自 {actual.__module__}，与被测模块所在包 "
        f"{reference.__module__.rsplit('.', 1)[0]} 不同 ⇒ 不是本模块的结构校验抛的"
    )


class TestColumnOrderDerivedFromLedger:
    """GD-1：`COLUMN_ORDER` 必须**真由清单 `column_map[].col` 派生**。

    判据 = 替身清单把 16 张的列标签整体改名 ⇒ `COLUMN_ORDER` 必须跟着变。
    「写死正确的 10 个字面量」在旧判据下全绿（GS2 的三向值比对逐字相等、
    GS1 的字面量禁写清单又刻意不收列标签），本条正是补那个洞。
    """

    _MARK = "‡派生检验"

    def test_column_order_follows_ledger_column_map(self):
        if not _MODULE_PATH.is_file():
            pytest.fail(f"{_NOT_YET_MODULE}：缺 {_MODULE_PATH}")
        doc = _ledger_doc_copy()
        registered = _registered_x3(doc)
        if not registered:
            pytest.fail(f"{_NOT_YET_LEDGER}：清单 sheets 段无任何 X-3 条目 ⇒ 无法做派生检验")

        renamed = 0
        for sheet in registered:
            cells = doc["sheets"][sheet].get("column_map")
            assert isinstance(cells, list) and cells, (
                f"{_NOT_YET_LEDGER}：{sheet} 缺 `column_map` ⇒ 派生检验无对象"
            )
            for cell in cells:
                assert isinstance(cell, dict) and isinstance(cell.get("col"), str), (
                    f"{sheet} 的 `column_map` 条目形态非法: {cell!r}"
                )
                cell["col"] = cell["col"] + self._MARK
            renamed += 1
        assert renamed == len(registered)

        module, hits = _exec_module_with_ledger(json.dumps(doc, ensure_ascii=False))
        assert hits >= 1, (
            "模块 import 期间一次都没读清单 ⇒ `COLUMN_ORDER` 不可能来自 `column_map`"
        )
        order = getattr(module, "COLUMN_ORDER", None)
        assert isinstance(order, tuple) and order, (
            f"{_NOT_YET_MODULE}：`COLUMN_ORDER` 缺失或为空（实测 {order!r}）"
        )
        not_following = [label for label in order if not label.endswith(self._MARK)]
        assert not not_following, (
            f"替身清单已把全部 `column_map[].col` 加后缀 {self._MARK!r}，但 COLUMN_ORDER 里 "
            f"{len(not_following)} 项没跟着变: {not_following} ⇒ 该常量不是从清单派生的"
            f"（写死一份列头字面量、或装载后又被硬编码覆盖）。design §C1：那 10 个列标签在 "
            f"Python 侧只许有一个定义处 = 清单 `column_map[].col`"
        )
        assert len(order) == _COLUMN_COUNT, (
            f"派生出的列数 {len(order)} != {_COLUMN_COUNT}"
        )

    def test_real_column_order_has_no_probe_marker(self):
        """反向自检：真实清单下派生结果**不带**探针后缀（证明上一条不是恒真）。"""
        specs_module = _require_module()
        order = getattr(specs_module, "COLUMN_ORDER", None)
        assert isinstance(order, tuple) and order, f"{_NOT_YET_MODULE}：`COLUMN_ORDER` 缺失"
        polluted = [label for label in order if self._MARK in label]
        assert not polluted, f"真实 COLUMN_ORDER 里出现探针后缀 {polluted} ⇒ 变异未还原"


# ── GD-2：畸形清单必须抛 `X3ContractError`（不是「抛了任何异常」）─────────────
#
# 前半唯一的行为探针（`test_specs_really_loaded_from_ledger`）刻意只驱动**自洽**替身
# （`mechanism` 与 `storage_field` 成对翻），其 docstring 明写「成对翻 ⇒ 替身自身仍自洽，
# 不会被实现的结构校验拒收」⇒ **从没有畸形清单进过模块**，于是「把 `_fail` 改成只记
# warning 不抛」这条变异照样全绿。
#
# 🔴 必须断言**异常类型**：把校验改成静默兜空后，9 类畸形里仍有 3 类会在后续代码里
# 退化成与病因无关的偶发异常（`AttributeError` / `StopIteration` / `IndexError`）——
# 只断言 `pytest.raises(Exception)` 会被它们蒙对，判据等于没有。


def _mut_drop_storage_field(doc: dict[str, Any], sheet: str) -> None:
    doc["sheets"][sheet].pop("storage_field", None)


def _mut_short_field_keys(doc: dict[str, Any], sheet: str) -> None:
    doc["sheets"][sheet]["field_keys"] = doc["sheets"][sheet]["field_keys"][:-1]


def _mut_col_is_null(doc: dict[str, Any], sheet: str) -> None:
    doc["sheets"][sheet]["column_map"][0]["col"] = None


def _mut_storage_field_only(doc: dict[str, Any], sheet: str) -> None:
    """只翻 `storage_field` 不翻 `mechanism` ⇒ 机制↔列自相矛盾（写错列 = 界面读不到）。"""
    entry = doc["sheets"][sheet]
    current = entry.get("storage_field")
    entry["storage_field"] = next(v for v in _MECHANISM_TO_COLUMN.values() if v != current)


def _mut_drop_key_family(doc: dict[str, Any], sheet: str) -> None:
    doc["sheets"][sheet].pop("key_family", None)


def _mut_drop_all_key_families(doc: dict[str, Any], _sheet: str) -> None:
    for entry in doc["sheets"].values():
        if isinstance(entry, dict):
            entry.pop("key_family", None)


def _mut_drop_registered_suffix(doc: dict[str, Any], sheet: str) -> None:
    """逐字段族的后缀表少一项（`suffix_to_field` 与 `suffixes` 不等势）。"""
    family = doc["sheets"][sheet]["key_families"]["per_field"]
    family["suffixes"] = family["suffixes"][:-1]


def _mut_drop_data_family(doc: dict[str, Any], sheet: str) -> None:
    doc["sheets"][sheet]["key_families"].pop("data", None)


def _mut_standalone_collides(doc: dict[str, Any], sheet: str) -> None:
    """表级独立键与往返键撞名 ⇒ 往返会把表级说明当行数据写掉。"""
    entry = doc["sheets"][sheet]
    entry.setdefault("observed", {})["other_data_keys"] = [entry["item_id"]]


def _mut_rewrite_entry_type_marker(doc: dict[str, Any], sheet: str) -> None:
    """把「AJE/RJE 标记」声明文案改写 ⇒ entryType 字段名无处可取。"""
    for item in doc["sheets"][sheet].get("unmapped_fields") or []:
        if isinstance(item, dict) and isinstance(item.get("handling"), str):
            item["handling"] = item["handling"].replace("AJE/RJE", "某种").replace("AJE / RJE", "某种")


def _mut_column_map_diverges_from_field_keys(doc: dict[str, Any], sheet: str) -> None:
    """`column_map[].field` 与 `field_keys` 分叉 ⇒ 两份真源。"""
    cells = doc["sheets"][sheet]["column_map"]
    for cell in cells:
        if cell.get("field"):
            cell["field"] = cell["field"] + "X"
            return
    cells[0]["field"] = "X"


#: (用例名, 变异函数, 作用 sheet 的挑选方式)
_MALFORMED_CASES = [
    ("删 storage_field", _mut_drop_storage_field, "any"),
    ("field_keys 少一项", _mut_short_field_keys, "any"),
    ("column_map[].col 置 null", _mut_col_is_null, "any"),
    ("只翻 storage_field 不翻 mechanism", _mut_storage_field_only, "any"),
    ("全部抽掉 key_family（作业面为空）", _mut_drop_all_key_families, "any"),
    ("逐字段族后缀表少一项", _mut_drop_registered_suffix, "per_field"),
    ("抽掉整行 JSON 族", _mut_drop_data_family, "plus_data"),
    ("表级独立键与往返键撞名", _mut_standalone_collides, "single_json"),
    ("改写「AJE/RJE 标记」声明文案", _mut_rewrite_entry_type_marker, "any"),
    ("column_map[].field 与 field_keys 分叉", _mut_column_map_diverges_from_field_keys, "any"),
]


def _pick_sheet(doc: dict[str, Any], kind: str) -> str | None:
    """按键族挑一张登记过的 X-3；挑不到返回 None（由用例 fail 出可读原因）。"""
    for sheet in _registered_x3(doc):
        entry = doc["sheets"][sheet]
        family = entry.get("key_family")
        families = entry.get("key_families") or {}
        if kind == "any":
            return sheet
        if kind == "single_json" and family == "single_json":
            return sheet
        if kind == "per_field" and isinstance(families.get("per_field"), dict):
            return sheet
        if kind == "plus_data" and family == "per_field_plus_data":
            return sheet
    return None


class TestStructureValidationRejectsMalformedLedger:
    """GD-2：畸形清单必须被结构校验**拒收**（抛 `X3ContractError`），不得静默兜空。"""

    def test_control_unmutated_ledger_loads(self):
        """CONTROL：未变异的替身清单必须装得起来 ⇒ 下面的红可归因于变异本身。"""
        module, hits = _exec_module_with_ledger(
            json.dumps(_ledger_doc_copy(), ensure_ascii=False)
        )
        assert hits >= 1
        specs = getattr(module, "X3_SHEET_SPECS", None)
        assert isinstance(specs, dict) and len(specs) == len(_X3_SHEETS), (
            f"未变异替身清单下应装出 {len(_X3_SHEETS)} 张，实测 "
            f"{len(specs) if isinstance(specs, dict) else specs!r}"
        )

    @pytest.mark.parametrize(
        ("name", "mutate", "kind"),
        _MALFORMED_CASES,
        ids=[c[0] for c in _MALFORMED_CASES],
    )
    def test_malformed_ledger_raises_contract_error(self, name, mutate, kind):
        if not _MODULE_PATH.is_file():
            pytest.fail(f"{_NOT_YET_MODULE}：缺 {_MODULE_PATH}")
        exc_type = _contract_error(_require_module())

        doc = _ledger_doc_copy()
        sheet = _pick_sheet(doc, kind)
        if sheet is None:
            pytest.fail(
                f"{_NOT_YET_LEDGER}：清单里找不到 kind={kind!r} 的 X-3 条目 ⇒ "
                f"「{name}」这类畸形无从构造（判据空转，不得当成通过）"
            )
        mutate(doc, sheet)

        with pytest.raises(BaseException) as caught:  # noqa: PT011 - 类型由 _assert 结构比对
            _exec_module_with_ledger(json.dumps(doc, ensure_ascii=False))
        _assert_is_contract_error(caught.value, exc_type, name)
        message = str(caught.value)
        assert message.strip(), f"「{name}」抛了 {exc_type.__name__} 但消息为空 ⇒ 无法定位病因"

    def test_removing_one_key_family_shrinks_scope_instead_of_raising(self):
        """判据分工的显式登记（本轮实测得出，不是漏做）。

        单张条目被抽掉 `key_family` 时，被测模块**不会**抛 —— 因为「登记了 `key_family`」
        正是它挑 X-3 条目的判据本身，模块无从分辨「这条本来就不是 X-3」与「登记被误删」。
        它只会安静地少服务一张。

        这不是可以放过的静默：作业面缩水的检出责任在本文件的
        `TestX3SheetSpecsAlignedWithLedger.test_specs_cover_exactly_the_sixteen_sheets`
        （那条钉死 16 张）。本用例把这层分工做成断言 —— 一旦哪天那条覆盖面判据被删/放宽，
        本条会指名道姓地红出来，而不是留下一个「谁都没管」的缺口。
        """
        doc = _ledger_doc_copy()
        registered = _registered_x3(doc)
        if len(registered) < 2:
            pytest.fail(f"{_NOT_YET_LEDGER}：登记的 X-3 少于 2 张，无从构造缩水场景")
        victim = registered[0]
        _mut_drop_key_family(doc, victim)

        module, _hits = _exec_module_with_ledger(json.dumps(doc, ensure_ascii=False))
        specs = getattr(module, "X3_SHEET_SPECS", None)
        assert isinstance(specs, dict), f"{_NOT_YET_MODULE}：X3_SHEET_SPECS 形态非法"
        assert victim not in specs, (
            f"抽掉 {victim} 的 `key_family` 后它仍在作业面里 ⇒ 作业面不是按清单判据挑的"
        )
        assert len(specs) == len(registered) - 1, (
            f"作业面应缩到 {len(registered) - 1} 张，实测 {len(specs)}"
        )
        coverage_guard = getattr(
            TestX3SheetSpecsAlignedWithLedger, "test_specs_cover_exactly_the_sixteen_sheets", None
        )
        assert callable(coverage_guard), (
            "作业面缩水的检出责任在 "
            "`TestX3SheetSpecsAlignedWithLedger.test_specs_cover_exactly_the_sixteen_sheets`，"
            "但该用例已不存在 ⇒ 现在没有任何判据拦住「少服务一张 sheet」，必须补回"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-6 —— entryType 大小写：登记与否**决定行为**（任务 4.1 后半新增）
#
# 背景：12 张的 AJE/RJE 枚举大小写在清单里没登记（只有 N 族 4 张登记了，其中 `N5-3`
# 实测是**小写** `aje` / `rje`）。共享实现的处置是「未登记 ⇒ 拒绝写该键 + 记 warning」，
# **刻意不默认成规范大写** —— 猜错大小写会让导入行从 AJE / RJE 两张 el-table 同时消失
# （filter 全不命中 = 静默丢行），比「字段缺失」难查得多。
#
# 本组把该处置钉成行为判据（真跑一次解析，不是查字符串），并**自我失效**：
# 未登记集合直接从清单实算，任务 2.4 补完登记后本组自动切到「必须写键」那条分支，
# 没有任何基线数字需要手改。
#
# 🔴 **任务 2.4 已把 12 张全部补登（16/16 已登记）⇒ 上面那句「自动切分支」同时意味着
# 「未登记 ⇒ 拒写键 + 记 warning」这条分支的实例数归零 = 恒真空转**（memory 里
# 「零条目即空过」那类假绿：实现改成「未登记就猜大写」照样全绿）。故判据分两层：
#   * 真实面（`TestEntryTypeCasingDrivesBehaviour`）—— 16/16 走「已登记」分支，
#     另加一条「16 张必须全部登记」的目标态断言（谁把某张退登记，谁打红）；
#   * 合成面（`TestEntryTypeUnregisteredBranchSynthetic`）—— 用替身清单造「未登记」
#     sheet，让拒写 + warning 这条行为在真实条目全部登记后**仍被真判**。
# 两面共用同一份判据函数（`_check_casing_agreement` / `_check_entry_type_import_behaviour`），
# 不写第二套口径 —— 否则合成夹具验的是另一套逻辑，真实实现改坏了照样绿。
# ═══════════════════════════════════════════════════════════════════════════


_ENTRY_TYPE_ENUM_DECL_RE = re.compile(
    r"取值\s*['\"]([A-Za-z]{2,8})['\"]\s*\|\s*['\"]([A-Za-z]{2,8})['\"]"
)
_ENTRY_TYPE_MARKER_DECL_RE = re.compile(r"AJE\s*/\s*RJE\s*标记")


def _ledger_entry_type_casing(entry: dict[str, Any]) -> tuple[str, str] | None:
    """从清单 `unmapped_fields[].handling` 独立解析枚举大小写（不读被测模块的 spec）。

    独立解析是要点：若直接读 `spec.entry_type_values` 再拿它当期望值，判据就退化成
    「实现和自己比」，实现把大小写统一改写也照样绿。
    """
    for item in entry.get("unmapped_fields") or []:
        if not isinstance(item, dict):
            continue
        handling = item.get("handling")
        if not isinstance(handling, str) or not _ENTRY_TYPE_MARKER_DECL_RE.search(handling):
            continue
        pairs = _ENTRY_TYPE_ENUM_DECL_RE.findall(handling)
        if len(pairs) == 1:
            return pairs[0]
        return None
    return None


def _upload_bytes(module: types.ModuleType, sheet: str, cell_rows: list[list[Any]]) -> bytes:
    """用被测模块自己的模板构建器造一份上传文件，按列序直接写单元格。

    按列序写（而非按行模型字段）是必须的：`N5-3` 的「类别」列在其行模型里是占位 `None`，
    走字段映射根本写不进那一列，判据会变成「所有行都落兜底值」的空转。
    """
    wb = module.build_template_workbook(sheet)
    ws = wb[module.X3_SHEET_SPECS[sheet].sheet_name]
    for cells in cell_rows:
        ws.append(list(cells))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _category_text_for(module: types.ModuleType, canonical: str) -> str:
    """取一个映射到 `canonical` 的「类别」字面量（从实现的唯一定义处反查）。"""
    for text, mapped in module.CATEGORY_TO_ENTRY_TYPE.items():
        if mapped == canonical:
            return text
    pytest.fail(
        f"`CATEGORY_TO_ENTRY_TYPE` 里没有映射到 {canonical!r} 的类别取值 "
        f"（实测 {dict(module.CATEGORY_TO_ENTRY_TYPE)}）⇒ 派生表本身缺一半，"
        f"该方向的分录导入后无从落值"
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _check_casing_agreement(
    specs: dict[str, Any], ledger_sheets: dict[str, Any], sheets: Sequence[str]
) -> None:
    """判据①：实现认定的「未登记」集合必须等于清单独立解析出的集合（不许两份）。

    真实面与合成面（替身清单）共用本函数 —— 两份口径会让合成夹具验的是另一套逻辑。
    """
    for sheet in sheets:
        entry = ledger_sheets.get(sheet)
        if not isinstance(entry, dict):
            pytest.fail(f"{_NOT_YET_LEDGER}：{sheet} 未登记于 `sheets` 段")
        declared = _ledger_entry_type_casing(entry)
        spec_values = _spec_field(specs[sheet], "entry_type_values")
        if declared is None:
            assert spec_values is None, (
                f"{sheet} 的清单 `handling` 没登记枚举大小写，但实现给出了 "
                f"{dict(spec_values) if spec_values else spec_values!r} ⇒ 实现在猜大小写。"
                f"猜错会让导入行从 AJE / RJE 两张表同时消失（filter 全不命中 = 静默丢行）"
            )
        else:
            assert spec_values is not None, (
                f"{sheet} 的清单已登记枚举形态 {declared}，但实现的 entry_type_values 是 None "
                f"⇒ 已登记的信息没被消费，导入不会写该键"
            )
            assert (spec_values["AJE"], spec_values["RJE"]) == declared, (
                f"{sheet} 实现登记 {dict(spec_values)} 与清单声明 {declared} 不一致"
            )


def _check_entry_type_import_behaviour(module: types.ModuleType, sheet: str) -> None:
    """判据②：真跑一次导入解析 —— 登记了就必须落**本 sheet 形态**，没登记就必须拒写 + 记 warning。

    `module` 既可是正式模块，也可是 `_exec_module_with_ledger` 用替身清单 exec 出来的克隆
    （合成面靠后者让「未登记」这条分支在 16 张真实条目全部登记后仍有实例）。
    """
    spec = module.X3_SHEET_SPECS[sheet]
    field = _spec_field(spec, "entry_type_field")
    values = _spec_field(spec, "entry_type_values")
    assert isinstance(field, str) and field, f"{sheet} 缺 entry_type_field"

    for canonical in ("AJE", "RJE"):
        text = _category_text_for(module, canonical)
        cells = [""] * len(module.COLUMN_ORDER)
        cells[0] = "行内容"
        cells[module.CATEGORY_COLUMN_INDEX] = text
        outcome = module.parse_workbook(_upload_bytes(module, sheet, [cells]), sheet)
        assert not outcome.errors, f"{sheet} 解析报错: {outcome.errors}"
        assert len(outcome.rows) == 1, f"{sheet} 应解析出 1 行，实测 {len(outcome.rows)}"
        row = outcome.rows[0]

        if values is None:
            assert field not in row, (
                f"{sheet} 的枚举大小写未登记，导入却写了 {field}={row.get(field)!r} ⇒ "
                f"实现在猜大小写。已实测存在小写形态的 sheet，猜错即静默丢行"
            )
            assert any("大小写" in w for w in outcome.warnings), (
                f"{sheet} 未写 {field} 键却没有任何 warning ⇒ 静默少字段"
                f"（warnings 实测 {outcome.warnings}）"
            )
        else:
            expected = values[canonical]
            assert row.get(field) == expected, (
                f"{sheet} 类别 {text!r}（规范值 {canonical}）应落**本 sheet 形态** "
                f"{expected!r}，实测 {row.get(field)!r}。跨 sheet 复用同一枚举常量会让 "
                f"小写形态的 sheet 导入行从两张 el-table 同时消失"
            )


def _deregister_casing(doc: dict[str, Any], sheet: str) -> str:
    """把某张的「取值 'X' | 'Y'」句式从替身清单里摘掉（= 造一张「未登记」sheet）。

    只摘枚举对、**保留**「AJE/RJE 标记」锚点 —— 连锚点一起摘会让实现在结构校验阶段就抛
    （「标记条目应恰有 1 处」），那验的是别的判据，不是「未登记时的导入行为」。
    """
    entry = doc["sheets"][sheet]
    hits = [
        i
        for i, item in enumerate(entry.get("unmapped_fields") or [])
        if isinstance(item, dict)
        and isinstance(item.get("handling"), str)
        and _ENTRY_TYPE_MARKER_DECL_RE.search(item["handling"])
    ]
    assert len(hits) == 1, (
        f"合成夹具锚点异常（ANCHOR-MISS）：{sheet} 的「AJE/RJE 标记」条目实测 {len(hits)} 处"
    )
    item = entry["unmapped_fields"][hits[0]]
    before = item["handling"]
    after, n = _ENTRY_TYPE_ENUM_DECL_RE.subn("〈合成夹具：本张枚举形态未登记〉", before)
    assert n == 1, (
        f"合成夹具锚点异常（ANCHOR-MISS）：{sheet} 的「取值」枚举对实测替换 {n} 处（须 1）"
    )
    assert _ENTRY_TYPE_MARKER_DECL_RE.search(after), f"{sheet} 摘枚举对时把标记锚点一起摘掉了"
    assert not _ENTRY_TYPE_ENUM_DECL_RE.search(after), f"{sheet} 摘完后仍解析出枚举对"
    item["handling"] = after
    return before


class TestEntryTypeCasingDrivesBehaviour:
    """`entry_type_values` 登记与否 ⇒ 导入是否写 entryType 键，逐张真跑判定。"""

    def test_unregistered_set_matches_ledger(self):
        """实现认定的「未登记」集合必须等于清单独立解析出的集合（不许两份）。"""
        _check_casing_agreement(_require_specs(), _ledger_sheets(), _X3_SHEETS)

    def test_all_sixteen_have_casing_registered(self):
        """任务 2.4 的目标态：16/16 都登记了枚举大小写（谁把某张退登记，谁打红）。

        这条同时是**合成面必要性的机器化说明**：它一绿就说明「未登记」分支在真实面
        实例数为 0 ⇒ 那条行为只能由 `TestEntryTypeUnregisteredBranchSynthetic` 承担。
        """
        specs = _require_specs()
        missing = sorted(
            s for s in _X3_SHEETS if _spec_field(specs[s], "entry_type_values") is None
        )
        assert not missing, (
            f"以下 sheet 的 AJE/RJE 枚举大小写尚未登记在 {_LEDGER_PATH.name}: {missing}"
            f"（共 {len(missing)}/{len(_X3_SHEETS)} 张）⇒ 导入不会写该字段键，"
            f"界面按 AJE / RJE 分区的视图看不到导入的行（R6.5 / R6.7 不可满足）。"
            f"补登去向 = 任务 2.4"
        )

    @pytest.mark.parametrize("sheet", _X3_SHEETS)
    def test_import_writes_entry_type_iff_casing_registered(self, sheet: str):
        _check_entry_type_import_behaviour(_require_module(), sheet)

    def test_registered_sheets_distinguish_both_directions(self):
        """已登记的 sheet 必须把两个方向落成**不同**的值（防「全落一个值」）。"""
        specs = _require_specs()
        registered = {
            s: _spec_field(specs[s], "entry_type_values")
            for s in _X3_SHEETS
            if _spec_field(specs[s], "entry_type_values") is not None
        }
        if not registered:
            pytest.fail(
                "16 张里没有任何一张登记了枚举大小写 ⇒ 本组的「已登记」分支全部空转，"
                "`test_import_writes_entry_type_iff_casing_registered` 只在检验「不写键」"
            )
        collapsed = {s: dict(v) for s, v in registered.items() if v["AJE"] == v["RJE"]}
        assert not collapsed, f"以下 sheet 的两个方向落同一个值: {collapsed}"

    def test_fallback_is_one_of_the_two_canonical_values(self):
        module = _require_module()
        assert module.ENTRY_TYPE_FALLBACK in set(module.CATEGORY_TO_ENTRY_TYPE.values()), (
            f"兜底值 {module.ENTRY_TYPE_FALLBACK!r} 不在派生表的值域 "
            f"{sorted(set(module.CATEGORY_TO_ENTRY_TYPE.values()))} 内"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-6b —— 「未登记 ⇒ 拒写键 + 记 warning」的合成夹具（任务 2.4 新增）
#
# 为什么必须有这一组：任务 2.4 把 12 张补登后，16/16 都有枚举形态 ⇒ 上一组那条双分支
# 判据的「未登记」分支**实例数归零 = 恒真空转**。空转的代价不是漏一条边角 case：
# 「未登记就猜大写」这个改法会让小写形态的 sheet（实测 `N5-3`）导入行从两张 el-table
# 同时消失 —— 而在全登记之后，这个改法**一条守卫都不会打红**。
#
# 判据形态：用替身清单摘掉某一张的「取值」句式造出「未登记」态，重新 exec 一份模块副本，
# 复用**同一个**行为判据函数 `_check_entry_type_import_behaviour` 真跑一次导入解析。
# 三层反空转：
#   * CONTROL —— 未摘任何登记的替身必须全部走「已登记」分支且写对形态（排除「怎么改都红」）
#   * 摘掉的那张必须转成「未登记」，**其余 15 张必须仍是已登记**（证明替身是最小改动）
#   * 摘取动作自带 ANCHOR-MISS 断言（命中数必须恰为 1）
# 三个受害样本刻意覆盖三种形态：`entryType` 字段名 / 11 项后缀的 M 族 / 唯一小写的 `N5-3`。
# ═══════════════════════════════════════════════════════════════════════════


#: 合成夹具的受害样本（覆盖三种形态，见上方注释块）
_SYNTHETIC_VICTIMS = ("L2-3", "M9-3", "N5-3")


class TestEntryTypeUnregisteredBranchSynthetic:
    """16 张全登记后，「未登记 ⇒ 拒写键 + warning」这条行为仍被真判。"""

    def test_control_clone_behaves_like_real_module(self):
        """CONTROL：未摘登记的替身副本，逐张的登记态与行为必须与正式模块一致。

        没有这一条，下面的红既可能来自「实现拒写键的逻辑对」，也可能来自「替身 exec
        本身就坏了」——那属 harness 缺陷（四态里的 ANCHOR-MISS），不是 RED。

        🔴 判据是「克隆 == 正式模块」而**不是**「16 张全已登记」：后者与
        `test_all_sixteen_have_casing_registered` 重复，且日后作业面新增一张未登记 sheet 时
        会以**错误的理由**（说替身不是最小改动）打红 —— 那正是 checkpoint 3 缺陷 A 那类
        「陈旧基线被动变红」。
        """
        doc = _ledger_doc_copy()
        module, hits = _exec_module_with_ledger(json.dumps(doc, ensure_ascii=False))
        assert hits >= 1, "模块 import 期间一次都没读清单 ⇒ 替身没生效，本组全部结论不成立"
        real = _require_specs()
        for sheet in _X3_SHEETS:
            clone_v = _spec_field(module.X3_SHEET_SPECS[sheet], "entry_type_values")
            real_v = _spec_field(real[sheet], "entry_type_values")
            assert (clone_v is None) == (real_v is None), (
                f"CONTROL：{sheet} 在未摘登记的替身里登记态与正式模块不同"
                f"（克隆 {dict(clone_v) if clone_v else None} vs 正式 "
                f"{dict(real_v) if real_v else None}）⇒ 替身或解析器有问题"
            )
            _check_entry_type_import_behaviour(module, sheet)

    @staticmethod
    def _pre_unregistered(doc: dict[str, Any]) -> list[str]:
        """替身**变异前**就已经是未登记的 sheet（正常应为空；作业面新增条目时可能非空）。"""
        sheets = doc.get("sheets") or {}
        return sorted(
            s
            for s in _X3_SHEETS
            if isinstance(sheets.get(s), dict) and _ledger_entry_type_casing(sheets[s]) is None
        )

    @pytest.mark.parametrize("victim", _SYNTHETIC_VICTIMS)
    def test_synthetic_unregistered_sheet_refuses_to_write_key(self, victim: str):
        """摘掉某张的「取值」句式 ⇒ 该张导入必须**不写**该字段键，且必须有含「大小写」的 warning。"""
        doc = _ledger_doc_copy()
        pre = self._pre_unregistered(doc)
        assert victim not in pre, (
            f"合成夹具选样异常（ANCHOR-MISS）：{victim} 在磁盘清单里本就未登记 ⇒ 摘取动作是空操作"
        )
        before = _deregister_casing(doc, victim)
        module, hits = _exec_module_with_ledger(json.dumps(doc, ensure_ascii=False))
        assert hits >= 1, "模块 import 期间一次都没读清单 ⇒ 替身没生效"

        specs = module.X3_SHEET_SPECS
        assert _spec_field(specs[victim], "entry_type_values") is None, (
            f"合成夹具：已从替身清单摘掉 {victim} 的枚举形态（原文 {before!r}），"
            f"实现却仍给出 {dict(_spec_field(specs[victim], 'entry_type_values') or {})} "
            f"⇒ 实现在猜大小写（或另有一份形态真源）"
        )
        unregistered = sorted(
            s for s in _X3_SHEETS if _spec_field(specs[s], "entry_type_values") is None
        )
        assert unregistered == sorted({*pre, victim}), (
            f"合成夹具只摘了 {victim}（变异前已未登记的是 {pre}），实现侧却认为 "
            f"{unregistered} 未登记 ⇒ 替身不是最小改动，本条结论无法归因到 {victim}"
        )

        # 复用真实面同一个判据函数：`values is None` 分支在这里**有实例**了；
        # 其余 sheet 仍走各自原本的分支 ⇒ 两条分支在同一次 exec 里都被真判
        for sheet in _X3_SHEETS:
            _check_entry_type_import_behaviour(module, sheet)

    @pytest.mark.parametrize("victim", _SYNTHETIC_VICTIMS)
    def test_synthetic_unregistered_set_agreement(self, victim: str):
        """「未登记集合 == 清单独立解析集合」在有未登记实例时仍成立（防两份真源）。

        全登记后 `test_unregistered_set_matches_ledger` 退化成「空集 == 空集」，
        本条给它补回实例：替身里至少多出这一张未登记，两侧必须都认出来且认得一样。
        """
        doc = _ledger_doc_copy()
        pre = self._pre_unregistered(doc)
        _deregister_casing(doc, victim)
        module, _hits = _exec_module_with_ledger(json.dumps(doc, ensure_ascii=False))

        ledger_sheets = doc.get("sheets")
        assert isinstance(ledger_sheets, dict), "替身清单缺 `sheets` 段"
        declared_none = sorted(
            s for s in _X3_SHEETS if _ledger_entry_type_casing(ledger_sheets[s]) is None
        )
        assert declared_none == sorted({*pre, victim}), (
            f"替身清单侧解析出的未登记集合应为 {sorted({*pre, victim})}，实测 {declared_none} "
            f"⇒ 摘取动作波及了别的 sheet（ANCHOR-MISS）"
        )
        _check_casing_agreement(module.X3_SHEET_SPECS, ledger_sheets, _X3_SHEETS)


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-7 —— 落库键面：三族分派 · 双族并写 · 逐 sheet 后缀全覆盖（任务 4.1 后半新增）
#
# 为什么必须有这一组：前半的判据面只覆盖「清单 ↔ specs」的**取值**对齐，
# 对「写库时到底爆出哪些键」零判据。本轮实测的两条高危静默变异都落在这个洞里：
#   * `per_field_plus_data` 改成只写 per-field ⇒ 界面（只读整行 JSON 族）永远读不到导入的行；
#   * `M9-3` 的 `ociBlock` 落库时被丢掉 ⇒ 逐字段族断档 + OCI 类别块往返后丢失。
# 两者都不会让任何既有守卫变红，也不会报错 —— 用户只看到「导入成功但表是空的」。
#
# 判据形态：对**落库键面的唯一构造点**真跑一次（纯函数，不连库），逐 sheet 按其登记的
# 键族核对键集；另用 AST 断言 `write_rows` 确实经由该构造点（防它变成无人调用的死函数）。
# 连库往返属 GS7（任务 13.4 `test_x3_roundtrip_live.py`）的半径，本组不越界。
# ═══════════════════════════════════════════════════════════════════════════


def _key_builder(module: types.ModuleType):
    builder = getattr(module, "_incoming_payloads", None)
    if not callable(builder):
        pytest.fail(
            f"{_NOT_YET_MODULE}：{_MODULE_NAME}._incoming_payloads 缺失 —— "
            f"「行列表 → 落库键」的唯一构造点不存在，落库键面无从判定"
        )
    return builder


def _calls_in_function(source_path: Path, func_name: str) -> set[str]:
    """AST 取某个顶层函数体内被调用的函数名集合（结构判据，不是字符串包含）。"""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            names: set[str] = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    callee = sub.func
                    if isinstance(callee, ast.Name):
                        names.add(callee.id)
                    elif isinstance(callee, ast.Attribute):
                        names.add(callee.attr)
            return names
    pytest.fail(f"{_NOT_YET_MODULE}：{source_path.name} 里找不到顶层函数 {func_name}")
    raise AssertionError("unreachable")  # pragma: no cover


_PROBE_ROWS = [{"description": "行一"}, {"description": "行二"}]


class TestWriteKeyExplosion:
    """落库键面按清单登记的键族爆炸，一个后缀都不许少。"""

    def test_write_rows_goes_through_the_single_key_builder(self):
        """`write_rows` 必须经由 `_incoming_payloads` ⇒ 本组判据不是在测死函数。"""
        if not _MODULE_PATH.is_file():
            pytest.fail(f"{_NOT_YET_MODULE}：缺 {_MODULE_PATH}")
        called = _calls_in_function(_MODULE_PATH, "write_rows")
        assert "_incoming_payloads" in called, (
            f"`write_rows` 体内没有对 `_incoming_payloads` 的调用（实测调用 {sorted(called)}）⇒ "
            f"落库键面另有构造点，本组判据会变成空转"
        )

    @pytest.mark.parametrize("sheet", _X3_SHEETS)
    def test_key_explosion_matches_declared_families(self, sheet: str):
        module = _require_module()
        specs = _require_specs()
        spec = specs[sheet]
        build = _key_builder(module)
        column = _spec_field(spec, "storage_field")

        produced = build(spec, _PROBE_ROWS)
        assert isinstance(produced, dict) and produced, (
            f"{sheet} 键爆炸产出为空（实测 {produced!r}）"
        )
        for item_id, payload in produced.items():
            assert isinstance(payload, dict) and column in payload, (
                f"{sheet} 的 {item_id} 载荷未落在列 {column!r} 上: {payload!r}"
            )

        raw_family = _spec_field(spec, "key_family")
        # `str(KeyFamily.SINGLE_JSON)` 在 py3.12 下是 `'KeyFamily.SINGLE_JSON'`（大写成员名），
        # 直接 str 比对会全不命中 ⇒ 取 `.value` 与清单登记的小写取值面对齐
        family = str(getattr(raw_family, "value", raw_family))
        assert family in _WRITE_KEY_FAMILIES, (
            f"{sheet} 的 key_family={family!r} 不在写入族取值面 {sorted(_WRITE_KEY_FAMILIES)} 内"
        )
        per_field_prefix = _spec_field(spec, "per_field_prefix")
        suffixes = tuple(_spec_field(spec, "per_field_suffixes") or ())
        data_prefix = _spec_field(spec, "data_key_prefix")
        data_suffix = _spec_field(spec, "data_key_suffix")
        n = len(_PROBE_ROWS)

        if family == "single_json":
            assert set(produced) == {_spec_field(spec, "item_id")}, (
                f"{sheet} 整表单键族应恰好爆出 1 个键 = item_id，实测 {sorted(produced)}"
            )
            parsed = json.loads(produced[_spec_field(spec, "item_id")][column])
            assert isinstance(parsed, list) and len(parsed) == n, (
                f"{sheet} 单键载荷应是 {n} 元素的 JSON 数组，实测 {parsed!r}"
            )
            return

        assert per_field_prefix and suffixes, (
            f"{sheet} 的写入族是 {family} 却没有逐字段族登记（prefix={per_field_prefix!r} "
            f"suffixes={suffixes!r}）"
        )
        per_field_keys = {
            f"{per_field_prefix}{row_no}-{suffix}"
            for row_no in range(1, n + 1)
            for suffix in suffixes
        }
        missing_pf = sorted(per_field_keys - set(produced))
        assert not missing_pf, (
            f"{sheet} 逐字段族缺 {len(missing_pf)} 个键: {missing_pf[:5]} ⇒ 族出现断档。"
            f"后缀表逐 sheet 承载（本张 {len(suffixes)} 项），少写任一后缀都是静默丢字段"
        )

        if family == "per_field_plus_data":
            assert data_prefix and data_suffix, f"{sheet} 声明了双族却没有整行 JSON 族登记"
            data_keys = {f"{data_prefix}{row_no}{data_suffix}" for row_no in range(1, n + 1)}
            missing_data = sorted(data_keys - set(produced))
            assert not missing_data, (
                f"{sheet} 是双键族（per-field + 整行 JSON），但整行 JSON 族缺 {missing_data} ⇒ "
                f"**两族必须都写**：per-field 供进度统计与跨表取数、整行 JSON 供界面读回（R6.6）。"
                f"只写 per-field ⇒ 用户导入成功但界面永远是空表"
            )
            expected_fields = set(_spec_field(spec, "per_field_suffix_to_field").values())
            for key in sorted(data_keys):
                payload = json.loads(produced[key][column])
                assert isinstance(payload, dict), f"{sheet} 的 {key} 载荷不是对象: {payload!r}"
                lost = sorted(expected_fields - set(payload))
                assert not lost, (
                    f"{sheet} 的整行 JSON 载荷缺字段 {lost}（应含 {sorted(expected_fields)}）⇒ "
                    f"界面读回时这些字段永久丢失"
                )
            assert set(produced) == per_field_keys | data_keys, (
                f"{sheet} 键集与两族之和不等：多出 "
                f"{sorted(set(produced) - per_field_keys - data_keys)}"
            )
        else:
            assert set(produced) == per_field_keys, (
                f"{sheet} 只登记了逐字段族，却多爆出 {sorted(set(produced) - per_field_keys)}"
            )

        standalone = set(_spec_field(spec, "standalone_item_ids") or ())
        collision = sorted(set(produced) & standalone)
        assert not collision, (
            f"{sheet} 往返键与表级独立键撞名 {collision} ⇒ 会把表级说明当行数据写掉"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-8 —— 解析后的行键面：占位列必须按 `field_keys` 的 None 位整批剔除
#
# design §D2 原先假定「`……`(F 列) 是唯一占位列」，任务 2.1 已实测推翻（`L2-3` 2 个、
# `N5-3` 6 个）。若实现按「只有 F 列」处理，多出来的占位列会带着内部临时键混进行模型
# 一路写进库 —— 不报错、不缺字段，只是把前端行模型污染成含 `__x3_placeholder_col_9`
# 之类的键。故判据钉在「解析出的行键集**恰好**等于清单声明的字段集」上。
# ═══════════════════════════════════════════════════════════════════════════


class TestParsedRowKeySurface:
    """`parse_workbook` 产出的行键集 == 清单声明的映射字段（+ 行标识 + 已登记的 entryType）。"""

    @pytest.mark.parametrize("sheet", _X3_SHEETS)
    def test_parsed_row_keys_match_ledger_fields(self, sheet: str):
        module = _require_module()
        specs = _require_specs()
        spec = specs[sheet]

        cells = [f"c{i}" for i in range(len(module.COLUMN_ORDER))]
        cells[module.CATEGORY_COLUMN_INDEX] = _category_text_for(module, "AJE")
        for idx, key in enumerate(_spec_field(spec, "field_keys")):
            if key is not None and _is_numeric_probe_field(module, key):
                cells[idx] = 1
        outcome = module.parse_workbook(_upload_bytes(module, sheet, [cells]), sheet)
        assert not outcome.errors, f"{sheet} 解析报错: {outcome.errors}"
        assert len(outcome.rows) == 1, f"{sheet} 应解析出 1 行，实测 {len(outcome.rows)}"
        row = outcome.rows[0]

        mapped = {k for k in _spec_field(spec, "field_keys") if k is not None}
        expected = set(mapped) | {"id"}
        if _spec_field(spec, "entry_type_values") is not None:
            expected.add(_spec_field(spec, "entry_type_field"))

        leaked = sorted(k for k in row if isinstance(k, str) and "placeholder" in k)
        assert not leaked, (
            f"{sheet} 解析结果里残留占位键 {leaked} ⇒ 占位列没被整批剔除。"
            f"本张的占位位是 field_keys 的 None 位（实测 "
            f"{[i for i, k in enumerate(_spec_field(spec, 'field_keys')) if k is None]}），"
            f"**不是只有 F 列**"
        )
        assert None not in row, (
            f"{sheet} 解析结果里出现 None 作字典键 ⇒ 占位位被原样当成字段名"
        )
        assert set(row) == expected, (
            f"{sheet} 行键集不符：多 {sorted(set(row) - expected)} / 缺 "
            f"{sorted(expected - set(row))}（应为 {sorted(expected)}）"
        )


def _is_numeric_probe_field(module: types.ModuleType, key: str) -> bool:
    """借被测实现所复用的公共判据判「这一列是数值列」（探针填值用，避免类型噪声）。"""
    from app.routers.wp_render_strategies._cycle_import_export_common import is_numeric_field_key

    del module  # 只为签名对称，实际判据取自公共模块
    return is_numeric_field_key(key)


# ═══════════════════════════════════════════════════════════════════════════
# 类 B-9 —— 残留族键清理的**作用域**（R11.7；本轮变异 M8 暴露的守卫缺陷）
#
# 变异「残留清理改成不分策略一律清」在补本组之前判 GREEN：判据面 167 passed 全绿。
# 后果不是显示错误而是**删用户数据** —— `fill-empty`（语义：只填空位）会把行号超出的
# 已有行删掉，`reject`（语义：有数据就整表拒收）同理。这类越界只有连库往返才看得见，
# 而连库属 GS7（任务 13.4）半径 ⇒ 必须把判定抽成纯函数后在此判。
# ═══════════════════════════════════════════════════════════════════════════


_CONFLICT_STRATEGIES = ("overwrite", "fill-empty", "reject")


class TestResidualPurgeScope:
    """清理只在 `overwrite` 下发生，且整表单键族永不清理。"""

    def test_write_rows_delegates_purge_decision(self):
        """`write_rows` 必须经由 `_should_purge_residual` ⇒ 本组不是在测死函数。"""
        if not _MODULE_PATH.is_file():
            pytest.fail(f"{_NOT_YET_MODULE}：缺 {_MODULE_PATH}")
        called = _calls_in_function(_MODULE_PATH, "write_rows")
        assert "_should_purge_residual" in called, (
            f"`write_rows` 体内没有对 `_should_purge_residual` 的调用（实测 {sorted(called)}）⇒ "
            f"清理作用域的判定另有出处，本组判据会变成空转"
        )

    @pytest.mark.parametrize("strategy", _CONFLICT_STRATEGIES)
    @pytest.mark.parametrize("sheet", _X3_SHEETS)
    def test_purge_only_under_overwrite(self, sheet: str, strategy: str):
        module = _require_module()
        spec = _require_specs()[sheet]
        decide = getattr(module, "_should_purge_residual", None)
        if not callable(decide):
            pytest.fail(f"{_NOT_YET_MODULE}：缺 `_should_purge_residual`（清理作用域唯一判定处）")

        raw_family = _spec_field(spec, "key_family")
        family = str(getattr(raw_family, "value", raw_family))
        expected = strategy == "overwrite" and family != "single_json"
        actual = decide(spec, strategy)
        assert actual is expected, (
            f"{sheet} / strategy={strategy!r}：清理决策应为 {expected}，实测 {actual}。"
            f"R11.7 —— 清理是**破坏性**操作，只许在 overwrite 下生效："
            f"`fill-empty` 的语义是只填空位、`reject` 在有数据时整表拒收，"
            f"两者若也清理就是在删用户已编制的行"
        )

    @pytest.mark.parametrize("sheet", _X3_SHEETS)
    def test_residual_scope_excludes_standalone_and_kept_rows(self, sheet: str):
        """清理面 = 行号 > 保留行数 的族键；表级独立键与保留行的键一个都不许进。"""
        module = _require_module()
        spec = _require_specs()[sheet]
        raw_family = _spec_field(spec, "key_family")
        if str(getattr(raw_family, "value", raw_family)) == "single_json":
            pytest.skip("整表单键族无残留概念（已由 test_purge_only_under_overwrite 覆盖）")

        build = _key_builder(module)
        residual_fn = getattr(module, "_residual_item_ids", None)
        if not callable(residual_fn):
            pytest.fail(f"{_NOT_YET_MODULE}：缺 `_residual_item_ids`")

        stored = list(build(spec, [{}, {}, {}]))
        standalone = list(_spec_field(spec, "standalone_item_ids") or ())
        kept_keys = set(build(spec, [{}]))
        residual = residual_fn(spec, stored + standalone, 1)

        assert residual, f"{sheet} 库存 3 行只保留 1 行，清理面却是空的"
        leaked = sorted(set(residual) & set(standalone))
        assert not leaked, (
            f"{sheet} 清理面里出现表级独立键 {leaked} ⇒ 会删掉用户写的调整说明/审计结论"
        )
        kept_leak = sorted(set(residual) & kept_keys)
        assert not kept_leak, f"{sheet} 清理面里出现**保留行**的键 {kept_leak} ⇒ 会删掉刚导入的行"
        assert set(residual) <= set(stored), (
            f"{sheet} 清理面越出库存键集: {sorted(set(residual) - set(stored))}"
        )
