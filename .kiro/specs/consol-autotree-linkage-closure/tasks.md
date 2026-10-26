# 任务：合并模块自动建树、左树联动与四维表收口

> 批次：B1 后端核心 → B2 后端扩展 → B3 前端联动 → B4 前端内容 → B5 验收。每个任务完成须有代码 + 测试通过证据。

## B1 后端核心

- [x] 1. 命名常量拆出与新命名（R2）
  - 新建 `consol_node_naming.py`，`consol_group_tree` 再导出；`display_name` 按 design §3.2；诊断文案同步
  - 更新硬编码旧名称的后端测试；`consol_group_tree.py` ≤ 800 行
- [x] 2. 树版本迁移 V206 / R206 与模型（R1.2）
  - `confirmed_by` 可空、`confirmation_mode`；迁移一致性测试覆盖 V183 ∪ V206；本地库 `MigrationRunner.run_pending()` 落库
- [x] 3. 计算门改年度校验 + 自动记录版本 + 结构差异（R1.1~R1.3）
  - `require_calc_year` / `record_scope_version` / `structural_diff` / `scope_version_info`；去 legacy；`load_calc_basis` 去 `allow_legacy_read`
  - 推送 worksheet 步骤记录版本并写明细；`build_tree_view` 附 `scope_version`
  - 改写 `test_consol_scope_confirmation.py`（未确认可算、推送记版本、同指纹不重复、改名不算结构变化、锁定不记、年度不符仍拒、手动记录 CAS）
- [x] 4. 合并上期（R8.1）
  - `prior_node_values` + 路由带 `prior_blank_reason`；测试：有上年合并项目取同节点、无上年留空带原因、上年树缺节点
- [x] 5. 右键合并明细读时计算（R8.2）
  - 行次走 `child_contributions`、科目码沿用旧路径；测试合并数 = 后端合计、差额子节点计入抵销
- [x] 6. 一致性校验修复与删除手改接口（R8.3 / R8.4）
  - `await` + 按科目方向；删 PUT；测试（含路由不存在）

## B2 后端扩展

- [x] 7. 拖拽改上级下沉服务 + 鉴权（R3）
  - `group_links.reparent_project`；路由 `require_project_access("edit")`；测试两口径同步名称 / 关系 / 向导数据、非成员 403、成环 400
- [x] 8. 试算页读时视图扩展（R5.1 / R8.5 / R10.1 / R10.3 后端）
  - `include_drafts` / `consolidated_with_drafts` / `node_kind` / `balance`；穿透行补类型、说明、所属上级；测试
- [x] 9. 分录汇总表同源重写（R9 后端）
  - design §3.7；测试：金额 = `elim_totals`、对账一致、持久化过期检测、孤儿单列、含草稿净额、`other` 标签、方向提示

## B3 前端联动

- [x] 10. 命名与角色标签（R2.4）
  - `consolTreeView` 角色标签按 kind；向导提示、差额面板说明、范围弹窗角色列；测试
- [x] 11. 单棵树与高亮同步（R7.1）
  - 删页内侧栏；中栏加搜索、`consol-current-node` 高亮；组织图 / 试算 / 差额表回写当前节点；测试
- [x] 12. 树版本标签、结构变化提示与「树版本」弹窗（R1.4~R1.6）
  - 中栏标签与提示、重新推送；弹窗改造（向导预览模式、可选手动记录）；向导去死代码 `attached`；测试
- [x] 13. 差额户呈现与上下文条（R7.2 / R7.3）
  - 差额户不自动弹抽屉、「📝 差额分录」按钮与右键；内容区上下文条；合并报表列名随口径；测试
- [x] 14. 就绪门、四栏自动切换与循环修复（R7.4 / R7.5）
  - 树与年度就绪后加载当前页；进附注页切四栏；`four-col-switch` 只转发一次；附注空态去写死计数；测试
- [x] 15. 差额表非汇总节点与节点下拉（R7.6 / R10.2）
  - `nearestAggregateAncestor` + 高亮列；试算页全部节点下拉 + `node-change`；测试

## B4 前端内容

- [x] 16. 数据节点显示单体报表与附注（R6）
  - `ConsolEntityStandalonePanel` + `NoteTablesReadonly`；无项目 / 403 / 未生成说明；进入项目；测试
- [x] 17. 基本信息表按企业树带出（R4）
  - `consolSubsidiaryInfo.ts`；`SubsidiaryInfoSheet` 锁定模式与按代码导入；企业列只认企业树；测试
- [x] 18. 草稿预览列、口径说明、平衡提示与穿透补全（R5.1 / R8.5 / R10.1 / R10.3）
  - 试算页；测试
- [x] 19. 分录汇总表组件与导航（R9 前端）
  - `EntrySummarySheet.vue`；进「合并抵消」分组；进入 / 分录变化 / 推送后重读；测试
- [x] 20. 右键合并明细弹窗与拖拽提示（R8.2 / R3.3 前端）
  - `ConsolBreakdownDialog` 新契约；`ConsolidationHub` 同步提示；测试

## B5 验收

- [x] 21. 回归与静态检查
  - 后端合并相关 pytest 与改前失败集合逐条对比；前端相关 vitest；单区域 vue-tsc + 变异证明；行数门；鉴权基线守卫
- [x] 22. 变异证明
  - 每条新判据磁盘注入反例须打红，逐字节恢复
- [x] 23. 浏览器实测（design §5）
  - 记录各节点右侧内容、请求参数与截图结论；探针与截图用完即删
- [x] 24. 收尾
  - INDEX.md 登记、memory 精简记录、提交只含本 spec 改动块

## 验收记录（2026-10-26，聚合摘要）

- 回归（提交树 = HEAD + 本 spec 改动，临时 worktree 干净检出；全量回归在 HEAD `97b3534c2` 上跑，HEAD 前移到 `e36cf246d`（程序链批 3，未触及合并代码）后重跑本 spec 相关后端 13 个文件 167 passed、前端 86 个文件结果不变）：后端合并相关 91 个测试文件 1526 passed / 5 failed（`test_consol_note_formulas` 种子计数 ×2、`test_note_standalone_consolidated_only_scope` ×2 在 HEAD 单跑同红；`test_p0_6_9_contract_and_lock` 发布人校验在整组里红、单跑绿，HEAD 整组同红）；前端合并 / 向导 / 布局 / 视图相关 86 个 spec 文件 1118 passed / 1 failed（`views/__tests__/composables.spec.ts` loadNoteMappingPreset，HEAD 同红）；单区域 vue-tsc 相对 HEAD 只多 1 条，在 HEAD 的 `useNoteTableProjection.ts`（本 spec 的只读表格引用它后才进入检查范围）；行数门通过；鉴权台账只删本 spec 撤掉的 `PUT /api/consolidation/trial/{trial_id}`（汇总只减这一条的贡献，台账其余存量漂移不动），两份鉴权清单按提交树重生成（含 HEAD 上他人遗漏的漂移；edit 级清单读附注写端点清册，须在清册之后生成），`test_authz_inventories_check_mode` 由 HEAD 的 4 红变 4 绿；后端失败集合 5 条 ⊂ HEAD 整组 6 条（HEAD 多出的 `test_consol_push` 审批 → 推送 → 撤销往返由本 spec 修复）。
- 变异：磁盘注入、逐字节恢复，64 条全部打红 —— 首批 52 条里 B19（推送不再记录树版本）存活 ⇒ 在 `test_consol_push.py` 补「worksheet 步骤写明树版本」断言后打红；F16~F18 / F26 首批因提交树基线红跳过，去掉未入库依赖后重跑打红；第二批另 12 条覆盖附注列树与多根组件包裹。附注列树对拍组在临时放入编辑器列树时打红（文件随即删除）。
- 浏览器实测（2098 测试集团可写；【测试】公式同步集团只读）：合并报表直达加载在树就绪之后、节点新命名、树版本标签、上下文条、上期整列留空横幅；数据节点右侧只显示单体项目面板（报表未生成给说明；附注目录 199 节、三层表头正确），切回合并户合并附注恢复；差额户不自动弹抽屉、列名「调整抵销本期 / 上期」、「📝 差额分录」打开分录面板；试算页节点下拉含全部 5 个节点、「含草稿预览」列与口径说明；基本信息表三码只读、删除禁用；分录汇总表列出未归属分录及原因；报表页右键「查看合并明细」应收账款 1,920.00 = 1,350.00 + 70.00 + 500.00（差额户 0）。
- 偏离：①只读附注表格原引用 `views/composables/noteColumnTree.ts`（另一会话 spec note-pull-header-formula-closure 未入库的文件）⇒ 干净检出 import 失败；改为本地同读法实现 `composables/consolNoteColumns.ts` + 对拍组（编辑器列树存在时逐表对拍，四份附注模板全部表格），其入库后应改为直接复用 ②合并附注组件是多根组件，组件上的 `v-show` 不生效（浏览器实测两块同时显示）⇒ 改在包裹元素上，源码守卫钉住。
- 范围外（未改）：`reports.py` 的 GET `/{project_id}/{year}/{report_type}`、drilldown、export-excel 只校验登录；系统字典 review_status rejected 为「已退回」而合并 STATUS_LABELS 为「已驳回」；ConsolidationHub 范围差异仍比 consol_scope 表（已不驱动列）；【测试】公式同步集团的 2 笔 E2E-001 分录 `lines` 存成 `{"lines": [...]}`（全库仅此 2 行，测试数据），合并计算如实标为未计入。
