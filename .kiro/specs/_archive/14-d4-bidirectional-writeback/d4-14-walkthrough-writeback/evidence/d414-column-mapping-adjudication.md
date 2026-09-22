# D4-14 营业收入发生检查表 — 物理列 ↔ 前端 7 维逐列映射裁决表

> **状态**：✅ 已签署（路线 A 全受管，2026-09-21）
> **产出日期**：2026-09-21（Task 1 几何冻结 + 逐列初稿 → 业务复核签署）
> **权威源**：本表经审计业务复核签署确认后，成为 D4-14 sync 双向回写「物理列 ↔ 前端字段」映射的唯一权威源。
> **未签署 = Task 3-12 全部 BLOCKED**（不得基于本初稿的"建议"列先建 provider）。
>
> **判据（DEC-4 correctness 优先）**：37 个物理列每列必须有明确归属，无「未决」残留；无论受管/HTML-only，
> 都**不得静默丢弃**任何物理列（HTML-only 列显式标"不受管、保留模板内容"，materialize 不写、extract 不读）。

## 一、几何锚点（`d414-geometry.json` 冻结，openpyxl 实读）

- 源模板：`backend/wp_templates/D/D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx`
- sheet：`营业收入发生检查表D4-14`，dims `A1:AK52`（**37 物理列 A–AK**）
- 两级表头：R13（组）+ R14（子字段）
- 数据区：**R15–R36（22 行）**，A 列全空（模板无预填样例）
- footer marker：**单行 `合计` A37**（唯一，非计算型 footer → 引擎范式非阻塞）
- formula_cells（数据/合计区）：**G37 / X37 / AF37**（=SUM 合计）+ **G39**（=G37/G38 检查比例）→ formula_mask
- R38 本期发生额 / R39 检查比例 / R40 审计说明 / R44 审计结论 / R48-52 提示 = HTML-only
- UUID 列 = **AL**（物理列止于 AK，AL 空）
- AG/AH = 表头即 `……` 占位列（无实际字段）
- R3/R4 的公式（=底稿目录!Ax）是表头链接，非数据区，不涉及本裁决

## 二、前端 7 维模型（`useD4WalkthroughTest.ts` 冻结，27 业务字段）

| 维度 | 前端字段 |
|---|---|
| voucher 记账凭证（7） | month / date / number / productName / quantity / amount / accountingDate |
| contract 销售合同（5） | number / productName / amount / approver（签发审批）/ confirmor（签收确认）|
| delivery 出库单（4） | date / productName / amount / warehouseKeeper（仓库保管员）|
| shipping 运输单（3） | date / productName / amount |
| receipt 签收单（3） | date / productName / amount |
| invoice 发票（3） | date / number / amount |
| other 其他（2） | description / indexNo |
| 派生（4，不入契约） | consistencyScore / consistencyDetails / conclusion / isAnomalous |

> ⚠️ 反误导：后端 `_SHEET_HEADERS["D4-14"]` 的 32 列是**按前端 7 维平铺的语义投影头**，非源模板物理列。
> sync 映射以本表（物理列权威）为准，不得拿语义投影头当映射。

## 三、逐列裁决表（37 列，`建议` 列为初稿，`裁决` 列待业务复核填写）

图例：**受管**=映射到某前端字段双向回写 · **补字段**=前端 7 维无此字段需扩模型后受管 · **HTML-only**=不受管保留模板内容 · **派生/占位**=formula_mask 或占位列不入契约

| 列 | R13 组 | R14 字段 | 前端对应 | 建议归属 | 理由 | 裁决(业务复核填) | 复核意见 |
|----|--------|---------|---------|---------|------|-----------------|---------|
| A | 序号 | — | indexNo(前端自增) | **派生/占位** | 模板自增序号，前端 `reindexItems` 生成 `D4-14-{i+1}`，不入契约 | | |
| B | 记账凭证 | 客户名称 | ❌ 无 | **补字段 或 HTML-only** | 前端 voucher 无 customerName。穿行测试核心是"同一客户/同一笔交易七维一致"，客户名称是识别锚点，建议 **补 voucher.customerName**；若业务认为客户名以合同为准则留 HTML-only | **补字段** voucher.customerName | 路线A受管 |
| C | 记账凭证 | 日期 | ✅ voucher.date | **受管** | 一致性引擎 date 比对维度 | | |
| D | 记账凭证 | 编号 | ✅ voucher.number | **受管** | 凭证号 | | |
| E | 记账凭证 | 品名 | ✅ voucher.productName | **受管** | 一致性引擎 productName 比对维度 | | |
| F | 记账凭证 | 数量 | ✅ voucher.quantity | **受管** | 前端 quantity 为 string 型 | | |
| G | 记账凭证 | 金额 | ✅ voucher.amount | **受管**（G37 SUM 除外） | 一致性引擎 amount 比对维度；**G37=SUM → formula_mask** | | |
| H | 销售合同/订单 | 日期 | ❌ 无 | **补字段 或 HTML-only** | 前端 contract 无 date。合同签订日期是"合同先于发货"时序核查依据，建议 **补 contract.date**；ROI 低则 HTML-only | **补字段** contract.date | 路线A受管 |
| I | 销售合同/订单 | 合同号/订单号 | ✅ contract.number | **受管** | 合同编号；亦是 D4-12 联动锚点(refD4ContractId) | | |
| J | 出库单 | 日期 | ✅ delivery.date | **受管** | 一致性引擎 date 比对维度 | | |
| K | 出库单 | 编号 | ❌ 无 | **补字段 或 HTML-only** | 前端 delivery 无 number。出库单号是实物流转凭证编号，建议 **补 delivery.number**；ROI 低则 HTML-only | **补字段** delivery.number | 路线A受管 |
| L | 出库单 | 品名 | ✅ delivery.productName | **受管** | 一致性引擎 productName 比对维度 | | |
| M | 出库单 | 数量 | ❌ 无 | **补字段 或 HTML-only** | 前端 delivery 无 quantity。数量核对是"账实一致"关键，建议 **补 delivery.quantity**；ROI 低则 HTML-only | **补字段** delivery.quantity | 路线A受管 |
| N | 仓库保管员 | —（独立列，R13 组名即字段） | ✅ delivery.warehouseKeeper | **受管** | 前端已有；注意物理列 N 的 R13 组名是"仓库保管员"、R14 空，值在数据行 N 列 | | |
| O | 发货审批人 | —（独立列） | ⚠️ 归属存疑 | **待业务裁决**（补 delivery.shippingApprover / 或映射 contract.approver / 或 HTML-only） | 前端 contract.approver 语义是"签发审批"、confirmor 是"签收确认"，与"发货审批人"语义**不完全等同**。建议 **补 delivery.shippingApprover**；若业务认定等同 contract.approver 则复用；否则 HTML-only | **补字段** delivery.shippingApprover | 受管；不复用contract.approver(语义不同) |
| P | 运输单 | 日期 | ✅ shipping.date | **受管** | 一致性引擎 date 比对维度 | | |
| Q | 运输单 | 编号 | ❌ 无 | **补字段 或 HTML-only** | 前端 shipping 无 number。运单号，建议 **补 shipping.number**；ROI 低则 HTML-only | **补字段** shipping.number | 路线A受管 |
| R | 运输单 | 运输数量 | ❌ 无 | **补字段 或 HTML-only** | 前端 shipping 无 quantity。建议 **补 shipping.quantity**；ROI 低则 HTML-only | **补字段** shipping.quantity | 路线A受管 |
| S | 运输单 | 运输公司 | ❌ 无 | **补字段 或 HTML-only** | 前端 shipping 无 company。承运方是第三方舞弊核查线索(见 R49 提示)，建议 **补 shipping.company**；ROI 低则 HTML-only | **补字段** shipping.company | 路线A受管；第三方舞弊核查线索 |
| T | 运输单 | 运输地址 | ❌ 无 | **补字段 或 HTML-only** | 前端 shipping 无 address。建议 **补 shipping.address 或 HTML-only**（自由文本、比对价值低，倾向 HTML-only） | **补字段** shipping.address | 路线A受管 |
| U | 签收单 | 日期 | ✅ receipt.date | **受管** | 一致性引擎 date 比对维度 | | |
| V | 签收单 | 品名 | ✅ receipt.productName | **受管** | 一致性引擎 productName 比对维度 | | |
| W | 签收单 | 数量 | ❌ 无 | **补字段 或 HTML-only** | 前端 receipt 无 quantity。建议 **补 receipt.quantity**；ROI 低则 HTML-only | **补字段** receipt.quantity | 路线A受管 |
| X | 签收单 | 金额 | ✅ receipt.amount | **受管**（X37 SUM 除外） | 一致性引擎 amount 比对维度；**X37=SUM → formula_mask** | | |
| Y | 签收单 | 签收人 | ❌ 无 | **补字段 或 HTML-only** | 前端 receipt 无 signer。签收人是控制权转移凭证，建议 **补 receipt.signer**；ROI 低则 HTML-only | **补字段** receipt.signer | 路线A受管 |
| Z | 签收单 | 盖章类型 | ❌ 无 | **HTML-only（建议）** | 前端 receipt 无。分类文本、比对价值低，倾向 **HTML-only**；如业务需受管再补 | **补字段** receipt.sealType | 路线A受管(全受管一个不落) |
| AA | 签收单 | 盖章单位 | ❌ 无 | **补字段 或 HTML-only** | 前端 receipt 无。盖章单位可交叉验证客户身份，建议 **补 receipt.sealEntity 或 HTML-only** | **补字段** receipt.sealEntity | 路线A受管；交叉验证客户身份 |
| AB | 发票 | 日期 | ✅ invoice.date | **受管** | 一致性引擎 date 比对维度 | | |
| AC | 发票 | 编号 | ✅ invoice.number | **受管** | 发票号 | | |
| AD | 发票 | 品名 | ❌ 无 | **补字段 或 HTML-only** | 前端 invoice 无 productName。发票品名参与 productName 一致性有价值，建议 **补 invoice.productName**；ROI 低则 HTML-only | **补字段** invoice.productName | 路线A受管 |
| AE | 发票 | 数量 | ❌ 无 | **补字段 或 HTML-only** | 前端 invoice 无 quantity。建议 **补 invoice.quantity**；ROI 低则 HTML-only | **补字段** invoice.quantity | 路线A受管 |
| AF | 发票 | 金额 | ✅ invoice.amount | **受管**（AF37 SUM 除外） | 一致性引擎 amount 比对维度；**AF37=SUM → formula_mask** | | |
| AG | …… | …… | ❌ 无 | **派生/占位** | 表头即 `……` 占位列，无实际字段语义，不入契约（保留模板内容） | | |
| AH | （AG 组续）| …… | ❌ 无 | **派生/占位** | 同 AG 占位列，不入契约 | | |
| AI | 其他支持性文件或说明 | — | ✅ other.description | **受管** | 前端 other.description（textarea 自由文本） | | |
| AJ | 索引号 | — | ✅ other.indexNo | **受管** | 前端 other.indexNo | | |
| AK | 是否异常 | — | ⚠️ isAnomalous(派生) | **待业务裁决**（受管 or 派生 HTML-only） | 前端 isAnomalous 是布尔派生（由 conclusion/一致性推导）。模板 AK 是可录入文本列。建议：若业务要人工录入异常标记则 **受管映射到新增 other.anomalyNote**；若纯前端派生展示则 **HTML-only** | **补字段** other.anomalyNote(人工录入) | 受管；人工异常标记(与派生isAnomalous并存) |

## 四、formula_mask（不可回写，extract 拒绝把公式当值）

| cell | 公式 | 说明 |
|------|------|------|
| G37 | `=SUM(G15:G36)` | 记账凭证金额合计 |
| X37 | `=SUM(X15:X36)` | 签收单金额合计 |
| AF37 | `=SUM(AF15:AF36)` | 发票金额合计 |
| G39 | `=G37/G38` | 检查比例（footer 下辅助行，随 HTML-only 段） |

## 五、HTML-only 区（受管数据区之外，不入契约，materialize 不触碰）

- R1-R12：标题 / 审计目标 / 样本选取标准（对应前端 samplingParams，走 D4-14-sampling store，非 sync 受管）
- R37 `合计`（marker）/ R38 `本期发生额` / R39 `检查比例`（G39 公式）
- R40-R47：四、审计说明（对应前端 auditNote，D4-14-note store）
- R44-R47：五、审计结论（对应前端 auditConclusion，D4-14-conclusion store）
- R48-R52：提示 1/2 及舞弊资金流转说明（模板固定文本）

## 六、业务复核裁决结论（2026-09-21 签署，DEC-4：correctness 优先于覆盖率）

> ✅ **裁决已签署，解除 Task 3-12 BLOCKED。**
> - **决策 1 = A 全受管**：37 物理列中数据区列全部受管（含 16 个前端补字段），无 HTML-only 数据列。
> - **决策 2** = 14 列全部「补字段」（含 Z 盖章类型，全受管一个不落）。
> - **决策 3** = O 发货审批人补 `delivery.shippingApprover`（不复用 contract.approver，语义不同）；AK 是否异常补 `other.anomalyNote`（人工录入，与前端派生 isAnomalous 并存）。
>
> **新增前端字段清单（16 个，camelCase，前端 store 真源）**：
> voucher.customerName / contract.date / delivery.number / delivery.quantity / delivery.shippingApprover /
> shipping.number / shipping.quantity / shipping.company / shipping.address /
> receipt.quantity / receipt.signer / receipt.sealType / receipt.sealEntity /
> invoice.productName / invoice.quantity / other.anomalyNote
>
> **受管数据列（36 列中）**：B–AF 全部数据列受管（A 序号=派生自增；AG/AH=占位不入契约；G37/X37/AF37/G39=formula_mask）；
> AI/AJ/AK 受管。**无 HTML-only 数据列**（HTML-only 仅限数据区之外的 R1-12 / R37-52 说明结论段，见第五节）。

### 决策 1：ROI 整体路线（A / B / C 三选一）
- **A 全受管**：补齐 15+ 前端缺失字段（B/H/K/M/O/Q/R/S/T/W/Y/AA/AD/AE 等）+ AK。覆盖率最高，但前端 7 维模型改动面大（TransactionItem/DIMENSION_GROUPS/一致性引擎/OCR 映射/import-export 32 列头全需同步），ROI 需评估。
- **B 部分受管 + 部分 HTML-only**（**初稿倾向，最可能现实结论**）：核心可比对字段（各维 date/amount/productName/number）+ 已有前端字段受管；辅助/自由文本字段（客户名称、盖章类型、运输地址等）留 HTML-only。平衡覆盖率与改动面。
- **C 不值得双向（single_html）**：若受管收益 < 补字段成本，D4-14 保持 legacy 单向，本 spec 收口为裁决记录，清册标终态。

### 决策 2：逐列表中标「补字段 或 HTML-only」的 14 列，逐列二选一
> B/H/K/M/Q/R/S/T/W/Y/AA/AD/AE + Z（初稿倾向 HTML-only），业务复核逐列在「裁决」列填 **补字段** 或 **HTML-only**。

### 决策 3：语义存疑两列
- **O 发货审批人**：补 delivery.shippingApprover / 复用 contract.approver / HTML-only ？
- **AK 是否异常**：受管映射新字段 / 纯前端派生 HTML-only ？

## 七、签署（权威源确认）— ✅ 已签署

> ✅ 本表经审计业务复核签署确认，解除 Task 3-12 的 BLOCKED。

- [x] 审计业务复核已逐列确认「裁决」列，无「待业务裁决/未决」残留
- [x] 决策 1（A/B/C 路线）已选定：**A 全受管**
- [x] 决策 2（14 列）已逐列填定：**全部补字段**
- [x] 决策 3（O 发货审批人、AK 是否异常）已裁定：O→补 delivery.shippingApprover；AK→补 other.anomalyNote（人工录入）

签署人：审计业务复核　日期：2026-09-21　结论路线（A/B/C）：**A**
