/**
 * 汇算申报表结构（spec citar-assurance-report-menus）：目录 taxReturnIndex.json + 每张表 sheets/<编号>.json。
 *
 * 由 backend/scripts/gen/gen_tax_workpaper_sheets.py 从样表「税审底稿10.16.xlsx」生成，禁止手改。
 * 单表结构与税务底稿同一格式（TaxWorkpaperSheetDefinition），表格组件共用 TaxWorkpaperGrid。
 */
import type { TaxWorkpaperSheetDefinition } from '@/views/tax-workpapers/taxWorkpaperSheets'
import index from './taxReturnIndex.json'

export interface TaxReturnForm {
  /** 表单编号，如 A100000 */
  code: string
  name: string
  /** 「表单」页「是否填报」格（C 列） */
  markRef: string
  /** 样表默认是否填报 */
  filed: boolean
}

export interface TaxReturnIndex {
  cover: { code: string; name: string }
  formsCode: string
  formsSheet: string
  forms: TaxReturnForm[]
}

export const TAX_RETURN_INDEX = index as TaxReturnIndex

export const FILED_MARK = '√'
export const UNFILED_MARK = '□'

const loaders = import.meta.glob<TaxWorkpaperSheetDefinition>('./sheets/*.json', { import: 'default' })

export async function loadTaxReturnSheet(code: string): Promise<TaxWorkpaperSheetDefinition | undefined> {
  const loader = loaders[`./sheets/${code}.json`]
  return loader ? loader() : undefined
}

/** 编号 → 表名（封面 + 表单列出的表） */
export function taxReturnName(code: string): string {
  if (code === TAX_RETURN_INDEX.cover.code) return TAX_RETURN_INDEX.cover.name
  return TAX_RETURN_INDEX.forms.find(f => f.code === code)?.name ?? code
}
