# Design Document

## Overview

本设计把程序裁剪决策从「单维（科目有无余额）」升级为「三维（风险评估 → 重要性 → 数据存在性）」，把委派从「一次一个循环给一个人」升级为「按风险与负载给出建议分配表」。

核心设计取向是**加法式接线**而非重建：三个判据数据源（试算表科目金额、重要性水平、B50 认定层次风险）的**读取能力全部已存在**，本设计新增的是一层**纯函数决策内核** + 把内核结论接到既有裁剪/委派写入路径上。既有的 canonical trim preview/apply、委派 preview/apply、B50 录入 UI、B50 风险读取器一律不改写其对外契约。

### 🔴 术语钉死：禁用 PM / TE / SAT 缩写

`GtB50RiskAssessment.vue` 的既有实现把 `overall_materiality` 命名为 `pm`、把 `performance_materiality` 命名为 `te`，而审计实务中 PM 通常指 performance materiality（实际执行重要性）—— **两套命名正好相反**。为避免实现时取错字段：

- 本设计与实现代码中**一律使用 DB 字段名**：`overall_materiality` / `performance_materiality` / `trivial_threshold`
- 新增代码**禁止**出现 `pm` / `te` / `sat` 作为变量名或字段名
- `GtB50RiskAssessment.vue` 内既有的 `pm`/`te`/`sat` 命名**不在本 spec 范围内改动**（改它会波及该组件的 12 条 PBT），但新代码不得沿用
- 守卫按此断言（见 Property 3）

判据口径：`trivial_threshold` 是更强的裁剪建议依据（明显微小错报临界值），`performance_materiality` 是主口径，`overall_materiality` **不作为裁剪判据**（它是财报整体层面的评价基准，不是单个科目是否需要实施程序的门槛）。

### 已存在能力清单（本设计的复用面，禁重建）

| 能力 | 位置 | 本设计如何使用 |
|---|---|---|
| 试算表科目金额聚合 | `GET /api/b50/scope-accounts` → `{name, amount, cycle}` | 直接消费 `amount`（现状被丢弃） |
| 重要性读取 | `GET /api/materiality` + `MaterialityService` | 直接消费，不新建端点 |
| B50 认定层次风险读取 | `b50_risk_reader.load_b50_accounts()` / `load_b50_risks()` | additive 补三字段后消费 |
| B50 录入 UI 与一键导入 | `GtB50RiskAssessment.vue` + 3 个 composable | 只加完成度提示，不改录入逻辑 |
| B50 × B15 联动面板 | 同组件的 `loadMateriality()` + `suggestedTeRatio()` | 复用其取数口径，不重建 |
| 科目级数据可用性 | `GET /api/projects/{pid}/procedure-scope/data-availability` | 保持现有 `subject_with_data` / `subject_no_data` 用法 |
| 粗裁写入 | canonical trim preview → apply | 建议确认后走同一路径；scope entry additive 扩 `reason_code`（见下） |
| 委派 preview / apply | `ProcedureDelegationService` | 建议分配表应用走同一路径 |
| 裁剪 → 委派联动 | `_trimmed_scopes()` | 逻辑无需改动；⚠️ 真实库 `procedure_instances.status` 436 行**全为 `execute`**，该联动**从未有数据流经过**（逻辑对但未被真实验证） |
| 附注"本期无内容"标注 | `disclosure_notes.is_empty` + `note_content_utils.note_has_data`（与 `NoteWordExporter._has_content` 收敛的共享 helper，归档 spec `disclosure-notes-selective-generation` Req2） | Task 21 **复用**它，不新建标注字段 |
| 科目级数据可用性端点 | `GET /api/projects/{pid}/procedure-scope/data-availability`（`procedures.py`） | 已确认存在，保持现有用法 |

### canonical trim scope entry 的 additive 扩展

现状 scope entry 为 `{kind, cycle, wp_index_code, target_status, skip_reason}`（前端 `commonApi.canonicalTrimPreview/Apply` 与后端契约），**没有理由码位置**。而理由码必须与适用性状态同一次落库（Requirement 8.8）—— 两次写入会产生「状态已改、理由码未写」的中间态，且 canonical 的一次性 preview 凭证机制不覆盖第二次写入。

因此在 scope entry 上 additive 增加可选字段：

```
{ kind, cycle, wp_index_code, target_status, skip_reason, reason_code? }
```

三条约束：

- **未携带 `reason_code` 时行为逐字节不变**（Requirement 8.9）—— 存量调用方与既有测试零影响，这是本扩展可安全落地的结构性保证
- `reason_code` 必须参与 preview → apply 的 **request payload 归一**（否则 preview 与 apply 的 payload 不一致会触发防篡改校验失败）
- 后端落库时写入 `procedure_instances.suggestion_state.reason_code`，与 `skip_reason` 并列写在同一事务

### 🔴 `affected_workpapers` 是同名不同源字段，勿复用错组件

平台有两个 `affected_workpapers`，结构与语义都不同：

| 来源 | 结构 | 用途 |
|---|---|---|
| **委派 preview**（本 spec 要展示的） | `{wp_index_ids: string[], wp_ids: string[]}` | 本次委派将影响哪些底稿 |
| 调整分录影响预览 | `string[]`（`AdjustmentImpactPreview`）或 `ImpactWorkpaper[]`（`ImpactPreviewPanel`） | 调整分录会波及哪些底稿 |

Task 15 展示的是**委派侧**那个（对象含两个 id 数组），不得复用 `ImpactPreviewPanel` / `AdjustmentImpactPreview` 的渲染组件。

## Architecture

### 分层

```
┌─ 表现层 ────────────────────────────────────────────────────────┐
│ ProcedureTrimming.vue        委派向导 / 建议分配表 / 建议态 UI    │
│ GtB50RiskAssessment.vue      + 填写完成度提示（加法式）           │
│ 裁剪充分性复核视图（新）      只读，复用决策真源                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ 只传数据，不含判断
┌─ 决策内核（纯函数，零 IO）──────────────────────────────────────┐
│ procedureTrimDecision.ts     单程序 verdict + reason_code + evidence │
│ completenessExemption.ts     完整性豁免两级判据                   │
│ trimAggregateGate.ts         汇总闸                              │
│ delegationSuggestion.ts      建议分配算法                        │
└──────────────────────┬──────────────────────────────────────────┘
                       │ 输入由取数层备好
┌─ 取数层（后端 additive）────────────────────────────────────────┐
│ trim_decision_context.py     一次性装配三维判据上下文             │
│ b50_risk_reader.py           + balance / category / is_estimate  │
│ workpaper_entry_probe.py     底稿是否已有录入（批量）             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌─ 写入层（既有，不改契约）───────────────────────────────────────┐
│ canonical trim preview/apply    ProcedureDelegationService       │
└─────────────────────────────────────────────────────────────────┘
```

### 为什么决策内核放前端纯函数而不是后端服务

裁剪是**交互式决策**：审计师在页面上切换循环、逐条驳回建议、调整完整性清单后要立刻看到重算结果。若决策在后端，每次交互都要往返一次，且「建议态」这种未落库的中间状态无处存放。

因此：**判据数据由后端一次性装配下发（`trim_decision_context`），决策在前端纯函数完成，确认后的结果经既有 canonical 路径落库。** 决策函数零 IO、零 Vue 依赖，可直接单测与变异检验。

代价是决策逻辑只在前端一份 —— 通过两条措施控制：① 判据数据的**取数**在后端并有守卫钉死口径 ② 决策纯函数有完整 PBT + 变异检验，且 `reason_code` 真源前后端交叉锁死。

### 数据缺失的三态贯穿

| 维度 | 数据可用 | 数据缺失 | 禁止的做法 |
|---|---|---|---|
| 重要性 | 产生 `below_trivial` / `below_materiality` 建议 | 整体跳过该维度 + 摘要标注 | 用 `overall_materiality` 推算实际执行重要性 |
| 风险 | 特别风险/高风险保护 + 完整性认定豁免 | 整体跳过 + 退回循环级清单 + 摘要标注 | 把「未填」当「低风险」 |
| 数据存在性 | 现有 `no_data` 自动裁 | 阻断裁剪（现有兜底） | 把「读不到」当「无数据」 |
| 单科目风险未知 | — | `risk_unknown`：不享受保护也不因风险被裁 | 按低风险处理 |

摘要标注与实际执行必须一致（Requirement 4.5），由守卫钉死 —— 这是防「假装做了联动」。

## Components and Interfaces

### 1. `composables/procedureTrimDecision.ts`（新建，前端纯函数）

```typescript
export type TrimVerdict = 'keep' | 'auto_trim' | 'suggest_trim'

export interface TrimDecisionInput {
  /** 程序属性 */
  procedure: {
    wpCode: string
    cycle: string
    isMandatory: boolean
    executionStatus: string | null
    hasManualReason: boolean
    suggestionRejected: boolean
    hasWorkpaperEntry: boolean
  }
  /** 科目金额；null = 该科目未在试算表出现 */
  accountAmount: number | null
  /** 科目级数据可用性（registry 覆盖时优先于循环级） */
  subjectDataState: 'with_data' | 'no_data' | 'unknown'
  cycleHasData: boolean
  /** 重要性；整体为 null 表示该维度不可用 */
  materiality: { performanceMateriality: number; trivialThreshold: number } | null
  /** B50 该科目结论；null = B50 无该科目 */
  risk: {
    maxRisk: 'H' | 'M' | 'L' | null
    hasSpecial: boolean
    completenessRmm: 'H' | 'M' | 'L' | null
    completenessSpecial: boolean
    approach: 'substantive' | 'combined' | null
    reliance: string | null
  } | null
  /** B50 是否有任何已评估科目（决定风险维度整体可用性） */
  riskDimensionAvailable: boolean
  /** 完整性豁免的循环级判据（已合并项目覆盖） */
  completenessSensitiveCycle: boolean
  completenessSource: 'assertion' | 'cycle_default' | 'cycle_override'
}

export interface TrimDecision {
  verdict: TrimVerdict
  reasonCode: TrimReasonCode | null
  /** 面向审计师的一句话说明，含判据数值 */
  narrative: string
  evidence: TrimEvidence
  /** 附加提示（如"拟不信赖内部控制，实质性程序需加强"） */
  hints: string[]
}

export function decideTrim(input: TrimDecisionInput): TrimDecision
```

决策顺序（前者命中即短路，对应 Requirement 3.2）：

1. 风险保护：`risk.hasSpecial || risk.maxRisk === 'H'` → `keep`
2. 强制保留：`isMandatory` / A·S 循环 / `executionStatus ∈ {in_progress, completed, reviewed}` / `hasManualReason` / `hasWorkpaperEntry` / `suggestionRejected` → `keep`
3. 非科目余额驱动循环 → `keep`
4. 数据存在性：`subjectDataState === 'no_data'`（或循环级无数据）→ `auto_trim` + `no_data`
5. 完整性豁免命中 → `keep`（不进入重要性判据）
6. `materiality === null` → `keep`（重要性维度不可用）
7. `|accountAmount| < trivialThreshold` → `suggest_trim` + `below_trivial`
8. `|accountAmount| < performanceMateriality` → `suggest_trim` + `below_materiality`
9. 默认 → `keep`；若 `approach === 'substantive'` 且不信赖控制则附提示

`evidence` 记录本次实际用到的数值与来源标识，供理由留痕与复核追溯。

### 2. `composables/completenessExemption.ts`（新建，前端纯函数）

```typescript
export interface CompletenessCycleRule {
  cycle: string
  /** 默认是否视为完整性敏感 */
  sensitiveByDefault: boolean
  /** 审计依据（不得为空，Requirement 5.4） */
  rationale: string
}

/** 平台默认清单（声明式真源，Requirement 5.3） */
export const COMPLETENESS_CYCLE_RULES: readonly CompletenessCycleRule[]

export interface CompletenessExemptionResult {
  exempt: boolean
  source: 'assertion' | 'cycle_default' | 'cycle_override' | 'none'
  /** 用于复核视图标注"使用平台默认，未经本项目确认" */
  usingPlatformDefault: boolean
  rationale: string
}

export function resolveCompletenessExemption(args: {
  completenessRmm: 'H' | 'M' | 'L' | null
  completenessSpecial: boolean
  cycle: string
  projectOverride: Record<string, boolean> | null
}): CompletenessExemptionResult
```

判据优先级（Requirement 5.8）：**认定级优先** —— 若 `completenessRmm` 非 null 或 `completenessSpecial`，则只按认定判定（`H` 或 special ⇒ 豁免），完全不看循环级清单；仅当该科目在 B50 无完整性认定评估时才退回循环级。

默认清单取值（Requirement 5.3，每条附 `rationale`）：

| cycle | sensitiveByDefault | rationale 要点 |
|---|---|---|
| L 债务 | true | 表外负债与未记录负债是最经典的完整性风险，账面小恰是要查的对象 |
| J 职工薪酬 | true | 应付薪酬/福利/社保少记，可与人数勾稽独立验证 |
| N 税金 | true | 应交税费少记（含滞纳金、未申报），后果含税务处罚 |
| K 管理 | true | 其他应付款常是未记录负债的藏身处 |
| D 收入 | true | 截止期完整性（跨期少记）成立；用户裁决「默认开 + 项目组可关」 |
| E 货币资金 | false | 主风险为存在与估值；另有函证完整性程序覆盖 |
| F 存货 | false | 主风险为存在与估值，金额低于重要性时敞口小 |
| G 投资 | false | 同上 |
| H 固定资产 | false | 同上 |
| I 无形资产 | false | 同上 |
| M 权益 | false | 同上 |

B/C/A/S 不在清单内（非科目余额驱动，本判据不适用）。

### 3. `composables/trimAggregateGate.ts`（新建，前端纯函数）

```typescript
export interface AggregateGateResult {
  applicable: boolean          // 重要性缺失时为 false
  distinctAccountCount: number
  totalAmount: number          // 按科目去重后的绝对值合计
  threshold: number | null
  blocked: boolean             // totalAmount >= threshold
  narrative: string
}

export function evaluateAggregateGate(args: {
  /** 因重要性原因被建议/已确认裁剪的项（含科目名与金额） */
  items: { accountName: string; amount: number; reasonCode: TrimReasonCode }[]
  performanceMateriality: number | null
}): AggregateGateResult
```

三条易被"优化"掉的约束（对应 Requirement 7.4/7.5/7.2，均有变异检验）：只计入重要性类 `reason_code`、按科目名去重、判据是 `>=` 而非 `>`。

### 4. `composables/delegationSuggestion.ts`（新建，前端纯函数）

```typescript
export interface DelegationSuggestionInput {
  workpapers: { wpIndexId: string; wpCode: string; cycle: string; riskLevel: 'H' | 'M' | 'L' | null; rowCount: number }[]
  members: { staffId: string; role: string; currentWeightedLoad: number }[]
  riskDimensionAvailable: boolean
}

export interface DelegationAssignment {
  wpIndexId: string
  assigneeStaffId: string
  reviewerStaffId: string | null
  /** 为何这样分（供审计师判断是否接受） */
  rationale: string
}

export interface DelegationSuggestionResult {
  assignments: DelegationAssignment[]
  loadAfter: Record<string, number>
  /** riskDimensionAvailable=false 时标注"未做风险匹配" */
  degraded: boolean
  warnings: string[]
}

export function suggestDelegation(input: DelegationSuggestionInput): DelegationSuggestionResult
```

算法（Requirement 11.2–11.5）：按风险降序 → 每张底稿选「资历满足该风险等级要求 且 加权负载最小」的成员 → 复核人取「资历不低于执行人 且 非执行人本人」中负载最小者 → 累加负载后继续。风险维度不可用时退化为纯负载均衡并置 `degraded = true`。

权重：`weight = 1 + riskCoefficient + rowCount / 20`，`riskCoefficient` 取 `H:1.0 / M:0.5 / L:0.2 / null:0.3`。

### 5. `backend/app/services/trim_decision_context.py`（新建，取数装配）

```python
async def build_trim_decision_context(
    db: AsyncSession, project_id: UUID, year: int, cycles: list[str]
) -> dict:
    """一次性装配三维判据上下文（只读，fail-soft 但不静默伪装）。

    返回:
      {
        "accounts": {科目名: {"amount": float, "cycle": str}},
        "materiality": {"performance_materiality": float, "trivial_threshold": float} | None,
        "risk": {科目名: {...b50_risk_reader 科目项...}} ,
        "risk_dimension_available": bool,
        "completeness_override": {cycle: bool} | None,
        "workpaper_entry": {wp_code: bool},
        "degradations": [{"dimension": str, "reason": str}],
      }
    """
```

四条约束：① 任一维度取数失败 → 该维度置 `None` 并往 `degradations` 记一条，**不抛异常也不伪造默认值** ② 试算表读取失败保持现有阻断兜底 ③ `workpaper_entry` 批量一次查询（Requirement 9.4） ④ `degradations` 是前端摘要标注的唯一来源（Requirement 4.5 的一致性由此结构性保证）。

### 6. `b50_risk_reader.load_b50_accounts()` additive 扩展

新增解析三个键并填入返回项：`B50-T3-balance-{account}` → `balance`（取 `remark` 转 float，失败为 `None`）/ `B50-T3-category-{account}` → `category` / `B50-T3-estimate-{account}` → `is_estimate`。

`_parse_matrix_item_id` 的 `body == item_id` 守卫**必须保留**（它是这三个键不被误判成矩阵单元格的唯一保障，Requirement 1.4）。既有 cycle/plan/matrix 解析分支逐字不动（Requirement 1.5）。

### 7. `backend/app/services/workpaper_entry_probe.py`（新建）

```python
async def probe_workpaper_entries(
    db: AsyncSession, project_id: UUID, wp_codes: list[str]
) -> dict[str, bool]:
    """批量判定各 wp_code 对应底稿是否已有实质录入。

    判据 = 该底稿存在 checklist_responses 行（conclusion 或 remark 非空）
           或 working_paper.parsed_data 非空。
    查询失败 → 全部返回 True（保守保留，Requirement 9.5）并记 WARNING。
    """
```

### 8. 前端 UI 改动点

| 组件 | 改动 | 性质 |
|---|---|---|
| `ProcedureTrimming.vue` | 建议态列与视觉状态、逐条/批量确认与驳回、汇总闸提示、B50 状态徽标与跳转、完整性清单覆盖入口、摘要降级标注 | 主要改动面 |
| 委派向导（同文件） | 展示 `membership_load` / `affected_workpapers`；负载改读后端口径 | 加法式 |
| 建议分配表（新组件） | 底稿粒度分配表 + 逐行调整 + 负载对比条 | 新建 |
| `GtB50RiskAssessment.vue` | 填写完成度面板（已导入/已评估/未评估清单 + 定位） | 加法式，不碰录入逻辑 |
| 裁剪充分性复核视图（新组件） | 只读复核视图 | 新建 |

`assigneeLoadMap` 的前端自算实现删除，改读后端（Requirement 10.3）。

## Data Models

### 持久化落点决策

三处新状态需要持久化，各自落点与理由：

| 状态 | 落点 | 理由 |
|---|---|---|
| 完整性清单项目级覆盖（R5.5） | `checklist_responses`，键 `B50-T3-cscope-{cycle}`（`conclusion` = `Y`/`N`，`remark` = 覆盖理由） | 它本质是**风险评估判断**而非裁剪操作：与 B50 同生命周期、有 `updated_by`/`updated_at`、B50 审批锁定后自动只读、零迁移。已验证该键前缀不会被 `load_b50_accounts` 的任何分支误解析（`body == item_id` 守卫 + 不匹配 `cycle-`/`plan-` 前缀）。⚠️ 该表**只保留当前值**（`updated_by` 是最后一次修改者），**不保留多次覆盖的历史**；R5.5 因此只要求记录最后一次的 who/when/why，需要完整变更历史属另一议题 |
| 建议驳回标记（R6.4） | **新增迁移**给 `procedure_instances` 加 `suggestion_state` jsonb | 它跟着**程序实例**走而非跟着方案快照走。`procedure_trim_schemes.trim_data` 的键空间是 procedure_instance UUID、且是带日期的历史方案快照（实测 `裁剪方案-D-20260706` 等多份），把当前状态塞进历史快照语义错位 |
| 裁剪理由码（R8.1） | 复用 `procedure_instances.skip_reason` + 新增 `suggestion_state` 内的 `reason_code` 键 | 避免为一个枚举再加一列；`skip_reason` 保持存量可读（R8.4） |

### 迁移

```sql
-- V{next}__add_procedure_instance_suggestion_state.sql
ALTER TABLE procedure_instances
  ADD COLUMN IF NOT EXISTS suggestion_state JSONB;
```

`suggestion_state` 结构：

```json
{
  "reason_code": "below_materiality",
  "rejected": false,
  "rejected_by": null,
  "rejected_at": null,
  "evidence": { "account_amount": 12345.67, "threshold_kind": "performance_materiality", "threshold": 500000.0, "risk_level": null, "completeness_source": "cycle_default" }
}
```

🔴 迁移号在实现时取当前最大 +1（实测最高为 V144，但并发 spec 可能已占用，**落地前必须重查 `schema_version` 与 `backend/migrations/` 目录**，迁移号永不复用）。新增列必须同步加 ORM `mapped_column`，否则该列在表里存在但代码写不进去。

### 理由码真源

```python
class TrimReasonCode(str, Enum):
    NO_RELATED_BUSINESS = "no_related_business"
    NO_DATA = "no_data"                      # 新增
    BELOW_TRIVIAL = "below_trivial"          # 新增
    BELOW_MATERIALITY = "below_materiality"  # 新增
    LOW_RISK_ASSESSMENT = "low_risk_assessment"
    COVERED_ELSEWHERE = "covered_elsewhere"  # 新增
    OTHER = "other"
```

在 `procedure_trim_engine.py` 既有枚举上 additive 扩展（细裁已在用，粗裁改为共用同一枚举，Requirement 8.2）。前端 `trimReasonCodes.ts` 镜像该枚举，守卫读 py 源码交叉锁死（Requirement 8.7）。

### 既有模型不变

`procedure_instances` 除新增一列外字段不变；`procedure_trim_schemes.trim_data` 结构不变；委派侧 `procedure_row_tasks` / `workpaper_delegation_history` 不变；`materiality` / `risk_assessments` 表不变（本设计不写这两张表）。

## Error Handling

| 场景 | 处置 | 对应需求 |
|---|---|---|
| 试算表读取失败或零科目 | 阻断裁剪并提示（保持现有兜底） | 4.4 |
| 重要性记录缺失 | 该维度跳过 + `degradations` 记一条 + 摘要标注 | 4.1 |
| `performance_materiality` 缺失但 `overall_materiality` 存在 | 仍按缺失处理，**不推算** | 4.6 |
| B50 无任何已评估科目 | 风险维度跳过 + 标注 | 4.2 |
| B50 有数据但缺某科目 | 该科目 `risk_unknown`，不保护也不裁 | 4.3 |
| 底稿录入探测失败 | 全部按"可能有录入"保守保留 + WARNING | 9.5 |
| 完整性清单覆盖读取失败 | 退回平台默认 + 标注"未经本项目确认" | 5.6 |
| 附注章节定位失败 | 跳过并记录，不阻断裁剪保存 | 13.6 |
| 委派 preview 过期/版本变化 | 保持现有 409 + 重新预览提示 | 14.1 |
| 汇总闸阻断 | 阻断批量确认但允许逐条 | 7.3 |

统一原则：**取数失败一律降级为"该维度不可用"并如实告知，绝不用默认值伪装成已联动**。

## Testing Strategy

| 层次 | 内容 | 位置 |
|---|---|---|
| 前端纯函数单测 | `decideTrim` 决策顺序逐条、完整性豁免两级、汇总闸三约束、建议分配算法 | `composables/__tests__/procedureTrimDecision.spec.ts` 等 |
| PBT | 决策顺序短路性质、豁免优先级、汇总闸去重与阈值方向、分配算法负载单调性 | 同上（`max_examples` 20） |
| 后端单测 | `load_b50_accounts` 三字段解析 + 既有三类键零回归、`build_trim_decision_context` 降级路径、`probe_workpaper_entries` 批量与失败兜底 | `backend/tests/procedure_trim/` |
| 交叉锁死 | 前端 `trimReasonCodes.ts` 读后端 py 源码比对枚举；完整性清单 rationale 非空 | 前端守卫 |
| 变异检验 | 移除风险保护 / 移除汇总闸去重 / `>=` 改 `>` / 移除认定级优先 / 移除 `body == item_id` 守卫 / 摘要标注与执行不一致 —— 全部必须打红 | `mutate_trim_decision_guards.py` |
| 零回归 | `no_data` 自动裁集合与改造前逐条一致；委派 preview/apply 契约字段不变 | characterization 测试 |
| 真实库验收 | 覆盖"有重要性无 B50"、"无重要性无 B50"、"有试算表数据"三种项目状态 | `backend/scripts/diagnose/verify_trim_decision_live.py`（只读） |
| 浏览器实测 | 建议态展示、逐条与批量确认、汇总闸阻断、委派建议分配表、负载对比 | chrome-devtools + postgres 交叉核实 |

## Correctness Properties

### Property 1: 特别风险与高风险不受金额豁免

对任意输入，若 `risk.hasSpecial === true` 或 `risk.maxRisk === 'H'`，则 `decideTrim` 返回的 `verdict` 恒为 `keep`，与 `accountAmount` 及重要性取值无关。移除该保护的变异必须被打红。

**Validates: Requirements 3.3, 14.3**

### Property 2: 重要性类判据永不产生自动裁

对任意输入，若返回的 `reasonCode ∈ {below_trivial, below_materiality}`，则 `verdict` 恒为 `suggest_trim`，绝不为 `auto_trim`。反向：`verdict === 'auto_trim'` 时 `reasonCode` 恒为 `no_data`。

**Validates: Requirements 3.6, 3.7, 3.8, 6.2, 6.7**

### Property 3: 禁用 PM/TE/SAT 缩写

本 spec 新增的前后端源文件中，剥除注释后不得出现 `pm` / `te` / `sat` 作为标识符（变量名、字段名、属性名）；重要性字段一律为 `performance_materiality` / `trivial_threshold` / `overall_materiality`。反向自检：`GtB50RiskAssessment.vue` 内既有的这些命名不在扫描面内。

**Validates: Requirements 3.8, 7.2**

### Property 4: 整体重要性不作为裁剪判据

`decideTrim` 的输入类型中不存在 `overall_materiality` 字段，且实现体不引用它。

**Validates: Requirements 3.8, 4.6**

### Property 5: 决策顺序短路性

对任意输入，命中靠前判据时靠后判据的取值变化不改变 `verdict`。具体：风险保护命中时改变 `accountAmount`/`materiality` 结果不变；数据存在性命中时改变重要性结果不变。

**Validates: Requirements 3.2, 3.11**

### Property 6: 完整性认定优先于循环级

若 `completenessRmm` 非 null 或 `completenessSpecial === true`，则 `resolveCompletenessExemption` 的结果与 `projectOverride` 及循环级默认清单无关，且 `source === 'assertion'`。

**Validates: Requirements 5.1, 5.8**

### Property 7: 循环级清单仅在认定缺失时生效

若 `completenessRmm === null` 且 `completenessSpecial === false`，则结果 `source ∈ {cycle_default, cycle_override, none}`，绝不为 `assertion`。

**Validates: Requirements 5.2**

### Property 8: 完整性清单每条都有审计依据

`COMPLETENESS_CYCLE_RULES` 每条的 `rationale` 长度 ≥ 20 且非占位文本；清单覆盖 D/E/F/G/H/I/J/K/L/M/N 全部十一个科目余额驱动循环，不含 A/B/C/S。

**Validates: Requirements 5.3, 5.4**

### Property 9: 平台默认标注与覆盖状态一致

`usingPlatformDefault === true` 当且仅当 `source === 'cycle_default'`；`source === 'cycle_override'` 时该标志恒为 `false`。

**Validates: Requirements 5.6, 5.7**

### Property 10: 汇总闸只计重要性类且按科目去重

`evaluateAggregateGate` 的 `totalAmount` 仅累加 `reasonCode ∈ {below_trivial, below_materiality}` 的项，且同一 `accountName` 只计一次；`distinctAccountCount` 等于去重后科目数。移除去重或纳入 `no_data` 的变异必须被打红。

**Validates: Requirements 7.1, 7.4, 7.5, 7.7**

### Property 11: 汇总闸阈值方向

`blocked === true` 当且仅当 `threshold !== null && totalAmount >= threshold`；把 `>=` 改成 `>` 的变异必须被打红。`performanceMateriality === null` 时 `applicable === false` 且 `blocked === false`。

**Validates: Requirements 7.2, 7.3, 7.6**

### Property 12: 降级标注与实际执行一致

若 `degradations` 含 `dimension === 'materiality'`，则该次决策集合中不存在 `reasonCode ∈ {below_trivial, below_materiality}` 的项；若含 `dimension === 'risk'`，则不存在因风险保护而 `keep` 的项（`evidence.risk_level` 恒为 null）。反之亦然。

**Validates: Requirements 4.1, 4.2, 4.5, 14.7**

### Property 13: 风险未知既不保护也不裁

当某科目 `risk === null` 而 `riskDimensionAvailable === true` 时，该科目不因风险获得 `keep`，也不因风险被裁，且 `evidence` 含 `risk_unknown` 标记。

**Validates: Requirements 4.3**

### Property 14: 实际执行重要性缺失时不推算

当 `materiality === null` 时，无论上下文是否存在 `overall_materiality`，决策结果中不出现重要性类 `reasonCode`。

**Validates: Requirements 4.6**

### Property 15: 底稿已录入必保留

当 `hasWorkpaperEntry === true` 时 `verdict` 恒为 `keep`，与 `executionStatus` 无关；特别地「`executionStatus` 为待执行 + `hasWorkpaperEntry` 为真」这一组合必须判 `keep`。

**Validates: Requirements 9.1, 9.2, 9.3, 9.5, 9.6**

### Property 16: 驳回不再被重新建议

当 `suggestionRejected === true` 时 `verdict` 恒为 `keep`，且不产生任何 `suggest_trim`。

**Validates: Requirements 6.4**

### Property 17: 建议态不改变适用性

建议态的产生路径中不存在对程序适用性状态的写入；只有确认动作才调用 canonical trim 写入路径。源码级断言：产生建议的函数体内不出现适用性写入调用。

**Validates: Requirements 6.1, 6.2, 6.3, 6.6**

### Property 18: 确认后理由含判据数值

用户确认建议后生成的裁剪理由文本中包含科目金额与所用重要性阈值的数值，且 `suggestion_state.evidence` 与该文本数值一致。

**Validates: Requirements 3.10, 6.5**

### Property 19: 理由码前后端交叉锁死

前端 `trimReasonCodes.ts` 的取值集合与后端 `TrimReasonCode` 枚举逐值相等（守卫读 py 源码）；一侧新增而另一侧未跟进即打红。

**Validates: Requirements 8.1, 8.2, 8.3, 8.5, 8.7, 14.5**

### Property 41: 理由码与状态同一次写入且 additive

裁剪确认路径中，理由码与 `target_status` 在同一个 canonical apply 请求内提交；不存在「先 apply 状态、再单独写理由码」的第二次写入调用。反向：scope entry 未携带 `reason_code` 时，preview 与 apply 的请求 payload 与改造前逐字节相同（存量调用方零影响）。

**Validates: Requirements 8.8, 8.9**

### Property 20: 存量自由文本理由可读

引入理由码后，`suggestion_state` 为 null 而 `skip_reason` 非空的存量记录仍显示原理由文本，不显示为空或"未知理由"。

**Validates: Requirements 8.4**

### Property 21: B50 三字段 additive 且未录入为 None

`load_b50_accounts()` 对未录入 `balance`/`category`/`estimate` 的科目返回 `None`（非 0、非空串）；对既有 cycle/plan/matrix 三类键的解析结果与扩展前逐字节相同。

**Validates: Requirements 1.1, 1.2, 1.3, 1.5, 1.6, 14.6**

### Property 22: 非矩阵键不被误判为矩阵单元格

`_parse_matrix_item_id()` 对 `B50-T3-balance-*` / `-category-*` / `-estimate-*` / `-cscope-*` 一律返回 `None`；移除 `body == item_id` 守卫的变异必须被打红。

**Validates: Requirements 1.4, 14.3**

### Property 23: 完整性覆盖键不污染 B50 解析

`checklist_responses` 中形如 `B50-T3-cscope-{cycle}` 的行不会改变 `load_b50_accounts()` 的任何输出（既不产生科目项，也不改变既有科目项字段）。

**Validates: Requirements 1.5, 5.5**

### Property 24: B50 完成度三态与前后端同口径

完成度判定为纯函数；`未开始` ⟺ 导入科目数为 0；`已完成` ⟺ 每个导入科目至少一个认定有 RMM；其余为 `部分完成`。裁剪页徽标与 B50 面板取同一函数结果。

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

### Property 25: 委派负载单一口径

前端不存在自行计算成员负载的实现（源码级断言：无按底稿计数聚合负载的逻辑）；所有负载展示读后端下发值；取值缺失时显示"负载未知"而非 0。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7**

### Property 26: 建议分配满足职责分离

`suggestDelegation` 输出的每条 `assignment` 满足 `reviewerStaffId !== assigneeStaffId`（或 reviewer 为 null）；不存在把同一人同时排为执行人与复核人的输出。

**Validates: Requirements 11.1, 11.2, 11.3, 11.5, 11.6**

### Property 27: 建议分配负载单调性与降级标注

分配后各成员 `loadAfter` 不小于其 `currentWeightedLoad`，且总增量等于所分配底稿的权重之和；`riskDimensionAvailable === false` 时 `degraded === true` 且 warnings 含未做风险匹配的说明。

**Validates: Requirements 11.4, 11.8, 11.9, 11.10**

### Property 28: 委派写入路径唯一

建议分配表的应用复用既有 `ProcedureDelegationService` 的 preview → apply；源码级断言：本 spec 不新增任何直接写 `procedure_row_tasks` 分配字段的代码路径。

**Validates: Requirements 11.7, 14.1**

### Property 29: 复核视图只读且同源

裁剪充分性复核视图不含任何写入调用；其统计数值由裁剪决策的同一真源派生（相同输入下与裁剪页统计逐项相等）。

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7**

### Property 30: 附注联动加法式且不覆盖人工内容

附注不适用标注不删除章节或模板结构；当该章节存在人工录入内容时只提示不自动标注；标注前后既有附注同步链路输出逐字节不变。

**Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7**

### Property 31: `no_data` 零回归

对同一项目同一年度，改造后按 `no_data` 自动裁剪的程序集合与改造前逐条相同。

**Validates: Requirements 14.2**

### Property 32: 既有保留判据行为保持

`is_mandatory` / A·S 循环 / `executionStatus ∈ {in_progress, completed, reviewed}` / 已手动填写理由 / 非科目余额驱动循环 —— 这五类在改造前后均判 `keep`，且判定结果与新增的重要性、风险、完整性判据取值无关。

**Validates: Requirements 3.4, 3.5**

### Property 33: 决策结果结构完备

`decideTrim` 的返回值恒包含 `verdict` / `reasonCode` / `narrative` / `evidence` / `hints` 五个键；`verdict === 'keep'` 时 `reasonCode` 为 `null`，其余两种 verdict 时 `reasonCode` 非 `null`。

**Validates: Requirements 3.1**

### Property 34: 试算表不可用时阻断而非全裁

当试算表读取失败或返回零科目时，`build_trim_decision_context` 返回的上下文使前端阻断裁剪（不产生任何 `auto_trim`），且提示文案区分「读取失败」与「试算表未导入」两种成因。复现旧行为（把不可用当无数据）的替身必须被打红。

**Validates: Requirements 4.4**

### Property 35: 裁剪方案导出含理由码与文本

导出的裁剪方案每一行同时含理由码列与理由文本列；系统建议裁剪的行理由码非空，纯人工自由文本的存量行理由码列为空而文本列非空。

**Validates: Requirements 8.6**

### Property 36: 底稿录入探测批量化

`probe_workpaper_entries` 对 N 个 wp_code 的查询次数与 N 无关（不随程序数增长）；源码级断言：其实现体内不存在按 wp_code 循环发查询的结构。

**Validates: Requirements 9.4**

### Property 37: 守卫与变异检验完备

汇总闸、完整性豁免、决策顺序三处各有守卫文件；变异脚本对每一处至少施加一个有效变异并被打红，且变异后源文件字节级还原。变异脚本须区分三态（RED / GREEN=守卫缺陷 / ANCHOR-MISS=脚本缺陷），锚点命中数必须为 1。

**Validates: Requirements 14.4**

### Property 38: 真实库三状态验收

真实库诊断脚本覆盖并如实报告三种项目状态：有重要性无 B50、无重要性无 B50、有试算表数据。任一状态在库中不存在时脚本输出 `UNVERIFIABLE` 而非用 fixture 冒充通过。

**Validates: Requirements 14.8**

### Property 39: 浏览器实测与数据复原

浏览器实测覆盖建议态展示、逐条确认、批量确认、汇总闸阻断、委派建议分配表、负载对比六项；实测后数据复原以**独立查询**核实（不看操作脚本自身输出），复原判据含 `suggestion_state` 为 null、`skip_reason` 与基线逐字相等、`checklist_responses` 行数回到基线。

**Validates: Requirements 14.9, 14.10**

### Property 40: 拟不信赖控制时保留并提示

当 B50 该科目 `approach === 'substantive'` 且 `reliance` 为不信赖时，`verdict` 为 `keep` 且 `hints` 含「实质性程序需加强」类提示；该提示不改变 verdict 本身（即不因有提示而变成裁剪）。

**Validates: Requirements 3.9**
