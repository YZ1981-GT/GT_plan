/**
 * 税务底稿单表结构：每个索引编号一份 JSON（sheets/<编号>.json）。
 *
 * 由 backend/scripts/gen/gen_tax_workpaper_sheets.py 从样表「税审底稿10.16.xlsx」生成，禁止手改；
 * 样表更新后重跑生成脚本（--check 可查漂移）。
 * 只做可视化还原：值、合并范围、呈现类型照原表；取数与计算规则另行定义。
 * 按编号懒加载：162 张表合计约 700KB，不进页面首包。
 */

/** 单元格呈现类型，只影响样式 */
export type TaxCellKind = 'title' | 'header' | 'meta' | 'number' | 'total' | 'input'

export interface TaxWorkpaperCell {
  text?: string
  kind?: TaxCellKind
  /** 横向合并的列数 */
  colSpan?: number
  /** 纵向合并的行数；被合并掉的格子在后续行里不再出现 */
  rowSpan?: number
  /** 样表单元格地址（合并区取左上角）：值由后端接口按此地址给出 */
  ref?: string
  /** f 公式格（只读）/ e 可填写（含取数格） */
  role?: 'f' | 'e'
  /** 数值显示口径 */
  fmt?: 'money' | 'pct' | 'int'
}

/** 一个编号可能对应样表里的多张 sheet（如 1-01 报告封面 + 报告正文），每张是一段 */
export interface TaxWorkpaperSheetPart {
  /** 分段标题；只有一段时没有 */
  title?: string
  /** 样表里的 sheet 名，便于对照 */
  source: string
  /** 单元格矩阵，每个子数组是一行 */
  rows: TaxWorkpaperCell[][]
}

export interface TaxWorkpaperSheetDefinition {
  code: string
  parts: TaxWorkpaperSheetPart[]
}

const loaders = import.meta.glob<TaxWorkpaperSheetDefinition>('./sheets/*.json', { import: 'default' })

function pathOf(code: string): string {
  return `./sheets/${code}.json`
}

/** 该编号是否已有表格结构 */
export function hasTaxWorkpaperSheet(code: string): boolean {
  return pathOf(code) in loaders
}

/** 取某编号的表格结构；没有录入返回 undefined */
export async function loadTaxWorkpaperSheet(code: string): Promise<TaxWorkpaperSheetDefinition | undefined> {
  const loader = loaders[pathOf(code)]
  return loader ? loader() : undefined
}
