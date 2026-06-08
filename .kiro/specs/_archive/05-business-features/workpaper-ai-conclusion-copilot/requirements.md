# 需求文档：底稿科目结论 AI 副驾驶

## 需求

### 需求 1：AI 结论草稿场景
1. THE system SHALL 在 D1-C / D2-C 科目结论场景接入 AI 草稿能力。
2. WHEN 用户请求生成结论草稿，THE system SHALL 基于结构化底稿上下文生成“目标-程序-发现-结论”草稿。
3. THE system SHALL NOT 让 AI 直接写入已确认结论；AI 输出必须先处于 pending 草稿状态。
4. WHEN 用户确认、修订或拒绝草稿，THE system SHALL 记录处理动作和处理人。

### 需求 2：复用 AI 内容治理
1. THE system SHALL 复用现有 `ai_content_log_service` 记录 AI 草稿。
2. THE system SHALL 复用现有 AI gate rule 阻断未确认草稿的 sign_off。
3. WHEN AI 草稿处于 pending，THE system SHALL 在工作包和签发入口显示阻断或提醒。
4. THE system SHALL NOT 新建平行的 AI 草稿治理表。
5. THE system SHALL 将 AI 草稿日志绑定到 `account_package_id`、`wp_id`、`sheet_type=conclusion` 和目标 `field_id`，便于 UI 和 gate 精确定位。

### 需求 3：结构化上下文
1. THE system SHALL 为 D1-C 结论提供审定表差异、程序状态、调整影响、字段来源和附注影响。
2. THE system SHALL 为 D2-C 结论提供审定表差异、函证摘要、坏账/账龄、期后回款、调整影响、字段来源和附注影响。
3. WHEN 上下文缺失，THE system SHALL 明确标记 missing，不得让 AI 假定不存在的数据。
4. THE system SHALL 在草稿中展示引用来源，支持用户跳转或查看来源面板。

### 需求 4：用户交互
1. WHEN AI 结论生成后，THE system SHALL 标记为 AI 草稿并显示来源摘要。
2. THE system SHALL 支持确认、修订后确认、拒绝三种动作。
3. WHEN 用户修订 AI 草稿，THE system SHALL 保留 AI 原文、用户修订文和确认人。
4. WHEN 用户拒绝草稿，THE system SHALL 要求填写拒绝原因或选择原因。
5. WHEN 用户保存 D1-C / D2-C 结论字段，THE system SHALL 在后端校验相关 AI log 已确认或已修订确认；pending 草稿不得直接进入正式结论。

### 需求 5：审计留痕与测试
1. THE system SHALL 记录 prompt、模型、上下文摘要、草稿内容、处理动作和处理人。
2. THE system SHALL 提供单元测试覆盖 pending 阻断、确认后放行、拒绝后不进入结论。
3. THE system SHALL 提供前端测试覆盖草稿标记、确认、修订、拒绝交互。

## 范围边界

- 不新建 AI 内容治理机制，必须复用 `ai_content_log_service` 和现有 gate rule。
- 不把 AI 扩展到所有底稿场景，P0 只覆盖 D1-C，P1 覆盖 D2-C。
- 不允许 AI 输出覆盖系统金额、程序状态或函证事实真源。
- 不在本 spec 中实现工作包聚合服务，结构化上下文由 D1/D2 工作包 spec 提供。
- 不在本 spec 中定义 D1/D2 sheet 结构；D1/D2 的 sheet inventory、生产 schema 真源和口径对账由 `workpaper-content-semantic-contract` 与 `workpaper-account-package-d1-d2-pilot` 提供。

## 实施批次

- **P0 D1-C AI 结论**：生成草稿、写入 log、pending 阻断、确认后进入结论。
- **P1 D2-C AI 结论**：接入函证摘要、坏账/账龄、期后回款和调整影响。
- **P2 复核回复辅助**：在复核问题回复中复用同一治理链路。

## Properties / 验收不变量

1. **Property 1：AI 不直接确认**  
   任一 AI 输出初始状态必须为 pending。
2. **Property 2：pending 阻断**  
   存在 pending AI 结论草稿时，sign_off 必须被既有 gate rule 阻断。
3. **Property 3：来源可见**  
   任一草稿必须显示引用的结构化来源摘要。
4. **Property 4：事实不编造**  
   上下文缺失项必须标记 missing，不得生成确定性结论。
5. **Property 5：治理不平行**  
   AI 草稿处理必须落在现有 AI 内容日志机制中。

## 依赖关系

- 依赖 `workpaper-content-semantic-contract` 的字段来源契约。
- 依赖 `workpaper-account-package-d1-d2-pilot` 的工作包上下文。
- 依赖现有 `ai_content_log_service.py`、`gate_rules_ai_content.py`。

## UAT 场景

1. 助理在 D1-C 生成 AI 结论草稿，页面显示 AI 草稿标签和来源摘要。
2. 未确认草稿时尝试签发，系统阻断并提示待确认 AI 内容。
3. 经理修订并确认 D1-C 草稿，结论进入底稿，sign_off 不再被该草稿阻断。
4. D2-C 草稿引用函证覆盖率、坏账分析和调整影响，缺失数据以 missing 展示。
