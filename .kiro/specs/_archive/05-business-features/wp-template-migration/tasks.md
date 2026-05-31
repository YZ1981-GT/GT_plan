# 实施计划：模板版本升级数据迁移

## 任务

- [x] 1. 模板 diff 引擎
  - [x] 1.1 新建 `backend/app/services/wp_template_diff_service.py`
    - _Requirements: 1.1_
  - [x] 1.2 openpyxl 读两版本 xlsx → 生成 TemplateDiff（sheet/列级增删改名）
    - _Requirements: 1.1, 1.2_
  - [x] 1.3 单元测试（构造两版本模板 → 断言 diff 正确）
    - _Requirements: 1.1_

- [x] 2. 数据迁移引擎
  - [x] 2.1 新建 `backend/app/services/wp_migration_service.py`
    - _Requirements: 2.1_
  - [x] 2.2 按 TemplateDiff 迁移 parsed_data（共有保留/新增填默认/删除归档）
    - _Requirements: 2.2, 2.3, 2.4_
  - [x] 2.3 迁移前快照存 wp_migration_snapshots 表
    - _Requirements: 4.1_
  - [x] 2.4 回滚 API（恢复快照）
    - _Requirements: 4.2_

- [x] 3. 迁移报告
  - [x] 3.1 生成 markdown 报告（成功/跳过/需人工处理）
    - _Requirements: 3.1_
  - [x] 3.2 "需人工处理"标记机制
    - _Requirements: 3.2_

- [x] 4. 迁移脚本
  - [x] 4.1 `backend/scripts/migrate_template_version.py`（批量执行迁移）
    - _Requirements: 2.1_
  - [x] 4.2 幂等（已迁移不重复）
    - _Requirements: 2.1_

- [x] 5. 测试
  - [x]* Property 1：共有数据不丢失
    - _Requirements: 2.2_
  - [x]* Property 2：回滚后数据恢复
    - _Requirements: 4.2_
  - [x]* 集成测试：真实模板 v2025-R5→R6 diff + 迁移
    - _Requirements: 1.1, 2.1_

## 说明
- 中长期能力，年度修订必遇
- 不改模板文件本身
- 约 2 周
