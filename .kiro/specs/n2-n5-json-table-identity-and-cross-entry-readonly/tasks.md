# N2 / N5 整表 JSON 行身份与跨 entry 只读 — 任务

约定：`[ ]` 待办 · `[ ]*` 受外部依赖阻塞（不计入完成率）。共同判据只引用 **NC 编号**，判据正文在 foundation。

🔴 **跨 spec 顺序硬约束**：任务 6（N5 inert 修复）须在 foundation 任务 13（N4 inert 修复）**之后**，复用其已验证形态；任务 7（行身份改造）须在 foundation 任务 14（E 族样板提取）**之后**；任务 14（删 orphan）须在任务 7 之后。

## 阶段 1 — 归属基线

- [x] 1. lane3 归属守卫
  - 落地 `design.md` 归属份额表全部 17 行，逐行与 foundation 算术自检表比对（任一不等即视为归属错）
  - 断言 entry 2 条全名、科目跨类（2221 负债/贷 vs 6801 损益/借）、BP 数 N2 **8** / N5 **10** 且成员集吻合
  - 断言本 spec 三项过半：sheets 34/59 · 公式格 1194/2185 · 带 fx 30/49
  - _Requirements: 1_
  - _NC/NB-P: NC-1 · NC-22 · NB-P1 ~ NB-P3_

## 阶段 2 — BP-12 跨 entry 只读契约

- [x] 2. 固化 `useN5CrossSheet.ts` 8 键只读契约
  - 8 键跨 5 命名空间：A（`A-accounting-profit` / `A-profit-total`）· I2（`I2-1-audited-total`）· I6（`I6-1-audited-total`）· N1（`N1-1-total-audited` / `N1-1-total-begin`）· N3（`N3-1-change-total` / `N3-1-end-balance-total`）
  - 🔴 断言无任何指向这 5 个命名空间的写入路径（只读单向）
  - 守卫锁定 8 键现值，新增或删除时显式失败
  - _Requirements: 2_
  - _NC/NB-P: NC-19 · NB-P4 · NB-P5_

- [x] 3. 登记 N 键被外部引用的一侧（双向都要）
  - `nCycleTaxConsistency.ts` **10** 处 · `cycleImportExportRegistry.generated.ts` **6** · `workpaperSyncManifest.generated.ts` **4** · `ForceGraph.stories.ts` 3
  - 🔴 `nCycleTaxConsistency.ts` 连 `^n[1-5]` 也不匹配（`nCycle` 开头）⇒ 文件集判据须三路取并（依 NC-5）
  - 断言 N5 10 键（含 5 cross）· N2 7 键；BP-12 收口为空集
  - _Requirements: 2_
  - _NC/NB-P: NC-5 · NC-19 · NB-P6 ~ NB-P8_

## 阶段 3 — BP-8 行身份与 BP-5 开关

- [x] 4. N2 / N5 整表 JSON 行身份改造（**须在 foundation 任务 14 之后**）
  - 🔴 抄 E 族既有形态（全域 **86** 处 / 27 文件），禁自建新范式（依 NC-6 反转裁定）
  - 本 spec 范围内 `removeRow` 的 by_index 调用改为 by_rowid，守卫按单调方向断言
  - BP-8 的 N2 / N5 侧收口（N1 侧归 lane2，两侧都完成后 BP-8 成员集为空）
  - _Requirements: 3_
  - _NC/NB-P: NC-6 · NC-7 · NB-P9 · NB-P10_

- [x] 5. `transport_key` 守卫（N2 / N5 单一 owner）
  - N2 `useN2FormData.ts`（362 行）= `'N2-'` · N5 `useN5FormData.ts`（406 行）= `'N5-'`，均单一声明（双声明仅 N1 有）
  - `N2-1-rows` / `N5-1-rows` / `N5-5-rows` 各 **0** 命中（反向分母）
  - _Requirements: 3_
  - _NC/NB-P: NC-30 · NB-P11 · NB-P12_

- [x] 6. N5 inert 开关修复（**须在 foundation 任务 13 之后**）
  - 现状 `const dualMode = { ... onModeChange: () => {} }` 与 canary N4 **逐字同形** ⇒ 复用 foundation 已验证的改造形态，禁并行各自发明
  - 保留 `modeOptions` 为普通数组的事实（不带 `.value`，与 N1 / N3 的 ref 形态不同）
  - 改造后 N5 switch 从 `inert` 变 `redeemable`，BP-5 成员集变空集，foundation 与本 spec 事实基线表同步更新
  - _Requirements: 4_
  - _NC/NB-P: NC-13 · NB-P13 · NB-P14_

- [x] 7. N2 薄封装与共享基类边处理
  - 现状 17 行、无 localStorage 键、生产边 1 条、`mode.value` 赋值处 0（逻辑在共享基类内）
  - 评估是否移除薄封装；🔴 若移除须断言共享基类生产边 **26 → 25**（全域 26 生产 + 1 测试 = 27），不留悬空计数
  - 🔴 断言 BP-10 对本 spec **空分母**（N2 / N5 已采用共享路由），禁写「已验证正常」
  - _Requirements: 5_
  - _NC/NB-P: NC-11 · NC-19 · NC-20 · NB-P15 · NB-P16_

## 阶段 4 — 确认门异形与契约

- [x] 8. 确认门判据容忍 N5 结构异形
  - 🔴 `useN5Adjudication.ts` **不存在**，N5 的 `ElMessageBox.confirm` 落在 `N5TabAdjudication.vue`
  - 判据按「每 entry 至少一处 confirm」，禁按「每 entry 有同名 composable」
  - 断言确认门与发布门交集 **0**（不强求同文件相邻）；发布门本 spec **2** 处且不新增第 3 处
  - _Requirements: 6_
  - _NC/NB-P: NC-3 · NC-4 · NB-P17 · NB-P18_

- [x] 9. 契约双列映射（载荷全在 `conclusion`）
  - `conclusion` 非空 N2 **4** + N5 **3** = **7**；`remark` 非空 **2** 行
  - 🔴 这 2 行 **100% 是 AI 会话**（`N2-review-session-*` / `N5-review-session-*` 各 261 B）⇒ 白名单排除必须在解析前生效，否则会把会话记录当行表 JSON 解析
  - 采「实际非空列优先于后缀规则」（与 lane2 同一裁定）
  - 披露表读写覆盖两变体；🔴 N5 国企版 sheet 名缺右括号（`附注披露信息（国企`）须按原始字面量匹配，禁补括号
  - _Requirements: 7_
  - _NC/NB-P: NC-10 · NC-26 · NC-34 · NB-P19_

- [x] 10. 真库污染 2 条登记（asyncpg）
  - `N2-3-entries` / `N5-3-entries` 均落 `wp_code='G8'`，登记 + 守卫锁定现值，**不就地清理**（依 NC-19 平台级裁定）
  - 实现 `-3-entries` 双向回写时以 entry 自身 `wp_code` 为写入目标
  - 无库环境 skip 并标原因，禁静默 pass
  - _Requirements: 8_
  - _NC/NB-P: NC-19 · NB-P20_

## 阶段 5 — 模板缺陷登记

- [x] 11. 族 A1 两处真缺陷守卫（记录型，不改模板）
  - `N5-6-1 E12` `=C12+N5`（正确形态 37 行 ⇒ **37 : 1**）· `N5-8 H12` `=C12-B12+N5-E12-F12+G12`（正确形态 28 行，表头 H9 明写 `⑦=②-①+③-④+⑥-⑤` ⇒ **28 : 1**）
  - 🔴 登记 `N5-8` 的连带影响：r39 合计 `=SUM(H10:H38)` 因 H12 恒空而连带错（全域唯一有连带影响的超列缺陷）
  - 根因引 NC-32（`N5` 与 Excel A1 引用语法同形，列 N 超出 `max_column` 7 / 10）
  - `N5-6-1 D11 =SUM(D5:N16)` 判合法；🔴 断言本 spec **无族 A2**（空分母）
  - 🔴 本任务 SHALL NOT 修改 `.xlsx`，交付后模板 sha256 仍须 5/5 match
  - _Requirements: 9_
  - _NC/NB-P: NC-20 · NC-25 · NC-32 · NB-P21_

- [x] 12. footer / 脏字面量 / definedName 守卫
  - footer 缺斜杠 **2** 处（`N2/出口退税额复核示例` · `N5/…N3A (原底稿)`），形态 `&P&N`（全域 49 : 7 : 3）
  - 缺右括号 1 处（N5）· 外来字母码 `O1A` 1 处（N2 册）
  - 🔴 `出口退税额复核示例` 是 **visible** 的 ⇒ hidden 8 与 OO 兜底 12 的口径差 4 中有 1 来自此处，两套口径都声明
  - `definedName` N2 24 / broken 15（含 `'[2]2004'!#REF!` 新形态 + 中文名 `本循环科目`）· 🔴 **N5 为 0 / 0 ⇒ 声明空分母**，禁写「已验证 N5 无断链」
  - _Requirements: 9, 11_
  - _NC/NB-P: NC-9 · NC-20 · NC-21 · NC-24 · NC-26 · NC-36 · NB-P22_

- [x] 13. 超宽表遍历 + 「合计」标签非 A 列
  - `N5/附注披露信息（国企` 255 列 / 有值列 4 / 幽灵 **251** ⇒ 遍历上界取 `last_value_col`，守卫锁差值
  - 🔴 「合计 / 小计」定位改用「**首个非空列**」—— `N5-5` r63 标签在 **B 列**，是全域 34 处中唯一非 A 列的一处，M 轮限 A 列口径在此会漏
  - 标签字面量按原始 7 种集合匹配，禁去空格归一化
  - 登记幽灵行 Top（`N5-3` 12 · `N2-3` 10）· 公式格与裸 IF Top（`N2-1` 198 / 32 · `N2-7` 10 · `N2-10` 9 · `N5-5` 9 · `N5-1` 6 · `N5-6-2` 4）
  - 倒挤形态候选严格口径 **0**：`N5-8 H10~H38`（29 行同构核对）· `N2-6 F39`（应纳税额正常业务）· `N5-1 B8/F8`（跨表减法）—— 形态命中但业务正确
  - _Requirements: 10_
  - _NC/NB-P: NC-17 · NC-20 · NC-35 · NB-P22_

## 阶段 6 — orphan 删除与收口

- [x] 14. 删除 orphan 3 个（**须在任务 4 之后**）
  - `useN5DualMode.ts` · `useN5AiAssist.ts` · `n2VatSourceConstants.ts`
  - 🔴 统计须用含小写分支的正则，否则 `n2VatSourceConstants.ts` 会漏、本 spec orphan 数错报为 2（依 NC-5）
  - 🔴 3 个中只有 1 个与 dual-mode 有关 ⇒ 守卫类名沿用 `TestOrphanInventory`，非 M 轮的 `TestOrphanDualModeInventory`
  - 删前 grep 确认 0 生产引用；行数以现算为准，禁照抄删除清册（plan 计数本身有错，依 NC-29）
  - _Requirements: 12_
  - _NC/NB-P: NC-5 · NC-29_

- [x] 15. `N3A` 跨册碰撞交叉校验（与 lane2 联动）
  - 本 spec 侧 `…N3A (原底稿)`（N5 册，半角括号 + 前导空格）· lane2 侧 `递延所得税负债审计程序表的N3A`（N3 册）
  - 🔴 判据按 `(册, sheet 名)` 二元组定位，禁仅按 sheet 码；测试注释须指向 lane2 `n1-n3-host-inline-router-and-shared-adoption` 的对应断言
  - 「原底稿」三形态各不相同：`表O1A （原底稿）`（N2 册，全角空格 + 全角括号）· `表O2A（原底稿）`（N4 册，foundation）· `表N3A (原底稿)`（N5 册，半角括号 + 前导空格）⇒ 本 spec 占 **2** 张，禁单一分隔符假设
  - 断言全域仅 2 张「净」程序表（`表N2A` · `表N5A`），两者都在本 spec
  - _Requirements: 13_
  - _NC/NB-P: NC-10 · NC-21 · NC-27_

- [x] 16. 交付前自检
  - 归属份额表 17 行等式全过；NB-P1 ~ NB-P22 无缺号且每条关联 NC
  - 模板 sha256 仍 5/5 match；无 U+FFFD；「N 处」类表述与列举项数一致
  - 校验本 spec 未复述任何 NC 判据正文（只引编号）
  - 校验三处跨 spec 顺序约束（任务 4 / 6 / 14 的前置条件）已在实施记录中体现
  - _Requirements: 1, 9_
  - _NC/NB-P: NC-1 · NC-11 · NC-25_

- [ ] 17.* 平台级欠账（不在本 spec 闭合）
  - BP-1 / BP-2 / BP-3（approved 权威模型与 contract/bundle · published 表示层 · 真 OnlyOffice 9.4 探针）
  - G8 污染清理（须跨循环统一方案，N 侧单独清理无效）
  - 阻塞理由：跨循环 / 平台层，单 lane spec 无法闭合
  - _Requirements: 8_
  - _NC/NB-P: NC-19_


---

## 实施记录（2026-10-01，append-only）

**守卫**：`backend/tests/workpaper_sync/test_n_lane3_json_table_identity.py`（复用 foundation 的 `n_cycle_scanner.py` / `n_cycle_facts.py`，不另写口径）· 前端 `composables/__tests__/nCycleLane3RowIdentity.spec.ts`（13 例）。

**代码改动**：
- T4（BP-8 收口）：`useN5TaxAdjustment` / `useN5DeferredReconcile` / `useN5RdSuperDeduction` / `useN2OtherTaxCalc` 行对象加 `rowKey`（随行落库），增删改全部按身份寻址，复用 foundation 提取的 `shared/stableRowIdentity.ts`（新增确定性派生 `assignStableRowKeys` / `withStableRowKeys`：旧数据无身份时由编码/名称派生，computed 重算不漂移，重名追加 `#n`）。N2-8 渲染键 `manual-${idx}` 改为与持久化身份同源。
- 🔴 **顺带修掉两处真缺陷**（不在 spec 原文里，改身份时暴露）：① `N5TabTaxAdjustment.vue` 渲染的是**按分类过滤后**的 `filteredRows`，却拿模板行下标去改**未过滤**数组 ⇒ 有过滤时改/删的是另一行；② `N5TabRdSuperDeduction.vue` 把费用化/资本化分两张子表渲染，子表下标 ≠ 全量下标 ⇒ 在资本化子表改第 1 行实际改的是费用化第 1 行。两处均有前端用例钉住。
- T6：N5 inert 开关复用 foundation T13 形态（统一能力层探针 + 显式回落提示），`modeOptions` 保持普通数组。
- T9：四张表读取改走 `shared/checklistPayload.ts`（实际非空列优先 + AI 会话白名单解析前排除）。
- T14：删除 `useN5DualMode.ts` / `useN5AiAssist.ts` / `n2VatSourceConstants.ts`（删前 0 生产边 0 测试边，删后无新增二阶 orphan）。
- T7：N2 薄封装**保留**（移除只省 17 行却要改宿主载体，收益低于风险）⇒ 共享基类 N 域边仍 1 条。

**🔴 现算偏离**：真库 lane3 现 3 行（design 10 行）、污染 0（design 2）⇒ T10 锁现值、不宣称污染判据通过；`definedName` N2 broken 现算 14（design 15）；共享基类生产边现算 24（design 26 → 25 作废）。

**跨 spec 顺序约束**：T6 在 foundation T13 之后 ✓ · T4 在 foundation T14 之后 ✓ · T14 在 T4 之后 ✓。

**未做**：T17 `[ ]*` 平台级；Playwright 真浏览器实测未做（需 start-dev.bat 环境）。


### 真浏览器补充验收（2026-10-01）
- N5：16 tab 可见；N5-1 工具栏/notice 真渲染，HTML ↔ OnlyOffice 真切换；N5-5（18 行）、N5-4（9 行）、N5-8（8 行）、N5-6-1（空分母）逐页无 ErrorBoundary、console 0 error、打开页面无 PUT。
- N2-8 首轮抓到**整套接口过期**：组件仍读已从 composable 删除的 `monthlyRows/quarterSummaries/exemptMonths/setMonthlyData`，打开即 `undefined.value`。否决伪造月度兼容字段，页面改按当前权威 `allCalcRows`（3 自动附加税 + 稳定身份手工税种）渲染；实测 7 行、9 列、汇总卡完整、console 0 error。浏览器新增 1 行→8、按 rowKey 删除→7 闭环通过；实测临时行及默认持久化行已删除恢复原库。
- EventBus 同步为单一发布方：页面不再重复投第二种 `tax-accrual:updated` 载荷；composable 按契约发 `accruals/totalAccrual/timestamp`。N3/N4/N5 的相关事件类型与真实载荷同步收口。
