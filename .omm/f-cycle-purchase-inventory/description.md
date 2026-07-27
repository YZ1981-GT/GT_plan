# F 采购与付款 / 存货循环

F 循环覆盖采购付款与存货，是**全平台体量最大的循环**：F2 存货一个科目被拆成 **4 个 componentType**
（主体 / 特殊存货 / 计价与减值 / 监盘），加上 F1/F3/F4/F5 共 8 个渲染入口。

## 组成

| 元素 | 科目 | componentType | 后端 render 策略 |
|---|---|---|---|
| F0 函证 | — | 复用 D0 `confirmation-*` | — |
| F1 预付账款 | 1123 | `f1-prepayment` | `_f1_prepayment.py` |
| F2 存货（主体） | 1401~1411 原值 / 1412 进销差价 / 1471 跌价准备 | `f2-inventory-main` | `_f2_inventory_main.py` |
| F2 存货（计价与减值） | 同上 | `f2-inventory-valuation-impairment` | `_f2_inventory_valuation_impairment.py` |
| F2 存货（特殊存货） | 同上 | `f2-inventory-special` | `_f2_inventory_special.py` |
| F2 存货（监盘） | 同上 | `f2-stocktake-bundle` | `_f2_stocktake.py` |
| F3 应付票据 | 2201 | `f3-notes-payable` | `_f3_notes_payable.py` |
| F4 应付账款 | 2202 | `f4-accounts-payable` | `_f4_accounts_payable.py` |
| F5 营业成本 | 6401 | `f5-cost-of-sales` | `_f5_cost_of_sales.py` |

## 为什么 F2 被拆成四个入口

存货底稿在源模板里是**多个独立工作簿**（存货主体、存货计价与跌价、特殊行业存货、存货监盘），
sheet 总量远超单个专属组件可维护的规模，且四组的审计目的不同：

- **主体**：审定 / 明细 / 调整 / 披露 / 整体分析 / 产销量 / 政策
- **计价与减值**：先进先出与移动平均计价测试、标准成本、生产成本 / 制造费用 / 直接人工归集、采购入库检查、材料领用检查、委外加工、关联采购、跌价测试与转回、呆滞存货
- **特殊存货**：合同履约成本（含亏损合同）+ IPO 专项（供应商结构 / 访谈 / 单位耗用 / 产能能耗 / 采购价格 / 未披露关联方）
- **监盘**：计划 / 程序 / 问卷 / 抽盘结果 / 差异调节 / 倒轧 / 小结

四者共享 F2 的审定表与科目模型（`f2AccountModel.ts`），但各自独立渲染、独立持久化 sheet。

## F 循环的两条主脉

1. **采购—应付—存货**：F1 预付 → F2 存货入库 → F4 应付账款 → 付款（E1 货币资金）
2. **存货—成本—收入**：F2 存货 → F5 营业成本 → D4 营业收入（毛利率勾稽）

F3 应付票据是付款方式的一种（票据结算），与 F4、E1、L1 短期借款（票据贴现/敞口）相关。
