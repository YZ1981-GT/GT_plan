# 任务清单：consol-phase1-arch-lock（合并模块 Phase 1 架构修复 + 锁定闭环）

> 关联设计：#[[file:.kiro/specs/consol-phase1-arch-lock/design.md]]
> 关联需求：#[[file:.kiro/specs/consol-phase1-arch-lock/requirements.md]]
> 前置：consol-phase0-core-pipeline 完成（consol_lock 三层一致 + B1 trial 已通）。~2 人天。
> 任务约定：`[ ]` 未开始 / `[x]` 完成 / `[ ]*` 可选。铁律：彻底解决不绕开 / 金额 Decimal / 改动后必 Playwright 实测 / 触类旁通 grep。

---

## 阶段 0：基线核实（动手前实证）

- [x] 0. 实证基线
  - [x] 0.1 readCode `report_engine` 公式求值入口 + 支持的函数集（TB/SUM/ABS/IF/比较），作为统一目标
  - [x] 0.2 readCode `consol_report_service._execute_formula`（裸 eval line 253）+ `_resolve_consol_tb`/`_resolve_sum_consol`/`_extract_account_codes` 取数口径
  - [x] 0.3 diff 两侧支持的公式函数集，确认合并是否有 report_engine 缺的独有 token（关联 R2，缺则先补 report_engine）
  - [x] 0.4 grep `consol_report_service` 调用方 + 单体报表既有测试清单（A1 回归基线，关联 R1）
  - [x] 0.5 readCode `consol_worksheet_engine._get_elimination_map`（确认仅 is_deleted 过滤无 review_status）+ trial 的 APPROVED 过滤，确认衔接2 口径差异
  - [x] 0.6 grep 全部子公司维度写端点（working_paper/disclosure/ledger/report 的 POST/PUT/DELETE），列 P3 锁定覆盖清单 + 标注哪些端点无 project_id 需反查
  - _需求：全部（基线）_ _铁律：彻底解决不绕开（先实证）/ 触类旁通 grep_

---

## 阶段 1：A1/A2 公式引擎统一

> 📌 P2 部分先行（2026-05-31）：`consol_report_service._execute_formula` 的**裸 eval 已替换为复用 `report_engine._safe_eval_expr`**（ast 安全求值，支持 ABS/IF/ROUND/MAX/MIN/比较）——A1 的"安全+语义不一致"硬伤已消除（7 测试 test_consol_report_formula_eval 守护）。**剩余**：完整 AmountResolver 注入抽象 + 删除 `_resolve_consol_tb`/`_resolve_sum_consol` 重复取数逻辑（任务 1/2 的架构重构部分仍待做）。

- [x] 1. AmountResolver 抽象 + report_engine 注入
  - [x] 1.1 新建 `AmountResolver` Protocol（`resolve_tb` / `resolve_sum`）+ `TrialBalanceResolver`（读 trial_balance.audited_amount）+ `ConsolTrialResolver`（读 consol_trial.consol_amount）
  - [x] 1.2 `report_engine` 公式求值入口改造为接受 `resolver` 注入（`evaluate_formula(formula, *, resolver, year, is_prior)`），取数走 resolver
  - [x] 1.3 单体报表生成改为注入 `TrialBalanceResolver`（行为须与改造前逐位一致，跑 0.4 回归基线）
  - _需求：1.1·1.2·1.6·1.7_ _属性：Q1/Q2/Q6_ _铁律：金额 Decimal / 彻底解决不绕开_

- [x] 2. 合并报表复用 + 删除重复
  - [x] 2.1 `consol_report_service.generate_consol_reports` 改调 `report_engine.evaluate_formula(resolver=ConsolTrialResolver(...))`
  - [x] 2.2 注入版跑通合并用例后，删除 `_execute_formula`/`_resolve_consol_tb`/`_resolve_sum_consol`/`_extract_account_codes`（先跑通再删，关联 R6）
  - [x] 2.3 若 0.3 发现合并独有 token，先在 report_engine 补齐再删（不丢功能，关联 R2）
  - _需求：1.3·1.4·1.5_ _属性：Q1/Q2_ _铁律：彻底解决不绕开（删裸 eval）_

---

## 阶段 2：衔接2 抵销口径统一

- [x] 3. worksheet 抵销过滤对齐 APPROVED
  - [x] 3.1 `consol_worksheet_engine._get_elimination_map` where 加 `review_status == ReviewStatusEnum.APPROVED`
  - [x] 3.2 标注口径变更 + 通知用户（draft 不再进合并数，关联 R3）
  - _需求：2.1·2.2·2.6_ _属性：Q3_

- [x] 4. 抵销审批事件驱动重算
  - [x] 4.1 `EventType` 增补 `ELIMINATION_APPROVED`（若枚举未含）
  - [x] 4.2 抵销审批端点（→APPROVED）发 `ELIMINATION_APPROVED` 事件（含 project_id/year）
  - [x] 4.3 EventBus handler 订阅 → 触发 `recalc_full(worksheet)` + `recalculate_trial`（幂等）
  - [x] 4.4 重算失败记 error 不阻断审批（审批已落库，关联 EH3）
  - _需求：2.3·2.4·2.5_ _属性：Q4_

---

## 阶段 3：F2 锁定全端点覆盖

- [x] 5. check_consol_lock 全端点装配
  - [x] 5.1 依据 0.6 清单，给底稿/附注/序时账/报表全部子公司写端点挂 `Depends(check_consol_lock)`
  - [x] 5.2 端点仅含资源 id（wp_id/note_id）无 project_id 时，在 check_consol_lock 内反查所属 project_id 再判锁
  - [x] 5.3 反查失败放行不误拦 + warning（关联 EH4）
  - _需求：3.1~3.5_ _属性：Q5_ _铁律：触类旁通 grep（全端点覆盖）_

---

## 阶段 4：F4 前端锁定 banner + 423 拦截

- [x] 6. ConsolLockedBanner + 423 拦截
  - [x] 6.1 新建 `components/common/ConsolLockedBanner.vue`（仿 ArchivedBanner，无 props 内部读锁定态，consol_lock=true 显示橙色横幅 + 编辑按钮 disabled）
  - [x] 6.2 合并相关子公司视图挂 `<ConsolLockedBanner />`（grep 子公司编辑视图逐一接入）
  - [x] 6.3 http 拦截器统一处理 423 → ElMessage「项目已被合并锁定，无法修改」+ 刷新锁定态
  - _需求：4.1~4.3_ _铁律：UI 全中文化 / 改动后必 Playwright 实测_

---

## 阶段 4B：会计正确性修正（B6/B7/A3）

> 注：6A/6B/6C 是本阶段三个**独立任务**（非任务 6 的子任务），编号续接 6 以避免与阶段 5 起始的任务 7 冲突；实施互不依赖，6C 建议搭车阶段 1 的 A1/A2 重构。

- [-] 6A. 负商誉 CAS 20 修正（B6）
  - [x] 6A.1 readCode `goodwill_service.calculate_goodwill` 负商誉分支，确认 `25% 阈值 + 递延收益摊销` 编造逻辑
  - [x] 6A.2 删除 25% 阈值分支，负商誉统一"计入当期损益（营业外收入）"+ 提示审计师复核计量；商誉公式本身不变
  - [ ] 6A.3* `[ ]* 待审计专业确认`：懂 CAS 20 的审计专业人员复核准则符合性后方可标完成（关联 R7）
  - _需求：5.1~5.5_ _铁律：彻底解决不绕开 / 会计正确性归审计专业_

- [-] 6B. 少数股东比例语义统一（B7）
  - [x] 6B.1 grep `minority_share_ratio` 全部用法，确认 calculate_mi（直接用）vs consol_disclosure_service（求补数）口径冲突
  - [x] 6B.2 修 `consol_disclosure_service` 的 `(1 - ratio) * 100` → 直接用少数股东比例
  - [x] 6B.3 加单测锁口径：母 80%/子 20% → 附注少数股东持股比例 == 20%（关联 Q7）
  - [ ] 6B.4* `[ ]* 待审计专业确认` 字段语义最终口径（关联 R7）
  - _需求：6.1~6.4_ _属性：Q7_

- [x] 6C. consol_report_service sync/async 统一（A3，搭车 A1/A2）
  - [x] 6C.1 grep `self.db.query` in consol_report_service + `*_sync` 包装及其调用方
  - [x] 6C.2 同步 query → async `await self.db.execute(select(...))`；`*_sync` 用 `run_sync` 桥接
  - [x] 6C.3 与任务 1/2（A1/A2 重构 consol_report_service）合并改完，避免二次触碰（关联 R8）
  - _需求：7.1~7.4_ _铁律：彻底解决不绕开 / 改动后必验_

---

## 阶段 5：测试（PBT + 集成 + Playwright）

- [x] 7. PBT（hypothesis）
  - [x] 7.1 Q1 公式语义一致：同一 formula 注入两 resolver → 解析+求值路径相同仅取数值不同
  - [x] 7.2 Q2 求值安全：随机非法/注入表达式 → 返回 0 不抛、不执行 eval
  - [x] 7.3 Q3 抵销口径一致：随机抵销集（含 draft/APPROVED 混合）→ worksheet 与 trial 消费集合相同（均 APPROVED）
  - [x] 7.4 Q4 审批重算幂等：同笔抵销重复触发 → 结果不变
  - [x] 7.5 Q6 Decimal：AmountResolver + 抵销聚合全程 Decimal 逐位相等
  - [x] 7.6 Q7 少数股东比例语义：随机母/子持股比例 → 附注少数股东比例 == 子比例（不求补数）
  - _需求：1/2/6_ _属性：Q1~Q4·Q6·Q7_ _铁律：hypothesis 调速 10~15_

- [x] 8. 集成测试 + 单体回归
  - [x] 8.1 A1 单体报表全量回归基线全绿（复用引擎不破坏单体，关联 R1）
  - [x] 8.2 Q5 锁定全端点 423 参数化（遍历底稿/附注/序时账/报表写端点）
  - [x] 8.3 抵销审批 → 事件 → worksheet+trial 重算端到端
  - [x] 8.4 PG-only SQL 在 SQLite 加 dialect 兜底
  - _需求：1.6/2.3/3.3_ _铁律：任务标记不能假绿_

- [ ] 9. Playwright 锁定闭环实测（F2/F4）
  - [x] 9.1 后端锁 → 前端点 → 真改子公司被拦 423 → ConsolLockedBanner + ElMessage 显示（关联 R1）
  - _需求：4.4_ _铁律：改动后必 Playwright 实测_

- [ ] 10.* 真实数据 UAT（外部依赖，待数据）
  - [ ] 10.1* 真实合并母子项目验证合并报表公式语义一致 + 锁定全覆盖；显式标"待数据"不伪绿
  - _需求：NFR-1.3_ _阻塞：PG consolidated 项目 0_

---

## 阶段 6：收尾

- [-] 11. 文档与沉淀
  - [x] 11.1 ADR-CONSOL-101/102/103 落地 `docs/adr/`（注册前查编号防冲突）
  - [x] 11.2 抵销口径变更（draft 不进合并数）写入 conventions + 通知用户
  - [x] 11.3 更新 INDEX.md + memory Phase 1 完成记录
  - [ ] 11.4 单 commit（commit 前 git status 确认无其他 staged）
  - _铁律：单 commit / ADR 编号防冲突 / 历史档案不回填_

---

## 完成度判定口径

- **必需完成** = 任务 0~9 + 6A.2/6B/6C + 11（无星号）全绿。
- **可选/外部** = 任务 10（真实 UAT，卡 PG 合并数据）+ 6A.3/6B.4（B6/B7 待审计专业确认准则口径）。
- **判定铁律**：A1 单体回归全绿（不破坏既有）+ Q1~Q7 全绿 + 锁定全端点 423 参数化通过 + Playwright 锁定闭环实测；**B6 负商誉 + B7 少数股东比例修代码可做，但准则符合性最终判定须懂 CAS 20 的审计专业人员复核（标 `[ ]*`）**；标 completed 必须有代码+测试证据，真实 UAT 标"待数据"不伪绿。
- **范围外显式声明（proposal 对应项归属）**：B8 同一控制企业合并（独立大模块，不在本批 4 Phase）/ B4 MI·商誉 verify_balance 口径（待审计专业）/ B5 跨年上年数结转（Phase 4）。
