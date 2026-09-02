"""published representation → :class:`FrozenEntryDefinitions` 的**公共观测器**（Task 75）。

═══ 这个模块解决什么 ═══

Task 36 的 :class:`~app.services.workpaper_sync.excel_entry_gate.ExcelEntryDefinitionLoader`
是「一个 Excel entry 的完整已校验身份」的唯一加载器，但它的九个入参里有**四个是运行时
实测事实**：

* ``identity_inventory``      —— 三类 identity 载体的实测清册；
* ``observed_structure``      —— ``(sheet_key, table_key, stable_field_key, locator)`` 清册；
* ``observed_business_sheets``—— 业务 sheet 枚举；
* ``observed_dynamic_columns``—— 动态列的实测 ``(label, key)`` 对。

Tasks 40~43 交付时这四项**只有一个来源**：Task 17 candidate 的 equivalence 报告，也就是
**finalize 那一刻**。于是四个 pilot 的 ``resolve_published_frozen_definitions()`` 只能
``raise``，四处各登记一条 ``UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER``；连锁后果是四个
Excel pilot ``adapter_registered=False``、``build_production_registry()`` 只
``return WorkpaperSyncAdapterRegistry()``、manifest 186 条 entry 的 ``adapter_id`` 全 ``null``。

本模块把那四项在**请求时刻**现读出来，来源只有两处，两处都是**冻结**的：

1. **published representation artifact 的字节**（``representation.artifact_id`` /
   ``artifact_sha256`` 是 immutable representation row 上的冻结 FK + digest）；
2. **frozen definition bundle 的 typed child payload**（``definition_bundle_id`` /
   ``definition_bundle_sha256`` 同样冻结在 representation row 上），其中
   instrumentation child 的 canonical payload 提供了读 artifact 所需的全部锚点参数
   （Excel Table displayName、row UUID 列列标、隐藏 metadata sheet 名）。

═══ 三条禁令是怎么被结构性满足的（AC 2.10 / Property 7） ═══

* **不按 registry 当前 alias 或运行时 registry 快照重组 bundle**：本模块**没有** registry
  入参，也不 import ``adapters.registry``；bundle 只能经 ``representation.definition_bundle_id``
  这一个 FK 读到，digest 必须与 ``representation.definition_bundle_sha256`` 逐字相等。
  ``adapter_id`` 取 representation row 上冻结的那一个，不查 registry。
* **不读 candidate / 任何 non-current representation**：唯一读路径是 Task 14 的
  :class:`~app.services.workpaper_sync.resolution.CanonicalResolutionService`（它自己在
  第 ② 步 ``_assert_not_candidate_id`` 显式拒 candidate、在 artifact 层还有
  ``assert_canonical_resolvable`` 的 ``CandidateNotResolvableError``），本模块随后再加一道
  「必须等于 entry current pointer」的判据（:data:`ObservationStage.current_pointer`）。
  本模块**不 import** ``WorkpaperRepresentationUpgradeCandidate``。
* **重复观测逐字节相同**：全部输入都是冻结字节；输出携带 :attr:`PublishedObservation.observation_digest`
  （canonical digest），守卫据此断言同一 ``(content version, entry, representation generation)``
  重复观测、以及 registry alias 改名后的观测结果一字不变。

═══ 为什么这里没有一个 ``except Exception``（AC 5.12） ═══

缺 artifact、缺 bundle FK、digest 不符、typed slot 非法空值、identity 与 contract 不符
一律抛 :class:`PublishedIdentityObserverError` 子类，异常上带 ``error_code`` +
:attr:`PublishedIdentityObserverError.context`（stage、bundle/authority identity、typed
child inventory、correlation id）。**绝不**降级成 ``None`` / 空 identity / WARNING：
返回 ``None`` 会让上游把「观测失败」表现成「这个 entry 没有身份」，而后者会一路静默走到
「注册一个没有 identity binding 的 adapter」—— 本 spec 最贵的一类缺陷。

唯一的 ``except`` 是把**第三方**异常（``FingerprintError`` / ``OSError`` / ``zipfile``）
转成本模块的 ERROR 态并 ``raise ... from exc``，捕获类型逐个点名，不含 ``Exception``。
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping as AbcMapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncEntryState,
)
from app.services.excel_structure_fingerprint import (
    FingerprintError,
    WorkbookFingerprint,
    identity_inventory,
    structure_fingerprint,
)
from app.services.workpaper_sync.contracts import (
    SyncContract,
    declared_structure_inventory,
    load_contract,
    parse_a1_range,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.excel_entry_gate import (
    AdapterBuild,
    EntryIdentityInventory,
    ExcelEntryDefinitionLoader,
    FrozenEntryDefinitions,
    dynamic_column_stable_keys,
    parse_identity_inventory,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    DefinitionKind,
    DefinitionState,
    SyncDomainError,
    is_digest,
)
from app.services.workpaper_sync.resolution import (
    CanonicalResolution,
    CanonicalResolutionService,
    ResolutionIntent,
)

__all__ = [
    "ObservationStage",
    "PublishedIdentityObserverError",
    "RepresentationShapeError",
    "NonCurrentRepresentationError",
    "FrozenBundleLinkError",
    "FrozenChildUnusableError",
    "ArtifactUnreadableError",
    "ObservedIdentityDriftError",
    "PublishedObservation",
    "PublishedIdentityObserver",
    "observe_published_frozen_definitions",
    "observe_dynamic_columns",
    "observe_structure_inventory",
    "recompute_structure_hash",
    "resolve_project_scope",
    "STRUCTURE_HASH_SCHEMA_VERSION",
]

#: :class:`~app.services.workpaper_sync.excel_entry_gate.ExcelEntryFinalizeGate` 在
#: finalize 时刻用这个 schema 算 ``representation.structure_hash``。观测器**必须**用同一个
#: 字面量重算，否则「重算 == 冻结值」这条判据会恒假 ⇒ 观测器在任何真实 entry 上都不可用。
#: 两处必须一致由 :mod:`backend.tests.workpaper_sync.test_task75_published_identity_observer`
#: 的 ``TestStructureHashSchemaIsShared`` 双向锁死（从 gate 源码现取字面量比对）。
STRUCTURE_HASH_SCHEMA_VERSION: Final[str] = "excel-entry-structure:v1"

#: 只有 xlsx 走本观测器。Word 走 Task 77 的 ``word_entry_gate``（Word 无 sheet 无 cell，
#: 套用本模块的 sheet/table/cell 判据即恒真重言式）。
_SUPPORTED_DOCUMENT_TYPE: Final[str] = "xlsx"

_A1_CELL_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<col>[A-Z]{1,3})(?P<row>[1-9][0-9]*)$")


# ═══════════════════════════════════════════════════════════════════════════
# 1. stage 与异常
# ═══════════════════════════════════════════════════════════════════════════


class ObservationStage(str, Enum):
    """观测阶段。**封闭枚举**，顺序即执行顺序，也是 AC 5.12 要求的 ``stage`` 取值域。

    守卫按 ``tuple(ObservationStage)`` 断言每个 stage 至少有一条可达的 ERROR 判据 ——
    新增 stage 却不给它 ERROR 路径，等于开了一条静默通道。

    🔴 **没有** ``canonical_resolve`` / ``load_definitions`` 两项：canonical resolver 与
    Task 36 loader 的失败保留它们**自己的** error_code（``HistoricalResolutionError`` /
    ``CandidateNotResolvableError`` / ``BundleIntegrityError`` /
    ``PerEntryContractUnapprovedError`` / ``ContractDriftError`` …），本模块**不**把它们重新
    包一层 —— 包一层会把「到底是哪道门拦的」这条信息碾平，而 AC 5.12 要的正是可定位的
    error code。
    """

    representation_shape = "representation_shape"
    current_pointer = "current_pointer"
    frozen_bundle = "frozen_bundle"
    frozen_children = "frozen_children"
    published_artifact = "published_artifact"
    observe_workbook = "observe_workbook"
    frozen_digest_match = "frozen_digest_match"


class PublishedIdentityObserverError(SyncDomainError):
    """观测失败的基类。**永不**降级为 ``None`` / 空 identity / WARNING。

    ``context`` 逐条对应 AC 5.12 列举的诊断项：error code、stage、bundle/authority
    identity、bundle typed child inventory、correlation id。
    """

    error_code = "published_identity_observation_failed"

    def __init__(self, message: str, *, stage: ObservationStage, context: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.stage = stage
        self.context: Mapping[str, Any] = dict(context)

    def as_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "stage": self.stage.value,
            "message": str(self),
            **dict(self.context),
        }


class RepresentationShapeError(PublishedIdentityObserverError):
    error_code = "published_identity_representation_shape"


class NonCurrentRepresentationError(PublishedIdentityObserverError):
    error_code = "published_identity_non_current_representation"


class FrozenBundleLinkError(PublishedIdentityObserverError):
    error_code = "published_identity_frozen_bundle_link"


class FrozenChildUnusableError(PublishedIdentityObserverError):
    error_code = "published_identity_frozen_child_unusable"


class ArtifactUnreadableError(PublishedIdentityObserverError):
    error_code = "published_identity_artifact_unreadable"


class ObservedIdentityDriftError(PublishedIdentityObserverError):
    error_code = "published_identity_observed_drift"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PublishedObservation:
    """一次观测的完整结果。

    :attr:`observation_digest` 是「重复观测逐字节相同」这条判据的可比对投影：它只由冻结
    输入（bundle/artifact digest、representation generation）与现读事实决定，**不含**
    时间戳、不含 registry 状态、不含 correlation id。
    """

    entry_id: str
    representation_id: uuid.UUID
    content_version_id: uuid.UUID
    representation_generation: int
    definitions: FrozenEntryDefinitions
    #: ``adapters.excel.build_excel_adapter()`` 的第二个必需入参。
    #:
    #: 🔴 它**不在** :class:`FrozenEntryDefinitions` 上（Task 36 的那个 dataclass 没有
    #: ``identity_binding`` 字段）—— 四个 pilot 的 ``attach_pilot_adapters()`` 原先写的是
    #: ``binding=definitions.identity_binding``，那是一处**接线错误**：只因为
    #: ``resolve_published_frozen_definitions()`` 恒 ``raise``、这行永不可达，才一直没暴露
    #: （BP-17；fail-closed 掩盖接线错误与 fail-open 是同一类问题）。观测器把 binding 一起
    #: 产出并由 pilot 显式传入，于是「adapter 能不能真的造出来」在请求路径上可被证伪。
    identity_binding: Any
    observed_business_sheets: tuple[str, ...]
    observed_structure: tuple[tuple[str, str, str, str], ...]
    observed_dynamic_columns: Mapping[str, tuple[tuple[str, str], ...]]
    recomputed_structure_hash: str
    recomputed_identity_inventory_sha256: str

    @property
    def observation_digest(self) -> str:
        return canonical_digest(
            {
                "schema_version": "published-identity-observation:v1",
                "entry_id": self.entry_id,
                "content_version_id": str(self.content_version_id),
                "representation_generation": int(self.representation_generation),
                "definitions": self.definitions.as_dict(),
                "observed_business_sheets": list(self.observed_business_sheets),
                "observed_structure": [list(item) for item in self.observed_structure],
                "observed_dynamic_columns": {
                    key: [list(pair) for pair in value]
                    for key, value in sorted(self.observed_dynamic_columns.items())
                },
                "recomputed_structure_hash": self.recomputed_structure_hash,
                "recomputed_identity_inventory_sha256": (
                    self.recomputed_identity_inventory_sha256
                ),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "representation_id": str(self.representation_id),
            "content_version_id": str(self.content_version_id),
            "representation_generation": int(self.representation_generation),
            "observation_digest": self.observation_digest,
            "recomputed_structure_hash": self.recomputed_structure_hash,
            "recomputed_identity_inventory_sha256": (
                self.recomputed_identity_inventory_sha256
            ),
            "definitions": self.definitions.as_dict(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. 纯函数：从工作簿事实派生四项实测输入
# ═══════════════════════════════════════════════════════════════════════════


def _column_index(column: str) -> int:
    index = 0
    for char in column:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def _sheet_extent(fingerprint: WorkbookFingerprint, sheet: str) -> tuple[int, int]:
    """一张 sheet 的**物理**行/列外延 ``(max_row, max_col_index)``。

    口径刻意取「值 ∪ 公式 ∪ merge ∪ Table ref」的并集而**不是** ``cell_values`` 单独：
    ``structure_fingerprint`` 只收录 ``cell.value is not None`` 的格，所以合法为空的
    可编辑格（G7 的 ``C64:L73`` 逐格实测全空）在 ``cell_values`` 里根本不出现 ——
    用「格里有值」当存在性判据会让整张矩阵表恒判漂移。

    删列/删行会让并集收缩 ⇒ 落在外延之外的声明字段拿不到物理锚点 ⇒
    :func:`observe_structure_inventory` 少给一项 ⇒ ``assert_no_structure_drift`` 打红并
    点名首个漂移位置。这是本模块的物理性所在。
    """
    max_row = 0
    max_col = 0
    for coord in (
        *fingerprint.cell_values.get(sheet, {}),
        *fingerprint.formulas.get(sheet, {}),
        *fingerprint.cell_styles.get(sheet, {}),
    ):
        match = _A1_CELL_RE.match(coord)
        if match is None:
            continue
        max_row = max(max_row, int(match.group("row")))
        max_col = max(max_col, _column_index(match.group("col")))
    for rng in fingerprint.merges.get(sheet, []):
        for part in str(rng).split(":"):
            match = _A1_CELL_RE.match(part.strip())
            if match is None:
                continue
            max_row = max(max_row, int(match.group("row")))
            max_col = max(max_col, _column_index(match.group("col")))
    for table in fingerprint.tables:
        if table.get("sheet") != sheet:
            continue
        for part in str(table.get("ref") or "").split(":"):
            match = _A1_CELL_RE.match(part.strip())
            if match is None:
                continue
            max_row = max(max_row, int(match.group("row")))
            max_col = max(max_col, _column_index(match.group("col")))
    return max_row, max_col


def _cell_coordinates_for(field: Any, *, row_uuid_rows: Sequence[int]) -> tuple[str, int] | None:
    """一个声明字段的**物理**坐标 ``(列标, 行号)``；拿不到物理行时返回 ``None``。

    * ``row_from == "row_identity"`` 的动态行字段：物理行取实测 row UUID 的**首行**。
      identity 列被删干净时 ``row_uuid_rows`` 为空 ⇒ 返回 ``None`` ⇒ 该字段进不了实测
      清册 ⇒ 漂移打红（对应 Requirement 6.15 的「用户删除 identity 列」形态）。
    * 其余（静态行）字段：物理行取 ``static_row``；没有 ``static_row`` 时按
      ``row_from`` 的数字形态解析，两者都拿不到即 ``None``。
    """
    cell = getattr(field, "cell", None)
    if cell is None:
        return None
    column = str(getattr(cell, "column", "") or "").strip().upper()
    if not column or _column_index(column) <= 0:
        return None
    row_from = str(getattr(cell, "row_from", "") or "").strip()
    if row_from == "row_identity":
        if not row_uuid_rows:
            return None
        return column, min(row_uuid_rows)
    static_row = getattr(cell, "static_row", None)
    if static_row is not None:
        return column, int(static_row)
    if row_from.isdigit():
        return column, int(row_from)
    return None


def observe_structure_inventory(
    *,
    contract: SyncContract,
    fingerprint: WorkbookFingerprint,
    physical_sheet_by_key: Mapping[str, str],
    row_uuid_rows: Sequence[int],
) -> tuple[tuple[str, str, str, str], ...]:
    """按契约声明逐字段**核对物理锚点是否真在工作簿里**，产出实测结构清册。

    元组形态与 :func:`~app.services.workpaper_sync.contracts.declared_structure_inventory`
    完全一致（``(sheet_key, table_key, stable_field_key, locator)``），因此工作簿未漂移
    时两者逐项相等、``assert_no_structure_drift`` 通过；任一字段的物理锚点消失（列被删、
    行被删、受管 sheet 的 Table 关联断开、identity 列被删）时本函数**少给或给出不同的**
    那一项，漂移判据据此点名首个位置。

    🔴 这里**不是**「把声明抄一遍」：每一项都要过 :func:`_sheet_extent` 的物理外延与
    :func:`_cell_coordinates_for` 的物理行解析；``physical_sheet_by_key`` 也不是契约里的
    ``excel_name``，而是由 Excel Table 关联反解出来的真实 sheet 名（sheet 改名不改身份）。
    """
    rows: list[tuple[str, str, str, str]] = []
    extents: dict[str, tuple[int, int]] = {}
    for sheet in contract.sheets:
        physical = physical_sheet_by_key.get(sheet.sheet_key)
        if not physical:
            continue
        if physical not in extents:
            extents[physical] = _sheet_extent(fingerprint, physical)
        max_row, max_col = extents[physical]
        for table in sheet.tables:
            for spec in table.fields:
                coordinate = _cell_coordinates_for(spec, row_uuid_rows=row_uuid_rows)
                if coordinate is None:
                    continue
                column, row = coordinate
                if row > max_row or _column_index(column) > max_col:
                    continue
                cell = spec.cell
                locator = f"{cell.column}:{cell.row_from}" + (
                    f":{cell.static_row}" if cell.static_row is not None else ""
                )
                rows.append((sheet.sheet_key, table.table_key, spec.stable_field_key, locator))
    return tuple(sorted(rows))


def observe_dynamic_column_bindings(
    *, contract: SyncContract, fingerprint: WorkbookFingerprint,
    physical_sheet_by_key: Mapping[str, str],
) -> dict[str, dict[str, str]]:
    """``table_key`` → (``{slot}_{seq}`` → Excel 列标) 的**实测**绑定。

    与 :func:`observe_dynamic_columns` 共用同一段物理列跨度推导（``_dynamic_spans``），
    因此「键数与列数不等」或「两个键绑同一列」在构造上不可能 ——
    ``excel_materialize.assert_dynamic_column_binding_usable`` 还会独立复核一遍。
    """
    out: dict[str, dict[str, str]] = {}
    for table_key, span, _labels, keys in _dynamic_spans(
        contract=contract, fingerprint=fingerprint, physical_sheet_by_key=physical_sheet_by_key
    ):
        out[table_key] = {key: _letters(index) for index, key in zip(span, keys)}
    return out


def _dynamic_spans(
    *, contract: SyncContract, fingerprint: WorkbookFingerprint,
    physical_sheet_by_key: Mapping[str, str],
) -> list[tuple[str, list[int], list[str], tuple[str, ...]]]:
    """每张声明了 ``dynamic_columns`` 的表的 ``(table_key, 物理列序列, labels, keys)``。

    **唯一**推导处：label 与 key 与列标三者由同一个 span 派生，抄第二份就会出现
    「label 数与 key 数对不上」这类只在运行时才暴露的错位。
    """
    spans: list[tuple[str, list[int], list[str], tuple[str, ...]]] = []
    for sheet in contract.sheets:
        physical = physical_sheet_by_key.get(sheet.sheet_key)
        for table in sheet.tables:
            if table.dynamic_columns is None:
                continue
            if not physical:
                spans.append((table.table_key, [], [], ()))
                continue
            a1 = str(table.dynamic_columns.source_ref or "").rsplit("!", 1)[-1].strip()
            col_from, row_from, col_to, _row_to = parse_a1_range(
                a1,
                location=(
                    f"contract[{contract.contract_id}].{table.table_key}.dynamic_columns"
                ),
            )
            low, high = sorted((_column_index(col_from), _column_index(col_to)))
            _max_row, max_col = _sheet_extent(fingerprint, physical)
            span = list(range(low, min(high, max_col) + 1))
            merged = _merged_anchor_values(fingerprint, physical)
            labels: list[str] = []
            for index in span:
                coord = f"{_letters(index)}{row_from}"
                raw = fingerprint.cell_values.get(physical, {}).get(coord)
                if raw is None:
                    raw = merged.get(coord)
                labels.append("" if raw is None else str(raw))
            keys = dynamic_column_stable_keys(slot=table.table_key, count=len(span))
            spans.append((table.table_key, span, labels, keys))
    return spans


def observe_dynamic_columns(
    *, contract: SyncContract, fingerprint: WorkbookFingerprint,
    physical_sheet_by_key: Mapping[str, str],
) -> dict[str, tuple[tuple[str, str], ...]]:
    """契约声明 ``dynamic_columns`` 的每张表的实测 ``(label, key)`` 对。

    * **label** 从工作簿里现读：``dynamic_columns.source_ref`` 的 A1 区域给出列跨度与
      label 行，label 取该行各列的物理值（含 merge 锚点值），空格给空串 —— label 是**可改**
      的，正因如此它只出现在 ``observed`` 侧；
    * **key** 一律委派 Task 36 的 :func:`dynamic_column_stable_keys`（两参 ``(slot, count)``，
      签名里拿不到 label），``count`` 由**物理列跨度**决定，不写死列数。

    于是「改名/重排」不动 key、「删列」使 count 收缩并被
    :func:`~app.services.workpaper_sync.excel_entry_gate.assert_dynamic_columns_label_independent`
    与结构漂移双向抓住（Property 22）。
    """
    return {
        table_key: tuple(zip(labels, keys))
        for table_key, _span, labels, keys in _dynamic_spans(
            contract=contract,
            fingerprint=fingerprint,
            physical_sheet_by_key=physical_sheet_by_key,
        )
    }


def _letters(index: int) -> str:
    out = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def _merged_anchor_values(
    fingerprint: WorkbookFingerprint, sheet: str
) -> dict[str, str]:
    """把 merge 区域左上角的值铺到区域内每个坐标上。

    源模板的横向分组表头就是 merge 出来的（G7 行 62 的 5 个占位槽），openpyxl 只在左上角
    留值 ⇒ 不铺开的话第 2..N 列的 label 全读成空，"改名"就观测不到了。
    """
    values = fingerprint.cell_values.get(sheet, {})
    spread: dict[str, str] = {}
    for rng in fingerprint.merges.get(sheet, []):
        parts = str(rng).split(":")
        if len(parts) != 2:
            continue
        first, last = (_A1_CELL_RE.match(p.strip()) for p in parts)
        if first is None or last is None:
            continue
        anchor = f"{first.group('col')}{first.group('row')}"
        if anchor not in values:
            continue
        c1, c2 = sorted((_column_index(first.group("col")), _column_index(last.group("col"))))
        r1, r2 = sorted((int(first.group("row")), int(last.group("row"))))
        for col in range(c1, c2 + 1):
            for row in range(r1, r2 + 1):
                spread[f"{_letters(col)}{row}"] = values[anchor]
    return spread


# ═══════════════════════════════════════════════════════════════════════════
# 4. 观测器
# ═══════════════════════════════════════════════════════════════════════════


class PublishedIdentityObserver:
    """请求路径上的 ``published representation → FrozenEntryDefinitions`` 观测器。

    只读：不写任何行、不发布任何 definition、不切 pointer、不碰 candidate 表。构造时
    **不接受 registry**（AC 2.10 的核心禁令在构造签名上就被满足）。
    """

    def __init__(
        self, *, session: AsyncSession, resolution: CanonicalResolutionService
    ) -> None:
        self._session = session
        self._resolution = resolution
        self._loader = ExcelEntryDefinitionLoader(session=session, resolution=resolution)

    # ─────────────────────────────────────────────────────────────────

    async def observe(
        self,
        *,
        representation: Any,
        project_id: uuid.UUID,
        intent: ResolutionIntent | str = ResolutionIntent.config,
        correlation_id: str | None = None,
    ) -> PublishedObservation:
        """现读并校验；任一判据不过即抛，不返回半成品。"""
        cid = correlation_id or f"observe-{uuid.uuid4().hex[:12]}"
        rep = self._assert_representation_shape(representation, correlation_id=cid)
        entry_id = str(rep["entry_id"])

        resolution = await self._resolve(
            rep=rep, project_id=project_id, intent=intent, entry_id=entry_id, correlation_id=cid
        )
        await self._assert_is_current(rep=rep, entry_id=entry_id, correlation_id=cid)
        self._assert_frozen_bundle_link(
            rep=rep, resolution=resolution, entry_id=entry_id, correlation_id=cid
        )
        contract_semantic_version, instrumentation = await self._load_frozen_children(
            resolution=resolution, entry_id=entry_id, correlation_id=cid
        )
        data = self._read_published_bytes(
            resolution=resolution, entry_id=entry_id, correlation_id=cid
        )
        adapter_build = AdapterBuild(
            adapter_id=str(rep["adapter_id"]),
            adapter_build_digest=str(rep["adapter_build_digest"]),
            document_type=str(rep["document_type"]),
            contract_version=contract_semantic_version,
        )
        contract = self._load_frozen_contract(
            adapter_id=adapter_build.adapter_id,
            resolution=resolution,
            entry_id=entry_id,
            correlation_id=cid,
        )
        observed = self._observe_workbook(
            data=data,
            contract=contract,
            instrumentation=instrumentation,
            resolution=resolution,
            entry_id=entry_id,
            correlation_id=cid,
        )
        self._assert_matches_frozen_digests(
            rep=rep,
            contract=contract,
            observed=observed,
            resolution=resolution,
            entry_id=entry_id,
            correlation_id=cid,
        )
        definitions = await self._load_definitions(
            resolution=resolution,
            adapter_build=adapter_build,
            observed=observed,
            entry_id=entry_id,
            correlation_id=cid,
        )
        return PublishedObservation(
            entry_id=entry_id,
            representation_id=resolution.representation_id,
            content_version_id=resolution.content_version_id,
            representation_generation=int(resolution.representation_generation),
            definitions=definitions,
            identity_binding=self._build_identity_binding(
                contract=contract,
                anchors=observed["anchors"],
                dynamic_bindings=observed["dynamic_bindings"],
                entry_id=entry_id,
                resolution=resolution,
                correlation_id=cid,
            ),
            observed_business_sheets=observed["business_sheets"],
            observed_structure=observed["structure"],
            observed_dynamic_columns=observed["dynamic_columns"],
            recomputed_structure_hash=observed["structure_hash"],
            recomputed_identity_inventory_sha256=observed["identity_inventory_sha256"],
        )

    # ─── stage 1 ─────────────────────────────────────────────────────

    def _assert_representation_shape(
        self, representation: Any, *, correlation_id: str
    ) -> dict[str, Any]:
        """representation row 的冻结身份必须完整合法。**缺一项即 ERROR，绝不补默认值。**"""
        base = {"correlation_id": correlation_id, "stage": ObservationStage.representation_shape.value}
        if representation is None:
            raise RepresentationShapeError(
                "观测器收到 representation=None —— 缺 published representation 时不得"
                "「按 current pointer 现查」也不得返回空 identity",
                stage=ObservationStage.representation_shape,
                context=base,
            )
        required = (
            "id", "wp_id", "entry_id", "content_version_id", "generation", "document_type",
            "artifact_id", "artifact_sha256", "definition_bundle_id", "definition_bundle_sha256",
            "authority_model_definition_id", "authority_model_definition_sha256",
            "adapter_id", "adapter_build_digest", "structure_hash", "identity_inventory_sha256",
        )
        out: dict[str, Any] = {}
        for name in required:
            if not hasattr(representation, name):
                raise RepresentationShapeError(
                    f"representation 缺字段 {name!r} —— 冻结身份不完整时不得继续观测",
                    stage=ObservationStage.representation_shape,
                    context={**base, "missing_field": name},
                )
            out[name] = getattr(representation, name)
        for name in ("id", "wp_id", "content_version_id", "artifact_id", "definition_bundle_id"):
            if out[name] is None:
                raise RepresentationShapeError(
                    f"representation.{name} 为 None —— 冻结 FK 不得为空",
                    stage=ObservationStage.representation_shape,
                    context={**base, "null_field": name},
                )
        for name in (
            "artifact_sha256", "definition_bundle_sha256", "authority_model_definition_sha256",
            "adapter_build_digest", "structure_hash", "identity_inventory_sha256",
        ):
            if not is_digest(out[name]):
                raise RepresentationShapeError(
                    f"representation.{name} 不是合法非全零 64 位 digest: {out[name]!r}",
                    stage=ObservationStage.representation_shape,
                    context={**base, "invalid_digest_field": name},
                )
        if not str(out["adapter_id"] or "").strip():
            raise RepresentationShapeError(
                "representation.adapter_id 为空 —— adapter 身份必须冻结在 representation 上，"
                "不得在请求时按 registry 当前 alias 现查（AC 2.10）",
                stage=ObservationStage.representation_shape,
                context=base,
            )
        if str(out["document_type"] or "").strip() != _SUPPORTED_DOCUMENT_TYPE:
            raise RepresentationShapeError(
                f"本观测器只处理 document_type={_SUPPORTED_DOCUMENT_TYPE!r}，实得 "
                f"{out['document_type']!r} —— Word 走 Task 77 的 tagged-SDT 门，"
                "sheet/cell 判据套到 Word 上是恒真重言式",
                stage=ObservationStage.representation_shape,
                context={**base, "document_type": str(out["document_type"])},
            )
        if int(out["generation"] or 0) < 1:
            raise RepresentationShapeError(
                f"representation.generation={out['generation']!r} 非法（必须 >= 1）",
                stage=ObservationStage.representation_shape,
                context=base,
            )
        return out

    # ─── stage 2 ─────────────────────────────────────────────────────

    async def _resolve(
        self, *, rep: Mapping[str, Any], project_id: uuid.UUID,
        intent: ResolutionIntent | str, entry_id: str, correlation_id: str,
    ) -> CanonicalResolution:
        """唯一读路径：Task 14 canonical resolver，显式给 frozen ``representation_id``。

        给 frozen id 而不是让它按 current pointer 现查，是为了让 candidate 拒绝
        （``_assert_not_candidate_id``）真的跑到 —— 那条门只在显式给 id 时执行。
        """
        return await self._resolution.resolve(
            intent=intent,
            project_id=project_id,
            wp_id=rep["wp_id"],
            entry_id=entry_id,
            representation_id=rep["id"],
            expected_content_version_id=rep["content_version_id"],
            expected_document_type=str(rep["document_type"]),
        )

    # ─── stage 3 ─────────────────────────────────────────────────────

    async def _assert_is_current(
        self, *, rep: Mapping[str, Any], entry_id: str, correlation_id: str
    ) -> None:
        """必须等于 entry 的 current pointer（拒 non-current published generation）。"""
        pointer = (
            await self._session.execute(
                sa.select(WorkpaperSyncEntryState.current_representation_id).where(
                    WorkpaperSyncEntryState.wp_id == rep["wp_id"],
                    WorkpaperSyncEntryState.entry_id == entry_id,
                )
            )
        ).scalars().first()
        base = {
            "correlation_id": correlation_id,
            "entry_id": entry_id,
            "representation_id": str(rep["id"]),
            "current_representation_id": None if pointer is None else str(pointer),
        }
        if pointer is None:
            raise NonCurrentRepresentationError(
                f"entry {entry_id} 没有 current representation pointer —— 观测器不得为"
                "「还没 finalize」的 entry 编出身份",
                stage=ObservationStage.current_pointer,
                context=base,
            )
        if pointer != rep["id"]:
            raise NonCurrentRepresentationError(
                f"entry {entry_id} 的 current pointer 是 {pointer}，观测目标 {rep['id']} 是"
                "**non-current** generation —— 请求路径只观测 current published "
                "representation（AC 6.18 / Property 67）",
                stage=ObservationStage.current_pointer,
                context=base,
            )

    # ─── stage 4 ─────────────────────────────────────────────────────

    def _assert_frozen_bundle_link(
        self, *, rep: Mapping[str, Any], resolution: CanonicalResolution,
        entry_id: str, correlation_id: str,
    ) -> None:
        """bundle/authority/adapter 三条冻结链必须与 resolver 解析出的快照逐项相等。"""
        bundle = resolution.bundle
        base = self._identity_context(
            resolution=resolution, entry_id=entry_id, correlation_id=correlation_id
        )
        # 🔴 这里**只**留一条判据。首版还写了四条（bundle_id / bundle digest /
        #    authority child id / adapter_id 各比一次），2026-08-31 的变异检验把它们判 GREEN ——
        #    因为它们全都恒真或已有单一真源：
        #
        #    * `bundle_id`：`load_bundle_snapshot(rep.definition_bundle_id)` 就是按它读的 ⇒ 恒等；
        #    * bundle digest / authority child id：`CanonicalResolutionService.resolve` 的第 ⑤ 步
        #      已经比过（`BundleIntegrityError`），那里是单一真源；
        #    * `adapter_id`：`resolution.adapter_id` 直接取自同一个 rep ⇒ 恒等。
        #
        #    抄一份的后果不是「更安全」，而是任一侧被短路都不改变行为 ⇒ 变异恒 GREEN、
        #    读者以为判据比实际强。只有下面这条不在别处：**标准 Excel 通道的 authority model
        #    必须是 `projection_contract`**（custom/opaque 走 Task 65），resolver 不管这件事。
        if bundle.authority_model is not AuthorityModel.projection_contract:
            raise FrozenBundleLinkError(
                f"标准 Excel entry 的 authority model 必须是 projection_contract，实得 "
                f"{bundle.authority_model.value} —— custom/opaque 走 Task 65",
                stage=ObservationStage.frozen_bundle,
                context=base,
            )

    # ─── stage 5 ─────────────────────────────────────────────────────

    async def _load_frozen_children(
        self, *, resolution: CanonicalResolution, entry_id: str, correlation_id: str
    ) -> tuple[str, Mapping[str, Any]]:
        """读 contract / instrumentation 两个 typed child 的冻结 row 与 payload。

        返回 ``(contract semantic_version, instrumentation canonical payload)``。
        ``semantic_version`` 取**冻结的 definition row**（不是磁盘契约文件），于是
        ``assert_adapter_build_usable`` 的「adapter contract_version ↔ 磁盘契约
        semantic_version」比对是**跨来源**的，不是自我比对。
        """
        base = self._identity_context(
            resolution=resolution, entry_id=entry_id, correlation_id=correlation_id
        )
        contract_child = await self._load_child_row(
            slot=BundleSlot.contract, resolution=resolution, context=base
        )
        if contract_child.kind != DefinitionKind.contract.value:
            raise FrozenChildUnusableError(
                f"contract slot 指向 kind={contract_child.kind!r} 的 definition —— "
                "必须是 per-entry contract",
                stage=ObservationStage.frozen_children,
                context={**base, "slot": BundleSlot.contract.value},
            )
        if contract_child.state != DefinitionState.approved.value:
            raise FrozenChildUnusableError(
                f"per-entry contract definition {contract_child.id} 的 state="
                f"{contract_child.state!r} —— generator 候选永不放行",
                stage=ObservationStage.frozen_children,
                context={**base, "slot": BundleSlot.contract.value},
            )
        semantic_version = str(contract_child.semantic_version or "").strip()
        if not semantic_version:
            raise FrozenChildUnusableError(
                f"per-entry contract definition {contract_child.id} 的 semantic_version 为空",
                stage=ObservationStage.frozen_children,
                context={**base, "slot": BundleSlot.contract.value},
            )

        instrumentation_child = await self._load_child_row(
            slot=BundleSlot.instrumentation, resolution=resolution, context=base
        )
        if instrumentation_child.kind != DefinitionKind.instrumentation.value:
            raise FrozenChildUnusableError(
                f"instrumentation slot 指向 kind={instrumentation_child.kind!r} 的 definition",
                stage=ObservationStage.frozen_children,
                context={**base, "slot": BundleSlot.instrumentation.value},
            )
        if instrumentation_child.state != DefinitionState.approved.value:
            raise FrozenChildUnusableError(
                f"instrumentation definition {instrumentation_child.id} 的 state="
                f"{instrumentation_child.state!r} —— 未 approved 的 instrumentation 不得"
                "用于请求路径反读",
                stage=ObservationStage.frozen_children,
                context={**base, "slot": BundleSlot.instrumentation.value},
            )
        payload = await self._read_definition_payload(
            child=instrumentation_child, resolution=resolution, context=base
        )
        return semantic_version, payload

    async def _load_child_row(
        self, *, slot: BundleSlot, resolution: CanonicalResolution, context: Mapping[str, Any]
    ) -> WorkpaperSyncDefinitionArtifact:
        """按 frozen slot ref 读 child definition row（无 alias、无 entry 反查）。"""
        spec = resolution.bundle.slots.get(slot)
        if spec is None or not spec.is_definition:
            raise FrozenChildUnusableError(
                f"frozen bundle 的 {slot.value} slot 不是 definition child（"
                f"slot_type={None if spec is None else spec.slot_type!r}）—— typed null "
                "marker 不得冒充 approved child",
                stage=ObservationStage.frozen_children,
                context={**dict(context), "slot": slot.value},
            )
        child_id = uuid.UUID(spec.slot_ref.split(":", 1)[1])
        row = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id == child_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise FrozenChildUnusableError(
                f"frozen bundle 的 {slot.value} slot 指向不存在的 definition {child_id}",
                stage=ObservationStage.frozen_children,
                context={**dict(context), "slot": slot.value},
            )
        if str(row.sha256 or "").strip() != str(spec.slot_digest or "").strip():
            raise FrozenChildUnusableError(
                f"{slot.value} child {child_id} 的 sha256 {row.sha256!r} 与 frozen slot digest "
                f"{spec.slot_digest!r} 不一致",
                stage=ObservationStage.frozen_children,
                context={**dict(context), "slot": slot.value},
            )
        return row

    async def _read_definition_payload(
        self, *, child: WorkpaperSyncDefinitionArtifact, resolution: CanonicalResolution,
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """读 child definition 的 canonical payload 字节并按 digest 复核。"""
        ctx = {**dict(context), "definition_id": str(child.id)}
        path = await self._resolve_definition_blob(child=child, context=ctx)
        raw = self._read_bytes(path, stage=ObservationStage.frozen_children, context=ctx)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FrozenChildUnusableError(
                f"definition {child.id} 的 canonical payload 不是合法 UTF-8 JSON: {exc}",
                stage=ObservationStage.frozen_children,
                context=ctx,
            ) from exc
        if not isinstance(payload, AbcMapping):
            raise FrozenChildUnusableError(
                f"definition {child.id} 的 canonical payload 根不是对象，实得 "
                f"{type(payload).__name__}",
                stage=ObservationStage.frozen_children,
                context=ctx,
            )
        if canonical_digest(payload) != str(child.sha256).strip():
            raise FrozenChildUnusableError(
                f"definition {child.id} 的 payload canonical digest 与 row 上冻结的 "
                f"{child.sha256!r} 不一致 —— 已 approved 的 definition 不可被改写",
                stage=ObservationStage.frozen_children,
                context=ctx,
            )
        return payload

    async def _resolve_definition_blob(
        self, *, child: WorkpaperSyncDefinitionArtifact, context: Mapping[str, Any]
    ) -> Path:
        """definition blob 的物理路径：按冻结 FK 读 artifact row，再交仓储解析相对路径。

        **不自拼** ``definition_store/{kind}/…`` 布局：那是 ``ArtifactStorageLayout`` 的
        领地，抄一份就是第二真源（布局一改，观测器会安静地读到不存在的路径）。
        """
        from app.models.workpaper_sync_models import WorkpaperArtifact

        artifacts = getattr(self._resolution, "_artifacts", None)
        if artifacts is None:
            raise FrozenChildUnusableError(
                "resolution service 未装配 artifact 仓储 —— 观测器不得自拼 definition "
                "store 布局（那是第二真源）",
                stage=ObservationStage.frozen_children,
                context=dict(context),
            )
        row = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(
                    WorkpaperArtifact.id == child.blob_artifact_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise FrozenChildUnusableError(
                f"definition {child.id} 的 blob artifact {child.blob_artifact_id} 不存在",
                stage=ObservationStage.frozen_children,
                context=dict(context),
            )
        return artifacts.resolve_relative_path(str(row.relative_path))

    # ─── stage 6 ─────────────────────────────────────────────────────

    def _read_published_bytes(
        self, *, resolution: CanonicalResolution, entry_id: str, correlation_id: str
    ) -> bytes:
        """读 published representation 的 artifact 字节并按冻结 digest 复核。"""
        import hashlib

        ctx = self._identity_context(
            resolution=resolution, entry_id=entry_id, correlation_id=correlation_id
        )
        data = self._read_bytes(
            resolution.artifact_path, stage=ObservationStage.published_artifact, context=ctx
        )
        observed = hashlib.sha256(data).hexdigest()
        if observed != str(resolution.artifact_sha256).strip():
            raise ArtifactUnreadableError(
                f"published artifact 实测 digest {observed} 与冻结的 "
                f"{resolution.artifact_sha256} 不一致 —— immutable representation 的字节"
                "被改写，不得按旧身份继续解析",
                stage=ObservationStage.published_artifact,
                context={**ctx, "observed_artifact_sha256": observed},
            )
        return data

    def _read_bytes(
        self, path: Path, *, stage: ObservationStage, context: Mapping[str, Any]
    ) -> bytes:
        try:
            return Path(path).read_bytes()
        except OSError as exc:
            raise ArtifactUnreadableError(
                f"artifact 读不到: {path} ({type(exc).__name__}: {exc})",
                stage=stage,
                context={**dict(context), "path": str(path)},
            ) from exc

    # ─── stage 7 ─────────────────────────────────────────────────────

    def _load_frozen_contract(
        self, *, adapter_id: str, resolution: CanonicalResolution, entry_id: str,
        correlation_id: str,
    ) -> SyncContract:
        """按 representation 冻结的 ``adapter_id`` 加载磁盘 per-entry contract。

        ``adapter_id`` 是 immutable representation row 上的冻结值（不是 registry alias），
        所以这条读路径不受 registry 改名影响。契约与 frozen bundle 的 digest 锁由
        ``ExcelEntryDefinitionLoader.load()`` 里的 ``assert_contract_identity_frozen``
        单一真源承担，本模块**不重写**那条比对。
        """
        from app.services.workpaper_sync.contracts import ContractError

        try:
            return load_contract(adapter_id)
        except ContractError as exc:
            raise FrozenChildUnusableError(
                f"adapter {adapter_id!r} 的磁盘 per-entry contract 不可用: {exc}",
                stage=ObservationStage.observe_workbook,
                context=self._identity_context(
                    resolution=resolution, entry_id=entry_id, correlation_id=correlation_id
                ),
            ) from exc

    def _observe_workbook(
        self, *, data: bytes, contract: SyncContract, instrumentation: Mapping[str, Any],
        resolution: CanonicalResolution, entry_id: str, correlation_id: str,
    ) -> dict[str, Any]:
        """从 artifact 字节现读四项实测事实 + 两个重算 digest。"""
        ctx = self._identity_context(
            resolution=resolution, entry_id=entry_id, correlation_id=correlation_id
        )
        anchors = _frozen_anchors(instrumentation)
        if anchors is None:
            raise FrozenChildUnusableError(
                "frozen instrumentation payload 缺 managed_sheets/table/uuid 列锚点 —— "
                "请求时刻的反读参数只能来自冻结 instrumentation，不得按 sheet 展示名猜",
                stage=ObservationStage.observe_workbook,
                context=ctx,
            )
        try:
            fingerprint = structure_fingerprint(data)
            inventory_raw = identity_inventory(
                data,
                expected_table=anchors["table_name"],
                uuid_column_letter=anchors["uuid_column_letter"],
                metadata_sheet=anchors["metadata_sheet"],
            )
        except FingerprintError as exc:
            raise ArtifactUnreadableError(
                f"published artifact 结构采集失败: {exc}",
                stage=ObservationStage.observe_workbook,
                context=ctx,
            ) from exc
        if fingerprint.errors:
            raise ArtifactUnreadableError(
                f"published artifact 结构采集有非致命错误 {fingerprint.errors[:3]} —— "
                "采集不完整时不得按半份事实组装 adapter",
                stage=ObservationStage.observe_workbook,
                context={**ctx, "fingerprint_errors": list(fingerprint.errors)},
            )
        table = inventory_raw.get("excel_table") or {}
        physical_sheet = table.get("table_sheet")
        if not table.get("present") or not physical_sheet:
            raise ObservedIdentityDriftError(
                f"published artifact 里找不到冻结 instrumentation 声明的 Excel Table "
                f"{anchors['table_name']!r} —— 受管 sheet 的唯一运行态锚点"
                "（`excel_table_sheet_association`）已断，不得回退按 sheet 展示名定位",
                stage=ObservationStage.observe_workbook,
                context={**ctx, "expected_table": anchors["table_name"]},
            )
        physical_sheet_by_key = {anchors["sheet_key"]: str(physical_sheet)}
        inventory = parse_identity_inventory(inventory_raw)
        row_uuid_rows = sorted(int(row) for row in inventory.row_uuids if str(row).isdigit())
        structure = observe_structure_inventory(
            contract=contract,
            fingerprint=fingerprint,
            physical_sheet_by_key=physical_sheet_by_key,
            row_uuid_rows=row_uuid_rows,
        )
        dynamic_columns = observe_dynamic_columns(
            contract=contract,
            fingerprint=fingerprint,
            physical_sheet_by_key=physical_sheet_by_key,
        )
        return {
            "fingerprint": fingerprint,
            "anchors": anchors,
            "identity_inventory": inventory,
            "business_sheets": tuple(fingerprint.business_sheet_names()),
            "structure": structure,
            "dynamic_columns": dynamic_columns,
            "dynamic_bindings": observe_dynamic_column_bindings(
                contract=contract,
                fingerprint=fingerprint,
                physical_sheet_by_key=physical_sheet_by_key,
            ),
            "structure_hash": recompute_structure_hash(
                contract=contract, observed_structure=structure
            ),
            "identity_inventory_sha256": canonical_digest(inventory.inventory_digest_input),
        }

    def _build_identity_binding(
        self, *, contract: SyncContract, anchors: Mapping[str, str],
        dynamic_bindings: Mapping[str, Mapping[str, str]], entry_id: str,
        resolution: CanonicalResolution, correlation_id: str,
    ) -> Any:
        """组 ``ExcelIdentityBinding``：Table 名/UUID 列取**冻结 instrumentation**，
        ``table_key`` 取契约里那张**唯一**声明了 ``row_identity`` 的受管表。

        ``row_identity`` 表不唯一（0 张或 ≥2 张）时 fail closed 并点名 —— 「随手挑第一张」
        会让 UUID 列绑到另一张表上，受管格整体错位而没有任何报错。
        """
        from app.services.workpaper_sync.excel_extract import ExcelIdentityBinding

        row_tables = [
            (sheet.sheet_key, table.table_key)
            for sheet in contract.sheets
            for table in sheet.tables
            if table.row_identity is not None
        ]
        ctx = self._identity_context(
            resolution=resolution, entry_id=entry_id, correlation_id=correlation_id
        )
        if len(row_tables) != 1:
            raise FrozenChildUnusableError(
                f"契约声明了 {len(row_tables)} 张带 row_identity 的表 "
                f"{[t for _s, t in row_tables]} —— 隐藏 UUID 列只有一列，绑定必须唯一；"
                "不得随手挑第一张（挑错会让受管格整体错位而无任何报错）",
                stage=ObservationStage.observe_workbook,
                context=ctx,
            )
        return ExcelIdentityBinding(
            table_name=anchors["table_name"],
            uuid_column=anchors["uuid_column_letter"],
            table_key=row_tables[0][1],
            metadata_sheet=anchors["metadata_sheet"],
            dynamic_column_columns={
                key: dict(value) for key, value in dynamic_bindings.items()
            },
        )

    # ─── stage 8 ─────────────────────────────────────────────────────

    def _assert_matches_frozen_digests(
        self, *, rep: Mapping[str, Any], contract: SyncContract, observed: Mapping[str, Any],
        resolution: CanonicalResolution, entry_id: str, correlation_id: str,
    ) -> None:
        """重算的两个 digest 必须与 finalize 时刻冻结在 representation 上的逐字相等。

        这一条把整个观测变成**可falsify**的：finalize 时刻的
        ``ExcelEntryFinalizeGate`` 用同一公式把 ``structure_hash`` /
        ``identity_inventory_sha256`` 冻进 representation row，请求时刻重算不等即说明
        artifact 的受管结构或 identity 清册已漂移（或观测公式与 finalize 公式脱钩）。
        """
        ctx = self._identity_context(
            resolution=resolution, entry_id=entry_id, correlation_id=correlation_id
        )
        if observed["structure_hash"] != str(rep["structure_hash"]).strip():
            raise ObservedIdentityDriftError(
                f"重算 structure_hash {observed['structure_hash']} 与 representation 冻结的 "
                f"{rep['structure_hash']} 不一致 —— 受管结构已漂移，不得继续按旧坐标写格"
                "（Requirement 6.10 / Property 28）",
                stage=ObservationStage.frozen_digest_match,
                context={
                    **ctx,
                    "recomputed_structure_hash": observed["structure_hash"],
                    "frozen_structure_hash": str(rep["structure_hash"]),
                    "observed_structure_size": len(observed["structure"]),
                    "declared_structure_size": len(declared_structure_inventory(contract)),
                },
            )
        if observed["identity_inventory_sha256"] != str(rep["identity_inventory_sha256"]).strip():
            raise ObservedIdentityDriftError(
                f"重算 identity_inventory_sha256 {observed['identity_inventory_sha256']} 与 "
                f"representation 冻结的 {rep['identity_inventory_sha256']} 不一致 —— "
                "row identity / defined name / Table ref 已漂移",
                stage=ObservationStage.frozen_digest_match,
                context={
                    **ctx,
                    "recomputed_identity_inventory_sha256": (
                        observed["identity_inventory_sha256"]
                    ),
                    "frozen_identity_inventory_sha256": str(rep["identity_inventory_sha256"]),
                },
            )

    # ─── stage 9 ─────────────────────────────────────────────────────

    async def _load_definitions(
        self, *, resolution: CanonicalResolution, adapter_build: AdapterBuild,
        observed: Mapping[str, Any], entry_id: str, correlation_id: str,
    ) -> FrozenEntryDefinitions:
        """交给 Task 36 的唯一 loader 做九步校验。失败按原样上抛（error_code 已足够定位）。"""
        return await self._loader.load(
            entry_id=entry_id,
            frozen_bundle_id=resolution.bundle.bundle_id,
            frozen_bundle_sha256=resolution.bundle.bundle_sha256,
            adapter_build=adapter_build,
            identity_inventory=observed["identity_inventory"],
            observed_structure=observed["structure"],
            observed_business_sheets=observed["business_sheets"],
            observed_dynamic_columns={
                key: list(value) for key, value in observed["dynamic_columns"].items()
            },
        )

    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _identity_context(
        *, resolution: CanonicalResolution, entry_id: str, correlation_id: str
    ) -> dict[str, Any]:
        """AC 5.12 要求的诊断上下文（bundle/authority identity + typed child inventory）。"""
        bundle = resolution.bundle
        return {
            "correlation_id": correlation_id,
            "entry_id": entry_id,
            "representation_id": str(resolution.representation_id),
            "representation_generation": int(resolution.representation_generation),
            "content_version_id": str(resolution.content_version_id),
            "definition_bundle_id": str(bundle.bundle_id),
            "definition_bundle_sha256": bundle.bundle_sha256,
            "authority_model": bundle.authority_model.value,
            "authority_model_definition_id": str(bundle.authority_model_definition_id),
            "bundle_typed_child_inventory": [
                list(item) for item in bundle.typed_slot_inventory
            ],
            "adapter_id": resolution.adapter_id,
            "adapter_build_digest": resolution.adapter_build_digest,
        }


def recompute_structure_hash(
    *, contract: SyncContract, observed_structure: Sequence[tuple[str, str, str, str]]
) -> str:
    """与 ``ExcelEntryFinalizeGate`` 完全同构的 ``structure_hash`` 公式。

    两处必须一致 —— 不一致时观测器在任何真实 entry 上都会判「漂移」。守卫从 gate 源码
    现取那段表达式与本函数双向锁死（不是各写一份常量）。
    """
    return canonical_digest(
        {
            "schema_version": STRUCTURE_HASH_SCHEMA_VERSION,
            "contract_sha256": contract.canonical_sha256,
            "structure": [list(item) for item in sorted(observed_structure)],
        }
    )


def _frozen_anchors(instrumentation: Mapping[str, Any]) -> dict[str, str] | None:
    """从冻结 instrumentation payload 取反读所需的三个锚点参数。缺任一项返回 ``None``。"""
    sheets = instrumentation.get("managed_sheets")
    if not isinstance(sheets, (list, tuple)) or not sheets:
        return None
    sheet = sheets[0]
    if not isinstance(sheet, AbcMapping):
        return None
    sheet_key = str(sheet.get("sheet_key") or "").strip()
    boundary = sheet.get("region_boundary_locator")
    table_name = ""
    if isinstance(boundary, AbcMapping):
        table_name = str(boundary.get("table_key") or "").strip()
    tables = sheet.get("tables")
    uuid_column = ""
    if isinstance(tables, (list, tuple)) and tables and isinstance(tables[0], AbcMapping):
        uuid_column = str(tables[0].get("row_uuid_column_letter") or "").strip()
    meta = instrumentation.get("hidden_metadata_sheet")
    metadata_sheet = ""
    if isinstance(meta, AbcMapping):
        metadata_sheet = str(meta.get("sheet_name") or "").strip()
    if not (sheet_key and table_name and uuid_column and metadata_sheet):
        return None
    return {
        "sheet_key": sheet_key,
        "table_name": table_name,
        "uuid_column_letter": uuid_column,
        "metadata_sheet": metadata_sheet,
    }


async def resolve_project_scope(*, session: AsyncSession, representation: Any) -> uuid.UUID:
    """按 representation 冻结的 ``artifact_id`` 读出它所属 project。

    刻意**不**接受调用方传入的 project_id 作为 scope 真源：resolver 的第 ⑥ 步要把
    「artifact 属于请求 scope」比出来，两边都由调用方给就退化成自我比对。这里取的是
    immutable representation row → artifact row 这条冻结链上的值。
    """
    from app.models.workpaper_sync_models import WorkpaperArtifact

    artifact_id = getattr(representation, "artifact_id", None)
    if artifact_id is None:
        raise RepresentationShapeError(
            "representation.artifact_id 为空 —— 无法确定 project scope",
            stage=ObservationStage.representation_shape,
            context={"stage": ObservationStage.representation_shape.value},
        )
    project_id = (
        await session.execute(
            sa.select(WorkpaperArtifact.project_id).where(WorkpaperArtifact.id == artifact_id)
        )
    ).scalars().first()
    if project_id is None:
        raise ArtifactUnreadableError(
            f"representation 冻结的 artifact {artifact_id} 没有对应 artifact row —— "
            "pointer 指向缺失 artifact 的半成功态必须可见地报错",
            stage=ObservationStage.published_artifact,
            context={"artifact_id": str(artifact_id)},
        )
    return project_id


async def observe_published_frozen_definitions(
    *,
    session: AsyncSession,
    resolution: CanonicalResolutionService,
    representation: Any,
    project_id: uuid.UUID | None = None,
    intent: ResolutionIntent | str = ResolutionIntent.config,
    correlation_id: str | None = None,
) -> PublishedObservation:
    """四个 pilot 的 ``resolve_published_frozen_definitions()`` 共用的**唯一**实现入口。

    返回**完整** :class:`PublishedObservation` 而不是只返回
    :class:`FrozenEntryDefinitions` —— ``adapters.excel.build_excel_adapter()`` 要两个入参
    （``definitions`` **与** ``binding``），而 ``FrozenEntryDefinitions`` 上没有
    ``identity_binding`` 字段。只返回前者会让调用方写出
    ``binding=definitions.identity_binding`` 这种 ``AttributeError`` 接线（BP-17 实测形态）。
    """
    scope = (
        project_id
        if project_id is not None
        else await resolve_project_scope(session=session, representation=representation)
    )
    observer = PublishedIdentityObserver(session=session, resolution=resolution)
    return await observer.observe(
        representation=representation,
        project_id=scope,
        intent=intent,
        correlation_id=correlation_id,
    )
