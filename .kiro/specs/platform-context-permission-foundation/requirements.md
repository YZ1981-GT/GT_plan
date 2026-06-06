# 需求文档：平台上下文、年度与权限基础统一

## 需求

### 需求 1：项目上下文单一真源
1. WHEN 用户进入任何项目内页面，THE system SHALL 显示统一项目上下文条，包含项目、年度、适用准则、审计范围、项目状态。
2. WHEN 用户切换项目，THE system SHALL 清空当前项目相关缓存、SSE 订阅、编辑锁上下文和页面临时状态。
3. WHEN 页面需要 project_id，THE system SHALL 从统一 `ProjectContext` 获取，不允许组件自行解析多个来源。

### 需求 2：年度上下文统一
1. WHEN 用户切换年度，THE system SHALL 刷新试算表、底稿、报表、附注、合并数据和缓存。
2. WHEN 页面展示上年数、期初数、上年附注或跨年度对比，THE system SHALL 明确标注来源年度。
3. THE system SHALL 禁止业务页面硬编码默认年度。

### 需求 3：权限矩阵统一
1. THE system SHALL 建立系统角色与项目职责两层权限矩阵。
2. WHEN 前端展示按钮、菜单、批量操作，THE system SHALL 使用同一权限矩阵判断可见性和可用性。
3. WHEN 后端执行写操作、审批、解锁、签发、归档，THE system SHALL 使用同一权限矩阵执行授权。
4. WHEN 前端允许点击但后端拒绝，THE system SHALL 返回结构化权限错误并提示缺失权限。

### 需求 4：项目设置中心
1. THE system SHALL 提供项目设置中心，集中管理年度、准则、模板、成员、职责、权限、锁定策略。
2. WHEN 项目进入 signed 或 archived 状态，THE system SHALL 默认置为只读。
3. WHEN 需要临时授权或紧急解锁，THE system SHALL 记录审批人、原因、到期时间和审计日志。

### 需求 5：枚举字典扩展
1. THE system SHALL 将高频展示枚举纳入系统字典，包括审计循环、底稿状态、复核状态、工时状态、AI 内容确认状态、风险等级。
2. WHEN 管理员修改枚举展示，THEN SHALL 仅允许修改 label/color，不允许修改 value。
3. WHEN 字典加载失败，THEN SHALL 使用前端 fallback 并显示降级提示。

### 需求 6：上下文与权限契约测试
1. THE system SHALL 提供项目/年度切换的前端单元测试和集成测试。
2. THE system SHALL 提供前后端权限矩阵一致性契约测试。
3. THE system SHALL 提供枚举字典 value 不可变的测试。

## 范围边界
- 不重做登录认证体系。
- 不改变现有角色名称，先做映射与收口。
- 不一次性迁移所有页面，先覆盖项目内高频页面。

## 实施批次

- **P0 核心闭环**：ProjectContext、年度切换、权限矩阵后端 facade、项目内高频页面接入。
- **P1 试点增强**：项目设置中心、前端权限矩阵全面替换、枚举字典覆盖高频业务枚举。
- **P2 规模化治理**：临时授权审批流、归档/签发只读策略全覆盖、权限矩阵可视化管理。

## Properties / 验收不变量

1. **Property 1：项目切换隔离性**  
   WHEN 用户从项目 A 切换到项目 B，THEN 页面不得保留项目 A 的底稿、报表、附注、编辑锁、SSE 事件或临时筛选状态。
2. **Property 2：年度切换一致性**  
   WHEN 用户切换年度，THEN 所有项目域数据请求都必须携带新年度，且旧年度缓存必须失效。
3. **Property 3：权限前后端一致性**  
   对任一操作 code，前端可见性判断与后端授权判断 SHALL 使用同一权限矩阵定义。
4. **Property 4：枚举 value 不可变性**  
   管理端只能修改 label/color，任何修改 value、删除 value、新增未登记 value 的请求 SHALL 被拒绝。
5. **Property 5：归档只读不变量**  
   archived 项目默认不允许写入底稿、报表、附注、附件元数据和复核结论，除非存在有效临时授权。

## 依赖关系

- 依赖现有 `auth` / `project` / `roleContext` store。
- 依赖后端 `permission_service.py`、`project_permissions.py`、`system_dicts.py`。
- 被 `platform-linkage-contract-stale`、`platform-role-workbench-quality-loop`、`platform-ui-editing-consistency` 依赖。

## UAT 场景

1. 审计助理从项目 A 切到项目 B，确认底稿列表、年度、待办、编辑锁全部刷新。
2. 项目经理切换 2025/2026 年度，确认报表、附注、试算表不串年。
3. QC 用户访问经理专属设置项，应前端不可见且后端拒绝。
4. 管理员修改枚举 label/color 后，状态标签即时按新展示生效。
