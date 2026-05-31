# 实施计划：多准则状态统一（multi-standard-unification）

## 概述

分 3 阶段：数据模型 + 统一源 → 底稿切换能力 → 联动接入 + 迁移。

## 任务

- [ ] 1. 数据模型：新增 applicable_standard_v2
  - [ ] 1.1 编写迁移 `V0XX__add_applicable_standard_v2.sql`
    - ALTER TABLE projects ADD COLUMN IF NOT EXISTS applicable_standard_v2 JSONB
    - _Requirements: 1.1_
  - [ ] 1.2 更新 Project ORM 模型
    - 加 `applicable_standard_v2: Mapped[dict | None] = mapped_column(JSONB, nullable=True)`
    - _Requirements: 1.1_
  - [ ] 1.3 新增 STANDARD_CHANGED 事件类型
    - EventType enum 加 `STANDARD_CHANGED = "standard_changed"`
    - _Requirements: 1.5_

- [ ] 2. 统一源服务：standard_unification_service
  - [ ] 2.1 新建 `backend/app/services/standard_unification_service.py`
    - `get_standard(project_id)` → 读 applicable_standard_v2（fallback 旧字段）
    - `set_standard(project_id, new_standard, changed_by)` → 写 v2 + 双写旧字段 + 发事件
    - `derive_from_wizard(wizard_state)` → 从 template_type 推断结构化 standard
    - _Requirements: 1.2, 1.3, 1.4, 1.5_
  - [ ] 2.2 项目创建/向导完成时接入
    - 向导完成后调 `set_standard(derive_from_wizard(...))`
    - _Requirements: 1.2_

- [ ] 3. 底稿切换能力：wp_standard_conversion_service
  - [ ] 3.1 新建 `backend/app/services/wp_standard_conversion_service.py`
    - `classify_workpapers(project_id, old_standard, new_standard)` → 返回 {共有/源独有/目标独有} 三组 wp_codes
    - `convert_workpapers(project_id, classification, new_standard)` → 执行切换（共有保留/独有归档/新建）
    - `preview_conversion(project_id, old_standard, new_standard)` → 影响预览
    - _Requirements: 2.1, 2.2, 2.3, 5.1_
  - [ ] 3.2 实现共有底稿保留逻辑
    - parsed_data 不动 / working_paper 不动 / 只更新 classification（如有变化）
    - _Requirements: 2.2, 2.5_
  - [ ] 3.3 实现源独有底稿归档逻辑
    - soft delete（is_deleted=True）+ 记录 template_lineage.conversion_reason
    - _Requirements: 2.1, 2.3_
  - [ ] 3.4 实现目标独有底稿创建逻辑
    - 复用 generate_from_codes 子逻辑（建 WpIndex + WorkingPaper + 模板文件 + parsed_data）
    - _Requirements: 2.1_
  - [ ] 3.5 实现切换前置条件检查
    - 所有底稿 dirty=false / 项目非归档 / 无进行中任务
    - _Requirements: 2.4_

- [ ] 4. 切换 API + 预览 API
  - [ ] 4.1 新建 `backend/app/routers/standard_conversion.py`
    - `POST /api/projects/{pid}/standard/preview` → 影响预览
    - `POST /api/projects/{pid}/standard/convert` → 执行切换（需确认）
    - 注册到 router_registry
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 5. 联动 handler 接入
  - [ ] 5.1 附注层：STANDARD_CHANGED → note_conversion_service
    - 注册 handler，调已有 `execute_conversion`
    - 切换后更新 current_standard 与 v2 一致
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ] 5.2 报表层：STANDARD_CHANGED → 标记 stale + 更新 applicable_standard
    - _Requirements: 4.1, 4.2_

- [ ] 6. 迁移脚本
  - [ ] 6.1 新建 `backend/scripts/migrate_applicable_standard.py`
    - 从现有 4 套字段推断填充 applicable_standard_v2
    - 无法推断时默认 {entity_type: "soe", scope: "standalone", stage: "normal"}
    - 幂等（已有值不覆盖）
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 7. 测试
  - [ ]* 7.1 Property 1 属性测试：统一源一致性
    - 切换后 v2 与旧字段值一致
    - _Requirements: 1.3, 1.4_
  - [ ]* 7.2 Property 2 属性测试：底稿数据不丢失
    - 共有底稿 parsed_data 切换前后不变
    - _Requirements: 2.2_
  - [ ]* 7.3 Property 3 属性测试：roundtrip 不变量
    - SOE→Listed→SOE 共有底稿 parsed_data 与初始一致
    - _Requirements: 2.2_
  - [ ]* 7.4 单元测试
    - classify_workpapers 分类正确 / derive_from_wizard 推断正确 / 前置条件检查
    - _Requirements: 2.1, 2.4_

- [ ] 8. Final Checkpoint
  - pytest 0 回归
  - 迁移脚本对现有项目跑通（applicable_standard_v2 非空）
  - 切换预览 API 返回正确影响范围

## 说明

- 标 `*` 为可选（属性测试），核心实现任务必需
- 本 spec 只做后端能力，前端准则切换 UI 是后续 spec（wp-frontend-ux-polish）
- 不处理"合并↔单体"切换（只 SOE↔Listed）
- 底稿切换复用附注层已验证的模式（共有保留/独有归档/新建）
- 迁移脚本无 `_` 前缀（可重复跑，幂等）
