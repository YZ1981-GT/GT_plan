# 实施计划：账表导入符号约定与历史迁移

## 任务总览

- [x] 1. 定义符号与方向契约
  - [x] 1.1 后端新增 `DirectionSource`、`SignConventionVersion`、`SignAnomaly` 类型
  - [x] 1.2 前端新增对应 TypeScript 类型
  - [x] 1.3 定义 `v1_net_debit_positive` 符号约定常量
  - [x] 1.4 增加前后端枚举一致性 fixture
  - [x] 1.5 增加 `account_category_inferred_low_confidence` 与迁移安全等级枚举
  - _Requirements: 1.1, 1.3, 2.2_

- [x] 2. 数据库字段与迁移
  - [x] 2.1 为 `tb_balance` / `tb_aux_balance` 增加期初/期末方向、方向来源、符号版本和异常 JSONB 字段
  - [x] 2.2 为 `tb_ledger` / `tb_aux_ledger` 增加发生方向和来源字段
  - [x] 2.3 新增独立方向覆盖 overlay 表，记录原始方向、覆盖方向、原因、覆盖人和时间
  - [x] 2.4 编写配对 `V0XX__*.sql` / `R0XX__*.sql`，DDL 使用 `IF NOT EXISTS`
  - [x] 2.5 测试：迁移幂等、字段可空、旧数据可读
  - [x] 2.6 测试：用户覆盖不改写原始四表导入行
  - _Requirements: 2.1, 3.3, 5.3, 6.6_

- [x] 3. Converter 结果结构改造
  - [x] 3.1 定义 `BalanceConversionResult` / `LedgerConversionResult`
  - [x] 3.2 `convert_balance_rows` 输出 rows、aux rows、warnings、sign anomalies、stats
  - [x] 3.3 保留兼容 wrapper，避免一次性破坏旧测试
  - [x] 3.4 pipeline 消费新结果并合并 warnings
  - [x] 3.5 writer 持久化方向字段和异常字段
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 4. 方向推导规则
  - [ ] 4.1 显式方向列：按借/贷/D/C/debit/credit 调符号
  - [ ] 4.2 借贷分列：按借方列减贷方列计算净额并记录 `split_columns`
  - [ ] 4.3 借贷两方同时非零：按净额判定方向并记录 warning
  - [ ] 4.4 单一净额列：按 Account_Category / Contra_Asset 推断
  - [ ] 4.5 metadata 缺失时标记 `unknown`，不强行猜测
  - [ ] 4.6 测试：负债贷方余额存负、资产借方余额存正、资产备抵为贷方
  - [ ] 4.7 源分列字段保持绝对值，仅净额字段带符号
  - [ ] 4.8 科目编码前缀低置信推断只用于提示，不用于自动迁移改写
  - _Requirements: 1.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [ ] 5. 符号异常与复核
  - [ ] 5.1 识别与 Account_Category 正常方向冲突的余额
  - [ ] 5.2 识别借贷并存、资产备抵反向、负债权益收入借方净额
  - [ ] 5.3 将异常写入 `sign_anomaly_flags`
  - [ ] 5.4 提供方向异常列表 API
  - [ ] 5.5 提供用户确认/修正方向 API，记录原因和留痕
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 6. 历史数据 dry-run 与迁移
  - [ ] 6.1 编写 dry-run 脚本，输出建议改写和待复核清单
  - [ ] 6.2 dry-run 报告包含项目、dataset、科目、原金额、建议金额、原因、风险等级
  - [ ] 6.3 dry-run 输出 `safe_auto_fix`、`manual_review_required`、`no_change` 三类安全等级
  - [ ] 6.4 重复执行不改变已符合约定的数据
  - [ ] 6.5 测试：冲突项默认不改写
  - [ ] 6.6 执行脚本仅处理人工确认 allowlist 或 `safe_auto_fix` allowlist
  - [ ] 6.7 dry-run 报告输出 JSON/CSV，作为审计留痕附件保存
  - [ ] 6.8 测试：2221 等可能真实反向余额不能仅凭科目类别自动改写
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

- [ ] 7. 试算表展示去补救化
  - [ ] 7.1 后端试算表 API 返回方向、方向来源、复核状态和异常 flags
  - [ ] 7.2 `TrialBalance.vue#getDirection()` 优先使用后端权威方向
  - [ ] 7.3 移除普通科目按金额正负作为第一方向来源的逻辑
  - [ ] 7.4 本地 `directionOverrides` 改为调用后端 overlay 持久化接口
  - [ ] 7.5 历史 fallback 显示 `legacy_inferred` / "推断方向"
  - [ ] 7.6 提供方向异常列表 API 与批量确认 API
  - [ ] 7.7 Vitest：方向来源优先级和用户覆盖持久化
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

## P0-MVP

- [ ] MVP-1. 新导入余额表持久化方向与方向来源
- [ ] MVP-2. 借贷分列、显式方向、类别推断三类来源可区分
- [ ] MVP-3. 符号异常进入导入报告或异常 API
- [ ] MVP-4. 试算表优先使用后端方向字段
- [ ] MVP-5. 历史 dry-run 能输出影响清单且不改数据
- [ ] MVP-6. 用户方向覆盖通过 overlay 留痕，不改写原始导入行

## 验收与回归

- [ ] CI-1 pytest：converter 符号约定与方向来源测试通过
- [ ] CI-2 pytest：migration DDL 幂等与 dry-run 通过
- [ ] CI-3 pytest：pipeline 能写入新增方向字段
- [ ] CI-4 Vitest：TrialBalance 不再默认按金额正负猜普通科目方向
- [ ] CI-5 手工 UAT：2221/4003 等异常科目进入复核清单
- [ ] CI-6 回归：旧项目未迁移时仍可打开并显示推断方向标记
- [ ] CI-7 pytest：dry-run 安全等级与 no-change/manual-review 边界通过
