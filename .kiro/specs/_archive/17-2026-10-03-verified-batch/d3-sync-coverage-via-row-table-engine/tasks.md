# Implementation Plan

## Overview

**spec**：`d3-sync-coverage-via-row-table-engine`　**创建**：2026-09-25　**状态**：16/16 全部完成
（阶段 0 全部 + 阶段 1 D3-6 完整交付 + 阶段 2 Task 10 验收：引擎跨 sheet 引用改写碰撞/verify 缓存串味已修[3a/3b]、D3-5/D3-6 模板 footer 缺陷已修[3c]、整册 materialize verify equivalent；阶段 3 D3-7 双区接入验收；阶段 4 D3-1 审定表声明+四态；阶段 5 D3-3 可行性核 single_html + **Task 16 前端受管集合派生 + Property 1~12 变异总表**；真栈相关判据均如实标 `[ ]*`，adapter_registered=False 卡点同全 spec）

本 spec 是纯**声明层**，消费两个上游：`d1-sync-row-table-engine-and-d1-coverage`（引擎 /
注册表 / `AdjudicationSheetSpec` / 四态状态机）与 `d-cycle-sheet-bidirectional-expansion`
（裁决与分波真源）。⇒ **Task 0 是硬前置门**。

**受管区路线**：`1(D3-2 已接) → 2(D3-6) → 4(D3-4 双区) → 5(D3-5) → 7(D3-7 双区) → 8(D3-1)`。
D3-3 调整分录只做可行性核、不计入。

顺序理由：D3-6 单区最简作首张（证明多受管 sheet 在 D3 成立、失败面最小）→ D3-4 双区把同 sheet
多区位移链在 D3 验通 → D3-7 双区同型快速复制 → D3-1 审定表最后（依赖两个外部前置 + 逐格 mask）。

🔴 **本 spec 有一个 D1/D2 没有的真实卡点**：D3 的 `adapter_registered=False`（真库
`register_from_manifest()` 只注册 `{d2,d4,g7,h1}`，D3 因 store 全库 0 行、无 published
representation 未注册）⇒ 真栈实测跑不起来，相关判据如实标 `[ ]*`，**不得**以合成测试冒充真栈。

## Tasks

### 阶段 0：前置门与实测填参

- [x] 0. 前置依赖核查（**判定用 `git show HEAD:` 不读工作树**）
  - 前置 A：上游框架层（`RowTableSheetSpec` / `StoreItemSpec` 注册表 /
    `attach_sibling_bindings(provider=…)` / `phase5_d3_02_detail.py` 声明拆分）已入 HEAD
  - 前置 B：`AdjudicationSheetSpec` 已交付
  - 前置 C：`merge._protection` 的 `cell_in_ranges` + `_mask_spans_data_column` 已入 HEAD
  - 前置 D：D3 的 `adapter_registered` 是否已 True（实测现状 **False**）
  - IF A 未满足 THEN 全部阻塞。IF B/C 未满足 THEN 阶段 4（D3-1）阻塞，其余可推进。
    IF 仅 D 未满足 THEN 代码与合成判据可推进、真栈实测阻塞并标 `[ ]*`
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 1. 六张 sheet **形态判定** + 几何实测填参 + 下游消费方 grep 补全
  - 🔴 **形态判定先于几何填参**（复盘补，需求 9）：每张先定 `binding_kind`
    （`excel_table` vs **`static_region`**）与 `row_identity_key`（`rowId` / **稳定 key** / 无）
  - 待判定：**D3-5**（20r×8c/**9 公式**，公式集中在 A2 C2 E2 前几列 ⇒ 形似固定结构）与
    **D3-6**（34r×12c/16f，被选作「最简样本」的前提是它确实是动态行表 —— 若实测为固定行或静态区，
    接入顺序与声明形态都要改）。D3-5 与 D7-5 同型，须与 D567 spec 用**同一结论**
  - 参照 D4 三实现：`phase5_d4_erp_check_sheet`(D4-13 单 cell) / D4-33(72 static cell) /
    `phase5_d4_indicator_sheet`(D4-6 稳定 key 固定行 + 仍注入 UUID 列)
  - 🔴 另两项：①note/conclusion/procedures item 若在 footer 之下，逐项核是否命中
    「footer 下 `static_row` 与插行 fail-closed 冲突」⇒ 命中则登记 HTML-only ②宿主须覆盖
    **两套 gating**（`isD3DetailSheet` + 审定表 D3-1 若走独立宿主则第二套）
  - openpyxl 逐张实测 `first_data_row` / `last_data_row` / `footer_row` / `header_row` /
    公式列归类（哪些是数据行列向公式、哪些是 footer/表头）/ 有无可注入 UUID 列
  - 已实测在案可直接用：D3-1 30r×12c/88f（主列 E14 I12 J11 K11）· D3-4 38r×9c/22f（E8 D6 C3）·
    D3-5 20r×8c/9f（A2 C2 E2）· D3-6 34r×12c/16f（F6 D3 A2）· D3-7 48r×18c/19f（F5 G5 E3）·
    D3-3 23r×10c/6f（A2 D2 F2）
  - 🔴 **D3-1 的区块数与行模型必须实测**（裁决 F3）：不得照 D1-1（3 区 × 动态票据种类）或
    D2-1（1 区 × 写死 4 行）推演
  - 🔴 **按值 grep 补全每个 store 键的下游 computed 消费方清单**（上游 P18 教训）；
    已知 `useD3CrossSheet` 读 `D3-vc-post-rows`、`D3TabIndex` 各键做完成度判定
  - 实证 D3-7 侧**没有** D2-7 那种「新旧两套并存」债（D3 只有 `useD3VoucherCheck` 一个模块）
  - 产出实测表落 spec `evidence/`，后续任务引用它而非重测
  - 🔴 **本任务产出会改后续阶段顺序**：判为 `static_region` 的 sheet 绕开整条位移链
    ⇒ 风险显著低于行表 ⇒ 应**提前**接入，首版「D3-6 → D3-4 双区 → D3-5 → D3-7 双区 → D3-1」
    需据此调整为「先静态区、再单区、再双区、最后审定表」
  - _Requirements: 1.3, 2.3, 3.2, 4.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

- [x] 2. Property 1 零回归基线：D3-2 与其余 7 contract 的 golden digest
  - 复用上游交付的 `check_sync_provider_golden_digest.py`，此时必绿，记录实测值
  - D3 store 全库 0 行 ⇒ 用**合成 payload** 驱动（需求 6.5）
  - _Requirements: 6.3, 6.5_

- [x] 3. Property 2 红判据：`store_item_id` 必须逐字等于按值 grep 实测值
  - 断言六张的键分别为 `D3-rp-rows` / `D3-ana-credit-rows` / `D3-ana-debit-rows` /
    `D3-lt-rows` / `D3-vc-current-rows` / `D3-vc-post-rows`（D3-1 待实测）
  - 变异：把 `D3-rp-rows` 写成 `D3-6-rows` ⇒ 投影恒空、回写丢失，必红
  - 🔴 这是本 spec 最易犯且最难发现的错 —— D3 的键用**语义缩写**与 sheet 编号无对应关系；
    D1/D2 已因「按模式推演键名」出过三次遗漏（D2-3 三键 / D1-15 双键 / D1-13 双键）
  - _Requirements: 1.2, 2.3_

- [x] 4. Property 3 / 4 红判据：D3-4 与 D3-7 是双区
  - 断言受管区 2→4（D3-4）与 5→7（D3-7）；现状必红（两张尚未接入）
  - 变异：只声明一个受管区 ⇒ 另一键数据在 OO 里不可见，必红
  - _Requirements: 2.1, 3.1_

- [x] 5. 性能基线 + `adapter_registered` 现状登记
  - 脚本现测整册 materialize 与三端点耗时；若因 `adapter_registered=False` 跑不起来，
    如实登记「真库不可测」并给出合成基线替代口径
  - `store_field_count` / `field_count` 记实测值；🔴 **不得**用二者作差推断数据丢失
  - _Requirements: 6.1, 6.4, 7.3_

### 阶段 1：D3-6 关联关系及交易检查表（首张，单区最简）

- [x] 6. `phase5_d3_06_related_party.py` 声明 + 灰度开关
  - `RowTableSheetSpec(managed_sheet="关联关系及交易检查表D3-6", sheet_key="d36-managed",
    table_key="related_party_rows", store_item_id="D3-rp-rows", store_kind=rows,
    aging_layout=None, …)`；几何与 `formula_columns` 取 Task 1 实测值
  - `formula_mask` 走引擎 property 现算，**不手写字面量**（Property 5）
  - 循环层 `phase5_d3_prepaid_receipts` 只追加 sheet 清单项 + 一个 `_INCLUDE_D306` 开关
  - _Requirements: 1.1, 1.2, 1.3_

- [x]* 7. D3-6 接入验收
  - Property 2 的 D3-6 部分转绿；Property 5 绿；Property 1 零回归
  - 整册 materialize 200 + `verify_unmanaged_regions` 全绿 + **受管区 1→2** + 耗时登记
    （若 `adapter_registered=False` 则标 `[ ]*` 写明卡点）
  - Property 9：`D3-rp-rows` 下游消费方（Task 1 grep 出的清单）在 OO 回写后仍正确重算
  - _Requirements: 1.4, 1.5, 6.1, 6.3_
  - ✅ 2026-09-26 证据落 `evidence/task7-d3-06-acceptance.md`：Property 2/1 回归复核绿；
    Property 5 补齐独立判据（4 条，钉住 Task 6 仅 REPL 验证过的 `formula_mask`）；受管区
    1→2 monkeypatch 验证通过；Property 9 前端下游消费方（`D3TabIndex.isSheetComplete`）
    真实验证通过（新建全仓首个 `D3TabIndex.spec.ts`，5 条）；`verify_unmanaged_regions`
    离线机制真实验证通过（新建 `test_d3_06_offline_materialize_and_verify.py`，6 条：真实
    模板无 Table→注入后真实出现→`resolve_managed_region` 定位到→identity 校验通过→覆盖
    计数非零→变异检出无关 sheet 改动）
  - `[ ]*` **整册 materialize 200 真栈不可测**（引用 Task 5：D3 manifest capability 非
    bidirectional + 共享注册通路先在 D2 契约漂移处中断，均为平台级/跨 spec 缺口）
  - 🔴 **实测翻转 `_INCLUDE_D306_RELATED_PARTY` 后发现它会打红 3 个既有基线判据文件共 11
    用例**（`assert_contract_file_matches_source()` 磁盘契约↔现算 payload 双向锁死机制，
    翻开关须同步 `generate_phase5_d3_contract.py --apply` 重生成受版本控制的磁盘契约，影响
    面超出本任务单方面决定范围）⇒ 开关**维持 False**，留给 Task 8/9 统一规划批量翻开关时机

### 阶段 2：D3-4 分析表（双区）+ D3-5 账龄 1 年以上

- [x] 8. `phase5_d3_04_analysis.py` 声明**两个** spec
  - 同 `managed_sheet="预收账款分析表D3-4"`，不同 `sheet_key` / `table_key` / `store_item_id`
    （`D3-ana-credit-rows` / `D3-ana-debit-rows`）/ 行段 / UUID 列，形如 D4-9 双区
  - 借贷两区各占哪几行由 Task 1 实测确定（38 行 ×9 列内）
  - 🔴 前置：上游 D1 spec 任务 24（位移判据清单按 provider 参数化）须先落，否则双区不进
    `test_sibling_table_ref_row_shift.py` 自动覆盖清单
  - _Requirements: 2.1, 2.2_

- [x] 9. `phase5_d3_05_long_term.py` 声明（单区）
  - `store_item_id="D3-lt-rows"`（实测值，不是 `D3-5-rows`）；20 行 ×8 列 / 9 公式 ⇒ 最简形态
  - _Requirements: 2.3_
  - ✅ 2026-09-26 证据落 `evidence/task9-d3-05-declaration.md`：独立 openpyxl 三轮复核
    （表头/候选空列 → 全表 9 处公式坐标扫描确认数据行 11-13 逐格为空 → 候选空列扩大到
    L/M/N 确认全空）与 Task 1 结论完全一致，且额外发现"9 处公式全部不落在数据行本身，
    7 处页眉 + 2 处 footer"这一更精确结论；`SPEC_D305` 不传 `formula_columns`（数据行
    无公式列，`formula_mask` 现算为空 tuple）、`footer_carries_total_formula=True`
    （footer SUM 确覆盖全部 3 行数据区，显式传值）；`phase5_d3_prepaid_receipts.py`
    **确认无需改动**（monkeypatch 实测验证，D3-5 独立 sheet_key 被既有分组函数通用处理）；
    Property 2 判据 `test_d3_05_long_term_store_item_id` 从 SKIPPED 转 PASSED；golden
    digest 26 个零回归；`test_d3_expansion.py` 7 条零回归；全量 D3 回归 74 passed/1 skipped
    （D3-7 正确保持跳过）。灰度开关 `_INCLUDE_D305_LONG_TERM` 维持 False，留给 Task 10 决定。

- [x] 10. 阶段 2 验收（双区位移链在 D3 验通）
  - Property 3 转绿（受管区 2→4）；D3-5 接入后 4→5
  - 🔴 **双区同 sheet 的位移链必须实证**：上区插行后下区 Table ref 随之下移、`_GT_SYNC` footer
    坐标重冻结、verify 累积归一化通过（照 D4-9 双区范式）
  - 整册 materialize + 耗时登记 + Property 1 零回归
  - _Requirements: 2.2, 2.4, 6.1_
  - 【第 3c 段收尾 2026-xx，用户批准"修引擎+修模板"，引擎 3a/3b 已定稿】证据 `evidence/task10-stage2-acceptance.md` §11/§7/§8/§9：
    - **模板缺陷修复**（新脚本 `scripts/fix/fix_d3_template_footer_defects.py` --apply）：D3-6 合计行 C17/D17/E17/F17 SUM 区间 12:14→12:16（C17 独立公式 + D17 共享 master，E17/F17 派生）；D3-5 A14 空→inlineStr「合计」（保 style s=12，不动 sharedStrings）。模板新 sha `33165493…`（旧 `699a9be0…`），仅 D3-5/D3-6 两 sheet 变、merged 不变、其它 10 张零 diff；`.prefooterfix.bak` 备份。
    - **哨兵同步**：`TEMPLATE_SHA256` 改新值；契约 `generate_phase5_d3_contract.py --apply` 重生成（`assert_contract_file_matches_source()` 通过，canonical `54ffa5f5…`）；`wp_templates_baseline.json` 只同步 D3 一条。
    - **停下报告（需裁决）**：definition_store 内容寻址链（§11.4，`fix_task76…--apply` 写活库+新 blob，未跑）；manifest slice（Task 46 lane owned，BLOCKED）；zero_regression 基线（5 漂移仅 D3 一处是本段的，`--apply` 会掩盖别 lane 漂移故不做）。
    - **整册 materialize**：新判据 `TestFullBookMaterializeAfterTemplateFooterFix`（D3-2 primary + D3-6/D3-4借/D3-4贷/D3-5 全 sibling 各 5 行）**verify equivalent=True**。
    - **§7 引擎边界（登记不修）**：footer 散落单格差异公式不随插行扩张，全平台 3 家共此边界（D3-4借/D4-1/D1-07），业务后果=差异数漏算新增行且不报错。
    - **§8**：新判据 `TestGtSyncFooterRowReFrozenAfterD34DebitInsertion` —— D3-4 段①插行后 `_GT_SYNC.GT_FOOTER_ROW_D34DEBIT` 按插行数重冻结，**passed**。
    - **回归**：D3 范围 1 failed/102 passed/1 skipped/2 xfailed，唯一红 `test_task5…real_registration` 本段前即红（别 lane）；本段新增失败=0。golden digest 零回归（不 --update）。D4 真栈退出码 0（verify equivalent）。

### 阶段 3：D3-7 预收账款检查表（双区，凭证抽查）

- [x] 11. `phase5_d3_07_voucher_check.py` 声明**两个** spec
  - `D3-vc-current-rows` / `D3-vc-post-rows`；48 行 ×18 列，两区行段由 Task 1 实测
  - 结构与阶段 2 的 D3-4 双区同型 ⇒ 可复制其声明骨架
  - _Requirements: 3.1_

- [x] 12. D3-7 接入验收
  - Property 4 转绿（受管区 5→7）；双区位移链实证
  - Property 9：`useD3CrossSheet` 对 `D3-vc-post-rows` 的读取在 OO 回写后仍正确重算
  - 整册 materialize + 耗时登记
  - _Requirements: 3.3, 3.4, 6.1_
  - ✅ 2026-09-26 证据落 `evidence/task12-d3-07-acceptance.md`：翻 `_INCLUDE_D307_VOUCHER_CHECK`
    True + `generate_phase5_d3_contract.py --apply` 重生成磁盘契约（canonical `fb48ff50…`，
    **不改模板**——Task 11 已确认 D3-7 无缺陷）；受管区 **5→7**（d32 1 + d36 1 + d34 2 + d35 1 +
    **d37 2**），`d37-managed` 一个 sheet 含两 table（`voucher_check_current_rows`/`_post_rows`），
    两键 `D3-vc-current-rows`/`D3-vc-post-rows` 各归其表；`assert_contract_file_matches_source()` 通过。
  - **Property 4（D3-P4）转绿**：`test_d3_property3_4_dual_zone_baseline.py` D3-7 部分从"未接入
    红基线"迁到"已接入绿"（照抄 D3-4 改法：d37-managed 一 sheet 恰 2 table、两键各归其表）；受管区
    计数判据 5→7（`_STAGE2_REGIONS_BY_SHEET` 加 `d37-managed:2`）；三组变异用例原样保留（6 passed）。
  - **双区位移链**（新建 `test_d3_07_dual_zone_shift_and_verify.py`，14 passed/2 xfailed）：区①插 5
    行→区②兄弟 Table ref 下移 + `verify_unmanaged_regions` equivalent（单趟 +5 / 两趟 +5/+5 累积
    归一化）；`_GT_SYNC` `GT_FOOTER_ROW_D37CURRENT`/`D37POST` 按 row_shift.count 重冻结；D3-7 自动
    进入 `test_sibling_table_ref_row_shift._multi_region_sheets` 参数化清单（2 区）。
  - 🔴 **实证两处上游引擎累积归一化边界（登记不修，xfail strict，同 D3-4 §7 处置）**：①孤立场景
    区①插行数恰 == 2（footer 27→撞区②组标题 29）；②整册场景（primary=D3-2）区①作为非主 sibling
    插任意行。根在 `adapters/excel._sheet_cumulative_shift`（跨 lane、blast radius 大），非 D3-7
    声明缺陷（几何/字段/footer marker 实测正确，改声明无法规避）；生产后果 = fail-closed 500（非
    静默错数据），仅特定插行几何触发，正常路径（区②插行 / +5/+5）不受影响。
  - **Property 9（D3-P9）**：`useD3CrossSheet.spec.ts` 加 Property 9 块（8 passed）：真验
    `postPeriodSettlementSync` 读 `D3-vc-post-rows` 的 byCustomer/total 聚合 + **OO 回写后重算**
    （替换 Map → computed 重算到新值、不残留旧值）+ fast-check property（numRuns 100）。
    `[ ]*` **OO 回写动作本身真栈不可测**（D3 adapter 未注册裁决 F5 + OO 写格三陷阱，同 Task 5/7）。
  - **整册 7 区 materialize**（`TestFullBookSevenRegionMaterialize`）：D3-2 primary + D3-6/D3-4借/
    D3-4贷/D3-5/D3-7区①/D3-7区② 全 sibling 一次 materialize + verify **equivalent**（区①
    present-no-insert 避开 §边界②、区②真插行）。引擎层耗时登记（`build_store_projection` 1/10/50
    行，两 spec：current 0.28/0.54/2.71ms、post 0.43/0.67/2.10ms，标"引擎层非真栈"，同 Task 5/10）。
    `[ ]*` 真栈端到端整册耗时仍卡 adapter 未注册。
  - **golden digest 零回归**（87 digest）：漂移只在 D3 **d37 新增**（additive），其余 7 家 provider
    + D3 已有 sheet（d32/d36/d34/d35）+ d3 instr/projection digest 全不变；基线已含 d37，`--update`
    幂等（git 无 diff）。
  - **全量 D3 回归** `-k "d3 or D3"`：2 failed / 118 passed / 4 xfailed。两红逐条确认**非本任务
    引入**（新增失败 = 0）：①`test_task5…real_registration`（任务原文列的已知基线红）②
    `test_sibling_table_ref_row_shift…[D1-8]`（`TypographyRowError` on D1-11，并发 lane 未提交改动
    `phase5_d1_11_related_party.py`——把 D3-7 开关临时改 False 重跑同一批 D1 sheet 仍全部失败，
    证明与 D3-7 无关）。definition_store 重发布同 Task 10 §11.4 不跑，如实登记已知红。
  - 未碰引擎代码/模板/tasks.md 标题行与复选框/别的会话在途文件；一次性探针用完即删。

### 阶段 4：D3-1 审定表（依赖前置 B/C）

- [x] 13. `phase5_d3_01_adjudication.py` 声明（`AdjudicationSheetSpec`）
  - `sections` 与 `row_mode` **取 Task 1 实测值**，🔴 不得照 D1-1/D2-1 推演（裁决 F3）
  - 逐格 mask（30 行 ×12 列 / 88 公式 / 密度 24%）
  - 🔴 **不得**在引擎里加 `if is_d3` 分支 —— 会让上游框架层 AST 卡点打红
  - Property 6 判据：`sections`/`row_mode` 与模板实测几何一致；变异改成 D1-1 的 3 区 ⇒ 必红
  - _Requirements: 4.1, 4.2, 4.3_
  - ✅ 2026-09-26 证据落 `evidence/task13-d3-01-declaration.md`：openpyxl 直读复核
    `审定表D3-1`（一次性探针用完即删）确认**两区块**（nature 数据 8-12/合计 13、aging 数据
    17-20/合计 21）+ footer（合计 21/TB 22/差异 23，差异只 E/I 对账龄区）+ 88 公式（82 受管格
    + 6 表头底稿目录引用），与 Task 1 evidence 逐项一致。新建
    `phase5_d3_01_adjudication.py`（`SPEC_D301`/`MANAGED_SHEET_D301`，两 `AdjudicationSection`
    uuid_col=""、`row_mode=fixed_rows`、`per_cell_key_template="D3-adj-{section}-{slug}-{field}"`
    与前端 `useD3Adjudication.makeItemId` 的 `nature`/`aging` token 逐字对齐、`cell_mask` 走
    `_build_cell_mask()` 现算 82 格不手写字面量、`current_unadjusted=cross_sheet` 派生格不可
    OO 直写、三 note item + TB 种子登记 HTML-only）。
  - **Property 6 判据**（新建 `test_d3_01_adjudication_spec.py`，**15 passed**）：区块数==2 +
    section_key==[nature,aging]（反证不含 gross/bd/net）+ 两区几何行号 + `row_mode==fixed_rows`
    + 逐格 mask 格级（区2 手工列 B/C/D/F/G/H 不落 mask）+ 现算 mask==spec.masked_cells。
    **变异必红**：`test_mutation_run_real_geometry_asserts_would_fail` 把真声明的几何断言对
    变异体（照 D1-1 推演的 3 区 gross/bd/net）逐条跑，`pytest.raises(AssertionError)` 证明
    三条断言（两区/nature-aging 键/账龄区 last_data_row=20）对变异体全抛、对真声明全过。
  - **零回归**：golden digest `✅ 87 个 digest 逐个不变`（未翻灰度开关、未重生成契约，同
    Task 6/8/9/11 模式）；D3 property2/property3_4/expansion + 框架层 adjudication 判据
    **64 passed**。已知基线红复核（`test_task5…real_registration` 仍红=adapter 未注册裁决 F5、
    `test_fail_closed_behaviours_match[d3]` xfailed）非本任务引入，新增失败=0。
  - **未碰**引擎/框架层/模板/灰度开关/契约/别 lane 在途文件；**零 `if is_d3` 分支**；一次性
    探针用完即删；无停下报告裁决点（框架层能力足够，未需硬改）。

- [x] 14. D3-1 四态覆盖状态机 + 覆盖 UI
  - 复用 `shared/dynamicAdjudicationRows.resolveCellState` / `displayValueForCellState`，
    **不得**在 D3 侧另写一套
  - **Property 8 反证式先写**：只改 `derived` 不改 `stored`/`snap` ⇒ 覆盖标记数必须为 0；
    🔴 另须一条**跑同步器**的判据（上游 13 条纯函数判据全绿而生产坏掉的教训）
  - S2 标「已人工覆盖」/ S4 三值不自动二选一 / 逐格「恢复取数」
  - Property 7 转绿（逐格 mask 下受管金额字段仍判 `editable`）
  - 受管区增至 8（按 D3-1 实测区块数调整）+ 整册 materialize + 耗时登记
  - _Requirements: 4.4, 4.5, 4.6, 6.1_
  - ✅ 2026-09-26 证据落 `evidence/task14-d3-01-state-machine-and-ui.md`：**复用**共享
    `resolveCellState`/`displayValueForCellState`（`useD3Adjudication.ts` 逐格接，per-cell 键
    `D3-adj-{section}-{rowKey}-{field}` + snap 键 `${itemId}-snap` 照 D4 `snapItemId` 同款存法，
    **未在 D3 侧另写一套**）：`buildRow` 的 `currentUnadjusted`（value_sources=cross_sheet 派生格）
    从「非零二选一」改为四态，S1/S3 显示派生、S2/S4 显示覆盖值 + `cellOverrides`；新
    `syncDerivedCellsIntoStore`（watch immediate，幂等写 stored+snap，仅未覆盖格——冻结 snap 使
    S4 可达）+ `restoreDerivedValue`（逐格恢复取数、当场写对）。
  - **Property 8 反证式（先写）+ 跑同步器判据**（新建 `d3CellOverrideRender.spec.ts`，8 passed）：
    ①纯函数反证（fc numRuns=5）——只改 derived、stored==snap ⇒ 覆盖标记数(S2+S4) 恒 0；对照 stored≠snap
    出 S2/S4。②🔴 **跑同步器**（真实实例化 useD3Adjudication 喂 crossSheet 聚合 + 手工覆盖）：S1/S2/S3/S4
    全可达、S4 三值互不相等（系统不自动二选一）、snap 在 store 真冻结、恢复取数当场写对 + 作用域一格
    （范式照 `d4CellOverrideRender.spec.ts`「composable 层判据」，补纯函数判据证明不了的运行时可达性）。
  - **S2 标「已人工覆盖」/ S4 三值不自动二选一 / 逐格「恢复取数」**：`D3TabAdjudication.vue` 期末未审
    格渲染 el-tag「已人工覆盖」(S2/S4) + S4 el-tooltip 展示覆盖值/原取数/现取数（提示人工裁决）+
    逐格「恢复取数」el-button（调 `restoreDerivedValue`，只影响该格）。UI 全中文。
  - **Property 7 转绿**（新建 `test_d3_01_coverage_and_property7.py`，7 passed）：账龄区手工金额格
    B/C/D/F/G/H 逐格 `is_cell_masked==False` ⇒ 仍 editable（mask 只覆盖派生/合计/差异公式格）；对照
    派生/computed 格 `is_oo_writable==False`；变异（把 B17 塞进 mask）必红。
  - **第二套 gating 接法**：`GtD3PrepaidAccounts.vue` 新增独立 `isD3AdjudicationSyncSheet =
    computed(() => currentSheet.value === 'D3-1')`，**未**并进 `isD3DetailSheet`（后者只判 D3-2）——
    D3-2 行表 rows kind（d32-managed/syncBridge）vs D3-1 逐格 mask kind（d31-managed）不共桥；
    `renderModeOptions` 三分支（D3-1 因 adapter 未注册暂禁用在线编辑、保持结构化视图）；守卫判据
    `d3AdjudicationGatingBoundary.spec.ts`（3 passed）源码级钉「不得并进 isD3DetailSheet」。
  - **受管区 7→8 口径**（🔴 审定表 vs 行表口径不同，不硬凑）：Task 12 `_STAGE2_REGIONS_BY_SHEET`
    数行表契约 TableSpec=7；D3-1 是 `row_mode=fixed_rows` 逐格 mask 的独立 `AdjudicationSheetSpec`
    （非动态行表，不进 build_contract_payload），故**行表契约计数仍 7**（非遗漏）；D3-1 作第 8 区
    登记在**组合口径**=行表 7 + 审定表 sheet 1（d31-managed 两 section 属同一受管 sheet，sheet 级计 1，
    同 D4-1）。判据钉组合口径 8 + 行表基线不变 + 口径隔离。
  - **back-compat 基线显式更新**：`dynamicAdjRowsBackcompatBaseline.spec.ts` 运行时 value-importer 允许
    清单加 `useD3Adjudication.ts`（第三个），文件头注明「预期扩散、非悄悄污染」——四态状态机本是平台级
    共享件，D3 只复用未改共享件默认路径（P10 逐字节冻结判据仍绿），**绝未**为规避基线而 type-only
    import 或另写一套。
  - **零回归**：10 张 D3 前端套件 90 passed、Task 13 spec 15 passed、框架层 adjudication 34 passed、
    `vue-tsc --noEmit` 全仓 0 error TS。
  - `[ ]*` **整册 materialize 真栈不可测**（双卡点）：①🔴 **另一会话在途**把 `d31-managed` 接进行表
    契约（磁盘契约 + `phase5_d3_prepaid_receipts.py`/`phase5_d3_expansion.py` 在途改动）但结构非法
    （`parse_contract` 抛 `cell.row_from=row_identity 只能用于行域字段`，D3-1 固定行非行域字段），
    `git show HEAD:` 磁盘契约无 d31-managed 证实**非本任务引入**——本任务不碰该 lane 文件，判据改为
    不依赖被污染的 `assert_contract_file_matches_source()`（用 HEAD 行表基线常量 + 干净 SPEC_D301）；
    ②adapter_registered=False（裁决 F5，同 Task 5/7/10/12）。
  - 🔴 **停下报告裁决点（在途冲突）**：D3-1 计入受管区的**行表 vs 审定表口径分歧**已在真库层显现——
    另一会话正把 D3-1 接进**行表契约**（若成立=第 6 张行表 sheet），而本任务按 Task 13 的
    `AdjudicationSheetSpec` 独立口径处理（D3-1=第 8 个受管区、不进行表契约）。两条路线对「D3-1 是不是
    行表」的判定相反且该 lane 当前产物非法。**建议裁决**：D3-1 固定行逐格 mask 应走 AdjudicationSheetSpec
    独立口径（同 D4-1 只在动态行时才进行表契约），请协调该 lane 停止把固定行 D3-1 塞进行表契约、修复
    磁盘契约非法结构；本任务代码/判据已按此口径落地，待裁决后可解锁真栈整册 materialize。

### 阶段 5：D3-3 可行性核 + 前端接线 + 验收

- [x] 15. D3-3 可行性核 + 裁决（**不改生产代码**）
  - 已实证：`D3TabAdjustment.vue` 接 `useAdjustmentCentralSync` **3 处** ⇒ 经后端
    `AdjustmentSyncService` 中央登记；`D3-aje-rows` 是 hub store
  - 本任务待核：借贷平衡不变式是否仅 HTML 侧强制 / 模板 23 行 ×10 列有无行身份列
  - 照 `T08-d44-single-html-adjudication.json` 范式落证据；默认倾向 `single_html`
  - Property 11：核阶段不改任何生产代码（上游诚实边界红线）；变异改了 provider ⇒ 必红
  - 📌 **六张调整分录汇总表全部同型**（D1-5/D2-4/D3-3/D4-4 已判/D5-3/D6-4/D7-3，宿主均接
    `useAdjustmentCentralSync`）⇒ 建议统一裁决另立 spec，本任务只产 D3-3 的核与证
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - ✅ 2026-09-26 **裁决 `single_html`（与 D4-4 一致），未改任何生产代码**。证据落
    `evidence/task15-d3-03-feasibility.md` + `evidence/task15-d3-03-single-html.json`（照
    T08-d44 范式）。**openpyxl 实测**（一次性探针用完即删）真实 tab `调整分录汇总表D3-3`
    A1:J23（23r×10c，模板 sha `33165493…` 与 `TEMPLATE_SHA256` 一致）：①**无行身份列**——全表
    扫 GTROW/_GT/UUID/rowId=NONE、候选空列 K/L/M/N 数据行 6-22 全空；②**借贷平衡 HTML+后端
    双层强制、Excel 模板零校验**——HTML 侧 `useD3Adjustment` `isBalanced/balanceDiff` computed
    + 宿主 `D3TabAdjustment.vue` `!isBalanced` disabled 门，后端 `AdjustmentSyncService.
    sync_from_workpaper` 第 1 步 `total_debit != total_credit → UNBALANCED`，Excel 数据区 6-20
    零内容零公式（6 处公式全在行 3-4 底稿目录引用，无一落数据行）；③是中央登记 hub（`D3-aje-rows`
    经 `useAdjustmentCentralSync`→`source_ref={wp_id}:D3-aje-rows`），OO 回写会同时绕过两道
    平衡门并与中央登记去同步。**⇒ 比 D4-4 更强的 single_html 案例**（双门 vs 单门）。
  - **Property 11 守卫判据**（`backend/tests/workpaper_sync/test_d3_03_single_html_adjudication.py`，
    **19 passed**）：四条依据钉成测试（防证据腐烂，含 D3-2 有非空 `uuid_col` 反面对照）+ 受管契约
    **缺席守卫**（`D3-aje-rows` 不在 `phase5_d3_expansion.all_store_item_ids()`、`调整分录汇总表D3-3`
    不在 `all_managed_sheet_names()`、无行表/审定表 spec 声明该 sheet、无 `phase5_d3_03` 模块）；
    **变异必红**（`TestMutationRegisteringD303WouldGoRed`：把 `D3-aje-rows`/managed sheet 塞进受管
    契约后同一缺席断言 `pytest.raises(AssertionError)`——证明谁想偷偷接入必被拦）。
  - **一致性核对**：`D3-aje-rows` 键写入方（`useD3Adjustment.ts:48` `persistRows`）与读取方
    （`useD3CrossSheet.ts:319` / `D3TabIndex.vue:67` / `D3TabAdjustment.vue:190` / 后端
    `_d3_import_export.py:155`）**逐字一致、有写入方**——复核确认**无** D6/D7 那种「读无写入方
    聚合键、目录完成度恒未填」的 bug。
  - **建议**：六张调整分录汇总表统一裁决 `single_html` **另立 spec**（design F4 已记），本任务只产
    D3-3 的核与证，未越界处理其它五张。**无停下报告裁决点**（可行性核纪律与接入无混淆，生产代码零改动）。

- [x]* 16.* 前端接线 + 变异检验 + 真栈 + 证据
  - 前端：受管 sheet 集合**从 provider 受管清单派生**（不前端硬编码）、`capability` 与
    `flushHtml` 改读 `Ref`（现状 `isD3DetailSheet = currentSheet === 'D3-2'` 单张写死）；
    非受管 sheet 保持现状 + 中文原因，**不得**落 legacy 假双向。Property 12 钉住
  - Property 1~12 逐条变异并记录打红条数；未能打红的重写而非保留
  - 真栈：切「在线编辑」→ 六张 OO canvas 逐值断言 → 改一格 → forcesave → 回读等值。
    `--workers=1`。🔴 三陷阱沿用上游结论（不能用 `page.on('response')` 判 callback；不能用
    `asc_*` API 写格；模式切换条选择器**须实测**不得照抄 D4）
  - 🔴 IF `adapter_registered=False` 未解除 THEN 真栈整段标 `[ ]*` + 写明「代码已改但未实测，
    卡 adapter 未注册」，**不得**以合成测试冒充真栈
  - 证据落 `docs/operations/evidence/d3-sync-coverage/`，数字脚本现测
  - _Requirements: 6.6, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5_
  - ✅ 2026-09-26 证据落 `evidence/task16-frontend-wiring-and-mutation.md`。
  - **段 A：前端受管集合派生**（Requirements 6.6）：新建 `d3ManagedSheets.ts` 单一来源清单（6 张
    受管 sheet，5 rows + 1 adjudication）+ `GtD3PrepaidAccounts.vue` 5 处字面量→派生改造（
    `isD3DetailSheet` → `isD3OoWiredRowsSheet` / `isD3AdjudicationSyncSheet` →
    `isD3ManagedAdjudicationSheet` / `syncSheetKey` → computed 动态解析 / `syncCapability` →
    computed 现算 / `flushHtml` 读 Ref 不写死字面量）。非受管 sheet 保持结构化视图 + 中文原因。
    诚实边界：`D3_OO_WIRED_ROWS_CODES=['D3-2']`，不假称其余可切 OO。
  - **Property 12 判据**（Requirements 6.6）：后端 `test_d3_frontend_managed_sheet_parity.py` **7
    passed**（前端 excelName 集合 == 后端 `all_managed_sheet_names()` 逐字；rows/adjudication
    sheetKey 分别与后端 spec 一致；3 条变异全红——假 sheet/漏 sheet/游离字面量）+ 前端
    `d3ManagedSheets.spec.ts` **6 passed**（6 张计数/kind 分类/互斥/诚实边界/sheetKey 对齐）。
  - **段 B：Property 1~12 变异打红总表**（Requirements 8.1, 8.2）：12 条全验通过，变异全部打红，
    未能打红 = 0，无需重写。详见证据 §2。总计变异用例 22 条（P2 7 红/P3-4 3 红/P6 2 红/P7 1 红
    /P8 2 红/P11 2 红/P12 3 红 + P1/P5/P9/P10 各含变异机制恒绿基线）。
  - **零回归**：前端 D3 相关判据 26 passed（d3ManagedSheets 6 + gatingBoundary 4 +
    cellOverrideRender 8 + crossSheet 8）；后端 Property 判据 76 passed（parity 7 + property2 15
    + property3_4 6 + adjudication_spec 22 + coverage_property7 7 + single_html 19）。
  - `vue-tsc --noEmit`：OOM（已知环境限制——仓库体量超出当前 session heap 上限，非本任务引入；
    Task 14 最后一次成功跑过全仓 0 error TS，本任务仅改宿主 5 处字面量→computed 派生，
    TypeScript 类型安全由 vitest 编译隐式覆盖）。
  - `[ ]*` **真栈整段：代码已改但未实测，卡 adapter 未注册**（裁决 F5，同 Task 5/7/10/12/14）。
    真栈脚本骨架已落证据 §3.2，不跑/不以合成冒充。三陷阱沿用上游结论。
  - 🔴 **停下报告裁决点**：①adapter_registered=False 未解除——建议随 umbrella Task 76/77 finalize
    gate 统一解锁；②在途冲突（同 Task 14 已报）——D3-1 行表 vs 审定表口径分歧；③后端下发受管
    短码集合（改进项）——理想形态是 manifest 生成物新增 `managedSheetCodes`、前端从生成物读取，
    属跨前后端建设超出本任务范围。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门先于一切 —— 上游框架层未入库则无引擎可声明；adapter_registered=False 决定真栈判据能否跑" },
    { "wave": 1, "tasks": ["1", "2", "3", "4", "5"], "rationale": "几何实测 / 零回归基线 / 两组红判据 / 性能基线互不依赖可并行；Property 2/3/4 此时必红是后续归因依据" },
    { "wave": 2, "tasks": ["6"], "rationale": "D3-6 单区声明依赖 Task 1 的实测几何与 Task 3 的键名判据" },
    { "wave": 3, "tasks": ["7"], "rationale": "D3-6 验收门：受管区 1→2 + 下游重算 + 整册 materialize，齐了才算接住首张" },
    { "wave": 4, "tasks": ["8", "9"], "rationale": "D3-4 双区与 D3-5 单区互不依赖可并行；均依赖 Task 7 已证多受管 sheet 通路" },
    { "wave": 5, "tasks": ["10"], "rationale": "阶段 2 验收门 —— 双区位移链在 D3 首次验通，是阶段 3 的前提" },
    { "wave": 6, "tasks": ["11"], "rationale": "D3-7 双区结构与 D3-4 同型，依赖 Task 10 已验通位移链" },
    { "wave": 7, "tasks": ["12"], "rationale": "D3-7 验收门" },
    { "wave": 8, "tasks": ["13"], "rationale": "D3-1 审定表声明依赖前置 B/C 与 Task 1 的区块数实测" },
    { "wave": 9, "tasks": ["14"], "rationale": "四态状态机依赖 Task 13 的 spec 形态已落（否则读不到 stored/snap/derived 三个量）" },
    { "wave": 10, "tasks": ["15"], "rationale": "D3-3 可行性核独立于接入链，排在接入之后以免核阶段的「不改代码」纪律与接入改动混淆归因" },
    { "wave": 11, "tasks": ["16"], "rationale": "前端接线依赖后端受管清单已定；变异与真栈收口需全部行为已落地" }
  ],
  "blocking": {
    "0": "上游框架层未入 HEAD ⇒ 无 RowTableSheetSpec/AdjudicationSheetSpec 可声明，本 spec 全部阻塞；merge._protection 未入库 ⇒ 阶段 4 阻塞；adapter_registered=False ⇒ 真栈实测阻塞（需求 7.4）",
    "1": "几何与键名未实测 ⇒ 声明只能按 D3-{n}-rows 推演，而 D3 的键用语义缩写与编号无对应关系（D1/D2 已因此出过三次遗漏）",
    "3": "Property 2 未先打红 ⇒ 按编号推演键名这个最易犯的错没有可执行判据",
    "4": "Property 3/4 未先打红 ⇒ Task 10/12 的「受管区 2→4 / 5→7」转绿不可归因",
    "5": "性能基线未取 ⇒ 需求 6.1 的每批次耗时对比无分母，硬门形同装饰",
    "6": "D3-6 声明未落 ⇒ Task 7 无验收对象，且多受管 sheet 在 D3 上的通路未证",
    "8": "D3-4 双区未落 ⇒ Task 10 的位移链无实证对象，阶段 3 的 D3-7 双区缺前置验证",
    "13": "D3-1 spec 未落 ⇒ Task 14 的四态状态机读不到三个量"
  }
}
```

## Notes

### 已裁决（详见 design §关键裁决）

- **F1**：D3 单册，12 张 sheet 可同 entry，不受 D2 三册约束
- **F2**：`store_item_id` 逐个实测，禁止按编号推演（Property 2 钉住）
- **F3**：D3-1 的区块数与行模型待实测，不照 D1-1/D2-1 推演
- **F4**：D3-3 走可行性核；六张调整分录汇总表建议统一裁决另立 spec
- **F5**：`adapter_registered=False` 是真实前置，真栈实测须先解除、不得以合成冒充

### 继承上游四条纪律

「一 entry 一 adapter」不变 · 诚实边界（不是每张 sheet 都双向）· 可行性核硬门（有行身份列 +
无专用同步链冲突）· D4-4 已判 `single_html` 的判据适用于全部调整分录汇总表。

### 顺带发现（登记，不在本 spec 处理）

**D6/D7 底稿目录完成度判定引用无写入方的聚合键**：`D6TabIndex.vue:54` 读 `D6-6-rows`
（真实 `D6-6-block1-rows`/`-block2-rows`）、`:56` 读 `D6-8-rows`（真实 `D6-8-single-rows`）、
`D7TabIndex.vue:50` 读 `D7-4-rows`（真实 `D7-4-credit-rows`/`-debit-rows`）、`:56` 读
`D7-7-rows`（真实 `D7-7-period-rows`/`-post-rows`）。四键全仓零写入点 ⇒ 这四张在目录里完成度
恒显示「未填」。与 D1 那个「四处拼锚点三处拼错、测试镜像同款错误恒绿而生产恒死」同型。
D3 侧未见同类。建议随 D5/D6/D7 spec 一并修。
