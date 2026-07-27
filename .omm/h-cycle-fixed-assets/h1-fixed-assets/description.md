# H1 固定资产（1601 原值 / 1602 累计折旧）

componentType `h1-fixed-assets`，后端 `_h1_fixed_assets.py`。H 循环的**范式提供者**：
折旧引擎、跨底稿 pull、OCR、监盘、减值 DCF 都由 H1 首发后被 H2~H8 复用。

## 子目录

| 目录 | 内容 |
|---|---|
| `core/` | 审定表 H1-1（原值/折旧/减值三段 12 列）/ 明细 H1-2 / 调整分录 H1-3 / 分析 H1-6 / 附注上市 / 附注国企 / 目录 |
| `depreciation/` | 折旧测算（`useH1DepreciationEngine`：4 种折旧法 + 多次减值分段重算）、折旧分配、折旧合理性整体重算 |
| `impairment/` | H1-14 减值测试（CAS8 迹象 → 可收回金额：公允净额 vs 使用价值 DCF/WACC/敏感性） |
| `inspection/` | H1-7 增加检查 / H1-8 减少检查（抽凭 1601）/ H1-12·13 折旧检查 / H1-17 车辆年检 / H1-18 产权证 / H1-19·20 合同 |
| `stocktake/` | H1-10 监盘（双向：账 → 实物 vouching、实物 → 账 tracing） |
| `handbooks/` + `H1PreparationHandbookDialog` | 编制/使用手册 |

## 关键机制

- **审定表回写双科目**：1601 原值 + 1602 累计折旧（两次 `PUT /trial-balance/writeback`）
- **折旧引擎**：直线法 / 工作量法 / 双倍余额递减 / 年数总和，支持多次减值后分段重算；被 H3/H5/H7/H8 复用
- **折旧合理性整体重算**（实质性分析）：预期折旧 = 平均原值 × 综合年折旧率，差异率 >10% flagged
- **税会差异 → 递延所得税**：账面价值 vs 计税基础 → 暂时性差异 → DTA(N1)/DTL(N3)，税基/税率手工输入
- **跨底稿 pull**：`h1CipH2Pull`（H2 转固）/ `h1SoeClearingH6Pull`（H6 清理）/ `h1FinanceLeaseG5Pull`（G5 融资租赁）
- **OCR**：不动产权证 `/h1/property-title-ocr`、行驶证 `/h1/vehicle-title-ocr`，仅回填空字段 + 确认弹窗
- **闲置 → 减值预警**：`h1:idle-impairment-sign` 事件 → H1-14 红色 alert + 一键引入
- **附注**：**五、22（上市）/ 八、22（国企）**（权威 `note_template_variant_matrix.gu_ding_zi_chan`；
  曾误写 五、15 = 其他债权投资，属数据污染级 bug 已修）；含"已提足折旧仍在使用"专项披露

## 与其他元素的关系

- 上游：H2 在建工程转固、H4 工程物资、G5 融资租赁租入
- 下游：H6 清理 → H10 处置收益（6115）；折旧 → F5/K8/K9/I6；减值 → K11（6701）
- 抵押固定资产 → L1/L3/L4 借款质押披露（所有权受限）
