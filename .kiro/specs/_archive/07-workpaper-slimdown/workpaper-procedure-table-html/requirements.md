# Requirements: A循环程序表 HTML 化

## Introduction

A循环中有 17+ 个程序表（A1~A17），当前作为 Excel 底稿存在，用户需要手动勾选"是否适用"、填写"执行人"和"执行情况说明"。这些程序表的大部分信息可以从系统已有数据自动填充。将其改为 HTML 结构化表格，支持自动填充+索引跳转+状态联动。

## Requirements

### Requirement 1: 程序表统一 HTML 渲染

**User Story:** 作为审计人员，我打开程序表时希望看到结构清晰的 HTML 表格（而非 Excel），其中大部分字段已自动填好，我只需确认和补充。

#### Acceptance Criteria
1. THE 以下程序表 SHALL 以 HTML 结构化表格呈现（非 Univer/Excel）：A1/A2/A3/A4/A5/A6/A7/A8/A9/A10/A11/A12/A13/A14/A15/A16/A17
2. EACH 程序表 SHALL 包含列：序号、程序描述、是否适用（三态勾选）、执行人、执行情况说明、索引号、备注
3. THE "索引号"列中的引用（如 A1-17、A2-2、A1-13）SHALL 渲染为可点击链接，跳转到对应底稿
4. THE 程序表 SHALL 保留表头信息（客户名/编制人/复核人/索引号/日期），从项目元数据自动填充

### Requirement 2: 自动填充逻辑

**User Story:** 作为系统，我根据项目状态自动判断程序表各项的执行情况。

#### Acceptance Criteria
1. "是否适用"列 SHALL 根据项目类型(A/B/C)+属性自动预判（如 A1 第15项"重大事项决定程序"：非 A 类→自动标"不适用"）
2. "执行人"列 SHALL 从 project_assignments 自动取对应循环的负责人
3. "执行情况说明"SHALL 根据关联底稿/模块状态自动生成摘要文本（如"已完成12笔审计调整，金额合计 XXX 万元"）
4. THE 用户 SHALL 可以覆盖自动填充值（手动修改适用性/说明）
5. WHEN 关联底稿状态变化时，THE 程序表对应行 SHALL 自动更新说明

### Requirement 3: A1 财务报告程序表特殊逻辑

**User Story:** A1 是最核心的程序表（18项），每项都有明确的系统联动数据源。

#### Acceptance Criteria
1. A1 第3~5项（核对） SHALL 自动关联试算表与报表/底稿核对状态
2. A1 第9项（分析性复核）SHALL 跳转 A1-13/A1-14 并显示完成状态
3. A1 第10项（披露检查表）SHALL 跳转 A1-15/A1-16 并显示完成状态
4. A1 第14项（审计报告）SHALL 关联交付模块报告生成状态
5. A1 第15项（重大事项）SHALL 根据业务类别判定适用性+跳转 A1-12
6. A1 第17项（管理层声明书）SHALL 跳转 A16 模块并显示签回状态
7. A1 第18项（关键审计事项）SHALL 跳转 A17-2 并显示完成状态

### Requirement 4: A2 调整分录程序表自动生成

**User Story:** A2 程序表的 5 项内容完全可以从调整分录模块自动统计。

#### Acceptance Criteria
1. A2 审计调整(AJE) SHALL 自动显示笔数+金额汇总，索引跳转调整模块(filter=AJE)
2. A2 重分类(RJE) SHALL 同上，跳转调整模块(filter=RJE)
3. A2 合并分录 SHALL 跳转合并模块抵销分录视图
4. A2 未调整分录(Passed) SHALL 跳转 adjustments(review_status=passed) 汇总视图
5. A2 "综合作用调"列 SHALL 从 trial_balance.aje_adjustment + rje_adjustment 取

### Requirement 5: A16 管理层声明书智能推荐

**User Story:** A16 有 7 种版本，系统应根据项目类型自动推荐恰当版本。

#### Acceptance Criteria
1. A16 程序表 SHALL 高亮推荐适用的模板版本（一般→16-1、整合→16-2、IPO→16-3等）
2. THE 用户点击推荐模板后 SHALL 进入 OnlyOffice 编辑链路（预填占位符→编辑→保存→下载）
3. A16 声明书中"未更正错报"段落 SHALL 自动从 adjustments(passed) 拉取填充
4. THE 系统 SHALL 记录声明书发送/签回状态（待发送→已发送→已签回）

### Requirement 6: 程序表导出

**User Story:** 归档时需要将 HTML 程序表导出为致同标准 Excel 格式。

#### Acceptance Criteria
1. EACH HTML 程序表 SHALL 支持"导出 Excel"功能
2. THE 导出 SHALL 按照原模板格式（含表头+合并单元格）生成标准 xlsx
3. THE 导出 SHALL 包含所有已填充数据（自动+手动）
