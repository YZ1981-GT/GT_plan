# 需求文档：平台数据联动契约、穿透与 stale 统一

## 需求

### 需求 1：LinkageContract 统一
1. THE system SHALL 定义统一 `LinkageContract`，覆盖四表、序时账、试算表、未审报表、调整分录、审定表、底稿、附注、审计报告、附件、AI 内容之间的引用关系。
2. WHEN 任一模块展示金额来源，THE system SHALL 使用 `LinkageContract` 描述来源、目标、金额、状态、跳转和审计日志。
3. WHEN 新增跨模块穿透，THE system SHALL 禁止手写 route 字符串，必须通过统一 linkage route resolver。

### 需求 2：统一穿透面板
1. WHEN 用户点击金额、公式、附注单元格或报表行，THE system SHALL 展示统一穿透面板。
2. THE panel SHALL 展示来源类型、来源年度、金额口径、是否人工覆盖、是否 stale、影响下游。
3. WHEN 目标为底稿编码 `wp_code`，THE system SHALL 解析到 `wp_id` 后跳转编辑器。

### 需求 3：stale 传播三层一致
1. WHEN 上游四表、试算表、调整分录、底稿或合并数据变化，THE system SHALL 触发 stale 事件。
2. THE system SHALL 同时更新后端状态、前端 badge、影响范围缓存。
3. WHEN stale 字段不存在或更新失败，THE system SHALL 记录错误并返回 degraded，不允许静默跳过。

### 需求 4：冲突调解与引用关系联动
1. WHEN 跨模块引用数据与人工覆盖数据冲突，THE system SHALL 生成冲突记录。
2. WHEN 用户在穿透面板发现冲突，THE system SHALL 提供跳转到冲突调解面板的入口。
3. WHEN 冲突被解决，THE system SHALL 更新相关 linkage 状态。

### 需求 5：签发一致性清单
1. WHEN 合伙人进入签发页，THE system SHALL 生成四表、未审报表、调整分录、审定表、附注、报告正文一致性清单。
2. WHEN 任一关键链路 stale 或 conflict，THE system SHALL 阻断签发或要求合伙人显式确认。
3. THE checklist SHALL 支持一键跳转到问题来源。

### 需求 6：联动契约测试
1. THE system SHALL 提供 LinkageContract schema 单元测试。
2. THE system SHALL 提供 stale 事件到前端 badge 的集成测试。
3. THE system SHALL 提供 wp_code 到 wp_id 路由解析测试。

## 范围边界
- 不重写所有现有穿透服务，先提供统一 facade。
- 不一次性覆盖所有历史数据，仅覆盖新产生或可实时计算的引用关系。
- 不改变现有冲突调解业务规则。

## 实施批次

- **P0 核心闭环**：LinkageContract schema、wp_code 路由解析、stale 不静默吞错、四表→底稿→附注最小链路。
- **P1 试点增强**：统一穿透面板、冲突调解联动、试算表/报表/附注高频入口接入。
- **P2 签发治理**：合伙人签发一致性清单、阻断规则、影响范围全量覆盖。

## Properties / 验收不变量

1. **Property 1：LinkageContract 字段完整性**  
   任一 contract 必须包含 source、target、status、route、basis、audit 信息。
2. **Property 2：路由解析可达性**  
   任一 `target_type=workpaper` 且含 `wp_code` 的 contract，必须能解析到可访问的 `wp_id` 或返回结构化 missing。
3. **Property 3：stale 非静默性**  
   任一 stale 更新失败必须产生 degraded 记录，不允许仅 `pass`。
4. **Property 4：冲突解决后状态单调性**  
   conflict resolved 后，相关 contract 不得继续显示 `status=conflict`。
5. **Property 5：签发阻断可解释性**  
   任一签发阻断项必须可跳转到来源，且包含责任对象和原因。

## 依赖关系

- 依赖 `platform-context-permission-foundation` 的项目/年度上下文。
- 依赖现有 `linkage_service.py`、`unified_lineage_service.py`、`wp_note_linkage_service.py`、`cross_module_conflicts.py`。
- 被 `platform-role-workbench-quality-loop` 合伙人签发雷达依赖。

## UAT 场景

1. 助理从试算表金额穿透到底稿审定表，再穿透到附注。
2. 经理修改调整分录后，报表/附注 stale badge 自动出现。
3. 用户在穿透面板发现人工覆盖冲突，跳转冲突调解并解决。
4. 合伙人签发时看到 stale 阻断项，并一键定位来源。
