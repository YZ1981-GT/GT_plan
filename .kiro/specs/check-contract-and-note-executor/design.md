# 设计文档：S2　校对契约与附注执行器（check-contract-and-note-executor）

> 需求编号：requirements §1 六条依次记 R1（附注执行器只回写 auto_calc）、R2（校对目录执行状态）、R3（XR skip 计入签字）、R4（表间审核规则只提示）、R5（enforce 下签字人逐项确认留痕）、R6（`ConsistencyBlockingDiffRule` 吞异常）。
> 现状基线：分支 HEAD `4c0a1e0a6` + 母 spec 整合树 `tmp_fhic/integ`（`d91f5f804`，含 ADR-FHIC-14 门禁五态与 `gate_decision`）。数字为 2026-10-29 现算。

## 0. 结论

六件事背后是同一个问题：校对类结果没有统一的状态契约，各处把「没跑」「跑挂了」当成「通过」。本设计给校对结果一个五态契约（与母 spec 门禁五态同一枚举），附注执行器按类别分流（取数类回写、校对类只出问题清单），XR 与门禁规则的跳过 / 异常一律变成可见的「未执行」，enforce 下由签字人逐项确认并留痕。触类旁通扫描发现门禁规则里异常即放行的处理器有 27 处（R6 只点名了 1 处），一并收口。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | R1：附注执行器会覆盖手工格 | `note_formula_generator.execute_note_formulas` 合并 `_formulas` 与 `_user_formulas`（用户集优先）后**不看 `category`**，结果非空即以 `float` 回写 `rows[r].values[c]`；只跳过 `_cell_modes[col] != "auto"` 的格，没有 `_cell_modes` 的格按 auto 处理 ⇒ 用户直接录入但未记模式的格会被覆盖；校对类公式（如 `cell(2,0) = cell(0,0) + cell(1,0)`）被当成取数式回写右侧结果 | 成立 |
| 2 | R1 可达性 | 生产调用方只有附注页「执行公式」端点（`routers/disclosure_notes.py`）；Draft Refresh 编排器的模块文档提到它，但现无调用；类别取值 `auto_calc / logic_check / reasonability`，缺省 `auto_calc`。真库活项目附注 727 节：`_formulas` 非空 0、`_user_formulas` 非空 0、含 `_cell_modes` 的行 85、带 `evaluated_at` 的 0 ⇒ 执行器从未在真实数据上回写过 | 现网暴露 0，正常前置可达 |
| 3 | R2：校对目录只有定义 | `formula_check_catalog.py`（`GET /api/formula-catalog/check-rules`）登记 12 类来源，只输出规则定义与来源文件；结果落库的只有 `cross_check_results`（真库 0 行）、`wp_qc_results`（1 行）、`gate_decisions`（2 行）；一致性门禁不落库 | 成立 |
| 4 | R3：XR skip 不计入签字 | `gate_rules_cross_check.CrossCheckPassedRule` → `CrossCheckService.check_for_sign_off` 只把 `status == "fail"` 且规则 `severity == "blocking"` 判为不通过；`skip` 一律放行。XR-08 恒 `skip`（实现为占位）；取不到底稿值的规则也是 `skip`；XR-05 用了未注册函数 `TB_SUM`。年度取 `trial_balance` 最大年度，取不到直接放行 | 成立，另有年度口径与 `TB_SUM` 两处 |
| 5 | R4：表间审核规则不能声明「只提示」 | V199 `cross_check` 域定义只有 `left_ref / operator / right_ref / tolerance / label / description`，没有严重度字段；内置 7 条勾稽同样没有 | 成立 |
| 6 | R5：enforce 下没有逐项确认 | 整合树 `gate_decision`：enforce 下阻断级 failed / not_executed / error 一律阻断，没有任何豁免或确认入口 ⇒ 开启 enforce（母 spec X4）后被卡住的项目只能等数据补齐，没有审计判断的出口 | 成立 |
| 7 | R6：`ConsistencyBlockingDiffRule` 吞异常 | `gate_rules_phase14.ConsistencyBlockingDiffRule.check` 异常 ⇒ `logger.debug` 后返回 `None`（放行）；它走 `consistency_replay_engine`，其中「报表 → 附注」层是空实现（注释「完整实现需要 note_wp_mapping 关联」） | 成立 |
| 8 | （交接未列）同类处理器 | AST 现算：`gate_rules*.py` 里门禁规则 `check()` 内「捕获 `Exception` 后返回 `None`」共 **27 处 / 7 个文件**（`gate_rules_phase14` 13、`gate_rules_round6` 5、`gate_rules_b60` 3、`gate_rules_chain` 2、`gate_rules_eqcr` 2、`gate_rules_ai_content` 1、`gate_rules_cross_module_conflict` 1） | 新增：触类旁通 |

### Task 0 现状复核 (2026-10-29)

> 探针产物：`tmp_check_contract/baseline/`、`tmp_check_contract/probes/`。

| # | 判定 | 说明 |
|---|---|---|
| 1 | ✅ 成立 | `execute_note_formulas` 合并 `_formulas` + `_user_formulas`（用户集优先），不看 `category`，`_cell_modes` 缺失按 auto，结果非空即 `float` 回写 — 与原表一致 |
| 2 | ⚠️ 部分变化 | 727 节 / `_formulas` 非空 0 / `_user_formulas` 非空 0 / `evaluated_at` 0 均不变；**`_cell_modes` 从 85 降至 3**（真库行数据变化所致，不影响结论"执行器从未回写"） |
| 3 | ✅ 成立 | 12 类来源不变；`cross_check_results` 0 / `wp_qc_results` 1 / `gate_decisions` 2 均不变 |
| 4 | ✅ 成立 | `check_for_sign_off` 只判 `status=="fail"` + `severity=="blocking"`；`skip` 一律放行；XR-08 恒 skip；XR-05 含 `TB_SUM`；年度取 `trial_balance` 最大年度、取不到放行 |
| 5 | ✅ 成立 | `cross_check` DomainSpec `exec_fields=("left_ref","operator","right_ref","tolerance")` + `meta=("label","description")`，无 severity |
| 6 | ✅ 成立 | HEAD 无 acknowledgement 表 / 函数；`GateEngine.evaluate` 只有 allow / warn / block，无确认旁路 |
| 7 | ⚠️ 数字变化 | 实际 **28 处 / 7 文件**（原写 27 / 7）：`gate_rules_chain.py` 有 3 处（原写 2）— 第三处是 `ConsistencyPassedRule.check()` line 152；其余 6 文件计数不变 |
| 8 | ✅ 成立 | `_check_layer3`（报表→附注）空实现（注释"完整实现需要 note_wp_mapping 关联"）；layer4/5 同样空实现 |

## 2. 架构裁定

**ADR-CCN-01 校对结果五态契约。** 新模块 `backend/app/services/check_outcome.py`：`CheckOutcome(status, reason, left, right, diff, severity, rule_id, source)`，`status` 直接复用母 spec 门禁五态枚举（`passed / failed / not_executed / not_applicable / error`），`severity ∈ {blocking, warning, info}`；工厂函数 `passed(...)` 不得在 `except` 块内调用（AST 守卫，与母 spec `test_consistency_gate_status.py` 同法）。XR、表间审核、附注校对类公式三个执行器的结果都转成它，前端展示用同一组中文标签（「通过」「未通过」「未执行（原因）」「不适用」「检查异常」）。

**ADR-CCN-02 附注执行器按类别分流（R1）。** `execute_note_formulas` 在合并公式集后按 `category` 分两路：`auto_calc` 回写；`logic_check / reasonability` 只求值、产出 `CheckOutcome` 列表（比较式两侧都算，差额 > 0.005 为 failed），不回写任何格。回写条件收紧为：目标格 `_cell_modes[col] == "auto"`，或该格没有模式且当前值为空 / 与上次本执行器写入值相同（上次写入值记在公式定义的 `last_value`）；有值且不是本执行器写的 ⇒ 不覆盖，结果记 `skipped_manual`。回写值用 `Decimal` 量化到分后存数字（与 S1 的 float → Decimal 一致，本处先做）。返回体增 `checks[]`；附注页把 `checks` 显示在问题清单里，不再计入「已更新 N 格」。

**ADR-CCN-03 校对目录执行状态（R2）。** 目录每条规则增 `execution`：`wired`（有执行器且有生产调用）、`display_only`（只展示，无执行器）、`not_executable`（定义是自然语言或依赖的表 / 文件不存在，写明原因）。判定写在 `formula_check_catalog.py` 的来源登记里（每类来源一个执行器入口或 `None`），守卫断言 `wired` 的入口函数真实存在且被生产代码调用。带 `project_id` 请求时再给 `last_run{at, status, counts}`：XR 与表间审核读 `cross_check_results`，质控读 `wp_qc_results`，一致性门禁读 `gate_decisions`（只读，不新增落库）；没有落库的来源返回 `last_run: null` 并注明「本类结果不落库」。覆盖度统计只计 `wired`。

**ADR-CCN-04 XR 进签字判据（R3）。** `CrossCheckPassedRule` 改为：年度取 `fetch_project_audit_year`，为空 ⇒ warning 命中「项目未设置审计年度，未运行跨科目校验」；XR 结果按 ADR-01 转换（`skip` → `not_executed`，原因来自执行器）；判定交给与一致性门禁同一个函数（`gate_decision` 增 `consumer="cross_check_rule"` 分支）：observe 下有阻断级 failed / not_executed / error ⇒ warning 命中，enforce 下 ⇒ blocking 命中。XR-05 的 `TB_SUM` 改为已注册的 `SUM_TB`（与母 spec 预设库归一同一映射）；XR-08 在实现前标 `not_executable`（原因「利息合理性规则尚未实现」），不再报 `skip`。

**ADR-CCN-05 表间审核规则带严重度，缺省「只提示」（R4）。** `cross_check` 域定义 `exec_fields` 增 `severity`（变更即重新执行），缺省 `warning`；内置 7 条勾稽同样缺省 `warning`。表间审核结果的「未通过」在界面上按严重度显示为「提示：差额 x」或「未通过」；签字 / 导出门禁不读表间审核结果（现状如此，守卫钉住），只有将来显式标 `blocking` 的规则才可能被门禁消费，本 spec 不开放该用法。报表审核（`report_review` 汇总）把 warning 级未通过计入「提示」，不计入「失败」（实施时现读该汇总函数位置）。

**ADR-CCN-06 enforce 下逐项确认留痕（R5）。** 新表 `consistency_gate_acknowledgements(id, project_id, year, check_name, branch_id, status, result_fingerprint, reason, acknowledged_by, acknowledged_role, created_at, revoked_at, revoked_by)`。`result_fingerprint` = sha256（检查名、分支编号、状态、该项的关键数值 —— 差额、左右值），数据变了指纹就变、确认自动失效。`gate_decision` 在 enforce 下把「有未撤销且指纹一致的确认」的项从阻断集合里移出，改为 warning 并带确认人与原因。端点：`GET/POST /api/projects/{pid}/consistency-gate/acknowledgements`、`POST …/{id}/revoke`；确认与撤销都写审计链（`mandatory`，经 S10 的 `append_audit_log`）。谁能确认见 §4 D1。前端 `ConsistencyGatePanel` 对阻断项显示「确认并说明」（原因 ≥ 10 字），已确认项显示确认人、时间、原因与「撤销」。observe 下不显示确认入口（不阻断就不需要确认）。

**ADR-CCN-07 门禁规则异常不再放行（R6 + 同类 27 处）。** 新增 `gate_engine.GateRule` 的包装：`check()` 抛出的异常与规则内部「捕获后返回 None」的写法统一改为返回 warning 命中「检查异常，未执行：{规则名}（{原因前 200 字}）」，原因记 error 日志；27 处 `except … return None` 逐个改成调用 `self.not_executed(reason)`（基类方法），规则内部按业务含义「本项目不适用」而返回 `None` 的分支保留（如 QC-25 在 `report_snapshots` 表不存在时属于结构性不可用，改为 `not_applicable` 而非放行）。AST 守卫：`gate_rules*.py` 的 `check()` 内捕获 `Exception` 的处理块不得 `return None`。是否在 enforce 下把「检查异常」升为阻断见 §4 D2。`consistency_replay_engine` 空实现的「报表 → 附注」层改为该层返回 `not_executed`，不再产出空层冒充一致。

## 3. 数据与迁移

迁移 `V{n}`（实施时三路合扫取号）：`consistency_gate_acknowledgements` 与索引 `(project_id, year, check_name) WHERE revoked_at IS NULL`；`R{n}` 删表。`cross_check` 的 `severity` 存在定义 JSON 里，不加列。无存量数据迁移（V199 六表 0 行、`cross_check_results` 0 行）。

## 4. 待用户拍板

| # | 事项 | 建议 |
|---|---|---|
| D1 | 谁能逐项确认 | 数据缺失 / 检查异常类：本项目经理或合伙人；比较不通过类：只签字合伙人；原因必填 ≥ 10 字 |
| D2 | enforce 下「检查异常」是否阻断 | 与 not_executed 同等对待（阻断，可逐项确认） |
| D3 | 附注执行器对「没有模式、有值、非本执行器写入」的格 | 不覆盖并提示（ADR-02）；若要求一律以公式为准则需用户确认 |
| D4 | 本 spec 何时启动 | 与母 spec X4（门禁切 enforce）同批；R1、R2、R4、R6 不依赖 X4，可先做 |

## 5. 测试与变异

- 单元：执行器分流（三类别各一组夹具：auto_calc 回写、logic_check 只出结果、手工格不覆盖、本执行器上次写入值可覆盖）；`CheckOutcome` 工厂 AST 守卫；目录 `execution` 判定与 `wired` 入口真实存在守卫；XR 转换表（pass / fail / skip / error）；`gate_decision` 三种 consumer × 两种模式 × 有无确认；指纹随数据变化失效。
- 端点：确认 / 撤销权限配方表（按 D1）；确认写审计链；observe 下确认端点返回 409「当前为只提示模式，无需确认」。
- 门禁规则：27 处每处一个参数化用例（注入异常 ⇒ warning 命中，不再返回 `None`）；结构性不可用分支 ⇒ `not_applicable`。
- 真 PG（回滚事务内【测试】项目）：XR 在缺底稿数据时签字门禁出现 warning；enforce 下阻断项确认后放行、改数据后重新阻断。
- 前端 vitest：`ConsistencyGatePanel` 确认 / 撤销交互与五态标签；附注页问题清单显示校对结果。
- 磁盘变异：执行器去掉类别分流 ⇒ logic_check 用例红；XR `skip` 改回放行 ⇒ 签字用例红；`gate_decision` 不看指纹 ⇒ 失效用例红；任一门禁规则恢复 `return None` ⇒ AST 守卫红。
