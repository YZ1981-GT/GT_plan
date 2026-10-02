# 任务清单：合并企业树按三码自动构建

> 需求：#[[file:.kiro/specs/consol-tree-three-code-autobuild/requirements.md]]
> 设计：#[[file:.kiro/specs/consol-tree-three-code-autobuild/design.md]]
> 顺序：建项段（1~4）→ 树与链接（5~6）→ 计算口径（7~8）→ 接口（9）→ 前端（10~12）→ 母公司列（13）→ 验证（14）。
> 纪律：每个任务开始前现读相关文件（工作树有并发会话改动）；标完成必须有代码与测试证据；PBT `max_examples=5`。

- [x] 1. 数据层 V167 / R167
  - [x] 1.1 迁移 `projects.relation_to_parent`（CHECK 子公司/分公司）+ `elimination_entries.branch_entity_code` + 两个索引，幂等
  - [x] 1.2 回滚脚本逆序删除；ORM `Project.relation_to_parent`、`EliminationEntry.branch_entity_code` 三层一致
  - [x] 1.3 模型注释登记 `consol_worksheet.node_company_code` 存 `node_key`、`projects.consolidation_type` 不再读写
  - 证据：2026-09-29 真库执行 V167 成功（2 列 + CHECK + 2 索引现查存在）；`/api/health` applied=167、critical drift 0
  - _需求：6.1, 7.1, 4.3_

- [x] 2. 与上级关系默认规则（前后端共用夹具）
  - [x] 2.1 夹具 `backend/data/relation_to_parent_cases.json`（含真库 7 个企业名 + 边界用例）
  - [x] 2.2 后端 `app/services/group_relation.py`：`infer_relation_from_name` + `normalize_relation`
  - [x] 2.3 前端 `src/utils/groupRelation.ts` 同规则；pytest 与 vitest 逐条跑同一夹具（P11）
  - 证据：`test_group_relation.py` 35 passed；`groupRelation.spec.ts` 27 passed；真库 7 名仅临港店判分公司
  - _需求：2.1, 2.2_

- [x] 3. 建项后端
  - [x] 3.1 `BasicInfoSchema` 加 `relation_to_parent`；上级/控制方代码非空过 USCC、上级≠本企业、关系取值校验
  - [x] 3.2 `_sync_basic_info_to_project` 写关系（上级为空则清空；缺省按名称补）；不再按报表类型清空合并类型
  - [x] 3.3 两口径同步 helper（新建继承、保存外推），响应带 `notices`；`ProjectCreateResponse` 增加三码/名称/关系
  - [x] 3.4 `PUT /config` 拒写 `consolidation_type`（400），`GET /config` 不再返回该字段
  - [x] 3.5 批量模板第 10 列「与上级关系(relation)」+ 下拉 + 说明；解析/预校验/导出；旧 9 列兼容（P12）
  - [x] 3.6 连续审计继承关系、不复制 `parent_project_id`
  - [x] 3.7 测试：向导服务、批量建项、连续审计、配置接口
  - 证据（2026-09-29）：新增 `app/services/group_links.py`；新测试 `test_group_links.py` 31 例、
    `test_project_config_consolidation_type.py` 7 例（真发请求）、向导路由 `TestGroupFieldsEndpoints` 6 例、
    批量 6 例（含 P12 旧 9 列与新模板空关系列两库对比、模板下拉 `J2:J501`）、连续审计真 SQLite 5 例；
    回归 15 个文件 319 passed，余 2 红经归因为 HEAD 预存（见 design §十二）；9 条源码变异全部被咬住；
    连续审计在真 PG 回滚探针 8/8 成功（1 例下年已存在按业务拒绝），事务未毒化、无数据残留。
    顺带修复预存：向导两份测试 helper 缺必填字段（27 条 HEAD 即红，其中 3 条断言随 2026-06-05
    「确认无前置依赖」口径同步）；连续审计映射属性名、第 8 步残缺 SQL 毒化事务、试算未按年度过滤
  - 口径更正（2026-09-29 用户）：需求 1.5 由「上级=本企业拒绝保存」改为「请用户确认本企业就是上级企业，
    三码相同即最终控制方」。后端改为照存、关系置空、不拿自己当上级补控制方、说明只在含义变化时出一次；
    批量导入由行错误改为预校验提示（`BatchValidateResponse.warnings`）；判定集中在
    `group_relation.effective_parent_code` / `self_reference_kind`，共享夹具新增 `self_reference_cases` 9 条。
    后端回归 165 passed；3 条后端变异（有效上级判定、说明去重、预校验提示）全部被咬住
  - _需求：1.4~1.9, 2.3, 2.4, 4.5, 7.4_

- [x] 4. 建项前端
  - [x] 4.1 `stores/wizard.ts` 类型与创建请求对所有报表类型发三码与关系；回填恢复三码与关系
  - [x] 4.2 `BasicInfoStep.vue`：「集团架构」分组对所有项目显示、关系下拉联动、校验、移除合并类型单选、改提示文案
  - [x] 4.3 vitest：显示条件、置灰与必填、名称默认、手动选择不被覆盖
  - 证据（2026-09-29）：`BasicInfoStep.group.spec.ts` 9 例、`wizard.group.spec.ts` 4 例、`groupRelation.spec.ts`
    38 例（含 `self_reference_cases`），向导相关 vitest 68 passed；5 条前端变异全部被咬住；ESLint 0 error。
    上级=本企业：保存前弹确认（两种文案），取消不保存，已确认/回填的同一组代码不重复问。
    `ConsolidationIndex` 合并方式单选改为只读标签（接口已拒写），识别结果待任务 10.4 接入。
    Playwright（真后端 + 真库）：新建单户项目三码相同 ⇒ 确认框 ⇒ 取消未落库 ⇒ 确认后创建，请求体带三码、
    响应 `notices` 为「三个代码相同…」；编辑回填三码、未改代码保存不弹框；清空控制方代码 ⇒ 改问「本企业就是上级企业」
    ⇒ 保存响应说明正确、库内关系为空；实测项目已清理（引用列 216 个均无关联行）。
    截图 `.playwright-mcp/ctree-wizard-{self-parent,confirm-ultimate,confirm-top}.png`。
    环境注记：并发会话持续改后端文件致 uvicorn 频繁重载，实测中两次请求被重载中断（与本改动无关，重试通过）
  - _需求：1.1~1.3, 1.5, 1.6, 1.7_

- [x] 5. 企业树推导（纯函数）
  - [x] 5.1 `consol_group_tree.py`：实体合并、关系边、脱挂、确定性断环、三节点、母分展开、提升与 via、诊断
  - [x] 5.2 `TreeNode` 扩展 `node_key/role/kind/relation/host_project_id/flags/display_name`（旧字段与位置不变）；
        `to_dict` 保留旧键并追加新键；`find_node` 兼容纯代码；新增 `find_node_by_key`、`iter_nodes`
  - [x] 5.3 `build_tree` 改为三码推导（签名不变），附带 `mode` 与诊断
  - [x] 5.4 属性测试 P1~P4、P6；示例：多级合并、提升、并存模式、母公司未建单体、年度隔离
  - 证据（2026-09-29）：`test_consol_group_tree.py` 29 passed（含 P1~P6 hypothesis max_examples=5、
    上级=本企业不建自环、断环、脱挂、按控制方挂靠、分公司再有分公司、分公司自带合并项目、真 SQLite 装载）；
    另用一次性探针跑 3000 例随机集团校验 P1~P6 + 派生链接与树放置一致：首轮抓到「两家互为控制方 ⇒ 挂靠成环」
    的 P6 反例，改为挂靠边与上级边合并检测断环后 0 失败（分公司自带合并项目的双重消费按 design §3.3 登记，不比对）。
    预期打红：以 `parent_project_id` 造树的旧合并测试 15 条（`test_consol_worksheet.py` 13、全链路 2），任务 7 按新模型改写
  - _需求：3.1~3.9, 4.1, 4.2_

- [x] 6. 派生链接 `sync_group_links`
  - [x] 6.1 按年度一次推导并只写变化行；返回受影响合并项目 ⇒ 广播范围变更 + 标记陈旧
  - [x] 6.2 接入写路径：建项、保存基本信息、PATCH 上级代码（两口径同写）、attach（改写三码）、批量导入、
        连续审计、删除/批量删除、回收站恢复、配置改报表类型、准则统一写报表类型
  - [x] 6.3 `available-subsidiaries` 按树排除已纳入项目并带推断关系
  - [x] 6.4 运维脚本 `scripts/ops/resync_group_links.py [--year] [--dry-run]`
  - [x] 6.5 测试：顺序无关与幂等（P5）、各写路径触发、连续审计不串年
  - 证据（2026-09-29）：`group_links.sync_group_links`（整年推导、只写变化行、受影响合并项目的合并试算标陈旧、
    广播挂到提交之后且回滚丢弃）；`test_group_links_sync.py` 13 passed（含 10 条写路径、端点真发请求）；
    17 条源码变异全部被咬住（首轮「连续审计不重算」未咬住，补「新年度合并项目已存在再结转」用例后咬住）；
    真库 `resync_group_links.py --dry-run`：2024/2025/2099 三个年度需更正 0 个（三码全空，推导值与库存一致）。
    顺带：PATCH 上级代码的审计日志写入放进 SAVEPOINT；旧 `_would_form_cycle`（跨年、按项目、把上级=本企业判环）
    由同年度实体级 `would_form_cycle` 取代；批量导入删除逐行找项目写链接的旧逻辑（`_resolve_parent_project`）。
    口径变更的旧断言：`test_parent_code_update.py`（合法代码、自引用改 200、脱挂链接改为集团合并项目）、
    `test_batch_project_service.py::test_parse_and_import_intra_batch_parent_link`，均在 docstring 注明
  - _需求：7.1~7.6, 11.3_

- [x] 7. 计算口径统一
  - [x] 7.1 `consol_calc_basis.py`：科目方向 `sign(a)`、分录归属 `attribute_entry`、装载子树已审批分录
  - [x] 7.2 差额表引擎：数据叶子/差额/汇总三类节点、明细行口径、调整与抵销分列、清理旧行
  - [x] 7.3 B1 汇总取全部数据叶子，溯源加 `node_key/role`
  - [x] 7.4 合并试算：删除 branch 跳过分支，抵销/调整取归属后的归一金额，为只在分录出现的科目建行
  - [x] 7.5 对账、节点汇总、穿透、透视、附注汇总、披露、完整度、级联刷新改按 `node_key` 与数据叶子
  - [x] 7.6 测试：P7~P10（真 ORM 行）、全链路集成测试按新模型改写、旧断言逐条注明口径变更
  - 证据（2026-09-29）：新模块 `consol_calc_basis`（纯函数 `build_calc_basis/node_values/worksheet_rows/trial_amounts`
    + 薄装载 `load_calc_basis`），差额表 `recalc_full` 与试算 `recalculate_trial` 只调它；金额输入先到分
    （库列 `Numeric(20,2)`，派生值落库后逐分恒等）；明细行坏数据（非列表、金额无法识别、有金额无科目）⇒ 孤儿并列原因。
    差额表：键 `node_key`、结果外旧行软删、软删行复活不新插、重跑零写入（幂等）；删除死代码 `_calc_node` 等 4 个 helper。
    试算：`sync_trial_rows` 为只在分录里出现的科目建行、消失科目清零、同科目重复行只留一行。
    消费方：对账取根 `node_key`（两路同源后差异即缺陷，日志升 error）；汇总/穿透/透视按 `node_key`（纯代码兼容），
    透视表头用展示名并返回 `node_keys`；穿透分录与金额同一归属函数、带计入标记与孤儿原因；附注汇总/披露/完整度改数据叶子
    （披露家数只数子公司企业，没有单户项目的叶子不取数；完整度对无单户叶子直接提示不查库）；级联刷新进度标签用展示名；
    三形式差额表加节点列并排除软删行；报表穿透透传节点溯源键。
    测试：`test_consol_calc_basis.py` 9 passed（P7/P9 hypothesis、P8 真 SQLite 随机集团、P10 示例、归属各分支）；
    `test_consol_worksheet.py` 22、`test_consol_full_chain_integration.py` 5、`test_consol_completeness.py` 8 按新模型改写；
    合并相关回归 204 passed。一次性探针放大到 P7/P9 400 例 + P8 真 SQLite 80 例 0 失败；21 条源码变异全部咬住
    （首轮 2 条存活：明细行非列表、附注取数含空项目 —— 补用例后咬住）。
    口径变更的旧断言（均在 docstring 注明）：中间节点不含本体、按 related 分摊抵销、branch 跳过抵销、
    叶子=无子节点、透视表头=原始代码、完整度/附注取全部后代、`_calc_node_batch` 纯逻辑用例改为口径模块用例
  - _需求：5.1~5.9, 6.3, 6.4_

- [x] 8. 分录归属与服务修复
  - [x] 8.1 schema 增 `branch_entity_code`（Create/Update/Response，响应补 `related_company_codes`）
  - [x] 8.2 创建/修改校验归属节点（承载项目一致），错误信息说明应在哪个合并项目录入
  - [x] 8.3 修改同步明细行与代表科目；`get_entry` 排除软删；列表按节点筛选
  - [x] 8.4 自动生成草稿按交易双方最近公共节点预填归属
  - [x] 8.5 测试：归属校验、孤儿分录诊断、修改后明细行生效
  - 证据（2026-09-29）：`elimination_service.validate_entry_attribution` 调用与金额计算同一个
    `consol_calc_basis.attribute_entry`（能保存 ⇔ 会被计入）；非合并项目、找不到母分差额节点、由其他合并项目承载
    ⇒ 400 并说明应到哪个合并项目录入；明细行为空/缺科目/借贷不平衡拦截。修改：明细行、表头代表科目、借贷合计同步，
    改归属重新校验（显式 null 改回合并差额，不传不改）；`get_entry` 排除软删（删除后读/改/再删均视为不存在）；
    列表 `node_key` 筛选（非差额节点 400）。响应补 `related_company_codes`（历史 dict 归一成列表）与 `branch_entity_code`，
    旧数据无明细行时 `lines` 返回空列表。自动草稿：`suggest_branch_entity` 按交易各方数据叶子的公共祖先向上找
    本项目承载的母分差额，否则留空；建树放进 SAVEPOINT。
    测试：`test_elimination_attribution.py` 14 passed（服务 + 端点真发请求，鉴权走真实 `require_project_access`：
    非成员 403、只读成员可列表不可新增）；15 条变异 14 条咬住，存活的 1 条是死代码（母分差额不会出现在合并节点之上，
    已删除该判断并注明原因）。口径变更的旧断言：`test_elimination.py` 夹具改为带企业代码与年度的合并项目（docstring 注明）
  - _需求：6.1~6.6_

- [x] 9. 接口
  - [x] 9.1 `GET /worksheet/tree` 返回 `{tree, mode, diagnostics, year}`；新增 `GET /worksheet/accounts`
  - [x] 9.2 `GET /api/projects/tree`：可见性过滤、实体节点合并两口径、统一年度解析、按（控制方,年度）分树
  - [x] 9.3 端点测试（真发请求，含非 admin 可见性 P14）
  - 证据（2026-09-30）：`consol_tree_service.build_tree_view` ⇒ 树接口返回 `{tree, mode, mode_label, diagnostics, year}`
    （保留 `tree` 键，项目不存在时 `tree=None` 并给说明）；诊断 = 树推导诊断 + 本树分录中找不到归属的
    （`consol_calc_basis.attribute_entries` 与重算共用：已审批的就是重算没计入的同一批，草稿等提示先改归属）。
    新增 `GET /worksheet/accounts`：数据叶子试算表科目 ∪ 本树分录明细行科目（含未审批），名称/类别/方向与计算口径
    同一取法（`_canonical_tb_rows` + `account_sign`），带来源标记；只读权限。
    森林改为新模块 `group_forest`（批量预览与 `/api/projects/tree` 共用，需求 8.6）：企业节点列出两口径项目
    （`projects/consolidatedProjectId/standaloneProjectId`，同口径重复也列出并标记）、年度按统一 5 级解析且属性缺省安全、
    未传年度按（控制方, 年度）分树（`key/year`）、上级边与合并树同源（`build_entity_graph`）、没有上级的按控制方挂靠
    （`attach_to_controllers` 不要求控制方有合并项目，合并树的挂靠规则不变）、报表类型筛选后被筛掉的中间企业由下级
    接替并记 `via`；可见性按 `get_visible_project_ids` 同口径，上级确有项目只是不可见 ⇒ 标 `parent_hidden` 不标脱挂、
    不泄露上级任何字段。旧键（`id/label/companyCode/…/isDetached/isCycleBreak/hasNoCompanyCode`）不变。
    顺带：合并范围校对改取合并企业树的子公司类企业（需求 11.3，分公司与母公司不算成员），年度改统一解析；
    分录审批流补「提交审批」（草稿/已驳回 → 待审批），提交与审批前重新校验归属（能审批 ⇔ 会被计入）；
    批量预览树构建失败改为记日志（原先静默为空）；森林富集查询放进 SAVEPOINT。
    测试：`test_group_forest.py` 21（含 hypothesis 顺序无关 + 每项目恰一次 + 一树一年度）、
    `test_ctree_endpoints.py` 16（真发请求，真实 `require_project_access`：P14 审计员只见参与项目、经理无成员为空、
    admin/partner 全见、上级不可见不标脱挂（含只能靠项目名解析年度的旧上级）、树接口字段/诊断/403、科目接口、
    审批流、合并范围成员）；`test_consol_group_tree.py` 补「控制方无合并项目不挂靠」1 例。
    回归：树/森林/批量/合并范围/合并计算/分录/链接相关 21 个文件 356 passed、2 skipped。
    变异 36 条：首轮 35 咬住，存活 1 条（合并树挂靠放宽为不要求控制方有合并项目）⇒ 补用例后咬住。
    口径变更：森林节点以企业为单位（旧版同代码两口径后者覆盖前者）、年度统一解析（旧版只看期末日）；
    `test_consol_tree_by_codes.py`、`test_group_tree_endpoint.py`、`test_batch_project_service.py` 旧用例原样通过
  - _需求：3, 8.1~8.3, 8.6, 9.1_

- [x] 10. 合并页前端
  - [x] 10.1 `consolidationApi.ts` 类型：节点新字段、树响应、分录 `branch_entity_code`
  - [x] 10.2 `OrgNode.vue` / 树形列表：`node_key` 作键、角色样式与标签、「进入项目」仅对有项目节点
  - [x] 10.3 `ConsolMiddleNav.vue`：只渲染后端树，删除自造差额节点、「添加」「同步」与手工企业存储
  - [x] 10.4 `ConsolidationIndex.vue`：头部识别标签替换单选、诊断提示、差额节点事件处理
  - [x] 10.5 新组件 `ConsolElimNodePanel.vue`：分录列表/新增/修改/删草稿/审批、只读承载提示
  - [x] 10.6 `ConsolWorksheetTabs.vue` 公司列回退与总分汇总提示；`ConsolNoteTab.vue` 汇总树键改 `node_key`
  - [x] 10.7 vitest：节点渲染与键、差额面板表单
  - 证据：vitest 4 文件 29 passed（`consolTreeView` / `elimNodePanel` / `ConsolTreeComponents` / `ConsolElimNodePanel`）；
    改动文件 ESLint 0 error（4 条 warning 均在未改动行，既存）；vue-tsc 单区域 exit 0（注入 TS2322 两例均被抓，变异有效）；
    后端 `/worksheet/node-amounts` `test_ctree_endpoints.py` 18 passed。
    浏览器实测（真实后端 + 真库，审计年度 2098 小集团 G⊃{GB 分公司, S 子公司, A⊃AB 分公司}）：
    模式标签「合并方式：母子合并＋总分汇总」；组织图与树形列表 13 节点、4 层、`node_key` 无重复；
    「进入项目」只出现在 7 个有项目的节点（合并 2 / 本部 2 / 分公司 2 / 子公司 1）；中栏无「添加」「同步」与自造差额节点；
    G 母分差额面板 新增（1122 借 50 / 2202 贷 50）→ 草稿 → 提交审批 → 待审批 → 审批 → 已审批，节点金额抵销 50/50；
    真库核对 `consol_worksheet` G:branch_elim 抵销借 50 / 贷 50、G:parent 1122 = 1350、`consol_trial` 1122 抵销 50；
    A 合并差额（承载 = 甲合并项目）只读提示 +「前往该合并项目录入」、无新增按钮；控制台 0 error。
    实测中发现并修复 4 处：组织图居中溢出使最左节点滚动不到（`.org-chart` 改按内容撑宽）；兄弟横向连接线从未画出
    （`--child-count` 从未赋值，改为逐子节点拼接）；子公司/分公司卡片角色与关系标签重复（`relationTagLabel` 去重，+1 用例）；
    差额面板关闭动画期间点另一差额节点打不开（Element Plus 离场结束才回写 false ⇒ 监听 `close` 立即回写，+1 用例，
    去掉修复后该用例红）；分录列表列宽超出抽屉使固定操作列盖住状态列（收窄列宽，实测无横向滚动）
  - _需求：4.4, 4.6, 9.1~9.5_

- [ ] 11. 集团架构森林与项目树视图
  - [ ] 11.1 `useGroupTree.ts` 类型扩展；`ConsolidationHub.vue` / `Projects.vue` 关系与口径标签、拖拽按实体
  - [ ] 11.2 `BatchImportDialog.vue` 预览显示关系
  - _需求：8.4~8.6_

- [ ] 12. 配置合并范围弹窗改为识别结果展示
  - [ ] 12.1 `ConsolScopeConfigDialog.vue` 展示已识别下级与关系；未识别时给填写指引
  - _需求：11.1, 11.2_

- [x] 13. 母公司个别数
  - [x] 13.1 `parent_company_scope` 增加「母公司是否有分公司」判定（仍经唯一 helper 定位单体项目）
  - [x] 13.2 附注母公司章：有分公司时 `_parent_tb_cache` 取本部+分公司之和并叠加母分差额（仅审定数）
  - [x] 13.3 报表母公司列：有分公司时按报表配置对汇总节点求值，上年数留空并注明原因
  - [x] 13.4 特征测试 P13（无分公司逐字节一致）+ 有分公司示例
  - _需求：10.1~10.4_
  - 证据（2026-10-01）：`parent_company_scope.resolve_parent_company_context` 先委托唯一
    `resolve_parent_standalone_project`，再精确检查 `{根企业代码}:parent` 节点是否为 aggregate；禁用整棵树 mode 推断（已测
    「仅子公司有分公司，根 mode=mixed，但根母公司无分公司」反例）。新增共享 `parent_company_values.py`：审定数复用
    `load_calc_basis + node_measures[parent][consolidated]`（本部+分公司+仅 approved 母分差额），未审/期初只汇总 parent
    子树数据叶子，不含母分差额且不夹带子公司。`DisclosureEngine` 仅 branch 路径切到共享汇总 cache，仍保留 standalone
    project_id 给其他 resolver，并在表级溯源增量落 `parent_aggregate / source_node_key / includes_branches`；前端横幅显示
    「母公司汇总（本部＋分公司）」及未审/期初不含母分差额。`ReportExcelExporter` 仅 branch 路径先聚合科目再对
    `{tpl}_consolidated` 报表公式求值（非线性公式不做子列相加）；母公司汇总上年数带强制留空标记，即使
    `fill_empty_as=zero` 也不复活为 0，两条填充路径均写 Excel 批注「母公司汇总上年数未结转」。无分公司继续原
    `_load_report_data(standalone)` / `_parent_tb_cache`，P13 对两条输出做 canonical UTF-8 bytes 全等。
    新真 ORM 测试 **5 passed**（100+20+approved 5=125；未审 90+18=108；期初 80+15=95；draft 99 与子公司 1000
    均不计），前端溯源 **24 passed**；母公司/树/报表/附注联合回归 **272 passed、1 pre-existing failed**（仅
    `test_parent_only_code_path_allowlist`：并发改动 `routers/wp_render_pipeline.py` 多出未登记 `parent_only`，与本任务文件无关）；
    后端变异 **12/12 killed**、前端变异 **2/2 killed**；改动文件 diagnostics 0。

- [ ] 14. 验证与收尾
  - [ ] 14.1 全量回归：合并、建项、批量、母公司口径、集团树相关测试文件
  - [ ] 14.2 Playwright：建子公司/分公司/合并项目 → 合并页三节点 → 差额录入审批 → 数值核对，截图后清理数据
  - [ ] 14.3 清理一次性探针与临时文件；更新 INDEX.md 与 memory
  - _需求：12.1~12.4_
