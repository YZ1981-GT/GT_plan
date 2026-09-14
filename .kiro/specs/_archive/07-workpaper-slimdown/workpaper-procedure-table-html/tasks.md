# Implementation Plan: A循环程序表 HTML 化

## Overview

程序表模板 JSON + 自动填充服务 + 前端 HTML 渲染组件 + Excel 导出。

**依赖**：workpaper-foundation-kit（`WorkpaperHtmlTable` 渲染框架 + `FieldOverrideService` 字段覆盖存储 + `useWorkpaperNavigation` 索引跳转 + 注册表）。不再自建 override 表/渲染组件。迁移号实施时顺延。

## Tasks

- [x] 1. 程序表模板数据
  - [x] 1.1 创建 `backend/data/procedure_table_templates.json`（A1~A17 共 17 表的 items + 自动填充规则）
    - 从现有 xlsx 模板提取每表的程序条目+索引引用
    - _Requirements: 1.1, 1.2_
  - [x] 1.2 标注每项的 `auto_data_source`（数据源标识）和 `ref_index`（跳转索引）
    - _Requirements: 2.3, 1.3_

- [x] 2. 用户覆盖存储（复用基础设施）
  - [x] 2.1 使用 `FieldOverrideService`（scope='procedure_table:{code}'），不新建表
    - _Requirements: 2.4_

- [x] 3. 自动填充服务
  - [x] 3.1 新建 `procedure_table_service.py`：`get_procedure_table` 主逻辑
    - _Requirements: 1.1, 2.1, 2.2, 2.3_
  - [x] 3.2 实现各 `auto_data_source` 解析器（workpaper_completion/prior_year_comparison/adjustment_summary 等）
    - _Requirements: 2.2, 2.3, 2.5_
  - [x] 3.3 适用性自动判定（按 business_category，A1 第15项等）
    - _Requirements: 2.1, 3.5_
  - [x] 3.4 用户覆盖值合并逻辑（自动值 + override）
    - _Requirements: 2.4_
  - [x]* 3.5 自动填充 PBT（随机 category → A1 第15项适用性）
    - _Requirements: 3.5_

- [x] 4. A2 调整程序表自动生成
  - [x] 4.1 A2 从 adjustments 按 type 统计（AJE/RJE/合并/Passed 笔数+金额）
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [x] 4.2 A2 索引跳转配置（A2-2→调整模块 AJE 视图等）
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 5. A1 联动逻辑
  - [x] 5.1 A1 第3~5/9/10/14/15/17/18 项各自的数据源接入
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 6. A16 智能推荐
  - [x] 6.1 A16 程序表按项目类型高亮推荐模板版本
    - _Requirements: 5.1_
  - [x] 6.2 A16 → OnlyOffice 编辑链路 + "未更正错报"占位符填充（依赖 misstatement-auto spec）
    - _Requirements: 5.2, 5.3, 5.4_

- [x] 7. 前端组件
  - [x] 7.1 基于基础设施 `WorkpaperHtmlTable` 配置 17 个程序表渲染（不自建渲染组件）
    - _Requirements: 1.1, 1.2_
  - [x] 7.2 索引号列用 `useWorkpaperNavigation` 跳转
    - _Requirements: 1.3_
  - [x] 7.3 行内编辑通过框架失焦保存到 FieldOverrideService
    - _Requirements: 2.4_
  - [x]* 7.4 程序表配置单测
    - _Requirements: 1.1, 2.4_

- [x] 8. Excel 导出
  - [x] 8.1 复用框架导出能力（按原模板格式）
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 9. Checkpoint
  - 跑 pytest + vitest，全绿后继续

## Notes
- 依赖 workpaper-header-and-metadata（业务分类）+ workpaper-misstatement-auto（A16 错报填充）
- 迁移号顺延
