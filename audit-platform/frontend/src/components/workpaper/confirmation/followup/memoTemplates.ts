/**
 * memoTemplates.ts — D0-3 备忘录话术模板
 */

export const IMMEDIATE_CONFIRM_TPL = `本人于〔followup_date〕前往〔entity_name〕（地址：〔entity_address〕），就函证事项进行现场跟函。

到达后，经确认联系人〔confirm_contact〕身份（〔confirm_identity_verified〕），在〔confirm_location〕对函证内容进行了当面确认。

确认过程中，本人观察到对方按照正常业务流程处理了函证回复事宜。`

export const LATER_FOLLOW_TPL = `本人于〔leave_date〕前往〔entity_name〕（地址：〔entity_address〕），就函证事项进行现场跟函。

因无法即时确认，将询证函留置于联系人〔leave_contact〕处。

后于〔follow_call_date〕致电〔follow_call_phone〕（号码取自独立公开来源）进行跟踪确认，结果为：〔follow_call_result〕。`

export const LATER_RECEIVED_TPL = `

【补记】回函已于〔received_date〕收回（办公室：〔received_office〕），对应函证索引号〔received_confirm_index〕。`

/** 根据场景获取模板 */
export function getTemplate(scenario: string, laterReceived?: boolean): string {
  let tpl = scenario === 'immediate' ? IMMEDIATE_CONFIRM_TPL : LATER_FOLLOW_TPL
  if (laterReceived) tpl += LATER_RECEIVED_TPL
  return tpl
}
