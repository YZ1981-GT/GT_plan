# -*- coding: utf-8 -*-
r"""Task 64 生成器 —— A16/A17 专用 Word 链与 Word editor 宿主的 source-backed 裁决记录。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 64
Requirements: 7.1 · 7.3 · 11.4 · 11.5 · 11.12 · 12.1 · 12.5 · 12.10 · 12.11 · 12.12
Properties: 30 · 31 · 47 · 69 · 70

产物（一个，可由本脚本从**权威 docx 字节 + 前端源码 + 生产解析器**重算）::

    backend/data/workpaper_sync_a16_a17_word_chain_adjudication.json

用法（仓库根；PATH 上的 `python` 指向坏掉的 `.venv_depprobe`，报 `No pyvenv.cfg`）::

    .\.venv\Scripts\python.exe backend/scripts/gen/generate_task64_dedicated_word_chain.py --check
    .\.venv\Scripts\python.exe backend/scripts/gen/generate_task64_dedicated_word_chain.py --write

`--check` 只比对不落盘（幂等判据）；`--write` 覆盖产物。

═══ 为什么本任务**不**发布 per-entry tagged-SDT 契约 ═══

Task 64 正文要求「为每个**保留的** entry ... 发布 approved authority model、tagged-SDT
per-entry contract 与 non-null bundle」。逐 entry 现算后，四条 docx entry 里**没有一条**
满足「保留 + projection 有对端」这两个前提，故本任务的交付是**裁决 + 如实登记**，与
Task 63 正文「无合法模板/HTML 对端则裁决 single/missing，不为满足数字伪造
contract/bundle/finalize」同一处置原则。

🔴 理由**不是**「造不出锚点」—— 那个说法是错的，本脚本用 impl 真跑证伪了它：
`WordFieldInjection` 支持 `literal_anchor=True`（字面文本作**一次性**迁移线索，由
`expected_token_occurrences` fail-closed 锁死命中数；Task 6 对 B30-11-2 的注入用的就是
字面标题），`WordRowInjection` 支持 `(table_index,row_index,cell_index)` 一次性坐标，
而本任务名下 15 个模板 **15/15 都有 `w:tbl`**、空单元格多达 312 个（A16-7）。技术上完全
可以注入。

真正的理由是**投影没有对端**：`projection_contract` 的语义是「HTML 结构化数据是权威、
docx 是它的投影」。A16 侧反过来 —— 生产 HTML 侧字段面**实测为 0**（`_word_template.py`
→ `wp_docx_template_parser.parse_template` 对 A16-1..A16-7 全部返回 0 个 placeholder，
`wt-{wp_code}-` 前缀下无任何字段），审计师是在 Word 里写整篇声明书。给一个没有消费方的
投影建 SDT 与契约，正是本 spec 反复实测过的**假绿第①源**（additive 注入即死代码）。
而 `registry.assert_authority_model_contract_pairing`（RG-8/RG-9）对非 projection 的
authority model **传入 SyncContract 即抛** `AuthorityModelMismatchError` —— 也就是说
「裁 opaque 却发 contract」在 impl 层就是矛盾，不是风格选择。

═══ 三边锁（每条裁决都过三条边）═══

1. **声明** —— 本脚本的 `ENTRY_DECLS` / `A16_SUBCODES` / `A17_SUBCODES` 表；
2. **磁盘真读** —— `zipfile` 直读权威 docx 的 `word/document.xml`（段落/`w:tbl`/`w:tr`/
   既有 `w:sdt`/`${token}`）、前端 `.vue` 现扫（mount 门控链 + 静态 TABS 词表 +
   popup config 顶层 key）、Task 58 裁决清册与 entry manifest 现读；
3. **impl 常量/行为现读** —— 生产解析器 `wp_docx_template_parser.parse_template`、
   Task 58 `word_resolution.resolve_word_template`、Task 6 门
   `word_instrumentation.WordSdtCarrierGate.load()`、Task 13 交付登记表
   `registry.DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES`，以及四条
   **真跑**的 impl 反证（见 `_impl_probes`）。

═══ 不做什么 ═══

* 不建 `adapters/word.py` —— `registry.PENDING_ENGINE_ADAPTERS.forbidden_paths` 明禁，
  门是 Task 61（`[-]` UNVERIFIABLE）；
* 不往 `DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` 加行；
* 不改 entry manifest（重新生成是 Task 67 的 structural pre-reconcile）；
* 不改 `backend/wp_templates/` 一个字节（Task 59 第 4 步「源文件只读」）；
* 不改任何生产代码 —— 本任务只产一份裁决记录 + 守卫 + 变异脚本。
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

# ════════════════════════════════════════════════════════════════════════════
# 路径常量
# ════════════════════════════════════════════════════════════════════════════
DATA = _BACKEND / "data"
TEMPLATE_ROOT = _BACKEND / "wp_templates"
A_DIR = TEMPLATE_ROOT / "A"
ADJUDICATION_PATH = DATA / "workpaper_sync_a16_a17_word_chain_adjudication.json"
LEDGER_PATH = DATA / "workpaper_word_template_adjudication.json"
ENTRY_MANIFEST = DATA / "workpaper_sync_entry_manifest.json"
CARRIER_CONTRACT = DATA / "onlyoffice_word_sdt_carrier_contract.json"
F2_PUBLICATION = DATA / "workpaper_sync_f2_word_lane_publication.json"

_FRONTEND = _REPO / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = _FRONTEND / "components" / "workpaper"
A16_BUNDLE_VUE = WP_COMPONENTS / "GtA16Bundle.vue"
A17_BUNDLE_VUE = WP_COMPONENTS / "GtA17Bundle.vue"
WORD_EDITOR_VUE = WP_COMPONENTS / "WorkpaperWordEditor.vue"
OO_WORD_DIALOG_VUE = WP_COMPONENTS / "OnlyOfficeWordDialog.vue"
POPUP_DOCX_EDITOR_VUE = WP_COMPONENTS / "WpPopupDocxEditor.vue"
POPUP_CONFIG_FILES: tuple[tuple[Path, str], ...] = (
    (WP_COMPONENTS / "wpPopupDocxConfigs.ts", "DOCX_POPUP_CONFIGS"),
    (WP_COMPONENTS / "wpPopupDocxConfigsB.ts", "B_DOCX_POPUP_CONFIGS"),
    (WP_COMPONENTS / "wpPopupDocxConfigsS.ts", "S_DOCX_POPUP_CONFIGS"),
)
WORD_TEMPLATE_STRATEGY = (
    _BACKEND / "app" / "routers" / "wp_render_strategies" / "_word_template.py"
)
DOCX_PARSER = _BACKEND / "app" / "services" / "wp_docx_template_parser.py"

SCHEMA_VERSION = "a16-a17-word-chain-adjudication:v1"
WORD_DOC_PART = "word/document.xml"


# ════════════════════════════════════════════════════════════════════════════
# 第一边：声明表
# ════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class EntryDecl:
    """一条 docx entry 的裁决声明。

    `verdict` 只能取下面四值之一（封闭词表 —— 自由文本会让守卫只能比整句字符串）：

    * `opaque_ooxml_authority` —— docx 本体是业务权威，HTML 侧无字段对端；
    * `unreachable_stub` —— 宿主里的挂载点被静态门控恒假，运行时永不渲染；
    * `parent_duplicate_follows_parent` —— 非独立 entry，跟随其父 entry 裁决；
    * `shared_room_opaque_multiplexer` —— 一个宿主复用给 N 个 wp_code 的 opaque 弹窗。
    """

    entry_id: str
    host_vue: Path
    verdict: str
    authority_model: str | None
    why: str
    blocked_by: tuple[str, ...]


VERDICTS: tuple[str, ...] = (
    "opaque_ooxml_authority",
    "unreachable_stub",
    "parent_duplicate_follows_parent",
    "shared_room_opaque_multiplexer",
)

#: A16 bundle 的静态 TABS 承载的 7 个子码（现扫校验，不作为真源信任）。
A16_SUBCODES: tuple[str, ...] = tuple(f"A16-{i}" for i in range(1, 8))

#: A17 bundle 的静态 TABS 里带 wpCode 的 9 项（含裁决清册无行的 `A17-5`）。
A17_TAB_WPCODES: tuple[str, ...] = (
    "A17-1", "A17-2-1", "A17-3", "A17-3-1", "A17-4", "A17-5", "A17-6", "A17-7", "A17-7A",
)

ENTRY_DECLS: tuple[EntryDecl, ...] = (
    EntryDecl(
        entry_id="docx/gt-a16-bundle",
        host_vue=A16_BUNDLE_VUE,
        verdict="opaque_ooxml_authority",
        authority_model="opaque_single_onlyoffice",
        why=(
            "宿主 mount 真实可达（`el-tab-pane` v-for over visibleTabs，无外层 kind 门控），"
            "承载 A16-1..A16-7 七个 wp_code 的真实 DOCX。但生产 HTML 侧字段面实测为 0："
            "`_word_template.py` 经 `wp_docx_template_parser.parse_template` 对七份模板"
            "全部返回 0 个 placeholder ⇒ `wt-{wp_code}-` 前缀下无任何字段可投影。"
            "审计师是在 Word 里写整篇管理层声明书（`isA16Mode` 走 OO 弹窗，不走结构化视图）"
            "⇒ docx 本体即业务权威，authority model 只能是 opaque，不得发 SyncContract"
            "（RG-8/RG-9 对非 projection 传 contract 直接抛 AuthorityModelMismatchError）。"
        ),
        blocked_by=("BP-16", "BP-19", "BP-20"),
    ),
    EntryDecl(
        entry_id="docx/gt-a17-bundle",
        host_vue=A17_BUNDLE_VUE,
        verdict="unreachable_stub",
        authority_model=None,
        why=(
            "`WorkpaperWordEditor` 挂载点的**外层**门控是 `v-else-if=\"tab.kind === 'word'\"`，"
            "而静态 TABS 十条里没有一条 `kind: 'word'`（`word` 只出现在 TabDef 的类型联合"
            "声明里，从未被任何 tab 使用）⇒ 该分支运行时恒假、mount 永不渲染。"
            "A17 的每个子码都有自己的专属 HTML 组件与渲染策略（a171-/a1721-/a173-/a1731-/"
            "a174-/a176-/a177- 七套 item_id 字段集），没有任何子码需要走通用 Word 编辑器。"
            "按 Requirement 1.7 裁决 unreachable：不可达旧桩应删除，不得注册 adapter、"
            "不得发契约。删除归 Task 66 计划 + Task 72 Stage B 执行。"
        ),
        blocked_by=("BP-17", "BP-18"),
    ),
    EntryDecl(
        entry_id="docx/workpaper-word-editor",
        host_vue=WORD_EDITOR_VUE,
        verdict="parent_duplicate_follows_parent",
        authority_model=None,
        why=(
            "manifest 实测 `independent_entry=false` / "
            "`parent_entry_id=docx/gt-a16-bundle` ⇒ `registry.build_manifest_registration_plan` "
            "已有 blocked 分支「parent 重复入口 —— 只能复用其独立 entry 的 adapter」"
            "（Requirement 1.6 / 12.4）。它承载的 `OnlyOfficeWordDialog` 是 A16 弹窗的实现子件，"
            "裁决跟随父 entry（opaque），本任务不为它单独发 contract/bundle/scenario。"
            "🔴 但它的 inbound 实测 5 个（A10/A12/A16/A17 bundle + registry 派发），跨 "
            "Task 62/64 归属 ⇒ 「父裁决单一来源」在它身上不成立，登记 BP-19。"
        ),
        blocked_by=("BP-19",),
    ),
    EntryDecl(
        entry_id="docx/wp-popup-docx-editor",
        host_vue=POPUP_DOCX_EDITOR_VUE,
        verdict="shared_room_opaque_multiplexer",
        authority_model="opaque_single_onlyoffice",
        why=(
            "唯一 `room_model=shared` 的 docx entry，且是**一个宿主复用给 N 个 wp_code** 的"
            "弹窗多路复用器：popup 配置真源（三个 `wpPopupDocxConfigs*.ts` 的顶层 key）现算 "
            "98 条，按 Task 58 清册 owner_task 分桶跨 Task 62/63/64 三家。"
            "SyncContract 的 `template` 是**单个** TemplateRef，而 "
            "`load_projection_supply` 要求「一个独立 entry 唯一 per-entry 契约」⇒ 一条 entry "
            "对 98 个模板在契约模型里无法表达。这些 docx 又各自是本体权威（弹窗直接编辑整份"
            "文档，无 HTML 字段对端）⇒ 裁 opaque。契约模型的表达力缺口登记 BP-21。"
        ),
        blocked_by=("BP-20", "BP-21"),
    ),
)


# ════════════════════════════════════════════════════════════════════════════
# 第二边：磁盘真读
# ════════════════════════════════════════════════════════════════════════════
def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _docx_facts(path: Path) -> dict[str, Any]:
    """zip 级现算权威 docx 的结构事实（不经 python-docx，避免它归一化掉原始形态）。"""
    raw = path.read_bytes()
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        xml = zf.read(WORD_DOC_PART).decode("utf-8", errors="replace")
    stripped = re.sub(r"<[^>]+>", "", xml)
    return {
        "size_bytes": len(raw),
        "template_sha256": _sha256_bytes(raw),
        "paragraph_count": xml.count("<w:p>") + xml.count("<w:p "),
        "w_tbl_count": xml.count("<w:tbl>"),
        "w_tr_count": xml.count("<w:tr>") + xml.count("<w:tr "),
        "existing_w_sdt_count": xml.count("<w:sdt>"),
        "existing_w_tag_count": xml.count("<w:tag "),
        "dollar_tokens": sorted(set(re.findall(r"\$\{([A-Za-z0-9_]+)\}", stripped))),
        "part_count": len(names),
        "has_comments_part": "word/comments.xml" in names,
        "has_media": any(n.startswith("word/media/") for n in names),
    }


def _mount_gate_chain(text: str, component: str) -> list[dict[str, Any]]:
    """每个 `<Component` 挂载点 + 它**外层**最近的静态门控。

    🔴 判「mount 是否可达」必须看外层门控链：entry manifest 的 `mounts[].condition`
    只记了挂载标签自己的 `v-if`，外层 `<template v-else-if="...">` 整条缺失，于是
    「门控恒假的死代码」在 manifest 上看不出来（本任务实测到的 `docx/gt-a17-bundle`
    正是这个形态）。三要素缺一即不可达：遍历 + 外层门控 + 内层嵌套。
    """
    lines = text.splitlines()
    out: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        if f"<{component}" not in line:
            continue
        gate: str | None = None
        gate_line: int | None = None
        for back in range(idx - 1, max(-1, idx - 200), -1):
            probe = lines[back]
            m = re.search(r"<template\s+v-(else-if|if)=\"([^\"]+)\"", probe)
            if m:
                gate, gate_line = f'v-{m.group(1)}="{m.group(2)}"', back + 1
                break
            if "<el-tab-pane" in probe:
                gate, gate_line = "el-tab-pane v-for over visibleTabs", back + 1
                break
        window = "\n".join(lines[idx : idx + 8])
        inner = re.search(r'v-if="([^"]+)"', window)
        out.append(
            {
                "component": component,
                "mount_line": idx + 1,
                "outer_gate": gate,
                "outer_gate_line": gate_line,
                "inner_condition": inner.group(0) if inner else None,
            }
        )
    return out


def _a17_tab_kind_vocabulary() -> dict[str, Any]:
    """A17 bundle 的静态 TABS 词表 vs TabDef 类型联合 —— 死分支的判据。"""
    text = _read_text(A17_BUNDLE_VUE)
    used = sorted(set(re.findall(r"kind:\s*'([^']+)'", text)))
    union_block = re.findall(r"kind:\s*((?:'[^']+'\s*\|\s*)+'[^']+')", text)
    declared = sorted(set(re.findall(r"'([^']+)'", union_block[0]))) if union_block else []
    return {
        "kinds_used_in_TABS": used,
        "kind_type_union_declared": declared,
        "kinds_declared_but_never_used": sorted(set(declared) - set(used)),
        "tab_wp_codes": re.findall(r"wpCode:\s*'([^']+)'", text),
    }


def _a16_tab_wp_codes() -> list[str]:
    return re.findall(r"wpCode:\s*'([^']+)'", _read_text(A16_BUNDLE_VUE))


def _popup_config_rows() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """三个 popup 配置文件的**顶层 key**（= wp_code）与 templatePath，附各文件 digest。

    🔴 真源是顶层 key，**不是** `relatedLinks[].wpCode` —— 后者是跳转链接，抓它会把
    分母算成另一个集合（本任务首版探针踩过）。顶层 key 的判据是「行首恰两个空格 +
    引号」，嵌套对象的键缩进更深。

    🔴 这三个文件是**并发在改的活文件**：本任务实测过一次漂移 ——
    `wpPopupDocxConfigsS.ts` 的 `S33-REV` 配置在两次现算之间被删掉（3 个 key → 2 个），
    那正是 Task 63 正文点名处理的 `S33-REV`。故本函数同时返回逐文件 sha256，让
    「全量 popup 计数」成为**带 digest 的观测值**而不是被锁死的基线：digest 变了应当
    重跑 `--write` 并复核 diff，而不是把并发方的正常推进判成本任务打红。
    Task 64 的**稳定**分母是 `popup_owned_by_task_64`（A16/A17 侧），它不随 B/S 漂移。
    """
    rows: list[dict[str, Any]] = []
    digests: dict[str, str] = {}
    for path, const_name in POPUP_CONFIG_FILES:
        raw = path.read_bytes()
        digests[path.name] = _sha256_bytes(raw)
        text = raw.decode("utf-8")
        start = text.find(const_name)
        if start < 0:
            raise SystemExit(f"popup 配置常量未找到: {const_name} in {path}")
        body = text[start:]
        for m in re.finditer(r"^  '([^']+)':\s*\{", body, re.M):
            tail = body[m.end() : m.end() + 4000]
            tm = re.search(r"templatePath:\s*'([^']+)'", tail)
            rel = (tm.group(1) if tm else "").replace("wp_templates/", "", 1)
            rows.append(
                {
                    "wp_code": m.group(1),
                    "source_file": path.name,
                    "template_relative_path": rel or None,
                    "template_exists": bool(rel) and (TEMPLATE_ROOT / rel).is_file(),
                }
            )
    return rows, digests


def _ledger_rows_owned_by_64() -> list[dict[str, Any]]:
    ledger = json.loads(_read_text(LEDGER_PATH))
    return [r for r in ledger["rows"] if str(r.get("owner_task")) == "64"]


def _manifest_docx_entries() -> dict[str, dict[str, Any]]:
    manifest = json.loads(_read_text(ENTRY_MANIFEST))
    out: dict[str, dict[str, Any]] = {}
    for e in manifest["entries"]:
        if e.get("document_type") != "docx":
            continue
        out[e["entry_id"]] = {
            "host_path": e.get("host_path"),
            "capability": e.get("capability"),
            "room_model": e.get("room_model"),
            "editability": e.get("editability"),
            "independent_entry": e.get("independent_entry"),
            "parent_entry_id": e.get("parent_entry_id"),
            "adapter_id": e.get("adapter_id"),
            "canonical_resolver": e.get("canonical_resolver"),
            "migration_state": e.get("migration_state"),
            "wp_code_patterns": e.get("wp_match", {}).get("wp_code_patterns"),
            "scenario_profile_id": e.get("scenario_profile", {}).get("profile_id"),
            "doc_key_defects": e.get("scenario_profile", {}).get("doc_key_defects"),
            "mount_conditions": [m.get("condition") for m in e.get("mounts", [])],
            "evidence_contract_test": e.get("evidence", {}).get("contract_test"),
            "evidence_browser_case": e.get("evidence", {}).get("browser_case"),
        }
    return out


# ════════════════════════════════════════════════════════════════════════════
# 第三边：impl 常量与行为现读（真跑，不抄常量）
# ════════════════════════════════════════════════════════════════════════════
def _html_projection_surface() -> dict[str, Any]:
    """生产 HTML 侧字段面 —— 委派生产解析器现算，不重写一份解析。

    判「投影有没有对端」只能执行生产那份：重写一份的后果不是「更安全」，而是两侧
    任一被短路都不改变行为 ⇒ 变异检验判 GREEN。
    """
    from app.services.wp_docx_template_parser import parse_template

    ledger = {r["wp_code"]: r for r in _ledger_rows_owned_by_64()}
    out: dict[str, Any] = {}
    for code in sorted(r for r in ledger if ledger[r].get("unified_relative_path")):
        rel = ledger[code]["unified_relative_path"]
        st = parse_template(str(TEMPLATE_ROOT / rel))
        by_kind: dict[str, int] = {}
        positions: dict[str, int] = {}
        ordinal_suffixed = 0
        for p in st.placeholders:
            kind = (
                "new_dollar_token"
                if p.pattern.startswith("${")
                else "legacy_cjk_marker"
            )
            by_kind[kind] = by_kind.get(kind, 0) + 1
            pos = "paragraph_index" if "paragraph_index" in p.position else "table_cell"
            positions[pos] = positions.get(pos, 0) + 1
            if p.field_id[-1].isdigit() and "_" in p.field_id:
                ordinal_suffixed += 1
        out[code] = {
            "html_store_prefix": f"wt-{code}-",
            "placeholder_count": len(st.placeholders),
            "by_pattern_kind": by_kind,
            "by_position_kind": positions,
            "ordinal_suffixed_field_ids": ordinal_suffixed,
            "parsed_paragraph_count": len(st.paragraphs),
            "parsed_table_count": len(st.tables),
        }
    return out


def _impl_probes() -> dict[str, Any]:
    """四条**真跑**的 impl 反证。每条都记异常类型，不记「我认为会抛」。"""
    from app.services.workpaper_sync.word_instrumentation import (
        WordFieldInjection,
        WordInstrumentationError,
        WordInstrumentationSpec,
        WordSdtCarrierGate,
        WordTokenAnchorError,
        instrument_docx_bytes,
    )
    from app.services.workpaper_sync.word_resolution import resolve_word_template

    probes: dict[str, Any] = {}

    # ① A16 本体只有 XLSX ⇒ 统一 resolver 必抛 DocumentTypeMismatchError。
    for parent in ("A16", "A17"):
        try:
            resolve_word_template(parent)
            probes[f"{parent}_parent_resolve"] = {
                "outcome": "UNEXPECTED_SUCCESS",
                "note": "父码解析到了 DOCX —— 与 Task 58 清册的 document_type_mismatch 矛盾",
            }
        except Exception as exc:  # noqa: BLE001 - 反证要记真实类型
            probes[f"{parent}_parent_resolve"] = {
                "outcome": "rejected",
                "error_type": type(exc).__name__,
                "error_code": getattr(exc, "error_code", None),
            }

    # ② 子码解析到自己的 DOCX（证明 resolver 不是整条链都拒）。
    resolved = resolve_word_template("A16-1")
    probes["A16_1_child_resolve"] = {
        "outcome": "resolved",
        "relative_path": resolved.relative_to(TEMPLATE_ROOT).as_posix(),
    }

    # ③ 空 instrumentation 声明恒被拒（空集恒等价 ⇒ 「注入成功」会恒真）。
    try:
        WordInstrumentationSpec(
            entry_id="probe/a16-empty",
            contract_id="probe.a16.empty",
            template_id="probe-a16",
            template_relative_path="A/A16-1 管理层声明书-财务报表审计（企业会计准则）.docx",
        )
        probes["empty_spec_rejected"] = {"outcome": "UNEXPECTED_SUCCESS"}
    except WordInstrumentationError as exc:
        probes["empty_spec_rejected"] = {
            "outcome": "rejected",
            "error_type": type(exc).__name__,
        }

    # ④ 声明一个模板里不存在的 token ⇒ 注入按命中数 fail closed（不按段落序号挑）。
    gate = WordSdtCarrierGate.load()
    source = (A_DIR / "A16-1 管理层声明书-财务报表审计（企业会计准则）.docx").read_bytes()
    spec = WordInstrumentationSpec(
        entry_id="probe/a16-phantom",
        contract_id="probe.a16.phantom",
        template_id="probe-a16",
        template_relative_path="A/A16-1 管理层声明书-财务报表审计（企业会计准则）.docx",
        fields=(
            WordFieldInjection(
                token="${entityName}",
                stable_field_key="probe/entity_name",
                alias="被审计单位",
            ),
        ),
    )
    try:
        instrument_docx_bytes(source, spec, gate=gate)
        probes["phantom_token_rejected"] = {"outcome": "UNEXPECTED_SUCCESS"}
    except WordTokenAnchorError as exc:
        probes["phantom_token_rejected"] = {
            "outcome": "rejected",
            "error_type": type(exc).__name__,
            "mentions_hit_count_zero": "命中 0 个段落" in str(exc),
        }

    # ⑤ literal_anchor 形态**可**构造 —— 证伪「造不出锚点」这个说法。
    literal = WordFieldInjection(
        token="致：致同会计师事务所（特殊普通合伙）",
        stable_field_key="probe/addressee",
        alias="收件方",
        literal_anchor=True,
        expected_token_occurrences=1,
    )
    probes["literal_anchor_constructible"] = {
        "outcome": "constructed",
        "locator_kind": literal.locator_kind,
        "note": (
            "字面文本可作**一次性**迁移线索（Task 6 对 B30-11-2 用的就是字面标题），"
            "安全性来自 expected_token_occurrences 的 fail-closed 计数。"
            "故本任务不发契约的理由是「投影无对端」，不是「造不出锚点」。"
        ),
    }

    probes["probe_gate_identity"] = gate.probe_gate_identity()
    return probes


def _registry_facts() -> dict[str, Any]:
    """Task 13 交付登记表与 pending adapter 门现读（不抄常量）。"""
    from app.services.workpaper_sync import contracts as C
    from app.services.workpaper_sync.adapters import registry as R

    pending_docx = [
        dict(row) for row in R.PENDING_ENGINE_ADAPTERS if row.get("document_type") == "docx"
    ]
    return {
        "delivered_per_entry_contracts": [
            {"entry_id": r["entry_id"], "contract_id": r["contract_id"],
             "delivered_by_task": r["delivered_by_task"],
             "adapter_registered": r["adapter_registered"]}
            for r in R.DELIVERED_PER_ENTRY_CONTRACTS
        ],
        "delivered_per_entry_contract_count": len(R.DELIVERED_PER_ENTRY_CONTRACTS),
        "allowed_provider_modules": sorted(R._ALLOWED_PROVIDER_MODULES),
        "available_contract_ids": sorted(C.available_contract_ids()),
        "pending_docx_adapter_forbidden_paths": [
            p for row in pending_docx for p in row.get("forbidden_paths", ())
        ],
        "pending_docx_blocking_task": [row.get("blocking_task") for row in pending_docx],
        "task64_added_contract_rows": 0,
        "task64_added_provider_modules": 0,
    }


def _a17_projection_ownership() -> dict[str, Any]:
    """A17 七个 docx 子码的「有 HTML 对端但 entry 是 xlsx」归属矛盾现算。"""
    strategy_dir = _BACKEND / "app" / "routers" / "wp_render_strategies"
    manifest = json.loads(_read_text(ENTRY_MANIFEST))
    by_host = {}
    for e in manifest["entries"]:
        by_host.setdefault(Path(e.get("host_path", "")).name, []).append(e)

    strategies: dict[str, Any] = {}
    for p in sorted(strategy_dir.glob("_a17*.py")):
        text = _read_text(p)
        strategies[p.name] = {
            "like_prefixes": sorted(set(re.findall(r"item_id LIKE '([a-z0-9]+-)%'", text))),
            "exact_item_ids": sorted(set(re.findall(r'item_id == "([a-z0-9][\w\-]*)"', text))),
            "startswith_prefixes": sorted(
                set(re.findall(r'item_id\.startswith\("([a-z0-9][\w\-]*)"\)', text))
            ),
        }

    xlsx_entries: dict[str, Any] = {}
    for host, entries in by_host.items():
        if not host.startswith("GtA17") and not host.startswith("GtA16"):
            continue
        for e in entries:
            xlsx_entries[e["entry_id"]] = {
                "host_path": e.get("host_path"),
                "document_type": e.get("document_type"),
                "capability": e.get("capability"),
                "wp_code_patterns": e.get("wp_match", {}).get("wp_code_patterns"),
            }

    ledger = {r["wp_code"]: r for r in _ledger_rows_owned_by_64()}
    conflict = []
    for code in ("A17-1", "A17-2-1", "A17-3", "A17-3-1", "A17-4", "A17-6", "A17-7", "A17-7A"):
        row = ledger.get(code)
        if row is None:
            continue
        conflict.append(
            {
                "wp_code": code,
                "ledger_unified_verdict": row.get("unified_verdict"),
                "ledger_unified_relative_path": row.get("unified_relative_path"),
                "ledger_legacy_verdict": row.get("legacy_verdict"),
                "ledger_legacy_bridge_takes_over": row.get("legacy_bridge_takes_over"),
                "ledger_owner_task": str(row.get("owner_task")),
            }
        )
    return {
        "a17_render_strategies": strategies,
        "a16_a17_component_entries": xlsx_entries,
        "subcode_ownership_conflict": conflict,
        "conflict_summary": (
            "Task 58 清册把这些子码裁为 `resolved_docx`（各有自己的 DOCX 载体、"
            "owner_task=64），但 entry manifest 里它们的独立 entry 全是 "
            "`document_type=xlsx`（存量 `legacy_bridge_takes_over=true` 走父级 "
            "A17 程序表 XLSX）⇒ 「A16/A17 专用 Word 链」的迁移对象与 manifest 的 "
            "entry document_type 不在同一坐标系。改 manifest 是 Task 67 的 structural "
            "pre-reconcile，本任务只如实登记（BP-22），不自行扩权改写。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# 阻断项（编号续接 Task 60 发布记录的 BP-15）
# ════════════════════════════════════════════════════════════════════════════
def _blocking_preconditions(facts: dict[str, Any]) -> list[dict[str, Any]]:
    surface = facts["html_projection_surface"]
    a16_zero = sorted(c for c in A16_SUBCODES if surface[c]["placeholder_count"] == 0)
    legacy_total = sum(
        v["by_pattern_kind"].get("legacy_cjk_marker", 0) for v in surface.values()
    )
    dollar_total = sum(
        v["by_pattern_kind"].get("new_dollar_token", 0) for v in surface.values()
    )
    ordinal_total = sum(v["ordinal_suffixed_field_ids"] for v in surface.values())
    para_pos_total = sum(
        v["by_position_kind"].get("paragraph_index", 0) for v in surface.values()
    )
    return [
        {
            "id": "BP-16",
            "blocks": ["per_entry_contract", "definition_bundle", "capability_verdict"],
            "what": (
                f"A16 链七份权威 DOCX 的生产 HTML 侧字段面实测全为 0（零 placeholder 的是 "
                f"{a16_zero}）⇒ `projection_contract` 没有对端可投影。给没有消费方的投影建 "
                "SDT 与契约就是 additive 死代码（本 spec 的假绿第①源）。"
            ),
            "status": "open",
            "must_fix_before": "把 A16 链的 capability 从 single_html 改成 bidirectional",
            "observable_consequences": [
                "`parse_template` 对 A16-1..A16-7 返回 0 个 placeholder（本记录 "
                "`html_projection_surface` 逐 wp_code 现算）",
                "`registry.assert_authority_model_contract_pairing` 对 opaque + SyncContract "
                "直接抛 AuthorityModelMismatchError ⇒ 「裁 opaque 却发 contract」在 impl 层矛盾",
                "结构化视图（`useWordTemplateStructured`）在 A16 上无字段可渲染，"
                "`isA16Mode` 因此走 OO 弹窗而非结构化视图",
            ],
            "source_refs": [
                "backend/app/routers/wp_render_strategies/_word_template.py",
                "backend/app/services/wp_docx_template_parser.py",
                "backend/app/services/workpaper_sync/adapters/registry.py",
            ],
            "numbering_note": (
                "编号续接 Task 60 发布记录 `workpaper_sync_f2_word_lane_publication.json` 的 "
                "BP-10..BP-15（本记录消费它们、不改它们）；BP-16 起为 A16/A17 链新查出的阻断项。"
            ),
        },
        {
            "id": "BP-17",
            "blocks": ["per_entry_contract", "runtime_anchor"],
            "what": (
                f"生产字段定位今天靠 Task 77 明禁的三种锚点：legacy 中文正则 {legacy_total} 处、"
                f"`paragraph_index` 绝对索引 {para_pos_total} 处、按出现顺序追加 `_2`/`_3` 的 "
                f"field_id {ordinal_total} 处；可用的 `${{}}` 声明式 token 共 {dollar_total} 个。"
            ),
            "status": "open",
            "must_fix_before": "任何 A16/A17 entry 进入 tagged-SDT 运行态",
            "observable_consequences": [
                "`wp_docx_template_parser._LEGACY_PATTERNS` 用 `××公司`/`202X年`/`××` 等中文"
                "字面量作字段身份，Requirement 7.1 明禁中文 label 作定位/身份",
                "`_dedupe_field_id` 按出现顺序编号 ⇒ 审计师改掉第一处 `××公司` 后，"
                "`entity_name` 与 `entity_name_2` 整体错位串值",
                "`PlaceholderDef.position` 是 `{paragraph_index}`，Task 6 对段落绝对索引的 "
                "probe_verdict 已裁 failed（文首插 2 段即整体位移）",
            ],
            "source_refs": [
                "backend/app/services/wp_docx_template_parser.py",
                "backend/app/services/workpaper_sync/word_entry_gate.py",
            ],
            "correction_note": (
                "🔴 本项**不**等于「造不出锚点」。`WordFieldInjection(literal_anchor=True)` "
                "允许字面文本作一次性迁移线索（Task 6 对 B30-11-2 用的就是字面标题），"
                "`WordRowInjection` 允许一次性单元格坐标，且 15/15 模板都有 `w:tbl`。"
                "本记录 `impl_probes.literal_anchor_constructible` 真跑构造成功。"
                "阻断点是**运行态**仍靠禁用锚点，以及 BP-16 的「投影无对端」。"
            ),
        },
        {
            "id": "BP-18",
            "blocks": ["entry_retention", "manifest_scanner_fidelity"],
            "what": (
                "`docx/gt-a17-bundle` 的 `WorkpaperWordEditor` 挂载点外层门控是 "
                "`v-else-if=\"tab.kind === 'word'\"`，而静态 TABS 无任何 `kind: 'word'` ⇒ "
                "运行时恒假、mount 永不渲染（unreachable，Requirement 1.7）。"
                "entry manifest 的 `mounts[].condition` 只记内层 `v-if=\"getTabWpId(tab)\"`，"
                "**外层 kind 门控整条缺失** ⇒ 扫描器口径看不见这类死代码。"
            ),
            "status": "open",
            "must_fix_before": "Task 67 重新生成 manifest 时把外层门控链纳入 mount 事实",
            "observable_consequences": [
                "manifest 该 entry 的 `capability=single_html`、`host_reachable=true`，"
                "但真实渲染路径不可达 ⇒ 计数把一条死 entry 当活的",
                "`scenario_profile.mount_count=1` 与「运行时渲染 0 次」并存",
                "删除动作归 Task 66 计划 + Task 72 Stage B；本任务只裁决与登记",
            ],
            "source_refs": [
                "audit-platform/frontend/src/components/workpaper/GtA17Bundle.vue",
                "backend/data/workpaper_sync_entry_manifest.json",
                "backend/scripts/gen/generate_workpaper_sync_manifest.py",
            ],
        },
        {
            "id": "BP-19",
            "blocks": ["parent_duplicate_resolution", "descriptor_bridge"],
            "what": (
                "`docx/workpaper-word-editor` 是 `parent_duplicate`（父 = "
                "`docx/gt-a16-bundle`），但 `WorkpaperWordEditor.vue` 的 inbound 实测 5 个，"
                "跨 A10/A12/A16/A17 bundle 与 registry 派发 ⇒ 「跟随单一父 entry 裁决」"
                "在它身上不成立：A10/A12 归 Task 62，A16 归本任务。"
            ),
            "status": "open",
            "must_fix_before": "为该宿主接 descriptor/bridge 或裁决其独立性",
            "observable_consequences": [
                "manifest `parent_reason` 写「A16 modal 是 A16 entry 的实现子件」，"
                "但同一组件同时是 A10B/A12B 的宿主 ⇒ 父指向是四选一的任意选择",
                "该宿主与 `OnlyOfficeWordDialog` 都不是 descriptor consumer"
                "（无 `descriptor` prop、无 `defineExpose`、不 import `sync/*`）⇒ "
                "AC 11.5 要求的可 await `forceSave()` 与 durable ack 无承载者",
            ],
            "source_refs": [
                "audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue",
                "audit-platform/frontend/src/components/workpaper/OnlyOfficeWordDialog.vue",
                "backend/data/workpaper_sync_entry_manifest.json",
            ],
        },
        {
            "id": "BP-20",
            "blocks": ["authority_model_publication", "definition_bundle"],
            "what": (
                "本任务裁决的 `opaque_single_onlyoffice` authority model 只能经 "
                "`writer_migration.OpaqueAuthorityProvisioner` 落库，而该通道的收敛归 "
                "Task 65（「收敛 custom/user-upload xlsx 单一权威 bundle 协议」）；"
                "且 approved bundle 需要 DB 侧 definition 行（typed slot 的 slot_ref 形如 "
                "`definition:<uuid>`），离线产不出（同 Task 60 的 BP-11）。"
            ),
            "status": "open",
            "must_fix_before": "把 A16 链与 popup 多路复用器接入统一 room/durable ack",
            "observable_consequences": [
                "本记录只给可复算的裁决与 slot 计划，`db_published` 恒 false",
                "`models.validate_bundle_slot` 对 slot_ref=None 的 definition slot 抛 "
                "BundleIntegrityError",
                "Task 65 未交付前这些 entry 的 capability 保持现状、verification_state "
                "保持 UNVERIFIABLE",
            ],
            "source_refs": [
                "backend/app/services/workpaper_sync/writer_migration.py",
                "backend/app/services/workpaper_sync/models.py",
                ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md",
            ],
        },
        {
            "id": "BP-21",
            "blocks": ["per_entry_contract", "contract_model_expressiveness"],
            "what": (
                f"`docx/wp-popup-docx-editor` 一条 entry 复用给 "
                f"{facts['popup_config_total']} 个 popup 配置（三个 "
                "`wpPopupDocxConfigs*.ts` 顶层 key 现算，观测值附 "
                "`denominator.popup_source_digests`），而 `SyncContract.template` 是"
                "**单个** `TemplateRef`、`load_projection_supply` 要求「一个独立 entry 唯一 "
                "per-entry 契约」（登记表出现 >1 次即 fail closed）⇒ 一对多在契约模型里"
                "无法表达。"
            ),
            "status": "open",
            "must_fix_before": "该宿主进入逐 entry 契约验收",
            "observable_consequences": [
                f"popup 配置按 Task 58 清册 owner_task 分桶跨三家："
                f"{facts['popup_owner_task_counts']} ⇒ 单条 entry 的契约无论挂谁都越界",
                "`contracts.TemplateRef` 只有一组 `relative_path`/`sha256`/`structure_hash`",
                "部分 popup 配置的 templatePath 在模板库里不存在："
                f"{facts['popup_missing_template_files']}（该清单随并发方推进而变，"
                "以 `popup_source_digests` 为观测锚）",
            ],
            "source_refs": [
                "audit-platform/frontend/src/components/workpaper/wpPopupDocxConfigs.ts",
                "backend/app/services/workpaper_sync/contracts.py",
                "backend/app/services/workpaper_sync/projection_provisioning.py",
            ],
        },
        {
            "id": "BP-22",
            "blocks": ["migration_target_coordinates", "owner_task_boundary"],
            "what": (
                "A17 的七个 docx 子码有真实 HTML 对端（a171-/a1721-/a173-/a1731-/a174-/"
                "a176-/a177- 七套 item_id 字段集）与自己的 DOCX 载体（清册裁 "
                "`resolved_docx`、owner_task=64），但它们在 entry manifest 里的独立 entry "
                "全是 `document_type=xlsx`（存量 `legacy_bridge_takes_over=true` 走父级 "
                "A17 程序表 XLSX）⇒ 「A16/A17 专用 Word 链」的迁移对象与 manifest 坐标系不一致。"
            ),
            "status": "open",
            "must_fix_before": "对 A17 子码执行 Word 链迁移或改判其载体归属",
            "observable_consequences": [
                "同一 wp_code 在清册里是 docx、在 manifest entry 里是 xlsx ⇒ "
                "按 manifest 迁移会漏掉整条 A17 Word 链；按清册迁移会与 Task 57 的 "
                "Excel entry 撞车",
                "`A17-5` 出现在 GtA17Bundle 的静态 TABS，但 Task 58 清册无该 wp_code 行"
                "（只有 A17-5-1..A17-5-5）⇒ `getTabWpId` 用首个可用子码顶替",
                "改 manifest 属 Task 67 structural pre-reconcile，本任务无权改写",
            ],
            "source_refs": [
                "backend/data/workpaper_word_template_adjudication.json",
                "backend/data/workpaper_sync_entry_manifest.json",
                "audit-platform/frontend/src/components/workpaper/GtA17Bundle.vue",
            ],
        },
    ]


# ════════════════════════════════════════════════════════════════════════════
# 组装
# ════════════════════════════════════════════════════════════════════════════
def _collect_facts() -> dict[str, Any]:
    ledger_64 = _ledger_rows_owned_by_64()
    popup_rows, popup_digests = _popup_config_rows()
    owner_counts: dict[str, int] = {}
    ledger_all = {r["wp_code"]: r for r in json.loads(_read_text(LEDGER_PATH))["rows"]}
    popup_owned_64: list[str] = []
    for row in popup_rows:
        lr = ledger_all.get(row["wp_code"])
        key = str(lr.get("owner_task")) if lr else "absent_from_ledger"
        owner_counts[key] = owner_counts.get(key, 0) + 1
        if key == "64":
            popup_owned_64.append(row["wp_code"])

    template_facts: dict[str, Any] = {}
    for row in sorted(ledger_64, key=lambda r: r["wp_code"]):
        rel = row.get("unified_relative_path")
        if not rel:
            continue
        template_facts[row["wp_code"]] = dict(
            _docx_facts(TEMPLATE_ROOT / rel), relative_path=rel
        )

    mount_gates = {
        "GtA16Bundle.vue": _mount_gate_chain(
            _read_text(A16_BUNDLE_VUE), "WorkpaperWordEditor"
        ),
        "GtA17Bundle.vue": _mount_gate_chain(
            _read_text(A17_BUNDLE_VUE), "WorkpaperWordEditor"
        ),
        "WorkpaperWordEditor.vue": _mount_gate_chain(
            _read_text(WORD_EDITOR_VUE), "OnlyOfficeWordDialog"
        ),
        "WpPopupDocxEditor.vue": _mount_gate_chain(
            _read_text(POPUP_DOCX_EDITOR_VUE), "OnlyOfficeWordDialog"
        ),
    }

    return {
        "ledger_rows_owned_by_64": len(ledger_64),
        "ledger_wp_codes_owned_by_64": sorted(r["wp_code"] for r in ledger_64),
        "template_facts": template_facts,
        "html_projection_surface": _html_projection_surface(),
        "mount_gate_chains": mount_gates,
        "a17_tab_vocabulary": _a17_tab_kind_vocabulary(),
        "a16_tab_wp_codes": _a16_tab_wp_codes(),
        "popup_config_total": len(popup_rows),
        "popup_owner_task_counts": owner_counts,
        "popup_owned_by_task_64": sorted(popup_owned_64),
        "popup_source_digests": popup_digests,
        "popup_missing_template_files": sorted(
            r["wp_code"] for r in popup_rows if not r["template_exists"]
        ),
        "manifest_docx_entries": _manifest_docx_entries(),
        "registry_facts": _registry_facts(),
        "impl_probes": _impl_probes(),
        "a17_projection_ownership": _a17_projection_ownership(),
    }


def _build_entries(facts: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for decl in ENTRY_DECLS:
        if decl.verdict not in VERDICTS:
            raise SystemExit(f"未登记的 verdict: {decl.verdict}")
        manifest = facts["manifest_docx_entries"].get(decl.entry_id)
        if manifest is None:
            raise SystemExit(
                f"entry {decl.entry_id} 不在 source-backed manifest 的 docx entry 里 —— "
                "裁决对象必须命中 manifest，不得凭空登记"
            )
        host_name = decl.host_vue.name
        out.append(
            {
                "entry_id": decl.entry_id,
                "host_path": decl.host_vue.relative_to(_REPO).as_posix(),
                "verdict": decl.verdict,
                "authority_model": decl.authority_model,
                "why": decl.why,
                "blocked_by": list(decl.blocked_by),
                "manifest_facts": manifest,
                "mount_gate_chain": facts["mount_gate_chains"].get(host_name, []),
                "per_entry_contract": None,
                "definition_bundle": None,
                "published_representation": None,
                "adapter_id": None,
                "capability_current": manifest.get("capability"),
                "capability_verdict_stage": "adjudicated_no_contract_by_design",
                "verification_state": "UNVERIFIABLE",
                "sync_test_run_id": None,
                "required_scenario_set_digest": None,
            }
        )
    return out


def _counters(facts: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    surface = facts["html_projection_surface"]
    return {
        "docx_entries_adjudicated": len(entries),
        "docx_entries_in_manifest_total": len(facts["manifest_docx_entries"]),
        "entries_by_verdict": {
            v: sum(1 for e in entries if e["verdict"] == v) for v in VERDICTS
        },
        "per_entry_contracts_published": sum(
            1 for e in entries if e["per_entry_contract"] is not None
        ),
        "definition_bundles_published": sum(
            1 for e in entries if e["definition_bundle"] is not None
        ),
        "adapters_registered": sum(1 for e in entries if e["adapter_id"] is not None),
        "authoritative_templates_read": len(facts["template_facts"]),
        "templates_with_dollar_tokens": sum(
            1 for v in facts["template_facts"].values() if v["dollar_tokens"]
        ),
        "templates_with_existing_sdt": sum(
            1 for v in facts["template_facts"].values() if v["existing_w_sdt_count"]
        ),
        "templates_with_tables": sum(
            1 for v in facts["template_facts"].values() if v["w_tbl_count"]
        ),
        "html_placeholder_total": sum(v["placeholder_count"] for v in surface.values()),
        "html_placeholder_dollar_total": sum(
            v["by_pattern_kind"].get("new_dollar_token", 0) for v in surface.values()
        ),
        "html_placeholder_legacy_cjk_total": sum(
            v["by_pattern_kind"].get("legacy_cjk_marker", 0) for v in surface.values()
        ),
        "wp_codes_with_zero_html_surface": sorted(
            c for c, v in surface.items() if v["placeholder_count"] == 0
        ),
        "popup_config_total_observed": facts["popup_config_total"],
        "popup_owned_by_task_64_count": len(facts["popup_owned_by_task_64"]),
        "blocking_preconditions_open": sum(
            1 for bp in _blocking_preconditions(facts) if bp["status"] == "open"
        ),
    }


def build_record() -> dict[str, Any]:
    facts = _collect_facts()
    entries = _build_entries(facts)
    bps = _blocking_preconditions(facts)
    surface = facts["html_projection_surface"]

    return {
        "schema_version": SCHEMA_VERSION,
        "task": "64",
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "description": (
            "A16/A17 专用 Word 链与全部 Word editor 宿主的 source-backed 裁决记录。"
            "本任务**不**发布 per-entry tagged-SDT 契约 —— 四条 docx entry 逐条现算后"
            "没有一条同时满足「保留」与「projection 有对端」，故按 Task 63 同款条款"
            "裁决并如实登记，不为满足数字伪造 contract/bundle/finalize。"
        ),
        "paradigm_ref": "backend/data/workpaper_sync_f2_word_lane_publication.json",
        "why_no_per_entry_contract": {
            "wrong_reason_rejected": (
                "「A16/A17 模板零 `${}` token 所以造不出锚点」—— 这个说法本记录用 impl "
                "真跑证伪：`WordFieldInjection(literal_anchor=True)` 可构造"
                "（`impl_probes.literal_anchor_constructible`），Task 6 对 B30-11-2 的注入"
                "用的就是字面标题；`WordRowInjection` 支持一次性单元格坐标，且本任务 "
                f"{sum(1 for v in facts['template_facts'].values() if v['w_tbl_count'])}"
                f"/{len(facts['template_facts'])} 份模板都有 `w:tbl`。"
            ),
            "actual_reason": (
                "`projection_contract` 的语义是「HTML 结构化数据是权威、docx 是其投影」。"
                "A16 链反向：生产 HTML 侧字段面实测 0（`parse_template` 对 A16-1..A16-7 "
                "全返 0 个 placeholder），审计师在 Word 里写整篇声明书 ⇒ docx 本体即权威。"
                "给无消费方的投影建 SDT/契约 = additive 死代码（假绿第①源）；而 "
                "`assert_authority_model_contract_pairing` 对非 projection 传 SyncContract "
                "直接抛 AuthorityModelMismatchError ⇒ 「裁 opaque 却发 contract」是 impl 级矛盾。"
            ),
            "impl_single_points_delegated": [
                "app.services.wp_docx_template_parser.parse_template",
                "app.services.workpaper_sync.word_resolution.resolve_word_template",
                "app.services.workpaper_sync.word_instrumentation.WordSdtCarrierGate.load",
                "app.services.workpaper_sync.word_instrumentation.instrument_docx_bytes",
                "app.services.workpaper_sync.adapters.registry.DELIVERED_PER_ENTRY_CONTRACTS",
            ],
        },
        "denominator": {
            "docx_entries_in_manifest": sorted(facts["manifest_docx_entries"]),
            "docx_entries_owned_by_task_64": [d.entry_id for d in ENTRY_DECLS],
            "docx_entries_owned_by_other_tasks": sorted(
                set(facts["manifest_docx_entries"]) - {d.entry_id for d in ENTRY_DECLS}
            ),
            "ledger_wp_codes_owned_by_64": facts["ledger_wp_codes_owned_by_64"],
            "ledger_rows_owned_by_64": facts["ledger_rows_owned_by_64"],
            "a16_tab_wp_codes": facts["a16_tab_wp_codes"],
            "a17_tab_wp_codes": facts["a17_tab_vocabulary"]["tab_wp_codes"],
            "popup_config_total_observed": facts["popup_config_total"],
            "popup_owner_task_counts": facts["popup_owner_task_counts"],
            "popup_owned_by_task_64": facts["popup_owned_by_task_64"],
            "popup_source_digests": facts["popup_source_digests"],
            "popup_missing_template_files": facts["popup_missing_template_files"],
            "how_counted": (
                "全部现算：manifest 按 `document_type == 'docx'` 过滤；popup 分母按三个 "
                "`wpPopupDocxConfigs*.ts` 的**顶层 key**（不是 relatedLinks[].wpCode）；"
                "tab wp_code 按静态 TABS 的 `wpCode:` 字面量。禁手数（BP-15 教训："
                "「没有承载者所以通过」是假绿，分母必须现算）。"
            ),
            "popup_total_is_an_observation_not_a_baseline": (
                "🔴 `popup_config_total_observed` 是**带 digest 的观测值**，不是被锁死的"
                "基线：三个 popup 配置文件是并发在改的活文件。本任务实测过一次漂移 —— "
                "`wpPopupDocxConfigsS.ts` 的 `S33-REV` 配置在两次现算之间被删掉"
                "（3 个顶层 key → 2 个），而 `S33-REV` 正是 Task 63 正文点名处理的对象，"
                "该文件在 git 里也是 ` M`。故 digest 变化应触发重跑 `--write` 并复核 diff，"
                "把并发方的正常推进判成本任务打红是假红。Task 64 的**稳定**分母是 "
                "`popup_owned_by_task_64`（A16/A17 侧），它不随 B/S 文件漂移。"
            ),
        },
        "entries": entries,
        "authoritative_templates": facts["template_facts"],
        "html_projection_surface": surface,
        "mount_gate_chains": facts["mount_gate_chains"],
        "a17_tab_vocabulary": facts["a17_tab_vocabulary"],
        "a17_projection_ownership": facts["a17_projection_ownership"],
        "registry_facts": facts["registry_facts"],
        "impl_probes": facts["impl_probes"],
        "unreachable_findings": [
            {
                "entry_id": "docx/gt-a17-bundle",
                "host_path": "audit-platform/frontend/src/components/workpaper/GtA17Bundle.vue",
                "mount_line": next(
                    (
                        m["mount_line"]
                        for m in facts["mount_gate_chains"]["GtA17Bundle.vue"]
                    ),
                    None,
                ),
                "outer_gate": next(
                    (
                        m["outer_gate"]
                        for m in facts["mount_gate_chains"]["GtA17Bundle.vue"]
                    ),
                    None,
                ),
                "gate_kind_never_used": facts["a17_tab_vocabulary"][
                    "kinds_declared_but_never_used"
                ],
                "verdict": "unreachable_stub",
                "deletion_owner": "Task 66 计划 + Task 72 Stage B",
            }
        ],
        "cross_entry_isolation": {
            "rule": (
                "四条 entry 的裁决、mount 门控链、模板事实与 blocked_by 逐项独享，"
                "不交叉复用（Task 64 正文「不得跨 entry 复用 contract/bundle/scenario」）。"
            ),
            "assertions": [
                "四条 entry 的 `verdict` 各自独立推导：A16 由 HTML 字段面 0 得 opaque；"
                "A17 bundle 由外层 kind 门控恒假得 unreachable；word-editor 由 manifest "
                "`independent_entry=false` 得 parent_duplicate；popup 由 98 配置对单 "
                "TemplateRef 得 multiplexer",
                "三条 `profile_id` 逐字相同（docx.editable.exclusive.single."
                "room_service_wired.v1）⇒ scenario **不得**按 profile_id 去重，必须按 entry_id",
                "本任务发布 0 份契约、0 份 bundle、0 个 adapter ⇒ 不存在可被复用的产物",
            ],
            "production_contract_dir_untouched": True,
            "delivered_contract_rows_added": 0,
            "provider_modules_added": 0,
        },
        "blocking_preconditions": bps,
        "properties_verified": {
            "Property 30": {
                "claim": "NOT_CLAIMED_NO_TAGGED_SDT_ENTRY_IN_THIS_LANE",
                "denominator": 0,
                "why": (
                    "本 lane 未发布任何 tagged-SDT per-entry contract（裁决见 "
                    "`why_no_per_entry_contract`）⇒ 「tag 是唯一锚点」这条在本 lane 上"
                    "没有承载者。分母现算为 0 并如实标注，不宣称通过。"
                ),
            },
            "Property 31": {
                "claim": "NOT_CLAIMED_NO_MATERIALIZE_IN_THIS_LANE",
                "denominator": 0,
                "why": (
                    "Word-only 区域保留需要一次真实 materialize/往返；本 lane 无契约、"
                    "无 binding、无 candidate ⇒ 无从执行。不借离线 engine 宣称通过。"
                ),
            },
            "Property 47": {
                "claim": "NOT_CLAIMED_CARRIERS_ARE_COUNTEREXAMPLES",
                "denominator": 2,
                "why": (
                    "本 lane 有 2 个 OO 宿主承载者（`WorkpaperWordEditor` 与 "
                    "`OnlyOfficeWordDialog`，现算），但两者都**不是** descriptor consumer："
                    "无 `descriptor` prop、无 `defineExpose`、不 import `sync/*`，"
                    "`OnlyOfficeWordDialog` 的「保存」判据是 `onDocumentStateChange` 取反"
                    "（非 durable ack）⇒ 它们是 Property 47 的**反例**而非通过项"
                    "（BP-19）。分母不是 0：承载者存在且形态相反。"
                ),
            },
            "Property 69": {
                "claim": "NOT_CLAIMED_NO_SCENARIO_EVIDENCE",
                "denominator": 0,
                "why": (
                    "逐 entry sync test run / scenario evidence 一条都没有"
                    "（`sync_test_run_id` 与 `required_scenario_set_digest` 全 null）⇒ "
                    "不宣称通过。真实 OO 场景刷新归 Task 70。"
                ),
            },
            "Property 70": {
                "claim": "PASS",
                "denominator": len(ENTRY_DECLS),
                "how": (
                    "跨 entry 隔离：四条 entry 的 verdict 各自从**不同**的现算事实推导"
                    "（HTML 字段面 / 外层门控链 / manifest independent_entry / popup 配置数），"
                    "且本任务 0 产物可复用。守卫按 entry_id 逐条断言推导依据互不相同，"
                    "并断言三条同 profile_id 的 entry 没有被按 profile 去重。"
                ),
            },
        },
        "property_denominators": {
            "docx_entries": len(ENTRY_DECLS),
            "authoritative_templates": len(facts["template_facts"]),
            "oo_host_components": 2,
            "popup_configs_observed": facts["popup_config_total"],
            "popup_configs_owned_by_task_64": len(facts["popup_owned_by_task_64"]),
            "published_contracts": 0,
            "published_bundles": 0,
            "registered_adapters": 0,
        },
        "counters": _counters(facts, entries),
        "task61_gate_compliance": {
            "gate": "word_bulk",
            "gate_tasks": ["61"],
            "task61_state": "[-] UNVERIFIABLE（真实 OnlyOffice 9.4 F2 Word gate 未通过）",
            "what_this_task_did_not_do": [
                "未建 `adapters/word.py`（`PENDING_ENGINE_ADAPTERS.forbidden_paths` 明禁）",
                "未往 `DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` 加行",
                "未改 entry manifest（重生成归 Task 67）",
                "未改 `backend/wp_templates/` 任何字节（Task 59 第 4 步源文件只读）",
                "未把任何 candidate 带入 resolver/room/current/evidence",
                "未改 capability 为 bidirectional，未宣称任何真实 OO probe 通过",
            ],
            "forbidden_paths_still_absent": True,
        },
        "requirements_covered": [
            "7.1", "7.3", "11.4", "11.5", "11.12", "12.1", "12.5", "12.10", "12.11", "12.12",
        ],
    }


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════
def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只比对不落盘（幂等判据）")
    group.add_argument("--write", action="store_true", help="覆盖产物")
    args = parser.parse_args()

    record = build_record()
    payload = canonical_json_bytes(record)

    if args.write:
        ADJUDICATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        ADJUDICATION_PATH.write_bytes(payload)
        print(f"[write] {ADJUDICATION_PATH.relative_to(_REPO).as_posix()} "
              f"({len(payload)} bytes, sha256={_sha256_bytes(payload)[:16]})")
        return 0

    if not ADJUDICATION_PATH.is_file():
        print(f"[check] 缺产物: {ADJUDICATION_PATH.relative_to(_REPO).as_posix()}")
        return 1
    on_disk = ADJUDICATION_PATH.read_bytes()
    if on_disk == payload:
        print(f"[check] OK 幂等 ({len(payload)} bytes, "
              f"sha256={_sha256_bytes(payload)[:16]})")
        return 0

    print("[check] 产物与现算结果不一致 —— 先跑 --write 再复核 diff")
    print(f"  on_disk sha256 = {_sha256_bytes(on_disk)}")
    print(f"  recomputed     = {_sha256_bytes(payload)}")
    # 区分「上游活文件被并发改动」与「本生成器逻辑变了」：前者是并发方的正常推进，
    # 把它当本任务的红是假红（见 denominator.popup_total_is_an_observation_not_a_baseline）。
    try:
        old = json.loads(on_disk.decode("utf-8"))
        old_digests = old.get("denominator", {}).get("popup_source_digests", {})
        new_digests = record["denominator"]["popup_source_digests"]
        if not old_digests:
            # 旧产物没有这个字段（schema 首次引入），不是漂移 —— 说成漂移会误导。
            print("  ↳ 旧产物无 `popup_source_digests` 字段（schema 变更），非上游漂移。")
        else:
            drifted = sorted(
                name
                for name, digest in new_digests.items()
                if old_digests.get(name) != digest
            )
            if drifted:
                print(
                    "  ↳ 上游 popup 配置文件已被改动（很可能是并发会话在推进 "
                    f"Task 62/63）: {drifted}"
                )
                print("    这不是本任务的缺陷；重跑 --write 并只复核 popup 相关字段的 diff。")
            else:
                print("  ↳ popup source digest 未变 ⇒ 差异来自本生成器逻辑或其他上游事实。")
    except (ValueError, KeyError, AttributeError) as err:
        print(f"  ↳ 无法比对 popup source digest（旧产物结构不符）: {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
