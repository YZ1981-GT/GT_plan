"""底稿管理路由注册 — 按 6 大聚合组 + 辅助组循环注册

分组方案（design §7.1）：
  模板管理: wp_template / wp_template_metadata / wp_template_files / wp_template_download / wp_template_version
  生命周期: working_paper / workpaper_batch_status / wp_batch_ops / wp_progress / wp_prerequisite_status / wp_procedure_status
  复核:     wp_review / wp_review_status / wp_cell_annotations / review_records_global / wp_eqcr_evaluation
  渲染:     wp_render_config / wp_classification / wp_html_save / wp_xlsx_export / wp_index_resolve / wp_trace / wp_disclosure_sync
  数据:     formula / wp_mapping / wp_data_rules / wp_prefill_context / wp_prefill_preview / wp_user_formulas / wp_cross_check / wp_dependencies / sampling / sampling_enhanced / aging_analysis / data_fetch_custom
  搜索:     wp_search / wp_version_search / global_search / wp_health_dashboard
  程序管理: wp_procedures / wp_procedure_trim / wp_step_mapping / wp_evidence
  AI与辅助: wp_ai / wp_ai_confirm / wp_chat / wp_explanation
  其他:     qc / wp_storage / wp_download / workpaper_summary / process_record / review_conversations / annotations / background_jobs / wp_data_rules / excel_html / wp_structure / wp_manuals / wp_fine_rules
"""
from fastapi import FastAPI


def register_workpaper_routers(app: FastAPI) -> None:
    """注册底稿管理相关路由（6 大聚合组 + 辅助组，循环注册）"""
    from app.routers.wp_template import router as wp_template
    from app.routers.wp_template_metadata import router as wp_template_metadata
    from app.routers.wp_template_files import router as wp_template_files
    from app.routers.wp_template_download import router as wp_template_download
    from app.routers.wp_template_version import router as wp_template_version
    from app.routers.working_paper import router as working_paper
    from app.routers.workpaper_batch_status import router as workpaper_batch_status
    from app.routers.wp_batch_ops import router as wp_batch_ops
    from app.routers.wp_progress import router as wp_progress
    from app.routers.wp_prerequisite_status import router as wp_prerequisite_status
    from app.routers.wp_procedure_status import router as wp_procedure_status
    from app.routers.wp_procedure_status import categories_router as wp_procedure_categories
    from app.routers.wp_review import router as wp_review
    from app.routers.wp_review_status import router as wp_review_status
    from app.routers.wp_cell_annotations import router as wp_cell_annotations
    from app.routers.review_records_global import router as review_records_global
    from app.routers.wp_eqcr_evaluation import router as wp_eqcr_evaluation
    from app.routers.wp_render_config import router as wp_render_config
    from app.routers.wp_classification import router as wp_classification
    from app.routers.wp_html_save import router as wp_html_save
    from app.routers.wp_xlsx_export import router as wp_xlsx_export
    from app.routers.wp_index_resolve import router as wp_index_resolve
    from app.routers.wp_trace import router as wp_trace
    from app.routers.wp_disclosure_sync import router as wp_disclosure_sync
    from app.routers.formula import router as formula
    from app.routers.wp_mapping import router as wp_mapping
    from app.routers.wp_data_rules import router as wp_data_rules
    from app.routers.wp_prefill_context import router as wp_prefill_context
    from app.routers.wp_prefill_preview import router as wp_prefill_preview
    from app.routers.wp_user_formulas import router as wp_user_formulas
    from app.routers.wp_cross_check import router as wp_cross_check
    from app.routers.wp_dependencies import router as wp_dependencies
    from app.routers.sampling import router as sampling
    from app.routers.sampling_enhanced import router as sampling_enhanced
    from app.routers.aging_analysis import router as aging_analysis
    from app.routers.data_fetch_custom import router as data_fetch_custom
    from app.routers.wp_search import router as wp_search
    from app.routers.wp_version_search import router as wp_version_search
    from app.routers.global_search import router as global_search
    from app.routers.wp_health_dashboard import router as wp_health_dashboard
    from app.routers.wp_procedures import router as wp_procedures
    from app.routers.wp_procedure_trim import router as wp_procedure_trim
    from app.routers.wp_step_mapping import router as wp_step_mapping
    from app.routers.wp_evidence import router as wp_evidence
    from app.routers.wp_ai import router as wp_ai
    from app.routers.wp_ai_confirm import router as wp_ai_confirm
    from app.routers.wp_chat import router as wp_chat
    from app.routers.wp_explanation import router as wp_explanation
    from app.routers.qc import router as qc
    from app.routers.wp_storage import router as wp_storage
    from app.routers.wp_download import router as wp_download
    from app.routers.workpaper_summary import router as workpaper_summary
    from app.routers.process_record import router as process_record
    from app.routers.review_conversations import router as review_conversations
    from app.routers.annotations import router as annotations
    from app.routers.background_jobs import router as background_jobs
    from app.routers.excel_html import router as excel_html
    from app.routers.wp_structure import router as wp_structure
    from app.routers.wp_manuals import router as wp_manuals
    from app.routers.wp_fine_rules import router as wp_fine_rules
    from app.routers.wp_offline import router as wp_offline
    from app.routers.wp_audit_flow_graph import router as wp_audit_flow_graph
    from app.routers.wp_sheet_lock import router as wp_sheet_lock
    from app.routers.standard_conversion import router as standard_conversion
    from app.routers.attachment_lineage import router as attachment_lineage
    from app.routers.wp_functional_actions import router as wp_functional_actions
    from app.routers.wp_formula import router as wp_formula

    groups = {
        # ── 6 大聚合组（design §7.1）──
        "模板管理": [wp_template, wp_template_metadata, wp_template_files, wp_template_download, wp_template_version],
        "生命周期": [working_paper, workpaper_batch_status, wp_batch_ops, wp_progress, wp_prerequisite_status, wp_procedure_status, wp_procedure_categories],
        "复核": [wp_review, wp_review_status, wp_cell_annotations, review_records_global, wp_eqcr_evaluation],
        "渲染": [wp_render_config, wp_classification, wp_html_save, wp_xlsx_export, wp_index_resolve, wp_trace, wp_disclosure_sync],
        "数据": [formula, wp_mapping, wp_data_rules, wp_prefill_context, wp_prefill_preview, wp_user_formulas, wp_formula, wp_cross_check, wp_dependencies, sampling, sampling_enhanced, aging_analysis, data_fetch_custom],
        "搜索": [wp_search, wp_version_search, global_search, wp_health_dashboard],
        # ── 辅助组 ──
        "程序管理": [wp_procedures, wp_procedure_trim, wp_step_mapping, wp_evidence],
        "AI与辅助": [wp_ai, wp_ai_confirm, wp_chat, wp_explanation],
        "其他": [qc, wp_storage, wp_download, workpaper_summary, process_record, review_conversations, annotations, background_jobs, excel_html, wp_structure, wp_manuals, wp_fine_rules, wp_offline, wp_audit_flow_graph, wp_sheet_lock, standard_conversion, attachment_lineage, wp_functional_actions],
    }

    for tag, routers in groups.items():
        for r in routers:
            app.include_router(r, tags=[tag])
