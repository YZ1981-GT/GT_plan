# 全局建议书剩余 27 项 — 设计文档

## ADR-1：实施顺序

**决策**：按"用户感知度 × 实施难度"排序，先做高感知低难度项

**Sprint 划分**：
- Sprint 0（部分实现补齐 4 项，3.5 天）：M-1 / M-5 / G-1 / D-1
- Sprint 1（快修 5 项，3 天）：D-2 / D-5 / W-4 / A-5 / DT-3
- Sprint 2（联动 3 项，6 天）：L-2 / L-3 / K-2
- Sprint 3（搜索+导出 4 项，6 天）：S-2 / C-2 / C-3 / AT-1
- Sprint 4（深度 3 项，7 天）：L-4 / K-4 / Y-2
- Sprint 5（重型 4 项 + 运维治理 4 项，8 天）：S-3 / AT-2 / AT-3 / S-4 / UI-8 / MT-5 / MT-8 / MT-9

**总工时**：~33.5 天（单人），建议 2 人并行 ~17 天
**外部依赖**：K-1（vLLM）/ W-3（钉钉）条件满足后独立接入，不阻塞主线

## ADR-1b：Sprint 0 部分实现补齐方案

| 项 | 实现方式 |
|----|---------|
| M-1 甘特图 | ManagerDashboard 新增 `ProjectGanttChart.vue`，ECharts `type: 'custom'` 绘制甘特条（横轴=时间/纵轴=项目名），数据源复用 `/api/dashboard/manager/projects-overview` 的 `start_date/due_date/progress` 字段。<br/>**实施备注**：spec 起草时引用的 `/api/manager/projects/matrix` 不存在；实施时改用 Phase 6 F7 的 projects-overview 端点 + 补 start_date/due_date/primary_cycle 三字段。 |
| M-5 底稿进度列 | WorkHourApprovalTab 表格新增列，后端 workhour_approval 端点 response 增加 `wp_completion_rate` 字段（`COUNT(status>=edit_complete) / COUNT(assigned_to=user)` 百分比） |
| G-1 GtPageHeader 审查 | `grep -rn "GtPageHeader" src/views/` 输出使用清单，简单 CRUD 页面（StaffManagement/KnowledgeBase/AttachmentHub/RecycleBin 等）替换为 `<GtToolbar>` 白色简洁工具栏 |
| D-1 大底稿懒加载 | WorkpaperEditor `loadWorkpaper` 时仅请求 `?sheets=active`（后端返回 active sheet 的 cells + 其余 sheet 仅返回 name/row_count 元数据），切换 sheet 时 `GET /working-papers/{id}/sheet/{name}` 按需加载 |

## ADR-2：L-2 AJE 影响预览

**方案**：后端新增 `POST /api/projects/{pid}/adjustments/preview-impact`

```python
# 请求：模拟的调整分录（不写 DB）
{
  "line_items": [{"account_code": "1122", "debit": 100000, "credit": 0}],
  "year": 2025
}

# 响应：受影响的报表行
{
  "affected_report_rows": [
    {"report_type": "balance_sheet", "row_code": "BS-005", "field": "当期金额", "delta": 100000},
    {"report_type": "income_statement", "row_code": "IS-008", "field": "当期金额", "delta": -100000}
  ],
  "affected_workpapers": ["D2", "K8"]
}
```

前端：`AdjustmentImpactPreview.vue` 嵌入调整分录编辑弹窗右侧，debounce 500ms 调用。

## ADR-3：L-3 一致性快照

**方案**：`working_paper` 表新增 `prefill_tb_snapshot` JSONB 字段

- prefill 执行时：记录 `{account_code: audited_amount}` 快照
- 下次 prefill 时：对比当前 TB 值与快照，差异 > 0 则标记 cell 为 `stale_since_last_prefill`
- 前端：prefill diff 面板（已有 PrefillDiffPanel）增加"与上次快照对比"列

## ADR-4：S-2 Ctrl+F 全覆盖

**方案**：创建 ESLint 规则 `no-el-table-without-search`

- 检测 `<el-table` 标签所在组件是否 import 了 `useTableSearch` 或 `TableSearchBar`
- 不满足则 warn（不 block，逐步迁移）
- 优先接入 10 个高频表格页：WorkpaperList / TrialBalance / Adjustments / Misstatements / Projects / StaffManagement / WorkHoursPage / ReviewWorkbench / KnowledgeBase / AttachmentHub

## ADR-5：K-2 相关准则侧栏

**方案**：WorkpaperSidePanel 新增第 11 个 Tab "准则"

- 数据源：`TSJ/` 目录下 70 个 Markdown 文件，按 wp_code 前缀匹配
- 匹配规则：`wp_code.startsWith('E1')` → 加载"货币资金审计复核提示词.md"
- 前端：`SideStandardsTab.vue`，渲染 Markdown（复用 marked + DOMPurify）
- 后端：`GET /api/knowledge/tsj/{cycle_name}` 返回对应提示词内容

## ADR-6：K-4 LLM 解释链

**方案**：LLMService 输出格式扩展

```python
class LLMResponse(BaseModel):
    content: str           # 主要输出
    reasoning: str | None  # 推理过程
    references: list[dict] # 引用来源 [{type: "CAS", code: "CAS 8", section: "减值测试"}]
    data_sources: list[str] # 数据来源 ["TB:1601:期末余额", "WP:H1:折旧分配分析表"]
    confidence: float      # 置信度 0-1
```

前端：LLM 输出区域底部增加可折叠的"推理依据"面板。

## ADR-7：Y-2 跨年选择性继承

**方案**：ProjectWizard 新增步骤"继承配置"

```
┌─ 继承选项 ─────────────────────────────┐
│ ☑ 科目表（account_chart）              │
│ ☑ 报表行次映射（report_line_mapping）   │
│ ☑ 底稿模板配置                         │
│ ☐ 人员分工（project_assignments）       │
│ ☐ 复核链配置                           │
│ ☑ VR 规则                              │
│ ☐ 重要性水平                           │
└────────────────────────────────────────┘
```

后端：`POST /api/projects/{pid}/clone-from/{prev_pid}` 增加 `options: {inherit_chart, inherit_mapping, ...}` 参数。

## ADR-8：Sprint 1 快修项设计

| 项 | 实现方式 |
|----|---------|
| D-2 编辑模式过渡 | `useEditMode` 切换时 `nextTick` + CSS `transition: opacity 0.3s` |
| D-5 列宽自适应 | `watch(displayPrefs.fontSize, () => nextTick(() => tableRef.value?.doLayout()))` |
| W-4 加班识别 | `WorkHour` 模型新增 `is_overtime` computed 字段（hours > 8），前端 WorkHoursPage 高亮 |
| A-5 计时器 | WorkpaperSidePanel 新增 `SideTimerTab.vue`（localStorage 存 start_time，保存时 POST /workhour-entries） |
| DT-3 枚举管理 | SystemSettings 新增 Tab "枚举管理"，CRUD `/api/system/dicts`（已有后端，缺前端 UI） |

## 实施偏差备忘

> **task 5.1 高级查询构建器（S-3）**：v1 仅支持单表查询（11 张白名单只读表），design 文档列的 JOIN 能力延后到 v2，未来需求触发时扩展白名单 join 关系而非任意 ON 条件。
