# H 固定资产与长期资产循环

H 循环覆盖固定资产及其"亲属科目"（在建工程 / 投资性房地产 / 工程物资 / 油气 / 生物资产 / 清理 / 租赁 / 处置损益），
10 个科目包 = **10 个 componentType**（每科目一个，不再拆分），前端目录 `h1/`~`h10/`。

## 组成

| 元素 | 科目 | componentType | 后端 render 策略 | 子目录 |
|---|---|---|---|---|
| H1 固定资产 | 1601 原值 / 1602 累计折旧 | `h1-fixed-assets` | `_h1_fixed_assets` | core / depreciation / impairment / inspection / stocktake |
| H2 在建工程 | 1604（工程物资并入 1605 核对） | `h2-construction-in-progress` | `_h2_construction_in_progress` | core / impairment / inspection / interest / stocktake |
| H3 投资性房地产 | 1503 / 1504 累计折旧 ⚠ | `h3-investment-property` | `_h3_investment_property` | core / depreciation / fairvalue / impairment / inspection / rental |
| H4 工程物资 | 1605（+1604 核对） | `h4-engineering-materials` | `_h4_engineering_materials` | core / impairment / inspection |
| H5 油气资产 | 1631 / 1632 累计折耗 | `h5-oil-gas-assets` | `_h5_oil_gas_assets` | core / depletion / impairment / inspection / lease / stocktake |
| H6 固定资产清理 | 1606（**过渡科目**） | `h6-asset-disposal-clearing` | `_h6_asset_disposal_clearing` | core / inspection |
| H7 生产性生物资产 | 1621 | `h7-biological-assets` | `_h7_biological_assets` | core / depreciation / fairvalue / impairment / inspection / production / stocktake |
| H8 使用权资产 | 1901 / 1902 累计折旧 | `h8-right-of-use-assets` | `_h8_right_of_use_assets` | core / depreciation / impairment / inspection / lease-judgment / measurement |
| H9 租赁负债 | 2205 / 1802 未确认融资费用 | `h9-lease-liabilities` | `_h9_lease_liabilities` | core / amortization / inspection |
| H10 资产处置收益 | 6115（损益） | `h10-asset-disposal-income` | `_h10_asset_disposal_income` | core / inspection |

⚠ H3 用 1503/1504（与 G6/G8 的 1503 撞码，见 `concern.md`）。

## H 循环的统一骨架（每科目高度同构）

1. **HxA 程序表**（含 C 类控制测试前置结论，失效则扩大实质性程序）
2. **Hx-1 审定表**：原值 / 累计折旧(折耗) / 减值 三段 × 期初期末 × 未审·账项调整·审定，净值 = 原值 − 折旧 − 减值；
   变动率 ≥30% 须说明；确认后回写 TB 并广播 `substantive:adjudicated`
3. **Hx-2 明细表**：未审 → 调整 → 审定，可从序时账取数（`pullAssetMovementFromLedger`）
4. **折旧/折耗测算**：直线法为主，H5 单位产量法折耗，H7 生产性生物资产折旧，含减值分段重算
5. **增加/减少/转固检查**：抽凭引擎（各自科目码）+ 行级 OCR（合同 / 产权证 / 发票）
6. **减值测试**：CAS8 迹象判断 → 可收回金额（公允净额 vs 使用价值 DCF）→ 减值准备，**一经确认不得转回**
7. **监盘 / 盘点**：计划 — 抽盘 — 差异（H1/H2/H5/H7 有 `stocktake/`）
8. **调整分录 + 附注上市/国企 + 目录页**

## 三条主脉

1. **在建 → 转固 → 折旧 → 处置**：H4 工程物资 → H2 在建工程 → **转固** → H1 固定资产 →
   H6 清理 → H10 资产处置收益（6115）
2. **租赁双侧**：H8 使用权资产（1901）↔ H9 租赁负债（2205 + 1802 未确认融资费用），
   CAS21 同一份合同的资产侧与负债侧，租赁期/折现率/付款额必须一致
3. **计量模式分叉**：H3 投资性房地产（成本模式 vs 公允价值模式）、H7 生物资产（成本 vs 公允），
   模式决定是否计折旧与公允变动去处
