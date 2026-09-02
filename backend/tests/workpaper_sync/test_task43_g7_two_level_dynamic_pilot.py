"""Task 43 离线守卫：G7 两级动态表 pilot 的选型、两级表头、动态列绑定与四边真源。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 43
Requirements: 6.3, 6.4, 6.10, 6.16, 12.1, 12.2, 12.10, 14.1
Properties: **P22 / P28 / P49 / P66 / P69**

═══ 这一半证的是「判据本身正确 + 契约真有来源 + 四边真源真的在比 + 漂移真的 fail closed」═══

`test_task43_g7_two_level_dynamic_pilot_pg.py` 在真库上跑完整 run（发布四个 definition、
组 non-null bundle、逐场景 record、finalize），并冻结「真实库里 `G7-main-disclosure-soe-v2`
今天不存在」这一事实。本文件不连库，只证八件事：

1. **冻结的 entry 不是拍脑袋挑的**：三条必要条件在真实 manifest / 真实
   `wp_template_finder` / 真实 `_index.json` / 两份真实渲染 schema 上重新推导一遍。
   🔴 第 2 条与 Task 40/41/42 **都不同**：本类有 **3 个**候选，收敛到一个的决定性事实是
   **matcher 域独占**（另外两个共用 `G7E`，以它作 `EntryMatcher.wp_codes` 会触发 RG-3）。
2. **107 个字段逐个有来源**：`source_ref` / `header_source_ref` / `group_source_ref` /
   `row_label_source_ref` 指向的单元格，用 openpyxl 直读权威模板取出**真实文本/公式/空值**
   再比对。
3. **两级表头真的是两级**：行 62 的 5 个**空白**横向合并（源自己的动态列占位）+ 行 63 的
   10 个叶子逐格 merge/文本实测；并且 **10 列只有 2 个不同 label、各重复 5 次**而 100 个
   stable key 互不相同（Property 22 的真实、非合成 oracle）。
4. **动态列 `{slot}_{seq}` 的实测绑定真的在跑**：本 pilot 是四类里唯一有动态列的，
   `dynamic_column_binding_for()` 的 10 个键逐个喂进真实 extract；缺绑定 / 键形态错 /
   两键撞一列三种形态各自 fail closed。
5. **四边真源各自有独立比对**：源 xlsx（openpyxl）/ seed（`g7_column_source_facts.json`）/
   运行时（真实 extract）/ **渲染层**（`.vue` 模板形态三要素 + `.ts` 键规则）。
   🔴 第四边不是 grep 符号名：它解包装链、要求「遍历 + 外层门控 + 内层嵌套」落在**同一个
   循环变量**上，缺一即红 —— 归档 spec 的 0/38 张就是只比数据层漏掉的。
6. **Property 28 的漂移 fail closed 真的在真实契约上跑**：改 template digest / 改
   instrumentation digest / 改 bundle contract slot / 改结构清册四种漂移，各自打出**不同**
   的异常类型。
7. **插删重排复制跑在真实模板上**：真实权威模板 → 真实注入产物 → 真实 extract，identity
   保留 / 公式范围 / 未管理区域结论逐项断言。
8. **登记的五条欠账都是可打红的实测事实**，且各带「上游修好即抛错」的反向自检。

═══ 反假绿 ═══

* 覆盖计数硬判据：107 字段 / 100 editable / 7 protected / 100 次叶子表头比对 /
  100 次组标题比对 / 100 次 metric 标签比对 / 100 格「源侧全空」逐格实测 /
  30 格公式逐格比对 / 10 个动态列键 / 5 个源侧占位槽 / 8 个未管理 aspect 里 7 个 > 0
  （第 8 个为 0 且有专门事实判据）。
* 双向锁：磁盘契约 ↔ 现算 payload（改任一侧都打红）。
* 分型可达：`StorePayloadError` 的六个分支各真触发一次，且与 `PilotSelectionError` /
  `RenderLayerError` 互不相同（共用错误码会让较早分支永久不可达 —— 本 spec 已实测 3 次）。
* 期望值一律从**源侧**推导或写字面量，绝不用被测函数算期望。
* 不借用 Task 40/41/42 的 definition identity：authority model / bundle digest / contract /
  required-set digest 四项各自与它们比对**不相等**。
"""
from __future__ import annotations

import ast
import hashlib
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
from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P  # noqa: E402
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
    declared_structure_inventory,
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
    DynamicColumnIdentityError,
    FrozenEntryDefinitions,
    assert_dynamic_columns_label_independent,
    dynamic_column_stable_keys,
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
#    `_sheet_part_of` **不能**复用：它带着 Task 42 已修掉的「rels 里 Id 必须排在 Target
#    之前」那条假设，而本任务的权威模板恰恰是 `Type` → `Target` → `Id` 顺序。
from test_task37_excel_extract import (  # noqa: E402
    _read_entries,
    _write_entries,
    patch_cells,
)

_MANIFEST_PATH = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"
_ROUTER = _BACKEND / "app" / "routers" / "wp_sync_router.py"

#: 107 = 矩阵 10 metric × 10 动态列 + 记录表 7 列。
EXPECTED_FIELD_COUNT = 107
#: 100 = 矩阵全部（源侧逐格实测全空 ⇒ editable）。
EXPECTED_EDITABLE_COUNT = 100
#: 7 = 记录表 1 个 auto_source（A 序号字面量）+ 6 个 formula（B..G 跨 sheet 公式）。
EXPECTED_PROTECTED_COUNT = 7
#: 权威模板的 sheet 数（openpyxl 实测）。
EXPECTED_SHEET_COUNT = 22
#: 受管 sheet 的 merge 总数（openpyxl 实测）。
EXPECTED_MERGE_COUNT = 187
#: 源侧动态列占位槽数（行 62 的 5 个**空白**横向合并）。
EXPECTED_TEMPLATE_SLOT_COUNT = 5
#: 动态列总数 = 5 槽 × 2 子列。
EXPECTED_DYNAMIC_COLUMN_COUNT = 10
#: 记录表公式格数（6 列 × 5 行，逐格实测）。
EXPECTED_RECORD_FORMULA_CELLS = 30
#: `g7_column_source_facts.json` 的三个计数（归档 spec 的成果，本任务现推复核）。
EXPECTED_FACTS_TABLE_COUNT = 38
EXPECTED_FACTS_TWO_LEVEL = 24
EXPECTED_FACTS_EXEMPT = 4
EXPECTED_FACTS_TWO_LEVEL_RENDERED = 20
#: 同类候选数（`assess_pilot_classes()` 实测）。
EXPECTED_G7_CANDIDATES = 3

FIRST = P.RECORD_FIRST_ROW
LAST = P.RECORD_LAST_ROW
#: 记录表的六个公式列（`A` 是 auto_source 字面量）。
RECORD_FORMULA_COLUMNS = tuple(
    column for _key, column, mode, *_rest in P.RECORD_COLUMNS if mode == "formula"
)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def uid(row: int) -> str:
    """instrumentation 预生成的行 UUID 字面量（与 `spec.row_uuid` 同形态）。"""
    return f"GTROW-{P.TEMPLATE_ID}-{row:04d}"


def _non_docstring_literals(path: Path) -> list[str]:
    """模块里的**非 docstring** 字符串字面量。

    docstring 必须剥掉：本任务的生产模块 docstring 里刻意写着「参考副本一次都不读」
    「不借用 B60/D2/H1 的 identity」这类**说明**，纯字面量判据会把说明本身判成违规。
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


def function_body_code(path: Path, name: str) -> str:
    """某个函数的**可执行体**源码（剥掉 docstring 与注释）。

    🔴 必须剥：本任务的生产函数 docstring 里刻意写着「不写死 5，也不写死 10」「在这里重写
    一遍 ``f"{slot}_{seq}"`` 的后果……」这类**说明**，纯字面量/正则判据会把说明本身判成
    违规（首轮实测就是这么打红的两条）。`ast.unparse` 只输出语句，注释与 docstring 天然
    不在其中。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            body = list(node.body)
            first = body[0] if body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                body = body[1:]
            assert body, f"{name} 的函数体只有 docstring"
            return "\n".join(ast.unparse(stmt) for stmt in body)
    raise AssertionError(f"{path.name} 里找不到函数 {name}")


def observe_template_resolution() -> Any:
    """借用契约生成器里的**同一个**观测器（不抄第二份）。

    观测器住在 `backend/scripts/gen/` 而不是 `backend/app/`：`find_template_file*` 是
    Task 19 清册登记的 non-canonical resolver 符号，生产模块里出现它们会给收口门增债
    （见 `P.TemplateResolutionFacts` 的 docstring）。
    """
    import importlib.util

    path = _BACKEND / "scripts" / "gen" / "generate_pilot_g7_two_level_dynamic_contract.py"
    spec = importlib.util.spec_from_file_location("_t43_contract_gen", path)
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
    实测是 `Type` → `Target` → `Id` 顺序（生产侧 `excel_instrumentation._sheet_part_for`
    的同一条缺陷已由 Task 42 修掉，本文件的
    `TestUpstreamRelsAndNamespaceShapesStillHold` 对它做反向自检）。
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
    """把 Excel Table 的 ref 行区间扩到 `last_row`（模拟 OO 插行）。"""
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


def uuid_cell_occurrences(data: bytes, part: str) -> dict[str, int]:
    """UUID 列每个坐标在 sheet XML 里出现几次（正常必须恰 1 次）。

    🔴 这条 helper 存在的理由是**本任务修掉的第 4 条生产缺陷**：
    `_add_uuid_cells` 原来无条件在 `</row>` 前追加，而本 sheet 的 `N79..N83` 在模板里已有
    「有样式、无值」的格 ⇒ 同一行出现两个相同 `r` 的 `<c>`（非法 OOXML）。首轮实测时
    `patch_cells` 因此改到了**前一个**（模板那一个），三条结构操作 fixture 静默失效。
    """
    xml = _read_entries(data)[part].decode("utf-8")
    return {
        f"{P.UUID_COL}{row}": len(
            re.findall(rf'<c r="{P.UUID_COL}{row}"(?:\s|/|>)', xml)
        )
        for row in range(FIRST, LAST + 2)
    }


def assert_uuid_cells_are_unique(data: bytes, part: str) -> None:
    counts = uuid_cell_occurrences(data, part)
    duplicated = {coord: n for coord, n in counts.items() if n > 1}
    assert not duplicated, f"UUID 格重复出现 {duplicated} —— 非法 OOXML，fixture 会改错格"


def fill_record_formula_cache(data: bytes, part: str) -> bytes:
    """给记录表六个公式列补缓存值 `<v>`（并按列的 `value_type` 给对的载体）。

    🔴 为什么必须补：权威模板里公式格是 ``<f>…</f><v></v>`` —— **缓存值是空的**（模板从未
    被计算过）。`excel_extract` 按 Task 14 语义把读到 `None` 的格当 MISSING
    （`if not present: continue`），于是公式字段既不进 projection、也不进
    `formula_inventory`。真实 OO 往返回来的工作簿一定带缓存值，所以 fixture 必须补上，
    否则「公式范围」判据会在一个恒空的集合上通过（假绿第⑤源）。

    🔴 文本列必须补 `t="str"`：源格没有 `t` 属性（数值型），直接塞文本会让 openpyxl 在
    `_cast_number` 抛 `ValueError`（实测踩过一次）。模板自身那个「缓存值为空」的事实由
    `TestAuthoritativeTemplate::test_record_formula_cells_ship_without_cached_values`
    单独钉住。
    """
    numeric_columns = {
        column
        for _key, column, mode, value_type, *_rest in P.RECORD_COLUMNS
        if mode == "formula" and value_type != "text"
    }
    entries = _read_entries(data)
    xml = entries[part].decode("utf-8")
    filled = 0
    for column in RECORD_FORMULA_COLUMNS:
        numeric = column in numeric_columns
        for row in range(FIRST, LAST + 1):
            pattern = re.compile(
                r'<c r="' + column + str(row) + r'"([^>]*)>(<f>[^<]*</f>)<v></v>'
            )

            def repl(match: re.Match[str], _col: str = column, _row: int = row,
                     _numeric: bool = numeric) -> str:
                attrs = match.group(1)
                if _numeric:
                    return f'<c r="{_col}{_row}"{attrs}>{match.group(2)}<v>{_row}</v>'
                if 't="' not in attrs:
                    attrs = f'{attrs} t="str"'
                return f'<c r="{_col}{_row}"{attrs}>{match.group(2)}<v>V{_col}{_row}</v>'

            xml, count = pattern.subn(repl, xml, count=1)
            filled += count
    assert filled == EXPECTED_RECORD_FORMULA_CELLS, (
        f"只补了 {filled} 个公式缓存值（期望 {EXPECTED_RECORD_FORMULA_CELLS}）—— "
        "模板的公式格形态已变，公式范围判据会退化成空集"
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
def merges(worksheet: Any) -> frozenset[str]:
    return frozenset(str(item) for item in worksheet.merged_cells.ranges)


@pytest.fixture(scope="module")
def contract() -> Any:
    return P.load_pilot_contract()


@pytest.fixture(scope="module")
def contract_payload() -> dict[str, Any]:
    """磁盘契约的**原始 JSON**（`SyncContract` 丢掉了 header/group source_ref 等扩展键）。"""
    return json.loads(P.contract_file_path().read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix_fields(contract_payload: dict[str, Any]) -> list[dict[str, Any]]:
    table = next(
        t
        for t in contract_payload["sheets"][0]["tables"]
        if t["table_key"] == P.MATRIX_TABLE_KEY
    )
    return list(table["fields"])


@pytest.fixture(scope="module")
def record_fields(contract_payload: dict[str, Any]) -> list[dict[str, Any]]:
    table = next(
        t
        for t in contract_payload["sheets"][0]["tables"]
        if t["table_key"] == P.RECORD_TABLE_KEY
    )
    return list(table["fields"])


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
    """把 100 个矩阵 editable 格逐格写满，并补上记录表六个公式列的缓存值。"""
    cells: dict[str, Any] = {}
    for metric_key, _label in P.MATRIX_METRICS:
        row = P.metric_row_for(metric_key)
        for seq in range(1, EXPECTED_DYNAMIC_COLUMN_COUNT + 1):
            cells[f"{P.matrix_column_letter_for_seq(seq)}{row}"] = 1000 + row * 10 + seq
    assert len(cells) == EXPECTED_EDITABLE_COUNT, len(cells)
    return fill_record_formula_cache(
        patch_cells(instrumented.instrumented_bytes, sheet_part, cells), sheet_part
    )


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("task43")


@pytest.fixture(scope="module")
def base_path(base_bytes: bytes, workdir: Path) -> Path:
    path = workdir / "base.xlsx"
    path.write_bytes(base_bytes)
    return path


def make_binding(**over: Any) -> X.ExcelIdentityBinding:
    kwargs: dict[str, Any] = {
        "table_name": P.TABLE_NAME,
        "uuid_column": P.UUID_COL,
        "table_key": P.RECORD_TABLE_KEY,
        "dynamic_column_columns": {
            P.MATRIX_TABLE_KEY: P.dynamic_column_binding_for(P.RENDER_SLOT_DEFAULT_NAMES)
        },
    }
    kwargs.update(over)
    return X.ExcelIdentityBinding(**kwargs)


@pytest.fixture(scope="module")
def binding() -> X.ExcelIdentityBinding:
    return make_binding()


def make_bundle(contract: Any, **over: Any) -> DefinitionBundleSnapshot:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    slots = {
        BundleSlot.template: slot(BundleSlot.template, contract.template_definition_sha256),
        BundleSlot.instrumentation: slot(
            BundleSlot.instrumentation, contract.instrumentation_definition_sha256
        ),
        BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
    }
    slots.update(over.pop("slots", {}))
    kwargs: dict[str, Any] = {
        "bundle_id": uuid.uuid4(),
        "bundle_sha256": _d("g7-bundle"),
        "schema_version": "definition-bundle:v1",
        "state": DefinitionState.approved,
        "authority_model": AuthorityModel.projection_contract,
        "authority_model_definition_id": uuid.uuid4(),
        "authority_model_definition_sha256": _d("g7-authority"),
        "slots": slots,
    }
    kwargs.update(over)
    return DefinitionBundleSnapshot(**kwargs)


def make_definitions(
    contract: Any,
    inventory_bytes: bytes,
    *,
    drop_identity: str | None = None,
    bundle: DefinitionBundleSnapshot | None = None,
    entity_names: tuple[str, ...] = P.RENDER_SLOT_DEFAULT_NAMES,
) -> FrozenEntryDefinitions:
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
        bundle=bundle if bundle is not None else make_bundle(contract),
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=P.PILOT_ADAPTER_ID,
            adapter_build_digest=_d("g7-adapter-build"),
            document_type="xlsx",
            contract_version="1.0.0",
        ),
        identity_inventory=parse_identity_inventory(raw),
        business_sheets=(),
        dynamic_column_keys={
            P.MATRIX_TABLE_KEY: P.dynamic_column_keys_for_entities(entity_names)
        },
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


def store_state(
    *,
    entity_names: tuple[str, ...] = P.RENDER_SLOT_DEFAULT_NAMES,
    metrics: tuple[tuple[str, str], ...] = P.MATRIX_METRICS,
    version: int = P.STORE_STATE_VERSION,
) -> dict[str, Any]:
    """按**真实 store 形态**造 state（键集合逐个来自契约常量）。

    🔴 用合成载荷而不是真实载荷是**实测结论**而非偷懒：`G7-main-disclosure-soe-v2` 这一条
    item 在参考库里**不存在**，由 `test_task43_g7_two_level_dynamic_pilot_pg.py` 从库里
    重新观测并冻结。所有键取自 :data:`P.MATRIX_METRICS` / :func:`P.render_column_key_for_seq`。
    """
    width = len(P.RENDER_SUB_COLUMNS)
    rows = []
    for index, (metric_key, label) in enumerate(metrics):
        values: dict[str, Any] = {}
        for seq in range(1, len(entity_names) * width + 1):
            values[P.render_column_key_for_seq(seq)] = float(index * 100 + seq)
        rows.append({"id": metric_key, "label": label, "values": values, "kind": "data"})
    return {
        "version": version,
        "tables": {P.RENDER_MATRIX_TABLE_ID: rows},
        "texts": {},
        "entitySlots": {P.RENDER_SLOT: list(entity_names)},
        "previouslySyncedTables": {},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结的 entry：必要条件在真实数据上重新推导
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenEntrySelection:
    """**Validates: Requirements 12.1 / 12.2**

    三条必要条件全部在真实数据上现推。第 2 条是本 spec 的**第四种形态**：本类有 3 个候选，
    三者都是「名字提取产物 + 零回退 + 码族精确唯一」，收敛到一个靠的是**matcher 域独占**。
    """

    def test_entry_is_frozen_from_the_source_backed_manifest(
        self, entry: dict[str, Any]
    ) -> None:
        assert entry["entry_id"] == P.PILOT_ENTRY_ID
        assert entry["document_type"] == "xlsx"
        assert entry["editability"] == "editable"
        assert entry["room_model"] == "shared"

    def test_class_really_has_three_candidates(self, manifest: dict[str, Any]) -> None:
        """三个候选是选型推导的前提；数量一变，matcher 独占性的排除理由就要重做。"""
        assessment = PH.assess_pilot_classes(manifest=manifest)[
            PH.PilotClass.g7_two_level_dynamic
        ]
        assert len(assessment.candidate_entry_ids) == EXPECTED_G7_CANDIDATES, (
            assessment.candidate_entry_ids
        )
        assert set(assessment.candidate_entry_ids) == {P.PILOT_ENTRY_ID} | set(
            P.SIBLING_G7_CANDIDATES
        )
        assert assessment.bidirectional_entry_ids == ()

    def test_entry_is_independent_and_not_a_parent_duplicate(
        self, entry: dict[str, Any]
    ) -> None:
        assert entry["independent_entry"] is True
        assert entry["parent_entry_id"] is None

    def test_matcher_domain_is_exclusive_and_siblings_share_one_code(
        self, manifest: dict[str, Any]
    ) -> None:
        """🔴 决定性事实：`G7L` 独属本 entry，`G7E` 被另外两个共用。"""
        by_code = P.assert_matcher_domain_is_exclusive(manifest=manifest)
        assert by_code["G7L"] == (P.PILOT_ENTRY_ID,)
        assert by_code["G7E"] == tuple(sorted(P.SIBLING_G7_CANDIDATES))
        assert len(by_code["G7E"]) == 2

    def test_a_shared_matcher_domain_really_breaks_registry_rg3(self) -> None:
        """把 `G7E` 当 matcher 会撞 RG-3 —— 用**真实** registry 判据跑一次，不是推理。"""
        shared = RG.EntryMatcher(document_type="xlsx", wp_codes=frozenset({"G7E"}))
        assert shared.overlaps(RG.EntryMatcher(document_type="xlsx", wp_codes=frozenset({"G7E"}))) == (
            "G7E",
        )
        # 本 pilot 的 matcher 与它不重叠（两个 pilot 可以共存）。
        assert P.build_pilot_matcher().overlaps(shared) == ()

    def test_selection_fails_closed_when_the_matcher_domain_is_shared(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        """反向自检：把另一个 entry 的码改成 `G7L` ⇒ 独占性判据必须打红。"""
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == "xlsx/gt-g7-equity-method":
                item["wp_match"]["wp_code_patterns"] = ["G7L"]
        with pytest.raises(P.PilotSelectionError, match="matcher 码"):
            P.assert_matcher_domain_is_exclusive(manifest=patched)
        with pytest.raises(P.PilotSelectionError):
            P.assert_pilot_entry_selectable(resolution=resolution, manifest=patched)

    def test_selection_passes_on_the_real_manifest(self, resolution: Any) -> None:
        """正路径：真实 manifest + 真实 resolver + 真实两份配置下选型必须**通过**。

        🔴 没有这条正路径，所有「短路某个判据 ⇒ 该判据不再拦」的变异都会因为「没有任何
        测试真的调用过 `assert_pilot_entry_selectable(真实数据)`」而判 GREEN
        （首轮实测：M05/M06 就是这么绿的）。
        """
        entry = P.assert_pilot_entry_selectable(resolution=resolution)
        assert entry["entry_id"] == P.PILOT_ENTRY_ID
        assert entry["document_type"] == "xlsx"

    def test_selection_fails_closed_when_the_shared_code_becomes_exclusive(
        self, manifest: dict[str, Any]
    ) -> None:
        """反向自检：`G7E` 不再共用 ⇒ 当初的排除理由失效，必须提醒重做选型。"""
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == "xlsx/gt-g7-equity-subsidiary":
                item["wp_match"]["wp_code_patterns"] = ["G7S"]
        with pytest.raises(P.PilotSelectionError, match="不再是共用码"):
            P.assert_matcher_domain_is_exclusive(manifest=patched)

    def test_selection_fails_closed_when_a_sibling_stops_using_the_shared_code(
        self, manifest: dict[str, Any]
    ) -> None:
        """反向自检：孪生 entry 换了码但**共用码仍被两个 entry 用着** ⇒ 第一条分支必须打红。

        🔴 顺序：这一条与上一条触发的是**不同**分支。上一条让 `owners` 长度掉到 1（第二条
        判据），本条把码转给第三个 entry ⇒ `owners` 仍是 2、但不含那个 sibling（第一条判据）。
        缺了本条，第一条分支对任何输入都不可达 ⇒ 它的变异恒 GREEN（首轮实测的 M05）。
        """
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == "xlsx/gt-g7-equity-method":
                item["wp_match"]["wp_code_patterns"] = ["G7M"]
            elif item["entry_id"] == "xlsx/gt-d2-accounts-receivable":
                item["wp_match"]["wp_code_patterns"] = ["G7E"]
        with pytest.raises(P.PilotSelectionError, match="不再使用"):
            P.assert_matcher_domain_is_exclusive(manifest=patched)

    def test_selection_fails_closed_when_a_sibling_leaves_the_candidate_set(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        """反向自检：孪生 entry 离开 harness 候选集 ⇒ 「三个候选」前提失效必须打红。"""
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == "xlsx/gt-g7-equity-method":
                item["entry_id"] = "xlsx/gt-renamed-equity-method"
        with pytest.raises(P.PilotSelectionError, match="已不在 g7_two_level_dynamic 候选里"):
            P.assert_pilot_entry_selectable(resolution=resolution, manifest=patched)

    def test_wp_code_pattern_is_a_name_extraction_artifact(self, resolution: Any) -> None:
        extracted = P.assert_wp_code_pattern_is_a_name_extraction_artifact(resolution)
        assert "G7L" in extracted
        assert resolution.host_stem == "GtG7LongTermEquityMain"

    def test_name_extraction_judgement_fails_closed_when_the_code_is_real(
        self, resolution: Any
    ) -> None:
        from dataclasses import replace

        with pytest.raises(P.PilotSelectionError, match="真 wp_code"):
            P.assert_wp_code_pattern_is_a_name_extraction_artifact(
                replace(resolution, index_wp_codes=(*resolution.index_wp_codes, "G7L"))
            )

    def test_name_extraction_judgement_fails_closed_on_a_filename_prefix(
        self, resolution: Any
    ) -> None:
        from dataclasses import replace

        with pytest.raises(P.PilotSelectionError, match="前缀回退"):
            P.assert_wp_code_pattern_is_a_name_extraction_artifact(
                replace(
                    resolution, index_filenames=(*resolution.index_filenames, "G7L 某表.xlsx")
                )
            )

    def test_name_extraction_judgement_fails_closed_on_a_different_host(
        self, resolution: Any
    ) -> None:
        from dataclasses import replace

        with pytest.raises(P.PilotSelectionError, match="复现不出"):
            P.assert_wp_code_pattern_is_a_name_extraction_artifact(
                replace(resolution, host_stem="GtSomethingElse")
            )

    def test_no_implicit_template_fallback(self, resolution: Any) -> None:
        """`G7L` 在三个 finder 入口上全空 —— 零回退的最强形态是「根本没有回退」。"""
        assert set(resolution.by_wp_code) == set(P.PILOT_WP_CODES)
        for code, hits in resolution.by_wp_code.items():
            assert list(hits) == [None, None, ()], (code, hits)
        P.assert_no_implicit_template_fallback(resolution, wp_codes=P.PILOT_WP_CODES)

    def test_code_family_is_exactly_unique_in_the_template_index(
        self, resolution: Any
    ) -> None:
        rows = list(resolution.family_index_rows)
        assert len(rows) == 1, rows
        assert "/".join(str(rows[0]["relative_path"]).split("\\")) == P.TEMPLATE_RELATIVE_PATH

    def test_code_family_resolver_lands_on_the_same_workbook(self, resolution: Any) -> None:
        expected = P.authoritative_template_path().resolve()
        assert resolution.family_resolved_paths
        for resolved in resolution.family_resolved_paths:
            assert Path(str(resolved)).resolve() == expected

    def test_fallback_judgement_fails_closed_on_a_non_empty_resolution(
        self, resolution: Any
    ) -> None:
        from dataclasses import replace

        leaked = replace(
            resolution,
            by_wp_code={"G7L": (P.authoritative_template_path(), None, ())},
        )
        with pytest.raises(P.PilotSelectionError, match="解析到了"):
            P.assert_no_implicit_template_fallback(leaked, wp_codes=P.PILOT_WP_CODES)

    def test_fallback_judgement_fails_closed_on_a_non_unique_family_row(
        self, resolution: Any
    ) -> None:
        from dataclasses import replace

        doubled = replace(
            resolution,
            family_index_rows=(*resolution.family_index_rows, *resolution.family_index_rows),
        )
        with pytest.raises(P.PilotSelectionError, match="要求恰 1 条"):
            P.assert_no_implicit_template_fallback(doubled, wp_codes=P.PILOT_WP_CODES)

    def test_both_render_schemas_declare_the_authoritative_template(self) -> None:
        declared = P.render_schema_template_paths()
        assert set(declared) == set(P.RENDER_SCHEMA_RELATIVE_PATHS)
        for relative, value in declared.items():
            assert value == f"backend/wp_templates/{P.TEMPLATE_RELATIVE_PATH}", relative

    def test_render_schema_wp_code_must_stay_inside_the_code_family(self) -> None:
        """`G7-1`（子码形）与 `G7A`（后缀字母形）都必须被接受，别的码族必须被拒。"""
        for good in ("G7", "G7-1", "G7A"):
            paths = P.render_schema_template_paths(
                payloads={
                    relative: {"wp_code": good, "template_path": "x"}
                    for relative in P.RENDER_SCHEMA_RELATIVE_PATHS
                }
            )
            assert set(paths) == set(P.RENDER_SCHEMA_RELATIVE_PATHS), good
        with pytest.raises(P.PilotSelectionError, match="不属于本 pilot 的码族"):
            P.render_schema_template_paths(
                payloads={
                    relative: {"wp_code": "H1-1", "template_path": "x"}
                    for relative in P.RENDER_SCHEMA_RELATIVE_PATHS
                }
            )

    def test_scenario_profile_is_the_shared_editable_standard(
        self, entry: dict[str, Any]
    ) -> None:
        profile = entry["scenario_profile"]
        assert profile["profile_id"] == "xlsx.editable.shared.single.room_service_wired.v1"
        assert profile["mount_cardinality"] == "single"
        assert profile["room_service_state"] == "room_service_wired"
        assert profile["host_reachable"] is True

    def test_required_set_digest_is_this_entry_own(self) -> None:
        """required set 是 shared+editable 的标准 24 条，digest 与其他三个 pilot 都不同。"""
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entries = manifest_entries_by_id(load_entry_manifest())
        mine = derive_for_manifest_entry(
            entries[P.PILOT_ENTRY_ID], authority_model=P.AUTHORITY_MODEL
        )
        assert len(mine.scenario_ids) == 24, mine.scenario_ids
        others = {
            "xlsx/b60/gt-b60-bundle",
            "xlsx/gt-d2-accounts-receivable",
            "xlsx/gt-h1-fixed-assets",
        }
        for other_id in sorted(others):
            other = derive_for_manifest_entry(
                entries[other_id], authority_model=P.AUTHORITY_MODEL
            )
            assert other.digest != mine.digest, other_id

    def test_selection_fails_closed_when_the_entry_disappears(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        patched["entries"] = [
            item for item in patched["entries"] if item["entry_id"] != P.PILOT_ENTRY_ID
        ]
        with pytest.raises(P.PilotSelectionError, match="不在 source-backed manifest"):
            P.assert_pilot_entry_selectable(resolution=resolution, manifest=patched)

    def test_selection_fails_closed_on_parent_duplicate(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["independent_entry"] = False
                item["parent_entry_id"] = "xlsx/gt-wp-renderer"
        with pytest.raises(P.PilotSelectionError, match="independent_entry"):
            P.assert_pilot_entry_selectable(resolution=resolution, manifest=patched)

    def test_selection_fails_closed_on_wp_code_drift(
        self, manifest: dict[str, Any], resolution: Any
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["wp_match"]["wp_code_patterns"] = ["G7L", "G7X"]
        with pytest.raises(P.PilotSelectionError, match="wp_code_patterns"):
            P.assert_pilot_entry_selectable(resolution=resolution, manifest=patched)

    def test_selection_fails_closed_when_a_render_schema_points_elsewhere(
        self, resolution: Any
    ) -> None:
        bad = {
            relative: f"backend/wp_templates/{P.TEMPLATE_RELATIVE_PATH}"
            for relative in P.RENDER_SCHEMA_RELATIVE_PATHS
        }
        bad[P.RENDER_SCHEMA_RELATIVE_PATHS[1]] = "backend/wp_templates/H/H1 固定资产.xlsx"
        with pytest.raises(P.PilotSelectionError, match="与本 pilot 冻结的"):
            P.assert_pilot_entry_selectable(
                resolution=resolution, declared_template_paths=bad
            )

    def test_selection_fails_closed_when_a_render_schema_is_unobserved(
        self, resolution: Any
    ) -> None:
        """只给一份声明 ⇒ 必须打红，不得对未观测的配置放行（fail-open 的常见形态）。"""
        partial = {
            P.RENDER_SCHEMA_RELATIVE_PATHS[0]: (
                f"backend/wp_templates/{P.TEMPLATE_RELATIVE_PATH}"
            )
        }
        with pytest.raises(P.PilotSelectionError, match="不得对未观测的"):
            P.assert_pilot_entry_selectable(
                resolution=resolution, declared_template_paths=partial
            )

    def test_the_contract_generator_refuses_to_write_when_selection_breaks(self) -> None:
        """生成器必须先过选型门再落盘（源码级：`assert_pilot_entry_selectable` 在 build 之前）。"""
        source = (
            _BACKEND / "scripts" / "gen" / "generate_pilot_g7_two_level_dynamic_contract.py"
        ).read_text(encoding="utf-8")
        gate = source.index("assert_pilot_entry_selectable")
        build = source.index("P.build_contract_payload()")
        write = source.index("path.write_bytes(blob)")
        assert gate < build < write, (gate, build, write)
        assert "assert_managed_tables_are_not_exempted" in source
        assert "assert_render_layer_renders_two_level" in source


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板与受管 sheet 选择：都是实测事实
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthoritativeTemplate:
    """**Validates: Requirements 6.13 / 9.9**"""

    def test_template_bytes_are_unchanged(self) -> None:
        data = P.read_authoritative_template()
        assert hashlib.sha256(data).hexdigest() == P.TEMPLATE_SHA256
        assert len(data) == 263335

    def test_template_lives_under_the_authority_root(self) -> None:
        path = P.authoritative_template_path()
        assert path.is_file()
        assert path.parent.parent.name == "wp_templates"
        assert path.parent.parent.parent.name == "backend"

    def test_reference_copy_is_never_read(self) -> None:
        """`基础数据/…参考副本` 一次都不读（memory 铁律：运行时权威只认 wp_templates）。"""
        literals = _non_docstring_literals(Path(P.__file__))
        for text in literals:
            assert "基础数据" not in text, text
            assert "致同通用审计程序" not in text, text

    def test_template_sentinel_rejects_a_mutated_workbook(
        self, monkeypatch: pytest.MonkeyPatch, workdir: Path
    ) -> None:
        fake = workdir / "mutated.xlsx"
        fake.write_bytes(P.read_authoritative_template() + b"\x00")
        monkeypatch.setattr(P, "authoritative_template_path", lambda: fake)
        with pytest.raises(P.PilotSelectionError, match="权威模板字节已变"):
            P.read_authoritative_template()

    def test_workbook_has_twenty_two_sheets_and_only_one_is_declared(
        self, workbook: Any, contract: Any
    ) -> None:
        assert len(workbook.sheetnames) == EXPECTED_SHEET_COUNT, workbook.sheetnames
        assert P.MANAGED_SHEET in workbook.sheetnames
        assert [sheet.excel_name for sheet in contract.sheets] == [P.MANAGED_SHEET]

    def test_managed_sheet_merge_count_is_the_real_template_fact(
        self, merges: frozenset[str]
    ) -> None:
        assert len(merges) == EXPECTED_MERGE_COUNT, len(merges)

    def test_record_formula_cells_ship_without_cached_values(
        self, sheet_part: str, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        """模板自身的公式格**没有**缓存值 —— fixture 因此必须补值。

        这条钉住的是「为什么 `fill_record_formula_cache` 存在」。模板哪天带上缓存值，本测试
        打红，提醒去掉补值步骤（否则那一步会静默覆盖真实值）。
        """
        xml = _read_entries(instrumented.instrumented_bytes)[sheet_part].decode("utf-8")
        empty = 0
        for column in RECORD_FORMULA_COLUMNS:
            for row in range(FIRST, LAST + 1):
                match = re.search(r'<c r="' + column + str(row) + r'"[^>]*>(.*?)</c>', xml)
                assert match, f"{column}{row}"
                body = match.group(1)
                assert "<f>" in body, f"{column}{row} 不是公式格"
                assert "<v></v>" in body, f"{column}{row} 已带缓存值"
                empty += 1
        assert empty == EXPECTED_RECORD_FORMULA_CELLS, empty


class TestManagedSheetSelectionIsMeasured:
    """**Validates: Requirements 6.1 / 6.3 / 12.2**

    「为什么受管 sheet 是国企披露 sheet」的每一条都是实测事实，不是文档声明。
    """

    def test_four_edge_seed_covers_exactly_the_two_disclosure_sheets(self) -> None:
        facts = json.loads(
            (_REPO / P.COLUMN_SOURCE_FACTS_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        assert tuple(facts["_meta"]["sheet_names"]) == (
            "附注披露信息（上市公司）",
            P.MANAGED_SHEET,
        )
        assert facts["_meta"]["source_sha256"] == P.TEMPLATE_SHA256

    def test_seed_counts_reproduce_the_archived_spec_numbers(self) -> None:
        """38 张表 / 24 两级 / 4 豁免 ⇒ 应渲染两级 20 张（`is_two_level` 不能直接当期望）。"""
        facts = json.loads(
            (_REPO / P.COLUMN_SOURCE_FACTS_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        total = sum(
            len(tables)
            for variant in ("listed", "soe")
            for tables in facts[variant].values()
        )
        assert total == EXPECTED_FACTS_TABLE_COUNT, total
        two_level, exempt, rendered = P.assert_managed_tables_are_not_exempted(facts=facts)
        assert (two_level, exempt, rendered) == (
            EXPECTED_FACTS_TWO_LEVEL,
            EXPECTED_FACTS_EXEMPT,
            EXPECTED_FACTS_TWO_LEVEL_RENDERED,
        )

    def test_exemption_judgement_fails_closed_when_my_table_becomes_exempt(self) -> None:
        """反向自检：给本表打上豁免 ⇒ 必须打红（已裁决单槽 flat 的表不能当两级 pilot）。"""
        facts = json.loads(
            (_REPO / P.COLUMN_SOURCE_FACTS_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        facts["soe"]["七、重要非全资子公司"]["主要财务信息"]["single_slot_exemption"] = {
            "exempt_kinds": ["flat", "group"]
        }
        with pytest.raises(P.PilotSelectionError, match="single_slot_exemption"):
            P.assert_managed_tables_are_not_exempted(facts=facts)

    def test_listed_side_twin_matrix_is_all_formula_in_the_source(
        self, workbook: Any
    ) -> None:
        """上市侧同构表 102 格全是公式 ⇒ 零 editable ⇒ merge 家族两条场景结构性不可满足。"""
        sheet = workbook["附注披露信息（上市公司）"]
        formula = 0
        cells = 0
        for row in range(171, 188):
            for column in ("B", "C", "D", "E", "F", "G"):
                value = sheet[f"{column}{row}"].value
                cells += 1
                if isinstance(value, str) and value.startswith("="):
                    formula += 1
        assert cells == 102, cells
        assert formula == 102, formula

    def test_my_matrix_data_cells_are_all_empty_in_the_source(self, worksheet: Any) -> None:
        """本表 100 格逐格实测**全空** ⇒ 全部 editable（这才让 merge 家族可满足）。"""
        empty = 0
        for metric_key, _label in P.MATRIX_METRICS:
            row = P.metric_row_for(metric_key)
            for seq in range(1, EXPECTED_DYNAMIC_COLUMN_COUNT + 1):
                coord = f"{P.matrix_column_letter_for_seq(seq)}{row}"
                assert worksheet[coord].value is None, coord
                empty += 1
        assert empty == EXPECTED_EDITABLE_COUNT, empty

    def test_uuid_column_choice_is_forced_by_real_column_usage(
        self, worksheet: Any
    ) -> None:
        """`M` 列有内容不能隐藏；`N..Q` 全空 ⇒ `N` 是最左的安全列。"""
        used: dict[str, int] = {}
        for row in worksheet.iter_rows():
            for cell in row:
                if cell.value is not None:
                    letter = cell.column_letter
                    used[letter] = used.get(letter, 0) + 1
        assert used.get("M", 0) == 13, used.get("M")
        for letter in ("N", "O", "P", "Q"):
            assert used.get(letter, 0) == 0, (letter, used.get(letter))
        assert P.UUID_COL == "N"
        assert P.MANAGED_LAST_COL == "M"

    def test_uuid_column_left_of_managed_columns_is_refused(self) -> None:
        """反向自检：UUID 列放到受管列左侧 ⇒ Task 17 必须拒。"""
        with pytest.raises(EI.InstrumentationError, match="必须在受管业务列"):
            EI.ExcelInstrumentationSpec(
                entry_id=P.PILOT_ENTRY_ID,
                template_id=P.TEMPLATE_ID,
                template_relative_path=P.TEMPLATE_RELATIVE_PATH,
                managed_sheet=P.MANAGED_SHEET,
                first_data_row=FIRST,
                last_data_row=LAST,
                footer_row=P.RECORD_FOOTER_ROW,
                managed_last_col="M",
                uuid_col="L",
                table_name=P.TABLE_NAME,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约的每个字段都有源（第 1 边：源 xlsx）
# ═══════════════════════════════════════════════════════════════════════════


def _source_cell(coord_or_range: str) -> str:
    """把 `源xlsx!{sheet}!{格}` 还原成格坐标（守卫据此回查 openpyxl）。"""
    prefix = f"源xlsx!{P.MANAGED_SHEET}!"
    assert coord_or_range.startswith(prefix), coord_or_range
    return coord_or_range[len(prefix) :]


class TestContractIsGroundedInTheTemplate:
    """**Validates: Requirements 6.1 / 6.2 / 6.3 / 6.6**"""

    def test_disk_contract_matches_the_source_of_truth(self) -> None:
        assert P.assert_contract_file_matches_source() is not None

    def test_contract_is_registered_in_the_delivery_ledger(self) -> None:
        rows = [
            row
            for row in RG.DELIVERED_PER_ENTRY_CONTRACTS
            if row["contract_id"] == P.PILOT_ADAPTER_ID
        ]
        assert len(rows) == 1, rows
        row = rows[0]
        assert row["delivered_by_task"] == "43"
        assert row["pilot_class"] == P.PILOT_CLASS
        assert row["entry_id"] == P.PILOT_ENTRY_ID
        assert row["template_relative_path"] == P.TEMPLATE_RELATIVE_PATH
        assert row["adapter_registered"] is False
        assert set(available_contract_ids()) == {
            str(item["contract_id"]) for item in RG.DELIVERED_PER_ENTRY_CONTRACTS
        }

    def test_field_counts_are_the_real_template_facts(self, contract: Any) -> None:
        fields = contract.all_fields()
        assert len(fields) == EXPECTED_FIELD_COUNT, len(fields)
        editable = [f for f in fields if f.mode is FieldMode.editable]
        protected = [f for f in fields if f.is_protected]
        assert len(editable) == EXPECTED_EDITABLE_COUNT, len(editable)
        assert len(protected) == EXPECTED_PROTECTED_COUNT, len(protected)
        assert len(contract.protected_field_keys()) == EXPECTED_PROTECTED_COUNT

    def test_matrix_header_rows_is_two(self, contract: Any) -> None:
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.MATRIX_TABLE_KEY
        )
        assert table.header_rows == 2
        assert table.two_level_header is True
        assert table.anchor == f"A{P.GROUP_HEADER_ROW}"
        assert table.has_dynamic_rows is False

    def test_record_table_is_the_dynamic_row_table(self, contract: Any) -> None:
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.RECORD_TABLE_KEY
        )
        assert table.header_rows == 1
        assert table.has_dynamic_rows is True
        assert table.delete_policy is not None
        assert table.dynamic_columns is None
        assert list(table.formula_mask) == list(P.RECORD_FORMULA_MASK)

    def test_exactly_one_dynamic_row_table_on_the_managed_sheet(
        self, contract: Any, binding: X.ExcelIdentityBinding
    ) -> None:
        dynamic, statics = X.managed_tables_of(contract, binding=binding)
        assert dynamic.table_key == P.RECORD_TABLE_KEY
        assert [t.table_key for t in statics] == [P.MATRIX_TABLE_KEY]

    def test_label_header_text_is_the_real_cell_text(self, worksheet: Any) -> None:
        """`A62` 是「项  目」（**双空格**），逐字不得简写。"""
        assert worksheet[f"A{P.GROUP_HEADER_ROW}"].value == P.MATRIX_LABEL_HEADER
        assert P.MATRIX_LABEL_HEADER == "项  目"
        assert f"A{P.GROUP_HEADER_ROW}:B{P.LEAF_HEADER_ROW}" in {
            str(item) for item in worksheet.merged_cells.ranges
        }

    def test_every_matrix_leaf_header_matches_the_real_cell_text(
        self, worksheet: Any, matrix_fields: list[dict[str, Any]]
    ) -> None:
        checked = 0
        for spec in matrix_fields:
            coord = _source_cell(spec["header_source_ref"])
            assert worksheet[coord].value == spec["header_text"], coord
            checked += 1
        assert checked == EXPECTED_EDITABLE_COUNT, checked

    def test_every_matrix_group_header_is_a_real_blank_merge(
        self, worksheet: Any, merges: frozenset[str], matrix_fields: list[dict[str, Any]]
    ) -> None:
        """组标题指向的合并区必须真存在，且值**为空** —— 那正是源自己的动态列占位。"""
        checked = 0
        seen: set[str] = set()
        for spec in matrix_fields:
            rng = _source_cell(spec["group_source_ref"])
            assert rng in merges, rng
            anchor = rng.split(":")[0]
            assert worksheet[anchor].value is None, rng
            assert anchor[0] == spec["group_anchor_column"], (anchor, spec)
            seen.add(rng)
            checked += 1
        assert checked == EXPECTED_EDITABLE_COUNT, checked
        assert len(seen) == EXPECTED_TEMPLATE_SLOT_COUNT, sorted(seen)

    def test_every_metric_row_label_matches_the_real_merged_cell(
        self, worksheet: Any, merges: frozenset[str], matrix_fields: list[dict[str, Any]]
    ) -> None:
        checked = 0
        for spec in matrix_fields:
            rng = _source_cell(spec["row_label_source_ref"])
            assert rng in merges, rng
            assert worksheet[rng.split(":")[0]].value == spec["row_label_text"], rng
            checked += 1
        assert checked == EXPECTED_EDITABLE_COUNT, checked

    def test_metric_ids_and_labels_are_source_ordered(self, worksheet: Any) -> None:
        for index, (metric_key, label) in enumerate(P.MATRIX_METRICS):
            row = P.METRIC_FIRST_ROW + index
            assert P.metric_row_for(metric_key) == row
            assert worksheet[f"A{row}"].value == label
            assert metric_key == f"{P.RENDER_METRIC_ID_PREFIX}-{index + 1}"
        # 🔴 store 表键与 metric 行 id 前缀是**两个不同的串**（首轮按前缀猜过一次）。
        assert P.RENDER_MATRIX_TABLE_ID != P.RENDER_METRIC_ID_PREFIX
        assert P.MATRIX_TERMINATOR_ROW == P.METRIC_FIRST_ROW + len(P.MATRIX_METRICS)

    def test_metric_lookup_fails_closed_on_an_unknown_id(self) -> None:
        with pytest.raises(P.PilotSelectionError, match="不在本 pilot 的受管 metric"):
            P.metric_row_for("minority-fs-99")

    def test_every_record_header_matches_the_real_cell_text(
        self, worksheet: Any, record_fields: list[dict[str, Any]]
    ) -> None:
        checked = 0
        for spec in record_fields:
            coord = _source_cell(spec["header_source_ref"])
            assert worksheet[coord].value == spec["header_text"], coord
            checked += 1
        assert checked == len(P.RECORD_COLUMNS) == 7, checked
        # 两个百分号括号必须是**全角**（逐字取源）。
        assert worksheet[f"E{P.RECORD_HEADER_ROW}"].value == "持股比例（%）"
        assert worksheet[f"F{P.RECORD_HEADER_ROW}"].value == "表决权比例（%）"

    def test_record_formula_cells_match_the_declared_template(
        self, worksheet: Any
    ) -> None:
        """30 格逐格与 `RECORD_FORMULA_TEMPLATE` 比对（不是抽样）。"""
        checked = 0
        for column in RECORD_FORMULA_COLUMNS:
            for offset in range(LAST - FIRST + 1):
                row = FIRST + offset
                expected = P.RECORD_FORMULA_TEMPLATE.format(
                    col=column, src=P.RECORD_FORMULA_SOURCE_FIRST_ROW + offset
                )
                assert worksheet[f"{column}{row}"].value == expected, f"{column}{row}"
                checked += 1
        assert checked == EXPECTED_RECORD_FORMULA_CELLS, checked

    def test_record_seq_column_is_a_literal_not_a_formula(self, worksheet: Any) -> None:
        for offset in range(LAST - FIRST + 1):
            value = worksheet[f"A{FIRST + offset}"].value
            assert value == offset + 1, (offset, value)

    def test_formula_mask_covers_every_formula_field(self, contract: Any) -> None:
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.RECORD_TABLE_KEY
        )
        assert list(table.formula_mask) == [f"B{FIRST}:G{LAST}"]
        formula_columns = {
            spec.cell.column for spec in table.fields if spec.mode is FieldMode.formula
        }
        assert formula_columns == set(RECORD_FORMULA_COLUMNS)

    def test_matrix_declares_no_formula_mask_because_the_source_has_none(
        self, worksheet: Any, contract: Any
    ) -> None:
        """矩阵源侧 0 公式 ⇒ 不造 mask（Requirement 6.1）。空 mask 有专门事实判据。"""
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.MATRIX_TABLE_KEY
        )
        assert table.formula_mask == ()
        formulas = [
            f"{P.matrix_column_letter_for_seq(seq)}{P.metric_row_for(key)}"
            for key, _label in P.MATRIX_METRICS
            for seq in range(1, EXPECTED_DYNAMIC_COLUMN_COUNT + 1)
            if isinstance(
                worksheet[
                    f"{P.matrix_column_letter_for_seq(seq)}{P.metric_row_for(key)}"
                ].value,
                str,
            )
        ]
        assert formulas == [], formulas
        # 语义上是合计的两行在源模板里也确实是空的（不得据"常识"补公式）。
        for metric_key in ("minority-fs-3", "minority-fs-6"):
            row = P.metric_row_for(metric_key)
            assert worksheet[f"C{row}"].value is None

    def test_footer_marker_is_the_real_cell_text(self, worksheet: Any) -> None:
        assert worksheet[f"A{P.RECORD_FOOTER_ROW}"].value == P.FOOTER_MARKER
        assert worksheet[f"A{P.RECORD_FOOTER_ROW - 1}"].value is None

    def test_footer_anchor_never_hardcodes_a_row(self, contract_payload: Any) -> None:
        table = next(
            t
            for t in contract_payload["sheets"][0]["tables"]
            if t["table_key"] == P.RECORD_TABLE_KEY
        )
        anchor = table["footer_anchor"]
        assert set(anchor) == {"marker", "search_column"}
        assert anchor["marker"] == P.FOOTER_MARKER
        assert anchor["search_column"] == "A"

    def test_row_identity_is_not_positional(self, contract: Any) -> None:
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.RECORD_TABLE_KEY
        )
        assert table.row_identity is not None
        assert table.row_identity.json_pointer == "/rows/*/rowUuid"
        for spec in table.fields:
            assert "{row_uuid}" in spec.json_pointer, spec.stable_field_key
            assert not re.search(r"/\d+/", spec.json_pointer), spec.json_pointer

    def test_matrix_fields_are_static_and_carry_no_row_placeholder(
        self, contract: Any
    ) -> None:
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.MATRIX_TABLE_KEY
        )
        for spec in table.fields:
            assert spec.row_scoped is False, spec.stable_field_key
            assert spec.cell is not None and spec.cell.static_row is not None
            assert "{row_uuid}" not in spec.json_pointer

    def test_unmanaged_neighbour_cells_are_the_real_contents(self, worksheet: Any) -> None:
        checked = 0
        for coord, content in P.UNMANAGED_NEIGHBOUR_CELLS:
            assert worksheet[coord].value == content, coord
            checked += 1
        assert checked == 6, checked

    def test_contract_declares_no_metadata_sheet(self, contract: Any) -> None:
        from app.services.workpaper_sync.excel_entry_gate import (
            assert_contract_declares_no_metadata_sheet,
        )

        assert_contract_declares_no_metadata_sheet(contract)
        blob = json.dumps(contract.canonical_payload, ensure_ascii=False)
        assert GT_SYNC_SHEET_NAME not in blob

    def test_metadata_sheet_declared_as_business_is_refused(self, contract_payload: Any) -> None:
        """反向自检：把 `_GT_SYNC` 写成受管业务 sheet ⇒ 必须打红。"""
        from app.services.workpaper_sync.excel_entry_gate import (
            MetadataSheetLeakError,
            assert_contract_declares_no_metadata_sheet,
        )

        patched = json.loads(json.dumps(contract_payload))
        patched["sheets"][0]["excel_name"] = GT_SYNC_SHEET_NAME
        leaked = parse_contract(patched, adapter_id=P.PILOT_ADAPTER_ID)
        with pytest.raises(MetadataSheetLeakError):
            assert_contract_declares_no_metadata_sheet(leaked)

    def test_mutated_contract_payload_is_rejected(self, contract_payload: Any) -> None:
        patched = json.loads(json.dumps(contract_payload))
        patched["sheets"][0]["tables"][0]["header_rows"] = 4
        with pytest.raises(ContractError):
            parse_contract(patched, adapter_id=P.PILOT_ADAPTER_ID)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 22：动态列 key 与 label 解耦（本 pilot 是唯一真有动态列的）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty22ColumnIdentityIsDecoupledFromLabel:
    """**Validates: Requirements 6.4** · **Property 22**

    真实（非合成）oracle：源模板行 63 的 **10 个数据列只有 2 个不同 label**，各重复 5 次。
    """

    def test_duplicate_leaf_labels_really_exist_in_the_template(
        self, worksheet: Any
    ) -> None:
        labels: dict[str, int] = {}
        for seq in range(1, EXPECTED_DYNAMIC_COLUMN_COUNT + 1):
            coord = f"{P.matrix_column_letter_for_seq(seq)}{P.LEAF_HEADER_ROW}"
            value = str(worksheet[coord].value)
            labels[value] = labels.get(value, 0) + 1
        assert labels == {
            "期末数/本期发生额": EXPECTED_TEMPLATE_SLOT_COUNT,
            "期初数/上期发生额": EXPECTED_TEMPLATE_SLOT_COUNT,
        }, labels
        assert len(labels) == 2
        assert sum(labels.values()) == EXPECTED_DYNAMIC_COLUMN_COUNT

    def test_dynamic_column_keys_are_distinct_despite_duplicate_labels(self) -> None:
        keys = P.dynamic_column_keys_for_entities(P.RENDER_SLOT_DEFAULT_NAMES)
        assert len(keys) == EXPECTED_DYNAMIC_COLUMN_COUNT
        assert len(set(keys)) == EXPECTED_DYNAMIC_COLUMN_COUNT
        for key in keys:
            assert key.isascii(), key
            assert re.fullmatch(rf"{P.MATRIX_TABLE_KEY}_[1-9][0-9]*", key), key

    def test_stable_field_keys_are_distinct_and_carry_no_chinese_label(
        self, contract: Any
    ) -> None:
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.MATRIX_TABLE_KEY
        )
        keys = [spec.stable_field_key for spec in table.fields]
        assert len(keys) == EXPECTED_EDITABLE_COUNT
        assert len(set(keys)) == EXPECTED_EDITABLE_COUNT
        for key in keys:
            assert key.isascii(), key
            for label in ("期末数", "期初数", "本期发生额", "上期发生额", "公司"):
                assert label not in key, (key, label)

    def test_renaming_every_entity_does_not_change_any_key(self) -> None:
        """改名 = 只动 `entityName`。5 家公司全部改名后 10 个键**逐字不变**。"""
        before = P.dynamic_column_keys_for_entities(P.RENDER_SLOT_DEFAULT_NAMES)
        renamed = ("华东实业", "华东实业", "华东实业", "北方能源", "北方能源")
        after = P.dynamic_column_keys_for_entities(renamed)
        assert after == before
        # label 重名（三家同名）也不撞键 —— 这正是 H7 付过学费的形态。
        observed = P.observed_dynamic_columns_for(renamed)[P.MATRIX_TABLE_KEY]
        labels = [label for label, _key in observed]
        assert len(set(labels)) < len(labels), labels
        derived = assert_dynamic_columns_label_independent(
            slot=P.MATRIX_TABLE_KEY, observed=observed, where="task43"
        )
        assert derived == before

    def test_key_builder_signature_cannot_see_a_label(self) -> None:
        """构造上不可能「按 label 建键」：上游生成器只吃 `(slot, count)`。"""
        import inspect

        params = list(inspect.signature(dynamic_column_stable_keys).parameters)
        assert params == ["slot", "count"], params
        assert "label" not in params

    def test_module_delegates_key_generation_and_never_reimplements_it(self) -> None:
        """源码级：本模块不得自己拼 `f"{slot}_{seq}"`，必须委派上游生成器。"""
        body = function_body_code(Path(P.__file__), "dynamic_column_keys_for_entities")
        assert "dynamic_column_stable_keys(" in body
        for forbidden in ("{slot}_{seq}", "'{}_{}'.format", "%s_%s"):
            assert forbidden not in body, (forbidden, body)
        # 反向自检：把旧形态喂回去必须仍被抓到（否则这条判据是空转）。
        legacy = 'return tuple(f"{slot}_{seq}" for seq in range(1, count + 1))'
        assert "{slot}_{seq}" in legacy

    def test_contract_identity_is_the_imported_constant_never_a_literal(self) -> None:
        """源码级：契约 payload 里每个 `identity` 值都必须**引用**上游常量，不得写字面量。

        🔴 同值字面量与常量在**运行时完全不可分辨**：磁盘契约逐字节相同、
        `parse_contract` 照过、`{slot}_{seq}` 形态断言照绿、`test_disk_contract_matches_
        the_source_of_truth` 双向锁也照绿。唯一能分辨的只有源码 —— 而后果是真的：上游
        `contracts.DYNAMIC_COLUMN_IDENTITY_TEMPLATE` 一改形状（比如 `{slot}#{seq}`），
        `_parse_dynamic_columns` 按新形状拒，本模块却仍按旧形状产出 ⇒ 整表发布不出去。

        本判据是 Task 43 变异 **M31**（故意的同值变异）逼出来的：首轮 M31 因
        `scope_check` 误用 JSON 回调判 ERROR（pytest 从未执行）；修好后实测 **GREEN**，
        证明「identity 是否引用单一真源」这条判据当时并不存在。
        """

        def identity_values(tree: ast.AST) -> list[str]:
            """所有字典字面量里键为 `"identity"` 的**值表达式**源码。

            走 AST 而不是文本：本模块的 docstring / 欠账登记里刻意写着
            `identity 只能是 {slot}_{seq}` 这类**说明**，纯文本判据会把说明判成违规
            （`build_contract_payload` 的事实块里就有一条）。
            """
            found: list[str] = []
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "identity":
                        found.append(ast.unparse(value))
            return found

        module_source = Path(P.__file__).read_text(encoding="utf-8")
        observed = identity_values(ast.parse(module_source))
        # 两处：`_matrix_table_payload` 的契约表 + `build_contract_payload` 的事实块。
        assert observed == ["DYNAMIC_COLUMN_IDENTITY_TEMPLATE"] * 2, observed
        # 且本模块不得自建第二真源（重新赋值同名常量）。
        assigned = {
            target.id
            for node in ast.walk(ast.parse(module_source))
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        } | {
            node.target.id
            for node in ast.walk(ast.parse(module_source))
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        assert "DYNAMIC_COLUMN_IDENTITY_TEMPLATE" not in assigned, sorted(assigned)
        # 反向自检：用**同一个**谓词跑旧形态，必须报出字面量（不是再写一遍判据）。
        legacy = identity_values(ast.parse('spec = {"identity": "{slot}_{seq}"}'))
        assert legacy == ["'{slot}_{seq}'"], legacy
        assert legacy != ["DYNAMIC_COLUMN_IDENTITY_TEMPLATE"]

    def test_column_count_is_never_hardcoded(self) -> None:
        """列数 = len(实体) × len(子列)，逐个 seed 现算；函数体里不得出现列数字面量。"""
        width = len(P.RENDER_SUB_COLUMNS)
        for count in (1, 2, 3, 5, 9, 37):
            names = tuple(f"e{i}" for i in range(count))
            assert len(P.dynamic_column_keys_for_entities(names)) == count * width
        assert P.dynamic_column_keys_for_entities(()) == ()
        body = function_body_code(Path(P.__file__), "dynamic_column_keys_for_entities")
        assert not re.search(r"\b(?:3|5|6|10)\b", body), body
        # 反向自检：写死列数的旧形态必须被同一条正则抓到。
        assert re.search(r"\b(?:3|5|6|10)\b", "count = 10")

    def test_binding_maps_each_key_to_its_own_column(self) -> None:
        binding = P.dynamic_column_binding_for(P.RENDER_SLOT_DEFAULT_NAMES)
        assert list(binding.values()) == list("CDEFGHIJKL")
        assert len(set(binding.values())) == EXPECTED_DYNAMIC_COLUMN_COUNT
        assert set(binding) == set(
            P.dynamic_column_keys_for_entities(P.RENDER_SLOT_DEFAULT_NAMES)
        )

    def test_binding_is_verified_by_the_materializer_gate(self, contract: Any) -> None:
        """用**生产**判据（Task 38）跑一次，不是自己再写一遍。"""
        binding = make_binding()
        resolved = M.assert_dynamic_column_binding_usable(contract=contract, binding=binding)
        assert resolved[P.MATRIX_TABLE_KEY] == binding.dynamic_column_columns[
            P.MATRIX_TABLE_KEY
        ]

    def test_missing_binding_fails_closed_on_both_sides(
        self, contract: Any, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        """契约声明了动态列却不给绑定 ⇒ 读写两侧各自 fail closed（不按声明列右移猜）。"""
        naked = make_binding(dynamic_column_columns={})
        with pytest.raises(M.DynamicColumnWriteError, match="没给"):
            M.assert_dynamic_column_binding_usable(contract=contract, binding=naked)
        with pytest.raises(X.DynamicColumnBindingMissingError):
            extract(base_path, definitions, naked)

    def test_label_shaped_key_fails_closed(self, contract: Any) -> None:
        """用可改 label 当键 ⇒ 两侧都拒（Requirement 6.4）。"""
        bad = make_binding(
            dynamic_column_columns={P.MATRIX_TABLE_KEY: {"公司1_期末数": "C"}}
        )
        with pytest.raises(M.DynamicColumnWriteError, match="不符契约声明的 identity"):
            M.assert_dynamic_column_binding_usable(contract=contract, binding=bad)
        with pytest.raises(DynamicColumnIdentityError):
            assert_dynamic_columns_label_independent(
                slot=P.MATRIX_TABLE_KEY,
                observed=[("公司1 期末数", "公司1_期末数")],
                where="task43",
            )

    def test_two_keys_on_one_column_fails_closed(self, contract: Any) -> None:
        collided = P.dynamic_column_binding_for(P.RENDER_SLOT_DEFAULT_NAMES)
        collided[f"{P.MATRIX_TABLE_KEY}_2"] = collided[f"{P.MATRIX_TABLE_KEY}_1"]
        bad = make_binding(dynamic_column_columns={P.MATRIX_TABLE_KEY: collided})
        with pytest.raises(M.DynamicColumnWriteError, match="都绑定到列"):
            M.assert_dynamic_column_binding_usable(contract=contract, binding=bad)

    def test_duplicate_keys_in_observed_pairs_fail_closed(self) -> None:
        with pytest.raises(DynamicColumnIdentityError, match="发生冲突"):
            assert_dynamic_columns_label_independent(
                slot=P.MATRIX_TABLE_KEY,
                observed=[
                    ("公司1 期末数", f"{P.MATRIX_TABLE_KEY}_1"),
                    ("公司1 期初数", f"{P.MATRIX_TABLE_KEY}_1"),
                ],
                where="task43",
            )

    def test_reordered_entities_shift_keys_and_the_gate_notices(self) -> None:
        """漏号/错序必须被 label 无关的派生结果抓到（第 3 条判据可达）。"""
        observed = P.observed_dynamic_columns_for(P.RENDER_SLOT_DEFAULT_NAMES)[
            P.MATRIX_TABLE_KEY
        ]
        skipped = [
            (label, key if index != 3 else f"{P.MATRIX_TABLE_KEY}_99")
            for index, (label, key) in enumerate(observed)
        ]
        with pytest.raises(DynamicColumnIdentityError, match="与 label 无关的派生键"):
            assert_dynamic_columns_label_independent(
                slot=P.MATRIX_TABLE_KEY, observed=skipped, where="task43"
            )

    def test_seq_to_column_and_render_key_are_bijective(self) -> None:
        columns = [
            P.matrix_column_letter_for_seq(seq)
            for seq in range(1, EXPECTED_DYNAMIC_COLUMN_COUNT + 1)
        ]
        renders = [
            P.render_column_key_for_seq(seq)
            for seq in range(1, EXPECTED_DYNAMIC_COLUMN_COUNT + 1)
        ]
        assert len(set(columns)) == len(set(renders)) == EXPECTED_DYNAMIC_COLUMN_COUNT
        assert renders[0] == f"{P.RENDER_SLOT}_1_current"
        assert renders[1] == f"{P.RENDER_SLOT}_1_prior"
        assert renders[-1] == f"{P.RENDER_SLOT}_5_prior"
        for bad in (0, -1):
            with pytest.raises(DynamicColumnIdentityError):
                P.matrix_column_letter_for_seq(bad)
            with pytest.raises(DynamicColumnIdentityError):
                P.render_column_key_for_seq(bad)

    def test_dynamic_columns_source_ref_points_at_the_placeholder_row(
        self, contract_payload: Any, merges: frozenset[str]
    ) -> None:
        table = next(
            t
            for t in contract_payload["sheets"][0]["tables"]
            if t["table_key"] == P.MATRIX_TABLE_KEY
        )
        spec = table["dynamic_columns"]
        assert spec["identity"] == "{slot}_{seq}"
        rng = _source_cell(spec["source_ref"])
        assert rng == f"C{P.GROUP_HEADER_ROW}:L{P.GROUP_HEADER_ROW}"
        # 该区间恰好被 5 个空白横向合并覆盖。
        covered = {
            item
            for item in merges
            if item.endswith(str(P.GROUP_HEADER_ROW))
            and re.fullmatch(r"[C-L]\d+:[C-L]\d+", item)
        }
        assert len(covered) == EXPECTED_TEMPLATE_SLOT_COUNT, sorted(covered)


# ═══════════════════════════════════════════════════════════════════════════
# 5. 四边真源：第 2 边（seed）与第 4 边（渲染层）
# ═══════════════════════════════════════════════════════════════════════════


class TestSecondEdgeSeed:
    """**Validates: Requirements 6.3**（seed / 派生投影侧的逐字比对）"""

    def test_seed_describes_my_matrix_exactly(self, worksheet: Any) -> None:
        table = P.source_facts_for_managed_tables()[P.MATRIX_TABLE_KEY]
        assert table["is_two_level"] is True
        assert table["level_count"] == 2
        assert table["label_xlsx_span"] == len(P.MATRIX_LABEL_COLUMNS) == 2
        assert table["label_header_raw"] == P.MATRIX_LABEL_HEADER
        assert table["source_rows"] == (
            f"A{P.GROUP_HEADER_ROW - 1}:L{P.LEAF_HEADER_ROW}"
        ) or table["source_rows"] == f"A{P.GROUP_HEADER_ROW}:L{P.LEAF_HEADER_ROW}"
        columns = table["columns"]
        assert len(columns) == EXPECTED_DYNAMIC_COLUMN_COUNT, len(columns)
        # 每列的 label 与源 xlsx 行 63 逐字相等；group 是按锚列区分的动态占位。
        for seq, column in enumerate(columns, start=1):
            coord = f"{P.matrix_column_letter_for_seq(seq)}{P.LEAF_HEADER_ROW}"
            assert column["label"] == worksheet[coord].value, coord
            anchor_index = (seq - 1) // len(P.RENDER_SUB_COLUMNS)
            expected_group = P.TEMPLATE_SLOT_GROUP_MERGES[anchor_index][2]
            assert column["group"] == expected_group, (seq, column)

    def test_seed_describes_my_record_table_exactly(self, worksheet: Any) -> None:
        table = P.source_facts_for_managed_tables()[P.RECORD_TABLE_KEY]
        assert table["is_two_level"] is False
        assert table["level_count"] == 1
        assert table["label_header_raw"] == worksheet[f"A{P.RECORD_HEADER_ROW}"].value
        labels = [item["label"] for item in table["columns"]]
        assert labels == [
            worksheet[f"{column}{P.RECORD_HEADER_ROW}"].value
            for _key, column, *_rest in P.RECORD_COLUMNS
            if column != "A"
        ], labels

    def test_seed_lookup_fails_closed_on_a_different_workbook(self) -> None:
        facts = json.loads(
            (_REPO / P.COLUMN_SOURCE_FACTS_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        facts["_meta"]["source_sha256"] = "0" * 64
        with pytest.raises(P.PilotSelectionError, match="source_sha256"):
            P.source_facts_for_managed_tables(facts=facts)

    def test_seed_lookup_fails_closed_when_my_table_disappears(self) -> None:
        facts = json.loads(
            (_REPO / P.COLUMN_SOURCE_FACTS_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        del facts["soe"]["七、重要非全资子公司"]["主要财务信息"]
        with pytest.raises(P.PilotSelectionError, match="在 seed 侧没有登记项"):
            P.source_facts_for_managed_tables(facts=facts)


class TestFourthEdgeRenderLayer:
    """**Validates: Requirements 6.3 / 6.4**（渲染层：三要素判据，不是 grep 符号名）

    归档 spec 的最贵教训：模型声明 `column.group`、三向数据守卫 39 例全绿，而任何 `.vue`
    零引用 ⇒ 两级表头 0/38 张从未渲染。故这一边必须落到模板形态。
    """

    def test_render_layer_really_renders_two_level_headers(self) -> None:
        facts = P.assert_render_layer_renders_two_level()
        assert facts["header_block_symbols_used_by_tab"] == ("buildG7HeaderBlocks",)
        assert len(facts["iterates_groups"]) == 1, facts["iterates_groups"]
        assert len(facts["outer_gate"]) == 1, facts["outer_gate"]
        assert len(facts["inner_nesting"]) == 1, facts["inner_nesting"]
        assert "headerBlocks(table)" in facts["iterates_groups"][0]
        assert "blk.group" in facts["outer_gate"][0]
        assert "blk.columns" in facts["inner_nesting"][0]

    @pytest.mark.parametrize(
        "removal,expected",
        [
            ("buildG7HeaderBlocks", "一个都没被引用"),
            ('v-for="(blk, bi) in headerBlocks(table)"', "父表头遍历"),
            ('v-if="blk.group"', "两级门控"),
            ('v-for="column in blk.columns"', "子列遍历"),
        ],
    )
    def test_each_missing_element_turns_the_fourth_edge_red(
        self, removal: str, expected: str
    ) -> None:
        """反向自检：三要素（+ 符号引用）各拿掉一个 ⇒ 必须打红，且指出**是哪一个**。"""
        tab = (_REPO / P.RENDER_TAB_RELATIVE_PATH).read_text(encoding="utf-8")
        assert removal in tab, removal
        patched = dict.fromkeys(
            (
                P.RENDER_TAB_RELATIVE_PATH,
                P.RENDER_HEADER_BLOCKS_RELATIVE_PATH,
                P.RENDER_MODEL_RELATIVE_PATH,
                P.RENDER_SLOT_COLUMNS_RELATIVE_PATH,
            )
        )
        sources = {
            relative: (_REPO / relative).read_text(encoding="utf-8") for relative in patched
        }
        sources[P.RENDER_TAB_RELATIVE_PATH] = tab.replace(removal, "GONE")
        with pytest.raises(P.RenderLayerError, match=expected):
            P.assert_render_layer_renders_two_level(sources=sources)

    def test_slot_key_rule_matches_my_conversion(self) -> None:
        """渲染层的键拼接规则必须与 :func:`render_column_key_for_seq` 一致（第四边闭合）。"""
        source = (_REPO / P.RENDER_SLOT_COLUMNS_RELATIVE_PATH).read_text(encoding="utf-8")
        assert "out.push({ key: `${slot}_${seq}`, seq, entityName, editable: true })" in source
        assert "key: `${slot}_${seq}_${s.key}`," in source
        # 渲染层按「实体外层、子列内层」展开 ⇒ 第 n 列属实体 ceil(n/2)。
        for seq in range(1, EXPECTED_DYNAMIC_COLUMN_COUNT + 1):
            entity_seq = (seq - 1) // len(P.RENDER_SUB_COLUMNS) + 1
            sub_key = P.RENDER_SUB_COLUMNS[(seq - 1) % len(P.RENDER_SUB_COLUMNS)][0]
            assert P.render_column_key_for_seq(seq) == (
                f"{P.RENDER_SLOT}_{entity_seq}_{sub_key}"
            )
        forward = re.search(
            r"names\.forEach\(\(entityName, index\) => \{\s*const seq = index \+ 1", source
        )
        assert forward, "渲染层的实体/子列展开顺序已变，换算规则失去依据"

    def test_render_model_declares_my_slot_and_sub_columns(self) -> None:
        source = (_REPO / P.RENDER_MODEL_RELATIVE_PATH).read_text(encoding="utf-8")
        assert f"MINORITY_FS_SLOT = '{P.RENDER_SLOT}'" in source
        for sub_key, sub_label in P.RENDER_SUB_COLUMNS:
            assert f"{{ key: '{sub_key}', label: '{sub_label}' }}" in source
        for name in P.RENDER_SLOT_DEFAULT_NAMES:
            assert f"'{name}'" in source
        assert f"templateTableKey: '主要财务信息'" in source
        assert f"labelHeader: '{P.MATRIX_LABEL_HEADER}'" in source

    def test_render_model_metric_labels_match_the_source_rows(self, worksheet: Any) -> None:
        """渲染层的 10 个 metric label 与源 A64..A73 逐字相等（顺序也要相等）。"""
        source = (_REPO / P.RENDER_MODEL_RELATIVE_PATH).read_text(encoding="utf-8")
        block = re.search(r"const minorityFsLabels = \[(.*?)\]", source, re.S)
        assert block, "渲染层 minorityFsLabels 形态已变"
        labels = re.findall(r"'([^']+)'", block.group(1))
        assert labels == [
            worksheet[f"A{P.METRIC_FIRST_ROW + index}"].value
            for index in range(len(P.MATRIX_METRICS))
        ], labels
        assert labels == [label for _key, label in P.MATRIX_METRICS]

    def test_render_record_columns_match_the_source_header(self, worksheet: Any) -> None:
        source = (_REPO / P.RENDER_MODEL_RELATIVE_PATH).read_text(encoding="utf-8")
        block = re.search(
            r"const formerSubsidiaryColumns = flatCols\(cols\(\[(.*?)\]\)\)", source, re.S
        )
        assert block, "渲染层 formerSubsidiaryColumns 形态已变"
        pairs = re.findall(r"\['(\w+)', '([^']+)'", block.group(1))
        expected = [
            (render_key, worksheet[f"{column}{P.RECORD_HEADER_ROW}"].value)
            for _key, column, _mode, _vt, render_key, _header in P.RECORD_COLUMNS
            if render_key
        ]
        assert pairs == expected, (pairs, expected)

    def test_store_item_id_comes_from_the_real_tab(self) -> None:
        tab = (_REPO / P.RENDER_TAB_RELATIVE_PATH).read_text(encoding="utf-8")
        assert f"const RESPONSE_KEY = '{P.STORE_ITEM_ID}'" in tab
        assert f"const SHEET_NAME = '{P.MANAGED_SHEET}'" in tab
        assert f"if (saved.version !== {P.STORE_STATE_VERSION}) return" in tab

    def test_host_really_mounts_the_soe_disclosure_tab(self) -> None:
        """渲染层必须有**宿主**：G7 主入口真的分发到国企披露 Tab（不是孤立组件）。"""
        host = (
            _REPO
            / "audit-platform/frontend/src/components/workpaper/GtG7LongTermEquityMain.vue"
        ).read_text(encoding="utf-8")
        assert "<G7TabDisclosureSOE" in host
        assert "currentSheet === 'disclosureSOE'" in host
        assert "<GtOnlyOfficeSheet" in host


# ═══════════════════════════════════════════════════════════════════════════
# 6. 发布 DAG 单向 + 不借用别的 pilot 身份
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishDagIsOneWay:
    """**Validates: Requirements 6.2 / 6.14 / 12.1**"""

    def test_template_payload_has_no_self_or_forward_reference(self) -> None:
        payload = P.template_definition_payload()
        blob = json.dumps(payload, sort_keys=True)
        for forbidden in ("contract_definition_sha256", "definition_bundle_sha256"):
            assert forbidden not in blob, forbidden
        assert payload["template_sha256"] == P.TEMPLATE_SHA256
        assert payload["authority_root"] == "backend/wp_templates"

    def test_instrumentation_payload_references_template_only(self) -> None:
        payload = P.instrumentation_definition_payload()
        assert payload["template_definition_sha256"] == canonical_digest(
            P.template_definition_payload()
        )
        blob = json.dumps(payload, sort_keys=True)
        for forbidden in ("contract_definition_sha256", "definition_bundle_sha256"):
            assert forbidden not in blob, forbidden

    def test_contract_payload_references_both_and_no_bundle(self, contract: Any) -> None:
        assert contract.template_definition_sha256 == canonical_digest(
            P.template_definition_payload()
        )
        assert contract.instrumentation_definition_sha256 == canonical_digest(
            P.instrumentation_definition_payload()
        )
        blob = json.dumps(contract.canonical_payload, sort_keys=True)
        assert "definition_bundle_sha256" not in blob

    def test_authority_model_is_projection_contract_with_three_slots(self) -> None:
        payload = P.authority_model_payload()
        assert payload["authority_model"] == "projection_contract"
        assert payload["required_slots"] == ["template", "instrumentation", "contract"]
        assert payload["entry_id"] == P.PILOT_ENTRY_ID
        assert payload["pilot_class"] == P.PILOT_CLASS

    def test_pilot_does_not_reuse_another_pilot_definition_identity(self) -> None:
        """四项身份逐个与 Task 40/41/42 比对**不相等**（任务正文明令）。"""
        from app.services.workpaper_sync import pilot_d2_large_json as D2
        from app.services.workpaper_sync import pilot_h1_grouped_dynamic as H1
        from app.services.workpaper_sync import pilot_simple_checklist as B60

        mine = {
            "authority": canonical_digest(P.authority_model_payload()),
            "template": canonical_digest(P.template_definition_payload()),
            "instrumentation": canonical_digest(P.instrumentation_definition_payload()),
            "contract": P.load_pilot_contract().canonical_sha256,
        }
        for other in (B60, D2, H1):
            theirs = {
                "authority": canonical_digest(other.authority_model_payload()),
                "template": canonical_digest(other.template_definition_payload()),
                "instrumentation": canonical_digest(other.instrumentation_definition_payload()),
                "contract": other.load_pilot_contract().canonical_sha256,
            }
            for key, value in mine.items():
                assert value != theirs[key], (other.__name__, key)
            assert other.PILOT_ADAPTER_ID != P.PILOT_ADAPTER_ID
            assert other.PILOT_ENTRY_ID != P.PILOT_ENTRY_ID
            assert other.TEMPLATE_SHA256 != P.TEMPLATE_SHA256

    def test_instrumentation_declares_no_disproved_anchor(self) -> None:
        """`identity_anchors` 只能是已过 probe gate 的锚点；被证伪的两条必须在禁用表里。"""
        payload = P.instrumentation_definition_payload()
        anchors = set(payload["identity_anchors"])
        assert X.TABLE_SHEET_ANCHOR in anchors
        assert anchors & X.DISPROVED_SHEET_ANCHORS == set(), anchors
        gate = EI.ExcelIdentityCarrierGate.load()
        assert {"sheet_display_name", "sheet_id"} <= set(gate.forbidden_anchors)
        for anchor in sorted(gate.forbidden_anchors):
            with pytest.raises(EI.ForbiddenAnchorError):
                gate.assert_anchor_allowed(anchor)

    def test_publish_order_is_delegated_not_reimplemented(self) -> None:
        """源码级：本模块只编排 publisher，不自己算 digest、不自己校验 slot。"""
        body = function_body_code(Path(P.__file__), "publish_pilot_definitions")
        assert body.count("publisher.publish_definition") == 4
        assert "publisher.publish_bundle" in body
        for forbidden in ("hashlib", "canonical_json_bytes", "sha256("):
            assert forbidden not in body, forbidden


# ═══════════════════════════════════════════════════════════════════════════
# 7. 第 3 边（运行时）：真实注入产物上的 extract
# ═══════════════════════════════════════════════════════════════════════════


class TestThirdEdgeRuntimeExtract:
    """**Validates: Requirements 6.11 / 6.16 / 6.17 / 6.20** · **Property 66**"""

    def test_instrumentation_produces_all_four_carriers(
        self, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        gate = EI.ExcelIdentityCarrierGate.load()
        report = EI.verify_visible_equivalence(
            source=P.read_authoritative_template(),
            instrumented=instrumented,
            spec=P.instrumentation_spec(),
        )
        assert report["equivalent"] is True
        assert report["hidden_sheets_added"] == [GT_SYNC_SHEET_NAME]
        assert report["metadata_sheet_excluded_from_business"] is True
        inventory = EI.read_back_identity(
            instrumented=instrumented, spec=P.instrumentation_spec(), gate=gate
        )
        assert inventory["hidden_sheet"]["present"] is True
        assert inventory["excel_table"]["table_name"] == P.TABLE_NAME
        assert inventory["hidden_uuid_column"]["uuid_column_hidden"] is True
        assert inventory["hidden_uuid_column"]["row_uuid_count"] == LAST - FIRST + 1
        # sheet 解析候选只剩 Table 关联一条（被证伪的两条结构上不可达）。
        assert set(
            inventory["hidden_uuid_column"]["sheet_resolution_candidates"]
        ) == {"table_sheet"}
        assert set(inventory["defined_name"]["names"]) == {
            f"GT_MANAGED_REGION_{P.TEMPLATE_ID}",
            f"GT_FOOTER_ANCHOR_{P.TEMPLATE_ID}",
            f"GT_SYNC_ANCHOR_{P.TEMPLATE_ID}",
            f"GT_ROW_UUID_RANGE_{P.TEMPLATE_ID}",
        }

    def test_region_is_resolved_by_the_table_sheet_association(self, region: Any) -> None:
        assert region.table_key == P.RECORD_TABLE_KEY
        assert region.sheet_name == P.MANAGED_SHEET
        assert region.table_ref == f"A{FIRST}:{P.UUID_COL}{LAST}"
        assert (region.first_row, region.last_row) == (FIRST, LAST)
        assert region.uuid_column == P.UUID_COL

    def test_baseline_extract_reads_back_every_managed_field(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        projection = base_outcome.projection
        # 100 个矩阵静态字段 + 7 列 × 5 行记录字段 = 135。
        assert len(projection.values) == EXPECTED_EDITABLE_COUNT + 7 * (LAST - FIRST + 1)
        assert base_outcome.anomalies == ()
        assert projection.row_keys == {
            P.RECORD_TABLE_KEY: tuple(uid(row) for row in range(FIRST, LAST + 1))
        }
        for metric_key, _label in P.MATRIX_METRICS:
            row = P.metric_row_for(metric_key)
            for seq in range(1, EXPECTED_DYNAMIC_COLUMN_COUNT + 1):
                key = P.stable_key_for_metric_cell(
                    metric_key, f"{P.MATRIX_TABLE_KEY}_{seq}"
                )
                value = projection.get(key)
                assert value is not None, key
                assert value.mode is FieldMode.editable
                assert value.value == 1000 + row * 10 + seq

    def test_dynamic_columns_land_on_the_measured_letters(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """把绑定右移一列 ⇒ 读到的值必须整列改变（证明绑定真的在决定列，而不是巧合）。"""
        first_metric = P.MATRIX_METRICS[0][0]
        row = P.metric_row_for(first_metric)
        key = P.stable_key_for_metric_cell(first_metric, f"{P.MATRIX_TABLE_KEY}_1")
        assert base_outcome.projection.get(key).value == 1000 + row * 10 + 1

    def test_shifted_binding_reads_a_different_column(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        shifted = dict(P.dynamic_column_binding_for(P.RENDER_SLOT_DEFAULT_NAMES))
        shifted[f"{P.MATRIX_TABLE_KEY}_1"] = "D"
        shifted[f"{P.MATRIX_TABLE_KEY}_2"] = "C"
        outcome = extract(
            base_path, definitions, make_binding(
                dynamic_column_columns={P.MATRIX_TABLE_KEY: shifted}
            )
        )
        first_metric = P.MATRIX_METRICS[0][0]
        row = P.metric_row_for(first_metric)
        key1 = P.stable_key_for_metric_cell(first_metric, f"{P.MATRIX_TABLE_KEY}_1")
        key2 = P.stable_key_for_metric_cell(first_metric, f"{P.MATRIX_TABLE_KEY}_2")
        assert outcome.projection.get(key1).value == 1000 + row * 10 + 2
        assert outcome.projection.get(key2).value == 1000 + row * 10 + 1

    def test_binding_outside_the_table_span_fails_closed(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        outside = dict(P.dynamic_column_binding_for(P.RENDER_SLOT_DEFAULT_NAMES))
        outside[f"{P.MATRIX_TABLE_KEY}_1"] = "Z"
        with pytest.raises(X.ManagedRegionResolutionError, match="列跨度之外"):
            extract(
                base_path,
                definitions,
                make_binding(dynamic_column_columns={P.MATRIX_TABLE_KEY: outside}),
            )

    def test_formula_columns_are_read_with_their_formula_text(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        inventory = base_outcome.formula_inventory
        assert len(inventory) == EXPECTED_RECORD_FORMULA_CELLS, len(inventory)
        for offset in range(LAST - FIRST + 1):
            row = FIRST + offset
            for column_key, column, mode, *_rest in P.RECORD_COLUMNS:
                if mode != "formula":
                    continue
                key = P.stable_key_for_record_column(column_key, uid(row))
                assert key in inventory, key
                assert inventory[key] == P.RECORD_FORMULA_TEMPLATE.format(
                    col=column, src=P.RECORD_FORMULA_SOURCE_FIRST_ROW + offset
                )

    def test_protected_field_report_is_not_an_empty_set(
        self, base_outcome: X.ExcelExtractOutcome, contract: Any
    ) -> None:
        report = X.verify_formula_regions(
            base_outcome.protected_findings,
            declared_protected_keys=contract.protected_field_keys(),
        )
        assert report.intact is True
        assert len(report.inspected_keys) == EXPECTED_PROTECTED_COUNT

    def test_unmanaged_region_coverage_is_not_empty(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        coverage = dict(base_outcome.unmanaged.coverage)
        assert set(coverage) == {
            "managed_sheet_unmanaged_cells",
            "managed_sheet_structure",
            "shared_strings_prefix",
            "other_sheet_parts",
            "protected_parts",
            "workbook_and_styles",
            "relationships",
            "other_parts",
        }
        positive = {name: count for name, count in coverage.items() if count > 0}
        assert len(positive) == 7, coverage
        assert coverage["shared_strings_prefix"] == 0
        assert coverage["other_sheet_parts"] == EXPECTED_SHEET_COUNT - 1
        assert base_outcome.unmanaged.part_count > 0

    def test_shared_strings_zero_is_a_workbook_fact_not_an_empty_judgement(
        self, base_path: Path
    ) -> None:
        """`shared_strings_prefix = 0` 的**专门事实判据**：本工作簿没有 sharedStrings.xml。"""
        with zipfile.ZipFile(base_path) as zf:
            names = set(zf.namelist())
        assert "xl/sharedStrings.xml" not in names
        # 而 inline string 是真实存在的（否则「没有 sharedStrings」会是空表的副作用）。
        part = sheet_part_of(base_path.read_bytes(), P.MANAGED_SHEET)
        with zipfile.ZipFile(base_path) as zf:
            xml = zf.read(part).decode("utf-8")
        assert 't="inlineStr"' in xml
        assert len(re.findall(r"&#\d+;", xml)) > 1000

    def test_metadata_sheet_is_excluded_from_business_enumeration(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        inventory = base_outcome.identity_inventory
        assert inventory.excluded_from_business_enumeration is True
        assert GT_SYNC_SHEET_NAME not in inventory.business_sheets
        assert len(inventory.business_sheets) == EXPECTED_SHEET_COUNT
        assert P.MANAGED_SHEET in inventory.business_sheets

    def test_metadata_sheet_leak_fails_closed(self) -> None:
        from app.services.workpaper_sync.excel_entry_gate import (
            MetadataSheetLeakError,
            assert_metadata_sheet_excluded,
        )

        assert_metadata_sheet_excluded([P.MANAGED_SHEET], where="task43")
        with pytest.raises(MetadataSheetLeakError, match="第 1 项"):
            assert_metadata_sheet_excluded(
                [P.MANAGED_SHEET, GT_SYNC_SHEET_NAME], where="task43"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 8. Property 28：immutable definition 漂移 fail closed（在真实契约上跑）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty28DefinitionDriftFailsClosed:
    """**Validates: Requirements 6.10** · **Property 28**

    四种漂移各打出**不同**的异常类型 —— 共用一个错误码会让较早分支永久不可达
    （本 spec 已实测 3 次的形态）。判据一律**真跑一次** engine 入口，不看源码字符串。
    """

    def test_baseline_passes_the_engine_entry_gate(
        self, definitions: FrozenEntryDefinitions
    ) -> None:
        X.assert_engine_entry_definitions(definitions)

    def test_contract_slot_digest_drift_fails_closed(
        self, contract: Any, base_bytes: bytes
    ) -> None:
        """bundle 的 contract slot digest 与磁盘契约不符 ⇒ `StaleAdapterError`。"""
        bad = make_bundle(
            contract,
            slots={
                BundleSlot.contract: BundleSlotSpec(
                    BundleSlot.contract, "definition", f"definition:{uuid.uuid4()}", _d("other")
                )
            },
        )
        drifted = make_definitions(contract, base_bytes, bundle=bad)
        with pytest.raises(RG.StaleAdapterError):
            X.assert_engine_entry_definitions(drifted)

    def test_template_slot_digest_drift_fails_closed(
        self, contract: Any, base_bytes: bytes
    ) -> None:
        """template slot 漂移 ⇒ `ContractDriftError`（单向引用断裂，与 contract slot 分型）。"""
        from app.services.workpaper_sync.contracts import ContractDriftError

        bad = make_bundle(
            contract,
            slots={
                BundleSlot.template: BundleSlotSpec(
                    BundleSlot.template, "definition", f"definition:{uuid.uuid4()}", _d("t2")
                )
            },
        )
        drifted = make_definitions(contract, base_bytes, bundle=bad)
        with pytest.raises(ContractDriftError, match="template_definition_sha256"):
            X.assert_engine_entry_definitions(drifted)

    def test_instrumentation_slot_digest_drift_fails_closed(
        self, contract: Any, base_bytes: bytes
    ) -> None:
        from app.services.workpaper_sync.contracts import ContractDriftError

        bad = make_bundle(
            contract,
            slots={
                BundleSlot.instrumentation: BundleSlotSpec(
                    BundleSlot.instrumentation,
                    "definition",
                    f"definition:{uuid.uuid4()}",
                    _d("i2"),
                )
            },
        )
        drifted = make_definitions(contract, base_bytes, bundle=bad)
        with pytest.raises(ContractDriftError, match="instrumentation_definition_sha256"):
            X.assert_engine_entry_definitions(drifted)

    def test_typed_null_marker_in_the_contract_slot_fails_closed(
        self, contract: Any, base_bytes: bytes
    ) -> None:
        """`projection_contract` 的 contract slot 用 typed null marker ⇒ `BundleIntegrityError`。

        🔴 顺序即判据：`assert_bundle_usable` 在 `assert_authority_model_contract_pairing`
        之前，所以 marker 冒充 contract 由前者抓走。这不是"错误码不够细"，而是两条判据各管
        一件事 —— 下面 `test_authority_model_mismatch_is_its_own_kind` 证明后者仍可达。
        """
        bad = make_bundle(
            contract,
            slots={
                BundleSlot.contract: BundleSlotSpec(
                    BundleSlot.contract, "contract:none:v1", "marker:contract:none:v1", _d("m")
                )
            },
        )
        drifted = make_definitions(contract, base_bytes, bundle=bad)
        with pytest.raises(RG.BundleIntegrityError, match="approved definition child"):
            X.assert_engine_entry_definitions(drifted)

    def test_authority_model_mismatch_is_its_own_kind(
        self, contract: Any, base_bytes: bytes
    ) -> None:
        """custom/opaque authority model + 带 contract ⇒ `AuthorityModelMismatchError`。"""
        bad = make_bundle(
            contract,
            authority_model=AuthorityModel.custom_authoritative_ooxml,
            slots={
                BundleSlot.contract: BundleSlotSpec(
                    BundleSlot.contract, "contract:none:v1", "marker:contract:none:v1", _d("m")
                ),
                BundleSlot.instrumentation: BundleSlotSpec(
                    BundleSlot.instrumentation,
                    "instrumentation:none:v1",
                    "marker:instrumentation:none:v1",
                    _d("m2"),
                ),
            },
        )
        drifted = make_definitions(contract, base_bytes, bundle=bad)
        with pytest.raises(RG.AuthorityModelMismatchError):
            X.assert_engine_entry_definitions(drifted)

    def test_unapproved_bundle_fails_closed(self, contract: Any, base_bytes: bytes) -> None:
        bad = make_bundle(contract, state=DefinitionState.candidate)
        drifted = make_definitions(contract, base_bytes, bundle=bad)
        with pytest.raises(RG.BundleIntegrityError):
            X.assert_engine_entry_definitions(drifted)

    def test_structure_inventory_drift_points_at_the_first_offender(
        self, contract: Any
    ) -> None:
        """结构清册漂移 ⇒ `ContractDriftError` 且指出**首个**位置（Property 28 的定位要求）。"""
        from app.services.workpaper_sync.contracts import (
            ContractDriftError,
            assert_no_structure_drift,
            first_structure_drift,
        )

        declared = list(declared_structure_inventory(contract))
        assert len(declared) == EXPECTED_FIELD_COUNT, len(declared)
        assert_no_structure_drift(contract, declared)
        moved = list(declared)
        sheet_key, table_key, stable_key, locator = moved[0]
        moved[0] = (sheet_key, table_key, stable_key, locator.replace(":", ":X", 1))
        drift = first_structure_drift(contract, moved)
        assert drift == declared[0], (drift, declared[0])
        with pytest.raises(ContractDriftError, match="结构漂移"):
            assert_no_structure_drift(contract, moved)

    def test_structure_inventory_locators_are_the_real_geometry(self, contract: Any) -> None:
        """清册里的 locator 必须是「列 + 行来源」，静态块带真实静态行号。"""
        declared = dict(
            ((table_key, stable_key), locator)
            for _sheet, table_key, stable_key, locator in declared_structure_inventory(
                contract
            )
        )
        first_metric = P.MATRIX_METRICS[0][0]
        key = P.stable_key_for_metric_cell(first_metric, f"{P.MATRIX_TABLE_KEY}_1")
        assert declared[(P.MATRIX_TABLE_KEY, key)] == (
            f"C:static:{P.metric_row_for(first_metric)}"
        )
        record_key = P.stable_key_for_record_column("name")
        assert declared[(P.RECORD_TABLE_KEY, record_key)] == "B:row_identity"

    def test_missing_structure_row_is_also_drift(self, contract: Any) -> None:
        from app.services.workpaper_sync.contracts import first_structure_drift

        declared = list(declared_structure_inventory(contract))
        assert first_structure_drift(contract, declared[:-1]) is not None

    def test_failure_kinds_are_reachable_and_mutually_distinct(
        self, contract: Any, base_bytes: bytes
    ) -> None:
        """五类漂移各真触发一次，断言异常类型集合基数 == 4（三类共用 StaleAdapterError）。"""
        from app.services.workpaper_sync.contracts import (
            ContractDriftError,
            assert_no_structure_drift,
        )

        kinds: set[type[Exception]] = set()
        bundles = [
            # contract slot digest 与磁盘契约不符 ⇒ RG-10 StaleAdapterError
            make_bundle(
                contract,
                slots={
                    BundleSlot.contract: BundleSlotSpec(
                        BundleSlot.contract, "definition", f"definition:{uuid.uuid4()}", _d("c")
                    )
                },
            ),
            # template / instrumentation slot 漂移 ⇒ ContractDriftError
            make_bundle(
                contract,
                slots={
                    BundleSlot.template: BundleSlotSpec(
                        BundleSlot.template, "definition", f"definition:{uuid.uuid4()}", _d("t")
                    )
                },
            ),
            # marker 冒充 contract / bundle 未 approved ⇒ BundleIntegrityError
            make_bundle(
                contract,
                slots={
                    BundleSlot.contract: BundleSlotSpec(
                        BundleSlot.contract,
                        "contract:none:v1",
                        "marker:contract:none:v1",
                        _d("m"),
                    )
                },
            ),
            make_bundle(contract, state=DefinitionState.candidate),
            # authority model 与 contract 组合矛盾 ⇒ AuthorityModelMismatchError
            make_bundle(
                contract,
                authority_model=AuthorityModel.custom_authoritative_ooxml,
                slots={
                    BundleSlot.contract: BundleSlotSpec(
                        BundleSlot.contract,
                        "contract:none:v1",
                        "marker:contract:none:v1",
                        _d("m"),
                    ),
                    BundleSlot.instrumentation: BundleSlotSpec(
                        BundleSlot.instrumentation,
                        "instrumentation:none:v1",
                        "marker:instrumentation:none:v1",
                        _d("m2"),
                    ),
                },
            ),
        ]
        for bad in bundles:
            drifted = make_definitions(contract, base_bytes, bundle=bad)
            with pytest.raises(Exception) as excinfo:  # noqa: PT011 - 分型就是被测项
                X.assert_engine_entry_definitions(drifted)
            kinds.add(type(excinfo.value))
        declared = list(declared_structure_inventory(contract))
        with pytest.raises(ContractDriftError):
            assert_no_structure_drift(contract, declared[:-1])
        kinds.add(ContractDriftError)
        assert kinds == {
            RG.StaleAdapterError,
            RG.AuthorityModelMismatchError,
            RG.BundleIntegrityError,
            ContractDriftError,
        }, kinds
        assert len(kinds) == 4

    def test_drift_gate_runs_before_any_byte_is_written(self, contract: Any) -> None:
        """顺序不可交换：frozen 身份门在 substrate 准入之前（`extract` / `materialize` 两处）。"""
        for name in ("extract_projection",):
            body = function_body_code(Path(X.__file__), name)
            assert body.index("assert_engine_entry_definitions") < body.index(
                "assert_substrate_usable"
            ), name
        body = function_body_code(Path(M.__file__), "materialize_projection")
        assert body.index("assert_engine_entry_definitions") < body.index(
            "assert_substrate_usable"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 9. Property 66：结构操作后 identity 保留（真实模板 + 真实注入产物）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty66StructuralOperations:
    """**Validates: Requirements 6.15 / 6.16** · **Property 66**"""

    def test_reorder_keeps_values_attached_to_identity(
        self,
        base_bytes: bytes,
        sheet_part: str,
        workdir: Path,
        definitions: FrozenEntryDefinitions,
        binding: X.ExcelIdentityBinding,
        base_outcome: X.ExcelExtractOutcome,
    ) -> None:
        """把两行的 UUID 互换（= OO 排序）⇒ 值随 identity 走，不随行号走。"""
        swapped = patch_cells(
            base_bytes,
            sheet_part,
            {
                f"{P.UUID_COL}{FIRST}": uid(FIRST + 1),
                f"{P.UUID_COL}{FIRST + 1}": uid(FIRST),
            },
        )
        assert_uuid_cells_are_unique(swapped, sheet_part)
        before_xml = _read_entries(base_bytes)[sheet_part].decode("utf-8")
        after_xml = _read_entries(swapped)[sheet_part].decode("utf-8")
        assert before_xml != after_xml, "UUID 互换没改到字节 —— fixture 静默失效"
        path = workdir / "reordered.xlsx"
        path.write_bytes(swapped)
        outcome = extract(path, definitions, binding)
        assert outcome.anomalies == ()
        before = base_outcome.projection
        after = outcome.projection
        key_a = P.stable_key_for_record_column("name", uid(FIRST))
        key_b = P.stable_key_for_record_column("name", uid(FIRST + 1))
        assert after.get(key_a).value == before.get(key_b).value
        assert after.get(key_b).value == before.get(key_a).value

    def test_lost_row_identity_is_a_retention_failure(
        self,
        base_bytes: bytes,
        sheet_part: str,
        workdir: Path,
        contract: Any,
        binding: X.ExcelIdentityBinding,
    ) -> None:
        """UUID 被清掉 ⇒ 保留门打红（Property 66 的核心）。"""
        cleared = patch_cells(base_bytes, sheet_part, {f"{P.UUID_COL}{FIRST}": None})
        assert uuid_cell_occurrences(cleared, sheet_part)[f"{P.UUID_COL}{FIRST}"] == 0, (
            "UUID 格没被清掉 —— fixture 静默失效，保留门判据会变成空转"
        )
        path = workdir / "lost.xlsx"
        path.write_bytes(cleared)
        definitions = make_definitions(contract, base_bytes)
        with pytest.raises(X.IdentityRetentionError):
            extract(path, definitions, binding)

    def test_new_row_gets_minted_identity_never_reusing_a_deleted_one(
        self,
        base_bytes: bytes,
        sheet_part: str,
        workdir: Path,
        contract: Any,
        binding: X.ExcelIdentityBinding,
    ) -> None:
        """在受管区域**末尾追加**一行（空 UUID）⇒ 分配新 ID，且不复用已删除的。"""
        grown = add_row(
            base_bytes,
            sheet_part,
            row=LAST + 1,
            cells={f"B{LAST + 1}": "新增行", f"{P.UUID_COL}{LAST + 1}": None},
        )
        assert_uuid_cells_are_unique(grown, sheet_part)
        assert uuid_cell_occurrences(grown, sheet_part)[f"{P.UUID_COL}{LAST + 1}"] == 0
        path = workdir / "appended.xlsx"
        path.write_bytes(grown)
        definitions = make_definitions(contract, grown)
        # 已删除的 identity 进 tombstone —— minted 值不得与它撞（Requirement 6.15 后半句）。
        tombstoned = uid(FIRST)
        outcome = extract(
            path,
            definitions,
            make_binding(
                tombstoned_row_keys=frozenset({tombstoned}),
                dynamic_column_columns=binding.dynamic_column_columns,
            ),
        )
        minted = dict(outcome.scan.minted_by_row)
        assert set(minted) == {LAST + 1}, minted
        assert minted[LAST + 1] not in {uid(row) for row in range(FIRST, LAST + 1)}
        assert minted[LAST + 1] != tombstoned

    def test_copied_row_duplicate_identity_is_a_structural_conflict(
        self,
        base_bytes: bytes,
        sheet_part: str,
        workdir: Path,
        contract: Any,
        binding: X.ExcelIdentityBinding,
    ) -> None:
        duplicated = add_row(
            base_bytes,
            sheet_part,
            row=LAST + 1,
            cells={f"{P.UUID_COL}{LAST + 1}": uid(FIRST)},
        )
        path = workdir / "copied.xlsx"
        path.write_bytes(duplicated)
        definitions = make_definitions(contract, duplicated)
        outcome = extract(path, definitions, binding)
        kinds = {anomaly.kind.value for anomaly in outcome.anomalies}
        assert "duplicate_row_identity" in kinds, kinds

    def test_footer_anchor_drift_is_detected(
        self,
        base_bytes: bytes,
        sheet_part: str,
        contract: Any,
    ) -> None:
        """footer 标记被推走 ⇒ `FooterAnchorDriftError`（marker 通过数字字符引用解码定位）。"""
        entries = _read_entries(base_bytes)
        runtime = X.read_runtime_binding_pairs(zipfile.ZipFile(__import__("io").BytesIO(base_bytes)))
        assert runtime["GT_FOOTER_ROW"] == str(P.RECORD_FOOTER_ROW)
        row = M.assert_footer_anchor_stable(
            entries=entries,
            sheet_part=sheet_part,
            contract=contract,
            runtime_binding=runtime,
        )
        assert row == P.RECORD_FOOTER_ROW
        with pytest.raises(M.FooterAnchorDriftError, match="已下移"):
            M.assert_footer_anchor_stable(
                entries=entries,
                sheet_part=sheet_part,
                contract=contract,
                runtime_binding={**runtime, "GT_FOOTER_ROW": str(P.RECORD_FOOTER_ROW + 1)},
            )

    def test_footer_marker_is_found_through_the_numeric_reference_decoder(
        self, base_bytes: bytes, sheet_part: str
    ) -> None:
        """marker 在 sheet XML 里是数字字符引用 ⇒ 定位必须过解码器（Task 42 修的缺陷 ③）。"""
        xml = _read_entries(base_bytes)[sheet_part].decode("utf-8")
        assert P.FOOTER_MARKER not in xml, "marker 竟然是明文 —— 解码判据会变成空转"
        assert f'<c r="A{P.RECORD_FOOTER_ROW}"' in xml
        found = M._find_marker_row(xml, column="A", marker=P.FOOTER_MARKER, shared=[])
        assert found == P.RECORD_FOOTER_ROW


class TestFooterHasNoTotalFormula:
    """**Validates: Requirements 6.3**（footer 无合计公式是**源侧事实**，不是判据空转）"""

    def test_footer_row_carries_no_formula_in_the_source(self, worksheet: Any) -> None:
        for column in "ABCDEFGHIJKLM":
            value = worksheet[f"{column}{P.RECORD_FOOTER_ROW}"].value
            assert not (isinstance(value, str) and value.startswith("=")), column

    def test_footer_formula_gate_returns_an_empty_checked_list(
        self, base_bytes: bytes, sheet_part: str, region: Any
    ) -> None:
        checked = M.assert_footer_formula_covers_managed_rows(
            entries=_read_entries(base_bytes),
            sheet_part=sheet_part,
            footer_row=P.RECORD_FOOTER_ROW,
            region=region,
        )
        assert checked == (), checked

    def test_the_gate_really_bites_when_a_total_formula_exists(
        self, base_bytes: bytes, sheet_part: str, region: Any
    ) -> None:
        """反向自检：给 footer 塞一条区间不足的合计公式 ⇒ 必须打红（证明判据不是恒真）。"""
        entries = _read_entries(base_bytes)
        xml = entries[sheet_part].decode("utf-8")
        patched, count = re.subn(
            r'<c r="B' + str(P.RECORD_FOOTER_ROW) + r'"([^>]*)></c>',
            rf'<c r="B{P.RECORD_FOOTER_ROW}"\g<1>><f>SUM(B{FIRST}:B{LAST - 1})</f>'
            f"<v>0</v></c>",
            xml,
            count=1,
        )
        assert count == 1, "footer 行的 B 列形态已变，反向自检失效"
        entries[sheet_part] = patched.encode("utf-8")
        with pytest.raises(M.FooterFormulaRangeError, match="合计漏算"):
            M.assert_footer_formula_covers_managed_rows(
                entries=entries,
                sheet_part=sheet_part,
                footer_row=P.RECORD_FOOTER_ROW,
                region=region,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 10. HTML store 拆分（第 2 边到运行时的桥）
# ═══════════════════════════════════════════════════════════════════════════


class TestStorePayloadSplit:
    """**Validates: Requirements 6.4 / 6.7 / 6.12**"""

    def test_split_yields_one_field_per_metric_per_dynamic_column(
        self, contract: Any
    ) -> None:
        projection = P.build_store_projection(store_state(), contract=contract)
        assert len(projection.values) == EXPECTED_EDITABLE_COUNT
        assert projection.row_keys == {}
        assert projection.contract_id == P.PILOT_ADAPTER_ID

    def test_split_accepts_text_bytes_and_parsed_inputs_alike(self, contract: Any) -> None:
        state = store_state()
        text = json.dumps(state, ensure_ascii=False)
        results = [
            P.build_store_projection(payload, contract=contract)
            for payload in (state, text, text.encode("utf-8"))
        ]
        keys = [sorted(item.values) for item in results]
        assert keys[0] == keys[1] == keys[2]

    def test_entity_count_drives_the_column_count(self, contract: Any) -> None:
        """删到 3 家 ⇒ 只产 6 列（不补默认名、不写死 10）。"""
        state = store_state(entity_names=("甲", "乙", "丙"))
        projection = P.build_store_projection(state, contract=contract)
        assert len(projection.values) == len(P.MATRIX_METRICS) * 3 * len(
            P.RENDER_SUB_COLUMNS
        )
        keys = {key.rsplit("/", 1)[1] for key in projection.values}
        assert keys == set(P.dynamic_column_keys_for_entities(("甲", "乙", "丙")))

    def test_more_entities_than_the_contract_declares_fail_closed(
        self, contract: Any
    ) -> None:
        """多出的列在契约里没有字段 ⇒ 抛，而不是静默丢掉某家公司的整列披露数据。"""
        state = store_state(entity_names=P.RENDER_SLOT_DEFAULT_NAMES + ("公司6",))
        with pytest.raises(Exception) as excinfo:  # noqa: PT011
            P.build_store_projection(state, contract=contract)
        assert "minority_financials_11" in str(excinfo.value)

    def test_entities_missing_fails_closed(self, contract: Any) -> None:
        for broken in ({}, {P.RENDER_SLOT: []}, {P.RENDER_SLOT: ["", "x"]}):
            state = store_state()
            state["entitySlots"] = broken
            with pytest.raises(P.StorePayloadError):
                P.iter_store_entities(state)

    def test_unknown_metric_id_fails_closed(self, contract: Any) -> None:
        state = store_state()
        state["tables"][P.RENDER_MATRIX_TABLE_ID][0]["id"] = "minority-fs-42"
        with pytest.raises(P.StorePayloadError, match="不在受管 metric 集合"):
            list(P.iter_store_metric_rows(state))

    def test_duplicate_metric_id_fails_closed(self) -> None:
        state = store_state()
        rows = state["tables"][P.RENDER_MATRIX_TABLE_ID]
        rows[1]["id"] = rows[0]["id"]
        with pytest.raises(P.StorePayloadError, match="重复 metric id"):
            list(P.iter_store_metric_rows(state))

    def test_non_object_payload_fails_closed(self) -> None:
        with pytest.raises(P.StorePayloadError, match="必须是对象"):
            list(P.iter_store_metric_rows("[]"))

    def test_wrong_state_version_fails_closed(self) -> None:
        state = store_state(version=1)
        with pytest.raises(P.StorePayloadError, match="state version"):
            list(P.iter_store_metric_rows(state))

    def test_invalid_json_fails_closed(self) -> None:
        with pytest.raises(P.StorePayloadError, match="不是合法 JSON"):
            list(P.iter_store_metric_rows("{not json"))

    def test_non_object_row_fails_closed(self) -> None:
        state = store_state()
        state["tables"][P.RENDER_MATRIX_TABLE_ID][0] = ["x"]
        with pytest.raises(P.StorePayloadError, match="不是对象"):
            list(P.iter_store_metric_rows(state))

    def test_failure_kinds_are_reachable_and_mutually_distinct(self) -> None:
        """六个分支各真触发一次；三类异常互不相同（共用错误码会让较早分支永久不可达）。"""
        broken_metric = store_state()
        broken_metric["tables"][P.RENDER_MATRIX_TABLE_ID][0]["id"] = "nope"
        duplicated = store_state()
        duplicated["tables"][P.RENDER_MATRIX_TABLE_ID][1]["id"] = duplicated["tables"][
            P.RENDER_MATRIX_TABLE_ID
        ][0]["id"]
        no_slots = store_state()
        no_slots["entitySlots"] = {}
        cases: list[tuple[Any, str, Any]] = [
            ("{not json", "不是合法 JSON", P.iter_store_metric_rows),
            ("[]", "必须是对象", P.iter_store_metric_rows),
            (store_state(version=1), "state version", P.iter_store_metric_rows),
            (broken_metric, "不在受管 metric 集合", P.iter_store_metric_rows),
            (duplicated, "重复 metric id", P.iter_store_metric_rows),
            (no_slots, "缺失或为空", P.iter_store_entities),
        ]
        seen: set[str] = set()
        for payload, fragment, call in cases:
            with pytest.raises(P.StorePayloadError) as excinfo:
                result = call(payload)
                list(result) if hasattr(result, "__iter__") else result
            message = str(excinfo.value)
            assert fragment in message, (fragment, message)
            seen.add(fragment)
        assert len(seen) == 6, sorted(seen)
        assert P.StorePayloadError.error_code != P.PilotSelectionError.error_code
        assert P.StorePayloadError.error_code != P.RenderLayerError.error_code
        assert P.PilotSelectionError.error_code != P.RenderLayerError.error_code

    def test_split_uses_the_contract_as_the_spec_source(self, contract: Any) -> None:
        """`value_type` / `mode` 从**契约**取（写错一个键会立刻炸，而不是静默产出野字段）。"""
        projection = P.build_store_projection(store_state(), contract=contract)
        for key, value in projection.values.items():
            spec = contract.field_by_stable_key(key)
            assert value.value_type is spec.value_type
            assert value.mode is spec.mode

    def test_row_and_field_budgets_are_wired_into_the_split(self, contract: Any) -> None:
        with pytest.raises(BudgetExceededError):
            P.build_store_projection(
                store_state(), contract=contract, limits=scaled_limits(max_projection_fields=5)
            )

    def test_module_declares_no_budget_threshold(self) -> None:
        body = function_body_code(Path(P.__file__), "build_store_projection")
        assert "StreamingProjectionBudget" in body
        assert not re.search(r"\b\d{3,}\b", body), body


# ═══════════════════════════════════════════════════════════════════════════
# 11. Property 落点：oracle 必须真在 required set 里
# ═══════════════════════════════════════════════════════════════════════════

#: Property → 该 Property 的 oracle 落在本 entry required set 的哪几条场景上。
#:
#: 🔴 **P22 为什么不落 `dynamic_column_stable_keys`**：那条场景（AC 6.4 自己的场景）对任何
#: xlsx entry 结构性不可达 —— `evidence.derive_for_manifest_entry` 只按
#: `scenario_profile.mount_cardinality == "dynamic"` 追加它，而该字段量的是**前端宿主挂载
#: 基数**，全 manifest 186 条里只有 1 条 dynamic 且是 docx。见
#: :data:`P.UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY`。本 pilot 因此把 P22
#: 落在 required set 里**真实存在**的 merge 家族场景上，并在**真实契约形态**（真实 10 列
#: 绑定 + 真实重复 label）上跑 oracle，而不是为了让它进分母去改 profile。
#:
#: 🔴 **P28 为什么落 `oo_to_html` + `quarantined_rejects_application_and_engine`**：
#: 漂移门 `assert_engine_entry_definitions` 是 `extract_projection` /
#: `materialize_projection` 的**第一条**语句（`TestProperty28DefinitionDriftFailsClosed::
#: test_drift_gate_runs_before_any_byte_is_written` 用源码顺序钉住），因此两个方向的每次
#: engine 调用都过它；`quarantined_…` 那条更强 —— 它要求 substrate 被拒，而 substrate 门
#: **排在漂移门之后**，能走到那里就证明漂移门已经放行过一次（顺序不可交换）。
PROPERTY_ORACLE_LANDING: dict[str, tuple[str, ...]] = {
    "P22": ("different_field_merge", "same_field_conflict_resolve"),
    "P28": ("oo_to_html", "quarantined_rejects_application_and_engine"),
    "P49": ("identity_retention",),
    "P66": ("identity_retention",),
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

    def test_dynamic_column_scenario_is_not_in_the_required_set(self) -> None:
        """P22 之所以改落 merge 家族：`dynamic_column_stable_keys` 确实不在分母里。"""
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        required = set(
            derive_for_manifest_entry(entry, authority_model=P.AUTHORITY_MODEL).scenario_ids
        )
        assert "dynamic_column_stable_keys" not in required
        assert "dynamic_row_add_delete_reorder_copy" not in required
        # 但它们**登记**着（不是不存在）—— 这正是欠账而不是设计如此。
        assert "dynamic_column_stable_keys" in PH.SCENARIO_ORACLES
        assert "dynamic_row_add_delete_reorder_copy" in PH.SCENARIO_ORACLES

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
        """P49/P66/P28 的落点需要真实 OO ⇒ 今天只能 UNVERIFIABLE（Property 49 后半句）。"""
        offline_only = {
            "different_field_merge",
            "same_field_conflict_resolve",
            "single_participant_close",
            "quarantined_rejects_application_and_engine",
        }
        need_black_box = {
            scenario_id
            for scenarios in PROPERTY_ORACLE_LANDING.values()
            for scenario_id in scenarios
        }
        assert need_black_box - offline_only == {"identity_retention", "oo_to_html"}
        for scenario_id in sorted(need_black_box - offline_only):
            assert PH.SCENARIO_ORACLES[scenario_id].needs_black_box, scenario_id
        for scenario_id in sorted(need_black_box & offline_only):
            assert not PH.SCENARIO_ORACLES[scenario_id].needs_black_box, scenario_id

    def test_pilot_class_stays_unverifiable_until_server_recompute(self) -> None:
        assessment = PH.assess_pilot_classes()[PH.PilotClass.g7_two_level_dynamic]
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
        assert checked >= 8, checked


# ═══════════════════════════════════════════════════════════════════════════
# 12. 五条登记的上游缺口：可打红的实测事实，不是注释
# ═══════════════════════════════════════════════════════════════════════════


class TestUpstreamDebtsAreVisibleFacts:
    """**Validates: Requirements 6.3 / 6.4 / 6.5 / 12.10**"""

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

    def test_observed_dynamic_columns_is_non_empty_only_for_this_pilot(
        self, contract: Any
    ) -> None:
        """本 entry 是四类里唯一必须给出非空 `observed_dynamic_columns` 的 —— 缺口更贵的原因。"""
        from app.services.workpaper_sync.excel_entry_gate import (
            _assert_dynamic_columns_declared,
        )
        from app.services.workpaper_sync import pilot_d2_large_json as D2
        from app.services.workpaper_sync import pilot_h1_grouped_dynamic as H1
        from app.services.workpaper_sync import pilot_simple_checklist as B60

        for other in (B60, D2, H1):
            other_contract = other.load_pilot_contract()
            assert (
                _assert_dynamic_columns_declared(other_contract, {}) == {}
            ), other.__name__
        with pytest.raises(DynamicColumnIdentityError, match="未提供实测"):
            _assert_dynamic_columns_declared(contract, {})
        resolved = _assert_dynamic_columns_declared(
            contract, P.observed_dynamic_columns_for(P.RENDER_SLOT_DEFAULT_NAMES)
        )
        assert set(resolved) == {P.MATRIX_TABLE_KEY}
        assert len(resolved[P.MATRIX_TABLE_KEY]) == EXPECTED_DYNAMIC_COLUMN_COUNT

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

    def test_this_entry_really_has_dynamic_columns(self, contract: Any) -> None:
        """欠账之所以是缺口：本 entry 的契约**确实**声明了动态列（不是它不需要）。"""
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.MATRIX_TABLE_KEY
        )
        assert table.dynamic_columns is not None
        assert table.dynamic_columns.identity == "{slot}_{seq}"
        assert table.header_rows == 2

    def test_matrix_mode_is_per_column_debt_is_a_measured_schema_limit(
        self, workbook: Any, contract: Any
    ) -> None:
        """三段链条：同构表按行分布公式 / mode 在 field 上 / 读写两侧都按 field 判。"""
        # ① 上市侧同构表的公式按**行**分布：两行是 SUM、其余是跨 sheet 引用。
        sheet = workbook["附注披露信息（上市公司）"]
        sum_rows = {
            row
            for row in range(171, 188)
            if str(sheet[f"B{row}"].value or "").startswith("=SUM(")
        }
        assert sum_rows == {173, 176}, sum_rows
        cross_rows = {
            row
            for row in range(171, 188)
            if str(sheet[f"B{row}"].value or "").startswith("='")
        }
        assert len(cross_rows) == 15, sorted(cross_rows)
        assert sum_rows & cross_rows == set()
        # ② mode 在 field 上，且行域字段的 row_from 只能是 row_identity。
        contracts_source = Path(
            __import__("app.services.workpaper_sync.contracts", fromlist=["x"]).__file__
        ).read_text(encoding="utf-8")
        assert "行域字段的 cell.row_from 不得写死行号" in contracts_source
        # ③ 读写两侧都按 field.mode 判。
        assert "declared_protected_keys=contract.protected_field_keys()" in Path(
            X.__file__
        ).read_text(encoding="utf-8").replace("\n", "").replace(" ", "") or (
            "contract.protected_field_keys()" in Path(X.__file__).read_text(encoding="utf-8")
        )
        assert "if spec.mode is FieldMode.formula:" in Path(M.__file__).read_text(
            encoding="utf-8"
        )
        # ④ 本 pilot 的规避办法：矩阵是静态块，mode 精确到格。
        matrix = next(
            t for t in contract.sheets[0].tables if t.table_key == P.MATRIX_TABLE_KEY
        )
        assert matrix.row_identity is None
        assert all(spec.cell.static_row is not None for spec in matrix.fields)
        note = P.UPSTREAM_DEBT_TWO_LEVEL_MATRIX_MODE_IS_PER_COLUMN
        assert "owner" in note and "静态块" in note

    def test_key_space_split_debt_is_a_measured_fact(self) -> None:
        """契约只能 `{slot}_{seq}`（schema 硬限），渲染层带子列时是三段 —— 两侧都实测。"""
        from app.services.workpaper_sync.contracts import (
            ContractSchemaError,
            DYNAMIC_COLUMN_IDENTITY_TEMPLATE,
        )

        assert DYNAMIC_COLUMN_IDENTITY_TEMPLATE == "{slot}_{seq}"
        payload = json.loads(P.contract_file_path().read_text(encoding="utf-8"))
        table = next(
            t
            for t in payload["sheets"][0]["tables"]
            if t["table_key"] == P.MATRIX_TABLE_KEY
        )
        table["dynamic_columns"]["identity"] = "{slot}_{seq}_{sub}"
        with pytest.raises(ContractSchemaError, match="必须恰为"):
            parse_contract(payload, adapter_id=P.PILOT_ADAPTER_ID)
        source = (_REPO / P.RENDER_SLOT_COLUMNS_RELATIVE_PATH).read_text(encoding="utf-8")
        assert "key: `${slot}_${seq}_${s.key}`," in source
        note = P.UPSTREAM_DEBT_SLOT_SUBCOLUMN_KEY_SPACE_SPLIT
        assert "owner" in note and "sub_columns" in note

    def test_positional_render_row_id_debt_is_a_measured_fact(self) -> None:
        """渲染层的行 id 是位置派生的（`${prefix}-${index + 1}`）—— 源码实测。"""
        source = (_REPO / P.RENDER_MODEL_RELATIVE_PATH).read_text(encoding="utf-8")
        assert source.count("id: `${prefix}-${index + 1}`") == 2, source.count(
            "id: `${prefix}-${index + 1}`"
        )
        # 本 pilot 因此不用它当记录表行身份：记录表走注入的 rowUuid。
        contract = P.load_pilot_contract()
        record = next(
            t for t in contract.sheets[0].tables if t.table_key == P.RECORD_TABLE_KEY
        )
        assert record.row_identity is not None
        assert record.row_identity.json_pointer.endswith("/rowUuid")
        # 且记录表没有 editable 字段 ⇒ HTML 侧不写它，位置派生 id 不进任何持久化身份。
        assert all(spec.is_protected for spec in record.fields)
        note = P.UPSTREAM_DEBT_RENDER_ROW_IDS_ARE_POSITIONAL
        assert "owner" in note and "AC 6.5" in note

    def test_every_exported_debt_constant_is_registered_and_distinct(self) -> None:
        """本模块导出的**每一条** `UPSTREAM_DEBT_*` 都必须独立可辨、带 owner。

        🔴 判据取 `__all__` 而不是手写清单：手写清单会在新增第 N+1 条时静默漏掉它，
        「合成一条会让其余几条的撤销条件无处可查」这条判据就退化成只管旧的那几条。
        """
        names = [name for name in P.__all__ if name.startswith("UPSTREAM_DEBT_")]
        # Task 75 结清并删除了 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER` ⇒ 6 → 5。
        assert len(names) == 5, names
        assert "UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER" not in names
        notes = {getattr(P, name) for name in names}
        assert len(notes) == len(names), names
        for name in names:
            note = getattr(P, name)
            assert note.startswith("Task 43 欠账"), (name, note[:40])
            assert "owner" in note, (name, note[:40])


# ═══════════════════════════════════════════════════════════════════════════
# 13. 本任务修掉的生产缺陷 + Task 42 三条形态仍成立（反向自检）
# ═══════════════════════════════════════════════════════════════════════════


class TestUuidCellDuplicationDefectIsFixed:
    """**Validates: Requirements 6.13 / 6.17**

    🔴 **本任务修掉的生产缺陷**：`excel_instrumentation._add_uuid_cells` 原来无条件在
    `</row>` 前追加 UUID 格，而本 sheet 的 `N79..N83` 在模板里已有「有样式、无值」的格 ⇒
    同一行出现两个相同 `r` 的 `<c>`（非法 OOXML）。缺陷此前潜伏：Task 40/41/42 三个 entry
    选的 UUID 列在受管行上都没有既有格。首轮实测的症状是三条结构操作 fixture 静默失效
    （`patch_cells` 改到了模板那一个）。
    """

    def test_the_template_really_has_pre_existing_uuid_column_cells(
        self, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        """前提事实：源模板的 `N79..N83` 确有空格（否则本缺陷在本 entry 上不可达）。"""
        source_part = None
        with zipfile.ZipFile(__import__("io").BytesIO(P.read_authoritative_template())) as zf:
            source_part = sheet_part_of(P.read_authoritative_template(), P.MANAGED_SHEET)
            xml = zf.read(source_part).decode("utf-8")
        for row in range(FIRST, LAST + 1):
            assert re.search(rf'<c r="{P.UUID_COL}{row}"[^>]*>', xml), row

    def test_instrumented_uuid_cells_are_unique_per_row(
        self, instrumented: EI.InstrumentedWorkbook, sheet_part: str
    ) -> None:
        counts = uuid_cell_occurrences(instrumented.instrumented_bytes, sheet_part)
        for row in range(FIRST, LAST + 1):
            assert counts[f"{P.UUID_COL}{row}"] == 1, (row, counts)
        # 受管区间之外的那一行（`N84`）在模板里本来就有一个空格 —— 它**没有**被注入 UUID。
        xml = _read_entries(instrumented.instrumented_bytes)[sheet_part].decode("utf-8")
        assert counts[f"{P.UUID_COL}{LAST + 1}"] == 1, counts
        assert len(re.findall(r"GTROW-", xml)) == LAST - FIRST + 1
        assert (
            re.search(rf'<c r="{P.UUID_COL}{LAST + 1}"[^>]*>(.*?)</c>', xml).group(1) == ""
        )

    def test_old_append_only_behaviour_would_have_duplicated(
        self, sheet_part: str
    ) -> None:
        """反向自检：故意退回「无条件追加」⇒ 必须产出重复格（证明修复不是空操作）。"""
        spec = P.instrumentation_spec()
        xml = _read_entries(P.read_authoritative_template())[sheet_part].decode("utf-8")
        legacy = xml
        for row in range(FIRST, LAST + 1):
            cell = (
                f'<c r="{P.UUID_COL}{row}" t="inlineStr">'
                f"<is><t>{uid(row)}</t></is></c>"
            )
            opened = re.search(rf'<row r="{row}"(?:\s[^>]*)?>', legacy)
            assert opened, row
            close = legacy.find("</row>", opened.end())
            legacy = legacy[:close] + cell + legacy[close:]
        for row in range(FIRST, LAST + 1):
            assert len(re.findall(rf'<c r="{P.UUID_COL}{row}"(?:\s|/|>)', legacy)) == 2, row
        # 修好之后的实现在同一份 XML 上只产出一个。
        fixed = EI._add_uuid_cells(
            xml, uuid_col=P.UUID_COL, uuids={row: uid(row) for row in range(FIRST, LAST + 1)}
        )
        for row in range(FIRST, LAST + 1):
            assert len(re.findall(rf'<c r="{P.UUID_COL}{row}"(?:\s|/|>)', fixed)) == 1, row
        assert spec.uuid_col == P.UUID_COL

    def test_the_fix_is_conditional_and_leaves_other_templates_untouched(self) -> None:
        """不存在既有格时走原追加路径 ⇒ 另外那些模板的注入字节一个字节都不变。"""
        xml = (
            '<worksheet xmlns="x"><sheetData>'
            f'<row r="{FIRST}"><c r="A{FIRST}"><v>1</v></c></row>'
            "</sheetData></worksheet>"
        )
        out = EI._add_uuid_cells(xml, uuid_col=P.UUID_COL, uuids={FIRST: uid(FIRST)})
        assert out == xml.replace(
            "</row>",
            f'<c r="{P.UUID_COL}{FIRST}" t="inlineStr"><is><t>{uid(FIRST)}</t></is></c></row>',
        )


def _workbook_rels(data: bytes) -> str:
    return _read_entries(data)["xl/_rels/workbook.xml.rels"].decode("utf-8")


class TestUpstreamRelsAndNamespaceShapesStillHold:
    """**Validates: Requirements 6.16 / 9.9**

    Task 42 修掉的三条缺陷（rels 属性顺序 / per-element `xmlns:r` / 数字字符引用）在**本
    工作簿**上逐条复核 —— 它是那 10 个「由非 Excel 工具写出」的模板之一。这不是重复 Task 42
    的守卫，而是「本 entry 命中同一形态」的实证：形态一变，本 pilot 的注入产物立刻不可用。
    """

    def test_authoritative_template_writes_target_before_id(self) -> None:
        rels = _workbook_rels(P.read_authoritative_template())
        first = re.search(r"<Relationship\b[^>]*?/?>", rels)
        assert first, rels[:200]
        raw = first.group(0)
        assert raw.index("Target=") < raw.index("Id="), raw

    def test_old_id_before_target_regex_would_have_failed(self) -> None:
        """反向自检：Task 37 那条隐含「Id 在 Target 之前」的正则在本模板上必然失配。"""
        rels = _workbook_rels(P.read_authoritative_template())
        legacy = re.search(r'Id="rId1"[^>]*Target="([^"]+)"', rels)
        assert legacy is None
        assert sheet_part_of(P.read_authoritative_template(), P.MANAGED_SHEET).startswith(
            "xl/worksheets/"
        )

    def test_workbook_root_does_not_declare_the_relationship_namespace(self) -> None:
        workbook = _read_entries(P.read_authoritative_template())[
            "xl/workbook.xml"
        ].decode("utf-8")
        root = re.search(r"<workbook\b[^>]*>", workbook)
        assert root and "xmlns:r=" not in root.group(0), root
        sheets = re.findall(r"<sheet\b[^>]*/?>", workbook)
        assert sheets and all("xmlns:r=" in item for item in sheets[:3]), sheets[:1]

    def test_instrumented_workbook_and_sheet_xml_are_well_formed(
        self, instrumented: EI.InstrumentedWorkbook, sheet_part: str
    ) -> None:
        import xml.etree.ElementTree as ET

        entries = _read_entries(instrumented.instrumented_bytes)
        for name in ("xl/workbook.xml", sheet_part):
            ET.fromstring(entries[name].decode("utf-8"))

    def test_inline_strings_use_numeric_character_references(self, sheet_part: str) -> None:
        xml = _read_entries(P.read_authoritative_template())[sheet_part].decode("utf-8")
        assert len(re.findall(r"&#\d+;", xml)) > 10000
        assert P.MATRIX_LABEL_HEADER not in xml

    def test_numeric_character_references_are_decoded(self) -> None:
        """🔴 解码器住在 `excel_materialize`（Task 42 修的那一处），**不是** `excel_extract`。

        两处各有一个 `_xml_unescape`，只有 materialize 侧解数字字符引用。本条把这个不对称
        钉住：哪天有人"顺手统一"了两处，footer 定位路径的判据来源就变了，必须重新复核。
        """
        assert M._xml_unescape("&#21512;&#35745;") == "合计"
        assert M._xml_unescape("&#39033;&#32;&#32;&#30446;") == P.MATRIX_LABEL_HEADER
        assert X._xml_unescape("&#21512;&#35745;") == "&#21512;&#35745;"

    def test_ten_authoritative_workbooks_share_this_shape(self) -> None:
        """本模板不是孤例：`backend/wp_templates/` 下同形态的工作簿实测 10 个。"""
        root = _BACKEND / "wp_templates"
        by_extension: dict[str, int] = {}
        legacy_writer = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.startswith("~$"):
                continue
            suffix = path.suffix.lower()
            if suffix not in {".xlsx", ".xlsm", ".xls"}:
                continue
            by_extension[suffix] = by_extension.get(suffix, 0) + 1
            try:
                with zipfile.ZipFile(path) as zf:
                    rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
            except (KeyError, zipfile.BadZipFile):
                continue
            first = re.search(r"<Relationship\b[^>]*?/?>", rels)
            if first and "Id=" in first.group(0) and "Target=" in first.group(0):
                if first.group(0).index("Target=") < first.group(0).index("Id="):
                    legacy_writer += 1
        assert by_extension == {".xlsx": 351, ".xlsm": 17, ".xls": 1}, by_extension
        assert sum(by_extension.values()) == 369
        assert legacy_writer == 10, legacy_writer


# ═══════════════════════════════════════════════════════════════════════════
# 14. 顺序门 + 生产接线 + 无 resolver 欠账
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
    """**Validates: Requirements 12.1 / 12.2**（capability 只能在 finalize 之后启用）"""

    def test_capability_is_not_enabled_before_finalize(self, entry: dict[str, Any]) -> None:
        assert capability_of(entry) is Capability.single_onlyoffice
        assert entry["adapter_id"] is None
        with pytest.raises(P.PilotSelectionError, match="manifest capability"):
            P.assert_manifest_capability_enabled()

    def test_capability_predicate_agrees_with_the_ordering_gate(
        self, manifest: dict[str, Any]
    ) -> None:
        """布尔谓词**委派**顺序门；两侧不得各写一套。"""
        assert P.manifest_capability_enabled() is False
        assert P.manifest_capability_enabled(manifest=manifest) is False
        body = function_body_code(Path(P.__file__), "manifest_capability_enabled")
        assert "assert_manifest_capability_enabled" in body
        assert "except PilotSelectionError" in body
        assert "except Exception" not in body
        # 启用之后两侧必须同时变真（谓词不是恒 False）。
        enabled = json.loads(json.dumps(manifest))
        for item in enabled["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["capability"] = "bidirectional"
                item["adapter_id"] = P.PILOT_ADAPTER_ID
        P.assert_manifest_capability_enabled(manifest=enabled)
        assert P.manifest_capability_enabled(manifest=enabled) is True
        # adapter_id 不符时仍必须打红（顺序门有两条独立判据）。
        wrong = json.loads(json.dumps(enabled))
        for item in wrong["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["adapter_id"] = "h1.disposal_check"
        with pytest.raises(P.PilotSelectionError, match="adapter_id"):
            P.assert_manifest_capability_enabled(manifest=wrong)

    def test_attach_is_a_no_op_before_enablement_and_never_raises(self) -> None:
        """🔴 未启用时必须 `return ()` 且**一次库都不读** —— 抛会让整条 sync 路由 500。"""
        import asyncio

        class ExplodingSession:
            async def execute(self, *args: Any, **kwargs: Any) -> Any:
                raise AssertionError("capability 未启用时不得读库")

        registry = RG.WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        assert (
            asyncio.run(P.attach_pilot_adapters(registry, session=ExplodingSession())) == ()
        )

    def test_ledger_records_adapter_not_registered_yet(self) -> None:
        row = next(
            item
            for item in RG.DELIVERED_PER_ENTRY_CONTRACTS
            if item["contract_id"] == P.PILOT_ADAPTER_ID
        )
        assert row["adapter_registered"] is False
        assert "Task 36" in row["reason"]
        assert "matcher" in row["reason"]
        assert "Task 75" in row["reason"], (
            "reason 仍指向已删除的欠账常量 ⇒ 登记表与现实脱钩"
        )
        assert "Task 76" in row["reason"], (
            "reason 没说清今天挡住注册的是供给（approved bundle / published representation 两表 0 行）"
        )

    def test_contract_orphan_is_visible_in_the_registry_report(self) -> None:
        """契约孤儿是**可见的欠账**：磁盘上有契约、registry 里没有 adapter。"""
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        report = registry.build_report(contract_ids=sorted(available_contract_ids()))
        assert P.PILOT_ADAPTER_ID in set(report.contract_files_without_adapter)
        # 四个 pilot 的契约今天全是孤儿（顺序门尚未放行），不是本 entry 特例。
        assert set(report.contract_files_without_adapter) == set(available_contract_ids())
        assert report.registered_adapter_ids == ()

    def test_registration_is_refused_while_manifest_says_single_onlyoffice(
        self, contract: Any
    ) -> None:
        """伪双向必须被 RG-18 拒（不能靠"填对" declared_capability 绕过）。"""
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        descriptor = _descriptor_facts()
        assert descriptor is not None
        with pytest.raises(RG.RegistryError):
            P.register_pilot_adapter(
                registry,
                adapter=object(),
                bundle=make_bundle(contract),
                descriptor=descriptor,
                room=_room_facts(),
                contract=contract,
            )


class TestProductionWiring:
    """**Validates: Requirements 12.1**（两个生产接线点各一条，且都过契约锁）"""

    def test_router_calls_the_g7_attach_on_both_paths(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        assert source.count("pilot_g7_two_level_dynamic import") == 2, source.count(
            "pilot_g7_two_level_dynamic import"
        )
        assert source.count("attach_g7_pilot_adapters") == 4, source.count(
            "attach_g7_pilot_adapters"
        )

    def test_router_still_calls_the_other_three_pilot_attaches(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        for name in (
            "pilot_simple_checklist import attach_pilot_adapters",
            "attach_d2_pilot_adapters",
            "attach_h1_pilot_adapters",
        ):
            assert name in source, name
        assert source.count("attach_d2_pilot_adapters") >= 4
        assert source.count("attach_h1_pilot_adapters") >= 4

    def test_both_production_paths_go_through_the_contract_lock(self) -> None:
        """两个生产入口都必须经磁盘契约 ↔ 现算 payload 的双向锁。"""
        for name in ("publish_pilot_definitions", "attach_pilot_adapters"):
            body = function_body_code(Path(P.__file__), name)
            assert "assert_contract_file_matches_source()" in body, name

    def test_generator_is_the_only_writer_of_the_disk_contract(self) -> None:
        """磁盘契约只由生成器写；生产模块里没有任何写盘。

        🔴 AST 判据而不是词面：两个文件的 docstring 里都刻意写着「用 `write_bytes` 而不是
        `write_text`」这段**说明**，纯字符串判据会把说明本身判成违规。
        """
        forbidden = {"write_bytes", "write_text", "mkdir", "unlink", "dump", "dumps"}

        def attribute_calls(path: Path) -> set[str]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            return {
                node.func.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            }

        produced = attribute_calls(Path(P.__file__))
        assert not (produced & forbidden), sorted(produced & forbidden)
        generated = attribute_calls(
            _BACKEND / "scripts" / "gen" / "generate_pilot_g7_two_level_dynamic_contract.py"
        )
        assert "write_bytes" in generated
        assert "write_text" not in generated, "write_text 会把 LF 腌成 CRLF"

    def test_disk_contract_is_lf_and_byte_stable(self) -> None:
        raw = P.contract_file_path().read_bytes()
        assert b"\r\n" not in raw
        assert raw.endswith(b"\n")
        payload = json.loads(raw.decode("utf-8"))
        rendered = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        assert raw == rendered

    def test_generator_check_mode_passes(self) -> None:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(
                    _BACKEND
                    / "scripts"
                    / "gen"
                    / "generate_pilot_g7_two_level_dynamic_contract.py"
                ),
                "--check",
            ],
            capture_output=True,
            text=True,
            cwd=str(_REPO),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK g7.soe_subsidiary_disclosure.json" in result.stdout


class TestPilotIntroducesNoResolverDebt:
    """**Validates: Requirements 9.1**（新模块不得给 Task 20 收口门增债）"""

    def test_module_never_calls_a_non_canonical_resolver(self) -> None:
        """用**生成器本体**的符号清单判定，不抄一份名字。"""
        import importlib.util

        path = _BACKEND / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"
        spec = importlib.util.spec_from_file_location("_t43_inventory_gen", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        symbols = set(module._RESOLVER_SYMBOLS)
        assert "find_template_file" in symbols
        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        called: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name in symbols:
                    called.add(str(name))
        assert called == set(), called
        # 观测器住在脚本里，而脚本**不在**清册扫描范围内。
        generator = (
            _BACKEND / "scripts" / "gen" / "generate_pilot_g7_two_level_dynamic_contract.py"
        ).read_text(encoding="utf-8")
        assert "find_template_file" in generator

    def test_no_function_in_this_module_is_classified_as_writer_or_resolver(self) -> None:
        """真实清册（Task 20 收口门消费的那份产物）里本模块贡献 **0** 行。

        判据落在**已生成的产物**上：那份 JSON 的 `source_digest` / `inventory_digest` 由
        `--check` 与 Task 30 的收口门共同守着新鲜度，所以「产物里没有我」等价于「分类器不
        认为我是 writer/resolver」，而且顺带证明我没有让清册过期。
        """
        payload = json.loads(
            (_BACKEND / "data" / "workpaper_writer_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        entries = payload["entries"]
        mine = [
            row
            for row in entries
            if "pilot_g7_two_level_dynamic" in str(row.get("module") or "")
            or "pilot_g7_two_level_dynamic" in str(row.get("source_path") or "")
        ]
        assert mine == [], [row.get("writer_id") for row in mine]
        # 另外三个 pilot 也一样是 0 行（证明这条判据不是"本模块恰好没被扫到"）。
        for other in (
            "pilot_simple_checklist",
            "pilot_d2_large_json",
            "pilot_h1_grouped_dynamic",
        ):
            assert not [
                row for row in entries if other in str(row.get("module") or "")
            ], other

    def test_module_does_not_hardcode_the_template_root(self) -> None:
        """路径拼接必须走既有单一真源常量（Task 40 为自拼路径付过代价）。

        🔴 AST 判据：错误文案里出现 `wp_templates/_index.json` 是**说明**，不是路径拼接。
        被禁的是 `Path(...) / "wp_templates"` 这种 `BinOp(Div)` 形态。
        """
        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        joined: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                for side in (node.left, node.right):
                    if isinstance(side, ast.Constant) and isinstance(side.value, str):
                        joined.append(side.value)
        assert "wp_templates" not in joined, joined
        assert "_index.json" not in joined, joined
        body = function_body_code(Path(P.__file__), "authoritative_template_path")
        assert "assert_template_under_authority" in body
        # 反向自检：旧形态（自己拼 `wp_templates`）必须被同一条 AST 判据抓到。
        legacy = ast.parse('p = root / "wp_templates" / "G"')
        found = [
            side.value
            for node in ast.walk(legacy)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
            for side in (node.left, node.right)
            if isinstance(side, ast.Constant) and isinstance(side.value, str)
        ]
        assert "wp_templates" in found


# ═══════════════════════════════════════════════════════════════════════════
# 15. store 表键 / 行 id 前缀 与历史列键（真实库形态在离线侧的结构判据）
# ═══════════════════════════════════════════════════════════════════════════


class TestStoreKeyShapesComeFromTheRenderModel:
    """**Validates: Requirements 6.4 / 6.5**

    真实库里三条载荷的实测形态（由 pg 守卫冻结）在离线侧对应的**结构**判据。
    """

    def test_store_table_key_is_the_table_id_not_the_metric_prefix(self) -> None:
        source = (_REPO / P.RENDER_MODEL_RELATIVE_PATH).read_text(encoding="utf-8")
        assert f"id: '{P.RENDER_MATRIX_TABLE_ID}'," in source
        assert f"metricRows('{P.RENDER_METRIC_ID_PREFIX}'," in source
        assert f"id: '{P.RENDER_RECORD_TABLE_ID}'," in source
        assert P.RENDER_MATRIX_TABLE_ID != P.RENDER_METRIC_ID_PREFIX
        assert P.RENDER_RECORD_TABLE_ID != P.RENDER_RECORD_ROW_ID_PREFIX

    def test_json_pointers_use_the_store_table_key(self, contract: Any) -> None:
        for spec in contract.all_fields():
            assert spec.json_pointer.startswith("/tables/"), spec.json_pointer
            table_id = spec.json_pointer.split("/")[2]
            assert table_id in {
                P.RENDER_MATRIX_TABLE_ID,
                P.RENDER_RECORD_TABLE_ID,
            }, spec.json_pointer

    def test_legacy_column_keys_fail_closed_instead_of_dropping_a_row(
        self, contract: Any
    ) -> None:
        """改造前的 `c{n}Current` 载荷 ⇒ 抛并点名历史键，绝不静默丢整行。"""
        state = store_state()
        for row in state["tables"][P.RENDER_MATRIX_TABLE_ID]:
            row["values"] = {
                f"c{(index // 2) + 1}{'Current' if index % 2 == 0 else 'Prior'}": 1.0
                for index in range(EXPECTED_DYNAMIC_COLUMN_COUNT)
            }
        with pytest.raises(P.StorePayloadError, match="改造前的历史键"):
            P.build_store_projection(state, contract=contract)

    def test_legacy_pattern_matches_only_the_legacy_shape(self) -> None:
        for legacy in ("c1Current", "c5Prior", "c12Current"):
            assert re.match(P.LEGACY_COLUMN_KEY_PATTERN, legacy), legacy
        for modern in (
            f"{P.RENDER_SLOT}_1_current",
            f"{P.MATRIX_TABLE_KEY}_1",
            "c0Current",
            "cCurrent",
        ):
            assert not re.match(P.LEGACY_COLUMN_KEY_PATTERN, modern), modern

    def test_empty_values_row_is_not_a_failure(self, contract: Any) -> None:
        """全空行（新建底稿的初始态）不算故障 —— 只有「有值却键全不对」才 fail closed。"""
        state = store_state()
        for row in state["tables"][P.RENDER_MATRIX_TABLE_ID]:
            row["values"] = {}
        projection = P.build_store_projection(state, contract=contract)
        assert projection.values == {}

    def test_legacy_debt_is_registered(self) -> None:
        note = P.UPSTREAM_DEBT_LEGACY_COLUMN_KEYS_STRANDED
        assert note.startswith("Task 43 欠账")
        assert "owner" in note and "c{n}Current" in note and "upgrader" in note

    def test_remaining_debts_are_registered_and_mutually_distinct(self) -> None:
        """原第一条已由 Task 75 结清并删除 ⇒ 6 → 5；计数从 `__all__` 现算。"""
        notes = {
            P.UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY,
            P.UPSTREAM_DEBT_TWO_LEVEL_MATRIX_MODE_IS_PER_COLUMN,
            P.UPSTREAM_DEBT_SLOT_SUBCOLUMN_KEY_SPACE_SPLIT,
            P.UPSTREAM_DEBT_RENDER_ROW_IDS_ARE_POSITIONAL,
            P.UPSTREAM_DEBT_LEGACY_COLUMN_KEYS_STRANDED,
        }
        exported = [n for n in (P.__all__ or ()) if n.startswith("UPSTREAM_DEBT_")]
        assert len(notes) == len(exported), sorted(exported)
        for note in notes:
            assert note.startswith("Task 43 欠账"), note[:40]
            assert "owner" in note, note[:40]
