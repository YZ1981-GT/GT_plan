# 实施计划：审计证据收集体系

## 任务

- [ ] 1. PBC CRUD 填实
  - [ ] 1.1 pbc.py router 从 developing 补成真 CRUD（list/create/update/delete）
    - _Requirements: 1.1_
  - [ ] 1.2 pbc_service.py（模型已就绪，补 service 层）
    - _Requirements: 1.1_
  - [ ] 1.3 PBC 项关联底稿/审计循环
    - _Requirements: 1.2_

- [ ] 2. PBC ↔ 底稿联动
  - [ ] 2.1 底稿侧栏"证据收集"tab（显示关联 PBC 项 + 状态）
    - _Requirements: 2.1_
  - [ ] 2.2 缺失证据高亮提示
    - _Requirements: 2.2_

- [ ] 3. 原始凭证 LLM 识别
  - [ ] 3.1 新建 wp_document_recognizer（按 doc_type 调 LLM 结构化提取）
    - _Requirements: 3.1_
  - [ ] 3.2 支持记账凭证/发票/出入库单/银行回单 4+ 类型
    - _Requirements: 3.1_
  - [ ] 3.3 逐份确认 UI（复用 V3 Req6 AiContent 确认流）
    - _Requirements: 3.2_

- [ ] 4. evidence_group 升级
  - [ ] 4.1 迁移：voucher_row attachment_id→evidence_group JSONB
    - _Requirements: 3.3_
  - [ ] 4.2 前端：抽凭行展开显示多原始凭证 + 提取字段
    - _Requirements: 3.3_

- [ ] 5. 缺失资料催收
  - [ ] 5.1 PBC 逾期检测 + 自动建 IssueTicket（source=pbc）
    - _Requirements: 4.1_
  - [ ] 5.2 通知机制接入
    - _Requirements: 4.2_

- [ ] 6. 测试
  - [ ]* PBC CRUD 单测 + LLM 识别 mock 测试 + evidence_group 填充测试

## 说明
- 依赖 vllm-httpx-bugfix + wp-traceability-panel
- PBC 模型已就绪（投入小），LLM 识别是重头
