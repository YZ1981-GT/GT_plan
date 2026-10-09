/**
 * 本文件由 `backend/scripts/gen/generate_workpaper_sync_managed_sheets.py` 生成，请勿手工编辑。
 *
 * 真源链（三段全是既有真源，零新增声明）：
 *   `adapters.registry.DELIVERED_PER_ENTRY_CONTRACTS` → contract_id
 *   → `contracts.contract_path_for` → `backend/data/workpaper_sync_contracts/*.json`
 *   → `sheets[].{sheet_key, excel_name}`
 *
 * spec: d567-sync-coverage-via-row-table-engine · Task 22 · Property 15
 *
 * 🔴 `adapterRegistered` 与 `managedSheets` 是**两个分母**：受管清单来自「契约已交付」，
 *    adapter 是否注册另算。前端判「这张 sheet 是否受管」只看 `managedSheets`；
 *    判「OO 能否真用」看 manifest 的 `capability`。别把两者混成一个门。
 *
 * 🔴 `excelName` 是**后端权威 sheet 名**，不要在前端做字符串推演拼页签码 ——
 *    用各循环自己的归一函数（`resolveD5SheetCode` 等）换算。
 */

export interface WorkpaperSyncManagedSheet {
  /** 契约里的受管区键（如 `d52-managed`） */
  readonly sheetKey: string
  /** 模板册里的真实 Excel sheet 名（如 `应收款项融资明细表D5-2`） */
  readonly excelName: string
}

export interface WorkpaperSyncManagedSheetsEntry {
  readonly entryId: string
  readonly contractId: string
  /** adapter 是否已注册 —— **不影响** managedSheets 是否下发 */
  readonly adapterRegistered: boolean
  readonly managedSheets: readonly WorkpaperSyncManagedSheet[]
}

export const WORKPAPER_SYNC_MANAGED_SHEETS_DIGEST = "748326389074a1e03d8f8f32d4e35c06e54ef1b1fb36aabe49c365369c76c9e6"

export const WORKPAPER_SYNC_MANAGED_SHEETS: readonly WorkpaperSyncManagedSheetsEntry[] =
[
  {
    "adapterRegistered": false,
    "contractId": "b60.hour_budget",
    "entryId": "xlsx/b60/gt-b60-bundle",
    "managedSheets": [
      {
        "excelName": "B60-1工时预算与控制表",
        "sheetKey": "b601-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "a51.cashflow_audit",
    "entryId": "xlsx/gt-a51-cashflow-audit",
    "managedSheets": [
      {
        "excelName": "A5-1-1列示于现金流量表的现金及现金等价物",
        "sheetKey": "a511-audit"
      },
      {
        "excelName": "A5-1-3相关报表勾稽关系核对",
        "sheetKey": "a513-reconcile"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "c2.control_test_summary",
    "entryId": "xlsx/gt-c-control-test",
    "managedSheets": [
      {
        "excelName": "C2控制测试汇总表",
        "sheetKey": "c2-summary-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "d1.notes_receivable_detail",
    "entryId": "xlsx/gt-d1-notes-receivable",
    "managedSheets": [
      {
        "excelName": "应收票据监盘D1-10",
        "sheetKey": "d110-managed"
      },
      {
        "excelName": "关联方关系及交易检查表D1-11",
        "sheetKey": "d111-managed"
      },
      {
        "excelName": "应收票据质押检查表D1-12",
        "sheetKey": "d112-managed"
      },
      {
        "excelName": "应收票据检查表D1-13",
        "sheetKey": "d113-managed"
      },
      {
        "excelName": "应收票据坏账准备测试表D1-15",
        "sheetKey": "d115-managed"
      },
      {
        "excelName": "坏账准备转回、核销检查表D1-16",
        "sheetKey": "d116-managed"
      },
      {
        "excelName": "原值明细表（按类别）D1-2",
        "sheetKey": "d12-managed"
      },
      {
        "excelName": "原值明细表（按客户）D1-3",
        "sheetKey": "d13-managed"
      },
      {
        "excelName": "坏账准备明细表D1-4",
        "sheetKey": "d14-managed"
      },
      {
        "excelName": "应收票据备查簿核对D1-7",
        "sheetKey": "d17-managed"
      },
      {
        "excelName": "应收票据贴现、票据已背书未到期明细表D1-8",
        "sheetKey": "d18-managed"
      },
      {
        "excelName": "应收票据贴息检查表D1-9",
        "sheetKey": "d19-managed"
      }
    ]
  },
  {
    "adapterRegistered": true,
    "contractId": "d2.receivable_detail",
    "entryId": "xlsx/gt-d2-accounts-receivable",
    "managedSheets": [
      {
        "excelName": "审定表D2-1",
        "sheetKey": "d21-managed"
      },
      {
        "excelName": "明细表D2-2",
        "sheetKey": "d22-managed"
      },
      {
        "excelName": "坏账准备明细表D2-3",
        "sheetKey": "d23-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "d3.prepaid_receipts_detail",
    "entryId": "xlsx/gt-d3-prepaid-accounts",
    "managedSheets": [
      {
        "excelName": "预收账款明细表D3-2",
        "sheetKey": "d32-managed"
      }
    ]
  },
  {
    "adapterRegistered": true,
    "contractId": "d4.revenue_detail",
    "entryId": "xlsx/gt-d4-operating-revenue",
    "managedSheets": [
      {
        "excelName": "合同检查表D4-12",
        "sheetKey": "d4-12-managed"
      },
      {
        "excelName": "营业收入完整性检查表D4-15",
        "sheetKey": "d4-15-managed"
      },
      {
        "excelName": "出口收入电子口岸系统核对D4-16",
        "sheetKey": "d4-16-managed"
      },
      {
        "excelName": "经销商检查D4-25",
        "sheetKey": "d4-25-managed"
      },
      {
        "excelName": "境外销售收入检查D4-26",
        "sheetKey": "d4-26-managed"
      },
      {
        "excelName": "识别未披露的关联方D4-27",
        "sheetKey": "d4-27-managed"
      },
      {
        "excelName": "客户信息核查清单D4-28",
        "sheetKey": "d4-28-managed"
      },
      {
        "excelName": "客户信息检查表D4-29",
        "sheetKey": "d4-29-managed"
      },
      {
        "excelName": "客户访谈记录汇总表D4-30",
        "sheetKey": "d4-30-managed"
      },
      {
        "excelName": "客户访谈记录 D4-31",
        "sheetKey": "d4-31-managed"
      },
      {
        "excelName": "客户、供应商等资金流水检查D4-32",
        "sheetKey": "d4-32-managed"
      },
      {
        "excelName": "营业收入审定表D4-1",
        "sheetKey": "d41-managed"
      },
      {
        "excelName": "重要客户销售价格分析D4-10",
        "sheetKey": "d410-managed"
      },
      {
        "excelName": "产品销售价格分析D4-11",
        "sheetKey": "d411-managed"
      },
      {
        "excelName": "营业收入账面金额与ERP系统核对记录D4-13",
        "sheetKey": "d413-managed"
      },
      {
        "excelName": "营业收入发生检查表D4-14",
        "sheetKey": "d414-managed"
      },
      {
        "excelName": "营业收入截止测试（账到单据）D4-17",
        "sheetKey": "d417-managed"
      },
      {
        "excelName": "营业收入截止测试（单据到账）D4-18",
        "sheetKey": "d418-managed"
      },
      {
        "excelName": "销售折扣与折让检查D4-19",
        "sheetKey": "d419-managed"
      },
      {
        "excelName": "主营业务收入明细表D4-2",
        "sheetKey": "d42-managed"
      },
      {
        "excelName": "销售退货检查表 D4-20",
        "sheetKey": "d420-managed"
      },
      {
        "excelName": "关联方销售情况及价格分析D4-21",
        "sheetKey": "d421-managed"
      },
      {
        "excelName": "重要指标分析表D4-22",
        "sheetKey": "d422-managed"
      },
      {
        "excelName": "收入与开具发票金额比较分析D4-23",
        "sheetKey": "d423-managed"
      },
      {
        "excelName": "第三方回款检查D4-24",
        "sheetKey": "d424-managed"
      },
      {
        "excelName": "其他业务收入明细表D4-3",
        "sheetKey": "d43-managed"
      },
      {
        "excelName": "其他业务毛利率分析表D4-33",
        "sheetKey": "d433-managed"
      },
      {
        "excelName": "其他业务收入合同测算表D4-34",
        "sheetKey": "d434-managed"
      },
      {
        "excelName": "其他业务收入检查表D4-35",
        "sheetKey": "d435-managed"
      },
      {
        "excelName": "其他业务收入截止性测试D4-36",
        "sheetKey": "d436-managed"
      },
      {
        "excelName": "营业收入会计政策检查D4-5",
        "sheetKey": "d45-managed"
      },
      {
        "excelName": "重要指标分析D4-6",
        "sheetKey": "d46-managed"
      },
      {
        "excelName": "毛利率分析表D4-7",
        "sheetKey": "d47-managed"
      },
      {
        "excelName": "重要产品毛利分析D4-8",
        "sheetKey": "d48-managed"
      },
      {
        "excelName": "重要客户结构分析D4-9",
        "sheetKey": "d49-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "d5.receivables_financing_detail",
    "entryId": "xlsx/gt-d5-receivables-financing",
    "managedSheets": [
      {
        "excelName": "审定表D5",
        "sheetKey": "d51-managed"
      },
      {
        "excelName": "应收款项融资明细表D5-2",
        "sheetKey": "d52-managed"
      },
      {
        "excelName": "应收款项融资公允价值测算表D5-4",
        "sheetKey": "d54-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "d6.contract_assets_detail",
    "entryId": "xlsx/gt-d6-contract-assets",
    "managedSheets": [
      {
        "excelName": "审定表D6-1",
        "sheetKey": "d61-managed"
      },
      {
        "excelName": "明细表D6-2",
        "sheetKey": "d62-managed"
      },
      {
        "excelName": "合同资产减值准备明细表D6-3",
        "sheetKey": "d63-managed"
      },
      {
        "excelName": "关联关系及交易检查D6-5",
        "sheetKey": "d65-managed"
      },
      {
        "excelName": "合同资产检查表D6-6",
        "sheetKey": "d66-managed"
      },
      {
        "excelName": "减值准备测算D6-8",
        "sheetKey": "d68-managed"
      },
      {
        "excelName": "减值准备转回、核销检查表D6-9",
        "sheetKey": "d69-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "d7.contract_liabilities_detail",
    "entryId": "xlsx/gt-d7-contract-liabilities",
    "managedSheets": [
      {
        "excelName": "审定表D7-1",
        "sheetKey": "d71-managed"
      },
      {
        "excelName": "明细表D7-2",
        "sheetKey": "d72-managed"
      },
      {
        "excelName": "合同负债分析表D7-4",
        "sheetKey": "d74-managed"
      },
      {
        "excelName": "账龄1年以上合同负债检查表D7-5",
        "sheetKey": "d75-managed"
      },
      {
        "excelName": "关联方关系及交易检查表D7-6",
        "sheetKey": "d76-managed"
      },
      {
        "excelName": "合同负债检查表D7-7",
        "sheetKey": "d77-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "e1.monetary_fund_detail",
    "entryId": "xlsx/gt-e1-monetary-fund",
    "managedSheets": [
      {
        "excelName": "现金明细表E1-2",
        "sheetKey": "e12-managed"
      },
      {
        "excelName": "数字货币明细表E1-4",
        "sheetKey": "e14-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "f1.prepayment_detail",
    "entryId": "xlsx/gt-f1-prepayment",
    "managedSheets": [
      {
        "excelName": "关联方及交易检查表F1-6",
        "sheetKey": "f16-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "f2.inventory_main",
    "entryId": "xlsx/gt-f2-inventory-main",
    "managedSheets": [
      {
        "excelName": "四、自制半成品明细表F2-6",
        "sheetKey": "f26-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "f2.inventory_special",
    "entryId": "xlsx/gt-f2-inventory-special",
    "managedSheets": [
      {
        "excelName": "合同履约成本减值准备测算表F2-57",
        "sheetKey": "f257-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "f2.inventory_valuation",
    "entryId": "xlsx/gt-f2-inventory-valuation",
    "managedSheets": [
      {
        "excelName": "长库龄 呆滞 超过保质期存货明细表F2-48",
        "sheetKey": "f248-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "f2.stocktake_bundle",
    "entryId": "xlsx/gt-f2-stocktake-bundle",
    "managedSheets": [
      {
        "excelName": "抽盘结果汇总表F2-25",
        "sheetKey": "f225-exist"
      },
      {
        "excelName": "抽盘结果汇总表F2-25",
        "sheetKey": "f225-floor"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "f3.notes_payable_detail",
    "entryId": "xlsx/gt-f3-notes-payable",
    "managedSheets": [
      {
        "excelName": "逾期票据检查F3-5",
        "sheetKey": "f35-managed"
      },
      {
        "excelName": "关联方及交易检查表F3-6",
        "sheetKey": "f36-managed"
      },
      {
        "excelName": "应付票据检查表F3-7",
        "sheetKey": "f37-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "f4.accounts_payable_detail",
    "entryId": "xlsx/gt-f4-accounts-payable",
    "managedSheets": [
      {
        "excelName": "关联方及交易检查表F4-6",
        "sheetKey": "f46-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "f5.cost_of_sales_detail",
    "entryId": "xlsx/gt-f5-cost-of-sales",
    "managedSheets": [
      {
        "excelName": "营业务成本审定表F5-1",
        "sheetKey": "f51-managed"
      },
      {
        "excelName": "重大调整核查表F5-8",
        "sheetKey": "f58-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g1.trading_financial_assets_detail",
    "entryId": "xlsx/gt-g1-trading-financial-assets",
    "managedSheets": [
      {
        "excelName": "明细表G1-2",
        "sheetKey": "g102-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g10.trading_liabilities_detail",
    "entryId": "xlsx/gt-g10-trading-financial-liabilities",
    "managedSheets": [
      {
        "excelName": "明细表G10-2",
        "sheetKey": "g1002-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g11.investment_income_detail",
    "entryId": "xlsx/gt-g11-investment-income",
    "managedSheets": [
      {
        "excelName": "明细分析表G11-2",
        "sheetKey": "g1102-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g12.net_hedge_detail",
    "entryId": "xlsx/gt-g12-net-hedge-gains",
    "managedSheets": [
      {
        "excelName": "明细表G12-2",
        "sheetKey": "g1202-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g13.fair_value_changes_detail",
    "entryId": "xlsx/gt-g13-fair-value-changes",
    "managedSheets": [
      {
        "excelName": "明细表G13-2",
        "sheetKey": "g1302-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g14.credit_impairment_detail",
    "entryId": "xlsx/gt-g14-credit-impairment-loss",
    "managedSheets": [
      {
        "excelName": "明细表G14-2",
        "sheetKey": "g1402-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g2.interest_receivable_detail",
    "entryId": "xlsx/gt-g2-interest-receivable",
    "managedSheets": [
      {
        "excelName": "明细表G2-2",
        "sheetKey": "g202-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g3.dividend_receivable_detail",
    "entryId": "xlsx/gt-g3-dividend-receivable",
    "managedSheets": [
      {
        "excelName": "明细表G3-2",
        "sheetKey": "g302-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g4.bond_main",
    "entryId": "xlsx/gt-g4-bond-investment-main",
    "managedSheets": [
      {
        "excelName": "有价证券盘点表G4-7",
        "sheetKey": "g407-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g5.long_term_receivable_detail",
    "entryId": "xlsx/gt-g5-long-term-receivable",
    "managedSheets": [
      {
        "excelName": "余额明细表G5-2",
        "sheetKey": "g502-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g6.other_bond_main",
    "entryId": "xlsx/gt-g6-other-bond-main",
    "managedSheets": [
      {
        "excelName": "公允价值测试表G6-5",
        "sheetKey": "g605-managed"
      }
    ]
  },
  {
    "adapterRegistered": true,
    "contractId": "g7.soe_subsidiary_disclosure",
    "entryId": "xlsx/gt-g7-long-term-equity-main",
    "managedSheets": [
      {
        "excelName": "附注披露信息（国企）",
        "sheetKey": "g7n-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g8.other_equity_detail",
    "entryId": "xlsx/gt-g8-other-equity-instruments",
    "managedSheets": [
      {
        "excelName": "明细表G8-2",
        "sheetKey": "g802-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "g9.other_noncurrent_detail",
    "entryId": "xlsx/gt-g9-other-noncurrent-financial",
    "managedSheets": [
      {
        "excelName": "明细表G9-2",
        "sheetKey": "g902-managed"
      }
    ]
  },
  {
    "adapterRegistered": true,
    "contractId": "h1.disposal_check",
    "entryId": "xlsx/gt-h1-fixed-assets",
    "managedSheets": [
      {
        "excelName": "减少检查表H1-8",
        "sheetKey": "h18-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "h10.asset_disposal_income_adjustment",
    "entryId": "xlsx/gt-h10-asset-disposal-income",
    "managedSheets": [
      {
        "excelName": "调整分录汇总H10-3",
        "sheetKey": "h1003-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "h2.construction_in_progress_detail",
    "entryId": "xlsx/gt-h2-construction-in-progress",
    "managedSheets": [
      {
        "excelName": "明细表H2-2",
        "sheetKey": "h202-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "h3.investment_property_detail",
    "entryId": "xlsx/gt-h3-investment-property",
    "managedSheets": [
      {
        "excelName": "明细表（成本模式）H3-2",
        "sheetKey": "h302cost-managed"
      },
      {
        "excelName": "明细表（公允价值模式）H3-2",
        "sheetKey": "h302fair-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "h4.engineering_materials_detail",
    "entryId": "xlsx/gt-h4-engineering-materials",
    "managedSheets": [
      {
        "excelName": "明细表H4-2",
        "sheetKey": "h402-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "h5.oil_gas_assets_detail",
    "entryId": "xlsx/gt-h5-oil-gas-assets",
    "managedSheets": [
      {
        "excelName": "明细表H5-2",
        "sheetKey": "h502-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "h6.asset_disposal_clearing_detail",
    "entryId": "xlsx/gt-h6-asset-disposal-clearing",
    "managedSheets": [
      {
        "excelName": "明细表H6-2",
        "sheetKey": "h602-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "h7.biological_assets_detail",
    "entryId": "xlsx/gt-h7-biological-assets",
    "managedSheets": [
      {
        "excelName": "明细表（成本模式）H7-2",
        "sheetKey": "h702cost-managed"
      },
      {
        "excelName": "明细表（公允价值模式）H7-2",
        "sheetKey": "h702fair-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "h8.right_of_use_assets_detail",
    "entryId": "xlsx/gt-h8-right-of-use-assets",
    "managedSheets": [
      {
        "excelName": "明细表H8-2",
        "sheetKey": "h802-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "h9.lease_liability_detail",
    "entryId": "xlsx/gt-h9-lease-liabilities",
    "managedSheets": [
      {
        "excelName": "租赁负债明细表H9-2",
        "sheetKey": "h902-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "i1.intangible_assets_detail",
    "entryId": "xlsx/gt-i1-intangible-assets",
    "managedSheets": [
      {
        "excelName": "明细表I1-2",
        "sheetKey": "i12-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "i2.development_expenditure_detail",
    "entryId": "xlsx/gt-i2-development-expenditure",
    "managedSheets": [
      {
        "excelName": "明细表I2-2",
        "sheetKey": "i22-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "i3.goodwill_detail",
    "entryId": "xlsx/gt-i3-goodwill",
    "managedSheets": [
      {
        "excelName": "明细表I3-2",
        "sheetKey": "i32-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "i4.long_term_prepaid_detail",
    "entryId": "xlsx/gt-i4-long-term-prepaid",
    "managedSheets": [
      {
        "excelName": "明细表I4-2",
        "sheetKey": "i42-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "i5.other_noncurrent_assets_detail",
    "entryId": "xlsx/gt-i5-other-noncurrent-assets",
    "managedSheets": [
      {
        "excelName": "明细表I5-2",
        "sheetKey": "i52-gross-managed"
      },
      {
        "excelName": "明细表I5-2",
        "sheetKey": "i52-impairment-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "i6.research_development_expense_detail",
    "entryId": "xlsx/gt-i6-research-development-expense",
    "managedSheets": [
      {
        "excelName": "明细表I6-2",
        "sheetKey": "i62-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "l1.short_term_loans",
    "entryId": "xlsx/gt-l1-short-term-loans",
    "managedSheets": [
      {
        "excelName": "明细表L1-2",
        "sheetKey": "l12-managed"
      }
    ]
  },
  {
    "adapterRegistered": false,
    "contractId": "j1.accrual_check_short_term",
    "entryId": "xlsx/j1/gt-j1-employee-compensation",
    "managedSheets": [
      {
        "excelName": "计提情况检查表J1-6",
        "sheetKey": "j16-short-term-managed"
      }
    ]
  }
] as const

/** entry_id → 受管 sheet 清单（未登记 entry 返回空数组，fail-closed 为「无受管 sheet」）。 */
export function managedSheetsForEntry(
  entryId: string,
): readonly WorkpaperSyncManagedSheet[] {
  const hit = WORKPAPER_SYNC_MANAGED_SHEETS.find((e) => e.entryId === entryId)
  return hit ? hit.managedSheets : []
}
