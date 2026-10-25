# Requirements Document

## Introduction

本 spec 是 **I 循环 lane 1**，覆盖 **I1（无形资产）与 I3（商誉）** 两条 entry 的双向回写落地。

选这两条放一起不是按科目相邻，而是因为**缺陷集合天然重合**：
🔴 **BP-6（位置化行身份）的 entry 全集恰好就是 {I1, I3}** —— 全 I 循环 8 处位置化 site 里，
**I3 占 7 处、I1 占 1 处，其余 4 条 entry 一处也没有**。同时 **BP-7**（`I1_SOE_CATEGORIES`
与两个真源都不符）与 **IC-14**（`明细表I3-2` 四格金额错误）也分别只落在这两条上。
把它们合成一个 lane，改一次披露层行身份范式就能同时收口两条 entry。

**上游（只引用，不复述）**：
`i-cycle-sync-foundation-and-first-canary`（**IC-1 ~ IC-20** 共同裁决 + canary I6 端到端范式）·
umbrella Task 51 的 I slice · FC-1~FC-13 · GC-1~GC-10 · HC-1~HC-16。

🔴 **IC-1 ~ IC-20 的正文在地基 spec 裁定，本 spec 一条都不复述**（复述即漂移）。
本 spec 只做两件事：把 IC 判据**实例化到 I1/I3**，以及裁定 **lane 专属**的新事实。

**不重造已有产物**：
`backend/tests/workpaper_sync/test_task51_i_cycle_migration.py`（149,054 B 守卫）·
`composables/__tests__/iAdjudicationPublishGate.spec.ts`（已含 `buildI1()` / `buildI3()`）·
`composables/__tests__/i1CategoryScope.spec.ts` · `iCycleDynamicRows.spec.ts` ·
`i1DisclosureAddCategory.spec.ts` · `backend/app/services/four_table/i_cycle_*.py`（5 文件）。

🔴 **不得修改 `backend/wp_templates/` 字节**（IC-14 走覆盖层）。
🔴 **不得修改 H1 pilot 的契约 / adapter / golden digest**（IC-17）。
🔴 **不得改 `I2-2-rows` 键名**：I1 侧 `useI1AdditionCheck.ts#L250-251` 跨 entry 读它（详见 Requirement 7）。

## 范围：2 条 entry / 33 sheets

| entry_id | 宿主 | 幻影码 | sha256 前 16 / 字节 / sheets | mount | 写族 | payload mode | 主表键 | 身份 | 专属阻塞 |
|---|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-i1-intangible-assets` | `GtI1IntangibleAssets.vue` | I1I | `97eced1f58ab3925` / 136,885 / **18** | 2 | host_inline | remark_only | `I1-2-rows` | rowId | **BP-6**（1 处）· **BP-7** |
| `xlsx/gt-i3-goodwill` | `GtI3Goodwill.vue` | I3G | `96cd6d6cb70698ce` / 212,588 / **15** | **4** | host_inline | remark_only | `I3-2-rows` | rowId | **BP-6**（7 处）· **IC-14** |

🔴 **两条 entry 的真库主表载荷都是空的**（I 循环真库只 `I5-2-rows` 745 B 与 `I6-2-detail-rows` 194 B
两条非空）⇒ 本 lane **不具备 canary 资格**，必须复用地基 spec 的 I6 canary 范式；
且 roundtrip 只能用**合成载荷**，SHALL 在证据里标 `synthetic_payload_no_live_db_baseline`。

## Requirement 1：BP-6 位置化行身份 8 个 site 的分治修复

**User Story**：作为审计助理，我在披露表里增删行后再次打开底稿，每一行必须还是原来那一行，
不能因为行序变了就把上一行的数据顶到下一行。

### Acceptance Criteria

1. WHEN 实施本 Requirement THEN SHALL 先**现算**位置化 site 清单并与下表**逐项等值**，
   任何一项不符 SHALL 停止实施并回到地基 spec Task 9 重裁：

| # | 族（IC-6 口径） | site | 身份表达式 | entry |
|---|---|---|---|---|
| 1 | **A′ 纯下标** | `composables/useI3Disclosure.ts#L488` | `rowId: \`cgu-${i}\`` | I3 |
| 2 | B 下标兜底 | `composables/useI3Disclosure.ts#L441` | `bv-${r.rowId \|\| i}` | I3 |
| 3 | B 下标兜底 | `composables/useI3Disclosure.ts#L463` | `imp-${r.rowId \|\| i}` | I3 |
| 4 | B 下标兜底 | `composables/useI3Disclosure.ts#L503` | `perf-${r.rowId \|\| i}` | I3 |
| 5 | B 下标兜底 | 🔴 `i3/impairment/I3TabRecoverableTest.vue#L686` | `String(r.rowId \|\| \`cgu-${idx}\`)` | I3 |
| 6 | B 下标兜底 | `composables/i1DisclosureEnhance.ts#L241` | `tc-i18-${r.rowId \|\| i}` | **I1** |
| 7 | **D 递增计数** | `composables/useI3Disclosure.ts#L665` | `perf-${Date.now()}-${added}` | I3 |
| 8 | **D 递增计数** | `composables/useI3Disclosure.ts#L725` | `ap-${Date.now()}-${added}` | I3 |

2. 🔴 WHEN 编写扫描守卫 THEN SHALL 按**形态口径**（`r.rowId || <下标>` / `${i}` / `${added}`）扫描，
   **禁按文件类型口径**只扫 `composables/`：site #5 在 `.vue` 里，只扫 composable 会整处漏网。
   变异「把扫描限定为 `composables/` 目录」SHALL 打红。
3. WHEN 修 **族 A′（site #1）** THEN SHALL 换成 `Date.now()+Math.random()` 稳定 id（照 IC-6 族 A 范式，
   同文件 `#L521/#L570/#L629/#L690` 已是族 A，直接复用其生成器），
   并 SHALL 断言落库链路仍完整：`#L497 _persistSection('cgu_allocation')` → `#L870 _persistSection`
   → `GtI3Goodwill.vue#L319 http.put`，写入键 `I3-disc-{listed|soe}-cgu_allocation-rows`。
4. WHEN 修 **族 B（site #2~#6）** THEN 回落分支 SHALL 改为生成稳定 id 而非下标；
   SHALL 保留「上游有 rowId 时优先用上游 rowId」的现有语义（不得反向覆盖上游身份）。
5. WHEN 修 **族 D（site #7/#8）** THEN SHALL 去掉 `${added}` 计数，改用与族 A 同一生成器；
   判据 SHALL 复现原缺陷：同一毫秒内两次批量预填且 `added` 均从 0 起 ⇒ 撞 id。
6. 🔴 WHEN 编写判据 THEN SHALL 对 **族 C 的 20 处展示序号反向断言「不被点名」**
   （`i1AdditionCheckModel.ts#L314` · `i1DisclosureSyncPayload.ts#L43` · `useI{1,2,3}Adjustment.ts` 等）；
   把任一处族 C 报成缺陷即判据失败。
7. WHEN 修完 THEN SHALL **另行登记不修**的位置化**标签** 3 处
   （`useI3Disclosure.ts#L442`/`#L464` 的 `investee: 项目${i+1}` · `#L504` 的 `name: 项目${i+1}`）：
   它们是业务字段兜底不是行身份，改动会影响用户可见文案 ⇒ 归业务确认（`[ ]*`）。
8. WHEN 迁移历史数据 THEN SHALL 提供 backfill：已落库的 `cgu-{n}` / `bv-{n}` / `imp-{n}` / `perf-{n}` /
   `tc-i18-{n}` 形态 id **保持原值不动**（改了等于换身份），只对**新增行**用新生成器；
   SHALL 在契约里声明 `legacy_positional_ids_grandfathered: true`。

## Requirement 2：BP-7 修复 + 🔴 CD-1 的 impl 边是**双定义**（本轮新发现）

**User Story**：作为业务合伙人，我在国企版披露表看到的无形资产分类必须与源模板一致，
不能出现源模板里没有的分类，也不能把源模板里的分类改了名。

### Acceptance Criteria

1. WHEN 处置 **BP-7** THEN SHALL 按 IC-5 三边校验（声明 / openpyxl 真读 / impl 常量）**有序等值**比对
   `I1_SOE_CATEGORIES`（`i1SoeDisclosureModel.ts#L29-42`，**12 条**）
   对 `附注披露信息（国有企业）!A9:A19`（**11 格**），并 SHALL 逐条落表五项差异：

| # | 差异 | impl 值 | 源模板值 |
|---|---|---|---|
| 1 | 条数 | 12 | **11** |
| 2 | 位次 | `软件` 在**第 1 条**（label `其中：软件`） | `软件` 在**第 8 条** |
| 3 | 命名 | `房屋使用权` | `住房使用权` |
| 4 | 命名 | `特许权` / `采矿权` | `特许经营权` / `矿产权` |
| 5 | 多出 | `探矿权`（源模板无） | — |

2. WHEN 校验第二真源 THEN SHALL 断言 `采矿权` / `探矿权` / `房屋使用权` 三词在
   `note_template_soe.json` 里命中 **0**（slice 已双向证实）⇒ 两个真源都不支持 impl 的写法。
3. 🔴 WHEN 实施 **CD-1** 的三边校验 THEN SHALL 登记本轮新发现：
   **`I1_DEFAULT_CATEGORIES` 是同名双 export 定义**，且**类型不同**：

| 定义处 | 类型 | 条数 | 现算内容 |
|---|---|---|---|
| `composables/i1CategoryScope.ts#L19` | `I1CategorySlot[]`（key/label/seq/removable） | 11 | 土地使用权 / 住房使用权 / 专利权 / 非专利技术 / 商标权 / 著作权 / 特许经营权 / 软件 / 矿产权 / 数据资源 / 其他 |
| `composables/useI1Adjudication.ts#L105` | `readonly string[]`（纯中文串） | 11 | **同上，有序完全一致** |

4. 🔴 THEREFORE CD-1 的 impl 边 SHALL **同时比对这两处**：当前两边**内容与顺序都一致**（本轮现算确认），
   但它们是**两个独立真源** —— 改一处不会传播到另一处。
   `i1ListedDisclosureModel.ts#L41` 的注释已明确「label 由 `i1CategoryScope.I1_DEFAULT_CATEGORIES` 派生，
   本文件不再抄第二份」⇒ 平台**收敛过一次但漏掉了 `useI1Adjudication.ts`**。
5. 🔴 WHEN 编写 CD-1 判据 THEN 变异「只改 `i1CategoryScope.ts` 的第 8 条 `软件`」SHALL 打红
   （若判据只比对单边则静默通过 = 假绿）。
6. WHEN 收敛双定义 THEN SHALL 让 `useI1Adjudication.ts#L105` 改为从 `i1CategoryScope` 派生
   （`I1_DEFAULT_CATEGORIES.map(c => c.label)`），保持导出名与 `as const` 语义兼容现有 22 处引用；
   SHALL 逐条跑 `i1CategoryScope.spec.ts` / `useI1Adjudication.spec.ts` / `iCycleDynamicRows.spec.ts` 零回归。
7. 🔴 WHEN 处置 BP-7 的**修法** THEN SHALL 标 `[ ]*`（依赖业务确认）：
   源模板 11 类与 `note_template_soe.json` 谁是权威、`探矿权` 是否保留，
   都是**会计披露口径问题不是代码问题**；本 lane 只交付三边判据 + 差异登记 + 不修的显式记录。
8. WHEN 校验稳定 key THEN SHALL 断言 `i1CategoryColumnKey`（`i1CategoryScope.ts#L34-36`）
   生成 `${slot.key}_${slot.seq}` 符合 H7 范式 SK-1；
   SHALL 反向断言全 I 的 `key: X.label` 与 `row[X.label]` 命中 **0**（H8 那族缺陷在 I 不存在）。
9. 🔴 WHEN 登记**源模板内部真源断链** THEN 本 lane SHALL 承接落在 I1 的 2 处
   （`附注披露信息（上市公司）!K10` 与 `明细表I1-2!A29` 都是字面 `数据资源`，不是 `=底稿目录!A18`）；
   第 3 处 `明细表I2-2!A17` 属 I2 ⇒ 归 lane 2。SHALL 登记不修模板字节。

## Requirement 3：IC-14 —— `明细表I3-2` 四格金额错误走覆盖层

**User Story**：作为现场经理，商誉减值准备区的审定数合计不能恒为 0，否则我复核时看不出任何异常。

### Acceptance Criteria

1. WHEN 实施本 Requirement THEN SHALL 先 openpyxl 现算确认缺陷仍在：
   `明细表I3-2!AA23:AD23` **四格**公式都是 `=SUM(AA27:AA30)` 形态（各自列），
   而本 sheet 的数据区是 **R14:R22**、footer 是 **R23**。
2. WHEN 定位根因 THEN SHALL 登记两条实测事实：
   ① **R27~R29 是编制说明文本行**（不是数据行）
   ② **R30 超出 `max_row`（29）** ⇒ 引用区间完全落在数据区之外
   ⇒ **减值准备区审定数四列合计恒 0**。
3. 🔴 WHEN 修复 THEN SHALL **只走覆盖层**（`backend/wp_templates/` 字节不动，FC-5 的**第 5 个**例外；
   前四个是 `F2-26!J9` / `F5-7!G31` / `G5-2` 45 格 / `G5-1!B35`），
   覆盖层把四格改成 `=SUM(<同列>14:<同列>22)`。
4. 🔴 WHEN 编写判据 THEN 判据载荷 SHALL 是「**只有减值准备区有数、其他区为 0**」的合成载荷
   —— 若用「全区都有数」的载荷，修复前后合计都非 0，判据会假绿。
5. WHEN 验证 THEN SHALL 断言修复**前** `AA23:AD23` 四格求值 == 0、修复**后** == 数据区 R14:R22 的真实合计；
   且 SHALL 断言 R23 这一行的**其他列**（非 AA:AD）取值在修复前后**不变**（不得误伤）。
6. WHEN 登记 THEN SHALL 在契约 `known_template_quirks` 里写明本条为 `overlay_fixed`
   而非 `registered_not_fixed`（与 I6 的 `S19=SUM(S9:S18)` 文本列求和恒 0 是不同处置）。

## Requirement 4：I1 双区派生 + 四级表头 + sheet 命名陷阱

### Acceptance Criteria

1. WHEN 声明 `明细表I1-2` 几何 THEN SHALL 落实测值：**四级表头 R8-11** · 数据区 **R12-17** ·
   footer **R18（纯 SUM）** · 有效列 **47**（`max_column` 56） · 公式 **179** · merged **72**。
2. 🔴 WHEN 声明第二区 THEN SHALL 按 IC-19 登记 **R19-30 是派生区**，其行标签逐格引用
   `底稿目录!A9:A19`（11 类）⇒ 该区 SHALL 标 `derived`，**不接受用户改行标签**。
3. WHEN 声明 `明细表I3-2` 几何 THEN SHALL 落实测值：**四级表头 R10-13** · 数据区 **R14-22** ·
   footer **R23（🔴 行公式套用，不是纯 SUM）** · 有效列 **30**（`max_column` 30） · 公式 **133**。
   `footer_kind` SHALL 取 IC-13 新增的第四值 `row_formula_applied`，并加 `footer_convention_split`。
4. WHEN 声明 sheet 命名 THEN SHALL 按 IC-11 逐条落本 lane 命中的陷阱，**不得 strip 任何后缀**：

| 陷阱 | 实例 | entry |
|---|---|---|
| 审定表**无** `-1` 尾码 | `审定表I1` | I1 |
| 括号后缀 | `摊销测算表（不含减值）I1-10（剩余年限法）` | I1 |
| 附注披露名多「信息」二字 | `附注披露信息（上市公司）` / `附注披露信息（国有企业）` | I1 |
| 🔴 **全角连字符** | `参考－商誉减值测试示例`（非 hidden，104 行 / 114 公式） | I3 |
| hidden 参考页 | `市场平均收益率2017`（hidden，167 行） | I3 |

5. 🔴 WHEN 处理 I3 两张参考页 THEN SHALL 声明它们**不参与双向回写**（`excluded_from_sync`），
   理由逐条写明：`参考－商誉减值测试示例` 是示例数据非项目数据 · `市场平均收益率2017` 是 hidden 年份基准表；
   变异「把参考页纳入 sheet 白名单」SHALL 打红。
6. WHEN 校验 prefill THEN SHALL 断言 16 条 I mapping 里属 I1/I3 的部分**已正确用 sheet 全名**
   且 `items` 里 **`cells` 型 == 0**（IC-11 已裁，本 lane 只复核不改口径）。
7. WHEN 声明 `GT_Custom` THEN SHALL 登记 I1/I3 两册**都有** hidden `GT_Custom`（6 册全有）⇒
   SHALL 一并 `excluded_from_sync`。

## Requirement 5：载体 / 门控 / 删行 —— I1 与 I3 同族，只有 mount 数不同

### Acceptance Criteria

1. WHEN 声明载体 THEN SHALL 按 IC-2 落两行：I1 与 I3 **都是 `host_inline`**（写在宿主，
   `write_client=http`，读走 `host_inline_render_config_refetch`）；SHALL 反向断言
   两宿主 checklist GET == 0 · `bridge`/`ocr`/`notice`/`localStorage` 命中均 0。
2. 🔴 WHEN 声明 mount THEN SHALL 落 **I1 = 2 · I3 = 4**（I3 是全 I 循环唯一 mount≠2 的 entry）⇒
   I3 的 `force_component_type` 判据 SHALL 覆盖全部 4 个挂载点，变异「只验 1 个」SHALL 打红。
3. WHEN 声明 legacy OO 与视图开关 THEN SHALL 落实测值：
   `legacyOO` **I1 = 4 · I3 = 6（全 I 最多）** · `http_import` 各 1 · `isOoAvailable` 各 2 ·
   「仅结构化视图」各 1。SHALL 断言注册 adapter 后 `legacyOO` 分支**不再被走到**（不必删代码）。
4. WHEN 声明 TB 发布门 THEN SHALL 落实测位置：
   I1 = `composables/useI1Adjudication.ts`（`publishToTb` 定义 `#L659` / 导出 `#L1109`）
   + `i1/core/I1TabAdjudication.vue`（import `#L889` / 调用 `#L1119`）；
   I3 = `composables/useI3Adjudication.ts`（定义 `#L402` / 导出 `#L496`）
   + `i3/core/I3TabAdjudication.vue`（import `#L500` / 调用 `#L708`）。
5. 🔴 WHEN 验证发布门 THEN SHALL **复用已有** `composables/__tests__/iAdjudicationPublishGate.spec.ts`
   （已含 `buildI1()#L81` 与 `buildI3()#L86`），**不重造**；
   SHALL 只在其上补「注册 adapter 后仍走同一显式门」的断言。
6. WHEN 验证发布铁律 THEN SHALL 断言只走
   `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` + 必经二次确认，
   且 🔴 **禁**在 `watch` / `onMounted` / debounce 回调内发布；SHALL 复用平台既有 2 道 CI 守卫
   （`check_tb_writeback_no_direct_call` / `check_tb_publish_confirm_gate`），**不重造**。
7. WHEN 声明调整分录中央同步 THEN SHALL 落 I1 = `i1/core/I1TabAdjustment.vue`（`#L349` import /
   `#L391` 解构）· I3 = `i3/core/I3TabAdjustment.vue`（`#L420` / `#L456`）⇒
   roundtrip 期间 SHALL **冻结** `useAdjustmentCentralSync`（IC-2 已裁，本 lane 只实例化）。
8. 🔴 WHEN 声明删行语义 THEN SHALL 落 **I1/I3 都属 IC-7 的「下标族」**：
   `useI1Detail.ts#L623 removeRow(rowIndex: number)` · `useI3Detail.ts#L580 removeRow(rowIndex: number)`
   ⇒ 契约 `row_delete_api_kind = "index"`。
9. 🔴 THEREFORE 本 lane 是**唯一「下标族删行 + 位置化行身份」双重叠**的 lane：
   删行按下标、身份也曾按下标 ⇒ SHALL 加一条组合判据：
   「删中间一行后，剩余行的 `rowId` 全部不变」；修复前 SHALL 打红、修复后 SHALL 通过。
10. WHEN 声明 `derived_total_keys` THEN SHALL 现算（当前 I1 = **8** · I3 = **0**），
    🔴 **禁写死阈值**；SHALL 说明 I3 为 0 不是漏扫（IC-18 已裁 I3/I4/I5 皆 0）。
11. WHEN 声明裸 IF 中性化 THEN SHALL per-file 挂 `oo_crash_neutralization_fn`，
    计数现算（当前 I1 = **321，全 I 最高** · I3 = **63**）；变异「整册统一挂」SHALL 打红。
12. WHEN 声明 definedName THEN SHALL 按 IC-10 登记基线 **I1 = 0 · I3 = 0** 并断言**不增长**
    （🔴 不得照抄 H 的「断言全 0」口径 —— 那在 I4/I5 会假红，本 lane 虽都是 0 也须用同一基线口径）。
13. WHEN 声明 UUID 落位 THEN SHALL 用「有效列 + 1」规则：I1 = **48**（有效 47）· I3 = **31**（有效 30）；
    🔴 不得放到 `max_column` 之后（I1 的 56 / I3 的 30）。

## Requirement 6：跨 entry / 跨 lane / 跨循环协调

### Acceptance Criteria

1. 🔴 WHEN 冻结键 THEN SHALL 登记 **I1 跨 entry 消费 I2 的主表键**：
   `composables/useI1AdditionCheck.ts#L250-251` 读 `allResponses.get('I2-2-rows')?.remark`
   并回落 `?.conclusion` ⇒ **`I2-2-rows` 对 lane 2 是冻结键**，lane 2 改名 SHALL 打红。
2. WHEN 登记该消费边 THEN SHALL 同时登记它**读两列**（`remark` 优先、`conclusion` 兜底）⇒
   若 lane 2 把 I2 的 payload mode 从 `remark_only` 改成别的，本消费边 SHALL 受影响；
   两个 lane SHALL 在同一张跨引用表上对账（表在地基 spec IC-17，本 lane 不复述）。
3. WHEN 声明 I1 被下游消费 THEN SHALL 登记 `expenseWpI1AmortPull.ts` 与
   `i1AmortAllocCounterpartPull.ts` 消费 **`I6-2-detail-rows`**（不是 I1 自己的键）⇒
   这两条是 **I1 读 I6**，SHALL 断言 canary（I6）注册后这两条仍取到同一载荷。
4. 🔴 WHEN 回归 THEN SHALL 断言 **H1 pilot golden digest 不变**：
   `h1DepAllocCounterpartPull.ts` 也消费 `I6-2-detail-rows`，本 lane 任何改动不得触及它。
5. WHEN 声明 wp_index THEN SHALL 按 IC-12 断言契约 `source_ref` **不含任何 wp_index 来源字段**；
   SHALL 登记本 lane 命中的两套编号体系例（`I1-3` / `I1-4` / `I1-5` / `I3-3` 子码与模板尾码不对应）。
6. WHEN 声明同源引用 THEN SHALL 只**引用**已有跨循环规则、不重写：
   月度矩阵 → F5-2 `months/0` · 减值/可回收金额 → H2/H4 的 `useH2Impairment` 族 · 稳定 key → H7 SK-1。

## Requirement 7：零回归 + 不复述 IC + 证据

### Acceptance Criteria

1. WHEN 实施任一 Task THEN SHALL 先**现算**零回归基线（契约目录 `*.json` 个数与文件名集合 ·
   `register_from_manifest()` 已注册集合 · `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS` 成员），
   🔴 **禁写死个数**（地基 spec Task 3 现算为契约 17 个 / 注册集 `{d2,d4,g7,h1}`；canary 注册后会变）。
2. 🔴 WHEN 本 spec 引用 IC-1~IC-20 THEN SHALL **只写编号 + 一句话用途**，正文一律不抄；
   交付后 SHALL 用脚本核「本 spec 的 `IC-\d+` 引用集合 ⊆ 地基 spec 的 `### IC-\d+` 定义集合」。
3. WHEN 写「N 处」类表述 THEN N SHALL 与同段列举项数**逐条相等**（F1 / H lane 1 都踩过此坑）。
4. WHEN 产出证据 THEN SHALL 落 `evidence/` 下逐 Task 一份，含 openpyxl 真读片段与 grep 原文行号；
   SHALL 断言全文无 U+FFFD。
5. WHEN 迁移 THEN SHALL 只走 `register_from_manifest()`，🔴 **禁手改 manifest 文件**（IC-1）。

## 阻塞项

**平台级（全循环共有，只标 `[ ]*` 不承诺）**：
BP-1 instrumentation candidate · BP-2 人工审核 per-entry contract · BP-3 approved authority model +
non-null bundle · BP-4 真 OnlyOffice 9.4 required scenario set。

**本 lane 专属**：

| BP / 事项 | 状态 | 说明 |
|---|---|---|
| **BP-6** | 本 lane 交付 | 8 sites 分治修复（Requirement 1） |
| **BP-7** 的**修法** | `[ ]*` 业务确认 | 源模板 11 类 vs `note_template_soe.json` 谁权威 · `探矿权` 去留 |
| 位置化**标签** 3 处 | `[ ]*` 业务确认 | 改动影响用户可见文案 |
| 源模板真源断链 2 处（I1） | 登记不修 | 不改模板字节 |
| I3 两张参考页 | `excluded_from_sync` | 示例数据 / hidden 年份基准 |
| roundtrip 载荷 | `[ ]*` 依赖 BP-4 | 真库两键皆空 ⇒ 只能合成载荷，标 `synthetic_payload_no_live_db_baseline` |
