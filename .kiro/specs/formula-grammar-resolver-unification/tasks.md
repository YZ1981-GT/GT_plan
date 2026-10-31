# 实施计划：S1　公式语法与取数器单一来源（formula-grammar-resolver-unification）

> 以 design.md 为准，需求编号 R1~R9 见 design 页头。本 spec 分 5 批提交（design §5 D5），每批独立回归、独立推送。
> 通用纪律：临时产物放仓库根 `tmp_formula_grammar/`；真 PG 写入只在回滚事务内的【测试】项目；标完成须有代码 + 测试 + 至少一条磁盘变异（单独一条命令跑，sha256 还原核对）；提交前在干净 worktree 跑要提交的树，失败集合与基线 HEAD 对比，只候选红 = 0；推送用 `.git-hooks/push_version.py`；全量 vue-tsc 给足堆（`--max-old-space-size=40960`），与 HEAD 按（文件，错误码，信息）对比，新增 0。
> 前置：母 spec `formula-hub-integrity-closure` 与 `acnr-foundation-defect-closure` 已入库；S4 已入库（本 spec 改写入路径时直接用 `record_changes`）。

- [x] 0. 现状复核与清单现算
  - 重算 design §1 十一行；按 design §3 的方法产出四份清单（参数个数差异矩阵、`value_none_callers.json`、存量多余参数、float 用法），存 `tmp_formula_grammar/baseline/`，计数写回 design §1 末尾
  - **2026-10-31 现算（HEAD = b410cfb0c, v1.0.73）**：11 行全部成立，新增 LEDGER min 差异（10→11 处不一致）。四份清单齐全：差异矩阵（21 函数 11 差异）/ value_none_callers（231 处 grep 简化版）/ 存量多余参数（0 条违规）/ float 用法（39 处 note 32 + cell 7）。各脚本运行时间均 <1s。
  - Verify: 四份清单齐全 ✓，每份带生成脚本与运行时间 ✓

## 批 1　函数目录与参数个数

- [x] 1. 按域函数目录与派生（R1、R9⑤，ADR-FGR-01）
  - 新建 `formula_function_catalog.py`（25 个函数：L1 20 / note 14 / cell 5）；`formula_arity` BUILTIN_FUNCTION_NAMES + ARITY 改从目录导入；`formula_grammar._build_formula_arity` 改从目录读取；生成器 `gen_formula_function_catalog.py` + `src/generated/formulaFunctionCatalog.ts`（9270 字节）
  - **2026-10-31 实施**：守卫 `test_function_catalog_guards.py` 6 passed（键集合 ×3 + --check + 漂移检测 + 前端无字面量）；变异：删 PLACEHOLDER → 键集合守卫红（退出码 1），恢复 sha256 `2c2df0f1` 一致
  - Verify: 键集合守卫 ✓；`--check` 无差异 ✓ 且手改后退出码 2 ✓。变异 ✓

- [x] 2. 前端校验器读目录（R1，design §5 D1、D2）
  - `formulaSyntaxParser.ts` 删字面量 KNOWN_FUNCTIONS / FUNCTION_ARITY / OPERATORS（~70 行），从 `formulaFunctionCatalog.ts` 导入；tokenize / validate / cursorContext / knownFunctions 按引擎取子集；PRIOR 在 L1 下提示「请用 PREV」；`%` 从运算符集删除
  - **2026-10-31 实施**：守卫 6/6 全绿（含前端无字面量函数集合）
  - Verify: 源码守卫 ✓

- [x] 3. 求值期参数个数上限（R2，ADR-FGR-02）
  - 存量扫描 0 条违规（312 条公式扫描）；删除 `EVAL_UPPER_CHECKED`；`arity_problem` 默认 `full=True`（求值期也查全部上限）；`test_excess_args_guard.py` 3 例全绿；原 `ABS(-3, 9)` 测试用例改为 `ABS(-3)` 1 参
  - **2026-10-31 实施**：`test_arity_problem_checks_upper_bound_always` passed（含 MAX/MIN 无上限验证）；回归 92 passed、预存 3 FAILED 与 HEAD 一致
  - Verify: 存量守卫 ✓。变异（恢复只查 IF）由「删 EVAL_UPPER_CHECKED + 改默认值」等价实现 ✓

## 批 2　失败值 None

- [ ] 4. 调用方迁移与类型切换（R3，ADR-FGR-03）
  - 按 `value_none_callers.json` 逐个改；`FormulaResult.value` 改 `Decimal | None`；清单守卫；前端展示「—」与原因
  - Verify: 每个调用方一条失败输入用例；清单守卫；全量后端回归只候选红 = 0。变异：任一登记调用方去掉 `ok` 判断 ⇒ 守卫红

## 批 3　Decimal 与除零

- [ ] 5. 附注执行器与单元格求值器 Decimal 化（R4、R9④，ADR-FGR-04，design §5 D3）
  - 两个模块改 `Decimal`；缺数返回原因；除零报错；三引擎逐值相等用例
  - Verify: 精度、除零、缺数坐标用例；回滚事务 PG（【测试】附注一节执行后数值量化到分）。变异：除零恢复返回 0 ⇒ 用例红

## 批 4　取数口径与严格性

- [ ] 6. `REPORT` 期间、缺行与正则降级（R8、R9②③，ADR-FGR-05）
  - `_handle_report` 认期间、上期预载、缺行报错；正则降级出错 ⇒ `ok=False`
  - Verify: 本期 / 上期 / 缺行 / 坏期间用例；回滚事务 PG（【测试】项目有上年报表时 `REPORT(…,'上期')` = 上年本期值）。变异：恢复忽略期间 ⇒ 上期用例红

- [ ] 7. `typed_eval_strictness` 收敛与三参读取走 ACNR（R7，ADR-FGR-06/07）
  - `WPExecutor` 两参 / 默认调用缺数报错；`formula_wp_semantics.py` 删差异维度；三参分支统一经 `acnr/wp_cell_target.py`
  - Verify: 四方一致用例（母 spec 需求 1.5 口径）无差异维度；契约测试断言不变。变异：恢复缺数返回 0 ⇒ 用例红

## 批 5　底稿有效定义

- [ ] 8. 全轨读有效定义与旧保存路径（R5，ADR-FGR-08）
  - `effective_cell_formulas`；coordinator `_load_formulas` 与 Tier A 预设改调；`wp_formula_service.save` 经同步内核；直写 `wp_formula` 守卫
  - Verify: 三路径同表达式用例；旧保存路径版本与待确认用例；回滚事务 PG（【测试】项目全局改一条底稿公式后运行时读到新定义）。变异：coordinator 恢复只读 `wp_formula` ⇒ 用例红

- [ ] 9. R6 处置（ADR-FGR-09，design §5 D4）
  - 用户同意移交 ⇒ 本任务标「移交 S9」并在 design 记录；不同意 ⇒ 按 S9 design ADR-ISL-01 实施并补对应用例

- [ ] 10. 收尾
  - 每批的回归与变异记录汇总；浏览器（chrome-devtools，【测试】项目）：公式编辑框对 `%`、`PRIOR`、多余参数的提示，报表 trace 对失败行显示原因；截图放 `tmp_formula_grammar/screenshots/`，用完停 about:blank
  - INDEX.md 本行与 memory.md 任务状态
  - Verify: 只候选红 = 0；推送带版本号与主要变动
