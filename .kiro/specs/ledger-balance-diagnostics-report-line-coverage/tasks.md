# 实施计划：借贷不平衡诊断与报表行次覆盖治理

## 任务总览

- [x] 1. 定义统一诊断 DTO
  - [x] 1.1 后端新增 `BalanceDiagnosticsResult`、`DiagnosticCause`、`DiagnosticJumpTarget`
  - [x] 1.2 前端新增对应 TypeScript 类型
  - [x] 1.3 明确 `caliber` 枚举与中文展示文案
  - [x] 1.4 增加 DTO fixture，确保前后端字段一致
  - [x] 1.5 为每个 `caliber` 定义数据源、公式和 top_contributors 来源
  - [x] 1.6 `DiagnosticJumpTarget` 增加 transport 字段，明确 route query / dialog prop / event payload
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 6.5_

- [x] 2. 新增 `BalanceDiagnosticsService`
  - [x] 2.1 将 `validator.py` 的 `BALANCE_UNBALANCED` / `BALANCE_LEDGER_MISMATCH` findings 转为诊断 DTO
  - [x] 2.2 将 `DataQualityService` 检查结果转为诊断 DTO
  - [x] 2.3 查询未匹配报表行次科目并输出 `Unmatched_Account`
  - [x] 2.4 查询符号异常并输出 `sign_anomalies`
  - [x] 2.5 生成 `report_line_mapping`、`sign_anomaly_review`、`ledger_penetration` 跳转目标
  - [x] 2.6 `sign_anomaly_flags` 字段缺失或未上线时 graceful degrade，不阻断其他诊断
  - [x] 2.7 测试：符号异常不可用时仍能输出未匹配科目和源数据不平原因
  - _Requirements: 1.2, 2.1, 2.2, 2.3, 2.4, 2.6_

- [x] 3. 诊断原因排序与解释
  - [x] 3.1 定义 `report_line_unmatched` 原因
  - [x] 3.2 定义 `sign_convention_anomaly` 原因
  - [x] 3.3 定义 `pnl_not_closed_or_caliber_gap` 原因
  - [x] 3.4 定义 `source_data_unbalanced` 原因
  - [x] 3.5 自动判断不足时加入 `manual_review_required`
  - [x] 3.6 为 `ledger_debit_credit`、`balance_vs_ledger`、`trial_balance_debit_credit`、`balance_sheet_equation` 分别定义 top_contributors 结构
  - [x] 3.7 测试：原因按 severity 和 confidence 排序
  - _Requirements: 2.1, 2.5, 2.7_

- [x] 4. DataQualityService 口径统一
  - [x] 4.1 拆分 `ledger_debit_credit_balance` 与 `trial_balance_debit_credit`
  - [x] 4.2 明确 `report_balance` 只表示资产负债表生成后的 BS 勾稽
  - [x] 4.3 `debit_credit_balance` 兼容旧入口，但内部映射到新口径并提示口径
  - [x] 4.4 返回 details 可转换为 `BalanceDiagnosticsResult`
  - [x] 4.5 测试：损益未结转时不使用 "资产=负债+权益" 作为通用试算平衡
  - [x] 4.6 测试：每个 caliber 的数据源和公式输出与设计一致
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 5. 前端统一诊断弹窗
  - [ ] 5.1 新增 `BalanceDiagnosticsDialog.vue`
  - [ ] 5.2 展示差额、口径、原因、样本、修复入口
  - [ ] 5.3 `DiagnosticPanel.vue` 对平衡类 finding 打开统一弹窗
  - [ ] 5.4 `DataQualityDialog.vue` 对借贷平衡检查打开统一弹窗
  - [ ] 5.5 `TrialBalance.vue` 数据质量检查入口接入统一弹窗
  - [ ] 5.6 Vitest：报表行次未匹配只跳 ReportLineMapping，不跳 ColumnMappingEditor
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 6. Report_Line_Mapping 跳转闭环
  - [ ] 6.1 `ReportLineMappingDialog` 支持接收 `account_code` / `standard_account_code` 定位参数
  - [ ] 6.2 未匹配科目高亮并展示金额和未匹配原因
  - [ ] 6.3 用户修复后可重新运行诊断
  - [ ] 6.4 区分 seed 缺失、项目映射未确认、手工映射错误
  - [ ] 6.5 明确跳转采用 dialog prop / route query / event payload 的具体参数
  - [ ] 6.6 测试：诊断跳转后定位到指定科目
  - _Requirements: 6.1, 6.2, 6.4, 6.5_

- [ ] 7. Seed 覆盖率脚本
  - [ ] 7.1 新增 `check_account_to_report_line_seed_coverage.py`
  - [ ] 7.2 校验四套 Seed_Dimension 均存在且各自完整
  - [ ] 7.3 校验 `standard_account_code` 重复、`report_line_code` 格式、`report_type` 合法性
  - [ ] 7.4 以平台标准 AccountChart seed / CAS 标准科目库为权威全集输出未覆盖科目清单
  - [ ] 7.5 输出国企/上市、单体/合并差异清单
  - [ ] 7.6 报表模板行次只用于校验 `report_line_code` 存在性，不用于反推科目全集
  - [ ] 7.7 生成 coverage baseline，CI 初期只阻断新增缺口
  - [ ] 7.8 测试：脚本能发现缺失、重复和非法行次
  - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7_

- [ ] 8. 一键预设未匹配治理
  - [ ] 8.1 `ai_suggest_mappings` 或一键预设流程返回 `unmatched_accounts`
  - [ ] 8.2 有余额但 seed 查不到行次时不静默跳过
  - [ ] 8.3 seed 升级刷新仅覆盖未确认 `ai_suggested`，保护 manual / reference_copied
  - [ ] 8.4 测试：长期负债、权益细分、损益类缺失时进入未匹配清单
  - _Requirements: 5.4, 6.3_

## P0-MVP

- [ ] MVP-1. 后端能返回统一 `BalanceDiagnosticsResult`
- [ ] MVP-2. DataQualityService 的借贷平衡检查标明口径
- [ ] MVP-3. 未匹配报表行次科目进入诊断清单
- [ ] MVP-4. 前端诊断弹窗可跳转 ReportLineMapping
- [ ] MVP-5. seed 覆盖率脚本输出四套维度报告
- [ ] MVP-6. 每个 caliber 的数据源、公式和 top_contributors 明确可测
- [ ] MVP-7. seed 覆盖率以标准科目全集为输入，并有 baseline

## 验收与回归

- [ ] CI-1 pytest：诊断 DTO 与原因分类通过
- [ ] CI-2 pytest：DataQualityService 新口径通过
- [ ] CI-3 pytest：seed 覆盖率脚本通过
- [ ] CI-4 pytest：一键预设返回 unmatched_accounts
- [ ] CI-5 Vitest：BalanceDiagnosticsDialog 展示与跳转通过
- [ ] CI-6 手工 UAT：借贷不平衡时能看到原因排序和修复入口
- [ ] CI-7 回归：原 DiagnosticPanel 和 DataQualityDialog 仍可打开旧 findings
- [ ] CI-8 pytest：`sign_anomaly_flags` 未上线时诊断 graceful degrade
- [ ] CI-9 pytest：top_contributors 四种 caliber 结构通过
