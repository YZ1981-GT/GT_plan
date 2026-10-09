# Implementation Plan

## Overview

**spec**：`i2-i4-i5-carrier-and-structure-exceptions`　**创建**：2026-09-26　
**状态**：0/26（Task 0~20，含 4a / 6a / 11a / 15a / 19a），Design-First 未实施

**上游（只引用不复述）**：`i-cycle-sync-foundation-and-first-canary`（**IC-1 ~ IC-20** + canary I6 范式）·
`i1-i3-disclosure-positional-identity-and-classification-source`（lane 1，跨 lane 键冻结对账方）·
umbrella Task 51 的 I slice · FC-1~FC-13 · GC-1~GC-10 · HC-1~HC-16。

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认 / UI 回归）。

🔴 **本 lane 每条判据都要先回答「这是特例还是通例」** —— 三条 entry 各自把某一维度推到了极端，
放一起才有对照组。
🔴 **不得改 `I2-2-rows` 键名**（lane 1 的 `useI1AdditionCheck.ts#L250-251` 跨 entry 读它）。
🔴 **不得修改 `backend/wp_templates/` 字节**。
🔴 **不得修改 H1 pilot 的契约 / adapter / golden digest**（IC-17）。
🔴 **不重造已有产物**：149 KB 守卫 · `iAdjudicationPublishGate.spec.ts` · `useI2Detail.spec.ts` ·
`useI2CrossSheet.spec.ts` · `iCycleDynamicRows.spec.ts` · 5 个 `four_table/i_cycle_*.py`。

## Tasks

### 阶段 0：前置门 + 红判据（先打红）

- [x] 0. 前置依赖与已有产物清点（`git show HEAD:` 判定，不读工作树）
  - 核 `RowTableSheetSpec` · `StoreMergePlan.oo_crash_neutralization_fn` ·
    `g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas` **函数体**（IC-9 历史坑）
  - 清点 5 个不得重造的既有产物，逐个写明「已存在 ⇒ 只在其上补断言」
  - 证据 `evidence/task0-prerequisites.md`

- [x] 1. 现算复核四组承重结论（先打红）
  - 🔴 ①**三个 FormData 的消费计数**（IC-3 import 路径字面量三形态）：
    `useI2FormData.ts`（500 行）== **4** · `useI4FormData.ts`（394 行）== **0**；
    🔴 禁符号名 grep（I 循环有 4 处注释链式提及会被误判成消费边）
  - 🔴 ②**发布门层级**逐文件现读：`useI4Adjudication.ts#L371`/`#L489` ·
    `useI5Adjudication.ts#L362`/`#L472` · 🔴 `useI2Adjudication.ts` 里 `publishToTb` **0 命中**
    而 `I2TabAdjudication.vue` 有 **4 处**（`#L74`/`#L359`/`#L381`/`#L384`）
  - 🔴 ③**I5 内置行重置**逐行现读 `useI5Detail.ts#L821-839`，确认传入 4 字段不含 `rowId`
    且 `#L305 rowId: generateRowId()`
  - 🔴 ④**三册几何**openpyxl 现读（表头 / 数据区 / footer / 有效列 / `max_column` / 公式数 /
    definedName / 裸 IF）；I5 SHALL 确认三区各 11 行
  - 另现算：mount 三条均 2 · `derived_total_keys` I2 2 / I4 0 / I5 0 ·
    真库 `I2-2-rows`/`I4-2-rows` 无行、`I5-2-rows` 745 B 且 `rowId == e2e-i52-contract`
  - 证据 `evidence/task1-recompute.md`（逐项「design 声明值 vs 现算值」两列表）

- [x] 2. 零回归基线现算（IE-P31，GC-10）
  - 现算契约目录 `*.json` 个数与**文件名集合** · `register_from_manifest()` 已注册集合 ·
    `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS` 成员
  - 🔴 **禁写死个数**（canary 与 lane 1 注册后都会变）
  - 断言开工前无一条契约 `review.entry_id` 以 `xlsx/gt-i2` / `xlsx/gt-i4` / `xlsx/gt-i5` 开头

- [x] 3. 🔴 IC-6 命中 0 的主动断言（IE-P30）
  - 断言三条 entry 的位置化 site == **0**（8 个 site 全在 lane 1 的 {I1, I3}）
  - 🔴 按 IC-20 写成「现算等于 0 且不是漏扫」，**不宣称该维度通过**
  - 变异「用 lane 1 的形态口径扫本 lane 三条 entry」SHALL 得到空集且**不被当成判据通过**

### 阶段 1：IE-1 载体三分 + IE-5 孤儿 FormData

- [x] 4. IE-1 载体三分表落地 + 三条反向断言（IE-P1 / IE-P4 / IE-P5）
  - 三行落表且互不相同（I2 `host_inline`+第二写路径 · I4 `host_inline` · I5 `formdata_composable`）
  - 🔴 反向断言 ① I5 宿主**无任何 http / api client import**；
    变异「按 F 版守卫要求宿主自带 GET+PUT」SHALL 在 I5 上打红
  - 🔴 反向断言 ② 三条 entry checklist GET == 0
  - 🔴 反向断言 ③ 三个 0 值各附解释（I5 `http_import` 0 = 无导入入口靠 composable 建行 ·
    I2 `isOoAvailable` 0 = 不做 OO 可用性探测 · I2 结构化开关 0 = 无该开关）；
    按 IC-20 **不宣称该维度通过**
  - 登记 `useAdjustmentCentralSync` 三处（`I2TabAdjustment.vue#L374` / `I4#L450` / `I5#L467`）

- [x] 4a. I2 双写一致性判据（IE-P3）
  - 断言两条写路径打**同一端点** `PUT /api/workpapers/{wpId}/checklist-responses`
    与**同一 item 形状** `{item_id, conclusion, remark}`
  - 判据：经 `useI2FormData._doSave` 保存后，从 adapter 侧读到的载荷 == 经宿主内联写入后读到的载荷
  - 🔴 变异「只验宿主内联那条路径」SHALL 因漏掉第二写路径而在分叉场景下打红

- [x] 5. IE-5 BP-5 的 I4 侧：零消费禁接（IE-P2）
  - 用 IC-3 三形态（`from` / `import(` / `vi.mock(`）现算 `useI4FormData.ts` 消费方 == 0，**两侧都断言**
  - 列入 `i4.*.json` 的 `forbidden_carriers`；🔴 **本 lane 不删文件**
    （删除是跨 spec 清理动作，与并发会话有冲突风险；禁接已足够防误用）
  - 🔴 对照断言 `useI2FormData.ts` 消费计数 **> 0**（现算 4）⇒
    变异「把三个 FormData 一起列入可删名单」SHALL 打红

### 阶段 2：分类三边（IE-5 续）

- [x] 6. BP-8② `CATEGORY_OPTIONS` 三边校验（IE-P17）
  - 三边：①声明 `明细表I4-2!A11` ②openpyxl 真读 **1 条**（`使用权资产改良及维护支出`）
    ③impl **6 条**；**有序等值**比对，禁集合比对
  - 登记 `A9`/`A10` 空 + `A12:A22` 全空 ⇒ 无真源尾部 **3 条**逐条列出
    （`租入固定资产改良支出` / `固定资产大修理支出` / `开办费`）；「3 条」与列举数相等
  - verdict `PREFIX_MATCH_WITH_UNSOURCED_TAIL` / status `defect_registered_not_fixed`
  - 🔴 反向自检：把 declaration 的 `expected_source_labels` 改一字，判据 SHALL 点名那一条

- [x] 6a. BP-8② 的修法（2026-10-01：模板不完整 + impl 有税法依据，保留 impl）
  - 🔴 **复核结论翻面**：此前记「第 2~4 条是否属长期待摊费用合法分类属会计判断」。
    真读 `明细表I4-2!A11:A22`：仅 `A11=使用权资产改良及维护支出` 一条，`A9/A10` 空、`A12:A22` 全空 ⇒ **模板不完整**，不是 impl 多列错。
    impl 税尾 3 条（`租入固定资产改良支出`/`固定资产大修理支出`/`开办费`）**有平台内税法条文依据**，见 `useI4Detail.ts#I4_2_TAX_NOTES`：
    《企业所得税法》第十三条（租入固定资产改建支出 / 固定资产大修理支出 / 其他规定支出）+《实施条例》第六十八条；开办费为筹建期费用的会计实务经典长期待摊科目
  - 修复：provider `phase5_i4_02_detail.py#CLASSIFICATION_FACTS_I402` 改 `verdict = IMPL_AUTHORITATIVE_TEMPLATE_INCOMPLETE` ·
    `status = resolved` · 加 `authority_refs`（税法条文）+ `authority_impl_ref`；契约重生成（非手改 JSON），canonical_digest 不变
  - `category` 是明细行自由下拉选项（非固定表结构行）⇒ 选项增减不影响已填数据 key；真库 `i42-%` **0 行** 无迁移风险
  - 验证：契约 `i4 classification = IMPL_AUTHORITATIVE_TEMPLATE_INCOMPLETE/resolved`；契约全量 check rc=0；golden digest rc=0
  - 🟡 残留业务背书（低风险，默认保留，不阻塞）：**B-2** 分类选项是否需增补 —— 见
    `i1-i3-disclosure-positional-identity-and-classification-source/evidence/classification-decision-and-business-checklist-2026-10-01.md`

- [x] 7. CD-3 / CD-5 / CD-6 落表（IE-P18 / IE-P19）
  - **CD-3（I5）**：`I5_BUILTIN_CATEGORIES` **10 条** 对 `明细表I5-2!A11:A20`（10 格）有序等值 ⇒ clean；
    一并登记 `A21`=`……`（可扩位）· `A22`=合计 ⇒ 声明区间边界正确
  - **CD-5（I2）**：`NO_IMPL_CLASSIFICATION_BY_DESIGN` / clean
  - **CD-6（I2）**：`defaultPerCapitaPeers` ⇒ `HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF` /
    `scanned_and_classified_not_a_defect`；SHALL 写明「不是缺陷」的理由
    （同业人均数对照表的默认行数种子，模板无对应分类区间 ⇒ 无真源是设计）
  - 🔴 断言 CD-5 与 CD-6 同属 I2 但两 verdict，status 维度**不相加**（IC-5 已裁）

- [x] 8. 源模板真源断链 1 处登记不修（IE-P20）
  - `明细表I2-2!A17` 是字面 `数据资源`（不是 `=底稿目录!A18`）⇒ 断言改 `A18` **不传播**
  - 登记另 2 处在 I1 ⇒ 归 lane 1；🔴 不改模板字节、不开覆盖层例外

### 阶段 3：IE-3 definedName 基线 + IE-2 几何三形态

- [x] 9. definedName 基线口径 + 双变异（IE-P10 / IE-P11 / IE-P12）
  - 登记基线 `{I1:0, I2:0, I3:0, I4:476, I5:334, I6:0}`（现算，合计 810）+ 断言**不增长**
  - 🔴 双变异：①「给 I1 加一个 definedName」SHALL 打红
    ②🔴「把判据写成 definedName 全 0」SHALL 在 **I4/I5 打红**
    —— 本 lane 是全 I 唯一能捕获「照抄 H 循环 HC-14 口径」这个错误的地方
  - 声明**不删**这 810 个（是模板公式的命名引用，删了公式整片失效），
    只声明「同步时不新增、不改写」

- [x] 10. per-file 裸 IF 中性化（IE-P13）
  - 三册计数现算落表（I4 **186** / I2 **113** / I5 **49**；全 I 总 777）
  - per-file 挂 `oo_crash_neutralization_fn`；变异「整册统一挂」SHALL 打红

- [x] 11. IE-2 I5 三区 + 镜像 + 三 footer（IE-P7 / IE-P8 / IE-P9）
  - 三区落表：R11-21 原值（editable）· R24-34 减值准备（editable）·
    🔴 R37-47 净值（**`fully_derived_region`**，= 原值 − 减值）
  - 🔴 第三区回写时**整区跳过**、不接受用户输入；
    变异「允许写第三区」SHALL 因「下次 render 被公式覆盖导致静默丢失」而打红
  - 🔴 断言三区**行数各 11 且按行序镜像对应**；变异「把某一区改成 10 行」SHALL 打红
  - `footer_rows: [22, 35, 48]` 三个**分别**标 `footer_kind`；只声明第一个 SHALL 打红

- [x] 11a. I4 双区 + I2 单区落表（IE-P6）
  - I4：`regions[1] = {rows:[24,28], kind:"derived"}`（IC-19）
  - I2：单区 R13-22，无派生区
  - 三册 UUID 落位「有效列 + 1」：I2 **21** / I4 **23** / I5 **18**；
    🔴 I2 不得放 62（`max_column` 61 而有效 20，差 **41** 列，全 I 差距最大）

### 阶段 4：IE-4 I5 内置行身份

- [x] 12. I5 内置行重置现象落判据（IE-P14）
  - 断言 `removeRow` 的 `isBuiltin` 分支传入 4 字段（`projectName`/`name`/`isBuiltin`/`indexRef`）
    **不含 `rowId`**，且 `emptyI5DetailRow` 内 `#L305 rowId: generateRowId()`
  - 🔴 复现现象：删内置行 → 重读 → `rowId` **变了**但 `projectName` 没变
  - 登记 `#L830` 的兜底逻辑用 `projectName` 反查 `indexRef` ⇒ 实现自己已把 `projectName` 当稳定标识

- [x] 13. I5 内置行修复①+②双保险（IE-P15）
  - ① 改 `useI5Detail.ts#L826` 传入 `rowId: row.rowId`（一行，治未来）
  - ② 契约声明 `builtin_row_identity_field = "projectName"` +
    `builtin_row_delete_semantics = "reset_in_place"`（治历史已漂移数据）
  - 🔴 判据分别验：①修复后删内置行 `rowId` **不变** ②按 `projectName` 查得到那一行
  - 🔴 断言契约里**两个身份字段都存在**；只声明 `rowId` 一侧 SHALL 打红

- [x] 14. 删行两族在本 lane 是 1:2（IE-P16）
  - 落表：I2 `useI2Detail.ts#L505 removeRow(index: number)` → `index` ·
    I4 `useI4Detail.ts#L672 removeRow(rowId: string)` → `identity` ·
    I5 `useI5Detail.ts#L821 removeRow(rowId: string)` → `identity`
  - 🔴 断言与 lane 1（两条 entry 100% 下标族）**不复用同一个签名断言**，
    否则一边必然假红或假绿

### 阶段 5：IE-8 门控 + IE-7 键冻结与 wp_index

- [x] 15. IE-8 I2 缺二级门控 + `gate_layer` 三值（IE-P27 / IE-P28 / IE-P29）
  - IC-16 门控判据 SHALL **按 toolbar class 定位区块**（防 `I1#L171` / `I4#L142` 误判）
  - 🔴 反向自检：把判据改成「全 slice 都有二级门控」SHALL 在 I2 上**从静默恒真变打红**；
    若改了还恒真 ⇒ 判据分母是空的（IC-20 要防的重言式）
  - 🔴 `gate_layer` 三值落表：I2 `host_tab`（`I2TabAdjudication.vue#L384` 自建）·
    I4 `composable`（`useI4Adjudication.ts#L371`）· I5 `composable`（`useI5Adjudication.ts#L362`）
  - 🔴 判据按 **entry 维度**找门（composable 或宿主 Tab 任一处有即算有）；
    变异「写成 composable 里必须有 `publishToTb`」SHALL 在 I2 上假红并被捕获
  - 三条 entry 一律只走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` + 二次确认；
    禁 `watch`/`onMounted`/debounce 内发布；**复用**平台既有 2 道 CI 守卫与
    `iAdjudicationPublishGate.spec.ts`，不重造

- [x] 15a. I2 发布门收敛到 composable
  - ✅ **已收敛（2026-10-01）**：二次确认→save→唯一 publish-to-tb 端点整体搬进 `useI2Adjudication`，host 只绑按钮；参数化 gate 20 passed，契约重生成/新 bundle/representation 重发布后真 OO I2 再验通过
  - 🔴 **假绿复位（2026-10-01）**：I2 契约仍登记 `gate_layer: host_tab`，`useI2Adjudication.ts` 无 `publishToTb`；详见 `i1-i3-disclosure-positional-identity-and-classification-source/evidence/lane1-2026-10-01-positional-fix-and-registration.md` §六
  - 收益判据统一且保留二次确认/互斥锁；契约现登记 `gate_layer: "composable"`

- [x] 16. IE-7 wp_index 规避 + 跨 lane 键冻结（IE-P24 / IE-P25 / IE-P26）
  - 🔴 登记 **`I2-1` 一码两名两底稿**（`商誉减值测试` ×1 业务上属 I3 / `开发支出审定表` ×3）
  - 契约 `source_ref` 只 `{workbook_sha256, sheet_name}`，🔴 **禁任何 wp_index 字段**，schema 卡死；
    变异「用 wp_index 的 `I2-1` 反查底稿」SHALL 打红（会取到 I3 的底稿）
  - 登记两套编号体系例 `I2-3`
  - 🔴 `I2-2-rows` 引用点集合**现算**（当前 16 处，禁写死），含
    `i2ConsistencyModel.ts#L213` 的前缀映射 `'I2-2-': ['I2-2-rows']`；
    改键名 SHALL 打红（同时打断 lane 1 消费边与一致性检查前缀表）
  - 断言 `composables/useI2Analysis.ts` 读 `I6-2-detail-rows`，canary 注册后仍取到同一载荷；
    🔴 断言 **H1 pilot golden digest 不变**

### 阶段 6：三份契约 + 注册 + roundtrip + 交接

- [x] 17. 三份契约落地（IE-P6 / IE-P21 / IE-P23，字段见 design §三份契约）
  - ✅ **i2 已交付（2026-09-27）**：provider phase5_i2_development_expenditure.py + sheet spec phase5_i2_02_detail.py（三级表头 header_rows=3 / 7 公式列 / footer 非单一形态 R23=P23-Q23）+ registry 台账；契约由 uild_contract_payload() 生成（18,227 B / LF / canonical 一致），parse_contract 与 ssert_contract_file_matches_source() 双向锁均通过；mask 与 editable 零冲突
  - ✅ **i4 已交付（2026-09-27）**：provider phase5_i4_long_term_prepaid.py + sheet spec phase5_i4_02_detail.py（三级表头 R8-R10 / 6 公式列 / 双区 R24-28 ArrayFormula 派生 / definedName 476 基线 / CD-8 无真源尾 3 条 / removeRow id 族）+ registry 台账；契约 20,232 B 双向锁通过 / masked_editable=0
  - ✅ **i5 已交付（2026-09-27）**：provider `phase5_i5_other_noncurrent_assets.py` + sheet spec `phase5_i5_02_detail.py`。🔴 **三区完全镜像是平台新形态**（一行同时在三个区，与既有「一区一 store 键」`phase5_d3_04_analysis` 和 `region_filter` G9/G1 两范式都不同）⇒ 用**两个 spec 共享同一 store_item_id**（契约两 table，json_key 走 `gross/*` 与 `impairment/*`），区③ fully_derived_region 不建 spec；区②的 A 列是 FORMULA 镜像不映射 store 字段（否则 merge 会拿 None 覆盖镜像公式）。契约 27,854 B 双向锁通过 / masked_editable=0 / store item 去重=1 / sheet 去重=1
  - `i2.development_expenditure_detail.json`（`provider_id = phase5_development_expenditure_detail`）：
    含 `second_write_path` / `gate_layer: host_tab` / `secondary_ui_gate: false` /
    `frozen_key: true` + `frozen_reason`（lane 1 消费 + 前缀映射）
  - `i4.long_term_prepaid_detail.json`（`phase5_long_term_prepaid_detail`）：
    含 `forbidden_carriers` / `classification` BP-8② / `defined_name_baseline: 476` /
    `payload_column_mode: dual_write` + `unverified_in_live_db` /
    `sheet_name_traps: ["摊销测算表I4-7（工作量法）"]`（🔴 禁 strip 括号）
  - `i5.other_noncurrent_assets_detail.json`（`phase5_other_noncurrent_assets_detail`）：
    含三 `regions` + `region_mirror` / `footer_rows:[22,35,48]` /
    `builtin_row_identity_field: projectName` / `defined_name_baseline: 334` /
    `payload_column_mode: passthrough` + `unverified_in_live_db` +
    🔴 `live_payload_flag: live_payload_is_e2e_seed_not_business_data`
  - 三份均：`positional_identity.sites: []`（主动断言）· `excluded_sheets: ["GT_Custom"]` ·
    `derived_total_keys` **现算**（I2 2 / I4 0 / I5 0，禁写死）· per-file 中性化 · `variant_axis: null`

- [x] 18. 注册 + 零回归重算（IE-P31，IC-1）
  - ✅ **已注册（2026-10-01）**：I2/I4/I5 approved bundle + current representation；manifest 三条已翻转，真实 PG register 全 OK；证据 `../i-cycle-sync-foundation-and-first-canary/evidence/task22-24-gates-cleared-2026-10-01.md`
  - 🔴 **回滚原因（2026-09-27 复盘）**：注册需 provider 就绪
  - 🟡 **现状（2026-10-01 真实 PG 实测）**：I2/I4/I5 provider + 契约 + 台账 + 白名单均已就绪，注册计划绑定、`blocked_reason=None`；`register_from_manifest` 实际注册 0 条，原因是无 current published representation（BP-2/BP-3）⇒ 保持 `[ ]*`；证据 `i1-i3-disclosure-positional-identity-and-classification-source/evidence/lane1-2026-10-01-positional-fix-and-registration.md` §五
  - 只走 `register_from_manifest()`，🔴 **禁手改 manifest 文件**；注册后 `capability` 才变 `bidirectional`
  - 重跑 Task 2 基线：契约目录 +3、注册集 +`{i2, i4, i5}`；🔴 全部**现算**比对，禁写死
  - 复跑 149 KB 守卫 `test_task51_i_cycle_migration.py` 零回归

- [x] 19. roundtrip 合成载荷实证（IE-P32，BP-4 已解除）
  - ✅ **真 OO（2026-10-01）**：I2 `i-oo94-i2-1de4d7db5bcf` / I4 `i-oo94-i4-2411d20845ff` / I5 `i-oo94-i5-dc80dc19f756`；G1/公式/DB 快照全绿，证据 `../i-cycle-sync-foundation-and-first-canary/evidence/task22-24-gates-cleared-2026-10-01.md`
  - 🔴 **假绿复位（2026-10-01）**：无真 OO `sync_test_run_id`；详见 `i1-i3-disclosure-positional-identity-and-classification-source/evidence/lane1-2026-10-01-positional-fix-and-registration.md` §六
  - 🔴 三条都用**合成载荷**：I2/I4 真库无行 · I5 那 745 B 是 E2E 种子**不可作基线**；
    证据标 `synthetic_payload`
  - 合成载荷四条件：①I5 三区各 11 行行序镜像（验第三区整区跳过）②含 ≥1 个 `isBuiltin: true` 行
    （验重置后 `rowId` 不变）③I2 载荷经两条写路径各写一次（验不分叉）
    ④I4 载荷写 `conclusion` 列（验不破坏 `remark_only` 读侧）
  - 三条冻结：冻 `useAdjustmentCentralSync`（三处）· 排除 `derived_total_keys`（I2 2 / I4 0 / I5 0）·
    不改三个主表键名 · 完成后回归 H1 golden digest 不变
  - 🔴 `evidence.sync_test_run_id` 须来自真 OO 栈，**不得** mock 充数

- [x] 19a. 人工审核契约与 approved bundle（BP-2/BP-3 已解除）
  - ✅ **已发布（2026-10-01）**：三条 reviewed contract + approved bundle + current representation 独立发布，证据 `../i-cycle-sync-foundation-and-first-canary/evidence/task22-24-gates-cleared-2026-10-01.md`
  - 🔴 **假绿复位（2026-10-01）**：approved bundle / published representation 未产出；详见 `i1-i3-disclosure-positional-identity-and-classification-source/evidence/lane1-2026-10-01-positional-fix-and-registration.md` §六
  - 产出 `review.entry_id` 为 `xlsx/gt-i2-…` / `xlsx/gt-i4-…` / `xlsx/gt-i5-…` 的 per-entry contract
  - 🔴 判据是「逐文件读 `review.entry_id`」**不是数契约个数**

- [x] 20. 交接与复盘核验（不改代码，只核）
  - IC 引用闭合性：本 spec 的 `IC-\d+` 引用集合 ⊆ 地基 spec 的 `### IC-\d+` 定义集合，无悬空
  - 🔴 断言本 spec **无一条复述** IC 正文（只写编号 + 一句话用途）
  - entry 归属：本 lane 恰为 {`xlsx/gt-i2-development-expenditure`,
    `xlsx/gt-i4-long-term-prepaid`, `xlsx/gt-i5-other-noncurrent-assets`}，
    与地基 spec Task 25 的归属表一致；entry 一律写全名（禁 `I2` 简写作归属键）
  - 「N 处」类表述与列举项数**逐条相等**（无真源 3 条 / `gate_layer` 3 值 / 三区各 11 行 /
    三 footer / 16 处引用点 / 三个 0 值）
  - 计数类要么现算要么标明「现算值 + 禁写死阈值」；全文无 U+FFFD
  - 🔴 与 lane 1 对账：`I2-2-rows` 冻结在两份 spec 里的表述一致；两个 lane 的
    `row_delete_api_kind` 判据**未复用同一断言**
  - 逐条确认**未交付项**的归属与理由：BP-8② 修法（业务确认）· I2 门收敛（UI 回归）·
    `useI4FormData.ts` 删文件（另起清理 spec）· `I2-1` wp_index 修数据（数据治理另议）·
    真源断链 1 处（登记不修）· roundtrip（BP-4）· 人工审核（BP-2/3）

## 阻塞项对齐

| BP / 事项 | 归属 | 本 spec 交付 |
|---|---|---|
| BP-1 ~ BP-4 | 平台级（全循环共有） | 只标 `[ ]*`，不承诺 |
| **BP-5**（I4 侧） | **本 lane** | Task 5（`forbidden_carriers`，不删文件） |
| **BP-8②** 判据 | **本 lane** | Task 6 |
| **BP-8②** 修法 | `[ ]*` 业务确认 | Task 6a |
| **IC-16** I2 门控例外 | **本 lane** | Task 15（含反向自检） |
| `gate_layer` 三值（🔴 新） | **本 lane** | Task 15 |
| I5 内置行 rowId 保留 | **本 lane** | Task 12/13（①+②双保险） |
| definedName 基线唯一实证场 | **本 lane** | Task 9（双变异） |
| I2 发布门收敛 | `[ ]*` UI 回归 | Task 15a |
| `useI4FormData.ts` 删文件 | 另起清理 spec | 只禁接 |
| `I2-1` 一码两底稿 | 登记 + 契约规避 | Task 16（不改 wp_index 数据） |
| 源模板真源断链 1 处（I2） | 登记不修 | Task 8 |
| BP-6 / BP-7 / IC-14 | **lane 1** | 不在本 lane（IC-6 在本 lane 命中 0，Task 3 主动断言） |
| BP-9 / BP-10 / BP-8① | 地基 spec | 不在本 lane |
