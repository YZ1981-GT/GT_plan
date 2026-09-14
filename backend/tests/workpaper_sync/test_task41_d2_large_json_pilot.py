# -*- coding: utf-8 -*-
"""Task 41 离线守卫：D2 大 JSON 子表 Excel pilot 的选型、契约、载荷拆分与预算。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 41
Requirements: 6.9, 6.11, 6.12, 12.1, 12.2, 12.10, 14.1, 14.11
Properties: **P27 / P29 / P49 / P60 / P69**

═══ 这一半证的是「判据本身正确 + 契约真有来源 + 拆分真的在跑」 ═══

`test_task41_d2_large_json_pilot_pg.py` 在真库上跑完整 run（发布四个 definition、组
non-null bundle、逐场景 record、finalize），并在**真实 906,239 字节载荷**上跑 Property 27
的 delete/update oracle 与预算三侧。本文件不连库，只证四件事：

1. **冻结的 entry 不是拍脑袋挑的**：三条必要条件在真实 manifest / 真实
   `wp_template_finder` / 真实 `D2A.yaml` 上重新推导一遍。🔴 其中第 2 条与 Task 40
   **形态不同**（`D2A` 在模板索引里没有精确对应的 wp_code），因此改为等价的三条实测
   事实 —— 见 `TestFrozenEntrySelection` 的 docstring。
2. **39 个字段逐个有来源**：`header_source_ref` / `group_source_ref` /
   `source_ref` 指向的单元格，用 openpyxl 直读权威模板取出**真实文本/公式**再比对；
   列键集合与前端 `useD2DetailColumnPrefs.FIXED_COLUMNS`、账龄段与
   `useAgingConfig.PRESET_SEGMENTS.FIVE_YEAR` 三源锁死。
3. **载荷拆分真的把整 JSON 拆开了**：`build_store_projection` 在真实 39 列形态上产出
   `行数 × 39` 个 stable field，且四类坏载荷（非数组 / 非法 JSON / 缺 rowId / 重复 rowId）
   各自 fail closed 且**错误分型互不相同**。
4. **预算与分块真的挂在生产路径上**：N-1/N/N+1 三侧样本 + 缩小的 `SyncLimits` 端到端跑
   `build_store_projection` 与 `extract_projection`；峰值内存落在 `tracemalloc` 实测上。

═══ 反假绿 ═══

* 覆盖计数硬判据：39 个字段 / 36 editable / 3 protected / 39 次表头比对 / 18 次组标题比对 /
  39 次公式比对（3 列 × 13 行）/ 8 个未管理区域 aspect 覆盖计数全部 > 0。
* 双向锁：磁盘契约 ↔ 现算 payload（改任一侧都打红）。
* 分型可达：`StorePayloadError` 的四个分支各真触发一次，且与 `PilotSelectionError`
  互不相同（共用错误码会让较早分支永久不可达 —— 本 spec 已实测 3 次的形态）。
* 期望值一律从**源侧**推导或写字面量，绝不用被测函数算期望。
"""
from __future__ import annotations

import ast
import gzip
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

from app.services.excel_structure_fingerprint import (  # noqa: E402
    GT_SYNC_SHEET_NAME,
    identity_inventory,
)
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import pilot_d2_large_json as P  # noqa: E402
from app.services.workpaper_sync import pilot_harness as PH  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    FieldValue,
    Projection,
    SubstrateRole,
)
from app.services.workpaper_sync.contracts import (  # noqa: E402
    ContractError,
    ExtractCarrierTier,
    FieldMode,
    available_contract_ids,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402
from app.services.workpaper_sync.entry_profile import (  # noqa: E402
    Capability,
    capability_of,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_entry_gate import (  # noqa: E402
    AdapterBuild,
    FrozenEntryDefinitions,
    parse_identity_inventory,
)
from app.services.workpaper_sync.limits import (  # noqa: E402
    BudgetExceededError,
    SyncLimits,
    load_limits,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402

# 🔴 与 Task 37 共用同一份 zip 级字节编辑件（`patch_cells` 的正则有两处已实测的坑，
#    抄第二份就是把那两个坑再踩一遍）。这些是 **fixture 构造件**、不是判据。
from test_task37_excel_extract import (  # noqa: E402
    _read_entries,
    _sheet_part_of,
    _write_entries,
    patch_cells,
)

#: `__BOOL1__` / `__BOOL0__` 占位 → 真 OOXML 布尔格 `t="b"`。
#:
#: 只做一次**定点字符串替换**（占位串全局唯一），刻意不复制 Task 37 `patch_cells` 的
#: 单元格正则 —— 那段正则有两处已实测的坑（自闭合分支必须在前、属性段必须惰性）。
_BOOL_PLACEHOLDERS: dict[str, str] = {"__BOOL1__": "1", "__BOOL0__": "0"}


def _promote_boolean_cells(data: bytes, sheet_part: str) -> bytes:
    entries = _read_entries(data)
    xml = entries[sheet_part].decode("utf-8")
    promoted = 0
    for placeholder, rendered in _BOOL_PLACEHOLDERS.items():
        pattern = re.compile(
            r'<c r="([A-Z]+\d+)"(?:\s[^>]*?)?\st="inlineStr"><is><t[^>]*>'
            + re.escape(placeholder)
            + r"</t></is></c>"
        )
        for match in list(pattern.finditer(xml)):
            xml = xml.replace(
                match.group(0), f'<c r="{match.group(1)}" t="b"><v>{rendered}</v></c>', 1
            )
            promoted += 1
    assert promoted == EXPECTED_TEMPLATE_ROW_COUNT, (
        f"只提升了 {promoted} 个布尔格 —— 占位形态与 patch_cells 的落盘形态不再匹配，"
        "反向自检会变成空判据"
    )
    entries[sheet_part] = xml.encode("utf-8")
    return _write_entries(entries)

_MANIFEST_PATH = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"
_FRONTEND = _REPO / "audit-platform" / "frontend" / "src"
_COLUMN_PREFS = (
    _FRONTEND / "components" / "workpaper" / "composables" / "useD2DetailColumnPrefs.ts"
)
_AGING_CONFIG = _FRONTEND / "composables" / "useAgingConfig.ts"
_ROUTER = _BACKEND / "app" / "routers" / "wp_sync_router.py"

#: 真实载荷的实测事实（pg 侧守卫从**库里**重新取一次并逐条比对；这里作为字面量互锁）。
REAL_PAYLOAD_BYTES = 906_239
REAL_PAYLOAD_ROWS = 1_260
REAL_D2_ITEM_COUNT = 24

#: 39 = 21 个标量列 + 3 组 × 6 段账龄列（源 xlsx 的真实列数，`max_column == 39`）。
EXPECTED_FIELD_COUNT = 39
EXPECTED_PROTECTED_COUNT = 3
#: 权威模板的**物理**骨架行数（`A13..A24` 字面量 1..12 + `A25` 占位 `……`）= 13。
#:
#: 🔴 BP-21 起它**不再等于**受管行数：`A25` 是排版占位行（续行省略号），不是业务行。
EXPECTED_PHYSICAL_SKELETON_ROWS = 13
#: 受管行数 = 物理骨架 − 尾部排版占位行 = 12（`A13..A24`）。
EXPECTED_TEMPLATE_ROW_COUNT = P.LAST_DATA_ROW - P.FIRST_DATA_ROW + 1  # 12


# ═══════════════════════════════════════════════════════════════════════════
# fixtures：真实 manifest / 真实权威模板 / 真实注入产物（不手搓 xlsx）
# ═══════════════════════════════════════════════════════════════════════════


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _non_docstring_literals(path: Path) -> list[str]:
    """模块里的**非 docstring** 字符串字面量。

    docstring 必须剥掉：本任务的生产模块 docstring 里刻意写着「参考副本一次都不读」
    「与 b60 的 digest 不同」这类**说明**，纯字面量判据会把说明本身判成违规。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = (node.body or [None])[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def observe_template_resolution() -> Any:
    """借用契约生成器里的**同一个**观测器（不抄第二份）。

    观测器住在 `backend/scripts/gen/` 而不是 `backend/app/`：`find_template_file*` 是
    Task 19 清册登记的 non-canonical resolver 符号，生产模块里出现它们会给收口门增债
    （见 `P.TemplateResolutionFacts` 的 docstring）。
    """
    import importlib.util

    path = _BACKEND / "scripts" / "gen" / "generate_pilot_d2_large_json_contract.py"
    spec = importlib.util.spec_from_file_location("_t41_contract_gen", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.observe_template_resolution()


@pytest.fixture(scope="module")
def resolution() -> Any:
    return observe_template_resolution()


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entry(manifest: dict[str, Any]) -> dict[str, Any]:
    return dict(manifest_entries_by_id(manifest)[P.PILOT_ENTRY_ID])


@pytest.fixture(scope="module")
def workbook() -> Any:
    import openpyxl

    return openpyxl.load_workbook(P.authoritative_template_path(), data_only=False)


@pytest.fixture(scope="module")
def worksheet(workbook: Any) -> Any:
    """openpyxl 直读权威模板的受管 sheet（源侧事实，用于推导期望值）。"""
    return workbook[P.MANAGED_SHEET]


@pytest.fixture(scope="module")
def contract() -> Any:
    return P.load_pilot_contract()


@pytest.fixture(scope="module")
def instrumented() -> EI.InstrumentedWorkbook:
    gate = EI.ExcelIdentityCarrierGate.load()
    return EI.instrument_workbook_bytes(
        P.read_authoritative_template(), P.instrumentation_spec(), gate=gate
    )


@pytest.fixture(scope="module")
def sheet_part(instrumented: EI.InstrumentedWorkbook) -> str:
    return _sheet_part_of(instrumented.instrumented_bytes, P.MANAGED_SHEET)


#: 唯一的 boolean 列（`AK 是否函证`），fixture 按**生产落盘形态**写。
#:
#: 🔴 BP-22 起生产形态是 OOXML **真布尔格** `t="b"` + `<v>1|0</v>`
#: （`excel_materialize._write_kind_for(boolean)` → `CellWriteKind.boolean_literal`）。
#: 之前它归 `number_literal`、落 `<v>1</v>` 无 `t` ⇒ extract 读回 int ⇒
#: `normalize_value` 拒绝折叠 0/1 ⇒ 每行一条 `type_normalization_failure`。
#: 本 fixture 必须跟着生产走：镜像旧形态会让「缺陷已修」这件事在判据上看不见。
#:
#: 落盘手法仍走 `__BOOL1__` / `__BOOL0__` 占位串 + :func:`_promote_boolean_cells`：
#: `patch_cells` 直接写 Python `True` 会落出 `<v>False</v>`，openpyxl
#: `_cast_number('False')` 抛 `ValueError`、整份 workbook 不可打开（首轮实测 14 例 ERROR）。
BOOLEAN_COLUMN = "AK"


@pytest.fixture(scope="module")
def base_bytes(instrumented: EI.InstrumentedWorkbook, sheet_part: str) -> bytes:
    """把 36 个 editable 列逐行写满业务值（公式列不写，留模板公式）。

    🔴 BP-22：boolean 列写成**真布尔格**（生产形态），于是基线 extract 的 schema 异常
    从「每行一条」变成 **0 条**。
    """
    cells: dict[str, Any] = {}
    written_columns: set[str] = set()
    for row in range(P.FIRST_DATA_ROW, P.LAST_DATA_ROW + 1):
        for _key, column, mode, value_type, _path, _label in P.MANAGED_FIELD_SPECS:
            if mode == "formula":
                continue
            written_columns.add(column)
            if value_type == "boolean":
                cells[f"{column}{row}"] = "__BOOL1__" if row % 2 == 0 else "__BOOL0__"
            elif value_type == "amount":
                cells[f"{column}{row}"] = 100 + row
            elif value_type == "integer":
                cells[f"{column}{row}"] = row
            else:
                cells[f"{column}{row}"] = f"值{column}{row}"
    assert len(written_columns) == 36, sorted(written_columns)
    assert BOOLEAN_COLUMN in written_columns
    return _promote_boolean_cells(
        patch_cells(instrumented.instrumented_bytes, sheet_part, cells), sheet_part
    )


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("task41")


@pytest.fixture(scope="module")
def base_path(base_bytes: bytes, workdir: Path) -> Path:
    path = workdir / "base.xlsx"
    path.write_bytes(base_bytes)
    return path


@pytest.fixture(scope="module")
def binding() -> X.ExcelIdentityBinding:
    return X.ExcelIdentityBinding(
        table_name=P.TABLE_NAME, uuid_column=P.UUID_COL, table_key=P.ROWS_TABLE_KEY
    )


@pytest.fixture(scope="module")
def definitions(contract: Any, base_bytes: bytes) -> FrozenEntryDefinitions:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    bundle = DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d2-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d2-authority"),
        slots={
            BundleSlot.template: slot(
                BundleSlot.template, contract.template_definition_sha256
            ),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )
    return FrozenEntryDefinitions(
        entry_id=P.PILOT_ENTRY_ID,
        bundle=bundle,
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=P.PILOT_ADAPTER_ID,
            adapter_build_digest=_d("d2-adapter-build"),
            document_type="xlsx",
            contract_version="1.0.0",
        ),
        identity_inventory=parse_identity_inventory(
            identity_inventory(
                base_bytes, expected_table=P.TABLE_NAME, uuid_column_letter=P.UUID_COL
            )
        ),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


def extract(
    path: Path,
    definitions: FrozenEntryDefinitions,
    binding: X.ExcelIdentityBinding,
    **over: Any,
) -> X.ExcelExtractOutcome:
    kwargs: dict[str, Any] = {
        "artifact": path,
        "definitions": definitions,
        "binding": binding,
        "substrate_role": SubstrateRole.incoming,
        "artifact_kind": ArtifactKind.incoming,
        "artifact_state": ArtifactState.durable,
    }
    kwargs.update(over)
    return X.extract_projection(**kwargs)


@pytest.fixture(scope="module")
def base_outcome(
    base_path: Path, definitions: FrozenEntryDefinitions, binding: X.ExcelIdentityBinding
) -> X.ExcelExtractOutcome:
    return extract(base_path, definitions, binding)


def scaled_limits(**over: Any) -> SyncLimits:
    """按生产配置派生一份缩小的预算（被测常量仍来自单一真源配置文件）。"""
    base = load_limits()
    fields = {
        name: getattr(base, name) for name in base.__dataclass_fields__ if name != "ooxml"
    }
    fields.update(over)
    return SyncLimits(ooxml=base.ooxml, **fields)


def store_rows(count: int, *, start: int = 0) -> list[dict[str, Any]]:
    """按**真实 39 列形态**造 `count` 行 store 数据（键集合逐个来自契约常量）。

    值是合成的，形态不是：39 个 json 路径、三层 aging 嵌套、`rowId` 命名规则全部取自
    :data:`P.MANAGED_FIELD_SPECS` / :data:`P.AGING_GROUPS`。真实 906,239 字节载荷上的
    判据在 `test_task41_d2_large_json_pilot_pg.py`（本文件不连库）。
    """
    rows: list[dict[str, Any]] = []
    for index in range(start, start + count):
        row: dict[str, Any] = {P.ROW_IDENTITY_STORE_KEY: f"dr-fixture-{index:05d}"}
        for prefix, _cell, _cols, _label in P.AGING_GROUPS:
            row[prefix] = {}
        for _key, _col, _mode, value_type, path, _label in P.MANAGED_FIELD_SPECS:
            if "/" in path:
                prefix, leaf = path.split("/", 1)
                row[prefix][leaf] = float(index + 1)
                continue
            if value_type == "amount":
                row[path] = float(index + 1)
            elif value_type == "integer":
                row[path] = index + 1
            elif value_type == "boolean":
                row[path] = index % 2 == 0
            else:
                row[path] = f"{path}-{index}"
        rows.append(row)
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结的 entry：必要条件在真实数据上重新推导
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenEntrySelection:
    """**Validates: Requirements 12.1 / 12.2**

    🔴 第 2 条必要条件与 Task 40 **形态不同**，这里把理由写成可执行事实：

    Task 40 用「wp_code 与 `wp_templates/_index.json` 精确相等」证明
    `find_template_file()` 不会回退到父级程序表。本 entry 的 `wp_code_patterns` 是
    `["D2A"]`，索引里三份 D2 模板的 `wp_code` 都是 `D2` ⇒ 那条判据**不成立**。
    但它的**目的**由三条实测事实等价满足，且每条都单独可打红：

    1. `D2A` 在 `wp_template_finder` 上解析结果为空（None/None/[]）——「零回退」的最强形态
       是「根本没有回退」；
    2. 权威模板由配置真源 `D2A.yaml` 的 `template_path` 唯一声明；
    3. 父码 `D2` 的 canonical resolver 落在**同一份**文件上（声明没指向别的底稿）。
    """

    def test_entry_is_frozen_from_the_source_backed_manifest(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        got = P.assert_pilot_entry_selectable(manifest=manifest, resolution=resolution)
        assert got["entry_id"] == P.PILOT_ENTRY_ID

    def test_entry_is_the_only_d2_candidate_in_the_harness_assessment(
        self, manifest: dict[str, Any]
    ) -> None:
        """类边界由 harness 判定，不由本模块声明；实测**恰好 1 个**候选。"""
        assessment = PH.assess_pilot_classes(manifest=manifest)[PH.PilotClass.d2_large_json]
        assert assessment.candidate_entry_ids == (P.PILOT_ENTRY_ID,), (
            assessment.candidate_entry_ids
        )
        assert assessment.status is PH.PilotClassStatus.unverifiable

    def test_entry_is_independent_and_not_a_parent_duplicate(
        self, entry: dict[str, Any]
    ) -> None:
        assert entry["independent_entry"] is True
        assert entry["parent_entry_id"] is None

    def test_wp_code_has_no_implicit_template_fallback(self, resolution: Any) -> None:
        """`D2A` 在 `wp_template_finder` 三个入口上都必须解析不到任何文件（**实测**）。"""
        assert set(resolution.by_wp_code) == set(P.PILOT_WP_CODES)
        checked = 0
        for code, hits in sorted(resolution.by_wp_code.items()):
            assert len(hits) == 3, (code, hits)
            assert [item for item in hits if item] == [], (code, hits)
            checked += 1
        assert checked == 1, checked
        # 判定函数在真实事实上不抛（正向），非空事实上必抛（反向自检见下条）。
        P.assert_no_implicit_template_fallback(resolution, wp_codes=P.PILOT_WP_CODES)

    def test_fallback_judgement_fails_closed_on_a_non_empty_resolution(
        self, resolution: Any
    ) -> None:
        """反向自检：任一入口解析出文件必须打红（否则上一条是空集恒真）。"""
        polluted = P.TemplateResolutionFacts(
            by_wp_code={"D2A": (P.authoritative_template_path(), None, ())},
            parent_code=resolution.parent_code,
            parent_resolved_path=resolution.parent_resolved_path,
        )
        with pytest.raises(P.PilotSelectionError, match="零回退判据"):
            P.assert_no_implicit_template_fallback(polluted, wp_codes=P.PILOT_WP_CODES)
        missing = P.TemplateResolutionFacts(
            by_wp_code={},
            parent_code=resolution.parent_code,
            parent_resolved_path=resolution.parent_resolved_path,
        )
        with pytest.raises(P.PilotSelectionError, match="finder 实测结果"):
            P.assert_no_implicit_template_fallback(missing, wp_codes=P.PILOT_WP_CODES)

    def test_authoritative_template_is_declared_by_the_render_schema(self) -> None:
        """配置真源（`D2A.yaml`）声明的 `template_path` 就是冻结的那份模板。"""
        import yaml

        declared = P.render_schema_template_path()
        assert "/".join(declared.split("\\")) == (
            f"backend/wp_templates/{P.TEMPLATE_RELATIVE_PATH}"
        )
        assert (_REPO / declared).is_file()
        # 源侧：YAML 的 wp_code 与本 pilot 的 matcher 域一致（一一对应关系的另一半）。
        schema = yaml.safe_load(
            (_REPO / P.RENDER_SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        assert schema["wp_code"] in P.PILOT_WP_CODES

    def test_render_schema_wp_code_must_stay_inside_the_matcher_domain(self) -> None:
        """反向自检：配置的 wp_code 漂到别的码必须打红（配置真源与 entry 不得脱钩）。"""
        with pytest.raises(P.PilotSelectionError, match="matcher 域"):
            P.render_schema_template_path(
                payload={"wp_code": "D2B", "template_path": "backend/wp_templates/x.xlsx"}
            )

    def test_parent_code_canonical_resolver_lands_on_the_same_workbook(
        self, resolution: Any
    ) -> None:
        """父码 `D2` 的 canonical resolver 与配置声明必须是同一份文件。"""
        assert resolution.parent_code == "D2"
        assert resolution.parent_resolved_path is not None
        assert (
            Path(str(resolution.parent_resolved_path)).resolve()
            == P.authoritative_template_path().resolve()
        )
        wrong = P.TemplateResolutionFacts(
            by_wp_code=resolution.by_wp_code,
            parent_code="D2",
            parent_resolved_path=None,
        )
        with pytest.raises(P.PilotSelectionError, match="canonical resolver 落在"):
            P.assert_no_implicit_template_fallback(wrong, wp_codes=P.PILOT_WP_CODES)

    def test_scenario_profile_is_the_shared_editable_standard(
        self, entry: dict[str, Any]
    ) -> None:
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        profile = entry["scenario_profile"]
        assert profile["profile_id"] == "xlsx.editable.shared.single.room_service_wired.v1"
        required = derive_for_manifest_entry(entry, authority_model=P.AUTHORITY_MODEL)
        PH.assert_required_set_non_empty(required)
        assert required.editability.value == "editable"
        assert required.room_model.value == "shared"
        assert required.close_required is True
        assert required.substituted is False
        assert len(required.scenario_ids) == 24, required.scenario_ids

    def test_required_set_digest_is_this_entry_own_not_the_checklist_pilot(
        self, manifest: dict[str, Any]
    ) -> None:
        """evidence 必须按**本** bundle/entry 的 digest 记录（禁用 checklist pilot 的）。"""
        from app.services.workpaper_sync import pilot_simple_checklist as CHECKLIST
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entries = manifest_entries_by_id(manifest)
        mine = derive_for_manifest_entry(
            entries[P.PILOT_ENTRY_ID], authority_model=P.AUTHORITY_MODEL
        )
        theirs = derive_for_manifest_entry(
            entries[CHECKLIST.PILOT_ENTRY_ID], authority_model=CHECKLIST.AUTHORITY_MODEL
        )
        assert set(mine.scenario_ids) == set(theirs.scenario_ids), "两者场景集合形态相同"
        assert mine.digest != theirs.digest, (
            "required_scenario_set_digest 必须绑定各自 entry —— 两个 pilot 共用一个 digest "
            "就意味着 evidence 可以互相冒充"
        )
        assert P.PILOT_ADAPTER_ID != CHECKLIST.PILOT_ADAPTER_ID
        assert P.contract_file_path() != CHECKLIST.contract_file_path()

    # ── fail-closed 分支（每条都要真触发一次）────────────────────────────
    def test_selection_fails_closed_when_the_entry_disappears(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        payload = {
            **manifest,
            "entries": [
                item for item in manifest["entries"] if item["entry_id"] != P.PILOT_ENTRY_ID
            ],
        }
        with pytest.raises(P.PilotSelectionError, match="不在 source-backed manifest"):
            P.assert_pilot_entry_selectable(manifest=payload, resolution=resolution)

    def test_selection_fails_closed_on_parent_duplicate(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["independent_entry"] = False
                item["parent_entry_id"] = "xlsx/parent"
        with pytest.raises(P.PilotSelectionError, match="independent_entry"):
            P.assert_pilot_entry_selectable(manifest=patched, resolution=resolution)

    def test_selection_fails_closed_on_wp_code_drift(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["wp_match"]["wp_code_patterns"] = ["D2A", "D2B"]
        with pytest.raises(P.PilotSelectionError, match="wp_code_patterns"):
            P.assert_pilot_entry_selectable(manifest=patched, resolution=resolution)

    def test_selection_fails_closed_when_the_render_schema_points_elsewhere(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        with pytest.raises(P.PilotSelectionError, match="template_path"):
            P.assert_pilot_entry_selectable(
                manifest=manifest,
                resolution=resolution,
                declared_template_path="backend/wp_templates/D/D2-5  应收账款 -分析程序（Leap应对措施-分析程序）.xlsx",
            )

    def test_the_contract_generator_refuses_to_write_when_selection_breaks(self) -> None:
        """契约生成器是 `assert_pilot_entry_selectable` 的**非测试**调用方（非死代码）。"""
        generator = (
            _BACKEND / "scripts" / "gen" / "generate_pilot_d2_large_json_contract.py"
        )
        tree = ast.parse(generator.read_text(encoding="utf-8"))
        main = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        calls = {
            inner.func.id
            for inner in ast.walk(main)
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
        }
        assert "observe_template_resolution" in calls
        attrs = {
            inner.func.attr
            for inner in ast.walk(main)
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
        }
        assert "assert_pilot_entry_selectable" in attrs, sorted(attrs)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板：只认 `backend/wp_templates/`，跑完字节原样
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthoritativeTemplate:
    """**Validates: Requirements 6.11**"""

    def test_template_bytes_are_unchanged(self) -> None:
        """跑完本文件 `backend/wp_templates/` 必须原样（Requirement 9.9）。"""
        data = P.read_authoritative_template()
        assert hashlib.sha256(data).hexdigest() == P.TEMPLATE_SHA256
        assert len(data) == 123_162

    def test_template_lives_under_the_authority_root(self) -> None:
        path = P.authoritative_template_path()
        assert path.is_file()
        assert path.resolve().is_relative_to((_BACKEND / "wp_templates").resolve())

    def test_reference_copy_is_never_read(self) -> None:
        """参考副本（`基础数据/致同通用审计程序及底稿模板…`）不得进入**代码**路径。

        🔴 判据必须剥掉 docstring：本模块的 docstring 刻意写明「一次都不读它」，
        纯词面搜索会把这句说明本身判成违规（词面搜索的经典假阳性 —— 首轮实测发生过）。
        判据落在 AST 的**非 docstring 字符串常量**上。
        """
        literals = _non_docstring_literals(Path(P.__file__))
        assert literals, "AST 判据自身失效：没有采到任何非 docstring 字符串常量"
        offenders = [
            text for text in literals if "基础数据" in text or "致同通用审计程序" in text
        ]
        assert offenders == [], offenders
        # 正向：权威根确实出现在代码字面量里（否则上面这条是空集恒真）。
        assert any("wp_templates" in text for text in literals)

    def test_managed_sheet_is_one_of_eleven_and_only_it_is_declared(
        self, workbook: Any, contract: Any
    ) -> None:
        """工作簿 11 张 sheet，契约只声明受管的那一张（`managed_tables_of` 会 fail closed）。"""
        assert len(workbook.sheetnames) == 11, workbook.sheetnames
        assert P.MANAGED_SHEET in workbook.sheetnames
        assert [sheet.excel_name for sheet in contract.sheets] == [P.MANAGED_SHEET]
        assert len(contract.sheets[0].tables) == 1

    def test_template_sentinel_rejects_a_mutated_workbook(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """反向自检：模板字节被改一位必须抛（不是 warning）。"""
        fake = tmp_path / "mutated.xlsx"
        fake.write_bytes(P.read_authoritative_template() + b"\x00")
        monkeypatch.setattr(P, "authoritative_template_path", lambda: fake)
        with pytest.raises(P.PilotSelectionError, match="权威模板字节已变"):
            P.read_authoritative_template()


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约逐字段有来源（源侧推导期望值）
# ═══════════════════════════════════════════════════════════════════════════


class TestContractIsGroundedInTheTemplate:
    """**Validates: Requirements 6.9 / 6.11 / 12.1**"""

    def test_disk_contract_matches_the_source_of_truth(self) -> None:
        """磁盘契约 ↔ 现算 payload 双向锁死。"""
        assert P.assert_contract_file_matches_source().contract_id == P.PILOT_ADAPTER_ID

    def test_contract_is_registered_in_the_delivery_ledger(self) -> None:
        ledger = {row["contract_id"]: row for row in RG.DELIVERED_PER_ENTRY_CONTRACTS}
        assert P.PILOT_ADAPTER_ID in ledger
        row = ledger[P.PILOT_ADAPTER_ID]
        assert row["entry_id"] == P.PILOT_ENTRY_ID
        assert row["pilot_class"] == P.PILOT_CLASS
        assert row["document_type"] == "xlsx"
        assert row["template_relative_path"] == P.TEMPLATE_RELATIVE_PATH
        assert P.PILOT_ADAPTER_ID in available_contract_ids()

    def test_field_counts_are_the_real_template_facts(self, contract: Any) -> None:
        """覆盖计数硬判据（空集恒等价不算通过）。"""
        assert len(contract.all_fields()) == EXPECTED_FIELD_COUNT == 39
        assert len(P.MANAGED_FIELD_SPECS) == EXPECTED_FIELD_COUNT
        assert len(P.SCALAR_FIELD_SPECS) == 21
        assert len(P.AGING_GROUPS) * len(P.AGING_SEGMENTS) == 18
        assert len(contract.protected_field_keys()) == EXPECTED_PROTECTED_COUNT == 3
        assert len(contract.editable_field_keys()) == 36

    def test_column_letters_cover_a_to_am_without_gap(self, worksheet: Any) -> None:
        """39 列必须**连续**覆盖 A..AM，且与 sheet 的 `max_column` 一致。"""
        columns = [spec[1] for spec in P.MANAGED_FIELD_SPECS]
        assert columns[0] == "A"
        assert columns[-1] == P.MANAGED_LAST_COL == "AM"
        assert len(set(columns)) == 39
        indices = [P._col_index(col) for col in columns]
        assert indices == list(range(1, 40)), indices
        assert worksheet.max_column == 39

    def test_every_managed_header_matches_the_real_cell_text(
        self, contract: Any, worksheet: Any
    ) -> None:
        """39 次比对：每个字段的 `header_source_ref` 指向的格文本 == 登记文本。"""
        by_key = {
            spec.column_key: spec
            for sheet in contract.sheets
            for table in sheet.tables
            for spec in table.fields
        }
        compared = 0
        for column_key, column, _mode, _vt, _path, label in P.MANAGED_FIELD_SPECS:
            spec = by_key[column_key]
            raw = spec.source_ref  # `源xlsx!{sheet}!{cell}`
            assert raw.startswith(f"源xlsx!{P.MANAGED_SHEET}!"), raw
            assert raw.endswith(f"{column}{P.FIRST_DATA_ROW}"), raw
            header_row = (
                P.HEADER_LEAF_ROW if column_key in P.GROUP_HEADER_CELLS else P.HEADER_GROUP_ROW
            )
            cell = f"{column}{header_row}"
            declared = contract.canonical_payload["sheets"][0]["tables"][0]["fields"]
            entry = next(item for item in declared if item["column_key"] == column_key)
            assert entry["header_source_ref"] == f"源xlsx!{P.MANAGED_SHEET}!{cell}", cell
            assert worksheet[cell].value == label, (cell, worksheet[cell].value, label)
            compared += 1
        assert compared == 39, compared

    def test_every_aging_group_header_matches_the_real_cell_text(
        self, contract: Any, worksheet: Any
    ) -> None:
        """18 次比对：账龄列的组标题单元格文本 == 登记的组标题。"""
        declared = {
            item["column_key"]: item
            for item in contract.canonical_payload["sheets"][0]["tables"][0]["fields"]
        }
        compared = 0
        for column_key, cell in sorted(P.GROUP_HEADER_CELLS.items()):
            label = P.GROUP_HEADER_LABELS[column_key]
            assert worksheet[cell].value == label, (cell, worksheet[cell].value)
            item = declared[column_key]
            assert item["group_source_ref"] == f"源xlsx!{P.MANAGED_SHEET}!{cell}"
            assert item["group_header_text"] == label
            compared += 1
        assert compared == 18, compared
        # 标量列不得带组标题（否则「两级」判据会退化成到处都有组）。
        scalar_with_group = [
            key for key, _c, _m, _v, _p, _l in P.SCALAR_FIELD_SPECS
            if "group_source_ref" in declared[key]
        ]
        assert scalar_with_group == [], scalar_with_group

    def test_three_formula_columns_are_really_formulas_in_the_template(
        self, worksheet: Any
    ) -> None:
        """39 次比对（3 列 × **13 行物理骨架**）：逐格公式文本必须与登记模板逐字相等。

        🔴 BP-21：逐行公式是**物理**模板事实，覆盖整个骨架（含 `A25` 那行排版占位）——
        所以按 `TEMPLATE_PHYSICAL_LAST_ROW` 迭代。第二段单独断言「受管区内那 12 行也全都
        有公式」，两个口径各自被取证、不互相掩盖。
        """
        seen = 0
        for column, template in sorted(P.FORMULA_TEMPLATES.items()):
            for row in range(P.FIRST_DATA_ROW, P.TEMPLATE_PHYSICAL_LAST_ROW + 1):
                assert worksheet[f"{column}{row}"].value == template.format(r=row), (
                    f"{column}{row}"
                )
                seen += 1
        assert seen == 3 * EXPECTED_PHYSICAL_SKELETON_ROWS == 39, seen

        managed = sum(
            1
            for column, template in P.FORMULA_TEMPLATES.items()
            for row in range(P.FIRST_DATA_ROW, P.LAST_DATA_ROW + 1)
            if worksheet[f"{column}{row}"].value == template.format(r=row)
        )
        assert managed == 3 * EXPECTED_TEMPLATE_ROW_COUNT == 36, managed
        assert managed < seen, "受管区必须是物理骨架的真子集（否则 BP-21 没有生效）"
        declared = {
            spec[0]: spec[2] for spec in P.MANAGED_FIELD_SPECS if spec[1] in P.FORMULA_TEMPLATES
        }
        assert set(declared.values()) == {"formula"}, declared
        assert len(declared) == 3, declared

    def test_column_h_has_no_formula_in_the_template(self, worksheet: Any) -> None:
        """`H 期初审定余额` 在模板里没有公式 ⇒ 契约判 editable（以源 xlsx 为准）。

        前端 `useD2Detail.recalcRow()` 把它算成 `priorUnadjusted+priorAje+priorRje`。
        两侧口径不同是**存量**差异，这里把它钉住：模板哪天真加了公式，本条打红，
        必须重新审核 mode 而不是让 OO 侧覆盖服务端算出来的值。
        """
        checked = 0
        for row in range(P.FIRST_DATA_ROW, P.LAST_DATA_ROW + 1):
            value = worksheet[f"H{row}"].value
            assert not (isinstance(value, str) and value.startswith("=")), (row, value)
            checked += 1
        assert checked == EXPECTED_TEMPLATE_ROW_COUNT == 12
        mode = next(spec[2] for spec in P.MANAGED_FIELD_SPECS if spec[1] == "H")
        assert mode == "editable"

    def test_formula_mask_covers_all_three_formula_columns(self, contract: Any) -> None:
        table = contract.sheets[0].tables[0]
        assert set(table.formula_mask) == set(P.FORMULA_MASK)
        assert len(table.formula_mask) == 3
        assert table.two_level_header is True and table.header_rows == 2

    def test_footer_marker_is_the_real_cell_text(
        self, worksheet: Any, contract: Any
    ) -> None:
        table = contract.sheets[0].tables[0]
        assert table.footer_anchor is not None
        assert table.footer_anchor.marker == P.FOOTER_MARKER
        assert table.footer_anchor.search_column == "A"
        assert worksheet[f"A{P.FOOTER_ROW}"].value == P.FOOTER_MARKER
        # footer 行确实带 SUM（证明它是真 footer 而不是一行普通数据）。
        assert str(worksheet[f"E{P.FOOTER_ROW}"].value or "").startswith("=SUM(")

    def test_two_level_header_is_real_in_the_template(self, worksheet: Any) -> None:
        """`header_rows=2` 不是猜的：三个账龄组在行 11 横跨 6 列且行 12 有二级标题。"""
        merged = {str(rng) for rng in worksheet.merged_cells.ranges}
        for _prefix, group_cell, columns, _label in P.AGING_GROUPS:
            span = f"{columns[0]}{P.HEADER_GROUP_ROW}:{columns[-1]}{P.HEADER_GROUP_ROW}"
            assert span in merged, (span, group_cell)
        # 21 个标量列在行 11:12 纵向合并（单级列）。
        for column_key, column, *_ in P.SCALAR_FIELD_SPECS:
            span = f"{column}{P.HEADER_GROUP_ROW}:{column}{P.HEADER_LEAF_ROW}"
            assert span in merged, (column_key, span)

    def test_row_identity_is_not_positional(self, contract: Any) -> None:
        table = contract.sheets[0].tables[0]
        assert table.row_identity is not None
        assert table.row_identity.kind.value == "field"
        assert table.row_identity.json_pointer == f"/rows/*/{P.ROW_IDENTITY_STORE_KEY}"
        assert table.delete_policy is not None
        assert table.delete_policy.value == "tombstone"
        # 39 个 stable key 全部带 `{row_uuid}` 占位，且没有任何数组下标形态。
        keys = [spec.stable_field_key for spec in contract.all_fields()]
        assert all("{row_uuid}" in key for key in keys), keys[:3]
        assert not any(re.search(r"/\d+/", key) for key in keys)

    def test_contract_declares_no_metadata_sheet(self, contract: Any) -> None:
        from app.services.workpaper_sync.excel_entry_gate import (
            assert_contract_declares_no_metadata_sheet,
        )

        assert_contract_declares_no_metadata_sheet(contract)
        assert GT_SYNC_SHEET_NAME not in {sheet.excel_name for sheet in contract.sheets}

    def test_uuid_column_sits_right_of_the_managed_business_columns(self) -> None:
        spec = P.instrumentation_spec()
        assert P._col_index(P.UUID_COL) == P._col_index(P.MANAGED_LAST_COL) + 1
        assert spec.table_ref == f"A{P.FIRST_DATA_ROW}:{P.UUID_COL}{P.LAST_DATA_ROW}"
        assert spec.row_count == EXPECTED_TEMPLATE_ROW_COUNT == 12
        # 🔴 BP-21：footer 与受管末行之间隔着那行排版占位 ⇒ 不再相邻
        assert spec.footer_row == P.FOOTER_ROW > P.LAST_DATA_ROW
        assert P.FOOTER_ROW == P.TEMPLATE_PHYSICAL_LAST_ROW + 1 == 26
        assert spec.footer_row > spec.last_data_row + 1

    def test_mutated_contract_payload_is_rejected(self) -> None:
        """反向自检：把一个 formula 字段挪出 formula_mask 必须被 `parse_contract` 拒。"""
        payload = json.loads(json.dumps(P.build_contract_payload()))
        payload["sheets"][0]["tables"][0]["formula_mask"] = [
            f"Q{P.FIRST_DATA_ROW}:Q{P.LAST_DATA_ROW}"
        ]
        with pytest.raises(ContractError, match="formula_mask"):
            parse_contract(payload, adapter_id=P.PILOT_ADAPTER_ID)

    def test_row_identity_pointer_matching_the_real_store_key_is_load_bearing(self) -> None:
        """把 `rowId` 写成 `rowUuid` 之类必须被 store 拆分拒（不是只在契约里好看）。"""
        rows = store_rows(2)
        for row in rows:
            row["rowUuid"] = row.pop(P.ROW_IDENTITY_STORE_KEY)
        with pytest.raises(P.StorePayloadError, match="缺少稳定行身份"):
            list(P.iter_store_rows(rows))


# ═══════════════════════════════════════════════════════════════════════════
# 4. 三源锁死：源 xlsx ↔ 契约 ↔ 前端列/账龄真源
# ═══════════════════════════════════════════════════════════════════════════


def _frontend_fixed_columns() -> list[tuple[str, str]]:
    """解析 `useD2DetailColumnPrefs.ts` 的 `FIXED_COLUMNS`（21 条 `(key, label)`，按序）。"""
    text = _COLUMN_PREFS.read_text(encoding="utf-8")
    block = re.search(r"const FIXED_COLUMNS: ColumnDef\[\] = \[(.*?)\n\]", text, re.S)
    assert block, "FIXED_COLUMNS 块不再存在 —— 前端列真源被重构，必须重新审核映射"
    return [
        (match.group(1), match.group(2))
        for match in re.finditer(
            r"\{\s*key:\s*'([^']+)',\s*label:\s*'([^']+)'", block.group(1)
        )
    ]


def _frontend_five_year_segments() -> list[tuple[str, str]]:
    """解析 `useAgingConfig.ts` 的 `PRESET_SEGMENTS.FIVE_YEAR`（6 条 `(key, label)`）。"""
    text = _AGING_CONFIG.read_text(encoding="utf-8")
    block = re.search(r"FIVE_YEAR:\s*\[(.*?)\n\s*\],", text, re.S)
    assert block, "PRESET_SEGMENTS.FIVE_YEAR 块不再存在 —— 账龄真源被重构"
    return [
        (match.group(1), match.group(2))
        for match in re.finditer(
            r"\{\s*key:\s*'([^']+)',\s*label:\s*'([^']+)'", block.group(1)
        )
    ]


class TestThreeSourceColumnLock:
    """**Validates: Requirements 6.12**

    契约的 39 个字段既不能自造、也不能只对着 Excel 对 —— OO 侧写回的是 HTML store 的
    键，两边键名不一致就会静默丢字段。这一组把三个真源锁在一起。
    """

    def test_scalar_columns_match_the_frontend_column_defs_in_order(self) -> None:
        frontend = _frontend_fixed_columns()
        assert len(frontend) == 21, frontend
        assert [key for key, _label in frontend] == [
            path for _k, _c, _m, _v, path, _l in P.SCALAR_FIELD_SPECS
        ]

    def test_aging_segments_match_the_frontend_aging_preset(self) -> None:
        frontend = _frontend_five_year_segments()
        assert len(frontend) == 6, frontend
        assert tuple(frontend) == P.AGING_SEGMENTS

    def test_aging_leaf_labels_match_the_template_second_level_header(
        self, worksheet: Any
    ) -> None:
        compared = 0
        for _prefix, _cell, columns, _label in P.AGING_GROUPS:
            for column, (_key, leaf_label) in zip(columns, P.AGING_SEGMENTS):
                assert worksheet[f"{column}{P.HEADER_LEAF_ROW}"].value == leaf_label
                compared += 1
        assert compared == 18, compared

    def test_json_paths_are_distinct_and_cover_the_row_shape(self) -> None:
        paths = [spec[4] for spec in P.MANAGED_FIELD_SPECS]
        assert len(set(paths)) == 39
        nested = [path for path in paths if "/" in path]
        assert len(nested) == 18
        assert {path.split("/")[0] for path in nested} == {
            prefix for prefix, _c, _cols, _l in P.AGING_GROUPS
        }
        # store 行里 `rowId` 之外恰好 39 个叶子（22 标量键含 rowId ⇒ 21 + 18）。
        row = store_rows(1)[0]
        leaves = sum(
            len(value) if isinstance(value, dict) else 1
            for key, value in row.items()
            if key != P.ROW_IDENTITY_STORE_KEY
        )
        assert leaves == 39, row.keys()

    def test_column_keys_are_snake_case_projections_of_the_json_paths(self) -> None:
        for column_key, _col, _mode, _vt, path, _label in P.MANAGED_FIELD_SPECS:
            expected = "_".join(P._snake(part) for part in path.split("/"))
            assert column_key == expected, (column_key, path)


# ═══════════════════════════════════════════════════════════════════════════
# 5. 发布 DAG 单向
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishDagIsOneWay:
    """**Validates: Requirements 12.1**"""

    def test_template_payload_has_no_self_or_forward_reference(self) -> None:
        from app.services.workpaper_sync.definitions import validate_template_payload

        payload = P.template_definition_payload()
        validate_template_payload(payload)
        assert payload["template_sha256"] == P.TEMPLATE_SHA256
        assert payload["authority_root"] == "backend/wp_templates"

    def test_instrumentation_payload_references_template_only(self) -> None:
        from app.services.workpaper_sync.definitions import (
            validate_instrumentation_payload,
        )

        payload = P.instrumentation_definition_payload()
        validate_instrumentation_payload(payload)
        assert payload["template_definition_sha256"] == canonical_digest(
            P.template_definition_payload()
        )
        blob = json.dumps(payload, ensure_ascii=False)
        assert '"contract_' not in blob and '"bundle_' not in blob

    def test_contract_payload_references_both_and_no_bundle(self, contract: Any) -> None:
        from app.services.workpaper_sync.definitions import validate_contract_payload

        payload = dict(contract.canonical_payload)
        validate_contract_payload(payload)
        assert payload["template_definition_sha256"] == canonical_digest(
            P.template_definition_payload()
        )
        assert payload["instrumentation_definition_sha256"] == canonical_digest(
            P.instrumentation_definition_payload()
        )
        blob = json.dumps(payload, ensure_ascii=False)
        assert '"definition_bundle_' not in blob and '"bundle_' not in blob

    def test_authority_model_is_projection_contract(self) -> None:
        from app.services.workpaper_sync.definitions import (
            validate_authority_model_payload,
        )

        payload = P.authority_model_payload()
        model = validate_authority_model_payload(payload)
        assert model is AuthorityModel.projection_contract
        assert payload["merge_model"] == "stable_field_three_way"

    def test_instrumentation_sheet_key_matches_the_contract(self, contract: Any) -> None:
        payload = P.instrumentation_definition_payload()
        assert payload["managed_sheets"][0]["sheet_key"] == P.SHEET_KEY
        assert contract.sheets[0].sheet_key == P.SHEET_KEY

    def test_instrumentation_declares_no_disproved_anchor(self) -> None:
        payload = json.dumps(P.instrumentation_definition_payload(), ensure_ascii=False)
        for anchor in ("sheet_id", "sheet_display_name"):
            assert f'"anchor": "{anchor}"' not in payload
        assert X.TABLE_SHEET_ANCHOR in payload


# ═══════════════════════════════════════════════════════════════════════════
# 6. 866KB 载荷拆分：整 JSON 不当一个字段
# ═══════════════════════════════════════════════════════════════════════════


class TestStorePayloadSplit:
    """**Validates: Requirements 6.9 / 6.12**"""

    def test_split_yields_one_field_per_column_per_row(self, contract: Any) -> None:
        """`N` 行 ⇒ `N × 39` 个 stable field，**不是** 1 个（整 JSON 一个字段）。"""
        rows = store_rows(7)
        projection = P.build_store_projection(rows, contract=contract)
        assert len(projection.values) == 7 * 39 == 273
        assert len(projection.row_keys[P.ROWS_TABLE_KEY]) == 7
        projection.assert_matches_contract(contract)
        # 键里带的是 rowId 而不是下标。
        assert all("dr-fixture-" in key for key in projection.values)
        assert not any(re.search(r"/\d+/", key) for key in projection.values)

    def test_nested_aging_leaves_become_their_own_fields(self, contract: Any) -> None:
        rows = store_rows(1)
        rows[0]["agingPrior"]["y2to3"] = 4321.5
        projection = P.build_store_projection(rows, contract=contract)
        key = P.stable_key_for("aging_prior_y2to3", rows[0][P.ROW_IDENTITY_STORE_KEY])
        assert projection.values[key].value == 4321.5
        # 嵌套对象本身**不是**一个字段。
        assert P.stable_key_for("aging_prior", rows[0][P.ROW_IDENTITY_STORE_KEY]) not in (
            projection.values
        )

    def test_row_identity_comes_from_the_payload_not_the_index(self, contract: Any) -> None:
        rows = store_rows(3)
        rows.reverse()  # 重排：行身份不得随位置变化
        projection = P.build_store_projection(rows, contract=contract)
        assert projection.row_keys[P.ROWS_TABLE_KEY] == (
            "dr-fixture-00002",
            "dr-fixture-00001",
            "dr-fixture-00000",
        )

    def test_missing_row_identity_fails_closed(self) -> None:
        rows = store_rows(2)
        del rows[1][P.ROW_IDENTITY_STORE_KEY]
        with pytest.raises(P.StorePayloadError, match="缺少稳定行身份"):
            list(P.iter_store_rows(rows))

    def test_duplicate_row_identity_fails_closed(self) -> None:
        rows = store_rows(2)
        rows[1][P.ROW_IDENTITY_STORE_KEY] = rows[0][P.ROW_IDENTITY_STORE_KEY]
        with pytest.raises(P.StorePayloadError, match="重复行身份"):
            list(P.iter_store_rows(rows))

    def test_non_array_payload_fails_closed(self) -> None:
        with pytest.raises(P.StorePayloadError, match="必须是行对象数组"):
            list(P.iter_store_rows(json.dumps({"rows": []})))

    def test_non_object_element_fails_closed(self) -> None:
        with pytest.raises(P.StorePayloadError, match="不是对象"):
            list(P.iter_store_rows(json.dumps([1, 2, 3])))

    def test_invalid_json_fails_closed(self) -> None:
        with pytest.raises(P.StorePayloadError, match="不是合法 JSON"):
            list(P.iter_store_rows("[{"))

    def test_bytes_and_text_and_parsed_inputs_agree(self, contract: Any) -> None:
        rows = store_rows(4)
        text = json.dumps(rows, ensure_ascii=False)
        from_text = P.build_store_projection(text, contract=contract)
        from_bytes = P.build_store_projection(text.encode("utf-8"), contract=contract)
        from_parsed = P.build_store_projection(rows, contract=contract)
        assert set(from_text.values) == set(from_bytes.values) == set(from_parsed.values)
        assert len(from_text.values) == 4 * 39

    def test_failure_kinds_are_reachable_and_mutually_distinct(
        self, manifest: Any, resolution: Any
    ) -> None:
        """两个错误码各真触发一次，且集合基数 == 2（合并成一个会让较早分支不可达）。"""
        codes: set[str] = set()
        with pytest.raises(P.StorePayloadError) as store_exc:
            list(P.iter_store_rows("[{"))
        codes.add(str(store_exc.value.error_code))
        payload = {**manifest, "entries": []}
        with pytest.raises(P.PilotSelectionError) as sel_exc:
            P.assert_pilot_entry_selectable(manifest=payload, resolution=resolution)
        codes.add(str(sel_exc.value.error_code))
        assert codes == {
            "sync_pilot_store_payload_invalid",
            "sync_pilot_selection_invalid",
        }, codes
        assert len(codes) == 2

    def test_split_uses_the_contract_as_the_spec_source(self, contract: Any) -> None:
        """`split_store_row` 的 spec 必须来自 contract（写错 key 立刻炸，不静默产字段）。"""
        rows = store_rows(1)
        identity = rows[0][P.ROW_IDENTITY_STORE_KEY]
        emitted = list(
            P.split_store_row(rows[0], row_identity=identity, contract=contract)
        )
        assert len(emitted) == 39
        for stable_key, _value, spec in emitted:
            assert stable_key.startswith(f"{P.ROWS_TABLE_KEY}/{identity}/")
            assert spec.mode in tuple(FieldMode)
        modes = [spec.mode for _k, _v, spec in emitted]
        assert modes.count(FieldMode.formula) == 3
        assert modes.count(FieldMode.editable) == 36


# ═══════════════════════════════════════════════════════════════════════════
# 7. Property 60：预算 N-1 / N / N+1，且真挂在两条生产路径上
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty60BudgetsFailVisible:
    """**Validates: Requirements 14.11**"""

    def test_row_budget_boundaries_on_the_store_split(self, contract: Any) -> None:
        """三侧真样本：`L-1` / `L` 行通过、`L+1` 行拒绝（观测量相对固定预算）。"""
        limit = 5
        limits = scaled_limits(max_table_rows=limit)
        for count in (limit - 1, limit):
            projection = P.build_store_projection(
                store_rows(count), contract=contract, limits=limits
            )
            assert len(projection.row_keys[P.ROWS_TABLE_KEY]) == count
        with pytest.raises(BudgetExceededError) as exc:
            P.build_store_projection(
                store_rows(limit + 1), contract=contract, limits=limits
            )
        assert exc.value.budget == "max_table_rows"
        assert exc.value.observed == limit + 1
        assert exc.value.limit == limit

    def test_field_budget_boundaries_on_the_store_split(self, contract: Any) -> None:
        rows = store_rows(4)
        total = 4 * 39
        for limit in (total - 1, total, total + 1):
            limits = scaled_limits(max_projection_fields=limit)
            if limit < total:
                with pytest.raises(BudgetExceededError) as exc:
                    P.build_store_projection(rows, contract=contract, limits=limits)
                assert exc.value.budget == "max_projection_fields"
                assert exc.value.observed == total
            else:
                assert len(
                    P.build_store_projection(rows, contract=contract, limits=limits).values
                ) == total

    def test_production_limits_are_the_single_source(self) -> None:
        """本 pilot 不含任何阈值数字：预算全部来自 `workpaper_sync_limits` 配置。"""
        limits = load_limits()
        assert limits.max_table_rows == 100_000
        assert limits.max_projection_fields == 200_000
        source = Path(P.__file__).read_text(encoding="utf-8")
        for number in ("100000", "200000", "50 * 1024", "16777216", "262144"):
            assert number not in source, number

    def test_row_budget_is_wired_into_extract(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
    ) -> None:
        """`N`（=13 行）通过、`N-1` 拒绝 —— 预算门真的在 extract 里跑。"""
        ok = extract(
            base_path,
            definitions,
            binding,
            limits=scaled_limits(max_table_rows=EXPECTED_TEMPLATE_ROW_COUNT),
        )
        assert ok.stats.table_row_counts[P.ROWS_TABLE_KEY] == EXPECTED_TEMPLATE_ROW_COUNT
        with pytest.raises(BudgetExceededError) as exc:
            extract(
                base_path,
                definitions,
                binding,
                limits=scaled_limits(max_table_rows=EXPECTED_TEMPLATE_ROW_COUNT - 1),
            )
        assert exc.value.budget == "max_table_rows"
        assert exc.value.observed == EXPECTED_TEMPLATE_ROW_COUNT

    def test_field_budget_is_wired_into_extract(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
    ) -> None:
        total = EXPECTED_TEMPLATE_ROW_COUNT * 39
        # 🔴 BP-21：468 = 12 受管行 × 39 字段（原 507 = 13 × 39，那 13 行含占位行）
        assert total == 468
        extract(
            base_path, definitions, binding, limits=scaled_limits(max_projection_fields=total)
        )
        with pytest.raises(BudgetExceededError) as exc:
            extract(
                base_path,
                definitions,
                binding,
                limits=scaled_limits(max_projection_fields=total - 1),
            )
        assert exc.value.budget == "max_projection_fields"

    def test_zip_entry_budget_is_wired_into_extract(
        self,
        base_path: Path,
        base_bytes: bytes,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
    ) -> None:
        import zipfile

        with zipfile.ZipFile(base_path) as zf:
            entries = len([n for n in zf.namelist() if not n.endswith("/")])
        extract(base_path, definitions, binding, limits=scaled_limits(max_zip_entries=entries))
        with pytest.raises(BudgetExceededError) as exc:
            extract(
                base_path, definitions, binding, limits=scaled_limits(max_zip_entries=entries - 1)
            )
        assert exc.value.budget == "max_zip_entries"

    def test_compressed_size_budget_is_wired_into_extract(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
    ) -> None:
        size = base_path.stat().st_size
        extract(
            base_path, definitions, binding, limits=scaled_limits(max_compressed_bytes=size)
        )
        with pytest.raises(BudgetExceededError) as exc:
            extract(
                base_path,
                definitions,
                binding,
                limits=scaled_limits(max_compressed_bytes=size - 1),
            )
        assert exc.value.budget == "max_compressed_bytes"

    def test_budget_abort_leaves_no_truncated_sidecar(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
    ) -> None:
        """越界中止时不得留下被截断的 sidecar —— 留下就是「静默截断」。"""
        sidecar = workdir / "aborted.ndjson.gz"
        with pytest.raises(BudgetExceededError):
            extract(
                base_path,
                definitions,
                binding,
                limits=scaled_limits(max_projection_fields=5),
                sidecar_path=sidecar,
            )
        assert not sidecar.exists()


# ═══════════════════════════════════════════════════════════════════════════
# 8. 分块 sidecar（Requirement 6.12 / Property 29 的反读侧）
# ═══════════════════════════════════════════════════════════════════════════


class TestChunkedSidecarAndRoundtrip:
    """**Validates: Requirements 6.11 / 6.12**"""

    def test_baseline_extract_reads_back_every_managed_field(
        self, base_outcome: X.ExcelExtractOutcome, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        assert base_outcome.stats.field_count == EXPECTED_TEMPLATE_ROW_COUNT * 39 == 468
        assert base_outcome.stats.table_row_counts == {
            P.ROWS_TABLE_KEY: EXPECTED_TEMPLATE_ROW_COUNT
        }
        assert base_outcome.stats.carrier_tier is ExtractCarrierTier.instrumented_identity
        # 🔴 BP-22 前这里是「每行一条 boolean 缺口异常」，现在**零异常**
        #    （见 `TestBooleanCellRoundTripsThroughARealOoxmlBooleanCell`）。
        assert base_outcome.anomalies == (), [
            (a.kind.value, a.stable_field_key, a.detail[:80])
            for a in base_outcome.anomalies
        ]
        source_uuids = set(instrumented.row_uuids.values())
        assert len(source_uuids) == EXPECTED_TEMPLATE_ROW_COUNT
        for identity in source_uuids:
            assert P.stable_key_for("customer_name", identity) in base_outcome.projection.values
        assert not any(re.search(r"/\d+/", key) for key in base_outcome.projection.values)

    def test_formula_columns_are_read_as_cached_values_with_formula_inventory(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        seen = 0
        for identity in base_outcome.projection.row_keys[P.ROWS_TABLE_KEY]:
            row = int(identity.rsplit("-", 1)[1])
            for column, template in P.FORMULA_TEMPLATES.items():
                column_key = next(
                    spec[0] for spec in P.MANAGED_FIELD_SPECS if spec[1] == column
                )
                key = P.stable_key_for(column_key, identity)
                assert base_outcome.formula_inventory[key] == template.format(r=row)
                seen += 1
        # 🔴 BP-21：36 = 3 列 × **12 受管行**。模板物理上有 39 个，第 13 行是 `A25`
        #    那行排版占位 —— 它已不在受管区，其公式属未管理区域，不进 formula_inventory。
        assert seen == 3 * EXPECTED_TEMPLATE_ROW_COUNT == 36, seen

    def test_unmanaged_region_coverage_is_not_empty(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """8 个 aspect 的覆盖计数全部 > 0（空集恒等价不算通过）。"""
        coverage = dict(base_outcome.unmanaged.coverage)
        assert set(coverage) == set(X.UNMANAGED_ASPECTS), sorted(coverage)
        assert len(coverage) == 8
        zero = sorted(name for name, count in coverage.items() if count <= 0)
        assert zero == [], zero
        assert base_outcome.unmanaged.part_count >= 40

    def test_sidecar_is_gzip_ndjson_and_round_trips(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
    ) -> None:
        sidecar = workdir / "projection.ndjson.gz"
        outcome = extract(base_path, definitions, binding, sidecar_path=sidecar)
        assert sidecar.read_bytes()[:2] == b"\x1f\x8b", "不是 gzip 流"
        header, fields = X.read_projection_sidecar(sidecar)
        assert header["contract_id"] == P.PILOT_ADAPTER_ID
        assert header["table_key"] == P.ROWS_TABLE_KEY
        assert header["sheet"] == P.MANAGED_SHEET
        assert len(fields) == outcome.stats.field_count == 468
        by_key = {row["stable_key"]: row for row in fields}
        for key, value in outcome.projection.values.items():
            assert by_key[key]["value_type"] == value.value_type.value
            assert by_key[key]["mode"] == value.mode.value
            assert by_key[key]["row_key"] == value.row_key

    def test_sidecar_bytes_are_reproducible(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
    ) -> None:
        first = workdir / "repro_a.gz"
        second = workdir / "repro_b.gz"
        extract(base_path, definitions, binding, sidecar_path=first)
        extract(base_path, definitions, binding, sidecar_path=second)
        assert first.read_bytes() == second.read_bytes()

    def test_sidecar_never_holds_whole_projection_in_one_buffer(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
    ) -> None:
        """峰值内存落在 `tracemalloc` 实测上，不是「代码里写了 flush」。"""
        import tracemalloc

        sidecar = workdir / "peak.gz"
        tracemalloc.start()
        try:
            extract(base_path, definitions, binding, sidecar_path=sidecar)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert peak < load_limits().peak_memory_budget_bytes, peak

    def test_chunking_is_observable_and_driven_by_limits(
        self,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
    ) -> None:
        """缩小内存预算 ⇒ 块数真的变多（`chunk_count` 是实测量，不是声明值）。"""
        limits = load_limits()
        assert X.rows_per_chunk(limits) == 64
        assert extract(base_path, definitions, binding).stats.chunk_count == 1
        small = scaled_limits(peak_memory_budget_bytes=limits.chunk_bytes * 4)
        outcome = extract(base_path, definitions, binding, limits=small)
        assert outcome.stats.rows_per_chunk == 4
        # 🔴 BP-21：12 受管行 / 每块 4 行 = 3 块（原 13 行向上取整得 4 块）
        assert outcome.stats.chunk_count == -(-EXPECTED_TEMPLATE_ROW_COUNT // 4) == 3
        assert (
            outcome.projection.values
            == extract(base_path, definitions, binding).projection.values
        )

    def test_sidecar_rejects_wrong_schema_version(self, workdir: Path) -> None:
        bad = workdir / "bad_schema.gz"
        with gzip.open(bad, "wt", encoding="utf-8") as fh:
            fh.write(json.dumps({"schema_version": "excel-projection-sidecar:v0"}) + "\n")
        with pytest.raises(X.ExcelExtractError, match="schema"):
            X.read_projection_sidecar(bad)

    def test_roundtrip_verifier_passes_on_the_extracted_projection(
        self, base_outcome: X.ExcelExtractOutcome, contract: Any
    ) -> None:
        """Property 29 的纯判据侧：反读结果与自身比对必须等值且**比对过非零个键**。"""
        report = X.verify_roundtrip_equivalence(
            expected=base_outcome.projection,
            extracted=base_outcome.projection,
            contract=contract,
        )
        assert report.equivalent is True
        assert len(report.compared_keys) == EXPECTED_TEMPLATE_ROW_COUNT * 36 == 432
        assert report.missing_keys == () and report.unexpected_keys == ()

    def test_roundtrip_verifier_catches_a_single_changed_field(
        self, base_outcome: X.ExcelExtractOutcome, contract: Any
    ) -> None:
        """反向自检：改一个 editable 字段必须不等值（否则上一条是空判据）。"""
        identity = base_outcome.projection.row_keys[P.ROWS_TABLE_KEY][0]
        key = P.stable_key_for("customer_name", identity)
        values = dict(base_outcome.projection.values)
        original = values[key]
        values[key] = FieldValue(
            stable_key=key,
            value="被 OO 改过的客户名",
            value_type=original.value_type,
            mode=original.mode,
            row_key=original.row_key,
        )
        tampered = Projection(
            contract_id=base_outcome.projection.contract_id,
            semantic_version=base_outcome.projection.semantic_version,
            document_type=base_outcome.projection.document_type,
            values=values,
            row_keys=base_outcome.projection.row_keys,
        )
        report = X.verify_roundtrip_equivalence(
            expected=base_outcome.projection, extracted=tampered, contract=contract
        )
        assert report.equivalent is False
        assert key in (report.first_difference or "")


# ═══════════════════════════════════════════════════════════════════════════
# 9. Property oracle 落点（P27 / P29 / P49 / P60 / P69）
# ═══════════════════════════════════════════════════════════════════════════

#: 本任务要验的 5 条 Property → 它在 **本 entry 自己的** required scenario set 里的落点。
#:
#: 🔴 P27 落在 merge 家族两条而不是 `dynamic_row_add_delete_reorder_copy`：后者是 AC 6.9
#: 自己的场景，但它只在 `mount_cardinality == "dynamic"` 时进 required set，而那个字段量的
#: 是前端宿主挂载基数 ⇒ 对**任何 xlsx entry** 都不可达（见
#: :data:`P.UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY`，
#: 并由 `TestUpstreamDebtsAreVisibleFacts` 把它变成可打红的实测事实）。
PROPERTY_ORACLE_LANDING: dict[str, tuple[str, ...]] = {
    "P27": ("different_field_merge", "same_field_conflict_resolve"),
    "P29": ("oo_to_html",),
    "P49": ("identity_retention",),
    "P60": ("oo_to_html",),
    "P69": ("single_participant_close",),
}


class TestPropertyOracleLanding:
    """**Validates: Requirements 12.10 / 14.1**"""

    def test_every_property_lands_on_a_registered_oracle(self) -> None:
        """五条 Property 各有 oracle，**且**该 oracle 真的在本 entry 的 required set 里。"""
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        required = set(
            derive_for_manifest_entry(entry, authority_model=P.AUTHORITY_MODEL).scenario_ids
        )
        assert len(PROPERTY_ORACLE_LANDING) == 5, sorted(PROPERTY_ORACLE_LANDING)
        for prop, scenarios in sorted(PROPERTY_ORACLE_LANDING.items()):
            assert scenarios, prop
            for scenario_id in scenarios:
                assert scenario_id in PH.SCENARIO_ORACLES, (prop, scenario_id)
                assert scenario_id in required, (prop, scenario_id)

    def test_field_level_properties_are_not_substituted_away(self) -> None:
        """`projection_contract` ⇒ AC 12.12 的字段级两场景**不得**被替换。"""
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        ids = set(
            derive_for_manifest_entry(entry, authority_model=P.AUTHORITY_MODEL).scenario_ids
        )
        assert "different_field_merge" in ids
        assert "same_field_conflict_resolve" in ids
        assert "authoritative_revision_conflict" not in ids
        assert "no_silent_overwrite" not in ids

    def test_black_box_scenarios_stay_unverifiable_without_real_onlyoffice(self) -> None:
        """P29/P49/P60 的落点都需要真实 OO ⇒ 今天只能 UNVERIFIABLE。"""
        offline_only = {
            "different_field_merge",
            "same_field_conflict_resolve",
            "single_participant_close",
        }
        need_black_box = {
            scenario_id
            for scenarios in PROPERTY_ORACLE_LANDING.values()
            for scenario_id in scenarios
        }
        assert need_black_box - offline_only == {"oo_to_html", "identity_retention"}
        for scenario_id in sorted(need_black_box - offline_only):
            assert PH.SCENARIO_ORACLES[scenario_id].needs_black_box, scenario_id

    def test_pilot_class_stays_unverifiable_until_server_recompute(self) -> None:
        """Property 49 的后半句：文档声明不得计为通过。"""
        assessment = PH.assess_pilot_classes()[PH.PilotClass.d2_large_json]
        assert assessment.status is PH.PilotClassStatus.unverifiable
        assert assessment.verified_entry_ids == ()
        assert PH.pilot_coverage_summary()["all_verified"] is False

    def test_oracle_production_refs_resolve(self) -> None:
        """落点场景在生产上的实现符号必须真能 import + getattr（不是死声明）。"""
        checked = 0
        for scenarios in PROPERTY_ORACLE_LANDING.values():
            for scenario_id in scenarios:
                refs = PH.resolve_production_refs(PH.SCENARIO_ORACLES[scenario_id])
                assert refs, scenario_id
                checked += len(refs)
        assert checked >= 6, checked


# ═══════════════════════════════════════════════════════════════════════════
# 10. 两条登记的上游缺口：可打红的实测事实，不是注释
# ═══════════════════════════════════════════════════════════════════════════


class TestUpstreamDebtsAreVisibleFacts:
    """**Validates: Requirements 6.9 / 12.10**"""

    def test_published_identity_observer_debt_is_cleared_by_task75(self) -> None:
        """Task 75 已交付公共观测器 ⇒ 本 pilot 的那条欠账登记必须**已删**且函数是真实现。

        判据三条，逐条可打红：① 模块不再导出该常量、源码零出现；② `resolve_published_
        frozen_definitions()` 顶层没有 `raise`（不是「删了登记却仍 fail closed」）；
        ③ 它真的 `await` 了共享观测器（AST 判据，不是字符串出现即算）。
        """
        import ast
        import inspect

        name = "UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER"
        assert not hasattr(P, name)
        assert name not in (P.__all__ or ())
        source = Path(inspect.getsourcefile(P) or "").read_text(encoding="utf-8")
        assert name not in source
        node = next(
            n
            for n in ast.walk(ast.parse(source))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "resolve_published_frozen_definitions"
        )
        assert [s for s in node.body if isinstance(s, ast.Raise)] == [], (
            "欠账登记删了但函数顶层仍 raise ⇒ 中间形态①"
        )
        awaited = {
            inner.value.func.id
            for inner in ast.walk(node)
            if isinstance(inner, ast.Await)
            and isinstance(inner.value, ast.Call)
            and isinstance(inner.value.func, ast.Name)
        }
        assert "observe_published_frozen_definitions" in awaited, sorted(awaited)

    def test_resolve_published_definitions_never_returns_none(self) -> None:
        """找不到载体必须抛可分辨异常，绝不返回 None（fail-open 是最贵的一类缺陷）。

        Task 75 起抛的是观测器的 `RepresentationShapeError`（「representation 为空 ⇒ 无法确定
        project scope」），而不是原先那条欠账 `PilotSelectionError`。意图一字不改：**不返回
        None、不返回空 identity**。
        """
        import asyncio

        from app.services.workpaper_sync.published_identity_observer import (
            RepresentationShapeError,
        )

        with pytest.raises(RepresentationShapeError):
            asyncio.run(
                P.resolve_published_frozen_definitions(
                    session=None, representation=None, contract=P.load_pilot_contract()
                )
            )

    def test_dynamic_family_gate_reads_mount_cardinality_not_the_contract(self) -> None:
        """源码级判据：`DYNAMIC_SCENARIOS` 的唯一门就是 `mount_cardinality == dynamic`。"""
        from app.services.workpaper_sync import evidence as EV

        source = Path(EV.__file__).read_text(encoding="utf-8")
        assert 'if str(payload.get("mount_cardinality") or "") == "dynamic":' in source
        assert "scenarios.extend(DYNAMIC_SCENARIOS)" in source
        assert {scenario.scenario_id for scenario in EV.DYNAMIC_SCENARIOS} == {
            "dynamic_row_add_delete_reorder_copy",
            "dynamic_column_stable_keys",
        }

    def test_dynamic_family_is_structurally_unreachable_for_every_xlsx_entry(self) -> None:
        """实测：全 manifest 只有 1 条 dynamic，且是 docx ⇒ AC 6.9 场景对 xlsx 不可达。"""
        observed = P.assert_dynamic_family_is_unreachable_for_xlsx_entries()
        assert observed["xlsx_dynamic"] == ()
        assert observed["dynamic"] == ("docx/gt-wp-renderer",), observed["dynamic"]
        assert observed["total"] == 186, observed["total"]

    def test_debt_note_is_retracted_when_upstream_fixes_the_gate(
        self, manifest: dict[str, Any]
    ) -> None:
        """反向自检：给本 entry 的 profile 打上 dynamic ⇒ 欠账函数必须抛（提醒撤销登记）。"""
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["scenario_profile"]["mount_cardinality"] = "dynamic"
        with pytest.raises(P.PilotSelectionError, match="不再对 xlsx 侧"):
            P.assert_dynamic_family_is_unreachable_for_xlsx_entries(manifest=patched)

    def test_this_entry_really_has_a_dynamic_row_table(self, contract: Any) -> None:
        """欠账之所以是缺口：本 entry 的契约**确实**声明了动态行（不是它不需要）。"""
        table = contract.sheets[0].tables[0]
        assert table.has_dynamic_rows is True
        assert table.delete_policy is not None
        assert REAL_PAYLOAD_ROWS == 1260 > EXPECTED_TEMPLATE_ROW_COUNT

    def test_debt_note_names_the_owner_and_the_fix(self) -> None:
        note = P.UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY
        assert "mount_cardinality" in note
        assert "dynamic_row_add_delete_reorder_copy" in note
        assert "owner" in note

    def test_remaining_debts_are_registered_and_mutually_distinct(self) -> None:
        """剩余欠账各自独立可辨（合成一条会让其余的撤销条件无处可查）。

        已结清并删除的两条：
        * `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER` —— Task 75；
        * `UPSTREAM_DEBT_BOOLEAN_CELL_ROUNDTRIP` —— **BP-22**（改走 OOXML 真布尔格
          `t="b"`，见 `TestBooleanCellRoundTripsThroughARealOoxmlBooleanCell`）。

        计数**从 `__all__` 现算**（不写死数字），于是再删/再加一条都会被这里抓到。
        """
        notes = {
            P.UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY,
        }
        exported = [n for n in (P.__all__ or ()) if n.startswith("UPSTREAM_DEBT_")]
        assert len(notes) == len(exported), sorted(exported)
        for note in notes:
            assert note.startswith("Task 41 欠账"), note[:40]
            assert "owner" in note, note[:40]


class TestBooleanCellRoundTripsThroughARealOoxmlBooleanCell:
    """**Validates: Requirements 6.11 / 6.12**

    ═══ BP-22：这一组从「钉住缺陷」翻成「钉住修复」═════════════════════════════

    原状（`UPSTREAM_DEBT_BOOLEAN_CELL_ROUNDTRIP`，已删）：`value_type=boolean` 的 Excel
    受管格端到端**不自洽** —— `_write_kind_for` 把它归 `number_literal` ⇒ 落盘
    `<c r="AK13"><v>1</v></c>`（无 `t`）⇒ extract 用 openpyxl 读回 **int 1** ⇒
    `merge.normalize_value(1, boolean)` 明令拒绝折叠 ⇒ **每一行**一条
    `type_normalization_failure`。

    它原本是**看不见**的：materialize 写得下去、extract 读得回来、roundtrip verifier 还会
    因为 `True == 1` 在 Python 里为真而**误判等值**，只有 schema 异常那一路会暴露它。
    首版发布链把它顶到地面：D2 卡在 `roundtrip_verified`，
    `ValueNormalizationError: boolean 字段只接受真 bool 或 'true'/'false'，实得 0`。

    修法取「写入侧落 OOXML 真布尔格 `t="b"`」而**不是**「让 `normalize_value` 折叠 0/1」：
    后者会让「整数 1 被当成 true」这类真实类型错误静默通过，那条拒绝是对的。
    openpyxl 写真 `bool` 时本来就落 `t="b"`（实测），读回是真 `bool` ⇒ 往返自洽；
    也消除了两条写入路径（zip/XML 与 openpyxl）此前的形态分歧。
    """

    def test_materializer_writes_boolean_as_a_real_ooxml_boolean_cell(self) -> None:
        """判据落在**落盘字节**上，不只是枚举值。

        只断言 `CellWriteKind` 时，把 `_cell_xml` 的 `t="b"` 分支删掉仍会判 GREEN
        （枚举没变）—— 那就成了「改了没红」的守卫缺陷。
        """
        from app.services.workpaper_sync.excel_materialize import (
            CellWrite,
            CellWriteKind,
            EditableCellWriteError,
            _cell_xml,
            _write_kind_for,
        )

        spec = next(
            field
            for field in P.load_pilot_contract().all_fields()
            if field.column_key == "is_confirmation"
        )
        assert spec.value_type.value == "boolean"
        assert _write_kind_for(spec) is CellWriteKind.boolean_literal

        def _xml(value: Any) -> str:
            return _cell_xml(
                coord="AK13",
                style="7",
                write=CellWrite(
                    coord="AK13",
                    kind=CellWriteKind.boolean_literal,
                    value=value,
                    stable_field_key=P.stable_key_for("is_confirmation", "GTROW-X-0013"),
                ),
            )

        # 真布尔 ⇒ `t="b"`；样式恒带回（AC 3.5）
        assert _xml(True) == '<c r="AK13" s="7" t="b"><v>1</v></c>'
        assert _xml(False) == '<c r="AK13" s="7" t="b"><v>0</v></c>'
        # `None` ⇒ 空格而不是 `<v>0</v>`：后者把「未填」变成「填了 false」，
        # 对「是否函证」这类审计字段是实质性语义错误
        assert _xml(None) == '<c r="AK13" s="7"/>'
        assert "<v>" not in _xml(None)

        # 非 bool 值 fail closed —— 「0/1 不得当布尔写入」的正面判据
        for wrong in (0, 1, "true", "1"):
            with pytest.raises(EditableCellWriteError, match="value_type=boolean"):
                _xml(wrong)

    def test_number_literal_no_longer_claims_the_boolean_type(self) -> None:
        """数值族**不再**包含 boolean —— 防止哪天有人把它加回去。

        判据用 `_write_kind_for` 逐 `value_type` 现算，不抄一份清单：抄一份时把生产里的
        boolean 分支删掉，这条仍会按自己那份清单判 GREEN。
        """
        from app.services.workpaper_sync.contracts import FieldMode, ValueType
        from app.services.workpaper_sync.excel_materialize import (
            CellWriteKind,
            _write_kind_for,
        )

        class _S:
            def __init__(self, value_type: Any) -> None:
                self.mode = FieldMode.editable
                self.value_type = value_type

        by_kind: dict[Any, list[str]] = {}
        for value_type in ValueType:
            by_kind.setdefault(_write_kind_for(_S(value_type)), []).append(
                value_type.value
            )
        assert by_kind[CellWriteKind.boolean_literal] == ["boolean"]
        assert "boolean" not in by_kind[CellWriteKind.number_literal]
        assert set(by_kind[CellWriteKind.number_literal]) == {
            "amount",
            "integer",
            "rate",
            "ratio",
        }

    def test_the_upstream_debt_registration_is_gone(self) -> None:
        """欠账登记必须**真删**，不是改成注释留着。

        判据用 `hasattr` 而不是查字符串：字符串判据会被 docstring 里的复盘说明满足。
        """
        assert not hasattr(P, "UPSTREAM_DEBT_BOOLEAN_CELL_ROUNDTRIP")
        exported = [n for n in (P.__all__ or ()) if n.startswith("UPSTREAM_DEBT_")]
        assert "UPSTREAM_DEBT_BOOLEAN_CELL_ROUNDTRIP" not in exported

    def test_merge_refuses_to_fold_the_written_shape(self) -> None:
        from app.services.workpaper_sync.contracts import ValueType
        from app.services.workpaper_sync.merge import (
            ValueNormalizationError,
            normalize_value,
        )

        assert normalize_value(True, ValueType.boolean) is True
        for written in (1, 0, "1", "True"):
            with pytest.raises(ValueNormalizationError):
                normalize_value(written, ValueType.boolean)

    def test_extract_reports_no_anomaly_on_the_boolean_column(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """🔴 BP-22 前这里是「每行一条 `type_normalization_failure`」，现在是**零条**。

        分母非空由 `base_outcome` 自己保证（12 行 × 39 字段 = 468 个值都真读出来了），
        所以「零异常」不是空转。
        """
        assert base_outcome.anomalies == (), [
            (a.kind.value, a.stable_field_key, a.detail[:80])
            for a in base_outcome.anomalies
        ]
        assert len(base_outcome.projection.values) == (
            EXPECTED_TEMPLATE_ROW_COUNT * 39
        ), "分母塌了 ⇒「零异常」变成空转"

    def test_the_boolean_column_reads_back_as_real_python_bools(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """真布尔格读回来必须是 `bool`，且两个取值都出现过（不是恒 True/恒 False）。"""
        values = {
            base_outcome.projection.values[
                P.stable_key_for("is_confirmation", identity)
            ].value
            for identity in base_outcome.projection.row_keys[P.ROWS_TABLE_KEY]
        }
        assert values == {True, False}, values
        assert all(isinstance(value, bool) for value in values), values

    def test_a_real_boolean_cell_would_extract_cleanly(
        self,
        instrumented: EI.InstrumentedWorkbook,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
    ) -> None:
        """反向自检：把该列写成真布尔格（`t="b"`）⇒ 异常归零 ⇒ 缺口在**写入形态**上。

        这条是欠账的撤销条件：engine 侧一旦按 `t="b"` 写，本条仍绿而上一条会打红。
        """
        cells: dict[str, Any] = {}
        for row in range(P.FIRST_DATA_ROW, P.LAST_DATA_ROW + 1):
            for _key, column, mode, value_type, _path, _label in P.MANAGED_FIELD_SPECS:
                if mode == "formula":
                    continue
                if value_type == "boolean":
                    cells[f"{column}{row}"] = "__BOOL1__" if row % 2 == 0 else "__BOOL0__"
                elif value_type == "amount":
                    cells[f"{column}{row}"] = 100 + row
                elif value_type == "integer":
                    cells[f"{column}{row}"] = row
                else:
                    cells[f"{column}{row}"] = f"值{column}{row}"
        data = _promote_boolean_cells(
            patch_cells(instrumented.instrumented_bytes, sheet_part, cells), sheet_part
        )
        path = workdir / "real_boolean.xlsx"
        path.write_bytes(data)
        outcome = extract(path, definitions, binding)
        assert outcome.anomalies == (), outcome.anomalies
        assert outcome.stats.field_count == EXPECTED_TEMPLATE_ROW_COUNT * 39 == 468
        values = {
            outcome.projection.values[
                P.stable_key_for("is_confirmation", identity)
            ].value
            for identity in outcome.projection.row_keys[P.ROWS_TABLE_KEY]
        }
        assert values == {True, False}, values


# ═══════════════════════════════════════════════════════════════════════════
# 11. 顺序门：finalize 之前不得注册 adapter / 启用 capability
# ═══════════════════════════════════════════════════════════════════════════


def _descriptor_facts() -> Any:
    from app.services.workpaper_sync.entry_profile import DescriptorFacts, DescriptorMode

    return DescriptorFacts(mode=DescriptorMode.bidirectional, exposes_mode_switch=True)


def _room_facts() -> Any:
    from app.services.workpaper_sync.entry_profile import RoomFacts

    return RoomFacts(shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=True)


class TestOrderingGate:
    """**Validates: Requirements 12.1 / 12.10**"""

    def test_capability_is_not_enabled_before_finalize(self) -> None:
        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        assert capability_of(entry) is Capability.single_onlyoffice
        assert entry["adapter_id"] is None
        with pytest.raises(P.PilotSelectionError, match="manifest capability"):
            P.assert_manifest_capability_enabled()

    def test_capability_predicate_agrees_with_the_ordering_gate(self) -> None:
        """真值判定与顺序门必须**同一套判据**（两处各写一套会悄悄不一致）。"""
        assert P.manifest_capability_enabled() is False
        manifest = json.loads(json.dumps(load_entry_manifest()))
        for item in manifest["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["capability"] = "bidirectional"
                item["adapter_id"] = P.PILOT_ADAPTER_ID
        assert P.manifest_capability_enabled(manifest=manifest) is True
        P.assert_manifest_capability_enabled(manifest=manifest)

    def test_attach_is_a_no_op_before_enablement_and_never_raises(self) -> None:
        """🔴 未启用时接线必须返回空元组、**一次库都不读**，而不是抛异常。

        首轮实测（辐射面 Task 28 的路由守卫 8 例打红）：这里抛 `PilotSelectionError` 会让
        `_registration` / `_apply_durable_incoming` 对**所有** entry 都 500 —— Task 28 的
        fixture 用的 `ENTRY` 正是本 pilot 冻结的这个 entry。判据用 `session=None`：真去读库
        就会 `AttributeError`，所以「返回空元组」同时证明了「没读库」。
        """
        import asyncio

        registry = RG.WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        assert asyncio.run(P.attach_pilot_adapters(registry, session=None)) == ()
        assert registry.registrations() == ()

    def test_ledger_records_adapter_not_registered_yet(self) -> None:
        row = next(
            r
            for r in RG.DELIVERED_PER_ENTRY_CONTRACTS
            if r["contract_id"] == P.PILOT_ADAPTER_ID
        )
        assert row["adapter_registered"] is False
        assert "方可" in row["reason"] or "才启用" in row["reason"] or "后启用" in row["reason"]

    def test_contract_orphan_is_visible_in_the_registry_report(self) -> None:
        """契约有了但 adapter 没注册 ⇒ 必须作为**可见欠账**报出来（不是静默）。"""
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        report = registry.build_report(contract_ids=available_contract_ids())
        assert P.PILOT_ADAPTER_ID in report.contract_files_without_adapter
        assert report.closed is False

    def test_registration_is_refused_while_manifest_says_single_onlyoffice(self) -> None:
        """capability 未启用时注册必须被拒，且拒的原因可分辨。"""

        class _Adapter:
            adapter_id = P.PILOT_ADAPTER_ID
            document_type = "xlsx"
            contract_version = "1.0.0"

            async def read_current_projection(self, ctx: Any) -> Any: ...
            async def stage_projection_mutation(
                self, ctx: Any, merged: Any, **kw: Any
            ) -> Any: ...
            def materialize(self, **kw: Any) -> Any: ...
            def extract(self, **kw: Any) -> Any: ...
            def verify_unmanaged_regions(self, **kw: Any) -> Any: ...

        from app.services.workpaper_sync.entry_profile import EntryProfileDriftError

        registry = RG.WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        with pytest.raises((EntryProfileDriftError, RG.RegistryError)) as exc:
            P.register_pilot_adapter(
                registry,
                adapter=_Adapter(),
                bundle=object(),
                descriptor=_descriptor_facts(),
                room=_room_facts(),
                contract=P.load_pilot_contract(),
            )
        assert getattr(exc.value, "error_code", None), exc.value
        assert registry.registrations() == (), "被拒的注册不得留下半成品"


# ═══════════════════════════════════════════════════════════════════════════
# 12. 生产接线（非 additive 死代码）
# ═══════════════════════════════════════════════════════════════════════════


class TestProductionWiring:
    """**Validates: Requirements 12.1**"""

    def test_router_calls_the_d2_attach_on_both_paths(self) -> None:
        """两个生产接线点都必须真的调用本 pilot 自己的 attach（AST 判据）。"""
        tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
        called_in: dict[str, bool] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in {"_attach_pilot_adapters", "_apply_durable_incoming"}:
                continue
            called_in[node.name] = any(
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "attach_d2_pilot_adapters"
                for inner in ast.walk(node)
            )
        assert called_in.get("_attach_pilot_adapters") is True
        assert called_in.get("_apply_durable_incoming") is True

    def test_router_still_calls_the_checklist_pilot_attach(self) -> None:
        """只加不动：Task 40 的两个调用点必须原样保留（本任务不复用也不顶掉它）。"""
        tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
        called_in: dict[str, bool] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in {"_attach_pilot_adapters", "_apply_durable_incoming"}:
                continue
            called_in[node.name] = any(
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "attach_pilot_adapters"
                for inner in ast.walk(node)
            )
        assert called_in == {
            "_attach_pilot_adapters": True,
            "_apply_durable_incoming": True,
        }, called_in

    def test_both_production_paths_go_through_the_bidirectional_contract_lock(self) -> None:
        """发布与接线**都**必须经 `assert_contract_file_matches_source()` 取契约。

        🔴 Task 40 实测（M26）：判据若只是「守卫自己调那把锁」，把生产路径换成
        `load_pilot_contract()` 后整组测试仍全绿 —— 判据与生产路径脱钩。
        """
        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        sources: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in {"publish_pilot_definitions", "attach_pilot_adapters"}:
                continue
            sources[node.name] = {
                inner.func.id
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
            }
        assert set(sources) == {"publish_pilot_definitions", "attach_pilot_adapters"}, sources
        for name, calls in sorted(sources.items()):
            assert "assert_contract_file_matches_source" in calls, (name, sorted(calls))
            assert "load_pilot_contract" not in calls, (
                f"{name} 直接读磁盘契约 —— 生产路径必须走双向锁"
            )

    def test_pilot_does_not_reuse_the_checklist_bundle_or_contract(self) -> None:
        """任务正文：禁止用 checklist pilot 的 bundle/契约代替本 entry 自己的。

        🔴 判据是**代码路径 + 身份**，不是词面：docstring 里必须能提到另一个 pilot 的
        digest 才说得清「为什么两者不同」（首轮实测过词面判据把这句说明本身判成违规）。
        """
        from app.services.workpaper_sync import pilot_simple_checklist as CHECKLIST

        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any("pilot_simple_checklist" in name for name in imported), imported
        literals = set(_non_docstring_literals(Path(P.__file__)))
        assert CHECKLIST.PILOT_ADAPTER_ID not in literals
        assert CHECKLIST.PILOT_ENTRY_ID not in literals
        assert CHECKLIST.TEMPLATE_RELATIVE_PATH not in literals
        assert CHECKLIST.TEMPLATE_SHA256 not in literals
        assert P.TEMPLATE_SHA256 != CHECKLIST.TEMPLATE_SHA256

    def test_generator_is_the_only_writer_of_the_disk_contract(self) -> None:
        """契约落盘只有生成器一个写入者（生产模块不写 `backend/data/`）。"""
        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        writes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"write_bytes", "write_text", "mkdir", "unlink"}
        }
        assert writes == set(), writes
        generator = (
            _BACKEND / "scripts" / "gen" / "generate_pilot_d2_large_json_contract.py"
        )
        assert generator.is_file()
        assert "build_contract_payload" in generator.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# 13. 本 pilot 不得给 writer/resolver 清册增债（Task 19-20 收口门）
# ═══════════════════════════════════════════════════════════════════════════

_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"

#: 被刻意避开的 ad-hoc 路径拼接**原始形态**（反向自检的输入，不是文档说明）。
_RETIRED_AD_HOC_PATH_SHAPE = '    index_path = _BACKEND_ROOT / "wp_templates" / "_index.json"'


@pytest.fixture(scope="module")
def inventory_generator() -> Any:
    """Task 19 清册生成器本体 —— 判据必须用**它的**分类谓词，不是本文件重写一份。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_t41_wp_inv_gen", _GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPilotIntroducesNoResolverDebt:
    """**Validates: Requirements 12.1**

    本模块每个函数在**真实分类器**下都不得被判成 writer / resolver。Task 40 实测过：
    函数内出现 ``… / "wp_templates" / …`` 这类路径拼接会被 AST 分类器记成一条
    `<ad_hoc_path_construction>` resolver，同时命中 `unadjudicated_resolver` 与
    `non_canonical_resolver_only` 两条 blocking fact，而盖 overlay 标签清不掉。
    """

    def test_no_function_in_this_module_is_classified_as_writer_or_resolver(
        self, inventory_generator: Any
    ) -> None:
        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        classified: dict[str, str] = {}
        checked = 0
        for _parent, function in inventory_generator._iter_functions(tree):
            checked += 1
            facts = inventory_generator._collect_facts(function)
            kind = inventory_generator._classify(facts, delegates_to=[])
            if kind is not None:
                classified[function.name] = kind
        assert checked >= 20, f"只走到 {checked} 个函数 —— 遍历谓词失效，空集恒等价"
        assert classified == {}, (
            f"{Path(P.__file__).name} 给 writer/resolver 清册增债：{classified}"
        )

    def test_the_generator_would_still_flag_the_retired_ad_hoc_path(
        self, inventory_generator: Any
    ) -> None:
        """反向自检：把旧形态喂回去必须仍被判成 resolver（否则上一条是空判据）。"""
        import textwrap

        source = textwrap.dedent(
            f"""
            def _probe() -> set[str]:
                import json
            {_RETIRED_AD_HOC_PATH_SHAPE}
                return set(json.loads(index_path.read_text(encoding="utf-8")))
            """
        )
        function = ast.parse(source).body[0]
        facts = inventory_generator._collect_facts(function)
        assert facts.ad_hoc_paths, "旧形态不再被识别 ⇒ 上一条测试恒真"
        assert inventory_generator._classify(facts, delegates_to=[]) == "resolver"
        assert inventory_generator._resolver_identities(facts.as_dict()) == [
            "<ad_hoc_path_construction>"
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 14. 真实载荷事实的字面量互锁（pg 侧从库里重取一次逐条比对）
# ═══════════════════════════════════════════════════════════════════════════


class TestRealPayloadFactsAreFrozen:
    """**Validates: Requirements 6.12 / 14.11**

    真实 906,239 字节载荷的判据在 pg 守卫里（本文件不连库）。这里把三个实测数字写成
    字面量，pg 侧从 `checklist_responses` 重新取一次并逐条比对 —— 两侧任一漂移都打红。
    """

    def test_frozen_numbers_are_consistent_with_the_declared_shape(self) -> None:
        assert REAL_PAYLOAD_BYTES == 906_239
        assert REAL_PAYLOAD_ROWS == 1_260
        assert REAL_D2_ITEM_COUNT == 24
        # 39 列 × 1260 行 = 49,140 个 stable field（远小于 200,000 field 预算）。
        assert REAL_PAYLOAD_ROWS * EXPECTED_FIELD_COUNT == 49_140
        assert REAL_PAYLOAD_ROWS * EXPECTED_FIELD_COUNT < load_limits().max_projection_fields
        # 载荷量级：AC 6.12 的「866KB+」
        assert 866_000 <= REAL_PAYLOAD_BYTES
        assert REAL_PAYLOAD_BYTES / 1024 == pytest.approx(885.0, abs=0.1)

    def test_store_item_id_is_the_only_item_the_contract_claims(self, contract: Any) -> None:
        """契约只声明 `D2-detail-rows` 一条 item ⇒ 回写不会碰其他 23 条。"""
        blob = json.dumps(contract.canonical_payload, ensure_ascii=False)
        assert blob.count(f'"{P.STORE_ITEM_ID}"') >= 1
        others = re.findall(r'"(D2-(?!detail-rows)[a-z0-9-]+)"', blob)
        assert others == [], others
        declared = {
            item["store_item_id"]
            for item in contract.canonical_payload["sheets"][0]["tables"][0]["fields"]
        }
        assert declared == {P.STORE_ITEM_ID}
