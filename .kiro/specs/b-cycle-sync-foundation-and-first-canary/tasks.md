# B 循环双向回写地基与首张 canary — 任务

> 判据引用规则：本文件裁定 BC-1 ~ BC-60，两份 lane spec 只引用编号。
> `[ ]*` = 外部依赖阻塞，不可在本轮标 completed。

## 阶段 1：事实基线冻结

- [ ] 1. 建 B 域基线守卫骨架 `backend/tests/workpaper_sync/test_b_cycle_baseline.py`
  - 断言 B 域 in-scope entry 恰 **10** 条，`entry_id` 逐值匹配 requirements.md 范围表
  - 断言 10 条的 `capability_target_blocked_by` 逐条等于 `[BP-1,2,3,4,5,7,8]`
  - 断言 `migration_state` / `dual_mode_carrier.switch_verdict` / `resolution_kind` / `mount_count` / `component_type_family` 全域一致
  - 🔴 权威路径：`switch_verdict` 在 `dual_mode_carrier` 下，**不在** `ui_toolbar_gate` 下（后者无 switch 字段）
  - _判据：BC-1、BC-43_

- [ ] 2. 载体归属断言（BC-2、BC-58）
  - 断言 `useWpDualMode` 3 条 / 共享基类 5 条 / host_inline 2 条，合计 10
  - 断言 `useWpDualMode.ts` 的 `becomes_orphan_after_rewire` 为真（全 slice 唯一）
  - 断言共享基类 26 条生产边中 B 域占 5，改线后不成孤儿
  - _判据：BC-2、BC-58_

- [ ] 3. 解析三模式断言（BC-46、BC-51、BC-52）
  - 纯码 10 个（`B1-1` `B1-2` `B1-3` `B1-4` `B1-5` `B22A` `B22B` `B22C` `B23` `B50`）全部可解析
  - 中文名 5 个（`风险评估表-保持` `风险评估表-承接` `业务评价表B1-3` `B1-5 KAA检查表-业务承接` `尽职调查报告B1-4`）全部返回 `None`
  - `manifest` 的 6 个 pattern（`B1E` `B1K` `B1R` `B14D` `B23P` `B50R`）全部返回 `None`
  - 带前导空格的 `' B1-5 KAA检查表-业务承接'` 抛 `FileNotFoundError`（第三种失败模式）
  - 断言根因：`B1-1` 册的 sheet 名就是 `风险评估表-承接`（override 表把 sheet 名当 wp_code）
  - _判据：BC-46、BC-51、BC-52_

- [ ] 4. 目录册对账 + 一码多册登记（BC-29、BC-50）
  - 断言 `backend/wp_templates/B` = **137** 本 = docx **71** + xlsx **49** + xlsm **17**
  - 断言一码多册 **6** 组，其中 `B22A` **11** 本、`B5` 3 本、`B1-4`/`B2-3`/`B5-1`/`B5-2` 各 2 本
  - 断言册 ↔ entry 归属为 **0**（137 本全部带 `excluded_reason`，BP-8 全覆盖）
  - _判据：BC-29、BC-44、BC-50_

- [ ] 5. `wp_index` 一码多行登记（BC-55）
  - 断言 10 个真实 wp_code 在 `wp_index` 全部存在且全部 n ≥ 2
  - 断言分布：`B1-1`~`B1-5` 与 `B22A` 各 2 · `B22B`/`B22C` 各 3 · `B23`/`B50` 各 4，合计 **26** 行
  - _判据：BC-55_

- [ ] 6. 空分母清册 + 变异证明（BC-20，覆盖全部 ❌ 判定条）
  - 逐项断言 design.md §五 的 **14** 项结构性零
  - 每项配人造正样本变异测试（证明扫描器能扫出，区分「真零」与「扫描器坏」）
  - 逐条落断言：`definedName` 0（BC-9）· localStorage 无 mode 键（BC-16）· 无合计行形态（BC-17）· 册名无跨循环码混入（BC-21）· 无科目借贷方向（BC-22）· 无 `SHEET_MAP`（BC-23）· 册名无「原底稿/历史」（BC-24 / BC-27）· slice 无 `transport_key_resolution` 节（BC-30）· in-scope `parent_duplicate` 0（BC-31）· 超列引用 0（BC-32）· `workbook_format` 10/10 为 `null`（BC-38）· 公式行数超数据行数形态 0（BC-40）
  - _判据：BC-20、BC-9、BC-16、BC-17、BC-21、BC-22、BC-23、BC-24、BC-27、BC-30、BC-31、BC-32、BC-38、BC-40_

## 阶段 2：口径判据落地

- [ ] 7. 门控扫描器（BC-13）
  - 实现祖先链 × 递归 v-if/v-else 链头回溯口径
  - 断言 OO 挂点 **10** · segmented **11**（`b14` 有 2 个）· mode 门控 **10** · `mode_radio_sites` **0**
  - 断言仅自身口径只得 **7**，假阴 **3**（`gt-b1-risk-assessment` / `gt-b23-process-control` / `gt-b50-risk-assessment`）
  - 🔴 双向对账：独立 DOM 扫描结果须与 slice 权威字段 `ui_toolbar_gate.{segmented_sites, oo_mount_sites, mode_gated_oo_mount_sites}` 站点数逐值一致（本轮已验证三项全中）
  - _判据：BC-13、BC-11_

- [ ] 8. 持久化闭包扫描器（BC-42）
  - 实现 import 闭包深度 3 遍历（含 `@/` 别名与相对路径）
  - 断言 `/checklist-responses` 全 10 条命中：D0 **2** 条 + D1 **8** 条
  - 断言仅扫宿主只得 2 ⇒ 假阴 **8 / 10（80%）**
  - 断言 `field-overrides` / `custom-cells` / `publish-to-tb` 在深度 3 内全 0（GRP-05 的 field_overrides 通道不在前端闭包内）
  - _判据：BC-42、BC-3、BC-43_

- [ ] 9. 行身份扫描器（BC-53，🔴 禁照抄 N 轮）
  - 新建 `bCycleRowIdentity.spec.ts`，扫函数参数式行下标：`rowIndex` 形参 **2** / 1 文件 + `idx` 形参 **36** / 4 文件 = **38**
  - 扫 label 作渲染 key **4** 处（全在 `GtB50RiskAssessment.vue`）
  - 断言 N 轮形态（`${PREFIX}-${index}` / `row-${n}`）在 B 域命中 **0**，且该 0 不得被判为「无缺陷」
  - 双向变异测试：N 口径样本与 B 口径样本互不遮蔽
  - _判据：BC-53、BC-8、BC-6_

- [ ] 10. `count` 键一致性判据（BC-54、BC-56）
  - 断言前端 `count` 字段持久化 **13** 处 / 3 文件（b22c / b23 / b50）
  - 断言真库三种 count 键：`B22A-T1-count` / `B22B-row-count` / `B22C-env-def-count`
  - 断言两种编号基准并存：`B22B-row-0`（0-based）vs `B22C-env-def-1`（1-based）
  - 判据：`count` 值须等于实际行键数量，不一致即静默丢行
  - _判据：BC-54、BC-56_

- [ ] 11. mode 值体系登记（BC-41）
  - 断言三体系混用：中文 4 条（`'结构化视图'` / `'在线编辑'`）· `'onlyoffice'` **6** 次（b22 家族 4 条各 1 + b50 2）· `'structured'` 1 条（b23）
  - 断言第四值 `'polish'` 1 次（b14）
  - 断言只有 `b14` 在宿主内声明 `modeOptions`（3 处字符串数组），其余 9 条定义在共享载体内
  - _判据：BC-41_

- [ ] 12. strict 域口径（BC-5、BC-57）
  - 断言正则须为 `^GtB\d`：`^GtB` 会误命中 **3** 个（`GtBadDebtSheet` / `GtBArchitectureTree` / `GtBIndex`）
  - 断言漏命中 **4** 个不带 `Gt` 前缀的子对话框（`B22AControlItemDialog` / `B23ControlPointDialog` / `B50AccountRiskDialog` / `B60AttachmentMatrixPanel`）
  - 断言 strict 域 **24** 个，含本轮 10；未纳入 **14** 个（9 非 pilot + 5 pilot）须逐个登记排除原因
  - 断言小写 `Gtb` 分支为 **0**（空分母，配变异证明）
  - _判据：BC-5、BC-57、BC-20_

- [ ] 13. 真库分母与 remark/conclusion 反转（BC-34、BC-60）
  - 断言 B 域 `item_id ~ '^B[0-9]'` 分布：B1 1 / B2 3 / B22 57 / B23 2 / B60 4
  - 断言 remark 非空 **17** > conclusion 非空 **1**（与 N / A 两轮反转）
  - 断言 B60 pilot 同样 conclusion **0**（证明反转是全域性质非本轮偶然）
  - 断言 entry 级分母：B22C 23 / B22A 21 / B22B 13 / B23 2 / B1* 1 / **B50 0**
  - 断言跨 entry 污染 **0**
  - _判据：BC-34、BC-60、BC-19_

## 阶段 3：模板层判据

- [ ] 14. xlsm 宏层双重丢失登记（BC-49）
  - 断言 **17** 本 xlsm 全含 `xl/vbaProject.bin`
  - 断言 openpyxl 默认 `vba_archive` 为 `None`（丢宏），须 `keep_vba=True`
  - 断言 `Data Validation extension is not supported and will be removed` 警告影响 **16 / 66** 本（14 本 B23 家族 xlsm + `B22B 控制矩阵.xlsx` + 1）
  - 🔴 数据验证扩展**无技术解**，须记录为已知限制而非已解决
  - _判据：BC-49_

- [ ] 15. 幽灵行列上界判据（BC-35）
  - 断言 `B1-1` 的 `风险评估表-承接` 是 438 行 × 5 列而 last_value 仅 **103 × 3** ⇒ 幽灵 **335 行 / 2 列**
  - 判据：遍历上界必须取 `last_value_row`，不得用 `max_row`
  - _判据：BC-35_

- [ ] 16. footer 与 docx 几何判据（BC-36、BC-39、BC-26）
  - footer 读 raw XML（禁用 openpyxl）：4 册 14 sheets 三态 = 有内容 8 + 无容器 4 + 有容器无 `oddFooter` 2
  - 断言内容全为 `&C&P/&N`（B 域统一，与 A 域中英双语并存不同）；xlsm 也有 footer
  - docx merged 比例 **65% ~ 85%** ⇒ `id(cell._tc)` 去重判据适用
  - 占位符 `XX` + `【`，`××` 全角为 **0**（空分母）
  - `B1-3` 首段为 `索引号：B1-3`（第三种首段形态）
  - _判据：BC-36、BC-39、BC-26_

- [ ] 17. 册名脏形态穷举（BC-10、BC-26）
  - 断言波浪号范围码 **1**（`B13-2~5未审报表初步分析.xlsx`，一册覆盖 4 个码）
  - 断言全角括号 **45** / 半角 **0** / 连续两空格 **0**（后两项空分母配变异）
  - 断言 sheet 名前导空格禁归一化（`' B1-5 KAA检查表-业务承接'`）
  - _判据：BC-10、BC-26、BC-20_

## 阶段 4：首张 canary

- [ ] 18. canary 事实锁定（`xlsx/gt-b22-a-control-matrix`）
  - 断言真库 `B22A` = 21 行 / remark 非空 **9** / conclusion 非空 0 / 1 个 wp 实例
  - 断言载荷溯源：`B22A-T3-item-{1..6}-point` 文本同时存在于 `b22aReference.ts`（预置落库）
  - 断言 `B22A-T3-item-7-*` **6** 个键值全为空（人工新增行证据）
  - 断言 seed / 测试目录对 `B22A-T3-item` 零命中（排除 seed 产物）
  - _判据：BC-18、BC-59_

- [ ] 19. canary 改线：显式册指定（BC-50 制约）
  - 🔴 不得依赖 finder 内部排序：`B22A` 有 **11** 本候选册，实测解析到 `B22A-4-1 IT概要.xlsx`
  - 改线须显式声明权威册，并在守卫中断言该册的 size + sha256
  - 🔴 BC-55 制约：`wp_index` 中 `B22A` 有 **2** 行，须确定用哪一行并断言
  - _判据：BC-50、BC-55、BC-44_

- [ ] 20. canary 双向读写一致性
  - 结构化视图与 OO 视图读同一权威源
  - OO 侧写入后切回结构化视图能反映写入结果（非缓存快照）
  - 变异证明用 `B22A-T3-item-7` 空白新增行（不得用预置文本行，改预置会被 `b22aReference.ts` 覆盖）
  - _判据：BC-18、BC-59_

- [ ] 21. canary 回滚路径
  - `capability` 可从 `bidirectional` 退回 `null` 且不留脏数据
  - 既存 B60 pilot 的 **7** 处断言保持通过
  - 共享基类 `useWorkpaperEntryDualMode` 的其他 21 条生产边（26 − 5）不受影响
  - _判据：BC-2、BC-58_

- [ ] 22. 公式层判据（BC-14、BC-40）
  - 断言公式格仅 **3**（全在 `B22A-4-1 IT概要`，全裸 IF）⇒ canary 册恰是唯一含公式的册
  - 断言 `derived_total` 冒号式 **0**（空分母）/ `.reduce(` **4**（仅 `gt-b1-risk-assessment`）
  - 断言无「公式行数超数据行数致除零」形态（BC-40 空分母）
  - _判据：BC-14、BC-40、BC-20_

## 阶段 5：slice 缺陷回报

- [ ] 23. slice 自相矛盾与漏登回报（BC-47、BC-48）
  - 回报 `label_as_key_sites` 漏登 **1** 处：`GtB50RiskAssessment.vue#L1499` 的 `` :key="`${row.name}-${a}`" ``（复合 key 仍以 `row.name` 为基）⇒ 实际 4 处而非 3 处
  - 回报 `dynamic_row_identity` 只登记 `b14_chapter_table_rows` 1 个表，实测函数参数式下标 **38** 处横跨 5 个宿主
  - 断言 Property 22 站点 **5** 条（b14 2 + b23 3）的 key 用 `col.key` / `col.field` 属正确形态，不计缺陷
  - 断言 `dynamic_column_sites` 全 slice 7 条中 B 域占 5
  - _判据：BC-47、BC-48、BC-53_

- [ ] 24. BC-45 对偶形态登记
  - 断言 `B22B` 被 **2** 条 entry 共用（`gt-b22-b-control-matrix` 与 `gt-b22-b-deficiency-evaluation`，不同 componentType + 不同宿主）
  - 断言 `gt-b22-b-deficiency-evaluation` 的 `wp_code_count_via_component_type` 为 **0**（override 表零命中）
  - 断言这是 A 域 BP-11（单宿主多 componentType）的对偶：多 entry 共用一个 wp_code pattern
  - _判据：BC-45、BC-15_

- [ ] 25. BC-15 pattern 与真实码不一致登记
  - 断言 **6 / 10** 条 pattern 与真实 wp_code 不一致（仅 B22 家族 4 条一致）
  - 最严重：`gt-b14-due-diligence-report` 的 pattern 为 `B14D` 而真实码是 `B1-4`
  - `gt-b1-risk-assessment` 的 1 个 componentType 覆盖 **4** 个 wp_code
  - _判据：BC-15、BC-51_

- [ ] 26. 门与接线判据（BC-4、BC-12、BC-37）
  - 断言 `ElMessageBox.confirm` **12** 处 / 5 文件，确认门独立于 mode 门控存在
  - 断言 `GtEntrySyncCapabilityNotice` 在 10 宿主中命中 **0**（同 A 域），tooltip 不计作 notice 接线
  - 断言 `prefill` **4** 处 / 1 文件
  - 断言 `onlyoffice/health` **2** 处 / 2 文件（A 域 13，B 域显著更少）
  - _判据：BC-4、BC-12、BC-37、BC-3_

- [ ] 27. 边界与校验器判据（BC-25、BC-28、BC-33）
  - 断言归档 spec 边界：**9** 份真 B 域 spec 全部 100% 完成（`b22a-control-matrix` 47/47 · `b22b-deficiency-evaluation` 45/45 · `b50-risk-assessment` 41/41 · `b22-entity-control-rework` 32/32 · `b23-process-control` 26/26 · `b60-dedicated-component` 25/25 · `b1-4-due-diligence-report` 21/21 · `b23-business-control-rework` 19/19 · `b50-workpaper-rework` 8/8）⇒ 与 A 轮 6 份未完成反向
  - 断言 `resolveProcedureSheetKey.ts` 存在（15 处引用）但 **B 分支为 0**（与 A 域同态）
  - slice schema 校验器走追加节（`residual_inconsistency` 处置同 A 轮）
  - 断言既存守卫 `test_task57_abcs_and_shared_migration.py` 对 B 域 10 条 entry 零逐条断言（仅 `b60` 7 处）
  - _判据：BC-25、BC-28、BC-33_

## 外部依赖（本轮不可标 completed）

- [ ]* 28. BP-1 approved 模型落地 —— 全 slice 10 条 B 域 entry 共有阻塞
- [ ]* 29. BP-2 contract 定义 —— 同上
- [ ]* 30. BP-3 capability 裁决流程 —— 同上
- [ ]* 31. BP-4 bundle + published representation —— 同上
- [ ]* 32. BP-5 adapter 注册 —— 同上
- [ ]* 33. BC-49 数据验证扩展保留 —— openpyxl 无解，须换库或放弃该能力
