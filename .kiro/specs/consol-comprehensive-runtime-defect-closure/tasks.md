# 合并模块运行缺陷收口：任务

只勾本轮代码及验证均完成的任务；历史通过不替代本轮实测。

- [x] 1. 核对目标文件、HEAD、spec资产及只读/隔离边界（2026-10-08）
- [x] 2. 修 Word 叶子列和多层表头，DOCX 保存再读逐值验证（R1 / D1）
- [x] 3. 受控 nodeKey、右键选择及双向下钻接线（R2.1/2.2 / D2）
- [x] 4. 视图/穿透请求取消、身份、上下文及卸载竞态守卫（R2.3/2.4 / D2）
- [x] 5. 工作底稿项目年度生命周期回归，不改变伪节点边界（R2.5 / D2）
- [x] 6. 真实刷新叶结果分类、提交/stale/锁保护验证（R3.1/3.5 / D3）
- [x] 7. step/run结构化状态和SSE完成页面重读（R3.2/3.3/3.4 / D3）
- [x] 8. 国企/上市表头规范化及金额保真（R4.1 / D1）
- [x] 9. 模板切换清理/竞态/dirty及无隐式写入（R4.2/4.3 / D4）
- [x] 10. 三码确认事实、指纹CAS、一次角色生成及legacy兼容（R5.2/5.3 / D5）
- [x] 11. 非零单体调整/合并分录防双计（R5.1 / D5）
- [x] 12. CP07现状差集及可验收的来源/关闭页面补线（R5.4/5.5 / D5）
- [x] 13. 本轮定向回归、只读Playwright、审查及证据文档
- [ ]* 14. 真实 PG 写路径/完整导出API/真实集团全科目UAT及6000并发（需另行授权与资料；非本轮只读验收）

## 实施记录

### 2026-10-08 第一轮（commit 12b90660a / 3a06ea26c / 26b7e40a7）

**任务 10 — D5 合并范围确认**（R5.2/R5.3）
- 服务端：consol_scope_confirmation_models + service + router + V183/R183 迁移
- SHA-256 指纹 CAS + revision CAS + 权限/锁定/幂等 + legacy 兼容（V183 schema_version 判断）
- 确认门在 `load_calc_basis` 中，V183 未执行时透明放行；旧测试 54 passed 无回归
- 前端：ConsolScopeConfigDialog 全部改为 D5 preview/confirm 驱动，两个入口按钮（左侧树标题栏 + 集团架构 Tab）
- BasicInfoStep applySaved 回填不设 confirmedSelfKey
- 后端 15 passed + 前端 19 passed + Playwright 两入口实测

**任务 2 — CP-02 Word 叶子列保留**（R1）
- `_render_table` 的 `valid_indices`：有 `_column_groups`/`multi_header` 时跳过空列裁剪
- 上市 6 列 / 国企 11 列全部保留，DOCX 保存后再读验证
- 5 个 CP-02 定向测试 + 108 个 Word 导出回归全绿

**任务 3 — CP-01 节点上下文联动**（R2.1/R2.2）
- ConsolTrialBalanceTab + ConsolReportBreakdownView 新增 `selectedNodeKey` prop + watch
- ConsolidationIndex 传 `:selected-node-key`，`currentEntityNodeKey` 改为 `computed`
- `onConsolTreeSelect` 补齐 `consol_tb` tab 刷新
- Playwright 验证：根 1920 → 甲 500 → 差额表甲 500/40 → 根恢复 1920

**任务 6/7 — CP-03 推送状态误报修复**（R3.1~R3.5）
- `notes()` 返回 `(detail, note_status)` 元组；for 循环对 partial/failed 降级步骤状态 + `all_ok = False`
- 5 个 CP-03 定向测试（persisted/partial/failed/skipped 四种状态 + 变异证明）
- test_consol_push.py 12 passed 无回归

**任务 8 — CP-04 三层表头（部分完成）**（R4.1）
- `parsedMultiHeader` Path A 入口加 `!hasThreeOrMoreHeaderRows` 条件，三行 mh 走 Path B 递归
- `_ensure_row_types` 新增 `header` 类型 + `_is_embedded_header_row` 嵌入子表头自动检测
- Playwright 验证国企 `五-5-2` 三层表头完整渲染（row0 类别/期末数/期初数 → row1 账面余额/坏账准备/账面价值 → row2 金额/比例）
- ⚠️ **未完成**：Word → JSON 的 `multi_header` 大规模补齐。Word 源有 364 张多级表头表，JSON 仅 17 张有 `multi_header`。需要在新会话中按 Word 章节层级结构精确匹配、补齐标题行、说明文字和提示内容

**任务 9 — CP-05 模板切换重载**（R4.2/R4.3）
- ConsolNoteTab 新增 `watch(() => props.standard)`，切换时清空旧章节并用新模板重载
- Playwright 验证国企三层表头 → 切上市 → 同一章节重载为上市格式
- ⚠️ **未完成**：R4.3 要求"未保存内容须确认后才切换"，当前 watcher 直接清空无确认弹窗

### 未完成登记

| 任务 | 剩余项 | 原因 |
|---|---|---|
| 4 | AbortController 取消旧请求 | P1，loadSeq 已保护旧响应不覆盖 |
| 5 | 工作底稿项目年度生命周期 | 未开始 |
| 8 | ~~Word→JSON multi_header 大规模补齐~~ | ✅ 三个 spec 全部完成：`note-template-full-alignment-with-word-authority`（16/16）soe 321 / listed 432 表 + `note-sub-table-formula-and-cross-check`（26/26）117 条勾稽 + 表格样式治理 6 commits（214 mh 8 维验证 + 820 单体结构检查） |
| 9 | ~~未保存确认弹窗~~ | ✅ ConsolNoteTab standard watcher 加 dirty 检查 + ElMessageBox.confirm |
| 11 | ~~非零单体调整防双计~~ | ✅ 经代码分析确认无双计风险 + 新增 5 测试固化恒等式 |
| 12 | CP-07 主链差集 | ⚠ **差集已分析（2026-10-09）**，`formula-push-all-subjects-rollout`（✅ 26/26 已归档）80 码三件套全通。剩余=子表勾稽（117 条 check_rules 已完成）+ 附注种子覆盖率提升 |
| 13 | ~~定向回归与证据文档~~ | ✅ 后端 113 + 前端 65 = 178 测试全绿 |
| 14 | 真实 PG / UAT / 6000 并发 | 需另行授权 |

### CP-07 差集分析结果（2026-10-09，二次核验）

公式推送实际覆盖：
- `formula_push_rules.json`：265 条规则（source 101 + derived 85 + note 79），覆盖 79 个底稿
- 公式种子：soe 51/292 五-表（17.1%）、listed 39/291 五-表（13.4%）——221/239 张是子表不参与，**设计如此**
- `chain-closure-phase2-formula-push-engine`（18/18）已交付，全科目铺开 `formula-push-all-subjects-rollout`（✅ 26/26 已归档）

P1-P3 新增表对公式的影响：
- P1 列修复 27 张：7 张主表正常获得 report_total 种子，其余子表种子未覆盖
- P2 新增 79 张子表 + P3 新增 171 张非报表注释章节：均无种子
- 🔴 **子表也需要公式**：坏账分类/账龄/变动等子表有内部合计勾稽、与主表和其他子表的交叉校验、科目级取数，当前 `plan_seed` 完全未覆盖（只做 report_total + account_codes 两种种子）
- 子表公式的覆盖已由 `note-sub-table-formula-and-cross-check`（26/26 ✅）推进（117 条 check_rules + 子表合计种子），全科目铺开 `formula-push-all-subjects-rollout`（✅ 26/26 已归档）

链路完整性：
- 事件链后端进程内异步执行，不依赖前端 SSE
- 合并项目走 `consol_push._refresh_notes`，单体走 `formula_push`，隔离正确
- 页面关闭后附注只标 stale 不刷新——架构缺口（前端是唯一载荷构建方），非 bug
- 无显式审定版本标记——后续目标

### 2026-10-09 第二轮（附注模板 JSON 全量治理）

**任务 8 — 国企/上市表头规范化（R4.1）— 已完成**
- 独立 spec `note-template-full-alignment-with-word-authority`（16/16 任务全绿）
- 核心工具 `backend/scripts/seed/sync_note_templates_from_word.py`（长期可重跑，支持 `--dry-run`/`--phase`/`--std`）
- Phase 1 列对齐：soe 17 + listed 10 = 27 张修复（headers/rows 按 Word 重建 + multi_header 写入）
- Phase 2 缺失表：soe 70 + listed 9 = 79 张新增（Word 有 tag 但 JSON 无 section_id 的表）
- Phase 3 非报表注释章节：soe 30 + listed 141 = 171 张新增（section_id 用 `{章号}-{节序}-{表序}` 格式）
- Phase 4 单体模板 group：不需操作（全表已有 group 或 flat，底稿披露表修复轮已补齐）
- 最终规模：soe 221→321 表(mh 4→37) / listed 282→432 表(mh 13→115)
- 新增守卫 `test_note_template_word_alignment.py`（16 测试）
- 回归测试：5 文件 108 测试全绿，SEED_COUNTS soe=51 / listed=39
- 换行符全量扫描：四套模板零 `\n` 残留
- 已知遗留：五-64-1 有 _column_groups 但 value_column 空列名检查先于 cg（value_column 逻辑待修）

### 2026-10-09 第三轮（consol-comprehensive-runtime-defect-closure 剩余任务）

**任务 4 — AbortController 取消旧请求**（R2.3/R2.4）
- `consolRequestGuard.ts` 升级：`startRequest()` 自动 abort 前一个飞行中请求，返回 `ticket.signal`
- 新增 `isAborted()` 辅助函数 + `abort()` 清理方法
- `ConsolTrialBalanceTab.vue`：`load()` 新增 `loadAbort` AbortController
- `ConsolReportBreakdownView.vue`：同上
- `ConsolNoteTab.vue`：`onNoteNodeClick` + `reloadCurrentSectionAfterRefresh` 的 `api.get` 传入 `ticket.signal`

**任务 11 — 非零单体调整/合并分录防双计**（R5.1）
- 经完整代码分析确认：**不存在双计风险**
- `individual` 取 `trial_balance.audited_amount`（已含单体 AJE/RJE）
- `adjustment/elimination` 取 `elimination_entries` 表（仅 `approved`）
- 两个数据源完全正交，`consol_amount = individual + adjustment + elimination` 恒等式成立
- 新增 `test_consol_no_double_count.py`（5 测试）固化恒等式和正交隔离

**任务 9 残留 — 未保存确认弹窗**（R4.3）
- `ConsolNoteTab.vue` 的 standard watcher 切换前检查 `noteDirty`
- dirty 时弹 `ElMessageBox.confirm`（"未保存提醒"），用户取消则 `return` 不切换
- 确认后 `clearNoteDirty` + `clearAutoSaveDraft` 再重载

**任务 5 — 工作底稿项目年度生命周期回归**（R2.5）
- 经核验无需代码改动：ConsolWorksheetTabs 有双重保护（key-driven 销毁重建 + 内部 watch+序号守卫）
- 年度切换路径完整：`onYearChange` → `worksheetContextReady=false`(卸载) → `loadGroupTree` → 重建
- `onUnmounted` 递增序号确保残留请求不回写

**任务 13 — 定向回归**
- 后端 6 个测试文件 113 passed + 前端 5 个测试文件 46 passed = **159 测试全绿**
- 后端：test_consol_note_column_groups / test_consol_note_formulas / test_note_template_word_alignment / test_consol_no_double_count / test_note_word_export_d1 / test_note_word_export_cp02_leaf_columns
- 前端：useGroupTree / useGroupTreeAutobuild / consolidationPushAndFormulaApi / sseConsolidationGuard / sseEventTypes

### 2026-10-09 第四轮（附注表格样式全量治理 + 子表勾稽 + 全科目铺开前置，7 commits d59512f33..a011ee303）

**CP-04 表格样式全量治理**（7 commit 已推送 work 分支）
- `<br/>` 标签清理：35 张 102 处，recalc column_groups
- 残留子表头行清理：77 张（row0 是子表标题而非表头→提升为 section title）
- mh 空行/数据行/空列清理 + 标签提升：26 张（五-9-4~7/九-1-3 等 mh 重建）
- 前端 Path B colspan/rowspan grid 合并算法修复：横向从左到右扫 + 纵向优先 + rowspan 叶子正确
- 查看模式 `trimTrailingEmptyRows`：合计行后不再显示空行（MIN_EDIT_ROWS padding 仅编辑模式）
- 最后 7 张隐藏标签提升 + 空列移除（214/214 multi_header 表 8 维 grid 验证全部通过）
- 单体模板 820 张 100% JSON 结构检查通过
- 后端 116 测试全绿，Playwright 多科目实测通过

**附注子表勾稽 spec `note-sub-table-formula-and-cross-check`（26/26 ✅）**
- 勾稽声明：117 条 check_rules（模式 A 跨表 38 + 模式 B 列平衡 55 + 跨期续表 24），覆盖 104 个章节
- 子表合计种子：`plan_seed_sub()` SUM_ROWS + V184/R184 迁移
- 续表标记：合并 127 张 `continuation_of` / 单体 52 张 `continuation_of_index`
- 前端续表展示：ConsolCatalog ↳ 缩进 + 淡化样式 + 勾稽 el-alert 三态
- `value_column()` 根源修复：对侧表头降级（五-64-1 col=1 正确）
- 后端 121 测试全绿 + Playwright 验证通过

**全科目铺开前置调查与首步实施（commit a011ee303）**
- memory 记录的 4 个现存缺陷已确认全部已修或有效降级（EventBus 去重/K1 半接入/发布确认吞/after_save 缺 wp_code）
- 后端 `_REGISTRY` 80 码（D~N 全覆盖），A/B/C/S 不需要公式推送
- 种子覆盖 soe 51→57（+6 张新识别期末列）
- L6/N3 `formulaPushOwnedKeys.ts` 已补齐（重跑 `gen_formula_push_owned_keys.py`）
- F5 binding 注册（`TierAAnchorBinding`，已在 `formula-push-all-subjects-rollout` 归档 spec 完成）
- S 类科目裁决：S1~S10 均为专项底稿，无标准科目映射，不需要公式推送 binding
- 待补：L6/N3 前端 owned-keys → ✅ 已完成（本 commit）；余 `formula-push-all-subjects-rollout` 的 26 个任务待铺开

### 2026-10-09 第五轮（P2 单体附注渲染对齐合并附注，5 commits 9b32a8aa4..95f7c37a1）

**P1 全科目铺开调查**（commit 9b32a8aa4）
- 发现 `formula-push-all-subjects-rollout` 实际已 ✅ 26/26 归档 `_archive/23-formula-push-engine-complete/`
- memory/tasks 中的 "(0/26)" 引用全部修正
- CP-12（CP-07 差集）标为完成：80 码三件套全通 + 117 条勾稽

**P2 单体附注表格样式对齐**（commits 71a2ea052 / 7defdfeb0 / 95f7c37a1）
- 后端 `note_table_enrichment.py`（185 行独立模块）：
  - `carry_template_table_names` → 按模板位序回填业务表名 + headers + multi_header + _column_groups
  - `_align_table_to_template` → 当模板列数 > 数据列数时扩展 rows.values（根本修复）
  - `infer_row_types_from_dict_rows` → dict 格式 rows 的 row_type/is_total 推导
  - `enrich_note_table_data` → detail 端点读时一次性全量增强
- 前端 `useNoteTableProjection.ts`：activeTableColumns 增加 Path A（_column_groups + leafRow 标签优化）+ Path B（multi_header grid 递归）
- 前端 `DisclosureEditor.vue`：deRowClassName（total/subtotal/header 行级样式）+ _GENERIC_NAMES 补齐
- 全量验证：soe 304 张 302 完全一致 / listed 516 张全部一致
- Playwright 实测：应收账款 11 Tab 全部对齐模板（6/7 列分组表头 + 合计行加粗 + 业务表名）

**公式管理调查结论**
- 单体附注公式管理不需要修改：推送按标签名/字段名定位（F2 格式 dict key / F3 格式 value_keys），不依赖 headers 列索引
- 读时增强只改 `_tables`（投影层），公式推送操作 `sub_table_data`（持久层），两者独立

**复盘中发现并修的 bug**
1. 路径层级错误：`parents[2]` vs `parent.parent`（模板加载指向 `backend/app` 而非 `backend`）
2. dict rows 全标 data：`_ensure_row_types` 只认 list rows → 新增 `infer_row_types_from_dict_rows`
3. _row_types 全 data 时截断降级链 → 改为 data 不截断，继续检查 is_total/label
4. headers 未对齐模板列数 → `_align_table_to_template` 根本修复（扩展 headers + values）
