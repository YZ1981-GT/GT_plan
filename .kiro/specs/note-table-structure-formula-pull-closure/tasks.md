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
