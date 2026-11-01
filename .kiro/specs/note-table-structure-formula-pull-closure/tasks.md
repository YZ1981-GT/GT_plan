# 附注表格结构、预设公式与合并拉数收口 — 任务

## A. 合计构成与列语义（R1）

- [x] 1. 后端 `note_total_terms`：冒号标题行、嵌套小计、纵向变动表；前端 `noteTotalTerms.ts` 同步；`text_pattern` 加 `账龄$`；golden 与标题行库重生成
- [x] 2. 用例：三类形态正反例 + 前后端 golden 对拍 + 变异

## B. 比例与损失率（R2）

- [x] 3. `note_formula_ratios.ratio_plans` + 单体预设 `ratio` 类型 + 执行器 `requires`
- [x] 4. 合并 `build_note_rows` 只加金额列并派生比例 / 损失率；apply 与子树汇总传表结构
- [x] 5. 用例（D2 两版逐表、投影表只补空、合并派生）+ 变异

## C. 读时增强（R3）

- [x] 6. 期间层只挂无期间层的表；泄漏名不放行、位置兜底须列数相同；用例 + 变异

## D. 推送后自动运算与溯源（R4）

- [x] 7. `note_followup` + 四个调用方接线；执行器跳过推送拥有格；来源诊断带取数口径；用例 + 变异

## E. 公式管理（R5）

- [x] 8. 附注节点可执行公式在前、文字预设标「审核要点」；`list_section` 回未生成原因并显示；用例

## F. 合并拉数（R6）

- [x] 9. 行名键去【】/ 可选行方括号 / 括号全角、别名（期初余额 ≡ 上年年末余额 等 7 组）、账龄区间建议 `aging_bucket`（可自动确认）、明细模板不另建区间行、来源独有行按来源位置放（新 `consol_note_detail_order`）
- [x] 10. 读取层：单体「小计 / 减：坏账准备 / 合计」折进合并合计行（新 `consol_note_provision_fold`）、金额列一列都没对上报因、来源合计 / 小计不模糊配（`total_row` / `total_ignored`）
- [x] 11. 跨口径子表名（生成器 `_cross_std_table` + 映射 JSON `standalone_table_name_by_std` + 运行时按来源口径取）
- [x] 12. 映射弹窗：非自动确认建议确认前弹窗过目、忽略带后端原因、来源问题显示原因；用例 + 变异

## G. 离屏自动带入（R7）

- [x] 13. D2 `buildSnapshot` 逐项表派生（新 `d2DisclosureDerive`，「带入」与离屏同一份映射）；Tab 与离屏载荷一致的用例

## H. 存量与验收（R8）

- [x] 14. 只读清点脚本 `report_note_orphan_push_cells.py` + 真库预演（规则已删、格里仍留推送值 18 行，其中 4 行非零）
- [x] 15. 回归：候选 worktree（HEAD + 本轮 76 个文件）与干净 HEAD worktree 逐节点比对；标题行库 / golden / Word 树三项 `--check` 通过
- [x] 16. 顺带修 HEAD 预存编译失败（18 文件 22 处「await 写在非 async 函数里」+ 5 个 `.ts` 模板字面量被批量替换弄坏）并补门禁 `vueSfcSyntax.spec.ts`（原先 `allowAwaitOutsideFunction` 放过同步函数里的 await，且不扫 `.ts`）
- [ ]* 17. 浏览器实测（【测试】项目：D2 表头、公式管理、刷新后公式）—— 待前端编译修复推送后在共享环境走查
- [ ]* 18. 写真库修复（孤儿推送格、D2 旧结构表、和平药房全部刷新）—— 须用户放行

## 第二轮：未做项与改进建议（R9~R14）

- [x] 19. R9 正式修复脚本 `backend/scripts/fix/purge_orphan_push_states.py`（dry-run 默认、`--apply --confirm`、备份 JSON、重跑附注公式）+ 用例
- [x] 20. R10 推送 run 回报孤儿状态（新模块 `formula_push/orphan_states.py`，panel / 路由回执带上）+ 推送页提示 + 用例
- [x] 21. R12 账龄表「减：…准备」时按账面余额合计兜底（新 `formula_push/note_total_pick.py`，engine 接线前先抽模块把行数降到门禁内）+ 用例
- [x] 22. R13 附注权威源对拍守卫（D2 样板：后端 builder vs 前端载荷逐值相等；其余 wp_code 清单只许变短）
- [x] 23. R11 预览回执带可自动确认比例 + 映射弹窗 / 合并附注页显示 + 章节级一键 + 用例
- [x] 24. R14 跨口径转置表对应（读取层 + 判据）+ 用例
- [x] 25. 回归（候选 worktree vs 远端最新逐节点）+ 三项门禁 `--check` + 浏览器实测 + 单提交推送

## 第三轮：共享环境解阻 + 存量列头漂移（R16~R17）

- [x] 26. R16 解除共享环境两处阻断（`pm_dashboard.py` / `useAiNoteCapture.ts` 对齐远端权威版，不动 git HEAD、不碰别人提交）+ 实测「单文件是否够」+ `/api/health` 的 reload 由 failed 变 ok 验证
- [x] 27. R16 后端真实端点实测：`/latest` 回执带 `orphan_push_states`、`/run?dry_run` 由 500 恢复 200（第二轮 NameError 修复的运行时证据）
- [x] 28. R17 存量列头漂移只读报告 `backend/scripts/analyze/report_pushed_note_header_drift.py`（117 张表 → 18 张不一致，按空白/文字/列数分类）
- [x] 29. R17 判定「存量而非代码缺陷」：前端 12 循环 107 张表逐位现算 0 不一致（临时诊断用完即删）
- [x] 30. R17 修复脚本 `backend/scripts/fix/fix_pushed_note_header_labels.py`（dry-run 默认 / `--apply --confirm` / 备份）+ 安全门 `reordered_columns()`（dry-run 逐条审查抓到的列序错位风险）+ 判据双向测试 17 例
- [ ]* 31. 执行存量修复 `--apply --confirm`（10 张表 12 个 label）—— **须用户放行**（含两个真实项目：陕西华氏医药、重庆和平药房）
- [ ]* 32. 8 张需重新推送的表（7 张列数不同 + 1 张列序错位）—— 须在界面上对相应底稿重新推送；另 2 张「模板无此表名」待查是否孤儿表
- [x] 33. R18 界面走查（任务 17 的实质）：附注编辑器 199 章节渲染正常、D2 底稿页 14 个页签可打开、公式管理入口可点开；抓到并定位 1 条 500
- [x] 34. R18 跨会话迁移撞号取证（V227 / V228 两组记账与磁盘文件不符 ⇒ `attachment_lineage.project_id` 与 `formula_sync_item.revision` 永不执行，两个接口恒 500）+ 修复 SQL 与回滚方案（design §8）
- [ ]* 35. 执行迁移撞号修复（改共享库 schema_version 记账 + 跑 V227/V228）—— **须用户放行**；同批待执行的 V229/V233/V234 需逐条确认（V234 含 UPDATE 改数据）
