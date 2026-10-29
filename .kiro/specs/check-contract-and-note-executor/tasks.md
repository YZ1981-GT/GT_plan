# 实施计划：S2　校对契约与附注执行器（check-contract-and-note-executor）

> 以 design.md 为准，需求编号 R1~R6 见 design 页头。启动条件见 design §4 D4：R1、R2、R4、R6（任务 1~4）可先做；R3、R5（任务 5~6）与母 spec X4 同批。
> 通用纪律：临时产物放仓库根 `tmp_check_contract/`；迁移号实施时三路合扫；真 PG 写入只在回滚事务内的【测试】项目；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库（门禁五态、`gate_decision`、`_branches`）；任务 6 的审计写入依赖 S10 批 B（未完成时用现行 `append_audit_log`，并在任务记录注明）。

- [ ] 0. 现状复核
  - 重算 design §1 八行（执行器分流与回写条件、真库附注公式数据、目录来源与结果落库表、XR 签字判据、cross_check 定义字段、enforce 出口、门禁规则吞异常 AST 计数），变化追加到 design §1 末尾
  - Verify: 探针输出存 `tmp_check_contract/baseline/`

- [ ] 1. 校对结果五态契约（ADR-CCN-01）
  - 新建 `backend/app/services/check_outcome.py`；AST 守卫（`passed(` 不得在 `except` 内）
  - Verify: 单元用例；守卫带违规样本自检

- [ ] 2. 附注执行器按类别分流（R1，ADR-CCN-02，design §4 D3）
  - `note_formula_generator.execute_note_formulas`：分流、回写条件、`last_value`、`Decimal` 量化、返回 `checks[]`；附注页问题清单接 `checks`
  - Verify: 三类别夹具 + 手工格不覆盖 + 上次写入可覆盖；vitest（问题清单显示）；回滚事务 PG（【测试】附注一节，执行后手工格值不变）。变异：去掉类别分流 ⇒ logic_check 用例红；去掉手工格判断 ⇒ 不覆盖用例红

- [ ] 3. 校对目录执行状态（R2，ADR-CCN-03）
  - `formula_check_catalog.py` 来源登记增执行器入口；响应增 `execution` 与（带项目时）`last_run`；覆盖度只计 `wired`；前端目录页显示状态列
  - Verify: `wired` 入口真实存在且有生产调用的守卫；端点用例（带 / 不带项目）；vitest。变异：把一类来源错标 `wired` 而入口不存在 ⇒ 守卫红

- [ ] 4. 表间审核严重度与门禁规则异常收口（R4、R6，ADR-CCN-05/07）
  - `cross_check` 域 `severity`（缺省 warning）与界面「提示」显示；报表审核汇总按严重度计数；`GateRule.not_executed` / `not_applicable` 基类方法；27 处处理器逐个改写；`consistency_replay_engine` 空层改 `not_executed`
  - Verify: 27 处参数化用例；AST 守卫（`check()` 内捕获 `Exception` 不得 `return None`）；表间审核 warning 不计入失败的用例。变异：任一规则恢复 `return None` ⇒ 守卫红

- [x] 5. XR 进签字判据（R3，ADR-CCN-04）
  - `CrossCheckPassedRule` 年度改单一来源、结果转五态、经 `gate_decision(consumer="cross_check_rule")`；XR-05 改 `SUM_TB`；XR-08 标 `not_executable`
  - Verify: 转换表单元用例；observe / enforce 各一组端点用例（`GET /api/projects/{pid}/sign-readiness`）；回滚事务 PG（缺底稿数据时出现 warning）。变异：`skip` 改回放行 ⇒ 签字用例红

- [x] 6. enforce 下逐项确认留痕（R5，ADR-CCN-06，design §4 D1、D2）
  - 迁移 `V{n}` / `R{n}`；ORM 与三层一致；端点（列表 / 确认 / 撤销）与审计写入；`gate_decision` 按确认与指纹移出阻断集合；`ConsistencyGatePanel` 确认 / 撤销
  - Verify: 权限配方表；指纹失效用例；observe 下 409；回滚事务 PG（enforce 下确认后放行、改数据后重新阻断）；vitest。变异：`gate_decision` 不看指纹 ⇒ 失效用例红

- [ ] 7. 回归、浏览器实测与收尾
  - 候选树 vs 基线 HEAD 失败集合对比；浏览器（chrome-devtools，【测试】项目）：附注执行公式后手工格不变、问题清单有校对结果；目录页状态列；门禁面板 enforce 下确认流程（在本地以 `CONSISTENCY_GATE_ENFORCEMENT=enforce` 起一套指向回滚夹具的环境时做，做不到则标 `[ ]*` 写明原因）；截图放 `tmp_check_contract/screenshots/`，用完停 about:blank
  - INDEX.md 本行与 memory.md 任务状态
  - Verify: 只候选红 = 0；推送带版本号与主要变动
