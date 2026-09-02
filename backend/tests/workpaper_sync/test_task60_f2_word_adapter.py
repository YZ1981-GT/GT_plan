r"""Task 60 守卫 —— F2-22 / F2-23 统一 Word adapter 的 per-entry 契约、发布记录与裁决。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 60
点名 Property：**31 / 32 / 47 / 69**；点名 AC：7.3 · 7.4 · 7.9 · 11.5 · 12.3 · 12.7 ·
12.10 · 14.1。

═══ 被守的产物 ═══

* `backend/scripts/gen/generate_task60_f2_word_contracts.py`（生成器；本文件 import 它，
  按**impl 常量现读**而不是抄一份字段表）
* `backend/data/workpaper_sync_word_contracts/f2.stocktake.{plan,summary}.json`（staged 契约）
* `backend/data/workpaper_sync_f2_word_lane_publication.json`（发布记录）

═══ 本轮与前十二轮 per-cycle 守卫的判据差异（照抄会假红/空跑的点）═══

1. **本轮不是 manifest slice**。发布记录刻意落在 AP-1 检测器的 `scan_glob`
   （`backend/data/*_cycle_manifest_slice.json`）**之外** ⇒ 不能套 slice schema 校验器，
   `_UNJUDGED_SLICES` 与 slice 数 12 / Property 70 配对 66 全部**不变**（本文件反向锁住这三条）。
2. **权威册是 docx 不是 xlsx** ⇒ 第二边是 `zipfile` 直读 `word/document.xml`，不是 openpyxl。
3. **锚点只有 `w:tag` 一个**。Task 6 真实 OO 9.4 探针把 `paragraph_index` / `run_index`
   裁为 failed、把 `row_sdt` 裁为 blocked ⇒ 契约里出现 `row_sdt` 或用段落/run 序号作锚点，
   本文件必须打红。段落序号只能作**一次性迁移线索**（`source_ref` 的 `p{NN}`）。
4. **两份文档实测 0 `w:tbl` / 0 `w:tr` / 0 既有 SDT** ⇒ `row_scoped_fields_total == 0` 必须由
   **现读文档**证明（`negative_claims` 逐字段可复算），不是抄结论。
5. **Property 47 的分母不是 0**（首版记录写错，本文件改正并锁住）：本 lane 有 1 个 OO 挂载点
   （`GtF2StocktakeBundle.vue` 的 `<GtOnlyOfficeSheet>`），但它**自行请求 config**、零 descriptor
   prop ⇒ 它是 Property 47 的**反例**。不宣称通过的理由随之从「空分母」改成「承载者形态相反」。
6. **六族 0 命中**（bundle / representation / adapter / 生产契约装载 / 四个 capability 分桶 /
   第二流程删除）必须给「分母存在且判据能命中」的非空跑证明，不能只断言 `== 0`。

═══ 判据强度约定（沿用前十二轮，逐条不放宽）═══

1. **三边锁**：声明（生成器的 `_PLAN_FIELDS` / `_SUMMARY_FIELDS`）→ 磁盘真读（`zipfile` 直读
   `word/document.xml`）→ impl 常量现读（载体/锚点白名单委派 `WordSdtCarrierGate`、契约强校验
   委派 `contracts.parse_contract`、digest 链委派 `word_instrumentation` + `canonical_digest`）。
2. **文本字面量不得 strip**。本 lane 现算 0 条脏字面量 ⇒ 该判据在此是**方法性**的，其非空性由
   :meth:`TestGuardSelfChecks.test_verbatim_comparator_is_strip_sensitive` 的**合成反例**证明。
3. **counters 全族现算等值** + `counting_notes` 的**覆盖面元判据**（它提到的键的并集必须覆盖
   全部数值键，少一个即红）。
4. **Property 31 / 32 逐条落判据；Property 47 / 69 只断言前提 + 承载者存在 + `not_claimed`
   登记在案**，明确不宣称通过（禁空分母重言式）。
5. **既存欠账用 `xfail(strict=True)` + 解除条件**，禁 `pytest.skip`（记为通过 = fail-open）。
6. **禁 `except Exception` fail-open**：取值层判据真跑一次并把异常上抛；反向自检要「故意写错必失败」。
7. **CJK 在 Python 里算 `\w`** ⇒ 提取 sheet 码禁用 `\b`，一律
   `(?<![A-Za-z0-9])…(?![A-Za-z0-9])`。
8. 任何 `declared` 与 `computed` 列表做**有序等值 + 无重复**双断言（集合层，不只逐元素）。
9. 范式 JSON 只读：**四块**（`paradigm` / `definition_producer_paradigm` /
   `adjudication_criteria` / `slice_schema`）各用 `raw_block_digest()` + `canonical_digest()`
   双向锁死。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器）::

    .\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_task60_f2_word_adapter.py -q
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

# ════════════════════════════════════════════════════════════════════════════
# 路径与自举
# ════════════════════════════════════════════════════════════════════════════
_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
SVC = BACKEND / "app" / "services" / "workpaper_sync"
GEN_DIR = BACKEND / "scripts" / "gen"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"

for _p in (BACKEND, GEN_DIR):
    if str(_p) not in sys.path:  # pragma: no cover - import 自举
        sys.path.insert(0, str(_p))

from app.services.word_sdt_fingerprint import structure_fingerprint  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import models as M  # noqa: E402
from app.services.workpaper_sync import word_instrumentation as WI  # noqa: E402
from app.services.workpaper_sync import word_sdt_engine as WE  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    ArtifactKind,
    ArtifactState,
    FieldValue,
    Projection,
    SubstrateRole,
)
from app.services.workpaper_sync.conflicts import ConflictKind  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402

import generate_task60_f2_word_contracts as GEN  # noqa: E402

GENERATOR = GEN_DIR / "generate_task60_f2_word_contracts.py"
PUBLICATION = DATA / "workpaper_sync_f2_word_lane_publication.json"
STAGED_DIR = DATA / "workpaper_sync_word_contracts"
PRODUCTION_CONTRACT_DIR = DATA / "workpaper_sync_contracts"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
CARRIER_CONTRACT = DATA / "onlyoffice_word_sdt_carrier_contract.json"
ENTRY_MANIFEST = DATA / "workpaper_sync_entry_manifest.json"
F_SLICE = DATA / "workpaper_sync_f_cycle_manifest_slice.json"
CONTRACT_GUARD = _THIS.with_name("test_migration_paradigm_contract.py")
COVERAGE_GUARD = _THIS.with_name("test_slice_schema_validator_coverage.py")

LANE_HOST_VUE = WP_COMPONENTS / "GtF2StocktakeBundle.vue"
OO_SHEET_VUE = WP_COMPONENTS / "GtOnlyOfficeSheet.vue"
LANE_DUAL_MODE_TS = WP_COMPONENTS / "composables" / "useF2StocktakeDualMode.ts"
OO_ROUTER_PY = BACKEND / "app" / "routers" / "wp_onlyoffice_router.py"
PLAN_WRITER_PY = (
    BACKEND / "app" / "routers" / "wp_render_strategies" / "_f2_stocktake_plan_sync.py"
)
SUMMARY_WRITER_PY = (
    BACKEND / "app" / "routers" / "wp_render_strategies" / "_f2_stocktake_summary_sync.py"
)
PLAN_SERVICE_PY = BACKEND / "app" / "services" / "f2_stocktake_plan_sync.py"

# ── 范式四块的双向锁（raw 字节 + canonical 结构）─────────────────────────────
#: 🔴 `paradigm` 这一块的期望值在 JSON 自己的 `paradigm_registry` 里也有一份 ⇒ 那块是**真**
#: 双向（改 JSON 或改本常量都打红）。另三块 JSON 里没有自带期望值，本常量是唯一期望值：
#: **解除条件** —— 后续任务合法扩充这三块（例如 Tasks 62–64 给 `slice_schema` 加必填项）时，
#: 必须在同一批改动里更新对应常量并在此写明原因；直接删判据 = 让「只读」失去把守。
FROZEN_PARADIGM_BLOCKS: dict[str, tuple[str, str]] = {
    "paradigm": (
        "363c477cd8042073049c627c9f7cf13cf906ace2a5139a13a79197a5897b7f09",
        "81f7ce00ee2aa19813faad7b9716d821353ea84325960fc615684d57846245a2",
    ),
    "definition_producer_paradigm": (
        "20326a8efce8e9e2491b4dee5c7973677c1803954ab3d8226e625491b6120f6e",
        "6ca2184df59c64209c01347c54b6adda2681e7182ed6e7d7ad5fd4230884bf51",
    ),
    "adjudication_criteria": (
        "b457ab32e76db00bb2918a5a575f80a52517fd35ad81cce911ac6c5b6b2ef779",
        "4e3746d2c2021349a02ff896fd62d6c1189e65c38955fd0d23ed1e304ef4b7e5",
    ),
    "slice_schema": (
        "248808df9cade7e5d41a6ab8309acce47b5d7f973e85063a760c42889c790258",
        "dc9aa5370de67c53eb8c200f413776bfe085bc183b033fd555569fe12ac2335e",
    ),
}

#: AC 原文（`requirements.md` 逐字引用；改了 AC 不改这里必打红）。
AC_TEXT: dict[str, str] = {
    "7.3": "SDT 外内容 SHALL 视为 Word-only，自由正文在 HTML materialize 时必须保留。",
    "7.4": "同一 stable field key 多实例值一致时可合并；值不一致时 SHALL 产生冲突并列出全部 OO 位置。",
    "7.9": "HTML materialize SHALL 只更新结构化岛；不得用模板重生成覆盖审计师已编辑的 Word-only 内容。",
    "11.5": (
        "`GtOnlyOfficeSheet` SHALL 暴露可 await 的 `forceSave()`/状态 API，发出 ready、dirty、"
        "save-requested、incoming-durable、applied/conflict、recovery-case、error 事件；"
        "不得只 emit `fallback`，且 recovery-case 事件在 claim 前不得伪造 operation id。"
    ),
    "12.3": "Word pilot SHALL 为 F2-22/F2-23；pilot 未通过 tagged SDT 往返保留前不得批量迁移其他 DOCX。",
    "12.7": (
        "F2-22/F2-23 现有专用 to/from 端点 SHALL 迁到统一协议并删除第二套半闭环；"
        "删除前必须有等价证据和 rollback 点。"
    ),
    "12.10": "每个 bidirectional entry SHALL 有一个服务端生成的 evidence summary",
    "14.1": "每个 bidirectional entry SHALL 有服务端编排的逐 scenario 产物级测试",
}

#: 发布记录的顶层节 —— 有序等值（缺节 / 多节 / 换序都打红）。
EXPECTED_TOP_LEVEL: tuple[str, ...] = (
    "schema_version",
    "task",
    "spec",
    "description",
    "paradigm_ref",
    "why_not_a_cycle_manifest_slice",
    "source_ref_semantics",
    "probe_gate",
    "authoritative_templates",
    "entries",
    "task59_compatibility",
    "second_pipeline_deletion_plan",
    "blocking_preconditions",
    "cross_entry_isolation",
    "descriptor_consumption",
    "properties_verified",
    "property_denominators",
    "counters",
    "requirements_covered",
    "ac_12_3_compliance",
)

#: `source_ref` 的唯一合法形态：`{sheet}!p{NN}[+NN…]:${token}`。
#: 🔴 sheet 段用 `(?<![A-Za-z0-9])`/`(?![A-Za-z0-9])` 而不是 `\b` —— CJK 在 Python 里算 `\w`，
#: `\b` 在「计划F2-22」这类串上不成立（Task 56 的教训，Decision 19）。
SOURCE_REF_RE = re.compile(
    r"^(?P<sheet>[A-Z]\d+-\d+)!p(?P<ordinals>\d{2}(?:\+\d{2})*):(?P<token>\$\{[A-Za-z][A-Za-z0-9_]*\})$"
)

#: Task 6 裁决里**不得**作锚点的东西（本文件按它做否定式判据；真源仍是探针 JSON）。
FORBIDDEN_ANCHOR_WORDS: tuple[str, ...] = ("paragraph_index", "run_index", "alias_display_name", "sdt_id")

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# ════════════════════════════════════════════════════════════════════════════
# 基础工具
# ════════════════════════════════════════════════════════════════════════════
def _load(path: Path) -> dict:
    """读 JSON。🔴 不吞异常：文件坏了就该以 ERROR 态暴露，不是「视作空」。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_PY_COMMENT_RE = re.compile(r"#[^\n]*")
_TS_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*|<!--.*?-->", re.S)


def _blank_keep_newlines(match: "re.Match[str]") -> str:
    """同长空白替换 —— 剥注释**保留行号**（删行式会让 `#Lnn` 坐标上移 ⇒ 锚点假红）。"""
    return "".join("\n" if ch == "\n" else " " for ch in match.group(0))


def _strip_ts_comments(source: str) -> str:
    return _TS_COMMENT_RE.sub(_blank_keep_newlines, source)


def _strip_py_comments(source: str) -> str:
    """剥 Python 行注释（保留行号）。

    🔴 只剥 `#` 行注释，**不剥** docstring / `sa.text(\"\"\"…SQL…\"\"\")` —— 后者会把真判据
    一起剥掉（memory 里的既有教训）。
    """
    out: list[str] = []
    for line in source.split("\n"):
        in_str: str | None = None
        cut = len(line)
        idx = 0
        while idx < len(line):
            ch = line[idx]
            if in_str:
                if ch == "\\":
                    idx += 2
                    continue
                if ch == in_str:
                    in_str = None
            elif ch in "\"'":
                in_str = ch
            elif ch == "#":
                cut = idx
                break
            idx += 1
        kept = line[:cut]
        out.append(kept + " " * (len(line) - len(kept)))
    return "\n".join(out)


def _commit_bytes_lane_id(path: Path) -> str:
    """取 `_save_fields` 里 `commit_bytes(lane_id=...)` 的**字面量**实参（AST，不 grep）。

    🔴 Task 65 之后 `commit_bytes` 已无 `authority_model` 参数：authority model 由
    `lane_id` 经 `opaque_entry_gate` 的 lane 登记表单向决定。因此「本 writer 仍用哪个
    authority model」的判据落点从「源码里有没有那个枚举名」搬到「这个字面量 + 登记表」。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit_bytes"
    ]
    assert len(calls) == 1, f"{path.name} 的 `commit_bytes` 调用点有 {len(calls)} 处（应 1）"
    lane_kw = [kw for kw in calls[0].keywords if kw.arg == "lane_id"]
    assert len(lane_kw) == 1, f"{path.name}: `commit_bytes` 缺 `lane_id=` 实参"
    value = lane_kw[0].value
    assert isinstance(value, ast.Constant) and isinstance(value.value, str), (
        f"{path.name}: `lane_id=` 实参是 {ast.unparse(value)!r} 而不是字符串字面量"
    )
    return value.value


def _lane_registry() -> Any:
    """生产那份 opaque lane 登记表（authority model 的唯一真源）。"""
    from app.services.workpaper_sync import opaque_entry_gate as OG  # noqa: PLC0415

    return OG


def _lines_of(path: Path) -> list[str]:
    """整行集合（strip 后）—— 🔴 源码侧判据禁用含 `\\n` 的字面量（CRLF 下恒假）。"""
    return [line.rstrip("\r").strip() for line in path.read_text(encoding="utf-8").split("\n")]


def _validator_module() -> ModuleType:
    """范式守卫模块（`raw_block_digest` / `canonical_digest` 的真源）。"""
    spec = importlib.util.spec_from_file_location(
        "task60_paradigm_contract", CONTRACT_GUARD
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _coverage_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task60_slice_coverage", COVERAGE_GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ── 第二边：磁盘真读（每次都真读，不缓存成快照）───────────────────────────────
def _docx_facts(sheet_code: str) -> dict[str, Any]:
    """一份权威 docx 的现算事实（段落 / token / 否定式声明）。"""
    entry = _entry_decl(sheet_code)
    data = entry.template_path.read_bytes()
    xml = GEN.document_xml(data)
    return {
        "bytes": data,
        "xml": xml,
        "sha256": hashlib.sha256(data).hexdigest(),
        "paragraphs": GEN.paragraph_survey(data),
        "tokens": GEN.token_facts(data),
        "w_tbl": xml.count("<w:tbl>"),
        "w_tr": xml.count("<w:tr>"),
        "w_sdt": xml.count("<w:sdt>"),
    }


def _entry_decl(sheet_code: str) -> Any:
    for entry in GEN.ENTRIES:
        if entry.sheet_code == sheet_code:
            return entry
    raise AssertionError(f"生成器的 ENTRIES 里没有 {sheet_code} ⇒ 声明侧对象消失")


# ════════════════════════════════════════════════════════════════════════════
# fixtures
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def record() -> dict:
    return _load(PUBLICATION)


@pytest.fixture(scope="module")
def paradigm() -> dict:
    return _load(PARADIGM_PATH)


@pytest.fixture(scope="module")
def contracts_on_disk() -> dict[str, dict]:
    return {
        entry.contract_id: _load(STAGED_DIR / f"{entry.contract_id}.json")
        for entry in GEN.ENTRIES
    }


@pytest.fixture(scope="module")
def gate() -> WI.WordSdtCarrierGate:
    return WI.WordSdtCarrierGate.load()


@pytest.fixture(scope="module")
def workdir() -> Any:
    with tempfile.TemporaryDirectory(prefix="tmp_task60_guard_") as tmp:
        yield Path(tmp)


def _binding(payload: dict, *, entry_id: str) -> WE.WordEngineBinding:
    """离线 binding —— 本 lane 无 approved bundle，故只能 offline_candidate_validation。"""
    return WE.WordEngineBinding(
        contract=C.parse_contract(payload, adapter_id=payload["contract_id"]),
        entry_id=entry_id,
        mode=WE.WordEngineMode.offline_candidate_validation,
    )


def _instrumented(sheet_code: str, gate: WI.WordSdtCarrierGate) -> WI.InstrumentedDocx:
    entry = _entry_decl(sheet_code)
    data = entry.template_path.read_bytes()
    facts = GEN.token_facts(data)
    spec = GEN.build_instrumentation_spec(entry, facts)
    return WI.instrument_docx_bytes(data, spec, gate=gate)


def _substrate(sheet_code: str, workdir: Path, gate: WI.WordSdtCarrierGate) -> Path:
    target = workdir / f"{sheet_code}.substrate.docx"
    if not target.is_file():
        target.write_bytes(_instrumented(sheet_code, gate).instrumented_bytes)
    return target


def _projection_for(payload: dict, *, seed: str) -> Projection:
    """按契约声明的每个字段的 value_type 派值（**全给值**，漏一个会削弱等值门）。"""
    values: dict[str, FieldValue] = {}
    for raw in payload["fields"]:
        vt = C.ValueType(raw["value_type"])
        if vt is C.ValueType.date:
            value: Any = date(2026, 12, 31)
        elif vt is C.ValueType.integer:
            value = 2026
        else:
            value = f"{seed}·{raw['stable_field_key']}"
        values[raw["stable_field_key"]] = FieldValue(
            stable_key=raw["stable_field_key"],
            value=value,
            value_type=vt,
            mode=C.FieldMode(raw["mode"]),
            row_key=None,
        )
    return Projection(
        contract_id=payload["contract_id"],
        semantic_version=payload["semantic_version"],
        document_type="docx",
        values=values,
    )


def _rewrite_document(data: bytes, mutate: Any) -> bytes:
    """改写 `word/document.xml`（其余部件逐字节复制）—— 只给守卫造反例用。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        parts = {i.filename: zf.read(i) for i in infos}
        order = [(i.filename, i.compress_type) for i in infos]
    parts[WE.WORD_DOCUMENT_PART] = mutate(
        parts[WE.WORD_DOCUMENT_PART].decode("utf-8")
    ).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as out:
        for name, compress in order:
            out.writestr(zipfile.ZipInfo(name), parts[name], compress_type=compress)
    return buffer.getvalue()


_WT_RE = re.compile(r"<w:t(?:\s[^>]*)?>([^<]{6,})</w:t>")


def _sdt_spans(xml: str) -> list[tuple[int, int]]:
    """`<w:sdt>…</w:sdt>` 的顶层区间（带深度计数，嵌套只记最外层）。"""
    spans: list[tuple[int, int]] = []
    depth = 0
    start = -1
    for match in re.finditer(r"<w:sdt(?:\s[^>]*)?>|</w:sdt>", xml):
        if match.group(0).startswith("</"):
            depth -= 1
            if depth == 0:
                spans.append((start, match.end()))
        else:
            if depth == 0:
                start = match.start()
            depth += 1
    return spans


def _an_outside_sdt_wt_element(xml: str) -> str:
    """取一个**确实落在任何 SDT 之外**、且逐字出现在 XML 里的 `<w:t>` 元素整串。

    🔴 不用 `structure_fingerprint().outside_sdt_blocks` 的规范化文本做 replace：那些文本
    可能是跨 run 拼接出来的，`xml.replace(text, "")` 会是**空操作** ⇒ 反例造不出来、
    「必须打红」变成假绿（本文件实测踩过一次）。
    """
    spans = _sdt_spans(xml)
    for match in _WT_RE.finditer(xml):
        if any(lo <= match.start() < hi for lo, hi in spans):
            continue
        literal = match.group(0)
        if xml.count(literal) == 1:
            return literal
    raise AssertionError("文档里找不到唯一的 SDT 外 <w:t> 元素 ⇒ 反例分母消失")


def _extract(artifact: Path, binding: WE.WordEngineBinding) -> WE.WordExtractOutcome:
    return WE.extract_word_projection(
        artifact=artifact,
        binding=binding,
        substrate_role=SubstrateRole.staged_result,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.staged,
    )


# ════════════════════════════════════════════════════════════════════════════
# 判据零：守卫自检（反向自检 —— 「故意写错必失败」）
# ════════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:
    """每条工具函数与每个分母都要能被证伪，否则后面的判据可能整类空跑。"""

    def test_all_required_artifacts_exist(self) -> None:
        """**Validates: Requirements 12.3**"""
        for path in (
            GENERATOR,
            PUBLICATION,
            STAGED_DIR,
            PARADIGM_PATH,
            CARRIER_CONTRACT,
            ENTRY_MANIFEST,
            F_SLICE,
            CONTRACT_GUARD,
            COVERAGE_GUARD,
            LANE_HOST_VUE,
            OO_SHEET_VUE,
            LANE_DUAL_MODE_TS,
            OO_ROUTER_PY,
            PLAN_WRITER_PY,
            SUMMARY_WRITER_PY,
            PLAN_SERVICE_PY,
        ):
            assert path.exists(), f"缺少判据对象：{path}"
        for entry in GEN.ENTRIES:
            assert entry.template_path.is_file(), f"权威模板缺失：{entry.template_path}"

    def test_the_generator_is_idempotent_against_the_artifacts_on_disk(self) -> None:
        """产物必须能由生成器**现算重现** —— 手改产物即刻打红。

        🔴 真跑 `generate()` 而不是比对 mtime：只比 mtime 的话，手改一个字节仍绿。
        """
        rendered = GEN.generate()
        assert rendered, "生成器现算结果为空 ⇒ 判据分母消失"
        for path, text in rendered.items():
            assert path.is_file(), f"生成器声称要产出 {path}，磁盘上没有"
            assert path.read_text(encoding="utf-8") == text, (
                f"{path.relative_to(ROOT).as_posix()} 与生成器现算结果不一致 ⇒ "
                "产物被手改过（或生成器被改了却没重跑 --write）"
            )

    def test_docx_reader_is_non_vacuous(self) -> None:
        """第二边的分母：两份文档都必须真读出段落与 token。"""
        for entry in GEN.ENTRIES:
            facts = _docx_facts(entry.sheet_code)
            assert len(facts["paragraphs"]) >= 30, (
                f"{entry.sheet_code} 只读出 {len(facts['paragraphs'])} 段 ⇒ 读取器可疑"
            )
            assert len(facts["tokens"]) >= 15, (
                f"{entry.sheet_code} 只读出 {len(facts['tokens'])} 个 token ⇒ 读取器可疑"
            )
            assert re.fullmatch(r"[0-9a-f]{64}", facts["sha256"]), facts["sha256"]
            assert facts["w_tbl"] == facts["w_tr"] == facts["w_sdt"] == 0, (
                f"{entry.sheet_code} 现算 w:tbl={facts['w_tbl']} w:tr={facts['w_tr']} "
                f"w:sdt={facts['w_sdt']} ⇒ 「0 行载体 / 0 既有 SDT」这个前提变了，"
                "row_scoped_fields_total=0 与 sdt_external_body 的裁决都要重做"
            )

    def test_verbatim_comparator_is_strip_sensitive(self) -> None:
        """🔴 「文本字面量不得 strip」的**非空性证明**（合成反例）。

        本 lane 现算 0 条脏字面量（前导/尾随空格、缺右括号都没有）⇒ 直接断言
        「declared == computed 且 strip 后不同」会是重言式。故用合成值证明比较口径真的
        strip-敏感：只要有人把两侧任一改成 `.strip()`，同一比较函数就会把脏值判成相等。
        """
        dirty = "  【提示：现场亲自监盘  "
        assert dirty != dirty.strip(), "构造前提被破坏"
        assert self._verbatim_equal(dirty, dirty) is True
        assert self._verbatim_equal(dirty, dirty.strip()) is False, (
            "比较口径对前后空白不敏感 ⇒ 「不 strip」这条判据是装饰"
        )
        # 缺右括号形态（历史上另一类脏字面量）
        broken = "（以下简称该公司"
        assert self._verbatim_equal(broken, broken + "）") is False

    @staticmethod
    def _verbatim_equal(left: str, right: str) -> bool:
        """本文件全域使用的字面量比较口径 —— **逐字**，两侧都不 strip。"""
        return left == right

    def test_the_lane_really_has_no_dirty_verbatim_so_the_rule_is_methodological(
        self, record: dict
    ) -> None:
        """如实登记：本 lane 的 `paragraph_texts_verbatim` 里脏字面量数 = 0。

        写成判据而不是散文，后来者才知道「这条在本 lane 上靠合成反例撑着」，
        而不是以为它在真数据上有非空分母。
        """
        dirty = [
            text
            for entry in record["entries"]
            for field in entry["field_evidence"]
            for text in field["paragraph_texts_verbatim"]
            if text != text.strip()
        ]
        assert dirty == [], f"本 lane 出现脏字面量 {dirty[:3]} ⇒ 该判据分母变非空，请改成直接断言"
        # 但**全部段落**里确有空串段（源模板的空行）—— 空串正是 strip 抹不掉却容易被
        # 「if not text: continue」跳过的形态，它的存在使「逐段登记」不是摆设。
        empties = [
            p
            for entry in GEN.ENTRIES
            for p in GEN.paragraph_survey(entry.template_path.read_bytes())
            if p["text"] == ""
        ]
        assert len(empties) >= 2, (
            f"两份文档里空串段现算只有 {len(empties)} 段 ⇒ 「逐段登记不过滤空串」失去对象"
        )

    def test_strip_py_comments_keeps_line_numbers_and_hides_a_real_marker(self) -> None:
        """剥注释保留行号 + 真藏得住一个真实源文件里的注释标记。"""
        src = "a = 1\n# hidden marker\nb = 2\n"
        out = _strip_py_comments(src)
        assert "hidden marker" not in out
        assert len(out.split("\n")) == len(src.split("\n")), "剥注释改变了行数"
        assert _strip_py_comments('x = "# not a comment"') == 'x = "# not a comment"', (
            "把字符串里的 # 当注释剥了 ⇒ 会造出假判据"
        )
        raw = PLAN_WRITER_PY.read_text(encoding="utf-8")
        needle = "🔴 entry_id 必须带 sheet code"
        assert needle in raw, f"{PLAN_WRITER_PY.name} 里的那段注释不见了 ⇒ 本自检失去对象"
        assert needle not in _strip_py_comments(raw)

    def test_strip_ts_comments_hides_a_real_marker_in_the_lane_host(self) -> None:
        raw = LANE_DUAL_MODE_TS.read_text(encoding="utf-8")
        needle = "强制 GtOnlyOfficeSheet 重挂载"
        assert needle in raw, "composable 里那段注释不见了 ⇒ 本自检失去对象"
        assert needle not in _strip_ts_comments(raw)

    def test_source_ref_regex_survives_cjk_word_boundaries(self) -> None:
        """🔴 CJK 算 `\\w` ⇒ 提取 sheet 码禁用 `\\b`（Decision 19）。

        实测方向：`监盘计划F2-22` 里「划」与「F」都是 `\\w` ⇒ **两者之间没有 `\\b`** ⇒
        `\\bF2-22\\b` 在这个串上**匹配不到**。而生产代码里的 sheet 别名恰恰是这个形态
        （`_SHEET_CODES = {"F2-22", "监盘计划F2-22"}`）⇒ 用 `\\b` 提码会整类漏掉别名。
        lookaround 形态没有这个问题。
        """
        good = "F2-22!p01+04:${entityName}"
        assert SOURCE_REF_RE.match(good), "正则连正样本都不认"
        b_version = re.compile(r"\bF2-22\b")
        assert b_version.search("F2-22!p01") is not None
        assert b_version.search("监盘计划F2-22") is None, (
            "CJK 与 ASCII 之间竟然有 \\b ⇒ 本自检的前提（CJK 算 \\w）变了，"
            "整条「禁用 \\b」的理由要重新论证"
        )
        ours = re.compile(r"(?<![A-Za-z0-9])F2-22(?![A-Za-z0-9])")
        assert ours.search("F2-22!p01") is not None
        assert ours.search("监盘计划F2-22") is not None, (
            "lookaround 形态漏掉了 CJK 前缀的别名 ⇒ 换回 \\b 也一样错，判据无效"
        )
        assert ours.search("XF2-22") is None, "前置 ASCII 边界失效"
        # 生产代码里真有这个别名 ⇒ 本自检不是造出来的假设
        assert '"监盘计划F2-22"' in PLAN_WRITER_PY.read_text(encoding="utf-8"), (
            "生产代码里的 CJK 前缀别名不见了 ⇒ 本自检失去对象"
        )

    def test_carrier_gate_is_live_and_blocks_row_sdt(self, gate: WI.WordSdtCarrierGate) -> None:
        """载体/锚点白名单是**现读**探针 JSON 的，且真的会拒 blocked 项。"""
        gate.assert_carrier_allowed("field_sdt_inline")
        gate.assert_carrier_allowed("field_sdt_block")
        gate.assert_anchor_allowed("w_tag")
        with pytest.raises(WI.WordCarrierGateError):
            gate.assert_carrier_allowed("row_sdt")
        for anchor in FORBIDDEN_ANCHOR_WORDS:
            with pytest.raises(WI.WordCarrierGateError):
                gate.assert_anchor_allowed(anchor)

    def test_negative_claim_detector_can_actually_see_a_table(self) -> None:
        """🔴 `document_has_w_tbl == False` 的**非空跑证明**：检测器能看见表格。

        两份权威 docx 都 0 个 `w:tbl`；只断言 `== 0` 的话，把检测器写坏成恒 0 也仍绿。
        故这里在真实字节上合成一个表格再读一次，必须变成 True。
        """
        entry = _entry_decl("F2-22")
        base = entry.template_path.read_bytes()
        assert "<w:tbl>" not in GEN.document_xml(base)
        injected = _rewrite_document(
            base,
            lambda xml: xml.replace(
                "<w:body>",
                "<w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>x</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
                1,
            ),
        )
        xml = GEN.document_xml(injected)
        assert "<w:tbl>" in xml and "<w:tr>" in xml
        facts = GEN.token_facts(injected)
        assert any(f["negative_claims"]["document_has_w_tbl"] for f in facts.values()), (
            "注入了真表格，`document_has_w_tbl` 仍为 False ⇒ 否定式判据是装饰"
        )
        assert any(f["negative_claims"]["document_has_w_tr"] for f in facts.values())

    def test_inside_table_detector_can_actually_fire(self) -> None:
        """`inside_w_tbl == False` 的非空跑证明：把一个 token 段搬进表格 ⇒ 必须变 True。"""
        entry = _entry_decl("F2-22")
        base = entry.template_path.read_bytes()

        def mutate(xml: str) -> str:
            needle = "<w:p"
            start = xml.find("${purpose}")
            assert start > 0, "构造前提被破坏：找不到 ${purpose}"
            popen = xml.rfind(needle, 0, start)
            pclose = xml.find("</w:p>", start) + len("</w:p>")
            para = xml[popen:pclose]
            wrapped = f"<w:tbl><w:tr><w:tc>{para}</w:tc></w:tr></w:tbl>"
            return xml[:popen] + wrapped + xml[pclose:]

        facts = GEN.token_facts(_rewrite_document(base, mutate))
        assert facts["${purpose}"]["negative_claims"]["inside_w_tbl"] is True, (
            "token 段已被包进 w:tbl，`inside_w_tbl` 仍为 False ⇒ 该字段是死声明"
        )

    def test_contract_validator_is_the_production_one_and_rejects_a_bad_carrier(
        self, contracts_on_disk: dict[str, dict]
    ) -> None:
        """第三边：契约强校验委派生产校验器，且它真的会拒不合法载体。"""
        payload = json.loads(json.dumps(contracts_on_disk[GEN.PLAN_ID]))
        C.parse_contract(payload, adapter_id=payload["contract_id"])  # 正样本必须通过
        payload["identity_carriers"] = ["row_sdt"]
        with pytest.raises(C.ContractError):
            C.parse_contract(payload, adapter_id=payload["contract_id"])

    def test_bundle_slot_gate_is_live(self) -> None:
        """`validate_bundle_slot` 真的会拒 `slot_ref=None`（BP-11 的正向断言依赖它）。"""
        ok = M.BundleSlotSpec(
            slot=M.BundleSlot.template,
            slot_type="definition",
            slot_ref="definition:11111111-2222-3333-4444-555555555555",
            slot_digest="a" * 64,
        )
        M.validate_bundle_slot(ok)  # 正样本必须过，否则下面的「必拒」是恒真
        with pytest.raises(M.BundleIntegrityError):
            M.validate_bundle_slot(
                M.BundleSlotSpec(
                    slot=M.BundleSlot.template,
                    slot_type="definition",
                    slot_ref=None,
                    slot_digest="a" * 64,
                )
            )

    def test_declared_vs_computed_helper_checks_both_order_and_duplicates(self) -> None:
        """🔴 Decision 18：集合层判据要「有序等值 + 无重复」双断言，不只逐元素。"""
        assert _same_sequence(["a", "b"], ["a", "b"]) is True
        assert _same_sequence(["a", "b"], ["b", "a"]) is False, "换序没被发现"
        assert _same_sequence(["a", "a"], ["a", "a"]) is False, "重复没被发现"
        assert _same_sequence(["a"], ["a", "b"]) is False


def _same_sequence(declared: list[Any], computed: list[Any]) -> bool:
    """有序等值 + 两侧无重复。"""
    if len(set(map(str, declared))) != len(declared):
        return False
    if len(set(map(str, computed))) != len(computed):
        return False
    return list(declared) == list(computed)


# ════════════════════════════════════════════════════════════════════════════
# 判据一：范式 JSON 只读 —— 四块 × （raw 字节 + canonical 结构）双向锁死
# ════════════════════════════════════════════════════════════════════════════
class TestParadigmIsReadOnly:
    """本任务对 `workpaper_sync_migration_paradigm.json` **只读禁改**。"""

    def test_four_blocks_are_frozen_both_by_raw_bytes_and_canonical_structure(
        self, paradigm: dict
    ) -> None:
        """**Validates: Requirements 12.3**"""
        mod = _validator_module()
        raw = PARADIGM_PATH.read_text(encoding="utf-8")
        assert set(FROZEN_PARADIGM_BLOCKS) <= set(paradigm), (
            f"范式 JSON 少了被冻结的块：{sorted(set(FROZEN_PARADIGM_BLOCKS) - set(paradigm))}"
        )
        for key, (want_raw, want_canonical) in sorted(FROZEN_PARADIGM_BLOCKS.items()):
            got_raw = mod.raw_block_digest(raw, key)
            got_canonical = mod.canonical_digest(paradigm[key])
            assert got_raw == want_raw, (
                f"范式块 `{key}` 的**原始字节**变了（{got_raw} != {want_raw}）—— "
                "本任务对该文件只读；若是后续任务合法扩充，请同批更新本常量并写明理由"
            )
            assert got_canonical == want_canonical, (
                f"范式块 `{key}` 的**canonical 结构**变了（{got_canonical} != {want_canonical}）"
            )

    def test_the_paradigm_block_is_locked_against_the_json_own_registry_too(
        self, paradigm: dict
    ) -> None:
        """`paradigm` 那一块是**真**双向：JSON 自带期望值，两边互为对照。"""
        mod = _validator_module()
        reg = next(
            p
            for p in paradigm["paradigm_registry"]["paradigms"]
            if p["alias"] == "legacy_deletion_paradigm"
        )
        raw = PARADIGM_PATH.read_text(encoding="utf-8")
        assert mod.raw_block_digest(raw, "paradigm") == reg["frozen_raw_block_sha256"]
        assert mod.canonical_digest(paradigm["paradigm"]) == reg["frozen_canonical_sha256"]
        assert len(paradigm["paradigm"]["steps"]) == reg["step_count"] == 7
        assert reg["frozen_raw_block_sha256"] == FROZEN_PARADIGM_BLOCKS["paradigm"][0], (
            "守卫常量与 JSON 的登记值脱钩 ⇒ 双向锁退化成单向"
        )

    def test_the_digest_helpers_are_alive(self, paradigm: dict) -> None:
        """反向自检：改一个字节，两个 digest 必须都变。"""
        mod = _validator_module()
        raw = PARADIGM_PATH.read_text(encoding="utf-8")
        tampered = raw.replace('"name": "identify_legacy"', '"name": "identify_legacyX"', 1)
        assert tampered != raw, "构造前提被破坏：锚点串没找到"
        assert mod.raw_block_digest(tampered, "paradigm") != FROZEN_PARADIGM_BLOCKS["paradigm"][0]
        mutated = json.loads(json.dumps(paradigm["slice_schema"]))
        mutated["schema_version"] = f"{mutated['schema_version']}-x"
        assert mod.canonical_digest(mutated) != FROZEN_PARADIGM_BLOCKS["slice_schema"][1]

    def test_the_paradigm_ref_in_the_record_points_at_a_real_pointer(
        self, record: dict, paradigm: dict
    ) -> None:
        """发布记录声明的 `paradigm_ref` 必须真存在且步数可复算。"""
        ref = record["paradigm_ref"]
        assert ref["file"] == PARADIGM_PATH.relative_to(ROOT).as_posix()
        assert ref["json_pointer"] == "/definition_producer_paradigm"
        block = paradigm["definition_producer_paradigm"]
        step_numbers = sorted(step["step"] for step in block["steps"])
        declared = sorted(ref["steps_delivered"] + ref["steps_blocked"])
        assert set(ref["steps_delivered"]) & set(ref["steps_blocked"]) == set(), (
            "同一步不能既 delivered 又 blocked"
        )
        # 🔴 范式现算 12 步；本 lane 只对 step 1 例外（不可执行，理由必须写明）⇒
        #    「declared + {1} 覆盖全部步号」比「declared == 全部步号」更准，且不给漏步留缝。
        assert _same_sequence(sorted(declared + [1]), step_numbers), (
            f"声明的 delivered+blocked 步号 {declared}（+ 例外的 step 1）与范式现算 "
            f"{step_numbers} 不等值 ⇒ 有步号既没交付也没登记阻断"
        )
        assert 1 not in declared, (
            "step 1（freeze_manifest_slice）在本 lane 上不可执行，不得声明为 delivered/blocked；"
            "理由见 record.paradigm_ref.step_1_note"
        )
        assert ref["step_1_note"].strip(), "step 1 的不可执行理由必须写明（禁空注解）"
        assert len(step_numbers) == 12, (
            f"definition_producer_paradigm 现算 {len(step_numbers)} 步 ⇒ 范式被改过"
        )


# ════════════════════════════════════════════════════════════════════════════
# 判据二：source_ref 三边锁（本轮最重的判据）
# ════════════════════════════════════════════════════════════════════════════
class TestSourceRefThreeWayLock:
    """声明 → 磁盘真读 → impl 常量现读，三边逐字段等值。"""

    def test_declared_tokens_equal_the_tokens_on_disk(self) -> None:
        """**Validates: Requirements 7.4**

        声明侧（生成器的字段表）与磁盘侧（`word/document.xml` 里的 `${token}`）**双向等值**：
        漏声明一个 token = 有受管字段没进契约；声明了磁盘上不存在的 token = 自造字段。
        """
        for entry in GEN.ENTRIES:
            facts = _docx_facts(entry.sheet_code)
            declared = [decl.token for decl in entry.fields]
            on_disk = sorted(facts["tokens"])
            assert _same_sequence(sorted(declared), on_disk), (
                f"{entry.sheet_code}: 声明 {sorted(declared)} 与磁盘 {on_disk} 不等值 ⇒ "
                "漏声明或自造字段"
            )
            assert len(declared) == len(set(declared)), f"{entry.sheet_code} 声明里有重复 token"

    def test_every_source_ref_is_recomputable_from_the_docx(
        self, contracts_on_disk: dict[str, dict]
    ) -> None:
        """**Validates: Requirements 7.4**

        逐字段：`source_ref` 的 sheet 段 / 段落序号集合 / token 必须与现读文档一致，
        `instances` 必须与现算出现次数一致。
        """
        checked = 0
        for entry in GEN.ENTRIES:
            facts = _docx_facts(entry.sheet_code)
            payload = contracts_on_disk[entry.contract_id]
            for field in payload["fields"]:
                match = SOURCE_REF_RE.match(field["source_ref"])
                assert match, (
                    f"{entry.sheet_code}/{field['stable_field_key']}: source_ref "
                    f"{field['source_ref']!r} 不合法（唯一形态 `{{sheet}}!p{{NN}}[+NN]:${{token}}`）"
                )
                assert match.group("sheet") == entry.sheet_code
                token = match.group("token")
                assert token in facts["tokens"], (
                    f"{entry.sheet_code}: source_ref 指向磁盘上不存在的 token {token}"
                )
                fact = facts["tokens"][token]
                declared_ordinals = [int(x) for x in match.group("ordinals").split("+")]
                assert _same_sequence(declared_ordinals, list(fact["paragraph_ordinals"])), (
                    f"{entry.sheet_code}/{field['stable_field_key']}: 声明段落序号 "
                    f"{declared_ordinals} 与现算 {fact['paragraph_ordinals']} 不等值"
                )
                expected_instances = (
                    "many" if fact["occurrences_in_document_xml"] > 1 else "one"
                )
                assert field["instances"] == expected_instances, (
                    f"{entry.sheet_code}/{field['stable_field_key']}: instances="
                    f"{field['instances']!r} 与现算出现 {fact['occurrences_in_document_xml']} 次不符"
                )
                checked += 1
        assert checked == 33, f"逐字段判据只跑了 {checked} 条 ⇒ 分母与 managed_fields_total 不符"

    def test_field_evidence_verbatim_matches_the_docx_byte_for_byte(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 7.4**

        🔴 `paragraph_texts_verbatim` / `run_counts_at_injection` / `paragraph_ordinals`
        逐项**逐字**等值，两侧都不 strip（比较口径见 `TestGuardSelfChecks`）。
        """
        for entry_record in record["entries"]:
            facts = _docx_facts(entry_record["sheet_code"])
            for field in entry_record["field_evidence"]:
                fact = facts["tokens"][field["token"]]
                assert field["occurrences_in_document_xml"] == fact[
                    "occurrences_in_document_xml"
                ]
                assert _same_sequence(
                    list(field["paragraph_ordinals"]), list(fact["paragraph_ordinals"])
                )
                assert list(field["run_counts_at_injection"]) == list(
                    fact["run_counts_at_injection"]
                )
                declared_texts = list(field["paragraph_texts_verbatim"])
                computed_texts = list(fact["paragraph_texts_verbatim"])
                assert len(declared_texts) == len(computed_texts)
                for got, want in zip(declared_texts, computed_texts, strict=True):
                    assert got == want, (
                        f"{entry_record['sheet_code']}/{field['stable_field_key']}: "
                        f"段落原文不逐字相等\n声明 {got!r}\n现算 {want!r}"
                    )
                assert field["verdict"] == "source_backed"
                assert field["verdict_recipe"].strip(), "verdict 必须带可复算配方（禁空注解）"

    def test_negative_claims_are_recomputable_and_include_the_document_level_facts(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 7.4**

        否定式声明（该 token 不在任何 `w:tbl` / 不在既有 SDT 内；整篇 0 表格 / 0 行 / 0 SDT）
        必须逐条现算等值。非空跑证明见 `TestGuardSelfChecks` 的两条注入反例。
        """
        for entry_record in record["entries"]:
            facts = _docx_facts(entry_record["sheet_code"])
            for field in entry_record["field_evidence"]:
                claims = field["negative_claims"]
                computed = facts["tokens"][field["token"]]["negative_claims"]
                assert claims == computed, (
                    f"{entry_record['sheet_code']}/{field['stable_field_key']}: "
                    f"negative_claims 声明 {claims} 与现算 {computed} 不等值"
                )
                assert claims["inside_w_tbl"] is False
                assert claims["inside_existing_sdt"] is False
                assert claims["document_has_w_tbl"] is False
                assert claims["document_has_w_tr"] is False
                assert claims["document_has_existing_sdt"] is False

    def test_carriers_and_anchors_come_only_from_the_task6_gate(
        self, contracts_on_disk: dict[str, dict], record: dict, gate: WI.WordSdtCarrierGate
    ) -> None:
        """**Validates: Requirements 7.4**

        载体只能取 Task 6 `downstream_gate.carriers_allowed_into_word_engine`，
        锚点只能 `w_tag`。出现 `row_sdt` 或用 `paragraph_index`/`run_index` 作锚点 = 违反 gate。
        """
        allowed = set(_load(CARRIER_CONTRACT)["downstream_gate"]["carriers_allowed_into_word_engine"])
        blocked = set(_load(CARRIER_CONTRACT)["downstream_gate"]["carriers_blocked"])
        assert "row_sdt" in blocked, "Task 6 的 blocked 名单里没有 row_sdt ⇒ 本判据失去对象"
        assert record["probe_gate"]["carriers_allowed_into_word_engine"] == sorted(
            allowed
        ) or set(record["probe_gate"]["carriers_allowed_into_word_engine"]) == allowed, (
            "发布记录抄的 allowlist 与探针 JSON 现读不一致"
        )
        assert set(record["probe_gate"]["carriers_blocked"]) == blocked
        assert record["probe_gate"]["anchors_allowed"] == ["w_tag"]
        for entry in GEN.ENTRIES:
            payload = contracts_on_disk[entry.contract_id]
            carriers = set(payload["identity_carriers"])
            assert carriers <= allowed, f"{entry.sheet_code}: 契约载体越界 {carriers - allowed}"
            assert carriers & blocked == set(), f"{entry.sheet_code}: 契约用了 blocked 载体"
            for carrier in sorted(carriers):
                gate.assert_carrier_allowed(carrier)
            declared = {decl.carrier for decl in entry.fields}
            assert declared <= allowed, f"{entry.sheet_code}: 声明侧载体越界 {declared - allowed}"

    def test_no_paragraph_or_run_ordinal_is_used_as_a_runtime_anchor(
        self, contracts_on_disk: dict[str, dict], record: dict
    ) -> None:
        """**Validates: Requirements 7.4**

        `p{NN}` 只准出现在 `source_ref`（一次性迁移线索）里。任何字段级键名带
        `paragraph_index` / `run_index` = 违反 Task 6 的 `anchors_blocked`。
        """
        for entry in GEN.ENTRIES:
            payload = contracts_on_disk[entry.contract_id]
            flat = json.dumps(payload, ensure_ascii=False)
            for word in FORBIDDEN_ANCHOR_WORDS:
                assert word not in flat, (
                    f"{entry.sheet_code}: 契约里出现被裁 failed 的锚点 {word!r}"
                )
            assert "row_sdt" not in flat, f"{entry.sheet_code}: 契约里出现 blocked 载体 row_sdt"
            for field in payload["fields"]:
                assert field["sdt_tag"].startswith(("gt:field:", "gt:block:"))
                assert f":{entry.contract_id}:" in field["sdt_tag"], (
                    "sdt_tag 的 contract 段必须是本 entry 自己的 contract_id"
                )
        semantics = record["source_ref_semantics"]
        assert semantics["runtime_locator"].startswith("w:tag"), semantics["runtime_locator"]
        assert "${token}" in semantics["one_time_migration_hints"]
        assert any("p{NN}" in hint for hint in semantics["one_time_migration_hints"])

    def test_row_scoped_total_is_zero_because_the_documents_have_no_rows(
        self, record: dict, contracts_on_disk: dict[str, dict]
    ) -> None:
        """**Validates: Requirements 7.4**

        🔴 `row_scoped_fields_total == 0` 必须由**现读文档**证明（0 `w:tbl` / 0 `w:tr`）+
        契约里 0 个 row-scoped 字段，而不是抄结论。
        """
        for entry in GEN.ENTRIES:
            facts = _docx_facts(entry.sheet_code)
            assert facts["w_tbl"] == 0 and facts["w_tr"] == 0, (
                f"{entry.sheet_code} 现算有表格/行 ⇒ row_scoped_fields_total=0 的前提不成立"
            )
            payload = contracts_on_disk[entry.contract_id]
            assert "repeaters" not in payload, f"{entry.sheet_code} 契约出现 repeaters"
            row_scoped = [
                f for f in payload["fields"] if f["stable_field_key"].startswith("rows/")
            ]
            assert row_scoped == [], f"{entry.sheet_code}: 出现行域字段 {row_scoped}"
        assert record["counters"]["row_scoped_fields_total"] == 0
        for entry_record in record["entries"]:
            spec = entry_record["instrumentation_spec"]
            assert spec["row_injections"] == 0
            assert spec["row_injections_why_zero"].strip(), "0 行注入的理由必须写明"

    def test_the_digest_chain_recomputes_from_the_authoritative_bytes(
        self, record: dict, contracts_on_disk: dict[str, dict], gate: WI.WordSdtCarrierGate
    ) -> None:
        """**Validates: Requirements 7.3**

        template → instrumentation → contract 三段 digest 全部现算等值（impl 现读，不抄快照）。
        """
        for entry_record in record["entries"]:
            entry = _entry_decl(entry_record["sheet_code"])
            data = entry.template_path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry_record["template_sha256"]
            assert WI.word_structure_hash(data) == entry_record[
                "template_normalized_structure_hash"
            ]
            facts = GEN.token_facts(data)
            spec = GEN.build_instrumentation_spec(entry, facts)
            template_payload = WI.build_word_template_payload(
                spec=spec,
                template_sha256=entry_record["template_sha256"],
                structure_hash=entry_record["template_normalized_structure_hash"],
            )
            template_digest = canonical_digest(template_payload)
            assert template_digest == entry_record["template_definition"][
                "definition_sha256"
            ]
            instrumentation_payload = WI.build_word_instrumentation_payload(
                spec=spec,
                template_definition_sha256=template_digest,
                template_sha256=entry_record["template_sha256"],
                gate=gate,
            )
            instrumentation_digest = canonical_digest(instrumentation_payload)
            assert instrumentation_digest == entry_record["instrumentation_definition"][
                "definition_sha256"
            ]
            payload = contracts_on_disk[entry.contract_id]
            assert payload["template_definition_sha256"] == template_digest
            assert payload["instrumentation_definition_sha256"] == instrumentation_digest
            parsed = C.parse_contract(payload, adapter_id=entry.contract_id)
            assert parsed.canonical_sha256 == entry_record["contract"]["canonical_sha256"]
            assert canonical_digest(
                entry_record["authority_model"]["definition_payload"]
            ) == entry_record["authority_model"]["definition_sha256"]


# ════════════════════════════════════════════════════════════════════════════
# 判据三：counters 全族现算等值 + counting_notes 覆盖面元判据
# ════════════════════════════════════════════════════════════════════════════
def _recompute_counters(record: dict) -> dict[str, Any]:
    """从 `entries` 现算全部 20 个计数键（配方即 `counting_notes` 声明的那套）。"""
    entries = record["entries"]
    field_rows = [row for e in entries for row in e["field_evidence"]]
    return {
        "lane_entries": len(entries),
        "contracts_published_reviewed": sum(
            1 for e in entries if e["contract"]["review_status"] == "reviewed"
        ),
        "contracts_installed_into_production_inventory": sum(
            1
            for e in entries
            if e["contract"]["contract_id"] in C.available_contract_ids()
        ),
        "authority_models_published": sum(
            1 for e in entries if (e["authority_model"] or {}).get("definition_sha256")
        ),
        "definition_bundles_published": sum(
            1 for e in entries if e["definition_bundle"] is not None
        ),
        "published_representations_finalized": sum(
            1 for e in entries if e["published_representation"] is not None
        ),
        "adapters_registered": sum(1 for e in entries if e["adapter_id"] is not None),
        "capability_verdict_pending": sum(1 for e in entries if e["capability"] is None),
        "adjudicated_as_bidirectional": sum(
            1 for e in entries if e["capability"] == "bidirectional"
        ),
        "adjudicated_as_single_onlyoffice": sum(
            1 for e in entries if e["capability"] == "single_onlyoffice"
        ),
        "adjudicated_as_single_html": sum(
            1 for e in entries if e["capability"] == "single_html"
        ),
        "adjudicated_as_unreachable": sum(
            1 for e in entries if e["capability"] == "unreachable"
        ),
        "entries_left_unverifiable": sum(
            1 for e in entries if e["evidence"]["verification_state"] == "UNVERIFIABLE"
        ),
        "managed_fields_total": len(field_rows),
        "managed_fields_by_entry": {
            e["sheet_code"]: len(e["field_evidence"]) for e in entries
        },
        "multi_instance_fields_total": sum(
            1 for row in field_rows if row["occurrences_in_document_xml"] > 1
        ),
        "block_carrier_fields_total": sum(
            1 for row in field_rows if row["carrier"] == "field_sdt_block"
        ),
        "row_scoped_fields_total": sum(
            len(_load(STAGED_DIR / f"{e['contract']['contract_id']}.json").get("repeaters", []))
            for e in entries
        ),
        "second_pipeline_endpoints_deleted": sum(
            1
            for plan in record["second_pipeline_deletion_plan"]["delegate_then_delete"]
            for endpoint in plan["endpoints"]
            if not _endpoint_still_in_source(endpoint)
        ),
    }


#: `counting_notes` 里允许的**族级**写法：`adjudicated_as_*` 覆盖同前缀的四个桶。
#: 🔴 只允许「前缀 + `*`」这一种通配，且通配前缀必须至少 12 字符 —— 否则 `a*` 就能
#: 一口气「覆盖」全部键，覆盖面元判据当场退化成恒真。
_WILDCARD_RE = re.compile(r"[a-z_]{12,}\*")


def _mentioned_in(notes: str, key: str) -> bool:
    if key in notes:
        return True
    for pattern in _WILDCARD_RE.findall(notes):
        if key.startswith(pattern[:-1]):
            return True
    return False


def _endpoint_route(endpoint: str) -> str:
    """`POST /api/workpapers/{wp_id}/f2-st/plan-sync-to-oo` → `f2-st/plan-sync-to-oo`。"""
    return endpoint.split("/api/workpapers/{wp_id}/", 1)[1]


def _endpoint_still_in_source(endpoint: str) -> bool:
    """路由是否**仍在源码里**（现读两个 writer 模块的整行集合）。"""
    route = _endpoint_route(endpoint)
    for path in (PLAN_WRITER_PY, SUMMARY_WRITER_PY):
        if any(route in line for line in _lines_of(path)):
            return True
    return False


class TestCountersRecomputeFromEntries:
    """20 个计数键逐一现算等值 + `counting_notes` 的覆盖面元判据（Decision 13/16）。"""

    def test_every_counter_recomputes_from_the_entries(self, record: dict) -> None:
        """**Validates: Requirements 12.10**"""
        declared = record["counters"]
        computed = _recompute_counters(record)
        numeric_keys = sorted(k for k in declared if k != "counting_notes")
        assert _same_sequence(numeric_keys, sorted(computed)), (
            f"计数键集合不等值：声明 {numeric_keys} vs 现算 {sorted(computed)}"
        )
        for key in numeric_keys:
            assert declared[key] == computed[key], (
                f"counter `{key}`：声明 {declared[key]!r} 与现算 {computed[key]!r} 不等值"
            )

    def test_counting_notes_covers_every_numeric_key(self, record: dict) -> None:
        """🔴 覆盖面**元判据**：`counting_notes` 提到的键的并集必须覆盖全部数值键。

        少提一个键 ⇒ 那族计数没有可复算配方，等于自由文本 ⇒ 打红。
        """
        notes = record["counters"]["counting_notes"]
        numeric_keys = [k for k in record["counters"] if k != "counting_notes"]
        missing = [key for key in numeric_keys if not _mentioned_in(notes, key)]
        assert missing == [], f"counting_notes 没写这些键的配方：{missing}"
        # 反向：另起一族的键必须报缺（否则通配符匹配写宽了、元判据退化成恒真）
        assert not _mentioned_in(notes, "fabricated_family_total"), (
            "通配符匹配写得太宽 ⇒ 覆盖面元判据会把没写配方的键也算成已覆盖"
        )
        # 通配符族的**基数**也要锁：notes 写「四项」，键就必须恰好 4 个 ——
        # 否则以后加第五个桶只靠通配符就“自动被覆盖”，配方与事实脱钩。
        buckets = sorted(k for k in numeric_keys if k.startswith("adjudicated_as_"))
        assert len(buckets) == 4, f"adjudicated_as_* 现算 {len(buckets)} 个：{buckets}"
        assert "四项" in notes, "notes 不再声明该族基数 ⇒ 通配符成了无限授权"
        assert len(numeric_keys) == 19, (
            f"数值键现算 {len(numeric_keys)} 个（预期 19 + counting_notes = 20）"
        )

    def test_the_field_totals_are_non_vacuous_and_split_per_entry(self, record: dict) -> None:
        """**Validates: Requirements 7.4**"""
        counters = record["counters"]
        assert counters["managed_fields_total"] == 33
        assert counters["managed_fields_by_entry"] == {"F2-22": 17, "F2-23": 16}
        assert sum(counters["managed_fields_by_entry"].values()) == counters[
            "managed_fields_total"
        ]
        assert counters["multi_instance_fields_total"] == 2, (
            "多实例字段现算不是 2 ⇒ Property 32 的分母变了"
        )
        assert counters["block_carrier_fields_total"] == 2, (
            "block 载体字段现算不是 2 ⇒ 「两种载体都用到」的分母变了"
        )

    def test_multi_instance_and_block_carrier_denominators_are_really_non_empty(
        self, record: dict
    ) -> None:
        """两个非零族也要证明「不是恒零」：逐条指出是哪个字段。"""
        multi = [
            (e["sheet_code"], row["stable_field_key"])
            for e in record["entries"]
            for row in e["field_evidence"]
            if row["occurrences_in_document_xml"] > 1
        ]
        block = [
            (e["sheet_code"], row["stable_field_key"])
            for e in record["entries"]
            for row in e["field_evidence"]
            if row["carrier"] == "field_sdt_block"
        ]
        assert multi == [("F2-22", "plan/entity_name"), ("F2-23", "summary/entity_name")], multi
        assert block == [("F2-22", "plan/warehouses"), ("F2-23", "summary/conclusion")], block


# ════════════════════════════════════════════════════════════════════════════
# 判据四：六族 0 命中的非空跑证明（Decision 13）
# ════════════════════════════════════════════════════════════════════════════
class TestSixZeroFamiliesAreNonVacuous:
    """不能只断言「== 0」—— 每族都要证明「分母存在且判据能命中」。"""

    def test_contracts_installed_into_production_inventory_is_zero_but_the_scan_works(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.3**

        分母 = `contracts.available_contract_ids()`（现扫生产目录）。它必须**非空**，
        且本 lane 的两个 id 都不在其中；同时 `load_contract` 必须真的抛。
        """
        available = C.available_contract_ids()
        assert len(available) >= 4, (
            f"生产契约清册现扫只有 {len(available)} 条 ⇒ 「本 lane 不在其中」的分母可疑"
        )
        for entry in GEN.ENTRIES:
            assert entry.contract_id not in available, (
                f"{entry.contract_id} 已进生产清册 ⇒ BP-10 被绕过"
            )
            with pytest.raises(Exception) as excinfo:
                C.load_contract(entry.contract_id)
            assert not isinstance(excinfo.value, AssertionError), (
                "load_contract 抛的是 AssertionError ⇒ 说明不是生产校验路径"
            )
            assert not (PRODUCTION_CONTRACT_DIR / f"{entry.contract_id}.json").exists()
        assert record["counters"]["contracts_installed_into_production_inventory"] == 0
        assert record["cross_entry_isolation"]["production_contract_dir_untouched"] is True

    def test_definition_bundles_published_is_zero_and_the_planned_slots_are_rejected(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.10**

        BP-11 的**正向**断言：把 `bundle_slot_plan` 的三个 slot 交给生产门，必须逐个被拒
        （`slot_ref=None` ⇒ `definition:<uuid>` 不成立）。绝不为凑 non-null 造假 uuid。
        """
        rejected = 0
        for entry_record in record["entries"]:
            assert entry_record["definition_bundle"] is None
            plan = entry_record["bundle_slot_plan"]
            assert plan["publishable_now"] is False
            assert plan["blocked_by"], "阻断项不能为空数组"
            for name, slot in sorted(plan["slots"].items()):
                spec = M.BundleSlotSpec(
                    slot=M.BundleSlot(name),
                    slot_type=slot["slot_type"],
                    slot_ref=slot["slot_ref"],
                    slot_digest=slot["slot_digest"],
                )
                with pytest.raises(M.BundleIntegrityError):
                    M.validate_bundle_slot(spec)
                rejected += 1
                # 反向：补上合法 ref 后必须通过 ⇒ 证明被拒的原因正是缺 ref，不是别的
                M.validate_bundle_slot(
                    M.BundleSlotSpec(
                        slot=M.BundleSlot(name),
                        slot_type=slot["slot_type"],
                        slot_ref="definition:11111111-2222-3333-4444-555555555555",
                        slot_digest=slot["slot_digest"],
                    )
                )
        assert rejected == 6, f"只跑了 {rejected} 个 slot（预期 2 entry × 3 slot）"
        assert record["counters"]["definition_bundles_published"] == 0

    def test_published_representations_finalized_is_zero_and_publish_is_gated(
        self, record: dict, contracts_on_disk: dict[str, dict]
    ) -> None:
        """**Validates: Requirements 7.3**

        离线 binding 的 `assert_may_publish()` 必须恒抛 ⇒ 「candidate 不得带入运行态」有门。
        """
        for entry in GEN.ENTRIES:
            binding = _binding(contracts_on_disk[entry.contract_id], entry_id=entry.contract_id)
            assert binding.mode is WE.WordEngineMode.offline_candidate_validation
            with pytest.raises(WE.WordApprovedBundleRequiredError):
                binding.assert_may_publish()
            assert binding.frozen_identity["definition_bundle_id"] is None
            assert binding.frozen_identity["definition_bundle_sha256"] is None
        for entry_record in record["entries"]:
            assert entry_record["published_representation"] is None
            assert entry_record["published_representation_blocked_by"], "阻断项不能为空"
        assert record["counters"]["published_representations_finalized"] == 0

    def test_adapters_registered_is_zero_and_the_registry_has_no_lane_row(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.3**

        分母 = `DELIVERED_PER_ENTRY_CONTRACTS`（非空）+ `PENDING_ENGINE_ADAPTERS` 的
        `forbidden_paths`（Word adapter 未落地）。
        """
        delivered = RG.DELIVERED_PER_ENTRY_CONTRACTS
        assert len(delivered) >= 4, f"交付登记表现算只有 {len(delivered)} 行 ⇒ 分母可疑"
        lane_ids = {entry.contract_id for entry in GEN.ENTRIES}
        assert {row["contract_id"] for row in delivered} & lane_ids == set(), (
            "本 lane 的契约已进 DELIVERED_PER_ENTRY_CONTRACTS ⇒ 与 adapters_registered=0 矛盾"
        )
        pending = [row for row in RG.PENDING_ENGINE_ADAPTERS if row["document_type"] == "docx"]
        assert len(pending) == 1, "docx engine adapter 的 pending 登记必须恰 1 行"
        assert "60" in pending[0]["blocking_task"], (
            f"pending 行的 blocking_task={pending[0]['blocking_task']!r} 不含 60 ⇒ "
            "本任务与那道门脱钩"
        )
        for forbidden in pending[0]["forbidden_paths"]:
            assert not (BACKEND / forbidden).exists(), (
                f"Word adapter 已落地（{forbidden}）却仍登记为 pending"
            )
        for entry_record in record["entries"]:
            assert entry_record["adapter_id"] is None
            assert entry_record["adapter_blocked_by"], "阻断项不能为空"
        assert record["counters"]["adapters_registered"] == 0

    def test_the_four_capability_buckets_are_zero_and_the_bucketing_can_fire(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.10**

        四个 `adjudicated_as_*` 全 0 是因为两个 entry 的 capability 都是 `null`；
        分桶器本身能命中（把 capability 换成任一枚举值，对应桶就变 1）。
        """
        counters = record["counters"]
        for bucket in (
            "adjudicated_as_bidirectional",
            "adjudicated_as_single_onlyoffice",
            "adjudicated_as_single_html",
            "adjudicated_as_unreachable",
        ):
            assert counters[bucket] == 0
        assert counters["capability_verdict_pending"] == len(record["entries"]) == 2
        # 非空跑证明：合成一个 capability 非空的副本，分桶必须变 1
        for value, bucket in (
            ("bidirectional", "adjudicated_as_bidirectional"),
            ("single_onlyoffice", "adjudicated_as_single_onlyoffice"),
            ("single_html", "adjudicated_as_single_html"),
            ("unreachable", "adjudicated_as_unreachable"),
        ):
            probe = json.loads(json.dumps(record))
            probe["entries"][0]["capability"] = value
            recomputed = _recompute_counters(probe)
            assert recomputed[bucket] == 1, (
                f"把 capability 改成 {value!r} 后 `{bucket}` 仍为 {recomputed[bucket]} ⇒ 分桶器是死代码"
            )
            assert recomputed["capability_verdict_pending"] == 1

    def test_second_pipeline_endpoints_deleted_is_zero_and_the_routes_are_still_there(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.7**

        本轮**不删任何调用点** ⇒ 四条路由必须仍在源码里现读得到，删除计数才是可复算的 0。
        """
        plans = record["second_pipeline_deletion_plan"]["delegate_then_delete"]
        endpoints = [ep for plan in plans for ep in plan["endpoints"]]
        assert len(endpoints) == 4, f"第二流程端点现算 {len(endpoints)} 条（预期 4）"
        for endpoint in endpoints:
            assert _endpoint_still_in_source(endpoint), (
                f"{endpoint} 在源码里找不到了 ⇒ 要么本轮误删了调用点，要么路由被改名"
            )
        assert record["counters"]["second_pipeline_endpoints_deleted"] == 0
        assert record["second_pipeline_deletion_plan"]["delete_files"] == []
        # 非空跑证明：伪造一个不存在的路由，删除计数必须变 1
        probe = json.loads(json.dumps(record))
        probe["second_pipeline_deletion_plan"]["delegate_then_delete"][0]["endpoints"][0] = (
            "POST /api/workpapers/{wp_id}/f2-st/plan-sync-to-oo-DELETED"
        )
        assert _recompute_counters(probe)["second_pipeline_endpoints_deleted"] == 1, (
            "路由改成不存在的形态后删除计数仍为 0 ⇒ 该判据是装饰"
        )


# ════════════════════════════════════════════════════════════════════════════
# 判据五：Property 31 —— Word-only 正文保留（真契约、真模板、真往返）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty31WordOnlyPreserved:
    """design 原文：「两次 HTML materialize 前后，所有 SDT 外 OOXML 正文节点规范化内容相等。」"""

    @pytest.mark.parametrize("sheet_code", ["F2-22", "F2-23"])
    def test_two_materialize_passes_keep_every_non_sdt_node(
        self,
        sheet_code: str,
        workdir: Path,
        gate: WI.WordSdtCarrierGate,
        contracts_on_disk: dict[str, dict],
    ) -> None:
        """**Validates: Requirements 7.3**"""
        entry = _entry_decl(sheet_code)
        payload = contracts_on_disk[entry.contract_id]
        binding = _binding(payload, entry_id=entry.contract_id)
        substrate = _substrate(sheet_code, workdir, gate)
        base = _extract(substrate, binding)
        first = workdir / f"{sheet_code}-p31-pass1.docx"
        second = workdir / f"{sheet_code}-p31-pass2.docx"
        WE.materialize_word_projection(
            substrate=substrate,
            projection=_projection_for(payload, seed="第一次"),
            output=first,
            binding=binding,
            substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.staged,
        )
        WE.materialize_word_projection(
            substrate=first,
            projection=_projection_for(payload, seed="第二次（更长的中文文本）"),
            output=second,
            binding=binding,
            substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.staged,
        )
        after = _extract(second, binding)
        assert after.word_only_digest == base.word_only_digest, (
            f"{sheet_code}: 两次 materialize 后 SDT 外正文 digest 变了"
        )
        report = WE.verify_word_only_regions(before=substrate, after=second, binding=binding)
        assert report.equivalent, report.first_difference
        # 🔴 防「空集恒等价」：四个 aspect 必须有真实覆盖；另两个**如实**为 0 ——
        #    本 lane 现算 0 `w:tbl` / 0 `w:tr` ⇒ `table_shape` 与 `managed_row_identity`
        #    没有对象。把它们也要求 > 0 会造出永远打不过的假判据；写成「必须是 0」
        #    则一旦源模板将来加了表格，本条会打红提示重判（两个方向都不放过）。
        coverage = report.details["coverage"]
        for aspect in ("outside_sdt_text", "sdt_tag_set", "sdt_hierarchy", "protected_parts"):
            assert coverage[aspect] > 0, (
                f"{sheet_code}: aspect `{aspect}` 覆盖计数为 0 ⇒ 「空集恒等价」，等价结论无效"
            )
        for aspect in ("table_shape", "managed_row_identity"):
            assert coverage[aspect] == 0, (
                f"{sheet_code}: aspect `{aspect}` 覆盖计数变成 {coverage[aspect]} ⇒ "
                "源模板出现了表格/行载体，row_scoped_fields_total=0 与载体裁决都要重做"
            )
        assert set(coverage) == set(WE.WORD_ONLY_ASPECTS) | {"managed_row_identity"}, (
            f"aspect 集合变了：{sorted(coverage)} vs {sorted(WE.WORD_ONLY_ASPECTS)}"
        )

    @pytest.mark.parametrize("sheet_code", ["F2-22", "F2-23"])
    def test_word_only_drift_is_detected(
        self,
        sheet_code: str,
        workdir: Path,
        gate: WI.WordSdtCarrierGate,
        contracts_on_disk: dict[str, dict],
    ) -> None:
        """反向：删掉一段 SDT 外自由正文必须打红（否则上一条是空转）。"""
        entry = _entry_decl(sheet_code)
        binding = _binding(contracts_on_disk[entry.contract_id], entry_id=entry.contract_id)
        substrate = _substrate(sheet_code, workdir, gate)
        base_xml = GEN.document_xml(substrate.read_bytes())
        victim = _an_outside_sdt_wt_element(base_xml)
        broken = workdir / f"{sheet_code}-word-only-drift.docx"
        broken.write_bytes(
            _rewrite_document(
                substrate.read_bytes(), lambda xml: xml.replace(victim, "<w:t></w:t>", 1)
            )
        )
        # 🔴 构造前提必须自证：若 replace 是空操作，下面的「必须打红」会变成假绿。
        #    Task 59 的同款判据用 `outside_sdt_blocks` 的**规范化文本**做 replace，在本 lane
        #    的 17 字段注入下那些文本是跨 run 拼出来的、并不逐字出现在 XML 里 ⇒ 空操作。
        assert GEN.document_xml(broken.read_bytes()) != base_xml, (
            "反例没造出来（replace 是空操作）⇒ 本条判据无效"
        )
        report = WE.verify_word_only_regions(before=substrate, after=broken, binding=binding)
        assert not report.equivalent
        assert "outside_sdt_text" in (report.first_difference or "")
        with pytest.raises(WE.UnmanagedRegionDriftError):
            report.assert_equivalent()

    @pytest.mark.parametrize("sheet_code", ["F2-22", "F2-23"])
    def test_materialize_only_touches_the_structured_islands(
        self,
        sheet_code: str,
        workdir: Path,
        gate: WI.WordSdtCarrierGate,
        contracts_on_disk: dict[str, dict],
    ) -> None:
        """**Validates: Requirements 7.9**

        AC 7.9 原文：「HTML materialize SHALL 只更新结构化岛；不得用模板重生成覆盖审计师已
        编辑的 Word-only 内容。」判据 = materialize 结果里 SDT 外正文与 substrate 逐字相同，
        且**不是**从权威模板重新拷一份（否则 SDT 内的旧值会一并回退）。
        """
        entry = _entry_decl(sheet_code)
        payload = contracts_on_disk[entry.contract_id]
        binding = _binding(payload, entry_id=entry.contract_id)
        substrate = _substrate(sheet_code, workdir, gate)
        # 先在 SDT **外**写一段「审计师编辑」，它必须在 materialize 后原样保留
        edited = workdir / f"{sheet_code}-ac79-edited.docx"
        marker = "【审计师手写：本段属 Word-only 区域】"
        edited.write_bytes(
            _rewrite_document(
                substrate.read_bytes(),
                lambda xml: xml.replace(
                    "</w:body>",
                    f"<w:p><w:r><w:t>{marker}</w:t></w:r></w:p></w:body>",
                    1,
                ),
            )
        )
        out = workdir / f"{sheet_code}-ac79-materialized.docx"
        WE.materialize_word_projection(
            substrate=edited,
            projection=_projection_for(payload, seed="AC79"),
            output=out,
            binding=binding,
            substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.staged,
        )
        result_xml = GEN.document_xml(out.read_bytes())
        assert marker in result_xml, (
            "审计师在 SDT 外写的段落被 materialize 抹掉了 ⇒ 违反 AC 7.9"
        )
        report = WE.verify_word_only_regions(
            before=edited, after=out, binding=binding
        )
        assert report.equivalent, report.first_difference
        # 反向：证明该 marker 不在权威模板里 ⇒ 若实现改成「从模板重生成」，上面必红
        assert marker not in GEN.document_xml(entry.template_path.read_bytes())


# ════════════════════════════════════════════════════════════════════════════
# 判据六：Property 32 —— Word 多实例异值冲突
# ════════════════════════════════════════════════════════════════════════════
class TestProperty32DuplicateWordInstances:
    """design 原文：「同 stable tag 多实例出现不同值时生成 duplicate conflict，并列出全部 XPath。」"""

    @pytest.mark.parametrize(
        ("sheet_code", "stable_key"),
        [("F2-22", "plan/entity_name"), ("F2-23", "summary/entity_name")],
    )
    def test_identical_values_merge_without_a_conflict(
        self,
        sheet_code: str,
        stable_key: str,
        workdir: Path,
        gate: WI.WordSdtCarrierGate,
        contracts_on_disk: dict[str, dict],
    ) -> None:
        """**Validates: Requirements 7.4**（前半句：值一致时可合并）"""
        entry = _entry_decl(sheet_code)
        binding = _binding(contracts_on_disk[entry.contract_id], entry_id=entry.contract_id)
        outcome = _extract(_substrate(sheet_code, workdir, gate), binding)
        instances = [i for i in outcome.instances if i.tag.stable_key == stable_key]
        assert len(instances) == 2, (
            f"{sheet_code}/{stable_key} 现算只有 {len(instances)} 个实例 ⇒ 本判据空转"
        )
        assert stable_key in outcome.projection.values
        assert [
            c for c in outcome.conflicts if c.kind is ConflictKind.duplicate_word_instance
        ] == []

    @pytest.mark.parametrize(
        ("sheet_code", "stable_key", "token"),
        [
            ("F2-22", "plan/entity_name", "${entityName}"),
            ("F2-23", "summary/entity_name", "${entityName}"),
        ],
    )
    def test_divergent_values_produce_a_conflict_listing_every_xpath(
        self,
        sheet_code: str,
        stable_key: str,
        token: str,
        workdir: Path,
        gate: WI.WordSdtCarrierGate,
        contracts_on_disk: dict[str, dict],
    ) -> None:
        """**Validates: Requirements 7.4**（后半句：异值 ⇒ 冲突 + 列出全部 OO 位置）"""
        entry = _entry_decl(sheet_code)
        payload = contracts_on_disk[entry.contract_id]
        binding = _binding(payload, entry_id=entry.contract_id)
        tag = next(f["sdt_tag"] for f in payload["fields"] if f["stable_field_key"] == stable_key)

        def mutate(xml: str) -> str:
            marker = f'<w:tag w:val="{tag}"/>'
            first = xml.find(marker)
            second = xml.find(marker, first + 1)
            assert second > first > -1, f"{sheet_code}: 文档里没有两个 {tag} 实例"
            head, tail = xml[:second], xml[second:]
            return head + tail.replace(token, "乙公司", 1)

        path = workdir / f"{sheet_code}-p32-divergent.docx"
        path.write_bytes(_rewrite_document(_substrate(sheet_code, workdir, gate).read_bytes(), mutate))
        outcome = _extract(path, binding)
        dupes = [
            c for c in outcome.conflicts if c.kind is ConflictKind.duplicate_word_instance
        ]
        assert len(dupes) == 1, f"{sheet_code}: 异值实例没产出唯一 duplicate 冲突：{dupes}"
        record = dupes[0]
        assert len(record.word_instances) == 2, "必须列出**全部**实例位置（AC 7.4）"
        assert len({ref.xpath for ref in record.word_instances}) == 2, "两个 XPath 撞了"
        assert all(ref.xpath.startswith("/w:document") for ref in record.word_instances)
        assert {str(ref.value.value) for ref in record.word_instances} == {token, "乙公司"}
        assert stable_key not in outcome.projection.values, (
            "异值字段进了 projection ⇒ engine 自行选边（AC 7.4 不允许）"
        )


# ════════════════════════════════════════════════════════════════════════════
# 判据七：Property 47 / 69 明确不宣称通过
# ════════════════════════════════════════════════════════════════════════════
class TestProperty47AndProperty69AreNotClaimed:
    """只断言**前提 + 承载者存在 + `not_claimed` 登记在案**，不做通过性断言（Decision 10）。"""

    def test_not_claimed_is_registered_for_both(self, record: dict) -> None:
        """**Validates: Requirements 11.5**"""
        denominators = record["property_denominators"]
        assert _same_sequence(
            list(denominators["not_claimed"]), ["Property 47", "Property 69"]
        )
        assert denominators["why_not_claimed_is_recorded"].strip()
        assert _same_sequence(list(denominators["empty_denominator"]), ["Property 69"])
        assert _same_sequence(
            list(denominators["carrier_is_a_counterexample"]), ["Property 47"]
        )
        for name in denominators["not_claimed"]:
            claim = record["properties_verified"][name]["claim"]
            assert claim != "PASS", f"{name} 登记为不宣称，却又写着 {claim!r}"
            assert claim.startswith("NOT_CLAIMED"), claim

    def test_property_47_premise_is_recomputed_from_the_frontend_source(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 11.5**

        AC 11.5 原文见 `AC_TEXT['11.5']`。本 lane 的承载者**存在但形态相反**：
        1 个 `<GtOnlyOfficeSheet>` 挂载点、零 descriptor prop、组件自行请求 config。
        三项都从源码现读并与发布记录等值比对 —— 首版记录写「无挂载点」正是被这条抓出来的。
        """
        facts = record["descriptor_consumption"]
        host_lines = _lines_of(LANE_HOST_VUE)
        mount_lines = [
            i for i, line in enumerate(host_lines, 1) if "<GtOnlyOfficeSheet" in line
        ]
        assert facts["oo_mount_site_count"] == len(mount_lines) == 1, (
            f"OO 挂载点现算 {len(mount_lines)} 处，记录声明 {facts['oo_mount_site_count']} 处"
        )
        assert _same_sequence(list(facts["oo_mount_site_lines"]), mount_lines)
        assert facts["descriptor_props_on_the_mount"] == [], (
            "挂载点已带 descriptor prop ⇒ BP-12/BP-15 的前提变了，Property 47 要重新裁决"
        )
        # 门控也要**现算**，且必须在**挂载点自身的标签块**里找：
        # 🔴 宿主第 17 行另有一个 `v-else-if="dualMode.currentMode.value === 'onlyoffice' && …"`
        #    （「仅预览·无回写」提示 tag 的门控）。用全文 `any(...)` 时，把挂载点的 v-if 改成
        #    `v-if="true"` 仍判 true —— 该变异实测判过一次 GREEN，判据口径因此收窄到标签块。
        raw_lines = LANE_HOST_VUE.read_text(encoding="utf-8").split("\n")
        computed_gated = GEN.mount_is_mode_gated(raw_lines)
        assert facts["oo_mount_is_mode_gated"] is computed_gated is True, (
            f"mode 门控现算 {computed_gated}，记录声明 {facts['oo_mount_is_mode_gated']}"
        )
        block = GEN.mount_tag_block(raw_lines)
        assert 2 <= len(block) <= 20, f"挂载点标签块解析出 {len(block)} 行 ⇒ 解析器可疑"
        assert any("v-if" in line for line in block), (
            "挂载点标签块里没有 v-if ⇒ 门控口径失效"
        )
        oo_src = OO_SHEET_VUE.read_text(encoding="utf-8")
        assert "/onlyoffice-config`" in oo_src, (
            "GtOnlyOfficeSheet 不再自取 config ⇒ 记录里的反例判据失去对象"
        )
        assert facts["oo_component_self_fetches_config"] is True
        assert facts["oo_component_self_fetch_line"] == next(
            i for i, line in enumerate(oo_src.split("\n"), 1) if "/onlyoffice-config`" in line
        )
        # 挂载点确实服务本 lane 的两个 sheet（不是别的 tab）
        assert _same_sequence(
            list(facts["lane_sheet_codes_are_tabs_of_this_host"]), ["F2-22", "F2-23"]
        )
        for code in ("F2-22", "F2-23"):
            assert f"id: '{code}'" in LANE_HOST_VUE.read_text(encoding="utf-8"), (
                f"{code} 不再是该宿主的 tab ⇒ 挂载点归属要重判"
            )
        assert record["properties_verified"]["Property 47"]["denominator"] == 1
        assert facts["router_callback_has_a_lane_specific_docx_branch"] is True, (
            "callback 里那段 F2-22/F2-23 docx 回写分支不见了 ⇒ BP-15 的对象变了"
        )
        assert re.search(
            r'_save_wp_code in \("F2-22", "F2-23"\)',
            _strip_py_comments(OO_ROUTER_PY.read_text(encoding="utf-8")),
        ), "那段分支只存在于注释里 ⇒ 记录把注释当成了代码"

    def test_property_69_premise_is_an_empty_denominator(self, record: dict) -> None:
        """**Validates: Requirements 12.10**

        AC 12.10 要求逐 entry 的服务端 evidence summary；本 lane 一条都没有 ⇒ 分母为空。
        判据 = 每个 entry 的 evidence 三件（run id / scenario set digest / browser case）
        全 null 且 `verification_state == UNVERIFIABLE` 且 reasons 非空。
        """
        assert record["properties_verified"]["Property 69"]["denominator"] == 0
        for entry_record in record["entries"]:
            evidence = entry_record["evidence"]
            assert evidence["sync_test_run_id"] is None
            assert evidence["required_scenario_set_digest"] is None
            assert evidence["browser_case"] is None
            assert evidence["verification_state"] == "UNVERIFIABLE"
            assert evidence["unverifiable_reasons"], "UNVERIFIABLE 必须写明理由（禁空数组）"
            assert evidence["contract_test"] == (
                _THIS.relative_to(ROOT).as_posix()
            ), (
                f"entry 的 contract_test 指向 {evidence['contract_test']!r}，"
                f"本守卫实际路径是 {_THIS.relative_to(ROOT).as_posix()}"
            )

    def test_property_31_and_32_are_claimed_with_a_non_empty_denominator(
        self, record: dict
    ) -> None:
        """对照条：宣称通过的两条必须有非空分母与可复算的 how。"""
        for name in ("Property 31", "Property 32"):
            node = record["properties_verified"][name]
            assert node["claim"] == "PASS"
            assert node["denominator"] == 2 == len(record["entries"])
            assert node["how"].strip(), f"{name} 的通过方式必须写明"


# ════════════════════════════════════════════════════════════════════════════
# 判据八：逐条 AC
# ════════════════════════════════════════════════════════════════════════════
class TestAcceptanceCriteria:
    """AC 7.3 / 7.4 / 7.9 / 11.5 / 12.3 / 12.7 / 12.10 / 14.1 逐条落判据。"""

    def test_the_record_declares_exactly_the_nominated_acs(self, record: dict) -> None:
        assert _same_sequence(
            list(record["requirements_covered"]),
            ["7.3", "7.4", "7.9", "11.5", "12.3", "12.7", "12.10", "14.1"],
        )
        assert _same_sequence(sorted(AC_TEXT), sorted(record["requirements_covered"]))

    def test_ac_texts_are_quoted_verbatim_from_requirements_md(self) -> None:
        """🔴 AC 原文逐字锁：改了 requirements.md 而没改本文件必打红。"""
        req = (
            ROOT
            / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
            / "requirements.md"
        ).read_text(encoding="utf-8")
        for ac, text in sorted(AC_TEXT.items()):
            assert f"{ac}. {text}" in req or text in req, (
                f"AC {ac} 的原文在 requirements.md 里找不到 ⇒ AC 变了或引用抄错"
            )

    def test_ac_12_3_compliance_recomputes(self, record: dict) -> None:
        """**Validates: Requirements 12.3**

        AC 12.3 原文：pilot 必须是 F2-22/F2-23，且未过往返保留前不得批量迁移其他 DOCX。
        判据 = 权威册现算恰 2 条 + 两个 wp_code 恰为 F2-22/F2-23 + 平台上其他 docx 一张未动。
        """
        node = record["ac_12_3_compliance"]
        assert node["text_role"] in AC_TEXT["12.3"] or AC_TEXT["12.3"].startswith(
            node["text_role"][:20]
        )
        files = record["authoritative_templates"]["files"]
        assert len(files) == 2, f"权威册现算 {len(files)} 条（AC 12.3 只允许两份 docx）"
        assert _same_sequence(
            sorted(e["wp_code"] for e in record["entries"]), ["F2-22", "F2-23"]
        )
        for item in files:
            path = BACKEND / "wp_templates" / "F" / item["name"]
            assert path.is_file(), f"权威册登记的文件不存在：{path}"
            data = path.read_bytes()
            assert item["size"] == len(data) == path.stat().st_size
            assert item["sha256"] == hashlib.sha256(data).hexdigest(), (
                f"{item['name']} 的 sha256 漂移 ⇒ 本任务对模板只读的声明不成立"
            )
            assert item["normalized_structure_hash"] == WI.word_structure_hash(data)
        # 「不得批量迁移其他 DOCX」的可复算判据：其他 docx 一份契约也没有
        other = [
            p
            for p in (BACKEND / "wp_templates").rglob("*.docx")
            if not p.name.startswith("~$") and p.parent.name != "F"
        ]
        assert len(other) >= 20, f"平台其他 docx 现算只有 {len(other)} 张 ⇒ 反向分母可疑"
        staged = sorted(p.stem for p in STAGED_DIR.glob("*.json"))
        assert _same_sequence(staged, sorted(e.contract_id for e in GEN.ENTRIES)), (
            f"staged 契约目录里出现了非本 lane 的契约：{staged}"
        )

    def test_ac_7_3_and_7_9_have_carriers_in_the_engine_not_only_in_json(self) -> None:
        """**Validates: Requirements 7.3**

        AC 7.3 / 7.9 的承载者必须是**代码**：`verify_word_only_regions` +
        `WORD_ONLY_ASPECTS` 必须真实存在且覆盖 SDT 外正文。
        """
        assert callable(WE.verify_word_only_regions)
        assert "outside_sdt_text" in WE.WORD_ONLY_ASPECTS
        assert "protected_parts" in WE.WORD_ONLY_ASPECTS

    def test_ac_12_7_keeps_the_second_pipeline_but_registers_the_plan(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.7**

        AC 12.7 原文要求「删除前必须有等价证据和 rollback 点」⇒ 本轮**只生成计划**：
        每个模块都要写明 already_delegated / still_second_pipeline / delete_after /
        等价证据清单，且 `must_not_delete` 覆盖两份权威模板。
        """
        plan = record["second_pipeline_deletion_plan"]
        assert plan["delete_files"] == []
        assert plan["delete_files_why_empty"].strip()
        assert len(plan["delegate_then_delete"]) == 2
        for item in plan["delegate_then_delete"]:
            module = ROOT / item["module"]
            assert module.is_file(), f"计划指向的模块不存在：{item['module']}"
            assert item["already_delegated"].strip()
            assert item["still_second_pipeline"], "仍属第二流程的部分必须逐条写明"
            assert item["delete_after"], "删除前置必须写明"
            assert item["equivalence_evidence_required_by_ac_12_7"], (
                "AC 12.7 的等价证据清单不得为空"
            )
            assert len(item["endpoints"]) == 2
        must_not_delete = [ROOT / p for p in plan["must_not_delete"]]
        assert len(must_not_delete) == 2
        for path in must_not_delete:
            assert path.is_file(), f"must_not_delete 指向的文件不存在：{path}"
        assert {p.name for p in must_not_delete} == {
            e.template_path.name for e in GEN.ENTRIES
        }
        # 「先委派统一 coordinator」的**现读**证据：commit 侧已走统一 writer
        for path in (PLAN_WRITER_PY, SUMMARY_WRITER_PY):
            src = _strip_py_comments(path.read_text(encoding="utf-8"))
            assert "build_content_mutation_service_writer" in src, (
                f"{path.name} 的 commit 侧不再委派统一 writer ⇒ 记录里的 already_delegated 过期"
            )

    def test_ac_12_10_and_14_1_evidence_summary_is_absent_and_says_so(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.10**

        AC 12.10 / 14.1 只对 **bidirectional** entry 生效；本 lane 一个都不是 ⇒ 判据 =
        「两个 entry 都不是 bidirectional」+「evidence 明写 UNVERIFIABLE」+ BP-13 登记在案。
        """
        assert record["counters"]["adjudicated_as_bidirectional"] == 0
        assert record["counters"]["entries_left_unverifiable"] == len(record["entries"])
        bp_ids = [bp["id"] for bp in record["blocking_preconditions"]]
        assert "BP-13" in bp_ids
        bp13 = next(bp for bp in record["blocking_preconditions"] if bp["id"] == "BP-13")
        assert "12.10" in bp13["what"] and "14.1" in bp13["what"]
        assert bp13["status"] == "open"
        assert bp13["must_fix_before"].strip()

    def test_every_blocking_precondition_is_well_formed(self, record: dict) -> None:
        """每条 BP 都要有 blocks / what / status / must_fix_before / 后果 / source_refs。"""
        bps = record["blocking_preconditions"]
        ids = [bp["id"] for bp in bps]
        assert _same_sequence(
            ids, ["BP-10", "BP-11", "BP-12", "BP-13", "BP-14", "BP-15"]
        ), f"BP 编号集合变了：{ids}（BP-1..BP-9 属 F 循环 slice，本记录只续接 BP-10 起）"
        assert len(bps) == 6
        for bp in bps:
            assert bp["blocks"], f"{bp['id']} 的 blocks 为空"
            assert bp["what"].strip()
            assert bp["status"] == "open"
            assert bp["must_fix_before"].strip()
            assert bp["observable_consequences"], f"{bp['id']} 缺可观察后果"
            for ref in bp["source_refs"]:
                assert (ROOT / ref).exists(), f"{bp['id']} 的 source_ref 不存在：{ref}"

    def test_bp_14_is_carried_by_the_f2_22_contract_shape(self, record: dict) -> None:
        """BP-14（`${specialNotes}` 合并段）在契约上必须留下痕迹：docx 侧只有 1 个字段。

        🔴 BP-14 已在首版登记，本条只验证它的**对象仍在**（防「登记了但对象消失」）。
        """
        payload = _load(STAGED_DIR / f"{GEN.PLAN_ID}.json")
        special = [
            f for f in payload["fields"] if f["stable_field_key"] == "plan/special_notes"
        ]
        assert len(special) == 1, "docx 侧的 special_notes 不再是单字段 ⇒ BP-14 的形态变了"
        service = _strip_py_comments(PLAN_SERVICE_PY.read_text(encoding="utf-8"))
        assert "异地" in service and "舞弊" in service, (
            "plan sync service 里的中文标签拆分不见了 ⇒ BP-14 已被处置，请更新登记"
        )


# ════════════════════════════════════════════════════════════════════════════
# 判据九：candidate / unapproved / missing-contract bundle 不得进入运行态
# ════════════════════════════════════════════════════════════════════════════
class TestNothingUnapprovedReachesTheRuntime:
    """否定式判据 —— 到 resolver / registry / room 的**代码**里现查，不看 JSON 声明。"""

    def test_the_staged_contract_dir_has_no_production_consumer(self) -> None:
        """**Validates: Requirements 12.3**

        🔴 staged 目录名在 `backend/app/**` 里出现 0 次 ⇒ 运行态**根本读不到**它。
        这是「candidate 不入运行态」最直接的结构判据（比读 JSON 声明强）。
        """
        needle = STAGED_DIR.name
        hits = [
            p.relative_to(ROOT).as_posix()
            for p in (BACKEND / "app").rglob("*.py")
            if needle in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert hits == [], f"生产代码引用了 staged 契约目录：{hits}"
        # 反向分母：生产目录名在生产代码里**必须**出现（否则上面的 0 是恒真）
        production_hits = [
            p.relative_to(ROOT).as_posix()
            for p in (BACKEND / "app").rglob("*.py")
            if PRODUCTION_CONTRACT_DIR.name in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert production_hits, (
            "生产契约目录名在 backend/app 里一次都没出现 ⇒ 上一条的 0 是恒真，判据无效"
        )

    def test_no_lane_adapter_is_reachable_from_the_production_registry(self) -> None:
        """**Validates: Requirements 12.3**"""
        registry = RG.build_production_registry()
        report = registry.build_report()
        registered = set(report.registered_adapter_ids)
        # 分母自证：manifest entry 数非空（否则「没注册」是恒真）
        assert report.entry_count >= 100, (
            f"registry 现算 entry 数只有 {report.entry_count} ⇒ 「本 lane 未注册」的分母可疑"
        )
        for entry in GEN.ENTRIES:
            assert entry.contract_id not in registered
            assert entry.lane_entry_key not in registered
            with pytest.raises(RG.AdapterNotRegisteredError):
                registry.resolve_for_entry(entry.contract_id)
        for row in RG.DELIVERED_ENGINE_ADAPTERS:
            assert row["document_type"] != "docx", (
                "docx engine adapter 已登记为 delivered ⇒ 与 Task 60 的 adapters_registered=0 矛盾"
            )

    def test_an_unapproved_bundle_snapshot_is_refused_by_the_shared_gate(self) -> None:
        """**Validates: Requirements 12.10**

        `assert_bundle_usable` 是 Task 13 的共享门；这里证明它对「不是 approved」的
        snapshot 真的抛，而不是本 lane 自己写了个私有检查。
        """
        assert callable(RG.assert_bundle_usable)

        class _NotApproved:
            bundle_id = "11111111-2222-3333-4444-555555555555"
            bundle_sha256 = "a" * 64
            state = "candidate"
            authority_model = M.AuthorityModel.projection_contract
            slots: dict = {}

        with pytest.raises(Exception) as excinfo:
            RG.assert_bundle_usable(_NotApproved(), entry_id=GEN.PLAN_ID)  # type: ignore[arg-type]
        assert not isinstance(excinfo.value, AssertionError), (
            "抛的是 AssertionError ⇒ 说明走的不是生产门"
        )

    def test_the_lane_writers_still_declare_the_pre_task60_authority_model(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.7**

        两个 writer 仍用 `opaque_single_onlyoffice`（**不是** Task 60 要发布的
        `projection_contract`），而发布记录必须如实登记这个差异与切换条件（否则就是
        「声称已切换」的假绿）。

        🔴 判据载体迁移（Task 65），语义一字未放宽。原判据两条：
          正面 `"opaque_single_onlyoffice" in src` ——「仍是切换前那个 model」
          否定 `"projection_contract" not in src` ——「没有偷偷切过去」
        `commit_bytes` 的 `authority_model` 参数已被删除，authority model 改由
        `lane_id` 经 lane 登记表单向决定 ⇒ 两条都搬到新载体上，且**否定式那条同时保留
        源码形态与登记表形态**：源码里不得出现 `projection_contract`，登记表解出来的也
        不得是它。任一侧偷偷切换都打红。
        """
        OG = _lane_registry()
        by_writer = {str(e["wired_writer"]): e for e in record["entries"]}
        assert len(by_writer) == 2, f"记录里的 wired_writer 实得 {sorted(by_writer)}"

        for path in (PLAN_WRITER_PY, SUMMARY_WRITER_PY):
            src = _strip_py_comments(path.read_text(encoding="utf-8"))
            lane_id = _commit_bytes_lane_id(path)
            lane = OG.lane_for(lane_id)  # 未登记即抛
            module = "app." + (
                path.relative_to(BACKEND / "app").with_suffix("").as_posix().replace("/", ".")
            )
            assert (lane.writer_module, lane.writer_qualname) == (module, "_save_fields"), (
                f"{path.name} 传的 lane_id={lane_id!r} 登记在 {lane.writer_ref} 名下 —— "
                "借用另一条 lane 的身份会让本记录登记的 authority model 差异失真"
            )
            # ① 正面：仍是切换前那个 authority model（现从登记表解，不再 grep 枚举名）
            assert (
                OG.authority_model_for_lane(lane_id)
                is M.AuthorityModel.opaque_single_onlyoffice
            ), (
                f"{path.name} 的 authority model 已变成 "
                f"{OG.authority_model_for_lane(lane_id).value} ⇒ 本记录登记的"
                "「writer 仍用 opaque_single_onlyoffice」与切换条件全部过期"
            )
            # ② 否定：两侧都不得已经切到 projection_contract（防「声称已切换」的假绿）
            assert "projection_contract" not in src, (
                f"{path.name} 已切到 projection_contract ⇒ 记录的 switch_condition 过期"
            )
            assert (
                OG.authority_model_for_lane(lane_id)
                is not M.AuthorityModel.projection_contract
            ), f"{path.name} 的 lane 登记已切到 projection_contract ⇒ switch_condition 过期"
            # ③ 记录侧与登记表锁死：`currently_used_by_writer` 不再是一句自述
            slice_key = path.relative_to(ROOT).as_posix()
            assert slice_key in by_writer, (
                f"记录里没有 wired_writer={slice_key} 的条目，实有 {sorted(by_writer)}"
            )
            entry = by_writer[slice_key]
            assert (
                entry["authority_model"]["currently_used_by_writer"]
                == OG.authority_model_for_lane(lane_id).value
            ), (
                f"记录声称 {entry['sheet_code']} 的 writer 在用 "
                f"{entry['authority_model']['currently_used_by_writer']!r}，而登记表现算的是 "
                f"{OG.authority_model_for_lane(lane_id).value!r}"
            )

    def test_bp10_root_cause_is_recomputable_from_the_source_manifest(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.3**

        BP-10 的根因（「本 lane 在 source-backed manifest 里没有 entry」）必须**现算**：
        manifest 里 `document_type=='docx'` 的 entry 数、其中 wp_code 前缀为 F 的条数，
        都从 manifest 现读，并与每个 entry 的 `manifest_entry_state` 及 `..._recipe`
        里写的数字逐一等值。否则「没有 entry」只是自述，改一句声明就能翻案。
        """
        manifest = _load(ENTRY_MANIFEST)
        docx_entries = [e for e in manifest["entries"] if e.get("document_type") == "docx"]
        f_prefixed = [
            e
            for e in docx_entries
            if any(
                str(p).upper().startswith("F")
                for p in ((e.get("wp_match") or {}).get("wp_code_patterns") or [])
            )
        ]
        assert len(docx_entries) >= 5, (
            f"manifest 里 docx entry 现算只有 {len(docx_entries)} 条 ⇒ 反向分母可疑"
        )
        assert f_prefixed == [], (
            f"manifest 里出现了 F 前缀的 docx entry {[e.get('entry_id') for e in f_prefixed]} ⇒ "
            "BP-10 的根因已消失，契约装载的裁决要重做"
        )
        for entry_record in record["entries"]:
            assert entry_record["manifest_entry_state"] == "absent_from_source_manifest", (
                f"{entry_record['sheet_code']} 声称已在 manifest 里，而现算 F 前缀 docx entry "
                "为 0 ⇒ 两处对不上"
            )
            numbers = [int(x) for x in re.findall(r"\d+", entry_record["manifest_entry_absence_recipe"])]
            assert numbers == [len(docx_entries), len(f_prefixed)], (
                f"{entry_record['sheet_code']} 的 absence_recipe 写的数字 {numbers} 与现算 "
                f"[{len(docx_entries)}, {len(f_prefixed)}] 不等值"
            )
            for ref in entry_record["manifest_entry_absence_source_refs"]:
                assert (ROOT / ref.split("#")[0]).exists(), f"absence source_ref 不存在：{ref}"

    def test_the_record_registers_that_switch_condition(self, record: dict) -> None:
        for entry_record in record["entries"]:
            model = entry_record["authority_model"]
            assert model["value"] == "projection_contract"
            assert model["db_published"] is False
            assert model["currently_used_by_writer"] == "opaque_single_onlyoffice"
            assert model["switch_condition"].strip()
            assert model["blocked_by"], "authority model 的阻断项不得为空"


# ════════════════════════════════════════════════════════════════════════════
# 判据十：slice 侧三条前提不受本轮影响（反向锁）
# ════════════════════════════════════════════════════════════════════════════
class TestSliceInvariantsAreUntouched:
    """本记录**不是** slice ⇒ slice 数 12 / Property 70 配对 66 / `_UNJUDGED_SLICES` 空 三条不变。"""

    def test_the_publication_record_is_outside_the_ap1_scan_glob(
        self, record: dict, paradigm: dict
    ) -> None:
        """**Validates: Requirements 12.3**"""
        ap1 = next(
            item
            for item in paradigm["adjudication_criteria"]["anti_patterns"]
            if item["id"] == "AP-1"
        )
        scan_glob = ap1["scan_glob"]
        slices = sorted(DATA.glob(Path(scan_glob).name))
        names = {p.name for p in slices}
        assert PUBLICATION.name not in names, (
            "发布记录落进了 AP-1 的 scan_glob ⇒ slice 数与 Property 70 配对分母都会被推高"
        )
        declared = record["why_not_a_cycle_manifest_slice"]["denominators"]
        assert declared["ap1_scan_glob"] == scan_glob
        assert declared["ap1_detector"] == ap1["detector"]
        assert declared["publication_record_is_outside_the_scan_glob"] is True

    def test_slice_count_and_pairwise_count_are_recomputed_not_hardcoded(
        self, record: dict
    ) -> None:
        """**Validates: Requirements 12.3**

        🔴 配对数**现算** `len(sets)*(len(sets)-1)//2`，禁写死。
        """
        slices = sorted(DATA.glob("*_cycle_manifest_slice.json"))
        count = len(slices)
        pairwise = count * (count - 1) // 2
        declared = record["why_not_a_cycle_manifest_slice"]["denominators"]
        assert declared["slice_count_before_and_after_task_60"] == count == 12, (
            f"slice 数现算 {count} ⇒ 本轮声称「前后皆 12」不成立"
        )
        assert declared["property_70_pairwise_count"] == pairwise == 66, (
            f"Property 70 配对数现算 {pairwise}"
        )
        assert "len(sets)" in declared["pairwise_recipe"], "配方必须写明现算公式"

    def test_the_slice_coverage_guard_still_reports_no_unjudged_slices(self) -> None:
        """**Validates: Requirements 12.3**

        `_UNJUDGED_SLICES` 必须保持 `{}`，且它的分母（现扫 slice 数）与上一条一致。
        """
        module = _coverage_module()
        assert module._UNJUDGED_SLICES == {}, (
            f"覆盖面守卫的未裁决登记非空：{module._UNJUDGED_SLICES} ⇒ 本轮不该动它"
        )
        assert len(module._SLICE_PARAMS) == 12, (
            f"覆盖面守卫的 slice 分母现算 {len(module._SLICE_PARAMS)}（预期 12）"
        )

    def test_the_f_cycle_slice_is_consumed_not_overturned(self, record: dict) -> None:
        """**Validates: Requirements 12.3**

        F 循环 slice 的既有结论（excluded_from_slice[0] 委派 Tasks 60/61、stocktake entry
        的 capability 仍 null）必须与本记录声明一致 —— 证明本轮**消费**而非改写它。
        """
        delegation = record["why_not_a_cycle_manifest_slice"]["f_slice_delegation"]
        slice_doc = _load(F_SLICE)
        excluded = slice_doc["slice_scope"]["excluded_from_slice"] if "excluded_from_slice" in slice_doc.get(
            "slice_scope", {}
        ) else slice_doc.get("excluded_from_slice", [])
        assert excluded, "F 循环 slice 的 excluded_from_slice 现算为空 ⇒ 委派对象消失"
        item = excluded[delegation["excluded_from_slice_index"]]
        blob = json.dumps(item, ensure_ascii=False)
        assert "60" in blob and "61" in blob, (
            f"excluded_from_slice[{delegation['excluded_from_slice_index']}] 不再委派 Tasks 60/61：{blob[:200]}"
        )
        stocktake = next(
            e
            for e in slice_doc["independent_entries"]
            if e["entry_id"] == delegation["stocktake_entry_id"]
        )
        assert stocktake["capability"] == delegation["stocktake_entry_capability"] is None
        for writer in delegation["partially_wired_word_lane_writers"]:
            assert (ROOT / writer).is_file(), f"登记的 writer 不存在：{writer}"
        assert delegation["consumed_not_overturned"].strip()

    def test_both_docx_files_are_registered_in_the_f_slice_template_ledger(
        self, record: dict
    ) -> None:
        """两份 docx 在 F 循环 slice 的权威册里已登记为 `belongs_to_entry=null` + 排除理由。"""
        files = _load(F_SLICE)["authoritative_templates"]["files"]
        by_name = {item["name"]: item for item in files}
        for entry in GEN.ENTRIES:
            key = next(
                (name for name in by_name if name.endswith(entry.template_path.name)), None
            )
            assert key, f"F 循环 slice 的权威册里找不到 {entry.template_path.name}"
            assert by_name[key].get("belongs_to_entry") is None, (
                f"{key} 在 F slice 里已归属某 entry ⇒ 与本 lane 的登记双归属冲突"
            )
        assert record["authoritative_templates"]["read_only"].strip()


# ════════════════════════════════════════════════════════════════════════════
# 判据十一：Property 70 —— 两个 entry 逐项隔离
# ════════════════════════════════════════════════════════════════════════════
class TestCrossEntryIsolation:
    """每个 F2 entry 保存自身 digest 与 evidence，不交叉复用。"""

    def test_every_per_entry_identity_is_distinct(self, record: dict) -> None:
        """**Validates: Requirements 12.10**"""
        entries = record["entries"]
        assert len(entries) == 2
        for field in (
            "lane_entry_key",
            "wp_code",
            "sheet_code",
            "template_ref",
            "template_sha256",
            "template_normalized_structure_hash",
            "wired_writer",
            "wired_writer_reason_tag",
        ):
            values = [e[field] for e in entries]
            assert len(set(values)) == 2, f"字段 `{field}` 在两个 entry 上相同：{values}"
        for path in (
            ("contract", "canonical_sha256"),
            ("template_definition", "definition_sha256"),
            ("instrumentation_definition", "definition_sha256"),
            ("authority_model", "definition_sha256"),
        ):
            values = [e[path[0]][path[1]] for e in entries]
            assert len(set(values)) == 2, f"digest `{'.'.join(path)}` 在两个 entry 上相同"

    def test_tags_of_one_entry_cannot_be_resolved_by_the_other_contract(
        self, contracts_on_disk: dict[str, dict]
    ) -> None:
        """**Validates: Requirements 12.10**

        `WordEngineBinding.resolve_tag` 对 contract 段不符必须 fail closed ——
        这是「一份文档的 tag 不可能被另一份契约解析」的**真跑**证明。
        """
        plan_payload = contracts_on_disk[GEN.PLAN_ID]
        summary_payload = contracts_on_disk[GEN.SUMMARY_ID]
        plan_binding = _binding(plan_payload, entry_id=GEN.PLAN_ID)
        foreign_tag = WE.parse_sdt_tag(summary_payload["fields"][0]["sdt_tag"])
        assert foreign_tag is not None
        with pytest.raises(WE.WordTagUnregisteredError):
            plan_binding.resolve_tag(foreign_tag)
        own_tag = WE.parse_sdt_tag(plan_payload["fields"][0]["sdt_tag"])
        assert own_tag is not None
        assert plan_binding.resolve_tag(own_tag).stable_field_key == plan_payload["fields"][0][
            "stable_field_key"
        ]

    def test_the_html_side_payload_keys_are_not_shared(self, record: dict) -> None:
        item_ids = [e["html_counterpart"]["item_id"] for e in record["entries"]]
        assert _same_sequence(item_ids, ["F2-22-fields", "F2-23-fields"])
        for entry_record in record["entries"]:
            counterpart = entry_record["html_counterpart"]
            assert counterpart["store"] == "checklist_responses"
            for key in ("writer", "reader", "field_key_owner"):
                module = counterpart[key].split("::")[0]
                assert (ROOT / module).is_file(), f"html_counterpart.{key} 指向不存在的模块"
            assert entry_record["html_counterpart_verdict"] == "exists"
            for ref in entry_record["html_counterpart_source_refs"]:
                assert (ROOT / ref).exists(), f"html_counterpart_source_ref 不存在：{ref}"

    def test_the_isolation_assertions_are_declared_and_non_empty(self, record: dict) -> None:
        node = record["cross_entry_isolation"]
        assert node["rule"].strip()
        assert len(node["assertions"]) >= 5
        assert _same_sequence(
            sorted(node["staged_contract_files"]),
            sorted(f"{e.contract_id}.json" for e in GEN.ENTRIES),
        )


# ════════════════════════════════════════════════════════════════════════════
# 判据十二：Task 59 兼容性登记（差异必须显式，不能静默打红邻居）
# ════════════════════════════════════════════════════════════════════════════
class TestTask59Compatibility:
    def test_the_overlapping_keys_agree_on_the_must_match_axes(self, record: dict) -> None:
        """**Validates: Requirements 7.4**

        Task 59 的 engine 守卫用 in-test fixture；真契约与它在 `sdt_tag` 等轴上必须一致，
        否则本轮发布会把 Task 59 静默打红。
        """
        node = record["task59_compatibility"]
        assert node["shared_contract_id"] == GEN.PLAN_ID
        payload = _load(STAGED_DIR / f"{GEN.PLAN_ID}.json")
        by_key = {f["stable_field_key"]: f for f in payload["fields"]}
        for key in node["overlapping_stable_keys"]:
            assert key in by_key, f"Task 59 fixture 覆盖的 {key} 在真契约里不存在"
            assert by_key[key]["sdt_tag"] == WI.format_sdt_tag(
                kind="block" if key.endswith("warehouses") else "field",
                contract_id=GEN.PLAN_ID,
                stable_key=key,
            )
        assert node["registered_differences"], "差异必须显式登记（禁静默）"
        assert node["difference_is_not_a_conflict_because"].strip()

    def test_task59_guard_file_still_exists_and_uses_its_own_fixture(self) -> None:
        """反向：Task 59 守卫若改成读磁盘契约，本轮的「两者共存」结论就要重写。"""
        guard = _THIS.with_name("test_task59_word_sdt_engine.py")
        assert guard.is_file()
        src = _strip_py_comments(guard.read_text(encoding="utf-8"))
        assert "def plan_contract_payload" in src, (
            "Task 59 不再自建 payload fixture ⇒ task59_compatibility 的前提变了"
        )
        assert STAGED_DIR.name not in src, (
            "Task 59 已开始读 staged 契约目录 ⇒ 两份真源共存的结论要重判"
        )


# ════════════════════════════════════════════════════════════════════════════
# 判据十三：既存欠账 —— xfail(strict=True) + 解除条件（禁 pytest.skip）
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.xfail(
    strict=True,
    reason=(
        "BP-10：本 lane 在 source-backed manifest 里没有 entry ⇒ 契约不能装进生产清册"
        "（`DELIVERED_PER_ENTRY_CONTRACTS` 的每行 entry_id 必须命中 manifest）。"
        "**解除条件**：manifest 扫描器能发现本 lane（需要 descriptor/adapter 形态的挂载点，"
        "见 BP-12）后，把两份契约装入 `workpaper_sync_contracts/` 并补登记行 ⇒ 本条转 XPASS，"
        "届时删除本 xfail 标记。"
    ),
)
def test_bp10_the_lane_contracts_are_installed_into_the_production_inventory() -> None:
    available = C.available_contract_ids()
    for entry in GEN.ENTRIES:
        assert entry.contract_id in available


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BP-11：approved definition bundle 需要 DB 侧 definition 行（`definition:<uuid>`），"
        "离线产不出 ⇒ 三个 typed slot 现在必然被 `validate_bundle_slot` 拒。"
        "**解除条件**：Task 15/36 发布 definition 行后 slot_ref 变成 `definition:<uuid>` ⇒ "
        "本条转 XPASS。绝不为凑 non-null 造假 uuid。"
    ),
)
def test_bp11_the_planned_bundle_slots_pass_the_production_gate() -> None:
    record = _load(PUBLICATION)
    for entry_record in record["entries"]:
        for name, slot in sorted(entry_record["bundle_slot_plan"]["slots"].items()):
            M.validate_bundle_slot(
                M.BundleSlotSpec(
                    slot=M.BundleSlot(name),
                    slot_type=slot["slot_type"],
                    slot_ref=slot["slot_ref"],
                    slot_digest=slot["slot_digest"],
                )
            )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BP-12 / BP-15：本 lane 的 OO 挂载点自行请求 config、零 descriptor prop ⇒ "
        "AC 11.5 / Property 47 要求的「只消费 descriptor 并暴露可 await 的 forceSave()」"
        "没有实现。**解除条件**：Task 61 把 `<GtOnlyOfficeSheet>` 改成消费 descriptor（含 "
        "approved bundle）并暴露 durable API ⇒ 本条转 XPASS。"
    ),
)
def test_bp12_the_lane_mount_consumes_a_descriptor() -> None:
    host = LANE_HOST_VUE.read_text(encoding="utf-8")
    mount_block = host[host.index("<GtOnlyOfficeSheet") : host.index("<GtOnlyOfficeSheet") + 400]
    assert re.search(r":(descriptor|sync-descriptor|entry-descriptor)=", mount_block), (
        "挂载点没有 descriptor prop"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BP-13：AC 12.10 / 14.1 要求的服务端 evidence summary 与逐 scenario 产物级测试在本 "
        "lane 上一条都没有。**解除条件**：Task 61 跑完真实 OO 9.4 全场景并落 "
        "`sync_test_run_id` / `required_scenario_set_digest` ⇒ 本条转 XPASS。"
    ),
)
def test_bp13_each_entry_has_a_server_side_evidence_summary() -> None:
    record = _load(PUBLICATION)
    for entry_record in record["entries"]:
        evidence = entry_record["evidence"]
        assert evidence["sync_test_run_id"] is not None
        assert evidence["required_scenario_set_digest"] is not None
        assert evidence["verification_state"] != "UNVERIFIABLE"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BP-14：`extract_fields_from_docx` 仍用中文章节标题正则切分（Requirement 7.1 明禁"
        "中文 label 作定位/身份）。**解除条件**：Task 61 用 tagged SDT 取代该正则 ⇒ 本条转 "
        "XPASS。本任务不改生产代码。"
    ),
)
def test_bp14_the_lane_extract_no_longer_depends_on_chinese_headings() -> None:
    src = _strip_py_comments(PLAN_SERVICE_PY.read_text(encoding="utf-8"))
    assert "监盘目的" not in src, "service 里仍有中文章节标题定位"
