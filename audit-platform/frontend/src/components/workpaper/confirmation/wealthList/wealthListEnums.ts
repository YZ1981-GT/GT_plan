/**
 * wealthListEnums.ts — E0-6 理财产品发函记录表 枚举
 *
 * 枚举值一律取自源模板：
 * - `产品类型（封闭式/开放式）`：列名自带的括注枚举（E5）
 * - `是否被用于担保或存在其他使用限制`：源模板数据验证 `K6:K10` list `"是,否"`
 *   （源模板 DV 范围只到 K10 而数据区到 R20 = 源模板缺陷，平台侧整列启用）
 *
 * 币种不在源模板枚举内（F 列自由输入），此处给常用币种作**建议项**并允许自定义，
 * 不做强约束（宁缺勿造：源模板没有的约束不凭空加）。
 */
export { CONFIRMATION_DICT_KEYS } from '../coordination/confirmationDicts'

/** 产品类型（源 E5 列名括注） */
export const WEALTH_PRODUCT_TYPES = ['封闭式', '开放式'] as const
export type WealthProductType = typeof WEALTH_PRODUCT_TYPES[number]

/** 是否受限（源 K 列 DV） */
export const WEALTH_RESTRICTED_OPTIONS = ['是', '否'] as const
export type WealthRestrictedOption = typeof WEALTH_RESTRICTED_OPTIONS[number]

/** 币种建议项（allow-create，非强约束） */
export const WEALTH_CURRENCY_SUGGESTIONS = [
  '人民币', '美元', '欧元', '港币', '日元', '英镑', '澳元',
] as const

/** 审计结论枚举 */
export const WEALTH_CONCLUSION_TYPES = ['完整', '存在例外需跟进', '不适用'] as const
export type WealthConclusionType = typeof WEALTH_CONCLUSION_TYPES[number]

export const WEALTH_LIST_DICT_KEYS = {
  /** 是/否 */
  YES_NO: 'yes_no',
} as const
