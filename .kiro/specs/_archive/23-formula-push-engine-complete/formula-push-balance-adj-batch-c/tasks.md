# 任务：公式推送批 C — 资产负债类审定表族

> 顺序即依赖。每项完成须有证据。

## 阶段 1：族 binding + K2 canary

- [x] 1. `AdjudicationSpec` 数据类 + `BalanceAdjudicationBinding` 实现
  - `backend/app/services/formula_push/bindings/balance_adj.py`
  - 通过 `PushBinding` 协议校验；与 K1 binding 共用 `_row_audited` 模式
  - 证据：`test_formula_push_k2_balance_adj_integration.py` 12/12 全绿
  - _需求：C1_

- [x] 2. K2 规格声明 + 规则
  - 现读 `k_cycle_specs.K_CYCLE_SPECS['K2']` 确认 account_codes=("1901",)
  - 规则 K2.audited_total.receivable + K2.audited_total.net 写入 rules.json
  - 注册表 K2 从 NoteDirectBinding 切到 BalanceAdjudicationBinding
  - _需求：C2_

- [x] 3. K2 canary SQLite 真 ORM
  - 造 K2 底稿 + 动态行条目 → 推送 → 审定合计 2 键写入（has_provision=False）→ 幂等 → 空行=0 → 冻结跳过 → formula 锚点兼容
  - _需求：C4_

- [x]* 4. K2 canary 真 PG 试跑
  - _需求：C4_

## 阶段 2：K 循环铺开

- [x] 5. K3/K5/K7 负债方向验证 + 规格声明
  - K3 固定行 nature r0~r3 / K5 固定行 r0~r5 / K7 动态行，全部 is_liability=True
  - 证据：`test_formula_push_batch_c_k_cycle.py` 17/17 全绿
  - _需求：C6_

- [x] 6. K4 无科目处理
  - has_account=False，account_codes=("2261",)（formula 规则需要），固定行 r0~r4
  - _需求：C7_

- [x] 7. K6 资产+负债两侧 + 独占键更新
  - 双区块 sections=(("asset",r0~r6),("liab",r0~r4))，derived 键 K6-1-audited-asset / K6-1-audited-liab
  - _需求：C8_

## 阶段 3：G/H/I/J 循环铺开

- [x] 8. G1~G10 逐科目现读 + 规格声明 + 规则
  - G1~G6/G8~G9 + G10（负债类），G7 暂不入批 C（长期股权投资结构太复杂）
  - 9 个科目全部 dynamic_rows=True（无条目时合计=0 正确）
  - _需求：C2_

- [x] 9. H1~H10 逐科目 + Tier A 接管
  - H1~H10 全 10 个科目接入；H5~H10 从 Tier A 迁移（注册表+测试基线同步更新）
  - H9 is_liability=True（租赁负债 2802）
  - Tier A 从 18 码缩到 7 码（D1~D7 + I6）
  - _需求：C5_

- [x] 10. I1~I5 + J1~J2
  - I1~I5 全 5 个科目接入（从 Tier A 迁移）；J1/J2 保留 NoteDirectBinding（无审定表）
  - _需求：C2_

## 阶段 4：明细表→审定表联动

- [-]* 11. 明细表汇总推送到审定表
  - 明细表 `{code}-2` 的户级汇总（按组合分类聚合）→ 审定表 `{code}-1` 的组合行
  - 链路：明细表保存 → `WORKPAPER_SAVED` 事件 → 推送引擎 → editable 目标写入审定表
  - 覆盖 K 循环（K1-2→K1-1 已有前端 `syncUnadjFromK12`）、D 循环、G/H/I 循环
  - 🔴 当前「从 K1-2 同步」是前端按钮触发，不是自动联动；推送接管后可改为事件驱动
  - 🔴 外部依赖：改事件驱动需大改 triggers.py 的分册→主册映射+明细汇总逻辑，超出批 C 范围
  - _需求：C13_

- [x] 12. 调整分录汇总 `{code}-4` 联动
  - K2 新增 `K2.hall_adj.ending` 规则：`ADJ('1901','aje_net')` → `K2-1-hall-adj-ending`（policy=system）
  - `load_sources` 已加载 `hall_adj`（`load_hall_adjustments`，与 E1 同口径 ADR-PUSH-001）
  - 证据：`test_k2_hall_adj_ending_is_pushed` + `test_k2_hall_adj_idempotent` 全绿
  - _需求：C14_

## 阶段 5：报表联动 + stale 清除

- [-] 11. 全套回归 + 双侧夹具 + 独占键 + 清册
  - _需求：C3, C8_

- [-] 12. 推送完成后报表标 stale + 触发重算
  - 引擎写入审定合计后，检查受影响的报表行（通过 `address_registry_v2` 的依赖图或直接按科目码映射报表行）
  - 将对应 `financial_report` 行标 `is_stale=True`
  - 可选：同步触发 `report_engine.recalculate_stale` 或只标记、由下一次报表打开时重算
  - 测试：推送写入 K2 审定合计 → 报表 BS-014 行 `is_stale=True`；重算后值 = 推送值
  - _需求：C9_

- [-] 13. 报表公式求值与推送审定合计逐值对拍
  - 报表 `ReportFormulaParser.resolve_tb('1901','期末余额')` == 推送写入的 K2 审定合计
  - 覆盖全部批 C 科目（参数化）
  - _需求：C10_

- [-] 14. `is_stale` 清除链路验证
  - 现有 `financial_report.is_stale` 只标不清（`report_engine` 无清除路径）
  - 本批须新增清除路径：`recalculate_stale_rows` 函数在报表重算成功后清除 `is_stale`
  - 测试：标 stale → 重算 → `is_stale=False` ∧ `current_period_amount` = 新值
  - _需求：C11_

- [-] 15. 试算表 `audited_amount` 回写一致性
  - 审定表「发布到试算表」写 `trial_balance.audited_amount`，推送引擎从同一字段取值
  - 验证不存在双写竞争：推送取数读 TB → 审定表发布门写 TB → 推送再取数（CAS 版本检测）
  - _需求：C12_
