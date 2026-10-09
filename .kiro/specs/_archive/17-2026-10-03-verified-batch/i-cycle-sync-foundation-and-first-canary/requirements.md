# Requirements Document

## Introduction

本 spec 是 **I 循环（无形资产）6 条 Excel 独立 entry** 从 legacy 假双向接成真双向的**地基 spec**：
承载 I 循环共同裁决 **IC-1 ~ IC-20**、I 专属前置（BP-5 ~ BP-10）的处置边界、以及**首张 canary（I6 研发费用明细表）**。
它是 umbrella `workpaper-html-onlyoffice-bidirectional-writeback-closure` **Task 51** 的下游实施 spec
（Task 51 只交付 I slice 与冻结口径 + 149 KB 守卫，不接双向）。

上游沿用 **FC-1~FC-13**（`f1-sync-coverage-and-first-canary/design.md`）·
**GC-1~GC-10**（`g-cycle-sync-foundation-and-first-canary/design.md`）·
**HC-1~HC-16**（`h-cycle-sync-foundation-and-first-canary/design.md`）；
逐条适用性重裁见 design §FC/GC/HC 适用性重裁 —— 🔴 **I 循环有 7 条上游裁决不命中**。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`IF-P{N}`**（I Foundation）。

🔴 **本 spec 与 slice 冲突或超出时一律以实测为准**：本轮三轮按值实测**独立复算了 slice 的全部承重结论**，
结果是 **slice 全部相符**（这是 D/E/F/G/H/I 六份 slice 里唯一一份零反驳的），
但**实测出 3 条 slice 未登记 / 不够精确的事实**（见 Requirement 3）。

### 两份下游 lane spec（本 spec 是它们的共同前置）

| lane spec | 覆盖 entry | 数 |
|---|---|---|
| `i1-i3-disclosure-positional-identity-and-classification-source` | I1 / I3 | 2 |
| `i2-i4-i5-carrier-and-structure-exceptions` | I2 / I4 / I5 | 3 |

canary（I6）在本 spec 内打通；其余 5 条由两份 lane spec 承接。
**IC-1 ~ IC-20 在本 spec 裁一次，两份 lane 只引用不复述。**

### 范围与排除（slice `slice_scope` 逐条 + manifest 现算复核）

**6 条独立 entry** = manifest 里 `wp_code_patterns` 以 `I` 开头 × `document_type=='xlsx'` × `independent_entry is True`。
🔴 **无排除项**（实算 6 = 6 = 6：I 前缀 entry 总数 == independent 总数 == 本 slice 条数）。

**四类「查过且没有」（都必须落成判据，否则后来者会重复调查或误以为 I 也有）**：

1. 🔴 **I 循环没有 pilot**。四个 pilot 是 B60（Task 40）/ D2（41）/ H1（42）/ G7（43）。
   逐文件读 `review.entry_id` 实证：`xlsx/b60/gt-b60-bundle`（🔴 **三段式**）/ `xlsx/gt-d2-accounts-receivable` /
   `xlsx/gt-h1-fixed-assets` / 🔴 `xlsx/gt-g7-long-term-equity-main`（契约文件名叫 `g7.soe_subsidiary_disclosure.json`
   却指 `-main`）⇒ **按文件名猜 entry_id 会猜错两条**。故 selection_rule **不含** pilot 排除项。
2. 🔴 **没有 I0 函证**。`backend/wp_templates/I/` 下只有 6 个文件（I1..I6），
   `find_template_file('I0')` 与 `find_template_file_any('I0')` 都返 `None`。
3. 🔴 **parent_duplicate 子入口 0 条**。6 条 `parent_entry_id` 全为 `null`、`independent_entry` 全为 `true`；
   manifest 现算 `/i[1-6]/` 路径命中 **0**。与 D4（31 条）、H（5 条）不同形，与 F、G（各 0 条）同形。
   6 条 entry 各自的子 Tab（I1 有 15 个、I3 有 8 个）是**同一 entry 内的 sheet 分发**，没有自己的
   `GtOnlyOfficeSheet` 挂载点 ⇒ 不在 manifest 的 entry 里。
4. **附注披露同步链路**与**四表取数链路**不碰字节：前者属 `disclosure-sync-path-buildout` 等 spec，
   🔴 但与本 slice **共用分类常量**（`i1SoeDisclosureModel.I1_SOE_CATEGORIES` 同时被底稿披露 Tab 与
   `i1DisclosureSyncPayload` 消费）故 BP-7 一并核；后者属 `i-cycle-extraction-formula-and-disclosure-closure`
   （🔴 **该 spec 已归档**在 `.kiro/specs/_archive/08-disclosure-notes/`，但 5 个
   `backend/app/services/four_table/i_cycle_*.py` 文件仍在）。

### 6 条 entry 清单（entry_id 全名 / 宿主 / 模板 / 载体族 / 主表键）

| entry_id | 宿主 | 幻影码 | 模板 sha256 前 16 / 字节 / sheets | mount | 写族 | 读族 | payload mode | 主表键 | 身份 | 专属阻塞 |
|---|---|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-i1-intangible-assets` | `GtI1IntangibleAssets.vue` | I1I | `97eced1f58ab3925` / 136,885 / 18 | 2 | host_inline | render_config_refetch | remark_only | `I1-2-rows` | rowId | BP-6, **BP-7** |
| `xlsx/gt-i2-development-expenditure` | `GtI2DevelopmentExpenditure.vue` | I2D | `a93c298b1f4adfe2` / 138,084 / **21** | 2 | host_inline **+第二写路径** | 同 | remark_only | `I2-2-rows` | rowId | （无，但唯一缺二级门控） |
| `xlsx/gt-i3-goodwill` | `GtI3Goodwill.vue` | I3G | `96cd6d6cb70698ce` / 212,588 / 15 | **4** | host_inline | 同 | remark_only | `I3-2-rows` | rowId | **BP-6**（4/6 命中） |
| `xlsx/gt-i4-long-term-prepaid` | `GtI4LongTermPrepaid.vue` | I4L | `8bfb85884705e471` / **312,532** / 12 | 2 | host_inline | 同 | **dual_write** | `I4-2-rows` | rowId | **BP-5, BP-8②** |
| `xlsx/gt-i5-other-noncurrent-assets` | `GtI5OtherNoncurrentAssets.vue` | I5O | `7e8ec9c22580e05d` / **306,241** / 9 | 2 | **formdata_composable** | **formdata_composable** | **passthrough** | `I5-2-rows` | rowId | （无，但结构最深） |
| **`xlsx/gt-i6-research-development-expense`（canary）** | `GtI6ResearchDevelopmentExpense.vue` | I6R | `924a1e8348a897c2` / 87,268 / 11 | 2 | host_inline | 同 | remark_only | **`I6-2-detail-rows`**（+legacy alias `I6-2-rows`） | **id** | **BP-5, BP-8①** |

共 **86 sheets**。6 条共同：`migration_state=legacy_fake_bidirectional` /
`scenario_profile_id=xlsx.editable.shared.single.room_service_wired.v1` /
`canonical_resolver=legacy_sheet_onlyoffice_router` / `html_counterpart_verdict=exists` /
载荷列 **`remark`** / `adapter_id=None` / 0 契约 / 0 representation / 6 条 `capability_verdict_pending`。
`classification_source_sheet`：I1=`底稿目录` · I5=`明细表I5-2` · I6=`明细表I6-2` · I2/I3/I4=`null`。

🔴 **模板 6 文件 ↔ 6 entry 是双射**（单射且满射，无 `belongs_to_entry` 为 null 的条目）——
与 F（F2 一册跨两 entry）、G（G4/G6 一册服务三 entry）、H（11 文件对 9 entry，两条带 `excluded_reason`）**都不同形**。

---

## Requirements

### Requirement 1: I 循环共同裁决 IC-1 ~ IC-20 落地为可复核声明

**User Story:** 作为两份下游 lane spec 的实施者，我希望 I 循环的共性裁决只做一次并有判据锁死，
不要在三份 spec 里各裁一遍互相漂移。

#### Acceptance Criteria

1. WHEN 本 spec 交付 THEN design SHALL 承载 **IC-1 ~ IC-20** 完整裁决正文，两份 lane spec 只引用不复述。
2. WHEN 引用上游裁决 THEN SHALL 逐条给出 **FC-1~FC-13 / GC-1~GC-10 / HC-1~HC-16 在 I 的适用性重裁**，
   且 🔴 **以下 7 条 SHALL 明确标为「在 I 不命中或不适用」并给出实测依据**：
   FC-8（6 宿主 `OcrConfirm|runOcr` 命中 **0**）· FC-11（prefill I 16 条全 `cells` 型、`items=0`）·
   HC-5（同尾码双 sheet **0 组**）· HC-10（6 宿主 `localStorage` 命中 **0**）·
   HC-13（`max_column≥200` 的 sheet **0 张**）· GC-4（无转置形态）·
   H 的 BP-7 label-as-key（`key: X.label` 与 `row[X.label]` 命中 **0**）。
3. WHEN 声明任一 I entry 的阻塞项 THEN SHALL 逐元素取 slice `capability_target_blocked_by`（FC-13），
   **不得**跨 entry 套用；判据 SHALL 覆盖 6 条全集。
4. WHEN 登记四类「查过且没有」（见 §范围与排除）THEN SHALL **现算**而非读 slice 快照；
   变异「往 `backend/wp_templates/I/` 塞第 7 个文件」/「给某条 I entry 造一个 `parent_entry_id`」
   / 「造一份 `review.entry_id` 以 `xlsx/gt-i` 开头的契约」SHALL 分别打红。
5. 🔴 WHEN 任一 lane spec 复述 IC-x 正文 THEN 跨 spec 复盘 SHALL 判为缺陷（漂移源）。

### Requirement 2: 载体族二分与两条反向断言（IC-2 / IC-3 / IC-4）

**User Story:** 作为实施者，我不要拿 F 的单一形态守卫或 H 的三族守卫套 I ——
F 的口径对 5 条假红，H 的口径让 `per_tab` 族分母为空变成空跑重言式。

#### Acceptance Criteria

1. WHEN 为任一 I entry 定位写路径 THEN SHALL 按实测二分：
   **`host_inline` 5 条**（I1/I2/I3/I4/I6，各自 `import http from '@/utils/http'` 并 PUT）·
   **`formdata_composable` 1 条**（**只有 I5**）。
   🔴 判据 SHALL 对 I5 **反向断言宿主文件里没有 http/api 的 import**
   （写死「全宿主都有 client import」会让 I5 静默通过）。
2. WHEN 登记 I2 的第二写路径 THEN SHALL 按实测：`useI2FormData.ts#L185` 的 PUT，
   消费方 = 宿主 + `useI2Adjudication.ts` + `useI2Impairment.ts` + `i2/core/I2TabAdjudication.vue`
   （实测 import 生产消费 **4**）。
3. 🔴 WHEN 为任一 I entry 定位读路径 THEN SHALL 断言 **没有一条宿主直接 GET `/checklist-responses`**：
   5 条先读 `props.htmlData.allResponses`，无则 `GET /render-config?force_component_type={ct}`；
   I5 由 `useI5FormData.ts#L280` 做同样 GET。
   **判据 SHALL 断言宿主文件里 `checklist-responses` 的 GET 命中数 == 0 —— 这个 0 是判据的一部分，不是省略。**
   `ct` 实测值：`i1-intangible-assets` / `i2-development-expenditure` / `i3-goodwill` /
   `i4-long-term-prepaid` / `i6-research-development-expense`（I5 无 `force_component_type`）。
4. 🔴 WHEN 判定任一 composable 是否零消费 THEN SHALL 用 **import 路径字面量**三形态
   （`from '<...mod>'` / `import('<...mod>')` / `vi.mock('<...mod>')`），**禁用符号名 grep**；
   两侧都断言（声称零消费的真零、声称有消费方的真有）。
5. WHEN 登记 mention-only THEN SHALL 对 **4 处**反向断言它们**不是** import 边
   （实测链式：`useI3DualMode.ts`→提 `useI1DualMode` · `useI4DualMode.ts`→提 `useI3DualMode` ·
   `useI5DualMode.ts`→提 `useI4DualMode` · `useI6DualMode.ts`→提 `useI5DualMode`；
   即 `useI2DualMode`/`useI6DualMode` 未被提及）。
6. WHEN 登记零消费成员 THEN SHALL 按实测：**`useI4FormData.ts`（394 行）与 `useI6FormData.ts`（448 行）
   import 生产 == 0 且 import 测试 == 0**（双零消费），两者都含完整 checklist GET/PUT + trial-balance/writeback 管道；
   🔴 **6 个 `useI{n}DualMode` 全部 import 生产 == 1**（各自父宿主）⇒ **I 循环无孤儿 dual-mode**
   （与 H 的 `useH5DualMode`/`useH7DualMode` 零消费不同）。
7. WHEN 声明主表键与 owner 常量 THEN SHALL 从常量现读，不按命名规律推断：
   `useI{1..5}Detail.ts` 各 `ITEM_ID_ROWS='I{n}-2-rows'`；
   🔴 `useI6Detail.ts` 是 `STORAGE_KEY='I6-2-detail-rows'` + `LEGACY_STORAGE_KEY='I6-2-rows'`
   ⇒ 契约 SHALL 声明「**读认两键、写只写主键**」，并断言 `LEGACY_STORAGE_KEY` 常量真存在且值为 `I6-2-rows`
   （读兼容不能悄悄消失，否则历史数据读不出）。
8. WHEN 声明 value 形态 THEN SHALL 按 stringify 位置两族：
   **host 族 = I1/I3/I6**（宿主 `JSON.stringify`）· **composable 族 = I2(`useI2Detail#L523`) /
   I4(`useI4Detail#L588`) / I5(`useI5Detail#L704`)**（composable 内先 stringify 再交）。

### Requirement 3: 三条实测超出 slice 的新事实（必须登记并落成判据）

**User Story:** 作为维护者，我要 spec 写出「slice 没说 / 说得不够精确、实测是什么、按实测走」，
而不是把 slice 当完备清单。

#### Acceptance Criteria

1. 🔴 WHEN 设计 roundtrip 的删行映射 THEN SHALL 登记 **removeRow 签名两族 3:3**（slice 未登记）：
   **按数组下标删** = `useI1Detail.ts#L623 removeRow(rowIndex: number)` ·
   `useI2Detail.ts#L505 removeRow(index: number)` · `useI3Detail.ts#L580 removeRow(rowIndex: number)`；
   **按 rowId/id 删** = `useI4Detail.ts#L672 removeRow(rowId: string)` ·
   `useI5Detail.ts#L821 removeRow(rowId: string)` · `useI6Detail.ts#L779 removeRow(id: string)`。
   ⇒ 「OO 侧删了第 N 行」在两族要走不同映射；按单一口径实现会在另一族**删错行**。
2. 🔴 WHEN 处置 I5 内置分类行的删除 THEN SHALL 登记比 slice **更精确**的事实：
   `useI5Detail.ts#L821-839` 实读 `if (row.isBuiltin) { rows.value[idx] = emptyI5DetailRow({projectName, name, isBuiltin:true, indexRef}) } else { rows.value.splice(idx,1) }`，
   而 `emptyI5DetailRow` 内部 `#L305 rowId: generateRowId()` ⇒ **重置会生成新 rowId**。
   slice 只说「原位重置为空行并保留 projectName/indexRef」、**未提 rowId 会变**。
   ⇒ 双重影响：①行数不变（按行数 / `projectName` 比对会认为没变）②**rowId 变了**
   （按 rowId 比对会认为「删一行 + 增一行」）⇒ 契约 SHALL 声明内置行稳定身份是 `projectName`/`indexRef`
   而非 `rowId`，**或**要求重置时保留原 rowId。
3. 🔴 WHEN 扫描位置化身份 THEN SHALL 登记 slice 扫描口径的**缺口**：
   `useI3Disclosure.ts#L665 rowId: \`perf-${Date.now()}-${added}\`` 与 `#L725 rowId: \`ap-${Date.now()}-${added}\``
   —— `${added}` 是批量新增的**局部递增计数**（不是数组下标），slice 冻结的判据正则
   （`${i}`/`${idx}`/`${index}`/`${seq}`/`?? i`/`|| i`/`indexOf(`）**不覆盖它**。
   风险：同一毫秒内两次批量插入且 `added` 均从 0 起会撞 ⇒ 属**族 D**（弱于 family_b 但非零）。
   判据 SHALL 把扫描正则扩到覆盖 `${added}` 形态，并断言命中 **2 处**。
4. WHEN 登记「slice 全部承重结论经独立复算相符」THEN SHALL 写明复算范围：
   8 条 CD 中 5 条源区间逐格字节（CD-1/CD-2/CD-3/CD-4/CD-8）· ID-3 的 12 个 composable 消费方计数 ·
   ID-1/ID-2/ID-5 的宿主命中计数 · 6 条 owner 常量实值 · BP-6 的 family_a/b 与 3 处位置化标签 ·
   manifest 6 条字段 · 模板 6 文件 size。
   🔴 **这是 D/E/F/G/H/I 六份 slice 里唯一一份零反驳的** —— 该结论本身也要现算维持，不得当永久结论。

### Requirement 4: I 专属前置 BP-5 ~ BP-10 的处置边界

#### Acceptance Criteria

1. WHEN 处置 **BP-5**（两个孤儿 production FormData）THEN 本 spec SHALL 交付 IC-3 判据 +
   🔴 **canary 内的禁接判据**（I6 的真实载体是 host_inline，`useI6FormData` 是死代码，
   接线时若接到它 ⇒ 宿主行为不变而守卫因「文件确实被改了」全绿 = **假绿第①源**）；
   `useI4FormData` 的处置归 `i2-i4-i5-carrier-and-structure-exceptions`。
2. WHEN 处置 **BP-6**（披露层位置化行身份）THEN 本 spec SHALL 交付 IC-6 四族分治裁决 + 扫描口径扩充；
   修复归 `i1-i3-disclosure-positional-identity-and-classification-source`。
   🔴 SHALL 登记 **entry 维度是 2（I3 7 处 + I1 1 处）而 site 维度是 8**（族 A′ 1 + 族 B 5 + 族 D 2）
—— 不分开会把「2」当成「8 条 entry 都有」；且族 B 第 5 处在 `.vue`（`I3TabRecoverableTest.vue#L686`），
扫描 SHALL 按形态口径而非只扫 `composables/`。
3. WHEN 处置 **BP-7**（`I1_SOE_CATEGORIES` 与两个真源都不符）THEN 本 spec SHALL 交付 IC-5 三边校验裁决；
   修复归 lane 1，且 🔴 SHALL 登记**修复动作原属已归档的附注同步 spec**（改常量会同时改附注列头）
   ⇒ **须新立任务**，本 spec 与 lane 1 只登记不改附注侧。
4. WHEN 处置 **BP-8**（两条 entry 的分类枚举含无真源标签）THEN 本 spec SHALL 交付 IC-5 判据；
   BP-8①（I6 `I6_DETAIL_DEFAULT_CATEGORIES` 后 4 条）**后置**（分类只作 `category` 字段值不是行身份，
   不阻塞 canary）；BP-8②（I4 `CATEGORY_OPTIONS` 第 2~4 条）归 lane 2。
5. WHEN 处置 **BP-9**（manifest capability）THEN 本 spec SHALL 交付 IC-1 全部正文与迁移路径
   （必须走 `register_from_manifest()`，**禁手改 manifest 文件**），与 FC-12 / G BP-6 / H HC-1 同源。
6. 🔴 WHEN 处置 **BP-10** THEN SHALL 登记它在 I 是「**从零补**」不是「已有待改」（**与 H 相反**）：
   6 宿主**全无** `GtEntrySyncCapabilityNotice.vue`、**全无** `workpaperEntrySyncNotice.ts` 引用；
   现状的 `el-tag 仅结构化视图` 只在「OO 健康探测失败」时出现（5 条有、**I2 连这个都没有**），
   完全不覆盖「未注册 adapter ⇒ 不得显示可双向回写并显示可操作原因」。
   本 spec SHALL 在 canary 内建第一处 notice 挂载（作为后两份 lane 的范式）。

### Requirement 5: 首张 canary（I6 研发费用明细表 I6-2）端到端打通

**User Story:** 作为实施者，我要一条**有真库非空载荷**且**几何最简**的 entry 先打通全链路。

#### Acceptance Criteria

1. WHEN 选定 canary THEN SHALL 是 **I6**，并 SHALL 在 design 记录三条硬依据与三条逆风（§canary 选型）；
   🔴 判据 SHALL 现算 `checklist_responses` 确认 `I6-2-detail-rows` 非空（实测 **194 B / 2 行**），
   且确认 I1/I2/I3/I4 主表键 + `I6-2-rows`(legacy) 全部零载荷。
2. WHEN 声明 I6-2 几何 THEN SHALL 按实测：**单级表头 R8** · 数据区 **R9-18（10 行）** ·
   footer **R19 合计** + 🔴 **R20「各月比例」第二 footer** · **有效列 26 / `max_column` 65** ·
   84 个公式 · merged **2** · 裸 IF **45（全 I 最少）** · definedName **0**。
3. WHEN 声明 I6-2 列语义 THEN SHALL 覆盖实测 26 列全集：`A=类别` · **B-M = 1月..12月** ·
   `N=本期未审合计`(`=SUM(B9:M9)`) · `O=账项调整` · `P=重分类调整` · `Q=本期审定数`(`=N9+O9+P9`) ·
   `R=各项目占比`(`=IF(Q9=0,0,Q9/$Q$19)`) · `S=与相关科目勾稽`（🔴 **文本列**，模板值「开发支出等」）·
   `T=上期未审数` · `U=上期账项调整` · `V=上期重分类调整` · `W=上期审定数`(`=T9+U9+V9`) ·
   `X=个别报表下的重分类` · `Y=合并报表下的重分类` · `Z=备注`。
4. 🔴 WHEN 声明 I6-2 representation THEN SHALL 覆盖真库实证形态
   `[{"category":"智能平台研发","months":[500000,0,…],"aje":0,"rje":0}]`：
   ① **`months` 是 12 元素数组**（对应 B-M 列）⇒ 嵌套路径声明，**同源引用** F5-2 `months/0` 族规则；
   ② 🔴 **那 2 行没有 `id` 字段** ⇒ `useI6Detail.ts#L303 raw.id ?? raw.rowId ?? \`row-${Date.now()}…\``
   会每次兜底生成新 id，roundtrip 会判成「全删全增」⇒ 契约 SHALL 声明
   「**读时兜底生成的 id 必须持久化回写一次**」或改用业务键作稳定身份；
   ③ 中英双字段名（`useI6Detail.ts#L516 r.类别 || r.category` / `#L517 r.本期审定 ?? r.auditedAmount`）
   ⇒ representation **不得只声明一侧**，须标注中文键是历史/导入路径形态、英文是当前真库形态。
5. WHEN canary 通过 THEN SHALL 产出 `i6.research_development_expense_detail.json` 契约 + provider
   `phase5_research_development_expense_detail`，并 SHALL 走 `register_from_manifest()` 注册；
   🔴 provider 范式 SHALL 是 `phase5_*`（**不照** pilot 的 `pilot_*`），
   唯一复用 pilot 的是 `oo_crash_neutralization_fn`。
6. 🔴 WHEN 声明 canary 的键约束 THEN SHALL **冻结 `I6-2-detail-rows` 键名**：
   实测 5 个消费方中 4 个不属 I6 —— `expenseWpI1AmortPull.ts` ·
   **`h1DepAllocCounterpartPull.ts`（H1 pilot，adapter 已注册、golden 已锁）** ·
   `h8DepAllocCounterpartPull.ts` · `i1AmortAllocCounterpartPull.ts` · `useI2Analysis.ts`
   ⇒ 本 spec 只补契约与 adapter、**不动键名**；每次改动完成后 SHALL 回归 **H1 契约 golden digest**
   且 **不得修改 H1 的契约 / adapter / golden**。
7. 🔴 WHEN canary 接线 THEN SHALL 断言**不接** `useI6FormData`（BP-5②，双零消费死代码），
   并断言宿主/Tab 侧**确实引用了新载体**；变异「把 `useI6FormData` 当载体接上」SHALL 打红。
8. WHEN canary 覆盖 TB 发布链 THEN SHALL 利用 🔴 **I 循环 6/6 全有发布门**这一事实
   （与 H 的 H8/H9 完全无门相反）：I6 的门在 `useI6Adjudication.ts`（`publishToTb`×3）+
   `i6/core/I6TabAdjudication.vue`（×2）⇒ **canary 可直接覆盖发布链**，不需外移首例。
   发布 SHALL 走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` + 二次确认；
   🔴 **禁在 `watch`/`onMounted`/debounce 回调内发布**。

### Requirement 6: 分类/行模型三边校验（IC-5，继承 slice 首创节）

**User Story:** 作为维护者，我要「声明」与「实现」同时错成一致时判据仍能打红 ——
第三边（源字节）是唯一能兜住这种情形的。

#### Acceptance Criteria

1. WHEN 校验任一分类/行模型常量 THEN 判据 SHALL 是**三边**：
   ①声明的 `工作簿!sheet!cell` ②openpyxl **真读**那个区间得到的字面文本 ③impl 常量里对应位置的 label；
   断言 ②==③ 且 ① 可解析。
2. 🔴 WHEN 比对 THEN SHALL 用**有序等值**比对，**不得**用集合比对（顺序也是行模型的一部分 ——
   BP-7 的缺陷之一正是 impl 把 `软件` 提到首位而源里是第 8 条）。
3. WHEN 实施 THEN SHALL 遵守 slice 冻结的**四条 forbidden_shortcuts**：
   只断言 sheet 名在 `workbook.sheetnames` 里 · 只断言 cell 非空 · 用集合比对代替有序比对 ·
   把 impl 常量硬抄进守卫常量（那是第二真源，改了实现不改守卫就假绿）。
4. WHEN 登记 8 条 CD 的裁定 THEN SHALL 按实测（本轮已独立复算 5 条源区间字节，与 slice **全部相符**）：
   **clean 4**（CD-1 I1 `I1_DEFAULT_CATEGORIES` / CD-3 I5 `I5_BUILTIN_CATEGORIES` /
   CD-5 I2 无 impl 常量 by design / CD-7 I3 源自身派生自明细）·
   **defect_registered_not_fixed 3**（CD-2 I1 `I1_SOE_CATEGORIES` MISMATCH=BP-7 /
   CD-4 I6 `I6_DETAIL_DEFAULT_CATEGORIES` PREFIX_MATCH_WITH_UNSOURCED_TAIL=BP-8① /
   CD-8 I4 `CATEGORY_OPTIONS` 同型=BP-8②）· **scanned_and_classified_not_a_defect 1**（CD-6 I2
   `defaultPerCapitaPeers` 硬编码种子行数）。
   🔴 计数 SHALL 按 **status 维度**现算并与 slice 的 summary 等值比对
   （`no_impl_classification_by_design` 是 **verdict 维度**的子集，**不与三个 status 数相加**）。
5. WHEN 登记 CD-1 的 additional_evidence THEN SHALL 写明**源模板自己就把 `底稿目录!A9:A19` 当分类真源**：
   `附注披露信息（上市公司）!B10..L10` 逐格是 `=底稿目录!A9`..`=底稿目录!A19` 的公式引用；
   🔴 **K10 例外是字面 `数据资源`**，且实测 `明细表I1-2!A29` 也是字面 `数据资源`（第二处断链）·
   `明细表I2-2!A17` 是字面 `数据资源`（第三处）⇒ 改 `底稿目录!A18` **不会传播到这三处**，
   是模板侧的真源断链，SHALL 登记（本轮不修模板字节）。
6. WHEN 登记稳定 key 与 label 分离 THEN SHALL 断言 `i1CategoryColumnKey` 生成 `{slot.key}_{slot.seq}`
   （`i1CategoryScope.ts#L34-36`）符合 H7 范式 SK-1；🔴 并反向断言全 I 的 `key: X.label` 与
   `row[X.label]` 命中 **0**（H8 那族缺陷在 I 不存在）。

### Requirement 7: 模板侧事实与 instrumentation 边界

#### Acceptance Criteria

1. WHEN 挂 OO 崩溃中性化 THEN SHALL **per-file** 挂 `oo_crash_neutralization_fn`（IC-9），**不得**整册统一；
   判据 SHALL 覆盖 6/6 全命中的实测计数：I1 **321** · I4 186 · I2 113 · I3 63 · I5 49 · I6 **45**（总 777）。
2. 🔴 WHEN 断言「干净点」THEN SHALL **区分可断言「保持为无」与必须登记基线值两类**（IC-10）：
   可断言为无五项 = 合计漏加小计 **0 格** · `max_column≥200` 宽表 **0 张** · 同尾码双 sheet **0 组** ·
   整册码回落 **clean**（31 个 I 码逐个实跑 `find_template_file`/`_any`）· `key: X.label` **0 命中**；
   🔴 **definedName 不是 0** —— 实测 I4 **476** / I5 **334**、其余 4 册 0 ⇒
   **必须改成登记基线值 + 断言不增长**，照抄 H 的「9 册全 0」在 I 会直接假红。
3. WHEN 放 UUID 列 THEN SHALL 放「**有效内容列 +1**」而非 `max_column+1`：
   实测差值大的四条 = I2 **20/61** · I6 **26/65** · I1 **47/56** · I4 **22/25**（I3 30/30 · I5 17/26）
   ⇒ UUID 落位 I1 48 · I2 21 · I3 31 · I4 23 · I5 18 · I6 27。**同源引用** G/H 的同一规则。
4. WHEN 声明 footer 形态 THEN SHALL 按 **IC-13 四形态 + 多 footer**：
   纯 SUM（I1 R18 / I2 R23 / I4 R23）· 🔴 **第四形态「合计行套用行公式」**（I3-2 R23
   `I23=SUM(D23:E23)-G23` / `M23=D23+J23` / `N23=E23+K23`，且**左右两区约定不一致** ——
   右区 `W23=SUM(W14:W22)` 用纯 SUM）· **三 footer**（I5-2 R22/R35/R48）·
   **双 footer**（I6-2 R19 + R20，同 H10-2 同源引用）。
5. 🔴 WHEN 登记 I3-2 模板真实金额错误 THEN SHALL 按 **IC-14**：`明细表I3-2!AA23:AD23` 四格
   `=SUM(AA27:AA30)` / `=SUM(AB27:AB30)` / `=SUM(AC27:AC30)` / `=SUM(AD27:AD30)`，
   正确区间应是 `AA14:AA22`（数据区 R14-22）；**R27-29 实为「编制说明」文本区、R30 超出 `max_row`=29**
   ⇒ **减值准备区审定数四列（期初数/本期增加/本期减少/期末数）合计恒 0**；
   同行左侧 `S23..Z23` 全部正确 `=SUM(x14:x22)`；四格错法一致 = 复制粘贴错误。
   处置 SHALL 走**模板覆盖层不改字节**（`backend/wp_templates/` 运行时只读 + sha 冻结），
   同族先例 F2-26!J9 · F5-7!G31 · G5-2 45 格 · G5-1!B35；修复归 lane 1。
6. WHEN 登记 I6-2 的小缺陷 THEN SHALL 登记不修：R19 合计行把 **B19..Y19 全部写成 `=SUM(x9:x18)`**，
   其中 `S19=SUM(S9:S18)` 对**文本列**求和恒 0（无意义合计）、`R19=SUM(R9:R18)` 对占比列求和（语义勉强）。
7. WHEN 声明表头层级 THEN SHALL 按实测：**四级**（I1 R8-R11 · I3 R10-R13）· **三级**（I2 R10-R12 · I4 R8-R10）·
   **两级**（I5 R8/R9）· **单级**（I6 R8）。
8. WHEN 登记模板其他事实 THEN SHALL 断言：6 册 **86 sheets** · **无一个 Excel Table** ·
   🔴 **6 册全有 `GT_Custom` hidden sheet**（H 只 H9/H10 两册）· I3 另有 `市场平均收益率2017`（hidden, 167r）。

### Requirement 8: sheet 命名四陷阱与 wp_index 禁依赖

#### Acceptance Criteria

1. 🔴 WHEN 契约按 sheet 定位 THEN SHALL 用**模板 sheet 全名**作唯一真源，并按 **IC-11 四陷阱**容错：
   ①**`审定表I1` 不带 `-1`**（其余 5 册是 `审定表I{n}-1`）⇒ 按 `审定表I{n}-1` 模式定位在 I1 上失配
   ②两张 sheet 尾码后还跟**括号后缀**（`摊销测算表（不含减值）I1-10（剩余年限法）` /
   `摊销测算表I4-7（工作量法）`）⇒ 按 `尾码$` 锚定失配
   ③**I3 两张参考/数据页须进排除清单**：`参考－商誉减值测试示例`（104r/114f，🔴 **非 hidden**，
   🔴 用**全角连字符 `－`** 不是 `-`）· `市场平均收益率2017`（hidden, 167r）
   ④附注披露命名两族：**I1 是 `附注披露信息（上市公司）`/`（国有企业）`**（多「信息」二字），
   其余 5 册是 `附注披露（上市公司）`/`（国有企业）`。
2. WHEN 需要命名口径先例 THEN SHALL 登记 🔴 **prefill 侧已正确使用 sheet 全名**
   （`prefill_formula_mapping.json` 的 16 条 I mapping 里 `审定表I1` 与两张括号后缀 sheet 都用全名）
   ⇒ 契约照此口径。
3. 🔴 WHEN 契约声明 `sheet_code` THEN SHALL **绝对禁止依赖 `wp_index`**（IC-12）：
   ①`I2-1` **一码两名两底稿**（`商誉减值测试` x1 vs `开发支出审定表` x3 —— 指**完全不同的底稿**，
   比 H 的 `H1-2` 同底稿不同名严重）
   ②**wp_index 子码与模板 sheet 尾码是两套不同编号体系**（实测举例：wp_index `I1-3=无形资产摊销测算`
   vs 模板 `I1-3=调整分录汇总I1-3`；`I1-4`/`I1-5`/`I2-3`/`I3-3` 同类）
   ③wp_index 有 `I6-7`/`I6-8` 但模板只到 `I6-6`
   ④仅少数一致：`I{n}-2` 明细表 ✓ · `I1-10`/`I1-11` 摊销测算表 ✓。
4. WHEN 登记 wp_index 多行 THEN SHALL 断言根因是 **project_id 维度**（每项目一行），**不是重复缺陷**。

### Requirement 9: 派生区、派生合计与 representation 未证实项

#### Acceptance Criteria

1. WHEN 声明多区结构 THEN SHALL 按 **IC-19** 把第二/三区声明为 **derived、不纳入业务行比对**：
   I1 双区（数据 R12-17 + **R19「其中：」+ R20-30** 分类汇总，A 列逐格 `=底稿目录!A9`..`A19`，
   `F20` 用 `SUMPRODUCT(($B$12:$B$17=…)` 按 B 列回汇总第一区）·
   I4 双区（R11-22 + **R24「其中：」+ R25-28**，A 列 `=底稿目录!A9`..`A12`）·
   I5 三区（原值 R11-21 / 减值准备 R24-34 A 列 `=A11`..`=A21` **镜像** /
   净值 R37-47 A 列 `=A24`..`=A34` 且数值逐格 `=B11-B24` ⇒ **第三区完全派生**）。
2. WHEN 声明 `derived_total_keys` THEN SHALL **现算**（IC-18）：当前现算 **13 个**
   （I1 **8** · I2 2 · I6 3 · **I3/I4/I5 各 0**），与 H 的 **89 个**差一个数量级
   ⇒ 仍须排除 roundtrip 业务比对并指定重算责任方，但不构成主要工作量；
   🔴 判据与**现算基线**比对，**禁写死阈值**。
   清单：`I1-10-period-amort-total` · `I1-11-period-amort-total` · `I1-12-supplement-total` ·
   `I1-5-period-total` · `I1-9-alloc-totals`（🔴 注意**复数**）· `I1-adj-amort-increase-total` ·
   `I1-adj-cost-increase-total` · `I1-adjudication-cost-addition-total` · `I2-1-audited-total` ·
   `I2-15-supplement-total` · `I6-1-audited-total` · `I6-adj-audited-total` · `I6-adj-expected-total`。
3. 🔴 WHEN 声明 payload 列形态 THEN SHALL 标 `unverified_in_live_db`（IC-8③）：
   slice 记三形态（`remark_only_conclusion_null` 4 条 / I4 `dual_write_remark_and_conclusion_for_status_marker` /
   I5 `passthrough_remark_and_conclusion`），但真库 **7 行全部 remark_only**
   （`both=0` / `conclusion_only=0`，I5 那行 `concl_max=None`）
   ⇒ **dual_write 与 passthrough 声明未被真库证实**；SHALL 在 canary 前置实证或降级声明，
   **不得**把 slice 声明当已验证事实。
4. WHEN 处置 `useI2Detail.ts#L408` 的 `rowId: '__total__'` THEN SHALL 把它**排除在业务行之外**
   （固定身份的派生合计行，与 H5/H7 的 `rowId: 'subtotal'` 同型）。
5. WHEN 登记 `useAdjustmentCentralSync` THEN SHALL 断言 **6/6 全覆盖**
   （`i{1..6}/core/I{n}TabAdjustment.vue` 各 3 处引用、宿主层 0）⇒
   roundtrip SHALL 把它视为 primary 表之外的**第二写入方**。

### Requirement 10: Property 20 的空分母纪律

#### Acceptance Criteria

1. 🔴 WHEN 论证 Property 20 THEN SHALL **不宣称通过**其 contract 维度（I 循环 **0 契约** ⇒ 空分母重言式）；
   SHALL 改在**非空同型分母**上验 —— 8 条 CD 的 stable key / label 来源分离。
2. WHEN 实施该判据 THEN SHALL 真验四件事：①逐文件读 `workpaper_sync_contracts/*.json` 的 `review.entry_id`，
   断言无一条属本 slice 6 条 entry（🔴 **不是数文件个数** —— 契约目录现算 **17 个**，slice 冻结时记 5 个）
   ②承载字段级判据的 pilot 守卫文件真存在 ③8 条 declaration 逐条断言「稳定 key 与可变 label 分离」
   ④反向断言 `col_[a-z]+` 形态的无语义占位在 I 的分类常量里命中 **0**。
3. WHEN 声明零回归基线 THEN SHALL **现算**（GC-10 / IC-17），**不得**写死契约数或注册集
   （现算：契约 17 个 · `register_from_manifest()` 已注册 `{d2,d4,g7,h1}`）。

---

## 阻塞项（BP-1 ~ BP-4，6 条 entry 共有的平台级供给）

沿用 FC-13 逐元素口径，本 spec **不承诺**在缺供给时交付，相关任务在 tasks.md 标 `[ ]*`：

- **BP-1** Task 17 的 non-current instrumentation candidate + Task 36 finalize 的 published representation
- **BP-2** 人工审核的 per-entry contract（🔴 现算 17 份契约无一条 `review.entry_id` 以 `xlsx/gt-i` 开头）
- **BP-3** approved authority model + non-null approved definition bundle
- **BP-4** 真 OnlyOffice 9.4 的 required scenario set（`evidence.sync_test_run_id` 与
  `required_scenario_set_digest` 全为 null）

🔴 这四条是**全循环共有**（D/E/F/G/H/I 同）；I 专属是 BP-5 ~ BP-10。
