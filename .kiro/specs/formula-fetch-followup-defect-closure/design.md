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
