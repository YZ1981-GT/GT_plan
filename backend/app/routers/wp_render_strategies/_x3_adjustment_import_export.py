"""16 张 X-3 调整分录汇总表的共享实现（spec `x3-adjustment-entry-import-export` 任务 4.1）

作业面 = `L2-3` · `L6-3` · `M1-3`~`M10-3` · `N1-3` · `N2-3` · `N3-3` · `N5-3`
（16 张，design 用户裁决 1：`N5-3` 纳入，零 `pending_manual`）。

## 一、数据层（design §C1 / §D2）

1. `X3_SHEET_SPECS` —— **模块导入时**从 `backend/data/adjustment_ie_contract.json`
   （= Key_Ledger，design §C6 的单一真源）装载并做结构校验。
2. `COLUMN_ORDER` —— 由清单 `column_map[].col` 派生，是那 10 个源模板列头字面量在
   Python 侧的**唯一定义处**（源模板第 5 行是列面真源，GS2 用 openpyxl 直读三向比对）。
3. 三族 item_id 生成器：`single_json_item_id` / `per_field_item_id` / `data_item_id`。
4. `CATEGORY_TO_ENTRY_TYPE` —— B 列「类别」→ AJE/RJE 的派生映射表（唯一定义处）；
   `CATEGORY_COLUMN_INDEX` 由它与 `COLUMN_ORDER` 反查得出，不写列标签字面量。

## 二、执行层

* `build_template_workbook` / `build_data_workbook` / `parse_workbook` —— 一律复用
  `_cycle_import_export_common` 的 `build_workbook_template` / `parse_upload_xlsx` /
  `parse_row_by_headers(expected_headers=…)` / `export_row_by_keys`（R1.5：现存两套已够，
  不造第三套 xlsx 构建/解析）。列面用 `COLUMN_ORDER`、sheet 名用 `spec.sheet_name`。
* `load_rows` —— 按 `spec.read_family` 取族；`NONE`（design E21 的四张）回落到写入族并
  在 `warnings` 标注。
* `write_rows` —— 按 `spec.key_family` 三族分派；`per_field_plus_data` **两族都写**
  （per-field 供进度统计与跨表取数、整行 JSON 供界面读回，R6.6）；冲突策略复用
  `conflict_resolver.resolve_conflict`；`overwrite` 下清理行号超出的残留族键（R11.7）。
* `attach_shape_a_routes` —— 三个 **POST** `/api/workpapers/{wp_id}/{短前缀}/{三态}`，
  `sheet` 必填，鉴权依赖与 16 个宿主模块既有三态端点逐字相同。

## 🔴 后半的一条已知缺口（施工期实测，须显式知道）

**12 张的 AJE/RJE 枚举大小写在清单未登记**（`L2-3` `L6-3` `M1-3`~`M10-3`）：只有 N 族
4 张登记了形态，其中 `N5-3` 实测是**小写** `aje` / `rje`。故本模块对未登记的 12 张
**拒绝写 entryType 键**并在 `warnings` 记明原因（`_entry_type_literal` 返回 `None`），
**刻意不默认成规范大写** —— 猜错大小写会让导入行从 AJE / RJE 两张 el-table 同时消失
（filter 全不命中 = 静默丢行，这是比「字段缺失」更难查的形态）。

不写该键的后果同样已实测：8 张有读回路径的 sheet 在读回侧都有
`data.type || 'AJE'` 之类的兜底 ⇒ 被归为 RJE 的行会显示成 AJE（值错，不是不可见）；
4 张 `read_family = none` 的由任务 4.2 的读回实现决定。**收口 = 先补清单登记（任务 2.4）**，
补完后本模块无需改动即自动落对大小写（值全部走 `spec.entry_type_values`）。

> **状态更新（任务 2.4 已执行）**：12 张已按前端实测逐张补登（实测全部为大写
> `AJE` / `RJE`，逐张证据行落在清单各自的 `handling` 里）⇒ 现在 16/16 都有形态，
> 本模块**未改一行代码**即开始写该键（值全部来自 `spec.entry_type_values`）。
> 上面这段「拒写 + warning」的分支**仍然活着**（清单日后新增 sheet 时立即生效），
> 其行为由 `test_x3_key_ledger.TestEntryTypeUnregisteredBranchSynthetic` 的
> 合成夹具持续判定 —— 真实条目全部登记后那条分支实例数归零，只靠真实面会恒真空转。

## 🔴 为什么 Python 侧一个键/后缀/列名字面量都不许写

平台最贵的一类假绿 = 后端写死一份键、清单写另一份，两边各自自洽、守卫全绿、
用户导入后界面读不到（Orphan_Key）。故本模块的**全部**取值来自清单，`GS1`
（`backend/tests/test_x3_key_ledger.py`）用两条判据双向锁死：

* 结构判据：剥注释后本文件源码不得出现任何 X-3 键字面量；
* **行为**判据：把清单内容重定向成替身重新 exec 本模块，`X3_SHEET_SPECS` 必须跟着变
  （`json.load` 存在 ≠ 装载结果被采用 —— 同一模块里再写一份硬编码覆盖它，grep 照样绿）。

⇒ 本文件里出现的 X-3 键/列名一律只在 docstring 与 `#` 注释里（那两处会被剥掉），
   **代码行内不得出现**。

## 🔴 逐 sheet 从清单读，禁套公式 —— 清单实测推翻 design 预设的 9 条分叉

| # | 分叉 | 实测 | 本模块的处理位置 |
|---|---|---|---|
| 1 | 族前缀单/双混杂 | `L6-3`/`M1-3`/`M2-3`/`M3-3` 是双前缀（`M3-M3-3-entry-`），`M4-3`~`M10-3` 与 N 族是单前缀 | `per_field_prefix` / `data_key_prefix` 逐 sheet 取 `key_families.*.prefix`，**不按 `{X}-{X}-3-entry-` 套公式** |
| 2 | 后缀数普遍 10、`M9-3` 为 11（多 `ociBlock`） | `M9-3` 的 `-ociBlock` 键必须落库保留 | `per_field_suffixes` 逐 sheet 承载，无全局后缀常量 |
| 3 | 写入列两种 | 机制②（`saveBatch`/`debouncedSave`）⇒ `remark`（12 张）；机制①（`setField`）⇒ `conclusion`（4 张 N 族） | `storage_field` 取清单值，并断言 == `_MECHANISM_STORAGE_FIELD[mechanism]` |
| 4 | 索引列字段名三种 | `indexRef`(L2/L6) · `refIndex`(M 族 + N1/N3) · `indexNo`(N2)；`N5-3` 该列无字段 | 一律走 `field_keys`（与 `COLUMN_ORDER` 同序），本模块不认识「索引字段」这个概念 |
| 5 | 金额字段名两种 | 普遍 `debitAmount`/`creditAmount`，`N5-3` 是 `debit`/`credit` | 同上，走 `field_keys` |
| 6 | `type` 大小写两种 | N1/N2/N3 大写 `AJE`/`RJE`，**`N5-3` 小写 `aje`/`rje`** | `entry_type_field` + `entry_type_values` 逐 sheet 承载。跨 sheet 复用同一枚举常量会让 `N5-3` 的导入行从两张 el-table 同时消失（filter 全不命中 = 静默丢行） |
| 7 | 占位列数不一 | 普遍 1（F 列 `……`）· `L2-3` 为 2（F+J）· `N5-3` 为 6（B/C/E/F/I/J） | `field_keys` 的 `None` 位即占位位，**不假定只有 F 列** |
| 8 | `sample_row` 只有 `L2-3` 非空 | 其余 15 张为 `null` | `sample_row` 逐 sheet 取，`None` 表示该 sheet 无示例行 |
| 9 | 表级独立键 | `M2-M2-3-adjustment-note` / `M8-3-adjustmentNote` / `N5-3-audit-notes` / `N5-3-audit-conclusion` | 收进 `standalone_item_ids` 并断言与往返键**不重合**；导入导出往返一律不碰 |

## `read_family` 的取值面比 design 宽（据实登记）

design §Data Models 的 `KeyFamily` 只列了 `single_json` / `per_field` /
`per_field_plus_data` / `none`，但清单 `read_family` 实测有 `data`（8 张 M 族读的是
`-data` 族而不是逐字段族）。故本模块的 `KeyFamily` 枚举含 5 个成员，并用
`_WRITE_FAMILIES` / `_READ_FAMILIES` 两个子集分别约束「写入族」与「读取族」。

## 异常纪律（R10.11）

结构校验一律 `logger.error` + 抛 `X3ContractError`；**禁** `except Exception:
logger.warning` 式兜空 —— 静默兜空会让「清单字段拼错 / 键族登记漏项」表现成
「本项目无此数据」，四层静态检查全绿而只有用户能发现。

## 本文件不写 `from __future__ import annotations`（**现在是纯风格选择，不再是被迫**）

前半交付时它是被迫的：GS1 的装载探针（`test_specs_really_loaded_from_ledger` →
`_exec_module_with_ledger`）用 `module_from_spec` + `exec_module` 载入本模块的克隆副本，
却没先把克隆名注册进 `sys.modules`；CPython 3.12 的 `dataclasses._process_class` 对
**字符串形态**的字段注解（正是该 future import 的效果）会走 `_is_type(...)` →
`sys.modules.get(cls.__module__).__dict__`，克隆名查不到就是 `None.__dict__`
⇒ `AttributeError: 'NoneType' object has no attribute '__dict__'`，表现成「装载探针失败」
而与本模块逻辑毫无关系。

该 harness 缺陷已在后半修掉（GD-3：`exec_module` 前注册、`finally` 删）。三态复测：
①无 future import + 修好的 harness ⇒ 全绿；②**加** future import + 修好的 harness ⇒ 全绿；
③加 future import + 退回旧 harness ⇒ 复现 `dataclasses.py:749` 的 `AttributeError`。
故「加」已经安全；此处仍不加，仅因 Python ≥ 3.10 下 `str | None` / `tuple[str, ...]`
运行期原生可用、本模块无前向引用需求 ⇒ 加了零收益。**别把这段当成「必须不加」的禁令。**
"""

import io
import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, NamedTuple
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    export_row_by_keys,
    import_rows_generic,
    is_numeric_field_key,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    workbook_to_response,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CATEGORY_COLUMN_INDEX",
    "CATEGORY_TO_ENTRY_TYPE",
    "COLUMN_ORDER",
    "ENTRY_TYPE_FALLBACK",
    "ImportOutcome",
    "KeyFamily",
    "LEDGER_PATH",
    "Mechanism",
    "ParseOutcome",
    "X3ContractError",
    "X3SheetSpec",
    "X3_SHEET_SPECS",
    "attach_shape_a_routes",
    "build_data_workbook",
    "build_template_workbook",
    "data_item_id",
    "derive_entry_type",
    "load_rows",
    "parse_workbook",
    "per_field_item_id",
    "sheet_spec",
    "single_json_item_id",
    "write_rows",
]

#: Key_Ledger 单一真源（design §C6）。`parents[3]` = `backend/`，故 pytest 从仓库根跑也定位得到。
LEDGER_PATH = Path(__file__).resolve().parents[3] / "data" / "adjustment_ie_contract.json"


class X3ContractError(RuntimeError):
    """契约清单结构校验失败 —— 缺字段 / 类型不符 / 自相矛盾。

    刻意用异常而非「兜空 + warning」：本模块是 16 张 sheet 的取数与落库真源，
    兜空会把登记错误伪装成「这张表没数据」。
    """


class KeyFamily(str, Enum):
    """键族。前三个可作写入族，后四个（含 `NONE`）可作读取族。"""

    SINGLE_JSON = "single_json"
    PER_FIELD = "per_field"
    PER_FIELD_PLUS_DATA = "per_field_plus_data"
    DATA = "data"
    NONE = "none"


class Mechanism(str, Enum):
    """前端持久化机制（design E18）。`storage_field` 由它推导。"""

    FORMDATA_SETFIELD = "formdata_setfield"
    ADJUSTMENT_SAVEBATCH = "adjustment_savebatch"


#: 写入族取值面（`key_family`）
_WRITE_FAMILIES = frozenset(
    {KeyFamily.SINGLE_JSON, KeyFamily.PER_FIELD, KeyFamily.PER_FIELD_PLUS_DATA}
)

#: 读取族取值面（`read_family`）。含 `DATA`（M 族界面只读整行 JSON 族）与 `NONE`
#: （design E21 的四张：界面零读回路径，由任务 4.2 补齐）。
_READ_FAMILIES = frozenset(
    {KeyFamily.SINGLE_JSON, KeyFamily.PER_FIELD, KeyFamily.DATA, KeyFamily.NONE}
)

#: 机制 ⇒ 写入列（design E18，16/16 无例外）。清单登记的 `storage_field` 必须与它一致。
_MECHANISM_STORAGE_FIELD: dict[Mechanism, str] = {
    Mechanism.FORMDATA_SETFIELD: "conclusion",
    Mechanism.ADJUSTMENT_SAVEBATCH: "remark",
}

#: `key_family` ⇒ 该 sheet 必须登记的键族名（清单 `key_families` 的键）
_REQUIRED_FAMILIES: dict[KeyFamily, tuple[KeyFamily, ...]] = {
    KeyFamily.SINGLE_JSON: (KeyFamily.SINGLE_JSON,),
    KeyFamily.PER_FIELD: (KeyFamily.PER_FIELD,),
    KeyFamily.PER_FIELD_PLUS_DATA: (KeyFamily.PER_FIELD, KeyFamily.DATA),
}

# ── AJE / RJE 派生（design §D2 / R3.5）────────────────────────────────────────
# 规范取值只在这里各出现一次，`CATEGORY_TO_ENTRY_TYPE` 与两条正则都由它们拼出，
# 避免同一枚举值在文件里散落多份。
_ENTRY_TYPE_AJE = "AJE"
_ENTRY_TYPE_RJE = "RJE"

#: B 列「类别」→ `entryType` 的派生映射表，**唯一定义处**（design §D2）。
#: 本轮只定义；消费（导入时按行派生 + 非枚举值记 warning 落 `ENTRY_TYPE_FALLBACK`）
#: 在任务 4.1 后半的 `parse_workbook` / `write_rows`。
CATEGORY_TO_ENTRY_TYPE: dict[str, str] = {
    "账项调整": _ENTRY_TYPE_AJE,
    "报表调整": _ENTRY_TYPE_RJE,
    "其他": _ENTRY_TYPE_AJE,
}

#: `category` 为空 / 非枚举值时的落值（design §D2 已知限制：会把「其他」类 RJE 变成 AJE，
#: 故后半必须同时在 `warnings` 记行号，不得静默）。
ENTRY_TYPE_FALLBACK = _ENTRY_TYPE_AJE

#: 清单 `unmapped_fields[].handling` 里「AJE/RJE 标记」这一句是该 sheet 的
#: entryType 字段声明处（16/16 各恰一处，实测唯一）。
#: 🔴 不能改用「handling 里出现 AJE」——`N2-3` 的 `accountCode` 条目提到 `ajeNetAmount`，
#: 大写化后含 `AJE`，会命中第二条。
_ENTRY_TYPE_MARKER_RE = re.compile(rf"{_ENTRY_TYPE_AJE}\s*/\s*{_ENTRY_TYPE_RJE}\s*标记")

#: 清单 `handling` 里以「取值」引出的枚举字面量对，例如「取值 'aje' | 'rje'」。
#: 只认「取值」引出的那一对：`N5-3` 的同一句里还有一处对照用的大写形态
#: （「与 N1-3 / N2-3 / N3-3 的大写 'AJE' | 'RJE' 相反」），不带「取值」前缀。
_ENTRY_TYPE_ENUM_RE = re.compile(
    r"取值\s*['\"]([A-Za-z]{2,8})['\"]\s*\|\s*['\"]([A-Za-z]{2,8})['\"]"
)


@dataclass(frozen=True)
class X3SheetSpec:
    """一张 X-3 的运行期规格。全部字段派生自 Key_Ledger（+ `sheet_name` 取 ACNR catalog）。"""

    #: sheet 码，如 `M4-3`（清单 `sheets` 的键）
    sheet_code: str
    #: 所属循环底稿码，如 `M4`（清单 `cycle`）
    cycle: str
    #: 短前缀，如 `m4`（= `cycle` 小写；与 catalog `parent_wp_code` 交叉锁死）
    api_prefix: str
    #: 导出 workbook 的 sheet 名 = ACNR catalog `sheet_name`（R3.8；与源模板 tab 名逐字一致）
    sheet_name: str
    #: 清单 `item_id`（逐字段族下是族键通配串，bulk 不按它取数 —— 见 design §manifest 条目）
    item_id: str
    #: 写入族
    key_family: KeyFamily
    #: 界面实际读的族；`NONE` = 零读回路径（design E21 四张，任务 4.2 补齐）
    read_family: KeyFamily
    #: 前端持久化机制
    mechanism: Mechanism
    #: 落库列（`remark` | `conclusion`），由 `mechanism` 推导并与清单登记值双向锁死
    storage_field: str
    #: 与 `COLUMN_ORDER` 同序、同长；`None` = 该列无前端字段（占位列）
    field_keys: tuple[str | None, ...]
    #: 逐字段族前缀（单/双前缀逐 sheet 不同）；非逐字段族为 None
    per_field_prefix: str | None
    #: 逐字段族后缀（`M9-3` 为 11 项，含 `ociBlock`）；非逐字段族为空
    per_field_suffixes: tuple[str, ...]
    #: 后缀 → 前端行字段名
    per_field_suffix_to_field: Mapping[str, str]
    #: 整行 JSON 族前缀；无该族为 None
    data_key_prefix: str | None
    #: 整行 JSON 族后缀（清单登记值已含前导分隔符）；无该族为 None
    data_key_suffix: str | None
    #: 读回宿主符号（清单 `read_host`）
    read_host: str | None
    #: 读回数据源（`formData.allResponses` | `props.allResponses`）——决定 `@imported` 重载谁
    read_source: str | None
    #: 源模板第 5 行无对应列的前端字段（`type` / `index` / `ociBlock` 等）
    extra_fields: tuple[str, ...]
    #: 源模板示例行（仅 `L2-3` 非空，design E13）
    sample_row: tuple[str, ...] | None
    #: AJE/RJE 标记字段名（`L2-3` 是 `entryType`，其余 15 张是 `type`）
    entry_type_field: str
    #: 规范值 → 本 sheet 实际字面量（`N5-3` 为小写）。**None = 清单未登记该 sheet 的大小写**
    entry_type_values: Mapping[str, str] | None
    #: 表级独立键（调整说明 / 审计说明 / 审计结论）——导入导出往返一律不碰
    standalone_item_ids: tuple[str, ...]
    #: 取得依据（design R2.2 的 `Provenance`）
    provenance: Mapping[str, Any]


# ═══════════════════════════════════════════════════════════════════════════
# 取值 helper —— 每个都 fail-loud（缺字段 / 类型不符即抛，不返回兜底值）
# ═══════════════════════════════════════════════════════════════════════════


def _fail(where: str, detail: str) -> None:
    msg = f"X-3 契约清单结构校验失败 [{where}]: {detail}（真源 {LEDGER_PATH}）"
    logger.error("%s", msg)
    raise X3ContractError(msg)


def _req_str(entry: Mapping[str, Any], key: str, where: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail(where, f"字段 {key!r} 必须是非空字符串，实测 {type(value).__name__}: {value!r}")
    return value  # type: ignore[return-value]


def _opt_str(entry: Mapping[str, Any], key: str, where: str) -> str | None:
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _fail(where, f"字段 {key!r} 应为非空字符串或 null，实测 {type(value).__name__}: {value!r}")
    return value  # type: ignore[return-value]


def _req_list(entry: Mapping[str, Any], key: str, where: str) -> list[Any]:
    value = entry.get(key)
    if not isinstance(value, list) or not value:
        _fail(where, f"字段 {key!r} 必须是非空数组，实测 {type(value).__name__}: {value!r}")
    return list(value)  # type: ignore[arg-type]


def _req_mapping(entry: Mapping[str, Any], key: str, where: str) -> Mapping[str, Any]:
    value = entry.get(key)
    if not isinstance(value, Mapping) or not value:
        _fail(where, f"字段 {key!r} 必须是非空对象，实测 {type(value).__name__}: {value!r}")
    return value  # type: ignore[return-value]


def _req_str_list(entry: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    items = _req_list(entry, key, where)
    bad = [(i, v) for i, v in enumerate(items) if not isinstance(v, str) or not v.strip()]
    if bad:
        _fail(where, f"字段 {key!r} 的第 {[i for i, _ in bad]} 项不是非空字符串: {[v for _, v in bad]}")
    return tuple(items)


def _as_enum(raw: Any, enum_cls: type[Enum], allowed: frozenset[Any], key: str, where: str) -> Any:
    if not isinstance(raw, str):
        _fail(where, f"字段 {key!r} 必须是字符串，实测 {type(raw).__name__}: {raw!r}")
    try:
        member = enum_cls(raw)
    except ValueError:
        _fail(
            where,
            f"字段 {key!r} 取值 {raw!r} 不在 {enum_cls.__name__} 取值面 "
            f"{sorted(m.value for m in enum_cls)} 内",
        )
        raise  # pragma: no cover - _fail 必抛
    if member not in allowed:
        _fail(
            where,
            f"字段 {key!r} 取值 {raw!r} 不在本字段允许的子集 "
            f"{sorted(m.value for m in allowed)} 内",
        )
    return member


# ═══════════════════════════════════════════════════════════════════════════
# 清单读取与结构校验
# ═══════════════════════════════════════════════════════════════════════════


def _read_ledger() -> Mapping[str, Any]:
    """读并解析 Key_Ledger。任何 I/O / 解析失败一律记 ERROR 并上抛。"""
    try:
        raw = LEDGER_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("X-3 契约清单读取失败: %s (%s)", LEDGER_PATH, exc)
        raise X3ContractError(f"X-3 契约清单读取失败: {LEDGER_PATH}") from exc
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("X-3 契约清单 JSON 解析失败: %s (%s)", LEDGER_PATH, exc)
        raise X3ContractError(f"X-3 契约清单 JSON 解析失败: {LEDGER_PATH}") from exc
    if not isinstance(doc, Mapping):
        _fail("根", f"清单根必须是对象，实测 {type(doc).__name__}")
    return doc


def _select_x3_entries(doc: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """从清单 `sheets` 段挑出 X-3 条目。

    判据 = 条目登记了 `key_family`（逐字段/整表 JSON 写入族声明）。这是 X-3 条目独有的
    字段：清单里另外 14 张工厂 sheet（I / K 族）都没有它 —— 与既有守卫
    `test_adjustment_ie_contract_guard._is_pending_x3_shared` 同一口径，不另立第二份判据。

    章节号不写字面量：改为断言 16 张的 sheet 码「循环段 == `cycle`」且「章节段全体唯一」
    —— 一旦别的章节（如审定表 `K1-4`）被误加 `key_family`，章节段就会出现两种而打红，
    不会被静默吞掉。
    """
    sheets = doc.get("sheets")
    if not isinstance(sheets, Mapping) or not sheets:
        _fail("sheets", f"`sheets` 段必须是非空对象，实测 {type(sheets).__name__}")

    bad_shape = [code for code, entry in sheets.items() if not isinstance(entry, Mapping)]
    if bad_shape:
        _fail("sheets", f"以下条目不是对象: {sorted(bad_shape)}")

    selected = {
        code: entry
        for code, entry in sheets.items()
        if isinstance(entry, Mapping) and entry.get("key_family")
    }
    if not selected:
        _fail(
            "sheets",
            "没有任何条目登记 `key_family` ⇒ X-3 作业面为空。要么清单被回退到任务 2.1 之前，"
            "要么选择判据失效 —— 两者都不得当成「本项目无此数据」放过",
        )

    sections: dict[str, list[str]] = {}
    for code, entry in selected.items():
        cycle = _req_str(entry, "cycle", code)
        head, sep, section = code.partition("-")
        if not sep or head != cycle or not section.isdigit():
            _fail(
                code,
                f"sheet 码与 `cycle` 不自洽：cycle={cycle!r}，码拆解为 {head!r} + {section!r}",
            )
        sections.setdefault(section, []).append(code)
    if len(sections) != 1:
        _fail(
            "sheets",
            "登记了 `key_family` 的条目跨多个章节段 "
            f"{ {k: sorted(v) for k, v in sections.items()} } —— 本模块作业面只含调整分录汇总表一档",
        )
    return selected


def _column_labels(entry: Mapping[str, Any], code: str) -> tuple[str, ...]:
    """取该 sheet 的 `column_map[].col` 列面，并校验 map 自身结构。"""
    cells = _req_list(entry, "column_map", code)
    labels: list[str] = []
    fields: list[str | None] = []
    letters: list[str] = []
    for idx, cell in enumerate(cells):
        where = f"{code}.column_map[{idx}]"
        if not isinstance(cell, Mapping):
            _fail(where, f"必须是对象，实测 {type(cell).__name__}")
            continue  # pragma: no cover - _fail 必抛
        labels.append(_req_str(cell, "col", where))
        letters.append(_req_str(cell, "letter", where))
        field_name = cell.get("field")
        if field_name is not None and (not isinstance(field_name, str) or not field_name.strip()):
            _fail(where, f"`field` 应为非空字符串或 null，实测 {field_name!r}")
        fields.append(field_name)

    if len(set(labels)) != len(labels):
        _fail(code, f"`column_map` 出现重复列头: {labels}")
    if len(set(letters)) != len(letters) or letters != sorted(letters):
        _fail(code, f"`column_map` 的 letter 序列必须唯一且升序，实测 {letters}")

    declared = _req_list(entry, "field_keys", code)
    if [None if v is None else v for v in declared] != fields:
        _fail(
            code,
            "`field_keys` 与 `column_map[].field` 不一致（两处会成为两份真源）：\n"
            f"  field_keys  = {declared}\n  column_map  = {fields}",
        )
    return tuple(labels)


def _entry_type_declaration(entry: Mapping[str, Any], code: str) -> tuple[str, Mapping[str, str] | None]:
    """从 `unmapped_fields` 取 AJE/RJE 标记字段名与（若已登记的）本 sheet 枚举大小写。

    返回 `(字段名, {规范值: 本 sheet 字面量} | None)`。`None` 表示**清单未登记**该 sheet
    的大小写形态（实测 12 张如此：`L2-3` `L6-3` `M1-3`~`M10-3`）——刻意不默认成规范大写：
    `N5-3` 正是靠登记才发现它是小写，未登记的那 12 张同样需要先补登记再消费，
    否则会重演「导入行落错大小写 ⇒ 界面 filter 全不命中 ⇒ 静默丢行」。
    """
    unmapped = _req_list(entry, "unmapped_fields", code)
    hits: list[Mapping[str, Any]] = []
    for idx, item in enumerate(unmapped):
        if not isinstance(item, Mapping):
            _fail(f"{code}.unmapped_fields[{idx}]", f"必须是对象，实测 {type(item).__name__}")
            continue  # pragma: no cover - _fail 必抛
        handling = item.get("handling")
        if isinstance(handling, str) and _ENTRY_TYPE_MARKER_RE.search(handling):
            hits.append(item)
    if len(hits) != 1:
        _fail(
            code,
            f"`unmapped_fields` 里「AJE/RJE 标记」声明应恰有 1 处，实测 {len(hits)} 处"
            f"（命中字段 {[h.get('field') for h in hits]}）—— R3.5 要求每张都登记该字段；"
            "登记文案改动会在此打红，属有意的 fail-loud",
        )
    marker = hits[0]
    field_name = _req_str(marker, "field", f"{code}.unmapped_fields[AJE/RJE]")

    pairs = _ENTRY_TYPE_ENUM_RE.findall(str(marker.get("handling") or ""))
    if not pairs:
        return field_name, None
    if len(pairs) > 1:
        _fail(
            code,
            f"`handling` 里以「取值」引出的枚举对出现 {len(pairs)} 组 {pairs}，无法判定唯一形态",
        )
    first, second = pairs[0]
    if first.upper() != _ENTRY_TYPE_AJE or second.upper() != _ENTRY_TYPE_RJE:
        _fail(
            code,
            f"`handling` 登记的枚举对 {pairs[0]!r} 与规范值 "
            f"({_ENTRY_TYPE_AJE} / {_ENTRY_TYPE_RJE}) 不对应（大小写以外的差异）",
        )
    return field_name, MappingProxyType({_ENTRY_TYPE_AJE: first, _ENTRY_TYPE_RJE: second})


def _standalone_item_ids(entry: Mapping[str, Any], code: str, roundtrip_id: str) -> tuple[str, ...]:
    """表级独立键（调整说明 / 审计说明 / 审计结论）—— 往返一律不碰。

    两处来源取并集：`observed.other_data_keys`，以及 `key_families` 里**非**三个往返族的
    条目（`M8-3` 的「调整说明」既登记在 `other_data_keys` 也自成一族）。
    """
    ids: set[str] = set()
    observed = entry.get("observed")
    if observed is not None:
        if not isinstance(observed, Mapping):
            _fail(code, f"`observed` 应为对象，实测 {type(observed).__name__}")
        others = observed.get("other_data_keys", [])  # type: ignore[union-attr]
        if not isinstance(others, list):
            _fail(code, f"`observed.other_data_keys` 应为数组，实测 {type(others).__name__}")
        for item in others:  # type: ignore[union-attr]
            if not isinstance(item, str) or not item.strip():
                _fail(code, f"`observed.other_data_keys` 含非法项: {item!r}")
            ids.add(item)

    families = _req_mapping(entry, "key_families", code)
    roundtrip_names = {f.value for f in (KeyFamily.SINGLE_JSON, KeyFamily.PER_FIELD, KeyFamily.DATA)}
    for name, family in families.items():
        if name in roundtrip_names:
            continue
        if not isinstance(family, Mapping):
            _fail(f"{code}.key_families[{name}]", f"必须是对象，实测 {type(family).__name__}")
            continue  # pragma: no cover - _fail 必抛
        ids.add(_req_str(family, "item_id", f"{code}.key_families[{name}]"))

    if roundtrip_id in ids:
        _fail(
            code,
            f"表级独立键与往返键撞名 {roundtrip_id!r} —— 往返会把表级说明当行数据写掉",
        )
    return tuple(sorted(ids))


def _family(families: Mapping[str, Any], which: KeyFamily, code: str) -> Mapping[str, Any]:
    """取某个键族并校验其 `storage_field` 落在合法列面内。

    🔴 刻意**不**断言「族内 `storage_field` == sheet 级 `storage_field`」：GS1 的装载行为
    探针（`test_specs_really_loaded_from_ledger`）把 sheet 级 `mechanism` 与 `storage_field`
    **成对**翻到另一取值、族内值保持原样，并声明「成对翻 ⇒ 替身自洽，不会被实现的结构校验
    拒收」。若在此加上跨层等值断言，本模块会拒收那份替身清单，把一条本该考察「值是否真来自
    清单」的探针变成 ERROR。改为两条等价强度的判据：
      ① 同一 sheet 的各族之间 `storage_field` 必须一致（`_assert_families_agree`）——
         真正的风险是「同一张的两族写进不同列」，那会让读回只看到一半数据；
      ② sheet 级 `storage_field` 由 `mechanism` 推导并锁死（`_build_spec` 内）。
    落库列取的是 sheet 级值（任务 4.1「列一律取 `spec.storage_field`」），族内值属清单的
    重复登记，其与 sheet 级的一致性由前端侧守卫 GS9（机制探针）覆盖。
    """
    where = f"{code}.key_families[{which.value}]"
    family = families.get(which.value)
    if not isinstance(family, Mapping) or not family:
        _fail(
            where,
            f"`key_family` 声明需要该族，但清单未登记（实测 {type(family).__name__}）；"
            f"已登记的族为 {sorted(families)}",
        )
    declared = _req_str(family, "storage_field", where)  # type: ignore[arg-type]
    if declared not in set(_MECHANISM_STORAGE_FIELD.values()):
        _fail(
            where,
            f"族内 `storage_field`={declared!r} 不在合法列面 "
            f"{sorted(set(_MECHANISM_STORAGE_FIELD.values()))} 内",
        )
    return family  # type: ignore[return-value]


def _assert_families_agree(families: Mapping[str, Any], required: tuple[KeyFamily, ...], code: str) -> None:
    """同一 sheet 的各往返族必须落同一列（两族分写两列 ⇒ 读回只看到一半）。"""
    declared = {
        which.value: families[which.value].get("storage_field")
        for which in required
        if isinstance(families.get(which.value), Mapping)
    }
    if len(set(declared.values())) > 1:
        _fail(code, f"同一 sheet 的各键族 `storage_field` 不一致: {declared}")


def _sample_row(entry: Mapping[str, Any], code: str, width: int) -> tuple[str, ...] | None:
    raw = entry.get("sample_row")
    if raw is None:
        return None
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        _fail(code, f"`sample_row` 应为数组或 null，实测 {type(raw).__name__}")
    if len(raw) != width:  # type: ignore[arg-type]
        _fail(code, f"`sample_row` 长度 {len(raw)} != 列数 {width}")  # type: ignore[arg-type]
    bad = [v for v in raw if not isinstance(v, str)]  # type: ignore[union-attr]
    if bad:
        _fail(code, f"`sample_row` 含非字符串项: {bad}")
    return tuple(raw)  # type: ignore[arg-type]


def _catalog_sheet_name(code: str, cycle: str) -> str:
    """导出 sheet 名的运行期真源 = ACNR catalog `sheet_name`（R3.8）。

    清单 `provenance.column_source.tab` 只作列面取值溯源，**不在此当第二份真源**
    （清单自己的 note 已如此声明；实测两者逐字一致）。
    """
    from app.services.acnr.catalog import get_catalog

    try:
        entries = get_catalog().sheets_by_code.get(code, [])
    except Exception as exc:
        logger.error("ACNR catalog 不可用，无法解析 %s 的 sheet_name: %s", code, exc)
        raise X3ContractError(f"ACNR catalog 不可用，无法解析 {code} 的 sheet_name") from exc
    if len(entries) != 1:
        _fail(code, f"catalog 中该 sheet_code 有 {len(entries)} 条条目，sheet_name 不唯一")
    entry = entries[0]
    name = entry.get("sheet_name")
    if not isinstance(name, str) or not name.strip():
        _fail(code, f"catalog `sheet_name` 缺失或为空: {name!r}")
    parent = entry.get("parent_wp_code")
    if parent != cycle:
        _fail(
            code,
            f"catalog `parent_wp_code`={parent!r} 与清单 `cycle`={cycle!r} 不一致 ⇒ "
            "短前缀派生失去交叉锁；两处必须同步修",
        )
    return name  # type: ignore[return-value]


def _build_spec(code: str, entry: Mapping[str, Any]) -> X3SheetSpec:
    cycle = _req_str(entry, "cycle", code)
    mechanism: Mechanism = _as_enum(
        entry.get("mechanism"), Mechanism, frozenset(Mechanism), "mechanism", code
    )
    storage_field = _req_str(entry, "storage_field", code)
    expected_field = _MECHANISM_STORAGE_FIELD[mechanism]
    if storage_field != expected_field:
        _fail(
            code,
            f"机制 {mechanism.value!r} 应落列 {expected_field!r}，清单登记 {storage_field!r} "
            "—— 写错列 = 界面读不到（最隐蔽的 Orphan_Key）",
        )

    key_family: KeyFamily = _as_enum(
        entry.get("key_family"), KeyFamily, _WRITE_FAMILIES, "key_family", code
    )
    read_family: KeyFamily = _as_enum(
        entry.get("read_family"), KeyFamily, _READ_FAMILIES, "read_family", code
    )

    labels = _column_labels(entry, code)
    field_keys = tuple(_req_list(entry, "field_keys", code))
    if len(field_keys) != len(labels):
        _fail(code, f"`field_keys` {len(field_keys)} 项 != `column_map` {len(labels)} 列")

    families = _req_mapping(entry, "key_families", code)
    required_families = _REQUIRED_FAMILIES[key_family]
    for required in required_families:
        _family(families, required, code)
    _assert_families_agree(families, required_families, code)
    if read_family is not KeyFamily.NONE and read_family.value not in families:
        _fail(
            code,
            f"`read_family`={read_family.value!r} 指向未登记的族（已登记 {sorted(families)}）",
        )

    item_id = _req_str(entry, "item_id", code)
    per_field_prefix: str | None = None
    per_field_suffixes: tuple[str, ...] = ()
    suffix_to_field: Mapping[str, str] = MappingProxyType({})
    if KeyFamily.PER_FIELD in _REQUIRED_FAMILIES[key_family]:
        where = f"{code}.key_families[{KeyFamily.PER_FIELD.value}]"
        family = _family(families, KeyFamily.PER_FIELD, code)
        per_field_prefix = _req_str(family, "prefix", where)
        per_field_suffixes = _req_str_list(family, "suffixes", where)
        mapping = _req_mapping(family, "suffix_to_field", where)
        missing = [s for s in per_field_suffixes if s not in mapping]
        extra = [s for s in mapping if s not in per_field_suffixes]
        if missing or extra:
            _fail(where, f"`suffix_to_field` 与 `suffixes` 不等势：缺 {missing} / 多 {extra}")
        bad = {k: v for k, v in mapping.items() if not isinstance(v, str) or not v.strip()}
        if bad:
            _fail(where, f"`suffix_to_field` 含非法值: {bad}")
        suffix_to_field = MappingProxyType(dict(mapping))

    data_prefix: str | None = None
    data_suffix: str | None = None
    if KeyFamily.DATA in _REQUIRED_FAMILIES[key_family]:
        where = f"{code}.key_families[{KeyFamily.DATA.value}]"
        family = _family(families, KeyFamily.DATA, code)
        data_prefix = _req_str(family, "prefix", where)
        data_suffix = _req_str(family, "suffix", where)

    if key_family is KeyFamily.SINGLE_JSON:
        where = f"{code}.key_families[{KeyFamily.SINGLE_JSON.value}]"
        family = _family(families, KeyFamily.SINGLE_JSON, code)
        declared_id = _req_str(family, "item_id", where)
        if declared_id != item_id:
            _fail(where, f"族内 `item_id`={declared_id!r} 与 sheet 级 {item_id!r} 不一致")

    entry_type_field, entry_type_values = _entry_type_declaration(entry, code)
    if entry_type_field not in _req_str_list(entry, "frontend_extra_fields", code):
        _fail(
            code,
            f"AJE/RJE 标记字段 {entry_type_field!r} 不在 `frontend_extra_fields` 里 ⇒ "
            "两处登记互相矛盾",
        )

    return X3SheetSpec(
        sheet_code=code,
        cycle=cycle,
        api_prefix=cycle.lower(),
        sheet_name=_catalog_sheet_name(code, cycle),
        item_id=item_id,
        key_family=key_family,
        read_family=read_family,
        mechanism=mechanism,
        storage_field=storage_field,
        field_keys=field_keys,
        per_field_prefix=per_field_prefix,
        per_field_suffixes=per_field_suffixes,
        per_field_suffix_to_field=suffix_to_field,
        data_key_prefix=data_prefix,
        data_key_suffix=data_suffix,
        read_host=_opt_str(entry, "read_host", code),
        read_source=_opt_str(entry, "read_source", code),
        extra_fields=_req_str_list(entry, "frontend_extra_fields", code),
        sample_row=_sample_row(entry, code, len(labels)),
        entry_type_field=entry_type_field,
        entry_type_values=entry_type_values,
        standalone_item_ids=_standalone_item_ids(entry, code, item_id),
        provenance=MappingProxyType(dict(_req_mapping(entry, "provenance", code))),
    )


def _load() -> tuple[dict[str, X3SheetSpec], tuple[str, ...]]:
    """装载全部 X-3 规格 + 派生 `COLUMN_ORDER`。模块导入时执行一次。"""
    doc = _read_ledger()
    selected = _select_x3_entries(doc)

    specs: dict[str, X3SheetSpec] = {}
    columns: dict[tuple[str, ...], list[str]] = {}
    for code in sorted(selected):
        entry = selected[code]
        specs[code] = _build_spec(code, entry)
        columns.setdefault(_column_labels(entry, code), []).append(code)

    if len(columns) != 1:
        _fail(
            "column_map",
            "16 张的 `column_map[].col` 不再逐字一致，无法派生单一 COLUMN_ORDER：\n"
            + "\n".join(f"  {sorted(v)} -> {list(k)}" for k, v in columns.items()),
        )

    prefixes = {s.api_prefix for s in specs.values()}
    if len(prefixes) != len(specs):
        _fail("api_prefix", f"短前缀不唯一（{len(prefixes)} 个前缀 / {len(specs)} 张 sheet）")

    logger.info(
        "X-3 共享实现装载完成: %d 张 sheet / %d 列 (真源 %s)",
        len(specs),
        len(next(iter(columns))),
        LEDGER_PATH.name,
    )
    return specs, next(iter(columns))


def _category_column_index(labels: tuple[str, ...]) -> int:
    """定位「类别」列在 `COLUMN_ORDER` 中的下标 —— **不写列标签字面量**。

    判据：该列的标签必须同时包含 `CATEGORY_TO_ENTRY_TYPE` 的**全部**键（源模板第 5 行的
    第二个标签把三个枚举值直接写在括号里）。实测在 10 个标签里恰命中 1 处。

    为什么必须靠它而不是「`column_map[].field == category`」：`N5-3` 的行模型没有
    `category` 字段（该列在其 `field_keys` 里是占位 `None`），但导入时**仍要**从该列取值
    派生 AJE/RJE ⇒ 只能按列定位，不能按前端字段名定位。

    命中数 != 1 即抛：枚举表或源模板列面任一侧被改动时，在模块 import 当刻打红，
    而不是把「派生不出类别列」静默兜成「所有行都落兜底值」。
    """
    hits = [i for i, label in enumerate(labels) if all(k in label for k in CATEGORY_TO_ENTRY_TYPE)]
    if len(hits) != 1:
        _fail(
            "column_map",
            f"按「标签含全部类别枚举 {sorted(CATEGORY_TO_ENTRY_TYPE)}」定位类别列，"
            f"命中 {len(hits)} 处（下标 {hits}）；列面实测 {list(labels)}",
        )
    return hits[0]


X3_SHEET_SPECS, COLUMN_ORDER = _load()

#: 「类别」列在 `COLUMN_ORDER` / `field_keys` 中的下标（导入时 AJE/RJE 的取值列）
CATEGORY_COLUMN_INDEX = _category_column_index(COLUMN_ORDER)


# ═══════════════════════════════════════════════════════════════════════════
# 公共访问器与三族 item_id 生成器
# ═══════════════════════════════════════════════════════════════════════════


def sheet_spec(sheet: str) -> X3SheetSpec:
    """按 sheet 码取规格；未知 sheet 抛错（不返回 None —— 静默 None 会一路兜到写空库）。"""
    spec = X3_SHEET_SPECS.get(sheet)
    if spec is None:
        raise X3ContractError(
            f"{sheet!r} 不在 X-3 作业面内（已登记 {sorted(X3_SHEET_SPECS)}）"
        )
    return spec


def _require_row_no(row_no: Any, spec: X3SheetSpec) -> int:
    """行号必须是 >= 1 的整数（前端逐字段族与整行 JSON 族都是 1-based）。"""
    if isinstance(row_no, bool) or not isinstance(row_no, int):
        raise X3ContractError(
            f"{spec.sheet_code} 行号必须是整数，实测 {type(row_no).__name__}: {row_no!r}"
        )
    if row_no < 1:
        raise X3ContractError(f"{spec.sheet_code} 行号必须 >= 1（1-based），实测 {row_no}")
    return row_no


def single_json_item_id(spec: X3SheetSpec) -> str:
    """整表单键 JSON 族的 item_id（整表一个键，不带行号）。

    形态例：`L2-L2-3-entries`（双前缀）· `N5-3-entries`（单前缀）——两者都直接取清单
    `item_id`，本函数不做任何拼接，故双/单前缀分叉在此天然无害。
    """
    if spec.key_family is not KeyFamily.SINGLE_JSON:
        raise X3ContractError(
            f"{spec.sheet_code} 的写入族是 {spec.key_family.value!r}，不是整表单键 JSON 族"
        )
    return spec.item_id


def per_field_item_id(spec: X3SheetSpec, row_no: int, suffix: str) -> str:
    """逐字段族的 item_id：`{前缀}{行号}-{后缀}`。

    形态例：`M4-3-entry-1-desc`（单前缀）· `L6-L6-3-entry-1-type`（双前缀）。
    前缀逐 sheet 取清单登记值 ⇒ 单/双前缀分叉不靠公式；后缀必须在该 sheet 的登记后缀集内
    （`M9-3` 多一个 `ociBlock`，写死一份全局后缀表必丢字段）。
    """
    if spec.per_field_prefix is None:
        raise X3ContractError(
            f"{spec.sheet_code} 的写入族是 {spec.key_family.value!r}，无逐字段族"
        )
    _require_row_no(row_no, spec)
    if suffix not in spec.per_field_suffixes:
        raise X3ContractError(
            f"{spec.sheet_code} 无后缀 {suffix!r}（已登记 {list(spec.per_field_suffixes)}）"
        )
    return f"{spec.per_field_prefix}{row_no}-{suffix}"


def data_item_id(spec: X3SheetSpec, row_no: int) -> str:
    """整行 JSON 族的 item_id：`{前缀}{行号}{后缀}`（后缀登记值已含前导分隔符）。

    形态例：`M4-3-entry-1-data`。只有 `per_field_plus_data` 的 8 张有该族。
    """
    if spec.data_key_prefix is None or spec.data_key_suffix is None:
        raise X3ContractError(
            f"{spec.sheet_code} 的写入族是 {spec.key_family.value!r}，无整行 JSON 族"
        )
    _require_row_no(row_no, spec)
    return f"{spec.data_key_prefix}{row_no}{spec.data_key_suffix}"


# ═══════════════════════════════════════════════════════════════════════════
# 后半（任务 4.1 剩余部分）—— workbook 构建/解析 · 取数/落库 · 形态 A 三态端点
#
# 🔴 三条纪律贯穿本段：
#   ① xlsx 构建与解析**一律**经 `_cycle_import_export_common`（R1.5，不造第三套）；
#   ② 列面/键面/大小写**一律**从 `X3_SHEET_SPECS` 取，代码里不出现任何 X-3 字面量；
#   ③ 异常不吞：`except Exception: logger.warning` 是明令禁止形态；任何异常记 ERROR
#      并向上抛或转成用户可读的 4xx（R10.11）。
# ═══════════════════════════════════════════════════════════════════════════


#: 导出工作簿的列头行号。`build_workbook_template` 不传 `title` / `subtitle` 时列头落第 1 行，
#: 故导入解析的 `header_row` 与之配对为 1。
#: （源模板的第 5 行只是**列标签的真源**，不是导出布局；两者不可混为一谈。）
_EXPORT_HEADER_ROW = 1

#: 占位列（`field_keys` 的 `None` 位）在解析期的临时键前缀。
#: 导出：`export_row_by_keys` 取不到该键 ⇒ 写空字符串，列序得以保持（R3.4）。
#: 导入：解析后由 `_strip_placeholders` 整批剔除 ⇒ 该列被忽略。
#: 🔴 占位位一律按 `spec.field_keys` 的 `None` 位判定，**不假定只有 F 列**
#: （实测 14 张 1 个 / `L2-3` 2 个 / `N5-3` 6 个）。
_PLACEHOLDER_KEY_PREFIX = "__x3_placeholder_col_"

#: `parse_row_by_headers` 为每行注入的行标识键（来自被复用的公共实现，不是本模块造的）
_PARSED_ROW_ID_KEY = "id"

#: LIKE 模式里需要转义的三个字符（前缀含 `_` 会被当单字符通配 ⇒ 多捞别的键）
_LIKE_SPECIAL_RE = re.compile(r"([\\%_])")

#: 冲突策略取值面（与 `app.services.bulk_tab.single_tab_adapter.ConflictStrategy` 同一套词表）
_STRATEGY_OVERWRITE = "overwrite"

_SUFFIX_TEMPLATE = "export-template"
_SUFFIX_DATA = "export-data"
_SUFFIX_IMPORT = "import-data"

#: 形态 A 三态**必须**声明的 HTTP 方法（R4.1 / design §C1）。
#: 🔴 为什么方法要单独立常量并进注册自检：前端共享 composable `useWorkpaperImportExport`
#: 只发 POST，而 bulk 侧 `_endpoint_for` 是按 `path.endswith(后缀)` 找端点、**不看方法**。
#: 于是把某一态误写成 `@router.get` 时 —— batch 通路照样跑通、UI 通路 405 ——
#: 又是一条「一半通路静默失效」（与 `_register_shape_a` 里防的前缀污染同一族缺陷）。
#: 故 `attach_shape_a_routes` 的注册自检按「路径 + 方法」**双向**比对，只比路径抓不住这类漂移。
_SHAPE_A_METHOD = "POST"

#: 比对方法集前先剔掉的**自动派生**方法：Starlette 的 `Route` 对含 `GET` 的路由自动补
#: `HEAD`、`OPTIONS` 由 CORS 中间件应答 —— 两者都不是「声明的方法」。
#: 实测 fastapi 0.135.3 / starlette 0.52.1 的 `APIRoute` 两个都不补（`@router.get` 得到
#: 恰 `{"GET"}`），但换版本或改用 `add_route`/`Mount` 就会补 ⇒ 判据先归一，
#: 免得日后升级把「真判据」变成「假红」。剔完为空的处理见 `_declared_methods`。
_AUTO_DERIVED_METHODS = frozenset({"HEAD", "OPTIONS"})


class ParseOutcome(NamedTuple):
    """`parse_workbook` 的返回值。

    前两项即 design §C1 / 任务正文写的 `(rows, errors)`；另加两项是施工期实测必须的出口：

    * `warnings` —— 「`category` 非枚举值」「跳过示例行」「`type` 大小写未登记」这类
      **可继续**的告警。压进 `errors` 会让它们变成「零写入」（errors 非空 ⇒ 整表拒收），
      把可用的导入直接判死；靠日志承载则用户看不到 ⇒ 违反「不得静默」。
    * `truncated` —— 行数超 `ROW_LIMIT` 的截断标记，决定响应是 `success` 还是 `partial`。
    """

    rows: list[dict[str, Any]]
    errors: list[str]
    warnings: list[str]
    truncated: bool


class ImportOutcome(NamedTuple):
    """`write_rows` 的返回值（design §C1 的 `ImportOutcome`）。"""

    written_count: int
    written_item_ids: tuple[str, ...]
    removed_item_ids: tuple[str, ...]
    warnings: list[str]


# ── 列面 / 占位列 ────────────────────────────────────────────────────────────


def _placeholder_key(index: int) -> str:
    return f"{_PLACEHOLDER_KEY_PREFIX}{index}"


def _row_field_keys(spec: X3SheetSpec) -> list[str]:
    """与 `COLUMN_ORDER` 同序、同长的取值键；占位位换成临时占位键。

    `parse_row_by_headers` 会 `zip(expected_headers, field_keys)` 并把结果写成
    `out[key]`，`None` 作字典键会污染行模型 ⇒ 占位位必须给一个可识别、之后能整批剔除的键。
    """
    return [
        key if key is not None else _placeholder_key(idx)
        for idx, key in enumerate(spec.field_keys)
    ]


def _strip_placeholders(row: Mapping[str, Any]) -> dict[str, Any]:
    """剔除占位列的临时键（= 导入忽略占位列）。"""
    return {k: v for k, v in row.items() if not k.startswith(_PLACEHOLDER_KEY_PREFIX)}


def _guidance_lines(spec: X3SheetSpec) -> list[str]:
    """「编制说明」sheet 的正文。

    唯一实质内容 = B 列类别枚举与 AJE/RJE 的对应关系（design §D2 的已知限制缓解措施：
    `category` 落枚举外时导入会按兜底值落 `entryType`，故必须在模板里把枚举写清）。
    文案由 `CATEGORY_TO_ENTRY_TYPE` 与 `COLUMN_ORDER` 拼出，**不写死任何列名/枚举值**。
    """
    category_label = COLUMN_ORDER[CATEGORY_COLUMN_INDEX]
    lines = [
        f"{spec.sheet_code}（{spec.sheet_name}）导入导出说明",
        "",
        f"1. 列头共 {len(COLUMN_ORDER)} 列，取自源模板，请勿增删或改名：",
        "   " + " | ".join(COLUMN_ORDER),
        "",
        f"2.「{category_label}」列只接受以下取值，导入时据此判定分录属 AJE 还是 RJE：",
    ]
    for category, entry_type in CATEGORY_TO_ENTRY_TYPE.items():
        lines.append(f"   {category} -> {entry_type}")
    lines.append(
        f"   留空或填枚举外的值 -> 一律按 {ENTRY_TYPE_FALLBACK} 处理，"
        f"并在导入结果的 warnings 里逐行回报（不会静默改写）"
    )
    placeholders = [
        COLUMN_ORDER[idx] for idx, key in enumerate(spec.field_keys) if key is None
    ]
    if placeholders:
        lines += [
            "",
            f"3. 以下 {len(placeholders)} 列在本表无对应录入字段，导出留空、导入忽略"
            f"（保留列序以便与源模板对齐）：",
            "   " + " | ".join(placeholders),
        ]
    return lines


# ── AJE / RJE 派生（design §D2）──────────────────────────────────────────────


def derive_entry_type(category: Any) -> tuple[str, bool]:
    """由「类别」列取值派生规范 entryType。

    返回 `(规范值, 是否命中枚举)`。空值/枚举外取值 ⇒ `(ENTRY_TYPE_FALLBACK, False)`，
    由调用方在 `warnings` 里记行号 —— design §D2 的已知限制（被归为兜底类的 RJE 往返后
    会变成 AJE）必须可见，**不得静默**。
    """
    text = safe_str(category)
    canonical = CATEGORY_TO_ENTRY_TYPE.get(text)
    if canonical is None:
        return ENTRY_TYPE_FALLBACK, False
    return canonical, True


def _entry_type_literal(spec: X3SheetSpec, canonical: str) -> str | None:
    """把规范值翻成**本 sheet 的字面形态**；清单未登记大小写时返回 None。

    🔴 `None` 的处置是「不写该键」而**不是**默认成规范大写：`N5-3` 的实测形态是小写
    `aje` / `rje`，界面按该小写值分 AJE / RJE 两张 el-table —— 猜错大小写会让导入行
    从两张表里同时消失（filter 全不命中 = 静默丢行）。实测 12 张清单未登记枚举形态
    （见模块 docstring「后半的一条已知缺口」）。
    """
    if spec.entry_type_values is None:
        return None
    literal = spec.entry_type_values.get(canonical)
    if not isinstance(literal, str) or not literal:
        _fail(
            spec.sheet_code,
            f"清单登记的 entryType 形态缺规范值 {canonical!r}（实测 {literal!r}）",
        )
    return literal


# ── workbook 构建（复用 `_cycle_import_export_common`，不造第三套）───────────


def build_template_workbook(sheet: str) -> Workbook:
    """空白模板：列头 = `COLUMN_ORDER`，sheet 名 = catalog `sheet_name`（R3.1 / R3.8）。

    🔴 **不预填**源模板第 6 行的示例行（design E13：只有 `L2-3` 有示例行，预填会让
    「示例」被当成用户数据导回库）。示例行只在导入侧用于「逐字段全等即跳过」。
    """
    spec = sheet_spec(sheet)
    return build_workbook_template(
        spec.sheet_name,
        list(COLUMN_ORDER),
        guidance=_guidance_lines(spec),
    )


def build_data_workbook(
    rows: Sequence[Mapping[str, Any]],
    sheet: str,
    *,
    warnings: Sequence[str] | None = None,
) -> Workbook:
    """含数据的工作簿。行值按 `field_keys` 取，占位列写空保列序（R3.4）。

    `warnings`（如 `load_rows` 报的「界面读回路径尚未补齐」）写进「编制说明」sheet ——
    导出走 StreamingResponse，响应体里塞不下告警，落进用户拿到手的文件才叫「不静默」。
    """
    spec = sheet_spec(sheet)
    keys = _row_field_keys(spec)
    guidance = list(_guidance_lines(spec))
    if warnings:
        guidance += ["", "本次导出的提示："] + [f"   - {w}" for w in warnings]
    wb = build_workbook_template(spec.sheet_name, list(COLUMN_ORDER), guidance=guidance)
    ws = wb[spec.sheet_name]
    for row in rows:
        ws.append(export_row_by_keys(dict(row), keys))
    return wb


# ── workbook 解析 ──────────────────────────────────────────────────────────


def _foreign_sheet_error(content: bytes, spec: X3SheetSpec) -> str | None:
    """上传文件的活动工作表被**正面识别为另一张 X-3** 时给出可读错误，否则返回 None。

    只做身份识别、不解析数据行（数据行解析的唯一入口仍是 `parse_upload_xlsx`，R1.5）。
    判据刻意取窄：仅当活动表名逐字等于**别的**已登记 X-3 的 `sheet_name` 才拒收 ——
    手工新建的表（`Sheet1` 之类）不会被误拒，而「把 A 表的导出文件传进 B 表」这类
    会静默覆盖 B 表数据的操作必被挡住。
    """
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        logger.error("X-3 %s 上传文件无法打开: %s", spec.sheet_code, exc)
        raise
    try:
        title = safe_str(getattr(wb.active, "title", ""))
    finally:
        wb.close()
    if title == spec.sheet_name:
        return None
    foreign = [
        other.sheet_code
        for other in X3_SHEET_SPECS.values()
        if other.sheet_code != spec.sheet_code and other.sheet_name == title
    ]
    if not foreign:
        return None
    return (
        f"上传文件的工作表是 {title!r}（属 {'/'.join(sorted(foreign))}），"
        f"与本次请求的 {spec.sheet_code}（{spec.sheet_name}）不一致，已拒绝导入。"
        f"请在对应底稿页重新导出模板后填写"
    )


def _matches_sample_row(spec: X3SheetSpec, parsed: Mapping[str, Any], keys: Sequence[str]) -> bool:
    """是否与源模板示例行**逐字段全等**（design E13 / 任务 4.1「不用过半相似」）。

    「过半相似」会吞真实数据：示例行里 5 个字段是同一个地名、两列金额同值，
    用户真填的行很容易过半命中。故这里要求 10 列**全部**相等才跳过。
    金额列按数值比、其余按字符串比（示例行在清单里一律登记为字符串）。
    """
    if spec.sample_row is None:
        return False
    for key, expected in zip(keys, spec.sample_row):
        actual = parsed.get(key)
        if is_numeric_field_key(key):
            if safe_float(actual) != safe_float(expected):
                return False
        elif safe_str(actual) != safe_str(expected):
            return False
    return True


def parse_workbook(content: bytes, sheet: str) -> ParseOutcome:
    """解析回传 xlsx（纯函数，不碰库）。

    解析器复用 `parse_upload_xlsx`（列头校验 + 全空行跳过）与
    `parse_row_by_headers(expected_headers=…)`（**按列名**取值 ⇒ 列序无关）+
    `import_rows_generic`（`ROW_LIMIT` 截断），本模块只做三件 X-3 专属的事：
    占位列剔除 · 示例行跳过 · entryType 派生。
    """
    spec = sheet_spec(sheet)
    headers = list(COLUMN_ORDER)
    keys = _row_field_keys(spec)

    foreign = _foreign_sheet_error(content, spec)
    if foreign:
        return ParseOutcome([], [foreign], [], False)

    try:
        actual, raw_rows = parse_upload_xlsx(content, headers, header_row=_EXPORT_HEADER_ROW)
    except ValueError as exc:
        # 列头缺失 / 无活动工作表 —— 用户可修的输入问题，作 errors 回报（零写入）
        return ParseOutcome([], [str(exc)], [], False)

    parsed_rows, truncated = import_rows_generic(
        raw_rows,
        actual,
        keys,
        parse_fn=lambda r, h: parse_row_by_headers(r, h, keys, expected_headers=headers),
    )

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    unmatched_rows: list[int] = []
    skipped_sample = 0
    for ordinal, parsed in enumerate(parsed_rows, start=1):
        if _matches_sample_row(spec, parsed, keys):
            skipped_sample += 1
            continue
        canonical, matched = derive_entry_type(parsed.get(keys[CATEGORY_COLUMN_INDEX]))
        if not matched:
            unmatched_rows.append(ordinal)
        row = _strip_placeholders(parsed)
        literal = _entry_type_literal(spec, canonical)
        if literal is not None:
            row[spec.entry_type_field] = literal
        rows.append(row)

    if skipped_sample:
        warnings.append(
            f"已跳过 {skipped_sample} 行与源模板示例行逐字段全等的内容"
            f"（判据是 {len(COLUMN_ORDER)} 列全等，不做相似度匹配）"
        )
    if unmatched_rows:
        warnings.append(
            f"第 {unmatched_rows} 行数据（跳过全空行后的序号）的"
            f"「{COLUMN_ORDER[CATEGORY_COLUMN_INDEX]}」不在枚举 "
            f"{sorted(CATEGORY_TO_ENTRY_TYPE)} 内，已按 {ENTRY_TYPE_FALLBACK} 落值"
        )
    if rows and spec.entry_type_values is None:
        warnings.append(
            f"{spec.sheet_code} 的 AJE/RJE 枚举大小写尚未在 {LEDGER_PATH.name} 登记，"
            f"本次导入**不写** {spec.entry_type_field!r} 键（拒绝猜大小写：已实测存在小写形态的 sheet，"
            f"猜错会让导入行从 AJE / RJE 两张表里同时消失）。"
            f"后果：界面读回时该字段走各自的兜底值 ⇒ 被归为 RJE 的行会显示成 "
            f"{ENTRY_TYPE_FALLBACK}。收口 = 先补清单登记（任务 2.4）"
        )
    if truncated:
        warnings.append(f"数据行数超过{ROW_LIMIT}行限制，已截断")
    return ParseOutcome(rows, [], warnings, truncated)


# ── checklist_responses 读写（批量语句；SQL 形态与 `upsert_json_payload` 一致）──


def _storage_column(spec: X3SheetSpec) -> str:
    """落库列名。取值面已被结构校验锁死在两列内，此处再断言一次再拼进 SQL。"""
    allowed = set(_MECHANISM_STORAGE_FIELD.values())
    if spec.storage_field not in allowed:
        _fail(spec.sheet_code, f"落库列 {spec.storage_field!r} 不在 {sorted(allowed)} 内")
    return spec.storage_field


def _like_prefix(prefix: str) -> str:
    return _LIKE_SPECIAL_RE.sub(r"\\\1", prefix) + "%"


async def _fetch_by_prefix(
    db: AsyncSession, wp_id: str, prefix: str, column: str
) -> dict[str, Any]:
    """一条语句取回该族全部键值。

    逐键点查会让一次导入产生上千次往返（`ROW_LIMIT` 500 × 最多 11 个后缀），
    故按前缀一次捞回。`_` 是 LIKE 的单字符通配 ⇒ 必须转义，否则会多捞别的键。
    """
    result = await db.execute(
        sa.text(
            f"SELECT item_id, {column} AS value FROM checklist_responses "  # noqa: S608 - 列名已白名单校验
            "WHERE wp_id = :wp_id AND item_id LIKE :pattern ESCAPE '\\'"
        ),
        {"wp_id": wp_id, "pattern": _like_prefix(prefix)},
    )
    return {row.item_id: row.value for row in result.fetchall()}


async def _fetch_one(db: AsyncSession, wp_id: str, item_id: str, column: str) -> dict[str, Any]:
    result = await db.execute(
        sa.text(
            f"SELECT item_id, {column} AS value FROM checklist_responses "  # noqa: S608 - 列名已白名单校验
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    return {row.item_id: row.value for row in result.fetchall()}


async def _require_project_id(db: AsyncSession, wp_id: str) -> str:
    """底稿必须存在 —— 与 `upsert_json_payload` 同一判据同一异常（`ValueError` ⇒ 端点 400）。"""
    result = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id AND is_deleted = false"),
        {"wp_id": wp_id},
    )
    project_id = result.scalar_one_or_none()
    if not project_id:
        raise ValueError(f"working_paper not found: {wp_id}")
    return str(project_id)


def _row_index_from_key(item_id: str, prefix: str, suffix: str | None) -> int | None:
    """从族键里抠出行号；形态不符返回 None（不猜、不兜 0）。"""
    if not item_id.startswith(prefix):
        return None
    rest = item_id[len(prefix) :]
    if suffix is None:
        head, sep, _tail = rest.partition("-")
        if not sep or not head.isdigit():
            return None
        return int(head)
    if not rest.endswith(suffix):
        return None
    head = rest[: -len(suffix)]
    return int(head) if head.isdigit() else None


def _suffix_from_key(item_id: str, prefix: str) -> str | None:
    rest = item_id[len(prefix) :] if item_id.startswith(prefix) else ""
    _head, sep, tail = rest.partition("-")
    return tail if sep and tail else None


# ── 取数（load_rows）────────────────────────────────────────────────────────


def _effective_read_family(spec: X3SheetSpec) -> KeyFamily:
    """界面实际读的族；`NONE`（design E21 的四张）回落到写入族。"""
    if spec.read_family is not KeyFamily.NONE:
        return spec.read_family
    if spec.data_key_prefix is not None:
        return KeyFamily.DATA
    if spec.per_field_prefix is not None:
        return KeyFamily.PER_FIELD
    return KeyFamily.SINGLE_JSON


def _typed(field: str, raw: Any) -> Any:
    """逐字段族的值是纯文本，取数时按与导入侧**同一套** helper 归一类型。"""
    return safe_float(raw) if is_numeric_field_key(field) else safe_str(raw)


def _rows_from_data_family(
    spec: X3SheetSpec, stored: Mapping[str, Any], warnings: list[str]
) -> list[dict[str, Any]]:
    """整行 JSON 族 → 行列表。行序与界面读回一致：从 1 连续取到断档为止。"""
    assert spec.data_key_prefix is not None and spec.data_key_suffix is not None
    by_index: dict[int, Any] = {}
    for item_id, value in stored.items():
        idx = _row_index_from_key(item_id, spec.data_key_prefix, spec.data_key_suffix)
        if idx is not None:
            by_index[idx] = value
    rows: list[dict[str, Any]] = []
    row_no = 1
    while row_no in by_index:
        raw = by_index[row_no]
        if raw:
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError) as exc:
                # 具名异常、记 ERROR 并回报给用户 —— 不是 `except Exception` 兜空
                logger.error(
                    "X-3 %s 第 %d 行整行 JSON 解析失败: %s", spec.sheet_code, row_no, exc
                )
                warnings.append(f"第 {row_no} 行库中存的整行 JSON 无法解析，导出时已跳过该行")
                payload = None
            if isinstance(payload, Mapping):
                rows.append(dict(payload))
        row_no += 1
    return rows


def _rows_from_per_field_family(
    spec: X3SheetSpec, stored: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """逐字段族 → 行列表。

    行存在的判据 = 该行号下**任一**登记后缀有键（不锚定某个具体后缀 ⇒ 不写后缀字面量）；
    行序同样从 1 连续取到断档为止。
    """
    assert spec.per_field_prefix is not None
    by_index: dict[int, dict[str, Any]] = {}
    for item_id, value in stored.items():
        idx = _row_index_from_key(item_id, spec.per_field_prefix, None)
        if idx is None:
            continue
        suffix = _suffix_from_key(item_id, spec.per_field_prefix)
        if suffix is None or suffix not in spec.per_field_suffix_to_field:
            continue
        by_index.setdefault(idx, {})[suffix] = value
    rows: list[dict[str, Any]] = []
    row_no = 1
    while row_no in by_index:
        cells = by_index[row_no]
        rows.append(
            {
                field: _typed(field, cells.get(suffix))
                for suffix, field in spec.per_field_suffix_to_field.items()
            }
        )
        row_no += 1
    return rows


async def load_rows(db: AsyncSession, wp_id: str, sheet: str) -> tuple[list[dict[str, Any]], list[str]]:
    """按**界面读回族**取该 sheet 的分录行。

    返回 `(rows, warnings)`。design §C1 的签名只写了 `-> list[dict]`，但同一段正文要求
    「`read_family = NONE` 时读写入族并在 `warnings` 标注」——告警必须有出口，否则那句
    要求只能落进日志（用户看不见 = 静默）。故据实返回二元组。
    """
    spec = sheet_spec(sheet)
    column = _storage_column(spec)
    warnings: list[str] = []

    family = _effective_read_family(spec)
    if spec.read_family is KeyFamily.NONE:
        warnings.append(
            f"{spec.sheet_code} 的界面读回路径尚未补齐（design E21，收口在任务 4.2）："
            f"本次导出取自写入族 {family.value!r}。此前用户在界面填的行刷新即看不见，"
            f"故导出内容可能多于界面所显示的行"
        )

    if family is KeyFamily.SINGLE_JSON:
        rows = await load_json_rows(db, wp_id, spec.item_id, field=column)
        return [dict(r) for r in rows if isinstance(r, Mapping)], warnings

    if family is KeyFamily.DATA:
        assert spec.data_key_prefix is not None
        stored = await _fetch_by_prefix(db, wp_id, spec.data_key_prefix, column)
        return _rows_from_data_family(spec, stored, warnings), warnings

    if family is KeyFamily.PER_FIELD:
        assert spec.per_field_prefix is not None
        stored = await _fetch_by_prefix(db, wp_id, spec.per_field_prefix, column)
        return _rows_from_per_field_family(spec, stored), warnings

    _fail(spec.sheet_code, f"读取族 {family.value!r} 无取数实现")
    raise AssertionError("unreachable")  # pragma: no cover - _fail 必抛


# ── 落库（write_rows）──────────────────────────────────────────────────────


def _scalar_cell(value: Any) -> str | None:
    """逐字段族的落库值 —— 与前端 `saveBatch` 载荷形态逐字对齐。

    前端写的是 `{ remark: entry.x || null }` 与 `{ remark: String(entry.amount) }`：
    假值（`0` / `''` / `None`）落 `null`、数值落无小数点尾巴的字符串。照抄该形态才能让
    「前端写 → 后端读」与「后端写 → 前端读」两个方向的往返都逐字节一致。
    """
    if value is None or value == "" or value == 0:
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _data_payload(spec: X3SheetSpec, row: Mapping[str, Any]) -> dict[str, Any]:
    """整行 JSON 族的载荷 —— 键集取自清单 `suffix_to_field`，不写字段名字面量。

    该键集实测恰好等于前端读回时消费的键集（行序号字段除外，界面读回侧对它有
    `data.index || i` 的位置兜底）。`M9-3` 的 `ociBlock` 也在其中 ⇒ 随整行 JSON 一并保留。
    """
    return {field: row.get(field) for field in spec.per_field_suffix_to_field.values()}


def _incoming_payloads(
    spec: X3SheetSpec, rows: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """行列表 → `{item_id: {落库列: 值}}`（族键爆炸）。

    三族分派：
      * 整表单键 JSON —— 一个键存整个数组；
      * 逐字段族 —— 每行每个登记后缀一个键（`M9-3` 的 `ociBlock` 后缀键**必写**，
        缺键会让该 sheet 的逐字段族出现断档）；
      * 逐字段 + 整行 JSON —— **两族都写**：per-field 供进度统计与跨表取数、
        整行 JSON 供界面读回（R6.6）。只写一族 = 一半通路读不到。
    """
    column = _storage_column(spec)
    incoming: dict[str, dict[str, Any]] = {}

    if spec.key_family is KeyFamily.SINGLE_JSON:
        incoming[single_json_item_id(spec)] = {
            column: json.dumps([dict(r) for r in rows], ensure_ascii=False)
        }
        return incoming

    if spec.per_field_prefix is not None:
        for row_no, row in enumerate(rows, start=1):
            for suffix in spec.per_field_suffixes:
                field = spec.per_field_suffix_to_field[suffix]
                incoming[per_field_item_id(spec, row_no, suffix)] = {
                    column: _scalar_cell(row.get(field))
                }
    if spec.data_key_prefix is not None:
        for row_no, row in enumerate(rows, start=1):
            incoming[data_item_id(spec, row_no)] = {
                column: json.dumps(_data_payload(spec, row), ensure_ascii=False)
            }
    if not incoming and rows:
        _fail(spec.sheet_code, f"写入族 {spec.key_family.value!r} 未产出任何落库键")
    return incoming


def _should_purge_residual(spec: X3SheetSpec, strategy: str) -> bool:
    """是否清理行号超出的残留族键 —— **唯一判定处**（R11.7 的破坏性作用域）。

    只有 `overwrite` 才清：`fill-empty` 的语义是「只填空位」，`reject` 在有数据时压根到不了
    这一步。整表单键 JSON 族没有残留概念（一个键存整个数组，覆盖即完成）。

    抽成纯函数是为了让「越界删数据」这类变异可被守卫直接判定：把条件放在 `write_rows` 的
    行内 `if` 里时，任何守卫都只能靠连库往返才发现 `fill-empty` 也删了数据
    （本轮变异 M8 实测：改成不分策略一律清，判据面 167 passed 全绿 = 守卫缺陷）。
    """
    return strategy == _STRATEGY_OVERWRITE and spec.key_family is not KeyFamily.SINGLE_JSON


def _residual_item_ids(
    spec: X3SheetSpec, stored: Iterable[str], kept_rows: int
) -> list[str]:
    """行号 > 本次导入行数的残留族键（Property 2 的「无幽灵残留」）。

    作用域由 `(wp_id, 族前缀, 行号 > N)` 三重限定；`standalone_item_ids`（调整说明 /
    审计说明 / 审计结论）显式排除 —— 它们与往返无关，误删等于删用户写的结论。
    """
    standalone = set(spec.standalone_item_ids)
    residual: list[str] = []
    for item_id in stored:
        if item_id in standalone:
            continue
        idx = None
        if spec.data_key_prefix is not None and spec.data_key_suffix is not None:
            idx = _row_index_from_key(item_id, spec.data_key_prefix, spec.data_key_suffix)
        if idx is None and spec.per_field_prefix is not None:
            candidate = _row_index_from_key(item_id, spec.per_field_prefix, None)
            suffix = _suffix_from_key(item_id, spec.per_field_prefix)
            if candidate is not None and suffix in spec.per_field_suffix_to_field:
                idx = candidate
        if idx is not None and idx > kept_rows:
            residual.append(item_id)
    return sorted(residual)


async def _upsert_many(
    db: AsyncSession,
    wp_id: str,
    project_id: str,
    column: str,
    resolved: Mapping[str, Mapping[str, Any]],
) -> None:
    """批量 upsert。SQL 形态与 `upsert_json_payload` 逐字一致，只把逐条改成一次多参。"""
    params = [
        {
            "id": str(uuid4()),
            "project_id": project_id,
            "wp_id": wp_id,
            "item_id": item_id,
            "payload": payload.get(column),
        }
        for item_id, payload in resolved.items()
    ]
    if not params:
        return
    await db.execute(
        sa.text(
            f"""
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, {column}, updated_at, created_at)
            VALUES (:id, :project_id, :wp_id, :item_id, :payload, NOW(), NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET {column} = :payload, updated_at = NOW()
            """  # noqa: S608 - 列名已白名单校验
        ),
        params,
    )


async def _delete_many(db: AsyncSession, wp_id: str, item_ids: Sequence[str]) -> None:
    if not item_ids:
        return
    await db.execute(
        sa.text("DELETE FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :item_id"),
        [{"wp_id": wp_id, "item_id": iid} for iid in item_ids],
    )


async def write_rows(
    db: AsyncSession,
    wp_id: str,
    sheet: str,
    rows: Sequence[Mapping[str, Any]],
    strategy: str = _STRATEGY_OVERWRITE,
) -> ImportOutcome:
    """把分录行写进 `checklist_responses`，按 `spec.key_family` 三族分派。

    冲突策略复用平台既有纯函数 `conflict_resolver.resolve_conflict`
    （`overwrite` / `fill-empty` / `reject`，`reject` 抛 `ConflictRejected`）——
    忽略 `strategy` 参数会让 bulk 侧传 `reject` 时照样覆盖，那是静默数据丢失。

    残留族键清理**只在** `overwrite` 下执行（R11.7）：`fill-empty` 不清、`reject` 不到这一步。
    """
    # 惰性 import：避免 router 层在 import 期拉起整个 bulk_tab 包（与 `get_catalog` 同款处置）
    from app.services.bulk_tab.conflict_resolver import resolve_conflict

    spec = sheet_spec(sheet)
    column = _storage_column(spec)
    warnings: list[str] = []

    kept: list[Mapping[str, Any]] = list(rows)
    if len(kept) > ROW_LIMIT:
        warnings.append(f"数据行数超过{ROW_LIMIT}行限制，已截断")
        kept = kept[:ROW_LIMIT]

    project_id = await _require_project_id(db, wp_id)
    incoming = _incoming_payloads(spec, kept)

    if spec.key_family is KeyFamily.SINGLE_JSON:
        stored = await _fetch_one(db, wp_id, single_json_item_id(spec), column)
    else:
        stored = {}
        for prefix in (spec.per_field_prefix, spec.data_key_prefix):
            if prefix is not None:
                stored.update(await _fetch_by_prefix(db, wp_id, prefix, column))

    existing = {item_id: {column: value} for item_id, value in stored.items()}
    resolved = resolve_conflict(existing, incoming, strategy, sheet_code=spec.sheet_code)  # type: ignore[arg-type]

    collision = sorted(set(resolved) & set(spec.standalone_item_ids))
    if collision:
        _fail(spec.sheet_code, f"往返键与表级独立键撞名 {collision} —— 会把表级说明当行数据写掉")

    removed: list[str] = []
    if _should_purge_residual(spec, strategy):
        removed = _residual_item_ids(spec, stored, len(kept))

    await _upsert_many(db, wp_id, project_id, column, resolved)
    await _delete_many(db, wp_id, removed)
    await db.commit()

    logger.info(
        "X-3 %s 导入落库: %d 行 / %d 键写入 / %d 键清理 (wp=%s, strategy=%s)",
        spec.sheet_code,
        len(kept),
        len(resolved),
        len(removed),
        wp_id,
        strategy,
    )
    return ImportOutcome(len(kept), tuple(sorted(resolved)), tuple(removed), warnings)


# ── 形态 A 三态端点 ────────────────────────────────────────────────────────


def _validate_sheet(sheet: str, allowed: frozenset[str]) -> X3SheetSpec:
    """沿用工厂 `_validate` 的文案（R4.2）；未登记 sheet 一律 400，禁回退成「导出全部」。"""
    if sheet not in allowed:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(allowed)}")
    return sheet_spec(sheet)


def _register_shape_a(router: APIRouter, api_prefix: str, allowed: frozenset[str]) -> None:
    """在**无前缀** router 上注册形态 A 三态。

    🔴 只许传无前缀 router：`APIRouter.add_api_route` 会把 `router.prefix` 拼在路径前面，
    在 `prefix='/api/{长前缀}'` 的宿主 router 上直接注册绝对路径会得到
    `/api/{长前缀}/api/workpapers/...` —— 而 bulk 侧的 `_endpoint_for` 用 `path.endswith`
    找端点**照样能命中**，于是 batch 通路正常、UI 通路 404，正是本 spec 要消灭的那类
    「一半通路静默失效」。故由 `attach_shape_a_routes` 自建无前缀 router 后再搬运路由对象。
    """

    @router.post(f"/api/workpapers/{{wp_id}}/{api_prefix}/{_SUFFIX_TEMPLATE}")
    async def export_template(  # pyright: ignore[reportUnusedFunction]
        wp_id: str,
        sheet: str = Query(...),
        current_user: User = Depends(get_current_user),
    ) -> StreamingResponse:
        _validate_sheet(sheet, allowed)
        return workbook_to_response(build_template_workbook(sheet), f"{sheet}_模板.xlsx")

    @router.post(f"/api/workpapers/{{wp_id}}/{api_prefix}/{_SUFFIX_DATA}")
    async def export_data(  # pyright: ignore[reportUnusedFunction]
        wp_id: str,
        sheet: str = Query(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> StreamingResponse:
        _validate_sheet(sheet, allowed)
        rows, warnings = await load_rows(db, wp_id, sheet)
        wb = build_data_workbook(rows, sheet, warnings=warnings)
        return workbook_to_response(wb, f"{sheet}_数据.xlsx")

    @router.post(f"/api/workpapers/{{wp_id}}/{api_prefix}/{_SUFFIX_IMPORT}")
    async def import_data(  # pyright: ignore[reportUnusedFunction]
        wp_id: str,
        sheet: str = Query(...),
        file: UploadFile = File(...),
        strategy: str = Query(_STRATEGY_OVERWRITE),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> dict[str, Any]:
        from app.services.bulk_tab.conflict_resolver import ConflictRejected

        _validate_sheet(sheet, allowed)
        if not file.filename or not file.filename.endswith(".xlsx"):
            raise HTTPException(400, "请上传 .xlsx 格式文件")
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "文件大小不能超过10MB")

        try:
            outcome = parse_workbook(content, sheet)
        except HTTPException:
            raise
        except Exception as exc:
            # 记 ERROR 后转可读 400。**不是**兜空：既不返回 ok=True，也不落 warning 了事
            logger.error(
                "X-3 %s 导入解析失败 (wp=%s): %s", sheet, wp_id, exc, exc_info=True
            )
            raise HTTPException(400, "无法解析xlsx文件") from exc

        if outcome.errors:
            return {"ok": False, "imported_count": 0, "errors": outcome.errors}

        try:
            written = await write_rows(db, wp_id, sheet, outcome.rows, strategy)
        except ConflictRejected as exc:
            return {"ok": False, "imported_count": 0, "errors": [str(exc)]}
        except ValueError as exc:
            # `working_paper` 不存在 —— 与 `upsert_json_payload` 同一异常契约
            raise HTTPException(400, str(exc)) from exc

        payload: dict[str, Any] = {
            "ok": True,
            "imported_count": written.written_count,
            "errors": [],
        }
        merged = list(outcome.warnings) + list(written.warnings)
        if merged:
            payload["warnings"] = merged
        if outcome.truncated:
            payload["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        if written.removed_item_ids:
            payload["removed_item_ids"] = list(written.removed_item_ids)
        return payload


def _declared_methods(route: Any) -> frozenset[str]:
    """路由对象**声明**的 HTTP 方法集（大写归一 + 剔掉自动派生的 `HEAD` / `OPTIONS`）。

    剔完为空 = 该路由**只**声明了 `HEAD`/`OPTIONS`（一个业务方法都没有）⇒ 返回原始集合，
    让上层比对照样打红。若这里返回空集，`{}` != `{"POST"}` 虽也会红，但错误消息会变成
    「实得 <无方法>」而看不出它声明了什么；更要紧的是**不许**把「剔空」当成通过。
    """
    raw = frozenset(str(m).upper() for m in (getattr(route, "methods", None) or ()))
    return (raw - _AUTO_DERIVED_METHODS) or raw


def _route_signatures(routes: Iterable[Any]) -> list[tuple[str, tuple[str, ...]]]:
    """(路径, 方法集) 的有序清单。

    用 `list` 而非 `set`：同一路径被注册两次（哪怕方法相同）也会被比对出来 —— 重复注册下
    「用户打到哪个端点」由注册顺序决定（first-wins），属静默失效，不该被集合去重吞掉。
    """
    return sorted(
        (getattr(r, "path", ""), tuple(sorted(_declared_methods(r)))) for r in routes
    )


def _fmt_signatures(signatures: Iterable[tuple[str, tuple[str, ...]]]) -> str:
    """把 `_route_signatures` 的输出渲染成 `[POST /a, GET /b]` 形态（错误消息可读性）。"""
    return (
        "["
        + ", ".join(f"{'/'.join(methods) or '<无方法>'} {path}" for path, methods in signatures)
        + "]"
    )


def attach_shape_a_routes(
    host_router: APIRouter, api_prefix: str, sheets: Iterable[str]
) -> None:
    """给宿主 router 挂上 X-3 的形态 A 三态端点（design §C1 / §C2）。

    调用形态（任务 5.1 / 5.2）::

        attach_shape_a_routes(router, api_prefix=<短前缀>, sheets=frozenset({_X3_CODE}))

    三个端点一律 **POST** `/api/workpapers/{wp_id}/{短前缀}/{三态}`（= 前端共享
    composable `useWorkpaperImportExport` 唯一支持的形态），`sheet` 为**必填** query
    参数，鉴权依赖 `Depends(get_current_user)` 与 16 个宿主模块既有三态端点逐字相同。

    路由对象建在**无前缀**子 router 上再搬进宿主 `router.routes`：宿主的 `prefix` 是
    `/api/{长前缀}`，直接在其上注册绝对路径会被前缀污染（见 `_register_shape_a` 的说明）。
    搬运保留宿主的 router 级 `dependencies`（如有），并使 bulk 侧
    `_endpoint_for(module, 短前缀, 三态)` 能在 `module.router.routes` 里按后缀命中。

    搬进宿主前做一次注册自检，按 **(路径, HTTP 方法集)** 双向比对（`_route_signatures`）：
    路径漂移、方法漂移（`@router.post` 误写成 `@router.get`）、同路径重复注册三类都会抛
    `X3ContractError`；`_endpoint_for` 只按路径后缀找端点、不看方法，故方法那一维必须自检。
    """
    allowed = frozenset(sheets)
    if not allowed:
        raise X3ContractError(f"attach_shape_a_routes({api_prefix!r}) 的 sheets 为空")
    unknown = sorted(s for s in allowed if s not in X3_SHEET_SPECS)
    if unknown:
        raise X3ContractError(
            f"attach_shape_a_routes({api_prefix!r}) 收到非 X-3 作业面 sheet {unknown}"
            f"（已登记 {sorted(X3_SHEET_SPECS)}）"
        )
    mismatched = sorted(
        s for s in allowed if X3_SHEET_SPECS[s].api_prefix != api_prefix
    )
    if mismatched:
        raise X3ContractError(
            f"attach_shape_a_routes 的 api_prefix={api_prefix!r} 与清单派生值不一致: "
            + ", ".join(f"{s} -> {X3_SHEET_SPECS[s].api_prefix!r}" for s in mismatched)
        )

    shape_a = APIRouter(
        tags=list(getattr(host_router, "tags", None) or []),
        dependencies=list(getattr(host_router, "dependencies", None) or []),
    )
    _register_shape_a(shape_a, api_prefix, allowed)

    # 注册自检：**路径 + HTTP 方法**双向比对（只比路径抓不住 `@router.post` → `@router.get`
    # 这类漂移 —— 见 `_SHAPE_A_METHOD` 的成块说明）。
    registered = _route_signatures(shape_a.routes)
    expected = sorted(
        (f"/api/workpapers/{{wp_id}}/{api_prefix}/{suffix}", (_SHAPE_A_METHOD,))
        for suffix in (_SUFFIX_TEMPLATE, _SUFFIX_DATA, _SUFFIX_IMPORT)
    )
    if registered != expected:
        raise X3ContractError(
            "形态 A 路由注册结果与预期不一致（路径 + HTTP 方法双向比对）: 实得 "
            f"{_fmt_signatures(registered)} / 应为 {_fmt_signatures(expected)}"
        )
    host_router.routes.extend(shape_a.routes)
    logger.info(
        "X-3 形态 A 三态已挂载: prefix=%s sheets=%s", api_prefix, sorted(allowed)
    )
