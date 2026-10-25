# 取数口径后续缺陷收口 —— 任务

> 证据口径：每项测试 + 变异（在独立 worktree 里改坏生产代码、守卫打红、逐字节恢复）；「base」= 改动前 HEAD 干净检出。
> 写入型实测只在临时【测试】项目；真库只读核对除外的写入（报表公式发布、映射修正）在 design 写明并在交付说明里列出。

## 1. 小项（R7 / R8 / R9）

- [x] 1.1 底稿求值器 `本期发生额` = 审定数 − 期初余额（TB / SUM_TB），删死分支；未注册列名记 errors；先扫全部经底稿求值器的预设列名（R7）
  - 证据：`wp_formula_eval_service._DERIVED_COLUMNS` / `_balance_field`（提交 25a506a57）；`formula_settings/test_wp_eval_period_amount.py`
    （与 L1 预载同值、未注册列名报错、预载发生额与区间）+ 本轮补「Tier A 预设列名全部已注册」常驻守卫与扫描自检；变异 MR7a / MR7b 打红
- [x] 1.2 业务分类以参考标准为单一来源（C / B 排除清单、族匹配、映射表标注仍生效）；`review_workflow_service` 按主分类前缀；PBT 全过（R8）
  - 证据：`business_category_service.is_template_applicable`（提交 25a506a57），`test_business_category_pbt.py` 6 例全过；
    本轮复核发现复核模板另有一份适用性（`review_checklist_templates.json` 的 `a_only`），按前缀判断后 B 类质量复核合伙人 / EQCR 仍拿不到模板，
    与参考标准「B 类保留 A24 / A25」矛盾 ⇒ `_get_template_for_role` 改调 `is_template_applicable`、删掉 `a_only`，`test_review_workflow_pbt.py` 按参考标准改写；
    变异 MR8a / MR8b 打红
- [x] 1.3 删除模板：`is_deleted` + 更新时间、管理员权限、被引用按底稿编码精确判断；端点测试（R9）
  - 证据：`TemplateEngine.delete_template` + `DELETE /api/templates/{id}` 只许管理员（提交 25a506a57）；`test_template_engine.py` 服务层 4 例、
    端点成功 / 非管理员 403 + 本轮补「被引用 400、模板仍在」；变异 MR9a / MR9b / MR9c 打红。同文件 3 例模板集种子用例在 HEAD 同样红（与本项无关）

## 2. 推错数的规则（R6）

- [x] 2.1 K4 / D5 改无科目声明，删试算表取数与附注主表规则，删已知偏差条目；生成物重生成（R6.2）
  - 证据：规则清单 K4 只剩 `audited_total.receivable / net`、D5 无规则；`KNOWN_ACCOUNT_DEVIATIONS` 只剩 D4；
    `gen_formula_push_coverage.py --check`（81 条）/ `gen_formula_push_owned_keys.py --check`（172 键）通过；
    `test_formula_push_account_single_source.py` / `test_formula_push_rules.py` 绿（提交 25a506a57、6b0e7889d）
- [x] 2.2 F2 附注主表：备抵科目按减项，六字段只写合计行（R6.1）
  - 证据：`test_formula_push_f2_note_book_value.py` 4 例；变异 ME（跌价准备算进账面余额）/ MF（进销差价按加项）/ M1（旧格式表原因退回旧文案）
    均打红后逐字节恢复；真库 dry-run 安徽 6 格写入与试算表逐值一致、和平旧格式表 6 格跳过并写明原因（提交 6b0e7889d）
  - 偏离：字段名用真实同步列键 `end_gross / end_impairment / end_net / prior_*`（design §10.1）
- [x] 2.3 审定表族审定合计按前端真实持久化取数（逐底稿现读声明），备抵按减项，读不到不写 0（R6.3）
  - 证据：`balance_adj_extract.AUDITED_SOURCES` + `test_formula_push_balance_adj_extract.py` 20 例、批 C 对账 34 例（含前端键存在性守卫）；
    变异 MA（不可取→0）/ MB（备抵按加项）/ MC（主清单读不到→0）/ MD（合计键空串→0）均打红
- [x] 2.4 H1 / I1 附注主表按账面价值出行，行名对齐两种准则模板（R6.3）
  - 证据：`test_formula_push_h1_i1_note_book_value.py` 3 例、`test_disclosure_builders_h1_i1_net.py` 10 例；变异 MG / MH（净值读不到写 0）打红
- [x] 2.5 报表 BS-037 置空、BS-028 / BS-032 补减减值准备：发布脚本（`publish_global`，幂等）+ 种子 / 生成器 / 按名回填拦截 + 测试（R6.4）
  - 证据：`scripts/fix/fix_report_bs_book_value_formulas.py`；`tests/formula_settings/test_fix_report_bs_book_value_formulas.py` 5 例
    （预览不写 / 必须留底 / 四准则发布 + 跟随副本更新 + 改过的行进待确认 + 传播 + 重跑不再发布 / 行名漂移一个都不发布 / 真库留底）；
    `four_table/test_h6_report_tier_closed.py` 7 例；新守卫「置空的派生行必须按名拦住」11 例；
    变异 M3 来源 / M4 不留底 / M5 固定资产不减 1603 / M7 不传播 / M8 先发布后校验 / M9 filler 恢复 1901 / M10 / M10b 拦截集合删条目 /
    M11 H6 打开层③ 全部打红（M10 首轮存活 → 补守卫后打红）
  - 真库已发布（四个准则 v1→v2，无冲突、无待确认），留底与传播结果见 design §10.1；`test_i_cycle_row_code_evidence.py` 连库绿
- [x] 2.6 推送 dry-run：和平 2025 / 安徽 2025 改动前后逐地址对比，变化逐条可解释（R6.5）
  - 证据：base（bf759b369）→ 现状逐地址对比：G / H / I / K 审定合计由恒 0 改为按底稿行清单的实数（H1 / H8 / H9 有行清单）或写空
    （底稿未存行清单）；H1 / I1 附注按账面价值行写入；F2 见 2.2；D5 / K4 规则删除；D6 / H2 附注合计与人工格变化来自并发会话
    `note_writer` 六列对称兜底（不在本 spec）。报表公式发布前后推送结果逐地址 0 变化。

## 3. 映射表（R1）

- [x] 3.1 全表探针：映射码 vs 标准科目表 / 真库科目表 / 口径单一来源；`report_row` vs `report_config` 行名（R1.1~R1.3）
  - 证据：探针固化为守卫 `test_wp_account_mapping_single_source.py`（码形态 / 静态存在 / 真库 `account_chart` 104 码全在 / 族级 ⊆ 单一来源 /
    函证族 / 条目名对科目名 / 修正脚本生效，植入错码自检 11 例）；`report_row` 只核对与登记（勘误文档第二批末段，99 条有值只 18 条对得上）
- [x] 3.2 修正脚本扩展（J2 / J3 / L7 / M3~M10 / K4 / D5 及探针新发现）+ 勘误文档；`--apply` 后 `--check` 通过（R1.1~R1.3）
  - 证据：`fix_wp_account_mapping_wrong_codes.py` 第二~四批（M / J / L / K4 / D5 / H6~H9 / I1 / I5 / F2-55~58；G6 / G8 / K2；F2 子条目 / E0-4 / E0-5），
    改为修正链（同一条目多批改正、链外值拒绝覆盖），`--check` 183 项幂等；`scripts/validate_seed_files.py` 7/7；勘误文档第二~四批
  - 探针新发现并修：调整到达通知、底稿一键刷新两个读取方从未读到映射（design §10.5）；登记未修：§10.3 第 15~18 条
- [x] 3.3 4xxx 写死码统一（前端 M 组合函数 / 后端 M 服务与路由 / phase5 / equity_method），逐处现读用途（R1.4）
  - 证据：前端 `mCycleAccountScope` 单一来源 + `mCycleAccountCodes` / `mCycleAccountRuntime` / `gCycleOciAccount` 守卫；后端
    `test_m_cycle_account_single_source.py` 41 例；变异前端 22 条、后端 12 条全部打红；M 相关后端失败集与 HEAD 逐条一致（117 例）
  - 触类旁通（design §10.4）：J2 / K1 / K2 / K4 / K5 / L3 / L6 / L7 的带入调整、发布、事件码、调整分录码与文案改用各自真源；
    新守卫 `cycleWrongLegacyAccountCodes.spec.ts` 51 例（零容忍组 + G1 / I2 / I5 / I6 棘轮 + 带入码 ⊆ 映射 + 运行态）；变异 FB1~FB29 全部打红；
    单区域 vue-tsc 与 HEAD 对比新增 0、消除 1（K4 宿主 / 审定表 tbData 形状不符 TS2739），注入 TS2322 被报出
  - 未改并登记：design §10.3 第 6~14 条（报表 OCI 公式 3102、I 循环旧码、G 循环 1501、K1-4 宽口径、L7 发布假成功等）
- [x] 3.4 派生物：补 `gen_account_to_wp_ts.py`（`--check`）并重生成前端映射；重生成 `note_template_bindings.json` / 覆盖率并解释 diff（R1.5）
  - 证据：生成器 `scripts/gen/gen_account_to_wp_ts.py`，`accountToWpMapping.ts` 98 → 104 行（删 17 / 增 23 / 改名 8，逐条见 design §10.5）；
    守卫「表 = 生成器输出」+ 字面量抽样（`test_wp_account_mapping_single_source.py`）、M 名码配对守卫补 prefix / wpName 写法；
    `formula_push_coverage.json` 只变 F2 `account_prefixes`（`--check` 通过）
  - 偏离：附注模板绑定做了隔离实验（映射改动 5 节 289 格、模板陈旧 42 格），因映射表 `note_section` 编号陈旧且多族共用，重生成会让两节由取 0 变成取错科目，
    未提交，拆为 3.6 待拍板（design §10.3 第 19 条）
- [ ] 3.6 附注模板绑定按新映射重生成 —— 待拍板：先定 `note_section` 按准则分列 / 按科目名关联，再改生成器按行级绑定（design §10.3 第 19 条）
- [x] 3.5 守卫 `test_wp_account_mapping_single_source.py` + 读取方行为变化钉住（R1.6）
  - 证据：守卫见 3.1；读取方 `test_wp_generation_matching.py`（26 组科目 → 生成底稿 + 开关码 + AST 判编排器不另写码表）、
    `test_wp_account_mapping_readers.py`（按科目找底稿 / 一键刷新取数科目 / 真 SQLite 调整到达通知 3 例 / 真库只读一键刷新）、
    `test_data_file_paths_resolve.py`（174 处数据文件路径静态求值，3 处登记）；陈旧测试 `test_note_direct_integration` / `test_note_direct_binding` 改正
  - 变异：MW1~MW7（提交 `12ece3df4`）、MS1~MS12 + MS11b（映射退回旧码 / 判据失效 / 修正链 / 子科目兜底 / 通知与一键刷新退回旧实现 /
    登记失效）全部打红后逐字节恢复

## 4. 鉴权（R4）

- [x] 4.1 地址库端点项目只读权限、清空全部缓存仅管理员；端点测试（401 / 403 / 成员可用）（R4.1）
  - 证据：`test_address_registry_authz.py` 41 例（权限世界：只读 / 复核 / 编辑级成员与非成员管理员放行、非成员 403、未登录 401、非 UUID 422、
    清空全部仅管理员、`jump` / `parse` 不经项目门禁）；旧测试 `test_address_registry_limit` / `_offloop` 改管理员 + UUID 项目，三文件 75 passed；
    变异 MA1~MA7 全部打红（design §10.7）
- [ ] 4.2 生成底稿与新建自定义底稿端点项目编辑权限；前端入口按权限；端点测试含该放行角色（R4.2）
  - 前端已改：底稿管理页两个入口按本项目编辑权限且未归档显示，`workpaperListCreateGate.spec.ts` 3 例；单区域 vue-tsc 本文件 0 错（注入错误被报出）
  - 未完成：后端门禁在并发 spec `procedure-trim-generation-delegation-chain` 任务 6 的工作树改动里（同文件、未入库），本 spec 不改该文件；入库后补端点测试
- [ ] 4.3 模板清单端点项目只读权限（R4.3）—— 同 4.2：门禁在并发 spec 未入库的改动里，入库后补端点测试
- [x] 4.4 `mcp_tools` / `address_mention` 按项目口径与审计年度（R4.4）
  - 证据：`project_address_scope`（年度单一真源、口径归一、只读）；mention 改在全部地址里找（原只看前 500 条）；MCP 上下文年度回退审计期末；
    `test_ai_chat_address_project_scope.py` 7 例 + MCP / mention 既有测试共 95 passed；变异 MM1~MM6 全部打红
- [ ] 4.5 鉴权基线按现算下调、新端点钉进 `_FIXED_ENDPOINTS`（R4.5）
  - 已做：本维 93 → 87、地址库五端点进 `_FIXED_ENDPOINTS`、变异扩到签名里的依赖、`jump` 登记为刻意仅登录（可伪证）；变异 MB1 / MB2 打红
  - 未完成：路径维（生成底稿五端点）待 4.2 后端入库后下调并逐个钉住

## 5. 引用校验（R5）

- [x] 5.1 `formula_ref_check` 模块（TB 前缀 / 报表按准则 / 附注按结构，模板兜底）+ `validate_formula_refs` 改调（R5.2）
  - 证据：`test_formula_ref_check.py` 判定口径 23 例（期望写死）+ 原因文案 + 模板兜底（含只剩已删除章节）+ 三域路由；
    变异 MR1~MR9 全部打红（MR6 首轮存活：已删除章节在第二层取数时也被过滤，补「原因 = 没有章节」与「只剩已删除也按模板」后打红）
- [x] 5.2 `full_resolve` 非底稿域：单引用判定、有项目按数据、无项目返回无法确认；身份类调用方显式不校验；GET 加项目参数（R5.1）
  - 证据：核对放新模块 `acnr/non_wp_verification.py`，请求级复用判定器；只建身份的 4 类调用方显式 `verify_existence=False`；
    `ResolveRefResult.dangling` 不把「无法确认」算悬空；公式导入 / 新增预设逐个引用校验（原整条表达式当一个引用）；GET 带项目先鉴权；
    变异 MR10~MR14、MR20~MR23 打红（MR10 首轮存活：有项目时第二道检查兜住，补「复合 + 无项目」用例后打红）；陈旧测试 8 个文件按新口径改写
- [x] 5.3 附注公式保存服务端校验（422 列明原因）；附注执行器 NOTE 按行 / 列取数（R5.3）
  - 证据：`test_note_formula_save_ref_check.py`（真路由：悬空 422 + 每条带单元格 + 不写库；有效则保存）；执行器 NOTE 按行列、TB 按前缀、
    参数间空格、排除已删除附注；变异 MR15~MR19 打红。偏离：错误码沿用 `FORMULA_DANGLING_REFS`（与报表 / 底稿公式保存同契约）
- [x] 5.4 前端：`addressRegistry.validate` 只对单个 WP 引用短路、解析带项目上下文、按 `found` 拦截的调用方改正；vitest（R5.4）
  - 证据：`addressRegistry.validateRefScope.spec.ts`、`useAcnr_resolve_project.spec.ts`、`GtFormulaEditDialog.spec.ts` 补 3 组、
    `GtIndexChip.spec.ts` 补 1 例（非底稿引用不存在时显示后端原因）；变异 MF1~MF7 打红（红在预期断言上）；单区域 vue-tsc 见 7.1
  - 回归：涉及的 102 个后端测试文件与基线 `9eb504a5e` 逐条对比新增失败 0；前端相关 7 文件 58 passed

## 6. 三参 PREV 定位表与陈旧测试（R2 / R3）

- [x] 6.1 生成器 + 定位表（扫模板、歧义格人工裁定、幂等、`--check`）（R2.1 / R2.2）
  - 证据：`scripts/gen/gen_prev3_prefill_locator.py`（`--check` 漂移 exit 2、`--report` 审阅清单、`MANUAL` 34 条各写原因、失效 / 缺原因即中止）；
    `data/prev3_prefill_locator.json` 192 格（verify 167 / write 3 / none 22，85 本模板指纹），`--check` 通过、重跑无差异
  - 偏离：覆盖全部映射块的三参格（设计稿只算首块）；审定表族按「原值小计 → 差异数核对行 → 首个合计行」落行（design §10.9）
- [x] 6.2 初次预填按定位表：路由解析上年值、`write` 写值、`verify` 批注、取不到写原因；重新预填落格查定位表（R2.3 / R2.4）
  - 证据：`services/prev3_prefill_locator.py`（`resolve_prev_prefill` / `override_prefills` / `apply_prefills` / `locate`）；
    `prefill_workpaper_xlsx(prev_values=…)` 首块循环跳过三参格；`get_workpaper_xlsx` 传上年值；`wp_effective.locate_cell` 三参格只认定位表；
    一并修 `_get_tb_data_for_prefill` 按审计年度 + 排除已删除（ORM、保存点）
- [x] 6.3 守卫与变异（R2.5）
  - 证据：`test_prev3_prefill_locator.py` 15 例（定位表 = 生成器输出、映射三参格一一对应、目标格对模板逐格核对、列头上年语义、同格同参、
    模板列头改动使 `--check` 红、写值 / 批注 / 取不到 / 去重、模板不符与用户公式格不落、初次预填不猜格、重新预填只认定位表、取值与原因、
    试算表按年度与删除标记、路由首次打开端到端）；变异 MR2a~MR2o 15 条全部打红后逐字节恢复
- [x] 6.4 改写 `test_prefill_wp_prev_resolution.py`、`four_table/test_k_cycle_preset_closure.py`（R3）
  - 证据：前者 1037 → 523 行 28 例、后者 33 例全过；变异 MR3a~MR3h 8 条全部打红；`prefill_anchor_map.OUT_OF_SCOPE_CHANGES['prev_year_dimension']` 改为现行说法
  - 回归：引用改动模块的 186 个测试文件与基线 `3c8fe7726` 逐条对比，新增失败 0、消除 18（双方其余 93 例相同，预存）
- [x] 6.5 同根陈旧测试（`2638b32fd` 删 `_FORMULA_RESOLVERS` / `_resolve_*_formula` / `_resolve_tb_aux` 后整文件或部分红）按现行预载层 + L1 改写：
  `test_e1_formula_types` / `test_h_ledger_formula` / `test_k_prefill_ledger_detail`（收集即错）、`test_adj_formula_resolution` /
  `test_adj_domain_caliber_boundaries` / `test_adj_e2e_integration` / `test_f_prefill_extension` / `test_formula_runtime_zero_regression` /
  `test_formula_wp_semantics` / `test_user_formulas_override`；改写中发现的取数缺陷逐条复现后修或登记待拍板
  - 证据：10 个文件按真 SQLite + 现行入口改写全过；改写中复现并修 4 个取数缺陷（三参 WP 恒 0 与同名锚点互相覆盖、LEDGER_DETAIL 恒 0 笔、
    COUNT_LEDGER 期间被忽略、方向 / 期间 / 金额条件写错给错数），见 design §10.10；真库对齐锚点「预载 + L1」与直接读锚点逐条相等
  - 变异 MR65a~MR65q 17 条（后端 16 + 前端 1）全部打红；回归 360 个测试文件对比 `988c6809b` 新增失败 0、消除 30
  - 偏离：`test_f_prefill_extension` 不同根（`5783c4ffe` 有意改为 WP 联动），按其防循环引用的本意改写；L1 序时账三函数「未预载」由返回 0 改为报错，
    收敛 spec 的两个用例随之改
  - 待拍板：F2 盘点 9 格「期末数量 / 期末金额」的取数口径、J1 月度分析 21 格四参写法、LEDGER_DETAIL 写笔数还是写明细清单（design §10.10 范围外）
- [x] 6.6 `report_engine.evaluate_formula_result` 的 `enable_prev` 死分支；运行时改写已跟踪文件的测试（`tests/_snapshots/workpaper_route_task1_baseline.json`、归档证据）
  - 证据：删 `enable_prev` / `enable_aux` 与两段从不运行的取数（其一从不存在的 `four_table_models` 导入）；公式调试上下文改走统一预载
    （原从不存在的模块导入、试算表恒空），真 SQLite 按值断言 + 端点级缺口进 `warnings`；lazy import 守卫不再豁免 `except Exception`
    （新暴露 11 条：3 条随删除消失、8 条冻结）；表间审核严格取数补用例。干净检出跑 142 + 190 个候选测试文件找改写已跟踪文件的用例：
    快照用例与 4 处归档证据（task14 / 15 / 17 / go-live task6，task5 已 skip 同改）全部改为不写仓库；新增守卫 `tests/_tracked_write_guard.py`
    （root conftest 登记，本进程改写已跟踪文件不还原 ⇒ 点名并置退出码 1；同批 213 例交替开关各跑 2 次，耗时差在噪声内）
  - 同根顺带：两条随本节失效的源码锚点守卫改按行为 / AST 判；`_FALLBACK_KNOWN_FUNCS` 补齐漏同步的 5 个函数、`_known_acnr_funcs` 扣除待迁移白名单
    （序时账三函数与 PLACEHOLDER 原被误判已迁移），预存红 4 例转绿
  - 变异 MR66a~MR66k、MG1~MG10、MS1~MS5 全部打红在预期断言上；回归（提交树干净检出）新增失败 0、消除 4，见 design §10.11

## 7. 回归与交付（R10）

- [ ] 7.1 变异汇总；定向回归（改动涉及的全部测试目录）对比 base；前端相关 vitest + 单区域 vue-tsc
- [ ] 7.2 浏览器实测：地址选择器 / 附注公式保存悬空提示 / 生成底稿入口权限 / 初次预填批注（【测试】项目）
- [ ] 7.3 提交推送到 `spec/disclosure-note-doc-upload-and-batch-fill`；INDEX / memory 更新

## 8. 年度兜底（另立 spec）

- [x] 8.1 另立 spec `audit-year-calendar-fallback-ratchet`（三件套），先加只许减少的守卫：前端拿不到审计年度时用今年的写法（251 处）；
  后端同类（`wp_prefill_preview.py` 两处 `year = 2025`）一并登记
  - 证据：三件套已建；守卫即该 spec 任务 1：前端 vitest 按文件冻结 340 处 / 288 个文件（兜底写法 251 处，与原记一致；另含初值 / 实参等 89 处）、
    后端 AST pytest 冻结 130 处 / 72 个文件（含 `wp_prefill_preview.py` 两处）；变异 MY1~MY9 / MB1~MB7 全部打红。逐处判定与收口在该 spec 任务 2~7
