/**
 * D5 应收款项融资 — 程序表常量（对齐 d_cycle_procedures.json）
 */
export const D5_PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取明细', description: '获取应收款项融资明细表，核对与总账余额一致', isRequired: true, relatedTab: 'detail' },
  { stepName: '核对总账', description: '核对应收款项融资总账余额与试算平衡表一致', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '分类评估', description: '评估金融资产分类是否恰当，检查业务模式和合同现金流特征', isRequired: true, relatedTab: 'detail' },
  { stepName: '公允计量', description: '复核以公允价值计量的应收款项融资估值方法和输入值', isRequired: true, relatedTab: 'fair-value' },
  { stepName: '终止确认', description: '检查已终止确认的应收款项融资是否满足终止确认条件', isRequired: true, relatedTab: null },
  { stepName: '减值测试', description: '评估应收款项融资预期信用损失，复核减值准备计提', isRequired: true, relatedTab: null },
  { stepName: '披露检查', description: '检查应收款项融资相关披露是否完整准确', isRequired: true, relatedTab: 'disclosure' },
  { stepName: '结论', description: '汇总审计发现，形成应收款项融资审计结论', isRequired: false, relatedTab: null },
]
