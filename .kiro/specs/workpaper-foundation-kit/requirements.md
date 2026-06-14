# Requirements: 底稿基础设施套件（A循环改造地基）

## Introduction

A循环 6 个改造 spec（表头/程序表/CF/错报/复核/报表分析）共享一组基础能力：索引跳转、字段覆盖存储、HTML 表格渲染框架、底稿类型注册表。如果各 spec 各自实现会产生大量重复代码和不一致。本 spec 先行建立这些统一基础设施，作为其余 6 个 spec 的依赖地基。

## Requirements

### Requirement 1: 统一底稿索引跳转

**User Story:** 作为开发者，我需要一个统一的"索引号→底稿/视图"跳转机制，所有底稿中的索引引用（如 A1-17、A2-2、B13-1）点击后都能正确导航。

#### Acceptance Criteria
1. THE 系统 SHALL 提供前端 composable `useWorkpaperNavigation`，输入 wp_code 返回导航目标
2. THE 跳转 SHALL 解析索引号到具体路由：底稿→底稿编辑器、程序表→HTML视图、报表→报表模块、附注→附注编辑器
3. IF 索引号对应底稿不存在（未生成），THE 系统 SHALL 提示"该底稿尚未生成"而非报错
4. THE 索引号 SHALL 支持模糊匹配（A1-13,A1-14 多个引用拆分为多个可点击链接）
5. THE 跳转机制 SHALL 维护索引号→底稿类型的映射注册表（可配置）

### Requirement 2: 统一字段覆盖存储

**User Story:** 作为开发者，多个底稿模块都有"系统自动算值+用户可覆盖"的模式，需要统一的覆盖值存储，避免每个模块建一张表。

#### Acceptance Criteria
1. THE 系统 SHALL 提供统一表 `workpaper_field_overrides`（project_id/year/scope/item_key/field/value/updated_by/updated_at）
2. THE scope SHALL 区分不同底稿域（如 'procedure_table:A1'、'review:A23'、'report_analysis:bs_trend'）
3. THE 系统 SHALL 提供通用读写服务 `FieldOverrideService.get/set/get_batch`
4. THE 覆盖值 SHALL 支持任意 JSON 值（字符串/数字/布尔/对象）
5. THE 服务 SHALL 提供"自动值 + 覆盖值合并"辅助函数（覆盖优先）

### Requirement 3: HTML 底稿渲染框架

**User Story:** 作为开发者，程序表/核查表/复核表都是"表头+结构化表格"形式，需要统一的 HTML 渲染框架。

#### Acceptance Criteria
1. THE 系统 SHALL 提供通用组件 `WorkpaperHtmlTable`，支持配置驱动渲染（列定义+行数据+表头）
2. THE 框架 SHALL 统一渲染致同标准表头（致同事务所/底稿名/客户+编制+复核+索引+日期）
3. THE 框架 SHALL 支持列类型：文本、三态勾选(是/否/不适用)、可编辑文本、索引链接、自动计算值（只读）
4. THE 框架 SHALL 支持行内编辑 + 失焦保存到字段覆盖存储
5. THE 框架 SHALL 统一"导出 Excel"能力（按致同模板格式）
6. THE 框架 SHALL 应用 GT 紫令牌样式 + 紧凑表格类

### Requirement 4: 底稿类型注册表

**User Story:** 作为系统，我需要知道每个底稿用什么形式呈现（HTML/Univer/Word/只读），以正确路由和渲染。

#### Acceptance Criteria
1. THE 系统 SHALL 维护底稿类型注册表 `workpaper_render_registry.json`
2. EACH 底稿 SHALL 标注 render_type：'html_procedure'/'html_review'/'auto_report'/'univer'/'word_template'/'readonly_reference'/'signing'
3. THE 注册表 SHALL 标注每个底稿的关联模块/数据源/适用业务类型
4. WHEN 打开底稿时，THE 系统 SHALL 按注册表 render_type 选择渲染组件
5. THE 注册表 SHALL 可扩展（新增底稿类型不改代码）

### Requirement 5: 底稿溯源链

**User Story:** 作为审计人员，我需要看到底稿之间的数据流转关系（如错报→声明书、调整→试算表→报表）。

#### Acceptance Criteria
1. THE 系统 SHALL 维护底稿间引用关系（source_wp → target_wp + 数据字段）
2. THE 系统 SHALL 提供"溯源视图"展示某底稿数据的上下游来源
3. WHEN 上游底稿数据变更时，THE 下游底稿 SHALL 标记 stale（复用现有 linkage stale 机制）
