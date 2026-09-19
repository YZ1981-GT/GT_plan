# Design Document

## Scope and preserved business structure
保留 D4-13 ERP 两段叙述、D4-14 `D4-14-transactions` 7 维、D4-15 delivery/invoice/voucher 三层与 `D4-15-items`、D4-16 英文 key `D4-16-rows` 及现有风险事实。源 xlsx 逐 sheet 核定列头、稳定 row/column id 后，后端专用 parser/exporter 与前端适配共同遵守该结构。

## Architecture
导入导出继续使用 `_d4_import_export.py` 与 `useD4ImportExport`；公式统一走 F-SHELL effective definition，`useD4FormulaEngine` 仅作为同一定义的执行适配；后端权威执行，前端仅预览，Excel 是同声明投影。双模式提交统一经过 `ContentMutationService`、`useWorkpaperSyncBridge`、版本三方合并和 durable ack。风险发现经人工方向/金额/证据确认后，才调用 `useD4InspectionWriteback` 发布 A13；A13 与 D4-1 说明写入分别 ack、幂等和重试，不回环。

## Components
1. 源核定 gate：读取权威 xlsx，建立稳定 row/column ids、字段映射和未知值人工映射清单。
2. IO：D4-13 双 item 文本锚点；D4-15 专用嵌套 parser/exporter 与 `D4-15-items`；D4-16 专用英文 key parser/exporter 与差异重算；动态 id 保留，解析失败保留原数据。
3. Formula：F-SHELL preset/custom expression/refs/params/schema；后端执行与前端预览共享定义，统一自动列和来源 tooltip。
4. Linkage：发现记录、人工认定、A13 durable ack、D4-1 独立 durable ack；`eventBus.emit` 只表示请求，不表示成功。
5. Acceptance：pytest/vitest、变异四态、真实浏览器 HTML/Excel 双向往返与失败恢复。

## Boundaries
不能以 A13 代替 HTML/Excel 同步，不能 Excel 优先；不能自动将整笔凭证、客户收入或 `amount:0` 定性发现变成错报；不能把 reason/“否”非空当异常；未知分类/科目不得归其他；截止非跨期不恒取反。

## Decisions
- 保留全部业务 item_id 与现有业务结构，不重命名、不重分配既有 id。
- 共同治理由 `d4-dual-mode-formula-governance` 提供，本文只定义四表接入点。
- A13 与 D4-1 说明是两个可独立恢复的持久写入目标。
