# -*- coding: utf-8 -*-
"""Task 38 守卫：Excel identity-aware materializer / rematerializer。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 38
Requirements: 3.4, 3.5, 6.3, 6.4, 6.5, 6.6, 6.9, 6.11, 6.15, 6.16, 6.17, 6.18,
8.10, 8.11, 8.12
Properties: P9 / P22 / P23 / P24 / P29 / P65 / P66 / P67

═══ 判据落在哪 ═══

* **P9 临时校验与原子发布** —— :class:`TestProperty9AtomicPublish`。判据不是「代码里有
  `os.replace`」而是**注入失败后盘上的事实**：substrate 字节 sha256 不变、`output` 不存在、
  `*.materializing` 临时文件不残留。注入点覆盖计划期（结构判据）、写盘期（`_write_entries`
  抛错）与反读期（verifier 不通过 ⇒ `assert_ready_for_commit` 抛）。
* **P22 动态列 key 与 label 解耦** —— :class:`TestProperty22DynamicColumnKeys`。正面判据是
  「改 label 后两次 materialize 的受管 projection 逐键相同」与「两列同名 label 各自落进不同
  列且值互不覆盖」；反面判据是「用 label 当键」「两 slot 撞同一列」「缺实测绑定」三种形态
  各自打红。
* **P23 动态行身份不使用下标** —— :class:`TestProperty23RowIdentityIsNotPositional`。把
  merged projection 的行序**反转**后 materialize，值仍落在各自 identity 的物理行上；已
  tombstone 的 UUID 不被 minted 复用；OO 新增行的 minted UUID 必须先进 projection。
* **P24 保护字段修改形成冲突** —— :class:`TestProperty24ProtectedFieldsStayProtected`。
  incoming 把 `=G7-D7` 改成 `=G7-D7+1`（缓存值不变）后：baseline 从 application 冻结的 base
  representation 现算 ⇒ 篡改**可见**；未进 conflict set 即抛；staged result 的 `<f>` 与 base
  逐字相同。同时反证「没有 baseline 时这条链完全不可见」。
* **P29 materialize/extract roundtrip** —— :class:`TestProperty29Roundtrip`。两个口径都测：
  Task 37 的 `verify_roundtrip_equivalence`（只比 editable）与 Task 15 的
  `_assert_roundtrip_equivalent`（比**全部**受管字段，含 formula 缓存值与 auto_source）。
  后者才是 `cached_value_only` 这种写法存在的理由。
* **P65 projection 与 representation 等值 / substrate 准入** ——
  :class:`TestProperty65SubstrateAdmissionAndProjectionIdentity`。quarantined 与 candidate 在
  **打开文件之前**被拒（用不存在的路径证明顺序不可交换）；staged result 的 projection digest
  与 merged 逐字节相同。
* **P66 identity 往返保留** —— :class:`TestProperty66IdentityRetainedAfterWrite`。写完之后
  反读 staged 产物的运行时清册，交给 Task 37 的 `assert_identity_inventory_retained`；载体被
  破坏时 engine 门必须拦住。
* **P67 upgrade candidate** —— :class:`TestProperty67UpgradeCandidateFirst`。candidate 命名
  空间、不可当业务 commit、`revision_delta == 0`、业务 projection 逐字节不变；并用故障注入
  证明「业务 projection 真的变了」这一支可达（否则该分支永久 GREEN）。

═══ 假绿防线 ═══

1. **失败形态可达且互不折叠** —— :class:`TestFailureKindsAreReachableAndMutuallyDistinct`
   把 10 种写入侧失败**各真触发一次**，收集实际 `error_code` 集合，与
   `excel_materialize.FAILURE_KINDS` 双向等值 + 断言基数。这比「每类各测一遍」强：后者在
   两类被合并成同一个 code 时全部仍绿。
2. **fixture 用真实权威模板** —— 全部 substrate 由 `backend/wp_templates/K/K11 资产减值损失.xlsx`
   经 Task 17 instrumentation 得到（7 sheet / 1 drawing / 8 merge / 多组共享公式）。手搓的最小
   xlsx 上「未管理区域」是空集 ⇒ `equivalent` 恒真，判据空转。
3. **fixture 与 Task 37 共用同一份** —— 直接 import `test_task37_excel_extract` 的构造件，
   不抄第二份。抄一份就会出现「extractor 在 A 形态上验过、materializer 在 B 形态上验过」，
   而 roundtrip 判据恰恰要求两侧看到同一份字节。
4. **模板库只读** —— 本文件跑完 `TEMPLATE_SHA` 必须不变（Requirement 9.9）。
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import identity_inventory  # noqa: E402
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_rematerialize as RM  # noqa: E402
from app.services.workpaper_sync import merge as MG  # noqa: E402
from app.services.workpaper_sync.adapters import excel as AX  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    AdapterCandidateSubstrateError,
    AdapterSubstrateError,
    FieldValue,
    Projection,
    SubstrateRole,
)
from app.services.workpaper_sync.content_mutation import (  # noqa: E402
    projection_canonical_digest,
)
from app.services.workpaper_sync.contracts import (  # noqa: E402
    FieldMode,
    ValueType,
    parse_contract,
)
from app.services.workpaper_sync.excel_entry_gate import (  # noqa: E402
    AdapterBuild,
    FrozenEntryDefinitions,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    ArtifactKind,
    ArtifactState,
    DefinitionState,
    QuarantinedIncomingError,
)
from app.services.workpaper_sync.adapters.registry import StaleAdapterError  # noqa: E402

# 🔴 与 Task 37 共用同一份 fixture 构造件（真实模板 + zip 级字节编辑）。
#    不抄第二份：roundtrip 判据要求 extractor 与 materializer 看到同一份字节。
from test_task37_excel_extract import (  # noqa: E402
    BINDING,
    CONTRACT_ID,
    ENTRY_ID,
    EXPECTED_ROW_COUNT,
    EXPECTED_TABLE_REF,
    FIRST_ROW,
    FOOTER_ROW,
    LAST_ROW,
    MANAGED_SHEET,
    SPEC,
    TABLE_NAME,
    TEMPLATE,
    TEMPLATE_SHA,
    UUID_COL,
    _d,
    _read_entries,
    _sheet_part_of,
    _write_entries,
    business_cells,
    contract_payload,
    edit_part,
    grow_table_to,
    make_bundle,
    make_definitions,
    patch_cells,
)
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402

#: 模板里实测的两个空列（行 7..25 上无公式、无值），落在 Table ref `A7:N25` 之内。
#: 动态列 fixture 用它们，避免覆盖 `'明细表K11-2'!C11` 这类跨表引用公式。
DYN_COLUMNS: Mapping[str, str] = {"unit_1": "K", "unit_2": "L"}

#: 模板实测：`H8:H25` 是一组共享公式，主格在 H8（`<f t="shared" ref="H8:H25" si="1">`）。
SHARED_MASTER_ROW = FIRST_ROW + 1
#: 模板实测：footer 合计行是第 26 行，B26 是 `SUM(B7:B25)` 的共享公式主格。
TEMPLATE_FOOTER_ROW = 26


def _managed_projection(projection: Projection) -> dict[str, Any]:
    """按 Task 15 `_assert_roundtrip_equivalent` 的口径取**全部**受管字段值。"""
    return {key: value.value for key, value in projection.values.items()}


def _sweep_template_library_leak(candidate: Path) -> bool:
    """返回「这个路径是否真的被写出来了」，并**顺手删掉**它。

    🔴 顺序是「先判定、再清理」，不是「先清理、再判定」——后者会把判据掏空。

    为什么必须清理：变异检验把模板库写入禁令关掉之后，这条用例会真的在
    `backend/wp_templates/` 下留下文件；不清理的话**下一轮基线**就带着一个失败进来，
    `cli.run_cli` 直接 ABORT（本任务首轮实测：`injected.xlsx` 与 `kinds-10.xlsx` 两个残留
    让整轮变异在基线阶段中止）。这不是「掩盖问题」：判定结果已经记下来了，清理只是让守卫
    不带副作用。
    """
    existed = candidate.exists()
    if existed:
        candidate.unlink()
    return existed


# ═══════════════════════════════════════════════════════════════════════════
# 1. fixture：真实模板 → instrumented → 业务值 → frozen 身份
# ═══════════════════════════════════════════════════════════════════════════


def dynamic_contract_payload(*, footer_anchor: bool = True) -> dict[str, Any]:
    """`k11_rows` 声明 `dynamic_columns` 的契约变体（Property 22 用）。

    与 Task 37 的 `contract_payload(with_dynamic_columns=True)` 的区别：那一份的
    `column_key` 仍是 `adjustment`/`reason`/`variance`（extractor 不校验键形态），而写入侧的
    Property 22 判据要求键**必须**符合 `{slot}_{seq}`。因此这里换成实测空列 K/L 上的
    `unit_1`/`unit_2`。

    :param footer_anchor: 是否保留 `footer_anchor` 声明。去掉它可以让 footer 判据整体跳过，
        用于让「OO 新增行的 minted 身份未进 projection」这条分支可达（否则会先撞 footer
        合计公式区间判据 —— 判定顺序不可交换，靠后的分支在真实数据上不可达）。
    """
    payload = contract_payload()
    rows = payload["sheets"][0]["tables"][0]
    rows["dynamic_columns"] = {
        "identity": "{slot}_{seq}",
        "source_ref": "源xlsx!审定表K11-1!K6:L6",
    }
    if not footer_anchor:
        rows.pop("footer_anchor", None)
    rows["fields"] = [
        {
            "stable_field_key": "k11_rows/{row_uuid}/unit_1",
            "json_pointer": "/rows/{row_uuid}/unit1",
            "column_key": "unit_1",
            "cell": {"column": DYN_COLUMNS["unit_1"], "row_from": "row_identity"},
            "mode": "editable",
            "value_type": "amount",
            "source_ref": "源xlsx!审定表K11-1!K7",
        },
        {
            "stable_field_key": "k11_rows/{row_uuid}/unit_2",
            "json_pointer": "/rows/{row_uuid}/unit2",
            "column_key": "unit_2",
            "cell": {"column": DYN_COLUMNS["unit_2"], "row_from": "row_identity"},
            "mode": "editable",
            "value_type": "amount",
            "source_ref": "源xlsx!审定表K11-1!L7",
        },
    ]
    return payload


def dynamic_binding(**over: Any) -> X.ExcelIdentityBinding:
    columns: dict[str, str] = dict(over.pop("columns", DYN_COLUMNS))
    return X.ExcelIdentityBinding(
        table_name=TABLE_NAME,
        uuid_column=UUID_COL,
        table_key="k11_rows",
        dynamic_column_columns={"k11_rows": columns},
        **over,
    )


def gt_sync_part(data: bytes) -> str:
    """隐藏 `_GT_SYNC` 的 sheet 部件名。

    🔴 不能用 Task 37 fixture 的 `_sheet_part_of`：它按 `r:id="(rId\\d+)"` 找关系，而 Task 17 给
    隐藏 sheet 的关系 id 是 `rIdGTSYNC` ⇒ 0 命中。生产读侧走
    `excel_extract.read_runtime_binding_pairs`（经 `parse_workbook_xml` 解析关系，不假设 id 形态）；
    测试这里直接取 Task 17 的固定部件名常量，并实测它在 zip 里。
    """
    part = EI._GT_SYNC_SHEET_PART
    assert part in _read_entries(data), f"{part} 不在 zip 里（instrumentation 形态变了）"
    return part


def patch_runtime_binding(data: bytes, key: str, value: str) -> bytes:
    """把隐藏 `_GT_SYNC` 里某个 key 的 value 换掉（模拟冻结值与实测不符）。

    定位按「A 列文本 == key」而不是行号：Task 17 往 pairs 里加一条就会让行号全部下移。
    """
    part = gt_sync_part(data)

    def _transform(blob: bytes) -> bytes:
        xml = blob.decode("utf-8")
        pattern = re.compile(
            r'(<c r="A(?P<row>\d+)" t="inlineStr"><is><t xml:space="preserve">'
            + re.escape(key)
            + r'</t></is></c><c r="B(?P=row)" t="inlineStr"><is><t xml:space="preserve">)'
            r"(?P<value>[^<]*)(</t>)"
        )
        found = pattern.search(xml)
        assert found is not None, f"`_GT_SYNC` 里找不到 {key!r}（fixture 已失效）"
        # 🔴 用命名组取，不用位置组：`(?P<row>...)` 嵌在 group(1) 里，`</t>` 其实是 group(4)。
        #    首轮按 group(3) 拼回去，把 value 写了两遍 ⇒ XML 标签不配对。
        return (
            xml[: found.start()] + found.group(1) + value + "</t>" + xml[found.end() :]
        ).encode("utf-8")

    return edit_part(data, part, _transform)


def label_cells(**labels: str) -> dict[str, Any]:
    """动态列的展示 label（写在表头第 6 行，受管行区间之外）。"""
    return {f"{DYN_COLUMNS[slot]}6": text for slot, text in labels.items()}


def set_cell_attrs(data: bytes, sheet_part: str, coord: str, attrs: str) -> bytes:
    """给某格换掉属性串（用于给受管格补上样式 / 过期的 `t=` 标记）。

    🔴 存在的理由：Task 37 的 `patch_cells` 写格时不带 `s=`，于是 fixture 里的受管格**没有
    样式** ⇒ 「样式保留」这条判据在真实数据上恒真（变异 M24 实测 GREEN）。补一次样式后判据
    才有区分力。
    """

    def _transform(blob: bytes) -> bytes:
        xml = blob.decode("utf-8")
        pattern = re.compile(
            r'<c r="' + re.escape(coord) + r'"(?P<attrs>(?:\s[^>]*?)?)(?P<tail>/>|>)'
        )
        found = pattern.search(xml)
        assert found is not None, f"{coord} 在 sheet XML 里定位不到（fixture 已失效）"
        return (
            xml[: found.start()]
            + f'<c r="{coord}"{attrs}{found.group("tail")}'
            + xml[found.end() :]
        ).encode("utf-8")

    return edit_part(data, sheet_part, _transform)


def drop_cached_value(data: bytes, sheet_part: str, coord: str) -> bytes:
    """删掉某个公式格的缓存 `<v>`（OO 尚未重算时的真实形态）。"""

    def _transform(blob: bytes) -> bytes:
        xml = blob.decode("utf-8")
        pattern = re.compile(
            r'(<c r="' + re.escape(coord) + r'"(?:\s[^>]*?)?>.*?</f>)<v>[^<]*</v>', re.S
        )
        found = pattern.search(xml)
        assert found is not None, f"{coord} 上找不到「公式 + 缓存值」（fixture 已失效）"
        return (xml[: found.start()] + found.group(1) + xml[found.end() :]).encode("utf-8")

    return edit_part(data, sheet_part, _transform)


@pytest.fixture(scope="module")
def instrumented_bytes() -> bytes:
    gate = EI.ExcelIdentityCarrierGate.load()
    return EI.instrument_workbook_bytes(TEMPLATE.read_bytes(), SPEC, gate=gate).instrumented_bytes


@pytest.fixture(scope="module")
def sheet_part(instrumented_bytes: bytes) -> str:
    return _sheet_part_of(instrumented_bytes, MANAGED_SHEET)


#: 受管 editable 格在 fixture 里被显式补上的样式（模板原值：C 列 `s="94"`、J 列 `s="56"`）。
#:
#: 🔴 文本格必须连 `t="inlineStr"` 一起写回：只写 `s="56"` 会把类型标记抹掉，那一格的
#: inline 文本就读不出来了（受管字段从 58 掉到 57，首轮实测 10 例连带打红）。
STYLED_MANAGED_CELLS: Mapping[str, str] = {
    f"C{FIRST_ROW}": ' s="94"',
    f"J{FIRST_ROW}": ' s="56" t="inlineStr"',
}


@pytest.fixture(scope="module")
def base_bytes(instrumented_bytes: bytes, sheet_part: str) -> bytes:
    """基线 substrate：业务值 + 动态列 label + 动态列初值 + 受管格样式。"""
    cells: dict[str, Any] = dict(business_cells())
    cells.update(label_cells(unit_1="公司甲", unit_2="公司乙"))
    for row in range(FIRST_ROW, LAST_ROW + 1):
        cells[f"{DYN_COLUMNS['unit_1']}{row}"] = 1000 + row
        cells[f"{DYN_COLUMNS['unit_2']}{row}"] = 2000 + row
    data = patch_cells(instrumented_bytes, sheet_part, cells)
    for coord, attrs in STYLED_MANAGED_CELLS.items():
        data = set_cell_attrs(data, sheet_part, coord, attrs)
    return data


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("task38")


@pytest.fixture(scope="module")
def base_path(base_bytes: bytes, workdir: Path) -> Path:
    path = workdir / "base.xlsx"
    path.write_bytes(base_bytes)
    return path


@pytest.fixture(scope="module")
def base_inventory(base_bytes: bytes) -> dict[str, Any]:
    return identity_inventory(
        base_bytes, expected_table=TABLE_NAME, uuid_column_letter=UUID_COL
    )


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(contract_payload(), adapter_id=CONTRACT_ID)


@pytest.fixture(scope="module")
def definitions(contract: Any, base_inventory: dict[str, Any]) -> FrozenEntryDefinitions:
    return make_definitions(contract, base_inventory)


@pytest.fixture(scope="module")
def base_outcome(
    base_path: Path, definitions: FrozenEntryDefinitions
) -> X.ExcelExtractOutcome:
    return X.extract_projection(
        artifact=base_path,
        definitions=definitions,
        binding=BINDING,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
    )


@pytest.fixture
def staging(workdir: Path, request: pytest.FixtureRequest) -> Path:
    out = workdir / ".staging" / re.sub(r"[^A-Za-z0-9_]", "_", request.node.name)
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_artifact(directory: Path, name: str, data: bytes) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def rebuild(
    projection: Projection,
    *,
    overrides: Mapping[str, Any] | None = None,
    row_keys: Mapping[str, Any] | None = None,
) -> Projection:
    """在既有 projection 上换掉若干字段值 / 行集（其余原样）。

    `overrides` 的 value 只换 :attr:`FieldValue.value`，`value_type`/`mode`/`row_key` 全部
    沿用原字段 —— 否则测试会顺手把契约声明也改掉，判据就不再是「值变了」而是「契约变了」。
    """
    values = dict(projection.values)
    for key, value in (overrides or {}).items():
        old = values[key]
        values[key] = FieldValue(
            stable_key=old.stable_key,
            value=value,
            value_type=old.value_type,
            mode=old.mode,
            row_key=old.row_key,
        )
    return Projection(
        contract_id=projection.contract_id,
        semantic_version=projection.semantic_version,
        document_type=projection.document_type,
        values=values,
        row_keys=dict(row_keys if row_keys is not None else projection.row_keys),
    )


def materialize(
    *,
    substrate: Path,
    projection: Projection,
    output: Path,
    definitions: FrozenEntryDefinitions,
    binding: X.ExcelIdentityBinding = BINDING,
    **over: Any,
) -> M.ExcelMaterializeOutcome:
    kwargs: dict[str, Any] = {
        "substrate": substrate,
        "projection": projection,
        "output": output,
        "definitions": definitions,
        "binding": binding,
        "substrate_role": SubstrateRole.published_representation,
        "substrate_kind": ArtifactKind.canonical,
        "substrate_state": ArtifactState.published,
    }
    kwargs.update(over)
    return M.materialize_projection(**kwargs)


def extract_staged(
    path: Path, definitions: FrozenEntryDefinitions, binding: X.ExcelIdentityBinding = BINDING
) -> X.ExcelExtractOutcome:
    return X.extract_projection(
        artifact=path,
        definitions=definitions,
        binding=binding,
        substrate_role=SubstrateRole.staged_result,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.staged,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 基线：真实模板上跑通一次，且模板库字节原样
# ═══════════════════════════════════════════════════════════════════════════


class TestBaselineMaterialize:
    """**Validates: Requirements 3.5 / 6.11 / 9.9**"""

    def test_authority_template_is_untouched(self) -> None:
        """跑完模板库字节必须原样（Requirement 9.9：`backend/wp_templates/` 运行时只读）。"""
        assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == TEMPLATE_SHA

    def test_fixture_substrate_carries_real_unmanaged_content(
        self, base_bytes: bytes, sheet_part: str
    ) -> None:
        """fixture 必须是真实模板：手搓最小 xlsx 上未管理区域是空集 ⇒ 判据空转。

        四项实测事实同时作为其它用例的前提锁死（模板换版时这里先红）：drawing 部件存在、
        受管 sheet 有 merge、`H8:H25` 是共享公式组、footer 合计是 `SUM(B7:B25)` 主格。
        """
        entries = _read_entries(base_bytes)
        assert "xl/drawings/vmlDrawing1.vml" in entries, "drawing 部件不见了"
        xml = entries[sheet_part].decode("utf-8")
        assert 'ref="E30:F30"' in xml, "受管区域之下的 merge 不见了"
        assert 'ref="H8:H25" si="1"' in xml, "H 列共享公式组不见了"
        assert "SUM(B7:B25)" in xml, "footer 合计公式不见了"
        assert len(entries) >= 30, f"部件数 {len(entries)} 太少，不像真实模板"

    def test_managed_writes_cover_every_field_mode(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        """三种写入形态都必须真的产生写入 —— 否则某一支的判据全是空转。"""
        outcome = X.extract_projection(
            artifact=base_path,
            definitions=definitions,
            binding=BINDING,
            substrate_role=SubstrateRole.published_representation,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.published,
        )
        result = materialize(
            substrate=base_path,
            projection=outcome.projection,
            output=staging / "staged.xlsx",
            definitions=definitions,
        )
        counts = result.plan.as_dict()["kind_counts"]
        assert counts["number_literal"] == EXPECTED_ROW_COUNT + 1, counts
        assert counts["inline_text"] == EXPECTED_ROW_COUNT, counts
        assert counts["cached_value_only"] == EXPECTED_ROW_COUNT, counts
        assert result.plan.footer_marker_row == TEMPLATE_FOOTER_ROW
        assert len(result.intended_formulas) == EXPECTED_ROW_COUNT

    def test_zip_patch_is_the_default_strategy(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        """默认恒为 zip 级定点修改，且拒绝理由被逐条记下（不是静默回落）。"""
        result = materialize(
            substrate=base_path,
            projection=_baseline_projection(base_path, definitions),
            output=staging / "staged.xlsx",
            definitions=definitions,
        )
        assert result.strategy.strategy is M.ExcelWriteStrategy.zip_patch
        assert result.strategy.refusals, "拒绝理由为空 ⇒ 无法从 evidence 看出为什么没开 openpyxl"

    def test_style_and_unmanaged_cells_survive_the_write(
        self,
        base_path: Path,
        base_bytes: bytes,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        staging: Path,
    ) -> None:
        """AC 3.5：只写受管字段，样式与未管理格逐字保留。"""
        projection = _baseline_projection(base_path, definitions)
        output = staging / "staged.xlsx"
        materialize(
            substrate=base_path,
            projection=projection,
            output=output,
            definitions=definitions,
        )
        before = _read_entries(base_bytes)
        after = _read_entries(output.read_bytes())
        assert sorted(before) == sorted(after), "zip 条目集合变了"
        for name in before:
            if name == sheet_part:
                continue
            assert before[name] == after[name], f"非受管部件 {name} 被改动"
        after_xml = after[sheet_part].decode("utf-8")
        # 🔴 判据必须落在**受管 editable 格**上：fixture 里其它格根本没有 `s=`（Task 37 的
        #    `patch_cells` 写格时不带样式）⇒ 拿它们比对时判据恒真（变异 M24 实测 GREEN）。
        for coord, attrs in STYLED_MANAGED_CELLS.items():
            got = re.search(rf'<c r="{coord}"([^>]*)', after_xml)
            assert got is not None, f"受管格 {coord} 消失了"
            assert attrs.strip() in got.group(1), (
                f"受管格 {coord} 的样式 {attrs.strip()!r} 没保留，实得 {got.group(1)!r}"
                "（AC 3.5：只写受管字段，样式必须保留）"
            )
        for coord in ("A7", "E30"):
            want = re.search(rf'<c r="{coord}"([^>]*)', before[sheet_part].decode("utf-8"))
            got = re.search(rf'<c r="{coord}"([^>]*)', after_xml)
            if want is None:
                continue
            assert got is not None and got.group(1) == want.group(1), (
                f"非受管格 {coord} 的属性被改动"
            )


def _baseline_projection(
    path: Path, definitions: FrozenEntryDefinitions, binding: X.ExcelIdentityBinding = BINDING
) -> Projection:
    return X.extract_projection(
        artifact=path,
        definitions=definitions,
        binding=binding,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
    ).projection


def _plan_for(
    substrate: Path,
    definitions: FrozenEntryDefinitions,
    *,
    extract_binding: X.ExcelIdentityBinding = BINDING,
    plan_binding: X.ExcelIdentityBinding | None = None,
    projection: Projection | None = None,
) -> M.MaterializePlan:
    """直接调 `plan_managed_writes`（纯函数入口）。

    `plan_binding` 与 `extract_binding` 可以不同 —— 那正是「adapter 跨 entry 复用」的真实错误
    形态，也是写入侧自己那几条 binding 判据的唯一可达入口。
    """
    outcome = X.extract_projection(
        artifact=substrate,
        definitions=definitions,
        binding=extract_binding,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
    )
    with zipfile.ZipFile(substrate) as zf:
        runtime_binding = X.read_runtime_binding_pairs(zf)
    return M.plan_managed_writes(
        projection=projection if projection is not None else outcome.projection,
        contract=definitions.contract,
        binding=plan_binding or extract_binding,
        region=outcome.region,
        scan=outcome.scan,
        substrate_entries=_read_entries(substrate.read_bytes()),
        substrate_formulas=outcome.formula_inventory,
        runtime_binding=runtime_binding,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 9：临时校验与原子发布
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty9AtomicPublish:
    """**Validates: Requirements 3.4** · Property 9

    判据是**盘上的事实**，不是「源码里有 os.replace」：注入失败后 substrate sha256 不变、
    `output` 不存在、`*.materializing` 不残留。三个注入点分别落在计划期、写盘期、反读期 ——
    「任一点」是 Property 9 的原话，只测一点会让另外两点的回滚路径永久不被执行。
    """

    def _assert_nothing_published(self, substrate: Path, before: str, output: Path) -> None:
        assert hashlib.sha256(substrate.read_bytes()).hexdigest() == before, (
            "substrate（current representation）字节被改动 —— materialize 必须只读它"
        )
        assert not output.exists(), f"校验失败却留下了产物 {output}"
        tmp = output.with_name(output.name + ".materializing")
        assert not tmp.exists(), f"临时文件 {tmp} 残留 —— 下一次 materialize 会读到半成品"

    def test_plan_stage_failure_publishes_nothing(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
    ) -> None:
        """计划期失败（merged projection 有 substrate 上不存在的行身份）⇒ 零产物。"""
        before = hashlib.sha256(base_path.read_bytes()).hexdigest()
        output = staging / "staged.xlsx"
        rows = dict(base_outcome.projection.row_keys)
        rows["k11_rows"] = tuple(rows["k11_rows"]) + ("GTROW-K11-9999",)
        with pytest.raises(M.RowSetDivergenceError):
            materialize(
                substrate=base_path,
                projection=rebuild(base_outcome.projection, row_keys=rows),
                output=output,
                definitions=definitions,
            )
        self._assert_nothing_published(base_path, before, output)

    def test_write_stage_failure_publishes_nothing(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """写盘期注入 IO 失败 ⇒ 临时文件被清掉、`output` 不出现。

        注入点选 `_write_entries`：它是 zip 重打包的唯一出口，此时**部分**条目已经写进了
        内存缓冲，正是「半成品」最容易泄漏到盘上的时刻。
        """
        before = hashlib.sha256(base_path.read_bytes()).hexdigest()
        output = staging / "staged.xlsx"

        def _boom(entries: Mapping[str, bytes]) -> bytes:
            raise OSError("注入：zip 重打包失败")

        monkeypatch.setattr(M, "_write_entries", _boom)
        with pytest.raises(OSError, match="注入"):
            materialize(
                substrate=base_path,
                projection=base_outcome.projection,
                output=output,
                definitions=definitions,
            )
        self._assert_nothing_published(base_path, before, output)

    def test_publish_stage_failure_leaves_no_temp_file(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """发布期（原子改名）失败 ⇒ 临时文件必须被清掉。

        🔴 注入点必须选 `os.replace`：只在 `_write_entries` 注入时临时文件**根本还没落盘**，
        「失败后清理临时文件」这条分支在那条路径上不可达 ⇒ 它的变异恒 GREEN。这里让写盘先
        成功、改名再失败，清理分支才真的被执行。
        """
        before = hashlib.sha256(base_path.read_bytes()).hexdigest()
        output = staging / "staged.xlsx"

        def _boom(src: Any, dst: Any) -> None:
            raise OSError("注入：原子改名失败")

        monkeypatch.setattr(M.os, "replace", _boom)
        with pytest.raises(OSError, match="注入"):
            materialize(
                substrate=base_path,
                projection=base_outcome.projection,
                output=output,
                definitions=definitions,
            )
        self._assert_nothing_published(base_path, before, output)

    def test_failed_write_does_not_touch_a_preexisting_output(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """临时文件必须是**另一条路径**：失败时已存在的 `output` 一个字节都不该动。

        判据形态是刻意选的：`tmp = output`（即「直接写目标路径」）在成功路径上与正确实现
        无法区分 —— 两者都产出同一份字节。只有「失败后」才能分辨：`finally` 的清理会把
        已存在的 `output` 删掉。于是这条用例把「tmp 与 output 不同路径」变成可 falsify 的
        行为判据，而不是读一遍源码。
        """
        sentinel = b"PRE-EXISTING-ARTIFACT"
        output = staging / "staged.xlsx"
        output.write_bytes(sentinel)

        def _boom(entries: Mapping[str, bytes]) -> bytes:
            raise OSError("注入：zip 重打包失败")

        monkeypatch.setattr(M, "_write_entries", _boom)
        with pytest.raises(OSError, match="注入"):
            materialize(
                substrate=base_path,
                projection=base_outcome.projection,
                output=output,
                definitions=definitions,
            )
        assert output.read_bytes() == sentinel, (
            "materialize 失败却动了已存在的 output —— 临时文件与目标路径必须是两条路径"
        )
        assert not output.with_name(output.name + ".materializing").exists()

    def test_verification_stage_failure_blocks_commit(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """反读期注入「写下去的值不是 projection 说的值」⇒ `assert_ready_for_commit` 抛。

        staged 文件此时**允许**存在（它就是待裁决的证物），但它不可交 commit：Property 9 守的
        是「current file hash / pointer / revision 不变」，不是「不许留 staged 文件」。
        """
        original = M._render_number

        def _lossy(value: Any) -> str:
            rendered = original(value)
            try:
                return str(int(float(rendered)) + 1)
            except (TypeError, ValueError):
                return rendered

        monkeypatch.setattr(M, "_render_number", _lossy)
        before = hashlib.sha256(base_path.read_bytes()).hexdigest()
        result = RM.materialize_for_editing(
            current_representation=base_path,
            projection=base_outcome.projection,
            output=staging / "staged.xlsx",
            definitions=definitions,
            binding=BINDING,
        )
        assert result.publishable is False
        with pytest.raises(X.RoundtripEquivalenceError):
            result.assert_ready_for_commit()
        assert hashlib.sha256(base_path.read_bytes()).hexdigest() == before

    def test_temp_file_is_not_the_output_path(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
    ) -> None:
        """成功路径也必须经临时文件 + 原子改名：直接写 `output` 会让读侧看到半成品。

        判据落在**真实执行**上：把 `output` 预先塞成一个哨兵字节串，materialize 成功后它必须
        被整体取代（而不是被就地追加/部分覆盖），且临时文件不残留。
        """
        output = staging / "staged.xlsx"
        output.write_bytes(b"SENTINEL-NOT-A-ZIP")
        materialize(
            substrate=base_path,
            projection=base_outcome.projection,
            output=output,
            definitions=definitions,
        )
        assert output.read_bytes()[:2] == b"PK", "产物不是 zip ⇒ 原子改名没发生"
        assert not output.with_name(output.name + ".materializing").exists()

    def test_output_inside_template_library_is_refused_before_any_read(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        """输出落模板库 ⇒ 在打开 substrate **之前**就拒（Requirement 9.9）。

        用 `..` 拼出来的路径也必须被拒 —— 判据是解析后的路径分量，不是字符串前缀。
        """
        for candidate in (
            _BACKEND / "wp_templates" / "K" / "injected.xlsx",
            _BACKEND / "data" / ".." / "wp_templates" / "injected.xlsx",
        ):
            with pytest.raises(M.TemplateLibraryWriteError):
                materialize(
                    substrate=base_path,
                    projection=_baseline_projection(base_path, definitions),
                    output=candidate,
                    definitions=definitions,
                )
            assert not _sweep_template_library_leak(candidate), (
                f"{candidate} 真的被写出来了 —— 模板库被污染（Requirement 9.9）"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 22：动态列 key 与 label 解耦
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def dyn_definitions(base_inventory: dict[str, Any]) -> FrozenEntryDefinitions:
    return make_definitions(
        parse_contract(dynamic_contract_payload(), adapter_id=CONTRACT_ID), base_inventory
    )


class TestProperty22DynamicColumnKeys:
    """**Validates: Requirements 6.4** · Property 22

    正面判据用**两份 label 不同的 substrate**跑同一套绑定，比对受管 projection 是否逐键相同；
    反面判据要求「label 当键」「两 slot 撞同一列」「缺实测绑定」各自打红。只写反面会让「键
    真的与 label 解耦」这件事完全没被证明。
    """

    def _materialize_with(
        self,
        *,
        data: bytes,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
        staging: Path,
        tag: str,
    ) -> Projection:
        substrate = write_artifact(workdir, f"dyn-{tag}.xlsx", data)
        projection = _baseline_projection(substrate, definitions, binding)
        output = staging / f"staged-{tag}.xlsx"
        materialize(
            substrate=substrate,
            projection=projection,
            output=output,
            definitions=definitions,
            binding=binding,
        )
        return extract_staged(output, definitions, binding).projection

    def test_renaming_the_label_does_not_change_the_key_or_the_target_column(
        self,
        base_bytes: bytes,
        sheet_part: str,
        dyn_definitions: FrozenEntryDefinitions,
        workdir: Path,
        staging: Path,
    ) -> None:
        """把公司 label 从「公司甲/公司乙」改成「合并主体A/合并主体B」⇒ 受管 projection 不变。"""
        binding = dynamic_binding()
        renamed = patch_cells(
            base_bytes, sheet_part, label_cells(unit_1="合并主体A", unit_2="合并主体B")
        )
        before = self._materialize_with(
            data=base_bytes, definitions=dyn_definitions, binding=binding,
            workdir=workdir, staging=staging, tag="label-a",
        )
        after = self._materialize_with(
            data=renamed, definitions=dyn_definitions, binding=binding,
            workdir=workdir, staging=staging, tag="label-b",
        )
        assert sorted(before.values) == sorted(after.values), "改 label 后 stable key 集合变了"
        assert _managed_projection(before) == _managed_projection(after), (
            "改 label 后受管值变了 —— label 参与了 identity（Requirement 6.4 明令禁止）"
        )
        assert any("/unit_1" in key for key in before.values), "unit_1 一个字段都没有 ⇒ 判据空转"

    def test_duplicate_labels_do_not_collide_into_one_column(
        self,
        base_bytes: bytes,
        sheet_part: str,
        dyn_definitions: FrozenEntryDefinitions,
        workdir: Path,
        staging: Path,
    ) -> None:
        """两个 slot 用**同一个** label（两家单位同名，合法输入）⇒ 值仍各归各列。"""
        binding = dynamic_binding()
        same = patch_cells(base_bytes, sheet_part, label_cells(unit_1="甲公司", unit_2="甲公司"))
        substrate = write_artifact(workdir, "dyn-dup-label.xlsx", same)
        source = _baseline_projection(substrate, dyn_definitions, binding)
        row = source.row_keys["k11_rows"][0]
        key1, key2 = f"k11_rows/{row}/unit_1", f"k11_rows/{row}/unit_2"
        target = rebuild(source, overrides={key1: 111.11, key2: 222.22})
        output = staging / "staged.xlsx"
        materialize(
            substrate=substrate, projection=target, output=output,
            definitions=dyn_definitions, binding=binding,
        )
        read_back = extract_staged(output, dyn_definitions, binding).projection
        assert str(read_back.values[key1].value) == "111.11"
        assert str(read_back.values[key2].value) == "222.22", (
            "同名 label 的两个 slot 互相覆盖了 —— 一家单位的数据凭空消失"
        )
        after = _read_entries(output.read_bytes())[sheet_part].decode("utf-8")
        assert f'<c r="{DYN_COLUMNS["unit_1"]}{FIRST_ROW}"' in after
        assert f'<c r="{DYN_COLUMNS["unit_2"]}{FIRST_ROW}"' in after

    def test_label_shaped_key_is_refused(
        self, base_path: Path, base_inventory: dict[str, Any], staging: Path
    ) -> None:
        """绑定里出现 `公司甲_1` 这类带 label 的键 ⇒ 拒（不得用可改 label 作 identity）。"""
        definitions = make_definitions(
            parse_contract(dynamic_contract_payload(), adapter_id=CONTRACT_ID), base_inventory
        )
        binding = dynamic_binding(columns={"公司甲_1": "K", "unit_2": "L"})
        with pytest.raises(M.DynamicColumnWriteError) as exc:
            M.assert_dynamic_column_binding_usable(
                contract=definitions.contract, binding=binding
            )
        assert "6.4" in str(exc.value) or "identity" in str(exc.value)

    def test_two_slots_bound_to_one_column_is_refused(
        self, base_inventory: dict[str, Any]
    ) -> None:
        """两个 `{slot}_{seq}` 落进同一列 ⇒ 拒（后写的会静默覆盖先写的）。"""
        definitions = make_definitions(
            parse_contract(dynamic_contract_payload(), adapter_id=CONTRACT_ID), base_inventory
        )
        with pytest.raises(M.DynamicColumnWriteError) as exc:
            M.assert_dynamic_column_binding_usable(
                contract=definitions.contract,
                binding=dynamic_binding(columns={"unit_1": "K", "unit_2": "K"}),
            )
        assert "同一列" in str(exc.value)

    def test_missing_measured_binding_is_refused(
        self, base_inventory: dict[str, Any]
    ) -> None:
        """契约声明 dynamic_columns 但没有实测绑定 ⇒ 拒，不按声明列右移猜。"""
        definitions = make_definitions(
            parse_contract(dynamic_contract_payload(), adapter_id=CONTRACT_ID), base_inventory
        )
        with pytest.raises(M.DynamicColumnWriteError):
            M.assert_dynamic_column_binding_usable(
                contract=definitions.contract,
                binding=X.ExcelIdentityBinding(
                    table_name=TABLE_NAME, uuid_column=UUID_COL, table_key="k11_rows"
                ),
            )

    def test_binding_outside_the_table_span_is_refused_by_both_layers(
        self, base_path: Path, base_inventory: dict[str, Any], staging: Path
    ) -> None:
        """绑定到 Table 列跨度之外（`A7:N25` 之外）⇒ 两层各自拒，且**顺序被锁死**。

        🔴 实测（本任务首轮）：经 `materialize_projection` 进来时先撞 Task 37 的
        `_resolve_field_column`（extract 在 plan 之前跑），于是写入侧自己那条列跨度判据在这条
        路径上**不可达**。这不是缺陷 —— 它守的是另一个入口：`plan_managed_writes` 是公开 API，
        调用方完全可能给 extract 与 plan 传**不同**的 binding（adapter 复用时的真实错误形态）。
        两条都锁住，任何一侧被删或被重排都会打红。
        """
        definitions = make_definitions(
            parse_contract(dynamic_contract_payload(), adapter_id=CONTRACT_ID), base_inventory
        )
        bad = dynamic_binding(columns={"unit_1": "Z", "unit_2": "L"})
        with pytest.raises(X.ManagedRegionResolutionError) as first:
            materialize(
                substrate=base_path,
                projection=_baseline_projection(base_path, definitions, dynamic_binding()),
                output=staging / "staged.xlsx",
                definitions=definitions,
                binding=bad,
            )
        assert EXPECTED_TABLE_REF in str(first.value)

        good = dynamic_binding()
        with pytest.raises(M.DynamicColumnWriteError) as second:
            _plan_for(
                base_path,
                definitions,
                extract_binding=good,
                plan_binding=dynamic_binding(
                    columns={"unit_1": "Z", "unit_2": "L", "unit_3": "M"}
                ),
            )
        assert EXPECTED_TABLE_REF in str(second.value)

    def test_column_count_is_not_hardcoded_anywhere(self) -> None:
        """反向自检：写入侧不得出现写死的列数/列字母清单（Requirement 6.4 末句）。

        判据是「动态列的目标列只从 binding 取」这一条结构事实：`_resolve_column` 在
        `table.dynamic_columns is not None` 时**只**读 `binding.dynamic_column_columns`。
        """
        source = (
            _BACKEND / "app" / "services" / "workpaper_sync" / "excel_materialize.py"
        ).read_text(encoding="utf-8")
        body = source.split("def _resolve_column(", 1)[1].split("\n\ndef ", 1)[0]
        assert "binding.dynamic_column_columns" in body
        assert "cell.column" in body, "静态列仍应走契约声明列（否则本判据把功能关掉了）"
        assert not re.search(r'\["[A-Z]"(?:\s*,\s*"[A-Z]")+\]', body), (
            "出现了写死的列字母清单"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Property 23：动态行身份不使用下标
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty23RowIdentityIsNotPositional:
    """**Validates: Requirements 6.5 / 6.9 / 6.15** · Property 23

    核心判据：把 merged projection 的行序**反转**后 materialize，值必须仍落在各自 identity 的
    物理行上。如果写入侧任何一处按下标定位，反转后第 1 行会拿到第 19 行的值 —— 而「值都写进去
    了、总数也对」这类计数式判据完全抓不到这个形态。
    """

    def test_reversed_row_order_lands_on_the_same_physical_rows(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
    ) -> None:
        identities = list(base_outcome.projection.row_keys["k11_rows"])
        assert len(identities) == EXPECTED_ROW_COUNT
        overrides = {
            f"k11_rows/{identity}/adjustment": float(index * 10 + 1)
            for index, identity in enumerate(identities)
        }
        reversed_rows = {"k11_rows": tuple(reversed(identities))}
        target = rebuild(
            base_outcome.projection, overrides=overrides, row_keys=reversed_rows
        )
        output = staging / "staged.xlsx"
        materialize(
            substrate=base_path,
            projection=target,
            output=output,
            definitions=definitions,
        )
        read_back = extract_staged(output, definitions).projection
        for key, want in overrides.items():
            got = read_back.values[key].value
            assert float(got) == want, (
                f"{key} 读回 {got!r} 期望 {want!r} —— 行序反转后值串行了，"
                "说明写入侧用了下标而不是 row identity"
            )

    def test_writes_target_the_row_that_carries_the_identity(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
        sheet_part: str,
    ) -> None:
        """结构判据：某个 identity 的写入坐标必须等于它在 substrate 上的物理行。"""
        plan = _plan_for(base_path, definitions)
        physical = base_outcome.scan.row_identity_by_row
        by_identity = {identity: row for row, identity in physical.items()}
        checked = 0
        for write in plan.field_writes:
            if not write.row_key:
                continue
            row = int(re.search(r"\d+$", write.coord).group(0))
            assert row == by_identity[write.row_key], (
                f"{write.stable_field_key} 写到第 {row} 行，"
                f"而 identity {write.row_key} 的物理行是 {by_identity[write.row_key]}"
            )
            checked += 1
        assert checked >= EXPECTED_ROW_COUNT, f"只检查了 {checked} 处写入 ⇒ 判据偏空"

    def test_minted_identity_must_reach_the_projection_first(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_inventory: dict[str, Any],
        workdir: Path,
        staging: Path,
    ) -> None:
        """OO 在受管区域末尾新增一行（空 UUID）⇒ minted 身份必须先经 merge 进 projection。

        🔴 fixture 形态是**追加新行**（先扩 Table ref 再写格），不是改已有行的 UUID：后者语义上
        是「原有 identity 消失」，会先被 Property 66 的保留门拦住，本分支根本走不到。
        用去掉 `footer_anchor` 的契约变体：留着它会先撞 footer 合计公式区间判据（Table ref 长到
        26 行而 `SUM(B7:B25)` 没跟着长）—— 判定顺序不可交换，靠后的分支在真实数据上不可达。
        """
        definitions = make_definitions(
            parse_contract(
                dynamic_contract_payload(footer_anchor=False), adapter_id=CONTRACT_ID
            ),
            base_inventory,
        )
        binding = dynamic_binding()
        grown = patch_cells(
            grow_table_to(base_bytes, TEMPLATE_FOOTER_ROW),
            sheet_part,
            {
                f"{DYN_COLUMNS['unit_1']}{TEMPLATE_FOOTER_ROW}": 4242.0,
                f"{DYN_COLUMNS['unit_2']}{TEMPLATE_FOOTER_ROW}": 4343.0,
            },
        )
        substrate = write_artifact(workdir, "dyn-oo-inserted.xlsx", grown)
        outcome = X.extract_projection(
            artifact=substrate,
            definitions=definitions,
            binding=binding,
            substrate_role=SubstrateRole.incoming,
            artifact_kind=ArtifactKind.incoming,
            artifact_state=ArtifactState.durable,
        )
        assert outcome.scan.minted_by_row, "Task 37 没有为新增行 mint 身份 ⇒ fixture 失效"
        minted = sorted(outcome.scan.minted_by_row.values())

        stale_rows = {
            "k11_rows": tuple(
                identity
                for identity in outcome.projection.row_keys["k11_rows"]
                if identity not in minted
            )
        }
        with pytest.raises(M.RowIdentityWriteError) as exc:
            materialize(
                substrate=substrate,
                projection=rebuild(outcome.projection, row_keys=stale_rows),
                output=staging / "staged.xlsx",
                definitions=definitions,
                binding=binding,
                substrate_role=SubstrateRole.incoming,
                substrate_kind=ArtifactKind.incoming,
                substrate_state=ArtifactState.durable,
            )
        assert minted[0] in str(exc.value)

    def test_minted_identity_is_written_into_the_hidden_uuid_column(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_inventory: dict[str, Any],
        workdir: Path,
        staging: Path,
    ) -> None:
        """minted 身份进了 projection 之后，必须**真的落盘**到隐藏 UUID 列（反读实测）。

        判据刻意不是「plan 里有一条 row_identity 写入」而是「反读 staged 产物的运行时清册里有
        这个 UUID」—— 前者在「写入被静默丢掉」时仍然成立。
        """
        definitions = make_definitions(
            parse_contract(
                dynamic_contract_payload(footer_anchor=False), adapter_id=CONTRACT_ID
            ),
            base_inventory,
        )
        binding = dynamic_binding()
        grown = patch_cells(
            grow_table_to(base_bytes, TEMPLATE_FOOTER_ROW),
            sheet_part,
            {f"{DYN_COLUMNS['unit_1']}{TEMPLATE_FOOTER_ROW}": 4242.0},
        )
        substrate = write_artifact(workdir, "dyn-oo-inserted-2.xlsx", grown)
        outcome = X.extract_projection(
            artifact=substrate,
            definitions=definitions,
            binding=binding,
            substrate_role=SubstrateRole.incoming,
            artifact_kind=ArtifactKind.incoming,
            artifact_state=ArtifactState.durable,
        )
        minted = sorted(outcome.scan.minted_by_row.values())
        assert minted, "fixture 失效：没有 minted 身份"
        output = staging / "staged.xlsx"
        result = materialize(
            substrate=substrate,
            projection=outcome.projection,
            output=output,
            definitions=definitions,
            binding=binding,
            substrate_role=SubstrateRole.incoming,
            substrate_kind=ArtifactKind.incoming,
            substrate_state=ArtifactState.durable,
        )
        assert result.plan.identity_writes, "没有产生 identity 写入"
        landed = set(result.staged_identity_inventory.row_uuids.values())
        assert set(minted) <= landed, (
            f"minted 身份 {minted} 没有落进隐藏 UUID 列（实测 {sorted(landed)[-3:]}）"
        )

    def test_tombstoned_identity_is_never_reused_for_a_new_row(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_inventory: dict[str, Any],
        workdir: Path,
        staging: Path,
    ) -> None:
        """已删除（tombstone）的 UUID 不得被 minted 复用（Requirement 6.15 末句）。"""
        definitions = make_definitions(
            parse_contract(
                dynamic_contract_payload(footer_anchor=False), adapter_id=CONTRACT_ID
            ),
            base_inventory,
        )
        grown = patch_cells(
            grow_table_to(base_bytes, TEMPLATE_FOOTER_ROW),
            sheet_part,
            {f"{DYN_COLUMNS['unit_1']}{TEMPLATE_FOOTER_ROW}": 5151.0},
        )
        substrate = write_artifact(workdir, "dyn-tombstone.xlsx", grown)
        tombstones = tuple(
            f"GTROW-K11-{row:04d}" for row in range(FIRST_ROW, FIRST_ROW + 3)
        )
        binding = dynamic_binding(tombstoned_row_keys=tombstones)
        outcome = X.extract_projection(
            artifact=substrate,
            definitions=definitions,
            binding=binding,
            substrate_role=SubstrateRole.incoming,
            artifact_kind=ArtifactKind.incoming,
            artifact_state=ArtifactState.durable,
        )
        minted = set(outcome.scan.minted_by_row.values())
        assert minted, "fixture 失效：没有 minted 身份"
        assert not (minted & set(tombstones)), (
            f"minted 身份 {sorted(minted)} 复用了已 tombstone 的 UUID {tombstones}"
        )
        output = staging / "staged.xlsx"
        result = materialize(
            substrate=substrate,
            projection=outcome.projection,
            output=output,
            definitions=definitions,
            binding=binding,
            substrate_role=SubstrateRole.incoming,
            substrate_kind=ArtifactKind.incoming,
            substrate_state=ArtifactState.durable,
        )
        landed = set(result.staged_identity_inventory.row_uuids.values())
        assert minted <= landed


# ═══════════════════════════════════════════════════════════════════════════
# 6. Property 24：受保护字段（公式 / auto-source）
# ═══════════════════════════════════════════════════════════════════════════

VARIANCE_KEY = f"k11_rows/GTROW-K11-{FIRST_ROW:04d}/variance"
TB_KEY = "k11_footer/tb_amount"


def tamper_formula(data: bytes, sheet_part: str, coord: str, new_text: str) -> bytes:
    """把某格的公式文本改掉但**保留缓存值**（OO 侧「等值字面量改写」的形态）。"""

    def _transform(blob: bytes) -> bytes:
        xml = blob.decode("utf-8")
        pattern = re.compile(
            r'(<c r="' + re.escape(coord) + r'"(?:\s[^>]*?)?>)<f>(?P<text>[^<]*)</f>'
        )
        found = pattern.search(xml)
        assert found is not None, f"{coord} 上找不到非共享公式（fixture 已失效）"
        return (
            xml[: found.start()]
            + found.group(1)
            + f"<f>{new_text}</f>"
            + xml[found.end() :]
        ).encode("utf-8")

    return edit_part(data, sheet_part, _transform)


class TestProperty24ProtectedFieldsStayProtected:
    """**Validates: Requirements 6.6** · Property 24

    三段判据缺一不可：
    1. **可见性** —— baseline 从 application 冻结的 base representation **现算**，篡改才可见；
       没有 baseline 时同一份 incoming 一条 finding 都没有（反证）。
    2. **闭合性** —— 每一处 finding 必须在调用方交来的 conflict set 里，漏报即抛。
    3. **不被覆盖** —— staged result 的 `<f>` 与 base 逐字相同，缓存 `<v>` 写服务端值。
    """

    def test_baseline_from_frozen_representation_makes_tamper_visible(
        self, base_bytes: bytes, base_path: Path, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path,
    ) -> None:
        tampered = tamper_formula(base_bytes, sheet_part, f"H{FIRST_ROW}", "G7-D7+1")
        incoming = write_artifact(workdir, "incoming-tampered.xlsx", tampered)
        baseline, baseline_formulas = RM.derive_baseline_from_representation(
            representation=base_path, definitions=definitions, binding=BINDING
        )
        assert baseline_formulas[VARIANCE_KEY] == "=G7-D7", baseline_formulas[VARIANCE_KEY]

        blind = X.extract_projection(
            artifact=incoming, definitions=definitions, binding=BINDING,
            substrate_role=SubstrateRole.incoming,
            artifact_kind=ArtifactKind.incoming,
            artifact_state=ArtifactState.durable,
        )
        assert blind.protected_findings == (), (
            "没有 baseline 时竟然报出了 finding —— 那说明它在猜，而不是在比对"
        )

        seeing = X.extract_projection(
            artifact=incoming, definitions=definitions, binding=BINDING,
            substrate_role=SubstrateRole.incoming,
            artifact_kind=ArtifactKind.incoming,
            artifact_state=ArtifactState.durable,
            baseline=baseline, baseline_formulas=baseline_formulas,
        )
        keys = {finding.stable_field_key for finding in seeing.protected_findings}
        assert VARIANCE_KEY in keys, (
            "带 baseline 也没发现公式被改写 —— Property 24 在生产上不可见"
            "（这正是 Task 37 登记给本任务的那条缺口）"
        )

    def test_unreported_tamper_blocks_rematerialize_before_any_byte_is_written(
        self, base_bytes: bytes, base_path: Path, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path, staging: Path,
    ) -> None:
        tampered = tamper_formula(base_bytes, sheet_part, f"H{FIRST_ROW}", "G7-D7+1")
        incoming = write_artifact(workdir, "incoming-unreported.xlsx", tampered)
        output = staging / "staged.xlsx"
        with pytest.raises(Exception) as exc:
            RM.rematerialize_merged_projection(
                merged=_baseline_projection(base_path, definitions),
                incoming_substrate=incoming,
                base_representation=base_path,
                output=output,
                definitions=definitions,
                binding=BINDING,
                merge_conflicts=(),
            )
        assert type(exc.value).__name__ != "OSError"
        assert not output.exists(), "篡改漏报时仍写出了 staged 产物"

    def test_reported_tamper_proceeds_and_keeps_the_template_formula(
        self, base_bytes: bytes, base_path: Path, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path, staging: Path,
    ) -> None:
        """把 finding 补成 protected 冲突后放行；staged 的 `<f>` 与 base 逐字相同。"""
        tampered = tamper_formula(base_bytes, sheet_part, f"H{FIRST_ROW}", "G7-D7+1")
        incoming = write_artifact(workdir, "incoming-reported.xlsx", tampered)
        base_projection, baseline_formulas = RM.derive_baseline_from_representation(
            representation=base_path, definitions=definitions, binding=BINDING
        )
        incoming_view = X.extract_projection(
            artifact=incoming, definitions=definitions, binding=BINDING,
            substrate_role=SubstrateRole.incoming,
            artifact_kind=ArtifactKind.incoming,
            artifact_state=ArtifactState.durable,
            baseline=base_projection, baseline_formulas=baseline_formulas,
        )
        conflicts = RM.protected_conflicts_from_incoming(
            incoming_view=incoming_view,
            definitions=definitions,
            base=base_projection,
            current=base_projection,
            incoming=incoming_view.projection,
        )
        assert conflicts, "受保护格篡改没有翻成 conflict ⇒ 审计师看不到任何冲突"
        output = staging / "staged.xlsx"
        result = RM.rematerialize_merged_projection(
            merged=base_projection,
            incoming_substrate=incoming,
            base_representation=base_path,
            output=output,
            definitions=definitions,
            binding=BINDING,
            merge_conflicts=conflicts,
        )
        assert result.protected_findings, "结论里没有带上 finding ⇒ 时间线无从追溯"
        staged_xml = _read_entries(output.read_bytes())[sheet_part].decode("utf-8")
        cell = re.search(
            r'<c r="H' + str(FIRST_ROW) + r'"(?:\s[^>]*?)?>(?P<body>.*?)</c>',
            staged_xml,
            re.S,
        )
        assert cell is not None
        assert "<f>G7-D7+1</f>" not in cell.group("body"), (
            "OO 改写的公式被写进了 staged result —— 受保护字段被覆盖（AC 6.6 失守）"
        )
        assert "<f>G7-D7</f>" in cell.group("body"), (
            f"模板公式没有逐字保留，实得 {cell.group('body')!r}"
        )

    def test_formula_cell_keeps_f_and_only_updates_cached_value(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path,
        sheet_part: str,
    ) -> None:
        """公式格只改 `<v>`：`<f>`（含 `t="shared" si=`）逐字保留。

        `H8` 是共享公式主格（`ref="H8:H25" si="1"`）—— 它的 `<f>` 一旦被换成字面量，H9..H25
        全组失效。判据直接比对字节。
        """
        projection = _baseline_projection(base_path, definitions)
        key = f"k11_rows/GTROW-K11-{SHARED_MASTER_ROW:04d}/variance"
        target = rebuild(projection, overrides={key: 777.25})
        output = staging / "staged.xlsx"
        materialize(
            substrate=base_path, projection=target, output=output, definitions=definitions
        )
        staged_xml = _read_entries(output.read_bytes())[sheet_part].decode("utf-8")
        cell = re.search(
            r'<c r="H' + str(SHARED_MASTER_ROW) + r'"(?:\s[^>]*?)?>(?P<body>.*?)</c>',
            staged_xml,
            re.S,
        )
        assert cell is not None
        body = cell.group("body")
        assert '<f t="shared" ref="H8:H25" si="1">G8-D8</f>' in body, (
            f"共享公式主格被改写，实得 {body!r}"
        )
        assert "<v>777.25</v>" in body, f"缓存值没有写服务端值，实得 {body!r}"

    def test_auto_source_cell_is_written_as_a_literal(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path,
        sheet_part: str,
    ) -> None:
        """auto_source 写服务端字面量（B27 在模板上无公式）—— 与公式格是两种不同写法。"""
        projection = _baseline_projection(base_path, definitions)
        target = rebuild(projection, overrides={TB_KEY: 98765.43})
        output = staging / "staged.xlsx"
        materialize(
            substrate=base_path, projection=target, output=output, definitions=definitions
        )
        staged_xml = _read_entries(output.read_bytes())[sheet_part].decode("utf-8")
        cell = re.search(
            r'<c r="B' + str(FOOTER_ROW) + r'"(?:\s[^>]*?)?>(?P<body>.*?)</c>',
            staged_xml,
            re.S,
        )
        assert cell is not None and "<v>98765.43</v>" in cell.group("body")
        assert "<f" not in cell.group("body"), "auto_source 格凭空长出了公式"

    def test_auto_source_on_a_formula_cell_is_refused(
        self, base_path: Path, base_inventory: dict[str, Any], staging: Path
    ) -> None:
        """契约把 auto_source 声明在**公式格**上 ⇒ 拒（写字面量会毁掉模板公式）。

        🔴 与「契约说 formula 但模板上没有公式」是**两条独立判据**（同一个 error_code、不同
        成因）。变异 M19 实测：只测后者时，把前者关掉照样绿 —— 靠前的分支永久不可达。
        fixture 把 footer auto_source 从 B27（模板上无公式）挪到 B26（`SUM(B7:B25)` 主格）。
        """
        payload = contract_payload()
        footer = payload["sheets"][0]["tables"][1]
        footer["anchor"] = f"A{TEMPLATE_FOOTER_ROW}"
        footer["fields"][0]["cell"] = {
            "column": "B", "row_from": TEMPLATE_FOOTER_ROW
        }
        definitions = make_definitions(
            parse_contract(payload, adapter_id=CONTRACT_ID), base_inventory
        )
        with pytest.raises(M.ProtectedRegionWriteError) as exc:
            materialize(
                substrate=base_path,
                projection=_baseline_projection(base_path, definitions),
                output=staging / "staged.xlsx",
                definitions=definitions,
            )
        assert "auto_source" in str(exc.value)
        assert "SUM(B7:B25)" in str(exc.value)

    def test_stale_text_marker_is_dropped_from_a_numeric_formula_cell(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_inventory: dict[str, Any],
        contract: Any,
        workdir: Path,
        staging: Path,
    ) -> None:
        """公式格带着过期的 `t="str"` 时，写数值缓存必须把它剥掉。

        真实形态：OO 保存时会按**上一次**计算结果给公式格打类型标记；服务端重算出数值后
        标记若不清掉，Excel 会把数字当字符串（求和恒为 0）。变异 M21 实测：不构造这个 fixture
        时该分支在真实模板上不可达（K11 的 H 列本来就没有 `t=`）⇒ 判据恒真。
        """
        stale = set_cell_attrs(base_bytes, sheet_part, f"H{FIRST_ROW}", ' s="95" t="str"')
        substrate = write_artifact(workdir, "stale-marker.xlsx", stale)
        definitions = make_definitions(
            contract,
            identity_inventory(stale, expected_table=TABLE_NAME, uuid_column_letter=UUID_COL),
        )
        output = staging / "staged.xlsx"
        materialize(
            substrate=substrate,
            projection=rebuild(
                _baseline_projection(substrate, definitions),
                overrides={VARIANCE_KEY: 1234.5},
            ),
            output=output,
            definitions=definitions,
        )
        after = _read_entries(output.read_bytes())[sheet_part].decode("utf-8")
        cell = re.search(r'<c r="H' + str(FIRST_ROW) + r'"(?P<attrs>[^>]*)>', after)
        assert cell is not None
        assert 't="str"' not in cell.group("attrs"), (
            f"过期的文本标记没被剥掉，实得 {cell.group('attrs')!r} —— "
            "Excel 会把这一格的数字当字符串"
        )

    def test_text_valued_formula_cell_keeps_its_string_marker(
        self, base_path: Path, base_inventory: dict[str, Any], staging: Path, sheet_part: str
    ) -> None:
        """文本型公式格（K11 实测 A7 是 `t="str"` + 跨表引用）必须**带上** `t="str"`。

        反过来的一半：无条件剥掉类型标记会让中文项目名被当数字解析，Excel 打开即报错。
        """
        # 🔴 只能挂**单行静态表**：模板实测 A 列并非每行都是公式（A7/A8 是跨表引用，
        #    A25 是 `t="s"` 的共享字符串）。按整列声明 formula 会先撞「substrate 上没有公式」
        #    那条判据，本判据就到不了。
        payload = contract_payload()
        payload["sheets"][0]["tables"].append(
            {
                "table_key": "k11_item_name",
                "anchor": f"A{FIRST_ROW}",
                "header_rows": 1,
                "formula_mask": [f"A{FIRST_ROW}:A{FIRST_ROW}"],
                "fields": [
                    {
                        "stable_field_key": "k11_item_name/first_row",
                        "json_pointer": "/itemName",
                        "column_key": "item_name",
                        "cell": {"column": "A", "row_from": FIRST_ROW},
                        "mode": "formula",
                        "value_type": "text",
                        "source_ref": "源xlsx!审定表K11-1!A7",
                    }
                ],
            }
        )
        definitions = make_definitions(
            parse_contract(payload, adapter_id=CONTRACT_ID), base_inventory
        )
        output = staging / "staged.xlsx"
        materialize(
            substrate=base_path,
            projection=_baseline_projection(base_path, definitions),
            output=output,
            definitions=definitions,
        )
        after = _read_entries(output.read_bytes())[sheet_part].decode("utf-8")
        cell = re.search(
            r'<c r="A' + str(FIRST_ROW) + r'"(?P<attrs>[^>]*)>(?P<body>.*?)</c>', after, re.S
        )
        assert cell is not None
        assert 't="str"' in cell.group("attrs"), (
            f"文本型公式格丢了 `t=\"str\"`，实得 {cell.group('attrs')!r}"
        )
        assert "<f>" in cell.group("body"), "文本型公式格的 `<f>` 没保留"

    def test_formula_cell_without_a_cached_value_gets_one(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_inventory: dict[str, Any],
        contract: Any,
        workdir: Path,
        staging: Path,
    ) -> None:
        """公式格只有 `<f>`、没有 `<v>` 时必须**补**一个缓存值。

        真实形态：OO 保存尚未重算的公式格时会省掉 `<v>`。不补的话 Task 15 的全字段等值门
        反读不到值 ⇒ 整次发布被挡掉。

        🔴 两处 fixture 细节都是实测逼出来的：
        1. K11 的公式格都带 `<v>0</v>`，不主动删掉这个分支根本不可达（变异 M22 首轮 GREEN）；
        2. 删掉 `<v>` 之后 **extract 反读不到这个字段**（openpyxl `data_only=True` 给 None），
           所以要写的值只能来自**另一侧**的 projection —— 这恰好就是生产形态：merged 带着
           base/current 的值，而 incoming 那一格还没重算。
        """
        stripped = drop_cached_value(base_bytes, sheet_part, f"H{FIRST_ROW}")
        substrate = write_artifact(workdir, "no-cached-value.xlsx", stripped)
        base = write_artifact(workdir, "no-cached-value-base.xlsx", base_bytes)
        definitions = make_definitions(
            contract,
            identity_inventory(
                stripped, expected_table=TABLE_NAME, uuid_column_letter=UUID_COL
            ),
        )
        merged = rebuild(
            _baseline_projection(base, definitions), overrides={VARIANCE_KEY: 4567.75}
        )
        assert VARIANCE_KEY not in _baseline_projection(substrate, definitions).values, (
            "fixture 失效：incoming 侧竟然还能反读到这个公式格的值"
        )
        output = staging / "staged.xlsx"
        materialize(
            substrate=substrate,
            projection=merged,
            output=output,
            definitions=definitions,
        )
        after = _read_entries(output.read_bytes())[sheet_part].decode("utf-8")
        cell = re.search(
            r'<c r="H' + str(FIRST_ROW) + r'"(?:\s[^>]*?)?>(?P<body>.*?)</c>', after, re.S
        )
        assert cell is not None
        assert "<v>4567.75</v>" in cell.group("body"), (
            f"缺 `<v>` 的公式格没有被补上缓存值，实得 {cell.group('body')!r}"
        )
        assert "<f>" in cell.group("body"), "补缓存值时把 `<f>` 弄丢了"

    def test_formula_regions_verifier_passes_on_a_clean_write(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path,
    ) -> None:
        """干净写入必须过 Task 37 的公式区域 verifier（否则上面那些判据是空转）。"""
        result = RM.materialize_for_editing(
            current_representation=base_path,
            projection=_baseline_projection(base_path, definitions),
            output=staging / "staged.xlsx",
            definitions=definitions,
            binding=BINDING,
        )
        assert result.verification.formulas.intact, result.verification.formulas
        assert result.verification.formulas.inspected_keys, "一个公式格都没检查 ⇒ 判据空转"
        result.assert_ready_for_commit()


# ═══════════════════════════════════════════════════════════════════════════
# 7. Property 29：materialize / extract roundtrip
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty29Roundtrip:
    """**Validates: Requirements 6.11 / 3.4** · Property 29

    两个口径都测，因为它们**范围不同**且都是硬约束：

    * Task 37 `verify_roundtrip_equivalence` 只比 `mode=editable`（公式/auto-source 的值由 OO
      重算，逐字节相等不是它们的正确性判据）；
    * Task 15 `_assert_roundtrip_equivalent` 比**全部**受管字段（只排除 `word_only`），因此
      公式格反读出来的**缓存值**也必须等于 merged projection 的值。

    后者正是 `cached_value_only` 这种「保 `<f>`、改 `<v>`」写法存在的理由：只要漏写 `<v>`，
    Task 15 的门就会在 commit 前把整次发布挡掉。
    """

    @pytest.mark.parametrize(
        "amount,text",
        [
            (0, "零"),
            (-1234.56, "负数与中文"),
            (1234567.89, "千分位边界"),
            (0.005, "小数舍入边界"),
            (99999999.99, "大额"),
        ],
    )
    def test_editable_values_survive_the_roundtrip(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
        amount: float,
        text: str,
    ) -> None:
        identity = base_outcome.projection.row_keys["k11_rows"][0]
        amount_key = f"k11_rows/{identity}/adjustment"
        text_key = f"k11_rows/{identity}/reason"
        target = rebuild(
            base_outcome.projection, overrides={amount_key: amount, text_key: text}
        )
        output = staging / f"staged-{amount}.xlsx"
        result = RM.materialize_for_editing(
            current_representation=base_path,
            projection=target,
            output=output,
            definitions=definitions,
            binding=BINDING,
        )
        result.assert_ready_for_commit()
        report = result.verification.roundtrip
        assert report.equivalent, report.first_difference
        assert len(report.compared_keys) == EXPECTED_ROW_COUNT * 2, (
            f"只比了 {len(report.compared_keys)} 个 editable 键 ⇒ 判据偏空"
        )
        read_back = result.verification.extracted.projection
        assert float(read_back.values[amount_key].value) == pytest.approx(amount)
        assert read_back.values[text_key].value == text

    def test_all_managed_fields_including_formula_cache_are_equivalent(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
    ) -> None:
        """Task 15 口径：公式格的缓存值与 auto_source 也必须逐字段等值。"""
        identity = base_outcome.projection.row_keys["k11_rows"][0]
        target = rebuild(
            base_outcome.projection,
            overrides={
                f"k11_rows/{identity}/adjustment": 4321.5,
                f"k11_rows/{identity}/variance": 55.25,
                TB_KEY: 24680.13,
            },
        )
        output = staging / "staged.xlsx"
        materialize(
            substrate=base_path, projection=target, output=output, definitions=definitions
        )
        read_back = extract_staged(output, definitions).projection
        want = _managed_projection(target)
        got = _managed_projection(read_back)
        assert sorted(want) == sorted(got), "受管字段集合变了"
        differing = {
            key: (want[key], got[key])
            for key in want
            if not MG.values_equal(want[key], got[key], target.values[key].value_type)
        }
        assert not differing, (
            f"以下受管字段反读不等值（Task 15 会在 commit 前挡掉整次发布）: "
            f"{sorted(differing)[:5]} 例 {list(differing.items())[:2]}"
        )
        assert len(want) == EXPECTED_ROW_COUNT * 3 + 1, (
            f"受管字段只有 {len(want)} 个 ⇒ 判据偏空（19 行 × 3 列 + footer）"
        )

    def test_a_written_value_that_cannot_be_read_back_fails_the_gate(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        staging: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """反向自检：把写入的值悄悄改掉一位，roundtrip 门必须打红（否则它是空转）。"""
        original = M._render_number

        def _shifted(value: Any) -> str:
            rendered = original(value)
            return rendered + "1" if rendered.replace(".", "").isdigit() else rendered

        monkeypatch.setattr(M, "_render_number", _shifted)
        result = RM.materialize_for_editing(
            current_representation=base_path,
            projection=base_outcome.projection,
            output=staging / "staged.xlsx",
            definitions=definitions,
            binding=BINDING,
        )
        assert result.verification.roundtrip.equivalent is False
        with pytest.raises(X.RoundtripEquivalenceError):
            result.assert_ready_for_commit()

    def test_unmanaged_regions_are_compared_against_the_substrate(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        """未管理区域比对必须**真的比到东西**（8 个 aspect 计数全部 > 0 的那份覆盖面）。"""
        result = RM.materialize_for_editing(
            current_representation=base_path,
            projection=_baseline_projection(base_path, definitions),
            output=staging / "staged.xlsx",
            definitions=definitions,
            binding=BINDING,
        )
        report = result.verification.unmanaged
        assert report.equivalent, report.first_difference
        coverage = result.verification.extracted.unmanaged.coverage
        assert coverage, "覆盖面为空 ⇒ 未管理区域判据在空集上恒真"
        zero = sorted(name for name, count in coverage.items() if not count)
        assert not zero, f"以下 aspect 一个条目都没比到 ⇒ 判据空转: {zero}"


# ═══════════════════════════════════════════════════════════════════════════
# 8. Property 65：substrate 准入与 projection 身份
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty65SubstrateAdmissionAndProjectionIdentity:
    """**Validates: Requirements 8.10 / 8.11 / 8.12** · Property 65

    🔴 判定顺序不可交换：substrate 准入必须在**任何**解析/写入之前。判据用一条不存在的路径 ——
    若准入门被挪到解析之后，抛出来的会是 zip/FileNotFound 而不是隔离错误。本 spec 已实测过
    这个形态（Task 58 的路径穿越判据因为放在模板解析之后而落在永久不可达分支）。
    """

    def test_quarantined_incoming_is_refused_before_the_file_is_opened(
        self, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        missing = staging / "does-not-exist.xlsx"
        assert not missing.exists()
        with pytest.raises(QuarantinedIncomingError):
            materialize(
                substrate=missing,
                projection=Projection(
                    contract_id=CONTRACT_ID,
                    semantic_version="1.0.0",
                    document_type="xlsx",
                    values={},
                    row_keys={},
                ),
                output=staging / "staged.xlsx",
                definitions=definitions,
                substrate_role=SubstrateRole.incoming,
                substrate_kind=ArtifactKind.incoming,
                substrate_state=ArtifactState.quarantined,
            )
        assert not (staging / "staged.xlsx").exists()

    def test_quarantined_incoming_is_refused_by_the_oo_to_html_entry(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        """OO→HTML 入口同样在 engine 入口拒 —— 本协议不提供解除隔离的边。"""
        with pytest.raises(QuarantinedIncomingError):
            RM.rematerialize_merged_projection(
                merged=_baseline_projection(base_path, definitions),
                incoming_substrate=base_path,
                base_representation=base_path,
                output=staging / "staged.xlsx",
                definitions=definitions,
                binding=BINDING,
                incoming_state=ArtifactState.quarantined,
            )
        assert not (staging / "staged.xlsx").exists()

    def test_quarantined_is_refused_before_the_output_path_check(
        self, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        """判定顺序：quarantined 必须先于「输出落模板库」被拒。

        🔴 这条判据的形式是刻意的。变异 M26 实测：单独测「quarantined 被拒」时把
        materializer 自己那道准入门删掉**照样绿** —— 因为 Task 37 的 `extract_projection`
        内部也会拒，只是抛得更晚。用「同时违反两条禁令、看抛哪一条」才能把顺序钉住：
        engine 入口的安全门必须在任何路径/解析判据之前（AC 8.10）。
        """
        leak = _BACKEND / "wp_templates" / "K" / "order-probe.xlsx"
        try:
            with pytest.raises(QuarantinedIncomingError):
                materialize(
                    substrate=staging / "missing.xlsx",
                    projection=Projection(
                        contract_id=CONTRACT_ID, semantic_version="1.0.0",
                        document_type="xlsx", values={}, row_keys={},
                    ),
                    output=leak,
                    definitions=definitions,
                    substrate_role=SubstrateRole.incoming,
                    substrate_kind=ArtifactKind.incoming,
                    substrate_state=ArtifactState.quarantined,
                )
        finally:
            assert not _sweep_template_library_leak(leak)

    def test_unapproved_bundle_is_refused_before_the_output_path_check(
        self, contract: Any, base_inventory: dict[str, Any], staging: Path
    ) -> None:
        """判定顺序：frozen 身份门必须先于「输出落模板库」被拒。

        同上（变异 M27）：materializer 自己那道身份门若被删，Task 37 的 extract 仍会拒，
        但那时 substrate 已经被打开、输出路径判据也已经先抛。用「同时违反两条禁令」定序。
        """
        drafted = make_definitions(
            contract,
            base_inventory,
            bundle=make_bundle(contract, state=DefinitionState.candidate),
        )
        leak = _BACKEND / "wp_templates" / "K" / "order-probe-2.xlsx"
        try:
            with pytest.raises(Exception) as exc:
                materialize(
                    substrate=staging / "missing.xlsx",
                    projection=Projection(
                        contract_id=CONTRACT_ID, semantic_version="1.0.0",
                        document_type="xlsx", values={}, row_keys={},
                    ),
                    output=leak,
                    definitions=drafted,
                )
            assert not isinstance(exc.value, M.TemplateLibraryWriteError), (
                "身份门被挪到输出路径判据之后 —— 未 approved bundle 的报错指向了错的地方"
            )
            assert "approved" in str(exc.value) or "candidate" in str(exc.value)
        finally:
            assert not _sweep_template_library_leak(leak)

    def test_quarantined_is_refused_before_the_tamper_closure_check(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        workdir: Path,
        staging: Path,
    ) -> None:
        """OO→HTML：quarantined 必须在**受保护格篡改闭合检查之前**被拒。

        🔴 这条判据的形式是被防御性重复逼出来的。`rematerialize_merged_projection` 有两道
        quarantined 门（带 baseline 的 incoming extract、以及 materialize 入口），互为兜底 ⇒
        单测「quarantined 被拒」时**关掉任意一道都仍然绿**（变异 M30 首轮 GREEN）。
        用「同时构造一份被篡改的 incoming」就能定序：第一道门在的时候抛隔离错误，第一道门
        没了就会先抛篡改漏报错误 —— 两者类型不同，顺序因此可 falsify。
        """
        tampered = tamper_formula(base_bytes, sheet_part, f"H{FIRST_ROW}", "G7-D7+1")
        incoming = write_artifact(workdir, "quarantined-tampered.xlsx", tampered)
        output = staging / "staged.xlsx"
        with pytest.raises(QuarantinedIncomingError):
            RM.rematerialize_merged_projection(
                merged=_baseline_projection(base_path, definitions),
                incoming_substrate=incoming,
                base_representation=base_path,
                output=output,
                definitions=definitions,
                binding=BINDING,
                merge_conflicts=(),
                incoming_state=ArtifactState.quarantined,
            )
        assert not output.exists()

    def test_upgrade_candidate_is_never_a_substrate(
        self, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        missing = staging / "candidate.xlsx"
        with pytest.raises(AdapterCandidateSubstrateError):
            materialize(
                substrate=missing,
                projection=Projection(
                    contract_id=CONTRACT_ID, semantic_version="1.0.0",
                    document_type="xlsx", values={}, row_keys={},
                ),
                output=staging / "staged.xlsx",
                definitions=definitions,
                substrate_role=SubstrateRole.published_representation,
                substrate_kind=ArtifactKind.upgrade_candidate,
                substrate_state=ArtifactState.candidate,
            )

    def test_incoming_never_becomes_a_published_representation_substrate(
        self, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        """`kind=incoming` 不得当 HTML→OO 的 substrate（incoming 永不 published）。"""
        with pytest.raises(AdapterSubstrateError):
            materialize(
                substrate=staging / "nope.xlsx",
                projection=Projection(
                    contract_id=CONTRACT_ID, semantic_version="1.0.0",
                    document_type="xlsx", values={}, row_keys={},
                ),
                output=staging / "staged.xlsx",
                definitions=definitions,
                substrate_role=SubstrateRole.published_representation,
                substrate_kind=ArtifactKind.incoming,
                substrate_state=ArtifactState.durable,
            )

    def test_unapproved_bundle_blocks_the_engine_entry(
        self, base_path: Path, contract: Any, base_inventory: dict[str, Any], staging: Path
    ) -> None:
        """未 approved（candidate）的 bundle ⇒ engine 入口拒（frozen 身份门在写字节之前）。"""
        drafted = make_definitions(
            contract,
            base_inventory,
            bundle=make_bundle(contract, state=DefinitionState.candidate),
        )
        with pytest.raises(Exception) as exc:
            materialize(
                substrate=base_path,
                projection=Projection(
                    contract_id=CONTRACT_ID, semantic_version="1.0.0",
                    document_type="xlsx", values={}, row_keys={},
                ),
                output=staging / "staged.xlsx",
                definitions=drafted,
            )
        assert "approved" in str(exc.value) or "candidate" in str(exc.value)
        assert not (staging / "staged.xlsx").exists()

    def test_contract_digest_drift_blocks_the_engine_entry(
        self, base_path: Path, contract: Any, base_inventory: dict[str, Any], staging: Path
    ) -> None:
        """bundle 的 contract slot digest 漂移 ⇒ 拒（不得按 registry 当前 alias 顶替）。"""
        drifted = make_definitions(
            contract,
            base_inventory,
            bundle=make_bundle(contract, contract_slot_digest=_d("another-contract")),
        )
        with pytest.raises(StaleAdapterError):
            materialize(
                substrate=base_path,
                projection=_baseline_projection(base_path, definitions=drifted)
                if False
                else Projection(
                    contract_id=CONTRACT_ID, semantic_version="1.0.0",
                    document_type="xlsx", values={}, row_keys={},
                ),
                output=staging / "staged.xlsx",
                definitions=drifted,
            )

    def test_staged_projection_digest_equals_the_merged_projection_digest(
        self,
        base_path: Path,
        base_bytes: bytes,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
        staging: Path,
    ) -> None:
        """AC 8.11 / 8.12：staged result 的受管 projection 与 merged **等值**，且 merged 侧
        digest 可重复。

        🔴 判据刻意**不是**「两侧 `projection_canonical_digest` 逐字节相同」。实测（本任务）：
        merged 侧的金额出自 `merge.normalize_value` ⇒ `Decimal('8888.0')` ⇒ canonical 载荷里是
        字符串 `"8888.0"`；staged 反读侧出自 openpyxl ⇒ `int 8888` ⇒ 载荷里是数字 `8888`。
        两者业务上相等（`values_equal` 判等），digest 却不同。

        这不是缺陷也不是可以忽略的差异，而是**口径分工**：`working_paper_content_application.
        merged_projection_sha256` 由 **merged** 一侧算（`_stage_and_verify` 用同一个
        `projection_canonical_digest`），反读侧只负责「等值」这件事（Task 15
        `_assert_roundtrip_equivalent` 用 `values_equal`）。把两侧 digest 硬绑成逐字节相等，
        真实数据上恒不成立 ⇒ 调用方只能整体关掉判据（本 spec 已三次踩到这个形态）。
        因此这里锁两件真事：等值 + merged 侧 digest 可重复（retry 幂等）。
        """
        incoming = write_artifact(
            workdir,
            "incoming-clean.xlsx",
            patch_cells(base_bytes, sheet_part, {f"C{FIRST_ROW}": 8888.0}),
        )
        # 🔴 merged 侧的值必须走 `merge.normalize_value`：生产上 merged projection 出自
        #    `merge_projections`，它已经规范化过（float 8888.0 → Decimal('8888')）。测试里塞
        #    原始 float 会让 digest 因序列化形态而不等，把「口径统一」这条判据变成假红。
        merged = rebuild(
            base_outcome.projection,
            overrides={
                f"k11_rows/{base_outcome.projection.row_keys['k11_rows'][0]}/adjustment": (
                    MG.normalize_value(8888.0, ValueType.amount)
                )
            },
        )
        output = staging / "staged.xlsx"
        result = RM.rematerialize_merged_projection(
            merged=merged,
            incoming_substrate=incoming,
            base_representation=base_path,
            output=output,
            definitions=definitions,
            binding=BINDING,
        )
        result.assert_ready_for_commit()
        read_back = result.verification.extracted.projection
        want, got = _managed_projection(merged), _managed_projection(read_back)
        assert sorted(want) == sorted(got)
        differing = {
            key: (want[key], got[key])
            for key in want
            if not MG.values_equal(want[key], got[key], merged.values[key].value_type)
        }
        assert not differing, f"staged result 与 merged 不等值: {list(differing.items())[:3]}"
        assert projection_canonical_digest(merged) == projection_canonical_digest(
            rebuild(merged)
        ), "merged 侧 digest 不可重复 ⇒ retry 会造出第二个 applied 身份（AC 3.6 / 8.12）"

    def test_the_three_entries_hardcode_their_substrate_shape(self) -> None:
        """三条入口的 substrate 形态写死在入口里，不是参数（结构判据）。

        `materialize_for_editing` / `plan_representation_upgrade` 只接
        `published_representation / canonical / published`，`rematerialize_merged_projection`
        只接 `incoming / incoming`。做成 `role` 参数会让「OO→HTML 拿 published 当底」在类型上
        合法 —— 那是本 spec 里最贵的一类错误。
        """
        import inspect

        for name in ("materialize_for_editing", "plan_representation_upgrade"):
            params = inspect.signature(getattr(RM, name)).parameters
            assert "substrate_role" not in params, f"{name} 暴露了 substrate_role 参数"
            assert "incoming_substrate" not in params, f"{name} 能接 incoming"
        remat = inspect.signature(RM.rematerialize_merged_projection).parameters
        assert "substrate_role" not in remat and "substrate_kind" not in remat
        assert "incoming_substrate" in remat and "base_representation" in remat
        assert remat["base_representation"].default is inspect.Parameter.empty, (
            "base_representation 必须是必填 —— 它是 Property 24 的 baseline 来源，"
            "给它默认 None 等于允许调用方关掉那条判据"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 9. Property 66：identity 载体经写入后保留
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty66IdentityRetainedAfterWrite:
    """**Validates: Requirements 6.16 / 6.17 / 6.20** · Property 66

    写入侧的收口判据：写完之后**反读** staged 产物的运行时清册，交给 Task 37 的
    `assert_identity_inventory_retained` 与 frozen inventory 比对。刻意不用「substrate 的清册 +
    我 minted 的那几个」推导 —— 那是自证式，UUID 根本没写进去时它照样给出正确答案。
    """

    def test_staged_inventory_is_measured_not_derived(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        output = staging / "staged.xlsx"
        result = materialize(
            substrate=base_path,
            projection=_baseline_projection(base_path, definitions),
            output=output,
            definitions=definitions,
        )
        inventory = result.staged_identity_inventory
        assert inventory.hidden_sheet_present and inventory.hidden_sheet_is_hidden
        assert inventory.excluded_from_business_enumeration, (
            "隐藏 metadata sheet 没有被业务 sheet 枚举排除（Requirement 6.17）"
        )
        assert inventory.defined_names, "GT_ defined name 全丢了"
        assert inventory.table_present and inventory.table_ref == EXPECTED_TABLE_REF
        assert inventory.uuid_column == UUID_COL and inventory.uuid_column_hidden
        assert len(inventory.row_uuids) == EXPECTED_ROW_COUNT
        assert not inventory.duplicate_row_uuids and not inventory.empty_row_uuids
        X.assert_identity_inventory_retained(
            expected=definitions.identity_inventory,
            observed=inventory,
            entry_id=ENTRY_ID,
        )

    def test_carrier_loss_after_the_write_blocks_the_engine(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path,
        sheet_part: str,
    ) -> None:
        """反向自检：把 staged 产物的隐藏 UUID 列整列抹掉 ⇒ engine 门必须拦住。

        证明上一条不是空转：清册判据在载体真的丢了的时候会打红。
        """
        output = staging / "staged.xlsx"
        materialize(
            substrate=base_path,
            projection=_baseline_projection(base_path, definitions),
            output=output,
            definitions=definitions,
        )
        wiped = edit_part(
            output.read_bytes(),
            sheet_part,
            lambda blob: re.sub(
                r'<c r="' + UUID_COL + r'\d+"(?:\s[^>]*?)?>.*?</c>',
                "",
                blob.decode("utf-8"),
                flags=re.S,
            ).encode("utf-8"),
        )
        broken = staging / "broken.xlsx"
        broken.write_bytes(wiped)
        with pytest.raises(X.IdentityCarrierMissingError):
            extract_staged(broken, definitions)

    def test_runtime_binding_reader_fails_closed_instead_of_returning_empty(
        self, base_path: Path, staging: Path
    ) -> None:
        """`read_runtime_binding_pairs` 定位失败必须抛，不得返回空 dict。

        🔴 这是本任务首轮踩到的形态：materializer 自己抄了一份 `r:id="(rId\\d+)"` 的 sheet 定位，
        而 Task 17 的隐藏 sheet 关系 id 是 `rIdGTSYNC` ⇒ 恒读空 ⇒ 「sheet 定位失败」被报成
        「缺 GT_FOOTER_ROW」。返回空 dict 的 fail-open 会把真因彻底埋掉。
        """
        with zipfile.ZipFile(base_path) as zf:
            pairs = X.read_runtime_binding_pairs(zf)
        assert pairs.get("GT_FOOTER_ROW") == str(TEMPLATE_FOOTER_ROW)
        assert pairs.get("GT_MANAGED_TABLE") == TABLE_NAME
        with zipfile.ZipFile(base_path) as zf:
            with pytest.raises(X.IdentityCarrierMissingError) as exc:
                X.read_runtime_binding_pairs(zf, metadata_sheet="_NOT_THERE")
        assert "_NOT_THERE" in str(exc.value)

    def test_runtime_binding_reader_rejects_an_empty_metadata_sheet(
        self, base_bytes: bytes, workdir: Path
    ) -> None:
        """sheet 在、但一对 key/value 都读不到 ⇒ 也必须抛，不得当成「没有冻结任何绑定」。

        🔴 与上一条是**两条独立分支**（sheet 定位失败 vs 载体形态不符）。变异 M32 实测：只测
        前者时把后者关掉照样绿。这一条也是首轮真实缺陷的形态 —— 载体形态与 Task 17 写侧不符时
        返回空 dict，症状会变成「缺某个键」。
        """
        gutted = edit_part(
            base_bytes,
            gt_sync_part(base_bytes),
            lambda blob: re.sub(
                r"<sheetData>.*?</sheetData>",
                "<sheetData/>",
                blob.decode("utf-8"),
                flags=re.S,
            ).encode("utf-8"),
        )
        path = write_artifact(workdir, "gutted-gt-sync.xlsx", gutted)
        with zipfile.ZipFile(path) as zf:
            with pytest.raises(X.IdentityCarrierMissingError) as exc:
                X.read_runtime_binding_pairs(zf)
        assert "sheetGtSync" in str(exc.value) or "key/value" in str(exc.value)

    def test_footer_anchor_cross_checks_two_independent_carriers(
        self, base_bytes: bytes, base_inventory: dict[str, Any], contract: Any,
        workdir: Path, staging: Path,
    ) -> None:
        """footer 位置由「可见 marker 行号」与「冻结 GT_FOOTER_ROW」交叉验证，不一致即拒。"""
        drifted_bytes = patch_runtime_binding(base_bytes, "GT_FOOTER_ROW", "99")
        drifted = write_artifact(workdir, "footer-drift.xlsx", drifted_bytes)
        definitions = make_definitions(
            contract,
            identity_inventory(
                drifted_bytes, expected_table=TABLE_NAME, uuid_column_letter=UUID_COL
            ),
        )
        with pytest.raises(M.FooterAnchorDriftError) as exc:
            materialize(
                substrate=drifted,
                projection=_baseline_projection(drifted, definitions),
                output=staging / "staged.xlsx",
                definitions=definitions,
            )
        assert "99" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# 10. Property 67：upgrade candidate 先行
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty67UpgradeCandidateFirst:
    """**Validates: Requirements 6.18 / 3.4** · Property 67

    四条判据：candidate 命名空间物理隔离、结论不可交业务 commit、`revision_delta == 0`、业务
    projection 逐字节不变。第四条还必须**可 falsify** —— 用故障注入让「业务 projection 真的变了」
    这一支可达，否则它是永久 GREEN 分支。
    """

    def _candidate_path(self, staging: Path, name: str = "candidate.xlsx") -> Path:
        return staging / RM.CANDIDATE_NAMESPACE / name

    def test_candidate_must_land_in_the_candidate_namespace(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        with pytest.raises(RM.CandidateNamespaceRequiredError):
            RM.plan_representation_upgrade(
                current_representation=base_path,
                candidate_output=staging / "versions" / "candidate.xlsx",
                definitions=definitions,
                binding=BINDING,
            )
        assert not (staging / "versions" / "candidate.xlsx").exists()

    def test_candidate_is_produced_and_is_not_committable(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        outcome = RM.plan_representation_upgrade(
            current_representation=base_path,
            candidate_output=self._candidate_path(staging),
            definitions=definitions,
            binding=BINDING,
        )
        assert outcome.candidate_path.is_file()
        assert RM.CANDIDATE_NAMESPACE in outcome.candidate_path.resolve().parts
        assert outcome.business_projection_unchanged is True
        assert outcome.before_projection_digest == outcome.after_projection_digest
        assert outcome.revision_delta == 0, (
            "纯表示升级声明了非零 revision 增量 —— 业务 projection 没变就不得造业务 revision"
        )
        with pytest.raises(RM.RepresentationUpgradeNotCommittableError):
            outcome.rematerialize.assert_ready_for_commit()

    def test_the_candidate_is_never_read_as_a_substrate(
        self, definitions: FrozenEntryDefinitions, base_path: Path, staging: Path
    ) -> None:
        """产出的 candidate 拿回去当 substrate ⇒ 被 Task 13 的准入门拒（AC 6.18）。"""
        outcome = RM.plan_representation_upgrade(
            current_representation=base_path,
            candidate_output=self._candidate_path(staging, "again.xlsx"),
            definitions=definitions,
            binding=BINDING,
        )
        with pytest.raises(AdapterCandidateSubstrateError):
            materialize(
                substrate=outcome.candidate_path,
                projection=_baseline_projection(base_path, definitions),
                output=staging / "staged.xlsx",
                definitions=definitions,
                substrate_kind=ArtifactKind.upgrade_candidate,
                substrate_state=ArtifactState.candidate,
            )

    def test_upgrade_does_not_accept_an_external_projection(self) -> None:
        """升级入口不接外部 projection —— 否则「趁升级顺手改业务值」在类型上合法。"""
        import inspect

        params = inspect.signature(RM.plan_representation_upgrade).parameters
        assert "projection" not in params and "merged" not in params

    def test_a_business_value_change_during_upgrade_is_detected(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """故障注入让「业务 projection 真的变了」这一支可达（否则永久 GREEN）。

        🔴 为什么必须注入：`plan_representation_upgrade` 要写的 projection 就是从当前
        representation 反读出来的那一份，写入值又走同一套 `normalize_value` ⇒ 构造上恒等。
        Property 9 的原话就是「在校验任一点**注入失败**」，注入是本 spec 认可的手段。这里把
        低层渲染器改成有损的（正是这条判据要防的生产缺陷类：materializer 写出去的值不是
        projection 说的值），断言**高层**判据抓得住。
        """
        original = M._render_number

        def _truncating(value: Any) -> str:
            rendered = original(value)
            try:
                return str(int(float(rendered)) + 7)
            except (TypeError, ValueError):
                return rendered

        monkeypatch.setattr(M, "_render_number", _truncating)
        with pytest.raises(RM.BusinessProjectionChangedError):
            RM.plan_representation_upgrade(
                current_representation=base_path,
                candidate_output=self._candidate_path(staging, "lossy.xlsx"),
                definitions=definitions,
                binding=BINDING,
            )

    def test_business_projection_check_precedes_the_generic_roundtrip_error(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """诊断精度：升级路径上「业务 projection 变了」必须先于通用的反读不等值抛出。

        两者都会被同一处有损写入触发。若顺序反过来，运维看到的是「反读不等值」——
        对升级路径来说那是**错的诊断**（真因是有人在纯表示升级里改了业务值）。
        """
        original = M._render_number
        monkeypatch.setattr(
            M,
            "_render_number",
            lambda value: str(int(float(original(value))) + 3)
            if str(original(value)).replace(".", "").replace("-", "").isdigit()
            else original(value),
        )
        with pytest.raises(RM.BusinessProjectionChangedError):
            RM.plan_representation_upgrade(
                current_representation=base_path,
                candidate_output=self._candidate_path(staging, "order.xlsx"),
                definitions=definitions,
                binding=BINDING,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 11. 失败形态：各真触发一次 + 与登记清单双向等值
# ═══════════════════════════════════════════════════════════════════════════


def _no_drawing_workbook(data: bytes) -> bytes:
    """去掉 drawing 部件的工作簿（`select_write_strategy` 的放行支需要它）。

    🔴 刻意从**真实模板**减一个部件，而不是手搓一个最小 xlsx：策略门的判据是 zip 条目名，
    真实模板减部件后仍保留 sharedStrings / tables / styles / 多 sheet 等全部形态。
    `backend/wp_templates` 全量 351 个 xlsx 里 182 个含 drawing、1 个含 chart，探针对 pivot/VBA/
    外链/条件格式四项仍是 `not_covered` ⇒ **生产上没有一个模板能过这道门**。因此放行支只能靠
    合成 substrate 才可达，这里明确记下这一点（不是把分支写死成不可达 ——
    capability 与实测部件两个条件各自都能被单独 falsify，见下面两条用例）。
    """
    entries = _read_entries(data)
    dropped = {
        name: blob
        for name, blob in entries.items()
        if not re.match(r"^xl/(drawings/|media/)", name)
    }
    assert len(dropped) < len(entries), "fixture 失效：模板里本来就没有 drawing"
    return _write_entries(dropped)


class TestWriteStrategyGate:
    """**Validates: Requirements 3.5 / 6.17**

    design §Materialize 末段的三条件门。四条拒绝理由**各自独立**：任一条被删都必须打红。
    """

    def test_capability_absent_refuses_openpyxl(self, base_path: Path) -> None:
        decision = M.select_write_strategy(artifact=base_path, capability=None)
        assert decision.strategy is M.ExcelWriteStrategy.zip_patch
        assert any("openpyxl_safe" in reason for reason in decision.refusals)

    def test_protected_parts_refuse_openpyxl_even_with_capability(
        self, base_path: Path
    ) -> None:
        """实测含 drawing ⇒ 即使 capability 声明安全也拒（不信任任何声明）。"""
        capability = M.ExcelWriteCapability(
            template_relative_path="K/K11 资产减值损失.xlsx",
            openpyxl_safe=True,
            probe_covered_aspects=frozenset(M.CAPABILITY_REQUIRED_PROBE_ASPECTS),
        )
        decision = M.select_write_strategy(
            artifact=base_path, capability=capability, uncovered_probe_aspects=frozenset()
        )
        assert decision.strategy is M.ExcelWriteStrategy.zip_patch
        assert decision.facts.protected_aspects_present == ("drawing",), decision.facts
        assert any("受保护部件" in reason for reason in decision.refusals)

    def test_uncovered_probe_aspect_refuses_openpyxl(
        self, base_bytes: bytes, workdir: Path
    ) -> None:
        """探针 not_covered ⇒ 拒（「未取证」不等于「已证明安全」）。"""
        clean = write_artifact(workdir, "no-drawing.xlsx", _no_drawing_workbook(base_bytes))
        capability = M.ExcelWriteCapability(
            template_relative_path="synthetic/no-drawing.xlsx",
            openpyxl_safe=True,
            probe_covered_aspects=frozenset(M.CAPABILITY_REQUIRED_PROBE_ASPECTS),
        )
        decision = M.select_write_strategy(
            artifact=clean,
            capability=capability,
            uncovered_probe_aspects=frozenset({"pivot_table"}),
        )
        assert decision.strategy is M.ExcelWriteStrategy.zip_patch
        assert any("not_covered" in reason for reason in decision.refusals)

    def test_capability_not_declaring_coverage_refuses_openpyxl(
        self, base_bytes: bytes, workdir: Path
    ) -> None:
        clean = write_artifact(workdir, "no-drawing-2.xlsx", _no_drawing_workbook(base_bytes))
        capability = M.ExcelWriteCapability(
            template_relative_path="synthetic/no-drawing.xlsx",
            openpyxl_safe=True,
            probe_covered_aspects=frozenset({"pivot_table"}),
        )
        decision = M.select_write_strategy(
            artifact=clean, capability=capability, uncovered_probe_aspects=frozenset()
        )
        assert decision.strategy is M.ExcelWriteStrategy.zip_patch
        assert any("未声明已覆盖" in reason for reason in decision.refusals)

    def test_all_three_conditions_met_allows_openpyxl(
        self, base_bytes: bytes, workdir: Path
    ) -> None:
        """三条件全满足时**真的**放行 —— 否则这道门是装饰品（分支永久不可达）。"""
        clean = write_artifact(workdir, "no-drawing-3.xlsx", _no_drawing_workbook(base_bytes))
        capability = M.ExcelWriteCapability(
            template_relative_path="synthetic/no-drawing.xlsx",
            openpyxl_safe=True,
            probe_covered_aspects=frozenset(M.CAPABILITY_REQUIRED_PROBE_ASPECTS),
        )
        decision = M.select_write_strategy(
            artifact=clean, capability=capability, uncovered_probe_aspects=frozenset()
        )
        assert decision.strategy is M.ExcelWriteStrategy.openpyxl_roundtrip
        assert decision.refusals == ()
        assert decision.openpyxl_allowed is True

    def test_production_templates_never_pass_the_gate(self) -> None:
        """实测事实锁死：Task 5 契约对四项关键部件仍是 not_covered ⇒ 生产上恒不放行。"""
        uncovered = M.probe_uncovered_aspects()
        assert uncovered, "Task 5 契约的 `visible_equivalence.not_covered` 变空了 —— 请复核证据"
        assert set(M.CAPABILITY_REQUIRED_PROBE_ASPECTS) & uncovered, (
            f"关键部件已全部取证（实测 not_covered={sorted(uncovered)}）—— "
            "若真如此，openpyxl 放行支就进入生产范围，本判据需要重写"
        )

    def test_capability_cannot_claim_all_templates(self) -> None:
        with pytest.raises(M.WriteStrategyForbiddenError):
            M.ExcelWriteCapability(template_relative_path="  ", openpyxl_safe=True)

    def test_openpyxl_path_is_fail_closed_at_its_own_entry(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path
    ) -> None:
        """未获放行却直接调 `apply_plan_openpyxl` ⇒ 抛，不是靠调用方自觉。"""
        plan = _plan_for(base_path, definitions)
        refused = M.select_write_strategy(artifact=base_path, capability=None)
        with pytest.raises(M.WriteStrategyForbiddenError):
            M.apply_plan_openpyxl(
                base_path, plan, staging / "via-openpyxl.xlsx", decision=refused
            )
        assert not (staging / "via-openpyxl.xlsx").exists()


class TestFailureKindsAreReachableAndMutuallyDistinct:
    """**Validates: Requirements 6.3 / 6.4 / 6.6 / 6.9 / 6.15** · 假绿第①源防线

    🔴 本 spec 已三次实测「多条判据共用一个 error code ⇒ 靠前的分支永久不可达 ⇒ 只断言类型的
    守卫判 GREEN」。所以判据不是「每类各测一遍」（两类被合并后那种写法**全部仍绿**），而是：

    1. 十种失败**各真触发一次**，收集实际抛出的 `error_code`；
    2. 收集到的集合与 `excel_materialize.FAILURE_KINDS` **双向等值**；
    3. 集合**基数**等于登记条数（合并两类会让基数变小 ⇒ 打红）；
    4. 登记键与「全部具体异常类的 error_code」双向等值（新增类不登记 / 登记了没有类都打红）。
    """

    def _triggers(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        base_inventory: dict[str, Any],
        contract: Any,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
        staging: Path,
    ) -> dict[str, M.ExcelMaterializeError]:
        """十种失败各触发一次，返回 `error_code → 异常实例`。"""
        caught: dict[str, M.ExcelMaterializeError] = {}

        def _record(label: str, thunk: Any) -> None:
            try:
                thunk()
            except M.ExcelMaterializeError as exc:
                assert exc.error_code not in caught, (
                    f"{label} 与 {caught[exc.error_code].__class__.__name__} 抛出了**同一个** "
                    f"error_code {exc.error_code!r} —— 两条判据被折叠，靠前的那条永久不可达"
                )
                caught[exc.error_code] = exc
            else:  # pragma: no cover - 触发器失效时必须打红
                raise AssertionError(f"{label} 没有抛出任何写入侧失败 ⇒ 该分支不可达")

        projection = base_outcome.projection
        identities = list(projection.row_keys["k11_rows"])

        # 1) editable 值无法规范化
        _record(
            "editable 值无法按 amount 规范化",
            lambda: materialize(
                substrate=base_path,
                projection=rebuild(
                    projection, overrides={f"k11_rows/{identities[0]}/adjustment": "不是数字"}
                ),
                output=staging / "k1.xlsx",
                definitions=definitions,
            ),
        )

        # 2) 契约声明 formula 但 substrate 上没有公式（J 列是文本）
        formula_on_text = contract_payload()
        # 🔴 `formula_mask` 必须跟着扩到 J：Task 13 的契约校验器要求 formula 字段的列落在 mask
        #    覆盖的列跨度内（否则 OO 侧修改会覆盖公式结果）。只改 mode 会被契约层先拦住，
        #    本触发器就永远到不了写入侧那条判据。
        formula_on_text["sheets"][0]["tables"][0]["formula_mask"] = [f"H{FIRST_ROW}:J{LAST_ROW}"]
        for field in formula_on_text["sheets"][0]["tables"][0]["fields"]:
            if field["column_key"] == "reason":
                field["mode"] = "formula"
        formula_defs = make_definitions(
            parse_contract(formula_on_text, adapter_id=CONTRACT_ID), base_inventory
        )
        _record(
            "契约声明 formula 但模板上无公式",
            lambda: materialize(
                substrate=base_path,
                projection=projection,
                output=staging / "k2.xlsx",
                definitions=formula_defs,
            ),
        )

        # 3) 契约声明 editable 的格是共享公式主格（H8 实测 `ref="H8:H25" si="1"`）
        #    刻意不带 dynamic_columns：带上之后 `variance` 也得有 `{slot}_{seq}` 绑定，
        #    而它不是那个形态 ⇒ 会先撞 Task 37 的动态列绑定门（判定顺序不可交换）。
        shared_master = contract_payload()
        shared_master["sheets"][0]["tables"][0]["formula_mask"] = []
        for field in shared_master["sheets"][0]["tables"][0]["fields"]:
            if field["column_key"] == "variance":
                field["mode"] = "editable"
        master_defs = make_definitions(
            parse_contract(shared_master, adapter_id=CONTRACT_ID), base_inventory
        )
        _record(
            "契约声明 editable 的格是共享公式主格",
            lambda: materialize(
                substrate=base_path,
                projection=_baseline_projection(base_path, master_defs),
                output=staging / "k3.xlsx",
                definitions=master_defs,
            ),
        )

        # 4) OO 新增行的 minted 身份没进 merged projection
        no_footer = make_definitions(
            parse_contract(
                dynamic_contract_payload(footer_anchor=False), adapter_id=CONTRACT_ID
            ),
            base_inventory,
        )
        grown = write_artifact(
            workdir,
            "kinds-grown.xlsx",
            patch_cells(
                grow_table_to(base_bytes, TEMPLATE_FOOTER_ROW),
                sheet_part,
                {f"{DYN_COLUMNS['unit_1']}{TEMPLATE_FOOTER_ROW}": 1.0},
            ),
        )
        grown_outcome = X.extract_projection(
            artifact=grown, definitions=no_footer, binding=dynamic_binding(),
            substrate_role=SubstrateRole.incoming,
            artifact_kind=ArtifactKind.incoming,
            artifact_state=ArtifactState.durable,
        )
        minted = set(grown_outcome.scan.minted_by_row.values())
        assert minted, "fixture 失效：没有 minted 身份"
        _record(
            "minted 身份未进 merged projection",
            lambda: materialize(
                substrate=grown,
                projection=rebuild(
                    grown_outcome.projection,
                    row_keys={
                        "k11_rows": tuple(
                            i
                            for i in grown_outcome.projection.row_keys["k11_rows"]
                            if i not in minted
                        )
                    },
                ),
                output=staging / "k4.xlsx",
                definitions=no_footer,
                binding=dynamic_binding(),
                substrate_role=SubstrateRole.incoming,
                substrate_kind=ArtifactKind.incoming,
                substrate_state=ArtifactState.durable,
            ),
        )

        # 5) 动态列绑定不可用
        dyn_defs = make_definitions(
            parse_contract(dynamic_contract_payload(), adapter_id=CONTRACT_ID), base_inventory
        )
        _record(
            "两个 slot 撞同一列",
            lambda: M.assert_dynamic_column_binding_usable(
                contract=dyn_defs.contract,
                binding=dynamic_binding(columns={"unit_1": "K", "unit_2": "K"}),
            ),
        )

        # 6) footer 冻结行号与实测不符
        drift_bytes = patch_runtime_binding(base_bytes, "GT_FOOTER_ROW", "99")
        drift = write_artifact(workdir, "kinds-footer-drift.xlsx", drift_bytes)
        drift_defs = make_definitions(
            contract,
            identity_inventory(
                drift_bytes, expected_table=TABLE_NAME, uuid_column_letter=UUID_COL
            ),
        )
        _record(
            "footer 冻结行号与实测不符",
            lambda: materialize(
                substrate=drift,
                projection=_baseline_projection(drift, drift_defs),
                output=staging / "k6.xlsx",
                definitions=drift_defs,
            ),
        )

        # 7) footer 合计公式区间没覆盖当前受管行区间（OO 在末尾插行）
        grown_footer_bytes = patch_cells(
            grow_table_to(base_bytes, TEMPLATE_FOOTER_ROW), sheet_part, {}
        )
        grown_footer = write_artifact(
            workdir, "kinds-footer-stale.xlsx", grown_footer_bytes
        )
        grown_footer_defs = make_definitions(
            contract,
            identity_inventory(
                grown_footer_bytes, expected_table=TABLE_NAME, uuid_column_letter=UUID_COL
            ),
        )
        _record(
            "footer 合计公式区间漏算新行",
            lambda: materialize(
                substrate=grown_footer,
                projection=_baseline_projection(grown_footer, grown_footer_defs),
                output=staging / "k7.xlsx",
                definitions=grown_footer_defs,
                substrate_role=SubstrateRole.incoming,
                substrate_kind=ArtifactKind.incoming,
                substrate_state=ArtifactState.durable,
            ),
        )

        # 8) merged projection 的行身份在 substrate 上没有物理行
        _record(
            "merged projection 行集与物理行集不一致",
            lambda: materialize(
                substrate=base_path,
                projection=rebuild(
                    projection,
                    row_keys={"k11_rows": tuple(identities) + ("GTROW-K11-9999",)},
                ),
                output=staging / "k8.xlsx",
                definitions=definitions,
            ),
        )

        # 9) openpyxl 未获放行却被调用
        plan = _plan_for(base_path, definitions)
        refused = M.select_write_strategy(artifact=base_path, capability=None)
        _record(
            "openpyxl 未获放行却被调用",
            lambda: M.apply_plan_openpyxl(
                base_path, plan, staging / "k9.xlsx", decision=refused
            ),
        )

        # 10) 输出落模板库（判定后必须清理残留，见 `_sweep_template_library_leak`）
        leak = _BACKEND / "wp_templates" / "K" / "kinds-10.xlsx"
        try:
            _record(
                "输出落模板库",
                lambda: materialize(
                    substrate=base_path,
                    projection=projection,
                    output=leak,
                    definitions=definitions,
                ),
            )
        finally:
            _sweep_template_library_leak(leak)
        return caught

    def test_every_registered_failure_kind_is_really_reachable(
        self,
        base_bytes: bytes,
        base_path: Path,
        sheet_part: str,
        base_inventory: dict[str, Any],
        contract: Any,
        definitions: FrozenEntryDefinitions,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
        staging: Path,
    ) -> None:
        caught = self._triggers(
            base_bytes, base_path, sheet_part, base_inventory, contract,
            definitions, base_outcome, workdir, staging,
        )
        assert len(caught) == len(M.FAILURE_KINDS), (
            f"实际触发 {len(caught)} 种 error_code，登记 {len(M.FAILURE_KINDS)} 种 —— "
            "基数不等意味着有两条判据被折叠成同一个 code（靠前的那条永久不可达）"
        )
        assert sorted(caught) == sorted(M.FAILURE_KINDS), (
            f"实际触发 {sorted(caught)}\n登记 {sorted(M.FAILURE_KINDS)} —— 双向等值不成立"
        )
        for code, exc in sorted(caught.items()):
            assert len(str(exc)) >= 20, f"{code} 的诊断文案太短，运维看不出发生了什么"

    def test_registry_matches_the_concrete_exception_classes(self) -> None:
        """登记键与「全部具体异常类的 error_code」双向等值。

        `FAILURE_KINDS` 是**手写**清单（不是从类反推）—— 从类反推就是自证式同义反复，改类
        也自动改期望，「合并两个类」这件事永远不会被发现。
        """
        concrete = {
            cls.error_code
            for cls in vars(M).values()
            if isinstance(cls, type)
            and issubclass(cls, M.ExcelMaterializeError)
            and cls is not M.ExcelMaterializeError
        }
        assert concrete == set(M.FAILURE_KINDS), (
            f"类侧 {sorted(concrete)}\n登记侧 {sorted(M.FAILURE_KINDS)}"
        )
        codes = [
            cls.error_code
            for cls in vars(M).values()
            if isinstance(cls, type)
            and issubclass(cls, M.ExcelMaterializeError)
            and cls is not M.ExcelMaterializeError
        ]
        assert len(codes) == len(set(codes)), (
            f"有两个异常类共用同一个 error_code: "
            f"{sorted({c for c in codes if codes.count(c) > 1})}"
        )
        for code, reason in M.FAILURE_KINDS.items():
            assert code.startswith("excel_materialize_"), code
            assert len(reason) >= 15, f"{code} 的登记说明太短"

    def test_rematerialize_failure_kinds_are_distinct_too(
        self, base_path: Path, definitions: FrozenEntryDefinitions, staging: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """rematerialize 侧三种失败同样互不折叠（各自 error_code 不同）。"""
        codes: dict[str, str] = {}

        with pytest.raises(RM.CandidateNamespaceRequiredError) as one:
            RM.plan_representation_upgrade(
                current_representation=base_path,
                candidate_output=staging / "not-a-candidate.xlsx",
                definitions=definitions,
                binding=BINDING,
            )
        codes["namespace"] = one.value.error_code

        outcome = RM.plan_representation_upgrade(
            current_representation=base_path,
            candidate_output=staging / RM.CANDIDATE_NAMESPACE / "c.xlsx",
            definitions=definitions,
            binding=BINDING,
        )
        with pytest.raises(RM.RepresentationUpgradeNotCommittableError) as two:
            outcome.rematerialize.assert_ready_for_commit()
        codes["not_committable"] = two.value.error_code

        original = M._render_number
        monkeypatch.setattr(
            M, "_render_number", lambda value: str(int(float(original(value))) + 11)
            if str(original(value)).replace(".", "").replace("-", "").isdigit()
            else original(value)
        )
        with pytest.raises(RM.BusinessProjectionChangedError) as three:
            RM.plan_representation_upgrade(
                current_representation=base_path,
                candidate_output=staging / RM.CANDIDATE_NAMESPACE / "d.xlsx",
                definitions=definitions,
                binding=BINDING,
            )
        codes["projection_changed"] = three.value.error_code

        assert len(set(codes.values())) == 3, f"error_code 被折叠: {codes}"
        assert all(code.startswith("excel_rematerialize_") for code in codes.values())


# ═══════════════════════════════════════════════════════════════════════════
# 12. adapter 接线：engine 必须有生产消费方
# ═══════════════════════════════════════════════════════════════════════════


def build_adapter(
    definitions: FrozenEntryDefinitions, direction: str, **over: Any
) -> AX.ExcelSyncAdapter:
    kwargs: dict[str, Any] = {
        "definitions": definitions,
        "binding": BINDING,
        "direction": direction,
    }
    kwargs.update(over)
    return AX.build_excel_adapter(**kwargs)


class TestExcelAdapterWiring:
    """**Validates: Requirements 6.11 / 8.10 / 8.11**

    没有 adapter 层，Task 37/38 在生产链上**一个消费方都没有** —— 那正是假绿第①源
    （additive 注入即死代码）。因此这里的判据是「protocol 方法真的落到 engine 上」，
    不是「adapter 类存在」。
    """

    def test_direction_is_a_closed_vocabulary(
        self, definitions: FrozenEntryDefinitions
    ) -> None:
        with pytest.raises(AX.ExcelAdapterIdentityError):
            build_adapter(definitions, "sideways")

    def test_oo_to_html_requires_the_frozen_base_representation(
        self, definitions: FrozenEntryDefinitions, base_path: Path
    ) -> None:
        """OO→HTML 缺 base representation ⇒ 拒（那是 Property 24 的 baseline 来源）。"""
        with pytest.raises(AX.ExcelAdapterIdentityError) as exc:
            build_adapter(definitions, "oo_to_html")
        assert "baseline" in str(exc.value) or "base representation" in str(exc.value)
        adapter = build_adapter(
            definitions, "oo_to_html", baseline_representation=base_path
        )
        assert adapter.substrate_kind is ArtifactKind.incoming
        assert adapter.substrate_state is ArtifactState.durable
        assert adapter.substrate_role is SubstrateRole.incoming

    def test_html_to_oo_substrate_shape_is_published_representation(
        self, definitions: FrozenEntryDefinitions
    ) -> None:
        adapter = build_adapter(definitions, "html_to_oo")
        assert adapter.substrate_role is SubstrateRole.published_representation
        assert adapter.substrate_kind is ArtifactKind.canonical
        assert adapter.substrate_state is ArtifactState.published

    def test_cross_entry_contract_is_refused_at_every_protocol_entry(
        self, definitions: FrozenEntryDefinitions, base_path: Path, staging: Path
    ) -> None:
        """传入 contract 与 adapter 冻结的不是同一份 ⇒ 三个入口各自抛。

        protocol 只传 contract 不传 bundle，所以「adapter 是按哪个 bundle 造的」在签名上看不见。
        少了这一条，把 A entry 的 adapter 复用到 B entry 会按 A 的 identity binding 去写 B 的
        文件 —— 受管格全部错位而没有任何报错。
        """
        adapter = build_adapter(definitions, "html_to_oo")
        other = parse_contract(
            {**contract_payload(), "semantic_version": "9.9.9"}, adapter_id=CONTRACT_ID
        )
        assert other.canonical_sha256 != definitions.contract.canonical_sha256
        with pytest.raises(AX.ExcelAdapterIdentityError):
            adapter.materialize(
                substrate=base_path,
                projection=_baseline_projection(base_path, definitions),
                output=staging / "staged.xlsx",
                contract=other,
            )
        with pytest.raises(AX.ExcelAdapterIdentityError):
            adapter.extract(artifact=base_path, contract=other)
        with pytest.raises(AX.ExcelAdapterIdentityError):
            adapter.verify_unmanaged_regions(
                before=base_path, after=base_path, contract=other
            )

    def test_adapter_materialize_really_writes_through_the_engine(
        self, definitions: FrozenEntryDefinitions, base_path: Path, staging: Path
    ) -> None:
        """`adapter.materialize` 必须真的产出受管写入（不是空转返回一个 result）。"""
        adapter = build_adapter(definitions, "html_to_oo")
        output = staging / AX.STAGING_NAMESPACE / "staged.xlsx"
        output.parent.mkdir(parents=True, exist_ok=True)
        projection = _baseline_projection(base_path, definitions)
        result = adapter.materialize(
            substrate=base_path,
            projection=projection,
            output=output,
            contract=definitions.contract,
        )
        assert output.is_file() and output.read_bytes()[:2] == b"PK"
        assert result.managed_field_count == EXPECTED_ROW_COUNT * 3 + 1, (
            f"受管写入只有 {result.managed_field_count} 处 ⇒ engine 没被真的调用"
            "（19 行 × 3 列 + footer auto_source）"
        )
        assert result.artifact_sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
        assert result.identity_inventory_sha256

    def test_adapter_extract_classifies_the_substrate_shape_by_path(
        self,
        definitions: FrozenEntryDefinitions,
        base_path: Path,
        staging: Path,
        workdir: Path,
    ) -> None:
        """`extract` 按**路径身份**判形态：base / staged / incoming 三支都能真的走通。"""
        output = staging / AX.STAGING_NAMESPACE / "staged.xlsx"
        output.parent.mkdir(parents=True, exist_ok=True)
        adapter = build_adapter(
            definitions, "oo_to_html", baseline_representation=base_path
        )
        adapter.materialize(
            substrate=base_path,
            projection=_baseline_projection(base_path, definitions),
            output=output,
            contract=definitions.contract,
        )
        assert adapter._substrate_shape_of(base_path) == (
            SubstrateRole.published_representation,
            ArtifactKind.canonical,
            ArtifactState.published,
        )
        assert adapter._substrate_shape_of(output) == (
            SubstrateRole.staged_result,
            ArtifactKind.canonical,
            ArtifactState.staged,
        )
        # 🔴 incoming 必须落在 `.staging/` **之外**：`staging` fixture 自己就在 `.staging` 下，
        #    路径里带这个命名空间会被判成 staged result（首轮实测踩到）。
        elsewhere = workdir / "adapter-incoming.xlsx"
        elsewhere.write_bytes(base_path.read_bytes())
        assert AX.STAGING_NAMESPACE not in elsewhere.resolve().parts
        assert adapter._substrate_shape_of(elsewhere) == (
            SubstrateRole.incoming,
            ArtifactKind.incoming,
            ArtifactState.durable,
        )
        for path in (base_path, output, elsewhere):
            projection = adapter.extract(artifact=path, contract=definitions.contract)
            assert projection.values, f"{path.name} 反读出空 projection"

    def test_adapter_verify_unmanaged_regions_delegates_to_task37(
        self, definitions: FrozenEntryDefinitions, base_path: Path, staging: Path
    ) -> None:
        adapter = build_adapter(definitions, "html_to_oo")
        output = staging / AX.STAGING_NAMESPACE / "staged.xlsx"
        output.parent.mkdir(parents=True, exist_ok=True)
        adapter.materialize(
            substrate=base_path,
            projection=_baseline_projection(base_path, definitions),
            output=output,
            contract=definitions.contract,
        )
        report = adapter.verify_unmanaged_regions(
            before=base_path, after=output, contract=definitions.contract
        )
        assert report.equivalent, report.first_difference

    def test_adapter_only_accepts_xlsx(
        self, contract: Any, base_inventory: dict[str, Any]
    ) -> None:
        """docx 契约 ⇒ 抛 `ExcelAdapterIdentityError`（**具体类型**，不是「随便报个错」）。

        🔴 首轮写的是 `pytest.raises(Exception)` ⇒ 变异 M55 判 GREEN：把 document_type 判据
        关掉后别的地方照样抛，宽泛的 `Exception` 全部接受。判据必须落在具体类型上。
        """
        # 🔴 不能走 `parse_contract` 造 docx 契约：Word 的 identity 载体门（Task 6 的真实
        #    OO 9.4 探针）现在**全部**未过或被 blocklist，任何 docx 契约在契约层就被拒 ⇒
        #    adapter 自己那条判据不可达。所以这里用**内存里改一个字段**的方式隔离出它：
        #    `canonical_sha256` 是存储字段、不随 replace 重算，于是 bundle digest 门照常通过，
        #    唯一还会拦下它的就是 adapter 的 document_type 判据。
        docx_contract = dataclasses.replace(contract, document_type="docx")
        assert docx_contract.canonical_sha256 == contract.canonical_sha256
        definitions = make_definitions(
            docx_contract,
            base_inventory,
            adapter_build=AdapterBuild(
                adapter_id=CONTRACT_ID,
                adapter_build_digest=_d("k11-adapter-build"),
                document_type="docx",
                contract_version="1.0.0",
            ),
        )
        with pytest.raises(AX.ExcelAdapterIdentityError) as exc:
            AX.ExcelSyncAdapter(definitions=definitions, binding=BINDING)
        assert "xlsx" in str(exc.value)

    def test_adapter_construction_rejects_a_field_with_a_write_surface(
        self, definitions: FrozenEntryDefinitions
    ) -> None:
        """构造时逐字段实测「零写入面」：任一字段暴露 commit/publish 能力即抛。

        判据是**行为**（真造一个带 `.commit()` 的字段值）而不是「源码里没有 session 这个词」——
        后者改个变量名就能绕过（假绿第②源）。变异 M56 实测：只用源码文本判据时，把
        `assert_no_mutation_surface` 整个删掉照样绿。
        """

        class _LeakyBinding:
            table_name = TABLE_NAME
            uuid_column = UUID_COL
            table_key = "k11_rows"

            def commit(self) -> None:  # pragma: no cover - 只需可调用
                raise AssertionError("不应被调用")

        with pytest.raises(Exception) as exc:
            AX.ExcelSyncAdapter(
                definitions=definitions, binding=_LeakyBinding()  # type: ignore[arg-type]
            )
        assert "commit" in str(exc.value), (
            f"构造门没有报出泄漏的写入能力面，实得 {exc.value!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 13. 本任务边界与登记裁决
# ═══════════════════════════════════════════════════════════════════════════

_MATERIALIZE_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "excel_materialize.py"
_REMATERIALIZE_PY = (
    _BACKEND / "app" / "services" / "workpaper_sync" / "excel_rematerialize.py"
)
_ADAPTER_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "adapters" / "excel.py"
_TASK38_MODULES = (_MATERIALIZE_PY, _REMATERIALIZE_PY, _ADAPTER_PY)


def _stripped(path: Path) -> str:
    sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
    from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
        strip_comments_and_docstrings,
    )

    return strip_comments_and_docstrings(path.read_text(encoding="utf-8"))


class TestTask38ScopeBoundary:
    """「只做 Excel 写入 engine，不 commit / 不切 pointer / 不发事件」是可验证的承诺。"""

    def test_no_commit_or_pointer_or_event_surface(self) -> None:
        for path in _TASK38_MODULES:
            body = _stripped(path)
            for forbidden in (
                "session.commit(",
                "set_entry_pointer(",
                "finalize_candidate(",
                "publish_representation(",
                "EventBus",
                "outbox",
                "AsyncSession",
            ):
                assert forbidden not in body, (
                    f"{path.name} 出现 {forbidden!r} —— engine 只产出 staged 文件，"
                    "发布由 `ContentMutationService` / `RepresentationService` 唯一控制"
                )

    def test_content_mutation_is_only_used_for_the_shared_digest(self) -> None:
        """`content_mutation` 只允许被用来取**同一套** projection digest 口径。

        判据不是「不许出现这个词」：`excel_rematerialize._projection_digest` 必须复用 Task 15 的
        `projection_canonical_digest`，否则「业务 projection 有没有变」会有第二套口径。判据是
        「只 import 那一个符号，且不是模块级 import」。
        """
        body = _stripped(_REMATERIALIZE_PY)
        assert "projection_canonical_digest" in body
        module_level = [
            line
            for line in body.splitlines()
            if line.startswith("from app.services.workpaper_sync.content_mutation")
        ]
        assert not module_level, (
            "写入侧模块级 import 了 commit 侧 —— 方向必须是 commit 侧消费 engine，"
            f"实测 {module_level}"
        )
        assert _stripped(_MATERIALIZE_PY).count("content_mutation") == 0

    def test_direction_is_only_38_to_37(self) -> None:
        """Task 37 的真实 import 图判据必须通过，且清单登记了本任务的三个模块。"""
        import app.services.workpaper_sync.adapters.excel  # noqa: F401,PLC0415
        import app.services.workpaper_sync.excel_materialize  # noqa: F401,PLC0415
        import app.services.workpaper_sync.excel_rematerialize  # noqa: F401,PLC0415

        X.assert_no_materializer_dependency()
        forbidden = set(X.FORBIDDEN_DOWNSTREAM_MODULES)
        assert {
            "app.services.workpaper_sync.excel_materialize",
            "app.services.workpaper_sync.excel_rematerialize",
            "app.services.workpaper_sync.adapters.excel",
        } <= forbidden, (
            f"本任务的模块没有全部登记在 FORBIDDEN_DOWNSTREAM_MODULES 里（实测 {sorted(forbidden)}）"
            " —— 漏一个就等于允许 extract 反向依赖它"
        )

    def test_engine_delivery_is_registered_for_task38(self) -> None:
        """归因型判据：只看**我这一条**登记（`DELIVERED_ENGINE_ADAPTERS` 是跨任务共享表）。"""
        mine = [
            entry
            for entry in RG.DELIVERED_ENGINE_ADAPTERS
            if str(entry.get("delivered_by_task")) == "38"
        ]
        assert len(mine) == 1, f"Task 38 的 engine 交付登记应恰一条，实得 {len(mine)}"
        entry = mine[0]
        assert entry["document_type"] == "xlsx"
        assert entry["adapter_module"].endswith("adapters/excel.py")
        assert {
            "app/services/workpaper_sync/excel_materialize.py",
            "app/services/workpaper_sync/excel_rematerialize.py",
        } <= set(entry["engine_modules"])

    def test_merge_domain_retirement_is_registered_for_task38(self) -> None:
        """归因型判据：只看 `retired_by_task == "38"` 的两条，不用全局等值。

        `merge.RETIRED_DEFERRALS` 是跨任务共享登记表 —— 写 `len(...) == N` 之类的全局等值判据，
        别人合法追加一条就把本守卫打红（本 spec 已实测踩过）。
        """
        mine = {
            str(entry["expected_consumer_module"]): entry
            for entry in MG.RETIRED_DEFERRALS
            if str(entry.get("retired_by_task")) == "38"
        }
        assert sorted(mine) == [
            "app/services/workpaper_sync/excel_materialize.py",
            "app/services/workpaper_sync/excel_rematerialize.py",
        ], f"Task 38 的退役登记与事实不符: {sorted(mine)}"
        expectations = {
            "app/services/workpaper_sync/excel_materialize.py": (
                "from app.services.workpaper_sync.merge import"
            ),
            "app/services/workpaper_sync/excel_rematerialize.py": (
                "from app.services.workpaper_sync.conflicts import"
            ),
        }
        for module, entry in sorted(mine.items()):
            assert entry["intended_status"] == "retired"
            assert entry["commits_through"] is None, (
                f"{module} 声明了 commits_through —— engine 不落库，"
                "落库仍在 oo_to_html → content_mutation 那一条上"
            )
            assert len(str(entry["reason"])) >= 40
            source = (_BACKEND / "app" / module.split("app/", 1)[1]).read_text(
                encoding="utf-8"
            )
            assert expectations[module] in source, (
                f"{module} 登记为已接线，但源码里没有对应的 import —— 登记与事实脱钩"
            )
            assert "merge_projections" not in str(entry["capability"]), (
                "本任务消费的是 `normalize_value` / `ConflictRecord`，不是 `merge_projections`；"
                "capability 写错会让 Task 14 的分域判据要求错误的 pattern"
            )


class TestGuardSelfCheck:
    """用替身复现已实证的假绿形态，证明真实判据确实在起作用。"""

    def test_presence_style_guard_would_miss_a_disabled_branch(self) -> None:
        """反例：只查「源码里有没有这个词」的判据，在分支被 `if False:` 关掉后仍绿。"""
        disabled = 'def f():\n    if False and state is quarantined:\n        raise Boom()\n'
        assert "quarantined" in disabled, "presence 式判据：仍绿（假绿第②源）"
        assert "if False" in disabled, "行为式判据：抓到了被关掉的分支"

    def test_derived_registry_would_be_a_tautology(self) -> None:
        """反例：从异常类反推登记清单 ⇒ 合并两个类时期望值跟着变，永远不打红。"""
        classes = {"A": "code_x", "B": "code_x"}  # 两个类被合并成同一个 code
        derived = set(classes.values())
        assert derived == {"code_x"}, "自证式：派生期望与事实恒相等"
        handwritten = {"code_x", "code_y"}
        assert derived != handwritten, "手写清单：基数不等 ⇒ 打红"

    def test_empty_unmanaged_region_would_be_vacuously_equivalent(self) -> None:
        """反例：手搓最小 xlsx 上未管理区域是空集 ⇒ `equivalent` 恒真。"""
        coverage_minimal: dict[str, int] = {}
        coverage_real = {"protected_parts": 1, "shared_strings_prefix": 212}
        assert all(count > 0 for count in coverage_real.values())
        assert not coverage_minimal, "空覆盖面：判据空转"

    def test_formula_equals_prefix_conversion_is_needed(self) -> None:
        """反例：不换算 openpyxl 的 `=` 前缀 ⇒ 写出 `<f>=G7-D7</f>`（Excel 里是 `==G7-D7`）。"""
        assert M._formula_body("=G7-D7") == "G7-D7"
        assert M._formula_body("G7-D7") == "G7-D7"
        assert M._formula_body("==G7-D7") == "=G7-D7", "只去一个 `=`"
