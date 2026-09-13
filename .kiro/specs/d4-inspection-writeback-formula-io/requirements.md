# Requirements Document

## Introduction
本 spec 覆盖 D4-13（ERP 核对）、D4-14（发生/穿行）、D4-15（完整性）和 D4-16（出口口岸核对）。现有组件与业务结构保留：D4-13 使用 `D4-13-process`/`D4-13-conclusion` 两个叙述 item；D4-14 使用嵌套 7 维 `D4-14-transactions`；D4-15 使用 `{delivery,invoice,voucher}` 嵌套行并持久化为 `D4-15-items`；D4-16 使用英文 key 的 `D4-16-rows`。共同双模式治理链接 [`d4-dual-mode-formula-governance`](../d4-dual-mode-formula-governance/requirements.md)，本文件只规定本四表的业务落点。

## Requirements
### Requirement 1: 源模板与导入导出
**User Story:** 作为审计助理，我需要 D4-13~16 的导入导出功能正确保留源模板结构和业务数据，以便底稿数据往返不丢失。

#### Acceptance Criteria
1. WHEN 处理 D4-13~16 的模板、列头或结构 THEN 源 xlsx 是唯一结构真源，必须逐 sheet 核定并以稳定 row id/column id 保存；未知列、未知分类或未知科目必须拒绝或进入人工映射，禁止猜测、默归"其他"或静默丢弃。
2. WHEN 导入或导出 D4-13 THEN "核对过程/核对结论"分别读写 `D4-13-process`/`D4-13-conclusion`，文本锚点逐字往返，缺失文本明确为 N/A。
3. WHEN 导入导出 D4-15 THEN 专用 parser/exporter 必须保持 `CompletenessItem` 的 delivery/invoice/voucher 三层字段；item_id 必须是 `D4-15-items`，动态 id 原样保留，不得重新生成既有 id；`isConsistent` 由统一公式重算。
4. WHEN 导入导出 D4-16 THEN 中文列头映射到 `bookAmount/portsAmount/portsPeriod/portsReason/taxReportAmount/taxReason/taxIndex`，`portsDiff`/`taxDiff` 必须重算，保持 `D4-16-rows`。
5. WHEN 往返测试通过 THEN 所有录入字段逐字段一致，派生字段不信任文件值；解析失败阻止写回并保留原数据。

### Requirement 2: 公式与双模式表达式
**User Story:** 作为审计师，我需要 D4-13~16 的公式在 HTML 和 Excel 双模式下保持一致定义和执行，以便审计结论不因渲染模式不同而矛盾。

#### Acceptance Criteria
1. WHEN 公式 preset、custom 或 F-SHELL 被读取/编辑 THEN effective definition 必须统一包含可编辑 expression、refs、params 及 `wp/sheet/row/field` 稳定 scope；公式覆盖和值覆盖分离，不能退化为只有纯函数、阈值或 remark JSON。
2. WHEN HTML 或 Excel 计算/预览/写回 THEN 后端权威执行器与前端预览必须使用同一 expression/refs/params 定义；Excel 只能作为同声明的投影，不能 Excel 优先覆盖 HTML。
3. WHEN 双模式提交 THEN 必须经平台统一 `ContentMutationService`、`useWorkpaperSyncBridge`、版本三方合并、durable ack 及批准的 contract/representation；单模式只能标记阻塞态，不能宣称完成。
4. WHEN D4-14 一致性、D4-15 一致性或 D4-16 差异计算 THEN 复用 `useD4FormulaEngine`/F-SHELL 同一定义，自动列可编辑 expression/refs/params 并显示来源。

### Requirement 3: 风险发现与 A13 业务联动
**User Story:** 作为审计助理，我需要检查表发现的风险经人工确认后才推入 A13，并且 A13 与 D4-1 说明各自可独立重试和恢复，以便审计结论可靠且可追溯。

#### Acceptance Criteria
1. WHEN 检查表发现差异、异常或不一致 THEN 只生成可追溯发现记录，不得直接把风险金额推入 A13；`reason` 或"否"非空本身不构成异常。
2. WHEN A13 写入请求生成 THEN 必须由人工确认方向、金额和证据后发布，金额 0 的定性事项也不得自动变成错报；未知金额必须停留在发现/风险通道。
3. WHEN 发布 A13 THEN 只能经白名单 `a13:push-misstatement`，事件 emit 不代表成功；必须有持久 ack、幂等 `source identity`，并记录 D4-1 说明的来源。
4. WHEN D4-1 说明追加 THEN 与 A13 成功状态独立、按 source identity 去重、可独立重试且不得回环触发源表写入；只读态不得写入。

### Requirement 4: 截止方向和三态边界
**User Story:** 作为审计师，我需要日期和截止方向的判断严格基于业务语义，不因缺失或零值产生错误风险结论。

#### Acceptance Criteria
1. WHEN 日期缺失、非法、零或未知 THEN 分别保留其语义并显示 N/A，不得凑出风险判断。
2. WHEN 截止方向计算 THEN 仅跨期条件互斥；非跨期可以同时为真，不能用"输出恒相反"替代业务判定。

### Requirement 5: 质量证据
**User Story:** 作为质量控制复核合伙人，我需要本 spec 交付物有充分的行为测试、变异检验和真实浏览器往返证据，以便验收时可信。

#### Acceptance Criteria
1. WHEN 完成交付 THEN 必须有后端/前端行为测试、变异检验四态结果（RED/GREEN/ANCHOR-MISS/WRONG-TEST）及浏览器真实 HTML/Excel 往返证据。
2. WHEN 验收双模式 THEN 必须验证真实平台三方合并、durable ack、失败恢复与后端/前端同定义执行，不能只测纯函数。

## Correctness Properties
### Property 1
**Validates: Requirements 1.2, 1.3, 1.4, 1.5**
导入导出往返后，稳定 row/column id 与全部录入字段逐字段一致，派生值由同一公式重算。
### Property 2
**Validates: Requirements 2.1, 2.2, 2.3, 2.4**
任一 preset/custom/F-SHELL 定义在后端执行、前端预览和 Excel 投影中 expression/refs/params 与 scope 相同。
### Property 3
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**
未人工确认方向、金额、证据的发现永不产生 A13 写入；成功写入必须产生可重放的 durable ack，D4-1 追加可独立重试且幂等。
### Property 4
**Validates: Requirements 4.1, 4.2**
空/零/未知/非法日期保持独立三态；跨期条件互斥，非跨期不被强制取反。
### Property 5
**Validates: Requirements 5.1, 5.2**
变异确实使对应行为守卫 RED，真实双模式测试覆盖 HTML/Excel/后端执行与失败恢复。

## Glossary
`item_id`、`D4-13-process`、`D4-13-conclusion`、`D4-14-transactions`、`D4-15-items`、`D4-16-rows`、`a13:push-misstatement`、`D4-1-adj-note`、`F-SHELL`、`durable ack`、`source identity` 均沿用平台定义。
