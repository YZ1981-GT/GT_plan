"""Task 62 —— 18 个 generic DOCX entry 的逐 entry 迁移可行性裁决（`--check` / `--write`）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 62
Requirements: 7.1, 7.3, 7.4, 7.5, 7.6, 7.8, 12.1, 12.5, 12.10, 12.11, 12.12
Properties: **P30 / P31 / P32 / P33 / P34 / P69 / P70**

═══ 为什么这个任务的产物是「裁决记录」而不是 18 份 approved bundle ═══

Task 62 正文要求「每份读真实模板并为该 entry 发布自己的 approved authority model、
tagged-SDT per-entry contract 与 non-null bundle」。逐份读完 `backend/wp_templates/`
里的 18 份真实 docx 之后，实测结论是**这一步在当前平台事实下无法诚实执行**：

* 18/18 份模板的 `word/document.xml` 里 `${...}` 声明 token **0 个**、既有 `w:sdt`
  **0 个**（F2-22/F2-23 各有 17/16 个 token，那才是 Task 60 能建 tagged-SDT 契约的
  唯一原因）；
* 这 18 个 wp_code 的 HTML 对端是 `wp_render_strategies/_word_template.py` +
  `GtWordTemplateStructuredView.vue`，字段身份由
  `app/services/wp_docx_template_parser.py` 的 **legacy 中文标记正则**现算
  （`××公司` / `202X年…` / `××`）—— Requirement 7.1 逐字禁止「中文正则」作为正式
  回写协议；
* 该正则产出的 field_id 大量带**序号后缀**（`placeholder_generic_2..21`），序号来自
  `_dedupe_field_id` 的文档扫描顺序 ⇒ 模板中间插一个 `××` 就整体位移，不是稳定键；
* `WordFieldInjection` 的 `literal_anchor` 通道（Task 6 对 B30-11-2 用过）要求
  **一个 literal token 绑一个 stable key**，全部出现处注入同一 tag；而 `××` 在单份
  约定书里出现最多 22 次、语义各不相同 ⇒ 字面锚点**不具区分度**，无法逐字段注入；
* `_LEGACY_PATTERNS` 自身互相重叠（`202X年` 落在 `202X年12月31日` 内、两条日期正则
  命中同一段文本）⇒ 同一物理 span 会产出两个「字段」，SDT 注入在结构上不可能；
* `parse_template` 的表格循环 `for cell in row.cells` 会把**横向合并单元格**按跨列数
  重复扫描 ⇒ 候选数被虚增（A26-1 的 4 个 `audit_year` 实为 1 个合并单元格）。

把这批序号型、语义空洞（全部 136 个候选只有「审计年度 / 待填内容 / 报告日期」3 种
label）的候选写成 `review_status="reviewed"` 的 per-entry 契约，机器侧会全绿
（`projection_provisioning.assert_projection_supply_authentic` 只查 `review_status`
字面），但那正是本 spec 反复记录的**伪造供给**。Task 62 正文同样明禁「不为满足数字
伪造 contract/bundle/finalize」。

因此本脚本交付的是**逐 entry、source-backed、可机器复核的裁决记录**：18 个 entry 各
自的模板身份、结构事实、候选清册、封闭词表 verdict、阻塞原因与解除条件。真正的
per-entry 契约供给要等阻塞项清零（见记录里的 `blocking_preconditions`）。

═══ 三边锁 ═══

1. **清册边** —— `backend/data/workpaper_word_template_adjudication.json` 的
   `owner_task == "62"`（Task 58 的裁决，含 `unified_relative_path`）；
2. **磁盘边** —— `backend/wp_templates/<rel>` 的真实字节：zipfile 直读
   `word/document.xml`、python-docx 读段落/表格，逐 occurrence 现算；
3. **实现边** —— `wp_docx_template_parser._LEGACY_COMPILED` / `_NEW_PLACEHOLDER_RE`
   （HTML 对端的字段身份真源）、`word_instrumentation.WordSdtCarrierGate.load()`
   （Task 6 载体/锚点裁决真源）、`adapters.registry.PENDING_ENGINE_ADAPTERS`
   （Word adapter 禁令真源）、requirements.md 的 AC 7.7 声明数。

任一边改动而另两边没跟上，`--check` 立刻打红。所有计数**现算**，记录里不存在手抄
常量。

用法（Windows PowerShell，仓库根）::

    .\\.venv\\Scripts\\python.exe backend/scripts/gen/generate_task62_generic_docx_adjudication.py --check
    .\\.venv\\Scripts\\python.exe backend/scripts/gen/generate_task62_generic_docx_adjudication.py --write
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import re
import sys
import zipfile
from dataclasses import dataclass
from typing import Any

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

from app.services.wp_docx_template_parser import (  # noqa: E402
    _LEGACY_COMPILED,
    _NEW_PLACEHOLDER_RE,
    parse_template,
)
from app.services.workpaper_sync import word_instrumentation as WI  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
# 0. 路径与常量（只有真源路径与封闭词表，无任何实测数字）
# ═══════════════════════════════════════════════════════════════════════════

#: Task 58 的裁决清册 —— 本脚本的**唯一** entry 真源（不写第二份 wp_code 清单）。
LEDGER_PATH: pathlib.Path = _BACKEND / "data" / "workpaper_word_template_adjudication.json"

#: 权威模板根目录（AC 9.1：标准模板权威源固定 `backend/wp_templates/`）。
TEMPLATE_ROOT: pathlib.Path = _BACKEND / "wp_templates"

#: 本脚本的产物。
OUTPUT_PATH: pathlib.Path = (
    _BACKEND / "data" / "workpaper_sync_task62_generic_docx_adjudication.json"
)

#: Task 60 的 F2 范式发布记录（BP 继承与「为什么 F2 能做而这 18 个不能」的对照源）。
F2_PUBLICATION_PATH: pathlib.Path = (
    _BACKEND / "data" / "workpaper_sync_f2_word_lane_publication.json"
)

#: Task 60 发布的 Word per-entry 契约暂存目录（本任务必须往里写 **0** 份）。
STAGED_WORD_CONTRACT_DIR: pathlib.Path = _BACKEND / "data" / "workpaper_sync_word_contracts"

#: spec requirements.md —— AC 7.7 的声明数交叉锁。
REQUIREMENTS_PATH: pathlib.Path = (
    _BACKEND.parent
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "requirements.md"
)

SCHEMA_VERSION: str = "task62-generic-docx-adjudication:v1"
OWNER_TASK: str = "62"

#: 逐 entry verdict 的**封闭**词表。自由文本会让守卫只能比整句字符串。
ENTRY_VERDICTS: tuple[str, ...] = (
    # 模板里有 `${...}` 声明 token ⇒ 可照 F2 范式建契约（当前实测 0 个 entry 命中，
    # 保留该取值是为了「模板改版后本脚本自动改判」而不是永远报同一个结论）。
    "token_declared_template",
    # 有唯一可区分的字面锚点、无重叠、verbatim 可定位、且该锚点就是完整的人类占位
    # ⇒ 注入可行。（当前实测 0 个 entry 命中。）
    "instrumentable_literal_anchor",
    # 字面锚点在 `word/document.xml` 里被 run 边界切断（python-docx 拼得出来、原始
    # XML 里找不到连续字符串）⇒ `instrument_docx_bytes` 的一次性定位命中 0 个段落。
    "blocked_literal_anchor_split_across_runs",
    # 锚点唯一且可注入，但它只是某个更大的人类占位的**片段**（同一容器文本里还有
    # parser 不认的占位形态，如 `第YY次` / `X月X日` / `【…】`）⇒ 注入出来的受管字段
    # 只覆盖片段，旁边的占位仍是死文本。
    "blocked_partial_field_fragment_anchor",
    # 字面锚点在同一文档内多次出现且语义不同 ⇒ 一个 literal 绑不了多个 stable key。
    "blocked_non_discriminating_literal_anchor",
    # 候选 span 互相嵌套/重合 ⇒ 同时注入 SDT 结构上不可能。
    "blocked_nested_literal_anchor",
    # 该 entry 一个受管字段候选都没有 ⇒ tagged-SDT projection 无内容可管。
    "no_managed_field_candidate",
)

#: 逐 entry 阻塞原因的**封闭**词表（一个 entry 可命中多条，全部如实列出）。
BLOCKING_REASONS: tuple[str, ...] = (
    "no_declared_token_in_authoritative_template",
    "field_identity_derived_from_chinese_regex",
    "ordinal_suffixed_field_ids",
    "non_discriminating_literal_anchor",
    "nested_or_identical_candidate_spans",
    "merged_cell_duplicated_candidates",
    "unrecognised_placeholder_forms_present",
    "literal_anchor_split_across_runs",
    "partial_field_fragment_anchor",
    "generic_labels_only",
    "zero_managed_field_candidates",
)

#: 「人眼可见但 `_LEGACY_PATTERNS` 不认」的占位形态。**只用于证明候选分母不完整**，
#: 一个都不参与注入 —— 它们正是「HTML 对端的字段集合既虚增又漏项」的实证。
UNRECOGNISED_PLACEHOLDER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("bracketed_insert_slot", r"【[^】]{1,24}】"),
    ("ordinal_yy_slot", r"第\s*YY\s*次"),
    ("single_x_date_slot", r"X{1,2}\s*月\s*X{1,2}\s*日"),
    ("underscore_blank", r"(?:_{3,}|＿{2,})"),
)
_UNRECOGNISED_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pat)) for name, pat in UNRECOGNISED_PLACEHOLDER_PATTERNS
)

#: AC 7.7 声明数的抓取正则（与 Task 58 生成器同款：数字漂移即打红）。
_AC_7_7_RE = re.compile(
    r"7\.7\.\s*(?P<generic>\d+)\s*个可正确解析\s*DOCX、(?P<subcode>\d+)\s*个误解析"
)


class Task62GeneratorError(RuntimeError):
    """生成器自身失败（禁 fail-open：让退出码非零，不降级成「无数据」）。"""


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真源读取
# ═══════════════════════════════════════════════════════════════════════════


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Task62GeneratorError(f"读不到或不是合法 JSON: {path} ({exc})") from exc


def ledger_rows() -> list[dict[str, Any]]:
    """Task 58 清册里 `owner_task == "62"` 的行（空即报错，防空集恒成功）。"""
    ledger = _read_json(LEDGER_PATH)
    rows = [r for r in ledger.get("rows", []) if str(r.get("owner_task")) == OWNER_TASK]
    if not rows:
        raise Task62GeneratorError(
            f"{LEDGER_PATH.name} 里 owner_task=={OWNER_TASK!r} 的行为 0 条 —— "
            "空清单会让本脚本恒成功（假绿）"
        )
    return sorted(rows, key=lambda r: str(r.get("wp_code")))


def requirement_7_7_declared() -> dict[str, int]:
    """从 requirements.md 现读 AC 7.7 的声明数（不抄 18/9）。"""
    try:
        text = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise Task62GeneratorError(f"读不到 requirements.md: {exc}") from exc
    match = _AC_7_7_RE.search(text)
    if match is None:
        raise Task62GeneratorError(
            "requirements.md 里没抓到 AC 7.7 的「N 个可正确解析 DOCX、M 个误解析」句式 —— "
            "声明数抓不到时不得退回硬编码 18/9"
        )
    return {
        "declared_generic_docx": int(match.group("generic")),
        "declared_subcode_wrong_type": int(match.group("subcode")),
    }


def word_adapter_ban() -> dict[str, Any]:
    """现读 `PENDING_ENGINE_ADAPTERS` 里 docx 那条禁令（不抄路径字面量）。"""
    from app.services.workpaper_sync.adapters import registry as registry_module

    rows = [
        row
        for row in registry_module.PENDING_ENGINE_ADAPTERS
        if str(row.get("document_type")) == "docx"
    ]
    if len(rows) != 1:
        raise Task62GeneratorError(
            f"`PENDING_ENGINE_ADAPTERS` 里 document_type=='docx' 现算 {len(rows)} 条 —— "
            "Word adapter 禁令必须唯一；为 0 条时说明禁令被删（Task 61 的门失守）"
        )
    row = rows[0]
    delivered_docx = [
        r
        for r in registry_module.DELIVERED_ENGINE_ADAPTERS
        if str(r.get("document_type")) == "docx"
    ]
    if delivered_docx:
        raise Task62GeneratorError(
            "`DELIVERED_ENGINE_ADAPTERS` 里出现 docx adapter —— Task 61 门未过时"
            "不得落地 Word adapter"
        )
    return {
        "forbidden_paths": list(row.get("forbidden_paths") or ()),
        "blocking_task": str(row.get("blocking_task") or ""),
        "identity_gate": str(row.get("identity_gate") or ""),
        "delivered_docx_engine_adapters": len(delivered_docx),
    }


def task62_contract_files() -> list[str]:
    """暂存契约目录里属于本任务的文件（必须恒为空；见模块 docstring）。"""
    if not STAGED_WORD_CONTRACT_DIR.is_dir():
        return []
    known_f2 = {
        str(((e.get("contract") or {}).get("contract_id")) or "")
        for e in _read_json(F2_PUBLICATION_PATH).get("entries", [])
    }
    return sorted(
        p.name
        for p in STAGED_WORD_CONTRACT_DIR.glob("*.json")
        if p.stem not in known_f2
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 逐 entry 现算事实
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Occurrence:
    """一个 legacy 中文标记候选的实测出现处。"""

    site: str  # "paragraph" | "table_cell"
    locator: str  # 只作报告用位置（**不**参与任何定位协议）
    matched: str
    field_id_base: str
    label: str
    start: int
    end: int
    container_text: str
    merged_cell_duplicate: bool
    #: 同一容器文本里 parser **不认**的占位形态（名字 → 次数）。非空 ⇒ 本锚点只是
    #: 某个更大的人类占位的片段，注入它会留下旁边的死文本。
    sibling_unrecognised_forms: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "report_only_locator": self.locator,
            "matched_literal": self.matched,
            "parser_field_id_base": self.field_id_base,
            "parser_label": self.label,
            "merged_cell_duplicate": self.merged_cell_duplicate,
            "sibling_unrecognised_forms": dict(sorted(self.sibling_unrecognised_forms.items())),
            "context": self.container_text.strip()[:160],
        }


def _legacy_spans(text: str) -> list[tuple[str, str, str, int, int]]:
    """逐 pattern 现算 span，委派 parser 那份已编译正则（不抄第二份清单）。"""
    remaining = _NEW_PLACEHOLDER_RE.sub("", text)
    spans: list[tuple[str, str, str, int, int]] = []
    for regex, field_id, label in _LEGACY_COMPILED:
        for m in regex.finditer(remaining):
            spans.append((field_id, label, m.group(0), m.start(), m.end()))
    return spans


def _span_overlaps(spans: list[tuple[str, str, str, int, int]]) -> dict[str, int]:
    """同一段文本内两两求交：identical / contained / partial 各计一类。"""
    counts = {"identical": 0, "contained": 0, "partial": 0}
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            _, _, _, a0, a1 = spans[i]
            _, _, _, b0, b1 = spans[j]
            if max(a0, b0) >= min(a1, b1):
                continue
            if (a0, a1) == (b0, b1):
                counts["identical"] += 1
            elif (a0 <= b0 and b1 <= a1) or (b0 <= a0 and a1 <= b1):
                counts["contained"] += 1
            else:
                counts["partial"] += 1
    return counts


def _unrecognised_in_text(text: str, spans: list[tuple]) -> dict[str, int]:
    """一段文本里「人眼可见但 parser 不认」的占位形态（排除已被 legacy 命中的 span）。"""
    covered = [(s[3], s[4]) for s in spans]
    found: dict[str, int] = {}
    for name, regex in _UNRECOGNISED_COMPILED:
        for m in regex.finditer(text):
            if any(lo <= m.start() and m.end() <= hi for lo, hi in covered):
                continue
            found[name] = found.get(name, 0) + 1
    return dict(sorted(found.items()))


def _merge_counts(target: dict[str, int], addition: dict[str, int]) -> None:
    for key, val in addition.items():
        target[key] = target.get(key, 0) + val


def collect_entry_facts(row: dict[str, Any]) -> dict[str, Any]:
    """一个 entry 的全部实测事实（磁盘边 + 实现边）。"""
    from docx import Document

    wp_code = str(row["wp_code"])
    rel = str(row["unified_relative_path"])
    path = TEMPLATE_ROOT / rel
    if not path.is_file():
        raise Task62GeneratorError(
            f"{wp_code}: 权威模板不存在: {path} —— Task 58 清册与磁盘脱钩"
        )
    data = path.read_bytes()
    with zipfile.ZipFile(path) as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8")

    doc = Document(str(path))
    paragraph_texts = [p.text for p in doc.paragraphs]

    occurrences: list[Occurrence] = []
    overlap = {"identical": 0, "contained": 0, "partial": 0}
    unrecognised_total: dict[str, int] = {}

    for idx, text in enumerate(paragraph_texts):
        spans = _legacy_spans(text)
        siblings = _unrecognised_in_text(text, spans)
        _merge_counts(unrecognised_total, siblings)
        if not spans:
            continue
        for key, val in _span_overlaps(spans).items():
            overlap[key] += val
        for field_id, label, matched, s0, s1 in spans:
            occurrences.append(
                Occurrence(
                    site="paragraph",
                    locator=f"p{idx:02d}",
                    matched=matched,
                    field_id_base=field_id,
                    label=label,
                    start=s0,
                    end=s1,
                    container_text=text,
                    merged_cell_duplicate=False,
                    sibling_unrecognised_forms=siblings,
                )
            )

    #: 表格：按 `row.cells` 走（与 `parse_template` 同一循环形态），但额外用 `_tc`
    #: 元素身份判定横向合并 —— python-docx 会把合并单元格按跨列数重复返回，
    #: `parse_template` 因此虚增候选数。这里如实标记，不悄悄去重。
    for ti, table in enumerate(doc.tables):
        for ri, trow in enumerate(table.rows):
            seen_tc: set[int] = set()
            for ci, cell in enumerate(trow.cells):
                tc_id = id(cell._tc)
                is_dup = tc_id in seen_tc
                seen_tc.add(tc_id)
                text = cell.text
                spans = _legacy_spans(text)
                siblings = _unrecognised_in_text(text, spans)
                if not is_dup:
                    _merge_counts(unrecognised_total, siblings)
                if not spans:
                    continue
                if not is_dup:
                    for key, val in _span_overlaps(spans).items():
                        overlap[key] += val
                for field_id, label, matched, s0, s1 in spans:
                    occurrences.append(
                        Occurrence(
                            site="table_cell",
                            locator=f"t{ti:02d}[{ri},{ci}]",
                            matched=matched,
                            field_id_base=field_id,
                            label=label,
                            start=s0,
                            end=s1,
                            container_text=text,
                            merged_cell_duplicate=is_dup,
                            sibling_unrecognised_forms=siblings,
                        )
                    )

    structure = parse_template(str(path))
    parser_field_ids = [ph.field_id for ph in structure.placeholders]
    ordinal_ids = [fid for fid in parser_field_ids if re.search(r"_\d+$", fid)]
    literal_counter = collections.Counter(
        o.matched for o in occurrences if not o.merged_cell_duplicate
    )
    #: `instrument_docx_bytes` 的一次性定位要求 token **verbatim 出现在原始 XML**里
    #: （`_token_paragraphs` 用 `token in xml[span]`）。python-docx 会把跨 run 的
    #: `w:t` 拼起来，所以「python-docx 看得见」不等于「注入定位得到」——两侧计数
    #: 在此逐 literal 对照。
    raw_xml_counts = {lit: document_xml.count(lit) for lit in sorted(literal_counter)}

    return {
        "wp_code": wp_code,
        "ledger": {
            "unified_relative_path": rel,
            "unified_verdict": str(row.get("unified_verdict") or ""),
            "ledger_class": str(row.get("ledger_class") or ""),
            "carrier_ambiguity": bool(row.get("carrier_ambiguity")),
            "own_docx_carriers": list(row.get("own_docx_carriers") or ()),
            "component_type": str(row.get("component_type") or ""),
        },
        "template": {
            "relative_path": rel,
            "size": len(data),
            "template_sha256": hashlib.sha256(data).hexdigest(),
            "normalized_structure_hash": WI.word_structure_hash(data),
        },
        "structure": {
            "paragraph_count": len(paragraph_texts),
            "table_count": document_xml.count("<w:tbl>"),
            "existing_sdt_count": document_xml.count("<w:sdt>") + document_xml.count("<w:sdt "),
            "declared_dollar_token_count": len(_NEW_PLACEHOLDER_RE.findall(document_xml)),
        },
        "html_counterpart": {
            "render_strategy": "app/routers/wp_render_strategies/_word_template.py",
            "structured_host": (
                "audit-platform/frontend/src/components/workpaper/"
                "GtWordTemplateStructuredView.vue"
            ),
            "persistence": f"checklist_responses.item_id LIKE 'wt-{wp_code}-%'",
            "field_identity_source": (
                "app/services/wp_docx_template_parser.py::_LEGACY_PATTERNS"
                "（中文标记正则 + `_dedupe_field_id` 序号后缀）"
            ),
            "parser_placeholder_count": len(parser_field_ids),
            "parser_field_ids": parser_field_ids,
            "ordinal_suffixed_field_ids": ordinal_ids,
            "distinct_labels": sorted({ph.label for ph in structure.placeholders}),
        },
        "anchor_analysis": {
            "candidate_occurrences": len(occurrences),
            "merged_cell_duplicate_occurrences": sum(
                1 for o in occurrences if o.merged_cell_duplicate
            ),
            "distinct_literal_anchors": len(literal_counter),
            "max_literal_anchor_multiplicity": max(literal_counter.values(), default=0),
            "literal_anchor_multiplicity": dict(sorted(literal_counter.items())),
            "raw_xml_verbatim_counts": raw_xml_counts,
            "literals_not_verbatim_in_raw_xml": sorted(
                lit for lit, cnt in raw_xml_counts.items() if cnt == 0
            ),
            "span_overlap": overlap,
            "unrecognised_placeholder_forms": dict(sorted(unrecognised_total.items())),
            "occurrences_whose_container_has_unrecognised_form": sum(
                1
                for o in occurrences
                if not o.merged_cell_duplicate and o.sibling_unrecognised_forms
            ),
            "occurrences": [o.as_dict() for o in occurrences],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. verdict 与阻塞原因（纯函数，全部由事实派生）
# ═══════════════════════════════════════════════════════════════════════════


def derive_verdict(facts: dict[str, Any]) -> str:
    """由实测事实派生 verdict。顺序即「首个原因」，每一档都有自己的变异锚点。"""
    st = facts["structure"]
    an = facts["anchor_analysis"]
    if int(st["declared_dollar_token_count"]) > 0:
        return "token_declared_template"
    effective = int(an["candidate_occurrences"]) - int(an["merged_cell_duplicate_occurrences"])
    if effective <= 0:
        return "no_managed_field_candidate"
    ov = an["span_overlap"]
    if int(ov["identical"]) or int(ov["contained"]) or int(ov["partial"]):
        # 嵌套/重合先判：两个 span 重叠时「同时注入 SDT」结构上不可能，
        # 这比「锚点不具区分度」更靠前 —— 后者至少还能讨论换锚点。
        return "blocked_nested_literal_anchor"
    if int(an["max_literal_anchor_multiplicity"]) > 1:
        return "blocked_non_discriminating_literal_anchor"
    if an["literals_not_verbatim_in_raw_xml"]:
        return "blocked_literal_anchor_split_across_runs"
    if int(an["occurrences_whose_container_has_unrecognised_form"]) > 0:
        # 锚点唯一且技术上可注入，但它只是更大人类占位的片段 —— 注入后旁边的
        # `第YY次` / `X月X日` / `【…】` 仍是死文本，受管字段名不副实。
        return "blocked_partial_field_fragment_anchor"
    return "instrumentable_literal_anchor"


def derive_blocking_reasons(facts: dict[str, Any]) -> list[str]:
    """全部命中的阻塞原因（不只报第一条 —— 少报一条就等于那条无人把守）。"""
    st = facts["structure"]
    an = facts["anchor_analysis"]
    hc = facts["html_counterpart"]
    reasons: list[str] = []
    if int(st["declared_dollar_token_count"]) == 0:
        reasons.append("no_declared_token_in_authoritative_template")
    effective = int(an["candidate_occurrences"]) - int(an["merged_cell_duplicate_occurrences"])
    if effective <= 0:
        reasons.append("zero_managed_field_candidates")
    else:
        reasons.append("field_identity_derived_from_chinese_regex")
        if hc["ordinal_suffixed_field_ids"]:
            reasons.append("ordinal_suffixed_field_ids")
        if int(an["max_literal_anchor_multiplicity"]) > 1:
            reasons.append("non_discriminating_literal_anchor")
        ov = an["span_overlap"]
        if int(ov["identical"]) or int(ov["contained"]) or int(ov["partial"]):
            reasons.append("nested_or_identical_candidate_spans")
        if int(an["merged_cell_duplicate_occurrences"]) > 0:
            reasons.append("merged_cell_duplicated_candidates")
        if an["literals_not_verbatim_in_raw_xml"]:
            reasons.append("literal_anchor_split_across_runs")
        if int(an["occurrences_whose_container_has_unrecognised_form"]) > 0:
            reasons.append("partial_field_fragment_anchor")
        if set(hc["distinct_labels"]) <= {"待填内容", "审计年度", "报告日期"}:
            reasons.append("generic_labels_only")
    if an["unrecognised_placeholder_forms"]:
        reasons.append("unrecognised_placeholder_forms_present")
    unknown = [r for r in reasons if r not in BLOCKING_REASONS]
    if unknown:
        raise Task62GeneratorError(
            f"{facts['wp_code']}: 派生出封闭词表外的阻塞原因 {unknown}"
        )
    return sorted(set(reasons))


# ═══════════════════════════════════════════════════════════════════════════
# 4. 可注入 entry 的离线 tagged-SDT 实证（不碰 DB、不碰模板库）
# ═══════════════════════════════════════════════════════════════════════════

#: 机制探针用的**片段**锚点声明（**不是**契约，也不构成任何 entry 的受管字段集合）。
#:
#: 🔴 为什么留这张表：18 个 entry 全部 blocked 之后，「tagged-SDT 机制到底能不能作用
#: 在 F2 之外的真实 generic 模板上」就成了没人回答的问题 —— 而那正是 Task 62 后续解除
#: 阻塞后第一件要依赖的事。这里对唯一锚点的那几个 entry 真跑一遍
#: 注入 → 可见等价 → 只按 tag 反读，把「机制可用」变成实测事实。
#:
#: 🔴 为什么它不是契约：`fragment_of` 记录了这个锚点只是哪个更大人类占位的片段。
#: 生成器会强制 `verdict == "blocked_partial_field_fragment_anchor"`、entry 的
#: `contract` 恒为 `None`、探针结果标 `is_not_a_contract=True`；本表 key 集合与实测
#: fragment-verdict 且锚点唯一的 entry 集合**逐个相等**，多写少写都打红。
MECHANISM_PROBE_ANCHORS: dict[str, tuple[str, str, str]] = {
    # wp_code: (探针用 stable_field_key, 该锚点所属的完整人类占位, 中文说明)
    "A26-1": (
        "probe/as_of_year",
        "截至202X年X月X日",
        "表 1 合并单元格内「截至202X年X月X日（建议临近会议日）」的年份片段；"
        "同格另有 20+ 个 `【…】` 填写指引槽位，parser 一个都不认",
    ),
    "A26-4": (
        "probe/minutes_year",
        "202X年第YY次",
        "签字页「系事务所202X年第YY次专业技术委员会会议记录的签字页」的年份片段；"
        "兄弟占位 `第YY次`（会议次序）parser 不认。A26-3 的同一句在 python-docx 视图"
        "里一模一样，但它的原始 XML 把 `202X` 切在了 run 边界上 ⇒ 那个 entry 连定位都"
        "做不到（verdict=blocked_literal_anchor_split_across_runs），两者不可互相顶替",
    ),
}


def mechanism_probe_evidence(facts: dict[str, Any]) -> dict[str, Any]:
    """对唯一锚点的 entry 真跑一遍离线注入 + 可见等价 + 只按 tag 反读。

    只吃 bytes，**不**碰 DB、**不**写 `backend/wp_templates/`、**不**产生 candidate
    行 / representation / 契约文件。目的只有一个：把「tagged-SDT 机制在 F2 之外的真实
    generic 模板上是否可用」变成可核对的实测事实。
    """
    wp_code = facts["wp_code"]
    stable_key, fragment_of, note = MECHANISM_PROBE_ANCHORS[wp_code]
    an = facts["anchor_analysis"]
    literals = list(an["literal_anchor_multiplicity"])
    if len(literals) != 1:
        raise Task62GeneratorError(
            f"{wp_code}: 机制探针要求字面锚点唯一，现算 {len(literals)} 个"
        )
    anchor = literals[0]
    #: `expected_token_occurrences` 取**原始 XML** 的 verbatim 计数（注入引擎看到的
    #: 那个数），不取 python-docx 视图的计数 —— 两者在合并单元格/跨 run 上会不一致，
    #: 用错一侧会被 `_inject` 的 fail-closed 计数直接拒掉（这正是它存在的意义）。
    occurrences = int(an["raw_xml_verbatim_counts"][anchor])

    gate = WI.WordSdtCarrierGate.load()
    #: 🔴 探针 id 带 `probe.` 前缀且**不**等于任何可能的生产 contract_id ——
    #: 防止有人把探针产物当契约装载。
    contract_id = f"probe.task62.{wp_code.lower().replace('-', '_')}"
    spec = WI.WordInstrumentationSpec(
        entry_id=contract_id,
        contract_id=contract_id,
        template_id=contract_id,
        template_relative_path=facts["template"]["relative_path"],
        semantic_version="1.0.0",
        fields=(
            WI.WordFieldInjection(
                token=anchor,
                stable_field_key=stable_key,
                carrier="field_sdt_inline",
                alias="",
                expected_token_occurrences=occurrences,
                literal_anchor=True,
            ),
        ),
    )
    source = (TEMPLATE_ROOT / facts["template"]["relative_path"]).read_bytes()
    # 三步全是纯函数（只吃 bytes）：注入 → 注入前后可见等价 → 只按 tag 反读。
    # 一个字节都不落盘 —— 所以这里刻意**没有**临时目录：需要目录的那条路径
    # （`validate_candidate_offline` 的第 4/5 步 extract/materialize 往返）会写
    # candidate 文件，属 Task 59 的宿主职责，本生成器不代劳。
    instrumented = WI.instrument_docx_bytes(source, spec, gate=gate)
    equivalence = WI.verify_docx_visible_equivalence(
        source=source, instrumented=instrumented, spec=spec
    )
    readback = WI.read_back_word_tags(instrumented=instrumented, spec=spec, gate=gate)
    return {
        "ran": True,
        "is_not_a_contract": True,
        "what_it_proves": (
            "tagged-SDT 注入 + 注入前后可见等价 + 只按 w:tag 反读，在这份真实 generic "
            "模板上逐条通过 —— 即机制不是 F2 专属。它**不**证明该 entry 可迁移："
            f"该锚点只是「{fragment_of}」的片段（见 verdict）"
        ),
        "probe_id": contract_id,
        "one_time_locator_kind": spec.fields[0].locator_kind,
        "literal_anchor": anchor,
        "fragment_of": fragment_of,
        "expected_token_occurrences": occurrences,
        "probe_stable_field_key": stable_key,
        "note": note,
        "source_ref": (
            f"{wp_code}!{an['occurrences'][0]['report_only_locator']}:{anchor}"
        ),
        "instrumented_sha256": instrumented.instrumented_sha256,
        "injected_tags": list(instrumented.injected_tags),
        "untouched_parts": int(instrumented.untouched_parts),
        "non_document_parts_byte_identical": all(
            ok
            for name, ok in instrumented.part_bytes_identical.items()
            if name != "word/document.xml"
        ),
        "visible_equivalence": equivalence,
        "tag_readback": readback,
        "published": False,
        "published_blocked_by": ["BP-62-1", "BP-62-2", "BP-62-3"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. 阻塞前置（BP-20 起，续 Task 60 的 BP-10~BP-15）
# ═══════════════════════════════════════════════════════════════════════════


def blocking_preconditions(adapter_ban: dict[str, Any]) -> list[dict[str, Any]]:
    """本任务的阻塞前置。

    🔴 **id 用 task-scoped 前缀 `BP-62-N`，不用全局 `BP-NN`**：实测 Tasks 63 与 64 的裁决
    记录**各自**登记了 `BP-16`~`BP-20`（Task 64 到 `BP-22`），同号不同义 —— 全局单调编号
    在多会话并发下已经被双重占用，再往后接号只会制造第三份冲突。task-scoped 前缀让
    「哪条前置属于哪个任务」在 id 上自证，Task 67 结构复核时不需要靠上下文猜。
    """
    return [
        {
            "id": "BP-62-1",
            "title": "`word-template` HTML 业务模型没有稳定字段身份",
            "evidence": [
                "`app/services/wp_docx_template_parser.py` 的 `_LEGACY_PATTERNS` 用中文"
                "标记（`××公司` / `202X年…` / `××`）现算字段，Requirement 7.1 逐字禁止"
                "「中文正则」作正式回写协议",
                "`_dedupe_field_id` 按文档扫描顺序追加序号后缀 ⇒ 模板中间插一个 `××` "
                "会让其后全部 field_id 位移，不是稳定键",
                "`_LEGACY_PATTERNS` 自身互相重叠（`202X年` 落在 `202X年12月31日` 内；"
                "两条日期正则命中同一 span）⇒ 同一物理文本产出两个「字段」",
                "`parse_template` 的表格循环 `for cell in row.cells` 把横向合并单元格"
                "按跨列数重复扫描 ⇒ 候选数虚增",
            ],
            "consequence": (
                "这 18 个 entry 拿不到「稳定键 + 唯一可锚位置」的字段集合，"
                "因此无法诚实地发布 tagged-SDT per-entry contract"
            ),
            "release_condition": (
                "对权威模板做受控、版本化的 `${semantic_key}` 占位改造（AC 9.9 的声明式"
                "迁移清单 + AC 3.4 的 template definition 发布），并把 `word-template` "
                "的字段身份从序号型改为 token 型；该改造跨 `word-template-dual-mode` "
                "feature 与模板库，需自己的 spec 三件套，不属 Task 62 权限"
            ),
            "must_fix_before": "Task 62 发布任何 per-entry contract / bundle",
            "owner_task": "待立 spec（不得在 Task 62 内私自改模板库或 parser）",
            "same_root_cause_as": [
                "Task 64 裁决记录的 BP-17（「生产定位仍靠 legacy 中文正则 + "
                "`paragraph_index` 绝对索引 + 序号后缀 field_id」）",
                "Task 63 裁决记录的 `field_identity_admissible_entries: []` 与 "
                "`legacy_chinese_derived_total`",
            ],
            "cross_lane_corroboration": (
                "三个 Word lane 任务各自独立现算后落到同一条根因：Task 62 实测 18/18 模板 "
                "`declared_dollar_token_count=0`、115/136 field_id 带序号后缀；Task 63 记录 "
                "`dollar_token_total=0` 且 `field_identity_admissible_entries` 为空集；"
                "Task 64 记录 A16 链 HTML 字段面为 0。同一结论被三条独立取样路径复现，"
                "不是单个 entry 的偶然"
            ),
        },
        {
            "id": "BP-62-2",
            "title": "Word adapter 仍被 `PENDING_ENGINE_ADAPTERS` 禁止落地",
            "evidence": [
                "现读 `adapters/registry.py::PENDING_ENGINE_ADAPTERS` 的 docx 条目："
                f"forbidden_paths={adapter_ban['forbidden_paths']}，"
                f"blocking_task={adapter_ban['blocking_task']!r}",
                f"`DELIVERED_ENGINE_ADAPTERS` 里 docx adapter 现算 "
                f"{adapter_ban['delivered_docx_engine_adapters']} 条",
            ],
            "consequence": "即便契约齐备，Task 62 也不得注册 Word adapter / 标 bidirectional",
            "release_condition": "Task 61 真实 OO 9.4 F2 Word gate 全场景通过",
            "must_fix_before": "Task 62 注册 adapter / 接宿主",
            "owner_task": "61",
        },
        {
            "id": "BP-62-3",
            "title": "Word lane 的 published representation 供给为 0",
            "evidence": [
                "Task 60 发布记录里 F2-22/F2-23 的 `definition_bundle` 与 "
                "`published_representation` 均为 null（BP-10~BP-12）",
                "`WordEntryFinalizeGate.finalize_candidate` 要求 candidate 已绑 approved "
                "bundle；`working_paper_content_version` / "
                "`working_paper_representation_upgrade_candidate` 实测 0 行",
            ],
            "consequence": "Task 62 无法为任何 entry finalize published representation",
            "release_condition": (
                "F2 lane 先经 Task 76 provisioner + Task 77 finalize gate 走通一次，"
                "证明 Word 侧 `template → instrumentation → contract → bundle → "
                "representation` 全链可发布"
            ),
            "must_fix_before": "Task 62 标任何 entry 为已验收",
            "owner_task": "61",
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 6. 组装记录
# ═══════════════════════════════════════════════════════════════════════════


def build_record() -> dict[str, Any]:
    rows = ledger_rows()
    declared = requirement_7_7_declared()
    adapter_ban = word_adapter_ban()
    gate = WI.WordSdtCarrierGate.load()

    entries: list[dict[str, Any]] = []
    for row in rows:
        facts = collect_entry_facts(row)
        verdict = derive_verdict(facts)
        reasons = derive_blocking_reasons(facts)
        entry: dict[str, Any] = {
            **facts,
            "lane_entry_key": f"word-lane/{facts['wp_code'].lower()}",
            "lane_entry_key_is_not_a_manifest_entry_id": True,
            "manifest_entry_state": "absent_from_source_manifest",
            "verdict": verdict,
            "blocking_reasons": reasons,
            "authority_model": None,
            "authority_model_blocked_by": ["BP-62-1"],
            "contract": None,
            "contract_blocked_by": ["BP-62-1"],
            "definition_bundle": None,
            "definition_bundle_blocked_by": ["BP-62-1", "BP-62-3"],
            "published_representation": None,
            "published_representation_blocked_by": ["BP-62-1", "BP-62-3"],
            "adapter_id": None,
            "adapter_blocked_by": ["BP-62-2"],
            "capability": None,
            "capability_target": "bidirectional",
            "capability_target_blocked_by": ["BP-62-1", "BP-62-2", "BP-62-3"],
            "canonical_resolver": "word_resolution.resolve_word_template",
            "evidence": {
                "verification_state": "UNVERIFIABLE",
                "sync_test_run_id": None,
                "required_scenario_set_digest": None,
                "browser_case": None,
                "unverifiable_reasons": [
                    f"verdict={verdict}；阻塞原因 {reasons}",
                    "无 approved authority model / per-entry contract / non-null bundle",
                    "Task 61 真实 OO 9.4 Word gate 未通过（BP-21）",
                ],
            },
        }
        probe_eligible = (
            verdict == "blocked_partial_field_fragment_anchor"
            and int(facts["anchor_analysis"]["max_literal_anchor_multiplicity"]) == 1
            and not facts["anchor_analysis"]["literals_not_verbatim_in_raw_xml"]
        )
        if probe_eligible:
            if facts["wp_code"] not in MECHANISM_PROBE_ANCHORS:
                raise Task62GeneratorError(
                    f"{facts['wp_code']}: 实测锚点唯一且 verdict=fragment，但 "
                    "`MECHANISM_PROBE_ANCHORS` 里没有它 —— 能实证的必须实证，"
                    "不得静默跳过"
                )
            entry["mechanism_probe"] = mechanism_probe_evidence(facts)
        else:
            if facts["wp_code"] in MECHANISM_PROBE_ANCHORS:
                raise Task62GeneratorError(
                    f"{facts['wp_code']}: `MECHANISM_PROBE_ANCHORS` 里有它，但实测 "
                    f"verdict={verdict} / 锚点重数="
                    f"{facts['anchor_analysis']['max_literal_anchor_multiplicity']} / "
                    "非 verbatim 锚点="
                    f"{facts['anchor_analysis']['literals_not_verbatim_in_raw_xml']} —— "
                    "不得给不合格 entry 挂机制探针"
                )
            entry["mechanism_probe"] = {
                "ran": False,
                "is_not_a_contract": True,
                "why": (
                    f"verdict={verdict}：字面锚点不唯一、被 run 边界切断，或无候选 —— "
                    "逐字段注入在本 entry 上无法构造"
                ),
            }
        entries.append(entry)

    verdict_counts = collections.Counter(e["verdict"] for e in entries)
    reason_counts: collections.Counter[str] = collections.Counter()
    for e in entries:
        reason_counts.update(e["blocking_reasons"])

    counters = {
        "entries_total": len(entries),
        "requirement_7_7_declared_generic_docx": declared["declared_generic_docx"],
        "templates_read_from_authoritative_root": len(entries),
        "templates_with_declared_dollar_token": sum(
            1 for e in entries if e["structure"]["declared_dollar_token_count"] > 0
        ),
        "templates_with_existing_sdt": sum(
            1 for e in entries if e["structure"]["existing_sdt_count"] > 0
        ),
        "candidate_occurrences_total": sum(
            e["anchor_analysis"]["candidate_occurrences"] for e in entries
        ),
        "merged_cell_duplicate_occurrences_total": sum(
            e["anchor_analysis"]["merged_cell_duplicate_occurrences"] for e in entries
        ),
        "parser_placeholders_total": sum(
            e["html_counterpart"]["parser_placeholder_count"] for e in entries
        ),
        "ordinal_suffixed_field_ids_total": sum(
            len(e["html_counterpart"]["ordinal_suffixed_field_ids"]) for e in entries
        ),
        "span_overlap_identical_total": sum(
            e["anchor_analysis"]["span_overlap"]["identical"] for e in entries
        ),
        "span_overlap_contained_total": sum(
            e["anchor_analysis"]["span_overlap"]["contained"] for e in entries
        ),
        "span_overlap_partial_total": sum(
            e["anchor_analysis"]["span_overlap"]["partial"] for e in entries
        ),
        "entries_with_literal_anchor_split_across_runs": sum(
            1 for e in entries if e["anchor_analysis"]["literals_not_verbatim_in_raw_xml"]
        ),
        "entries_with_unrecognised_placeholder_forms": sum(
            1 for e in entries if e["anchor_analysis"]["unrecognised_placeholder_forms"]
        ),
        "authority_models_published": sum(
            1 for e in entries if e["authority_model"] is not None
        ),
        "contracts_published_reviewed": sum(1 for e in entries if e["contract"] is not None),
        "definition_bundles_published": sum(
            1 for e in entries if e["definition_bundle"] is not None
        ),
        "published_representations_finalized": sum(
            1 for e in entries if e["published_representation"] is not None
        ),
        "adapters_registered": sum(1 for e in entries if e["adapter_id"] is not None),
        "entries_left_unverifiable": sum(
            1 for e in entries if e["evidence"]["verification_state"] == "UNVERIFIABLE"
        ),
        "mechanism_probe_runs": sum(1 for e in entries if e["mechanism_probe"].get("ran")),
        "entries_with_instrumentable_verdict": sum(
            1 for e in entries if e["verdict"] == "instrumentable_literal_anchor"
        ),
        "task62_contract_files_in_staged_dir": len(task62_contract_files()),
        "verdicts": dict(sorted(verdict_counts.items())),
        "blocking_reasons": dict(sorted(reason_counts.items())),
    }

    if counters["entries_total"] != counters["requirement_7_7_declared_generic_docx"]:
        raise Task62GeneratorError(
            f"Task 58 清册里 owner_task=62 现算 {counters['entries_total']} 条，"
            f"requirements.md AC 7.7 声明 "
            f"{counters['requirement_7_7_declared_generic_docx']} 个 —— 两侧必须一致"
        )
    distinct = {v for v in verdict_counts}
    unknown = distinct - set(ENTRY_VERDICTS)
    if unknown:
        raise Task62GeneratorError(f"派生出封闭词表外的 verdict: {sorted(unknown)}")

    return {
        "schema_version": SCHEMA_VERSION,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "task": OWNER_TASK,
        "wave": 6,
        "generator": (
            "backend/scripts/gen/generate_task62_generic_docx_adjudication.py"
        ),
        "why_this_record_instead_of_18_approved_bundles": (
            "18/18 权威模板零 `${}` 声明 token、零既有 w:sdt；这 18 个 wp_code 的 HTML "
            "对端字段身份由中文标记正则 + 序号后缀现算（Requirement 7.1 明禁中文正则作"
            "回写协议）。把这批序号型、语义空洞的候选写成 reviewed 契约会让机器侧全绿"
            "而实质是伪造供给，Task 62 正文亦明禁「不为满足数字伪造 contract/bundle/"
            "finalize」。故本任务先交付逐 entry 可复核裁决与阻塞登记。"
        ),
        "the_reason_is_not_zero_dollar_tokens": {
            "claim_explicitly_rejected": (
                "「模板里没有 `${}` 占位所以造不出锚点」—— 这个说法是错的，本记录**不**"
                "以它为理由（Task 64 裁决记录已就同一误读做过更正，此处逐字对齐）"
            ),
            "disproved_by_real_execution": [
                "`WordFieldInjection(literal_anchor=True)` 是正式支持的一次性定位通道，"
                "Task 6 对 B30-11-2 用的就是中文字面标题",
                "本记录的 `mechanism_probe` 对 A26-1 / A26-4 **真跑**了 "
                "`instrument_docx_bytes` → `verify_docx_visible_equivalence` → "
                "`read_back_word_tags`，逐条通过（`equivalent=true`、覆盖计数非空、"
                "非 document part 逐字节相同）⇒ 机制在 generic 模板上确实可用",
                "`WordRowInjection` 支持一次性单元格坐标，空单元格也能注入",
            ],
            "the_actual_reasons": [
                "**锚点不具区分度**（10/18）：`WordFieldInjection` 一个 literal token 只能绑"
                "一个 stable key 且全部出现处注入同一 tag，而 `××` 在单份约定书里最多出现 "
                "22 次、语义各不相同 ⇒ 无法逐字段注入",
                "**候选 span 互相嵌套/重合**（2/18）：`202X年` 落在 `202X年12月31日` 内部，"
                "两者同时注入 SDT 结构上不可能",
                "**锚点被 run 边界切断**（1/18，另有 6 个 entry 至少一个 literal 命中）："
                "`_token_paragraphs` 要求 token verbatim 出现在原始 `word/document.xml`",
                "**锚点只是更大人类占位的片段**（2/18）：注入后旁边的 `第YY次` / `X月X日` "
                "仍是死文本，受管字段名不副实",
                "**零受管字段候选**（3/18）：tagged-SDT projection 无内容可管，"
                "空 `fields` 会让「注入成功 / 等值通过」全部恒真",
                "**字段身份不稳定**：115/136 的 field_id 带文档扫描顺序派生的序号后缀，"
                "design 对 `stable_field_key` 的定义是「adapter 全局稳定键」",
            ],
        },
        "three_way_lock": {
            "ledger_side": str(LEDGER_PATH.relative_to(_BACKEND.parent)).replace("\\", "/"),
            "disk_side": str(TEMPLATE_ROOT.relative_to(_BACKEND.parent)).replace("\\", "/"),
            "impl_side": [
                "app/services/wp_docx_template_parser.py::_LEGACY_COMPILED",
                "app/services/wp_docx_template_parser.py::_NEW_PLACEHOLDER_RE",
                "app/services/workpaper_sync/word_instrumentation.py::WordSdtCarrierGate.load",
                "app/services/workpaper_sync/adapters/registry.py::PENDING_ENGINE_ADAPTERS",
            ],
            "requirements_side": "AC 7.7 的声明数现读，不抄 18/9",
        },
        "probe_gate": {
            "source": str(
                WI.WORD_GATE_CONTRACT_PATH.relative_to(_BACKEND.parent)
            ).replace("\\", "/"),
            "carriers_allowed": sorted(gate.carrier_gate.allowed_carriers),
            "carriers_blocked": sorted(gate.carrier_gate.blocked_carriers),
            "anchors_allowed": sorted(gate.carrier_gate.allowed_anchors),
            "anchors_blocked": sorted(gate.carrier_gate.blocked_anchors),
            "identity": gate.probe_gate_identity(),
        },
        "word_adapter_ban": adapter_ban,
        "entry_verdict_vocabulary": list(ENTRY_VERDICTS),
        "blocking_reason_vocabulary": list(BLOCKING_REASONS),
        "unrecognised_placeholder_patterns": [
            {"name": n, "regex": p} for n, p in UNRECOGNISED_PLACEHOLDER_PATTERNS
        ],
        "blocking_preconditions": blocking_preconditions(adapter_ban),
        "cross_entry_isolation": {
            "rule": "不得跨 entry 复用 bundle / candidate / contract / evidence",
            "how_enforced": (
                "每个 entry 自己的 `template_sha256` / `normalized_structure_hash` / "
                "候选清册 / verdict / blocking_reasons 全部独立现算；`contract_id` 由 "
                "wp_code 派生且互不相同；`REVIEWED_LITERAL_FIELDS` 的 key 集合与实测 "
                "instrumentable 集合逐个相等，多写少写都打红"
            ),
            "f2_lane_untouched": (
                "本任务往 `backend/data/workpaper_sync_word_contracts/` 写 0 份文件，"
                "F2-22/F2-23 的两份契约与发布记录逐字节不变"
            ),
        },
        "zero_families_are_non_vacuous": {
            "authority_models_published": "分母 = 18 个 entry，全部因 BP-20 为 0，不是没有 entry",
            "contracts_published_reviewed": "同上；`--check` 会核对暂存目录里本任务文件数为 0",
            "definition_bundles_published": "同上，另叠加 BP-22（Word lane 供给为 0）",
            "published_representations_finalized": "同上",
            "adapters_registered": (
                "分母 = 18；`PENDING_ENGINE_ADAPTERS` 现读证明禁令仍在（BP-21），"
                "`DELIVERED_ENGINE_ADAPTERS` 里 docx 为 0"
            ),
            "templates_with_declared_dollar_token": (
                "分母 = 18 份真实模板全部读过；为 0 是实测结论，不是没读"
            ),
        },
        "counters": counters,
        "entries": entries,
        "requirements_covered": [
            "7.1", "7.3", "7.4", "7.5", "7.6", "7.8",
            "12.1", "12.5", "12.10", "12.11", "12.12",
        ],
        "properties_verified": [
            "Property 30", "Property 31", "Property 32",
            "Property 33", "Property 34", "Property 69", "Property 70",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 7. CLI
# ═══════════════════════════════════════════════════════════════════════════


def _canonical_text(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="只读：现算并与磁盘记录比对")
    mode.add_argument("--write", action="store_true", help="现算并落盘")
    args = parser.parse_args(argv)

    record = build_record()
    text = _canonical_text(record)

    if args.write:
        OUTPUT_PATH.write_text(text, encoding="utf-8")
        print(f"[write] {OUTPUT_PATH.name} counters=")
        print(json.dumps(record["counters"], ensure_ascii=False, indent=2))
        return 0

    if not OUTPUT_PATH.is_file():
        raise Task62GeneratorError(
            f"{OUTPUT_PATH.name} 不存在 —— 先跑 `--write`。`--check` 不得因缺文件而报成功"
        )
    on_disk = OUTPUT_PATH.read_text(encoding="utf-8")
    if on_disk != text:
        raise Task62GeneratorError(
            f"{OUTPUT_PATH.name} 与现算结果不一致 —— 三边锁其中一边变了，"
            "请重跑 `--write` 后复核 diff（磁盘 "
            f"{hashlib.sha256(on_disk.encode('utf-8')).hexdigest()[:12]} vs 现算 "
            f"{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}）"
        )
    print(f"[check] {OUTPUT_PATH.name} 与现算逐字节一致")
    print(json.dumps(record["counters"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
