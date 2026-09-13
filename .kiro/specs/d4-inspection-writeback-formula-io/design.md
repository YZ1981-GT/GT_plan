# Design Document

## Overview
本 spec 覆盖 D4-13（ERP 核对）、D4-14（发生/穿行）、D4-15（完整性）和 D4-16（出口口岸核对）四表的导入导出、公式预设、风险发现链与质量验收。保留现有组件与业务结构，源 xlsx 逐 sheet 核定列头、稳定 row/column id 后，后端专用 parser/exporter 与前端适配共同遵守该结构。

## Scope and preserved business structure
保留 D4-13 ERP 两段叙述、D4-14 `D4-14-transactions` 7 维、D4-15 delivery/invoice/voucher 三层与 `D4-15-items`、D4-16 英文 key `D4-16-rows` 及现有风险事实。源 xlsx 逐 sheet 核定列头、稳定 row/column id 后，后端专用 parser/exporter 与前端适配共同遵守该结构。

## Architecture
导入导出继续使用 `_d4_import_export.py` 与 `useD4ImportExport`；公式统一走 F-SHELL effective definition，`useD4FormulaEngine` 仅作为同一定义的执行适配；后端权威执行，前端仅预览，Excel 是同声明投影。双模式提交统一经过 `ContentMutationService`、`useWorkpaperSyncBridge`、版本三方合并和 durable ack。风险发现经人工方向/金额/证据确认后，才调用 `useD4InspectionWriteback` 发布 A13；A13 与 D4-1 说明写入分别 ack、幂等和重试，不回环。

## Components and Interfaces
1. **源核定 gate**：读取权威 xlsx，建立稳定 row/column ids、字段映射和未知值人工映射清单。
2. **IO**：D4-13 双 item 文本锚点；D4-15 专用嵌套 parser/exporter 与 `D4-15-items`；D4-16 专用英文 key parser/exporter 与差异重算；动态 id 保留，解析失败保留原数据。
3. **Formula**：F-SHELL preset/custom expression/refs/params/schema；后端执行与前端预览共享定义，统一自动列和来源 tooltip。
4. **Linkage**：发现记录、人工认定、A13 durable ack、D4-1 独立 durable ack；`eventBus.emit` 只表示请求，不表示成功。
5. **Acceptance**：pytest/vitest、变异四态、真实浏览器 HTML/Excel 双向往返与失败恢复。

## Data Models
- **D4-13**：`D4-13-process`（叙述文本）、`D4-13-conclusion`（叙述文本），item_id = `D4-13-{process,conclusion}`。
- **D4-14**：`D4-14-transactions`（7 维嵌套行），item_id = `D4-14-transactions`。
- **D4-15**：`D4-15-items`（`CompletenessItem` delivery/invoice/voucher 三层），动态 row id 原样保留。
- **D4-16**：`D4-16-rows`（英文 key `bookAmount/portsAmount/portsPeriod/portsReason/taxReportAmount/taxReason/taxIndex`），`portsDiff`/`taxDiff` 派生重算。

## Boundaries
不能以 A13 代替 HTML/Excel 同步，不能 Excel 优先；不能自动将整笔凭证、客户收入或 `amount:0` 定性发现变成错报；不能把 reason/"否"非空当异常；未知分类/科目不得归其他；截止非跨期不恒取反。

## Decisions
- 保留全部业务 item_id 与现有业务结构，不重命名、不重分配既有 id。
- 共同治理由 `d4-dual-mode-formula-governance` 提供，本文只定义四表接入点。
- A13 与 D4-1 说明是两个可独立恢复的持久写入目标。

## Correctness Properties
### Property 1: IO 往返一致性
**Validates: Requirements 1.2, 1.3, 1.4, 1.5**
导入导出往返后，稳定 row/column id 与全部录入字段逐字段一致，派生值由同一公式重算。

### Property 2: 公式同定义
**Validates: Requirements 2.1, 2.2, 2.3, 2.4**
任一 preset/custom/F-SHELL 定义在后端执行、前端预览和 Excel 投影中 expression/refs/params 与 scope 相同。

### Property 3: 发现→A13 人工门
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**
未人工确认方向、金额、证据的发现永不产生 A13 写入；成功写入必须产生可重放的 durable ack，D4-1 追加可独立重试且幂等。

### Property 4: 三态边界
**Validates: Requirements 4.1, 4.2**
空/零/未知/非法日期保持独立三态；跨期条件互斥，非跨期不被强制取反。

### Property 5: 变异与真实双模式
**Validates: Requirements 5.1, 5.2**
变异确实使对应行为守卫 RED，真实双模式测试覆盖 HTML/Excel/后端执行与失败恢复。

## Error Handling
- 解析失败：阻止写回并保留原数据，不静默丢弃。
- 未知列/分类/科目：拒绝或进入人工映射，禁止猜测。
- A13 emit 失败：durable ack 未确认则不视为成功，可独立重试。
- 公式求值失败：verdict 层裁决为 `applied=False`，绝不转零。

## Testing Strategy
- 后端 pytest：D4-13 item_id 映射 + D4-15 嵌套往返 + D4-16 英文 key 往返 + 派生列重算 + 反向自检。
- 前端 vitest：D4-14 穿行不一致提取 + D4-16 差异提取 + canConfirm 三门 + 幂等 + 变异反向自检。
- 变异检验：四态（RED/GREEN/ANCHOR-MISS/WRONG-TEST）。
- Playwright 真实双模式：HTML/Excel 双向往返（需全栈环境 backend 9980 + frontend 3030 + OnlyOffice）。
