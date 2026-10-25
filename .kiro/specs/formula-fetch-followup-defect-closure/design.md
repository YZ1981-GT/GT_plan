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

### 10.7 R4 鉴权（2026-10-24）

- **地址库（R4.1）**：搜索 / 统计 / 解析挂 `require_project_access("readonly")`；校验 / 失效缓存的项目在请求体里，函数首句
  `assert_project_permission(..., "readonly")`，请求体项目缺失 / 空 / 非 UUID 一律 422（原先校验照常跑、失效缓存返回 `ok=false` 的 200）；
  `all=true` 清空全部项目缓存只许管理员（编辑级成员 403，两种失效都不发生）。`jump` / `parse` 只做字符串换算、不读库，保持仅登录，
  在本维登记 `_BODY_IDENTITY_BY_DESIGN`（可伪证：在本维、仅登录档、不挂会话依赖、不引用查询）。前端两处调用本就只在有项目时发请求、不传 `all`。
  端点测试 `test_address_registry_authz.py` 走权限世界（真实成员行、生产门禁与生产注册，只 override 当前用户与会话）：只读 / 复核 / 编辑级成员与
  非成员管理员放行且业务桩拿到请求里的项目、非成员 403、未登录 401、非 UUID 422；两个旧测试（上限 / 工作线程编码）改为管理员身份 + UUID 项目。
- **AI 对话的地址查找（R4.4）**：新增只读 `address_mention.project_address_scope`（年度经单一真源 `resolve_project_year`：`audit_year` → 审计期末年份，
  都没有为 0、不猜今年；口径读项目基本信息、非 soe / listed 按 soe，与前端 `normalizeTemplateType` 同口径；不经 `DisclosureEngine`，它会回填快照并 flush）。
  `mcp_tools._search_address_ids` 与 `_load_address_entry` 改用它；后者另把「排序后的前 500 条」改为全部地址（报表域在前、占满 500 条，
  试算表 / 附注 / 底稿 / 辅助余额地址原先一律找不到）。MCP 工具上下文年度也改走 `resolve_project_year`（原只读 `audit_year`，未填时
  试算表 / 附注工具按年度 0 取数恒空）。
- **生成底稿 / 新建自定义底稿 / 模板清单（R4.2 / R4.3）**：后端门禁由并发 spec `procedure-trim-generation-delegation-chain` 任务 6 在同两个文件里实现
  （工作树已有 `require_project_access("edit")` × 4、批量预览 `readonly`、模板清单 `readonly`，混在该 spec 的保留范围改动里，**尚未入库**），本 spec 不改这两个文件。
  前端入口本 spec 改：底稿管理页「生成底稿」「批量自定义底稿」按 `useRoleContextStore().canEditInProject` 且项目未归档显示（与 `GtRefreshScopeDialog` 同口径），
  守卫 `workpaperListCreateGate.spec.ts`；两个既有挂载测试补项目角色上下文的 mock。单条新建自定义底稿（`commonApi.createCustomWorkpaper`）现无界面调用方。
  待并发 spec 入库后补端点测试（含复核级 403、编辑级放行）与路径维基线下调。
- **基线（R4.5）**：本维（项目在请求体 / 查询参数）现算 93 → 87，常量下调；地址库五个端点钉进 `_FIXED_ENDPOINTS`。原变异只删函数体里的门禁语句，
  门禁在签名里的（`Depends(require_project_access(...))`）打不到，扩为同时把签名里的项目级依赖换成仅登录。路径维现算 200（本提交树），未动。
- **变异**：MA1~MA7（搜索 / 统计 / 解析退回仅登录、校验 / 失效缓存不判项目、清空全部不限管理员、请求体项目不校验格式、门禁降为 review 级）、
  MM1~MM6（MCP 检索 / mention 写死年度 0 与 soe、只看前 500 条、上下文年度只读 audit_year、口径不归一、取不到年度猜今年）、
  MB1 / MB2（守卫：搜索退回仅登录、`jump` 改为读库）全部打红后逐字节恢复；`WorkpaperList.vue` 注入类型错误被单区域 vue-tsc 报出。
- **范围外（登记，未改）**：
  1. 会写 stale 标记却只校验登录的三个端点：地址库 v2 `notify-cell-change`（前后端零调用方，`year` 缺省写死 2025）、联动总线 `POST /impact`、
     `GET /impact-by-addr` —— 任意登录用户可给任意项目打过期标记。跨联动总线域，需逐个评估调用方后另定。
  2. 审计年度解析另有两份重复实现（`routers/audit_check._resolve_project_year`、`routers/wp_formula._resolve_project_year`），本 spec 只复用单一真源、未合并。
  3. `mention_service._search_address` 传写死的 `soe`，只取 tb / aux 两域（构建不看口径，只影响缓存键），无行为影响。

### 10.8 R5 引用校验（2026-10-24）

- **判定模块（R5.2）** `services/formula_ref_check.py`：试算表按前缀 + 已注册列名（本年度）；报表按本项目适用准则的有效配置
  （`ReportConfigService.resolve_applicable_standard` + `load_effective_report_configs`，含项目层）；附注按本年度附注结构
  （`formula_ref_preload.note_locate`，与严格求值同一套匹配，只看结构不要求有值），本年度一节都没有时按附注模板
  （模板合计行写 `row_type=total`、附注写 `is_total`，两种都认）；项目编号无效一律判不存在。`validate_formula_refs` 的三域改调它，
  底稿 / 辅助余额仍查地址目录。`note_locate` 是从 `_note_cell` 抽出的定位部分，`_note_cell` 行为不变。
- **ACNR（R5.1）**：`full_resolve` 增 `verify_existence`（默认真）与结果字段 `verified` / `reason`；核对放 `acnr/non_wp_verification.py`：
  复合表达式 ⇒ `not_single_reference`；缺项目 ⇒ `project_context_required`；有项目按数据 ⇒ `ref_not_found` + 原因；章节级索引
  （`Note:五、3`）只看章节；读库在保存点里；`_instance_memo` 请求级复用同一判定器（报表生成对每个 ROW 引用都解析，配置只读一次）。
  只建身份的调用方显式 `verify_existence=False`：附注执行器 `_resolve_cross_refs_via_acnr`、公式管理执行 `_resolve_formula_refs`、
  高级查询寻址与跨表追溯。`ResolveRefResult.dangling`：缺项目的「无法确认」不算悬空（全局预设导入 / 新增不拦）。
  GET `/api/acnr/resolve` 增可选 `project_id`（先校验项目访问权）—— 前端 `resolveIndex` 一直在传，后端原先没有这个参数、静默忽略。
- **附注（R5.3）**：保存 `PUT …/formulas` 先逐条 `validate_refs_via_acnr`，悬空 422、不写库，每条带单元格 `target`；执行器 NOTE 按
  `_note_cell` 取行 / 列（含两参、参数间空格），原先一律取最后一个合计行、「期末」= 第一列；`_load_cross_table_data` 改存每节
  `table_data` 并排除已删除附注（原先没排除）。
- **触类旁通**：执行器 TB 只认精确码（一级科目只有下级行时恒 0）→ 前缀合计；TB / REPORT / WP 参数间有空格整条取不到 → 允许空格
  （与保存前校验写法一致）。公式导入 / 新增预设的逐条校验原先把整条表达式当一个引用（`_formula_ref_from_expr`）：以 TB 开头的取第一个
  引用判存在，以 `ABS(` / 括号开头的整条判悬空 → 拆成单个引用逐个校验（`_individual_refs`）；前端预设编辑弹窗的 refs 同样拆开
  （原先把 JSON 串化的引用项整条送去解析，必判悬空）。
- **前端（R5.4）**：`addressRegistry.validate` 只有整条公式是单个 WP 引用（`SINGLE_WP_REF`）才用 ACNR 命中短路，其余走带项目的数据校验；
  `useAcnr.resolveFormula` / `resolveUri` 带项目（缓存键含项目）；store `resolve` 带当前绑定项目；`GtFormulaEditDialog`（预设库，不在项目里）
  把 `project_context_required` 当无法确认、不拦，其余未命中照常拦。
- **测试**：`test_formula_ref_check.py`（判定口径 23 例、原因文案、模板兜底、三域路由、ACNR 单引用 / 复合 / 缺项目 / 只建身份 / 请求级缓存、
  `dangling` 口径、导入逐个引用、只建身份调用方、执行器 NOTE / TB、已删除附注）、`test_note_formula_save_ref_check.py`（真路由：悬空 422 不写库、
  有效则保存）；前端 `addressRegistry.validateRefScope.spec.ts`、`useAcnr_resolve_project.spec.ts`、`GtFormulaEditDialog.spec.ts` 补 3 组。
  陈旧测试按新口径改写：ACNR 委托类改以只建身份口径调用并补「默认缺项目 = 无法确认」、查询构造器写法闭包同、附注 DSL 两个夹具改
  `note_tables`、寻址 PBT 的替身断言 `verify_existence=False`、校验 PBT 的试算表改按科目存在性、底稿公式保存校验补附注表。
- **回归**：涉及的 102 个测试文件与本提交基线（`9eb504a5e` 干净检出）逐条对比新增失败 0（双方同为 20 failed + 8 errors，均为预存）。
- **历史大文件**：`acnr/resolver.py`（HEAD 1073 行）、`note_formula_generator.py`（HEAD 1489 行）此前未登记白名单、任何改动都被门禁拒，
  登记基线（resolver 只 +13 行，逻辑放新模块；生成器净 −6）。
- **偏离**：422 用与报表 / 底稿公式保存相同的 `FORMULA_DANGLING_REFS`（设计稿写 `FORMULA_REF_NOT_FOUND`，全仓无此码、前端无处理）；
  报表生成的 `dangling_row_ref` 告警原先恒为空（V1 换算即判存在），现在按本项目适用准则真实判定。
- **范围外（登记，未改）**：
  1. 两参 `PREV('科目','列')` 不在 ACNR 非底稿域识别里（`_detect_non_wp_domain` 无 `PREV(`），走底稿路径必未命中；前端保存前校验已不经 ACNR
     走非 WP 引用，影响面只剩直接调 ACNR 的外部调用方。
  2. 附注公式保存 422 的提示只显示「公式含悬空引用，拒绝保存」（`handleApiError` 只取 `detail.message`），不列引用；前端先校验时已列明。

### 10.9 R2 三参 PREV 定位表 / R3 陈旧测试（2026-10-24）

- **定位表（R2.1 / R2.2）**：映射表三参 PREV 共 192 格（全部映射块；设计稿只统计了首块 91 格），`prev3_prefill_locator.json` 逐格一条：
  verify 167 / write 3 / none 22，记 85 本模板的 sha256。落格来源：规则 154 格（原值小计 21、差异数核对行 55、首个合计行 78）；
  人工裁定 34 条（落格 16：verify 14 / write 2；none 18，各写原因）；模板里没有该表 4 格（H1 `分析程序H1-3`、N1 `审定表N1-1`、
  N3 `明细表N3-2`、N4 `明细表N4-2`）。write 只有 3 格（D4 上市 D10 / 国企 D9：附注「上期发生额 / 收入」列「主营业务」行；
  K6 上市 G16），其余目标格是模板公式（期初 / 上期列由模板按明细算），写值会破坏公式链 ⇒ 只批注核对。
  - 行规则（审定表族）：取数定义是「未审数」那组科目（总额口径），故先取原值 / 账面余额 / 原始金额 / 余额 / 公允价值段（首个叶子段）
    的小计；否则取模板「差异数」公式声明的行（须是合计类行、不是「试算平衡表数」行，遇「减：」行往回退）；否则首个合计行。
    否决「一律首个合计行」：会落到净额行，也会把模板自身的错（G11 审定表差异数 `D27 = D24 − D26`，减的是「其他」行）带进来。
  - 列规则：列头路径含上年 / 上期 / 期初 / 年初且不含比较类字样（比较 / 变动 / 差异 / 增减 / 比率 …）；字段名带限定词时列头须对上。
  - 同一目标格两套参数只留一套（F5 上年发生额、K8-4 本年期初判 none，守卫钉住）。生成器 `--check` 漂移 exit 2、输出幂等；
    `MANUAL` 有失效条目或缺原因即中止。
- **初次预填（R2.3）**：路由 `get_workpaper_xlsx` 调 `resolve_prev_prefill`（年度经 `resolve_project_year`，来源 `PriorWpFieldResolver`，
  与重新预填 / 公式运行时同源），传给 `prefill_workpaper_xlsx(prev_values=…)`。首块循环跳过三参格（原按列头关键词猜格，落到「本期审定数」
  「比较」列）；保存前 `apply_prefills`：write 写值 + 浅蓝底 + 批注来源；verify 只批注上年值与来源；取不到只批注原因、不写 0；模板与定位表
  记录的列头 / 行标签 / 公式标记不符就不落格并记日志（事务所覆盖版模板，不猜）；同一目标格只落一次；用户自定义公式格不动；批注追加在
  模板原有批注之后。三参格被本项目 / 全局改成别的三参 PREV ⇒ 按改后的参数取；改成非 PREV 公式 ⇒ 按 `override_value` 取数、落定位表的格。
- **重新预填（R2.4）**：`wp_effective.locate_cell` 对三参格只认定位表（write 给坐标；verify / none / 缺条目一律不落格），不再退回关键词猜格。
- **一并修**（归档 §9.3「其他」条）：`_get_tb_data_for_prefill` 原 SQL 不按年度、不排除已删除行（多年度项目会混年）⇒ 按 `resolve_project_year`
  + `is_deleted = false`，ORM 查询放保存点里，取不到年度不预填；发生额归集用同一年度。`formula_preloader._load_wp`：未对齐锚点记 warning、
  每次取值放保存点、失败带 `exc_info`、按排序遍历（结果与日志顺序确定）。
- **R3**：`test_prefill_wp_prev_resolution.py` 按现行语义改写（1037 → 523 行，28 例）：取值路径不读 `cells`、锚点 SQL 对真实 schema 可执行、
  已对齐 / 未对齐双向对照、三参取到 / 取不到（原因，不为 0）、两参未注册列报错、底稿定位确定、未对齐 / 取值失败留日志、待对齐上限只许下调；
  删掉对已删函数的源码抽取断言（文件头写明）。`four_table/test_k_cycle_preset_closure.py` 的 `test_prev_is_fail_closed…` 换成三例
  （K8~K13 期初余额三参读「未审数」定义；有上年数据取上年本期发生额、没有则空 + 原因；`prefill_anchor_map` 的登记条目是现行说法）。
  `OUT_OF_SCOPE_CHANGES['prev_year_dimension']` 改写：不再写「恒返 None / fail-closed」，剩下的缺口是底稿没有年度列（读不到上年底稿里人工录入的值）。
- **变异**：MR2a~MR2o 15 条（坐标改坏 / 动作与公式标记不符 / 漏条目 / 落比较列 / 取不到写 0 / 落格前不核对模板 / 重新预填退回猜格 /
  初次预填不跳过三参格 / 试算表不按年度 / 含已删除行 / 同格重复批注 / 用户公式格也落 / 改成非 PREV 公式不取值 / 年度缺失猜今年 /
  写值不批注来源）、MR3a~MR3h 8 条全部打红后逐字节恢复。
- **回归**：引用改动模块的 186 个测试文件（另 3 个收集即错的同根陈旧文件见任务 6.5）与本提交基线 `3c8fe7726` 干净检出逐条对比：
  新增失败 0、消除 18（R3 两个文件）；双方其余 93 例失败相同（预存）。
- **偏离**：
  1. 设计稿写「解析该底稿第一块的三参格」⇒ 全部块的三参格都按定位表落格（定位表给的是确切坐标，不依赖只认首块的猜格逻辑）。
  2. 设计稿的落格规则只写「合计行按行标签」⇒ 审定表族按上面三级行规则。
  3. 没有本年试算表时整个初次预填跳过（`if tb_data`），三参格也不批注：保持原行为（否则 TB_SUM 会写 0），未改。
- **范围外（登记，未改）**：
  1. 48 个动作格只能批注原因、永远取不到数：三参指向的字段没有取数定义、也不能由「未审数」换列 41 格（如 `PREV('D2','坏账准备明细表D2-3','期末余额')`；
     G11~G14 附注「上期」指向审定表并不存在的「投资收益_本期」等字段；K2 / K3 / K5 / K7 附注「期末账面价值_*」），定义是占位 / 序时账 / 底稿引用 5 格，
     「未审数」不是单纯试算表取数 2 格（D5、L7 占位）。能在上年数据上重算的 122 格（write 3、verify 119）。要逐格补字段定义或改参数。
  2. K8~K13「未审数」预设是 `TB('66xx','本期发生额')`，底稿求值器本期发生额 = 审定数 − 期初余额（含调整），而模板审定数 = 未审数 + 账项调整 + 重分类调整
     （K8-1：`I = F + G + H`）⇒ 字段名与口径不符。三参期初余额 / 附注上期跟随它，在上年数据上取到上年审定发生额（期初 / 上期要的正是这个值）；
     本年「未审数」格的取数口径需另定。
  3. 初次预填其余格仍按列头关键词猜格：首块 TB 182 / ADJ 152 / TB_SUM 8 格全是语义名、没有一格是坐标；89 个底稿中 70 个有多块映射（共 306 块），
     非首块从不初次预填；首块 sheet 在模板里找不到时（F0 `审定表F0-1`、N1 `审定表N1-1` 不存在；J1 模板表名带尾空格，靠「含审定表」兜底碰上）
     退回含「审定表」的 sheet 或活动 sheet 后照样猜格写值。建议把定位表扩到这些格（先定落合计行还是「试算平衡表数」行），另立 spec。
  4. `routers/wp_prefill_preview.py` 两处项目无审计期末时 `year = 2025`；`four_table/occurrence_by_standard_code` 查询失败时 `db.rollback()`
     回滚整个事务（调用方未提交的改动一起丢），`_fetch_code_mapping` 用 `CAST(:pid AS uuid)` + `str(uuid)`（SQLite 上恒查不到）。
  5. 前端 251 处拿不到审计年度时用今年：另立 spec `audit-year-calendar-fallback-ratchet`（见任务 8）。

### 10.10 6.5 同根陈旧测试改写与改写中发现的取数缺陷（2026-10-24）

- **背景**：`2638b32fd` 删掉 `prefill_engine` 的旧解析器（`_FORMULA_RESOLVERS` / `_resolve_*_formula` / `_resolve_tb_aux`），它们自
  formula-execution-path-convergence（`a8cbb1b45`）起就没有调用方，预填改走「预载 `formula_preloader` → L1 `formula_engine`」。以这些函数为对象的
  10 个测试文件随之收集即错（3 个）或部分红（7 个共 30 例），一直没人处理。按现行路径重测时发现收敛时漏掉的 4 个取数缺陷，都是「给了错数或 0、且 ok」：
  1. **三参 WP 恒为 0**：`_load_wp` 按锚点存值，L1 `_handle_wp` 只取两个实参、把第二参（表名）当列名取 ⇒ 重新预填（`prefill_workpaper_real`）与
     用户公式预览里的三参 WP 即使锚点已对齐、底稿已录入也是 0；同一底稿两张表的同名锚点（D4 主营 / 其他业务收入明细表「全年收入合计」、
     D6 两张明细表「期末合计」）在同一批预载里还会互相覆盖。改：两侧都按「表!锚点」存取，三参取不到报错不代 0。真库只读核对：已对齐锚点经
     「预载 + L1」的值与直接读锚点逐条相等。报表 / 自定义公式路径（`WPExecutor` 预载）从不取三参，原先恒 0，现在报错；真库 `report_config` 与
     `wp_formula` 里三参 WP 均为 0 条。
  2. **LEDGER_DETAIL 恒为 0 笔**：收敛 spec 的 R1.2 / R2.2 写的是「从 `ledger_detail_data` 取明细、L1 按行数给值」，但预载层从不取明细
     （`ledger_detail_data={}` 写死，「Phase 2 实装」没做）⇒ 映射表 56 格恒 0。改：新增 `_load_ledger_detail`（口径同原实现：科目精确匹配或含 `%`
     按 LIKE，金额条件对借方或贷方任一侧成立即命中，按凭证日期 / 凭证号排序）；符合条件超过 200 行就不取（L1 按行数给值，截断后的行数是错数）。
  3. **COUNT_LEDGER 期间被忽略**：它混在 LEDGER 里扫描，第二参（期间）被当成方向、期间恒按全年 ⇒ 非全年的笔数取不到（恒 0）。注册表写成三参
     「科目, 方向, 范围」、前端语法校验也按三参收，与原设计（E1 spec：`COUNT_LEDGER('科目','日期范围')`）和 L1 handler 都不符。改：单独扫描
     （科目, 范围），注册表与前端改为 1~2 参。
  4. **方向 / 期间 / 金额条件写错给错数**：方向不认识按贷方取（映射表 F2 盘点 / 监盘 9 格 `LEDGER('1403','期末数量' | '期末金额')` 拿到的是贷方发生额），
     期间不认识（如「上半年」「13月」）不加条件或按 13 月查，金额条件不认识就不过滤。改：不认识就不取，L1 对没取的键报错。
- **L1 语义变化**：序时账三个函数的键预载层没取 ⇒ 报错（原先返回 0 且 ok）。生产上只有预载路径求值这三个函数（底稿可编辑公式保存即拒、报表不用）。
  收敛 spec 的两个用例按新语义改（`test_formula_preloader::test_ledger_missing_key`、`test_execution_path_parity::test_known_function_not_blocked`）；
  `test_formula_preloader::test_count_ledger` 原先钉住的正是缺陷 3 的扫描写法，一并改。
- **改写口径**：一律在真 SQLite 落数据、经现行入口（`resolve_extended_formula` / `preload` + `execute`）按值断言；原 mock DB 用例（返回什么断言什么）删除。
  `formula_wp_semantics.py` 的登记改为现状：预填路径 `_load_wp`、L1 `_handle_wp`、报表 / 自定义公式路径 `WPExecutor.execute` 三处，三条差异照旧登记。
  `test_formula_runtime_zero_regression` 的注册表基线 14 → 20（收敛时并入的 6 个函数一直没同步）。`test_adj_formula_resolution` 的冒烟改为
  「注册表里每个取数函数，预载层都扫得到、取得到」（新增函数未登记取数口径即红），原冒烟只防 ImportError，发现不了缺陷 2。
- **不同根的一条**：`test_f_prefill_extension::test_f22_master_sheet_uses_aux_or_tb` 是 `5783c4ffe` 有意把 F2-2 明细汇总表改为联动分类明细表
  （原判据「F2-2 不许用 WP」被推翻），改为断言它真正要防的循环引用（不指向自己与下游 F2-1、映射表 WP 联动无环）。
- **顺带**：删掉 `2638b32fd` 留在 `prefill_engine` 的死代码（6 个无引用的正则、`_parse_period_range` 里 return 之后不可达的重复代码、无用 import）；
  L1 取数报错的日志文案由「TB column unregistered」改为通用说法（PREV / WP / 序时账也走这条）。
- **测试 / 变异 / 回归**：改写的 10 个文件 + 两个收敛用例文件全过；变异 MR65a~MR65p（后端 16 条：L1 三参退回按表名取 / 预载按锚点存 / 三参取不到给 0 /
  预载不取明细 / 明细未取给 0 笔 / 金额条件、期间、方向不认识退回旧行为 / COUNT_LEDGER 期间按全年 / LEDGER 未取给 0 / 超上限照截断 / 科目不支持 LIKE /
  登记表指回已删函数 / 预填入口不写两套口径 / 重新预填改排除底稿来源 / COUNT_LEDGER 混回 LEDGER 扫描）与 MR65q（前端 COUNT_LEDGER 退回 3 参）全部打红后
  逐字节恢复。回归：引用预载层 / L1 / 预填入口 / 登记模块的 360 个测试文件与 `988c6809b` 干净检出逐条对比，新增失败 0、消除 30（另 3 个原收集即错的文件
  现在全过）；双方其余 182 例失败相同（预存）。前端 `formulaSyntaxParser.spec.ts` 43 例过。
- **范围外（登记，未改）**：
  1. `LEDGER('1403','期末数量' | '期末金额')` 9 格：序时账有数量列（`debit_qty` / `credit_qty`），但「期末数量 / 期末金额」是余额不是发生额，
     取数口径需另定（现在报错不取）。
  2. J1 月度分析表 21 格 `LEDGER_DETAIL('2211','月度分析表J1-4','1月','期末余额')`：四参写法，要的是月末余额而不是明细笔数（现在报错不取）。
     其余 35 格三参 LEDGER_DETAIL（截止测试「期末大额收入明细」等）现在写入的是符合条件的笔数；若模板要的是明细清单，需要「把明细写进表格区域」的能力。
  3. 两参 WP 取不到返回 0（与「值确实为 0」不可区分）、预填与报表两条路径的数据来源不同：照旧登记在 `formula_wp_semantics`。

### 10.11 6.6 报表求值半成品开关 / 公式调试上下文 / 改写已跟踪文件的测试（2026-10-25）

- **报表求值半成品开关**：`report_engine.evaluate_formula_result` 删 `enable_prev` / `enable_aux`。唯一调用方（表间审核）传 False；
  打开时 PREV 只认同项目上年、AUX 从不存在的 `app.models.four_table_models` 导入（恒失败、被 except 吞掉），从没有用例测过打开的分支。
  PREV / AUX 在报表域照旧置 0（合成一个循环），表间审核照旧先经 `_substitute_strict` 严格代入。表间审核传的 `strict_context=True`
  此前没有用例：补「NOTE / WP 取不到如实记为不通过、不按 0 去比」（否则左右两边都缺数时 0 = 0 恒通过）。
- **公式调试上下文**：`routers/formula_debug._build_context` 原自拼上下文 —— 从不存在的 `four_table_models` / `disclosure_models` 导入
  （被 except 吞掉，试算表与附注恒空）、试算表列名写成不存在的 `account_code`、调整额 / 底稿 / 上年 / 辅助核算 / 序时账一律不取 ⇒
  调试结果与真实求值对不上。改为按待调试公式走统一预载 `formula_preloader.preload`：调整额口径按作用域（报表 / 附注排除底稿来源，
  底稿 / 明细不排除）、口径由 `formula_ref_check.project_ref_scope` 取；取数缺口（如本年度报表未生成）随响应的 `warnings` 返回。
  原用例用 mock DB 只断言「返回的是 dict」，改为真 SQLite 落数据按值断言（TB 100、报表调整额 20、底稿调整额 50），另补端点级用例
  （权限世界真发请求，缺口进 `warnings`）。
- **lazy import 守卫**：`_guarded_import_linenos` 原把 `try / except Exception` 里的 import 当「可选导入」豁免 ⇒ 写错路径只剩一条
  warning 日志（`formula_debug` 两条即此）。改为只豁免 `except ImportError / ModuleNotFoundError`；新暴露 11 条，3 条随本节删除代码消失，
  8 条冻结进 `_KNOWN_UNRESOLVED_BASELINE`（各需按功能核实后修，现在修等于第一次运行从没跑过的代码）：`wp_formula._build_four_table_prefill`、
  `_d4_operating_revenue` 的 `FinancialReport`、`ai_chat/startup_health` 的 `audit_event`、`unified_graph_builder` 的 `get_registry_edges`、
  `formula_timeline_service` 的 `Project`、`issue_ticket_service` 的 `notification_service`、`role_workbench_facade` 的 `PBCItem`、
  `wp_scripts/registry` 的 `get_review_points`。自检加「`except Exception` 包住的 import 不豁免」。
- **改写已跟踪文件的测试**：干净检出跑 142 + 190 个候选测试文件（静态扫「写文件 + 仓库路径」；第二批排除往真库提交数据的 7 个 PG 文件，
  静态核对过它们只写临时目录或写完即还原），跑完 `git status` 只有第一批找到两组：
  1. `test_workpaper_route_task1_baseline::test_baseline_snapshot_can_be_regenerated` 每跑一次无条件重写 `tests/_snapshots/…json`（带
     `generated_at_epoch`）。快照是 workpaper-page-formula-toolbar-closure 任务 1 的红基线冻结（现扫与它本就不等，没有代码读它）⇒ 改为内存往返 +
     核对已提交快照的键集、断言运行前后字节不变；只在 `GT_UPDATE_SNAPSHOTS=1` 时重写，且除时间戳外没变就沿用旧时间戳。
  2. 归档 spec 的 evidence（manifest 钉了 sha256）：procedure-delegation-visibility-isolation 的 task14（session 收尾写样例数）、task15
     （EXPLAIN ANALYZE 实测耗时）、task17（容量报告 / 冻结阈值 / p95），visibility-isolation-go-live-hardening 的 task5（已 skip）、task6
     （浏览器结果文件在不在决定写哪份摘要）⇒ 统一改写到 `tests/_test_artifacts.artifact_dir()`（`GT_TEST_ARTIFACT_DIR` 或系统临时目录）。
  守卫 `tests/_tracked_write_guard.py`（root conftest 登记）：`sys.addaudithook` 记本进程对已跟踪文件的写（写方式 `open`、`os.rename` /
  `os.replace` 两端、`os.remove`、`os.truncate`、Windows 上 `shutil.copy2` 走的 `_winapi.CopyFile2`），首次写之前记原摘要；每个用例
  （含 teardown）后重算，已还原放过（变异测试写完即恢复），没还原的到会话结束再核一次，仍不一致 ⇒ 列出文件与首次写入的用例、退出码置 1。
  不覆盖子进程里的写；`GT_UPDATE_SNAPSHOTS=1` 放行。自测在临时 git 仓库里起子进程 pytest 按真实退出码判（改写不还原 / 原子替换 /
  copy2 / 删除 ⇒ 红并点名；写完还原、写未跟踪文件 ⇒ 绿；conftest 的 `pytest_sessionfinish` 里写的也能抓到）。开销：同批 213 例
  交替开 / 关各跑 2 次，开 59.4 / 53.9 秒、关 62.0 / 70.5 秒（机器同时在跑别的测试，差异在噪声内）。
- **同根顺带**：两条源码锚点守卫随本节改动失效 —— `test_function_support_matrix::test_report_path_source_still_zeros_prev_aux` 以注释
  「报表域默认置 0」为锚点（注释改写即红、取数改了反而不一定红），改为按行为判（PREV / AUX 经报表路径求值为 0）；
  `test_adj_formula_function::test_adj_not_in_report_engine_zero_substitution_list` 查的是兼容入口 `evaluate_formula` 的源码（拆分后恒找不到列表，
  预存红），改为查求值主体、按 AST 认列表 / 元组。`preset_acnr_migration._FALLBACK_KNOWN_FUNCS`（内核注册表的手抄副本，内核导入失败时兜底）
  漏同步 `TB_AUX / LEDGER / COUNT_LEDGER / LEDGER_DETAIL / PLACEHOLDER`（unified-formula-registry 登记进内核时没跟上），补齐。
- **变异**：MR66a~MR66j（调试上下文不取数 / 调整额口径不分作用域两向 / 缺口不进 warnings / 加回 `enable_prev` / 表间审核不严格取数 /
  `except Exception` 又算受保护 / 兜底函数集漏同步 / 报表路径 PREV 改成真取数 / ADJ 加进置 0 列表）、MG1~MG10（守卫各环节失效）、
  MS1~MS5（快照与三处归档证据改回写仓库）全部打红在预期断言上，跑完逐字节恢复。
- **范围外（登记，未改）**：
  1. `routers/wp_prefill_preview.py` 的「预览」端点注释写「不写入」，实际调用会写底稿的 `prefill_workpaper_real`（预览即应用）；
     年度兜底 2025 已进 `audit-year-calendar-fallback-ratchet` 的基线。
  2. `formula_grammar.FORMULA_FUNCTION_NAMES` 无引用方，内容停在 14 个函数（不含 ADJ / 序时账 / TB_AUX）。
  3. 守卫不覆盖子进程：用 `subprocess` 跑生成器 `--write` 的测试仍可能改写已跟踪文件（本轮扫描未见）。
