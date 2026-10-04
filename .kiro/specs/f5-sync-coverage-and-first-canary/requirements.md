# Requirements Document

## Introduction

本 spec 把 **F5 营业成本**从 legacy 假双向接成真双向，覆盖其**唯一一册**模板 `F/F5 营业成本.xlsx` 内可表达的 sheet。
它是 umbrella Task 48 的下游 lane spec；F 循环共同裁决 **FC-1~FC-13** 见
`f1-sync-coverage-and-first-canary/design.md` §F 循环共同裁决（本 spec 引用、不复述）。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`F5-P{N}`**。

F5 是损益类底稿（发生额口径，非余额），与 F1~F4 的资产负债类结构不同，并带**四处 F1~F4 都没有的问题**：
① **模板 F5-7 结论行审定数漏算 7 项**（`G31` 引用越界区 `G56:G61`）—— 真实金额错误，FC-5 的第二个例外；
② **F5-1 主营区 10 槽 vs F5-2 12 行**，且 F5-2 自己的合计覆盖 12 行 ⇒ 模板内部小计不一致；
③ **F5 公式管理页一条预设都没有**（FC-11：唯一的 prefill 块是 `items` 型死配置，14 条公式全不生效）；
④ **BP-7 三处**（F5-2 / F5-3 / F5-5 载入路径均为下标/时间戳回退），是 F 循环中 BP-7 最密集的 entry。

### F5 当前状态实测（manifest + slice + 真库，2026-09-26）

```
entry_id            xlsx/gt-f5-cost-of-sales
host_path           audit-platform/frontend/src/components/workpaper/GtF5CostOfSales.vue
independent_entry   true     mount_count  2     parent_entry_id  null
capability          single_onlyoffice        migration_state  legacy_fake_bidirectional  🔴
adapter_id          null     html_store  "unresolved"
wp_code_patterns    ["F5C"]  ← 幻影码；真码 F5（wp_index 5 行）
scenario_profile    xlsx.editable.shared.single.room_service_wired.v1
legacy_reasons      template_only_open / no_durable_forcesave_ack / missing_adapter
template_ref        F/F5 营业成本.xlsx
```

slice 对本 entry 的 `capability_target_blocked_by` 记 **`["BP-1","BP-2","BP-3","BP-4","BP-7"]`**
（`capability_target="bidirectional"` / `capability_verdict_stage="pipeline_entry_pending_definition_delivery"`，按值实测）。
🔴 **BP-7 不是 F5 独有**：BP-7 的 `must_fix_before` 原文点名两条 entry ——「把 `xlsx/gt-f2-inventory-main` 或
`xlsx/gt-f5-cost-of-sales` 标 bidirectional 之前（也在 step 6 为这两条发布 contract 之前）」；
`why_not_fixed_here` 原文「改行身份派生逻辑会影响既存持久化数据的读取……属数据迁移」，`status="REGISTERED_NOT_FIXED"`。
🔴 **BP-7 原文只举 F5 侧一处**（`useF5MonthlyDetail.ts#L133`，`observable_consequences` 明写
「F5-2：从 F5-2-rows 旧键迁来的存量行……每次载入都拿到新的 `m-{ts}-{i}`」）；本 spec 按「触类旁通」另实测
**F5-3 / F5-5 两处同型**（红基线 B4），合计 F5 侧三处 —— 后两处是本 spec 新增证据，不是 slice 原文。

| 事实 | 实测 |
|---|---|
| provider / 契约 | ❌ 无 `phase5_f5_*.py`、无 `f5.*.json` |
| 发布链供给 | `working_paper_sync_entry_state` F 循环 0 行 |
| wp_code 裁决 | 文件中 F 循环 0 条 |
| 宿主接桥 | `GtF5CostOfSales.vue` 两处 legacy `<GtOnlyOfficeSheet>`（L30 带 `isHtmlSheet &&` 前置门控 / L133 兜底）+ `GtEntrySyncCapabilityNotice`；零 `useWorkpaperSyncBridge`。🔴 **F 循环唯一带 `isHtmlSheet &&` 门控的宿主**（slice 已登记） |
| 公式管理 | 宿主 emit 0 次；入口由 F-SHELL 提供；`wp_formula` 表 F5 0 行；**prefill 预设 0 条生效**（见红基线 B1） |
| TB 发布门 | ✅ `F5TabAdjudication.vue:260 adj.publishToTb()`（科目 6401，**发生额口径**）；旧 `f5:writeback-trial-balance` 监听已移除（`GtF5CostOfSales.vue:300` 注释）；🔴 宿主明写「严格保留 `f5:save-items` + `substantive:adjudicated`（F5-7 成本倒轧校验区消费 6401 审定数）两条监听」 |
| 调整分录中央同步 | ✅ `F5TabAdjustment.vue:286 useAdjustmentCentralSync` ⇒ F5-4 是 hub（FC-6） |
| 真库载荷 | F5 全部键 **0 行**（F 循环唯一完全无载荷的 entry） |

### 模板实测：1 册 / 11 sheets（sha256 `417e5ae7…7cb7`，187,721 B）

| sheet | state | 尺寸 | 公式 | 表头 / 数据 / footer（逐格实测） | 形态 | 本 spec |
|---|---|---|---|---|---|---|
| 底稿目录 | visible | 20r×H | 8 | — | 导航 | 不接 |
| 营业成本实质性程序表F5A | visible | 31r×M | 7 | — | 步骤清单 | 不接 |
| 🔴 **营业务成本审定表F5-1** | visible | 60r×N | 135 | 表头 R6；**主营区 R8-17（10 行，A/B/C/D/F/G/H 全是引 F5-2 的公式）**；小计 R18；其他业务区标题 R19 + 数据 **R20-25**；小计 **R26**；合计 **R27**（`=R26+R18`）；试算 R28；差异 R29 | 两个行数组（主营区几乎全公式） | ✅ 仅其他业务区 |
| **主营业务成本月度明细表F5-2** | visible | 30r×X | 102 | 两级表头 **R9/R10**；数据 **R11-22（12 品种行）**；合计 **R23**；比例 R24 | 行表（月度矩阵 12 列） | ✅ |
| **其他业务成本明细表F5-3** | visible | 37r×N | 85 | 两级表头 **R9/R10**；数据 **R11-21**（R11-13 预填「出租固定资产/出租无形资产/出租包装物和商品」）；合计 **R22** | 行表 | ✅ |
| 调整分录汇总F5-4 | visible | 22r×J | 7 | — | hub | 🔍 FC-6 |
| **与上年度比较分析表F5-5** | visible | 30r×Q | 59 | 两级表头 **R9/R10**；数据 **R11-16**；合计 **R17** | 行表 | ✅ |
| 销售数量与结转成本数量核对明细表F5-6 | visible | 81r×P | **244** | 三块，总计 R21/R34/R47 | 分厂×产品×12 月三块 | 🔍 后置 |
| **成本倒轧表F5-7** | visible | 36r×K | 40 | 表头 **R10**；**21 固定行 R11-31**（稳定 rowKey）；**无 footer 合计**（R32 审计说明） | 稳定 key 固定行 | ✅ |
| **重大调整核查表F5-8** | visible | 39r×I | 7 | 两级表头 **R12/R13**；数据 **R14-29**；**无 footer 合计**（R30 审计说明） | 行表（数据区零公式） | ✅ **canary** |
| GT_Custom | hidden | 8r×B | 0 | — | 平台注入区 | 不接 |

**逐格实测公式：**

| 位置 | 公式 |
|---|---|
| F5-1 R8（主营区，10 行同型） | `A='主营业务成本月度明细表F5-2'!A11` · `B=!N11` · `C=!O11` · `D=!P11` · `E=B8+C8+D8` · `F=!R11` · `G=!S11` · `H=!T11` · `I=F8+G8+H8` |
| F5-1 R20（其他业务区，6 行同型） | 仅 `E=B20+C20+D20` · `I=F20+G20+H20`（B/C/D/F/G/H **手填**） |
| F5-1 R18/R26/R27 | `SUM(8:17)` / `SUM(20:25)` / `=R26+R18` 逐列；R29 `E=E27-E28` · `I=I27-I28` |
| F5-2 R11 | `N=SUM(B11:M11)`（12 月合计）· `Q=N+O+P` · `U=R+S+T` · `V/W` 变动率 `IF(AND(…))` |
| F5-2 R23/R24 | `SUM(N11:N22)` 等逐列（**覆盖 12 行**）· R24 比例 `IF(x23=0,0,x23/$N$23)` |
| F5-3 R11 | `E=B+C+D` · `F=IF(E11=0,0,E11/E$22)` · `J=G+H+I` · `K=IF(J11=0,0,J11/$J$22)` · `L=E11-J11` · `M=IF(AND(J11=0,L11=0),0,…)` |
| F5-5 R11 | `D=B11*C11`（本期总成本）· `G=E11*F11`（上期）· `H=B-E` · `I=C-F` · `J=D-G` · `K=H/E` · `L=I/F` · `M=J/G` |
| F5-7 R16/R21/R24 | `G16=G11+G12+G13-G14-G15` · `G21=G16+G17+G18+G20` · `G24=G21+G22-G23`（E/F/H 列同型） |
| 🔴 **F5-7 R31** | `E31=E24+E25+E26-E27-E28-E29-E30`（正确）· `F31`/`H31` 同型正确 · **`G31=G24+G56+G57-G58-G59-G60-G61`**（🔴 引用越界空区，见红基线 B2） |
| F5-8 | 数据区 **零公式**（7 个公式全在表头/页眉区） |

模板**无 Excel Table**；3 个 definedName（`AS2DocOpenMode` / `a暗暗` / `ffd`）全是历史残留、非受管锚点。

**UUID 候选列（逐格实测数据区 + 表头全空）**：F5-2 **Y**（X 备注、max Y）· F5-3 **O**（N 备注、max O）·
F5-5 **P**（N 差异原因分析 / O 索引号、max Q）· F5-7 **I**（H 上期数、max K）· F5-8 **I**（H 理由是否充分、max I）
🔴 F5-2 / F5-3 / F5-8 的 UUID 列等于或超出 `max_col` ⇒ instrumentation 需扩列，Task 2 须确认扩列不破坏打印区域。

### F5 store 键实测（按值 grep；`_probe_f_keys.py F5`）

| sheet | store 键（主 / legacy 读回退） | 形态 | 写入方 | 行身份 / 增删 |
|---|---|---|---|---|
| F5-1 审定表 | `F5-1-adj-main-rows` + `F5-1-adj-other-rows` + `F5-1-adj-tb-6401` + `-tb-6401-prior` + `-adj-note` / `-adj-conclusion` | rows ×2 | `useF5Adjudication`(748) | `rowKey`（19 处）；add/del ×1/×1 |
| F5-2 月度明细 | **`F5-2-monthly-rows`** / legacy `F5-2-rows` + `F5-2-audit-note` / `-audit-conclusion` | rows | `useF5MonthlyDetail`(387) | **`id`**（不是 rowId）；add/del ×1/×1；🔴 **BP-7**（L133） |
| F5-3 其他业务成本 | **`F5-3-other-cost-rows`** / legacy `F5-3-rows` | rows | `useF5OtherCost`(416) | `id`；add/del；🔴 **BP-7**（L146） |
| F5-4 调整分录 | `F5-4-rows` + `F5-4-audit-note` / `-audit-conclusion` / `F5-4-adjustment` | rows（hub） | `F5TabAdjustment.vue` | `rowId`；add/del |
| F5-5 比较分析 | **`F5-5-comparison-rows`** / legacy `F5-5-rows` + `F5-5-audit-note` / `-audit-conclusion` / legacy `F5-5-conclusion` | rows | `useF5Comparison`(330) | `id`；add/del；🔴 **BP-7**（L128） |
| F5-6 数量核对 | `F5-6-quantity-recon-rows` + `F5-6-quantity-recon-plants` / legacy `F5-6-rows` | rows + 分厂维度 | `useF5QuantityRecon`(520) | `id`；无 add/del（`id` 出现 30 次） |
| F5-7 成本倒轧 | `F5-7-cost-rollforward` + `F5-7-adjudicated-cogs`（外部审定数） | 固定行 | `useF5CostRollforward`(643) | **`rowKey`**（21 个稳定键 `openingMaterial`…`mainBusinessCOGS`，`F57_ROW_DEFS`）；无 add/del |
| F5-8 重大调整 | `F5-8-rows` + `F5-8-audit-note` / `-audit-conclusion` / legacy `F5-8-conclusion` | rows | `useF5MajorAdjustment`(327) | `id`；add/del ×1/×1；**无 BP-7** |

🔴 **键名陷阱（按值实测）**：①五张表都有「主键 + legacy 读回退键」双键（`F5-2/3/5/6/8`），契约 SHALL 只声明主键；
②F5-2 的行身份字段是 **`id`** 不是 `rowId`（与 D 类惯例相反，同 E1 教训）；③F5-7 的 store 键**不带 `-rows` 后缀**
（`F5-7-cost-rollforward`），按 `-rows` 模式 grep 会漏；④`F5-7-adjudicated-cogs` 由**宿主**写入
（`GtF5CostOfSales.vue:275`，来源是 `substantive:adjudicated` 事件的 6401 审定数）⇒ 是跨表注入值、非本表数据。

**零写入读键（按值实测，读方有、全仓无写方）**：`D4-1-adj-main-rows`（`useF5CrossSheet.ts:55` 读 D4 主营未审数）·
`F5-2-detail-rows`（`h1DepAllocCounterpartPull.ts:164` 读）⇒ 恒 undefined，登记不修（与 F4-8 两个零写入读键同型）。

### 🔴 红基线（实测，非本 spec 引入）

**B1 · FC-11 在 F5 的后果最严重：公式管理页一条预设都没有**

F5 在 `prefill_formula_mapping.json` 中**只有 1 个块**（`[226]` `营业务成本审定表F5-1`），且该块 `cells` 为空、
14 条公式全在 `items` 里 ⇒ 运行时四个消费方（只读 `cells`）全部读不到。实证：`convert_prefill_presets()` 现算
`workpaper:F0=2 / F1=33 / F2=78 / F3=18 / F4=18`，**F5 完全缺席**（F 循环唯一为 0 的科目）。
该块内另有一条 `=PREV('F5','审定表F5-1','审定数')` **引用不存在的 sheet**（模板真名是 `营业务成本审定表F5-1`，
带「营业务」错字），即便迁为 `cells` 也解析不到。

**B2 · 🔴 模板 F5-7 结论行审定数漏算 7 项（真实金额错误）**

```
F5-7!E31 = E24+E25+E26-E27-E28-E29-E30     ← 未审数列，正确
F5-7!F31 = F24+F25+F26-F27-F28-F29-F30     ← 审计调整列，正确
F5-7!H31 = H24+H25+H26-H27-H28-H29-H30     ← 上期数列，正确
F5-7!G31 = G24+G56+G57-G58-G59-G60-G61     🔴 审定数列：G56:G61 是空白越界区（sheet 仅 36 行）
```
⇒ 审定数列的「主营业务成本」退化为 `G24`（产成品成本），**漏掉产成品期初 / 其他增加 / 期末 / 自制自用 / 内部领用 /
其他发出六项**。前端 `useF5CostRollforward` 三个口径（未审 / AJE / 上期）都调
`calcF57MainBusinessCOGS(fg, openingFG, …)` 正确计算 ⇒ **前端对、模板错**。
🔴 这是 FC-5「以模板为权威」的**第二个例外**（第一个是 F3-4 应计利息）：此处以模板为权威等于把结论行算错，
必须走模板覆盖层修 `G31`，或该列不受管（见需求 5.2）。
触类旁通（`_probe_f_oob.py` 扫全 F 目录「同 sheet 引用行号 > max_row」）：**唯一命中就是这一格**。

**B3 · F5-1 主营区 10 槽 vs F5-2 12 行（模板内部小计不一致）**

F5-2 数据区 **R11-22（12 品种行）**、合计 `R23=SUM(N11:N22)` 覆盖 12 行；
F5-1 主营区只有 **R8-17（10 行）**、逐行引 `F5-2!A11`~`A20`、小计 `R18=SUM(B8:B17)` ⇒
**F5-2 的 R21/R22 两行不进 F5-1**，`F5-1!B18 ≠ F5-2!N23`（品种数 > 10 时）。
叠加前端：`useF5MonthlyDetail` 支持**任意行数**（`addRow`/`removeRow`）⇒ 三层容量不一致（前端任意 / F5-2 12 / F5-1 10）。

**B4 · BP-7 三处（F 循环最密集）**

| 键 | 位置 | 回退写法 |
|---|---|---|
| `F5-2-monthly-rows` | `useF5MonthlyDetail.ts:133` | `id: String(r?.id ?? r?.rowId ?? \`m-${Date.now()}-${i}\`)` |
| `F5-3-other-cost-rows` | `useF5OtherCost.ts:146` | `id: String(r?.id ?? r?.rowId ?? \`oc-migrated-${i}\`)` |
| `F5-5-comparison-rows` | `useF5Comparison.ts:128` | `id: String(r?.id ?? r?.rowId ?? \`cmp-migrated-${i}\`)` |

三者都含下标 `${i}`（F5-2 还混时间戳）⇒ 插删行后身份错位。slice 的 `not_bidirectional_because` 已明令「具备双向前必须先修」。

**B5 · 双键并存**：F5-2/3/5/6/8 五张各有 legacy 读回退键。BP-7 的 `consequence` 原文
「行身份一旦由位置派生……⇒ stable field key 在 roundtrip 中无法保持」，而 F5-2 的 `observable_consequences`
把双键并存写成该退化的触发条件（「从 `F5-2-rows` 旧键迁来的存量行**既无 `id` 也无 `rowId`**」）
⇒ 双键并存与 BP-7 是同一条链的两环，本 spec 一并处置。
⇒ 契约只声明主键；但**读回退不得删**（旧数据仍在），需求 2.3 给出边界。

**B6 · FC-10 命中面待取证**：F5-2 `V/W`（变动率）· F5-3 `F/K`（结构比）/ `M`（变动率）· F5-5 `K/L/M`（变动率）都是
**公式列**（逐格实测），与 F4 同属「百分比格列全是公式」⇒ 初判 FC-10 **不命中**；但 F5-5 `C/F`（单位成本）参与
`D=B*C` 乘法、F5-3 无可编辑比例列，Task 2 SHALL 逐列取证后确认（不得沿用初判）。

**B7 · F5-1 主营区受管价值极低**：R8-17 的 A/B/C/D/F/G/H **七列全是引 F5-2 的公式**，只有 E/I 是本行加总（也是公式）
⇒ 整区**零 editable 字段**。按 FC-4 三元组，前端 `F5-1-adj-main-rows` 虽有 add/del，但模板侧无可写格 ⇒
受管它等于把 F5-2 的派生值物化后再读回（双源）。需求 6.1 裁决为 HTML-only。

## Glossary

沿用 F1 spec Glossary；新增：

| 术语 | 含义 |
|------|------|
| 发生额口径 | 损益类底稿的金额语义（本期发生额），非资产负债类的期初/期末余额；F5 TB 发布用 `amount_kind` 与余额类不同 |
| 三层容量不一致 | 前端任意行数 / 中间表固定行数 / 汇总表槽位数 三者互不相等（B3） |
| 越界引用 | 模板公式引用超出 sheet 已用区的空白格（`F5-7!G31` 引 `G56:G61`），求值为 0 而不报错 ⇒ 静默错数 |
| 跨表注入值 | 由宿主监听事件写入本表 store 的值（`F5-7-adjudicated-cogs` ← `substantive:adjudicated` 的 6401 审定数） |

## Requirements

### Requirement 1: F5 首张 canary —— 从零打通真双向（F5-8 重大调整核查表）

1. WHEN 选定首张 canary THEN 它 SHALL 是 **`重大调整核查表F5-8`**（39r×I / 7 公式全在表头区 / 两级表头 R12/R13 /
   数据 **R14-29** / **无 footer 合计** / 键 `F5-8-rows` / 行身份 `id` / UUID **I**）—— 理由见 design 裁决 F5-H1：
   数据区零公式、**F5 唯一无 BP-7 的动态行表**、无 FC-10、零跨 sheet、无模板缺陷。
2. WHEN 建 provider THEN SHALL 新建 `phase5_f5_cost_of_sales.py`；`assert_entry_selectable(*, resolution, manifest=None)`
   照 D3 同签名（`resolution` 必填、无关闭开关、真 manifest 真调）；`WP_CODES={"F5C"}`（幻影码，FC-2）；
   `build_matcher()` 带 `document_type="xlsx"`；`build_registration` 照 `phase5_d3_prepaid_receipts.py:830` 并有**真构造**判据。
3. WHEN 声明 wp_code 裁决 THEN 新增 F5 条目 `wp_codes=["F5"]` + `matcher_domain_conflict=null`；
   🔴 `store_payload_evidence.max_payload_bytes` SHALL 为 **0** 并写明「F5 全部键真库 0 行」（F 循环唯一完全无载荷的 entry，
   不得伪造非零证据）。
4. WHEN 无 footer 合计 THEN `footer_row` SHALL 指向其后第一个非数据锚行（R30「三、审计说明：」）、
   `footer_marker="三、审计说明"`、`footer_carries_total_formula=False`（E1-10 / D3-4 先例）。
5. WHEN 契约发布 THEN 走完整五环；第③环缺供给时如实登记 `upstream_gap`（BP-61-1）。
6. WHEN adapter 注册成功 THEN manifest `migration_state` SHALL 变为 `adapter_registered`、三条 `legacy_reasons` 全消。
7. WHEN 宿主接桥 THEN `GtF5CostOfSales.vue` SHALL 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`；
   🔴 本宿主是 F 循环**唯一带 `isHtmlSheet &&` 前置门控**的（L30），接桥 SHALL 保持该门控语义（未迁移 sheet 走兜底分支），
   且 SHALL 严格保留 `f5:save-items` 与 `substantive:adjudicated` 两条 window 监听（F5-7 校验区消费 6401 审定数）。
8. WHEN 真栈验收 THEN SHALL 达三谓词并留 DB 证据；🔴 真库零载荷 ⇒ 验收 SHALL 先 seed 最小载荷
   （`backend/scripts/e2e/seed_f5_publish_e2e.py`），不得以「无数据也算通过」收尾。

### Requirement 2: 形态判定先行 + 双键边界

1. WHEN 判定形态 THEN SHALL 用前端三元组。实测结论：F5-2/3/5/8 为 `excel_table` + **`id`**（不是 `rowId`）；
   F5-7 为 `excel_table` + 稳定 **`rowKey`**（21 个固定行）；F5-1 两区为 `rowKey`；F5-6 待核。
2. WHEN 声明 `store_item_id` THEN SHALL 取**主键**不取 legacy 读回退键；变异 SHALL 含
   ①`F5-2-monthly-rows → F5-2-rows`（legacy）②`F5-7-cost-rollforward → F5-7-rows`（不存在的键）并证明打红。
3. WHEN 处理双键并存（红基线 B5）THEN 契约只声明主键；前端 legacy 读回退 **SHALL 保留**（旧数据仍需读到），
   但 SHALL 有判据证明：受管后回写只写主键、legacy 键不被二次写入（避免双写漂移）。
4. WHEN 某 sheet 无 footer 合计（F5-7 / F5-8）THEN 按需求 1.4 同款处置。
5. WHEN UUID 列等于或超出 `max_col`（F5-2 Y / F5-3 O / F5-8 I）THEN SHALL 确认 instrumentation 扩列后
   打印区域 / 页面设置不被破坏（Task 2 实测）。

### Requirement 3: BP-7 三处修复（受管硬前置）

1. 🔴 WHEN F5-2 / F5-3 / F5-5 任一受管 THEN 其载入路径的下标回退 SHALL 已修：缺 `id` 时铸稳定 UUID 并**立即回写**，
   不得出现 `m-${Date.now()}-${i}` / `oc-migrated-${i}` / `cmp-migrated-${i}` 三种形态。
2. WHEN 修复 THEN SHALL 按「触类旁通」一次修完三处（不逐个 spec 各修一次），并加判据：含下标模式的 id 在载入后被重铸。
3. WHEN 旧载荷已含下标型 id THEN SHALL 有迁移判据（重铸后 id 不匹配 `^(m|oc-migrated|cmp-migrated)-` 模式）。

### Requirement 4: F5-5 / F5-3 / F5-2 行表接入

1. WHEN 声明 F5-5 THEN `F5-5-comparison-rows` / `id` / 两级表头 R9/R10 / 数据 **R11-16** / footer **R17「合计」** /
   UUID **P** / `formula_columns=("D","G","H","I","J","K","L","M")`（模板 `D=B*C` · `G=E*F` · `H/I/J` 差额 · `K/L/M` 变动率）。
   🔴 前端 `calcF5ComparisonChangeRate` 在上期为 0 时返 **`'N/A'` 字符串**（`useF5Comparison.ts:69-73`，注释「对应 Excel #DIV/0」）
   ⇒ 变动率三列是 `mode=formula`（不回写），但 extract 读回 `#DIV/0!` 时须容错（同 F4-7 除零，判据见 4.4）。
2. WHEN 声明 F5-3 THEN `F5-3-other-cost-rows` / `id` / 两级表头 R9/R10 / 数据 **R11-21** / footer **R22「合计」** /
   UUID **O** / `formula_columns=("E","F","J","K","L","M")`；R11-13 三行模板预填标签（出租固定资产等）SHALL 作为
   「预填行」登记（同 E1-2 的 `PREFILLED_CURRENCY_ROWS` 范式），不得当作空行被裁剪。
3. WHEN 声明 F5-2 THEN `F5-2-monthly-rows` / `id` / 两级表头 R9/R10 / 数据 **R11-22（12 行）** / footer **R23「合计」** /
   UUID **Y** / `formula_columns=("N","Q","U","V","W")`；12 个月度列 B-M 是 editable，前端字段是 `months[12]` 数组
   ⇒ 契约 field 的 `json_key` SHALL 用 nested 路径（`months/0`…`months/11`），不得展平成 12 个顶层键。
4. WHEN 任一公式列可能产出 Excel 错误值（F5-5 变动率除零）THEN SHALL 有判据：extract 不崩、异常类型为
   `type_normalization_failure`、store 中该字段不出现 `#DIV/0!`（按值实测 `excel_extract.py:3400-3431` 的行为）。
5. WHEN F5-2 受管 THEN 🔴 红基线 B3 的容量不一致 SHALL 已裁决（需求 6.2），否则 F5-2 受管后行数 > 10 会让 F5-1 小计静默漏算。

### Requirement 5: F5-7 成本倒轧表（稳定 key 固定行 + 模板缺陷）

1. WHEN 声明 F5-7 THEN SHALL 用 `RowTableSheetSpec` + `row_identity_key="rowKey"`：21 个固定行 R11-31
   （rowKey 逐字取 `F57_ROW_DEFS`：`openingMaterial` / `materialPurchaseNet` / `materialOtherIncrease` / `closingMaterial` /
   `materialOtherIssue` / `directMaterialCost` / `directLabor` / `manufacturingOverhead` / `overheadMaterialTransfer` /
   `specialTooling` / `productProductionCost` / `openingWIP` / `closingWIP` / `finishedGoodsCost` / `openingFG` /
   `fgOtherIncrease` / `closingFG` / `selfUseProductCost` / `internalUseProductCost` / `fgOtherIssue` / `mainBusinessCOGS`）；
   表头 R10；无 footer（按需求 1.4 处置）；UUID **I**；受管列 E（未审）/ F（调整）/ H（上期）为 editable，G（审定数）为 formula。
2. 🔴 WHEN 模板缺陷 `G31`（红基线 B2）THEN SHALL 二选一，**不得**以模板为权威：
   ①经模板覆盖层把 `G31` 修为 `=G24+G25+G26-G27-G28-G29-G30`（与 E/F/H 列同型）后受管
   ②`G` 列整列判 HTML-only（不受管）并在 UI 中文提示「审定数列由系统计算，模板公式存在已知缺陷」。
   默认①（覆盖层可用时），否则②。判据 SHALL 证明修复后 OO 与 HTML 的 `mainBusinessCOGS` 审定数相等。
3. WHEN 行是 `rowType='formula'` 的派生行（`directMaterialCost` / `productProductionCost` / `finishedGoodsCost` /
   `mainBusinessCOGS`）THEN 其 E/F/H 列在模板中也是公式（`=G11+G12+…` 同型）⇒ SHALL 判 `mode=formula`，不得 editable。
4. WHEN `F5-7-adjudicated-cogs`（跨表注入值）THEN SHALL **不进** `field_specs`（它由宿主从 `substantive:adjudicated` 写入、
   非本表数据）；但校验区消费它的行为 SHALL 不回归（需求 1.7 的两条监听）。

### Requirement 6: F5-1 审定表（其他业务区受管 / 主营区 HTML-only）+ F5-4 / F5-6 核

1. 🔴 WHEN 判定 F5-1 主营区（R8-17）THEN 按红基线 B7 SHALL 判 **HTML-only**：模板侧七列全是引 F5-2 的公式、
   零 editable 字段，受管等于把派生值物化后读回（双源）。判据：`F5-1-adj-main-rows` 不在 `all_store_item_ids()`。
2. 🔴 WHEN 容量不一致（红基线 B3）THEN SHALL 裁决并落地：模板 F5-1 主营区 10 槽 / F5-2 12 行 / 前端任意行。
   默认裁决：**F5-2 品种数 ≤10 时受管，>10 时整表降级 legacy + 中文提示**（提示须点明「超出审定表主营区槽位，
   F5-1 小计将漏算」）；不得为适配而改模板槽位或 SUM 区间。
3. WHEN 声明 F5-1 其他业务区 THEN `F5-1-adj-other-rows` / `rowKey` / 数据 **R20-25** / footer **R26「小计」** /
   `formula_columns=("E","I")`（B/C/D/F/G/H 手填）；UUID 列由 Task 2 实测（F5-1 max_col N、J-N 全空）。
4. WHEN F5-1 受管 THEN FC-9 TB 红线：sync 路径对 `trial_balance` 写次数为 **0**；`publishToTb`（科目 6401、
   **发生额口径**）仍是唯一入口；变异「sync 回写里调 publishToTb」SHALL 必红。
5. WHEN 核 F5-4 THEN 照 FC-6 默认 `single_html`（`F5TabAdjustment.vue:286 useAdjustmentCentralSync`），只产裁决与证据。
6. WHEN 核 F5-6 THEN 244 公式 / 三块（分厂×产品×12 月，总计 R21/R34/R47）⇒ SHALL 后置并先做形态核，
   不在本 spec 的 canary~收口链路内强行接入；核结论落证据。

### Requirement 7: 公式管理、prefill 修复与零回归

1. WHEN 提供公式管理入口 THEN SHALL 消费 F-SHELL，不在 F5 宿主新建第二个 owner；判据覆盖两种渲染模式下入口可达。
2. 🔴 WHEN 修 prefill（红基线 B1）THEN SHALL：①块 `[226]` 的 14 条 `items` 迁为 `cells`（FC-11 数据侧）
   ②修块内 `PREV('F5','审定表F5-1',…)` 的 sheet 名为 `营业务成本审定表F5-1`（模板真名，带错字）
   ③判据：`convert_prefill_presets()` 的 `workpaper:F5` 预设数从 **0** 变为 **14**（F5 是唯一可用「从 0 到有」证明 FC-11
   修复生效的科目）。工具链根因由 F3 spec 修，本 spec 依赖其完成。
3. WHEN 声明 `formula_columns` THEN SHALL 与模板逐格实测一致，mask 由引擎现算；F5-1 两区各自实测（主营区不受管）。
4. WHEN F5 provider 纳入 THEN 既有 contract golden digest **逐项不变**（🔴 **现算基线，不写死数字** —— 依 G 循环裁决 GC-10：契约目录已从 10 涨到 12（并发会话交付 d1/d3/d5/d6/d7/e1），写死数字的判据下次交付即 stale；判据形态应为「非本 spec 的 digest 逐项比对」，不断言集合大小）；F5 进 `check_sync_provider_golden_digest.PROVIDERS`；
   登记点（`DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` / `store_item_registry` plan / wp_code 裁决 /
   overlay + 重生 manifest）同步。
5. WHEN 零写入读键（`D4-1-adj-main-rows` / `F5-2-detail-rows`）THEN SHALL 登记为「恒 undefined 的兼容回退」、
   不进 field_specs、不修（与 F4-8 同型）。
6. WHEN 未接 sheet 切在线编辑 THEN SHALL 保持 legacy 并显式登记为假双向。

### 不在本 spec 范围

- 底稿目录 / `营业成本实质性程序表F5A` / GT_Custom / 3 个残留 definedName。
- F5-6（244 公式三块）的接入 —— 本 spec 只做形态核。
- FC-11 工具链根因（F3 spec）；F3 / F4 的 items 型块（🔴 F2 无 items 型块 —— 全库 7 个 items 块只属 F3/F4/F5）。
- 模板 sheet 名错字「营业务成本审定表F5-1」的纠正（改 sheet 名会动 sha 与全部引用，属模板治理债）。
- 发布链平台级供给（BP-61-1）、模板覆盖层本身。
