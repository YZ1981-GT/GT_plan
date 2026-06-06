# 实施计划：附件证据、知识库与 AI 治理闭环

## 任务总览

> 本节保留主任务索引；实际排期和执行以“详细落地拆解”为准。

- [ ] 1. EvidenceRef 契约
  - [ ] 1.1 后端新增 EvidenceRef schema
  - [ ] 1.2 前端新增 EvidenceRef 类型
  - [ ] 1.3 证据跳转 route resolver
  - [ ] 1.4 测试：各 evidence_type 可序列化与跳转
  - _Requirements: 1.3, 3.1_

- [ ] 2. 附件证据属性
  - [ ] 2.1 扩展附件元数据字段
  - [ ] 2.2 上传表单补来源、取得日期、提供方、关键证据
  - [ ] 2.3 删除/替换前查询影响范围
  - [ ] 2.4 测试：被引用附件删除需确认
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 3. Office 预览/编辑统一入口
  - [ ] 3.1 新建 `AttachmentActionBar`
  - [ ] 3.2 集成预览、编辑、下载、引用四类动作
  - [ ] 3.3 展示 OnlyOffice/WOPI 健康状态
  - [ ] 3.4 只读文件明确显示只读
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 4. 复核意见证据链
  - [ ] 4.1 复核意见支持关联 EvidenceRef
  - [ ] 4.2 关闭复核意见要求关闭依据
  - [ ] 4.3 统计 Aging、重复问题、逾期未回复
  - [ ] 4.4 测试：无关闭依据不可关闭重大复核意见
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] 5. 交付件中心统一真源
  - [ ] 5.1 对齐 `audit-report-deliverable-center` 版本链
  - [ ] 5.2 报告、附注、PDF、归档导出进入交付件中心
  - [ ] 5.3 终态再导出新建版本或交付物
  - [ ] 5.4 测试：历史版本不可覆盖
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 6. 知识库真源收口
  - [ ] 6.1 梳理 KnowledgeDocument / 文件系统 / 向量索引调用方
  - [ ] 6.2 明确 DB 元数据主源、文件存储原文、索引为派生物
  - [ ] 6.3 文档更新触发索引 stale
  - [ ] 6.4 AI 引用返回文档版本和段落
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 7. AI 内容治理
  - [ ] 7.1 定义 AI 内容状态机
  - [ ] 7.2 记录 prompt、模型、上下文、输出和确认人
  - [ ] 7.3 底稿/附注/报告/签发/EQCR 接入 confirmed 校验
  - [ ] 7.4 stub/降级统一展示
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 8. 验收
  - [ ]* 附件替换影响范围 UAT
  - [ ]* AI 内容确认后才可入报告/附注
  - [ ]* 交付件中心能预览历史版本

---

## 详细落地拆解（执行以本节为准）

### P0-MVP：一周内最小可交付

- [ ] MVP-1. EvidenceRef schema 先作为 API DTO，不立即入库
- [ ] MVP-2. 附件删除/替换前展示已知影响范围
- [ ] MVP-3. AI 内容状态映射 suggestion/draft/confirmed/rejected
- [ ] MVP-4. confirmed 前进入报告/附注正式导出先 warning，后续切 blocking
- [ ] MVP-5. 测试文件落地：
  - `backend/tests/test_evidence_ref_schema.py`
  - `backend/tests/test_attachment_impact_service.py`
  - `backend/tests/test_ai_content_confirmation_gate.py`
  - `audit-platform/frontend/src/components/ai/__tests__/AiContentPendingBanner.spec.ts`
  - **验收标准**：后端 pytest mock DB in-memory 可跑；前端 vitest mock API shallow mount；核心 Property 对应 case 必须覆盖

### P0：EvidenceRef、AI 确认与附件影响范围

- [ ] P0-1. 现状盘点
  - [ ] P0-1.1 梳理附件、复核、交付件、知识库、AI 内容相关模型和 API
  - [ ] P0-1.2 梳理 OnlyOffice/WOPI、vue-office、office_preview 的实际入口
  - [ ] P0-1.3 梳理 `ai_content` 已有确认/待确认链路
  - [ ] P0-1.4 输出 `docs/reference/evidence-ai-current-inventory.md`
  - _Requirements: 1.1, 2.1, 5.1, 6.1_

- [ ] P0-2. EvidenceRef schema
  - [ ] P0-2.1 后端新增 EvidenceRef Pydantic schema
  - [ ] P0-2.2 前端新增 EvidenceRef 类型
  - [ ] P0-2.3 支持 attachment/workpaper_cell/report_paragraph/note_table/ai_output/deliverable
  - [ ] P0-2.4 测试：EvidenceRef 可跳转、可序列化
  - _Requirements: 1.3, 3.1_

- [ ] P0-3. 附件影响范围
  - [ ] P0-3.1 先出 ADR：附件证据属性是否新增列，或先用 metadata JSON
  - [ ] P0-3.2 如新增列，编写 Vxxx migration + rollback
  - [ ] P0-3.3 同步 ORM、Pydantic schema、service
  - [ ] P0-3.4 编写三层一致契约测试
  - [ ] P0-3.5 扩展附件上传表单：来源、取得日期、提供方、关键证据
  - [ ] P0-3.6 新增影响范围查询 service
  - [ ] P0-3.7 删除/替换附件前弹窗展示影响范围
  - [ ] P0-3.8 pytest：被引用关键附件删除必须确认
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] P0-4. Office 预览/编辑状态
  - [ ] P0-4.1 新建 `AttachmentActionBar`
  - [ ] P0-4.2 接入预览、编辑、下载、引用
  - [ ] P0-4.3 显示 OnlyOffice/WOPI health 与只读状态
  - [ ] P0-4.4 UAT：docx/xlsx/pdf 三类附件动作清晰
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] P0-5. AI 内容状态机最小闭环
  - [ ] P0-5.1 对齐现有 `ai_content` 状态，映射 suggestion/draft/confirmed/rejected
  - [ ] P0-5.2 前端统一 `AiContentPendingBanner` 和确认弹窗
  - [ ] P0-5.3 底稿/附注生成结果标记 AI 状态
  - [ ] P0-5.4 增加 `AI_CONTENT_CONFIRMATION_STRICT` 开关
  - [ ] P0-5.5 strict=false 时 warning；strict=true 时 blocking
  - [ ] P0-5.6 测试：draft AI 内容在 strict=true 时被签发阻断
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

### P1：复核证据链与交付件中心对齐

- [ ] P1-1. 复核意见证据链
  - [ ] P1-1.1 复核意见支持关联 EvidenceRef
  - [ ] P1-1.2 UI 支持关联底稿单元格、附件、报告段落、附注表格
  - [ ] P1-1.3 关闭重大复核意见必须填写关闭依据
  - [ ] P1-1.4 统计 Aging、重复问题、逾期未回复
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] P1-2. 交付件中心对齐
  - **边界澄清**：本 spec 不新建版本模型，只做引用接入（EvidenceRef 指向 deliverable-center 的版本 ID）。版本链、生成、签发、归档逻辑归 `audit-report-deliverable-center` spec
  - [ ] P1-2.1 复用 `audit-report-deliverable-center` 的版本链
  - [ ] P1-2.2 报告、附注、PDF、签发文件进入交付件中心
  - [ ] P1-2.3 终态再导出新建版本或交付物
  - [ ] P1-2.4 测试：历史版本不可覆盖
  - _Requirements: 4.1, 4.2, 4.3_

### P2：知识库真源与索引治理

- [ ] P2-1. 知识库真源 ADR
  - [ ] P2-1.1 盘点 KnowledgeDocument DB、文件系统、向量索引调用方
  - [ ] P2-1.2 明确 DB 元数据主源、对象/文件存储原文、向量索引派生
  - [ ] P2-1.3 输出 ADR：知识库真源与索引生命周期
  - _Requirements: 5.1_

- [ ] P2-2. 知识引用与索引 stale
  - [ ] P2-2.1 AI 引用返回文档版本、段落、引用位置
  - [ ] P2-2.2 文档更新后标记旧索引 stale
  - [ ] P2-2.3 重建索引后解除 stale
  - [ ] P2-2.4 测试：旧索引不可作为 confirmed AI 来源
  - _Requirements: 5.2, 5.3_

### 验收与回归

- [ ] UAT-1 助理：上传关键附件并关联到底稿
- [ ] UAT-2 复核人：提出意见并关联附件，关闭时补依据
- [ ] UAT-3 合伙人：AI 未确认内容阻断签发
- [ ] UAT-4 用户：查看历史交付件版本不被覆盖
- [ ] CI-1 EvidenceRef schema 测试通过
- [ ] CI-2 AI confirmed 阻断测试通过
- [ ] CI-3 附件影响范围测试通过
