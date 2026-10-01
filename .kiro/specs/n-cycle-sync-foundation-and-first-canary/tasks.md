# N 循环双向回写地基与首张 canary — 任务

约定：`[ ]` 待办 · `[ ]*` 受外部依赖阻塞（不计入完成率，理由须写明）。任务引用 `_Requirements:` 与 `_NC/NF-P:` 双轴，便于复盘校验引用闭合性。

## 阶段 1 — 扫描器地基与事实基线

- [x] 1. 建 N 域扫描器模块 `backend/scripts/analyze/n_cycle_scanner.py`
  - 实现 strict 域三路取并（目录段 / 大写文件名 / **小写 `n{1..5}` 前缀** / `nCycle` 内容引用），断言总 160（生产 135 / 测试 25）、`loose_only` = 0
  - 实现注释剥离（块 / 行 / HTML，同长空白替换以保留行号），统一行数口径 `len(text.split("\n"))`
  - 提供变异证明开关：去掉小写分支时应漏 35 个文件、orphan 数应从 8 降为 6
  - _Requirements: 9_
  - _NC/NF-P: NC-5 · NF-P10_

- [x] 2. entry 基线与归属算术守卫
  - 断言 entry 5 条全名、wp_code / 科目 / 借贷方向四分映射、`N0` 不存在、slice 无 `pilot`
  - 落地 `design.md` 算术自检表全部 17 行等式（sheets 59 / 公式格 2185 / 带 fx 49 / HTML child 45 / prog 2 / OO 兜底 12 / mount 15 等）
  - 断言 BP 公共 7 项、区分项成员集、逐 entry 9/8/9/8/10
  - _Requirements: 1, 6_
  - _NC/NF-P: NC-1 · NC-22 · NF-P1 ~ NF-P3 · NF-P34_

- [x] 3. 模板前置守卫：sha256 / size / 公式格口径
  - sha256 与 size 5/5 match 断言置于测试文件最前，失败即中止
  - 公式格 2185（口径 `data_only=False` + `startswith('=')` + `len > 1`）、带 fx sheet 49
  - `data_only=True` 反证命中 0（slice `formula_scan_policy` 明文要求）
  - _Requirements: 7_
  - _NC/NF-P: NC-25 · NF-P4 · NF-P5_

## 阶段 2 — 共同判据的可执行形式

- [x] 4. 行身份六族与 `removeRow` 归类扫描器
  - 六族现算：A 3 / B 67 / C 7 / D 29 / **E 86 / 27 文件** / M 式 0
  - `removeRow` 四元组归类：14 种签名 / 32 命中 / by_index 18 : by_rowid 13 : other 1
  - 🔴 断言方向为「by_index 单调降、by_rowid 单调升」，禁沿用 M 轮「从 0 建起」
  - 用 M 轮同一扫描器在 M 域跑出非零，作为「M 式 = 0」的变异证明
  - _Requirements: 10_
  - _NC/NF-P: NC-6 · NC-7 · NC-8 · NF-P12 · NF-P13_

- [x] 5. `transport_key` 解析与键全集守卫
  - owner 常量 6 处逐一现读吻合；N1 双 owner 声明（`'N1-'` + `'N1-1-adj'`）登记
  - 🔴 TK-2 用双条件判据（模板串命中 + 展开数 == `N1_ADJUDICATION_CATEGORIES` 长度 7），禁用恒假的「字面量至少 1 命中」
  - 8 个 `nonexistent_guessed_keys` 各 0；`N4-1-rows-v2` 命中 1（orphan 自身）⇒ 两类不混
  - `useChecklistPersistence` = 0（`shared_adapter_absent`）
  - 断言 `item_id` 命名轴：owner 常量 6 处中 N1 占 2（`two_source_declarations` = 1，全域唯一），其余 4 entry 各 1；localStorage 声明点按 NC-16 现算
  - _Requirements: 10_
  - _NC/NF-P: NC-15 · NC-16 · NC-30 · NF-P14 · NF-P15_

- [x] 6. 超列引用三族扫描器（wp_code 与 A1 同形）
  - 先剔 `'...'!` 段、中文 sheet 名 `!` 段、函数名；正确口径 17 = A1 3 + A2 11 + B 3
  - 附错口径 232 对照（误报 215），防未来放宽正则
  - A1 逐处锁反向分母（9:1 / 37:1 / 28:1）；A2 锁「无反向分母、整列同形」；B 判合法
  - _Requirements: 15_
  - _NC/NF-P: NC-32 · NF-P20_

- [x] 7. 合计/小计与倒挤链严格口径扫描器
  - 「漏加小计」双条件（同段连续区间 + 同行跨列写法不一致）⇒ 真值 0；附粗口径误报 8 的现读依据
  - 变异证明：同一扫描器在 M 域 M10 上应命中
  - 倒挤减法链严格口径 0；登记形态候选 32 处逐处业务正确性依据
  - 「合计/小计」标签 34 处 / 7 种字面量；🔴 判据用「首个非空列」而非限 A 列（`N5-5` r63 在 B 列）
  - _Requirements: 8, 17_
  - _NC/NF-P: NC-17 · NC-20 · NF-P21 · NF-P22 · NF-P23_

- [x] 8. 模板几何与脏形态守卫
  - sheet 名 3 种脏形态、审计程序表 8 张 6 形态、「原底稿」3 张三形态、跨册码 `N3A` 碰撞、外来码 `O1A`/`O2A`；🔴 禁归一化，按原始字面量比对
  - hidden 8（`GT_Custom` 5 + 原底稿 3）与 OO 兜底 12 的口径差 4，两套口径都声明
  - footer 三形态 49 / 7 / 3 = 59；`definedName` 72 / broken 45（N4·N5 各 0）含 `'[2]2004'!#REF!` 新形态与中文名 `本循环科目`
  - 超宽表 2 张（幽灵 249 / 251）+ 幽灵列 24 处；遍历上界取 `last_value_col`
  - 裸 IF 244 分布；公式格 Top 5；变体轴 4 : 1 且 N3 无附注披露
  - _Requirements: 17, 18_
  - _NC/NF-P: NC-9 · NC-10 · NC-21 · NC-24 · NC-26 · NC-27 · NC-35 · NC-36 · NF-P23 ~ NF-P28_

- [x] 9. 结构性零 16 项 + 变异证明
  - 逐项实现「零断言 + 变异证明」成对结构，单独零断言视为未完成
  - 两项附对照：合计漏加小计（误报 8）· 倒挤链（候选 32）
  - _Requirements: 8_
  - _NC/NF-P: NC-20 · NF-P35_

## 阶段 3 — 契约、真库与口径差

- [x] 10. 契约字段双列映射（`remark` + `conclusion`）
  - 🔴 映射覆盖 `conclusion`（非空 23 > `remark` 非空 4），推翻 M/L 轮「只映 remark」
  - `*-review-session-*` 键白名单排除（3 行各 261 B，非业务载荷）
  - 冲突优先级按 `item_id` 后缀判（`-rows`/`-entries` → `remark`；`-disclosure-*` → `conclusion`；都不匹配记冲突并跳过，不猜）
  - _Requirements: 11_
  - _NC/NF-P: NC-34 · NF-P16_

- [x] 11. 真库跨 entry 污染登记（asyncpg）
  - 断言 N 域 30 行、归属 1 + 19 + 10、`conclusion` 非空 23
  - 污染 4 条全落 `wp_code='G8'`（`N1/N2/N3/N5-3-entries`）；登记与 L 轮 LC-22 同宿主
  - 🔴 登记 slice `cross_entry_isolation` 只扫代码不查库的局限（L / N 两轮连续漏检）
  - 无库环境 skip 并标原因，禁静默 pass
  - _Requirements: 12_
  - _NC/NF-P: NC-19 · NF-P18 · NF-P19_

- [x] 12. 口径差 14 组与现算纪律
  - 落地口径差对照表全部 14 行；🔴 配对数现算 `C(len(slices), 2)`，禁引用 slice 自相矛盾的 55 / 66
  - 契约目录 30（生产 28 + candidate 2）· `adapter_id` 非空 5 ⇒ 28 : 5
  - notice 全域 53 / N 域 0 · `derived_total` TAIL 28 : MID 37 · `cycleSheetRouting` 3
  - orphan 行数以现算 1331 为准，注释写明 plan 的 1325 / 288 / 773 是错值
  - _Requirements: 13, 19, 20_
  - _NC/NF-P: NC-11 · NC-12 · NC-14 · NC-29 · NC-37 · NF-P29 ~ NF-P31 · NF-P36 ~ NF-P39_

## 阶段 4 — canary N4 闭环

- [x] 13. 修复 canary 短板 ①：N4 的 inert 模式开关
  - `host_inline_inert` 的 `onModeChange: () => {}` 改为真实实现（切换 + health 检查 + 失败回落 HTML）
  - 保留宿主内联形态（依决策 3 不做载体归一化），但门控须由 `dualMode.currentMode.value === 'onlyoffice'` 真实驱动
  - 🔴 修复后 N4 的 switch 从 `inert` 变 `redeemable`，须同步更新 `design.md` 事实基线表并在守卫中断言变更
  - _Requirements: 5_
  - _NC/NF-P: NC-13 · NF-P9_

- [x] 14. 提取 E 族稳定行身份正面样板（**必须在删 orphan 之前**）
  - 从 `useN4AdjudicationV2.ts`（9 处）与 `useN4DetailV2.ts`（9 处）提取 18 处 `rowId`/`rowKey`/`id` 形态到正式模块
  - 提取后以测试固定形态，确保删 orphan 不丢样板
  - _Requirements: 10_
  - _NC/NF-P: NC-6 · NF-P12_

- [x] 15. canary `N4-1-rows` 双向回写闭环
  - 读路径：`remark`（1665 B）解析为行表，`rowKey: "row-消费税"` 作稳定语义键
  - 写路径：只走 `audit-determination/publish-to-tb`（现算 5 处之一，不新增第 6 处）；禁在 watch / onMounted / debounce 回调内触发
  - 确认门：沿用 `useN4Adjudication.ts` 内既有 `ElMessageBox.confirm`（与发布门分居，交集 0，不强求同文件）
  - 断言 `N4-1-rows` 非 `parent_duplicate`、单 sheet 单键组（宿主 sheet `税金及附加审定表N4-1`）
  - _Requirements: 3, 5_
  - _NC/NF-P: NC-3 · NC-4 · NC-18 · NF-P6 · NF-P7 · NF-P17_

- [x] 16. 把 N4 域 by_index 删行改造为 by_rowid（抄已有 13 处形态）
  - 🔴 目标是「改造成已存在的正面形态」，不是「从零自建」（M 轮结论在 N 反转）
  - 改造后 by_index 计数下降、by_rowid 上升，守卫按单调方向断言
  - _Requirements: 10_
  - _NC/NF-P: NC-6 · NC-7 · NF-P13_

- [x] 17. 删除 foundation 归属的 3 个 orphan（**在任务 14 之后**）
  - `useN4DualMode.ts` · `useN4AdjudicationV2.ts`（真实 294 行，plan 记 288 为错值）· `useN4DetailV2.ts`
  - 删前 grep 确认 0 生产引用；删后 orphan 总数从 8 降为 5，`TestOrphanInventory` 同步更新
  - _Requirements: 9, 20_
  - _NC/NF-P: NC-5 · NC-29 · NF-P11_

- [x] 18. 登记 canary 短板 ②：模板缺陷 T-1 守卫
  - `N4-2 E9` 的 `=B9+C9+N4` 以**记录型**测试锁定现状（反向分母 9 : 1），未来修复时测试显式失败提醒同步更新
  - 🔴 本任务 SHALL NOT 修改 `.xlsx`（模板 sha256 交付后须仍 5/5 match）
  - _Requirements: 7, 15_
  - _NC/NF-P: NC-32 · NF-P5 · NF-P20_

## 阶段 5 — 收口与平台级欠账

- [x] 19. BP-7 接入 `GtEntrySyncCapabilityNotice`
  - N 域现算 0 命中（全域 53），须新接入 N4 宿主；🔴 tooltip 不算接线
  - _Requirements: 6_
  - _NC/NF-P: NC-12 · NF-P39_

- [x] 20. `parent_duplicate` 条件节实装（判据在此，数据在 lane2）
  - K/L/M 三轮该字段均 0，N 首次触发（4 条全挂 N1）⇒ 从空壳分支改为实装并断言 4 条
  - 本 spec 只交付判据与守卫骨架，N1 侧数据断言由 lane2 完成
  - _Requirements: 14_
  - _NC/NF-P: NC-31 · NF-P33_

- [x] 21. `resolveProcedureSheetKey` 现状核对（反转项，无欠账）
  - 断言 N 段完备 5/5（`N1→n1a` … `N5→n5a`，文件 90 行）
  - 🔴 同时断言 **M 段仍只 6 条**（M 轮欠账未修，不因本轮而变），避免误记为已修
  - N 为单位数码，无 M10 那类多位数顺序陷阱 ⇒ 无需顺序守卫
  - _Requirements: 17_
  - _NC/NF-P: NC-28 · NF-P32_

- [ ] 22.* 平台级欠账登记（不在本 spec 闭合）
  - BP-1 approved 权威模型与 contract / bundle · BP-2 published 表示层 · BP-3 真 OnlyOffice 9.4 探针
  - NC-33 `validate_slice_against_schema` 把 `forbidden_identity_kinds` 字面值当非法声明拒收（反向激励藏缺陷）⇒ 正解是区分「声明存在」与「实际使用」两语义，归平台层
  - NC-19 G8 跨循环污染汇聚点清理（须跨循环统一方案，N 侧单独清理无效）
  - 阻塞理由：均需跨循环 / 平台层方案，单循环 spec 无法闭合
  - _Requirements: 6, 12, 16_
  - _NC/NF-P: NC-19 · NC-33 · NF-P18 · NF-P40_

- [x] 23. 交付前自检
  - 跑 `design.md` 算术自检表 17 行等式，任一不等即视为归属错
  - 校验 NC-1 ~ NC-37 与 NF-P1 ~ NF-P40 无缺号、每条至少被本 spec 或 lane spec 引用一次
  - 🔴 校验唯一判 ❌ 不适用的 **NC-23（`SHEET_MAP` 常量映射）**已显式写出空分母及其现算证据，SHALL NOT 静默省略
  - 校验模板 sha256 仍 5/5 match、无 U+FFFD、「N 处」类表述与列举项数一致
  - 🔴 校验「M 轮换 canary 判据是 M 特有、本轮收回」的声明仍在交付物中
  - _Requirements: 1, 2, 5, 7_
  - _NC/NF-P: NC-1 · NC-18 · NC-20 · NC-23 · NC-25_


---

## 实施记录（2026-10-01，append-only）

**交付物**：扫描器 `backend/scripts/analyze/n_cycle_scanner.py`（三份 N spec 共用的唯一口径）· 基线与分歧登记 `backend/tests/workpaper_sync/n_cycle_facts.py` · 守卫 `backend/tests/workpaper_sync/test_n_cycle_foundation_canary.py`（**87 passed**）· 前端正面样板 `composables/shared/stableRowIdentity.ts` + 双列取列 `composables/shared/checklistPayload.ts` · 前端往返测试 `composables/__tests__/nCycleCanaryRowIdentity.spec.ts`（15 例）。

**代码改动**：
- T13 / lane3 T6：`GtN4TaxesAndSurcharges.vue` / `GtN5IncomeTaxExpense.vue` 的 `onModeChange: () => {}` 改为真实切换（统一能力层 `sync/onlyOfficeHealth.ts` 探针 + 不可用时显式提示并回落 HTML + OO `@fallback` 回落）；未新增 health 直调字面量。
- T19：两宿主接入 `GtEntrySyncCapabilityNotice`（常显摘要，非 tooltip）。
- T10 / T14 / T16：`useN4Adjudication.ts` 取列改走 `payloadJson/payloadText`（原 `remark ?? conclusion` 在 remark 为空串时静默丢整表）；删行改 `removeRowByKey`（原 `splice(idx,1)`）；身份改 `adoptRowKey`/语义键，**同税种第二行自动退熵键防重复身份**。
- T17：删除 `useN4DualMode.ts` / `useN4AdjudicationV2.ts` / `useN4DetailV2.ts`（删前 0 生产边 0 测试边；样板已先提取）。

**变异证明**：5 个源码变异（恢复空实现 / 去 notice / 改回 splice / 改回 `??` 取列 / 再抄一份 health 直调）各自红在预期测试上；单区域 `tsconfig._n-cycle-sync.json` 的 vue-tsc 对本轮 5 个文件 0 错误，注入 `number = 'x'` 报 TS2322（非 OOM 假绿）。

**🔴 现算与 design 的偏离（逐条见 `n_cycle_facts.DESIGN_VS_RECOMPUTED`，17 条）**，最重要的三条：
1. **真库 N 域只剩 3 行**（design 30 行）：全表 `checklist_responses` 仅 42 行。⇒ T11 污染现算 **0**（design 4）；T15 canary `N4-1-rows` 真库 **0 行** ⇒ **真库往返空分母，不宣称通过**，闭环由前端往返测试（读 conclusion 列 → 删中间行 → 写回 → 再读，不串行）证明。决策 1「分母非空故收回硬标准」在实施时点前提不成立，已登记。
2. 超列引用正确口径 **17 = 3 + 11 + 3 与 design 逐值吻合**，但 design 的口径描述不足：只剔 `'…'!` 会把限定段后的引用留下按本表列宽误判（N2 附注 +39 假阳）；已改为连同引用一起剔。
3. design「合计漏加小计粗口径 8」与其正文列举的 4 处不等（design 内部矛盾），以列举为准。

**连带改动既存守卫 `test_task56_n_cycle_migration.py`**（它锁 slice 时点现状，代码按 spec 改了必然红）：不删判据，改为「未登记文件仍逐值相等、`n_cycle_facts.POST_SLICE_EDITED_FILES` 登记的文件改为单调/结构断言」，并加反向约束（只许兑现 slice 判 inert 的 entry、只许删 slice 判 orphan 的模块）。归因：动手前 task56+task66 预存红 22 条，本轮引入 6 条已全部消化；task56 现余 5 条红**均为预存**（契约目录/registry/notice 平台计数漂移，与 N 无关）。

**🔴 待用户决策**：删 V2 孪生后出现**二阶 orphan** `composables/n4TaxTypes.ts`（N4 税种词典 `n4NormalizeKey`，唯一消费方是被删的 V2）。它不在任何删除清单里且承载「N4-1 行键与 N4-2 税种名不一致」的修复意图 —— 接到 live 的 `useN4Adjudication`/`useN4Detail` 还是删除，属业务决策，已登记 `SECOND_ORDER_ORPHANS_CREATED`，未擅自处理。

**未做**：T22 `[ ]*` 平台级（BP-1/2/3、NC-33 校验器、G8 跨循环清理）；Playwright 真浏览器点「OnlyOffice」切换未实测（需 start-dev.bat 环境）。


### 真浏览器补充验收（2026-10-01，重启前后端后）
- N4-1：工具栏与 AC 1.4 常显 notice 真渲染；HTML → OnlyOffice 后 `.gt-onlyoffice-sheet` 真挂载、表格退出 DOM；切回 HTML 后 21 行恢复，console 0 error。
- 🔴 Playwright 抓到并修复：N4→N2 原调用**后端不存在**的 `/api/projects/{pid}/wp-index/by-code/N2`（恒 404 被 catch 吞掉）⇒ 改用平台约定 `/api/custom-query/wp-id-by-code`，网络实测 200 并继续 GET N2 checklist；同时修「N2 无行时每次打开 N4-1 无条件 PUT `{}` 覆盖历史计提额」，复测打开页面 PUT=0，实测误写行已精确删除恢复。
- 二阶 orphan `n4TaxTypes.ts` 已裁决删除：其唯一消费方是已删 V2 孪生；声称解决的税种别名问题已由 live `useN4CrossSheet._normalizeTaxName` 覆盖，另一潜在调用 `useN4Detail.updateN2Accruals` 全仓 0 调用方，接线无对象。
