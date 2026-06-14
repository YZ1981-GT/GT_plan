# Implementation Plan: 复核流程 HTML 化与签署工作流

## Overview

复核检查要点模板 + 复核记录表 + 独立性签署表 + 复核流程服务 + 签署服务 + 前端面板 + 归档导出。

**依赖**：workpaper-foundation-kit（`WorkpaperHtmlTable` 渲染框架 + `FieldOverrideService` + 索引跳转 + 注册表）。迁移号实施时顺延。**START GATE**：先确认现有 review_status 机制边界，本 spec 生成复核记录底稿但不替代底稿级状态机。

## Tasks

- [x] 1. 模板与数据模型
  - [x] 1.1 创建 `backend/data/review_checklist_templates.json`（A21~A25 各级×财报/内控 检查要点）
    - _Requirements: 1.1, 1.5_
  - [x] 1.2 V080/R080 迁移：`review_records` + `independence_signing_tasks` 两表
    - _Requirements: 4.1, 3.4_

- [x] 2. 复核流程服务
  - [x] 2.1 新建 `review_workflow_service.py` 骨架
    - _Requirements: 1.1_
  - [x] 2.2 `get_review_panel`：按角色+审计类型匹配模板 + 自动检查项取值
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 2.3 `save_review`：保存复核勾选+意见
    - _Requirements: 1.x_
  - [x] 2.4 `get_completion_checklist`：A17-5 按项目类型选版本 + 自动校验
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 2.5 `generate_archive_file`：生成 A21~A25 归档 Excel/PDF
    - _Requirements: 4.1, 4.2_
  - [ ]* 2.6 角色→模板匹配 PBT
    - _Requirements: 1.3, 1.4_

- [x] 3. 独立性签署服务
  - [x] 3.1 新建 `independence_signing_service.py`
    - _Requirements: 3.1_
  - [x] 3.2 `initiate_signing`：为成员创建签署任务
    - _Requirements: 3.1, 3.2_
  - [x] 3.3 `sign` + `get_signing_progress`：签署+进度
    - _Requirements: 3.3, 3.4, 3.5, 3.7_
  - [x] 3.4 A17-7A 按角色推专委会委员
    - _Requirements: 3.6_

- [x] 4. API 端点
  - [x] 4.1 review-panel/save-review/completion-checklist/archive 端点
    - _Requirements: 1.x, 2.x, 4.x_
  - [x] 4.2 signing initiate/sign/progress 端点
    - _Requirements: 3.x_

- [x] 5. 前端
  - [x] 5.1 新建 `ReviewPanel.vue`（分级复核面板，逐项勾选+关联底稿+意见）
    - _Requirements: 1.1, 1.2_
  - [x] 5.2 A17-5 完成核对表弹窗（签发前置关卡）
    - _Requirements: 2.1, 2.4, 2.5_
  - [x] 5.3 独立性签署：我的待办任务 + 签署界面 + 进度面板
    - _Requirements: 3.2, 3.3, 3.5_
  - [x] 5.4 导入空白模板/导出标准格式
    - _Requirements: 4.3, 4.4, 4.5_
  - [x]* 5.5 前端单测

- [x] 6. 生命周期联动
  - [x] 6.1 复核阶段进度从各级完成状态计算
    - _Requirements: 5.1, 5.2_
  - [x] 6.2 委派执行阶段进度从底稿编制率计算
    - _Requirements: 5.3_
  - [x] 6.3 A1 程序表联动复核状态
    - _Requirements: 5.4_

- [x] 7. Checkpoint
  - 22 后端测试(18 CF + 4 review PBT) + 10 前端 vitest 全绿 + imports 验证通过

## Notes
- 复核要点从 Excel 模板提取（可配置）
- 迁移号顺延
