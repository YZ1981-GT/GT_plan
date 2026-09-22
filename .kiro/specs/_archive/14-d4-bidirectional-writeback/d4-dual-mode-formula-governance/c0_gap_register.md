# C0 Gap登记簿

> 依据：C0 Owner矩阵实证结果 + `backend/wp_templates/` 源模板 openpyxl 实读
> 规则：仅登记 owner 为 `d4-adjustment-and-analysis-gap-closure` 的 wp_code；该 owner spec 已在 `.kiro/specs/` 存在，非空壳，本表记录其缺口边界。

---

## Gap 项汇总

| wp_code | 目标 | 模板文件 | 边界 | 已有能力（可复用） | 缺口 | 优先级 |
|---------|------|---------|------|-----------------|------|--------|
| D4-4 | 营业收入调整分录汇总 | D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx | 10列表格，动态行数（预留空行），类别分「报表调整/账项调整/其他」 | A13 集中调整分录平台能力（错报模块）；TB 回写通道；`ContentMutationService` | ①wp_id 公式 key 绑定到 D4-4；②HTML→Excel→HTML roundtrip（当前未实现）；③Playwright 验收未做 | P1 |
| D4-8 | 重要产品毛利分析 | D4-6至D4-11营业收入 - 分析程序（Leap应对措施-分析程序）.xlsx | 24列两级表头，按产品维度动态扩展行，本期/上期/增减变动三组 | 现有月度毛利计算（`app/services/four_table/`）；`ReportLineAccountSpec` 取数；preset 公式引擎 | ①产品维度身份键（按产品A/B/C.. 命名行，非固定序号）；②公式 preset/custom 分离未实装；③双向同步（HTML↔Excel）未接通 | P1 |
| D4-12 | 合同检查表 | D4-12 营业收入-合同检查（Leap-常规程序）.xlsx | 11列（行标签+10合同），23行固定骨架，合同列动态扩展 | 合同卡片上传/OCR（`/d4/contract-ocr`）；AI 辅助；`useWorkpaperSyncBridge` | ①合同身份键（按合同编号，非列索引）；②公式 mask（合同金额/交货时间等）未实装；③HTML→Excel→HTML roundtrip 未实现；④Playwright 验收未做 | P2 |

---

## 缺口共性

1. **身份键绑定**：三项均缺少 `wp_id + stable_sheet_key + row_key + field_key` 公式 key 的实装，现有 D4 循环模板的 `wp_code` 在 `_index.json` 中均为 `"D4"`（父级），运行时按 sheet 名后缀解析，尚未固化到公式定义层。
2. **双向同步**：三项均未接通 `ContentMutationService` + `useWorkpaperSyncBridge`（C1sync 门控未通过）。
3. **Playwright 验收**：三项均未完成 Playwright roundtrip（HTML→Excel→HTML），属于 C4 验收前置条件。
4. **owner spec 状态**：`d4-adjustment-and-analysis-gap-closure` 已存在（有 tasks.md/design.md/requirements.md），但其中 Task 状态需核对该 spec 是否已完成 C0/C1/C2 门控；本总纲仅登记缺口，不重复该 spec 的工作范围。

## 处置规则

- 本登记簿**不替代** `d4-adjustment-and-analysis-gap-closure` 的 owner spec，仅作为总纲侧的缺口索引。
- 推进顺序：D4-4（P1，与 D4-1 同属审定表明细 workbook）→ D4-8（P1，与 D4-6/7/9/10/11 同属分析程序 workbook）→ D4-12（P2，独立 workbook）。
- UNVERIFIABLE 项：无（三项均有实际模板文件 + sheet 实证）。
