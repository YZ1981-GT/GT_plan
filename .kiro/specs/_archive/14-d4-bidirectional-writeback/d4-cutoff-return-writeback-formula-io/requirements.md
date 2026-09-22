# Requirements Document

## Introduction
本 spec 覆盖 D4-17（截止测试·账到单据）、D4-18（截止测试·单据到账）、D4-19（折扣折让）和 D4-20（销售退货）。保留业务结构：D4-17/18 为英文 key 截止行并分别使用 `D4-17-rows`/`D4-18-rows`；D4-19 为 `D4-19-rows` 的 16 字段；D4-20 保留 `D4-20-policy`、`D4-20-summary`、`D4-20-assessment`、`D4-20-provision`、`D4-20-current-returns`、`D4-20-post-returns`、`D4-20-note`、`D4-20-conclusion` 六区结构。共同双模式治理链接 [`d4-dual-mode-formula-governance`](../d4-dual-mode-formula-governance/requirements.md)。

## Requirements
### Requirement 1: 源模板与 IO
1. WHEN 核定 D4-17~20 THEN 源 xlsx 是唯一列头/结构真源，建立稳定 row/column ids；未知分类、科目或分组拒绝或人工映射，禁止默归“其他”；动态 id 保留，解析失败保留原数据。
2. WHEN 导入导出 D4-17/18 THEN 专用 parser/exporter 映射英文 key，`isCutoff` 忽略文件值并由公式重算；截止方向分别保持账到单据与单据到账语义，item_id 不变。
3. WHEN 导入导出 D4-19 THEN 专用 parser/exporter 保留 16 字段，`discountRate` 重算，item_id 为 `D4-19-rows`。
4. WHEN 导入导出 D4-20 THEN current/post 映射到 `D4-20-current-returns`/`D4-20-post-returns`，provision 专用重算 `shouldProvide`/`diff`；主 `D4-20` 无对应存储，必须删除死配置或显式中文错误，禁止 generic 静默写孤儿键。
5. WHEN 往返完成 THEN 录入字段逐字段一致，派生值不信任文件值。

### Requirement 2: 统一公式与双模式
1. WHEN preset/custom/F-SHELL 定义生效 THEN expression、refs、params 和 `wp/sheet/row/field` scope 可编辑且公式/值覆盖分离。
2. WHEN HTML/Excel 计算或写回 THEN 后端权威执行与前端预览同定义，Excel 只是投影，不能优先覆盖 HTML；统一经过 mutation、sync、版本三方合并、durable ack、contract/representation。
3. WHEN 截止方向计算 THEN 只对跨期条件互斥；非跨期允许同为真，缺失/非法日期返回 N/A，不得输出恒相反。

### Requirement 3: 发现与 A13
1. WHEN 发现跨期、折扣、退货或计提差异 THEN 仅保存发现，不自动造错报；reason 或“否”非空不能单独判异常。
2. WHEN A13 请求发布 THEN 人工确认方向、金额和证据；不得自动推整笔凭证、客户收入或 amount=0 定性事项。
3. WHEN emit A13 THEN 事件不代表成功，必须 durable ack、幂等 source identity；D4-1 说明追加去重、独立重试、防回环。

### Requirement 4: 质量验证
1. WHEN 完成交付 THEN 必须有行为测试、四态变异检验和真实 HTML/Excel 双向浏览器证据，不能只测纯函数。

## Correctness Properties
### Property 1
**Validates: Requirements 1.2-1.5**
四类记录 export/import 后录入字段、稳定 id 和分组归属不丢失，派生字段由统一定义重算。
### Property 2
**Validates: Requirements 2.1-2.3**
同一公式 definition 在后端、前端和 Excel 投影中 expression/refs/params/scope 一致，截止非跨期不被强制取反。
### Property 3
**Validates: Requirements 3.1-3.3**
未经人工方向/金额/证据确认的发现不产生 A13 写入；ack、source identity 和 D4-1 独立重试幂等。
### Property 4
**Validates: Requirements 4.1**
变异检验命中预期守卫，真实双模式测试验证合并、失败恢复与 durable ack。
