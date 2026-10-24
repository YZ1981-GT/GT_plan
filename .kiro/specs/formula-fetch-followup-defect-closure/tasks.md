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

- [ ] 4.1 地址库端点项目只读权限、清空全部缓存仅管理员；端点测试（401 / 403 / 成员可用）（R4.1）
- [ ] 4.2 生成底稿与新建自定义底稿端点项目编辑权限；前端入口按权限；端点测试含该放行角色（R4.2）
- [ ] 4.3 模板清单端点项目只读权限（R4.3）
- [ ] 4.4 `mcp_tools` / `address_mention` 按项目口径与审计年度（R4.4）
- [ ] 4.5 鉴权基线按现算下调、新端点钉进 `_FIXED_ENDPOINTS`（R4.5）

## 5. 引用校验（R5）

- [ ] 5.1 `formula_ref_check` 模块（TB 前缀 / 报表按准则 / 附注按结构，模板兜底）+ `validate_formula_refs` 改调（R5.2）
- [ ] 5.2 `full_resolve` 非底稿域：单引用判定、有项目按数据、无项目返回无法确认；身份类调用方显式不校验；GET 加项目参数（R5.1）
- [ ] 5.3 附注公式保存服务端校验（422 列明原因）；附注执行器 NOTE 按行 / 列取数（R5.3）
- [ ] 5.4 前端：`addressRegistry.validate` 只对单个 WP 引用短路、解析带项目上下文、按 `found` 拦截的调用方改正；vitest（R5.4）

## 6. 三参 PREV 定位表与陈旧测试（R2 / R3）

- [ ] 6.1 生成器 + 定位表（扫模板、歧义格人工裁定、幂等、`--check`）（R2.1 / R2.2）
- [ ] 6.2 初次预填按定位表：路由解析上年值、`write` 写值、`verify` 批注、取不到写原因；重新预填落格查定位表（R2.3 / R2.4）
- [ ] 6.3 守卫与变异（R2.5）
- [ ] 6.4 改写 `test_prefill_wp_prev_resolution.py`、`four_table/test_k_cycle_preset_closure.py`（R3）

## 7. 回归与交付（R10）

- [ ] 7.1 变异汇总；定向回归（改动涉及的全部测试目录）对比 base；前端相关 vitest + 单区域 vue-tsc
- [ ] 7.2 浏览器实测：地址选择器 / 附注公式保存悬空提示 / 生成底稿入口权限 / 初次预填批注（【测试】项目）
- [ ] 7.3 提交推送到 `spec/disclosure-note-doc-upload-and-batch-fill`；INDEX / memory 更新
