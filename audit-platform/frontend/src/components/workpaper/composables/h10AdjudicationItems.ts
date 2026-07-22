/** H10-1 审定表行定义 — 与 xlsx 审定表 H10-1 行 6–12 一致 */

export interface H10AdjudicationLineDef {
  rowKey: string
  label: string
}

export const H10_ADJUDICATION_ITEMS: H10AdjudicationLineDef[] = [
  {
    rowKey: 'hfs_disposal',
    label: '持有待售的非流动资产（处置组）处置利得（损失以"-"填列）',
  },
  {
    rowKey: 'fixed_asset_disposal',
    label: '固定资产处置利得（损失以"-"填列）',
  },
  {
    rowKey: 'construction_disposal',
    label: '在建工程处置利得（损失以"-"填列）',
  },
  {
    rowKey: 'productive_bio_disposal',
    label: '生产性生物资产处置利得（损失以"-"填列）',
  },
  {
    rowKey: 'intangible_disposal',
    label: '无形资产处置利得（损失以"-"填列）',
  },
  {
    rowKey: 'debt_restructuring_disposal',
    label: '债务重组中因处置非流动资产产生的利得（损失以"-"填列）',
  },
  {
    rowKey: 'non_monetary_exchange',
    label: '非货币性资产交换产生的利得（损失以"-"填列）',
  },
  {
    rowKey: 'rou_disposal',
    label: '使用权资产处置利得（损失以"-"填列）',
  },
  {
    rowKey: 'oil_gas_disposal',
    label: '油气资产处置利得（损失以"-"填列）',
  },
  {
    rowKey: 'trial_operation_sales',
    label: '试运行销售损益（损失以"-"填列）',
  },
]
