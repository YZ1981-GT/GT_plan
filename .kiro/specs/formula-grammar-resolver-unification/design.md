# 设计文档：S1　公式语法与取数器单一来源（formula-grammar-resolver-unification）

> 本 spec 量大（跨后端 L1、附注、底稿单元格三套求值器与前端校验器，触及约 20 个结果调用方），按批交付。
> 需求编号：requirements §1 八条依次记 R1（单一 registry 生成前后端函数表）、R2（多余参数报错）、R3（`value=None` 全量迁移）、R4（note / cell 求值器 float → Decimal）、R5（底稿公式全轨读有效定义，含旧保存路径）、R6（报表按依赖排序求值）、R7（`typed_eval_strictness` 收敛）、R8（L1「期间」与列名）；§4 的母 spec 任务 8 遗留 ②~⑤ 记 R9。
> 现状基线：分支 HEAD `4c0a1e0a6` + 母 spec 整合树 `tmp_fhic/integ`（`d91f5f804`，含 ADR-FHIC-01/02 失败语义与参数个数表、ADR-03 叶子口径、ADR-06 WP 读取、ADR-18/19）。数字为 2026-10-29 现算。

## 0. 结论

「平台支持哪些函数、各要几个参数」现在有四份互相不一致的表：母 spec 的 `formula_arity.ARITY`、L1 注册时的展示用 `arity=`、`formula_grammar.FORMULA_ARITY`、前端 `formulaSyntaxParser.ts`。而且附注执行器是另一套语法（`cell`、`SUM`、`PRIOR`、`AGING`、`REGION`），底稿单元格求值器又是一套（Excel 式坐标）。所以 R1 的「单一 registry」必须**按域**分：一份目录登记每个函数属于哪些求值器、参数个数、说明，后端三处与前端都从它生成或读取。其余各项按依赖顺序：先目录（R1、R9⑤）→ 参数个数上限（R2）→ 失败值改 `None`（R3，先迁调用方）→ 浮点改 Decimal 与除零（R4、R9④）→ 取数口径（R8、R9②③、R7）→ 底稿有效定义（R5）。R6 建议移交 S9（§5 D4）。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | R1：前端另有 `PRIOR`、`%` | `formulaSyntaxParser.ts` 的 `KNOWN_FUNCTIONS` 含 `PRIOR`，运算符含 `%`；L1 词法没有 `%`（`_AST_TOKEN_PATTERNS` 只有 `+ - * /` 与比较符，认不出的字符被 `finditer` 跳过）；`PRIOR` 不在 L1，但**是附注执行器的合法函数**（`PRIOR('科目','期末')`、`PRIOR('章节','行','期末')`） | 成立，且 `PRIOR` 是附注域函数，不能简单删 |
| 2 | （交接未列）参数个数表的份数 | 4 份：`formula_arity.ARITY`（母 spec，按处理器真实可取数写法定下限）；`_REGISTRY.register(arity=…)`（TB=2、AUX=3、NOTE=3、WP=2、PREV=2、ROUND=2、MAX=2、LEDGER=3、PLACEHOLDER=0…）；`formula_grammar.FORMULA_ARITY`（由注册元数据派生，WP / PREV 另写 `[2,3]`）；前端 `FUNCTION_ARITY`。前端与 `ARITY` 不一致的有 10 个：TB、SUM_TB、REPORT（三者前端都是 [2,2]，后端 1~2）、AUX（[2,3] vs 2~4）、ROUND（[2,2] vs 1~2）、MAX / MIN（[2,2] vs 2~不限）、LEDGER（[3,3] vs 2~3）、LEDGER_DETAIL（[3,3] vs 1~3）、PLACEHOLDER（[0,0] vs 0~1） | 新增：比交接多两份 |
| 3 | R2：只强制下限与 `IF` 上限 | 成立：`formula_arity.EVAL_UPPER_CHECKED = {"IF"}`；写入期 validator 上下限都查 | 成立 |
| 4 | R3：约 20 个 `Decimal` 运算调用方 | 母 spec ADR-01 的估计；`FormulaResult.value` 失败时仍是 `Decimal('0')`。精确清单要用 AST 跟数据流现算（§3 方法） | 成立，数字待现算 |
| 5 | R4：note / cell 求值器用 float | AST 现算 `float(` 调用：`note_formula_generator.py` 32 处（取数装载、回写、聚合，缺数多处 `else 0`；与评估报告数字一致）、`cell_formula_evaluator.py` 7 处，后者除零 `return 0.0  # 除零返回0`（母 spec 遗留 ④） | 成立 |
| 6 | R5：底稿公式没有全轨读有效定义 | `formula_settings/wp_effective.py` 自述「公式运行时与各循环 Tier A 预设只读 `wp_formula` 行，不读全局层」；`formula-global-settings-sync` 的交付勘误 S5：「底稿旧保存路径 `wp_formula_service.save` 接入同步内核暂缓」 | 成立 |
| 7 | R6：报表按行号求值 | 成立；S9 现状复核发现国企利润表小计行在明细之前，S9 必须先有拓扑序（见 S9 design ADR-ISL-01） | 建议移交 S9 |
| 8 | R7：`typed_eval_strictness` | 整合树 `formula_wp_semantics.py` 登记了该差异维度（typed_eval 与严格轨缺数 blocked，`WPExecutor` 两参与默认调用缺数 0） | 成立 |
| 9 | R8：L1「期间」与列名 | `_handle_report` 只取第一个参数、**忽略期间**（`REPORT('BS-002','上期')` 取的是本期）；`_handle_prev` 的列名在整合树已按列取并对未注册列报错 ⇒ 列名一项已由母 spec 修好 | 期间成立，列名已修 |
| 10 | R9：母 spec 任务 8 遗留 | ②`REPORT` 缺行按 0：成立（`row_cache.get(row_code, Decimal("0"))`）；③正则降级路径出错时 `value` 是部分结果：待现读定位；④cell 除零为 0：成立；⑤注册 `arity=` 未与 `ARITY` 统一：成立（第 2 行） | 成立 |
| 11 | 依赖：等 ACNR 接 `exact_identity.sheet_of` 后才有真实可接受键 | HEAD 的 `wp_cell_reader._catalog_sheet_keys` 仍恒为 `not_found`，且模块文档写明这是**有意设计**：ACNR 在 `services/acnr/wp_cell_target.py` 用锁定目录判身份后把目录 sheet 名传进来，读取函数不另读目录（ACNR design §2.4 R2-F7） | 交接假设已过时：三参读取改走 `wp_cell_target`，不等 `_catalog_sheet_keys` 填值 |

## 2. 架构裁定

**ADR-FGR-01 按域的函数目录是唯一来源（R1、R9⑤）。** 新模块 `backend/app/services/formula_function_catalog.py`：每个函数一条 `FunctionSpec(name, arity=(min, max|None), engines, category, syntax, description)`，`engines ⊆ {"l1", "note", "cell"}`（L1 = 报表 / 试算表明细 / 表间审核 / 中央执行 / 底稿公式 / 推送共用的内核；note = 附注执行器；cell = 底稿单元格求值器）；另登记各引擎支持的运算符。派生关系：`formula_arity.BUILTIN_FUNCTION_NAMES` / `ARITY` = `engines` 含 `l1` 的条目；`_REGISTRY.register(...)` 的 `arity` / `description` / `syntax` 从目录取（不再写字面量）；`formula_grammar.FORMULA_ARITY` 从目录派生；附注执行器的函数清单（`TB / REPORT / WP / NOTE / PRIOR / AGING / REGION / cell / SUM`）登记为 `note`。生成器 `backend/scripts/gen/gen_formula_function_catalog.py`（输出无时间戳，`--check` 比对，退出码 2 列出差异）写 `audit-platform/frontend/src/generated/formulaFunctionCatalog.ts`（先例：同目录的 `formulaPushOwnedKeys.ts`）。前端 `formulaSyntaxParser.ts` 删掉自带的 `KNOWN_FUNCTIONS` / `FUNCTION_ARITY` / 函数提示，按调用方传入的引擎（`l1` / `note` / `cell`）取函数集与运算符集；`PRIOR` 只在 `note` 引擎下合法，L1 下报「PRIOR 是附注公式函数，报表 / 底稿公式请用 PREV」；`%` 三个后端引擎都不支持，从前端运算符集删除（§5 D1）。守卫：目录与 `_REGISTRY` 内置键集合相等；生成文件 `--check` 无差异；前端源码不得再出现函数名字面量集合（vitest 源码守卫）。

**ADR-FGR-02 求值期也查参数个数上限（R2）。** `EVAL_UPPER_CHECKED` 删除，求值期上下限都查（`arity_problem(..., full=True)`）。切换前用目录对全部存量定义扫描多余参数：`report_config` 全部公式、`formula_push_rules.json`、`prefill_formula_mapping.json`、预设库、V199 `formula_setting`、`wp_formula`、`cross_account_rules.json`；有命中先列清单修数据（经同步内核发布），清单为空后再切；扫描脚本留作守卫（存量多余参数 = 0）。

**ADR-FGR-03 失败值改 `None`，先迁调用方（R3）。** 步骤：①AST 现算清单：`FormulaEngine.execute` / `execute_with_status`、`report_engine.evaluate_formula*`、`report_row_compute.compute_row`、中央执行等产出 `FormulaResult` 的函数，跟到使用 `.value` 做算术、比较、`quantize`、格式化的位置，逐个登记到 `tests/formula_grammar/value_none_callers.json`（文件、函数、用法、处理方式）；②逐个改为先判 `ok`（或 `value is None`）再用值，只读展示类改为显示「—」与原因；③把 `FormulaResult.value` 类型改为 `Decimal | None`，失败时为 `None`；④AST 守卫：清单内每处都有 `ok` / `is None` 判断，清单外新增的 `.value` 算术用法即红。前端调用方母 spec N2 已确认中央执行无生产调用；报表 trace、调试面板按 `null` 显示（实施时现读）。

**ADR-FGR-04 附注与单元格求值器 Decimal 化（R4、R9④）。** 附注执行器与其跨表装载（`_load_cross_table_data`）改用 `Decimal`，缺数不再 `else 0`，返回 `None` 并在结果里带原因（与 S2 的校对结果契约对接）；回写时量化到分存数字。单元格求值器 `_eval_node` 改 `Decimal`，除零 ⇒ 错误「除数为 0」（对应 Excel 的 `#DIV/0!`，§5 D3），缺数坐标不再代 `"0"`，返回错误「单元格 X 无数值」。两处都补「同一夹具在 L1 / 附注 / 单元格三引擎逐值相等」的用例（只覆盖三者共有的写法）。

**ADR-FGR-05 取数口径（R8、R9②③）。** `REPORT('行次','期间')`：期间认「本期 / 期末 / current」与「上期 / 期初 / prior」，上期值来自上年报表行（复用报表「上期」列的 `prior_year_context` 装载，预载进 `ctx.prior_row_cache`）；期间无法识别 ⇒ 错误；行不存在 ⇒ 错误「报表行不存在或未生成：X」（不再按 0）。正则降级路径（`_apply_regex_fallback` 一类，实施时现读定位）出错 ⇒ `ok=False`，不返回部分结果。

**ADR-FGR-06 `typed_eval_strictness` 收敛（R7）。** `WPExecutor.execute` 两参与默认调用在读取函数返回非 ok 时抛 `FormulaEvalError`（原因透传），不再返回 0；依赖 ADR-03 之后才不会让只读调用方崩。`formula_wp_semantics.py` 删掉该差异维度，守卫的精确相等断言同步更新。

**ADR-FGR-07 三参 WP 读取走 ACNR 的锁定目录（交接依赖更正）。** typed_eval、严格轨、`WPExecutor` 三参分支统一经 `services/acnr/wp_cell_target.py` 判 sheet 身份（锁定目录），再调 `resolve_wp_cell` 传目录 sheet 名；`_catalog_sheet_keys` 保持 ACNR 的设计不动。契约测试 `test_wp_cell_reader_contract.py` 不改断言（母 spec §8.2「后落地方不改」）。

**ADR-FGR-08 底稿公式全轨读有效定义（R5）。** 新函数 `formula_settings/wp_effective.py::effective_cell_formulas(db, project_id, wp_id)`（本项目 > 全局 > 系统预设，与预填同一优先级），公式运行时 coordinator 的 `_load_formulas` 与各循环 Tier A 预设入口改调它；`wp_formula_service.save` 改为经同步内核的项目层写入（`project_ops.save_overrides`，domain = wp），不再直写 `wp_formula`（实施时先现读 `WpStore` 的项目层存储形态，确认二者是同一张表时只改入口、不迁数据）。守卫：`backend/app` 内除 `WpStore` 与迁移脚本外不得直接 `INSERT` / `UPDATE wp_formula`；三条执行路径对同一单元格读到同一表达式的用例（母 spec P1-5 的验收口径）。

**ADR-FGR-09 R6 移交 S9（§5 D4）。** 若用户同意，本 spec 删去 R6，以 S9 的 `report_eval_order.py` 为准；不同意则把 S9 design ADR-ISL-01 原样作为本 spec 的一批。

## 3. 现算方法（实施第一步）

- 参数个数表差异：脚本 import 四份表逐函数对比，输出差异矩阵。
- R3 调用方：AST 找上述产出函数的调用结果变量（含解包、属性链、`RowOutcome` 转存），在同一函数内跟到 `.value` 的使用；跨函数传递的按「返回值类型标注为 `FormulaResult`」继续跟一层；结果存 `value_none_callers.json`。
- 存量多余参数：ADR-02 的数据源全扫，输出（来源、标识、函数、实参个数、上限）。
- float 用法：两个求值器模块 AST 统计 `float(` 调用与 `else 0` 兜底。

## 4. 测试与变异

- 目录：键集合守卫；生成 `--check`；前端源码守卫；`PRIOR` 在三引擎下的接受 / 拒绝。
- 参数个数：求值期多余参数 ⇒ `ok=False` 带原因（参数化全部内置函数）；存量扫描 = 0。
- `None`：清单守卫；每个改过的调用方一条失败输入用例（不再崩、显示原因）。
- Decimal：三引擎逐值相等；`0.1 + 0.2` 类精度用例；除零与缺数坐标报错。
- 取数口径：`REPORT` 本期 / 上期 / 缺行 / 坏期间；正则降级出错 ⇒ `ok=False`。
- 底稿有效定义：三路径同表达式；旧保存路径经同步内核后项目层版本 +1、待确认按同步规则出现。
- 磁盘变异：目录与 `_REGISTRY` 不同步（删一条）⇒ 键集合守卫红；`EVAL_UPPER_CHECKED` 恢复只含 IF ⇒ 多余参数用例红；任一登记调用方去掉 `ok` 判断 ⇒ 清单守卫红；除零恢复返回 0 ⇒ 除零用例红；`_handle_report` 恢复忽略期间 ⇒ 上期用例红；coordinator 恢复只读 `wp_formula` ⇒ 三路径用例红。

## 5. 待用户拍板

| # | 事项 | 建议 |
|---|---|---|
| D1 | 前端 `%` | 删除（三个后端引擎都不支持，现在写了也算不出） |
| D2 | `PRIOR` | 保留为附注域函数；L1 下给出改用 `PREV` 的提示 |
| D3 | 底稿单元格除零 | 报错（同 Excel `#DIV/0!`），不再显示 0 |
| D4 | R6 报表拓扑序 | 移交 S9（S9 必须先有它，且 S9 规模小、触发更早） |
| D5 | 实施方式 | 本 spec 跨模块多、调用方多，按 §2 顺序分 5 批提交（目录与参数个数 / None / Decimal / 取数口径与严格性 / 底稿有效定义），每批独立回归 |
