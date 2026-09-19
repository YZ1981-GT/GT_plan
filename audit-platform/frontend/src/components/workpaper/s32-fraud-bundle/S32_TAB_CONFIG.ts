/**
 * S32 Fraud Response Bundle — Tab & Sub-Sheet 映射表
 *
 * 来源：Phase0 双源核对，源模板 openpyxl 读取 + 底稿模板库 md 交叉验证
 * 产出日期：2026-07（Task 1 of s32-fraud-response-bundle spec）
 *
 * 结构：13 舞弊情形 Tab，每个 Tab 对应一个 S32-x 底稿
 *   - programSheet: 核查程序表（IC 程序表）sheet 名
 *   - guidanceSheet: IC-0 导引表（仅 S32-6/9/10 有）
 *   - disclosureSheet: IC-X 披露格式参考（仅 S32-6/9/10 有）
 *   - tipSheet: 提示 sheet（部分底稿有）
 *
 * Requirements: 3.1, 3.3, 3.4
 */

export interface S32TabDef {
  /** Tab id，对应 wp_code（如 'S32-1'） */
  id: string
  /** Tab 标签简称（舞弊情形） */
  label: string
  /** 底稿编码 */
  wpCode: string
  /** 程序表 sheet 名（源模板中实际 sheet name） */
  programSheet: string
  /** IC-0 导引表 sheet 名（可选） */
  guidanceSheet?: string
  /** IC-X 披露格式参考 sheet 名（可选） */
  disclosureSheet?: string
  /** 提示 sheet 名（可选） */
  tipSheet?: string
}

/**
 * 13 舞弊情形完整 Tab 配置
 *
 * 数据来源：openpyxl 读取源模板 S32-1~13.xlsx（2025年修订版）
 * GT_Custom 为系统元数据 sheet，不纳入用户可见 Tab 映射
 */
export const S32_FRAUD_TABS: S32TabDef[] = [
  {
    id: 'S32-1',
    label: '自我交易虚增利润',
    wpCode: 'S32-1',
    programSheet: 'S32程序表IC1',
    tipSheet: '提示',
  },
  {
    id: 'S32-2',
    label: '恶意串通提前确认收入',
    wpCode: 'S32-2',
    programSheet: 'S32程序表IC2',
    tipSheet: '提示',
  },
  {
    id: 'S32-3',
    label: '关联方代付成本费用',
    wpCode: 'S32-3',
    programSheet: 'S32程序表IC3',
    tipSheet: '提示',
  },
  {
    id: 'S32-4',
    label: '保荐机构PE利益输送',
    wpCode: 'S32-4',
    programSheet: 'S32程序表IC4',
    tipSheet: '提示',
  },
  {
    id: 'S32-5',
    label: '体外资金支付货款',
    wpCode: 'S32-5',
    programSheet: 'S32程序表IC5',
    tipSheet: '提示',
  },
  {
    id: 'S32-6',
    label: '互联网造假虚增收入',
    wpCode: 'S32-6',
    programSheet: 'S32程序表IC6',
    guidanceSheet: 'IC6-0导引表',
    disclosureSheet: '互联网造假虚增收入披露格式参考IC6-X',
    tipSheet: '提示',
  },
  {
    id: 'S32-7',
    label: '成本费用资本化',
    wpCode: 'S32-7',
    programSheet: 'S32-7程序表',
  },
  {
    id: 'S32-8',
    label: '压缩员工薪金',
    wpCode: 'S32-8',
    programSheet: 'S32-8程序表',
  },
  {
    id: 'S32-9',
    label: '延迟成本费用',
    wpCode: 'S32-9',
    programSheet: 'S32-9程序表',
    guidanceSheet: 'IC9-0导引表',
    disclosureSheet: '延迟成本费用增加利润披露格式参考IC9-X',
    tipSheet: '提示',
  },
  {
    id: 'S32-10',
    label: '资产减值估计不足',
    wpCode: 'S32-10',
    programSheet: 'S32-10程序表',
    guidanceSheet: 'IC10-0导引表',
    disclosureSheet: '资产减值估计不足披露格式参考IC10-X',
    tipSheet: '提示',
  },
  {
    id: 'S32-11',
    label: '延迟资产转固减少折旧',
    wpCode: 'S32-11',
    programSheet: 'S32程序表',
  },
  {
    id: 'S32-12',
    label: '其他粉饰业绩',
    wpCode: 'S32-12',
    programSheet: 'S32程序表',
  },
  {
    id: 'S32-13',
    label: '期后业绩下滑',
    wpCode: 'S32-13',
    programSheet: 'S32-13程序表',
  },
]

/** 所有 S32 wp_code 集合（用于 skip 映射校验） */
export const S32_WP_CODES = S32_FRAUD_TABS.map((t) => t.wpCode) as readonly string[]

/** 含导引表的底稿编码集合 */
export const S32_WITH_GUIDANCE = S32_FRAUD_TABS
  .filter((t) => t.guidanceSheet)
  .map((t) => t.wpCode) as readonly string[]

/** 含披露格式参考的底稿编码集合 */
export const S32_WITH_DISCLOSURE = S32_FRAUD_TABS
  .filter((t) => t.disclosureSheet)
  .map((t) => t.wpCode) as readonly string[]

/** 含提示 sheet 的底稿编码集合 */
export const S32_WITH_TIPS = S32_FRAUD_TABS
  .filter((t) => t.tipSheet)
  .map((t) => t.wpCode) as readonly string[]
