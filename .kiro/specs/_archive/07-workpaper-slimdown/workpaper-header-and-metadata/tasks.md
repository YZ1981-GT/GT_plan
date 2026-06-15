# Implementation Plan: 底稿表头自动填充与业务分类裁剪

## Overview

后端迁移(business_category) + 表头填充服务 + 裁剪 API；前端创建项目业务分类选择 + 裁剪确认弹窗。Python + FastAPI + Vue 3 + Vitest + pytest。

**依赖**：workpaper-foundation-kit（底稿类型注册表用于裁剪预选）。迁移号实施时确认当前最高顺延（基础设施占 V076，本 spec 顺延）。

## Tasks

- [x] 1. 数据模型与迁移
  - [x] 1.1 迁移（号顺延）：`projects` 表加 `business_category VARCHAR(10) DEFAULT 'C'`
    - 三层一致：迁移 + ORM `Mapped[]` + service；CREATE/ALTER 必 IF NOT EXISTS
    - _Requirements: 2.1_
  - [x] 1.2 `wp_account_mapping.json` 扩展 `applicable_categories` 字段（206 条标注）
    - _Requirements: 4.1, 4.4_
  - [x] 1.3 创建 `backend/data/business_category_reference.json`（A1~A8/B1~B6/C 定义+质控措施+专属底稿清单）
    - _Requirements: 2.5_

- [x] 2. 表头填充服务
  - [x] 2.1 新建 `backend/app/services/wp_header_service.py`：`WpHeaderService.fill_header` 返回表头字段映射
    - 复用现有 `_render_template_var` 占位符机制
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 2.2 集成到底稿生成流程：`generate_project_workpapers` 生成时调用表头填充
    - _Requirements: 1.1_
  - [x] 2.3 前端 Univer 渲染时表头区域(前5行)设只读
    - _Requirements: 1.4_
  - [x] 2.4 项目信息变更时表头同步（watch project 更新事件）
    - _Requirements: 1.5_
  - [x]* 2.5 表头填充单元测试（占位符替换正确性）
    - _Requirements: 1.1, 1.2_

- [x] 3. 业务分类后端
  - [x] 3.1 项目创建/更新 API 接受 `business_category` 参数
    - _Requirements: 2.1, 2.6_
  - [x] 3.2 实现 `is_template_applicable(template, category)` 判定函数
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 3.3 新增 `GET /api/workpapers/template-list` 端点（返回模板+applicable 预判）
    - _Requirements: 3.1, 3.3_
  - [x]* 3.4 业务分类过滤 PBT（随机 category → 验证 A 类专属裁剪）
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 4. 底稿裁剪
  - [x] 4.1 修改 `generate_project_workpapers` 接受 `selected_templates` 参数
    - _Requirements: 3.5_
  - [x] 4.2 `POST /api/workpapers/generate` 端点支持裁剪列表
    - _Requirements: 3.5, 3.6_

- [x] 5. 前端
  - [x] 5.1 创建项目页增加业务分类下拉选择 + "查看分类标准"弹窗
    - _Requirements: 2.1, 2.5_
  - [x] 5.2 新建 `WorkpaperTrimDialog.vue`：树形 checkbox 按循环分组 + 自动预选
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 5.3 "生成底稿"按钮先弹裁剪确认，确认后调用生成 API
    - _Requirements: 3.1, 3.5_
  - [x]* 5.4 裁剪逻辑前端单测（预选规则）
    - _Requirements: 3.3_

- [x] 6. Checkpoint
  - 跑 pytest + vitest，全绿后继续

## Notes
- 迁移号确认当前最高后顺延（V075 已用→本 spec 用 V076）
- 前端路径 `audit-platform/frontend/src/`
- PBT max_examples=5
