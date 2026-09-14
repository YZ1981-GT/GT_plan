# H5 油气资产（1631/1632）/ H7 生产性生物资产（1621）

两个**行业专属**科目包，普通客户不适用（应能整包裁剪）。结构同构于 H1 但各有独有 sheet。

## H5 油气资产（`h5-oil-gas-assets`）

| 目录 | 内容 |
|---|---|
| `core/` | 审定表（四区块：原值/累计折耗/减值/净值）/ 明细 / 调整 / 披露 / 目录 |
| `depletion/` | **单位产量法折耗**（油气行业特有，非直线法） |
| `impairment/` | 减值测算（CAS8 + 油气储量评估） |
| `inspection/` | 增加/减少/勘探开发支出检查 |
| `lease/` | 矿区租赁/权益 |
| `stocktake/` | 实物盘点 |

- 科目：`ACCOUNT_CODE_1631='1631'`（油气资产）+ `ACCOUNT_CODE_1632='1632'`（累计折耗）；
  `writebackTB` **只接受 1631/1632**，其它科目 warn 并 return
- 行业守卫：`oil_gas` + `mining`（非该行业不适用）
- EventBus 3 事件 + TB 回写 1631/1632

## H7 生产性生物资产（`h7-biological-assets`）

| 目录 | 内容 |
|---|---|
| `core/` | 审定（成本/公允双版本）/ 明细（成本/公允双区段）/ 调整 / 分析 / 附注上市国企 |
| `depreciation/` | 直线法折旧（不含减值 / 含减值双版本）+ 折旧分配 |
| `fairvalue/` | 公允价值复核（**仅公允模式**） |
| `impairment/` | 减值测算 / 可收回金额 |
| `production/` | **产量记录**（H7 独有，变动率 >30% 预警） |
| `inspection/` | 增加/减少（成本公允双版本）/ 政策检查 CAS5 / 关联交易 / 互转审核 |
| `stocktake/` | 计划 / 检查 / 小结 |

- 科目：`ACCOUNT_CODE_1621='1621'`；**TB 取数用 `account_codes` 参数 + `POST /trial-balance/writeback {items:[...]}` 批量形态**
  （与 H 循环其余科目的 `account_prefix` + `PUT` 不同）
- 行业守卫：`agriculture` + `forestry` + `livestock` + `fishery`
- 双计量模式（成本 / 公允）切换审定表与折旧适用性
- 曾有 25 个 tab 全是 `el-empty` 占位（composable 逻辑层先行、UI 后补），现已实现

## 共同要点

- **适用性裁剪**：非对应行业应整包标不适用，不要留空表
- 折耗/折旧 → F5 营业成本；减值 → K11（6701）
- H5 的折耗基于储量与产量（单位产量法），H7 的产量记录是**成本分摊与合理性分析的基础**
