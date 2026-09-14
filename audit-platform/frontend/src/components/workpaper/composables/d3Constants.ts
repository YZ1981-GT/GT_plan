/**
 * D3 预收账款 — 共享常量
 */
export const D3_PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取明细', description: '获取预收账款明细表，复核加计正确性', isRequired: true, relatedTab: 'detail' },
  { stepName: '核对总账', description: '核对预收账款总账与明细账、报表一致', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '分析程序', description: '实施预收账款分析程序，关注异常波动', isRequired: true, relatedTab: 'analysis' },
  { stepName: '账龄检查', description: '检查账龄1年以上预收账款的性质与结转', isRequired: true, relatedTab: 'longterm' },
  { stepName: '关联方检查', description: '检查关联方预收账款及交易价格公允性', isRequired: true, relatedTab: 'related-party' },
  { stepName: '凭证检查', description: '对重要预收账款实施凭证核对与期后结转测试', isRequired: true, relatedTab: 'voucher' },
  { stepName: '披露检查', description: '检查预收账款附注披露完整性', isRequired: true, relatedTab: 'disclosure' },
  { stepName: '结论', description: '汇总预收账款审计发现，形成整体结论', isRequired: false, relatedTab: null },
]
