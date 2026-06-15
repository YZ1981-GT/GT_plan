# Requirements: A13 错报自动生成与跨模块溯源

## Introduction

A13 错报底稿（5 个 sheet：程序表/未更正错报汇总/未更正披露错报/评价错报/沟通）的数据来源全部在调整分录模块（adjustments 表 review_status='passed'）。当前用户需要手动将调整模块的"未更正错报"重新抄写到 A13 底稿中，造成重复劳动和数据不一致风险。需要实现 A13 从系统数据自动生成+与 A16 管理层声明书联动。

## Requirements

### Requirement 1: A13-1 未更正错报汇总表自动生成

**User Story:** 作为审计人员，A13-1 表应自动列出所有审计师发现但管理层未予更正的错报，无需手动抄录。

#### Acceptance Criteria
1. THE A13-1 SHALL 从 `adjustments WHERE review_status='passed'` 自动生成
2. EACH 错报行 SHALL 显示：序号、内容说明、索引号（来源底稿）、借方科目/金额、贷方科目/金额、错报性质、管理层不予更正原因
3. THE 错报 SHALL 按"以前期间/本期"分两节显示（对应模板中"一""二"分区）
4. THE 索引号列 SHALL 可跳转到产生该错报的底稿
5. WHEN 调整模块新增/移除 passed 错报时，A13-1 SHALL 实时更新

### Requirement 2: A13-2 列报和披露错报录入

**User Story:** 作为审计人员，列报和披露层面的错报（不影响金额，不在 adjustments 表）需要单独录入。

#### Acceptance Criteria
1. THE 系统 SHALL 提供 A13-2 披露错报独立录入入口（HTML 表单）
2. EACH 披露错报 SHALL 记录：内容说明、涉及报表项目、错报性质、管理层是否更正
3. THE 披露错报 SHALL 存储在 `workpaper_field_overrides`（scope='misstatement:disclosure'），不混入 adjustments
4. THE A13-2 SHALL 与 A13-1（金额错报）在视图中分区展示

### Requirement 3: A13-3 评价识别出的错报

**User Story:** 作为审计人员，我需要系统自动将未更正错报汇总金额与重要性水平比较，判断是否重大。

#### Acceptance Criteria
1. THE 系统 SHALL 自动计算未更正错报合计金额（AJE+RJE 分别汇总）
2. THE 系统 SHALL 自动从 materiality 取项目重要性水平
3. THE 系统 SHALL 自动比较：合计错报 vs 重要性水平，超过阈值高亮
4. THE 评价结论 SHALL 支持用户手动填写（自动提供建议文本但可修改）

### Requirement 4: A13-5 对错报的沟通

**User Story:** 作为审计人员，错报沟通记录需要追踪与管理层的沟通情况。

#### Acceptance Criteria
1. THE 沟通记录 SHALL 关联具体错报行（从 A13-1 引用）
2. THE 系统 SHALL 记录沟通日期、沟通对象、管理层反馈、最终决定
3. WHEN 管理层同意更正时，THE 系统 SHALL 允许将 passed 状态改回 approved（触发调整生效）

### Requirement 5: 与 A16 管理层声明书联动

**User Story:** 管理层声明书中的"未更正错报"段落应自动引用 A13 数据。

#### Acceptance Criteria
1. A16 声明书模板中"未更正错报"占位符 SHALL 自动填充 A13-1 的错报清单摘要
2. IF A13-1 为空（无未更正错报），THE 声明书 SHALL 填充"无未更正错报"
3. THE A16 → A13 SHALL 支持双向跳转

### Requirement 6: 与试算表审定数联动

#### Acceptance Criteria
1. THE 未更正错报汇总金额 SHALL 与 trial_balance.aje_adjustment/rje_adjustment 一致
2. IF 存在差异（如部分错报跨期），THE 系统 SHALL 高亮提示并允许说明原因
