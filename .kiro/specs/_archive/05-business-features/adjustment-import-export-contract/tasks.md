# Implementation Plan

## Overview

按 design 的 5 波交付：Wave 0（中央 4 项确定性缺陷，独立可发布可回退）→ Wave 1（底稿 Sheet_Spec 三重对齐 `item_id`+`storage_field`+`field_keys`，含 `K2-3` 补注册）→ Wave 2（K12-3 前端迁 JSON 数组）→ Wave 3（契约清单双侧守卫）→ Wave 4（Round_Trip 实测 + 零回归门）。

全程 additive：不改富模板列集合、不改 `syncToCentral`/`sync-from-workpaper` 幂等链、不改 `recalc` 聚合口径、不改前端 Storage_Key 与行模型（K12-3 例外，用户已定）。

后端服务只 flush 不 commit（router 统一 commit）；权限/自校验置于 `try` 外避免被吞成 500；PBT 用 hypothesis `max_examples=5`。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6"], "depends_on": [0] },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "depends_on": [1] },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3"], "depends_on": [1, 2] },
    { "wave": 4, "tasks": ["5.1", "5.2"], "depends_on": [0, 1, 2, 3] }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 中央通道 4 项确定性缺陷（独立可发布）

- [x] 1.1 characterization 基线锁定既有正确路径
  - 为 `mode=append` 中央导入、富模板 `export-template` 列集合、`_is_example_row` 对内置示例的判定、7 张无漂移 sheet（`K1-4/K6-3/K9-3/K11-3/K13-3/I5-3/I6-3`）的导入导出产物与落库键写 characterization 测试
  - 作为 Property 2 / Property 13 的逐字节对照基线；本波后续改动不得使其变色
  - _Requirements: 8.1, 8.5_
  - _Properties: Property 2, Property 13_

- [x] 1.2 `mode` 真传递 + overwrite by-key 覆盖
  - `_dispatch_import` 的 `adjustments` 分支把 `mode` 传入 `_import_adjustments`；后者新增 `mode` 形参（默认 `append` 保持现状）
  - `overwrite` 按 design 决策 3 实现：对文件内出现的每个 `adjustment_no` 查同 project+year 既有分录组 → 可覆盖则软删旧组再建新组；`approved` / 活跃协作 / `origin='workpaper'` 撞号则跳过并累加 `skipped` + 可读原因
  - 非法 `mode` 值降级为 `append` 不抛 500；单编号失败计入 `failed_rows` 并继续其余编号（不整批回滚）
  - 覆盖后复用既有删除路径触发试算表重算，不新造 recalc 调用
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - _Properties: Property 1, Property 2, Property 3_

- [x] 1.3 示例行判定收紧为全字段相等
  - `_is_example_row` 判定改「与某个内置示例行的全部可比字段逐字相等」（保留前 6 行窗口与 `_norm` 数值规范化）
  - **实施发现（超出 design 决策 4 的单示例假设）**：富模板 AJE/RJE 各写 2 行示例共 4 行，
    只有 AJE 第 1 行与 `TEMPLATE_COLUMNS` 单示例一致 → 单示例全等会让另 3 行示例变脏数据（违反 Property 5 硬门）。
    故新增 `TEMPLATE_EXAMPLE_ROWS` 内置示例行登记表，全等判定对「任一候选示例行」成立即跳过
  - **hypothesis 抓到的漏洞**：示例金额 0 被读取端读成 ""，若空值视为"不可比"，用户在该格填真实金额仍被吞
    → `_example_comparable_pairs`：数值列示例为空按 0 参与比较（公式自动填充列仍不可比，保 Property 5）
  - 两处调用点（`validate_import_file` / `parse_import_data`）：被跳过示例行以独立口径计数，不计入 `failed`；
    形状 = `example_skipped_count`（`parse_import_data` 新增可选 `stats` 出参 + 端点/校验响应**仅在非空时附带**，
    与 Task 1.2 的 `skipped_rows` 同款策略，`skipped_count ≡ len(skipped_rows)` 不变）
  - characterization 同步翻转（basis 改变）：`test_a_partially_matching_real_data_row_*` → `False`、
    阈值基线用例改锁严格判定 + 登记表覆盖；`test_a_builtin_example_rows_are_skipped` 保持 `True` 未动
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - _Properties: Property 4, Property 5_

- [x] 1.4 汇总导出补「类型」列 + 解析器 sheet 名兜底
  - `_write_adj_sheet` 的 `headers` 在「编号」后插入「类型」并逐行写入已接收的 `adj_type`（与富模板列序一致，7→8 列）；
    **三条写行路径全部同步列偏移**（分录组带 line_items / 组无明细行的汇总行 / 扁平模式兼容）+ 列宽 A~H
  - adjustments 解析：缺「类型」列且 sheet 名含 `AJE`/`RJE`（含 `审计调整`/`重分类`）关键词时按 sheet 名为该 sheet 全部行注入类型；
    列存在则以列为准并对冲突行给出提示（parse 走 `stats`、validate 走 `warnings`，均不阻断）；两者都无 → 保留既有"缺少必填列: 类型"错误
  - **实施发现（超出 design 决策 5）**：`validate_import_file` 不做表头别名规范化，
    而汇总导出用「科目编码/科目名称」（parse 侧才有 `科目名称→二级科目名称` 别名）→ 光补「类型」列仍会被校验判「缺少必填列: 二级科目名称」，
    Property 6 不成立。故把别名表/候选 sheet 判定/类型推断三者抽为模块级单一真源
    （`_ADJ_HEADER_ALIASES` / `adjustment_sheet_candidates` / `infer_adjustment_type_from_sheet_name`），validate 与 parse 共用
  - **validate（只选首个匹配 sheet）与 parse（合并多 sheet）一致性**：类型兜底仅在**全部**候选 sheet 都可判别时才免除「缺类型」错误，
    避免「校验过了但解析某 sheet 仍缺类型」（用 `test_p7_validate_and_parse_agree_on_multi_sheet_fallback` 锁定）
  - `stats` 新增 `type_inferred_from_sheet` / `type_source_conflicts`，与 Task 1.3 的 `example_skipped_count` 同款「非空才带」；
    导入端点同款附带并追加可读提示
  - characterization 同步翻转（basis 改变）：`test_c_export_summary_headers_currently_lack_type_column`
    → `test_c_export_summary_headers_include_type_column`（8 列 + 断言旧 7 列列头不得回退）；
    C 组富模板列头断言（`test_c_rich_template_*`）一字未动
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Properties: Property 6, Property 7, Property 8_

- [x] 1.5 模板下载入口统一为项目感知富模板
  - 导入弹窗内「下载导入模板」改指向 `GET /adjustments/export-template`；无项目上下文时降级通用裸模板并提示"无科目下拉，请核对科目编码/名称"
  - 验证两入口模板必填列集合互相兼容（旧手上已填模板仍可导入）
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 1.6 Wave 0 PBT + 回归
  - Property 1（overwrite 幂等：同文件导入 N 次 ≡ 1 次）/ P2（append 逐字节不变）/ P3（覆盖范围安全：workpaper-origin·approved·活跃协作不被动且在 skipped 可见）/ P4（示例行判定单调）/ P5（内置示例仍被跳过）/ P6（汇总导出可被导入接受）/ P7（类型来源优先级）/ P8（导出→导回业务等价）
  - 跑 `adjustments` / `import_templates` / `trial_balance` 相关既有测试全量回归，1.1 基线不得变色
  - **核对发现的唯一真缺口（已补）**：R1.6（覆盖后触发试算表重算链路）不在 Property 1-8 任一条的
    Validates 内，且无用例显式守卫 —— 若实现改成裸 SQL `UPDATE adjustments SET is_deleted` 直接软删，
    落库结果看似相同但**不发 `ADJUSTMENT_DELETED`、不触发重算**，`trial_balance` 会残留被覆盖分录的影响。
    补 `test_overwrite_replace_goes_through_service_delete_entry`（spy 断言覆盖调
    `AdjustmentService.delete_entry(被覆盖组)` + `db.updates` 只有编号钉住 UPDATE 无裸软删）
    与 `test_overwrite_skip_does_not_delete_anything`（跳过路径不得触发删除）
  - 门结果：spec 四文件 115 passed / `adjustments`+`adjustment_sync`+`adjustment_detail_account_code`+`trial_balance` 68 passed
    / 前端 `src/components/import` 10 passed / `test_xlsx_calamine_equivalence` 11 passed（`import_template_service` 读取路径）
  - _Requirements: 9.1, 9.2, 9.3, 9.6, 8.1, 8.5, 1.6_
  - _Properties: Property 1, Property 2, Property 3, Property 4, Property 5, Property 6, Property 7, Property 8_

- [x] 2. Wave 1 — 底稿 Sheet_Spec 三重对齐

- [x] 2.1 新建契约清单 `backend/data/adjustment_ie_contract.json`
  - 按 design 施工表登记每张调整 sheet 的 `item_id` / `storage_field` / `field_keys`（前端行模型字段名），含 `exempt` 段（登记显式豁免 + 原因）
  - 实施前用 grep 复核前端各 tab 的 `ITEM_PREFIX` / `itemId` / 行模型字段当前真实值（并发会话可能已改），清单以核实结果为准不照抄 design
  - 本任务只建数据文件，守卫在 Wave 3
  - _Requirements: 5.1, 5.2, 7.1, 7.4_

- [x] 2.2 对齐 K3-3 / K4-3 / K5-3 / K7-3
  - 四张按清单改 `item_id`（`KX-3-adj-entries`，**K5-3 为 `K5-3-entries` 无 adj**）+ 显式 `storage_field: "remark"` + 重写 `headers`/`field_keys`
  - K5-3 金额键对齐前端 `debit`/`credit`；K7-3 列结构对齐 `reportItem`/`noteItem`/`indexRef`；K3-3/K4-3 去掉前端不存在的 `noteRef`/`voucherNo`、补前端字段（K4-3 的 `entryNo`/`offsetAccount`/`source`、两者的 `preparedBy`）
  - 落地列数：K3-3 10→9 列、K4-3 10→12 列、K5-3 10→8 列（无 remark 列）、K7-3 10→10 列（列集合换血）
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Properties: Property 9, Property 10_

- [x] 2.3 对齐 K8-3（双列 + category 语义）
  - 消除后端 `description`（调整事项说明）+ `summary`（摘要）双列与前端单 `summary` 的错位（10→9 列，「调整事项说明」列直接绑 `summary`）
  - `item_id` → `K8-3-adj-entries` + `storage_field: "remark"`；保留前端 `remark ?? conclusion` 双读兼容不回退
  - **实测纠正 design 施工表**：后端 `_K8_3_KEYS` 本就含 `category` 且无 `entryType`，枚举（报表调整/账项调整/其他）两侧一致 → 「entryType→category」是无操作项，K8-3 唯一真差异就是 description/summary 双列
  - _Requirements: 5.1, 5.2, 5.4_
  - _Properties: Property 9, Property 10_

- [x] 2.4 新增 K2-3 Sheet_Spec（借贷科目分列，不同构）
  - `_K2_SPECS` 新增 `K2-3` 条目：`item_id: "K2-3-adj-entries"` + `storage_field: "remark"` + `headers`/`field_keys` 对齐前端 `seq/entryType/summary/debitAccount/debitAmount/creditAccount/creditAmount/preparedBy`
  - 不得照抄 K3-3 结构（K2-3 是借贷科目分列，与其余 6 张不同构）；`debitAccount`/`creditAccount` 是文本，已核实不在数值白名单内
  - _Requirements: 5.1, 5.2, 5.5_
  - _Properties: Property 9, Property 10, Property 11_

- [x] 2.5 数值字段白名单补齐 —— **实测为 no-op（无需改动）**
  - 逐一实测 `is_numeric_field_key`：本波新增/改动的金额键 `debit`/`credit`（显式集合内）、`debitAmount`/`creditAmount`（`"Amount" in key` 命中）、`seq`（显式集合）全部已为 `True`；
    新增文本键 `entryNo`/`offsetAccount`/`preparedBy`/`source`/`indexRef`/`reportItem`/`noteItem`/`debitAccount`/`creditAccount` 全部为 `False`（正确不进数值白名单）
  - 故 `_cycle_import_export_common.is_numeric_field_key` 一字未改；该行为由 Round_Trip（数值列往返为 `float`、文本列为 `str`）持续守卫
  - _Requirements: 5.4_
  - _Properties: Property 9_

- [x] 2.7 修 K1-4 / K6-3 / I5-3 / I6-3 的 `storage_field`（Task 1.1 新发现）
  - 四张 `item_id` 正确但未声明 `storage_field` → 取工厂默认 `conclusion`，而前端读写 `remark`（第三种 Orphan_Key）
  - 各加 `"storage_field": "remark"`（或给对应 router 调用加 `storage_field="remark"`，与 K11 现有做法一致）；`item_id`/`headers`/`field_keys` 一律不动
  - 同步更新 `test_adjustment_ie_characterization.py` 的 `_EXPECTED_EFFECTIVE_STORAGE_FIELD`（basis 改变，非放宽断言）
  - _Requirements: 5.1, 5.4_
  - _Properties: Property 9, Property 13_

- [x] 2.6 Wave 1 Round_Trip + 属性
  - 对 2.2/2.3/2.4 的 6 张 sheet（K2-3/K3-3/K4-3/K5-3/K7-3/K8-3）各做一次 Round_Trip：
    导出模板 → 按列头填一行 → 导入 → 断言**落库 `item_id` == 前端持久化键 且 INSERT 写的是前端读取列（`remark`）**，
    并逐字段核对往返值（数值列为 `float`、文本列为 `str`）；`ok=True` 不作为通过依据
  - 追加「错表/缺列必须被拒且不写库」用例（防静默导入空数据）
  - Property 9（三方键一致，**遍历清单** + 清单必须覆盖全部登记 sheet）/ P10（`frontend_row_model − frontend_extra_fields` 必被 `field_keys` 覆盖）/ P13（K9-3·K11-3·K13-3 保持 aligned 不退化，逐字节基线在 characterization）
  - 新增 `backend/tests/test_adjustment_ie_wave1_alignment.py`（82 passed / 4 skipped = K12-3 待 Wave 2）；
    `test_adjustment_ie_characterization.py` 的 `_EXPECTED_EFFECTIVE_STORAGE_FIELD` 4 张由 `conclusion` → `remark`（basis 改变，非放宽断言；`item_id`/`headers`/`field_keys` 断言未动，54 passed）
  - 契约清单 `backend/data/adjustment_ie_contract.json` 的 `backend_current` / `status` 已按实测同步（Wave 1 十张 → `aligned`）
  - _Requirements: 5.6, 5.7, 9.4, 9.5_
  - _Properties: Property 9, Property 10, Property 13_

- [x] 3. Wave 2 — K12-3 存储结构收敛（前端迁 JSON 数组）

- [x] 3.1 前端 `useK12Adjustment` 迁 JSON 数组
  - 新增导出常量 `K12_ADJ_ROWS_KEY = 'K12-3-rows'`；`_persistEntries` 只写该单键（`remark`，`K12AdjustmentEntry[]` JSON），
    `_triggerSave`/`_triggerSaveAll` 全部委托它（不再逐字段写 8 个 per-field 键）；`saveAndPublish` 同款单键 `saveBatch`
  - `restoreEntries` 优先解析 JSON（含 `{rows:[...]}` 包裹兼容 + `_normalizeEntry` 归一：导入产物的字符串 `index`/小写 `type`/缺省字段）；
    为空时回退 `_restoreLegacyEntries()` per-field 扫描重建（历史数据不丢），重建后首次保存自然收敛为 JSON
  - JSON 解析失败 → 回退 per-field 重建 + `console.warn`，不清空用户数据；**显式空数组 `[]` 视为用户已清空，不回退旧数据**；旧 per-field 键不主动删除
  - _Requirements: 6.1, 6.2_
  - _Properties: Property 12_

- [x] 3.2 后端 K12-3 Sheet_Spec 对齐
  - `item_id` 保持 `K12-3-rows` + 显式 `storage_field: "remark"`；`headers`/`field_keys` 10→9 列对齐前端行模型
    `index/type/description/accountCode/accountName/debitAmount/creditAmount/refIndex/remark`
    （去掉前端不存在的 `category`/`reportItem`/`noteItem`/`summary`/`indexRef` 错位列，索引列绑 `refIndex`）
  - `index` 不在数值白名单（按文本导入），由前端 `_normalizeEntry` 的 `Number(r.index) || i+1` 归一，不改全局白名单避免波及其它 sheet
  - _Requirements: 6.1, 6.3, 5.2_
  - _Properties: Property 9, Property 10_

- [x] 3.3 K12-3 属性 + Round_Trip
  - 前端 `useK12Adjustment.spec.ts`（9 passed）覆盖 Property 12：只写 JSON 键 / per-field-only 历史读取一致（含借贷平衡可算）/
    重建后收敛为 JSON 且旧键保留 / JSON 与 per-field 并存以 JSON 为准 / 解析失败回退不清空 / 导入产物归一 / 显式空数组不回退 /
    `saveAndPublish` 单键 / 删行重编号整体重写
  - 后端 Round_Trip：K12-3 纳入 `test_adjustment_ie_wave1_alignment.py` 的 `_WAVE1_ROUNDTRIP`（导出模板→填→导入→
    断言落库 `K12-3-rows` 的 `remark` 列 + 字段逐字对应），Property 9/10 对 K12-3 由 skip 转真跑（88 passed）
  - _Requirements: 6.2, 6.3, 5.6_
  - _Properties: Property 12_

- [x] 4. Wave 3 — 契约守卫（双侧对同一清单）

- [x] 4.1 后端契约守卫
  - 新增 `backend/tests/test_adjustment_ie_contract_guard.py`：遍历**全部** `*_import_export.py` 的工厂式 `_X_SPECS`
    自动发现调整 sheet（判定口径 = `title` 含「调整分录」或 `item_id` 命中 `adjustment`/`adj-entries`/`-aje-rows`），
    逐条对照 `adjustment_ie_contract.json` 断言 `item_id`/**有效** `storage_field`/`field_keys`；失败信息指名 sheet + 维度 + 模块
  - **🔴 判定口径踩坑**：裸 `-adj-` 会把审定表（X-1）的 AJE/RJE 列键误判为调整分录 sheet
    （`F4-1-adj-aging-rows`/`G10-adj-rows`/`I1-adj-rows`/`G3-1-adj-rows`/`I3-adj-rows`），已显式排除并注释
  - 反向断言：清单 `sheets` 里的每张必须真的在后端注册（防清单登记幽灵条目）+ 同一 sheet 不得既在 sheets 又在 exempt
  - Property 6：中央导入必填列 ⊆ 富模板列，且经 `normalize_adjustment_header` 规范化后 ⊆ 汇总导出列（列头从
    `_write_adj_sheet` 源码提取，不复制常量）
  - 结果：实测发现 **37 张**调整 sheet（14 in `sheets` + 23 in `exempt`），56 passed / 23 skipped（skip = exempt 不做三重键断言）
  - _Requirements: 7.1, 7.2_
  - _Properties: Property 9, Property 6_

- [x] 4.2 前端 vitest 契约守卫
  - 新增 `adjustmentIeContract.spec.ts`：用 `node:fs` 向上寻根定位**同一份** `backend/data/adjustment_ie_contract.json`，
    扫描全部 `*TabAdjustment.vue` / `use*Adjustment.ts`（142 个文件），对 aligned 的每张 sheet 断言
    其 `item_id`（字面量或 `ITEM_PREFIX` + `` `${ITEM_PREFIX}-entries` `` 拼接形态）在前端源码真实存在，
    且拥有该键的源文件确实写 `remark` 列（契约 `storage_field` 必须为 `remark`）
  - 另断言 K12-3 已迁 JSON 单键且写路径不再逐字段写 per-field 键（Wave 2 不得回退）
  - 结果：33 passed
  - _Requirements: 7.1, 7.3_
  - _Properties: Property 9_

- [x] 4.3 注册完整性与豁免可区分
  - Property 11 双侧实现：后端守卫断言「发现的每张调整 sheet 必在 `sheets` 或 `exempt`」；
    前端守卫扫描全部调整源文件提取持久化键（含 `ITEM_PREFIX` 拼接），按键 → sheet/cycle 归属清单，未登记即失败并打印
    `键 @ 文件`（守卫遍历源码，不硬编码逐条清单）
  - **首跑暴露 24 个未登记 sheet-guess**（D1/D2/D3/D5-3/D6-4/D7-3/F1/G4-3/H9-4/H9-5/L2/L2-3/L7-3/M1-3…M10-3），
    按**实测**批量登记到 `exempt`（附 `frontend_keys`/`frontend_files`/`backend_key_hits`/`backend_sheet_modules`）：
    - `not_cycle_ie_factory_key_shared`（新增 kind）= 后端 bespoke 自建 router（`_d3`/`_d5`/`_d7`/`_g4…`）以**同名键字面量**读写
    - `not_cycle_ie_factory` = bespoke router 支持该 sheet 但未出现前端调整键
    - `no_backend_spec` = 全部 `*_import_export.py` 均无该 sheet/键 → 无底稿通道导入导出，无 Orphan_Key 风险
    - 无一项落入「工厂已注册却未纳入契约」（那种必须进 `sheets` 而非 exempt，脚本内已 assert）
  - 每条 exempt 必有已登记 `kind` + 非空 `reason`（双侧各一条断言）；清单 exempt 41 → **65** 条
  - _Requirements: 5.5, 7.3, 7.4_
  - _Properties: Property 11_

- [x] 5. Wave 4 — 零回归门 + 端到端

- [x] 5.1 零回归门 + 上游链路不变
  - 全量跑 `adjustments` / `import_templates` / `adjustment_sync` / `trial_balance` / 各循环 IE 相关后端测试 + 前端 vitest；1.1 characterization 基线全绿
  - Property 14：`syncToCentral`/`sync-from-workpaper` 的 `source_ref` 幂等、`origin='workpaper'`、协作锁行为，以及 `recalc` 头表聚合 + workpaper 过滤行为前后一致
  - 禁止以放宽断言/跳过用例取得通过
  - **门结果**：本 spec 四文件 + `adjustments`/`adjustment_sync`/`adjustment_detail_account_code`/`trial_balance`
    共 **333 passed / 23 skipped**（skip = exempt sheet 不做三重键断言）；
    循环 IE 相关（`-k "import_export or import_template or cycle_import"`）**266 passed**；
    前端 `src/components/import` + `useK12Adjustment` + `adjustmentIeContract` 共 **52 passed**
  - **pre-existing 无关失败（已核实非本 spec 回归，均未碰其源文件）**：
    - 收集期 ImportError：`test_h2_import_export_pbt.py`（`_H2_2_BASE_HEADERS` 缺失，`git status` 该模块与测试均无本地改动）、
      `tests/acnr/*`（`from backend.app` 路径）、`test_template_selector.py`、`test_advanced_query_hardening_wave012.py`、
      `services/test_migrate_disclosure_notes.py`、`services/test_sprint1_e2e_roundtrip.py`
    - 执行期：`test_d2_import_export.py::test_validate_columns_rejects_unknown`（`_d2_import_export.py` 是**并发会话**的未提交改动）、
      `test_f3_import_export_pbt.py` 2 项（F3 源文件与测试均无本地改动 = 已提交的既有失败）
  - _Requirements: 8.1, 8.2, 8.3, 8.5_
  - _Properties: Property 2, Property 13, Property 14_

- [x] 5.2 端到端实测*
  - 采用**鉴权 HTTP round-trip（create → verify → cleanup 还原）**替代 flaky Playwright（真实项目 `0ec33ac9` 重药控股安徽 / 2025）
  - **A 底稿通道（K3-3，wp `08d8630c`）**：`export-template` 200 → 列头 = 对齐后 9 列
    `['序号','分录类型','摘要','科目代码','科目名称','借方金额','贷方金额','编制人','备注']` → 填一行 → `import-data` 200 `imported_count=1`
    → `GET checklist-responses` 断言**前端读取键 `K3-3-adj-entries` 的 `remark` 列**有值，且
    `summary`/`accountCode`/`debitAmount`/`preparedBy` 逐字对应、**无 `noteRef`/`voucherNo` 孤儿列**
    → PUT 还原原值 `RESTORED_IDENTICAL = True`
  - **B 中央通道**：富模板 → **在 AJE模板 内置示例行位置（第 2/3 行）覆盖填第一笔真实分录** → `validate` 200 `valid=true row_count=2`
    → `import(append)` 200 `imported=1`（Property 4/5：真实数据不再被吞，同时 RJE模板 的 2 行内置示例仍被跳过 = `"2 行模板示例跳过"`）
    → `import(overwrite)` ×2 → 文件编号组恒 **1** 个（Property 1 幂等不重复）→ 清理后活跃组数与 TB 非零调整集合均回到基线
  - **🔴 实测澄清（我的首版脚本期望写错，代码是对的）**：`append` 走 `create_entry` **自动编号**（不落文件编号，Property 2 要保的既有行为，
    实测创建为 `AJE-014`）；只有 `overwrite` 会 `_pin_adjustment_no` 把文件编号钉住以实现 by-key 幂等
  - **C 汇总导回**：`export-summary` 200（sheets `['AJE审计调整','RJE重分类']`，列头含 Task 1.4 新增的「类型」列）
    → 原样回传 `validate` 200 `valid=true row_count=6` **无「缺少必填列」错误**（仅「未知列（将被忽略）: 来源」提示）= Property 6/8 成立
  - **诚实说明**：TB 非零调整集合在整个 B 流程中恒为空（该项目草稿态调整未计入 `trial_balance` 的 aje/rje 列），
    故"不双计"由 Wave0 PBT（Property 1/Property 3）承担，live 仅证明**分录组不重复**；
    数据零污染已用 postgres 只读复核（该项目 `adjustments` 13 组全 `is_deleted=true`、`trial_balance` 无非零 aje/rje）
  - _Requirements: 1.1, 2.1, 3.4, 5.6, 6.3_
  - _Properties: Property 1, Property 4, Property 8, Property 9, Property 12_

## Notes

- **对齐方向铁律**：改后端 Sheet_Spec 靠向前端，**不改**前端 Storage_Key / 行模型 / `syncToCentral` 配置（K12-3 存储结构例外，用户已定迁 JSON）。前端键被中央同步 `source_ref`、跨 tab 推送（`K8TabDetail`/`K8TabContractCheck` 直写 `K8-3-adj-entries`）、存量数据三方消费。
- **三重键**：`item_id` + `storage_field` + `field_keys` 必须同时对齐；工厂 `storage_field` 默认 `"conclusion"` 而前端读 `remark`，只改 `item_id` 仍读不到（最隐蔽的 Orphan_Key 形态）。
- **不启用 `dual_write`**：双写会让 `conclusion` 残留半新副本形成第二真源。历史落在 `KX-3-rows/conclusion` 的数据是 Orphan_Key（前端从未读到），不迁移。
- **overwrite 语义**：按 `adjustment_no` by-key 覆盖，**不清空全年 manual**（`origin='manual'` 混含中央导入与中央页手工新建，按年度清空会不可逆误删后者）。
- **Round_Trip 验收口径**：必须验证到"前端读取键有值"这一层，接口 `200` 不算通过。
- **实施前复核**：2.1 建清单前用 grep 复核前端各 tab 键与行模型当前真实值（K 循环被并发会话改过多轮），清单以核实结果为准。
- **commit 纪律**：工作树有大量并发未提交改动，commit 前 `git status` + `git diff --cached --name-only` 核实只 stage 本 spec 文件。
