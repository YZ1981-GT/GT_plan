# Implementation Plan

## Overview

7 波推进，波与波之间可独立发布/回退：W0 建灰度开关与零回归基线 → W1 G7 侧联动入口（纯 UI 复用既有端点，收益最快）→ W2 G7-2 四表取数（后端端点 + 前端映射）→ W3 G7-1 分类核对与 G7-14 跨册带入 → W4 抽凭铺开 → W5 stale 常驻 + G7-4 反向补录 → W6 属性/集成测试与零回归门。

设计已定的两处落点纠偏必须遵守：**不给 G7-1 加「从 G7-2 带入」按钮**（G7-1 是 G7-2 的自动投影，见 design Decision 1）；**G7-14 带入目标是 G7-2 权益法行**（Decision 2）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "parallel": true },
    { "wave": 1, "tasks": ["2.1", "2.2"], "parallel": false },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "parallel": false },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3"], "parallel": false },
    { "wave": 4, "tasks": ["5.1"], "parallel": false },
    { "wave": 5, "tasks": ["6.1", "6.2"], "parallel": true },
    { "wave": 6, "tasks": ["7.1", "7.2", "7.3"], "parallel": false },
    { "wave": 7, "tasks": ["8.1", "8.2"], "parallel": false }
  ]
}
```

## Tasks

- [x] 1. Wave 0：灰度开关与零回归基线
- [x] 1.1 新增灰度开关 `G7_FOUR_TABLE_EXTRACTION_ENABLED`
  - `backend/app/core/config.py` 追加 `G7_FOUR_TABLE_EXTRACTION_ENABLED: bool = False`
  - 单测 `tests/g7_extraction/test_g7_config_flag.py`（3 passed）
  - _Requirements: 2.6, 9.1_

- [x] 1.2 建零回归基线（characterization）
  - 后端 `tests/g7_extraction/test_g7_characterization.py`（8 passed）：`_is_leaf`/`_sum_leaf_by_prefix` 叶子无双算 + `g7_consol_linkage_service` 签名/语义常量（Property 1/15）
  - 基线命令 `python -m pytest tests/g7_extraction -q`
  - _Requirements: 9.2, 9.4, 3.5_

- [x] 2. Wave 1：G7 底稿侧发起合并联动
- [x] 2.1 新增 `useG7ConsolLinkageEntry` + 入口弹窗
  - 新建 `composables/g7ConsolLinkageEntry.ts`：`openPreview()` 调既有 `previewG7Linkage`、`confirmImport()` 调既有 `importG7Linkage` 并透传最近一次 preview 的 `expected_versions`；409 → 提示 + 自动重新 preview（**不重试写入**）；422 → 显示后端 detail 原文；`gotoConsolidation()` 跳合并工作底稿
  - 新建 `G7ConsolLinkageEntryDialog.vue`：预览摘要（四表可导入/候选数、未匹配主体、建议草稿条数、stale 提示）+ 确认导入（`:disabled="isReadonly || !canEdit"`）
  - 禁止新建 preview/import 后端端点或改映射口径
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2.2 在 G7-1 与底稿目录挂入口
  - `G7TabAdjudication.vue` 头部与 `G7TabDirectory.vue`（用 useAuditContext 取 projectId/year/canEdit）各加「🔗 联动到合并工作底稿」按钮 + 弹窗
  - 单测 `g7ConsolLinkageEntry.spec.ts`（6 passed：409 不重试写入+自动重预览/422 detail/expected_versions 透传/stale 静默/缺上下文）；diagnostics 全清 + Vite transform 200×4
  - _Requirements: 1.1, 1.4_

- [x] 3. Wave 2：G7-2 明细逐户四表取数
- [x] 3.1 后端 aux 归集纯函数与端点
  - `_g7_long_term_equity_main_import_export.py` 追加 `build_g7_detail_rows_from_aux`（纯函数，`section='cost'`，来源串写 remark，比例列不取数）与 `aggregate_g7_detail_rows_from_aux`（`get_active_filter` + 先定 `aux_type` 后归集，列名用 `opening_balance/debit_amount/credit_amount/closing_balance`，科目 `LIKE '1511%'`）
  - 新增 `POST /api/workpapers/{wp_id}/g7/import-aux-balance`：灰度关闭直接返回 `imported_count=0` 且不触库；merge 按 `investeeName` 去重；`overwrite=True` 回报影响行数；查询异常 `rollback()` + `ok:True` 提示（不 500）
  - 🔴 照 F1 `import-aux-balance` 实现，禁止照 D3/D5/D6/D7 历史 aux 版本（其列名不存在）
  - 单测：映射、空名跳过、closing 优先、无数据返回空 + 提示、灰度关闭零写入
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6_

- [x] 3.2 前端合并纯函数
  - 新建 `composables/g7AuxExtraction.ts`：`mergeAuxRowsIntoDetail(state, incoming, {overwrite})`，名称规范化（去空白/全角括号）匹配，`overwrite=false` 只填空，返回 `added/filled/skipped`
  - 单测：Persist_First、overwrite、幂等、名称变体匹配
  - _Requirements: 2.1, 2.3_

- [x] 3.3 G7-2 接入取数入口
  - `G7TabDetail.vue` 工具栏加「从四表取数」（`extractionEnabled` 灰度关闭时隐藏，render project_context.g7_extraction_enabled 透出）→ 调 `/g7/import-aux-balance` → `mergeAuxRowsIntoDetail`(Persist_First) → `recalcAndPublish`+`markDirty`+`saveRows`(持久化 G7-2-rows) → 既有 `publishDetail` 发 `g7:detail-updated`
  - 提示含 aux_type、归集单位数、新增/填空行数、截断、「控制类型未取数请按 G7-4 改段」
  - 后端 aux 单测 9 passed + 前端 merge 单测 7 passed；diagnostics 全清 + Vite 200
  - _Requirements: 2.1, 2.3, 2.4, 2.5_

- [x] 4. Wave 3：G7-1 分类核对与 G7-14 跨册带入
- [x] 4.1 render 注入叶子分类合计
  - `_g7_long_term_equity_main.py` 新增 `_build_g7_leaf_categories`（叶子判定 = 某 code 不是任何其它 code 前缀；Category_Map 见 design；unmapped 单列；灰度关闭/异常返回 `None`），additive 写入 `html_data.tb_leaf_categories`
  - 单测：叶子过滤无双算、Category_Map、unmapped、灰度关闭为 None
  - _Requirements: 3.2, 3.4, 9.1_

- [x] 4.2 G7-1 分类核对卡片（只读）
  - `G7TabAdjudication.vue` 新增核对卡片：分类合计 vs 审定表相应合计，差异 > 0.01 告警并给出可能原因；顶部加一行说明「本表行由 G7-2 明细自动投影，请在 G7-2 修改」
  - 阈值与四舍五入口径与既有 TB 核对一致；**不写 rows、不改 TB 回写触发条件**
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 9.4_

- [x] 4.3 G7-14 → G7-2 跨册带入 + G7-1 对照展示
  - 新建 `composables/g7EquityMethodPullToDetail.ts`：`extractG7_14ClosingRows`（纯函数）、`buildEquityPullDiff`、`pullG7_14ForDetail`（ACNR `resolve-instance` + `checklist-responses`，缺源返回空集合）
  - `G7TabDetail.vue` 加「从 G7-14 带入期末余额」→ 逐户对照弹窗 → 确认后按 Persist_First 写 `G7EquityRow`
  - `G7TabAdjudication.vue` 加只读「G7-14 对照差异」（复用 `calcClosingReconVariance`，不新造公式）
  - 单测：提取、差异构建、缺源安全、Persist_First
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 5. Wave 4：抽凭引擎铺开
- [x] 5.1 G7-10 / G7-11 / G7-12 挂载抽凭
  - 三组件各挂 `GtVoucherSamplingEngine`（`account-code="1511"`、`phase="final"`、`:workpaper-id`、`:year`，`v-if="!isReadonly && wpId && projectId"`）
  - `onSampleFilled(payload)` 解构 `payload.samples`，按各表既有行模型映射（凭证号/日期/借贷金额/对方科目），按 `voucherNo` 去重
  - 单测：props 齐备、只读隐藏、去重
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 6. Wave 5：stale 常驻提示与 G7-4 反向补录
- [x] 6.1 stale 只读端点与两侧常驻提示
  - `consol_worksheet_data.py` 新增 `GET /g7-linkage/{project_id}/{year}/stale`，函数体仅委托既有 `load_linkage_stale_state`，权限 `readonly`
  - `ConsolWorksheetTabs.vue` 主界面顶部横幅（列 `stale_sheets`）；`GtG7LongTermEquityMain.vue` 顶部提示；成功导入后刷新清除；请求失败静默降级
  - 契约测试：端点无额外逻辑（源码断言）
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 6.2 G7-4 从合并范围带入
  - `g7BasicInfoModel.ts` 追加 `sourcesFromConsolScope`（`is_included=false` 跳过、空名跳过、`ownership_ratio` 百分数口径），复用既有 `syncG7BasicInfoFromSources`
  - `G7TabBasicInfo.vue` 加「从合并范围带入」→ `GET /api/consolidation/scope?project_id&year` → 提示 `added/filled`；空数据提示「合并范围未维护」
  - 单测：不删不覆盖、ratioScale='percent'、空数据不变
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 7. Wave 6：属性测试与联动集成测试
- [x] 7.1 属性测试（hypothesis / fast-check）
  - 后端 `tests/g7_extraction/test_g7_pbt.py`：Property 1（叶子无双算）、3（单一 aux_type）、5（灰度零写入）
  - 前端：Property 2（Persist_First）、4（按名归并幂等）
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 7.2 联动端点与 DB 写入集成测试
  - `preview`/`import` 成功、409、422、readonly 不可导入
  - import DB 写入：四表只填空合并、`consol_scope` 同步不覆盖 `is_included`、`g7_suggestions` 写入、Linkage_Stale 置位与清零
  - _Requirements: 8.1, 8.2_

- [x] 7.3 建议草稿读取健壮性测试
  - `G7SuggestionDraftSheet` / `ConsolWorksheetTabs` 对未知 `type`、字段缺失、空数组、`imported_at` 缺失均不崩且给空态引导
  - _Requirements: 8.3_

- [x] 8. Wave 7：零回归门与端到端
- [x] 8.1 零回归门
  - 跑齐：G7 前端全部 spec（main/method/subsidiary + 披露 + 反向跳转）、合并 `ConsolWorksheetTabs` 全部 spec、后端 G7/合并联动相关 pytest
  - `get_diagnostics` 全清 + 全部改动 `.vue`/`.ts` 经 `curl.exe` 查 Vite transform 200
  - 用 `git stash` 区分 pre-existing 失败并记录
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 8.2* 端到端实测（可选）
  - 需要实例化 G7 三册且 1511 有辅助余额的项目：四表取数 → G7-2 落库 → G7-1 投影与分类核对 → 联动预览/导入 → 建议草稿可见 → stale 提示消失
  - 若环境不满足（无 aux 数据 / 未实例化），如实记录留待，不伪造通过
  - _Requirements: 1.6, 2.1, 6.3_

## Notes

- 全程只用 `str_replace` / `fs_write` 改 `.vue` / `.md`（禁 PowerShell `Set-Content`/`Get-Content`，会破坏 UTF-8 / 加 BOM）。
- G7 三册是三个 `wp_id`，跨册取数只能走 ACNR `resolve-instance` + `checklist-responses`，禁止在前端直接猜 wp_id。
- 取数「宁缺勿造」：aux 无控制类型 → 不产 relationship；aux 无持股比例 → 不填比例列；无 aux 数据 → 提示手工，不用科目合计拆逐户。
- 后端 `--reload` 会自动加载新端点；`wp_code_overrides.json` 一类静态 JSON 改动需重启（本 spec 不改它）。
- 每波结束即跑该波单测 + Task 1.2 基线，避免尾部集中返工。
