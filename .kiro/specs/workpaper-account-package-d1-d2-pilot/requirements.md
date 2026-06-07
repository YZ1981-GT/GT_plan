# 需求文档：D1/D2 科目工作包试点

## 需求

### 需求 1：科目工作包注册表
1. THE system SHALL 定义 `account_package_registry`，描述科目工作包包含的 wp_code、sheet、程序、外部模块卡片和下游影响。
2. WHEN 用户进入销售循环，THE system SHALL 能展示 D1 应收票据和 D2 应收账款工作包入口。
3. WHEN 用户进入工作包，THE system SHALL 展示科目、报表行、附注章节、责任人、复核状态和数据状态。
4. THE system SHALL NOT 将 Excel 文件作为工作包的主导航层；Excel 文件只能作为来源或载体。
5. THE system SHALL 基于 D1/D2 inventory 构建工作包注册表，不得直接把 generated schema 当作生产配置来源。

### 需求 2：D1 技术闭环
1. THE system SHALL 将 D1 作为技术闭环试点，覆盖控制台、审定表、明细、披露、调整和结论。
2. WHEN D1 工作包打开，THE system SHALL 优先按 `sheet_type` 分组导航。
3. WHEN D1 程序状态被修改，THE system SHALL 持久化并刷新后保留。
4. WHEN D1 审定表关键字段展示，THE system SHALL 提供字段来源面板。
5. WHEN D1-C 结论存在未确认 AI 草稿，THE system SHALL 阻断 sign_off。

### 需求 3：D2 业务闭环
1. THE system SHALL 将 D2 作为业务闭环试点，聚合审定表、明细、账龄、坏账、函证摘要、期后回款、关联方、披露、调整和结论。
2. WHEN 函证状态变化，THE system SHALL 刷新 D2 函证摘要卡片的覆盖率、差异金额和未解决事项。
3. WHEN D2 调整保存，THE system SHALL 标记下游报表和附注 stale。
4. WHEN D2-C 结论生成，THE system SHALL 能引用字段来源、函证摘要、坏账/账龄结果和调整影响。

### 需求 4：函证模块边界
1. THE system SHALL 将 `ConfirmationHub` / `confirmation_service` 作为函证事实真源。
2. THE system SHALL 将 D0 定位为销售循环函证底稿汇总视图。
3. THE system SHALL 在 D1/D2 中展示函证摘要卡片，不复制维护函证明细。
4. WHEN `confirmation:received` 或相关函证事件发生，THE system SHALL 通过工作包摘要服务刷新 D1/D2 展示。

### 需求 5：验收和可复制性
1. THE system SHALL 输出 D1 技术闭环验收报告。
2. THE system SHALL 输出 D2 业务闭环验收报告。
3. THE system SHALL 记录可复制到 D4、F、H 的工作包配置模式。
4. THE system SHALL 提供 D1/D2 后端和前端回归测试。
5. THE system SHALL 修正前端静态入口中 D1/D2 错配文案，确保 D1 显示为应收票据，D2 显示为应收账款，营业收入归属 D4。

## 范围边界

- 不重写函证模块，只消费函证事实真源和事件。
- 不一次性重构所有 D 循环底稿。
- 不改变既有底稿编辑器路由，只增加工作包入口和聚合视图。
- 不在本 spec 中定义底层 `sheet_type`、`field_source` 类型，类型由 `workpaper-content-semantic-contract` 提供。
- 不直接启用 `backend/data/wp_render_schema/generated/*.yaml` 作为工作包生产 schema。

## 实施批次

- **P0 D1 技术闭环**：注册表、D1 导航、程序状态、字段来源、D1-C 结论入口。
- **P1 D2 业务闭环**：D2 多 sheet 聚合、函证摘要、坏账/账龄/调整/附注联动。
- **P2 可复制模式**：抽象到 D4/F/H 的工作包模板。

## Properties / 验收不变量

1. **Property 1：工作包主对象稳定**  
   用户从销售循环进入 D1/D2 时，看到的是科目工作包而不是 Excel 文件列表。
2. **Property 2：状态不丢失**  
   任一程序状态刷新页面后保持一致。
3. **Property 3：函证事实真源唯一**  
   D1/D2 不得复制维护函证明细状态，只展示函证模块摘要。
4. **Property 4：D2 摘要可追溯**  
   D2 函证覆盖率和差异金额必须能追溯到函证对象。
5. **Property 5：试点可复制**  
   D1/D2 的注册表结构必须能表达 D4/F/H 的多文件工作包。

## 依赖关系

- 依赖 `workpaper-content-semantic-contract`。
- 依赖现有 `useWorkpaperRefresh.confirmationReceived`、D2/D0 函证 callback 测试。
- 依赖 `platform-linkage-contract-stale` 处理调整、报表和附注 stale。
- 依赖 `workpaper-ai-conclusion-copilot` 完成 D1-C / D2-C AI 草稿治理。
- 可被后续 D4/F/H 工作包推广 spec 复用。

## UAT 场景

1. 助理从销售循环进入 D1 应收票据工作包，完成程序状态并刷新页面。
2. 经理点击 D1 审定表关键金额，查看来源和是否 stale。
3. 函证回函后，D2 应收账款工作包函证卡片自动刷新覆盖率和差异。
4. D2 保存调整后，附注披露表显示 stale 提示。
5. 合伙人查看 D2-C 科目结论，能看到结论引用的函证、坏账和调整依据。
