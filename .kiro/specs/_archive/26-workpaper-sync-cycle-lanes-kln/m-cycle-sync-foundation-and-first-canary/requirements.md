# M 循环双向回写地基与首张 canary — 需求

## 引言

**上游**：umbrella Task 55 的 M slice（`backend/data/workpaper_sync_m_cycle_manifest_slice.json`，227,879 B，冻结 2026-08-31）+ 删除清册 `backend/data/workpaper_sync_m_cycle_deletion_plan.json`（93,321 B）+ 既存守卫 `backend/tests/workpaper_sync/test_task55_m_cycle_migration.py`（2752 行 / 14 测试类 / 152 test）+ 前八轮共同裁决 FC-1~13 / GC-1~10 / HC-1~16 / IC-1~20 / JC-1~20 / KC-1~24 / LC-1~26。

**本 spec 的 entry 范围**：`xlsx/gt-m6-retained-earnings`（**1 条**，canary 所在 entry 完整纳入，沿用 H/I/J/K/L 五轮既定形态）。

**承接策略**：以 **LC-1~26 为基准逐条重裁**。LC 已是 F/G/H/I/J/K 六轮的收口层，故 FC/GC/HC/IC/JC/KC 经 LC 间接覆盖，本 spec 不再逐轮展开。LC-x 在 M 的适用性判定见 `design.md` 的 MC-1 ~ MC-29 对照表；**五处不适用项（LC-11 / LC-12 / LC-19 / LC-20 / KC-17）必须显式声明，不得静默沿用**。

**既存守卫的边界**：`test_task55_m_cycle_migration.py` 锁的是「**现状诚实记录**」（capability 记 null + BP 齐备 + 计数可重算）。本 spec 锁的是「**改线后目标态**」。凡判据与既存守卫重叠，本 spec **引用既存测试名**而非重写。

🔴 **M 循环另有 4 份已归档 spec**（底稿功能方向，与本系列的 sync 方向正交，合计 190 task / 已完成 181）：

| 已归档 spec | 路径 | tasks |
|---|---|---|
| `workpaper-m-equity-cycle` | `.kiro/specs/_archive/02-workpaper-cycles/` | 28/28 |
| `m10-other-equity-instruments` | `.kiro/specs/_archive/05-business-features/` | 31/31 |
| `m-cycle-four-table-extraction-and-disclosure-alignment` | `.kiro/specs/_archive/08-disclosure-notes/` | **76/85**（9 条未做） |
| `m-cycle-workpapers` | `.kiro/specs/_archive/10-A~S-workpaper-all-cycles-complete/` | 46/46 |

其中第 2 份的**假绿遗留**是 BP-4（M10 两处）与 BP-12 的共同根因，必须在本系列修（见 Requirement 16）。

## 术语与口径（先立规矩，后面 Req 直接引用）

- **M 域文件集（strict）**：前端 `audit-platform/frontend/src/` 下，路径含 `m{1..10}/` 目录段，**或**文件名匹配 `^(?:use|Gt)?M(?:10|[1-9])(?![0-9])(?:[A-Z]|$|\.)` 的 `.ts`/`.vue`。🔴 **`M10` 的分支必须排在 `M1` 之前**且带 `(?![0-9])`，否则 `M1` 会吞掉 `M10`。
- **宽口径差集为空**：与 L 不同，M 域宽口径 `loose_only` 现算 **0** —— M 的命名不撞任何其他循环。🔴 抄 LC-5 的「撞 G 循环 Level-3」在 M 上**无对象**，须显式声明而非静默沿用。
- **行数口径**：统一 `len(text.split("\n"))`。🔴 M slice 与删除清册用的是 `splitlines()`（每文件少 1），比对时必须指明口径（见 Requirement 20）。
- **计数现算**：所有数字一律从源现算并与 `design.md` 等值比对。禁写死。
- **判据锚点**：用常量名 / 端点字面量 / 形态特征。🔴 **禁写死行号**（`.vue` 行号会漂）。
- **注释剥离**：判 `el-segmented` / 端点调用前必须先剥块注释、行注释、HTML 注释（同长空白替换以保留行号）。
- **按索引删 / 按行身份删**：`removeRow` 首参匹配 `^\$?(?:raw|global|display|table|original)?[Ii]dx?(?:ex)?(?::\s*number)?$` 家族判前者；含 `rowId` 判后者。
- **位置化行身份**：除 `rowKey:` / `rowId:` 赋值外，**`item_id` 模板串里的 `row-${n}` 段同样计入**；M slice 已纳入此口径（`44` 处），与 L 相反（见 MC-8）。
- **canary**：entry `xlsx/gt-m6-retained-earnings`，宿主 sheet = `审定表M6-1`，键组前缀 `M6-`。

## Requirement 1：entry 边界与 manifest 分歧（BP-9）

**User Story:** 作为迁移实施者，我需要 M 循环 10 条 entry 的边界与 manifest 的分歧被显式登记，这样我不会把组件级默认值当成能力裁决。

### 验收准则

1. WHEN 按 slice 的 `selection_rule` 从 manifest 现算 THEN 系统 SHALL 得到恰 **10** 条 entry，且与 slice 的 `independent_entries` 等值（多一条或少一条都红）。
2. WHEN 读 manifest 里这 10 条 entry THEN 系统 SHALL 断言其 `capability` 全为 `single_onlyoffice`、`html_store` 全为 `unresolved`、**且 manifest entry 上不存在 `capability_target` 字段**。
3. WHEN 读 slice 里同 10 条 THEN 系统 SHALL 断言 `capability` 全为 `null`、`capability_target` 全为 `bidirectional`、`adapter_id` 全为 `null`、`html_counterpart_verdict` 全为 `exists`。
4. WHEN 登记这一分歧 THEN 系统 SHALL 按 MC-1 的表述写明性质是「**overlay 的 `defaults_by_component.GtOnlyOfficeSheet` 默认值填充，不是逐 entry 裁决**」，🔴 **不得写成「数据冲突」或「manifest 错了」**；且 SHALL 断言守卫的方向是「**必须不一致且已登记 BP-9**」，不是断言两侧相等。
5. WHEN 断言 M0 册不存在 THEN 系统 SHALL 用两条现算证据而非沿用 L 的形态：① manifest 全量 entry 现算 `'m0' in entry_id.lower()` 命中 **0**；② `backend/wp_templates/_index.json` 里 `M/M0` 条目现算 **0**。🔴 L 的 L0 是「有条目但排除」，M 是「根本不存在」，两者判据不可互抄。
6. WHEN 断言 M 无 pilot THEN 系统 SHALL 现算逐文件读 `backend/data/workpaper_sync_contracts/*.json` 的 `review.entry_id`，得已迁移契约的 entry 归属集合，并断言**无一属 M**；同时 SHALL 声明该集合大小是现算值（禁写死），且它与 manifest 的 `adapter_id` 非空数**是两个不同分母**（「契约已发」≠「adapter 已注册」，manifest 无 `adapter_registered` 字段）。

## Requirement 2：MC-1 ~ MC-29 共同裁决只裁一次

**User Story:** 作为后续 lane 的实施者，我需要共同裁决有唯一出处，这样三份 spec 的判据不会各自漂移。

### 验收准则

1. WHEN 任一 lane spec 需要共同裁决 THEN 它 SHALL 只引用 `MC-x` 编号，**不得复述判据内容**。
2. WHEN 本 spec 落 MC-x THEN 每条 SHALL 带「与 LC-x 的关系」标注，取值限于 `✅ 适用` / `⚠️ 扩展` / `⚠️ 变形` / `⚠️ 换义` / `⚠️ 换向` / `⚠️ 换形` / `⚠️ 反转` / `⚠️ 恶化` / `M 独有` / `❌ 不适用`。
3. WHEN LC-11（`#REF!` 死公式）/ LC-12（footer 异常形态）/ LC-19（OCR 借 D4 端点）/ LC-20（倒挤减法链）/ KC-17（prefill sheet 名逐字一致）被评估 THEN 系统 SHALL 各自显式判 **❌ 不适用**，理由一律是「**M 侧分母为空**」（现算命中 0），并指明承载者保持既有测试原样。🔴 静默沿用即违规；写成「M 没有这个问题」也违规。
4. WHEN 复盘检查引用闭合性 THEN MC-1 ~ MC-29 SHALL 无缺号、无重号，且每条至少被一份 spec（含本 spec）引用。

## Requirement 3：写路径与发布门必须按端点字面量判定，且确认门在调用链上

**User Story:** 作为守卫作者，我需要写路径判定不依赖符号名、也不依赖「同文件有 confirm」，这样 10 条 entry 不会集体假红。

### 验收准则

1. WHEN 判 TB 发布门 THEN 系统 SHALL 按端点字面量 `audit-determination/publish-to-tb` 扫描，且 🔴 **必须能匹配反引号模板串**。
2. WHEN 统计命中 THEN 系统 SHALL 区分**代码行**与**注释行**（注释行以 `*` / `//` / `/*` 起），并断言代码命中恰 **10** 处（10 个 `useM{n}FormData` 各 1），注释命中为现算值。
3. WHEN 扫旧端点 `trial-balance/writeback` THEN 系统 SHALL 断言代码命中 **0**、命中总数为现算值且**全部为注释** ⇒ 铁律未违反。🔴 只数命中数不判注释即误立缺陷。
4. WHEN 判二次确认门 THEN 系统 SHALL 落「**调用链上有 `ElMessageBox.confirm`**」：现算 confirm 所在文件集与发布门所在文件集**交集为空**，故判据须验「`useM{n}Adjudication` → `useM{n}FormData` 的调用边存在且 Adjudication 侧有 confirm」。🔴 写成「同文件有 confirm」会让 10 条全假红。
5. WHEN 断言两个文件集的规模 THEN 系统 SHALL 现算并声明：发布门代码命中文件 **10** 个（全是 `useM{n}FormData`）、`ElMessageBox.confirm` 所在文件为现算值，两集合交集 **0**。

## Requirement 4：载体族是成对孪生，只有两种 kind

**User Story:** 作为守卫作者，我需要载体族判据按 M 的成对孪生形态写，这样 M9 不会因「找不到活载体」被误判、其余 9 条也不会因「有 orphan」被当成未接线。

### 验收准则

1. WHEN 现算 10 条 entry 的 `dual_mode_carrier.kind` THEN 系统 SHALL 得到**只两类**：`per_entry_wrapper_over_shared_base` **9** + `none` **1**（M9）。🔴 M 没有 L 的 `child_tab_dedicated_composable`、也没有 K/H 的宿主内联实现（现算 `const dualMode = (() =>` 命中各 **0**）。
2. WHEN 现算 dual-mode 模块总数 THEN 系统 SHALL 得到 **20 = entry 数 × 2**，且断言 orphan **11** ≠ live **9** —— 差额来自 **M9 的双孪生皆 orphan**（`entries_with_two_orphan_twins` 现算 1）。🔴 抄 L 的「orphan 与 live 数相等」会红。
3. WHEN 判 `switch_is_redeemable` THEN 系统 SHALL 断言 **`true` 9 + M9 为 `false`**，且断言 `inert` 数为 **0**、`entries_with_inert_switch` 为 **0**。🔴 抄 L 的 `switch_present_but_inert` verdict 会直接判错（见 MC-13）。
4. WHEN 判 9 条 redeemable THEN 系统 SHALL 要求**三条同时成立**：① 剥注释后宿主有 `el-segmented`；② 存在以 mode 为条件的 `v-if`/`v-else-if`；③ `v-else` 分支下真挂 `GtOnlyOfficeSheet`。
5. WHEN 判 M9 的 `none` THEN 系统 SHALL 验：宿主 `GtM9OtherComprehensiveIncome.vue` 连 `el-segmented` 都没有、`ui_toolbar_gate.anchor` 为 `null`（`entries_without_any_ui_gate_anchor` 现算 1），且其两个孪生模块生产边与测试边均为 **0**。
6. WHEN 现算共享基类的消费面 THEN 系统 SHALL 断言它是**会收缩**的：窄口径 statement 边现算值 → 扣除 M 路径 10 条后的剩余值。🔴 抄 L 的「删完不变」会红；本口径与删除清册的 `shared_base_consumers_before/after`（29 → 19）比对时须按 Requirement 20 声明行数/口径差异。
7. WHEN 现算 legacy health 端点直调点 THEN 系统 SHALL 断言删 orphan 后**降到 1 而不是 0**（共享基类里那一处不删），且 `onlyoffice-config` 命中恒 **0**。
8. WHEN 现算 barrel 与二阶 orphan THEN 系统 SHALL 断言 `components/workpaper/composables/index.ts` **不存在** ⇒ `orphan_barrel_reexports_to_drop` 与二阶 orphan 恒 **0**。

## Requirement 5：canary 选型判据偏离 K/L 口径，必须显式声明

**User Story:** 作为迁移实施者，我需要知道 M 的 canary 为什么不是按「真库有非空业务载荷」选的，这样我不会以为判据被偷换。

### 验收准则

1. WHEN 应用 K/L 两轮的 canary 硬标准「真库有非空业务载荷」THEN 系统 SHALL 现算证明它在 M 域**无解**：`checklist_responses` 里 `item_id ~ '^M\d'` 现算 **6** 行（M1 2 行 · M2/M6/M7/M9 各 1 行 · **M3/M4/M5/M8/M10 各 0 行**），`remark` 非空仅 **1** 行，而该行 `item_id = 'M1-review-session-20260725075149'`、内容是 **AI 复核会话记录**（`{"session_id": …}`）而非业务数据 ⇒ **合格者为空集**。
2. WHEN 判据被替换 THEN 本 spec SHALL 在 `design.md` 显式标注「**对 K/L 口径的偏离**」并给出五条替代判据的现算值：① `must_fix_before_wiring` 数为最少档；② SHEET_MAP 零错位且 declared 最少；③ `switch_is_redeemable == true`；④ 权威册公式格数最少；⑤ **存在可作正面样板的正确处理先例**。🔴 只写结论不写偏离即违规。
3. WHEN 现算判据 ① THEN 系统 SHALL 得到 M6 的 `must_fix_before_wiring` = BP-1 / BP-2 / BP-3 / BP-5 / BP-7 / BP-9 / BP-10 / BP-11 共 **8** 项（全为公共项，无任何区分项），并断言 M5 / M9 同为 8 项、M2 为最多档。
4. WHEN 现算判据 ② THEN 系统 SHALL 得到 M6 的 SHEET_MAP `declared / hit / missing` = **6 / 6 / 0**，且 declared 数是 10 条里最少的。
5. WHEN 现算判据 ④ THEN 系统 SHALL 用 openpyxl 现读 `M6 未分配利润` 册得公式格 **175**，并断言它是 10 册最少值。
6. WHEN 现算判据 ⑤ THEN 系统 SHALL 证明 M6 是 **3 张「修订前」Q 表里唯一被正确处理**的：宿主 dispatch 顺序里 `Q6A` + `修订前` 的判断**排在** `实质性程序表` 之前，返回专用 code `skip-q6a` 并渲染 `el-empty`；而 M8 无拦截、M10 写了拦截但排在后面（不可达死代码）⇒ 两者都被折叠到 `procedure`（见 Requirement 18）。
7. WHEN 排除其余候选 THEN 系统 SHALL 逐条给出现算理由：**M1** 含 BP-6 且其 `procedure` 声明为 `'应付股利实质性程序表M1'`（**10 册唯一不带 `A`** 的异类）且 item_id 属重复前缀型；**M5** 判据 ①②③ 同样干净但公式格 193 > 175 且无判据 ⑤；**M9** 载体 kind 为 `none` 且双孪生皆 orphan；**M3/M4/M5/M8/M10** 真库 0 行。
8. WHEN canary 闭环被排期 THEN 它 SHALL 标 `[ ]*`，理由是「真库 M6 唯一行 `M6-4-explanation` 的 `remark` 为 `NULL`，闭环须先造业务载荷」。🔴 不得标为已完成，也不得用 `M1-review-session-*` 那行冒充业务数据。

## Requirement 6：canary entry `xlsx/gt-m6-retained-earnings` 的 BP 收口

**User Story:** 作为实施者，我需要 M6 这条 entry 上的阻塞项被逐条归位，这样我知道哪些能做完、哪些卡外部供给。

### 验收准则

1. WHEN 处理 BP-1 / BP-2 / BP-3 THEN 本 spec SHALL 标 `[ ]*`（依赖外部供给：approved authority model + per-entry contract + non-null bundle / Task 36 published representation / 真实 OnlyOffice 9.4 探针），**不承诺完成**。
2. WHEN 处理 BP-5（orphan）THEN 系统 SHALL 现算 M6 的 orphan 孪生 = `components/workpaper/composables/useM6DualMode.ts`，断言它零生产边零测试边、是一阶 orphan、自带 `m6-dual-mode` 键（按 wpId 分区），并按删除清册可在 step 9 之前直接删。
3. WHEN 登记 `must_not_wire_to` THEN 系统 SHALL 断言该 orphan **内容完整**（`currentMode` / `modeOptions` / `switchMode` / `checkOOHealth` 全在）⇒ 改线时最易误接；判据 SHALL 验改线后宿主不再 import 它。
4. WHEN 处理 BP-7（notice）THEN 系统 SHALL 断言 M 域 notice 符号命中 **0**，锚点是宿主 `GtM6RetainedEarnings.vue` 的模式工具条（形态锚点，禁写行号），并按 MC-12 要求**常显摘要 + tooltip 细节**双落位。
5. WHEN 处理 BP-10（位置化）THEN 系统 SHALL 按 Requirement 11 收口，且 SHALL 采纳删除清册给出的修法：「内存里已有熵键，直接用它即可」。
6. WHEN 处理 BP-11（受保护公式）THEN 系统 SHALL 按 Requirement 17 收口，**只登记可复算事实，不为 M 造 contract、不猜 `formula_mask`**。
7. WHEN 处理 BP-9 THEN 系统 SHALL 按 Requirement 1 第 4 条登记，不重复裁决。
8. WHEN 现算 M6 的活封装 THEN 系统 SHALL 定位 `components/workpaper/composables/useM6EntryDualMode.ts`，断言它恰有 1 条生产边（宿主）、委托共享基类、是 `resolveOoSheetName` 的唯一实现方 ⇒ **不能在改线前删**（与 L5~L8 的 `can_delete_before_step_9: true` 相反）。

## Requirement 7：模板层登记（不修，只冻结基线）

**User Story:** 作为实施者，我需要模板层缺陷有基线，这样后续改动会被发现而不是静默漂移。

### 验收准则

1. WHEN 现读 `backend/wp_templates/M/` THEN 系统 SHALL 断言 **10** 册 / **102** sheets（无 M0），且 10 册的 sha256 与 `sheet_count` 与 slice 的 `template_ref` **10/10 等值**。
2. WHEN 现算 sheet 归属 THEN 系统 SHALL 断言 `102 = HTML 覆盖 89 + OO 兜底 13`，并按 MC-11 声明**两套口径**：slice 的 13 是按 dispatch 分的（GT_Custom 10 + 参考页 1 + 带「删除」1 + unmatched 1，`pre_revision_q` 计 0），而按 hidden 状态分是 **14**（GT_Custom 10 + 3 张 Q 表 + 带「删除」1）。🔴 混用两套口径必红。
3. WHEN 登记 sheet 名字符缺陷 THEN 系统 SHALL 断言 **10 册的实质性程序表 sheet 名全部含中间空格**，其中 M2/M3/M7 另有前导空格、M6/M7/M8 另有尾随空格（M7 是**前导+中间+尾随三重**），🔴 **禁归一化** —— 它们是 SHEET_MAP 比对的真实输入，BP-4 的 6 处丢空格正是 strip 造成的。
4. WHEN 登记参考页 THEN 系统 SHALL 断言它属 **M3** 册、sheet 名为 `参考－会计规定`（🔴 用**全角连字符 `－`**），落 OO 兜底是正确处置。
5. WHEN 登记带「删除」的 sheet THEN 系统 SHALL 断言它是 M8 的 `针对性测试M8-5-删除`，「删除」二字是**源模板作者的标注**，🔴 不得据此裁 single、也不得真删 sheet。
6. WHEN 登记 definedName 断链 THEN 系统 SHALL 现算 total / broken 并与 `design.md` 等值比对（🔴 **禁写死**，清理污染后会变），且断言分布形态：**M9 与 M1 显著高于其余 8 册、其余 8 册彼此相同**，并登记两种新形态：`{#N/A,…,"BBPREP"}`（打印区域宏残留）与 `[1]Breakdown!#REF!`（带外部工作簿引用）。
7. WHEN 登记 footer THEN 系统 SHALL 断言 M 全域统一为单个 `&P/&N`（无 L 的重复两次形态）⇒ **LC-12 在 M 空分母**，判据不宣称通过。
8. WHEN 登记幽灵行 THEN 系统 SHALL 用 `max_row − last_value_row` 现算并声明该口径（openpyxl 的 `max_row` 含无值但有格式的行），最大值出现在 M6 的 `调整分录汇总M6-3`。
9. WHEN 登记「合计 / 小计」标签 THEN 系统 SHALL 断言存在**中文分散对齐**写法（`合  计` / `合   计` / `小  计`，双空格与三空格并存），现算处数并声明它们**业务上正常**、但按标签文本精确匹配回写会失配。
10. WHEN 扫「小计」行标签 THEN 系统 SHALL **限定 A 列或首个非空列**；🔴 否则会把 M10 `明细表M10-2` 的 `R10='小计'`（两级表头的列名）当成小计行。
11. WHEN 本 Requirement 的任一计数被写入守卫 THEN 它 SHALL 现算比对，禁写死。

## Requirement 8：结构性零必须现算且带变异证明

**User Story:** 作为质控，我需要「某项为 0」不是漏扫的结果，这样守卫不会空跑通过。

### 验收准则

1. WHEN 断言结构性零 THEN 系统 SHALL 覆盖 **19** 项并逐项现算：M 前缀契约 0 · M 域 `adapter_id` 0 · `parent_duplicate` 0 · `excluded_pilot` 0 · `'m0'` 命中 0 · barrel 0 · 二阶 orphan 0 · `#REF!` 公式 0 · 越界引用 0 · dangling sheet 引用 0 · 倒挤减法链 0 · OCR 命中 0 · prefill 命中 0 · inert 开关 0 · notice 符号 0 · `onlyoffice-config` 0 · **按行身份删 0** · 真库 `conclusion` 非空 0 · M3/M4/M5/M8/M10 真库 0 行。
2. WHEN 每项零被断言 THEN 系统 SHALL 同时给出**非空分母**或显式标注「结构性零」；🔴 不得只写「为 0 故通过」。
3. WHEN 变异证明被要求 THEN 系统 SHALL 对至少「M 域 `adapter_id` 0」「barrel 0」「越界引用 0」「按行身份删 0」四项构造反例（人为注入后守卫必红），证明扫描非空跑。
4. WHEN 契约目录被现算 THEN 系统 SHALL 声明口径：目录下 `.json` 总数为现算值、生产口径需排除 `_` 前缀的 candidate 样例，且断言 **M 前缀契约恒 0**。🔴 总数禁写死。
5. WHEN 公式层四项零（`#REF!` / 越界 / dangling / 倒挤链）被断言 THEN 系统 SHALL 写明**分母是权威册全部公式格现算值**（数千级，非空分母），并写明「L 循环在这四项上分别有 8 / 0 / 0 / 6 处」⇒ 🔴 **抄 L 的这四条缺陷会在 M 上误立**。
6. WHEN 「按行身份删 0」被断言 THEN 系统 SHALL 写明分母是 `removeRow` / `handleRemove` 全部命中现算值，并写明 M 域**零正面样板**（L 有 3 个可抄模块）⇒ 去位置化改造在 M 必须**自建**样板。

## Requirement 9：空分母纪律

**User Story:** 作为质控，我需要「没有 contract 所以 Property 通过」这种重言式被显式拒绝。

### 验收准则

1. WHEN 某 Property 的 M 侧分母为空 THEN 系统 SHALL 在 `design.md` 的 Property 清单里标 `不宣称通过`，并指明承载该部分的既有测试文件。
2. WHEN 分母非空 THEN 系统 SHALL 写出分母的现算方式（扫什么、排除什么、得几个）。
3. WHEN LC-11 / LC-12 / LC-19 / LC-20 / KC-17 被判不适用 THEN 理由 SHALL 一律是「分母为空」而非「M 没有这个问题」。
4. WHEN slice 的 `property_denominators` 被引用 THEN 系统 SHALL 断言它显式区分真分母与空分母，且 M 侧多出 `property_24`（受保护公式，L 无此项）。

## Requirement 10：M 域文件集口径必须 strict，且 M10 优先于 M1

**User Story:** 作为守卫作者，我需要 M 域文件集的正则不把 M10 误判成 M1，这样所有比例类判据的分母是对的。

### 验收准则

1. WHEN 建立 M 域文件集 THEN 系统 SHALL 用 strict 口径（见术语节），现算文件数并与 `design.md` 等值比对。
2. WHEN 验正则正确性 THEN 系统 SHALL 构造反例自检：断言 `M10` 分支**不被** `M1` 分支吞掉（现算 `'M10-'.startswith('M1-')` 为 `False`，但**文件名**匹配必须靠 `M(?:10|[1-9])(?![0-9])` 顺序保证）。
3. WHEN 验宽口径差集 THEN 系统 SHALL 现算 `loose_only` 集合并断言其大小为 **0** ⇒ M 的命名不撞其他循环。🔴 本条是**反向断言**：LC-5 在 L 上的差集非空（G Level-3 / H2），在 M 上为空，必须显式声明而不是沿用 L 的表述。
4. WHEN 任何「按索引删 N 处」「位置化 N 处」类比例被写入 THEN 分母 SHALL 声明为 strict 口径。🔴 混用口径即判据失效。

## Requirement 11：item_id 层位置化行身份与双索引基准

**User Story:** 作为迁移实施者，我需要 BP-10 的范围覆盖 item_id 里的行序号段，并且知道真库存在 0-based 与 1-based 两种基准。

### 验收准则

1. WHEN 现算位置化行身份 THEN 系统 SHALL 用**四族**扫描口径并分别报数：① 渲染键（`rowKey:` / `rowId:` 赋值）；② **持久化键**（`itemId` 模板串里的 `row-${…}` 段）；③ 展示序号（`seq: idx + 1`）；④ 熵键（`${Date.now()}` / `${Math.random()}` 拼接）。
2. WHEN 报族 ② 的结果 THEN 系统 SHALL 断言它与 slice 的 `dynamic_row_identity` **一致**（M slice 已纳入 item_id 口径），并现算配套事实：命中文件数 = 10 个 `useM{n}Adjudication.ts` + `useM9OciReconcile.ts`，每个恰 **1** 处 `const n = idx + 1`。🔴 与 L 相反 —— L 的 slice 有此盲区、M 的 slice 没有，不得抄 L 的「slice 记漏」表述（见 MC-8）。
3. WHEN 报族 ④ 的结果 THEN 系统 SHALL 如实登记**口径差**：本 spec 正则较 slice 更宽，两个数不等，须写明「错误口径 → 正确口径 → 两个现算值」而非择一。
4. WHEN 登记「熵键假象」THEN 系统 SHALL 断言：内存里行身份是 `${Date.now()}-${Math.random()}` 形态（看似 opaque），但落库 `item_id` 是 `row-1 … row-N` **纯位置**⇒ 🔴 **只看内存会误判已达标**。
5. WHEN 登记索引基准 THEN 系统 SHALL 断言**两种基准并存**：代码侧 `const n = idx + 1` 是 1-based，而真库实证存在 **0-based** 行（`M7-disclosure-soe-row-0-policy`）⇒ 迁移映射必须**同时**处理两种基准，否则整表错位一行。🔴 该事实 slice 未记录，是真库实证。
6. WHEN 本 spec 收口 M6 的位置化 THEN 范围 SHALL 限于 M6 的族 ②（`useM6Adjudication.ts`）与族 ③；其余模块归 lane 2 / lane 3。

## Requirement 12：跨循环键冻结（M 是被引用方）

**User Story:** 作为实施者，我需要 M 键的下游消费者被冻结登记，这样改键不会静默打断 L6 与共享工厂。

### 验收准则

1. WHEN 现算 M 键的跨循环消费者 THEN 系统 SHALL 定位并断言四类生产文件（排除 `__tests__/`）：① `components/workpaper/composables/useL6Adjustment.ts`（**L6 → M**，1 处）；② `components/workpaper/composables/g2NoteSectionMap.ts`（1 处）；③ `components/workpaper/composables/factories/createChecklistFormData.ts`（共享工厂，3 处）；④ `components/workpaper/shared/cycleImportExportRegistry.generated.ts`（generated 注册表，10 处）。🔴 与 LC-23 **方向相反** —— L 是引用方（H2 ← L1），M 是**被引用方**。
2. WHEN 冻结基线 THEN 系统 SHALL 断言这些引用点在本 spec 内**不被改动**；若后续 lane 需改 M 键，SHALL 先在对应 spec 侧同步。
3. WHEN 登记 generated 文件 THEN 系统 SHALL 写明它是**生成物**，改键必须改生成器而非手改产物。
4. WHEN 登记已归档披露 spec 的未做守卫 THEN 系统 SHALL 断言其 tasks 里存在**未完成**的跨循环守卫「M1 推送的子表键与 K3 推送的键无交集」，并把它纳入本系列（归 lane 3 的 M1 分支），🔴 不得因「已归档 spec 标了 31/31 或 76/85」就认为已完成。
5. WHEN 断言 canary 安全性 THEN 系统 SHALL 现算确认上述四类消费者**均不引用 `M6-` 前缀键** ⇒ canary 改造与跨循环依赖正交。🔴 此断言必须现算，不得引用本文档结论。

## Requirement 13：五处扫描口径差与误报必须如实登记

**User Story:** 作为质控，我需要本轮自查出的口径差被写进文档，这样后续实施者不会照着误报去「修」不存在的缺陷。

### 验收准则

1. WHEN 登记口径差 THEN 系统 SHALL 覆盖 **5** 项并各自写明「错误口径 → 正确口径 → 两侧现算值」：① 熵键正则（本 spec 更宽 vs slice 更窄，两值不等）；② 共享基类消费边（窄口径 statement vs 宽口径 token，两值不等）；③ 行数（`split("\n")` vs `splitlines()`，每文件差 1）；④ 「小计」标签（不限列 vs 限 A 列，前者会把 M10 `明细表M10-2` 的 `R10` 表头当小计行）；⑤ OO 兜底分类（按 dispatch 13 vs 按 hidden 状态 14）。
2. WHEN 登记第 ③ 项 THEN 系统 SHALL 给出**可完全解释**的算式：orphan 侧 11 文件各差 1、live 侧 9 文件各差 1 ⇒ 两组总数差恰为 11 与 9。
3. WHEN 守卫实现这些判据 THEN 它 SHALL 对每项构造一个「用错误口径会红、用正确口径应绿」的自检用例，并在注释里写明两个口径各自的值。
4. WHEN 任一口径差被发现无法解释 THEN 系统 SHALL 判红而非取较大值或较小值。

## Requirement 14：`M{n}_SHEET_MAP` 11 对错位基线（MC-23）

**User Story:** 作为实施者，我需要 SHEET_MAP 的错位被逐对冻结，这样改线时不会把缺陷原样搬到 bridge 侧。

### 验收准则

1. WHEN 现算 SHEET_MAP 全量声明 THEN 系统 SHALL 得到 `declared 84 = hit 73 + missing 11`，并断言三个数与 slice、与删除清册的 `oo_sheet_map_defects_to_fix_not_delete.counters` **三方等值**。
2. WHEN 现算缺陷归属 THEN 系统 SHALL 断言 `entries_with_defects` = **6**、`defect_pairs_in_live_modules` = **9**、`defect_pairs_in_orphan_modules` = **2**（M9 的 2 处在 orphan 模块里，故 **BP-4 只登记 5 条 entry**）。🔴 「6 个 entry 有缺陷」与「5 条 entry 挂 BP-4」两个数都对，不可互相覆盖。
3. WHEN 分类三种错法 THEN 系统 SHALL 断言 `6 + 4 + 1 = 11`：① **丢空格 6**（去空格后能命中真 sheet ⇒ 纯空格问题）；② **名字整段不同 4**；③ **两张同码 sheet 被压成一个 1**。
4. WHEN 反向判据被要求 THEN 系统 SHALL 证明比对器**不是恒判不存在**：`procedure` 键的 10 条声明里现算 **hit 3 / miss 6 / 无此键 1**，且 10 条 fallback 字面量 `审定表M{n}-1` **全部命中**真 sheet（现算 10）。
5. WHEN 登记「无单一真源」的铁证 THEN 系统 SHALL 断言 `procedure` 键在 10 个模块里有 **4 种写法**：不带 `A`（M1）· 带中间空格（M5）· 带中间+尾随空格（M8）· 不带空格（6 条）· 以及**根本没有这个键**（M6）。
6. WHEN 登记危害为何长期不可见 THEN 系统 SHALL 写明：SHEET_MAP miss 时代码回落到 fallback 而 fallback 全部命中真 sheet ⇒ 用户看到的是**错的 tab 但不是空白**；且 AC 6.10 要求 fail closed，而现状 **零 fail closed**。
7. WHEN 本 spec 落 M6 侧基线 THEN 系统 SHALL 断言 M6 的 6 对**全部命中**、可原样迁移，并断言 M6 **没有 `procedure` 键** ⇒ 它靠 `skip-q6a` 专用分支而非 SHEET_MAP。其余 5 条含 BP-4 的 entry 归 lane 2。

## Requirement 15：历史 sheet 过滤两侧口径不一致（MC-24）

**User Story:** 作为实施者，我需要 HTML 侧与 OO 侧的 sheet 集合相等，否则 sheet_key 无法一一对应、双向回写从根上对不齐。

### 验收准则

1. WHEN 现算后端已有的历史 sheet 过滤 THEN 系统 SHALL 定位 `backend/app/services/wp_template_finder.py` 的 `_should_skip_historical_sheet`，并断言其规则集覆盖：含「修订前」/「（原）」/「(原)」· `G\d+` 配合「删除」或「移至」· 以 `-删除` 结尾 · 含「（示例）」或以「示例」结尾。
2. WHEN 对 M 的历史 sheet 验命中 THEN 系统 SHALL 断言 **4/4 命中**（3 张「修订前」Q 表 + `针对性测试M8-5-删除`）。
3. WHEN 反向判据被要求 THEN 系统 SHALL 断言正常 sheet **全部保留**，样本至少含 `审定表M6-1`、`明细表M10-2` 与一个带前导空格的程序表名。
4. WHEN 现算消费方 THEN 系统 SHALL 断言仅 **2** 处调用（`backend/app/routers/wp_onlyoffice_router.py` 与 `backend/app/services/wp_template_init_service.py`），且 🔴 **`backend/app/services/wp_render_config.py`（前端 sheet 列表主来源）无此过滤**。
5. WHEN 后果被登记 THEN 系统 SHALL 写明：HTML 侧看得到 3 张 Q 表、OO 侧看不到 ⇒ **两侧 sheet 集合不等** ⇒ 双向回写时 sheet_key 无法一一对应。🔴 这是 slice 未记录的新缺陷，且是 BP-8 在 HTML 侧可观察的原因。
6. WHEN 现算 fail-open 兜底 THEN 系统 SHALL 定位 `wp_onlyoffice_router.py` 里形如 `if not sheet_names: sheet_names = all_names` 的兜底（形态锚点，禁写行号），并断言它与 AC 6.10 的 fail-closed 要求**冲突**。
7. WHEN 修法被定义 THEN 系统 SHALL 要求**单一真源**：两侧共用同一个过滤函数，且过滤结果为空时 **fail closed**（报错而非回落全集）。🔴 本条是平台级修，不属任何单条 entry，收在 foundation。

## Requirement 16：已归档 spec 的假绿遗留必须登记并修正（MC-25）

**User Story:** 作为质控，我需要知道两份已归档 spec 的结论互相矛盾、且代码采纳了错的那份，这样同一个错名不会再被抄第三次。

### 验收准则

1. WHEN 现读 `_archive/05-business-features/m10-other-equity-instruments/requirements.md` THEN 系统 SHALL 断言其中把 sheet 名写成「附注披露信息（**国有企业**）」，而 openpyxl 现读权威册的真名是 **`附注披露信息核对（国企）`**（**双重差异**：少「核对」+「国有企业」vs「国企」）。
2. WHEN 现读 `_archive/08-disclosure-notes/m-cycle-four-table-extraction-and-disclosure-alignment/tasks.md` THEN 系统 SHALL 断言**另一份已归档 spec 记对了名**（明写「M10 sheet 名分叉：`附注披露信息核对（上市公司）`/`…核对（国企）` 与其余循环命名规则不同」）⇒ 🔴 **两份已归档 spec 结论不一致，代码采纳了错的那份**。
3. WHEN 现算传播路径 THEN 系统 SHALL 断言前端 `useM10EntryDualMode.ts` 的 SHEET_MAP 与宿主判断串**照抄了错名** ⇒ BP-4 的 M10 两处 + BP-12 全部同源。
4. WHEN 现读 `m10-other-equity-instruments/m10_conflict_resolution.md` THEN 系统 SHALL 断言其中写「Q10A 修订前 sheet 跳过 ✅ 通过」，而实测该跳过代码是**不可达死代码** ⇒ **验收结论是假绿**。
5. WHEN 登记该披露 spec 的未完成任务 THEN 系统 SHALL 现算其未勾项数并逐条列出（6 个 `m{n}NoteSubtableContract.spec.ts` + 复用 `useAgingConfig` 首档判「超过 1 年」+ `el-input-number` → `WpAmountInput` + **跨循环键无交集守卫**），🔴 计数现算禁写死。
6. WHEN 修正动作被定义 THEN 系统 SHALL 要求：① 前端 SHEET_MAP 改为 openpyxl 真名；② 在已归档 spec 的 requirements 里**不回填修改**（历史档案 append-only），而在本 spec 登记勘误；③ 加守卫「SHEET_MAP 的每个 value 必须在权威册 sheet 名集合里」防复发。
7. WHEN 本条被排期 THEN 修正动作 SHALL 归 lane 2（M10 属 lane 2 的 entry），foundation 只负责登记根因与勘误。

## Requirement 17：BP-11 受保护公式欠账（Property 24 / MC-26）

**User Story:** 作为实施者，我需要受保护公式的欠账被登记为可复算事实，而不是被猜出一份 contract。

### 验收准则

1. WHEN 现算权威册公式规模 THEN 系统 SHALL 得到公式格 **2937** / 带公式 sheet **81**，且与 slice 的 `protected_formula_and_classification_summary` 等值。
2. WHEN 现算前端把公式结果当普通字段写的处数 THEN 系统 SHALL 分两类报数：**公式重算列**与**分类/汇总派生值**，两个数均现算并与 `design.md` 等值比对。
3. WHEN 欠账被登记 THEN 系统 SHALL 遵守「**宁缺勿造**」：🔴 **不为 M 造 contract、不猜 `formula_mask` 的具体掩码**，只登记两个可复算事实 + 一条约束（发布 contract 时公式列必须落 `mode=formula` / `auto_source` + `formula_mask`，不得声明为 `editable`）。
4. WHEN Property 24 被引用 THEN 系统 SHALL 断言其 claim 为 `partial`、validates_requirement 为 `6.6`，并按 Requirement 9 说明哪部分分母为空。
5. WHEN M6 侧基线被冻结 THEN 系统 SHALL 现算 M6 册的公式格数（**175**，10 册最少）作为 canary 的公式负担基线。

## Requirement 18：3 张 Q 表三种待遇与 M6 正确先例抽取（MC-27）

**User Story:** 作为实施者，我需要知道同一类历史 sheet 在三个宿主里有三种待遇，并把唯一正确的那份抽成可复用样板。

### 验收准则

1. WHEN 现算 3 张 Q 表的宿主待遇 THEN 系统 SHALL 断言三种互不相同：**M6 正确**（`Q6A` + `修订前` 判断排在 `实质性程序表` 之前 ⇒ 返回专用 code `skip-q6a` ⇒ 渲染 `el-empty`）· **M8 无拦截**（`实质性程序表` 先命中 ⇒ 折叠到 `procedure`）· **M10 写了拦截但排在后面**（不可达死代码 ⇒ 折叠到 `procedure`）。
2. WHEN 现算 3 张 sheet 的真名形态 THEN 系统 SHALL 断言形态也不一致：M6 与 M8 的是 `…Q{n}A  (修订前)`（**双空格**）、M10 的是 `…Q10A (修订前)`（**单空格**）⇒ 🔴 按字面量比对必须逐张取真名，禁写统一模板。
3. WHEN 正面样板被抽取 THEN 系统 SHALL 把 M6 的「先判历史 sheet、再判业务 sheet」顺序固化为可复用判据，并要求 M8 / M10 按同一顺序修（归 lane 2 / lane 3）。
4. WHEN 与 Requirement 15 的关系被说明 THEN 系统 SHALL 写明：MC-24 的后端过滤是**根治**（两侧共用单一真源），本条的宿主顺序修是**前端侧补救**，两者不互相替代 —— 后端过滤生效后前端仍可能收到旧缓存的 sheet 列表。
5. WHEN Q 表被断言不是删除对象 THEN 系统 SHALL 引用删除清册的 `excluded_from_plan`：它们是权威模板里的 sheet，🔴 不是要删的前端文件。

## Requirement 19：`resolveProcedureSheetKey.ts` 的 M 段缺 4 条（MC-28）

**User Story:** 作为实施者，我需要已交付平台工具的 M 段被补齐，且补齐时不破坏其他循环。

### 验收准则

1. WHEN 现读 `audit-platform/frontend/src/utils/resolveProcedureSheetKey.ts` THEN 系统 SHALL 现算其行数与 M 段条数，断言 M 段现有 **6** 条（M2 / M4 / M5 / M6 / M9 / M10），🔴 **缺 M1 / M3 / M7 / M8**。
2. WHEN 补齐被执行 THEN 系统 SHALL 要求 **M10 的分支排在 M1 之前**（防 `startsWith` 误匹配），并在代码注释里写明该顺序约束 —— 现状 G 段有此注释、M 段**没有**。
3. WHEN 回归被保护 THEN 系统 SHALL 断言 4 个既存测试文件（`.spec.ts` / `.test.ts` / `.j-cycle.spec.ts` / `.m-cycle.spec.ts`）**全绿且不修改断言**，仅新增 M1/M3/M7/M8 的用例。
4. WHEN 补齐的 sheetKey 取值被确定 THEN 它 SHALL 与 openpyxl 真读的程序表 sheet 名对齐（含空格形态），而不是与 SHEET_MAP 的现有声明对齐。🔴 后者本身错 6 处。
5. WHEN 本条被排期 THEN 它 SHALL 归 foundation（平台工具是全循环共用，不属任何单条 entry）。

## Requirement 20：行数与计数口径差异必须声明（MC-29）

**User Story:** 作为守卫作者，我需要行数口径被写明，这样与 slice / 删除清册比对时不会整批假红。

### 验收准则

1. WHEN 任何行数被断言 THEN 系统 SHALL 声明所用口径，并在至少一个真实文件上现算证明 `split("\n")` 与 `splitlines()` 差 **1**。
2. WHEN 与 slice / 删除清册的行数计数比对 THEN 系统 SHALL 用 `splitlines()` 口径，或在等值断言里显式加上文件数的偏移量。🔴 直接比会红。
3. WHEN 偏移量被给出 THEN 系统 SHALL 用**可完全解释**的算式：orphan 侧 11 文件 ⇒ 偏移 11；live 侧 9 文件 ⇒ 偏移 9；共享基类单文件 ⇒ 偏移 1。
4. WHEN 计数类判据被写入守卫 THEN 它 SHALL 现算比对，禁写死；🔴 「N 处」的表述必须与紧随其后的列举项数**相等**。
