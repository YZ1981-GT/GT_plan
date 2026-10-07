# K8/K9/K11/K12/K13 专用 composable 与跨循环枢纽 — 设计

## 上游与边界

| 项 | 内容 |
|---|---|
| 共同裁决 | `k-cycle-sync-foundation-and-first-canary/design.md` 的 **KC-1 ~ KC-24** —— 🔴 **本 spec 只引用编号，不复述正文** |
| 本 spec entry | `xlsx/gt-k8-selling-expenses` · `xlsx/gt-k9-admin-expenses` · `xlsx/gt-k11-asset-impairment-loss` · `xlsx/gt-k12-non-operating-income` · `xlsx/gt-k13-non-operating-expense`（**5 条 = BP-6 除 K10**） |
| Property 前缀 | `KB-P` |
| 变异 / 实景脚本 | 复用 `backend/scripts/diagnose/` 的 `mutate_k_cycle_guards.py` · `mutate_task53_k_cycle_migration_guards.py` · `verify_k_cycle_live.py`（**不新写**） |

🔴 **本 lane 与 lane 1 的分界 = BP-6 / BP-5**。BP-6 全集 6 条（K8~K13），**K10 已在 foundation 作 canary 完整交付** ⇒ 本 lane 是剩余 **5** 条。
🔴 **本 lane 相对 lane 1 的优势**：foundation 的 canary（`K10-3-entries`）与本 lane **同属 BP-6 组** ⇒ **canary 的 BP-6 形态判据可直接外推到本 lane 5 条**；lane 1 的 BP-5 形态则完全没有 canary 覆盖。

---

## 聚类理由：为什么这 5 条在一起

1. 🔴 **BP-6 的 entry 全集是 K8~K13，去掉已在 foundation 的 K10 恰好是这 5 条** ⇒ 「5 个 live composable 的 legacy 端点收口 + localStorage 收敛」写一次即收口。
2. 🔴 **BP-8 的 45 处按 BP-5/BP-6 分界恰好二分成 24 / 21**，本 lane 占 **21**（K8 8 · K9 7 · K11 4 · K12 2），不跨 lane。
3. 🔴 **KC-15 的 `disabled` 门控形态只落 K8/K9**（全在本 lane）⇒ 二分支判据只在本 lane 需要。
4. 🔴 **KC-8 的跨循环枢纽 K11 在本 lane** ⇒ H1 pilot golden 回归钩子单点收口。
5. **内含对照组**：K13 的位置化命中为 **0**（K 域零缺陷 4 条里的 1 条）；且 **K11 / K13 真库无载荷**、**K8 / K9 真库有大载荷** ⇒ 一份 spec 内同时有「真库实证」与「合成载荷」两种 roundtrip 形态，能对照出哪条结论依赖真库。

---

## KB-1 ~ KB-6 本 lane 专属裁决

### KB-1 BP-6：5 个 live composable 的端点与持久化清册

| composable | 生产边 | 测试边 | `onlyoffice/health` | `onlyoffice-config` | localStorage 前缀 | 行数（`split("\n")`） |
|---|---|---|---|---|---|---|
| `useK8DualMode.ts` | **1**（`GtK8SellingExpenses.vue`） | 0 | 1 | **2** | `k8-dual-mode:`（2 处） | 189 |
| `useK9DualMode.ts` | **1**（`GtK9AdminExpenses.vue`） | 0 | 1 | **2** | `k9-dual-mode:`（2 处） | 182 |
| `useK11DualMode.ts` | **1**（`GtK11AssetImpairmentLoss.vue`） | 0 | 1 | **2** | `k11-dual-mode:`（2 处） | 154 |
| `useK12DualMode.ts` | **1**（`GtK12NonOperatingIncome.vue`） | 0 | 1 | 1 | `k12-dual-mode:`（3 处） | 158 |
| `useK13DualMode.ts` | **1**（`GtK13NonOperatingExpense.vue`） | 0 | 1 | 1 | `k13-dual-mode:`（3 处） | 158 |
| **本 lane 合计** | **5** | **0** | **5** | **8** | 5 前缀 / 12 处 | **841** |

🔴 **与 foundation 的 K10 对账**：K10 的 `useK10DualMode.ts`（155 行 / health 1 / config 1 / 前缀 3 处）⇒ BP-6 全集 6 个 composable 的 config 合计 **9 处 / 6 文件**。slice 的 `dual_mode_modules_calling_legacy_config_endpoint = 6` 是**文件数不是处数**（引用 KC-3）。
🔴 **与 lane 1 的反向对照**：lane 1 的 7 个 `useK{n}DualMode.ts` **生产边与测试边各为 0、config 全为 0** ⇒ 两侧都验，证明本 lane 的「各 1 条边 + config 非 0」不是漏扫。
🔴 **端点形态**：这 8 处 config 直调**全是反引号模板字面量** `` `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config` `` ⇒ 只认单/双引号的正则会漏成 0（KC-3 的实证来源之一）。
🔴 **行数口径**：上表用 `len(text.split("\n"))`；`splitlines()` 口径逐个 188/181/153/157/157 = 836（**恒少 1**，5 个各少 1）。

**处置**：两类端点直调全部改走 sync bridge materialize；断言处置后本 lane `onlyoffice/health` 与 `onlyoffice-config` 命中**都降为 0**。
**localStorage**：5 个前缀收敛到 `workpaper-sync-mode:`；🔴 **列偏好类不动** —— `useK10DetailColumnPrefs.ts` / `useK11DetailColumnPrefs.ts` / `useK10GrantColumnPrefs.ts`（引用 KC-18）。

### KB-2 KC-15 落地：K8/K9 的 `disabled` 门控形态

| entry | 宿主 `v-if` 门控 | composable `disabled: !isOoAvailable` | 宿主 `isOoAvailable` 命中 |
|---|---|---|---|
| 🔴 **K8** | **0** | ✅ 在 `useK8DualMode.ts` 的 `modeOptions` computed | 🔴 **0** |
| 🔴 **K9** | **0** | ✅ 在 `useK9DualMode.ts` 的 `modeOptions` computed | 1 |
| K11 | 1 | — | 3 |
| K12 | 1 | — | 2 |
| K13 | 1 | — | 3 |

🔴 **两处会让判据假红的陷阱**：
1. 统一写「宿主必须有 `v-if` 二级门控」⇒ **K8/K9 假红**。判据须二分支：「有 `v-if`」**或**「composable 里有 `disabled: !isOoAvailable`」。
2. 按宿主层扫 `isOoAvailable` ⇒ **K8 命中 0**（全在 composable）。判据范围必须含 composable。

`el-segmented` 现算：剥注释前 5 宿主多数为 2 处（第二处在**块注释里**），**剥后各恒 1 处**，且落在该宿主 `toolbar_gate_anchor` 之后 6 行内（引用 KC-15）。

### KB-3 KC-8 落地：K11 跨循环枢纽的 9 键冻结

| K11 键 | 消费方 | 消费方性质 |
|---|---|---|
| `K11-2-detail-rows` | `useH1Impairment.ts` · `useH8Impairment.ts` · `useI1Impairment.ts` · `h3ImpairmentCrossSheet.ts` | 🔴 **4 方，含 H1 pilot** |
| `K11-2-fixed-asset-occurrence` | `useH1Impairment.ts` | H1 pilot |
| `K11-2-rou-occurrence` | `useH8Impairment.ts` | H 循环 |
| `K11-2-intangible-occurrence` | `useI1Impairment.ts` | I 循环 |
| `K11-2-intangible-source-amount` | `useI1Impairment.ts` | I 循环 |
| `K11-source-H1-amount` | `useH1Impairment.ts` | H1 pilot |
| `K11-source-H3-amount` | `h3ImpairmentCrossSheet.ts` | H 循环 |
| `K11-source-H8-amount` | `useH8Impairment.ts` | H 循环 |
| `K11-source-I1-amount` | `useI1Impairment.ts` | I 循环 |

**冻结判据**：这 **9 个键**一律不得改名；改动 SHALL 触发 **H1 pilot golden 回归**（H1 的 `adapter_id` 现算非空，契约 `h1.disposal_check.json` 已 reviewed）。

🔴 **与 J 循环的完全反向**：JC-17 在 J 是「**完全自闭**」（J 键无一被非 J 消费、J 文件无非 J 键）⇒ J 轮结论是「改键无跨循环风险」。**K 是强命中** ⇒ 照抄 J 的自闭结论会**漏掉整条跨循环风险**。
全局现算：非 K 域文件消费的 K 键 **70 个**；反向 K 域引用的非 K 键仅 **4 种**（`b19-alert` 2 处 · `b19-tag` 1 · `H1-14-supplement-total` 1 · `H1-14-calc-rows` 1）。

🔴 **K11 的矛盾状态**：键有 **4 方跨循环消费者**，但 **`K11-%` 真库行数为 0**（完全无载荷）⇒
- K11 自己的 roundtrip 必须用**合成载荷**（标 `synthetic_payload_no_live_db_baseline`）
- H1 golden 回归必须用 **H1 侧自己的载荷**（不能指望 K11 侧有数据）
- 🔴 这是「有消费方但无数据」的形态，与 H 循环 BP-12 的「猜键回退链」（猜出的键生产命中 0 + 真库零载荷 ⇒ 静默取空）**同型风险**：消费方读 K11 键恒取空而不报错

### KB-4 BP-8 落地：本 lane 21 处位置化 + 「一表两路两套身份」

| entry | defect | 说明 |
|---|---|---|
| **K8** | **8** | 含 `useK8Checks.ts` 多处 + 🔴 `useK8Cutoff.ts` 的反序列化路径 |
| **K9** | **7** | 含 `useK9Checks.ts` 多处 + 🔴 `useK9Cutoff.ts` 的反序列化路径 |
| **K11** | **4** | 含 `K11TabDisclosureListed.vue` / `K11TabDisclosureSoe.vue` 各两处 |
| K12 | **2** | 含 `useK12Check.ts` 的 family_a 与 family_b 各一 |
| 🔴 **K13** | **0** | **对照组** |
| 合计 | **21** | 与 lane 1 的 24 合计 **45** ✓ |

🔴 **KB-4 的核心发现：同一张表两条路走两套身份**

| 路径 | 形态 | 族 | 是否缺陷 |
|---|---|---|---|
| 新增行 | `useK8Cutoff.ts` / `useK9Cutoff.ts` 的 `` rowKey: `row-${idx}-${Date.now()}` `` | **family_c** | ❌ 非缺陷（含时间戳熵，新增行不会撞既有行） |
| 反序列化 | 同文件的 `` raw.rowKey ?? `row-${idx}` `` | 🔴 **family_b** | ✅ **缺陷**（历史载荷缺 `rowKey` 时**静默退化**成位置化身份） |

⇒ **「主身份机制干净」不等于「该表干净」**。slice 的 `dynamic_row_identity.tables[]` 把 K8-6/K8-7 与 K9-6/K9-7 的 `row_identity.kind` 登记为 `generated_opaque_string`（非禁止值），同时把反序列化路径的退化单独记进 `positional_identity_inventory` 挂 BP-8 —— 两个容器的**并集覆盖全部命中、交集为空**。判据必须两条路都扫。

**family_c 全 K 只 3 处，其中 2 处在本 lane**：`useK8Cutoff.ts` · `useK9Cutoff.ts`；第 3 处 `K6TabImpairmentTest.vue` 的 `` rowId: `row-${Date.now()}-${i}` ``（时间戳在前、序号只作同批次去重）在 lane 1。

🔴 **family_c 真落库确证**（`K8-6-rows` 真库现读，195,960 B）：
```json
{"rowKey":"row-0-1784807974207","index":1,"voucherNo":"0285","bookDate":"2025-12-26",
 "summary":"物流中心胡本刚报销路桥费,CY133-FYBXD-202512-000217","amount":79.97,
 "sourceDate":"","accountCode":"6601.15.01","accountName":"销售费用_车辆运行费_路桥费",
 "sourceVoucherNo":"","sourceAmount":0,"businessContent":"…"}
```
⇒ `row-{idx}-{13位时间戳}` 形态真落库（`idx=0`），且另有 **`index` 字段**（展示序号）⇒ **family_d 不计入 `total_hits` 的实证来源**（引用 KC-6）。

`positional_row_id_template`（KC-24 的第六个 hardcoded 模式，全 K **13 处非 0**）本 lane 占多数：`useK8Cutoff.ts` 2 处 · `useK9Cutoff.ts` 2 处 · `K11TabDisclosureListed.vue` 2 处 · `K11TabDisclosureSoe.vue` 2 处等；这 13 处 SHALL 是位置化 48 处的**子集**。

**处置**：已落库 id **grandfather 不重写**；反序列化路径的 `` ?? `row-${idx}` `` 兜底改为「缺身份时生成新的值化身份」而不是退化成下标。

### KB-5 K8/K9 截止性测试双 sheet 是方向变体不是同尾码变体

| 册 | sheet | 尾码 | 几何 | 括号 |
|---|---|---|---|---|
| K8 | 🔴 `截止性测试(从记账凭证至原始凭证）K8-6` | `K8-6` | r=44 c=11 | **半角左 + 全角右** |
| K8 | `截止性测试（从原始凭证至记账凭证）K8-7` | `K8-7` | r=44 c=12 | 全角配对 |
| K9 | 🔴 `截止性测试(从记账凭证至原始凭证）K9-6` | `K9-6` | r=44 c=11 | **半角左 + 全角右** |
| K9 | `截止性测试（从原始凭证至记账凭证）K9-7` | `K9-7` | r=44 c=12 | 全角配对 |

🔴 **HC-5 / JC-11 的「同尾码双 sheet」在 K 全域现算为 0** ⇒ 这四张是**不同尾码的方向变体**（记账凭证→原始凭证 vs 原始凭证→记账凭证），**不是同尾码变体**；照抄那两条判据会误判。
🔴 **K6-5/K6-6**（`减值准备测试表（后续计量） K6-5` / `处置组减值测试表（后续计量） K6-6`，在 lane 1）是**对象变体**（单项资产 vs 处置组），同样不是同尾码。
⇒ **K 的变体轴是「尾码不同 + 语义成对」**，判据须按「sheet 名前缀相同 + 尾码相邻」识别，不能按「尾码相同」。

**括号缺陷分摊**：本 lane 占 KC-10 的「括号半/全混不配对 **5** 处」中的 **2** 处（`K8-6` / `K9-6`），另 3 处（K1 / K5 / K6）在 lane 1 ⇒ **2 + 3 == 5** ✓。
**采样端点**：`POST /api/projects/{X}/sampling/cutoff-test` 现算命中 **2 文件**（K8/K9 各 1）⇒ 截止性测试有专用后端能力，契约须声明它**不是 checklist 写路径**。

### KB-6 真库空载荷与大载荷并存的 roundtrip 二分策略

| entry | 非空键 | 载荷 | roundtrip 策略 |
|---|---|---|---|
| **K8** | **1** | 🔴 `K8-6-rows` **195,960 B**（真凭证号 / 真日期 / 真金额 / 真科目码） | ✅ **真库实证**，金额维度无须合成 |
| **K9** | **3** | `K9-1-rows` **11,549 B** · `K9-1-audited-by-item` 3,905 B · `K9-1-audited-total` 1 B | ✅ 真库实证 |
| K12 | 2 | `K12-review-session-{时间戳}` 262 B（**另一命名空间**）· `K12-4-check-rows` 2 B（空数组） | ⚠️ 结构可验、业务维度须合成 |
| 🔴 **K11** | **0** | **真库完全无行** | 🔴 合成载荷 + 标 `synthetic_payload_no_live_db_baseline` |
| 🔴 **K13** | **0** | **真库完全无行** | 🔴 合成载荷 + 标 `synthetic_payload_no_live_db_baseline` |
| **合计** | **6** | **211,679 B** | — |

🔴 **算术口径须现算裁定**：非空键 1+3+2+0+0 = **6** ✓；载荷 195,960 + 15,455 + 264 = **211,679 B**。
🔴 **`K9-1-rows` 载荷形态**：`{"rowKey":"row-jil2dvsb","projectName":"管理费用_职工薪酬_工资","unadjustedDebit":0,"unadjustedCredit":0,"unadjusted":0,"aje":0,"rje":0,"audited":0,"priorAmount":0,"yoyChange":0,"yoyChangeRate":null,"remark":"","isEditable":true}` ⇒ `row-{8位base36}` **纯随机族**（安全），但**金额字段全 0** ⇒ 与 foundation canary 同型的「骨架已落库业务未填」，金额维度仍须合成或改用 K8 的载荷。
🔴 **K12 的 `K12-4-check-rows` 只 2 B**（空数组 `[]`）⇒ 不是有效载荷。

**K11 的双重特殊性**（KB-3 已述）：键有 4 方跨循环消费者但真库 0 行 ⇒ 消费方读它恒取空而不报错，与 H 循环 BP-12「猜键回退链静默取空」同型风险。

---

## 本 lane 的模板层基线

| 项 | 现算 | 备注 |
|---|---|---|
| sheets | **49** = K8 12 + K9 12 + K11 **7** + K12 9 + K13 9 | 🔴 K11 只 7 张是**全 K 最少** |
| 裸 IF | **424** = K9 **175** + K8 **136** + K11 39 + K12 37 + K13 37 | 🔴 **占 13 entry 册 715 的 59%，三份 spec 里最高**；K9 与 K8 是全 K 前两名 |
| definedName | **5 册全 0** | K 循环 82 个全在 foundation K10（1）+ lane 1（81）⇒ 断言保持为 0 |
| `#REF!` 死公式 | **0 格** | 70 格全在 lane 1 的 K1 |
| hidden `GT_Custom` | K12 / K13 **有**；K8 / K9 / K11 **无** | 全 K 8 册有 |
| 名中半角空格 | **1 处**（`实质性程序表 K11A`） | 与 lane 1 分摊合计 = KC-10 全 K 口径 |
| 括号半/全混不配对 | **2 处**（`K8-6` / `K9-6`） | 2 + 3（lane 1）== 5 ✓ |
| 跳跃式 footer | **0 处** | KC-12 的 5 处全在 lane 1 |
| 披露双变体 | **10 处**（5 entry × 2，全在 `K{n}TabDisclosure{Listed,Soe}.vue`） | 10 + 14（lane 1）+ 2（foundation）== **26** ✓ |
| 宽表（≥20 列） | `明细表K8-2` c=27 · `合同检查表K8-5` c=22 · `附注披露信息（上市公司）`(K8) c=28 · `明细表K9-2` c=25 · `合同检查表K9-5` c=22 · `明细表K12-2` c=26 · `明细表K13-2` c=26 · `附注披露信息（上市公司）`(K11) c=27 · `附注披露信息（国企）`(K11) c=27 | 9 张；`明细表K11-2` c=18 未达阈值 |
| 明细表 bareIF | K8-2 **39** · K12-2 **37** · K13-2 **37** · K9-2 **30** · K11-2 **19** | 五张全非 0（lane 1 有 6 张为 0） |
| 审定表 | K8-1 f=135/bareIF=11 · K9-1 f=**223**/bareIF=19 · K11-1 f=**190**/bareIF=20 · K12-1 f=80/bareIF=0 · K13-1 f=79/bareIF=0 | K9-1 与 K11-1 是全 K 第二、第三复杂（第一是 lane 1 的 K1-1 f=547） |
| 调整分录汇总 | 5 张全部 `c=10 f=7 bareIF=0 merged=3` | ✅ 与 canary 所在的 `调整分录汇总K10-3` **完全同构**（KC-5 / canary 外推的直接依据） |

---

## 本 lane 的写路径与其余收口

| 项 | 现算 |
|---|---|
| TB 发布门 | **5 处 / 5 条 entry**：`useK8Adjudication.ts` · `useK9Adjudication.ts` · `useK11Adjudication.ts` · `K12TabAdjudication.vue` · `K13TabAdjudication.vue` ⇒ 与 foundation 1 + lane 1 8 合计 **14** ✓（KC-4） |
| `checklist-responses` 载体 | 5 个 `useK{n}FormData.ts` **各 2 处** + `useK11Detail.ts` **1 处** ⇒ 全属 `formdata_composable_bare_endpoint` 族（KC-2） |
| `useAdjustmentCentralSync` | 5 条各 **3 处**（`K{n}TabAdjustment.vue`）⇒ roundtrip 的**第二写入方** |
| 披露层写路径 | `disclosure-notes/sync-from-workpaper` **10 处**（5 entry × 2 变体）⇒ **写另一张表**不是 `checklist_responses` |
| OCR 两形态 | 🔴 `/api/d4/contract-ocr`（无 wpId 段）含 `K12TabDetail.vue` · `K12TabNonOperatingCheck.vue` · `K13TabNonOperatingCheck.vue` · `K8TabContractCheck.vue`；`/api/workpapers/${…}/d4/contract-ocr` 含 `K9TabAdminCheck.vue` · `K9TabContractCheck.vue` ⇒ **同一能力两个契约面**须统一（KC-19） |
| derived_total | 🔴 KC-16 的 **6 个「仅中置命中」键里有 3 个在本 lane**（`K11-2-total-occurrence` · `K8-2-total-audited` · `K9-2-total-audited`），另 3 个在 lane 1 ⇒ **3 + 3 == 6** ✓ |
| notice | 5 宿主两符号命中**都是 0**（BP-7 从零补） |
| 宿主 `isOoAvailable` | K8 **0** · K9 1 · K11 3 · K12 2 · K13 3 ⇒ 🔴 K8 宿主完全不引用该符号 |
| 宿主 `localStorage` | 5 宿主**全为 0**（与 lane 1 的 K4/K5/K6 各 2 处不同）⇒ 本 lane 的模式偏好只在 composable 侧 |

---

## Property 清单（KB-P1 ~ KB-P40）

| ID | 断言 | 来源 |
|---|---|---|
| KB-P1 | 本 spec 的 5 条 entry_id 用全名列出；与 foundation 的 K10、lane 1 的 7 条**三者无交集且并集 == 13** | 切分 |
| KB-P2 | 5 条的 `capability_target_blocked_by` **全部含 BP-6**；且 K 循环含 BP-6 的 entry 恰好是 K8~K13 共 6 条，去 K10 后是这 5 条（两侧都验） | KB-1 |
| KB-P3 | 5 个 `useK{n}DualMode.ts` **各恰 1 条生产边**、测试边 0，边指向的宿主与 slice 的 `dual_mode_carrier.site` 一致 | KB-1 |
| KB-P4 | 🔴 反向对照：lane 1 的 7 个 `useK{n}DualMode.ts` 生产边与测试边**各为 0**、config **全为 0**（两侧都验，证明本 lane 非漏扫） | KB-1 |
| KB-P5 | legacy 端点现算：`health` **各 1（合 5）** · `config` **K8/K9/K11 各 2 + K12/K13 各 1（合 8）** | KB-1 |
| KB-P6 | 🔴 与 K10 对账：BP-6 全集 6 个 composable 的 config 合计 **9 处 / 6 文件**；slice 的 6 是**文件数不是处数** | KB-1 / KC-3 |
| KB-P7 | 🔴 8 处 config 直调**全是反引号模板字面量**；只认单/双引号的正则会漏成 0（变异证明） | KB-1 / KC-3 |
| KB-P8 | 5 个 composable 行数按 `split("\n")` 现算 189/182/154/158/158 = **841**；`splitlines()` 得 836（各少 1） | KB-1 / KC-22② |
| KB-P9 | 处置后本 lane `onlyoffice/health` 与 `onlyoffice-config` 命中**都降为 0**，bridge materialize 路径命中非 0 | KB-1 |
| KB-P10 | localStorage 5 前缀（12 处）收敛到 `workpaper-sync-mode:`；🔴 列偏好类 `useK10DetailColumnPrefs.ts` / `useK11DetailColumnPrefs.ts` / `useK10GrantColumnPrefs.ts` **不动** | KB-1 / KC-18 |
| KB-P11 | 🔴 5 宿主 `localStorage` 命中**全为 0**（与 lane 1 的 K4/K5/K6 各 2 处不同） | KB-1 |
| KB-P12 | 宿主 `v-if` 门控现算 K11/K12/K13 各 1、🔴 **K8/K9 为 0** | KB-2 / KC-15 |
| KB-P13 | 🔴 K8/K9 的 `disabled: !isOoAvailable` 在 **composable 的 `modeOptions` computed** 里（宿主层 0）；判据二分支写 | KB-2 |
| KB-P14 | 🔴 宿主 `isOoAvailable` 现算 K8 **0** / K9 1 / K11 3 / K12 2 / K13 3 ⇒ 判据范围须含 composable | KB-2 |
| KB-P15 | `el-segmented` 剥注释后 5 宿主**各恒 1 处**，落在 `toolbar_gate_anchor` 之后 6 行内 | KB-2 / KC-15 |
| KB-P16 | 🔴 K11 的 **9 个键**及其消费方逐条等值（`K11-2-detail-rows` 4 方含 H1 pilot · `K11-2-fixed-asset-occurrence`←H1 · `K11-2-rou-occurrence`←H8 · `K11-2-intangible-occurrence`+`-source-amount`←I1 · `K11-source-{H1,H3,H8,I1}-amount` 各 1） | KB-3 / KC-8 |
| KB-P17 | 🔴 这 9 键**冻结不得改名**；改动触发 **H1 pilot golden 回归**（H1 `adapter_id` 现算非空、契约已 reviewed） | KB-3 |
| KB-P18 | 全局现算：非 K 域消费 K 键 **70 个**；反向 K 域引非 K 键仅 **4 种** | KB-3 |
| KB-P19 | 🔴 显式登记「JC-17 在 J 是完全自闭，K 是强命中」⇒ 照抄 J 会漏掉整条跨循环风险 | KB-3 |
| KB-P20 | 🔴 `K11-%` 真库行数 == **0** ⇒ 键有 4 方消费者但无载荷；roundtrip 用合成载荷标 `synthetic_payload_no_live_db_baseline`；H1 golden 回归用 H1 侧自己的载荷 | KB-3 / KB-6 |
| KB-P21 | 🔴 登记「有消费方但无数据」与 H 循环 BP-12「猜键回退链静默取空」**同型风险**（消费方读 K11 键恒取空而不报错） | KB-3 |
| KB-P22 | 本 lane BP-8 现算 **21 处**（K8 8 · K9 7 · K11 4 · K12 2；🔴 **K13 为 0 是对照组**），与 lane 1 的 24 合计 **45** ✓ | KB-4 |
| KB-P23 | 🔴 **一表两路两套身份**：`useK8Cutoff.ts` / `useK9Cutoff.ts` 的新增行路径 `` `row-${idx}-${Date.now()}` `` 归 family_c（非缺陷），反序列化路径 `` raw.rowKey ?? `row-${idx}` `` 归 **family_b（缺陷）**；判据两条路都扫 | KB-4 |
| KB-P24 | 🔴 「主身份机制干净」≠「该表干净」：slice 的 `dynamic_row_identity.tables[]` 与 `positional_identity_inventory` 两容器**并集覆盖全部命中、交集为空**（两侧都验） | KB-4 |
| KB-P25 | family_c 全 K 只 **3 处**，其中 **2 处在本 lane**（K8/K9 的 Cutoff），第 3 处在 lane 1（`K6TabImpairmentTest.vue`） | KB-4 |
| KB-P26 | 🔴 family_c 真落库确证：`K8-6-rows` 的 `"rowKey":"row-0-1784807974207"` ∧ 另有 `"index":1` 展示序号字段 ⇒ **family_d 不计入 total_hits 的实证来源** | KB-4 / KC-6 |
| KB-P27 | `positional_row_id_template`（全 K 13 处非 0）本 lane 占多数，且这 13 处是位置化 48 处的**子集** | KB-4 / KC-24 |
| KB-P28 | 已落库 id **grandfather 不重写**；反序列化兜底改为「缺身份时生成新值化身份」而非退化成下标 | KB-4 |
| KB-P29 | 🔴 K8/K9 截止性测试四张 sheet 是**不同尾码的方向变体**；**HC-5 / JC-11 的同尾码双 sheet 在 K 全域为 0** ⇒ 照抄会误判 | KB-5 |
| KB-P30 | 🔴 K 的变体轴判据 = 「sheet 名前缀相同 + 尾码相邻 + 语义成对」，**不是「尾码相同」**；K6-5/K6-6（lane 1）是同型的对象变体 | KB-5 |
| KB-P31 | 括号缺陷分摊：本 lane **2**（`K8-6` / `K9-6`）+ lane 1 **3** == KC-10 的 **5** ✓ | KB-5 / KC-10 |
| KB-P32 | `sampling/cutoff-test` 现算 **2 文件**；契约声明它**不是 checklist 写路径** | KB-5 |
| KB-P33 | 真库非空键现算 **6**（K8 1 · K9 3 · K12 2 · **K11 0 · K13 0**）/ 载荷 **211,679 B**；算术两项都现算裁定 | KB-6 |
| KB-P34 | 🔴 K8 用真库 `K8-6-rows` **195,960 B** 真业务载荷跑 roundtrip（**K 域第二大**），金额维度无须合成 | KB-6 |
| KB-P35 | 🔴 `K9-1-rows` 是 `row-{8位base36}` 纯随机族（安全）但**金额字段全 0** ⇒ 与 foundation canary 同型「骨架已落库业务未填」，金额维度须合成或改用 K8 载荷 | KB-6 |
| KB-P36 | K12 的 `K12-review-session-{时间戳}` 按 KC-5 判为**另一命名空间**不纳入 managed table；`K12-4-check-rows` 只 2 B 是空数组**不是有效载荷** | KB-6 / KC-5 |
| KB-P37 | 模板层基线：sheets **49**（K11 只 7 张全 K 最少）· 裸 IF **424**（占 715 的 59%，三份最高）· definedName 与 `#REF!` **全 0** · 跳跃式 footer **0 处** · 5 张调整分录汇总与 canary **完全同构** | 模板层 |
| KB-P38 | 披露双变体 **10 处**；10 + 14（lane 1）+ 2（foundation）== **26** ✓ | 写路径 |
| KB-P39 | TB 发布门 **5 处 / 5 条**；5 + 8（lane 1）+ 1（foundation）== **14** ✓ | KC-4 |
| KB-P40 | 🔴 derived_total 的 6 个「仅中置命中」键：本 lane **3**（`K11-2-total-occurrence` · `K8-2-total-audited` · `K9-2-total-audited`）+ lane 1 **3** == **6** ✓ | KC-16 |

### 边界 Property（KB-P41 ~ KB-P44）

| ID | 断言 |
|---|---|
| KB-P41 | 🔴 **BP-1 / BP-2 / BP-3 对本 lane 的五件事都不是阻塞**（legacy 端点收口 / localStorage 收敛 / 位置化修复 / K11 键冻结清单 / 模板层登记）⇒ 这五件**可立刻实施完**；只有发 contract、注册 adapter、产 evidence 卡它们 |
| KB-P42 | 🔴 **BP-4 与 BP-5 都不落本 lane**（BP-4 只 K1、BP-5 是 K1~K7，全在 lane 1） |
| KB-P43 | 🔴 本 lane **不产 canary**；但 foundation 的 canary 与本 lane **同属 BP-6 组** ⇒ **canary 的 BP-6 形态判据可直接外推到本 lane 5 条**（这是本 lane 相对 lane 1 的优势，lane 1 的 BP-5 形态完全无 canary 覆盖） |
| KB-P44 | 本 lane 只**引用** KC-1 ~ KC-24 的编号，**不复述正文**（脚本核验零复述）；`KB-P1`~`KB-P44` 无重号无缺号；无 U+FFFD |
