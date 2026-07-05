/**
 * D7 合同负债 — 程序表常量
 */
export const D7_PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取明细', description: '获取合同负债明细表，核对与总账余额一致', isRequired: true, relatedTab: 'detail' },
  { stepName: '核对总账', description: '核对合同负债总账余额与试算平衡表一致', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '预收验证', description: '验证预收款项的真实性，核实收款凭证和合同依据', isRequired: true, relatedTab: null },
  { stepName: '履约进度', description: '检查履约进度计量方法，评估合同负债转收入的时点', isRequired: true, relatedTab: 'analysis' },
  { stepName: '收入时点', description: '判断收入确认时点，检查合同负债转收入的依据是否充分', isRequired: true, relatedTab: 'voucher' },
  { stepName: '截止测试', description: '检查期末前后合同负债确认和转收入的截止是否正确', isRequired: true, relatedTab: null },
  { stepName: '披露检查', description: '检查合同负债相关披露是否完整，包括重大合同条款', isRequired: true, relatedTab: 'disclosure' },
  { stepName: '结论', description: '汇总审计发现，形成合同负债审计结论', isRequired: false, relatedTab: null },
]
