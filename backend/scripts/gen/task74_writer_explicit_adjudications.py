"""Task 74 writer 域裁决里「逐 writer_id 精确裁决」那张表（只有数据，不含规则）。

从 `adjudicate_task74_writer_domains.py` 原样拆出：2026-11-03 清册重算补裁后该文件到 1127 行，
超过行数门（白名单基线 1030 + 5%）。表是人工裁决的数据，规则引擎（`_RULES` / `classify`）留在
原文件；拆开后两边各自更好审，原文件 `from … import EXPLICIT as _EXPLICIT`，调用方零改动。
"""
from __future__ import annotations

#: 逐 writer_id 精确裁决（lane 由这一行自己的角色决定，不能靠模块名归并）。
EXPLICIT: dict[str, tuple[str, str, str]] = {
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
    # ── 有界委派闭包 (2026-09-20) 补回的多跳 writer/resolver 入口 ─────────────
    # 单跳传播盲区：D2/D4 双向回写迁移把 d4_import_data/import_data 从 direct writer
    # 改成委派 writer，调用它们的适配器/端点因此掉出发现面。闭包补回后逐条裁决入 lane。
    "app.routers.b60_plan::post_b60_plan_update": (
        "template_provisioning",
        "The B60 plan-update endpoint; its delegation chain reaches the B60 plan provisioning "
        "service (`bump_plan_version` / `save_attachment_flags`), which Task 3 already put in the "
        "provisioning lane, so this entry point belongs with it",
        "It holds no content of its own and inherits the provisioning lane through its delegates; "
        "it must not open a second transaction boundary next to the provisioning commit, and its "
        "chain migrates when the B60 plan service commits through `ContentMutationService`",
    ),
    "app.routers.b60_plan::put_b60_attachment_flags": (
        "template_provisioning",
        "The B60 attachment-flag endpoint; it delegates to `b60_plan_service.save_attachment_flags`, "
        "a provisioning-lane writer, so the entry point shares that lane",
        "Same obligation as its sibling `post_b60_plan_update`: no second boundary here, and the "
        "chain migrates onto `ContentMutationService` when the plan service does",
    ),
    "app.routers.custom_workpaper_cells::update_custom_cells": (
        "custom",
        "The custom-cell write endpoint. Task 19 routed its authoritative xlsx body through "
        "`ContentMutationService` (so it carries no direct version/content fact of its own), but "
        "it still delegates to `refresh_custom_projection`, which refreshes the custom projection "
        "into `working_paper.parsed_data`; that delegation is a real content mutation, so it is a "
        "delegation writer two hops above the projection writer. It was retired under the "
        "single-hop discovery model, which masked this edge",
        "The authoritative-body leg is already migrated; the remaining obligation is that the "
        "projection refresh it triggers rides the same unified commit rather than a second write "
        "of `parsed_data`, and that no second transaction boundary wraps the pair",
    ),
    "app.routers.custom_workpaper_cells::refresh_custom_projection_endpoint": (
        "custom",
        "The custom projection-refresh endpoint; it delegates to `refresh_custom_projection` -> "
        "`write_projection_to_parsed_data`, the same custom-projection writer its sibling "
        "`update_custom_cells` reaches, so it shares the custom lane",
        "It inherits the custom lane through its delegate; the projection write must move onto the "
        "unified commit and it must not open its own boundary around the refresh",
    ),
    "app.routers.d2_sync_router::_load_context": (
        "export_storage_resolver",
        "A D2 sync helper that resolves the OnlyOffice storage directory through "
        "`_onlyoffice_storage_dir` to locate the workpaper's cached file, composing a storage path "
        "rather than reaching the canonical `resolve_wp_file`",
        "A path resolver applies no content, so no version field may move here. The debt is the "
        "resolver split: it reaches the file through the OnlyOffice cache directory instead of the "
        "canonical resolver, which is why it is also counted in `non_canonical_resolver_only`",
    ),
    "app.routers.trial_balance::recalc_trial_balance": (
        "dedicated_router",
        "The trial-balance recalculation endpoint; it delegates to "
        "`prefill_engine.resolve_stale_after_recalc`, a dedicated-router-lane convergence writer, "
        "so this entry point shares that lane",
        "It holds no content of its own and inherits the lane through its delegate; it must not "
        "open a second boundary around the batch, and the chain migrates when the prefill stack "
        "commits through `ContentMutationService`",
    ),
    "app.routers.wp_i_amortization::i1_amortization_calc": (
        "dedicated_router",
        "The I1 amortization-calculation endpoint; it delegates to the module-local `_execute`, "
        "which writes the computed schedule into `working_paper.parsed_data`, the same content "
        "shape as the other dedicated cycle-calculation routers Task 3 adjudicated",
        "This is a real content application, so it needs the unified boundary: read the current "
        "`content_revision`, apply, commit once through `ContentMutationService`; today the write "
        "lands outside that boundary",
    ),
    "app.routers.wp_i_amortization::i4_amortization_calc": (
        "dedicated_router",
        "The I4 amortization-calculation endpoint; like its I1 sibling it delegates to the "
        "module-local `_execute` that writes the schedule into `working_paper.parsed_data`",
        "Same obligation as `i1_amortization_calc`: one unified commit per calculation, replacing "
        "the current write outside the boundary",
    ),
    "app.services.event_handlers._impl::register_event_handlers._on_b515_high_risk": (
        "orchestrator_side_effect",
        "An EventBus handler registered inside `register_event_handlers`: on a B51-5 high fraud "
        "risk verdict it appends the D4 IPO workpapers by calling `_ensure_d4_ipo_loaded`, which "
        "Task 3 already adjudicated as `template_provisioning` -- the same shape as the sibling "
        "`_on_b514_high_risk` handler",
        "It holds no content of its own -- the lane statement is about the trigger, not the "
        "store. It must never move a version field (it moves none), and its commit has to become "
        "the provisioning call's commit instead of a second boundary opened by the handler",
    ),
    "app.services.guidance_runtime_facts::load_template_source_facts": (
        "export_storage_resolver",
        "Resolves the template source file by composing a path under the template tree itself so "
        "guidance runtime facts can be read back, the same template-lookup role as the "
        "`wp_template_finder` rows in this lane",
        "Reading template facts is not a content application, so no version field may move. The "
        "debt is the resolver split: it builds the path itself instead of going through the "
        "canonical resolver, which is why it is also counted in `non_canonical_resolver_only`",
    ),
    "app.services.wp_batch_prefill::batch_prefill": (
        "dedicated_router",
        "The batch prefill service; it delegates to `prefill_engine.batch_prefill_ordered`, a "
        "dedicated-router-lane writer, so the service shares that lane",
        "It inherits the lane through its delegate; it must not open a second boundary around the "
        "batch, and the chain migrates when the ordered prefill commits through "
        "`ContentMutationService`",
    ),
    "app.services.wp_batch_prefill::batch_prefill_project": (
        "dedicated_router",
        "The project-level batch prefill entry; it delegates to `batch_prefill` in the same "
        "module, so it shares the dedicated-router lane",
        "Same obligation as `batch_prefill`: no second boundary, migrates with the prefill stack",
    ),
    "app.services.wp_whole_workbook_document::whole_workbook_template_or_primary": (
        "export_storage_resolver",
        "Resolves the whole-workbook template (or the primary sheet's template) by delegating to "
        "`find_template_file_any`, the template-library lookup lane the `wp_template_finder` rows "
        "already occupy",
        "A template resolver applies no content, so no version field may move. It never reaches "
        "the canonical `resolve_wp_file`, which is why it is also counted in "
        "`non_canonical_resolver_only`",
    ),
    # 2026-11-03 清册重算（workpaper-html-onlyoffice-bidirectional-writeback-closure 修复批 A-3）：
    # 清册自 2026-09-24 起没再重生成，期间各 spec 新增的写入 / 解析行一直不在门的视野里。
    # 下面是规则表描述不准、必须逐行写清角色的那几条；其余新增行由模块规则覆盖。
    # 🔴 `AdjustmentService.update_entry` 曾在这里以一条单独 lane 裁决：它推进的是
    #    `Adjustment.content_revision`（调整分录组的 CAS 计数器），不是底稿版本。按「lane 不是
    #    豁免」的约定，这种误报应修在发现谓词里 —— 生成器 `_module_foreign_version_owners`
    #    现按模块事实把它判为另一聚合根的计数器，它不再进入清册，这里也就不需要裁决。
    "app.services.archive_inventory::_workpaper_entries": (
        "export_storage_resolver",
        "Archive packaging reads each workpaper's physical file through the canonical "
        "`resolve_wp_file` to place it into the archive zip; it serves bytes and applies no content",
        "Already on the canonical resolver, so the only obligation is to stay there: archiving a "
        "file the resolver would not return is how an archive diverges from the live project",
    ),
    "app.services.workpaper_file_backlog::classify": (
        "export_storage_resolver",
        "The read half of the lazy-file backlog: it asks the canonical `resolve_wp_file` whether a "
        "workpaper already owns a physical file before `_bind` / `apply_backlog` provision one",
        "A classification reads, it does not provision. It must keep using `resolve_wp_file` so the "
        "backlog and every reader agree on which workpapers still share the template file",
    ),
    "app.services.wp_generate_file::needs_own_file": (
        "export_storage_resolver",
        "Decides whether a workpaper must be detached from the shared template by resolving its "
        "current file through the canonical `resolve_wp_file`; it writes nothing",
        "Read-only predicate on the canonical resolver; the provisioning it gates lives in "
        "`detach_from_shared_template` / `bind_lazy_workpaper_file`",
    ),
    "app.services.wp_generation_staging::_source_paths": (
        "export_storage_resolver",
        "Staging collects the generation sources: the library template through "
        "`find_template_file_any` and the workpaper's existing file through `resolve_wp_file`, in "
        "one function",
        "Two resolver identities in one function is the `multi_resolver` shape SYNC-MULTI-RESOLVER "
        "has to clear; converging means one source-resolution entry that answers 'which bytes does "
        "generation start from'. It is new debt outside `wp_onlyoffice_router`",
    ),
    "app.services.attachment_upload_policy::resolve_local_attachment_file": (
        "export_storage_resolver",
        "Locates a local attachment or deliverable file from its recorded path, falling back to a "
        "`storage/`-relative path it composes itself (the same fallback the attachment download "
        "used before the C3 storage plan)",
        "Serving bytes moves no version field. The debt is the second locator: convergence means "
        "this fallback goes through `attachment_storage_resolver` like the download endpoints",
    ),
    # 公式运行时的底稿适配器两半写两种存储（2026-11-04 审计更正：上一版把两行都判成「不再碰
    # `checklist_responses`」，那是清册看不见 `text(<变量>)` 的盲区造成的误判，见
    # `writer_inventory_sql_bindings.py`）。apply 一半只把 parsed_data 目标写在自己身上，
    # checklist 目标交给 `_apply_checklist_group`（它自己的一行，checklist_response_store）；
    # restore 一半两种目标都在自己身上写。
    "app.services.formula_runtime.adapters.workpaper::WorkpaperMutationAdapter.apply_many": (
        "dedicated_router",
        "The formula-runtime workpaper adapter's apply entry point writes parsed_data targets in "
        "place through `wp_parsed_data_service.write_cell_to_parsed_data`, the shared "
        "`working_paper.parsed_data` cell writer the dedicated-router lane owns; checklist targets "
        "are grouped per workpaper and handed to `_apply_checklist_group`, which is its own "
        "`checklist_response_store` row",
        "It flushes on the caller's session and opens no boundary of its own, so its parsed_data "
        "half migrates when the shared cell writer commits through `ContentMutationService`; the "
        "checklist half is `_apply_checklist_group`'s obligation",
    ),
    "app.services.formula_runtime.adapters.workpaper::WorkpaperMutationAdapter.restore_many": (
        "checklist_response_store",
        "The undo half of the same adapter writes both content stores itself: checklist targets "
        "are restored by a raw `UPDATE checklist_responses` of `remark` or `conclusion` (the "
        "statement is bound to a local name first, which hid it from this inventory until the "
        "2026-11-04 binding fix), parsed_data targets through "
        "`wp_parsed_data_service.write_cell_to_parsed_data`",
        "Both halves have to migrate: the checklist half waits for the unified protocol to own a "
        "`checklist_responses` content scope (Task 74's second half), the parsed_data half rides "
        "the shared cell writer's unified commit",
    ),
    "app.services.bulk_tab.bulk_async_runner::spool_import_upload": (
        "upload_import",
        "Spools an uploaded bulk-tab ZIP to a staging path under the storage tree it composes "
        "itself, before the durable import job reads it",
        "The spool holds an upload, not workpaper content, so no revision may move here; the "
        "content write happens later in `durable_job_executor.execute_bulk_import`",
    ),
    "app.services.custom_query.query_artifacts::SealResult.__init__": (
        "read_only_evaluation",
        "A result DTO constructor for custom-query artifact sealing: its `file_path` attribute "
        "describes the staged artifact returned to the caller, not a `WorkingPaper` model or a "
        "database content store, and the constructor performs no session, SQL, or artifact I/O",
        "Nothing to migrate. The discovery predicate matches the generic `file_path` attribute "
        "name on an in-memory result object; keep this row in the read-only evaluation lane so "
        "the false-positive is explicit rather than silently treated as a persisted workpaper write",
    ),
}
