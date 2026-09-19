# Design Document

## Overview

把九套替代程序（D05/D06/F05/F06/H05/K05/K06/L05/G06）的结构对齐致同源模板，并收敛结构债，不加源模板没有的能力。

**实证基线（读码确认）**：
- 八套已走工厂 `createAlternativeConfirmationData(config)`；工厂**固定 `block1_rows`~`block4_rows` 四个区块位**（`BlockType='block1'|'block2'|'block3'|'block4'`），`getBlockTotal`/`getCompletionStatus`/`hasAbnormal` 均遍历这四位。
- 区块列由适配器各自的 `blockColumnConfigs*` 定义；`getSumFields(blockType)` 决定合计字段。
- G06 未纳入工厂。
- 既有底稿 payload 的 `blockN_rows` 是数据映射红线（改 block 位或字段名会丢数据）。

**第一性约束**：工厂固定 4 block 位不动（改它牵动八套 + 既有数据映射）；Occurrence_Block 拆借贷「两张表」在**渲染层**实现（同一 block 内按 `direction` 字段分组渲染两张 el-table），不占用第二个 block 位、不改工厂结构。

## Architecture

```
源模板 X0-5/X0-6 结构           工厂 block 位映射（不改 block 数）
─────────────────────          ──────────────────────────────
抽样方法学区                    sampling（已有）
账面数据区                      balance（已有）
①…                             block1
②本期发生额（借方表/贷方表）    block2（一个 block，行带 direction，渲染层拆两张表）
③…                             block3
（源外增强区块）                block4（K05/K06/L05 的 block4 保留为 Source_Extra_Block）
检查比例                        （D0-5/F0-5 有；K0/L0 无 → 不加）

Occurrence_Block 借贷拆表（渲染层）：
  block2_rows 每行加 direction:'debit'|'credit'
  BlockCheckSheet 渲染两张 el-table（debit 组 / credit 组），各自合计
  getBlockTotal('block2') 保持全 block 合计不变；新增按 direction 分组小计（纯派生）
```

### 关键决策

**决策 1：Occurrence_Block 借贷拆表在渲染层做，数据仍单 block**

源模板 K0-5/K0-6/L0-5 的第 ③ 区块「本期发生额」是借方、贷方两张表。若占两个 block 位会改工厂固定结构 + 既有数据映射。方案：`block2_rows`（承载第 ③ 区块的 block 位，实施时按各套现有 block 映射确定具体位号）每行加可选 `direction: 'debit'|'credit'`；渲染组件按 direction 分组渲染两张 el-table，各自表头/行/合计；`getBlockTotal` 全 block 合计不变，新增 `getBlockTotalByDirection`（纯派生）供两张表小计。既有行无 direction → 归入「待归位」提示（Requirement 1.4，不猜方向）。

**决策 2：L0-5 Opening_Consistency_Check 作独立检查项，不占 block 位**

源模板 L0-5 第 3 项「检查期初余额是否与上期期末余额一致」是单项核对（非动态行区块）。作 payload 顶层字段 `opening_consistency`（`{ conclusion, note, current_opening, prior_closing, is_consistent }`），渲染为独立卡片。期初/上期期末可从平台取则提示带入，取不到手工录入并明示（Requirement 2.3）。

**决策 3：G06 纳入工厂 + 区块对齐源三区**

G06（1078 行）当前自造「持仓证明/股利/处置/公允价值」4 区块 + 源外的抽样总体/样本量等。改造：
- 区块映射源三区：block1=①初始投资协议检查表、block2=②本期发生额（借方表/贷方表，同决策 1）、block3=③期后出售/赎回检查表；block4 保留现有区块为 Source_Extra_Block
- 数据层纳入工厂 `createAlternativeConfirmationData(config)`（config 定 getSumFields/ratios/defaultBalance）
- 现有 4 区块数据能对应源区语义的迁移到对应 block（不丢），无对应的保留 block4 + 登记
- **除非实测证明 G06 有异质 IO 无法纳入工厂**（如 K06 曾因 http load/persist 异质旁挂）→ 异质面按 K06 proven 范式旁挂并注明依据（Requirement 3.5）

**决策 4：Source_Extra_Block 集中登记（数据文件），不删既有增强**

H05 四区块（源模板「二、检查过程记录」是空白区，属自造）、K05/K06 block4（往来对账/协议）、L05 block4（抵质押/担保）、G06 现有区块 —— 全部保留（不做破坏性删除，已录数据不丢），登记到 `alternativeSourceExtraManifest.ts`（每条含 套别/区块/依据），供守卫读取（Requirement 4.4）。H05 不新增区块/列/账面区/检查比例（Requirement 4.1/4.3）。

**决策 5：F05/F06 拆子组件 characterization 先行**

F05/F06（各 858 行单文件）拆子组件复用 D05 的 Dashboard/Master/CheckBlock + composables。红线：拆前先写 characterization 测试锁定可观察行为（区块渲染/合计/完成度/带入/persist payload 形状），拆后 payload 形状逐字不变（Requirement 5.1/5.3）。拆分中发现的行为与源模板不符 → 记为独立缺陷不夹带（Requirement 5.5）。

**决策 6：区块结构清单登记 + 契约守卫**

`alternativeBlockManifest.ts`：每套的区块集合 + 每区块列集合（对照源模板），契约守卫比对 `blockColumnConfigs*` 与该清单，漂移即失败（Requirement 7.1）。源外区块在此标 `sourceExtra: true` + 依据。

## Components and Interfaces

### 新增

**`alternativeBlockManifest.ts`（契约守卫基准）**
```ts
export interface BlockSpec {
  block: 'block1'|'block2'|'block3'|'block4'
  title: string
  columns: string[]           // 源模板该区块列
  splitByDirection?: boolean   // block2 借贷拆表标记
  sourceExtra?: boolean        // 源外增强区块
  sourceExtraReason?: string
}
export const ALTERNATIVE_BLOCK_MANIFEST: Record<AltCycleSheet, BlockSpec[]>
// AltCycleSheet: 'D05'|'D06'|'F05'|'F06'|'H05'|'K05'|'K06'|'L05'|'G06'
```

**`alternativeSourceExtraManifest.ts`（源外增强登记，可与上合并）**

### 工厂扩展（additive）

```ts
// createAlternativeConfirmationData 新增（不改既有签名/返回）：
getBlockTotalByDirection(company, blockType, direction): Record<string,number>  // 纯派生
// AltConfig 新增可选：
opening_consistency_enabled?: boolean   // L05 用
```

### 改造

| 套/组件 | 动作 |
|---|---|
| `alternativeD05Types.ts` (CheckRow) | additive 补 `direction?`（借贷拆表）；payload 顶层补 `opening_consistency?`（L05） |
| K05/K06/L05 适配器 + BlockCheckSheet | block2 借贷两表渲染（决策 1）；L05 加 Opening_Consistency_Check 卡片（决策 2） |
| G06 组件 + 新适配器 | 纳入工厂 + 区块对齐源三区（决策 3） |
| F05/F06 组件 | characterization 先行 → 拆子组件复用 D05（决策 5） |
| H05 | 不改结构，四区块登记源外（决策 4） |

## Data Models

### Occurrence_Block 借贷拆表（CheckRow additive）

```ts
interface CheckRow {
  // …既有字段不变
  direction?: 'debit' | 'credit'   // 仅 splitByDirection 区块用；旧行为 undefined
}
```

### L0-5 Opening_Consistency_Check（payload 顶层 additive）

```ts
interface AlternativePayload {
  // …既有不变
  opening_consistency?: {
    current_opening?: number
    prior_closing?: number
    is_consistent?: '一致' | '不一致' | '待核对'
    note?: string
  }
}
```

### 区块映射表（design 核心数据表，实施 M0 逐套核实填写）

| 套 | block1 | block2（借贷拆表） | block3 | block4 | 检查比例 |
|---|---|---|---|---|---|
| K05 | （现有映射，M0 核实）| 本期发生额 借/贷 | … | 往来对账/协议（源外）| 无（不加）|
| K06 | … | 本期发生额 借/贷 | … | 往来对账/协议（源外）| 无 |
| L05 | … | 本期发生额 借/贷 | … | 抵质押/担保（源外）| 无 |
| G06 | ①初始投资协议 | ②本期发生额 借/贷 | ③期后出售赎回 | 现有区块（源外）| 无 |
| H05 | 四区块全为源外（源留白）| — | — | — | 无 |
| D05/D06/F05/F06 | 现有（不改结构，F05/F06 仅拆子组件）| — | — | — | D0-5/F0-5 有（保留）|

## Correctness Properties

### Property 1: 借贷拆表行不互污染 + 各自合计正确
`block2_rows` 中 `direction='debit'` 与 `'credit'` 的行渲染到各自表；`getBlockTotalByDirection` 借方合计 SHALL 仅累加借方行，贷方同理；`getBlockTotal` 全 block 合计 = 借+贷。
**Validates: Requirements 1.1, 1.2, 7.2**

### Property 2: 既有行无 direction 不丢
既有 `block2_rows` 无 direction 的行 SHALL 完整回显并标「待归位」，SHALL NOT 被丢弃或自动猜方向。
**Validates: Requirements 1.3, 1.4**

### Property 3: 一张表的枢纽不强拆
源模板 Occurrence_Block 本就一张表的套（其区块 `splitByDirection` 未标）SHALL 保持一张表。
**Validates: Requirements 1.5**

### Property 4: L0-5 期初一致性持久化
`opening_consistency` SHALL 持久化并刷新后回显；判定不一致 SHALL 要求说明。
**Validates: Requirements 2.1, 2.2, 2.4**

### Property 5: G06 区块对齐源三区 + 数据不丢
G06 改造后区块集合 SHALL 含 ①初始投资协议 / ②本期发生额借贷 / ③期后出售赎回；现有区块数据 SHALL 迁移到对应 block 或保留 block4，SHALL NOT 丢弃。
**Validates: Requirements 3.1, 3.2, 3.3**

### Property 6: G06 源外能力不扩
G06 现有的抽样总体/样本量/账面区/检查比例 SHALL 保留但 SHALL NOT 新增扩展。
**Validates: Requirements 3.4**

### Property 7: H05 源留白不造
H05 SHALL NOT 新增区块/列/账面区/检查比例；现有四区块 SHALL 登记为源外增强。
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 8: 源外区块集中登记
每个 Source_Extra_Block SHALL 在 manifest 中有条目 + 依据；SHALL NOT 仅写代码注释。
**Validates: Requirements 4.4, 7.4**

### Property 9: F05/F06 拆分 payload 形状不变
F05/F06 拆子组件后 persist payload 形状与字段 SHALL 逐字不变；characterization 测试 SHALL 全绿。
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

### Property 10: 区块结构契约一致
每套 `blockColumnConfigs*` 的区块集合与列集合 SHALL 与 `ALTERNATIVE_BLOCK_MANIFEST` 一致，漂移即失败。
**Validates: Requirements 7.1**

### Property 11: round-trip 既有数据不丢
任一套旧 payload 读取→保存→读取，已录内容 SHALL 不丢。
**Validates: Requirements 1.3, 6.2, 7.3**

### Property 12: 逐套独立 + 工厂公共面不变
任一套改造 SHALL NOT 改变其余套行为；`createAlternativeConfirmationData` 导出名/构造签名/返回形状 SHALL 不变（除非契约测试同步更新并说明）。
**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

## Error Handling

| 场景 | 处理 |
|---|---|
| 既有 block2 行无 direction | 保留 + 标「待归位」，不猜方向 |
| L0-5 期初/上期期末取不到 | 允许手工录入 + 明示未取到 |
| G06 现有区块无源对应 | 保留 block4 + 登记源外，不删数据 |
| 拆分中发现行为与源模板不符 | 记独立缺陷，不在重构中夹带行为变更 |
| 工厂纳入 G06 遇异质 IO | 按 K06 proven 范式旁挂 + 注明依据，不强纳 |

## Testing Strategy

- **characterization（重构前锁定）**：F05/F06 现有可观察行为（区块渲染/合计/完成度/带入/payload 形状）
- **属性测试（fast-check）**：Property 1 借贷不互污染、Property 11 round-trip 不丢
- **契约测试**：Property 10 区块集合对 manifest、Property 8 源外登记、Property 12 工厂公共面不变
- **单元测试**：Property 2 待归位、Property 3 不强拆、Property 4 期初一致性、Property 5/6 G06、Property 7 H05
- **零回归门**：八套 alternative characterization + 函证域全量前端测试全绿；改动文件 `get_diagnostics` 清 + Vite transform 200
- **Playwright**：K0-5（借贷两表）、L0-5（期初一致性 + 借贷两表）、G0-6（源三区）各一次，验证旧数据回显不丢

## Migration / Phasing

| 阶段 | 内容 | 可回退 |
|---|---|---|
| **M0** | 逐套核实源模板区块/列清单 → 落 `ALTERNATIVE_BLOCK_MANIFEST` + 源外登记 + 各套 block 位映射（纯只读+数据文件）；F05/F06 characterization 测试先行 | 无风险 |
| **M1** | 工厂 additive：`getBlockTotalByDirection` + CheckRow `direction?` + payload `opening_consistency?`（不改既有） | 可回退 |
| **M2** | K05/K06/L05 借贷拆表（渲染层）+ L05 期初一致性 | 逐套可回退 |
| **M3** | G06 纳入工厂 + 区块对齐源三区 | 独立可回退 |
| **M4** | F05/F06 拆子组件（characterization 守护） | 逐套可回退 |
| **M5** | 契约/属性/守卫 + 零回归门 + Playwright | 仅测试 |

**M0 硬前置**：区块/列清单与 F05/F06 characterization 未就绪不得进 M1。
