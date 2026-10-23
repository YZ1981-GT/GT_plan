# 取数结果错误 / 底稿生成流程 / 测试欠账 收口 —— 设计

> 现状均为 2026-10-23 现读代码与真库现查（只读）。行号会漂，锚点用函数名 / 常量名。

## 1. R1 推送规则科目

根因：H/I 两循环在批 C 从 Tier A binding 迁到审定表族 binding（`bindings/balance_adj._SPECS`），科目改成手写字面量（抄自
`wp_account_mapping.json` 的主条目，含字母后缀码 `1606B` / `1703B` 与错码 `2802` / `1901`），而规则公式仍抄自 Tier A 预设
`d_cycle_extraction_presets.json` ⇒ 两边各错一部分。`load_tb_audited` 以 binding 科目为键（前缀匹配标准码），公式引擎对缺键取 0。

真库（trial_balance 未删行，标准码合计）：1606 有 10 个项目 6.65 万；1641 / 1651 合计 4.53 亿（使用权资产）；2601 / 2651 合计
1.88 亿（租赁负债）；1901 = 0；6602（管理费用）2.29 亿；6604（研发费用）= 0。

| 底稿 | 现 binding | 现规则 / 预设 | 改为（依据） |
|---|---|---|---|
| H6 固定资产清理 | 1606B | 1606 | binding `1606`（标准科目表；`h6_account_scope` 兜底码） |
| I1 无形资产 | 1701/1702/1703B | 1703 | binding `1701/1702/1703`（`i_cycle_accounts` I1 减值段） |
| H9 租赁负债 | 2802（不存在） | 2205（合同负债） | binding 与公式 `2601 + 2651`（`dual_family_codes.codes_for_cycle_slot("H9","gross")`） |
| H8 使用权资产 | 1901 | 1901 | binding 与公式 `1641 + 1651`（同上 `("H8","gross")`）—— 不推 0 但推错科目，同根因 |
| I2 开发支出 | 1704 | 1717（不存在） | 公式 `1704`（`i_cycle_accounts` I2 段） |
| I6 研发费用 | 6602（Tier A 由预设派生） | 6602（管理费用） | 预设与规则 `6604`（`i_cycle_accounts` I6 段）—— 推错科目，同根因 |
| I5 其他非流动资产 | 1901（待处理财产损溢） | 1911（不存在） | 无标准科目（`i_cycle_accounts` I5 段 `fallback=()` 宁缺勿造）：删 `I5.1_tb_amount` 规则与预设锚点；binding 不再取 1901 |

- binding 科目改从口径单一来源取（`dual_family_codes` / `i_cycle_accounts` 的兜底码），不在 `_SPECS` 再写一份字面量。
- I5：审定表族 binding 要求科目非空 ⇒ I5 改为「无科目」声明（`account_codes=()` 且取数跳过并给原因），附注主行规则如实跳过；
  该格不再是推送独占键，用户可填。
- 守卫：`KNOWN_PRESET_CONTEXT_GAPS` 清空；新增「binding 科目 ∈ 标准科目表 ∪ 口径单一来源登记码、且不带字母后缀」；
  「同一底稿的规则公式科目 ⊆ binding 科目」由既有 `push_context_errors` 守卫覆盖。
- 生成物重生成：`formula_push_coverage.json`（`gen_formula_push_coverage.py --write`）、`formulaPushOwnedKeys.ts`（删 I5 规则后变化）。

## 2. R2 PREV 三参

`PREV('底稿','表','字段')`（预设 192 格，全部指向本底稿；用法说明「从上年同底稿取审定数」）现状：初次预填留空、重新预填 / 公式运行时
恒 0（L1 `_handle_prev` 把底稿编码当科目查上年试算表）、底稿可编辑公式与严格路径拒收。

口径（与报表上期「用本年配置公式在上年数据上求值」同一思路，`report_prior_period` ③）：

1. 上年数据来源 `prior_year_context.resolve(db, project_id, year)`：同项目有 `year-1` 试算表 → 同项目；否则上年项目
   （`prior_year_project_id` → 同企业代码 + `audit_year = year-1` + 同报表口径，唯一才认）且该项目有 `year-1` 试算表。
   取不到 ⇒ 原因（未找到上年项目 / 上年项目不唯一 / 上年项目没有 Y-1 年试算表 / 本项目缺企业代码或审计年度）。
   `report_prior_period._find_prior_project` 改调同一函数（单一来源）。
2. 字段定义：本底稿该槽 `{底稿}|{表}|{字段}` 的有效定义（本项目底稿公式 > 全局 > 系统预设）；没有该槽而该表是审定表
   （有「未审数」槽）且字段是试算表列名（审定数 / 未审数 / 期末余额 …）⇒ 用「未审数」槽的定义。都没有 ⇒ 原因「没有取数定义」。
3. 定义只允许试算表 / 调整类取数（TB / SUM_TB / TB_SUM / ADJ 与四则、ABS / ROUND / MAX / MIN / IF）；占位、序时账、底稿 / 附注引用、
   再套 PREV ⇒ 原因（不在上年数据上重算这些）。
4. 在上年数据上严格求值（底稿求值器），取不到 ⇒ 原因。

接入：`formula_ref_preload.substitute_prev_aux`（严格路径：底稿可编辑公式、表间审核、报表审核）；`wp_formula_eval_service` 去掉三参拒收；
统一预载层 `preload` 区分两参 / 三参，三参值进 `FormulaContext.prev_wp_data`、缺数进 `gaps` 与 `prev_wp_missing`，L1 `_handle_prev`
三参读它；重新预填对缺数格记原因、不写 0；初次预填（`prefill_workpaper_xlsx`）由调用方预先解析 PREV 格的值传入。
两参 `PREV('科目','列')` 改用同一上年来源，并修 L1 忽略列名（恒取期末余额）。

## 3. R3 地址库 50000

- 后端 `address_registry.ADDRESS_REGISTRY_MAX_LIMIT = 50_000`；路由 `limit: Query(100, ge=1, le=上限)`；响应新增 `returned`、`truncated`、
  `truncated_domains`，`total` 改为真实匹配数（前端不读旧含义，已核对）。
- 前端 `ADDRESS_REGISTRY_FULL_LOAD_LIMIT = 50000`（store 与公式编辑弹窗底稿域直调同一常量，守卫比对后端上限）；`addresses` 改
  `shallowRef`；读 `truncated`，截断时提示一次，`isDomainComplete(域)` 供选择器判断是否回退。
- 刷新单飞：按（项目, 年度, 口径）共享在途请求，响应到达时绑定已变则丢弃（原先 B 项目的刷新在 A 加载中被吞、A 的数据被当成 B 的）。
- `FormulaRefPicker`：附注 / 报表行优先用登记的 `formula_ref`（原先拼 `NOTE(章节,'合计','期末')`，与登记表头不一致 ⇒ 附注域有数后保存判悬空）。

## 4. R4 生成底稿保留裁剪

`GenerateWorkpapersRequest` 加 `selected_templates: list[str] | None`；`TemplateEngine.generate_project_workpapers(..., selected_codes=)`
在取模板集编码后按选中过滤；回执加 `ignored_codes`（选中但不在模板集里的）。跨语言契约测试：前端请求体键 ⊆ 后端模型字段。

## 5. R5 按编码生成多页底稿

`generate_from_codes` 改走 `init_workpaper_from_template`（`find_template_file_any` → 多文件合并 → 场景裁剪），与链路编排同一解析；
先 flush 底稿行取 id 再初始化文件；名称取 `wp_name_source.resolve_wp_name`；找不到模板时仍建空白册但单列 `blank_codes` 并在消息里写明。
`wp_conversion/_generate.py` 的同款模板库精确匹配一并改用同一解析。

## 6. R6 自定义底稿编辑器口径

前端按宿主注入的适用准则（`useHostApplicableStandards`）取 `listed` / `soe`，取不到则不传；后端 `template_type` 改可选，缺省按项目口径
（与附注渲染同一权威）解析，`custom` / `private` 等归一为 `soe`。批量接口同。

## 7. R7 d-cycle 测试

两类替身过时：`list_formulas` 形参 `_user` → `user`；保存 / 列表经 `assert_project_permission`（归档检查 `db.get(Project)`、RLS
`get_bind()`）⇒ 替身补 `get` / `get_bind`，身份用管理员（门禁本身照常执行）。其余失败逐条定根因（见 §9 实施记录）。

## 8. R8 pytest 启动

根因：`backend/pytest.ini` 的 `pythonpath = tests`（cad40da77，为 7 处裸 `import authz_world` 等）把 `backend/tests` 放到导入路径首位，
`tests/playwright/` 包遮蔽真实 playwright，pytest-playwright 插件加载即崩；`tests/scripts` 同样遮蔽 `backend/scripts`（靠插入顺序侥幸可用）。
修：删 `pythonpath = tests`，裸导入改 `tests.` 限定；浏览器抽样测试默认跳过（`GT_BROWSER_E2E=1` 才跑）；守卫：ini 不得把测试目录放进
pythonpath、测试文件不得裸导入测试根目录模块、子进程不带 `-p no:playwright` 能完成收集。

## 9. 实施记录

> 2026-10-23。逐条证据见 tasks.md；本节只记与设计不同的地方、全量回归结论、范围外发现。

### 9.1 与设计的偏离

1. **R1 范围按同根因扩大**（§1 表只列 7 个底稿）：
   - G6 / G8 binding 原写 `1503`（旧准则可供出售金融资产），改取 `g_cycle_specs` 原值槽兜底码（1506 / 1507）。
   - K1 binding 原为 `("1221","1231")` 且期初「原值 + 坏账准备」：`1231` 按前缀把应收票据 / 应收账款的坏账准备也算进来，还加而不是减。
     真库重药控股安徽_2025 附注期初推成 166,031,263.81（应为 149,663,565.08）。改取 `k_cycle_specs`（1221 / 1231-03），期初 = 原值 − 坏账准备。
   - J / L / M 附注直推 binding 改取四表口径单一来源（`note_direct._single_source_codes`）：映射表在这三个循环有 9 个底稿科目码错
     （M3~M10 整体错位一格、J2 写不存在的 2611、L7 写 K5 的 2801）。真库和平药房_2025 盈余公积附注期末推成本年利润 53,384,067.82。
     L7 / M8 没有标准科目，登记无科目原因，规则清单里不得有取数规则。
   - H8 / H9 双族互斥科目（1641 / 1651、2601 / 2651）附注主表合成一行；不合行时每码一行撞同一附注行，一格都不写。
   - I3 / I4 也改为从 `i_cycle_accounts` 取（码值不变）。
   - I6 改正后：真库各项目 6604 研发费用均为 0，推送值由管理费用金额变为 0（结果正确；研发费用若记在别的科目，需按项目改公式）。
   - 没改：`wp_account_mapping.json` 本身（十几个模块在读，需拍板，见 9.3）、K4 / D5 / F2（见 9.3）。
2. **R2 初次预填不写三参值**（§2 最后一段原定由调用方预先解析后传入）。初次预填按语义定位「上年审定数」（关键词 上年 / 审定数）找列，
   真实模板上 91 格落到「本期审定数」或「本期与上期审定数比较」列（如 D1 → J5、E1 → D6；H10 取到 E5，J5 才是上期审定数）。
   写进去会覆盖本期数（宁缺勿造）。初次预填维持留空；重新预填与公式运行时按 §2 取上年值或报原因。需要按模板逐格的定位表，见 9.3。
3. **R2 保存时的引用校验跳过三参 PREV 的 `wp://` 地址**（§2 未写）：三参指向上年同底稿的取数槽，不是本年地址库条目；不跳过则保存仍报
   `FORMULA_REF_NOT_FOUND`。没有改成加载底稿域去校验（槽位不是地址库条目，会误报不存在）。
4. **R2「未审数」槽回退时改写列名**：把定义里 TB / SUM_TB 的列换成所取字段（TB_SUM → SUM_TB）。原样用「未审数」的定义会取到上年未审数。
   定义里有换不到列的试算表取数（单参 `TB('科目')` 等）⇒ 不取并写明原因（按缺省列取会把期末数当期初数）；预设 83 条「未审数」定义现算全部可换列。
5. **R2 上年求值用底稿求值器**（试算表按科目码精确匹配，与 §2 第 4 点一致）；它与 L1 的前缀聚合口径不同，列入 9.3。
6. **R2 两参 PREV 的缺数原因**改用 `prior_year_context` 的原因（如「本项目没有 2024 年试算表，…」），相关测试同步更新。
7. **R3 截断提示只列选择器页签真受影响的域**：报表 / 试算表 / 附注截断时改用页面数据并提示；底稿页签走 ACNR 目录，只在回退旧地址库时提示；
   辅助余额没有页签，不提示。浏览器实测和平 2025（只截断辅助余额）首版误提示后改。`isDomainComplete` 只接在 `FormulaRefPicker`。
8. **R5 生成时不预填**：按编码生成与准则转换生成只落模板文件（模板目录索引 + 多文件合并 + 场景裁剪），与模板集生成一致；预填在打开 / 刷新取数时。
9. **R6 前端一律不传 `template_type`**（§6 原定按宿主注入的适用准则传）：后端缺省按底稿所属项目口径解析，单一权威，宿主没注入时也不会回到写死。
10. **R8 补 locust 卡死**：见 tasks 1.1（R8b）。没用 `python_files = test_*.py`：会静默丢掉以后新写的 `*_test.py`。
11. **实测中顺带修的一处**：底稿面板（`WorkpaperSidePanel`）恒按日历年给公式 / 一致性子面板传年度。2025 年度项目在 2026 年保存提取公式时按 2026
    校验引用 ⇒ 本年试算表有的科目也判「引用地址不存在」（和平 2025 实测：`TB('1122','期末余额')` 按 2025 有效、按 2026 无效）。改为编辑器传项目审计年度。
    同一反模式在底稿管理页（`WorkpaperList.currentYear`）：不带 `?year=` 进入（编辑器「返回」、进度看板、试算表穿透等多数入口）时按今年发请求 ⇒
    生成底稿按 2026 绑数据集（绑不上）、回退的按编码生成因「无 2026 试算表」422、「刷新全部公式」被推送引擎以「只作用于项目审计年度」拒绝。
    改为 `resolveEffectiveAuditYear`（路由 `?year=` > 本项目审计年度 > 去年），浏览器实测 R4 生成时请求带的就是 2026。

### 9.2 全量回归

同参数（`-p no:playwright tests --ignore=tests/integration --ignore=tests/e2e --continue-on-collection-errors`），同一干净 worktree：

- base `54e73f695`：2811 failed / 62927 passed / 1548 skipped / 584 errors（4 小时 26 分）
- 本 spec 全量（临时提交 `8e974b2fe` = 上述 base + 本 spec 当时的全部文件，同一 worktree、同参数）：2719 failed / 63125 passed /
  1549 skipped / 583 errors（4 小时 18 分）。逐条比对：base 红而本 spec 不红 109 条（d_cycle_extraction 84、tests 根目录 21、
  workpaper_sync 3、playwright 1）；本 spec 新红 16 条，逐条处理：
  - `test_address_registry_limit`（5）：本 spec 自己的两个新测试同进程互相干扰（见 tasks 4.1），推送前已修；
  - `test_note_direct_integration` 的 L7 / M8（4）：R1 把两者改成「无科目」声明后，该测试仍按「每个批 D 科目都有科目和两条规则」断言 ⇒
    按新契约改写（无科目、无派生、无规则，并断言写明了原因）；
  - `test_wp_formula_endpoint`（2）/ `test_wp_formula_non_wp_kind_defense`（1）：R6 起请求不带口径时端点查 `projects.template_type`，
    这几个机制测试只建 `wp_formula` 表 ⇒ 与其已有的鉴权 / 归属隔离同样桩住这一处（口径解析由 `test_wp_formula_ref_template_type` 用真行覆盖）；
  - `workpaper_sync/test_task12_canonical_resolver::test_matrix_is_fresh`（1）：R5 去掉了生成端点里的自写路径判断，resolver 迁移矩阵的
    证据随之变化（状态不变：migrated 14 / deferred 79 / regressed 0）⇒ 按其约定 `--apply` 重生成；
  - 其余 3 条是间歇失败、与本 spec 无关：`test_business_category_pbt`（hypothesis 抽到 C 类就红 —— C 类下 A18 / A26 / A27 / A28 / A1-12 /
    A1-16 仍判适用，base 直接调用结果相同）、`test_param_sql_builder_pbt::test_p18`（base 上 5 次红 1 次）、
    `procedure_delegation/test_procedure_reconcile` 的 PG 用例（单独复跑 base 5 次、本 spec 7 次全过）。
- 最终提交树定向回归（HEAD `5f4e8b54c` + 本 spec；后端 96 个目标 = 本 spec 改过的测试 + 并发会话两提交改过的测试 + formula_settings /
  formula_management / d_cycle_extraction / 全部 formula_push；前端 330 个文件）：后端 13 failed / 3170 passed，前端 4 failed / 966 passed。
  同一组目标在 `5f4e8b54c` 上整组复跑：后端 117 failed（含上述 13 条，其余 104 条在本 spec 上通过），前端同 4 条 ⇒ **新增失败 0**。
  这 13 + 4 条见 9.3 末条。

### 9.3 范围外发现（未改，需拍板或另立 spec）

- **映射表科目码**：`wp_account_mapping.json` 上述 9 个底稿的科目码错，另有两套 4xxx 编码并存（4201 / 4301、4103 / 4003）。推送已改走口径单一来源，映射表本身没改。
- **其他推错 / 推 0 的规则**：F2 存货把 1461 存货跌价准备按正数并入；K4 其他流动负债取 2261、D5 应收款项融资取 1124，两码在各项目科目表里都不存在；
  I1 / H1 审定合计把备抵科目按正数相加；报表行 BS-037 取不存在的 1911。
- **初次预填定位**：语义定位「上年审定数」落错列（见 9.1 第 2 条），「期初余额」类格子找不到；需按模板逐格的定位表。
  重新预填（`prefill_engine`）求值出错时不写、也不清旧值；真库 3565 份底稿 `parsed_data` 0 份有 `univer_snapshot`、0 份含 PREV ⇒ 现无三参旧 0 残留。
- **口径差异**：底稿求值器遇到不认识的列名静默当审定数 —— 含「本期发生额」（L1 = 审定数 − 期初；底稿求值器 `_COLUMN_MAP` 没有它 ⇒ 取审定数，
  `_period_amount` 分支是死代码），影响 H10 / I6 等 Tier A 预设与 3 条 PREV 三参；L1 把「未审数」别名到期末余额，底稿求值器取未调整数；
  L1 前缀聚合与底稿求值器精确匹配不同。
- **年度兜底取今年（全平台）**：前端源码 251 处用 `new Date().getFullYear()` 当审计年度兜底（不减 1、不读项目年度），本 spec 只改了
  底稿面板与底稿管理页两处（见 9.1 第 11 条）；其余需另立 spec，可先冻结棘轮（只许减少）。
- **死分支 / 陈旧守卫**：`report_engine.evaluate_formula_result` 的 `enable_prev` 分支只认同项目、实际走不到；`test_prefill_wp_prev_resolution.py`、
  `four_table/test_k_cycle_preset_closure.py` 以「PREV 恒为 None」为前提，HEAD 上已红，前提已被本 spec 推翻，需改写或删除。
- **校验形同虚设**：`/api/acnr/resolve` 对 TB / NOTE / REPORT 引用（含不存在的章节、复合表达式）一律 `found: true` ⇒ 前端保存前校验
  `addressRegistry.validate` 对非底稿域恒判有效；附注公式集保存接口本身不校验引用 ⇒ 附注公式弹窗可存入悬空引用。
- **年度取值**：底稿管理页 `currentYear` 取 URL `?year=`，缺省日历年（直接打开页面生成底稿时请求带 2026）；附注公式弹窗取试算表行请求 `/api/trial-balance/`（404）。
- **鉴权**：地址库路由只校验登录不校验项目；生成底稿两个端点缺项目级鉴权。`mcp_tools` / `address_mention` 写死 `soe`。
- **业务分类**：C 类项目下 A 类专属底稿（A18 / A26 / A27 / A28 / A1-12 / A1-16）仍判适用，`test_business_category_pbt` 抽到 C 类就红（HEAD 上同样）。
- **其他**：删除模板调用 `WpTemplate.soft_delete()`，而该模型继承 `Base`、没有这个方法 ⇒ 删除恒抛 AttributeError；`_get_tb_data_for_prefill` 不按年度过滤；HEAD 上的覆盖率 JSON 过期；`test_h_ledger_formula` 导入不存在的
  `_FORMULA_RESOLVERS`；全量运行会改写已跟踪文件（`tests/_snapshots/workpaper_route_task1_baseline.json`、已归档 spec 的证据产物）。
- **HEAD 上已红、与本 spec 无关**（干净检出逐条复现）：后端 `test_note_formula_endpoints_auth_unchanged`（3）、
  `test_pbt_p22_preset_grammar::test_p22_pending_allowlist_functions_are_pending`、`test_preset_acnr_migration_drift_guard::test_hardcoded_old_format_is_pending`、
  `test_user_formulas_override::test_supported_types_includes_all_10`、`test_adj_formula_function`（2）、`test_formula_push_batch_e_l_note` / `_mnf_note` 的
  L6 / N3 sync_registry（2）、`four_table/test_k_cycle_specs`（21）、`test_formula_push_d4_canary::test_d4_second_push_idempotent`、
  `test_formula_push_note_row_containment[income_tax_component]`、`test_formula_push_owned_keys_baseline`（`disclosure_builders/e1_builder.py` 未登记）、
  `test_workpaper_route_task1_baseline::test_nodekey_payload_inventory_is_stable`（`ConsolWorksheetTabs.vue` 新写法）；PG 真库的
  `test_formula_push_k1_d4_canary_pg` / `_note_skip_pg` 批量跑时 asyncpg 连接在已关闭的事件循环上回收而红（base 同样红，单独跑 k1_d4 通过）；
  前端 `k1FormulaPushHost`（3）、`dSalesCycleLabelGuard`（2）、`formulaPaths`（2）、`WorkpaperListShell`（3）、`line-budget`（1）、
  `WorkpaperEditorShell`（`createRouter` 未 mock）。
