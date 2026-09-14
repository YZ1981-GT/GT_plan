/**
 * D6 合同资产 — 程序表常量
 */
export const D6_PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取明细', description: '获取合同资产明细表，核对与总账余额一致', isRequired: true, relatedTab: 'detail' },
  { stepName: '核对总账', description: '核对合同资产总账余额与试算平衡表一致', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '合同识别', description: '识别合同并检查合同资产确认条件是否满足', isRequired: true, relatedTab: 'inspection' },
  { stepName: '履约分析', description: '分析履约义务的识别和分摊是否恰当', isRequired: true, relatedTab: null },
  { stepName: '可变对价', description: '评估可变对价估计的合理性及约束条件', isRequired: true, relatedTab: null },
  { stepName: '进度计量', description: '检查履约进度计量方法及合同资产确认金额的合理性', isRequired: true, relatedTab: null },
  { stepName: '减值评估', description: '评估合同资产是否存在减值迹象并复核减值准备', isRequired: true, relatedTab: 'ecl' },
  { stepName: '结论', description: '汇总审计发现，形成合同资产审计结论', isRequired: false, relatedTab: null },
]
