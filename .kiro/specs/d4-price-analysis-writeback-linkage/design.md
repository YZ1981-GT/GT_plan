# Design — D4 价格分析双向回写联动 + 行同步回写死代码修复

## 设计原则（源自 D2 范式实证）

调查确认（context-gatherer + 直读）：**D2 循环的联动 = 共享 reactive store（`allResponses` Map）+ 纯 computed 派生链 + provide/inject 分发**，而非命令式"行同步 CustomEvent"。`d4:sync-row` 是无接收端的死代码。因此本设计的第一原则：**联动一律用 computed 派生自 `allResponses` 的上游 key，不用命令式行同步事件**；跨底稿"审定/异常/结论"通知才用 eventBus（经 `crossWpEventBridge` 已桥接的事件族）。

## 现状事实（改动前锚点）

| 事实 | 位置 | 状态 |
|------|------|------|
| `d4:sync-row` 两个发送函数无接收端 | `useD4CrossSheet.ts:271-288` | 死代码，待删 |
| `useD4CrossSheet` 创建后未 provide、无消费 | `GtD4OperatingRevenue.vue:264` | 未接线 |
| D4-1 审定表行只来自 `dynamicRows`，产品行不自动派生 | `useD4Adjudication.ts` sections computed | 缺行派生 |
| `useD4Adjudication` 已有活的 `mainRevenueByProduct`/`otherRevenueByItem` computed | `useD4Adjudication.ts` | 可复用 |
| `publishAdjudicated` 发 `substantive:adjudicated`+`d4:writeback-trial-balance` | `useD4Adjudication.ts` | 活（宿主监听 writeback；bridge 转发 adjudicated） |
| D4-10「本期销售总额」纯手工 | `D4TabCustomerPrice.vue` | 待接公式/联动 |
| D4-10 挂 `wp:D4-9`+`wp:D4-11` chip | `D4TabCustomerPrice.vue` | 正确 |
| D4-11 挂 `wp:D4-10` chip（应为指向上游 D4-2） | `D4TabProductPrice.vue` | bug，待修 |
| `substantive:adjudicated`/`disclosure:note-text-updated`/`adjustment:created`/`a13:push-misstatement` 已在 eventBus + bridge 桥接 | `eventBus.ts` / `crossWpEventBridge.ts` | 基础设施就位 |
| `customerStructureData`/`productRevenueForMargin` computed 现成 | `useD4CrossSheet.ts` | 可作上游取数源 |

## 架构总览

```
┌──────────────── allResponses (Ref<Map>) — 共享 reactive store ────────────────┐
│  D4-2-rows(JSON)   D4-3-rows(JSON)   D4-10-data(JSON)   D4-11-data(JSON)  ...  │
└───────┬──────────────┬───────────────────┬──────────────────┬────────────────┘
        │              │                   │                  │
  computed 派生    computed 派生       computed 上游取数    computed 上游取数
        │              │                   │                  │
        ▼              ▼                   ▼                  ▼
   D4-1 审定表     D4-1 审定表         D4-10 客户价格       D4-11 产品价格
  主营行派生       其他行派生       (客户←D4-9/D4-2)     (产品←D4-2)
  (Req1.1)        (Req1.2)          (Req2)               (Req3)
        │                                  │                  │
        │                              异常回标 ──eventBus──► D4-9/D4-2 行标记 (Req4)
        │                              结论/异常 ─eventBus──► D4附注/审计说明 (Req5)
        ▼
  publishAdjudicated ──eventBus('substantive:adjudicated')──► 附注/TB回写
```

## 组件与文件改动

### C1. `useD4Adjudication.ts` — D4-1 行结构 computed 派生（Req 1）

**核心改动**：`sections` computed 目前只遍历 `dynamicRows`。新增：把 `mainRevenueByProduct`（已存在）的每个产品、`otherRevenueByItem` 的每个项目，作为 `isFromCrossSheet=true` 的派生行注入 `sections`，与 `dynamicRows` 的手工行合并（同名去重）。

设计：
- 新增内部 computed `crossSheetMainRows` / `crossSheetOtherRows`：从 `mainRevenueByProduct`/`otherRevenueByItem` 生成 `AdjudicationRow[]`，`isFromCrossSheet=true`、`currentUnadjusted=产品聚合值`（只读）、`isEditable=false`（金额列），`rowKey=` 稳定 key（如 `xsheet-main-{normalizedProduct}`，不用 label 防撞键）。
- `sections` 合并顺序：先派生行（cross-sheet），后手工行（`dynamicRows` 中 `source!=='tb'`）；按 normalizedLabel 去重（派生优先）。
- 手工行的 AJE/RJE 仍读 per-field 键，不受影响（Req 1.4）。
- 删 `useD4CrossSheet.ts` 的 `syncProductRowToAdjudication`/`syncOtherItemRowToAdjudication` 及其 return 导出（Req 1.5）。

### C2. `GtD4OperatingRevenue.vue` — provide 联动数据（Req 6.1）

`provide('d4CrossSheet', crossSheet)`，使 D4-8/9/10/11 子表可 `inject` 消费 `customerStructureData`/`productRevenueForMargin`。子表也可自持 `useD4CrossSheet({allResponses})`（D2TabAdjudication 范式），二选一，优先 provide 复用同一实例。

### C3. `D4TabCustomerPrice.vue`（D4-10）— 上游取数 + 回写（Req 2 / 4 / 5）

- **导入**：「导入导出 ▾」下拉加「从 D4-9 导入客户」。点击 → 读 inject 的 `crossSheet.customerStructureData` → 按客户名 merge 进 `rows`（不覆盖手工改过行）；`totalAmount` 自动 = `crossSheet.mainRevenueTotal.current`（可手工覆盖）。
- **本期销售总额公式**：接公式管理，登记 `D4-10-total-amount` 的 Tier A 预设 `WP('D4-2','合计')`（详见 C6），render seed 进 allResponses；组件读 seed 值作默认，手工优先。
- **异常回标**（Req 4.1）：`computedRows` 中 `Math.abs(avgDiff)>0.2 || Math.abs(marketDiff)>0.2` 的客户 → watch → `eventBus.emit('substantive:adjudicated'|新增专用事件, {wpCode:'D4-10', abnormalCustomers:[...]})`，由 C5 接收端写回 D4-9。
- **结论供附注**（Req 5.1）：审计说明/结论保存 → `eventBus.emit('disclosure:note-text-updated', {wpCode:'D4-10',...})`。

### C4. `D4TabProductPrice.vue`（D4-11）— 上游取数 + 回写 + 修 chip（Req 3 / 4 / 5）

- **导入**：「导入导出 ▾」加「从 D4-2 导入产品」→ 读 `crossSheet.productRevenueForMargin` → 按品种 merge。
- **修 chip**：`GtIndexChip value="wp:D4-10"` → 改为指向真实上游 `wp:D4-2`（并保留一个指回 D4-10 的对称引用视需要）。
- **异常回标**（Req 4.2）：`Math.abs(policyDiff)>0.1 || Math.abs(marketDiff)>0.1` → eventBus → 写回 D4-2 行标记。
- **结论供附注**（Req 5）：同 C3。

### C5. 异常回标接收端（Req 4.3 / 6.2）— 新建 composable/接线

新增轻量接收：在宿主或一个 `useD4PriceWriteback` composable 中 `eventBus.on('d4:price-abnormal', handler)`，handler 读 `D4-2-rows`/`D4-9`（客户结构派生自 D4-2，回标落在 `D4-2-rows` 行的 `remark`/新字段 `priceAbnormal`），set 回 allResponses 并 debounceSave。**必须真接线**（守卫锁死发送↔接收）。

事件设计（新增，注册进 `eventBus.ts` + `crossWpEventBridge.BRIDGED_EVENTS`）：
- `d4:price-abnormal` — `{ wpCode:'D4-10'|'D4-11', targetKey:'customer'|'product', items: {name:string, diffPct:number}[] }`。幂等：接收端按 name 覆盖标记集合（不追加），空数组=清除（Req 4.5）。

### C6. 后端上游取数 resolver（Req 2 / 3 / 6.3）

价格分析的"单价/数量"多行明细不在前端 computed 覆盖范围（`D4-2-rows` 只有金额/月度，无数量/单价）。两条路：
- **主路（复用前端 computed）**：D4-10 客户/金额、D4-11 产品/金额直接从 `customerStructureData`/`productRevenueForMargin` 前端联动取（金额维度已够，单价/数量仍手工或后续 resolver）。**本 spec 主交付走此路**（宁缺勿造，不为不存在的数量维度造 resolver）。
- **可选增强（deferred）**：若 `tb_ledger` 有数量维度，新增 `@auto_resolver("d4_price_by_product")`。**本 spec 登记为 deferred，不实现**（除非核实数量维度真存在）。
- **公式管理接入**：D4-10 `D4-10-total-amount` 走 Tier A 预设 `WP('D4-2','合计')`，登记进 D 循环预设 JSON（若 D4-2 支持 WP 列名"合计"）；若 `WP('D4-2',...)` 列名不支持，退化为前端 computed 直接读 `mainRevenueTotal`（Req 2.3 允许等价联动）。

> 决策 DEC-A：优先前端 computed 联动（零后端改动、复用现成聚合）；公式管理接入仅用于"本期销售总额"这个单标量，且以 D4-2 列名实际支持为前提，否则等价前端联动。

## 数据契约

### D4-10-data（现状保持 + merge 语义）
```json
{ "rows": [{ "customer","product","amount","quantity","unitPrice","avgPrice","avgReason","marketPrice","marketReason" }],
  "totalAmount": number, "totalQuantity": number }
```
merge：按 `customer`（+`product`）去重；导入只填 `customer`/`amount`，不覆盖已有手工 `unitPrice`/`avgPrice` 等。

### D4-2-rows 异常标记回写（Req 4）
在行对象增可选字段 `priceAbnormal?: boolean` / `priceAbnormalPct?: number`（不破坏既有 `product`/`months` 结构，向后兼容 safeParse）。

## Error Handling

- 上游无数据 → `ElMessage.warning` 可辨别中文（Req 2.4/3.3），不填 0。
- 异常回标目标行缺失 → 静默跳过（Req 4.4）。
- eventBus 无消费者 → 不报错（Req 5.4），但守卫锁死接线关系。

## 守卫策略（Req 7）

| 守卫 | 类型 | 断言 |
|------|------|------|
| `d4AdjudicationRowLinkage.spec.ts` | vitest 行为 | 给 allResponses 塞 D4-2-rows 两产品 → `sections` 主营区块含 2 个 `isFromCrossSheet` 派生行；删一产品 → 1 行 |
| `d4PriceUpstreamImport.spec.ts` | vitest 行为 | D4-10 导入按钮点击 → merge customerStructureData；D4-11 → productRevenueForMargin；空上游给提示 |
| `d4PriceWritebackLinkage.spec.ts` | vitest 接线 | emit `d4:price-abnormal` → 接收端真消费、写回 D4-2-rows 的 priceAbnormal；幂等；空数组清除 |
| `d4NoDeadEvent.spec.ts` | vitest 静态 | 断言 `useD4CrossSheet.ts` 不再含 `d4:sync-row`；凡 D4 dispatch 的 CustomEvent 名都能在代码库找到 addEventListener 或 eventBus.on |
| 变异脚本 `mutate_d4_linkage_guards.py` | 变异 | 锚点≥3：删接收端 handler / 改错端点循环前缀 / 行派生 computed 依赖改成空 → 全 RED |

## Property（机器可校验）

### Property 1
*For any* D4-2 明细产品集合 P（0~N 个不同产品），D4-1 审定表主营区块的 `isFromCrossSheet` 派生行集合 SHALL 恰好等于 P（同名去重后），行数 == |distinct(P)|。
**Validates: Requirements 1.1**

### Property 2
*For any* D4-10 导入操作，导入后 `rows` 中客户名集合 SHALL 包含上游 customerStructureData 的全部客户名（merge 并集），且已有手工行的非金额字段值不变。
**Validates: Requirements 2.2**

### Property 3
*For any* 价格异常客户/产品集合 A，emit `d4:price-abnormal` payload={items:A} 后接收端写回上游行的异常标记集合 SHALL 恰好等于 A（幂等：重复 emit 同一 A 结果不变；emit 空集清除全部标记）。
**Validates: Requirements 4.5**

## 迁移与兼容

- 无 DB 迁移（纯前端联动 + 复用现有事件族 + 可选前端字段）。
- `d4:price-abnormal` 为新事件，注册进 eventBus 类型 + BRIDGED_EVENTS。
- D4-2-rows 新增可选字段向后兼容（safeParse 容忍缺字段）。


## C0-C4 治理对齐
C0核定D4-10/11逻辑编码与物理sheet/变体身份；公式key使用`wp_id`，`preset_version`仅为定义版本。C1验证共享sync、不同字段自动合并、同字段冲突和durable ack/applied分离；C2验证custom/preset升级与删除恢复、缺失/损坏/stale/blocked及schema白名单禁eval/外链；C3验证D4-2/D4-9上游派生和异常回标接收端，表内表间公式可二次编辑且不等于TB/A13发布；C4只门控价格分析相关contract、联动、权限、Playwright和变异产物。