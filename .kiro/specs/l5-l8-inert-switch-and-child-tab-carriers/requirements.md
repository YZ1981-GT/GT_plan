# L5 ~ L8 死开关与子 Tab 专属载体车道 — 需求

## 引言

**上游**：`l-cycle-sync-foundation-and-first-canary`（LC-1 ~ LC-26 共同裁决 + LF-P1 ~ LF-P48 + canary `L1-adj-*` 已闭环）+ `l2-l3-l4-orphan-twins-and-sheet-granularity-collapse`（LA-P1 ~ LA-P26，其中 **rowId 正面样板**是本 spec 去位置化的参考实现）+ L slice + 既存守卫 `backend/tests/workpaper_sync/test_task54_l_cycle_migration.py`。

**本 spec 的 entry 范围**（**4** 条，用 entry_id 全名）：
- `xlsx/gt-l5-long-term-payables`（L5L，长期应付款）
- `xlsx/gt-l6-special-payables`（L6S，专项应付款）
- `xlsx/gt-l7-other-noncurrent-liabilities`（L7O，其他非流动负债）
- `xlsx/gt-l8-financial-expenses`（L8F，财务费用）

**切分依据**：slice 自身的 `capability_target_blocked_by`——这四条是**含 BP-4 + BP-6、不含 BP-5** 的集合，与 {L1, L2, L3, L4} 完全互斥。四条的载体 kind 也齐整（全是 `child_tab_dedicated_composable`）、`switch_is_redeemable` 全为 `false`（开关存在但 inert）。

🔴 **共同裁决只引用编号**：LC-1 ~ LC-26 的判据内容在 foundation 的 `design.md`，本 spec **不复述**。

## 四条 entry 差异摘要（现算自 slice，供 Req 引用）

| entry | sheets / dispatch / HTML 覆盖 / OO 兜底 | 载体模块 | 科目性质 |
|---|---|---|---|
| `xlsx/gt-l5-long-term-payables` | 12 / 11 / 11 / 1（`GT_Custom`） | `useL5DualMode.ts` | 负债类 |
| `xlsx/gt-l6-special-payables` | 9 / 8 / 8 / 1（`GT_Custom`） | `useL6DualMode.ts` | 负债类 |
| `xlsx/gt-l7-other-noncurrent-liabilities` | 8 / 8 / 8 / 0 | `useL7DualMode.ts` | 负债类 |
| `xlsx/gt-l8-financial-expenses` | 10 / 10 / 10 / 0 | `useL8DualMode.ts` | 🔴 **损益类** |

**算术自检**：sheets 12 + 9 + 8 + 10 = **39**；HTML 覆盖 11 + 8 + 8 + 10 = **37**；OO 兜底 1 + 1 + 0 + 0 = **2**；37 + 2 = 39 ✓
**全 L 域闭合**：foundation 13 + lane2 38 + 本 spec 39 = **90** = owned sheets ✓

## Requirement 1：四条 entry 的 BP 归位

**User Story:** 作为实施者，我需要这四条 entry 的阻塞项被逐条归位，这样我知道哪些能做完、哪些卡外部供给。

### 验收准则

1. WHEN 现算四条的 `capability_target_blocked_by` THEN 系统 SHALL 得到每条均为 BP-1/2/3/**4**/**6**/7/9（7 项），并断言四条**完全一致**、且均**不含** BP-5 / BP-8 / BP-10。
2. WHEN 处理 BP-1 / BP-2 / BP-3 THEN 本 spec SHALL 标 `[ ]*`，**不承诺完成**。
3. WHEN 处理 BP-9 THEN 系统 SHALL 引用 **LC-1**，不重新裁决。
4. WHEN 处理 BP-7 THEN 系统 SHALL 引用 **LC-14**；🔴 四条的 `ui_toolbar_gate.anchor` 均为 `null`，但 `child_level_segmented_site` **非空**（子 Tab 里有 segmented）⇒ notice 的落位点须在**子 Tab 层**而非宿主层，这是与 foundation（L1 有宿主锚点）的关键差异。
5. WHEN 处理 BP-4 THEN 系统 SHALL 按 Requirement 2 收口。
6. WHEN 处理 BP-6 THEN 系统 SHALL 按 Requirement 3 收口。
7. WHEN 断言四条的 `evidence.unverifiable_reasons` THEN 系统 SHALL 现算确认它们比 L1~L4 **多一条**——即 BP-4 造成的「连『切过去看得到什么』都无法在浏览器里观察」，并断言 BP-4 **只**出现在这四条的 reasons 里。

## Requirement 2：BP-4 死开关收口（inert → 可兑现 或 摘除）

**User Story:** 作为实施者，我需要这四个 inert 开关不再骗人，这样用户点「OnlyOffice」时行为与界面一致。

### 验收准则

1. WHEN 判定 inert THEN 系统 SHALL 引用 **LC-2 / LC-15** 的三条件（子 Tab 有 `el-segmented` + mode 门控 `v-if`/`v-else-if`/`v-show` 现算 **0** + 该文件 `GtOnlyOfficeSheet` 命中 **0**），🔴 三条必须同时成立。
2. WHEN 建立对照组 THEN 系统 SHALL 现算 L1 / L2 宿主的门控式挂点作为「可兑现」的正例（引用 **LC-2**），证明判据能区分两种形态而非一律判红。
3. WHEN 现算每个 inert 开关消费到的 dualMode 成员 THEN 系统 SHALL 断言只有 `mode` / `modeOptions` / `switchMode` 三个，且 `mode` 只作 `v-model` 双绑（没有任何分支以它为条件）。
4. WHEN 选择收口路线 THEN 系统 SHALL 在两条之间**显式裁定并写明理由**：① **兑现**（补 OO 挂点 + mode 门控分支，使切换真实生效）；② **摘除**（删 segmented + 删 dual-mode 载体，回到单形态）。
5. WHEN 路线 ① 被选 THEN 它 SHALL 依赖 BP-1/2/3 的外部供给（无 contract / bundle 时补出来的 OO 侧无权威定义）⇒ 相应 task 标 `[ ]*`。
6. WHEN 路线 ② 被选 THEN 它 SHALL 遵守删旧代码铁律，且删除后四个 `useL{n}DualMode.ts` 的消费边归零 ⇒ 转为 orphan，须**同 commit 一并删**（不留 orphan）。
7. WHEN 收口完成 THEN 系统 SHALL 现算断言：inert 计数从 4 变为 0，且 `switch_is_redeemable` 不再有 `false` 值。
8. 🔴 WHEN 本 spec 描述 inert THEN 它 SHALL 引用 slice 的 `adjudication.not_single_html_because` 的立场：**「开关坏了」≠「无 OO 业务价值」**——四册模板各有真实业务 sheet，不得借 inert 把 entry 裁成 `single_html`。

## Requirement 3：BP-6 直调 health 端点收口

**User Story:** 作为实施者，我需要 OO 可用性探测走统一通道，这样不会各 entry 各自直调裸端点。

### 验收准则

1. WHEN 现算 L 域的 OO 端点调用 THEN 系统 SHALL 按端点字面量扫描并分别报数：`onlyoffice/health` 的命中数，与 `onlyoffice-config` 的命中数。
2. WHEN 断言两者关系 THEN 系统 SHALL 现算确认 **L 域 `onlyoffice-config` 命中为 0**（与 K 循环不同——K 有该端点的命中）⇒ L 域只探活不取配置，这是 BP-6 的准确形态。🔴 不得表述为「L 域两个端点都在直调」。
3. WHEN 判直调是否越层 THEN 系统 SHALL 定位调用点所属模块，并断言它们**不经**任何共享适配层（与 **LC-3** 的 LD-3 结论同型：L 域适配层是每循环一份）。
4. WHEN 收口方案被定义 THEN 它 SHALL 把探活收敛到单一入口（共享 composable 或 service），并现算断言收敛后直调点数为 0、入口调用点数 == 收敛前的直调点数。
5. WHEN 守卫落地 THEN 它 SHALL 禁止 L 域出现新的裸 `onlyoffice/health` 直调（按端点字面量卡点，不按符号名）。

## Requirement 4：子 Tab 专属载体族的统一

**User Story:** 作为实施者，我需要四个 `child_tab_dedicated_composable` 的载体形态被统一，这样后续改线只改一处。

### 验收准则

1. WHEN 现算四条的 `dual_mode_carrier` THEN 系统 SHALL 断言 kind 全为 `child_tab_dedicated_composable`、载体 site 全在 `l{n}/core/L{n}TabAdjudication.vue`、`mode_values` 全为 `["structured","onlyoffice"]`、`orphan_twin` 全为 `null`。
2. WHEN 对比 foundation 的形态 THEN 系统 SHALL 写明差异：L1/L2 的载体在**宿主**层且 `mode_values` 是 `["html","onlyoffice"]`（两个维度都不同）⇒ 🔴 四条的判据不可照抄 foundation。
3. WHEN 现算 localStorage 键 THEN 系统 SHALL 引用 **LC-18** 断言四条都属 `` `${PREFIX}:${wpId}` `` 形态（`:` 分隔，取键函数名与 L1/L2 不同），判据落「**key 含 wpId**」。
4. WHEN 统一方案被定义 THEN 它 SHALL 复用 foundation 对共享载体的裁定（引用 **LC-2** 与 foundation 关于「部分收缩」的结论），不新造第四种载体形态。

## Requirement 5：L6 / L7 的位置化行身份收口（全 L 域最密集）

**User Story:** 作为实施者，我需要 L6 / L7 的 item_id 行序号段被换成稳定行身份，这样双向回写不会删错行、读错值。

### 验收准则

1. WHEN 现算本 spec 四条名下的位置化命中 THEN 系统 SHALL 引用 **LC-8** 的口径 ②（`item_id` / `itemId` 模板串里的行序号段），按模块列分布并现算总数，断言本 spec 承担的份额是全 L 域最大的一块。
2. WHEN 登记分隔符两型 THEN 系统 SHALL 引用 **LC-8** 并断言 `row${…}`（**无连字符**）形态**只**出现在两个 L6 Disclosure 组件里，其余是 `row-${…}`。
3. 🔴 WHEN 登记索引基准两型 THEN 系统 SHALL 现算断言写侧模块用 `${i + 1}`、两个 L6 Disclosure 读侧用 `${i}`，并**逐键核对写入键与读取键是否真的成对**——若不成对则判为「读写键不闭合」真缺陷并单列修复项；若成对（不同 field 各自一套）则如实登记为「两套键并存」而非 bug。**取证前不得下结论。**
4. WHEN 去位置化方案被定义 THEN 它 SHALL 复用 lane 2 抽取的 **rowId 正面样板**（`useL2Detail` / `useL2VoucherCheck` / `useL3VoucherCheck` 的生成形态），不自造第四种。
5. WHEN 新旧键迁移 THEN 系统 SHALL 登记映射表，旧键保留只读兼容期；🔴 真库里 L6 / L7 / L8 载荷为 **0 行**（引用 **LC-24** 第 10 项）⇒ 迁移无存量数据风险，但闭环验证须标 `[ ]*`（待造数据）。
6. WHEN `removeRow` 被收口 THEN 系统 SHALL 引用 **LC-7** 的四元组，并处理本 spec 名下的签名变体（含 L7 两个 Disclosure 的 `removeRow($index)`、L8 的 `removeRow(section, index)` 双参形态）。

## Requirement 6：L5 / L6 的倒挤减法链（模板层）

**User Story:** 作为实施者，我需要「其他」项的倒挤公式不再吞掉新增行金额，这样增行后合计仍正确。

### 验收准则

1. WHEN 登记倒挤减法链 THEN 系统 SHALL 引用 **LC-20**，并断言**两种形态各自非空**：L5 是「减本表已列项」、L6 是「减对方表明细行」。
2. WHEN 断言变体不对称 THEN 系统 SHALL 现算确认它们**只出现在「国企」版附注**，上市公司版无 ⇒ 判据必须扫两个变体，只扫一个会漏。
3. WHEN 修复方案被定义 THEN 它 SHALL 把硬编码行号窗口换成**可随行数扩展**的形式（如整列 SUM 减去固定标签行，或用 `SUBTOTAL`），并现算断言修复后增行场景的合计正确。
4. 🔴 WHEN 本 spec 改模板 THEN 它 SHALL 同时更新 slice `template_ref` 的 sha256 基线，并在守卫里现算比对（引用 **LF-P23**）；不更新基线会让既存守卫红。
5. WHEN 修复范围被界定 THEN 它 SHALL 只含 L5 / L6 两册；L4 的审定表结构问题（引用 **LC-21**）归 lane 2，不在本 spec。

## Requirement 7：L8 损益类分支

**User Story:** 作为实施者，我需要 L8 的 TB 口径按发生额处理，这样审定数不会被当成余额发布。

### 验收准则

1. WHEN 现算 L8 的科目性质 THEN 系统 SHALL 引用 **LC-26** 并断言 L8 是本 spec 唯一（也是 8 条里唯一）的损益类 entry，其他七条是负债类。
2. WHEN 断言 TB 口径 THEN 系统 SHALL 现算确认 L8 的发布参数走「本期发生额」而非「期末余额」，判据落发布调用的实参形态（引用 **LC-3** 的端点字面量口径）。
3. WHEN 四表判据被写 THEN 它 SHALL 按资产负债 / 损益**分支**，且两个分支都有非空分母（负债类 7 条 + 损益类 1 条）。
4. WHEN L8 的 derived_total 键被处理 THEN 系统 SHALL 引用 **LC-16** 并断言它属 MID 型、且**少了重复 sheet 段**（L8 的二次分裂）。
5. WHEN L8 的模板结构被登记 THEN 系统 SHALL 记入两项：`非金融机构利息支出测算表L8-4` 的四固定槽 + 硬编码加法链；以及该表**单元格值带尾随空格**（含下划线占位）⇒ 按标签匹配回写会失配，须按坐标而非标签。

## Requirement 8：空分母与结构性零

### 验收准则

1. WHEN 本 spec 的任一 Property 分母为空 THEN 它 SHALL 标「不宣称通过」并指明承载者。
2. WHEN 引用结构性零 THEN 系统 SHALL 引用 **LC-24**，不重复列十项。
3. 🔴 WHEN 四条的端到端闭环被规划 THEN 它 SHALL 全部标 `[ ]*`——真库 L6/L7/L8 为 0 行、L5 仅两行 `'[]'` ⇒ 四条均无有效载荷。
