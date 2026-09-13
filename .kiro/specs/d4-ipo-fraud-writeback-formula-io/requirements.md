# Requirements Document

## Introduction
本 spec 覆盖 D4-29（营业收入客户信息）、D4-30（客户访谈汇总）、D4-31（客户访谈记录）和 D4-32（客户/供应商等资金流水）。保留原业务结构：D4-29 `D4-29-rows` 客户粒度；D4-30 `D4-30-customers` 的 `{customers,customDimensions}` 转置矩阵；D4-31 `D4-31-interview` 单对象问卷与 `q1_relation` 多选数组；D4-32 `D4-32-groups` 六段 `{key,rows}`。共同双模式治理链接 [`d4-dual-mode-formula-governance`](../d4-dual-mode-formula-governance/requirements.md)。

## Requirements
### Requirement 1: 源模板与客户/分组结构
1. WHEN 核定四表 THEN 源 xlsx 是列头、结构和业务粒度唯一真源，建立稳定 row/column ids；未知分类、科目、分组拒绝或人工映射，禁止猜测或默归其他；动态 id 保留，解析失败保留原数据。
2. WHEN D4-29 从其他底稿取客户 THEN 必须先核定真实客户粒度来源（D4-2 或 D4-3 的客户明细）；不得从 D4-2 的 `D2-detail-rows` 错误路径读取，也不得把产品汇总冒充客户数据。无真实来源必须中文提示并保持空态。
3. WHEN D4-30 导入导出 THEN 客户名称、所有维度值和已有 `customDimensions` 保留；不得把转置矩阵压平成丢失客户维度的固定列。
4. WHEN D4-31 导入导出 THEN 保留问卷原结构、四章节、多选/单选/条件展开；`q1_relation` 始终是 string array，不能改为字符串；问卷单对象仅允许一行。
5. WHEN D4-32 导入导出 THEN 六组归属必须由明确分组列/稳定 key 恢复，不能按行号或数量硬切；未知分组进入人工映射，不自动归“其他”。

### Requirement 2: 统一公式与双模式
1. WHEN preset/custom/F-SHELL 生效 THEN effective definition 必须可编辑 expression、refs、params，scope 含 `wp/sheet/row/field` 稳定标识，公式覆盖和值覆盖分离。
2. WHEN HTML、Excel 或后端计算 THEN 后端权威执行、前端预览和 Excel 投影使用同一定义；不能 Excel 优先，也不能只实现纯函数而不接真实执行链。
3. WHEN 双模式写回 THEN 必须经统一 mutation、sync bridge、版本三方合并、durable ack、批准 contract/representation；单模式只能是明确阻塞态。
4. WHEN D4-29 变动率、D4-32 异常率/资金回流判断计算 THEN 统一公式执行；0/0、prior=0、空/零/未知必须保持定义的三态，不得静默变成 0 或异常。

### Requirement 3: IPO 风险发现与 A13
1. WHEN 四表发现高风险、红旗或异常流水 THEN 先保存发现/风险记录，不自动造错报；描述型 amount=0 也不能自动进入 A13；reason 或“否”非空不能单独判异常。
2. WHEN D4-31 红旗发现 THEN 仍保留原问卷多选与 findings/q5_otherMatters 结构；发现可追加审计痕迹，但必须经过人工确认方向、金额和证据后才发布 A13。
3. WHEN 发布 A13 THEN 只能经白名单 `a13:push-misstatement`；emit 不等于落库成功，必须 durable ack 和幂等 source identity。
4. WHEN D4-1 说明追加 THEN 按 source identity 去重，独立于 A13 ack 可重试、失败可恢复且不回环；只读态不得写入。

### Requirement 4: 质量验证
1. WHEN 交付完成 THEN 必须有行为测试、四态变异检验和真实 HTML/Excel 双向实测，不能仅以静态字符串或纯函数测试验收。

### Requirement 5: D4-30/31/32 统一同步桥
1. WHEN D4-30、D4-31 或 D4-32 切换在线编辑 THEN 必须由 `WorkpaperSyncEditorHost` 消费受管 sheet provider descriptor，经过统一 mutation/version/三方合并/ack；不得继续由页面私自挂载 legacy `GtOnlyOfficeSheet`。
2. WHEN D4-32 导入未知组别 THEN 原始组别 label、稳定 row id、金额（含 0/空）、账号和中文必须保留并在 HTML 显示待映射；人工选择已知组后才移动并持久化。
3. WHEN D4-32 JSON 非法或桥接保存失败 THEN 旧数据不得被清空或覆盖，页面必须显示可见错误并保持可恢复状态。

### Requirement 6: 真栈接线边界
1. WHEN provider/contract 未注册或宿主未消费 descriptor THEN 不得宣称支持 OnlyOffice；能力应显示为阻塞态并记录原因。
2. WHEN D4-29 已有改动 THEN 本次不得修改 D4-29 生产或测试行为。
## Correctness Properties
### Property 1
**Validates: Requirements 1.1-1.5**
四表 export/import 往返后稳定 id、客户粒度、全部字段、问卷多选和分组归属不丢失；未知映射不被猜测。
### Property 2
**Validates: Requirements 2.1-2.4**
后端权威执行、前端预览和 Excel 投影共享 expression/refs/params/scope，边界三态与零除语义一致。
### Property 3
**Validates: Requirements 3.1-3.4**
发现不会自动写 A13；只有人工方向/金额/证据确认后的请求可持久化，ack/source identity 幂等，D4-1 可独立重试。
### Property 4
**Validates: Requirements 4.1**
变异能命中预期行为守卫，真实双模式测试验证三方合并、失败恢复和 durable ack。
