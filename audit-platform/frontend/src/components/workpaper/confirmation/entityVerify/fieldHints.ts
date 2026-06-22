/**
 * fieldHints.ts — D0-2 字段提示（说明1-5 就近呈现）
 *
 * 说明1：企查查核对注意事项（落位于 qcc_address 字段）
 * 说明2：退回原因分析（落位于 return_reason 字段）
 * 说明3：退回原因合理性判断标准（落位于 reason_reasonable 字段）
 * 说明4：二次发函注意事项（落位于 second_result 字段）
 * 说明5：电子函证可靠性提示（落位于 reply_method 字段，当 is_electronic=true）
 */

export interface FieldHint {
  field: string
  title: string
  content: string
  condition?: string  // 显示条件描述
}

export const FIELD_HINTS: FieldHint[] = [
  {
    field: 'qcc_address',
    title: '说明1：企查查/天眼查核对',
    content: '注册会计师应通过企查查、天眼查等独立渠道核实被函证单位的注册信息，包括全称、注册地址、法定代表人等，确认被函证单位真实存在且信息准确。如信息不一致，应进一步调查原因。',
  },
  {
    field: 'return_reason',
    title: '说明2：退回原因分析',
    content: '函证退回的常见原因包括：地址错误、单位搬迁、单位注销/不存在、拒绝回函、邮寄丢失等。注册会计师应分析退回原因是否合理，对于"单位不存在"等异常退回应重点关注并作为舞弊风险迹象。',
  },
  {
    field: 'reason_reasonable',
    title: '说明3：退回原因合理性',
    content: '判断标准：\n- 合理：地址变更有工商变更记录、邮寄丢失可重新发送\n- 不合理：查无此单位（伪造交易风险）、多次退回同一原因（虚构对手方可能）、拒绝回函但无合理解释\n\n不合理退回应提升为舞弊风险迹象(D0-8)。',
  },
  {
    field: 'second_result',
    title: '说明4：二次发函',
    content: '对首次退回且原因合理的函证，应在更正信息后进行第二次发函。若二次仍退回，需执行替代审计程序(D0-5/D0-6)并重点关注舞弊风险。',
  },
  {
    field: 'reply_method',
    title: '说明5：电子函证可靠性',
    content: '通过电子邮件或电子函证平台（如确函宝、e-确认）收到的回函，注册会计师应评估其可靠性，包括：\n1. 确认平台的安全性和可靠性\n2. 确认发送方身份的真实性\n3. 评估传输过程中被篡改的风险\n\n详见D0-7回函可靠性验证。',
    condition: 'is_electronic === true',
  },
]

/** 根据字段名获取对应提示 */
export function getFieldHint(field: string): FieldHint | undefined {
  return FIELD_HINTS.find(h => h.field === field)
}
