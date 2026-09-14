/**
 * b23CycleConfig — B23 业务层面控制单一循环配置源
 *
 * Spec: .kiro/specs/b23-business-control-rework/ | Task: 1.1
 *
 * 单一真源（Property P3）：仪表盘循环集合、附件入口、联动映射、目录节点全部从
 * B23_CYCLES 派生，消除标签错位类 bug。cTests/substantiveCycles 对齐后端
 * wp_dependency_service.CYCLE_DEPENDENCIES。
 */

/** 循环定义 */
export interface B23CycleDef {
  /** 循环 item_id 键，如 'c1'..'c15'、'cxx5' */
  code: string
  /** 子底稿编码，如 'B23-1'..'B23-15'、'B23-XX-5' */
  wpCode: string
  /** 循环名称 */
  name: string
  /** 对应科目循环字母：D/E/F...Q（B23-15/XX-5 为空） */
  subjectCycle: string
  /** 关联 C 类控制测试 wp_code（对齐 CYCLE_DEPENDENCIES） */
  cTests: string[]
  /** 关联 D~N 实质性程序循环字母 */
  substantiveCycles: string[]
  /** 预置子流程骨架（源模板，供点选套用，可增删） */
  defaultSubProcesses: string[]
  /** B23-15 / B23-XX-5 标记（非标准 14 循环） */
  isSpecial?: boolean
}

/**
 * 14 循环 + B23-15 信息处理控制 + B23-XX-5 职责分离通用模板。
 * defaultSubProcesses 取自致同源模板 BCD类底稿md/{cycle}/B23-N...业务层面控制底稿模板库.md。
 */
export const B23_CYCLES: readonly B23CycleDef[] = [
  {
    code: 'c1', wpCode: 'B23-1', name: '销售循环', subjectCycle: 'D',
    cTests: ['C2'], substantiveCycles: ['D'],
    defaultSubProcesses: ['客户信用管理', '销售订单', '组织发货', '开具发票', '收款与对账', '坏账准备计提'],
  },
  {
    code: 'c2', wpCode: 'B23-2', name: '货币资金', subjectCycle: 'E',
    cTests: ['C3'], substantiveCycles: ['E'],
    defaultSubProcesses: ['货币资金收款', '货币资金付款', '银行对账', '资金计划与审批'],
  },
  {
    code: 'c3', wpCode: 'B23-3', name: '存货循环', subjectCycle: 'F',
    cTests: ['C4'], substantiveCycles: ['F'],
    defaultSubProcesses: ['采购申请与审批', '入库验收', '领用发出', '存货盘点', '存货跌价准备'],
  },
  {
    code: 'c4', wpCode: 'B23-4', name: '投资循环', subjectCycle: 'G',
    cTests: ['C5'], substantiveCycles: ['G'],
    defaultSubProcesses: ['投资决策与审批', '投资执行', '投资后续计量', '投资处置'],
  },
  {
    code: 'c5', wpCode: 'B23-5', name: '固定资产', subjectCycle: 'H',
    cTests: ['C6'], substantiveCycles: ['H'],
    defaultSubProcesses: ['购建申请与审批', '验收入账', '折旧计提', '处置报废', '实物盘点'],
  },
  {
    code: 'c6', wpCode: 'B23-6', name: '在建工程', subjectCycle: 'H',
    cTests: ['C7'], substantiveCycles: ['H'],
    defaultSubProcesses: ['项目立项与预算', '工程款支付', '工程进度管理', '转固'],
  },
  {
    code: 'c7', wpCode: 'B23-7', name: '无形资产', subjectCycle: 'I',
    cTests: ['C8'], substantiveCycles: ['I'],
    defaultSubProcesses: ['取得与审批', '摊销计提', '减值测试', '处置'],
  },
  {
    code: 'c8', wpCode: 'B23-8', name: '研发循环', subjectCycle: 'I',
    cTests: ['C9'], substantiveCycles: ['I'],
    defaultSubProcesses: ['研发立项', '费用归集', '资本化判断', '研发成果管理'],
  },
  {
    code: 'c9', wpCode: 'B23-9', name: '职工薪酬', subjectCycle: 'J',
    cTests: ['C10'], substantiveCycles: ['J'],
    defaultSubProcesses: ['考勤管理', '薪酬计算', '薪酬审批与发放', '社保公积金'],
  },
  {
    code: 'c10', wpCode: 'B23-10', name: '管理循环', subjectCycle: 'K',
    cTests: ['C11'], substantiveCycles: ['K'],
    defaultSubProcesses: ['费用申请与审批', '费用报销', '费用核算'],
  },
  {
    code: 'c11', wpCode: 'B23-11', name: '税金循环', subjectCycle: 'N',
    cTests: ['C12'], substantiveCycles: ['D', 'N'],
    defaultSubProcesses: ['税金计算', '纳税申报', '税款缴纳', '税务备案'],
  },
  {
    code: 'c12', wpCode: 'B23-12', name: '债务循环', subjectCycle: 'L',
    cTests: ['C13'], substantiveCycles: ['L'],
    defaultSubProcesses: ['借款申请与审批', '借款到账', '利息计提', '还本付息'],
  },
  {
    code: 'c13', wpCode: 'B23-13', name: '租赁循环', subjectCycle: 'H',
    cTests: ['C14'], substantiveCycles: ['H'],
    defaultSubProcesses: ['租赁识别与审批', '租赁计量', '租赁付款', '租赁变更'],
  },
  {
    code: 'c14', wpCode: 'B23-14', name: '关联方及交易', subjectCycle: 'Q',
    cTests: ['C15'], substantiveCycles: ['Q'],
    defaultSubProcesses: ['关联方识别', '关联交易审批', '关联交易定价', '关联交易披露'],
  },
  {
    code: 'c15', wpCode: 'B23-15', name: '信息处理控制', subjectCycle: '',
    cTests: ['C26'], substantiveCycles: [], isSpecial: true,
    defaultSubProcesses: ['信息系统输入控制', '信息系统处理控制', '信息系统输出控制'],
  },
  {
    code: 'cxx5', wpCode: 'B23-XX-5', name: '职责分离（通用）', subjectCycle: '',
    cTests: [], substantiveCycles: [], isSpecial: true,
    defaultSubProcesses: ['不相容职责识别', '职责分离矩阵'],
  },
]

/** 附件入口（供附件 Tab；标签与 code 同源，杜绝错位） */
export interface B23AttachmentEntry {
  code: string
  wpCode: string
  label: string
}

export function attachmentEntries(): B23AttachmentEntry[] {
  return B23_CYCLES.map((c) => ({ code: c.code, wpCode: c.wpCode, label: c.name }))
}

/** 按 code 取循环定义 */
export function cycleByCode(code: string): B23CycleDef | undefined {
  return B23_CYCLES.find((c) => c.code === code)
}

/** 按 wpCode 取循环定义（供后端事件 cycle 映射对齐） */
export function cycleByWpCode(wpCode: string): B23CycleDef | undefined {
  return B23_CYCLES.find((c) => c.wpCode === wpCode)
}

/** 全部循环 code 列表 */
export const B23_CYCLE_CODES: readonly string[] = B23_CYCLES.map((c) => c.code)

export default B23_CYCLES
