# 需求文档：平台 UI、编辑状态与全局组件一致性

## 需求

### 需求 1：页面框架统一
1. WHEN 用户进入任何业务页面，THE system SHALL 使用统一页面头、项目上下文、工具栏和内容区布局。
2. WHEN 页面需要返回、刷新、导出、全屏、公式、导入、保存等动作，THE system SHALL 使用统一 `GtToolbar` 或业务域 toolbar。
3. THE system SHALL 禁止新页面自行实现重复的页面头与按钮组。

### 需求 2：表格组件统一
1. WHEN 页面展示列表或数据表，THE system SHALL 使用 `GtTableExtended`。
2. WHEN 页面需要行内编辑、dirty 标记、校验、撤销，THE system SHALL 使用 `GtFormTable`。
3. WHEN 新代码新增裸 `el-table`，THE CI SHALL fail，除非有明确豁免注释。

### 需求 3：金额、数值与复制粘贴统一
1. THE system SHALL 使用统一金额组件或 formatter 展示金额。
2. THE system SHALL 使用 Decimal 工具处理前端金额计算，禁止原生浮点求和。
3. WHEN 用户从 Excel 粘贴数据，THE system SHALL 识别千分位、括号负数、空格和多行多列。
4. WHEN 用户复制平台表格到 Excel，THE system SHALL 保留金额和表头格式。

### 需求 4：编辑状态机统一
1. THE system SHALL 定义统一编辑状态：pristine、dirty、saving、saved、conflict、readonly、locked、archived。
2. WHEN 页面存在未保存修改，THE system SHALL 显示统一保存状态并拦截离开。
3. WHEN 保存失败、冲突或被锁定，THE system SHALL 使用统一错误与冲突处理组件。

### 需求 5：加载、空态与异常统一
1. WHEN 页面首次加载，THE system SHALL 使用 skeleton 或统一 loading。
2. WHEN 数据为空、无权限、加载失败或功能开发中，THE system SHALL 使用 `GtEmpty` 预设。
3. WHEN API 报错，THE system SHALL 使用 `handleApiError`，禁止裸 `ElMessage.error(err.message)`。

### 需求 6：显示偏好统一
1. THE system SHALL 提供全局显示偏好，包括字号、紧凑模式、金额单位、深色模式。
2. WHEN 用户调整显示偏好，THE system SHALL 应用于试算表、底稿、报表、附注、合并表格。
3. THE system SHALL 提供字体字号与打印/导出样式的映射说明。

## 范围边界
- 不要求一次性迁移所有历史页面。
- 不引入新的 UI 组件库。
- 不改变现有 GT 视觉品牌，只做收口和治理。

## 实施批次

- **P0 核心闭环**：页面骨架试点、金额显示/Decimal、错误处理、编辑状态机。
- **P1 试点增强**：表格迁移、复制粘贴、加载空态、显示偏好。
- **P2 规模化治理**：全量页面迁移、动效细节、打印/导出样式映射。

## Properties / 验收不变量

1. **Property 1：金额展示不改变值**  
   任一 Decimal 金额经过展示、复制、粘贴、再解析后，数值 SHALL 保持一致。
2. **Property 2：编辑状态单调性**  
   dirty 页面在保存成功前不得显示 saved；保存失败不得清除 dirty。
3. **Property 3：错误处理一致性**  
   API 错误必须经过统一 handler，禁止新增裸 `ElMessage.error(err.message)`。
4. **Property 4：表格组件合规性**  
   新增裸 `el-table` 必须有豁免注释，否则 CI fail。
5. **Property 5：显示偏好全局生效**  
   字号/密度/金额单位在五类高频数据页面必须一致生效。

## 依赖关系

- 依赖 `platform-context-permission-foundation` 的 ProjectContextBar。
- 与 `platform-linkage-contract-stale` 共享穿透与状态展示组件。
- 影响所有前端高频页面，但先以试点迁移。

## UAT 场景

1. 助理从 Excel 粘贴含千分位和括号负数的数据，金额正确进入表格。
2. 用户编辑底稿后未保存离开，系统统一拦截。
3. 报表和附注页面切换紧凑/宽松模式，表格字号一致变化。
4. API 报错时页面展示统一错误文案和重试入口。
