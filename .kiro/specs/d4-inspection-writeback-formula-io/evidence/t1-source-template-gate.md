# T1 源模板核定与稳定 ID gate — 核定证据

> 生成依据：openpyxl 直读 `backend/wp_templates/D/D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx`（size=115295，sha256 前缀 `1201b80c`，`workpaper_sync_d_cycle_manifest_slice.json` 登记 `belongs_to_entry: xlsx/gt-d4-operating-revenue`）。
> 探针脚本（用完即删，非正式产物）：`backend/scripts/_probe_d4_13_16_template.py` / `_probe_d4_13_16_body.py` / `_probe_d4_14_body.py`。
> 后端真源：`backend/app/routers/wp_render_strategies/_d4_import_export.py`（`_SHEET_HEADERS` / `_parse_d4_1[3-6]_row` / `_handle_d4_13_*` / item_id 映射）。

## 源 xlsx sheet 清单（9 个，本 spec 目标 4 个加 ★）

| 物理 sheet 名 | wp_code | 类型 |
|---|---|---|
| 底稿目录 | — | 目录 |
| 营业收入账面金额与ERP系统核对记录D4-13 | ★D4-13 | 叙述文本 |
| 营业收入发生检查表D4-14 | ★D4-14 | 两级表头行表（7 维嵌套） |
| 营业收入完整性检查表D4-15 | ★D4-15 | 两级表头行表（3 维嵌套） |
| 出口收入电子口岸系统核对D4-16 | ★D4-16 | 两级表头行表（差异派生） |
| 营业收入截止测试（账到单据）D4-17 | D4-17 | （姊妹 spec d4-cutoff-return） |
| 营业收入截止测试（单据到账）D4-18 | D4-18 | （姊妹 spec） |
| 销售折扣与折让检查D4-19 | D4-19 | （姊妹 spec） |
| 销售退货检查表 D4-20 | D4-20 | （姊妹 spec） |

## D4-13：营业收入账面金额与 ERP 系统核对记录（叙述表，无行集）

- 结构：`一、核对过程`（row5 起）+ `二、核对结论`（row15 起）两段文本；row19 提示语。merges 仅 `A1:E1`/`A2:E2`（抬头），**无数据表结构**。
- 后端映射（核定通过）：`_D4_13_SECTIONS = [("核对过程","D4-13-process"),("核对结论","D4-13-conclusion")]`；`_SHEET_HEADERS["D4-13"] = ["区块","内容"]`（导出各段一行，导入按「区块」中文 label 回写两个 item_id）。
- item_id：`D4-13-process` / `D4-13-conclusion`（稳定，与前端 `D4TabErpCheck.vue` core 双侧一致）。
- **结论**：D4-13 是纯叙述表，**不适配受管行表同步模型** → 双模式同步桥归 B1 blocked（文本型适配另议）。文本锚点逐字往返由 T3 守卫。

## D4-14：营业收入发生检查表（两级表头，7 维嵌套）

- 两级表头：row13 父组 + row14 子列。父组 merges 实证：
  - 记账凭证 `B13:G13`（客户名称/日期/编号/品名/数量/金额）
  - 销售合同/销售订单 `H13:I13`（日期/合同号-订单号）
  - 出库单 `J13:M13`（日期/编号/品名/数量）
  - 仓库保管员 `N13:N14`、发货审批人 `O13:O14`（单列跨行）
  - 运输单 `P13:T13`（日期/编号/运输数量/运输公司/运输地址）
  - 签收单 `U13:AA13`（日期/品名/数量/金额/签收人/盖章类型/盖章单位）
  - 发票 `AB13:AF13`（日期/编号/品名/数量/金额）
  - `……` `AG13:AH13`、其他支持性文件 `AI13:AI14`、索引号 `AJ13:AJ14`、是否异常 `AK13:AK14`
- 后端映射（核定通过，语义归并）：`_parse_d4_14_row` → `TransactionItem` 顶层 `{id:"t-"+uuid4, indexNo, label, consistencyScore:0, consistencyDetails, conclusion, isAnomalous}` + 7 嵌套维度 `voucher/contract/delivery/shipping/receipt/invoice/other`。item_id = `D4-14-transactions`。
- 稳定 id：`t-`+uuid4（导入生成，导出保留 indexNo）；`consistencyScore` 导入恒置 0，前端重算（派生值单源）。
- **登记差异（非错误，业务投影）**：源模板 7 个物理父组（记账凭证/合同/出库/运输/签收/发票/其他）+ 仓库保管员/发货审批人两独立列，后端归并为 voucher/contract/delivery(出库)/shipping(运输)/receipt(签收)/invoice/other 七维；仓库保管员归 delivery.warehouseKeeper、发货审批人归 contract.approver。后端 `_SHEET_HEADERS["D4-14"]` 是 32 列平铺语义头（导出投影）。

## D4-15：营业收入完整性检查表（两级表头，3 维嵌套）

- 两级表头：row11 父组 + row12 子列。父组 merges 实证：
  - 发货单 `B11:F11`（日期/编号/品名/数量/金额）
  - 发票 `G11:K11`（日期/编号/品名/数量/金额）
  - 记账凭证 `L11:P11`（日期/编号/品名/数量/金额）
  - 所载信息是否一致√(X) `Q11:Q12`（单列跨行）
- 后端映射（核定通过）：`_parse_d4_15_row` → `{id:"c-"+uuid4, indexNo, delivery{...}, invoice{...}, voucher{...}, isConsistent:None, remark}`；三维各 5 字段 date/number/productName/quantity/amount。item_id = `D4-15-items`。
- 稳定 id：`c-`+uuid4（导入生成）；`isConsistent` 导入**强制留 None**（`_d4_import_export.py` L1902），由前端 `checkConsistency` 重算（派生值单源，不双写）。
- 🔴 **登记偏差（须知，非本 spec 强制修）**：源模板列头是「**所载信息是否一致√(X)**」，后端 `_SHEET_HEADERS["D4-15"]` 第 17 列写的是「**核核信息是否一致**」（疑似笔误：核核↔所载）。导出用后端 header，导入用列名 `index()` 匹配——因导入侧 `_parse_d4_15_row` 按固定子列名（发货单日期等）取值、不依赖「一致」列（该列由前端重算），故此偏差**不影响往返正确性**，但导出模板列头与源模板不一致。T3 守卫登记，是否改 header 待用户裁决（改动 `_SHEET_HEADERS` 属并发热点文件，需谨慎）。

## D4-16：出口收入电子口岸系统核对（两级表头，差异派生）

- 两级表头：row11 父组 + row12 子列。父组 merges 实证：
  - 账面出口收入金额（A 列，A11:A12 跨行）
  - 电子口岸系统 `B11:F11`（期间/结关金额/差异/原因/索引）
  - 免抵退税申报数据 `G11:K11`（期间/申报外销收入/差异/原因/索引）
- 源模板差异列 row13 内嵌 `0`（D 列口岸差异、I 列免抵退税差异）→ 证实差异是**派生列**。
- 后端映射（核定通过）：`_parse_d4_16_row` 中文→英文 key：账面出口收入金额→`bookAmount`、口岸期间→`portsPeriod`、口岸结关金额→`portsAmount`、口岸差异原因→`portsReason`、申报外营收入→`taxReportAmount`、申报差异原因→`taxReason`、索引→`taxIndex`；固定产出 `portsAmount2:0`。item_id = `D4-16-rows`。
- 派生值单源（核定通过）：`portsDiff = bookAmount - portsAmount`、`taxDiff = bookAmount - taxReportAmount` 后端强制重算（L1928/L1933），**不读文件差异列**（防手改造假）；前端 `onCellChange` 也走 `calcChangeAmount(a,b)=a-b` 重算。
- 稳定 id：`r-`+uuid4（导入生成）。
- 🔴 **登记偏差（须知）**：源模板有两个「期间」两个「差异」两个「原因」两个「索引」（电子口岸 5 子列 + 免抵退税 5 子列），后端 `_SHEET_HEADERS["D4-16"]` 只声明单套「口岸期间/口岸结关金额/口岸差异/口岸差异原因/申报外营收入/申报差异/申报差异原因/索引」10 列，把两个「索引」合并为一个 `taxIndex`。前端 `ExportCheckRow` 也只有一个 `taxIndex` 字段（无 portsIndex）。这是**业务简化**（口岸侧索引未建模），非往返错误。T3 守卫登记。

## 三态边界核定（Requirement 4.1）

- 四表**均不涉及截止方向计算**（跨期互斥属 D4-17/18/36，姊妹 spec）。`useD4FormulaEngine` 的 `isCrossPeriod*`/`calcCrossPeriodDays` 在本四表未被消费（核定通过，符合业务）。
- 日期字段：D4-14/15 各维度 date、D4-16 portsPeriod 均为 `_safe_str`（空/非法保留原文本，不凑风险判断）。
- 金额字段：`_safe_float`（空→0.0 数值语义）；派生差异/一致性由前端三态（true/false/null）表达，D4-15 `isConsistent` 三态、D4-16 差异数值。

## 稳定 ID / item_id 汇总（导出↔导入双侧一致，T3 守卫锚点）

| wp_code | item_id | 行 id 前缀 | 派生列（不信文件值，前端重算） |
|---|---|---|---|
| D4-13 | D4-13-process / D4-13-conclusion | 无（文本） | — |
| D4-14 | D4-14-transactions | t- | consistencyScore |
| D4-15 | D4-15-items | c- | isConsistent |
| D4-16 | D4-16-rows | r- | portsDiff / taxDiff |

## gate 结论

- 四表源列头、嵌套结构、item_id、动态 id 前缀、派生列单源、三态边界**全部核定通过**，后端 parser/exporter 与源模板结构一致。
- 登记 2 处**非阻断偏差**（D4-15「核核↔所载」header 笔误、D4-16 口岸索引未建模），不影响往返正确性，T3 守卫覆盖并留待用户裁决。
- 未知列/未知分类/未知科目：四表 parser 按固定子列名/中文 label 取值，未匹配列进 `_safe_str`/`_safe_float` 默认而非静默丢弃或猜测归「其他」（核定通过）。
