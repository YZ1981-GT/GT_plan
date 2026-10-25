# K 循环双向回写地基与首张 canary — 需求

## 引言

本 spec 是 **K 循环（管理循环）13 条 Excel 独立 entry** 的地基：把 **KC-1 ~ KC-24 共同裁决**在此裁一次，并交付**首张 canary**（`K10-3-entries` / `调整分录汇总K10-3`）的端到端双向回写闭环。另两份 lane spec 只引用 KC-x，不复述。

**上游**：umbrella Task 53 的 K slice（`backend/data/workpaper_sync_k_cycle_manifest_slice.json`，221,580 B，冻结 2026-08-31）+ 守卫 `backend/tests/workpaper_sync/test_task53_k_cycle_migration.py` + 已存在的三个 diagnose 脚本（`mutate_k_cycle_guards.py` / `mutate_task53_k_cycle_migration_guards.py` / `verify_k_cycle_live.py`，**复用不新写**）+ 前七轮共同裁决 FC-1~13 / GC-1~10 / HC-1~16 / IC-1~20 / JC-1~20。

**本 spec 的 entry 范围**：`xlsx/gt-k10-other-income`（**1 条**，canary 所在 entry 完整纳入，沿用 H/I/J 三轮既定形态）。
其余 12 条 entry 分属两份 lane spec：
- `k1-k7-inlined-iife-hosts-and-orphan-cleanup` —— K1~K7（7 条，BP-5 全部）
- `k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub` —— K8/K9/K11/K12/K13（5 条，BP-6 除 K10）

🔴 **本 spec 全部计数一律现算，禁写死**。下文出现的每个数字都标注了现算口径；实施时必须用同口径重算并与本文件等值比对，**多一处少一处都红**。

---

## 术语与口径（先立规矩，后面 Req 直接引用）

| 术语 | 口径（现算方法） |
|---|---|
| **K 域生产文件** | `components/workpaper/k{1..13}/**` + `composables/workpaper/k{1..13}/**` 的 `.ts`/`.vue`（排除 `__tests__`）+ `components/workpaper/GtK*.vue`（🔴 **必须排除 `GtKamWorkpaper.vue`**）+ `components/workpaper/composables/` 下匹配 `^(use)?[kK](1[0-3]\|[1-9])(?![0-9])` 的 `.ts` ⇒ 现算 **367** |
| **剥注释** | `stripComments()`：块注释 / 行注释 / HTML 注释一律**同长空白替换**（保留行号），行注释正则须用 `(?<!:)//` 避免吃掉 URL 的 `//` |
| **端点字面量** | 正则 `['"` + 反引号 + `](/api/[^'"` + 反引号 + `]+)['"` + 反引号 + `]`，🔴 **必须认反引号**；统计前把 `${...}` 归一为 `{X}` |
| **精确字面量命中** | 整个引号内容 `==` 目标串（**不是子串包含**）；每行至多计一次 |
| **行数口径** | 🔴 本 spec 一律用 `len(text.split("\n"))`（末尾换行计一行）；`splitlines()` 会**恒少 1** |
| **宽/窄口径（共享基类）** | 窄 = statement-position 路径字面量解析后路径相等；宽 = 文件内 token 命中。🔴 宽口径**不含基类自身**（含则 +1） |

---

## Requirement 1：entry 边界与 manifest 分歧（BP-9）

**User Story:** 作为迁移实施者，我需要 K 循环 13 条 entry 的边界与 manifest 的分歧被显式登记，这样我不会把 overlay 默认值当成能力裁决。

### 验收准则

1. **WHEN** 按 slice 的 `selection_rule`（`document_type=='xlsx'` ∧ `wp_match.wp_code_patterns` 任一以 `K` 开头 ∧ `independent_entry==true`）从 manifest 现算集合 **THEN** 该集合 SHALL 与 slice 的 `independent_entries` 做**等值比对**，现算 **13** 条，多一条或少一条都红。
2. **WHEN** 现算 manifest 里 K 前缀 entry 的 `capability` / `html_store` / `adapter_id` **THEN** SHALL 分别得 13 条 `single_onlyoffice` / 13 条 `unresolved` / 13 条 `null`，且 **0 条**有 `capability_target` 字段；本 slice 现算 `bidirectional` 条数为 **0** ⇒ 守卫 SHALL 断言两者**不相等**并指向 BP-9。
3. **WHEN** 核 `parent_duplicate` **THEN** SHALL 现算「`parent_entry_id ∈ 13 条 K entry_id`」的条数 == **0**，且 overlay 的 `parent_rules[].file_glob` 里含 `/k` 后接数字的条数 == **0**（实有六条是 d4/h4/h8/n1/j1/b60），并断言本 slice 顶层**没有** `parent_duplicate_summary` 键。
4. 🔴 **WHEN** 枚举 K 宿主 **THEN** SHALL 显式排除 `GtKamWorkpaper.vue`（其 `wp_code` 是 KAM，manifest 里无以 `K` 开头的 `wp_code_pattern` 命中它）。不排除则 K 域文件数为 **368**、且会把它的 2 处 `checklist-responses` 与 `/api/a17/kam/push-to-report`、`/api/a17/kam/{X}/ai-generate` 两端点计入 K 的写路径。
5. **WHEN** 核权威模板 **THEN** SHALL 现算 `backend/wp_templates/K/` 非锁文件数 == **14**、锁文件 == **0**；`belongs_to_entry` 非 null 的 == **13**、为 null 且带 `excluded_reason` 的 == **1**（`K0 管理循环函证.xlsx`，走 confirmation-hub 归 Task 57）⇒ **单射不满射**。
6. 🔴 **WHEN** 对 `K0` 跑 `find_template_file` 与 `find_template_file_any` **THEN** 两者 SHALL 都返回 `K0 管理循环函证.xlsx`（**非 None**）—— 与 J 循环的 `J0`（两函数都返 None）**相反**，判据不得照抄 J。

---

## Requirement 2：KC-1 ~ KC-24 共同裁决只裁一次

**User Story:** 作为后续 lane 的实施者，我需要共同裁决有唯一出处，这样三份 spec 的判据不会各自漂移。

### 验收准则

1. **WHEN** 检查 `design.md` **THEN** SHALL 定义 **KC-1 ~ KC-24** 全 24 条，每条含「结论 + 现算口径 + 反例或非空反证」。
2. **WHEN** 检查两份 lane spec **THEN** 它们 SHALL 只**引用** KC-x 编号，不复述条文正文；脚本核验「悬空引用 0 / 定义了但未被任何 spec 引用 0」。
3. **WHEN** 检查 Property 编号 **THEN** 三份 spec SHALL 各用独立前缀：本 spec `KF-P`、lane 1 `KA-P`、lane 2 `KB-P`，各自无重号无缺号。

---

## Requirement 3：写路径与发布门必须按端点字面量判定

**User Story:** 作为守卫作者，我需要写路径判定不依赖符号名，这样不会重演「`publishToTb` 符号名 0 命中但端点命中」的误判。

### 验收准则

1. 🔴 **WHEN** 扫 K 域端点 **THEN** 正则 SHALL **认反引号模板字面量**。只认单/双引号会把 6 个 `` `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config` `` 直调漏登记成 **0**（slice 首轮实测即因此打红）。
2. **WHEN** 现算 K 域端点全集 **THEN** SHALL 得 **30** 种（去插值归一后），其中：

| 端点 | 现算文件数 |
|---|---|
| `POST /api/workpapers/{X}/ai/generate-text` | 47 |
| `GET /api/projects/{X}/trial-balance` | 28 |
| `POST /api/projects/{X}/disclosure-notes/sync-from-workpaper` | **26** |
| `GET /api/workpapers/onlyoffice/health` | **20** |
| `PUT /api/workpapers/{X}/checklist-responses` | 17 |
| `POST /api/workpapers/{X}/audit-determination/publish-to-tb` | **14** |
| `GET /api/workpapers/{X}/sheets/{X}/onlyoffice-config` | 6 |

3. **WHEN** 核 `onlyoffice/health` 的 20 文件 **THEN** SHALL 拆成 **13 个 `useK{n}DualMode.ts` + 7 个宿主内联 IIFE**（K1~K7），13 + 7 = 20 ✓ 与 slice 的 `modules_calling_legacy_health_endpoint=13` 与 `hosts_calling_legacy_health_endpoint_directly=7` 双向吻合。
4. **WHEN** 核 `onlyoffice-config` **THEN** SHALL 现算 **6 文件 / 9 处**（K8:2 K9:2 K10:1 K11:2 K12:1 K13:1）⇒ slice 的 `dual_mode_modules_calling_legacy_config_endpoint=6` 是**文件数不是处数**，判据须写明口径。
5. 🔴 **WHEN** 核 TB 发布门 **THEN** SHALL 得 **13/13 全有**，但载体分布在**四层**共 14 处（K5 占 2 处）：`useK{n}FormData.ts` 5（K1/K3/K4/K5/K10）· `useK{n}Adjudication.ts` 3（K8/K9/K11）· `K{n}TabAdjudication.vue` 5（K2/K5/K7/K12/K13）· **宿主 `GtK6HeldForSale.vue` 1**（唯一在宿主层）⇒ 判据按单一层写必漏。

---

## Requirement 4：载体族 K 内部两种并存

**User Story:** 作为守卫作者，我需要载体族判据分支写，这样不会把 K5 假红。

### 验收准则

1. **WHEN** 现算 `checklist-responses` 端点字面量 **THEN** SHALL 得 **16 文件**（排除 `GtKamWorkpaper.vue` 后）：12 个 `useK{n}FormData.ts` 各 2 处（K1/K2/K3/K4/K6/K7/K8/K9/K10/K11/K12/K13）+ `useK11Detail.ts` 1 + K1 三个 Tab 各 1（`K1TabAdjudication.vue` / `K1TabPolicyCheck.vue` / `K1TabWriteoffCheck.vue`）。
2. 🔴 **WHEN** 核 K5 **THEN** `useK5FormData.ts` 的 `checklist-responses` 命中 SHALL 为 **0**，而 `useChecklistPersistence` 命中 SHALL 为 **3** ⇒ **K5 走共享持久化适配器，端点在适配器内部**。这**不是缺陷**，是载体族差异；判据按裸端点字面量要求「每条 entry 都有 `checklist-responses`」会**假红 K5**。
3. **WHEN** 核宿主层 **THEN** 13 宿主的 `checklist-responses` 命中 SHALL 全为 **0**（都在 composable 层）；`useChecklistPersistence` 各 **3** 处（13×3 = 39）。
4. **WHEN** 核 K5 的 Tab 层 **THEN** 10 个 Tab SHALL 全部只 `emit('save')`（无自有端点），由宿主 `GtK5Provisions.vue` 收口（`useChecklistPersistence` 3 + `emit('save')` 1）。

---

## Requirement 5：canary `K10-3-entries` 端到端闭环

**User Story:** 作为迁移实施者，我需要一张真库有非空载荷、几何最简、身份族已安全的表作首例，这样闭环能真验而不是造数据。

### 验收准则

1. **WHEN** 选 canary **THEN** SHALL 是 `K10-3-entries`（sheet `调整分录汇总K10-3`，entry `xlsx/gt-k10-other-income`），且 SHALL 同时满足四项硬标准（沿用 J 轮改后口径）：真库有非空载荷（**199 B**）+ 在 entry 内 + 非 parent_duplicate（K 循环该计数为 0 故自动满足）+ **单 sheet 单键组**。
2. **WHEN** 核模板几何 **THEN** SHALL 现算 `r=25 c=10 f=7 bareIF=0 merged=3`；🔴 且 SHALL 断言 **13 册「调整分录汇总」完全同构**（`r` 在 21~25、`c=10`、`f=7`、`bareIF=0`、`merged=3`，13/13 无例外）⇒ canary 判据可直接外推到其余 12 条 entry。
3. **WHEN** 核真库载荷 **THEN** SHALL 是单元素数组，`id` 形态 `entry-{13位时间戳}-{6位base36}`（实测 `entry-1784790231509-wlnkon`）⇒ **安全族**，canary **不必先修身份缺陷**（与 I6 需先 backfill、J1-6 需先修 RD-5 都不同）。
4. 🔴 **WHEN** 核载荷业务内容 **THEN** SHALL 如实登记它是**测试骨架**：`description` 为 `"测试确认政府补助"`、`debitAmount`/`creditAmount` 均为 0、`category`/`reportItem`/`noteItem`/`refIndex`/`remark` 五个字段为空串 ⇒ roundtrip **只能验结构**，SHALL 另造带金额合成载荷补一轮并标 `synthetic_payload_for_amount_dimension`。
5. 🔴 **WHEN** 核写入方集合 **THEN** SHALL 把 `useAdjustmentCentralSync` 算进去（`K10TabAdjustment.vue` 3 处）⇒ roundtrip 的第二写入方。
6. 🔴 **WHEN** 发 K10 的 per-entry contract **THEN** SHALL 显式声明 **6 个 `K10-review-session-{14位时间戳}` 键**（各 262 B，同在 entry 内）属**另一命名空间，不纳入 managed table**。
7. **WHEN** 核 K10 全部真库键 **THEN** SHALL 现算 **18 个有行 / 7 个 remark 非空**（6 个 review-session + `K10-3-entries`）；🔴 且 SHALL 如实登记 `K10-2-detail-rows` **有行但 remark 为空** ⇒ 明细表主键不满足硬标准，这是 canary 未选它的原因。
8. 🔴 **WHEN** 评估 canary 覆盖面 **THEN** SHALL 如实登记 K10 属 **BP-6 组（`dedicated_composable`）**，canary **不覆盖 BP-5 的「7 个一阶 orphan + 宿主内联 IIFE」主线形态** ⇒ 该首例外移到 lane 1，本 spec 在交接节指名。

---

## Requirement 6：K10 entry 的 BP 收口

**User Story:** 作为实施者，我需要 K10 这条 entry 上的阻塞项被逐条归位，这样我知道哪些能做完、哪些卡外部供给。

### 验收准则

1. **WHEN** 核 BP 归属 **THEN** K10 的 `capability_target_blocked_by` SHALL 现算为 `[BP-1, BP-2, BP-3, BP-6, BP-7, BP-9]`（**不含 BP-4/BP-5/BP-8**）。
2. **WHEN** 处理 BP-1/BP-2/BP-3 **THEN** SHALL 标 `[ ]*`（平台级供给：approved authority model + reviewed contract + non-null bundle / instrumentation candidate / 真 OO 9.4 探针），**不承诺在本 spec 内完成**。
3. **WHEN** 处理 BP-6 **THEN** SHALL 删除 `useK10DualMode.ts` 里的两个 legacy 端点直调（`onlyoffice/health` 1 处 + `onlyoffice-config` 1 处），改走 sync bridge 的 materialize 协议。
4. **WHEN** 处理 BP-7 **THEN** SHALL 在 `GtK10OtherIncome.vue` 挂 AC 1.4 的单一真源提示组件；🔴 判据 SHALL 写明用**组件名** `GtEntrySyncCapabilityNotice`（全平台生产命中 48）还是**模块名** `workpaperEntrySyncNotice`（全平台生产命中 2）—— K 域两者现算**都是 0**。
5. **WHEN** 处理 BP-9 **THEN** SHALL 在 step 9 后重新生成 manifest，届时 `adapter_id` 非空、`capability` 由 slice 反哺。

---

## Requirement 7：模板层登记（不修，只冻结基线）

**User Story:** 作为实施者，我需要模板层缺陷有基线，这样后续改动会被发现而不是静默漂移。

### 验收准则

1. 🔴 **WHEN** 现算 definedName **THEN** SHALL 得 **82 个 / 含 `#REF!` 65 个**（K4 43/36 · K2 37/29 · K6 1/0 · K10 1/0 · 其余 10 册 0）⇒ **slice 完全没有 definedName 节**，本 spec SHALL 自行登记基线 + 断言不增长，**不删**（删 definedName 有 Excel 公式连带风险）。
2. **WHEN** 现算 sheet 名字符缺陷 **THEN** SHALL 得四类共 **29 处**：名中半角空格 **21** + 括号半/全角混用不配对 **5** + 全半角括号 **2** + 「表表」重复字 **1**；另 K7 用「国有企业」而非「国企」（其余 12 册全「国企」）。SHALL 断言**首尾空格为 0**（与 J1 册相反）。
3. **WHEN** 现算 footer 形态 **THEN** SHALL 得 **164 处 / 3 形态**：连续区间 SUM **140** + 加法式 **19** + 跳跃式 SUM 多段 **5**（无 SUBTOTAL）。
4. **WHEN** 现算裸 IF **THEN** SHALL 得 14 册 **735**、13 entry 册 **715**（K0 占 20）；🔴 **K10 册为 0**（14 册唯一）。
5. **WHEN** 现算 hidden sheet **THEN** `GT_Custom` SHALL 在 **8 册**存在（K0/K1/K2/K3/K7/K10/K12/K13），6 册无（K4/K5/K6/K8/K9/K11）。

---

## Requirement 8：七项结构性零必须现算且带变异证明

**User Story:** 作为质控，我需要「某项为 0」不是漏扫的结果，这样守卫不会空跑通过。

### 验收准则

1. **WHEN** 声明任一项为 0 **THEN** SHALL 同时给出「现算为 0」与「变异注入后打红」两侧证据，变异脚本 SHALL 复用已存在的 `backend/scripts/diagnose/mutate_k_cycle_guards.py` 与 `mutate_task53_k_cycle_migration_guards.py`，**不新写**。
2. **WHEN** 列举结构性零 **THEN** SHALL 覆盖七项：① 本表行越界 **0 格** ② 跨表引用指向不存在 sheet **0 格** ③ **同尾码双 sheet 0**（⇒ HC-5 / JC-11 变体轴在 K **不命中**；K8-6/K8-7、K9-6/K9-7、K6-5/K6-6 都是**不同尾码**的方向或对象变体）④ Excel Table **0** ⑤ sheet 名首尾空格 **0** ⑥ hardcoded 六模式里**五个为 0** ⑦ `duplicate_account_aggregation_found` **0**。
3. 🔴 **WHEN** 核 hardcoded 第六个模式 **THEN** `positional_row_id_template` SHALL 现算 **13 处非 0**（J slice 的同名判据是「六个 0」，照抄即假红），且这 13 处 SHALL 是位置化 48 处命中的**子集**（证明两个扫描口径互相印证）。

---

## Requirement 9：空分母纪律

**User Story:** 作为质控，我需要「没有 contract 所以 Property 通过」这种重言式被显式拒绝。

### 验收准则

1. **WHEN** 报 Property 20 **THEN** contract 维度分母为空（本 slice 已发布 per-entry contract 数 = 0）⇒ 「registry 拒绝 `col_` 占位」这部分 SHALL **不宣称通过**；但前提方向 SHALL 真验（契约归属逐文件读 `review.entry_id` / 四条 pilot 契约 entry_id 逐一等值 / registry 里 K adapter 数 == 0 / 13 宿主模板无「可双向回写」字样）。
2. **WHEN** 报 Property 24 **THEN** SHALL 区分两个分母：空的是「OO↔HTML 回写时保护公式/summary 单元格」（回写路径不存在）⇒ 不宣称通过；实的是 K 域**派生态 checklist 键 83 个**（见 KC-16）。
3. **WHEN** 报 Property 69 **THEN** SHALL 只作**负向**真验（13 条 UNVERIFIABLE 各带非空 `unverifiable_reasons` + 无一条空口声称 VERIFIED）；正向逐 scenario 闭合待 BP-3。
4. **WHEN** 报 Property 70 **THEN** SHALL 真验非空分母：**八个 slice（D/E/F/G/H/I/J/K）两两不相交共 28 个配对** + 契约归属 + 14 册 `belongs_to_entry` 单射 + 13 条 `template_ref.workbook` 两两不同（集合大小 == 13）+ deletion path 与其余七份不相交。
5. 🔴 **WHEN** 核契约与 adapter 的分母 **THEN** SHALL 分开算：契约目录现算 **18 文件 / reviewed 17 / candidate 1**，而 manifest 里 `adapter_id` 非空的现算 **9 条**（d1,d2,d3,d4,d5,d6,d7,g7,h1）⇒ **「契约已发」≠「adapter 已注册」**，两个分母混用必算错；manifest **根本没有 `adapter_registered` 字段**。
