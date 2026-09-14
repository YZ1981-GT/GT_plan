# F2 特殊存货（`f2-inventory-special`）

主入口 `GtF2InventorySpecial.vue`，后端 `_f2_inventory_special.py`。目录 `f2-special/`，两组互不相干的专项：
**合同履约成本（CAS14）** 与 **IPO 供应商与采购专项核查**。

## 一、合同履约成本（`f2-special/contract/`）

| 组件 | 作用 |
|---|---|
| `F2TabContractProcedure` | 合同履约成本审计程序 |
| `F2TabContractCostDetail` | 合同成本明细（按合同/项目归集） |
| `F2TabContractCostCheck` + `F2ContractCostCheckDialog` | 成本归集检查（引导弹窗逐笔核对） |
| `F2TabImpairment` | 合同履约成本减值 |
| `F2TabLossContract` | 亏损合同（预计负债，CAS13 交叉） |
| `F2ContractCostTestExample` / `F2ContractCostTestExampleRef` + `f2ContractCostTestExampleData.ts` | **源模板示例内嵌**：编制界面内直接展示参照示例，可一键套用（非藏在 Drawer 里） |

审计要点：合同履约成本资本化条件（与合同直接相关、增加未来履约资源、预期收回）；
亏损合同确认预计负债 → 与 K5 预计负债、D6 合同资产口径联动。

## 二、IPO 专项（`f2-special/ipo/`）

| 组件 | 核查内容 |
|---|---|
| `F2TabIpoProcedure` | IPO 专项程序 |
| `F2TabSupplierStructure` / `F2TabSupplierChecklist` / `F2TabSupplierInfoCheck` | 供应商结构、清单、工商信息核查 |
| `F2TabInterviewSummary` / `F2TabInterviewDetail` + `F2InterviewCheckExample`(+`f2InterviewCheckExampleData.ts`) | 供应商访谈汇总/明细 + 内嵌示例 |
| `F2TabUnitPrice` / `F2TabPurchasePrice` | 采购单价与价格合理性 |
| `F2TabUnitConsumption` / `F2TabCapacityEnergy` | 单位耗用、产能与能耗匹配（勾稽产量真实性） |
| `F2TabRelatedPartyInquiry` / `F2TabRelatedPartyMarket` / `F2TabUndisclosedParty` | 关联方问询、市场化定价、**未披露关联方识别**（→ B19 关联方清单） |

`f2SoftMatrixStyles.css` / `f2IpoSoftStyles.css` 为矩阵/清单类软性表格样式。

审计要点：IPO 场景关注采购真实性与关联方完整性——供应商结构异常、单价偏离市场、
单位耗用与产能能耗不匹配、疑似未披露关联方，均是舞弊/财务真实性信号，应可回流 B19 与 B50 风险因素。

## 适用性

两组均**非普通年审必做**：合同履约成本仅建造/服务类客户适用；IPO 专项仅 IPO/新三板/重组场景适用。
按平台「适用性自动判断」铁律，不适用时应可整组裁剪而非留空表。
