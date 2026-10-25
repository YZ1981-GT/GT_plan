# 任务：公式推送附注铺开 · 批 C

> 顺序即依赖。每项完成须有证据。动手改文件前先 `git status` 核对。

## 阶段 1：现读确认

- [x] 1. 现读附注模板，确认 10 个目标科目在 soe/listed 两版的章节编号和主表名
  - 用探针脚本现读 `note_template_soe.json` 和 `note_template_listed.json`
  - 逐科目确认：上市编号、国企编号、主表名（第一张表 name）、主表列 keys、主表行数
  - 结果回填 design §3 映射表
  - 验证多科目共享章节的行标签不冲突

## 阶段 2：Tier A 附注能力

- [x] 2. `TierAAnchorBinding` 加 `note_rows()` 实现
  - 从 `TierASources.formula` 取 TB 审定数构建附注行
  - 支持单科目和多科目（I1 的三码差额）
  - 损益类用 `'本期发生额'` 取数（H10/I6）
  - 测试：单科目 H5 → 一行 + 不生合计；多科目 I1 → 三行 + 合计行

- [x] 3. K1 附注推送能力（`K1Binding.note_rows()` 实现）
  - 从 `k1_calc` 取审定合计的期末和期初值
  - 输出单行：label="其他应收款"，ending=audited_receivable-audited_baddebt（净值），opening=同口径上期
  - 测试：K1 note_rows 输出行标签正确、值等于 k1_calc 结果

## 阶段 3：规则与集成

- [x] 4. 在 `formula_push_rules.json` 中追加 10 条附注规则
  - 每科目一条：rule_id 格式 `{CODE}.note.main`
  - `section_by_template` 填 Task 1 确认的章节编号
  - `table` 填 Task 1 确认的主表名
  - 规则清单校验通过

- [x] 5. 独占键生成器重生成 + 回归
  - `--check` 确认附注规则不影响独占集合
  - 清册重生成，`has_note_rules` 更新
  - 全套推送测试 ≥250 passed

## 阶段 4：集成测试

- [x] 6. 每个科目的 SQLite 真 ORM 附注推送测试
  - 沿用 `_formula_push_env.py` 夹具
  - 每科目一个参数化用例：推送后附注表 `end_amount`/`prior_amount` 值等于 TB 取数
  - 共享章节（五、34 = H9+I6）测试两个底稿各写各的行
  - 损益类（H10/I6）测试取数口径是发生额不是余额

- [x] 7. 回归归因
  - 推送测试 287 passed ≥250（152 red 全为 batch D 的 K4 binding 空 account_prefixes，非本批回归）
  - INDEX.md 已插行 `formula-push-note-rollout-batch-c` → 7/7 ✅
  - 探针 `_batch_c_note_probe.py` 已删

## 复盘修复（2026-10-06）

- P0：I3 规则 `table` 从 `"商誉账面原值"` 改为 `"商誉"`（章节标题），新增 `table_by_template` 区分 listed/soe 子表名
- P2：集成测试 mock 从 TierAAnchorBinding 改为 load_tb_audited（I3 已迁移至 BalanceAdjBinding）；新增 soe 版 I3 测试
- P3：原文案 "10 条附注规则" 实际交付 2 条（Task 1 探针校正后范围 10→2）
