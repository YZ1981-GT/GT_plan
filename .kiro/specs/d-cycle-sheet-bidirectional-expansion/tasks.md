# Implementation Plan — D-cycle sheet bidirectional expansion

## Overview

在 D1–D7 父 entry 已各做实 1 张明细的前提下，按可双向性分波扩 sibling 受管表；**禁止**把程序/附注类强行双向。首 canary = D4-3（扩 `d4.revenue_detail`）。

## Tasks

- [x] 0. 盘点 D 循环 gap + 诚实 triage（done / candidate / single_html）
  - 产出：本 spec `README.md`；依据 g5-1 §§6–12 + manifest + 宿主
  - _Requirements: scope_

- [x] 1. D4-3 列↔字段映射冻结（阻塞门）
  - openpyxl 核定 `其他业务收入明细表D4-3` 几何与 A–N 语义
  - 对齐 `useD4OtherRevenue.StoredOtherRow`；裁决 D/I 重分类
  - 输出 `evidence/T01-d43-column-field-mapping.json` + `mapping_digest`
  - _Requirements: mapping_

- [x] 2. D4-3 生产链往返等值（阻塞门）
  - 在契约加入 `d43-managed` 后：materialize→extract→merge 对 6 个 store 字段等值
  - 公式列 E/F/J/K/L/M + D/I 不被 projection 覆盖（mask）
  - **完成**：`test_d43_production_roundtrip.py` 绿；多 sheet footer 用
    `GT_FOOTER_ROW_{TEMPLATE_ID}` + `assert_footer_anchor_stable(table_key=…)`
  - _Requirements: roundtrip_

- [x] 3. 扩展 `phase5_d4_revenue_detail`：第二 sheet + 双 store
  - `sheets[]` 增 `d43-managed`；`STORE_ITEM_IDS` + `build_combined_store_projection` + `merge_projection_into_all_d4_stores`
  - 生成器 `--apply`；`assert_contract_file_matches_source` OK（contract digest `74804f7491338660…`）
  - instrumentation 多 sheet：`build_instrumentation_payload_for_sheets` + `instrument_workbook_bytes_multi`；template sha 不变
  - _Note_：引擎受管末行 **18**（BP-21 排除 A19 `……`）；T01 digest 仍含 `last_data_row=19`。
  - _Requirements: provider_

- [x] 4. 发布链增量
  - Task76 `--apply` ✅ 新 bundle=`0b7bb759…` / contract=`74804f74…` / instr=`214577da…`
  - rematerialize ✅ representation=`5a62a7d1…` generation=1 revision=13（双 sheet 注入 +
    双 store overlay；修 multi-pass `row_shift` 取主 binding + sibling verify 共用
    `propagation`）
  - _Requirements: publish_

- [x] 5. 宿主 + oo_to_html
  - `isD4DetailSheet` → D4-2 | D4-3；`sheetKey` 随 currentSheet（d42/d43-managed）
  - `useD4OtherRevenue` 导出 `flushPendingSave`；formData 经 `d4:flush-pending` 覆盖
  - `oo_to_html` `_mirror_d4_dual_stores` 按 table 写 `D4-2-rows` / `D4-3-rows`
  - `store_projection_response` 在 `STORE_ITEM_IDS` 时走 `build_combined_store_projection`
  - _Requirements: host_

- [x] 6. §9.6 e2e + DB 三谓词（D4-3）
  - `e2e/g5-1-d43-unified-path.spec.ts` 绿；evidence `g5-1-d43-unified-path/`
  - 硬门：confirm 200 / forcesave `cs_error=0` / `store_mirrored`+`marker_visible`
  - DB：`db-check.json`（op `f54bbfd9…` / marker `g5d43680692` / `D4-3-rows`）
  - 修：`oo_to_html._adapter_for_oo_to_html` 保留 `sibling_bindings`（否则 D43 extract 空）
  - _Requirements: verify_

- [x] 7. 下一波候选开工（D4-4 或 D1-2）并更新 README 分波表
  - **原裁决**：Wave 2 = D4-4（同 entry 续扩 `d4.revenue_detail`）
  - kickoff：`evidence/T07-d44-wave2-kickoff.json` 实测**模板无 GTROW/UUID 列**（行身份锚缺失）——映射门未过
  - 🔴 **该裁决被 Task 8 撤销**：D4-4 据模板真相 + adjustment-hub 冲突改判 `single_html`（见 Task 8）；下一双向 canary 转 **D1-2**
  - _Requirements: continue_

- [x] 8. D4-4 单元格双向可行性裁决（改判 single_html）
  - openpyxl 直读真实模板 `D4 收入底稿.xlsx`（sha `b8fb92d4…`，唯一权威）：真实 tab = `营业收入调整分录汇总D4-4`，A1:J23，表头行 5 有 10 字段键列，数据区 6-20
  - **裁决 single_html**，四条依据：① 无 GTROW/UUID 行身份列（单元格双向回写无法按行定位）② `D4-4-rows` 是 hub store，已由 `useD4Adjustment`（借贷平衡）+ `useD4CrossSheet`（→D4-1）+ `useAdjustmentCentralSync`→后端 `AdjustmentSyncService`（source_ref `{wp_id}:D4-4-rows`）→ A13 联动占用，OO 覆盖会争 store 破坏平衡/A13 ③ 借贷平衡不变式仅 HTML 侧强制，Excel 不校验 ④ 动态插入带、列 F『……』排版占位
  - 撤销 T07 的 wave2=D4-4 双向裁决；不改任何生产代码（诚实边界，expansion spec 红线）
  - 证据 `evidence/T08-d44-single-html-adjudication.json`；README 分波表更新 D4-4→single_html、下一双向 canary=D1-2
  - 附带如实登记既有缺陷（不在本裁决修）：`src/generated/dSheetLabels.ts` 把 `D4-4` 误标为『主营业务收入审计程序表D4A（修订前）』，与真实 tab 不符——属 generated 映射生成器的债
  - _Requirements: continue, mapping_

## Notes

Registry 一 entry 一 adapter 不变；多 sheet 只扩契约 `sheets[]`。分析类/程序类未进本任务集前必须先做映射可行性核，不得默认 bidirectional。

- **D4-5 会计政策检查**：已 triage → `single_html`（`evidence/T08-d45-single-html-triage.json`）。段落式 + 多 `D4-5-*` item，无 GTROW；**禁止**扩进 `d4.revenue_detail` sheets[]。双向下一刀 = **D1-2**（D4-4 已于 Task 8 改判 single_html，见 `T08-d44-single-html-adjudication.json`）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "盘点 + 诚实 triage，全后续输入" },
    { "wave": 1, "tasks": ["1", "2", "3", "4", "5", "6"], "rationale": "D4-3 首 canary 全链：映射冻结→往返门→provider 扩 sheets[]→发布→宿主→e2e" },
    { "wave": 2, "tasks": ["7", "8"], "rationale": "下一波裁决 + D4-4 可行性核；Task 8 据模板真相把 D4-4 改判 single_html，下一双向 canary 转 D1-2" }
  ],
  "blocking": {
    "1": "D4-3 列↔字段 mapping_digest 未冻结 ⇒ Task 2/3 阻塞",
    "2": "D4-3 生产链往返未等值 ⇒ Wave 1 后续阻塞",
    "8": "任一新受管 sheet 必须先过『有行身份列 + 无专用同步链冲突』可行性核，否则判 single_html 不得扩 sheets[]"
  }
}
```
