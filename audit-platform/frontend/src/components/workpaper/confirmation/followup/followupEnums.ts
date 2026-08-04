/**
 * followupEnums.ts — D0-3 跟函函证过程控制 枚举字典 key
 */
export { CONFIRMATION_DICT_KEYS } from '../coordination/confirmationDicts'

export const FOLLOWUP_DICT_KEYS = {
  SCENARIO: 'confirmation_followup_scenario',
  YES_NO_NA: 'yes_no_na',
} as const

/**
 * 三项控制检查的**源模板逐字标签**（X0-3 `A23:A25`）。
 *
 * 🔴 改造前 UI 用的是意译短标签（「了解处理流程」/「确认身份权限」/「按正常流程处理」），
 * 与源模板措辞不一致 —— 源模板问的是「是否了解处理函证的通常流程**和处理人员**」
 * （多了「处理人员」这一层）、「是否确认询证函处理人员的身份**及权限**」。
 * 底稿是交付物，核对点措辞须与源模板一致。
 *
 * 六枢纽（D0/F0/G0/H0/K0/L0）的 X0-3 该三行逐字相同 → 共用一份常量。
 *
 * spec: h0-confirmation-source-fidelity-and-linkage R9.4
 */
export const FOLLOWUP_CONTROL_CHECKPOINTS = [
  {
    field: 'control_process',
    /** 源模板 A23 逐字 */
    label: '是否了解处理函证的通常流程和处理人员',
    anchor: 'A23',
    hint: '是否了解了对方单位处理函证回复的内部流程（收函→核对→签章→寄回）及具体处理人员',
  },
  {
    field: 'control_identity',
    /** 源模板 A24 逐字 */
    label: '是否确认询证函处理人员的身份及权限',
    anchor: 'A24',
    hint: '是否核实了处理人的身份及其是否有权代表公司确认函证内容（如索要名片、观察员工卡或姓名牌）',
  },
  {
    field: 'control_normal_flow',
    /** 源模板 A25 逐字 */
    label: '处理人员是否按正常流程处理',
    anchor: 'A25',
    hint: '观察到该人员是否在其计算机系统或相关记录中核对相关信息（非临时指派、非异常加急操作）',
  },
] as const
