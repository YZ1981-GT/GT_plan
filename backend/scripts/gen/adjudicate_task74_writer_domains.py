# -*- coding: utf-8 -*-
"""Task 74 第一半：把 writer 清册里全部未裁决行逐条裁决进 reviewed overlay。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 7 Task 74
Requirements: 2.1, 2.2, 2.11, 2.12, 9.11, 12.6, 12.7, 13.4 · Property 4, Property 61

═══ 这个脚本是什么、不是什么 ══════════════════════════════════════════════════

**是**：把评审结论（「这一行属于哪条 lane、为什么」）写成**可复核、可复跑的规则表**，再由规则
表逐行渲染 `version_domain_note`。规则表里每一条 `Rule` 都带 `lane` + `why`（lane 归属理由）+
`target`（这条 lane 的迁移目标 / 阻塞理由），这三样就是人工裁决本体；注解里的**事实**部分则一律
从该行自己的 AST 事实渲染，不允许出现该行没有的事实。

**不是**：不是让生成器发明裁决。`generate_workpaper_writer_inventory.py` 仍然「从不发明裁决」——
它只读 overlay。本脚本是 overlay 的**编辑器**，跑完之后 overlay 仍是那份 reviewed 产物，且：

* 规则表 fail-closed：任何一行没有命中规则 ⇒ 直接抛错，绝不给默认 lane（默认 lane 就是
  「未裁决伪装成已裁决」）；
* 注解只允许引用该行**真实存在**的事实键，`check_task74_domain_adjudication_notes.py` 反向逐条
  重算（注解里引用的每个事实必须能在该行 facts 里找到），所以把 A 行的注解粘到 B 行会打红；
* 域标签不改任何 verdict：`bypasses_unified_commit` 等 13 条准则全部由源码派生，裁决只清
  `unadjudicated_writer` / `unadjudicated_resolver` 两条。这一点由
  `test_task74_domain_adjudication.py::test_adjudicating_clears_exactly_two_criteria` 行为级断言。

用法（仓库根）::

    python backend/scripts/gen/adjudicate_task74_writer_domains.py --check
    python backend/scripts/gen/adjudicate_task74_writer_domains.py --apply
    python backend/scripts/gen/generate_workpaper_writer_inventory.py --apply   # 随后必跑
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

_REPO = Path(__file__).resolve().parents[3]
_OVERLAY = _REPO / "backend" / "data" / "workpaper_writer_domain_overlay.json"
_GENERATOR = _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("writer_inventory_generator", _GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ─── 事实渲染：注解里的每一句事实都来自该行自己的 facts ──────────────────────


def _fact_clauses(entry: dict[str, Any]) -> list[str]:
    """把该行的 AST 事实渲染成注解可用的短句。只渲染真实存在的事实。"""
    facts = entry["facts"]
    clauses: list[str] = []
    if facts["sql_update_columns"]:
        clauses.append(
            "raw SQL mutates " + ", ".join(f"`{c}`" for c in facts["sql_update_columns"])
        )
    if facts["content_fields_written"]:
        clauses.append(
            "assigns " + ", ".join(f"`{c}`" for c in facts["content_fields_written"])
        )
    if facts["version_fields_written"]:
        clauses.append(
            "moves the version field " + ", ".join(f"`{c}`" for c in facts["version_fields_written"])
        )
    if entry["delegates_to_content_writer"]:
        clauses.append(
            "delegates the content write to "
            + ", ".join(f"`{d}`" for d in entry["delegates_to_content_writer"])
        )
    if facts["commit_receivers"]:
        clauses.append(
            "owns its own transaction boundary (commit on "
            + ", ".join(f"`{r}`" for r in facts["commit_receivers"])
            + ")"
        )
    elif facts["flush_receivers"]:
        clauses.append(
            "flushes without committing (flush on "
            + ", ".join(f"`{r}`" for r in facts["flush_receivers"])
            + ")"
        )
    if entry["resolver_identities"]:
        clauses.append(
            "reaches the workpaper/template file through "
            + ", ".join(f"`{r}`" for r in entry["resolver_identities"])
        )
    literals = sorted({item["literal"] for item in facts["ad_hoc_paths"]})
    if literals:
        clauses.append(
            "builds the path from the literals " + ", ".join(f"`{l}`" for l in literals)
        )
    if facts["artifact_writes"]:
        traced = sorted({item["target"] for item in facts["artifact_write_targets"]})
        clauses.append(
            "writes an artifact via "
            + ", ".join(f"`{a}`" for a in facts["artifact_writes"])
            + f" (destination classified {', '.join(traced)})"
        )
    if facts["after_save_calls"]:
        clauses.append(
            "calls the save orchestrator " + ", ".join(f"`{c}`" for c in facts["after_save_calls"])
        )
    if facts["unified_commit_calls"]:
        clauses.append(
            "already reaches the unified boundary through "
            + ", ".join(f"`{c}`" for c in facts["unified_commit_calls"])
        )
    return clauses


def _evidence_clause(entry: dict[str, Any]) -> str:
    tests = entry["characterization_tests"]
    if not tests:
        return (
            "No test file resolves a call site to it, so it is also one of the "
            "`writer_without_characterization_test` rows"
        )
    return "Characterization call sites resolve in " + ", ".join(f"`{t}`" for t in tests)


def _shape_clause(entry: dict[str, Any]) -> str:
    """这一行的**结构形态**对迁移意味着什么。逐行由 facts 派生，同 lane 内也不相同。"""
    facts = entry["facts"]
    columns = set(facts["sql_update_columns"])
    fields = set(facts["content_fields_written"])
    bits: list[str] = []

    if any(column.endswith(".<delete>") for column in columns):
        bits.append(
            "it deletes store rows outright, and a delete has no content to attach a version to "
            "-- the strongest form of an application no revision consumer can see"
        )
    remark = "checklist_responses.remark" in columns
    conclusion = "checklist_responses.conclusion" in columns
    if remark and conclusion:
        bits.append(
            "one statement moves both `remark` and `conclusion`, so a single application already "
            "spans two content columns and would need one commit covering both"
        )
    elif remark:
        bits.append(
            "it upserts the `remark` column, the cell-text carrier of this store, so every saved "
            "cell is a business content application"
        )
    elif conclusion:
        bits.append(
            "it upserts the `conclusion` column, which carries the auditor's verdict text rather "
            "than a cell value"
        )

    if "working_paper.parsed_data" in columns and not fields:
        bits.append(
            "it mutates `working_paper.parsed_data` in SQL rather than through the ORM object, so "
            "no ORM-level version hook can ever observe it"
        )
    version_columns = sorted(
        column
        for column in columns
        if column in {"working_paper.content_revision", "working_paper.file_version"}
    )
    if version_columns:
        bits.append(
            "the column it moves is a version column ("
            + ", ".join(f"`{column}`" for column in version_columns)
            + "), not business content"
        )
    if "parsed_data" in fields:
        persists = bool(
            facts["commit_receivers"] or facts["flush_receivers"] or columns
        )
        if persists:
            bits.append(
                "it read-modify-writes the whole `parsed_data` column on the ORM object, which is "
                "the shape that loses concurrent edits when two applications overlap"
            )
        else:
            bits.append(
                "it assigns `parsed_data` on its receiver with no session call anywhere in the "
                "same function, so whether the assignment ever reaches the database depends on "
                "who owns the object -- the AST predicate cannot tell, which is exactly why this "
                "row needs a written adjudication instead of a derived verdict"
            )
    scoped = sorted(field for field in fields if field.startswith("parsed_data[") )
    if scoped:
        bits.append(
            "it writes the scoped key(s) " + ", ".join(f"`{field}`" for field in scoped)
            + ", so only part of the column moves per application"
        )
    if "file_path" in fields:
        bits.append(
            "it repoints `file_path` on its receiver, which changes what a later resolver returns "
            "without moving any counter"
        )
    if entry["canonical_resolver"]:
        bits.append(
            f"it already reaches the file through the canonical `{entry['canonical_resolver']}`"
        )
    elif entry["resolver_identities"]:
        bits.append(
            "it never reaches the canonical `resolve_wp_file`, which is why it is also counted in "
            "`non_canonical_resolver_only`"
        )
    if facts["commit_receivers"] and entry["delegates_to_content_writer"]:
        bits.append(
            "the transaction boundary lives here while the write itself is one level down, so the "
            "boundary and the application are already split across two functions"
        )
    if facts["swallowed_exception_lines"]:
        bits.append(
            f"{len(facts['swallowed_exception_lines'])} except handler(s) swallow without "
            "re-raising, so a failed write can still look successful to the caller"
        )
    if not bits:
        bits.append(
            "its only structural fact is the kind classification itself, so there is nothing here "
            "that a version consumer could observe"
        )
    return "Shape: " + "; ".join(bits)


# ─── 规则表 = 人工裁决本体 ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Rule:
    """一条裁决规则。`match` 命中的行全部进 `lane`，注解由 why/target + 该行事实渲染。"""

    key: str
    lane: str
    why: str
    target: str
    match: Callable[[dict[str, Any]], bool] = field(repr=False)


def _mod(entry: dict[str, Any]) -> str:
    return entry["module"]


def _leaf(entry: dict[str, Any]) -> str:
    return entry["writer_id"].split("::", 1)[1].rsplit(".", 1)[-1]


#: writer_id → entry，供委派链解析。由 `build_adjudications` 在分类前装配。
_INDEX: dict[str, dict[str, Any]] = {}


def _resolved(entry: dict[str, Any], picker: Callable[[dict[str, Any]], set[str]]) -> set[str]:
    """沿真实委派图（`delegates_to_content_writer`）传递求 `picker` 的并集。

    🔴 用委派图而不是函数名正则：入口层的 lane 取决于**内容最终落到哪个存储**，而不是它叫什么。
    名字正则会在第一个 `Cls.method` 形态的被委派方上失手（实测：
    `review_prompt::review_workpaper` → `BatchReviewService.persist_review_results`）。
    """
    seen: set[str] = set()
    stack = [entry]
    out: set[str] = set()
    while stack:
        current = stack.pop()
        writer_id = current["writer_id"]
        if writer_id in seen:
            continue
        seen.add(writer_id)
        out |= picker(current)
        for target in current["delegates_to_content_writer"]:
            nxt = _INDEX.get(target)
            if nxt is not None:
                stack.append(nxt)
    return out


def _own_stores(entry: dict[str, Any]) -> set[str]:
    return set(entry["content_stores_written"])


def _own_content_fields(entry: dict[str, Any]) -> set[str]:
    return set(entry["facts"]["content_fields_written"])


def _writes_only_checklist(entry: dict[str, Any]) -> bool:
    """内容（含经委派）只落 `checklist_responses`，一个字节都不进 `working_paper`。"""
    return _resolved(entry, _own_stores) == {"checklist_responses"}


def _own_html_data_marker(entry: dict[str, Any]) -> set[str]:
    """该行**自己**是否写 `parsed_data.html_data`。

    两种被实测到的形态，都要认：

    * 直接赋值 `wp.parsed_data['html_data']` ⇒ 生成器记进 `content_fields_written`；
    * `_save_html_data` 那种「Python 侧改 `parsed['html_data'][sheet]` 后整列 UPDATE」⇒ 生成器
      只看到 `working_paper.parsed_data` 这一列（局部变量 `parsed` 的下标不算 `parsed_data`），
      所以判据是「函数名 `_save_html_data` **且** 真的写了那一列」，两个条件缺一不认。
    """
    if "parsed_data['html_data']" in _own_content_fields(entry):
        return {"html_data"}
    if (
        _leaf(entry) == "_save_html_data"
        and "working_paper.parsed_data" in entry["facts"]["sql_update_columns"]
    ):
        return {"html_data"}
    return set()


def _reaches_html_data(entry: dict[str, Any]) -> bool:
    """内容（含经委派）最终写进 `parsed_data.html_data`。"""
    return "html_data" in _resolved(entry, _own_html_data_marker)

#: 逐 writer_id 精确裁决（lane 由这一行自己的角色决定，不能靠模块名归并）。
_EXPLICIT: dict[str, tuple[str, str, str]] = {
    # da Task 74 detector fix: rows recovered when _record_ad_hoc_path learned to
    # resolve module-level path constants. Each one is a real production resolver that
    # the old literal-only predicate could not see -- not a new write path.
    "app.routers.knowledge_base::_project_kb_dir": (
        "export_storage_resolver",
        "Composes the per-project knowledge-base directory under the storage tree itself, answering where this project KB files live without going through the canonical resolver",
        "Listing or serving KB files is not a content application, so no version field may move here. The debt is the resolver split: while this row keeps its own path arithmetic, a relocated storage root silently changes what the reader sees",
    ),
    "app.services.bulk_tab.bulk_async_runner::_run_export": (
        "export_storage_resolver",
        "The bulk-tab export job composes its own output path under the storage tree and writes the produced bytes there, publishing a derived deliverable rather than workpaper business content",
        "No business revision may move on an export publish. Convergence means the output path comes from one canonical storage entry instead of this job own arithmetic",
    ),
    "app.services.deliverable_package_service::DeliverablePackageService.run_package_job": (
        "export_storage_resolver",
        "Packages deliverables into an archive under the storage tree: it composes the path, writes the package bytes, and records job progress on its own session",
        "Packaging is a read-then-publish of derived bytes, so no content revision moves. The debt is that the archive path and the canonical resolver are two answers to where a workpaper file lives",
    ),
    "app.services.wp_template_init_service::get_workpaper_storage_path": (
        "export_storage_resolver",
        "Resolves the per-workpaper storage directory by composing the path itself, so provisioning and export both depend on this second entry into the storage namespace",
        "A path resolver applies no content, so no version field may move here. Convergence means one canonical entry for the workpaper storage root",
    ),
    "app.services.wp_xlsx_export_service::_resolve_template_path": (
        "export_storage_resolver",
        "Resolves the xlsx export template from the template library and swaps the rendered file into place, the same role as the sibling export rows already in this lane",
        "Rendering an export is not a content application. The debt is the resolver split between the template library lookup and the canonical workpaper resolver",
    ),
    # ── 统一提交协议自己的写入原语 ────────────────────────────────────────
    "app.services.workpaper_sync.repository::WorkpaperSyncRepository.bump_content_revision": (
        "unified_commit_substrate",
        "This is not a business write path at all: it is the innermost CAS primitive of the "
        "Task 9/15 unified protocol, called *by* `ContentMutationService.commit()` to advance "
        "the one sanctioned counter (`UPDATE ... WHERE content_revision = :expected`)",
        "Nothing to migrate -- it *is* the migration target's counter mover. It is nevertheless "
        "still counted by `bypasses_unified_commit`, because the discovery predicate puts 'the "
        "only writer allowed to move the version' and 'a writer that bypasses the unified entry' "
        "in one verdict. Task 20's evidence README section 4.2 registered that as a predicate "
        "layering defect and recommended a separate task; this adjudication records the lane "
        "and deliberately does NOT touch the predicate, so the count does not move",
    ),
    # ── AST 记为 writer 但零持久化 ────────────────────────────────────────
    "app.services.qc_rule_dry_run_service::_WorkpaperSample.__init__": (
        "read_only_evaluation",
        "A dry-run DTO constructor: `self.parsed_data = parsed_data or {}` binds an in-memory "
        "attribute on a throwaway sample object so QC rules can be evaluated without touching "
        "the database. No session, no SQL, no artifact write -- it persists nothing",
        "Nothing to migrate. The row exists because the discovery predicate matches the "
        "attribute *name* `parsed_data` on any receiver, not because a workpaper moved. It stays "
        "inside `bypasses_unified_commit` on purpose: an untraceable 'this one does not really "
        "write' claim is exactly the fail-open shape the gate refuses, so the honest record is a "
        "lane plus this note, not an exemption",
    ),
    "app.services.qc_rule_dry_run_service::_build_qc_context._SimpleContext.__init__": (
        "read_only_evaluation",
        "The same shape as `_WorkpaperSample.__init__` one scope over: a locally defined context "
        "class whose `__init__` binds `parsed_data` in memory so a QC rule can be evaluated "
        "against a candidate payload",
        "Nothing to migrate; see the sibling row. Kept in the gate's bypass count rather than "
        "excused, because 'no measured content facts' is a measurement outcome, not a proof that "
        "the row holds no authoritative content",
    ),
    # ── 事件/保存后副作用 ────────────────────────────────────────────────
    "app.services.consistency_check_service::ConsistencyCheckService.update_workpaper_consistency": (
        "orchestrator_side_effect",
        "Its own docstring names the lane: '底稿保存后...从 event_handlers._on_workpaper_saved "
        "提取' -- it runs after a workpaper save and writes the audited-vs-trial-balance verdict "
        "into `parsed_data.wp_consistency`",
        "Requirement 13.4 forbids a post-save side effect from moving any version field, and this "
        "row moves none, so it does not trip `after_save_still_increments_revision`. What it does "
        "need is to stop being a second writer of `parsed_data` behind the save it reacts to: the "
        "verdict has to ride the same `ContentMutationService.commit()` as the save, or move out "
        "of workpaper content entirely. Adjudicating it here also makes the gate's "
        "`orchestrator_side_effect` branch reachable from `entries` for the first time (Task 20's "
        "README section 9 registered it as reachable only through the retired ledger)",
    ),
    "app.services.event_handlers._impl::register_event_handlers._on_b514_high_risk": (
        "orchestrator_side_effect",
        "An EventBus handler registered inside `register_event_handlers`: on a B51-4 high fraud "
        "risk verdict it appends the F2-61~F2-72 workpapers by calling `_ensure_ipo_loaded`, "
        "which Task 3 already adjudicated as `template_provisioning`",
        "It holds no content of its own -- the lane statement is about the trigger, not the "
        "store. Two obligations follow: it must never move a version field (it moves none today, "
        "which is why `after_save_still_increments_revision` stays zero with this row in the "
        "lane), and its commit has to become the provisioning call's commit instead of a second "
        "boundary opened by the handler",
    ),
    # ── excel_html sidecar（活的平行权威）────────────────────────────────
    "app.routers.excel_html::save_edits": (
        "html_save",
        "The excel_html sidecar's own HTML save endpoint: it persists edited cells into "
        "`storage/projects/{pid}/excel_html/{stem}.structure.json` and rewrites the derived HTML, "
        "which is the same *kind* of write as `wp_html_save::save_html_data` but into a second, "
        "file-based authority with no `working_paper` row and no version column",
        "Cannot follow `save_html_data` into `ContentMutationService` as written: the whole module "
        "is keyed by `file_stem`, so there is no workpaper scope to open a content version "
        "against. Requirement 12.9 (bind the sidecar to workpaper identity, or delete it) is a "
        "product decision gated by Requirement 12.7's equivalence evidence, exactly as recorded "
        "for the sibling `rollback_file_version` row",
    ),
    "app.routers.excel_html::execute_formulas": (
        "html_save",
        "Evaluates every formula cell in the sidecar's `structure.json` and writes the computed "
        "values back into that same file plus a version snapshot -- a derived-content save inside "
        "the excel_html authority rather than a separate lane",
        "Same blocker as `save_edits`: no `wp_id`, so no content version to open. Migrating it "
        "means the formula results land in `working_paper.parsed_data` through the unified commit, "
        "which is only possible once the sidecar is bound to workpaper identity (Requirement 12.9)",
    ),
    "app.routers.excel_html::sync_from_onlyoffice": (
        "oo_callback",
        "The sidecar's OnlyOffice ingest: it pulls the edited workbook back out of OO and rewrites "
        "the sidecar's structure/HTML, i.e. the same role `wp_onlyoffice_router::"
        "post_sheet_onlyoffice_callback` plays for real workpapers",
        "The canonical `oo_callback` lane is being migrated onto room/staged representations "
        "(Tasks 25/26/36); this row cannot join it while its substrate is a `file_stem`-keyed "
        "sidecar with no representation generation. It is one of the paths Requirement 12.9 wants "
        "either bound to workpaper identity or deleted",
    ),
    "app.routers.excel_html::confirm_as_template": (
        "template_provisioning",
        "Promotes a sidecar workbook into the template library (copies the xlsx and writes the "
        "template's structure/HTML), which is the provisioning lane `WpMigrationService."
        "migrate_workpaper` and `init_workpaper_from_template` already occupy",
        "Provisioning writes are not business content applications, but this one still resolves "
        "and writes files itself instead of going through the canonical resolver plus the unified "
        "commit; the artifact destinations are `unclassified`, so it cannot claim the "
        "artifact-snapshot category either",
    ),
    # ── 附件 / 出品物：file_path 属于别的模型 ─────────────────────────────
    "app.services.evidence_governance.secure_attachment_gateway::SecureAttachmentGateway._promote_available._promote": (
        "upload_import",
        "The staged-to-available promotion of an uploaded evidence attachment. Honest measurement "
        "note: the `file_path` it assigns belongs to the attachment/version row, not to "
        "`working_paper` -- the row is in the inventory because the discovery predicate matches "
        "the attribute name on any receiver, and the generator then reports the store as "
        "`working_paper`",
        "Its own store (attachment versions) is outside the workpaper version domain, so the "
        "migration question is scoping, not counters: either the predicate learns to tell the two "
        "models apart (a Task 20-style predicate change, not a Task 74 adjudication) or the "
        "promotion keeps its own boundary. Recorded here so the row stops being an unexplained "
        "red line",
    ),
    "app.services.eqcr_memo_service::EqcrMemoService.finalize_memo": (
        "export_storage_resolver",
        "Renders the EQCR memo to docx/pdf and stores the produced file paths in "
        "`project.wizard_state.eqcr_memo.files`; it is a render-to-file path like "
        "`WpExportEngine._export_docx`, not a workpaper content application",
        "The lane's migration is about the *resolver*: it builds its own destination under "
        "`wp_storage` instead of going through the canonical `resolve_wp_file`, which is why it "
        "also shows up in `non_canonical_resolver_only`. The bytes it writes are a deliverable, "
        "so no `content_revision` should move for it",
    ),
    # ── 试算表重算后的 stale 收敛 ────────────────────────────────────────
    "app.services.prefill_engine::resolve_stale_after_recalc": (
        "dedicated_router",
        "The prefill stack's convergence entry after a full trial-balance recalculation: it "
        "re-runs `prefill_workpaper_real` for workpapers that hold formula snapshots and keeps "
        "`html_data`-only workpapers stale on purpose",
        "It inherits the lane of the writer it delegates to, so it migrates when "
        "`prefill_workpaper_real` starts committing through `ContentMutationService`; on its own "
        "it holds no content and must not open a second boundary around the batch",
    ),
    # ── 新协议自己的 artifact 布局 ───────────────────────────────────────
    "app.services.workpaper_sync.artifacts::ArtifactStorageLayout.project_root": (
        "export_storage_resolver",
        "The sync protocol's artifact layout root (`{storage_root}/{project}/workpapers`). It "
        "addresses immutable per-content-version artifacts, not the live workpaper file, so it is "
        "deliberately not a `resolve_wp_file` caller",
        "It is counted in `non_canonical_resolver_only` because it composes the path itself. That "
        "is the correct verdict for the *canonical resolver* question and the wrong lane to "
        "'fix' by pointing it at `resolve_wp_file`: artifact addressing must stay independent of "
        "wherever the live file currently sits. Requirement 9.11 convergence for this row means "
        "the layout stays the single owner of the artifact namespace",
    ),
    # ── 模板集批量生成 ──────────────────────────────────────────────────
    "app.services.template_engine::TemplateEngine.generate_project_workpapers": (
        "template_provisioning",
        "Creates `wp_index` + `working_paper` rows for a template set and copies each template "
        "xlsx into the project directory -- the same provisioning role as "
        "`init_workpaper_from_template`, one level up (per template set instead of per code)",
        "Provisioning is allowed to create the artifact, but it must stop composing storage paths "
        "itself: the destination has to come from the canonical resolver so that the file a "
        "resolver later returns and the file provisioning wrote can never diverge",
    ),
}

#: 模式规则。顺序敏感：先精确、后模式；命中即停。
_RULES: tuple[Rule, ...] = (
    # ═══ resolver 域 ═══════════════════════════════════════════════════
    Rule(
        key="wopi_resolver",
        lane="wopi",
        why="A WOPI host entry point that resolves the workpaper's physical file through the "
        "canonical `resolve_wp_file` before serving or accepting Office bytes; it belongs with "
        "`WOPIHostService.put_file`, which Task 3 adjudicated into the same lane",
        target="Read-side WOPI members hold no content, so their obligation is the resolver one: "
        "keep using the canonical resolver (they already do) and never grow a private path or a "
        "second version counter next to `put_file`'s unified commit",
        match=lambda e: _mod(e) == "app.services.wopi_service",
    ),
    Rule(
        key="storage_version_listing",
        lane="history_restore",
        why="The read half of the version-snapshot lane: it lists the `.versions/` snapshots that "
        "`WpStorageService.save_version` (already adjudicated `history_restore`) produced, "
        "resolving the live file through the canonical `resolve_wp_file`",
        target="Nothing to commit -- it is a listing. Task 20 measured this row as one of the two "
        "false characterization credits (a guard that merely mentioned the module credited it), so "
        "its real obligation is a test that actually calls it before the history lane is claimed "
        "verified",
        match=lambda e: e["writer_id"] == "app.services.wp_storage_service::WpStorageService.list_versions",
    ),
    Rule(
        key="template_finder",
        lane="export_storage_resolver",
        why="A template-library lookup: it answers 'which template file backs this wp_code', "
        "which is the resolver lane `wp_export.wp_file_resolver::_template_fallback` already "
        "occupies -- not a content write",
        target="Requirement 9.11 wants one canonical resolver for the *workpaper* file; template "
        "lookup is a second, legitimate namespace, so convergence here means the finder stays the "
        "only entry into it instead of every caller re-globbing `wp_templates`",
        match=lambda e: _mod(e) == "app.services.wp_template_finder",
    ),
    Rule(
        key="docx_sync_project_file",
        lane="export_storage_resolver",
        why="Locates the project's docx under the `workpapers` storage tree for the A-cycle Word "
        "sync to read back, composing the path itself instead of calling the canonical resolver",
        target="The sync's write half is adjudicated separately (`checklist_response_store`); this "
        "half must move onto the canonical resolver, otherwise the file the sync reads and the "
        "file a download serves can drift apart -- the exact second-authority split Requirement "
        "9.11 is about",
        match=lambda e: _leaf(e) == "_get_project_file",
    ),
    Rule(
        key="template_path_resolver",
        lane="export_storage_resolver",
        why="Resolves a template/render path for a read-only consumer (render config, guidance "
        "chat, program-table data, docx conversion, account package). It reaches the file through "
        "the template finder or its own path composition, never through `resolve_wp_file`",
        target="Same convergence obligation as the rest of the resolver lane: one canonical entry "
        "for the workpaper file and one for the template library. Until then every one of these "
        "rows is a place where a renamed or relocated file silently changes what the reader sees",
        match=lambda e: _mod(e)
        in {
            "app.routers.wp_guidance_chat",
            "app.routers.wp_render_config",
            "app.routers.wp_render_config_helpers",
            "app.routers.wp_render_strategies._a_program",
            "app.routers.wp_template_docx",
            "app.services.wp_account_package_resolver",
        },
    ),
    Rule(
        key="download_export_resolver",
        lane="export_storage_resolver",
        why="A download/preview/export path that resolves the bytes to serve by composing a "
        "`storage/...` path or by asking the template finder, exactly like the "
        "`WpDownloadService` / `WpExportEngine` rows Task 3 put in this lane",
        target="Serving bytes is not a content application, so no version field may move here. "
        "The debt is the resolver split: while these rows keep their own path arithmetic, "
        "'what the user downloads' and 'what the canonical resolver returns' are two answers to "
        "one question",
        match=lambda e: e["writer_id"]
        in {
            "app.routers.attachments::download_attachment",
            "app.routers.attachments::preview_attachment",
            "app.routers.completion_phase::export_workpaper_word",
            "app.routers.office_preview::_resolve_local_path",
            "app.routers.wp_download::get_cloud_url",
            "app.routers.wp_template_download::download_template_by_code",
            "app.routers.wp_template_download::download_template_prefilled",
            "app.routers.wp_template_download::preview_template_as_pdf",
            "app.services.export_job_service::ExportJobService.update_progress",
        },
    ),
    Rule(
        key="excel_html_sidecar_reader",
        lane="export_storage_resolver",
        why="A read-side member of the excel_html sidecar: it resolves "
        "`storage/projects/{pid}/excel_html/...` itself to serve HTML, cell info, a version list, "
        "a diff or a module export. The sidecar is a live parallel authority mounted through "
        "`router_registry`, and these rows are how it is read",
        target="Nothing to commit, but nothing to keep either: Requirement 12.9 asks for the "
        "sidecar to be bound to workpaper identity or deleted, and Requirement 12.7 requires "
        "equivalence evidence plus a rollback point first. Until that product decision lands, "
        "every one of these readers is a second answer to 'what is this workpaper's content'",
        match=lambda e: _mod(e) == "app.routers.excel_html",
    ),
    # ═══ working_paper 内容写路径 ══════════════════════════════════════
    Rule(
        key="html_data_writer",
        lane="html_save",
        why="Writes workpaper business content into `parsed_data.html_data` -- the store and the "
        "shape of the canonical HTML save (`wp_html_save::save_html_data`). Its own body performs "
        "that write",
        target="`save_html_data` is already migrated: Task 16 routes it through "
        "`build_html_content_mutation_service`, so this row's migration is not a design question "
        "but the same adapter applied at this call site -- and the second transaction boundary "
        "(where it has one) must disappear with it",
        match=lambda e: bool(_own_html_data_marker(e)),
    ),
    Rule(
        key="html_data_delegator",
        lane="html_save",
        why="The entry point of an HTML-shaped save: it holds no content of its own, and following "
        "its delegation edges to the end lands in `parsed_data.html_data`",
        target="It inherits `save_html_data`'s migrated adapter through its delegate; the remaining "
        "obligation on this chain is that no second transaction boundary is opened around it -- "
        "wherever one exists today, a single business application spans two commits, which "
        "Requirement 2.4 forbids",
        match=lambda e: not _own_stores(e) and _reaches_html_data(e),
    ),
    Rule(
        key="dedicated_calc_router",
        lane="dedicated_router",
        why="A dedicated cycle-calculation endpoint (or the private helper it delegates to) that "
        "writes its result straight into `working_paper.parsed_data`. Task 3 put the equivalent "
        "editor-side rows (`wp_editor_router`, `wp_structure`, "
        "`wp_parsed_data_service::write_cell_to_parsed_data`) in this lane",
        target="These are real content applications, so each needs the unified boundary: read the "
        "current `content_revision`, apply, commit once through `ContentMutationService`. Today this "
        "lane persists outside that boundary (most of its rows open their own commit), which is why "
        "one calculation can leave the version unchanged while the content moves",
        match=lambda e: _mod(e).startswith("app.routers.wp_")
        and (
            _leaf(e).startswith("_maybe_apply")
            or bool(
                {"parsed_data", "parsed_data['user_formulas']", "parsed_data['action_data']"}
                & set(e["facts"]["content_fields_written"])
            )
            or "working_paper.parsed_data" in e["facts"]["sql_update_columns"]
            or any(
                "_maybe_apply" in target or "::_fill_parsed_data" in target
                for target in e["delegates_to_content_writer"]
            )
        ),
    ),
    Rule(
        key="dedicated_router_service",
        lane="dedicated_router",
        why="A service behind the dedicated editor/prefill/procedure endpoints that writes "
        "`working_paper.parsed_data` (or delegates to the function that does). Task 3 already "
        "adjudicated `wp_parsed_data_service::write_cell_to_parsed_data` into this lane, so the "
        "rest of the same stack belongs with it",
        target="One unified commit per business application. The lane's specific hazard is "
        "layering: the router commits, the service commits, and the engine assigns -- so the same "
        "edit can move `parsed_data` two or three times with no version movement at all",
        match=lambda e: _mod(e)
        in {
            "app.routers.audit_check",
            "app.routers.working_paper",
            "app.routers.wp_ai_confirm",
            "app.routers.wp_editor_router",
            "app.routers.wp_fine_rules",
            "app.routers.wp_formula",
            "app.routers.wp_procedure_status",
            "app.services.audit_check.aggregator",
            "app.services.prefill_engine",
            "app.services.procedure_projection_service",
            "app.services.procedure_trim_engine",
            "app.services.wp_evidence_ocr_service",
            "app.services.wp_explanation_service",
            "app.routers.wp_prefill_preview",
        },
    ),
    # ═══ checklist_responses 第二权威 ═════════════════════════════════
    Rule(
        key="checklist_store",
        lane="checklist_response_store",
        why="Its business content lands in `checklist_responses`, the second content authority "
        "Requirement 9.11 names: no `working_paper` row is touched, so nothing about this write "
        "is visible to any `working_paper` version consumer",
        target="This is the lane Task 20's evidence flagged as declared-but-empty (97 rows). "
        "Migrating it is not an adapter tweak: `ContentMutationService` commits `working_paper` "
        "content, so the unified protocol first has to own a `checklist_responses` content scope "
        "-- until it does, every one of these rows is a business application with no revision at "
        "all. That work is Task 74's second half and is deliberately not done in this pass",
        match=_writes_only_checklist,
    ),
    # ═══ 导出 / 出品物渲染 ════════════════════════════════════════════
    Rule(
        key="render_to_file",
        lane="export_storage_resolver",
        why="Renders a deliverable (docx/pdf/xlsx) and points `file_path` at the produced file, "
        "the same role as `wp_xlsx_export_service::_sync_export_workpaper_xlsx` and "
        "`WpExportEngine._export_docx` in this lane",
        target="A rendered deliverable is derived output, so no business `content_revision` may "
        "move for it. What must converge is where the bytes land: while each renderer composes "
        "its own destination, `file_path` can point at a file the canonical resolver would never "
        "return",
        match=lambda e: _mod(e)
        in {
            "app.services.deliverable_refresh_service",
            "app.services.deliverable_service",
            "app.services.export_progress_service",
            "app.services.pdf_export_engine",
            "app.services.word_template_filler",
        },
    ),
    # ═══ 模板下发 / 底稿生成 ══════════════════════════════════════════
    Rule(
        key="provisioning",
        lane="template_provisioning",
        why="Provisions the workpaper itself -- it creates or replaces the physical file (and the "
        "`working_paper` row that points at it) from a template or a conversion source, which is "
        "the lane `init_workpaper_from_template` and `WpMigrationService.migrate_workpaper` "
        "already occupy",
        target="Provisioning legitimately creates content, but it has to do it once, through the "
        "canonical resolver, inside the unified boundary. Today this lane composes storage paths "
        "itself and persists outside that boundary, so a freshly provisioned workpaper starts life "
        "with content that no revision ever recorded",
        match=lambda e: _mod(e)
        in {
            "app.routers.wp_template",
            "app.services.b60_plan_service",
            "app.services.chain_orchestrator",
            "app.services.workpaper_generation_service",
            "app.services.wp_conversion._generate",
            "app.services.wp_standard_conversion_service",
        },
    ),
    # ═══ 回滚 / 历史恢复 ══════════════════════════════════════════════
    Rule(
        key="snapshot_rollback",
        lane="history_restore",
        why="Restores a previously captured snapshot by delegating to "
        "`VersionTrailService.rollback_to_snapshot`, which Task 3 adjudicated `history_restore` "
        "and Task 18 already routed through the unified commit",
        target="The write itself is migrated inside the delegate; what remains on this chain is that "
        "no second transaction boundary wraps it, so a restore stays exactly one content application "
        "with exactly one revision movement",
        match=lambda e: any(
            target.endswith("::VersionTrailService.rollback_to_snapshot")
            for target in e["delegates_to_content_writer"]
        ),
    ),
    Rule(
        key="cycle_import_entry",
        lane="checklist_response_store",
        why="A cycle import endpoint whose delegation chain ends in the `checklist_responses` "
        "store: the uploaded workbook's cells become checklist remarks/conclusions, and no "
        "`working_paper` row is touched anywhere on the chain",
        target="Same blocker as the rest of the second-authority lane: the unified protocol has no "
        "`checklist_responses` content scope yet, so the import cannot open a content version at "
        "all. The extra debt on this chain is any transaction boundary opened around the delegate: "
        "the boundary and the write already sit in different functions",
        match=lambda e: not _own_stores(e)
        and _resolved(e, _own_stores) == {"checklist_responses"},
    ),
)


def classify(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    """返回 (rule_key, lane, why, target)。命不中即抛 —— 默认 lane 是禁止的。"""
    explicit = _EXPLICIT.get(entry["writer_id"])
    if explicit is not None:
        return ("explicit:" + entry["writer_id"], *explicit)
    for rule in _RULES:
        if rule.match(entry):
            return rule.key, rule.lane, rule.why, rule.target
    raise SystemExit(
        "[FAIL] no adjudication rule matches "
        f"{entry['writer_id']} (kind={entry['kind']} stores={entry['content_stores_written']} "
        f"facts={json.dumps({k: v for k, v in entry['facts'].items() if v}, ensure_ascii=False)}). "
        "Add an explicit adjudication or a rule -- a default lane would be an undecided writer "
        "wearing an adjudicated label."
    )


def _entered_from(entry: dict[str, Any]) -> str:
    """谁在清册里委派到它（反向边）。迁移时「从哪进来」是逐行不同的实操信息。"""
    callers = sorted(
        other["writer_id"]
        for other in _INDEX.values()
        if entry["writer_id"] in other["delegates_to_content_writer"]
    )
    if not callers:
        return "no other inventory row delegates to it, so it is an entry point of its own"
    return "entered from " + ", ".join(f"`{caller}`" for caller in callers)


def build_note(entry: dict[str, Any], why: str, target: str) -> str:
    """身份/入边（派生） + lane 理由（人工） + 该行事实与形态（派生） + 迁移目标（人工） + 证据。"""
    clauses = _fact_clauses(entry)
    measured = "; ".join(clauses) if clauses else "no content or resolver fact beyond its kind"
    return (
        f"`{entry['qualname']}` in `{entry['source_path']}` ({entry['kind']}), "
        f"{_entered_from(entry)}. Lane: {why}. Measured: {measured}. "
        f"{_shape_clause(entry)}. {target}. {_evidence_clause(entry)}."
    )


def _identity_prefix(entry: dict[str, Any]) -> str:
    return f"`{entry['qualname']}` in `{entry['source_path']}`"


def _is_owned_by_this_script(entry: dict[str, Any]) -> bool:
    """这条已有裁决是不是本脚本写的？

    判据是**自描述的身份前缀**（`` `qualname` in `source_path` ``），不是外部名单：脚本因此可以
    重复跑（改了措辞就重渲染自己的行），同时绝不会碰 Task 3 那 49 条人工注解 —— 它们全都以散文
    开头，没有这个前缀。
    """
    note = (entry["adjudication"] or {}).get("version_domain_note") or ""
    return note.startswith(_identity_prefix(entry))


def build_adjudications(
    inventory: dict[str, Any]
) -> tuple[dict[str, dict[str, str]], Counter, int]:
    _INDEX.clear()
    _INDEX.update({entry["writer_id"]: entry for entry in inventory["entries"]})
    added: dict[str, dict[str, str]] = {}
    histogram: Counter = Counter()
    refreshed = 0
    for entry in inventory["entries"]:
        if entry["adjudication"]["status"] == "adjudicated":
            if not _is_owned_by_this_script(entry):
                continue
            refreshed += 1
        rule_key, lane, why, target = classify(entry)
        added[entry["writer_id"]] = {
            "domain": lane,
            "version_domain_note": build_note(entry, why, target),
        }
        histogram[lane] += 1
    return added, histogram, refreshed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the overlay")
    parser.add_argument("--check", action="store_true", help="report without writing")
    parser.add_argument("--dump", help="write the proposed adjudications to a JSON file for review")
    args = parser.parse_args(argv)

    generator = _load_generator()
    overlay = json.loads(_OVERLAY.read_text(encoding="utf-8"))
    rows, function_facts = generator.collect_source_facts()
    inventory = generator.build_inventory(rows, overlay, function_facts)

    added, histogram, refreshed = build_adjudications(inventory)
    print(f"rows this script owns: {len(added)} (newly adjudicated {len(added) - refreshed}, "
          f"re-rendered {refreshed})")
    for lane, count in sorted(histogram.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {lane:26} {count}")
    notes = [value["version_domain_note"] for value in added.values()]
    if not notes:
        print("[FAIL] no row to adjudicate and none owned by this script -- nothing to verify")
        return 1
    print(f"note length: min={min(map(len, notes))} max={max(map(len, notes))}")
    print(f"distinct notes: {len(set(notes))} / {len(notes)}")

    if args.dump:
        Path(args.dump).write_text(
            json.dumps(added, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[OUT] {args.dump}")

    if len(set(notes)) != len(notes):
        duplicates = [note for note, count in Counter(notes).items() if count > 1]
        print(f"[FAIL] {len(duplicates)} notes are not unique -- a shared note is a template")
        return 1

    if not args.apply:
        print("[CHECK] overlay not written (pass --apply)")
        return 0

    merged = dict(overlay["adjudications"])
    foreign = sorted(
        writer_id
        for writer_id in set(merged) & set(added)
        if not (merged[writer_id].get("version_domain_note") or "").startswith("`")
    )
    if foreign:
        print(f"[FAIL] would overwrite adjudications this script does not own: {foreign[:5]}")
        return 1
    merged.update(added)
    overlay["adjudications"] = {key: merged[key] for key in sorted(merged)}
    overlay["task"] = (
        "Wave 0 Task 3 (initial 49) + Wave 7 Task 74 (domain adjudication of the remaining 270)"
    )
    _OVERLAY.write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[APPLY] {_OVERLAY} now carries {len(overlay['adjudications'])} adjudications")
    print("[NEXT] python backend/scripts/gen/generate_workpaper_writer_inventory.py --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
