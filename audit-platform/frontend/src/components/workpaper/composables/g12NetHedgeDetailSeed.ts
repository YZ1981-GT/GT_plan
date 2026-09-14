/** G12-2 示例行 — 对齐源模板「净敞口套期收益明细表」 */
export const G12_NET_HEDGE_DETAIL_SEED = [
  {
    item: '预测销售和预测采购的外汇净头寸',
    netPosition: '支付200万美元',
    hedgingInstrument: '购入200万美元的外汇远期合约',
    rowKind: 'fv_allocation' as const,
    instrumentFvCumulative: -200_000,
    salesPortion: 1_000_000,
    purchasePortion: -1_200_000,
    indexRef: '',
    remark: '',
  },
  {
    item: '套期调整摊销',
    netPosition: '',
    hedgingInstrument: '',
    rowKind: 'amortization' as const,
    hedgeAdjAmortization: -240_000,
    indexRef: '',
    remark: '',
  },
]

export const G12_NET_HEDGE_DETAIL_OBJECTIVE =
  '获取并记录所有应确认的净敞口套期损益，核对套期工具公允价值变动在销售/采购部分的拆分及摊销影响，确保财务报表披露完整。'

export const G12_NET_HEDGE_DETAIL_GUIDANCE = [
  '1. 本表核算被套期项目或现金流量套期储备转入当期损益的累计公允价值变动。',
  '2. 公允价值套期：Dr/Cr 被套期项目 ↔ 套期工具；现金流量套期：Dr/Cr 其他综合收益—套期储备 ↔ 存货等。',
  '3. 「校验」= 销售部分 + 采购部分 = 套期工具累计公允价值变动；净敞口套期损益 = 销售部分 + 摊销行。',
  '4. 审计说明应列示测试程序、调整事项；审计结论可选「A 未见异常 / B 除上述调整外未见异常 / C 存在重大未调整事项」。',
]
