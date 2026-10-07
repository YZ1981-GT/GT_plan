# K8/K9/K11/K12/K13 专用 composable 与跨循环枢纽 — 需求

## 引言

本 spec 覆盖 **K 循环 5 条 entry（K8 / K9 / K11 / K12 / K13）**，它们的共同特征是 **BP-6 组**：宿主 **import 专用 dual-mode composable**（各 1 条生产边，非 orphan），且该 composable **直调两个 legacy 端点**。

🔴 **BP-6 的全集是 6 条（K8~K13），其中 K10 已在 foundation 作 canary 完整交付** ⇒ 本 spec 是 BP-6 的**剩余 5 条**。

**上游**：`k-cycle-sync-foundation-and-first-canary` 的 **KC-1 ~ KC-24**（🔴 **只引用编号，不复述正文**）。
**Property 前缀**：`KB-P`（spec-scoped）。

### 本 spec 的 5 条 entry（全名，无缩写）

| entry_id | wp_code | 宿主 | dual-mode composable | sheets | 键 | 裸 IF | BP-8 | 真库非空键 |
|---|---|---|---|---|---|---|---|---|
| `xlsx/gt-k8-selling-expenses` | `K8S` | `GtK8SellingExpenses.vue` | `useK8DualMode.ts` | 12 | 86 | **136** | **8** | 1 |
| `xlsx/gt-k9-admin-expenses` | `K9A` | `GtK9AdminExpenses.vue` | `useK9DualMode.ts` | 12 | 79 | **175** | **7** | 3 |
| `xlsx/gt-k11-asset-impairment-loss` | `K11A` | `GtK11AssetImpairmentLoss.vue` | `useK11DualMode.ts` | **7** | 48 | 39 | **4** | **0** |
| `xlsx/gt-k12-non-operating-income` | `K12N` | `GtK12NonOperatingIncome.vue` | `useK12DualMode.ts` | 9 | 53 | 37 | **2** | 2 |
| `xlsx/gt-k13-non-operating-expense` | `K13N` | `GtK13NonOperatingExpense.vue` | `useK13DualMode.ts` | 9 | 57 | 37 | **0** | **0** |
| **合计** | — | 5 宿主 | 5 composable | **49** | **323** | **424** | **21** | **6** |

🔴 **三处结构性特殊**：
- **K13 的 BP-8 位置化命中为 0**（K 循环零缺陷 4 条 entry 里的 1 条）⇒ 本 lane 的**对照组**
- **K11 与 K13 真库完全无行**（0 键）⇒ roundtrip 须用合成载荷
- **K11 是跨循环枢纽**（被 H1 pilot / H3 / H8 / I1 四方消费）

🔴 **本 lane 裸 IF 424 是三份 spec 里最高的**（占 13 entry 册 715 的 59%），其中 K9 **175** 与 K8 **136** 是全 K 前两名。

🔴 **所有计数一律现算，禁写死；判据锚点用常量名 / 端点字面量 / 形态特征，禁写死行号。**

---

## Requirement 1：BP-6 —— 5 个 live composable 的 legacy 端点直调收口

**User Story:** 作为迁移实施者，我需要这 5 个在用的 composable 的 legacy 端点直调被删净，这样不会 legacy 与 bridge 双路并存。

### 验收准则

1. **WHEN** 判定「在用」**THEN** SHALL 现算 5 个 `useK{n}DualMode.ts`（n ∈ {8,9,11,12,13}）**各恰 1 条生产边**、测试边 0，且该边指向的宿主与 slice 的 `dual_mode_carrier.site` 一致。
2. 🔴 **WHEN** 与 lane 1 反向对照 **THEN** SHALL 同时断言 lane 1 的 7 个 `useK{n}DualMode.ts`（n=1..7）**生产边与测试边各为 0**（两侧都验，证明本 lane 的「各 1 条边」不是漏扫）。
3. **WHEN** 现算 legacy 端点 **THEN** SHALL 得：

| composable | `onlyoffice/health` | `onlyoffice-config` |
|---|---|---|
| `useK8DualMode.ts` | 1 | **2** |
| `useK9DualMode.ts` | 1 | **2** |
| `useK11DualMode.ts` | 1 | **2** |
| `useK12DualMode.ts` | 1 | 1 |
| `useK13DualMode.ts` | 1 | 1 |
| **本 lane 合计** | **5** | **8** |

🔴 加上 foundation 的 K10（health 1 / config 1）⇒ BP-6 全集 6 个 composable 的 config 合计 **9 处 / 6 文件**；slice 的 `dual_mode_modules_calling_legacy_config_endpoint = 6` 是**文件数不是处数**（引用 KC-3）。
4. 🔴 **WHEN** 扫端点 **THEN** 正则 SHALL **认反引号模板字面量** —— 这 8 处 config 直调全是 `` `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config` `` 形态，只认单/双引号会漏成 0（引用 KC-3）。
5. **WHEN** 处置 **THEN** 5 个 composable 的两类端点直调 SHALL 全部改走 sync bridge 的 materialize 协议；断言处置后本 lane 的 `onlyoffice/health` 命中降为 **0**、`onlyoffice-config` 降为 **0**。
6. **WHEN** 核 localStorage **THEN** 5 个 composable SHALL 各维护一份 `k{n}-dual-mode:` 前缀（现算 `useK8` 2 处 · `useK9` 2 · `useK11` 2 · `useK12` 3 · `useK13` 3）⇒ SHALL 收敛到 `workpaper-sync-mode:`；🔴 列偏好类 `useK10DetailColumnPrefs.ts` / `useK11DetailColumnPrefs.ts` / `useK10GrantColumnPrefs.ts` **不动**（引用 KC-18）。

---

## Requirement 2：KC-15 —— K8/K9 的 `disabled` 门控形态（不是 `v-if`）

**User Story:** 作为守卫作者，我需要 K8/K9 的门控形态被单独识别，这样不会把它们假红。

### 验收准则

1. **WHEN** 现算宿主层 `v-if="dualMode.isOoAvailable.value"` **THEN** SHALL 得 **K11 / K12 / K13 各 1 处**，🔴 **K8 / K9 为 0**。
2. 🔴 **WHEN** 找 K8/K9 的门控 **THEN** SHALL 去 **composable** 里找 `disabled: !isOoAvailable.value`（在 `useK8DualMode.ts` 与 `useK9DualMode.ts` 的 `modeOptions` computed 里，宿主层命中 **0**）⇒ 这是 D4 的「always-visible + disabled」范式。
3. **WHEN** 立判据 **THEN** SHALL 写成二分支：「有 `v-if` 二级门控」**或**「composable 里有 `disabled: !isOoAvailable`」⇒ 统一写「必须有 `v-if`」会**假红 K8/K9**。
4. **WHEN** 核 `el-segmented` **THEN** SHALL 先 `stripComments()`，断言剥后 5 宿主**各恒 1 处**（剥前 K8/K9/K11/K12/K13 多数为 2 处，第二处在块注释里）。
5. **WHEN** 核 `isOoAvailable` 宿主层命中 **THEN** SHALL 现算 **K8 = 0 · K9 = 1 · K11 = 3 · K12 = 2 · K13 = 3** ⇒ 🔴 **K8 宿主完全不引用该符号**（全在 composable），判据按宿主层扫会漏。

---

## Requirement 3：KC-8 —— K11 跨循环枢纽的键冻结

**User Story:** 作为实施者，我需要 K11 的键被冻结，这样改名不会打断 H1 pilot 的 golden。

### 验收准则

1. 🔴 **WHEN** 核 K11 的被消费关系 **THEN** SHALL 现算：

| K11 键 | 消费方 |
|---|---|
| `K11-2-detail-rows` | `useH1Impairment.ts`（🔴 **H1 = adapter 已注册的 pilot**）· `useH8Impairment.ts` · `useI1Impairment.ts` · `h3ImpairmentCrossSheet.ts` |
| `K11-2-fixed-asset-occurrence` | `useH1Impairment.ts` |
| `K11-2-rou-occurrence` | `useH8Impairment.ts` |
| `K11-2-intangible-occurrence` | `useI1Impairment.ts` |
| `K11-2-intangible-source-amount` | `useI1Impairment.ts` |
| `K11-source-H1-amount` | `useH1Impairment.ts` |
| `K11-source-H3-amount` | `h3ImpairmentCrossSheet.ts` |
| `K11-source-H8-amount` | `useH8Impairment.ts` |
| `K11-source-I1-amount` | `useI1Impairment.ts` |

2. **WHEN** 立冻结清单 **THEN** 上述 **9 个 K11 键**一律**不得改名**；改动 SHALL 触发 **H1 pilot golden 回归**（H1 的 `adapter_id` 现算非空、契约 `h1.disposal_check.json` 已 reviewed）。
3. **WHEN** 核全局 **THEN** SHALL 现算「非 K 域文件消费的 K 键」= **70 个**（含大量 `cycleImportExportRegistry.generated.ts` 的 sheet 码）；反向「K 域文件引用的非 K 循环键」仅 **4 种**（`b19-alert` 2 处 · `b19-tag` 1 · `H1-14-supplement-total` 1 · `H1-14-calc-rows` 1）。
4. 🔴 **WHEN** 与 J 循环对照 **THEN** SHALL 显式登记「JC-17 在 J 是**完全自闭**（J 键无一被非 J 消费），K 是**强命中** ⇒ **照抄 J 的自闭结论会漏掉整条跨循环风险**」。
5. **WHEN** 核 K11 真库 **THEN** SHALL 现算 `K11-%` 行数 == **0** ⇒ 🔴 **K11 键有跨循环消费方但真库无载荷** ⇒ roundtrip 须用合成载荷标 `synthetic_payload_no_live_db_baseline`，且 H1 golden 回归须用 H1 侧自己的载荷。

---

## Requirement 4：BP-8 —— 本 lane 的 21 处位置化行身份

**User Story:** 作为实施者，我需要本 lane 的 21 处位置化按族分治。

### 验收准则

1. **WHEN** 现算本 lane 的 defect 分布 **THEN** SHALL 得 **21 处**：K8 **8** · K9 **7** · K11 **4** · K12 **2**；🔴 **K13 为 0**（对照组）。引用 KC-6 的判别式，不复述。
2. 🔴 **WHEN** 核 K8/K9 的截止性测试表 **THEN** SHALL 发现**同一张表两条路走两套身份**：
   - 新增行路径：`useK8Cutoff.ts` / `useK9Cutoff.ts` 的 `` rowKey: `row-${idx}-${Date.now()}` `` ⇒ **family_c（安全，非缺陷）**
   - 反序列化路径：同文件的 `` raw.rowKey ?? `row-${idx}` `` ⇒ **family_b（缺陷，静默退化成位置化身份）**
   ⇒ **「主身份机制干净」不等于「该表干净」**，判据必须两条路都扫。
3. **WHEN** 核 family_c 的 3 处 **THEN** SHALL 现算全 K 只 3 处，其中 **2 处在本 lane**（`useK8Cutoff.ts` / `useK9Cutoff.ts`），第 3 处 `K6TabImpairmentTest.vue` 的 `` rowId: `row-${Date.now()}-${i}` `` 在 lane 1。
4. 🔴 **WHEN** 核 `positional_row_id_template` 的 13 处 **THEN** SHALL 现算本 lane 占多数（含 `useK8Cutoff.ts` 两处 · `useK9Cutoff.ts` 两处 · `K11TabDisclosureListed.vue` 两处 · `K11TabDisclosureSoe.vue` 两处等），且这 13 处 SHALL 是位置化 48 处的**子集**（引用 KC-24）。
5. **WHEN** 核 K8-6 真库载荷 **THEN** SHALL 现读确证 family_c **真落库**：`{"rowKey":"row-0-1784807974207","index":1,"voucherNo":"0285","bookDate":"2025-12-26","amount":79.97,"accountCode":"6601.15.01","accountName":"销售费用_车辆运行费_路桥费"}` ⇒ `idx=0` 与 13 位时间戳都在，另有 `index` 展示序号字段（**family_d 不计入 total_hits 的实证**）。
6. **WHEN** 处置 **THEN** 已落库 id SHALL **grandfather 不重写**；反序列化路径的 `?? \`row-${idx}\`` 兜底 SHALL 改为「缺身份时生成新的值化身份」而不是退化成下标。

---

## Requirement 5：K8/K9 截止性测试双 sheet 的方向变体

**User Story:** 作为契约作者，我需要 K8/K9 的双 sheet 是「方向变体」而不是「同尾码变体」被讲清，这样不会照抄 HC-5/JC-11 的判据。

### 验收准则

1. **WHEN** 核 K8/K9 的截止性测试 sheet **THEN** SHALL 现算**各两张不同尾码**：

| 册 | sheet | 尾码 | 几何 |
|---|---|---|---|
| K8 | 🔴 `截止性测试(从记账凭证至原始凭证）K8-6` | `K8-6` | r=44 c=11 |
| K8 | `截止性测试（从原始凭证至记账凭证）K8-7` | `K8-7` | r=44 c=12 |
| K9 | 🔴 `截止性测试(从记账凭证至原始凭证）K9-6` | `K9-6` | r=44 c=11 |
| K9 | `截止性测试（从原始凭证至记账凭证）K9-7` | `K9-7` | r=44 c=12 |

2. 🔴 **WHEN** 判是否命中变体轴 **THEN** SHALL 断言 **HC-5 / JC-11 的「同尾码双 sheet」在 K 全域为 0** ⇒ 这四张是**不同尾码的方向变体**（记账凭证→原始凭证 vs 原始凭证→记账凭证），不是同尾码变体；照抄那两条判据会误判。
3. 🔴 **WHEN** 核 sheet 名 **THEN** SHALL 发现 `K8-6` 与 `K9-6` 两张的括号是**半角左 + 全角右**（`(从记账凭证至原始凭证）`）而对应的 `-7` 两张是**全角配对** ⇒ 本 lane 占 KC-10 的「括号半/全混不配对 5 处」里的 **2 处**（另 3 处 K1/K5/K6 在 lane 1），2 + 3 == 5 ✓。
4. **WHEN** 核采样端点 **THEN** SHALL 现算 `POST /api/projects/{X}/sampling/cutoff-test` 命中 **2 文件**（K8/K9 各 1）⇒ 截止性测试有专用后端能力，契约须声明它不是 checklist 写路径。

---

## Requirement 6：真库空载荷的 roundtrip 策略

**User Story:** 作为实施者，我需要 K11/K13 真库无载荷时的 roundtrip 有明确策略，这样不会伪造实证。

### 验收准则

1. **WHEN** 核本 lane 真库 **THEN** SHALL 现算非空键 **6 个 / 载荷合计 15,721 B**：

| entry | 非空键 | 载荷 |
|---|---|---|
| **K8** | **1** | `K8-6-rows` **195,960 B** |
| **K9** | **3** | `K9-1-rows` 11,549 B · `K9-1-audited-by-item` 3,905 B · `K9-1-audited-total` 1 B |
| K12 | 2 | `K12-review-session-{时间戳}` 262 B · `K12-4-check-rows` 2 B |
| 🔴 **K11 / K13** | **0** | **真库完全无行** |

🔴 **算术须现算裁定**：上表非空键 1+3+2+0+0 = **6** ✓；但载荷合计 195,960 + 15,455 + 264 = **211,679 B**（design 的 15,721 B 口径不含 K8，实施时须现算裁定统一口径）。
2. 🔴 **WHEN** K11 / K13 跑 roundtrip **THEN** SHALL 用合成载荷并标 `synthetic_payload_no_live_db_baseline`，**不得宣称有真库实证**。
3. **WHEN** K8 跑 roundtrip **THEN** SHALL 用真库 `K8-6-rows` 的 **195,960 B** 真业务载荷（含真凭证号 / 真日期 / 真金额 / 真科目码）⇒ 🔴 **本 lane 有 K 域第二大真实载荷**，金额维度无须合成。
4. **WHEN** 核 K12 的 review-session 键 **THEN** SHALL 按 KC-5 判为**另一命名空间**，不纳入 managed table。

---

## Requirement 7：本 lane 的模板层与其余收口

**User Story:** 作为实施者，我需要本 lane 的模板层特征与 BP-7 缺口被收口。

### 验收准则

1. **WHEN** 核 definedName **THEN** SHALL 现算本 lane **5 册全为 0**（K 循环 82 个全在 foundation 的 K10 1 个 + lane 1 的 81 个）⇒ 断言保持为 0。
2. **WHEN** 核裸 IF **THEN** SHALL 现算 **424**（K9 175 · K8 136 · K11 39 · K12 37 · K13 37）⇒ 🔴 **占 13 entry 册 715 的 59%，是三份 spec 里最高**；K9 与 K8 是全 K 前两名。
3. **WHEN** 核明细表 **THEN** SHALL 现算 `明细表K12-2` 与 `明细表K13-2` **各 c=26 / bareIF 各 37**、`明细表K8-2` c=27 / bareIF 39、`明细表K9-2` c=25 / bareIF 30、`明细表K11-2` c=18 / bareIF 19 ⇒ 五张全是 KC-24 登记的「≥20 列宽表」中的成员（除 K11-2）。
4. **WHEN** 核 K11 册 **THEN** SHALL 现算它只 **7 张 sheet**（全 K 最少）且**无 hidden `GT_Custom`**；K12/K13/K8/K9 中 K12/K13 有 `GT_Custom`、K8/K9 无。
5. **WHEN** 核 sheet 名 **THEN** SHALL 现算本 lane 名中半角空格 **1 处**（`实质性程序表 K11A`）+ 括号半/全混不配对 **2 处**（K8-6 / K9-6）⇒ 与 lane 1 的分摊合计等于 KC-10 的全 K 口径（引用 lane 1 的口径裁定结论）。
6. **WHEN** 处置 BP-7 **THEN** SHALL 在 5 宿主各挂 notice（按 KC-14 口径选符号）；现算 5 宿主两符号命中**都是 0**。
7. **WHEN** 核 TB 发布门 **THEN** SHALL 现算本 lane **5 处 / 5 条 entry**：`useK8Adjudication.ts` · `useK9Adjudication.ts` · `useK11Adjudication.ts` · `K12TabAdjudication.vue` · `K13TabAdjudication.vue` ⇒ 与 foundation 1（`useK10FormData.ts`）+ lane 1 8 合计 **14** ✓（引用 KC-4）。
8. **WHEN** 核披露层 **THEN** SHALL 现算本 lane **10 处**（5 entry × 2 变体，全在 `K{n}TabDisclosure{Listed,Soe}.vue`）⇒ 与全 K 的 26 处对账：本 lane 10 + lane 1 14（K1 的 2 处在 composable 层 + K2~K7 的 12 处）+ foundation 2（K10）= **26** ✓。

---

## Requirement 8：本 lane 的空分母与不交付边界

**User Story:** 作为后来者，我需要知道本 lane 哪些能立刻做完、哪些卡外部供给。

### 验收准则

1. 🔴 **WHEN** 核 BP-1 / BP-2 / BP-3 **THEN** SHALL 显式登记「它们对本 lane 的 **legacy 端点收口、localStorage 收敛、位置化修复、K11 键冻结清单、模板层登记** 五件事**都不是阻塞**」；只有「发 contract / 注册 adapter / 产 evidence」卡它们。
2. 🔴 **WHEN** 核 BP-4 / BP-5 **THEN** SHALL 显式登记**都不落本 lane**（BP-4 只 K1、BP-5 是 K1~K7，两者全在 lane 1）。
3. 🔴 **WHEN** 评估 canary 资格 **THEN** SHALL 登记本 lane **不产 canary**（首例在 foundation 的 `K10-3-entries`，且 K10 与本 lane 同属 BP-6 组 ⇒ **canary 的 BP-6 形态判据可直接外推到本 lane 5 条**，这是本 lane 相对 lane 1 的优势）。
4. **WHEN** 核 OCR **THEN** SHALL 现算本 lane 的两种 URL 形态分布并统一（引用 KC-19）：`/api/d4/contract-ocr` 无 wpId 段的形态命中含 `K12TabDetail.vue` / `K12TabNonOperatingCheck.vue` / `K13TabNonOperatingCheck.vue` / `K8TabContractCheck.vue`；`/api/workpapers/${…}/d4/contract-ocr` 命中含 `K9TabAdminCheck.vue` / `K9TabContractCheck.vue` ⇒ 🔴 **同一能力两个契约面**须在本 lane 统一。
5. **WHEN** 核 `useAdjustmentCentralSync` **THEN** SHALL 现算本 lane 5 条各 **3 处**（`K{n}TabAdjustment.vue`）⇒ 与全 K 的 13/13 各 3 处吻合；roundtrip 须把它算进**第二写入方**。
6. **WHEN** 核 derived_total **THEN** SHALL 现算本 lane 占 KC-16 的 83 个中的一部分，且 🔴 **6 个「仅中置命中」的键里有 3 个在本 lane**（`K11-2-total-occurrence` · `K8-2-total-audited` · `K9-2-total-audited`），另 3 个在 lane 1（`K1-8-calc-total-provision` · `K4-1-subtotal-credit` · `K4-1-subtotal-debit`）⇒ 3 + 3 == 6 ✓。
