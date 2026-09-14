/**
 * D4 营业收入 — 程序表常量
 */
export const D4_PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取明细', description: '获取主营业务收入及其他业务收入明细，复核加计正确', isRequired: true, relatedTab: 'revenue-detail' },
  { stepName: '核对总账', description: '核对营业收入总账与明细账、报表一致', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '分析程序', description: '实施毛利率、客户结构等重要指标分析', isRequired: true, relatedTab: 'indicator' },
  { stepName: '合同检查', description: '检查销售合同条款与收入确认政策一致性', isRequired: true, relatedTab: 'contract' },
  { stepName: '发生测试', description: '对重要交易实施发生认定检查', isRequired: true, relatedTab: 'occurrence' },
  { stepName: '完整性测试', description: '实施完整性认定检查程序', isRequired: true, relatedTab: 'completeness' },
  { stepName: '截止测试', description: '实施截止性测试（账到单据/单据到账）', isRequired: true, relatedTab: 'cutoff-forward' },
  { stepName: '披露检查', description: '检查营业收入附注披露完整性', isRequired: true, relatedTab: 'disclosure' },
  { stepName: '结论', description: '汇总营业收入审计发现，形成整体结论', isRequired: false, relatedTab: null },
]
