# Implementation Plan

## Overview

**spec**：`f3-sync-coverage-and-first-canary`　**创建**：2026-09-26　**状态**：**14/20 已实施**（2026-10-03 复盘修正，原 10/20 偏低）
**上游**：umbrella Task 48 · FC-1~FC-13（`f1-sync-coverage-and-first-canary/design.md`；**FC-11 由本 spec 提出**）·
D1 引擎 · D1 应收票据镜像先例 · D2-1 稳定 rowKey 固定行先例

## 实施进度（2026-09-26）

已完成 Task 0~8 + 17（canary 链路 + FC-11 全链路）。判据
`backend/tests/workpaper_sync/test_f3_canary_and_contract.py` **32 passed / 2 xfailed**
（2 个 xfail 是 BP-61-1 卡点的如实标记）；`backend/tests/test_f345_fc11_prefill_cells_invariant.py`
**25 passed**。

🔴 **实施中实测修正 spec 的四处**（详见 `evidence/task2-morphology-and-geometry.md`）：

1. **FC-10 判定方法论**：数据区 `number_format` 含 `%` 的列有 C/D/E/I 四列，但 C/D/E 是
   「文本列套错 `0.00%` 格式」的模板治理债 ⇒ 真命中只有 **I 列**。判据必须是
   「前端存 % 数值 ∧ 模板百分比格式 ∧ **该列语义确实是比率**」三条同时成立。
2. **F3-H1 的「可做真数据往返」**：真库 675 B 实测是 **2 行空白行**（仅 `rowId`/`seq`/`attSlot`
   有值，业务字段全空）⇒ 能验「真行身份 + 键映射 + 投影管线」，不能验真实数值往返；
   有意义数值的 roundtrip 与 F5 一样需 seed。
3. 🔴 **F3-7 三区的 `uuid_col` 不能全写 S**：同 sheet 多区靠 `uuid_col` 配对 spec↔contract table
   （框架层源码注释：缺它 → 匹配 0 张 → `ProviderCapabilityError`）⇒ 实测全空列 8 个（S~Z），
   改为 **S / T / U**。provider 的 `build_contract_payload()` 已加兄弟区重复检测并抛。
4. **契约装配一律走框架层 `spec_to_contract_sheet_payload`**，不照抄 F1 的手写 `_rows_table_payload`
   （后者缺 `anchor`/`header_rows`/`row_identity.json_pointer` 等必填，`parse_contract` 直接抛
   `ContractSchemaError`；F1 的该缺陷已登记移交）。

🔴 **FC-11 根因实测比 spec 记载多一处**：除 `_ensure_cells` 外，`_ensure_block` 的 `new_block`
也造 `items` 键；另有 13 处 `items_key` 兼容读。三者已一并收敛为 `_cells()` 单一口径。

`[ ]*` = 依赖外部供给（BP-61-1 / OO 真栈 / 模板覆盖层 / 业务确认），如实登记 `upstream_gap`。

## Tasks

### 阶段 0：前置门 + 形态判定 + 红判据

- [x] 0. 前置依赖核查（`git show HEAD:`）：框架层 `RowTableSheetSpec` / 兄弟 Table ref 位移（F3-7 三区与 F3-1 拆 spec 都依赖）/
  `merge._protection` 格级判定；模板覆盖层 spec 交付状态（决定 F3-4 方向②是否可选）
  - 证据 `evidence/task0-prerequisites.md`
  - _Requirements: 1.2, 5.3, 6.1_

- [x] 1. slice 核对 + wp_code 裁决条目
  - 核 F 循环 slice 中 `xlsx/gt-f3-notes-payable` 的 `migration_state` / 五个 null 供给位 / `template_ref` /
    `scenario_profile_id` / `mount_count=2` 与现 manifest 一致
  - 新增 F3 裁决条目（`wp_codes=["F3"]` + `F3-5-rows` 675 B 载荷证据 + `matcher_domain_conflict=null`），重算 digest
  - _Requirements: 1.3_

- [x] 2. 形态判定 + 几何逐格实测 + 下游消费方 grep
  - 七张受管候选的表头/数据/footer/UUID 列逐格复核；F3-1 R7/R8 vs R9/R10 公式集合差异（裁决 F3-H4 依据）
  - 三元组实证表（add/del/rowId/rowKey 计数）；`F3-2-rows` 6 处引用、`F3-3-rows` 读写方（复核红基线 B8 旧结论）
  - FC-10 命中四列逐列确认前端单位；F3-2 DV 两枚举 vs 前端 4 项 vs META 5 类的三方不一致登记
  - 证据 `evidence/task2-morphology-and-geometry.md`
  - _Requirements: 2.1, 2.3, 3.3, 3.4, 6.1_

- [x] 3. F3-P1 / P2 / P3 红判据（现状必红，记录红形态）
  - P1 migration_state；P2 键名两条变异；P3 F3-1 `rowKey` vs `rowId`
  - _Requirements: 1.5, 2.1, 2.2_

- [x] 4. F3-P4 / P9 红判据：footer marker 含空格 + FC-10 四列不受管
  - _Requirements: 2.4, 3.3, 4.3_

- [x] 5. F3-P12 / P13 红判据：FC-11 死配置 + 已修缺陷回归守卫
  - P12 四条子判据（items 键数 / `_ensure_cells` 源码 / `--check` 变异 / 预设数增长）；P13 累加器键集合 + 附注口径
  - _Requirements: 7.2, 7.4_

- [ ]* 6. F3-P15 零回归基线（10 contract golden digest 现算记录）
  - 🔴 **卡外部**：`check_sync_provider_golden_digest.py` 当前**整体红** —— 并发会话已把 F1 加进
    `PROVIDERS`，而 F1 的 `build_contract_payload()` 过不了 `parse_contract`
    （`table anchor 必须是 A1 单元格，实得 None`，手写 payload 缺必填字段）⇒ 该门在 F1 修好前
    无法产出基线。已登记移交 `f1-sync-coverage-and-first-canary`。
  - 替代验证（已做）：F3 契约自身的 `canonical_digest=4530e9050bb891b7199c7297604fbf5567d94a990793906870ad143323a9197a`
    + `assert_contract_file_matches_source()` 无漂移 + 生成器 `--check` OK；
    `test_platform_contract_disk_byte_stability` 的「仅在磁盘」已清空（三份契约均已登记）。
  - _Requirements: 7.5_

### 阶段 1：canary 链路（F3-5）

- [x] 7. `phase5_f3_notes_payable.py` 从零建
  - `ENTRY_ID="xlsx/gt-f3-notes-payable"` / `ADAPTER_ID="f3.notes_payable_detail"` / `WP_CODES={"F3N"}` /
    `TEMPLATE_RELATIVE_PATH="F/F3 应付票据.xlsx"` /
    `TEMPLATE_SHA256="06de707ba4d4f8d91534e872c7d135b9576cc3a012e3877b1f60db59ce6b3a6b"`（本 spec 实测，79,616 B）
  - `assert_entry_selectable(*, resolution, manifest=None)`（D3 同签名、无关闭开关）+ `build_matcher()`
    （`document_type="xlsx"`）+ `build_registration` 照 D3:830（`matcher=` / `declared_capability=`）+ **真构造判据**
  - 七个灰度开关（除 F3-5 外默认 False）+ `managed_row_table_specs` + `all_store_item_ids` + 单数
    `STORE_ITEM_ID="F3-5-rows"` + `instrumentation_specs()` 复数 + `build_contract_payload` + `attach_pilot_adapters`
  - _Requirements: 1.2, 1.3_

- [x] 8. `phase5_f3_05_overdue.py` canary 薄声明（无 def/class）
  - `F3-5-rows` / `rowId` / 两级表头 R5/R6 / 数据 R7-21 / footer R22「合计」/ UUID **P** / `formula_columns=()`
  - 字段键逐字取 `useF3OverdueCheck.F3OverdueNoteRow`；🔴 I 列（票面利率）FC-10 ⇒ 不进 `field_specs` 并登记原因；
    O 列（抵押金额，有 footer SUM）是业务列不可作 UUID
  - _Requirements: 1.1, 2.2, 3.3_

- [ ]* 9. 契约发布链五环 + 登记点　**①②环 ✅ / ③④⑤环卡 BP-61-1**
  - ✅ 第①环：`backend/scripts/gen/generate_phase5_f3_contract.py --apply` 已交付并跑通，
    产出 `backend/data/workpaper_sync_contracts/f3.notes_payable_detail.json`
    （`canonical_digest=4530e905…`）。🔴 生成器内置 `parse_contract` 预检 —— 落盘的契约必定可解析
    （F1 的手写 payload 就是绕过这一步才在 registry 侧炸的）。
  - ✅ 第②环：`assert_contract_file_matches_source()` 通过（判据 `test_disk_contract_matches_source`）。
  - 🔴 第③④⑤环（approved bundle → published representation → entry_state → `register_from_manifest()`）
    **卡 BP-61-1**：slice 实测 `published_representation=null`（五个供给位全 null），
    `working_paper_sync_entry_state` F 循环 0 行 ⇒ 如实登记 `upstream_gap`，
    `adapter_registered=False` 与真库对齐。`attach_adapters()` 在供给未就绪时返回空元组且一次库都不读。
  - ✅ 登记点：`DELIVERED_PER_ENTRY_CONTRACTS`（registry.py，含完整 reason）+
    `_ALLOWED_PROVIDER_MODULES` 已加 `phase5_f3_notes_payable`。
  - [ ]* 待做：`store_item_registry` plan · `check_sync_provider_golden_digest.PROVIDERS`（该门被 F1 阻塞，
    见 Task 6）· overlay 裁决 + 重生 manifest（会改动并发会话正在写的文件，留到 F1/F2 收口后做）
  - _Requirements: 1.4, 1.5, 7.5_

- [x] 10. 宿主接桥（保留 legacy）
  - `GtF3NotesPayable.vue` 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`；`F3_SHEET_KEY_BY_CODE` +
    `isF3SyncManagedSheet` 从 provider 派生；🔴 `currentSheet` 正则 `/(F3A|F3-\d+)/`（L434）与 `F3A` 末尾空格不受影响
  - _Requirements: 1.6, 7.6_
  - **已完成**：受管分支 `v-if="dualMode.currentMode.value === 'onlyoffice' && isF3SyncManagedSheet"`
    走 `WorkpaperSyncEditorHost`，非受管降级 `v-else-if` 保 legacy `GtOnlyOfficeSheet`；工具栏加
    「同步中…」tag；`.oo-container { min-height:600px; height:calc(100vh - 200px) }`（EditorHost 自身不带高度）。
    `currentSheet` 正则与 `F3A ` 末尾空格未动（判据 `GtF3NotesPayable.integration.spec.ts` 仍绿）。
  - 🔴 **`useF3FormData` 补导出 `flushPendingSave`**：`_flushPending()` 实现（清 `_debounceTimers` +
    保存 `_pendingItems`）**早已存在**且 `onScopeDispose` 在用，只是没对外导出 ⇒ 改动是一行。
    `flushHtml` 顺序不可换：先 `formData.flushPendingSave()` 再 `readStoreProjection`，否则读到旧快照、
    切 OO 后用旧值覆盖 HTML 侧刚写的编辑。
  - 🔴 **拒绝照抄 F1 宿主**（两处缺陷已移交 F1 spec）：① `GtF1Prepayment.vue:419` 调用**未定义**的
    `flushPendingSave()`（`useF1FormData` 不导出、宿主内也无定义）⇒ `ReferenceError`；
    ② `WorkpaperSyncEditorHost` 必填 props 是 `descriptor` + `bridge`，F1 传了 `wp-id`/`project-id`/`readonly`
    三个**不存在的 prop** 却**漏掉 `descriptor`** ⇒ 编辑器永不创建。本次照 E1 正确范式。
  - 🔴 `readStoreProjection` 的 `WorkpaperSyncEntryScope` **无 `sheetKey` 字段**（F1 多传了）；
    sheetKey 应由 `flushHtml` 的返回值 `WorkpaperSyncFlushResult.sheetKey` 回传 —— 多 sheet entry 必须带。
  - 类型核查：`npx vue-tsc --noEmit -p tsconfig._f345-canary.json` 三宿主 + 三 composable **零错误**。
  - 未做（如实）：Playwright 真栈实测卡 BP-61-1（slice 供给位全 null，OO 侧无 published_representation）。

- [ ]* 11. canary 验收：三谓词 + DB 证据（真库 `F3-5-rows` 675 B 做真数据 roundtrip）
  - _Requirements: 1.7_

- [x] 12. 批量 e2e 骨架：`e2e/fixtures/f3-l2-cases.json` + `e2e/f3-l2-oo-to-html-all.spec.ts` +
  `backend/scripts/e2e/seed_f3_publish_e2e.py`（照 D4/E1 lane，七态枚举）
  - _Requirements: 1.7_
  - **已完成**：`e2e/fixtures/f3-l2-cases.json` + `e2e/f3-l2-oo-to-html-all.spec.ts`（3 tests：
    2 条前置 + 1 条 canary），七态枚举沿用。`npx playwright test --list` 实测 **3 tests** 正常加载。
  - 🔴 **seed 脚本三 spec 合一**：不建 `seed_f3_publish_e2e.py`，改用
    `backend/scripts/e2e/seed_f345_canary_rows.py --entry f3`。理由：F3/F4/F5 要造的东西逐字同构
    （往 `checklist_responses` 写一条 `(wp_id,item_id)` 行数组），分三份会造三处重复实现，而
    seed 的风险点（覆盖真实数据 / 行身份不稳 / 非幂等）需要一次修对三处生效。
  - **F3 的 seed 决策是 `no_seed`**：真库 `F3-5-rows` 已有 **2 行真实行身份**（675 B，
    `_seed` 标记为 null ⇒ 确为真实数据）。覆盖会毁掉 roundtrip 的锚（换 id 等于把 A 行的值并进
    B 行）。脚本两道安全线实测拦住了覆盖：`--entry f3` → `skipped_no_seed`；
    加 `--fill-blank-values` → `refused_would_overwrite_real_data`（要 `--force` 才写）。
  - 🔴 **诚实边界**：那 2 行是**空白业务行**（仅 rowId/seq/attSlot 有值），故 roundtrip 验证的是
    「行身份与结构」而非「有意义数值的往返」。spec F3-H1 原写「可做真数据往返」已据此修正。
  - 🔴 **fixture 必须 `readFileSync` 不能 `import`**：`import cases from './fixtures/*.json'`
    在 Playwright 的 Node ESM 加载器下抛 `needs an import attribute of "type: json"`，
    整个文件 **0 tests**。实测对照：`f1-l2-oo-to-html-all.spec.ts --list` = `Total: 0 tests in 0 files`
    （F1 第三处缺陷，已移交 F1 spec）；本文件 = 3 tests。
  - 未做（如实）：真栈三谓词卡 BP-61-1（canary 用例 `pending_adapter` skip）；前置断言待后端可用
    （实测 9980 被 `start-dev.bat` 启的 reloader 进程占用但 HTTP 30s 无响应，非本 spec 范围）。

### 阶段 2：F3-6 + F3-7（三区）

- [x] 13. `phase5_f3_06_related_party.py`：`F3-6-rows` / 表头 R6 / R7-12 / footer R13 / UUID **N** /
  `formula_columns=("G",)` / `{"G":"=D{r}+F{r}-E{r}"}`；前端 `recalcRelatedPartyRow` 等价核（FC-5）；
  下拉源区 R18-26 保护 + F3-P11
  - **已完成**：`phase5_f3_06_related_party.py` + `_INCLUDE_F306=True` + 契约重算
    （digest `4530e905…` → `43a2da2b4fbb50fd00f4f4014d0c000408b6645027b66cd030966eba17ff9ade`，过 `parse_contract`）；
    判据 32→**58 passed**（+26 条）；`check_sheet_specs_fully_registered` 20→**21 adapter**；
    变异 **8/8 被抓**。spec 声明的几何/UUID/公式全部实测属实。
  - ✅ **验证了"复用框架层零改动"**：F3-6 是最标准的行表形态（单级表头 + 单区 + 一个公式列），
    `RowTableSheetSpec` 原样够用，**未改框架层一行**。
  - ✅ **FC-5 等价核通过**：模板 `G{r}=D{r}+F{r}-E{r}`（期末 = 期初 + 贷方 − 借方，R7~R12 逐行同构）
    ≡ 前端 `closingBalance = round2(openingBalance + creditMovement - debitMovement)` —— 逐项对应，
    两边不需统一口径。判据读前端源码时**先剥注释**再比对（文本匹配会被注释里的旧写法说明误命中）。
  - 🔴 **修正 spec**：Task 13 写的前端函数名 `recalcRelatedPartyRow` **不存在**，真名是
    `computeRelatedPartyRow`（判据已断言 `recalcRelatedPartyRow` 不得出现，防名字回流）。
  - 🔴 **修正 spec**：表头是**单级 R6**（spec 记「表头 R6」正确，但要点明 **R5 是一整句说明文字**
    不是表头行 —— 判据逐格断言 A5 是长句、B5~M5 全空、R6 十三列全有文字）。照抄同册 F3-5 的
    两级 R5/R6 会让 anchor 错位到 A5（变异已验证会被抓）。
  - 🔴 **F3-P11 源区保护落地为硬上限**：实测 DV 两条 —— `C7:C12` 是内联枚举、
    `B7:B12` 的 `formula1=$B$19:$B$26` **指向表内源区**（R18 `勿改、勿删` 标记行 + R19~R26 八个
    关联关系枚举值）。DV 的 formula1 是字面量、不随插行位移 ⇒ `last_data_row=12` 是**硬上限**，
    判据断言 `last_data_row < footer_row < 源区起始行`，扩行必须走"先下移源区再改 DV"的显式迁移。
  - 实测补充：footer R13 的 SUM **只覆盖 D/E/F/G/K 五列**（不是所有数值列，判据逐列断言）；
    FC-10 整表 **0 个**百分比格式（与同册 F3-5 的 I 列命中形成对照）；三个派生字段
    （`seq`/`concentration`/`riskFlags`）模板无列 ⇒ 登记 store-only。
  - 🔴 **顺带修一处真缺陷（行身份不稳）**：`useF3RelatedParty.migrateRow` 原为
    `rowId: raw.rowId || raw.id || generateRowId()` —— 为缺 id 的行铸新 UUID，但 `loadRows()`
    **不回写** ⇒ 下次载入再铸新的，行身份每次都变，OO↔HTML roundtrip 会把 A 行的值并进 B 行
    （与 BP-7 下标派生同型危害）。修法照 F5 BP-7：`F3RelatedPartyMintStats` 出参记数 +
    `loadRows` 在 `minted>0 && !readonly` 时立即 `persistRows()`（回写内容与 watch 守卫比对的
    同一串 ⇒ 不成环）。前端判据 5→**11 passed**（+6 条，含空串/纯空格 rowId、legacy `id` 兼容、
    行身份不随行序变化、stats 省略向后兼容）。真库 `F3-6-rows` 当前 0 行 ⇒ **属预防性修复**。
  - 🔴 **顺带加固两条既有判据**（受管面扩容暴露的写死假设，不是放宽）：
    ① `all_store_item_ids()` 断言改为逐键列出 `("F3-5-rows","F3-6-rows")` —— 每开一张灰度开关
    都必须显式更新，才保住守护力；② `test_contract_field_store_item_id_matches` 从写死
    `== "F3-5-rows"` 改为**按 table 归属校验**，还能抓「F3-6 的字段错挂 F3-5 的键」这类跨 sheet 串线。
  - _Requirements: 2.3, 5.1_

- [x] 14. `phase5_f3_07_voucher_check.py` 三区声明 + F3-P10 + OCR 粒度实测（FC-8）
  - 三区各自 `field_specs`（列集不同）；UUID **S**；兄弟 Table ref 位移
  - **已完成（声明部分）**：`phase5_f3_07_voucher_check.py` 三区 + `_INCLUDE_F307=True` + 契约重算
    （digest `43a2da2b…` → `6585ab47bf4156e5527192404aca473ed5bf89f4858af07bffeeb0d3e573a258`，
    三区一次装配过 `parse_contract`）；判据 58→**84 passed**（+26 条）；变异 **8/8 被抓**。
    F3 受管面 = 3 sheet / **5 table**（F3-7 三区共享 `sheet_key="f37-managed"`）。
  - 🔴 **实测确证"三区不可互换"**（spec 只说"列集不同"，实测给出了具体分叉与其后果）：
    · 区①③ 证据组宽 **5 列**（`H15:I15` 付款审批单 2 + `J15:L15` 银行回单 3）
    · 区② 证据组宽 **7 列**（`H39:K39` 入库单/验收单 4 + `L39:N39` 采购发票 3）
    ⇒ 区② 其后所有列**整体右移 2 列**：「……」在 O（区①③ 是 M）、「索引号」在 P（N）、
    「是否异常」在 Q（O）。拿区① 的 field_specs 套区②，会把索引号写进「……」列 ——
    **一整列静默错位，且三谓词全都会通过**（值都落库了，只是落错列）。判据用模板逐格
    读表头文字确认位移（不靠声明自证），变异「区②照抄区①」被抓 5 条。
  - 🔴 **footer SUM 列集三区不同**：区①③ 是 `F, L`（银行回单金额），区② 是 `F, **N**`
    （采购发票金额）—— 随证据组宽度右移。判据逐区回模板核对 SUM 列集与区间。
  - 🔴 **三区行数各不相同**（20 / 18 / 17：R17-36 / R41-58 / R63-79），不是笔误。
    判据显式断言三个数字，变异「对称化为全 20 行」被抓。
  - 🔴 **单一共享 sheet_key**（D3-4 先例）：区级唯一性靠 `table_key`
    （`voucher_{debit,credit,subsequent}_rows`）+ `template_id` + `table_name` + `uuid_col`。
    变异「sheet_key 逐区独立」被抓（契约装配会产生同 excel_name 多条目）。
  - uuid_col **S / T / U** 逐区独立（兄弟 Table ref 位移靠它配对 spec↔table）。
    🔴 三者**均超 `max_column=R`** ⇒ instrumentation 需扩列（同 F5-8 的 uuid_col I）。
  - 三区数据区**零公式**（整表公式只在页眉 R3/R4、三个 footer 的 SUM、R83~R85 的检查比例区
    `='明细表F3-2'!N31` / `=F37` / `=ROUND(F83/E83,4)`）⇒ `formula_columns=()` × 3。
  - **FC-10 不命中受管区**：百分比格式仅 5 格且全在 R83~R87 比例区（G83-85 有公式、
    G86/G87 无公式），三个数据区零命中。判据断言 `pct_rows ∩ managed_rows == ∅`。
  - **DV 与 F3-6 形成对照**：F3-7 只有一条 DV `G17:G36 G41:G58 G63:G79` 是**内联枚举**
    （`formula1` 不含 `$`）⇒ 不依赖表内源区，插行不打断 DV；而 F3-6 的 `B7:B12` 指向
    `$B$19:$B$26` 需要硬上限保护。判据断言 `"$" not in formula1`。
  - 🔴 **新发现模板债（登记不改字节）**：前端 `F3_VOUCHER_NOTE_TYPES` 有 **4 值**
    （银行承兑汇票/商业承兑汇票/供应链票据/其他），模板 DV 只给 **2 值** ⇒ 前端可写出 DV
    不接受的值。判定为**不阻塞受管**：DV 是软校验（Excel 只在手工输入时提示），程序写入
    不受限。已登记 `NOTE_TYPE_ENUM_DEBT_F307`，判据断言"模板枚举是前端枚举的真子集"。
  - 前端交叉验证：`useF3VoucherCheck.sectionEvidenceKind()`（`credit → purchase`，其余
    `payment`）与模板实测的分叉**完全吻合**，互为印证；三个 store key 按值实测
    `F3-7-{debit,credit,subsequent}-rows`，判据断言 `F3-7-post-rows` **不得**出现
    （spec 变异②点名的 F1 式错名）。
  - store-only 四键：`seq` / `attSlot` / `issueDesc` / `sampleSource`（模板无列）。
  - 未做（如实）：**F3-P10 与 OCR 粒度实测（FC-8）未做** —— 附件/OCR 挂载粒度（`attSlot`
    是行级还是单元格级）需要前端附件链路实测，本轮只把 `attSlot` 登记为 store-only；
    真栈三谓词卡 BP-61-1。
  - _Requirements: 5.2, 5.3, 5.4_

### 阶段 3：F3-2 明细 + F3-4 利息测算

- [ ] 15. `phase5_f3_02_detail.py`：两级表头 R13/R14 / R15-30 / footer R31「合␠␠计」/ UUID **X** /
  `formula_columns=("O","R")`；派生列按 FC-7 判 `auto_source`（`termDays`/`maturityBucket`/`isOverdue`）；
  J/U 两列 FC-10 暂 HTML-only；下游 6 处消费方回写后重算
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ]* 16. `phase5_f3_04_interest.py` + F3-4 口径三方向裁决（F3-H2）
  - 默认方向③（H 列 `mode=formula` 不受管 + UI 中文提示两侧算法差异）；出业务影响评估证据；方向①②登记 follow-up
  - `injectF3Adjustments` 幂等判据（F3-P14）
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

### 阶段 4：prefill 修复（FC-11）+ F3-3 核

- [x] 17. FC-11 修复：F3 三块 `items` → `cells`（删全角重复块 `[223]`、保留半角 `[306]`）+ 工具链根因
  - 改 `fix_f_cycle_prefill_presets.py._ensure_cells` **只写 `cells`**、`--check` 只认 `cells` + 加两条校验
    （块 `cells` 非空 / sheet 名 ∈ 模板 tab）；`test_sheet_exists_in_source_xlsx[F3]` 转绿；F3-P12 转绿
  - _Requirements: 7.2_

- [ ] 18. F3-3 调整分录汇总可行性核（**不改生产代码**）
  - 实证 `F3-3-rows` 三方读写（`useF3Adjustment` / `f3AdjustmentInject` / `F3TabAdjustment`）+
    `useAdjustmentCentralSync`（`F3TabAdjustment.vue:36`）⇒ 默认 `single_html`（FC-6）；证据 `evidence/task18-f33-single-html.json`
  - _Requirements: 2.1_

### 阶段 5：F3-1 审定表（两处硬前置）

- [ ]* 19. F3-1 槽位与口径裁决 → 声明 → 验收
  - 前置 A（F3-H5）：类别数 > 4 时降级，判据 F3-P6；前置 B（F3-H4）：拆 `f31-seed`(R7-8) / `f31-slot`(R9-10) 两 spec，
    判据 F3-P5；前置 C（B4 口径，需业务确认）：B/F/G/H/I 以模板 SUMPRODUCT 为权威，判据 F3-P7
  - TB 红线 F3-P16；变异收口 + 整册 materialize/verify + 公式管理双模式可达
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.3_
  - **进度：几何实测已落盘**（`evidence/task19-adjudication-f3-1-geometry.md`），声明未做。
  - ✅ **前置 B 已由实测确证**（拆 spec 是必需，不是可选）：R7/R8 是 6 公式列（B,E,F,G,H,I）、
    R9/R10 只 2 列（E,I），且 **`I` 列语义根本不同** —— R7/R8 的 `I7=SUMPRODUCT('明细表F3-2'!...R列)`
    是跨表取数，R9/R10 的 `I9=F9+G9+H9` 是本行横向加总。照单区声明会让空槽行的取数口径错位。
  - 🔴 **拆区方案修正**（按 D3-4 双区先例 `phase5_d3_04_analysis.py`）：两区**共享单一
    `sheet_key="f31-managed"`**，不可起两个 sheet_key（同 `managed_sheet` 映射到多个 sheet_key 会让契约
    装配产生「同 excel_name 多个 sheet 条目」冲突，D3-4 docstring 已记该教训）。区级唯一性靠
    `table_key`（`adjudication_seed_rows` / `adjudication_slot_rows`）+ `template_id` + `table_name` +
    **各区独立 uuid_col（K / L）**。全空列实测 6 个（K~P），K/L 在 `max_col=L` 内 ⇒ 无需扩列。
  - 🔴 **表头实测是两级 R5/R6**（`A5:A6` / `B5:E5`「期初数」/ `F5:J5`「期末数」三处合并），
    spec design 记单级 R6 不完整；两区共用该表头 ⇒ 都传 `header_group_row=5, header_leaf_row=6`。
  - 🔴 **A 列不可受管**（种子区）：`A7`/`A8` 是 `SUMPRODUCT` 的匹配键，改标签会让取数静默归零。
  - FC-10 不命中：百分比格式仅 2 格且都在 R15 审计说明区，数据区 R7~R10 零命中 ⇒ 无需 pct mask。
  - 阻塞（未做）：前置 C 取数口径依赖 **F1 spec 需求 7.3 的三家统一裁决**（F1 尚未出结论）；
    TB 红线 F3-P16 判据可独立先做（范式见 F5 Task 21 的 P20：AST 判定 + 剥注释，3/3 变异被抓）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门：框架层 + 兄弟 Table ref 位移（F3-7 与 F3-1 拆 spec 都依赖）+ 模板覆盖层状态" },
    { "wave": 1, "tasks": ["1", "2"], "rationale": "slice 核对与七张 sheet 几何/三元组实测，互不依赖" },
    { "wave": 2, "tasks": ["3", "4", "5", "6"], "rationale": "四组红判据并行；现状必红是后续归因依据" },
    { "wave": 3, "tasks": ["7"], "rationale": "provider 从零建，消费 Task 1 裁决与 Task 2 几何" },
    { "wave": 4, "tasks": ["8"], "rationale": "canary 薄声明（F3-5）" },
    { "wave": 5, "tasks": ["9"], "rationale": "发布链五环；第③环卡 BP-61-1 时如实 upstream_gap" },
    { "wave": 6, "tasks": ["10", "12", "17"], "rationale": "宿主接桥 / e2e 骨架 / FC-11 prefill 修复互不依赖，可并行" },
    { "wave": 7, "tasks": ["11"], "rationale": "canary 真栈验收（真库 F3-5 载荷做 roundtrip），是后续真栈的硬前置" },
    { "wave": 8, "tasks": ["13", "18"], "rationale": "F3-6 第二张验证「复用框架层零改动」；F3-3 核独立" },
    { "wave": 9, "tasks": ["14"], "rationale": "F3-7 三区，先验通兄弟 Table ref 位移" },
    { "wave": 10, "tasks": ["15"], "rationale": "F3-2 明细依赖两级表头与 FC-10 处置" },
    { "wave": 11, "tasks": ["16"], "rationale": "F3-4 依赖 F3-2（明细是其数据来源）+ 口径三方向裁决" },
    { "wave": 12, "tasks": ["19"], "rationale": "F3-1 最后：依赖 F3-2 受管（SUMPRODUCT 源）+ 槽位/口径两裁决 + 兄弟 Table ref" }
  ],
  "blocking": {
    "0": "兄弟 Table ref 位移未入 HEAD ⇒ Task 14 / Task 19 阻塞",
    "9": "published representation 供给（BP-61-1）⇒ adapter 注册与全部真栈验收阻塞",
    "16": "F3-4 口径未裁决 ⇒ H 列不得受管（模板不含天数 / 前端含 days/360）",
    "19": "类别槽位（4 vs 5）与取数口径未裁决 + 业务未确认 ⇒ F3-1 不得受管"
  }
}
```

## Notes

- 🔴 键名陷阱：F3-7 区③是 `subsequent` 不是 `post`（F1-7 用 `post`）；`F3-7-debit` / `-credit` / `-subsequent`
  （无 `-rows`）是导入导出标识不是 store 键。
- 🔴 footer 标记两张含双空格「合␠␠计」（F3-2 R31 / F3-4 R32），D6-9 已有同型先例。
- 🔴 F3-1 不用 `AdjudicationSheetSpec`（裁决 F3-H3）—— 形态由前端三元组决定，不由「它叫审定表」决定。
