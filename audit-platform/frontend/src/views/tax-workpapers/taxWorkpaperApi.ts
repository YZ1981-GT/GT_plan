/**
 * 税审底稿后端接口：取数 + 公式计算后的本表值、保存手工值、表头参数。
 * 值格式与后端 tax_workpaper_service.encode_value 一致：{n} 数字（字符串，保精度）/ {s} 文字 / {b} 逻辑 / {e} 错误。
 */
import { api } from '@/services/apiProxy'
import { taxWorkpapers as P_tw } from '@/services/apiPaths'

export type TaxValue = { n: string } | { s: string } | { b: boolean } | { e: string } | null

export interface TaxCellMeta {
  /** rule = 按规则取数 / input = 手工填写 */
  origin: 'rule' | 'input'
  /** auto 照取 / confirm 待确认 / manual 需人工填写 */
  status?: 'auto' | 'confirm' | 'manual'
  /** 样表取数规则原文 */
  rule?: string
  /** 取不到的原因 */
  issue?: string
  /** 手工改过的格：原取数值 */
  auto?: TaxValue
}

export interface TaxSheetPartValues {
  source: string
  values: Record<string, TaxValue>
  cells: Record<string, TaxCellMeta>
}

export interface TaxSheetResult {
  code: string
  year: number
  version: number
  updated_at: string | null
  parts: TaxSheetPartValues[]
  issues: { sheet: string; ref: string; message: string }[]
  notices: string[]
}

export interface TaxParam {
  ref: string
  label: string
  options: string[]
  default_value: string | null
  value: string | number | null
  saved: boolean
}

export interface TaxParamsResult {
  year: number
  version: number
  params: TaxParam[]
}

/** 手工值：{sheet 名: {单元格地址: 数字 / 文字 / null}} */
export type TaxInputs = Record<string, Record<string, number | string | null>>

export function fetchTaxSheet(projectId: string, year: number, code: string): Promise<TaxSheetResult> {
  return api.get(P_tw.sheet(projectId, code), { params: { year } }) as Promise<TaxSheetResult>
}

export function saveTaxSheet(projectId: string, year: number, code: string, version: number, inputs: TaxInputs): Promise<TaxSheetResult> {
  return api.put(P_tw.sheet(projectId, code), { version, inputs }, { params: { year }, _silent: true } as any) as Promise<TaxSheetResult>
}

export function fetchTaxParams(projectId: string, year: number): Promise<TaxParamsResult> {
  return api.get(P_tw.params(projectId), { params: { year } }) as Promise<TaxParamsResult>
}

export function saveTaxParams(projectId: string, year: number, version: number, values: Record<string, string | null>): Promise<TaxParamsResult> {
  return api.put(P_tw.params(projectId), { version, values }, { params: { year }, _silent: true } as any) as Promise<TaxParamsResult>
}

/** 纳税调整汇总表一项；金额为两位小数字符串，方向决定加减；没有调整的项金额 0、方向空 */
export interface TaxAdjustmentItem {
  index: number
  name: string
  /** 调整账载科目；三~五类为「不适用」 */
  account: string
  direction: '' | '调增' | '调减' | '免税' | '减计' | '加计' | '抵免'
  amount: string
  /** 调整底稿位置（domain=tax_return 时是申报表格子） */
  location: { domain: 'workpaper' | 'tax_return'; code: string; sheet: string; ref: string } | null
  /** 取数出处（审核调整额 / 申报表行次） */
  source: string
  /** 只列出、不计入验算（境外所得，现阶段暂未包含） */
  excluded?: boolean
}

export interface TaxAdjustmentSummary {
  year: number
  items: TaxAdjustmentItem[]
  check: {
    profit: string
    profit_declared: string
    foreign: string
    increase: string
    decrease: string
    exempt: string
    reduce: string
    plus: string
    offset: string
    result: string
    declared: string
    declared_domestic: string
    diff: string
    /** 申报表 A100000 行次（利润总额 / 纳税调整后所得等） */
    lines: Record<string, string>
  }
  notices: string[]
}

export function fetchTaxAdjustmentSummary(projectId: string, year: number): Promise<TaxAdjustmentSummary> {
  return api.get(P_tw.adjustmentSummary(projectId), { params: { year } }) as Promise<TaxAdjustmentSummary>
}

const MONEY = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const INT = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })

/** 值 → 显示文字；fmt 来自样表数字格式（money 两位小数 / pct 百分比 / int 整数） */
export function formatTaxValue(value: TaxValue | undefined, fmt?: string): string {
  if (!value) return ''
  if ('s' in value) return value.s
  if ('e' in value) return value.e
  if ('b' in value) return value.b ? 'TRUE' : 'FALSE'
  const n = Number(value.n)
  if (!Number.isFinite(n)) return value.n
  if (fmt === 'pct') return `${(n * 100).toFixed(2)}%`
  if (fmt === 'int') return INT.format(n)
  if (fmt === 'money' || !Number.isInteger(n)) return MONEY.format(n)
  return INT.format(n)
}

/** 编辑框里的值（不带千分位，便于修改） */
export function editTextOf(value: TaxValue | undefined): string {
  if (!value) return ''
  if ('s' in value) return value.s
  if ('n' in value) return value.n
  return ''
}

/** 用户输入 → 保存值：像数字（可带千分位；以 % 结尾按百分数）就存数字，空串存 null，其余存文字 */
export function parseTaxInput(text: string): number | string | null {
  const raw = text.trim()
  if (!raw) return null
  const cleaned = raw.replace(/,/g, '').replace(/%$/, '')
  if (/^[-+]?(\d+\.?\d*|\.\d+)$/.test(cleaned)) {
    const n = Number(cleaned)
    return raw.endsWith('%') ? n / 100 : n
  }
  return raw
}
