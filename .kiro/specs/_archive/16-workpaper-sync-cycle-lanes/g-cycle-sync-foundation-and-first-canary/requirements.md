# Requirements Document

## Introduction

本 spec 是 **G 循环（投资）17 条 Excel 独立 entry** 从 legacy 假双向接成真双向的**地基 spec**：
承载 G 循环共同裁决 **GC-1 ~ GC-10**、四条 G 专属前置的处置边界、以及**首张 canary（G2 应收利息）**。
它是 umbrella `workpaper-html-onlyoffice-bidirectional-writeback-closure` **Task 49** 的下游实施 spec
（Task 49 只交付 step 1~4 与 step 11 的冻结 slice，不接双向）。

上游沿用 F 循环共同裁决 **FC-1 ~ FC-13**（`f1-sync-coverage-and-first-canary/design.md`）；
🔴 其中 **FC-3 / FC-8 / FC-11 在 G 循环不成立或不命中**，逐条改写见 design §FC 适用性重裁。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`GF-P{N}`**（G Foundation）。

### 三份下游 lane spec（本 spec 是它们的共同前置）

| lane spec | 覆盖 entry | 数 |
|---|---|---|
| `g4-g6-shared-workbook-three-entry-lanes` | G4-main / G4-sppi / G4-ecl / G6-main / G6-sppi / G6-ecl | 6 |
| `g5-nested-sections-and-template-defects` | G5 | 1 |
| `g-cycle-single-region-detail-lanes` | G1 / G2 / G3 / G8 / G9 / G10 / G11 / G12 / G13 / G14 | 10 |

canary（G2）在本 spec 内打通；其余 9 条单区 lane 由 `g-cycle-single-region-detail-lanes` 承接。

🔴 **另有第五份后置 spec `g-cycle-adjudication-sheets-coverage`**（13 张 `审定表G{N}-1`）——
裁决 GF-H5：审定表的三条共性（全部命中裸 IF / 公式密度极高 G1-1 504f / TB 发布门含 GC-9 三家缺口）
大于其所属科目的差异 ⇒ 统一后置，本 spec 与三份 lane 均不含。

### 范围与排除（slice `slice_scope` 逐条实测）

**17 条 entry** = G 码 xlsx `independent_entry=true` 共 20 条 − G7 的 3 条。
排除三类，均有 slice 原文依据：

| 排除项 | 原因 | 归属 |
|---|---|---|
| G7 三条（`gt-g7-long-term-equity-main` / `-equity-method` / `-equity-subsidiary`，pattern G7L/G7E/G7E） | 任务正文明令「除 G7 外」 | 已归档 spec `g7-column-alignment-and-extraction-closure`(24/24) + 本 umbrella 的 G7 pilot |
| G0 投资循环函证（G0 / G0A / G0-1~G0-7） | 走跨循环共享 confirmation-* 组件族，纯 HTML 无 `GtOnlyOfficeSheet` 挂载点 ⇒ 不在 186 条 entry 里 | Task 57 |
| 不可达旧桩 `xlsx/gt-g6-other-bond-ecl`（`GtG6OtherBondEcl.vue`） | `independent_entry=false` / `capability='unreachable'` / `migration_state='unreachable_pending_delete'` / `inbound_reference_count=0`；实测该宿主连 `GtEntrySyncCapabilityNotice` 都没挂（`notice=0`，其余 17 个都是 3） | Task 66 生成计划 / Task 72 Stage B 删除 |

### 17 条 entry 现状（slice `independent_entries` 逐条实测，2026-09-26 复核）

17 条**全部**：`capability=null` · `capability_target="bidirectional"` ·
`capability_verdict_stage="pipeline_entry_pending_definition_delivery"` · `migration_state=legacy_fake_bidirectional` ·
`adapter_id=None` · `html_counterpart_verdict="exists"` · `mount_count=2`（G6-sppi 除外，见 lane spec）。

| 事实 | 实测 |
|---|---|
| provider | ❌ 零 `phase5_g*.py`（🔴 G7 走的是 `pilot_g7_two_level_dynamic.py`，是 **`pilot_*` 范式**不是 `phase5_*`） |
| 契约 | 17 条 entry 契约数 **0**；契约目录里唯一属 G 的是已排除的 `g7.soe_subsidiary_disclosure.json` |
| published representation | 0 |
| 宿主接桥 | 17 个 `GtG*.vue` 逐个实测 **`useWorkpaperSyncBridge` = 0**、`GtOnlyOfficeSheet` = 4、`GtEntrySyncCapabilityNotice` = 3。全仓唯一带 sync 桥的 G 宿主是 `GtG7LongTermEquityMain.vue` |
| 公式管理预设 | ✅ 全部生效（`convert_prefill_presets()` 现算：G1=27 / G2=11 / G3=11 / G4=20 / G5=14 / G6=16 / G8=14 / G9=11 / G10=11 / G11=16 / G12=10 / G13=14 / G14=13）—— 与 F5 的 **0** 形成对比 |
| 真库载荷 | ✅ G1~G14 **每个科目都有**（G5 12,952+2,844 B 最多；G3 仅 12 B 最少）—— 与 F 循环「F5 全零」形成对比 |
| TB 发布门 | ✅ 10 家已接 `publishToTb`；🔴 **G1 / G4-main / G6-main 三家未接**（见 GC-9） |
| 调整分录 | ✅ 13 个 `G{N}TabAdjustment.vue` 各 `useAdjustmentCentralSync=3` ⇒ 13 张全是 hub（FC-6） |
| OCR | ✅ 全仓 **零命中** ⇒ FC-8 在 G 不适用 |

### 模板字节锚（slice `authoritative_templates.files[]`，15 文件 **全部**在 `_index.json`）

| entry | 模板 | sha256 | 字节 |
|---|---|---|---|
| G1 | `G/G1 交易性金融资产.xlsx` | `eba510b3b7cef68a…` | 157,253 |
| G2 | `G/G2 应收利息.xlsx` | `c7563e85a3ebffb7…` | 99,479 |
| G3 | `G/G3 应收股利.xlsx` | `02a5727230a7e2b1…` | 480,411 |
| **G4-main / -sppi / -ecl** | `G/G4 债权投资.xlsx` | `da3a3480d37a4b95…` | 999,788 |
| G5 | `G/G5 长期应收款.xlsx` | `c59bba69789eba3f…` | 398,912 |
| **G6-main / -sppi / -ecl** | `G/G6 其他债权投资.xlsx` | `63bf38c797d4612e…` | 981,008 |
| G8 | `G/G8 其他权益工具投资.xlsx` | `5c8d3de7ee60ffef…` | 450,079 |
| G9 | `G/G9 其他非流动金融资产.xlsx` | `264322c0ed1b4bf6…` | 88,636 |
| G10 | `G/G10 交易性金融负债.xlsx` | `3afd5131f3783c01…` | 99,458 |
| G11 | `G/G11 投资收益.xlsx` | `a1b1d87f29e2dc63…` | 75,600 |
| G12 | `G/G12 净敞口套期收益.xlsx` | `6645caf0fdfadf38…` | 79,999 |
| G13 | `G/G13 公允价值变动收益.xlsx` | `fd5e5e9eeca7b392…` | 58,717 |
| G14 | `G/G14 信用减值损失.xlsx` | `5ca770907cfd3723…` | 60,094 |

🔴 `belongs_to_entries` 是**复数**字段（FD-3）：13 张 owner 模板覆盖 17 条 entry，单射不成立。
另 G0 `9d9820aba2761c1f…` / G7 `6bf9e2ebcdf50a1c…` 的 `belongs_to_entry=null` + `excluded_reason`，
**漏登会让「登记集合 == 磁盘实况」判据失效** ⇒ 本 spec 的判据沿用该双向锁。

### G 循环两条「实测后判定缺陷不存在」（虚报与漏报同罪，不得凭形态相似登记 BP）

| 候选缺陷 | G 循环裁定 | 证据 |
|---|---|---|
| 整册码回落打开错工作簿（D4/F2 同型） | **`not_present_in_g_cycle`** | 13 个整册码 + 8 个子码逐一实测 `find_template_file` / `_any` / `find_all`，全部正确；根因 G 目录每 wp_code 在 `_index.json` 恰 1 条命中，无 F2 那种「关键词 + 索引顺序决胜」的竞争 |
| 磁盘有、索引无的不可达冗余合册（`D4收入底稿.xlsx` / `F2存货.xlsx` 同型） | **`not_present_in_g_cycle`** | 磁盘 15 文件 vs 索引 15 条 G 项，差集为空 |

⇒ 本 spec **不得**为「对齐 F 的 BP 清单」而登记这两条；反之 SHALL 有判据锁住「它们确实不存在」（GF-P2）。

### 🔴 红基线（实测，非本 spec 引入）

**RG-1 · 三张 16384 列表：UUID 列无处可放**

`债权投资三阶段划分G4-9`(61r) / `长期应收款三阶段划分G5-9`(58r) / `其他债权投资三阶段划分G6-11`(61r)
的 `max_column` 实测 **16384**（= XFD，Excel 绝对上限），而三张的**有效内容列只有 11**。
instrumentation 的「UUID 列放 `max_col+1`」策略在此**结构上不可能**满足。三张全是「三阶段划分」表，
其中 G4-9 / G6-11 正是两个 ECL entry 的主受管表。

**RG-2 · 两个 ECL 主表是转置形态，不是行表**

`G4-9` / `G6-11` 的 R9（G6-11 是 R10）表头为 `A:需要考虑的信息 | B:说明 | G:投资1： | H:投资2： | I:投资3： | J:投资X：`
⇒ **列是投资项目、行是考虑因素**，且各含**三块**（「分析结论」锚行 G4-9 R24/R32/R46 · G6-11 R25/R33/R47）。
按 FC-4 三元组，用 `RowTableSheetSpec` 声明会把「投资项目」当成列而非行 ⇒ 投影恒空。

**RG-3 · G5 两处模板真实金额错误（FC-5 的第三、第四个例外）**

```
G5-2!D40  = =D18+D25+D39      🔴 段（一）四个小计 18/25/32/39 只加三个，漏 R32
G5-2!D72  = =D50+D57+D71      🔴 段（二）漏 R64
G5-2!D104 = …                 🔴 段（三）漏 R96
G5-1!B35  = =B9-B225          🔴 越界引用（审定表G5-1 仅 87 行）⇒ 恒等于 B9
```
漏加模式**三段一致（都漏第三个子区）** ⇒ 复制粘贴错误；影响 D~R 共 15 列 × 3 段 = **45 格**。
触类旁通扫全 G 目录：本 spec 范围内**仅 G5 命中**；另 `G7 明细表G7-2` 36 格 + `G0-1!E24` 1 格均属已排除范围
（🔴 G7 spec 已 24/24 归档却带着同型缺陷，登记见 design §顺带发现）。

**RG-4 · 13 册全部带裸 `IF(` ⇒ OO 加载期崩溃风险**

按 `g7_oo_crash_if_neutralize._BARE_IF_CALL`（`(?<![A-Za-z0-9_.])IF\s*\(`，**真实正则**，含
`IFERROR(IF(...))` 内层）实测：G1 141 · G2 40 · G3 36 · G4 186 · G5 122 · G6 192 · G8 24 · G9 84 ·
G10 56 · G11 114 · G12 14 · G13 22 · G14 22（G7 2325 / G0 16）。
**13 张审定表全部命中**（G1-1 126 / G5-1 122 / G6-1 96 / G9-1 84 / G10-1 56 / G4-1 54 / G11-1 38 /
G2-1 38 / G3-1 36 / G8-1 24 / G13-1 22 / G14-1 22 / G12-1 14）；主受管表里 **G11-2 命中 44 格、G4-2 命中 2 格**。
中性化是 **per-file**（整册就地改写），缓解件已存在且是声明式（`StoreMergePlan.oo_crash_neutralization_fn`）。

**RG-5 · prefill 两块 sheet 名错位 + G 循环缺 sheet 存在性守卫**

`[169] wp=G13 sheet='明细分析表G13-2'`（模板真名 **`明细表G13-2`**）· `[170] wp=G14 sheet='明细分析表G14-2'`
（真名 **`明细表G14-2`**）—— 照抄了 G11 的「明细分析表」前缀（G11 的 `明细分析表G11-2` 才是真名，已核）。
两块共 4+3=**7 条**预设指向不存在的 sheet ⇒ 写 xlsx 的预填消费方找不到 sheet。
🔴 根因是**守卫缺失**：D / E1 / F / I / J / K / L / H0 **八个**循环都有「块 sheet ∈ 模板真实 tab」断言，
而 `backend/tests/four_table/test_g_cycle_formula_presets.py`（7,070 B）只有 Property 8 科目码 /
Property 9 损益口径 / Property 10 披露块覆盖 / `KNOWN_BAD_CODES` 回归，**没有该断言** ⇒ 错名逃检。

**RG-6 · G1 / G4-main / G6-main 三家审定表未接 TB 显式发布门**

`publishToTb` 实测：10 家有（G2/G3/G5/G8/G9/G10/G11/G12/G13/G14，四层齐备：`useG{N}Adjudication.ts` +
`useG{N}FormData.ts` + `G{N}TabAdjudication.vue` + 宿主），且 `tb-writeback-explicit-publish-gate` **Task 12**
的「移除 `g{n}:writeback-trial-balance` 监听器」注释在 G2/G3/G9/G10/G13 宿主逐字可见。
🔴 三家为 **0**：`useG1Adjudication.ts`(673 行, `trial-balance`×2 / `writeback`×5，另有专属测试
`g1AdjudicationWriteback.spec.ts`) · `useG4MainAdjudication.ts`(738 行, ×1/×3) · `useG6MainAdjudication.ts`(784 行, ×1/×2)。
三家都是资产科目（G1 1101 / G4 1504 / G6 1506）本应回写 TB。

**RG-7 · TB 键名嵌的科目码与真码不一致，且一条注释本身是错的**

| 位置 | 键名 | 键名内科目码 | 真码（`test_g_cycle_formula_presets.G_ACCOUNT_CODES`） | 备注 |
|---|---|---|---|---|
| `useG4MainAdjudication.ts:37` | `G4-1-adj-tb-1501` | 1501 | **1504** | 1501 在 `KNOWN_BAD_CODES['G4']` 里 |
| `useG6MainAdjudication.ts:53` | `G6-1-adj-tb-1503` | 1503 | **1506** | 🔴 该行注释写「科目已纠正为 **1505**」—— 1505 也在 `KNOWN_BAD_CODES['G6']=['1505','1503']` 里，**注释本身是错的** |

键名是稳定标识符**不得改**（注释已说明「改了会丢已有项目的 TB 核对数据」），但契约声明 TB 键时
**不得按科目码推演键名**。

**RG-8 · 行级 mask 差异三处 + 布尔校验列三处**

行级 mask（同 F3-H4 族，矩形 mask 表达不了）：`G1-2` 区① T 列跨表引 `公允价值测试表G1-6` 而区②③ T 无公式 ·
`G6-5` R9/R10 有 D 列公式而 R11+ 无 · `G8-2` R11/R12/R13 三行公式集互不相同（R11 有 R+T、R12 有 R 无 T、
R13 有 T 无 R；`M` 列区间 R11 `SUM(I11:L11)` vs R12 `SUM(I12:K12)`）。
布尔校验列（求值为 TRUE/FALSE）：`G12-2!G=D9=SUM(E9:F9)` · `G13-2!K=J11=D11` · `G14-2!L=D11=K11`。

**RG-9 · BP-10 / FD-5：80 个 item_id 字面量在 2+ 模块各写一份**

slice 冻结口径（`const X = '…'` / `KEY: '…'` 的**声明**，不含消费方引用）：共 **80** 个，最严重
`G1-2-rows` 8 处 / `G10-detail-rows` 6 / `G11-adj-rows` 6 / `G2-1-rows` 5 / `G2-2-detail-rows` 5。
G6 做对了（`g6CrossHelpers.G6_11_ROWS_KEY = G6_ITEM_IDS.G6_11_ROWS` 是**派生别名**）；
G4 有 storage contract 却仍在 `g4CrossHelpers` 重复 4 条字面量。
`must_fix_before` = 为任一 G entry 发布 per-entry contract（step 6）之前。

**RG-10 · 真库三个 TB 回写记录键在前端源码按字面量搜不到**

真库有 `G11-adj-tb-writeback`(46 B) / `G9-adj-tb-writeback`(40) / `G8-adj-tb-writeback`(40) 三行载荷，
但前端源码按字面量 grep **零命中** ⇒ 模板化拼接或已退役键（FC-4 的模板化拼接陷阱）。

## Glossary

沿用 F1 spec Glossary；新增：

| 术语 | 含义 |
|------|------|
| `pilot_*` 范式 | G7 / D2 / H1 / B60 四个先导 entry 用的旧式 provider 形态（`PILOT_ADAPTER_ID`），与 D/E/F 的声明式 `phase5_*` 范式并存；G7 是 G 循环唯一已注册 adapter 的 entry |
| 一册多 entry | 一份权威 xlsx 按 sheet 段拆给多个宿主（G4/G6 各 3 条），`belongs_to_entries` 复数表达；不是 D4 那种 parent_duplicate 子入口 |
| 转置形态 | 列是业务实体、行是属性的 sheet（G4-9 / G6-11：列 = 投资1..X）；须 `TransposedSheetSpec`（D4-29 先例） |
| 裸 `IF(` | OO 9.4 在文档加载完成前跑依赖图计算，`cIF.Calculate` 读 `tocBool` 抛 TypeError ⇒ 前端收 `editor_error_-82`；不是「OO 不可用」而是「这份文档让 OO 崩了」 |
| payload 列四形态 | `remark_only` / `conclusion_only` / `conclusion_canonical_remark_mirror` / `dual_write_remark_and_conclusion`（FD-1）；决定契约 `json_pointer` 指哪一列 |
| null 占位子形态 | 写入点显式把另一列写成 `null`（全 slice 仅 G2），会骗过「窗口里有没有 `conclusion:` token」式探针 |

## Requirements

### Requirement 1: G 循环共同裁决 GC-1 ~ GC-10 落地为可复核声明

**User Story:** 作为下游 lane spec 的实施者，我希望 G 循环的共性裁决只做一次并有判据锁死，
不要在四份 spec 里各裁一遍互相漂移。

#### Acceptance Criteria

1. WHEN 本 spec 交付 THEN design SHALL 承载 **GC-1 ~ GC-10** 完整裁决正文，三份 lane spec 只引用不复述。
2. WHEN 引用上游 F 循环裁决 THEN SHALL 逐条给出 **FC-1~FC-13 在 G 的适用性重裁**，且
   🔴 **FC-3 / FC-8 / FC-11 三条 SHALL 明确标为「在 G 不成立或不命中」**并给出替代裁决（GC-1 / 零 OCR / RG-5）。
3. WHEN 声明任一 G entry 的阻塞项 THEN SHALL 逐元素取 slice `capability_target_blocked_by`（FC-13），
   **不得**跨 entry 套用；判据 SHALL 覆盖 17 条全集。
4. WHEN 登记「缺陷不存在」的两条结论（整册码回落 / 不可达合册）THEN SHALL 现算而非读 slice 快照，
   且变异「往 G 目录塞一本未索引的册子」SHALL 打红。

### Requirement 2: 四条 G 专属前置的处置边界

**User Story:** 作为维护者，我要清楚哪些前置本 spec 修、哪些只立守卫、哪些明确不修并说明归属。

#### Acceptance Criteria

1. 🔴 WHEN 处置 **BP-5**（G1 sheet 标签表 18 条里 5 条指向不存在的 sheet）THEN 本 spec SHALL 修：
   `g1SheetLabels.G1_SHEET_LABEL_MAP` 的 5 条错名改为模板真名（含 `交易性金融资产实质性程序表G1A `
   **尾部空格**必须保留 —— 空格是源模板事实）；判据 SHALL 断言 18/18 全部 ∈ 模板真实 tab 集合。
   `must_fix_before` 原文含「也在为它发布 contract 之前 —— 契约的 source_ref 要写 sheet 名」。
2. 🔴 WHEN 处置 **BP-8**（G4/G6 各一册服务 3 entry 且共用 wp_code_pattern `G4B`/`G6O`）THEN 本 spec
   SHALL 只交付**共性裁决 GC-1 + 守卫**（representation entry pointer 必须按 `entry_id` 不按 wp_code），
   具体六条 entry 的实施归 `g4-g6-shared-workbook-three-entry-lanes`；判据 SHALL 构造「两条同码 entry 先后
   发布 representation」并证明 pointer 不互顶。
3. WHEN 处置 **BP-7**（G6-sppi 行身份退化成数组下标）THEN 本 spec **不修**（归 lane spec，因为它只卡
   `gt-g6-other-bond-sppi` 一条），但 SHALL 在 GC-7 里登记其形态与 `must_fix_before`。
4. 🔴 WHEN 处置 **BP-9**（`useG1DualMode.ts` 被 G1 与 E1 **两个循环**共用）THEN 本 spec SHALL：
   ①登记该跨循环共用事实与 E 循环 deletion plan 的解锁条件原文（「Task 49 完成 G1 entry 的裁决与迁移」）
   ②判据 SHALL 断言本 spec **不删**该文件（删它会打断 E1）③G1 接桥时 SHALL 不改其对 E1 的行为。
5. WHEN 处置 **BP-6**（manifest `capability`/`html_store` 是 overlay 组件级默认值）THEN 照 FC-12：
   断言「manifest 值与 slice 重裁值不一致」这一事实成立，**不得**为对齐而改 overlay / manifest。
   🔴 SHALL 另加一条守卫：**不得**复制 BP-9 登记的那种论证方式（把 overlay 默认值当裁决依据）。
6. WHEN 处置 **BP-11**（不可达旧桩未删）THEN 本 spec **不删**（归 Task 66/72），但 SHALL 登记其
   `notice=0` 的实测事实并断言它不进任何受管清单。

### Requirement 3: OO 加载期裸 IF 崩溃 —— 13 册全命中的共性前置（GC-2）

**User Story:** 作为审计助理，我不希望点「在线编辑」后拿到 `editor_error_-82` 而不知所以。

#### Acceptance Criteria

1. WHEN 任一 G entry 走 materialize / verify THEN SHALL 经 `StoreMergePlan.oo_crash_neutralization_fn`
   声明式挂载中性化（复用 `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas`），
   **不得**在 `adapters/excel.py` 新增 `if adapter_id == …` 字面量分支（Task 13 已收敛掉两处）。
2. WHEN 统计裸 IF THEN SHALL 用 `_BARE_IF_CALL` 的**真实正则**现算，**不得**用「`IF(` 后跟 `IS*`/`AND`/`OR`」
   这类启发式（实测该启发式会低估：G11-2 真实 44 格 vs 启发式漏报）。
3. 🔴 WHEN 断言某册「不需要中性化」THEN SHALL 有**真 OO 加载**证据（BP-4），不得以「裸 IF 数少」推断；
   在 BP-4 未交付前，13 册 SHALL **一律挂**中性化并如实登记为「按 per-file 保守策略挂载」。
4. WHEN 中性化生效 THEN 判据 SHALL 证明 before/after 公式集一致、`verify_unmanaged_regions` 不报漂移
   （中性化在 substrate **副本**上做，不改权威模板字节）。

### Requirement 4: 首张 canary —— G2 应收利息从零打通真双向

**User Story:** 作为审计助理，我希望 G2 明细表在 OO 里改一格、切回结构化视图能看到同一个数。

#### Acceptance Criteria

1. WHEN 选定首张 canary THEN 它 SHALL 是 **`明细表G2-2`**（32r×16c / 34 公式 / **单级表头 R9** /
   数据 **R10-15** / footer **R16「合计」`=SUM(C10:C15)`** / 键 `G2-2-detail-rows` / 行身份 `id`
   （`generated_prefixed_opaque_string`，`useG2Detail.ts#L146`）/ 公式列仅 **E,H,J**
   （`E=C+D` · `H=C+F-G` · `J=H+I`）/ 有效列 13（A-M））—— 理由见 design 裁决 GF-H1。
2. WHEN 建 provider THEN SHALL 新建 `phase5_g2_interest_receivable.py`（**`phase5_*` 范式，不照 G7 的 `pilot_*`**）；
   `assert_entry_selectable(*, resolution, manifest=None)` 照 D3 同签名（`resolution` 必填、无关闭开关、真 manifest 真调）；
   `WP_CODES={"G2I"}`（幻影码，FC-2）；`build_matcher()` 带 `document_type="xlsx"`；
   `build_registration` 照 `phase5_d3_prepaid_receipts.py:830` 并有**真构造**判据；
   `TEMPLATE_SHA256="c7563e85a3ebffb7…"`（逐字取 slice，完整 64 位）。
3. 🔴 WHEN 声明 payload 列 THEN G2 是 `remark_only` **且带 null 占位子形态**
   （`useG2Detail.ts#L515-L519` 写 `{item_id, conclusion: null, remark: JSON.stringify(rows)}`）⇒
   契约 `json_pointer` SHALL 指 `remark`；判据 SHALL 证明**剔除字面 null 占位后**判定仍为 `remark_only`
   （Task 49 首轮守卫正是因不剔占位而把 G2 误判成 dual_write）。
4. WHEN 声明 `store_item_id` THEN SHALL 取 `G2-2-detail-rows`；变异 `G2-2-rows`（不存在）SHALL 投影恒空必红。
   🔴 该键在 slice 冻结口径下有 **5 处重复声明**（RG-9）⇒ 发布契约前 SHALL 收敛为单一真源。
5. WHEN 契约发布 THEN 走完整五环（生成器 → `assert_contract_file_matches_source` → approved bundle →
   published representation → entry_state → `register_from_manifest()`）；第③环缺供给时如实 `upstream_gap`（BP-1~3）。
6. WHEN adapter 注册成功 THEN manifest `migration_state` SHALL 变为 `adapter_registered`。
7. WHEN 宿主接桥 THEN `GtG2InterestReceivable.vue` SHALL 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，
   保留 legacy `GtOnlyOfficeSheet` 给未迁移 sheet；🔴 G2 是 G 循环**唯一**包共享基座
   `useWorkpaperEntryDualMode.ts` 的（`useG2DualMode.ts` 59 行）⇒ 接桥 SHALL 保留基座、不内联展开。
8. WHEN 真栈验收 THEN SHALL 达三谓词并留 DB 证据；真库 `G2-2-detail-rows` 已有 **475 B** 真实载荷
   ⇒ **不需要** seed（与 F5 相反），但 SHALL 断言验收用的是真实载荷而非空表往返。
9. WHEN G2 的 TB 发布门 THEN 它已接 `publishToTb`（科目 **1132**、余额口径，`useG2Adjudication.ts`）⇒
   FC-9 红线：sync 路径对 `trial_balance` 写次数为 **0**；变异「sync 回写里调 publishToTb」SHALL 必红。
   🔴 G2 的 TB 键有 legacy 双键（`ITEM_ID_TB='G2-1-tb'` + `ITEM_ID_TB_LEGACY='G2-1-adj-tb-1132'`）⇒
   契约只声明主键，legacy 读回退不得删。

### Requirement 5: prefill sheet 名修复 + 补齐 G 循环缺失的守卫（GC-8）

**User Story:** 作为审计助理，我希望公式管理页看到的预设在预填时真的写进对应 sheet。

#### Acceptance Criteria

1. 🔴 WHEN 修 prefill（红基线 RG-5）THEN SHALL 把块 `[169]` 的 sheet 名改为 **`明细表G13-2`**、
   块 `[170]` 改为 **`明细表G14-2`**（模板真名，已按值核 G13/G14 册内含「明细」的 tab 只有这一个）。
2. 🔴 WHEN 补守卫 THEN SHALL 给 `backend/tests/four_table/test_g_cycle_formula_presets.py` 增加
   「每个 G 块的 `sheet` ∈ 对应源 xlsx 真实 tab 名」断言 —— 口径照既有八循环之一（建议
   `test_i_cycle_formula_presets.test_sheet_exists_in_template`），**不新造第二套口径**；
   判据 SHALL 证明该断言在修复前**必红**、修复后转绿。
3. WHEN 断言 tab 名 THEN SHALL **保留源模板的空格事实**（`交易性金融资产实质性程序表G1A ` 尾部空格 /
   `信用减值损失审计程序表G14A -修订前` 名中空格），不得 strip 后比较。
4. WHEN 修复完成 THEN `convert_prefill_presets()` 的 G 各 key 计数 SHALL 不减少（现值 G13=14 / G14=13）。

### Requirement 6: G1 / G4-main / G6-main 三家 TB 发布门缺口裁决（GC-9）

**User Story:** 作为质控，我要确认受管后不会有第二条路把数写进试算表。

#### Acceptance Criteria

1. 🔴 WHEN 三家（G1 / G4-main / G6-main）任一受管 THEN SHALL 先出**书面裁决**：其 `useG*Adjudication.ts` 里
   残留的 `trial-balance` / `writeback` 引用是**活路径**还是注释/类型残留 —— 逐处按值核，不得推断。
2. WHERE 判定为活路径 THE 本 spec SHALL **不直接改造**（改 TB 回写路径属 `tb-writeback-explicit-publish-gate`
   spec 的作业面，其 Task 12 已覆盖另 10 家），但 SHALL ①登记为该 spec 的遗漏项并给出 entry 清单
   ②在三家受管前立硬门：`capability_target_blocked_by` 追加一条本地前置，判据必红直到裁决落地。
3. WHERE 判定为死代码 THE SHALL 登记证据（零消费方）并允许受管继续。
4. 🔴 WHEN 声明任一 G entry 的 TB 键 THEN SHALL **按值取键名**，不得按科目码推演（红基线 RG-7：
   `G4-1-adj-tb-1501` 的真码是 1504、`G6-1-adj-tb-1503` 的真码是 1506）；
   SHALL 同时修正 `useG6MainAdjudication.ts:53` 那条**把真码写成 1505** 的错注释（1505 在 `KNOWN_BAD_CODES` 里）。
5. WHEN 损益类 entry（G11 / G12 / G13 / G14）受管 THEN 其 TB 口径 SHALL 是**本期发生额**不是期末余额
   （`test_g_cycle_formula_presets.PL_CYCLES` 已冻结该集合）。

### Requirement 7: 零回归与登记点

**User Story:** 作为维护者，我不希望新增 G provider 打翻既有循环的门禁。

#### Acceptance Criteria

1. 🔴 WHEN G provider 纳入零回归门 THEN 既有 contract golden digest SHALL **现算基线**而非写死数字 ——
   实测 `check_sync_provider_golden_digest.PROVIDERS` 已含 b60/d1/d2/d3/d4/d5/d6/d7/e1(+g7/h1)、
   契约目录现 **12** 个 json（并发会话本轮交付了 d1/d3/d5/d6/d7/e1）⇒ 写死数字会在下次交付后立刻 stale。
2. WHEN 登记新 provider THEN SHALL 同步：`DELIVERED_PER_ENTRY_CONTRACTS` · `_ALLOWED_PROVIDER_MODULES` ·
   `store_item_registry` plan（含 `oo_crash_neutralization_fn`）· `check_sync_provider_golden_digest.PROVIDERS` ·
   wp_code 裁决文件 · overlay + 重生 manifest。
3. WHEN 复用既有 G 产物 THEN SHALL **不重造**：守卫 `backend/tests/workpaper_sync/test_task49_g_cycle_migration.py`
   （179 KB）· 变异脚本 `backend/scripts/diagnose/mutate_task49_g_cycle_migration_guards.py` ·
   删除清册 `backend/data/workpaper_sync_g_cycle_deletion_plan.json`（51 KB）；新判据 SHALL 加在既有文件里或
   显式说明为何另起文件。
4. WHEN 未接 sheet 切在线编辑 THEN SHALL 保持 legacy 并显式登记为假双向（AC 1.4 的 notice 已在 17 宿主挂好）。

### 不在本 spec 范围

- G7 三条 entry（已归档 spec + pilot）· G0 函证（Task 57）· 不可达旧桩删除（Task 66/72）。
- 六条 G4/G6 entry 的实施（`g4-g6-shared-workbook-three-entry-lanes`）；G5（`g5-nested-sections-and-template-defects`）；
  除 G2 外 9 条单区 entry（`g-cycle-single-region-detail-lanes`）。
- 13 张审定表（G1-1~G14-1）与 13 张调整分录汇总表（FC-6 默认 `single_html`）的接入 —— 各 lane spec 只做核。
- 平台级供给 BP-1~BP-4（instrumentation candidate / 人工审核契约 / approved bundle / 真 OO 场景集）。
- 模板覆盖层本身；G5 两处模板缺陷的修复动作（归 G5 lane spec，本 spec 只承载 FC-5 例外的裁决结构）。
- `tb-writeback-explicit-publish-gate` 对三家缺口的**改造**（本 spec 只裁决与立门）。
- BP-10 的 80 处重复声明**收敛实施**（按 entry 分摊到各 lane spec；本 spec 只立 GC-6 规则与全局判据）。
