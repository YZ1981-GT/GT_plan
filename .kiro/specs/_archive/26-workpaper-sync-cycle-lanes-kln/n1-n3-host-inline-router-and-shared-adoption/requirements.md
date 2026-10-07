# N1 / N3 宿主内联路由与共享路由采纳 — 需求

## 引言

**上游**：`n-cycle-sync-foundation-and-first-canary`（以下简称 **foundation**）已一次性裁定共同判据 **NC-1 ~ NC-37**，本 spec **只引用编号、不复述判据正文**。术语与口径（strict 域三路取并 / 注释剥离 / 行数口径 / 按索引删与按行身份删 / 计数现算纪律）一律沿用 foundation 的「术语与口径」节。

**本 spec 的 entry 范围**（**2** 条）：

| entry_id | wp_code | 科目 / 方向 | sheets | 公式格 | 带 fx | HTML child | prog | OO 兜底 | mount | 载体 kind | BP 数 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-n1-deferred-tax-assets` | N1D | 1811 递延所得税资产 / 借 | 10 | **593** | 8 | 8 | 1 | 1 | 2 | `per_entry_composable_three_modes`（257 行，含 **matrix** 第三值） | **9** |
| `xlsx/gt-n3-deferred-tax-liabilities` | N3D | 2901 递延所得税负债 / 贷 | 6 | 162 | 4 | 4 | 0 | 2 | 3 | **`host_inline_real`** | **9** |

**切分主题**：宿主内联 sheet 路由 + 未采用共享路由。两条 entry 共同构成 slice 自己的 `hosts_using_host_inline_regex: 2` 集合，且 **BP-4（{N3}）与 BP-10（{N1, N3}）完整内聚于本 spec**，无需跨 spec 协调。

🔴 **本 spec 与 lane3 的唯一交叉点**：sheet 码 `N3A` 同时存在于 **N3 册（本 spec）与 N5 册（lane3）**。任一侧单独修改会漏另一侧，两份 spec 须互相引用（见 Requirement 14）。

**Property 前缀**：本 spec 用 **NA-P**（foundation 用 NF-P，lane3 用 NB-P，三者不重号）。

## 需求

### Requirement 1 — entry 范围与归属算术

**用户故事**：作为维护者，我要确认本 spec 承担的份额与 foundation 算术自检表严格对齐，避免三份 spec 之间出现归属漏项或重复。

#### 验收标准

1. WHEN 现算本 spec 归属 THEN SHALL 逐项吻合：sheets **16**（10 + 6）· 公式格 **755**（593 + 162）· 带 fx **12**（8 + 4）· HTML child **12**（8 + 4）· prog console **1**（1 + 0）· OO 兜底 **3**（1 + 2）· OO 挂点 **5**（2 + 3）。
2. WHEN 现算 orphan 归属 THEN SHALL 为 **2** 个：`useN3DualMode.ts` · `n1DisclosureSegmentTypes.ts`；🔴 后者是**小写 `n{1..5}` 前缀模块**，用 M 轮正则会漏（依 NC-5）。
3. WHEN 现算 live dual-mode 归属 THEN SHALL 为 **1** 个（`useN1DualMode.ts`）；宿主内联载体归属 SHALL 为 **1**（N3）。
4. WHEN 现算真库归属 THEN SHALL 为 **19** 行（N1 **17** + N3 **2**），占 N 域 30 行中的多数。
5. WHEN 现算 `definedName` 归属 THEN total SHALL 为 **48**（N1 24 + N3 24）· broken SHALL 为 **30**（15 + 15）。
6. WHEN 现算超列真缺陷归属 THEN SHALL 为 **11** 处，全部属族 A2（`N3-2` H11~H21），本 spec **无族 A1 真缺陷**（族 A1 三处分属 foundation 1 + lane3 2）。
7. WHEN 现算超宽表归属 THEN SHALL 为 **1** 张（`N1/附注披露信息（国企）` 256 列 / 有值列 7 / 幽灵 **249**）；footer 缺斜杠归属 SHALL 为 **0**。
8. WHEN 现算真库跨 entry 污染归属 THEN SHALL 为 **2** 条（`N1-3-entries` · `N3-3-entries`，均落 `wp_code='G8'`），依 NC-19。

### Requirement 2 — BP-10 收口：N1 / N3 采纳共享 sheet 路由

**用户故事**：作为架构维护者，我要让 N1 / N3 停用宿主内联正则判 sheet，改用已有共享路由模块，消除两套并行实现。

#### 验收标准

1. WHEN 现算共享路由采用方 THEN SHALL 为 **3**（`n2SheetRouting.ts` / `n4SheetRouting.ts` / `n5SheetRouting.ts`），N1 / N3 SHALL NOT 在列 —— 这正是 BP-10 的成因（依 NC-19 · NC-31 的成员集裁定）。
2. WHEN 为 N1 / N3 新增路由模块 THEN SHALL 沿用既有三者的模块形态与命名（`n1SheetRouting.ts` / `n3SheetRouting.ts`），SHALL NOT 另创新范式。
3. 🔴 WHEN 迁移 N1 的 sheet 判定 THEN SHALL 保留 N1 特有的 `isSwitchableSheet` 语义 —— N1 门控写作 `v-if="isSwitchableSheet && dualMode.isOnlyOffice.value"`，其余 4 条 entry 用 `isHtmlSheet`；直接替换为 `isHtmlSheet` 会改变行为。
4. 🔴 WHEN 迁移 N3 的 sheet 判定 THEN SHALL 保留其**三条件**门控 `v-if="isHtmlSheet && renderMode === 'onlyoffice' && ooHealthy"`，SHALL NOT 简化为两条件。
5. WHEN 采纳完成 THEN 共享路由采用方 SHALL 从 3 升至 **5**，BP-10 成员集 SHALL 变为空集，守卫 SHALL 按此变化断言。
6. 🔴 WHEN 处理 sheet 名 THEN SHALL NOT 归一化（依 NC-10）—— 本 spec 范围内有「表的{码}」脏形态 **3** 处（见 Requirement 10），归一化会使守卫失效。

### Requirement 3 — BP-4 收口：N3 宿主直调 health 收敛

**用户故事**：作为实施者，我要把 N3 宿主里直接写的 OnlyOffice 健康检查收敛到统一能力层，并修掉静默失败。

#### 验收标准

1. WHEN 现读 N3 宿主 THEN SHALL 确认其为 `host_inline_real`：`renderMode = ref<'html' | 'onlyoffice'>('html')` · `ooHealthy` · `checkOoHealth()` 内 `http.get('/api/workpapers/onlyoffice/health')` · `onModeChange` 内 `renderMode.value = val`。🔴 识别正则 SHALL 覆盖**带泛型**的 `ref<...>(` 写法（依 NC-13 · NF-P9）。
2. 🔴 WHEN 现读 `onModeChange` THEN SHALL 登记缺陷：`if (val === 'onlyoffice' && !ooHealthy.value) return` —— **静默 return 无任何用户提示**，用户点了开关却无反应且不知原因。
3. WHEN 收敛 health 调用 THEN SHALL 改为经统一能力层，且 `onlyoffice/health` 的生产命中数 SHALL 保持 **5**（每 entry 一处，不因收敛而新增或丢失）。
4. 🔴 WHEN 修复静默失败 THEN SHALL 给出明确用户反馈（不可用原因 + 已回落 HTML 模式），SHALL NOT 仅加日志。
5. WHEN 收敛完成 THEN BP-4 成员集 SHALL 变为空集。
6. 🔴 WHEN 处理 N1 的端点直调 THEN SHALL 一并收敛 `onlyoffice-config`（全 N 域现算 **1** 处，位于 `useN1DualMode.ts`）—— 该项与 M 轮（0 处）不同，是 N 域独有触点（依 NC-37 的端点分母登记）。

### Requirement 4 — N1 三值载体（含 matrix）与门控异形

**用户故事**：作为实施者，我要知道 N1 的双模载体有第三个模式值 matrix，避免按二值假设改造后丢功能。

#### 验收标准

1. WHEN 现读 `useN1DualMode.ts` THEN SHALL 确认 **257** 行、kind = `per_entry_composable_three_modes`，且模式取值含 **matrix**（非 html / onlyoffice 二值）。
2. WHEN 现算其被消费成员 THEN SHALL 为 **9** 个：`mode` · `modeOptions` · `switchMode` · `fetchingConfig` · `isOOHealthy` · `ooConfigReady` · `isOnlyOffice` · `isMatrix` · `onOoLoadFailed`。改造 SHALL NOT 减少任何成员的对外契约。
3. WHEN 现算其生产边 THEN SHALL 为 **5** 条（宿主 + 4 个子 Tab），且 localStorage 键 SHALL 为 `n1-dual-mode` 并**按 wp 分区**（依 NC-16）。
4. 🔴 WHEN 现算 N1 直调端点 THEN SHALL 为 **2** 个（`onlyoffice/health` + `onlyoffice-config`），是 N 域唯一同时直调两端点的 entry。
5. WHEN 改造 N1 THEN SHALL 保留 matrix 分支；若统一能力层不支持三值，SHALL 在能力层扩展而非在 N1 侧砍功能。

### Requirement 5 — `parent_duplicate` 条件节的数据侧实装

**用户故事**：作为守卫维护者，我要让 K/L/M 三轮一直为空的条件节在 N1 真正被断言，而不是继续保留空壳。

#### 验收标准

1. 🔴 WHEN 现算 `parent_duplicate` THEN SHALL 为 **4** 条且**全部挂在 N1**：`xlsx/n1/calc/n1-tab-calc-table` · `xlsx/n1/core/n1-tab-adjudication` · `xlsx/n1/core/n1-tab-adjustment` · `xlsx/n1/core/n1-tab-detail`（依 NC-31）。
2. WHEN 比对前三轮 THEN K / L / M SHALL 均为 **0** ⇒ N 是首次触发的循环，本 spec SHALL 给出 4 条的完整断言而非分支占位。
3. WHEN foundation 交付判据骨架后 THEN 本 spec SHALL 填入 N1 侧数据断言，两者 SHALL NOT 重复实现判据逻辑。
4. WHEN 处理这 4 条 THEN SHALL 明确它们与 canary 的关系：canary 键 `N4-1-rows` 不在此列表中（foundation Requirement 5 第 5 条的前提由本 spec 的现算共同支撑）。

### Requirement 6 — `transport_key` 双 owner 与 TK-2 恒假陷阱

**用户故事**：作为守卫作者，我要避免为 N1 的调整类键写出永远为假的断言。

#### 验收标准

1. WHEN 现读 owner 常量 THEN N1 SHALL 有**两处**声明：`useN1FormData.ts`（545 行）= `'N1-'` · **`useN1Adjudication.ts`（507 行）= `'N1-1-adj'`** ⇒ `two_source_declarations` = **1**（全 N 域唯一）；N3 SHALL 为 `useN3FormData.ts`（379 行）= `'N3-'`。
2. 🔴 WHEN 为 TK-2 写守卫 THEN SHALL NOT 用「`N1-1-adj-0` … `-6` 字面量至少 1 命中」—— 这 7 个展开键在源码中**一个都不存在**（运行时拼接），该判据恒假。SHALL 改用 foundation NC-30 裁定的双条件（模板串命中 + 展开数 == `N1_ADJUDICATION_CATEGORIES` 长度 **7**）。
3. WHEN 现算 TK 分类 THEN 本 spec 范围内 SHALL 为 clean **1**（TK-1）+ with_defect **1**（TK-2 所在的 N1 调整链）+ N3 侧 **1**（TK-3，with_defect）。
4. WHEN 校验不存在的键 THEN 本 spec 相关的 `N1-1-rows` · `N1-1-adjudication-rows` · `N3-1-rows` SHALL 各 **0** 命中（依 NC-30 的反向分母纪律）。

### Requirement 7 — 行身份 A 族 3 处改造为稳定身份

**用户故事**：作为双向回写的实现者，我要把 N1 里用索引拼持久化键的 3 处改成稳定身份，避免行序变动导致数据错位。

#### 验收标准

1. WHEN 现算 A 族（持久化键 `${ITEM_PREFIX}-${index}`）THEN SHALL 为 **3** 处且**全部在 `useN1Adjudication.ts`** —— 全 N 域 A 族仅此 3 处，本 spec 承担 100%。
2. 🔴 WHEN 改造 THEN SHALL 抄 E 族既有正面形态（`rowId` / `rowKey` / `id`，全域 **86** 处 / 27 文件），SHALL NOT 自建新范式（依 NC-6 的反转裁定）。
3. 🔴 WHEN 取用样板 THEN SHALL 在 foundation 任务 14 完成形态提取**之后**进行 —— 18 处样板原位于 foundation 归属的 orphan 内，先删后抄会丢样板。
4. WHEN 改造 `removeRow` THEN SHALL 把本 spec 范围内的 by_index 调用改为 by_rowid 形态（全域 18 : 13，目标是提升后者），守卫按单调方向断言（依 NC-7）。
5. WHEN 改造完成 THEN A 族计数 SHALL 降至 0，且 `N1-1-adj` 的持久化键 SHALL 不再含数组下标。

### Requirement 8 — 契约字段：N1 披露表载荷在 `conclusion`

**用户故事**：作为契约实现者，我要确保 N1 的披露表数据被正确读写，它们不在 `remark` 而在 `conclusion`。

#### 验收标准

1. 🔴 WHEN 现算 N1 真库载荷 THEN `conclusion` 非空 SHALL 为 **14** 行（N3 为 **2**，本 spec 合计 **16**），而 `remark` 非空 N1 仅 **1** 行且该行是 AI 会话（`N1-review-session-*`，261 B）⇒ N1 的业务数据 **100% 在 `conclusion`**（依 NC-34）。
2. WHEN 列举 N1 的 `conclusion` 载荷 THEN SHALL 含 `N1-disclosure-listed-unoffset`（**1201 B**）· `N1-disclosure-soe-unoffset`（**1198 B**）· `N1-disclosure-soe-netoffset`（**1196 B**）· `N1-disclosure-soe-synced-tables`（298 B）· `N1-5-rows`（363 B）。
3. 🔴 WHEN 按后缀判优先级 THEN `-disclosure-*` SHALL 取 `conclusion`、`-rows` SHALL 取 `remark`（依 NC-34 的冲突优先级）—— 🔴 但 `N1-5-rows` 实际存在于 `conclusion`（363 B）⇒ 本 spec SHALL 登记该例外并以「实际非空列」优先于后缀规则，SHALL NOT 因规则冲突而跳过该行。
4. WHEN 处理 `N1-review-session-*` THEN SHALL 按白名单排除，SHALL NOT 当业务载荷解析（依 NC-34）。
5. WHEN 现算变体轴 THEN N1 SHALL 为完整双版本（`附注披露信息（上市公司）` + `附注披露信息（国企）`）⇒ 披露表读写须覆盖两个变体。

### Requirement 9 — 真库跨 entry 污染 2 条登记

**用户故事**：作为平台维护者，我要登记本 spec 范围内落错宿主的两行数据，避免 sync 改线时把污染固化。

#### 验收标准

1. 🔴 WHEN 现算本 spec 污染 THEN SHALL 为 **2** 条：`N1-3-entries` 与 `N3-3-entries`，两者 `wp_code` 均为 **`G8`**（依 NC-19）。
2. WHEN 判定性质 THEN SHALL 引用 NC-19 的裁定：G8 是跨循环污染汇聚点（与 L 轮 LC-22 同宿主），属平台级问题 ⇒ 本 spec **登记 + 守卫锁定现值**，SHALL NOT 就地清理。
3. WHEN 实现 `-3-entries`（调整分录汇总）的双向回写 THEN SHALL 以 entry 自身 `wp_code` 为写入目标，SHALL NOT 沿用被污染行的 `wp_code`。
4. WHEN 查询真库 THEN SHALL 用 asyncpg（🔴 `psycopg2` 未安装），每条查询独立连接；无库环境 skip 并标原因，SHALL NOT 静默 pass。

### Requirement 10 — 模板层缺陷登记（族 A2 · 「表的{码}」· definedName）

**用户故事**：作为审计业务负责人，我要知道 N3 有一整列公式静默失效、N1/N3 的 sheet 命名有多字脏形态，且这些都不在本轮改模板。

#### 验收标准

1. 🔴 WHEN 现算族 A2 THEN `N3/递延所得税负债明细表N3-2` 的 **H11 ~ H21 全 11 行**同形 `=F#+O#`（行偏移 **−8**，列 O(15) > `max_column` 14）SHALL 被登记为**结构残留**：**无反向分母**（11 行全同形）⇒ 整列一致但整列失效（H 列恒等于 F 列）。
2. 🔴 WHEN 判定性质 THEN SHALL 明确其与族 A1 **不可合并计数**（依 NC-32）：A1 是有强反向分母的个别行录入事故，A2 是整列结构残留（更像复制公式未调行号或 O 辅助列已被删）。
3. WHEN 处理族 B THEN `N3-2 E23 =SUM(E3:O22)` SHALL 判为**合法**（矩形区间，SUM 忽略空列）。
4. 🔴 WHEN 现算「表的{码}」脏形态 THEN SHALL 为 **3** 处且全在本 spec：N1 `递延所得税资产审计程序表的N1A` · N1 `可用以后年度税前利润弥补的亏损检查表的N1-5` · N3 `递延所得税负债审计程序表的N3A` ⇒ 按 `审计程序表{code}` 提码 SHALL 在 N1 / N3 失配（依 NC-10）。
5. WHEN 现算 `definedName` THEN N1 SHALL 为 24 / broken 15、N3 SHALL 为 24 / broken 15，合计 **48 / 30**；broken 形态 SHALL 含 `#REF!` · `[1]Breakdown!#REF!` · 🔴 `'[2]2004'!#REF!`（新形态）· 🔴 中文名 `本循环科目`（依 NC-9）。
6. 🔴 WHEN 本 spec 任何任务执行 THEN SHALL NOT 修改 `.xlsx` —— 模板 sha256 交付后须仍 5/5 match（依 NC-25）。缺陷以**记录型**测试锁定现状，未来修复时显式失败提醒同步更新。

### Requirement 11 — 超宽表 N1 256 列的遍历策略

**用户故事**：作为双向回写的实现者，我要避免在 249 个空列上空转。

#### 验收标准

1. 🔴 WHEN 现算 `N1/附注披露信息（国企）` THEN SHALL 为 **256 列 × 74 行**，`last_value_col` = **7** ⇒ 幽灵 **249** 列（依 NC-35）。
2. WHEN 遍历该 sheet THEN 上界 SHALL 取 `last_value_col` 而非 `max_column`；守卫 SHALL 锁定差值 249，变化时显式失败。
3. WHEN 现算本 spec 幽灵行 Top THEN SHALL 含 `N1/底稿目录` **11** 行。
4. WHEN 现算本 spec 公式格 Top THEN SHALL 为 `N1-4 测算表` **227** · `N1-2 明细表` **134** · `N1-1 审定表` **128**；裸 IF SHALL 为 `N1-4 测算表` **120** · `N1-1` 20 · `N3-1` 14。
5. 🔴 WHEN 处理 `N1-4 测算表` THEN SHALL 登记其为全 N 域公式与裸 IF 双料最密 sheet（227 公式格 / 120 裸 IF）⇒ 改造风险最高，须单独回归。

### Requirement 12 — N3 的结构性特殊（唯一无附注 entry）

**用户故事**：作为实施者，我要知道 N3 在多项维度上都是 5 条 entry 中的唯一例外，避免按「每 entry 都有」的假设写判据。

#### 验收标准

1. 🔴 WHEN 现算 N3 的附注披露 sheet THEN SHALL 为 **0** —— N3 是 5 条 entry 中**唯一完全无附注披露**的（其余 4 条为完整或缺括号的双版本）⇒ 变体轴 **4 : 1**（依 NC-22）。
2. WHEN 现算 N3 其余极值 THEN SHALL 确认它同时是：唯一无 disclosure 子组件 · sheets 最少（**6**）· 公式格最少（**162**）。
3. WHEN 编写覆盖 disclosure 的判据 THEN SHALL 对 N3 声明**空分母**，SHALL NOT 写「已验证 N3 披露正常」（依 NC-20）。
4. WHEN 现算 N3 的 OO 兜底 THEN SHALL 为 **2**、OO 挂点 **3**，多于其 HTML child 4 的比例关系须如实登记。

### Requirement 13 — orphan 2 个删除（先抄后删）

**用户故事**：作为维护者，我要清掉本 spec 范围内的两个无引用模块，但不能在提取样板前删。

#### 验收标准

1. WHEN 现算本 spec orphan THEN SHALL 为 **2** 个：`useN3DualMode.ts` · `n1DisclosureSegmentTypes.ts`。
2. 🔴 WHEN 统计 orphan THEN SHALL 用含小写分支的正则 —— 否则 `n1DisclosureSegmentTypes.ts` 会漏，本 spec orphan 数会错报为 1（依 NC-5）。
3. WHEN 删除前 THEN SHALL grep 确认 0 生产引用，且 SHALL 在 foundation 任务 14（形态提取）之后执行。
4. WHEN 删除后 THEN 全域 orphan 总数 SHALL 相应下降，`TestOrphanInventory` SHALL 同步更新（🔴 类名沿用 foundation 的 `TestOrphanInventory`，非 M 轮的 `TestOrphanDualModeInventory`）。
5. WHEN 断言 orphan 行数 THEN SHALL 用现算值，SHALL NOT 照抄删除清册（plan 的 orphan 行数计数本身有错，依 NC-29）。

### Requirement 14 — 与 lane3 的交叉引用（`N3A` 跨册碰撞）

**用户故事**：作为两份 lane spec 的读者，我要知道有一处缺陷横跨两份 spec，任一侧单独处理都不完整。

#### 验收标准

1. 🔴 WHEN 现算 sheet 码 `N3A` THEN SHALL 确认它同时存在于 **N3 册（本 spec）与 N5 册（lane3）**：N3 册内为 `递延所得税负债审计程序表的N3A`，N5 册内为 `…N3A (原底稿)`（半角括号 + 前导空格）。
2. WHEN 本 spec 处理 `N3A` THEN SHALL 显式引用 lane3 spec 名 `n2-n5-json-table-identity-and-cross-entry-readonly`，并 SHALL 要求两侧判据一致（按 `(册, sheet 名)` 二元组定位，SHALL NOT 仅按 sheet 码）。
3. WHEN 现算外来字母码 THEN SHALL 确认 N 册内存在 `O1A`（N2 册，lane3）与 `O2A`（N4 册，foundation）—— 本 spec 范围内**无外来码**，该项对本 spec 空分母（依 NC-21）。
4. WHEN 交付 THEN 两份 lane spec 的 `N3A` 相关断言 SHALL 在跨 spec 复盘时被一并校验，任一侧缺失即视为未完成。
