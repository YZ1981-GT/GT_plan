# -*- coding: utf-8 -*-
"""Task 42 离线守卫：H1 分组/动态结构 Excel pilot 的选型、分组表头、骨架策略与 identity。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 42
Requirements: 6.3, 6.4, 6.5, 6.9, 6.16, 12.1, 12.2, 12.10, 14.1
Properties: **P22 / P23 / P27 / P49 / P66 / P69**

═══ 这一半证的是「判据本身正确 + 契约真有来源 + 结构操作真的在跑」 ═══

`test_task42_h1_grouped_dynamic_pilot_pg.py` 在真库上跑完整 run（发布四个 definition、
组 non-null bundle、逐场景 record、finalize），并冻结「真实库里 `H1-8-rows` 今天为空」
这一事实。本文件不连库，只证六件事：

1. **冻结的 entry 不是拍脑袋挑的**：三条必要条件在真实 manifest / 真实
   `wp_template_finder` / 真实 `_index.json` / 真实 `H1-1.yaml` 上重新推导一遍。
   🔴 其中第 2 条与 Task 40/41 **都不同**（`H1F` 根本不是一个 wp_code，而是 manifest
   生成器从宿主文件名抽出来的产物），因此是四条实测事实 —— 见
   `TestFrozenEntrySelection` 的 docstring。
2. **25 个字段逐个有来源**：`header_source_ref` / `mid_source_ref` / `group_source_ref` /
   `source_ref` / `enum_source_ref` 指向的单元格，用 openpyxl 直读权威模板取出**真实
   文本/公式/数据验证**再比对；字段键集合与前端 `useH1DisposalCheck.DisposalRow`、
   类别值域与 `useH1Detail.H1_2_CATEGORY_OPTIONS` 三源锁死。
3. **三级分组表头真的是三级**：4 个横向组 + 3 个中层 + 6 个真叶子，逐格 merge 实测；
   并且 **7 列共用 3 个重复叶子 label** 而 25 个 stable key 互不相同（Property 22 的
   真实、非合成 oracle）。
4. **骨架行数真的是 `max(seed,1)`**：`skeleton_row_count` 是唯一决定行数的地方，
   `seed=0` 得 1 而不是模板自带的 15，且模块里没有第二处行数算术（源码级判据）。
5. **插删重排复制真的跑在真实模板上**：真实权威模板 → 真实注入产物 → 真实 extract，
   五种结构操作各自的 identity / 公式范围 / 未管理区域结论逐项断言。
   🔴 未管理区域的 8 个 aspect 覆盖计数全部落到实测值（`shared_strings_prefix` 为 0 是
   **本工作簿没有 sharedStrings.xml** 这一事实，不是空集恒真 —— 另有专门判据钉住它）。
6. **本任务修掉的三条真实缺陷有反向自检**：rels 属性顺序 / per-element `xmlns:r` /
   数字字符引用，三条各自「故意退回旧行为必失败」。

═══ 反假绿 ═══

* 覆盖计数硬判据：25 字段 / 22 editable / 3 protected / 25 次叶子表头比对 / 6 次中层比对 /
  19 次组标题比对 / 30 次公式比对（2 列 × 15 行）/ 2 条数据验证 / 5 处未管理区域格 /
  8 个未管理 aspect 里 7 个 > 0（第 8 个为 0 且有专门事实判据）。
* 双向锁：磁盘契约 ↔ 现算 payload（改任一侧都打红）。
* 分型可达：`StorePayloadError` 的四个分支各真触发一次，且与 `PilotSelectionError`
  互不相同（共用错误码会让较早分支永久不可达 —— 本 spec 已实测 3 次的形态）。
* 期望值一律从**源侧**推导或写字面量，绝不用被测函数算期望。
* 不借用 Task 40/41 的 definition identity：authority model / bundle digest / contract /
  required-set digest 四项各自与它们比对**不相等**。
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import sys
import uuid
import zipfile
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
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_typography_rows as TR  # noqa: E402
from app.services.workpaper_sync import pilot_h1_grouped_dynamic as P  # noqa: E402
from app.services.workpaper_sync import pilot_harness as PH  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    FieldValue,
    Projection,
    SubstrateRole,
)
from app.services.workpaper_sync.contracts import (  # noqa: E402
    ContractError,
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

# 🔴 与 Task 37 共用 zip 级字节编辑件里**与 K11 常量无关**的三个
#    （`patch_cells` 的正则有两处已实测的坑，抄第二份就是把那两个坑再踩一遍）。
#    `grow_table_to` / `add_row` / `_sheet_part_of` **不能**复用：它们绑死了 K11 的
#    `EXPECTED_TABLE_REF` / `FIRST_ROW` / `UUID_COL`，而 `_sheet_part_of` 还带着本任务
#    刚修掉的「rels 里 Id 必须排在 Target 之前」那条假设（见
#    `TestUpstreamRelsAndNamespaceDefectsAreFixed`）。
from test_task37_excel_extract import (  # noqa: E402
    _read_entries,
    _write_entries,
    patch_cells,
)

_MANIFEST_PATH = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"
_FRONTEND = _REPO / "audit-platform" / "frontend" / "src"
_DISPOSAL_COMPOSABLE = (
    _FRONTEND / "components" / "workpaper" / "composables" / "useH1DisposalCheck.ts"
)
_DETAIL_COMPOSABLE = (
    _FRONTEND / "components" / "workpaper" / "composables" / "useH1Detail.ts"
)
_DISPOSAL_TAB = (
    _FRONTEND / "components" / "workpaper" / "h1" / "inspection" / "H1TabDisposalCheck.vue"
)
_ROUTER = _BACKEND / "app" / "routers" / "wp_sync_router.py"

#: 25 = A..Z 的 26 列减去模板占位列 `X`（表头文本恰为 `……`）。
EXPECTED_FIELD_COUNT = 25
#: 3 = 2 个 formula 列（L/O）+ 1 个 auto_source 列（A 序号）。
EXPECTED_PROTECTED_COUNT = 3
EXPECTED_EDITABLE_COUNT = EXPECTED_FIELD_COUNT - EXPECTED_PROTECTED_COUNT
#: 权威模板的**物理**骨架行数（`A13..A26` 字面量 1..14 + `A27` 占位 `……`）= 15。
#:
#: 🔴 BP-21 起它**不再等于**受管行数：`A27` 是排版占位行（续行省略号），不是业务行。
EXPECTED_PHYSICAL_SKELETON_ROWS = 15
#: 受管行数 = 物理骨架 − 尾部排版占位行 = 14（`A13..A26`）。
EXPECTED_TEMPLATE_ROW_COUNT = P.LAST_DATA_ROW - P.FIRST_DATA_ROW + 1  # 14
#: 26 张 sheet（openpyxl 实测）。
EXPECTED_SHEET_COUNT = 26
#: 受管 sheet 的 merge 总数（openpyxl 实测）。
EXPECTED_MERGE_COUNT = 32
#: 三个重复叶子 label 与它们各自占的列数（Property 22 的真实 oracle）。
EXPECTED_DUPLICATE_LEAF_LABELS: Mapping[str, int] = {
    "日期/编号": 3,
    "对手方名称": 2,
    "金额": 2,
}
#: 本任务修掉的三条缺陷各自的影响面（`backend/wp_templates/` 369 个工作簿里的命中数）。
EXPECTED_LEGACY_WRITER_WORKBOOKS = 10
EXPECTED_TOTAL_WORKBOOKS = 369

FIRST = P.FIRST_DATA_ROW
LAST = P.LAST_DATA_ROW


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def uid(row: int) -> str:
    """instrumentation 预生成的行 UUID 字面量（与 `spec.row_uuid` 同形态）。"""
    return f"GTROW-{P.TEMPLATE_ID}-{row:04d}"


def _non_docstring_literals(path: Path) -> list[str]:
    """模块里的**非 docstring** 字符串字面量。

    docstring 必须剥掉：本任务的生产模块 docstring 里刻意写着「参考副本一次都不读」
    「不借用 D2/G7 的 identity」这类**说明**，纯字面量判据会把说明本身判成违规。
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

    path = _BACKEND / "scripts" / "gen" / "generate_pilot_h1_grouped_dynamic_contract.py"
    spec = importlib.util.spec_from_file_location("_t42_contract_gen", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.observe_template_resolution()


# ═══════════════════════════════════════════════════════════════════════════
# fixtures：真实 manifest / 真实权威模板 / 真实注入产物（不手搓 xlsx）
# ═══════════════════════════════════════════════════════════════════════════


def sheet_part_of(data: bytes, sheet_name: str) -> str:
    """sheet 展示名 → sheet part 路径（**属性顺序无关**）。

    🔴 不复用 `test_task37_excel_extract._sheet_part_of`：它写的是
    ``Id="{rid}"[^>]*Target="..."``，隐含「Id 必须排在 Target 之前」，而本任务的权威模板
    恰恰是 `Type` → `Target` → `Id` 顺序（同一缺陷已在生产侧
    `excel_instrumentation._sheet_part_for` 修掉，见
    `TestUpstreamRelsAndNamespaceDefectsAreFixed`）。
    """
    entries = _read_entries(data)
    workbook = entries["xl/workbook.xml"].decode("utf-8")
    match = re.search(
        r'<sheet [^>]*name="' + re.escape(sheet_name) + r'"[^>]*r:id="(rId\d+)"', workbook
    )
    assert match, sheet_name
    rid = match.group(1)
    rels = entries["xl/_rels/workbook.xml.rels"].decode("utf-8")
    for candidate in re.finditer(r"<Relationship\b[^>]*?/?>", rels):
        if re.search(r'\bId="' + re.escape(rid) + r'"', candidate.group(0)):
            target = re.search(r'\bTarget="([^"]+)"', candidate.group(0))
            assert target, candidate.group(0)
            path = target.group(1).lstrip("/")
            return path if path.startswith("xl/") else f"xl/{path}"
    raise AssertionError(f"rels 里找不到 {rid}")


def grow_table_to(data: bytes, last_row: int) -> bytes:
    """把 Excel Table 的 ref 行区间扩到 `last_row`（模拟 OO 插行）。

    不复用 Task 37 的同名 helper：它绑死了 K11 的 `EXPECTED_TABLE_REF` 字面量。
    """
    entries = _read_entries(data)
    part = next(name for name in entries if name.startswith("xl/tables/"))
    xml = entries[part].decode("utf-8")
    grown, count = re.subn(
        r'ref="A\d+:([A-Z]+)\d+"', rf'ref="A{FIRST}:\g<1>{last_row}"', xml, count=1
    )
    assert count == 1 and grown != xml, "Table ref 未扩 —— fixture 会变成无效变异"
    entries[part] = grown.encode("utf-8")
    return _write_entries(entries)


def add_row(data: bytes, part: str, *, row: int, cells: Mapping[str, Any]) -> bytes:
    """在受管区域**末尾追加一行**：先扩 Table ref，再写该行的格。

    🔴 这是「OO 新增行」的正确 fixture 形态。改**已有行**（清空/换重复 UUID）在语义上是
    「原有 identity 消失」⇒ 先被保留门（Property 66）拦住，身份分类分支根本走不到 ——
    「真实数据上分支不可达 = 永久 GREEN」的典型（Task 37 实测踩过）。
    """
    return patch_cells(grow_table_to(data, row), part, cells)


def fill_cached_formula_values(data: bytes, part: str) -> bytes:
    """给两个公式列补缓存值 `<v>`。

    🔴 为什么必须补：权威模板里公式格是 ``<f>I13-J13-K13</f><v></v>`` —— **缓存值是空的**
    （模板从未被计算过）。`excel_extract` 按 Task 14 语义把读到 `None` 的格当 MISSING
    （`if not present: continue`），于是公式字段既不进 projection、也不进
    `formula_inventory`。真实 OO 往返回来的工作簿一定带缓存值，所以 fixture 必须补上，
    否则「公式范围」判据会在一个恒空的集合上通过（假绿第⑤源）。
    模板自身那个「缓存值为空」的事实由
    `TestTemplateFormulaCellsShipWithoutCachedValues` 单独钉住。
    """
    entries = _read_entries(data)
    xml = entries[part].decode("utf-8")
    filled = 0
    for column in sorted(P.FORMULA_TEMPLATES):
        for row in range(FIRST, LAST + 1):
            pattern = re.compile(
                r'(<c r="' + column + str(row) + r'"[^>]*>(?:<f>[^<]*</f>))<v></v>'
            )
            xml, count = pattern.subn(rf"\g<1><v>{row}</v>", xml, count=1)
            filled += count
    expected = len(P.FORMULA_TEMPLATES) * EXPECTED_TEMPLATE_ROW_COUNT
    assert filled == expected, (
        f"只补了 {filled} 个公式缓存值（期望 {expected}）—— 模板的公式格形态已变，"
        "公式范围判据会退化成空集"
    )
    entries[part] = xml.encode("utf-8")
    return _write_entries(entries)


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
def contract_payload() -> dict[str, Any]:
    """磁盘契约的**原始 JSON**（`SyncContract` 丢掉了 header/mid/group source_ref 等扩展键）。"""
    return json.loads(P.contract_file_path().read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw_fields(contract_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(contract_payload["sheets"][0]["tables"][0]["fields"])


@pytest.fixture(scope="module")
def instrumented() -> EI.InstrumentedWorkbook:
    gate = EI.ExcelIdentityCarrierGate.load()
    return EI.instrument_workbook_bytes(
        P.read_authoritative_template(), P.instrumentation_spec(), gate=gate
    )


@pytest.fixture(scope="module")
def sheet_part(instrumented: EI.InstrumentedWorkbook) -> str:
    return sheet_part_of(instrumented.instrumented_bytes, P.MANAGED_SHEET)


@pytest.fixture(scope="module")
def base_bytes(instrumented: EI.InstrumentedWorkbook, sheet_part: str) -> bytes:
    """把 22 个 editable + 1 个 auto_source 列逐行写满，并补上两个公式列的缓存值。"""
    cells: dict[str, Any] = {}
    written: set[str] = set()
    for _key, column, mode, value_type, _path, _leaf, _label in P.MANAGED_FIELD_SPECS:
        if mode == "formula":
            continue
        written.add(column)
        for row in range(FIRST, LAST + 1):
            if value_type == "amount":
                cells[f"{column}{row}"] = 100 + row
            elif value_type == "integer":
                cells[f"{column}{row}"] = row - FIRST + 1
            elif value_type == "date":
                cells[f"{column}{row}"] = f"2026-01-{row:02d}"
            elif value_type == "enum" and column == "B":
                cells[f"{column}{row}"] = P.CATEGORY_DV_VALUES[
                    row % len(P.CATEGORY_DV_VALUES)
                ]
            elif value_type == "enum" and column == "E":
                cells[f"{column}{row}"] = P.DISPOSAL_METHOD_DV_VALUES[row % 2]
            elif value_type == "enum":
                cells[f"{column}{row}"] = "Y" if row % 2 else "N"
            else:
                cells[f"{column}{row}"] = f"值{column}{row}"
    assert len(written) == EXPECTED_FIELD_COUNT - len(P.FORMULA_TEMPLATES), sorted(written)
    return fill_cached_formula_values(
        patch_cells(instrumented.instrumented_bytes, sheet_part, cells), sheet_part
    )


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("task42")


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


def make_definitions(
    contract: Any, inventory_bytes: bytes, *, drop_identity: str | None = None
) -> FrozenEntryDefinitions:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    bundle = DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("h1-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("h1-authority"),
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
    raw = identity_inventory(
        inventory_bytes, expected_table=P.TABLE_NAME, uuid_column_letter=P.UUID_COL
    )
    if drop_identity:
        column = dict(raw["hidden_uuid_column"])
        column["row_uuids"] = {
            key: value
            for key, value in column["row_uuids"].items()
            if value != drop_identity
        }
        raw = dict(raw)
        raw["hidden_uuid_column"] = column
    return FrozenEntryDefinitions(
        entry_id=P.PILOT_ENTRY_ID,
        bundle=bundle,
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=P.PILOT_ADAPTER_ID,
            adapter_build_digest=_d("h1-adapter-build"),
            document_type="xlsx",
            contract_version="1.0.0",
        ),
        identity_inventory=parse_identity_inventory(raw),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


@pytest.fixture(scope="module")
def definitions(contract: Any, base_bytes: bytes) -> FrozenEntryDefinitions:
    return make_definitions(contract, base_bytes)


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


@pytest.fixture(scope="module")
def region(base_path: Path, contract: Any, binding: X.ExcelIdentityBinding) -> Any:
    with zipfile.ZipFile(base_path) as zf:
        return X.resolve_managed_region(zf, contract=contract, binding=binding)


def scaled_limits(**over: Any) -> SyncLimits:
    """按生产配置派生一份缩小的预算（被测常量仍来自单一真源配置文件）。"""
    base = load_limits()
    fields = {
        name: getattr(base, name) for name in base.__dataclass_fields__ if name != "ooxml"
    }
    fields.update(over)
    return SyncLimits(ooxml=base.ooxml, **fields)


def store_rows(count: int, *, start: int = 0) -> list[dict[str, Any]]:
    """按**真实 25 列形态**造 `count` 行 store 数据（键集合逐个来自契约常量）。

    🔴 用合成行而不是真实载荷是**实测结论**而非偷懒：`H1-8-rows` 这一条 item 在参考库里
    全库为空（5 个有 `H1-*` item 的底稿一条都没有），由
    `test_task42_h1_grouped_dynamic_pilot_pg.py` 从库里重新观测并冻结。25 个 json 路径与
    `rowId` 命名规则全部取自 :data:`P.MANAGED_FIELD_SPECS` / :data:`P.ROW_IDENTITY_STORE_KEY`。
    """
    rows: list[dict[str, Any]] = []
    for index in range(start, start + count):
        row: dict[str, Any] = {P.ROW_IDENTITY_STORE_KEY: f"disp-fixture-{index:05d}"}
        for _key, _column, _mode, value_type, path, _leaf, _label in P.MANAGED_FIELD_SPECS:
            if value_type == "amount":
                row[path] = float(index + 1)
            elif value_type == "integer":
                row[path] = index + 1
            elif value_type == "date":
                row[path] = "2026-01-01"
            else:
                row[path] = f"{path}-{index}"
        rows.append(row)
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结的 entry：必要条件在真实数据上重新推导
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenEntrySelection:
    """**Validates: Requirements 12.1 / 12.2**

    三条必要条件。第 2 条与 Task 40/41 **形态都不同**：本 entry 的
    `wp_match.wp_code_patterns == ["H1F"]`，而 `H1F` **根本不是一个 wp_code** ——
    manifest 生成器 `_source_match()` 对宿主文件名主干 `GtH1FixedAssets` 跑正则
    ``[A-Z][0-9]+(?:-[0-9]+)*(?:[A-Z])?`` 抽出来的产物。因此拆成四条实测事实：

    1. `H1F` 在三个 finder 入口上全空（零回退的最强形态 = 根本没有回退）；
    2. `H1F` 可证是提取产物（不在索引 wp_code 值域、不是任何 filename 前缀、正则可复现）；
    3. 真码族 `H1` 在 `_index.json` 里精确唯一且落在冻结的权威模板（Task 40 形态）；
    4. 配置真源 `H1-1.yaml` 声明同一份工作簿（判据是「属于码族」而**不是** Task 41 的
       `wp_code in PILOT_WP_CODES` —— 那条在这里本就不该成立）。
    """

    def test_entry_is_frozen_from_the_source_backed_manifest(
        self, resolution: Any, manifest: dict[str, Any]
    ) -> None:
        got = P.assert_pilot_entry_selectable(resolution=resolution, manifest=manifest)
        assert got["entry_id"] == P.PILOT_ENTRY_ID

    def test_entry_is_the_only_h1_candidate_in_the_harness_assessment(
        self, manifest: dict[str, Any]
    ) -> None:
        """类边界由 Task 39 的 harness 判定，不由本模块声明。"""
        assessment = PH.assess_pilot_classes(manifest=manifest)[
            PH.PilotClass.h1_grouped_dynamic
        ]
        assert assessment.candidate_entry_ids == (P.PILOT_ENTRY_ID,)
        assert assessment.bidirectional_entry_ids == ()
        assert assessment.status is PH.PilotClassStatus.unverifiable

    def test_entry_is_independent_and_not_a_parent_duplicate(
        self, entry: dict[str, Any]
    ) -> None:
        assert entry["independent_entry"] is True
        assert entry["parent_entry_id"] is None

    def test_wp_code_pattern_has_no_implicit_template_fallback(
        self, resolution: Any
    ) -> None:
        """`H1F` 在三个 finder 入口上**全部**解析不到任何文件。"""
        hits = resolution.by_wp_code
        assert set(hits) == set(P.PILOT_WP_CODES), sorted(hits)
        for code, (exact, any_hit, all_hits) in sorted(hits.items()):
            assert exact is None, (code, exact)
            assert any_hit is None, (code, any_hit)
            assert tuple(all_hits) == (), (code, all_hits)
        P.assert_no_implicit_template_fallback(
            resolution, wp_codes=frozenset(P.PILOT_WP_CODES)
        )

    def test_wp_code_pattern_is_a_name_extraction_artifact(self, resolution: Any) -> None:
        """`H1F` 是从宿主文件名抽出来的，不是真 wp_code —— 三条各自实测。"""
        assert "H1F" not in set(resolution.index_wp_codes)
        assert not [n for n in resolution.index_filenames if str(n).startswith("H1F")]
        assert resolution.host_stem == "GtH1FixedAssets", resolution.host_stem
        extracted = P.assert_wp_code_pattern_is_a_name_extraction_artifact(resolution)
        assert "H1F" in extracted, sorted(extracted)

    def test_name_extraction_judgement_fails_closed_when_the_code_is_real(
        self, resolution: Any
    ) -> None:
        """反向自检：若 `H1F` 真出现在索引 wp_code 值域里，判定必须打红。"""
        import dataclasses

        patched = dataclasses.replace(
            resolution, index_wp_codes=tuple(resolution.index_wp_codes) + ("H1F",)
        )
        with pytest.raises(P.PilotSelectionError, match="真 wp_code"):
            P.assert_wp_code_pattern_is_a_name_extraction_artifact(patched)

    def test_name_extraction_judgement_fails_closed_on_a_filename_prefix(
        self, resolution: Any
    ) -> None:
        """反向自检：出现以 `H1F` 开头的模板文件名 ⇒ 前缀回退分支变可达，必须打红。"""
        import dataclasses

        patched = dataclasses.replace(
            resolution,
            index_filenames=tuple(resolution.index_filenames) + ("H1F 假模板.xlsx",),
        )
        with pytest.raises(P.PilotSelectionError, match="前缀回退"):
            P.assert_wp_code_pattern_is_a_name_extraction_artifact(patched)

    def test_name_extraction_judgement_fails_closed_on_a_different_host(
        self, resolution: Any
    ) -> None:
        """反向自检：宿主改名后正则复现不出 `H1F` ⇒ 推导前提失效，必须打红。"""
        import dataclasses

        patched = dataclasses.replace(resolution, host_stem="GtFixedAssets")
        with pytest.raises(P.PilotSelectionError, match="复现不出"):
            P.assert_wp_code_pattern_is_a_name_extraction_artifact(patched)

    def test_code_family_is_exactly_unique_in_the_template_index(
        self, resolution: Any
    ) -> None:
        """真码族 `H1` 在 `_index.json` 里恰 1 行，且 relative_path 就是冻结的权威模板。"""
        rows = list(resolution.family_index_rows)
        assert len(rows) == 1, rows
        assert rows[0]["wp_code"] == P.PILOT_WP_CODE_FAMILY
        assert "/".join(str(rows[0]["relative_path"]).split("\\")) == (
            P.TEMPLATE_RELATIVE_PATH
        )

    def test_code_family_resolver_lands_on_the_same_workbook(
        self, resolution: Any
    ) -> None:
        """三个 finder 入口对码族 `H1` 都落在同一份权威模板上。"""
        expected = P.authoritative_template_path().resolve()
        assert resolution.family_resolved_paths, "缺码族实测结果"
        for resolved in resolution.family_resolved_paths:
            assert resolved is not None
            assert Path(str(resolved)).resolve() == expected, resolved

    def test_fallback_judgement_fails_closed_on_a_non_empty_resolution(
        self, resolution: Any
    ) -> None:
        """反向自检：`H1F` 一旦解析到文件，零回退判据必须打红。"""
        import dataclasses

        leaked = dataclasses.replace(
            resolution,
            by_wp_code={
                code: (P.authoritative_template_path(), None, ())
                for code in P.PILOT_WP_CODES
            },
        )
        with pytest.raises(P.PilotSelectionError, match="零回退"):
            P.assert_no_implicit_template_fallback(
                leaked, wp_codes=frozenset(P.PILOT_WP_CODES)
            )

    def test_fallback_judgement_fails_closed_on_a_non_unique_family_row(
        self, resolution: Any
    ) -> None:
        """反向自检：码族在索引里出现两行 ⇒ 「精确唯一」失守，必须打红。"""
        import dataclasses

        doubled = dataclasses.replace(
            resolution,
            family_index_rows=tuple(resolution.family_index_rows) * 2,
        )
        with pytest.raises(P.PilotSelectionError, match="精确唯一"):
            P.assert_no_implicit_template_fallback(
                doubled, wp_codes=frozenset(P.PILOT_WP_CODES)
            )

    def test_authoritative_template_is_declared_by_the_render_schema(self) -> None:
        """配置真源 `H1-1.yaml` 声明的 template_path 就是冻结的权威模板。"""
        assert P.render_schema_template_path() == (
            f"backend/wp_templates/{P.TEMPLATE_RELATIVE_PATH}"
        )

    def test_render_schema_wp_code_must_stay_inside_the_code_family(self) -> None:
        """判据是「属于码族 `H1`」而不是 Task 41 的 `wp_code in PILOT_WP_CODES`。"""
        # `H1` 与 `H1-1` 都属于码族 —— 这两条正是本 entry 的真实形态。
        for code in (P.PILOT_WP_CODE_FAMILY, "H1-1", "H1-8"):
            assert P.render_schema_template_path(
                payload={"wp_code": code, "template_path": "x"}
            ) == "x"
        # 跳出码族即打红（`H1F` 也不行 —— 它不是真码，不该出现在配置里）。
        for code in ("H2", "D2A", "H10", "H1F", ""):
            with pytest.raises(P.PilotSelectionError, match="码族"):
                P.render_schema_template_path(payload={"wp_code": code})

    def test_scenario_profile_is_the_shared_editable_standard(
        self, entry: dict[str, Any]
    ) -> None:
        profile = entry["scenario_profile"]
        assert profile["profile_id"] == "xlsx.editable.shared.single.room_service_wired.v1"
        assert profile["editability"] == "editable"
        assert profile["room_model"] == "shared"
        assert profile["mount_cardinality"] == "single"
        assert profile["host_reachable"] is True

    def test_required_set_digest_is_this_entry_own(self, entry: dict[str, Any]) -> None:
        """evidence 按本 entry 自己的 digest 记录（不复用 Task 40/41 的）。"""
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entries = manifest_entries_by_id(load_entry_manifest())
        mine = derive_for_manifest_entry(entry, authority_model=P.AUTHORITY_MODEL)
        assert len(mine.scenario_ids) == 24, sorted(mine.scenario_ids)
        assert mine.digest == (
            "319d10b4d610df67b105761f48abd78c1db6bd7f69d722f286b559addd8f67f7"
        ), mine.digest
        for other_entry_id in ("xlsx/b60/gt-b60-bundle", "xlsx/gt-d2-accounts-receivable"):
            other = derive_for_manifest_entry(
                entries[other_entry_id], authority_model=P.AUTHORITY_MODEL
            )
            assert other.digest != mine.digest, other_entry_id
            assert other.entry_id != mine.entry_id
            # 🔴 `scenario_profile_digest` 相不相同**由 profile 决定**，不由 entry 决定：
            #    它是 profile 的 digest。承担 entry 隔离的是上面那个
            #    `required_scenario_set_digest`（把 entry_id 摁进去了）。这条把两者的
            #    分工写成显式判据 —— 实测 D2 与本 entry 的 profile 逐字相同（digest 相等），
            #    B60 的 profile 不同（digest 不等）；若写死 `!=` 会逼人以后去改一个本就该
            #    相等的值。
            same_profile = other.scenario_profile_digest == mine.scenario_profile_digest
            other_profile = entries[other_entry_id]["scenario_profile"]
            assert same_profile == (other_profile == entry["scenario_profile"]), (
                other_entry_id,
                same_profile,
            )
        d2 = derive_for_manifest_entry(
            entries["xlsx/gt-d2-accounts-receivable"], authority_model=P.AUTHORITY_MODEL
        )
        b60 = derive_for_manifest_entry(
            entries["xlsx/b60/gt-b60-bundle"], authority_model=P.AUTHORITY_MODEL
        )
        assert d2.scenario_profile_digest == mine.scenario_profile_digest
        assert b60.scenario_profile_digest != mine.scenario_profile_digest
        assert len({mine.digest, d2.digest, b60.digest}) == 3

    def test_selection_fails_closed_when_the_entry_disappears(
        self, resolution: Any, manifest: dict[str, Any]
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        patched["entries"] = [
            item for item in patched["entries"] if item["entry_id"] != P.PILOT_ENTRY_ID
        ]
        with pytest.raises(P.PilotSelectionError, match="不在 source-backed manifest"):
            P.assert_pilot_entry_selectable(resolution=resolution, manifest=patched)

    def test_selection_fails_closed_on_parent_duplicate(
        self, resolution: Any, manifest: dict[str, Any]
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["independent_entry"] = False
                item["parent_entry_id"] = "xlsx/gt-wp-renderer"
        with pytest.raises(P.PilotSelectionError, match="independent_entry"):
            P.assert_pilot_entry_selectable(resolution=resolution, manifest=patched)

    def test_selection_fails_closed_on_wp_code_drift(
        self, resolution: Any, manifest: dict[str, Any]
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["wp_match"]["wp_code_patterns"] = ["H1F", "H1X"]
        with pytest.raises(P.PilotSelectionError, match="matcher 域"):
            P.assert_pilot_entry_selectable(resolution=resolution, manifest=patched)

    def test_selection_fails_closed_when_the_render_schema_points_elsewhere(
        self, resolution: Any, manifest: dict[str, Any]
    ) -> None:
        with pytest.raises(P.PilotSelectionError, match="template_path"):
            P.assert_pilot_entry_selectable(
                resolution=resolution,
                manifest=manifest,
                declared_template_path="backend/wp_templates/H/H6 固定资产清理.xlsx",
            )

    def test_the_contract_generator_refuses_to_write_when_selection_breaks(self) -> None:
        """生成器把选型判据放在落盘**之前**（源码级顺序判据）。"""
        source = (
            _BACKEND / "scripts" / "gen" / "generate_pilot_h1_grouped_dynamic_contract.py"
        ).read_text(encoding="utf-8")
        gate = source.index("assert_pilot_entry_selectable")
        build = source.index("build_contract_payload()")
        write = source.index("path.write_bytes(blob)")
        assert gate < build < write, (gate, build, write)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthoritativeTemplate:
    """**Validates: Requirements 9.9 / 12.2**"""

    def test_template_bytes_are_unchanged(self) -> None:
        data = P.read_authoritative_template()
        assert hashlib.sha256(data).hexdigest() == P.TEMPLATE_SHA256

    def test_template_lives_under_the_authority_root(self) -> None:
        path = P.authoritative_template_path()
        assert path.is_file()
        assert path.parent.parent.name == "wp_templates"
        assert path.parent.parent.parent.name == "backend"

    def test_reference_copy_is_never_read(self) -> None:
        """代码路径判据：本模块只经 gate 解析 `backend/wp_templates/`，一次都不读参考副本。

        🔴 是**代码路径**判据而不是「文件不存在」：这份工作簿在参考副本树里恰好不存在
        （`rglob` 0 命中），若判据只写「不存在」，哪天有人把副本补进去它就静默失效。
        """
        module = Path(P.__file__)
        literals = _non_docstring_literals(module)
        assert not [text for text in literals if "基础数据" in text], literals
        assert not [text for text in literals if "致同通用审计程序" in text]
        # 唯一的路径拼装处是 gate（authority-root 越界检查在它里面）。
        source = module.read_text(encoding="utf-8")
        assert "assert_template_under_authority(TEMPLATE_RELATIVE_PATH)" in source
        assert 'Path("backend") / "wp_templates"' not in source
        assert '"wp_templates"' not in source

    def test_managed_sheet_is_one_of_twenty_six_and_only_it_is_declared(
        self, workbook: Any, contract: Any
    ) -> None:
        assert len(workbook.sheetnames) == EXPECTED_SHEET_COUNT, workbook.sheetnames
        assert P.MANAGED_SHEET in workbook.sheetnames
        assert [sheet.excel_name for sheet in contract.sheets] == [P.MANAGED_SHEET]

    def test_template_sentinel_rejects_a_mutated_workbook(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """哨兵不是装饰：改一个字节必抛。

        🔴 只替换 `pilot_h1_grouped_dynamic.authoritative_template_path` 的返回目标，
        **不**全局替换 `Path.read_bytes`：后者会把 gate 自己读裁决 JSON 的那次也劫走，
        而 gate 又会调回 `authoritative_template_path()` ⇒ 无限递归（首轮实测
        `RecursionError`）。
        """
        real = P.authoritative_template_path()
        tampered = real.parent / "__tmp_task42_tampered.xlsx"
        tampered.write_bytes(real.read_bytes() + b"x")
        try:
            monkeypatch.setattr(P, "authoritative_template_path", lambda: tampered)
            with pytest.raises(P.PilotSelectionError, match="权威模板字节已变"):
                P.read_authoritative_template()
        finally:
            tampered.unlink(missing_ok=True)
        # 复核：真实模板一个字节都没动（`backend/wp_templates/` 运行时只读）。
        assert hashlib.sha256(real.read_bytes()).hexdigest() == P.TEMPLATE_SHA256

    def test_managed_sheet_merge_count_is_the_real_template_fact(
        self, worksheet: Any
    ) -> None:
        assert len(worksheet.merged_cells.ranges) == EXPECTED_MERGE_COUNT
        assert worksheet.dimensions == "A1:AA43", worksheet.dimensions

    def test_template_formula_cells_ship_without_cached_values(
        self, instrumented: EI.InstrumentedWorkbook, sheet_part: str
    ) -> None:
        """权威模板的公式格是 `<f>…</f><v></v>` —— 缓存值为空。

        这条把 `fill_cached_formula_values` 存在的**理由**钉住：模板从未被计算过，
        `excel_extract` 按 Task 14 语义把读到 `None` 的格当 MISSING，于是公式字段既不进
        projection 也不进 `formula_inventory`。哪天模板带上缓存值，这里打红提醒去掉 fixture
        里的补值步骤（否则那一步会静默变成覆盖真实值）。
        """
        xml = _read_entries(instrumented.instrumented_bytes)[sheet_part].decode("utf-8")
        empty = 0
        for column in sorted(P.FORMULA_TEMPLATES):
            for row in range(FIRST, LAST + 1):
                cell = re.search(
                    r'<c r="' + column + str(row) + r'"[^>]*>(.*?)</c>', xml, re.S
                )
                assert cell, f"{column}{row}"
                body = cell.group(1)
                assert "<f>" in body, f"{column}{row} 没有公式"
                assert "<v></v>" in body, f"{column}{row} 已带缓存值: {body[:80]}"
                empty += 1
        assert empty == len(P.FORMULA_TEMPLATES) * EXPECTED_TEMPLATE_ROW_COUNT


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约扎根在模板上：25 个字段逐个有来源
# ═══════════════════════════════════════════════════════════════════════════


class TestContractIsGroundedInTheTemplate:
    """**Validates: Requirements 6.3 / 6.5 / 12.1**"""

    def test_disk_contract_matches_the_source_of_truth(self) -> None:
        """磁盘契约 ↔ 现算 payload 双向锁死（改任一侧都打红）。"""
        assert P.assert_contract_file_matches_source().contract_id == P.PILOT_ADAPTER_ID

    def test_contract_is_registered_in_the_delivery_ledger(self) -> None:
        rows = [
            row
            for row in RG.DELIVERED_PER_ENTRY_CONTRACTS
            if row["contract_id"] == P.PILOT_ADAPTER_ID
        ]
        assert len(rows) == 1, rows
        row = rows[0]
        assert row["delivered_by_task"] == "42"
        assert row["pilot_class"] == P.PILOT_CLASS
        assert row["entry_id"] == P.PILOT_ENTRY_ID
        assert row["template_relative_path"] == P.TEMPLATE_RELATIVE_PATH
        assert row["authority_model"] == P.AUTHORITY_MODEL.value
        assert row["adapter_registered"] is False
        assert P.PILOT_ADAPTER_ID in available_contract_ids()

    def test_field_counts_are_the_real_template_facts(self, contract: Any) -> None:
        assert len(contract.all_fields()) == EXPECTED_FIELD_COUNT
        assert len(contract.editable_field_keys()) == EXPECTED_EDITABLE_COUNT
        assert len(contract.protected_field_keys()) == EXPECTED_PROTECTED_COUNT
        modes = [spec.mode for spec in contract.all_fields()]
        assert modes.count(FieldMode.formula) == len(P.FORMULA_TEMPLATES) == 2
        assert modes.count(FieldMode.auto_source) == 1
        assert modes.count(FieldMode.editable) == EXPECTED_EDITABLE_COUNT

    def test_column_letters_are_a_to_z_minus_the_placeholder(
        self, worksheet: Any, raw_fields: list[dict[str, Any]]
    ) -> None:
        """受管列恰是 A..Z 去掉占位列 `X`，且 `Z` 是源模板真实的最后一列表头。"""
        from openpyxl.utils import get_column_letter

        declared = [field["cell"]["column"] for field in raw_fields]
        expected = [
            get_column_letter(i)
            for i in range(1, 27)
            if get_column_letter(i) != P.PLACEHOLDER_COLUMN
        ]
        assert declared == expected, declared
        assert P.MANAGED_LAST_COL == "Z"
        # 占位列的表头文本恰为 `……`（不声明它的**理由**，从源侧取）。
        assert (
            str(worksheet[f"{P.PLACEHOLDER_COLUMN}{P.GROUP_HEADER_ROW}"].value) == "……"
        )

    def test_every_leaf_header_matches_the_real_cell_text(
        self, worksheet: Any, raw_fields: list[dict[str, Any]]
    ) -> None:
        """25 次逐格比对：`header_source_ref` 指向的单元格文本 == `header_text`。"""
        checked = 0
        for field in raw_fields:
            ref = field["header_source_ref"]
            assert ref.startswith(f"源xlsx!{P.MANAGED_SHEET}!"), ref
            cell = ref.rsplit("!", 1)[-1]
            assert str(worksheet[cell].value) == field["header_text"], (cell, field)
            checked += 1
        assert checked == EXPECTED_FIELD_COUNT, checked

    def test_every_mid_header_matches_the_real_cell_text(
        self, worksheet: Any, raw_fields: list[dict[str, Any]]
    ) -> None:
        """6 次逐格比对（只有 `减少情况` 组内 I/J/K/L/M/N 有真中层）。"""
        checked = 0
        for field in raw_fields:
            ref = field.get("mid_source_ref")
            if not ref:
                continue
            cell = ref.rsplit("!", 1)[-1]
            assert str(worksheet[cell].value) == field["mid_header_text"], (cell, field)
            checked += 1
        assert checked == 6, checked
        assert {
            field["column_key"] for field in raw_fields if field.get("mid_source_ref")
        } == {
            "original_cost",
            "acc_dep",
            "impairment",
            "net_value",
            "disposal_cost",
            "disposal_income",
        }

    def test_every_group_header_matches_the_real_cell_text(
        self, worksheet: Any, raw_fields: list[dict[str, Any]]
    ) -> None:
        """19 次逐格比对（4 个横向组共覆盖 I..W 的 15 列 + O 也在组内 ⇒ 实测 15 列）。"""
        checked = 0
        grouped: dict[str, list[str]] = {}
        for field in raw_fields:
            ref = field.get("group_source_ref")
            if not ref:
                continue
            cell = ref.rsplit("!", 1)[-1]
            assert str(worksheet[cell].value) == field["group_header_text"], (cell, field)
            grouped.setdefault(cell, []).append(field["cell"]["column"])
            checked += 1
        assert checked == 15, checked
        assert {
            cell: tuple(columns) for cell, columns in sorted(grouped.items())
        } == {
            f"I{P.GROUP_HEADER_ROW}": ("I", "J", "K", "L", "M", "N", "O"),
            f"P{P.GROUP_HEADER_ROW}": ("P", "Q"),
            f"R{P.GROUP_HEADER_ROW}": ("R", "S", "T"),
            f"U{P.GROUP_HEADER_ROW}": ("U", "V", "W"),
        }

    def test_group_spans_match_the_real_merged_ranges(self, worksheet: Any) -> None:
        """组的列跨度必须与源 xlsx 行 10 的**真实横向 merge** 逐项相等。"""
        from openpyxl.utils import get_column_letter

        observed: dict[str, tuple[str, ...]] = {}
        for rng in worksheet.merged_cells.ranges:
            if rng.min_row != P.GROUP_HEADER_ROW or rng.max_col == rng.min_col:
                continue
            anchor = f"{get_column_letter(rng.min_col)}{rng.min_row}"
            observed[anchor] = tuple(
                get_column_letter(col) for col in range(rng.min_col, rng.max_col + 1)
            )
        declared = {cell: columns for cell, columns, _label in P.GROUP_HEADERS}
        assert observed == declared, {"observed": observed, "declared": declared}

    def test_mid_spans_match_the_real_merged_ranges(self, worksheet: Any) -> None:
        """中层的列跨度必须与源 xlsx 行 11 的真实 merge 一致（含 `O11:O12` 纵向那条）。"""
        from openpyxl.utils import get_column_letter

        for cell, columns, label in P.MID_HEADERS:
            found = [
                rng
                for rng in worksheet.merged_cells.ranges
                if f"{get_column_letter(rng.min_col)}{rng.min_row}" == cell
            ]
            assert len(found) == 1, (cell, found)
            rng = found[0]
            spanned = tuple(
                get_column_letter(col) for col in range(rng.min_col, rng.max_col + 1)
            )
            assert spanned == columns, (cell, spanned, columns)
            assert str(worksheet[cell].value) == label

    def test_header_rows_is_three_and_is_the_schema_upper_bound(
        self, contract: Any
    ) -> None:
        """三级表头 ⇒ `header_rows = 3`，恰是 `contracts._parse_table` 的上界。"""
        table = contract.sheets[0].tables[0]
        assert table.header_rows == 3 == P.HEADER_ROW_COUNT
        assert table.two_level_header is True
        assert table.anchor == f"A{P.GROUP_HEADER_ROW}"
        # 上界确实是 3：4 必须被强校验拒绝（不是本模块"恰好没写 4"）。
        payload = json.loads(json.dumps(P.build_contract_payload()))
        payload["sheets"][0]["tables"][0]["header_rows"] = 4
        with pytest.raises(ContractError, match="header_rows"):
            parse_contract(payload, adapter_id=P.PILOT_ADAPTER_ID)

    def test_two_formula_columns_are_really_formulas_in_the_template(
        self, worksheet: Any
    ) -> None:
        """30 次逐格比对（2 列 × **15 行物理骨架**）。

        🔴 BP-21：逐行公式是**物理**模板事实，覆盖整个骨架（含 `A27` 那行排版占位）——
        所以这里按 `TEMPLATE_PHYSICAL_LAST_ROW` 迭代，不按受管末行。第二段再单独断言
        「受管区内的那 14 行也全都有公式」，于是两个口径各自被取证、不会互相掩盖。
        """
        checked = 0
        for column, template in sorted(P.FORMULA_TEMPLATES.items()):
            for row in range(FIRST, P.TEMPLATE_PHYSICAL_LAST_ROW + 1):
                assert worksheet[f"{column}{row}"].value == template.format(r=row), (
                    column,
                    row,
                )
                checked += 1
        assert checked == 2 * EXPECTED_PHYSICAL_SKELETON_ROWS == 30, checked

        # 受管区是它的真子集：14 行 × 2 列，且末行恰好是 LAST
        managed = sum(
            1
            for column in P.FORMULA_TEMPLATES
            for row in range(FIRST, LAST + 1)
            if worksheet[f"{column}{row}"].value
            == P.FORMULA_TEMPLATES[column].format(r=row)
        )
        assert managed == 2 * EXPECTED_TEMPLATE_ROW_COUNT == 28, managed
        assert managed < checked, "受管区必须是物理骨架的真子集（否则 BP-21 没有生效）"

    def test_editable_columns_have_no_formula_in_the_template(
        self, worksheet: Any, raw_fields: list[dict[str, Any]]
    ) -> None:
        """23 个非 formula 列在模板数据行里**一个公式都没有**（契约以源 xlsx 为准）。

        模板哪天真给某列加了公式，这里立刻打红，而不是悄悄让 OO 侧覆盖服务端算的值。
        """
        checked = 0
        for field in raw_fields:
            if field["mode"] == "formula":
                continue
            column = field["cell"]["column"]
            for row in range(FIRST, LAST + 1):
                value = worksheet[f"{column}{row}"].value
                assert not (isinstance(value, str) and value.startswith("=")), (
                    column,
                    row,
                    value,
                )
                checked += 1
        assert checked == 23 * EXPECTED_TEMPLATE_ROW_COUNT, checked

    def test_formula_mask_covers_both_formula_columns(self, contract: Any) -> None:
        table = contract.sheets[0].tables[0]
        assert table.formula_mask == (f"L{FIRST}:L{LAST}", f"O{FIRST}:O{LAST}")
        for spec in contract.all_fields():
            if spec.mode is not FieldMode.formula:
                continue
            assert spec.cell is not None
            assert spec.cell.column in set(P.FORMULA_TEMPLATES), spec.stable_field_key

    def test_footer_marker_is_the_real_cell_text(self, worksheet: Any) -> None:
        """footer 的 SUM 区间覆盖**物理**骨架，对受管区末行构成超集。

        🔴 BP-21：模板里是 `SUM(I13:I27)`，末行 27 是排版占位行。它对受管末行 26 是
        **超集**，而 `assert_footer_formula_covers_managed_rows` 的判据是
        `last >= effective_last_row` ⇒ 收缩受管区不会让合计判据打红。
        这条判据刻意断言「等于物理区间」而不是「覆盖受管区间」：后者用 `>=` 写会让
        「模板把合计区间改小到 26」也通过，而那是模板漂移，必须打红。
        """
        assert str(worksheet[f"A{P.FOOTER_ROW}"].value) == P.FOOTER_MARKER
        checked = 0
        for column in "IJKLMNO":
            assert worksheet[f"{column}{P.FOOTER_ROW}"].value == (
                f"=SUM({column}{FIRST}:{column}{P.TEMPLATE_PHYSICAL_LAST_ROW})"
            )
            checked += 1
        assert checked == 7, checked
        # 超集关系显式取证（这正是收缩受管区后合计判据仍成立的理由）
        assert P.TEMPLATE_PHYSICAL_LAST_ROW > LAST

    def test_footer_anchor_never_hardcodes_a_row(self, contract: Any) -> None:
        anchor = contract.sheets[0].tables[0].footer_anchor
        assert anchor is not None
        assert anchor.marker == P.FOOTER_MARKER
        assert anchor.search_column == "A"
        payload = json.loads(json.dumps(P.build_contract_payload()))
        payload["sheets"][0]["tables"][0]["footer_anchor"]["row"] = P.FOOTER_ROW
        with pytest.raises(ContractError, match="写死行号"):
            parse_contract(payload, adapter_id=P.PILOT_ADAPTER_ID)

    def test_row_identity_is_not_positional(self, contract: Any) -> None:
        table = contract.sheets[0].tables[0]
        assert table.row_identity is not None
        assert table.row_identity.kind.value == "field"
        assert table.row_identity.json_pointer == f"/rows/*/{P.ROW_IDENTITY_STORE_KEY}"
        assert table.delete_policy is not None
        for spec in contract.all_fields():
            assert spec.cell is not None
            assert spec.cell.row_from == "row_identity", spec.stable_field_key
            assert spec.cell.static_row is None

    def test_positional_row_identity_is_refused(self) -> None:
        for kind in ("index", "ordinal", "position", "row_number", "array_index"):
            payload = json.loads(json.dumps(P.build_contract_payload()))
            payload["sheets"][0]["tables"][0]["row_identity"] = {"kind": kind}
            with pytest.raises(ContractError, match="Property 23"):
                parse_contract(payload, adapter_id=P.PILOT_ADAPTER_ID)

    def test_uuid_column_sits_right_of_the_managed_business_columns(
        self, worksheet: Any
    ) -> None:
        """UUID 列必须在 `Z` 右侧，且**不能**是 `AA`（那格有可见注解）。"""
        assert P.UUID_COL == "AB"
        # 🔴 先读 max_column 再碰 AB11：openpyxl 的 `ws["AB11"]` 会**创建**该 cell 并把
        #    max_column 从 27 撑到 28（首轮实测的假红源）。
        assert worksheet.max_column == 27, worksheet.max_column
        assert worksheet.dimensions == "A1:AA43"
        assert str(worksheet["AA11"].value) == (
            "检查的关键证据和要素根据被审计单位具体情况修改"
        )
        # UUID 列（`AB`）在模板里整列为空 —— 从 **sheet XML 字节**判定，因为 openpyxl 的
        # `ws["AB11"]` / `iter_rows(min_col=28)` 都会**创建** cell 并把 max_column 撑到 28
        # （首轮两次假红都出在这里）。
        template_part = sheet_part_of(P.read_authoritative_template(), P.MANAGED_SHEET)
        xml = _read_entries(P.read_authoritative_template())[template_part].decode("utf-8")
        assert not re.search(r'<c r="' + P.UUID_COL + r'\d+"', xml), P.UUID_COL
        assert re.search(r'<c r="AA11"', xml), "AA11 的注解必须真实存在"
        # 换成 `AA` 就会藏掉那条注解 —— 这是不选 AA 的**理由**。
        assert P._col_index("AA") == 27
        assert P._col_index(P.UUID_COL) == 28 > P._col_index(P.MANAGED_LAST_COL) == 26

    def test_enum_value_domains_come_from_the_real_data_validations(
        self, worksheet: Any, raw_fields: list[dict[str, Any]]
    ) -> None:
        """2 条数据验证（样式源）逐字比对；契约的 `enum_values` 不是自拟的。"""
        observed = {
            str(dv.sqref): tuple(
                str(dv.formula1).strip('"').split(",")
            )
            for dv in worksheet.data_validations.dataValidation
        }
        assert len(observed) == 2, observed
        assert observed[P.CATEGORY_DV_CELL_RANGE] == P.CATEGORY_DV_VALUES
        assert observed[P.DISPOSAL_METHOD_DV_CELL_RANGE] == P.DISPOSAL_METHOD_DV_VALUES
        declared = {
            field["column_key"]: (field["enum_source_ref"], tuple(field["enum_values"]))
            for field in raw_fields
            if field.get("enum_source_ref")
        }
        assert set(declared) == {"category", "disposal_method"}, sorted(declared)
        assert declared["category"][1] == P.CATEGORY_DV_VALUES
        assert declared["disposal_method"][1] == P.DISPOSAL_METHOD_DV_VALUES
        for _key, (ref, _values) in declared.items():
            assert ref.rsplit("!", 1)[-1] in observed

    def test_unmanaged_below_footer_cells_are_the_real_contents(
        self, worksheet: Any
    ) -> None:
        """5 处未管理区域格逐格比对（含一条跨 sheet 公式）。"""
        checked = 0
        for cell, expected in P.UNMANAGED_BELOW_FOOTER_CELLS:
            assert str(worksheet[cell].value) == expected, (cell, worksheet[cell].value)
            checked += 1
        assert checked == 5, checked
        assert any(
            "'明细表H1-2'!" in expected
            for _cell, expected in P.UNMANAGED_BELOW_FOOTER_CELLS
        ), "跨 sheet 引用是未管理区域的关键形态，丢了就说明常量表被削过"

    def test_contract_declares_no_metadata_sheet(self, contract: Any) -> None:
        """`_GT_SYNC` 是 identity 载体，不得作为受管业务 sheet 出现在契约里。"""
        assert GT_SYNC_SHEET_NAME not in {sheet.excel_name for sheet in contract.sheets}

    def test_mutated_contract_payload_is_rejected(self) -> None:
        """现算 payload 自己也过强校验（磁盘对得上但两边都非法时仍要打红）。"""
        payload = json.loads(json.dumps(P.build_contract_payload()))
        payload["sheets"][0]["tables"][0]["fields"][0]["stable_field_key"] = ""
        with pytest.raises(ContractError):
            parse_contract(payload, adapter_id=P.PILOT_ADAPTER_ID)

    def test_row_identity_pointer_matching_the_real_store_key_is_load_bearing(
        self,
    ) -> None:
        """`rowId` 这个键名是前端真源里的字面量，不是本模块随手起的。"""
        source = _DISPOSAL_COMPOSABLE.read_text(encoding="utf-8")
        assert f"  {P.ROW_IDENTITY_STORE_KEY}: string" in source, source[:200]
        assert f"const ITEM_PREFIX = 'H1-8'" in source
        assert f"${{ITEM_PREFIX}}-rows" in source
        assert P.STORE_ITEM_ID == "H1-8-rows"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 22：列 identity 与 label 解耦（本表有真实重复 label）
# ═══════════════════════════════════════════════════════════════════════════


def _frontend_disposal_row_fields() -> list[str]:
    """解析 `useH1DisposalCheck.ts` 的 `DisposalRow` 接口字段名（前端行形态真源）。"""
    source = _DISPOSAL_COMPOSABLE.read_text(encoding="utf-8")
    block = re.search(r"export interface DisposalRow \{(.*?)\n\}", source, re.S)
    assert block, "DisposalRow 接口形态已变"
    return re.findall(r"^\s{2}(\w+)\s*:", block.group(1), re.M)


def _frontend_category_options() -> list[str]:
    """解析 `useH1Detail.ts` 的 `H1_2_CATEGORY_OPTIONS`（前端类别真源）。"""
    source = _DETAIL_COMPOSABLE.read_text(encoding="utf-8")
    block = re.search(
        r"export const H1_2_CATEGORY_OPTIONS = \[(.*?)\] as const", source, re.S
    )
    assert block, "H1_2_CATEGORY_OPTIONS 形态已变"
    return re.findall(r"'([^']+)'", block.group(1))


class TestProperty22ColumnIdentityIsDecoupledFromLabel:
    """**Validates: Requirements 6.4** · Property 22

    Property 22 原文：重命名 label 不改变稳定 key；**重复 label 不发生键冲突**。

    🔴 本表给出一个**真实、非合成**的重复 label 实例：三个证据组（审批单 / 合同 / 发票）
    的叶子 label 逐字重复 —— `日期/编号` ×3、`对手方名称` ×2、`金额` ×2，共 7 列共用
    3 个 label。identity 若用 label 就会撞键（平台 H7 已付学费：`key 不能用 label`）。
    """

    def test_duplicate_leaf_labels_really_exist_in_the_template(
        self, worksheet: Any, raw_fields: list[dict[str, Any]]
    ) -> None:
        """重复 label 是源 xlsx 的事实，逐格从模板读出来数。"""
        from collections import Counter

        counts = Counter(
            str(worksheet[field["header_source_ref"].rsplit("!", 1)[-1]].value)
            for field in raw_fields
        )
        duplicates = {label: n for label, n in counts.items() if n > 1}
        assert duplicates == dict(EXPECTED_DUPLICATE_LEAF_LABELS), duplicates
        assert sum(duplicates.values()) == 7, duplicates

    def test_stable_keys_stay_distinct_despite_duplicate_labels(
        self, contract: Any, raw_fields: list[dict[str, Any]]
    ) -> None:
        """25 个 stable key / column_key 互不相同；label 一个字符都没进键。"""
        keys = [field["stable_field_key"] for field in raw_fields]
        column_keys = [field["column_key"] for field in raw_fields]
        assert len(set(keys)) == len(keys) == EXPECTED_FIELD_COUNT
        assert len(set(column_keys)) == len(column_keys) == EXPECTED_FIELD_COUNT
        for label in EXPECTED_DUPLICATE_LEAF_LABELS:
            assert not [key for key in keys if label in key], label
        # 每个重复 label 下的那几列，键必须两两不同。
        for label, expected_n in EXPECTED_DUPLICATE_LEAF_LABELS.items():
            same_label = [
                field["stable_field_key"]
                for field in raw_fields
                if field["header_text"] == label
            ]
            assert len(same_label) == expected_n
            assert len(set(same_label)) == expected_n, same_label

    def test_keys_are_ascii_and_carry_no_chinese_label(self, contract: Any) -> None:
        """identity 不得依赖中文 label（Requirement 6.14 的同一条精神）。"""
        for spec in contract.all_fields():
            assert spec.stable_field_key.isascii(), spec.stable_field_key
            assert spec.column_key and spec.column_key.isascii()
            assert re.fullmatch(r"[a-z][a-z0-9_]*", spec.column_key), spec.column_key

    def test_renaming_a_header_label_does_not_change_any_stable_key(self) -> None:
        """把三个重复 label 全改名 ⇒ 25 个 stable key 一个都不变。

        判据落在 `stable_key_for` 这个**唯一拼装处**上：它的入参里根本没有 label，
        所以「改名不影响 key」是结构性的而不是巧合。
        """
        before = [P.stable_key_for(row[0]) for row in P.MANAGED_FIELD_SPECS]
        renamed = tuple(
            row[:6] + (f"改名_{row[6]}",) for row in P.MANAGED_FIELD_SPECS
        )
        after = [P.stable_key_for(row[0]) for row in renamed]
        assert before == after
        assert len(set(after)) == EXPECTED_FIELD_COUNT

    def test_stable_key_builder_is_the_only_assembly_point(self) -> None:
        """源码级判据：`ROWS_TABLE_KEY/.../` 的拼装只在 `stable_key_for` 里出现一次。"""
        source = Path(P.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        builders = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.JoinedStr)
            and any(
                isinstance(part, ast.FormattedValue)
                and isinstance(part.value, ast.Name)
                and part.value.id == "ROWS_TABLE_KEY"
                for part in node.values
            )
        ]
        assert len(builders) == 1, ast.dump(builders[0]) if builders else "none"
        assert P.stable_key_for("x") == f"{P.ROWS_TABLE_KEY}/{{row_uuid}}/x"
        assert P.stable_key_for("x", "rid") == f"{P.ROWS_TABLE_KEY}/rid/x"

    def test_no_dynamic_columns_are_declared_for_this_entry(self, contract: Any) -> None:
        """本表列是固定的 A..Z ⇒ 契约**不得**声明 `dynamic_columns`。

        `{slot}_{seq}` 是 G7 那种按公司横向展开的形态（Task 43）；在这里凭空声明一个
        `dynamic_columns` 就是无来源自造结构。

        🔴 磁盘契约与**现算 payload** 两侧都判：只判磁盘的话，代码里凭空塞一个
        `dynamic_columns` 只会打红「双向锁」那一条，本条自己恒绿（首轮变异 M25 实测）。
        """
        assert contract.sheets[0].tables[0].dynamic_columns is None
        computed = P.build_contract_payload()["sheets"][0]["tables"][0]
        assert "dynamic_columns" not in computed, sorted(computed)
        assert P.build_contract_payload() == json.loads(
            json.dumps(json.loads(P.contract_file_path().read_text(encoding="utf-8")))
        )

    def test_frontend_row_shape_covers_every_declared_json_path(self) -> None:
        """三源锁死之二：25 个 json 路径逐个存在于前端 `DisposalRow`。"""
        fields = _frontend_disposal_row_fields()
        assert len(fields) >= EXPECTED_FIELD_COUNT, fields
        declared = [row[4] for row in P.MANAGED_FIELD_SPECS]
        missing = [path for path in declared if path not in fields]
        assert not missing, missing
        assert P.ROW_IDENTITY_STORE_KEY in fields

    def test_category_domain_matches_the_frontend_truth_source(
        self, worksheet: Any
    ) -> None:
        """三源锁死之三：模板 DV ↔ 前端 `H1_2_CATEGORY_OPTIONS` 逐字同序相等。"""
        options = _frontend_category_options()
        assert tuple(options) == P.CATEGORY_DV_VALUES, options
        observed = {
            str(dv.sqref): tuple(str(dv.formula1).strip('"').split(","))
            for dv in worksheet.data_validations.dataValidation
        }
        assert observed[P.CATEGORY_DV_CELL_RANGE] == tuple(options)


# ═══════════════════════════════════════════════════════════════════════════
# 5. 骨架行数取 max(seed, 1)（平台铁律：动态区骨架行数禁写死）
# ═══════════════════════════════════════════════════════════════════════════


class TestSkeletonRowPolicy:
    """**Validates: Requirements 6.5 / 6.9**"""

    def test_skeleton_row_count_is_max_seed_one(self) -> None:
        assert P.skeleton_row_count(0) == 1
        assert P.skeleton_row_count(1) == 1
        assert P.skeleton_row_count(2) == 2
        assert P.skeleton_row_count(EXPECTED_TEMPLATE_ROW_COUNT) == (
            EXPECTED_TEMPLATE_ROW_COUNT
        )
        assert P.skeleton_row_count(1260) == 1260
        assert P.skeleton_row_count(-5) == 1

    def test_zero_seed_does_not_yield_the_template_skeleton(self) -> None:
        """seed=0 时**不得**退回模板自带的行数（预置空占位会被推成占位披露行）。"""
        assert P.skeleton_row_count(0) == 1
        assert P.TEMPLATE_SKELETON_ROWS == EXPECTED_PHYSICAL_SKELETON_ROWS == 15
        assert P.TEMPLATE_BUSINESS_SKELETON_ROWS == EXPECTED_TEMPLATE_ROW_COUNT == 14
        assert P.skeleton_row_count(0) != P.TEMPLATE_SKELETON_ROWS
        assert P.skeleton_row_count(0) != P.TEMPLATE_BUSINESS_SKELETON_ROWS
        for forbidden in (
            3,
            5,
            10,
            P.TEMPLATE_SKELETON_ROWS,
            P.TEMPLATE_BUSINESS_SKELETON_ROWS,
        ):
            assert P.skeleton_row_count(0) != forbidden, forbidden

    def test_template_skeleton_row_count_is_derived_from_the_source(
        self, worksheet: Any
    ) -> None:
        """两个数都从源侧反推：`A13..A26` 字面量 1..14、`A27` 是 `……`、`A28` 是 footer。

        🔴 BP-21 的核心区分就在这条判据里：**物理**骨架 15 行与**业务**骨架 14 行不是同一
        个数，差的那一行是 `A27` 的续行省略号。原实现把两者混成一个数（`observed =
        FOOTER_ROW - FIRST` 恰好等于 15），于是占位行被当成第 15 条业务行送进 materialize，
        `seq` 列按 `integer` 写回 `……` 直接失败。
        """
        numbered = [
            row
            for row in range(FIRST, P.FOOTER_ROW)
            if isinstance(worksheet[f"A{row}"].value, int)
        ]
        # 业务行 = 带整数序号的那些行，恰好是受管行区间
        assert numbered == list(range(FIRST, LAST + 1)), numbered
        assert len(numbered) == EXPECTED_TEMPLATE_ROW_COUNT == 14
        assert numbered[-1] == LAST == 26

        # 占位行紧跟业务行之后、footer 之前，且被生产判据认成排版占位
        placeholder_row = LAST + 1
        placeholder = str(worksheet[f"A{placeholder_row}"].value)
        assert placeholder == "……"
        assert TR.is_typography_placeholder(placeholder)
        assert placeholder_row == 27
        assert P.TEMPLATE_TYPOGRAPHY_TAIL_ROWS == 1

        # footer 物理位置未随收缩变化
        assert str(worksheet[f"A{P.FOOTER_ROW}"].value) == P.FOOTER_MARKER
        assert P.FOOTER_ROW == 28

        # 物理骨架 = 业务骨架 + 尾部占位行；两个数各自可从源侧独立反推
        assert P.FOOTER_ROW - FIRST == P.TEMPLATE_SKELETON_ROWS == 15
        assert (
            P.TEMPLATE_SKELETON_ROWS
            == P.TEMPLATE_BUSINESS_SKELETON_ROWS + P.TEMPLATE_TYPOGRAPHY_TAIL_ROWS
        )

    def test_managed_region_excludes_the_typography_row(self, worksheet: Any) -> None:
        """反向自检：受管行区间内**没有**任何排版占位行，且占位行确实在区间外。

        没有这条时，「受管区不含占位行」只由 `LAST_DATA_ROW` 的取值间接保证 ——
        而那正是 BP-21 之前写错的那个值。
        """
        inside = [
            row
            for row in range(FIRST, LAST + 1)
            if TR.is_typography_placeholder(str(worksheet[f"A{row}"].value or ""))
        ]
        assert inside == [], inside
        assert TR.is_typography_placeholder(str(worksheet[f"A{LAST + 1}"].value))

    def test_skeleton_row_count_is_the_only_row_arithmetic(self) -> None:
        """源码级判据：模块里没有第二处「行数算术」。

        判据形态：`LAST_DATA_ROW` 的定义必须**经过** `skeleton_row_count(...)`，
        且模块里除它之外没有别的 `FIRST_DATA_ROW + <数字>` / `LAST_DATA_ROW + <数字>` 形态
        （footer 那一处除外）。
        """
        source = Path(P.__file__).read_text(encoding="utf-8")
        assert (
            "LAST_DATA_ROW: Final[int] = (\n"
            "    FIRST_DATA_ROW + skeleton_row_count(TEMPLATE_BUSINESS_SKELETON_ROWS) - 1\n"
            ")" in source
        )
        # 业务骨架必须由物理骨架**减去**尾部占位行得来，不得直接写 14
        assert (
            "TEMPLATE_BUSINESS_SKELETON_ROWS: Final[int] = (\n"
            "    TEMPLATE_SKELETON_ROWS - TEMPLATE_TYPOGRAPHY_TAIL_ROWS\n"
            ")" in source
        )
        # 物理末行必须由物理骨架推出，不得写死 27
        assert (
            "TEMPLATE_PHYSICAL_LAST_ROW: Final[int] = "
            "FIRST_DATA_ROW + TEMPLATE_SKELETON_ROWS - 1" in source
        )
        tree = ast.parse(source)
        additions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Add)
            and isinstance(node.left, ast.Name)
            and node.left.id
            in {"FIRST_DATA_ROW", "LAST_DATA_ROW", "TEMPLATE_PHYSICAL_LAST_ROW"}
            and isinstance(node.right, ast.Constant)
        ]
        # 🔴 只允许 `TEMPLATE_PHYSICAL_LAST_ROW + 1`（footer 紧跟物理骨架末行）这一处
        #    常量加法。BP-21 之前是 `LAST_DATA_ROW + 1` —— 那个写法只在「占位行被误算成
        #    业务行」时才恰好成立，收缩受管区后它会把 footer 指到占位行上。
        assert len(additions) == 1, [ast.dump(node) for node in additions]
        assert additions[0].left.id == "TEMPLATE_PHYSICAL_LAST_ROW"
        assert additions[0].right.value == 1

    def test_contract_declares_the_policy_not_a_hardcoded_count(
        self, contract_payload: dict[str, Any]
    ) -> None:
        dynamic = contract_payload["review"]["dynamic_rows"]
        assert dynamic["skeleton_row_policy"] == "max(seed,1)"
        assert dynamic["template_physical_skeleton_rows"] == P.TEMPLATE_SKELETON_ROWS
        assert "不是骨架策略" in dynamic["note"]

    def test_instrumentation_row_region_goes_through_the_policy(self) -> None:
        spec = P.instrumentation_spec()
        assert spec.first_data_row == FIRST
        assert spec.last_data_row == LAST
        # 🔴 BP-21：seed 是**业务**骨架而不是物理骨架
        assert spec.row_count == P.skeleton_row_count(P.TEMPLATE_BUSINESS_SKELETON_ROWS)
        assert spec.row_count == EXPECTED_TEMPLATE_ROW_COUNT == 14
        # footer 与受管末行之间隔着那行排版占位 ⇒ 不再相邻
        assert spec.footer_row == P.FOOTER_ROW == LAST + 1 + P.TEMPLATE_TYPOGRAPHY_TAIL_ROWS
        assert spec.footer_row > spec.last_data_row + 1
        # Table ref 随之收缩（这是 `resolve_managed_region` 的唯一区间来源）
        assert spec.table_ref == f"A{FIRST}:{P.UUID_COL}{LAST}"

    def test_footer_must_sit_outside_the_managed_rows(self) -> None:
        """反向自检：把 footer 挪进受管行区间 ⇒ instrumentation 立刻抛。"""
        with pytest.raises(EI.InstrumentationError, match="footer_row"):
            EI.ExcelInstrumentationSpec(
                entry_id=P.PILOT_ENTRY_ID,
                template_id=P.TEMPLATE_ID,
                template_relative_path=P.TEMPLATE_RELATIVE_PATH,
                managed_sheet=P.MANAGED_SHEET,
                first_data_row=FIRST,
                last_data_row=LAST,
                footer_row=LAST,
                managed_last_col=P.MANAGED_LAST_COL,
                uuid_col=P.UUID_COL,
                table_name=P.TABLE_NAME,
            )

    def test_uuid_column_left_of_managed_columns_is_refused(self) -> None:
        """反向自检：UUID 列压到业务列上 ⇒ instrumentation 立刻抛。"""
        with pytest.raises(EI.InstrumentationError, match="UUID 列"):
            EI.ExcelInstrumentationSpec(
                entry_id=P.PILOT_ENTRY_ID,
                template_id=P.TEMPLATE_ID,
                template_relative_path=P.TEMPLATE_RELATIVE_PATH,
                managed_sheet=P.MANAGED_SHEET,
                first_data_row=FIRST,
                last_data_row=LAST,
                footer_row=P.FOOTER_ROW,
                managed_last_col=P.MANAGED_LAST_COL,
                uuid_col="Y",
                table_name=P.TABLE_NAME,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 发布 DAG 单向 + 不借用其它 pilot 的 definition identity
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishDagIsOneWay:
    """**Validates: Requirements 6.18 / 12.1**"""

    def test_template_payload_has_no_self_or_forward_reference(self) -> None:
        payload = P.template_definition_payload()
        blob = json.dumps(payload, sort_keys=True)
        for forbidden in ("contract", "bundle", "definition_artifact_id"):
            assert forbidden not in blob, forbidden
        assert payload["template_sha256"] == P.TEMPLATE_SHA256

    def test_instrumentation_payload_references_template_only(self) -> None:
        payload = P.instrumentation_definition_payload()
        assert payload["template_definition_sha256"] == canonical_digest(
            P.template_definition_payload()
        )
        blob = json.dumps(payload, sort_keys=True)
        assert "contract_definition_sha256" not in blob
        assert "bundle" not in blob
        assert payload["managed_sheets"][0]["sheet_key"] == P.SHEET_KEY

    def test_contract_payload_references_both_and_no_bundle(self, contract: Any) -> None:
        assert contract.template_definition_sha256 == canonical_digest(
            P.template_definition_payload()
        )
        assert contract.instrumentation_definition_sha256 == canonical_digest(
            P.instrumentation_definition_payload()
        )
        blob = json.dumps(dict(contract.canonical_payload), sort_keys=True)
        assert "definition_bundle" not in blob
        assert "canonical_sha256" not in blob

    def test_authority_model_is_projection_contract_with_three_slots(self) -> None:
        payload = P.authority_model_payload()
        assert payload["authority_model"] == AuthorityModel.projection_contract.value
        assert payload["merge_model"] == "stable_field_three_way"
        assert payload["required_slots"] == [
            BundleSlot.template.value,
            BundleSlot.instrumentation.value,
            BundleSlot.contract.value,
        ]
        assert payload["entry_id"] == P.PILOT_ENTRY_ID
        assert payload["pilot_class"] == P.PILOT_CLASS

    def test_pilot_does_not_reuse_another_pilot_definition_identity(
        self, contract: Any
    ) -> None:
        """任务正文明令：不得借用 D2/G7（及 B60）的 definition identity。逐项比对**不相等**。"""
        from app.services.workpaper_sync import pilot_d2_large_json as D2
        from app.services.workpaper_sync import pilot_simple_checklist as B60

        for other in (D2, B60):
            assert P.PILOT_ENTRY_ID != other.PILOT_ENTRY_ID
            assert P.PILOT_ADAPTER_ID != other.PILOT_ADAPTER_ID
            assert P.TEMPLATE_SHA256 != other.TEMPLATE_SHA256
            assert P.TEMPLATE_RELATIVE_PATH != other.TEMPLATE_RELATIVE_PATH
            assert P.TEMPLATE_ID != other.TEMPLATE_ID
            assert P.TABLE_NAME != other.TABLE_NAME
            assert P.ROWS_TABLE_KEY != other.ROWS_TABLE_KEY
            # `STORE_ITEM_ID` 只有 D2/H1 两个 pilot 有（B60 的载荷不是单条大 item）。
            if hasattr(other, "STORE_ITEM_ID"):
                assert P.STORE_ITEM_ID != other.STORE_ITEM_ID
            assert canonical_digest(P.authority_model_payload()) != canonical_digest(
                other.authority_model_payload()
            )
            assert canonical_digest(P.template_definition_payload()) != canonical_digest(
                other.template_definition_payload()
            )
            assert canonical_digest(
                P.instrumentation_definition_payload()
            ) != canonical_digest(other.instrumentation_definition_payload())
            assert contract.canonical_sha256 != other.load_pilot_contract().canonical_sha256
            assert P.contract_file_path() != other.contract_file_path()

    def test_instrumentation_declares_no_disproved_anchor(self) -> None:
        """被证伪的锚点只能出现在 `forbidden_anchors` 里，绝不能进 `identity_anchors`。

        🔴 判据不能写成「payload 里不含这些字符串」：`forbidden_anchors` 这个字段**就是**
        用来登记它们的，那样写会把正确的登记判成违规（首轮实测的假红）。
        """
        payload = P.instrumentation_definition_payload()
        assert payload["identity_anchors"] == [
            "defined_name_ref",
            "excel_table_sheet_association",
        ]
        for disproved in sorted(X.DISPROVED_SHEET_ANCHORS):
            assert disproved not in payload["identity_anchors"], disproved
        # gate 登记的禁用锚点必须是被证伪集合的子集（登记表不得自由发挥）。
        assert set(payload["forbidden_anchors"]) <= X.DISPROVED_SHEET_ANCHORS, payload[
            "forbidden_anchors"
        ]
        assert payload["forbidden_anchors"], "禁用锚点登记不得为空"
        # 逐个 locator 也不得引用它们。
        for sheet in payload["managed_sheets"]:
            assert sheet["locator"]["anchor"] == "defined_name_ref"
            assert (
                sheet["region_boundary_locator"]["anchor"]
                == "excel_table_sheet_association"
            )
        assert payload["cell_geometry"]["anchor_role"] == "none"


# ═══════════════════════════════════════════════════════════════════════════
# 7. 真实模板上的 extract 基线（非空覆盖计数是硬判据）
# ═══════════════════════════════════════════════════════════════════════════


class TestBaselineExtractOnTheRealTemplate:
    """**Validates: Requirements 6.3 / 6.16 / 14.1**"""

    def test_instrumentation_produces_all_four_carriers(
        self, definitions: FrozenEntryDefinitions
    ) -> None:
        inventory = definitions.identity_inventory
        assert inventory.hidden_sheet_present is True
        assert inventory.table_present is True
        assert inventory.table_ref == f"A{FIRST}:{P.UUID_COL}{LAST}"
        assert set(inventory.defined_names) == {
            f"GT_MANAGED_REGION_{P.TEMPLATE_ID}",
            f"GT_FOOTER_ANCHOR_{P.TEMPLATE_ID}",
            f"GT_SYNC_ANCHOR_{P.TEMPLATE_ID}",
            f"GT_ROW_UUID_RANGE_{P.TEMPLATE_ID}",
        }
        assert len(inventory.row_uuids) == EXPECTED_TEMPLATE_ROW_COUNT
        assert set(inventory.row_uuids.values()) == {
            uid(row) for row in range(FIRST, LAST + 1)
        }

    def test_baseline_extract_reads_back_every_managed_field(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        rows = base_outcome.projection.row_keys[P.ROWS_TABLE_KEY]
        assert len(rows) == EXPECTED_TEMPLATE_ROW_COUNT
        # 🔴 BP-21：350 = 14 受管行 × 25 字段（原 375 = 15 × 25，那 15 行里含排版占位行）
        assert len(base_outcome.projection.values) == (
            EXPECTED_TEMPLATE_ROW_COUNT * EXPECTED_FIELD_COUNT
        ) == 350
        assert base_outcome.anomalies == ()
        assert base_outcome.protected_findings == ()
        assert base_outcome.stats.table_row_counts == {
            P.ROWS_TABLE_KEY: EXPECTED_TEMPLATE_ROW_COUNT
        }

    def test_formula_columns_are_read_with_their_formula_text(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """28 个公式格的公式文本进 `formula_inventory`，且与源模板逐字相同。

        🔴 BP-21：28 = 2 列 × **14 受管行**。模板物理上有 30 个（2 × 15），第 15 行是
        `A27` 那行排版占位 —— 它已不在受管区，其公式属未管理区域（由
        `verify_unmanaged_regions` 把守），不进 `formula_inventory`。
        """
        assert len(base_outcome.formula_inventory) == 2 * EXPECTED_TEMPLATE_ROW_COUNT == 28
        for column, template in sorted(P.FORMULA_TEMPLATES.items()):
            column_key = next(
                row[0] for row in P.MANAGED_FIELD_SPECS if row[1] == column
            )
            for row in range(FIRST, LAST + 1):
                key = P.stable_key_for(column_key, uid(row))
                assert base_outcome.formula_inventory[key] == template.format(r=row), key

    def test_unmanaged_region_coverage_is_not_empty(
        self, base_path: Path, contract: Any, region: Any, binding: X.ExcelIdentityBinding
    ) -> None:
        """8 个 aspect 的覆盖计数落到实测值；7 个 > 0（第 8 个为 0 有专门事实判据）。

        🔴 这条防的是「空集恒等价」：手搓最小 xlsx 上未管理区域是空集，比对必然通过。
        用**真实权威模板**跑出来的计数是硬判据 —— 任何一项掉到 0 都说明比对面被削掉了。
        """
        report = X.verify_unmanaged_regions(
            before=base_path, after=base_path, contract=contract,
            region=region, binding=binding,
        )
        assert report.equivalent is True
        assert report.inspected_aspects == X.UNMANAGED_ASPECTS
        coverage = dict(report.details["coverage"])
        assert coverage == {
            # 🔴 BP-21：485 → 510（+25）。受管区从 13..27 收缩到 13..26 后，`A27` 那行
            #    排版占位行的 25 个格从「受管」变成「未管理」⇒ 计数上升**正是** BP-21
            #    生效的证据。它们此后由未管理区域比对把守（materialize 不碰它们）。
            "managed_sheet_unmanaged_cells": 510,
            # 🔴 4 → 6（spec excel-structural-row-insertion-and-shift-aware-verification
            #    Requirement 1.3）：`_SHEET_STRUCTURE_BLOCKS` 补入了 `dimension` /
            #    `hyperlinks` / `autoFilter` / `rowBreaks` 四项。H1 的受管 sheet
            #    （减少检查表H1-8）实测含 `dimension` 1 个、`hyperlinks` 1 个，
            #    `autoFilter` / `rowBreaks` 各 0 个 ⇒ 4 + 2 = 6。
            #
            #    这是**判据变严**而不是判据被破：那四类结构全部携带行号，插行必然改动
            #    它们，而它们在补入之前**不在任何 aspect 里**（既不在这六个 tag 内，
            #    受管 sheet part 又被 `_classify_parts` 整件排除）—— 改了没人看。
            "managed_sheet_structure": 6,
            "other_sheet_parts": 25,
            "protected_parts": 1,
            "shared_strings_prefix": 0,
            "workbook_and_styles": 3,
            "relationships": 4,
            "other_parts": 4,
        }, coverage
        positive = {name for name, count in coverage.items() if count > 0}
        assert positive == set(X.UNMANAGED_ASPECTS) - {"shared_strings_prefix"}
        assert report.details["part_count"] == 40

    def test_shared_strings_zero_is_a_workbook_fact_not_an_empty_judgement(
        self, base_bytes: bytes
    ) -> None:
        """`shared_strings_prefix = 0` 的**理由**：本工作簿根本没有 sharedStrings.xml。

        这一条把唯一那个 0 变成可打红的事实。模板哪天带上 sharedStrings，这里打红提醒把
        上面的期望计数改成非 0，而不是让一个「一直是 0」的 aspect 悄悄失去判据能力。
        """
        names = set(_read_entries(base_bytes))
        assert "xl/sharedStrings.xml" not in names, sorted(
            name for name in names if "shared" in name
        )
        with zipfile.ZipFile(io.BytesIO(P.read_authoritative_template())) as zf:
            assert "xl/sharedStrings.xml" not in zf.namelist()

    def test_managed_sheet_structure_aspect_covers_the_style_sources(
        self, base_bytes: bytes, sheet_part: str
    ) -> None:
        """`managed_sheet_structure` 的 6 项覆盖 = 样式源 + 位移敏感结构的真实存在。

        6 项 = `sheetPr` + `cols` + `mergeCells` + `dataValidations`（样式源，本来就在）
        ＋ `dimension` + `hyperlinks`（位移敏感结构，spec
        excel-structural-row-insertion-and-shift-aware-verification Requirement 1.3 补入）。
        `autoFilter` / `rowBreaks` 在本模板上各 0 个 —— 它们的判据由该 spec 的
        zip 级注入 fixture 承担（真实模板上全 0，在这里断言等于空转）。
        """
        xml = _read_entries(base_bytes)[sheet_part].decode("utf-8")
        assert "<mergeCells" in xml
        assert "<cols" in xml
        # 位移敏感结构的真实存在（补入 `_SHEET_STRUCTURE_BLOCKS` 的理由）
        assert xml.count("<dimension") == 1, xml.count("<dimension")
        assert xml.count("<hyperlinks") == 1, xml.count("<hyperlinks")
        assert "<autoFilter" not in xml
        assert "<rowBreaks" not in xml
        assert xml.count("<dataValidation ") == 2, xml.count("<dataValidation ")
        # 条件格式 0 条、sheetProtection 关 —— 与契约 review 里登记的一致。
        assert "<conditionalFormatting" not in xml
        assert "<sheetProtection" not in xml
        payload = json.loads(P.contract_file_path().read_text(encoding="utf-8"))
        styles = payload["review"]["style_sources"]
        assert styles["conditional_formatting_count"] == 0
        assert styles["sheet_protection"] is False
        assert len(styles["data_validations"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 8. Property 23 / 66 / 27：插删重排复制后的 identity、公式范围与未管理区域
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty23And66StructuralOperations:
    """**Validates: Requirements 6.5 / 6.9 / 6.16** · Property 23 / 66

    Property 23 原文：删除/重排/再新增后旧 `row_uuid` **不复用**，原行数据**不串到新行**。
    因此三件事各有独立判据：不复用、不串行、重排不改身份。

    Property 66 的保留门语义是**子集**（`expected ⊆ observed`）：OO 合法插行/排序/复制会
    新增 identity 并改变行号与 Table ref 的行区间，那些**不是**漂移。本组既证「丢了必红」，
    也证「插行不算漂移」（反向自检）。
    """

    def test_reorder_keeps_values_attached_to_identity(
        self,
        base_bytes: bytes,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
        base_path: Path,
        contract: Any,
        region: Any,
    ) -> None:
        """交换首尾行的 UUID 与值 ⇒ 各自的值仍跟着自己的 UUID，未管理区域不变。"""
        swapped = patch_cells(
            base_bytes,
            sheet_part,
            {
                f"{P.UUID_COL}{FIRST}": uid(LAST),
                f"{P.UUID_COL}{LAST}": uid(FIRST),
                f"I{FIRST}": 100 + LAST,
                f"I{LAST}": 100 + FIRST,
                f"C{FIRST}": f"值C{LAST}",
                f"C{LAST}": f"值C{FIRST}",
            },
        )
        path = workdir / "reordered.xlsx"
        path.write_bytes(swapped)
        outcome = extract(path, definitions, binding)
        values = outcome.projection.values
        # 期望值是**源侧**写进去的字面量，不是调用被测函数算出来的。
        for row in (FIRST, LAST):
            assert values[P.stable_key_for("original_cost", uid(row))].value == 100 + row
            assert values[P.stable_key_for("asset_no", uid(row))].value == f"值C{row}"
        assert outcome.anomalies == ()
        assert set(outcome.projection.row_keys[P.ROWS_TABLE_KEY]) == {
            uid(row) for row in range(FIRST, LAST + 1)
        }
        report = X.verify_unmanaged_regions(
            before=base_path, after=path, contract=contract,
            region=region, binding=binding,
        )
        assert report.equivalent is True, report.first_difference

    def test_row_insert_is_not_a_retention_failure(
        self,
        base_bytes: bytes,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
    ) -> None:
        """Property 66 的**反向自检**：Table ref 行区间变大不得被判成载体漂移。

        判据若写成「行区间/行号必须逐字相等」，合法插删行会全部打红，调用方只能整体关掉
        这道门。这里断言：新 identity 出现、15 个冻结 identity 一个不少、列跨度不变、
        行区间从 `A13:AB27` 变成 `A13:AB28` 而保留门仍 PASS。
        """
        new_row = LAST + 1
        path = workdir / "row_inserted.xlsx"
        path.write_bytes(
            add_row(
                base_bytes,
                sheet_part,
                row=new_row,
                cells={
                    f"{P.UUID_COL}{new_row}": uid(new_row),
                    f"I{new_row}": 999,
                    f"C{new_row}": "新增行",
                },
            )
        )
        outcome = extract(path, definitions, binding)
        keys = set(outcome.projection.row_keys[P.ROWS_TABLE_KEY])
        assert uid(new_row) in keys
        assert {uid(row) for row in range(FIRST, LAST + 1)} <= keys
        assert outcome.stats.table_row_counts[P.ROWS_TABLE_KEY] == (
            EXPECTED_TEMPLATE_ROW_COUNT + 1
        )
        assert (
            outcome.projection.values[
                P.stable_key_for("original_cost", uid(new_row))
            ].value
            == 999
        )
        # 行区间真的变了（否则这条反向自检是空判据）。
        assert definitions.identity_inventory.table_ref == f"A{FIRST}:{P.UUID_COL}{LAST}"
        assert outcome.identity_inventory.table_ref == (
            f"A{FIRST}:{P.UUID_COL}{new_row}"
        )
        assert (
            outcome.identity_inventory.table_ref
            != definitions.identity_inventory.table_ref
        )
        # 而保留门仍 PASS（子集语义）。
        X.assert_identity_inventory_retained(
            expected=definitions.identity_inventory,
            observed=outcome.identity_inventory,
            entry_id=P.PILOT_ENTRY_ID,
        )

    def test_appending_onto_the_footer_row_is_reported_by_the_unmanaged_gate(
        self,
        base_bytes: bytes,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
        base_path: Path,
        contract: Any,
        region: Any,
    ) -> None:
        """直接写到 footer 行 ⇒ 未管理区域 gate 必须报出来。

        🔴 BP-21 起受管区**不再紧贴** footer：中间隔着 `A27` 那行排版占位行
        （`LAST + 1 == 27 != FOOTER_ROW == 28`）。所以这条不再能用「受管区已饱和」来
        论证，改为**显式**写 footer 行 —— 判据要证的东西没变：往受管区外写一格，
        「未管理区域等价」必须打红。

        它同时是未管理区域判据的**非空证明**：写到 footer 行后
        `managed_sheet_unmanaged_cells` 计数变化、gate 打红，而 `A28` 的 `合计`
        被当成 `seq` 读回来还会产生一条 `type_normalization_failure`。
        「未管理区域等价」因此不是空集恒真。
        """
        new_row = P.FOOTER_ROW
        # 受管区与 footer 之间确实隔着排版占位行（BP-21 的可见后果）
        assert LAST + 1 == P.TEMPLATE_PHYSICAL_LAST_ROW < P.FOOTER_ROW, (
            LAST,
            P.TEMPLATE_PHYSICAL_LAST_ROW,
            P.FOOTER_ROW,
        )
        path = workdir / "onto_footer.xlsx"
        path.write_bytes(
            add_row(
                base_bytes, sheet_part, row=new_row,
                cells={f"{P.UUID_COL}{new_row}": uid(new_row), f"I{new_row}": 999},
            )
        )
        report = X.verify_unmanaged_regions(
            before=base_path, after=path, contract=contract,
            region=region, binding=binding,
        )
        assert report.equivalent is False
        assert "managed_sheet_unmanaged_cells" in (report.first_difference or "")
        # 🔴 BP-21：485/486 → 510/511（受管区收缩后 `A27` 那行的 25 个格转入未管理面）
        assert "510" in (report.first_difference or "")
        assert "511" in (report.first_difference or "")
        outcome = extract(path, definitions, binding)
        kinds = [item.kind.value for item in outcome.anomalies]
        # 🔴 BP-21：两条而不是一条。`add_row` 把 Table ref 撑到 28 后，受管区外的**两**行
        #    都被卷进来：`A27` 的排版占位 `……` 与 `A28` 的 `合计`，两者都按 `seq`
        #    (`value_type=integer`) 规范化失败。
        #    这比原判据更强 —— 它同时证明「占位行在受管区外」与「footer 在受管区外」，
        #    且碰它们都会显性化而不是静默取值。
        assert kinds == ["type_normalization_failure"] * 2, kinds
        by_detail = {item.stable_field_key: item.detail for item in outcome.anomalies}
        assert len(by_detail) == 2, by_detail

        # 占位行那一条：它没有 row UUID（instrumentation 只写到受管末行 26）⇒ 身份是**新铸**的
        placeholder = [
            key for key, detail in by_detail.items()
            if f"A{P.TEMPLATE_PHYSICAL_LAST_ROW}" in detail
        ]
        assert len(placeholder) == 1, by_detail
        assert placeholder[0].endswith("/seq"), placeholder
        assert "MINTED" in placeholder[0], (
            "占位行不该带 instrumentation 写的 row UUID —— 带了说明它仍被当业务行"
        )
        assert "……" in by_detail[placeholder[0]]

        # footer 那一条：身份是测试自己写进去的
        footer_key = P.stable_key_for("seq", uid(new_row))
        assert footer_key in by_detail, sorted(by_detail)
        assert P.FOOTER_MARKER in by_detail[footer_key]

    def test_lost_row_identity_is_a_retention_failure(
        self,
        base_bytes: bytes,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
    ) -> None:
        """只丢**一个** row UUID（其余仍在）⇒ 保留门打红，不得静默少读一行。"""
        path = workdir / "one_uuid_lost.xlsx"
        path.write_bytes(
            patch_cells(
                base_bytes, sheet_part, {f"{P.UUID_COL}{LAST}": None, f"I{LAST}": None}
            )
        )
        with pytest.raises(X.IdentityRetentionError) as exc:
            extract(path, definitions, binding)
        assert uid(LAST) in str(exc.value)
        assert "Property 23" in str(exc.value) or "Property 66" in str(exc.value)

    def test_new_row_gets_minted_identity_never_reusing_the_deleted_one(
        self,
        base_bytes: bytes,
        sheet_part: str,
        contract: Any,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
    ) -> None:
        """删一行再在同位置新增空 UUID ⇒ 分配**新** ID，绝不复用已删的那个（Property 23）。

        🔴 frozen 预期里必须先去掉那一行，否则会先被保留门拦住（那是上一条判据）——
        「在真实数据上分支不可达 = 永久 GREEN」的防线。
        """
        deleted = uid(LAST)
        path = workdir / "minted.xlsx"
        path.write_bytes(
            patch_cells(base_bytes, sheet_part, {f"{P.UUID_COL}{LAST}": "", f"I{LAST}": 777})
        )
        definitions = make_definitions(contract, base_bytes, drop_identity=deleted)
        outcome = extract(path, definitions, binding)
        keys = outcome.projection.row_keys[P.ROWS_TABLE_KEY]
        assert deleted not in keys, keys
        minted = [key for key in keys if key.startswith("GTROW-MINTED-")]
        assert len(minted) == 1, keys
        assert (
            outcome.projection.values[P.stable_key_for("original_cost", minted[0])].value
            == 777
        )
        # 原行数据不得串到新行：14 个未动的 identity 各自的值一个不差。
        for row in range(FIRST, LAST):
            assert (
                outcome.projection.values[
                    P.stable_key_for("original_cost", uid(row))
                ].value
                == 100 + row
            )

    def test_copied_row_duplicate_identity_is_a_structural_conflict(
        self,
        base_bytes: bytes,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        workdir: Path,
    ) -> None:
        """复制行造成的重复 UUID 默认是结构冲突（Requirement 6.15），不得静默合并。"""
        new_row = LAST + 1
        path = workdir / "copied.xlsx"
        path.write_bytes(
            add_row(
                base_bytes, sheet_part, row=new_row,
                cells={f"{P.UUID_COL}{new_row}": uid(FIRST), f"I{new_row}": 888},
            )
        )
        outcome = extract(path, definitions, binding)
        kinds = {item.kind.value for item in outcome.anomalies}
        assert "duplicate_row_identity" in kinds, kinds
        assert "multi_location_divergence" in kinds, kinds
        assert outcome.identity_inventory.duplicate_row_uuids == (uid(FIRST),)

    def test_structural_insert_beyond_the_skeleton_plans_a_row_shift(
        self,
        base_bytes: bytes,
        base_outcome: X.ExcelExtractOutcome,
        contract: Any,
        binding: X.ExcelIdentityBinding,
    ) -> None:
        """merged projection 里出现没有物理行的 identity ⇒ **算出插行计划**（不再 fail closed）。

        ═══ 这条判据的期望值被两件事合法地改过 ═══════════════════════════════════

        原状：Task 38 把结构性插删行留给后续，于是「超出骨架」一律
        `RowSetDivergenceError`。本判据当时钉的是那个 fail-closed。

        现状两个前置都已满足：

        1. spec `excel-structural-row-insertion-and-shift-aware-verification` 的 Wave 4
           把 `excel_row_shift` 接进了 `plan_managed_writes`；
        2. 本 pilot 的契约（BP-21 那一轮）如实声明了
           `footer_anchor.carries_total_formula = True`（`I28..O28` 实测 7 条
           `SUM(x13:x27)`）⇒ 引擎**有权**按声明的位移量扩张合计区间。
           不声明时它仍 fail closed（`blocked_total_formula_not_extendable`），
           那条语义没有被放宽。

        ⇒ 期望值改成「插行计划的形态正确」。**判据没有变弱**：原判据要防的是「静默丢行」，
        本判据末段直接断言那个新 identity 真的落成了写入（丢行会打红）。

        🔴 插入点 27 的业务含义：它恰在受管末行 26 之后、`A27` 那行排版占位之前 ⇒
        新数据行插进去后，续行省略号被推到 28、footer 推到 29，省略号仍留在数据行**下方**。
        这正是 BP-21 把占位行剔出受管区后想要的结果；若占位行仍算业务行，插入点会是 28
        （footer 上），那是错的。
        """
        spec = contract.field_by_stable_key(P.stable_key_for("original_cost"))
        extra = "disp-brand-new-row"
        values = dict(base_outcome.projection.values)
        key = P.stable_key_for("original_cost", extra)
        values[key] = FieldValue(
            stable_key=key, value=1, value_type=spec.value_type,
            mode=spec.mode, row_key=extra,
        )
        projection = Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=values,
            row_keys={
                P.ROWS_TABLE_KEY: base_outcome.projection.row_keys[P.ROWS_TABLE_KEY]
                + (extra,)
            },
        )
        plan = M.plan_managed_writes(
            projection=projection,
            contract=contract,
            region=base_outcome.region,
            binding=binding,
            scan=base_outcome.scan,
            substrate_entries=_read_entries(base_bytes),
            substrate_formulas=base_outcome.formula_inventory,
            runtime_binding={"GT_FOOTER_ROW": str(P.FOOTER_ROW)},
        )

        shift = plan.row_shift
        assert shift is not None, "多出一个行身份却没算插行计划 —— 那会静默丢行"
        assert shift.count == 1, shift
        assert shift.table_key == P.ROWS_TABLE_KEY, shift
        # 插入点紧跟**受管**末行，而不是紧跟 footer
        assert shift.insert_at == LAST + 1 == 27, shift
        assert shift.insert_at == P.TEMPLATE_PHYSICAL_LAST_ROW, shift
        assert shift.insert_at < P.FOOTER_ROW, shift
        # 样式源是最后一条**业务**行（不是占位行）
        assert shift.style_from == LAST == 26, shift

        # 🔴 反向判据：新 identity 必须真的落成写入，不得被静默丢掉
        written_rows = {write.row_key for write in plan.writes if write.row_key}
        assert extra in written_rows, sorted(written_rows)[:5]

    def test_footer_formula_range_still_covers_the_managed_rows(
        self, base_bytes: bytes, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """公式范围判据：footer 的 SUM 区间必须覆盖当前受管行区间（Task 38 的顺序门）。"""
        entries = _read_entries(base_bytes)
        footer_row = M.assert_footer_anchor_stable(
            entries=entries,
            sheet_part=base_outcome.region.sheet_part,
            contract=base_outcome.definitions.contract
            if hasattr(base_outcome, "definitions")
            else P.load_pilot_contract(),
            runtime_binding={"GT_FOOTER_ROW": str(P.FOOTER_ROW)},
        )
        assert footer_row == P.FOOTER_ROW
        M.assert_footer_formula_covers_managed_rows(
            entries=entries,
            sheet_part=base_outcome.region.sheet_part,
            footer_row=footer_row,
            region=base_outcome.region,
        )

    def test_footer_anchor_drift_is_detected(
        self, base_bytes: bytes, base_outcome: X.ExcelExtractOutcome, contract: Any
    ) -> None:
        """反向自检：把 footer marker 改掉 ⇒ 定位不到即结构漂移，必须打红。"""
        entries = dict(_read_entries(base_bytes))
        part = base_outcome.region.sheet_part
        xml = entries[part].decode("utf-8")
        # 模板把中文写成数字字符引用（见 TestUpstreamRelsAndNamespaceDefectsAreFixed）。
        encoded = "".join(f"&#{ord(char)};" for char in P.FOOTER_MARKER)
        assert encoded in xml, encoded
        entries[part] = xml.replace(encoded, "&#20313;&#39069;").encode("utf-8")
        with pytest.raises(M.FooterAnchorDriftError, match=P.FOOTER_MARKER):
            M.assert_footer_anchor_stable(
                entries=entries, sheet_part=part, contract=contract,
                runtime_binding={"GT_FOOTER_ROW": str(P.FOOTER_ROW)},
            )


# ═══════════════════════════════════════════════════════════════════════════
# 9. store 载荷拆分与 Property 27（delete/update 不整表覆盖）
# ═══════════════════════════════════════════════════════════════════════════


class TestStorePayloadSplit:
    """**Validates: Requirements 6.5 / 6.9**"""

    def test_split_yields_one_field_per_column_per_row(self, contract: Any) -> None:
        rows = store_rows(4)
        projection = P.build_store_projection(rows, contract=contract)
        assert len(projection.row_keys[P.ROWS_TABLE_KEY]) == 4
        assert len(projection.values) == 4 * EXPECTED_FIELD_COUNT
        for identity in projection.row_keys[P.ROWS_TABLE_KEY]:
            for row_spec in P.MANAGED_FIELD_SPECS:
                assert P.stable_key_for(row_spec[0], identity) in projection.values

    def test_row_identity_comes_from_the_payload_not_the_index(
        self, contract: Any
    ) -> None:
        rows = store_rows(3)
        keys = P.build_store_projection(rows, contract=contract).row_keys[P.ROWS_TABLE_KEY]
        assert keys == tuple(row[P.ROW_IDENTITY_STORE_KEY] for row in rows)
        for ordinal, key in enumerate(keys):
            assert key != str(ordinal)
            assert "fixture" in key

    def test_missing_row_identity_fails_closed(self) -> None:
        with pytest.raises(P.StorePayloadError, match="Property 23"):
            list(P.iter_store_rows([{"originalCost": 1}]))

    def test_duplicate_row_identity_fails_closed(self) -> None:
        rows = store_rows(2)
        rows[1][P.ROW_IDENTITY_STORE_KEY] = rows[0][P.ROW_IDENTITY_STORE_KEY]
        with pytest.raises(P.StorePayloadError, match="重复行身份"):
            list(P.iter_store_rows(rows))

    def test_non_array_payload_fails_closed(self) -> None:
        with pytest.raises(P.StorePayloadError, match="行对象数组"):
            list(P.iter_store_rows('{"rows": []}'))

    def test_non_object_element_fails_closed(self) -> None:
        with pytest.raises(P.StorePayloadError, match="不是对象"):
            list(P.iter_store_rows(["x"]))

    def test_invalid_json_fails_closed(self) -> None:
        with pytest.raises(P.StorePayloadError, match="不是合法 JSON"):
            list(P.iter_store_rows("{not json"))

    def test_bytes_and_text_and_parsed_inputs_agree(self, contract: Any) -> None:
        rows = store_rows(2)
        text = json.dumps(rows, ensure_ascii=False)
        parsed = P.build_store_projection(rows, contract=contract)
        from_text = P.build_store_projection(text, contract=contract)
        from_bytes = P.build_store_projection(text.encode("utf-8"), contract=contract)
        for other in (from_text, from_bytes):
            assert other.row_keys == parsed.row_keys
            assert set(other.values) == set(parsed.values)

    def test_failure_kinds_are_reachable_and_mutually_distinct(self) -> None:
        """四类坏载荷各真触发一次、集合基数 == 4，且与选型错误分型不同。

        🔴 比「每类各测一遍」强：后者在两类被合并成同一分支时**全部仍绿**。
        """
        details: list[str] = []
        for bad in ('{"rows": []}', "{not json", [{"x": 1}], ["x"]):
            with pytest.raises(P.StorePayloadError) as exc:
                list(P.iter_store_rows(bad))
            details.append(str(exc.value).split("——")[0].strip())
        rows = store_rows(2)
        rows[1][P.ROW_IDENTITY_STORE_KEY] = rows[0][P.ROW_IDENTITY_STORE_KEY]
        with pytest.raises(P.StorePayloadError) as exc:
            list(P.iter_store_rows(rows))
        details.append(str(exc.value).split("——")[0].strip())
        assert len(set(details)) == 5, details
        assert P.StorePayloadError.error_code != P.PilotSelectionError.error_code
        assert not issubclass(P.StorePayloadError, P.PilotSelectionError)
        assert not issubclass(P.PilotSelectionError, P.StorePayloadError)

    def test_split_uses_the_contract_as_the_spec_source(self, contract: Any) -> None:
        """写错一个 column_key 会立刻炸，而不是静默产出契约里没有的字段。"""
        rows = store_rows(1)
        identity = rows[0][P.ROW_IDENTITY_STORE_KEY]
        collected = list(
            P.split_store_row(rows[0], row_identity=identity, contract=contract)
        )
        assert len(collected) == EXPECTED_FIELD_COUNT
        for key, _value, spec in collected:
            assert key.startswith(f"{P.ROWS_TABLE_KEY}/{identity}/")
            assert spec is contract.field_by_stable_key(
                P.stable_key_for(key.rsplit("/", 1)[-1])
            )

    def test_row_and_field_budgets_are_wired_into_the_split(self, contract: Any) -> None:
        """预算由 Task 37 的 `StreamingProjectionBudget` 边读边判（N-1/N/N+1 三侧）。"""
        limits = scaled_limits(max_table_rows=3)
        assert P.build_store_projection(
            store_rows(3), contract=contract, limits=limits
        ).row_keys[P.ROWS_TABLE_KEY] == tuple(
            row[P.ROW_IDENTITY_STORE_KEY] for row in store_rows(3)
        )
        with pytest.raises(BudgetExceededError):
            P.build_store_projection(store_rows(4), contract=contract, limits=limits)
        field_limit = scaled_limits(max_projection_fields=EXPECTED_FIELD_COUNT * 2)
        P.build_store_projection(store_rows(2), contract=contract, limits=field_limit)
        with pytest.raises(BudgetExceededError):
            P.build_store_projection(store_rows(3), contract=contract, limits=field_limit)
        # 生产预算下真实规模远未越界（判据不是"预算恰好很小"）。
        production = load_limits()
        assert production.max_table_rows > EXPECTED_TEMPLATE_ROW_COUNT
        assert production.max_projection_fields > EXPECTED_FIELD_COUNT * 100

    def test_module_declares_no_budget_threshold(self) -> None:
        """源码级判据：阈值数字只在 `limits` 配置里，生产模块一个都不写。"""
        source = Path(P.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        big = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
            and node.value > 100
        ]
        assert not big, big


class TestProperty27DeleteUpdateDoesNotOverwriteTheWholeTable:
    """**Validates: Requirements 6.8 / 6.9** · Property 27

    Property 27 原文：一侧删行、另一侧改同 `row_uuid` 时**只**生成该行冲突，其他行照常合并。

    🔴 落点是 required set 里真实存在的 merge 家族两条场景，**不是**
    `dynamic_row_add_delete_reorder_copy` —— 后者对任何 xlsx entry 结构性不可达
    （见 `TestUpstreamDebtsAreVisibleFacts`）。oracle 跑在真实契约形态的载荷上。
    """

    ROWS = 12

    def _projection(self, contract: Any, rows: list[dict[str, Any]]) -> Projection:
        return P.build_store_projection(rows, contract=contract)

    def test_only_the_touched_row_conflicts(self, contract: Any) -> None:
        from app.services.workpaper_sync.merge import merge_projections

        base_rows = store_rows(self.ROWS)
        victim = base_rows[3][P.ROW_IDENTITY_STORE_KEY]
        current = [row for row in base_rows if row[P.ROW_IDENTITY_STORE_KEY] != victim]
        incoming = json.loads(json.dumps(base_rows))
        for row in incoming:
            if row[P.ROW_IDENTITY_STORE_KEY] == victim:
                row["originalCost"] = 987654.0
        outcome = merge_projections(
            base=self._projection(contract, base_rows),
            current=self._projection(contract, current),
            incoming=self._projection(contract, incoming),
            contract=contract,
        )
        kinds = [record.kind.value for record in outcome.conflicts.records]
        assert kinds.count("delete_update") == 1, kinds
        assert outcome.conflict_count == 1, kinds
        assert victim in outcome.conflicts.records[0].locator.stable_field_key

    def test_every_other_row_and_field_merges_normally(self, contract: Any) -> None:
        """**非空**判据：逐条断言其余 11 行 × 25 字段 = 275 个字段与 base 相同，不符 0 条。"""
        from app.services.workpaper_sync.merge import merge_projections

        base_rows = store_rows(self.ROWS)
        victim = base_rows[3][P.ROW_IDENTITY_STORE_KEY]
        current = [row for row in base_rows if row[P.ROW_IDENTITY_STORE_KEY] != victim]
        incoming = json.loads(json.dumps(base_rows))
        for row in incoming:
            if row[P.ROW_IDENTITY_STORE_KEY] == victim:
                row["originalCost"] = 987654.0
        base_projection = self._projection(contract, base_rows)
        outcome = merge_projections(
            base=base_projection,
            current=self._projection(contract, current),
            incoming=self._projection(contract, incoming),
            contract=contract,
        )
        compared = 0
        mismatched: list[str] = []
        for row in base_rows:
            identity = row[P.ROW_IDENTITY_STORE_KEY]
            if identity == victim:
                continue
            for spec in P.MANAGED_FIELD_SPECS:
                key = P.stable_key_for(spec[0], identity)
                compared += 1
                # `value_of` 返回 `ValueEnvelope`（`.value` 才是原值）—— 直接与原值比会
                # 让 275 条**全部**"不符"，那是假红而不是缺陷（首轮实测）。
                got = outcome.merged.get(key)
                if got is None or got.value != base_projection.values[key].value:
                    mismatched.append(key)
        assert compared == (self.ROWS - 1) * EXPECTED_FIELD_COUNT == 275, compared
        assert mismatched == [], mismatched[:5]
        # 被删那一行的 25 个字段都不在 merged 里（tombstone），且只此一行。
        gone = [
            P.stable_key_for(spec[0], victim)
            for spec in P.MANAGED_FIELD_SPECS
            if P.stable_key_for(spec[0], victim) not in outcome.merged.values
        ]
        assert len(gone) + len(mismatched) >= 1, "delete/update 必须留下可见痕迹"

    def test_reorder_alone_is_not_a_whole_table_overwrite(self, contract: Any) -> None:
        """只把行序反转 ⇒ 零冲突（位置变化不得被误判为整表覆盖）。"""
        from app.services.workpaper_sync.merge import merge_projections

        base_rows = store_rows(self.ROWS)
        outcome = merge_projections(
            base=self._projection(contract, base_rows),
            current=self._projection(contract, base_rows),
            incoming=self._projection(contract, list(reversed(base_rows))),
            contract=contract,
        )
        assert outcome.conflict_count == 0, [
            record.kind.value for record in outcome.conflicts.records
        ]
        # **非空**判据：12 行 × 25 字段 = 300 个字段逐个仍在且值不变。
        base_projection = self._projection(contract, base_rows)
        compared = 0
        for row in base_rows:
            identity = row[P.ROW_IDENTITY_STORE_KEY]
            for spec in P.MANAGED_FIELD_SPECS:
                key = P.stable_key_for(spec[0], identity)
                assert key in outcome.merged.values, key
                assert outcome.merged.values[key].value == base_projection.values[key].value, key
                compared += 1
        assert compared == self.ROWS * EXPECTED_FIELD_COUNT == 300, compared

    def test_different_field_merge_and_same_field_conflict_really_run(
        self, contract: Any
    ) -> None:
        """Property 25/26 在本契约形态上真跑一次（`projection_contract` 不得被替换掉）。"""
        from app.services.workpaper_sync.merge import merge_projections

        base_rows = store_rows(3)
        identity = base_rows[0][P.ROW_IDENTITY_STORE_KEY]
        current = json.loads(json.dumps(base_rows))
        current[0]["originalCost"] = 111.0
        incoming = json.loads(json.dumps(base_rows))
        incoming[0]["accDep"] = 222.0
        merged = merge_projections(
            base=self._projection(contract, base_rows),
            current=self._projection(contract, current),
            incoming=self._projection(contract, incoming),
            contract=contract,
        )
        assert merged.conflict_count == 0, [
            record.kind.value for record in merged.conflicts.records
        ]
        assert merged.merged.values[P.stable_key_for("original_cost", identity)].value == 111.0
        assert merged.merged.values[P.stable_key_for("acc_dep", identity)].value == 222.0

        incoming_same = json.loads(json.dumps(base_rows))
        incoming_same[0]["originalCost"] = 333.0
        conflicted = merge_projections(
            base=self._projection(contract, base_rows),
            current=self._projection(contract, current),
            incoming=self._projection(contract, incoming_same),
            contract=contract,
        )
        keys = [
            record.locator.stable_field_key for record in conflicted.conflicts.records
        ]
        assert keys == [P.stable_key_for("original_cost", identity)], keys
        record = conflicted.conflicts.records[0]
        # 三值完整（Property 26）：base / current / incoming 各自可追溯。
        assert record.base.value == float(1)
        assert record.current.value == 111.0
        assert record.incoming.value == 333.0
        # 冲突未裁决时 merged 不得等于 incoming（不得静默选 OO 侧）。
        assert (
            conflicted.merged.values[P.stable_key_for("original_cost", identity)].value != 333.0
        )


# ═══════════════════════════════════════════════════════════════════════════
# 10. Property oracle 落点（P22 / P23 / P27 / P49 / P66 / P69）
# ═══════════════════════════════════════════════════════════════════════════

#: 本任务要验的 6 条 Property → 它在 **本 entry 自己的** required scenario set 里的落点。
#:
#: 🔴 P22 / P23 / P27 都**不**落在 `dynamic_column_stable_keys` /
#: `dynamic_row_add_delete_reorder_copy` 上：那两条是 AC 6.4 / 6.9 自己的场景，但它们只在
#: `mount_cardinality == "dynamic"` 时进 required set，而那个字段量的是前端宿主挂载基数
#: ⇒ 对**任何 xlsx entry** 不可达（见
#: :data:`P.UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY`，
#: 并由 `TestUpstreamDebtsAreVisibleFacts` 把它变成可打红的实测事实）。
#: 三条改落 merge 家族两条 —— 它们消费的正是 stable field key 与 row identity。
PROPERTY_ORACLE_LANDING: dict[str, tuple[str, ...]] = {
    "P22": ("different_field_merge",),
    "P23": ("different_field_merge", "same_field_conflict_resolve"),
    "P27": ("different_field_merge", "same_field_conflict_resolve"),
    "P49": ("identity_retention",),
    "P66": ("identity_retention",),
    "P69": ("single_participant_close",),
}


class TestPropertyOracleLanding:
    """**Validates: Requirements 12.10 / 14.1**"""

    def test_every_property_lands_on_a_registered_oracle(self) -> None:
        """六条 Property 各有 oracle，**且**该 oracle 真的在本 entry 的 required set 里。"""
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        required = set(
            derive_for_manifest_entry(entry, authority_model=P.AUTHORITY_MODEL).scenario_ids
        )
        assert len(PROPERTY_ORACLE_LANDING) == 6, sorted(PROPERTY_ORACLE_LANDING)
        for prop, scenarios in sorted(PROPERTY_ORACLE_LANDING.items()):
            assert scenarios, prop
            for scenario_id in scenarios:
                assert scenario_id in PH.SCENARIO_ORACLES, (prop, scenario_id)
                assert scenario_id in required, (prop, scenario_id)

    def test_dynamic_family_scenarios_are_not_in_the_required_set(self) -> None:
        """P22/P23/P27 之所以改落 merge 家族：那两条场景确实不在分母里。"""
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        required = set(
            derive_for_manifest_entry(entry, authority_model=P.AUTHORITY_MODEL).scenario_ids
        )
        assert "dynamic_row_add_delete_reorder_copy" not in required
        assert "dynamic_column_stable_keys" not in required
        # 但它们**登记**着（不是不存在）—— 这正是欠账而不是设计如此。
        assert "dynamic_row_add_delete_reorder_copy" in PH.SCENARIO_ORACLES
        assert "dynamic_column_stable_keys" in PH.SCENARIO_ORACLES

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
        """P49/P66 的落点需要真实 OO ⇒ 今天只能 UNVERIFIABLE（Property 49 后半句）。"""
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
        assert need_black_box - offline_only == {"identity_retention"}
        for scenario_id in sorted(need_black_box - offline_only):
            assert PH.SCENARIO_ORACLES[scenario_id].needs_black_box, scenario_id

    def test_pilot_class_stays_unverifiable_until_server_recompute(self) -> None:
        assessment = PH.assess_pilot_classes()[PH.PilotClass.h1_grouped_dynamic]
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
# 11. 四条登记的上游缺口：可打红的实测事实，不是注释
# ═══════════════════════════════════════════════════════════════════════════


class TestUpstreamDebtsAreVisibleFacts:
    """**Validates: Requirements 6.3 / 6.9 / 12.10**"""

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

    def test_resolve_published_definitions_never_returns_none(self, contract: Any) -> None:
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
                    session=None, representation=None, contract=contract
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
        observed = P.assert_dynamic_family_is_unreachable_for_xlsx_entries()
        assert observed["xlsx_dynamic"] == ()
        assert observed["dynamic"] == ("docx/gt-wp-renderer",), observed["dynamic"]
        assert observed["total"] == 186, observed["total"]

    def test_dynamic_debt_is_retracted_when_upstream_fixes_the_gate(
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
        assert table.header_rows >= 2

    def test_four_level_header_debt_is_a_measured_schema_limit(
        self, workbook: Any
    ) -> None:
        """三段链条：H1-2 表头物理 4 行 / schema 硬限 1..3 / Task 13 把 4 锁死为被拒。"""
        from openpyxl.utils import get_column_letter

        sheet = workbook["明细表H1-2"]
        # ① 四行表头是源侧事实：E 列的四级路径逐格取出来。
        rows = (9, 10, 11, 12)
        merges = list(sheet.merged_cells.ranges)

        def covering(row: int, column: str) -> str:
            index = 0
            for char in column:
                index = index * 26 + (ord(char) - 64)
            for rng in merges:
                if (
                    rng.min_row <= row <= rng.max_row
                    and rng.min_col <= index <= rng.max_col
                ):
                    return f"{get_column_letter(rng.min_col)}{rng.min_row}"
            return f"{column}{row}"

        path = [str(sheet[covering(row, "E")].value) for row in rows]
        assert path == ["固定资产原值", "未审数", "本期增加", "金额"], path
        assert len(set(path)) == 4, "四级路径的四个层级必须互不相同，否则它其实不是四级"
        # ② schema 硬限 1..3。
        contracts_source = Path(
            __import__(
                "app.services.workpaper_sync.contracts", fromlist=["x"]
            ).__file__
        ).read_text(encoding="utf-8")
        assert "not 1 <= header_rows <= 3" in contracts_source
        # ③ Task 13 显式把 4 锁死为被拒。
        task13 = (
            Path(__file__).parent / "test_task13_contract_registry.py"
        ).read_text(encoding="utf-8")
        assert '@pytest.mark.parametrize("header_rows", [0, 4, "2", True])' in task13
        # ④ 欠账文案点名 owner 与修法。
        note = P.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE
        assert "header_rows" in note and "明细表H1-2" in note and "owner" in note

    def test_disposal_method_enum_domain_split_is_a_measured_fact(
        self, worksheet: Any
    ) -> None:
        """模板 DV 值域与前端下拉值域**互不为子集**，逐项从两个真源读出来比。"""
        template_domain = {
            value
            for dv in worksheet.data_validations.dataValidation
            if str(dv.sqref) == P.DISPOSAL_METHOD_DV_CELL_RANGE
            for value in str(dv.formula1).strip('"').split(",")
        }
        assert template_domain == set(P.DISPOSAL_METHOD_DV_VALUES)
        vue = _DISPOSAL_TAB.read_text(encoding="utf-8")
        block = re.search(
            r"v-model=\"row\.disposalMethod\".*?</el-select>", vue, re.S
        )
        assert block, "前端 disposalMethod 下拉形态已变"
        frontend_domain = set(re.findall(r'label="([^"]+)" value="\1"', block.group(0)))
        assert frontend_domain == {"出售", "报废", "损毁", "捐赠", "盘亏", "其他"}, (
            frontend_domain
        )
        assert not template_domain <= frontend_domain
        assert not frontend_domain <= template_domain
        assert template_domain & frontend_domain == set(), (
            template_domain & frontend_domain
        )
        note = P.UPSTREAM_DEBT_DISPOSAL_METHOD_ENUM_DOMAIN_SPLIT
        assert "减少方式" in note and "owner" in note and "不自造映射" in note

    def test_contract_never_invents_a_domain_mapping(self, contract_payload: Any) -> None:
        """反向判据：契约里**不得**出现任何 `出售→处置` 一类的自造映射。"""
        blob = json.dumps(contract_payload, ensure_ascii=False, sort_keys=True)
        for invented in ("出售", "报废", "损毁", "捐赠", "盘亏"):
            assert invented not in blob, invented

    def test_remaining_debts_are_registered_and_mutually_distinct(self) -> None:
        """剩余欠账各自独立可辨（合成一条会让其余的撤销条件无处可查）。

        原第一条 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER` 已由 Task 75 结清并删除；
        计数**从 `__all__` 现算**（不写死 4）。
        """
        notes = {
            P.UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY,
            P.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE,
            P.UPSTREAM_DEBT_DISPOSAL_METHOD_ENUM_DOMAIN_SPLIT,
        }
        exported = [n for n in (P.__all__ or ()) if n.startswith("UPSTREAM_DEBT_")]
        assert len(notes) == len(exported), sorted(exported)
        for note in notes:
            assert note.startswith("Task 42 欠账"), note[:40]
            assert "owner" in note, note[:40]


# ═══════════════════════════════════════════════════════════════════════════
# 12. 本任务修掉的三条真实缺陷：反向自检（故意退回旧行为必失败）
# ═══════════════════════════════════════════════════════════════════════════


def _workbook_rels(data: bytes) -> str:
    return _read_entries(data)["xl/_rels/workbook.xml.rels"].decode("utf-8")


class TestUpstreamRelsAndNamespaceDefectsAreFixed:
    """**Validates: Requirements 6.16 / 9.9**

    本任务在真实数据上撞出三条**生产缺陷**，全部已修。三条同源：`backend/wp_templates/`
    下 369 个工作簿里有 **10 个**由一个非 Excel 工具写出（含 Task 40 的
    `B60-1 审计项目工时预算与控制表.xlsx` 与 Task 43 的 `G7 长期股权投资.xlsx`），
    它们同时具备三个非典型形态。缺陷此前潜伏：Task 40 的守卫根本不调
    `instrument_workbook_bytes`，Task 41 的 D2 模板恰好三条都不命中。

    每条都带「故意退回旧行为必失败」的反向自检 —— 否则这一组就只是在断言现状。
    """

    def test_authoritative_template_writes_target_before_id(self) -> None:
        """缺陷 ① 的前提事实：本模板的 rels 是 `Type` → `Target` → `Id` 顺序。"""
        rels = _workbook_rels(P.read_authoritative_template())
        assert re.search(r'Target="[^"]+"[^>]*Id="[^"]+"', rels), rels[:200]
        assert not re.search(r'Id="[^"]+"[^>]*Target="[^"]+"', rels)

    def test_ten_of_the_authoritative_workbooks_share_this_shape(self) -> None:
        """影响面实测：369 个工作簿里 10 个是这种顺序，且含 B60 与 G7。"""
        root = P.authoritative_template_path().parent.parent
        target_first: list[str] = []
        total = 0
        for path in sorted(root.rglob("*.xls*")):
            if path.name.startswith("~$"):
                continue
            total += 1
            try:
                with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as zf:
                    if "xl/_rels/workbook.xml.rels" not in zf.namelist():
                        continue
                    rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
            except zipfile.BadZipFile:
                continue
            if re.search(r'Target="[^"]+"[^>]*Id="[^"]+"', rels) and not re.search(
                r'Id="[^"]+"[^>]*Target="[^"]+"', rels
            ):
                target_first.append(path.name)
        assert total == EXPECTED_TOTAL_WORKBOOKS, total
        assert len(target_first) == EXPECTED_LEGACY_WRITER_WORKBOOKS, target_first
        assert P.authoritative_template_path().name in target_first
        assert "B60-1 审计项目工时预算与控制表.xlsx" in target_first
        assert "G7 长期股权投资.xlsx" in target_first

    def test_sheet_part_resolution_is_attribute_order_independent(self) -> None:
        """缺陷 ① 已修：顺序无关地解析 sheet part。"""
        assert (
            EI._sheet_part_for(
                '<workbook><sheets><sheet name="s" r:id="rId7"/></sheets></workbook>',
                '<Relationships><Relationship Type="t" Target="/xl/worksheets/sheet7.xml" '
                'Id="rId7"/></Relationships>',
                "s",
            )
            == "xl/worksheets/sheet7.xml"
        )
        assert (
            EI._sheet_part_for(
                '<workbook><sheets><sheet name="s" r:id="rId7"/></sheets></workbook>',
                '<Relationships><Relationship Id="rId7" Type="t" '
                'Target="worksheets/sheet7.xml"/></Relationships>',
                "s",
            )
            == "xl/worksheets/sheet7.xml"
        )

    def test_old_id_before_target_regex_would_have_failed(self) -> None:
        """缺陷 ① 的反向自检：旧正则在本模板的 rels 上**确实**匹配不到。"""
        rels = _workbook_rels(P.read_authoritative_template())
        workbook = _read_entries(P.read_authoritative_template())[
            "xl/workbook.xml"
        ].decode("utf-8")
        rid = re.search(
            r'<sheet [^>]*name="' + re.escape(P.MANAGED_SHEET) + r'"[^>]*r:id="(rId\d+)"',
            workbook,
        )
        assert rid, "受管 sheet 的 r:id 取不到"
        assert re.search(r'Id="' + rid.group(1) + r'"[^>]*Target="([^"]+)"', rels) is None
        # 而修好的实现能解析出来。
        assert EI._sheet_part_for(workbook, rels, P.MANAGED_SHEET).startswith(
            "xl/worksheets/"
        )

    def test_workbook_root_does_not_declare_the_relationship_namespace(self) -> None:
        """缺陷 ② 的前提事实：根元素没有 `xmlns:r`，声明写在每个 `<sheet>` 上。"""
        workbook = _read_entries(P.read_authoritative_template())[
            "xl/workbook.xml"
        ].decode("utf-8")
        root = workbook[: workbook.find(">", workbook.find("<workbook")) + 1]
        assert 'xmlns:r="' not in root, root[:200]
        assert workbook.count('<sheet xmlns:r="') == EXPECTED_SHEET_COUNT

    def test_instrumented_workbook_and_sheet_xml_are_well_formed(
        self, instrumented: EI.InstrumentedWorkbook, sheet_part: str
    ) -> None:
        """缺陷 ② 已修：注入后 workbook.xml 与受管 sheet 都能被 ElementTree 解析。

        这条是那条缺陷唯一的可见形态 —— 未绑定前缀让 `ET.fromstring` 抛
        `unbound prefix`，`identity_inventory` / `structure_fingerprint` 全线不可用。
        """
        import xml.etree.ElementTree as ET

        entries = _read_entries(instrumented.instrumented_bytes)
        ET.fromstring(entries["xl/workbook.xml"])
        ET.fromstring(entries[sheet_part])
        assert '<sheet xmlns:r="' in entries["xl/workbook.xml"].decode("utf-8")
        assert '<tableParts xmlns:r="' in entries[sheet_part].decode("utf-8")

    def test_namespace_is_not_added_when_the_root_already_declares_it(self) -> None:
        """缺陷 ② 的反向自检：根元素已声明时**不得**再加。

        无条件加会改动另外 358 个工作簿的注入字节，从而改掉 Task 40/41 已冻结的
        structure hash —— 这条判据把「只在缺失时补」钉住。
        """
        declared = (
            '<worksheet xmlns:r="http://x"><sheetData/></worksheet>'
        )
        assert EI._attach_table_part(declared).count("xmlns:r=") == 1
        missing = "<worksheet><sheetData/></worksheet>"
        attached = EI._attach_table_part(missing)
        assert attached.count("xmlns:r=") == 1
        assert "<tableParts xmlns:r=" in attached

    def test_inline_strings_use_numeric_character_references(self, sheet_part: str) -> None:
        """缺陷 ③ 的前提事实：本工作簿把非 ASCII 内联文本写成数字字符引用。"""
        xml = _read_entries(P.read_authoritative_template())[sheet_part].decode("utf-8")
        encoded = "".join(f"&#{ord(char)};" for char in P.FOOTER_MARKER)
        assert encoded in xml, encoded
        assert f"<t>{P.FOOTER_MARKER}</t>" not in xml

    def test_numeric_character_references_are_decoded(self) -> None:
        """缺陷 ③ 已修：十进制/十六进制两种形态都还原，非法码位原样保留。"""
        assert M._xml_unescape("&#21512;&#35745;") == P.FOOTER_MARKER
        assert M._xml_unescape("&#x5408;&#x8BA1;") == P.FOOTER_MARKER
        # 既有具名实体行为**逐字未变**（新增的那一趟不得踩到它们）。
        assert M._xml_unescape("&lt;a&gt;&quot;&amp;&apos;") == "<a>\"&'"
        # `&amp;#39;` 的 `#` 前面是 `;` 而不是 `&` ⇒ 数字那趟匹配不上，随后具名那趟把它
        # 还原成字面 `&#39;`（不会被误解码成 `'`）。
        assert M._xml_unescape("&amp;#39;") == "&#39;"
        # 非法码位原样保留（静默丢字符比留下引用更难查）。
        assert M._xml_unescape("&#0;") == "&#0;"
        assert M._xml_unescape("&#1114112;") == "&#1114112;"
        assert M._decode_numeric_char_refs("no refs here") == "no refs here"

    def test_footer_marker_is_found_through_the_decoder(
        self, base_bytes: bytes, base_outcome: X.ExcelExtractOutcome, contract: Any
    ) -> None:
        """缺陷 ③ 的反向自检：解码器是 footer 定位的**必经之路**。

        故意把解码器退回「只还原具名实体」⇒ `assert_footer_anchor_stable` 必须打红。
        """
        entries = _read_entries(base_bytes)
        part = base_outcome.region.sheet_part
        runtime = {"GT_FOOTER_ROW": str(P.FOOTER_ROW)}
        assert (
            M.assert_footer_anchor_stable(
                entries=entries, sheet_part=part, contract=contract,
                runtime_binding=runtime,
            )
            == P.FOOTER_ROW
        )
        original = M._decode_numeric_char_refs
        try:
            M._decode_numeric_char_refs = lambda text: text  # type: ignore[assignment]
            with pytest.raises(M.FooterAnchorDriftError, match="一处都找不到"):
                M.assert_footer_anchor_stable(
                    entries=entries, sheet_part=part, contract=contract,
                    runtime_binding=runtime,
                )
        finally:
            M._decode_numeric_char_refs = original  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════════════════
# 13. 顺序门与生产接线
# ═══════════════════════════════════════════════════════════════════════════


def _descriptor_facts() -> Any:
    from app.services.workpaper_sync import entry_source_facts as facts

    entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
    return facts.observe_descriptor_facts(entry)


def _room_facts() -> Any:
    from app.services.workpaper_sync import entry_source_facts as facts

    entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
    return facts.observe_room_facts(entry)


class TestOrderingGate:
    """**Validates: Requirements 6.18 / 12.1**"""

    def test_capability_is_not_enabled_before_finalize(self, entry: dict[str, Any]) -> None:
        """顺序门今天必然抛：finalize 被 published-identity-observer 缺口挡住。"""
        assert capability_of(entry) is Capability.single_onlyoffice
        assert entry["adapter_id"] is None
        with pytest.raises(P.PilotSelectionError, match="manifest capability"):
            P.assert_manifest_capability_enabled()

    def test_capability_predicate_agrees_with_the_ordering_gate(
        self, manifest: dict[str, Any]
    ) -> None:
        """`manifest_capability_enabled` 委派给顺序门，只把异常翻成布尔。"""
        assert P.manifest_capability_enabled() is False
        # 🔴 AST 判据而不是词面：docstring 里刻意写着「宽 `except Exception` 会…」这段
        #    **说明**，纯字符串判据会把说明本身判成违规（首轮实测的假红）。
        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        node = next(
            item
            for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "manifest_capability_enabled"
        )
        called = {
            sub.func.id
            for sub in ast.walk(node)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
        }
        assert called == {"assert_manifest_capability_enabled"}, called
        handlers = [sub for sub in ast.walk(node) if isinstance(sub, ast.ExceptHandler)]
        assert len(handlers) == 1, len(handlers)
        assert isinstance(handlers[0].type, ast.Name)
        assert handlers[0].type.id == "PilotSelectionError", handlers[0].type.id
        # 整个模块里一个宽 except 都没有（同样用 AST 数，不看注释）。
        wide = [
            sub
            for sub in ast.walk(tree)
            if isinstance(sub, ast.ExceptHandler)
            and (
                sub.type is None
                or (isinstance(sub.type, ast.Name) and sub.type.id in {"Exception", "BaseException"})
            )
        ]
        assert wide == [], [ast.dump(item)[:80] for item in wide]
        # 反向自检：manifest 一旦裁决为 bidirectional + 正确 adapter_id ⇒ 谓词为真。
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["capability"] = "bidirectional"
                item["adapter_id"] = P.PILOT_ADAPTER_ID
        assert P.manifest_capability_enabled(manifest=patched) is True
        P.assert_manifest_capability_enabled(manifest=patched)
        # adapter_id 不符仍为假（两个字段都进判据）。
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["adapter_id"] = "b60.hour_budget"
        assert P.manifest_capability_enabled(manifest=patched) is False

    def test_attach_is_a_no_op_before_enablement_and_never_raises(self) -> None:
        """未启用时返回空元组、**一次库都不读**（session 传 None 也不炸）。

        🔴 Task 41 实测过 raise 的后果：它一抛就让 `_registration` /
        `_apply_durable_incoming` 对**所有** entry 都 500 —— 一个尚未启用的 pilot 把整条
        sync 路由拖下水（Task 28 的路由守卫 8 例打红）。
        """
        import asyncio

        from app.services.workpaper_sync.adapters.registry import (
            WorkpaperSyncAdapterRegistry,
        )

        registry = WorkpaperSyncAdapterRegistry()
        assert asyncio.run(P.attach_pilot_adapters(registry, session=None)) == ()
        assert registry.registrations() == ()

    def test_ledger_records_adapter_not_registered_yet(self) -> None:
        row = next(
            row
            for row in RG.DELIVERED_PER_ENTRY_CONTRACTS
            if row["contract_id"] == P.PILOT_ADAPTER_ID
        )
        assert row["adapter_registered"] is False
        assert "顺序" in row["reason"]
        assert "Task 75" in row["reason"], (
            "reason 仍指向已删除的欠账常量 ⇒ 登记表与现实脱钩"
        )
        assert "Task 76" in row["reason"], (
            "reason 没说清今天挡住注册的是供给（approved bundle / published representation 两表 0 行）"
        )

    def test_contract_orphan_is_visible_in_the_registry_report(self) -> None:
        """契约孤儿必须是**可见欠账**，不是静默缺失。"""
        from app.services.workpaper_sync.adapters.registry import (
            WorkpaperSyncAdapterRegistry,
        )

        report = WorkpaperSyncAdapterRegistry().build_report(
            contract_ids=available_contract_ids()
        )
        assert P.PILOT_ADAPTER_ID in report.contract_files_without_adapter
        assert report.registered_adapter_ids == ()
        # Task 40/41 的两个契约同样是可见孤儿（顺序未过就该如此）。
        assert {"b60.hour_budget", "d2.receivable_detail"} <= set(
            report.contract_files_without_adapter
        )

    def test_registration_is_refused_while_manifest_says_single_onlyoffice(self) -> None:
        """伪双向必须被 registry 拒（这条不能靠本模块"填对"）。"""
        from app.services.workpaper_sync.adapters.registry import (
            FakeBidirectionalError,
            WorkpaperSyncAdapterRegistry,
        )

        registry = WorkpaperSyncAdapterRegistry()
        descriptor = _descriptor_facts()
        assert descriptor is not None
        with pytest.raises((FakeBidirectionalError, RG.RegistryError)):
            P.register_pilot_adapter(
                registry,
                adapter=object(),
                bundle=None,
                descriptor=descriptor,
                room=_room_facts(),
            )


class TestProductionWiring:
    """**Validates: Requirements 12.1**"""

    def test_router_calls_the_h1_attach_on_both_paths(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        assert source.count("pilot_h1_grouped_dynamic import") == 2, source.count(
            "pilot_h1_grouped_dynamic import"
        )
        assert source.count("attach_h1_pilot_adapters") == 4, source.count(
            "attach_h1_pilot_adapters"
        )
        assert "await attach_h1_pilot_adapters(svc.registry, session=svc.session)" in source
        assert "await attach_h1_pilot_adapters(registry, session=db)" in source

    def test_router_still_calls_the_other_two_pilot_attaches(self) -> None:
        """只加不动：Task 40/41 的两条接线一条都不许掉。"""
        source = _ROUTER.read_text(encoding="utf-8")
        assert source.count("pilot_simple_checklist import attach_pilot_adapters") == 2
        assert source.count("pilot_d2_large_json import") == 2
        assert source.count("attach_d2_pilot_adapters") == 4
        assert "await attach_pilot_adapters(svc.registry, session=svc.session)" in source
        assert "await attach_pilot_adapters(registry, session=db)" in source

    def test_both_production_paths_go_through_the_bidirectional_contract_lock(self) -> None:
        """AST 判据：两个生产入口都调 `assert_contract_file_matches_source`，都不直接 load。

        🔴 Task 40 首轮把「守卫自己调锁」当成通过 ⇒ 整组变异判 GREEN。判据必须落在
        **生产函数体**上。
        """
        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        checked = 0
        for name in ("publish_pilot_definitions", "attach_pilot_adapters"):
            node = next(
                item
                for item in tree.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == name
            )
            calls = {
                sub.func.id
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            }
            assert "assert_contract_file_matches_source" in calls, name
            assert "load_pilot_contract" not in calls, name
            checked += 1
        assert checked == 2

    def test_generator_is_the_only_writer_of_the_disk_contract(self) -> None:
        """磁盘契约只由生成器写；生产模块里没有任何写盘。

        🔴 AST 判据而不是词面：两个文件的 docstring 里都刻意写着「用 `write_bytes` 而不是
        `write_text`」这段**说明**，纯字符串判据会把说明本身判成违规（首轮实测的假红）。
        """
        writers = ("write_bytes", "write_text", "mkdir", "unlink", "dump", "dumps")

        def attribute_calls(path: Path) -> set[str]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            return {
                node.func.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            }

        produced = attribute_calls(Path(P.__file__))
        assert not (produced & set(writers)), sorted(produced & set(writers))
        generator_path = (
            _BACKEND / "scripts" / "gen" / "generate_pilot_h1_grouped_dynamic_contract.py"
        )
        generated = attribute_calls(generator_path)
        assert "write_bytes" in generated
        assert "write_text" not in generated, "write_text 会把 LF 腌成 CRLF"

    def test_disk_contract_is_lf_and_byte_stable(self) -> None:
        blob = P.contract_file_path().read_bytes()
        assert b"\r\n" not in blob
        assert blob.endswith(b"\n")
        # 🔴 24931 → 25272：BP-21（受管区收缩 + 物理末行常量）与 Open Gate 5
        #    （`footer_anchor.carries_total_formula` + note）各改了契约 payload。
        assert len(blob) == 25272, len(blob)


class TestPilotIntroducesNoResolverDebt:
    """**Validates: Requirements 12.1**

    本模块**不得**给 Task 20 的收口门增加 writer/resolver 欠账：`find_template_file*` 是
    Task 19 清册登记的 non-canonical resolver 符号，出现在 `backend/app/` 里就会各增一条。
    """

    def test_module_never_calls_a_non_canonical_resolver(self) -> None:
        """AST 判据：既不 import、也不调用 `wp_template_finder` 的任何符号。

        🔴 不能写词面判据：docstring 里刻意逐条写着这三个函数名与实测结果（选型推导的
        依据），纯字符串判据会把说明本身判成违规（首轮实测的假红）。
        """
        forbidden = {
            "find_template_file",
            "find_template_file_any",
            "find_all_template_files",
        }
        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        assert not (imported & forbidden), sorted(imported & forbidden)
        assert not [name for name in modules if "wp_template_finder" in name], sorted(
            modules
        )
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        } | {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not (called & forbidden), sorted(called & forbidden)

    def test_no_function_in_this_module_is_classified_as_writer_or_resolver(self) -> None:
        """真实清册（Task 20 收口门消费的那份产物）里本模块贡献 **0** 行。

        🔴 判据落在**已生成的产物**上而不是重跑生成器：那份 JSON 的
        `source_digest`/`inventory_digest` 由 `--check` 与 Task 30 的收口门共同守着新鲜度，
        所以「产物里没有我」等价于「分类器不认为我是 writer/resolver」，而且顺带证明我没有
        让清册过期。
        """
        payload = json.loads(
            (_BACKEND / "data" / "workpaper_writer_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        entries = payload["entries"]
        # Task 74 detector fix: _record_ad_hoc_path now resolves module-level path
        # constants, so eight resolvers the d1262c80 file split had hidden are back in
        # the denominator (319 -> 327). Widening, not narrowing -- all eight are adjudicated.
        assert len(entries) == 327, len(entries)
        mine = [
            row
            for row in entries
            if "pilot_h1_grouped_dynamic" in str(row.get("module") or "")
            or "pilot_h1_grouped_dynamic" in str(row.get("source_path") or "")
        ]
        assert mine == [], [row["writer_id"] for row in mine]
        # 另外两个 pilot 也一样是 0 行（证明这条判据不是"本模块恰好没被扫到"）。
        for other in ("pilot_simple_checklist", "pilot_d2_large_json"):
            assert not [
                row for row in entries if other in str(row.get("module") or "")
            ], other
