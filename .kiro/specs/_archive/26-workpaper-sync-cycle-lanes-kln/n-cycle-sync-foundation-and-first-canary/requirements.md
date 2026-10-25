# N 循环双向回写地基与首张 canary — 需求

## 引言

**上游**：umbrella Task 56 的 N slice（`backend/data/workpaper_sync_n_cycle_manifest_slice.json`，172,620 B，冻结 2026-08-16）+ 删除清册 `backend/data/workpaper_sync_n_cycle_deletion_plan.json`（41,956 B）+ 既存守卫 `backend/tests/workpaper_sync/test_task56_n_cycle_migration.py`（2650 行 / 14 测试类 / 123 test）+ 前九轮共同裁决 FC-1~13 / GC-1~10 / HC-1~16 / IC-1~20 / JC-1~20 / KC-1~24 / LC-1~26 / MC-1~29。

**本 spec 的 entry 范围**：`xlsx/gt-n4-taxes-and-surcharges`（**1 条**，canary 所在 entry 完整纳入，沿用 H/I/J/K/L/M 六轮既定形态）。

**承接策略**：以 **MC-1~29 为基准逐条重裁**。MC 已是 F/G/H/I/J/K/L 七轮的收口层，故前七轮裁决经 MC 间接覆盖。MC-x 在 N 的适用性判定见 `design.md` 的 NC-1 ~ NC-37 对照表；**唯一判 ❌ 不适用的一项（MC-23）必须显式声明**，而 🔴 **M 轮判 ❌ 的 KC-17（prefill）在 N 上分母非空、重新适用** —— 不适用不是单向继承，每轮都要重算。

**既存守卫的边界**：`test_task56_n_cycle_migration.py` 锁「现状诚实记录」，本 spec 锁「改线后目标态」。凡判据与既存守卫重叠，本 spec **引用既存测试名**而非重写。🔴 **测试类名禁照抄 M**：N 有 `TestTransportKeyResolution` / `TestProperty23DynamicRowIdentity`，**M 有而 N 无** `TestProperty24ProtectedFormulaAndSummary`，且 M 的 `TestOrphanDualModeInventory` 在 N 改名为 **`TestOrphanInventory`**（因 orphan 不止 dual-mode）。

🔴 **N 循环另有 16 份已归档 spec**（底稿功能方向，与本系列的 sync 方向正交，合计 **494 task 全部 100% done**）：

| 归档区 | spec 数 | 合计 task |
|---|---|---|
| `_archive/02-workpaper-cycles/` | 1（`workpaper-n-tax-cycle`） | 27 |
| `_archive/05-business-features/` | **6**（n1-deferred-tax-assets / n1-loss-check-source-alignment / n2-taxes-payable / n3-deferred-tax-liabilities / n4-taxes-and-surcharges / n5-income-tax-expense） | 200 |
| `_archive/08-disclosure-notes/` | **8**（n-cycle-note-template… / n-cycle-tax-disclosure-alignment / n1-deferred-tax-disclosure-template-alignment / n1-disclosure-note-linkage / n1-four-table-extraction… / n2-disclosure-and-extraction-alignment / n2-vat-calc-source-alignment / n345-four-table-extraction-alignment） | 227 |
| `_archive/10-A~S-workpaper-all-cycles-complete/` | 1（`n-cycle-workpapers`） | 40 |
| `_archive/99-superseded/` | 1（`n2-source-alignment`，**无 tasks.md**） | — |

🔴 **与 M 轮的关键差异**：M 的 4 份里有 1 份 76/85（9 条未做）且含**假绿遗留**；**N 的 16 份全部 100% done、无未完成任务型欠账**。但「全绿」不等于「无假绿」—— 本轮实测仍抓到 slice/plan 未记录的模板层真缺陷（见 Requirement 15）。

## 术语与口径（先立规矩，后面 Req 直接引用）

- **N 域文件集（strict）**：前端 `audit-platform/frontend/src/` 下，路径含 `n{1..5}/` 目录段，**或**文件名匹配 `^(?:use|Gt)?N[1-5](?![0-9])(?:[A-Z]|[-.]|$)` **或** `^n[1-5][A-Z]`。🔴 **第三个分支不可省** —— N 域有 13 个**小写 `n{1..5}` 前缀**生产模块，抄 M 轮正则会漏 35 个文件（见 NC-5）。
- **宽口径差集为空**：`loose_only` 现算 **0**（同 M，N 的命名不撞其他循环）。
- **行数口径**：统一 `len(text.split("\n"))`。🔴 slice 与删除清册用 `splitlines()`，且 🔴 **删除清册的 orphan 行数计数本身有错**（见 Requirement 20）。
- **计数现算**：所有数字一律从源现算并与 `design.md` 等值比对。禁写死。
- **判据锚点**：用常量名 / 端点字面量 / 形态特征。🔴 **禁写死行号**。
- **注释剥离**：判 `el-segmented` / 端点调用前必须先剥块注释、行注释、HTML 注释（同长空白替换以保留行号）。
- **按索引删 / 按行身份删**：`removeRow` 首参含 `rowId` / `rowKey` / `.id` 判后者；含 `index` / `idx` 家族判前者。🔴 **N 域两者都非零**（18 : 13），不是 M 的 50 : 0。
- **canary**：entry `xlsx/gt-n4-taxes-and-surcharges`，宿主 sheet `税金及附加审定表N4-1`，键 `N4-1-rows`。

## 需求

### Requirement 1 — entry 边界与 manifest 分歧如实登记

**用户故事**：作为维护者，我要一眼看清 N 循环到底有几个 entry、哪些是 slice 的权威声明、哪些是 manifest 与 slice 的分歧，避免后续 spec 基于错误基数展开。

#### 验收标准

1. WHEN 现算 N slice 的 entry 清单 THEN 结果 SHALL 恰为 **5** 条，全名依次为 `xlsx/gt-n1-deferred-tax-assets` / `xlsx/gt-n2-taxes-payable` / `xlsx/gt-n3-deferred-tax-liabilities` / `xlsx/gt-n4-taxes-and-surcharges` / `xlsx/gt-n5-income-tax-expense`。
2. WHEN 校验 wp_code 与科目 THEN 映射 SHALL 为 N1D→1811 递延所得税资产（资产/借） · N2T→2221 应交税费（负债/贷） · N3D→2901 递延所得税负债（负债/贷） · N4T→6403 税金及附加（损益/借） · N5I→6801 所得税费用（损益/借）。🔴 **四分而非二分**：2 资产负债类借贷相反 + 2 损益类，判据禁假设「同循环同方向」（见 NC-22）。
3. WHEN 检索 `N0` 相关 entry THEN 结果 SHALL 为空 —— N 循环**不存在 N0 总表**，与 F/G 循环有 `F0`/`G0` 汇总层的形态不同。
4. WHEN 检索 slice 的 `pilot` / `pilot_entry` 字段 THEN 结果 SHALL 为空 —— N slice **未指定 pilot**，故本 spec 的 canary 由第 5 条需求自行裁定并登记理由。
5. WHEN 现算 `sheet_count` 归属 THEN SHALL 满足 `9 + 16 + 34 = 59`（本 spec 9 · lane2 16 · lane3 34），且 `HTMLchild 45 + prog_console 2 + OO兜底 12 = 59`。
6. 🔴 IF slice 的 `excluded_from_slice` 显式否决过某条捷径 THEN 本 spec SHALL NOT 重新引入该捷径，且 SHALL 在 `design.md` 引用其否决理由原文。

### Requirement 2 — 共同裁决 NC-1 ~ NC-37 只在本 spec 裁定一次

**用户故事**：作为三份 N spec 的共同上游，我要把跨 entry 复用的判据集中裁定，让 lane spec 只引用编号，避免三处复述后各自漂移。

#### 验收标准

1. WHEN 编写 `design.md` THEN SHALL 给出 **NC-1 ~ NC-37** 完整对照表，每条含「MC 基准编号 / 在 N 的判定（✅沿用 · ⚠️变形 · ❌不适用 · 🔁反转）/ N 侧现算分母 / 归属 spec」四列。
2. WHEN lane2 / lane3 spec 需要引用共同裁决 THEN SHALL 仅写编号（如「依 NC-32」），SHALL NOT 复述判据正文。
3. 🔴 WHEN 某条 MC 在 N 判 ❌ 不适用 THEN SHALL 显式写出「空分母」及其现算证据，SHALL NOT 静默省略。本轮 ❌ 仅 **1** 条（NC-23）。
4. 🔴 WHEN 某条在 N 判 🔁 反转 THEN SHALL 同时写出「M 轮结论」与「N 轮反证数据」。本轮 🔁 共 **4** 条：NC-6（零正面样板 → 13 处可抄）· NC-18（真库零载荷 → N4 有 1665 B）· NC-28（路由段有欠账 → N 段已完备）· NC-37（prefill 空分母 → 76 命中）。
5. WHEN NC 编号落地 THEN SHALL 无缺号、无重号，且每条至少被本 spec 或某 lane spec 的 tasks 引用一次（引用闭合性在 Task 6 复盘校验）。

### Requirement 3 — 写路径唯一与发布门不可绕过

**用户故事**：作为质控，我要确保 N 循环所有审定数回写只走既有显式发布门，不因新增 sync 能力而开后门。

#### 验收标准

1. WHEN 现算端点字面量 `audit-determination/publish-to-tb` THEN 生产代码命中 SHALL 为 **5**，分布恰为 `useN1FormData.ts` / `useN2FormData.ts` / `useN3FormData.ts` / `useN4FormData.ts` / `useN5FormData.ts`（每 entry 一处）。
2. WHEN 现算已废端点 `trial-balance/writeback` THEN 生产代码命中 SHALL 为 **0**（注释中 5 处不计）—— 平台铁律未被 N 域违反。
3. 🔴 WHEN 统计端点命中 THEN SHALL 同时识别单引号、双引号与**反引号模板串**三种写法，并 SHALL 先剥注释再统计。本轮 CODE 5 : CMT 15，两者必须分列。
4. WHEN 校验确认门 THEN `ElMessageBox.confirm` 现算 CODE **26** / **17** 文件，且与发布门所在 5 文件的**交集 SHALL 为 0** —— 确认门与发布门分居不同模块（同 M/L），本 spec SHALL NOT 断言「同文件内相邻」。
5. 🔴 WHEN 按 entry 核查确认门宿主 THEN SHALL 容忍 N5 异形：`useN{1..4}Adjudication.ts` 存在而 **`useN5Adjudication.ts` 不存在**，N5 的 confirm 落在 `N5TabAdjudication.vue`。判据 SHALL 按「每 entry 至少一处 confirm」而非「每 entry 有同名 composable」。
6. WHEN 新增任何 sync 写路径 THEN SHALL NOT 引入第 6 处 publish-to-tb 调用点，也 SHALL NOT 在 watch / onMounted / debounce 回调内触发发布。

### Requirement 4 — 三种载体并存的事实基线（禁按单一形态设计）

**用户故事**：作为实施者，我要知道 N 域双模载体有三种互不相同的实现形态，避免用 M 轮的单一形态假设写出必假红的判据。

#### 验收标准

1. 🔴 WHEN 现算 `*EntryDualMode.ts` 文件 THEN 结果 SHALL 为 **0** —— N 域**完全没有** M/L 轮那种独立 entry 级 dual-mode 模块（ND-2）。判据 SHALL NOT 以该文件名为锚点。
2. WHEN 现算 `useN[1-5]DualMode.ts` THEN SHALL 为 **5**，但其中 **3 个是 orphan**（`useN3DualMode` / `useN4DualMode` / `useN5DualMode` 无生产 import），仅 **2 个 live**（`useN1DualMode` / `useN2DualMode`）。
3. WHEN 分类载体 kind THEN SHALL 得三族：`per_entry_composable_three_modes`（N1，257 行，含 matrix 第三值）· `per_entry_wrapper_over_shared_base`（N2，17 行薄封装）· `host_inline`（N3/N4/N5，宿主 `.vue` 内直接 `const ... = ref/对象字面量`）。
4. 🔴 WHEN 细分 `host_inline` THEN SHALL 再分两亚族：**`host_inline_real`**（N3，`renderMode = ref<'html'|'onlyoffice'>('html')` + 真实 `checkOoHealth()` + `renderMode.value = val`）与 **`host_inline_inert`**（N4/N5，`const dualMode = { ... onModeChange: () => {} }` 空实现）。
5. 🔴 WHEN 用正则识别载体 THEN SHALL 覆盖**带泛型**的 `ref<'html' | 'onlyoffice'>(` 写法 —— 本轮实测抄 M 正则 `const renderMode = ref(` 会漏掉 N3。
6. 🔴 WHEN 识别模式门控 THEN SHALL 覆盖 `isOnlyOffice` 计算属性写法 —— N1 用 `v-if="isSwitchableSheet && dualMode.isOnlyOffice.value"`，其余 4 条用 `renderMode === 'onlyoffice'` / `currentMode.value === 'onlyoffice'`。且 N1 用 `isSwitchableSheet` 而非其余 4 条的 `isHtmlSheet`。
7. WHEN 现算 OO 挂点 THEN 分布 SHALL 为 N1 2 / N2 3 / N3 3 / N4 3 / N5 4，合计 **15**，且与 slice 的 `mount_count` 逐 entry 吻合。

### Requirement 5 — canary 判据回归 K/L 硬标准（显式收回 M 轮偏离）

**用户故事**：作为决策记录的读者，我要知道 canary 选型判据在 M 轮为何被放宽、在 N 轮为何收回，避免把一次性权宜当成新常态。

#### 验收标准

1. 🔴 WHEN 陈述 canary 判据 THEN SHALL 显式声明：**M 轮换判据（改用「结构最简 + BP 最少」替代「真库有业务载荷」）是 M 域特有情形的应对 —— M 真库 `checklist_responses` 仅 6 行且无一行业务载荷，硬标准分母为空；N 域分母非空，故本轮收回硬标准**。
2. WHEN 选定 canary THEN SHALL 同时满足四条 K/L 硬标准：① 真库存在非空业务载荷 ② 载荷键在 entry 内 ③ 该键非 `parent_duplicate` ④ 单 sheet 单键组。
3. WHEN 校验第 ① 条 THEN `N4-1-rows` 的 `remark` 现算 SHALL 为 **1665 B**，且内容首段 SHALL 含 `"rowKey":"row-消费税"`。
4. 🔴 WHEN 校验行身份质量 THEN `rowKey` 的值 SHALL 被判为**稳定语义键（税种名）而非位置索引** —— 故 canary 闭环 SHALL NOT 以「先改造行身份」为前置条件（与 K/L 轮 canary 需先改造相反）。
5. WHEN 校验第 ③ 条 THEN `N4-1-rows` SHALL NOT 出现在 slice 的 `parent_duplicate` 列表中（该列表 **4 条全挂 N1**，见 Requirement 14）。
6. WHEN 登记 canary 短板 THEN SHALL 写明两条：**① N4 的模式开关是 `host_inline_inert`，`onModeChange` 为空实现 ⇒ 闭环前须先修开关**；**② `N4-2` 的 `E9` 存在超列引用真缺陷（见 Requirement 15）**。
7. WHEN 记录排除理由 THEN SHALL 逐条写明：N1（593 公式格 + 4 条 parent_duplicate + 三值含 matrix + 直调 health 与 config 两端点 + 5 条生产边，最复杂）· N2（18 sheets / 710 公式格 / 7 键规模最大，真库 6 行**无业务载荷**）· N3（BP-9 + 宿主直调 health + A2 超列残留 11 处）· N5（BP-10 + BP-12 双重最重 + 兜底 id 缺失）。

### Requirement 6 — canary entry 的 BP 收口范围

**用户故事**：作为实施者，我要明确 N4 这一 entry 要闭合哪些 blocked_by，哪些属于全循环共有、哪些必须留给 lane spec。

#### 验收标准

1. WHEN 现算 N4 的 `blocked_by` THEN SHALL 恰为 **8** 项：1, 2, 3, **5**, 6, 7, 9, 11（其中 BP-5 为 N4/N5 共有）。
2. WHEN 校验全循环公共 BP THEN SHALL 恰为 **7** 项（1 / 2 / 3 / 6 / 7 / 9 / 11），五条 entry 无一例外。
3. WHEN 校验区分项 BP 的成员集 THEN SHALL 为 BP-4 = {N3}（1 条）· BP-5 = {N4, N5}（2 条）· BP-8 = {N1, N2, N5}（3 条）· BP-10 = {N1, N3}（2 条）· BP-12 = {N5}（1 条）。
4. WHEN 校验逐 entry BP 计数 THEN SHALL 为 N1 **9** / N2 **8** / N3 **9** / N4 **8** / N5 **10**。
5. 🔴 WHEN 处理 BP-1 / BP-2 / BP-3 THEN SHALL 标记为 `[ ]*`（全循环共有的平台级欠账：approved 权威模型与 contract/bundle · published 表示层 · 真 OnlyOffice 9.4 探针），SHALL NOT 在本 spec 内声称闭合。
6. WHEN 定义 BP-5 判据 THEN 判据正文 SHALL 在本 spec 裁定（因 canary 属该 BP），lane3 spec 仅以编号引用其 N5 侧成员。
7. WHEN 收口 BP-7 THEN `GtEntrySyncCapabilityNotice` 在 N 域现算 SHALL 为 **0** 命中（notice 生产消费方全域现算 **53**，N 域贡献 0）⇒ N 域须新接入，SHALL NOT 假设已有接线。

### Requirement 7 — 模板层只登记不修改

**用户故事**：作为审计业务负责人，我要确保 sync 改线不动 Excel 模板册本身，模板层缺陷走独立流程。

#### 验收标准

1. 🔴 WHEN 本 spec 的任何 task 执行 THEN SHALL NOT 修改 `backend/wp_templates/` 下任何 `.xlsx` 文件 —— 模板册 sha256 现算 **5/5 match**、size **5/5 match**，本 spec 交付后须仍然 match。
2. WHEN 发现模板层缺陷 THEN SHALL 以「登记 + 守卫锁定现状」处理：写入 `design.md` 缺陷台账，并加**记录型**测试断言其当前值，使未来修复时测试显式失败提醒同步更新。
3. 🔴 WHEN 登记缺陷 THEN SHALL 区分「真缺陷」与「合法形态」两类，并写明反向分母。本轮超列引用命中 17 = 真缺陷 **3**（族 A1）+ 结构残留 **11**（族 A2）+ 合法 **3**（族 B）。
4. WHEN 断言公式格总数 THEN SHALL 为 **2185**，口径 `data_only=False` 且 `isinstance(v, str) and len(v) > 1 and v.startswith('=')`；带公式 sheet SHALL 为 **49**。
5. 🔴 WHEN 执行 `data_only=True` 反证 THEN 公式格命中 SHALL 为 **0** —— slice 的 `formula_scan_policy` 明文要求此项，本轮已执行并通过，守卫 SHALL 保留该反证。
6. WHEN 归属公式格 THEN SHALL 满足 `236 + 755 + 1194 = 2185`（本 spec 236 · lane2 755 · lane3 1194），带 fx sheet `7 + 12 + 30 = 49`。

### Requirement 8 — 结构性零必须给出变异证明

**用户故事**：作为复盘者，我要能区分「扫描器写错导致 0」与「事实就是 0」，避免把假绿当成结论。

#### 验收标准

1. WHEN 断言某项为 0 THEN SHALL 同时提供**变异证明**：同一扫描器在非空场景（其他循环 / 本循环其他形态 / 故意造的反例串）上 SHALL 命中非零。
2. WHEN 登记本轮结构性零 THEN 清单 SHALL 为：`trial-balance/writeback` 生产 0 · `#REF!` 死公式 0 · 越界引用（按目标 sheet `max_row` 判）0 · dangling sheet 引用 0 · 合计漏加小计（严格双条件）0 · 倒挤减法链（严格口径）0 · `*EntryDualMode.ts` 0 · `useChecklistPersistence` 0 · `contract-ocr` 0 · `GtEntrySyncCapabilityNotice` 0 · `http.put` 0 · `api.put` 0 · `loose_only` 0 · M 式 `itemId: \`…row-${n}…\`` 0 · N4/N5 的 definedName 0 · 8 个 `nonexistent_guessed_keys` 各 0。
3. 🔴 WHEN 断言「M 式位置化 0」THEN SHALL 用 **M 轮同一扫描器**在 M 域跑出非零作为变异证明，而非仅在 N 域跑出 0（ND-8）。
4. 🔴 WHEN 断言「合计漏加小计 = 0」THEN SHALL 同时登记**粗口径误报 8 处**及其被判误报的现读依据（N1 两张附注披露的四段各自独立，且同一合计行内全列写法一致）—— 见 NC-17。
5. 🔴 WHEN 断言「倒挤减法链 = 0」THEN SHALL 同时登记**形态候选 32 处**及逐处业务正确性依据（`N5-8` H10~H38 表头明写 `⑦=②-①+③-④+⑥-⑤`；`N2-6 F39` 是「应纳税额 = 销项 − 进项 − 转出 − 减免 − 已交」正常业务）。
6. WHEN 某项分母为空 THEN SHALL 写「本轮空分母，判据保留待后续循环」，SHALL NOT 写「已验证无此问题」。

### Requirement 9 — strict 域口径与小写前缀陷阱

**用户故事**：作为扫描器作者，我要一个在 N 域真实成立的文件集判据，避免沿用 M 轮正则静默漏掉六分之一的文件。

#### 验收标准

1. WHEN 现算 strict 文件集 THEN 总数 SHALL 为 **160**，其中生产 **135** / 测试 **25**；生产数 SHALL 与 slice 的 `n_production_files_scanned` 等值。
2. 🔴 WHEN 使用 M 轮正则 `^(?:use|Gt)?N[1-5]` THEN SHALL 漏 **35** 个文件（生产 13 + 测试 22）—— 因 N 域存在小写 `n{1..5}` 前缀模块：`n1DisclosureConsistency` / `n1DisclosureSegmentTypes` / `n1LossMigration` / `n1NoteSectionMap` / `n2NoteSectionMap` / `n2SheetRouting` / `n2TaxLabelMap` / `n2VatSourceConstants` / `n4NoteSectionMap` / `n4SheetRouting` / `n4TaxTypes` / `n5NoteSectionMap` / `n5SheetRouting`（**13 个生产模块**）。
3. 🔴 WHEN 统计 orphan THEN SHALL 用含小写分支的正则 —— 否则 8 个 orphan 中的 `n1DisclosureSegmentTypes` 与 `n2VatSourceConstants` 会漏，orphan 数错报为 **6**。
4. 🔴 WHEN 处理 `nCycleTaxConsistency.ts` THEN SHALL 特别登记：该文件连 `^n[1-5]` 也不匹配（`nCycle` 开头）却引用 N 键 **10** 处 ⇒ 文件集判据 SHALL 按「目录段 + 文件名 + 内容引用」三路取并，SHALL NOT 仅靠文件名。
5. WHEN 现算 `loose_only` THEN SHALL 为 **0** —— N 的命名不与其他循环撞车，宽严两口径生产集等价。
6. WHEN 现算 orphan 归属 THEN SHALL 为 **8** 个 = 本 spec **3**（`useN4DualMode` / `useN4AdjudicationV2` / `useN4DetailV2`）+ lane2 **2**（`useN3DualMode` / `n1DisclosureSegmentTypes`）+ lane3 **3**（`useN5DualMode` / `useN5AiAssist` / `n2VatSourceConstants`）。
7. 🔴 WHEN 命名 orphan 守卫测试类 THEN SHALL 用 `TestOrphanInventory` 而非 M 轮的 `TestOrphanDualModeInventory` —— N 域 orphan **不止 dual-mode**（8 个 / 合计 **1331** 行，其中 5 个与 dual-mode 无关）。

### Requirement 10 — 行身份六族与 transport_key 解析

**用户故事**：作为双向回写的实现者，我要一份 N 域真实的行身份分布图，知道哪里有可抄的正面样板、哪里必须改造。

#### 验收标准

1. WHEN 分类行身份 THEN SHALL 得六族并各自给出现算值：A 持久化键 `${ITEM_PREFIX}-${index}` **3**（全在 `useN1Adjudication.ts`）· B 数组位置寻址 **67** / 24 文件 · C 展示序号 **7** / 6 文件 · D 熵键 **29** / 16 文件 · **E 稳定身份（`rowId`/`rowKey`/`id`）86 / 27 文件** · M 式 `row-${n}` 中缀 **0**。
2. 🔴 WHEN 比对 slice 声明 THEN SHALL 登记三处口径差：B 48 vs 67 · C 8 vs 7 · D 13 vs 29，并写明本轮口径扩项（B 含 `(rowIndex,` / `[index]` / `filter((r,i)=>i!==`）—— 口径差 SHALL NOT 被当作「slice 写错」。
3. 🔴 WHEN 登记 E 族 THEN SHALL 写明张力：**18 处正面样板位于将被删除的 orphan 内**（`useN4AdjudicationV2.ts` 9 + `useN4DetailV2.ts` 9）⇒ tasks SHALL 按「先抄形态、后删 orphan」排序，SHALL NOT 先删。
4. 🔴 WHEN 定义 `removeRow` 判据 THEN SHALL 承认 N 域两类并存：签名种类 **14** / 总命中 **32** / **by_index 18 : by_rowid 13 : other 1**。本 spec SHALL NOT 沿用 M 轮「零正面样板必须自建」的结论（M 为 50 : 0），而 SHALL 要求「把 18 处按索引的改造成已存在的 13 处形态」。
5. WHEN 现算 `transport_key` owner 常量 THEN SHALL 为 **6** 处并逐一吻合：`useN1FormData.ts` = `'N1-'` · **`useN1Adjudication.ts` = `'N1-1-adj'`** · `useN2FormData.ts` = `'N2-'` · `useN3FormData.ts` = `'N3-'` · `useN4FormData.ts` = `'N4-'` · `useN5FormData.ts` = `'N5-'`。🔴 N1 有**两个** owner 声明（`two_source_declarations` = 1）。
6. 🔴 WHEN 为 TK-2（`N1-1-adj-0` … `-6`）写守卫 THEN SHALL NOT 用「字面量至少 1 命中」—— 这 7 个展开键在源码中**一个都不存在**（运行时拼接），该判据恒假。守卫 SHALL 改为双条件：① 模板串 `'N1-1-adj'` 在 owner 模块命中 ② 展开数 == `N1_ADJUDICATION_CATEGORIES` 长度（**7**）。
7. WHEN 校验 `nonexistent_guessed_keys` THEN **8** 个键（`N1-1-rows` / `N1-1-adjudication-rows` / `N2-1-rows` / `N3-1-rows` / `N4-1-adjudication-rows` / `N5-1-rows` / `N5-5-rows` / `N4-1-rows-v3`）SHALL 各 **0** 命中；而 `N4-1-rows-v2` SHALL 命中 **1**（orphan `useN4AdjudicationV2.ts` 自身）⇒ 「伪造键形态」与「不存在的键」两类 SHALL NOT 混判。
8. WHEN 现算 `shared_adapter_absent` THEN `useChecklistPersistence` 命中 SHALL 为 **0** —— N 域无共享持久化适配层。

### Requirement 11 — 契约字段映射必须覆盖 `conclusion`（M/L 结论在 N 反转）

**用户故事**：作为契约设计者，我要确保 N 循环真实主载荷字段被纳入映射，避免照抄前两轮「只映 remark」导致 23 行数据不被识别。

#### 验收标准

1. 🔴 WHEN 现算真库 `checklist_responses` 中 `item_id ~ '^N[1-5]'` THEN SHALL 为 **30** 行，分布 N1 **17** / N2 6 / N3 2 / N4 **1** / N5 4；归属 SHALL 满足 `1 + 19 + 10 = 30`（本 spec 1 · lane2 19 · lane3 10）。
2. 🔴 WHEN 统计字段非空数 THEN **`conclusion` 非空 SHALL 为 23**（N1 14 / N2 4 / N3 2 / N4 0 / N5 3），而 `remark` 非空仅 **4** ⇒ **`conclusion` 是 N 域主载荷**。契约字段映射 SHALL 覆盖 `conclusion`，SHALL NOT 沿用 M/L 轮「`conclusion` 是死字段」的结论。
3. WHEN 列举 `conclusion` 载荷实例 THEN SHALL 含 `N1-disclosure-listed-unoffset`（1201 B）· `N1-disclosure-soe-unoffset`（1198 B）· `N1-disclosure-soe-netoffset`（1196 B）· `N1-disclosure-soe-synced-tables`（298 B）· `N1-5-rows`（363 B）—— 即**披露表数据存在 `conclusion` 而非 `remark`**。
4. 🔴 WHEN 统计 `remark` 非空 4 行 THEN SHALL 登记其中 **3 行是 AI 复核会话记录**（`N1-review-session-*` / `N2-review-session-*` / `N5-review-session-*`，各 **261 B**，与 M 轮 `M1-review-session-*` 同型同批次）⇒ 真业务载荷仅 **1** 行（`N4-1-rows`）。
5. WHEN 设计双向回写映射 THEN SHALL 对 `remark` 与 `conclusion` 两列都执行读写，且 SHALL 在 `design.md` 写明两列语义边界与冲突时的优先级。

### Requirement 12 — 跨循环引用与 G8 污染汇聚（平台级）

**用户故事**：作为平台维护者，我要知道 N 域既被外部引用、又引用外部，且真库存在跨 entry 落错宿主的污染，避免 sync 改线时把污染固化。

#### 验收标准

1. WHEN 现算 N 键被非 strict 生产文件引用 THEN SHALL 为：`composables/nCycleTaxConsistency.ts` **10** 处 · `shared/cycleImportExportRegistry.generated.ts` **6**（generated）· `sync/workpaperSyncManifest.generated.ts` **4**（generated）· `stories/business/ForceGraph.stories.ts` 3。
2. WHEN 现算 N5 引用外部命名空间（BP-12）THEN `useN5CrossSheet.ts` SHALL 恰为 **8** 个键、跨 **5** 个命名空间：`A-accounting-profit` · `A-profit-total` · `I2-1-audited-total` · `I6-1-audited-total` · `N1-1-total-audited` · `N1-1-total-begin` · `N3-1-change-total` · `N3-1-end-balance-total`；另 `N5TabDeferredReconcile.vue` 引 `N1-1` / `N3-1`。该判据正文归 lane3。
3. 🔴 WHEN 现算真库跨 entry 污染 THEN SHALL 为 **4** 条，全部落在 `wp_code = 'G8'`：`N1-3-entries` / `N2-3-entries` / `N3-3-entries` / `N5-3-entries`（四个不同 entry 的「调整分录汇总」键各一行）；归属 SHALL 为 lane2 **2** + lane3 **2**。
4. 🔴 WHEN 判定污染性质 THEN SHALL 写明与 L 轮 **LC-22 同一宿主**（L2 键亦落 G8）⇒ **G8 是跨循环污染汇聚点，属平台级问题**，N 侧规模 **4** 条大于 L 侧 1 条。本 spec SHALL 登记而非就地清理（清理需跨循环统一方案）。
5. 🔴 WHEN 评价 slice 的 `cross_entry_isolation` THEN SHALL 登记其局限：该检查**只扫代码不查库**，故连续两轮（L / N）漏掉真库污染 ⇒ 判据 SHALL 增加真库侧查询。
6. WHEN 冻结跨循环键 THEN 上述 8 个外部键与 4 条污染记录的现值 SHALL 被守卫锁定，变化时测试显式失败。
7. WHEN 记录真库全域基数 THEN `checklist_responses` 现算 SHALL 为 **1,034,702** 行 / **155** wp_code / `remark` 非空 **680**；N 底稿实例 SHALL 为 **40** 个 wp_code。

### Requirement 13 — 扫描口径差与误报必须登记

**用户故事**：作为后续循环的执行者，我要拿到本轮所有「口径不同导致数字不同」的清单，避免把口径差当成事实变化重新调查一遍。

#### 验收标准

1. WHEN 汇总口径差 THEN `design.md` SHALL 给出对照表，至少含：行身份 B（48→67）/ C（8→7）/ D（13→29）· 契约目录（slice 11 → 现算 **30**）· notice 消费方（slice 41 → 现算 **53**）· 配对数（slice 内部自相矛盾）· orphan 行数（plan 1325 → 现算 **1331**）· 超列引用（错口径 232 → 正确 **17**）。
2. 🔴 WHEN 登记超列引用误报 THEN SHALL 写明误报 **215** 处的根因：不剔除引号段时，sheet 名中的 `N2-1` 等被 `[A-Z]{1,3}\d+` 误当列引用 ⇒ 正确口径 SHALL 先剔 `'...'!` 段、中文 sheet 名 `!` 段与函数名。
3. 🔴 WHEN 登记契约目录口径差 THEN SHALL 写明 slice 的 `11` **严重过期**，现算 **30**（生产 28 + candidate 2），且 `adapter_id` 非空仍为 **5** ⇒ 比例 **28 : 5**。
4. 🔴 WHEN 处理配对数 THEN SHALL NOT 引用 slice 的任何硬编码值（`assertions/property_70` 写 11 份 55 对，`pairwise_recipe` 写 12 份 66 对，**slice 内部自相矛盾**）⇒ 守卫 SHALL 现算 `C(len(slices), 2)`。
5. WHEN 现算共享基类 statement 边 THEN SHALL 为 **26 生产 + 1 测试 = 27**，N 贡献 **1**（`useN2DualMode.ts`），移除后 after = **25**（该边归 lane3）。
6. WHEN 现算 `derived_total` 双正则 THEN TAIL（`-total` 结尾）SHALL 为 **28** / 11 文件，MID（`-total-` 中置）SHALL 为 **37** / 11 文件 ⇒ 🔴 **N 域两者相当（28 : 37）**，SHALL NOT 沿用 M 轮「单正则漏八成」的表述（M 为 9 : 35，L 为 5 : 3）。
7. WHEN 现算 `cycleSheetRouting` 采用方 THEN SHALL 为 **3**（`n2SheetRouting.ts` / `n4SheetRouting.ts` / `n5SheetRouting.ts`），与 slice 的 `hosts_using_shared_cycle_sheet_router: 3` 吻合；N1 / N3 未采用 ⇒ 构成 BP-10（归 lane2）。

### Requirement 14 — `parent_duplicate` 条件节在 N 首次触发

**用户故事**：作为守卫维护者，我要知道前三轮一直为空的 `parent_duplicate` 分支在 N 域首次有数据，必须真正实现而非保留空壳。

#### 验收标准

1. 🔴 WHEN 现算 slice 的 `parent_duplicate` THEN SHALL 为 **4** 条，**全部挂在 N1**：`xlsx/n1/calc/n1-tab-calc-table` · `xlsx/n1/core/n1-tab-adjudication` · `xlsx/n1/core/n1-tab-adjustment` · `xlsx/n1/core/n1-tab-detail`。
2. 🔴 WHEN 比对前三轮 THEN K / L / M 三轮该字段 SHALL 均为 **0** ⇒ N 是该条件节**首次触发**的循环，判据 SHALL 从「保留空分支」转为「实装并断言 4 条」。
3. WHEN 归属 THEN 4 条 SHALL 全归 lane2（N1 所在），本 spec 仅裁定判据正文（NC-31）。
4. WHEN canary 选型 THEN `N4-1-rows` SHALL NOT 属于该列表（Requirement 5 第 5 条的前提）。
5. WHEN 现算 `useN\dDualMode` 的 import 数 THEN SHALL 为 **4**，且 `http.put` / `api.put` 各 SHALL 为 **0**。

### Requirement 15 — wp_code 与 Excel A1 引用同形导致的静默失效（本轮首次发现）

**用户故事**：作为审计业务负责人，我要知道 N 循环的底稿编码与 Excel 单元格引用语法撞车，已造成三处公式静默吞掉一个分量，且这类缺陷不会被 Excel 报错。

#### 验收标准

1. 🔴 WHEN 现算「本表裸列引用超出 `max_column`」THEN 正确口径命中 SHALL 为 **17**，并 SHALL 分三族登记（族 A1 真缺陷 3 / 族 A2 结构残留 11 / 族 B 合法 3）。
2. 🔴 WHEN 登记族 A1 THEN SHALL 逐处写出反向分母：`N4/税金及附加明细表N4-2` **E9** `=B9+C9+N4`（正确形态 `=B#+C#+D#` 共 **9** 行，反向分母 **9 : 1**）· `N5/加计扣除研发费用情况明细表N5-6-1` **E12** `=C12+N5`（正确形态 **37** 行，**37 : 1**）· `N5/递延所得税费用核对表N5-8` **H12** `=C12-B12+N5-E12-F12+G12`（正确形态 **28** 行，表头 H9 明写 `⑦=②-①+③-④+⑥-⑤`，**28 : 1**）。
3. 🔴 WHEN 判定族 A1 根因 THEN SHALL 写明：三处**全是 `D` 列被替换为本册 wp_code**（`N4` / `N5`），两处在第 12 行、一处第 9 行，分布于三张不同 sheet、三个不同册 ⇒ 判为**系统性操作残留**而非单次手误；机理为 `N4` / `N5` 与 Excel A1 引用（列 N 第 4 / 5 行）**语法同形**，Excel 不报错、列 N 超出本表 `max_column`（11 / 7 / 10）⇒ 取值恒空、**静默吞掉第三个分量**，且 `N5-8` 的 r39 合计 `=SUM(H10:H38)` 连带错。
4. 🔴 WHEN 登记族 A2 THEN SHALL 写明其与 A1 **性质不同**：`N3/递延所得税负债明细表N3-2` H11~H21 **全 11 行同形** `=F#+O#`（行偏移 −8，列 O(15) > `max_column` 14），**无反向分母** ⇒ 不是「个别行写错」而是「整列一致但整列失效」（H 列恒等于 F 列），更像复制公式未调行号或 O 辅助列已被删 ⇒ 判据 SHALL 分两族，SHALL NOT 合并计数。
5. WHEN 登记族 B THEN SHALL 写明三处合法：`N3-2 E23 =SUM(E3:O22)` · `N4-2 D19 =SUM(D4:N18)` · `N5-6-1 D11 =SUM(D5:N16)` —— 矩形区间且 SUM 忽略空列 ⇒ 结果正确，仅为「原表曾有更多列」的痕迹。
6. WHEN 归属真缺陷 THEN SHALL 满足 `14 = 1（本 spec：N4-2 E9）+ 11（lane2：N3-2 H11~H21）+ 2（lane3：N5-6-1 E12 / N5-8 H12）`。
7. 🔴 WHEN 判定与 ND-7 的关系 THEN SHALL 写明**同源**：N 循环的 wp_code 命名空间与 Excel 引用语法冲突，既导致本项静默失效，也导致跨册 sheet 码碰撞（见 Requirement 18）。
8. WHEN 为本项写守卫 THEN SHALL 锁定「族 A1 = 3 且逐处位置与反向分母不变」，并 SHALL 附上错口径 232 的对照以防未来有人放宽正则。

### Requirement 16 — slice schema 校验器拒收诚实声明（平台级反向激励）

**用户故事**：作为 slice 维护者，我要修掉「如实登记缺陷反而通不过校验」的机制缺陷，否则所有后续循环都会被激励去隐藏缺陷。

#### 验收标准

1. 🔴 WHEN 审查 `validate_slice_against_schema` THEN SHALL 登记其缺陷：该校验器把 `forbidden_identity_kinds` 的**字面值**当作「非法声明」而拒收 ⇒ slice 越是如实点名违规形态、越通不过校验 ⇒ **反向激励藏缺陷**。
2. WHEN N slice 需要点名违规形态 THEN SHALL 使用 `violates_forbidden_identity_kind` 显式字段绕开该缺陷，并 SHALL 在 `design.md` 记录这是**权宜而非正解**。
3. WHEN 定位正解 THEN SHALL 写明：校验器应区分「声明了被禁形态的存在（合法登记）」与「使用了被禁形态（真违规）」两种语义，修复归平台层、不在本 spec 范围内 ⇒ 标 `[ ]*`。
4. WHEN 本 spec 交付 THEN SHALL NOT 为通过校验而删除任何诚实登记的缺陷声明。

### Requirement 17 — 历史 sheet、脏字面量与跨册码碰撞

**用户故事**：作为扫描器作者，我要一套能在 N 域真实成立的 sheet 名判据，避免「按 `审计程序表{code}` 提码」在六分之三的册上失配。

#### 验收标准

1. 🔴 WHEN 现算 sheet 名脏形态 THEN SHALL 为**三种**（slice 只记 2 种）：尾随空格 **1**（`'税金及附加审计程序表N4A '`）· 缺右括号 **1**（`'附注披露信息（国企'`，N5）· **「表的{码}」多字 3**（N1 `递延所得税资产审计程序表的N1A` / N1 `可用以后年度税前利润弥补的亏损检查表的N1-5` / N3 `递延所得税负债审计程序表的N3A`）。
2. 🔴 WHEN 统计审计程序表 THEN SHALL 为 **8 张 / 6 种形态**：`表的N1A` · `表N2A`（净）· `表O1A （原底稿）`（全角空格 + 全角括号）· `表的N3A` · `表N4A `（尾随空格）· `表O2A（原底稿）`（全角括号无空格）· `表N5A`（净）· `表N3A (原底稿)`（半角括号 + 前导空格）⇒ 仅 **2 张「净」**、6 张带脏 ⇒ 按 `审计程序表{code}` 提码 SHALL 在 N1 / N3 失配。
3. 🔴 WHEN 处理「原底稿」三张 THEN SHALL 写明**三种形态各不相同**（全角空格 + 全角括号 / 全角括号无空格 / 半角括号 + 前导空格）⇒ 与 M 轮 Q 表三种空格同型但更杂，判据 SHALL NOT 用单一分隔符假设。
4. 🔴 WHEN 处理跨册 sheet 码碰撞 THEN SHALL 登记 `N3A` 同时存在于 **N3 册与 N5 册** ⇒ 🔴 该项**横跨 lane2（N3 册）与 lane3（N5 册）**，两份 lane spec SHALL 交叉引用。
5. WHEN 处理外来字母码 THEN SHALL 登记 `O1A` 在 N2 册、`O2A` 在 N4 册 —— N 册内出现 **O** 开头码属跨册复制残留，判据 SHALL 容忍非本循环字母。
6. 🔴 WHEN 处理 sheet 名 THEN SHALL NOT 归一化（去空格 / 全半角转换 / 补括号）—— 归一化会使守卫无法发现真实脏数据，SHALL 按**原始字面量**比对。
7. WHEN 现算 hidden sheet THEN SHALL 为 **8** = `GT_Custom` **5** + 三张「原底稿」**3**；🔴 SHALL 登记 `出口退税额复核示例` 是 **visible** 的（`reference_example_sheet` 那一张可见）⇒ hidden 8 与 OO 兜底 12 存在口径差 **4**（未迁移程序表 3 + 参考示例 1 是 visible 但落 OO）⇒ 两套口径 SHALL 都声明。
8. WHEN 现算「合计 / 小计」标签 THEN SHALL 为 **34** 处 / **7** 种字面量（`'合计'` 15 · `'合  计'` 11 · `'小 计'` 3 · `'小计'` 2 · `'小  计'` 1 · `'合    计'` 1 · `'合 计'` 1）；🔴 SHALL 登记**非 A 列 1 处**（`N5/纳税调整明细表N5-5` r63 在 **B 列**）⇒ M 轮「限 A 列」口径在 N 会漏 1 处，判据 SHALL 改为「首个非空列」。
9. 🔴 WHEN 现算 `resolveProcedureSheetKey.ts` 的 N 段 THEN SHALL 为**已完备 5/5**（`N1→n1a` / `N2→n2a` / `N3→n3a` / `N4→n4a` / `N5→n5a`），文件头注释标 `N-tax-cycle N-F5 Task 2.5` ⇒ 🔁 **MC-28 在 N 反转为「无欠账」**；同时 SHALL 登记 **M 段仍只 6 条**（M 轮欠账未修，不因本轮而变）。N 为单位数码，无 M10 那类多位数顺序陷阱。

### Requirement 18 — 模板几何：超宽表、幽灵列与 footer 三形态

**用户故事**：作为双向回写的实现者，我要知道 N 域存在 250+ 空列的超宽 sheet，避免按 `max_column` 遍历时空转或超时。

#### 验收标准

1. 🔴 WHEN 现算超宽 sheet THEN SHALL 为 **2** 张（M 轮全域最宽 36 列，从未出现此形态）：`N1/附注披露信息（国企）` **256 列** × 74 行，`last_value_col` **7** ⇒ 幽灵 **249**；`N5/附注披露信息（国企` **255 列** × 32 行，`last_value_col` **4** ⇒ 幽灵 **251**。归属 SHALL 为 lane2 1（N1）+ lane3 1（N5）。
2. 🔴 WHEN 设计遍历策略 THEN SHALL NOT 按 `max_column` 全量遍历 —— 该形态是 Excel 旧版 256 列上限痕迹，全量遍历会扫 250+ 空列；SHALL 以 `last_value_col` 为界并在守卫中锁定两者差值。
3. WHEN 现算幽灵列总处数 THEN SHALL 为 **24** 处。
4. WHEN 现算幽灵行 Top THEN SHALL 为 `N5/调整分录汇总表N5-3` 12 · `N1/底稿目录` 11 · `N4/附注披露信息（国企）` 11 · `N2/调整分录汇总表N2-3` 10。
5. 🔴 WHEN 现算 footer THEN SHALL 为**三形态**（slice 未记）：`&P/&N` **49** · `None` **7** · **`&P&N` 3（缺斜杠）** = 59 ✓；缺斜杠三处恰为 `N2/出口退税额复核示例` + `N4/…O2A（原底稿）` + `N5/…N3A (原底稿)` ⇒ 🔴 **与 M 反向**（M 全域统一 `&P/&N`，该项空分母；N 分母非空）。归属 SHALL 为本 spec 1 + lane3 2。
6. WHEN 现算公式格 Top THEN SHALL 为 `N1-4 测算表` **227** · `N2-1 审定表` 198 · `N4-1 审定表` 136 · `N1-2 明细表` 134 · `N1-1 审定表` 128。
7. WHEN 现算裸 IF THEN SHALL 为 **244**，分布 `N1-4 测算表` **120** · `N2-1` 32 · `N1-1` 20 · `N4-1` 20 · `N3-1` 14 · `N2-7` 10 · `N2-10` 9 · `N5-5` 9 · `N5-1` 6 · `N5-6-2` 4（合计 244 ✓）。
8. 🔴 WHEN 现算 `definedName` THEN SHALL 为 total **72** / broken **45**，分布 N1 / N2 / N3 各 **24 / 15**，**N4 / N5 各 0 / 0** ⇒ 判据 SHALL NOT 假设每册都有 definedName（M 轮 10 册全有）。归属 SHALL 满足 `0 + 48 + 24 = 72` 与 `0 + 30 + 15 = 45`。
9. WHEN 登记 broken 形态 THEN SHALL 为三种：`#REF!` · `[1]Breakdown!#REF!`（外部工作簿，与 M 同源）· 🔴 **`'[2]2004'!#REF!`**（外部工作簿 `[2]` + sheet 名 `2004`，**M 轮未见的新形态**）；broken 名 SHALL 含 `XREF_COLUMN_1/2/3/5` · `XRefActiveRow` · `XRefCopy1/1Row/2Row` · `XRefPaste1/1Row/2/2Row/3/3Row` · 🔴 **`本循环科目`（中文名）**。
10. WHEN 现算变体轴 THEN SHALL 为 **4 : 1** —— N1 / N2 / N4 完整双版本（`附注披露信息（上市公司）` + `附注披露信息（国企）`）· N5 双版本但国企缺括号 · 🔴 **N3 完全无附注披露（n = 0）**，且 N3 亦是唯一无 disclosure 子组件、sheets 最少（6）、公式格最少（162）的 entry。

### Requirement 19 — prefill 分母非空，KC-17 在 N 重新适用

**用户故事**：作为实施者，我要知道 M / L 两轮判为空分母的 prefill 判据在 N 域有 76 处命中，必须重新纳入。

#### 验收标准

1. 🔴 WHEN 现算 `prefill` THEN CODE 命中 SHALL 为 **76** / **16** 文件（生产 13）、CMT 37 ⇒ 🔁 **KC-17 在 N 重新适用**（M 为 0、L 为 2）。
2. WHEN 现算 `onlyoffice/health` THEN CODE SHALL 为 **5** / 5 文件，与删除清册 `before: 5` 吻合。
3. 🔴 WHEN 现算 `onlyoffice-config` THEN CODE SHALL 为 **1**，位于 `useN1DualMode.ts` ⇒ 与 M（0）不同，**N1 直调 config 端点** ⇒ BP-4 类判据在 N 有两个触点（N3 直调 health、N1 直调 health + config）。
4. WHEN 现算 `contract-ocr` THEN SHALL 为 **0**（同 M，空分母）。
5. WHEN 现算 `useAdjustmentCentralSync` THEN SHALL 为 **15** 命中 / **5** 文件（每 entry 一处）。
6. WHEN 现算 localStorage 分区 THEN N1 的 `useN1DualMode.ts` 键 SHALL 为 `n1-dual-mode` 且按 wp 分区。

### Requirement 20 — 行数口径与上游计数错误如实登记

**用户故事**：作为复盘者，我要知道删除清册自身的行数计数有错，避免把上游错误值当基准写进守卫。

#### 验收标准

1. 🔴 WHEN 比对删除清册的 orphan 行数 THEN SHALL 登记两处错值：`useN4AdjudicationV2.ts` plan 记 **288** 而真值 **294** · `non_dual_mode` 合计 plan 记 **773** 而真值 **779**；plan 总计 **1325** 而真值 **1331**（🔴 slice 的 **1331** 是对的，plan 与 slice 不一致）。
2. 🔴 WHEN 编写守卫 THEN SHALL 以**现算值**为准并在注释写明上游差异，SHALL NOT 照抄 plan 的 288 / 773 / 1325。
3. WHEN 统一行数口径 THEN SHALL 用 `len(text.split("\n"))`，并在 `design.md` 写明与 slice / plan 的 `splitlines()` 口径差（末行无换行时相差 1）。
4. WHEN 断言 orphan 合计行数 THEN SHALL 为 **1331**，且 8 个文件逐一给出现算行数。
5. WHEN 现算 `transport_key` owner 文件行数 THEN SHALL 为 `useN1FormData.ts` 545 · `useN1Adjudication.ts` 507 · `useN2FormData.ts` 362 · `useN3FormData.ts` 379 · `useN4FormData.ts` 497 · `useN5FormData.ts` 406。
6. WHEN 现算 `resolveProcedureSheetKey.ts` 行数 THEN SHALL 为 **90**。
