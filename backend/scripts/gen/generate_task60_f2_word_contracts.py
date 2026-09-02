# -*- coding: utf-8 -*-
r"""Task 60 生成器 —— F2-22 / F2-23 统一 Word adapter 的 per-entry 契约与发布记录。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 60
Requirements: 7.3 · 7.4 · 7.9 · 11.5 · 12.3 · 12.7 · 12.10 · 14.1
Properties: 31 · 32 · 47 · 69

产物（三个，全部可由本脚本从**权威 docx 字节**重算）::

    backend/data/workpaper_sync_word_contracts/f2.stocktake.plan.json
    backend/data/workpaper_sync_word_contracts/f2.stocktake.summary.json
    backend/data/workpaper_sync_f2_word_lane_publication.json

用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）::

    .\.venv\Scripts\python.exe backend/scripts/gen/generate_task60_f2_word_contracts.py --check
    .\.venv\Scripts\python.exe backend/scripts/gen/generate_task60_f2_word_contracts.py --write

`--check` 只比对不落盘（幂等判据）；`--write` 覆盖产物。

═══ 三边锁（每个字段都过三条边）═══

1. **声明** —— 本脚本的 `_PLAN_FIELDS` / `_SUMMARY_FIELDS` 表；
2. **磁盘真读** —— `zipfile` 直读 `backend/wp_templates/F/*.docx` 的 `word/document.xml`，
   逐 token 现算出现次数 / 段落序号 / **未 strip 的**段落原文 / 所在段 run 数 /
   是否落在 `w:tbl` 内 / 是否落在既有 `w:sdt` 内；
3. **impl 常量现读** —— 载体与锚点白名单不在本脚本里抄，而是委派
   `word_instrumentation.WordSdtCarrierGate.load()`（真源 =
   `backend/data/onlyoffice_word_sdt_carrier_contract.json` 的 `downstream_gate`），
   digest 链委派 `build_word_template_payload` / `build_word_instrumentation_payload`
   与 `definitions.canonical_digest`，契约强校验委派 `contracts.parse_contract`。

═══ 为什么契约不落在 `backend/data/workpaper_sync_contracts/` ═══

那个目录是**生产清册**：`contracts.available_contract_ids()` 扫它，且
`test_task13_contract_registry.py::test_contract_directory_matches_the_delivery_ledger`
要求「目录 ↔ `registry.DELIVERED_PER_ENTRY_CONTRACTS` 双向等值」且登记表每行的
`entry_id` **必须命中 source-backed manifest**。而 F2 Word 通道在
`backend/data/workpaper_sync_entry_manifest.json` 里**没有 entry**（实测 7 条 docx
entry 全是 A10B/A12B/A16B/A17B + GtWpRenderer + WorkpaperWordEditor +
WpPopupDocxEditor，无一条 wp_code 前缀为 F；F2 的 to/from-OO 是
`useF2StocktakeDualMode.ts` 打 REST 端点，没有任何 OO 组件挂载点供 manifest 扫描器发现）。

⇒ 把契约放进生产清册会二选一地失败：要么登记表缺行（目录 ↔ 登记表不等值），要么伪造
一个不存在的 manifest entry_id。两者都是假绿。故本任务把契约落在
`workpaper_sync_word_contracts/`（**staged**，不进生产清册），并把「装进生产目录」
这一步的前置条件如实写进发布记录的 `installation` 与 BP-10。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_THIS = Path(__file__).resolve()
_REPO = _THIS.parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

from app.services.word_sdt_fingerprint import structure_fingerprint  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import word_instrumentation as WI  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402

# ════════════════════════════════════════════════════════════════════════════
# 路径常量
# ════════════════════════════════════════════════════════════════════════════
DATA = _BACKEND / "data"
TEMPLATE_ROOT = _BACKEND / "wp_templates"
F_DIR = TEMPLATE_ROOT / "F"
STAGED_CONTRACT_DIR = DATA / "workpaper_sync_word_contracts"
PUBLICATION_PATH = DATA / "workpaper_sync_f2_word_lane_publication.json"
PRODUCTION_CONTRACT_DIR = DATA / "workpaper_sync_contracts"
CARRIER_CONTRACT = DATA / "onlyoffice_word_sdt_carrier_contract.json"
ENTRY_MANIFEST = DATA / "workpaper_sync_entry_manifest.json"
F_SLICE = DATA / "workpaper_sync_f_cycle_manifest_slice.json"
PARADIGM = DATA / "workpaper_sync_migration_paradigm.json"

PLAN_DOCX = F_DIR / "F2-22 存货监盘计划.docx"
SUMMARY_DOCX = F_DIR / "F2-23 存货监盘小结.docx"

_FRONTEND = _REPO / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = _FRONTEND / "components" / "workpaper"
#: 本 lane 唯一的宿主（`useF2StocktakeDualMode` 的唯一 `.vue` 消费方，现算校验见守卫）。
LANE_HOST_VUE = WP_COMPONENTS / "GtF2StocktakeBundle.vue"
#: 宿主挂载的 OO 组件 —— 它**自行请求** config，不消费 descriptor（Property 47 的反面）。
OO_SHEET_VUE = WP_COMPONENTS / "GtOnlyOfficeSheet.vue"
LANE_DUAL_MODE_TS = WP_COMPONENTS / "composables" / "useF2StocktakeDualMode.ts"
OO_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_onlyoffice_router.py"

PLAN_ID = "f2.stocktake.plan"
SUMMARY_ID = "f2.stocktake.summary"

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TOKEN_RE = re.compile(r"\$\{[A-Za-z][A-Za-z0-9_]*\}")


# ════════════════════════════════════════════════════════════════════════════
# 字段声明表（三边锁的第一边）
# ════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class FieldDecl:
    """一个受管 Word 字段的声明。

    `carrier` 只能取 Task 6 allowlist 内的值（脚本运行时经 `WordSdtCarrierGate`
    校验，不在此处抄清单）；`pointer_key` 是 HTML 侧 JSON 的键名，用于把 docx 结构
    化岛与 `checklist_responses` 的 `{sheet}-fields` 载荷对齐。
    """

    token: str
    stable_field_key: str
    pointer_key: str
    value_type: str
    alias: str
    carrier: str = "field_sdt_inline"
    mode: str = "editable"


#: F2-22 存货监盘计划。`plan/warehouses` 用 block 载体、`plan/entity_name` 两实例 ——
#: 两者都不是选择而是**对齐 Task 6 探针实证**（`field_sdt_block.evidence.block_tags`
#: 与 `field_sdt_inline.evidence.duplicate_stable_key_instances_retained`）。
_PLAN_FIELDS: tuple[FieldDecl, ...] = (
    FieldDecl("${entityName}", "plan/entity_name", "entityName", "text", "被审计单位"),
    FieldDecl("${auditYear}", "plan/audit_year", "auditYear", "integer", "审计年度"),
    FieldDecl("${bsDate}", "plan/bs_date", "bsDate", "date", "资产负债表日"),
    FieldDecl("${purpose}", "plan/purpose", "purpose", "text", "监盘目的"),
    FieldDecl("${scope}", "plan/scope", "scope", "text", "监盘范围"),
    FieldDecl(
        "${warehouses}", "plan/warehouses", "warehouses", "text", "监盘地点",
        carrier="field_sdt_block",
    ),
    FieldDecl("${countDate}", "plan/count_date", "countDate", "text", "监盘时间"),
    FieldDecl("${auditors}", "plan/auditors", "auditors", "text", "项目组监盘人员"),
    FieldDecl("${clientStaff}", "plan/client_staff", "clientStaff", "text", "被审计单位配合人员"),
    FieldDecl("${assignment}", "plan/assignment", "assignment", "text", "分工"),
    FieldDecl("${prep}", "plan/prep", "prep", "text", "监盘前准备工作"),
    FieldDecl(
        "${inventoryComposition}", "plan/inventory_composition", "inventoryComposition",
        "text", "存货构成",
    ),
    FieldDecl("${countMethod}", "plan/count_method", "countMethod", "text", "监盘方式"),
    FieldDecl("${requirements}", "plan/requirements", "requirements", "text", "监盘要求"),
    FieldDecl("${specialNotes}", "plan/special_notes", "specialNotes", "text", "特别关注事项"),
    FieldDecl("${teamName}", "plan/team_name", "teamName", "text", "审计小组"),
    FieldDecl("${planDate}", "plan/plan_date", "planDate", "date", "计划日期"),
)

#: F2-23 存货监盘小结。`summary/conclusion` 用 block 载体 —— Task 6 探针实测的
#: `gt:block:f2.stocktake.summary:summary/conclusion` 就是它。
_SUMMARY_FIELDS: tuple[FieldDecl, ...] = (
    FieldDecl("${entityName}", "summary/entity_name", "entityName", "text", "被审计单位"),
    FieldDecl("${auditYear}", "summary/audit_year", "auditYear", "integer", "审计年度"),
    FieldDecl("${bsDate}", "summary/bs_date", "bsDate", "date", "资产负债表日"),
    FieldDecl("${purpose}", "summary/purpose", "purpose", "text", "监盘目的"),
    FieldDecl("${scope}", "summary/scope", "scope", "text", "监盘范围"),
    FieldDecl("${warehouses}", "summary/warehouses", "warehouses", "text", "监盘地点"),
    FieldDecl("${countDate}", "summary/count_date", "countDate", "text", "监盘时间"),
    FieldDecl("${clientStaff}", "summary/client_staff", "clientStaff", "text", "盘点人员"),
    FieldDecl("${auditors}", "summary/auditors", "auditors", "text", "项目组监盘人员"),
    FieldDecl("${assignment}", "summary/assignment", "assignment", "text", "分工"),
    FieldDecl("${countMethod}", "summary/count_method", "countMethod", "text", "公司存货盘点方法"),
    FieldDecl("${summaryBlock}", "summary/summary_block", "summaryBlock", "text", "监盘情况汇总"),
    FieldDecl(
        "${resultByLocation}", "summary/result_by_location", "resultByLocation",
        "text", "具体监盘情况",
    ),
    FieldDecl(
        "${conclusionBlock}", "summary/conclusion", "conclusionBlock", "text", "监盘结论",
        carrier="field_sdt_block",
    ),
    FieldDecl("${teamName}", "summary/team_name", "teamName", "text", "审计小组"),
    FieldDecl("${summaryDate}", "summary/summary_date", "summaryDate", "date", "小结日期"),
)


@dataclass(frozen=True)
class EntryDecl:
    """一个 Word lane entry 的声明。"""

    lane_entry_key: str
    contract_id: str
    wp_code: str
    sheet_code: str
    template_path: Path
    fields: tuple[FieldDecl, ...]
    fields_item_id: str
    writer_module: str
    reason_tag: str
    to_oo_endpoint: str
    from_oo_endpoint: str
    service_module: str
    router_module: str


ENTRIES: tuple[EntryDecl, ...] = (
    EntryDecl(
        lane_entry_key="word-lane/f2-22-stocktake-plan",
        contract_id=PLAN_ID,
        wp_code="F2-22",
        sheet_code="F2-22",
        template_path=PLAN_DOCX,
        fields=_PLAN_FIELDS,
        fields_item_id="F2-22-fields",
        writer_module="backend/app/routers/wp_render_strategies/_f2_stocktake_plan_sync.py",
        reason_tag="f2_st_plan_sync_from_oo",
        to_oo_endpoint="POST /api/workpapers/{wp_id}/f2-st/plan-sync-to-oo",
        from_oo_endpoint="POST /api/workpapers/{wp_id}/f2-st/plan-sync-from-oo",
        service_module="backend/app/services/f2_stocktake_plan_sync.py",
        router_module="backend/app/routers/wp_render_strategies/_f2_stocktake_plan_sync.py",
    ),
    EntryDecl(
        lane_entry_key="word-lane/f2-23-stocktake-summary",
        contract_id=SUMMARY_ID,
        wp_code="F2-23",
        sheet_code="F2-23",
        template_path=SUMMARY_DOCX,
        fields=_SUMMARY_FIELDS,
        fields_item_id="F2-23-fields",
        writer_module="backend/app/routers/wp_render_strategies/_f2_stocktake_summary_sync.py",
        reason_tag="f2_st_summary_sync_from_oo",
        to_oo_endpoint="POST /api/workpapers/{wp_id}/f2-st/summary-sync-to-oo",
        from_oo_endpoint="POST /api/workpapers/{wp_id}/f2-st/summary-sync-from-oo",
        service_module="backend/app/services/f2_stocktake_summary_sync.py",
        router_module="backend/app/routers/wp_render_strategies/_f2_stocktake_summary_sync.py",
    ),
)


# ════════════════════════════════════════════════════════════════════════════
# 第二边：磁盘真读
# ════════════════════════════════════════════════════════════════════════════
def document_xml(data: bytes) -> str:
    with zipfile.ZipFile(__import__("io").BytesIO(data)) as zf:
        return zf.read("word/document.xml").decode("utf-8")


def paragraph_survey(data: bytes) -> list[dict[str, Any]]:
    """逐段现算：原文（**不 strip**）、run 数、是否在表格内、是否在既有 SDT 内。

    段落序号只作**一次性迁移线索**登记（Task 6 里 `paragraph_index` 的
    `probe_verdict=failed`，不得作回写锚点）；运行态定位只用 `w:tag`。
    """
    import xml.etree.ElementTree as ET

    xml = document_xml(data)
    root = ET.fromstring(xml)
    body = root.find(f"{WORD_NS}body")
    if body is None:  # pragma: no cover - 非法 docx
        raise SystemExit("word/document.xml 缺 w:body")

    in_table: set[int] = set()
    for tbl in body.iter(f"{WORD_NS}tbl"):
        for para in tbl.iter(f"{WORD_NS}p"):
            in_table.add(id(para))
    in_sdt: set[int] = set()
    for sdt in body.iter(f"{WORD_NS}sdt"):
        for para in sdt.iter(f"{WORD_NS}p"):
            in_sdt.add(id(para))

    out: list[dict[str, Any]] = []
    for ordinal, para in enumerate(body.iter(f"{WORD_NS}p")):
        texts = [node.text or "" for node in para.iter(f"{WORD_NS}t")]
        out.append(
            {
                "ordinal": ordinal,
                "text": "".join(texts),
                "run_count": len(list(para.iter(f"{WORD_NS}r"))),
                "w_t_count": len(texts),
                "in_table": id(para) in in_table,
                "in_existing_sdt": id(para) in in_sdt,
            }
        )
    return out


def token_facts(data: bytes) -> dict[str, dict[str, Any]]:
    """每个 `${token}` 的可复算事实。"""
    xml = document_xml(data)
    paragraphs = paragraph_survey(data)
    facts: dict[str, dict[str, Any]] = {}
    for token in sorted(set(TOKEN_RE.findall(xml))):
        hits = [p for p in paragraphs if token in p["text"]]
        facts[token] = {
            "token": token,
            "occurrences_in_document_xml": xml.count(token),
            "paragraph_ordinals": [p["ordinal"] for p in hits],
            "paragraph_texts_verbatim": [p["text"] for p in hits],
            "run_counts_at_injection": [p["run_count"] for p in hits],
            "negative_claims": {
                "inside_w_tbl": any(p["in_table"] for p in hits),
                "inside_existing_sdt": any(p["in_existing_sdt"] for p in hits),
                "document_has_w_tbl": "<w:tbl>" in xml,
                "document_has_w_tr": "<w:tr>" in xml,
                "document_has_existing_sdt": "<w:sdt>" in xml,
            },
        }
    return facts


# ════════════════════════════════════════════════════════════════════════════
# 第三边：impl 常量现读 + digest 链
# ════════════════════════════════════════════════════════════════════════════
def build_instrumentation_spec(
    entry: EntryDecl, facts: dict[str, dict[str, Any]]
) -> WI.WordInstrumentationSpec:
    return WI.WordInstrumentationSpec(
        entry_id=entry.contract_id,
        contract_id=entry.contract_id,
        template_id=entry.sheet_code,
        template_relative_path=f"F/{entry.template_path.name}",
        fields=tuple(
            WI.WordFieldInjection(
                token=decl.token,
                stable_field_key=decl.stable_field_key,
                carrier=decl.carrier,
                alias=decl.alias,
                expected_token_occurrences=facts[decl.token]["occurrences_in_document_xml"],
            )
            for decl in entry.fields
        ),
    )


def build_contract_payload(
    entry: EntryDecl,
    *,
    facts: dict[str, dict[str, Any]],
    template_sha256: str,
    structure_hash: str,
    template_definition_sha256: str,
    instrumentation_definition_sha256: str,
    spec: WI.WordInstrumentationSpec,
) -> dict[str, Any]:
    """docx 契约 payload：顶层 `fields`（禁 `sheets`/`cell`），逐字段带 `sdt_tag`。"""
    carriers = list(spec.carriers())
    fields: list[dict[str, Any]] = []
    for decl in entry.fields:
        occ = facts[decl.token]["occurrences_in_document_xml"]
        ordinals = facts[decl.token]["paragraph_ordinals"]
        kind = "block" if decl.carrier == "field_sdt_block" else "field"
        fields.append(
            {
                "stable_field_key": decl.stable_field_key,
                "json_pointer": f"/{decl.pointer_key}",
                "mode": decl.mode,
                "value_type": decl.value_type,
                # `p{NN}:{token}` 与 Task 59 的 fixture 同形；`p{NN}` 是**一次性迁移
                # 线索**，运行态定位只认 `sdt_tag`（见发布记录 source_ref_semantics）。
                "source_ref": (
                    f"{entry.sheet_code}!p{ordinals[0]:02d}:{decl.token}"
                    if occ == 1
                    else f"{entry.sheet_code}!p"
                    + "+".join(f"{o:02d}" for o in ordinals)
                    + f":{decl.token}"
                ),
                "sdt_tag": WI.format_sdt_tag(
                    kind=kind, contract_id=entry.contract_id,
                    stable_key=decl.stable_field_key,
                ),
                "instances": "many" if occ > 1 else "one",
            }
        )
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": entry.contract_id,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "docx",
        "template": {
            "relative_path": f"F/{entry.template_path.name}",
            "template_sha256": template_sha256,
            "normalized_structure_hash": structure_hash,
        },
        "template_definition_sha256": template_definition_sha256,
        "instrumentation_definition_sha256": instrumentation_definition_sha256,
        "identity_carriers": carriers,
        "fields": fields,
    }


def build_entry_payloads(entry: EntryDecl, gate: WI.WordSdtCarrierGate) -> dict[str, Any]:
    """一个 entry 的完整 digest 链 + 契约 payload + 逐字段证据。"""
    data = entry.template_path.read_bytes()
    template_sha256 = hashlib.sha256(data).hexdigest()
    structure_hash = WI.word_structure_hash(data)
    facts = token_facts(data)
    declared_tokens = [decl.token for decl in entry.fields]
    missing = sorted(set(facts) - set(declared_tokens))
    invented = sorted(set(declared_tokens) - set(facts))
    if missing or invented:
        raise SystemExit(
            f"{entry.sheet_code}: token 集合与磁盘不符 —— 漏声明 {missing}；"
            f"磁盘上不存在 {invented}"
        )

    spec = build_instrumentation_spec(entry, facts)
    template_payload = WI.build_word_template_payload(
        spec=spec, template_sha256=template_sha256, structure_hash=structure_hash
    )
    template_definition_sha256 = canonical_digest(template_payload)
    instrumentation_payload = WI.build_word_instrumentation_payload(
        spec=spec,
        template_definition_sha256=template_definition_sha256,
        template_sha256=template_sha256,
        gate=gate,
    )
    instrumentation_definition_sha256 = canonical_digest(instrumentation_payload)
    contract_payload = build_contract_payload(
        entry,
        facts=facts,
        template_sha256=template_sha256,
        structure_hash=structure_hash,
        template_definition_sha256=template_definition_sha256,
        instrumentation_definition_sha256=instrumentation_definition_sha256,
        spec=spec,
    )
    # 生产强校验器必须接受它（reviewed + 载体过门 + sdt_tag 合法 + 无类型串用）。
    contract = C.parse_contract(contract_payload, adapter_id=entry.contract_id)
    authority_payload = {
        "schema_version": "authority-model-definition:v1",
        "entry_lane_key": entry.lane_entry_key,
        "authority_model": "projection_contract",
        "document_type": "docx",
        "contract_id": entry.contract_id,
        "why": (
            "逐字段 per-entry contract 已发布且载体是 tagged SDT ⇒ 结构化岛按契约投影；"
            "authority model 只能是 projection_contract（registry."
            "assert_authority_model_contract_pairing 对 custom/opaque 明禁携带 SyncContract）。"
            "SDT 外自由正文的保留由 AC 7.3 / 7.9 与 verify_word_only_regions 承担，"
            "不靠把 authority model 降级成 opaque。"
        ),
        "supersedes_premise": (
            "两个 writer 现用 AuthorityModel.opaque_single_onlyoffice，其 docstring 的理由是"
            "「manifest 里 F2 entry 的 capability=single_onlyoffice」；该 capability 实为 "
            "workpaper_sync_entry_overlay.json 的组件级默认值（F 循环 slice 的 BP-6），"
            "不是逐 entry 裁决 ⇒ 前提失效（F 循环 slice 的 BP-9 点名要求本任务重新论证）。"
        ),
    }
    authority_definition_sha256 = canonical_digest(authority_payload)

    field_evidence = []
    for decl in entry.fields:
        fact = facts[decl.token]
        field_evidence.append(
            {
                "stable_field_key": decl.stable_field_key,
                "token": decl.token,
                "alias_display_only": decl.alias,
                "carrier": decl.carrier,
                "sdt_tag": WI.format_sdt_tag(
                    kind="block" if decl.carrier == "field_sdt_block" else "field",
                    contract_id=entry.contract_id,
                    stable_key=decl.stable_field_key,
                ),
                "value_type": decl.value_type,
                "mode": decl.mode,
                "json_pointer": f"/{decl.pointer_key}",
                "html_field_key": decl.pointer_key,
                "occurrences_in_document_xml": fact["occurrences_in_document_xml"],
                "paragraph_ordinals": fact["paragraph_ordinals"],
                "paragraph_texts_verbatim": fact["paragraph_texts_verbatim"],
                "run_counts_at_injection": fact["run_counts_at_injection"],
                "negative_claims": fact["negative_claims"],
                "verdict": "source_backed",
                "verdict_recipe": (
                    "zipfile 读 backend/wp_templates/F/{docx}!word/document.xml，"
                    "现算 token 出现次数 / 段落序号 / 段落原文（不 strip）/ run 数，"
                    "与本节声明逐项等值"
                ),
            }
        )

    return {
        "entry": entry,
        "template_sha256": template_sha256,
        "structure_hash": structure_hash,
        "template_payload": template_payload,
        "template_definition_sha256": template_definition_sha256,
        "instrumentation_payload": instrumentation_payload,
        "instrumentation_definition_sha256": instrumentation_definition_sha256,
        "contract_payload": contract_payload,
        "contract_canonical_sha256": contract.canonical_sha256,
        "authority_payload": authority_payload,
        "authority_definition_sha256": authority_definition_sha256,
        "field_evidence": field_evidence,
        "spec": spec,
        "size": entry.template_path.stat().st_size,
    }


# ════════════════════════════════════════════════════════════════════════════
# 发布记录
# ════════════════════════════════════════════════════════════════════════════
def _slice_denominators() -> dict[str, Any]:
    """AP-1 检测器口径的现算分母 —— 证明本任务没有扰动它。"""
    paradigm = json.loads(PARADIGM.read_text(encoding="utf-8"))
    ap1 = next(
        item
        for item in paradigm["adjudication_criteria"]["anti_patterns"]
        if item["id"] == "AP-1"
    )
    scan_glob = ap1["scan_glob"]
    slices = sorted(DATA.glob(Path(scan_glob).name))
    count = len(slices)
    return {
        "ap1_detector": ap1["detector"],
        "ap1_scan_glob": scan_glob,
        "slice_count_before_and_after_task_60": count,
        "property_70_pairwise_count": count * (count - 1) // 2,
        "pairwise_recipe": "len(sets)*(len(sets)-1)//2 —— 现算，禁写死",
        "publication_record_is_outside_the_scan_glob": (
            PUBLICATION_PATH.name not in {p.name for p in slices}
        ),
    }


def mount_tag_block(host_lines: list[str], *, span: int = 20) -> list[str]:
    """`<GtOnlyOfficeSheet …/>` 这一个标签的**自身属性块**（到收尾 `/>` 或 `>` 为止）。

    守卫会 import 本函数复算，两侧共用同一口径（禁各写一份）。
    """
    start = next(
        (i for i, line in enumerate(host_lines) if "<GtOnlyOfficeSheet" in line), None
    )
    if start is None:
        return []
    block: list[str] = []
    for line in host_lines[start : start + span]:
        block.append(line)
        stripped = line.rstrip()
        if stripped.endswith("/>") or (stripped.endswith(">") and len(block) > 1):
            break
    return block


def mount_is_mode_gated(host_lines: list[str]) -> bool:
    return any(
        "v-if" in line and "currentMode" in line and "onlyoffice" in line
        for line in mount_tag_block(host_lines)
    )


def _descriptor_consumption_facts() -> dict[str, Any]:
    """Property 47 的承载者**现算** —— 本 lane 到底有没有 OO 挂载点、它消费不消费 descriptor。

    🔴 修正记录（BP-15）：本记录首版把 BP-12 写成「本 lane 没有 OO 组件挂载点」，实测**错**。
    `GtF2StocktakeBundle.vue` 里有一个 mode 门控的 `<GtOnlyOfficeSheet>`，而 F2-22 / F2-23 正是
    它的两个 `dataTabs`；`useF2StocktakeDualMode` 的 `ooRemountKey` 注释直接写着「强制
    GtOnlyOfficeSheet 重挂载」，`wp_onlyoffice_router` 的 callback 里还有一段
    `_save_wp_code in ("F2-22", "F2-23") … .docx` 的回写分支。⇒ 挂载点存在，Property 47 的分母
    **不是 0**；真正的事实是那个挂载点**自行请求 config**（`/sheets/{sheet}/onlyoffice-config`）、
    不接任何 descriptor prop ⇒ 它**违反** Property 47，而不是「没有承载者」。

    把这里做成现算而不是散文：挂载点数、descriptor prop 数、self-config 站点数都从源码取，
    守卫再独立复算一遍并与本节等值比对。
    """
    host = LANE_HOST_VUE.read_text(encoding="utf-8")
    oo_sheet = OO_SHEET_VUE.read_text(encoding="utf-8")
    router = OO_ROUTER_PY.read_text(encoding="utf-8")
    host_lines = host.split("\n")
    mount_lines = [i for i, line in enumerate(host_lines, 1) if "<GtOnlyOfficeSheet" in line]
    mount_block = mount_tag_block(host_lines)
    return {
        "verdict": "mount_site_exists_but_consumes_no_descriptor",
        "corrected_by": "BP-15",
        "lane_host": LANE_HOST_VUE.relative_to(_REPO).as_posix(),
        "oo_mount_component": "GtOnlyOfficeSheet",
        "oo_mount_site_count": len(mount_lines),
        "oo_mount_site_lines": mount_lines,
        # 🔴 门控必须在**挂载点自身的标签块**里找，不能全文 `any(...)`：宿主第 17 行的
        #    `v-else-if="dualMode.currentMode.value === 'onlyoffice' && …"` 是那条「仅预览」
        #    提示 tag 的门控，全文 any 会让「把挂载点的 v-if 改成 true」仍判 true（实测该
        #    变异一度判 GREEN）。
        "oo_mount_is_mode_gated": mount_is_mode_gated(host_lines),
        "lane_sheet_codes_are_tabs_of_this_host": sorted(
            code for code in (entry.sheet_code for entry in ENTRIES)
            if f"id: '{code}'" in host
        ),
        "descriptor_props_on_the_mount": sorted(
            re.findall(r':(descriptor|sync-descriptor|entry-descriptor)=', host)
        ),
        "oo_component_self_fetches_config": "/onlyoffice-config`" in oo_sheet,
        "oo_component_self_fetch_line": next(
            (
                i
                for i, line in enumerate(oo_sheet.split("\n"), 1)
                if "/onlyoffice-config`" in line
            ),
            None,
        ),
        "router_callback_has_a_lane_specific_docx_branch": bool(
            re.search(r'_save_wp_code in \("F2-22", "F2-23"\)', router)
        ),
        "why_property_47_is_still_not_claimed": (
            "承载者存在但形态相反：Property 47 要求「挂载组件不自行请求 config，只消费含 "
            "approved bundle 的 descriptor，可 await forceSave，且 ready/dirty/saveRequested/"
            "incomingDurable/terminal/recoveryCase/error 各有真实触发路径」。现算结果是"
            "「挂载点自行请求 config + 零 descriptor prop + 无 durable ack」⇒ 它是**反例**"
            "而不是通过项。本任务不接 descriptor/bridge（Task 60 正文把接线排在 bundle/"
            "representation 之后），故只登记事实与 BP-15，不宣称 Property 47 通过。"
        ),
    }


def build_publication_record(built: list[dict[str, Any]]) -> dict[str, Any]:
    gate_doc = json.loads(CARRIER_CONTRACT.read_text(encoding="utf-8"))
    downstream = gate_doc["downstream_gate"]
    manifest = json.loads(ENTRY_MANIFEST.read_text(encoding="utf-8"))
    docx_entries = [e for e in manifest["entries"] if e.get("document_type") == "docx"]
    f_prefixed_docx = [
        e
        for e in docx_entries
        if any(
            str(p).upper().startswith("F")
            for p in ((e.get("wp_match") or {}).get("wp_code_patterns") or [])
        )
    ]
    f_slice = json.loads(F_SLICE.read_text(encoding="utf-8"))
    stocktake = next(
        e
        for e in f_slice["independent_entries"]
        if e["entry_id"] == "xlsx/gt-f2-stocktake-bundle"
    )

    entries: list[dict[str, Any]] = []
    for item in built:
        entry: EntryDecl = item["entry"]
        entries.append(
            {
                "lane_entry_key": entry.lane_entry_key,
                "lane_entry_key_is_not_a_manifest_entry_id": True,
                "wp_code": entry.wp_code,
                "sheet_code": entry.sheet_code,
                "document_type": "docx",
                "template_ref": f"F/{entry.template_path.name}",
                "template_size": item["size"],
                "template_sha256": item["template_sha256"],
                "template_normalized_structure_hash": item["structure_hash"],
                "manifest_entry_state": "absent_from_source_manifest",
                "manifest_entry_absence_recipe": (
                    "backend/data/workpaper_sync_entry_manifest.json 里 document_type=='docx' "
                    "的 entry 现算 %d 条，其中 wp_code_patterns 有 F 前缀的 %d 条 ⇒ 本 lane 无 entry"
                    % (len(docx_entries), len(f_prefixed_docx))
                ),
                "manifest_entry_absence_source_refs": [
                    "backend/data/workpaper_sync_entry_manifest.json",
                    "audit-platform/frontend/src/components/workpaper/composables/"
                    "useF2StocktakeDualMode.ts#L67",
                    "audit-platform/frontend/src/components/workpaper/wpPopupDocxConfigs.ts",
                ],
                "commit_entry_id_expression": (
                    'opaque_entry_id(wp_code=f"{wp_code or wp_id}#{_SHEET_CODE}", wp_id=wp_id)'
                ),
                "commit_entry_id_materialized_form": f"opaque:{{wp_code}}#{entry.sheet_code}",
                "wired_writer": entry.writer_module,
                "wired_writer_reason_tag": entry.reason_tag,
                "second_pipeline_endpoints": [entry.to_oo_endpoint, entry.from_oo_endpoint],
                "html_counterpart_verdict": "exists",
                "html_counterpart": {
                    "store": "checklist_responses",
                    "store_kind": "relational_row_per_item_id",
                    "item_id": entry.fields_item_id,
                    "payload_column": "remark",
                    "shape": "json_object_keyed_by_html_field_key",
                    "writer": f"{entry.writer_module}::_save_fields",
                    "reader": f"{entry.writer_module}::_load_fields",
                    "field_key_owner": f"{entry.service_module}",
                },
                "html_counterpart_source_refs": [
                    entry.writer_module,
                    entry.service_module,
                    "audit-platform/frontend/src/components/workpaper/composables/"
                    "useF2StocktakeDualMode.ts",
                    f"backend/wp_templates/F/{entry.template_path.name}",
                ],
                "authority_model": {
                    "value": "projection_contract",
                    "definition_payload": item["authority_payload"],
                    "definition_sha256": item["authority_definition_sha256"],
                    "db_published": False,
                    "blocked_by": ["BP-10"],
                    "currently_used_by_writer": "opaque_single_onlyoffice",
                    "switch_condition": (
                        "bundle 发布 + adapter 注册后，writer 的 authority_model 必须同批改成 "
                        "projection_contract；本轮不改生产代码（Task 60 正文：Task 61 全场景"
                        "通过后才删除第二流程）"
                    ),
                },
                "template_definition": {
                    "payload": item["template_payload"],
                    "definition_sha256": item["template_definition_sha256"],
                    "recipe": (
                        "canonical_digest(word_instrumentation.build_word_template_payload("
                        "spec, template_sha256, structure_hash))"
                    ),
                    "db_published": False,
                },
                "instrumentation_definition": {
                    "payload": item["instrumentation_payload"],
                    "definition_sha256": item["instrumentation_definition_sha256"],
                    "recipe": (
                        "canonical_digest(word_instrumentation."
                        "build_word_instrumentation_payload(spec, template_definition_sha256, "
                        "template_sha256, gate))"
                    ),
                    "db_published": False,
                },
                "instrumentation_spec": {
                    "entry_id": item["spec"].entry_id,
                    "template_id": item["spec"].template_id,
                    "template_relative_path": item["spec"].template_relative_path,
                    "carriers": list(item["spec"].carriers()),
                    "expected_tags": list(item["spec"].expected_tags()),
                    "expected_instances": dict(item["spec"].expected_instances()),
                    "row_injections": 0,
                    "row_injections_why_zero": (
                        "本文档 w:tbl / w:tr 计数为 0（逐段现算，见 field_evidence 的 "
                        "negative_claims），且 Task 6 的 downstream_gate 把 row_sdt 列为 "
                        "carriers_blocked ⇒ 行载体在本 entry 上既无对象也不许用"
                    ),
                },
                "contract": {
                    "contract_id": entry.contract_id,
                    "staged_path": (
                        f"backend/data/workpaper_sync_word_contracts/{entry.contract_id}.json"
                    ),
                    "review_status": "reviewed",
                    "canonical_sha256": item["contract_canonical_sha256"],
                    "field_count": len(entry.fields),
                    "installation": {
                        "state": "staged_outside_production_inventory",
                        "required_production_path": (
                            f"backend/data/workpaper_sync_contracts/{entry.contract_id}.json"
                        ),
                        "blocked_by": ["BP-10"],
                        "why": (
                            "contracts.available_contract_ids() 扫生产目录，且 "
                            "test_task13_contract_registry.py::"
                            "test_contract_directory_matches_the_delivery_ledger 要求"
                            "「目录 ↔ registry.DELIVERED_PER_ENTRY_CONTRACTS 双向等值」"
                            "且登记表每行 entry_id 必须命中 source-backed manifest。"
                            "本 lane 在 manifest 里没有 entry ⇒ 现在装进生产目录只能二选一地"
                            "假绿（登记表缺行，或伪造 manifest entry_id）。"
                        ),
                        "required_ledger_row": {
                            "contract_id": entry.contract_id,
                            "entry_id": "<manifest 里该 lane 的 entry_id —— 尚不存在>",
                            "document_type": "docx",
                            "reason": (
                                "Task 60 发布的 F2 Word per-entry 契约；装入生产目录的前置是"
                                "该 lane 先在 source-backed manifest 里有 entry"
                            ),
                        },
                    },
                },
                "definition_bundle": None,
                "bundle_slot_plan": {
                    "authority_model": "projection_contract",
                    "authority_model_definition_sha256": item["authority_definition_sha256"],
                    "slots": {
                        "template": {
                            "slot_type": "definition",
                            "slot_ref": None,
                            "slot_digest": item["template_definition_sha256"],
                        },
                        "instrumentation": {
                            "slot_type": "definition",
                            "slot_ref": None,
                            "slot_digest": item["instrumentation_definition_sha256"],
                        },
                        "contract": {
                            "slot_type": "definition",
                            "slot_ref": None,
                            "slot_digest": item["contract_canonical_sha256"],
                        },
                    },
                    "publishable_now": False,
                    "blocked_by": ["BP-10", "BP-11"],
                    "gate_proof": (
                        "models.validate_bundle_slot 对 slot_type=='definition' 要求 slot_ref "
                        "形如 `definition:<uuid>`；DB 未发布 ⇒ 无 uuid ⇒ 本 plan 现在**必然**"
                        "被门拒绝。守卫正向断言这条拒绝，绝不为凑 non-null 造假 uuid。"
                    ),
                },
                "published_representation": None,
                "published_representation_blocked_by": ["BP-10", "BP-11", "BP-12"],
                "adapter_id": None,
                "adapter_blocked_by": ["BP-10", "BP-11", "BP-12"],
                "canonical_resolver": "word_resolution.resolve_word_canonical_path",
                "capability": None,
                "capability_verdict_stage": "word_contract_published_pending_bundle_and_representation",
                "capability_target": "bidirectional",
                "capability_target_blocked_by": ["BP-10", "BP-11", "BP-12", "BP-13"],
                "capability_enum_note": (
                    "AC 1.3 的四个枚举值当下一个都不成立：① html_counterpart_verdict == "
                    "'exists'（两个 writer 自己的 INSERT ... ON CONFLICT 写 "
                    f"{entry.fields_item_id}）⇒ AC 12.8 禁 single_onlyoffice；② OO 侧承载"
                    "真实业务正文（33/32 段权威模板 + 逐字段结构化岛）⇒ AC 12.9 的 "
                    "single_html 不适用；③ 入口在生产源码可达（useF2StocktakeDualMode 打四个"
                    "端点）⇒ 不是 unreachable；④ AC 12.1 六件前置里 bundle / published "
                    "representation / adapter / 逐 scenario evidence 四件未交付 ⇒ SR-6 禁 "
                    "bidirectional。故 capability 记 null + 三字段齐备。"
                ),
                "adjudication": {
                    "honest_capability": None,
                    "reason": (
                        "本轮交付 AC 12.1 六件前置里的两件：approved authority model "
                        "（projection_contract，canonical payload 可复算）与 reviewed per-entry "
                        "contract（逐字段 source_ref 三边锁，17/16 个 token 全覆盖、无自造字段）。"
                        "余下四件（non-null approved bundle / Task 15 finalize 的 published "
                        "representation / 注册 adapter / 逐 scenario evidence）受 BP-10~BP-13 "
                        "阻断，其中 BP-10 是**结构性**的：本 lane 在 source-backed manifest 里"
                        "没有 entry，而生产契约目录与 DELIVERED_PER_ENTRY_CONTRACTS 的双向等值"
                        "判据要求登记行的 entry_id 命中 manifest。"
                    ),
                    "not_single_html_because": (
                        "OO 侧不是空白模板切换入口（AC 12.9 的判据）：权威模板是真实业务正文"
                        "（F2-22 33 段 / F2-23 32 段，逐段原文已登记在 field_evidence），"
                        "且 Task 6 的真实 OO 9.4 探针在这两份文档上取到 field/block 载体"
                        "26/26 与 17/17 全保留。docx 权威册本身就是真实 OO 业务承载。"
                    ),
                    "not_bidirectional_because": (
                        "AC 12.1 六件前置四件未交付（见 reason），且 AC 12.10 / 14.1 要求的"
                        "服务端 evidence summary 与逐 scenario 产物级测试在本 lane 上一条没有 ⇒ "
                        "evidence 保持 UNVERIFIABLE。"
                    ),
                    "criterion_source": (
                        "backend/data/workpaper_sync_migration_paradigm.json#"
                        "adjudication_criteria.verdicts"
                    ),
                },
                "evidence": {
                    "browser_case": None,
                    "contract_test": (
                        "backend/tests/workpaper_sync/test_task60_f2_word_adapter.py"
                    ),
                    "sync_test_run_id": None,
                    "required_scenario_set_digest": None,
                    "verification_state": "UNVERIFIABLE",
                    "unverifiable_reasons": [
                        "no_source_backed_manifest_entry_for_this_lane",
                        "no_non_null_approved_definition_bundle",
                        "no_published_result_representation",
                        "no_registered_sync_adapter",
                        "no_real_onlyoffice_94_scenario_run_for_this_lane",
                    ],
                },
                "field_evidence": item["field_evidence"],
            }
        )

    return {
        "schema_version": "f2-word-lane-publication:v1",
        "task": 60,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "description": (
            "F2-22 / F2-23 统一 Word adapter 迁移的 per-entry 裁决与发布记录。本记录**不是** "
            "manifest slice：它刻意不匹配 AP-1 检测器的 scan_glob，理由见 "
            "why_not_a_cycle_manifest_slice。"
        ),
        "paradigm_ref": {
            "file": "backend/data/workpaper_sync_migration_paradigm.json",
            "json_pointer": "/definition_producer_paradigm",
            "steps_delivered": [2, 3, 4, 5, 6],
            "steps_blocked": [7, 8, 9, 10, 11, 12],
            "step_1_note": (
                "step 1（freeze_manifest_slice）在本 lane 上**不可执行**：它的 verifiable_by "
                "要求守卫按 selection_rule 从 source manifest 现算 entry 集合并等值比对，而本 "
                "lane 在 manifest 里 0 条 entry；硬写一份 entry 清单会正中该 step 的 "
                "forbidden 第一条「手抄 entry 列表 —— 不可复算的清单等于自由文本」。"
            ),
        },
        "why_not_a_cycle_manifest_slice": {
            "verdict": "deliberately_not_a_cycle_manifest_slice",
            "reasons": [
                "AP-1 检测器的 scan_glob 是 backend/data/*_cycle_manifest_slice.json，它把守的是"
                "「用本任务应交付的产物尚不存在当作裁 single_onlyoffice 的理由」；本 lane 的裁决"
                "不是 single_onlyoffice（html_counterpart_verdict == exists），进 scan 集合不增加"
                "任何保护。",
                "范式 step 1 要求 slice 的 entry 集合可从 source manifest 按 selection_rule 现算；"
                "本 lane 在 manifest 里 0 条 entry ⇒ 任何 slice 形态都只能是手抄清单。",
                "F 循环 slice 已把这两份 docx 登记为 excluded_from_slice[0]（归 Tasks 60/61）"
                "并把文件登记进 authoritative_templates（belongs_to_entry=null + excluded_reason）；"
                "再造一份 slice 声称它们是独立 entry 会与那份已冻结的登记冲突，且让两份文件双归属。",
                "新增第 13 份 slice 会把 Property 70 的配对分母由 66 推到 78、把 "
                "test_slice_schema_validator_coverage.py 的事实陈述由 12 推到 13，并辐射 D~N + "
                "abcs 十二轮 per-cycle 守卫 —— 这些代价换不到任何新判据。",
            ],
            "denominators": _slice_denominators(),
            "f_slice_delegation": {
                "path": "backend/data/workpaper_sync_f_cycle_manifest_slice.json",
                "excluded_from_slice_index": 0,
                "delegates_to": "Tasks 60/61",
                "stocktake_entry_id": stocktake["entry_id"],
                "stocktake_entry_capability": stocktake["capability"],
                "partially_wired_word_lane_writers": [
                    row["module"]
                    for row in stocktake["partially_wired_word_lane"]["wired_writers"]
                ],
                "consumed_not_overturned": (
                    "本记录只消费该 slice 的既有结论（BP-6 的 overlay 默认值、BP-9 的 lane "
                    "选择重论证要求、复合 entry_id 范式），不改它一个字节。"
                ),
            },
        },
        "source_ref_semantics": {
            "runtime_locator": "w:tag（sdt_tag）—— 唯一正式协议锚点",
            "one_time_migration_hints": ["${token}", "p{NN} 段落序号"],
            "why_paragraph_ordinal_is_only_a_hint": (
                "Task 6 实测 paragraph_index 的 probe_verdict=failed（文首插 2 段后整体位移）、"
                "run_index 亦 failed（3 run → 2 run）⇒ 两者都在 anchors_blocked 里。契约里的 "
                "source_ref 写 p{NN} 只为「谁来复核都能一眼定位」，运行态 extract/materialize "
                "只按 sdt_tag 定位。"
            ),
            "verbatim_rule": (
                "paragraph_texts_verbatim 一律不 strip：F2-22 的 P003/P029 是空串、"
                "P024 是【提示：…】整段蓝字，strip 会把「模板里到底长什么样」这条判据削弱。"
            ),
        },
        "probe_gate": {
            "source": "backend/data/onlyoffice_word_sdt_carrier_contract.json",
            "task": gate_doc["task"],
            "oo_build": gate_doc["environment"]["oo_build"],
            "carriers_allowed_into_word_engine": downstream["carriers_allowed_into_word_engine"],
            "carriers_blocked": downstream["carriers_blocked"],
            "anchors_allowed": downstream["anchors_allowed"],
            "anchors_blocked": downstream["anchors_blocked"],
            "row_carrier_consequence": downstream["blocked_consequence"],
            "how_this_task_complies": (
                "两份契约的 identity_carriers 现算只含 field_sdt_inline / field_sdt_block；"
                "无任何 repeaters（行域字段）⇒ 不依赖 row_sdt，也没有 row_uuid 需要承载。"
                "锚点只用 w:tag。"
            ),
        },
        "authoritative_templates": {
            "root": "backend/wp_templates/F",
            "reference_copy_status": "absent_from_working_tree",
            "lock_file_policy": "枚举时跳过 `~$` 前缀的 Office 锁文件",
            "files": [
                {
                    "name": item["entry"].template_path.name,
                    "size": item["size"],
                    "sha256": item["template_sha256"],
                    "normalized_structure_hash": item["structure_hash"],
                    "belongs_to_lane_entry": item["entry"].lane_entry_key,
                    "in_runtime_index": False,
                    "runtime_reachability": (
                        "经 wp_template_finder._EXPLICIT_TEMPLATE_RELPATHS['%s'] 显式命中；"
                        "不在 _index.json 里也可达" % item["entry"].sheet_code
                    ),
                }
                for item in built
            ],
            "read_only": (
                "本任务不改模板一个字节：全部 size/sha256 由 hashlib 现算，漂移即 fail closed"
                "（Requirement 6.10 / 9.9）。"
            ),
        },
        "entries": entries,
        "task59_compatibility": {
            "why": (
                "Task 59 的 engine 守卫用 in-test fixture（test_task59_word_sdt_engine.py 的 "
                "plan_contract_payload / plan_spec）而非磁盘契约。本任务发布真契约时必须与它"
                "兼容或显式登记差异，否则 Task 59 会被静默打红。"
            ),
            "shared_contract_id": PLAN_ID,
            "overlapping_stable_keys": [
                "plan/purpose", "plan/scope", "plan/entity_name", "plan/bs_date",
                "plan/warehouses",
            ],
            "must_match_on": ["sdt_tag", "value_type", "mode", "instances", "json_pointer_key"],
            "registered_differences": [
                "字段数：fixture 5 个 vs 真契约 17 个（真契约覆盖磁盘上全部 ${token}）",
                "digests：fixture 用 _digest('f222-template-def') 等占位 vs 真契约用 "
                "canonical_digest(真 payload)",
                "source_ref：fixture 写 `F2-22!p04:${entityName}`（单序号）vs 真契约对两实例"
                "字段写 `F2-22!p01+04:${entityName}`（两个序号都列出，AC 7.4「列出全部 OO 位置」）",
                "json_pointer：fixture 用 /plan/purpose（带 plan 段）vs 真契约用 /purpose"
                "（对齐 checklist_responses 的 F2-22-fields 载荷键，见 html_counterpart）",
            ],
            "difference_is_not_a_conflict_because": (
                "Task 59 的 fixture 是它自己构造的 payload，不读磁盘契约目录；两者共存不产生"
                "第二真源。真契约的 stable key / sdt_tag 命名与 fixture 逐字一致，故 Task 61 "
                "接线时 engine 侧无需改动。"
            ),
        },
        "second_pipeline_deletion_plan": {
            "policy": (
                "Task 60 正文：「现有 to/from OO endpoint 先委派统一 coordinator，Task 61 "
                "全场景通过后才删除第二流程」⇒ **本轮只生成计划，不删任何调用点**。"
            ),
            "delete_files": [],
            "delete_files_why_empty": (
                "两个 sync 模块目前是该 lane 唯一可用通道；在 adapter/bridge 未接线前删除会让"
                "F2-22/F2-23 的在线编辑直接不可用（可用性回退），且 AC 12.7 明确要求「删除前"
                "必须有等价证据和 rollback 点」。"
            ),
            "delegate_then_delete": [
                {
                    "module": item["entry"].router_module,
                    "endpoints": [
                        item["entry"].to_oo_endpoint, item["entry"].from_oo_endpoint
                    ],
                    "already_delegated": (
                        "commit 侧已走统一 writer：build_content_mutation_service_writer(db)."
                        "commit_bytes(...)（Task 19）"
                    ),
                    "still_second_pipeline": [
                        "materialize 侧仍自建：fill_plan_docx / fill_summary_docx 直接从模板"
                        "复制+占位符替换，不经 MaterializeCoordinator，也不以 current published "
                        "representation 为底（违反 AC 7.9 的「不得用模板重生成覆盖」）",
                        "extract 侧仍自建：extract_fields_from_docx 用中文章节标题正则切分"
                        "（`1．监盘目的[：:]`…），不按 w:tag 定位（违反 Requirement 7.1）",
                    ],
                    "delete_after": [
                        "Task 61 全场景通过（真实 OO 9.4 逐 scenario evidence 全绿）",
                        "rollback 点：本记录冻结的 template/instrumentation/contract digest 链",
                    ],
                    "equivalence_evidence_required_by_ac_12_7": [
                        "同一 docx 上 tagged-SDT extract 与现有中文标题正则 extract 的字段级"
                        "等值报告（逐字段 diff，不是抽样）",
                        "Word-only 正文两次 materialize 前后规范化等值（Property 31）",
                    ],
                }
                for item in built
            ],
            "must_not_delete": [
                "backend/wp_templates/F/F2-22 存货监盘计划.docx",
                "backend/wp_templates/F/F2-23 存货监盘小结.docx",
            ],
        },
        "blocking_preconditions": [
            {
                "id": "BP-10",
                "blocks": ["contract_installation", "definition_bundle", "adapter_registration"],
                "what": (
                    "F2 Word lane 在 source-backed manifest 里没有 entry ⇒ 生产契约目录与 "
                    "registry.DELIVERED_PER_ENTRY_CONTRACTS 的双向等值判据无法满足"
                    "（登记行的 entry_id 必须命中 manifest）。"
                ),
                "status": "open",
                "must_fix_before": "Task 61 注册 adapter / 装载生产契约",
                "observable_consequences": [
                    "契约只能 staged 在 workpaper_sync_word_contracts/，不进 "
                    "contracts.available_contract_ids()",
                    "registry.assert_contract_file_current(RG-11) 会因生产目录无此文件而拒绝注册",
                    "manifest 的 capability_counts / unadjudicated_count 里看不到这两个 entry ⇒ "
                    "平台级收口计数漏掉整条 Word lane",
                ],
                "source_refs": [
                    "backend/data/workpaper_sync_entry_manifest.json",
                    "backend/tests/workpaper_sync/test_task13_contract_registry.py",
                    "backend/app/services/workpaper_sync/adapters/registry.py",
                ],
                "numbering_note": (
                    "编号续接 F 循环 slice 的 BP-1..BP-9（本记录消费它们、不改它们）；"
                    "BP-10 起为 Word lane 新查出的阻断项。"
                ),
            },
            {
                "id": "BP-11",
                "blocks": ["definition_bundle", "published_representation"],
                "what": (
                    "approved definition bundle 需要 DB 侧 definition 行（typed slot 的 "
                    "slot_ref 必须形如 `definition:<uuid>`），离线无法产出；本记录只给可复算的 "
                    "slot digest 计划。"
                ),
                "status": "open",
                "must_fix_before": "Task 15 / Task 36 finalize published representation",
                "observable_consequences": [
                    "models.validate_bundle_slot 对 slot_ref=None 的 definition slot 直接抛 "
                    "BundleIntegrityError（守卫正向断言这条拒绝）",
                    "WordEngineBinding 只能用 offline_candidate_validation 模式；"
                    "assert_may_publish() 恒抛",
                ],
                "source_refs": [
                    "backend/app/services/workpaper_sync/models.py",
                    "backend/app/services/workpaper_sync/word_sdt_engine.py",
                ],
            },
            {
                "id": "BP-12",
                "blocks": ["published_representation", "adapter_registration", "descriptor_bridge"],
                "what": (
                    "本 lane 的 OO 挂载点**存在但不消费 descriptor**：`GtF2StocktakeBundle.vue` "
                    "里有一个 mode 门控的 `<GtOnlyOfficeSheet>`（F2-22 / F2-23 是它的两个 tab），"
                    "而该组件自行请求 `/sheets/{sheet}/onlyoffice-config`、零 descriptor prop、"
                    "无 durable ack ⇒ AC 11.5 / Property 47 要求的「只消费含 approved bundle 的 "
                    "descriptor 并暴露可 await 的 forceSave()」在本 lane 上**没有实现**。"
                ),
                "status": "open",
                "must_fix_before": "Task 61 接 descriptor/bridge 与 recovery UI",
                "observable_consequences": [
                    "AC 11.5 要求的 forceSave()/ready/dirty/incoming-durable/applied/conflict/"
                    "recovery-case 事件在本 lane 上无承载者",
                    "前端只有 useF2StocktakeDualMode 的两个 REST 按钮 + 一个自取 config 的 OO "
                    "挂载点，无 durable ack 语义",
                    "manifest 扫描器仍发现不到本 lane（BP-10 的同一根因的另一面）：扫描器按 "
                    "entry 级 descriptor/adapter 形态识别，自取 config 的挂载点不构成 entry",
                ],
                "correction_note": (
                    "🔴 首版把本项写成「本 lane 没有 OO 组件挂载点」，实测错（见 BP-15）。"
                    "结论方向不变（descriptor/bridge 仍被阻断、Property 47 仍不宣称通过），"
                    "但理由从「分母为空」改成「承载者存在且形态相反」——"
                    "前者会让守卫把 `oo_mount_site_count == 0` 当基线锁死。"
                ),
                "source_refs": [
                    "audit-platform/frontend/src/components/workpaper/composables/"
                    "useF2StocktakeDualMode.ts",
                    "audit-platform/frontend/src/components/workpaper/GtF2StocktakeBundle.vue",
                    "audit-platform/frontend/src/components/workpaper/GtOnlyOfficeSheet.vue",
                ],
            },
            {
                "id": "BP-13",
                "blocks": ["capability_verdict", "evidence"],
                "what": (
                    "AC 12.10 / 14.1 要求的服务端 evidence summary 与逐 scenario 产物级测试"
                    "在本 lane 上一条都没有（sync_test_run_id / "
                    "required_scenario_set_digest 均为 null）。"
                ),
                "status": "open",
                "must_fix_before": "把 capability 从 null 改成 bidirectional",
                "observable_consequences": [
                    "两个 entry 的 verification_state 只能是 UNVERIFIABLE",
                    "Property 69 分母为空 ⇒ 本任务不宣称它通过",
                ],
                "source_refs": [
                    "backend/app/services/workpaper_sync/evidence.py",
                    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/"
                    "requirements.md",
                ],
            },
            {
                "id": "BP-14",
                "blocks": ["html_projection_fidelity"],
                "what": (
                    "F2-22 的 `${specialNotes}` 是**合并段**：HTML 侧是三个独立字段"
                    "（remoteWarehouse / fraudRisk / expertNeeded），docx 侧只有一段；现有 "
                    "extract 用中文标签（「异地」「舞弊」「专家」）正则把它拆回三个字段。"
                ),
                "status": "open",
                "must_fix_before": "Task 61 用 tagged SDT 取代中文标题正则",
                "observable_consequences": [
                    "Requirement 7.1 明禁用中文 label 作定位/身份；现有拆分是中文标签依赖",
                    "审计师把「异地」改写成「异地仓库」时 fraudRisk/expertNeeded 会串值或丢值",
                    "本契约按 docx 事实只声明一个 plan/special_notes 字段 ⇒ 与 HTML 侧三字段的"
                    "映射必须由 Task 61 用三个独立 inline SDT 或显式合并规则解决，不得靠正则",
                ],
                "source_refs": [
                    "backend/app/services/f2_stocktake_plan_sync.py",
                    "backend/wp_templates/F/F2-22 存货监盘计划.docx",
                ],
            },
            {
                "id": "BP-15",
                "blocks": ["second_pipeline_inventory", "descriptor_bridge"],
                "what": (
                    "本 lane 的第二流程**不止两个 REST 端点**：还有一条 OO 原生通道 —— "
                    "`GtF2StocktakeBundle.vue` 的 `<GtOnlyOfficeSheet>` 自取 "
                    "`/api/workpapers/{wp_id}/sheets/{sheet}/onlyoffice-config`，"
                    "`wp_onlyoffice_router.post_sheet_onlyoffice_callback` 里另有一段 "
                    "`_save_wp_code in (\"F2-22\", \"F2-23\") … .docx` 的 fields 回写分支。"
                    "首版把 BP-12 写成「本 lane 没有 OO 组件挂载点」，因此这条通道整条漏登记。"
                ),
                "status": "open",
                "must_fix_before": "Task 61 接 descriptor/bridge；Task 66 生成 legacy 删除计划",
                "observable_consequences": [
                    "AC 12.7 的「删除第二套半闭环」清册若只列两个 REST 端点，则 OO config/"
                    "callback 这条腿会在 Task 66/72 的删除计划里缺席",
                    "该 callback 分支绕开 per-entry contract：它按 `extract_fields_from_docx` 的"
                    "中文标题正则取值（同 BP-14 的根因），不经 w:tag",
                    "Property 47 的分母不是 0：挂载点存在但自取 config ⇒ 它是反例而非空集",
                ],
                "source_refs": [
                    "audit-platform/frontend/src/components/workpaper/GtF2StocktakeBundle.vue",
                    "audit-platform/frontend/src/components/workpaper/GtOnlyOfficeSheet.vue",
                    "backend/app/routers/wp_onlyoffice_router.py",
                ],
                "numbering_note": (
                    "本轮守卫（Task 60 第二段交付）新查出的缺陷，续接 BP-14。"
                    "处置归属：Task 61 接线 + Task 66 删除计划，不在本任务内改生产代码。"
                ),
            },
        ],
        "cross_entry_isolation": {
            "rule": (
                "两个 entry 的 template / instrumentation / contract / bundle plan / evidence "
                "逐项独享，不交叉复用（Property 70 / Task 60 正文「每个 F2 entry 保存自身 "
                "bundle digest 与 scenario evidence」）。"
            ),
            "assertions": [
                "两个 contract_id 不同且各自的 canonical_sha256 不同",
                "两个 template_sha256 / normalized_structure_hash 各不相同",
                "两个 template_definition_sha256 / instrumentation_definition_sha256 各不相同",
                "两个 authority_model definition payload 的 entry_lane_key 各指自己",
                "每个 sdt_tag 的 contract 段等于自己的 contract_id ⇒ 一份文档的 tag 不可能被"
                "另一份契约解析（WordEngineBinding.resolve_tag 对 contract 段不符 fail closed）",
                "两个 entry 的 fields_item_id 不同（F2-22-fields / F2-23-fields）⇒ HTML 侧载荷"
                "也不共用",
            ],
            "staged_contract_files": [f"{item['entry'].contract_id}.json" for item in built],
            "production_contract_dir_untouched": True,
        },
        "descriptor_consumption": _descriptor_consumption_facts(),
        "properties_verified": {
            "Property 31": {
                "claim": "PASS",
                "denominator": 2,
                "how": (
                    "对两份权威 docx 各跑一次真实往返：instrument_docx_bytes 注入 tagged SDT → "
                    "materialize_word_projection 写值两次 → verify_word_only_regions 断言 SDT 外"
                    "正文 / 层级 / 表格形状 / 受保护部件逐 aspect 等价，且 coverage 各项 > 0"
                    "（防空集恒等价）。"
                ),
            },
            "Property 32": {
                "claim": "PASS",
                "denominator": 2,
                "how": (
                    "`${entityName}` 在两份文档里各出现 2 次（现算）⇒ 同 stable key 两实例。"
                    "把两处改成不同值后 extract_word_projection 必须产出 "
                    "duplicate_word_instance 冲突并列出全部 XPath。"
                ),
            },
            "Property 47": {
                "claim": "NOT_CLAIMED_CARRIER_IS_A_COUNTEREXAMPLE",
                "denominator": 1,
                "why": (
                    "本 lane 有 1 个 OO 挂载点（`GtF2StocktakeBundle.vue` 的 "
                    "`<GtOnlyOfficeSheet>`，现算），但它**自行请求 config**、零 descriptor "
                    "prop、无 durable ack ⇒ 它是 Property 47 的**反例**而不是通过项（BP-12 / "
                    "BP-15）。守卫断言前提（挂载点数、self-config 站点、descriptor prop 数全部"
                    "现算）与判据承载者存在，明确不宣称通过。"
                ),
                "first_version_said": (
                    "denominator 0 / 「无挂载点」—— 实测错，已按现算结果更正（BP-15）。"
                ),
            },
            "Property 69": {
                "claim": "NOT_CLAIMED_EMPTY_DENOMINATOR",
                "denominator": 0,
                "why": (
                    "没有任何 bidirectional entry、没有 sync_test_run、没有 required scenario "
                    "set ⇒ 「服务端重算逐 scenario 实体」无对象。守卫断言前提"
                    "（verification_state 全 UNVERIFIABLE + reasons 非空 + 计数现算），不宣称通过。"
                ),
            },
        },
        "property_denominators": {
            "not_claimed": ["Property 47", "Property 69"],
            "why_not_claimed_is_recorded": (
                "不宣称的两条各有各的理由，不能混成一句：**Property 69** 分母为空（无 "
                "bidirectional entry / 无 sync_test_run / 无 required scenario set）——"
                "空分母重言式是假绿源；**Property 47** 分母是 1 但承载者是**反例**"
                "（挂载点自取 config、零 descriptor）⇒ 也不宣称通过。把两种「不宣称」分别写进"
                "产物，后来者才不会把「有承载者」误读成「已通过」。"
            ),
            "empty_denominator": ["Property 69"],
            "carrier_is_a_counterexample": ["Property 47"],
        },
        "counters": {
            "lane_entries": len(built),
            "contracts_published_reviewed": len(built),
            "contracts_installed_into_production_inventory": 0,
            "authority_models_published": len(built),
            "definition_bundles_published": 0,
            "published_representations_finalized": 0,
            "adapters_registered": 0,
            "capability_verdict_pending": len(built),
            "adjudicated_as_bidirectional": 0,
            "adjudicated_as_single_onlyoffice": 0,
            "adjudicated_as_single_html": 0,
            "adjudicated_as_unreachable": 0,
            "entries_left_unverifiable": len(built),
            "managed_fields_total": sum(len(item["entry"].fields) for item in built),
            "managed_fields_by_entry": {
                item["entry"].sheet_code: len(item["entry"].fields) for item in built
            },
            "multi_instance_fields_total": sum(
                1
                for item in built
                for row in item["field_evidence"]
                if row["occurrences_in_document_xml"] > 1
            ),
            "block_carrier_fields_total": sum(
                1
                for item in built
                for row in item["field_evidence"]
                if row["carrier"] == "field_sdt_block"
            ),
            "row_scoped_fields_total": 0,
            "second_pipeline_endpoints_deleted": 0,
            "counting_notes": (
                "每一族计数都能从 entries 现算：lane_entries=len(entries)；"
                "contracts_published_reviewed=review_status=='reviewed' 的条数；"
                "contracts_installed_into_production_inventory 由 "
                "contracts.available_contract_ids() 现算（本任务后仍为 0）；"
                "authority_models_published=authority_model.definition_sha256 非空条数；"
                "definition_bundles_published / published_representations_finalized / "
                "adapters_registered 三项由 definition_bundle / published_representation / "
                "adapter_id 为 null 的条数取补；capability_verdict_pending=capability 为 null "
                "条数；adjudicated_as_* 四项按 capability 值分桶；entries_left_unverifiable="
                "verification_state=='UNVERIFIABLE' 条数；managed_fields_total 与 "
                "managed_fields_by_entry 由 field_evidence 长度求和；multi_instance_fields_total "
                "由 occurrences_in_document_xml>1 计数；block_carrier_fields_total 由 "
                "carrier=='field_sdt_block' 计数；row_scoped_fields_total 由 repeaters 长度求和"
                "（两份契约都没有 repeaters）；second_pipeline_endpoints_deleted=0 是本轮策略"
                "（Task 61 全场景通过后才删）。四个 0 不得解读为「已具备双向能力」。"
            ),
        },
        "requirements_covered": ["7.3", "7.4", "7.9", "11.5", "12.3", "12.7", "12.10", "14.1"],
        "ac_12_3_compliance": {
            "text_role": "Word pilot SHALL 为 F2-22/F2-23；pilot 未通过 tagged SDT 往返保留前不得批量迁移其他 DOCX",
            "how": (
                "本任务只处理 F2-22 / F2-23 两份 docx；authoritative_templates.files 现算恰 2 条，"
                "两个 lane entry 的 wp_code 恰为 F2-22 / F2-23。平台上另有 5 条 docx manifest "
                "entry（A10B/A12B/A16B/A17B/GtWpRenderer）与 45 张 docx 权威册，本任务一条未动 ⇒ "
                "「不得批量迁移其他 DOCX」有可复算判据而不是承诺。"
            ),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# 落盘 / 校验
# ════════════════════════════════════════════════════════════════════════════
def render(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def generate() -> dict[Path, str]:
    gate = WI.WordSdtCarrierGate.load()
    built = [build_entry_payloads(entry, gate) for entry in ENTRIES]
    out: dict[Path, str] = {}
    for item in built:
        target = STAGED_CONTRACT_DIR / f"{item['entry'].contract_id}.json"
        out[target] = render(item["contract_payload"])
    out[PUBLICATION_PATH] = render(build_publication_record(built))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只比对，不落盘")
    group.add_argument("--write", action="store_true", help="覆盖产物")
    args = parser.parse_args()

    rendered = generate()
    drift: list[str] = []
    for path, text in rendered.items():
        rel = path.relative_to(_REPO).as_posix()
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"[WRITE] {rel} ({len(text)} chars)")
            continue
        if not path.is_file():
            drift.append(f"{rel}: 缺失")
        elif path.read_text(encoding="utf-8") != text:
            drift.append(f"{rel}: 与现算结果不一致")
        else:
            print(f"[OK] {rel}")
    if drift:
        for line in drift:
            print(f"[DRIFT] {line}")
        return 1
    # 结构化摘要（人读用）
    fingerprints = {
        entry.sheet_code: structure_fingerprint(entry.template_path.read_bytes())
        for entry in ENTRIES
    }
    for code, fp in fingerprints.items():
        print(f"[INFO] {code}: sdt_nodes={len(fp.sdt_nodes)} errors={fp.errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
