/**
 * memoTemplates.ts — 跟函备忘录话术模板（按循环分发）
 *
 * 设计原则（e0-confirmation-completion §4）：
 * - `getTemplate(scenario)` 不传 cycle 时行为逐字不变（零回归）
 * - E0 新增五段银行专属话术（逐字取自源模板 E0-7 A8/A9/A10/A12/A14/A15）
 * - `scenariosFor(cycle)` 返回该循环可用的场景列表
 */

import type { ConfirmCycle } from '../confirmationColumnSpec'

export type MemoScenario =
  | 'immediate'       // 通用：即时确认
  | 'later_follow'    // 通用：留函后致电跟踪
  | 'later_received'  // 通用：事后收回补记
  | 'third_party_callback' // 通用：致电被函证方对外公开电话回访核实（源模板 X0-3 A18/A19）
  | 'bank_counter'    // E0：对公柜台办理
  | 'bank_department' // E0：对公柜台不办理转部门
  | 'bank_leave'      // E0：银行无法即时确认留函待寄回
  | 'bank_all_responded' // E0：银行已对全部项目作出回应
  | 'bank_later_received' // E0：事后收回补记

// ─── 通用话术（原有，逐字不变）─────────────────────────────────────────────

/**
 * 即时确认（源模板 X0-3 A10~A13）。
 *
 * 🔴 补两个源模板明确要求、改造前缺失的要素（h0 spec R9.1 / R9.2）：
 * - **陪同情况** —— 源模板 A10 逐字「与[被审计单位XX部XX]一同/或者在无被审计单位人员陪同下独立至」。
 *   有无被审计单位人员陪同是**串通舞弊防范的关键证据**，不能省。
 * - **工号** —— 源模板 A13「工号为[XX]（如有）」。E0 银行版早已有工号概念，通用版此前没有。
 */
export const IMMEDIATE_CONFIRM_TPL = `本人〔followup_staff〕于〔followup_date〕〔escort_desc〕前往〔entity_name〕（地址：〔entity_address〕），就函证事项进行现场跟函。

该函证在〔confirm_location〕办理，办理函证的被函证单位工作人员姓名为〔confirm_contact〕，工号为〔confirm_staff_no〕（如有），身份确认情况：〔confirm_identity_verified〕。

我们取得了由被函证单位确认的询证函，函证索引号〔received_confirm_index〕。确认过程中，本人观察到对方按照正常业务流程处理了函证回复事宜。`

/** 留函后致电跟踪（源模板 X0-3 A15~A17；同样补工号与陪同情况） */
export const LATER_FOLLOW_TPL = `本人〔followup_staff〕于〔leave_date〕〔escort_desc〕前往〔entity_name〕（地址：〔entity_address〕），就函证事项进行现场跟函。

被函证单位人员告知无法现场即时确认该询证函，需详细查询后才可确认，并同意将确认后的询证函直接寄回致同会计师事务所〔received_office〕。本人亲自将询证函交给被函证单位人员〔leave_contact〕（工号〔leave_staff_no〕，如有）办理，并将回邮信封留给该工作人员。

后于〔follow_call_date〕致电〔follow_call_phone〕（号码取自独立公开来源）进行跟踪确认，结果为：〔follow_call_result〕。`

/**
 * 第三方回访核实（源模板 X0-3 A18/A19）。
 *
 * 致电被函证方**对外公开电话**，与其工作人员确认「确实于某日接待过跟函人员」——
 * 这是防范「跟函过程被伪造」的独立验证段，源模板专门写了一段，改造前平台完全没有。
 */
export const THIRD_PARTY_CALLBACK_TPL = `

【回访核实】跟函人员（或项目组其他成员）〔callback_staff〕于〔callback_date〕致电〔entity_name〕对外公开电话〔callback_phone〕（号码取自独立公开来源），与被函证单位工作人员确认其确实于〔followup_date〕接待了我们的跟函人员，并确认了本次询证函。回访结果：〔callback_result〕。`

export const LATER_RECEIVED_TPL = `

【补记】回函已于〔received_date〕收回（办公室：〔received_office〕），对应函证索引号〔received_confirm_index〕。`

// ─── E0 银行专属话术（逐字取自源模板 E0-7 A8/A9/A10/A12/A14/A15）────────

export const BANK_COUNTER_TPL = `审计项目组成员〔bank_team_member〕于〔followup_date〕亲自至〔bank_full_name〕（〔bank_address〕）执行银行函证程序。

该函证是在银行的对公柜台办理，办理函证的银行工作人员为〔bank_staff_name〕，工号为〔bank_staff_no〕，回函信息由函证处理人员根据原始业务记录进行填写，并由主管人员〔bank_reviewer_name〕，工号为〔bank_reviewer_no〕，根据授权复核后在回函上签字并加盖有效印章。我们取得了银行确认的函证，函证的索引号为〔received_confirm_index〕。`

export const BANK_DEPARTMENT_TPL = `由于该银行对公柜台不办理函证业务事宜，我们询问了银行工作人员〔bank_inquiry_staff〕，员工号为〔bank_inquiry_staff_no〕，至银行〔bank_department〕办理，办理函证的银行工作人员为〔bank_staff_name〕，工号〔bank_staff_no〕；复核人员为〔bank_reviewer_name〕，工号〔bank_reviewer_no〕。`

export const BANK_LEAVE_TPL = `审计项目组成员〔bank_team_member〕于〔followup_date〕亲自至〔bank_full_name〕（〔bank_address〕）执行银行函证程序。

银行工作人员〔bank_staff_name〕，员工号为〔bank_staff_no〕，在确认本事务所审计人员身份后收下了询证函。银行无法即时确认询证函所列各项内容，该函证将在确认后寄回致同会计师事务所〔gt_office〕。`

export const BANK_ALL_RESPONDED_TPL = `银行已经对询证函列示的全部项目作出回应。银行回函工作流程、回函用章及银行函证受理部门名称、地址、联系电话与被询证银行管理制度及公示内容一致。`

export const BANK_LATER_RECEIVED_TPL = `该函证于〔received_date〕寄回致同会计师事务所。函证索引号为〔received_confirm_index〕。`

// ─── 模板注册表 ─────────────────────────────────────────────────────────────

const TEMPLATE_MAP: Record<MemoScenario, string> = {
  immediate: IMMEDIATE_CONFIRM_TPL,
  later_follow: LATER_FOLLOW_TPL,
  later_received: LATER_RECEIVED_TPL,
  third_party_callback: THIRD_PARTY_CALLBACK_TPL,
  bank_counter: BANK_COUNTER_TPL,
  bank_department: BANK_DEPARTMENT_TPL,
  bank_leave: BANK_LEAVE_TPL,
  bank_all_responded: BANK_ALL_RESPONDED_TPL,
  bank_later_received: BANK_LATER_RECEIVED_TPL,
}

/**
 * 通用场景集（D0/F0/G0/H0/K0/L0）。
 * `third_party_callback` 是源模板 X0-3 A18/A19 的独立回访段（h0 spec R9.3）。
 */
const GENERIC_SCENARIOS: MemoScenario[] = [
  'immediate',
  'later_follow',
  'later_received',
  'third_party_callback',
]

/** E0 银行专属场景集 */
const E0_SCENARIOS: MemoScenario[] = [
  'bank_counter',
  'bank_department',
  'bank_leave',
  'bank_all_responded',
  'bank_later_received',
]

/**
 * 获取该循环可用的场景列表
 */
export function scenariosFor(cycle?: ConfirmCycle | null): MemoScenario[] {
  if (cycle === 'E0') return E0_SCENARIOS
  return GENERIC_SCENARIOS
}

/**
 * 根据场景获取模板（零回归：不传 cycle/opts 时行为与改造前逐字相同）
 *
 * 兼容两种调用形态：
 * - 旧：getTemplate('immediate', true)  → 第二参为布尔
 * - 新：getTemplate('bank_counter', { cycle: 'E0' })
 */
export function getTemplate(
  scenario: MemoScenario | string,
  opts?: { cycle?: ConfirmCycle | null; laterReceived?: boolean } | boolean,
): string {
  const s = scenario as MemoScenario

  // 旧签名兼容：第二参为布尔值（laterReceived）
  if (typeof opts === 'boolean' || opts === undefined) {
    const laterReceived = typeof opts === 'boolean' ? opts : false
    let tpl = s === 'immediate' ? IMMEDIATE_CONFIRM_TPL : LATER_FOLLOW_TPL
    if (laterReceived) tpl += LATER_RECEIVED_TPL
    return tpl
  }

  // 新签名：opts 为对象
  if (!opts.cycle && opts.laterReceived !== undefined) {
    // 无 cycle 但有 laterReceived → 同旧行为
    let tpl = s === 'immediate' ? IMMEDIATE_CONFIRM_TPL : LATER_FOLLOW_TPL
    if (opts.laterReceived) tpl += LATER_RECEIVED_TPL
    return tpl
  }

  const tpl = TEMPLATE_MAP[s]
  if (!tpl) return TEMPLATE_MAP.immediate
  return tpl
}
