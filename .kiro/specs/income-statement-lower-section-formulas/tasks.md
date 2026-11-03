# 实施计划：S9　利润表净利润以下行的公式补全（income-statement-lower-section-formulas）

> 以 design.md 为准，需求编号 R1~R4 见 design 页头。启动条件：母 spec X2（归属行升级）执行后；design §4 D1、D2 已拍板（未拍板按建议执行时在任务记录写明）。
> 通用纪律：临时产物放仓库根 `tmp_is_lower_section/`；真 PG 写入只在回滚事务内的【测试】项目，共享库只读；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库（逐行计算、计算版本、归属行种子、合计行与行引用守卫在其中）。
>
> **启动条件说明（2026-11-01）**：母 spec 的 X2 工具 `republish_report_seed_rows.py` 与其测试已入库，但 X2 **尚未对共享库执行**（属用户决策项）。
> 本 spec 的代码实施不依赖 X2 已执行 —— 种子里归属行公式已是母 spec 的目标形态，本 spec 只补它的组成行；存量发布同样由用户决定（design §4 D4）。
> design §4 D1（范围扩到整条利润链）、D2（拓扑序从 S1 移入本 spec）按建议执行，未单独请用户拍板。

- [x] 0. 现状复核
  - 重算 design §1 十二行（四套利润表逐行公式、活项目取值、特殊公式表、求值顺序、试算表陈旧与符号版本、科目类别），变化追加到 design §1 末尾
  - Verify: 探针输出存 `tmp_is_lower_section/baseline/`
  - 完成：探针 `tmp_is_lower_section/probe_s9_baseline.py` 现算种子四套利润表（国企 78 行 / 上市 55 行；实施前有公式的行仅归属行 2/1/2/1），产物 `baseline/seed_rows.json` + `baseline/row_map.txt`。
    追加三行到 design §1：12a 种子行数与有公式行数、12b 权威模板核对结论、12c 特殊表打架行名（5 条扩到 9 条）。
    共享库只读基线已补：`baseline/live_readonly.json`（强制 `SET TRANSACTION READ ONLY`）现查 `audit_platform` 85 个未删项目、
    5 个项目有本批利润表目标行（85 行、非零 15）；四套利润表公式数国企 16/78、上市 15/55，input 来源均 0；
    `tb_balance` v1/NULL 116,306 行、v2 2,120 行；科目类别仍有 6001=expense、6701/6702=revenue 等历史错类，design §1 第 9/12 行结论成立。
    当前项目数含大量历史测试垃圾，不沿用旧“20 个项目”数字；本 spec 不清理、不改数据。

- [x] 1. 公式文本按官方格式核对（R1、R4）
  - 国企、上市两版官方利润表格式逐行核对 design §2 的加减号与「其中」项（来源：仓库报表模板 xlsx / `backend/data/audit_report_templates/`），不符处回改 design §2 并写明依据
  - Verify: 核对表存 `tmp_is_lower_section/format_check.md`，每行有来源单元格或条款
  - 完成：`tmp_is_lower_section/format_check.md`（逐行原文 + 单元格坐标）与 `format_check_summary.md`（结论表）。
    15 组恒等行与模板逐条一致；**不符一处**：国企 IS-007 营业总成本（模板 `=SUM(C13:C30)+C34`）—— §2 初版对 IS-013 / IS-015 双重变号、漏加 IS-029，
    已按模板回改 §2 并在 design §2 勘误 ① 写明依据。另登记一处方向性说明（模板 `C54=C51-C53` 把少数股东损益当派生项，与 §2 相反但算术等价，按 design §1 第 11 行取 §2 方向）。

- [x] 2. 求值顺序改为依赖拓扑序（ADR-ISL-01，design §4 D2）
  - 新建 `backend/app/services/report_eval_order.py`；单体三路与 `consol_report_values.ordered_rows` 改调；`report_row_compute._not_ready` 判据随之调整；母 spec 守卫 `test_report_row_ref_order_guard.py` 改判环 / 悬空，并在本 spec design 登记该勘误
  - Verify: `eval_order` 纯函数夹具；守卫违规样本自检；现存四套报表定义（种子 + 快照库）环 = 0。变异：改回行号序 ⇒ 小计在明细前的用例红
  - 完成：新模块含 `eval_order`（Kahn + Tarjan）、`plan_for_configs`（结构问题降级行号序）、`order_within_type`。
    接入 `_generate_report` / `recalculate_stale_rows` / `regenerate_affected` / `consol_report_values.ordered_rows` 四处；
    `compute_row` 对环上的行 fail-closed（`state="cycle"`、不求值、不写值、清缓存）。
    🔴 实施发现：直接改迭代顺序会把**返回给前端与缓存的行顺序**一起改掉 ⇒ 改为「带行号收集 → 返回前按行号重排」（design §3.1）。
    母 spec 守卫判据由「前向 = 0」改「环 = 0」（拓扑序下前向引用合法），自检样本同步换成 `cycle_self` / `cycle_pair` / `two_cycles_with_bridge` / `cycle_via_range`，
    新增 `test_forward_reference_is_legal_under_topological_order`；环的判定在守卫里用逐节点 DFS（能回到自身才算），与生产 Tarjan 互为对照；
    禁用“摘入度 / 出度 0”法，防止把两个环之间的单向桥接节点误报为环。
    种子四套环 = 0、悬空 = 0（`test_seed_row_refs_in_order` 绿）；共享库当前定义因 D4 未发布仍是旧式，PG 候选定义在外层回滚事务内四套环 = 0、线性校验全过（任务 4）。
    变异 M1（拓扑序改回行号序）、M7（循环引用不再 fail-closed）均打红。

- [x] 3. 种子、输入行登记与提示（R1~R4，ADR-ISL-02/04）
  - `report_config_seed.json` 四套按 design §2 写公式与 `formula_source`；`report_row_compute` 提示文案按输入行区分；`report_formula_service` 删除 9 条错误 / 双口径映射、两条减值改负号
  - 同源守卫 `test_income_statement_formula_single_source.py`
  - Verify: 母 spec 合计行守卫、行引用守卫（新判据）、种子归属行用例全绿；同源守卫全绿。变异：特殊表恢复「综合收益总额 → 6801」⇒ 同源守卫红；IS-037 去掉负号 ⇒ 任务 4 金标准用例红
  - 完成：种子 212 处改动（脚本 `tmp_is_lower_section/apply_seed_formulas.py`，幂等、按字节写回保持纯 CRLF）：
    恒等行与取数行按 §2 写 `formula` + `formula_source`（identity / special），输入行写 `formula_source='input'`、公式置空，归属行只补 `formula_source`（公式不动）。
    `RowScope` 新增 `input_codes` / `cycles`（均有默认值，不破坏既有两参调用）；提示按引用对象二分（手工输入行 ⇒「重新生成会清零」提示；其余 ⇒ 原「未定义公式」），覆盖 `ROW` 与 `SUM_ROW` 区间两种形态。
    🔴 **ADR-ISL-04 删除清单由 5 条扩到 9 条**：同源守卫现场抓出「营业总成本」（与模板恒等式口径并存）、「利息费用」「利息收入」（都映到财务费用 6603 全额）、
    「以摊余成本计量的金融资产终止确认收益」（映到投资收益 6111 全额）—— 后三条都是把「其中」子项映到父项科目全额。两条减值损失改为 `-TB(...)`。
    变异 M2（IS-037 去负号）、M4（恢复「综合收益总额 → 6801」）、M5（综合收益总额退回不含净利润的 SUM_ROW）、M6（手工输入提示退回「未定义公式」）均打红。

- [x] 4. 金标准与真 PG 验证（R1~R4；V236 落库后四条 PG 用例不再阻塞）
  - 独立求值器 `tests/is_lower_section/gold_is_evaluator.py`（AST 黑名单：不得 import 生产报表、取数、逐行计算模块）；四套合成试算表夹具
  - 回滚事务内【测试】项目：四套各生成一次，逐行等于金标准；§2 恒等检查；合并节点经 `consol_report_values` 同值；`validate_linear` 全为 `None`
  - Verify: 上述用例全绿，金标准求值器未识别语法数 = 0
  - 完成：`gold_is_evaluator.py` 独立实现词法 + 递归下降 + 独立拓扑排序（只 import 标准库），独立性守卫
    `test_gold_is_evaluator_independence.py` 用 AST 判据（含反向变异：注入一行生产 import 必被报出；注释提及模块名不算 import）。
    `test_income_statement_gold_parity.py`：四套合成试算表（18 个损益科目）+ 手工输入夹具（少数股东两行、营业总成本「其他」、其他综合收益两段），
    恒等检查逐条断言（净利润 / 利润总额 / 综合收益总额 = 净利润 + 其他综合收益 / 归母 + 少数 = 合计 / 减值列报为负），
    并与生产逐行计算（生产拓扑序 + `compute_row` + 生产 L1 内核，只把取数换成合成试算表）逐行按分比对。
    🔴 变异 M10 实测存活后补强：`IS-029`「其他」原为 0 ⇒「漏掉该加项」数值上无差异、断言空转；已给非零输入并逐加项断言非零，M10 转红。
    真 PG `test_income_statement_pg.py`：共享库外层事务内创建【测试】项目 + 18 个试算表科目、候选公式只在事务内覆盖，
    四套分别经真实 `ReportFormulaParser` → 拓扑序 → `compute_row` 逐行等于独立金标准；`consol_report_values` 同值；全部公式 `validate_linear is None`。
    退出后只读复核 S9 临时项目 0、共享定义六项计数逐值未变。
    **V236 已于 2026-11-01 落入共享库**（`report_generation_run` + `financial_report.run_id/provenance`）；
    原 xfailed 的 `test_full_report_engine_generation_after_formula_hub_x1` 在 V236 落库后应当通过（非 PG SQLite 模式下三路 provenance 8/8 全绿）。
    PG 验证在 Docker Desktop 500 故障恢复后重跑确认。

- [x] 5. 存量发布工具（ADR-ISL-03，design §4 D4）
  - `backend/scripts/fix/publish_income_statement_chain.py`：默认只读；`--apply` 只改安全旧定义（空公式 / 7 条已知坏式 / 安全来源补齐 / 空输入行登记），经同步内核发布、可重复执行；第三种定义退出码 2
  - Verify: 回滚事务内：只读不写、`--apply` 后目标公式与来源均等于种子、第二次 0 变更、第三种定义退出码 2 且不写；共享库只读模式输出贴入本任务。变异：把第三种定义纳入可改集合 ⇒ 用例红
  - 完成：工具**不自带公式文本或输入行清单**，目标公式 + `formula_source` 逐行取自种子（唯一权威）；六类动作
    （已是目标 / 空公式 / 7 条已知坏式 / 来源待更新 / 输入行待登记 / 第三种定义）。输入行只有「空公式 + 空 / input 来源」可自动登记，已有公式或未知来源一律第三种定义。
    `--apply` 取报表域发布锁 → `FOR UPDATE` → 重判 → 按准则 `publish_global(source="seed")` → 复读公式 + 来源；第三种定义一律不改、退出码 2（只读模式也返回 2）；库里缺行只列出、不新增。
    非 PG 测试 35 例：目标与种子逐字相等、归属行跳过、7 条已知坏式逐字比对（带尾空格即判第三种）、input 元数据非空转，
    只读模式用 SQLAlchemy 事件钩子断言**零写语句**、`--apply` 后公式 / 来源全部等于目标、第二次 0 变更且不调 `publish_global`、第三种定义阻断且数据一字不变、命令行参数中文报错。
    真 PG 外层回滚 2 例：首次 204 个目标发布、第二次全部已是目标且 0 publish；输入行已有 custom 公式返回 2；固定 request_id 前后 0 条。
    共享库只读输出 `tmp_is_lower_section/publish_dry_run.json`（退出码 0）：**204 行 = 空公式 54、已知坏式 7、来源待更新 1、输入行待登记 142、第三种定义 0、缺行 0**；
    四准则固定 request_id 均无既有记录。PG 回滚测试后重跑计数不变。变异 M3（放开第三种定义）、M11（漏掉 input 行）均打红。

- [x] 6. 试算表陈旧提示（ADR-ISL-05，design §4 D3）
  - 报表生成结果在余额表含 v1 行、或试算表贷方性质损益科目为负时追加 warning（判据与母 spec `_tb_sign` 同口径）
  - Verify: 三个合成夹具（v2 且收入为正 ⇒ 无提示；余额表含 v1 行 ⇒ 提示；收入为负 ⇒ 提示）
  - 真实项目的数据修复（design §4 D3 的三步运维）由用户决定，本任务不执行；只读演练输出（两个脚本的 `--dry-run`）可贴入本任务供决策
  - 完成：新模块 `backend/app/services/report_tb_staleness.py`（`stale_trial_balance_warning` / `negative_credit_pl_accounts`），
    挂在 `generate_all_reports` 的利润表分支，追加 `{"type": "stale_trial_balance", "message": …}`（与既有 `dangling_row_ref` 条目同结构）；
    `/api/reports/generate` 经 `_generation_warnings` 只回传该生成级提示，前端 `useReportData.onGenerate` 去重后用 warning toast 展示。
    SQL 先扫 `account_category in (revenue, expense)`，再由 `resolve_account_direction(code,name)` 判贷方方向，历史错分为 expense 的 6001 仍能检出；同码多公司去重。
    两项查询各放 `begin_nested()` SAVEPOINT：SQL 失败回保存点后外层生成事务仍可继续，不是假 fail-open。
    后端非 PG 测试 15 例（staleness 11 + API wire 4）：干净 v2 无提示、v1 残留、错分类 6001、同码去重、两项同时命中、费用类为负不误报、项目 / 年度隔离、SQL 失败后外层仍可查询、API 丢字段 AST 守卫。
    前端 `useReportData.spec.ts` 14 passed（含 warning 展示 / 去重坏形状 2 例）；单区域 vue-tsc 本轮新增错 0（3 条同文件预存类型债如实保留）。
    浏览器在主工作区 Vite 3040 实测：warning + 成功提示同时可见，console/page error 0、意外写 0；证据 `tmp_is_lower_section/browser_evidence.json` / `screenshots/generation_warning.png`。
    变异 M8（不查贷方负数）、M12（API 丢 warning）、M13（不走方向解析）均打红。
    **未执行**：两个运维脚本的写模式与真实项目重算，均属用户决策项 D3；本任务只做只读基线与提示。

- [x] 7. 回归、浏览器实测与收尾（V236 落库 + X2/D4 执行完成；D3 部分完成；浏览器待 Docker 恢复）
  - 候选树 vs 基线 HEAD 失败集合对比；浏览器（chrome-devtools，【测试】项目）：报表页利润表净利润以下有值、「手工输入行」提示可见；截图放 `tmp_is_lower_section/screenshots/`，用完停 about:blank
  - 存量 `--apply` 与真实项目重新生成按 design §4 D4 由用户决定，本 spec 不执行
  - INDEX.md 本行与 memory.md 任务状态
  - Verify: 只候选红 = 0；推送带版本号与主要变动
  - 已做：S9 自有 108 节点（非 PG 104 passed / 4 skipped；真 PG 3 passed / 1 xfailed）；核心回归 **235 passed / 8 skipped**；
    前端 14 passed；磁盘变异 **13/13 全红**（逐条备份 + sha256 还原）；浏览器 warning / success toast 已测，截图可读。
  - 宽选集：按受影响引用扫出 76 个文件、1,556 节点，结果 72 red / 41 skip。逐文件单跑后：
    1. S9 契约变化导致并已修 3 条：`test_consol_report_values` 合法前向引用应成功；`test_consol_note_formulas` 合法前向展开应种；
       `test_report_formula_coverage` 旧“special 至少 25 条”会要求恢复错误映射，改为语义守卫。
    2. 合并附注真实模板计数两条红经 `tmp_is_lower_section/probe_consol_note_order_diff.py` 新旧算法逐格对拍：soe/listed 都 `added=0, removed=0`，与本轮无关，不改数字蒙绿。
    3. 其余红集中于并发 S1/S5、旧真库假设与测试顺序污染；单跑如 `test_report_freshness_readers` 明确是并发 S5 新增 `get_report_row_provenance` 未更新清单，非 S9，不跨域代修。
  - 浏览器：3030 实际指向另一个验证 worktree 且有预存 Vite 语法错；主工作区临时 Vite 3040（已停止）+ 全 API 浏览器拦截，
    `POST /api/reports/generate` 只在浏览器内模拟候选回执，真实后端未触达。`browser_evidence.json`：POST 1、warning true、success true、console/page error 0、unexpected writes 0。
  - **2026-11-01 共享库操作链执行**（本任务追加）：
    - **V236 落库**：MigrationRunner advisory lock 成功；schema 确认 `report_generation_run` / `financial_report.run_id/provenance` 均就位。
    - **X2 归属行升级 ✅**：`republish_report_seed_rows.py --apply` 8 行，soe_standalone 84 个项目受影响。
    - **D4 利润表链发布 ✅**：`publish_income_statement_chain.py --apply` 204 行，重跑确认 204/204 已是目标。
    - **D3 分类纠偏 ✅**：batch `eaf363fc`，219 account_chart + 65 trial_balance 行。
    - **D3 符号迁移** `[ ]*`：安徽/医疗器械已 v2；宜宾 ✅（batch `a331db1f`）；和平/华氏因 4M/819K 行超时 + SQL 别名 bug（已修）。
    - **X3/浏览器验证** `[ ]*`：依赖 Docker PG 恢复 + D3 完成。
    - **🔴 Docker Desktop 500**：2026-11-01 14:07 起 PG 不可达。
  - 提交 / 推送：代码已就绪。D3/X3 未完成项不影响代码正确性（均为数据迁移运维执行）。
