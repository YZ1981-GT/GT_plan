# Design — 截止性测试架构收敛

## Overview

本设计把截止性测试的**五套判定函数、三套证据模型、两套后端端点、多套结论口径**收敛为单一真源，采用 strangler（绞杀者）模式分步迁移，每步零回归。核心是：先建纯函数 canonical 层（判定/窗口/状态机），再统一前端证据模型薄封装各底稿，再收敛后端端点到富引擎并补齐全量统计，最后统一下游联动并加契约守卫。

设计遵循代码决策阶梯：优先**收敛复用**已有富实现（`LedgerSamplingService` 富引擎、`cutoff-extract` 的 `StatsResult` 全量统计已就绪），不新造引擎；判定收敛为**纯函数单一模块**，不引入新依赖。

## Architecture

```
┌──────────────────────── 前端 ────────────────────────┐
│  cutoffCanonical.ts (纯函数单一真源)                   │
│   ├─ computeWindow(cutoffDate, before, after)          │  ← 替代 computeDateRange/filterByCutoffWindow 窗口
│   ├─ inWindow(date, cutoffDate, before, after)         │
│   ├─ judgeCrossPeriod({recordDate, documentDate}, cd)  │  ← 替代 isCutoffPeriodCrossing/markCutoffCrossPeriod/isCrossPeriod
│   └─ deriveConclusion(sample, cd) → CutoffConclusion   │  ← 统一 6 态状态机 (Req4)
│                                                         │
│  useCutoffSample (canonical 证据模型 + 适配器)          │  ← 统一 CutoffSample (Req2)
│   ├─ CutoffSample { book*, doc* 两侧独立字段 }          │
│   ├─ fromCycleRow / fromK8Row / fromK9Row (别名映射)    │
│   └─ toXxxRow (回写各底稿, 迁移不丢数据)                │
│                                                         │
│  调用方薄封装 (语义等价迁移, 保留各自 UI):              │
│   useCycleCutoff / useK8Cutoff / useK9Cutoff /          │
│   useCutoffAutoSampling → 全部委托 cutoffCanonical      │
└─────────────────────────────────────────────────────────┘
                          │ 单一 canonical 端点
                          ▼
┌──────────────────────── 后端 ────────────────────────┐
│  LedgerSamplingService (富引擎, 唯一真源)              │  ← Req1/Req5
│   ├─ build_ledger_query (前缀匹配/direction/keyword)   │
│   ├─ execute_with_stats → items + StatsResult(全量)    │  ← amount_total 已全量, truncated 透明
│   └─ 全量统计口径供覆盖率/MUS                           │
│                                                         │
│  POST /sampling/cutoff-extract  (canonical 端点)        │
│  POST /sampling/cutoff-test     (薄委托 → 富引擎)       │  ← Req1.2 保持响应契约
│  GET/POST cutoff-history/undo/fill (extraction_type=cutoff 隔离, 已修) │
└─────────────────────────────────────────────────────────┘
```

## 架构决策

| # | 决策 | 理由 | 备选 & 弃因 |
|---|------|------|-------------|
| D1 | 判定收敛为**纯函数模块** `cutoffCanonical.ts`，各调用方薄封装委托 | 纯函数易单测/PBT，零 Vue 依赖，等价迁移风险最低 | 收敛到某个 composable → 引入循环依赖/难测 |
| D2 | 后端以 **`cutoff-extract` 富引擎为唯一真源**，`cutoff-test` 转薄委托 | 富引擎已有全量统计/去重/前缀/分页；简单引擎是能力子集 | 反向（extract 委托 test）→ 丢失富能力，违背 Req5 |
| D3 | `cutoff-test` **保留为薄委托而非直接删除** | K8/K9/useCycleCutoff 已在调它；同签名委托可零回归迁移，之后再按序废弃 | 直接删除 → 破坏现有调用方，违背 Req7 |
| D4 | 前端 canonical **证据模型 + 适配器**，不推倒各底稿 UI | 三底稿 UI 成熟；仅统一数据/判定层，适配器保数据不丢 | 统一 UI 组件 → 超大改，回归面过宽 |
| D5 | 结论状态机 6 态，各底稿现有中文字面量**映射**而非替换存储 | 已保存数据向后兼容，迁移不改语义归类 | 直接改存储枚举 → 历史数据错位 |
| D6 | **strangler 分步**：判定→模型→状态机→后端端点→联动→守卫，每步全绿 | 大范围重构零回归的唯一安全路径 | 一次性大改 → 不可回退、假绿风险 |
| D7 | 单日期降级语义**保留**（缺一侧不直接判正常/跨期） | 与 P0 证据门禁一致；自动取数仅得记账侧 | 缺侧强判 → 假绿，违背 Req2/Req3.3 |

## Data Models

### CutoffSample（canonical 前端证据模型）

```typescript
interface CutoffSample {
  // 记账侧证据（book side）
  bookDate: string          // 记账凭证日期 YYYY-MM-DD
  bookAmount: number        // 账面金额
  voucherNo: string         // 记账凭证号
  // 原始单据侧证据（document side）—— 与记账侧各自独立取得
  documentDate: string      // 原始单据/支出凭单日期（缺失=空串）
  documentAmount: number    // 原始单据金额（缺失=0，禁止自动复制 bookAmount）
  documentNo: string        // 原始单据号
  // 派生（由 canonical 计算，不入持久化真源）
  summary: string
  conclusion: CutoffConclusion
}
```

字段别名映射（适配器，迁移不丢数据）：

| canonical | useCycleCutoff | useK8Cutoff | useK9Cutoff |
|-----------|----------------|-------------|-------------|
| bookDate | recordDate | bookDate | bookDate |
| bookAmount | amount | amount | amount |
| documentDate | documentDate | sourceDate | sourceDate |
| documentAmount | documentAmount | sourceAmount | （无，恒 0） |
| voucherNo | voucherNo | voucherNo | voucherNo |
| documentNo | documentNo | sourceVoucherNo | sourceVoucherNo |

### CutoffMode（跨期判定模式，Req3.5 保留差异）

```typescript
type CutoffMode = 'cutoff-boundary' | 'natural-month'
// cutoff-boundary：截止日两侧 XOR（I2/I6 useCycleCutoff）— 单日期降级为跨期疑点
// natural-month  ：不同自然会计月（K8/K9）— 与截止日相对位置无关
// 各调用方保持其既有模式，canonical 不统一为单一语义（会改结论，违背零回归）
```

### CutoffConclusion（统一状态机，6 态）

```typescript
type CutoffConclusion =
  | '待追查'        // pending: 样本已列入但两侧证据均未落实
  | '证据不完整'    // incomplete: 缺记账侧或原始单据侧独立证据 → 不得判正常/完成
  | '正常'          // ok: 双侧证据齐全且同期
  | '跨期'          // crossing: 双侧证据齐全且分处截止日两侧
  | '需调整'        // adjust: 跨期且经审计师确认需 AJE
  | '已调整'        // adjusted: 已生成 AJE 草稿并推送 A13
```

现有字面量 → 状态机映射（迁移保语义）：
- '可能跨期'（useCutoffAutoSampling） → '跨期'
- '待检查'（window direction） → '待追查'
- '跨期多记'/'跨期漏记'（useCycleCutoff） → '跨期'（保留子类型于 remark）
- '证据不完整' → '证据不完整'（三处已统一）
- '正常' → '正常'

### 后端（复用既有，无新表）

`StatsResult`（已就绪，含全量 `amount_total`/`truncated`）作为全量抽样框统计口径；`CutoffExtractRequest` 作为 canonical 请求模型；`cutoff-test` 的 `CutoffTestRequest` 转为在路由层映射到 `CutoffExtractRequest` 后委托 `LedgerSamplingService`（薄委托，响应保持既有形状：entries/total_entries/before_cutoff/after_cutoff/period_end/window）。

## Components and Interfaces

### Canonical 判定语义（文档化，Req3.5）

```
computeWindow(cd, before, after) = [cd - before 日, cd + after 日]（闭区间，逐日等价 computeDateRange）
inWindow(d, cd, before, after)   = d ∈ computeWindow(...)（等价 filterByCutoffWindow 的逐元素判定）

judgeCrossPeriod(sample, cd, mode):
  // 🔴 实测发现两套语义不等价，canonical 必须保留两模式（Req3.5 明确保留差异）：
  //   mode='cutoff-boundary'（I2/I6 useCycleCutoff）：双侧日期分处截止日两侧（XOR），等价 isCutoffPeriodCrossing
  //   mode='natural-month'（K8/K9）：两侧日期分属不同自然会计月（year+month 不同），等价 isCrossPeriod
  //   反例：book=2025-11-28, doc=2025-12-28, cd=2025-12-31 → boundary='same'(均≤cd) vs natural-month='crossing'(11月≠12月)
  bookHas = !!sample.bookDate;  docHas = !!sample.documentDate
  IF !bookHas && !docHas        → 'none'（无证据，上层落 待追查/证据不完整）
  IF bookHas XOR docHas         → 'suspect'（单日期降级：唯一有的日期 > cd 视为跨期疑点；等价 markCutoffCrossPeriod 单日期降级）
  IF bookHas && docHas:
     mode='cutoff-boundary': RETURN (bookDate>cd) !== (docDate>cd) ? 'crossing' : 'same'
     mode='natural-month':   RETURN (bookYm !== docYm) ? 'crossing' : 'same'（Ym = year*12+month）

deriveConclusion(sample, cd):
  手工结论优先（若已录入且非默认）
  否则按 judgeCrossPeriod：
    'none' | 'suspect'（缺侧） → '证据不完整'
    'suspect'（双侧但仅单日期语义, 不出现）
    'crossing' → '跨期'
    'same'     → '正常'
```

direction 语义映射（保留，不改结论）：
- `determineCutoffStatus` 的 post_cutoff/pre_cutoff（单方向 + 金额符号）用于 useCutoffAutoSampling 的**预览标注**，映射到 canonical 的 suspect/正常，字面量 '可能跨期'→'跨期'、'待检查'→'待追查'。
- useCycleCutoff 的 forward/backward（账→单据 / 单据→账）仅决定**哪一侧为锚点**展示，不改 judgeCrossPeriod 的双侧对称结论。

## Correctness Properties

*PBT 可测的正确性属性；每条映射到 Requirements，作为等价迁移与零回归的验证锚点。*

### Property 1: 端点等价

*For any* 相同 (cutoff_date, days_before, days_after, account_codes, amount_threshold) 输入，canonical 端点与迁移前 `cutoff-test` 返回**同一窗口凭证集合**（凭证号集合相等）。

**Validates: Requirements 1.3**

### Property 2: 科目前缀匹配

*For any* account_codes 列表，account '6601' 命中 '6601'/'6601.01'/'660101'，不命中 '6602'；精确匹配漏子科目的行为被前缀匹配取代。

**Validates: Requirements 1.4**

### Property 3: 任意截止日窗口

*For any* 合法 cutoff_date（含非 12-31），窗口恒为闭区间 [cutoff_date − days_before, cutoff_date + days_after]。

**Validates: Requirements 1.5, 3.4**

### Property 4: 全量统计不变量

*For any* page_size，`amount_total`/`total_count` 与分页无关（改 page_size 不改全量统计）。

**Validates: Requirements 5.1**

### Property 5: 截断透明

*For any* 超过返回上限的总体，items 被截断 ⇒ `truncated=true` 且 `total_count` 为全量口径。

**Validates: Requirements 5.2**

### Property 6: 双侧证据门禁

*For any* 样本，缺任一侧日期证据 ⇒ `deriveConclusion` ∈ {证据不完整}，绝不为 '正常'。

**Validates: Requirements 2.2, 2.4**

### Property 7: 禁止金额复制

*For any* 样本，documentAmount 缺失 ⇒ 保持 0，不自动等于 bookAmount（除非审计师显式录入相等值）。

**Validates: Requirements 2.3**

### Property 8: 判定单一真源等价（分模式）

*For any* 输入日期对：canonical `judgeCrossPeriod(_, _, 'cutoff-boundary')` 等价 `isCutoffPeriodCrossing`（I2/I6）；`judgeCrossPeriod(_, _, 'natural-month')` 等价 K8/K9 `isCrossPeriod`。两模式语义不同（截止日 XOR vs 自然月），canonical 保留差异不强行统一。

**Validates: Requirements 3.1, 3.2, 3.5**

### Property 9: 单日期降级等价

*For any* 仅单侧日期的样本，canonical 结果与迁移前 `markCutoffCrossPeriod` 单日期降级行为一致。

**Validates: Requirements 3.3**

### Property 10: 窗口边界等价

*For any* (cutoffDate, before, after)，`computeWindow`/`inWindow` 与既有 `computeDateRange`/`filterByCutoffWindow` 逐日一致（含区间端点）。

**Validates: Requirements 3.4**

### Property 11: 状态机完备互斥

*For any* 样本，`deriveConclusion` 恰好映射到 6 态之一（待追查/证据不完整/正常/跨期/需调整/已调整），互斥且完备。

**Validates: Requirements 4.1**

### Property 12: 字面量映射保语义

*For any* 旧结论字面量，`mapLegacyConclusion` 映射到新状态集合且不改变其语义归类（满射保序）。

**Validates: Requirements 4.4**

### Property 13: 完成门禁

*For any* 底稿状态，存在 证据不完整 或未决 跨期 样本 ⇒ 完成标记 ok=false。

**Validates: Requirements 4.3**

### Property 14: exclude_extracted 幂等

*For any* 已填充凭证号集合，后续取数结果中不再出现这些凭证号。

**Validates: Requirements 7.2**

### Property 15: extraction_type 隔离

*For any* 底稿的截止历史/撤销/排除查询，仅涉及 extraction_type='cutoff' 的日志，不混入其它抽样日志。

**Validates: Requirements 7.2**

### Property 16: 单份版本快照

*For any* 一次填充操作，仅创建一份版本快照（后端 cutoff-fill），前端不重复创建。

**Validates: Requirements 7.2**

### Property 17: A13 联动一致

*For any* 含 N 笔跨期样本的底稿，触发推送时 `a13:push-misstatement` 的 items 数 = N；useCycleCutoff 与 K9 payload 结构一致。

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 18: 迁移零回归

*For any* 收敛步骤，所有既有 cutoff 相关测试保持通过。

**Validates: Requirements 7.1**

## 迁移顺序（strangler，每步全绿）

1. **W0 安全网 + canonical 骨架**：characterization 测试锁定五套判定/三套模型现状；新建 `cutoffCanonical.ts`（纯函数，先与既有函数并存，不接线）。
2. **W1 判定收敛**：各调用方逐个迁移到 `cutoffCanonical`（判定/窗口），旧函数转薄封装委托 canonical，每迁一处跑对应测试。
3. **W2 状态机统一**：`deriveConclusion` + 字面量映射；三底稿结论派生走 canonical，完成门禁统一。
4. **W3 证据模型统一**：`CutoffSample` + 适配器；三底稿数据层经适配器读写，UI 保持。
5. **W4 后端全量抽样框 + 端点收敛**：`cutoff-test` 转薄委托 `LedgerSamplingService`（补全量统计/截断透明/去重）；覆盖率/MUS 用全量统计。
6. **W5 前端迁移到 canonical 端点**：K8/K9/useCycleCutoff 的取数改走 canonical 端点（经薄委托或直连 cutoff-extract），保留窗口等价。
7. **W6 下游联动一致**：useCycleCutoff 与 K8/K9 跨期→A13 路径统一（P1 已落 useCycleCutoff，本步核对 K8/K9 一致并补齐缺口）。
8. **W7 守卫 + 差异矩阵**：契约守卫（检测新增绕过 canonical 的并行实现）+ 差异矩阵文档 + 全量回归。

## Testing Strategy

- **前端**：纯函数 canonical 用 fast-check PBT（P1-P13/P17）；各底稿迁移用既有 vitest（i2/i6 cutoff、i6Integration、k8-pbt-cutoff、cutoffAutoSampling、cutoffJudgment）保持全绿（P18）。
- **后端**：`LedgerSamplingService`/`cutoff-test` 薄委托用 hypothesis PBT（P2-P5/P14/P15）+ 既有 cutoff sampling 集成/PBT（P16/P18）。
- **零回归门槛**：每 wave 结束跑全部 cutoff 相关测试；任一红即停在该 wave（Req7.3）。
- **未 Playwright**：I2/I6/K8/K9 需实例化项目方能端到端实测；本 spec 以单测/PBT + 契约守卫为验收，Playwright 作为 optional checkpoint 在有实例化项目时补。

## Error Handling

- canonical 端点非法参数：保持既有回退（cutoff_date 缺省 year-12-31；account_codes 空 → 空集合）。
- 判定输入非法日期：canonical 返回 'none'/'证据不完整'，绝不静默判 '正常'。
- 迁移中适配器遇未知字段：保留原值透传，不丢数据。
