# Design — A3-8 商誉减值测试专属组件

## Overview

新增 componentType `a3-8-goodwill-impairment`，覆盖 A3-8（商誉减值主表+减值损失分摊）与 A3-8-1（可收回金额双路径+WACC）两个 sheet 的结构化录入与公式自动计算，并与 I3 单体商誉底稿做 GtIndexChip 核对联动。

数据流（遵循单一来源 + 索引跳转铁律）：
```
模板解析(parse) ──┐
                  ├─→ render_a3_8 → {impairmentData, recoverableData, responses} → GtA38GoodwillImpairment.vue
field_overrides ──┘                                                                      │
                                                                          公式引擎(前端 composable 实时算)
                                                                          GtIndexChip → I3-2/I3-6/I3-7 (只跳转)
```

## Architecture

### 后端
- `backend/app/services/a3_8_goodwill_parser.py` — 解析 A3-8/A3-8-1 模板为结构化骨架（行/列定义 + 编制说明文本）。模板含大量 `#DIV/0!`（Excel 公式未填值），解析时清洗为 null/0。
- `backend/app/routers/wp_render_strategies/_a3_8_goodwill.py` — 渲染策略 `render(ctx)`，返回 `{impairmentData, recoverableData, responses}`；合并 `field_overrides`(scope=`a3_8_goodwill:{wp_id}`)。
- 注册：`__init__.py` 的 RENDERER_DISPATCH 加 `"a3-8-goodwill-impairment": render_a3_8_goodwill`；`wp_classification_service.py` 的 VALID_COMPONENT_TYPES 加该类型。

### 前端
- `GtA38GoodwillImpairment.vue` — 顶层编排（双模式切换 + 4 个 Tab：减值主表 / 减值损失分摊 / 可收回金额 / WACC 折现率）+ 编制说明折叠 + GtIndexChip 核对区。
- `composables/useA38Goodwill.ts` — 公式引擎（合计/差额/减值准备/分摊/折现/WACC）+ responses 状态 + debounce 保存。
- 注册 htmlRendererRegistry：componentType `a3-8-goodwill-impairment`，组件 GtA38GoodwillImpairment，icon 💠，label 'A3-8 商誉减值测试'，contextProps standard。

## Components and Interfaces

### 数据结构（TypeScript）
```ts
interface A38ImpairmentRow {
  id: string
  name: string            // 项目名称（资产组）
  carrying_a: number|null // 资产组账面价值 A
  goodwill_b1: number|null// 应分配商誉 B1
  minority_b2: number|null// 未确认少数股东权益商誉 B2
  recoverable: number|null// 可收回金额
  reason: string          // 减值原因
  remark: string
  // 计算字段（前端派生，不存）：total=A+B1+B2, diff=total-recoverable, impairment=max(diff,0)
}

interface A38AllocationRow {
  id: string
  asset_type: string      // 流动资产/固定资产/无形资产/商誉/...
  carrying: number|null
  minority: number|null
  recoverable: number|null
  // 派生：adjusted_nominal, impairment_loss, alloc_first(冲商誉), alloc_second(按比例)
}

interface A38RecoverableData {
  // (一) 公允价值减处置费用净额
  fair_value_rows: { id:string; name:string; fair_value:number|null; disposal_cost:number|null }[]
  // (二) DCF
  dcf: {
    cash_flows: (number|null)[]   // 第1~5年税前现金净流量
    base_cash_flow: number|null   // 基数
    perpetual_growth: number|null // 永续增长率
    discount_rate: number|null    // 折现率（税前）
  }
  // WACC 参数
  wacc: {
    tax_rate:number|null; debt_d:number|null; equity_e:number|null
    cost_debt_kd:number|null; rf:number|null; beta:number|null; rm:number|null
  }
}

interface A38Responses {
  impairment_rows: A38ImpairmentRow[]
  allocation_rows: A38AllocationRow[]
  recoverable: A38RecoverableData
  header: Record<string, any>
}
```

### 公式引擎（useA38Goodwill）
- `total(row) = (A??0)+(B1??0)+(B2??0)`
- `diff(row) = total - (recoverable??0)`
- `impairment(row) = max(diff, 0)`（diff≤0 显示 '-'）
- DCF：`discount_factor(n) = 1/(1+r)^n`；`pv(n)=cash_flow(n)*discount_factor(n)`；现值合计=Σpv
- 终值：`terminal = base*(1+g)/(r-g)`（r>g 时），其现值 = terminal*discount_factor(末年)
- WACC：`Ke = Rf+β*(Rm-Rf)`；`WACC = E/(D+E)*Ke + D/(D+E)*Kd*(1-tax)`；D+E=0→null
- 可收回金额 = max(公允价值净额合计, DCF现值合计)，标注采用路径
- 分摊：第一分配全冲商誉=min(减值损失, 商誉账面)，剩余按其他资产账面比例第二分配，且不得低于各自可收回金额（超限给提示）

### GtIndexChip 核对区
- 表头固定渲染 chip：`I3-2`/`I3-6`/`I3-7`，点击 emit `jump-to-workpaper`。
- 核对提示：A3-8 各资产组若已计提减值，提示"请核对 I3-6 单体层结论一致性"（纯文案，不取 I3 数据）。

## Error Handling
- 模板缺失 → 返回空骨架（空行 + 编制说明），前端显示空态可新增行。
- 除零（D+E=0 / r≤g / recoverable 缺失）→ 返回 null，UI 显示 '-'，不抛错。
- field-overrides 保存失败 → 重试 3 次后 ElMessage.warning，不阻断编辑。
- OnlyOffice 健康检查失败 → 降级提示。

## Testing Strategy
- **PBT (fast-check)**：公式引擎性质——total/diff/impairment 单调性、减值非负、分摊总和守恒（Σ分摊=减值损失）、WACC 边界（D+E=0→null）、DCF 折现系数随 n 递减。
- **hypothesis（后端）**：parser round-trip（解析→骨架结构稳定）、render 合并 overrides 不丢失。
- **vitest**：composable 计算单测 + 组件渲染（4 Tab、增删行、GtIndexChip emit、双模式切换、debounce 保存 mock）。
- **后端集成**：render-config 返回结构、VALID_COMPONENT_TYPES 注册、overrides 映射。
- **Playwright E2E**：打开 A3-8 → 录入资产组 → 减值准备自动算 → 可收回金额双路径 → WACC → GtIndexChip 跳转 → 保存回读。

## Design Decisions
- **公式放前端 composable**：实时交互体验，避免每次改数往返后端（参考 D1/D2/A5-1 模式）。
- **不做 EventBus 与 I3 自动同步**：遵循 A17 系列联动铁律，只跳转+提示，避免合并层/单体层双写冲突。
- **A3-8 与 A3-8-1 合并为一个组件 4 Tab**：二者强耦合（A3-8-1 的可收回金额结论回填 A3-8 主表），同组件内派生最自然。
- **不回写 trial_balance**：A3-8 是合并层测试底稿，减值入账由 I3/合并抵销处理，A3-8 仅测算不过账。
