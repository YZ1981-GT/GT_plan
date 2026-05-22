"""报表与附注路由注册

覆盖原 router_registry.py 中以下分组：
  §4  报表与附注（report_config/reports/cfs/disclosure_notes/audit_report/export/...）
  §44 报表 Excel 导出
  §45 附注 Word 导出
  §46 附注国企版↔上市版互转
  §47 附注高级功能（上年导入/交叉引用/变动分析）
  §48 Sprint 10：集团模板继承与下发
  §49 Sprint 10：附注章节锁定
  §50 Sprint 10：报表附注数据锁定与版本快照
  §52 Sprint 10：附注章节模板可扩展性
  §92 Phase 3 F1 双向穿透：附注来源追溯
  §93 Phase 3 F1.2 双向穿透：报表行构成科目
  §94 Phase 4 F2: 多年度对比分析
"""
from fastapi import FastAPI


def register_report_routers(app: FastAPI) -> None:
    """注册报表与附注相关路由"""

    # ═══ §4. 报表与附注 ═══
    from app.routers.report_config import router as rc_router
    from app.routers.reports import router as reports_router
    from app.routers.cfs_worksheet import router as cfs_router
    from app.routers.disclosure_notes import router as dn_router
    from app.routers.audit_report import router as ar_router
    from app.routers.export import router as export_router
    from app.routers.note_templates import router as nt_router
    from app.routers.note_wp_mapping import router as nwm_router
    from app.routers.note_trim import router as ntr_router
    from app.routers.note_ai import router as nai_router
    from app.routers.report_trace import router as rt_router
    from app.routers.word_export import router as word_export_router
    from app.routers.report_mapping import router as report_mapping_router

    for r in [rc_router, reports_router, cfs_router, dn_router, ar_router,
              export_router, nt_router, nwm_router, ntr_router, nai_router,
              rt_router, word_export_router, report_mapping_router]:
        app.include_router(r, tags=["报表与附注"])

    # ═══ §44. 报表 Excel 导出 ═══
    from app.routers.report_export import router as report_export_router
    app.include_router(report_export_router, tags=["report-export"])

    # ═══ §45. 附注 Word 导出 ═══
    from app.routers.note_export import router as note_export_router
    app.include_router(note_export_router, tags=["note-export"])

    # ═══ §46. 附注国企版↔上市版互转 ═══
    from app.routers.note_conversion import router as note_conversion_router
    app.include_router(note_conversion_router, tags=["note-conversion"])

    # ═══ §47. 附注高级功能（上年导入/交叉引用/变动分析） ═══
    from app.routers.note_advanced import router as note_advanced_router
    app.include_router(note_advanced_router, tags=["note-advanced"])

    # ═══ §48. Sprint 10：集团模板继承与下发 ═══
    from app.routers.note_group_template import router as note_group_template_router
    app.include_router(note_group_template_router, tags=["note-group-template"])

    # ═══ §49. Sprint 10：附注章节锁定（多人协作） ═══
    from app.routers.note_section_lock import router as note_section_lock_router
    app.include_router(note_section_lock_router, tags=["note-section-lock"])

    # ═══ §50. Sprint 10：报表附注数据锁定与版本快照 ═══
    from app.routers.note_data_lock import router as note_data_lock_router
    app.include_router(note_data_lock_router, tags=["note-data-lock"])

    # ═══ §52. Sprint 10：附注章节模板可扩展性 ═══
    from app.routers.note_custom_section import router as note_custom_section_router
    app.include_router(note_custom_section_router, tags=["note-custom-section"])

    # ═══ §92. Phase 3 F1 双向穿透：附注来源追溯 ═══
    from app.routers.note_trace import router as note_trace_router
    app.include_router(note_trace_router, tags=["note-trace"])

    # ═══ §93. Phase 3 F1.2 双向穿透：报表行构成科目 ═══
    from app.routers.reports import line_composition_router
    app.include_router(line_composition_router, tags=["report-line-composition"])

    # ═══ §94. Phase 4 F2: 多年度对比分析 ═══
    from app.routers.reports import multi_year_router
    app.include_router(multi_year_router, tags=["multi-year-compare"])
