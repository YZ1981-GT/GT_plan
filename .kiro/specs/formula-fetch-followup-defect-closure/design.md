# 取数口径后续缺陷收口 —— 设计

> 现状均为 2026-10-24 现读代码与真库只读现查。行号会漂，锚点用函数名 / 常量名 / 键名。

## 1. R1 映射表科目码

**根因**：`wp_account_mapping.json`（1025 条，非 memory 记的 206 条）J / L / M 的码按旧编码整体错位，四表口径单一来源
（`four_table/m_cycle_specs`、`l_cycle_specs`、`j_cycle_account_scope`、`k_cycle_specs`，均已逐项真库对账）是对的。
真库 `account_chart`：client 侧 4001 实收资本 / 4002 资本公积 / 4003 其他综合收益 / 4101 盈余公积 / 4103 本年利润 /
4104 利润分配 / 4201 库存股 / 4301 专项储备 / 4401 其他权益工具；1124 / 1911 / 2261 / 2611 / 4102 / 4501 全库不存在；
2705 长期应付职工薪酬（8 项目）。standard 侧同码另有成本类名（4001 生产成本、4101 制造费用、4301 研发支出、4401 工程施工），
即「两套 4xxx」在数据里也并存 —— 取数按名定位、客户科目表优先（`semantic_account_resolver`）是既有正确设计。

| 族 | 现码 | 改为 | 依据 |
|---|---|---|---|
| J2（8 条） | 2611 | 2705 | `J2_GROSS_FALLBACK` |
| J3（8 条） | 2711（L6 专项应付款） | 空 | 股份支付没有独立科目（应付职工薪酬 / 资本公积入账），宁缺勿造 |
| L7（5 条） | 2801（K5 预计负债） | 空 | `L7_SPEC` 兜底码空 |
| M3（6） / M4（8） / M5（6） / M7（6） / M9（8） / M10（6） | 4002 / 4101 / 4103 / 4201 / 4401 / 4501 | 4201 / 4002 / 4101 / 4301 / 4003 / 4401 | `M_CYCLE_SPECS` |
| M8（6 条） | 4301 | 空 | `M8_SPEC` 兜底码空 |
| K4（5 条） | 2261 | 空 | `k_cycle_specs.K4.fallback_standard=""` |
| D5 | 1124 | 空 | 全库无 1124，`d_cycle_specs` 不给兜底码 |

- 工具：扩展既有幂等修正脚本 `scripts/fix/fix_wp_account_mapping_wrong_codes.py`（`FIXES` 逐条写原值 / 新值 / 依据，`--check/--dry-run/--apply`），
  勘误文档 `docs/reference/wp-account-mapping-errata-2026-09-28.md` 追加一节。改前跑全表探针：每个码 ∈ 标准科目表 ∪ 真库科目表 ∪ 口径单一来源。
- `report_row`：现查 99 条有值条目只有 18 条与 `report_config` 行名一致（旧编号体系），同一行次编码在两套准则下含义不同 ⇒ 单值字段本身表达不了，
  本轮不改值、登记勘误；同族的 I5（1901）、F2-55~58（1412）、H6 / H8 / H9 / I1 字母后缀与错码一并按单一来源修正（共 19 族 109 项）。
- 4xxx 写死码统一到单一来源（前端 `useM3FormData` / `useM7FormData` / `M7TabDisclosure*` / `useM9FormData` / `useM10FormData` /
  `useM10Adjudication`，后端 `m3_treasury_stock_service`、M9 路由 `Field("4103")`、`phase5_m3`（4102）、`phase5_m9`、`equity_method_service`
  标签与 M 路由文档），每处改前读用途。
- 派生物：补 `scripts/gen/gen_account_to_wp_ts.py`（`--check`，`accountToWpMapping.ts` 头注释指向的生成器不存在）；重生成
  `note_template_bindings.json`（diff 逐条解释）、`formula_push_coverage.json`。
- 读取方行为变化即修正（`chain_orchestrator` 按科目触发生成：M5 不再被本年利润触发、J2 / M10 可被触发、L7 / M8 不再按科目触发；
  调整影响 / 一致性 / 报表过期标记 / 地址库标签随之改正），逐个在测试里钉住。
- 守卫 `test_wp_account_mapping_single_source.py`：码形态、码存在性、与单一来源一致（偏差逐条登记原因，只许减少，失效条目打红）。

## 2. R2 初次预填三参 PREV 定位表

**现状**：`prefill_workpaper_xlsx` 只读每个 wp_code 的第一块映射；三参 PREV 没有取值分支（隐式跳过）。定位靠列头关键词
（`_find_column_by_keyword` 的「上年审定数」= 列头含「上年」或「审定数」任一 + 第 7 行起第一个数据行），91 格里 76 格落到
「比较 / 本期」列、无一落在正确的合计格。模板扫描：正确目标 91 格中 85 格是模板公式（如 D1 `E18 =SUM(E16:E17)`、H10 `J15 =SUM(J6:J14)`），
即上年审定数已由模板按期初 / 上期列计算；写值会破坏公式链。

**设计**：
- 定位表 `backend/data/prev3_prefill_locator.json`：`entries[wp_code][映射 sheet][cell_ref] = {prev, template, cell, header, row_label, cell_is_formula, action, reason}`，
  `action ∈ {write, verify, none}`；`template_sha256` 记模板指纹。生成器 `backend/scripts/gen/gen_prev3_prefill_locator.py`（扫模板：合并单元格展开列头路径，
  上年 / 期初 / 上期列且不含 比较 / 变动 / 差异；合计行按行标签；歧义格由 `MANUAL` 表人工裁定并写原因），输出幂等、`--check` 漂移 exit 2。
- 初次预填：路由 `get_workpaper_xlsx`（异步，已读审计年度）用 `PriorWpFieldResolver` 解析该底稿第一块的三参格，传给
  `prefill_workpaper_xlsx(prev_values=...)`；`write` 格写值（标记 + 批注写来源），`verify` 格只加批注「上年同底稿审定数 X（来源…）；本格为模板公式，未改写」，
  取不到的写原因批注、不写 0；`none` 不动。
- 重新预填 `locate_cell` 对三参 PREV 公式位查定位表（命中即用确切坐标，`verify` 与原规则一样不覆盖公式）。
- 守卫：映射三参格 ↔ 定位表一一对应；目标格存在；列头语义；公式标记与模板一致；`--check`；变异（改坏坐标 / 动作 / 漏条目）打红。

## 3. R3 陈旧测试

两个文件的旧前提来自已删函数（`2638b32fd` 删 `_resolve_prev_formula` 等 408 行）。改写：断言 `PriorWpFieldResolver` 在上年来源四种情形下的值 / 原因、
`PREV('D1','审定表D1-1')` 两参按「科目, 列」报列名无法识别、K8~K13 期初余额三参取 `TB('66xx','本期发生额')` 在上年数据上的值且无上年数据时报原因；
保留仍成立的守卫（锚点 SQL 对真实 schema 有效、预填不读 `cells` 键等），对已删函数的抽取断言删除并在文件头写明。

## 4. R4 鉴权

- 地址库 `routers/address_registry.py`：GET 搜索 / 统计 / 解析挂 `require_project_access("readonly")`（内层依赖与端点同名 `project_id` 查询参数，
  非 UUID 即 422）；POST 校验首句 `assert_project_permission(..., "readonly")`；POST 失效：`all=true` 只许管理员，否则校验项目只读；
  `jump` / `parse` 是不读库的纯函数，保持仅登录并在基线测试里登记理由。🔴 该文件有并发会话未提交改动（搜索端点工作线程编码），只动依赖签名，
  提交时只提交本 spec 的改动块。
- `routers/wp_template.py`：`/working-papers/generate`、`generate-from-codes`、新建自定义底稿三端点挂 `require_project_access("edit")`
  （编制类；`ROLE_MAP` 现读：合伙人 / 经理 / 审计员 / 助理 = edit，质控 / EQCR = review）。前端入口按项目权限隐藏或禁用（沿用现有权限组合函数）。
- `routers/wp_template_list.py` 模板清单校验项目只读。
- `ai_chat/mcp_tools.py`、`ai_chat/address_mention.py`：口径取附注渲染同一权威（`DisclosureEngine._get_active_template_type` 归一为 soe / listed），
  年度取项目审计年度（年度 0 时试算表域恒空）。
- 基线：`test_project_endpoint_authorization_baseline.py` 的 `_IDENTITY_ONLY_BASELINE` 与前缀维、`test_project_endpoint_authz_body_carried.py` 的
  `_BODY_IDENTITY_ONLY_BASELINE` 按现算下调，新端点进 `_FIXED_ENDPOINTS`；端点测试用真实判定链（override `get_current_user` / `get_db`，不 override 工厂）。

## 5. R5 引用校验

**现状**：`acnr/resolver.full_resolve` 对 TB / ROW / SUM_ROW / SUM_TB / REPORT / NOTE / AUX 开头的输入走 `_delegate_v1`，只做语法解析就 `found=True`
（复合表达式取第一个引用）；前端 `addressRegistry.validate` 见 ACNR `found` 即判有效，不再走数据校验。数据校验 `validate_formula_refs` 本身也不准：
附注只登记模板「合计」行、报表登记全部准则全部项目的行、试算表只认精确码（求值按前缀）。附注公式保存接口不校验引用；附注公式执行器的 NOTE
分支忽略行名一律取合计。四个求值器对 NOTE 的口径不同，只有严格路径（`formula_ref_preload._note_cell`）按章节 / 行 / 列精确取数。

**设计**：
- 新模块 `services/formula_ref_check.py`：按项目、年度、口径判定单个引用是否存在 —— TB / SUM_TB / 两参 PREV：本年试算表有该码或其下级（与预载前缀口径一致）且列名已注册；
  ROW / SUM_ROW / REPORT：本项目适用准则（含项目层）的报表配置有该行、期间可识别；NOTE：本年度附注有该章节，按 `_note_tables` / `_note_rows` / `_note_column`
  结构匹配（只看结构，不要求单元格有值），本年度附注尚未生成时按附注模板（章节 + 行名 + 表头）；AUX / WP 沿用现有判定。请求内缓存。
- `validate_formula_refs` 的 tb / report / note 判定改调该模块（两处校验同一口径）。
- `full_resolve` 非底稿域：不是单个完整引用 ⇒ `found=False, error="not_single_reference"`；有项目上下文 ⇒ 按该模块判定；没有 ⇒ `found=False, error="project_context_required"`。
  只为建立引用身份的内部调用方（附注执行器 `_resolve_cross_refs_via_acnr` 等）显式传 `verify_existence=False`，结果字段 `verified` 如实标注。GET `/api/acnr/resolve` 增可选 `project_id`。
- 附注公式保存 `upsert_note_formulas`：保存前逐条校验跨表引用，悬空 ⇒ 422 `FORMULA_REF_NOT_FOUND`（列出单元格、引用、原因），不写库。
- 附注执行器 NOTE 分支改按 `_note_cell` 口径取行 / 列（含 2 参、参数间空格）。
- 前端：`addressRegistry.validate` 只对单个 `WP(` 引用用 ACNR 短路，其余一律走数据校验；`useAcnr` 解析带项目上下文；`GtFormulaEditDialog` 等按 `found` 拦截的调用方改走数据校验或带项目。

## 6. R6 推错数的规则

- **F2**：`NoteDirectBinding` 支持备抵科目（1461 及 TB 科目名含「进销差价 / 跌价准备 / 减值准备」者）按减项；F2 附注主表规则字段改为六字段
  （`end_balance / end_provision / end_book_value / prior_*`，与 D1 同写法），只写合计行（账面余额 = 原值科目合计、跌价准备 = 备抵合计、账面价值 = 差）。
- **K4 / D5**：照 I5 先例改无科目声明（`account_codes=()` + 原因），删 `K4.tb_amount` / `K4.note.main` / `D5.tb_amount` / `D5.note.main`，删 `KNOWN_ACCOUNT_DEVIATIONS` 两条。
- **审定表族审定合计**：现状 26 个动态行规格读 `{X}-1-rows` + 扁平 `-unadj/-aje/-rje` 键，只有 K2 前端是这种存法；其余全部读空，真库 G / H / I 审定合计全是 `'0'`。
  新模块 `bindings/balance_adj_extract.py` 逐底稿声明真实来源（现读前端组合函数确认）：优先前端已持久化的合计键（如 `H8-1-net-audited`、`I1-adj-audited-net`），
  否则按行清单 + 区块符号（原值 + / 备抵 −，跳过小计行，行金额取 `audited` 或 `未审 + 调整`）；来源读不到 ⇒ 不写（写空），不写假的 0。
- **H1 / I1 附注主表**：按账面价值（原值 − 累计折旧 / 摊销 − 减值准备）出行，行名对齐两种准则附注模板（真库 dry-run 逐地址核对）。
- **报表**：BS-037 公式置空；BS-028 = 1601 − 1602 − 1603 + 1606、BS-032 = 1701 − 1702 − 1703（四个准则，改前查各准则是否另有「固定资产清理」行）。
  经 `publish_global(domain="report", source="seed")` 发布（版本 +1、跟随全局的项目行随之更新、项目改过的行进待确认），脚本 `--dry-run/--apply` 幂等；
  种子与生成器同步；`fill_all_formulas` 的按名回填对这些行拦截。
- 改动后对和平 2025 / 安徽 2025 跑推送 dry-run，逐地址对比改动前后。

## 7. R7 底稿求值器

`_COLUMN_MAP` 只许真实列（守卫钉死），故新增派生列表 `_DERIVED_COLUMNS = {"本期发生额": 审定数 − 期初余额}`，在 `_resolve_tb` / `_resolve_sum_tb` 查表前处理；
删 `_period_amount` 死分支；列名不在 `COLUMN_ALIASES` ⇒ 记入 `errors`（与 L1 `FormulaColumnError` 同口径）。改前全量扫描经底稿求值器求值的预设列名，有未注册的先改预设。

## 8. R8 业务分类

`is_template_applicable` 以参考标准为单一来源：C 排除 `C.excluded_templates`；B 排除新增的 `B.excluded_templates = ["A26"]`（参考标准「专委会不强制」）；
映射表 `applicable_categories` 标注仍生效（A17 族）；清单编码按族匹配（`code == E or code.startswith(E + "-")`）。`review_workflow_service` 改用 `get_category_prefix`。

## 9. R9 删除模板

`TemplateEngine.delete_template`：被引用判断改为按底稿编码精确匹配；`template.is_deleted = True` + 更新时间；端点改为只许管理员（与同文件模板管理端点一致，改前现读）。

## 10. 实施记录与偏离（2026-10-24）

### 10.1 R6 推错数的规则

- **F2（R6.1）**：取试算表 1401~1499 全部行（与报表 BS-010 同区间），按科目名归类（单一来源 `classify_f2_category`）：
  跌价准备 / 减值准备取绝对值计入跌价准备列，商品进销差价取绝对值从账面余额中减去，其余计入账面余额，账面价值 = 差；
  只写「存货分类」合计行（按行名「合计」唯一对上），明细行由底稿同步；删 `F2.note.subtable_0`（跌价准备变动表没有取数行，
  原先被兜底写进存货原值合计）。
  - **偏离 §6**：字段名用 `end_gross / end_impairment / end_net / prior_*`（真库底稿同步写入「存货分类」的列键，
    `_sub_table_columns['存货分类']`），不用设计里 D1 写法 `end_balance / end_provision / end_book_value` —— 那套键读取方对不上列。
  - **旧格式表**（`_tables` + values 列）六个字段认不出列 ⇒ 逐格跳过，原因写明哪一列、为什么不按位置猜
    （`engine.SPLIT_FIELD_LABELS`；原先只写「附注表缺少「期末」列」，而表里有期末列）。按表头认列属另一 spec
    `consol-note-header-library-and-node-reaggregate` R5.3（该 spec 写明需先与用户确认），本 spec 不动 `note_writer`。
- **K4 / D5（R6.2）**：无科目声明；K4 只剩审定合计两条规则，D5 无规则，`KNOWN_ACCOUNT_DEVIATIONS` 只剩 D4。
- **审定表族（R6.3）**：`bindings/balance_adj_extract.AUDITED_SOURCES` 逐底稿声明 G1~G10（无 G7）/ H1~H10 / I1~I5 / K7 的真实来源
  （行清单 / 合计键 / 按模式 / 不可取）；读不出 ⇒ None ⇒ 派生目标写空，不写 0。H1 / I1 披露 builder 净值读不出返回 None。
  推送面板算式说明与规则清单 62 条文案由声明生成（中文字段名、按模式分支写模式名）。
- **报表（R6.4）**：脚本 `scripts/fix/fix_report_bs_book_value_formulas.py`（默认预览只读；`--apply --backup <文件>` 先四个准则
  全部校验行名与版本、再留底、再逐准则 `publish_global(source="seed")`、再按项目审计年度传播；每个准则固定 request_id，重跑不再发布）。
  - BS-028 四个准则 = 1601 − 1602 − 1603 + 1606（各准则都没有单列「固定资产清理」行，现查）；BS-032 = 1701 − 1702 − 1703；
    BS-037 公式置空（登记进 `DERIVED_ROWS_WITHOUT_ACCOUNT`，移出零命中白名单）。
  - 同步：`report_formula_service._BS_SPECIAL`（固定资产 / 无形资产同上，删「其他非流动资产→1901」）、`_NAME_TO_ACCOUNT`
    删「其他非流动资产→1901」、按名拦截集合加「其他非流动资产」、`multi_standard_report_formats.json` 的 CAS 两行、
    `scripts/gen/generate_report_seed.py` 三行；新增守卫「置空的派生行必须同时按行名拦住」（原先删掉按名拦截条目零测试打红，变异实测）。
  - **H6 层③关闭**：BS-028 是固定资产行、不是 H6 自己的行；单槽规格允许层③时，客户科目表里没有叫「固定资产清理」的科目就会把
    1601 / 1602 / 1603（补齐后还有 1606）一并当清理科目（对照用例实测）。`H6_ACCOUNT_SPEC.trust_report_config=False`。
    补齐 BS-028 同时消掉 H1 减值准备槽、H6 清理槽恒报的「报表公式与科目不一致」假冲突。
  - `tests/fixtures/consol_report_config_snapshot.json` 保持冻结：它是 2026-09-30 真库快照，用例测的是分解与种子机制，与当前公式无关。
  - **已在真库发布**（2026-10-24）：publish_id soe_consolidated `17b5d68d…` / soe_standalone `bb8ece06…` / listed_consolidated
    `c2916c3f…` / listed_standalone `019af23f…`，各公式位 v1→v2，无冲突、无待确认；跟随全局的项目副本（和平 2024）随之更新。
    留底 `C:\Users\Administrator\gt_data_backups\formula-fetch-followup-R6.4\backup_report_bs_20261024.json`
    （report_config 15 行 + 资产负债表 financial_report 973 行，`row_to_json` 原文）。
  - 传播结果：9 个有报表的项目重算 5~7 行、失败 0。金额只在报表本就落后于现试算表的项目变：和平 2025 BS-028
    148,536,020.26 → 18,857,032.69、BS-032 16,943,075.40 → 2,418,592.54（BS-038 / BS-039 随之）；陕西华氏 BS-032
    485,423.82 → 0.00；另两项目原已标过期的 BS-053（V144 置空）重算为 0。其余项目金额不变（1603 / 1703 全库为 0，1606 原已含在国企单体公式里）。
    这两个项目的报表发布前就与试算表不一致（资产总计 ≠ 负债和所有者权益总计），内核只重算受影响的行，整张报表需在报表页重新生成。
  - 脚本在独立进程里发布：正在运行的后端进程内「谁引用了该单元格」反向索引缓存要等下一次公式发布或重启才刷新（只影响 linkage 查询展示）。
- **推送 dry-run（R6.5）**：见 tasks 2.6 证据。

### 10.2 测试基础设施（同类修复）

共享连接池（`app.core.database` 的 `engine` / `async_engine` / `async_session`）绑在建连时的事件循环上，`asyncio.run` 退出不释放，
同进程下一个 `asyncio.run` 的真库用例报 `Event loop is closed`（全量跑公式推送 K2 canary 即因此红，单跑全绿）。全仓 AST 扫描同类 12 个文件：
4 个在用完的 `finally` 里 `engine.dispose()`，8 个改 `asyncio.run(run_and_dispose(...))`（`tests/_pg_shared_engine.py`）；
守卫 `test_pg_tests_dispose_shared_engine.py`（AST 判定，注释 / 文档字符串不算；只把 `get_db` 当依赖覆盖键的不在此列）。
修后原先被前一个文件连带 skip 的 5 个真库用例真正跑起来并通过。`test_x3_roundtrip_live.py` 会写真库非测试项目，未实跑。

### 10.3 范围外发现（登记，未改）

1. **同类报表公式**（全局、四个准则写法不一，需用户拍板；金额为 2026-10-24 全库审定数绝对值合计）：
   - BS-006 应收账款：上市单体减 1231 整科目、国企单体减 1231-02、两个合并口径不减（1231-02 坏账准备 5 个项目 2.15 亿）；
     BS-005 应收票据只国企单体减 1231-01（116 万）；BS-009 其他应收款只国企单体减 1231-03（938 万）。
   - BS-010 存货：只有上市单体减 1416，其余三个准则不减（1416 / 1461 跌价准备 4 个项目 598 万）。
   - BS-024 长期股权投资四个准则都不减 1512 减值准备（2 个项目 763 万）。
   - BS-027 投资性房地产：上市单体减 1525 / 1526、国企单体只减 1525、合并口径都不减（1525 844 万、1526 48 万）。
   - BS-029 在建工程四个准则都不含 1605 工程物资（现行报表格式工程物资并入在建工程行）；BS-030 生产性生物资产不减累计折旧；
     BS-011 合同资产、BS-021 债权投资、BS-023 长期应收款、BS-034 商誉均不减各自减值准备（这些科目全库当前为 0）。
2. **公式推送真库跳过棘轮** `test_formula_push_note_skip_pg` 自 `8798e92fd`（2026-10-22 新增 153 条子表推送规则）起红：
   安徽跳过 74 → 311（章节不符类 13 → 155、找不到行类 2 → 96），棘轮 85。本 spec 改动后 299 → 262，仍超棘轮。
3. **其余单槽规格的层③隐患**（与 H6 同类，报表行不是本槽自己的行或跨准则行次错位）：J2 → BS-093 = TB('2711')（2711 是专项应付款）、
   M1 → 国企 BS-055 = TB('2001')（短期借款）、G12 → IS-014 = TB('6113')（槽兜底码 6103）。
4. `scripts/gen/generate_report_seed.py` 已过期：现 `report_config_seed.json` 是另一套编号的模板结构种子（公式为空），重跑生成器会覆盖它。
5. 既有红（HEAD 干净检出同样红）：`test_report_config_account_integrity` 6 条（行次编码各准则不一致）、`test_wp_templates_readonly` 3 条、
   H 循环 72 条（导入导出登记 / H0 预设 / 迁移进度等）。
6. **其他综合收益报表公式仍按 3102 取数**：IS-030（四个准则）、国企 IS-053、BS-115、BS-126，以及 `report_formula_service.py` 的名称→科目码表
   （3102 其他综合收益、4102 一般风险准备）。实证：和平药房 2024 其他综合收益记在 3102（12,989,000），2025 记在 4003；医疗器械 2025 4003 有 791,000；
   和平物流 2025 3102 期初 619,000 —— 两种口径在真库并存，改公式会改变已出具报表的取数，需用户拍板。
7. `report_line_mapping_service._determine_report_type_from_code` 仍按旧科目表把 4xxx 判为利润表；`financial_ratio_service` 引用的行码
   （BS-019 / 040 / 059 / 079、PL-xxx）与现行报表配置不符。
8. `M9 /tb-writeback` 端点直写试算表、绕过显式发布门，前端无调用方（是否删除需拍板）。
9. G 循环 1501 拆分：G1 旧口径写 1501（应为 1101）、G4 1501 与 1504 新旧准则并存、G11 / G13 选项含 1501，大量测试按 1501 断言。
10. I 循环组合函数仍以旧码驱动取数 / 发布 / 调整码：I2 `1717`（真实库无此码，真源 1704）、I5 `1911`（其他非流动资产无标准独立码）、
    I6 `6602`（管理费用，真源 6604；`i6Integration.spec` 断言发布 6602）。发布目标一改就改变试算表落点，需拍板；现冻结为棘轮（§10.4）。
11. D5 带入调整 `1124`（应收款项融资无标准独立码、映射表为空；D 循环另有会话在改）。
12. 后端公式说明目录（`wp_surfaced_*.py`）其余错码：G1-1 / G4-1 `1501`、H2-1 `1604 / 1605` 并列、H3-1 `1503/1504/1505`（投资性房地产应为 1521）、
    H8-1 `TB('1901')`、H9-1 `TB('2205')`、I2-1 `1717`、I6-1 `6602`、K1-12 `TB('1901')`（只读展示，随第 9、10 条一起定）。
13. K1-4 调整表把所有 `1231*` 算作 K1 坏账（`useK1Adjustment.isBadDebtAccount`、中央同步前缀含 1231）：会把应收账款的坏账调整（1231-02）
    拉进 K1-4 并回写 K1-1。改它要把项目口径穿进 3 个以上组合函数，且对不分子目的客户会让分录消失，需定口径。
14. **L7 发布用报表行 BS-071 当科目码**：`tb_audited_writer.publish_rows` 只按 `standard_account_code` 精确匹配，BS-071 永远找不到行 ⇒ 跳过并记日志，
    而发布端点按载荷行数回「已发布 1 个科目」（假成功）。同根问题是全平台的：事件处理器跳过某科目时，端点仍报成功。
    L7 是否应像 K4 那样「无科目即禁用发布」需拍板。
15. **账套识别规则 JSON 从未加载**：`ledger_import/identifier._RULES_FILE = parents[4] / "data" / ...` 落在仓库根 `data/`（文件在 `backend/data/`），
    `reload_rules` 读不到就静默用内置默认（日志 debug 级）。而该 JSON（v2.1）已比内置旧：`column_aliases` 缺 `aux_dimensions`、`aux_type` 多一个「核算类型」，
    且 `_rebuild_aliases` 是整表替换 ⇒ 直接改路径会让辅助核算维度列识别退化。需先定：同步 JSON 后改路径，还是删 JSON、内置为唯一来源
    （`tests/ledger_import/test_balance_annual_semantics.py` 文件头把该 JSON 列为真源之一，与实际不符）。守卫 `test_data_file_paths_resolve.py` 已登记。
16. **BS-010 存货区间 `SUM_TB('1401~1499')` 含非存货科目**：1481 / 1482 持有待售资产（有独立报表行）、1471 合同取得成本（列示于其他流动资产 /
    其他非流动资产）都在区间内；`f2_extraction.category_rules` 也把合同取得成本归入存货的合同成本类。改报表公式与归类规则需拍板（与第 1 条同批）。
17. **底稿一致性检查把备抵科目按正数相加**：`consistency_check_service.update_workpaper_consistency` 对映射码的试算表审定数直接求和（H1 = 原值 + 累计折旧 +
    减值准备）。当前真库只有 1 张底稿（B22A）带 `parsed_data.audited_amount`，影响面为 0；接入前需按单一来源的账面价值口径取数。
18. `WpMappingService.recommend_workpapers` 合并报表追加项写死 `B12 集团审计计划`（映射表 B12 是「与相关人员访谈程序及记录」，集团审计是 B30 / A3）；
    前端 `getWpRecommendations` 无调用方。
19. **映射表 `note_section` 与附注模板绑定生成**（R1.5 的 `note_template_bindings.json` 因此未重生成，需拍板）：
    - `note_section` 是旧的上市口径编号且多族共用：五、19 同时挂 J1 应付职工薪酬 / G8 其他权益工具投资 / H8 使用权资产，五、34 挂 H9 租赁负债 / I6 研发费用，
      五、12 挂 G4 / H3 / I1……而现行上市模板五、12 是一年内到期的非流动资产、五、14 是债权投资、五、34 是交易性金融负债。与 `report_row` 同类，单值字段表达不了。
    - 生成器 `scripts/generate_note_template_bindings.py` 把同一章节号下所有条目的科目并集发给该节**每一个**数据行（存货节「原材料 / 在产品 / 库存商品」
      各行都按整个存货族求和）。
    - 隔离实验（同模板、同生成器，只换映射表：基线 `88b5d2cca` vs 现状）：映射改动影响 5 节 289 格（五、14 1503→1506 150 格、五、9 存货族 +13 码 100 格、
      五、34 2802→2601+2651 20 格、五、12 1703B→1703 10 格、五、19 9 格）；模板陈旧另有 34 增 8 删（国企八、14 / 31 / 53 …），与映射无关。
      五、34 交易性金融负债、五、12 一年内到期的非流动资产原先挂的是不存在的码（取 0），重生成后会把租赁负债、无形资产减值准备真实取进来 —— 比不重生成更坏。
    - 真库 disclosure_notes 目前全是国企口径（八、xx），映射表没有八、编号，国企附注绑定不取映射码，现网影响为 0。
    - 建议：`note_section` 按准则分列并对齐四版 Word 模板（或生成时按科目名与模板章节名关联），生成器按行级科目绑定；在此之前不重生成。

### 10.4 R1.4 科目码单一来源（含触类旁通，2026-10-24）

**M 循环（股东权益，4xxx）**

- 前端 `mCycleAccountScope.ts`：M1~M10 码、显示名、`isOwnMSource`（溯源槽名 = 本循环科目名才采用，防嵌入宿主注入别的循环的溯源）、
  `mAccountCodeOf` / `mPublishBlockReason`（M8 一般风险准备没有统一标准码：定位不到或多码时拦发布，不换成别的科目）、`OCI_ACCOUNT_CODE`（4003）。
  M1~M10 组合函数 / 页签 / 主入口的字面量全部换成常量；错码文案改正（M3 4002→4201、M7 4201→4301、M9 4103→4003、M10 4003→4401，M8 去掉 4104）。
- G 循环其他综合收益统一取 `OCI_ACCOUNT_CODE`（G8 / G9 / G12 / G14 的选项、认领前缀、配对、净额）。
- `useAuditData` 按 2006 科目表分类（3xxx / 5xxx 资产与成本、4xxx 权益、6xxx 损益），借方类含 5xxx 与 4201 库存股；`WorkpaperSummary` 权益选项改 4xxx。
- 后端 `four_table/m_cycle_specs.py` 增 `fallback_code_of` / `row_code_of`；M1~M10 render 策略（M8 除外）、M3 / M4 / M5 服务、M9 `TBWritebackRequest`
  缺省值、J3 `account_codes` 改取单一来源；新增行码 M4 BS-083 / M5 BS-087 / M7 BS-086 / M9 BS-085。phase5 m3 / m8 / m9 / m10 的 `ACCOUNT_CODE`
  保留字面量、由测试与 `fallback_code_of` 交叉核对（不在 workpaper_sync 里引 four_table，避免 import 闭包与 golden 摘要变动）。
- 冻结的 `reviewed_basis` 文案（phase5_m3「4102 库存股」、phase5_m10「4001 其他权益工具」）不改：改它要重生成契约与 golden 摘要，登记在 `_PAIR_ALLOWLIST`。

**触类旁通：真源已声明错码的循环（J2 / K1 / K2 / K4 / K5 / L3 / L6 / L7）**

起因：这些循环的 `*AccountScope.ts` 早已写明「哪个码是错的」并注「守卫用」，但没有任何守卫扫源码（`L6_WRONG_LEGACY_ACCOUNT` /
`J2_WRONG_LEGACY_ACCOUNTS` 只断言了常量值本身）；既有 `k5AccountCodeNoHardcode` 只扫 `k5/` 目录，漏了组合函数。

- J2 带入调整按 2221（应交税费）拉分录 → `j2GrossQueryCodes` / `j2AccountCode`（缺省 2705）。
- L6 带入调整按 2601（租赁负债）→ `L6_GROSS_FALLBACK_STANDARD`（2711，与发布同源）。
- L7 带入调整按 2801（预计负债）→ 无专属科目码不拉取、按钮禁用；事件码沿用发布口径 `L7_REPORT_ROW_CODE`。
- L3「生成一年内到期重分类」的贷方写 2801（预计负债）：中央同步后记到预计负债上，K5 带入调整也会把它拉进去 → 科目码留空、按科目名同步
  （`AdjustmentSyncLineItem.standard_account_code` 允许空，服务层按名称解析）。
- K1 坏账准备的带入与发布用宽口径 1231（同时承载应收票据 / 应收账款的坏账，发布会用 K1 一家的金额覆盖该行）→ `k1ProvisionQueryCodes`
  （render 溯源 `provision_standard`，缺省 1231-03）；`useK1FormData.writebackTB` 改为由调用方传码，空码不发。
- K4：`writebackTB` 删除缺省值 2245（漏传科目时会写进别的科目）；`loadTbData` 改读后端真实下发的 `tb_values.liability_*`
  （原读从未下发的 `other_current_liabilities_2245_*` ⇒ 恒按 2245 取数）、解析不出科目不发请求；K4-3 新增分录 / 事件 / 推送的科目码改取本项目解析结果
  （缺省空，留待填写）；两个附注页签的事件归属改用共享 `isK4Event`（按 wpCode；空码不去匹配别人的事件，不再认 2245）；
  K4-1 的 `tbData` 形状与宿主对齐（宿主传 `{unadjusted, audited}`，K4-1 原声明 `{unadjusted2245, audited2245}`，单区域 vue-tsc 在 HEAD 报 TS2739，本次消除）。
- K5：发布后事件载荷写死 2701（长期应付款）→ 事件码 = 本次发布码（`publishAdjudicated(accountCode)`）；带入与提示改为取值函数（溯源晚到仍按最新口径）；
  删除 `provisions_2701_*` 旧键兼容（2026-08-03 后端已改名并标注一个月后删）。
- 文案（含 `?raw` 渲染给用户的手册、后端公式说明目录 `wp_surfaced_j / k / l` 的 J2 / K2 / K4 / K5 / L3 / L6 / L7 段）：J2 2221→2705、K5 2701→2801、
  L6 2601→2711、K2 1231→1901；K4 / L7 / L3 去掉科目码，改为「没有统一标准科目码，按本项目科目表定位」/「无专属科目码」/「报表项目，按名称同步」。
  标识符 L6 `ajeNet2601`→`ajeNet2711`、L7 `ajeNet2801`→`ajeNetAccount`。解释「为什么不是这个码」的注释保留原码。
- 范围说明：`k5NoteSectionMap.ts` 文件头注释仍写 `account_code: 2701`，该文件属附注子表并发会话的工作区，本次未动（注释不影响取数，守卫剔注释后不计）。

**守卫**

- 前端 `mCycleAccountCodes.spec.ts`（与后端规格对齐 / 无字面量 / 标识符 / 全前端名码配对）、`mCycleAccountRuntime.spec.ts`、`gCycleOciAccount.spec.ts`；
  后端 `four_table/test_m_cycle_account_single_source.py` 41 例。
- 前端 `cycleWrongLegacyAccountCodes.spec.ts` 51 例：①零容忍组（J2 / K2 / K4 / K5 / L3 / L6 / L7，错码取自真源导出，K4 / K5 本次补
  `K4_WRONG_LEGACY_ACCOUNTS` / `K5_WRONG_LEGACY_ACCOUNT`；文件集含 `src/composables/use{X}{n}*`；向用户解释的文案逐条登记且须恰好命中一行；
  后端说明目录该底稿段同查）；②棘轮组（G1 44 / I2 60 / I5 55 / I6 69，只许减少，基线比现扫多 5 以上打红）；③K1 坏账不得用宽口径；
  ④全前端带入调整的字面量码 ⊆ 该底稿映射科目（H5 1632 / L5 2702 为备抵科目；G1 / G4 1501、D5 1124 已登记）；
  ⑤运行态：K4 事件归属、K5 事件码 = 发布码、L7 带入按钮禁用。
- 变异：M 部分前端 22 条、后端 12 条；触类旁通 29 条（FB1~FB29，含后端说明目录 3 条）全部打红后逐字节恢复。
- 单区域 vue-tsc（本次改动的 .ts / .vue 及 K1 / K4 宿主共 193 个入口 + 传递依赖，独立 worktree 与 HEAD 同口径对比）：新增 0、消除 1（上面的 K4 TS2739）；
  注入 `const x: number = 'x'` 报 TS2322（变异证明）。
- 回归：前端相关 115 个测试文件 2306 通过；失败 15 例全部来自 4 个 HEAD 同样失败的文件（`j2NoteSubtableContract` 2、`k1FormulaPushHost` 3、
  `k1NoteSubtableContract` 8、`k4NoteSectionMap` 2，附注子表契约 / 保存键集合，属其他会话）。后端 M 相关集合失败 117 例与 HEAD 逐条一致。

### 10.5 R1.6 映射表守卫与读取方（2026-10-24）

**映射表**（第三 / 四批，勘误文档同名节）：G6 1503→1506、G8 1503→1507、K2 1701→1901；F2 子条目按条目名逐条对科目名
（原材料 / 在途物资改正，在产品 / 库存商品 / 委托加工物资 / 工程施工 / 开发产品置空，跌价准备 1461+1471→1416+1461，合同履约成本 1411→1472），
F2 族级条目列全区间族 19 码；E0-4 借款发函 → 2001+2501、E0-5 应付票据发函 → 2201。修正脚本改为按（底稿, 字段）串修正链，`--check` 183 项。

**守卫** `test_wp_account_mapping_single_source.py`（与推送 binding 守卫共用 `four_table/declared_codes.py`，避免两份判据分叉）：
码形态 / 静态存在 / 真库 `account_chart` 存在（现 104 个码全在）/ 族级 ⊆ 声明 ∪ 双族码（偏差逐码登记：D4 6051、F5 6402、I6 1704、F2 区间族）/
声明为空 ⇒ 映射为空（D5 / I5 / K4 / L7 / M8）/ 声明的原值码必在映射 / 函证族只许同循环声明码（E0 跨循环 3 码登记且须由登记的族声明）/
条目名含平台标准一级科目名 ⇒ 码必须相交（M 循环与 L8-5 / I2-4 登记）/ 修正脚本各批全部生效；植入错码自检 11 例。

**读取方**：
- 全链路生成底稿：开关码表与映射匹配拆为 `wp_generation_matching.py`（纯函数），has_lease / has_rd 改正（§10.4 之后的提交 `12ece3df4`），
  `test_wp_generation_matching.py` 26 组「科目 → 生成的底稿」字面量期望。
- 调整到达通知、底稿一键刷新：原先各自读 json 且静默失效（路径落在 `app/data/`、把 `{"mappings": [...]}` 当列表），改经 `wp_mapping_service`
  （`workpapers_for_account_codes` / `audit_sheet_account_codes`）；`test_wp_account_mapping_readers.py`（真 SQLite 通知 3 例 + 真库只读一键刷新 1 例）。
- 触类旁通：`test_data_file_paths_resolve.py` 把 `backend/app` 里能静态求值的数据文件路径（174 处）逐个算出来看文件在不在，3 处故意可缺并登记
  （其中账套识别规则见 §10.3 第 15 条）。
- 本 spec 早先提交留下的陈旧测试一并改正：`test_note_direct_integration`（D5 归无科目组、F2 不再逐码出行）、`test_note_direct_binding`（F2 区间族）。

**派生物（R1.5）**：
- 前端挂凭推荐表 `views/ledger/accountToWpMapping.ts`：补生成器 `scripts/gen/gen_account_to_wp_ts.py`（`--check` / `--write`，幂等）。原表是手写的，
  头注释指向的生成器从未存在。重生成 98 → 104 行：删 17 行错码（D5 1124、F2 1412、G6 1503、H6 1606B、K2 1701、H8 1901、K4 2261、J2 2611、J3 2711、
  H9 2802、M3~M10 错位一格），增 23 行（G6 1506、H8 1641 / 1651、H9 2601 / 2651、J2 2705、K2 1901、M 循环正确码、F2 区间族），改名 8 行
  （D6 1141 原标「其他应收款」实为合同资产、D7 2205 原标「其他应付款」实为合同负债等）。守卫：表 = 生成器按当前映射的输出 + 字面量抽样；
  M 循环名码配对守卫补 `{ prefix, wpCode, wpName }` 写法（原先只认 code / name 键，所以这张表的 M 段错位没被抓到）。
- `formula_push_coverage.json` 重生成：只变 F2 的 `account_prefixes`（6 → 19）。
- `note_template_bindings.json`：做了隔离实验但**未重生成**（§10.3 第 19 条），待拍板。

**偏离**：设计稿写「读取方行为变化逐个钉住」，实施时发现两处读取方根本没读到映射（不是「行为变化」而是「从未生效」），按缺陷修正并单独钉住；
R1.5 的附注模板绑定未重生成（理由见 §10.3 第 19 条）。

### 10.6 R7 / R8 / R9 复核（2026-10-24）

三项实现随提交 `25a506a57` 入库，本轮逐条核对代码与测试并补缺：

- R7：补常驻守卫「经底稿求值器求值的 Tier A 预设，TB / SUM_TB 列名全部已注册」（设计要求的「改前全量扫描」固化下来）。
- R8：复核模板另有一份适用性 —— `review_checklist_templates.json` 的 `a_only`（A24-1 质量复核合伙人、A25-1 EQCR 为 true）。改成按主分类前缀后，
  A 类子分类项目能拿到模板了，但 B 类仍拿不到，而参考标准写的是「B 类需项目质量复核合伙人（A24/A25 保留）」、C 类排除 A24-1 / A25-1。
  改为与底稿清单同一判定 `is_template_applicable`，删掉 `a_only`（模板与角色两处，已无读取方），旧用例「B / C 类都没有 QR / EQCR 模板」按参考标准改写。
  🔴 复核面板端点的业务分类由前端查询参数传入（缺省 C），前端 `WorkpaperReviewPanel` 当前无挂载点；是否改为服务端按项目读取需另定（未改）。
- R9：补端点级「被引用 ⇒ 400、模板仍在」用例。
