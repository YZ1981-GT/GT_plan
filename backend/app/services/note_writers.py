"""DisclosureNote 写入方登记表。

当前阶段只冻结事实，不执行唯一写方拦截。D1 拍板后，所有权矩阵在本登记表上
按 ``(template_type, note_section, table_key, field_key)`` 绑定 writer_id。
"""
from __future__ import annotations

from dataclasses import dataclass

CANONICAL_FIELDS = frozenset({
    "table.rows.values",
    "table.sub_table_data",
    "table._tables",
    "table.structure",
    "table.formulas",
    "table.user_formulas",
    "text_content",
    "stale_state",
})


@dataclass(frozen=True)
class NoteWriterSpec:
    writer_id: str
    entrypoint: str
    trigger: str
    fields: tuple[str, ...]
    respects_cell_modes: bool
    transaction: str = "caller"
    template_types: tuple[str, ...] = ("listed", "soe")
    status: str = "active"


def _w(
    writer_id: str,
    entrypoint: str,
    trigger: str,
    fields: tuple[str, ...],
    respects_cell_modes: bool,
    transaction: str = "caller",
) -> NoteWriterSpec:
    return NoteWriterSpec(
        writer_id=writer_id,
        entrypoint=entrypoint,
        trigger=trigger,
        fields=fields,
        respects_cell_modes=respects_cell_modes,
        transaction=transaction,
    )


_TABLE = ("table.rows.values", "table._tables", "table.structure")
_TEXT = ("text_content",)

NOTE_WRITERS: tuple[NoteWriterSpec, ...] = (
    _w("manual_editor", "app.services.disclosure_engine:DisclosureEngine.update_note", "附注编辑器手工保存", _TABLE + _TEXT, True),
    _w("manual_editor_route", "app.routers.disclosure_notes:update_note._mutate", "附注编辑端点", _TABLE + _TEXT, True),
    _w("ai_adopt", "app.routers.ai_content:_writeback_note", "AI 内容采纳", _TEXT, True),
    # spec llm-linkage-audit-practice-closure ADR-LLM-016：确认时按基线版本 / before hash 应用预览过的正文，撤销时还原
    _w("ai_draft_apply", "app.services.draft_artifact_facade:apply_note_artifact", "AI 待确认草稿确认写回", _TEXT, True),
    _w("ai_draft_undo", "app.services.draft_artifact_facade:undo_note_artifact", "AI 草稿写回撤销", _TEXT, True),
    _w("excel_html", "app.routers.excel_html:save_edits", "Excel HTML 保存", _TABLE, True),
    _w("triple_format", "app.services.triple_format_adapter:DisclosureNoteAdapter.update_note_from_structure", "三格式适配写回", _TABLE, True),
    _w("writeback_text", "app.services.writeback_target_adapters:DisclosureNoteAdapter.write_upstream", "交付件正文回写", _TEXT, True),
    _w("generate_notes", "app.services.disclosure_engine:DisclosureEngine.generate_notes", "附注生成/重生成", _TABLE + _TEXT, True),
    _w("update_note_values", "app.services.disclosure_engine:DisclosureEngine.update_note_values", "附注增量更新", _TABLE, True),
    _w("binding_refill", "app.services.disclosure_engine:DisclosureEngine.refill_sections", "绑定取数刷新", ("table.rows.values", "table._tables"), True),
    _w("binding_formula_route", "app.routers.note_wp_mapping:refresh_all_bindings", "绑定刷新后的公式求值", ("table.rows.values", "table._tables", "table.formulas"), True),
    _w("read_time_rebuild", "app.services.disclosure_engine:DisclosureEngine.get_note_detail", "详情读取时修复空表", _TABLE, True, "own_commit"),
    _w("formula_push", "app.services.formula_push.engine:_push_note", "底稿公式推送", ("table.rows.values", "table._tables"), True),
    _w("formula_runtime_apply", "app.services.formula_runtime.adapters.note:NoteMutationAdapter.apply_many", "公式运行应用", ("table.rows.values",), True),
    _w("formula_runtime_restore", "app.services.formula_runtime.adapters.note:NoteMutationAdapter.restore_many", "公式运行回滚", ("table.rows.values",), True),
    _w("formula_settings_materialize", "app.services.formula_settings.note_settings:materialize", "公式设置物化", ("table.user_formulas",), True),
    _w("formula_executor", "app.services.note_formula_generator:execute_note_formulas", "附注公式执行", ("table.rows.values", "table.formulas", "table.user_formulas"), True),
    _w("report_sync", "app.services.report_note_sync_service:ReportNoteSyncService._sync_real", "报表同步附注", ("table.rows.values",), True),
    _w("workpaper_sync", "app.services.wp_disclosure_sync_service:sync_from_workpaper", "底稿披露表同步", ("table.sub_table_data", "table._tables", "text_content"), True, "optional_commit"),
    _w("workpaper_html_sync", "app.services.wp_disclosure_sync_service:WpDisclosureSyncService.sync_from_html", "HTML 底稿披露同步", ("table.sub_table_data", "table._tables"), True, "own_commit"),
    _w("workpaper_pull_mark", "app.services.note_workpaper_pull_service:_mark_synced_sections", "从底稿拉取后记来源", ("table.structure",), True),
    _w("group_baseline", "app.services.group_note_baseline_service:GroupNoteBaselineService.apply_baseline", "集团基线下发", _TABLE + _TEXT, True),
    _w("group_template", "app.services.note_group_template_service:NoteGroupTemplateService._upsert_section", "集团模板下发", _TABLE + _TEXT, False),
    _w("consol_template_push", "app.services.consol_note_template_push_service:_push_to_one", "合并模板下推子企业", _TABLE, True),
    _w("prior_year_import", "app.services.note_prior_year_import_service:NotePriorYearImportService.import_from_docx", "上年附注导入", _TABLE + _TEXT, True),
    _w("prior_year_inherit", "app.services.note_prior_year_import_service:NotePriorYearImportService.inherit_from_prior_year", "上年正文继承", _TEXT, True),
    _w("offline_import", "app.services.note_offline_import_tables:persist_applied_table_data", "离线附注导入", _TABLE, True),
    _w("text_batch", "app.services.note_text_batch_apply:apply_batch", "正文批量编制", _TEXT, True),
    _w("cross_reference", "app.services.note_cross_reference_service:NoteCrossReferenceService.update_all_references", "正文交叉引用刷新", _TEXT, True),
    _w("template_reflow", "app.services.note_template_reflow_service:apply_reflow_section", "模板结构重排", _TABLE, True, "optional_commit"),
    _w("project_realign", "app.services.note_project_realign_apply:apply_table_realignment", "项目附注结构重对齐", _TABLE, True),
    _w("standard_conversion_restore", "app.services.note_conversion_service:NoteConversionService._restore_note_from_snapshot", "准则切换还原", _TABLE, True),
    _w("standard_conversion_map", "app.services.note_conversion_service:NoteConversionService._map_disclosure_notes", "准则切换映射", _TABLE, True),
    _w("auto_trim", "app.services.note_trim_service:NoteTrimService.auto_trim_v2", "附注自动裁剪", _TABLE, True),
    _w("cell_mode", "app.services.note_wp_mapping_service:NoteWpMappingService.toggle_cell_mode", "切换手工/自动格", ("table.structure", "table.rows.values"), True),
    _w("clear_formulas", "app.services.note_wp_mapping_service:NoteWpMappingService.clear_formulas", "清除公式", ("table.structure",), True),
    _w("restore_auto", "app.services.note_wp_mapping_service:NoteWpMappingService.restore_auto_mode", "恢复自动模式", ("table.structure",), True),
    _w("stale_mark", "app.services.stale_state:mark_note_stale", "下游数据变化", ("stale_state",), True),
    _w("stale_clear", "app.services.stale_state:clear_note_stale", "完整重算成功", ("stale_state",), True),
)

# AST 会看到但不会持久化的对象；测试会验证这些入口仍保持只读/纯 DTO。
NOTE_WRITER_EXCLUSIONS: dict[str, str] = {
    "app.routers.disclosure_notes:get_note_detail": "只修改响应投影，函数内不 flush/commit",
    "app.services.deliverable_refresh_service:_EmptyNote.__init__": "仅构造内存 DTO，不是 ORM DisclosureNote",
    "app.services.a17_word_exporter:_html_to_docx._DocxHtmlParser.__init__": "DOCX HTML 解析器的内存表格缓存，不是 ORM 字段",
    "app.services.a17_word_exporter:_html_to_docx._DocxHtmlParser.handle_starttag": "DOCX HTML 解析器收集表格节点，不接触数据库",
    "app.services.note_md_template_parser:NoteMDTemplateParser._parse_content": "Markdown 模板解析结果 DTO，不是项目附注 ORM",
}

NOTE_WRITER_SCAN_BLIND_SPOTS: dict[str, str] = {
    "app.services.note_offline_import_tables:persist_applied_table_data": (
        "通过 values(**动态字典) 写 table_data，静态字段扫描看不到；入口与写入字段另由单测验证"
    ),
}

FRONTEND_BUILDER_AUTHORITY = (
    "audit-platform/frontend/src/views/composables/__tests__/noteHeadlessDisclosureCoverage.spec.ts"
)


def writer_by_id(writer_id: str) -> NoteWriterSpec | None:
    return next((item for item in NOTE_WRITERS if item.writer_id == writer_id), None)


__all__ = [
    "CANONICAL_FIELDS",
    "FRONTEND_BUILDER_AUTHORITY",
    "NOTE_WRITERS",
    "NOTE_WRITER_EXCLUSIONS",
    "NOTE_WRITER_SCAN_BLIND_SPOTS",
    "NoteWriterSpec",
    "writer_by_id",
]
