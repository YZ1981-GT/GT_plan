# ADR-CONSOL-302: 附注 provenance 在 V2 汇总时写入（依赖 Phase 2 V2）

## 状态
已接受 (2026-05-31)

## 背景

附注穿透要反查"该合并章节由哪些子公司哪些章节汇总而来"，必须在 V2 `generate_full_consol_notes` 汇总时同步写 `disclosure_notes.consolidation_breakdown`（事后无法重建）。

## 决策

- `disclosure_notes` 加 `source_project_id UUID` + `consolidation_breakdown JSONB`（迁移 V039 + ORM `Mapped` + service 读写，三层一致 T6）。
- V2 `generate_full_consol_notes` 汇总每章节时调 `_build_section_consolidation_breakdown` 写 provenance：
  ```json
  {"by_company": [{"source_project_id", "company_code", "company_name", "section_title", "amount"}], "computed_at": "..."}
  ```
- 附注穿透端点 `note_consol_drilldown_service.get_note_consol_breakdown` 直接读 `consolidation_breakdown`。
- 无 V2 / 无 breakdown 时穿透返回空 + 中文提示"该章节暂无合并明细，请先用 V2 生成合并附注"（EH1/EH3）。

## 后果

- 正向：附注穿透有数据基础 + 与报表穿透对称；provenance 自洽（Σ by_company amount == 章节汇总值，T2 hypothesis 守门）。
- 代价：附注穿透真实可用以 V2 启用为前提（R1）；V2 输出落 `disclosure_notes` 的接线依赖 Phase 2（当前 provenance 已附在 V2 章节 dict 上，待 Phase 2 落库路径消费）。
