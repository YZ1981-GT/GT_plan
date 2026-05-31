# 实施计划：底稿性能与虚拟滚动

## 任务

- [ ] 1. el-table-v2 条件虚拟化
  - [ ] 1.1 GtCNoteTable / d-form-table 类组件：>500 行时切 el-table-v2
    - _Requirements: 1.1, 3.1, 3.2_
  - [ ] 1.2 复用 TrialBalance 已有的 el-table-v2 模式（headerCellRenderer / cellRenderer / rowEventHandlers）
    - _Requirements: 1.1_
  - [ ] 1.3 g-generic-table（如已建）直接用 el-table-v2
    - _Requirements: 1.1_

- [ ] 2. 性能基准验证
  - [ ] 2.1 编写性能基准测试（冷启动 / 500 行渲染 / 滚动帧率）
    - _Requirements: 2.1, 2.2, 2.3_
  - [ ] 2.2 断言达标（<50ms / <200ms / ≥60fps）
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. 验收
  - [ ]* Playwright：打开大底稿（>500 行）→ 滚动流畅 → 无卡顿
    - _Requirements: 1.2_

## 说明
- 复用 TrialBalance 已有的 el-table-v2 模式
- 约 1 周
