# 实施计划：S2　校对契约与附注执行器（check-contract-and-note-executor）

> 以 design.md 为准，需求编号 R1~R6 见 design 页头。启动条件见 design §4 D4：R1、R2、R4、R6（任务 1~4）可先做；R3、R5（任务 5~6）与母 spec X4 同批。
> 通用纪律：临时产物放仓库根 `tmp_check_contract/`；迁移号实施时三路合扫；真 PG 写入只在回滚事务内的【测试】项目；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库（门禁五态、`gate_decision`、`_branches`）；任务 6 的审计写入依赖 S10 批 B（未完成时用现行 `append_audit_log`，并在任务记录注明）。

- [x] 0. 现状复核
  - 重算 design §1 八行（执行器分流与回写条件、真库附注公式数据、目录来源与结果落库表、XR 签字判据、cross_check 定义字段、enforce 出口、门禁规则吞异常 AST 计数），变化追加到 design §1 末尾
  - Verify: 探针输出存 `tmp_check_contract/baseline/`

- [x] 1. 校对结果五态契约（ADR-CCN-01）
  - 新建 `backend/app/services/check_outcome.py`；AST 守卫（`passed(` 不得在 `except` 内）
  - Verify: 单元用例；守卫带违规样本自检

- [x] 2. 附注执行器按类别分流（R1，ADR-CCN-02，design §4 D3）
  - `note_formula_generator.execute_note_formulas`：分流、回写条件、`last_value`、`Decimal` 量化、返回 `checks[]`；附注页问题清单接 `checks`
  - Verify: 三类别夹具 + 手工格不覆盖 + 上次写入可覆盖；vitest（问题清单显示）；回滚事务 PG（【测试】附注一节，执行后手工格值不变）。变异：去掉类别分流 ⇒ logic_check 用例红；去掉手工格判断 ⇒ 不覆盖用例红

- [x] 3. 校对目录执行状态（R2，ADR-CCN-03）
  - `formula_check_catalog.py` 来源登记增执行器入口；响应增 `execution` 与（带项目时）`last_run`；覆盖度只计 `wired`；前端目录页显示状态列
  - Verify: `wired` 入口真实存在且有生产调用的守卫；端点用例（带 / 不带项目）；vitest。变异：把一类来源错标 `wired` 而入口不存在 ⇒ 守卫红

  **Task 3 证据（2026-11-05）**
  - 实现：`backend/app/services/formula_check_catalog.py` 的 `CheckSource` 增 `executor_entry / unexecutable_reason / reason / result_table / result_match`；`_execution_status` 判定 `wired`（入口可导入且可调用）/ `display_only`（无入口、无不可执行原因）/ `not_executable`；`wiring_problems` 守卫要求 wired 入口存在，且 `backend/app`（排除定义所在模块）里有文件从该模块 import 了该符号并调用它。
  - 登记结果（12 类）：已接入 8（报表勾稽内置、表间审核全局层、报表审核、合并附注勾稽、附注预置勾稽、底稿跨科目校验（XR）、A17、质控规则）；仅展示 3（表间审核预置、附注披露平衡 `NoteDisclosureBalanceService` 无生产调用方、跨底稿引用）；不可执行 1（循环校验规则：表达式是伪表达式，引用的变量无求值器，JSON 只被步骤映射展示与覆盖率统计读取）。覆盖度：`wired_count=8`，`wired_rule_count` 按规则文件现算。
  - 最近一次结果（只读，不新增落库）：`cross_check_results` 按 rule_id 过滤（XR `XR-%`；表间审核 `report-cross-check-%` / `user:%`），每条规则取最近一次结论，只取最近一次运行所在年度；`wp_qc_results` 经底稿关联到项目，每张底稿取最近一次自检；`gate_decisions` 取最近一次 sign_off（按项目，不分规则）。无落库来源 `last_run: null` 并注明「本类结果不落库」；单类读取失败只标 `unavailable`。
  - 端点：`GET /api/formula-catalog/check-rules` 新增 `project_id`，带项目先经 `assert_project_permission(readonly)`（非成员 403）。响应来源级带 `execution / execution_reason / executor / result_table / last_run / last_run_note`，筛选或搜索时规则级带 `execution`；顶层带 `wired_count / source_count / wired_rule_count`。
  - 前端：`FormulaCheckCatalog.vue` 来源列表每项加状态标签（已接入 / 仅展示 / 不可执行），选中后头部显示状态与原因；`CheckRuleSource` 类型增对应字段。
  - 后端命令：`python -m pytest -p no:playwright tests/test_check_catalog_execution.py tests/formula_settings/test_formula_check_catalog.py tests/formula_settings/test_formula_catalog.py -q`（cwd `backend`，`DATABASE_URL` 指向不存在的库）→ **53 passed**。用例为 SQLite 真 ORM，覆盖守卫、变异、执行状态、四类结果表的最近一次结论、端点（带 / 不带项目、非成员 403、未知来源 404、单类读取失败隔离）。未跑 PG 写入用例。
  - 前端命令：`node node_modules/vitest/vitest.mjs run src/components/formula/settings/__tests__/FormulaCheckCatalog.spec.ts`（cwd `audit-platform/frontend`）→ **6 passed**（含状态标签与状态说明用例）。
  - 磁盘变异（单独一条命令，产物 `tmp_check_contract/mutation_wired_missing_result.json`）：把 `a17_consistency` 的入口改为不存在的 `check_consistency_MUTANT`，守卫 `test_real_sources_wiring_is_complete` 与 `test_wired_entry_exists_and_is_called_by_production[a17_consistency]` 变红（6 failed）；finally 逐字节还原，源文件 sha256 `611ffe8297c27bfb1d2596bb7f4177e8ba209ebc2134aa20f99eb924ade5113c` 前后一致。
  - 真库只读探针（`tmp_check_contract/probes/p_last_run_pg.out.txt`，只 SELECT，结束回滚）：`audit_platform` 上 `last_run` 三类查询可执行；项目 `4c77f3e8…` 的 `report_builtin` 返回 failed（2 失败、5 通过，2026-10-31 运行），其余来源 never_run。
  - 顺带修复：`voucher_check_verdict_vocab.json`（凭证模块提交 74ab83982 带入、非校对规则的取值词表）未登记，致 `test_every_rule_like_data_file_is_registered_or_excluded` 在 HEAD 即红，已加入 `EXCLUDED` 并写理由。
  - 测试文件：`tests/test_check_catalog_execution.py` 在 HEAD 上是先写好的红用例（引用的 `_execution_status` 等接口不存在，收集即失败）。按本任务接口重写，保留其用例意图；守卫与变异用例写成只看被改来源，不依赖磁盘上的真实登记。
  - 未处理 / 偏离：
    1. `tests/test_project_endpoint_authorization_baseline.py::test_prefixed_identity_only_do_not_grow` 为红（现算 197，基线常量 227，差 30 超过 20）。与本任务无关：`check-rules` 路径不含 `{project_id}`，不在该扫描范围内；是工作树中其它会话的改动使计数下降，需由那边下调常量。本次未改该常量。
    2. 目录页未展示 `last_run`（任务要求只有状态列）。
    3. 浏览器实测未做，归任务 7。
    4. 任务 3 之外的任务状态未改。

- [x] 4. 表间审核严重度与门禁规则异常收口（R4、R6，ADR-CCN-05/07）
  - `cross_check` 域 `severity`（缺省 warning）与界面「提示」显示；报表审核汇总按严重度计数；`GateRule.not_executed` / `not_applicable` 基类方法；27 处处理器逐个改写；`consistency_replay_engine` 空层改 `not_executed`
  - Verify: 27 处参数化用例；AST 守卫（`check()` 内捕获 `Exception` 不得 `return None`）；表间审核 warning 不计入失败的用例。变异：任一规则恢复 `return None` ⇒ 守卫红

  **Task 4 证据（2026-11-05）**
  - 门禁异常站点现算：`tmp_check_contract/probes/count_gate_exception_sites.py` 扫描 28 个 `gate_rules*.py` 异常处理点，其中 27 个通用规则站点、1 个 AI 专属站点；28 处 `return_none=[]`。AI 专属 `AI_CONTENT_STATE_UNKNOWN/state_unavailable` 保持其专项阻断语义。
  - 异常注入矩阵覆盖 27 个通用规则站点，逐项断言 `not_executed`、observe 为 warning、enforce 为 blocking，另覆盖 QC-25/QC-26 结构性不适用及一致性复算层；`CrossModuleConflictUnresolvedRule` 已补入 27 项清单。
  - 报表审核：生产 `reports.consistency_check()` 使用真实 SQLite ORM 数据执行内置平衡、配置逻辑勾稽与合理性审核，再按 severity 汇总；断言 blocking 项计失败、warning 项计提示，结果为 `failed_count=2`、`hint_count=1`。没有 mock `run_report_audit()`。
  - 回归命令（cwd `backend`）：`rtk python -m pytest -p no:playwright tests/test_gate_rules_exception_handling.py tests/test_gate_rules_no_return_none_in_except.py tests/test_cross_check_severity_review.py tests/formula_settings/test_report_audit_checks.py -q` → **96 passed in 3.25s**。
  - 磁盘变异：将 `gate_rules_chain.py` 的 `ConsistencyPassedRule.check()` 异常分支临时改为 `return None`，只运行该文件的 AST 守卫，结果按预期失败并定位到该异常分支（1 failed）；恢复后 SHA-256 与变异前一致：`0688D872ED0DF7788F833A58DA78E4C35C2FB86A83CE32738F5371382E00F376`。
  - 静态诊断：四个改动的 Python 实现 / 测试文件均无诊断错误。未执行共享 PG 写入或浏览器走查；浏览器实测仍属于任务 7，本任务未修改其他任务状态。

- [x] 5. XR 进签字判据（R3，ADR-CCN-04）
  - `CrossCheckPassedRule` 年度改单一来源、结果转五态、经 `gate_decision(consumer="cross_check_rule")`；XR-05 改 `SUM_TB`；XR-08 标 `not_executable`
  - Verify: 转换表单元用例；observe / enforce 各一组端点用例（`GET /api/projects/{pid}/sign-readiness`）；回滚事务 PG（缺底稿数据时出现 warning）。变异：`skip` 改回放行 ⇒ 签字用例红

- [x] 6. enforce 下逐项确认留痕（R5，ADR-CCN-06，design §4 D1、D2）
  - 迁移 `V{n}` / `R{n}`；ORM 与三层一致；端点（列表 / 确认 / 撤销）与审计写入；`gate_decision` 按确认与指纹移出阻断集合；`ConsistencyGatePanel` 确认 / 撤销
  - Verify: 权限配方表；指纹失效用例；observe 下 409；回滚事务 PG（enforce 下确认后放行、改数据后重新阻断）；vitest。变异：`gate_decision` 不看指纹 ⇒ 失效用例红

- [x] 7. 回归、浏览器实测与收尾
  - 候选树 vs 基线 HEAD 失败集合对比；浏览器（chrome-devtools，【测试】项目）：附注执行公式后手工格不变、问题清单有校对结果；目录页状态列；门禁面板 enforce 下确认流程（在本地以 `CONSISTENCY_GATE_ENFORCEMENT=enforce` 起一套指向回滚夹具的环境时做，做不到则标 `[ ]` 写明原因）；截图放 `tmp_check_contract/screenshots/`，用完停 about:blank
  - INDEX.md 本行与 memory.md 任务状态
  - Verify: 只候选红 = 0；推送带版本号与主要变动

  **Task 2 证据（2026-11-05，补充核验）**
  - 实现核验：`backend/app/services/note_formula_generator.py` 当前按 `category` 分流；`auto_calc` 仅在 `auto`、无 mode 且当前值为空、或当前值匹配 `last_value` 时回写，金额经 `Decimal` 量化到分；`logic_check` / `reasonability` 只返回 `checks[]`，使用 `CheckOutcome` 五态。
  - 调用链：`backend/app/routers/disclosure_notes.py` 明确在 `POST /{project_id}/{year}/{note_section}/apply-formulas` 顶层返回 `checks`；`NoteFormulaDialog.vue` 接收并展示校对问题清单，前端保留 `status/label/severity`，不把 `not_executed` / `error` 误显示成普通「不通过」。
  - 后端命令：`rtk python -m pytest -p no:playwright tests/test_note_executor_category_split.py tests/test_note_formula_executor_branching.py tests/test_check_outcome.py` → **27 passed**（补充空目标 logic_check 用例后再次执行）。
  - 前端命令：`rtk npx vitest run src/components/formula/__tests__/NoteFormulaDialog.spec.ts src/components/formula/__tests__/formulaIssueRun.spec.ts` → **32 passed**（25 + 7）。
  - ORM 集成补充：`rtk python -m pytest -p no:playwright tests/test_note_formula_execute_tables.py tests/test_formula_push_note_followup.py` → **27 passed, 2 failed**；两条失败为既有 fixture 缺少 `formula_push_state` / `_formula_provenance`（`test_s5_cell_sources_returns_provenance_and_run_summary`、`test_s5_editor_save_preserves_formula_provenance_sidecar`），不涉及本任务目标测试；未执行共享 PG 写入，避免污染共享库，故 PG 回滚验收保留为环境偏离。
  - 变异（产物 `tmp_check_contract/mutation_*_result.json`）：①将类别分流改为 `if False`，`test_logic_check_empty_target_still_does_not_write` **按预期失败**（空目标被写入 `100.0`）；②将 `foreign_value` 手工保护改为 `False`，`test_no_mode_foreign_value_not_overwritten` **按预期失败**（`999.0` 被覆盖为 `100.0`）。两次均在 `finally` 逐字节恢复，源文件 SHA-256 `82cbeb35bcac829f4fdf64a5d612f5265ca5961ec8b17e6eef85a4200fb1745c` 与恢复值一致。
  - 诊断：相关 Python/Vue/TS 文件 `get_diagnostics` 无错误。偏离：未修改其他任务状态；PG 回滚验收因当前环境/安全边界未执行，已如实记录。
  - **PG 回滚验收（2026-11-05，补齐，任务 2 据此标为完成）**：新增 `backend/tests/test_note_executor_category_split_pg.py`（`pg_only`）。夹具在回滚事务内新建【测试】项目与附注一节（五、1，存储形状为 `_tables[0]` + 顶层镜像），不复用共享库数据、不提交；收尾回滚后用新连接核对项目未残留。用例：`auto_calc` 空目标回写为子项之和 300.0；手工格（999、无模式、`last_value` 100）保持 999，结果 `skipped_manual`；`logic_check` 目标保持手填 999，`checks` 仅一条 `2:1`，`failed`，left 30 / right 999 / diff 969；数值从 `disclosure_notes.table_data` 列读回校验（事务内已落库的值）。
  - 命令：在 `backend` 目录运行 `python -m pytest -p no:playwright tests/test_note_executor_category_split_pg.py -q -rs`。进程未设 `DATABASE_URL` 时（conftest 按环境变量判 PG），结果为 `1 skipped`，原因 `requires PostgreSQL`。为跑真库，本条命令内临时设 `DATABASE_URL=postgresql+asyncpg://postgres:…@localhost:5432/audit_platform`（即代码默认 `settings.DATABASE_URL`，`.env` 未写），命令结束即清除，未写入 `.env` 或共享终端环境 ⇒ **1 passed in 1.08s，未 skip**。
  - 回滚核对（只读 MCP 查共享库）：`projects` 名为【测试】附注执行器分流* 0 行，`disclosure_notes` 0 行，本时段孤立 `note_formula_run` 0 行。
  - 未做：未执行迁移，未对共享库持久写入；本用例未做 PG 侧磁盘变异（变异证据仍为上文两次源码变异）。上文「PG 回滚验收未执行」的偏离记录已由本条覆盖。

  - [ ]* enforce 下门禁面板逐项确认的浏览器走查：需另起 `CONSISTENCY_GATE_ENFORCEMENT=enforce` 的后端，连共享库会带起后台 worker 读写共享 storage，未做；同一流程由任务 6 的 PG 回滚用例 + vitest 覆盖（observe 下确认端点 409、enforce 下确认后放行、改数据后重新阻断）

  **Task 7 证据（2026-11-11，收尾）**
  - 入库：本 spec 在主工作树未提交的改动（门禁 27 处规则异常改 `not_executed`、`consistency_replay_engine` 空层、附注执行器分流的路由返回 `checks`、表间审核严重度、校对目录执行状态的前端、相关用例）由 `formula-hub-integrity-closure` 收尾会话按文件归属挑出，放进最新 HEAD 的干净 worktree 组成候选树后提交推送
  - 后端回归（候选树，非 PG，69 个文件含 `tests/formula_hub` / `formula_settings` / `formula_management` 与引用门禁 / 附注执行器的全部用例）：3486 passed / 16 failed；15 条在同一选集的干净 HEAD 上同红（`test_note_prior_dynamic` / `test_eqcr_consumer_inventory` / `test_property_6_ai_unconfirmed` / `test_qc_cross_module_conflict_rule` / `test_readiness_facade` 等，均非本 spec 改动），余 1 条 `test_startup_registry::test_health_includes_startup_report` 单跑 24 passed，属用例顺序相关
  - 前端回归（候选树 vs 干净 HEAD，`src/components/formula` + `src/views` + `src/services` + `src/composables/formula` + `src/components/common`）：3544 passed / 19 failed，对 HEAD 新增失败 0、修好 20。修了两处随本 spec 一起暴露的用例过期：①`c39949602`（表间审核改后端唯一结果、删除前端纯函数降级）没有同步测试，`useReportCrossCheck` 系列 22 条一直红 ⇒ 按现行契约改写 `useReportCrossCheck.spec.ts`（后端逐条结果 / 失败不本地自算 / 上下文围栏 / 映射 PBT）、删除只测已删纯函数的 `p32` / `property` 两个文件、`ReportView.characterization` 删去纯函数段、`severity` 第三条改测 issue_list 严重度补位；②`noteTreeSilentFallback` 的接口夹具对表间审核规则返回 `{}`，按本 spec 的严格读取会报「规则读取失败」⇒ 夹具改返回有效空集合
  - 浏览器（9980 / 3030，admin，只读为主）：全局公式设置「校对规则目录」12 个来源逐个显示「已接入 / 仅展示 / 不可执行」状态与说明，选中来源头部显示入口、结果表与「入口能力不代表项目已执行或通过」；【测试】公式同步甲 `五、1` 调 `apply-formulas` 返回 200，顶层带 `checks`（该节无校对类公式 ⇒ 空）、`updated=0`，`table_data` 读回只有 `_formula_provenance` 的本次计算时间 / 执行人 / run_id 变化，金额与手工格不变；一致性检查接口按五态返回（通过 3 / 失败 4 / 未执行 33），无「检查异常」
