"""Feature: x3-adjustment-entry-import-export, Property 4: 列序无关解析与 sheet 身份不符零写入

*For any* 上传的 xlsx，若其列头是源模板 10 列的任意排列（含缺失前端字段的 ``……`` 占位列），
解析结果与按标准列序上传时逐字段相等；若其 sheet 身份与请求的 ``sheet`` 不一致，或请求的
``sheet`` 不在该前缀白名单内，则返回可读错误且 ``checklist_responses`` 无任何写入。

**Validates: Requirements 4.1, 4.2, 4.4, 4.7**

═══════════════════════════════════════════════════════════════════════════════
「零写入」= 库态判据，不是「返回码非 200」（任务 5.4 明确要求）
═══════════════════════════════════════════════════════════════════════════════

实测（本轮探针）：异表名被拒时端点返回的是 **HTTP 200** ``{"ok": false,
"imported_count": 0, "errors": [...]}``，不是 4xx。⇒ 任何「断言状态码 != 200」的判据
对这条通路**恒绿**，而「断言 ``ok is False``」也只是复述实现自己的返回值，抓不到
「先写了一半库再回报错误」这类形态。

故本文件的零写入判据一律是 **``checklist_responses`` 整表快照逐行逐列不变**：

* 快照 = ``SELECT`` 全部 10 列（含 ``created_at`` / ``updated_at``）× 全表行，按
  ``(wp_id, item_id)`` 排序后整体比对。新增 / 删除 / 改值 / 只动时间戳，四类都被抓。
* ``NOW()`` 在夹具里被替换成**单调递增**的替身 ⇒ 一次「值相同的幂等 upsert」也会让
  ``updated_at`` 前移，同样判为「有修改」。判据因此比「值有没有变」更严。
* 库里**预置**了目标 sheet 的族键行与表级独立键行（``standalone_item_ids``）⇒
  「零写入」不是在空表上恒真；越界残留清理（``_residual_item_ids`` 的 DELETE）若在
  被拒通路上误触发，也会被快照的行数差抓到。

反空转的正面对照是 **P4-5**：同一份文件配正确的 ``sheet`` 必须让快照**真的变化**。
没有这条，P4-3 / P4-4 的「快照不变」可能只是因为整条写库通路根本没接通。

═══════════════════════════════════════════════════════════════════════════════
与既有判据的分工（本文件不抄第二份）
═══════════════════════════════════════════════════════════════════════════════

| 面 | 既有归属 | 本文件（Property 4） |
|---|---|---|
| 形态 A 三态是否真注册 / 路径与 HTTP 方法 / ``IE_SHEETS`` 是否唯一真源 | GS3b ``test_x3_shape_a_wiring.py``（结构面） | 不重复 |
| ``sheet`` 参数是否声明且必填（``inspect.signature`` / ``dependant``） | GS3 ``test_ie_prefix_reachability.py``（结构面） | 只留一条**行为**锚点：不带 ``sheet`` 发请求 ⇒ 422 |
| 导出列面 / sheet 名对齐源模板 | GS2 + Property 3 ``test_x3_column_property.py`` | 不重复（本文件只用列面作输入构造） |
| 往返恒等 / 族键爆炸与归约 | Property 1 / Property 2（另任务） | 不重复（本文件只判「有没有写」，不判「写成什么」） |
| **∀ 列序排列下解析结果不变** | 无 | **本文件 P4-1 / P4-2** |
| **异表名 / 未登记 sheet 的库态零写入** | 无（既有判据全在结构面与返回值面） | **本文件 P4-3 / P4-4** |

═══════════════════════════════════════════════════════════════════════════════
零硬编码：作业面 / 列面 / 键面 / 前缀全部从真源装载
═══════════════════════════════════════════════════════════════════════════════

本文件不写任何 X-3 键 / 列头 / sheet 名 / 短前缀字面量：

* 作业面 = ``backend/data/adjustment_ie_contract.json`` 里登记了 ``key_family`` 的条目
  （与实现 ``_select_x3_entries`` 同一口径），并与 ``X3_SHEET_SPECS`` 键集双向锁死。
* 列面 = 实现由清单 ``column_map`` 派生的 ``COLUMN_ORDER``（其「是否真由清单派生」由 GS1
  的替身清单判据承载、其「是否等于源模板实读第 5 行」由 GS2 + Property 3 承载）。
* 每张的 ``field_keys`` / 占位位 / 族前缀 / 落库列 / 表级独立键 / 短前缀 —— 一律取
  ``X3_SHEET_SPECS`` 的 spec 字段。
* 形态 A 端点由生产函数 ``attach_shape_a_routes`` 挂载，``sheets`` 参数按生产同一式子
  （按 ``api_prefix`` 反查 ``X3_SHEET_SPECS``）派生。

═══════════════════════════════════════════════════════════════════════════════
🔴 两条施工期实测、写在这里免得下一轮再踩
═══════════════════════════════════════════════════════════════════════════════

1. **解析结果里的 ``id`` 是每次新生成的 uuid4**（来自被复用的公共实现
   ``parse_row_by_headers``），不是数据字段。故「逐字段相等」必须先剔掉它，同时
   ``test_p4_1`` 反过来断言它**确实每次都不同**（否则「剔掉 id 再比」就成了偷偷放过
   一个真会变的字段）。

2. **``N5-3`` 的「类别」列是占位列（无前端字段）但仍被消费**：``entryType`` 由
   ``CATEGORY_COLUMN_INDEX`` 位的取值派生，与该位有没有前端字段无关。所以
   「占位列内容一律被忽略」这句话对 ``N5-3`` 的类别位**不成立** ——
   ``test_anchor_placeholder_positions`` 把这条非直觉事实钉成断言，
   P4-1 的「占位噪声」维度也据此显式排除该位（不排除会得到一个假红）。

3. **「变形是否退化」必须在可观测层面判，不能在原始单元格层面判**：
   ``safe_str(None) == safe_str("") == ""``、``safe_float(None) == safe_float(0) == 0.0``，
   于是「把一个 ``None`` 列和一个 ``""`` 列换个位置」在字节层面是变形、在解析结果层面是恒等。
   首版 P4-2 按原始单元格判退化，被 hypothesis 找出反例
   （``L2-3`` / ``perm=(0,1,2,3,4,5,6,7,9,8)`` / ``values=[[None,'其他',…,None,'']]``）
   ⇒ 误报「等价判据恒真（守卫缺陷）」。现由 ``_observable`` 这个独立小 oracle 承担该判定，
   其完备性还依赖一条侧条件（生成器造不出源模板示例行），由
   ``test_anchor_sample_row_is_unreachable_from_generated_values`` 钉住。

设计边界（**刻意不当成缺陷锁死，也不当成正确基线锁死**）：实现的
``_foreign_sheet_error`` 对「身份不符」取的是**窄判据** —— 只有活动表名逐字等于**另一张
已登记 X-3** 的 ``sheet_name`` 才拒收；表名为 ``Sheet1`` 之类的手工新建表放行。
``test_p4_3b_identity_judgement_boundary_is_positive_identification`` 把这条边界**双向**
量化出来（∀ 已登记他表名 ⇒ 拒 + 零写入；∀ 中性表名 ⇒ 放行），使边界一旦漂移即打红，
并在该用例的 docstring 里写明「窄判据的残余暴露面」供下一轮裁决。
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import string
import uuid
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

import pytest
import sqlalchemy as sa
from fastapi import APIRouter, FastAPI
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.routers.wp_render_strategies import _x3_adjustment_import_export as impl

_REPO = Path(__file__).resolve().parents[2]
_CONTRACT = _REPO / "backend" / "data" / "adjustment_ie_contract.json"

#: 每条属性的迭代次数（任务要求 ≥100）。带库往返的几条单例成本高一档，仍 ≥100。
_RUNS = 150
_RUNS_DB = 100

#: 合成列名 / 合成表名的探针记号 —— 真实列面与真实 sheet 名里都不会出现。
_MARK = "‡属性探针"

_SETTINGS = settings(
    max_examples=_RUNS,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
_SETTINGS_DB = settings(
    max_examples=_RUNS_DB,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真源装载（清单 → 作业面；实现 → 列面 / 键面 / 前缀）
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=1)
def _contract() -> Mapping[str, Any]:
    assert _CONTRACT.is_file(), f"契约清单缺失：{_CONTRACT}（守卫必须打红而非跳过）"
    doc = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    assert isinstance(doc.get("sheets"), Mapping), "清单 `sheets` 段形态非法"
    return doc


@lru_cache(maxsize=1)
def _codes() -> tuple[str, ...]:
    """作业面 —— 判据 = 条目登记了 ``key_family``（与实现 ``_select_x3_entries`` 同口径）。"""
    sheets = _contract()["sheets"]
    codes = tuple(
        code
        for code, entry in sorted(sheets.items())
        if isinstance(entry, Mapping) and entry.get("key_family")
    )
    assert codes, (
        "清单里没有任何条目登记 `key_family` ⇒ 作业面为空、下面全部 ∀ 属性恒真（空转）。"
        f"真源：{_CONTRACT}"
    )
    return codes


def _spec(code: str) -> Any:
    return impl.sheet_spec(code)


@lru_cache(maxsize=1)
def _face() -> tuple[str, ...]:
    """列面 = 实现由清单 ``column_map`` 派生的 ``COLUMN_ORDER``（只作输入构造用）。"""
    face = tuple(impl.COLUMN_ORDER)
    assert len(face) > 1 and len(set(face)) == len(face), (
        f"列面退化或有重复标签，按列名取值的判据无法成立：{face}"
    )
    return face


@lru_cache(maxsize=None)
def _placeholders(code: str) -> tuple[int, ...]:
    """占位位 = ``field_keys`` 的 ``None`` 位（**不假定只有 F 列**）。"""
    return tuple(i for i, key in enumerate(_spec(code).field_keys) if key is None)


@lru_cache(maxsize=None)
def _ignored_placeholders(code: str) -> tuple[int, ...]:
    """内容**真的**被忽略的占位位 = 占位位减去「类别」列。

    「类别」列即使无前端字段（``N5-3``）也会被 ``derive_entry_type`` 消费 ⇒ 往它写噪声
    会改变 ``entryType`` 与 warnings，不属于「被忽略」。见模块 docstring 第 2 条。
    """
    return tuple(i for i in _placeholders(code) if i != impl.CATEGORY_COLUMN_INDEX)


@lru_cache(maxsize=1)
def _prefix_to_codes() -> dict[str, frozenset[str]]:
    """短前缀 → 该前缀的 X-3 码集合 —— **与生产模块同一式子**（按 ``api_prefix`` 反查）。"""
    out: dict[str, set[str]] = {}
    for code in _codes():
        out.setdefault(_spec(code).api_prefix, set()).add(code)
    return {prefix: frozenset(codes) for prefix, codes in sorted(out.items())}


# ═══════════════════════════════════════════════════════════════════════════
# 2. 上传工作簿构建（列序排列 / 额外列 / 占位噪声）
# ═══════════════════════════════════════════════════════════════════════════


class _Layout(NamedTuple):
    """一份上传文件的版式描述（与具体 sheet 解耦，可 materialize 到 16 张各自）。

    ``perm`` 是列面下标的排列；``extras`` 是插到随机位置的额外列（列名不在列面内）；
    ``noise`` 是给占位位另换的一批取值（用于证明占位内容被忽略）。
    """

    perm: tuple[int, ...]
    extras: tuple[tuple[int, str, Any], ...]
    noise: tuple[Any, ...]


def _write_workbook(title: str, header: Sequence[Any], rows: Sequence[Sequence[Any]]) -> bytes:
    """按给定表名 / 列头 / 数据行造一份真实 xlsx 字节。

    列头落 ``impl._EXPORT_HEADER_ROW`` 行（= 导出布局的列头行，导入解析与之配对），
    行号不写死。
    """
    wb = Workbook()
    ws = wb.active
    ws.title = title
    for _ in range(impl._EXPORT_HEADER_ROW - 1):
        ws.append([])
    ws.append(list(header))
    for row in rows:
        ws.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _apply(
    values: Sequence[Sequence[Any]],
    layout: _Layout | None,
    *,
    noisy: tuple[int, ...] = (),
) -> tuple[list[Any], list[list[Any]]]:
    """把「按列面标准列序的取值矩阵」重排成某个版式的 (列头, 数据行)。

    ``layout is None`` ⇒ 标准列序、无额外列、无噪声（= 比对基准那一侧）。
    ``noisy`` 里的列下标在本次重排时改用 ``layout.noise`` 的取值。
    """
    face = _face()
    perm = tuple(range(len(face))) if layout is None else layout.perm
    header: list[Any] = [face[i] for i in perm]
    body: list[list[Any]] = []
    for row in values:
        cells: list[Any] = []
        for i in perm:
            if layout is not None and i in noisy:
                cells.append(layout.noise[i])
            else:
                cells.append(row[i])
        body.append(cells)

    if layout is not None:
        for at, name, value in layout.extras:
            pos = min(max(at, 0), len(header))
            header.insert(pos, name)
            for cells in body:
                cells.insert(pos, value)
    return header, body


# ═══════════════════════════════════════════════════════════════════════════
# 3. 解析结果归一与比对
# ═══════════════════════════════════════════════════════════════════════════

#: 行标识键 —— 由公共实现每行注入一个新 uuid4，不是数据字段（见模块 docstring 第 1 条）。
_ROW_ID = impl._PARSED_ROW_ID_KEY


def _row_ids(outcome: Any) -> list[Any]:
    return [row.get(_ROW_ID) for row in outcome.rows]


def _fingerprint(outcome: Any) -> tuple[Any, ...]:
    """解析结果的可比对指纹 —— 剔掉行标识键后的逐字段内容 + errors / warnings / truncated。"""
    rows = tuple(
        tuple(sorted((k, v) for k, v in row.items() if k != _ROW_ID)) for row in outcome.rows
    )
    return (rows, tuple(outcome.errors), tuple(outcome.warnings), bool(outcome.truncated))


@lru_cache(maxsize=None)
def _observable_keys(code: str) -> tuple[tuple[int, str], ...]:
    """(列下标, 可观测键) —— 占位位一律剔除（导入侧会 strip 掉），「类别」列另算。

    「类别」列不进这里：它的可观测量不是原始取值而是 ``derive_entry_type`` 的派生结果
    （``N5-3`` 的类别列还是占位位），由 ``_observable`` 单独追加一项。
    """
    return tuple(
        (idx, key)
        for idx, key in enumerate(_spec(code).field_keys)
        if key is not None and idx != impl.CATEGORY_COLUMN_INDEX
    )


def _observable(code: str, header: Sequence[Any], body: Sequence[Sequence[Any]]) -> tuple[Any, ...]:
    """一份上传在**可观测层面**的取值（独立小 oracle，只用来判「变形是否退化」）。

    🔴 为什么必须有它（施工期实测的一条假红）：原始单元格不同 **≠** 解析结果不同 ——
    ``safe_str(None) == safe_str("") == ""``、``safe_float(None) == safe_float(0) == 0.0``。
    于是「把一个 ``None`` 列和一个 ``""`` 列换个位置」在字节层面是变形、在可观测层面是恒等。
    首版 P4-2 按**原始单元格**判退化，被 hypothesis 找出反例
    ``L2-3 / perm=(…,9,8) / values=[…, None, ""]`` ⇒ 误报「等价判据恒真」（假红）。

    三类量一个都不能少、也不能多：
      * 非占位列的**归一后**取值 —— 占位列会被 ``_strip_placeholders`` 剔掉，
        把它算进来会让「换两个占位列」被判成有效变形（同一族的另一个方向的假红）；
      * 「类别」列的 ``derive_entry_type`` **派生结果** —— 不是原始取值：
        实测多个类别值映射到同一个 ``entryType``（``N5-3`` 的类别列还是占位位，
        原始值根本不进行数据行）；
      * 行序 —— 保留（warnings 里带行号）。

    类型归一沿用平台共享 helper（``safe_str`` / ``safe_float`` / ``is_numeric_field_key``）：
    它们不是本属性的被测对象（被测的是「按列名 vs 按位置」这个**取值映射**），故不构成同源。
    """
    face = _face()
    labels = list(header)
    out: list[tuple[Any, ...]] = []
    for row in body:
        cells = list(row) + [None] * max(0, len(labels) - len(row))

        def _at(idx: int) -> Any:
            label = face[idx]
            return cells[labels.index(label)] if label in labels else None

        record: list[tuple[str, Any]] = [
            (
                key,
                impl.safe_float(_at(idx))
                if impl.is_numeric_field_key(key)
                else impl.safe_str(_at(idx)),
            )
            for idx, key in _observable_keys(code)
        ]
        record.append(
            (
                "__x3prop_derived_entry_type",
                impl.derive_entry_type(impl.safe_str(_at(impl.CATEGORY_COLUMN_INDEX))),
            )
        )
        out.append(tuple(record))
    return tuple(out)


def _diff(baseline: Any, candidate: Any) -> list[str]:
    """两次解析结果的逐字段差异（人可读；空列表 = 逐字段相等）。"""
    problems: list[str] = []
    base_rows, cand_rows = baseline.rows, candidate.rows
    if len(base_rows) != len(cand_rows):
        problems.append(f"行数不等：基准 {len(base_rows)} 行、候选 {len(cand_rows)} 行")
    for idx, (b, c) in enumerate(zip(base_rows, cand_rows), start=1):
        keys = sorted((set(b) | set(c)) - {_ROW_ID})
        for key in keys:
            if key not in b:
                problems.append(f"第 {idx} 行多出字段 {key!r}={c[key]!r}")
            elif key not in c:
                problems.append(f"第 {idx} 行缺字段 {key!r}（基准 {b[key]!r}）")
            elif b[key] != c[key]:
                problems.append(f"第 {idx} 行字段 {key!r}：基准 {b[key]!r} != 候选 {c[key]!r}")
    if list(baseline.errors) != list(candidate.errors):
        problems.append(f"errors 不等：基准 {list(baseline.errors)} != 候选 {list(candidate.errors)}")
    if list(baseline.warnings) != list(candidate.warnings):
        problems.append(
            f"warnings 不等：基准 {list(baseline.warnings)} != 候选 {list(candidate.warnings)}"
        )
    if bool(baseline.truncated) != bool(candidate.truncated):
        problems.append(f"truncated 不等：{baseline.truncated} != {candidate.truncated}")
    return problems


# ═══════════════════════════════════════════════════════════════════════════
# 4. 生成器
# ═══════════════════════════════════════════════════════════════════════════

#: 单元格取值字符面 —— 常用汉字 + 拉丁字母数字 + 中英文标点。刻意不含 ``\r`` / ``\n`` /
#: 制表符与前后空白（xlsx 的 XML 做空白归一）与 ``=``（openpyxl 会当公式落盘）——
#: 那些是序列化噪声，与「按列名取值」这一被测性质无关。
_ALPHABET = (
    "甲乙丙丁戊己庚辛壬癸一二三四五六七八九十零壹贰叁肆伍陆柒捌玖"
    "京沪粤苏浙鲁豫川渝陕甘青蒙桂黔滇藏宁新"
    + string.ascii_letters
    + string.digits
    + "，。、；：（）【】《》“”‘’—～·%&#@!?+-*/_|^$<>"
)
_LONG_CN = "壹贰叁肆伍陆柒捌玖拾京沪粤苏浙鲁豫川渝陕"

_arb_text = st.text(alphabet=_ALPHABET, min_size=0, max_size=20)
_arb_long = st.builds(lambda n: _LONG_CN * n, st.integers(min_value=3, max_value=6))
_arb_number = st.one_of(
    st.integers(min_value=-10**9, max_value=10**9),
    st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-1e-6, max_value=1e-6, allow_nan=False, allow_infinity=False),
)
_arb_cell = st.one_of(st.none(), _arb_text, _arb_long, _arb_number)


@lru_cache(maxsize=1)
def _categories() -> tuple[str, ...]:
    """「类别」列的枚举取值面 + 一个枚举外取值（后者走兜底并记 warning）。

    枚举本体取实现的派生映射表（唯一定义处），不在本文件写死中文枚举字面量。
    """
    return tuple(sorted(impl.CATEGORY_TO_ENTRY_TYPE)) + (f"{_MARK}枚举外",)


def _arb_values(width: int) -> st.SearchStrategy[list[list[Any]]]:
    """标准列序的取值矩阵（0~4 行）。「类别」列单独取枚举面，其余列取任意值。"""
    idx = impl.CATEGORY_COLUMN_INDEX

    def one_row() -> st.SearchStrategy[list[Any]]:
        cells = [
            st.sampled_from(_categories()) if i == idx else _arb_cell for i in range(width)
        ]
        return st.tuples(*cells).map(list)

    return st.lists(one_row(), min_size=0, max_size=4)


def _arb_layout(width: int) -> st.SearchStrategy[_Layout]:
    return st.builds(
        _Layout,
        perm=st.permutations(range(width)).map(tuple),
        extras=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=width),
                st.integers(min_value=0, max_value=9).map(lambda n: f"{_MARK}额外列{n}"),
                _arb_cell,
            ),
            max_size=2,
        ).map(tuple),
        noise=st.tuples(*([_arb_cell] * width)),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 库夹具 + 形态 A 端点（零写入判据的载体）
# ═══════════════════════════════════════════════════════════════════════════

#: ``checklist_responses`` 的全部列（顺序 = 迁移 V085 + V088/V089/V098 的最终形态）。
#: 快照取**全部**列：只比 ``item_id`` / 值列会漏掉「只动时间戳」的幂等 upsert。
_SNAPSHOT_COLUMNS = (
    "id",
    "project_id",
    "wp_id",
    "item_id",
    "conclusion",
    "remark",
    "wp_ref",
    "updated_by",
    "created_at",
    "updated_at",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS working_paper (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS checklist_responses (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        wp_id TEXT NOT NULL,
        item_id VARCHAR(64) NOT NULL,
        conclusion TEXT,
        remark TEXT,
        wp_ref VARCHAR(100),
        updated_by TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        UNIQUE (wp_id, item_id)
    )
    """,
)

_PROJECT_ID = "3f7c1a02-0000-4000-8000-000000000001"


class _Reply(NamedTuple):
    status: int
    body: Any


class _Harness:
    """一个事件循环 + 一个 sqlite 引擎 + 一个挂了 16 个前缀形态 A 三态的 ASGI 客户端。

    🔴 全程复用**同一个** loop：aiosqlite 的连接绑定在创建它的 loop 上，每次迭代各起一个
    ``asyncio.run`` 会在第二次就拿到一个已关闭 loop 上的连接（平台踩过的同族坑）。

    🔴 ``NOW()`` 在 sqlite 不存在（实现的 upsert SQL 用到它），此处注册一个**单调递增**的
    替身：既让 sqlite 跑得通，又让「值相同的幂等 upsert」也表现为 ``updated_at`` 前移，
    从而被整表快照抓到。
    """

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._tick = 0
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine.sync_engine, "connect")
        def _register_now(dbapi_connection: Any, _record: Any) -> None:
            dbapi_connection.create_function("NOW", 0, self._next_now)

        self.maker = async_sessionmaker(self.engine, expire_on_commit=False)
        #: 逐 sheet 一个底稿 id —— 跨 sheet 的族键互不干扰，快照仍覆盖全表
        self.wp_ids = {
            code: f"3f7c1a02-0000-4000-9000-{idx:012d}"
            for idx, code in enumerate(_codes(), start=1)
        }
        self.app = self._build_app()
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://x3-parse-property"
        )
        self.loop.run_until_complete(self._setup())

    # ── 生命周期 ──────────────────────────────────────────────────────────
    def _next_now(self) -> str:
        self._tick += 1
        return f"2026-01-01T00:00:00.{self._tick:09d}"

    def _build_app(self) -> FastAPI:
        from app.core.database import get_db
        from app.deps import get_current_user

        host = APIRouter()
        for prefix, codes in _prefix_to_codes().items():
            # 与生产同一调用形态：sheets = 按 api_prefix 反查出的 X-3 码集合
            impl.attach_shape_a_routes(host, api_prefix=prefix, sheets=codes)
        app = FastAPI()
        app.include_router(host)

        async def _db_override() -> Any:
            async with self.maker() as session:
                yield session

        class _User:
            id = "3f7c1a02-0000-4000-a000-000000000001"
            role = "admin"

        app.dependency_overrides[get_db] = _db_override
        app.dependency_overrides[get_current_user] = lambda: _User()
        return app

    async def _setup(self) -> None:
        async with self.engine.begin() as conn:
            for ddl in _DDL:
                await conn.execute(sa.text(ddl))
        async with self.maker() as db:
            for code, wp_id in self.wp_ids.items():
                await db.execute(
                    sa.text(
                        "INSERT INTO working_paper (id, project_id, is_deleted) "
                        "VALUES (:id, :pid, 0)"
                    ),
                    {"id": wp_id, "pid": _PROJECT_ID},
                )
            await db.commit()
        await self._reseed()

    async def _reseed(self) -> None:
        async with self.maker() as db:
            await db.execute(sa.text("DELETE FROM checklist_responses"))
            for code, wp_id in self.wp_ids.items():
                for item_id, column, value in _seed_rows(code):
                    await db.execute(
                        sa.text(
                            f"INSERT INTO checklist_responses "  # noqa: S608 - 列名取自白名单
                            f"(id, project_id, wp_id, item_id, {column}, created_at, updated_at) "
                            "VALUES (:id, :pid, :wp, :iid, :val, :ts, :ts)"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "pid": _PROJECT_ID,
                            "wp": wp_id,
                            "iid": item_id,
                            "val": value,
                            "ts": "2026-01-01T00:00:00.000000000",
                        },
                    )
            await db.commit()

    def reset(self) -> None:
        """把 ``checklist_responses`` 恢复成预置态 —— 每条库判据开头调一次。

        没有它，本文件的库判据就**互相依赖执行顺序**：``overwrite`` 策略会清掉行号超出的
        残留族键（P4-5 只导 1 行 ⇒ 预置的第 2 行被删），后跑的判据就再也见不到那批预置行。
        判据之间靠顺序才成立 = 单独跑 ``-k`` 时结论会变，属守卫缺陷。
        """
        self.loop.run_until_complete(self._reseed())

    def close(self) -> None:
        try:
            self.loop.run_until_complete(self.client.aclose())
            self.loop.run_until_complete(self.engine.dispose())
        finally:
            self.loop.close()

    # ── 库态快照 ──────────────────────────────────────────────────────────
    def snapshot(self) -> tuple[tuple[Any, ...], ...]:
        async def _run() -> tuple[tuple[Any, ...], ...]:
            async with self.maker() as db:
                result = await db.execute(
                    sa.text(
                        f"SELECT {', '.join(_SNAPSHOT_COLUMNS)} FROM checklist_responses "  # noqa: S608
                        "ORDER BY wp_id, item_id"
                    )
                )
                return tuple(tuple(row) for row in result.fetchall())

        return self.loop.run_until_complete(_run())

    # ── 三态端点调用 ──────────────────────────────────────────────────────
    def call(
        self, code: str, action: str, *, sheet: str | None, content: bytes | None = None
    ) -> _Reply:
        prefix = _spec(code).api_prefix
        wp_id = self.wp_ids[code]
        params = {} if sheet is None else {"sheet": sheet}
        files = (
            None
            if content is None
            else {
                "file": (
                    "upload.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
        )

        async def _run() -> _Reply:
            resp = await self.client.post(
                f"/api/workpapers/{wp_id}/{prefix}/{action}", params=params, files=files
            )
            ctype = resp.headers.get("content-type", "")
            body: Any = resp.json() if "json" in ctype else resp.content
            return _Reply(status=resp.status_code, body=body)

        return self.loop.run_until_complete(_run())


def _seed_rows(code: str) -> list[tuple[str, str, str]]:
    """预置行 —— 目标 sheet 的族键（行 1~2）+ 表级独立键。

    预置的意义：让「零写入」在**非空表**上判定，并使「越界残留清理误触发」（会删掉行 2）
    与「幂等 upsert」（会前移时间戳）两类形态都落在快照差里。
    """
    spec = _spec(code)
    column = spec.storage_field
    seeded: list[tuple[str, str, str]] = []
    if spec.key_family is impl.KeyFamily.SINGLE_JSON:
        seeded.append((impl.single_json_item_id(spec), column, f"[]{_MARK}预置"))
    else:
        for row_no in (1, 2):
            if spec.per_field_prefix is not None:
                for suffix in spec.per_field_suffixes:
                    seeded.append(
                        (
                            impl.per_field_item_id(spec, row_no, suffix),
                            column,
                            f"{_MARK}预置{row_no}",
                        )
                    )
            if spec.data_key_prefix is not None:
                seeded.append(
                    (impl.data_item_id(spec, row_no), column, f"{{}}{_MARK}预置{row_no}")
                )
    for item_id in spec.standalone_item_ids:
        seeded.append((item_id, column, f"{_MARK}表级独立键"))
    return seeded


_HARNESS: _Harness | None = None


def _hz() -> _Harness:
    global _HARNESS
    if _HARNESS is None:
        _HARNESS = _Harness()
    return _HARNESS


@pytest.fixture(scope="session", autouse=True)
def _harness_lifecycle() -> Any:
    yield
    global _HARNESS
    if _HARNESS is not None:
        _HARNESS.close()
        _HARNESS = None


# ═══════════════════════════════════════════════════════════════════════════
# 6. 前置锚点（反空转；红 = 作业面或夹具塌了，下面的属性结论不可解读）
# ═══════════════════════════════════════════════════════════════════════════


def test_anchor_workscope_and_prefixes() -> None:
    """作业面规模 / 与实现键集一致 / 短前缀 16 个互不相同 —— 塌陷时 ∀ 属性恒真。"""
    codes = _codes()
    assert len(codes) == 16, (
        f"作业面实测 {len(codes)} 张（design 用户裁决 1：16 张，零 pending_manual）：{list(codes)}"
    )
    assert set(codes) == set(impl.X3_SHEET_SPECS), (
        "清单派生作业面与实现 `X3_SHEET_SPECS` 分叉：\n"
        f"  清单={sorted(codes)}\n  实现={sorted(impl.X3_SHEET_SPECS)}"
    )
    prefixes = _prefix_to_codes()
    assert len(prefixes) == len(codes), (
        f"短前缀数 {len(prefixes)} != sheet 数 {len(codes)} ⇒ 有前缀承载了多于一张 X-3，"
        f"「未登记 sheet ⇒ 400」的量化面会失真：{ {p: sorted(c) for p, c in prefixes.items()} }"
    )
    assert len({_spec(c).sheet_name for c in codes}) == len(codes), (
        "16 张的 sheet_name 不唯一 ⇒ 「异表名」判据会互相蒙对"
    )


def test_anchor_placeholder_positions() -> None:
    """占位位分布 + 🔴「类别」列是占位位却仍被消费（``N5-3``）—— 把非直觉事实钉成断言。"""
    dist: dict[int, list[str]] = {}
    for code in _codes():
        dist.setdefault(len(_placeholders(code)), []).append(code)
    counts = {n: len(v) for n, v in sorted(dist.items())}
    assert counts == {1: 14, 2: 1, 6: 1}, (
        "占位位分布与实测不符（14 张 1 个 / L2-3 2 个 / N5-3 6 个）："
        f"{ {n: sorted(v) for n, v in sorted(dist.items())} }"
    )

    consumed = sorted(
        c for c in _codes() if impl.CATEGORY_COLUMN_INDEX in _placeholders(c)
    )
    assert len(consumed) == 1, (
        "「类别列无前端字段但仍被 entryType 派生消费」的 sheet 实测恰 1 张，现为 "
        f"{consumed} ⇒ P4-1 的「占位噪声」维度排除面已变，须重核（否则会出假红/漏判）"
    )
    for code in _codes():
        assert _ignored_placeholders(code) or code in consumed, (
            f"{code} 的可忽略占位位为空且不属类别列例外 ⇒ 占位噪声维度对它空转"
        )


def test_anchor_sample_row_is_unreachable_from_generated_values() -> None:
    """生成器造不出源模板示例行 ⇒ 「示例行跳过」分支在本文件恒不触发。

    这条是 P4-2 退化判据的**侧条件**：``_matches_sample_row`` 比的是**含占位列**的全部 10 列，
    若生成器能凑出示例行，则「跳过与否」会依赖占位列取值，而 ``_observable``（刻意剔除占位列）
    就不再是完备的退化判据 ⇒ 会出现「观测相同但解析结果不同」的假红。

    实测：唯一有示例行的 ``L2-3``，其文本列取值含生成字符面之外的字符 ⇒ 不可达。
    示例行本体取清单登记值（``spec.sample_row``），本文件不写它的字面量。
    """
    alphabet = set(_ALPHABET) | set(_LONG_CN) | set(_MARK)
    with_sample = [c for c in _codes() if _spec(c).sample_row]
    assert with_sample, (
        "没有任何 sheet 登记了示例行 ⇒ 本条侧条件无对象。若清单确实清空了 sample_row，"
        "P4-2 的退化判据可直接成立，但要人工确认一次再改这条断言"
    )
    for code in with_sample:
        spec = _spec(code)
        unreachable = [
            (idx, cell)
            for idx, cell in enumerate(spec.sample_row)
            if idx < len(spec.field_keys)
            and not impl.is_numeric_field_key(str(spec.field_keys[idx] or ""))
            and (set(str(cell)) - alphabet)
        ]
        assert unreachable, (
            f"{code} 的示例行 {list(spec.sample_row)} 的每一个文本列都能由生成字符面凑出 ⇒ "
            "「示例行跳过」分支可能被触发，P4-2 的 `_observable` 退化判据不再完备（会出假红）。"
            "收口方式：从 `_ALPHABET` 里剔掉示例行用到的字符，或把占位列取值也纳入 `_observable`"
        )


def test_anchor_db_fixture_is_writable_and_seeded() -> None:
    """夹具自检：``NOW()`` 替身生效、预置行落库、快照能读到全部列。

    这条红 = 下面「快照不变」类判据一律不可解读（可能只是库根本没接通）。
    """
    hz = _hz()
    hz.reset()
    snapshot = hz.snapshot()
    assert snapshot, "预置行没落库 ⇒ 「零写入」会在空表上恒真（空转）"
    assert len(snapshot[0]) == len(_SNAPSHOT_COLUMNS), (
        f"快照列数 {len(snapshot[0])} != 期望 {len(_SNAPSHOT_COLUMNS)}"
    )
    by_wp: dict[Any, int] = {}
    for row in snapshot:
        by_wp[row[_SNAPSHOT_COLUMNS.index("wp_id")]] = (
            by_wp.get(row[_SNAPSHOT_COLUMNS.index("wp_id")], 0) + 1
        )
    assert len(by_wp) == len(_codes()), (
        f"只有 {len(by_wp)} 张 sheet 的底稿有预置行，期望 {len(_codes())}"
    )

    async def _probe_now() -> tuple[Any, Any]:
        async with hz.maker() as db:
            first = (await db.execute(sa.text("SELECT NOW()"))).scalar()
            second = (await db.execute(sa.text("SELECT NOW()"))).scalar()
            return first, second

    first, second = hz.loop.run_until_complete(_probe_now())
    assert first and second and str(first) < str(second), (
        f"`NOW()` 替身不是单调递增（{first!r} → {second!r}）⇒ 「幂等 upsert 也算修改」"
        "这条更严的判据失效"
    )


def test_anchor_sheet_query_param_is_required() -> None:
    """R4.1 行为锚点：三态端点不带 ``sheet`` 一律 422（结构面由 GS3 / GS3b 承载）。"""
    hz = _hz()
    code = _codes()[0]
    content = _write_workbook(_spec(code).sheet_name, _face(), [])
    for action, payload in (
        (impl._SUFFIX_TEMPLATE, None),
        (impl._SUFFIX_DATA, None),
        (impl._SUFFIX_IMPORT, content),
    ):
        reply = hz.call(code, action, sheet=None, content=payload)
        assert reply.status == 422, (
            f"{code} 的 {action} 端点在**不传** sheet 时返回 {reply.status}（期望 422）⇒ "
            f"`sheet` 不是必填参数，FastAPI 会静默丢弃它：{reply.body!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. P4-1 —— ∀ sheet × ∀ 列序排列 × ∀ 取值：解析结果与标准列序逐字段相等
# ═══════════════════════════════════════════════════════════════════════════


def test_p4_1_parse_is_invariant_under_any_column_permutation() -> None:
    """∀ 16 张 × ∀ 列面排列 × ∀ 取值：``parse_workbook`` 结果与标准列序上传逐字段相等。

    同一次迭代覆盖三个维度：

    * **列序排列** —— ``perm`` 是列面下标的任意排列（含恒等）；
    * **额外列** —— 插入 0~2 个列面外的列，其内容必须被忽略（用户加辅助列不该改变结果）；
    * **占位噪声** —— 给「内容真被忽略」的占位位另换一批取值（排除「类别」列，见
      ``test_anchor_placeholder_positions``），结果仍须逐字段相等。

    若实现改成按**位置** ``zip(headers, field_keys)`` 取值（公共实现里就有这条旧分支），
    非恒等排列会立刻让结果分叉 ⇒ 本条打红。
    """
    face = _face()
    width = len(face)
    seen = {
        "sheets": set(),
        "row_counts": set(),
        "value_kinds": set(),
        "extras": set(),
        "nontrivial_perm": 0,
        "effective": 0,
        "noise_applied": 0,
    }

    @given(values=_arb_values(width), layout=_arb_layout(width))
    @_SETTINGS
    def prop(values: list[list[Any]], layout: _Layout) -> None:
        seen["row_counts"].add(len(values))
        seen["extras"].add(len(layout.extras))
        if layout.perm != tuple(range(width)):
            seen["nontrivial_perm"] += 1
        for row in values:
            for value in row:
                if value is None:
                    seen["value_kinds"].add("none")
                elif isinstance(value, (int, float)):
                    seen["value_kinds"].add("number")
                elif value == "":
                    seen["value_kinds"].add("empty")
                elif len(value) > 30:
                    seen["value_kinds"].add("long_cn")
                elif any(ch in value for ch in "，。（）%&#@!?+-*/_|^$<>"):
                    seen["value_kinds"].add("special")
                else:
                    seen["value_kinds"].add("text")

        base_header, base_body = _apply(values, None)
        for code in _codes():
            spec = _spec(code)
            seen["sheets"].add(code)
            noisy = _ignored_placeholders(code)
            if noisy and values:
                seen["noise_applied"] += 1
            baseline = impl.parse_workbook(
                _write_workbook(spec.sheet_name, base_header, base_body), code
            )
            assert not baseline.errors, (
                f"{code} 的**标准列序**基准就被判错 ⇒ 后面的等价比对不可归因："
                f"{list(baseline.errors)}"
            )
            header, body = _apply(values, layout, noisy=noisy)
            candidate = impl.parse_workbook(
                _write_workbook(spec.sheet_name, header, body), code
            )
            problems = _diff(baseline, candidate)
            assert not problems, (
                f"{code}（{spec.sheet_name}）列序变了就解析出不同结果 ⇒ 解析不是按列名取值"
                f"（R4.1）：\n  排列={layout.perm}\n  额外列={[e[1] for e in layout.extras]}"
                f"\n  占位噪声位={noisy}\n" + "".join(f"  {p}\n" for p in problems)
            )
            if baseline.rows and layout.perm != tuple(range(width)):
                seen["effective"] += 1

            # 行标识键是每次新生成的 uuid4，不是数据字段 —— 反过来钉住它「确实会变」，
            # 免得「剔掉 id 再比」把一个真会变的字段偷偷放过去。
            base_ids, cand_ids = _row_ids(baseline), _row_ids(candidate)
            assert len(base_ids) == len(cand_ids)
            for one in base_ids + cand_ids:
                assert isinstance(one, str) and uuid.UUID(one), f"{code}: 行标识键形态异常 {one!r}"
            assert not (set(base_ids) & set(cand_ids)), (
                f"{code}: 两次解析拿到了相同的行标识键 {sorted(set(base_ids) & set(cand_ids))} ⇒ "
                f"它不是每行新生成的 uuid4，`_fingerprint` 不该把它剔掉"
            )
            assert _fingerprint(baseline) == _fingerprint(candidate)

    prop()

    assert seen["sheets"] == set(_codes()), (
        f"只覆盖了 {len(seen['sheets'])} 张 sheet：{sorted(seen['sheets'])}"
    )
    assert 0 in seen["row_counts"] and max(seen["row_counts"]) >= 3, (
        f"行数维度覆盖不足（须含 0 行与 ≥3 行）：{sorted(seen['row_counts'])}"
    )
    assert {"none", "empty", "number", "long_cn", "special", "text"} <= seen["value_kinds"], (
        f"取值维度覆盖不足：{sorted(seen['value_kinds'])}"
    )
    assert max(seen["extras"]) >= 1, "「额外列」维度未覆盖 ⇒ 该维度空转"
    assert seen["nontrivial_perm"] >= 50, (
        f"非恒等排列只生成了 {seen['nontrivial_perm']} 次 ⇒ 「列序无关」这一维实际空转"
    )
    assert seen["effective"] >= 50, (
        f"「非恒等排列 + 有数据行」的有效实例只有 {seen['effective']} 个 ⇒ 覆盖不足"
        "（空表下任何排列都恒等，等价比对会恒真）"
    )
    assert seen["noise_applied"] >= 50, f"占位噪声维度只生效 {seen['noise_applied']} 次"


# ═══════════════════════════════════════════════════════════════════════════
# 8. P4-2 —— 判据非退化：∀ 上传变形必被判出（反空转的正面证明）
# ═══════════════════════════════════════════════════════════════════════════

_DEFORMS = (
    "header_rename",
    "header_drop",
    "header_dup",
    "values_not_permuted",
    "foreign_title",
)


def _deform(
    header: list[Any], body: list[list[Any]], title: str, kind: str, i: int, code: str
) -> tuple[list[Any], list[list[Any]], str]:
    """把一份合法上传改坏一处。返回 (列头, 数据行, 表名)。"""
    header = list(header)
    body = [list(r) for r in body]
    if kind == "header_rename":
        header[i] = f"{header[i]}{_MARK}"
    elif kind == "header_drop":
        del header[i]
        for row in body:
            del row[i]
    elif kind == "header_dup":
        header[i] = header[(i + 1) % len(header)]
    elif kind == "foreign_title":
        others = [c for c in _codes() if c != code]
        title = _spec(others[i % len(others)]).sheet_name
    else:  # pragma: no cover - `values_not_permuted` 由调用方就地构造，其余由词表限定
        raise AssertionError(f"未实现的变形：{kind}")
    return header, body, title


def test_p4_2_judgement_rejects_any_deformed_upload() -> None:
    """∀ 变形 × ∀ sheet × ∀ 取值：判据必须**判出差异或报错**（证明等价比对不是恒真）。

    同一次迭代先跑 CONTROL（未变形 ⇒ 与基准逐字段相等），再施加变形 ⇒ 「变形后打红」
    可归因于变形本身。变形若退化成恒等（例如 ``values_not_permuted`` 遇到恒等排列、
    或整行取值恰好对称），则反过来断言**仍然等价** —— 不给判据留「反正总能报个不同」的空子。
    """
    face = _face()
    width = len(face)
    seen_kinds: set[str] = set()
    seen_effective: set[str] = set()

    # 施工期由 hypothesis 找到的那条反例，就地钉成 `@example` —— `.hypothesis/examples`
    # 是本机缓存（不进版本库），只靠它复现等于把回归判据交给一个会被清掉的目录。
    # 这条实例的含义：交换两个「一个 None / 一个空串」的列 = 字节层面变形、可观测层面恒等。
    @example(
        values=[[None, sorted(impl.CATEGORY_TO_ENTRY_TYPE)[0], None, None, None, None, None, None, None, ""]],
        layout=_Layout(
            perm=tuple(list(range(width - 2)) + [width - 1, width - 2]),
            extras=(),
            noise=tuple([None] * width),
        ),
        kind="values_not_permuted",
        i=0,
        code=sorted(_codes())[0],
    )
    @given(
        values=_arb_values(width),
        layout=_arb_layout(width),
        kind=st.sampled_from(_DEFORMS),
        i=st.integers(min_value=0, max_value=width - 1),
        code=st.sampled_from(sorted(_codes())),
    )
    @_SETTINGS
    def prop(
        values: list[list[Any]], layout: _Layout, kind: str, i: int, code: str
    ) -> None:
        seen_kinds.add(kind)
        spec = _spec(code)
        base_header, base_body = _apply(values, None)
        baseline = impl.parse_workbook(
            _write_workbook(spec.sheet_name, base_header, base_body), code
        )
        assert not baseline.errors, (
            f"CONTROL 失败：{code} 标准列序基准就被判错 ⇒ 变形后的红不可归因："
            f"{list(baseline.errors)}"
        )

        header, body = _apply(values, _Layout(layout.perm, (), layout.noise), noisy=())
        control = impl.parse_workbook(_write_workbook(spec.sheet_name, header, body), code)
        control_diff = _diff(baseline, control)
        assert not control_diff, (
            f"CONTROL 失败：{code} 仅做列序排列就与基准不等 ⇒ P4-1 本该先红：\n"
            + "".join(f"  {p}\n" for p in control_diff)
        )

        if kind == "values_not_permuted":
            # 列头按 perm 排列、取值仍按标准列序 —— 按**列名**取值的实现必然读到不同的格子
            bad_header = [face[p] for p in layout.perm]
            bad_body = [list(row) for row in values]
            bad_title = spec.sheet_name
        else:
            bad_header, bad_body, bad_title = _deform(
                header, body, spec.sheet_name, kind, i, code
            )

        # 🔴 退化判定在**可观测层面**，不在原始单元格层面（见 `_observable` 的成块说明）
        degenerate = (
            bad_title == spec.sheet_name
            and list(bad_header) == list(header)
            and _observable(code, bad_header, bad_body) == _observable(code, header, body)
        )
        broken = impl.parse_workbook(_write_workbook(bad_title, bad_header, bad_body), code)
        if degenerate:
            assert not _diff(baseline, broken), (
                f"{code} 的 {kind}(i={i}) 变形在可观测层面退化成恒等，判据却报了差异 ⇒ "
                f"判据会无故打红：\n" + "".join(f"  {p}\n" for p in _diff(baseline, broken))
            )
            return

        seen_effective.add(kind)
        assert broken.errors or _diff(baseline, broken), (
            f"{code} 施加 {kind}(i={i}) 变形后，解析结果与基准**仍然逐字段相等且无报错** ⇒ "
            f"**等价判据恒真（守卫缺陷）**。\n  变形后列头={bad_header}\n  变形后表名={bad_title!r}"
        )

    prop()
    assert seen_kinds == set(_DEFORMS), f"变形词表未全覆盖：缺 {sorted(set(_DEFORMS) - seen_kinds)}"
    assert seen_effective == set(_DEFORMS), (
        "以下变形从未产生过有效（非恒等）实例 ⇒ 该维度实际空转："
        f"{sorted(set(_DEFORMS) - seen_effective)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9. P4-3 —— 上传文件的 sheet 身份不符 ⇒ 可读错误 + 库态零写入（R4.7）
# ═══════════════════════════════════════════════════════════════════════════


def test_p4_3_foreign_sheet_identity_writes_nothing(  # noqa: PLR0915
) -> None:
    """∀ 取值 × ∀「目标 sheet 配另一张已登记 X-3 的表名」：可读错误 + 整表快照逐行逐列不变。

    ``shift`` 让 16 张目标各配一个**不同**的他表名，故每次迭代都覆盖全部 16 张、
    且他表名随迭代轮换（不会固定成同一对）。

    快照在**16 次请求之前**取一次、**之后**取一次：任何一次请求写了库都会落在同一个差里，
    比逐次取快照更省时也更严（写了又改回去也算差异，因为 ``updated_at`` 会前移）。
    """
    hz = _hz()
    hz.reset()
    face = _face()
    width = len(face)
    codes = _codes()
    seen: dict[str, Any] = {"sheets": set(), "titles": set(), "row_counts": set(), "shifts": set()}

    @given(
        values=_arb_values(width),
        layout=_arb_layout(width),
        shift=st.integers(min_value=1, max_value=len(codes) - 1),
    )
    @_SETTINGS_DB
    def prop(values: list[list[Any]], layout: _Layout, shift: int) -> None:
        seen["row_counts"].add(len(values))
        seen["shifts"].add(shift)
        before = hz.snapshot()
        replies: list[tuple[str, str, _Reply]] = []
        for idx, code in enumerate(codes):
            spec = _spec(code)
            foreign = _spec(codes[(idx + shift) % len(codes)])
            seen["sheets"].add(code)
            seen["titles"].add(foreign.sheet_name)
            header, body = _apply(values, layout, noisy=_ignored_placeholders(code))
            content = _write_workbook(foreign.sheet_name, header, body)
            replies.append(
                (code, foreign.sheet_name, hz.call(code, impl._SUFFIX_IMPORT, sheet=code, content=content))
            )
        after = hz.snapshot()

        # ① 零写入 —— 判据是库态，不是返回码
        assert before == after, (
            "上传文件的 sheet 身份与请求的 sheet 不一致，但 `checklist_responses` 发生了变化"
            f"（R4.7 要求写库前返回错误）：\n{_snapshot_delta(before, after)}"
        )

        # ② 可读错误 —— 必须同时点出「传的是哪张表」与「要的是哪张表」
        for code, title, reply in replies:
            assert reply.status == 200, (
                f"{code} 配他表名 {title!r} 时返回 {reply.status}（实测实现走的是 200 + "
                f"ok=false 通路）：{reply.body!r}"
            )
            body = reply.body
            assert isinstance(body, Mapping), f"{code}: 响应体形态异常 {body!r}"
            assert body.get("ok") is False and body.get("imported_count") == 0, (
                f"{code} 配他表名 {title!r} 竟被判为可导入：{body!r}"
            )
            errors = body.get("errors") or []
            assert errors, f"{code}: 拒收了却没给出任何可读错误 —— 用户看不到原因：{body!r}"
            joined = " ".join(str(e) for e in errors)
            assert title in joined, (
                f"{code}: 错误消息没点出上传文件的工作表名 {title!r}，用户无从判断传错了哪份："
                f"{joined!r}"
            )
            assert code in joined, (
                f"{code}: 错误消息没点出本次请求的 sheet 码，无从判断该去哪张表重新导出：{joined!r}"
            )

    prop()
    assert seen["sheets"] == set(codes), (
        f"只覆盖了 {len(seen['sheets'])} 张目标 sheet：{sorted(seen['sheets'])}"
    )
    assert len(seen["titles"]) == len(codes), (
        f"他表名只用到 {len(seen['titles'])} 种，期望 {len(codes)} 种"
    )
    assert len(seen["shifts"]) >= 5, (
        f"shift 只取到 {sorted(seen['shifts'])} ⇒ 「目标 sheet ↔ 他表名」的配对面固定，"
        "换不到别的组合（该维度覆盖不足）"
    )
    assert 0 in seen["row_counts"] and max(seen["row_counts"]) >= 2, (
        f"行数维度覆盖不足：{sorted(seen['row_counts'])}"
    )


def test_p4_3b_identity_judgement_boundary_is_positive_identification() -> None:
    """身份判据的**边界**：只有「正面识别为另一张已登记 X-3」才拒收。

    实现的 ``_foreign_sheet_error`` 刻意取窄判据（源码有成块说明）：活动表名逐字等于
    **别的** X-3 的 ``sheet_name`` 才拒，``Sheet1`` 之类手工新建表放行。

    本条把该边界**双向**量化：∀ 已登记他表名 ⇒ 拒 + 零写入；∀ 中性表名 ⇒ 放行。
    一旦判据变宽（把中性表名也拒了，会把手工填表的用户挡在门外）或变窄（连他表名也放行，
    会让 A 表的导出文件静默覆盖 B 表）都打红。

    🔴 **残余暴露面（本 spec 未裁决，留给下一轮）**：窄判据下，一份表名中性、列头齐全的
    文件可以被导入任意一张 X-3。design Property 4 的字面表述（「sheet 身份与请求的 sheet
    不一致」）比这条窄判据宽；本文件**不**把任一侧当成正确基线锁死，只把当前边界钉出来，
    使它无法在无人察觉的情况下漂移。
    """
    hz = _hz()
    hz.reset()
    face = _face()
    codes = _codes()
    neutral_seen: set[str] = set()
    foreign_seen = 0

    @given(
        code=st.sampled_from(sorted(codes)),
        neutral=st.text(
            alphabet=string.ascii_letters + string.digits + "工作表 -_", min_size=1, max_size=12
        ),
    )
    @_SETTINGS_DB
    def prop(code: str, neutral: str) -> None:
        nonlocal foreign_seen
        spec = _spec(code)
        registered = {_spec(c).sheet_name for c in codes}
        # 带一行真数据：否则「拒收了却仍解析出行」那条断言在空表上恒真（空转）
        payload: list[Any] = [f"{_MARK}身份{n}" for n in range(len(face))]
        payload[impl.CATEGORY_COLUMN_INDEX] = sorted(impl.CATEGORY_TO_ENTRY_TYPE)[0]
        header, body = _apply([payload], None)

        # ① 中性表名（不等于任何已登记 sheet_name）⇒ 放行（无 errors）
        title = neutral.strip() or f"{_MARK}空白"
        if title not in registered and len(title) <= 31:
            neutral_seen.add(title)
            outcome = impl.parse_workbook(_write_workbook(title, header, body), code)
            assert not outcome.errors, (
                f"{code}: 中性表名 {title!r} 被拒 ⇒ 身份判据变宽了，手工新建的表会被挡在门外："
                f"{list(outcome.errors)}"
            )

        # ② 已登记他表名 ⇒ 必拒，且错误点出两侧
        for other in codes:
            if other == code:
                continue
            foreign_seen += 1
            outcome = impl.parse_workbook(
                _write_workbook(_spec(other).sheet_name, header, body), code
            )
            assert outcome.errors, (
                f"{code}: 上传文件顶着 {other} 的表名 {_spec(other).sheet_name!r} 却被放行 ⇒ "
                f"A 表的导出文件会静默覆盖 B 表的数据"
            )
            assert not outcome.rows, f"{code}: 拒收了却仍解析出 {len(outcome.rows)} 行"

        # ③ 本张自己的表名 ⇒ 放行
        own = impl.parse_workbook(_write_workbook(spec.sheet_name, header, body), code)
        assert not own.errors, f"{code}: 自己的表名被拒：{list(own.errors)}"

    prop()
    assert len(neutral_seen) >= 20, f"中性表名维度只覆盖 {len(neutral_seen)} 种：{sorted(neutral_seen)[:5]}"
    assert foreign_seen >= 100 * (len(codes) - 1) // 2, f"他表名实例只有 {foreign_seen} 个"


# ═══════════════════════════════════════════════════════════════════════════
# 10. P4-4 —— 未登记 sheet 值 ⇒ 三态一律可读错误 + 库态零写入（R4.2 / R4.4）
# ═══════════════════════════════════════════════════════════════════════════


def test_p4_4_unregistered_sheet_value_writes_nothing() -> None:
    """∀ 不在该前缀白名单内的 ``sheet`` 值 × 三态端点：400 可读错误 + 整表快照不变。

    取值面两类：**别的已登记 X-3 码**（最危险 —— 若端点回退成「按本前缀处理」就会把 B 表
    的数据写进 A 表的键）与**合成码**。断言的可读性只落在「消息里出现了被拒的取值与本
    端点支持的取值」这两个**值**上，不锁具体文案。
    """
    hz = _hz()
    hz.reset()
    face = _face()
    codes = _codes()
    seen: dict[str, Any] = {"actions": set(), "cross": 0, "synthetic": 0}

    @given(
        code=st.sampled_from(sorted(codes)),
        action=st.sampled_from([impl._SUFFIX_TEMPLATE, impl._SUFFIX_DATA, impl._SUFFIX_IMPORT]),
        candidate=st.one_of(
            st.sampled_from(sorted(codes)),
            st.text(
                alphabet=string.ascii_uppercase + string.digits + "-", min_size=1, max_size=8
            ),
        ),
    )
    @_SETTINGS_DB
    def prop(code: str, action: str, candidate: str) -> None:
        allowed = _prefix_to_codes()[_spec(code).api_prefix]
        if candidate in allowed:
            return
        seen["actions"].add(action)
        if candidate in codes:
            seen["cross"] += 1
        else:
            seen["synthetic"] += 1

        header, body = _apply([[None] * len(face)], None)
        content = (
            _write_workbook(_spec(code).sheet_name, header, body)
            if action == impl._SUFFIX_IMPORT
            else None
        )
        before = hz.snapshot()
        reply = hz.call(code, action, sheet=candidate, content=content)
        after = hz.snapshot()

        assert before == after, (
            f"请求的 sheet={candidate!r} 不在 {_spec(code).api_prefix!r} 前缀白名单 "
            f"{sorted(allowed)} 内，但 `checklist_responses` 发生了变化：\n"
            f"{_snapshot_delta(before, after)}"
        )
        assert reply.status == 400, (
            f"{code} 的 {action} 端点收到未登记 sheet={candidate!r} 时返回 {reply.status}"
            f"（期望 400；禁回退成「导出/导入全部 sheet」）：{reply.body!r}"
        )
        detail = ""
        if isinstance(reply.body, Mapping):
            detail = str(reply.body.get("detail") or "")
        else:
            detail = str(reply.body)
        assert candidate in detail, (
            f"{code}/{action}: 错误消息没点出被拒的取值 {candidate!r}：{detail!r}"
        )
        for one in sorted(allowed):
            assert one in detail, (
                f"{code}/{action}: 错误消息没告诉用户本端点支持哪些 sheet（缺 {one!r}）：{detail!r}"
            )

    prop()
    assert seen["actions"] == {
        impl._SUFFIX_TEMPLATE,
        impl._SUFFIX_DATA,
        impl._SUFFIX_IMPORT,
    }, f"三态未全覆盖：{sorted(seen['actions'])}"
    assert seen["cross"] >= 10, (
        f"「别的已登记 X-3 码」这一最危险取值面只覆盖 {seen['cross']} 次 ⇒ 覆盖不足"
    )
    assert seen["synthetic"] >= 10, f"合成码取值面只覆盖 {seen['synthetic']} 次"


# ═══════════════════════════════════════════════════════════════════════════
# 11. P4-5 —— 正面对照：合法上传**必须**改变库态（否则上面的「不变」全是空转）
# ═══════════════════════════════════════════════════════════════════════════


def test_p4_5_accepted_upload_really_changes_the_database() -> None:
    """∀ 16 张 × ∀ 列序排列：表名与 sheet 都对得上时，整表快照**必须**变化。

    这条是 P4-3 / P4-4 的反空转对照：若写库通路根本没接通（依赖注入错、SQL 报错被吞、
    ``NOW()`` 替身失效……），那两条的「快照不变」就只是「什么都没发生」。

    只判「有没有写」，不判「写成了什么」—— 后者属 Property 1 / Property 2 的作业面。
    """
    hz = _hz()
    hz.reset()
    face = _face()
    width = len(face)
    seen: dict[str, Any] = {"sheets": set(), "perms": set()}

    @given(layout=_arb_layout(width), tag=st.integers(min_value=0, max_value=10**6))
    @_SETTINGS_DB
    def prop(layout: _Layout, tag: int) -> None:
        seen["perms"].add(layout.perm)
        # 每次迭代都换一个标记值 ⇒ 写入内容与库里既有值必然不同（不靠时间戳兜）
        row: list[Any] = [f"{_MARK}{tag}-{i}" for i in range(width)]
        row[impl.CATEGORY_COLUMN_INDEX] = sorted(impl.CATEGORY_TO_ENTRY_TYPE)[0]
        for code in _codes():
            spec = _spec(code)
            seen["sheets"].add(code)
            header, body = _apply([row], layout, noisy=())
            content = _write_workbook(spec.sheet_name, header, body)
            before = hz.snapshot()
            reply = hz.call(code, impl._SUFFIX_IMPORT, sheet=code, content=content)
            after = hz.snapshot()
            assert reply.status == 200 and isinstance(reply.body, Mapping), (
                f"{code}: 合法上传返回 {reply.status}：{reply.body!r}"
            )
            assert reply.body.get("ok") is True and reply.body.get("imported_count") == 1, (
                f"{code}: 合法上传未被接受：{reply.body!r}"
            )
            assert before != after, (
                f"{code}: 合法上传（表名与 sheet 都对得上、列序={layout.perm}）后 "
                "`checklist_responses` 一字未变 ⇒ 写库通路没接通，"
                "P4-3 / P4-4 的「快照不变」是空转而非结论"
            )

    prop()
    assert seen["sheets"] == set(_codes()), (
        f"只覆盖了 {len(seen['sheets'])} 张 sheet：{sorted(seen['sheets'])}"
    )
    assert len(seen["perms"]) >= 20, f"列序排列只覆盖 {len(seen['perms'])} 种"


def test_p4_5_reverse_selfcheck_probe_marker_absent_from_truth_sources() -> None:
    """反向自检：探针记号不出现在任何真源取值里（证明上面几条不是在跟自己的合成值绕圈）。"""
    for code in _codes():
        spec = _spec(code)
        assert _MARK not in spec.sheet_name, f"{code}: 真实 sheet_name 里出现探针记号"
        assert _MARK not in spec.item_id, f"{code}: 真实 item_id 里出现探针记号"
    for label in _face():
        assert _MARK not in label, f"真实列头 {label!r} 里出现探针记号"
    assert _MARK not in " ".join(impl.CATEGORY_TO_ENTRY_TYPE), "类别枚举里出现探针记号"


# ═══════════════════════════════════════════════════════════════════════════
# 12. 快照差异渲染（错误消息可读性）
# ═══════════════════════════════════════════════════════════════════════════

_KEY_IDX = (_SNAPSHOT_COLUMNS.index("wp_id"), _SNAPSHOT_COLUMNS.index("item_id"))


def _snapshot_delta(before: Sequence[Sequence[Any]], after: Sequence[Sequence[Any]]) -> str:
    """把两次快照的差异渲染成「新增 / 删除 / 改值」三段（最多各列 5 条）。"""

    def keyed(rows: Sequence[Sequence[Any]]) -> dict[tuple[Any, Any], Sequence[Any]]:
        return {(row[_KEY_IDX[0]], row[_KEY_IDX[1]]): row for row in rows}

    b, a = keyed(before), keyed(after)
    added = sorted(set(a) - set(b))
    removed = sorted(set(b) - set(a))
    changed = sorted(k for k in set(b) & set(a) if tuple(b[k]) != tuple(a[k]))
    parts = [f"  行数 {len(before)} → {len(after)}"]
    for label, keys in (("新增", added), ("删除", removed), ("改值", changed)):
        if not keys:
            continue
        parts.append(f"  {label} {len(keys)} 条：")
        for key in keys[:5]:
            if label == "改值":
                fields = [
                    f"{name}: {ov!r} → {nv!r}"
                    for name, ov, nv in zip(_SNAPSHOT_COLUMNS, b[key], a[key])
                    if ov != nv
                ]
                parts.append(f"    {key[1]} — " + "; ".join(fields))
            else:
                parts.append(f"    {key[1]}")
        if len(keys) > 5:
            parts.append(f"    …… 另 {len(keys) - 5} 条")
    return "\n".join(parts)


# 未使用的导入会被 lint 判死；`re` 只在下面这条兜底自检里用到。
_ITEM_ID_SANE = re.compile(r"^[\x20-\x7e\u4e00-\u9fff·—～、。（）]+$")


def test_anchor_seeded_item_ids_are_storable() -> None:
    """夹具自检：预置的族键都落在库列宽内、且形态可读（防夹具自己造出不可能存在的键）。"""
    limit = 64  # `checklist_responses.item_id` 的列宽（迁移 V089 定为 VARCHAR(64)）
    for code in _codes():
        for item_id, _column, _value in _seed_rows(code):
            assert len(item_id) <= limit, (
                f"{code}: 预置族键 {item_id!r} 长 {len(item_id)} 超出 item_id 列宽 {limit} ⇒ "
                "真实 PG 上会写失败，夹具与生产不同源"
            )
            assert _ITEM_ID_SANE.match(item_id), f"{code}: 预置族键形态异常 {item_id!r}"
