# ADR-CONSOL-203: 自动抵销只产 draft，审批后才进合并数

## 状态
已接受 (2026-05-30)

## 背景

`auto_generate_eliminations` 端点（consolidation.py）+ `consol_elimination_rules.calculate_elimination_amount`（4 类规则：internal_ar / internal_revenue / internal_inventory_unrealized / internal_dividend）已存在但**未接通**——端点调的是 internal_trade_service 的预览 dict 逻辑，4 规则引擎是孤儿。大集团内部交易上百笔纯手工不现实（B3）。

## 决策

- 新建 `consol_auto_elimination_service.auto_generate_draft_eliminations(db, project_id, year)`，接通 4 类规则引擎，从子公司内部交易/往来自动生成 `EliminationEntry`。
- **强制 review_status=draft**（属性 S3），本服务不触发任何重算（不 import/call recalculate_trial）。
- 无匹配内部交易数据的规则返回 0，跳过不生成、不报错（EH4）。
- 端点 `POST /api/consolidation/eliminations/auto-generate` 改调新服务，返回序列化草稿清单。
- 审批（→APPROVED）后经 Phase 1 `ELIMINATION_APPROVED` 事件触发 worksheet+trial 重算才进合并数（4.4，依赖 Phase 1；当前 mitigation：recalculate_trial 已过滤 review_status==approved，审批后下次重算自动纳入）。

## 为什么不自动 APPROVED

自动生成可能算错（规则覆盖不全/数据不准），未经复核进合并数违审计流程；draft + 人工审批是会计审慎原则。

## 后果

- 正向：自动化省人力 + 人工把关防错。
- 代价：仍需审批步骤（但比纯手工录入高效）；4.4 完整事件链依赖 Phase 1。
- 守门：S3 由 `test_consol_phase2_auto_elim_pbt.py`（10 测试）验证所有生成 entry 均 draft + 不调重算 + EH4。

## 附带修复（根因）

接通过程中发现 `ReviewStatusEnum` 成员实为小写（draft/approved/...），但 `consol_trial_service.py` 与 `elimination_service.py` 引用大写 `.APPROVED/.DRAFT`（运行时 AttributeError，潜伏 bug，cascade trial 步会触发）。已统一改为小写；并修复 `elimination_service.create_entry` 未设 id/entry_group_id/account_code/lines 的 NOT NULL 缺陷，解除 `test_elimination.py` 5 个 xfail（现真实通过）。
