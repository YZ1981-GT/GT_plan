# 实施计划：底稿科目结论 AI 副驾驶

## 任务总览

- [ ] 1. 结论上下文服务
  - [ ] 1.1 新增 `workpaper_ai_conclusion_context_service.py`
  - [ ] 1.2 D1-C 上下文：审定表、程序状态、字段来源、调整影响
  - [ ] 1.3 D2-C 上下文：增加函证摘要、坏账/ECL、D2-5 分析程序、调整影响、披露影响
  - [ ] 1.4 上下文只从 `account_package_summary_service`、字段来源契约和 AI 目标绑定读取，不直接解析 generated schema
  - [ ] 1.5 缺失上下文进入 `missing`
  - [ ] 1.6 测试：上下文缺失、函证为空、坏账/ECL 不完整、调整影响存在时均输出结构化 `missing` 或来源摘要
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] 2. AI 草稿生成
  - [ ] 2.1 新增结论草稿 prompt 模板
  - [ ] 2.2 调用既有 AI 服务生成草稿
  - [ ] 2.3 写入 `ai_content_log_service`
  - [ ] 2.4 写入 `account_package_id`、`wp_id`、`sheet_type=conclusion`、`field_id` 目标绑定
  - [ ] 2.5 返回 pending log id、目标绑定和来源摘要
  - [ ] 2.6 增加 prompt fixture / golden tests，覆盖 missing、函证为空、坏账/ECL 不完整、调整影响存在四类输入
  - [ ] 2.7 测试：prompt 不得引导 AI 编造函证、坏账、附件、程序状态或未来源化结论
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.5_

- [ ] 3. AI 内容治理复用
  - [ ] 3.1 复用确认、修订确认、拒绝 API
  - [ ] 3.2 pending 状态接入工作包提示
  - [ ] 3.3 sign_off 继续由既有 gate rule 阻断
  - [ ] 3.4 后端保存 D1-C / D2-C 结论时校验 AI log 状态
  - [ ] 3.5 后端保存正式结论时校验 AI log 的 `account_package_id`、`wp_id`、`sheet_type`、`field_id` 与当前结论字段一致
  - [ ] 3.6 测试：pending 阻断，确认后放行，拒绝后不写入
  - [ ] 3.7 测试：拒绝旧草稿后可重新生成新草稿，但旧草稿不得进入正式结论
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.5_

- [ ] 4. 前端结论面板
  - [ ] 4.1 新增或扩展 D1-C/D2-C 结论区域
  - [ ] 4.2 接入“生成 AI 草稿”按钮
  - [ ] 4.3 展示 AI 草稿标签、来源摘要、missing 项
  - [ ] 4.4 支持确认、修订确认、拒绝
  - [ ] 4.5 当目标绑定不完整或上下文 missing 时，前端明确展示不可生成或需人工补充的原因
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 5. 审计留痕
  - [ ] 5.1 记录 prompt、模型、上下文摘要
  - [ ] 5.2 记录 AI 原文、用户修订文、确认/拒绝人
  - [ ] 5.3 拒绝时要求原因
  - [ ] 5.4 来源摘要可跳转到字段来源或工作包卡片
  - [ ] 5.5 AI content log 治理面板可按目标绑定跳转回 D1-C / D2-C
  - [ ] 5.6 测试：AI content log 查询可按 account_package_id、wp_id、field_id 过滤并跳转
  - _Requirements: 5.1, 3.4_

## P0-MVP：D1-C

- [ ] MVP-1. D1-C 可生成 AI 结论草稿
- [ ] MVP-2. 草稿写入 `ai_content_log` 且状态为 pending
- [ ] MVP-3. 草稿日志绑定到 D1-C 目标字段
- [ ] MVP-4. 未确认时 sign_off 被阻断
- [ ] MVP-5. 确认后进入结论字段
- [ ] MVP-6. 拒绝后不进入结论字段
- [ ] MVP-7. 保存正式结论时校验 AI log 目标绑定与当前字段一致

## P1：D2-C

- [ ] P1-1. D2-C 上下文接入函证摘要
- [ ] P1-2. D2-C 上下文接入坏账/ECL 和 D2-5 分析程序结果
- [ ] P1-3. D2-C 草稿引用调整和附注影响
- [ ] P1-4. 缺失资料以 missing 显示，不生成确定性判断
- [ ] P1-5. D2-C 上下文不直接解析 generated schema

## 验收与回归

- [ ] CI-1 pytest：上下文缺失项、草稿日志、pending 阻断、确认放行
- [ ] CI-2 pytest：拒绝草稿不写入结论
- [ ] CI-3 pytest：保存正式结论时校验目标 AI log 状态和目标绑定一致性
- [ ] CI-4 pytest：拒绝旧草稿后可重新生成新草稿，旧草稿不得进入正式结论
- [ ] CI-5 pytest：prompt fixture / golden tests 覆盖 missing、函证为空、坏账/ECL 不完整、调整影响存在
- [ ] CI-6 Vitest：草稿标签、来源摘要、目标绑定、确认、修订、拒绝交互
- [ ] UAT-1 助理生成 D1-C 草稿并看到 AI 标记
- [ ] UAT-2 经理修订确认 D1-C 草稿
- [ ] UAT-3 合伙人签发前看到未确认 AI 草稿阻断
- [ ] UAT-4 D2-C 草稿展示函证和坏账来源摘要
