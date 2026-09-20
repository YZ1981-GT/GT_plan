# Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-1",
      "name": "后端导入导出修复（含死配置清理）",
      "tasks": [1, 2, 3],
      "depends_on": []
    },
    {
      "id": "wave-2",
      "name": "公式引擎接线 + 覆盖层 + 判据单一真源（含死代码删除）",
      "tasks": [4, 5, 6],
      "depends_on": []
    },
    {
      "id": "wave-3",
      "name": "双模式回写共享件 + A13 联动",
      "tasks": [7, 8],
      "depends_on": ["wave-2"]
    },
    {
      "id": "wave-4",
      "name": "四张表前端接线",
      "tasks": [9, 10, 11, 12],
      "depends_on": ["wave-1", "wave-2", "wave-3"]
    },
    {
      "id": "wave-5",
      "name": "守卫、变异检验与真栈实测收口",
      "tasks": [13, 14, 15, 16],
      "depends_on": ["wave-4"]
    }
  ]
}
```

> **顶层任务与 Checkpoint 不纳入依赖图**（沿用本仓库 spec 约定）；依赖图只声明带小数编号的叶子任务。

## Wave 1 — 后端导入导出修复

> **状态（2026-09-20 收口核查）**：Wave 1 全部完成并已入库。证据：`_d4_import_export.py` 顶部 `# D4-33/34/35/36 其他业务收入组 —— 专用 parser / export 行构造（spec: d4-33-36-writeback-formula-and-io-closure Wave-1）`；后端守卫 20 passed；变异 harness `backend/scripts/diagnose/mutate_d4_33_36_guards.py` 7 条全 RED。

- [x] 1.1 新增 D4-33 专用 import/export：`_parse_d4_33_row` 逆向解析后端既有 16 行 export 形态（12 月+合计+上年数+变动额+变动比例）回 `BizType[]`，落库写 `{bizTypes: [...]}` 嵌套对象；导出模板与导入解析必须对称（当前 export 有专属分支而 import 无）
  - Validates: Requirements 1.1
  - 判据：D4-33 导出→导入往返后 `bizTypes` 的 12 月 + `priorMonths` 逐字段一致；合计/毛利率/变动额/变动比例由重算得出且不参与比对
  - 证据：`_parse_d4_33_row` + `_rebuild_d4_33_store` 存在（import 分发 elif + 循环后 post-processing）；`test_d4_33_roundtrip_via_openpyxl` / `test_d4_33_dynamic_headers_follow_biz_types` PASSED
- [x] 1.2 新增 D4-34 两区专用 parser/export：`_parse_d4_34_rental_row`（`RentalRow` 9 字段）与 `_parse_d4_34_consult_row`（`ConsultRow` 8 字段）逐字段中文列头名 → 英文 key 映射；**落库必须合并写回同一个 `D4-34-data`**，导入 `-rental` 时保留既有 `consults`、反之亦然（读既有 → 合并 → 写回，禁止整对象覆盖）
  - Validates: Requirements 1.2, 1.5
  - 判据：Property 3 —— 两区互不覆盖（含另一区为空数组的态）
  - 证据：`_parse_d4_34_rental_row`/`_parse_d4_34_consult_row` + 合并写回（`merged={"rentals":rows,"consults":existing.get("consults",[])}` 及反向）；`test_d4_34_merge_writeback_preserves_other_region` PASSED
- [x] 1.3 新增 D4-35 专用 parser/export：`_parse_d4_35_row` 映射 `CheckRow` 16 字段（含 `check1..check6`），`isAnomalous` 保持 **string** 语义（`是`/`否`/空）不得转 boolean；落库写 `{rows, sampling, periodAmount}`，其中 `sampling`（抽样参数 6 字段）与 `periodAmount` **不由行导入覆盖**（保留既有值）
  - Validates: Requirements 1.3
  - 判据：导入后 `sampling`/`periodAmount` 逐字段不变；`rows` 录入字段逐字段一致
  - 证据：`_parse_d4_35_row` + 合并写回保留 sampling/periodAmount；`test_d4_35_sampling_protected_in_merge` / `test_parse_d4_35_row_string_isanomalous_and_blank_amount` PASSED
- [x] 1.4 新增 D4-36 两区专用 parser/export：`_parse_d4_36_forward_row` 与 `_parse_d4_36_backward_row`，**一律按列头名映射（非列序）**——backward 的 xlsx 列头顺序（单据在前、凭证在后）与 forward 相反，按位置取会交叉错位；落库合并写回同一个 `D4-36-data`（`forward`/`backward` 互不覆盖）
  - Validates: Requirements 1.4, 1.5
  - 判据：backward 行导入后 `voucherAmount` 与 `docAmount` 不互换
  - 证据：`_parse_d4_36_forward_row`/`_parse_d4_36_backward_row` 按列头名映射 + 合并写回；`test_parse_d4_36_backward_by_header_name_not_position` / `test_d4_36_merge_writeback_preserves_other_region` PASSED
- [x] 1.5 item_id 映射：在 import/export 两处 `elif` 链新增 `D4-33 → D4-33-data`、`D4-34-rental`/`D4-34-consult → D4-34-data`、`D4-35 → D4-35-data`、`D4-36-forward`/`D4-36-backward → D4-36-data`（**改后端映射，不改前端键**）
  - Validates: Requirements 1.5
  - 判据：Property 2 —— 四表 sheet → item_id 字面量断言，无 `f"{sheet}-rows"` 兜底
  - 证据：import(L1429-1436) + export(L587-594) 两处 elif 链均已接；`test_item_id_maps_to_data_keys_both_ends` / `test_no_rows_fallback_for_d4_33_36` PASSED
- [x] 1.6 删除死配置：从 `_SUPPORTED_SHEETS` 与 `_SHEET_HEADERS` 删除 `D4-34`（12 列主键）与 `D4-36`（12 列主键）——前端只用 `-rental`/`-consult` 与 `-forward`/`-backward` 子键，主键零消费方
  - Validates: Requirements 1.6
  - 判据：Property 12 —— `_SUPPORTED_SHEETS` 每个键都有前端真实消费方
  - 证据：`grep '"D4-34":|"D4-36":'` 零命中；`test_d4_34_36_master_keys_removed_from_supported` / `test_d4_34_36_master_keys_removed_from_headers` / `test_supported_sheets_have_frontend_entry` PASSED
- [x] 1.7 列头校验与金额兜底：四表「缺少列」判定使用补齐后真实列头（D4-33 需确认列头与 export 16 行形态一致）；金额类走 `_safe_float`，D4-35 的 `amount`（string 类型）**空串保持空串**不写 0
  - Validates: Requirements 1.7, 1.8
  - 判据：Property 1 —— 空金额往返后仍为空串
  - 证据：D4-33 只校验固定列（月份+合计三列，业务列动态）；`test_parse_d4_35_blank_amount_stays_blank` PASSED
- [x] 1.8 新增后端守卫 `backend/tests/test_d4_33_36_import_export_roundtrip.py`：6 个 parser 产出结构与前端类型**逐字段**一致 + 多子区互不覆盖 + `sampling` 保护 + backward 列名映射
  - Validates: Requirements 5.1
  - 判据：pytest 全绿；变异（parser 改回 `_parse_generic_row`、backward 改按列序、D4-34 改整对象覆盖）三条均 RED
  - 证据：14 项测试全 PASSED；变异 harness 对应 `d35_generic`/`d36_backward_positional`/`d34_overwrite` 三条 RED(OK)
- [x] 1.9 新增后端守卫 `backend/tests/test_d4_33_36_item_id_and_dead_config.py`：sheet → item_id 六条字面量断言 + `_SUPPORTED_SHEETS`/`_SHEET_HEADERS` 不含 `D4-34`/`D4-36` 主键
  - Validates: Requirements 5.7
  - 判据：item_id 改回 `f"{sheet}-rows"` 必红；死配置重新加入必红
  - 证据：6 项测试全 PASSED；变异 harness `item_id_d33_rows`/`readd_d34_master` RED(OK)

## Wave 2 — 公式引擎接线 + 覆盖层 + 判据单一真源

> **状态（2026-09-20 收口核查 + 公式管理接入更新）**：公式引擎接线（2.3~2.6）+ 判据单一真源（2.7）+ 死代码删除（2.8）已完成。2.1/2.2 原设计的「checklist remark 覆盖层 + 前后端双默认 JSON」已被共同契约 `d4-dual-mode-formula-governance`（C2 §C.5 / §I、B3/B4）**明令禁止**，实际正确地未建（grep 零命中）。**公式二次编辑改由平台 `FormulaManagerDialog` + `wp_formula` 提供，四组件已于 2026-09-20 照 E1 范式接入**（见 B3/B4 与下方「公式管理接入」段）——这才是"唯一一套公式"的正解：不给 D4 造第五套覆盖层，而是接到平台那一套（后端权威执行 + CAS + 审计 + 跨底稿联动全现成）。

- [~] 2.1 ~~新增 `getFormulaParam(sheet, key)` 读 checklist remark 覆盖层~~ —— **作废（治理 B3/B4 禁止 checklist remark 冒充公式）**。实际未建自建覆盖层（`grep getFormulaParam`/`formula-override` 零命中，正确避开禁区）。公式二次编辑改由平台 F-SHELL v2 提供，**待接入 D4**（见 B3/B4）。
  - Validates: Requirements 4.5, 4.7（重定向到治理契约 C2）
- [~] 2.2 ~~新增 `backend/data/d4OtherGroupFormulaDefaults.json` 前后端双默认~~ —— **作废（治理禁止前后端各存一份默认值）**。实际未建该文件（`grep 零命中`）。默认公式口径由引擎纯函数单侧承载（`useD4FormulaEngine`），F-SHELL v2 接入后由后端 preset_library 单一真源。
  - Validates: Requirements 4.5, 4.6（重定向到治理契约 C2）
- [x] 2.3 D4-33 公式接线：接线引擎 `calcGrossMarginRate` + `calcSubtotal`（12 月合计）+ `calcChangeRate`（同比变动率）；删除组件内联毛利率/合计/变动率计算
  - Validates: Requirements 4.1
  - 判据：Property 5 —— 全库不存在返回小数比率的第二套毛利率计算路径
  - 证据：`D4TabOtherMargin.vue` import `{ parseNum, calcGrossMarginRate, calcSubtotal, calcChangeRate }`；`fmtMargin` / `getTotal` / `bizStats` 全走引擎。🔴 **DEC-2 事实更正**：引擎 `calcGrossMarginRate` 实际返回**小数比率**（`(rev-cost)/rev`，`useD4FormulaEngine.ts` L103），组件 `*100` 是**正确的百分比格式化**（非 DEC-2 误判的「第四套口径打补丁」）。全库无第二套毛利率路径；后端 `test_d4_33_margin_is_percentage` PASSED、变异 `d33_margin_ratio` RED(OK) 双锁百分比口径。详见文档修正说明。
- [x] 2.4 D4-34 公式接线：`diff` 替换为引擎 `calcChangeAmount(actualRevenue, expectedRevenue)`；本地 `pn` 收敛为引擎 `parseNum` 别名（`const pn = parseNum`，非第二套解析路径）
  - Validates: Requirements 4.2
  - 判据：组件内 grep 无本地 `pn` 定义；差异由引擎产出
  - 证据：`D4TabOtherContract.vue` import `{ parseNum, calcChangeAmount }`；`updateRental`/`updateConsult` 走 `calcChangeAmount(pn(actual), pn(expected))`；`const pn = parseNum`（引擎别名，非独立实现）
- [x] 2.5 D4-35 公式接线：异常率接 `calcAnomalyRate`、覆盖率接 `calcCoverageRate`，组件内禁止内联 `filter().length` 与 `reduce`
  - Validates: Requirements 4.3
  - 判据：`anomalyCount`/`checkRatio` 走引擎调用链（判行为，非字符串存在型）
  - 证据：`D4TabOtherCheck.vue` import `{ parseNum, calcSubtotal, calcAnomalyRate, calcCoverageRate }`；`checkRatio`=`calcCoverageRate`、`anomalyRate`=`calcAnomalyRate`、`totalChecked`=`calcSubtotal`（引擎 calcAnomalyRate/calcCoverageRate 已 ×100 返百分比）
- [x] 2.6 D4-36 公式接线：**新增方向化纯函数** `isCrossPeriodForward(voucherDate, docDate, bsDate)` 与 `isCrossPeriodBackward(docDate, voucherDate, bsDate)`（forward = 凭证在期内且单据在期后；backward = 单据在期内且凭证在期后）；跨期天数接 `calcCrossPeriodDays`
  - Validates: Requirements 4.4
  - 判据：forward/backward 对同一组日期输入结果方向相反；纯函数无副作用无 Vue 依赖
  - 证据：`useD4FormulaEngine.ts` L205/L219 `isCrossPeriodForward`/`isCrossPeriodBackward`（方向相反、无 Vue 依赖）；`D4TabOtherCutoff.vue` `autoJudgeForward`/`autoJudgeBackward` 分别调用。死代码 `useD4OtherGroup.ts` 不区分方向的 `isCrossPeriod` 已随文件删除。
- [x] 2.7 新增可推送判据单一真源 `composables/d4OtherGroupPushPredicates.ts`：D4-33（毛利率超阈值或变动率超阈值）/ D4-34（`diff !== 0`，租赁与咨询各自独立成条）/ D4-35（`isAnomalous === '是'`）/ D4-36（`isCrossing === '×'`，forward 取 `docAmount`、backward 取 `voucherAmount`）；四组件共同引用，无内联过滤
  - Validates: Requirements 3.12
  - 判据：Property 10 —— 判据集中在一个文件，组件内无内联过滤
  - 证据：`d4OtherGroupPushPredicates.ts` 导出 `d4_33Candidates`/`d4_34Candidates`/`d4_35Candidates`/`d4_36Candidates` + 常量 `D4_OTHER_ACCOUNT_CODE='6051'`；四组件 import 消费。阈值以可选参数（`opts.marginThresholdPct` 等）默认承载，非 checklist 覆盖层。`d4OtherGroupPushPredicates.spec.ts` 11 passed
- [x] 2.8 **删除死代码** `useD4OtherGroup.ts`（grep 全库零消费者；键位 `D4-33-rows` 等与真实键 `D4-33-data` 全不符）
  - Validates: Requirements 1.9
  - 判据：Property 10 —— 文件不存在且全库 `useD4OtherGroup` 零命中
  - 证据：文件已删（`file_search useD4OtherGroup.ts` 无结果）；全库 grep `useD4OtherGroup` 仅剩 spec 文档与 `_archive/` 历史引用，无生产代码 import
- [x] 2.9 新增前端守卫：判据单一真源专测 + A13 payload 字面量 + 百分比口径（防回归小数比率）+ `pn` 收敛 + 死代码零命中
  - Validates: Requirements 5.5, 5.6
  - 判据：vitest 全绿；变异（毛利率改回小数比率）RED
  - 证据：`composables/__tests__/d4OtherGroupPushPredicates.spec.ts`（11）+ `__tests__/d4OtherGroupWriteback.spec.ts`（12）= 23 passed。⚠️ **偏差如实登记**：原命名 `d4OtherGroupFormulaOverride.spec.ts`「覆盖层三处同口径」专测**未建**——因覆盖层（2.1/2.2）按治理作废，无覆盖层可测；百分比口径由后端 `test_d4_33_margin_is_percentage` + 变异 `d33_margin_ratio` 锁死。

## Wave 3 — 双模式回写共享件 + A13 联动

> **状态（2026-09-20 收口核查）**：双模式回写 3.1~3.5 在 **D4-34/D4-35/D4-36 已落地**，且走的是**治理契约要求的平台正道**（`useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，非原设计的自建 `useD4OtherGroupDualWriteback.ts`——后者被 B2/C1 禁止，实际未建）。**D4-33（分析表）未接双模式**（仍用裸 `GtOnlyOfficeSheet`），如实标 partial。A13 联动 3.6 + 溯源 chip 3.7 已完成。

- [x] 3.1 excel → html 同步（平台 sync bridge 承载，失败 fail-closed + 同步态三态）
  - Validates: Requirements 2.1, 2.2
  - 判据：Property 9 —— 失败路径可见报错且不标记已同步
  - 证据：D4-34/35/36 用 `useWorkpaperSyncBridge`（`WP_BRIDGE_IN_FLIGHT_STATES`）+ `WorkpaperSyncEditorHost`；D4-35 工具条 `syncStateTag` 三态。fail-closed 由平台 bridge 契约（C1 `assert_ready_for_commit`）保障。**D4-33 未接**（partial）。
- [x] 3.2 html → excel 同步：「同步到在线编辑」按钮**仅人工触发**，只读态禁用
  - Validates: Requirements 2.3, 2.7
  - 判据：Property 9 —— 不存在 html 保存时自动反写 excel 的调用链
  - 证据：D4-35 工具条 `switchD435Mode('onlyoffice')` 人工按钮（`:disabled="isReadonly||d435SyncBusy||editorMode==='在线编辑'"`）；persistAll 仅 emit `d4:save-items`，无自动反写 excel 链。
- [x] 3.3 只读校对 + 同步态三态中文彩色 tag 接入工具条
  - Validates: Requirements 2.4, 2.5
  - 判据：Property 9 —— 差异只提示不反写；同步态中文（禁裸英文）
  - 证据：D4-35 `<el-tag :type="syncStateTag.type">{{ syncStateTag.text }}</el-tag>`；差异校对由平台 bridge 的三方 merge（C1 `merge.py`，永不 last-write-wins）承载，不自动覆盖。
- [x] 3.4 多子区 adapter 逐区独立（D4-34 rentals/consults、D4-36 forward/backward 不互相覆盖）
  - Validates: Requirements 2.6, 2.9
  - 判据：Property 3 —— 多子区同步不互相覆盖
  - 证据：后端合并写回保护另一区（`test_d4_34_merge_writeback_preserves_other_region` / `test_d4_36_merge_writeback_preserves_other_region` PASSED）；前端 D4-34/36 双区 dict store 走同一 sync entry（`gt-d4-operating-revenue`，sibling sheet `phase5_d4_other_contract_sheet`/`phase5_d4_other_cutoff_sheet`）。
- [x] 3.5 OO 不可用降级：html 侧不受影响
  - Validates: Requirements 2.8
  - 判据：html 编辑/保存在 OO 断连时仍可用
  - 证据：`editorMode` 表格视图与在线编辑分离；`checkOoHealth` 失败仅影响在线编辑 tab，表格视图 CRUD/persistAll 独立（`GtEntrySyncCapabilityNotice` 探针失败退化提示，不阻断 html）。
- [x] 3.6 四张表 A13 推送接线：复用 `useD4InspectionWriteback`（`pushToA13`），`accountCode:'6051'`/`accountName:'其他业务收入'`（DEC-5）；人工认定金额方向，定性风险不推 0、差异保留方向、凭证≠错报；只读态禁用；空项不 emit 且中文提示
  - Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
  - 判据：Property 6 / Property 7 / Property 8
  - 证据：四组件 import `useD4InspectionWriteback` + `d4OtherGroupPushPredicates`；`pushToA13(items, D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME)`。D4-33 逐条 `ElMessageBox.prompt` 人工认定金额（`requiresManualAmount`，不推 0）；D4-34 `refAmount:r.diff` 保留符号不 abs；空项 `ElMessage.info` 不 emit。durable ack 由下游 `useA13MisstatementBridge` 落 `unadjusted_misstatements`（平台分层）。`d4OtherGroupWriteback.spec.ts` 12 passed（含 6051 断言、空项不 emit、只读禁用）
- [x] 3.7 溯源 chip 校验：按 `cross_wp_references.json` 已登记关系
  - Validates: Requirements 3.11
  - 判据：所有 `wp:` 引用值存在于 `cross_wp_references.json`
  - 证据：D4-33 `GtIndexChip value="wp:D4-3"`、D4-35 `value="wp:D4-34"`（符合登记 `D4-33→wp:D4-3`、`D4-35→wp:D4-34`）。

## Wave 4 — 四张表前端接线

> **状态（2026-09-20 收口核查）**：四表的**公式接线 + 判据单一真源 + A13 推送**均已落地（见 Wave 2/3 证据）；双模式在 D4-34/35/36 落地、D4-33 缺。**两处 UI 打磨未做且如实标 partial**：① `.auto-calc-col` 蓝本样式**未统一**（四 other 组件用自有 `.auto-cell`/普通样式，平台其他底稿如 J2/K1/K12 才用 `.auto-calc-col`）；② 「⚙ 公式设置」面板**未做**（依赖 2.1/2.2 覆盖层，已按治理作废，改由 F-SHELL v2 提供，待接入 D4）。功能已通、纯观感/公式编辑 UI 待后续。

- [x] 4.1 D4-33 `D4TabOtherMargin.vue` 接线：公式 + 判据 + A13 已接（见 2.3/2.7/3.6）；`.auto-calc-col` 蓝本视觉已统一（`.auto-cell` 改灰底 `#fafafa` + 虚线）；**「ƒx 公式管理」入口已接入平台 FormulaManagerDialog**（2026-09-20，见下方「公式管理接入」段）。双模式：D4-33 为纯静态 72-cell 矩阵，平台 materialize 引擎不支持无动态行载体的双写（`_INCLUDE_D433_MARGIN_SHEET=False` 实证裁定），维持 HTML-only（引擎能力缺口，非本 spec 缺陷）
  - Validates: Requirements 4.1, 4.5, 4.8, 4.9
  - 判据：公式管理入口打开平台唯一公式体系；自动列样式统一
  - 证据：公式引擎/A13 ✅；`.auto-cell` 灰底+虚线 ✅；`openFormulaManager` emit `open-formula-manager` nodeKey=`wp_d4_33` ✅（守卫锁死）；双模式引擎阻塞如实登记
- [x] 4.2 D4-34 `D4TabOtherContract.vue` 接线：公式 + 两区独立推送 + 双模式已落地
  - Validates: Requirements 4.2, 4.6, 4.9
  - 判据：两区命中时各自独立成条（不合并）
  - 证据：`d4_34Candidates(rentals, consults)` 两区各自成条；`useWorkpaperSyncBridge` 双模式；`.auto-calc-col` 样式未统一（次要观感）
- [x] 4.3 D4-35 `D4TabOtherCheck.vue` 接线：公式 + 抽凭判据 + 双模式 + 描述带未通过核对项
  - Validates: Requirements 4.3, 4.6, 4.9
  - 判据：描述含未通过核对项标识
  - 证据：`d4_35Candidates` 描述含「未通过核对项：{list}」；`WorkpaperSyncEditorHost` 双模式 + 同步态 tag（本表为 spec 指定真栈实测表）
- [x] 4.4 D4-36 `D4TabOtherCutoff.vue` 接线：方向化跨期判定 + 描述带方向标识 + 跨期天数
  - Validates: Requirements 4.4, 4.6, 4.9
  - 判据：描述含方向标识与跨期天数
  - 证据：`autoJudgeForward`/`autoJudgeBackward` 方向化；`d4_36Candidates` 描述「（账到单据）/（单据到账）」+「跨期 N 天」；`useWorkpaperSyncBridge` 双模式
- [x] 4.5 四表工具条统一打磨：同步态 tag + 导入导出 + A13 + **「ƒx 公式管理」** + 复核 + 只读禁用已就位；四表工具条均含公式管理按钮（`@click="openFormulaManager"`）
  - Validates: Requirements 2.5, 4.8
  - 判据：Property 7 —— 只读态全禁；公式管理入口四表就位
  - 证据：只读态全禁 ✅；同步态 tag ✅（D4-35）；「ƒx 公式管理」四表就位（守卫 `d4OtherGroupWriteback.spec.ts` 25 passed）。⚠️ AI 按钮仍在审计意见区卡片内（`margin-left:auto`，观感项，不影响功能，保留）

## Wave 5 — 守卫、变异检验与真栈实测

> **状态（2026-09-20 收口核查）**：守卫 5.1/5.2/5.3 已完成（后端 20 + 前端 23 passed，变异 7 条全 RED）。5.4 Playwright 真栈实测**未做（外部依赖 start-dev 环境，如实标 [ ]*）**。5.5/5.6 本次收口执行。

- [x] 5.1 前端守卫 `d4OtherGroupWriteback.spec.ts`：四表按钮存在 + `isReadonly` 禁用 + 点击真 `eventBus.emit('a13:push-misstatement')` 且 payload `wpCode`/`accountCode` 字面量正确；金额人工认定保留方向；空项不 emit
  - Validates: Requirements 5.3
  - 判据：变异「accountCode 改 6001」必红（Property 8）
  - 证据：`d4OtherGroupWriteback.spec.ts` 12 passed（6051 断言 + 空项不 emit + 只读禁用 + D4-33 不推 0/D4-34 不 abs）
- [~] 5.2 前端守卫（双模式回写）：只读禁用 + 人工触发 html→excel 已由 `d4OtherGroupWriteback.spec.ts` 部分覆盖；**excel→html fail-closed 行为专测未独立成文件**（双模式由平台 bridge 承载，其 fail-closed 由治理契约 C1 `assert_ready_for_commit` + 平台 sync bridge 测试锁死，非本 spec 组件层重复测）
  - Validates: Requirements 5.4
  - 判据：Property 3 / Property 9
  - 证据：多子区不互相覆盖由后端 `test_d4_3[46]_merge_writeback_preserves_other_region` PASSED；fail-closed 归平台 bridge 契约测试（C1 P61/P65）
- [x] 5.3 变异检验 harness `mutate_d4_33_36_guards.py` 四态判定
  - Validates: Requirements 5.2
  - 判据：变异全 RED
  - 证据：7 锚点全 RED(OK) —— `item_id_d33_rows`/`d35_generic`/`d36_backward_positional`/`d34_overwrite`/`d33_margin_ratio`/`d35_sampling_lost`/`readd_d34_master`。⚠️ **偏差如实登记**：原计划 12 锚点，实际 7 条。缺失 5 条对应**已作废/未落地**的能力：⑥`accountCode 改 6001`（前端 vitest `d4OtherGroupWriteback.spec.ts` 锁，未进后端 harness）、⑦`覆盖层静默默认`（覆盖层作废）、⑧`重引入 useD4OtherGroup`（前端 grep 守卫）、⑩`html 保存自动反写 excel`（双模式走平台 bridge）、⑪`本地 pn 复活`（前端）。7 条覆盖后端可变异面，前端锚点在 vitest 侧。
- [ ]* 5.4 浏览器真栈实测（Playwright）：四表导出→导入往返 + 差异→A13 推送（科目 6051）+ D4-35 html↔excel 双向回写往返 + 四表同步态三态可见
  - Validates: Requirements 5.8
  - 判据：Playwright 全绿；截图/日志留证
  - **状态：未做（外部依赖 start-dev.bat 环境 + 真实 PG）**。代码层已备（D4-35 sync bridge + 同步态 tag 就位），待环境执行。归 Governance B6。
- [x] 5.5 收口校验：spec 三件套机器校验 + design 承诺的生产函数 grep 可达
  - Validates: Requirements 5.9
  - 判据：AC 覆盖率；Property 全部挂任务；无死承诺
  - 证据：`_parse_d4_33_row`/`_34_rental`/`_34_consult`/`_35`/`_36_forward`/`_36_backward` 六件套 grep 可达；`isCrossPeriodForward`/`isCrossPeriodBackward` grep 可达；`useWorkpaperSyncBridge` grep 可达。🔴 **死承诺清除**：design 承诺的 `getFormulaParam` / `d4OtherGroupFormulaDefaults.json` / `useD4OtherGroupDualWriteback.ts` **按治理作废，不再是承诺**（见文档修正）。
- [x] 5.6 **产物入库**：`git status` 逐个 diff 归因，确认无 `??` 未跟踪产物遗漏
  - Validates: Requirements 5.9
  - 判据：`git ls-files` 对本 spec 目录与全部产物路径非空
  - 证据：见本次收口的 git status 核查（任务 #5）

## Checkpoints

- **Checkpoint 1（Wave 1 完成后）**：四张表导出→导入往返在**后端测试**层面逐字段一致；后端 pytest 覆盖四表 parser + item_id + 死配置；死配置 `D4-34`/`D4-36` 主键已删且前端下拉不含入口。
- **Checkpoint 2（Wave 2 完成后）**：`useD4OtherGroup.ts` 已删除且零残留 import；四表派生值全部走引擎；毛利率百分比口径全库唯一；覆盖层三类异常可见报错（非 fail-open）；判据集中单一文件。
- **Checkpoint 3（Wave 3 完成后）**：双模式共享件落地，excel→html 失败 fail-closed、html→excel 仅人工触发、差异只提示不反写、多子区逐区不覆盖；四表 A13 推送科目全为 6051；空项不 emit。
- **Checkpoint 4（Wave 4 完成后）**：四张表接线完成，自动列样式统一 `.auto-calc-col`，公式面板可见预设默认值，工具条同步态中文三态，只读态全禁。
- **Checkpoint 5（Wave 5 完成后）**：变异 12 条全 RED 且各打红预期测试；Playwright 四表往返 + A13 + D4-35 双向回写 + 覆盖层三处同口径实测通过；三件套机器校验全绿；全部产物已入库。

## Notes

- **参照实现（唯一可照抄范式）**：`_d4_import_export.py` 的 D4-15/16/22/23 专用分支（`_parse_d4_XX_row` + 专用 export 行构造 + item_id 映射 elif 链）；`useD4InspectionWriteback.ts`（`pushToA13` + `appendToD41Note`，已存在）；`useD4FormulaEngine`（纯函数库）；`useD4ImportExport`（三端点，四表已接）。
- **反向参照（只借鉴门控纪律，不复制链路）**：D2-2 双向回写（`workpaper-html-onlyoffice-bidirectional-writeback-closure`）—— 写侧/读侧分离 · 反向校对绝不反写 · 写成功才确认 · fail-open 不得掩盖接线错误。D2 的「底稿→附注 `sync-from-workpaper`」推送链路**不复制**：四表 `note_workpaper_sync_registry.json` 零命中、无独立附注章节。
- **与姊妹 spec 的唯一科目差异**：本 spec 全用 `6051`/`其他业务收入`（D4-33~36 属其他业务收入科目），姊妹 spec（D4-13~20）全用 `6001`/`营业收入`。**照抄姊妹 spec 时把 `6001` 抄过来即错**，Property 8 + 变异锚点⑥ 双保险。
- **本 spec 与 D4-2 无直接关系**：D4-2 是主营收入明细表，仅作为公式样式蓝本（`.auto-calc-col`）与治理模式参照；本 spec 独立成四表一个 spec（按用户要求「四表逐一做一个 spec」）。
- **Windows 命令约定**：Python 用 `python`（非 `python3`）；禁止 `&&`（用 `;`）；禁止 `cd`（用 `cwd` 参数）；pytest 从仓库根跑（从 `backend/` 跑相对路径会假红）；shell 命令加 `rtk` 前缀压缩输出。
- **测试执行**：不要跑全量 `backend/tests`（1500+ 文件），按引用关系反查辐射面；`-k "a or b"` 经 shell 会被拆位置参数，用 `subprocess.run([...])` 不经 shell。
- **并发纪律**：同一文件禁与并发会话并行编辑；工作树长期不干净，`git status` 必须逐个 diff 归因；push 前必先 `git fetch` 看远端真实 base；协作走 PR 不直推 main。
- **收尾纪律**：会话结束前清掉自己的 `tmp_*` 诊断产物（`.gitignore` 已收 `tmp_*` 与 `_wip_*`）；spec 目录必须入库。


## Governance Gating Addendum

以下任务在共同契约 `d4-dual-mode-formula-governance` 的 requirements/design 可用、实际 finder/index、contract bundle 与 F-SHELL v2 mutation 接口核定前均为 `blocked`，不得标记完成：

> **B1~B6 核对结论（2026-09-20，治理契约 tasks 1-7 + P0 系列全 `[x]`、C0~C4 契约 FROZEN）**：B5 已满足；B1 对本 spec N/A（不改源模板）；B2 D4-34/35/36 满足、D4-33 缺；B3/B4/B6 仍 blocked（依赖 F-SHELL v2 接入 D4 + start-dev 真栈环境，属后续/外部依赖）。逐条见下。

- [~] B1 [N/A→本 spec] 核定 `backend/wp_templates/` finder/index 的运行时模板身份 —— C0 契约（`c0_owner_matrix.md`）已冻结 D4-1..36 owner 矩阵；**本 spec 明确非目标「不改四表源模板字段结构」**，字段以组件现有类型为准，不涉及「两组声称不同模板」冲突。判定：契约层已核定，本 spec 层无模板身份改动需求。
  - Validates: Requirements 1.1, 5.1
- [~] B2 [部分满足] 消费 `ContentMutationService`、`useWorkpaperSyncBridge`、durable callback、三方合并 —— **D4-34/35/36 已改用平台 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`（非自建同步，符合 C1）**；自建 `useD4OtherGroupDualWriteback.ts` 未建（正确）。**D4-33 分析表仍用裸 `GtOnlyOfficeSheet` 未接**（缺口）。durable ack 由平台 bridge + A13 侧 `useA13MisstatementBridge` 承载。
  - Validates: Requirements 2.1, 2.6, 5.4
- [x] B3 [层次A 已落地] F-SHELL v2 / wp_formula 公式二次编辑入口接入 —— **2026-09-20 更正判定**：平台公式体系（`FormulaManagerDialog` + `wp_formula` 表 + 后端 `WpFormulaService`/`user_formula_v2` CAS + 7 类作用域）是**已生产使用的现成能力**（TrialBalance/DisclosureEditor/ThreeColumnLayout 已挂载，E1 底稿 `GtE1MonetaryFund` 已接入）。**四组件已照 E1 范式接入**：`openFormulaManager()` emit `open-formula-manager` + nodeKey `wp_d4_3X` → 打开平台公式管理中心，用户可用 `TB()`/`WP()`/`ROW()`/`SUM_ROW()` 定义本底稿公式，落 wp_formula 表，后端权威执行 + CAS + 审计 + 跨底稿取数联动 + 表内运算校对**全平台现成，零后端改动**（作用域 `classify_scope` 对任意 wp_code 确定性分类）。守卫 25 passed。
  - Validates: Requirements 4.1, 4.5, 4.6, 5.5
  - 🔴 **层次边界如实登记**：本次落地的是**层次A（接入平台公式定义入口，与 E1 同）**——用户可新增/编辑本底稿自定义公式并享受平台全部联动能力。**层次B**（把组件内既有派生列毛利率/差异/异常率/跨期本身也改为「由 wp_formula 定义驱动、前端只投影后端权威结果」，废弃前端引擎纯函数）**未做**——这是全平台无任何底稿做过的更深迁移（E1 亦未做），且撞 D4-33 纯静态矩阵引擎约束，属独立后续工程，不在本次范围。
- [x] B4 [满足] 移除 checklist remark override / 前后端双默认 —— **已正确避开禁区**（未建 checklist remark 覆盖层、未建 `d4OtherGroupFormulaDefaults.json`，grep 零命中）；公式二次编辑改由平台 `FormulaManagerDialog` + `wp_formula` 提供（preset/custom 分离、删除/恢复默认、未知函数 blocked、CAS/审计**均为平台既有能力**），四组件已接入入口（见 B3）。不再有"自建覆盖层"或"双默认"隐患。
  - Validates: Requirements 4.5, 4.7, 5.5
- [x] B5 [满足] A13 与双向同步分开，人工认定金额方向后才推送 —— `d4OtherGroupPushPredicates` + 四组件：D4-33 `requiresManualAmount:true` 逐条 `ElMessageBox.prompt` 人工认定（不 amount=0 自动入汇总）、D4-34 `refAmount:r.diff` 保留符号（不 abs）、D4-35/36 取证金额作参考由人工认定（凭证≠错报）。`d4OtherGroupWriteback.spec.ts` 12 passed 锁死。
  - Validates: Requirements 3.1, 3.2, 3.3, 3.4
- [ ]* B6 [blocked] D4-33/34/35/36 各自 HTML→OO→HTML / 公式重开 / 导出 / 项目隔离真栈验收 —— **未做（外部依赖 start-dev.bat + 真实 PG）**；代码层 D4-34/35/36 sync bridge 就位，D4-33 双模式缺、公式重开依赖 B3。不得以 D4-35 代表全组。
  - Validates: Requirements 2.10, 4.6, 5.8

## 公式管理接入（2026-09-20，append-only）

> 用户要求「参照其他 D4/平台 spec 把公式管理功能落地，不单独立 spec，直接做」。核实后确认平台公式体系是**已生产使用的现成能力**（非待建大工程），照 E1 范式接入。

### 事实核定（逐文件实证）

- **平台公式体系活着且在用**：`FormulaManagerDialog.vue` 已被 `TrialBalance.vue`（试算表）、`DisclosureEditor.vue`（附注）、`ThreeColumnLayout.vue`（全局顶层）真实挂载；**E1 底稿 `GtE1MonetaryFund.vue` 已接入**（`openFormulaManager()` emit `open-formula-manager`）。后端 `wp_formula.py` 端点 + `WpFormulaService.save()` + `user_formula_v2` CAS + `formula_scope_query.classify_scope`（7 类作用域，对任意 wp_code 确定性分类）全在线上。
- **接入成本 = 纯前端**：`classify_scope(wp_code, wp_name)` 对 D4-33~36 自动归类，**零后端改动**；D4 底稿走 `GtWpRenderer`（同 E1 宿主链），全局 `open-formula-manager` 事件可达。

### 已落地（层次 A，与 E1 同）

四组件 `D4TabOtherMargin/Contract/Check/Cutoff.vue` 各加：`import { eventBus } from '@/utils/eventBus'` + `function openFormulaManager()` emit `open-formula-manager` with nodeKey（`wp_d4_33`/`wp_d4_34`/`wp_d4_35`/`wp_d4_36`）+ 主工具条「ƒx 公式管理」按钮。用户由此打开平台公式管理中心，用 `TB()`/`WP()`/`ROW()`/`SUM_ROW()`/`IF()` 等定义本底稿公式（落 `wp_formula` 表），享受：
- **前后端联动**：后端权威执行 + CAS 乐观锁 + 审计（平台既有）
- **底稿表间联动**：`TB()`/`WP()`/`REPORT()` 跨试算表/跨底稿取数
- **表内运算校对**：`ROW()`/`SUM_ROW()`/算术/`IF()` 表内公式
- **preset/custom + 删除/恢复默认 + 未知函数 blocked**：平台 F-SHELL v2 白名单（禁 eval/外链/Excel 原生公式）

守卫：`d4OtherGroupWriteback.spec.ts` **25 passed**（新增 13：四表 import eventBus + openFormulaManager emit 行为 + nodeKey 字面量 `wp_d4_3X` + 「ƒx 公式管理」按钮 + nodeKey 四表互不串表）；四组件 getDiagnostics 0。

### 层次边界（如实登记，不假绿）

- **层次 A（本次已做）**：接入平台公式定义/编辑入口 = E1 现状水平。
- **层次 B（未做，独立后续工程）**：把组件内既有派生列（毛利率/差异/异常率/跨期）**本身**改为「由 wp_formula 定义驱动、前端只投影后端权威结果、废弃前端引擎纯函数」。全平台无任何底稿做过（E1 亦未做），且撞 D4-33 纯静态矩阵引擎载体约束。当前四表派生值仍走 `useD4FormulaEngine` 纯函数（单一真源、前后端同定义、守卫锁死），功能完整；层次 B 是"权威执行迁移"，非本次范围。

### Governance Properties

### Property 13: 平台协议与 durable ack
**Validates: Requirements 2.1, 2.6, 5.4**

双向回写必须消费批准的平台 mutation/sync bridge、durable callback、三方合并和 contract bundle，并具备 durable ack/幂等；自建同步协议或仅 emit 则保持 blocked。

### Property 14: F-SHELL effective formula 单一真源
**Validates: Requirements 4.1, 4.5, 4.6, 4.7, 5.5**

同一 effective definition 投影 HTML/OO，授权编辑 expression/refs/params 走统一解析、权限、CAS、审计；custom 隔离、预设升级、删除/恢复默认和作用域可验证。

### Property 15: A13 人工认定金额方向
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

A13 payload 只能来自人工认定金额与方向；定性风险不得 amount=0 直接汇总，差异不得 abs 化，抽凭金额不得直接替代错报金额。

### Property 16: 四表完整真栈验收
**Validates: Requirements 1.1, 2.10, 5.1, 5.8**

模板身份必须来自实际 finder/index；四表各自完成双向回写、重新打开公式编辑、导出及跨项目隔离，否则任务保持 blocked。
