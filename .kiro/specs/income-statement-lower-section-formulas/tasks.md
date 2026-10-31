# 实施计划：S9　利润表净利润以下行的公式补全（income-statement-lower-section-formulas）

> 以 design.md 为准，需求编号 R1~R4 见 design 页头。启动条件：母 spec X2（归属行升级）执行后；design §4 D1、D2 已拍板（未拍板按建议执行时在任务记录写明）。
> 通用纪律：临时产物放仓库根 `tmp_is_lower_section/`；真 PG 写入只在回滚事务内的【测试】项目，共享库只读；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`。
> 前置：母 spec `formula-hub-integrity-closure` 已入库（逐行计算、计算版本、归属行种子、合计行与行引用守卫在其中）。

- [ ] 0. 现状复核
  - 重算 design §1 十二行（四套利润表逐行公式、活项目取值、特殊公式表、求值顺序、试算表陈旧与符号版本、科目类别），变化追加到 design §1 末尾
  - Verify: 探针输出存 `tmp_is_lower_section/baseline/`

- [ ] 1. 公式文本按官方格式核对（R1、R4）
  - 国企、上市两版官方利润表格式逐行核对 design §2 的加减号与「其中」项（来源：仓库报表模板 xlsx / `backend/data/audit_report_templates/`），不符处回改 design §2 并写明依据
  - Verify: 核对表存 `tmp_is_lower_section/format_check.md`，每行有来源单元格或条款

- [ ] 2. 求值顺序改为依赖拓扑序（ADR-ISL-01，design §4 D2）
  - 新建 `backend/app/services/report_eval_order.py`；单体三路与 `consol_report_values.ordered_rows` 改调；`report_row_compute._not_ready` 判据随之调整；母 spec 守卫 `test_report_row_ref_order_guard.py` 改判环 / 悬空，并在本 spec design 登记该勘误
  - Verify: `eval_order` 纯函数夹具；守卫违规样本自检；现存四套报表定义（种子 + 快照库）环 = 0。变异：改回行号序 ⇒ 小计在明细前的用例红

- [ ] 3. 种子、输入行登记与提示（R1~R4，ADR-ISL-02/04）
  - `report_config_seed.json` 四套按 design §2 写公式与 `formula_source`；`report_row_compute` 提示文案按输入行区分；`report_formula_service` 特殊公式表删 5 条、两条减值改负号
  - 同源守卫 `test_income_statement_formula_single_source.py`
  - Verify: 母 spec 合计行守卫、行引用守卫（新判据）、种子归属行用例全绿；同源守卫全绿。变异：特殊表恢复「综合收益总额 → 6801」⇒ 同源守卫红；IS-037 去掉负号 ⇒ 任务 4 金标准用例红

- [ ] 4. 金标准与真 PG 验证（R1~R4）
  - 独立求值器 `tests/is_lower_section/gold_is_evaluator.py`（AST 黑名单：不得 import 生产报表、取数、逐行计算模块）；四套合成试算表夹具
  - 回滚事务内【测试】项目：四套各生成一次，逐行等于金标准；§2 恒等检查；合并节点经 `consol_report_values` 同值；`validate_linear` 全为 `None`
  - Verify: 上述用例全绿，金标准求值器未识别语法数 = 0

- [ ] 5. 存量发布工具（ADR-ISL-03，design §4 D4）
  - `backend/scripts/fix/publish_income_statement_chain.py`：默认只读；`--apply` 只改空公式与已知坏式、经同步内核发布、可重复执行；第三种公式退出码 2
  - Verify: 回滚事务内：只读不写、`--apply` 后目标行与 §2 一致、第二次 0 变更、第三种公式退出码 2 且不写；共享库只读模式输出贴入本任务。变异：放开改写条件 ⇒ 第三种公式用例红

- [ ] 6. 试算表陈旧提示（ADR-ISL-05，design §4 D3）
  - 报表生成结果在余额表含 v1 行、或试算表贷方性质损益科目为负时追加 warning（判据与母 spec `_tb_sign` 同口径）
  - Verify: 三个合成夹具（v2 且收入为正 ⇒ 无提示；余额表含 v1 行 ⇒ 提示；收入为负 ⇒ 提示）
  - 真实项目的数据修复（design §4 D3 的三步运维）由用户决定，本任务不执行；只读演练输出（两个脚本的 `--dry-run`）可贴入本任务供决策

- [ ] 7. 回归、浏览器实测与收尾
  - 候选树 vs 基线 HEAD 失败集合对比；浏览器（chrome-devtools，【测试】项目）：报表页利润表净利润以下有值、「手工输入行」提示可见；截图放 `tmp_is_lower_section/screenshots/`，用完停 about:blank
  - 存量 `--apply` 与真实项目重新生成按 design §4 D4 由用户决定，本 spec 不执行
  - INDEX.md 本行与 memory.md 任务状态
  - Verify: 只候选红 = 0；推送带版本号与主要变动
