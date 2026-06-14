# Implementation Plan: 底稿基础设施套件

## Overview

4 大共享基础设施：字段覆盖存储(V076) + 索引跳转 composable + HTML 渲染框架组件 + 底稿类型注册表。本 spec 是 A 循环其余 6 spec 的依赖地基，应最先实施。

## Tasks

- [x] 1. 字段覆盖存储
  - [x] 1.1 V076/R076 迁移：`workpaper_field_overrides` 表（三层一致）
    - _Requirements: 2.1, 2.2_
  - [x] 1.2 ORM 模型 `WorkpaperFieldOverride`
    - _Requirements: 2.1_
  - [x] 1.3 新建 `field_override_service.py`：get/get_batch/set/merge
    - _Requirements: 2.3, 2.4, 2.5_
  - [x] 1.4 API 端点：GET/POST `/api/workpapers/field-overrides`
    - _Requirements: 2.3_
  - [x]* 1.5 set/get 往返 PBT（随机 scope+item_key+field+value）
    - _Requirements: 2.3, 2.4_

- [x] 2. 底稿类型注册表
  - [x] 2.1 创建 `backend/data/workpaper_render_registry.json`（A循环全底稿标注 render_type+module+categories+溯源关系）
    - _Requirements: 4.1, 4.2, 4.3, 5.1_
  - [x] 2.2 后端注册表加载服务 + API `GET /api/workpapers/render-registry`
    - _Requirements: 4.4, 4.5_
  - [x]* 2.3 注册表 schema 校验测试
    - _Requirements: 4.1_

- [x] 3. 索引跳转
  - [x] 3.1 前端 `useWorkpaperRegistry` composable（加载注册表+lookup）
    - _Requirements: 1.5_
  - [x] 3.2 前端 `useWorkpaperNavigation`：parseIndexRefs + navigateToWorkpaper
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x]* 3.3 parseIndexRefs 单测（多索引拆分/不存在处理）
    - _Requirements: 1.4_

- [x] 4. HTML 渲染框架
  - [x] 4.1 新建 `WorkpaperHtmlTable.vue`：配置驱动渲染（header+columns+rows）
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 4.2 列类型实现：text/tristate/editable/indexLink/computed
    - _Requirements: 3.3_
  - [x] 4.3 行内编辑 + 失焦保存到 FieldOverrideService
    - _Requirements: 3.4_
  - [x] 4.4 统一致同标准表头渲染
    - _Requirements: 3.2_
  - [x] 4.5 统一"导出 Excel"能力
    - _Requirements: 3.5_
  - [x] 4.6 GT 紫令牌 + gt-compact-table 样式
    - _Requirements: 3.6_
  - [x]* 4.7 组件测试（各列类型渲染+失焦保存）
    - _Requirements: 3.3, 3.4_

- [x] 5. 溯源链
  - [x] 5.1 注册表 upstream/downstream 字段 + 溯源关系定义
    - _Requirements: 5.1_
  - [x] 5.2 `WorkpaperTraceView.vue` 溯源视图组件
    - _Requirements: 5.2_
  - [x] 5.3 复用现有 linkage stale 机制标记下游
    - _Requirements: 5.3_

- [x] 6. Checkpoint
  - pytest + vitest 全绿；其余 6 spec 可开始依赖本套件

## Notes
- 本 spec 最先实施，占用 V076（其余 spec 迁移号顺延 V077+）
- 迁移号实施时确认当前最高顺延勿写死
- PBT max_examples=5
