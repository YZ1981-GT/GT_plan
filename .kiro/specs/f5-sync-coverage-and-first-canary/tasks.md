# Implementation Plan

## Overview

**spec**：`f5-sync-coverage-and-first-canary`　**创建**：2026-09-26　**状态**：**8/22 已实施**（2026-09-26）
**上游**：umbrella Task 48 · FC-1~FC-13（`f1-sync-coverage-and-first-canary/design.md`）· D1 引擎 ·
F2 spec（模板缺陷走覆盖层的先例 F2-26!J9）· F3 spec（FC-11 工具链根因 + FC-5 例外的裁决结构）· E1-2（预填行范式）

## 实施进度（2026-09-26）

已完成 Task 0~3 + 6 + 7 + 8 + 19（BP-7 硬前置 + canary 链路 + FC-11「从 0 到 14」）。判据：
`backend/tests/workpaper_sync/test_f5_canary_and_contract.py` **37 passed / 1 xfailed** ·
`audit-platform/frontend/src/components/workpaper/composables/__tests__/f5RowIdentityBp7.spec.ts`
**17 passed** · `backend/tests/workpaper_sync/test_f5_json_path_array_delegation.py` **22 passed**。

### ✅ FC-11 的唯一正面证明已拿到

`convert_prefill_presets()` 的 `workpaper:F5` 预设数 **0 → 14** —— F5 是唯一能用「从 0 到有」
证明 FC-11 修复生效的科目（F1/F2/F3/F4 本来非零，只能证明「不变差」）。
同时修了块内 `PREV('F5','审定表F5-1',…)` 的 sheet 名 → `营业务成本审定表F5-1`（模板真名带错字）。

### 🔴 实施中实测修正 spec 的四处

1. **Task 8 的 `footer_marker` 漏了冒号**：逐格实测 A30 = `'三、审计说明：'`（带**全角冒号**），
   而 spec 写 `"三、审计说明"`。`assert_footer_anchor_stable` 是逐字匹配 ⇒ 用 spec 的值会定位失败。
2. 🔴 **裁决 F5-H5 的事实前提半错**：框架层有**两份** json_path 实现 ——
   `json_path.py` 早已数组感知（自称「唯一允许的数组段实现真源」+ `FIXED_ARRAY_LENGTHS={"months":12}`，
   D4 月度矩阵在用），而 `phase5_row_table_sheet.py` 的同名函数只认 `Mapping`（F5-2 走的正是后者）。
   处置从「新增能力」改为**收敛到真源**（薄委托）：我曾先写了第三份实现，发现后撤回。
   `set_json_path` 原实现会把 `row["months"]`（12 元素数组）**整个替换成 `{}`** ⇒ 一格回写丢全年。
3. **F5-1 的 uuid_col 不是 J**：spec 说「max_col N、J-N 全空」，实测**J 列有值**，全空列从 **K** 起
   （12 个 K~V）⇒ 其他业务区取 **K**。
4. 🔴 **新发现模板错字**：F5-1 的 R7 标题是「主营业**业**成本：」（spec 只记了 sheet 名的
   「营业务」错字）。

### BP-7 三处修复超出 spec 原文的两条处置

① 不只在「缺 `id`」时铸，**id 命中旧下标形态时也重铸**（需求 3.3 的存量迁移判据）；
② **立即回写**（`loadRows()` 在 `minted > 0` 时 `persist()`）—— 不回写的话 store 里仍无 id，
下次载入又铸新的，身份每次都变，与下标派生一样破坏 roundtrip。`readonly` 态不写。
变异（绕过旧形态检查）精准打红 5 条。

`[ ]*` = 依赖外部供给（BP-61-1 / 模板覆盖层 / OO 真栈 / 业务确认）。

🔴 **F5 与 F1~F4 的顺序差异**：BP-7 三处修复是 slice 明令的**双向硬前置**，排在 canary **之前**（Task 6），
不是「接哪张修哪张」。

## Tasks

### 阶段 0：前置门 + 形态判定 + 红判据

- [x] 0. 前置依赖核查（`git show HEAD:`）：框架层 `RowTableSheetSpec` / **nested json 路径**（`months/0`…，F5-2 依赖）/
  `footer_carries_total_formula=False` 锚行模式（F5-7 / F5-8 两张依赖）/ `merge._protection` 格级判定 /
  **模板覆盖层交付状态**（F5-7!G31 修复依赖它）；F3 spec 的 FC-11 工具链修复状态
  - 证据 `evidence/task0-prerequisites.md`；覆盖层缺位时 Task 17 走降级分支（裁决 F5-H2 备选②）
  - _Requirements: 4.3, 5.2, 1.4, 7.2_

- [x] 1. slice 核对 + wp_code 裁决条目（**零载荷证据如实**）
  - 核 slice 中 `xlsx/gt-f5-cost-of-sales` 的 `migration_state` / 五个 null 供给位 / `template_ref="F/F5 营业成本.xlsx"` /
    `mount_count=2` / `capability_target_blocked_by == ["BP-1","BP-2","BP-3","BP-4","BP-7"]`（逐元素断言，
    🔴 **不含 BP-5**——BP-5 是 F2 专属）/ BP-7 的 `must_fix_before` 原文点名本 entry
  - 新增 F5 裁决条目：`wp_codes=["F5"]` + `matcher_domain_conflict=null` +
    🔴 `store_payload_evidence.max_payload_bytes=0` 并附原文「F5 全部键真库 0 行」（F 循环唯一完全无载荷的 entry，
    **不得伪造非零证据**）；重算 digest
  - _Requirements: 1.3_

- [x] 2. 形态判定 + 几何逐格实测 + UUID 扩列核 + FC-10 逐列取证 + 双键清单
  - 6 个受管候选区逐格复核（F5-8 R14-29 / F5-5 R11-16 / F5-3 R11-21 含三行预填标签 / F5-2 R11-22 两级表头 /
    F5-7 R11-31 的 21 个 rowKey 逐字核 `F57_ROW_DEFS` / F5-1 其他业务区 R20-25）
  - 三元组实证表（F5-2/3/5/8 = `id` 不是 `rowId`；F5-7 / F5-1 = `rowKey`；F5-6 待核）
  - 🔴 UUID 列 `Y`/`O`/`I` ≥ `max_col` ⇒ 实测扩列后 `print_area` / `page_setup` 不变（F5-P6）
  - 🔴 逐列取证模板百分比格式列（F5-2 `V,W` / F5-3 `F,K,M` / F5-5 `K,L,M`）均为公式列 ⇒ FC-10 不命中（不得沿用初判）
  - 五张表「主键 + legacy 读回退键」清单；两个零写入读键登记；F5-1 其他业务区 UUID 列实测（max_col N，J-N 全空）
  - 证据 `evidence/task2-morphology-and-geometry.md`
  - _Requirements: 2.1, 2.2, 2.5, 4.2, 5.1, 6.3, 7.3, 7.5_

- [x] 3. F5-P2 / P4 / P17 / P24 红判据（现状必红，记录红形态）
  - P2 四条子判据（`_index.json` 无 `F5C` / fallback 通过 / provisioner 用真码 `F5` / `max_payload_bytes==0` 证据核对）
  - P4 两条 legacy 键变异（`F5-2-monthly-rows → F5-2-rows`、`F5-7-cost-rollforward → F5-7-rows`）+ 受管区总数 == 6
  - P17 主营区纳入受管的双源变异；P24 两个零写入读键不在 `all_store_item_ids()`
  - _Requirements: 1.2, 1.3, 2.1, 2.2, 6.1, 7.5_

- [ ] 4. 三条红基线红判据：P9（BP-7 三处）/ P18（容量）/ P21（FC-11 预设 0→14）
  - P9：构造缺 `id` 与含下标型 id 的旧载荷，三处各一个变异（现状三处全红）
  - P18：构造 12 品种载荷，断言现状「11/12 行静默不进 F5-1」（红形态即 B3 的真实后果）
  - P21：现算 `convert_prefill_presets()['workpaper:F5']` 长度 == **0** 作为红基线锚点
  - _Requirements: 3.1, 3.2, 3.3, 4.5, 6.2, 7.2_

- [ ] 5. P22 零回归基线（10 contract golden digest 现算记录）+ P15 红形态取证
  - P15 红形态：现算模板 `F5-7!G31` 公式串 == `=G24+G56+G57-G58-G59-G60-G61`、`G56:G61` 全空、
    求值后审定数主营业务成本 != 前端 `calcF57MainBusinessCOGS` 结果（**留下模板错数的量化证据**）
  - _Requirements: 5.2, 7.4_

### 阶段 1：BP-7 三处修复（受管硬前置）

- [x] 6. 一次修完三处下标回退（触类旁通，不分 spec）
  - `useF5MonthlyDetail.ts:133` `m-${Date.now()}-${i}` / `useF5OtherCost.ts:146` `oc-migrated-${i}` /
    `useF5Comparison.ts:128` `cmp-migrated-${i}` ⇒ 统一改为缺 `id` 时铸稳定 UUID 并**立即回写**
  - 旧载荷迁移：载入后 id 不匹配 `^(m-\d+-\d+|oc-migrated-\d+|cmp-migrated-\d+)$`；插删行后同一逻辑行 id 不变（P9 转绿）
  - 🔴 grep 全仓确认无第四处同型写法（含 `-migrated-${` / `${Date.now()}-${i}` 两种模式）
  - _Requirements: 3.1, 3.2, 3.3_

### 阶段 2：canary 链路（F5-8 重大调整核查表）

- [x] 7. `phase5_f5_cost_of_sales.py` 从零建
  - `ENTRY_ID="xlsx/gt-f5-cost-of-sales"` / `ADAPTER_ID="f5.cost_of_sales_detail"` / `WP_CODES={"F5C"}`（幻影码）/
    `TEMPLATE_RELATIVE_PATH="F/F5 营业成本.xlsx"` /
    `TEMPLATE_SHA256="417e5ae7453528725f3ae5eb06f70d36269b089cd73a00884c835f4586267cb7"`（本 spec 实测，187,721 B）
  - `assert_entry_selectable(*, resolution, manifest=None)`（D3 同签名、无关闭开关、真 manifest 真调）+
    `build_matcher()`（带 `document_type="xlsx"`）+ `build_registration` 照 `phase5_d3_prepaid_receipts.py:830` +
    **真构造判据**；6 个灰度开关（除 F5-8 外默认 False）+ `all_store_item_ids` + 单数 `STORE_ITEM_ID="F5-8-rows"` +
    `instrumentation_specs()` 复数 + `build_contract_payload` + `attach_pilot_adapters`
  - _Requirements: 1.2, 1.3_

- [x] 8. `phase5_f5_08_major_adjustment.py` canary 薄声明（无 def/class）
  - `F5-8-rows` / 行身份 **`id`** / 两级表头 R12/R13 / 数据 R14-29 / **无 footer 合计** ⇒
    `footer_row=30` + `footer_marker="三、审计说明"` + `footer_carries_total_formula=False` / UUID **I** /
    `formula_columns=()`（数据区零公式，7 个公式全在表头页眉区）
  - 字段键逐字取 `useF5MajorAdjustment` 行接口（A-H 八列，H「理由是否充分」）
  - _Requirements: 1.1, 1.4, 2.1_

- [ ]* 9. 契约发布链五环 + 登记点
  - 生成器 `generate_phase5_f5_contract.py --apply` → `f5.cost_of_sales_detail.json` →
    `assert_contract_file_matches_source` → approved bundle → published representation → entry_state → `register_from_manifest()`
  - 登记点：`DELIVERED_PER_ENTRY_CONTRACTS` + `_ALLOWED_PROVIDER_MODULES` + `store_item_registry` plan +
    `check_sync_provider_golden_digest.PROVIDERS` + overlay + 重生 manifest（P1 / P22）
  - 🔴 第③环卡 BP-61-1 时如实 `upstream_gap`
  - _Requirements: 1.5, 1.6, 7.4_

- [x] 10. 宿主接桥（**保 `isHtmlSheet` 门控 + 保两条监听**）
  - `GtF5CostOfSales.vue` 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`；
    `F5_SHEET_KEY_BY_CODE` + `isF5SyncManagedSheet` 从 provider 派生
  - 🔴 F 循环唯一带 `isHtmlSheet &&` 前置门控的宿主（L30）⇒ 接桥 SHALL 保持该语义（未迁移 sheet 走 L133 兜底分支）
  - 🔴 严格保留 `f5:save-items` 与 `substantive:adjudicated` 两条 window 监听（F5-7 校验区消费 6401 审定数，P7）
  - _Requirements: 1.7, 7.6_
  - **已完成**：受管分支 `v-if="isF5SyncManagedSheet && dualMode.currentMode.value === 'onlyoffice'"`，
    `isF5SyncManagedSheet = isHtmlSheet.value && currentSheet.value in F5_SHEET_KEY_BY_CODE`（与门控取交集，
    不绕过）；legacy 分支降级为 `v-else-if="isHtmlSheet && ..."`；两条 window 监听未动。
  - 🔴 **拒绝照抄 F1 宿主**（`GtF1Prepayment.vue` 接桥有两处缺陷，已移交 F1 spec）：
    ① L419 调用**未定义**的 `flushPendingSave()`（`useF1FormData` 不导出、宿主内也无定义）⇒ `ReferenceError`；
    ② `WorkpaperSyncEditorHost` 必填 props 是 `descriptor` + `bridge`，F1 传了 `wp-id`/`project-id`/`readonly`
    三个**不存在的 prop** 却**漏掉 `descriptor`** ⇒ 编辑器永不创建。本次照 E1 正确范式
    （`syncOoDescriptor = computed(() => syncBridge.descriptor.value)` + 只传 `descriptor`/`bridge`）。
  - 🔴 **顺带修 `useF5CosSalFormData` 两处真缺陷**（接桥需要 flush，实测发现）：
    ① `onScopeDispose` 原来只 `clearTimeout` **不保存** ⇒ 卸载/切 sheet 时 debounce 窗口内的编辑被静默丢弃；
    ② `saveImmediate` 不撤销同 item 的 debounce 计时器，而该计时器闭包捕获的是**旧** `updated`
    ⇒ 2s 后旧值覆盖新值。两处按 D3/F3/F4 三家同构口径修（`_pendingItems` + `_flushPending`）。
  - 类型核查：`npx vue-tsc --noEmit -p tsconfig._f345-canary.json` 三宿主 + 三 composable **零错误**
    （全项目 vue-tsc OOM，故照 `tsconfig.pac-t21.json` 先例建窄 include 配置）。

- [x] 11. seed 脚本 + 批量 e2e 骨架（🔴 零载荷 entry 的特殊前置）
  - `backend/scripts/e2e/seed_f5_publish_e2e.py`：照 D4/E1 lane 的 seed 范式，幂等造 F5-8 两行最小载荷（`--dry-run` 可离线验）
  - `e2e/fixtures/f5-l2-cases.json` + `e2e/f5-l2-oo-to-html-all.spec.ts`；全部真栈用例前置 seed
  - P8 守护：未 seed 时验收脚本 SHALL 显式失败（不得因空表往返判 `store_mirrored`）
  - _Requirements: 1.8_
  - **已完成**：`backend/scripts/e2e/seed_f345_canary_rows.py`（三 spec 共用，`--entry f3|f4|f5|f5-1|all`）
    + `e2e/fixtures/f5-l2-cases.json` + `e2e/f5-l2-oo-to-html-all.spec.ts`（**6 tests**：2 条 P8 前置 +
    1 条双区行身份 + 1 条主营区不可受管 + 2 条 canary）。`--list` 实测 6 tests 正常加载。
  - 🔴 **不建 `seed_f5_publish_e2e.py` 而三 spec 合一**：F3/F4/F5 要造的东西逐字同构，分三份会造三处
    重复实现，而 seed 的风险点（覆盖真实数据 / 行身份不稳 / 非幂等）需要一次修对三处生效。
  - **F5 确认是零载荷 entry**（实测全库无任何 `F5-*` 载荷）⇒ seed 两个 key：
    `F5-8-rows` 1 行 236 B（行身份 `id`）、`F5-1-adj-other-rows` 1 行 244 B（行身份 **`rowKey`**），
    目标 wp `b751f499-…`（项目 `0ec33ac9-…`）。**两区行身份键不同**，fixture 与判据都逐条声明，
    e2e 有一条专门断言「两键不同且各自齐备」——照抄任一张都会让另一张投影 fail-closed。
  - **P8 守护落地**：前置用例断言「载荷非空 + 每行带 `_seed` 标记 + 行身份齐备」，且**不因 adapter
    未注册而跳过** ⇒ 未 seed 时显式失败，不会因空表往返判 `store_mirrored`。
  - 🔴 **额外加一条 e2e 断言**：主营区 `F5-1-adj-main-rows` 不得出现 seed 载荷（该区 A~I 九列全是
    模板公式、零可编辑格 ⇒ 受管它等于登记只读投影）。
  - seed 安全性实测（全部通过）：`--dry-run` 离线打印 · `--check` 只读核查 · 幂等（二次跑
    `was_seed=true`）· 拒绝覆盖非 seed 载荷（F3 两道安全线均触发）· `--purge` 只删带标记行
    （F3 真实载荷 `kept_not_seed` 保住）· 真库 SQL 复核 4 条记录的 bytes/rows/seed_tag。
  - 🔴 `_seed` 标记的边界已写进脚本常量注释：带标记的载荷**不构成业务载荷证据**，
    裁决文件 `max_payload_bytes=0`（F5）记的是真实业务载荷、且其 note 已预告「验收前必须先 seed」
    ⇒ seed 后真库非 0 是预期行为，不是证据过时；按真库行数回填证据的脚本须先剔除带标记的行。
  - 未做（如实）：真栈三谓词卡 BP-61-1（canary `pending_adapter` skip）；前置断言待后端可用
    （实测 9980 被 `start-dev.bat` 的 reloader 占用但 HTTP 30s 无响应，worker CPU 101.9s，
    疑似启动卡死；是他人进程故未清理）。

- [ ]* 12. canary 验收：seed → 三谓词 → DB 证据
  - _Requirements: 1.8_

### 阶段 3：F5-5 比较分析 + F5-3 其他业务成本

- [ ] 13. `phase5_f5_05_comparison.py`：`F5-5-comparison-rows` / `id` / 两级表头 R9/R10 / R11-16 / footer R17「合计」/
  UUID **P** / `formula_columns=("D","G","H","I","J","K","L","M")`
  - 🔴 除零容错（P11）：`calcF5ComparisonChangeRate` 上期为 0 返 `'N/A'`（`useF5Comparison.ts:69-73`）⇒
    `K/L/M` 为 `mode=formula`；判据三条（extract 不抛 / 异常 `type_normalization_failure` / store 无 `#DIV/0!`）
  - P10 等价性 PBT（`D=B*C` / `G=E*F` / `H,I,J` 差额）；依赖 Task 6 的 BP-7 修复
  - _Requirements: 4.1, 4.4_

- [ ] 14. `phase5_f5_03_other_cost.py`：`F5-3-other-cost-rows` / `id` / 两级表头 R9/R10 / R11-21 / footer R22「合计」/
  UUID **O** / `formula_columns=("E","F","J","K","L","M")`
  - 🔴 R11-13 三行模板预填标签（出租固定资产 / 出租无形资产 / 出租包装物和商品）登记为**预填行**
    （照 E1-2 `PREFILLED_CURRENCY_ROWS` 范式），空载荷 materialize 后仍在（P12）
  - P10 等价性 PBT（`E=B+C+D` / `J=G+H+I` / `L=E-J`）；依赖 Task 6
  - _Requirements: 4.2_

### 阶段 4：F5-2 月度明细（容量裁决先行）

- [ ] 15. F5-2 容量裁决落地（裁决 F5-H4）
  - 裁决证据：模板 F5-1 主营区 **10 槽**（R8-17，逐行引 `F5-2!A11`~`A20`、小计 `R18=SUM(B8:B17)`）vs
    F5-2 **12 行**（R11-22、合计 `R23=SUM(N11:N22)`）vs 前端任意行数（`addRow`/`removeRow`）
  - 落地：品种数 ≤10 受管、>10 **整表降级 legacy + 中文提示**（须点明「超出审定表主营区槽位」「F5-1 小计将漏算」）
  - P18 转绿三条（受管判定为关 / legacy 读到全 12 行 / 提示文案）；🔴 不得为适配而改模板槽位或 SUM 区间
  - _Requirements: 4.5, 6.2_

- [ ] 16. `phase5_f5_02_monthly_detail.py`：`F5-2-monthly-rows` / `id` / 两级表头 R9/R10 / R11-22（12 行）/
  footer R23「合计」/ UUID **Y** / `formula_columns=("N","Q","U","V","W")`
  - 🔴 12 个月度列 B-M 是 editable，`json_key` 用 **nested 路径** `months/0`…`months/11`（裁决 F5-H5），
    不得展平成 `month1`…`month12`；P13 判据（改一格只变对应下标元素，其余 11 个不变）
  - P10 等价性 PBT（`N=SUM(B:M)` / `Q=N+O+P` / `U=R+S+T`）；依赖 Task 6 + Task 15
  - _Requirements: 4.3, 4.5_

### 阶段 5：F5-7 成本倒轧（模板缺陷修复）

- [ ]* 17. F5-7!G31 模板缺陷处置（裁决 F5-H2，FC-5 第二个例外）
  - 默认①：经**模板覆盖层**把 `G31` 修为 `=G24+G25+G26-G27-G28-G29-G30`（与 E/F/H 三列同型，形态自证）
  - 备选②（覆盖层缺位）：`G` 列整列 HTML-only + UI 中文提示「审定数列由系统计算，模板公式存在已知缺陷」
  - P15 转绿：修复后 `G31` 求值 == 前端 `calcF57MainBusinessCOGS` 审定口径结果；🔴 **不改
    `backend/wp_templates/` 字节**（运行时只读 + sha 冻结），不改前端去对齐错误模板
  - _Requirements: 5.2_

- [ ] 18. `phase5_f5_07_cost_rollforward.py`：`F5-7-cost-rollforward`（🔴 **不带 `-rows` 后缀**）/ `rowKey` /
  表头 R10 / 21 固定行 R11-31 / **无 footer 合计**（`footer_row=32` + `footer_marker="三、审计说明"` +
  `footer_carries_total_formula=False`）/ UUID **I**
  - 21 个 rowKey 逐字取 `F57_ROW_DEFS`（`openingMaterial` … `mainBusinessCOGS`，顺序敏感，P14）
  - E（未审）/ F（调整）/ H（上期）editable、G（审定数）formula；🔴 四个 `rowType='formula'` 派生行
    （`directMaterialCost` / `productProductionCost` / `finishedGoodsCost` / `mainBusinessCOGS`）的 E/F/H 也是
    `mode=formula`，不得 editable（P14 变异）
  - 🔴 `F5-7-adjudicated-cogs`（宿主从 `substantive:adjudicated` 注入的 6401 审定数）**不进** `field_specs`（P16）
  - _Requirements: 5.1, 5.3, 5.4_

### 阶段 6：FC-11 数据侧 + F5-1 其他业务区 + 核与收口

- [x] 19. FC-11 数据侧修复（F5 是「从 0 到有」的唯一证明科目）
  - 块 `[226]`（`营业务成本审定表F5-1`）的 14 条 `items` 迁 `cells`；修块内
    `PREV('F5','审定表F5-1','审定数')` 的 sheet 名为 **`营业务成本审定表F5-1`**（模板真名，带「营业务」错字）
  - P21 转绿：`convert_prefill_presets()['workpaper:F5']` 从 **0** 变 **14**
  - 🔴 依赖 F3 spec 已修工具链（`_ensure_cells` 只写 `cells`），否则再跑
    `fix_f_cycle_prefill_presets.py` 会把 `items` 造回来
  - _Requirements: 7.2_

- [ ] 20. F5-4 / F5-6 可行性核（**不改生产代码**）
  - F5-4：照 FC-6 默认 `single_html`（`F5TabAdjustment.vue:286 useAdjustmentCentralSync` ⇒ hub）
  - F5-6：244 公式 / 分厂×产品×12 月三块（总计 R21/R34/R47）+ `F5-6-quantity-recon-plants` 维度键 ⇒
    只做形态核、结论为「后置另立 spec」；证据 `evidence/task20-f54-f56-feasibility.json`
  - P23 部分：F5-4 / F5-6 / F5-1 主营区在 slice 中显式登记为 legacy 假双向（不静默遗漏）
  - _Requirements: 6.5, 6.6, 7.6_

- [x]* 21. F5-1 其他业务区声明 + TB 红线 + 收口
  - `phase5_f5_01_adjudication.py`：仅 `f51-other` 一个 spec ——`F5-1-adj-other-rows` / `rowKey` / 表头 R6 /
    数据 R20-25 / footer R26「小计」/ `formula_columns=("E","I")`（B/C/D/F/G/H 手填）/ UUID 列取 Task 2 实测值
  - 🔴 主营区 `F5-1-adj-main-rows` **不进** `all_store_item_ids()`（裁决 F5-H3，P17 转绿）
  - TB 红线 P20：sync 路径对 `trial_balance` 写次数为 **0**；`publishToTb`（科目 6401、**发生额口径**）仍是唯一入口；
    变异「sync 回写里调 publishToTb」必红
  - 收口：P5（legacy 键不双写）+ P19（其他业务区列集 + FC-10 逐列不命中）+ P23（公式管理入口两模式可达）+
    P22（10 golden digest 不变）；整册 materialize/verify + 全部变异复跑
  - _Requirements: 6.1, 6.3, 6.4, 7.1, 7.3, 7.4, 7.6_
  - **已完成**：`phase5_f5_01_adjudication.py` + `_INCLUDE_F501_OTHER=True` + 契约重算
    （digest `d91814dc…` → `acf0720e65a6331c451f210ea7dc026eb3292251b18f4e42f5b127c9d314db14`，过 `parse_contract`）；
    判据 34 条（37→71 passed）；`check_sheet_specs_fully_registered` 19→20 adapter。
  - 变异验证 **6/6 被抓**：`rowKey`→`id` / uuid_col K→J / footer 标志 True→False /
    `formula_columns` (E,I)→() / 末行 25→17 / store_item_id 指向主营区键。
  - TB 红线 P20 变异 **3/3 被抓**：sheet spec 出现 `trial_balance` 常量 / 出现 `publish-to-tb` 端点常量 /
    provider sync 路径调 `publish_to_tb()`。判定走 **AST**（剔除 docstring）+ 前端查旧端点时**先剥注释**
    —— 两处都因"注释里正当写着历史变更说明"，文本匹配会让判据自己假红（第一版即踩，已修）。
  - 🔴 **实测修正 spec 四处**（证据 `evidence/task21-adjudication-f5-1-geometry.md`）：
    ① 主营区不是"选择 HTML-only"而是**不可受管** —— R8~R17 的 **A~I 九列全是公式**（含 A 列项目名
    `='主营业务成本月度明细表F5-2'!A11`），零可编辑格，OO 侧写入必被覆盖；判据逐格断言 10 行 × 9 列。
    ② uuid_col 取 **K** 不是 J：spec 记「J~N 全空」有误，`J` 有 2 格非空（`J5:J6` 合并的索引表头 + `J3` 公式）。
    ③ 表头是**两级 R5/R6**（`B5:E5`「本期数」/`F5:I5` 两个组表头 + `A5:A6`/`J5:J6`），不是 spec 写的单级 R6；
    区② 自己**没有**列表头行（R19 只有 A 列文字），复用表级表头 ⇒ anchor `A5`（D3-4 双区先例允许跨度）。
    ④ sheet_key 用 `f51-managed` 而非 spec 写的 `f51-other`：按 D3-4 先例，同 `managed_sheet` 的多区必须
    **共享单一 sheet_key**（映射到多个会让契约装配产生「同 excel_name 多个 sheet 条目」冲突），
    区级唯一性靠 `table_key`/`template_id`/`table_name`/`uuid_col`。
  - 模板债登记（不改字节）：`A7='主营业业成本：'` 错字（第 2 处）。
  - 未做（如实）：P22 的 10 golden digest 现算基线（属 Task 5，未开）；整册 materialize/verify 真栈
    （卡 BP-61-1：slice 五个供给位 `published_representation` 等全 null）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门：nested json 路径（F5-2）/ 锚行 footer（F5-7+F5-8 两张）/ 模板覆盖层（G31）三项共同依赖" },
    { "wave": 1, "tasks": ["1", "2"], "rationale": "slice + 零载荷证据 与 6 区几何/三元组/UUID 扩列/FC-10 逐列取证，互不依赖" },
    { "wave": 2, "tasks": ["3", "4", "5"], "rationale": "三组红判据并行；P15 须留下模板错数的量化证据" },
    { "wave": 3, "tasks": ["6"], "rationale": "🔴 BP-7 三处修复是 slice 明令的双向硬前置，排在 canary 之前" },
    { "wave": 4, "tasks": ["7"], "rationale": "provider 从零建" },
    { "wave": 5, "tasks": ["8"], "rationale": "canary 薄声明（F5-8：数据区零公式 + 无 footer 锚行首验）" },
    { "wave": 6, "tasks": ["9"], "rationale": "发布链五环；第③环卡 BP-61-1 时如实 upstream_gap" },
    { "wave": 7, "tasks": ["10", "11", "19"], "rationale": "宿主接桥（保门控+保两监听）/ seed+e2e 骨架 / FC-11 数据侧互不依赖" },
    { "wave": 8, "tasks": ["12"], "rationale": "canary 真栈验收（先 seed），是后续真栈的硬前置" },
    { "wave": 9, "tasks": ["13", "14", "20"], "rationale": "F5-5（除零）与 F5-3（预填行）第二三张验证复用；F5-4/F5-6 核独立" },
    { "wave": 10, "tasks": ["15"], "rationale": "容量裁决必须在 F5-2 声明之前落地，否则受管即静默漏算" },
    { "wave": 11, "tasks": ["16"], "rationale": "F5-2 月度矩阵（nested months 路径）" },
    { "wave": 12, "tasks": ["17"], "rationale": "G31 覆盖层修复；覆盖层缺位则走备选②降级" },
    { "wave": 13, "tasks": ["18"], "rationale": "F5-7 在 G31 处置定案后声明（21 固定 rowKey + 派生行不 editable）" },
    { "wave": 14, "tasks": ["21"], "rationale": "F5-1 最后：依赖主营区 HTML-only 裁决 + 容量裁决 + TB 红线 + 全量收口" }
  ],
  "blocking": {
    "0": "模板覆盖层未交付 ⇒ Task 17 只能走备选②（G 列 HTML-only），Task 18 的 G 列不受管",
    "6": "BP-7 三处未修 ⇒ F5-2 / F5-3 / F5-5 三张受管全部阻塞（slice BP-7 must_fix_before 明令：标 bidirectional 与发布 contract 之前）",
    "9": "published representation 供给（BP-61-1）⇒ adapter 注册与全部真栈验收阻塞",
    "11": "seed 脚本未交付 ⇒ 零载荷 entry 的验收是假绿，Task 12 不得判通过",
    "15": "容量裁决未落地 ⇒ Task 16 受管后品种数 11~12 时 F5-1 小计静默漏算",
    "19": "F3 spec 的 FC-11 工具链修复未完成 ⇒ 迁移后会被脚本改回 items"
  }
}
```

## Notes

- 🔴 **F5 是 F 循环红基线最多的 entry（7 条）**，其中三条是受管硬前置：BP-7 三处（B4，Task 6）、
  模板 `G31` 漏算 7 项（B2，Task 17）、容量不一致（B3，Task 15）。任务顺序由这三条倒推，与 F1~F4 不同。
- 🔴 **F5-7!G31 是 FC-5 的第二个例外**（第一个是 F3-4 应计利息）：模板引越界空区 `G56:G61` 求值恒 0 ⇒
  审定数列的主营业务成本漏掉 6 项，是**模板 bug 不是口径分歧**。与 F2-26!J9 同源，共同确立 F 循环规则：
  模板缺陷走覆盖层，FC-5 只适用于「两边都对、口径不同」的情形。
- 🔴 **F5 是唯一能用「从 0 到有」证明 FC-11 修复生效的科目**（`workpaper:F5` 预设数 0 → 14）；
  F1/F2/F3/F4 的预设本来就非零，只能证明「不变差」。
- 🔴 **F5 真库零载荷**（F 循环唯一）⇒ 验收必须先 seed，否则空表往返会被判 `store_mirrored` 假绿（P8 专门守护）。
- 🔴 F5-2/3/5/8 的行身份字段是 **`id`** 不是 `rowId`（与 D 类惯例相反）；F5-7 的 store 键**不带 `-rows` 后缀**
  （按 `-rows` 模式 grep 会漏）。两处都是按值实测所得，声明时逐字照抄。
- 🔴 F5 与 F4 同属「FC-10 不命中」，但该结论须有 Task 2 的逐列证据（B6 初判不得直接采信）。
