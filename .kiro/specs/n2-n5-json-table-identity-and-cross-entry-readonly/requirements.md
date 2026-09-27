# N2 / N5 整表 JSON 行身份与跨 entry 只读 — 需求

## 引言

**上游**：`n-cycle-sync-foundation-and-first-canary`（以下简称 **foundation**）已一次性裁定共同判据 **NC-1 ~ NC-37**，本 spec **只引用编号、不复述判据正文**。术语与口径一律沿用 foundation 的「术语与口径」节。

**本 spec 的 entry 范围**（**2** 条）：

| entry_id | wp_code | 科目 / 方向 | sheets | 公式格 | 带 fx | HTML child | prog | OO 兜底 | mount | 载体 kind | BP 数 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-n2-taxes-payable` | N2T | 2221 应交税费 / 贷 | **18**（全域最多） | **710**（全域最多） | 16 | 14 | 0 | 4 | 3 | `per_entry_wrapper_over_shared_base`（17 行薄封装） | **8** |
| `xlsx/gt-n5-income-tax-expense` | N5I | 6801 所得税费用 / 借 | 16 | 484 | 14 | 13 | 0 | 3 | 4 | `host_inline_inert`（与 N4 逐字同形） | **10**（全域最多） |

**切分主题**：整表 JSON 行表身份 + 跨 entry 只读引用。**BP-12（{N5}）完整内聚于本 spec**；BP-8（{N1, N2, N5}）与 BP-5（{N4, N5}）横跨，本 spec 只处理 N2 / N5 侧，判据正文分别在 foundation（BP-5）与 foundation 共同裁决（BP-8）。

🔴 **本 spec 与 lane2 的唯一交叉点**：sheet 码 `N3A` 同时存在于 **N5 册（本 spec，`…N3A (原底稿)`）与 N3 册（lane2，`递延所得税负债审计程序表的N3A`）**。任一侧单独修改会漏另一侧，两份 spec 须互相引用（见 Requirement 13）。

**Property 前缀**：本 spec 用 **NB-P**（foundation 用 NF-P，lane2 用 NA-P，三者不重号）。

## 需求

### Requirement 1 — entry 范围与归属算术

**用户故事**：作为维护者，我要确认本 spec 承担的份额与 foundation 算术自检表严格对齐。

#### 验收标准

1. WHEN 现算本 spec 归属 THEN SHALL 逐项吻合：sheets **34**（18 + 16）· 公式格 **1194**（710 + 484）· 带 fx **30**（16 + 14）· HTML child **27**（14 + 13）· prog console **0** · OO 兜底 **7**（4 + 3）· OO 挂点 **7**（3 + 4）。
2. 🔴 WHEN 比较规模 THEN 本 spec SHALL 为三份中最大：sheets 占 **34 / 59**、公式格占 **1194 / 2185**、带 fx sheet 占 **30 / 49** ⇒ 均过半。
3. WHEN 现算 orphan 归属 THEN SHALL 为 **3** 个：`useN5DualMode.ts` · `useN5AiAssist.ts` · `n2VatSourceConstants.ts`；🔴 后者是**小写 `n{1..5}` 前缀模块**，用 M 轮正则会漏（依 NC-5）。
4. WHEN 现算 live dual-mode 归属 THEN SHALL 为 **1** 个（`useN2DualMode.ts`）；宿主内联载体归属 SHALL 为 **1**（N5）。
5. WHEN 现算真库归属 THEN SHALL 为 **10** 行（N2 **6** + N5 **4**）。
6. 🔴 WHEN 现算 `definedName` 归属 THEN total SHALL 为 **24**（N2 24 + **N5 0**）· broken SHALL 为 **15**（15 + **0**）⇒ **N5 完全没有 definedName**，判据 SHALL NOT 假设每册都有（依 NC-9）。
7. WHEN 现算超列真缺陷归属 THEN SHALL 为 **2** 处，均属**族 A1**（`N5-6-1` E12 · `N5-8` H12），本 spec 无族 A2。
8. WHEN 现算其余归属 THEN 跨 entry 污染 **2** 条（`N2-3-entries` · `N5-3-entries`）· footer 缺斜杠 **2**（全域 3 中的 2）· 超宽 256 列表 **1**（`N5/附注披露信息（国企`）。

### Requirement 2 — BP-12 收口：N5 跨 entry 只读引用

**用户故事**：作为架构维护者，我要把 N5 对其他 entry 数据的引用固化为显式只读契约，避免跨 entry 写入。

#### 验收标准

1. WHEN 现算 `useN5CrossSheet.ts` 的外部键 THEN SHALL 恰为 **8** 个，跨 **5** 个命名空间：`A-accounting-profit` · `A-profit-total` · `I2-1-audited-total` · `I6-1-audited-total` · `N1-1-total-audited` · `N1-1-total-begin` · `N3-1-change-total` · `N3-1-end-balance-total`（依 NC-19）。
2. WHEN 现算其他引用点 THEN `N5TabDeferredReconcile.vue` SHALL 引用 `N1-1` / `N3-1`。
3. 🔴 WHEN 定义契约 THEN 这 8 个键 SHALL 全部为**只读**：SHALL NOT 出现任何指向 A / I2 / I6 / N1 / N3 命名空间的写入路径。
4. WHEN 现算 N5 键总数 THEN SHALL 为 **10** 个（含 **5** 个 cross 键），是全域键最多的 entry；N2 SHALL 为 **7** 键。
5. WHEN 冻结跨循环键 THEN 8 个键的现值 SHALL 被守卫锁定，新增或删除时测试显式失败。
6. WHEN 收口完成 THEN BP-12 成员集 SHALL 变为空集。
7. 🔴 WHEN 处理引用方向 THEN SHALL 同时登记 N 域**被外部引用**的一侧（`nCycleTaxConsistency.ts` 10 处 · `cycleImportExportRegistry.generated.ts` 6 · `workpaperSyncManifest.generated.ts` 4 · `ForceGraph.stories.ts` 3）—— 双向都要，SHALL NOT 只看单向（依 NC-19）。

### Requirement 3 — BP-8 收口：N2 / N5 整表 JSON 行身份

**用户故事**：作为双向回写的实现者，我要把 N2 / N5 的整表 JSON 行表改成稳定行身份，避免行序变动导致数据错位。

#### 验收标准

1. WHEN 现算 BP-8 成员 THEN SHALL 为 {N1, N2, N5}，本 spec 承担 **N2 / N5** 两侧（N1 侧归 lane2）。
2. 🔴 WHEN 改造行身份 THEN SHALL 抄 E 族既有正面形态（全域 **86** 处 / 27 文件），SHALL NOT 自建新范式（依 NC-6 的反转裁定）。
3. 🔴 WHEN 取用样板 THEN SHALL 在 foundation 任务 14（E 族样板提取）**之后**执行 —— 18 处样板原位于 foundation 归属的 orphan 内，先删后抄会丢样板。
4. WHEN 改造 `removeRow` THEN SHALL 把本 spec 范围内的 by_index 调用改为 by_rowid 形态（全域 18 : 13），守卫按单调方向断言（依 NC-7）。
5. WHEN 校验不存在的键 THEN `N2-1-rows` · `N5-1-rows` · `N5-5-rows` SHALL 各 **0** 命中（依 NC-30 的反向分母纪律）。
6. WHEN 现算 owner 常量 THEN N2 SHALL 为 `useN2FormData.ts`（362 行）= `'N2-'`、N5 SHALL 为 `useN5FormData.ts`（406 行）= `'N5-'`，两者均为单一声明（`two_source_declarations` 仅 N1 有）。

### Requirement 4 — BP-5 收口：N5 的 inert 开关（判据在 foundation）

**用户故事**：作为实施者，我要修掉 N5 的空实现模式开关，它与 canary N4 逐字同形，判据已在 foundation 裁定。

#### 验收标准

1. WHEN 现读 N5 宿主 THEN SHALL 确认 `host_inline_inert` 形态：`const dualMode = { ... currentMode: ref<...>('html') ... onModeChange: () => {} }`，门控 `v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"`。
2. 🔴 WHEN 比对 N4 THEN SHALL 确认两者**逐字同形** ⇒ BP-5 判据正文由 foundation 定义（canary 所在），本 spec 仅引用编号并在 N5 侧执行同一改造。
3. WHEN 现算 `modeOptions` THEN SHALL 确认其为**普通数组不带 `.value`**（与 N1 / N3 的 ref 形态不同）。
4. WHEN 改造完成 THEN N5 的 switch SHALL 从 `inert` 变 `redeemable`，BP-5 成员集 SHALL 变为空集，且 foundation 与本 spec 的事实基线表 SHALL 同步更新。
5. 🔴 WHEN 编排顺序 THEN 本任务 SHALL 在 foundation 任务 13（N4 inert 修复）**之后**执行，复用其已验证的改造形态，SHALL NOT 并行各自发明。

### Requirement 5 — N2 薄封装载体与共享基类边

**用户故事**：作为架构维护者，我要知道 N2 是唯一走共享基类的 entry，改造它会影响共享基类的引用计数。

#### 验收标准

1. WHEN 现读 `useN2DualMode.ts` THEN SHALL 确认其为 **17 行**薄封装、kind = `per_entry_wrapper_over_shared_base`、**无 localStorage 键**、生产边 **1** 条。
2. WHEN 现算门控 THEN SHALL 为 `v-if="isHtmlSheet && renderMode === 'onlyoffice'"`，且 `mode.value` 赋值处为 **0**（赋值逻辑在共享基类内）。
3. 🔴 WHEN 现算共享基类 statement 边 THEN SHALL 为 **26 生产 + 1 测试 = 27**，N 域贡献 **1**（`useN2DualMode.ts`）；移除该边后 after SHALL 为 **25**（依 NC-11 的口径差登记）。
4. WHEN 改造 N2 THEN SHALL 评估是否移除该薄封装；若移除，SHALL 在守卫中断言共享基类生产边从 26 降至 25，SHALL NOT 留下悬空计数。
5. WHEN 现算共享路由采纳 THEN N2 SHALL 已采用 `n2SheetRouting.ts`（属 `hosts_using_shared_cycle_sheet_router: 3` 之一）⇒ N2 / N5 **不在 BP-10 内**，该项对本 spec 空分母（依 NC-19）。

### Requirement 6 — N5 缺少 Adjudication composable 的异形

**用户故事**：作为守卫作者，我要让确认门判据容忍 N5 的结构异形，避免写出必假红的断言。

#### 验收标准

1. 🔴 WHEN 现算 Adjudication composable THEN `useN{1..4}Adjudication.ts` SHALL 存在而 **`useN5Adjudication.ts` 不存在** ⇒ N5 的 `ElMessageBox.confirm` 落在 **`N5TabAdjudication.vue`**（依 NC-4）。
2. WHEN 编写确认门判据 THEN SHALL 按「每 entry 至少一处 confirm」断言，SHALL NOT 按「每 entry 有同名 composable」断言。
3. WHEN 现算确认门与发布门关系 THEN 交集 SHALL 为 **0**（全域 confirm 26 / 17 文件；发布门 5 文件）⇒ 分居不同模块，SHALL NOT 断言同文件相邻。
4. WHEN 现算发布门 THEN 本 spec 范围内 SHALL 为 **2** 处（`useN2FormData.ts` · `useN5FormData.ts`），且 SHALL NOT 新增第 3 处（依 NC-3）。

### Requirement 7 — 契约字段：N2 / N5 载荷亦在 `conclusion`

**用户故事**：作为契约实现者，我要确保 N2 / N5 的载荷被正确读写，它们同样不在 `remark` 而在 `conclusion`。

#### 验收标准

1. 🔴 WHEN 现算本 spec 真库载荷 THEN `conclusion` 非空 SHALL 为 N2 **4** + N5 **3** = **7**，而 `remark` 非空 SHALL 为 N2 **1** + N5 **1** = **2**，且这 **2 行全部是 AI 复核会话**（`N2-review-session-*` / `N5-review-session-*`，各 **261 B**）⇒ 本 spec 范围内**真业务载荷 100% 在 `conclusion`**（依 NC-34）。
2. WHEN 处理 `*-review-session-*` THEN SHALL 按白名单排除，SHALL NOT 当业务载荷解析 —— 🔴 本 spec 的 `remark` 非空行**全是**该类型，若不排除会把 AI 会话当行表解析。
3. WHEN 按后缀判优先级 THEN SHALL 采「实际非空列优先于后缀规则」（与 lane2 同一裁定），避免按规则去空列取值而静默丢数据。
4. WHEN 现算变体轴 THEN N2 SHALL 为完整双版本（`附注披露信息（上市公司）` + `附注披露信息（国企）`）· 🔴 N5 SHALL 为**双版本但国企缺右括号**（`附注披露信息（国企`）⇒ 披露表读写须按原始 sheet 名匹配，禁补括号归一化（依 NC-10 · NC-26）。

### Requirement 8 — 真库跨 entry 污染 2 条登记

**用户故事**：作为平台维护者，我要登记本 spec 范围内落错宿主的两行数据。

#### 验收标准

1. 🔴 WHEN 现算本 spec 污染 THEN SHALL 为 **2** 条：`N2-3-entries` 与 `N5-3-entries`，两者 `wp_code` 均为 **`G8`**（依 NC-19）。
2. WHEN 判定性质 THEN SHALL 引用 NC-19 的裁定：G8 是跨循环污染汇聚点（与 L 轮 LC-22 同宿主），属平台级 ⇒ **登记 + 守卫锁定现值**，SHALL NOT 就地清理。
3. WHEN 实现 `-3-entries`（调整分录汇总）的双向回写 THEN SHALL 以 entry 自身 `wp_code` 为写入目标，SHALL NOT 沿用被污染行的 `wp_code`。
4. WHEN 查询真库 THEN SHALL 用 asyncpg（🔴 `psycopg2` 未安装），每条查询独立连接；无库环境 skip 并标原因，SHALL NOT 静默 pass。

### Requirement 9 — 模板层缺陷登记（族 A1 两处 · footer · 脏字面量）

**用户故事**：作为审计业务负责人，我要知道 N5 有两处公式静默吞掉一个分量、且其中一处连带使合计行出错。

#### 验收标准

1. 🔴 WHEN 现算族 A1 THEN 本 spec SHALL 有 **2** 处真缺陷，逐处含反向分母：
   - `N5/加计扣除研发费用情况明细表N5-6-1` **E12** `=C12+`**`N5`**（正确形态 `=C#+D#` 共 **37** 行 ⇒ **37 : 1**）
   - `N5/递延所得税费用核对表N5-8` **H12** `=C12-B12+`**`N5`**`-E12-F12+G12`（正确形态 **28** 行，表头 H9 明写 `⑦=②-①+③-④+⑥-⑤` ⇒ **28 : 1**）
2. 🔴 WHEN 登记 `N5-8` 的连带影响 THEN SHALL 写明其 **r39 合计 `=SUM(H10:H38)` 因 H12 恒空而连带错** —— 单元格级缺陷已扩散到合计层。
3. WHEN 判定根因 THEN SHALL 引用 NC-32：`N5` 与 Excel A1 引用（列 N 第 5 行）**语法同形**，Excel 不报错、列 N 超出本表 `max_column`（7 / 10）⇒ 取值恒空、静默吞掉第三个分量。
4. WHEN 处理族 B THEN `N5-6-1 D11 =SUM(D5:N16)` SHALL 判为**合法**（矩形区间，SUM 忽略空列）。
5. 🔴 WHEN 现算 footer 缺斜杠 THEN 本 spec SHALL 有 **2** 处（全域 3 中的 2）：`N2/出口退税额复核示例` · `N5/…N3A (原底稿)`，形态为 `&P&N`（缺斜杠）而非 `&P/&N`（依 NC-36）。
6. WHEN 现算脏字面量 THEN 本 spec SHALL 有 **1** 处缺右括号（`附注披露信息（国企`，N5）；外来字母码 SHALL 有 **1** 处（`O1A`，N2 册，依 NC-21）。
7. 🔴 WHEN 本 spec 任何任务执行 THEN SHALL NOT 修改 `.xlsx` —— 模板 sha256 交付后须仍 5/5 match（依 NC-25）。缺陷以**记录型**测试锁定现状。
8. WHEN 现算 `出口退税额复核示例` 的可见性 THEN SHALL 确认它是 **visible** 的（`reference_example_sheet` 那一张可见）⇒ hidden 8 与 OO 兜底 12 的口径差 4 中有 1 来自此处（依 NC-24）。

### Requirement 10 — 超宽表 N5 与「合计」标签非 A 列

**用户故事**：作为双向回写的实现者，我要避免在 251 个空列上空转，也要避免漏掉不在 A 列的合计行。

#### 验收标准

1. 🔴 WHEN 现算 `N5/附注披露信息（国企` THEN SHALL 为 **255 列 × 32 行**，`last_value_col` = **4** ⇒ 幽灵 **251** 列（依 NC-35）。
2. WHEN 遍历该 sheet THEN 上界 SHALL 取 `last_value_col` 而非 `max_column`；守卫 SHALL 锁定差值 251，变化时显式失败。
3. 🔴 WHEN 定位「合计 / 小计」标签 THEN SHALL 用「**首个非空列**」而非限 A 列 —— `N5/纳税调整明细表N5-5` **r63 的标签在 B 列**，是全域 34 处标签中唯一非 A 列的一处；M 轮「限 A 列」口径在此会漏（依 NC-17）。
4. WHEN 现算标签字面量 THEN 全域 SHALL 为 **7** 种（`'合计'` 15 · `'合  计'` 11 · `'小 计'` 3 · `'小计'` 2 · `'小  计'` 1 · `'合    计'` 1 · `'合 计'` 1，共 34），判据 SHALL 按原始字面量集合匹配，SHALL NOT 去空格归一化。
5. WHEN 现算本 spec 幽灵行 Top THEN SHALL 含 `N5/调整分录汇总表N5-3` **12** · `N2/调整分录汇总表N2-3` **10**。
6. WHEN 现算本 spec 公式格与裸 IF Top THEN SHALL 含 `N2-1 审定表` 公式格 **198** / 裸 IF **32**，以及 `N2-7` 10 · `N2-10` 9 · `N5-5` 9 · `N5-1` 6 · `N5-6-2` 4。
7. WHEN 现算倒挤形态候选 THEN 本 spec SHALL 含 `N5-8 H10~H38`（**29** 行同构核对公式）· `N2-6 F39 =F35-F36-F37-F38-C18`（应纳税额 = 销项 − 进项 − 转出 − 减免 − 已交）· `N5-1 B8` / `F8`（跨表减法）⇒ 全部**形态命中但业务正确**，严格口径命中 SHALL 为 **0**（依 NC-20 的候选 32 登记）。

### Requirement 11 — `definedName` 在 N5 为零的口径声明

**用户故事**：作为守卫作者，我要让 definedName 判据容忍「整册没有 definedName」的情形。

#### 验收标准

1. 🔴 WHEN 现算 `definedName` THEN N2 SHALL 为 total **24** / broken **15**，**N5 SHALL 为 0 / 0** ⇒ 判据 SHALL NOT 假设每册都有（M 轮 10 册全有，依 NC-9）。
2. WHEN 对 N5 声明 THEN SHALL 写「N5 本项空分母」，SHALL NOT 写「已验证 N5 无断链」（依 NC-20）。
3. WHEN 登记 N2 的 broken 形态 THEN SHALL 含 `#REF!` · `[1]Breakdown!#REF!` · 🔴 `'[2]2004'!#REF!`（M 轮未见的新形态，外部工作簿 `[2]` + sheet 名 `2004`）· 🔴 中文名 `本循环科目`。
4. WHEN 登记 broken 名清单 THEN SHALL 含 `XREF_COLUMN_1/2/3/5` · `XRefActiveRow` · `XRefCopy1/1Row/2Row` · `XRefPaste1/1Row/2/2Row/3/3Row`。

### Requirement 12 — orphan 3 个删除（先抄后删）

**用户故事**：作为维护者，我要清掉本 spec 范围内的三个无引用模块，但不能在提取样板前删。

#### 验收标准

1. WHEN 现算本 spec orphan THEN SHALL 为 **3** 个：`useN5DualMode.ts` · `useN5AiAssist.ts` · `n2VatSourceConstants.ts`。
2. 🔴 WHEN 统计 orphan THEN SHALL 用含小写分支的正则 —— 否则 `n2VatSourceConstants.ts` 会漏、本 spec orphan 数会错报为 2（依 NC-5）。
3. 🔴 WHEN 判定 orphan 性质 THEN SHALL 注意本 spec 的 3 个中**只有 1 个与 dual-mode 有关**（`useN5DualMode.ts`）⇒ 守卫类名沿用 foundation 的 `TestOrphanInventory`，SHALL NOT 用 M 轮的 `TestOrphanDualModeInventory`。
4. WHEN 删除前 THEN SHALL grep 确认 0 生产引用，且 SHALL 在 foundation 任务 14（形态提取）之后执行。
5. WHEN 断言 orphan 行数 THEN SHALL 用现算值，SHALL NOT 照抄删除清册（plan 的 orphan 行数计数本身有错，依 NC-29）。

### Requirement 13 — 与 lane2 的交叉引用（`N3A` 跨册碰撞）

**用户故事**：作为两份 lane spec 的读者，我要知道有一处缺陷横跨两份 spec，任一侧单独处理都不完整。

#### 验收标准

1. 🔴 WHEN 现算 sheet 码 `N3A` THEN SHALL 确认它同时存在于 **N5 册（本 spec，`…N3A (原底稿)`，半角括号 + 前导空格）与 N3 册（lane2，`递延所得税负债审计程序表的N3A`）**。
2. WHEN 本 spec 处理 `N3A` THEN SHALL 显式引用 lane2 spec 名 `n1-n3-host-inline-router-and-shared-adoption`，并 SHALL 要求两侧判据一致（按 `(册, sheet 名)` 二元组定位，SHALL NOT 仅按 sheet 码）。
3. 🔴 WHEN 现算「原底稿」三张 THEN SHALL 确认三形态各不相同：`表O1A （原底稿）`（N2 册，**全角空格 + 全角括号**）· `表O2A（原底稿）`（N4 册，foundation，全角括号无空格）· `表N3A (原底稿)`（N5 册，**半角括号 + 前导空格**）⇒ 本 spec 占 **2** 张，判据 SHALL NOT 用单一分隔符假设（依 NC-27）。
4. WHEN 现算审计程序表形态 THEN 本 spec 范围内 SHALL 含「净」形态 **2** 张（`表N2A` · `表N5A`）—— 全域仅这 2 张干净，其余 6 张带脏（依 NC-10）。
5. WHEN 交付 THEN 两份 lane spec 的 `N3A` 相关断言 SHALL 在跨 spec 复盘时被一并校验，任一侧缺失即视为未完成。
