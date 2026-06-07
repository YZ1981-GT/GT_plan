# 实施计划：D1/D2 科目工作包试点

## 任务总览

- [ ] 1. 工作包注册表
  - [ ] 1.1 消费 `docs/reference/workpaper-d1-d2-inventory.md`，确认 D1/D2 生产 schema、generated 草稿和口径冲突
  - [ ] 1.2 新增 `account_package_registry` 配置
  - [ ] 1.3 配置 D1 应收票据工作包，generated D1 仅作为 sheet inventory 来源
  - [ ] 1.4 配置 D2 应收账款工作包，优先引用 `D2A.yaml`、`D-D2-8.yaml`、`D-D2-13.yaml`、`C-D2-disclosure.yaml` 等生产 schema
  - [ ] 1.5 当 inventory 尚未确认 report_row / note_section 时，注册表输出 `mapping_status=pending_inventory_reconciliation`
  - [ ] 1.6 测试：注册表 schema 和必填字段
  - [ ] 1.7 测试：注册表不得直接引用 `backend/data/wp_render_schema/generated/*.yaml` 作为生产 schema
  - [ ] 1.8 测试：`mapping_status=pending_inventory_reconciliation` 时不得把 report_row / note_section 当作已确认口径
  - _Requirements: 1.1, 1.2, 5.3_

- [ ] 2. 工作包摘要服务
  - [ ] 2.1 新增 registry 读取服务
  - [ ] 2.2 新增 summary 服务，解析 wp_code 到 wp_id
  - [ ] 2.3 定义 summary DTO，包含 `registry_status`、`mapping_status`、`program_status_summary`、`external_cards`、`stale_summary`、`missing_sources`
  - [ ] 2.4 聚合 sheet、程序状态、字段来源、stale 状态
  - [ ] 2.5 API：工作包列表和详情
  - [ ] 2.6 测试：D2 部分 sheet 或 schema 缺失时，summary 返回 missing 卡片但工作包仍可打开
  - _Requirements: 1.2, 1.3, 1.4_

- [ ] 3. 程序状态持久化
  - [ ] 3.1 新建或复用 `account_package_program_status`
  - [ ] 3.2 支持 applicable/status/evidence/review/conclusion
  - [ ] 3.3 支持 not_applicable_reason、reviewer、reviewed_at、updated_by、updated_at 留痕字段
  - [ ] 3.4 PATCH API 更新程序状态
  - [ ] 3.5 测试：刷新后状态不丢失
  - [ ] 3.6 测试：程序标记不适用时必须填写理由
  - [ ] 3.7 测试：复核状态变更记录 reviewer 和 reviewed_at
  - _Requirements: 2.3, 5.1_

- [ ] 4. D1 技术闭环
  - [ ] 4.1 D1 工作包入口
  - [ ] 4.2 D1 sheet_type 分组导航
  - [ ] 4.3 D1 审定表字段来源面板
  - [ ] 4.4 D1-C 结论入口
  - [ ] 4.5 D1 附注来源链路：D1-1、D1-4、D1-8、D1-12 → `C-D1-disclosure`
  - [ ] 4.6 UAT：D1 技术闭环验收报告
  - _Requirements: 2.1, 2.2, 2.4, 2.5_

- [ ] 5. D2 业务闭环
  - [ ] 5.1 D2 工作包入口
  - [ ] 5.2 聚合审定表 D2-1、明细 D2-2、坏账 D2-3、调整 D2-4、分析 D2-5、检查 D2-6~D2-13、披露 C-D2-disclosure、结论 D2-C
  - [ ] 5.3 D2 函证摘要卡片
  - [ ] 5.4 D2 调整保存后下游 stale 提示
  - [ ] 5.5 D2 坏账与 ECL 分组：D2-3、D2-8、D2-9、D2-10、C-D2-disclosure
  - [ ] 5.6 D2 分析结果统一进入 `analysis_summary`，避免将账龄作为未确认独立 sheet 口径
  - [ ] 5.7 D2 多 sheet 不完整时，工作包仍可打开并明确显示缺失卡片
  - [ ] 5.8 UAT：D2 业务闭环验收报告
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 6. 函证模块边界接入
  - [ ] 6.1 明确 D0 汇总视图与函证模块边界
  - [ ] 6.2 D2 摘要读取函证事实真源
  - [ ] 6.3 `confirmation:received` 后刷新 D2 卡片
  - [ ] 6.4 测试：D2/D0 callback 与工作包摘要一致
  - [ ] 6.5 测试：工作包摘要服务不保存或覆盖函证明细状态，只消费函证 summary/metrics
  - [ ] 6.6 测试：`confirmation_service` 无数据时返回 missing/empty summary，不在底稿侧自行计算覆盖率
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 7. AI 结论依赖接入
  - [ ] 7.1 D1-C 结论入口预留 AI 草稿状态展示位
  - [ ] 7.2 D2-C 结论上下文向 `workpaper-ai-conclusion-copilot` 暴露字段来源、函证摘要、坏账/ECL、`analysis_summary`、调整影响、披露影响
  - [ ] 7.3 工作包 pending AI 草稿状态从 AI content log 读取，不重复建表
  - [ ] 7.4 测试：pending AI 草稿定位必须包含 account_package_id、wp_id、sheet_type、field_id
  - _Requirements: 2.5, 3.4_

- [ ] 8. 前端静态入口口径修正
  - [ ] 8.1 修正公式编辑器 / 公式管理器中 D1 被误标为营业收入的文案
  - [ ] 8.2 修正工作台中 D 销售循环 coreWps：D1=应收票据，D2=应收账款，D4=营业收入/收入截止或收入审定
  - [ ] 8.3 增加静态引用测试或快照，防止 D1/D2/D4 再次错配
  - _Requirements: 5.5_

## P0-MVP

- [ ] MVP-1. D1/D2 注册表可读取
- [ ] MVP-2. 注册表不直接引用 generated schema 作为生产真源
- [ ] MVP-3. D1 工作包入口可打开
- [ ] MVP-4. D1 程序状态可持久化
- [ ] MVP-5. D1 审定表关键字段可查看来源
- [ ] MVP-6. 前端静态入口 D1/D2/D4 文案修正
- [ ] MVP-7. D2 工作包能展示函证摘要占位和跳转
- [ ] MVP-8. `mapping_status=pending_inventory_reconciliation` 时，工作包明确显示映射待确认

## P1：D2 完整业务闭环

- [ ] P1-1. D2 多 sheet 聚合完整
- [ ] P1-2. 函证回函后覆盖率和差异刷新
- [ ] P1-3. 坏账/ECL 与 D2-5 分析程序结果进入 D2-C 结论上下文
- [ ] P1-4. 调整分录影响报表/附注 stale
- [ ] P1-5. D2 坏账与 ECL 分组展示完整
- [ ] P1-6. D2 部分 sheet 缺失时仍可打开并显示 missing 卡片
- [ ] P1-7. 形成 D2 模式推广说明

## 验收与回归

- [ ] CI-1 pytest：注册表、summary、program status 服务通过
- [ ] CI-2 pytest：`mapping_status=pending_inventory_reconciliation` 不会被当作已确认映射
- [ ] CI-3 pytest：D2 函证 callback 摘要一致
- [ ] CI-4 pytest：函证服务无数据时 summary 返回 missing/empty，不自行计算覆盖率
- [ ] CI-5 Vitest：工作包入口、状态刷新、函证卡片刷新通过
- [ ] CI-6 集成测试：工作包 pending AI 草稿状态可定位到 D1-C / D2-C
- [ ] CI-7 静态引用测试：D1=应收票据、D2=应收账款、D4=营业收入
- [ ] UAT-1 助理完成 D1 程序状态，刷新后仍存在
- [ ] UAT-2 经理查看 D2 函证摘要并跳转函证模块
- [ ] UAT-3 合伙人查看 D2-C 结论引用来源和下游影响
