# Implementation Plan: grid-sheet-inline-editing

## Overview

�?D0-1 函证结果汇总表创建专用组件 `GtConfirmationSummary`（confirmation-summary），包含 6 个子组件 + 1 个数�?composable + 后端枚举�? Sprint 自底向上：类�?枚举 �?数据�?�?明细编辑 �?看板+表单+结论 �?注册集成 �?回归实测�?

## Tasks

### Sprint 1：类型定�?+ 后端枚举（地基）

- [x] 1.1 新增 `confirmationTypes.ts`：ConfirmationRow(28 字段) / DashboardMetrics / SamplingData / NotesData / ConclusionData / ConfirmationPayload 类型定义
  - _需�?2.1, 3.1, 4.1, 5.1, 6.1_
- [x] 1.2 新增 `confirmationEnums.ts`：dictKey 常量映射（confirmation_account_type / confirmation_method / confirmation_reply_method / yes_no / confirmation_match / sampling_method�?
  - _需�?7.1_
- [x] 1.3 后端 `system_dicts.py _DICTS` �?6 个枚�?key（confirmation_account_type 13�?/ confirmation_method 2�?/ confirmation_reply_method 4�?/ yes_no 2�?/ confirmation_match 3�?/ sampling_method 4项）
  - _需�?7.1_
- [x] 1.4 后端枚举测试：dicts 端点返回 6 �?key 全部完整
  - _需�?7.1_

### Sprint 2：useConfirmationData composable（数据核心）

- [x] 2.1 新增 `useConfirmationData.ts`：从 htmlData 解析初始�?rows/sampling/notes/conclusion + watch(htmlData) 重建 + dirty
  - _需�?9.4; 属�?P4_
- [x] 2.2 rows CRUD：addRow(末尾插入空行 seq 自增) / deleteRow(ids) / updateField(rowId, field, value)
  - _需�?9.1, 9.2_
- [x] 2.3 accountTabs computed（从 rows[].account_type 去重�? activeTab 切换 + filteredRows
  - _需�?1.1, 1.2_
- [x] 2.4 dashboardMetrics computed（按 account_type 分组 SUM 7 指标，含 account_balances 注入�?
  - _需�?3.1; 属�?P1_
- [x] 2.5 可确认金额业务规�?`computeConfirmedAmount`：相符→amount / 不符→reply_amount / 未回+消极式→amount / 未回+积极式→alt_confirmed；difference=amount−reply_amount(相符强制0)；用户覆盖标 _overridden
  - _需�?17.1, 17.2, 2.5; 属�?P3/P7_
- [x] 2.6 buildPayload() 返回 ConfirmationPayload（rows + summary_config + sampling + notes + conclusion + _format�?
  - _需�?9.4_
- [x] 2.7 useConfirmationData 单测：addRow/deleteRow/updateField + dashboardMetrics 实时 + buildPayload + 可确认金�?4 规则 + 覆盖�?确认�?
  - _属�?P1/P3/P7_
- [x] 2.8 dashboardMetrics 扩展：函证覆盖率/确认覆盖�?+ warn_level（确�?80%=danger, 覆盖<50%=warn�?
  - _需�?19.1, 19.2, 19.3_

### Sprint 3：Master 列表 + Detail 面板（核�?UI�?

- [x] 3.1 新增 `ConfirmationMaster.vue`：el-table 7 �?+ 多�?+ 工具栏（新增/删除/保存�? 行展开触发
  - _需�?1.3, 9.1_
- [x] 3.2 新增 `ConfirmationDetail.vue`�? 阶段 el-collapse + 条件 v-show(is_replied) + 枚举 el-select + 数�?el-input-number + 文本 el-input
  - _需�?2.1, 2.2, 2.3, 2.4, 7.2_
- [x] 3.3 右键菜单：接�?useCellSelection + CellContextMenu slot（复制行/插入上下/删除/复制索引号）
  - _需�?9.3_
- [x] 3.4 D0-2 引用：entity_name 字段搜索建议（从�?wp �?D0-2 sheet parsed_data 提取已核实单位列表，不可用时降级 el-input�?
  - _需�?8.1, 8.2_
- [x] 3.5 ConfirmationMaster + Detail 渲染 spec：展开/折叠/条件字段/枚举下拉/只读守卫
  - _需�?1.5, 2.2, 2.3; 属�?P5_

### Sprint 4：看�?+ 样本选择 + 审计说明 + 审计结论

- [x] 4.1 新增 `ConfirmationDashboard.vue`�? 科目×7 指标网格 + 折叠 + 覆盖�?确认率红线警示（确认<80%=�?文案"证据可能不足", 覆盖<50%=橙）
  - _需�?3.1, 3.3, 19.1, 19.2, 19.3_
- [x] 4.2 新增 `ConfirmationSampling.vue`�? 字段折叠区（textarea×5 + select×1�?
  - _需�?4.1, 4.2_
- [x] 4.3 新增 `ConfirmationNotes.vue`�? 专题 textarea（placeholder 含示例）
  - _需�?5.1, 5.2_
- [x] 4.4 新增 `ConfirmationConclusion.vue`：radio(A/B/C) + v-show(B/C) textarea
  - _需�?6.1, 6.2, 6.3_
- [x] 4.5 新增 `ConfirmationTabs.vue`：el-tabs type=card + "全部"选项
  - _需�?1.1, 1.6_
- [x] 4.6 看板+表单+结论�?spec：折叠展开 / 指标实时 / 结论选择联动 / 只读
  - _需�?3.2, 4.3, 5.3, 6.4; 属�?P1/P5_

### Sprint 4.5：完整表格视�?+ 单元格选区（保�?Excel 式能力）

- [x] 4.7 新增 `ConfirmationFullGrid.vue`�?8 列宽表，沿用 GtGridSheet 美化（分�?5 色着�?冻结首列/斑马�?空值淡化）+ 列类型可编辑（enum/number/text/只读 span�?
  - _需�?13.2, 13.3_
- [x] 4.8 完整表格视图接入 useCellSelection：单�?Ctrl/Shift/拖拽框�?+ 复制(TSV+HTML) + 粘贴 + 多选求�?
  - _需�?14.1, 14.2, 14.3, 14.4_
- [x] 4.9 完整表格 CellContextMenu：复�?粘贴/求和/插入�?上下)/删除�?复制索引号；只读时仅复制/求和
  - _需�?14.5, 14.6_
- [x] 4.10 视图切换：列�?完整表格切换按钮 + localStorage 记忆 + 两视图共�?useConfirmationData.rows（编辑互通）
  - _需�?13.1, 13.4, 13.5; 属�?P6_
- [x] 4.11 完整表格视图 spec：美化保留、单元格选区/复制/粘贴/求和、右键全功能、视图切换数据一致、只读守�?
  - _需�?13, 14; 属�?P5/P6_

### Sprint 4.8：自动取�?+ 批量导入 + 跨底稿跳转（功能×内容结合�?

- [x] 4.12 新增 `useConfirmationAutoFetch.ts`：账面金额从 trial_balance �?按科目映�? + 索引号自动生�?+ 字段 `_source` 标识
  - _需�?15.1, 15.3, 15.4, 15.5_
- [x] 4.13 函证清单带入：新增行支持�?D0-2/抽样底稿带入"被询证单�?科目/金额"（有来源自动填，无来源手填）
  - _需�?15.2, 8.1_
- [x] 4.14 批量导入：工具栏"导入清单/导出模板"，复�?useExcelIO，解析→预览弹窗(匹配/跳过)→确认批量新增；缺列行标错跳�?
  - _需�?16.1, 16.2, 16.3, 16.4; 属�?P8_
- [x] 4.15 跨底稿跳转：调节索引(不符�?→D0-4、替代程序索引→D0-5/D0-6 渲染可点击链接，复用 addressRegistry jump_route；目标不存在提示
  - _需�?18.1, 18.2, 18.3, 18.4_
- [x] 4.16 默认布局聚焦：辅助区(样本选择/审计说明/审计结论)默认折叠，列表视图为默认，看�?明细首屏可见
  - _需�?20.1, 20.2, 20.3, 20.4_
- [x] 4.17 spec：自动取数来源标�?+ 导入预览不破坏既有行 + 跳转链接 + 折叠默认�?
  - _需�?15, 16, 18, 20; 属�?P8_

### Sprint 5：主组件组装 + 注册 + 保存集成
- [x] 5.1 新增 `GtConfirmationSummary.vue`：组�?Tabs+Dashboard+[列表视图:Master+Detail / 完整表格视图:FullGrid]+Sampling+Notes+Conclusion + 视图切换 + 接入 useConfirmationData + emit save/open-formula/restore
  - _需�?1-6, 13 全部_
- [x] 5.2 `htmlRendererRegistry.ts` 注册 confirmation-summary �?GtConfirmationSummary
  - _需�?11.3_
- [x] 5.3 后端 `_WP_CODE_OVERRIDE` �?render-config dispatch：D0-1 "函证结果汇总表" sheet �?componentType=confirmation-summary
  - _需�?11.3_
- [x] 5.4 旧格式兼容：htmlData �?`_format` 时降�?GtGridSheet 只读（在 GtConfirmationSummary 内检测）
  - _需�?12.2; 属�?P4_
- [x] 5.5 编制指引迁移：D0-1 �?wp_guidance JSON 补入准则条文/注意事项/参考结论模板（�?6-63 内容�?
  - _需�?10.1, 10.2_
- [x] 5.6 保存端到端：新增�?�?填写 �?保存 �?后端 parsed_data.html_data 存入 confirmation-v1 格式 �?重开组件解析显示
  - _需�?9.4, 9.5_

### Sprint 6：联�?+ 回归 + Playwright 实测

- [x] 6.1 D0-1 实测：科�?Tab 切换 �?新增�?�?detail 枚举填写 �?条件字段联动 �?保存 �?刷新持久�?�?看板指标正确
  - _需�?1-6, 9_
- [x] 6.2 只读回归：复核通过底稿全只�?+ 其他 sheet(D0A/D0-2 �? 渲染不受影响
  - _需�?12.1_
- [x] 6.3 旧格式回归：�?html_data._format 后打开 D0-1 降级�?GtGridSheet 只读（分组着�?冻结列保留）
  - _需�?12.2, 12.3_
- [x] 6.4 render-config 冒烟 + 后端 system_dicts 测试通过
  - _需�?12.3_
- [x] 6.5 Playwright D0-1 端到�?0 error：导入清�?�?Tab �?�?detail 枚举�?�?条件联动 �?可确认金额自动算 �?看板覆盖�?确认率警�?�?跳转链接 �?保存 �?重开全持久化
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3"] },
    { "wave": 2, "tasks": ["1.4", "2.1"] },
    { "wave": 3, "tasks": ["2.2", "2.3", "2.4", "2.5"] },
    { "wave": 4, "tasks": ["2.6", "2.7", "2.8"] },
    { "wave": 5, "tasks": ["3.1", "3.2", "4.1", "4.2", "4.3", "4.4", "4.5", "4.7"] },
    { "wave": 6, "tasks": ["3.3", "3.4", "3.5", "4.6", "4.8"] },
    { "wave": 7, "tasks": ["4.9", "4.10", "4.11", "4.12", "4.13", "4.14", "4.15", "4.16"] },
    { "wave": 8, "tasks": ["4.17", "5.1", "5.2", "5.3"] },
    { "wave": 9, "tasks": ["5.4", "5.5", "5.6"] },
    { "wave": 10, "tasks": ["6.1", "6.2", "6.3", "6.4"] },
    { "wave": 11, "tasks": ["6.5"] }
  ]
}
```

## Notes

- 复用：useCellSelection（右�?复制）、CellContextMenu（菜单壳+slot）、useDictStore（枚举）、wp_html_save（保存无需改后端）�?
- 保存载荷用结构化 JSON（`_format: confirmation-v1`），后端 wp_html_save 只校�?�?dict"直接存储�?
- �?grid cells 兼容：检�?`_format` 字段决定用专用组件还是降�?GtGridSheet�?
- 编制指引�?guidance：静态内容（准则/注意事项/结论模板）从模板提取后存�?`backend/data/wp_guidance/D0-1.json`�?
- D0-2 引用�?API 查同 wp 其他 sheet �?parsed_data（不硬编码，D0-2 更新后自动同步）�?
- 铁律：组�?props 不可变（useConfirmationData 内部深拷贝）；只读路径无编辑控件；改动后 Playwright 实测�?
