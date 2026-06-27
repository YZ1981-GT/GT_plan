# Design — A5-1 现金流量表审计 精美 HTML 专属组件

## Overview

A5-1 是多 sheet 综合性底稿（程序表+审定表+检查表），新 componentType `a5-1-cashflow-audit`。渲染为 6 Tab 结构化卡片 + 会计提示抽屉 + 双模式切换（结构化 HTML / OnlyOffice Excel）+ debounce 自动保存。

**设计原则：**
- 所有 Tab 的行结构都是**静态模板**（行数/项目名固定），用户只填写数值和文本
- 不需要后端 xlsx 解析器——步骤/行定义全部硬编码在前端 composable 的常量中
- 数据持久化统一走 `checklist_responses` 表（和 A1-15/A1-17 相同路径）
- 自动计算字段（审定数、合计、差异）在前端 Vue computed 中实时计算，不存储
- 双模式切换参考 A1-12 实现模式：el-segmented + GtOnlyOfficeSheet + 健康检查降级

## Architecture

```
GtA51CashflowAudit.vue（顶层编排 ~600行）
├── [顶部栏]
│   ├── el-segmented（「结构化视图」/「Excel 编辑」）
│   ├── 💡会计提示按钮 → el-drawer(480px)
│   └── "已保存 X秒前" 状态文本
├── [结构化视图模式 v-if="mode==='structured'"]
│   └── el-tabs（6 Tab + @wheel 横向滚动）
│       ├── Tab 1: 程序表（审计目标3条 + 21步骤卡片 + 进度条 + 签字区）
│       ├── Tab 2: 审定表（8行表格 + 审计说明 + 编制说明折叠）
│       ├── Tab 3: 勾稽核对（4分组卡片 × 项目表+合计+报表数+差异）
│       ├── Tab 4: 核查-子公司（取得/处置两卡片 × ~10行表格）
│       ├── Tab 5: 核查-明细（~10行现金明细表格）
│       └── Tab 6: 其他现金流量（3类 × 左右对照 + 编制说明折叠）
└── [Excel 模式 v-else]
    └── GtOnlyOfficeSheet(whole-workbook=true)
```

### Composable 设计

```
composables/useA51CashflowAudit.ts（数据管理+计算 ~500行）
├── 常量定义（从源模板提取，硬编码）
│   ├── PROGRAM_STEPS: Step[]           // 21条 {id, label, level, description}
│   ├── AUDIT_OBJECTIVES: string[]      // 3条审计目标文本
│   ├── AUDIT_ROWS: AuditRow[]          // 8行 {id, name, type:'editable'|'auto', sign:+/-}
│   ├── RECONCILE_GROUPS: ReconcileGroup[]  // 4组 {id, title, items:[{id,name}]}
│   ├── CHECK4_SECTIONS: CheckSection[]  // 2部分 {id, title, rows:[{id,name,type}]}
│   ├── CHECK5_ROWS: CheckRow[]          // ~10行 {id, name, type:'editable'|'auto'}
│   ├── OTHER_CF_GROUPS: OtherCFGroup[]  // 3类 {id, title, receive:[], pay:[]}
│   └── ACCOUNTING_TIPS: TipSection[]    // 4节 {title, content/items}
├── 状态管理
│   ├── responses: Ref<Record<string, string>>  // fieldId → JSON value
│   ├── loading: Ref<boolean>
│   ├── lastSavedAt: Ref<Date | null>
│   └── saveError: Ref<boolean>
├── 数据加载
│   ├── loadData(wpId): GET render-config?force_component_type=a5-1-cashflow-audit
│   │   → 解析 response.sheets[0].html_data.responses → 填充 responses map
│   └── refreshData(wpId): 同 loadData，用于模式切回刷新
├── 字段读写
│   ├── getField(fieldId): string       // responses[fieldId] ?? ''
│   ├── setField(fieldId, value): void  // responses[fieldId] = value + scheduleSave()
│   └── debouncedSave(): 2s debounce → PUT /api/workpapers/{wpId}/checklist-responses
│       └── payload: [{item_id, remark}] 批量
├── 自动计算函数
│   ├── getAuditedAmount(rowId): number
│   │   └── = parseFloat(getField(`a51-audit-${rowId}.unadjusted`))
│   │       + parseFloat(getField(`a51-audit-${rowId}.adjustment`)) // NaN→0
│   ├── getAuditRow6Amount(): number
│   │   └── = getAuditedAmount('1') - getAuditedAmount('2') - getAuditedAmount('3')
│   │       + getAuditedAmount('4') + getAuditedAmount('5')
│   ├── getAuditRow8Amount(): number
│   │   └── = getAuditRow6Amount() - getAuditedAmount('7')
│   ├── getReconcileTotal(groupId): number
│   │   └── = SUM( items.map(i => parseFloat(getField(`a51-reconcile-${groupId}-${i.idx}.amount`))) )
│   ├── getReconcileDiff(groupId): number
│   │   └── = getReconcileTotal(groupId) - parseFloat(getField(`a51-reconcile-${groupId}.report_amount`))
│   ├── getCheckDiff(tab, rowIdx): number
│   │   └── = parseFloat(estimated) - parseFloat(reported)  // NaN→0
│   ├── getCheck5Balance(): number
│   │   └── = SUM(行1~7的测算数) - 受限部分.测算数
│   ├── getOtherCFTotal(groupId, side:'receive'|'pay'): number
│   │   └── = SUM(该侧10项的金额)
│   └── programProgress: computed → { filled: number, total: 21 }
│       └── = PROGRAM_STEPS.filter(s => getField(`...conclusion`) in ['Y','N','NA']).length
└── 生命周期
    └── flushPendingSave(): 立即执行 pending save（onBeforeUnmount 调用）

composables/useA51EditorMode.ts（双模式管理 ~80行）
├── mode: Ref<'structured' | 'excel'>     // 默认 'structured'
├── switching: Ref<boolean>                // 切换中 loading
├── onlyofficeHealthy: Ref<boolean>        // 健康状态
├── activeTab: Ref<string>                 // 当前 Tab（切换时保留）
├── checkHealth(): async → GET /api/workpapers/onlyoffice/health → set healthy
├── switchToExcel(flushFn): 
│   └── flushFn() → switching=true → mode='excel' → nextTick → switching=false
└── switchToStructured(refreshFn):
    └── switching=true → refreshFn() → mode='structured' → switching=false
```

### 后端渲染策略

```python
# backend/app/workpapers/renderers/_a51_cashflow.py (~50行)
def render(wp, project, year, scope, session) -> dict:
    """极简渲染：从 checklist_responses 加载已保存数据返回"""
    from ..services.checklist_service import get_responses_by_prefix
    responses = get_responses_by_prefix(session, wp.id, "a51-")
    return {
        "component_type": "a5-1-cashflow-audit",
        "responses": responses,  # Dict[item_id, remark_json_string]
    }
```

## Static Data 定义

### 审定表行（8 行）+ 公式规则

| ID | 项目 | 类型 | 符号 | 审定数公式 |
|----|------|------|------|-----------|
| audit-1 | {year}年12月31日货币资金 | 可编辑 | + | 未审+调整 |
| audit-2 | 减：使用受到限制的存款 | 可编辑 | − | 未审+调整 |
| audit-3 | 减：其他扣减项 | 可编辑 | − | 未审+调整 |
| audit-4 | 加：持有期限≤3月国债 | 可编辑 | + | 未审+调整 |
| audit-5 | 加：其他加项 | 可编辑 | + | 未审+调整 |
| audit-6 | 现金等价物余额 | **自动** | — | **row1−row2−row3+row4+row5** |
| audit-7 | 减：{prev_year}年现金等价物余额 | 可编辑 | − | 未审+调整 |
| audit-8 | 净增加/(减少)额 | **自动** | — | **row6−row7** |

### 勾稽核对（4 组）

每组公式：`合计 = SUM(items[].amount)` → `差异 = 合计 - 报表数` → |差异|>0 红色

### 核查差异（Tab 4 + Tab 5 通用）

`差异 = 测算数 - 原报数`，|差异|>0 红色

Tab 5 额外：`期末余额.测算数 = SUM(行1~7.测算数) − 受限部分.测算数`

### 其他现金流量合计（Tab 6）

每类每侧：`合计 = SUM(item1.amount ~ item10.amount)`

## 双模式切换流程

```
组件挂载
  ├── checkHealth() → onlyofficeHealthy
  ├── loadData(wpId) → responses
  └── 渲染结构化视图（默认）

切换到 Excel：
  flushPendingSave() → switching=true → mode='excel' → GtOnlyOfficeSheet 渲染 → switching=false

切回结构化：
  switching=true → refreshData(wpId) → mode='structured' → switching=false
  （activeTab 保持不变）
```

## 注册点变更

| 注册点 | 文件 | 变更 |
|--------|------|------|
| VALID_COMPONENT_TYPES | `wp_classification_service.py` | 新增 `a5-1-cashflow-audit` |
| htmlRendererRegistry | `htmlRendererRegistry.ts` | lazy → GtA51CashflowAudit.vue |
| RENDERER_DISPATCH | `renderers/__init__.py` | `a5-1-cashflow-audit` → `_a51_cashflow.render` |
| CashFlowVerification.vue | 父组件 | A5-1 Tab 改用 GtA51CashflowAudit(wpId) |

## item_id 命名规范

| Tab | 前缀格式 | 示例 |
|-----|---------|------|
| 程序表步骤 | `a51-program-{stepId}.{field}` | `a51-program-step-1.conclusion` |
| 程序表签字 | `a51-program-approval.{field}` | `a51-program-approval.manager` |
| 审定表 | `a51-audit-{rowId}.{field}` | `a51-audit-1.unadjusted` |
| 审计说明 | `a51-audit-note` | `a51-audit-note` |
| 勾稽项目 | `a51-reconcile-{gid}-{idx}.{field}` | `a51-reconcile-1-3.amount` |
| 勾稽报表数 | `a51-reconcile-{gid}.report_amount` | `a51-reconcile-2.report_amount` |
| 核查子公司 | `a51-check4-{section}-{idx}.{field}` | `a51-check4-acquire-2.estimated` |
| 核查明细 | `a51-check5-{idx}.{field}` | `a51-check5-1.reported` |
| 其他现金流量 | `a51-other-{gid}-{side}-{idx}.{field}` | `a51-other-1-receive-3.amount` |

field 可选值：
- 程序表: `conclusion` / `executor` / `description` / `index_ref`
- 审定表: `unadjusted` / `adjustment` / `explanation` / `remark`
- 勾稽核对: `amount` / `remark` / `index_ref`
- 核查: `reported` / `estimated` / `basis`
- 其他CF: `name` / `amount`

## 视觉设计

```
┌────────────────────────────────────────────────────────────────────────────┐
│  [结构化视图 ·  Excel编辑]          💡会计提示       ✓ 已保存 3秒前       │
├────────────────────────────────────────────────────────────────────────────┤
│  程序表 | 现金等价物审定 | 勾稽核对 | 核查-子公司 | 核查-明细 | 其他CF    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌── 审计目标 ──────────────────────────────────────────────────────────┐ │
│  │ 1. 现金流量表的内容、性质和数额是否正确、合理、完整                  │ │
│  │ 2. 现金流量有关项目数额与其他报表及附注的勾稽关系是否正确            │ │
│  │ 3. 现金流量表各项目的披露是否恰当                                    │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  进度: 8/21 ████████░░░░░░░░░░░ 38%                                      │
│                                                                            │
│  ┌─ [1] 获取编制现金流量表的基础资料 ─────────────────────────────────┐  │
│  │  [● Y  ○ N  ○ NA]   执行人:[______]  说明:[__________]  索引:[__] │  │
│  ├────────────────────────────────────────────────────────────────────┤  │
│  │    [1.1] 复核加计是否正确                                          │  │
│  │    [○ Y  ○ N  ○ NA]   执行人:[______]  说明:[__________]  索引:   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌── 程序批准 ──────────────────────────────────────────────────────────┐ │
│  │  经理签字: [__________]    日期: [____-__-__]                        │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────┘
```

## Error Handling

| 场景 | 处理 |
|------|------|
| render-config 加载失败 | 不阻塞渲染（步骤静态定义），responses 空，可正常填写 |
| 保存失败 | 指数退避重试 3 次（1s/2s/4s）+ ElMessage.warning |
| OnlyOffice 不可用 | 「Excel 编辑」禁用 + tooltip "OnlyOffice 服务不可用" |
| 数值非法 | parseFloat NaN → 0，不阻断计算链 |
| 组件卸载有 pending | onBeforeUnmount → flushPendingSave() |
