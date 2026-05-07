/**
 * formRules.ts — 统一表单校验规则库（R8-S2-11）
 *
 * 消除"同一条客户名非空规则在 10 个视图各写一遍"的重复。
 * 所有 el-form :rules 优先组合本文件的规则。
 *
 * 用法：
 *   import { rules } from '@/utils/formRules'
 *   const formRules = {
 *     clientName: rules.clientName,
 *     amount: [rules.required('金额'), rules.amount],
 *     email: rules.email,
 *   }
 */
import type { FormItemRule } from 'element-plus'

export const rules = {
  /** 必填校验（生成器：传入字段 label） */
  required(label: string, trigger: 'blur' | 'change' = 'blur'): FormItemRule {
    return { required: true, message: `${label}不能为空`, trigger }
  },

  /** 金额（最多 2 位小数，允许负数） */
  amount: {
    pattern: /^-?\d+(\.\d{1,2})?$/,
    message: '请输入有效金额（最多 2 位小数）',
    trigger: 'blur' as const,
  } satisfies FormItemRule,

  /** 客户名：非空 + 2-100 字符 */
  clientName: [
    { required: true, message: '客户名不能为空', trigger: 'blur' },
    { min: 2, max: 100, message: '长度 2-100 字符', trigger: 'blur' },
  ] satisfies FormItemRule[],

  /** 科目编码：4-10 位数字 */
  accountCode: {
    pattern: /^\d{4,10}$/,
    message: '科目编码应为 4-10 位数字',
    trigger: 'blur' as const,
  } satisfies FormItemRule,

  /** 邮箱 */
  email: {
    type: 'email',
    message: '邮箱格式不正确',
    trigger: 'blur',
  } satisfies FormItemRule,

  /** 手机号（中国大陆 11 位，1 开头） */
  phone: {
    pattern: /^1\d{10}$/,
    message: '手机号应为 11 位数字（1 开头）',
    trigger: 'blur' as const,
  } satisfies FormItemRule,

  /** 百分比（0-100% 或 0-1） */
  ratio: {
    pattern: /^(0|0\.\d+|1|1\.0+|[1-9]\d*|[1-9]\d*\.\d+)%?$/,
    message: '请输入有效比例（0-100% 或 0-1）',
    trigger: 'blur' as const,
  } satisfies FormItemRule,

  /** 正整数 */
  positiveInt: {
    pattern: /^[1-9]\d*$/,
    message: '请输入正整数',
    trigger: 'blur' as const,
  } satisfies FormItemRule,

  /** 日期范围（YYYY-MM-DD，由 el-date-picker 输出） */
  dateRange: {
    type: 'array' as const,
    required: true,
    len: 2,
    message: '请选择起止日期',
    trigger: 'change' as const,
  } satisfies FormItemRule,

  /** 年度（四位数字，2000-2100） */
  year: {
    type: 'number' as const,
    min: 2000,
    max: 2100,
    message: '年度应在 2000-2100 之间',
    trigger: 'blur' as const,
  } satisfies FormItemRule,

  /** 身份证号（18 位，末位可为 X） */
  idCard: {
    pattern: /^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$/,
    message: '身份证号格式不正确',
    trigger: 'blur' as const,
  } satisfies FormItemRule,

  /** 统一社会信用代码（18 位） */
  creditCode: {
    pattern: /^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$/,
    message: '统一社会信用代码格式不正确',
    trigger: 'blur' as const,
  } satisfies FormItemRule,
}

/**
 * 组合：快速生成一个"必填 + 其他规则"的组合
 * @example makeRules('金额', rules.amount)
 */
export function makeRules(label: string, ...extra: FormItemRule[]): FormItemRule[] {
  return [rules.required(label), ...extra]
}

export default rules
