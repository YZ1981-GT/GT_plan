# Implementation Plan

## Overview

**spec**：`d4-html-to-oo-store-contract-alignment`　**创建**：2026-09-23　**状态**：17/18
（任务 18 未完成 —— 需求 5.2/5.3 未实测，卡 materialize Table ref 维护缺陷，详见任务 18 正文）
**2026-09-23 修订**：用户拍板 O1 选项 b（OO 侧覆盖生效）⇒ 任务 12 重写 + 新增 13~16，14 → 18 条。
**2026-09-23 进度校准**：此前 tasks 全标 `[ ]` 而代码/判据已实际落地 —— 逐符号 grep + 实跑核对后
按下表校准（详见文末「实施进度实证」）。剩余 11 / 17 / 18 三条为**真缺口**，不是标记滞后。

三处缺陷、两个缺陷类，外加选项 b 带来的逐格覆盖状态机与一处既有小计口径对齐。

顺序有意义：**阶段 1 是红判据先行** —— P1/P9 现状必红，没有这两条红，后面的「修好了」与
「判据本来就不会红」区分不开。**阶段 2（缺陷 C）刻意排在阶段 3（缺陷 A）之前**：它是纯后端、
不碰前端存储模型，先落地能让 D4-35/D4-13 两张立刻可用，也让阶段 3 的真链测试有干净底座。
下方复选框为唯一进度真源。

## Tasks

### 阶段 1：红判据先行

- [x] 1. P1 红判据：HTML 可见行 ≡ projection 两区受管键
  - 在真库 D4-1 底稿上断言「HTML 可见行集」与 `row_keys` + `values` 逐行逐字段等值
  - 现状必红（4 个行身份 / 0 个字段）；记录红的条数与实测数字
  - ✅ `backend/tests/workpaper_sync/test_d4_1_html_shape_store_projection_gap.py`（3 条）：
    修复后形态逐值带金额 / 旧四键形态仍丢金额（红形态镜像常驻）/ 前端行清单无金额键
  - _Requirements: 1.1_

- [x] 2. P9 红判据：D4-35 / D4-13 出方向拿不到 payload
  - 复用一次性探针的对照结构（端点真实装配 vs 手动塞入），落成正式测试
  - D4-35 断言字段数（现状 0 / 对照 32）；**D4-13 必须比值**（现状 `''`），不得比键数
  - ✅ `backend/tests/workpaper_sync/test_d4_store_item_wiring_gap.py`（3 条），`_endpoint_payload_loader_rule()`
    如实复刻端点选择逻辑；D4-13 比值不比键数
  - _Requirements: 3.2_

- [x] 3. P10 基线：非参与消费方序列化输出快照
  - 对 `useD1DetailCategory` 等自带 `serializeRows` 的实现取输出快照，作为阶段 3 的零回归底线
  - ✅ `dynamicAdjRowsBackcompatBaseline.spec.ts`（3 条）：不传 `readField` 时四键形态逐字节冻结
    + 运行时消费方边界恰为 `useD4Adjudication`/`useK2Adjudication`
  - _Requirements: 4.3_

### 阶段 2：缺陷 C —— store item 清单单源（纯后端）

- [x] 4. provider 暴露 `all_store_item_ids()` 单一口径
  - 并集：`STORE_ITEM_IDS` ∪ `STORE_ITEM_IDS_D45_FIXED` ∪ `STORE_ITEM_IDS_D413_FIXED`
    ∪ `{STORE_ITEM_ID_D435_DICT}` ∪ `STORE_ITEM_IDS_D47_DEDICATED`
  - per-item 缺省值规则保持既有 provider 单源（list `[]` / dict `{}` / fixed 纯文本 `""`），
    **不得**回退成 blanket `"[]"`（那条会打挂整个 entry，已修过一次）
  - ✅ `phase5_d4_revenue_detail.all_store_item_ids()`（46 item 收敛，per-item 缺省值规则未动）
  - _Requirements: 3.1_

- [x] 5. 出方向 `store_projection_response.py` 改走单一口径
  - 删掉 `STORE_ITEM_IDS` + `STORE_ITEM_IDS_D45_FIXED` 的双来源拼装（删前 grep 零调用方）
  - 任务 2 的 P9 判据 SHALL 转绿
  - ✅ 已改（老 provider 无该函数时回退旧并集，行为不变）；P9 三条已绿
  - _Requirements: 3.1, 3.2_

- [x] 6. 回方向 `oo_to_html.py` 改走同一口径
  - 消除三处 `hasattr(bridge, "STORE_ITEM_IDS_*")` 的清单来源（merge 分支本身保留）
  - 断言两方向取到的 item 集合**逐元素相等**（这是 3.1「不得各自维护并集」的判据面）
  - ✅ rows 循环基础集合取 `all_store_item_ids()` 再减去走专用块的 item
  - _Requirements: 3.1, 2.3_

- [x] 7. CI 卡点 `check_store_item_ids_fully_wired.py`
  - AST 扫 provider 上所有 `STORE_ITEM_IDS*` 声明与 dict-store 常量，断言逐个被
    `all_store_item_ids()` 覆盖；新增一条未接线的声明必须红
  - 接入 `governance-checks.yml`；**不**依赖 `tests/workpaper_sync/` 分母（见需求 3.3）
  - ✅ 脚本（AST 静态声明 + 运行时 `dir(P)` 兜 import 来的 tuple）+ `governance-checks.yml` 两 step
    + 自测 4 条（含变异反证）；实跑「46 个 item 全部经 all_store_item_ids() 收敛」
  - _Requirements: 3.3_

### 阶段 3：缺陷 A —— D4-1 存储模型对齐（共享层）

- [x] 8. 共享件 `serializeRows(rows, {readField})` 落 `valueFields`
  - 值写成 `number | null`（**不是**字符串，见 design §Error Handling），解析归一与 `readNum` 同源
  - 必带 `sectionKey`（否则后端 `_table_key_for_row` 静默兜底会把其他段落进主营段）
  - 任务 3 的 P10 快照 SHALL 零变化
  - ✅ `dynamicAdjudicationRows.serializeRows(rows, {readField, readDerivedSnapshot?})`；
    `dynamicAdjRowsValueCarrier.spec.ts`（9 条）；P10 三条零变化
  - _Requirements: 4.1, 4.3_

- [x] 9. 单源读 `readRowFieldWithFallback`：行对象优先、缺则回落 per-field
  - `useD4Adjudication.getRowFieldValue` 与 `useK2Adjudication` 同时改走它
  - P6 迁移用例：只有 per-field 旧数据的行读回等值（金额不归零）
  - ✅ 两消费方均已改走（`useK2Adjudication` 无业务改动，仅换读侧）；P6 迁移不归零已断言
  - _Requirements: 4.1, 4.2_

- [x] 10. 双写接线：`persistRowList` / `persistFieldValue` 同时刷新行对象
  - per-field 继续写（回滚只需改读侧优先级，不必回填数据）
  - ✅ `rowListReader` 供 `readField`/`readDerivedSnapshot`，行清单重写时把金额与 snap 一并刷进行对象
  - _Requirements: 4.2_

- [x] 11. P4 真链判据：OO 改动 → merge → HTML 读回等值
  - 真链：store → materialize → 改产物 → extract → `oo_to_html` merge → HTML 读回
  - **禁止两端各自 mock**（缺陷 A2 正是那样全绿的）；同时断言 P5 不丢 `source`/`accountCode`
  - ✅ 两段判据合计 6 条：
    * `test_d4_1_oo_to_html_realchain.py`（3 条，真 contract + 真 provider 双向函数）—— 覆盖
      merge → HTML 读回等值 / HTML-only 字段不丢 / `derivedSnapshot` 穿过 merge 不被冲掉；
    * `test_d4_1_materialize_extract_realchain.py`（3 条，**补真 xlsx 物化段**）—— 走
      `build_workbook_bytes` 真物化 → openpyxl 改产物 → `extract_projection` 真提取 → merge，
      端到端断言 HTML 读回等于 OO 改后值。此前只在 projection 里改 `FieldValue` 代替真产物，
      物化/提取那一段无判据覆盖，现已补齐。
  - _Requirements: 2.1, 2.2_

### 阶段 4：缺陷 B —— 派生行进 store + 逐格覆盖（选项 b）

- [x] 12. `syncDerivedRowsIntoStore()` + watch 派生源 + 写 `derivedSnapshot`
  - 幂等（值未变不写）、`source` 恒 `'tb'`（需求 1.4 的可区分落点）、带 `sectionKey`、
    **同时**写 `derivedSnapshot`
  - store `rowId` 直接用派生 `rowKey`（`xsheet-{section}-{labelKey}`）⇒ 与派生行按 rowId
    精确配对，不依赖 label 模糊匹配
  - **不**放在 `flushHtml` 里（切 OO 不得变成写操作，见 design 裁决 D4）
  - P13：S3 自动跟随幂等，值未变不产生第二次写库
  - ✅ `syncDerivedRowsIntoStore()` + `watch([crossSheetMainRows, crossSheetOtherRows], deep)`；
    `_writeIfChanged` 承担幂等；snap 落 `{rowId}-{field}-snap`，序列化时进行对象 `derivedSnapshot`
  - _Requirements: 1.1, 1.4, 6.3_

- [x] 13. 逐格四态解析 `resolveCellState()` + P11/P12 穷举判据
  - 按 `(stored vs snap, snap vs derived)` 两个布尔量穷举 S1~S4；相等判定走 `readNum` 同源容差
  - **P12 反证式判据先写**：只改 `derived` 不改 `stored`/`snap` ⇒ 覆盖标记数必须为 0
    （钉住「用 `stored ≠ derived` 判覆盖」那个错法，需求 6.1）
  - P11：断言无第五态可达
  - ✅ `resolveCellState` / `displayValueForCellState`；`dynamicAdjRowsCellState.spec.ts`（13 条）：
    四态穷举 + 无第五态 + 容差口径（不裸 `!==`）+ null 语义 + P12 反证式 + 错法对照
  - _Requirements: 6.1, 6.2_

- [x] 14. `sections` 改逐格覆盖合并（不再整行 `continue` 跳过）
  - 派生行做基底，逐格按四态取 `derived` 或 `stored`
  - P7 **条件式**：S1/S3 格落库前后渲染等值；S2/S4 格必须显示 `stored`（只断言前半会放过
    「覆盖被吞掉」）
  - ✅ 逐格合并落在 `buildCrossSheetRow` → `_resolveDerivedCell(rowId, field, derived)`：派生行
    做基底、逐格按四态定显示值，`cellOverrides` 只在 S2/S4 产生条目
  - ⚠️ **与本条原文的一处偏差，显式登记**：状态机只作用于 `currentUnadjusted`/`priorUnadjusted`
    两个**有派生值**的字段；AJE/RJE 改走单源读（`getRowFieldValue`）而非状态机。理由：派生聚合
    不产生调整额 ⇒ 其 `derived` 恒 0 ⇒ 状态机对它等价「有 stored 用 stored、否则 0」，与单源读
    同义，多接一层是死代码。tasks 原文「AJE/RJE 改走状态机」按此收口
  - _Requirements: 1.5, 1.6_

- [x] 15. UI：覆盖标记 + S4 冲突三值呈现 + 「恢复取数」
  - S2 标「已人工覆盖」；S4 同时呈现覆盖值 / 原派生值 / 现派生值，**不自动二选一**（P14）
  - 「恢复取数」只影响被点那一格，并在下次物化把该格写回派生值（P15）
  - 覆盖后 `mainCrossValidation` / `otherCrossValidation` 仍按覆盖值参与比对（需求 6.6）
  - ✅ `D4TabAdjudication.vue`：`el-tag`（S2「已人工覆盖」/ S4「覆盖·上游已变」danger）+ tooltip
    三值（覆盖值 / 原派生值 / 现派生值）+ 「恢复取数」`el-button` 按 `(rowKey, field)` 逐格；
    交叉验证读 `sections` 合并后的值故自动按覆盖值比对
  - ✅ P14 / P15 判据：`d4CellOverrideRender.spec.ts`（S4 三值同时出现在渲染输出 + 恢复取数只
    影响被点那一格 + 同行其余格与同列其他行不受影响）
  - _Requirements: 6.4, 6.5, 6.6_

- [x] 16. 本期 AJE/RJE 小计口径对齐 + D4-4 校验告警 + 清两处死代码
  - `buildSubtotalRow` 本期 AJE/RJE 改逐行汇总（与模板 `C12=SUM(C8:C11)` 同口径）——
    这是**唯一**与 Excel 一致的算法，不是口径二选一
  - 新增「小计逐行汇总 ≠ D4-4 汇总额」**校验告警**，与既有 `mainCrossValidation`/
    `otherCrossValidation`（小计 vs D4-2/D4-3）**同构**：computed 返回提示串、超容差才亮、
    指明差异、**不改任何一侧**（P17）。D4-4 仍是调整分录权威源，"D4-1 逐行填的调整 ≠ D4-4
    汇总"本身是一条要让审计师知道的事实，由他判断，不阻塞
  - **P16 必须读模板公式作第三边**，不得 HTML 与 OO 互比（两侧同错会自洽）
  - 清 `buildCrossSheetRow` 的 AJE/RJE 硬编码 `0`（改走状态机）与 `|| true` 死表达式，
    并使其上方那条注释与实现一致
  - ✅ `buildSubtotalRow` 本期 AJE/RJE 已改逐行汇总；`adjustmentTotalsValidation` computed 与
    `mainCrossValidation`/`otherCrossValidation` 同构（提示串 / 超容差才亮 / 不改任一侧 / 不阻塞）；
    `|| true` 死表达式已清、派生行 AJE/RJE 硬编码 0 已改走单源读、注释已与实现一致
  - ✅ 判据：`test_d4_1_subtotal_formula_caliber.py`（3 条，读模板 `C12`/`D12` 真实公式作第三边）
    + `d4AdjustmentTotalsValidation.spec.ts`（3 条，P17 告警三态）
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 17. P2 反读等值 + P3 formula_mask 不放宽
  - materialize 后 extract 与 projection 逐字段相等；48 格恒不产普通值键
  - ✅ `test_d4_1_materialize_extract_realchain.py` 承担 P2：新存储形态（金额随行落库）下
    `build_store_projection_d41` → 真物化 → 真提取，两区字段集合与值逐项相等
  - ✅ P3 本 spec 自带判据（不只依赖归档 spec）：断言 48 格 mask 规模不变、`FORMULA_MASK`
    覆盖格在新形态 projection 里恒不产普通值键、且提取产物里那些格不回流成受管值
  - _Requirements: 1.2, 1.3_

### 阶段 5：验收

- [x]* 18. 变异检验 + 真栈 Playwright + 证据登记
  - ✅ 变异检验：**12 项全 KILLED**（见上方变异检验登记表），逐项记录在
    `docs/operations/evidence/d4-store-contract-alignment/real-stack-probe-2026-09-23.md`
  - ✅ 真栈①的**端点层**已实测两轮（真库真端点，非 mock）。第二轮（证据文档 §六）在**全栈
    在跑**的状态下按正确层级（`data.projection.values`）复核了**最终 overlay 之后**的投影：

    | 受管区 | 最终受管格数 |
    |---|---|
    | `adjudication_main_rows/` | **21**（7 个派生行 × 3 格） |
    | `adjudication_other_rows/` | **16**（5 派生行 × 3 + 手工行） |
    | `other_revenue_check_rows/`（D4-35） | **32**（修复前 0） |
    | `d413_erp_check_fixed/` | **2**，值 = store 正文（修复前恒 `''`） |

    主营 7 行金额（`153431246.06` / `1528820416.32` / `89847600.46` / …）**正是用户报障时
    HTML 有、OO 里空的那 7 行**。⇒ 缺陷 A1 / B / C 在真栈上均已通达。
  - ✅ 顺带实证 Task 12 孤儿清理：`source='tb'` 且不在派生集又无覆盖的 `probeA` 已自动清掉，
    `source='manual'` 的 `probeB` 保留。
  - ✅ **推翻了一条此前登记错的结论**：原写「D4-35 端点最终 0 格，属既有 overlay 语义」——
    那是探针**读错响应层级**（投影体在 `data.projection`，不在 `data` 顶层）导致的误判。
    `overlay_store_on_baseline_projection` 实为**并集 + store 侧优先**，只丢「基线无该键且
    store 值为 None」的占位，**不会**滤掉 store 非空值。已在证据文档 §三 就地划掉 + §六 更正。
    教训：`store_field_count`(1648) 与 `field_count`(992) 的差值≠「store 被吞了多少业务值」，
    在没读到真实键集之前拿两个计数作差去推断数据丢失是没有依据的。
  - ✅ **真栈①浏览器层判据已写并真跑**：`e2e/d4-1-adjudication-oo-visibility.spec.ts`
    （`--workers=1`）。跑到的步骤：登录 ✅ → 取 projection 派生行 ✅ → 打开 D4-1 ✅ →
    **HTML 侧 7 行 label 全部在表格里可见** ✅ → 切「在线编辑」→ `store-projection` 200 ✅
    → `pending-mutations` 200 ✅ → **`materialize` 500 ×3** 🔴（OO canvas 断言未到达）
  - 🔴 **500 的响应体原文**：`excel_extract_identity_carrier_missing` ——
    「契约声明动态行的首张表 `sheet='d42-managed' table='revenue_detail_rows'`
    一个 row identity 都没反读到」。
  - ~~**失败面在 D4-2，不在本 spec 改动的 D4-1 两区 ⇒ 属另一范围，本 spec 不修**~~
    🔴 **这条结论已于 2026-09-24 第三轮复核推翻（证据文档 §八，§七 原文保留作审计轨迹）。
    两条都是错的**：
    * **(a) 文案里的 D4-2 是硬编码的首张动态表**：`excel_extract.py:1253`
      `first_sheet, first_table = dynamic_tables[0]` —— D4 契约的第 0 项恒为
      `('d42-managed','revenue_detail_rows')`，**无论哪个 binding 失败文案都报 D4-2**。
      单凭响应体断定失败面在 D4-2 没有依据。
    * **(b) 钩住载体门后，真正失败的 binding 是 D4-1 其他区**（`assert_identity_carriers_usable`
      收的是单个 inventory）：`sheet='营业收入审定表D4-1' table_ref='A14:X17' uuid_col='X'
      uuids=0 resolved_by=None empty_rows=4` ⇒ 即 `GT_D41_OTHER_ROWS`，**正是本 spec 改动的
      两区之一**。对照：同 binding 在未经 materialize 的 published substrate 上好的
      （逐 binding 复刻生产 `region.row_span` 口径，**36 个全 ok**）⇒ 零 UUID 是 materialize
      过程中产生的，不在 substrate 上。
    * **(c) A/B 对照实验证明由本 spec 触发**（同 substrate/contract/adapter，只差 store payload）：
      A 组含 `D4-1-rows`（main 7 / other 6）⇒ 🔴 上述错误；B 组摘掉 `D4-1-rows`（回到本 spec
      之前形态）⇒ ✅ **materialize OK `managed_field_count=1294`**。**A 红 B 绿** ⇒ 阻塞是
      Task 12/14「派生行入 store」的**直接下游后果**，**不是**「另一范围的既有缺陷」。
    * 机制（与观测一致，未逐行验证位移算术）：受管区要落的行数 > 模板 Table ref 覆盖行数 ⇒
      materialize 在**同一 sheet** 主营区插行 ⇒ 其他区数据被下推，但其他区 Table ref 仍停在
      `A14:X17` ⇒ 陈旧窗口里现在是主营区的行（UUID 在 W 列不在 X 列）⇒ X 列 4 行全空。
  - 📌 **缺陷所在层仍不是本 spec 的需求面**：「同 sheet 插行后 sibling 受管区 Excel Table ref
    未同步维护」属 materialize 行位移层，归 `excel-structural-row-insertion-and-shift-aware-verification`
    / `excel-workbook-wide-row-change-propagation` 两 spec。本 spec requirements 未覆盖 Table ref
    维护 ⇒ 本轮**不擅自修**，但按「**本 spec 触发的阻塞**」登记，不再说成「别人的 bug」。
  - 🔴 **顺带发现一条独立的可见性缺陷**：`excel_extract_identity_carrier_missing` 是
    domain error 却以 **500** 返回。`wp_sync_router.py` 自己的注释明写这类必须翻成
    fail-visible 4xx（否则「一路冒泡成 opaque 500…看不到中文根因」）。现状正是它警告的形态：
    中文根因在响应体里，但 HTTP 语义是 500 ⇒ 前端按"服务器内部错误"处理并重试 3 次。
  - ⛔ **真栈②（覆盖往返，需求 5.3）被阻塞**：OO 改派生行金额 → forcesave → 切回表格视图带
    「已人工覆盖」→ 再改 D4-2 进 S4 两值可见 —— 卡在上面的 materialize 500，**Table ref 维护
    修好后**才可跑（骨架可照 `e2e/g5-1-d4-unified-path.spec.ts` 的
    `asc_findCell`/`asc_insertInCell` + `[data-testid="wp-sync-host-forcesave"]` 范式）

  - ── **2026-09-24 第三轮复核（全栈在跑）** —— 证据文档新增 §八，append-only 不改 §一~§七 ──
  - ✅ **已声明产物核对属实**（不直接采信本文件的声称）：证据文档存在且含变异检验 + 端点层两轮
    实测；`e2e/d4-1-adjudication-oo-visibility.spec.ts` 存在（283 行真判据，`--list` 可正常收集
    1 test）；`task18-browser-materialize-failure.json` 存在且含三次 500 完整响应体。
  - ⚠️ **一处登记不全（如实记录）**：本文件变异检验表 **12 项**，而证据文档 §四 只逐项登记 **7 项**
    （P1 / P4 / P8 / P8-前端 / P9 / P12 / P16），缺 **P2 / P3 / P13 / P14 / P15** 五项。这五项的
    变异与打红条数写在本文件表里（有文件+条数）⇒ 判为**登记位置不全，非证据缺失**；已在 §8.1 登记。
  - ✅ **回归复核实跑数字与声称逐项一致**（不是"声称"，是本轮实跑）：

    | 面 | 实跑 | 对比声称 |
    |---|---|---|
    | 后端 11 文件（本 spec 5 新增 + 归档 spec D4-1 既有 5 + 门禁自测） | **73 passed / 0 failed** | 73 ✅ 一致 |
    | CI 门禁 `check_store_item_ids_fully_wired.py` | **exit 0**，46 item 收敛 | ✅ 一致 |
    | 前端零回归集 13 文件 | **13 files / 239 passed / 0 failed** | 239 ✅ 一致 |

  - 🔴 另：宽选 `-k "d4_1 or d4_store or d4_35 or d413 or store_item"` 跑 `tests/workpaper_sync/`
    得 **156 passed / 1 failed**。唯一失败 =
    `test_task42_h1_grouped_dynamic_pilot_pg.py::test_disposal_store_item_is_empty_across_the_whole_database`
    —— **H1 固定资产处置 pilot** 的「真实库数据出现即打红」哨兵（断言 `H1-8-rows` 全库 0 行，
    现测到 wp `c71b7c54…` 有 51B）。与 D4 无关、与本 spec 改动文件无交集，不计入本 spec 分母。
  - 🔴 **真栈 Playwright 第三轮（`--workers=1`）：500 复现，步骤 1/2 仍绿**。环境实测后端 9980
    healthy、前端 3030 在跑、`audit-onlyoffice` 容器 healthy（Up 36h）。登录 ✅ → projection 取到
    非零派生行（未 skip）✅ → **HTML 侧 7 行 label 全可见**（`labelsMissingInHtml == []`）✅ →
    `store-projection` 200 ✅ → `pending-mutations` 200 ✅ → **`materialize` 500 ×3** 🔴 →
    OO canvas 逐值断言 ⛔ 未到达。失败 JSON 已刷新（`captured_at=2026-09-23T23:07:43.171Z`）。
  - ⛔ **需求 5.2（OO canvas 逐值对齐）与需求 5.3（覆盖往返）本轮仍未实测** ——
    **代码已改但未实测，卡 materialize Table ref 维护缺陷**（非环境缺失：环境本轮全在跑）。
    解除条件：受管区插行时同步更新**同 sheet 其他受管区**的 Excel Table ref（或 materialize 侧
    改为按 ref 重算而非信任陈旧 ref）。修好后本判据会自动跑到 canvas 断言。
  - 📌 **本条判据的价值本轮进一步兑现**：它不只是把报障拆成三段（HTML ✅ / projection ✅ /
    materialize 🔴），本轮还**推翻了一条错误归因** —— 若没有这条真栈判据 + 载体门 trace +
    A/B 对照，本 spec 会带着「阻塞属别人范围」的错误结论收口。
  - 🔴 **可观测性缺陷（独立于上面，本轮新增一条同类事实）**：`excel_extract_identity_carrier_missing`
    是 domain error 却以 **500** 返回（`wp_sync_router.py` 自己的注释明写这类必须翻成 fail-visible
    4xx），**且其文案还会指错对象**（恒报 `dynamic_tables[0]`，见上 (a)）。两者叠加 ⇒ 排障者被
    导向完全无关的底稿。不在本 spec Requirements 内 ⇒ 登记为遗留项，不擅自修。
  - 📌 本条判据**不是空转**：它把「切 OO 后看不到数据」拆成三段可归因事实 —— HTML 侧行在 ✅、
    projection 侧值在 ✅、materialize 挂了 🔴（~~且根因在 D4-2~~ 🔴 **已推翻：根因在 D4-1 其他区的
    陈旧 Table ref，见上 2026-09-24 第三轮 (a)(b)(c)**）。此前三段混在一起，无法判断本 spec 修没修好。
    判据留在仓库，~~D4-2 侧~~ **Table ref 维护**修好后会自动转绿并完成需求 5.2 的 canvas 逐值对齐。
  - 📌 D4-1 的模式切换条是 `.d4-tab-adjudication .sync-mode-bar`，**不是** D4-2 那套
    `.d4-mode-toolbar` —— 照抄 g5-1-d4 范式会找不到元素（本次已踩）。
  - ⚠️ `--workers=1` 串行；证据落 `docs/operations/evidence/`；`getDiagnostics` 全绿不作为验收
  - _Requirements: 5.1, 5.2, 5.3_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3"], "rationale": "红判据与零回归基线先行，三者互不依赖可并行；P1/P9 现状必红是后续'修好了'的唯一归因依据" },
    { "wave": 2, "tasks": ["4"], "rationale": "provider 单一口径是两个方向改造的共同输入，必须先于 5/6" },
    { "wave": 3, "tasks": ["5", "6"], "rationale": "出/回两方向各自改走单一口径，互不依赖可并行；任务 5 使 P9 转绿" },
    { "wave": 4, "tasks": ["7"], "rationale": "CI 卡点要在两方向都接完之后才有可断言的稳定形态，否则守卫自身会红" },
    { "wave": 5, "tasks": ["8"], "rationale": "共享件序列化形态是单源读与双写的前置；P10 快照零变化是它的验收门" },
    { "wave": 6, "tasks": ["9", "10"], "rationale": "单源读与双写都依赖任务 8 的形态，二者可并行（读侧/写侧互不调用）" },
    { "wave": 7, "tasks": ["11"], "rationale": "回方向真链需要读侧已行对象优先（任务 9）+ 写侧已落行对象（任务 10），否则真链恒红且红的不是被测行为" },
    { "wave": 8, "tasks": ["12"], "rationale": "derivedSnapshot 的写入依赖任务 8 的序列化形态与任务 10 的双写接线" },
    { "wave": 9, "tasks": ["13"], "rationale": "四态解析必须在 derivedSnapshot 真的落库之后才有第三个量可读；P12 反证式判据在本波先写" },
    { "wave": 10, "tasks": ["14", "16"], "rationale": "sections 逐格合并依赖任务 13 的状态解析；小计口径对齐与它互不依赖可并行（前者改行值来源、后者改小计算法）" },
    { "wave": 11, "tasks": ["15"], "rationale": "UI 呈现依赖任务 13 的状态与任务 14 的合并结果，且需求 6.6 的交叉验证告警要基于合并后的值" },
    { "wave": 12, "tasks": ["17"], "rationale": "反读等值与 formula_mask 判据要在派生行已进 store（12）且行值来源已确定（14）之后才有意义" },
    { "wave": 13, "tasks": ["18"], "rationale": "变异检验与真栈实测收口，需全部行为已落地" }
  ],
  "blocking": {
    "1": "P1 未先打红 ⇒ 阶段 3/4 完成后无法区分'修好了'与'判据本来不会红'（需求 5.1）",
    "2": "P9 未先打红 ⇒ 任务 5 的转绿不可归因",
    "3": "P10 快照未取 ⇒ 任务 8 改共享件时对 D1/J1 的零回归无对照（需求 4.3）",
    "4": "all_store_item_ids() 未落 ⇒ 任务 5/6/7 无单一口径可取，缺陷 C 无法收敛",
    "8": "共享件未落 valueFields ⇒ 任务 9/10/12 全部无形态可依",
    "12": "derivedSnapshot 未落库 ⇒ 任务 13 的四态解析缺第三个量，只能退回被需求 6.1 明令禁止的 'stored ≠ derived' 判法",
    "13": "四态解析未落 ⇒ 任务 14/15 无状态可消费"
  }
}
```

## 实施进度实证（2026-09-23 校准）

此前 18 条全标 `[ ]`，而代码与判据已实际落地 —— 逐符号 grep + 实跑核对后校准为 **17/18**，
并补齐了当时缺的三处判据（T11 物化段 / T17 的 P2+P3 / P13~P15）。下表是**实跑数字**，不是声称：

| 面 | 范围 | 结果 |
|---|---|---|
| 后端 D4-1/D4-35 判据全量 | 本 spec 新增 5 文件 + 归档 spec 的 D4-1 既有 6 文件（contract / store_roundtrip / dual_region / sibling_binding / footer_anchor / 门禁自测） | ✅ **73 passed / 0 failed** |
| 前端零回归集 | 全部 13 个依赖被改模块（`useD4Adjudication` / `dynamicAdjudicationRows` / `useK2Adjudication` / `D4TabAdjudication.vue`）的测试文件 | ✅ **239 passed / 0 failed** |
| CI 门禁 | `python backend/scripts/check/check_store_item_ids_fully_wired.py` | ✅ exit 0，46 item 全部经 `all_store_item_ids()` 收敛 |
| diagnostics | 改动的源文件 + 新判据文件 | ✅ 0 |

🔴 **前端全量 `vitest run composables/__tests__/` 有 11 个文件 / 56 条既存失败**（L2/L4 披露接线、
K 系附注模板结构、G7 列对齐、F3/F5 集成、D4 inspection 页硬编码科目码等）。**归因已核**：
`git status` 显示本 spec 只改了 4 个源文件，那 11 个失败文件**一个都不在其中**，故与本 spec 无关，
不计入本 spec 分母（同需求 3.3 对 `tests/workpaper_sync/` 既存失败的处理口径）。

**唯一未完成项 = 任务 18 的浏览器层真栈**（Playwright ×3 + 覆盖往返），~~卡 `start-dev.bat` 环境~~，
按铁律标 `[ ]*` 而非 `[x]`。端点层真栈与变异检验已完成并留证。

> 🔴 **2026-09-24 就地更正（不改上方原文，仅加指针）**：「卡 `start-dev.bat` 环境」已不成立 ——
> 第三轮复核时全栈在跑（后端 9980 healthy / 前端 3030 / OnlyOffice healthy），真栈判据真跑到了
> materialize。真实卡点 = **materialize 同 sheet 插行后 sibling 受管区 Excel Table ref 未同步维护**，
> 且该阻塞经 A/B 对照实验证明**由本 spec 的派生行入 store 触发**（不是「另一范围的既有缺陷」）。
> 详见任务 18 正文与证据文档 §八。

### 🐛 补判据时抓到并修复的两个真 bug（选项 b 的覆盖在运行时会自我擦除）

补 P13/P14/P15 时红判据当场打红 4 条，暴露 `useD4Adjudication` 两处缺陷 —— **13 条纯函数
四态判据全绿而生产行为是坏的**，因为那些判据只喂 `resolveCellState(stored, snap, derived)`
三个入参，从不跑写这三个量的同步器。spec 的 Testing Strategy 预言过这件事
（「手写必漏 S4，而 S4 是唯一会静默丢数据的那一态」），这次是它兑现。

1. **`syncDerivedRowsIntoStore` 把显示值当派生值写回 snap** ⇒ 覆盖态下 `row.currentUnadjusted`
   等于 `stored`，于是 snap ← stored ⇒ `stored ≠ snap` 当场不再成立 ⇒ **覆盖标记在下一个
   tick 自我擦除**。现象：用户在 OO 改的数能显示，但「已人工覆盖」永不出现。
   修复：新增 `_pureDerived(row, field)`，覆盖态取 `cellOverrides[field].derived`。
2. **snap 无条件跟随最新派生值** ⇒ 上游一变 snap 立刻追上 derived ⇒ `snap ≠ derived` 永不成立
   ⇒ **S4 不可达**，需求 6.4 要的「覆盖值 / 原派生值 / 现派生值」三值里中间那个永久丢失。
   修复：snap 与 stored 都只在 `!overridden` 时跟随；覆盖态下 snap **冻结**在覆盖发生时的派生值。

连带修 `restoreDerivedValue` 同源问题（取显示值 ⇒ 恢复取数把覆盖值又写回一遍 = 空操作）。

**两处均为「纯函数判据覆盖不到的时序/数据来源缺陷」，不是四态算法本身错。**

### 变异检验登记（需求 5.1）

| 判据 | 变异 | 打红 |
|---|---|---|
| P1 | 行清单剥金额键 | KILLED |
| P2 | binding 漏写该列（物化产物该格清空） | KILLED（extract `MISSING` vs projection 12345.67） |
| P3 | E8 审定数 `=SUM(B8:D8)` 被普通值写死 | KILLED |
| P4 / T11 物化段 | merge 不回写行对象顶层（缺陷 A2） | KILLED（HTML 读回 12345.67 ≠ OO 改后 98765.43） |
| P8 | `all_store_item_ids()` 去掉 D4-35 | KILLED（门禁 exit 1，精确报漏项） |
| P8-前端 | `serializeRows` 金额不落行对象 | KILLED（2 条） |
| P9 | 单一口径去掉 D4-35 / D4-13 | KILLED |
| P12 | `overridden` 改用 `stored ≠ derived` 错法 | KILLED（5 条） |
| P13 | `_writeIfChanged` 去掉幂等短路 | KILLED（**9 条**） |
| P14 | snap 无条件跟随派生值（S4 不可达） | KILLED（2 条） |
| P15 | `_pureDerived` 在恢复取数里取显示值 | KILLED（1 条，"当场写对"那条） |
| P16 | 小计改跨表引用 | KILLED |

后端三项（P2 / P3 / T11 物化段）另跑过 baseline 对照：未变异时全 PASS，红不是恒红。

## Notes

### 已裁决

- ~~**O1 待拍板**~~ → **2026-09-23 用户裁决：选项 b**（OO 改了算，store 为准，HTML 标
  「已人工覆盖」）。任务 12 已重写，并新增任务 13~16；requirements 新增 1.5/1.6 + 需求 6 全节；
  design 新增裁决 D4 的逐格四态状态机 + Property 7/11~15。
  **已显式登记的代价**：`sections` 从「整行跳过」改为「逐格合并」；原「显示口径一字不改」
  不再成立（Property 7 改成条件式）；并连带触发裁决 D6。

### 已裁决（原 O4，2026-09-23 用户澄清后收口，不再阻塞）

- **小计口径 vs「恒等于 D4-4」不是二选一 —— 前者是算法、后者是校验，分属两层**：
  * 算法层：小计按模板 `C12=SUM(C8:C11)` **逐行汇总**，这是唯一与 Excel 一致的算法，无分叉。
  * 校验层：「小计是否等于 D4-4 汇总额」作为一条**跨底稿校验告警**（任务 16），与既有
    `mainCrossValidation`/`otherCrossValidation` 同构 —— 超容差亮提示、指明差异、不改任何一侧、
    不阻塞。若审计要求恒等于 D4-4，那是审计师看到告警后去调平，而不是系统替他盖掉某侧。
  * 之前把它写成「改口径 or 阻塞」的二选一是表述错误：口径本就该按 Excel，校验独立存在。

### 不在本 spec 范围

- **同一轮会话的另一报障已单独修完**：「切回表格视图后无法再切在线编辑」根因在
  `utils/http.ts` 请求去重键插入/删除不对称（POST 键带 body 指纹入、不带指纹删 ⇒ 键泄漏
  5 分钟，同 body POST 在发出前即被 abort）。**已根治 + 真栈 6/6 验收**，判据
  `audit-platform/frontend/src/utils/__tests__/httpDedupe.postKeySymmetry.spec.ts`
  （变异检验 2 条打红）。此处登记仅为防止后来者把两件事混成一件。
- **O2**：per-field item 的物理删除（本 spec 只做双写，不删）。
- **O3**：其余 12 张审定表接桥（K2-1 随共享层自动受益）。
- **O5**：人工覆盖的审计留痕（谁/何时覆盖）。本 spec 的 `overridden` 是现算态、不落库。
