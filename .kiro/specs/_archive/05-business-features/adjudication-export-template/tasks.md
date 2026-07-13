# Implementation Plan

## Overview

实现审定表导出模板动态生成器，覆盖全部 D~N 审定表（`^[A-N]\d+-1$`），通过统一的 `AdjudicationExportTemplateService` 动态生成含多行合并表头、编制说明 sheet、行骨架的空白 xlsx 模板。

## Tasks

- [x] 1. Create `backend/app/services/adjudication_export_template_service.py` with class skeleton and `is_adjudication_table(wp_code)` regex matcher
  - [x] 1.1 Implement `_get_aging_subject(wp_code)` to extract aging subject prefix (D2/D3/F1/K1/K3/G5)
  - [x] 1.2 Implement `_get_row_skeleton(template_file_path, wp_code)` using `extract_audit_rows`
- [x] 2. Implement multi-row merged header builder `_build_multi_row_header`
  - [x] 2.1 Row 2 level-1 headers with horizontal merges: "期初"(4 cols) and "期末"(4 cols)
  - [x] 2.2 Row 3 level-2 headers: "未审"/"AJE"/"RJE"/"审定" ×2 under 期初 and 期末
  - [x] 2.3 Vertical merges for "项目"/"变动额"/"变动率"/"原因分析" spanning rows 2-3
  - [x] 2.4 Apply bold font, center alignment, and thin border styles to header cells
- [x] 3. Implement aging dynamic columns integration
  - [x] 3.1 Integrate `resolve_aging_segments` and `build_aging_headers` for aging wp_codes (D2/D3/F1/K1/K3/G5)
  - [x] 3.2 Insert aging column headers between "期末审定" and "变动额" in the multi-row header
  - [x] 3.3 Handle fallback to default preset segments when AgingConfig resolution fails
- [x] 4. Implement instruction sheet builder `_build_instruction_sheet`
  - [x] 4.1 Column meaning table (项目/期初四列/期末四列/变动额/变动率/原因分析)
  - [x] 4.2 Read-only column identification with auto-calc formulas (审定=未审+AJE+RJE, 变动额=期末审定-期初审定, 变动率=变动额/期初审定)
  - [x] 4.3 Fill rules description (user fills 未审/AJE/RJE + 原因分析)
  - [x] 4.4 Import notes (row matching by item name, read-only columns ignored, empty rows skipped)
- [x] 5. Implement `generate()` async orchestrator and `_build_data_sheet`
  - [x] 5.1 Compose data sheet: title row + multi-row header + row skeleton
  - [x] 5.2 Fill row_skeleton items into project column (from row 4), bold for section/total rows
  - [x] 5.3 Return `(io.BytesIO, filename)` with filename format `{wp_code}_{wp_name}审定表_模板.xlsx`
- [x] 6. Modify `wp_render_config.export_template()` route to add adjudication branch
  - [x] 6.1 Add wp_code regex check, call `AdjudicationExportTemplateService.generate()` for matches
  - [x] 6.2 Return StreamingResponse via `workbook_to_response` with RFC5987 Content-Disposition
  - [x] 6.3 Preserve original FileResponse path for non-adjudication wp_codes (zero regression)
- [x] 7. Write Property-Based Tests (Hypothesis)
  - [x] 7.1 PBT for Property 1: `is_adjudication_table` correctness for generated wp_code strings
  - [x] 7.2 PBT for Property 4+9: column count = 12 (non-aging) or 12+N×P (aging) with generated segments
  - [x] 7.3 PBT for Property 2+3: sheet structure and header values for random valid wp_codes
  - [x] 7.4 PBT for Property 10+11: merged_cells correctness and xlsx validity
- [x] 8. Write integration and edge case tests
  - [x] 8.1 Test Property 6: RFC5987 Content-Disposition header with Chinese characters
  - [x] 8.2 Test Property 7: non-adjudication wp_codes return FileResponse unchanged
  - [x] 8.3 Test Property 5: row skeleton order matches extract_audit_rows for real D1 template
  - [x] 8.4 Test Property 8: instruction sheet contains all required sections
  - [x] 8.5 Edge case: template_file_path missing → template with empty project column
  - [x] 8.6 Edge case: aging config failure → fallback to default preset segments

## Notes

- 复用 `_cycle_import_export_common.workbook_to_response` 处理 RFC5987 中文文件名
- 复用 `_cycle_import_export_common.resolve_aging_segments` + `build_aging_headers` 处理账龄列
- 复用 `wp_audit_sheet_extract.extract_audit_rows` 提取行骨架
- PBT 使用 `@settings(max_examples=5)` 遵循测试提速铁律
- Service 为只读无写库，不需要 flush/commit

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave-1", "tasks": ["1"], "description": "Core module skeleton" },
    { "id": "wave-2", "tasks": ["2", "3", "4"], "description": "Parallel: headers, aging, instruction" },
    { "id": "wave-3", "tasks": ["5"], "description": "Compose generate() orchestrator" },
    { "id": "wave-4", "tasks": ["6"], "description": "Route integration" },
    { "id": "wave-5", "tasks": ["7", "8"], "description": "PBT + integration tests" }
  ]
}
```
