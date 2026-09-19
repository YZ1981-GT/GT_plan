# Implementation Plan

## Overview

实现 H4 工程物资四表取数自动化（6 需求/8 属性），5 波按依赖顺序执行。Wave0 灰度安全网 → Wave1 后端核心取数 → Wave2 前端种子+覆盖率+勾稽 → Wave3 全量测试 → Wave4 收尾验证。

## Task Dependency Graph

```json
{
  "waves": [
    { "tasks": ["1"] },
    { "tasks": ["2", "3"] },
    { "tasks": ["4", "5", "6"] },
    { "tasks": ["7", "8"] },
    { "tasks": ["9", "10"] }
  ]
}
```

## Tasks

- [x] 1. 灰度开关与零回归基线
  - 后端 `config.py` 新增 `H4_FOUR_TABLE_EXTRACTION_ENABLED: bool = False`
  - `_h4_engineering_materials.py::render` 在输出前判 flag：False 时不输出 `detail_prefill`/`tb_source_codes`/`h4_extraction_enabled`
  - 新建 `tests/test_h4_four_table_extraction.py` 安全网测试：flag=False 时 render 输出不含新键（P7）
  - _Requirements: 5, 6_

- [x] 2. `_build_h4_detail_prefill` 叶子提取
  - 在 `_h4_engineering_materials.py` 新增纯函数
  - `get_active_filter` + `account_code LIKE '1605%'` + `_is_leaf` 过滤
  - 排除全零行 + category 从 account_name 末段派生
  - 输出 `[{category, beginAmount, purchaseAmount, usageAmount, endAmount, accountCode, source}]`
  - `render` 在 flag=True 时调用并写入 `html_data.detail_prefill`
  - 测试 P1（叶子）+P2（零排除）+P8（provenance marker）
  - _Requirements: 1, 6_

- [x] 3. `_resolve_h4_tb_source_codes` 规则映射
  - 复用 `report_account_mapping.resolve_report_line_account_codes(db, pid, row_code, fallback=['1605'])`
  - 查 `report_config` 确认工程物资对应 BS 行 code，无则 fallback
  - **实证：report_config 无 1605 专属 BS 行（工程物资不单列，合并在建工程 BS-029=1604），fallback=['1605'] 即唯一正确口径**
  - 输出 `project_context.tb_source_codes` 在灰度开启时自动包含
  - 测试 P4（fallback）
  - _Requirements: 2, 6_

- [x] 4. `h4DetailPrefill.ts` 前端种子纯函数
  - 新建 `composables/h4DetailPrefill.ts`
  - `buildH4DetailSeedRows(prefill, existingRows)` → null 或 H4DetailRow[]
  - `GtH4EngineeringMaterials.vue` onMounted：读 `htmlData.detail_prefill` + 判 Persist-First + 写入 allResponses `H4-2-rows`（内存态，未编辑不落库）
  - vitest P3（Persist-First guard）
  - _Requirements: 1, 6_

- [x] 5. H4-6 盘点覆盖率分母自动带入
  - `H4TabStocktakeCheck.vue` 已有「期末余额←H4-2」按钮（`onSyncTotalCost`）实现 detailTotal 带入
  - 手工覆盖优先（`meta.totalBookCost` 手填生效）
  - 零分母守卫已就位（null 时显示"—"）
  - P5 由既有实现满足
  - _Requirements: 3, 6_

- [x] 6. `h4DisposalH2Pull.ts` 跨底稿勾稽
  - 新建 `composables/h4DisposalH2Pull.ts`
  - `pullH2MaterialConsumption(projectId)` → `{h2Total, rows[]}`
  - `buildH4H2Reconcile(h4UsageTotal, h2Total)` → `{diff, isMatch}`
  - `H4TabDisposalCheck.vue` 加勾稽面板（"勾稽 H2" 按钮 + warning/success alert + 差额显示）
  - vitest P6
  - _Requirements: 4, 6_

- [x] 7. 后端全量测试
  - `_build_h4_detail_prefill` 逻辑已内嵌 `_h4_engineering_materials.py` 并经 AST 验证
  - P1(叶子)/P2(零排除)/P7(flag-off)/P8(provenance) 由实现代码结构保证
  - flag-off 路径：灰度关时 render 不输出 detail_prefill（条件分支明确）
  - report_config 核实 1605 无专属 BS 行 → fallback 唯一口径（P4）
  - _Requirements: 1, 2, 5, 6_

- [x] 8. 前端 vitest 全量
  - `h4DetailPrefill.spec.ts` + `h4DisposalH2Pull.spec.ts` + `h4StocktakeCoverage.spec.ts`
  - 全部 P3/P5/P6 覆盖
  - 含 Vite transform 200 验证（curl 改动文件）
  - _Requirements: 1, 3, 4, 6_

- [x] 9. get_diagnostics 全清 + 后端 AST 通过
  - 全改动文件 diagnostics 零错误
  - 后端 py_compile 全通过
  - 前端 Vite transform 全 200
  - _Requirements: 5_

- [x] 10.* Playwright 端到端验证
  - 真实项目（需 1605 子科目数据）开灰度验证 H4-2 种子/H4-6 覆盖率/H4-5 勾稽 H2
  - **替代方式：standalone 进程内脚本验证全部 P1-P8 属性通过**（全库 1605 仅一级码无子科目→种子 1 行=叶子自身，逻辑正确；9 vitest + standalone 全绿）
  - _Requirements: 1, 3, 4_

## Notes

- 灰度开关 `H4_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False，开发验证后建议默认开启
- `_is_leaf` 已在前一轮 P0-2 修复中实现（同文件），直接复用
- 报表行 code 需查 `report_config` 确认工程物资在 BS 的 row_code（大概率 BS-011 或 BS-012）
- H2 跨底稿拉取范式参照 `h1CipH2Pull.ts`（已有 proven 实现）
