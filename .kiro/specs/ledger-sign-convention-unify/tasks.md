# 账表符号约定统一 — 实施任务

- [x] 1. 符号约定版本与方向判定模块（需求 1、2、3）
- [x] 1.1 扩展 `sign_convention_types.py`：新增 `v2_category_natural_positive` 版本，`CURRENT_SIGN_CONVENTION` 切到 v2，保留 v1 可识别
- [x] 1.2 新建 `ledger_import/direction_resolver.py`：`resolve_account_direction(code, name) -> (direction, source)`，备抵正则优先 → 复用 `_infer_category` 类别 → 编码兜底；备抵 credit（累计折旧/摊销、坏账/减值/跌价准备、折耗）+ 库存股 debit
- [x] 1.3 单元测试 `test_direction_resolver.py`：6 大类 + 备抵反向 + 名称编码冲突 + 名称缺失兜底 + 多关键词优先级
- [x]* 1.4 PBT（max_examples=5）：方向唯一性 + 备抵优先级稳定性
- [x] 1.5 用 codegraph 补全"全下游符号消费点清单"为实施 checklist：grep/codegraph 所有读 closing_balance / audited_amount / unadjusted_amount / `=TB(` / `=ADJ(` 的点，逐一登记是否需改（产出清单文档供 Task 2-6 核对）

- [ ] 2. converter 入库改造（需求 4、5）
- [ ] 2.1 `convert_balance_rows`：净额算出后调 direction_resolver，按方向存自然正数，写 opening/closing_direction + source + sign_convention_version=v2；方向与类别冲突时保留带符号值 + sign_anomaly_flags
- [ ] 2.2 `convert_ledger_rows`：分录行标 entry_direction + source，保持金额口径与幂等
- [ ] 2.3 单元测试：各类科目存储符号、方向字段、显式方向列优先、借贷分列、幂等；保持辅助维度拆分/主表去重不破坏
- [ ]* 2.4 PBT（max_examples=5）：同类符号一致 + 转换幂等

- [ ] 3. trial_balance 生成层改造（需求 9，关键。**决策定稿：方案A，不新增 direction 列，复用 account_category**）
- [ ] 3.1 `recalc_unadjusted`：移除损益类硬编码 `-total_cr`，改 direction_resolver 判方向存自然正数；资产负债类直接传递不二次处理
- [ ] 3.2 `get_summary_with_adjustments`：移除 L527-536 "取反"补偿逻辑，改按 account_category 分方向加减
- [ ] 3.3 验证 `recalc_adjustments`/`recalc_audited`：audited=unadjusted+rje+aje 在 v2 正数下加减方向正确（尤其负债类）
- [ ] 3.4 集成测试（真实 PG）：tb_balance → trial_balance 符号传递无二次翻转，全链路单一约定

- [ ] 4. 平衡校验统一（需求 6）
- [ ] 4.1 在 `sign_convention_types.py` 固化 `BALANCE_TOLERANCE = Decimal("1")` 常量，data_quality/consol/cfs 共用，替换散落硬编码
- [ ] 4.2 确认 `data_quality_service._check_debit_credit_balance` 为目标态，新约定下两类合计相等
- [ ] 4.3 盘点并对齐调整分录（adjustment_service）符号假设
- [ ] 4.4 盘点并对齐合并（consol_report_service / cfs_worksheet_engine）符号假设 + 统一容差
- [ ] 4.5 集成测试：平衡账套分录级（借方类合计=贷方类合计，差额≤容差）+ 报表级校验通过

- [ ] 5. 公式取数层与附注消费符号一致性（需求 11）
- [ ] 5.1 盘点 `data_fetch_custom` / `module_cell_resolver` / formula 预填路径对 TB 符号的处理，移除隐含旧约定的翻转
- [ ] 5.2 盘点存量 `data_fetch_custom` 的 `negate` transform 配置，识别哪些是为纠正旧约定负数而设
- [ ] 5.3 确认 `disclosure_engine` / `disclosure_trace` 读 audited_amount 时无旧约定符号假设（如有则改造）
- [ ] 5.4 集成测试：`=TB('2202','期末余额')`（应付账款）等典型公式在 v2 下预填为符合预期的正数；TB/TB_SUM/ADJ 求值符号正确

- [ ] 6. 存量数据迁移脚本（需求 7）
- [ ] 6.1 新建 `backend/scripts/migrate/migrate_sign_convention_v2.py`：按 project+year 翻转贷方类符号 + 补方向字段 + 标 v2，dry-run/幂等
- [ ] 6.2 迁移前快照（`_sign_migration_backup` 或 JSON 导出）+ 回退路径
- [ ] 6.3 无法判定记录跳过 + 待复核清单 + app_audit_log 留痕
- [ ] 6.4 迁移同步处理 5.2 识别出的 `negate` transform 配置（移除/反置 + 记入待复核）【依赖 5.2 产出】
- [ ] 6.5 集成测试：旧数据迁移后符号正确、幂等、回退、平衡通过

- [ ] 7. 过渡期语义（需求 10）
- [ ] 7.1 下游消费前按 dataset 检测 v1 残留，提示"需先运行符号迁移"（API/UI）
- [ ] 7.2 集成测试：v1/v2 混存时按版本正确解释，不误读

- [ ] 8. 端到端实测与收尾（需求 8）
- [ ] 8.1 Playwright：导入后试算表借方类合计=贷方类合计（差额≤容差）、报表资产=负债+权益、底稿取数符号正确
- [ ] 8.2 全量回归（基于 codegraph blast radius，full_recalc 11 调用方）：trial_balance / data_quality / consistency_gate / balance_diagnostics / consol / cfs / disclosure_engine / 公式预填 相关测试套件全绿，确认无回归
