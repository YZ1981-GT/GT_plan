# Design Document

## Overview

修正函证三项覆盖率口径，以**科目审定总额（TB population）**为分母，收敛为单一真源，tooltip/标签与计算严格一致，population 缺失时 Skip-on-missing（显示不可用而非误导数字）。

改动分三层，均为加法式：
1. **后端渲染注入**：`confirmation-summary` 渲染路径向 htmlData.`project_context` 注入 `population_amount`（科目审定总额）。
2. **前端口径修正**：`useConfirmationData.coverageMetrics` 接收 population，产出 `confirmation_coverage` / `confirmed_coverage` / `reply_coverage` / `warn_level`（含 null 分支）。
3. **UI 一致性**：`ConfirmationDashboard` tooltip/标签与计算对齐；population 缺失显示占位。
4. **单一真源收敛**：后端 `GET /confirmations/stats` 死端点（当前零消费者、字段名与前端不符、不接 population）→ **移除**，避免误导后续接入；相关假绿测试同步清理。

## Architecture

```
后端 wp_render_config（confirmation-summary 渲染路径）
  └─ _resolve_confirmation_population(ctx, htmlData_rows)
       ├─ 从 confirmation-v1 rows 提取 distinct account_type（中文科目名）
       ├─ _ACCOUNT_TYPE_TO_CODE_PREFIX 映射 → TB 科目编码前缀集合
       ├─ get_active_filter(TbBalance/trial_balance) + LIKE 前缀 SUM(audited)（负债 abs）
       └─ 无匹配前缀 / SUM 为 0 → None（不臆测）
     → htmlData.project_context.population_amount

前端 GtConfirmationSummary
  └─ population = htmlData.project_context?.population_amount ?? null
     └─ useConfirmationData({ ..., population })
          └─ coverageMetrics (computed)
               ├─ confirmation_coverage = population ? 发函总额/population*100 : null
               ├─ confirmed_coverage    = population ? confirmedTotal/population*100 : null
               ├─ reply_coverage        = repliedCount/sentCount*100（笔数口径）
               └─ warn_level（Req5 规则，population 缺失仅由 reply 决定）
     → ConfirmationDashboard（tooltip/标签对齐 + population 缺失占位）
```

## Components and Interfaces

### 后端：population 解析与注入（Req3）

位于 confirmation-summary 渲染路径（`wp_render_config` / `wp_render_config_helpers`，与既有 `_CONFIRMATION_FORMAT_MAP` 播种同处）。

```python
# 中文科目名 → TB 标准科目编码前缀（confirmation 相关科目 canonical 子集）
_ACCOUNT_TYPE_TO_CODE_PREFIX: dict[str, str] = {
    "库存现金": "1001", "银行存款": "1002", "其他货币资金": "1012",
    "应收票据": "1121", "应收账款": "1122", "预付账款": "1123",
    "其他应收款": "1221", "长期应收款": "1531",
    "应付票据": "2201", "应付账款": "2202", "预收账款": "2203",
    "其他应付款": "2241", "合同负债": "2203",
    "短期借款": "2001", "长期借款": "2501",
}
# 负债/权益类前缀（audited 取绝对值归一为正）
_LIABILITY_PREFIXES = ("2", "3", "4")

async def _resolve_confirmation_population(
    ctx, rows: list[dict]
) -> float | None:
    """从函证行的科目类型解析科目审定总额（Σ 相关科目 TB audited）。

    - 无法映射任一前缀 / SUM 为 0 → None（Req3.3 不臆测）。
    - 复用 get_active_filter + trial_balance.audited_amount（Req3.2）。
    - 负债/权益取 abs（Req1.4）。
    """
    types = {str(r.get("account_type") or "").strip() for r in rows}
    prefixes = {p for t in types if (p := _ACCOUNT_TYPE_TO_CODE_PREFIX.get(t))}
    if not prefixes:
        return None
    # SUM(ABS 按前缀分类) over trial_balance.audited_amount, get_active_filter 数据集隔离
    total = await _sum_tb_audited_by_prefixes(ctx, prefixes, _LIABILITY_PREFIXES)
    return total if total and total > 0 else None
```

注入点：confirmation-summary 渲染时，读取已持久化/播种的 confirmation-v1 htmlData，
若含 rows 则解析 population，`htmlData.setdefault("project_context", {})["population_amount"] = population`。
不改 rows / _format / 其它字段（Req3.4）。

### 前端：coverageMetrics 口径（Req1/Req2/Req5）

`useConfirmationData` 入参新增可选 `population`：

```typescript
interface UseConfirmationDataOptions {
  htmlData: () => any
  readonly: boolean
  population?: () => number | null   // 科目审定总额；null=不可用
}
```

`ConfirmationCoverageMetrics` 扩展（加法式，保留既有字段名）：

```typescript
export interface ConfirmationCoverageMetrics {
  /** 函证覆盖率 = 发函总额 / 科目审定总额；population 缺失=null */
  confirmation_coverage: number | null
  /** 确认覆盖率 =（回函确认+替代确认）/ 科目审定总额；population 缺失=null */
  confirmed_coverage: number | null
  /** 回函覆盖率 = 已回函笔数 / 已发函笔数（笔数口径） */
  reply_coverage: number
  /** 预警等级 */
  warn_level: 'ok' | 'warn' | 'danger'
  /** population 是否可用（供 UI 决定显示占位 vs 百分比） */
  population_available: boolean
}
```

计算（防除零、Skip-on-missing）：

```typescript
const population = props.population?.() ?? null
const sentCount = rows.value.filter(isConfirmationInFlight).length   // 已发函笔数
const repliedCount = rows.value.filter(r => r.is_replied).length
const sentAmount = rows.value.reduce((s, r) => s + (r.amount ?? 0), 0)  // 发函总额
const confirmedTotal = rows.value.reduce((s, r) =>
  s + (r._overridden ? (r.confirmed_amount ?? 0) : computeConfirmedAmount(r)), 0)

const popValid = population != null && population > 0
const confirmation_coverage = popValid ? (sentAmount / population) * 100 : null
const confirmed_coverage    = popValid ? (confirmedTotal / population) * 100 : null
const reply_coverage = sentCount > 0 ? (repliedCount / sentCount) * 100 : 0

let warn_level: 'ok'|'warn'|'danger' = 'ok'
if (reply_coverage < 80) warn_level = 'danger'
else if (confirmation_coverage != null && confirmation_coverage < 50) warn_level = 'warn'
```

### UI：ConfirmationDashboard（Req1.2/Req2.3/Req5.3）

- 回函覆盖率 tooltip 改为「已回函笔数 / 已发函笔数 × 100%（建议 ≥ 80%）」（笔数口径）。
- 函证覆盖率：`population_available` 为 true 显示百分比进度条；false 显示占位「需科目总体金额（TB）方可计算」+ 灰色禁用态。
- 新增确认覆盖率行（可选展示），tooltip「（回函+替代确认）/ 科目审定总额」。
- population 缺失 warn banner：「函证覆盖率因缺科目总体金额未参与预警」。

### 单一真源收敛：移除死端点（Req4）

`GET /projects/{pid}/confirmations/stats`（`confirmation_stats`）当前零前端消费者、字段名 `reply_rate` 与前端 `reply_coverage` 不符、不接 population。**移除该端点**（Req4.3），删除或改写其测试（Req4.4），口径唯一权威落在前端 `coverageMetrics`（Req4.1）。若未来需服务端聚合，另起接 population 的实现。

## Data Models

- `ConfirmationCoverageMetrics`：见上（新增 `confirmed_coverage` / `population_available`，`confirmation_coverage` 改为 `number|null`）。
- `htmlData.project_context.population_amount: number | null`：后端注入，前端只读。

## Correctness Properties

### Property 1: 函证覆盖率分母为 population
WHEN population 可用（>0）THEN `confirmation_coverage === sentAmount / population * 100`。
**Validates: Requirements 1.1**

### Property 2: population 缺失时覆盖率为 null 且不误导
WHEN population 为 null 或 ≤0 THEN `confirmation_coverage === null` AND `confirmed_coverage === null` AND `population_available === false`。
**Validates: Requirements 1.2, 3.3**

### Property 3: 确认覆盖率分子口径
WHEN population 可用 THEN `confirmed_coverage === confirmedTotal / population * 100`，其中 confirmedTotal 用 computeConfirmedAmount/覆盖值。
**Validates: Requirements 1.3**

### Property 4: 负债科目 population 取绝对值
WHEN 科目为负债/权益前缀 THEN population 贡献为 abs(audited)（恒非负）。
**Validates: Requirements 1.4**

### Property 5: 回函覆盖率笔数口径 + 除零
`reply_coverage === (sentCount>0 ? repliedCount/sentCount*100 : 0)`，sentCount=0 时为 0。
**Validates: Requirements 2.1, 2.2**

### Property 6: 已发函笔数复用在途语义
sentCount 由 `isConfirmationInFlight`（或等价 send 状态）判定，非 rows.length。
**Validates: Requirements 2.4**

### Property 7: population 由后端注入且加法式
渲染后 htmlData.rows / _format 逐字节不变，仅新增 project_context.population_amount。
**Validates: Requirements 3.1, 3.4**

### Property 8: population 解析无匹配返回 null
WHEN rows 的 account_type 无一映射到已知前缀 THEN population_amount === null。
**Validates: Requirements 3.3**

### Property 9: 预警等级规则
reply<80→danger；reply≥80 且 confirmation 可用且<50→warn；confirmation 不可用→仅由 reply 决定。
**Validates: Requirements 5.1, 5.2, 5.3**

### Property 10: 死端点移除且无假绿
`GET /confirmations/stats` 路由不存在 AND 无测试断言其返回口径。
**Validates: Requirements 4.3, 4.4**

## Testing Strategy

- **前端单测**（`useConfirmationData.spec.ts` 扩展）：Property1-6/9，含 population=null/0/正数、sentCount=0、负债 abs、warn_level 三分支。
- **后端单测**（新建 `test_confirmation_population.py`）：Property4/7/8，`_resolve_confirmation_population` 纯逻辑（mock TB SUM）+ 映射覆盖 + 无匹配返回 None + 负债 abs。
- **契约/回归**：确认 confirmation-v1 持久化 payload 结构不变（Req6.1）；移除 `/stats` 后既有 test_confirmations_router 相关断言更新（Req4.4/Property10）；get_diagnostics + Vite transform + AST 校验（Req6.4）。
- **零回归**：现有 `useConfirmationData.spec.ts` 中 `reply_coverage` 断言从「repliedCount/totalCount」迁移到「repliedCount/sentCount」——需重算期望值（若测试数据全部 in-flight 则 sentCount==totalCount 期望不变）。

## Error Handling

- population 解析异常（TB 查询失败）→ 捕获返回 None（fail-open，不阻断渲染）。
- population=null 前端全程走「不可用」分支，不抛错、不显示 NaN/Infinity。
